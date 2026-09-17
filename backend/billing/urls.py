from django.urls import path

from .views import (
    CheckoutView,
    DeadLetterListView,
    DeadLetterReplayView,
    PlanListView,
    PortalView,
    RazorpayWebhookView,
    SubscriptionDetailView,
)

urlpatterns = [
    path("plans/", PlanListView.as_view(), name="billing-plans"),
    path("subscription/", SubscriptionDetailView.as_view(), name="billing-subscription"),
    path("checkout/", CheckoutView.as_view(), name="billing-checkout"),
    path("portal/", PortalView.as_view(), name="billing-portal"),
    path("razorpay/webhook/", RazorpayWebhookView.as_view(), name="billing-razorpay-webhook"),
    path("dlq/", DeadLetterListView.as_view(), name="billing-dlq"),
    path("dlq/<int:pk>/replay/", DeadLetterReplayView.as_view(), name="billing-dlq-replay"),
]
