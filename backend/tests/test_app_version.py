"""WP-L1: mobile builds below the supported minimum are told to update; the web is unaffected."""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from core.middleware import AppVersionMiddleware

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(("raw", "parsed"), [("1.4.0", (1, 4, 0)), ("v2.10", (2, 10)), ("bad", None), ("", ())])
def test_versions_parse(raw, parsed):
    assert AppVersionMiddleware.parse(raw) == parsed


@override_settings(MIN_SUPPORTED_APP_VERSION="1.4.0")
def test_an_old_app_build_is_asked_to_update(tenant_a):
    resp = tenant_a.client.get("/api/v1/auth/me/", HTTP_X_APP_VERSION="1.3.9")
    assert resp.status_code == 426
    assert resp.json()["error"]["code"] == "APP_UPDATE_REQUIRED"
    assert "Play Store" in resp.json()["error"]["message"]


@override_settings(MIN_SUPPORTED_APP_VERSION="1.4.0")
def test_current_builds_and_the_browser_are_served(tenant_a):
    assert tenant_a.client.get("/api/v1/auth/me/", HTTP_X_APP_VERSION="1.4.0").status_code == 200
    assert tenant_a.client.get("/api/v1/auth/me/", HTTP_X_APP_VERSION="1.10.0").status_code == 200
    assert tenant_a.client.get("/api/v1/auth/me/").status_code == 200  # no header: web


@override_settings(MIN_SUPPORTED_APP_VERSION="1.4.0")
def test_health_stays_open_for_an_old_build():
    assert APIClient().get("/api/v1/health/", HTTP_X_APP_VERSION="0.1.0").status_code == 200


def test_no_floor_means_no_check(tenant_a):
    assert tenant_a.client.get("/api/v1/auth/me/", HTTP_X_APP_VERSION="0.0.1").status_code == 200
