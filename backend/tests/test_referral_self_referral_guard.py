"""Security addendum (2026-09-25) to the Growth OS Referral Engine (G5):

`crm.referrals.issue_referral_code()` had no self-referral check, and
`evaluate_referral_reward()` had no check comparing the referrer's identity
against the actual customer on the won opportunity — a referrer could issue
a code and have a "referred" lead resolve to themselves (via a different
phone/email, or the same customer record) and collect a reward for
referring themselves. There was also no rate limit on code issuance.

These tests cover the abuse scenarios the fix closes, not just the happy
path already covered by `test_growth_os.py`.
"""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.models import CompanyUser
from core.exceptions import BusinessRuleError
from core.models import AuditEvent
from crm.models import Opportunity, ReferralCode, ReferralReward
from crm.pipeline import capture_lead
from crm.referrals import DAILY_ISSUANCE_LIMIT, evaluate_referral_reward, issue_referral_code
from crm.services import convert_lead

from .conftest import make_customer


def _flags(company, **extra):
    company.feature_flags = {"ENABLE_CRM": True, "ENABLE_REFERRALS": True, **extra}
    company.save(update_fields=["feature_flags"])


def _won_opportunity(company, *, lead, customer, user, amount="100"):
    return Opportunity.objects.create(
        company=company,
        lead=lead,
        customer=customer,
        title="Deal",
        amount=Decimal(amount),
        stage=Opportunity.Stage.WON,
        created_by=user,
        updated_by=user,
    )


def test_self_referral_same_customer_id_blocks_reward(tenant_a):
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Self Referrer", phone="9111100001")
    code = issue_referral_code(
        tenant_a.company, tenant_a.owner, referrer_customer=referrer,
        reward_type="FLAT", reward_value=Decimal("50"),
    )
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Self Lead", phone="9111100099",
        referral_code=code.code,
    )
    lead.customer = referrer
    lead.save(update_fields=["customer"])
    opportunity = _won_opportunity(tenant_a.company, lead=lead, customer=referrer, user=tenant_a.owner)

    reward = evaluate_referral_reward(opportunity)

    assert reward.reward_status == ReferralReward.Status.REJECTED
    assert reward.rejection_reason == "self_referral"
    assert AuditEvent.objects.filter(
        company=tenant_a.company, action="referral_self_referral_blocked", entity_id=str(reward.id),
    ).exists()
    listed = tenant_a.client.get("/api/v1/crm/referrals/rewards/")
    assert listed.status_code == 200
    payload = listed.data
    page = payload.get("data", payload) if isinstance(payload, dict) else payload
    body = page["results"] if isinstance(page, dict) and "results" in page else page
    match = next(row for row in body if row.get("id") == reward.id)
    assert match["rejection_reason"] == "self_referral"
    rendered = json.loads(listed.content)["data"]["results"]
    wire = next(row for row in rendered if row["id"] == reward.id)
    assert wire["rejectionReason"] == "self_referral"


def test_self_referral_matching_phone_different_customer_row_blocks_reward(tenant_a):
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Referrer Phone", phone="9222200001")
    code = issue_referral_code(
        tenant_a.company, tenant_a.owner, referrer_customer=referrer,
        reward_type="FLAT", reward_value=Decimal("50"),
    )
    # A distinct Customer row, but the same phone in a different format —
    # canonicalization must still catch the match.
    referee = make_customer(tenant_a.company, name="Referrer Alt Identity", phone="+91 92222 00001")
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Phone Match Lead", phone="9222200099",
        referral_code=code.code,
    )
    lead.customer = referee
    lead.save(update_fields=["customer"])
    opportunity = _won_opportunity(tenant_a.company, lead=lead, customer=referee, user=tenant_a.owner)

    reward = evaluate_referral_reward(opportunity)

    assert reward.reward_status == ReferralReward.Status.REJECTED
    assert referrer.id != referee.id


def test_self_referral_matching_email_blocks_reward(tenant_a):
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Referrer Email", email="dup@example.test")
    code = issue_referral_code(
        tenant_a.company, tenant_a.owner, referrer_customer=referrer,
        reward_type="FLAT", reward_value=Decimal("50"),
    )
    referee = make_customer(tenant_a.company, name="Referee Same Email", email="DUP@example.test")
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Email Match Lead", phone="9333300099",
        referral_code=code.code,
    )
    lead.customer = referee
    lead.save(update_fields=["customer"])
    opportunity = _won_opportunity(tenant_a.company, lead=lead, customer=referee, user=tenant_a.owner)

    reward = evaluate_referral_reward(opportunity)

    assert reward.reward_status == ReferralReward.Status.REJECTED
    assert referrer.id != referee.id


