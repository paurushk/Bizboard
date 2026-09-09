"""A7+A8+A9 High regression tests (CR-016/030/031/034/037/061/064/083)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from core.idempotency import MONEY_IDEMPOTENCY_SCOPES
from ledgers.services import LedgerService
from payments.models import PaymentAllocation, SupplierPayment, SupplierPaymentStatus
from reporting.services import ReportService
from sales.models import SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    return tenant_a


def _lines_by_code(company, source_type, source_id, purpose="COMPLETE"):
    je = JournalEntry.objects.get(
        company=company,
        source_type=source_type,
        source_id=source_id,
        purpose=purpose,
        status=JournalEntry.Status.POSTED,
    )
    out = {}
    for line in je.lines.all():
        d, c = out.get(line.account.code, (Decimal("0"), Decimal("0")))
        out[line.account.code] = (d + line.debit, c + line.credit)
    return out


def test_cr030_purchase_note_complete_scopes_are_money():
    assert "purchase_credit_note_complete" in MONEY_IDEMPOTENCY_SCOPES
    assert "purchase_debit_note_complete" in MONEY_IDEMPOTENCY_SCOPES


def test_cr030_cr031_purchase_credit_note_idempotent_single_je(books):
    product = make_product(books.company, purchase_price="100", selling_price="120", gst_rate="0")
    supplier = make_supplier(books.company)
    pur = create_draft_purchase(
        books,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert books.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    cn = books.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    key = "pcn-complete-idem-1"
    first = books.client.post(
        f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert first.status_code == 200, first.data
    second = books.client.post(
        f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert second.status_code == 200, second.data
    assert second.data.get("id") == first.data.get("id") or (
        (second.data.get("data") or {}).get("id") == (first.data.get("data") or {}).get("id")
    )
    assert (
        JournalEntry.objects.filter(
            company=books.company,
            source_type="PURCHASE_CREDIT_NOTE",
            source_id=cn.data["id"],
            purpose="COMPLETE",
            status=JournalEntry.Status.POSTED,
        ).count()
        == 1
    )


def test_cr037_lapsed_subscription_blocks_purchase_credit_note_complete(tenant_a, settings):
    from billing.models import Plan, Subscription

    settings.MIDDLEWARE = [m for m in settings.MIDDLEWARE if "SubscriptionWriteGate" not in m]
    product = make_product(tenant_a.company, purchase_price="80", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    plan = Plan.objects.create(name="A7", slug="a7-lapsed", seat_limit=3, price_paise=0)
    Subscription.objects.create(
        company=tenant_a.company,
        plan=plan,
        status=Subscription.Status.PAST_DUE,
        current_period_end=timezone.now() - timedelta(days=1),
    )
    resp = tenant_a.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/")
    assert resp.status_code in (402, 403), resp.data


def test_cr016_sales_invoice_list_balance_nets_credit_note(tenant_a):
    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "400", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert (
        tenant_a.client.post(
            f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/",
            {"confirm_price_override": True},
            format="json",
        ).status_code
        == 200
    )

    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/")
    assert detail.status_code == 200
    detail_balance = Decimal(str(detail.data.get("balance") or detail.data.get("data", {}).get("balance") or 0))

    listed = tenant_a.client.get("/api/v1/sales/invoices/", {"status": "COMPLETED"})
    assert listed.status_code == 200
    rows = listed.data.get("results") or listed.data.get("data") or listed.data
    if isinstance(rows, dict):
        rows = rows.get("results") or []
    row = next(r for r in rows if r["id"] == inv["id"])
    list_balance = Decimal(str(row.get("balance") or 0))
    assert list_balance == detail_balance == Decimal("600.00")


def test_cr016_purchase_invoice_list_balance_nets_credit_note(tenant_a):
    product = make_product(tenant_a.company, purchase_price="1000", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "250", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert (
        tenant_a.client.post(
            f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/",
            {"confirm_price_override": True},
            format="json",
        ).status_code
        == 200
    )

    detail = tenant_a.client.get(f"/api/v1/purchases/invoices/{pur['id']}/")
    assert detail.status_code == 200
    detail_balance = Decimal(str(detail.data.get("balance") or detail.data.get("data", {}).get("balance") or 0))

    listed = tenant_a.client.get("/api/v1/purchases/invoices/", {"status": "COMPLETED"})
    assert listed.status_code == 200
    rows = listed.data.get("results") or listed.data.get("data") or listed.data
    if isinstance(rows, dict):
        rows = rows.get("results") or []
    row = next(r for r in rows if r["id"] == pur["id"])
    list_balance = Decimal(str(row.get("balance") or 0))
    assert list_balance == detail_balance == Decimal("750.00")


def test_cr061_aging_ignores_supplier_payment_on_sales_invoice(tenant_a):
    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "500", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    supplier = make_supplier(tenant_a.company)
    sp = SupplierPayment.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        amount=Decimal("500.00"),
        mode="CASH",
        number="SP-MIS-1",
        status=SupplierPaymentStatus.POSTED,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company,
        supplier_payment=sp,
        sales_invoice_id=inv["id"],
        amount=Decimal("500.00"),
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    assert LedgerService.sales_invoice_outstanding(invoice) == Decimal("500.00")
    aging = ReportService.receivables_aging(tenant_a.company)
    assert sum(aging.values(), Decimal("0")) == Decimal("500.00")


def test_cr064_dashboard_mtd_purchases_nets_notes(tenant_a):
    product = make_product(tenant_a.company, purchase_price="1000", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    before = ReportService.dashboard(tenant_a.company)["purchases_this_month"]["total"]
    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert (
        tenant_a.client.post(
            f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/",
            {"confirm_price_override": True},
            format="json",
        ).status_code
        == 200
    )
    after = ReportService.dashboard(tenant_a.company)["purchases_this_month"]["total"]
    assert Decimal(str(after)) == Decimal(str(before)) - Decimal("200.00")


def test_cr034_cancel_blocked_when_completed_credit_note_exists_sales(tenant_a):
    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert (
        tenant_a.client.post(
            f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/",
            {"confirm_price_override": True},
            format="json",
        ).status_code
        == 200
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/cancel/")
    assert resp.status_code == 400, resp.data
    assert "credit" in str(resp.data).lower() or "debit" in str(resp.data).lower()


def test_cr034_cr035_purchase_cancel_guards(tenant_a):
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    draft_ret = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        },
        format="json",
    )
    assert draft_ret.status_code == 201, draft_ret.data
    blocked_draft = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/cancel/")
    assert blocked_draft.status_code == 400, blocked_draft.data
    assert "return" in str(blocked_draft.data).lower()

    assert tenant_a.client.delete(f"/api/v1/purchases/returns/{draft_ret.data['id']}/").status_code in (200, 204)

    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert (
        tenant_a.client.post(
            f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/",
            {"confirm_price_override": True},
            format="json",
        ).status_code
        == 200
    )
    blocked_cn = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/cancel/")
    assert blocked_cn.status_code == 400, blocked_cn.data
    assert "credit" in str(blocked_cn.data).lower() or "debit" in str(blocked_cn.data).lower()


def test_cr083_purchase_credit_note_reverses_tds_payable_not_advance(books):
    supplier = make_supplier(books.company)
    product = make_product(books.company, purchase_price="1000", selling_price="1200", gst_rate="18")
    draft = create_draft_purchase(
        books,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    patch = books.client.patch(
        f"/api/v1/purchases/invoices/{draft['id']}/",
        {"tdsSection": "194C", "tdsRate": "1", "tdsAmount": "10.00"},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    assert books.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200

    cn = books.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": draft["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    done = books.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/")
    assert done.status_code == 200, done.data

    codes = _lines_by_code(books.company, "PURCHASE_CREDIT_NOTE", cn.data["id"])
    assert codes.get("2265", (Decimal("0"), Decimal("0")))[0] == Decimal("10.00")
    assert codes.get("2100", (Decimal("0"), Decimal("0")))[0] == Decimal("1170.00")
    assert "1250" not in codes or codes["1250"][0] == Decimal("0")
