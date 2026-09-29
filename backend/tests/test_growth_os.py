"""Growth OS epics: campaigns, lines, complaints, tickets, contracts, referrals."""

import logging
import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection
from django.db.models.query import QuerySet
from django.test import override_settings
from django.utils import timezone

from accounts.models import CompanyUser
from complaints.models import Complaint
from contracts.models import Contract
from contracts.status import compute_contract_status
from contracts.tasks import refresh_contract_statuses
from core.models import AuditEvent, SequenceCounter
from core.services.sequences import next_number
from crm.models import Campaign, Lead, Opportunity, ReferralCode, ReferralReward
from crm.pipeline import capture_lead, import_lead_rows, ingest_whatsapp_message, next_assignee
from insights.alerts import build_business_alerts
from insights.attention import build_attention_rows
from sales.models import Quotation, SalesInvoice
from support.models import Ticket
from support.tickets import next_ticket_assignee

from .conftest import create_draft_invoice, make_customer, make_product


def _flags(company, **extra):
    company.feature_flags = {
        "ENABLE_COMPLAINTS": True,
        "ENABLE_SUPPORT_TICKETS": True,
        "ENABLE_CONTRACTS": True,
        "ENABLE_CRM": True,
        "ENABLE_REFERRALS": True,
        **extra,
    }
    company.save(update_fields=["feature_flags"])


def test_campaign_funnel_sums_converted_quotations_and_ignores_bad_public_campaign(tenant_a):
    company = tenant_a.company
    campaign = Campaign.objects.create(
        company=company, name="Diwali", campaign_type=Campaign.Type.DIGITAL, budget=Decimal("100"),
        created_by=tenant_a.owner,
    )
    child = Campaign.objects.create(
        company=company, name="Diwali South", campaign_type=Campaign.Type.EVENT,
        parent=campaign, budget=Decimal("0"), created_by=tenant_a.owner,
    )
    customer = make_customer(company)
    lead = capture_lead(company, tenant_a.owner, name="Asha", phone="9876543210", campaign=campaign.id)
    opportunity = Opportunity.objects.create(
        company=company, lead=lead, customer=customer, title="Deal", amount=Decimal("50"),
        stage=Opportunity.Stage.WON, created_by=tenant_a.owner,
    )
    Quotation.objects.create(
        company=company, customer=customer, opportunity=opportunity, grand_total=Decimal("40"),
        status=Quotation.Status.CONVERTED, created_by=tenant_a.owner,
    )
    Quotation.objects.create(
        company=company, customer=customer, opportunity=opportunity, grand_total=Decimal("25"),
        status=Quotation.Status.CONVERTED, created_by=tenant_a.owner,
    )
    Quotation.objects.create(
        company=company, customer=customer, opportunity=opportunity, grand_total=Decimal("999"),
        status=Quotation.Status.DRAFT, created_by=tenant_a.owner,
    )
    child_lead = capture_lead(company, tenant_a.owner, name="Beena", phone="9876543211", campaign=child.id)
    Opportunity.objects.create(
        company=company, lead=child_lead, customer=customer, title="Child", amount=Decimal("10"),
        stage=Opportunity.Stage.WON, created_by=tenant_a.owner,
    )
    resp = tenant_a.client.get(f"/api/v1/crm/campaigns/{campaign.id}/funnel/")
    assert resp.status_code == 200
    assert Decimal(resp.data["revenue"]) == Decimal("65")
    assert Decimal(resp.data["rollup"]["revenue"]) == Decimal("75")
    assert resp.data["roi_ratio"] is not None
    bare = Campaign.objects.create(
        company=company, name="Empty", campaign_type=Campaign.Type.DIGITAL, budget=0, created_by=tenant_a.owner,
    )
    zero = tenant_a.client.get(f"/api/v1/crm/campaigns/{bare.id}/funnel/")
    assert zero.data["roi_ratio"] is None
    cycle = tenant_a.client.patch(f"/api/v1/crm/campaigns/{campaign.id}/", {"parent": child.id}, format="json")
    assert cycle.status_code == 400
    from crm.pipeline import ensure_lead_form_token

    token = ensure_lead_form_token(company)
    public = tenant_a.client.post(
        f"/api/v1/crm/public/lead-form/{token}/",
        {"name": "Public", "phone": "9876543212", "campaign": 999999},
        format="json",
    )
    assert public.status_code == 202
    assert public.data == {"ok": True}


