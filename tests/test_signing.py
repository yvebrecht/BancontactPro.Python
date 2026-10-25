import base64
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from bancontactpro.signing import (
    BancontactSignatureVerifier,
    JoseHeader,
    b64url_decode,
    jwk_to_public_key,
    sign,
    to_public_jwk_json,
    verify,
)

NS = "https://payconiq.com/"
HEADER = JoseHeader("kid-1", "ppid-1", "Payconiq", datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC), "jti-1", "/callback")


class FakeJwks:
    def __init__(self, **keys):
        self.keys = keys

    async def get_key(self, kid):
        return self.keys.get(kid)


def test_signature_is_header_dot_dot_signature_with_raw_r_s(ec_key):
    jws = sign(HEADER, b'{"a":1}', ec_key)
    head, middle, sig = jws.split(".")
    assert middle == ""  # RFC 7797 detached form documented by Bancontact: empty payload segment
    assert len(b64url_decode(sig)) == 64  # raw r||s, never DER
    assert verify(jws, b'{"a":1}', ec_key.public_key())


def test_header_claims_and_exact_bytes(ec_key):
    jws = sign(HEADER, b"x", ec_key)
    raw = base64.urlsafe_b64decode(jws.split(".")[0] + "==")
    claims = json.loads(raw)
    assert claims["typ"] == "jose+json" and claims["alg"] == "ES256" and claims["kid"] == "kid-1"
    assert claims[NS + "iat"] == "2026-01-02T03:04:05.678Z"
    assert claims[NS + "path"] == "/callback"
    assert claims["crit"] == [NS + s for s in ("sub", "iss", "iat", "jti", "path")]
    assert b"https://payconiq.com/sub" in raw  # not escaped


def test_tampered_body_fails(ec_key):
    jws = sign(HEADER, b"original", ec_key)
    assert not verify(jws, b"tampered", ec_key.public_key())


def test_single_dot_form_is_tolerated_on_verify(ec_key):
    head, _, sig = sign(HEADER, b"b", ec_key).split(".")
    assert verify(f"{head}.{sig}", b"b", ec_key.public_key())


@pytest.mark.parametrize("bad", ["", "abc", "a.b.c.d", "a..b..c", "!!!..???"])
def test_malformed_never_raises(bad, ec_key):
    assert verify(bad, b"x", ec_key.public_key()) is False


async def test_verifier_returns_claims(ec_key):
    jws = sign(HEADER, b"body", ec_key)
    claims = await BancontactSignatureVerifier(FakeJwks(**{"kid-1": ec_key.public_key()})).verify(jws, b"body", "/callback")
    assert claims is not None and claims.request_id == "jti-1"
    assert claims.issued_at == datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)


async def test_verifier_rejects_wrong_path_unknown_kid_and_wrong_key(ec_key):
    jws = sign(HEADER, b"body", ec_key)
    ok = BancontactSignatureVerifier(FakeJwks(**{"kid-1": ec_key.public_key()}))
    assert await ok.verify(jws, b"body", "/other") is None
    assert await BancontactSignatureVerifier(FakeJwks()).verify(jws, b"body", "/callback") is None
    other = ec.generate_private_key(ec.SECP256R1()).public_key()
    assert await BancontactSignatureVerifier(FakeJwks(**{"kid-1": other})).verify(jws, b"body", "/callback") is None


@pytest.mark.parametrize(
    ("claim", "received", "expected"),
    [
        ("https://shop.example/callback", "/callback", True),
        ("http://shop.example/callback", "/callback", True),
        ("https://shop.example/other", "/callback", False),
        ("ftp://shop.example/callback", "/callback", False),
        ("/callback", "/callback", True),
    ],
)
async def test_path_claim_may_be_the_callback_url(ec_key, claim, received, expected):
    jws = sign(replace(HEADER, path=claim), b"body", ec_key)
    verifier = BancontactSignatureVerifier(FakeJwks(**{"kid-1": ec_key.public_key()}))
    assert (await verifier.verify(jws, b"body", received) is not None) is expected


