from __future__ import annotations

from .enums import BancontactEnvironment

_MERCHANT_API = {
    BancontactEnvironment.PREPROD: "https://merchant.api.preprod.bancontact.net/",
    BancontactEnvironment.PRODUCTION: "https://merchant.api.bancontact.net/",
}
_JWKS = {
    BancontactEnvironment.PREPROD: "https://jwks.preprod.bancontact.net/",
    BancontactEnvironment.PRODUCTION: "https://jwks.bancontact.net/",
}


def get_merchant_api_base_url(environment: BancontactEnvironment) -> str:
    """The base address of the Payment, Refund and Reconciliation APIs."""
    return _MERCHANT_API[BancontactEnvironment(environment)]


def get_jwks_url(environment: BancontactEnvironment) -> str:
    """The address of Bancontact's JWKS (the public keys that sign its callbacks)."""
    return _JWKS[BancontactEnvironment(environment)]
