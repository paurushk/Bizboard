from django.urls import include, path
from core.routers import DefaultRouter

from .views import (
    AgeingView, BalanceView, ChallanViewSet, Itc04FilingViewSet, Itc04View, OrderViewSet,
    PrincipalMovementViewSet, ReceiptViewSet,
)

router = DefaultRouter()
router.register("orders", OrderViewSet, basename="jobwork-order")
router.register("challans", ChallanViewSet, basename="jobwork-challan")
router.register("receipts", ReceiptViewSet, basename="jobwork-receipt")
router.register("itc04-filings", Itc04FilingViewSet, basename="jobwork-itc04-filing")
router.register("principal-movements", PrincipalMovementViewSet, basename="jobwork-principal-movement")

urlpatterns = [
    path("balance/", BalanceView.as_view(), name="jobwork-balance"),
    path("ageing/", AgeingView.as_view(), name="jobwork-ageing"),
    path("itc04/", Itc04View.as_view(), name="jobwork-itc04"),
    path("", include(router.urls)),
]
