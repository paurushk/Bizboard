"""Proofs for the LLM path-to-ten tickets L1 and L4–L12.

L3 lives in tests/workflows/test_wf_grn.py, after the bill completes.
"""

from __future__ import annotations

import ast
import threading
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from billing.services import ensure_register_trial
from complaints.models import Complaint
from contracts.models import Contract
from crm.models import Lead, Opportunity, ReferralReward
from crm.pipeline import capture_lead
from inventory.models import SerialNumber
from inventory.services import InventoryService
from ledgers.services import LedgerService
from masters.models import Customer, Product
from payments.models import CustomerPortalToken, PaymentAllocation
from payments.portal_views import CustomerPortalComplaintView
from sales.models import (
    DeliveryRoute,
    DeliveryRouteStop,
    RecurringInvoiceSchedule,
    SalesCreditNote,
    SalesInvoice,
    SalesOrder,
)
from tests.conftest import create_draft_invoice, make_customer, make_product
from workshop.models import JobCard, JobCardLine

pytestmark = pytest.mark.django_db


def _clear_flag_cache(company):
    if hasattr(company, "_feature_flags_cache"):
        del company._feature_flags_cache


def _grant(tenant, flag):
    call_command("grant_company_flag", email=tenant.owner.email, flag=flag, on=True)
    tenant.company.refresh_from_db()
    _clear_flag_cache(tenant.company)


def _crm(tenant):
    flags = dict(tenant.company.feature_flags or {})
    flags["ENABLE_CRM"] = True
    # CRM is a dark module: bare JSON no longer turns it on, the insurance pack grant does.
    flags["pack_grant"] = "insurance"
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])
    _clear_flag_cache(tenant.company)


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking")


def test_second_tally_commit_does_not_change_opening_quantity(tenant_a, tenant_b):
    raw = (
        b"entity_type,name,sku,hsn_code,gst_rate,purchase_price,selling_price,opening_qty\n"
        b"product,Open Prod,SKU-L1,8471,18,10,20,5\n"
    )
    ensure_register_trial(tenant_a.company)
    ensure_register_trial(tenant_b.company)
    tenant_a.company.feature_flags = {}
    tenant_b.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    tenant_b.company.save(update_fields=["feature_flags"])
    _clear_flag_cache(tenant_a.company)
    _clear_flag_cache(tenant_b.company)
    denied = tenant_b.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": SimpleUploadedFile("masters.csv", raw, content_type="text/csv")},
        format="multipart",
    )
    assert denied.status_code == 404

    _grant(tenant_a, "ENABLE_TALLY")
    uploaded = tenant_a.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": SimpleUploadedFile("masters.csv", raw, content_type="text/csv")},
        format="multipart",
    )
    assert uploaded.status_code == 201, uploaded.data
    run_id = uploaded.data["sync_run_id"]
    committed = tenant_a.client.post(
        "/api/v1/integrations/tally/commit/", {"sync_run_id": run_id}, format="json",
    )
    assert committed.status_code == 200, committed.data
    product = Product.objects.get(company=tenant_a.company, sku="SKU-L1")
    on_hand = InventoryService.available_quantity(company=tenant_a.company, product=product)
    assert on_hand == Decimal("5.000")
    again = tenant_a.client.post(
        "/api/v1/integrations/tally/commit/", {"sync_run_id": run_id}, format="json",
    )
    assert again.status_code >= 400
    assert InventoryService.available_quantity(company=tenant_a.company, product=product) == on_hand
    still = tenant_b.client.post(
        "/api/v1/integrations/tally/commit/", {"sync_run_id": run_id}, format="json",
    )
    assert still.status_code == 404


