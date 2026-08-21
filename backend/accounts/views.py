import secrets
import uuid

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.exceptions import (
    OtpExpiredError,
    OtpInvalidError,
    OtpTooManyAttemptsError,
    TooManyLoginAttemptsError,
)
from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.audit import AuditService
from core.services.sms import SmsProvider

from .models import Company, CompanyGstin, CompanyUser, InviteJti, OtpChallenge, User
from .otp_utils import hash_otp, normalize_e164, phone_lookup_values, verify_otp
from .serializers import (
    CompanyGstinSerializer,
    CompanySerializer,
    CompanySerializerStaff,
    CompanyUserSerializer,
    InviteUserSerializer,
    MeSerializer,
    RegisterSerializer,
)


def _tokens_for_user(user):
    """Issue access + refresh JWTs. Refresh is cookie-only in API responses (BB-000257)."""
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


_INVITE_SALT = "bizboard.invite.v1"
_INVITE_MAX_AGE = 7 * 24 * 3600


def _make_invite_token(*, user_id: int, company_id: int, membership_id: int) -> str:
    jti = str(uuid.uuid4())
    token = signing.dumps(
        {
            "uid": user_id,
            "cid": company_id,
            "mid": membership_id,
            "jti": jti,
        },
        salt=_INVITE_SALT,
    )
    InviteJti.objects.create(
        jti=jti,
        membership_id=membership_id,
        expires_at=timezone.now() + timezone.timedelta(seconds=_INVITE_MAX_AGE),
    )
    return token


def _invite_url(token: str) -> str:
    base = getattr(settings, "FRONTEND_URL", "").rstrip("/") or "http://localhost:5173"
    return f"{base}/invite?token={token}"


def _load_invite_token(token: str) -> dict:
    return signing.loads(token, salt=_INVITE_SALT, max_age=_INVITE_MAX_AGE)


def _set_refresh_cookie(response, refresh_token: str):
    """BB-000257: store refresh JWT in httpOnly cookie."""
    max_age = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        path=settings.JWT_REFRESH_COOKIE_PATH,
    )
    return response


def _set_access_cookie(response, access_token: str):
    """BB-000375: access JWT in httpOnly cookie (not readable by XSS)."""
    max_age = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
    response.set_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        access_token,
        max_age=max_age,
        httponly=True,
        secure=bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        path=getattr(settings, "JWT_ACCESS_COOKIE_PATH", "/"),
    )
    return response


def _clear_auth_cookies(response):
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        path=settings.JWT_REFRESH_COOKIE_PATH,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
    )
    response.delete_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        path=getattr(settings, "JWT_ACCESS_COOKIE_PATH", "/"),
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
    )
    return response


def _clear_refresh_cookie(response):
    return _clear_auth_cookies(response)


def _ensure_csrf_cookie(request):
    """BB-000602: mark response to set csrftoken (readable by SPA)."""
    get_token(request)


def _active_membership(user):
    qs = user.company_memberships.filter(is_active=True).select_related("company")
    if user.active_company_id:
        m = qs.filter(company_id=user.active_company_id).order_by("id").first()
        if m:
            return m
    return qs.order_by("id").first()


def _ensure_active_company(user):
    """Default active company to first membership when unset."""
    if user.active_company_id:
        return
    membership = user.company_memberships.filter(is_active=True).order_by("id").first()
    if membership:
        user.active_company_id = membership.company_id
        user.save(update_fields=["active_company_id"])


LOGIN_FAIL_LIMIT = 10
LOGIN_FAIL_WINDOW_SECONDS = 15 * 60

OTP_PHONE_COOLDOWN_SECONDS = 60
OTP_PHONE_HOUR_LIMIT = 5
OTP_PHONE_HOUR_SECONDS = 60 * 60

_REGISTER_DETAIL = "If this email can be registered, an account has been prepared."


def _login_fail_key(email):
    return f"login_fail:{(email or '').strip().lower()}"


