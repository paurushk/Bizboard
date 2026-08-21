from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import AuditEventViewSet, FeatureFlagsView, FileAssetViewSet, NotificationViewSet, StatutoryDocumentEventViewSet

router = DefaultRouter()
router.register("files", FileAssetViewSet, basename="files")
router.register("notifications", NotificationViewSet, basename="notifications")
router.register("audit", AuditEventViewSet, basename="audit")
router.register("statutory-events", StatutoryDocumentEventViewSet, basename="statutory-events")

urlpatterns = router.urls + [
    path("feature-flags/", FeatureFlagsView.as_view(), name="feature-flags"),
]
