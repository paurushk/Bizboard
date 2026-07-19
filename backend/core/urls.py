from rest_framework.routers import DefaultRouter

from .views import AuditEventViewSet, FileAssetViewSet, NotificationViewSet

router = DefaultRouter()
router.register("files", FileAssetViewSet, basename="files")
router.register("notifications", NotificationViewSet, basename="notifications")
router.register("audit", AuditEventViewSet, basename="audit")

urlpatterns = router.urls
