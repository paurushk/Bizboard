"""WP-AB1: per-number, per-range and platform caps in front of every SMS send.

The per-IP throttle (``otp``) and the per-phone cooldown in ``accounts.views`` stop one client.
SMS pumping rotates IPs and phone numbers, so this guard counts at the provider layer, for every
SMS (OTP and texts), against four counters in the Django cache (Redis in staging/production):

- this phone, this hour and today;
- this number range (the first ``SMS_RANGE_PREFIX_LEN`` digits after +91), this hour;
- the whole platform, today.

An attempt counts whether the provider then succeeds, fails or times out: a broken provider or an
attacker hammering it must still use up the budget. A send the guard refuses is rolled back from
every counter (nothing left the building) and raises ``SmsBlocked``; callers already answer with
the same message either way, so a refusal is not an oracle.

``SMS_DISABLED`` (env) or the runtime kill switch (``manage.py sms_guard kill on``) refuses every
send. If the cache is down, sends are refused (``SMS_GUARD_FAIL_CLOSED``, default on).
"""

from __future__ import annotations

import hashlib
import logging
import math

from django.conf import settings
from django.utils import timezone

from core.exceptions import BusinessRuleError

logger = logging.getLogger(__name__)

KILL_KEY = "sms:guard:kill"
_HOUR_TTL = 2 * 60 * 60
_DAY_TTL = 48 * 60 * 60


class SmsBlocked(BusinessRuleError):
    """The SMS was refused before it was sent (cap reached, kill switch, counter store down)."""


def _digits(phone: str) -> str:
    """Digits with the Indian country code. Customer phones are often stored as 10 digits."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        digits = "91" + digits
    return digits


def _is_indian(digits: str) -> bool:
    return len(digits) == 12 and digits.startswith("91")


def _phone_id(digits: str) -> str:
    # Keys must not carry the raw number.
    return hashlib.sha256(digits.encode()).hexdigest()[:20]


def _range_id(digits: str) -> str:
    width = max(1, int(getattr(settings, "SMS_RANGE_PREFIX_LEN", 4) or 4))
    return digits[2 : 2 + width] if _is_indian(digits) else digits[:width]


def _event(name: str) -> None:
    try:
        from core.ops_metrics import bump_event

        bump_event(name)
    except Exception:  # noqa: BLE001 - metrics must never break a send
        pass


def kill_switch_on() -> bool:
    if getattr(settings, "SMS_DISABLED", False):
        return True
    from django.core.cache import cache

    return bool(cache.get(KILL_KEY))


def set_kill_switch(on: bool) -> None:
    from django.core.cache import cache

    if on:
        cache.set(KILL_KEY, 1, None)
    else:
        cache.delete(KILL_KEY)


# Share of the platform's daily cap that bulk texts (payment reminders) may use; the rest is kept
# for sign-in codes, so a heavy reminder day never locks owners out of OTP sign-in.
BULK_PLATFORM_SHARE = 0.9


def _counters(digits: str, purpose: str = "otp") -> list[tuple[str, int, int, str]]:
    now = timezone.localtime()
    hour = now.strftime("%Y%m%d%H")
    day = now.date().isoformat()
    pid = _phone_id(digits)
    # Sign-in codes and other texts have separate number-series budgets: the hourly reminder run
    # (thousands of customers, many in one series) must not use up the series for OTP.
    cls = "otp" if purpose == "otp" else "msg"
    platform_cap = int(getattr(settings, "SMS_PLATFORM_DAILY_CAP", 0) or 0)
    if platform_cap and cls == "msg":
        platform_cap = max(1, math.floor(platform_cap * BULK_PLATFORM_SHARE))
    return [
        (f"sms:ph:h:{hour}:{pid}", int(getattr(settings, "SMS_PER_PHONE_HOUR", 0) or 0), _HOUR_TTL, "phone_hour"),
        (f"sms:ph:d:{day}:{pid}", int(getattr(settings, "SMS_PER_PHONE_DAY", 0) or 0), _DAY_TTL, "phone_day"),
        (f"sms:rg:h:{hour}:{cls}:{_range_id(digits)}", int(getattr(settings, "SMS_PER_RANGE_HOUR", 0) or 0),
         _HOUR_TTL, "range_hour"),
        (f"sms:pl:d:{day}", platform_cap, _DAY_TTL, "platform_day"),
    ]


def _block(reason: str, message: str) -> SmsBlocked:
    _event(f"sms_blocked_{reason}")
    logger.warning("SMS refused by guard: %s", reason)
    return SmsBlocked(message, code="SMS_BLOCKED")


def check_and_count(phone: str, purpose: str) -> None:
    """Count one SMS attempt for ``phone`` or raise ``SmsBlocked``. Call right before the provider."""
    from core.services.counters import incr

    digits = _digits(phone)
    try:
        if kill_switch_on():
            raise _block("disabled", "SMS is paused right now. Try again later.")
    except SmsBlocked:
        raise
    except Exception as exc:  # noqa: BLE001 - counter store down
        if getattr(settings, "SMS_GUARD_FAIL_CLOSED", True):
            raise _block("unavailable", "SMS is unavailable right now. Try again in a few minutes.") from exc
        return
    if not _is_indian(digits) and not getattr(settings, "SMS_ALLOW_INTERNATIONAL", False):
        raise _block("international", "SMS can only be sent to Indian mobile numbers.")

    done: list[tuple[str, int]] = []
    platform_total = 0
    try:
        for key, cap, ttl, reason in _counters(digits, purpose):
            total = incr(key, 1, ttl)
            done.append((key, ttl))
            if reason == "platform_day":
                platform_total = total
            if cap and total > cap:
                for k, k_ttl in done:  # a refused attempt uses up none of the budgets
                    incr(k, -1, k_ttl)
                raise _block(reason, "Too many SMS to this number. Try again later.")
    except SmsBlocked:
        raise
    except Exception as exc:  # noqa: BLE001 - counter store down
        for k, k_ttl in done:
            try:
                incr(k, -1, k_ttl)
            except Exception:  # noqa: BLE001
                pass
        if getattr(settings, "SMS_GUARD_FAIL_CLOSED", True):
            raise _block("unavailable", "SMS is unavailable right now. Try again in a few minutes.") from exc
        return

    cap = int(getattr(settings, "SMS_PLATFORM_DAILY_CAP", 0) or 0)
    if cap and platform_total == math.ceil(cap * 0.8):
        _event("sms_platform_cap_80")
        logger.warning("SMS platform use reached 80%% of today's cap (%s).", cap)
    _event(f"sms_attempt_{purpose}")


def record_result(purpose: str, *, ok: bool) -> None:
    _event(f"sms_sent_{purpose}" if ok else f"sms_failed_{purpose}")


def status() -> dict:
    """Today's platform use and the kill switch, for ``manage.py sms_guard status``."""
    from django.core.cache import cache

    day = timezone.localdate().isoformat()
    return {
        "kill_switch": kill_switch_on(),
        "platform_today": int(cache.get(f"sms:pl:d:{day}") or 0),
        "platform_cap": int(getattr(settings, "SMS_PLATFORM_DAILY_CAP", 0) or 0),
    }
