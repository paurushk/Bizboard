"""CRM review (docs/plans/CRM_REVIEW_FIX_PLAN.md): repro tests for F-01, F-02, F-03, F-18.

Each test asserts the CORRECT behaviour, so each one FAILS until its fix lands.
They are the starting tests for PR-A (F-02, F-03, F-18) and PR-B (F-01).
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from crm.models import Opportunity, ReferralReward
from crm.pipeline import capture_lead
from masters.models import Product

from .conftest import create_draft_invoice, make_customer, make_product
from .test_growth_os import _flags

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def _completed_invoice(tenant, customer, amount):
    from sales.models import SalesInvoice
    from sales.services import SalesService

    product = make_product(
        tenant.company,
        sku=f"CRM-REPRO-{customer.id}",
        product_type=Product.ProductType.SERVICE,
    )
    inv = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": amount, "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    SalesService.complete(invoice, tenant.owner)
    return invoice


def _issue_code(tenant, referrer, reward_type, value):
    resp = tenant.client.post(
        "/api/v1/crm/referrals/codes/issue/",
        {"referrer_customer": referrer.id, "reward_type": reward_type, "reward_value": value},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return resp.data["code"]


def test_f02_convert_won_with_no_amount_or_lines_is_refused(tenant_a):
    """F-02: a won deal with amount 0 and no lines must not close and must not earn a reward."""
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Referrer F02")
    code = _issue_code(tenant_a, referrer, "FLAT", "40")
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Referred F02", phone="9000000302", referral_code=code,
    )
    resp = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/", {"won": True, "amount": "0"}, format="json",
    )
    assert resp.status_code == 400, f"convert-won with amount 0 returned {resp.status_code}"
    assert not Opportunity.objects.filter(lead=lead, stage=Opportunity.Stage.WON).exists()
    assert not ReferralReward.objects.filter(lead=lead).exists()


def test_f03_editing_title_of_deal_with_lines_succeeds(tenant_a):
    """F-03: the Opportunities edit dialog always sends amount; that must not 400 when unchanged."""
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company, name="Buyer F03")
    product = make_product(tenant_a.company, sku="CRM-F03")
    created = tenant_a.client.post(
        "/api/v1/crm/opportunities/",
        {"title": "Deal F03", "amount": "0", "stage": "OPEN", "customer": customer.id},
        format="json",
    )
    assert created.status_code == 201, created.data
    opp_id = _body(created)["id"]
    line = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{opp_id}/lines/",
        {"product": product.id, "quantity": "2", "unit_price": "50"},
        format="json",
    )
    assert line.status_code == 201, line.data
    current = Opportunity.objects.get(pk=opp_id)
    assert str(current.amount) == "100.00"
    # Exactly what OpportunitiesPage.saveMutation sends for an edit.
    resp = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opp_id}/",
        {
            "title": "Deal F03 renamed",
            "amount": "100.00",
            "stage": "OPEN",
            "lead": None,
            "customer": customer.id,
            "competitor": "",
        },
        format="json",
    )
    assert resp.status_code == 200, f"{resp.status_code}: {resp.data}"
    assert Opportunity.objects.get(pk=opp_id).title == "Deal F03 renamed"


def test_f18_expired_subscription_blocks_opportunity_writes(tenant_a):
    """F-18: OpportunityViewSet.get_permissions drops SubscriptionWritesAllowed. Leads is the control."""
    from billing.models import Subscription

    from .test_sprint_d_saas_billing import _plan

    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company, name="Buyer F18")
    created = tenant_a.client.post(
        "/api/v1/crm/opportunities/",
        {"title": "Deal F18", "amount": "10", "stage": "OPEN", "customer": customer.id},
        format="json",
    )
    assert created.status_code == 201, created.data
    opp_id = _body(created)["id"]
    lead = capture_lead(tenant_a.company, tenant_a.owner, name="Lead F18", phone="9000000318")

    Subscription.objects.create(
        company=tenant_a.company,
        plan=_plan(slug="crm-f18"),
        status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() - timedelta(days=1),
    )

    control = tenant_a.client.patch(f"/api/v1/crm/leads/{lead.id}/", {"name": "Renamed"}, format="json")
    assert control.status_code == 403, f"control (lead PATCH) returned {control.status_code}"

    patched = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opp_id}/", {"title": "Edited while expired"}, format="json",
    )
    assert patched.status_code == 403, f"opportunity PATCH returned {patched.status_code}"
    posted = tenant_a.client.post(
        "/api/v1/crm/opportunities/",
        {"title": "New while expired", "amount": "1", "stage": "OPEN"},
        format="json",
    )
    assert posted.status_code == 403, f"opportunity POST returned {posted.status_code}"


def test_f01_percent_reward_is_payable_after_the_deal_is_invoiced(tenant_a):
    """F-01: PERCENT reward is 10% of billed value. WON happens before billing, so it must be set at pay time."""
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Referrer F01")
    _completed_invoice(tenant_a, referrer, "500")  # headroom for the reward credit note
    code = _issue_code(tenant_a, referrer, "PERCENT", "10")
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Referred F01", phone="9000000301", referral_code=code,
    )
    converted = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/", {"won": True, "amount": "1000"}, format="json",
    )
    assert converted.status_code == 200, converted.data
    opp_id = converted.data["opportunity"]["id"]
    customer = Opportunity.objects.get(pk=opp_id).customer
    _completed_invoice(tenant_a, customer, "1000")

    reward = ReferralReward.objects.get(opportunity_id=opp_id)
    assert tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/").status_code == 200
    paid = tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/mark-paid/")
    assert paid.status_code == 200, f"mark-paid returned {paid.status_code}: {paid.data}"
    reward.refresh_from_db()
    assert reward.reward_status == ReferralReward.Status.PAID
    assert str(reward.reward_amount) == "100.00", f"reward_amount={reward.reward_amount}"


# ---- PR-A (WP-1 / WP-2) behaviour that goes beyond the four repros ---------------------


def _won_deal(tenant, *, with_code=False, amount="100"):
    referrer = make_customer(tenant.company, name="Referrer PRA")
    body = {"name": "Lead PRA", "phone": "9000000777"}
    if with_code:
        body["referral_code"] = _issue_code(tenant, referrer, "FLAT", "40")
    lead = capture_lead(tenant.company, tenant.owner, name=body["name"], phone=body["phone"],
                        referral_code=body.get("referral_code", ""))
    resp = tenant.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/", {"won": True, "amount": amount}, format="json",
    )
    assert resp.status_code == 200, resp.data
    return Opportunity.objects.get(pk=resp.data["opportunity"]["id"])


def test_closed_deal_is_locked_and_its_lines_are_refused(tenant_a):
    _flags(tenant_a.company)
    opp = _won_deal(tenant_a)
    product = make_product(tenant_a.company, sku="CRM-LOCK")
    changed = tenant_a.client.patch(f"/api/v1/crm/opportunities/{opp.id}/", {"title": "Edited"}, format="json")
    assert changed.status_code == 400, changed.data
    same = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opp.id}/", {"title": opp.title, "stage": "WON"}, format="json",
    )
    assert same.status_code == 200, same.data
    note = tenant_a.client.patch(f"/api/v1/crm/opportunities/{opp.id}/", {"competitor": "Rival"}, format="json")
    assert note.status_code == 200, note.data
    line = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{opp.id}/lines/",
        {"product": product.id, "quantity": "1", "unit_price": "5"}, format="json",
    )
    assert line.status_code == 400, line.data


def test_lost_needs_a_reason_and_other_needs_a_note(tenant_a):
    _flags(tenant_a.company)
    opp = Opportunity.objects.create(company=tenant_a.company, title="Maybe", amount="50")
    url = f"/api/v1/crm/opportunities/{opp.id}/"
    assert tenant_a.client.patch(url, {"stage": "LOST"}, format="json").status_code == 400
    other = tenant_a.client.patch(url, {"stage": "LOST", "lost_reason": "OTHER"}, format="json")
    assert other.status_code == 400
    ok = tenant_a.client.patch(
        url, {"stage": "LOST", "lost_reason": "OTHER", "lost_reason_note": "Moved abroad"}, format="json",
    )
    assert ok.status_code == 200, ok.data
    opp.refresh_from_db()
    assert opp.lost_reason == "OTHER" and opp.lost_reason_note == "Moved abroad"


def test_negative_opportunity_amount_is_refused(tenant_a):
    _flags(tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/crm/opportunities/", {"title": "Neg", "amount": "-5", "stage": "OPEN"}, format="json",
    )
    assert resp.status_code == 400, resp.data


def test_reopen_is_owner_or_manager_only_and_rejects_a_pending_reward(tenant_a):
    _flags(tenant_a.company)
    opp = _won_deal(tenant_a, with_code=True)
    reward = ReferralReward.objects.get(opportunity=opp)
    assert reward.reward_status == ReferralReward.Status.PENDING
    denied = tenant_a.staff_client.post(f"/api/v1/crm/opportunities/{opp.id}/reopen/")
    assert denied.status_code == 403
    done = tenant_a.client.post(f"/api/v1/crm/opportunities/{opp.id}/reopen/")
    assert done.status_code == 200, done.data
    opp.refresh_from_db()
    reward.refresh_from_db()
    assert opp.stage == Opportunity.Stage.OPEN and opp.closed_at is None and opp.reopened_at is not None
    assert reward.reward_status == ReferralReward.Status.REJECTED
    assert reward.rejection_reason == "deal_reopened"
    again = tenant_a.client.post(f"/api/v1/crm/opportunities/{opp.id}/reopen/")
    assert again.status_code == 400


def test_reopen_is_refused_once_the_reward_is_approved(tenant_a):
    _flags(tenant_a.company)
    opp = _won_deal(tenant_a, with_code=True)
    reward = ReferralReward.objects.get(opportunity=opp)
    assert tenant_a.client.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/").status_code == 200
    blocked = tenant_a.client.post(f"/api/v1/crm/opportunities/{opp.id}/reopen/")
    assert blocked.status_code == 400, blocked.data
    opp.refresh_from_db()
    assert opp.stage == Opportunity.Stage.WON


def test_converting_an_open_deal_as_won_still_needs_an_amount(tenant_a):
    _flags(tenant_a.company)
    lead = capture_lead(tenant_a.company, tenant_a.owner, name="Open first", phone="9000000778")
    first = tenant_a.client.post(f"/api/v1/crm/leads/{lead.id}/convert/", {}, format="json")
    assert first.status_code == 200, first.data
    assert first.data["opportunity"]["stage"] == "OPEN"
    refused = tenant_a.client.post(f"/api/v1/crm/leads/{lead.id}/convert/", {"won": True}, format="json")
    assert refused.status_code == 400, refused.data
    ok = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead.id}/convert/", {"won": True, "amount": "75"}, format="json",
    )
    assert ok.status_code == 200, ok.data
    assert ok.data["opportunity"]["stage"] == "WON"
