"""Login-time MFA challenge helpers (F-SEC-02). Import-safe: no dependency on views."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response

from .models import CompanyUser, UserMfa

_SALT = "bizboard.mfa.login"
_ENROL_SALT = "bizboard.mfa.enrol"
MFA_TOKEN_MAX_AGE = 300  # seconds the user has to type the code after the password step
ENROL_TOKEN_MAX_AGE = 600
ENROL_MAX_PRESENTATIONS = 8


def mfa_is_enabled(user) -> bool:
    return UserMfa.objects.filter(user=user, confirmed_at__isnull=False).exists()


def make_login_token(user) -> str:
    return signing.dumps({"uid": user.pk}, salt=_SALT)


def load_login_token(token: str) -> int:
    """Return the user id, or raise ``signing.BadSignature`` (includes SignatureExpired)."""
    data = signing.loads(token, salt=_SALT, max_age=MFA_TOKEN_MAX_AGE)
    return int(data["uid"])


def mfa_challenge_response(user) -> Response:
    """200 with NO tokens or cookies: the client must call /auth/mfa/verify/."""
    return Response(
        {
            "mfa_required": True,
            "mfa_token": make_login_token(user),
            "methods": ["totp", "recovery_code"],
            "expires_in": MFA_TOKEN_MAX_AGE,
        },
        status=status.HTTP_200_OK,
    )


def user_has_money_role(user) -> bool:
    """True when any active membership can post journals or is Owner or Accountant.

    Owner/Admin is the OWNER role. There is no separate Admin role. A Manager
    (and anyone else granted can_post_journals) must enrol too. Sales staff
    stay out unless that flag is turned on for them.
    """
    memberships = CompanyUser.objects.filter(user=user, is_active=True)
    return memberships.filter(
        role__in=(CompanyUser.Role.OWNER, CompanyUser.Role.ACCOUNTANT),
    ).exists() or memberships.filter(can_post_journals=True).exists()


def enrolment_required(user) -> bool:
    if not getattr(settings, "MFA_ENFORCE_FOR_MONEY_ROLES", False):
        return False
    if mfa_is_enabled(user):
        return False
    return user_has_money_role(user)


def make_enrol_token(user) -> str:
    return signing.dumps({"uid": user.pk, "jti": str(uuid.uuid4())}, salt=_ENROL_SALT)


def load_enrol_token(token: str) -> tuple[int, str]:
    data = signing.loads(token, salt=_ENROL_SALT, max_age=ENROL_TOKEN_MAX_AGE)
    return int(data["uid"]), str(data["jti"])


def _enrol_count_key(jti: str) -> str:
    return f"mfa_enrol_n:{jti}"


def _enrol_burned_key(jti: str) -> str:
    return f"mfa_enrol_burned:{jti}"


def note_enrol_presentation(jti: str) -> bool:
    """Count one use of an enrol token. False at the 9th presentation or after confirm."""
    if cache.get(_enrol_burned_key(jti)):
        return False
    key = _enrol_count_key(jti)
    seen = int(cache.get(key, 0) or 0)
    if seen >= ENROL_MAX_PRESENTATIONS:
        return False
    cache.set(key, seen + 1, ENROL_TOKEN_MAX_AGE)
    return True


def burn_enrol_jti(jti: str) -> None:
    cache.set(_enrol_burned_key(jti), 1, ENROL_TOKEN_MAX_AGE)
    cache.delete(_enrol_count_key(jti))


def mfa_enrollment_response(user) -> Response:
    """200 with NO cookies. The enrol token is not a session."""
    return Response(
        {
            "mfa_enrollment_required": True,
            "enrol_token": make_enrol_token(user),
            "expires_in": ENROL_TOKEN_MAX_AGE,
        },
        status=status.HTTP_200_OK,
    )


def check_second_factor(rec: UserMfa, *, code: str = "", recovery_code: str = "") -> bool:
    """Validate a TOTP or recovery code and burn it. Caller holds the row lock."""
    from . import mfa

    if recovery_code:
        remaining = mfa.consume_recovery_code(list(rec.recovery_hashes or []), recovery_code)
        if remaining is None:
            return False
        rec.recovery_hashes = remaining
        rec.save(update_fields=["recovery_hashes", "updated_at"])
        return True
    secret = mfa.decrypt_secret(rec.secret_enc)
    step = mfa.verify_totp(secret, code, last_used_step=rec.last_used_step)
    if step is None:
        return False
    rec.last_used_step = step
    rec.save(update_fields=["last_used_step", "updated_at"])
    return True
