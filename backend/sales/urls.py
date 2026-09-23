from django.urls import path
from core.routers import DefaultRouter

from .phase1_views import (
    DeliveryChallanViewSet,
    SalesCreditNoteViewSet,
    SalesDebitNoteViewSet,
    SalesOrderViewSet,
)
from .route_combine import RouteCombineView
from .route_views import DeliveryChallanReturnViewSet, DeliveryRouteViewSet
from .views import QuotationViewSet, RecurringInvoiceScheduleViewSet, SalesInvoiceViewSet, SalesReturnViewSet

router = DefaultRouter()
router.register("invoices", SalesInvoiceViewSet, basename="sales-invoices")
router.register("quotations", QuotationViewSet, basename="quotations")
router.register("returns", SalesReturnViewSet, basename="sales-returns")
router.register("credit-notes", SalesCreditNoteViewSet, basename="sales-credit-notes")
router.register("debit-notes", SalesDebitNoteViewSet, basename="sales-debit-notes")
router.register("orders", SalesOrderViewSet, basename="sales-orders")
router.register("delivery-challans", DeliveryChallanViewSet, basename="delivery-challans")
router.register("delivery-routes", DeliveryRouteViewSet, basename="delivery-routes")
router.register("challan-returns", DeliveryChallanReturnViewSet, basename="challan-returns")
router.register("recurring-schedules", RecurringInvoiceScheduleViewSet, basename="recurring-schedules")

urlpatterns = [
    path("delivery-routes/combine-suggestions/", RouteCombineView.as_view(), name="route-combine"),
] + router.urls
