"""OTP hashing helpers — store HMAC-SHA256 digests, never plaintext codes."""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings

PHONE_INVALID_MESSAGE = "Enter a valid mobile number with country code, e.g. +91 98765 43210."


def _pepper() -> bytes:
    pepper = getattr(settings, "OTP_PEPPER", None) or settings.SECRET_KEY
    return str(pepper).encode("utf-8")


def hash_otp(code: str) -> str:
    """Return HMAC-SHA256 hex digest of ``code`` with OTP_PEPPER."""
    return hmac.new(_pepper(), (code or "").encode("utf-8"), hashlib.sha256).hexdigest()


def verify_otp(stored: str, code: str) -> bool:
    """Constant-time compare of stored digest against ``hash_otp(code)``."""
    if not stored:
        return False
    return hmac.compare_digest(str(stored), hash_otp(code))


def phone_lookup_values(phone: str) -> list[str]:
    import re

    variants = {phone.strip()} if phone else set()
    digits = re.sub(r"\D", "", phone or "")
    if digits:
        variants.add(digits)
        if digits.startswith("91") and len(digits) == 12:
            variants.add(digits[2:])
            variants.add(f"+{digits}")
        if len(digits) == 10:
            variants.add(f"+91{digits}")
            variants.add(f"91{digits}")
        if digits.startswith("0") and len(digits) == 11:
            national = digits[1:]
            variants.add(national)
            variants.add(f"+91{national}")
            variants.add(f"91{national}")
    return [v for v in variants if v]


def normalize_e164(phone: str) -> str:
    """BB-000633: accept E.164 or 10-digit Indian mobiles → +91XXXXXXXXXX.

    Also forgives the ways people actually type numbers: spaces, hyphens,
    brackets and dots; a trunk ``0`` (``09876543210``, ``+91 098765 43210``);
    and the ``00`` international prefix (``0044 20 7946 0958``).
    """
    import re

    raw = re.sub(r"[\s\-().]", "", (phone or "").strip())
    if raw.startswith("00"):
        raw = f"+{raw[2:]}"
    if re.fullmatch(r"\+910[6-9]\d{9}", raw):
        return f"+91{raw[4:]}"
    if re.fullmatch(r"\+[1-9]\d{7,14}", raw):
        return raw
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}"
    if digits.startswith("91") and len(digits) == 12:
        return f"+{digits}"
    raise ValueError(PHONE_INVALID_MESSAGE)


def canonicalize_user_phone(phone: str) -> str:
    """Blank stays blank; otherwise E.164 so unique+lookup cannot collide."""
    raw = (phone or "").strip()
    if not raw:
        return ""
    return normalize_e164(raw)


def canonicalize_new_phone(phone: str) -> str:
    """Like ``canonicalize_user_phone``, but stricter for a number being entered now.

    ``normalize_e164`` takes any ``+`` and 8–15 digits so that numbers already
    stored keep saving. A new Indian number must be a full mobile:
    +91 then 10 digits starting 6–9.
    """
    import re

    canon = canonicalize_user_phone(phone)
    if canon.startswith("+91") and not re.fullmatch(r"\+91[6-9]\d{9}", canon):
        raise ValueError(PHONE_INVALID_MESSAGE)
    return canon


def phone_taken(*, phone: str, exclude_pk=None) -> bool:
    """True when any user already owns this number (any format)."""
    from accounts.models import User

    variants = phone_lookup_values(phone)
    if not variants:
        return False
    qs = User.objects.filter(phone__in=variants)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def resolve_user_by_phone(phone: str, *, active_only: bool = True):
    """Pick the canonical E.164 row when duplicate formats still exist."""
    from accounts.models import User

    variants = phone_lookup_values(phone)
    if not variants:
        return None
    qs = User.objects.filter(phone__in=variants)
    if active_only:
        qs = qs.filter(is_active=True)
    rows = list(qs.order_by("id"))
    if not rows:
        return None
    try:
        canon = canonicalize_user_phone(phone)
    except ValueError:
        canon = ""
    for user in rows:
        if canon and user.phone == canon:
            return user
        if user.phone.startswith("+"):
            return user
    return rows[0]
