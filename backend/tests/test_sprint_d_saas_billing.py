"""Sprint D BB-000671: SaaS entitlements, write gate, webhook, plan modules."""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.models import Plan, Subscription
from core.services.feature_flags import build_feature_flags
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db


def _plan(**kwargs):
    defaults = {
        "name": "Starter",
        "slug": kwargs.pop("slug", "starter"),
        "seat_limit": 3,
        "modules": {
            "ENABLE_CRM": True,
            "ENABLE_PAYROLL": False,
            "ENABLE_MANUFACTURING": False,
            "ENABLE_TDS": False,
        },
        "price_paise": 49900,
    }
    defaults.update(kwargs)
    return Plan.objects.create(**defaults)


def test_bb_000671_trial_expired_blocks_sales_invoice_post(tenant_a):
    plan = _plan()
    Subscription.objects.create(
        company=tenant_a.company,
        plan=plan,
        status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() - timedelta(days=1),
    )
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    blocked = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert blocked.status_code == 403, blocked.content

    tenant_a.company.billing_override_active = True
    tenant_a.company.save(update_fields=["billing_override_active"])
    allowed = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert allowed.status_code == 201, allowed.data


def test_bb_000671_webhook_updates_subscription_status(tenant_a):
    plan = _plan(slug="growth")
    sub = Subscription.objects.create(
        company=tenant_a.company,
        plan=plan,
        status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() + timedelta(days=7),
        razorpay_subscription_id="sub_test_abc",
    )
    client = APIClient()
    payload = {
        "event": "subscription.halted",
        "payload": {"subscription": {"entity": {"id": "sub_test_abc", "status": "halted"}}},
    }
    resp = client.post(
        "/api/v1/billing/razorpay/webhook/",
        payload,
        format="json",
        HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
    )
    assert resp.status_code == 200, resp.data
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.PAST_DUE

    resp2 = client.post(
        "/api/v1/billing/razorpay/webhook/",
        {
            "event": "subscription.cancelled",
            "payload": {"subscription": {"entity": {"id": "sub_test_abc", "status": "cancelled"}}},
        },
        format="json",
        HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
    )
    assert resp2.status_code == 200
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.SUSPENDED


@override_settings(ENABLE_CRM=True)
def test_bb_000671_plan_modules_and_with_env_and_company_flags(tenant_a):
    tenant_a.company.feature_flags = {"ENABLE_CRM": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    plan = _plan(
        slug="books-only",
        modules={
            "ENABLE_CRM": False,
            "ENABLE_PAYROLL": False,
            "ENABLE_MANUFACTURING": False,
            "ENABLE_TDS": False,
        },
    )
    Subscription.objects.create(
        company=tenant_a.company,
        plan=plan,
        status=Subscription.Status.ACTIVE,
    )
    flags = build_feature_flags(company=tenant_a.company)
    assert flags["ENABLE_CRM"] is False


def test_bb_000671_owner_plans_checkout_portal(tenant_a):
    plan = _plan(slug="pro", price_paise=99900)
    listed = tenant_a.client.get("/api/v1/billing/plans/")
    assert listed.status_code == 200
    assert any(row["slug"] == "pro" for row in listed.data)

    checkout = tenant_a.client.post("/api/v1/billing/checkout/", {"plan_id": plan.id}, format="json")
    assert checkout.status_code == 201, checkout.data
    assert checkout.data["checkout_order_id"]
    assert checkout.data["subscription"]["status"] == Subscription.Status.PENDING

    portal = tenant_a.client.get("/api/v1/billing/portal/")
    assert portal.status_code == 200
    assert portal.data["subscription"]["plan"]["slug"] == "pro"
    assert portal.data["seat_limit"] == plan.seat_limit
