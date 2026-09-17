"""A11 — dedicated supplier payment + allocation chain.

WF-04 already pays a bill in one shot. This chain is the freeze-map A11 gate:
partial allocate → outstanding agrees across ledger/dashboard → remainder
settles AP to zero → GL stays balanced.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import create_draft_purchase, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_a11_supplier_payment_partial_then_full_allocation(tenant_a, assert_consistent):
    from accounting.models import JournalEntry
    from accounting.services import seed_chart_of_accounts
    from ledgers.services import LedgerService
    from purchases.models import PurchaseInvoice
    from reporting.services import ReportService

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company)

    supplier = make_supplier(company, state="Karnataka", gstin="29A11PAY0000A1Z5")
    product = make_product(company, gst_rate="18", purchase_price="80")
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "10", "unit_price": "80.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice = PurchaseInvoice.objects.get(pk=pur["id"])
    assert LedgerService.purchase_invoice_outstanding(invoice) == Decimal("944.00")

    partial = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {"supplier": supplier.id, "amount": "400.00", "mode": "BANK"},
        format="json",
    )
    assert partial.status_code == 201, partial.data
    alloc = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {
            "supplier_payment": partial.data["id"],
            "purchase_invoice": pur["id"],
            "amount": "400.00",
        },
        format="json",
    )
    assert alloc.status_code == 201, alloc.data
    invoice.refresh_from_db()
    assert LedgerService.purchase_invoice_outstanding(invoice) == Decimal("544.00")
    assert LedgerService.supplier_outstanding(company, supplier) == Decimal("544.00")
    dash = ReportService.dashboard(company)
    assert Decimal(str(dash["payables"])) == Decimal("544.00")

    rest = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {"supplier": supplier.id, "amount": "544.00", "mode": "BANK"},
        format="json",
    )
    assert rest.status_code == 201, rest.data
    alloc2 = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {
            "supplier_payment": rest.data["id"],
            "purchase_invoice": pur["id"],
            "amount": "544.00",
        },
        format="json",
    )
    assert alloc2.status_code == 201, alloc2.data
    invoice.refresh_from_db()
    assert LedgerService.purchase_invoice_outstanding(invoice) == Decimal("0.00")
    assert LedgerService.supplier_outstanding(company, supplier) == Decimal("0.00")
    dash = ReportService.dashboard(company)
    assert Decimal(str(dash["payables"])) == Decimal("0.00")

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)
