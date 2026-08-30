from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import CanCreateSales, HasCompany, get_company_user
from core.viewsets import CompanyScopedViewSet

from .models import Lead, LeadActivity, Opportunity
from .permissions import assert_crm_enabled
from .serializers import LeadActivitySerializer, LeadSerializer, OpportunitySerializer
from .services import convert_lead


def _truthy(value) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or "").lower() in ("1", "true", "yes", "won")


class LeadViewSet(CompanyScopedViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "Lead"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_crm_enabled(get_company_user(request).company)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        lead = self.get_object()
        won = _truthy(request.query_params.get("won")) or _truthy(request.data.get("won"))
        amount = request.data.get("amount")
        lead, opportunity, _customer = convert_lead(lead, request.user, won=won, amount=amount)
        return Response(
            {
                "lead": LeadSerializer(lead, context={"request": request}).data,
                "opportunity": OpportunitySerializer(opportunity, context={"request": request}).data,
            }
        )

    @action(detail=True, methods=["get", "post"], url_path="activities")
    def activities(self, request, pk=None):
        lead = self.get_object()
        if request.method.lower() == "get":
            qs = LeadActivity.objects.filter(company=self.company, lead=lead).order_by("-created_at")
            return Response(LeadActivitySerializer(qs, many=True).data)
        serializer = LeadActivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            lead=lead,
            company=lead.company,
            created_by=request.user,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OpportunityViewSet(CompanyScopedViewSet):
    queryset = Opportunity.objects.select_related("lead")
    serializer_class = OpportunitySerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "Opportunity"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_crm_enabled(get_company_user(request).company)
