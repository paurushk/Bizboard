from rest_framework.routers import DefaultRouter

from .views import (
    BrandViewSet,
    CategoryViewSet,
    CustomerViewSet,
    ExpenseCategoryViewSet,
    PaymentModeViewSet,
    ProductViewSet,
    PriceListViewSet,
    SupplierViewSet,
    TaxRateViewSet,
    UnitViewSet,
)

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customers")
router.register("suppliers", SupplierViewSet, basename="suppliers")
router.register("products", ProductViewSet, basename="products")
router.register("masters/price-lists", PriceListViewSet, basename="price-lists")
router.register("masters/categories", CategoryViewSet, basename="categories")
router.register("masters/brands", BrandViewSet, basename="brands")
router.register("masters/units", UnitViewSet, basename="units")
router.register("masters/tax-rates", TaxRateViewSet, basename="tax-rates")
router.register("masters/payment-modes", PaymentModeViewSet, basename="payment-modes")
router.register("masters/expense-categories", ExpenseCategoryViewSet, basename="expense-categories")

urlpatterns = router.urls
