"""TOTP multi-factor authentication primitives (F-SEC-02).

RFC 6238 time-based one-time passwords (HMAC-SHA1, 30 s step, 6 digits) implemented
on the standard library, so no new dependency enters the auth path. Compatible with
Google Authenticator, Microsoft Authenticator, Authy, 1Password, ...

Design notes
* The shared secret is encrypted at rest (Fernet). Key = ``MFA_ENCRYPTION_KEY`` (one key,
  or several comma-separated, newest first, for rotation). If unset the key is derived
  from ``SECRET_KEY`` - fine for dev/test, but then rotating SECRET_KEY locks MFA users
  out, so production should set MFA_ENCRYPTION_KEY explicitly.
* A code is accepted at most once: ``last_used_step`` rejects replay of the same step.
* Recovery codes are single-use, stored only as keyed hashes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1  # accept the previous and next step to tolerate clock drift
RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


# --- TOTP (RFC 4226 / 6238) -----------------------------------------------------

def generate_secret() -> str:
    """160-bit random secret, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def _key_bytes(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(key: bytes, counter: int, digits: int = DIGITS) -> str:
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    binary = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** digits)).zfill(digits)


def totp_at(secret_b32: str, at: float | None = None, *, digits: int = DIGITS) -> str:
    t = time.time() if at is None else at
    return hotp(_key_bytes(secret_b32), int(t // STEP_SECONDS), digits)


def verify_totp(secret_b32: str, code: str, *, last_used_step: int = 0, now: float | None = None) -> int | None:
    """Return the matched time step, or None. A step <= ``last_used_step`` is a replay."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != DIGITS:
        return None
    key = _key_bytes(secret_b32)
    current = int((time.time() if now is None else now) // STEP_SECONDS)
    matched = None
    for step in range(current - WINDOW, current + WINDOW + 1):
        # compare every candidate (constant-time) so timing does not reveal which step hit
        if hmac.compare_digest(hotp(key, step), code) and step > last_used_step:
            matched = step
    return matched


def provisioning_uri(email: str, secret_b32: str, issuer: str = "BizBoard") -> str:
    label = quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"


def qr_png_data_uri(text: str) -> str:
    """The provisioning URI as a PNG data: URI, so the SPA needs no QR library."""
    import qrcode

    img = qrcode.make(text, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# --- secret encryption ---------------------------------------------------------

def _fernet() -> MultiFernet:
    raw = (getattr(settings, "MFA_ENCRYPTION_KEY", "") or "").strip()
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        derived = hashlib.sha256(("bizboard-mfa|" + settings.SECRET_KEY).encode("utf-8")).digest()
        keys = [base64.urlsafe_b64encode(derived).decode("ascii")]
    return MultiFernet([Fernet(k.encode("ascii")) for k in keys])


def encrypt_secret(secret_b32: str) -> str:
    return _fernet().encrypt(secret_b32.encode("ascii")).decode("ascii")


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("ascii")
    except InvalidToken as exc:  # wrong/rotated key: fail closed, never treat as "no MFA"
        raise ValueError("MFA secret cannot be decrypted with the configured key") from exc


# --- recovery codes ---------------------------------------------------------------

def _hash_recovery(code: str) -> str:
    norm = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    pepper = (getattr(settings, "OTP_PEPPER", "") or settings.SECRET_KEY).encode("utf-8")
    return hmac.new(pepper, norm.encode("utf-8"), hashlib.sha256).hexdigest()


def new_recovery_codes() -> tuple[list[str], list[str]]:
    """Return (plaintext codes shown once, hashes to store)."""
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes, [_hash_recovery(c) for c in codes]


def consume_recovery_code(hashes: list[str], code: str) -> list[str] | None:
    """Return the hash list without ``code`` if it matched, else None."""
    target = _hash_recovery(code)
    remaining, matched = [], False
    for h in hashes:
        if not matched and hmac.compare_digest(h, target):
            matched = True
            continue
        remaining.append(h)
    return remaining if matched else None
