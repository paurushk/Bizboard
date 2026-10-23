"""Browser error tunnel: the SPA's Sentry SDK posts envelopes to the API, which
forwards them only to the configured browser DSN (Sentry or self-hosted GlitchTip)."""

from __future__ import annotations

import json
from unittest import mock

import pytest
import requests
from django.test import override_settings
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

URL = "/api/v1/client-errors/"
DSN = "https://publickey@errors.example.in/3"


def _envelope(dsn: str = DSN) -> bytes:
    header = json.dumps({"event_id": "a" * 32, "dsn": dsn, "sent_at": "2026-10-23T00:00:00Z"})
    item_header = json.dumps({"type": "event"})
    item = json.dumps({"message": "boom", "level": "error"})
    return f"{header}\n{item_header}\n{item}\n".encode()


def _post(client: APIClient, body: bytes):
    return client.generic("POST", URL, body, content_type="text/plain;charset=UTF-8")


def test_tunnel_is_off_without_a_browser_dsn(settings):
    settings.SENTRY_BROWSER_DSN = ""
    with mock.patch("core.error_tunnel.requests.post") as forward:
        resp = _post(APIClient(), _envelope())
    assert resp.status_code == 404
    forward.assert_not_called()


@override_settings(SENTRY_BROWSER_DSN=DSN)
def test_envelope_for_the_configured_project_is_forwarded():
    with mock.patch("core.error_tunnel.requests.post") as forward:
        forward.return_value = mock.Mock(status_code=200, headers={})
        body = _envelope()
        resp = _post(APIClient(), body)
    assert resp.status_code == 200
    forward.assert_called_once()
    assert forward.call_args.args[0] == "https://errors.example.in/api/3/envelope/"
    assert forward.call_args.kwargs["data"] == body
    assert forward.call_args.kwargs["params"] == {"sentry_key": "publickey"}
    assert forward.call_args.kwargs["headers"]["Content-Type"] == "application/x-sentry-envelope"


@override_settings(SENTRY_BROWSER_DSN="http://publickey@localhost:8095/sub/path/7")
def test_dsn_with_port_and_path_prefix_keeps_both():
    with mock.patch("core.error_tunnel.requests.post") as forward:
        forward.return_value = mock.Mock(status_code=200, headers={})
        resp = _post(APIClient(), _envelope("http://publickey@localhost:8095/sub/path/7"))
    assert resp.status_code == 200
    assert forward.call_args.args[0] == "http://localhost:8095/sub/path/api/7/envelope/"


@pytest.mark.parametrize(
    "other_dsn",
    [
        "https://publickey@attacker.example.com/3",  # another host
        "https://publickey@errors.example.in/4",  # another project
        "http://publickey@errors.example.in/3",  # downgraded scheme
        "https://publickey@errors.example.in:8443/3",  # another port
        "not a dsn",
        "",
    ],
)
@override_settings(SENTRY_BROWSER_DSN=DSN)
def test_envelope_for_any_other_destination_is_refused(other_dsn):
    with mock.patch("core.error_tunnel.requests.post") as forward:
        resp = _post(APIClient(), _envelope(other_dsn))
    assert resp.status_code == 400
    forward.assert_not_called()


@override_settings(SENTRY_BROWSER_DSN=DSN)
def test_garbage_and_empty_bodies_are_refused():
    with mock.patch("core.error_tunnel.requests.post") as forward:
        assert _post(APIClient(), b"{not json\nmore").status_code == 400
        assert _post(APIClient(), b"").status_code == 400
    forward.assert_not_called()


@override_settings(SENTRY_BROWSER_DSN=DSN)
def test_oversized_envelope_is_refused_before_forwarding():
    from core.error_tunnel import MAX_ENVELOPE_BYTES

    body = _envelope() + b"x" * MAX_ENVELOPE_BYTES
    with mock.patch("core.error_tunnel.requests.post") as forward:
        resp = _post(APIClient(), body)
    assert resp.status_code == 413
    forward.assert_not_called()


@override_settings(SENTRY_BROWSER_DSN=DSN)
def test_tracker_down_answers_502():
    with mock.patch("core.error_tunnel.requests.post", side_effect=requests.ConnectionError("down")):
        resp = _post(APIClient(), _envelope())
    assert resp.status_code == 502


@override_settings(SENTRY_BROWSER_DSN=DSN)
def test_tracker_rate_limit_is_passed_back_to_the_sdk():
    with mock.patch("core.error_tunnel.requests.post") as forward:
        forward.return_value = mock.Mock(
            status_code=429, headers={"Retry-After": "60", "X-Sentry-Rate-Limits": "60::organization"}
        )
        resp = _post(APIClient(), _envelope())
    assert resp.status_code == 429
    assert resp["Retry-After"] == "60"
    assert resp["X-Sentry-Rate-Limits"] == "60::organization"


@override_settings(SENTRY_BROWSER_DSN=DSN)
def test_signed_in_browser_without_csrf_token_still_gets_through(django_user_model):
    # The SDK's fetch carries the session cookie but never a CSRF token; the tunnel
    # does no authentication, so a signed-in user's reports are not dropped with 403.
    user = django_user_model.objects.create_user(email="tunnel-user@example.com", password="x-Pass-123456")
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    with mock.patch("core.error_tunnel.requests.post") as forward:
        forward.return_value = mock.Mock(status_code=200, headers={})
        resp = _post(client, _envelope())
    assert resp.status_code == 200


def test_tunnel_rate_limit_has_its_own_bucket():
    # The default "anon" scope would share one request history with every anonymous endpoint,
    # so login-page traffic would eat the error budget and the other way round.
    from rest_framework.throttling import AnonRateThrottle

    from core.error_tunnel import ClientErrorTunnelThrottle

    assert ClientErrorTunnelThrottle.scope == "client_errors" != AnonRateThrottle.scope
