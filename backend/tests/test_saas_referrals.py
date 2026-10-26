"""D-19 (2026-10-25, BB-139): a Bizboard customer refers another business."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from accounts.models import Company
from billing.models import Plan, ReferralEvent, ReferralLink, Subscription
from billing.referrals import attribute_signup, link_for, qualify_referrals
from core.rls import rls_bypass
from tests.rls_helpers import app_role, needs_pg

pytestmark = pytest.mark.django_db


def _flag(company, on=True):
    flags = dict(company.feature_flags or {})
    flags["ENABLE_SAAS_REFERRALS"] = on
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _signup(name, *, email=None, gstin="", code=""):
    from accounts.views import create_owner_account

    data = {
        "company_name": name, "email": email or f"owner@{name.lower().replace(' ', '')}.test",
        "full_name": "", "phone": "", "state": "Karnataka", "gstin": gstin, "referral_code": code,
    }
    _user, company = create_owner_account(None, data, password="StrongPass123!x")
    return company


def _events(company, kind=None):
    with rls_bypass():
        qs = ReferralEvent.objects.filter(company=company)
        if kind:
            qs = qs.filter(kind=kind)
        return list(qs)


def _pay(company, *, price=49900):
    plan, _ = Plan.objects.get_or_create(slug=f"paid-{price}", defaults={"name": "Paid", "price_paise": price, "seat_limit": 3})
    Subscription.objects.update_or_create(
        company=company,
        defaults={"plan": plan, "status": Subscription.Status.ACTIVE, "current_period_end": timezone.now() + timedelta(days=30)},
    )


def test_the_panel_is_hidden_while_the_flag_is_off(tenant_a):
    assert tenant_a.client.get("/api/v1/billing/referral/").status_code == 404
    _flag(tenant_a.company)
    res = tenant_a.client.get("/api/v1/billing/referral/")
    assert res.status_code == 200, res.data
    assert len(res.data["code"]) == 8 and res.data["signed_up"] == 0 and res.data["qualified"] == 0
    # The same link every time; staff cannot see it.
    assert tenant_a.client.get("/api/v1/billing/referral/").data["code"] == res.data["code"]
    assert tenant_a.staff_client.get("/api/v1/billing/referral/").status_code == 403


def test_the_public_check_says_only_yes_or_no(tenant_a, client):
    _flag(tenant_a.company)
    code = link_for(tenant_a.company).code
    def valid(c):
        res = client.get(f"/api/v1/billing/referral/check/{c}/")
        assert res.status_code == 200
        assert tenant_a.company.name not in res.content.decode()
        body = res.json()
        return body.get("data", body)["valid"]

    assert valid(code.lower()) is True  # codes are case-insensitive
    assert valid("NOPE2345") is False
    _flag(tenant_a.company, on=False)
    assert valid(code) is False


def test_a_signup_with_the_code_is_recorded_for_the_referrer(tenant_a):
    _flag(tenant_a.company)
    code = link_for(tenant_a.company).code
    new = _signup("Referred Traders", code=code)
    [event] = _events(tenant_a.company)
    assert event.kind == ReferralEvent.Kind.SIGNED_UP and event.referred_company_id == new.pk
    assert tenant_a.client.get("/api/v1/billing/referral/").data["signed_up"] == 1


def test_bad_codes_and_switched_off_referrers_never_block_signup(tenant_a):
    assert _signup("No Such Code", code="ZZZZ9999").pk
    code = link_for(tenant_a.company).code  # link exists but the flag is off
    assert _signup("Flag Off Co", code=code).pk
    _flag(tenant_a.company)
    ReferralLink.objects.filter(code=code).update(is_active=False)
    assert _signup("Inactive Link Co", code=code).pk
    assert _events(tenant_a.company) == []


def test_the_same_business_does_not_count(tenant_a):
    _flag(tenant_a.company)
    code = link_for(tenant_a.company).code
    _signup("Same Gstin Co", gstin=tenant_a.company.gstin, code=code)
    _signup("Same Domain Co", email=f"other{tenant_a.owner.email[tenant_a.owner.email.index('@'):]}", code=code)
    assert _events(tenant_a.company) == []
    _signup("Gmail Co", email="someone-new@gmail.com", code=code)  # a public mail domain says nothing
    assert len(_events(tenant_a.company)) == 1


@override_settings(SAAS_REFERRAL_DAILY_CAP=2)
def test_at_most_the_daily_cap_is_attributed(tenant_a):
    _flag(tenant_a.company)
    code = link_for(tenant_a.company).code
    for i in range(3):
        _signup(f"Cap Co {i}", code=code)
    assert len(_events(tenant_a.company)) == 2


def test_a_referral_qualifies_once_the_business_pays(tenant_a):
    _flag(tenant_a.company)
    new = _signup("Will Pay Co", code=link_for(tenant_a.company).code)
    assert qualify_referrals() == {"qualified": 0, "voided": 0}  # on the trial: not yet
    _pay(new, price=0)
    assert qualify_referrals()["qualified"] == 0  # a free plan is not paying
    _pay(new)
    assert qualify_referrals()["qualified"] == 1
    assert qualify_referrals()["qualified"] == 0  # once only
    assert tenant_a.client.get("/api/v1/billing/referral/").data["qualified"] == 1


def test_a_gstin_added_later_that_matches_the_referrer_voids_it(tenant_a):
    _flag(tenant_a.company)
    new = _signup("Later Gstin Co", code=link_for(tenant_a.company).code)
    Company.objects.filter(pk=new.pk).update(gstin=tenant_a.company.gstin)
    _pay(Company.objects.get(pk=new.pk))
    assert qualify_referrals() == {"qualified": 0, "voided": 1}
    [event] = _events(tenant_a.company)
    assert event.voided_at and "same GSTIN" in event.void_reason
    assert tenant_a.client.get("/api/v1/billing/referral/").data["signed_up"] == 0


def test_erasing_either_company_keeps_working(tenant_a):
    from accounts.erasure import erase_company

    _flag(tenant_a.company)
    new = _signup("Erased Later Co", code=link_for(tenant_a.company).code)
    erase_company(new, mode="hard", requested_by_email="t@test", reason="test")
    [event] = _events(tenant_a.company)
    assert event.referred_company_id is None
    other = _signup("Second Co", code=link_for(tenant_a.company).code)
    erase_company(tenant_a.company, mode="hard", requested_by_email="t@test", reason="test")
    with rls_bypass():
        assert not ReferralLink.objects.filter(company_id=tenant_a.company.pk).exists()
        assert not ReferralEvent.objects.filter(referred_company=other).exists()


def test_google_signup_takes_the_code_too():
    from accounts.google_signin import _signup_serializer_class

    assert "referral_code" in _signup_serializer_class()().fields


def test_attribution_errors_are_swallowed(tenant_a, monkeypatch):
    _flag(tenant_a.company)
    code = link_for(tenant_a.company).code
    monkeypatch.setattr("billing.referrals._same_business", lambda *a, **k: 1 / 0)
    new = _signup("Boom Co")
    assert attribute_signup(new, code) is False


# --- Postgres, under the NOSUPERUSER NOBYPASSRLS app role -----------------------------------


def _rls_on():
    return override_settings(POSTGRES_RLS_ENABLED=True)


@pytest.mark.postgres
@needs_pg
@pytest.mark.django_db(transaction=True)
def test_signup_records_the_referrers_event_under_rls(tenant_a):
    from core.rls import company_scope

    from django.db import DatabaseError, transaction

    _flag(tenant_a.company)
    link = link_for(tenant_a.company)
    with _rls_on(), app_role():
        new = _signup("Rls Referred Co", code=link.code)
        # The referred company's own context cannot write the referrer's row directly.
        with company_scope(new.pk), pytest.raises(DatabaseError), transaction.atomic():
            ReferralEvent.objects.create(company=tenant_a.company, link=link, kind="QUALIFIED")
    assert [e.referred_company_id for e in _events(tenant_a.company)] == [new.pk]


@pytest.mark.postgres
@needs_pg
@pytest.mark.django_db(transaction=True)
def test_the_daily_task_qualifies_under_the_app_role(tenant_a):
    from billing.tasks import qualify_saas_referrals_task

    _flag(tenant_a.company)
    new = _signup("Rls Pays Co", code=link_for(tenant_a.company).code)
    _pay(new)
    with _rls_on(), app_role():
        assert qualify_saas_referrals_task()["qualified"] == 1
    assert len(_events(tenant_a.company, ReferralEvent.Kind.QUALIFIED)) == 1
