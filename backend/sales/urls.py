from rest_framework.routers import DefaultRouter

from .phase1_views import (
    DeliveryChallanViewSet,
    SalesCreditNoteViewSet,
    SalesDebitNoteViewSet,
    SalesOrderViewSet,
)
from .views import QuotationViewSet, RecurringInvoiceScheduleViewSet, SalesInvoiceViewSet, SalesReturnViewSet

router = DefaultRouter()
router.register("invoices", SalesInvoiceViewSet, basename="sales-invoices")
router.register("quotations", QuotationViewSet, basename="quotations")
router.register("returns", SalesReturnViewSet, basename="sales-returns")
router.register("credit-notes", SalesCreditNoteViewSet, basename="sales-credit-notes")
router.register("debit-notes", SalesDebitNoteViewSet, basename="sales-debit-notes")
router.register("orders", SalesOrderViewSet, basename="sales-orders")
router.register("delivery-challans", DeliveryChallanViewSet, basename="delivery-challans")
router.register("recurring-schedules", RecurringInvoiceScheduleViewSet, basename="recurring-schedules")

urlpatterns = router.urls
