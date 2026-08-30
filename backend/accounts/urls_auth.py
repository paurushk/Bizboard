from django.urls import path

from .views import (
    AcceptInviteView,
    ChangePasswordView,
    CookieTokenRefreshView,
    CsrfCookieView,
    LoginView,
    LogoutAllView,
    LogoutView,
    MeView,
    MembershipsListView,
    RegisterView,
    RequestOtpView,
    RequestPasswordResetView,
    ConfirmPasswordResetView,
    SwitchCompanyView,
    VerifyOtpView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("csrf/", CsrfCookieView.as_view(), name="auth-csrf"),
    path("refresh/", CookieTokenRefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("logout-all/", LogoutAllView.as_view(), name="auth-logout-all"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("invite/accept/", AcceptInviteView.as_view(), name="auth-invite-accept"),
    path("otp/request/", RequestOtpView.as_view(), name="auth-otp-request"),
    path("otp/verify/", VerifyOtpView.as_view(), name="auth-otp-verify"),
    path("password/reset/", RequestPasswordResetView.as_view(), name="auth-password-reset"),
    path("password/reset/confirm/", ConfirmPasswordResetView.as_view(), name="auth-password-reset-confirm"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("memberships/", MembershipsListView.as_view(), name="auth-memberships"),
    path("switch-company/", SwitchCompanyView.as_view(), name="auth-switch-company"),
]
