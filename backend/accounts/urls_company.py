from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CompanyDetailView, CompanyUserViewSet

router = DefaultRouter()
router.register("users", CompanyUserViewSet, basename="company-users")

urlpatterns = [
    path("", CompanyDetailView.as_view(), name="company-detail"),
] + router.urls
