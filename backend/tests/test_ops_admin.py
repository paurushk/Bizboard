"""ops app wired into Django admin: reachable only by a superuser, the
add-run flow kicks off the Celery task, and the health page renders."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client

from accounts.models import User
from ops.models import CoverageAuditRun

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client():
    User.objects.create_superuser(email="ops-admin@bizboard.local", password="test-pass-123")
    client = Client()
    client.login(email="ops-admin@bizboard.local", password="test-pass-123")
    return client


def test_coverage_audit_run_changelist_reachable(admin_client):
    resp = admin_client.get("/admin/ops/coverageauditrun/")
    assert resp.status_code == 200


def test_health_page_reachable_and_uses_compute_help_health(admin_client):
    with patch("ops.admin.compute_help_health", return_value={
        "window_days": 30, "scope": "all", "opens": 0, "rated": 0,
        "resolution_rate": None, "escalation_rate": None, "repeat_query_rate": None,
        "time_to_resolution_seconds": None, "feedback_open": 0, "search_count": 0,
        "zero_result_rate": None, "top_zero_queries": [], "repeat_queries": [],
    }) as mock_health:
        resp = admin_client.get("/admin/ops/health/")
    assert resp.status_code == 200
    mock_health.assert_called_once()


def test_adding_a_run_via_admin_enqueues_the_task(admin_client):
    with patch("ops.admin.run_coverage_audit_task") as mock_task:
        resp = admin_client.post("/admin/ops/coverageauditrun/add/", {})
    assert resp.status_code in (200, 302), resp.content
    run = CoverageAuditRun.objects.get()
    mock_task.delay.assert_called_once_with(run.pk)
    assert run.requested_by.email == "ops-admin@bizboard.local"


def test_health_page_requires_staff_login():
    resp = Client().get("/admin/ops/health/")
    assert resp.status_code in (302, 403)
