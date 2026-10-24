from __future__ import annotations

from .enums import BancontactProduct


class BancontactApiException(Exception):
    """Bancontact returned a non-success HTTP response.

    ``trace_id``/``span_id`` are what to hand Bancontact support; only the Payment API's errors include them.
    ``code`` is empty when the response body was not Bancontact's error shape.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.trace_id = trace_id
        self.span_id = span_id


class RefundIdempotencyConflictException(BancontactApiException):
    """The Idempotency-Key was reused with different parameters (``REFUND_REQUEST_CONFLICT``): a caller bug."""

    def __init__(self, idempotency_key: str, inner: BancontactApiException) -> None:
        super().__init__(
            inner.status_code,
            inner.code,
            f"The idempotency key '{idempotency_key}' was already used for a refund with different parameters. {inner}",
            inner.trace_id,
            inner.span_id,
        )
        self.idempotency_key = idempotency_key


class InvalidCallbackException(Exception):
    """A webhook callback could not be trusted: bad signature or unparseable body."""


class BancontactProductNotConfiguredException(RuntimeError):
    def __init__(self, product: BancontactProduct) -> None:
        super().__init__(
            f"Bancontact product '{product.value}' is not configured: it needs both its api_key and its "
            "merchant_profile_id (PPID), the pair Bancontact issued for this product."
        )
        self.product = product


class BancontactSigningKeyNotConfiguredException(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "The Refund and Reconciliation APIs require a signed request. Configure a signing key (kid and "
            "private_key_pem) and host the public key as a JWKS whose URL is shared with Bancontact. "
            "The Payment API works with a product's API key alone."
        )
