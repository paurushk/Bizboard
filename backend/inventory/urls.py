from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdjustmentView,
    LowStockAlertsView,
    ExpiryAlertsView,
    OpeningStockView,
    SerialNumberViewSet,
    StockBalanceViewSet,
    StockMovementViewSet,
    StockTransferViewSet,
    StockValuationReportView,
    WarehouseViewSet,
    BatchLotViewSet,
)

router = DefaultRouter()
router.register("balances", StockBalanceViewSet, basename="stock-balances")
router.register("movements", StockMovementViewSet, basename="stock-movements")
router.register("warehouses", WarehouseViewSet, basename="warehouses")
router.register("transfers", StockTransferViewSet, basename="stock-transfers")
router.register("batches", BatchLotViewSet, basename="batch-lots")
router.register("serials", SerialNumberViewSet, basename="serial-numbers")

urlpatterns = [
    path("adjustments/", AdjustmentView.as_view(), name="stock-adjustments"),
    path("opening-stock/", OpeningStockView.as_view(), name="opening-stock"),
    path("alerts/", LowStockAlertsView.as_view(), name="stock-alerts"),
    path("alerts/expiry/", ExpiryAlertsView.as_view(), name="expiry-alerts"),
    path("valuation/", StockValuationReportView.as_view(), name="stock-valuation"),
] + router.urls
