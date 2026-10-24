"""The three typed API clients. Each wraps a ``Transport`` bound to one product's credentials."""

from __future__ import annotations

from datetime import date

from ._json import from_json
from .errors import BancontactApiException, RefundIdempotencyConflictException
from .http import Transport, escape
from .models import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    CreateRefundRequest,
    CreateStaticQrPaymentRequest,
    DebtorRefundIban,
    Payment,
    PaymentAcknowledgeRequest,
    PaymentSearchQuery,
    PaymentSearchResponse,
    PayoutListResponse,
    PayoutPaymentsResponse,
    PayoutRefundsResponse,
    RefundCreationResponse,
    RefundModel,
)


def _with_query(path: str, params: list[str]) -> str:
    return f"{path}?{'&'.join(params)}" if params else path


def _paging(params: list[str], page: int | None, size: int | None) -> None:
    if page is not None:
        params.append(f"page={page}")
    if size is not None:
        params.append(f"size={size}")


class PaymentClient:
    """Payment API v3: online, VOID-mode and static QR payments. Authenticated by the product's API key."""

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def create(self, request: CreatePaymentRequest) -> CreatePaymentResponse:
        """``POST v3/payments``.

        If the call times out the outcome is unknown: Bancontact may have created the payment. Do not retry blindly;
        look the payment up by the reference you sent with ``search`` first.
        """
        return from_json(CreatePaymentResponse, await self._t.request("POST", "v3/payments", request))

    async def get(self, payment_id: str) -> Payment:
        """``GET v3/payments/{id}``: the documented polling fallback."""
        return from_json(Payment, await self._t.request("GET", f"v3/payments/{escape(payment_id)}"))

    async def cancel(self, payment_id: str) -> None:
        """``DELETE v3/payments/{id}``, allowed while the payment is PENDING or IDENTIFIED."""
        await self._t.request("DELETE", f"v3/payments/{escape(payment_id)}")

    async def search(
        self, query: PaymentSearchQuery | None = None, page: int | None = None, size: int | None = None
    ) -> PaymentSearchResponse:
        """``POST v3/payments/search``. ``page`` is zero-based (default 0); ``size`` max 100 (default 10)."""
        params: list[str] = []
        _paging(params, page, size)
        body = query if query is not None else PaymentSearchQuery()
        return from_json(PaymentSearchResponse, await self._t.request("POST", _with_query("v3/payments/search", params), body))

    async def acknowledge(self, payment_id: str, request: PaymentAcknowledgeRequest) -> None:
        """``POST v3/payments/{id}/acknowledge`` for the VOID-mode flow (PENDING_MERCHANT_ACKNOWLEDGEMENT)."""
        await self._t.request("POST", f"v3/payments/{escape(payment_id)}/acknowledge", request)

    async def get_debtor_refund_iban(self, payment_id: str) -> DebtorRefundIban:
        """``GET v3/payments/{id}/debtor/refundIban``. Requires the payment to be SUCCEEDED."""
        return from_json(DebtorRefundIban, await self._t.request("GET", f"v3/payments/{escape(payment_id)}/debtor/refundIban"))

    async def create_static_qr_payment(self, request: CreateStaticQrPaymentRequest) -> CreatePaymentResponse:
        """``POST v3/payments/pos``. Replaces the till's active payment; a timed-out call has an unknown outcome."""
        return from_json(CreatePaymentResponse, await self._t.request("POST", "v3/payments/pos", request))


class RefundClient:
    """Refund API v3. Requests are signed with the merchant's key."""

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def create(self, payment_id: str, request: CreateRefundRequest, idempotency_key: str | None = None) -> RefundCreationResponse:
        """``POST v3/payments/{payment-id}/refunds``. Idempotent on the ``Idempotency-Key`` header (max 64 chars).

        Pass the same key when retrying the same refund. Generated (UUID) when omitted, in which case a retry
        would create a second refund, so supply your own key for anything you may retry.
        """
        import uuid

        key = idempotency_key or str(uuid.uuid4())
        if len(key) > 64:
            raise ValueError("The Idempotency-Key may be at most 64 characters.")
        try:
            data = await self._t.request("POST", f"v3/payments/{escape(payment_id)}/refunds", request, {"Idempotency-Key": key})
        except BancontactApiException as ex:
            # The key was reused with different parameters: a caller bug, not a transient failure.
            if ex.code == "REFUND_REQUEST_CONFLICT":
                raise RefundIdempotencyConflictException(key, ex) from ex
            raise
        return from_json(RefundCreationResponse, data)

    async def get(self, payment_id: str, refund_id: str) -> RefundModel:
        """``GET v3/payments/{payment-id}/refunds/{refund-id}``."""
        return from_json(RefundModel, await self._t.request("GET", f"v3/payments/{escape(payment_id)}/refunds/{escape(refund_id)}"))


class ReconciliationClient:
    """Reconciliation API v3. Requests are signed with the merchant's key.

    ``size`` is fixed by the spec (minimum, maximum and default are all 10000); it is exposed in case that changes.
    """

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def get_payouts(self, on: date | None = None, page: int | None = None, size: int | None = None) -> PayoutListResponse:
        """``GET v3/reconciliation/payouts``. ``on`` defaults server-side to the current UTC date."""
        params: list[str] = []
        if on is not None:
            params.append(f"date={on.isoformat()}")
        _paging(params, page, size)
        return from_json(PayoutListResponse, await self._t.request("GET", _with_query("v3/reconciliation/payouts", params)))

    async def get_payments(
        self,
        payout_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int | None = None,
        size: int | None = None,
    ) -> PayoutPaymentsResponse:
        """``GET v3/reconciliation/payments``, by payout id or by a date range of at most 30 days."""
        params = self._payout_filter(payout_id, start_date, end_date)
        _paging(params, page, size)
        return from_json(PayoutPaymentsResponse, await self._t.request("GET", _with_query("v3/reconciliation/payments", params)))

    async def get_refunds(
        self,
        payout_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int | None = None,
        size: int | None = None,
    ) -> PayoutRefundsResponse:
        """``GET v3/reconciliation/refunds``, by payout id or by a date range of at most 30 days."""
        params = self._payout_filter(payout_id, start_date, end_date)
        _paging(params, page, size)
        return from_json(PayoutRefundsResponse, await self._t.request("GET", _with_query("v3/reconciliation/refunds", params)))

    @staticmethod
    def _payout_filter(payout_id: str | None, start_date: date | None, end_date: date | None) -> list[str]:
        if (start_date is None) != (end_date is None):
            raise ValueError("start_date and end_date must be given together.")
        if start_date is not None and end_date is not None and (end_date - start_date).days > 30:
            raise ValueError("The range between start_date and end_date can be at most 30 days.")
        params: list[str] = []
        if payout_id is not None:
            params.append(f"payout-id={escape(payout_id)}")
        if start_date is not None and end_date is not None:
            params.append(f"start-date={start_date.isoformat()}")
            params.append(f"end-date={end_date.isoformat()}")
        return params
