---
paths:
  - "src/bancontactpro/signing.py"
  - "src/bancontactpro/http.py"
  - "src/bancontactpro/jwks.py"
  - "src/bancontactpro/webhooks.py"
  - "tests/test_signing.py"
  - "tests/test_webhooks_jwks.py"
---

# Signing en callbackverificatie

- ES256 over P-256. De handtekening is altijd raw `r || s` (64 bytes, IEEE P1363), nooit DER. `cryptography` geeft DER terug: converteer met `decode_dss_signature`/`encode_dss_signature`.
- Formaat `base64url(header)..base64url(signature)` (twee punten, RFC 7797) volgens de callback-gids en de Payment-spec. Verificatie tolereert ook één punt. De signing input is `base64url(header) + "." + base64url(body)`; dit is nog te bevestigen (BancontactPro.Net#1, #2).
- Sign en verifieer de body-bytes exact zoals verstuurd of ontvangen, nooit een herserialisatie.
- Het `path`-claim is het pad van de request-URI zonder querystring, in de verzonden (percent-encoded) vorm.
- Een onbekend of ontbrekend `crit`-claim betekent afwijzen. De verifier geeft `None` terug, de callback-verifier gooit `InvalidCallbackException`.
- JWKS: herladen bij onbekende `kid` (eenmalig, gecoalesceerd), cache maximaal 12 uur, één cache per omgeving.
- Nooit een sleutel, API-key of licentiesleutel loggen of in `repr` tonen.
