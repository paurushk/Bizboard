"""H0–H6 locks for the narrowed trial plan.

Books balance is already proven in test_phase5_accounting.py
(test_trial_balance_and_balance_sheet_equation). Complaint credit-note
idempotency is already proven in test_growth_os.py. Tally refuses a second
post in test_track_readiness.py. Portal isolation is already proven in
test_customer_portal.py. This file covers the gaps those tests do not.
"""

import ast
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from billing.models import Plan
from billing.services import (
    TRIAL_HELD_FALSE,
    ensure_register_trial,
    grandfather_trial_module_use,
    trial_plan_modules,
)
from core.services.feature_flags import DARK_MODULE_KEYS, ROLLOUT_GRANTABLE_KEYS, flag_enabled
from sales import order_gates
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


def test_trial_dict_names_every_grantable_flag_and_holds_the_rest(tenant_a):
    # The trial plan row is created on first use; do not depend on another test.
    ensure_register_trial(tenant_a.company)
    modules = trial_plan_modules()
    assert set(modules) == set(ROLLOUT_GRANTABLE_KEYS)
    assert modules["ENABLE_GSTR"] is True
    assert modules["ENABLE_GST_GUARD"] is True
    assert modules["ENABLE_CUSTOMER_PORTAL"] is True
    assert modules["ENABLE_CUSTOMER_360"] is True
    for key in TRIAL_HELD_FALSE:
        assert modules[key] is False
    assert not (set(modules) & set(DARK_MODULE_KEYS))
    plan = Plan.objects.get(slug="trial")
    assert plan.modules == modules
    assert settings.GSP_LIVE_ENABLED is False


def test_trade_pack_on_a_trial_skips_held_flags(tenant_a):
    from accounts.packs import apply_pack

    ensure_register_trial(tenant_a.company)
    state = apply_pack(
        tenant_a.company,
        "trade",
        {"what_you_sell": "goods", "how_you_sell": "field", "deliver": "yes", "gst_registered": "yes"},
        tenant_a.owner,
    )
    tenant_a.company.refresh_from_db()
    flags = tenant_a.company.feature_flags or {}
    for key in ("ENABLE_TALLY", "ENABLE_ROUTE_OPTIMIZATION", "ENABLE_ROUTE_PROFIT", "ENABLE_CUSTOMER_ACTIONS"):
        assert key in state.skipped_flags
        assert flags.get(key) is not True
    assert flags.get("ENABLE_GSTR") is True
    assert flags.get("ENABLE_GST_GUARD") is True


def test_pack_without_a_subscription_uses_the_trial_dict(tenant_a):
    from accounts.packs import apply_pack
    from billing.models import Subscription

    Subscription.objects.filter(company=tenant_a.company).delete()
    state = apply_pack(tenant_a.company, "insurance", {}, tenant_a.owner)
    tenant_a.company.refresh_from_db()
    flags = tenant_a.company.feature_flags or {}
    for key in ("ENABLE_INSURANCE", "ENABLE_REFERRALS", "ENABLE_SUPPORT_TICKETS", "ENABLE_COMPLAINTS"):
        assert flags.get(key) is not True
        assert key in state.skipped_flags
    assert flags.get("ENABLE_CRM") is True


def test_grandfather_keeps_modules_that_already_have_rows(tenant_a, tenant_b):
    from workshop.models import JobCard

    ensure_register_trial(tenant_a.company)
    ensure_register_trial(tenant_b.company)
    customer = make_customer(tenant_a.company)
    card = JobCard.objects.create(company=tenant_a.company, customer=customer, complaint="Noise")
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    kept = grandfather_trial_module_use()
    tenant_a.company.refresh_from_db()
    tenant_b.company.refresh_from_db()
    assert tenant_a.company.feature_flags.get("ENABLE_WORKSHOP") is True
    assert tenant_b.company.feature_flags.get("ENABLE_WORKSHOP") is not True
    assert tenant_b.company.feature_flags.get("ENABLE_PROJECTS") is not True
    assert kept["ENABLE_WORKSHOP"] >= 1
    assert JobCard.objects.filter(pk=card.pk).exists()

    tenant_a.company.feature_flags = {"ENABLE_WORKSHOP": False}
    tenant_a.company.save(update_fields=["feature_flags"])
    grandfather_trial_module_use()
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.feature_flags["ENABLE_WORKSHOP"] is False


def test_grant_company_flag_overrides_the_trial_without_editing_the_plan(tenant_a, monkeypatch):
    ensure_register_trial(tenant_a.company)
    before = dict(Plan.objects.get(slug="trial").modules)
    call_command(
        "grant_company_flag",
        email=tenant_a.owner.email,
        flag="ENABLE_TALLY",
        on=True,
    )
    tenant_a.company.refresh_from_db()
    assert flag_enabled(tenant_a.company, "ENABLE_TALLY") is True
    assert Plan.objects.get(slug="trial").modules == before
    call_command(
        "grant_company_flag",
        email=tenant_a.owner.email,
        flag="ENABLE_TALLY",
        off=True,
    )
    tenant_a.company.refresh_from_db()
    assert "ENABLE_TALLY" not in (tenant_a.company.feature_flags or {})
    if hasattr(tenant_a.company, "_feature_flags_cache"):
        del tenant_a.company._feature_flags_cache
    assert flag_enabled(tenant_a.company, "ENABLE_TALLY") is False
    with pytest.raises(CommandError):
        call_command("grant_company_flag", email=tenant_a.owner.email, flag="NOT_A_FLAG", on=True)
    with pytest.raises(CommandError):
        call_command("grant_company_flag", email=tenant_a.owner.email, flag="ENABLE_CRM", on=True)
    monkeypatch.setenv("E2E_GOLDEN_GRANT", "1")
    with pytest.raises(CommandError):
        call_command("grant_company_flag", email=tenant_a.owner.email, flag="ENABLE_TALLY", on=True)


