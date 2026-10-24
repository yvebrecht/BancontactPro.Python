"""Request and response DTOs shared by the typed clients and the webhook payload.

Notes taken from the raw OpenAPI specs: ``Payment`` and ``MerchantCallback`` deliberately have no ``total_amount``
(the specs list it as required but never define it); ``CreatePaymentResponse.expires_at`` and ``Payment.expire_at``
are genuinely spelled differently in the spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .enums import MerchantPaymentStatus, PaymentChannel, PayoutStatus, RefundStatus

# --- Requests ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CreatePaymentRequest:
    """``POST v3/payments``. Only ``amount`` (cents, 1-999,999,999,999) is required."""

    amount: int
    reference: str | None = None
    bulk_id: str | None = None
    currency: str | None = None
    description: str | None = None
    identify_callback_url: str | None = None
    callback_url: str | None = None
    return_url: str | None = None


@dataclass(frozen=True)
class CreateStaticQrPaymentRequest:
    """``POST v3/payments/pos``. An active payment for the same pos id/profile is replaced."""

    amount: int
    pos_id: str
    reference: str | None = None
    bulk_id: str | None = None
    currency: str | None = None
    description: str | None = None
    shop_id: str | None = None
    shop_name: str | None = None
    identify_callback_url: str | None = None
    callback_url: str | None = None


@dataclass(frozen=True)
class CreateRefundRequest:
    """``POST v3/payments/{payment-id}/refunds``. Partial refunds are simply any amount."""

    amount: int
    currency: str
    description: str | None = None


@dataclass(frozen=True)
class PaymentAcknowledgeRequest:
    """``POST v3/payments/{id}/acknowledge`` for the VOID-mode flow."""

    currency: str
    amount: int
    reference: str | None = None


@dataclass(frozen=True)
class PaymentSearchQuery:
    """Filter body for ``POST v3/payments/search``. ``from_`` defaults server-side to yesterday."""

    from_: datetime | None = None
    to: datetime | None = None
    payment_statuses: list[MerchantPaymentStatus] | None = None
    reference: str | None = None


# --- Payment resources ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PaymentLink:
    href: str


@dataclass(frozen=True)
class PaymentLinks:
    self: PaymentLink
    deeplink: PaymentLink
    qrcode: PaymentLink
    cancel: PaymentLink | None = None
    refund: PaymentLink | None = None
    checkout: PaymentLink | None = None


@dataclass(frozen=True)
class PaymentCreditor:
    profile_id: str | None = None
    merchant_id: str | None = None
    name: str | None = None
    iban: str | None = None
    identify_callback_url: str | None = None
    callback_url: str | None = None


@dataclass(frozen=True)
class PaymentDebtor:
    name: str | None = None
    iban: str | None = None


@dataclass(frozen=True)
class CreatePaymentResponse:
    payment_id: str
    status: MerchantPaymentStatus
    created_at: datetime
    expires_at: datetime
    amount: int
    currency: str
    creditor: PaymentCreditor
    links: PaymentLinks
    description: str | None = None
    reference: str | None = None


@dataclass(frozen=True)
class Payment:
    payment_id: str
    created_at: datetime
    expire_at: datetime
    currency: str
    status: MerchantPaymentStatus
    creditor: PaymentCreditor
    amount: int
    links: PaymentLinks | None = None  # optional in get_payment_response, unlike payment_create_response
    succeeded_at: datetime | None = None
    debtor: PaymentDebtor | None = None
    description: str | None = None
    message: str | None = None
    reference: str | None = None
    bulk_id: str | None = None


@dataclass(frozen=True)
class PaymentSearchResponse:
    size: int
    total_pages: int
    total_elements: int
    number: int
    details: list[Payment] = field(default_factory=list)  # not required by the spec


@dataclass(frozen=True)
class DebtorRefundIban:
    iban: str


# --- Webhook ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CallbackDebtor:
    iban: str
    name: str | None = None


@dataclass(frozen=True)
class MerchantCallback:
    payment_id: str
    currency: str
    amount: int
    created_at: datetime
    status: MerchantPaymentStatus
    debtor: CallbackDebtor
    description: str | None = None
    reference: str | None = None
    expire_at: datetime | None = None
    succeeded_at: datetime | None = None


# --- Refunds ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RefundCreationResponse:
    refund_id: str
    payment_id: str
    status: RefundStatus
    amount: int
    currency: str
    creation_date: datetime
    description: str | None = None


@dataclass(frozen=True)
class RefundModel:
    refund_id: str
    payment_id: str
    amount: int
    currency: str
    status: RefundStatus
    creation_date: datetime
    description: str | None = None


# --- Reconciliation ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Payout:
    payout_id: str
    merchant_id: str
    bulk_id: str
    iban: str
    payout_status: PayoutStatus
    payout_date: datetime
    payout_currency: str
    total_payments: int
    total_refunds: int
    total_payment_amount: int
    total_refund_amount: int
    payout_amount: int


@dataclass(frozen=True)
class PayoutListResponse:
    size: int
    total_pages: int
    total_elements: int
    number: int
    payouts: list[Payout]


@dataclass(frozen=True)
class ReconciliationPaymentDetails:
    payment_id: str
    payment_profile_id: str
    merchant_name: str
    payment_channel: PaymentChannel
    currency: str
    amount: int
    transaction_date: datetime
    payout_id: str | None = None
    reference: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class PayoutPaymentsResponse:
    size: int
    total_pages: int
    total_elements: int
    number: int
    payments: list[ReconciliationPaymentDetails]


@dataclass(frozen=True)
class ReconciliationRefundDetails:
    refund_id: str
    payment_id: str
    payment_profile_id: str
    merchant_name: str
    payment_channel: PaymentChannel
    currency: str
    amount: int
    transaction_date: datetime
    payout_id: str | None = None
    reference: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class PayoutRefundsResponse:
    size: int
    total_pages: int
    total_elements: int
    number: int
    refunds: list[ReconciliationRefundDetails]


@dataclass(frozen=True)
class ErrorResponse:
    """Payment API errors also carry ``trace_id``/``span_id``; Refund and Reconciliation errors do not."""

    code: str | None = None
    message: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
