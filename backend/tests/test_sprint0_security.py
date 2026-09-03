"""Sprint 0 security fixes: host gates, DEBUG parsing, health disclosure, cookie JWT."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from config.settings import (
    _assert_allowed_hosts,
    _assert_cors_credentials_safe,
    _is_local_allowed_host,
    _parse_debug_flag,
)
from core.authentication import CookieJWTAuthentication


def test_star_is_not_a_local_allowed_host():
    """BB-000550: wildcard must never count as local."""
    assert _is_local_allowed_host("*") is False
    assert _is_local_allowed_host(" * ") is False
    assert _is_local_allowed_host("localhost") is True
    assert _is_local_allowed_host("127.0.0.1") is True
    assert _is_local_allowed_host("testserver") is True
    assert _is_local_allowed_host("app.localhost") is True
    assert _is_local_allowed_host("example.com") is False


def test_star_allowed_hosts_refused_outside_local_dev():
    """BB-000550: '*' is forbidden outside development/test."""
    with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
        _assert_allowed_hosts(["*"], "production")
    with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
        _assert_allowed_hosts(["api.example.com", "*"], "staging")
    _assert_allowed_hosts(["*"], "development")
    _assert_allowed_hosts(["*"], "test")
    _assert_allowed_hosts(["localhost", "127.0.0.1"], "production")


def test_django_debug_accepts_truthy_strings():
    """BB-000634: DJANGO_DEBUG accepts 1/true/yes/on, case-insensitive."""
    assert _parse_debug_flag("1") is True
    assert _parse_debug_flag("true") is True
    assert _parse_debug_flag("TRUE") is True
    assert _parse_debug_flag("Yes") is True
    assert _parse_debug_flag("on") is True
    assert _parse_debug_flag("0") is False
    assert _parse_debug_flag("false") is False
    assert _parse_debug_flag("off") is False
    assert _parse_debug_flag("") is False
    assert _parse_debug_flag(None) is False


@pytest.mark.django_db
def test_health_ready_unauthenticated_is_redacted():
    """BB-000626: public ?ready=1 must not leak topology."""
    resp = APIClient().get("/api/v1/health/?ready=1")
    assert resp.status_code in (200, 503)
    assert resp.data["status"] in ("ok", "degraded")
    for key in ("db", "cache", "celery", "celery_workers", "celery_beat", "pdf_queue_depth"):
        assert key not in resp.data


@pytest.mark.django_db
def test_health_ready_authenticated_includes_details(tenant_a):
    resp = tenant_a.client.get("/api/v1/health/?ready=1")
    assert resp.status_code in (200, 503)
    assert "db" in resp.data
    assert "cache" in resp.data
    assert "celery" in resp.data


@pytest.mark.django_db
def test_cookie_jwt_rejects_bearer_in_production(tenant_a):
    """BB-000603: production/staging cookie JWT ignores Authorization Bearer."""
    access = str(RefreshToken.for_user(tenant_a.owner).access_token)
    request = RequestFactory().get("/api/v1/auth/me/")
    request.COOKIES = {}
    request.META["HTTP_AUTHORIZATION"] = f"Bearer {access}"

    with override_settings(DJANGO_ENV="production"):
        assert CookieJWTAuthentication().authenticate(request) is None

    with override_settings(DJANGO_ENV="staging"):
        assert CookieJWTAuthentication().authenticate(request) is None


@pytest.mark.django_db
def test_cookie_jwt_accepts_bearer_outside_production(tenant_a):
    access = str(RefreshToken.for_user(tenant_a.owner).access_token)
    request = RequestFactory().get("/api/v1/auth/me/")
    request.COOKIES = {}
    request.META["HTTP_AUTHORIZATION"] = f"Bearer {access}"

    with override_settings(DJANGO_ENV="development"):
        user, _token = CookieJWTAuthentication().authenticate(request)
        assert user.pk == tenant_a.owner.pk


@pytest.mark.django_db
def test_csrf_endpoint_sets_csrftoken_cookie():
    """BB-000602: GET /auth/csrf/ bootstraps csrftoken for the SPA."""
    resp = APIClient().get("/api/v1/auth/csrf/")
    assert resp.status_code == 200
    assert "csrftoken" in resp.cookies
    # FE-06: token also in the body for the cross-origin double-submit fallback.
    # (get_token() returns the masked form the SPA sends as X-CSRFToken; the
    # cookie stores the raw secret — Django validates one against the other.)
    body_token = resp.data.get("csrfToken")
    assert body_token and len(body_token) >= 32


def test_cors_wildcard_with_credentials_rejected_regardless_of_admin():
    """BB-000625: credentialed CORS * is always refused."""
    with pytest.raises(ImproperlyConfigured, match="CORS"):
        _assert_cors_credentials_safe(
            origins=["*"],
            allow_all=False,
            allow_credentials=True,
        )
    with pytest.raises(ImproperlyConfigured, match="CORS"):
        _assert_cors_credentials_safe(
            origins=["http://localhost:5173"],
            allow_all=True,
            allow_credentials=True,
        )
    _assert_cors_credentials_safe(
        origins=["http://localhost:5173"],
        allow_all=False,
        allow_credentials=True,
    )
