from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.permissions import (
    CanCreatePurchases,
    CanCreateSales,
    CanManageInventory,
    CanViewMastersCatalog,
    HasCompany,
    IsOwner,
)
from core.services.gstin_verify import apply_verification, get_gstin_provider
from core.viewsets import CompanyScopedViewSet

from .models import Brand, Category, Customer, ExpenseCategory, PaymentMode, PriceList, Product, Supplier, TaxRate, Unit
def _soft_destroy(instance, user):
    from django.utils import timezone

    instance.is_deleted = True
    instance.deleted_at = timezone.now()
    instance.updated_by = user
    instance.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])


from .serializers import (
    BrandSerializer,
    CategorySerializer,
    CustomerSerializer,
    ExpenseCategorySerializer,
    PaymentModeSerializer,
    ProductSerializer,
    PriceListSerializer,
    SupplierSerializer,
    TaxRateSerializer,
    UnitSerializer,
)

# BB-000195: short TTL list cache for hot masters reads.
_MASTERS_LIST_TTL = 60

# BB-000297/Wave 12B: masters mutation is Owner-only; list/retrieve stay HasCompany.
_MUTATE_ACTIONS = ("create", "update", "partial_update", "destroy")


class _CachedMastersListMixin:
    list_cache_kind = ""

    def _bust_list_cache(self):
        kind = getattr(self, "list_cache_kind", "") or ""
        if kind:
            cache.delete(f"masters:{kind}:{self.company.pk}")

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self._bust_list_cache()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._bust_list_cache()

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        self._bust_list_cache()


def _barcode_svg(code: str) -> str:
    try:
        from reportlab.graphics.barcode import createBarcodeDrawing
        from reportlab.graphics import renderSVG

        drawing = createBarcodeDrawing("Code128", value=code, barHeight=50, humanReadable=True)
        return renderSVG.drawToString(drawing)
    except Exception as exc:
        raise BusinessRuleError("Could not render barcode image.") from exc


class CategoryViewSet(CompanyScopedViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]


class BrandViewSet(CompanyScopedViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]


class UnitViewSet(_CachedMastersListMixin, CompanyScopedViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
    list_cache_kind = "units"

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    def list(self, request, *args, **kwargs):
        key = f"masters:units:{self.company.pk}"
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, _MASTERS_LIST_TTL)
        return response


class TaxRateViewSet(_CachedMastersListMixin, CompanyScopedViewSet):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    list_cache_kind = "tax_rates"

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    def list(self, request, *args, **kwargs):
        key = f"masters:tax_rates:{self.company.pk}"
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, _MASTERS_LIST_TTL)
        return response


class PaymentModeViewSet(CompanyScopedViewSet):
    queryset = PaymentMode.objects.all()
    serializer_class = PaymentModeSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]


class ExpenseCategoryViewSet(CompanyScopedViewSet):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]


