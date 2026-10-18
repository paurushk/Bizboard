"""Regression: GST on taxable additional charges must not trip the GL tax-drift guard.

Header cgst/sgst/igst totals include the freight/packing GST; line rows do not.
`post_sales_invoice` (and the purchase twin) must account for that, post the
freight tax to Output GST, and keep the journal balanced.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db.models import Sum

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from sales.models import SalesInvoice
from sales.services import SalesService
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _gl_total(entry, code, side):
    return (
        entry.lines.filter(account__code=code).aggregate(t=Sum(side))["t"] or Decimal("0")
    )


def test_sales_complete_with_taxable_freight_posts_output_gst_incl_freight(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    product = make_product(tenant_a.company, hsn_code="8517", gst_rate="18")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)  # same state as the company
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "1000", "gst_rate": "18"}],
        additional_charges="100",
        charges_hsn="9965",
        charges_gst_rate="18",
    )
    inv = SalesInvoice.objects.get(pk=draft["id"])
    SalesService.complete(inv, tenant_a.owner)  # previously: BusinessRuleError drift
    inv.refresh_from_db()

    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="SALES_INVOICE", source_id=inv.id, purpose="COMPLETE",
    )
    debit = entry.lines.aggregate(t=Sum("debit"))["t"]
    credit = entry.lines.aggregate(t=Sum("credit"))["t"]
    assert debit == credit

    # 2 x 1000 @18% = 360 line tax + 18 freight tax = 378 -> 189 CGST + 189 SGST.
    assert inv.cgst_total + inv.sgst_total == Decimal("378.00")
    assert _gl_total(entry, "2210", "credit") == inv.cgst_total == Decimal("189.00")
    assert _gl_total(entry, "2220", "credit") == inv.sgst_total == Decimal("189.00")
    # Freight tax must be Output GST, not absorbed into Round Off.
    assert _gl_total(entry, "5500", "credit") == 0
    assert _gl_total(entry, "4100", "credit") == Decimal("2100.00")  # goods + freight
    assert _gl_total(entry, "1200", "debit") == inv.grand_total
