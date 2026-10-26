"""BB-100 F10: who is on the team, for the lead, attention and care pickers.

The full member list (``/company/users/``) is owner-only because it carries emails, phones and
permissions. Managers and assignees may still hand work to a colleague, so any active member can
read this list: member id, a display name and the role, nothing else.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user


class TeamMemberSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text="Company membership id, the value the pickers assign.")
    name = serializers.CharField(help_text="Full name, or the part of the email before @ when none is set.")
    role = serializers.CharField()


def _display_name(user) -> str:
    return (user.full_name or "").strip() or (user.email or "").split("@", 1)[0]


class TeamMembersView(APIView):
    """GET /api/v1/company/members/ — active members who have signed up (no pending invites)."""

    permission_classes = [IsAuthenticated, HasCompany]

    @extend_schema(responses=TeamMemberSerializer(many=True))
    def get(self, request):
        from .models import CompanyUser

        company = get_company_user(request).company
        rows = (
            CompanyUser.objects.filter(company=company, is_active=True, user__is_active=True)
            .select_related("user")
            .order_by("user__full_name", "id")
        )
        data = [{"id": cu.id, "name": _display_name(cu.user), "role": cu.role} for cu in rows]
        return Response(TeamMemberSerializer(data, many=True).data)
