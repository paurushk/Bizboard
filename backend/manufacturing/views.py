from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.permissions import DenyViewerWrite, HasCompany, get_company_user
from core.viewsets import CompanyScopedViewSet

from .models import Bom, WorkOrder
from .permissions import assert_manufacturing_enabled
from .serializers import BomSerializer, WorkOrderSerializer
from .services import cancel_work_order, complete_work_order, release_work_order


class BomViewSet(CompanyScopedViewSet):
    queryset = Bom.objects.prefetch_related("lines__component").select_related("product")
    serializer_class = BomSerializer
    permission_classes = [IsAuthenticated, HasCompany, DenyViewerWrite]
    audit_entity = "Bom"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_manufacturing_enabled(get_company_user(request).company)


class WorkOrderViewSet(CompanyScopedViewSet):
    queryset = WorkOrder.objects.select_related("bom", "warehouse").prefetch_related(
        "component_lines__component"
    )
    serializer_class = WorkOrderSerializer
    permission_classes = [IsAuthenticated, HasCompany, DenyViewerWrite]
    audit_entity = "WorkOrder"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_manufacturing_enabled(get_company_user(request).company)

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        wo = self.get_object()
        try:
            wo = release_work_order(wo, request.user)
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(wo).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        wo = self.get_object()
        try:
            wo = complete_work_order(wo, request.user)
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(wo).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        wo = self.get_object()
        try:
            wo = cancel_work_order(wo, request.user)
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(wo).data)
