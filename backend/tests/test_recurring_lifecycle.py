"""Recurring invoices hardening: auto-complete, run-now, lifecycle, cadences, cross-module guards."""

import itertools
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounting.models import AccountingPeriod
from accounts.models import CompanyUser
from contracts.models import Contract
from contracts.services import pause_ended_contract_schedules
from core.models import AuditEvent, Notification
from sales.models import RecurringInvoiceRun, RecurringInvoiceSchedule, SalesInvoice
from sales.recurring import (
    advance_next_run,
    generate_draft_for_schedule,
    generate_for_schedule,
    next_future_run,
    period_key_for,
    process_due_schedules,
)
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db

URL = "/api/v1/sales/recurring-schedules/"
_SKU = itertools.count(1)
Cadence = RecurringInvoiceSchedule.Cadence


def _schedule(tenant, *, cadence=Cadence.MONTHLY, next_run_at=None, stock=True, **extra):
    customer = extra.pop("customer", None) or make_customer(tenant.company)
    product = extra.pop("product", None) or make_product(tenant.company, sku=f"R-{next(_SKU)}")
    if stock:
        add_stock(tenant, product, "500")
    return RecurringInvoiceSchedule.objects.create(
        company=tenant.company,
        customer=customer,
        cadence=cadence,
        next_run_at=next_run_at or timezone.now() - timedelta(minutes=5),
        anchor_day=(next_run_at or timezone.now()).day,
        is_active=True,
        line_template={"items": [{"product": product.id, "quantity": "2", "unit_price": "100"}]},
        created_by=tenant.owner,
        updated_by=tenant.owner,
        **extra,
    )


def _sales_staff_client(tenant, *, can_create=True):
    cu = CompanyUser.objects.get(company=tenant.company, user=tenant.staff)
    cu.can_create_sales = can_create
    cu.save(update_fields=["can_create_sales"])
    return tenant.staff_client


# ---- auto-complete ---------------------------------------------------------------------------------


def test_auto_complete_success_does_not_report_a_false_failure(tenant_a):
    sched = _schedule(tenant_a, auto_complete=True)
    result = process_due_schedules(now=timezone.now())
    assert result["created"] == 1
    assert result["skipped_error"] == 0
    inv = SalesInvoice.objects.get(company=tenant_a.company)
    assert inv.status == SalesInvoice.Status.COMPLETED
    sched.refresh_from_db()
    assert sched.last_error == ""
    run = RecurringInvoiceRun.objects.get(schedule=sched)
    assert run.completion_error == ""
    assert sched.total_runs_count == 1
    note = Notification.objects.filter(company=tenant_a.company, channel=Notification.Channel.IN_APP).get()
    assert "completed automatically" in note.body


def test_auto_complete_gate_failure_keeps_draft_and_records_reason_on_the_run(tenant_a):
    customer = make_customer(tenant_a.company, credit_limit=Decimal("1.00"))
    sched = _schedule(tenant_a, auto_complete=True, customer=customer)
    result = process_due_schedules(now=timezone.now())
    assert result["created"] == 1 and result["skipped_error"] == 0
    inv = SalesInvoice.objects.get(company=tenant_a.company)
    assert inv.status == SalesInvoice.Status.DRAFT
    run = RecurringInvoiceRun.objects.get(schedule=sched)
    assert run.completion_error
    sched.refresh_from_db()
    assert sched.last_error == ""  # generation worked; only completion was held back
    note = Notification.objects.get(company=tenant_a.company, channel=Notification.Channel.IN_APP)
    assert note.subject == "Recurring documents need review"
    assert run.completion_error.split(":")[0][:10] in note.body


def test_catch_up_only_auto_completes_the_first_period(tenant_a):
    start = timezone.now() - timedelta(weeks=3, minutes=5)
    sched = _schedule(tenant_a, cadence=Cadence.WEEKLY, next_run_at=start, auto_complete=True)
    result = process_due_schedules(now=timezone.now())
    assert result["created"] >= 3
    runs = list(RecurringInvoiceRun.objects.filter(schedule=sched).order_by("id"))
    assert runs[0].completion_error == ""
    assert runs[0].invoice.status == SalesInvoice.Status.COMPLETED
    for later in runs[1:]:
        assert later.invoice.status == SalesInvoice.Status.DRAFT
        assert "catch-up" in later.completion_error
    # One digest for the whole catch-up, not one message per period.
    assert Notification.objects.filter(
        company=tenant_a.company, channel=Notification.Channel.IN_APP,
    ).count() == 1


