from rest_framework.routers import DefaultRouter

from .views import ImportJobViewSet

router = DefaultRouter()
router.register("", ImportJobViewSet, basename="imports")

urlpatterns = router.urls
