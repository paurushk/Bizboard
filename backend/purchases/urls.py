from rest_framework.routers import DefaultRouter

from .phase1_views import (
    PurchaseCreditNoteViewSet,
    PurchaseDebitNoteViewSet,
    PurchaseOrderViewSet,
)
from .views import PurchaseInvoiceViewSet, PurchaseReturnViewSet

router = DefaultRouter()
router.register("invoices", PurchaseInvoiceViewSet, basename="purchase-invoices")
router.register("returns", PurchaseReturnViewSet, basename="purchase-returns")
router.register("credit-notes", PurchaseCreditNoteViewSet, basename="purchase-credit-notes")
router.register("debit-notes", PurchaseDebitNoteViewSet, basename="purchase-debit-notes")
router.register("orders", PurchaseOrderViewSet, basename="purchase-orders")

urlpatterns = router.urls
