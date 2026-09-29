from core.routers import DefaultRouter

from .views import TicketViewSet, VendorTicketShareViewSet

router = DefaultRouter()
router.register("tickets", TicketViewSet, basename="ticket")
router.register("shared", VendorTicketShareViewSet, basename="vendor-ticket-share")

urlpatterns = router.urls
