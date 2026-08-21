"""Sprint 2: purchase DN headroom, PR books/cost, UTR uniqueness, dates, payroll JE."""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from inventory.models import MovementType, StockMovement
from payments.services import PaymentService
from payroll.models import Employee, PayRun
from payroll.services import complete_pay_run, pay_period_month_end
from purchases.models import PurchaseInvoice
from tests.conftest import add_stock, create_draft_purchase, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_bb_000656_purchase_dn_headroom(tenant_a):
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="PDN-1")
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    dn = tenant_a.client.post(
        "/api/v1/purchases/debit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": draft["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "150", "gst_rate": "0"}],
        },
        format="json",
    )
    assert dn.status_code == 201, dn.data
    fail = tenant_a.client.post(f"/api/v1/purchases/debit-notes/{dn.data['id']}/complete/")
    assert fail.status_code == 400

    ok = tenant_a.client.post(
        "/api/v1/purchases/debit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": draft["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "60", "gst_rate": "0"}],
        },
        format="json",
    )
    assert ok.status_code == 201, ok.data
    assert tenant_a.client.post(f"/api/v1/purchases/debit-notes/{ok.data['id']}/complete/").status_code == 200
    second = tenant_a.client.post(
        "/api/v1/purchases/debit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": draft["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "60", "gst_rate": "0"}],
        },
        format="json",
    )
    assert second.status_code == 201, second.data
    blocked = tenant_a.client.post(f"/api/v1/purchases/debit-notes/{second.data['id']}/complete/")
    assert blocked.status_code == 400


def test_bb_000665_supplier_alloc_allows_returned(tenant_a):
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="RET-AP")
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    invoice = PurchaseInvoice.objects.get(pk=draft["id"])
    pret = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "purchase_invoice": invoice.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        },
        format="json",
    )
    assert pret.status_code == 201, pret.data
    assert tenant_a.client.post(f"/api/v1/purchases/returns/{pret.data['id']}/complete/").status_code == 200
    invoice.refresh_from_db()
    if invoice.status != PurchaseInvoice.Status.RETURNED:
        invoice.status = PurchaseInvoice.Status.RETURNED
        invoice.save(update_fields=["status"])
    pay = PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("50"), mode="CASH", user=tenant_a.owner,
    )
    alloc = PaymentService.allocate_supplier_payment(
        payment=pay, purchase_invoice=invoice, amount=Decimal("50"), user=tenant_a.owner,
    )
    assert alloc.pk


def test_bb_000662_unlinked_pr_blocked_when_books_on(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="UL-PR")
    add_stock(tenant_a, product, "5", unit_cost="80")
    pret = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "90"}],
        },
        format="json",
    )
    assert pret.status_code == 201, pret.data
    done = tenant_a.client.post(f"/api/v1/purchases/returns/{pret.data['id']}/complete/")
    assert done.status_code == 400
    assert "linked purchase invoice" in str(done.data).lower() or "accounting" in str(done.data).lower()


def test_bb_000661_pr_cost_uses_purchase_move(tenant_a):
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="COST-PR")
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "2", "unit_price": "80", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    pret = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "purchase_invoice": draft["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "90"}],
        },
        format="json",
    )
    assert pret.status_code == 201, pret.data
    assert tenant_a.client.post(f"/api/v1/purchases/returns/{pret.data['id']}/complete/").status_code == 200
    move = StockMovement.objects.filter(
        company=tenant_a.company,
        movement_type=MovementType.PURCHASE_RETURN,
        reference_type="purchase_return",
        reference_id=str(pret.data["id"]),
    ).first()
    assert move is not None
    assert move.unit_cost == Decimal("80.00")


def test_bb_000645_utr_unique_all_time(tenant_a):
    supplier = make_supplier(tenant_a.company)
    customer = make_supplier(tenant_a.company, name="CustAsParty")
    from tests.conftest import make_customer

    cust = make_customer(tenant_a.company)
    PaymentService.create_receipt(
        company=tenant_a.company, customer=cust, amount=Decimal("10"), mode="BANK", utr="SAMEUTRALLTIME",
        user=tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError, match="UTR"):
        PaymentService.create_receipt(
            company=tenant_a.company, customer=cust, amount=Decimal("11"), mode="BANK", utr="sameutralltime",
            user=tenant_a.owner,
        )
    with pytest.raises(BusinessRuleError, match="UTR"):
        PaymentService.create_supplier_payment(
            company=tenant_a.company, supplier=supplier, amount=Decimal("12"), mode="BANK",
            utr="SAMEUTRALLTIME", user=tenant_a.owner,
        )


def test_bb_000666_money_dates_use_localdate():
    from payments.models import CustomerReceipt, SupplierPayment
    from purchases.models import PurchaseInvoice
    from sales.models import SalesCreditNote, SalesInvoice

    assert SalesInvoice._meta.get_field("invoice_date").default is timezone.localdate
    assert SalesCreditNote._meta.get_field("note_date").default is timezone.localdate
    assert PurchaseInvoice._meta.get_field("invoice_date").default is timezone.localdate
    assert CustomerReceipt._meta.get_field("receipt_date").default is timezone.localdate
    assert SupplierPayment._meta.get_field("payment_date").default is timezone.localdate
    from accounting.reports import _indian_fy_bounds

    start, end = _indian_fy_bounds(None)
    today = timezone.localdate()
    assert start <= today <= end


def test_bb_000683_payroll_je_uses_period_month_end(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    Employee.objects.create(
        company=tenant_a.company, name="Asha", code="ASH1", salary=Decimal("1000"),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    run = PayRun.objects.create(
        company=tenant_a.company, period="2026-01", status=PayRun.Status.DRAFT,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    complete_pay_run(run, tenant_a.owner)
    entry = JournalEntry.objects.get(company=tenant_a.company, source_type="PayRun", purpose="PAYROLL")
    assert entry.entry_date == date(2026, 1, 31)
    assert pay_period_month_end("2026-01") == date(2026, 1, 31)
    debit = entry.lines.get(account__code="5800")
    credit = entry.lines.get(account__code="1100")
    assert debit.debit == Decimal("1000.00")
    assert credit.credit == Decimal("1000.00")


def test_bb_000567_payroll_accrual_uses_wages_payable(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    Employee.objects.create(
        company=tenant_a.company, name="Bina", code="BIN1", salary=Decimal("2500"),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    run = PayRun.objects.create(
        company=tenant_a.company, period="2026-03", status=PayRun.Status.DRAFT,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    complete_pay_run(run, tenant_a.owner, pay_from_cash=False)
    entry = JournalEntry.objects.get(company=tenant_a.company, source_type="PayRun", purpose="PAYROLL")
    assert entry.lines.get(account__code="5800").debit == Decimal("2500.00")
    assert entry.lines.get(account__code="2150").credit == Decimal("2500.00")
    assert not entry.lines.filter(account__code="2100").exists()