def test_scheduled_run_is_audited_as_system_run(tenant_a):
    sched = _schedule(tenant_a)
    process_due_schedules(now=timezone.now())
    ev = AuditEvent.objects.get(company=tenant_a.company, action="RECURRING_RUN")
    assert ev.entity_id == str(sched.pk) and ev.user_id is None


# ---- locked period diagnostics -----------------------------------------------------------------------


def test_locked_period_records_reason_then_clears_on_success(tenant_a):
    sched = _schedule(tenant_a)
    on = sched.next_run_at.date()
    period = AccountingPeriod.objects.create(
        company=tenant_a.company, name="Locked",
        start_date=on.replace(day=1), end_date=on + timedelta(days=28),
        status=AccountingPeriod.Status.SOFT_CLOSED,
    )
    original = sched.next_run_at
    assert process_due_schedules(now=timezone.now())["skipped_locked"] == 1
    sched.refresh_from_db()
    assert "closed" in sched.last_error
    assert sched.next_run_at == original
    # Same reason again: no second notice.
    process_due_schedules(now=timezone.now())
    assert Notification.objects.filter(
        company=tenant_a.company, subject="Recurring schedule needs attention",
        channel=Notification.Channel.IN_APP,
    ).count() == 1
    period.delete()
    assert process_due_schedules(now=timezone.now())["created"] == 1
    sched.refresh_from_db()
    assert sched.last_error == ""


# ---- run now -----------------------------------------------------------------------------------------


def test_run_now_is_allowed_for_sales_users_audited_and_denied_without_permission(tenant_a):
    sched = _schedule(tenant_a, next_run_at=timezone.now() + timedelta(days=10))
    denied = tenant_a.staff_client.post(f"{URL}{sched.pk}/run-now/", {}, format="json")
    assert denied.status_code == 403
    client = _sales_staff_client(tenant_a)
    resp = client.post(f"{URL}{sched.pk}/run-now/", {}, format="json")
    assert resp.status_code == 200, resp.data
    body = resp.data
    assert body["already_existed"] is False
    assert SalesInvoice.objects.get(pk=body["invoice_id"]).status == SalesInvoice.Status.DRAFT
    assert AuditEvent.objects.filter(
        company=tenant_a.company, action="RUN_NOW", entity_id=str(sched.pk), user=tenant_a.staff,
    ).exists()
    again = client.post(f"{URL}{sched.pk}/run-now/", {}, format="json")
    assert again.status_code == 200
    assert again.data["already_existed"] is True
    assert RecurringInvoiceRun.objects.filter(schedule=sched).count() == 1


def test_run_now_refuses_inactive_customer_paused_schedule_and_reports_specific_reason(tenant_a):
    sched = _schedule(tenant_a)
    sched.customer.status = "BLOCKED"
    sched.customer.save(update_fields=["status"])
    resp = tenant_a.client.post(f"{URL}{sched.pk}/run-now/", {}, format="json")
    assert resp.status_code == 400 and "not active" in str(resp.data)
    sched.customer.status = "ACTIVE"
    sched.customer.save(update_fields=["status"])
    sched.is_active = False
    sched.save(update_fields=["is_active"])
    resp = tenant_a.client.post(f"{URL}{sched.pk}/run-now/", {}, format="json")
    assert resp.status_code == 400 and "paused" in str(resp.data)


