# BancontactPro.Python

Idiomatische Python-client voor de Bancontact Pro-API's (Payment, Refund, Reconciliation). Geen officieel Bancontact-project.

## Bronnen in volgorde van gezag

1. Bancontact Pro-documentatie en OpenAPI-specs: https://docs.bancontactpro.com/ (Payment v3.6.5, Refund v3.0.3, Reconciliation v3.0.1, productgidsen, callback-gids).
2. `../BancontactPro.Net` als vergelijking en bron van testvectoren. Dit is **geen directe port**. Bij conflict wint de documentatie.

Verzin geen Bancontact-gedrag. Elke gedragsbeslissing verwijst naar een documentatiepagina of spec-operatie (docstring of commentaar). Wat niet gedocumenteerd is, noteer je als open vraag in het issue. Afwijkingen met de .NET-code meld je in BancontactPro.Net met het label `spec-discrepancy`.

Werk met `claude --add-dir ../BancontactPro.Net` om de .NET-code te kunnen lezen (zijn CLAUDE.md wordt niet geladen).

## Ontwerp

- Async-first met `httpx.AsyncClient`; volledige type hints (`mypy --strict`); `pyproject.toml` (hatchling); `snake_case`; uitzonderingsklassen in `errors.py`.
- Distributie en import: `bancontactpro` (nog niet gereserveerd).
- Versie: major.minor loopt gelijk met alle taalversies (nu die van BancontactPro.Net, 0.2); patch en prerelease-deel zijn vrij per taal. Zelfde SemVer-formaat als BancontactPro.Net (`0.2.0-preview.1`), enige bron `src/bancontactpro/_version.py`; git-tags `v0.2.0-preview.1`. PyPI normaliseert dit naar PEP 440 (`0.2.0rc1`); dat is een eis van Python, geen afwijking.
- Python >= 3.11. Runtime-afhankelijkheden: alleen `cryptography` en `httpx`.
- Modellen zijn frozen dataclasses; `_json.py` mapt snake_case <-> camelCase. Ongezette optionele velden worden weggelaten, nooit als `null` verstuurd. Onbekende enumwaarden crashen niet (pseudo-lid in `_TolerantStrEnum`).
- Credentials worden per aanroep gelezen (`BancontactClientFactory`) en nooit gecachet; een client is gebonden aan één product.
- Payment-calls: alleen `Authorization: Bearer`. Refund en Reconciliation: ook `Signature`.
- `totalAmount` niet modelleren (verplicht maar niet gedefinieerd in de specs).
- Geen telemetrie en geen netwerkverkeer naar de aanbieder.

## Commando's

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[test]"   # Windows; .venv/bin/python elders
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m ruff check src tests && .venv/Scripts/python -m ruff format --check src tests
.venv/Scripts/python -m mypy src
```

Tests: pytest + pytest-asyncio (`asyncio_mode = "auto"`) + respx voor gemockte HTTP. Geen echte credentials of netwerk.

## Status en grenzen

- De repo staat onder Apache-2.0 (LICENSE en NOTICE, copyright Axel Dewaele). Het project is onafhankelijk en maakt geen aanspraak op de merken Bancontact of Bancontact Pro (zie NOTICE). **Er wordt niets gepubliceerd (PyPI, tags, releases) zonder uitdrukkelijk akkoord.**
- Open punten bij Bancontact: zie BancontactPro.Net#1, #2, #9 en #10 (`..` in de Signature, scheiding in de signing input, callback-retries, callback-headerclaims).
- Commit alleen op verzoek, met het Gmail-adres (zie geheugen), nooit met het werkadres.
