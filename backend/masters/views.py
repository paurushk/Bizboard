from django.db.models import Q
from rest_framework.response import Response

from core.viewsets import CompanyScopedViewSet

from .models import Brand, Category, Customer, Product, Supplier, TaxRate, Unit
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    CustomerSerializer,
    ProductSerializer,
    SupplierSerializer,
    TaxRateSerializer,
    UnitSerializer,
)


class CategoryViewSet(CompanyScopedViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class BrandViewSet(CompanyScopedViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer


class UnitViewSet(CompanyScopedViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class TaxRateViewSet(CompanyScopedViewSet):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer


class CustomerViewSet(CompanyScopedViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q))
        return qs


class SupplierViewSet(CompanyScopedViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q))
        return qs


class ProductViewSet(CompanyScopedViewSet):
    queryset = Product.objects.select_related("category", "brand", "unit")
    serializer_class = ProductSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(sku__iexact=q) | Q(barcode__iexact=q)
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
