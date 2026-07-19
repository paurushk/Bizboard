from rest_framework.routers import DefaultRouter

from .views import (
    BrandViewSet,
    CategoryViewSet,
    CustomerViewSet,
    ProductViewSet,
    SupplierViewSet,
    TaxRateViewSet,
    UnitViewSet,
)

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customers")
router.register("suppliers", SupplierViewSet, basename="suppliers")
router.register("products", ProductViewSet, basename="products")
router.register("masters/categories", CategoryViewSet, basename="categories")
router.register("masters/brands", BrandViewSet, basename="brands")
router.register("masters/units", UnitViewSet, basename="units")
router.register("masters/tax-rates", TaxRateViewSet, basename="tax-rates")

urlpatterns = router.urls
