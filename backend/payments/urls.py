from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    BankAccountViewSet,
    BankStatementViewSet,
    CustomerReceiptViewSet,
    GatewayPaymentViewSet,
    GatewaySettingsView,
    PaymentAllocationViewSet,
    PaymentHealthView,
    PaymentLinkViewSet,
    ReconViewSet,
    SupplierPaymentViewSet,
    UpiQrView,
)
from .webhook_views import payment_webhook, public_payment_link

router = DefaultRouter()
router.register("bank-accounts", BankAccountViewSet, basename="bank-accounts")
router.register("receipts", CustomerReceiptViewSet, basename="receipts")
router.register("supplier-payments", SupplierPaymentViewSet, basename="supplier-payments")
router.register("allocations", PaymentAllocationViewSet, basename="allocations")
router.register("links", PaymentLinkViewSet, basename="payment-links")
router.register("gateway-payments", GatewayPaymentViewSet, basename="gateway-payments")
router.register("statements", BankStatementViewSet, basename="bank-statements")
router.register("recon", ReconViewSet, basename="payment-recon")

urlpatterns = router.urls + [
    path("upi-qr/", UpiQrView.as_view(), name="upi-qr"),
    path("gateway-settings/", GatewaySettingsView.as_view(), name="gateway-settings"),
    path("health/", PaymentHealthView.as_view(), name="payment-health"),
]

# Mounted from config/urls at api/v1/ for public + webhooks
public_urlpatterns = [
    path("public/pay/<str:token>/", public_payment_link, name="public-pay"),
    path("webhooks/payments/<str:provider>/", payment_webhook, name="payment-webhook"),
]
