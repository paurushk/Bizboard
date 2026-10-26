from accounting.books import posts_to_ledger
from decimal import Decimal

from django.db import transaction
from django.http import HttpResponse, StreamingHttpResponse
from django.db.models import F, Q, Sum, Window
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination

from core.pagination import DefaultPagination
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError, StockCountConflict
from core.idempotency import IdempotentCreateMixin, wrap_idempotent
from core.permissions import (
    CanManageInventory,
    CanViewFinancialReports,
    CanViewInventorySurfaces,
    CanViewWarehouseSurfaces,
    HasCompany,
    get_company_user,
)
from core.viewsets import CompanyScopedViewSet
from core.services.audit import AuditService
from masters.models import Product

from .models import (
    BatchLot, MovementType, SerialNumber, StockBalance, StockCountLine, StockCountSession,
    StockMovement, StockTransfer, Warehouse, WarehouseReorderLevel,
)
from .serializers import (
    AdjustmentSerializer,
    OpeningStockSerializer,
    StockBalanceSerializer,
    StockCountSessionSerializer,
    StockLedgerSerializer,
    StockMovementSerializer,
    BatchLotSerializer,
    SerialNumberSerializer,
    StockTransferSerializer,
    WarehouseReorderLevelSerializer,
    WarehouseSerializer,
)
from .low_stock import low_stock_rows
from .services import InventoryService, InventoryValuationService, StockTransferService


def low_stock_alert_payload(company, status="low"):
    """Rows for the low-stock alerts. The definition lives in :mod:`inventory.low_stock` (INV-WP-08)."""
    return low_stock_rows(company, status=status)


class _GroupedPagination(DefaultPagination):
    """Pages a grouped (GROUP BY) queryset. The default class appends the primary key to the
    ordering for stability, which would split every group back into its rows."""

    def paginate_queryset(self, queryset, request, view=None):
        return PageNumberPagination.paginate_queryset(self, queryset, request, view)


class StockBalanceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = StockBalanceSerializer
    # BB-000420: cost/qty balances are not for VIEWER.
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]
    queryset = StockBalance.objects.select_related("product", "warehouse", "batch")

    def get_queryset(self):
        qs = self.queryset.filter(company=get_company_user(self.request).company)
        from masters.custom_fields import active_defs, apply_cf_filters, build_search_q

        if self.request.query_params.get("low_stock") == "1":
            # INV-WP-08: the same rows the Low stock page lists, not a second per-row rule.
            low = low_stock_rows(get_company_user(self.request).company, status="low")
            godown_pairs = Q()
            company_wide = set()
            for row in low:
                if row.is_warehouse_specific:
                    godown_pairs |= Q(product_id=row.product_id, warehouse_id=row.warehouse_id)
                else:
                    company_wide.add(row.product_id)
            qs = qs.filter(godown_pairs | Q(product_id__in=company_wide)) if (company_wide or low) else qs.none()
        if warehouse := self.request.query_params.get("warehouse"):
            qs = qs.filter(warehouse_id=warehouse)
        if product := self.request.query_params.get("product"):
            qs = qs.filter(product_id=product)
        raw_ids = (self.request.query_params.get("product_ids") or "").strip()
        if raw_ids:
            ids = [int(part) for part in raw_ids.split(",") if part.strip().isdigit()]
            qs = qs.filter(product_id__in=ids[:250])
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
        if self.action != "by_product":
            # INV-IDR-10: "only what is out, zero or negative" for the flat list. The grouped list
            # applies the same rule to the item's total, so it filters after the sum.
            if self.request.query_params.get("negative") in ("1", "true"):
                qs = qs.annotate(_avail=F("on_hand") - F("reserved")).filter(_avail__lte=0)
        return qs

    BY_PRODUCT_ORDERING = {
        "name": ("product__name", "product_id"),
        "-name": ("-product__name", "product_id"),
        "available": ("available_total", "product__name", "product_id"),
        "-available": ("-available_total", "product__name", "product_id"),
        "on_hand": ("on_hand_total", "product__name", "product_id"),
        "-on_hand": ("-on_hand_total", "product__name", "product_id"),
    }

    @action(detail=False, methods=["get"], url_path="by-product")
    def by_product(self, request):
        """One row per item (summed over godowns and lots), paged on the server (INV-IDR-10).

        The Current stock page used to download every product x godown x lot row and add them up in
        the browser. The same filters apply here; lots for one item come from ``?product=<id>``.
        """
        from django.db.models import Count, Min

        from masters.models import Product

        params = request.query_params
        base = self.filter_queryset(self.get_queryset()).order_by()
        grouped = (
            base.values("product_id", "product__name", "product__sku", "product__rack_code")
            .annotate(
                on_hand_total=Sum("on_hand"),
                reserved_total=Sum("reserved"),
                available_total=Sum("on_hand") - Sum("reserved"),
                lot_count=Count("id"),
                nearest_expiry=Min("batch__expiry_date"),
            )
        )
        # Totals for the chips come from the whole filtered set, not just the page on screen.
        availabilities = list(grouped.values_list("available_total", flat=True))
        summary = {
            "items": len(availabilities),
            "items_in_stock": sum(1 for a in availabilities if (a or 0) > 0),
            "items_out": sum(1 for a in availabilities if (a or 0) <= 0),
        }
        if params.get("negative") in ("1", "true"):
            grouped = grouped.filter(available_total__lte=0)
        ordering = self.BY_PRODUCT_ORDERING.get(params.get("ordering", "name"), self.BY_PRODUCT_ORDERING["name"])
        paginator = _GroupedPagination()
        page = paginator.paginate_queryset(grouped.order_by(*ordering), request, view=self)
        rows = list(page)
        extras = {
            p["id"]: p
            for p in Product.objects.filter(pk__in=[r["product_id"] for r in rows]).values("id", "custom_fields")
        }
        warehouse = params.get("warehouse")
        data = [
            {
                "product": r["product_id"],
                "product_name": r["product__name"],
                "sku": r["product__sku"],
                "rack_code": r["product__rack_code"] or "",
                "custom_fields": (extras.get(r["product_id"]) or {}).get("custom_fields") or {},
                "warehouse": int(warehouse) if warehouse and str(warehouse).isdigit() else None,
                "on_hand": r["on_hand_total"],
                "reserved": r["reserved_total"],
                "available": r["available_total"],
                "lots": r["lot_count"],
                "nearest_expiry": r["nearest_expiry"],
            }
            for r in rows
        ]
        response = paginator.get_paginated_response(data)
        response.data["summary"] = summary
        return response


class StockMovementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The item ledger: every movement, filterable, with a running balance for one item."""

    serializer_class = StockLedgerSerializer
    # BB-000618: unit_cost / movement detail is not HasCompany-only for VIEWER.
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]
    queryset = StockMovement.objects.select_related("product", "warehouse", "batch", "created_by")

    def _filtered(self):
        qs = self.queryset.filter(company=get_company_user(self.request).company)
        params = self.request.query_params
        if product := params.get("product"):
            qs = qs.filter(product_id=product)
        if movement_type := params.get("movement_type"):
            qs = qs.filter(movement_type=movement_type)
        if warehouse := params.get("warehouse"):
            qs = qs.filter(warehouse_id=warehouse)
        if batch := params.get("batch"):
            qs = qs.filter(batch_id=batch)
        if reference_type := params.get("reference_type"):
            qs = qs.filter(reference_type=reference_type)
        if reason_code := params.get("reason_code"):
            qs = qs.filter(reason_code=reason_code)
        if date_from := params.get("date_from"):
            qs = qs.filter(movement_date__gte=date_from)
        if date_to := params.get("date_to"):
            qs = qs.filter(movement_date__lte=date_to)
        if q := (params.get("search") or params.get("q") or "").strip():
            qs = qs.filter(
                Q(product__name__icontains=q) | Q(product__sku__icontains=q)
                | Q(batch__batch_no__icontains=q) | Q(reason__icontains=q)
            )
        return qs

    def _show_cost(self):
        return _can_see_costs(self.request)

    def get_queryset(self):
        qs = self._filtered()
        if self.request.query_params.get("product"):
            # A running balance only means something for one item. The window runs over the rows
            # that pass the filters, in time order; the page then shows newest first.
            qs = qs.annotate(
                _running=Window(Sum("quantity"), order_by=[F("movement_date").asc(), F("id").asc()])
            )
        return qs.order_by("-movement_date", "-id")

    def _opening(self):
        """Stock the item already held before the first day shown, so the balance column starts right."""
        params = self.request.query_params
        date_from = params.get("date_from")
        if not (params.get("product") and date_from):
            return Decimal("0")
        qs = StockMovement.objects.filter(
            company=get_company_user(self.request).company, product_id=params["product"],
            movement_date__lt=date_from,
        )
        for key, field in (("warehouse", "warehouse_id"), ("batch", "batch_id")):
            if params.get(key):
                qs = qs.filter(**{field: params[key]})
        return qs.aggregate(total=Sum("quantity"))["total"] or Decimal("0")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["show_cost"] = self._show_cost()
        context["opening"] = self._opening()
        return context

    @action(detail=False, methods=["get"], url_path="export")
    def export_csv(self, request):
        """BUG-SEC-005: stream movement rows instead of building one in-memory list."""
        import csv

        show_cost = self._show_cost()
        qs = self._filtered().order_by("movement_date", "id")

        class _Echo:
            def write(self, value):
                return value

        writer = csv.writer(_Echo())

        def _safe(value):
            # A spreadsheet runs a cell that starts with = + - @ as a formula.
            text = "" if value is None else str(value)
            return "'" + text if text[:1] in ("=", "+", "-", "@") else text

        def _rows():
            header = ["Date", "Item", "SKU", "Godown", "Batch", "Type", "Quantity"]
            if show_cost:
                header.append("Unit cost")
            header += ["Reason", "Reference", "Reference id", "By"]
            yield writer.writerow(header)
            for row in qs.iterator(chunk_size=500):
                by = getattr(row.created_by, "full_name", "") or getattr(row.created_by, "email", "") or ""
                line = [
                    row.movement_date, _safe(row.product.name), _safe(row.product.sku),
                    _safe(row.warehouse.name if row.warehouse_id else ""),
                    _safe(row.batch.batch_no if row.batch_id else ""),
                    row.get_movement_type_display(), row.quantity,
                ]
                if show_cost:
                    line.append(row.unit_cost if row.unit_cost is not None else "")
                line += [_safe(row.reason), row.reference_type, row.reference_id, _safe(by)]
                yield writer.writerow(line)

        response = StreamingHttpResponse(_rows(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="stock-ledger.csv"'
        return response


# Label sizes in printer dots (203 dpi: 8 dots to the millimetre) - 2.6x1.3in, 3.2x2in and 4x2.5in.
ZPL_SIZES = {
    "small": (528, 264),
    "medium": (650, 406),
    "large": (812, 508),
}
MAX_ZPL_LABELS = 500


def code128_ok(code: str) -> bool:
    """CODE128 (subset B) takes printable ASCII. Anything else prints as a blank or wrong barcode."""
    return bool(code) and all(32 <= ord(ch) <= 126 for ch in code)


def _zpl_text(value: str, limit: int) -> str:
    return (value or "")[:limit].replace("^", " ").replace("~", " ")


def zpl_barcode_label(
    *, name: str, code: str, copies: int = 1, size: str = "small",
    price: str | None = None, batch_no: str = "", expiry: str = "",
) -> str:
    """Raw ZPL for a warehouse barcode printer (BUG-INV-006).

    The label carries what the browser label carries: name, barcode, price (when asked) and the lot
    with its expiry date. ``^PW``/``^LL`` set the label width and length for the chosen size.
    """
    width, length = ZPL_SIZES.get(size, ZPL_SIZES["small"])
    safe_name = _zpl_text(name, 40)
    safe_code = (code or "ITEM")[:40].replace("^", "").replace("~", "")
    try:
        copies = int(copies or 1)
    except (TypeError, ValueError):
        copies = 1
    copies = max(1, min(copies, 50))
    lines = [
        "^XA",
        f"^PW{width}",
        f"^LL{length}",
        f"^FO24,16^A0N,28,28^FD{safe_name}^FS",
        f"^FO24,54^BY2^BCN,{max(50, length // 4)},Y,N,N^FD{safe_code}^FS",
    ]
    y = 54 + max(50, length // 4) + 44
    if price:
        lines.append(f"^FO24,{y}^A0N,30,30^FD{_zpl_text(price, 16)}^FS")
        y += 36
    if batch_no:
        lot = f"Batch {_zpl_text(batch_no, 20)}"
        if expiry:
            lot += f"  Exp {_zpl_text(expiry, 12)}"
        lines.append(f"^FO24,{y}^A0N,24,24^FD{lot}^FS")
    lines.append("^XZ")
    return ("\n".join(lines) + "\n") * copies


def _label_price(product) -> str:
    """The shelf price: MRP when set, else the selling price (the browser label does the same)."""
    mrp = Decimal(str(product.mrp or 0))
    value = mrp if mrp > 0 else Decimal(str(product.selling_price or 0))
    return f"Rs {value:.2f}"


def _label_for(company, product, copies, size, batch_id, include_price) -> str:
    code = (product.barcode or product.sku or str(product.pk))
    if not code128_ok(code):
        raise BusinessRuleError(
            f"'{product.name}' has a code ({code}) that cannot be printed as a barcode. Change its barcode.",
            code="label_code_unencodable",
        )
    batch_no = expiry = ""
    if batch_id:
        lot = get_object_or_404(BatchLot, pk=batch_id, company=company, product=product)
        batch_no = lot.batch_no
        expiry = lot.expiry_date.isoformat() if lot.expiry_date else ""
    return zpl_barcode_label(
        name=product.name, code=code, copies=copies, size=size,
        price=_label_price(product) if include_price else None, batch_no=batch_no, expiry=expiry,
    )


def _truthy(value, default=True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class BarcodeLabelZplView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]

    def get(self, request):
        company = get_company_user(request).company
        product_id = request.query_params.get("product")
        try:
            pk = int(product_id)
        except (TypeError, ValueError):
            raise BusinessRuleError("product is required.")
        product = get_object_or_404(Product, pk=pk, company=company)
        batch = request.query_params.get("batch")
        body = _label_for(
            company, product, request.query_params.get("copies") or 1,
            request.query_params.get("size") or "small",
            int(batch) if batch and str(batch).isdigit() else None,
            _truthy(request.query_params.get("price"), default=True),
        )
        return HttpResponse(body, content_type="text/plain")

    def post(self, request):
        """Several labels in one file: ``{"labels": [{"product", "copies", "batch"}], "size", "price"}``."""
        company = get_company_user(request).company
        rows = request.data.get("labels")
        if not isinstance(rows, list) or not rows:
            raise BusinessRuleError("Send at least one label.")
        size = request.data.get("size") or "small"
        include_price = _truthy(request.data.get("price"), default=True)
        parts, total = [], 0
        for row in rows:
            try:
                pk = int(row.get("product"))
                copies = max(1, min(int(row.get("copies") or 1), 50))
            except (AttributeError, TypeError, ValueError):
                raise BusinessRuleError("Each label needs an item and a number of copies.") from None
            total += copies
            if total > MAX_ZPL_LABELS:
                raise BusinessRuleError(f"One file holds at most {MAX_ZPL_LABELS} labels. Split the run.")
            product = get_object_or_404(Product, pk=pk, company=company)
            batch = row.get("batch")
            parts.append(_label_for(
                company, product, copies, size, int(batch) if batch and str(batch).isdigit() else None, include_price,
            ))
        return HttpResponse("".join(parts), content_type="text/plain")


def _can_see_costs(request) -> bool:
    """What an item cost is for the owner and for anyone allowed financial reports, not for a
    salesperson who may look at stock."""
    cu = get_company_user(request)
    return bool(cu and (cu.role == "OWNER" or cu.can_view_financial_reports))


class AdjustmentView(APIView):
    """Manual stock adjustment with reason → ADJUSTMENT movement (E2.4)."""

    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def post(self, request):
        # INV-WP-01: a retry after a lost response must not post a second movement.
        company = get_company_user(request).company
        return wrap_idempotent(
            request=request,
            company=company,
            scope="stock_adjustment",
            build=lambda: self._post(request),
        )

    @transaction.atomic
    def _post(self, request):
        # B8-014: wrap the whole body so a get_or_create_batch() BatchLot rolls
        # back with a failed post_movement instead of leaving an orphan lot.
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = get_company_user(request).company
        product = get_object_or_404(Product, pk=serializer.validated_data["product"], company=company)
        warehouse_id = serializer.validated_data.get("warehouse")
        if warehouse_id is not None:
            warehouse = Warehouse.objects.filter(pk=warehouse_id, company=company, is_system=False).first()
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
        # B8-013 / CR-011 and INV-IDR-02: period gate, second-person approval, negative-stock check,
        # movement, journal and audit all live in post_stock_loss, shared with the other stock-loss paths.
        from django.utils import timezone as _tz

        from .stock_loss import SOURCE_ADJUSTMENT, StockLoss, post_stock_loss

        adj_date = serializer.validated_data.get("date") or _tz.localdate()
        reason = serializer.validated_data["reason"]
        result = post_stock_loss(
            company,
            request.user,
            StockLoss(
                product=product,
                quantity=Decimal(str(serializer.validated_data["quantity"])),
                reason=reason,
                source=SOURCE_ADJUSTMENT,
                warehouse=warehouse,
                batch=batch,
                reason_code=serializer.validated_data.get("reason_code") or "",
                movement_date=adj_date,
                check_negative=True,
                audit_text=f"Adjustment: {reason}",
            ),
            approval_id=request.data.get("approval_id"),
        )
        if result.pending:
            return Response({"status": "PENDING", "approval_id": result.approval.pk}, status=202)
        data = StockMovementSerializer(result.movement).data
        # INV-WP-01: say plainly that this applied (the other outcome is PENDING / 202).
        data["status"] = "APPLIED"
        if result.warnings:
            data["warnings"] = result.warnings
        return Response(data, status=status.HTTP_201_CREATED)


class OpeningStockView(APIView):
    """Opening stock entry → OPENING_STOCK movement (E2.3)."""

    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def post(self, request):
        company = get_company_user(request).company
        # F3-010: a retry after a partial "item saved but opening stock failed"
        # must not double the quantity for lots that already succeeded.
        return wrap_idempotent(
            request=request,
            company=company,
            scope="opening_stock",
            build=lambda: self._post(request, company),
        )

    def _post(self, request, company):
        serializer = OpeningStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = get_object_or_404(Product, pk=serializer.validated_data["product"], company=company)
        data = serializer.validated_data
        quantity = data.get("quantity")
        serials = data.get("serial_numbers") or []
        if quantity is None:
            quantity = Decimal(len(serials))
        warehouse_id = data.get("warehouse")
        if warehouse_id is not None:
            warehouse = Warehouse.objects.filter(pk=warehouse_id, company=company, is_system=False).first()
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
            if posts_to_ledger(company):
                from accounting.services import PostingService

                PostingService.post_opening_stock(movement, request.user)
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


class LowStockAlertsView(APIView):
    """Low stock / reorder alerts (E2.6)."""

    # BB-000618: qty/reorder alerts expose inventory position.
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]

    def get(self, request):
        company = get_company_user(request).company
        # low (default): items with a reorder rule at or below it. out: no rule, nothing left.
        # all: both, so one request fills the page's two tabs.
        status = (request.query_params.get("status") or "low").lower()
        if status not in ("low", "out", "all"):
            raise BusinessRuleError("status must be low, out or all.")
        balances = low_stock_rows(company, status=status)
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
            return [IsAuthenticated(), HasCompany(), CanViewWarehouseSurfaces()]
        return [IsAuthenticated(), HasCompany(), CanManageInventory()]

    def get_queryset(self):
        # The system's own in-transit godown is not a person's godown: out of every list, and
        # not reachable for edit or delete either.
        qs = super().get_queryset().filter(is_system=False)
        # MFG-02: a picker passes ?purpose=SALE|COUNT|REORDER|TRANSFER|MFG_ISSUE|MFG_RECEIPT to get only the
        # godowns that make sense there. Without it, a godown at a job worker is still left out of lists,
        # so it can never be offered by accident; detail routes keep reaching it for edit.
        if getattr(self, "action", None) == "list":
            purpose = (self.request.query_params.get("purpose") or "").upper()
            if purpose:
                from .models import WarehouseManager

                kinds = WarehouseManager.SELECTABLE_KINDS.get(purpose)
                if kinds is None:
                    raise BusinessRuleError("Unknown godown purpose.")
                qs = qs.filter(kind__in=kinds)
            else:
                qs = qs.exclude(kind=Warehouse.Kind.JOB_WORKER)
        return qs

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
        # B8-030: re-assert the invariant after the write, regardless of which
        # field changed — a PUT that flips is_default or is_active in a way that
        # leaves zero (or >1) active default godowns is otherwise not caught.
        active_defaults = Warehouse.objects.filter(
            company=self.company, is_active=True, is_default=True
        )
        if not active_defaults.exists():
            fallback = (
                Warehouse.objects.filter(company=self.company, is_active=True)
                .order_by("id")
                .first()
            )
            if fallback is not None:
                Warehouse.objects.filter(pk=fallback.pk).update(is_default=True)
        elif active_defaults.count() > 1:
            keep = active_defaults.order_by("id").first()
            active_defaults.exclude(pk=keep.pk).update(is_default=False)

    def perform_destroy(self, instance):
        from .item_stock import assert_can_delete_warehouse

        assert_can_delete_warehouse(instance)
        super().perform_destroy(instance)


class StockTransferViewSet(IdempotentCreateMixin, CompanyScopedViewSet):
    queryset = StockTransfer.objects.select_related("from_warehouse", "to_warehouse").prefetch_related("lines")
    serializer_class = StockTransferSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def get_queryset(self):
        # INV-IDR-07: the list can be narrowed by status, godown, search and "open shortage".
        qs = super().get_queryset()
        params = self.request.query_params
        if status_ := params.get("status"):
            qs = qs.filter(status__in=[x.strip().upper() for x in status_.split(",") if x.strip()])
        if wh := params.get("warehouse"):
            if str(wh).isdigit():
                qs = qs.filter(Q(from_warehouse_id=wh) | Q(to_warehouse_id=wh))
        if q := (params.get("q") or "").strip():
            qs = qs.filter(
                Q(number__icontains=q) | Q(notes__icontains=q) | Q(lines__product__name__icontains=q)
            ).distinct()
        if params.get("open_shortage") in ("1", "true"):
            qs = qs.filter(
                status=StockTransfer.Status.COMPLETED, lines__shortage_qty__gt=0, lines__shortage_resolution="",
            ).distinct()
        return qs

    @action(detail=True, methods=["post"], url_path="resolve-shortage")
    def resolve_shortage(self, request, pk=None):
        """Settle quantities found missing at receive: write off or return to the source godown."""
        cu = get_company_user(request)
        if cu is None or cu.role not in ("OWNER", "MANAGER"):
            raise PermissionDenied("Only an owner or manager can settle a transfer shortage.")

        def build():
            transfer, applied, pending = StockTransferService.resolve_shortage(
                self.get_object(), request.user, request.data.get("resolutions"),
            )
            data = self.get_serializer(transfer).data
            data["resolved"] = applied
            data["pending_approval"] = pending
            return Response(data, status=202 if pending and not applied else 200)

        return wrap_idempotent(
            request=request, company=self.company, scope="stock_transfer_shortage", build=build,
        )

    def create(self, request, *args, **kwargs):
        # INV-IDR-01: a double click or a retry after a lost response is one draft, not two.
        return self._idempotent(
            request,
            "stock_transfer_create",
            lambda: super(StockTransferViewSet, self).create(request, *args, **kwargs),
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Dispatch: stock leaves the source and sits in transit."""
        def build():
            transfer, warnings = StockTransferService.dispatch(self.get_object(), request.user)
            data = self.get_serializer(transfer).data
            if warnings:
                data["warnings"] = warnings
            return Response(data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="stock_transfer_complete",
            build=build,
        )

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        """Land in-transit stock at the destination godown."""
        def build():
            transfer, warnings = StockTransferService.receive(
                self.get_object(), request.user, receipts=request.data.get("receipts"),
            )
            data = self.get_serializer(transfer).data
            if warnings:
                data["warnings"] = warnings
            return Response(data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="stock_transfer_receive",
            build=build,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        transfer = self.get_object()
        # INV-WP-05: undoing a transfer that has already landed can take stock away from a godown
        # that may have sold it since, so it is an owner/manager decision. Cancelling a draft or a
        # transfer still in transit is open to anyone who can run transfers.
        if transfer.status == StockTransfer.Status.COMPLETED:
            cu = get_company_user(request)
            if cu is None or cu.role not in ("OWNER", "MANAGER"):
                raise PermissionDenied("Only an owner or manager can cancel a transfer that has been received.")
        return Response(self.get_serializer(StockTransferService.cancel(transfer, request.user)).data)


class BatchLotViewSet(CompanyScopedViewSet):
    queryset = BatchLot.objects.select_related("product")
    serializer_class = BatchLotSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def get_permissions(self):
        # BB-100 F7: whoever sells or buys picks a lot on the line, so reading lots follows the
        # stock-view rule (a lot carries no cost). Creating or changing lots stays inventory-only.
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewInventorySurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if product := self.request.query_params.get("product"):
            qs = qs.filter(product_id=product)
        # INV-WP-05: lots that actually have stock in one godown (the source of a transfer).
        if warehouse := self.request.query_params.get("warehouse"):
            stocked = StockBalance.objects.filter(
                company=self.company, warehouse_id=warehouse, on_hand__gt=0, batch__isnull=False,
            ).values("batch_id")
            qs = qs.filter(pk__in=stocked)
        return qs


def _sale_movement_for_serial(company, serial):
    """Resolve the SALE StockMovement that issued ``serial`` (invoice or challan).

    Serials live on document lines, not on ``StockMovement`` (CR-048).
    CR-099 / CR-142: prefer COMPLETED/RETURNED invoices that actually have SALE
    moves (draft shadows must not win). When one invoice has multiple SALE moves
    for the same SKU, map the serial's index on the *line* onto the peel that
    consumed that unit — not always moves[0] or product-wide first move.
    """
    from sales.cogs_service import CogsService
    from sales.models import DeliveryChallanItem, SalesInvoice, SalesItem

    def _move_for_serial_index(moves, serials, sn):
        if not moves:
            return None
        try:
            idx = list(serials or []).index(sn)
        except ValueError:
            return moves[0]
        cursor = 0
        for move in moves:
            q = int(abs(Decimal(str(move.quantity or 0))))
            if q <= 0:
                continue
            if idx < cursor + q:
                return move
            cursor += q
        return moves[-1]

    def _line_scoped_moves(invoice, item):
        """Map serial index onto SALE moves for this invoice+SKU, offset by
        earlier lines of the same product so multi-line peels stay aligned."""
        moves = CogsService.invoice_sale_moves(invoice, product=serial.product)
        if not moves:
            return []
        prior_qty = Decimal("0")
        for sib in invoice.items.filter(product_id=item.product_id).order_by("id"):
            if sib.pk == item.pk:
                break
            prior_qty += abs(Decimal(str(sib.quantity or 0)))
        cursor = Decimal("0")
        scoped = []
        for move in moves:
            q = abs(Decimal(str(move.quantity or 0)))
            if q <= 0:
                continue
            # Keep moves that overlap this line's quantity window.
            move_end = cursor + q
            if move_end > prior_qty and cursor < prior_qty + abs(Decimal(str(item.quantity or 0))):
                scoped.append(move)
            cursor = move_end
        return scoped or moves

    sn = serial.serial_number
    candidates = []
    for item in (
        SalesItem.objects.filter(product=serial.product, invoice__company=company)
        .select_related("invoice")
        .order_by("-invoice_id", "-id")[:200]
    ):
        if sn not in (item.serial_numbers or []):
            continue
        inv = item.invoice
        moves = _line_scoped_moves(inv, item)
        if not moves:
            continue
        posted = inv.status in (
            SalesInvoice.Status.COMPLETED,
            SalesInvoice.Status.RETURNED,
        )
        candidates.append((posted, inv.pk, item, moves))

    # Prefer posted invoices with SALE moves; among those, newest invoice wins.
    candidates.sort(key=lambda row: (not row[0], -row[1], -row[2].pk))
    for _posted, _inv_id, item, moves in candidates:
        hit = _move_for_serial_index(moves, item.serial_numbers, sn)
        if hit is not None:
            return hit

    for item in (
        DeliveryChallanItem.objects.filter(
            product=serial.product,
            challan__company=company,
            challan__stock_posted=True,
        )
        .select_related("challan")
        .order_by("-challan_id", "-id")[:200]
    ):
        if sn not in (item.serial_numbers or []):
            continue
        moves = list(
            StockMovement.objects.filter(
                company=company,
                product=serial.product,
                movement_type=MovementType.SALE,
                reference_type="delivery_challan",
                reference_id=str(item.challan_id),
            )
            .order_by("id")
        )
        hit = _move_for_serial_index(moves, item.serial_numbers, sn)
        if hit is not None:
            return hit
    return None


class CanReadSerials(BasePermission):
    """Counter lookup is a read. Stock writes stay on CanManageInventory."""

    message = "Serial lookup requires sales or inventory permission."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or not cu.is_active:
            return False
        return bool(cu.role == "OWNER" or cu.can_create_sales or cu.can_manage_inventory)


class SerialNumberViewSet(CompanyScopedViewSet):
    queryset = SerialNumber.objects.select_related("product", "warehouse")
    serializer_class = SerialNumberSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    def get_permissions(self):
        from billing.permissions import SubscriptionWritesAllowed

        if self.action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanReadSerials(), SubscriptionWritesAllowed()]
        return [IsAuthenticated(), HasCompany(), CanManageInventory(), SubscriptionWritesAllowed()]

    def get_queryset(self):
        qs = super().get_queryset()
        if status := self.request.query_params.get("status"):
            qs = qs.filter(status=status)
        serial = (self.request.query_params.get("serial_number") or "").strip()
        if serial:
            qs = qs.filter(serial_number=serial)
        # INV-WP-02: typed search on the Serial numbers page (the exact match above is the counter lookup).
        if q := (self.request.query_params.get("q") or "").strip():
            qs = qs.filter(serial_number__icontains=q)
        return qs

    @action(detail=True, methods=["get"])
    def document(self, request, pk=None):
        """The sale (invoice or challan) a SOLD unit went out on, so the Serials page can link to it."""
        from sales.models import DeliveryChallan, SalesInvoice

        serial = self.get_object()
        if serial.status != SerialNumber.Status.SOLD:
            return Response({"document": None})
        move = _sale_movement_for_serial(self.company, serial)
        if move is None or not move.reference_id:
            return Response({"document": None})
        try:
            ref_id = int(move.reference_id)
        except (TypeError, ValueError):
            return Response({"document": None})
        if move.reference_type == "sales_invoice":
            doc = SalesInvoice.objects.filter(company=self.company, pk=ref_id).first()
            kind, path = "invoice", f"/sales/invoices/{ref_id}"
        elif move.reference_type == "delivery_challan":
            doc = DeliveryChallan.objects.filter(company=self.company, pk=ref_id).first()
            kind, path = "challan", f"/sales/delivery-challans/{ref_id}"
        else:
            return Response({"document": None})
        if doc is None:
            return Response({"document": None})
        return Response({"document": {"type": kind, "id": ref_id, "number": doc.number or "", "path": path}})

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        # INV-IDR-03: a repeated click or a retry after a lost response is one transition.
        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="serial_transition",
            build=lambda: self._transition(request, pk),
        )

    @transaction.atomic
    def _transition(self, request, pk):
        # The row is locked so two requests cannot both pass the status check below and each post
        # a stock movement for the same unit.
        self.get_object()
        serial = SerialNumber.objects.select_for_update(of=("self",)).select_related("product", "warehouse").get(
            pk=pk, company=self.company,
        )
        target = request.data.get("status")
        allowed = {
            SerialNumber.Status.AVAILABLE: {SerialNumber.Status.SCRAPPED},
            # API still accepts RETURNED; sellable path lands on AVAILABLE (CR-049).
            SerialNumber.Status.SOLD: {SerialNumber.Status.RETURNED, SerialNumber.Status.AVAILABLE},
            SerialNumber.Status.RETURNED: {SerialNumber.Status.SCRAPPED},
            SerialNumber.Status.SCRAPPED: set(),
        }
        if target not in allowed.get(serial.status, set()):
            return Response({"detail": "Invalid serial status transition."}, status=status.HTTP_400_BAD_REQUEST)
        from_status = serial.status
        manual_reason = ""
        if from_status == SerialNumber.Status.SOLD:
            # INV-IDR-03: a sold unit comes back through a sales return (credit note), which restores
            # stock, the receivable and GST together. Putting it back on the shelf here moves stock
            # only, so it is an owner's repair, with a written reason.
            cu = get_company_user(request)
            if cu is None or cu.role != "OWNER":
                raise PermissionDenied(
                    "A sold unit comes back through a sales return. Only an owner can put it back in stock without one."
                )
            manual_reason = str(request.data.get("reason") or "").strip()
            if not manual_reason:
                raise BusinessRuleError(
                    "Give the reason this unit is being put back in stock without a sales return.",
                    code="sales_return_required",
                )
            if request.data.get("confirm_no_document") is not True:
                raise BusinessRuleError(
                    "Create a sales return for the invoice instead. To put the unit back in stock without one, "
                    "confirm that no sales return is needed.",
                    code="sales_return_required",
                )
        from inventory.models import Warehouse

        warehouse_id = request.data.get("warehouse", serial.warehouse_id)
        if warehouse_id:
            if not Warehouse.objects.filter(company=self.company, pk=warehouse_id, is_system=False).exists():
                return Response({"detail": "Warehouse does not belong to this company."}, status=status.HTTP_400_BAD_REQUEST)
        warehouse = serial.warehouse
        if warehouse_id:
            warehouse = Warehouse.objects.filter(company=self.company, pk=warehouse_id).first() or warehouse

        if target in (
            SerialNumber.Status.RETURNED,
            SerialNumber.Status.AVAILABLE,
        ) and from_status == SerialNumber.Status.SOLD:
            # CR-048 / CR-049: match document sales-return semantics —
            # cost from linked SALE (not nonexistent StockMovement.serial_numbers),
            # post SALES_RETURN, restore FIFO peels, mark AVAILABLE for resale.
            sale_move = _sale_movement_for_serial(self.company, serial)
            if sale_move is not None:
                sale_cost = Decimal(str(sale_move.unit_cost or 0))
                restore_wh = sale_move.warehouse or warehouse
            else:
                sale_cost = InventoryValuationService.unit_cost(
                    self.company, serial.product, warehouse
                )
                restore_wh = warehouse
            inbound = InventoryService.post_movement(
                company=self.company,
                warehouse=restore_wh,
                product=serial.product,
                batch=getattr(sale_move, "batch", None) if sale_move else None,
                quantity=Decimal("1"),
                unit_cost=sale_cost,
                movement_type=MovementType.SALES_RETURN,
                reference_type="serial_manual_return",
                reference_id=serial.pk,
                reason=f"Serial {serial.serial_number} returned without a sales return: {manual_reason}",
                user=request.user,
            )
            if sale_move is not None:
                InventoryService.restore_fifo_peels(sale_move, inbound)
            target = SerialNumber.Status.AVAILABLE
            warehouse = restore_wh
            warehouse_id = restore_wh.id if restore_wh is not None else warehouse_id

        if target == SerialNumber.Status.SCRAPPED and from_status in (
            SerialNumber.Status.AVAILABLE,
            SerialNumber.Status.RETURNED,
        ):
            on_hand = InventoryService.available_quantity(
                self.company, serial.product, warehouse
            )
            # CR-057: AVAILABLE scrap requires on_hand >= 1 (refuse desync hit).
            if from_status == SerialNumber.Status.AVAILABLE and on_hand < 1:
                return Response(
                    {"detail": "Cannot scrap: no on-hand quantity for this product."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if on_hand >= 1:
                from .stock_loss import SOURCE_SERIAL_SCRAP, StockLoss, post_stock_loss

                result = post_stock_loss(
                    self.company,
                    request.user,
                    StockLoss(
                        product=serial.product,
                        quantity=Decimal("-1"),
                        reason=f"Serial {serial.serial_number} scrapped",
                        source=SOURCE_SERIAL_SCRAP,
                        warehouse=warehouse,
                        reference_id=serial.pk,
                        check_period=False,
                    ),
                    approval_id=request.data.get("approval_id"),
                )
                if result.pending:
                    # Nothing has moved and the serial keeps its status until the owner decides.
                    return Response({"status": "PENDING", "approval_id": result.approval.pk}, status=202)
        serial.status = target
        serial.warehouse_id = warehouse_id
        serial.updated_by = request.user
        serial.save(update_fields=["status", "warehouse", "updated_by", "updated_at"])
        AuditService.log(
            company=self.company, user=request.user, action="UPDATE",
            entity_type="SerialNumber", entity_id=serial.pk,
            description=(
                f"Serial {serial.serial_number}: {from_status} to {serial.status}"
                + (f" without a sales return. Reason: {manual_reason}" if manual_reason else "")
            ),
        )
        return Response(self.get_serializer(serial).data)


class ExpiryAlertsView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), HasCompany(), CanManageInventory()]
        return [IsAuthenticated(), HasCompany(), CanViewInventorySurfaces()]

    def get(self, request):
        # B8-005: read-only. Recording bands + sending customer emails moved to
        # the daily record_expiry_bands_task (a GET must not have side effects).
        company = get_company_user(request).company
        try:
            days = int(request.query_params.get("days", 30))
            warehouse_raw = request.query_params.get("warehouse")
            warehouse_id = int(warehouse_raw) if warehouse_raw not in (None, "") else None
        except (TypeError, ValueError):
            raise BusinessRuleError("days and warehouse must be whole numbers.") from None
        days = max(0, min(days, 3650))
        from .item_stock import expiry_horizon_rows

        rows = expiry_horizon_rows(company, days=days, warehouse_id=warehouse_id)
        if not _can_see_costs(request):
            for row in rows:
                row["unit_cost"] = None
                row["value"] = None
        return Response({"count": len(rows), "items": rows})

    def post(self, request):
        # INV-IDR-06: a double click, or a retry after a lost response, writes the lot off once.
        company = get_company_user(request).company
        return wrap_idempotent(
            request=request,
            company=company,
            scope="expiry_write_off",
            build=lambda: self._write_off(request),
        )

    def _write_off(self, request):
        """Write off remaining qty of an expired/near-expiry lot as ADJUSTMENT / EXPIRED."""
        from decimal import InvalidOperation

        from django.utils import timezone as _tz
        from django.utils.dateparse import parse_date

        from .item_stock import remaining_qty

        company = get_company_user(request).company
        product = get_object_or_404(Product, pk=request.data.get("product"), company=company)
        warehouse = Warehouse.objects.filter(pk=request.data.get("warehouse"), company=company, is_system=False).first()
        if warehouse is None:
            raise BusinessRuleError("Godown is required for expiry write-off.")
        batch = BatchLot.objects.filter(pk=request.data.get("batch"), company=company, product=product).first()
        if batch is None:
            raise BusinessRuleError("Invalid batch for this product.")
        try:
            qty = Decimal(str(request.data.get("quantity") or 0))
        except InvalidOperation:
            raise BusinessRuleError("Enter the write-off quantity as a number.") from None
        if not qty.is_finite() or qty <= 0:
            raise BusinessRuleError("Write-off quantity must be greater than zero.")
        movement_date = None
        raw_date = request.data.get("movement_date")
        if raw_date not in (None, ""):
            movement_date = parse_date(str(raw_date))
            if movement_date is None:
                raise BusinessRuleError("Write-off date must be a date (YYYY-MM-DD).")
            if movement_date > _tz.localdate():
                raise BusinessRuleError("Write-off date cannot be in the future.")
        reason = str(request.data.get("reason") or "EXPIRED").upper()
        if reason not in ("EXPIRED", "DAMAGED"):
            raise BusinessRuleError("Reason must be EXPIRED or DAMAGED.")
        # B8-013 / INV-IDR-02: period gate, approval (when the company asks for it on this path),
        # movement, journal and audit go through the same service as a manual adjustment.
        from .stock_loss import SOURCE_EXPIRY, StockLoss, post_stock_loss

        with transaction.atomic():
            # Lock the lot's balance first, then check what is left: two people writing off the same
            # lot at once must not both pass the check (INV-IDR-14).
            list(StockBalance.objects.select_for_update().filter(
                company=company, product=product, warehouse=warehouse, batch=batch,
            ))
            on_hand = remaining_qty(company, product, warehouse=warehouse, batch=batch)
            available = InventoryService.available_quantity(company, product, warehouse, batch)
            if qty > available:
                raise BusinessRuleError(
                    f"Cannot write off {qty} — only {available} available on this lot at this godown "
                    f"({on_hand} on hand)."
                )
            result = post_stock_loss(
                company,
                request.user,
                StockLoss(
                    product=product,
                    quantity=-qty,
                    reason=reason,
                    source=SOURCE_EXPIRY,
                    warehouse=warehouse,
                    batch=batch,
                    movement_date=movement_date,
                    skip_negative_check=True,
                    audit_text=f"Write-off ({reason.lower()}): {qty} of {product.name}, lot {batch.batch_no}",
                ),
                approval_id=request.data.get("approval_id"),
            )
        if result.pending:
            return Response({"status": "PENDING", "approval_id": result.approval.pk}, status=202)
        data = StockMovementSerializer(result.movement).data
        data["status"] = "APPLIED"
        return Response(data, status=status.HTTP_201_CREATED)


