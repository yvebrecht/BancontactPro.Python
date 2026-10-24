import json
from datetime import date

import httpx
import pytest
import respx

from bancontactpro import (
    BancontactApiException,
    BancontactClientFactory,
    BancontactProduct,
    BancontactProductNotConfiguredException,
    BancontactSigningKeyNotConfiguredException,
    CreatePaymentRequest,
    CreateRefundRequest,
    MerchantPaymentStatus,
    PaymentSearchQuery,
    RefundIdempotencyConflictException,
    RefundStatus,
)
from bancontactpro.signing import b64url_decode, verify

BASE = "https://merchant.api.preprod.bancontact.net"
PID = "5c18cbd1296e9a26d3278518"
LINK = {"href": "https://x"}
LINKS = {"self": LINK, "deeplink": LINK, "qrcode": LINK, "checkout": LINK}
CREATED = {
    "paymentId": PID,
    "status": "PENDING",
    "createdAt": "2026-01-02T03:04:05.123456+00:00",
    "expiresAt": "2026-01-02T03:06:05.000Z",
    "amount": 1000,
    "currency": "EUR",
    "creditor": {"name": "Shop"},
    "_links": LINKS,
}
PRODUCT = BancontactProduct.ON_DISPLAY


@pytest.fixture
async def factory(credentials):
    async with httpx.AsyncClient() as http:
        yield BancontactClientFactory(credentials, http)


@respx.mock
async def test_create_payment_sends_bearer_only_and_omits_unset_fields(factory):
    route = respx.post(f"{BASE}/v3/payments").respond(201, json=CREATED)
    client = await factory.payments(PRODUCT)
    response = await client.create(CreatePaymentRequest(amount=1000, reference="ref"))

    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer api-key"
    assert "Signature" not in request.headers  # the Payment API is authenticated by the API key alone
    assert json.loads(request.content) == {"amount": 1000, "reference": "ref"}
    assert response.status == MerchantPaymentStatus.PENDING
    assert response.links.checkout.href == "https://x"
    assert response.expires_at.microsecond == 0


@respx.mock
async def test_get_cancel_and_path_escaping(factory):
    payment = {**CREATED, "expireAt": CREATED["expiresAt"], "debtor": {"iban": "BE**1234"}}
    del payment["expiresAt"]
    respx.get(f"{BASE}/v3/payments/{PID}").respond(200, json=payment)
    cancel = respx.delete(f"{BASE}/v3/payments/{PID}").respond(204)
    client = await factory.payments(PRODUCT)
    got = await client.get(PID)
    assert got.debtor.iban == "BE**1234" and got.succeeded_at is None
    await client.cancel(PID)
    assert cancel.called


@respx.mock
async def test_search_paging_and_body(factory):
    route = respx.post(f"{BASE}/v3/payments/search").respond(
        200, json={"size": 0, "totalPages": 0, "totalElements": 0, "number": 0, "details": []}
    )
    client = await factory.payments(PRODUCT)
    result = await client.search(PaymentSearchQuery(payment_statuses=[MerchantPaymentStatus.SUCCEEDED], reference="r"), page=1, size=50)
    assert str(route.calls.last.request.url).endswith("search?page=1&size=50")
    assert json.loads(route.calls.last.request.content) == {"paymentStatuses": ["SUCCEEDED"], "reference": "r"}
    assert result.details == []


@respx.mock
async def test_unknown_status_value_does_not_crash(factory):
    payment = {**CREATED, "status": "SOMETHING_NEW", "expireAt": "2026-01-02T03:06:05Z"}
    respx.get(f"{BASE}/v3/payments/{PID}").respond(200, json=payment)
    got = await (await factory.payments(PRODUCT)).get(PID)
    assert got.status == "SOMETHING_NEW"


@respx.mock
async def test_payment_error_carries_trace_and_span(factory):
    respx.get(f"{BASE}/v3/payments/{PID}").respond(
        404, json={"code": "PAYMENT_NOT_FOUND", "message": "nope", "traceId": "t1", "spanId": "s1"}
    )
    with pytest.raises(BancontactApiException) as ex:
        await (await factory.payments(PRODUCT)).get(PID)
    assert (ex.value.status_code, ex.value.code, ex.value.trace_id, ex.value.span_id) == (404, "PAYMENT_NOT_FOUND", "t1", "s1")


@respx.mock
async def test_non_json_error_falls_back_to_generic_exception(factory):
    respx.get(f"{BASE}/v3/payments/{PID}").respond(502, text="<html>Bad gateway</html>", headers={"WWW-Authenticate": "Bearer"})
    with pytest.raises(BancontactApiException) as ex:
        await (await factory.payments(PRODUCT)).get(PID)
    assert ex.value.code == "" and "502" in str(ex.value) and "Bearer" in str(ex.value)


