from core.routers import DefaultRouter

from .views import PlatformTicketViewSet, SupportAccessGrantViewSet, TicketViewSet, VendorTicketShareViewSet

router = DefaultRouter()
router.register("tickets", TicketViewSet, basename="ticket")
router.register("shared", VendorTicketShareViewSet, basename="vendor-ticket-share")
# WP-PO3: tenant-to-Bizboard support (not the merchant helpdesk above).
router.register("platform-tickets", PlatformTicketViewSet, basename="platform-ticket")
router.register("access-grants", SupportAccessGrantViewSet, basename="support-access-grant")

urlpatterns = router.urls
