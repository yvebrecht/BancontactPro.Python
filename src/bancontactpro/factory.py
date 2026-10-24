from __future__ import annotations

import httpx
from cryptography.hazmat.primitives.asymmetric import ec

from .clients import PaymentClient, ReconciliationClient, RefundClient
from .credentials import BancontactCredentials, CredentialsProvider, ProductCredentials, as_provider, resolve
from .endpoints import get_merchant_api_base_url
from .enums import BancontactProduct
from .errors import BancontactProductNotConfiguredException, BancontactSigningKeyNotConfiguredException
from .http import ApiKeyAuth, SigningAuth, Transport
from .jwks import JwksClient
from .signing import BancontactSignatureVerifier, load_ec_private_key_pem
from .webhooks import BancontactCallbackVerifier


class BancontactClientFactory:
    """Creates product-bound clients from the *current* credentials.

    Credentials are read on every call and never captured, so a provider that changes at runtime (a rotated key, an
    environment switch) takes effect immediately. The returned clients keep the credentials they were created with,
    which is why callers ask for one per operation rather than holding it. Bancontact issues credentials per product
    type, so a client is always bound to one product.
    """

    def __init__(
        self,
        credentials: BancontactCredentials | CredentialsProvider,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._credentials = as_provider(credentials)
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient()
        self._jwks: JwksClient | None = None
        self._signing_key_cache: tuple[str, str, ec.EllipticCurvePrivateKey] | None = None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def is_configured(self, product: BancontactProduct) -> bool:
        return (await resolve(self._credentials)).get_credentials(product) is not None

    async def payments(self, product: BancontactProduct) -> PaymentClient:
        credentials, pair = await self._prepare(product)
        return PaymentClient(Transport(self._http, get_merchant_api_base_url(credentials.environment), ApiKeyAuth(pair.api_key)))  # type: ignore[arg-type]

    async def refunds(self, product: BancontactProduct) -> RefundClient:
        return RefundClient(await self._signed_transport(product))

    async def reconciliation(self, product: BancontactProduct) -> ReconciliationClient:
        return ReconciliationClient(await self._signed_transport(product))

    def callback_verifier(self) -> BancontactCallbackVerifier:
        """The verifier for inbound webhooks. Uses one long-lived JWKS cache; never build a ``JwksClient`` per call."""
        if self._jwks is None:
            self._jwks = JwksClient(self._credentials, self._http)
        return BancontactCallbackVerifier(BancontactSignatureVerifier(self._jwks))

    async def _prepare(self, product: BancontactProduct) -> tuple[BancontactCredentials, ProductCredentials]:
        credentials = await resolve(self._credentials)
        pair = credentials.get_credentials(product)
        if pair is None:
            raise BancontactProductNotConfiguredException(product)
        return credentials, pair

    async def _signed_transport(self, product: BancontactProduct) -> Transport:
        credentials, pair = await self._prepare(product)
        key = credentials.signing_key
        if key is None or not key.kid.strip() or not key.private_key_pem.strip():
            raise BancontactSigningKeyNotConfiguredException()
        auth = SigningAuth(
            api_key=pair.api_key,  # type: ignore[arg-type]
            merchant_profile_id=pair.merchant_profile_id,  # type: ignore[arg-type]
            issuer=credentials.issuer,
            kid=key.kid,
            private_key=self._parse_signing_key(key.kid, key.private_key_pem),
        )
        return Transport(self._http, get_merchant_api_base_url(credentials.environment), auth)

    def _parse_signing_key(self, kid: str, pem: str) -> ec.EllipticCurvePrivateKey:
        # Parsing a PEM costs more than a request needs, so the last parsed key is kept, keyed on its content.
        cached = self._signing_key_cache
        if cached is not None and cached[0] == kid and cached[1] == pem:
            return cached[2]
        try:
            parsed = load_ec_private_key_pem(pem)
        except (ValueError, TypeError) as ex:
            raise ValueError(
                f"The signing key '{kid}' is not a valid PEM-encoded EC (P-256) private key, "
                "so Refund and Reconciliation requests cannot be signed."
            ) from ex
        self._signing_key_cache = (kid, pem, parsed)
        return parsed
