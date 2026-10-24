import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from bancontactpro import BancontactCredentials, BancontactEnvironment, BancontactProduct, ProductCredentials, SigningKey


@pytest.fixture(scope="session")
def ec_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def ec_pem(ec_key):
    return ec_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()


@pytest.fixture
def credentials(ec_pem):
    return BancontactCredentials(
        environment=BancontactEnvironment.PREPROD,
        products={BancontactProduct.ON_DISPLAY: ProductCredentials("api-key", "ppid-1")},
        signing_key=SigningKey("my-kid", ec_pem),
    )


CALLBACK_BODY = json.dumps(
    {
        "paymentId": "5c18cbd1296e9a26d3278518",
        "currency": "EUR",
        "amount": 1000,
        "description": "Order #42",
        "createdAt": "2026-01-02T03:04:05.000Z",
        "expireAt": "2026-01-02T03:19:05.123456+00:00",
        "succeededAt": None,
        "status": "AUTHORIZED",
        "debtor": {"iban": "BE**********1234", "name": "Jane Doe"},
    }
).encode()
