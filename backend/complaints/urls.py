from core.routers import DefaultRouter

from .supplier_views import SupplierComplaintViewSet
from .views import ComplaintViewSet

router = DefaultRouter()
router.register("supplier", SupplierComplaintViewSet, basename="supplier-complaint")
router.register("", ComplaintViewSet, basename="complaint")

urlpatterns = router.urls
