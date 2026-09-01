from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounting.models import AccountingPeriod
from accounting.services import PostingService, seed_chart_of_accounts
from purchases.models import PurchaseInvoice
from sales.models import RecurringInvoiceRun, RecurringInvoiceSchedule, SalesInvoice
from django.db import transaction

from sales.recurring import generate_draft_for_schedule, process_due_schedules
from tests.conftest import add_stock, create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_recurring_creates_draft_skips_locked_and_duplicate(tenant_a):
    product = make_product(tenant_a.company, sku="REC-1")
    customer = make_customer(tenant_a.company)
    now = timezone.now() - timedelta(minutes=5)
    schedule = RecurringInvoiceSchedule.objects.create(
        company=tenant_a.company,
        customer=customer,
        cadence=RecurringInvoiceSchedule.Cadence.MONTHLY,
        next_run_at=now,
        is_active=True,
        line_template={"items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}]},
        created_by=tenant_a.owner,
    )
    created = process_due_schedules()["created"]
    assert created >= 1
    inv = SalesInvoice.objects.filter(company=tenant_a.company, customer=customer).latest("id")
    assert inv.status == SalesInvoice.Status.DRAFT
    with transaction.atomic():
        again = generate_draft_for_schedule(schedule, run_date=timezone.localdate(), user=tenant_a.owner)
    assert again is not None
    assert RecurringInvoiceRun.objects.filter(schedule=schedule).count() == 1

    AccountingPeriod.objects.create(
        company=tenant_a.company,
        name="Lock",
        start_date=timezone.localdate().replace(day=1),
        end_date=timezone.localdate() + timedelta(days=28),
        status=AccountingPeriod.Status.CLOSED,
    )
    RecurringInvoiceRun.objects.all().delete()
    SalesInvoice.objects.filter(pk=inv.pk).delete()
    schedule.next_run_at = timezone.now() - timedelta(minutes=1)
    schedule.save(update_fields=["next_run_at"])
    with transaction.atomic():
        skipped = generate_draft_for_schedule(schedule, run_date=timezone.localdate(), user=tenant_a.owner)
    assert skipped is None


def test_recurring_run_now_owner_api(tenant_a):
    product = make_product(tenant_a.company, sku="REC-2")
    customer = make_customer(tenant_a.company)
    schedule = RecurringInvoiceSchedule.objects.create(
        company=tenant_a.company,
        customer=customer,
        cadence=RecurringInvoiceSchedule.Cadence.MONTHLY,
        next_run_at=timezone.now(),
        is_active=True,
        line_template={"items": [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "18"}]},
    )
    resp = tenant_a.client.post(f"/api/v1/sales/recurring-schedules/{schedule.id}/run-now/")
    assert resp.status_code == 200, resp.data
    body = resp.data.get("data", resp.data) if isinstance(resp.data, dict) else resp.data
    inv = SalesInvoice.objects.get(pk=body.get("invoice_id") or body.get("invoiceId"))
    assert inv.status == "DRAFT"


def test_tds_purchase_gl_194c(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    supplier = make_supplier(tenant_a.company, gstin="29EEEEE0000E1ZY")
    product = make_product(tenant_a.company, sku="TDS-1", hsn_code="9983")
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{draft['id']}/",
        {"tds_section": "194C", "tds_rate": "1.000", "tds_amount": "10.00"},
        format="json",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200
    inv = PurchaseInvoice.objects.get(pk=draft["id"])
    tds_acct = PostingService._account(tenant_a.company, "2265")
    from django.db.models import Sum
    from accounting.models import JournalLine

    credit = JournalLine.objects.filter(
        entry__company=tenant_a.company,
        entry__source_type="PURCHASE_INVOICE",
        entry__source_id=inv.id,
        account=tds_acct,
    ).aggregate(c=Sum("credit"))["c"] or Decimal("0")
    assert credit == Decimal("10.00")


def test_tcs_sales_gl_206c(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    product = make_product(tenant_a.company, sku="TCS-1", hsn_code="1001")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, gstin="29FFFFF0000F1ZP")
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/sales/invoices/{draft['id']}/",
        {"tcs_section": "206C", "tcs_rate": "0.100", "tcs_amount": "1.00"},
        format="json",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    from django.db.models import Sum
    from accounting.models import JournalLine

    tcs_acct = PostingService._account(tenant_a.company, "2266")
    credit = JournalLine.objects.filter(
        entry__company=tenant_a.company,
        entry__source_type="SALES_INVOICE",
        entry__source_id=draft["id"],
        account=tcs_acct,
    ).aggregate(c=Sum("credit"))["c"] or Decimal("0")
    # Owner decision 2026-08-31: the explicit tcs_amount (1.00) overrides the
    # rate-computed figure (0.100% of 1180 consideration = 1.18).
    assert credit == Decimal("1.00")

    # The divergence is recorded on the COMPLETE audit event (trust layer).
    from core.models import StatutoryDocumentEvent

    ev = StatutoryDocumentEvent.objects.get(
        company=tenant_a.company,
        entity_type="sales_invoice",
        entity_id=draft["id"],
        event_type=StatutoryDocumentEvent.EventType.COMPLETE,
    )
    assert ev.payload["tcs_override"]["provided_amount"] == "1.00"
    assert ev.payload["tcs_override"]["calculated_rate_amount"] == "1.18"


def test_tds_worksheet_csv(tenant_a):
    period = timezone.localdate().strftime("%Y-%m")
    resp = tenant_a.client.get("/api/v1/reports/tds-worksheet/", {"period": period})
    assert resp.status_code == 200
