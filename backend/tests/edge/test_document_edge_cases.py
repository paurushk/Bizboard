"""§H6 — business-logic edge cases the happy-path chains don't hit.

Each asserts the system stays *consistent* (invariant sweep clean) under an
unusual-but-valid input, or rejects an invalid one cleanly (4xx, never 500).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _complete(t, inv):
    return t.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")


def test_zero_value_invoice_completes_and_is_consistent(tenant_a):
    p = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, p, "5")
    c = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, c,
        [{"product": p.id, "quantity": "1", "unit_price": "0.00", "gst_rate": "0"}],
    )
    r = _complete(tenant_a, inv)
    assert r.status_code == 200, r.data
    assert Decimal(str(r.data["grand_total"])) == Decimal("0.00")
    assert_all_invariants(tenant_a.company)


def test_mixed_gst_rates_in_one_invoice(tenant_a):
    p5 = make_product(tenant_a.company, sku="P5", gst_rate="5")
    p18 = make_product(tenant_a.company, sku="P18", gst_rate="18")
    for p in (p5, p18):
        add_stock(tenant_a, p, "10")
    c = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a, c,
        [
            {"product": p5.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "5"},
            {"product": p18.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"},
        ],
    )
    r = _complete(tenant_a, inv)
    assert r.status_code == 200, r.data
    d = r.data
    # 200 @ 5% => 10; 100 @ 18% => 18; total tax 28, split 14 CGST + 14 SGST
    assert Decimal(str(d["taxable_total"])) == Decimal("300.00")
    assert Decimal(str(d["cgst_total"])) == Decimal("14.00")
    assert Decimal(str(d["sgst_total"])) == Decimal("14.00")
    assert_all_invariants(tenant_a.company)


def test_large_amount_near_precision_limit(tenant_a):
    p = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, p, "100")
    c = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a, c,
        [{"product": p.id, "quantity": "50", "unit_price": "999999.99", "gst_rate": "18"}],
    )
    r = _complete(tenant_a, inv)
    # either it completes with a correct total, or it rejects cleanly — never 500
    assert r.status_code in (200, 400), r.data
    if r.status_code == 200:
        d = r.data
        taxable = Decimal(str(d["taxable_total"]))
        assert taxable == Decimal("49999999.50")
        assert_all_invariants(tenant_a.company)


def test_service_item_posts_no_stock_movement(tenant_a):
    # Create through the API so apply_product_type_matrix runs (SERVICE => track_inventory False).
    resp = tenant_a.client.post(
        "/api/v1/products/",
        {"name": "Consulting", "sku": "SVC-1", "gst_rate": "18", "product_type": "SERVICE",
         "selling_price": "500", "purchase_price": "0"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    pid = resp.data["id"]
    c = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a, c,
        [{"product": pid, "quantity": "3", "unit_price": "500.00", "gst_rate": "18"}],
    )
    r = _complete(tenant_a, inv)
    assert r.status_code == 200, r.data
    from inventory.models import StockMovement

    assert not StockMovement.objects.filter(company=tenant_a.company, product_id=pid).exists()
    assert_all_invariants(tenant_a.company)


def test_backdated_invoice_stays_consistent(tenant_a):
    p = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, p, "10")
    c = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a, c,
        [{"product": p.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
    )
    # backdate if the API allows it; otherwise this still exercises completion
    tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/", {"invoice_date": "2020-04-01"}, format="json"
    )
    r = _complete(tenant_a, inv)
    assert r.status_code in (200, 400), r.data
    if r.status_code == 200:
        assert_all_invariants(tenant_a.company)