def test_legitimate_unrelated_referral_reward_proceeds_normally(tenant_a):
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Real Referrer", phone="9444400001", email="referrer@example.test")
    code = issue_referral_code(
        tenant_a.company, tenant_a.owner, referrer_customer=referrer,
        reward_type="PERCENT", reward_value=Decimal("10"),
    )
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Real Lead", phone="9444400099",
        referral_code=code.code,
    )
    lead, opportunity, customer = convert_lead(lead, tenant_a.owner, won=True, amount="500")

    reward = ReferralReward.objects.get(company=tenant_a.company, opportunity=opportunity)
    assert reward.reward_status == ReferralReward.Status.PENDING
    assert reward.rejection_reason == ""
    assert reward.reward_amount == Decimal("50")
    assert customer.id != referrer.id
    assert not AuditEvent.objects.filter(
        company=tenant_a.company, action="referral_self_referral_blocked",
    ).exists()


def test_employee_referrer_self_referral_via_matching_login_identity(tenant_a):
    """Employee referral case: there is no CompanyUser<->Customer link in this
    schema, so the judgment call is to compare the employee's own login
    identity (accounts.User.email/phone) against the referee customer as the
    best available proxy — see crm.referrals._employee_identity_signals."""
    _flags(tenant_a.company)
    staff_membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    code = issue_referral_code(
        tenant_a.company, tenant_a.owner, referrer_user=staff_membership,
        reward_type="FLAT", reward_value=Decimal("50"),
    )
    # The referee customer's email matches the employee's own login email —
    # the employee routed a reward to "a customer" that is really themself.
    referee = make_customer(tenant_a.company, name="Staff Alter Ego", email=tenant_a.staff.email)
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Employee Self Lead", phone="9555500099",
        referral_code=code.code,
    )
    lead.customer = referee
    lead.save(update_fields=["customer"])
    opportunity = _won_opportunity(tenant_a.company, lead=lead, customer=referee, user=tenant_a.owner)

    reward = evaluate_referral_reward(opportunity)

    assert reward.reward_status == ReferralReward.Status.REJECTED


def test_employee_referrer_unrelated_customer_proceeds_normally(tenant_a):
    _flags(tenant_a.company)
    staff_membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    code = issue_referral_code(
        tenant_a.company, tenant_a.owner, referrer_user=staff_membership,
        reward_type="FLAT", reward_value=Decimal("50"),
    )
    referee = make_customer(tenant_a.company, name="Unrelated Customer", email="unrelated@example.test")
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Employee Lead", phone="9666600099",
        referral_code=code.code,
    )
    lead.customer = referee
    lead.save(update_fields=["customer"])
    opportunity = _won_opportunity(tenant_a.company, lead=lead, customer=referee, user=tenant_a.owner)

    reward = evaluate_referral_reward(opportunity)

    assert reward.reward_status == ReferralReward.Status.PENDING


def test_issuance_rate_limit_rejects_after_daily_cap(tenant_a):
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Prolific Referrer")
    for _ in range(DAILY_ISSUANCE_LIMIT):
        issue_referral_code(
            tenant_a.company, tenant_a.owner, referrer_customer=referrer,
            reward_type="FLAT", reward_value=Decimal("5"),
        )
    assert ReferralCode.objects.filter(company=tenant_a.company, referrer_customer=referrer).count() == DAILY_ISSUANCE_LIMIT

    with pytest.raises(BusinessRuleError):
        issue_referral_code(
            tenant_a.company, tenant_a.owner, referrer_customer=referrer,
            reward_type="FLAT", reward_value=Decimal("5"),
        )
    # The rejected attempt must not have minted a code.
    assert ReferralCode.objects.filter(company=tenant_a.company, referrer_customer=referrer).count() == DAILY_ISSUANCE_LIMIT


def test_issuance_rate_limit_resumes_the_next_company_local_day(tenant_a):
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Yesterday Referrer")
    for _ in range(DAILY_ISSUANCE_LIMIT):
        issue_referral_code(
            tenant_a.company, tenant_a.owner, referrer_customer=referrer,
            reward_type="FLAT", reward_value=Decimal("5"),
        )
    # Backdate every code issued "today" to yesterday so the daily window no
    # longer contains them, simulating the next company-local calendar day.
    ReferralCode.objects.filter(company=tenant_a.company, referrer_customer=referrer).update(
        created_at=timezone.now() - timedelta(days=1, hours=1)
    )
    new_code = issue_referral_code(
        tenant_a.company, tenant_a.owner, referrer_customer=referrer,
        reward_type="FLAT", reward_value=Decimal("5"),
    )
    assert new_code.id is not None


