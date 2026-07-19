from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    RequestOtpView,
    VerifyOtpView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("otp/request/", RequestOtpView.as_view(), name="auth-otp-request"),
    path("otp/verify/", VerifyOtpView.as_view(), name="auth-otp-verify"),
    path("me/", MeView.as_view(), name="auth-me"),
]
