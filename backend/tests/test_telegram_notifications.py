"""Telegram notification channel: NotificationService branch + link/unlink API."""

from __future__ import annotations

from unittest import mock

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@override_settings(TELEGRAM_BOT_TOKEN="dummy-token")
def test_notification_service_telegram_sent(tenant_a):
    from core.models import Notification
    from core.services.notifications import NotificationService

    tenant_a.owner.telegram_chat_id = "555"
    tenant_a.owner.save(update_fields=["telegram_chat_id"])

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        n = NotificationService.send(
            company=tenant_a.company,
            channel=Notification.Channel.TELEGRAM,
            recipient=tenant_a.owner.telegram_chat_id,
            subject="Test",
            body="hello",
            user=tenant_a.owner,
        )
    assert n.status == Notification.Status.SENT
    assert n.error == ""


def test_notification_service_telegram_unlinked_fails_without_exception(tenant_a):
    from core.models import Notification
    from core.services.notifications import NotificationService

    n = NotificationService.send(
        company=tenant_a.company,
        channel=Notification.Channel.TELEGRAM,
        recipient="",
        subject="Test",
        body="hello",
        user=tenant_a.owner,
    )
    assert n.status == Notification.Status.FAILED
    assert "not linked" in n.error.lower()


@override_settings(ENABLE_TELEGRAM=True)
def test_telegram_link_then_status_then_unlink(tenant_a):
    c = APIClient()
    c.force_authenticate(user=tenant_a.owner)

    status_before = c.get("/api/v1/telegram/status/")
    assert status_before.status_code == 200
    assert status_before.data["linked"] is False
    assert status_before.data["enabled"] is True

    with override_settings(TELEGRAM_BOT_USERNAME="BizboardBot"):
        link_resp = c.post("/api/v1/telegram/link/")
    assert link_resp.status_code == 200
    assert link_resp.data["deep_link"].startswith("https://t.me/BizboardBot?start=")

    tenant_a.owner.refresh_from_db()
    assert tenant_a.owner.telegram_link_code

    tenant_a.owner.telegram_chat_id = "12345"
    tenant_a.owner.save(update_fields=["telegram_chat_id"])

    status_after = c.get("/api/v1/telegram/status/")
    assert status_after.data["linked"] is True

    unlink_resp = c.post("/api/v1/telegram/unlink/")
    assert unlink_resp.status_code == 200
    tenant_a.owner.refresh_from_db()
    assert tenant_a.owner.telegram_chat_id == ""


def test_telegram_link_requires_enabled_flag(tenant_a):
    c = APIClient()
    c.force_authenticate(user=tenant_a.owner)
    resp = c.post("/api/v1/telegram/link/")
    assert resp.status_code == 400


@override_settings(ENABLE_TELEGRAM=True)
def test_notify_company_owners_is_best_effort_and_never_raises(tenant_a):
    from core.services.telegram import notify_company_owners

    tenant_a.owner.telegram_chat_id = "999"
    tenant_a.owner.save(update_fields=["telegram_chat_id"])

    with mock.patch("core.services.telegram.requests.post", side_effect=RuntimeError("network down")):
        notify_company_owners(tenant_a.company, subject="x", body="y")
    # No exception propagated — best-effort by contract.


# --- core.services.telegram unit coverage ----------------------------------


def test_send_telegram_message_empty_chat_id_is_unlinked():
    from core.services.telegram import send_telegram_message

    result = send_telegram_message("", "hi")
    assert result.mode == "unlinked"


@override_settings(TELEGRAM_BOT_TOKEN="")
def test_send_telegram_message_missing_bot_token_fails():
    from core.services.telegram import send_telegram_message

    result = send_telegram_message("123", "hi")
    assert result.mode == "failed"
    assert "not configured" in (result.raw or {}).get("error", "").lower()


@override_settings(TELEGRAM_BOT_TOKEN="dummy-token")
def test_send_telegram_message_http_error_fails():
    from core.services.telegram import send_telegram_message

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 403
        mock_post.return_value.text = "Forbidden: bot was blocked by the user"
        result = send_telegram_message("123", "hi")
    assert result.mode == "failed"
    assert result.raw["status_code"] == 403


@override_settings(TELEGRAM_BOT_TOKEN="dummy-token")
def test_notification_service_telegram_http_failure_is_recorded(tenant_a):
    from core.models import Notification
    from core.services.notifications import NotificationService

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "Internal Server Error"
        n = NotificationService.send(
            company=tenant_a.company,
            channel=Notification.Channel.TELEGRAM,
            recipient="777",
            subject="Test",
            body="hello",
            user=tenant_a.owner,
        )
    assert n.status == Notification.Status.FAILED
    assert "HTTP 500" in n.error


