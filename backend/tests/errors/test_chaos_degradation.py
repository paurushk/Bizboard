"""QOS-0050 — dependency-outage degradation contract.

A real "kill the Redis / Postgres container mid-request" drill is an ops / Phase-5
task. This is the *contract* that drill would check: when a dependency is
unavailable the app degrades — a clear 503 from the health probe, never an
unhandled 500 / hang — and it recovers when the dependency comes back.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def _client():
    return APIClient()


def test_cache_outage_degrades_health_not_crash():
    """Redis/cache down => readiness probe is 503 `cache: false`, not a 500."""
    boom = mock.Mock(side_effect=ConnectionError("redis down"))
    with mock.patch.object(cache, "set", boom), mock.patch.object(cache, "get", boom):
        resp = _client().get("/api/v1/health/?ready=1")
    assert resp.status_code == 503, resp.content
    assert resp.data["status"] == "degraded"


def test_db_outage_degrades_liveness_not_crash():
    """Postgres down => liveness probe is a clean 503, never an unhandled 500."""
    with mock.patch(
        "django.db.connection.ensure_connection",
        side_effect=Exception("could not connect to server"),
    ):
        resp = _client().get("/api/v1/health/")
    assert resp.status_code == 503, resp.content
    assert resp.data["status"] == "degraded"


def test_health_recovers_when_dependencies_return():
    """After the outage clears, the probe reports healthy again — no stuck state."""
    resp = _client().get("/api/v1/health/")
    assert resp.status_code == 200
    assert resp.data["status"] == "ok"
