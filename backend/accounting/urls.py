from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AccountViewSet, AccountingReportView, AccountingSettingsView, BankReconSessionViewSet,
    CostCenterViewSet, FinancialYearCloseView, FixedAssetViewSet, JournalViewSet, PeriodViewSet,
)

router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="accounting-account")
router.register("periods", PeriodViewSet, basename="accounting-period")
router.register("cost-centers", CostCenterViewSet, basename="accounting-cost-center")
router.register("journals", JournalViewSet, basename="accounting-journal")
router.register("bank-recon-sessions", BankReconSessionViewSet, basename="accounting-bank-recon")
router.register("fixed-assets", FixedAssetViewSet, basename="accounting-fixed-asset")

urlpatterns = [
    path("", include(router.urls)),
    path("settings/", AccountingSettingsView.as_view(), name="accounting-settings"),
    path("fy-close/", FinancialYearCloseView.as_view(), name="accounting-fy-close"),
    path("<str:report>/", AccountingReportView.as_view(), name="accounting-report"),
]
