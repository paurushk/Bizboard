from core.routers import DefaultRouter

from .views import JobCardViewSet

router = DefaultRouter()
router.register("job-cards", JobCardViewSet, basename="job-card")
urlpatterns = router.urls