async def test_real_preprod_callback_verifies():
    # Captured from Bancontact's preprod on 2026-10-24 and checked with the public key of https://jwks.preprod.bancontact.net/ :
    # header..signature, a path claim that is the callback URL, signing input header + "." + base64url(body).
    public_key = jwk_to_public_key(
        {
            "kty": "EC",
            "crv": "P-256",
            "x": "QXagknFz-0HTQGL-jISbuOdPFP4561SmbmHm2y14HEg",
            "y": "0XJYHdztagEf-qFj1_lnE1HAqp5LkMDskW4hbhnKiII",
        }
    )
    signature = "eyJjcml0IjpbImh0dHBzOi8vcGF5Y29uaXEuY29tL2lzcyIsImh0dHBzOi8vcGF5Y29uaXEuY29tL2lhdCIsImh0dHBzOi8vcGF5Y29uaXEuY29tL3N1YiIsImh0dHBzOi8vcGF5Y29uaXEuY29tL3BhdGgiLCJodHRwczovL3BheWNvbmlxLmNvbS9qdGkiXSwiaHR0cHM6Ly9wYXljb25pcS5jb20vaXNzIjoiUGF5Y29uaXEiLCJraWQiOiJjMzBmNDE0ZC04NTVmLTQ3OTEtOTc1ZC1mNmQ5ZjNkMjNlNDIiLCJodHRwczovL3BheWNvbmlxLmNvbS9pYXQiOiIyMDI2LTEwLTI0VDIyOjI1OjIzLjE4NVoiLCJ0eXAiOiJKT1NFK0pTT04iLCJodHRwczovL3BheWNvbmlxLmNvbS9zdWIiOiI3eGt5ZGpiYzluZ2dzeWtjZzVzaDBhYnMiLCJodHRwczovL3BheWNvbmlxLmNvbS9wYXRoIjoiaHR0cHM6Ly9iYW5jb250YWN0LXByZXByb2Qub3MtbGFuLmJlL2JhbmNvbnRhY3QvY2FsbGJhY2siLCJodHRwczovL3BheWNvbmlxLmNvbS9qdGkiOiI4MTM4OWVhNS1lZDRlLTQyZTMtODkwYy0xNjExMjkyZWNiOTYiLCJhbGciOiJFUzI1NiJ9..rqZVQYddn67bBOG7iej3jAYwMpT-6R3mI_Ar7npJwHfYLd8iGmKw62on21guVo9XGveBJBd8ApVGPTcZSr78Hg"
    body = b'{"paymentId":"tx668ldrz9fgg4ararakc62r","currency":"EUR","amount":100,"createdAt":"2026-10-24T22:08:10.040086Z","status":"SUCCEEDED","debtor":{"iban":"************7034","name":"Axel Dewaele"},"description":"sample payment","expireAt":"2026-10-24T22:10:10.040086Z","succeededAt":"2026-10-24T22:08:28.514776Z"}'
    claims = await BancontactSignatureVerifier(FakeJwks(**{"c30f414d-855f-4791-975d-f6d9f3d23e42": public_key})).verify(
        signature, body, "/bancontact/callback"
    )
    assert claims is not None
    assert claims.issuer == "Payconiq"
    assert claims.request_id == "81389ea5-ed4e-42e3-890c-1611292ecb96"


async def test_verifier_rejects_unrecognised_critical_extension(ec_key):
    jws = sign(HEADER, b"body", ec_key)
    head = json.loads(base64.urlsafe_b64decode(jws.split(".")[0] + "=="))
    head["crit"].append("https://example.com/extra")
    forged = base64.urlsafe_b64encode(json.dumps(head).encode()).rstrip(b"=").decode()
    verifier = BancontactSignatureVerifier(FakeJwks(**{"kid-1": ec_key.public_key()}))
    assert await verifier.verify(f"{forged}..{jws.split('.')[2]}", b"body", "/callback") is None


def test_jwk_round_trip_and_rejects_other_curves(ec_key):
    jwk = json.loads(to_public_jwk_json(ec_key, "k"))
    assert jwk["kty"] == "EC" and jwk["crv"] == "P-256" and jwk["kid"] == "k"
    assert jwk_to_public_key(jwk).public_numbers() == ec_key.public_key().public_numbers()
    assert jwk_to_public_key({**jwk, "crv": "P-384"}) is None
    with pytest.raises(ValueError):
        to_public_jwk_json(ec.generate_private_key(ec.SECP384R1()), "k")
