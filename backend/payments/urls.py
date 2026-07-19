from rest_framework.routers import DefaultRouter

from .views import CustomerReceiptViewSet, PaymentAllocationViewSet, SupplierPaymentViewSet

router = DefaultRouter()
router.register("receipts", CustomerReceiptViewSet, basename="receipts")
router.register("supplier-payments", SupplierPaymentViewSet, basename="supplier-payments")
router.register("allocations", PaymentAllocationViewSet, basename="allocations")

urlpatterns = router.urls