def test_generate_and_resolve_link_code_roundtrip(tenant_a):
    from core.services.telegram import generate_link_code, resolve_link_code

    code = generate_link_code(tenant_a.owner)
    assert code
    tenant_a.owner.refresh_from_db()
    assert tenant_a.owner.telegram_link_code == code
    assert tenant_a.owner.telegram_link_code_expires_at is not None

    resolved = resolve_link_code(code)
    assert resolved is not None
    assert resolved.pk == tenant_a.owner.pk


def test_resolve_link_code_unknown_code_returns_none(tenant_a):
    from core.services.telegram import resolve_link_code

    assert resolve_link_code("this-code-does-not-exist") is None
    assert resolve_link_code("") is None


def test_resolve_link_code_expired_returns_none(tenant_a):
    from django.utils import timezone

    from core.services.telegram import generate_link_code, resolve_link_code

    code = generate_link_code(tenant_a.owner)
    tenant_a.owner.telegram_link_code_expires_at = timezone.now() - timezone.timedelta(minutes=1)
    tenant_a.owner.save(update_fields=["telegram_link_code_expires_at"])

    assert resolve_link_code(code) is None


@override_settings(TELEGRAM_BOT_USERNAME="")
def test_bot_deep_link_empty_when_username_not_configured():
    from core.services.telegram import bot_deep_link

    assert bot_deep_link("some-code") == ""


@override_settings(TELEGRAM_BOT_USERNAME="BizboardBot")
def test_bot_deep_link_builds_start_url():
    from core.services.telegram import bot_deep_link

    assert bot_deep_link("abc123") == "https://t.me/BizboardBot?start=abc123"


def test_notify_company_owners_noop_when_flag_disabled(tenant_a):
    """ENABLE_TELEGRAM off (the default) must not send, even to a linked user."""
    from core.models import Notification
    from core.services.telegram import notify_company_owners

    tenant_a.owner.telegram_chat_id = "111"
    tenant_a.owner.save(update_fields=["telegram_chat_id"])

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        notify_company_owners(tenant_a.company, subject="x", body="y")
        mock_post.assert_not_called()
    assert not Notification.objects.filter(channel=Notification.Channel.TELEGRAM).exists()


@override_settings(ENABLE_TELEGRAM=True, TELEGRAM_BOT_TOKEN="dummy-token")
def test_notify_company_owners_skips_users_without_linked_chat(tenant_a):
    """Owner never linked their Telegram — must not attempt a send for them,
    and the sales-staff CompanyUser without a chat_id must be skipped too."""
    from core.models import Notification
    from core.services.telegram import notify_company_owners

    assert tenant_a.owner.telegram_chat_id == ""
    assert tenant_a.staff.telegram_chat_id == ""

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        notify_company_owners(tenant_a.company, subject="x", body="y")
        mock_post.assert_not_called()
    assert not Notification.objects.filter(channel=Notification.Channel.TELEGRAM).exists()


@override_settings(ENABLE_TELEGRAM=True, TELEGRAM_BOT_TOKEN="dummy-token")
def test_notify_company_owners_sends_only_to_linked_recipients(tenant_a):
    from core.models import Notification
    from core.services.telegram import notify_company_owners

    tenant_a.staff.telegram_chat_id = "222"
    tenant_a.staff.save(update_fields=["telegram_chat_id"])

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        notify_company_owners(tenant_a.company, subject="x", body="y")

    assert mock_post.call_count == 1
    sent = Notification.objects.filter(channel=Notification.Channel.TELEGRAM)
    assert sent.count() == 1
    assert sent.first().recipient == "222"


# --- authenticated-only endpoints -------------------------------------------


def test_telegram_endpoints_require_authentication():
    c = APIClient()
    assert c.get("/api/v1/telegram/status/").status_code in (401, 403)
    assert c.post("/api/v1/telegram/link/").status_code in (401, 403)
    assert c.post("/api/v1/telegram/unlink/").status_code in (401, 403)


@override_settings(ENABLE_TELEGRAM=True, TELEGRAM_BOT_USERNAME="")
def test_telegram_link_fails_without_bot_username_configured(tenant_a):
    c = APIClient()
    c.force_authenticate(user=tenant_a.owner)
    resp = c.post("/api/v1/telegram/link/")
    assert resp.status_code == 400
    # A rejected link request must not consume/burn a code for a later retry.
    tenant_a.owner.refresh_from_db()
    assert tenant_a.owner.telegram_link_code == ""
