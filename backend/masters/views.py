from django.core.cache import cache
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
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        if getattr(self, "action", None) == "verify_gstin":
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
        return qs

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

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), CanCreatePurchases()]
        if getattr(self, "action", None) == "verify_gstin":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse party masters.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("search") or self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q))
        return qs

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


class ProductViewSet(CompanyScopedViewSet):
    queryset = Product.objects.select_related("category", "brand", "unit")
    serializer_class = ProductSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), CanManageInventory()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

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
                | build_search_q(q, defs)
            )
        qs = apply_cf_filters(qs, self.request.query_params, defs)
        return qs

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
        from masters.custom_fields import active_defs, distinct_values_for_keys

        keys = [
            row["key"]
            for row in active_defs(self.company)
            if row.get("type") == "list" and row.get("key")
        ]
        return Response(distinct_values_for_keys(self.company, keys))

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
            return Response(
                {"detail": "Product is protected by database constraints; marked Inactive instead of deleting."},
                status=200,
            )


class PriceListViewSet(CompanyScopedViewSet):
    queryset = PriceList.objects.prefetch_related("items__product")
    serializer_class = PriceListSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]
