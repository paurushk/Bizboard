"""PJ-TRADER-OWNER — a small B2B trader's normal day.

Buy from a supplier, sell to a GSTIN customer on credit, receive part payment,
run the ledger + a GST worksheet, and confirm the books stay consistent.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_trader_owner_normal_day():
    ns = seed_archetype("trader")
    company, oc = ns.company, ns.owner_client
    product = ns.products[1]  # a non-batch line
    supplier = ns.suppliers[0]
    customer = next(c for c in ns.customers if c.gstin)

    # 1. purchase 20 units
    pur = oc.post(
        "/api/v1/purchases/invoices/",
        {"supplier": supplier.id, "purchase_type": "GST",
         "items": [{"product": product.id, "quantity": "20", "unit_price": "50.00", "gst_rate": "18"}]},
        format="json",
    )
    assert pur.status_code == 201, pur.data
    assert oc.post(f"/api/v1/purchases/invoices/{pur.data['id']}/complete/").status_code == 200

    # 2. sell 8 on credit
    inv = oc.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "invoice_type": "GST",
         "items": [{"product": product.id, "quantity": "8", "unit_price": "100.00", "gst_rate": "18"}]},
        format="json",
    )
    assert inv.status_code == 201, inv.data
    done = oc.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/")
    assert done.status_code == 200, done.data
    grand = Decimal(str(done.data["grand_total"]))  # 800 + 144 = 944

    # 3. receive a part payment and allocate it
    rec = oc.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "500.00", "method": "BANK",
         "allocations": [{"sales_invoice": inv.data["id"], "amount": "500.00"}]},
        format="json",
    )
    assert rec.status_code in (200, 201), rec.data

    # 4. owner runs the customer ledger + GSTR-1 aid
    led = oc.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert led.status_code == 200, led.data
    assert oc.get(f"/api/v1/reports/gstr1/?period={done.data['invoice_date'][:7]}").status_code == 200

    # 5. stock moved: 20 in, 8 out -> 12
    from inventory.services import InventoryService

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("12.000")

    assert_all_invariants(company)
