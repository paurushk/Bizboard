"""WSGI write gate for suspended / trial-expired SaaS subscriptions (BB-000671)."""

from django.http import JsonResponse

from billing.services import company_writes_blocked

ALLOW_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/health/",
    "/api/v1/billing/",
)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


class SubscriptionWriteGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in SAFE_METHODS:
            return self.get_response(request)
        path = getattr(request, "path", "") or ""
        if any(path.startswith(prefix) for prefix in ALLOW_PREFIXES):
            return self.get_response(request)
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return self.get_response(request)
        from core.permissions import get_company_user

        try:
            cu = get_company_user(request)
        except Exception:  # noqa: BLE001 — gate must not break unauthenticated/company-less paths
            return self.get_response(request)
        if cu is None:
            return self.get_response(request)
        if company_writes_blocked(cu.company):
            return JsonResponse(
                {
                    "success": False,
                    "error": {
                        "code": "subscription_blocked",
                        "message": "Subscription is suspended or the trial has expired. Billing portal remains available.",
                    },
                },
                status=403,
            )
        return self.get_response(request)
