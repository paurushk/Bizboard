from django.urls import path

from core.routers import DefaultRouter

from .views import AdvisorBookView, PolicyOptionSetViewSet, PolicyProductViewSet, PolicyViewSet, ProspectView, RenewalDiaryView

router = DefaultRouter()
router.register("products", PolicyProductViewSet, basename="policy-product")
router.register("option-sets", PolicyOptionSetViewSet, basename="policy-option-set")
router.register("policies", PolicyViewSet, basename="policy")

urlpatterns = [
    path("prospects/", ProspectView.as_view(), name="insurance-prospect"),
    path("book/", AdvisorBookView.as_view(), name="insurance-book"),
    path("renewals/", RenewalDiaryView.as_view(), name="insurance-renewals"),
    *router.urls,
]
