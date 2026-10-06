"""enable_full_demo: demo/staging-only helper that grants every grantable module."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from core.services.feature_flags import DARK_MODULE_KEYS, ROLLOUT_GRANTABLE_KEYS

from tests.conftest import make_tenant

pytestmark = pytest.mark.django_db


def test_grants_every_module_key_in_company_json_and_turns_accounting_on():
    t = make_tenant("fulldemo")
    call_command("enable_full_demo", email=t.owner.email, stdout=StringIO())
    t.company.refresh_from_db()
    skipped = {"ENABLE_GSTN_JSON", "ENABLE_PREDICTIVE_DUNNING", *DARK_MODULE_KEYS}
    for key in set(ROLLOUT_GRANTABLE_KEYS) - skipped:
        assert t.company.feature_flags.get(key) is True, key
    for key in DARK_MODULE_KEYS:
        assert t.company.feature_flags.get(key) is not True
    assert t.company.accounting_enabled is True


def test_never_touches_ai_consent_or_credential_integrations():
    t = make_tenant("fulldemo2")
    t.company.ai_features_enabled = False
    t.company.save(update_fields=["ai_features_enabled"])
    call_command("enable_full_demo", email=t.owner.email, stdout=StringIO())
    t.company.refresh_from_db()
    assert t.company.ai_features_enabled is False
    for key in ("ENABLE_WHATSAPP_CLOUD", "ENABLE_CASHFREE", "ENABLE_PAYU", "ENABLE_ACCOUNT_AGGREGATOR"):
        assert key not in t.company.feature_flags


def test_dry_run_writes_nothing():
    t = make_tenant("fulldemo3")
    call_command("enable_full_demo", email=t.owner.email, dry_run=True, stdout=StringIO())
    t.company.refresh_from_db()
    assert not t.company.feature_flags


@override_settings(DJANGO_ENV="production")
def test_refuses_in_production():
    t = make_tenant("fulldemo4")
    with pytest.raises(CommandError):
        call_command("enable_full_demo", email=t.owner.email, stdout=StringIO())
    t.company.refresh_from_db()
    assert not t.company.feature_flags


def test_unknown_email_is_an_error():
    with pytest.raises(CommandError):
        call_command("enable_full_demo", email="nobody@example.test", stdout=StringIO())


def test_seeds_the_chart_of_accounts_when_turning_books_on():
    from accounting.models import Account

    t = make_tenant("fulldemo5")
    assert not Account.objects.filter(company=t.company).exists()
    call_command("enable_full_demo", email=t.owner.email, stdout=StringIO())
    assert Account.objects.filter(company=t.company).exists()


@override_settings(DJANGO_ENV="staging")
def test_fmea2_002_demo_refuses_staging():
    t = make_tenant("fmea2stage")
    with pytest.raises(CommandError):
        call_command("enable_full_demo", email=t.owner.email, stdout=StringIO())


def test_fmea2_003_demo_company_is_explicit():
    from accounts.models import CompanyUser

    t = make_tenant("fmea2multi")
    other = make_tenant("fmea2other")
    CompanyUser.objects.create(
        company=other.company, user=t.owner, role=CompanyUser.Role.OWNER,
    )
    with pytest.raises(CommandError, match="several companies"):
        call_command("enable_full_demo", email=t.owner.email, stdout=StringIO())
    out = StringIO()
    call_command(
        "enable_full_demo", email=t.owner.email, company_id=t.company.id, stdout=out,
    )
    t.company.refresh_from_db()
    assert t.company.accounting_enabled is True
    other.company.refresh_from_db()
    assert other.company.accounting_enabled is False


def test_fmea2_002_dark_flags_follow_subscription():
    from billing.models import Plan, Subscription
    from django.utils import timezone

    bare = make_tenant("fmea2dark")
    out = StringIO()
    call_command("enable_full_demo", email=bare.owner.email, with_dark=True, stdout=out)
    bare.company.refresh_from_db()
    assert bare.company.feature_flags.get("ENABLE_PAYROLL") is not True
    assert bare.company.feature_flags.get("ENABLE_CRM") is not True
    assert bare.company.feature_flags.get("pack_grant") == "insurance"
    assert bare.company.feature_flags.get("manufacturing_pack_grant") is True
    assert "Payroll stays off" in out.getvalue()
    from core.services.feature_flags import build_feature_flags

    effective = build_feature_flags(company=bare.company)
    assert effective["ENABLE_CRM"] is True
    assert effective["ENABLE_MANUFACTURING"] is True
    assert effective.get("ENABLE_PAYROLL") is not True

    subscribed = make_tenant("fmea2sub")
    plan = Plan.objects.create(slug="fmea2-plan", name="FMEA2", modules={"ENABLE_POS": True}, is_active=True)
    Subscription.objects.create(
        company=subscribed.company, plan=plan, status=Subscription.Status.ACTIVE,
        current_period_end=timezone.now(),
    )
    out = StringIO()
    call_command("enable_full_demo", email=subscribed.owner.email, with_dark=True, stdout=out)
    subscribed.company.refresh_from_db()
    assert subscribed.company.feature_flags.get("ENABLE_PAYROLL") is not True
    assert "Payroll stays off" in out.getvalue()


def test_fmea2_010_trial_plan_lock():
    from billing.services import TRIAL_HELD_FALSE, trial_plan_modules

    modules = trial_plan_modules()
    assert modules["ENABLE_GSTR"] is True
    assert modules["ENABLE_GSTR_EXTENDED"] is True
    assert modules["ENABLE_CUSTOMER_360"] is True
    for key in TRIAL_HELD_FALSE:
        assert modules[key] is False
    for key in ("ENABLE_CRM", "ENABLE_MANUFACTURING", "ENABLE_PAYROLL"):
        assert key not in modules


def test_fmea2_grant_dark_module_dry_run_and_apply():
    from core.services.feature_flags import build_feature_flags

    first = make_tenant("fmea2grant")
    second = make_tenant("fmea2grantb")
    with pytest.raises(CommandError, match="Payroll has no pack"):
        call_command("grant_dark_module", pack="payroll", company_id=[first.company.id])

    dry = StringIO()
    call_command(
        "grant_dark_module",
        pack="insurance",
        company_id=[first.company.id, second.company.id],
        dry_run=True,
        stdout=dry,
    )
    text = dry.getvalue()
    assert text.count("dry-run") == 2
    assert "after ENABLE_CRM=True" in text
    first.company.refresh_from_db()
    second.company.refresh_from_db()
    assert first.company.feature_flags.get("pack_grant") != "insurance"
    assert second.company.feature_flags.get("pack_grant") != "insurance"

    call_command(
        "grant_dark_module",
        pack="manufacturing",
        company_id=[first.company.id],
        apply=True,
        stdout=StringIO(),
    )
    first.company.refresh_from_db()
    assert first.company.feature_flags.get("manufacturing_pack_grant") is True
    assert "ENABLE_PAYROLL" not in (first.company.feature_flags or {})
    flags = build_feature_flags(company=first.company)
    assert flags["ENABLE_MANUFACTURING"] is True
    second.company.refresh_from_db()
    assert second.company.feature_flags.get("manufacturing_pack_grant") is not True