def test_opportunity_lines_derive_amount_and_forecast_keeps_unscheduled(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="OPP-1")
    created = tenant_a.client.post("/api/v1/crm/leads/", {"name": "Line Lead", "phone": "9000000001"}, format="json")
    converted = tenant_a.client.post(f"/api/v1/crm/leads/{created.data['id']}/convert/", {"amount": "10"}, format="json")
    opportunity_id = converted.data["opportunity"]["id"]
    line = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{opportunity_id}/lines/",
        {"product": product.id, "quantity": "2", "unit_price": "15"},
        format="json",
    )
    assert line.status_code == 201, line.data
    opportunity = Opportunity.objects.get(pk=opportunity_id)
    assert opportunity.amount == Decimal("30.00")
    blocked = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity_id}/", {"amount": "1"}, format="json",
    )
    assert blocked.status_code == 400
    tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity_id}/",
        {"probability": 50, "expected_close_date": None},
        format="json",
    )
    forecast = tenant_a.client.get("/api/v1/crm/opportunities/forecast/")
    assert forecast.status_code == 200
    assert Decimal(forecast.data["unscheduled"]) == Decimal("15.00")
    won = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity_id}/", {"stage": "WON"}, format="json",
    )
    assert won.status_code == 200
    quote = tenant_a.client.post(f"/api/v1/crm/opportunities/{opportunity_id}/quotation/")
    assert quote.status_code == 201
    quotation = Quotation.objects.get(pk=quote.data["id"])
    assert quotation.items.count() == 1
    assert quotation.grand_total > 0


def test_complaint_transitions_and_return_requires_invoice(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "DAMAGED", "description": "Box crushed"},
        format="json",
    )
    assert created.status_code == 201
    complaint_id = created.data["id"]
    assert created.data["number"].startswith("RMA-")
    illegal = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "RESOLVED"}, format="json",
    )
    assert illegal.status_code == 400
    tenant_a.client.post(f"/api/v1/complaints/{complaint_id}/transition/", {"status": "INSPECTING"}, format="json")
    missing = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-return/", {"items": []}, format="json",
    )
    assert missing.status_code == 400
    invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, created_by=tenant_a.owner,
    )
    tenant_a.client.patch(f"/api/v1/complaints/{complaint_id}/", {"source_invoice": invoice.id}, format="json")
    product = make_product(tenant_a.company, sku="RMA-1")
    made = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-return/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "10"}]},
        format="json",
    )
    assert made.status_code == 201, made.data
    again = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-return/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "10"}]},
        format="json",
    )
    assert again.status_code == 200
    assert again.data["id"] == made.data["id"]
    tenant_a.client.post(f"/api/v1/complaints/{complaint_id}/transition/", {"status": "APPROVED"}, format="json")
    blocked = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "RESOLVED"}, format="json",
    )
    assert blocked.status_code == 400
    from sales.models import SalesReturn
    SalesReturn.objects.filter(pk=made.data["id"]).update(status=SalesReturn.Status.COMPLETED)
    resolved = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "RESOLVED"}, format="json",
    )
    assert resolved.status_code == 200
    reopen = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "OPEN"}, format="json",
    )
    assert reopen.status_code == 400
    report = tenant_a.client.get("/api/v1/complaints/report/")
    assert report.data["resolved_with_document"] == 1


def test_ticket_sla_waiting_and_alert_stays_off_without_flag(tenant_a, tenant_b):
    before = build_business_alerts(tenant_b.company)
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/support/tickets/",
        {"customer": customer.id, "subject": "Pump", "priority": "URGENT"},
        format="json",
    )
    assert created.status_code == 201, created.data
    ticket = Ticket.objects.get(pk=created.data["id"])
    delta = ticket.sla_due_at - ticket.created_at
    assert timedelta(hours=4) - timedelta(seconds=5) <= delta <= timedelta(hours=4) + timedelta(seconds=5)
    no_customer = tenant_a.client.post("/api/v1/support/tickets/", {"subject": "x"}, format="json")
    assert no_customer.status_code == 400
    tenant_a.client.post(f"/api/v1/support/tickets/{ticket.id}/transition/", {"status": "IN_PROGRESS"}, format="json")
    tenant_a.client.post(f"/api/v1/support/tickets/{ticket.id}/transition/", {"status": "WAITING"}, format="json")
    ticket.refresh_from_db()
    ticket.waiting_since = timezone.now() - timedelta(hours=2)
    ticket.save(update_fields=["waiting_since"])
    due_before = ticket.sla_due_at
    tenant_a.client.post(f"/api/v1/support/tickets/{ticket.id}/transition/", {"status": "IN_PROGRESS"}, format="json")
    ticket.refresh_from_db()
    assert ticket.sla_due_at > due_before
    assert ticket.waiting_since is None
    ticket.sla_due_at = timezone.now() - timedelta(minutes=1)
    ticket.save(update_fields=["sla_due_at"])
    alerts = build_business_alerts(tenant_a.company)
    assert any(row["code"] == "TICKET_SLA_BREACH" for row in alerts)
    assert build_business_alerts(tenant_b.company) == before