def test_open_invoice_row_uses_sales_invoice_outstanding(tenant_a, tenant_b):
    customer = make_customer(tenant_a.company, state="Karnataka")
    product = make_product(tenant_a.company, sku="COLL-1", gst_rate="0", product_type=Product.ProductType.SERVICE)
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
    )
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert completed.status_code == 200, completed.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    invoice.due_date = timezone.localdate() - timedelta(days=3)
    invoice.save(update_fields=["due_date"])
    receipt = tenant_a.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": "40.00", "mode": "CASH",
    }, format="json")
    assert receipt.status_code == 201, receipt.data
    allocated = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt.data["id"], "sales_invoice": invoice.id, "amount": "40.00",
    }, format="json")
    assert allocated.status_code == 201, allocated.data

    other = make_customer(tenant_b.company, state="Karnataka")
    other_product = make_product(tenant_b.company, sku="COLL-B", gst_rate="0", product_type=Product.ProductType.SERVICE)
    other_draft = create_draft_invoice(
        tenant_b, other,
        [{"product": other_product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
    )
    assert tenant_b.client.post(f"/api/v1/sales/invoices/{other_draft['id']}/complete/").status_code == 200

    rows = tenant_a.client.get("/api/v1/insights/collections-open-invoices/")
    assert rows.status_code == 200, rows.data
    match = [row for row in rows.data["rows"] if row["invoice_id"] == invoice.id]
    assert len(match) == 1
    invoice.refresh_from_db()
    assert Decimal(match[0]["outstanding"]) == LedgerService.sales_invoice_outstanding(invoice)
    assert Decimal(match[0]["amount_received"]) == Decimal("40.00")
    assert match[0]["days_overdue"] >= 1
    assert Decimal(match[0]["customer_outstanding"]) == LedgerService.customer_outstanding(tenant_a.company, customer)
    assert all(row["invoice_id"] != other_draft["id"] for row in rows.data["rows"])


def test_credit_note_after_a_partial_receipt(tenant_a):
    customer = make_customer(tenant_a.company, state="Karnataka")
    product = make_product(tenant_a.company, sku="CN-1", gst_rate="0", product_type=Product.ProductType.SERVICE)
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    receipt = tenant_a.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": "40.00", "mode": "CASH",
    }, format="json")
    assert receipt.status_code == 201, receipt.data
    allocated = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt.data["id"], "sales_invoice": invoice.id, "amount": "40.00",
    }, format="json")
    assert allocated.status_code == 201, allocated.data
    note = tenant_a.client.post("/api/v1/sales/credit-notes/", {
        "customer": customer.id,
        "sales_invoice": invoice.id,
        "items": [{"product": product.id, "quantity": "0.600", "unit_price": "100", "gst_rate": "0"}],
    }, format="json")
    assert note.status_code == 201, note.data
    completed = tenant_a.client.post(
        f"/api/v1/sales/credit-notes/{note.data['id']}/complete/",
        {"confirm_paid_invoice": True},
        format="json",
    )
    assert completed.status_code == 200, completed.data
    from payments.models import CustomerReceipt

    assert CustomerReceipt.objects.filter(company=tenant_a.company, customer=customer).count() == 1
    assert PaymentAllocation.objects.filter(sales_invoice=invoice, reversed_at__isnull=True).count() == 1
    assert SalesCreditNote.objects.filter(company=tenant_a.company, sales_invoice=invoice).count() == 1
    invoice.refresh_from_db()
    assert LedgerService.sales_invoice_outstanding(invoice) == Decimal("0.00")


def test_won_lead_creates_one_draft_invoice(tenant_a, tenant_b):
    _crm(tenant_a)
    product = make_product(tenant_a.company, sku="LEAD-INV", gst_rate="0")
    created = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Won Lead", "phone": "9000001111", "state": "Karnataka"},
        format="json",
    )
    assert created.status_code == 201, created.data
    converted = tenant_a.client.post(
        f"/api/v1/crm/leads/{created.data['id']}/convert/",
        {"won": True, "amount": "100"},
        format="json",
    )
    assert converted.status_code == 200, converted.data
    opportunity_id = converted.data["opportunity"]["id"]
    customer_id = converted.data["opportunity"]["customer"]
    payload = {"items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}]}
    first = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{opportunity_id}/draft-invoice/",
        payload, format="json", HTTP_IDEMPOTENCY_KEY="lead-draft-1",
    )
    assert first.status_code == 201, first.data
    again_convert = tenant_a.client.post(
        f"/api/v1/crm/leads/{created.data['id']}/convert/",
        {"won": True}, format="json",
    )
    assert again_convert.status_code == 200
    second = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{opportunity_id}/draft-invoice/",
        payload, format="json", HTTP_IDEMPOTENCY_KEY="lead-draft-1",
    )
    assert second.status_code == 201, second.data
    assert second.data["id"] == first.data["id"]
    assert second.data["customer"] == customer_id
    assert Customer.objects.filter(company=tenant_a.company).count() == 1
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1
    lost = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Lost Lead", "phone": "9000001112", "state": "Karnataka"},
        format="json",
    )
    Lead.objects.filter(pk=lost.data["id"]).update(status=Lead.Status.LOST)
    refused = tenant_a.client.post(f"/api/v1/crm/leads/{lost.data['id']}/convert/", {"won": True}, format="json")
    assert refused.status_code == 400
    hidden = tenant_b.client.get(f"/api/v1/sales/invoices/{first.data['id']}/")
    assert hidden.status_code == 404


