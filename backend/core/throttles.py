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
        if cu is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": cu.company_id}
