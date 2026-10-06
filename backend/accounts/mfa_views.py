"""MFA enrolment and login-verification endpoints (F-SEC-02)."""

from __future__ import annotations

from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from core.exceptions import TooManyLoginAttemptsError
from core.services.audit import AuditService

from . import mfa
from .mfa_service import (
    burn_enrol_jti,
    check_second_factor as _check_second_factor,
    load_enrol_token,
    load_login_token,
    note_enrol_presentation,
)
from .models import User, UserMfa
from .views import (
    _active_membership,
    _complete_login,
    _incr_with_ttl,
)


# Stricter than the password limit: a 6-digit code (3 valid values per window) is far
# weaker than a password, so 5 wrong codes lock the second factor for the fail window.
MFA_FAIL_LIMIT = 5


def _fail_key(user_id) -> str:
    return f"mfa_fail:{user_id}"


def _audit(user, action: str) -> None:
    membership = _active_membership(user)
    AuditService.log(
        company=membership.company if membership else None,
        user=user, action=action, entity_type="User", entity_id=user.id,
    )


def _actor_for_enrolment(request, *, remember_jti: bool):
    """Session user, or the user named by an enrol token. Other credentials are ignored."""
    token = ""
    if isinstance(request.data, dict):
        token = str(request.data.get("enrol_token") or request.data.get("enrolToken") or "")
    if token:
        try:
            uid, jti = load_enrol_token(token)
        except signing.BadSignature as exc:
            raise AuthenticationFailed("Enrolment session expired. Sign in again.") from exc
        if not note_enrol_presentation(jti):
            raise AuthenticationFailed("Enrolment session expired. Sign in again.")
        user = User.objects.filter(pk=uid, is_active=True).first()
        if user is None:
            raise AuthenticationFailed("Enrolment session expired. Sign in again.")
        if remember_jti:
            request.mfa_enrol_jti = jti
        request.mfa_via_enrol_token = True
        return user
    if getattr(request.user, "is_authenticated", False):
        request.mfa_via_enrol_token = False
        return request.user
    raise AuthenticationFailed("Authentication credentials were not provided.")


def _require_session_password(request, user) -> None:
    """BUG-SEC-010: a stolen session must not bind an authenticator.

    An enrol token was issued after a password check in this process, so that
    path does not ask again. A logged-in session does.
    """
    if getattr(request, "mfa_via_enrol_token", False):
        return
    password = ""
    if isinstance(request.data, dict):
        password = request.data.get("password") or ""
    if not user.check_password(password):
        raise ValidationError({"password": "Incorrect password."})


class MfaStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rec = UserMfa.objects.filter(user=request.user).first()
        return Response({
            "enabled": bool(rec and rec.is_active),
            "pending_setup": bool(rec and not rec.is_active),
            "recovery_codes_remaining": len(rec.recovery_hashes or []) if rec and rec.is_active else 0,
        })


class MfaSetupView(APIView):
    """Start (or restart) enrolment: returns a fresh secret + QR. Nothing is enforced
    until /auth/mfa/confirm/ proves the user can generate codes.

    An enrol token is accepted here and only here (plus confirm). It is not a session.
    """

    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        user = _actor_for_enrolment(request, remember_jti=False)
        _require_session_password(request, user)
        existing = UserMfa.objects.filter(user=user).first()
        if existing and existing.is_active:
            raise ValidationError({"detail": "Two-step verification is already enabled. Disable it first."})
        secret = mfa.generate_secret()
        UserMfa.objects.update_or_create(
            user=user,
            defaults={"secret_enc": mfa.encrypt_secret(secret), "confirmed_at": None,
                      "last_used_step": 0, "recovery_hashes": []},
        )
        uri = mfa.provisioning_uri(user.email, secret)
        return Response({"secret": secret, "otpauth_uri": uri, "qr_png": mfa.qr_png_data_uri(uri)})


class MfaConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        user = _actor_for_enrolment(request, remember_jti=True)
        _require_session_password(request, user)
        code = str(request.data.get("code") or "")
        with transaction.atomic():
            rec = UserMfa.objects.select_for_update().filter(user=user).first()
            if rec is None or rec.is_active:
                raise ValidationError({"detail": "Start setup first."})
            step = mfa.verify_totp(mfa.decrypt_secret(rec.secret_enc), code)
            if step is None:
                raise ValidationError({"code": "That code is not valid. Check the clock on your phone and try again."})
            codes, hashes = mfa.new_recovery_codes()
            rec.confirmed_at = timezone.now()
            rec.last_used_step = step
            rec.recovery_hashes = hashes
            rec.save(update_fields=["confirmed_at", "last_used_step", "recovery_hashes", "updated_at"])
        jti = getattr(request, "mfa_enrol_jti", None)
        if jti:
            burn_enrol_jti(jti)
        _audit(user, "MFA_ENABLED")
        return Response({"enabled": True, "recovery_codes": codes}, status=status.HTTP_200_OK)


class _ReauthMixin:
    """Disabling or regenerating needs the password AND a current second factor, so a
    stolen session alone cannot remove the protection."""

    def _reauth(self, request) -> UserMfa:
        password = request.data.get("password") or ""
        if not request.user.check_password(password):
            raise ValidationError({"password": "Incorrect password."})
        if cache.get(_fail_key(request.user.pk), 0) >= MFA_FAIL_LIMIT:
            raise TooManyLoginAttemptsError()
        rec = UserMfa.objects.select_for_update().filter(user=request.user, confirmed_at__isnull=False).first()
        if rec is None:
            raise ValidationError({"detail": "Two-step verification is not enabled."})
        ok = _check_second_factor(
            rec, code=str(request.data.get("code") or ""), recovery_code=str(request.data.get("recovery_code") or ""),
        )
        if not ok:
            _incr_with_ttl(_fail_key(request.user.pk))
            raise ValidationError({"code": "That code is not valid."})
        cache.delete(_fail_key(request.user.pk))
        return rec


class MfaDisableView(_ReauthMixin, APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "login"

    def post(self, request):
        with transaction.atomic():
            rec = self._reauth(request)
            rec.delete()
        _audit(request.user, "MFA_DISABLED")
        return Response({"enabled": False})


class MfaRecoveryCodesView(_ReauthMixin, APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "login"

    def post(self, request):
        with transaction.atomic():
            rec = self._reauth(request)
            codes, hashes = mfa.new_recovery_codes()
            rec.recovery_hashes = hashes
            rec.save(update_fields=["recovery_hashes", "updated_at"])
        _audit(request.user, "MFA_RECOVERY_CODES_REGENERATED")
        return Response({"recovery_codes": codes})


class MfaLoginVerifyView(APIView):
    """Second step of login. Body: ``mfa_token`` + (``code`` | ``recovery_code``)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "login"

    def get_authenticate_header(self, request):
        # Same as SimpleJWT's login view: without a scheme DRF turns a failed
        # authentication into 403 instead of the 401 clients expect from /auth/*.
        return 'Bearer realm="api"'

    def post(self, request):
        token = str(request.data.get("mfa_token") or "")
        try:
            uid = load_login_token(token)
        except signing.BadSignature:
            raise AuthenticationFailed("Your sign-in session expired. Enter your password again.")
        user = User.objects.filter(pk=uid, is_active=True).first()
        if user is None:
            raise AuthenticationFailed("Your sign-in session expired. Enter your password again.")
        if cache.get(_fail_key(uid), 0) >= MFA_FAIL_LIMIT:
            raise TooManyLoginAttemptsError()
        with transaction.atomic():
            rec = UserMfa.objects.select_for_update().filter(user=user, confirmed_at__isnull=False).first()
            ok = rec is not None and _check_second_factor(
                rec, code=str(request.data.get("code") or ""), recovery_code=str(request.data.get("recovery_code") or ""),
            )
        if not ok:
            _incr_with_ttl(_fail_key(uid))
            raise AuthenticationFailed("That verification code is not valid.")
        cache.delete(_fail_key(uid))
        refresh = RefreshToken.for_user(user)
        refresh["sv"] = int(getattr(user, "session_version", 0) or 0)
        response = Response({"refresh": str(refresh), "access": str(refresh.access_token)})
        return _complete_login(request, response, user)
