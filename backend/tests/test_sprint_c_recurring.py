"""BB-000669: recurring invoice schedules — draft only, skip locked/duplicate."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounting.models import AccountingPeriod
from reporting.models import GstReturnPeriod
from sales.models import RecurringInvoiceRun, RecurringInvoiceSchedule, SalesInvoice
from sales.recurring import generate_draft_for_schedule, process_due_schedules
from sales.tasks import generate_recurring_invoices_task
from tests.conftest import make_customer, make_product


pytestmark = pytest.mark.django_db


@pytest.fixture
def schedule(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company)
    now = timezone.now() - timedelta(minutes=5)
    return RecurringInvoiceSchedule.objects.create(
        company=tenant_a.company,
        customer=customer,
        cadence=RecurringInvoiceSchedule.Cadence.MONTHLY,
        next_run_at=now,
        is_active=True,
        line_template={"items": [{"product": product.id, "quantity": "2", "unit_price": "100"}]},
        notes="Monthly widget",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    ), product, customer


def test_beat_creates_draft_invoice(tenant_a, schedule):
    sched, _product, _customer = schedule
    result = generate_recurring_invoices_task()
    assert result["created"] == 1
    inv = SalesInvoice.objects.get(company=tenant_a.company)
    assert inv.status == SalesInvoice.Status.DRAFT
    assert inv.notes == "Monthly widget"
    assert inv.items.count() == 1
    run = RecurringInvoiceRun.objects.get(schedule=sched)
    assert run.invoice_id == inv.id
    assert run.period_key.startswith("20")


def test_skips_locked_accounting_period(tenant_a, schedule):
    sched, _product, _customer = schedule
    on = sched.next_run_at.date()
    AccountingPeriod.objects.create(
        company=tenant_a.company,
        name="Locked",
        start_date=on.replace(day=1),
        end_date=on + timedelta(days=28),
        status=AccountingPeriod.Status.SOFT_CLOSED,
    )
    result = process_due_schedules(now=timezone.now())
    assert result["created"] == 0
    assert result["skipped_locked"] == 1
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 0


def test_skips_locked_gst_period(tenant_a, schedule):
    sched, _product, _customer = schedule
    on = sched.next_run_at.date()
    GstReturnPeriod.objects.create(
        company=tenant_a.company,
        period=f"{on.year:04d}-{on.month:02d}",
        status=GstReturnPeriod.Status.CLOSED,
    )
    result = process_due_schedules(now=timezone.now())
    assert result["skipped_locked"] == 1
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 0


def test_skips_duplicate_period_key(tenant_a, schedule):
    sched, _product, _customer = schedule
    generate_draft_for_schedule(sched, run_date=sched.next_run_at.date(), user=tenant_a.owner)
    sched.refresh_from_db()
    # Force due again for same calendar month
    sched.next_run_at = timezone.now() - timedelta(minutes=1)
    sched.save(update_fields=["next_run_at"])
    result = process_due_schedules(now=timezone.now())
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1
    assert result["skipped_duplicate"] >= 1 or result["created"] == 0


def test_never_auto_completes(tenant_a, schedule):
    sched, _product, _customer = schedule
    generate_draft_for_schedule(sched, run_date=date(2026, 8, 1), user=tenant_a.owner)
    inv = SalesInvoice.objects.get(company=tenant_a.company)
    assert inv.status == SalesInvoice.Status.DRAFT
    assert inv.completed_at is None


def test_recurring_api_crud_and_run_now(tenant_a, schedule):
    sched, product, customer = schedule
    listed = tenant_a.client.get("/api/v1/sales/recurring-schedules/")
    assert listed.status_code == 200
    created = tenant_a.client.post(
        "/api/v1/sales/recurring-schedules/",
        {
            "customer": customer.id,
            "cadence": "WEEKLY",
            "nextRunAt": timezone.now().isoformat(),
            "isActive": True,
            "lineTemplate": {"items": [{"product": product.id, "quantity": 1}]},
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    pk = created.data.get("id") or created.data.get("data", {}).get("id")
    staff = tenant_a.staff_client.post(f"/api/v1/sales/recurring-schedules/{pk}/run-now/", {}, format="json")
    assert staff.status_code in (403, 400)
    run = tenant_a.client.post(f"/api/v1/sales/recurring-schedules/{pk}/run-now/", {}, format="json")
    assert run.status_code == 200, run.data
    body = run.data.get("data", run.data)
    inv = SalesInvoice.objects.get(pk=body["invoice_id"])
    assert inv.status == SalesInvoice.Status.DRAFT
