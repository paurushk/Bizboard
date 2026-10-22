"""WP-AB2: a bot check (Cloudflare Turnstile) on sign-up, OTP and password reset.

The per-IP throttles stop one client; a script rotating IPs can still create accounts and trigger
SMS. The four pre-login endpoints that create accounts or send messages call ``require_human``:

- ``BOT_CHECK_PROVIDER=turnstile`` verifies the widget token with Cloudflare (5 s timeout).
  Production fails closed when Cloudflare can't be reached.
- ``none`` passes everything (local development and tests). Production refuses to boot with it
  unless ``BOT_CHECK_ALLOW_NONE=1`` (see settings).
- ``stub`` passes only the token ``"ok"`` (unit tests and the golden browser run).

``BOT_CHECK_ENFORCE=0`` is shadow mode: a failed check is logged and counted but not refused, to
watch for false blocks on staging for a week before enforcing.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from core.exceptions import BusinessRuleError

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_FIELD = "bot_token"


class BotCheckFailed(BusinessRuleError):
    """The request did not pass the bot check."""


def _provider() -> str:
    return (getattr(settings, "BOT_CHECK_PROVIDER", "") or "none").strip().lower()


def _event(name: str) -> None:
    try:
        from core.ops_metrics import bump_event

        bump_event(name)
    except Exception:  # noqa: BLE001
        pass


def verify(token: str, remote_ip: str = "") -> bool:
    provider = _provider()
    if provider == "none":
        return True
    if provider == "stub":
        return token == "ok"
    if provider != "turnstile":
        raise BusinessRuleError(f"Unknown BOT_CHECK_PROVIDER '{provider}'.")
    secret = (getattr(settings, "TURNSTILE_SECRET_KEY", "") or "").strip()
    if not secret or not token:
        return False
    data = urllib.parse.urlencode({"secret": secret, "response": token, "remoteip": remote_ip}).encode()
    req = urllib.request.Request(SITEVERIFY_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - fixed Cloudflare HTTPS URL
        payload = json.loads(resp.read().decode("utf-8") or "{}")
    return bool(payload.get("success"))


def require_human(request, *, action: str) -> None:
    """Raise ``BotCheckFailed`` unless the request carries a valid bot-check token."""
    if _provider() == "none":
        return
    data = getattr(request, "data", None) or {}
    token = str(data.get(TOKEN_FIELD) or request.headers.get("X-Bot-Token") or "")
    ip = (request.META.get("REMOTE_ADDR") or "").strip()
    try:
        ok = verify(token, ip)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("Bot check unreachable on %s: %s", action, exc)
        _event(f"bot_check_unavailable_{action}")
        ok = False
    if ok:
        return
    _event(f"bot_check_failed_{action}")
    if not getattr(settings, "BOT_CHECK_ENFORCE", True):
        logger.info("Bot check would have refused %s (shadow mode).", action)
        return
    raise BotCheckFailed(
        "Please complete the check that you are not a robot, then try again.",
        code="BOT_CHECK_FAILED",
    )
