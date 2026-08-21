"""OTP hashing helpers — store HMAC-SHA256 digests, never plaintext codes."""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings


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
    return [v for v in variants if v]


def normalize_e164(phone: str) -> str:
    """BB-000633: accept E.164 or 10-digit Indian mobiles → +91XXXXXXXXXX."""
    import re

    raw = (phone or "").strip().replace(" ", "").replace("-", "")
    if re.fullmatch(r"\+[1-9]\d{7,14}", raw):
        return raw
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}"
    if digits.startswith("91") and len(digits) == 12:
        return f"+{digits}"
    raise ValueError("Phone must be E.164 (e.g. +919876543210).")