def test_contract_status_boundaries_and_cancel(tenant_a):
    today = timezone.localdate()
    assert compute_contract_status(today, 30, today) == "EXPIRING"
    assert compute_contract_status(today + timedelta(days=1), 30, today) == "EXPIRING"
    assert compute_contract_status(today + timedelta(days=31), 30, today) == "ACTIVE"
    assert compute_contract_status(today - timedelta(days=1), 30, today) == "EXPIRED"
    assert compute_contract_status(today, 0, today) == "EXPIRING"
    assert compute_contract_status(today + timedelta(days=1), 0, today) == "ACTIVE"
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/contracts/",
        {
            "customer": customer.id,
            "contract_type": "WARRANTY",
            "start_date": str(today - timedelta(days=10)),
            "end_date": str(today - timedelta(days=1)),
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["status"] == "EXPIRED"
    contract = Contract.objects.get(pk=created.data["id"])
    contract.end_date = today + timedelta(days=10)
    contract.status = Contract.Status.ACTIVE
    contract.save()
    contract.refresh_from_db()
    assert contract.status == "EXPIRING"
    cancelled = tenant_a.client.patch(f"/api/v1/contracts/{contract.id}/", {"status": "CANCELLED"}, format="json")
    assert cancelled.status_code == 200
    refresh_contract_statuses()
    contract.refresh_from_db()
    assert contract.status == "CANCELLED"
    forced = tenant_a.client.patch(f"/api/v1/contracts/{contract.id}/", {"status": "EXPIRED"}, format="json")
    assert forced.status_code == 400
    backwards = tenant_a.client.patch(
        f"/api/v1/contracts/{contract.id}/",
        {"start_date": str(today), "end_date": str(today - timedelta(days=1))},
        format="json",
    )
    assert backwards.status_code == 400


def test_referral_reward_snapshot_and_owner_approval(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    issued = tenant_a.client.post(
        "/api/v1/crm/referrals/codes/issue/",
        {"referrer_customer": customer.id, "reward_type": "PERCENT", "reward_value": "10"},
        format="json",
    )
    assert issued.status_code == 201, issued.data
    code = issued.data["code"]
    assert len(code) == 8
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Referred", phone="9000000099", referral_code=code,
    )
    assert lead.referral_code_id == issued.data["id"]
    capture_lead(
        tenant_a.company, tenant_a.owner, name="Bad code", phone="9000000098",
        referral_code="NOPE", attribution_quiet=True,
    )
    converted = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/", {"won": True, "amount": "250"}, format="json",
    )
    opportunity_id = converted.data["opportunity"]["id"]
    reward = ReferralReward.objects.get(opportunity_id=opportunity_id)
    assert reward.reward_amount == Decimal("25")
    assert reward.reward_status == ReferralReward.Status.PENDING
    Opportunity.objects.filter(pk=opportunity_id).update(amount=Decimal("999"))
    reward.refresh_from_db()
    assert reward.reward_amount == Decimal("25")
    denied = tenant_a.staff_client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/")
    assert denied.status_code == 403
    approved = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/")
    assert approved.status_code == 200
    board = tenant_a.client.get("/api/v1/crm/referrals/codes/leaderboard/")
    assert board.status_code == 200
    assert Decimal(board.data[0]["approved_total"]) == Decimal("25")
    both = ReferralCode(company=tenant_a.company, code="ZZZZZZZZ", reward_value=0)
    with pytest.raises(IntegrityError):
        both.save()


def test_next_number_is_unique_per_company(tenant_a):
    first = next_number(tenant_a.company, "COMPLAINT", prefix="RMA")
    second = next_number(tenant_a.company, "COMPLAINT", prefix="RMA")
    assert first != second
    assert first.endswith("000001")


def test_next_number_retries_a_lost_insert_race(tenant_a, monkeypatch):
    calls = {"n": 0}
    original = QuerySet.get_or_create

    def flaky(self, *args, **kwargs):
        if self.model is SequenceCounter:
            calls["n"] += 1
            if calls["n"] == 1:
                raise IntegrityError("duplicate sequence row")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "get_or_create", flaky)
    assert next_number(tenant_a.company, "RACE", prefix="R").endswith("000001")
    assert calls["n"] == 2


