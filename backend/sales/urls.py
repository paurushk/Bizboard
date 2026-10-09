from django.urls import path, re_path
from core.routers import DefaultRouter

from .phase1_views import (
    DeliveryChallanViewSet,
    SalesCreditNoteViewSet,
    SalesDebitNoteViewSet,
    SalesOrderViewSet,
)
from .route_combine import RouteCombineView
from .route_views import DeliveryChallanReturnViewSet, DeliveryRouteViewSet, PodSlipView
from .pos_batch import PosBatchSyncView
from .pos_views import PosCollectView, PosCounterEventView, PosReturnView, PosSettingsView
from .public_invoice_views import PublicInvoicePayView, PublicInvoicePdfView, PublicInvoiceView
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

public_urlpatterns = [
    path("public/invoices/<str:token>/pdf/", PublicInvoicePdfView.as_view(), name="public-invoice-pdf"),
    path("public/invoices/<str:token>/pay/", PublicInvoicePayView.as_view(), name="public-invoice-pay"),
    path("public/invoices/<str:token>/", PublicInvoiceView.as_view(), name="public-invoice"),
]

urlpatterns = [
    path("pos/batch-sync/", PosBatchSyncView.as_view(), name="pos-batch-sync"),
    path("pos/settings/", PosSettingsView.as_view(), name="pos-settings"),
    path("pos/events/", PosCounterEventView.as_view(), name="pos-events"),
    path("pos/collect/", PosCollectView.as_view(), name="pos-collect"),
    path("pos/return/", PosReturnView.as_view(), name="pos-return"),
    path("delivery-routes/combine-suggestions/", RouteCombineView.as_view(), name="route-combine"),
    re_path(
        r"^delivery-routes/(?P<pk>[0-9]+)/stops/(?P<stop_id>[0-9]+)/pod\.pdf$",
        PodSlipView.as_view(),
        name="delivery-route-pod",
    ),
] + router.urls
