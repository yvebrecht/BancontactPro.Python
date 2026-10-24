"""Contract tests: the models, enums and operations must match the stored copies of Bancontact's OpenAPI specs.

The specs in ``tests/specs`` are the versions below. When Bancontact publishes a newer spec these tests fail on
purpose, with a readable list of differences. To refresh them, see ``tests/specs/README.md``.
"""

from __future__ import annotations

import dataclasses
import json
import typing
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

from bancontactpro import _json, models
from bancontactpro import enums as enum_module

SPECS = Path(__file__).parent / "specs"
VERSIONS = {"merchant-payment": "3.6.5", "refund-public": "3.0.3", "merchant-reconciliation": "3.0.1"}


def load(name: str) -> dict[str, Any]:
    return json.loads((SPECS / f"{name}.openapi.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def resolve(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Follows ``$ref`` and merges ``allOf`` into one schema with ``properties`` and ``required``."""
    if "$ref" in schema:
        node: Any = spec
        for part in schema["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        return resolve(spec, node)
    merged: dict[str, Any] = {"properties": {}, "required": []}
    for part in schema.get("allOf", []):
        sub = resolve(spec, part)
        merged["properties"].update(sub.get("properties", {}))
        merged["required"] += sub.get("required", [])
    merged["properties"].update(schema.get("properties", {}))
    merged["required"] += schema.get("required", [])
    if "enum" in schema:
        merged["enum"] = schema["enum"]
    return merged


# (spec, schema, model class, spec properties deliberately not modelled)
# totalAmount: listed as required but never defined (BancontactPro.Net#28). voucherEligibility: deprecated.
MODELS: list[tuple[str, str, type, set[str]]] = [
    ("merchant-payment", "payment_create_request", models.CreatePaymentRequest, {"voucherEligibility"}),
    ("merchant-payment", "static_qr_payment_create_request", models.CreateStaticQrPaymentRequest, {"voucherEligibility"}),
    ("merchant-payment", "payment_create_response", models.CreatePaymentResponse, set()),
    ("merchant-payment", "get_payment_response", models.Payment, {"totalAmount"}),
    ("merchant-payment", "merchant-callback", models.MerchantCallback, {"totalAmount"}),
    ("merchant-payment", "merchant-acknowledge", models.PaymentAcknowledgeRequest, set()),
    ("merchant-payment", "payment-search-query", models.PaymentSearchQuery, set()),
    ("merchant-payment", "PaymentSearchResponse", models.PaymentSearchResponse, set()),
    ("merchant-payment", "refund-response", models.DebtorRefundIban, set()),
    ("merchant-payment", "payment_creditor_response", models.PaymentCreditor, set()),
    ("merchant-payment", "links", models.PaymentLinks, set()),
    ("merchant-payment", "link", models.PaymentLink, set()),
    ("merchant-payment", "error", models.ErrorResponse, set()),
    ("refund-public", "CreateRefundRequest", models.CreateRefundRequest, set()),
    ("refund-public", "RefundCreationResponse", models.RefundCreationResponse, set()),
    ("refund-public", "RefundModel", models.RefundModel, set()),
    ("refund-public", "ErrorResponse", models.ErrorResponse, set()),
    ("merchant-reconciliation", "PayoutListItem", models.Payout, set()),
    ("merchant-reconciliation", "PayoutListResponse", models.PayoutListResponse, set()),
    ("merchant-reconciliation", "PaymentDetails", models.ReconciliationPaymentDetails, set()),
    ("merchant-reconciliation", "PayoutPaymentsResponse", models.PayoutPaymentsResponse, set()),
    ("merchant-reconciliation", "RefundDetails", models.ReconciliationRefundDetails, set()),
    ("merchant-reconciliation", "PayoutRefundsResponse", models.PayoutRefundsResponse, set()),
]

# Fields we model as optional although the spec requires them: the Payment API's error schema requires traceId and spanId, but
# the same class also serves the Refund and Reconciliation errors, which do not define them (see ErrorResponse's docstring).
OPTIONAL_HERE = {("error", "code"), ("error", "message"), ("error", "traceId"), ("error", "spanId"),
                 ("ErrorResponse", "code"), ("ErrorResponse", "message")}  # fmt: skip

# Modelled although this spec's schema lacks them: ErrorResponse is shared, and only the Payment API defines trace and span ids.
EXTRA_OK = {("refund-public", "ErrorResponse"): {"traceId", "spanId"}}

ENUMS: list[tuple[str, str, type[Enum]]] = [
    ("merchant-payment", "merchant-payment-status", enum_module.MerchantPaymentStatus),
    ("refund-public", "RefundStatus", enum_module.RefundStatus),
    ("merchant-reconciliation", "PayoutStatus", enum_module.PayoutStatus),
    ("merchant-reconciliation", "PaymentChannel", enum_module.PaymentChannel),
]

# Every operation we cover: (spec, method, path). A new or removed operation in a spec fails the test below.
OPERATIONS = {
    ("merchant-payment", "get", "/v3/payments/{id}"),
    ("merchant-payment", "delete", "/v3/payments/{id}"),
    ("merchant-payment", "post", "/v3/payments/search"),
    ("merchant-payment", "post", "/v3/payments"),
    ("merchant-payment", "post", "/v3/payments/pos"),
    ("merchant-payment", "post", "/v3/payments/{id}/acknowledge"),
    ("merchant-payment", "get", "/v3/payments/{id}/debtor/refundIban"),
    ("merchant-payment", "post", "/callback"),  # served by the merchant, verified by BancontactCallbackVerifier
    ("refund-public", "post", "/v3/payments/{payment-id}/refunds"),
    ("refund-public", "get", "/v3/payments/{payment-id}/refunds/{refund-id}"),
    ("merchant-reconciliation", "get", "/v3/reconciliation/payouts"),
    ("merchant-reconciliation", "get", "/v3/reconciliation/payments"),
    ("merchant-reconciliation", "get", "/v3/reconciliation/refunds"),
}


@pytest.mark.parametrize("name", VERSIONS)
def test_stored_spec_version(name: str) -> None:
    assert load(name)["info"]["version"] == VERSIONS[name]


@pytest.mark.parametrize(("spec_name", "schema", "cls", "ignored"), MODELS, ids=[f"{m[0]}:{m[1]}" for m in MODELS])
def test_model_matches_schema(spec_name: str, schema: str, cls: type, ignored: set[str]) -> None:
    spec = load(spec_name)
    resolved = resolve(spec, spec["components"]["schemas"][schema])
    spec_props = set(resolved["properties"]) - ignored
    spec_required = set(resolved["required"]) - ignored

    fields = {_json._wire_name(f.name.rstrip("_") if f.name != "from_" else "from"): f for f in dataclasses.fields(cls)}
    problems = []
    if missing := sorted(spec_props - set(fields)):
        problems.append(f"in the spec but not modelled: {missing}")
    if extra := sorted(set(fields) - spec_props - EXTRA_OK.get((spec_name, schema), set())):
        problems.append(f"modelled but not in the spec: {extra}")
    for wire, f in fields.items():
        if wire not in spec_props or (schema, wire) in OPTIONAL_HERE:
            continue
        is_required = f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        if is_required != (wire in spec_required):
            problems.append(f"{wire}: spec says required={wire in spec_required}, model says required={is_required}")
    assert not problems, f"{cls.__name__} vs {spec_name}:{schema}: " + "; ".join(problems)


@pytest.mark.parametrize(("spec_name", "schema", "enum"), ENUMS, ids=[e[1] for e in ENUMS])
def test_enum_matches_schema(spec_name: str, schema: str, enum: type[Enum]) -> None:
    spec = load(spec_name)
    assert [m.value for m in enum] == list(spec["components"]["schemas"][schema]["enum"]) or {m.value for m in enum} == set(
        spec["components"]["schemas"][schema]["enum"]
    )


@pytest.mark.parametrize("name", VERSIONS)
def test_operations_match_covered_set(name: str) -> None:
    spec = load(name)
    in_spec = {
        (name, method, path)
        for path, item in spec["paths"].items()
        for method in item
        if method in {"get", "post", "put", "delete", "patch"}
    }
    expected = {op for op in OPERATIONS if op[0] == name}
    assert in_spec == expected, f"new in spec: {sorted(in_spec - expected)}; gone from spec: {sorted(expected - in_spec)}"


def test_every_model_type_hint_resolves() -> None:
    # Guards the wire mapping itself: every annotation must be convertible by _json.
    for _, _, cls, _ in MODELS:
        typing.get_type_hints(cls)
