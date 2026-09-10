"""PJ-RETAIL-* — a counter retail shop.

PJ-RETAIL-OWNER: proprietor runs a day of counter sales + a stock adjustment +
end-of-day reports.
PJ-RETAIL-SALES: sales staff does POS + receipts + lookup, and is blocked from
everything outside that.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def _stock_in(ns, product, qty="50"):
    from inventory.models import MovementType
    from inventory.services import InventoryService

    InventoryService.post_movement(
        company=ns.company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal(qty), unit_cost=Decimal("60"), user=ns.owner,
    )


def test_pj_retail_owner_normal_day():
    ns = seed_archetype("retail")
    for p in ns.products[:5]:
        _stock_in(ns, p)
    cust = ns.customers[0]
    oc = ns.owner_client

    # three counter sales
    for p in ns.products[:3]:
        checkout = oc.post(
            "/api/v1/sales/invoices/pos-checkout/",
            {
                "invoice": {
                    "customer": cust.id, "invoice_type": "RETAIL",
                    "items": [{"product": p.id, "quantity": "2", "unit_price": "100.00", "gst_rate": str(p.gst_rate)}],
                },
                "payment": {"mode": "CASH", "amount": "236.00", "tendered_amount": "300.00"},
            },
            format="json",
        )
        assert checkout.status_code in (200, 201), checkout.data

    # a shrinkage write-off (owner can)
    adj = oc.post(
        "/api/v1/inventory/adjustments/",
        {"product": ns.products[0].id, "quantity": "-1", "reason": "breakage"},
        format="json",
    )
    assert adj.status_code == 201, adj.data

    # end-of-day: owner sees reports
    assert oc.get("/api/v1/dashboard/").status_code == 200

    assert_all_invariants(ns.company)


def test_pj_retail_sales_staff_boundary(boundary):
    ns = seed_archetype("retail")
    for p in ns.products[:3]:
        _stock_in(ns, p)
    sc = ns.sales_client
    p = ns.products[0]
    cust = ns.customers[0]

    # --- allowed: the counter job ---
    boundary.allowed(sc, "get", f"/api/v1/products/?search={p.sku}")
    checkout = sc.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {"customer": cust.id, "invoice_type": "RETAIL",
                        "items": [{"product": p.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}]},
            "payment": {"mode": "CASH", "amount": "118.00", "tendered_amount": "120.00"},
        },
        format="json",
    )
    assert checkout.status_code in (200, 201), checkout.data
    inv_id = checkout.data["invoice"]["id"]

    # --- denied: everything outside the counter job ---
    boundary.denied(sc, "post", f"/api/v1/sales/invoices/{inv_id}/cancel/", data={"reason": "x"}, format="json")
    boundary.denied(sc, "post", "/api/v1/inventory/adjustments/",
                    data={"product": p.id, "quantity": "-1", "reason": "x"}, format="json")
    boundary.denied(sc, "get", "/api/v1/dashboard/")
    boundary.denied(sc, "get", "/api/v1/reports/sales-register/")

    assert_all_invariants(ns.company)
