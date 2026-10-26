from django.urls import path

from core.routers import DefaultRouter

from .satisfaction_views import NpsDueView, SatisfactionAnswerView

from .views import PlatformTicketViewSet, SupportAccessGrantViewSet, TicketViewSet, VendorTicketShareViewSet

router = DefaultRouter()
router.register("tickets", TicketViewSet, basename="ticket")
router.register("shared", VendorTicketShareViewSet, basename="vendor-ticket-share")
# WP-PO3: tenant-to-Bizboard support (not the merchant helpdesk above).
router.register("platform-tickets", PlatformTicketViewSet, basename="platform-ticket")
router.register("access-grants", SupportAccessGrantViewSet, basename="support-access-grant")

urlpatterns = [
    # BB-136: NPS prompt and support CSAT (behind ENABLE_SATISFACTION_SURVEY).
    path("satisfaction/", SatisfactionAnswerView.as_view(), name="support-satisfaction"),
    path("satisfaction/nps-due/", NpsDueView.as_view(), name="support-satisfaction-nps-due"),
] + router.urls