@pytest.mark.postgres
def test_concurrent_next_number_allocates_two_values(tenant_a):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL so two connections can race the counter")
    results = []
    errors = []
    barrier = threading.Barrier(2, timeout=10)

    def allocate():
        connection.close()
        try:
            barrier.wait()
            results.append(next_number(tenant_a.company, "RACE2", prefix="R"))
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=allocate) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    assert len(set(results)) == 2


def test_campaign_rollup_stops_at_depth_five(tenant_a):
    customer = make_customer(tenant_a.company)
    parent = None
    root = None
    for index in range(7):
        row = Campaign.objects.create(
            company=tenant_a.company, name=f"Level {index}", campaign_type=Campaign.Type.DIGITAL,
            parent=parent, budget=0, created_by=tenant_a.owner,
        )
        if root is None:
            root = row
        parent = row
        lead = capture_lead(
            tenant_a.company, tenant_a.owner, name=f"L{index}", phone=f"910000000{index}", campaign=row.id,
        )
        Opportunity.objects.create(
            company=tenant_a.company, lead=lead, customer=customer, title=f"D{index}",
            amount=Decimal("1"), stage=Opportunity.Stage.WON, created_by=tenant_a.owner,
        )
    funnel = tenant_a.client.get(f"/api/v1/crm/campaigns/{root.id}/funnel/")
    assert Decimal(funnel.data["revenue"]) == Decimal("1")
    assert Decimal(funnel.data["rollup"]["revenue"]) == Decimal("6")


def test_csv_and_whatsapp_attribution(tenant_a):
    _flags(tenant_a.company)
    campaign = Campaign.objects.create(
        company=tenant_a.company, name="CSV", campaign_type=Campaign.Type.DIGITAL, created_by=tenant_a.owner,
    )
    issued = tenant_a.client.post(
        "/api/v1/crm/referrals/codes/issue/",
        {"referrer_customer": make_customer(tenant_a.company).id, "reward_type": "FLAT", "reward_value": "5"},
        format="json",
    )
    result = import_lead_rows(tenant_a.company, tenant_a.owner, [{
        "name": "Csv Lead",
        "phone": "9222000001",
        "campaign": str(campaign.id),
        "referral_code": issued.data["code"],
    }])
    assert result["created"] == 1, result
    lead = Lead.objects.get(company=tenant_a.company, name="Csv Lead")
    assert lead.campaign_id == campaign.id
    assert lead.referral_code_id == issued.data["id"]
    whatsapp = ingest_whatsapp_message(
        tenant_a.company, message_id="wa-1", sender="9222000002", text="hello", sent_at="2026-09-24",
    )
    assert whatsapp.campaign_id is None
    assert whatsapp.referral_code_id is None


def test_public_bad_referral_still_captures(tenant_a):
    _flags(tenant_a.company)
    from crm.pipeline import ensure_lead_form_token

    token = ensure_lead_form_token(tenant_a.company)
    public = tenant_a.client.post(
        f"/api/v1/crm/public/lead-form/{token}/",
        {"name": "Bad ref", "phone": "9222000003", "referral_code": "NOTACODE"},
        format="json",
    )
    assert public.status_code == 202
    assert public.data == {"ok": True}
    lead = Lead.objects.get(company=tenant_a.company, name="Bad ref")
    assert lead.referral_code_id is None


def test_line_validators_and_forecast_month(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="OPP-2")
    created = tenant_a.client.post("/api/v1/crm/leads/", {"name": "Forecast", "phone": "9222000004"}, format="json")
    converted = tenant_a.client.post(f"/api/v1/crm/leads/{created.data['id']}/convert/", {"amount": "100"}, format="json")
    opportunity_id = converted.data["opportunity"]["id"]
    zero = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{opportunity_id}/lines/",
        {"product": product.id, "quantity": "0", "unit_price": "10"},
        format="json",
    )
    assert zero.status_code == 400
    negative = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{opportunity_id}/lines/",
        {"product": product.id, "quantity": "1", "unit_price": "-1"},
        format="json",
    )
    assert negative.status_code == 400
    close = timezone.localdate().replace(day=1)
    tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity_id}/",
        {"probability": 50, "expected_close_date": str(close)},
        format="json",
    )
    forecast = tenant_a.client.get("/api/v1/crm/opportunities/forecast/")
    assert forecast.data["months"][0]["month"] == close.strftime("%Y-%m")
    assert Decimal(forecast.data["months"][0]["amount"]) == Decimal("50.00")
    assert customer.id


