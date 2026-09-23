"""Churn and repeat-order Attention rows from completed sales orders."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Avg
from django.utils import timezone

MIN_ORDERS = 3
MIN_HISTORY_DAYS = 60
CADENCE_MULTIPLE = Decimal("1.5")
APPROACH_FRACTION = Decimal("0.20")
SAMPLE_ORDERS = 6


def _median_gap(dates: list) -> int | None:
    if len(dates) < 2:
        return None
    ordered = sorted(dates)
    gaps = [(ordered[i] - ordered[i - 1]).days for i in range(1, len(ordered))]
    gaps = [gap for gap in gaps if gap > 0]
    if not gaps:
        return None
    return int(median(gaps))


def _history_ok(dates: list) -> bool:
    if len(dates) < MIN_ORDERS:
        return False
    span = (max(dates) - min(dates)).days
    return span >= MIN_HISTORY_DAYS


def build_customer_action_rows(company, as_of=None) -> list[dict]:
    from core.services.feature_flags import flag_enabled
    if not flag_enabled(company, "ENABLE_CUSTOMER_ACTIONS"):
        return []
    as_of = as_of or timezone.localdate()
    window_start = as_of - timedelta(days=90)
    by_customer, money_by_customer = _bounded_orders(company, window_start)

    rows: list[dict] = []
    for customer_id, history in by_customer.items():
        sample = history[:SAMPLE_ORDERS]
        dates = [row["order_date"] for row in sample]
        if not _history_ok(dates):
            continue
        cadence = _median_gap(dates)
        if not cadence:
            continue
        last = max(dates)
        name = sample[0]["customer__name"]
        gap = (as_of - last).days
        if Decimal(gap) >= CADENCE_MULTIPLE * Decimal(cadence):
            recent = money_by_customer.get(customer_id) or []
            average = (
                sum(recent, Decimal("0")) / Decimal(len(recent))
                if recent
                else Decimal("0")
            )
            rows.append(_attention(
                code="CHURN_RISK",
                title=f"{name} is past their usual order gap",
                money=average,
                reason=(
                    f"Last order was {gap} days ago. Their usual gap is {cadence} days."
                ),
                href=f"/sales/customers/{customer_id}",
                entity_id=customer_id,
                dedupe=f"CHURN_RISK:{customer_id}",
            ))

        product_dates = _product_dates(company, [row["id"] for row in sample])
        for product_id, payload in product_dates.items():
            pdates = payload["dates"]
            if not _history_ok(pdates):
                continue
            pcadence = _median_gap(pdates)
            if not pcadence:
                continue
            plast = max(pdates)
            predicted = plast + timedelta(days=pcadence)
            lead = int(Decimal(pcadence) * APPROACH_FRACTION)
            window_open = predicted - timedelta(days=lead)
            if not (window_open <= as_of <= predicted):
                continue
            typical = _typical_product_value(company, customer_id, product_id)
            rows.append(_attention(
                code="REPEAT_ORDER_DUE",
                title=f"{name} is due to reorder {payload['name']}",
                money=typical,
                reason=(
                    f"Usual reorder gap for this product is {pcadence} days. "
                    f"The next order is expected on {predicted.isoformat()}."
                ),
                href=f"/sales/orders/new?customer={customer_id}&product={product_id}",
                entity_id=product_id,
                dedupe=f"REPEAT_ORDER_DUE:{customer_id}:{product_id}",
                entity_type="product",
            ))
    return rows


def _bounded_orders(company, window_start):
    """Last six orders per customer for cadence, plus trailing-90-day totals for money.

    The attention feed used to load every confirmed order. Cadence only needs
    the latest six, and the rupee figure only needs the last 90 days.
    """
    from django.db.models import F, Window
    from django.db.models.functions import RowNumber

    from sales.models import SalesOrder

    statuses = (SalesOrder.Status.CONFIRMED, SalesOrder.Status.CONVERTED)
    base = SalesOrder.objects.filter(company=company, status__in=statuses)
    ranked = base.annotate(
        rn=Window(
            expression=RowNumber(),
            partition_by=[F("customer_id")],
            order_by=[F("order_date").desc(), F("id").desc()],
        )
    ).filter(rn__lte=SAMPLE_ORDERS)
    by_customer: dict[int, list] = {}
    for row in ranked.values("id", "customer_id", "customer__name", "order_date", "grand_total"):
        by_customer.setdefault(row["customer_id"], []).append(row)
    for history in by_customer.values():
        history.sort(key=lambda item: (item["order_date"], item["id"]), reverse=True)
    money: dict[int, list] = {}
    for row in base.filter(order_date__gte=window_start).values("customer_id", "grand_total"):
        money.setdefault(row["customer_id"], []).append(row["grand_total"])
    return by_customer, money


def _product_dates(company, order_ids: list[int]) -> dict:
    from sales.models import SalesOrderItem

    grouped: dict[int, dict] = {}
    items = (
        SalesOrderItem.objects.filter(company=company, sales_order_id__in=order_ids)
        .select_related("product", "sales_order")
    )
    for item in items:
        bucket = grouped.setdefault(
            item.product_id,
            {"name": item.product.name, "dates": []},
        )
        bucket["dates"].append(item.sales_order.order_date)
    return grouped


def _typical_product_value(company, customer_id, product_id) -> Decimal:
    from django.db.models import ExpressionWrapper, F, DecimalField
    from sales.models import SalesOrderItem

    line_total = ExpressionWrapper(
        F("quantity") * F("unit_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    value = (
        SalesOrderItem.objects.filter(
            company=company,
            product_id=product_id,
            sales_order__customer_id=customer_id,
            sales_order__status__in=("CONFIRMED", "CONVERTED"),
        )
        .annotate(line_value=line_total)
        .aggregate(avg=Avg("line_value"))
    )
    return Decimal(str(value["avg"] or 0))


def _attention(*, code, title, money, reason, href, entity_id, dedupe, entity_type="customer"):
    amount = Decimal(str(money or 0))
    return {
        "code": code,
        "severity": "warning",
        "title": title[:80],
        "money_impact_paise": int((amount * 100).to_integral_value()),
        "currency": "INR",
        "reason": reason,
        "action_label": "Review customer",
        "action_href": href,
        "source_ticket": "D1",
        "entity_ref": {"type": entity_type, "id": int(entity_id)},
        "dedupe_key": dedupe,
        "first_seen": None,
        "snooze_until": None,
    }
