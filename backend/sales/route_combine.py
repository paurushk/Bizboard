"""Advise combining same-day pending stops that share a customer pincode."""

from __future__ import annotations

from collections import defaultdict

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user
from core.services.feature_flags import flag_enabled
from sales.models import DeliveryRouteStop


def combine_suggestions(company) -> list[dict] | None:
    if not flag_enabled(company, "ENABLE_ROUTE_OPTIMIZATION"):
        return None
    stops = (
        DeliveryRouteStop.objects.filter(
            company=company,
            status=DeliveryRouteStop.StopStatus.PENDING,
        )
        .select_related("sales_order", "sales_order__customer", "route")
    )
    groups = defaultdict(list)
    for stop in stops:
        order = stop.sales_order
        customer = order.customer
        pincode = (getattr(customer, "pincode", "") or "").strip()
        if not pincode:
            continue
        day = order.expected_delivery or order.order_date
        groups[(day.isoformat(), pincode)].append(stop)
    suggestions = []
    for (day, pincode), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        suggestions.append({
            "date": day,
            "pincode": pincode,
            "stop_ids": [stop.id for stop in members],
            "order_ids": [stop.sales_order_id for stop in members],
            "route_ids": sorted({stop.route_id for stop in members}),
        })
    return suggestions


class RouteCombineView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        company = get_company_user(request).company
        rows = combine_suggestions(company)
        if rows is None:
            return Response({"detail": "Not found."}, status=404)
        return Response({"suggestions": rows, "count": len(rows)})
