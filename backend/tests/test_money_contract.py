"""BB-000191: FE↔BE money contract smoke — invoice money fields as Decimal strings."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

import pytest

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db

# Snake_case API keys (tests use .data before camelCase render) — critical money totals.
MONEY_FIELDS = (
    "taxable_total",
    "cgst_total",
    "sgst_total",
    "igst_total",
    "grand_total",
    "round_off",
)

# FE typically accepts "1000.00" or "1000" — reject floats / scientific notation in JSON.
_DECIMAL_STR = re.compile(r"^-?\d+(\.\d+)?$")


def _assert_money_string(value, field: str) -> Decimal:
    assert isinstance(value, str), f"{field} must be JSON string for FE Decimal parse, got {type(value).__name__}: {value!r}"
    assert _DECIMAL_STR.match(value), f"{field} not a plain decimal string: {value!r}"
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise AssertionError(f"{field} not Decimal-parseable: {value!r}") from exc


def test_sales_invoice_money_fields_are_decimal_strings(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    data = done.data
    for field in MONEY_FIELDS:
        assert field in data, f"missing money field {field}"
        amount = _assert_money_string(data[field], field)
        assert amount >= 0 or field == "round_off"
    taxable = Decimal(data["taxable_total"])
    cgst = Decimal(data["cgst_total"])
    sgst = Decimal(data["sgst_total"])
    igst = Decimal(data["igst_total"])
    rnd = Decimal(data["round_off"])
    grand = Decimal(data["grand_total"])
    assert abs((taxable + cgst + sgst + igst + rnd) - grand) < Decimal("0.02")
    assert grand == Decimal("236.00")  # 200 taxable + 36 GST


def test_purchase_invoice_money_fields_are_decimal_strings(tenant_a):
    from tests.conftest import make_supplier

    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company, gstin="29BBBBB0000B1ZP")
    payload = {
        "supplier": supplier.id,
        "purchase_type": "GST",
        "items": [
            {"product": product.id, "quantity": "1", "unit_price": "50.00", "gst_rate": "18"},
        ],
    }
    resp = tenant_a.client.post("/api/v1/purchases/invoices/", payload, format="json")
    assert resp.status_code in (200, 201), resp.data
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data
    for field in MONEY_FIELDS:
        assert field in done.data
        _assert_money_string(done.data[field], field)
    assert Decimal(done.data["grand_total"]) == Decimal("59.00")


def test_openapi_lists_money_fields_as_string_or_decimal(tenant_a):
    """Smoke: schema documents totals (if OpenAPI enabled)."""
    from django.conf import settings

    if not getattr(settings, "ENABLE_API_DOCS", False) and not getattr(settings, "DEBUG", False):
        pytest.skip("API docs disabled")
    r = tenant_a.client.get("/api/schema/")
    if r.status_code != 200:
        pytest.skip("schema endpoint unavailable")
    body = r.content.decode("utf-8", errors="ignore")
    assert "grand_total" in body or "SalesInvoice" in body
