import random

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.audit import AuditService

from .models import Company, CompanyUser, OtpChallenge, User
from .serializers import (
    CompanySerializer,
    CompanyUserSerializer,
    InviteUserSerializer,
    MeSerializer,
    RegisterSerializer,
)


def _tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class RegisterView(APIView):
    """Create owner user + company + owner membership in one shot (M0)."""

    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.create_user(
            email=data["email"], password=data["password"],
            full_name=data.get("full_name", ""), phone=data.get("phone", ""),
        )
        company = Company.objects.create(name=data["company_name"], state=data.get("state", ""))
        CompanyUser.objects.create(
            company=company, user=user, role=CompanyUser.Role.OWNER,
            can_manage_inventory=True, can_import=True,
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

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            user = User.objects.filter(email__iexact=request.data.get("email", "")).first()
            if user:
                membership = user.company_memberships.filter(is_active=True).first()
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
        membership = request.user.company_memberships.filter(is_active=True).first()
        AuditService.log(
            company=membership.company if membership else None,
            user=request.user, action="LOGOUT", entity_type="User", entity_id=request.user.id,
        )
        return Response({"detail": "Logged out."})


class RequestOtpView(APIView):
    """Mobile + OTP step 1 (E0.6). SMS provider integration is stubbed;
    in DEBUG the code is returned in the response for development."""

    permission_classes = [AllowAny]

    def post(self, request):
        phone = (request.data.get("phone") or "").strip()
        if not phone:
            return Response({"detail": "phone is required"}, status=400)
        if not User.objects.filter(phone=phone, is_active=True).exists():
            return Response({"detail": "No user with this phone number."}, status=404)
        code = f"{random.randint(0, 999999):06d}"
        OtpChallenge.objects.create(
            phone=phone, code=code,
            expires_at=timezone.now() + timezone.timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
        )
        payload = {"detail": "OTP sent."}
        if settings.OTP_DEBUG_ECHO:
            payload["debug_code"] = code
        return Response(payload)


class VerifyOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone = (request.data.get("phone") or "").strip()
        code = (request.data.get("code") or "").strip()
        challenge = (
            OtpChallenge.objects.filter(phone=phone, consumed=False)
            .order_by("-created_at").first()
        )
        if not challenge or challenge.is_expired:
            return Response({"detail": "OTP expired or not found."}, status=400)
        if challenge.attempts >= settings.OTP_MAX_ATTEMPTS:
            return Response({"detail": "Too many attempts."}, status=400)
        if challenge.code != code:
            challenge.attempts += 1
            challenge.save(update_fields=["attempts"])
            return Response({"detail": "Invalid OTP."}, status=400)
        challenge.consumed = True
        challenge.save(update_fields=["consumed"])
        user = User.objects.get(phone=phone, is_active=True)
        membership = user.company_memberships.filter(is_active=True).first()
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

    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated, HasCompany]

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH"):
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return super().get_permissions()

    def get_object(self):
        return get_company_user(self.request).company

    def perform_update(self, serializer):
        instance = serializer.save()
        AuditService.log(
            company=instance, user=self.request.user, action="UPDATE",
            entity_type="Company", entity_id=instance.id,
        )


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
        user = User.objects.filter(email__iexact=data["email"]).first()
        if user and user.company_memberships.filter(company=company).exists():
            return Response({"detail": "User already belongs to this company."}, status=400)
        if user is None:
            user = User.objects.create_user(
                email=data["email"], password=data["password"],
                full_name=data.get("full_name", ""), phone=data.get("phone", ""),
            )
        membership = CompanyUser.objects.create(
            company=company, user=user, role=data["role"],
            can_manage_inventory=data["can_manage_inventory"], can_import=data["can_import"],
        )
        AuditService.log(company=company, user=request.user, action="CREATE",
                         entity_type="CompanyUser", entity_id=membership.id)
        return Response(CompanyUserSerializer(membership).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        # Soft-deactivate rather than delete.
        instance.is_active = False
        instance.save(update_fields=["is_active"])
