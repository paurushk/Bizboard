"""Sprint 0 books: GST complete posts a balanced journal (BB-000599)."""

from decimal import Decimal

import pytest
from django.db.models import Sum

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_gst_invoice_complete_posts_balanced_journal(tenant_a):
    """BB-000599: line cgst/sgst/igst/cess must not false-trip the tax drift guard."""
    tenant_a.company.accounting_enabled = True
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["accounting_enabled", "gstin", "state"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)

    product = make_product(tenant_a.company, sku="S0-GST")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{
            "product": product.id,
            "quantity": "1",
            "unit_price": "100",
            "gst_rate": "18",
            "cess_rate": "1",
        }],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data

    entry = JournalEntry.objects.get(
        company=tenant_a.company,
        source_type="SALES_INVOICE",
        source_id=inv["id"],
        purpose="COMPLETE",
        status=JournalEntry.Status.POSTED,
    )
    totals = entry.lines.aggregate(debit=Sum("debit"), credit=Sum("credit"))
    assert totals["debit"] == totals["credit"]
    assert totals["debit"] == Decimal("119.00")
