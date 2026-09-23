"""Trip profit snapshot at route Complete (COMP-005).

Frozen at completion. Later returns, credit notes, or invoices do not rewrite it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .cogs_service import CogsService
from .models import DeliveryRouteStop, SalesInvoice

# F1-004: only a genuinely-realized sale counts toward trip revenue/COGS. A
# CANCELLED invoice (order stays CONVERTED-linked per the invoice-cancel
# unlink exclusion in sales/services.py) or a fully-RETURNED invoice (whose
# taxable_total is never reduced by the return flow) must not be counted as
# if the sale still stood.
_REALIZED_INVOICE_STATUSES = frozenset({SalesInvoice.Status.COMPLETED})

# F1-004: a delivery that failed or came back must not count as realized
# revenue even if its order has a (still-COMPLETED) converted invoice — the
# goods didn't move, so the trip didn't actually earn that line.
_UNREALIZED_STOP_STATUSES = frozenset(
    {DeliveryRouteStop.StopStatus.FAILED, DeliveryRouteStop.StopStatus.RETURNED}
)


@dataclass
class RouteFinancials:
    realized_revenue: Decimal
    realized_cogs: Decimal
    realized_profit: Decimal
    invoiced_stop_count: int
    stop_count: int


def _q2(value: Decimal) -> Decimal:
    # BILL-05 convention: ROUND_HALF_UP, matching every other money
    # quantize() in this codebase (sales/services.py, tax_engine/india.py) —
    # not the Decimal context default (ROUND_HALF_EVEN), which would round a
    # half-paise figure differently here than everywhere else in the app.
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_route_financials(route) -> RouteFinancials:
    stops = list(route.stops.select_related("sales_order__converted_invoice"))
    revenue = Decimal("0")
    cogs = Decimal("0")
    invoiced = 0
    for stop in stops:
        invoice = getattr(stop.sales_order, "converted_invoice", None)
        if invoice is None:
            continue
        if invoice.status not in _REALIZED_INVOICE_STATUSES:
            # Cancelled or fully-returned — treat like "not invoiced" for
            # revenue/COGS purposes; still not counted as realized.
            continue
        if stop.status in _UNREALIZED_STOP_STATUSES:
            # Delivery failed or was returned on arrival — the invoice may
            # still be COMPLETED (not reversed same-day), but this trip did
            # not actually realize that sale.
            continue
        invoiced += 1
        revenue += Decimal(str(invoice.taxable_total or 0))
        for move in CogsService.invoice_sale_moves(invoice):
            cogs += Decimal(str(move.unit_cost or 0)) * abs(Decimal(str(move.quantity or 0)))
    logistics = Decimal(str(route.actual_logistics_cost or 0))
    return RouteFinancials(
        realized_revenue=_q2(revenue),
        realized_cogs=_q2(cogs),
        realized_profit=_q2(revenue - cogs - logistics),
        invoiced_stop_count=invoiced,
        stop_count=len(stops),
    )
