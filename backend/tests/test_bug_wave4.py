"""Wave 4 GST and books regressions that are in place so far."""

from datetime import date
from decimal import Decimal

import pytest

from core.exceptions import BusinessRuleError
from purchases.models import PurchaseInvoice
from reporting.gstr2b import match_gstr2b_to_purchases
from reporting.models import Gstr2bIngest
from tests.conftest import make_supplier

pytestmark = pytest.mark.django_db


def test_bug_gst_007_matches_supplier_bill_number(tenant_a):
    supplier = make_supplier(tenant_a.company, gstin="29CCCCC0000C1Z5")
    bill = PurchaseInvoice.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        number="PI-INTERNAL-7",
        supplier_bill_number="SUP-BILL-7",
        status=PurchaseInvoice.Status.COMPLETED,
        invoice_date=date(2026, 8, 10),
        taxable_total=Decimal("100.00"),
        cgst_total=Decimal("9.00"),
        sgst_total=Decimal("9.00"),
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    Gstr2bIngest.objects.create(
        company=tenant_a.company,
        period="2026-08",
        supplier_gstin="29CCCCC0000C1Z5",
        invoice_number="SUP-BILL-7",
        invoice_date=date(2026, 8, 10),
        taxable_value=Decimal("100.00"),
        cgst=Decimal("9.00"),
        sgst=Decimal("9.00"),
        match_status=Gstr2bIngest.MatchStatus.UNMATCHED,
    )
    match_gstr2b_to_purchases(tenant_a.company, "2026-08")
    row = Gstr2bIngest.objects.get(company=tenant_a.company, invoice_number="SUP-BILL-7")
    assert row.purchase_invoice_id == bill.id
    assert row.match_status == Gstr2bIngest.MatchStatus.MATCHED


def test_bug_gst_005_ingest_document_is_unique():
    names = {c.name for c in Gstr2bIngest._meta.constraints}
    assert "uniq_gstr2b_ingest_doc" in names


def test_bug_gst_008_off_slab_rate_is_rejected():
    from imports.services import _normalize_gst_rate

    assert _normalize_gst_rate("18.2") == Decimal("18")
    with pytest.raises(BusinessRuleError, match="not an allowed slab"):
        _normalize_gst_rate("7")