def test_run_now_sales_order_stage_returns_order_id(tenant_a):
    sched = _schedule(tenant_a, stop_stage=RecurringInvoiceSchedule.StopStage.SALES_ORDER)
    resp = tenant_a.client.post(f"{URL}{sched.pk}/run-now/", {}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["invoice_id"] is None and resp.data["sales_order_id"]


def test_run_now_consumes_the_current_period_so_the_scheduled_run_is_a_duplicate(tenant_a):
    sched = _schedule(tenant_a, next_run_at=timezone.now() + timedelta(minutes=1))
    assert tenant_a.client.post(f"{URL}{sched.pk}/run-now/", {}, format="json").status_code == 200
    sched.next_run_at = timezone.now() - timedelta(minutes=1)
    sched.save(update_fields=["next_run_at"])
    result = process_due_schedules(now=timezone.now())
    assert result["created"] == 0 and result["skipped_duplicate"] >= 1


# ---- edit / resume -----------------------------------------------------------------------------------


def test_editing_next_run_recomputes_anchor_day_but_resaving_the_same_date_does_not(tenant_a):
    sched = _schedule(tenant_a, next_run_at=timezone.now() + timedelta(days=3))
    target = timezone.make_aware(timezone.datetime(2027, 3, 31, 9, 0))
    resp = tenant_a.client.patch(f"{URL}{sched.pk}/", {"nextRunAt": target.isoformat()}, format="json")
    assert resp.status_code == 200, resp.data
    sched.refresh_from_db()
    assert sched.anchor_day == 31
    # A month-end schedule whose stored date was clamped to the 28th keeps its anchor.
    sched.next_run_at = timezone.make_aware(timezone.datetime(2027, 2, 28, 9, 0))
    sched.anchor_day = 31
    sched.save(update_fields=["next_run_at", "anchor_day"])
    same = tenant_a.client.patch(
        f"{URL}{sched.pk}/", {"nextRunAt": sched.next_run_at.isoformat(), "notes": "x"}, format="json",
    )
    assert same.status_code == 200, same.data
    sched.refresh_from_db()
    assert sched.anchor_day == 31


def test_resume_needs_a_future_date_and_an_active_customer(tenant_a):
    sched = _schedule(tenant_a)
    sched.is_active = False
    sched.save(update_fields=["is_active"])
    bad = tenant_a.client.patch(f"{URL}{sched.pk}/", {"isActive": True}, format="json")
    assert bad.status_code == 400
    assert "nextRunAt" in str(bad.data) or "next_run_at" in str(bad.data)
    assert RecurringInvoiceSchedule.objects.get(pk=sched.pk).is_active is False

    later = (timezone.now() + timedelta(days=5)).isoformat()
    sched.customer.status = "INACTIVE"
    sched.customer.save(update_fields=["status"])
    inactive = tenant_a.client.patch(f"{URL}{sched.pk}/", {"isActive": True, "nextRunAt": later}, format="json")
    assert inactive.status_code == 400 and "not active" in str(inactive.data)

    sched.customer.status = "ACTIVE"
    sched.customer.save(update_fields=["status"])
    ok = tenant_a.client.patch(f"{URL}{sched.pk}/", {"isActive": True, "nextRunAt": later}, format="json")
    assert ok.status_code == 200, ok.data
    # No back-dated burst: nothing is due after the resume.
    assert process_due_schedules(now=timezone.now())["created"] == 0


def test_next_future_run_skips_missed_periods(tenant_a):
    sched = _schedule(tenant_a, cadence=Cadence.WEEKLY, next_run_at=timezone.now() - timedelta(weeks=5))
    assert next_future_run(sched) > timezone.now()


# ---- delete guard -------------------------------------------------------------------------------------


def test_delete_is_blocked_once_runs_exist(tenant_a):
    empty = _schedule(tenant_a, next_run_at=timezone.now() + timedelta(days=9), stock=False)
    assert tenant_a.client.delete(f"{URL}{empty.pk}/").status_code == 204
    used = _schedule(tenant_a, stock=False)
    generate_draft_for_schedule(used, user=tenant_a.owner)
    resp = tenant_a.client.delete(f"{URL}{used.pk}/")
    assert resp.status_code == 400 and "Pause" in str(resp.data)
    assert RecurringInvoiceSchedule.objects.filter(pk=used.pk).exists()


# ---- runs endpoint -----------------------------------------------------------------------------------


def test_runs_endpoint_lists_history_paginated_and_is_tenant_scoped(tenant_a, tenant_b):
    sched = _schedule(tenant_a, cadence=Cadence.WEEKLY, next_run_at=timezone.now() - timedelta(weeks=2, minutes=5))
    process_due_schedules(now=timezone.now())
    resp = tenant_a.client.get(f"{URL}{sched.pk}/runs/")
    assert resp.status_code == 200, resp.data
    rows = resp.data["results"]
    assert len(rows) == RecurringInvoiceRun.objects.filter(schedule=sched).count() >= 3
    assert rows[0]["document_type"] == "invoice" and rows[0]["status"] == "DRAFT"
    assert resp.data["count"] == len(rows)
    # Deleting a generated draft leaves the run as a record.
    run = RecurringInvoiceRun.objects.filter(schedule=sched).order_by("-id").first()
    SalesInvoice.objects.filter(pk=run.invoice_id).delete()
    after = tenant_a.client.get(f"{URL}{sched.pk}/runs/")
    assert any(r["status"] == "DELETED" and r["document_number"] is None for r in after.data["results"])
    assert tenant_b.client.get(f"{URL}{sched.pk}/runs/").status_code == 404


def test_schedule_serializer_exposes_last_error_and_term_fields(tenant_a):
    sched = _schedule(tenant_a, last_error="boom", end_date=date(2030, 1, 1), max_occurrences=3)
    body = tenant_a.client.get(f"{URL}{sched.pk}/").data
    assert body["last_error"] == "boom"
    assert body["end_date"] == "2030-01-01" and body["max_occurrences"] == 3
    assert body["total_runs_count"] == 0 and body["managed_by_contract"] is None
    assert body["customer_status"] == "ACTIVE"


# ---- cadences, period keys, term ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "cadence,expected",
    [
        (Cadence.MONTHLY, (2026, 2, 28)),
        (Cadence.QUARTERLY, (2026, 4, 30)),
        (Cadence.HALF_YEARLY, (2026, 7, 31)),
        (Cadence.ANNUALLY, (2027, 1, 31)),
    ],
)
def test_advance_next_run_for_each_cadence_keeps_the_anchor_day(cadence, expected):
    start = timezone.make_aware(timezone.datetime(2026, 1, 31, 10, 0))
    nxt = advance_next_run(start, cadence, 31)
    assert (nxt.year, nxt.month, nxt.day) == expected
    # From a clamped date the anchor still wins.
    again = advance_next_run(nxt, cadence, 31)
    assert again.day == min(31, __import__("calendar").monthrange(again.year, again.month)[1])


