"""Customer care + jobs & contracts, Phase 0: regression tests for the confirmed defects."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from complaints.models import Complaint
from contracts.models import Contract, ContractServiceEvent
from contracts.views import ContractViewSet
from masters.models import Product
from sales.models import RecurringInvoiceSchedule, SalesCreditNote, SalesInvoice

from .conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _flags(company, **extra):
    company.feature_flags = {
        "ENABLE_CONTRACTS": True,
        "ENABLE_COMPLAINTS": True,
        "ENABLE_WORKSHOP": True,
        "ENABLE_SUPPORT_TICKETS": True,
        **extra,
    }
    company.save(update_fields=["feature_flags"])


def _contract(tenant, customer, **extra):
    today = timezone.localdate()
    return Contract.objects.create(
        company=tenant.company,
        customer=customer,
        contract_type=Contract.Type.AMC,
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=200),
        value=Decimal("1000"),
        number="CON-T1",
        **extra,
    )


def _schedule(tenant, customer):
    return RecurringInvoiceSchedule.objects.create(
        company=tenant.company,
        customer=customer,
        next_run_at=timezone.now() + timedelta(days=30),
        line_template={"items": []},
    )


# CCJ-00e: the subscription write lock must survive the per-action permission override.
def test_contract_viewset_keeps_subscription_write_lock():
    from billing.permissions import SubscriptionWritesAllowed

    view = ContractViewSet()
    for action in ("create", "create_schedule"):
        view.action = action
        assert any(isinstance(p, SubscriptionWritesAllowed) for p in view.get_permissions()), action


def test_only_the_owner_may_create_a_billing_schedule(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    contract = _contract(tenant_a, customer)
    resp = tenant_a.staff_client.post(f"/api/v1/contracts/{contract.id}/create-schedule/")
    assert resp.status_code == 403


# CCJ-00a / CON-01a: deleting a contract must not leave its schedule billing for ever.
def test_deleting_a_contract_pauses_its_orphaned_schedule(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    schedule = _schedule(tenant_a, customer)
    contract = _contract(tenant_a, customer, recurring_schedule=schedule)
    resp = tenant_a.client.delete(f"/api/v1/contracts/{contract.id}/")
    assert resp.status_code == 204
    schedule.refresh_from_db()
    assert schedule.is_active is False
    assert schedule.paused_reason == RecurringInvoiceSchedule.PausedReason.CONTRACT_ENDED


def test_a_shared_schedule_keeps_running_when_one_contract_is_deleted(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    schedule = _schedule(tenant_a, customer)
    first = _contract(tenant_a, customer, recurring_schedule=schedule)
    Contract.objects.create(
        company=tenant_a.company, customer=customer, contract_type=Contract.Type.AMC,
        start_date=first.start_date, end_date=first.end_date, number="CON-T2", recurring_schedule=schedule,
    )
    assert tenant_a.client.delete(f"/api/v1/contracts/{first.id}/").status_code == 204
    schedule.refresh_from_db()
    assert schedule.is_active is True


def test_a_contract_with_service_history_cannot_be_deleted(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    contract = _contract(tenant_a, customer)
    ContractServiceEvent.objects.create(
        company=tenant_a.company, contract=contract, occurred_at=timezone.now(), notes="visit",
    )
    resp = tenant_a.client.delete(f"/api/v1/contracts/{contract.id}/")
    assert resp.status_code == 400
    assert Contract.objects.filter(pk=contract.pk).exists()


# JOB-01: warranty parts and goodwill labour are free.
def _job(tenant, customer):
    resp = tenant.client.post(
        "/api/v1/workshop/job-cards/", {"customer": customer.id, "complaint": "Noise"}, format="json",
    )
    assert resp.status_code == 201, resp.data
    return resp.data["id"]


def test_zero_priced_lines_are_accepted_and_negative_ones_are_not(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    labour = make_product(
        tenant_a.company, name="Labour", sku="LB-0", product_type=Product.ProductType.SERVICE,
    )
    job_id = _job(tenant_a, customer)
    url = f"/api/v1/workshop/job-cards/{job_id}/lines/"
    free = tenant_a.client.post(
        url, {"kind": "LABOUR", "product": labour.id, "quantity": "1", "unit_price": "0"}, format="json",
    )
    assert free.status_code == 200, free.data
    negative = tenant_a.client.post(
        url, {"kind": "LABOUR", "product": labour.id, "quantity": "1", "unit_price": "-1"}, format="json",
    )
    assert negative.status_code == 400


# CCJ-00b / JOB-02a: a line added after the draft invoice exists would be reserved but never billed.
def test_no_line_can_be_added_once_the_invoice_draft_exists(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    part = make_product(tenant_a.company, name="Spare", sku="SP-0", product_type=Product.ProductType.GOODS)
    add_stock(tenant_a, part, "10")
    job_id = _job(tenant_a, customer)
    url = f"/api/v1/workshop/job-cards/{job_id}/lines/"
    body = {"kind": "PART", "product": part.id, "quantity": "1", "unit_price": "100"}
    assert tenant_a.client.post(url, body, format="json").status_code == 200
    assert tenant_a.client.post(f"/api/v1/workshop/job-cards/{job_id}/convert/").status_code == 200
    late = tenant_a.client.post(url, body, format="json")
    assert late.status_code == 400
    assert "invoice" in str(late.data).lower()


# JOB-11a: a job whose invoice was cancelled can be cancelled.
def test_a_job_with_a_cancelled_invoice_can_be_cancelled(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    part = make_product(tenant_a.company, name="Spare", sku="SP-1", product_type=Product.ProductType.GOODS)
    add_stock(tenant_a, part, "10")
    job_id = _job(tenant_a, customer)
    tenant_a.client.post(
        f"/api/v1/workshop/job-cards/{job_id}/lines/",
        {"kind": "PART", "product": part.id, "quantity": "1", "unit_price": "100"},
        format="json",
    )
    converted = tenant_a.client.post(f"/api/v1/workshop/job-cards/{job_id}/convert/")
    SalesInvoice.objects.filter(pk=converted.data["sales_invoice"]).update(status=SalesInvoice.Status.CANCELLED)
    resp = tenant_a.client.post(f"/api/v1/workshop/job-cards/{job_id}/cancel/")
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "CANCELLED"
    assert resp.data["sales_invoice"] is None


# CCJ-00c: a cancelled remedy document must not wedge the complaint.
def _approved_complaint_with_note(tenant, note_status):
    customer = make_customer(tenant.company)
    invoice = SalesInvoice.objects.create(company=tenant.company, customer=customer)
    note = SalesCreditNote.objects.create(
        company=tenant.company, customer=customer, sales_invoice=invoice, status=note_status,
    )
    complaint = Complaint.objects.create(
        company=tenant.company, customer=customer, source_invoice=invoice, category="DAMAGED",
        description="Broken", status=Complaint.Status.APPROVED, sales_credit_note=note, number="RMA-T1",
    )
    return complaint, note


def test_a_complaint_with_a_cancelled_document_can_unlink_it_and_resolve(tenant_a):
    _flags(tenant_a.company)
    complaint, _note = _approved_complaint_with_note(tenant_a, SalesCreditNote.Status.CANCELLED)
    blocked = tenant_a.client.post(
        f"/api/v1/complaints/{complaint.id}/transition/", {"status": "RESOLVED"}, format="json",
    )
    assert blocked.status_code == 400
    unlinked = tenant_a.client.post(
        f"/api/v1/complaints/{complaint.id}/unlink-document/", {"document": "sales_credit_note"}, format="json",
    )
    assert unlinked.status_code == 200, unlinked.data
    assert unlinked.data["sales_credit_note"] is None


def test_only_a_cancelled_document_can_be_unlinked(tenant_a):
    _flags(tenant_a.company)
    complaint, _note = _approved_complaint_with_note(tenant_a, SalesCreditNote.Status.DRAFT)
    resp = tenant_a.client.post(
        f"/api/v1/complaints/{complaint.id}/unlink-document/", {"document": "sales_credit_note"}, format="json",
    )
    assert resp.status_code == 400
    complaint.refresh_from_db()
    assert complaint.sales_credit_note_id is not None
