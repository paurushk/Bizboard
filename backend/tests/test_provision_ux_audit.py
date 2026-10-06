"""UX audit company: five roles, no subscription, no AI consent, history seed."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from accounts.models import Company, CompanyUser
from billing.models import Subscription
from crm.models import Lead
from payroll.models import Employee
from sales.models import SalesInvoice

pytestmark = pytest.mark.django_db


@override_settings(DEBUG=True, DJANGO_ENV="development")
def test_provision_creates_audit_company_roles_and_history(tmp_path: Path):
    creds = tmp_path / "creds.txt"
    out = StringIO()
    call_command("provision_ux_audit", credentials_file=str(creds), stdout=out)
    text = out.getvalue()
    assert "Passwords are in that file only." in text
    body = creds.read_text(encoding="utf-8")
    assert "ux-audit-owner@bizboard.local" in body
    password = [line.split("\t")[2] for line in body.splitlines() if line.startswith("ux-audit-owner")][0]
    assert password not in text

    audit = Company.objects.get(name="UX Audit Traders")
    assert audit.ai_features_enabled is False
    assert audit.accounting_enabled is True
    # CRM is a dark module: bare company JSON no longer grants it, the full-demo plan does.
    from core.services.feature_flags import build_feature_flags

    assert build_feature_flags(company=audit)["ENABLE_CRM"] is True
    assert audit.feature_flags.get("ENABLE_AA_CONSENT") is not True
    assert "NAV_PACK_DEFAULT" not in (audit.feature_flags or {})
    # A trial subscription would turn the dark modules off, so the company sits on the full-demo plan.
    assert Subscription.objects.get(company=audit).plan.slug == "ux-full-demo"
    roles = set(CompanyUser.objects.filter(company=audit).values_list("role", flat=True))
    assert roles == {
        CompanyUser.Role.OWNER,
        CompanyUser.Role.POLICY_DESK,
        CompanyUser.Role.ACCOUNTANT,
        CompanyUser.Role.AUDITOR,
        CompanyUser.Role.INVENTORY_STAFF,
        CompanyUser.Role.SALES_STAFF,
    }
    assert SalesInvoice.objects.filter(company=audit, number__startswith="UXH-S-").count() == 24
    assert Employee.objects.filter(company=audit).count() == 4
    assert Lead.objects.filter(company=audit).count() == 8

    control = Company.objects.get(name="UX Pack Control")
    assert control.feature_flags.get("NAV_PACK_DEFAULT") is True
    assert control.ai_features_enabled is False
    assert not Subscription.objects.filter(company=control).exists()

    again = StringIO()
    call_command("provision_ux_audit", credentials_file=str(creds), stdout=again)
    assert SalesInvoice.objects.filter(company=audit, number__startswith="UXH-S-").count() == 24
    body_again = creds.read_text(encoding="utf-8")
    assert password in body_again


@override_settings(DEBUG=True, DJANGO_ENV="development")
def test_history_refuses_demo_traders():
    with pytest.raises(CommandError, match="Demo Traders"):
        call_command("seed_synthetic_bulk", history=True, company="Demo Traders", stdout=StringIO())


def test_aa_consent_is_opt_in_only():
    from tests.conftest import make_tenant

    t = make_tenant("aaconsent")
    t.company.ai_features_enabled = False
    t.company.save(update_fields=["ai_features_enabled"])
    call_command("enable_full_demo", email=t.owner.email, stdout=StringIO())
    t.company.refresh_from_db()
    assert t.company.feature_flags.get("ENABLE_AA_CONSENT") is not True
    call_command("enable_full_demo", email=t.owner.email, with_aa_consent=True, stdout=StringIO())
    t.company.refresh_from_db()
    assert t.company.feature_flags.get("ENABLE_AA_CONSENT") is True
    assert t.company.ai_features_enabled is False


@override_settings(DJANGO_ENV="production")
def test_provision_refuses_production(tmp_path: Path):
    with pytest.raises(CommandError):
        call_command("provision_ux_audit", credentials_file=str(tmp_path / "c.txt"), stdout=StringIO())


@override_settings(DEBUG=True, DJANGO_ENV="development")
def test_full_demo_plan_keeps_dark_modules_on_after_a_subscription_exists(tmp_path: Path):
    """A trial subscription would turn CRM, manufacturing and payroll off. The audit company
    is moved to a plan that names them, and the shared trial plan is left alone."""
    from billing.models import Plan, Subscription
    from core.services.feature_flags import build_feature_flags

    trial_before = None
    trial = Plan.objects.filter(slug="trial").first()
    if trial is not None:
        trial_before = dict(trial.modules or {})
    call_command("provision_ux_audit", credentials_file=str(tmp_path / "c.txt"), stdout=StringIO())
    from accounts.models import Company

    company = Company.objects.get(name="UX Audit Traders")
    flags = build_feature_flags(company=company)
    assert Subscription.objects.get(company=company).plan.slug == "ux-full-demo"
    if trial is not None:
        trial.refresh_from_db()
        assert dict(trial.modules or {}) == trial_before
    assert flags["ENABLE_CRM"] and flags["ENABLE_MANUFACTURING"] and flags["ENABLE_PAYROLL"]
