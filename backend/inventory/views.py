from django.db import transaction
from django.db.models import F
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import (
    CanManageInventory,
    CanViewFinancialReports,
    CanViewInventorySurfaces,
    HasCompany,
    get_company_user,
)
from core.viewsets import CompanyScopedViewSet
from core.services.audit import AuditService
from masters.models import Product

from .models import BatchLot, MovementType, SerialNumber, StockBalance, StockMovement, StockTransfer, Warehouse
from .serializers import (
    AdjustmentSerializer,
    OpeningStockSerializer,
    StockBalanceSerializer,
    StockMovementSerializer,
    BatchLotSerializer,
    SerialNumberSerializer,
    StockTransferSerializer,
    WarehouseSerializer,
)
from .services import InventoryService, InventoryValuationService, StockTransferService


class StockBalanceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = StockBalanceSerializer
    # BB-000420: cost/qty balances are not for VIEWER.
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]
    queryset = StockBalance.objects.select_related("product")

    def get_queryset(self):
        qs = self.queryset.filter(company=get_company_user(self.request).company)
        if self.request.query_params.get("low_stock") == "1":
            # INV-08: reorder alerts use available (on_hand - reserved).
            qs = qs.annotate(_available=F("on_hand") - F("reserved")).filter(
                _available__lte=F("product__reorder_level")
            )
        if warehouse := self.request.query_params.get("warehouse"):
            qs = qs.filter(warehouse_id=warehouse)
        if product := self.request.query_params.get("product"):
            qs = qs.filter(product_id=product)
        return qs


class StockMovementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = StockMovementSerializer
    # BB-000618: unit_cost / movement detail is not HasCompany-only for VIEWER.
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]
    queryset = StockMovement.objects.select_related("product")

    def get_queryset(self):
        qs = self.queryset.filter(company=get_company_user(self.request).company)
        product = self.request.query_params.get("product")
        if product:
            qs = qs.filter(product_id=product)
        movement_type = self.request.query_params.get("movement_type")
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        if warehouse := self.request.query_params.get("warehouse"):
            qs = qs.filter(warehouse_id=warehouse)
        return qs


class AdjustmentView(APIView):
    """Manual stock adjustment with reason → ADJUSTMENT movement (E2.4)."""

    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def post(self, request):
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = get_company_user(request).company
        product = get_object_or_404(Product, pk=serializer.validated_data["product"], company=company)
        warehouse_id = serializer.validated_data.get("warehouse")
        if warehouse_id is not None:
            warehouse = Warehouse.objects.filter(pk=warehouse_id, company=company).first()
            if warehouse is None:
                raise BusinessRuleError("Invalid warehouse for this company.")
        else:
            warehouse = None
        batch_id = serializer.validated_data.get("batch")
        if batch_id is not None:
            batch = BatchLot.objects.filter(pk=batch_id, company=company).first()
            if batch is None:
                raise BusinessRuleError("Invalid batch for this company.")
        else:
            batch = None
        movement = InventoryService.post_movement(
            company=company,
            product=product,
            movement_type=MovementType.ADJUSTMENT,
            quantity=serializer.validated_data["quantity"],
            reason=serializer.validated_data["reason"],
            reference_type="manual_adjustment",
            user=request.user,
            warehouse=warehouse,
            batch=batch,
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
        warehouse_id = serializer.validated_data.get("warehouse")
        if warehouse_id is not None:
            warehouse = Warehouse.objects.filter(pk=warehouse_id, company=company).first()
            if warehouse is None:
                raise BusinessRuleError("Invalid warehouse for this company.")
        else:
            warehouse = None
        batch_id = serializer.validated_data.get("batch")
        if batch_id is not None:
            batch = BatchLot.objects.filter(pk=batch_id, company=company).first()
            if batch is None:
                raise BusinessRuleError("Invalid batch for this company.")
        else:
            batch = None
        # BB-000705: movement + GL post as one atomic unit.
        with transaction.atomic():
            movement = InventoryService.post_movement(
                company=company,
                product=product,
                movement_type=MovementType.OPENING_STOCK,
                quantity=serializer.validated_data["quantity"],
                unit_cost=serializer.validated_data.get("unit_cost"),
                reference_type="opening_stock",
                user=request.user,
                warehouse=warehouse,
                batch=batch,
            )
            if company.accounting_enabled:
                from accounting.services import PostingService

                PostingService.post_opening_stock(movement, request.user)
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


class LowStockAlertsView(APIView):
    """Low stock / reorder alerts (E2.6)."""

    # BB-000618: qty/reorder alerts expose inventory position.
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]

    def get(self, request):
        company = get_company_user(request).company
        balances = (
            StockBalance.objects.select_related("product")
            .annotate(_available=F("on_hand") - F("reserved"))
            .filter(
                company=company,
                product__status="ACTIVE",
                _available__lte=F("product__reorder_level"),
            )
        )
        return Response({
            "count": balances.count(),
            "items": StockBalanceSerializer(balances, many=True).data,
        })