def _record_login_failure(email):
    """BB-000291: prefer atomic Redis INCR; fall back to get/set."""
    fail_key = _login_fail_key(email)
    try:
        cache.incr(fail_key)
    except ValueError:
        # Key missing — seed with TTL. add is atomic (only sets if absent).
        if not cache.add(fail_key, 1, LOGIN_FAIL_WINDOW_SECONDS):
            try:
                cache.incr(fail_key)
            except ValueError:
                cache.set(fail_key, 1, LOGIN_FAIL_WINDOW_SECONDS)


def _otp_phone_cooldown_key(phone: str) -> str:
    return f"otp_phone_cd:{(phone or '').strip()}"


def _otp_phone_hour_key(phone: str) -> str:
    return f"otp_phone_hr:{(phone or '').strip()}"


def _otp_phone_rate_limited(phone: str) -> bool:
    """Per-phone cooldown (1/min) and hourly cap (5/hour), independent of IP throttle."""
    if cache.get(_otp_phone_cooldown_key(phone)):
        return True
    hour_key = _otp_phone_hour_key(phone)
    try:
        count = int(cache.get(hour_key) or 0)
    except (TypeError, ValueError):
        count = 0
    return count >= OTP_PHONE_HOUR_LIMIT


def _record_otp_phone_request(phone: str) -> None:
    cache.set(_otp_phone_cooldown_key(phone), 1, OTP_PHONE_COOLDOWN_SECONDS)
    hour_key = _otp_phone_hour_key(phone)
    try:
        cache.incr(hour_key)
    except ValueError:
        if not cache.add(hour_key, 1, OTP_PHONE_HOUR_SECONDS):
            try:
                cache.incr(hour_key)
            except ValueError:
                cache.set(hour_key, 1, OTP_PHONE_HOUR_SECONDS)


def _register_payload():
    """BB-000349: identical body for new and duplicate emails (no JWT/ids oracle)."""
    return {
        "detail": _REGISTER_DETAIL,
        "access": None,
        "user_id": None,
        "company_id": None,
    }


class RegisterView(APIView):
    """Create owner user + company + owner membership in one shot (M0)."""

    permission_classes = [AllowAny]
    throttle_scope = "register"

    @transaction.atomic
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # BB-000251 / BB-000290 / BB-000349: non-enumerating register — always 200 + same body.
        existing = User.objects.filter(email__iexact=data["email"]).first()
        if existing:
            return Response(_register_payload(), status=status.HTTP_200_OK)
        try:
            user = User.objects.create_user(
                email=data["email"], password=data["password"],
                full_name=data.get("full_name", ""), phone=data.get("phone", ""),
            )
        except IntegrityError:
            return Response(_register_payload(), status=status.HTTP_200_OK)
        company = Company.objects.create(
            name=data["company_name"],
            state=data.get("state", ""),
            registration_type=data.get("registration_type", Company.RegistrationType.UNREGISTERED),
            gstin=data.get("gstin", ""),
        )
        CompanyUser.objects.create(
            company=company, user=user, role=CompanyUser.Role.OWNER,
            can_manage_inventory=True, can_import=True,
            can_cancel_documents=True, can_view_financial_reports=True, can_export=True,
            can_create_sales=True, can_create_purchases=True, can_create_payments=True,
            can_post_journals=True,
        )
        from inventory.services import InventoryService

        InventoryService.default_warehouse(company)
        AuditService.log(company=company, user=user, action="CREATE",
                         entity_type="Company", entity_id=company.id,
                         description="Company registered")
        # BB-000389: never set auth cookies on register (enumeration oracle).
        return Response(_register_payload(), status=status.HTTP_200_OK)

def _access_in_json_body_allowed() -> bool:
    """BB-000471: access JWT in JSON only for local DEBUG; never when DEBUG=0."""
    from django.conf import settings as dj_settings

    if not getattr(dj_settings, "DEBUG", False):
        return False
    env = (getattr(dj_settings, "DJANGO_ENV", "") or "").lower().strip()
    return env in ("development", "test", "")


