"""DRF write gate for suspended / trial-expired SaaS subscriptions (BB-000671)."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from billing.services import company_writes_blocked

ALLOW_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/health/",
    "/api/v1/billing/",
)


class SubscriptionWritesAllowed(BasePermission):
    message = "Subscription is suspended or the trial has expired. Billing portal remains available."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        path = getattr(request, "path", "") or ""
        if any(path.startswith(prefix) for prefix in ALLOW_PREFIXES):
            return True
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return True
        from rest_framework.exceptions import APIException

        from core.permissions import get_company_user

        try:
            cu = get_company_user(request)
        except APIException:
            raise
        except Exception:  # noqa: BLE001 — missing company context is not a write
            return True
        if cu is None:
            return True
        return not company_writes_blocked(cu.company)
