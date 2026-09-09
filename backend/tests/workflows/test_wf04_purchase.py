"""WF-04 — New Purchase (no GRN), full chain.

Complete posts stock UP and AP UP atomically, ITC recorded. Then a supplier
payment allocates against the bill. Every downstream ledger must agree.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import create_draft_purchase, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_wf04_purchase_full_chain(tenant_a, assert_consistent):
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company, gst_rate="18", purchase_price="80")
    supplier = make_supplier(company, state="Karnataka")

    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "10", "unit_price": "80.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert done.status_code == 200, done.data
    d = done.data

    # 10 x 80 = 800 taxable; 18% -> 72 + 72; grand 944
    assert Decimal(str(d["taxable_total"])) == Decimal("800.00")
    assert Decimal(str(d["cgst_total"])) == Decimal("72.00")
    assert Decimal(str(d["sgst_total"])) == Decimal("72.00")
    assert Decimal(str(d["grand_total"])) == Decimal("944.00")

    # stock up by 10
    from inventory.services import InventoryService

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("10.000")

    # GL posted and balanced
    from accounting.models import JournalEntry

    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists(), "completing a purchase with accounting_enabled posted no GL"
    for e in entries:
        e.assert_balanced()

    # supplier payment against the bill
    pay = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {
            "supplier": supplier.id,
            "amount": "944.00",
            "method": "BANK",
            "allocations": [{"purchase_invoice": pur["id"], "amount": "944.00"}],
        },
        format="json",
    )
    assert pay.status_code in (200, 201), pay.data

    assert_consistent(company)