class LoginView(TokenObtainPairView):
    """Email + password JWT login with LOGIN audit. Access in body; refresh cookie only."""

    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        email = request.data.get("email", "")
        fail_key = _login_fail_key(email)
        # Per-account lockout — IP-based throttling alone (login scope) is
        # trivially bypassed by distributing attempts across many IPs.
        if cache.get(fail_key, 0) >= LOGIN_FAIL_LIMIT:
            raise TooManyLoginAttemptsError()
        try:
            response = super().post(request, *args, **kwargs)
        except AuthenticationFailed:
            _record_login_failure(email)
            raise
        if response.status_code == 200:
            cache.delete(fail_key)
            user = User.objects.filter(email__iexact=email).first()
            if user:
                _ensure_active_company(user)
                membership = _active_membership(user)
                AuditService.log(
                    company=membership.company if membership else None,
                    user=user, action="LOGIN", entity_type="User", entity_id=user.id,
                )
                if membership:
                    refresh = response.data.get("refresh", "")
                    access = response.data.get("access", "")
                    # BB-000407 / BB-000471: cookie-only access when not local DEBUG.
                    body = {"user": MeSerializer(membership).data}
                    body["access"] = access if _access_in_json_body_allowed() else None
                    response.data = body
                    if refresh:
                        _set_refresh_cookie(response, refresh)
                    if access:
                        _set_access_cookie(response, access)
                    _ensure_csrf_cookie(request)
        return response


class CookieTokenRefreshView(APIView):
    """BB-000257: refresh from httpOnly cookie; body refresh only when DEBUG."""

    permission_classes = [AllowAny]
    # UXW2-003: own scope, not "login" — refresh fires automatically and far
    # more often than a human submits a login form; sharing login's tight
    # anti-brute-force budget caused 429s during normal fast navigation.
    throttle_scope = "token_refresh"

    def post(self, request):
        from rest_framework.authentication import SessionAuthentication

        cookie_raw = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        body_raw = request.data.get("refresh") if isinstance(request.data, dict) else None
        if settings.DEBUG:
            raw = cookie_raw or body_raw
        else:
            # BB-000266: outside DEBUG accept cookie only (reject body refresh).
            if body_raw and not cookie_raw:
                raise AuthenticationFailed("Refresh token must be provided via cookie.")
            raw = cookie_raw
        if not raw:
            raise AuthenticationFailed("Refresh token required.")
        # BB-000417: cookie refresh is a mutating cross-site risk — require CSRF.
        if cookie_raw:
            SessionAuthentication().enforce_csrf(request)
        try:
            old = RefreshToken(raw)
            user_id = old.get("user_id")
            user = User.objects.filter(pk=user_id, is_active=True).first()
            if not user:
                raise AuthenticationFailed("Invalid refresh token.")
            try:
                old.blacklist()
            except TokenError:
                pass
            tokens = _tokens_for_user(user)
            env = (getattr(settings, "DJANGO_ENV", "") or "").lower().strip()
            # BB-000407: production/staging — cookie-only access.
            if env in ("production", "staging"):
                response = Response({"access": None})
            else:
                response = Response({"access": tokens["access"]})
            _set_refresh_cookie(response, tokens["refresh"])
            _set_access_cookie(response, tokens["access"])
            _ensure_csrf_cookie(request)
            return response
        except TokenError as exc:
            raise AuthenticationFailed("Invalid refresh token.") from exc


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if settings.DEBUG and not refresh:
            refresh = request.data.get("refresh") if isinstance(request.data, dict) else None
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass
        membership = _active_membership(request.user)
        AuditService.log(
            company=membership.company if membership else None,
            user=request.user, action="LOGOUT", entity_type="User", entity_id=request.user.id,
        )
        response = Response({"detail": "Logged out."})
        return _clear_refresh_cookie(response)


