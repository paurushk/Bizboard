"""Tax calculation suite — intra/inter state GST split, discounts, rounding (E4.3)."""

from decimal import Decimal

import pytest

from tests.conftest import create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _line(product, qty="2", price="100", **kwargs):
    return {"product": product.id, "quantity": qty, "unit_price": price, **kwargs}


def test_intra_state_splits_cgst_sgst(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    customer = make_customer(tenant_a.company, state="Karnataka")  # same as company
    data = create_draft_invoice(tenant_a, customer, [_line(product)])
    assert Decimal(data["taxable_total"]) == Decimal("200.00")
    assert Decimal(data["cgst_total"]) == Decimal("18.00")
    assert Decimal(data["sgst_total"]) == Decimal("18.00")
    assert Decimal(data["igst_total"]) == Decimal("0.00")
    assert Decimal(data["grand_total"]) == Decimal("236.00")


def test_inter_state_uses_igst(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    customer = make_customer(tenant_a.company, state="Maharashtra")
    data = create_draft_invoice(tenant_a, customer, [_line(product)])
    assert Decimal(data["cgst_total"]) == Decimal("0.00")
    assert Decimal(data["sgst_total"]) == Decimal("0.00")
    assert Decimal(data["igst_total"]) == Decimal("36.00")
    assert Decimal(data["grand_total"]) == Decimal("236.00")


def test_non_gst_invoice_has_zero_tax(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    customer = make_customer(tenant_a.company)
    data = create_draft_invoice(tenant_a, customer, [_line(product)], invoice_type="NON_GST")
    assert Decimal(data["cgst_total"]) == Decimal("0.00")
    assert Decimal(data["igst_total"]) == Decimal("0.00")
    assert Decimal(data["grand_total"]) == Decimal("200.00")


def test_discount_and_rounding(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    customer = make_customer(tenant_a.company, state="Karnataka")
    data = create_draft_invoice(
        tenant_a, customer, [_line(product, discount_percent="10")]
    )
    # 200 gross − 10% = 180 taxable; 18% GST = 32.40 → 16.20 + 16.20
    assert Decimal(data["discount_total"]) == Decimal("20.00")
    assert Decimal(data["taxable_total"]) == Decimal("180.00")
    assert Decimal(data["cgst_total"]) == Decimal("16.20")
    assert Decimal(data["sgst_total"]) == Decimal("16.20")
    # raw 212.40 rounds to 212 → round_off −0.40
    assert Decimal(data["round_off"]) == Decimal("-0.40")
    assert Decimal(data["grand_total"]) == Decimal("212.00")


def test_gst_rate_snapshot_defaults_from_product(tenant_a):
    product = make_product(tenant_a.company, gst_rate="12")
    customer = make_customer(tenant_a.company)
    data = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    assert Decimal(data["items"][0]["gst_rate"]) == Decimal("12.00")


def test_multiple_lines_accumulate(tenant_a):
    p1 = make_product(tenant_a.company, sku="A1", gst_rate="5")
    p2 = make_product(tenant_a.company, sku="A2", gst_rate="28")
    customer = make_customer(tenant_a.company, state="Karnataka")
    data = create_draft_invoice(tenant_a, customer, [
        _line(p1, qty="1", price="100"),   # tax 5
        _line(p2, qty="1", price="100"),   # tax 28
    ])
    assert Decimal(data["taxable_total"]) == Decimal("200.00")
    assert Decimal(data["cgst_total"]) == Decimal("16.50")
    assert Decimal(data["sgst_total"]) == Decimal("16.50")
    assert Decimal(data["grand_total"]) == Decimal("233.00")


def test_purchase_tax_calculated_from_supplier_state(tenant_a):
    from tests.conftest import create_draft_purchase, make_supplier

    product = make_product(tenant_a.company, gst_rate="18")
    supplier = make_supplier(tenant_a.company, state="Maharashtra")
    data = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "10", "unit_price": "80"}
    ])
    assert Decimal(data["taxable_total"]) == Decimal("800.00")
    assert Decimal(data["igst_total"]) == Decimal("144.00")
    assert Decimal(data["grand_total"]) == Decimal("944.00")
