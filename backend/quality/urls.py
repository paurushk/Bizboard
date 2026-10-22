from django.urls import include, path
from core.routers import DefaultRouter

from .views import (
    BatchStatusView, DefectCodeViewSet, InspectionTemplateViewSet, InspectionViewSet,
    NonConformanceViewSet, ScorecardView,
)

router = DefaultRouter()
router.register("defect-codes", DefectCodeViewSet, basename="quality-defect-code")
router.register("templates", InspectionTemplateViewSet, basename="quality-template")
router.register("inspections", InspectionViewSet, basename="quality-inspection")
router.register("non-conformances", NonConformanceViewSet, basename="quality-ncr")

urlpatterns = [
    path("supplier-scorecard/", ScorecardView.as_view(), name="quality-scorecard"),
    path("batches/<int:pk>/status/", BatchStatusView.as_view(), name="quality-batch-status"),
    path("", include(router.urls)),
]
