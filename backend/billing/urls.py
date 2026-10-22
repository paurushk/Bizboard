from django.urls import path

from .views import (
    CheckoutView,
    DeadLetterListView,
    DeadLetterReplayView,
    PlanListView,
    OnboardingChecklistView,
    OnboardingDismissView,
    PlatformInvoiceListView,
    PlatformInvoicePdfView,
    PortalView,
    RazorpayWebhookView,
    SaasTdsClaimRefundView,
    SaasTdsClaimView,
    SubscriptionDetailView,
    VendorTenantsView,
)

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="billing-plans"),
    path("subscription/", SubscriptionDetailView.as_view(), name="billing-subscription"),
    path("vendor/tenants/", VendorTenantsView.as_view(), name="billing-vendor-tenants"),
    path("checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path("portal/", PortalView.as_view(), name="billing-portal"),
    path("razorpay/webhook/", RazorpayWebhookView.as_view(), name="billing-razorpay-webhook"),
    path("invoices/", PlatformInvoiceListView.as_view(), name="billing-invoices"),
    path("onboarding/", OnboardingChecklistView.as_view(), name="billing-onboarding"),
    path("onboarding/dismiss/", OnboardingDismissView.as_view(), name="billing-onboarding-dismiss"),
    path("invoices/<int:pk>/pdf/", PlatformInvoicePdfView.as_view(), name="billing-invoice-pdf"),
    path("tds-claims/", SaasTdsClaimView.as_view(), name="billing-tds-claims"),
    path("tds-claims/<int:pk>/refund/", SaasTdsClaimRefundView.as_view(), name="billing-tds-claim-refund"),
    path("dlq/", DeadLetterListView.as_view(), name="billing-dlq"),
    path("dlq/<int:pk>/replay/", DeadLetterReplayView.as_view(), name="billing-dlq-replay"),
]
