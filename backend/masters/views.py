from django.core.cache import cache
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.permissions import CanViewMastersCatalog, HasCompany, IsOwner
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

# BB-000195: short TTL list cache for hot masters reads (no write invalidation yet).
_MASTERS_LIST_TTL = 60

# BB-000297/Wave 12B: masters mutation is Owner-only; list/retrieve stay HasCompany.
_MUTATE_ACTIONS = ("create", "update", "partial_update", "destroy")


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


class UnitViewSet(CompanyScopedViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer

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


class TaxRateViewSet(CompanyScopedViewSet):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer

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
        if getattr(self, "action", None) in (*_MUTATE_ACTIONS, "verify_gstin"):
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
        if getattr(self, "action", None) in (*_MUTATE_ACTIONS, "verify_gstin"):
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
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        q = self.request.query_params.get("search") or self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(sku__icontains=q)
                | Q(barcode__icontains=q)
                | Q(hsn_code__icontains=q)
            )
        return qs

    def destroy(self, request, *args, **kwargs):
        """Never hard-delete a referenced product (§4.5) — deactivate instead."""
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
        return super().destroy(request, *args, **kwargs)


class PriceListViewSet(CompanyScopedViewSet):
    queryset = PriceList.objects.prefetch_related("items__product")
    serializer_class = PriceListSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        # BB-000422: VIEWER must not browse product catalog / prices.
        return [IsAuthenticated(), HasCompany(), CanViewMastersCatalog()]
