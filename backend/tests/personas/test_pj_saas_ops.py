"""PRE-10 success and billing journeys. Vendor staff read a redacted copy. They do not become the tenant."""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Company, CompanyUser, User
from billing.models import Plan, Subscription, VendorTenantSnapshot
from billing.ops import note_first_invoice, note_setup_completed, trial_ending_notice, upgrade_prompt
from core.invariants import assert_all_invariants
from crm.models import Campaign
from masters.models import Customer
from support.models import Ticket, VendorTicketShare
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


def test_j_saas_p13_activate_and_winback(tenant_a):
    """J-SAAS-P13-ACTIVATE J-SAAS-P13-WINBACK."""
    vendor = Company.objects.create(name="Vendor Co", state="Karnataka")
    plan = Plan.objects.create(
        name="Small", slug=f"small-pj-{tenant_a.company.pk}", seat_limit=1, monthly_complete_limit=5, modules={},
    )
    Subscription.objects.create(
        company=tenant_a.company, plan=plan, status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() + timedelta(days=3),
    )
    with override_settings(VENDOR_COMPANY_ID=str(vendor.id)):
        note_setup_completed(tenant_a.company)
        note_first_invoice(tenant_a.company.id)
        note_first_invoice(tenant_a.company.id)
        snap = VendorTenantSnapshot.objects.get(company=vendor, source_company_id=tenant_a.company.id)
        assert snap.setup_completed_at is not None
        assert snap.first_invoice_at is not None
        assert VendorTenantSnapshot.objects.filter(company=vendor, source_company_id=tenant_a.company.id).count() == 1
        prompt = upgrade_prompt(tenant_a.company)
        assert prompt["reason"] in {"seats", "documents"}
        assert trial_ending_notice(tenant_a.company)["show"] is True
        later = Subscription.objects.get(company=tenant_a.company)
        later.trial_ends_at = timezone.now() + timedelta(days=8)
        later.save(update_fields=["trial_ends_at"])
        assert trial_ending_notice(tenant_a.company)["show"] is False
        later.trial_ends_at = timezone.now() - timedelta(hours=1)
        later.save(update_fields=["trial_ends_at"])
        assert trial_ending_notice(tenant_a.company)["show"] is False
        blank = tenant_a.client.post("/api/v1/billing/subscription/", {"action": "suspend", "churn_reason": "  "}, format="json")
        assert blank.status_code == 400
        assert Subscription.objects.get(company=tenant_a.company).status == Subscription.Status.TRIAL
        resp = tenant_a.client.post(
            "/api/v1/billing/subscription/",
            {"action": "suspend", "churn_reason": "Too expensive"},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert Campaign.objects.filter(company=vendor, name__startswith="Win-back").count() == 1
        again = tenant_a.client.post(
            "/api/v1/billing/subscription/",
            {"action": "suspend", "churn_reason": "Still gone"},
            format="json",
        )
        assert again.status_code == 200
        assert Campaign.objects.filter(company=vendor, name__startswith="Win-back").count() == 1
    assert_all_invariants(tenant_a.company)


@override_settings(VENDOR_COMPANY_ID="")
def test_j_saas_p10_support_share_is_owner_only(tenant_a, tenant_b):
    """J-SAAS-P10-SUPPORT."""
    tenant_a.company.feature_flags = {"ENABLE_SUPPORT_TICKETS": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    ticket = Ticket.objects.create(
        company=tenant_a.company, customer=customer, subject="Help", description="secret GSTIN", number="TKT-PJ",
    )
    missing = tenant_a.client.post(f"/api/v1/support/tickets/{ticket.id}/share/", {}, format="json")
    assert missing.status_code == 404
    assert VendorTicketShare.objects.count() == 0
    vendor = Company.objects.create(name="Vendor Desk", state="Karnataka")
    vendor.feature_flags = {"ENABLE_SUPPORT_TICKETS": True}
    vendor.save(update_fields=["feature_flags"])
    vendor_user = User.objects.create_user(email="vendor-pj@x.test", password="StrongPass123!", full_name="Vendor")
    CompanyUser.objects.create(
        company=vendor, user=vendor_user, role=CompanyUser.Role.SALES_STAFF, can_create_sales=True,
    )
    seller = User.objects.create_user(email="seller-pj@x.test", password="StrongPass123!", full_name="Seller")
    CompanyUser.objects.create(
        company=tenant_a.company, user=seller, role=CompanyUser.Role.SALES_STAFF, can_create_sales=True,
    )
    with override_settings(VENDOR_COMPANY_ID=str(vendor.id)):
        seller_client = APIClient()
        seller_client.force_authenticate(user=seller)
        assert seller_client.post(f"/api/v1/support/tickets/{ticket.id}/share/", {}, format="json").status_code == 403
        shared = tenant_a.client.post(f"/api/v1/support/tickets/{ticket.id}/share/", {}, format="json")
        assert shared.status_code == 200, shared.data
        vendor_client = APIClient()
        vendor_client.force_authenticate(user=vendor_user)
        listing = vendor_client.get("/api/v1/support/shared/")
        assert listing.status_code == 200, listing.data
        rows = listing.data["results"] if isinstance(listing.data, dict) else listing.data
        assert rows
        assert "description" not in rows[0]
        assert tenant_b.client.get(f"/api/v1/support/shared/{rows[0]['id']}/").status_code == 404
        assert tenant_a.client.get("/api/v1/support/shared/").status_code in (200, 404)
        own = tenant_a.client.get("/api/v1/support/shared/")
        if own.status_code == 200:
            own_rows = own.data["results"] if isinstance(own.data, dict) else own.data
            assert all(row["id"] != rows[0]["id"] for row in own_rows)
    assert Customer.objects.filter(company=vendor).count() == 0
