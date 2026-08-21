from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LeadViewSet, OpportunityViewSet

router = DefaultRouter()
router.register("leads", LeadViewSet, basename="crm-lead")
router.register("opportunities", OpportunityViewSet, basename="crm-opportunity")

urlpatterns = [
    path("", include(router.urls)),
]
