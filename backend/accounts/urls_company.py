from django.urls import path
from core.routers import DefaultRouter

from .backup_schedule_views import BackupScheduleView
from .export_views import TenantExportLastView, TenantExportView, TenantRestoreView
from .ownership_views import OwnershipAcceptView, OwnershipCancelView, OwnershipTransferView, OwnershipView
from .pack_views import NavScopeView, PackWizardView
from .readable_export_views import ReadableExportFileView, ReadableExportView
from .series_views import NumberSeriesView
from .session_views import MemberSessionCountsView
from .settings_history import SettingsHistoryView
from .settings_preview import SettingsPreviewView
from .team_views import TeamMembersView
from .settings_health import SettingsHealthView
from .views import (
    CompanyDetailView,
    CompanyEraseView,
    CompanyGstinViewSet,
    CompanyStatutoryLicenceViewSet,
    CompanyUserViewSet,
    CompanyVerifyGstinView,
    CompanyVerifyPanView,
    CompanyVerifyUdyamView,
)

router = DefaultRouter()
router.register("users", CompanyUserViewSet, basename="company-users")
router.register("gstins", CompanyGstinViewSet, basename="company-gstins")
router.register("statutory-licences", CompanyStatutoryLicenceViewSet, basename="company-statutory-licences")

urlpatterns = [
    path("", CompanyDetailView.as_view(), name="company-detail"),
    path("verify-gstin/", CompanyVerifyGstinView.as_view(), name="company-verify-gstin"),
    path("verify-pan/", CompanyVerifyPanView.as_view(), name="company-verify-pan"),
    path("verify-udyam/", CompanyVerifyUdyamView.as_view(), name="company-verify-udyam"),
    path("export/", TenantExportView.as_view(), name="company-tenant-export"),
    path("export/schedule/", BackupScheduleView.as_view(), name="company-backup-schedule"),
    path("export/last/", TenantExportLastView.as_view(), name="company-tenant-export-last"),
    path("export/readable/", ReadableExportView.as_view(), name="company-readable-export"),
    path("export/readable/<int:pk>/file/", ReadableExportFileView.as_view(), name="company-readable-export-file"),
    path("restore/", TenantRestoreView.as_view(), name="company-tenant-restore"),
    path("erase/", CompanyEraseView.as_view(), name="company-erase"),
    # WP-ID1: hand the company to another owner.
    path("ownership/", OwnershipView.as_view(), name="company-ownership"),
    path("users/session-counts/", MemberSessionCountsView.as_view(), name="company-user-session-counts"),
    path("members/", TeamMembersView.as_view(), name="company-members"),
    path("ownership/transfer/", OwnershipTransferView.as_view(), name="company-ownership-transfer"),
    path("ownership/accept/", OwnershipAcceptView.as_view(), name="company-ownership-accept"),
    path("ownership/cancel/", OwnershipCancelView.as_view(), name="company-ownership-cancel"),
    path("packs/", PackWizardView.as_view(), name="company-packs"),
    path("settings-health/", SettingsHealthView.as_view(), name="company-settings-health"),
    path("number-series/", NumberSeriesView.as_view(), name="company-number-series"),
    path("settings-history/", SettingsHistoryView.as_view(), name="company-settings-history"),
    path("settings-preview/", SettingsPreviewView.as_view(), name="company-settings-preview"),
    path("nav-scope/", NavScopeView.as_view(), name="company-nav-scope"),
] + router.urls
