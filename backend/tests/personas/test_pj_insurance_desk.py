"""PRE-09 desk journeys. A policy is an operational book. Commission is not a customer receipt (D17)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounting.models import JournalEntry
from accounts.models import CompanyUser, User
from core.invariants import assert_all_invariants
from crm.models import Campaign, Lead
from insurance.models import CommissionReceivable, Policy
from insurance.services import add_calendar_months
from payments.models import CustomerReceipt
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


def _desk(company):
    user = User.objects.create_user(email=f"desk-{company.pk}@x.test", password="StrongPass123!", full_name="Desk")
    CompanyUser.objects.create(
        company=company, user=user, role=CompanyUser.Role.POLICY_DESK, can_manage_policies=True, is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _flags(company):
    company.feature_flags = {"ENABLE_INSURANCE": True, "ENABLE_SUPPORT_TICKETS": True}
    company.save(update_fields=["feature_flags"])


def test_j_ins_p12_issue_and_p11_options(tenant_a):
    """J-INS-P11-OPTIONS J-INS-P12-ISSUE."""
    _flags(tenant_a.company)
    client = _desk(tenant_a.company)
    journals = JournalEntry.objects.filter(company=tenant_a.company).count()
    receipts = CustomerReceipt.objects.filter(company=tenant_a.company).count()
    a = client.post("/api/v1/insurance/products/", {
        "name": "Motor A", "insurer_name": "Insurer", "line": "MOTOR",
        "tenure_months": 1, "sum_insured": "100000", "premium": "5000",
    }, format="json")
    assert a.status_code == 201, a.data
    customer = make_customer(tenant_a.company)
    campaign = Campaign.objects.create(company=tenant_a.company, name="Motor", campaign_type="DIGITAL")
    lead = Lead.objects.create(company=tenant_a.company, name=customer.name, campaign=campaign, customer=customer)
    one = client.post("/api/v1/insurance/option-sets/", {"lead": lead.id, "products": [a.data["id"]]}, format="json")
    assert one.status_code == 400
    b = client.post("/api/v1/insurance/products/", {
        "name": "Motor B", "insurer_name": "Insurer", "line": "MOTOR",
        "tenure_months": 1, "sum_insured": "200000", "premium": "7000",
    }, format="json")
    options = client.post(
        "/api/v1/insurance/option-sets/",
        {"lead": lead.id, "products": [a.data["id"], b.data["id"]]},
        format="json",
    )
    assert options.status_code == 201, options.data
    chosen = options.data["options"][0]["id"]
    client.post(f"/api/v1/insurance/option-sets/{options.data['id']}/choose/", {"option": chosen}, format="json")
    start = timezone.localdate()
    issued = client.post("/api/v1/insurance/policies/", {
        "option": chosen, "customer": customer.id, "nominee": "Anita", "start_date": start.isoformat(),
    }, format="json")
    assert issued.status_code == 201, issued.data
    again = client.post("/api/v1/insurance/policies/", {
        "option": chosen, "customer": customer.id, "nominee": "Anita", "start_date": start.isoformat(),
    }, format="json")
    assert again.data["id"] == issued.data["id"]
    policy = Policy.objects.get(pk=issued.data["id"])
    assert policy.end_date == add_calendar_months(start, 1)
    assert policy.premium is not None
    assert JournalEntry.objects.filter(company=tenant_a.company).count() == journals
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == receipts
    assert_all_invariants(tenant_a.company)


def test_j_ins_p12_renew_p5_commission_p10_claim(tenant_a):
    """J-INS-P12-RENEW J-INS-P5-COMMISSION J-INS-P10-CLAIM."""
    _flags(tenant_a.company)
    client = _desk(tenant_a.company)
    a = client.post("/api/v1/insurance/products/", {
        "name": "Health A", "insurer_name": "Insurer", "line": "HEALTH",
        "tenure_months": 12, "sum_insured": "100000", "premium": "4000",
    }, format="json")
    b = client.post("/api/v1/insurance/products/", {
        "name": "Health B", "insurer_name": "Insurer", "line": "HEALTH",
        "tenure_months": 12, "sum_insured": "150000", "premium": "5500",
    }, format="json")
    customer = make_customer(tenant_a.company)
    campaign = Campaign.objects.create(company=tenant_a.company, name="Health", campaign_type="DIGITAL")
    lead = Lead.objects.create(company=tenant_a.company, name=customer.name, campaign=campaign, customer=customer)
    options = client.post(
        "/api/v1/insurance/option-sets/",
        {"lead": lead.id, "products": [a.data["id"], b.data["id"]]},
        format="json",
    )
    chosen = options.data["options"][0]["id"]
    client.post(f"/api/v1/insurance/option-sets/{options.data['id']}/choose/", {"option": chosen}, format="json")
    issued = client.post("/api/v1/insurance/policies/", {
        "option": chosen, "customer": customer.id, "nominee": "Anita", "start_date": timezone.localdate().isoformat(),
    }, format="json")
    policy_id = issued.data["id"]
    Policy.objects.filter(pk=policy_id).update(end_date=timezone.localdate() + timedelta(days=10))
    first = client.post("/api/v1/insurance/renewals/", {"within_days": 30}, format="json")
    second = client.post("/api/v1/insurance/renewals/", {"within_days": 30}, format="json")
    assert first.data["created"] == 1
    assert second.data["created"] == 0
    from crm.models import Lead as LeadModel

    renewal = LeadModel.objects.filter(company=tenant_a.company, message__startswith="Renewal ").first()
    assert renewal is not None
    assert renewal.message.startswith(f"Renewal {issued.data['number']}")
    journals = JournalEntry.objects.filter(company=tenant_a.company).count()
    commission = client.post(f"/api/v1/insurance/policies/{policy_id}/commission/", {"amount": "500"}, format="json")
    assert commission.status_code == 200, commission.data
    assert CommissionReceivable.objects.filter(pk=commission.data["id"], policy_id=policy_id).exists()
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
    assert JournalEntry.objects.filter(company=tenant_a.company).count() == journals
    claim = client.post(f"/api/v1/insurance/policies/{policy_id}/claim/", {"summary": "Bumper"}, format="json")
    assert claim.status_code == 200, claim.data
    assert JournalEntry.objects.filter(company=tenant_a.company).count() == journals
    assert_all_invariants(tenant_a.company)