class RequestOtpView(APIView):
    """Mobile + OTP step 1. SMS via SmsProvider; debug echo only when explicitly enabled."""

    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        try:
            phone = normalize_e164(request.data.get("phone") or "")
        except ValueError as exc:
            raise ValidationError({"phone": str(exc)}) from exc
        sms = (getattr(settings, "SMS_PROVIDER", "") or "").strip().lower()
        env = (getattr(settings, "DJANGO_ENV", "") or "").lower().strip()
        stub_sms = sms in ("", "off", "disabled", "console", "stub")
        # BB-000419: never claim OTP sent on stub SMS outside development/test.
        if stub_sms and env not in ("development", "test", ""):
            raise ValidationError(
                {"detail": "OTP login requires a real SMS provider outside development."}
            )
        # BB-000332: OTP enabled via OTP_ENABLED or a non-stub SMS provider — not OTP_DEBUG_ECHO.
        otp_on = bool(getattr(settings, "OTP_ENABLED", False)) or not stub_sms
        if not otp_on:
            # Dev convenience: console SMS + OTP_DEBUG_ECHO still allows local OTP testing.
            if not (sms == "console" and settings.OTP_DEBUG_ECHO):
                raise ValidationError(
                    {"detail": "OTP login is not configured. Use email/password or contact support."}
                )
        payload = {"detail": "If this phone number is registered, an OTP has been sent."}
        # Per-phone rate limit before existence check — same response either way.
        if _otp_phone_rate_limited(phone):
            return Response(payload)
        _record_otp_phone_request(phone)
        user_exists = User.objects.filter(phone__in=phone_lookup_values(phone), is_active=True).exists()
        if user_exists:
            code = f"{secrets.randbelow(10**6):06d}"
            challenge = OtpChallenge.objects.create(
                phone=phone,
                code=hash_otp(code),
                expires_at=timezone.now() + timezone.timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
            )
            try:
                SmsProvider.send_otp(phone, code)
            except Exception:
                # Uniform 200 — never leak registration via provider errors.
                challenge.delete()
        return Response(payload)


class VerifyOtpView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp_verify"

    def post(self, request):
        sms = (getattr(settings, "SMS_PROVIDER", "") or "").strip().lower()
        stub_sms = sms in ("", "off", "disabled", "console", "stub")
        otp_on = bool(getattr(settings, "OTP_ENABLED", False)) or not stub_sms
        if not otp_on and not (sms == "console" and settings.OTP_DEBUG_ECHO):
            raise ValidationError({"detail": "OTP login is not configured."})
        try:
            phone = normalize_e164(request.data.get("phone") or "")
        except ValueError as exc:
            raise ValidationError({"phone": str(exc)}) from exc
        code = (request.data.get("code") or "").strip()
        # BB-000209: lock row; persist failed attempts before raising so the
        # atomic block does not roll back the counter.
        invalid = False
        with transaction.atomic():
            challenge = (
                OtpChallenge.objects.select_for_update()
                .filter(phone=phone, consumed=False)
                .order_by("-created_at")
                .first()
            )
            if not challenge or challenge.is_expired:
                raise OtpExpiredError()
            if challenge.attempts >= settings.OTP_MAX_ATTEMPTS:
                raise OtpTooManyAttemptsError()
            if not verify_otp(challenge.code, code):
                challenge.attempts += 1
                challenge.save(update_fields=["attempts"])
                invalid = True
            else:
                challenge.consumed = True
                challenge.save(update_fields=["consumed"])
        if invalid:
            raise OtpInvalidError()
        user = User.objects.filter(phone__in=phone_lookup_values(phone), is_active=True).order_by("id").first()
        if not user:
            raise OtpExpiredError()
        _ensure_active_company(user)
        membership = _active_membership(user)
        AuditService.log(
            company=membership.company if membership else None,
            user=user, action="LOGIN", entity_type="User", entity_id=user.id,
            description="OTP login",
        )
        tokens = _tokens_for_user(user)
        # BB-000407 / BB-000471: cookie-only access when not local DEBUG.
        payload = {"access": tokens["access"] if _access_in_json_body_allowed() else None}
        if membership:
            payload["user"] = MeSerializer(membership).data
        response = Response(payload)
        _set_refresh_cookie(response, tokens["refresh"])
        _set_access_cookie(response, tokens["access"])
        _ensure_csrf_cookie(request)
        return response


