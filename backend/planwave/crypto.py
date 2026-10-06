"""AES-256-GCM for bank account numbers and tax-portal secrets.

Keys come from PLANWAVE_DATA_KEY (host secret store). Tests and local DEBUG
derive a key from SECRET_KEY. IFSC is never sealed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

PREFIX = "gcm1"
KEY_ID = "k1"


class SealError(Exception):
    pass


def _raw_key() -> bytes:
    raw = (getattr(settings, "PLANWAVE_DATA_KEY", None) or "").strip()
    if raw:
        try:
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except Exception as exc:
            raise ImproperlyConfigured("PLANWAVE_DATA_KEY is not url-safe base64.") from exc
        if len(key) != 32:
            raise ImproperlyConfigured("PLANWAVE_DATA_KEY must decode to 32 bytes.")
        return key
    env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
    if env in ("production", "staging"):
        raise ImproperlyConfigured("PLANWAVE_DATA_KEY is required in production and staging.")
    return hashlib.sha256(b"planwave:" + settings.SECRET_KEY.encode("utf-8")).digest()


def _looks_sealed(text: str) -> bool:
    """Structurally a sealed blob: prefix, key id, and base64 for at least nonce plus tag."""
    try:
        _prefix, _key_id, blob = text.split(".", 2)
        raw = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
    except (ValueError, binascii.Error):
        return False
    return len(raw) >= 12 + 16


def seal(plaintext: str, *, key: bytes | None = None, key_id: str = KEY_ID) -> str:
    if plaintext is None:
        return ""
    text = str(plaintext)
    if text == "":
        return text
    if text.startswith(f"{PREFIX}."):
        # Already sealed? Only if it really opens. Otherwise this is user text that merely
        # looks like our prefix, and returning it as-is would store it in the clear.
        try:
            open_secret(text, key=key)
            return text
        except (SealError, ImproperlyConfigured):
            if _looks_sealed(text):
                # A real blob that this key cannot open (rotated key, damaged value). Wrapping
                # it again would bury it under a second layer that reveal can never peel.
                import logging

                logging.getLogger(__name__).error("sealed value could not be opened with the current key; left unchanged")
                return text
    aes = AESGCM(key or _raw_key())
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, text.encode("utf-8"), key_id.encode("utf-8"))
    blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
    return f"{PREFIX}.{key_id}.{blob}"


def open_secret(token: str, *, key: bytes | None = None) -> str:
    if not (token or "").strip():
        return ""
    if not str(token).startswith(f"{PREFIX}."):
        return str(token)
    try:
        _prefix, key_id, blob = str(token).split(".", 2)
        raw = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
    except (ValueError, binascii.Error) as exc:
        raise SealError("truncated ciphertext") from exc
    nonce, ct = raw[:12], raw[12:]
    try:
        plain = AESGCM(key or _raw_key()).decrypt(nonce, ct, key_id.encode("utf-8"))
    except (InvalidTag, ValueError) as exc:  # ValueError: nonce length out of range
        raise SealError("authentication failed") from exc
    return plain.decode("utf-8")


def last4(plaintext: str) -> str:
    digits = "".join(ch for ch in (plaintext or "") if ch.isdigit())
    return digits[-4:]


def seal_bank_account(value: str) -> str:
    return seal(value or "")


def reveal_bank_account(value: str) -> str:
    try:
        return open_secret(value or "")
    except SealError:
        # An empty number hides a wrong or rotated key. Say so instead of failing silently.
        import logging

        logging.getLogger(__name__).error("bank account could not be opened: key mismatch or damaged value")
        return ""
