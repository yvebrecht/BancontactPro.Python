---
paths:
  - "src/bancontactpro/models.py"
  - "src/bancontactpro/enums.py"
  - "src/bancontactpro/_json.py"
  - "src/bancontactpro/clients.py"
---

# Modellen en clients

- Velden volgen de specs letterlijk, ook waar die onderling verschillen: `CreatePaymentResponse.expires_at` tegenover `Payment.expire_at` is geen typfout.
- Optioneel is niet nullable: laat ongezette velden weg bij requests.
- Bedragen zijn gehele getallen in cents (1 - 999.999.999.999).
- Datums worden tolerant geparsed (met of zonder microseconden, `Z` of `+00:00`); requests sturen `yyyy-MM-ddTHH:mm:ss.fffZ`.
- Refundstatus kent geen `PROCESSING` (verwijderd in Refund API v3.0.2).
- Reconciliation: `start-date` en `end-date` altijd samen, hoogstens 30 dagen; `size` is vast 10000 in de spec.
- Een time-out bij `create` heeft een onbekende uitkomst: nooit blind opnieuw proberen (zoek eerst op `reference`).
