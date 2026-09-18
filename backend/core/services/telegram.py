"""Telegram Bot API client — single platform-wide bot, per-user chat_id linking."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import secrets
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

import requests

LINK_CODE_TTL = timedelta(minutes=15)


@dataclass
class TelegramSendResult:
    mode: str  # "sent" | "unlinked" | "failed"
    raw: dict | None = None


def _bot_token() -> str:
    from django.conf import settings

    return (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()


def send_telegram_message(chat_id: str, text: str) -> TelegramSendResult:
    """Send a plain-text message via the Bot API's sendMessage endpoint."""
    chat_id = (chat_id or "").strip()
    if not chat_id:
        return TelegramSendResult(mode="unlinked")

    token = _bot_token()
    if not token:
        logger.warning("Telegram bot token is not configured; message not sent.")
        return TelegramSendResult(mode="failed", raw={"error": "TELEGRAM_BOT_TOKEN is not configured."})

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text[:4096]},
        timeout=15,
    )
    if resp.status_code >= 400:
        logger.warning("Telegram sendMessage HTTP %s", resp.status_code)
        return TelegramSendResult(
            mode="failed",
            raw={"error": resp.text[:500], "status_code": resp.status_code},
        )
    return TelegramSendResult(mode="sent", raw=resp.json())


def generate_link_code(user) -> str:
    """Issue a short-lived one-time code for the /start deep link handshake."""
    code = secrets.token_urlsafe(12)
    user.telegram_link_code = code
    user.telegram_link_code_expires_at = timezone.now() + LINK_CODE_TTL
    user.save(update_fields=["telegram_link_code", "telegram_link_code_expires_at"])
    return code


def bot_deep_link(code: str) -> str:
    from django.conf import settings

    username = (getattr(settings, "TELEGRAM_BOT_USERNAME", "") or "").strip()
    return f"https://t.me/{username}?start={code}" if username else ""


def resolve_link_code(code: str):
    """Match a /start code to a user and consume it. Returns the User or None."""
    from accounts.models import User

    code = (code or "").strip()
    if not code:
        return None
    user = User.objects.filter(telegram_link_code=code).first()
    if user is None:
        return None
    if not user.telegram_link_code_expires_at or user.telegram_link_code_expires_at < timezone.now():
        return None
    return user


def link_chat_id(user, chat_id: str) -> None:
    user.telegram_chat_id = str(chat_id)
    user.telegram_link_code = ""
    user.telegram_link_code_expires_at = None
    user.save(update_fields=["telegram_chat_id", "telegram_link_code", "telegram_link_code_expires_at"])


def send_ops_alert(text: str) -> TelegramSendResult:
    """Best-effort page to the fixed ops/on-call chat (not a per-user recipient).

    Used by the Sentry/health-check webhook relay — never raises, since a
    failed page must not turn the alert source's webhook call into an error.
    """
    from django.conf import settings

    chat_id = (getattr(settings, "OPS_TELEGRAM_CHAT_ID", "") or "").strip()
    if not chat_id:
        logger.warning("OPS_TELEGRAM_CHAT_ID is not configured; ops alert not sent.")
        return TelegramSendResult(mode="unlinked")
    try:
        return send_telegram_message(chat_id, text)
    except Exception:
        logger.warning("Ops alert Telegram send failed", exc_info=True)
        return TelegramSendResult(mode="failed", raw={"error": "send_telegram_message raised"})


def notify_company_owners(company, *, subject: str, body: str) -> None:
    """Best-effort broadcast to every linked owner/staff user of a company.

    Never raises — this rides alongside an existing email/in-app alert and
    must not break the caller if Telegram is unconfigured or a send fails.
    """
    from accounts.models import CompanyUser
    from core.models import Notification
    from core.services.feature_flags import build_feature_flags
    from core.services.notifications import NotificationService

    flags = build_feature_flags(company=company)
    if not flags.get("ENABLE_TELEGRAM"):
        return

    recipients = (
        CompanyUser.objects.filter(company=company, is_active=True)
        .exclude(user__telegram_chat_id="")
        .select_related("user")
    )
    for cu in recipients:
        try:
            NotificationService.send(
                company=company,
                channel=Notification.Channel.TELEGRAM,
                recipient=cu.user.telegram_chat_id,
                subject=subject,
                body=body,
                user=cu.user,
            )
        except Exception:
            logger.warning("Telegram staff notify failed for user %s", cu.user_id, exc_info=True)
