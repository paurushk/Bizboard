"""Recurring invoices follow-ups: contract renewal, e-invoice hand-off, quota reserve, paging, origin, restore."""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from sales.models import RecurringInvoiceRun, RecurringInvoiceSchedule, SalesInvoice
from sales.recurring import (
    QUOTA_DEFER,
    auto_complete_budget,
    generate_draft_for_schedule,
    process_due_schedules,
)
from tests.conftest import create_draft_invoice, make_customer, make_product
from tests.test_recurring_lifecycle import URL, _contract_for, _schedule

pytestmark = pytest.mark.django_db


def _contracts_on(tenant):
    tenant.company.feature_flags = {"ENABLE_CONTRACTS": True}
    tenant.company.save(update_fields=["feature_flags"])


def test_cancelling_pauses_and_uncancelling_restarts_a_contract_schedule(tenant_a):
    _contracts_on(tenant_a)
    sched = _schedule(tenant_a, next_run_at=timezone.now() + timedelta(days=5), stock=False)
    contract = _contract_for(tenant_a, sched)
    url = f"/api/v1/contracts/{contract.pk}/"
    assert tenant_a.client.patch(url, {"status": "CANCELLED"}, format="json").status_code == 200
    sched.refresh_from_db()
    assert sched.is_active is False and sched.paused_reason == "CONTRACT_ENDED"
    assert tenant_a.client.patch(url, {"status": "ACTIVE"}, format="json").status_code == 200
    sched.refresh_from_db()
    assert sched.is_active is True and sched.paused_reason == ""
    assert sched.next_run_at > timezone.now()


def test_a_schedule_a_person_paused_is_not_restarted_by_a_contract_renewal(tenant_a):
    _contracts_on(tenant_a)
    sched = _schedule(tenant_a, next_run_at=timezone.now() + timedelta(days=5), stock=False)
    contract = _contract_for(tenant_a, sched)
    assert tenant_a.client.patch(f"{URL}{sched.pk}/", {"isActive": False}, format="json").status_code == 200
    url = f"/api/v1/contracts/{contract.pk}/"
    assert tenant_a.client.patch(url, {"status": "CANCELLED"}, format="json").status_code == 200
    assert tenant_a.client.patch(url, {"status": "ACTIVE"}, format="json").status_code == 200
    sched.refresh_from_db()
    assert sched.is_active is False and sched.paused_reason == ""


def test_a_company_with_contracts_switched_off_still_has_ended_contract_schedules_paused(tenant_a):
    from contracts.tasks import refresh_contract_statuses

    tenant_a.company.feature_flags = {"ENABLE_CONTRACTS": False}
    tenant_a.company.save(update_fields=["feature_flags"])
    sched = _schedule(tenant_a, stock=False)
    _contract_for(tenant_a, sched, ended=True)
    result = refresh_contract_statuses()
    assert result["schedules_paused"] >= 1
    sched.refresh_from_db()
    assert sched.is_active is False and sched.paused_reason == "CONTRACT_ENDED"


@pytest.mark.parametrize(
    "enabled,gstin,expected",
    [(True, "29BBBBB1111B1Z5", 1), (False, "29BBBBB1111B1Z5", 0), (True, "", 0)],
)
def test_completed_b2b_invoice_is_sent_to_the_einvoice_portal_only_when_it_applies(
    tenant_a, monkeypatch, django_capture_on_commit_callbacks, enabled, gstin, expected,
):
    import sales.einvoice_eway_actions as actions
    import sales.tasks as tasks

    delay = MagicMock()
    monkeypatch.setattr(tasks.submit_einvoice_async, "delay", delay)
    monkeypatch.setattr(actions, "_assert_sandbox_gsp_allowed", lambda company: None)
    tenant_a.company.einvoice_enabled = enabled
    tenant_a.company.save(update_fields=["einvoice_enabled"])
    customer = make_customer(tenant_a.company, gstin=gstin)
    product = make_product(tenant_a.company, sku="EINV-1", hsn_code="998313")
    _schedule(tenant_a, auto_complete=True, customer=customer, product=product)
    with django_capture_on_commit_callbacks(execute=True):
        assert process_due_schedules(now=timezone.now())["created"] == 1
    assert SalesInvoice.objects.get().status == SalesInvoice.Status.COMPLETED
    assert delay.call_count == expected