class CsrfCookieView(APIView):
    """BB-000602: GET /auth/csrf/ sets csrftoken for cookie-JWT mutating calls."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        _ensure_csrf_cookie(request)
        return Response({"detail": "ok"})


class MeView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        return Response(MeSerializer(get_company_user(request)).data)


class MembershipsListView(APIView):
    """GET /auth/memberships/ — active companies for switcher (Wave 17G)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = (
            request.user.company_memberships.filter(is_active=True)
            .select_related("company")
            .order_by("company__name", "id")
        )
        active_id = request.user.active_company_id
        return Response(
            [
                {
                    "company_id": m.company_id,
                    "company_name": m.company.name,
                    "role": m.role,
                    "is_active_selection": m.company_id == active_id,
                }
                for m in rows
            ]
        )


class SwitchCompanyView(APIView):
    """POST /auth/switch-company/ — set active company for multi-membership users."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        company_id = request.data.get("company_id")
        if not company_id:
            raise ValidationError({"company_id": "company_id is required"})
        membership = (
            request.user.company_memberships.filter(is_active=True, company_id=company_id)
            .select_related("company")
            .first()
        )
        if not membership:
            raise ValidationError({"company_id": "No active membership for this company."})
        request.user.active_company_id = membership.company_id
        request.user.save(update_fields=["active_company_id"])
        if hasattr(request, "_company_user"):
            delattr(request, "_company_user")
        AuditService.log(
            company=membership.company,
            user=request.user,
            action="UPDATE",
            entity_type="User",
            entity_id=request.user.id,
            description=f"Switched active company to {membership.company_id}",
        )
        tokens = _tokens_for_user(request.user)
        body = {
            "user": MeSerializer(membership).data,
            "access": tokens["access"] if _access_in_json_body_allowed() else None,
        }
        response = Response(body)
        _set_refresh_cookie(response, tokens["refresh"])
        _set_access_cookie(response, tokens["access"])
        _ensure_csrf_cookie(request)
        return response


class CompanyDetailView(RetrieveUpdateAPIView):
    """Company profile & GST settings. Owner-only for writes (§5.5)."""

    permission_classes = [IsAuthenticated, HasCompany]

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH"):
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return super().get_permissions()

    def get_serializer_class(self):
        # Bank/UPI details are owner-only reading material — a SALES_STAFF
        # member has no business need to see the company's bank account.
        cu = get_company_user(self.request)
        if cu is not None and cu.role == "OWNER":
            return CompanySerializer
        return CompanySerializerStaff

    def get_object(self):
        return get_company_user(self.request).company

    def perform_update(self, serializer):
        instance = serializer.save()
        AuditService.log(
            company=instance, user=self.request.user, action="UPDATE",
            entity_type="Company", entity_id=instance.id,
        )


class CompanyVerifyGstinView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request):
        from core.exceptions import BusinessRuleError
        from core.services.gstin_verify import apply_verification, get_gstin_provider

        company = get_company_user(request).company
        if not (company.gstin or "").strip():
            raise BusinessRuleError("Company has no GSTIN.")
        # BB-000285/225: Null provider returns UNVERIFIED only — never VALID / verified_at.
        result = get_gstin_provider().lookup(company.gstin)
        apply_verification(company, result, user=request.user, company=company)
        return Response(CompanySerializer(company).data)


class CompanyVerifyPanView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request):
        from core.exceptions import BusinessRuleError
        from core.services.identity_verify import apply_pan_verification, get_identity_provider

        company = get_company_user(request).company
        pan = (request.data.get("pan") or company.pan or "").strip().upper()
        if not pan:
            raise BusinessRuleError("Company has no PAN.")
        if request.data.get("pan"):
            company.pan = pan
            company.save(update_fields=["pan", "updated_at"])
        result = get_identity_provider().lookup_pan(pan)
        apply_pan_verification(company, result, user=request.user)
        return Response(CompanySerializer(company).data)


class CompanyVerifyUdyamView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request):
        from core.exceptions import BusinessRuleError
        from core.services.identity_verify import apply_udyam_verification, get_identity_provider

        company = get_company_user(request).company
        udyam = (request.data.get("udyam") or company.udyam or "").strip().upper()
        if not udyam:
            raise BusinessRuleError("Company has no UDYAM number.")
        if request.data.get("udyam"):
            company.udyam = udyam
            company.save(update_fields=["udyam", "updated_at"])
        result = get_identity_provider().lookup_udyam(udyam)
        apply_udyam_verification(company, result, user=request.user)
        return Response(CompanySerializer(company).data)


class ChangePasswordView(APIView):
    """BB-000366: change password and blacklist all outstanding refresh tokens."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        current = request.data.get("current_password") or ""
        new = request.data.get("new_password") or ""
        if not request.user.check_password(current):
            raise ValidationError({"current_password": "Current password is incorrect."})
        try:
            validate_password(new, user=request.user)
        except Exception as exc:
            raise ValidationError({"new_password": list(exc.messages) if hasattr(exc, "messages") else str(exc)}) from exc
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        for token in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=token)
        membership = _active_membership(request.user)
        AuditService.log(
            company=membership.company if membership else None,
            user=request.user, action="UPDATE", entity_type="User", entity_id=request.user.id,
            description="Password changed; sessions revoked",
        )
        response = Response({"detail": "Password updated. Please sign in again."})
        return _clear_auth_cookies(response)


