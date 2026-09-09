"""WF-01 — New Invoice, GST intra-state, full chain.

draft -> complete -> stock down, CGST/SGST computed, (books on) GL balanced,
TB zero -> customer receipt -> allocation. Every downstream ledger must agree.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_wf01_sale_intrastate_full_chain(tenant_a, assert_consistent):
    company = tenant_a.company
    company.accounting_enabled = True  # exercise the D5 hard-gate GL path
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    # --- draft -> complete ---
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    d = done.data

    # --- money identity: 3 x 100 = 300 taxable; 18% -> 27 + 27; grand 354 ---
    assert Decimal(str(d["taxable_total"])) == Decimal("300.00")
    assert Decimal(str(d["cgst_total"])) == Decimal("27.00")
    assert Decimal(str(d["sgst_total"])) == Decimal("27.00")
    assert Decimal(str(d["igst_total"])) == Decimal("0.00")
    assert Decimal(str(d["grand_total"])) == Decimal("354.00")

    # --- stock: opening 20 -> 17 on hand ---
    from inventory.services import InventoryService

    on_hand = InventoryService.available_quantity(company=company, product=product)
    assert on_hand == Decimal("17.000"), on_hand

    # --- books: a GL entry exists for the invoice and it is balanced ---
    from accounting.models import JournalEntry

    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists(), "completing an invoice with accounting_enabled posted no GL"
    for e in entries:
        e.assert_balanced()

    # --- customer receipt for the full amount ---
    pay = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {
            "customer": customer.id,
            "amount": "354.00",
            "method": "CASH",
            "allocations": [{"invoice": inv["id"], "amount": "354.00"}],
        },
        format="json",
    )
    assert pay.status_code in (200, 201), pay.data

    # --- whole-chain consistency ---
    assert_consistent(company)
