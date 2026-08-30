"""WSGI write gate for suspended / trial-expired SaaS subscriptions (BB-000671)."""

from django.http import JsonResponse

from billing.services import company_writes_blocked

ALLOW_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/health/",
    "/api/v1/billing/",
    "/api/v1/help-events/",
    "/api/v1/help-feedback/",
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
            try:
                from core.authentication import CookieJWTAuthentication

                result = CookieJWTAuthentication().authenticate(request)
                if result is not None:
                    request.user, request.auth = result
                    user = request.user
            except Exception:  # noqa: BLE001 — anonymous requests continue
                user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return self.get_response(request)
        from rest_framework.exceptions import APIException

        from core.exceptions import exception_error_code
        from core.permissions import get_company_user

        try:
            cu = get_company_user(request)
        except APIException as exc:
            message = exc.detail
            if isinstance(message, (list, tuple)):
                message = "; ".join(str(m) for m in message)
            else:
                message = str(message)
            return JsonResponse(
                {
                    "success": False,
                    "error": {
                        "code": exception_error_code(exc),
                        "message": message,
                    },
                },
                status=int(exc.status_code),
            )
        except Exception:  # noqa: BLE001 — company-less paths are not tenant writes
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
