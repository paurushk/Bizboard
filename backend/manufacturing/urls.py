from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BomViewSet, WorkOrderViewSet

router = DefaultRouter()
router.register("boms", BomViewSet, basename="manufacturing-bom")
router.register("work-orders", WorkOrderViewSet, basename="manufacturing-work-order")

urlpatterns = [
    path("", include(router.urls)),
]