class WarehouseViewSet(CompanyScopedViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    # BB-000388: mutate requires inventory capability (not HasCompany-only).
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def get_permissions(self):
        if getattr(self, "action", None) in ("list", "retrieve"):
            # BB-000618: VIEWER must not browse warehouse/stock locations.
            return [IsAuthenticated(), HasCompany(), CanViewInventorySurfaces()]
        return [IsAuthenticated(), HasCompany(), CanManageInventory()]

    def perform_create(self, serializer):
        if not Warehouse.objects.filter(company=self.company).exists():
            serializer.save(company=self.company, created_by=self.request.user, updated_by=self.request.user, is_default=True)
        else:
            super().perform_create(serializer)


class StockTransferViewSet(CompanyScopedViewSet):
    queryset = StockTransfer.objects.select_related("from_warehouse", "to_warehouse").prefetch_related("lines")
    serializer_class = StockTransferSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return Response(self.get_serializer(StockTransferService.complete(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(self.get_serializer(StockTransferService.cancel(self.get_object(), request.user)).data)


class BatchLotViewSet(CompanyScopedViewSet):
    queryset = BatchLot.objects.select_related("product")
    serializer_class = BatchLotSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def get_queryset(self):
        qs = super().get_queryset()
        if product := self.request.query_params.get("product"):
            qs = qs.filter(product_id=product)
        return qs


class SerialNumberViewSet(CompanyScopedViewSet):
    queryset = SerialNumber.objects.select_related("product", "warehouse")
    serializer_class = SerialNumberSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def get_queryset(self):
        qs = super().get_queryset()
        if status := self.request.query_params.get("status"):
            qs = qs.filter(status=status)
        return qs

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        serial = self.get_object()
        target = request.data.get("status")
        allowed = {
            SerialNumber.Status.AVAILABLE: {SerialNumber.Status.SOLD, SerialNumber.Status.SCRAPPED},
            SerialNumber.Status.SOLD: {SerialNumber.Status.RETURNED},
            SerialNumber.Status.RETURNED: {SerialNumber.Status.AVAILABLE, SerialNumber.Status.SCRAPPED},
            SerialNumber.Status.SCRAPPED: set(),
        }
        if target not in allowed.get(serial.status, set()):
            return Response({"detail": "Invalid serial status transition."}, status=status.HTTP_400_BAD_REQUEST)
        serial.status = target
        serial.warehouse_id = request.data.get("warehouse", serial.warehouse_id)
        serial.updated_by = request.user
        serial.save(update_fields=["status", "warehouse", "updated_by", "updated_at"])
        return Response(self.get_serializer(serial).data)


class ExpiryAlertsView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]

    def get(self, request):
        company = get_company_user(request).company
        days = int(request.query_params.get("days", 30))
        from django.utils import timezone
        from datetime import timedelta
        lots = BatchLot.objects.filter(
            company=company, expiry_date__isnull=False,
            expiry_date__lte=timezone.localdate() + timedelta(days=days),
            stock_balances__on_hand__gt=0,
        ).distinct()
        return Response({"count": lots.count(), "items": BatchLotSerializer(lots, many=True).data})


class StockValuationReportView(APIView):
    # BB-000420: valuation is a financial surface.
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request):
        company = get_company_user(request).company
        warehouse = Warehouse.objects.filter(company=company, pk=request.query_params.get("warehouse")).first()
        rows = InventoryValuationService.valuation(
            company, method=request.query_params.get("method"), as_of=request.query_params.get("as_of"),
            warehouse=warehouse,
        )
        return Response({"method": request.query_params.get("method") or company.inventory_valuation_method, "items": rows})