def test_year_end_rollover_for_quarterly():
    start = timezone.make_aware(timezone.datetime(2026, 11, 15, 10, 0))
    nxt = advance_next_run(start, Cadence.QUARTERLY, 15)
    assert (nxt.year, nxt.month, nxt.day) == (2027, 2, 15)


def test_period_keys_are_unique_per_period():
    d = date(2026, 5, 20)
    assert period_key_for(Cadence.MONTHLY, d) == "2026-05"
    assert period_key_for(Cadence.QUARTERLY, d) == "2026-Q2"
    assert period_key_for(Cadence.HALF_YEARLY, d) == "2026-H1"
    assert period_key_for(Cadence.HALF_YEARLY, date(2026, 9, 1)) == "2026-H2"
    assert period_key_for(Cadence.ANNUALLY, d) == "2026"
    assert period_key_for(Cadence.WEEKLY, d).startswith("2026-W")


def test_annual_schedule_manual_run_in_another_month_does_not_double_bill(tenant_a):
    sched = _schedule(tenant_a, cadence=Cadence.ANNUALLY, next_run_at=timezone.now() + timedelta(days=200))
    first = generate_for_schedule(sched, run_date=date(2026, 1, 15), user=tenant_a.owner, manual=True)
    assert first.created
    second = generate_for_schedule(sched, run_date=date(2026, 8, 3), user=tenant_a.owner, manual=True)
    assert not second.created and second.reason == "duplicate"
    assert RecurringInvoiceRun.objects.filter(schedule=sched).count() == 1


def test_end_date_deactivates_and_blocks_generation(tenant_a):
    sched = _schedule(tenant_a, end_date=timezone.localdate() - timedelta(days=1))
    assert process_due_schedules(now=timezone.now())["created"] == 0
    sched.refresh_from_db()
    assert sched.is_active is False
    assert not SalesInvoice.objects.filter(company=tenant_a.company).exists()


def test_max_occurrences_counts_scheduled_and_manual_runs_then_stops(tenant_a):
    sched = _schedule(tenant_a, cadence=Cadence.WEEKLY, max_occurrences=2,
                      next_run_at=timezone.now() + timedelta(days=2))
    assert tenant_a.client.post(f"{URL}{sched.pk}/run-now/", {}, format="json").status_code == 200
    sched.refresh_from_db()
    assert sched.total_runs_count == 1 and sched.is_active
    r = generate_for_schedule(sched, run_date=timezone.localdate() + timedelta(days=14), user=tenant_a.owner)
    assert r.created
    sched.refresh_from_db()
    assert sched.total_runs_count == 2 and sched.is_active is False
    resp = tenant_a.client.post(f"{URL}{sched.pk}/run-now/", {}, format="json")
    assert resp.status_code == 400


def test_schedule_finishes_when_the_next_occurrence_is_past_end_date(tenant_a):
    sched = _schedule(
        tenant_a, cadence=Cadence.WEEKLY,
        next_run_at=timezone.now() - timedelta(minutes=5),
        end_date=timezone.localdate() + timedelta(days=3),
    )
    assert process_due_schedules(now=timezone.now())["created"] == 1
    sched.refresh_from_db()
    assert sched.is_active is False