def _inventory_books_comparison(company, rows, as_of):
    """Stock value from the valuation, the balance of GL 1400, and the gap between them."""
    from decimal import Decimal

    from django.db.models import Sum
    from django.utils.dateparse import parse_date

    from accounting.models import JournalEntry, JournalLine
    from core.services.feature_flags import flag_enabled

    lines = JournalLine.objects.filter(
        company=company,
        account__code="1400",
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
    )
    if as_of:
        day = parse_date(str(as_of))
        if day:
            lines = lines.filter(entry__entry_date__lte=day)
    agg = lines.aggregate(d=Sum("debit"), c=Sum("credit"))
    in_books = (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))
    stock_value = sum((Decimal(str(r.get("value") or 0)) for r in rows), Decimal("0"))
    return {
        "stock_value": stock_value.quantize(Decimal("0.01")),
        "inventory_in_books": in_books.quantize(Decimal("0.01")),
        "books_variance": (stock_value - in_books).quantize(Decimal("0.01")),
        "stock_writes_posted": flag_enabled(company, "ACCOUNTING_POST_STOCK_ADJUSTMENTS"),
    }


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
        used_basis = basis if basis in ("purchase", "selling", "mrp") else "cost"
        payload = {
            "method": request.query_params.get("method") or company.inventory_valuation_method,
            "basis": used_basis,
            "as_of": request.query_params.get("as_of") or None,
            "items": rows,
        }
        # Stock value at cost for the whole company is what the books' Inventory account (1400)
        # should hold. Show the two side by side so a difference is seen, not discovered (INV-WP-16).
        if used_basis == "cost" and warehouse is None and company.accounting_enabled:
            payload.update(_inventory_books_comparison(company, rows, request.query_params.get("as_of")))
        return Response(payload)


