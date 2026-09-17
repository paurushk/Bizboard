"""Telegram bot webhook: secret-token auth + linking-code replay.

Companion to test_webhook_enumeration.py's KNOWN_WEBHOOKS entry — every
inbound webhook needs its own forgery/replay contract test alongside the
generic "rejects unsigned" meta test.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

_SECRET = "telegram-webhook-secret-xyz"


def _start_body(chat_id: int, code: str) -> bytes:
    return json.dumps(
        {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": f"/start {code}"}}
    ).encode()


@override_settings(TELEGRAM_WEBHOOK_SECRET=_SECRET)
def test_telegram_webhook_rejects_missing_or_wrong_secret():
    c = APIClient()
    body = _start_body(12345, "whatever")

    missing = c.post("/api/v1/telegram/webhook/", data=body, content_type="application/json")
    assert missing.status_code == 401

    wrong = c.post(
        "/api/v1/telegram/webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="not-the-secret",
    )
    assert wrong.status_code == 401


@override_settings(TELEGRAM_WEBHOOK_SECRET=_SECRET, TELEGRAM_BOT_TOKEN="dummy-token")
def test_telegram_webhook_links_chat_id_once_then_code_is_consumed(tenant_a):
    from core.services.telegram import generate_link_code

    code = generate_link_code(tenant_a.owner)
    headers = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": _SECRET}

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}

        first = APIClient().post(
            "/api/v1/telegram/webhook/",
            data=_start_body(999888777, code),
            content_type="application/json",
            **headers,
        )
        assert first.status_code == 200

        tenant_a.owner.refresh_from_db()
        assert tenant_a.owner.telegram_chat_id == "999888777"
        assert tenant_a.owner.telegram_link_code == ""

        # Replay of the same /start code from a different chat must not
        # hijack the link — the code was already consumed on first use.
        replay = APIClient().post(
            "/api/v1/telegram/webhook/",
            data=_start_body(111222333, code),
            content_type="application/json",
            **headers,
        )
        assert replay.status_code == 200
        tenant_a.owner.refresh_from_db()
        assert tenant_a.owner.telegram_chat_id == "999888777"


@override_settings(TELEGRAM_WEBHOOK_SECRET=_SECRET, TELEGRAM_BOT_TOKEN="dummy-token")
def test_telegram_webhook_expired_code_does_not_link(tenant_a):
    from django.utils import timezone

    from core.services.telegram import generate_link_code

    code = generate_link_code(tenant_a.owner)
    tenant_a.owner.telegram_link_code_expires_at = timezone.now() - timezone.timedelta(minutes=1)
    tenant_a.owner.save(update_fields=["telegram_link_code_expires_at"])

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        resp = APIClient().post(
            "/api/v1/telegram/webhook/",
            data=_start_body(444555666, code),
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=_SECRET,
        )
    assert resp.status_code == 200
    tenant_a.owner.refresh_from_db()
    assert tenant_a.owner.telegram_chat_id == ""


@override_settings(TELEGRAM_WEBHOOK_SECRET=_SECRET)
def test_telegram_webhook_ignores_non_start_updates():
    c = APIClient()
    body = json.dumps(
        {"update_id": 2, "message": {"chat": {"id": 42}, "text": "hello there"}}
    ).encode()
    resp = c.post(
        "/api/v1/telegram/webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=_SECRET,
    )
    assert resp.status_code == 200
    assert resp.data == {"ok": True}
