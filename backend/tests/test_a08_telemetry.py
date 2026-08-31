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