def test_ticket_round_robin_counts_open_tickets_not_leads(tenant_a):
    other_user = get_user_model().objects.create_user(
        email="rr-other@a.test", password="StrongPass123!", full_name="Other staff",
    )
    other = CompanyUser.objects.create(
        company=tenant_a.company, user=other_user, role=CompanyUser.Role.SALES_STAFF,
    )
    staff = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    customer = make_customer(tenant_a.company)
    for index in range(3):
        Lead.objects.create(
            company=tenant_a.company, name=f"Lead {index}", phone=f"933300000{index}",
            assigned_to=other, created_by=tenant_a.owner,
        )
    assert next_assignee(tenant_a.company).id == staff.id
    assert next_ticket_assignee(tenant_a.company).id == min(staff.id, other.id)
    Ticket.objects.create(
        company=tenant_a.company, customer=customer, subject="Open", number="TKT-000099",
        status=Ticket.Status.OPEN, assigned_to=staff, created_by=tenant_a.owner,
    )
    assert next_ticket_assignee(tenant_a.company).id == other.id
    assert next_assignee(tenant_a.company).id == staff.id


def test_waiting_extends_sla_by_the_paused_duration(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/support/tickets/",
        {"customer": customer.id, "subject": "Pause", "priority": "HIGH"},
        format="json",
    )
    ticket_id = created.data["id"]
    tenant_a.client.post(f"/api/v1/support/tickets/{ticket_id}/transition/", {"status": "IN_PROGRESS"}, format="json")
    tenant_a.client.post(f"/api/v1/support/tickets/{ticket_id}/transition/", {"status": "WAITING"}, format="json")
    ticket = Ticket.objects.get(pk=ticket_id)
    paused_for = timedelta(hours=2)
    ticket.waiting_since = timezone.now() - paused_for
    ticket.save(update_fields=["waiting_since"])
    due_before = ticket.sla_due_at
    tenant_a.client.post(f"/api/v1/support/tickets/{ticket_id}/transition/", {"status": "IN_PROGRESS"}, format="json")
    ticket.refresh_from_db()
    assert abs((ticket.sla_due_at - due_before) - paused_for) < timedelta(seconds=5)


def test_complaint_credit_note_replacement_isolation_and_flag(tenant_a, tenant_b, caplog):
    hidden = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": 1, "category": "OTHER", "description": "off"},
        format="json",
    )
    assert hidden.status_code == 404
    assert tenant_a.client.get("/api/v1/support/tickets/").status_code == 404
    assert tenant_a.client.get("/api/v1/contracts/").status_code == 404
    assert tenant_a.client.get("/api/v1/crm/referrals/codes/").status_code == 404
    _flags(tenant_a.company)
    _flags(tenant_b.company)
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="RMA-2")
    caplog.set_level(logging.INFO, logger="bizboard.flags")
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "QUALITY", "description": "Leak"},
        format="json",
    )
    assert "complaint_created" in caplog.text
    complaint_id = created.data["id"]
    assert tenant_b.client.get(f"/api/v1/complaints/{complaint_id}/").status_code == 404
    tenant_a.client.post(f"/api/v1/complaints/{complaint_id}/transition/", {"status": "INSPECTING"}, format="json")
    invoice = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/complaints/{complaint_id}/", {"source_invoice": invoice["id"]}, format="json",
    )
    source_item = invoice["items"][0]["id"]
    credit_items = [{"product": product.id, "quantity": "1", "unit_price": "10", "source_item": source_item}]
    order_items = [{"product": product.id, "quantity": "1", "unit_price": "10"}]
    credit = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-credit-note/", {"items": credit_items}, format="json",
    )
    assert credit.status_code == 201, credit.data
    again = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-credit-note/", {"items": credit_items}, format="json",
    )
    assert again.status_code == 200
    assert again.data["id"] == credit.data["id"]
    replacement = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-replacement-order/", {"items": order_items}, format="json",
    )
    assert replacement.status_code == 201, replacement.data


