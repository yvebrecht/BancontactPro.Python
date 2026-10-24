from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

from .enums import BancontactEnvironment, BancontactProduct


@dataclass(frozen=True)
class ProductCredentials:
    """The API key and PPID (merchant profile id) Bancontact issued for one product type."""

    api_key: str | None = None
    merchant_profile_id: str | None = None

    @property
    def is_complete(self) -> bool:
        return bool((self.api_key or "").strip()) and bool((self.merchant_profile_id or "").strip())

    def __repr__(self) -> str:
        return f"ProductCredentials(api_key=***, merchant_profile_id={self.merchant_profile_id!r})"


@dataclass(frozen=True)
class SigningKey:
    """The merchant's ES256 (P-256) signing key, needed for Refund and Reconciliation calls."""

    kid: str
    private_key_pem: str

    def __repr__(self) -> str:
        return f"SigningKey(kid={self.kid!r}, private_key_pem=***)"


@dataclass(frozen=True)
class BancontactCredentials:
    """A snapshot of everything the library needs, read afresh on every use (never cached by the library)."""

    environment: BancontactEnvironment = BancontactEnvironment.PREPROD
    products: Mapping[BancontactProduct, ProductCredentials] = field(default_factory=dict)
    signing_key: SigningKey | None = None
    #: The ``iss`` claim of signed requests. The Payment and Refund specs say "Payconiq"; the Reconciliation
    #: spec templates it as the merchant id, which cannot be resolved from the documentation alone.
    issuer: str = "Payconiq"

    def get_credentials(self, product: BancontactProduct) -> ProductCredentials | None:
        credentials = self.products.get(product)
        return credentials if credentials is not None and credentials.is_complete else None


#: Anything that returns the current credentials, directly or as an awaitable. Called on every use, so it may read
#: a database or secret store; cache briefly yourself if that is expensive.
CredentialsProvider = Callable[[], BancontactCredentials | Awaitable[BancontactCredentials]]


def as_provider(source: BancontactCredentials | CredentialsProvider) -> CredentialsProvider:
    """Accepts a fixed ``BancontactCredentials`` or a provider callable."""
    if isinstance(source, BancontactCredentials):
        return lambda: source
    return source


async def resolve(provider: CredentialsProvider) -> BancontactCredentials:
    result = provider()
    if inspect.isawaitable(result):
        result = await result
    return result
