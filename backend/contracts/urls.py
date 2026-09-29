from core.routers import DefaultRouter

from .views import ContractViewSet

router = DefaultRouter()
router.register("", ContractViewSet, basename="contract")

urlpatterns = router.urls
