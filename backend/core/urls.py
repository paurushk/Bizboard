from django.urls import path

from .help_views import HelpEventsView, HelpFeedbackView, HelpHealthView
from .routers import DefaultRouter
from .views import (
    AuditEventViewSet,
    FeatureFlagsView,
    FileAssetViewSet,
    InvariantsCheckView,
    IntegrationsInventoryView,
    NotificationViewSet,
    StatutoryDocumentEventViewSet,
    TelegramLinkView,
    TelegramStatusView,
    TelegramUnlinkView,
    ops_alert_webhook,
    telegram_webhook,
)

router = DefaultRouter()
router.register("files", FileAssetViewSet, basename="files")
router.register("notifications", NotificationViewSet, basename="notifications")
router.register("audit", AuditEventViewSet, basename="audit")
router.register("statutory-events", StatutoryDocumentEventViewSet, basename="statutory-events")

urlpatterns = router.urls + [
    path("feature-flags/", FeatureFlagsView.as_view(), name="feature-flags"),
    path("invariants/check/", InvariantsCheckView.as_view(), name="invariants-check"),
    path("integrations/inventory/", IntegrationsInventoryView.as_view(), name="integrations-inventory"),
    path("help-events/", HelpEventsView.as_view(), name="help-events"),
    path("help-feedback/", HelpFeedbackView.as_view(), name="help-feedback"),
    path("help-health/", HelpHealthView.as_view(), name="help-health"),
    path("telegram/status/", TelegramStatusView.as_view(), name="telegram-status"),
    path("telegram/link/", TelegramLinkView.as_view(), name="telegram-link"),
    path("telegram/unlink/", TelegramUnlinkView.as_view(), name="telegram-unlink"),
    path("telegram/webhook/", telegram_webhook, name="telegram-webhook"),
    path("ops/alert/", ops_alert_webhook, name="ops-alert-webhook"),
]