def test_attachment_type_size_and_delete(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "DAMAGED", "description": "Photo"},
        format="json",
    )
    complaint_id = created.data["id"]
    bad = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
    rejected = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/attachments/", {"file": bad}, format="multipart",
    )
    assert rejected.status_code == 400
    # Real PDF magic bytes so the size check below is what actually rejects
    # it, not content-type sniffing tripping on plain "x" filler bytes.
    with override_settings(FILE_UPLOAD_MAX_MEMORY_SIZE=8):
        oversized = SimpleUploadedFile("big.pdf", b"%PDF-1234", content_type="application/pdf")
        too_big = tenant_a.client.post(
            f"/api/v1/complaints/{complaint_id}/attachments/", {"file": oversized}, format="multipart",
        )
    assert too_big.status_code == 400
    assert "size limit" in too_big.data["detail"]
    photo = SimpleUploadedFile("damage.jpg", b"\xff\xd8\xff\xd9", content_type="image/jpeg")
    uploaded = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/attachments/", {"file": photo}, format="multipart",
    )
    assert uploaded.status_code == 201, uploaded.data
    deleted = tenant_a.client.delete(
        f"/api/v1/complaints/{complaint_id}/attachments/?attachment={uploaded.data['id']}",
    )
    assert deleted.status_code == 204
    listed = tenant_a.client.get(f"/api/v1/complaints/{complaint_id}/attachments/")
    assert listed.data == []


def test_attachment_content_sniffing_ignores_a_spoofed_header(tenant_a):
    """A renamed executable with a forged image/* Content-Type header must
    still be rejected — the real signature check reads the file's actual
    bytes, not the client-supplied header."""
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "DAMAGED", "description": "Spoofed"},
        format="json",
    )
    complaint_id = created.data["id"]
    spoofed = SimpleUploadedFile("payload.jpg", b"MZ\x90\x00this is not a jpeg", content_type="image/jpeg")
    rejected = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/attachments/", {"file": spoofed}, format="multipart",
    )
    assert rejected.status_code == 400
    assert "JPEG" in rejected.data["detail"]

    # A real PNG works regardless of what the browser claims its type is.
    mislabeled_png = SimpleUploadedFile(
        "photo.bin", b"\x89PNG\r\n\x1a\n" + b"rest-of-file", content_type="application/octet-stream",
    )
    accepted = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/attachments/", {"file": mislabeled_png}, format="multipart",
    )
    assert accepted.status_code == 201, accepted.data

    webp = SimpleUploadedFile("anim.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ", content_type="image/webp")
    webp_ok = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/attachments/", {"file": webp}, format="multipart",
    )
    assert webp_ok.status_code == 201, webp_ok.data


def test_contract_service_event_and_idempotent_refresh(tenant_a, caplog):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    caplog.set_level(logging.INFO, logger="bizboard.flags")
    today = timezone.localdate()
    created = tenant_a.client.post(
        "/api/v1/contracts/",
        {
            "customer": customer.id,
            "contract_type": "AMC",
            "start_date": str(today - timedelta(days=5)),
            "end_date": str(today + timedelta(days=40)),
        },
        format="json",
    )
    assert "contract_created" in caplog.text
    ticket = tenant_a.client.post(
        "/api/v1/support/tickets/",
        {"customer": customer.id, "subject": "Visit", "priority": "LOW"},
        format="json",
    )
    assert "ticket_created" in caplog.text
    logged = tenant_a.client.post(
        f"/api/v1/contracts/{created.data['id']}/service-events/",
        {"ticket": ticket.data["id"], "notes": "Replaced filter"},
        format="json",
    )
    assert logged.status_code == 201, logged.data
    assert logged.data["ticket"] == ticket.data["id"]
    Contract.objects.filter(pk=created.data["id"]).update(
        status=Contract.Status.ACTIVE, end_date=today - timedelta(days=1),
    )
    assert refresh_contract_statuses() >= 1
    contract = Contract.objects.get(pk=created.data["id"])
    assert contract.status == Contract.Status.EXPIRED
    assert refresh_contract_statuses() == 0
    assert AuditEvent.objects.filter(
        company=tenant_a.company, action="contract_status_refreshed", entity_id=str(contract.pk),
    ).count() == 1


def test_inspection_notes_can_be_cleared(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "DAMAGED", "description": "Dent"},
        format="json",
    )
    complaint_id = created.data["id"]
    noted = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/",
        {"status": "INSPECTING", "inspection_notes": "Corner crushed"},
        format="json",
    )
    assert noted.data["inspection_notes"] == "Corner crushed"
    cleared = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/",
        {"status": "APPROVED", "inspection_notes": ""},
        format="json",
    )
    assert cleared.status_code == 200
    assert cleared.data["inspection_notes"] == ""


def test_probability_over_100_is_rejected(tenant_a):
    created = tenant_a.client.post("/api/v1/crm/leads/", {"name": "Odds", "phone": "9222000010"}, format="json")
    converted = tenant_a.client.post(f"/api/v1/crm/leads/{created.data['id']}/convert/", {"amount": "10"}, format="json")
    opportunity_id = converted.data["opportunity"]["id"]
    too_high = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity_id}/", {"probability": 101}, format="json",
    )
    assert too_high.status_code == 400
    negative = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity_id}/", {"probability": -1}, format="json",
    )
    assert negative.status_code == 400