def test_job_serial_history_is_capped_and_company_scoped(tenant_a, tenant_b):
    hidden = tenant_a.client.get("/api/v1/workshop/job-cards/")
    assert hidden.status_code == 404
    _grant(tenant_a, "ENABLE_WORKSHOP")
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="SER-1", product_type=Product.ProductType.GOODS)
    serial = SerialNumber.objects.create(company=tenant_a.company, product=product, serial_number="SN-L7")
    def _job(number):
        job = JobCard.objects.create(
            company=tenant_a.company, customer=customer, number=number, complaint="noise",
        )
        JobCardLine.objects.create(
            company=tenant_a.company, job=job, kind=JobCardLine.Kind.PART,
            product=product, quantity=Decimal("1"), unit_price=Decimal("10"), serial=serial,
        )
        return job

    first_job = _job("JC-0")
    second_job = _job("JC-1")
    second = tenant_a.client.get(f"/api/v1/workshop/job-cards/{second_job.id}/")
    assert second.status_code == 200, second.data
    history = second.data["serial_history"]
    assert history[0]["jobs"][0]["id"] == first_job.id
    earlier = tenant_a.client.get(f"/api/v1/workshop/job-cards/{first_job.id}/")
    assert earlier.data["serial_history"][0]["jobs"] == []
    jobs = [first_job, second_job]
    for index in range(20):
        jobs.append(_job(f"JC-{index + 2}"))
    newest = tenant_a.client.get(f"/api/v1/workshop/job-cards/{jobs[-1].id}/")
    listed = newest.data["serial_history"][0]
    assert listed["capped"] is True
    assert len(listed["jobs"]) == 20
    assert jobs[0].id not in {row["id"] for row in listed["jobs"]}
    other_customer = make_customer(tenant_b.company)
    other_product = make_product(tenant_b.company, sku="SER-B")
    other_serial = SerialNumber.objects.create(company=tenant_b.company, product=other_product, serial_number="SN-L7")
    other_job = JobCard.objects.create(company=tenant_b.company, customer=other_customer, number="JC-B", complaint="x")
    JobCardLine.objects.create(
        company=tenant_b.company, job=other_job, kind=JobCardLine.Kind.PART,
        product=other_product, quantity=Decimal("1"), unit_price=Decimal("1"), serial=other_serial,
    )
    ids = {row["id"] for row in newest.data["serial_history"][0]["jobs"]}
    assert other_job.id not in ids


def _portal_token(company, customer, token):
    return CustomerPortalToken.objects.create(
        company=company, customer=customer, token=token, requested_via="EMAIL",
        expires_at=timezone.now() + timedelta(minutes=15),
    )