class CustomerViewSet(CompanyScopedViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in (*_MUTATE_ACTIONS, "pos_walk_in"):
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        if getattr(self, "action", None) in ("verify_gstin", "set_pos_walk_in"):
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse party masters.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        q = self.request.query_params.get("search") or self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q))
        if self.request.query_params.get("is_pos_walk_in") in ("1", "true", "True"):
            qs = qs.filter(is_pos_walk_in=True)
        sort = (self.request.query_params.get("sort") or self.request.query_params.get("ordering") or "name").lower()
        if sort in ("recent", "recently_active", "-updated_at"):
            qs = qs.order_by("-updated_at", "name")
        elif sort in ("balance", "-balance"):
            from django.db.models import Case, DecimalField, Value, When

            from ledgers.services import LedgerService

            outstanding = LedgerService.bulk_customer_outstanding(self.company)
            whens = [
                When(pk=pk, then=Value(amt, output_field=DecimalField(max_digits=14, decimal_places=2)))
                for pk, amt in outstanding.items()
            ]
            qs = qs.annotate(
                _bal=Case(*whens, default=Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)))
            ).order_by("-_bal", "name")
        else:
            qs = qs.order_by("name")
        return qs

    @action(detail=False, methods=["post"], url_path="pos-walk-in")
    def pos_walk_in(self, request):
        """Get or create the single walk-in party. Cashiers do not set the flag themselves."""
        from django.db import IntegrityError

        name = str(request.data.get("name") or "Walk-in").strip()[:255] or "Walk-in"
        with transaction.atomic():
            row = (
                Customer.objects.select_for_update()
                .filter(company=self.company, is_pos_walk_in=True)
                .first()
            )
            if row is not None:
                return Response(self.get_serializer(row).data)
            try:
                row = Customer.objects.create(
                    company=self.company,
                    name=name,
                    status=Customer.Status.ACTIVE,
                    is_pos_walk_in=True,
                    created_by=request.user,
                    updated_by=request.user,
                )
            except IntegrityError:
                row = Customer.objects.filter(company=self.company, is_pos_walk_in=True).first()
                if row is None:
                    raise
        return Response(self.get_serializer(row).data, status=201)

    @action(detail=False, methods=["post"], url_path="set-pos-walk-in", permission_classes=[IsAuthenticated, HasCompany, IsOwner])
    def set_pos_walk_in(self, request):
        from decimal import Decimal

        from core.services.audit import AuditService

        target_id = request.data.get("customer")
        with transaction.atomic():
            target = (
                Customer.objects.select_for_update()
                .filter(company=self.company, pk=target_id)
                .first()
            )
            if target is None:
                raise BusinessRuleError("Choose a customer in this company.")
            if (target.gstin or "").strip() or Decimal(str(target.credit_limit or 0)) > 0:
                raise BusinessRuleError(
                    "The walk-in party cannot have a GSTIN or a credit limit.",
                    code="pos_walk_in_target",
                )
            # Lock the current walk-in rows first so two moves cannot race on the unique flag.
            list(Customer.objects.select_for_update().filter(company=self.company, is_pos_walk_in=True))
            Customer.objects.filter(company=self.company, is_pos_walk_in=True).exclude(pk=target.pk).update(
                is_pos_walk_in=False,
            )
            if not target.is_pos_walk_in:
                target.is_pos_walk_in = True
                target.updated_by = request.user
                target.save(update_fields=["is_pos_walk_in", "updated_by", "updated_at"])
        AuditService.log(
            company=self.company,
            user=request.user,
            action="UPDATE",
            entity_type="Customer",
            entity_id=str(target.pk),
            description=f"POS walk-in party set to {target.name}",
        )
        return Response(self.get_serializer(target).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.get("partial", False)
        if not partial:
            instance = self.get_object()
            try:
                sent = int(request.data.get("version"))
            except (TypeError, ValueError):
                sent = None
            if sent != instance.version:
                return Response(
                    {"detail": "stale write", "current": self.get_serializer(instance).data},
                    status=409,
                )
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        """Reload under a row lock and write only the fields in this request.

        A concurrent PATCH of a different field therefore keeps both edits.
        The lock is taken here, after any test barrier around perform_update.
        """
        with transaction.atomic():
            locked = Customer.all_objects.select_for_update().get(
                pk=serializer.instance.pk, company=self.company,
            )
            if not self.kwargs.get("partial", False) and self.request.method == "PUT":
                # The check in update() ran before the lock. Two PUTs carrying version N both pass
                # it, so compare again now that this request owns the row.
                try:
                    sent = int(self.request.data.get("version"))
                except (TypeError, ValueError):
                    sent = None
                if sent != locked.version:
                    from rest_framework.exceptions import APIException

                    class StaleWrite(APIException):
                        status_code = 409
                        default_detail = "stale write"
                        default_code = "stale_write"

                    raise StaleWrite()
            addresses = serializer.validated_data.pop("shipping_addresses", None)
            for key, value in serializer.validated_data.items():
                setattr(locked, key, value)
            locked.version = int(locked.version or 0) + 1
            locked.updated_by = self.request.user
            locked.save()
            serializer.instance = locked
            if addresses is not None:
                serializer._replace_addresses(locked, addresses)
        self._audit("UPDATE", serializer.instance)

    def perform_destroy(self, instance):
        _soft_destroy(instance, self.request.user)
        # a soft delete is still a delete: it must leave the same audit row a hard one did
        self._audit_raw("DELETE", str(instance.pk))

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # BUG-301-style fix: one bulk aggregation for the whole list instead of
        # a per-row LedgerService.customer_outstanding query (N+1).
        if getattr(self, "action", None) == "list":
            from ledgers.services import LedgerService

            context["outstanding_by_id"] = LedgerService.bulk_customer_outstanding(self.company)
            context["credit_exposure_by_id"] = LedgerService.bulk_customer_credit_exposure(self.company)
        return context

    def destroy(self, request, *args, **kwargs):
        """Never hard-delete a referenced customer — deactivate instead (BB-000057)."""
        customer = self.get_object()
        if customer.is_referenced():
            customer.status = Customer.Status.INACTIVE
            customer.updated_by = request.user
            customer.save(update_fields=["status", "updated_by"])
            self._audit("UPDATE", customer)
            return Response(
                {"detail": "Customer is referenced by documents; marked Inactive instead of deleting."},
                status=200,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="verify-gstin")
    def verify_gstin(self, request, pk=None):
        customer = self.get_object()
        if not (customer.gstin or "").strip():
            raise BusinessRuleError("Customer has no GSTIN.")
        result = get_gstin_provider().lookup(customer.gstin)
        apply_verification(customer, result, user=request.user, company=customer.company)
        return Response(self.get_serializer(customer).data)


class SupplierViewSet(CompanyScopedViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer

    def perform_destroy(self, instance):
        from core.exceptions import BusinessRuleError

        # Hard delete used to be stopped by PROTECT foreign keys. A soft delete hides the row from
        # the alive manager, so ledgers and open bills would lose a supplier that still has a balance.
        if instance.is_referenced():
            raise BusinessRuleError(
                f"Cannot delete '{instance.name}' because purchase documents reference it. Mark it Inactive instead."
            )
        _soft_destroy(instance, self.request.user)
        # a soft delete is still a delete: it must leave the same audit row a hard one did
        self._audit_raw("DELETE", str(instance.pk))

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), CanCreatePurchases()]
        if getattr(self, "action", None) == "verify_gstin":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse party masters.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    def get_queryset(self):
        qs = super().get_queryset()
        # F2-033: the Suppliers list filter bar sends status=ACTIVE|INACTIVE.
        status_filter = (self.request.query_params.get("status") or "").upper()
        if status_filter == "ACTIVE":
            qs = qs.filter(is_active=True)
        elif status_filter == "INACTIVE":
            qs = qs.filter(is_active=False)
        q = self.request.query_params.get("search") or self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q))
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if getattr(self, "action", None) == "list":
            from ledgers.services import LedgerService

            context["outstanding_by_id"] = LedgerService.bulk_supplier_outstanding(self.company)
        return context

    def destroy(self, request, *args, **kwargs):
        """Never hard-delete a referenced supplier — deactivate instead (BB-000057)."""
        supplier = self.get_object()
        if supplier.is_referenced():
            supplier.is_active = False
            supplier.updated_by = request.user
            supplier.save(update_fields=["is_active", "updated_by"])
            self._audit("UPDATE", supplier)
            return Response(
                {"detail": "Supplier is referenced by documents; marked inactive instead of deleting."},
                status=200,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="verify-gstin")
    def verify_gstin(self, request, pk=None):
        supplier = self.get_object()
        if not (supplier.gstin or "").strip():
            raise BusinessRuleError("Supplier has no GSTIN.")
        result = get_gstin_provider().lookup(supplier.gstin)
        apply_verification(supplier, result, user=request.user, company=supplier.company)
        return Response(self.get_serializer(supplier).data)