class WarehouseReorderLevelViewSet(CompanyScopedViewSet):
    queryset = WarehouseReorderLevel.objects.select_related("warehouse", "product")
    serializer_class = WarehouseReorderLevelSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]


class StockCountSessionViewSet(CompanyScopedViewSet):
    queryset = StockCountSession.objects.select_related("warehouse").prefetch_related("lines__product", "lines__batch")
    serializer_class = StockCountSessionSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]

    @action(detail=True, methods=["get"])
    def counter(self, request, pk=None):
        """Count screen. A blind session omits the expected quantity."""
        session = self.get_object()
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=["get"])
    def review(self, request, pk=None):
        """Review screen. Variance is visible even when the session is blind."""
        session = self.get_object()
        serializer = self.get_serializer(session)
        serializer.context["reveal_count"] = True
        return Response(serializer.data)

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
                if session.lines.filter(counted_qty__isnull=True, skipped=False).exists():
                    raise BusinessRuleError("Save all counted quantities, or skip the lines you are not counting, before posting.")
                if not session.lines.filter(counted_qty__isnull=False, skipped=False).exists():
                    raise BusinessRuleError("Count at least one item before posting.")
                # CR-052 / CR-040: same period gate as manual adjustments; evaluate counted_on if set.
                from django.utils import timezone as _tz

                from reporting.gst_periods import assert_period_allows_money_amend

                count_date = session.counted_on or _tz.localdate()
                assert_period_allows_money_amend(session.company, count_date)
                from .item_stock import remaining_qty

                lines = [
                    line for line in session.lines.select_related("product", "batch") if not line.skipped
                ]
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
                            "counted_at": line.counted_at.isoformat() if line.counted_at else None,
                        })
                # INV-IDR-04: each drifted line gets its own answer. Older clients send one answer for all.
                from .count_drift import KEEP_LOCAL, KEEP_SERVER, parse_resolutions, variance_for

                per_line, default_choice = parse_resolutions(request.data)
                if any(c["line_id"] not in per_line and not default_choice for c in conflicts):
                    raise StockCountConflict(conflicts)
                # INV-IDR-02: work out which lines will move stock first, so the recheck rule and the
                # approval rule are judged on the whole count before anything is written.
                planned = []
                for line in lines:
                    if line.counted_qty is None:
                        continue
                    current = current_by_line[line.pk]
                    drifted = current != line.system_qty
                    choice = (per_line.get(line.pk) or default_choice) if drifted else KEEP_LOCAL
                    # CR-056: KEEP_SERVER skips adjustment for drifted lines (abandons
                    # the physical count for those SKUs) while still marking POSTED.
                    if choice == KEEP_SERVER:
                        line.drift_skipped = True
                        line.save(update_fields=["drift_skipped"])
                        continue
                    planned.append((line, variance_for(session, line, current, choice), current))
                from .stock_loss import SOURCE_COUNT, StockLoss, gate_count_post, post_stock_loss

                raw_ids = request.data.get("rechecked_line_ids")
                try:
                    rechecked_ids = {int(x) for x in raw_ids} if isinstance(raw_ids, (list, tuple)) else set()
                except (TypeError, ValueError):
                    raise BusinessRuleError("rechecked_line_ids must be a list of line ids.") from None
                pending = gate_count_post(
                    session.company, request.user, session,
                    [row for row in planned if row[1] != 0], rechecked_ids,
                    approval_id=request.data.get("approval_id"),
                )
                if pending is not None:
                    # The count stays COUNTED; the owner decides, then posting again goes through.
                    return Response({"status": "PENDING", "approval_id": pending.pk}, status=202)
                for line, variance, _current in planned:
                    if variance == 0:
                        line.held_for_review = False
                        line.save(update_fields=["held_for_review"])
                        continue
                    from decimal import Decimal

                    from django.conf import settings

                    limit = Decimal(str(getattr(settings, "STOCK_COUNT_AUTO_POST_QTY", "5")))
                    # held_for_review flags a large variance for follow-up audit
                    # attention — it must not skip the adjustment itself, or the
                    # physical count silently never reaches StockBalance and the
                    # session still reports POSTED as if it had.
                    line.held_for_review = abs(variance) > limit
                    line.save(update_fields=["held_for_review"])
                    post_stock_loss(
                        session.company,
                        request.user,
                        StockLoss(
                            product=line.product,
                            quantity=variance,
                            reason="STOCK_COUNT",
                            source=SOURCE_COUNT,
                            warehouse=session.warehouse,
                            batch=line.batch,
                            movement_date=session.counted_on,
                            reference_id=session.pk,
                            check_period=False,  # gated once for the whole count above
                        ),
                        preapproved=True,
                    )
                session.status = StockCountSession.Status.POSTED
                session.posted_at = timezone.now()
                session.save(update_fields=["status", "posted_at"])
                AuditService.log(
                    company=session.company, user=request.user, action="POST",
                    entity_type="StockCountSession", entity_id=session.pk,
                    description=f"Stock count #{session.pk} posted for {session.warehouse.name}",
                    metadata={
                        "resolve_conflicts": default_choice or None,
                        "resolutions": {str(k): v for k, v in per_line.items()} or None,
                        # Lines the counter confirmed with "count equals system" instead of counting.
                        "filled_from_system": sum(1 for line in lines if line.filled_from_system) or None,
                    },
                )
            # The queryset prefetched the lines before the loop above changed them; read them again
            # so the response shows held_for_review / drift_skipped as they are now.
            session = self.get_queryset().get(pk=session.pk)
            return Response(self.get_serializer(session).data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="stock_count_post",
            build=_run,
        )

    @action(detail=True, methods=["post"], url_path="add-line")
    def add_line(self, request, pk=None):
        """Count an item that is not on the sheet (found stock the system does not know about)."""
        from .serializers import _count_line_system_qty, refresh_count_status

        session = self.get_object()
        if session.status not in (StockCountSession.Status.DRAFT, StockCountSession.Status.COUNTED):
            raise BusinessRuleError("Only a draft or counted session can be edited.")
        product = get_object_or_404(Product, pk=request.data.get("product"), company=session.company)
        batch = None
        if request.data.get("batch") not in (None, ""):
            batch = BatchLot.objects.filter(
                pk=request.data.get("batch"), company=session.company, product=product
            ).first()
            if batch is None:
                raise BusinessRuleError("Invalid batch for this product.")
        elif product.track_batch:
            raise BusinessRuleError("Choose a batch for a batch-tracked item.")
        try:
            counted = Decimal(str(request.data.get("counted_qty")))
        except (ArithmeticError, ValueError):
            raise BusinessRuleError("Enter the counted quantity.") from None
        if counted < 0:
            raise BusinessRuleError("Counted quantity cannot be negative.")
        with transaction.atomic():
            line, created = StockCountLine.objects.get_or_create(
                session=session, product=product, batch=batch,
                defaults={
                    "company": session.company,
                    "system_qty": _count_line_system_qty(session, product, batch),
                    "counted_qty": counted,
                    "snapshot_at": timezone.now(),
                    "counted_at": timezone.now(),
                },
            )
            if not created:
                line.counted_qty = counted
                line.skipped = False
                line.counted_at = timezone.now()
                line.filled_from_system = False
                line.version += 1
                line.save(update_fields=["counted_qty", "skipped", "counted_at", "filled_from_system", "version"])
            refresh_count_status(session)
            what = "Counted" if created else "Recounted"
            AuditService.log(
                company=session.company, user=request.user, action="UPDATE",
                entity_type="StockCountSession", entity_id=session.pk,
                description=f"{what} {product.name}: {counted}",
            )
        session = self.get_queryset().get(pk=session.pk)
        return Response(self.get_serializer(session).data, status=status.HTTP_201_CREATED if created else 200)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        self.get_object()  # tenancy and permission checks
        # INV-IDR-04: the row is locked, so a cancel cannot land on a count that is being posted.
        with transaction.atomic():
            session = get_object_or_404(self.get_queryset().select_for_update(), pk=pk)
            if session.status == StockCountSession.Status.POSTED:
                raise BusinessRuleError("A posted count cannot be cancelled.")
            if session.status == StockCountSession.Status.CANCELLED:
                return Response(self.get_serializer(session).data)
            session.status = StockCountSession.Status.CANCELLED
            session.save(update_fields=["status"])
            AuditService.log(
                company=session.company, user=request.user, action="CANCEL",
                entity_type="StockCountSession", entity_id=session.pk,
                description=f"Stock count #{session.pk} cancelled",
            )
        return Response(self.get_serializer(session).data)
