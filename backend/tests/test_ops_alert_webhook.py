"""Ops alert webhook: no-infra Sentry/uptime-monitor -> Telegram paging relay."""

from __future__ import annotations

from unittest import mock

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_ops_alert_requires_token_configured():
    c = APIClient()
    resp = c.post("/api/v1/ops/alert/", {"message": "hi"}, format="json")
    assert resp.status_code == 401


@override_settings(OPS_ALERT_TOKEN="secret123")
def test_ops_alert_rejects_wrong_token():
    c = APIClient()
    resp = c.post("/api/v1/ops/alert/?token=wrong", {"message": "hi"}, format="json")
    assert resp.status_code == 401


@override_settings(OPS_ALERT_TOKEN="secret123", OPS_TELEGRAM_CHAT_ID="-100555", TELEGRAM_BOT_TOKEN="dummy")
def test_ops_alert_generic_message_is_relayed_via_query_token():
    c = APIClient()
    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        resp = c.post("/api/v1/ops/alert/?token=secret123", {"message": "db is down"}, format="json")
    assert resp.status_code == 200
    assert mock_post.call_count == 1
    sent_body = mock_post.call_args.kwargs["json"]
    assert sent_body["chat_id"] == "-100555"
    assert "db is down" in sent_body["text"]


@override_settings(OPS_ALERT_TOKEN="secret123", OPS_TELEGRAM_CHAT_ID="-100555", TELEGRAM_BOT_TOKEN="dummy")
def test_ops_alert_accepts_token_via_header():
    c = APIClient()
    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        resp = c.post(
            "/api/v1/ops/alert/",
            {"text": "disk almost full"},
            format="json",
            HTTP_X_OPS_ALERT_TOKEN="secret123",
        )
    assert resp.status_code == 200
    assert mock_post.call_count == 1


@override_settings(OPS_ALERT_TOKEN="secret123", OPS_TELEGRAM_CHAT_ID="-100555", TELEGRAM_BOT_TOKEN="dummy")
def test_ops_alert_formats_sentry_event_alert_payload():
    c = APIClient()
    payload = {
        "action": "triggered",
        "data": {
            "event": {
                "title": "TypeError: fake_time() takes 0 positional arguments",
                "culprit": "sales.views.complete",
                "web_url": "https://sentry.io/organizations/bizboard/issues/123/",
            },
            "triggered_rule": "New issue in production",
        },
    }
    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        resp = c.post("/api/v1/ops/alert/?token=secret123", payload, format="json")
    assert resp.status_code == 200
    text = mock_post.call_args.kwargs["json"]["text"]
    assert "TypeError" in text
    assert "sales.views.complete" in text
    assert "sentry.io" in text
    assert "New issue in production" in text


@override_settings(OPS_ALERT_TOKEN="secret123", OPS_TELEGRAM_CHAT_ID="-100555", TELEGRAM_BOT_TOKEN="dummy")
def test_ops_alert_skips_sentry_installation_ping_without_paging():
    c = APIClient()
    payload = {"action": "created", "installation": {"uuid": "abc"}}
    with mock.patch("core.services.telegram.requests.post") as mock_post:
        resp = c.post("/api/v1/ops/alert/?token=secret123", payload, format="json")
        mock_post.assert_not_called()
    assert resp.status_code == 200


@override_settings(OPS_ALERT_TOKEN="secret123", OPS_TELEGRAM_CHAT_ID="", TELEGRAM_BOT_TOKEN="dummy")
def test_ops_alert_never_raises_when_chat_id_unconfigured():
    c = APIClient()
    resp = c.post("/api/v1/ops/alert/?token=secret123", {"message": "hi"}, format="json")
    assert resp.status_code == 200


@override_settings(OPS_ALERT_TOKEN="secret123")
def test_ops_alert_empty_body_is_a_noop_200():
    c = APIClient()
    resp = c.post("/api/v1/ops/alert/?token=secret123", {}, format="json")
    assert resp.status_code == 200