def test_end_date_before_next_run_is_rejected_by_the_api(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company)
    when = timezone.now() + timedelta(days=10)
    resp = tenant_a.client.post(
        URL,
        {
            "customer": customer.id, "cadence": "QUARTERLY", "nextRunAt": when.isoformat(),
            "lineTemplate": {"items": [{"product": product.id, "quantity": 1}]},
            "endDate": (when - timedelta(days=2)).date().isoformat(),
        },
        format="json",
    )
    assert resp.status_code == 400
    ok = tenant_a.client.post(
        URL,
        {
            "customer": customer.id, "cadence": "QUARTERLY", "nextRunAt": when.isoformat(),
            "lineTemplate": {"items": [{"product": product.id, "quantity": 1}]},
            "maxOccurrences": 4,
        },
        format="json",
    )
    assert ok.status_code == 201, ok.data


# ---- contracts ----------------------------------------------------------------------------------------


def _contract_for(tenant, sched, *, ended=False):
    """Contract.save() derives EXPIRED from the end date, so an ended contract has a past one."""
    today = timezone.localdate()
    return Contract.objects.create(
        company=tenant.company, customer=sched.customer, contract_type=Contract.Type.AMC,
        start_date=today - timedelta(days=400),
        end_date=today - timedelta(days=5) if ended else today + timedelta(days=300),
        value=Decimal("1000"), recurring_schedule=sched,
    )


def test_contract_managed_schedule_cannot_be_rewritten_or_deleted_from_the_recurring_page(tenant_a):
    sched = _schedule(tenant_a, next_run_at=timezone.now() + timedelta(days=5), stock=False)
    _contract_for(tenant_a, sched)
    body = tenant_a.client.get(f"{URL}{sched.pk}/").data
    assert body["managed_by_contract"]["id"]
    edit = tenant_a.client.patch(f"{URL}{sched.pk}/", {"cadence": "WEEKLY"}, format="json")
    assert edit.status_code == 400 and "contract" in str(edit.data).lower()
    assert tenant_a.client.patch(f"{URL}{sched.pk}/", {"isActive": False}, format="json").status_code == 200
    delete = tenant_a.client.delete(f"{URL}{sched.pk}/")
    assert delete.status_code == 400 and "contract" in str(delete.data).lower()


def test_ended_contract_pauses_its_schedule_but_a_live_one_keeps_it_running(tenant_a):
    sched = _schedule(tenant_a, stock=False)
    contract = _contract_for(tenant_a, sched, ended=True)
    assert contract.status == Contract.Status.EXPIRED
    assert pause_ended_contract_schedules(company_id=tenant_a.company.pk) == 1
    sched.refresh_from_db()
    assert sched.is_active is False

    live = _schedule(tenant_a, stock=False)
    _contract_for(tenant_a, live, ended=True)
    _contract_for(tenant_a, live)
    assert pause_ended_contract_schedules(company_id=tenant_a.company.pk) == 0
    live.refresh_from_db()
    assert live.is_active is True
    assert contract.pk


# ---- backup / restore --------------------------------------------------------------------------------


def test_backup_rows_carry_the_new_schedule_and_run_fields(tenant_a):
    from accounts.tenant_backup import _optional_rows

    sched = _schedule(tenant_a, end_date=date(2031, 1, 1), max_occurrences=5)
    generate_draft_for_schedule(sched, user=tenant_a.owner)
    srow = _optional_rows(RecurringInvoiceSchedule, tenant_a.company)[0]
    rrow = _optional_rows(RecurringInvoiceRun, tenant_a.company)[0]
    assert srow["max_occurrences"] == 5 and srow["total_runs_count"] == 1
    assert str(srow["end_date"]) == "2031-01-01"
    assert "completion_error" in rrow and "is_manual" in rrow


def test_schedule_list_does_not_query_per_row(tenant_a, django_assert_max_num_queries):
    for _ in range(3):
        _schedule(tenant_a, stock=False)
    tenant_a.client.get(URL)  # warm any one-time lookups
    with django_assert_max_num_queries(25) as ctx:
        resp = tenant_a.client.get(URL)
    assert resp.status_code == 200 and len(resp.data["results"]) == 3
    per_row = len(ctx.captured_queries)
    for _ in range(4):
        _schedule(tenant_a, stock=False)
    with django_assert_max_num_queries(per_row + 2):
        assert len(tenant_a.client.get(URL).data["results"]) == 7
