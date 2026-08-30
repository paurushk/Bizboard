"""Wave 3 books / GST integrity: auto CN on return, RCM GL, H9 period, ITC provisional."""

from decimal import Decimal
from datetime import date

import pytest

from accounting.models import AccountingPeriod, JournalEntry
from accounting.services import seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from ledgers.services import LedgerService
from purchases.models import PurchaseInvoice
from reporting.gst_periods import assert_period_allows_money_amend, soft_close_period
from reporting.gst_returns import build_gstr3b
from sales.models import NoteReason, SalesCreditNote, SalesInvoice, SalesReturn
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_sales_return_creates_cn_without_double_counting(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "10", "unit_price": "100"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    done = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert done.status_code == 200, done.data

    sales_return = SalesReturn.objects.get(pk=ret.data["id"])
    cn = SalesCreditNote.objects.get(
        sales_return=sales_return, status=SalesCreditNote.Status.COMPLETED
    )
    assert cn.reason == NoteReason.SALES_RETURN
    assert f"AUTO_RETURN:{sales_return.pk}" in cn.reason_detail

    invoice = SalesInvoice.objects.get(pk=inv["id"])
    # 1180 invoice − 236 CN = 944; returns must not also subtract.
    assert LedgerService.sales_invoice_outstanding(invoice) == Decimal("944.00")
    assert LedgerService.customer_outstanding(tenant_a.company, customer) == Decimal("944.00")


def test_rcm_purchase_posts_rcm_liability(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["accounting_enabled", "gstin", "state"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)

    product = make_product(tenant_a.company, sku="RCM-GL", hsn_code="9983")
    supplier = make_supplier(tenant_a.company, name="URP", state="Karnataka", gstin="")
    resp = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id,
            "purchase_type": "GST",
            "is_reverse_charge": True,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data

    inv = PurchaseInvoice.objects.get(pk=resp.data["id"])
    entry = JournalEntry.objects.get(
        company=tenant_a.company,
        source_type="PURCHASE_INVOICE",
        source_id=inv.id,
        purpose="COMPLETE",
        status=JournalEntry.Status.POSTED,
    )
    codes = set(entry.lines.values_list("account__code", flat=True))
    assert {"2240", "2250"}.issubset(codes)  # intra-state RCM CGST/SGST payable
    assert {"1310", "1320"}.issubset(codes)  # matching Input ITC
    rcm_credit = sum(
        line.credit
        for line in entry.lines.filter(account__code__in=("2240", "2250", "2260"))
    )
    assert rcm_credit == inv.rcm_cgst + inv.rcm_sgst + inv.rcm_igst
    assert rcm_credit == Decimal("180.00")


def test_h9_money_amend_blocked_on_soft_closed_period(tenant_a):
    soft_close_period(tenant_a.company, "2026-04", tenant_a.owner)
    with pytest.raises(BusinessRuleError, match="SOFT_CLOSED"):
        assert_period_allows_money_amend(tenant_a.company, date(2026, 4, 15))

    AccountingPeriod.objects.create(
        company=tenant_a.company,
        name="May soft",
        start_date="2026-05-01",
        end_date="2026-05-31",
        status=AccountingPeriod.Status.SOFT_CLOSED,
    )
    with pytest.raises(BusinessRuleError, match="SOFT_CLOSED"):
        assert_period_allows_money_amend(tenant_a.company, date(2026, 5, 10))


def test_gstr3b_itc_provisional(tenant_a):
    payload = build_gstr3b(tenant_a.company, "2026-07")
    assert payload["itc"]["provisional"] is True
    assert payload["itc"]["claimable"] is False
    assert "Provisional" in payload["itc"]["disclaimer"]
    assert payload["tax_payable_summary"]["itc_provisional"] is True
    # BB-000213: net_payable_hint must not subtract provisional ITC.
    assert "excludes" in payload["tax_payable_summary"]["note"]
    assert "ITC" in payload["tax_payable_summary"]["note"]
