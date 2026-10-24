from enum import Enum


class _TolerantStrEnum(str, Enum):
    """A string enum that does not crash on values added to the API later.

    An unknown wire value becomes a pseudo-member that compares equal to that string and is not part of
    ``list(Enum)``, so a new server-side status never breaks parsing of an otherwise valid response.
    """

    @classmethod
    def _missing_(cls, value: object) -> "_TolerantStrEnum | None":
        if not isinstance(value, str):
            return None
        member = str.__new__(cls, value)
        member._name_ = value
        member._value_ = value
        return member


class BancontactEnvironment(_TolerantStrEnum):
    PREPROD = "Preprod"
    PRODUCTION = "Production"


class BancontactProduct(_TolerantStrEnum):
    ON_DISPLAY = "OnDisplay"
    ON_RECEIPT = "OnReceipt"
    STATIC_QR = "StaticQr"
    TOP_UP = "TopUp"


class MerchantPaymentStatus(_TolerantStrEnum):
    PENDING = "PENDING"
    IDENTIFIED = "IDENTIFIED"
    AUTHORIZED = "AUTHORIZED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    PENDING_MERCHANT_ACKNOWLEDGEMENT = "PENDING_MERCHANT_ACKNOWLEDGEMENT"
    VOIDED = "VOIDED"


class PaymentChannel(_TolerantStrEnum):
    ONLINE = "ONLINE"
    INSTORE = "INSTORE"
    INVOICE = "INVOICE"


class PayoutStatus(_TolerantStrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class RefundStatus(_TolerantStrEnum):
    # PROCESSING was removed in Refund API v3.0.2; don't model it.
    PENDING = "PENDING"
    REFUNDED = "REFUNDED"
    FAILED = "FAILED"


class QrCodeImageFormat(str, Enum):
    PNG = "PNG"
    SVG = "SVG"


class QrCodeImageSize(str, Enum):
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"