def test_portal_complaint_is_idempotent_and_length_capped(tenant_a, tenant_b):
    customer = make_customer(tenant_a.company, email="portal-a@example.com")
    other = make_customer(tenant_a.company, email="portal-b@example.com")
    token = _portal_token(tenant_a.company, customer, "portal-l8-a")
    other_token = _portal_token(tenant_a.company, other, "portal-l8-b")
    _grant(tenant_a, "ENABLE_CUSTOMER_PORTAL")
    anon = APIClient()
    denied = anon.post(
        f"/api/v1/public/customer-portal/{token.token}/complaints/",
        {"description": "Broken", "category": "DAMAGED"},
        format="json",
    )
    assert denied.status_code == 404
    _grant(tenant_a, "ENABLE_COMPLAINTS")
    created = anon.post(
        f"/api/v1/public/customer-portal/{token.token}/complaints/",
        {"description": "Box arrived dented", "category": "DAMAGED"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="portal-complaint-1",
    )
    assert created.status_code == 201, created.data
    replay = anon.post(
        f"/api/v1/public/customer-portal/{token.token}/complaints/",
        {"description": "Box arrived dented", "category": "DAMAGED"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="portal-complaint-1",
    )
    assert replay.status_code == 201
    assert replay.data["id"] == created.data["id"]
    assert Complaint.objects.filter(company=tenant_a.company, customer=customer).count() == 1
    long = anon.post(
        f"/api/v1/public/customer-portal/{token.token}/complaints/",
        {"description": "x" * 2001, "category": "DAMAGED"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="portal-complaint-long",
    )
    assert long.status_code == 400
    listing = anon.get(f"/api/v1/public/customer-portal/{other_token.token}/complaints/")
    assert listing.status_code == 200
    assert created.data["id"] not in {row["id"] for row in listing.data["complaints"]}
    assert CustomerPortalComplaintView.throttle_classes[0].scope == "customer_portal_complaint"
    _grant(tenant_b, "ENABLE_CUSTOMER_PORTAL")
    _grant(tenant_b, "ENABLE_COMPLAINTS")
    foreign = _portal_token(tenant_b.company, make_customer(tenant_b.company), "portal-l8-c")
    foreign_list = anon.get(f"/api/v1/public/customer-portal/{foreign.token}/complaints/")
    assert created.data["id"] not in {row["id"] for row in foreign_list.data["complaints"]}


def test_referral_paid_records_settlement_without_a_credit_note(tenant_a):
    _crm(tenant_a)
    hidden = tenant_a.client.get("/api/v1/crm/referrals/rewards/")
    assert hidden.status_code == 404
    _grant(tenant_a, "ENABLE_REFERRALS")
    referrer = make_customer(tenant_a.company, name="Referrer", phone="9000002211", state="Karnataka")
    product = make_product(tenant_a.company, sku="REF-1", gst_rate="0", product_type=Product.ProductType.SERVICE)
    draft = create_draft_invoice(
        tenant_a, referrer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    before = LedgerService.customer_outstanding(tenant_a.company, referrer)
    issued = tenant_a.client.post("/api/v1/crm/referrals/codes/issue/", {
        "referrer_customer": referrer.id, "reward_type": "FLAT", "reward_value": "10",
    }, format="json")
    assert issued.status_code == 201, issued.data
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Buyer", phone="9000002212",
        referral_code=issued.data["code"],
    )
    lead.state = "Karnataka"
    lead.save(update_fields=["state"])
    converted = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/", {"won": True, "amount": "100"}, format="json",
    )
    assert converted.status_code == 200, converted.data
    reward = ReferralReward.objects.get(opportunity_id=converted.data["opportunity"]["id"])
    rejected = ReferralReward.objects.get(pk=reward.pk)
    rejected.reward_status = ReferralReward.Status.REJECTED
    rejected.rejection_reason = "self_referral"
    rejected.save(update_fields=["reward_status", "rejection_reason"])
    blocked = tenant_a.client.post(
        f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/",
        {}, format="json", HTTP_IDEMPOTENCY_KEY="reward-reject",
    )
    assert blocked.status_code == 400
    rejected.reward_status = ReferralReward.Status.APPROVED
    rejected.rejection_reason = ""
    rejected.save(update_fields=["reward_status", "rejection_reason"])
    denied = tenant_a.staff_client.post(
        f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/", {}, format="json",
    )
    assert denied.status_code == 403
    first = tenant_a.client.post(
        f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/",
        {}, format="json", HTTP_IDEMPOTENCY_KEY="reward-paid-1",
    )
    assert first.status_code == 200, first.data
    assert first.data["reward_status"] == "PAID"
    assert first.data["credit_note"] is not None
    second = tenant_a.client.post(
        f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/",
        {}, format="json", HTTP_IDEMPOTENCY_KEY="reward-paid-1",
    )
    assert second.status_code == 200, second.data
    assert second.data["credit_note"] == first.data["credit_note"]
    reward.refresh_from_db()
    assert reward.reward_status == ReferralReward.Status.PAID
    note = SalesCreditNote.objects.get(company=tenant_a.company, customer=referrer)
    assert note.status == SalesCreditNote.Status.DRAFT
    assert reward.credit_note_id == note.id
    # The draft is not posted, so the referrer's outstanding stays put.
    assert LedgerService.customer_outstanding(tenant_a.company, referrer) == before


def test_won_amount_sits_next_to_invoices(tenant_a, tenant_b):
    _crm(tenant_a)
    _crm(tenant_b)
    customer = make_customer(tenant_a.company, state="Karnataka")
    product = make_product(tenant_a.company, sku="WON-1", gst_rate="0", product_type=Product.ProductType.SERVICE)
    won_lead = tenant_a.client.post(
        "/api/v1/crm/leads/", {"name": "Won", "phone": "9000003311", "state": "Karnataka"}, format="json",
    )
    won = tenant_a.client.post(
        f"/api/v1/crm/leads/{won_lead.data['id']}/convert/",
        {"won": True, "amount": "80"}, format="json",
    )
    assert won.status_code == 200, won.data
    Opportunity.objects.filter(pk=won.data["opportunity"]["id"]).update(customer_id=customer.id)
    open_lead = tenant_a.client.post(
        "/api/v1/crm/leads/", {"name": "Open", "phone": "9000003312", "state": "Karnataka"}, format="json",
    )
    opened = tenant_a.client.post(
        f"/api/v1/crm/leads/{open_lead.data['id']}/convert/", {"amount": "500"}, format="json",
    )
    assert opened.status_code == 200
    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "0"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    other_lead = tenant_b.client.post(
        "/api/v1/crm/leads/", {"name": "Other", "phone": "9000003313", "state": "Karnataka"}, format="json",
    )
    assert tenant_b.client.post(
        f"/api/v1/crm/leads/{other_lead.data['id']}/convert/",
        {"won": True, "amount": "999"}, format="json",
    ).status_code == 200
    month = timezone.localdate().strftime("%Y-%m")
    denied = tenant_a.staff_client.get(f"/api/v1/crm/opportunities/won-versus-invoices/?month={month}")
    assert denied.status_code == 403
    body = tenant_a.client.get(f"/api/v1/crm/opportunities/won-versus-invoices/?month={month}")
    assert body.status_code == 200, body.data
    assert Decimal(body.data["won_amount"]) == Decimal("80.00")
    assert Decimal(body.data["invoiced_amount"]) == Decimal("80.00")
    assert "predict" not in str(body.data).lower()


def _route(tenant, count, number):
    day = timezone.localdate()
    route = DeliveryRoute.objects.create(company=tenant.company, number=number, route_date=day)
    stops = []
    for index in range(count):
        customer = make_customer(tenant.company, name=f"{number}-{index}", pincode=f"56000{index}")
        order = SalesOrder.objects.create(
            company=tenant.company, customer=customer, number=f"SO-{number}-{index}",
            status=SalesOrder.Status.CONFIRMED, order_date=day, expected_delivery=day,
        )
        stops.append(DeliveryRouteStop.objects.create(company=tenant.company, route=route, sales_order=order))
    return route, stops


def test_stop_cap_keeps_a_prefix_of_the_existing_sequence(tenant_a):
    route, _stops = _route(tenant_a, 5, "CAP")
    hidden = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/suggest-sequence/", {}, format="json")
    assert hidden.status_code == 404
    _grant(tenant_a, "ENABLE_ROUTE_OPTIMIZATION")
    uncapped = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/suggest-sequence/", {}, format="json")
    assert uncapped.status_code == 200, uncapped.data
    assert isinstance(uncapped.data, list)
    order = [row["stop_id"] for row in uncapped.data]
    assert len(order) == 5
    capped = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/suggest-sequence/",
        {"stop_cap": 2}, format="json",
    )
    assert capped.status_code == 200, capped.data
    assert [row["stop_id"] for row in capped.data["sequenced"]] == order[:2]
    assert [row["stop_id"] for row in capped.data["unassigned"]] == order[2:]
    assert {row["reason"] for row in capped.data["unassigned"]} == {"over_stop_cap"}
    fraction = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/suggest-sequence/",
        {"stop_cap": 1.5}, format="json",
    )
    assert fraction.status_code == 400, fraction.data
    from django.core.cache import cache
    from sales.tasks import _cached_sequence
    from sales.route_optimization import SequencedStop

    cache.set(
        f"route-seq-result:{route.id}",
        _cached_sequence([SequencedStop(stop_id=stop_id, sequence=index, pincode="") for index, stop_id in enumerate(order, start=1)]),
        600,
    )
    cached = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/suggest-sequence/",
        {"use_cached": "1", "stop_cap": 2}, format="json",
    )
    assert cached.status_code == 200, cached.data
    assert [row["stop_id"] for row in cached.data["sequenced"]] == order[:2]
    assert [row["stop_id"] for row in cached.data["unassigned"]] == order[2:]


