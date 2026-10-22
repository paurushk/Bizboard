"""Fernet encrypt/decrypt for company GSP credentials (never log plaintext)."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

logger = logging.getLogger(__name__)


def gsp_keys() -> list[str]:
    """WP-B3: GSP_FERNET_KEY may list several keys, newest first ("new,old"). The first encrypts;
    every key decrypts, so rotation is: prepend the new key, run rotate_encrypted_fields, drop the old."""
    raw = getattr(settings, "GSP_FERNET_KEY", None) or ""
    raw = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    return [k.strip() for k in raw.split(",") if k.strip()]


def _fernet() -> MultiFernet:
    keys = gsp_keys()
    if keys:
        return MultiFernet([Fernet(k.encode("utf-8")) for k in keys])
    env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
    # BB-000248 / BB-000313: never derive Fernet from SECRET_KEY outside local DEBUG.
    if env in ("production", "staging") or not getattr(settings, "DEBUG", True):
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "GSP_FERNET_KEY is required when DEBUG=False or in production/staging."
        )
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return MultiFernet([Fernet(base64.urlsafe_b64encode(digest))])


def encrypt_gsp_credentials(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    token = _fernet().encrypt(json.dumps(payload).encode("utf-8"))
    return token.decode("utf-8")


def decrypt_gsp_credentials(ciphertext: str) -> dict[str, Any]:
    if not (ciphertext or "").strip():
        return {}
    if str(ciphertext).startswith("gcm1."):
        from planwave.services import open_credential_blob

        return open_credential_blob(ciphertext)
    try:
        raw = _fernet().decrypt(ciphertext.encode("utf-8"))
    except (InvalidToken, ValueError):
        logger.warning("GSP credentials decrypt failed (invalid token or corrupt ciphertext).")
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def gsp_credentials_configured(ciphertext: str) -> bool:
    return bool((ciphertext or "").strip())
