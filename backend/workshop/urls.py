from core.routers import DefaultRouter

from .views import JobCardViewSet, ServiceBayViewSet

router = DefaultRouter()
router.register("job-cards", JobCardViewSet, basename="job-card")
router.register("bays", ServiceBayViewSet, basename="service-bay")
urlpatterns = router.urls
