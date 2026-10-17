"""Tenant-scoped statistical demand forecast. Method and window are on every row.

INV-WP-10 / INV-IDR-08: one definition of "how fast does this sell" used by this page, by Purchase
planning and by the days-to-stockout figure, so they agree.

The pace is units sold less sales returns, divided by the days the item was actually in stock during
the window (a day counts when the item had stock at the start or end of it, or sold something). An item that
was out of stock for half the window therefore shows its real selling pace instead of half of it. When
there is too little history (fewer than ``MIN_IN_STOCK_DAYS`` such days) the flat mean over the whole
window is used and the row says so in ``method``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import CanViewInventorySurfaces, HasCompany, get_company_user
from inventory import planning_settings as ps
from inventory.models import MovementType, StockBalance, StockMovement

# Defaults. A company can change them (see planning_settings).
WINDOW_DAYS = 30
METHOD = "trailing_mean_net"
METHOD_IN_STOCK = "in_stock_days_mean"
# How many days of sales a suggested order should cover (stock on hand and on order counts first).
COVER_DAYS = 30
# A reorder level that covers this many days of sales (lead time plus a little safety).
REORDER_COVER_DAYS = 14
# Fewer in-stock days than this and the pace is not trusted: use the flat mean over the window.
MIN_IN_STOCK_DAYS = 7
MAX_LOOKBACK_DAYS = 90
# An item with this many days of cover, or none sold in the lookback, is overstock.
OVERSTOCK_COVER_DAYS = 180
OVERSTOCK_LOOKBACK_DAYS = 90


class DemandForecastView(APIView):
    # INV-WP-04: same gate as the Demand forecast route (not VIEWER).
    permission_classes = [IsAuthenticated, HasCompany, CanViewInventorySurfaces]

    def get(self, request):
        company = get_company_user(request).company
        return Response({"rows": demand_forecast(company), "overstock": overstock_rows(company)})


def window_days(company) -> int:
    return min(ps.number_setting(company, ps.FORECAST_WINDOW_DAYS), MAX_LOOKBACK_DAYS)


def _pace(company, *, by_godown: bool, product_ids=None, warehouse_ids=None, as_of=None, days=None):
    """{key: (rate_per_day, net_sold, in_stock_days, method)} for items that sold in the window.

    ``key`` is the product id, or ``(product id, warehouse id)`` when ``by_godown``.
    """
    as_of = as_of or timezone.localdate()
    lookback = min(days or window_days(company), MAX_LOOKBACK_DAYS)
    first_day = as_of - timedelta(days=lookback - 1)
    group = ("product_id", "warehouse_id") if by_godown else ("product_id",)

    def key_of(row):
        return (row["product_id"], row["warehouse_id"]) if by_godown else row["product_id"]

    moves = StockMovement.objects.filter(company=company, movement_date__gte=first_day, movement_date__lte=as_of)
    balances = StockBalance.objects.filter(company=company)
    if product_ids is not None:
        moves = moves.filter(product_id__in=list(product_ids))
        balances = balances.filter(product_id__in=list(product_ids))
    if warehouse_ids is not None:
        moves = moves.filter(warehouse_id__in=list(warehouse_ids))
        balances = balances.filter(warehouse_id__in=list(warehouse_ids))

    net_sold: dict = defaultdict(Decimal)
    sale_days: dict = defaultdict(set)
    daily_net: dict = defaultdict(lambda: defaultdict(Decimal))
    for row in moves.values(*group, "movement_date", "movement_type").annotate(qty=Sum("quantity")).order_by():
        key = key_of(row)
        qty = Decimal(row["qty"] or 0)
        daily_net[key][row["movement_date"]] += qty
        if row["movement_type"] in (MovementType.SALE, MovementType.SALES_RETURN):
            # SALE is stored negative (stock out), SALES_RETURN positive: the signed sum is minus net sold.
            net_sold[key] -= qty
        if row["movement_type"] == MovementType.SALE:
            sale_days[key].add(row["movement_date"])

    sellers = [k for k, v in net_sold.items() if v > 0]
    if not sellers:
        return {}
    on_hand: dict = defaultdict(Decimal)
    for row in balances.values(*group).annotate(qty=Sum("on_hand")).order_by():
        on_hand[key_of(row)] += Decimal(row["qty"] or 0)

    out = {}
    for key in sellers:
        per_day = daily_net[key]
        balance = on_hand[key] - sum(per_day.values(), Decimal("0"))  # stock at the start of the window
        in_stock = 0
        day = first_day
        while day <= as_of:
            after = balance + per_day.get(day, Decimal("0"))
            # In stock if it had stock when the day began or ended (a delivery counts), or it sold.
            if balance > 0 or after > 0 or day in sale_days[key]:
                in_stock += 1
            balance = after
            day += timedelta(days=1)
        if in_stock >= MIN_IN_STOCK_DAYS:
            rate, method = net_sold[key] / Decimal(in_stock), METHOD_IN_STOCK
        else:
            rate, method = net_sold[key] / Decimal(lookback), METHOD
        out[key] = (rate.quantize(Decimal("0.001")), net_sold[key], in_stock, method)
    return out


def item_sales(company, product_ids=None, *, as_of=None, days: int | None = None) -> dict[int, Decimal]:
    """Net units sold per product over the trailing window: sales less sales returns."""
    return {
        pid: details[1]
        for pid, details in _pace(company, by_godown=False, product_ids=product_ids, as_of=as_of, days=days).items()
    }


def item_velocity(company, product_ids=None, *, as_of=None, days: int | None = None) -> dict[int, Decimal]:
    """Net units sold per day per product (only products that sold), company-wide."""
    return {
        pid: details[0]
        for pid, details in _pace(company, by_godown=False, product_ids=product_ids, as_of=as_of, days=days).items()
    }


def godown_velocity(company, warehouse_ids, product_ids=None, *, as_of=None, days: int | None = None):
    """The same pace at one godown: ``{(product id, warehouse id): units per day}``."""
    return {
        key: details[0]
        for key, details in _pace(
            company, by_godown=True, product_ids=product_ids, warehouse_ids=warehouse_ids, as_of=as_of, days=days,
        ).items()
    }


def demand_forecast(company, *, as_of=None):
    from inventory.planning import _whole_units_only
    from inventory.reorder_maps import last_completed_suppliers, open_order_quantities
    from masters.models import Product, Supplier

    as_of = as_of or timezone.localdate()
    window = window_days(company)
    cover_days = ps.number_setting(company, ps.FORECAST_COVER_DAYS)
    reorder_days = ps.number_setting(company, ps.REORDER_COVER_DAYS)
    since = as_of - timedelta(days=window - 1)
    pace = _pace(company, by_godown=False, as_of=as_of)
    if not pace:
        return []
    ids = list(pace)
    # Inactive items and items that are not stocked are not something to reorder.
    products = {
        p.id: p
        for p in Product.objects.filter(
            company=company, pk__in=ids, status=Product.Status.ACTIVE, track_inventory=True,
        ).select_related("unit")
    }
    available = {
        row["product_id"]: row["qty"] or Decimal("0")
        for row in StockBalance.objects.filter(company=company, product_id__in=ids)
        .values("product_id")
        .annotate(qty=Sum("on_hand") - Sum("reserved"))
        .order_by()
    }
    on_order, _stale = open_order_quantities(company, ids)
    suppliers = last_completed_suppliers(company, ids)
    supplier_names = dict(Supplier.objects.filter(pk__in=set(suppliers.values())).values_list("id", "name"))

    out = []
    for pid, (daily, qty, in_stock_days, method) in pace.items():
        product = products.get(pid)
        if product is None:
            continue
        have = Decimal(available.get(pid, 0))
        ordered = Decimal(on_order.get(pid, 0))
        cover = (have / daily).to_integral_value() if daily > 0 else None
        wanted = daily * Decimal(cover_days) - have - ordered
        if wanted < 0:
            wanted = Decimal("0")
        wanted = wanted.quantize(Decimal("0.001"))
        reorder_level = (daily * Decimal(reorder_days)).quantize(Decimal("0.001"))
        if _whole_units_only(product):
            reorder_level = reorder_level.to_integral_value(rounding=ROUND_CEILING)
            if wanted > 0:
                wanted = wanted.to_integral_value(rounding=ROUND_CEILING)
        supplier_id = suppliers.get(pid)
        out.append({
            "product_id": pid,
            "product_name": product.name,
            "unit": getattr(getattr(product, "unit", None), "short_name", "") or "",
            "method": method,
            "window_days": window,
            "in_stock_days": in_stock_days,
            "window_start": since.isoformat(),
            "window_end": as_of.isoformat(),
            "sold_qty": str(qty),
            "daily_rate": str(daily),
            "available": str(have),
            "on_order": str(ordered),
            "days_of_cover": int(cover) if cover is not None else None,
            "cover_days_target": cover_days,
            "suggested_qty": str(wanted),
            "suggested_reorder_level": str(reorder_level),
            "reorder_cover_days": reorder_days,
            "needs_action": wanted > 0,
            "supplier_id": supplier_id,
            "supplier_name": supplier_names.get(supplier_id, "") if supplier_id else "",
        })
    # Needs action first, then the least cover.
    out.sort(
        key=lambda r: (
            not r["needs_action"],
            r["days_of_cover"] if r["days_of_cover"] is not None else 10**6,
            r["product_name"],
        )
    )
    return out


def overstock_rows(company, *, as_of=None):
    """Stocked items that are not moving: more than ``OVERSTOCK_COVER_DAYS`` of cover, or stock
    on hand and nothing sold in the last ``OVERSTOCK_LOOKBACK_DAYS`` days."""
    from masters.models import Product

    as_of = as_of or timezone.localdate()
    on_hand = {
        row["product_id"]: row["qty"] or Decimal("0")
        for row in StockBalance.objects.filter(company=company)
        .values("product_id").annotate(qty=Sum("on_hand") - Sum("reserved")).order_by()
        if (row["qty"] or 0) > 0
    }
    if not on_hand:
        return []
    pace = _pace(company, by_godown=False, product_ids=list(on_hand), as_of=as_of, days=OVERSTOCK_LOOKBACK_DAYS)
    products = {
        p.id: p
        for p in Product.objects.filter(
            company=company, pk__in=list(on_hand), status=Product.Status.ACTIVE, track_inventory=True,
        ).select_related("unit")
    }
    out = []
    for pid, have in on_hand.items():
        product = products.get(pid)
        if product is None:
            continue
        daily = pace[pid][0] if pid in pace else Decimal("0")
        cover = int((have / daily).to_integral_value()) if daily > 0 else None
        if cover is not None and cover <= OVERSTOCK_COVER_DAYS:
            continue
        out.append({
            "product_id": pid,
            "product_name": product.name,
            "unit": getattr(getattr(product, "unit", None), "short_name", "") or "",
            "available": str(have),
            "daily_rate": str(daily),
            "days_of_cover": cover,
            "no_sales": cover is None,
            "lookback_days": OVERSTOCK_LOOKBACK_DAYS,
        })
    out.sort(key=lambda r: (not r["no_sales"], -(r["days_of_cover"] or 0), r["product_name"]))
    return out