class AcceptInviteView(APIView):
    """BB-000418: set password from signed invite token (dead-end fix)."""

    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        token = (request.data.get("token") or "").strip()
        new_password = request.data.get("new_password") or ""
        if not token:
            raise ValidationError({"token": "Invite token is required."})
        try:
            payload = _load_invite_token(token)
        except signing.BadSignature as exc:
            raise ValidationError({"token": "Invalid or expired invite token."}) from exc
        except signing.SignatureExpired as exc:
            raise ValidationError({"token": "Invite token has expired."}) from exc
        membership = (
            CompanyUser.objects.select_related("user", "company")
            .filter(
                pk=payload.get("mid"),
                user_id=payload.get("uid"),
                company_id=payload.get("cid"),
            )
            .first()
        )
        if not membership:
            raise ValidationError({"token": "Invite is no longer valid."})
        jti = payload.get("jti")
        invite_row = None
        if jti:
            invite_row = InviteJti.objects.filter(jti=jti, membership=membership).first()
            if invite_row is None or invite_row.is_consumed:
                raise ValidationError({"token": "Invite token has already been used."})
            if invite_row.expires_at and invite_row.expires_at < timezone.now():
                raise ValidationError({"token": "Invite token has expired."})
        user = membership.user
        if not user.has_usable_password():
            if not new_password:
                raise ValidationError({"new_password": "Password is required."})
            try:
                validate_password(new_password, user=user)
            except Exception as exc:
                raise ValidationError(
                    {"new_password": list(exc.messages) if hasattr(exc, "messages") else str(exc)}
                ) from exc
            user.set_password(new_password)
            user.save(update_fields=["password"])
        elif new_password:
            try:
                validate_password(new_password, user=user)
            except Exception as exc:
                raise ValidationError(
                    {"new_password": list(exc.messages) if hasattr(exc, "messages") else str(exc)}
                ) from exc
            user.set_password(new_password)
            user.save(update_fields=["password"])
        if not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=["is_active", "updated_at"])
        if invite_row is not None:
            invite_row.consumed_at = timezone.now()
            invite_row.save(update_fields=["consumed_at", "updated_at"])
        if not user.active_company_id:
            user.active_company_id = membership.company_id
            user.save(update_fields=["active_company_id"])
        AuditService.log(
            company=membership.company,
            user=user,
            action="UPDATE",
            entity_type="User",
            entity_id=user.id,
            description="Invite accepted; membership activated",
        )
        return Response(
            {
                "detail": "Invite accepted.",
                "company_id": membership.company_id,
            },
            status=status.HTTP_200_OK,
        )