def test_credit_limit_message_names_the_rule():
    assert "Credit limit exceeded" in __import__("inspect").getsource(order_gates)


def _complaint_list(user):
    from rest_framework.test import APIRequestFactory, force_authenticate

    from complaints.views import ComplaintViewSet

    request = APIRequestFactory().get("/api/v1/complaints/")
    force_authenticate(request, user=user)
    return ComplaintViewSet.as_view({"get": "list"})(request)


def test_complaints_are_hidden_until_the_company_is_granted(tenant_a):
    ensure_register_trial(tenant_a.company)
    assert flag_enabled(tenant_a.company, "ENABLE_COMPLAINTS") is False
    assert _complaint_list(tenant_a.owner).status_code == 404
    call_command(
        "grant_company_flag",
        email=tenant_a.owner.email,
        flag="ENABLE_COMPLAINTS",
        on=True,
    )
    tenant_a.company.refresh_from_db()
    assert _complaint_list(tenant_a.owner).status_code == 200


def test_customer_360_lists_only_this_customers_complaints(tenant_a, tenant_b):
    from complaints.models import Complaint
    from insights.customer_360 import customer_360

    ensure_register_trial(tenant_a.company)
    owner_flags = {"ENABLE_CUSTOMER_360": True}
    tenant_a.company.feature_flags = owner_flags
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company, name="Asha")
    other = make_customer(tenant_a.company, name="Other")
    foreign = make_customer(tenant_b.company, name="Foreign")
    Complaint.objects.create(
        company=tenant_a.company, customer=customer, category="QUALITY", description="Late",
    )
    Complaint.objects.create(
        company=tenant_a.company, customer=other, category="DAMAGED", description="Box",
    )
    Complaint.objects.create(
        company=tenant_b.company, customer=foreign, category="OTHER", description="Nope",
    )
    from accounts.models import CompanyUser

    owner = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.owner)
    hidden = customer_360(tenant_a.company, customer, owner)
    assert "complaints" not in hidden
    call_command(
        "grant_company_flag",
        email=tenant_a.owner.email,
        flag="ENABLE_COMPLAINTS",
        on=True,
    )
    tenant_a.company.refresh_from_db()
    # grant replaces the JSON dict; put the 360 grant back beside complaints.
    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_CUSTOMER_360"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    seen = customer_360(tenant_a.company, customer, owner)
    assert [row["category"] for row in seen["complaints"]] == ["QUALITY"]


def _onboarding(user):
    from rest_framework.test import APIRequestFactory, force_authenticate

    from crm.onboarding import CrmOnboardingView

    request = APIRequestFactory().get("/api/v1/crm/onboarding/")
    force_authenticate(request, user=user)
    return CrmOnboardingView.as_view()(request)


def test_booker_step_needs_an_active_sales_staff(tenant_a):
    from accounts.models import CompanyUser

    ready = _onboarding(tenant_a.owner)
    assert ready.status_code == 200
    steps = {row["id"]: row["done"] for row in ready.data["steps"]}
    assert steps["booker"] is True
    CompanyUser.objects.filter(
        company=tenant_a.company, role=CompanyUser.Role.SALES_STAFF,
    ).update(is_active=False)
    owner_only = _onboarding(tenant_a.owner)
    steps = {row["id"]: row["done"] for row in owner_only.data["steps"]}
    assert steps["booker"] is False


def test_sales_package_does_not_import_contracts():
    root = Path(__file__).resolve().parents[1] / "sales"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(name == "contracts" or name.startswith("contracts.") for name in names), path


def test_gst_guard_runs_from_the_trial_plan_alone(tenant_a, monkeypatch):
    from reporting.gst_health import build_gst_health
    from sales.models import SalesInvoice

    ensure_register_trial(tenant_a.company)
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    assert flag_enabled(tenant_a.company, "ENABLE_GST_GUARD") is True

    def boom(_gstin):
        raise AssertionError("provider must not be called for a format failure")

    monkeypatch.setattr("core.services.gstin_verify.get_gstin_provider", boom)
    customer = make_customer(tenant_a.company, gstin="")
    inv = SalesInvoice.objects.create(
        company=tenant_a.company,
        customer=customer,
        number="GG-TRIAL",
        status=SalesInvoice.Status.COMPLETED,
        invoice_type="GST",
        invoice_date=timezone.localdate(),
        filing_party_gstin="29AAAAA0000A1Z6",
        taxable_total=Decimal("100"),
        grand_total=Decimal("100"),
    )
    codes = {
        alert["code"]
        for alert in build_gst_health(tenant_a.company)["alerts"]
        if alert.get("document_id") == inv.id
    }
    assert "GSTIN_FORMAT_INVALID" in codes


def test_crm_stays_off_the_trial_until_a_plan_names_it(tenant_a):
    ensure_register_trial(tenant_a.company)
    assert flag_enabled(tenant_a.company, "ENABLE_CRM") is False
    plan = Plan.objects.create(
        name="CRM",
        slug=f"crm-{tenant_a.company.pk}",
        modules={**trial_plan_modules(), "ENABLE_CRM": True},
    )
    from billing.models import Subscription

    Subscription.objects.filter(company=tenant_a.company).update(plan=plan)
    tenant_a.company.refresh_from_db()
    if hasattr(tenant_a.company, "_feature_flags_cache"):
        del tenant_a.company._feature_flags_cache
    assert flag_enabled(tenant_a.company, "ENABLE_CRM") is True
