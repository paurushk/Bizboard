"""A-08: first-party shop-floor telemetry — no PII, Owner 7-day p95."""

import pytest

from insights.models import ShopFloorEvent

pytestmark = pytest.mark.django_db


def test_telemetry_post_rejects_gstin_and_phone(tenant_a):
    bad = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "invoice_complete", "gstin": "29ABCDE1234F1Z5"},
        format="json",
    )
    assert bad.status_code == 400, bad.data
    phone = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "pos_line_added", "phone": "9876543210"},
        format="json",
    )
    assert phone.status_code == 400, phone.data
    assert ShopFloorEvent.objects.filter(company=tenant_a.company).count() == 0


def test_telemetry_staff_can_post_owner_only_get(tenant_a):
    posted = tenant_a.staff_client.post(
        "/api/v1/insights/telemetry/",
        {"event": "complete_duration_ms", "duration_ms": 120},
        format="json",
    )
    assert posted.status_code == 201, posted.data
    denied = tenant_a.staff_client.get("/api/v1/insights/telemetry/")
    assert denied.status_code in (403, 404)

    for ms in (100, 200, 800, 900, 1000):
        ok = tenant_a.client.post(
            "/api/v1/insights/telemetry/",
            {"event": "complete_duration_ms", "duration_ms": ms},
            format="json",
        )
        assert ok.status_code == 201, ok.data
    fail = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "offline_flush_fail"},
        format="json",
    )
    assert fail.status_code == 201, fail.data

    summary = tenant_a.client.get("/api/v1/insights/telemetry/")
    assert summary.status_code == 200, summary.data
    assert summary.data["complete_count"] >= 0
    assert summary.data["complete_p95_ms"] in (900, 1000)
    assert summary.data["offline_flush_fail"] == 1
    assert summary.data["days"] == 7
    assert "funnel" in summary.data
    assert set(summary.data["funnel"]) >= {
        "signup_completed",
        "wizard_tax_confirmed",
        "wizard_completed",
        "invoice_complete",
        "invoice_complete_started",
        "invoice_complete_failed",
        "invoice_complete_failed_by_reason",
        "signup_failed",
        "pdf_started",
        "payment_started",
        "payment_completed",
        "payment_failed",
    }


def test_register_emits_signup_funnel_event():
    from accounts.models import User
    from rest_framework.test import APIClient

    client = APIClient()
    resp = client.post(
        "/api/v1/auth/register/",
        {
            "company_name": "Funnel Mart",
            "email": "funnel-owner@funnelmart.test",
            "password": "StrongPass123!",
            "state": "Karnataka",
        },
        format="json",
    )
    assert resp.status_code == 200
    user = User.objects.get(email="funnel-owner@funnelmart.test")
    company = user.company_memberships.get().company
    assert ShopFloorEvent.objects.filter(company=company, event="signup_completed").exists()
    signup = ShopFloorEvent.objects.get(company=company, event="signup_completed")
    assert signup.journey == "signup"
    assert signup.success is True
    login = client.post(
        "/api/v1/auth/login/",
        {"email": "funnel-owner@funnelmart.test", "password": "StrongPass123!"},
        format="json",
    )
    assert login.status_code == 200
    summary = client.get("/api/v1/insights/telemetry/")
    assert summary.status_code == 200, summary.data
    assert summary.data["funnel"]["signup_completed"] >= 1