def test_public_non_numeric_campaign_still_captures(tenant_a):
    _flags(tenant_a.company)
    from crm.pipeline import ensure_lead_form_token

    token = ensure_lead_form_token(tenant_a.company)
    public = tenant_a.client.post(
        f"/api/v1/crm/public/lead-form/{token}/",
        {"name": "Bad campaign", "phone": "9222000011", "campaign": "abc"},
        format="json",
    )
    assert public.status_code == 202, public.data
    assert public.data == {"ok": True}
    lead = Lead.objects.get(company=tenant_a.company, name="Bad campaign")
    assert lead.campaign_id is None


def test_waiting_ticket_never_shows_as_sla_breached(tenant_a):
    """Regression: the SLA-breach builder used to include WAITING, but the
    clock is frozen while waiting, so a stale sla_due_at must not alert."""
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/support/tickets/",
        {"customer": customer.id, "subject": "Paused", "priority": "URGENT"},
        format="json",
    )
    ticket_id = created.data["id"]
    tenant_a.client.post(f"/api/v1/support/tickets/{ticket_id}/transition/", {"status": "IN_PROGRESS"}, format="json")
    tenant_a.client.post(f"/api/v1/support/tickets/{ticket_id}/transition/", {"status": "WAITING"}, format="json")
    ticket = Ticket.objects.get(pk=ticket_id)
    # A realistic long wait: waiting_since is 2 days old, and the ticket's
    # frozen sla_due_at is already a day in the past.
    ticket.waiting_since = timezone.now() - timedelta(days=2)
    ticket.sla_due_at = timezone.now() - timedelta(days=1)
    ticket.save(update_fields=["waiting_since", "sla_due_at"])
    alerts = build_business_alerts(tenant_a.company)
    assert not any(row["code"] == "TICKET_SLA_BREACH" for row in alerts)
    # Leaving WAITING extends sla_due_at by the real elapsed pause (~2 days),
    # landing back in the future — still not a breach.
    tenant_a.client.post(f"/api/v1/support/tickets/{ticket_id}/transition/", {"status": "IN_PROGRESS"}, format="json")
    ticket.refresh_from_db()
    assert ticket.sla_due_at > timezone.now()
    alerts_after = build_business_alerts(tenant_a.company)
    assert not any(row["code"] == "TICKET_SLA_BREACH" for row in alerts_after)


def test_complaint_document_actions_reject_empty_items(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "DAMAGED", "description": "Empty items"},
        format="json",
    )
    complaint_id = created.data["id"]
    invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, created_by=tenant_a.owner,
    )
    tenant_a.client.patch(f"/api/v1/complaints/{complaint_id}/", {"source_invoice": invoice.id}, format="json")
    tenant_a.client.post(f"/api/v1/complaints/{complaint_id}/transition/", {"status": "INSPECTING"}, format="json")
    omitted = tenant_a.client.post(f"/api/v1/complaints/{complaint_id}/create-return/", {}, format="json")
    assert omitted.status_code == 400
    empty = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-return/", {"items": []}, format="json",
    )
    assert empty.status_code == 400
    assert Complaint.objects.get(pk=complaint_id).sales_return_id is None
    order_empty = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-replacement-order/", {"items": []}, format="json",
    )
    assert order_empty.status_code == 400


def test_complaint_rejects_invoice_for_a_different_customer(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company, name="Customer A", phone="9333300001")
    other_customer = make_customer(tenant_a.company, name="Customer B", phone="9333300002")
    other_invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=other_customer, created_by=tenant_a.owner,
    )
    mismatched = tenant_a.client.post(
        "/api/v1/complaints/",
        {
            "customer": customer.id,
            "source_invoice": other_invoice.id,
            "category": "DAMAGED",
            "description": "Wrong invoice",
        },
        format="json",
    )
    assert mismatched.status_code == 400
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "DAMAGED", "description": "Fine for now"},
        format="json",
    )
    complaint_id = created.data["id"]
    patched = tenant_a.client.patch(
        f"/api/v1/complaints/{complaint_id}/", {"source_invoice": other_invoice.id}, format="json",
    )
    assert patched.status_code == 400
    assert Complaint.objects.get(pk=complaint_id).source_invoice_id is None


