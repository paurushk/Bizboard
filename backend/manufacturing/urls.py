from django.urls import include, path
from core.routers import DefaultRouter

from .views import BomViewSet, MfgSettingsView, WorkOrderViewSet
from .views_shopfloor import (
    DowntimeReasonViewSet, DowntimeViewSet, JobCardViewSet, LoadView, MachineViewSet, MaintenanceLogViewSet,
    MaintenancePlanViewSet, OperatorViewSet, RoutingView, TabletCardActionView, TabletCardsView,
    TabletDowntimeView, TabletLoginView, UtilisationView, WorkCentreViewSet,
)
from .views_reports import ReportView, StandardCostViewSet
from .views_revaluation import StandardRevaluationViewSet
from .views_planning import (
    AtpView, BoardView, CanMakeView, CostRollupView, CreateFromSalesOrderView, ExplodeView, MrpRunViewSet,
    SalesOrderStatusView, SetPriorityView, ShortagesView, WhereUsedView, WorkOrderAvailabilityView,
)
from .views_docs import (
    MaterialIssueViewSet, MaterialReturnViewSet, ProductionReceiptViewSet, QuickProductionView, TraceView, BatchSearchView,
)

router = DefaultRouter()
router.register("boms", BomViewSet, basename="manufacturing-bom")
router.register("work-orders", WorkOrderViewSet, basename="manufacturing-work-order")
router.register("material-issues", MaterialIssueViewSet, basename="manufacturing-material-issue")
router.register("material-returns", MaterialReturnViewSet, basename="manufacturing-material-return")
router.register("standard-costs", StandardCostViewSet, basename="manufacturing-standard-cost")
router.register("standard-revaluations", StandardRevaluationViewSet, basename="manufacturing-standard-revaluation")
router.register("work-centres", WorkCentreViewSet, basename="manufacturing-work-centre")
router.register("job-cards", JobCardViewSet, basename="manufacturing-job-card")
router.register("operators", OperatorViewSet, basename="manufacturing-operator")
router.register("downtime-reasons", DowntimeReasonViewSet, basename="manufacturing-downtime-reason")
router.register("downtime", DowntimeViewSet, basename="manufacturing-downtime")
router.register("machines", MachineViewSet, basename="manufacturing-machine")
router.register("maintenance-plans", MaintenancePlanViewSet, basename="manufacturing-maintenance-plan")
router.register("maintenance-log", MaintenanceLogViewSet, basename="manufacturing-maintenance-log")
router.register("mrp-runs", MrpRunViewSet, basename="manufacturing-mrp-run")
router.register("production-receipts", ProductionReceiptViewSet, basename="manufacturing-production-receipt")

urlpatterns = [
    path("settings/", MfgSettingsView.as_view(), name="manufacturing-settings"),
    path("reports/<slug:slug>/", ReportView.as_view(), name="manufacturing-report"),
    path("boms/<int:pk>/routing/", RoutingView.as_view(), name="manufacturing-routing"),
    path("load/", LoadView.as_view(), name="manufacturing-load"),
    path("utilisation/", UtilisationView.as_view(), name="manufacturing-utilisation"),
    path("tablet/login/", TabletLoginView.as_view(), name="manufacturing-tablet-login"),
    path("tablet/cards/", TabletCardsView.as_view(), name="manufacturing-tablet-cards"),
    path("tablet/cards/<int:pk>/<str:verb>/", TabletCardActionView.as_view(), name="manufacturing-tablet-card-action"),
    path("tablet/downtime/<str:verb>/", TabletDowntimeView.as_view(), name="manufacturing-tablet-downtime"),
    path("explode/", ExplodeView.as_view(), name="manufacturing-explode"),
    path("where-used/", WhereUsedView.as_view(), name="manufacturing-where-used"),
    path("cost-rollup/", CostRollupView.as_view(), name="manufacturing-cost-rollup"),
    path("can-make/", CanMakeView.as_view(), name="manufacturing-can-make"),
    path("shortages/", ShortagesView.as_view(), name="manufacturing-shortages"),
    path("atp/", AtpView.as_view(), name="manufacturing-atp"),
    path("board/", BoardView.as_view(), name="manufacturing-board"),
    path("sales-order-status/", SalesOrderStatusView.as_view(), name="manufacturing-so-status"),
    path("work-orders/from-sales-order/", CreateFromSalesOrderView.as_view(), name="manufacturing-from-so"),
    path("work-orders/<int:pk>/availability/", WorkOrderAvailabilityView.as_view(), name="manufacturing-wo-availability"),
    path("work-orders/<int:pk>/set-priority/", SetPriorityView.as_view(), name="manufacturing-wo-priority"),
    path("trace/", TraceView.as_view(), name="manufacturing-trace"),
    path("batches/", BatchSearchView.as_view(), name="manufacturing-batch-search"),
    path("quick-production/", QuickProductionView.as_view(), name="manufacturing-quick-production"),
    path("", include(router.urls)),
]
