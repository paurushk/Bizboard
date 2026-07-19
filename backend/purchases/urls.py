from rest_framework.routers import DefaultRouter

from .views import PurchaseInvoiceViewSet, PurchaseReturnViewSet

router = DefaultRouter()
router.register("invoices", PurchaseInvoiceViewSet, basename="purchase-invoices")
router.register("returns", PurchaseReturnViewSet, basename="purchase-returns")

urlpatterns = router.urls
