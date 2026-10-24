from __future__ import annotations

import json
from dataclasses import dataclass

from ._json import from_json
from .errors import InvalidCallbackException
from .models import MerchantCallback
from .signing import BancontactSignatureVerifier


@dataclass(frozen=True)
class VerifiedCallback:
    payload: MerchantCallback
    #: The ``jti`` claim: unique per message. Bancontact retries a callback with identical headers and body, so
    #: handlers should tolerate duplicates.
    request_id: str


class BancontactCallbackVerifier:
    """The entry point for inbound webhooks: verify the signature, then parse the body.

    Failure raises ``InvalidCallbackException``: "this callback cannot be trusted" should stop request processing,
    not be a value the caller might ignore. Answer ``200 OK`` only after verifying and processing.
    """

    def __init__(self, signature_verifier: BancontactSignatureVerifier) -> None:
        self._signature_verifier = signature_verifier

    async def verify_and_parse(self, signature_header: str, body: bytes, path: str) -> VerifiedCallback:
        """``signature_header`` is the ``Signature`` header, ``body`` the raw request bytes (not re-serialized
        JSON), ``path`` the request path."""
        claims = await self._signature_verifier.verify(signature_header, body, path)
        if claims is None:
            raise InvalidCallbackException("The callback's signature could not be verified.")

        try:
            payload = from_json(MerchantCallback, json.loads(body))
        except (ValueError, KeyError, TypeError, AttributeError) as ex:
            raise InvalidCallbackException("The callback body could not be parsed.") from ex

        return VerifiedCallback(payload, claims.request_id)
