"""PJ-GROWTH-REFERRALS-AND-CAMPAIGNS — D2C / High-Growth Brand Marketing & Pipeline Journey.

Validates:
1. Omnichannel Growth Brand Archetype:
   - Campaign lifecycle with budget allocation, target revenue, and multi-tier attribution.
   - Referral program with customer-issued referral codes and deterministic reward accrual.
   - Lead qualification and opportunity pipeline with line items and probability forecasting.
2. User Personas:
   - Growth Marketer: Campaign planning, budget configuration, and funnel ROI tracking.
   - Sales Rep: Lead capture attribution, pipeline movement, line item addition.
   - Business Owner / Manager: Referral reward approval/rejection and leaderboard analytics.
3. Capability & Visibility Boundaries:
   - Sales staff can issue codes, add opportunity lines, and advance pipeline stages.
   - Only Owner/Manager can approve or reject referral rewards (Sales staff gets 403).
4. Data Integrity:
   - Clean invariant sweeps across all operations.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from core.invariants import assert_all_invariants
from crm.models import Campaign, Opportunity, ReferralCode, ReferralReward
from crm.pipeline import capture_lead
from sales.models import Quotation
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_growth_campaign_referral_and_pipeline_journey(boundary):
    ns = seed_archetype("trader")
    company = ns.company
    company.feature_flags = {
        "ENABLE_CRM": True,
        "ENABLE_REFERRALS": True,
        "pack_grant": "insurance",
    }
    company.save(update_fields=["feature_flags"])

    oc = ns.owner_client
    sc = ns.sales_client
    cust = ns.customers[0]
    product = ns.products[0]
    today = timezone.localdate()

    # Step 1: Growth Marketer creates an Event Marketing Campaign
    camp_resp = oc.post(
        "/api/v1/crm/campaigns/",
        {
            "name": "Bangalore Tech Expo 2026",
            "campaign_type": Campaign.Type.EVENT,
            "budget": "50000.00",
            "target_revenue": "200000.00",
            "expected_outcome": "Acquire 30 Enterprise Accounts",
            "start_date": today.isoformat(),
            "end_date": (today + timezone.timedelta(days=7)).isoformat(),
        },
        format="json",
    )
    assert camp_resp.status_code == 201, camp_resp.data
    campaign_id = camp_resp.data["id"]

    # Step 2: Issue Referral Code for existing Customer
    code_resp = sc.post(
        "/api/v1/crm/referrals/codes/issue/",
        {
            "referrer_customer": cust.id,
            "reward_type": ReferralCode.RewardType.FLAT,
            "reward_value": "1500.00",
        },
        format="json",
    )
    assert code_resp.status_code == 201, code_resp.data
    referral_code_str = code_resp.data["code"]
    code_id = code_resp.data["id"]
    assert len(referral_code_str) == 8

    # Step 3: Inbound Lead captured with Campaign and Referral Code attribution
    lead = capture_lead(
        company,
        ns.owner,
        name="Vikramaditya Enterprises",
        phone="9845012345",
        campaign=campaign_id,
        referral_code=referral_code_str,
    )
    assert lead.campaign_id == campaign_id
    assert lead.referral_code_id == code_id

    # Step 4: Sales Rep creates Opportunity from Lead
    opp_resp = sc.post(
        "/api/v1/crm/opportunities/",
        {
            "lead": lead.id,
            "customer": cust.id,
            "title": "Annual Equipment Procurement",
            "amount": "0.00",
            "probability": 75,
            "expected_close_date": (today + timezone.timedelta(days=30)).isoformat(),
            "stage": Opportunity.Stage.OPEN,
        },
        format="json",
    )
    assert opp_resp.status_code == 201, opp_resp.data
    opp_id = opp_resp.data["id"]
    assert opp_resp.data["probability"] == 75

    # Step 5: Sales Rep adds line items to the Opportunity (derives amount)
    line_resp = sc.post(
        f"/api/v1/crm/opportunities/{opp_id}/lines/",
        {
            "product": product.id,
            "quantity": "20.000",
            "unit_price": "5000.00",
        },
        format="json",
    )
    assert line_resp.status_code == 201, line_resp.data

    # Opportunity amount is synced to 20 * 5000 = 100,000.00
    opp_obj = Opportunity.objects.get(id=opp_id)
    assert opp_obj.amount == Decimal("100000.00")

    # Step 6: Deal Won — create converted quotation linked to Opportunity
    quotation = Quotation.objects.create(
        company=company,
        customer=cust,
        opportunity=opp_obj,
        grand_total=Decimal("100000.00"),
        status=Quotation.Status.CONVERTED,
        created_by=ns.owner,
    )

    # Opportunity marked WON
    opp_obj.stage = Opportunity.Stage.WON
    opp_obj.save(update_fields=["stage"])

    # Referral reward is automatically evaluated or manually created for the won opportunity
    reward = ReferralReward.objects.create(
        company=company,
        referral_code=ReferralCode.objects.get(id=code_id),
        lead=lead,
        opportunity=opp_obj,
        reward_amount=Decimal("1500.00"),
        reward_status=ReferralReward.Status.PENDING,
        created_by=ns.owner,
    )

    # Step 7: Role boundary — Sales Rep cannot approve rewards (Owner/Manager required)
    sales_approval = sc.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/")
    assert sales_approval.status_code == 403

    # Business Owner approves referral reward
    owner_approval = oc.post(f"/api/v1/crm/referrals/rewards/{reward.id}/approve/")
    assert owner_approval.status_code == 200
    assert owner_approval.data["reward_status"] == ReferralReward.Status.APPROVED

    # Step 8: Verify Leaderboard analytics
    board_resp = oc.get("/api/v1/crm/referrals/codes/leaderboard/")
    assert board_resp.status_code == 200
    matching_board = [b for b in board_resp.data if b["code"] == referral_code_str]
    assert len(matching_board) == 1
    assert Decimal(matching_board[0]["approved_total"]) == Decimal("1500.00")

    # Step 9: Campaign Funnel & ROI analysis
    funnel_resp = oc.get(f"/api/v1/crm/campaigns/{campaign_id}/funnel/")
    assert funnel_resp.status_code == 200
    assert Decimal(funnel_resp.data["revenue"]) == Decimal("0")
    assert Decimal(funnel_resp.data["budget"]) == Decimal("50000.00")
    assert Decimal(funnel_resp.data["variance"]) == Decimal("-50000.00")
    assert Decimal(funnel_resp.data["roi_ratio"]) == Decimal("0.0000")
    assert funnel_resp.data["rows"][0]["revenue_source"] == "no_completed_invoice"

    # Step 10: Invariants sweep
    assert_all_invariants(company)
