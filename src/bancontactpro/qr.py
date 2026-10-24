"""Client-templated QR/deeplink URLs (On a Receipt, Top Up, Static QR). No HTTP call is made.

Two encoding passes matter: ``D``/``A``/``R`` are percent-encoded once into the payload URL, then the whole payload
URL is percent-encoded again as the ``c=`` parameter of the QR image URL. Both must use the same environment.
"""

from __future__ import annotations

from urllib.parse import quote

from .enums import BancontactEnvironment, QrCodeImageFormat, QrCodeImageSize

_PAY_HOST = {
    BancontactEnvironment.PRODUCTION: "https://pay.bancontact.net",
    BancontactEnvironment.PREPROD: "https://pay.acc.bancontact.net",
}
_QR_HOST = {
    BancontactEnvironment.PRODUCTION: "https://qrcodegenerator.api.bancontact.net",
    BancontactEnvironment.PREPROD: "https://qrcodegenerator.api.preprod.bancontact.net",
}


def _escape(value: str) -> str:
    return quote(value, safe="")


def build_fixed_amount_payment_url(
    environment: BancontactEnvironment,
    product_profile_id: str,
    amount_cents: int | None = None,
    description: str | None = None,
    reference: str | None = None,
) -> str:
    query = []
    if description is not None:
        query.append(f"D={_escape(description)}")
    if amount_cents is not None:
        query.append(f"A={amount_cents}")
    if reference is not None:
        query.append(f"R={_escape(reference)}")
    url = f"{_PAY_HOST[environment]}/t/1/{_escape(product_profile_id)}"
    return f"{url}?{'&'.join(query)}" if query else url


def build_static_qr_location_url(environment: BancontactEnvironment, product_profile_id: str, pos_id: str) -> str:
    return f"{_PAY_HOST[environment]}/l/1/{_escape(product_profile_id)}/{_escape(pos_id)}"


def build_qr_code_image_url(
    environment: BancontactEnvironment,
    payload_url: str,
    image_format: QrCodeImageFormat = QrCodeImageFormat.PNG,
    size: QrCodeImageSize | None = None,
) -> str:
    query = [f"f={image_format.value}"]
    if image_format == QrCodeImageFormat.PNG and size is not None:
        query.append(f"s={size.value}")
    query.append(f"c={_escape(payload_url)}")
    return f"{_QR_HOST[environment]}/qrcode?{'&'.join(query)}"
