"""Regression tests for the 28 Sep 2026 release-audit defects."""

from datetime import date
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from contracts.models import Contract
from contracts.tasks import refresh_contract_statuses
from crm.referrals import reward_amount_for
from insurance.services import add_calendar_months
from masters.models import Product
from sales.models import SalesInvoice
from sales.recurring import process_due_schedules
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db


def _flags(company, **extra):
    company.feature_flags = {
        "ENABLE_CONTRACTS": True,
        "ENABLE_PROJECTS": True,
        "ENABLE_INSURANCE": True,
        "ENABLE_SUPPORT_TICKETS": True,
        **extra,
    }
    company.save(update_fields=["feature_flags"])


def _desk(company):
    user = User.objects.create_user(
        email=f"desk-dr-{company.pk}@x.test", password="StrongPass123!", full_name="Desk",
    )
    CompanyUser.objects.create(
        company=company, user=user, role=CompanyUser.Role.POLICY_DESK,
        can_manage_policies=True, is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_reward_amount_keeps_paise():
    assert reward_amount_for("PERCENT", "2.5", "1000.40") == Decimal("25.01")
    assert reward_amount_for("FLAT", "10.005", "0") == Decimal("10.01")


def test_policy_end_date_is_a_calendar_anniversary():
    assert add_calendar_months(date(2026, 1, 1), 12) == date(2027, 1, 1)
    assert add_calendar_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_calendar_months(date(2025, 1, 31), 1) == date(2025, 2, 28)


def test_second_option_cannot_issue_another_in_force_policy(tenant_a):
    _flags(tenant_a.company)
    client = _desk(tenant_a.company)
    customer = make_customer(tenant_a.company)
    products = []
    for name in ("Motor A", "Motor B"):
        created = client.post("/api/v1/insurance/products/", {
            "name": name, "insurer_name": "Insurer", "line": "MOTOR",
            "tenure_months": 12, "sum_insured": "100000", "premium": "5000",
        }, format="json")
        assert created.status_code == 201, created.data
        products.append(created.data["id"])
    prospect = client.post("/api/v1/insurance/prospects/", {"name": "Prospect"}, format="json")
    options = client.post("/api/v1/insurance/option-sets/", {
        "lead": prospect.data["id"], "products": products,
    }, format="json")
    assert options.status_code == 201, options.data
    first, second = [row["id"] for row in options.data["options"]]
    client.post(f"/api/v1/insurance/option-sets/{options.data['id']}/choose/", {"option": first}, format="json")
    issued = client.post("/api/v1/insurance/policies/", {
        "option": first, "customer": customer.id, "nominee": "Anita",
        "start_date": "2026-01-01",
    }, format="json")
    assert issued.status_code == 201, issued.data
    assert issued.data["end_date"] == "2027-01-01"
    client.post(f"/api/v1/insurance/option-sets/{options.data['id']}/choose/", {"option": second}, format="json")
    again = client.post("/api/v1/insurance/policies/", {
        "option": second, "customer": customer.id, "nominee": "Anita",
        "start_date": "2026-01-01",
    }, format="json")
    assert again.status_code == 400, again.data
    negative = client.post(
        f"/api/v1/insurance/policies/{issued.data['id']}/commission/",
        {"amount": "-1"}, format="json",
    )
    assert negative.status_code == 400
    garbage = client.post(
        f"/api/v1/insurance/policies/{issued.data['id']}/commission/",
        {"amount": "nope"}, format="json",
    )
    assert garbage.status_code == 400


def test_bad_policy_input_is_400(tenant_a):
    _flags(tenant_a.company)
    client = _desk(tenant_a.company)
    missing = client.post("/api/v1/insurance/policies/", {"start_date": "tomorrow"}, format="json")
    assert missing.status_code == 400
    diary = client.post("/api/v1/insurance/renewals/", {"within_days": "soon"}, format="json")
    assert diary.status_code == 400


def test_contract_read_uses_dates_not_the_stale_column(tenant_a):
    from datetime import timedelta

    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    today = timezone.localdate()
    contract = Contract.objects.create(
        company=tenant_a.company, customer=customer, contract_type=Contract.Type.WARRANTY,
        number="CON-DR15", start_date=today - timedelta(days=40),
        end_date=today - timedelta(days=1), created_by=tenant_a.owner,
    )
    Contract.objects.filter(pk=contract.pk).update(status=Contract.Status.ACTIVE)
    listed = tenant_a.client.get("/api/v1/contracts/?status=EXPIRED")
    assert listed.status_code == 200
    rows = listed.data.get("results", listed.data)
    assert contract.pk in [row["id"] for row in rows]
    detail = tenant_a.client.get(f"/api/v1/contracts/{contract.pk}/")
    assert detail.data["status"] == "EXPIRED"


def test_contract_and_recurring_sweeps_set_rls_per_company(tenant_a, monkeypatch):
    seen = []

    def _set(cid):
        seen.append(cid)

    monkeypatch.setattr("core.rls.set_rls_company", _set)
    refresh_contract_statuses()
    assert tenant_a.company.id in seen
    assert seen[-1] is None
    seen.clear()
    process_due_schedules()
    assert tenant_a.company.id in seen
    assert seen[-1] is None


def test_cancelled_milestone_invoice_can_be_replaced(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    service = make_product(tenant_a.company, name="Civil", sku="CV-DR", product_type=Product.ProductType.SERVICE)
    created = tenant_a.client.post("/api/v1/projects/", {"customer": customer.id, "name": "Site"}, format="json")
    pid = created.data["id"]
    tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/", {
        "name": "Foundation", "amount": "1000", "service_product": service.id, "sequence": 1,
    })
    detail = tenant_a.client.get(f"/api/v1/projects/{pid}/")
    milestone_id = detail.data["milestones"][0]["id"]
    tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{milestone_id}/ready/")
    first = tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{milestone_id}/invoice/")
    invoice_id = first.data["milestones"][0]["sales_invoice"]
    SalesInvoice.objects.filter(pk=invoice_id).update(status=SalesInvoice.Status.CANCELLED)
    second = tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/{milestone_id}/invoice/")
    assert second.status_code == 200, second.data
    assert second.data["milestones"][0]["sales_invoice"] != invoice_id
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 2


