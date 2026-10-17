"""Money hub endpoints (docs/plans/MONEY_HUB_PLAN.md). Read-only."""

from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.permissions import CanViewFinancialReports, HasCompany, get_company_user
from core.services.feature_flags import flag_enabled
from core.throttles import CompanyRateThrottle

from .money_position import TIMELINE_MAX_DAYS, build_position, build_statutory, build_timeline


class _MoneyHubView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "heavy_reports"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Kill-switch: company feature_flags {"ENABLE_MONEY_HUB": false}. On by default.
        if not flag_enabled(self.company, "ENABLE_MONEY_HUB"):
            raise NotFound()

    @property
    def company(self):
        return get_company_user(self.request).company


class MoneyPositionView(_MoneyHubView):
    @extend_schema(responses=OpenApiTypes.OBJECT, description="Where the business stands on money in and money out today.")
    def get(self, request):
        return Response(build_position(self.company))


class MoneyTimelineView(_MoneyHubView):
    @extend_schema(
        parameters=[OpenApiParameter("days", int, description=f"1 to {TIMELINE_MAX_DAYS}; default 30.")],
        responses=OpenApiTypes.OBJECT,
        description="Money expected in and due out over the next days, by due date (not a forecast).",
    )
    def get(self, request):
        raw = request.query_params.get("days", "30")
        if not (str(raw).isascii() and str(raw).isdigit()) or not 1 <= int(raw) <= TIMELINE_MAX_DAYS:
            raise ValidationError({"days": f"Use a whole number from 1 to {TIMELINE_MAX_DAYS}."})
        return Response(build_timeline(self.company, int(raw)))


class MoneyStatutoryView(_MoneyHubView):
    @extend_schema(responses=OpenApiTypes.OBJECT, description="Tax amounts and due dates, as estimates for the CA to confirm.")
    def get(self, request):
        return Response(build_statutory(self.company))