def test_issuance_rate_limit_isolated_per_tenant(tenant_a, tenant_b):
    _flags(tenant_a.company)
    _flags(tenant_b.company)
    referrer_a = make_customer(tenant_a.company, name="Tenant A Referrer")
    referrer_b = make_customer(tenant_b.company, name="Tenant B Referrer")
    for _ in range(DAILY_ISSUANCE_LIMIT):
        issue_referral_code(
            tenant_a.company, tenant_a.owner, referrer_customer=referrer_a,
            reward_type="FLAT", reward_value=Decimal("5"),
        )
    with pytest.raises(BusinessRuleError):
        issue_referral_code(
            tenant_a.company, tenant_a.owner, referrer_customer=referrer_a,
            reward_type="FLAT", reward_value=Decimal("5"),
        )
    # Company B's own referrer is unaffected by company A's exhausted cap.
    code_b = issue_referral_code(
        tenant_b.company, tenant_b.owner, referrer_customer=referrer_b,
        reward_type="FLAT", reward_value=Decimal("5"),
    )
    assert code_b.company_id == tenant_b.company.id


def test_issue_referral_code_rejects_cross_tenant_referrer_customer(tenant_a, tenant_b):
    _flags(tenant_a.company)
    other_company_customer = make_customer(tenant_b.company, name="Other Tenant Customer")
    with pytest.raises(BusinessRuleError):
        issue_referral_code(
            tenant_a.company, tenant_a.owner, referrer_customer=other_company_customer,
            reward_type="FLAT", reward_value=Decimal("5"),
        )


def test_backfill_audit_command_flags_but_never_modifies_pending_self_referrals(tenant_a, capsys):
    """Simulates a reward that was created *before* this hardening shipped —
    directly inserting a PENDING row that the new `evaluate_referral_reward`
    would have rejected. The one-off `audit_referral_self_matches` command
    must report it for manual review and must not touch the row itself."""
    _flags(tenant_a.company)
    referrer = make_customer(tenant_a.company, name="Pre-fix Referrer", phone="9777700001")
    code = ReferralCode.objects.create(
        company=tenant_a.company, referrer_customer=referrer, code="OLDCODE1",
        reward_type=ReferralCode.RewardType.FLAT, reward_value=Decimal("50"),
    )
    lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Pre-fix Lead", phone="9777700099",
        referral_code=code.code,
    )
    # Same customer as the referrer — a self-referral that predates the fix.
    lead.customer = referrer
    lead.save(update_fields=["customer"])
    opportunity = _won_opportunity(tenant_a.company, lead=lead, customer=referrer, user=tenant_a.owner)
    pre_existing_reward = ReferralReward.objects.create(
        company=tenant_a.company, referral_code=code, lead=lead, opportunity=opportunity,
        reward_amount=Decimal("50"), reward_status=ReferralReward.Status.PENDING,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )

    # An unrelated, legitimate PENDING reward must NOT be flagged.
    other_referrer = make_customer(tenant_a.company, name="Legit Referrer")
    other_code = ReferralCode.objects.create(
        company=tenant_a.company, referrer_customer=other_referrer, code="OKCODE01",
        reward_type=ReferralCode.RewardType.FLAT, reward_value=Decimal("20"),
    )
    other_lead = capture_lead(
        tenant_a.company, tenant_a.owner, name="Legit Lead", phone="9888800099",
        referral_code=other_code.code,
    )
    other_customer = make_customer(tenant_a.company, name="Unrelated Referee")
    other_lead.customer = other_customer
    other_lead.save(update_fields=["customer"])
    other_opportunity = _won_opportunity(
        tenant_a.company, lead=other_lead, customer=other_customer, user=tenant_a.owner,
    )
    legit_reward = ReferralReward.objects.create(
        company=tenant_a.company, referral_code=other_code, lead=other_lead,
        opportunity=other_opportunity, reward_amount=Decimal("20"),
        reward_status=ReferralReward.Status.PENDING, created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )

    call_command("audit_referral_self_matches")
    output = capsys.readouterr().out

    assert f"reward_id={pre_existing_reward.id}" in output
    assert f"reward_id={legit_reward.id}" not in output

    # Report-only: no row was modified.
    pre_existing_reward.refresh_from_db()
    legit_reward.refresh_from_db()
    assert pre_existing_reward.reward_status == ReferralReward.Status.PENDING
    assert legit_reward.reward_status == ReferralReward.Status.PENDING