class ProductViewSet(_CachedMastersListMixin, CompanyScopedViewSet):
    queryset = Product.objects.select_related("category", "brand", "unit")
    serializer_class = ProductSerializer
    list_cache_kind = "products"

    def _bust_list_cache(self):
        super()._bust_list_cache()
        cache.delete(f"masters:hsn:{self.company.pk}")
        for variant in ("cost", "nocost"):
            cache.delete(f"masters:products:{self.company.pk}:{variant}")

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), CanManageInventory()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    @action(detail=False, methods=["get"], url_path="pos-catalog")
    def pos_catalog(self, request):
        """Paged POS fields for the offline catalogue, plus ids removed since `updated_after`."""
        from django.utils.dateparse import parse_datetime

        try:
            limit = max(1, min(int(request.query_params.get("limit") or 500), 1000))
        except (TypeError, ValueError):
            limit = 500
        try:
            offset = max(0, int(request.query_params.get("cursor") or 0))
        except (TypeError, ValueError):
            offset = 0
        updated_after = parse_datetime(str(request.query_params.get("updated_after") or ""))
        # Only sellable products go to the till. An inactive item must not be sold offline.
        alive = Product.objects.filter(company=self.company, status=Product.Status.ACTIVE).select_related("unit")
        deleted_ids = []
        if updated_after is not None:
            alive = alive.filter(updated_at__gt=updated_after)
            gone = Product.all_objects.filter(company=self.company, updated_at__gt=updated_after).filter(
                Q(is_deleted=True) | ~Q(status=Product.Status.ACTIVE)
            )
            deleted_ids = list(gone.values_list("id", flat=True)[:1000])
        page = list(alive.order_by("id")[offset:offset + limit + 1])
        more = len(page) > limit
        page = page[:limit]
        results = []
        for product in page:
            unit = getattr(product, "unit", None)
            results.append({
                "id": product.id,
                "name": product.name,
                "sku": product.sku,
                "barcode": product.barcode,
                "price": str(product.selling_price),
                "gst": str(product.gst_rate),
                "hsn": product.hsn_code,
                "unit": getattr(unit, "name", "") or "",
                "track_batch": bool(product.track_batch),
                "track_serial": bool(product.track_serial),
                "product_type": product.product_type,
                "updated_at": product.updated_at,
            })
        return Response({
            "results": results,
            "deleted_ids": deleted_ids,
            "next_cursor": offset + limit if more else None,
        })

    @action(detail=False, methods=["get"], url_path="pos-price-lists")
    def pos_price_lists(self, request):
        """Price lists for the named customers, plus a list named Default."""
        from masters.models import Customer, PriceList

        raw_ids = []
        for part in str(request.query_params.get("customers") or "").split(","):
            if part.strip().isdigit():
                raw_ids.append(int(part))
        customers = list(Customer.objects.filter(company=self.company, pk__in=raw_ids))
        wanted = {row.price_list_id for row in customers if row.price_list_id}
        default = PriceList.objects.filter(
            company=self.company, is_active=True, name__iexact="Default",
        ).first()
        if default is not None:
            wanted.add(default.id)
        lists = []
        for plist in PriceList.objects.filter(company=self.company, pk__in=wanted, is_active=True):
            lists.append({
                "id": plist.id,
                "name": plist.name,
                "items": [
                    {
                        "product": item.product_id,
                        "unit_price": str(item.unit_price),
                        "min_qty": str(item.min_qty),
                        "max_qty": None if item.max_qty is None else str(item.max_qty),
                    }
                    for item in plist.items.all()[:2000]
                ],
            })
        return Response({
            "lists": lists,
            "customers": [{"id": row.id, "price_list": row.price_list_id} for row in customers],
        })

    def get_queryset(self):
        from django.db.models import Exists, OuterRef
        from inventory.models import StockMovement

        qs = super().get_queryset().annotate(
            has_movements=Exists(StockMovement.objects.filter(product_id=OuterRef("pk")))
        )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        q = self.request.query_params.get("search") or self.request.query_params.get("q")
        from masters.custom_fields import active_defs, apply_cf_filters, build_search_q

        defs = active_defs(self.company)
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(sku__icontains=q)
                | Q(barcode__icontains=q)
                | Q(hsn_code__icontains=q)
                | Q(salt__icontains=q)
                | Q(composition__icontains=q)
                | Q(manufacturer__icontains=q)
                | build_search_q(q, defs)
            )
        qs = apply_cf_filters(qs, self.request.query_params, defs)
        return qs

    def list(self, request, *args, **kwargs):
        # Cache the unfiltered catalog; filtered lists stay live.
        if request.query_params:
            return super().list(request, *args, **kwargs)
        # The cached rows carry item cost only for people allowed to see it.
        from core.permissions import can_see_product_cost

        key = f"masters:products:{self.company.pk}:{'cost' if can_see_product_cost(request) else 'nocost'}"
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, _MASTERS_LIST_TTL)
        return response

    def perform_destroy(self, instance):
        from django.db.models import ProtectedError

        from core.exceptions import BusinessRuleError

        if instance.is_referenced():
            raise BusinessRuleError(
                f"Cannot delete '{instance.name}' because it has transaction history. Deactivate it instead."
            )
        try:
            super().perform_destroy(instance)
        except ProtectedError:
            raise BusinessRuleError(
                f"Cannot delete '{instance.name}' because related documents reference it. Deactivate it instead."
            )

    @action(detail=False, methods=["get"], url_path="custom-field-values")
    def custom_field_values(self, request):
        # B8-027: distinct_values_for_keys() scans every product row with
        # custom_fields set, in Python, on every call -- this endpoint is hit
        # on every item-form open. A per-company short-TTL cache (same
        # pattern/TTL as _CachedMastersListMixin) turns a full-catalog scan
        # into a once-per-minute cost instead of once-per-request. Values are
        # dropdown suggestions, not authoritative data, so briefly-stale
        # results after a product edit are an acceptable tradeoff.
        from masters.custom_fields import active_defs, distinct_values_for_keys

        keys = [
            row["key"]
            for row in active_defs(self.company)
            if row.get("type") == "list" and row.get("key")
        ]
        cache_key = f"masters:custom_field_values:{self.company.pk}:{','.join(sorted(keys))}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        data = distinct_values_for_keys(self.company, keys)
        cache.set(cache_key, data, _MASTERS_LIST_TTL)
        return Response(data)

    @action(detail=False, methods=["post"], url_path="generate-barcode")
    def generate_barcode(self, request):
        import secrets

        company = self.company
        for _ in range(20):
            candidate = f"BB{company.id:04d}{secrets.randbelow(10**8):08d}"
            if not Product.objects.filter(company=company, barcode=candidate).exists():
                product_id = request.data.get("product")
                if product_id:
                    product = self.get_queryset().filter(pk=product_id).first()
                    if product is None:
                        raise BusinessRuleError("Product not found.")
                    product.barcode = candidate
                    product.updated_by = request.user
                    product.save(update_fields=["barcode", "updated_by"])
                    self._bust_list_cache()
                    return Response({**self.get_serializer(product).data, "svg": _barcode_svg(candidate)})
                return Response({"barcode": candidate, "svg": _barcode_svg(candidate)})
        raise BusinessRuleError("Could not generate a unique barcode. Retry.")

    @action(detail=False, methods=["get"], url_path="barcode-image")
    def barcode_image(self, request):
        import re

        code = re.sub(r"[^A-Za-z0-9\-_]", "", (request.query_params.get("code") or "").strip())[:64]
        if not code:
            raise BusinessRuleError("code is required")
        return HttpResponse(_barcode_svg(code), content_type="image/svg+xml")

    @action(detail=False, methods=["get"], url_path="hsn-search")
    def hsn_search(self, request):
        from .hsn_catalog import search_hsn

        rows = search_hsn(request.query_params.get("q") or "", kind=request.query_params.get("kind"))
        return Response({"count": len(rows), "items": rows})

    def destroy(self, request, *args, **kwargs):
        """Never hard-delete a referenced product (§4.5) — deactivate instead."""
        from django.db.models import ProtectedError

        product = self.get_object()
        if product.is_referenced():
            product.status = Product.Status.INACTIVE
            product.updated_by = request.user
            product.save(update_fields=["status", "updated_by"])
            self._audit("UPDATE", product)
            self._bust_list_cache()
            return Response(
                {"detail": "Product is referenced by documents; marked Inactive instead of deleting."},
                status=200,
            )
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            product.status = Product.Status.INACTIVE
            product.updated_by = request.user
            product.save(update_fields=["status", "updated_by"])
            self._audit("UPDATE", product)
            self._bust_list_cache()
            return Response(
                {"detail": "Product is protected by database constraints; marked Inactive instead of deleting."},
                status=200,
            )


class PriceListViewSet(CompanyScopedViewSet):
    queryset = PriceList.objects.prefetch_related("items__product")
    serializer_class = PriceListSerializer

    def perform_destroy(self, instance):
        _soft_destroy(instance, self.request.user)
        # a soft delete is still a delete: it must leave the same audit row a hard one did
        self._audit_raw("DELETE", str(instance.pk))

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]