def test_project_bad_input_is_400_not_500(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    service = make_product(tenant_a.company, name="Civil", sku="CV-400", product_type=Product.ProductType.SERVICE)
    created = tenant_a.client.post("/api/v1/projects/", {"customer": customer.id, "name": "Site"}, format="json")
    pid = created.data["id"]
    bad_sequence = tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/", {
        "name": "Foundation", "amount": "10", "service_product": service.id, "sequence": "x",
    }, format="json")
    assert bad_sequence.status_code == 400
    missing = tenant_a.client.post(f"/api/v1/projects/{pid}/milestones/999999/ready/")
    assert missing.status_code == 404


def test_reopen_resets_the_sla_clock(tenant_a):
    from datetime import timedelta

    from support.models import Ticket

    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company)
    created = tenant_a.client.post("/api/v1/support/tickets/", {
        "customer": customer.id, "subject": "Pump", "priority": "URGENT",
    }, format="json")
    ticket_id = created.data["id"]
    for status_name in ("IN_PROGRESS", "RESOLVED", "CLOSED"):
        moved = tenant_a.client.post(
            f"/api/v1/support/tickets/{ticket_id}/transition/", {"status": status_name}, format="json",
        )
        assert moved.status_code == 200, moved.data
    ticket = Ticket.objects.get(pk=ticket_id)
    ticket.sla_due_at = timezone.now() - timedelta(days=2)
    ticket.save(update_fields=["sla_due_at"])
    reopened = tenant_a.client.post(
        f"/api/v1/support/tickets/{ticket_id}/transition/", {"status": "IN_PROGRESS"}, format="json",
    )
    assert reopened.status_code == 200, reopened.data
    ticket.refresh_from_db()
    assert ticket.sla_due_at > timezone.now()


@override_settings(RAZORPAY_WEBHOOK_SECRET="", DJANGO_ENV="test")
def test_unsigned_billing_webhook_requires_header_in_test_env():
    client = APIClient()
    refused = client.post(
        "/api/v1/billing/razorpay/webhook/",
        {"event": "subscription.charged"},
        format="json",
    )
    assert refused.status_code == 403
