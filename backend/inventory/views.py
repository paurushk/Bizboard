from django.db.models import F
from rest_framework import mixins, status, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import CanManageInventory, HasCompany, get_company_user
from core.services.audit import AuditService
from masters.models import Product

from .models import MovementType, StockBalance, StockMovement
from .serializers import (
    AdjustmentSerializer,
    OpeningStockSerializer,
    StockBalanceSerializer,
    StockMovementSerializer,
)
from .services import InventoryService


class StockBalanceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = StockBalanceSerializer
    permission_classes = [IsAuthenticated, HasCompany]
    queryset = StockBalance.objects.select_related("product")

    def get_queryset(self):
        qs = self.queryset.filter(company=get_company_user(self.request).company)
        if self.request.query_params.get("low_stock") == "1":
            qs = qs.filter(on_hand__lte=F("product__reorder_level"))
        return qs


class StockMovementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated, HasCompany]
    queryset = StockMovement.objects.select_related("product")

    def get_queryset(self):
        qs = self.queryset.filter(company=get_company_user(self.request).company)
        product = self.request.query_params.get("product")
        if product:
            qs = qs.filter(product_id=product)
        movement_type = self.request.query_params.get("movement_type")
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        return qs


class AdjustmentView(APIView):
    """Manual stock adjustment with reason → ADJUSTMENT movement (E2.4)."""

    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def post(self, request):
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = get_company_user(request).company
        product = get_object_or_404(Product, pk=serializer.validated_data["product"], company=company)
        movement = InventoryService.post_movement(
            company=company,
            product=product,
            movement_type=MovementType.ADJUSTMENT,
            quantity=serializer.validated_data["quantity"],
            reason=serializer.validated_data["reason"],
            reference_type="manual_adjustment",
            user=request.user,
        )
        AuditService.log(
            company=company, user=request.user, action="CREATE",
            entity_type="StockMovement", entity_id=movement.id,
            description=f"Adjustment: {serializer.validated_data['reason']}",
        )
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


class OpeningStockView(APIView):
    """Opening stock entry → OPENING_STOCK movement (E2.3)."""

    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def post(self, request):
        serializer = OpeningStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = get_company_user(request).company
        product = get_object_or_404(Product, pk=serializer.validated_data["product"], company=company)
        movement = InventoryService.post_movement(
            company=company,
            product=product,
            movement_type=MovementType.OPENING_STOCK,
            quantity=serializer.validated_data["quantity"],
            unit_cost=serializer.validated_data.get("unit_cost"),
            reference_type="opening_stock",
            user=request.user,
        )
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


class LowStockAlertsView(APIView):
    """Low stock / reorder alerts (E2.6)."""

    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        company = get_company_user(request).company
        balances = (
            StockBalance.objects.select_related("product")
            .filter(company=company, product__status="ACTIVE", on_hand__lte=F("product__reorder_level"))
        )
        return Response({
            "count": balances.count(),
            "items": StockBalanceSerializer(balances, many=True).data,
        })
