from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives.asymmetric import ec

from ._json import to_json
from ._version import __version__
from .errors import BancontactApiException
from .signing import JoseHeader, sign

DEFAULT_TIMEOUT_SECONDS = 100
USER_AGENT = f"bancontactpro-python/{__version__} (+https://github.com/yvebrecht/BancontactPro.Python)"


def escape(value: str) -> str:
    """Percent-encodes one path or query value."""
    return quote(value, safe="")


@dataclass(frozen=True)
class ApiKeyAuth:
    """Payment API: the API key alone authenticates (the spec lists the JWS scheme as an alternative)."""

    api_key: str

    def apply(self, headers: dict[str, str], method: str, path: str, body: bytes) -> None:
        headers["Authorization"] = f"Bearer {self.api_key}"


@dataclass(frozen=True)
class SigningAuth:
    """Refund and Reconciliation: bearer API key plus a detached JWS ``Signature`` over the request body."""

    api_key: str
    merchant_profile_id: str
    issuer: str
    kid: str
    private_key: ec.EllipticCurvePrivateKey

    def apply(self, headers: dict[str, str], method: str, path: str, body: bytes) -> None:
        header = JoseHeader(
            kid=self.kid,
            merchant_profile_id=self.merchant_profile_id,
            issuer=self.issuer,
            issued_at=datetime.now(UTC),
            request_id=str(uuid.uuid4()),
            path=path,  # the absolute path of the request URI, without the query string
        )
        headers["Signature"] = sign(header, body, self.private_key)
        headers["Authorization"] = f"Bearer {self.api_key}"


class Transport:
    """One configured connection to the merchant API: base URL, credentials, shared ``httpx.Client``."""

    def __init__(self, http: httpx.AsyncClient, base_url: str, auth: ApiKeyAuth | SigningAuth) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._auth = auth

    async def request(
        self,
        method: str,
        relative_path: str,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Sends the request, raises ``BancontactApiException`` on a non-success status, returns decoded JSON
        (or None for an empty body). ``relative_path`` may carry an already-encoded query string."""
        path, _, query = relative_path.partition("?")
        content = json.dumps(to_json(body), separators=(",", ":")).encode("utf-8") if body is not None else b""
        request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        self._auth.apply(request_headers, method, "/" + path, content)

        url = f"{self._base_url}/{path}" + (f"?{query}" if query else "")
        response = await self._http.request(method, url, content=content or None, headers=request_headers, timeout=DEFAULT_TIMEOUT_SECONDS)
        ensure_success(response)
        return response.json() if response.content else None


def ensure_success(response: httpx.Response) -> None:
    """Turns a non-success response into ``BancontactApiException``.

    ``trace_id``/``span_id`` are only defined by the Payment API's error schema; they are None for Refund and
    Reconciliation errors. A body that is not Bancontact's error shape (an upstream 502, say) falls back to a
    generic exception carrying the raw status and text, never an unrelated parse error.
    """
    if response.is_success:
        return

    text = response.text
    error: dict[str, Any] | None = None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and isinstance(parsed.get("code"), str) and parsed["code"]:
            error = parsed
    except ValueError:
        pass

    if error is not None:
        raise BancontactApiException(
            response.status_code,
            error["code"],
            error.get("message") or text,
            error.get("traceId"),
            error.get("spanId"),
        )

    message = (
        f"Bancontact returned {response.status_code} with no response body."
        if not text.strip()
        else f"Bancontact returned {response.status_code}: {text}"
    )
    challenge = response.headers.get("WWW-Authenticate")
    if challenge:
        message += f" (WWW-Authenticate: {challenge})"
    raise BancontactApiException(response.status_code, "", message)
