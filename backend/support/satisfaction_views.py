"""BB-136: the NPS prompt and support CSAT for the signed-in member (support/satisfaction.py)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user

from . import satisfaction
from .models import SatisfactionResponse


class NpsDueSerializer(serializers.Serializer):
    due = serializers.BooleanField()
    enabled = serializers.BooleanField(help_text="ENABLE_SATISFACTION_SURVEY is on for this company.")


class SatisfactionAnswerSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=SatisfactionResponse.Kind.choices)
    score = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=10)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=satisfaction.COMMENT_MAX)
    platform_ticket = serializers.IntegerField(required=False, allow_null=True)


class SatisfactionSavedSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.CharField()
    score = serializers.IntegerField(allow_null=True)


class NpsDueView(APIView):
    """GET /api/v1/support/satisfaction/nps-due/ — show the recommend-us prompt now?"""

    permission_classes = [IsAuthenticated, HasCompany]

    @extend_schema(responses=NpsDueSerializer)
    def get(self, request):
        membership = get_company_user(request)
        return Response({
            "due": satisfaction.nps_due(membership),
            "enabled": satisfaction.survey_on(membership.company),
        })


class SatisfactionAnswerView(APIView):
    """POST /api/v1/support/satisfaction/ — an NPS answer ("Not now" = no score) or a CSAT rating."""

    permission_classes = [IsAuthenticated, HasCompany]

    @extend_schema(request=SatisfactionAnswerSerializer, responses={201: SatisfactionSavedSerializer})
    def post(self, request):
        data = SatisfactionAnswerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = satisfaction.record(
            get_company_user(request),
            kind=data.validated_data["kind"],
            score=data.validated_data.get("score"),
            comment=data.validated_data.get("comment", ""),
            platform_ticket_id=data.validated_data.get("platform_ticket"),
        )
        return Response(
            SatisfactionSavedSerializer({"id": row.id, "kind": row.kind, "score": row.score}).data,
            status=status.HTTP_201_CREATED,
        )
