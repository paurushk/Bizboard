from decimal import Decimal

from django.db import transaction
from django.db.models import F, OuterRef, Subquery
from django.db.models.functions import Coalesce
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError, StockCountConflict
from core.idempotency import wrap_idempotent
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

from .models import (
    BatchLot, MovementType, SerialNumber, StockBalance, StockCountSession,
    StockMovement, StockTransfer, Warehouse, WarehouseReorderLevel,
)
from .serializers import (
    AdjustmentSerializer,
    OpeningStockSerializer,
    StockBalanceSerializer,
    StockCountSessionSerializer,
    StockMovementSerializer,
    BatchLotSerializer,
    SerialNumberSerializer,
    StockTransferSerializer,
    WarehouseReorderLevelSerializer,
    WarehouseSerializer,
)
from .services import InventoryService, InventoryValuationService, StockTransferService


def _effective_reorder_annotation():
    warehouse_reorder = WarehouseReorderLevel.objects.filter(
        company_id=OuterRef("company_id"),
        warehouse_id=OuterRef("warehouse_id"),
        product_id=OuterRef("product_id"),
    ).values("reorder_level")[:1]
    return Coalesce(Subquery(warehouse_reorder), F("product__reorder_level"))


def low_stock_alert_payload(company):
    """Company-wide low stock unless a per-godown reorder override exists (E2E3-019)."""
    from collections import defaultdict

    override_keys = set(
        WarehouseReorderLevel.objects.filter(company=company).values_list(
            "product_id", "warehouse_id"
        )
    )
    balances = list(
        StockBalance.objects.select_related("product", "warehouse")
        .filter(company=company, product__status="ACTIVE")
        .annotate(
            _available=F("on_hand") - F("reserved"),
            _reorder=_effective_reorder_annotation(),
        )
    )
    totals = defaultdict(lambda: Decimal("0"))
    for row in balances:
        totals[row.product_id] += row._available

    items = []
    seen = set()
    for row in balances:
        key = (row.product_id, row.warehouse_id)
        if key in override_keys:
            if row._available <= row._reorder:
                items.append(row)
            continue
        if row.product_id in seen:
            continue
        seen.add(row.product_id)
        reorder = row.product.reorder_level or Decimal("0")
        if totals[row.product_id] <= reorder:
            row.on_hand = totals[row.product_id]
            row.reserved = Decimal("0")
            items.append(row)
    return items


class StockBalanceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = StockBalanceSerializer
    # BB-000420: cost/qty balances are not for VIEWER.
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]
    queryset = StockBalance.objects.select_related("product")

    def get_queryset(self):
        qs = self.queryset.filter(company=get_company_user(self.request).company)
        from django.db.models import Q
        from masters.custom_fields import active_defs, apply_cf_filters, build_search_q

        if self.request.query_params.get("low_stock") == "1":
            qs = qs.annotate(
                _available=F("on_hand") - F("reserved"),
                _reorder=_effective_reorder_annotation(),
            ).filter(_available__lte=F("_reorder"))
        if warehouse := self.request.query_params.get("warehouse"):
            qs = qs.filter(warehouse_id=warehouse)
        if product := self.request.query_params.get("product"):
            qs = qs.filter(product_id=product)
        company = get_company_user(self.request).company
        defs = active_defs(company)
        q = self.request.query_params.get("search") or self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(product__name__icontains=q)
                | Q(product__sku__icontains=q)
                | Q(product__barcode__icontains=q)
                | Q(product__hsn_code__icontains=q)
                | build_search_q(q, defs, prefix="product__")
            )
        qs = apply_cf_filters(qs, self.request.query_params, defs, prefix="product__")
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
        batch_no = (serializer.validated_data.get("batch_no") or "").strip()
        if batch_id is not None:
            batch = BatchLot.objects.filter(pk=batch_id, company=company, product=product).first()
            if batch is None:
                raise BusinessRuleError("Invalid batch for this company.")
        elif batch_no:
            from .item_stock import get_or_create_batch

            batch = get_or_create_batch(
                company=company, product=product, batch_no=batch_no, user=request.user,
            )
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
        data = serializer.validated_data
        quantity = data.get("quantity")
        serials = data.get("serial_numbers") or []
        if quantity is None:
            quantity = Decimal(len(serials))
        warehouse_id = data.get("warehouse")
        if warehouse_id is not None:
            warehouse = Warehouse.objects.filter(pk=warehouse_id, company=company).first()
            if warehouse is None:
                raise BusinessRuleError("Invalid warehouse for this company.")
        else:
            warehouse = None
        batch_id = data.get("batch")
        if batch_id is not None:
            batch = BatchLot.objects.filter(pk=batch_id, company=company, product=product).first()
            if batch is None:
                raise BusinessRuleError("Invalid batch for this product.")
        else:
            batch = None
        with transaction.atomic():
            movement = InventoryService.post_opening(
                company=company,
                product=product,
                quantity=quantity,
                unit_cost=data.get("unit_cost"),
                warehouse=warehouse,
                batch=batch,
                batch_no=data.get("batch_no") or "",
                expiry_date=data.get("expiry_date"),
                manufacturing_date=data.get("manufacturing_date"),
                serial_numbers=serials,
                as_of=data.get("as_of"),
                user=request.user,
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
        balances = low_stock_alert_payload(company)
        return Response({
            "count": len(balances),
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

    def perform_update(self, serializer):
        from .item_stock import assert_can_deactivate_warehouse

        instance = self.get_object()
        becoming_inactive = serializer.validated_data.get("is_active") is False and instance.is_active
        if becoming_inactive:
            assert_can_deactivate_warehouse(instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        from .item_stock import assert_can_delete_warehouse

        assert_can_delete_warehouse(instance)
        super().perform_destroy(instance)


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
        warehouse_id = request.data.get("warehouse", serial.warehouse_id)
        if warehouse_id:
            from inventory.models import Warehouse

            if not Warehouse.objects.filter(company=self.company, pk=warehouse_id).exists():
                return Response({"detail": "Warehouse does not belong to this company."}, status=status.HTTP_400_BAD_REQUEST)
        serial.status = target
        serial.warehouse_id = warehouse_id
        serial.updated_by = request.user
        serial.save(update_fields=["status", "warehouse", "updated_by", "updated_at"])
        return Response(self.get_serializer(serial).data)


class ExpiryAlertsView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), HasCompany(), CanManageInventory()]
        return [IsAuthenticated(), HasCompany(), CanViewInventorySurfaces()]

    def get(self, request):
        company = get_company_user(request).company
        days = int(request.query_params.get("days", 30))
        warehouse_id = request.query_params.get("warehouse")
        from .item_stock import expiry_horizon_rows, record_expiry_bands

        rows = expiry_horizon_rows(company, days=days, warehouse_id=warehouse_id)
        record_expiry_bands(company, rows)
        return Response({"count": len(rows), "items": rows})

    def post(self, request):
        """Write off remaining qty of an expired/near-expiry lot as ADJUSTMENT / EXPIRED."""
        from .item_stock import remaining_qty

        company = get_company_user(request).company
        product = get_object_or_404(Product, pk=request.data.get("product"), company=company)
        warehouse = Warehouse.objects.filter(pk=request.data.get("warehouse"), company=company).first()
        if warehouse is None:
            raise BusinessRuleError("Godown is required for expiry write-off.")
        batch = BatchLot.objects.filter(pk=request.data.get("batch"), company=company, product=product).first()
        if batch is None:
            raise BusinessRuleError("Invalid batch for this product.")
        qty = Decimal(str(request.data.get("quantity") or 0))
        if qty <= 0:
            raise BusinessRuleError("Write-off quantity must be greater than zero.")
        on_hand = remaining_qty(company, product, warehouse=warehouse, batch=batch)
        available = InventoryService.available_quantity(company, product, warehouse, batch)
        if qty > available:
            raise BusinessRuleError(
                f"Cannot write off {qty} — only {available} available on this lot at this godown "
                f"({on_hand} on hand)."
            )
        movement = InventoryService.post_movement(
            company=company,
            product=product,
            movement_type=MovementType.ADJUSTMENT,
            quantity=-qty,
            reason="EXPIRED",
            reference_type="expiry_write_off",
            user=request.user,
            warehouse=warehouse,
            batch=batch,
        )
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


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
        basis = (request.query_params.get("basis") or "cost").strip().lower()
        if basis in ("purchase", "selling", "mrp"):
            from decimal import Decimal

            from masters.models import Product

            field = {"purchase": "purchase_price", "selling": "selling_price", "mrp": "mrp"}[basis]
            products = {
                p.id: p
                for p in Product.objects.filter(
                    company=company, pk__in=[r.get("product") for r in rows if r.get("product")]
                )
            }
            for row in rows:
                product = products.get(row.get("product"))
                price = Decimal(str(getattr(product, field, 0) or 0)) if product else Decimal("0")
                qty = Decimal(str(row.get("qty") or row.get("quantity") or 0))
                row["unit_cost"] = price
                row["value"] = price * qty
                row["basis"] = basis
        return Response({
            "method": request.query_params.get("method") or company.inventory_valuation_method,
            "basis": basis if basis in ("purchase", "selling", "mrp") else "cost",
            "items": rows,
        })


class WarehouseReorderLevelViewSet(CompanyScopedViewSet):
    queryset = WarehouseReorderLevel.objects.select_related("warehouse", "product")
    serializer_class = WarehouseReorderLevelSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]


class StockCountSessionViewSet(CompanyScopedViewSet):
    queryset = StockCountSession.objects.select_related("warehouse").prefetch_related("lines__product", "lines__batch")
    serializer_class = StockCountSessionSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        from django.utils import timezone

        def _run():
            with transaction.atomic():
                session = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
                if session.status == StockCountSession.Status.POSTED:
                    return Response(self.get_serializer(session).data)
                if session.status == StockCountSession.Status.CANCELLED:
                    raise BusinessRuleError("A cancelled count cannot be posted.")
                if session.status != StockCountSession.Status.COUNTED:
                    raise BusinessRuleError("Save the count before posting.")
                if session.lines.filter(counted_qty__isnull=True).exists():
                    raise BusinessRuleError("Save all counted quantities before posting.")
                from .item_stock import remaining_qty

                lines = list(session.lines.select_related("product", "batch"))
                conflicts = []
                current_by_line = {}
                for line in lines:
                    if line.counted_qty is None:
                        continue
                    if line.product.company_id != session.company_id:
                        raise BusinessRuleError("Invalid product on stock count line.")
                    current = remaining_qty(
                        session.company, line.product, warehouse=session.warehouse, batch=line.batch,
                        unbatched_only=line.batch_id is None,
                    )
                    current_by_line[line.pk] = current
                    if current != line.system_qty:
                        conflicts.append({
                            "line_id": line.pk,
                            "product_name": line.product.name,
                            "server_qty": str(current),
                            "local_qty": str(line.counted_qty),
                            "snapshot_qty": str(line.system_qty),
                        })
                resolve = str(request.data.get("resolve_conflicts") or "").upper()
                if conflicts and resolve not in ("KEEP_SERVER", "KEEP_LOCAL"):
                    raise StockCountConflict(conflicts)
                for line in lines:
                    if line.counted_qty is None:
                        continue
                    current = current_by_line[line.pk]
                    if conflicts and current != line.system_qty and resolve == "KEEP_SERVER":
                        continue
                    variance = line.counted_qty - current
                    if variance == 0:
                        continue
                    InventoryService.post_movement(
                        company=session.company,
                        product=line.product,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=variance,
                        reason="STOCK_COUNT",
                        reference_type="stock_count",
                        reference_id=session.pk,
                        user=request.user,
                        warehouse=session.warehouse,
                        batch=line.batch,
                    )
                session.status = StockCountSession.Status.POSTED
                session.posted_at = timezone.now()
                session.save(update_fields=["status", "posted_at"])
            return Response(self.get_serializer(session).data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="stock_count_post",
            build=_run,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        session = self.get_object()
        if session.status == StockCountSession.Status.POSTED:
            raise BusinessRuleError("A posted count cannot be cancelled.")
        if session.status == StockCountSession.Status.CANCELLED:
            return Response(self.get_serializer(session).data)
        session.status = StockCountSession.Status.CANCELLED
        session.save(update_fields=["status"])
        return Response(self.get_serializer(session).data)