def test_refresh_contract_statuses_does_not_n_plus_one_on_company(tenant_a):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    today = timezone.localdate()

    def _desynced_contract(number):
        # save() immediately re-derives the correct status, so desync via a
        # bulk .update() (bypassing save()) the same way a real contract
        # could drift out of sync between nightly runs.
        contract = Contract.objects.create(
            company=tenant_a.company, customer=customer, contract_type=Contract.Type.WARRANTY,
            number=number, start_date=today - timedelta(days=40),
            end_date=today + timedelta(days=40), created_by=tenant_a.owner,
        )
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.ACTIVE, end_date=today - timedelta(days=1),
        )
        return contract.id

    _desynced_contract("CON-92000")
    with CaptureQueriesContext(connection) as one_ctx:
        changed_one = refresh_contract_statuses()
    assert changed_one == 1

    for index in range(5):
        _desynced_contract(f"CON-9300{index}")
    with CaptureQueriesContext(connection) as five_ctx:
        changed_five = refresh_contract_statuses()
    assert changed_five == 5

    # If contract.company triggered a fresh SELECT per changed row (the N+1
    # this fix removes), 5 changed rows would cost roughly 5x the queries of
    # 1 changed row instead of scaling with a small, bounded slope.
    assert len(five_ctx.captured_queries) <= len(one_ctx.captured_queries) + 8


def test_referral_reward_concurrent_win_returns_existing_row(tenant_a, monkeypatch):
    """A second evaluate_referral_reward() call racing the unique constraint
    must return the winner's row, not raise IntegrityError."""
    from crm import referrals as referrals_module

    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    issued = tenant_a.client.post(
        "/api/v1/crm/referrals/codes/issue/",
        {"referrer_customer": customer.id, "reward_type": "FLAT", "reward_value": "5"},
        format="json",
    )
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Race", phone="9444400001",
        referral_code=issued.data["code"],
    )
    opportunity = Opportunity.objects.create(
        company=tenant_a.company, lead=lead, customer=customer, title="Race deal",
        amount=Decimal("100"), stage=Opportunity.Stage.WON, created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    winner = ReferralReward.objects.create(
        company=tenant_a.company,
        referral_code=ReferralCode.objects.get(pk=issued.data["id"]),
        lead=lead,
        opportunity=opportunity,
        reward_amount=Decimal("5"),
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )

    original_filter = referrals_module.ReferralReward.objects.filter

    def racy_filter(*args, **kwargs):
        # Simulate another request having already won the race between this
        # function's existence check and its own create() call.
        return original_filter(*args, **kwargs).none()

    monkeypatch.setattr(referrals_module.ReferralReward.objects, "filter", racy_filter)
    result = referrals_module.evaluate_referral_reward(opportunity)
    monkeypatch.undo()
    assert result.id == winner.id
    assert ReferralReward.objects.filter(company=tenant_a.company, opportunity=opportunity).count() == 1


def test_attention_shows_each_sla_and_renewal_row(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_create_sales = True
    membership.save(update_fields=["can_create_sales"])
    for index in range(2):
        Ticket.objects.create(
            company=tenant_a.company, customer=customer, subject=f"Late {index}",
            number=f"TKT-90000{index}", status=Ticket.Status.OPEN,
            sla_due_at=timezone.now() - timedelta(minutes=5), created_by=tenant_a.owner,
        )
    today = timezone.localdate()
    for index in range(2):
        Contract.objects.create(
            company=tenant_a.company, customer=customer, contract_type=Contract.Type.WARRANTY,
            number=f"CON-90000{index}", start_date=today - timedelta(days=10), end_date=today,
            status=Contract.Status.EXPIRING, created_by=tenant_a.owner,
        )
    rows = build_attention_rows(tenant_a.company, membership)
    codes = [row["code"] for row in rows]
    assert codes.count("TICKET_SLA_BREACH") == 2
    assert codes.count("CONTRACT_RENEWAL") == 2


def test_opportunity_competitor_is_stored_and_ignored_by_forecast(tenant_a):
    import inspect

    from crm.forecast import pipeline_forecast

    assert "competitor" not in inspect.getsource(pipeline_forecast)
    _flags(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/crm/opportunities/",
        {"title": "Against a rival", "amount": "1000", "competitor": "Old Supplier Co", "probability": 0},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["competitor"] == "Old Supplier Co"
    blank = tenant_a.client.post(
        "/api/v1/crm/opportunities/",
        {"title": "No rival", "amount": "500"},
        format="json",
    )
    assert blank.status_code == 201, blank.data
    assert blank.data["competitor"] == ""
    forecast = tenant_a.client.get("/api/v1/crm/opportunities/forecast/")
    assert forecast.status_code == 200
    assert Decimal(str(forecast.data["unscheduled"])) == 0