def test_contract_schedule_is_idempotent_and_sales_does_not_import_contracts(tenant_a):
    hidden = tenant_a.client.get("/api/v1/contracts/")
    assert hidden.status_code == 404
    _grant(tenant_a, "ENABLE_CONTRACTS")
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="AMC-1")
    today = timezone.localdate()
    created = tenant_a.client.post("/api/v1/contracts/", {
        "customer": customer.id,
        "product": product.id,
        "contract_type": "AMC",
        "start_date": str(today),
        "end_date": str(today + timedelta(days=365)),
        "value": "1200.00",
    }, format="json")
    assert created.status_code == 201, created.data
    assert RecurringInvoiceSchedule.objects.filter(company=tenant_a.company).count() == 0
    denied = tenant_a.staff_client.post(
        f"/api/v1/contracts/{created.data['id']}/create-schedule/", {}, format="json",
    )
    assert denied.status_code == 403
    first = tenant_a.client.post(
        f"/api/v1/contracts/{created.data['id']}/create-schedule/",
        {}, format="json", HTTP_IDEMPOTENCY_KEY="contract-schedule-1",
    )
    assert first.status_code == 200, first.data
    second = tenant_a.client.post(
        f"/api/v1/contracts/{created.data['id']}/create-schedule/",
        {}, format="json", HTTP_IDEMPOTENCY_KEY="contract-schedule-1",
    )
    assert second.data["id"] == first.data["id"]
    contract = Contract.objects.get(pk=created.data["id"])
    assert contract.recurring_schedule_id == first.data["id"]
    assert RecurringInvoiceSchedule.objects.filter(company=tenant_a.company).count() == 1
    future = tenant_a.client.post("/api/v1/contracts/", {
        "customer": customer.id,
        "product": product.id,
        "contract_type": "AMC",
        "start_date": str(today + timedelta(days=10)),
        "end_date": str(today + timedelta(days=365)),
        "value": "800.00",
    }, format="json")
    assert future.status_code == 201, future.data
    scheduled = tenant_a.client.post(
        f"/api/v1/contracts/{future.data['id']}/create-schedule/",
        {}, format="json", HTTP_IDEMPOTENCY_KEY="contract-schedule-future",
    )
    assert scheduled.status_code == 200, scheduled.data
    later = RecurringInvoiceSchedule.objects.get(pk=scheduled.data["id"])
    assert timezone.localtime(later.next_run_at).date() == today + timedelta(days=10)
    sales_root = Path(__file__).resolve().parents[1] / "sales"
    for path in sales_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "contracts":
                raise AssertionError(f"{path} imports contracts")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "contracts":
                        raise AssertionError(f"{path} imports contracts")


