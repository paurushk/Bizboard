"""WP-AB2: sign-up, OTP and reset need a bot-check token when a provider is configured."""

import urllib.error
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from core.services import bot_check

pytestmark = pytest.mark.django_db

ENDPOINTS = [
    ("/api/v1/auth/register/otp/request/", {"email": "new-owner@alpha-traders.in"}),
    ("/api/v1/auth/register/", {"email": "new-owner@alpha-traders.in", "password": "Strong-Pass-123",
                                "company_name": "Bot Test Co", "accept_terms": True}),
    ("/api/v1/auth/otp/request/", {"phone": "+919820012345"}),
    ("/api/v1/auth/password/reset/", {"identifier": "someone@alpha-traders.in"}),
]


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    yield
    cache.clear()


def _code(resp) -> str:
    return str(resp.content)


@override_settings(BOT_CHECK_PROVIDER="stub", BOT_CHECK_ENFORCE=True)
@pytest.mark.parametrize("path,body", ENDPOINTS)
def test_each_endpoint_refuses_without_a_token(path, body):
    resp = APIClient().post(path, body, format="json")
    assert resp.status_code in (400, 422), (path, resp.status_code)
    assert "BOT_CHECK_FAILED" in _code(resp)


@override_settings(BOT_CHECK_PROVIDER="stub", BOT_CHECK_ENFORCE=True)
@pytest.mark.parametrize("path,body", ENDPOINTS)
def test_each_endpoint_passes_the_check_with_a_good_token(path, body):
    resp = APIClient().post(path, {**body, "bot_token": "ok"}, format="json")
    assert "BOT_CHECK_FAILED" not in _code(resp)
    header = APIClient().post(path, body, format="json", HTTP_X_BOT_TOKEN="ok")
    assert "BOT_CHECK_FAILED" not in _code(header)


@override_settings(BOT_CHECK_PROVIDER="stub", BOT_CHECK_ENFORCE=False)
def test_shadow_mode_counts_but_does_not_refuse():
    with mock.patch.object(bot_check, "_event") as event:
        resp = APIClient().post("/api/v1/auth/password/reset/", {"identifier": "a@b.in"}, format="json")
    assert "BOT_CHECK_FAILED" not in _code(resp)
    event.assert_any_call("bot_check_failed_password_reset")


@override_settings(BOT_CHECK_PROVIDER="turnstile", TURNSTILE_SECRET_KEY="secret", BOT_CHECK_ENFORCE=True)
def test_turnstile_unreachable_fails_closed():
    with mock.patch("core.services.bot_check.urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
        resp = APIClient().post(
            "/api/v1/auth/password/reset/", {"identifier": "a@b.in", "bot_token": "real"}, format="json",
        )
    assert "BOT_CHECK_FAILED" in _code(resp)


@override_settings(BOT_CHECK_PROVIDER="turnstile", TURNSTILE_SECRET_KEY="secret")
def test_turnstile_verdict_is_used():
    ok = mock.MagicMock()
    ok.read.return_value = b'{"success": true}'
    ok.__enter__.return_value = ok
    bad = mock.MagicMock()
    bad.read.return_value = b'{"success": false}'
    bad.__enter__.return_value = bad
    with mock.patch("core.services.bot_check.urllib.request.urlopen", return_value=ok) as urlopen:
        assert bot_check.verify("tok", "1.2.3.4") is True
    assert b"secret=secret" in urlopen.call_args[0][0].data
    with mock.patch("core.services.bot_check.urllib.request.urlopen", return_value=bad):
        assert bot_check.verify("tok") is False
    assert bot_check.verify("") is False


def test_provider_none_is_the_test_default_and_passes():
    assert bot_check.verify("") is True
