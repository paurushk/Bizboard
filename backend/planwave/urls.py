from django.urls import path

from . import views

urlpatterns = [
    path("plan/quarantine/", views.QuarantineView.as_view()),
    path("plan/approvals/", views.ApprovalListCreate.as_view()),
    path("plan/approvals/<int:pk>/decide/", views.ApprovalDecide.as_view()),
    path("plan/section-50/", views.Section50View.as_view()),
    path("plan/eway/", views.EwayStubView.as_view()),
    path("plan/itc/", views.ItcCheckView.as_view()),
    path("plan/certification/", views.CertificationView.as_view()),
    path("plan/anomalies/", views.AnomalyList.as_view()),
    path("plan/bulk-invoices/", views.BulkInvoiceView.as_view()),
    path("plan/tally-map/", views.TallyMapView.as_view()),
    path("plan/tally-commit/", views.TallyCommitView.as_view()),
    path("plan/pharmacy/", views.PharmacyView.as_view()),
    path("plan/pharmacy/register/", views.PharmacyRegisterView.as_view()),
    path("plan/section-50.csv", views.Section50CsvView.as_view()),
    path("plan/itc/summary/", views.ItcSummaryView.as_view()),
    path("plan/gstr2b/score/", views.TwoBScoreView.as_view()),
    path("plan/overdue/", views.OverdueReportView.as_view()),
    path("plan/cashflow/", views.CashflowView.as_view()),
    path("plan/godowns/", views.GodownDashboardView.as_view()),
    path("plan/bulk-invoices/commit/", views.BulkCommitView.as_view()),
    path("plan/restore/", views.RestoreMasterView.as_view()),
    path("plan/warehouse-access/", views.WarehouseAccessView.as_view()),
    path("plan/pos-holds/", views.PosHoldView.as_view()),
    path("plan/print/", views.PrintBridgeView.as_view()),
    path("plan/catalog/", views.CatalogExportView.as_view()),
]
