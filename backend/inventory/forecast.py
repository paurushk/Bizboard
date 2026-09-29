"""Tenant-scoped statistical demand forecast. Method and window are on every row."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user
from inventory.models import MovementType, StockMovement


class DemandForecastView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        company = get_company_user(request).company
        return Response({"rows": demand_forecast(company)})


WINDOW_DAYS = 90
METHOD = "trailing_mean"


def demand_forecast(company, *, as_of=None):
    as_of = as_of or timezone.localdate()
    since = as_of - timedelta(days=WINDOW_DAYS)
    rows = (
        StockMovement.objects.filter(
            company=company,
            movement_type=MovementType.SALE,
            movement_date__gte=since,
            movement_date__lte=as_of,
        )
        .values("product_id", "product__name")
        .annotate(qty=Sum("quantity"))
    )
    out = []
    for row in rows:
        qty = abs(Decimal(row["qty"] or 0))
        daily = (qty / Decimal(WINDOW_DAYS)).quantize(Decimal("0.001"))
        out.append({
            "product_id": row["product_id"],
            "product_name": row["product__name"],
            "method": METHOD,
            "window_days": WINDOW_DAYS,
            "window_start": since.isoformat(),
            "window_end": as_of.isoformat(),
            "sold_qty": str(qty),
            "daily_rate": str(daily),
        })
    return out
