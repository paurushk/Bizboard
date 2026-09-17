"""Company-scoped DRF throttles for expensive report endpoints."""

from rest_framework.throttling import SimpleRateThrottle

from .permissions import get_company_user


class CompanyRateThrottle(SimpleRateThrottle):
    """Rate limit keyed by company id + the view's ``throttle_scope``.

    Mirrors ScopedRateThrottle's deferred rate setup so ``scope`` can be read
    from the view on each request. Falls back to allowing the request when the
    caller has no active company membership (permission classes should already
    reject those requests).
    """

    scope_attr = "throttle_scope"

    def __init__(self):
        # Defer rate resolution until allow_request — scope comes from the view.
        pass

    def allow_request(self, request, view):
        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope:
            return True
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        cu = get_company_user(request)
        if cu is not None:
            ident = cu.company_id
        elif getattr(request, "user", None) is not None and request.user.is_authenticated:
            ident = f"user-{request.user.pk}"
        else:
            ident = self.get_ident(request) or "anon"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class TenantPlanRateThrottle(SimpleRateThrottle):
    """Optional per-tenant API cap from Plan.api_rate_per_minute (0 = off)."""

    scope = "tenant_api"

    def allow_request(self, request, view):
        if getattr(view, "throttle_classes", None) == []:
            return True
        try:
            cu = get_company_user(request)
        except Exception:  # noqa: BLE001 — unauthenticated / no company
            return True
        if cu is None:
            return True
        from billing.quotas import api_rate_per_minute

        limit = api_rate_per_minute(cu.company)
        if limit <= 0:
            return True
        self.rate = f"{int(limit)}/min"
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        try:
            cu = get_company_user(request)
        except Exception:  # noqa: BLE001 — unauthenticated / no company
            cu = None
        ident = cu.company_id if cu is not None else self.get_ident(request) or "anon"
        return self.cache_format % {"scope": self.scope, "ident": ident}
