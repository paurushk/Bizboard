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


@override_settings(OPS_TELEGRAM_CHAT_ID="", OPS_NTFY_URL="https://ntfy.sh/bb-test-topic")
def test_ops_page_also_pushes_to_ntfy_when_set():
    from core.services.telegram import send_ops_alert

    with mock.patch("core.services.telegram.requests.post") as post:
        post.return_value.ok = True
        result = send_ops_alert("⚠️ backup failed")
    assert result.mode == "sent"
    assert post.call_args.args[0] == "https://ntfy.sh/bb-test-topic"
    assert post.call_args.kwargs["data"] == "⚠️ backup failed".encode()
    assert all(v.isascii() for v in post.call_args.kwargs["headers"].values())


@override_settings(OPS_TELEGRAM_CHAT_ID="-100555", TELEGRAM_BOT_TOKEN="dummy", OPS_NTFY_URL="https://ntfy.sh/t")
def test_ntfy_failure_never_blocks_the_telegram_page():
    import requests

    from core.services.telegram import send_ops_alert

    with mock.patch("core.services.telegram.requests.post") as post:
        telegram_ok = mock.Mock(status_code=200)
        telegram_ok.json.return_value = {"ok": True}
        post.side_effect = [requests.ConnectionError("ntfy down"), telegram_ok]
        result = send_ops_alert("db is down")
    assert post.call_count == 2
    assert result.mode != "unlinked"


@override_settings(OPS_TELEGRAM_CHAT_ID="", OPS_NTFY_URL="http://ntfy.sh/plain-http")
def test_ntfy_needs_https():
    from core.services.telegram import send_ops_alert

    with mock.patch("core.services.telegram.requests.post") as post:
        assert send_ops_alert("x").mode == "unlinked"
    post.assert_not_called()


@override_settings(OPS_ALERT_TOKEN="secret123", DJANGO_ENV="staging")
def test_alertmanager_bearer_token_and_payload_are_relayed():
    """WP-6: Alertmanager sends Authorization: Bearer and its own JSON shape."""
    c = APIClient()
    payload = {
        "status": "firing",
        "alerts": [{
            "status": "firing",
            "labels": {"alertname": "BizBoardWorkerDown", "severity": "page"},
            "annotations": {"summary": "A Celery worker stopped answering", "runbook": "docs/ops/ALERTS.md#pdf-queue"},
        }],
    }
    with mock.patch("core.services.telegram.send_ops_alert") as page:
        resp = c.post("/api/v1/ops/alert/", payload, format="json", HTTP_AUTHORIZATION="Bearer secret123")
    assert resp.status_code == 200
    text = page.call_args.args[0]
    assert "FIRING: BizBoardWorkerDown: A Celery worker stopped answering" in text
    assert "docs/ops/ALERTS.md#pdf-queue" in text
    assert c.post("/api/v1/ops/alert/", payload, format="json", HTTP_AUTHORIZATION="Bearer wrong").status_code == 401
