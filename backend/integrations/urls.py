from django.urls import path

from .shopify import ShopifyWebhookView
from .views import (
    TallyCommitView,
    TallyErrorsView,
    TallyExportView,
    TallyHttpPushView,
    TallyMigrationDiffView,
    TallyPreviewView,
    TallyUploadView,
    WhatsAppConnectionView,
)

urlpatterns = [
    path("tally/upload/", TallyUploadView.as_view(), name="tally-upload"),
    path("tally/preview/", TallyPreviewView.as_view(), name="tally-preview"),
    path("tally/commit/", TallyCommitView.as_view(), name="tally-commit"),
    path("tally/export/", TallyExportView.as_view(), name="tally-export"),
    path("tally/push-http/", TallyHttpPushView.as_view(), name="tally-push-http"),
    path("tally/migrate-diff/", TallyMigrationDiffView.as_view(), name="tally-migrate-diff"),
    path("tally/runs/<int:pk>/errors/", TallyErrorsView.as_view(), name="tally-errors"),
    path("whatsapp/connection/", WhatsAppConnectionView.as_view(), name="whatsapp-connection"),
    path("shopify/webhook/", ShopifyWebhookView.as_view(), name="shopify-webhook"),
]
