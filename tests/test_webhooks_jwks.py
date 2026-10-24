import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import ec

from bancontactpro import (
    BancontactCallbackVerifier,
    BancontactClientFactory,
    BancontactCredentials,
    BancontactEnvironment,
    InvalidCallbackException,
    MerchantPaymentStatus,
)
from bancontactpro.jwks import JwksClient
from bancontactpro.signing import BancontactSignatureVerifier, JoseHeader, sign, to_public_jwk_json

from .conftest import CALLBACK_BODY

JWKS_PREPROD = "https://jwks.preprod.bancontact.net/"
JWKS_PROD = "https://jwks.bancontact.net/"


def header(kid="bank-kid", path="/callback"):
    return JoseHeader(kid, "ppid", "payconiq", datetime(2026, 1, 2, tzinfo=UTC), "jti-xyz", path)


class FakeJwks:
    def __init__(self, key):
        self.key = key

    async def get_key(self, kid):
        return self.key if kid == "bank-kid" else None


def verifier(key):
    return BancontactCallbackVerifier(BancontactSignatureVerifier(FakeJwks(key)))


async def test_valid_callback_is_parsed(ec_key):
    sig = sign(header(), CALLBACK_BODY, ec_key)
    result = await verifier(ec_key.public_key()).verify_and_parse(sig, CALLBACK_BODY, "/callback")
    assert result.request_id == "jti-xyz"
    assert result.payload.status == MerchantPaymentStatus.AUTHORIZED
    assert result.payload.amount == 1000 and result.payload.debtor.name == "Jane Doe"
    assert result.payload.succeeded_at is None
    assert result.payload.expire_at.microsecond == 123456  # preprod sends microseconds and +00:00


async def test_wrong_key_tamper_and_wrong_path_are_rejected(ec_key):
    other = ec.generate_private_key(ec.SECP256R1())
    v = verifier(ec_key.public_key())
    with pytest.raises(InvalidCallbackException):
        await v.verify_and_parse(sign(header(), CALLBACK_BODY, other), CALLBACK_BODY, "/callback")
    good = sign(header(), CALLBACK_BODY, ec_key)
    with pytest.raises(InvalidCallbackException):
        await v.verify_and_parse(good, CALLBACK_BODY.replace(b"1000", b"9999"), "/callback")
    with pytest.raises(InvalidCallbackException):
        await v.verify_and_parse(good, CALLBACK_BODY, "/elsewhere")
    with pytest.raises(InvalidCallbackException):
        await v.verify_and_parse(sign(header("unknown"), CALLBACK_BODY, ec_key), CALLBACK_BODY, "/callback")


async def test_validly_signed_garbage_body_raises_invalid_callback(ec_key):
    for body in (b"not json", b"{}", b"[]"):
        with pytest.raises(InvalidCallbackException):
            await verifier(ec_key.public_key()).verify_and_parse(sign(header(), body, ec_key), body, "/callback")


def jwks_json(key, kid):
    return {"keys": [json.loads(to_public_jwk_json(key, kid)), {"kty": "RSA", "kid": "rsa"}, {"kty": "EC"}]}


@respx.mock
async def test_jwks_refreshes_on_unknown_kid_once_and_caches(ec_key):
    route = respx.get(JWKS_PREPROD).respond(200, json=jwks_json(ec_key, "bank-kid"))
    async with httpx.AsyncClient() as http:
        client = JwksClient(lambda: BancontactCredentials(), http)
        assert (await client.get_key("bank-kid")).public_numbers() == ec_key.public_key().public_numbers()
        await client.get_key("bank-kid")
        assert route.call_count == 1  # second hit comes from the cache
        assert await client.get_key("rotated") is None
        assert route.call_count == 2  # a miss triggers one refresh
        assert await client.get_key("rsa") is None  # non-EC keys are ignored


@respx.mock
async def test_concurrent_misses_are_coalesced(ec_key):
    route = respx.get(JWKS_PREPROD).respond(200, json=jwks_json(ec_key, "bank-kid"))
    async with httpx.AsyncClient() as http:
        client = JwksClient(lambda: BancontactCredentials(), http)
        keys = await asyncio.gather(*(client.get_key("bank-kid") for _ in range(10)))
    assert all(k is not None for k in keys) and route.call_count == 1


@respx.mock
async def test_keys_expire_after_max_age_and_environments_are_separate(ec_key):
    pre = respx.get(JWKS_PREPROD).respond(200, json=jwks_json(ec_key, "bank-kid"))
    prod = respx.get(JWKS_PROD).respond(200, json={"keys": []})
    now = [0.0]
    env = [BancontactEnvironment.PREPROD]
    async with httpx.AsyncClient() as http:
        client = JwksClient(lambda: BancontactCredentials(environment=env[0]), http, max_age_seconds=100, clock=lambda: now[0])
        await client.get_key("bank-kid")
        now[0] = 101
        await client.get_key("bank-kid")
        assert pre.call_count == 2  # stale cache is refreshed
        env[0] = BancontactEnvironment.PRODUCTION
        assert await client.get_key("bank-kid") is None  # preprod keys are never used for production
        assert prod.call_count == 1


@respx.mock
async def test_factory_callback_verifier_end_to_end(ec_key):
    respx.get(JWKS_PREPROD).respond(200, json=jwks_json(ec_key, "bank-kid"))
    async with httpx.AsyncClient() as http:
        factory = BancontactClientFactory(BancontactCredentials(), http)
        sig = sign(header(), CALLBACK_BODY, ec_key)
        result = await factory.callback_verifier().verify_and_parse(sig, CALLBACK_BODY, "/callback")
    assert result.payload.payment_id == "5c18cbd1296e9a26d3278518"
