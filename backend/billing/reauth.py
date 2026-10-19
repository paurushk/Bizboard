"""Re-checking who is at the keyboard before a destructive action (SET-06).

A stolen session or an unattended screen must not be enough to suspend a workspace. The owner
re-enters their password and, if two-step verification is on for their account, a current code.
Wrong attempts are counted, so this cannot be used to guess the password.
"""

from __future__ import annotations

from django.core.cache import cache
from django.db import transaction
from rest_framework.exceptions import ValidationError

from core.exceptions import BusinessRuleError

REAUTH_FAIL_LIMIT = 5
REAUTH_WINDOW_SECONDS = 15 * 60


def _fail_key(user_id) -> str:
    return f"reauth_fail:{user_id}"


def _count_failure(user_id) -> None:
    key = _fail_key(user_id)
    if not cache.add(key, 1, REAUTH_WINDOW_SECONDS):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, REAUTH_WINDOW_SECONDS)


def require_reauth(request) -> None:
    """Raise unless ``password`` (and ``code`` / ``recovery_code`` when 2FA is on) are right."""
    from accounts.mfa_service import check_second_factor
    from accounts.models import UserMfa

    user = request.user
    if not user.has_usable_password():
        raise BusinessRuleError(
            "Set a password in your profile first: this action asks for it to confirm it is you.",
            code="PASSWORD_NOT_SET",
        )
    if cache.get(_fail_key(user.pk), 0) >= REAUTH_FAIL_LIMIT:
        raise BusinessRuleError("Too many wrong attempts. Wait a few minutes and try again.", code="REAUTH_LOCKED")
    if not user.check_password(str(request.data.get("password") or "")):
        _count_failure(user.pk)
        raise ValidationError({"password": "Incorrect password."})
    with transaction.atomic():
        mfa = UserMfa.objects.select_for_update().filter(user=user, confirmed_at__isnull=False).first()
        if mfa is not None:
            ok = check_second_factor(
                mfa,
                code=str(request.data.get("code") or ""),
                recovery_code=str(request.data.get("recovery_code") or ""),
            )
            if not ok:
                _count_failure(user.pk)
                raise ValidationError({"code": "Enter a current two-step verification code."})
    cache.delete(_fail_key(user.pk))
