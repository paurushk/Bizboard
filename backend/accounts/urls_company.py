from django.urls import path
from rest_framework.routers import DefaultRouter

from .export_views import TenantExportView, TenantRestoreView
from .views import (
    CompanyDetailView,
    CompanyGstinViewSet,
    CompanyUserViewSet,
    CompanyVerifyGstinView,
    CompanyVerifyPanView,
    CompanyVerifyUdyamView,
)

router = DefaultRouter()
router.register("users", CompanyUserViewSet, basename="company-users")
router.register("gstins", CompanyGstinViewSet, basename="company-gstins")

urlpatterns = [
    path("", CompanyDetailView.as_view(), name="company-detail"),
    path("verify-gstin/", CompanyVerifyGstinView.as_view(), name="company-verify-gstin"),
    path("verify-pan/", CompanyVerifyPanView.as_view(), name="company-verify-pan"),
    path("verify-udyam/", CompanyVerifyUdyamView.as_view(), name="company-verify-udyam"),
    path("export/", TenantExportView.as_view(), name="company-tenant-export"),
    path("restore/", TenantRestoreView.as_view(), name="company-tenant-restore"),
] + router.urls
