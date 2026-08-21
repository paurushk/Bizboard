from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EmployeeViewSet, PayRunViewSet

router = DefaultRouter()
router.register("employees", EmployeeViewSet, basename="payroll-employee")
router.register("pay-runs", PayRunViewSet, basename="payroll-pay-run")

urlpatterns = [
    path("", include(router.urls)),
]
