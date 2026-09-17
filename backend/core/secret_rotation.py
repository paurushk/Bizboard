"""10.4 — secret-rotation order and a dry-run check. Never mutates secrets."""

from __future__ import annotations

import os

# Rotate in this order so HMAC/JWT verifiers keep accepting the previous value
# until the new one is deployed. Human still performs the live cut.
ROTATION_ORDER = (
    "SECRET_KEY",
    "OTP_PEPPER",
    "GSP_FERNET_KEY",
    "TENANT_EXPORT_FERNET_KEY",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
    "SANDBOX_WEBHOOK_SECRET",
    "CASHFREE_SECRET_KEY",
    "PAYU_MERCHANT_SALT",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
)


def check_required_secrets(environ: dict | None = None) -> list[str]:
    """Return names that are missing or placeholder. Empty list = pass."""
    # Reuse settings.py's own placeholder vocabulary (BUG-704's fix) instead
    # of a second, narrower list here: a value settings.py's boot-time guard
    # would refuse to start with must not read as "rotation ready" in this
    # dry-run check too.
    from config.settings import _KNOWN_PLACEHOLDER_SECRETS

    env = environ if environ is not None else os.environ
    missing: list[str] = []
    placeholders = {"", "changeme", "change-me", "todo", "replace-me", "xxx"} | {
        value.strip().lower() for value in _KNOWN_PLACEHOLDER_SECRETS
    }
    for name in ROTATION_ORDER:
        raw = str(env.get(name, "") or "").strip()
        if raw.lower() in placeholders or raw.startswith("REPLACE"):
            missing.append(name)
            continue
        # settings.py additionally requires SECRET_KEY specifically to be
        # 40+ chars; mirror that one name-specific rule here too.
        if name == "SECRET_KEY" and len(raw) < 40:
            missing.append(name)
    return missing
