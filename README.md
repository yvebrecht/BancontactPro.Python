# BancontactPro.Python

> **Dit is geen officieel project van Bancontact.** Deze bibliotheek is onafhankelijk ontwikkeld op basis van de openbare Bancontact Pro-documentatie en is niet gemaakt, goedgekeurd of ondersteund door Bancontact (of Payconiq). 'Bancontact' en 'Bancontact Pro' zijn merken van hun eigenaars en worden enkel beschrijvend gebruikt. Overzicht: [BancontactPro.SDK](https://github.com/yvebrecht/BancontactPro.SDK).

Een async Python-client voor de [Bancontact Pro](https://docs.bancontactpro.com/)-API's: Payment, Refund en Reconciliation, met request-signing, verificatie van callbacks via JWKS en QR-/deeplinkgeneratie.

> **Status: in ontwikkeling, nog niet gepubliceerd en nog niet getest tegen Bancontact zelf.** Alles is getest met gemockte HTTP. Het pakket staat nog niet op PyPI en de naam `bancontactpro` is nog niet gereserveerd. De bibliotheek is gebouwd op de documentatie en specs van Bancontact, niet als port van een andere taalversie.

## Vereisten

Python 3.11 of hoger. Afhankelijkheden: `httpx` en `cryptography`.

## Credentials

Bancontact geeft per producttype (On a Display, On a Receipt, Static QR, Top Up) een API-key en een PPID. Refund- en Reconciliation-aanvragen moeten bovendien ondertekend worden met jouw eigen ES256-sleutel (P-256); de publieke sleutel host je als JWKS en deel je met Bancontact. Voor de Payment-API volstaat de API-key.

```python
from bancontactpro import (
    BancontactClientFactory, BancontactCredentials, BancontactEnvironment,
    BancontactProduct, ProductCredentials, SigningKey,
)

credentials = BancontactCredentials(
    environment=BancontactEnvironment.PREPROD,  # standaard; PRODUCTION voor echte betalingen
    products={BancontactProduct.ON_DISPLAY: ProductCredentials(api_key="...", merchant_profile_id="...")},
    signing_key=SigningKey(kid="mijn-kid", private_key_pem=open("key.pem").read()),
)
factory = BancontactClientFactory(credentials)
```

In plaats van een vast object kun je een functie meegeven (sync of async) die de actuele credentials teruggeeft, bijvoorbeeld uit een kluis of database. De bibliotheek roept ze bij elk gebruik opnieuw aan en cachet niets.

## Een betaling aanmaken

```python
payments = await factory.payments(BancontactProduct.ON_DISPLAY)
payment = await payments.create(CreatePaymentRequest(amount=1000, reference="order-42"))
print(payment.links.qrcode.href, payment.links.deeplink.href)

status = await payments.get(payment.payment_id)  # polling als terugval voor de callback
```

Bedragen zijn gehele getallen in cents. Bij een time-out op `create` is de uitkomst onbekend: zoek eerst op `reference` met `payments.search(...)` voor je opnieuw probeert.

## Een callback verifiëren

Geef de **ruwe** body-bytes door, niet een opnieuw geserialiseerde JSON, samen met de `Signature`-header en het pad van het verzoek.

```python
verifier = factory.callback_verifier()  # hergebruik: de JWKS-cache zit erin

try:
    callback = await verifier.verify_and_parse(request.headers["Signature"], raw_body, request.url.path)
except InvalidCallbackException:
    ...  # niet vertrouwen: antwoord met een foutstatus
else:
    handle(callback.payload.status, callback.request_id)  # request_id (jti) is uniek per bericht
```

Antwoord pas met `200` na verificatie en verwerking. Bancontact herhaalt callbacks met identieke inhoud, dus verwerk idempotent (zie ook BancontactPro.Net#9).

## Terugbetalingen en reconciliatie

```python
refunds = await factory.refunds(BancontactProduct.ON_DISPLAY)
refund = await refunds.create(payment_id, CreateRefundRequest(amount=500, currency="EUR"), idempotency_key="refund-order-42")

recon = await factory.reconciliation(BancontactProduct.ON_DISPLAY)
payouts = await recon.get_payouts()
```

Geef bij `refunds.create` altijd zelf een `idempotency_key` mee als je de aanvraag kunt herhalen. Hergebruik van dezelfde sleutel met andere parameters geeft een `RefundIdempotencyConflictException`.

## QR-links (On a Receipt, Top Up, Static QR)

```python
from bancontactpro import qr

payload = qr.build_fixed_amount_payment_url(BancontactEnvironment.PRODUCTION, ppid, amount_cents=1000, description="Kassabon")
image_url = qr.build_qr_code_image_url(BancontactEnvironment.PRODUCTION, payload)
```

Dit doet geen HTTP-aanroep. Gebruik voor payload en afbeelding dezelfde omgeving.

## Fouten

Een niet-succesvol antwoord geeft een `BancontactApiException` met `status_code`, `code` en, alleen bij de Payment-API, `trace_id` en `span_id` voor een supportticket. Een niet-geconfigureerd product of een ontbrekende signing-sleutel faalt bij het aanmaken van de client.

## Licentie

Apache License 2.0, zie [LICENSE](LICENSE) en [NOTICE](NOTICE). Copyright 2026 Axel Dewaele.

Dit is een onafhankelijk project, niet verbonden aan, goedgekeurd of ondersteund door Bancontact. "Bancontact" en "Bancontact Pro" zijn merken van hun eigenaar. De namen worden alleen gebruikt om aan te geven waarmee de bibliotheek werkt. De licentie geeft geen rechten op die merken en de rechthebbende van de code maakt er geen aanspraak op.

## Versies

SemVer in hetzelfde formaat als alle andere taalversies, bijvoorbeeld `0.2.0-preview.1`. De regels (major en minor gelijk over alle talen) staan in de [README van BancontactPro.SDK](https://github.com/yvebrecht/BancontactPro.SDK#versioning). PyPI toont deze versie als `0.2.0rc1` (PEP 440).

## Ontwikkelen

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python -m ruff check src tests
python -m mypy src
```
