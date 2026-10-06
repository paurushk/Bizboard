"""Bulk offline POS sync (BUG-PERF-008).

The per-bill checkout stays in SalesInvoiceViewSet.pos_checkout. This view
runs that same method once per checkout.

Each checkout is its own unit of work:

* it runs in its own savepoint, so one bad bill never rolls back the others, and
* it carries its own ``idempotency_key``, so replaying the whole batch after a
  lost response returns the bills already created instead of creating them again.
"""

from django.db import transaction
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.permissions import SubscriptionWritesAllowed
from core.exceptions import BusinessRuleError
from core.permissions import CanCreatePayments, CanCreateSales, HasCompany, get_company_user

MAX_CHECKOUTS = 50


class _ItemHeaders:
    """Request headers with the Idempotency-Key replaced by this checkout's own key."""

    def __init__(self, original, key):
        self._original = original
        self._key = key

    def get(self, name, default=None):
        if str(name).lower() == "idempotency-key":
            return self._key
        return self._original.get(name, default)

    def __getitem__(self, name):
        value = self.get(name)
        if value is None:
            raise KeyError(name)
        return value

    def __contains__(self, name):
        return self.get(name) is not None


class _CheckoutRequest:
    def __init__(self, request, data, key):
        object.__setattr__(self, "_request", request)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "headers", _ItemHeaders(request.headers, key))

    def __getattr__(self, name):
        return getattr(self._request, name)


def _error_detail(exc) -> str:
    detail = getattr(exc, "detail", None)
    return str(detail if detail is not None else exc)


class PosBatchSyncView(APIView):
    # The same gates as the single pos_checkout: an expired subscription or a role without
    # payment rights must not get a way around them by syncing a batch.
    permission_classes = [IsAuthenticated, HasCompany, SubscriptionWritesAllowed, CanCreateSales, CanCreatePayments]

    def post(self, request):
        company = get_company_user(request).company
        checkouts = request.data.get("checkouts")
        if not isinstance(checkouts, list) or not checkouts:
            raise BusinessRuleError("checkouts must be a non-empty list.")
        if len(checkouts) > MAX_CHECKOUTS:
            raise BusinessRuleError(f"At most {MAX_CHECKOUTS} offline checkouts can sync at once.")
        from sales.views import SalesInvoiceViewSet

        results = []
        errors = []
        for index, item in enumerate(checkouts):
            if not isinstance(item, dict):
                errors.append({"index": index, "detail": "Each checkout must be an object."})
                continue
            key = str(item.get("idempotency_key") or "").strip()
            if not key:
                errors.append({"index": index, "detail": "Each checkout needs its own idempotency_key."})
                continue
            view = SalesInvoiceViewSet()
            view.request = _CheckoutRequest(request, item, key)
            view.kwargs = {}
            view.format_kwarg = None
            view.action = "pos_checkout"
            try:
                with transaction.atomic():
                    response = view.pos_checkout(view.request)
            except (BusinessRuleError, APIException) as exc:
                errors.append({"index": index, "idempotency_key": key, "detail": _error_detail(exc)})
                continue
            if response.status_code >= 400:
                errors.append({
                    "index": index, "idempotency_key": key, "detail": str(getattr(response, "data", "")),
                })
                continue
            results.append(response.data)
        body = {"company": company.pk, "results": results, "errors": errors}
        return Response(body, status=207 if errors else 201)
