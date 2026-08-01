import random

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
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

from .models import Company, CompanyUser, OtpChallenge, User
from .serializers import (
    CompanySerializer,
    CompanySerializerStaff,
    CompanyUserSerializer,
    InviteUserSerializer,
    MeSerializer,
    RegisterSerializer,
)


def _tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


def _active_membership(user):
    return user.company_memberships.filter(is_active=True).select_related("company").order_by("id").first()


LOGIN_FAIL_LIMIT = 10
LOGIN_FAIL_WINDOW_SECONDS = 15 * 60


def _login_fail_key(email):
    return f"login_fail:{(email or '').strip().lower()}"


class RegisterView(APIView):
    """Create owner user + company + owner membership in one shot (M0)."""

    permission_classes = [AllowAny]
    throttle_scope = "register"

    @transaction.atomic
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = User.objects.create_user(
                email=data["email"], password=data["password"],
                full_name=data.get("full_name", ""), phone=data.get("phone", ""),
            )
        except IntegrityError:
            # Two concurrent registrations for the same email raced past the
            # pre-check in RegisterSerializer.validate_email.
            raise ValidationError({"email": "A user with this email already exists."})
        company = Company.objects.create(name=data["company_name"], state=data.get("state", ""))
        CompanyUser.objects.create(
            company=company, user=user, role=CompanyUser.Role.OWNER,
            can_manage_inventory=True, can_import=True,
            can_cancel_documents=True, can_view_financial_reports=True, can_export=True,
        )
        AuditService.log(company=company, user=user, action="CREATE",
                         entity_type="Company", entity_id=company.id,
                         description="Company registered")
        return Response(
            {"user_id": user.id, "company_id": company.id, **_tokens_for_user(user)},
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """Email + password JWT login with LOGIN audit event. Returns user + tokens."""

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
            cache.set(fail_key, cache.get(fail_key, 0) + 1, LOGIN_FAIL_WINDOW_SECONDS)
            raise
        if response.status_code == 200:
            cache.delete(fail_key)
            user = User.objects.filter(email__iexact=email).first()
            if user:
                membership = _active_membership(user)
                AuditService.log(
                    company=membership.company if membership else None,
                    user=user, action="LOGIN", entity_type="User", entity_id=user.id,
                )
                if membership:
                    response.data = {
                        "access": response.data["access"],
                        "refresh": response.data["refresh"],
                        "user": MeSerializer(membership).data,
                    }
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
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
        return Response({"detail": "Logged out."})


class RequestOtpView(APIView):
    """Mobile + OTP step 1. SMS via SmsProvider; debug echo only when explicitly enabled."""

    permission_classes = [AllowAny]
    throttle_scope = "otp"

    def post(self, request):
        phone = (request.data.get("phone") or "").strip()
        if not phone:
            raise ValidationError({"phone": "phone is required"})
        # Console/stub printing never reaches a real user, so OTP can only be
        # considered "configured" when explicitly opted into for local
        # development/testing (OTP_DEBUG_ECHO) — note this is independent of
        # DEBUG itself, since test runners commonly force DEBUG=False.
        if settings.SMS_PROVIDER in ("", "off", "disabled") or not settings.OTP_DEBUG_ECHO:
            raise ValidationError(
                {"detail": "OTP login is not configured. Use email/password or contact support."}
            )
        # Always respond identically regardless of whether the phone is
        # registered — a distinguishable response here is a phone-number
        # enumeration oracle (BUG-113).
        payload = {"detail": "If this phone number is registered, an OTP has been sent."}
        user_exists = User.objects.filter(phone=phone, is_active=True).exists()
        if user_exists:
            code = f"{random.randint(0, 999999):06d}"
            OtpChallenge.objects.create(
                phone=phone, code=code,
                expires_at=timezone.now() + timezone.timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
            )
            SmsProvider.send_otp(phone, code)
            if settings.OTP_DEBUG_ECHO:
                payload["debug_code"] = code
        return Response(payload)


class VerifyOtpView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "otp_verify"

    def post(self, request):
        phone = (request.data.get("phone") or "").strip()
        code = (request.data.get("code") or "").strip()
        challenge = (
            OtpChallenge.objects.filter(phone=phone, consumed=False)
            .order_by("-created_at").first()
        )
        if not challenge or challenge.is_expired:
            raise OtpExpiredError()
        if challenge.attempts >= settings.OTP_MAX_ATTEMPTS:
            raise OtpTooManyAttemptsError()
        if challenge.code != code:
            challenge.attempts += 1
            challenge.save(update_fields=["attempts"])
            raise OtpInvalidError()
        challenge.consumed = True
        challenge.save(update_fields=["consumed"])
        # phone is not unique on User at the DB level for legacy data, but a
        # partial unique constraint (migration 0006) now prevents new
        # collisions; stay defensive against any pre-existing duplicates.
        user = User.objects.filter(phone=phone, is_active=True).order_by("id").first()
        if not user:
            raise OtpExpiredError()
        membership = _active_membership(user)
        AuditService.log(
            company=membership.company if membership else None,
            user=user, action="LOGIN", entity_type="User", entity_id=user.id,
            description="OTP login",
        )
        tokens = _tokens_for_user(user)
        payload = {**tokens}
        if membership:
            payload["user"] = MeSerializer(membership).data
        return Response(payload)


class MeView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        return Response(MeSerializer(get_company_user(request)).data)


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


def _active_owner_count(company, exclude_pk=None):
    qs = CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER, is_active=True)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.count()


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
        # An existing User must not be silently attached to a different
        # company with no consent (BUG-109/701) — only brand-new accounts
        # can be created through this endpoint today.
        if User.objects.filter(email__iexact=data["email"]).exists():
            raise ValidationError({
                "email": "An account with this email already exists. Existing users "
                         "cannot be added to a company directly yet; contact support.",
            })
        user = User.objects.create_user(
            email=data["email"], password=data["password"],
            full_name=data.get("full_name", ""), phone=data.get("phone", ""),
        )
        membership = CompanyUser.objects.create(
            company=company, user=user, role=data["role"],
            can_manage_inventory=data["can_manage_inventory"],
            can_import=data["can_import"],
            can_cancel_documents=data.get("can_cancel_documents", False),
            can_view_financial_reports=data.get("can_view_financial_reports", True),
            can_export=data.get("can_export", False),
        )
        AuditService.log(company=company, user=request.user, action="CREATE",
                         entity_type="CompanyUser", entity_id=membership.id)
        return Response(CompanyUserSerializer(membership).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        instance = serializer.instance
        was_active_owner = instance.role == CompanyUser.Role.OWNER and instance.is_active
        new_role = serializer.validated_data.get("role", instance.role)
        new_active = serializer.validated_data.get("is_active", instance.is_active)
        stays_active_owner = new_role == CompanyUser.Role.OWNER and new_active
        if was_active_owner and not stays_active_owner:
            if _active_owner_count(instance.company, exclude_pk=instance.pk) == 0:
                raise ValidationError({"detail": "Cannot remove the company's last active Owner."})
        updated = serializer.save()
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
