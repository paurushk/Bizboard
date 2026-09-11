from django.urls import include, path
from core.routers import DefaultRouter

from .views import LeadViewSet, OpportunityViewSet

router = DefaultRouter()
router.register("leads", LeadViewSet, basename="crm-lead")
router.register("opportunities", OpportunityViewSet, basename="crm-opportunity")

urlpatterns = [
    path("", include(router.urls)),
]