def test_the_beat_keeps_a_tenth_of_the_plan_quota_free_for_manual_billing(tenant_a, monkeypatch):
    import billing.quotas as quotas

    monkeypatch.setattr(quotas, "_plan_for", lambda company: SimpleNamespace(monthly_complete_limit=10))
    monkeypatch.setattr(quotas, "monthly_complete_count", lambda company: 8)
    assert auto_complete_budget(tenant_a.company) == 1  # 10 - 8 - a reserve of 1
    _schedule(tenant_a, auto_complete=True)
    _schedule(tenant_a, auto_complete=True)
    assert process_due_schedules(now=timezone.now())["created"] == 2
    runs = list(RecurringInvoiceRun.objects.select_related("invoice"))
    done = [r for r in runs if r.invoice.status == SalesInvoice.Status.COMPLETED]
    held = [r for r in runs if r.invoice.status == SalesInvoice.Status.DRAFT]
    assert len(done) == 1 and len(held) == 1
    assert held[0].completion_error == QUOTA_DEFER


def test_an_unlimited_plan_has_no_budget(tenant_a):
    assert auto_complete_budget(tenant_a.company) is None


def test_list_filters_by_active_and_pages(tenant_a):
    for _ in range(3):
        _schedule(tenant_a, stock=False)
    paused = _schedule(tenant_a, stock=False)
    paused.is_active = False
    paused.save(update_fields=["is_active"])
    assert tenant_a.client.get(URL, {"is_active": "true"}).data["count"] == 3
    off = tenant_a.client.get(URL, {"is_active": "false"}).data
    assert off["count"] == 1 and off["results"][0]["id"] == paused.pk
    page = tenant_a.client.get(URL, {"page_size": 2}).data
    assert page["count"] == 4 and len(page["results"]) == 2 and page["next"]


def test_a_generated_invoice_shows_its_recurring_origin_on_detail_only(tenant_a):
    sched = _schedule(tenant_a)
    process_due_schedules(now=timezone.now())
    inv = SalesInvoice.objects.get()
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{inv.pk}/").data
    assert detail["recurring_origin"]["schedule_id"] == sched.pk
    rows = tenant_a.client.get("/api/v1/sales/invoices/").data["results"]
    assert rows[0]["recurring_origin"] is None
    product = make_product(tenant_a.company, sku="HAND-1")
    hand = create_draft_invoice(
        tenant_a, sched.customer, [{"product": product.id, "quantity": "1", "unit_price": "10"}],
    )
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{hand['id']}/").data["recurring_origin"] is None


def test_run_history_shows_the_einvoice_state_of_a_completed_invoice(tenant_a):
    sched = _schedule(tenant_a, auto_complete=True)
    process_due_schedules(now=timezone.now())
    SalesInvoice.objects.filter(company=tenant_a.company).update(einvoice_status="FAILED")
    rows = tenant_a.client.get(f"{URL}{sched.pk}/runs/").data["results"]
    assert rows[0]["einvoice_status"] == "FAILED"


def test_restore_keeps_schedules_runs_and_their_order_and_challan_links(tenant_a):
    from accounts.tenant_backup import build_export_payload, restore_destroy_in_place

    inv_sched = _schedule(tenant_a, max_occurrences=5, end_date=date(2031, 1, 1))
    order_sched = _schedule(tenant_a, stop_stage=RecurringInvoiceSchedule.StopStage.SALES_ORDER, stock=False)
    challan_sched = _schedule(
        tenant_a, stop_stage=RecurringInvoiceSchedule.StopStage.DELIVERY_CHALLAN, stock=False,
    )
    for sched in (inv_sched, order_sched, challan_sched):
        generate_draft_for_schedule(sched, user=tenant_a.owner)
    payload = build_export_payload(tenant_a.company)

    restore_destroy_in_place(
        company=tenant_a.company, payload=payload, owner=tenant_a.owner, confirm_destroy_unbacked=True,
    )

    schedules = RecurringInvoiceSchedule.objects.filter(company=tenant_a.company)
    assert schedules.count() == 3
    invoice_one = schedules.get(stop_stage="INVOICE")
    assert invoice_one.max_occurrences == 5 and invoice_one.end_date == date(2031, 1, 1)
    assert invoice_one.total_runs_count == 1
    runs = {r.schedule.stop_stage: r for r in RecurringInvoiceRun.objects.filter(company=tenant_a.company)}
    assert runs["INVOICE"].invoice.company_id == tenant_a.company.pk
    assert runs["SALES_ORDER"].sales_order_id
    assert runs["DELIVERY_CHALLAN"].delivery_challan.company_id == tenant_a.company.pk