@respx.mock
async def test_refund_is_signed_and_sends_idempotency_key(factory, ec_key):
    route = respx.post(f"{BASE}/v3/payments/{PID}/refunds").respond(
        201,
        json={
            "refundId": PID,
            "paymentId": PID,
            "status": "PENDING",
            "amount": 500,
            "currency": "EUR",
            "creationDate": "2026-01-02T03:04:05Z",
        },
    )
    client = await factory.refunds(PRODUCT)
    result = await client.create(PID, CreateRefundRequest(500, "EUR"), idempotency_key="key-1")
    request = route.calls.last.request
    assert request.headers["Idempotency-Key"] == "key-1"
    assert request.headers["Authorization"] == "Bearer api-key"
    assert verify(request.headers["Signature"], request.content, ec_key.public_key())
    claims = json.loads(b64url_decode(request.headers["Signature"].split(".")[0]))
    assert claims["https://payconiq.com/path"] == f"/v3/payments/{PID}/refunds"
    assert claims["https://payconiq.com/sub"] == "ppid-1" and claims["kid"] == "my-kid"
    assert result.status == RefundStatus.PENDING


@respx.mock
async def test_refund_conflict_becomes_dedicated_exception(factory):
    respx.post(f"{BASE}/v3/payments/{PID}/refunds").respond(422, json={"code": "REFUND_REQUEST_CONFLICT", "message": "conflict"})
    with pytest.raises(RefundIdempotencyConflictException) as ex:
        await (await factory.refunds(PRODUCT)).create(PID, CreateRefundRequest(500, "EUR"), "key-1")
    assert ex.value.idempotency_key == "key-1" and ex.value.trace_id is None


async def test_refund_rejects_overlong_idempotency_key(factory):
    with pytest.raises(ValueError):
        await (await factory.refunds(PRODUCT)).create(PID, CreateRefundRequest(1, "EUR"), "x" * 65)


@respx.mock
async def test_reconciliation_query_strings_and_signature_covers_path_without_query(factory, ec_key):
    route = respx.get(f"{BASE}/v3/reconciliation/payments").respond(
        200, json={"size": 0, "totalPages": 0, "totalElements": 0, "number": 0, "payments": []}
    )
    client = await factory.reconciliation(PRODUCT)
    await client.get_payments(payout_id=PID, page=0)
    request = route.calls.last.request
    assert request.url.query.decode() == f"payout-id={PID}&page=0"
    claims = json.loads(b64url_decode(request.headers["Signature"].split(".")[0]))
    assert claims["https://payconiq.com/path"] == "/v3/reconciliation/payments"
    assert verify(request.headers["Signature"], b"", ec_key.public_key())


@respx.mock
async def test_reconciliation_payouts_and_date_rules(factory):
    route = respx.get(f"{BASE}/v3/reconciliation/payouts").respond(
        200, json={"size": 0, "totalPages": 0, "totalElements": 0, "number": 0, "payouts": []}
    )
    client = await factory.reconciliation(PRODUCT)
    await client.get_payouts(on=date(2026, 1, 2))
    assert route.calls.last.request.url.query.decode() == "date=2026-01-02"
    with pytest.raises(ValueError):
        await client.get_payments(start_date=date(2026, 1, 1))
    with pytest.raises(ValueError):
        await client.get_refunds(start_date=date(2026, 1, 1), end_date=date(2026, 3, 1))


async def test_missing_product_or_signing_key_fail_at_client_creation(credentials):
    from dataclasses import replace

    async with httpx.AsyncClient() as http:
        with pytest.raises(BancontactProductNotConfiguredException):
            await BancontactClientFactory(credentials, http).payments(BancontactProduct.TOP_UP)
        no_key = replace(credentials, signing_key=None)
        with pytest.raises(BancontactSigningKeyNotConfiguredException):
            await BancontactClientFactory(no_key, http).refunds(PRODUCT)
        assert await BancontactClientFactory(no_key, http).is_configured(PRODUCT)


@respx.mock
async def test_credentials_are_read_per_call(credentials):
    from dataclasses import replace

    from bancontactpro import BancontactEnvironment

    current = [credentials]
    async with httpx.AsyncClient() as http:
        factory = BancontactClientFactory(lambda: current[0], http)
        respx.get("https://merchant.api.bancontact.net/v3/payments/" + PID).respond(
            200, json={**CREATED, "expireAt": "2026-01-02T03:06:05Z"}
        )
        current[0] = replace(credentials, environment=BancontactEnvironment.PRODUCTION)
        await (await factory.payments(PRODUCT)).get(PID)
