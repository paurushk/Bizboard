from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AdjustmentView,
    LowStockAlertsView,
    OpeningStockView,
    StockBalanceViewSet,
    StockMovementViewSet,
)

router = DefaultRouter()
router.register("balances", StockBalanceViewSet, basename="stock-balances")
router.register("movements", StockMovementViewSet, basename="stock-movements")

urlpatterns = [
    path("adjustments/", AdjustmentView.as_view(), name="stock-adjustments"),
    path("opening-stock/", OpeningStockView.as_view(), name="opening-stock"),
    path("alerts/", LowStockAlertsView.as_view(), name="stock-alerts"),
] + router.urls
