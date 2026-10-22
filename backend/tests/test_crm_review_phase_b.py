"""CRM review PR-B/C/E: one revenue definition, referral rewards, dedupe + lead lifecycle, capture hardening."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import override_settings

from accounts.models import CompanyUser
from crm.models import Campaign, Lead, LeadActivity, LeadIngestJob, Opportunity, ReferralCode, ReferralReward
from crm.pipeline import capture_lead
from crm.revenue import opportunity_revenue, revenue_by_opportunity
from sales.models import SalesCreditNote, SalesInvoice

from .conftest import make_customer, make_product
from .test_crm_review_repro import _completed_invoice, _issue_code
from .test_growth_os import _flags

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    return data["data"] if isinstance(data, dict) and "data" in data and "id" not in data else data


def _staff_can_sell(tenant):
    """Sales staff pass the base sales permission, so a 403 below comes from the CRM rule under test."""
    CompanyUser.objects.filter(company=tenant.company, user=tenant.staff).update(can_create_sales=True)


def _won_deal(tenant, amount="1000", phone="9000001001", **capture):
    lead = capture_lead(tenant.company, tenant.owner, name=f"Lead {phone}", phone=phone, **capture)
    resp = tenant.client.post(f"/api/v1/crm/leads/{lead.id}/convert/", {"won": True, "amount": amount}, format="json")
    assert resp.status_code == 200, resp.data
    return lead, Opportunity.objects.get(pk=resp.data["opportunity"]["id"])


# ------------------------------------------------------------------ WP-5: revenue


@pytest.mark.invariant_skip("money.header_totals_identity", reason="documents are built through the ORM with header totals that do not match their lines")
def test_revenue_follows_the_invoice_link_net_of_credit_notes(tenant_a):
    _flags(tenant_a.company)
    _lead, deal = _won_deal(tenant_a)
    invoice = _completed_invoice(tenant_a, deal.customer, "1000", opportunity_id=deal.id)
    assert opportunity_revenue(deal) == Decimal("1000.00")
    SalesCreditNote.objects.create(
        company=tenant_a.company, customer=deal.customer, sales_invoice=invoice,
        status=SalesCreditNote.Status.COMPLETED, taxable_total=Decimal("250.00"),
        created_by=tenant_a.owner,
    )
    assert opportunity_revenue(deal) == Decimal("750.00")
    # An invoice of the same customer that belongs to no deal is not this deal's revenue.
    _completed_invoice(tenant_a, deal.customer, "400")
    assert opportunity_revenue(deal) == Decimal("750.00")


def test_draft_invoice_from_a_deal_sets_the_link(tenant_a):
    _flags(tenant_a.company)
    _lead, deal = _won_deal(tenant_a, phone="9000001002")
    product = make_product(tenant_a.company, name="Linked product", sku="LNK-1")
    made = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{deal.id}/lines/",
        {"product": product.id, "quantity": "1", "unit_price": "100"}, format="json",
    )
    # A won deal is closed; lines go on before it closes, so give the draft its own items.
    assert made.status_code in (201, 400)
    resp = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{deal.id}/draft-invoice/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}]},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert SalesInvoice.objects.get(pk=_body(resp)["id"]).opportunity_id == deal.id


def test_funnel_counts_convert_won_deals_and_names_the_campaign(tenant_a):
    _flags(tenant_a.company)
    campaign = Campaign.objects.create(
        company=tenant_a.company, name="Diwali push", campaign_type=Campaign.Type.DIGITAL,
        status=Campaign.Status.ACTIVE, budget=Decimal("500"), created_by=tenant_a.owner,
    )
    _lead, deal = _won_deal(tenant_a, phone="9000001003", campaign=campaign.id)
    _completed_invoice(tenant_a, deal.customer, "1000", opportunity_id=deal.id)
    resp = tenant_a.client.get(f"/api/v1/crm/campaigns/{campaign.id}/funnel/")
    assert resp.status_code == 200, resp.data
    body = _body(resp)
    assert Decimal(body["revenue"]) == Decimal("1000.00")
    assert body["campaign_name"] == "Diwali push"
    assert "before GST" in body["roi_basis"]
    assert body["rows"][0]["title"] == deal.title
    assert body["roi_ratio"] == "2.0000"


def test_revenue_for_many_deals_uses_a_fixed_number_of_queries(tenant_a, django_assert_max_num_queries):
    _flags(tenant_a.company)
    deals = [_won_deal(tenant_a, phone=f"90000020{n:02d}")[1] for n in range(6)]
    with django_assert_max_num_queries(8):
        figures = revenue_by_opportunity(tenant_a.company.id, [d.id for d in deals])
    assert len(figures) == 6


def test_backfill_links_chain_invoices_and_dry_run_writes_nothing(tenant_a):
    from .test_quotation_plan_phases import _make_quote, _won_opportunity

    _flags(tenant_a.company)
    cust = make_customer(tenant_a.company)
    opp = _won_opportunity(tenant_a, cust)
    from sales.models import Quotation

    quote = _make_quote(tenant_a, cust, make_product(tenant_a.company))
    Quotation.objects.filter(pk=quote["id"]).update(opportunity=opp)
    r = tenant_a.client.post(f"/api/v1/sales/quotations/{quote['id']}/convert/", {}, format="json")
    assert r.status_code == 200, r.data
    invoice_id = r.data["id"]
    assert SalesInvoice.objects.get(pk=invoice_id).opportunity_id == opp.id  # set at conversion
    SalesInvoice.objects.filter(pk=invoice_id).update(opportunity=None)
    call_command("backfill_invoice_opportunity")
    assert SalesInvoice.objects.get(pk=invoice_id).opportunity_id is None
    call_command("backfill_invoice_opportunity", "--apply")
    assert SalesInvoice.objects.get(pk=invoice_id).opportunity_id == opp.id


def test_campaign_with_leads_cannot_be_deleted_and_paused_ones_take_no_leads(tenant_a):
    _flags(tenant_a.company)
    active = Campaign.objects.create(
        company=tenant_a.company, name="Live", campaign_type=Campaign.Type.EVENT,
        status=Campaign.Status.ACTIVE, created_by=tenant_a.owner,
    )
    capture_lead(tenant_a.company, tenant_a.owner, name="Attached", phone="9000001004", campaign=active.id)
    blocked = tenant_a.client.delete(f"/api/v1/crm/campaigns/{active.id}/")
    assert blocked.status_code == 400
    assert "1 lead" in str(blocked.data)
    assert Campaign.objects.filter(pk=active.pk).exists()
    empty = Campaign.objects.create(
        company=tenant_a.company, name="Empty", campaign_type=Campaign.Type.EVENT, created_by=tenant_a.owner,
    )
    assert tenant_a.client.delete(f"/api/v1/crm/campaigns/{empty.id}/").status_code == 204
    done = Campaign.objects.create(
        company=tenant_a.company, name="Done", campaign_type=Campaign.Type.EVENT,
        status=Campaign.Status.COMPLETED, created_by=tenant_a.owner,
    )
    lead = capture_lead(tenant_a.company, tenant_a.owner, name="Late", phone="9000001005")
    refused = tenant_a.client.patch(f"/api/v1/crm/leads/{lead.id}/", {"campaign": done.id}, format="json")
    assert refused.status_code == 400


def test_customer_360_splits_open_from_won_and_ignores_lost(tenant_a):
    from insights.customer_360 import customer_360

    _flags(tenant_a.company, ENABLE_CUSTOMER_360=True)
    customer = make_customer(tenant_a.company)
    for title, amount, stage in (("o", "10", "OPEN"), ("w", "20", "WON"), ("l", "40", "LOST")):
        Opportunity.objects.create(
            company=tenant_a.company, customer=customer, title=title, amount=Decimal(amount),
            stage=stage, created_by=tenant_a.owner,
        )
    body = customer_360(tenant_a.company, customer)
    assert (body["open_pipeline_total"], body["won_total"], body["opportunity_total"]) == ("10.00", "20.00", "30.00")


def test_growth_metrics_counts_leads_with_a_deal_as_converted(tenant_a):
    from insights.growth_metrics import growth_metrics

    _flags(tenant_a.company)
    _won_deal(tenant_a, phone="9000001006")
    capture_lead(tenant_a.company, tenant_a.owner, name="Cold", phone="9000001007")
    metrics = growth_metrics(tenant_a.company)
    assert metrics["leads"] == 2 and metrics["leads_converted"] == 1


# ------------------------------------------------------------------ WP-4: referral rewards


def test_percent_reward_has_no_amount_until_paid_and_refuses_before_an_invoice(tenant_a):
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Referrer B")
    _completed_invoice(tenant_a, referrer, "500")
    code = _issue_code(tenant_a, referrer, "PERCENT", "10")
    _lead, deal = _won_deal(tenant_a, phone="9000001010", referral_code=code)
    reward = ReferralReward.objects.get(opportunity=deal)
    assert reward.basis == "PERCENT" and reward.reward_amount == Decimal("0.00")
    assert tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/").status_code == 200
    early = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert early.status_code == 400 and "No completed invoice" in str(early.data)
    reward.refresh_from_db()
    assert reward.reward_status == ReferralReward.Status.APPROVED
    _completed_invoice(tenant_a, deal.customer, "1000", opportunity_id=deal.id)
    paid = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert paid.status_code == 200, paid.data
    again = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert again.status_code == 200
    reward.refresh_from_db()
    assert reward.reward_amount == Decimal("100.00") and reward.reward_status == ReferralReward.Status.PAID
    assert SalesCreditNote.objects.filter(reason_detail=f"Referral reward {reward.id}").count() == 1


def test_reward_for_someone_who_was_already_a_customer_is_flagged_not_rejected(tenant_a):
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Referrer C")
    code = _issue_code(tenant_a, referrer, "FLAT", "40")
    existing = make_customer(tenant_a.company, name="Old Customer", phone="9000001011")
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Old Customer", phone="9000001099", referral_code=code,
    )
    Lead.objects.filter(pk=lead.pk).update(customer=existing)
    opp = Opportunity.objects.create(
        company=tenant_a.company, lead=lead, customer=existing, title="Repeat", amount=Decimal("100"),
        stage=Opportunity.Stage.OPEN, created_by=tenant_a.owner,
    )
    resp = tenant_a.client.patch(f"/api/v1/crm/opportunities/{opp.id}/", {"stage": "WON"}, format="json")
    assert resp.status_code == 200, resp.data
    reward = ReferralReward.objects.get(opportunity=opp)
    assert reward.review_note == "existing_customer"
    assert reward.reward_status == ReferralReward.Status.PENDING


def test_deactivating_a_code_stops_new_leads_from_earning(tenant_a):
    _flags(tenant_a.company)
    _staff_can_sell(tenant_a)
    referrer = make_customer(tenant_a.company, name="Referrer D")
    code = _issue_code(tenant_a, referrer, "FLAT", "40")
    row = ReferralCode.objects.get(code=code)
    assert tenant_a.staff_client.post(f"/api/v1/crm/referrals/codes/{row.id}/deactivate/").status_code == 403
    done = tenant_a.client.post(f"/api/v1/crm/referrals/codes/{row.id}/deactivate/")
    assert done.status_code == 200 and _body(done)["active"] is False
    lead = capture_lead(tenant_a.company, tenant_a.owner, name="After", phone="9000001012", referral_code=code)
    assert lead.referral_code_id is None
    listed = tenant_a.client.get("/api/v1/crm/referrals/codes/")
    assert listed.status_code == 200
    first = listed.data["results"][0]
    assert first["referrer_name"] == "Referrer D" and first["active"] is False


def test_only_owner_or_manager_issue_codes_and_only_the_owner_exceeds_the_flat_cap(tenant_a):
    _flags(tenant_a.company)
    _staff_can_sell(tenant_a)
    referrer = make_customer(tenant_a.company, name="Referrer E")
    body = {"referrer_customer": referrer.id, "reward_type": "FLAT", "reward_value": "50000"}
    assert tenant_a.staff_client.post("/api/v1/crm/referrals/codes/issue/", body, format="json").status_code == 403
    assert tenant_a.client.post("/api/v1/crm/referrals/codes/issue/", body, format="json").status_code == 201
    manager_user = CompanyUser.objects.filter(company=tenant_a.company, user=tenant_a.owner).first()
    assert manager_user.role == CompanyUser.Role.OWNER
    from crm.referrals import issue_referral_code
    from core.exceptions import BusinessRuleError

    with pytest.raises(BusinessRuleError):
        issue_referral_code(tenant_a.company, tenant_a.owner, referrer_customer=referrer, reward_value="10001")


def test_rewards_list_carries_names_and_a_hand_made_note_for_a_reward_is_refused(tenant_a):
    from rest_framework.test import APIRequestFactory

    from sales.phase1_serializers import SalesCreditNoteSerializer
    from rest_framework import serializers as drf

    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Referrer F")
    code = _issue_code(tenant_a, referrer, "FLAT", "40")
    _lead, deal = _won_deal(tenant_a, phone="9000001013", referral_code=code)
    reward = ReferralReward.objects.get(opportunity=deal)
    listed = tenant_a.client.get("/api/v1/crm/referrals/rewards/")
    row = listed.data["results"][0]
    assert row["referrer_name"] == "Referrer F" and row["customer_name"] and row["code"] == code
    request = APIRequestFactory().post("/x")
    request.user = tenant_a.owner
    serializer = SalesCreditNoteSerializer(context={"request": request})
    with pytest.raises(drf.ValidationError):
        serializer._reject_referral_reward_duplicate({"reason_detail": f"Referral reward {reward.id}"})
    serializer._reject_referral_reward_duplicate({"reason_detail": "Referral reward 999999"})


# ------------------------------------------------------------------ WP-3: dedupe and lifecycle


def _pending_review(tenant, phone="9000001100"):
    existing = make_customer(tenant.company, name="Known Buyer", phone=phone)
    lead = capture_lead(
        tenant.company, tenant.owner, name="Maybe Known", phone=phone, manual=True, dedupe_decision="review",
    )
    assert lead.dedupe_review == "PENDING_REVIEW"
    return existing, lead


def test_convert_is_blocked_until_the_duplicate_review_is_resolved(tenant_a):
    _flags(tenant_a.company)
    _existing, lead = _pending_review(tenant_a)
    blocked = tenant_a.client.post(f"/api/v1/crm/leads/{lead.id}/convert/", {}, format="json")
    assert blocked.status_code == 400 and "duplicate review" in str(blocked.data)
    details = tenant_a.client.get(f"/api/v1/crm/leads/{lead.id}/dedupe-candidates/")
    assert details.status_code == 200
    assert _body(details)["customers"][0]["name"] == "Known Buyer"


def test_same_customer_links_the_customer(tenant_a):
    _flags(tenant_a.company)
    existing, lead = _pending_review(tenant_a, "9000001101")
    resp = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/resolve-dedupe/", {"decision": "same_customer"}, format="json",
    )
    assert resp.status_code == 200, resp.data
    lead.refresh_from_db()
    assert lead.customer_id == existing.id and lead.dedupe_review == ""


def test_different_person_is_remembered_and_convert_does_not_relink(tenant_a):
    _flags(tenant_a.company)
    existing, lead = _pending_review(tenant_a, "9000001102")
    resp = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/resolve-dedupe/", {"decision": "different"}, format="json",
    )
    assert resp.status_code == 200, resp.data
    lead.refresh_from_db()
    assert lead.dedupe_decision == "different"
    converted = tenant_a.client.post(f"/api/v1/crm/leads/{lead.id}/convert/", {}, format="json")
    lead.refresh_from_db()
    # Either a fresh customer was made, or the customer rules refused the shared phone; never a silent relink.
    assert lead.customer_id != existing.id
    assert converted.status_code in (200, 400)


def test_same_lead_closes_the_new_one_as_a_duplicate_and_moves_its_notes(tenant_a):
    _flags(tenant_a.company)
    first = capture_lead(tenant_a.company, tenant_a.owner, name="First", phone="9000001103")
    second = capture_lead(
        tenant_a.company, tenant_a.owner, name="First Again", phone="9000001103", message="Wants a quote",
        manual=True, dedupe_decision="review",
    )
    resp = tenant_a.client.post(
        f"/api/v1/crm/leads/{second.id}/resolve-dedupe/", {"decision": "same_lead"}, format="json",
    )
    assert resp.status_code == 200, resp.data
    second.refresh_from_db()
    assert second.status == Lead.Status.LOST and second.lost_reason == "DUPLICATE"
    assert second.duplicate_of_id == first.id and second.assigned_to_id is None
    assert LeadActivity.objects.filter(lead=first, body__contains="Wants a quote").exists()


def test_lead_status_source_gstin_and_lost_reason_are_validated(tenant_a):
    _flags(tenant_a.company)
    lead = capture_lead(tenant_a.company, tenant_a.owner, name="Val", phone="9000001104")
    url = f"/api/v1/crm/leads/{lead.id}/"
    assert tenant_a.client.patch(url, {"status": "WHATEVER"}, format="json").status_code == 400
    assert tenant_a.client.patch(url, {"source": "carrier_pigeon"}, format="json").status_code == 400
    assert tenant_a.client.patch(url, {"gstin": "123"}, format="json").status_code == 400
    assert tenant_a.client.patch(url, {"status": "QUALIFIED"}, format="json").status_code == 400
    assert tenant_a.client.patch(url, {"status": "LOST"}, format="json").status_code == 400
    ok = tenant_a.client.patch(url, {"status": "LOST", "lost_reason": "PRICE"}, format="json")
    assert ok.status_code == 200, ok.data
    reopened = tenant_a.client.patch(url, {"status": "CONTACTED"}, format="json")
    assert reopened.status_code == 200
    lead.refresh_from_db()
    assert lead.lost_reason == ""
    bad = tenant_a.client.post(
        "/api/v1/crm/leads/", {"name": "Bad", "phone": "9000001105", "status": "NOPE"}, format="json",
    )
    assert bad.status_code == 400
    assert not Lead.objects.filter(phone="+919000001105").exists()


def test_first_call_marks_contacted_and_activity_refreshes_last_touched(tenant_a):
    _flags(tenant_a.company)
    lead = capture_lead(tenant_a.company, tenant_a.owner, name="Touch", phone="9000001106")
    Lead.objects.filter(pk=lead.pk).update(last_touched_at=None)
    note = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/activities/", {"kind": "NOTE", "body": "thinking"}, format="json",
    )
    assert note.status_code == 201
    lead.refresh_from_db()
    assert lead.status == Lead.Status.NEW and lead.last_touched_at is not None
    before = lead.last_touched_at
    call = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/activities/", {"kind": "CALL", "body": "spoke"}, format="json",
    )
    assert call.status_code == 201 and _body(call)["created_by_name"]
    lead.refresh_from_db()
    assert lead.status == Lead.Status.CONTACTED and lead.last_touched_at >= before


def test_assign_is_limited_to_owner_manager_or_the_current_assignee(tenant_a):
    _flags(tenant_a.company)
    _staff_can_sell(tenant_a)
    staff = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    owner = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.owner)
    lead = capture_lead(tenant_a.company, tenant_a.owner, name="Assign", phone="9000001107")
    Lead.objects.filter(pk=lead.pk).update(assigned_to=owner)
    url = f"/api/v1/crm/leads/{lead.id}/assign/"
    assert tenant_a.staff_client.post(url, {"assigned_to": staff.id}, format="json").status_code == 403
    assert tenant_a.client.post(url, {"assigned_to": staff.id}, format="json").status_code == 200
    # Now the staff member holds it: they may hand it on but not unassign it.
    assert tenant_a.staff_client.post(url, {"assigned_to": None}, format="json").status_code == 403
    last = tenant_a.staff_client.post(url, {"assigned_to": owner.id}, format="json")
    assert last.status_code == 200, last.data


def test_onboarding_needs_state_and_counts_a_deal_closed_from_a_lead(tenant_a):
    _flags(tenant_a.company)
    company = tenant_a.company
    company.state = ""
    company.save(update_fields=["state"])
    steps = {s["id"]: s["done"] for s in _body(tenant_a.client.get("/api/v1/crm/onboarding/"))["steps"]}
    assert steps["company"] is False and steps["stage"] is False
    company.state = "Karnataka"
    company.gstin = company.gstin or "29AAAAA0000A1ZY"
    company.save(update_fields=["state", "gstin"])
    _won_deal(tenant_a, phone="9000001108")
    steps = {s["id"]: s["done"] for s in _body(tenant_a.client.get("/api/v1/crm/onboarding/"))["steps"]}
    assert steps["company"] is True and steps["stage"] is True


def test_no_sales_staff_routes_new_leads_to_the_owner(tenant_a):
    _flags(tenant_a.company)
    CompanyUser.objects.filter(company=tenant_a.company, role=CompanyUser.Role.SALES_STAFF).update(is_active=False)
    lead = capture_lead(tenant_a.company, tenant_a.owner, name="To owner", phone="9000001109")
    assert lead.assigned_to.role == CompanyUser.Role.OWNER


# ------------------------------------------------------------------ WP-7: capture hardening


def test_csv_parser_handles_cp1252_aliases_and_limits():
    from core.exceptions import BusinessRuleError
    from crm.pipeline import CSV_MAX_ROWS, parse_lead_csv

    raw = "Full Name,Mobile Number,Email Id,State\nJosé Müller,9000001200,j@x.test,Karnataka\n".encode("cp1252")
    rows = parse_lead_csv(raw)
    assert rows == [{"name": "José Müller", "phone": "9000001200", "email": "j@x.test", "state": "Karnataka"}]
    with pytest.raises(BusinessRuleError):
        parse_lead_csv(b"phone\n9000001201\n")
    with pytest.raises(BusinessRuleError):
        parse_lead_csv(b"x" * (2 * 1024 * 1024 + 1))
    many = "name,phone\n" + "".join(f"n{i},90000{i:05d}\n" for i in range(CSV_MAX_ROWS + 1))
    with pytest.raises(BusinessRuleError):
        parse_lead_csv(many.encode())


def test_csv_import_reports_row_errors_and_purges_the_rows(tenant_a):
    from django.core.files.uploadedfile import SimpleUploadedFile

    _flags(tenant_a.company)
    csv_bytes = "name,phone,gstin\nGood,9000001210,\nBad,9000001211,NOT-A-GSTIN\n".encode("utf-8")
    resp = tenant_a.client.post(
        "/api/v1/crm/leads/import-csv/", {"file": SimpleUploadedFile("l.csv", csv_bytes, "text/csv")},
        format="multipart",
    )
    assert resp.status_code == 202, resp.data
    job = LeadIngestJob.objects.get(pk=_body(resp)["id"])
    assert job.status == LeadIngestJob.Status.DONE
    assert job.result["created"] == 1 and job.result["error_count"] == 1
    assert job.result["errors"][0]["row"] == 2 and "GSTIN" in job.result["errors"][0]["detail"]
    assert job.payload == {}


def test_an_unexpected_error_marks_the_job_failed_not_running(tenant_a, monkeypatch):
    from crm import pipeline
    from crm.tasks import process_lead_ingest

    _flags(tenant_a.company)
    job = LeadIngestJob.objects.create(
        company=tenant_a.company, kind=LeadIngestJob.Kind.CSV, payload={"rows": [{"name": "x"}]},
        created_by=tenant_a.owner,
    )

    def boom(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(pipeline, "import_lead_rows", boom)
    process_lead_ingest(job.id, company_id=tenant_a.company.id)
    job.refresh_from_db()
    assert job.status == LeadIngestJob.Status.FAILED and "unexpectedly" in job.error
    assert "database went away" not in job.error and job.payload == {}


def test_reaper_retries_a_stuck_job_once_then_fails_it(tenant_a):
    from datetime import timedelta

    from django.utils import timezone

    from crm.tasks import reap_stale_lead_ingest_jobs

    _flags(tenant_a.company)
    job = LeadIngestJob.objects.create(
        company=tenant_a.company, kind=LeadIngestJob.Kind.WHATSAPP, status=LeadIngestJob.Status.RUNNING,
        payload={"message_id": "stuck-1", "sender": "9000001220", "text": "hi"},
    )
    old = timezone.now() - timedelta(minutes=30)
    LeadIngestJob.objects.filter(pk=job.pk).update(updated_at=old)
    assert reap_stale_lead_ingest_jobs() == {"retried": 1, "failed": 0}
    job.refresh_from_db()
    assert job.status in (LeadIngestJob.Status.DONE, LeadIngestJob.Status.PENDING, LeadIngestJob.Status.RUNNING)
    LeadIngestJob.objects.filter(pk=job.pk).update(
        status=LeadIngestJob.Status.RUNNING, updated_at=old, payload={"_retries": 1},
    )
    assert reap_stale_lead_ingest_jobs() == {"retried": 0, "failed": 1}
    job.refresh_from_db()
    assert job.status == LeadIngestJob.Status.FAILED


META_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp",
        "contacts": [{"profile": {"name": "Meera Nair"}, "wa_id": "919000001230"}],
        "messages": [{"from": "919000001230", "id": "wamid.ABC", "timestamp": "1700000000",
                      "type": "text", "text": {"body": "Price for 10 units?"}}],
    }}]}],
}


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@override_settings(ENABLE_CRM=True, ENABLE_CRM_WHATSAPP_INBOUND=True, WHATSAPP_APP_SECRET="server-secret")
def test_meta_payload_is_parsed_and_each_company_signs_with_its_own_secret(tenant_a):
    from .test_os_vision_plan import _enable

    _enable(tenant_a.company, "ENABLE_CRM", "ENABLE_CRM_WHATSAPP_INBOUND")
    _staff_can_sell(tenant_a)
    issued = tenant_a.client.post("/api/v1/crm/leads/whatsapp-token/", {}, format="json")
    token = _body(issued)["token"]
    assert _body(issued)["secret_configured"] is False
    saved = tenant_a.client.post("/api/v1/crm/leads/whatsapp-secret/", {"app_secret": "company-secret"}, format="json")
    assert saved.status_code == 200 and "company-secret" not in json.dumps(saved.data)
    assert tenant_a.staff_client.post(
        "/api/v1/crm/leads/whatsapp-secret/", {"app_secret": "x" * 12}, format="json",
    ).status_code == 403
    tenant_a.company.refresh_from_db()
    assert "company-secret" not in tenant_a.company.whatsapp_app_secret
    raw = json.dumps(META_PAYLOAD).encode()
    url = f"/api/v1/crm/public/whatsapp/{token}/"
    wrong = tenant_a.client.generic(
        "POST", url, raw, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=_sign(raw, "server-secret"),
    )
    assert wrong.status_code == 403  # the server-wide secret no longer applies once the company has its own
    good = tenant_a.client.generic(
        "POST", url, raw, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=_sign(raw, "company-secret"),
    )
    assert good.status_code == 200, good.content
    lead = Lead.objects.get(company=tenant_a.company, source="whatsapp")
    assert lead.name == "Meera Nair" and lead.message == "Price for 10 units?" and lead.phone.endswith("9000001230")
    status_only = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}).encode()
    receipt = tenant_a.client.generic(
        "POST", url, status_only, content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=_sign(status_only, "company-secret"),
    )
    assert receipt.status_code == 200 and receipt.data["received"] == 0
    assert Lead.objects.filter(company=tenant_a.company, source="whatsapp").count() == 1


def test_duplicate_whatsapp_message_id_returns_the_same_lead(tenant_a):
    from crm.pipeline import ingest_whatsapp_message

    _flags(tenant_a.company)
    first = ingest_whatsapp_message(tenant_a.company, message_id="dup-1", sender="9000001240", text="a", sent_at="1")
    second = ingest_whatsapp_message(tenant_a.company, message_id="dup-1", sender="9000001240", text="a", sent_at="1")
    assert first.id == second.id


def test_public_form_meta_signed_campaign_rotation_and_daily_cap(tenant_a):
    from crm.pipeline import sign_campaign, unsign_campaign

    _flags(tenant_a.company)
    _staff_can_sell(tenant_a)
    campaign = Campaign.objects.create(
        company=tenant_a.company, name="Link push", campaign_type=Campaign.Type.DIGITAL,
        status=Campaign.Status.ACTIVE, created_by=tenant_a.owner,
    )
    issued = tenant_a.client.post("/api/v1/crm/leads/form-token/", {"campaign": campaign.id}, format="json")
    assert issued.status_code == 200, issued.data
    token = _body(issued)["token"]
    param = _body(issued)["campaign_param"]
    assert unsign_campaign(param) == campaign.id and unsign_campaign(param + "x") is None
    assert unsign_campaign(sign_campaign(campaign.id)) == campaign.id
    meta = tenant_a.client.get(f"/api/v1/crm/public/lead-form/{token}/")
    assert meta.status_code == 200 and _body(meta)["company_name"] == tenant_a.company.name
    assert tenant_a.company.name in _body(meta)["consent_text"]
    url = f"/api/v1/crm/public/lead-form/{token}/"
    signed = tenant_a.client.post(url, {"name": "Signed", "phone": "9000001250", "campaign": param}, format="json")
    assert signed.status_code == 202, signed.data
    assert Lead.objects.get(name="Signed").campaign_id == campaign.id
    raw_id = tenant_a.client.post(url, {"name": "Raw", "phone": "9000001251", "campaign": campaign.id}, format="json")
    assert raw_id.status_code == 202
    assert Lead.objects.get(name="Raw").campaign_id is None
    bad = tenant_a.client.post(url, {"name": "Tampered", "phone": "9000001252", "campaign": param + "x"}, format="json")
    assert bad.status_code == 202 and Lead.objects.get(name="Tampered").campaign_id is None
    with override_settings(LEAD_FORM_DAILY_CAP=3):
        capped = tenant_a.client.post(url, {"name": "Over", "phone": "9000001253"}, format="json")
    assert capped.status_code == 429
    assert tenant_a.staff_client.post("/api/v1/crm/leads/form-token/", {"rotate": True}, format="json").status_code == 403
    rotated = tenant_a.client.post("/api/v1/crm/leads/form-token/", {"rotate": True}, format="json")
    assert rotated.status_code == 200 and _body(rotated)["token"] != token
    assert tenant_a.client.get(url).status_code == 404


def test_an_approved_reward_can_be_reversed_so_the_deal_can_be_reopened(tenant_a):
    _flags(tenant_a.company)
    _staff_can_sell(tenant_a)
    referrer = make_customer(tenant_a.company, name="Referrer G")
    code = _issue_code(tenant_a, referrer, "FLAT", "40")
    _lead, deal = _won_deal(tenant_a, phone="9000001300", referral_code=code)
    reward = ReferralReward.objects.get(opportunity=deal)
    assert tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/").status_code == 200
    assert tenant_a.client.post(f"/api/v1/crm/opportunities/{deal.id}/reopen/").status_code == 400
    assert tenant_a.staff_client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/reverse/").status_code == 403
    done = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/reverse/")
    assert done.status_code == 200, done.data
    reward.refresh_from_db()
    assert reward.reward_status == ReferralReward.Status.REJECTED and reward.rejection_reason == "reversed"
    assert tenant_a.client.post(f"/api/v1/crm/opportunities/{deal.id}/reopen/").status_code == 200
