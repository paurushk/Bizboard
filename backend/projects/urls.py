from core.routers import DefaultRouter

from .views import ProjectViewSet

router = DefaultRouter()
router.register("", ProjectViewSet, basename="project")
urlpatterns = router.urls
