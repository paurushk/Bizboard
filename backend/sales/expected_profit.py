"""Expected/estimated profit from current purchase price — not FIFO invoice profit."""

from __future__ import annotations

from decimal import Decimal

from core.services.billing import q2


def can_view_expected_profit(request) -> bool:
    """Gate cost/margin exposure the same way preview-totals does (CanViewFinancialReports),
    so a role with only CanViewSalesSurfaces can't read purchase cost/margin off ordinary
    Sales Order / Quotation / Delivery Challan / Delivery Route list and retrieve calls."""
    from core.permissions import CanViewFinancialReports

    if request is None:
        return False
    return CanViewFinancialReports().has_permission(request, None)


def expected_profit_for_lines(items) -> dict:
    revenue = Decimal("0")
    cost = Decimal("0")
    for item in items:
        qty = Decimal(str(getattr(item, "quantity", 0) or 0))
        unit = Decimal(str(getattr(item, "unit_price", 0) or 0))
        discount_pct = Decimal(str(getattr(item, "discount_percent", 0) or 0))
        gross = qty * unit
        line_revenue = gross - (gross * discount_pct / Decimal("100"))
        revenue += line_revenue
        product = getattr(item, "product", None)
        purchase = Decimal(str(getattr(product, "purchase_price", 0) or 0)) if product is not None else Decimal("0")
        cost += qty * purchase
    margin = revenue - cost
    pct = q2(margin / revenue * 100) if revenue else None
    return {
        "expected_revenue": q2(revenue),
        "expected_cost": q2(cost),
        "expected_profit": q2(margin),
        "expected_margin_percent": pct,
        "label": "Expected/Estimated Profit",
        "basis": "current_purchase_price",
    }


def expected_profit_for_order(order) -> dict:
    # Plain .all() (not .select_related(...).all()) so a queryset-level
    # prefetch_related("items__product") on the caller's viewset is reused
    # instead of triggering a fresh, unprefetched query per document.
    items = list(order.items.all())
    payload = expected_profit_for_lines(items)
    payload["sales_order_id"] = order.id
    return payload


def expected_profit_for_quotation(quotation) -> dict:
    items = list(quotation.items.all())
    payload = expected_profit_for_lines(items)
    payload["quotation_id"] = quotation.id
    return payload


def expected_profit_for_challan(challan) -> dict:
    items = list(challan.items.all())
    payload = expected_profit_for_lines(items)
    payload["delivery_challan_id"] = challan.id
    return payload
