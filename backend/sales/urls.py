from rest_framework.routers import DefaultRouter

from .views import QuotationViewSet, SalesInvoiceViewSet, SalesReturnViewSet

router = DefaultRouter()
router.register("invoices", SalesInvoiceViewSet, basename="sales-invoices")
router.register("quotations", QuotationViewSet, basename="quotations")
router.register("returns", SalesReturnViewSet, basename="sales-returns")

urlpatterns = router.urls
