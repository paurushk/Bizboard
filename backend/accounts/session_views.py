"""WP-ID3: signed-in devices for the current user, and session counts per member for owners."""

from __future__ import annotations

from django.conf import settings
from django.db.models import Count
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.audit import AuditService


def _current_jti(request) -> str:
    from rest_framework_simplejwt.tokens import RefreshToken

    raw = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
    if not raw:
        return ""
    try:
        return str(RefreshToken(raw).get("jti") or "")
    except Exception:  # noqa: BLE001 - an expired cookie just means "no current row"
        return ""


class UserSessionListView(APIView):
    """GET /api/v1/auth/sessions/ — the user's own signed-in devices, newest use first."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .user_sessions import list_for

        current = _current_jti(request)
        return Response([
            {
                "id": row.pk,
                "device": row.device_label,
                "network": row.ip_prefix,
                "created_at": row.created_at,
                "last_used_at": row.last_used_at,
                "current": bool(current) and row.current_jti == current,
            }
            for row in list_for(request.user)[:50]
        ])


class UserSessionRevokeView(APIView):
    """POST /api/v1/auth/sessions/<pk>/revoke/ — sign one of your own devices out."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        from .user_sessions import revoke

        if not revoke(request.user, pk):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        AuditService.log(
            user=request.user, action="LOGOUT", entity_type="UserSession", entity_id=pk,
            description="Signed one device out from the Security screen",
        )
        return Response({"revoked": True})


class MemberSessionCountsView(APIView):
    """GET /api/v1/company/users/session-counts/ — owners see how many devices each member is
    signed in on (counts only, not devices or networks)."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        from .models import CompanyUser, UserSession

        cu = get_company_user(request)
        user_ids = list(CompanyUser.objects.filter(company=cu.company, is_active=True).values_list("user_id", flat=True))
        counts = dict(
            UserSession.objects.filter(user_id__in=user_ids, revoked_at__isnull=True)
            .values("user_id").annotate(n=Count("id")).values_list("user_id", "n")
        )
        return Response({str(uid): counts.get(uid, 0) for uid in user_ids})