def test_portal_complaint_scope_is_not_a_money_scope():
    from core.idempotency import MONEY_IDEMPOTENCY_SCOPES

    assert "portal_complaint_create" not in MONEY_IDEMPOTENCY_SCOPES
    assert "referral_reward_credit_note" in MONEY_IDEMPOTENCY_SCOPES
    assert "contract_recurring_schedule" in MONEY_IDEMPOTENCY_SCOPES


@pytest.mark.django_db(transaction=True)
def test_won_lead_draft_invoice_race(tenant_a):
    _require_postgres()
    _crm(tenant_a)
    product = make_product(tenant_a.company, sku="RACE-LEAD", gst_rate="0")
    created = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Race", "phone": "9000004411", "state": "Karnataka"},
        format="json",
    )
    converted = tenant_a.client.post(
        f"/api/v1/crm/leads/{created.data['id']}/convert/", {"won": True}, format="json",
    )
    opportunity_id = converted.data["opportunity"]["id"]
    ids = []

    def post():
        connection.close()
        client = APIClient()
        client.force_authenticate(user=tenant_a.owner)
        try:
            response = client.post(
                f"/api/v1/crm/opportunities/{opportunity_id}/draft-invoice/",
                {"items": [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}]},
                format="json",
                HTTP_IDEMPOTENCY_KEY="lead-race",
            )
            if response.status_code in (200, 201):
                ids.append(response.data["id"])
        finally:
            connection.close()

    threads = [threading.Thread(target=post) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1
    assert len(set(ids)) == 1


@pytest.mark.django_db(transaction=True)
def test_referral_credit_note_race(tenant_a):
    _require_postgres()
    _crm(tenant_a)
    _grant(tenant_a, "ENABLE_REFERRALS")
    referrer = make_customer(tenant_a.company, name="Race Referrer", phone="9000005511", state="Karnataka")
    product = make_product(tenant_a.company, sku="RACE-REF", gst_rate="0", product_type=Product.ProductType.SERVICE)
    draft = create_draft_invoice(
        tenant_a, referrer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    issued = tenant_a.client.post("/api/v1/crm/referrals/codes/issue/", {
        "referrer_customer": referrer.id, "reward_type": "FLAT", "reward_value": "10",
    }, format="json")
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Race Buyer", phone="9000005512",
        referral_code=issued.data["code"],
    )
    lead.state = "Karnataka"
    lead.save(update_fields=["state"])
    converted = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/", {"won": True, "amount": "100"}, format="json",
    )
    reward = ReferralReward.objects.get(opportunity_id=converted.data["opportunity"]["id"])
    tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/")

    def post():
        connection.close()
        client = APIClient()
        client.force_authenticate(user=tenant_a.owner)
        try:
            client.post(
                f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/",
                {}, format="json", HTTP_IDEMPOTENCY_KEY="reward-race",
            )
        finally:
            connection.close()

    threads = [threading.Thread(target=post) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    notes = SalesCreditNote.objects.filter(company=tenant_a.company, customer=referrer)
    assert notes.count() == 1
    assert notes.get().status == SalesCreditNote.Status.DRAFT
    reward.refresh_from_db()
    assert reward.reward_status == ReferralReward.Status.PAID
    assert reward.credit_note_id == notes.get().id


@pytest.mark.django_db(transaction=True)
def test_contract_schedule_race(tenant_a):
    _require_postgres()
    _grant(tenant_a, "ENABLE_CONTRACTS")
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="RACE-AMC")
    today = timezone.localdate()
    created = tenant_a.client.post("/api/v1/contracts/", {
        "customer": customer.id,
        "product": product.id,
        "contract_type": "AMC",
        "start_date": str(today),
        "end_date": str(today + timedelta(days=30)),
        "value": "500.00",
    }, format="json")
    contract_id = created.data["id"]

    def post():
        connection.close()
        client = APIClient()
        client.force_authenticate(user=tenant_a.owner)
        try:
            client.post(
                f"/api/v1/contracts/{contract_id}/create-schedule/",
                {}, format="json", HTTP_IDEMPOTENCY_KEY="contract-race",
            )
        finally:
            connection.close()

    threads = [threading.Thread(target=post) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert RecurringInvoiceSchedule.objects.filter(company=tenant_a.company).count() == 1
