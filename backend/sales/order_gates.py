"""Sales-order confirmation gates. Invoice and POS keep their own credit check."""

from __future__ import annotations

from decimal import Decimal

from core.exceptions import BusinessRuleError
from core.services.feature_flags import flag_enabled
from core.services.flag_observability import log_flag_event
from ledgers.services import LedgerService

MARGIN_THRESHOLD = Decimal("0.05")


def sales_order_exposure(company, customer, order) -> Decimal:
    """Posted exposure plus other open orders and drafts, including this order."""
    from sales.models import SalesOrder

    posted = LedgerService.customer_exposure_for_credit_limit(company, customer)
    others = SalesOrder.objects.filter(
        company=company,
        customer=customer,
        status__in=(SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED),
    ).exclude(pk=order.pk)
    extra = sum((row.grand_total or Decimal("0") for row in others), Decimal("0"))
    return posted + extra + (order.grand_total or Decimal("0"))


def margin_warnings(order, items) -> list[dict]:
    warnings = []
    for item in items:
        price = Decimal(str(item.unit_price or 0))
        cost = Decimal(str(getattr(item.product, "purchase_price", 0) or 0))
        if cost <= 0 or price <= 0:
            continue
        margin = (price - cost) / price
        if margin < MARGIN_THRESHOLD:
            warnings.append({
                "product_id": item.product_id,
                "product_name": item.product.name,
                "margin": str(margin.quantize(Decimal("0.0001"))),
            })
    return warnings


def apply_order_gates(order, items) -> list[dict]:
    """Hard-block credit. Return margin warnings and still allow confirmation."""
    if not flag_enabled(order.company, "ENABLE_ORDER_GATES"):
        return []
    log_flag_event(order.company, "ENABLE_ORDER_GATES", "order_gate_checked", order_id=order.id)
    limit = Decimal(str(order.customer.credit_limit or 0))
    if limit > 0:
        exposure = sales_order_exposure(order.company, order.customer, order)
        if exposure > limit:
            raise BusinessRuleError(
                f"Credit limit exceeded. Exposure {exposure} > limit {limit}.",
                code="credit_limit_exceeded",
            )
    warnings = margin_warnings(order, items)
    order._gate_warnings = warnings
    return warnings
