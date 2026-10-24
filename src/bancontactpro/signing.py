"""Detached JWS (RFC 7797) signing and verification, ES256 over P-256.

The compact form has an empty payload segment: ``base64url(header) + ".." + base64url(signature)``, where the
signature covers ``base64url(header) + "." + base64url(body)``. The separator in the signing input is not stated by
Bancontact's callback guide (it writes ``+``); ``.`` is the RFC 7797 convention and is an open item to confirm with
devsupport@bancontact.com against a real sample. The header carries five custom claims under a
``https://payconiq.com/`` namespace, all listed in ``crit``.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

_NS = "https://payconiq.com/"
_CRIT = [f"{_NS}sub", f"{_NS}iss", f"{_NS}iat", f"{_NS}jti", f"{_NS}path"]
_IAT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
_COORDINATE_BYTES = 32  # P-256


@dataclass(frozen=True)
class JoseHeader:
    kid: str
    merchant_profile_id: str
    issuer: str
    issued_at: datetime
    request_id: str
    path: str


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    """Strict unpadded base64url; raises ``ValueError`` on anything else."""
    if not re.fullmatch(r"[A-Za-z0-9_-]*", text) or len(text) % 4 == 1:
        raise ValueError("Not valid unpadded base64url.")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except binascii.Error as ex:
        raise ValueError("Not valid unpadded base64url.") from ex


def _format_iat(value: datetime) -> str:
    value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def _parse_iat(value: str) -> datetime | None:
    if not _IAT_PATTERN.match(value):
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def compute_signing_input(encoded_header: str, body: bytes) -> bytes:
    return f"{encoded_header}.{b64url_encode(body)}".encode("ascii")


def try_split(detached_jws: str) -> tuple[str, str] | None:
    """Splits ``header..signature`` (RFC 7797, empty payload segment), as documented by Bancontact's callback guide
    and API specs. The single-dot form ``header.signature`` is tolerated on input."""
    parts = detached_jws.split(".")
    if len(parts) == 3 and parts[1] == "":
        return parts[0], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1]
    return None


def sign(header: JoseHeader, body: bytes, private_key: ec.EllipticCurvePrivateKey) -> str:
    """Signs ``body`` and returns the detached JWS for the ``Signature`` header."""
    header_json = {
        "typ": "jose+json",
        "kid": header.kid,
        "alg": "ES256",
        f"{_NS}sub": header.merchant_profile_id,
        f"{_NS}iss": header.issuer,
        f"{_NS}iat": _format_iat(header.issued_at),
        f"{_NS}jti": header.request_id,
        f"{_NS}path": header.path,
        "crit": _CRIT,
    }
    # ensure_ascii=False and no whitespace: the URI-shaped claim names must round-trip byte-for-byte.
    encoded_header = b64url_encode(json.dumps(header_json, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    der = private_key.sign(compute_signing_input(encoded_header, body), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    raw = r.to_bytes(_COORDINATE_BYTES, "big") + s.to_bytes(_COORDINATE_BYTES, "big")
    return f"{encoded_header}..{b64url_encode(raw)}"


def _verify_raw(public_key: ec.EllipticCurvePublicKey, signature: bytes, signing_input: bytes) -> bool:
    if len(signature) != 2 * _COORDINATE_BYTES:
        return False
    r = int.from_bytes(signature[:_COORDINATE_BYTES], "big")
    s = int.from_bytes(signature[_COORDINATE_BYTES:], "big")
    try:
        public_key.verify(encode_dss_signature(r, s), signing_input, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    return True


def verify(detached_jws: str, body: bytes, public_key: ec.EllipticCurvePublicKey) -> bool:
    """Pure signature check (no header policy). Never raises on malformed input."""
    parts = try_split(detached_jws)
    if parts is None:
        return False
    encoded_header, encoded_signature = parts
    try:
        signature = b64url_decode(encoded_signature)
    except ValueError:
        return False
    return _verify_raw(public_key, signature, compute_signing_input(encoded_header, body))


class JwksKeySource(Protocol):
    """Resolves a Bancontact public key by ``kid``; returns None when it does not exist."""

    async def get_key(self, kid: str) -> ec.EllipticCurvePublicKey | None: ...


class BancontactSignatureVerifier:
    """Verifies an inbound detached JWS and its structural policy.

    Returns the parsed claims on success and None on any failure: malformed or malicious inbound data is an expected,
    non-exceptional occurrence for anything facing the public internet.
    """

    def __init__(self, jwks: JwksKeySource) -> None:
        self._jwks = jwks

    async def verify(self, signature_header: str, body: bytes, path: str) -> JoseHeader | None:
        parts = try_split(signature_header)
        if parts is None:
            return None
        encoded_header, encoded_signature = parts

        try:
            claims = json.loads(b64url_decode(encoded_header))
            kid = claims["kid"]
            sub = claims[f"{_NS}sub"]
            iss = claims[f"{_NS}iss"]
            iat = claims[f"{_NS}iat"]
            jti = claims[f"{_NS}jti"]
            claimed_path = claims[f"{_NS}path"]
            crit = claims.get("crit", [])
            fields = (kid, sub, iss, iat, jti, claimed_path)
            if not isinstance(claims, dict) or not all(isinstance(f, str) for f in fields) or not isinstance(crit, list):
                return None
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            return None

        # An unrecognised (or missing) critical extension must cause rejection, never silent ignoring.
        if len(crit) != len(_CRIT) or not all(c in _CRIT for c in crit):
            return None

        # Defends against a validly signed message being replayed against the wrong route.
        if claimed_path != path:
            return None

        try:
            signature = b64url_decode(encoded_signature)
        except ValueError:
            return None

        public_key = await self._jwks.get_key(kid)
        if public_key is None:
            return None

        if not _verify_raw(public_key, signature, compute_signing_input(encoded_header, body)):
            return None

        issued_at = _parse_iat(iat)
        if issued_at is None:
            return None

        return JoseHeader(kid, sub, iss, issued_at, jti, claimed_path)


def jwk_to_public_key(jwk: dict[str, Any]) -> ec.EllipticCurvePublicKey | None:
    """Converts an EC/P-256 JWK to a public key, or None if it is some other kind of key."""
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256" or not jwk.get("x") or not jwk.get("y"):
        return None
    try:
        x = int.from_bytes(b64url_decode(jwk["x"]), "big")
        y = int.from_bytes(b64url_decode(jwk["y"]), "big")
        return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    except (ValueError, TypeError):
        return None


def to_public_jwk_json(key: ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey, kid: str) -> str:
    """Exports the public half of a P-256 key as a JWK, for Bancontact to host and fetch."""
    public = key.public_key() if isinstance(key, ec.EllipticCurvePrivateKey) else key
    if not isinstance(public.curve, ec.SECP256R1):
        raise ValueError(f"Only P-256 (ES256) keys are supported; got curve '{public.curve.name}'.")
    numbers = public.public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "kid": kid,
        "use": "sig",
        "alg": "ES256",
        "x": b64url_encode(numbers.x.to_bytes(_COORDINATE_BYTES, "big")),
        "y": b64url_encode(numbers.y.to_bytes(_COORDINATE_BYTES, "big")),
    }
    return json.dumps(jwk, separators=(",", ":"))


def load_ec_private_key_pem(pem: str) -> ec.EllipticCurvePrivateKey:
    """Parses a PEM-encoded EC (P-256) private key (PKCS#8 or SEC1)."""
    key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("The signing key must be an EC private key on the P-256 curve.")
    return key