class LogoutAllView(APIView):
    """BB-000366: blacklist all refresh tokens for the user."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        for token in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=token)
        membership = _active_membership(request.user)
        AuditService.log(
            company=membership.company if membership else None,
            user=request.user, action="LOGOUT", entity_type="User", entity_id=request.user.id,
            description="Logout all devices",
        )
        response = Response({"detail": "Logged out from all devices."})
        return _clear_auth_cookies(response)


def _active_owner_count(company, exclude_pk=None):
    qs = CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER, is_active=True)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.count()


def _staff_invite_caps(data: dict) -> dict:
    """Capability flags for roles without fixed ACCOUNTANT/VIEWER defaults.

    Omitted create flags default Sales Staff to selling + receipts so an invite
    is usable without a second Settings round-trip.
    """
    sales_default = data.get("role") == CompanyUser.Role.SALES_STAFF

    def flag(key: str, default: bool = False) -> bool:
        val = data.get(key)
        return default if val is None else bool(val)

    return {
        "can_manage_inventory": data["can_manage_inventory"],
        "can_import": data["can_import"],
        "can_cancel_documents": data.get("can_cancel_documents") or False,
        "can_view_financial_reports": data.get("can_view_financial_reports") or False,
        "can_export": data.get("can_export") or False,
        "can_view_ai_insights": data.get("can_view_ai_insights") or False,
        "can_use_ai_assistant": data.get("can_use_ai_assistant") or False,
        "can_create_sales": flag("can_create_sales", sales_default),
        "can_create_purchases": flag("can_create_purchases", False),
        "can_create_payments": flag("can_create_payments", sales_default),
        "can_post_journals": data.get("can_post_journals") or False,
    }


def _enforce_plan_seat_limit(company) -> None:
    """BB-000727: reject invite/create when active members >= plan.seat_limit."""
    from billing.services import subscription_for_company

    sub = subscription_for_company(company)
    if sub is None or sub.plan_id is None:
        return
    limit = int(getattr(sub.plan, "seat_limit", 0) or 0)
    if limit <= 0:
        return
    active = CompanyUser.objects.filter(company=company, is_active=True).count()
    if active >= limit:
        raise ValidationError({
            "detail": f"Seat limit of {limit} reached for the current plan.",
        })


class CompanyUserViewSet(viewsets.ModelViewSet):
    """Owner manages staff users (E1.9)."""

    serializer_class = CompanyUserSerializer
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]
    queryset = CompanyUser.objects.select_related("user")
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        return self.queryset.filter(company=get_company_user(self.request).company)

    def create(self, request, *args, **kwargs):
        serializer = InviteUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        company = get_company_user(request).company
        _enforce_plan_seat_limit(company)
        existing_user = User.objects.filter(email__iexact=data["email"]).first()
        if existing_user is not None:
            if CompanyUser.objects.filter(company=company, user=existing_user).exists():
                raise ValidationError({"email": "This user is already a member of this company."})
            role = data["role"]
            role_defaults = CompanyUser.capability_defaults_for_role(role)
            if role_defaults is not None:
                caps = role_defaults
            else:
                caps = _staff_invite_caps(data)
            membership = CompanyUser.objects.create(
                company=company, user=existing_user, role=role, is_active=False, **caps,
            )
            AuditService.log(
                company=company, user=request.user, action="CREATE",
                entity_type="CompanyUser", entity_id=membership.id,
                description="Consent invite for existing user",
            )
            body = CompanyUserSerializer(membership).data
            token = _make_invite_token(
                user_id=existing_user.id, company_id=company.id, membership_id=membership.id,
            )
            body["invite_url"] = _invite_url(token)
            body["consent_required"] = True
            django_env = (getattr(settings, "DJANGO_ENV", "") or "").lower().strip()
            if django_env in ("production", "staging"):
                body["invite_hint"] = (
                    "Share invite_url with the existing user so they can consent "
                    "and join this company."
                )
            else:
                body["invite_token"] = token
                body["invite_hint"] = (
                    "Share invite_token; the existing user must POST /api/v1/auth/invite/accept/ "
                    "to consent and join this company."
                )
            return Response(body, status=status.HTTP_201_CREATED)
        # BB-000306 / BB-000366: password optional — forbidden in production/staging.
        password = (data.get("password") or "").strip()
        django_env = (getattr(settings, "DJANGO_ENV", "") or "").lower().strip()
        if password and django_env in ("production", "staging"):
            raise ValidationError({
                "password": "Invite passwords are disabled in production. "
                            "Omit password; the invitee must set one via password-change after login token.",
            })
        user = User.objects.create_user(
            email=data["email"],
            password=password or None,
            full_name=data.get("full_name", ""),
            phone=data.get("phone", ""),
        )
        if not password:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        role = data["role"]
        role_defaults = CompanyUser.capability_defaults_for_role(role)
        if role_defaults is not None:
            caps = role_defaults
        else:
            caps = _staff_invite_caps(data)
        membership = CompanyUser.objects.create(
            company=company, user=user, role=role, **caps,
        )
        AuditService.log(company=company, user=request.user, action="CREATE",
                         entity_type="CompanyUser", entity_id=membership.id)
        body = CompanyUserSerializer(membership).data
        token = _make_invite_token(
            user_id=user.id, company_id=company.id, membership_id=membership.id,
        )
        body["invite_url"] = _invite_url(token)
        django_env = (getattr(settings, "DJANGO_ENV", "") or "").lower().strip()
        if django_env in ("production", "staging"):
            body["invite_hint"] = (
                "Share invite_url with the user; it expires in 7 days."
            )
        else:
            body["invite_token"] = token
            body["invite_hint"] = (
                "Share invite_token with the user; they must POST /api/v1/auth/invite/accept/ "
                "with token + new_password within 7 days."
            )
        return Response(body, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        instance = serializer.instance
        was_active_owner = instance.role == CompanyUser.Role.OWNER and instance.is_active
        new_role = serializer.validated_data.get("role", instance.role)
        new_active = serializer.validated_data.get("is_active", instance.is_active)
        stays_active_owner = new_role == CompanyUser.Role.OWNER and new_active
        if was_active_owner and not stays_active_owner:
            if _active_owner_count(instance.company, exclude_pk=instance.pk) == 0:
                raise ValidationError({"detail": "Cannot remove the company's last active Owner."})
        # BB-000084: membership company is immutable.
        updated = serializer.save(company=get_company_user(self.request).company)
        AuditService.log(company=updated.company, user=self.request.user, action="UPDATE",
                         entity_type="CompanyUser", entity_id=updated.id)

    def perform_destroy(self, instance):
        if instance.role == CompanyUser.Role.OWNER and instance.is_active:
            if _active_owner_count(instance.company, exclude_pk=instance.pk) == 0:
                raise ValidationError({"detail": "Cannot remove the company's last active Owner."})
        # Soft-deactivate rather than delete.
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        AuditService.log(company=instance.company, user=self.request.user, action="DELETE",
                         entity_type="CompanyUser", entity_id=instance.pk, description="Deactivated")


class CompanyGstinViewSet(viewsets.ModelViewSet):
    """BB-000674: Owner CRUD for branch GSTIN registrations."""

    serializer_class = CompanyGstinSerializer
    permission_classes = [IsAuthenticated, HasCompany]
    queryset = CompanyGstin.objects.all()
    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.request.method in ("POST", "PATCH", "PUT", "DELETE"):
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return super().get_permissions()

    def get_queryset(self):
        return self.queryset.filter(company=get_company_user(self.request).company)

    def perform_create(self, serializer):
        company = get_company_user(self.request).company
        instance = serializer.save(
            company=company, created_by=self.request.user, updated_by=self.request.user,
        )
        AuditService.log(
            company=company, user=self.request.user, action="CREATE",
            entity_type="CompanyGstin", entity_id=instance.id,
        )

    def perform_update(self, serializer):
        instance = serializer.save(
            company=get_company_user(self.request).company, updated_by=self.request.user,
        )
        AuditService.log(
            company=instance.company, user=self.request.user, action="UPDATE",
            entity_type="CompanyGstin", entity_id=instance.id,
        )

    def perform_destroy(self, instance):
        entity_id = instance.pk
        company = instance.company
        instance.delete()
        AuditService.log(
            company=company, user=self.request.user, action="DELETE",
            entity_type="CompanyGstin", entity_id=entity_id,
        )
