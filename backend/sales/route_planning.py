"""Route planning: what a dispatcher needs to know about an order before it goes on a van (hardening plan R7).

One module owns the facts (``order_summaries``) and the rules (``RISKS`` and the evaluator), so the
planning table, the "add to route" check and the "start route" check can never disagree: they all read
this. Everything here is read-only; enforcement lives in ``RouteService``.

Risk levels
- ``block``: the order cannot be routed. None of them can be overridden (DEC-P1 revised: an unconfirmed order never goes on a route).
- ``warn``: it can go, once someone accepts the risk with a reason that is kept on the route.
- ``info``: shown for awareness, nothing to accept.

The work is done in bulk: queries grow with the number of customers and invoices involved, not with the
number of orders on the page.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

BLOCK, WARN, INFO = "block", "warn", "info"
OVERRIDE_NONE, OVERRIDE_OWNER, OVERRIDE_MANAGER, OVERRIDE_ANY = "none", "owner", "manager", "any"

NEAR_EXPIRY_DAYS = 30
ROUTABLE_STATUSES = ("CONFIRMED", "PARTIALLY_CONVERTED", "CONVERTED")

# code -> (level, who may accept it)
RISKS: dict[str, tuple[str, str]] = {
    "order_cancelled": (BLOCK, OVERRIDE_NONE),
    "already_on_route": (BLOCK, OVERRIDE_NONE),
    "already_delivered": (BLOCK, OVERRIDE_NONE),
    "customer_blocked": (BLOCK, OVERRIDE_NONE),
    "not_ready": (BLOCK, OVERRIDE_NONE),
    "empty_order": (BLOCK, OVERRIDE_NONE),
    "no_stock": (BLOCK, OVERRIDE_NONE),
    "credit_hold": (WARN, OVERRIDE_MANAGER),
    "over_credit_limit": (WARN, OVERRIDE_MANAGER),
    "customer_overdue": (WARN, OVERRIDE_ANY),
    "stock_short": (WARN, OVERRIDE_ANY),
    "expired_or_near_expiry": (WARN, OVERRIDE_ANY),
    "no_address": (WARN, OVERRIDE_ANY),
    "no_phone": (WARN, OVERRIDE_ANY),
    "eway_needed": (WARN, OVERRIDE_ANY),
    "no_pincode": (INFO, OVERRIDE_NONE),
    "low_margin": (INFO, OVERRIDE_NONE),
    "partial_delivery": (INFO, OVERRIDE_NONE),
    "late": (INFO, OVERRIDE_NONE),
    "gstin_unverified": (INFO, OVERRIDE_NONE),
    "eway_will_be_needed": (INFO, OVERRIDE_NONE),
}

_ZERO = Decimal("0")


def _q(value) -> Decimal:
    return Decimal(str(value or 0))


def _money(value) -> str:
    return str(_q(value).quantize(Decimal("0.01")))


def _fmt(value) -> str:
    from .order_quantities import fmt_qty

    return fmt_qty(value)


@dataclass
class Viewer:
    """Who is asking: what they may see, and what they may accept."""

    role: str = ""
    can_see_customer_money: bool = False
    can_see_cost: bool = False

    @property
    def is_owner(self) -> bool:
        return self.role == "OWNER"

    @property
    def is_manager(self) -> bool:
        return self.role in ("OWNER", "MANAGER")

    def may_accept(self, code: str) -> bool:
        _level, who = RISKS[code]
        if who == OVERRIDE_NONE:
            return False
        if who == OVERRIDE_OWNER:
            return self.is_owner
        if who == OVERRIDE_MANAGER:
            return self.is_manager
        return True


def viewer_from_user(company, user) -> Viewer:
    """The same facts as ``viewer_for`` for a caller that has a user but no request (a service, a task)."""
    from accounts.models import CompanyUser
    from insights.customer_360 import can_open_customer_360

    company_user = CompanyUser.objects.filter(company=company, user=user, user__is_active=True).first()
    return Viewer(
        role=getattr(company_user, "role", "") or "",
        can_see_customer_money=can_open_customer_360(company_user),
        can_see_cost=bool(
            company_user is not None and (company_user.role == "OWNER" or company_user.can_view_financial_reports)
        ),
    )


def viewer_for(request) -> Viewer:
    from core.permissions import get_company_user
    from insights.customer_360 import can_open_customer_360

    from .expected_profit import can_view_expected_profit

    company_user = get_company_user(request) if request is not None else None
    return Viewer(
        role=getattr(company_user, "role", "") or "",
        can_see_customer_money=can_open_customer_360(company_user),
        can_see_cost=can_view_expected_profit(request),
    )


def risk(code: str, message: str, **extra) -> dict:
    level, who = RISKS[code]
    return {"code": code, "level": level, "message": message, "override": who, **extra}


# ---------------------------------------------------------------------------
# bulk facts
# ---------------------------------------------------------------------------


def _group_sum(qs, order_field: str) -> dict[int, dict[int, Decimal]]:
    out: dict[int, dict[int, Decimal]] = defaultdict(dict)
    for row in qs.values(order_field, "product_id").annotate(total=Sum("quantity")):
        out[row[order_field]][row["product_id"]] = _q(row["total"])
    return out


def _bulk_quantities(company, order_ids):
    """Per order and product: shipped (net of returns) and billed directly, from the live documents."""
    from .models import (
        DeliveryChallan,
        DeliveryChallanItem,
        DeliveryChallanReturn,
        DeliveryChallanReturnItem,
        SalesInvoice,
        SalesItem,
    )

    shipped = _group_sum(
        DeliveryChallanItem.objects.filter(
            challan__company=company,
            challan__sales_order_id__in=order_ids,
            challan__status=DeliveryChallan.Status.COMPLETED,
        ),
        "challan__sales_order_id",
    )
    returned = _group_sum(
        DeliveryChallanReturnItem.objects.filter(
            challan_return__company=company,
            challan_return__challan__sales_order_id__in=order_ids,
            challan_return__status=DeliveryChallanReturn.Status.COMPLETED,
        ),
        "challan_return__challan__sales_order_id",
    )
    direct = _group_sum(
        SalesItem.objects.filter(
            invoice__company=company,
            invoice__source_order_id__in=order_ids,
            invoice__status__in=(SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED),
        ),
        "invoice__source_order_id",
    )
    for oid, by_product in returned.items():
        for pid, qty in by_product.items():
            if pid in shipped.get(oid, {}):
                shipped[oid][pid] = max(_ZERO, shipped[oid][pid] - qty)
    return shipped, direct


def _bulk_invoices(company, order_ids):
    """order id -> its live invoices (direct, or via a challan), with balances for the completed ones."""
    from ledgers.services import LedgerService

    from .models import DeliveryChallan, SalesInvoice

    by_order: dict[int, dict[int, SalesInvoice]] = defaultdict(dict)
    for inv in SalesInvoice.objects.filter(company=company, source_order_id__in=order_ids).exclude(
        status=SalesInvoice.Status.CANCELLED
    ):
        by_order[inv.source_order_id][inv.pk] = inv
    challan_links = list(
        DeliveryChallan.objects.filter(
            company=company, sales_order_id__in=order_ids, converted_invoice__isnull=False
        )
        .exclude(converted_invoice__status=SalesInvoice.Status.CANCELLED)
        .select_related("converted_invoice")
    )
    for challan in challan_links:
        by_order[challan.sales_order_id][challan.converted_invoice_id] = challan.converted_invoice
    completed_ids = [
        inv.pk
        for invoices in by_order.values()
        for inv in invoices.values()
        if inv.status in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)
    ]
    balances = LedgerService.bulk_sales_invoice_outstanding(company, completed_ids) if completed_ids else {}
    return by_order, balances


def _bulk_eway(company, order_ids) -> dict[int, set[str]]:
    """order id -> e-Way statuses on its completed challans."""
    from .models import DeliveryChallan

    out: dict[int, set[str]] = defaultdict(set)
    for oid, status in DeliveryChallan.objects.filter(
        company=company, sales_order_id__in=order_ids, status=DeliveryChallan.Status.COMPLETED
    ).values_list("sales_order_id", "eway_status"):
        out[oid].add(status)
    return out


def _bulk_stock(company, orders):
    """(warehouse id, product id) -> free stock (on hand less everything reserved)."""
    from inventory.models import StockBalance
    from inventory.services import InventoryService

    default_wh = InventoryService.default_warehouse(company)
    product_ids = {item.product_id for order in orders for item in order.items.all()}
    free: dict[tuple[int, int], Decimal] = {}
    for row in (
        StockBalance.objects.filter(company=company, product_id__in=product_ids)
        .values("warehouse_id", "product_id")
        .annotate(on_hand=Sum("on_hand"), reserved=Sum("reserved"))
    ):
        free[(row["warehouse_id"], row["product_id"])] = _q(row["on_hand"]) - _q(row["reserved"])
    return free, (default_wh.pk if default_wh is not None else None)


def _bulk_expiry(company, orders, today: date):
    """product id -> earliest expiry among lots that still hold stock, for batch-tracked products."""
    from inventory.models import StockBalance

    product_ids = {item.product_id for order in orders for item in order.items.all() if item.product.track_batch}
    out: dict[int, date] = {}
    if not product_ids:
        return out
    for row in StockBalance.objects.filter(
        company=company, product_id__in=product_ids, batch__isnull=False, on_hand__gt=0, batch__expiry_date__isnull=False
    ).values("product_id", "batch__expiry_date"):
        expiry = row["batch__expiry_date"]
        if row["product_id"] not in out or expiry < out[row["product_id"]]:
            out[row["product_id"]] = expiry
    return out


def _bulk_stops(company, order_ids, route):
    """order id -> ('on_route' | 'delivered', route) for stops that keep an order off another route."""
    from .models import DeliveryRoute, DeliveryRouteStop

    live = (DeliveryRoute.Status.PLANNED, DeliveryRoute.Status.IN_TRANSIT)
    not_out = (
        DeliveryRouteStop.StopStatus.FAILED,
        DeliveryRouteStop.StopStatus.REJECTED,
        DeliveryRouteStop.StopStatus.RETURNED,
    )
    out: dict[int, tuple[str, object]] = {}
    qs = DeliveryRouteStop.objects.filter(company=company, sales_order_id__in=order_ids).select_related("route")
    if route is not None:
        qs = qs.exclude(route_id=route.pk)
    for stop in qs.order_by("id"):
        if stop.status == DeliveryRouteStop.StopStatus.DELIVERED:
            out[stop.sales_order_id] = ("delivered", stop.route)
        elif stop.route.status in live and stop.status not in not_out and stop.sales_order_id not in out:
            out[stop.sales_order_id] = ("on_route", stop.route)
    return out


def _customer_facts(company, customers, viewer: Viewer):
    """customer id -> money position and credit flags; one pass per customer, never per order."""
    from payments.dunning import customer_risk_snapshot
    from planwave.services import chronic_overdue

    from .order_gates import sales_order_exposure

    facts = {}
    placeholder = type("NoOrder", (), {"pk": None, "grand_total": _ZERO})()
    for customer in customers:
        limit = _q(customer.credit_limit)
        snapshot = customer_risk_snapshot(company, customer)
        blocked, chronic_total = chronic_overdue(company, customer)
        exposure = sales_order_exposure(company, customer, placeholder) if limit > 0 else _ZERO
        facts[customer.pk] = {
            "snapshot": snapshot,
            "chronic_blocked": bool(blocked),
            "chronic_total": _q(chronic_total),
            "limit": limit,
            "exposure": exposure,
        }
    return facts


# ---------------------------------------------------------------------------
# the summary and its risks
# ---------------------------------------------------------------------------


def order_summaries(company, orders, *, viewer: Viewer, route=None, today: date | None = None) -> dict[int, dict]:
    """Facts and risks for each order, keyed by order id."""
    today = today or timezone.localdate()
    orders = list(orders)
    if not orders:
        return {}
    order_ids = [o.pk for o in orders]
    shipped, direct = _bulk_quantities(company, order_ids)
    invoices_by_order, balances = _bulk_invoices(company, order_ids)
    free, default_wh = _bulk_stock(company, orders)
    expiry = _bulk_expiry(company, orders, today)
    stops = _bulk_stops(company, order_ids, route)
    customers = {o.customer_id: o.customer for o in orders}.values()
    cust = _customer_facts(company, customers, viewer)
    eway_threshold = _q(getattr(company, "eway_threshold_amount", None) or 50000)
    eway = _bulk_eway(company, order_ids)

    out: dict[int, dict] = {}
    for order in orders:
        items = list(order.items.all())
        customer = order.customer
        facts = cust[order.customer_id]
        snapshot = facts["snapshot"]
        warehouse_id = order.warehouse_id or default_wh
        ordered: dict[int, Decimal] = defaultdict(lambda: _ZERO)
        for item in items:
            ordered[item.product_id] += _q(item.quantity)
        shipped_here = shipped.get(order.pk, {})
        direct_here = direct.get(order.pk, {})

        invoices = list(invoices_by_order.get(order.pk, {}).values())
        completed = [i for i in invoices if i.status in ("COMPLETED", "RETURNED")]
        owed = sum((_q(balances.get(i.pk)) for i in completed), _ZERO)
        has_challan = bool(shipped_here)
        if completed:
            bill_status, due = ("paid" if owed <= 0 else "invoiced"), owed
        elif invoices:
            bill_status, due = "draft_invoice", _q(order.grand_total)
        elif has_challan:
            bill_status, due = "challan", _q(order.grand_total)
        else:
            bill_status, due = "order_only", _q(order.grand_total)
        terms = int(order.payment_terms_days or 0)
        to_collect = _ZERO if terms > 0 else (due if due > 0 else _ZERO)

        lines = []
        stock_short_for: list[str] = []
        no_stock_for: list[str] = []
        for item in items:
            qty = _q(item.quantity)
            out_already = shipped_here.get(item.product_id, _ZERO) + direct_here.get(item.product_id, _ZERO)
            still_to_ship = max(_ZERO, ordered[item.product_id] - out_already)
            held = still_to_ship if order.stock_held else _ZERO
            available = free.get((warehouse_id, item.product_id), _ZERO) + held if item.product.track_inventory else None
            short = _ZERO
            if available is not None and still_to_ship > 0:
                short = max(_ZERO, still_to_ship - available)
            if short > 0:
                # Nothing at all on the shelf is a stop; only a partial shortage is a warning.
                bucket = no_stock_for if available <= 0 else stock_short_for
                if item.product.name not in bucket:
                    bucket.append(item.product.name)
            lines.append({
                "product": item.product_id,
                "name": item.product.name,
                "quantity": _fmt(qty),
                "unit": getattr(item.product, "unit_name", "") or "",
                "available": None if available is None else _fmt(max(_ZERO, available)),
                "short": _fmt(short) if short > 0 else "0",
            })

        risks: list[dict] = []
        status = order.status
        if status == "CANCELLED":
            risks.append(risk("order_cancelled", "This order is cancelled."))
        elif status not in ROUTABLE_STATUSES:
            risks.append(risk("not_ready", "This order is not confirmed yet, so it holds no stock. Confirm it first."))
        held_elsewhere = stops.get(order.pk)
        if held_elsewhere is not None:
            kind, other = held_elsewhere
            label = other.number or f"#{other.pk}"
            if kind == "delivered":
                risks.append(risk("already_delivered", f"Already delivered on route {label}."))
            else:
                risks.append(risk("already_on_route", f"Already on route {label}. Remove it from there first."))
        if customer.status != "ACTIVE":
            risks.append(risk("customer_blocked", f"{customer.name} is blocked or inactive."))

        money_ok = viewer.can_see_customer_money
        if facts["chronic_blocked"]:
            total = f" (₹{_money(facts['chronic_total'])})" if money_ok else ""
            risks.append(risk("credit_hold", f"Credit is on hold: invoices over 60 days overdue{total}."))
        if facts["limit"] > 0 and facts["exposure"] > facts["limit"]:
            over = facts["exposure"] - facts["limit"]
            detail = f" by ₹{_money(over)}" if money_ok else ""
            risks.append(risk("over_credit_limit", f"Customer is over their credit limit{detail}."))
        overdue = _q(snapshot.get("overdue_amount"))
        if overdue > 0 and snapshot.get("collection_status") in ("overdue", "overdue_severe"):
            detail = f": ₹{_money(overdue)} overdue" if money_ok else ""
            severe = " (more than 90 days)" if snapshot.get("collection_status") == "overdue_severe" else ""
            risks.append(risk("customer_overdue", f"Customer has overdue invoices{detail}{severe}.", severity=snapshot.get("collection_status")))
        if not any(_q(item.quantity) > 0 for item in items):
            risks.append(risk("empty_order", "This order has no items, or every quantity is zero. Fix the order first."))
        if no_stock_for:
            risks.append(risk("no_stock", "No stock at all for: " + ", ".join(no_stock_for[:4]) + ("…" if len(no_stock_for) > 4 else "") + "."))
        if stock_short_for:
            risks.append(risk("stock_short", "Not enough stock for: " + ", ".join(stock_short_for[:4]) + ("…" if len(stock_short_for) > 4 else "") + "."))
        near = [
            (item.product.name, expiry[item.product_id])
            for item in items
            if item.product_id in expiry and expiry[item.product_id] <= today + timedelta(days=NEAR_EXPIRY_DAYS)
        ]
        if near:
            name, when = near[0]
            word = "expired on" if when < today else "expires on"
            risks.append(risk("expired_or_near_expiry", f"Stock of {name} {word} {when:%d %b %Y}."))
        address = (order.delivery_address or "").strip()
        if not address:
            risks.append(risk("no_address", "No delivery address. Ask the customer before this goes out."))
        if not (customer.phone or "").strip():
            risks.append(risk("no_phone", "No phone number for the customer."))
        if not (customer.pincode or "").strip():
            risks.append(risk("no_pincode", "No pincode, so it cannot be grouped or sequenced by area."))
        value = _q(order.grand_total)
        if value >= eway_threshold:
            generated = "GENERATED" in eway.get(order.pk, set()) or any(
                getattr(i, "eway_status", "") == "GENERATED" for i in invoices
            )
            if (has_challan or invoices) and not generated:
                risks.append(risk(
                    "eway_needed",
                    f"Value ₹{_money(value)} is above ₹{_money(eway_threshold)} and no e-Way Bill is recorded: "
                    "generate it before the goods move.",
                ))
            elif not (has_challan or invoices):
                risks.append(risk(
                    "eway_will_be_needed",
                    f"Value ₹{_money(value)} is above ₹{_money(eway_threshold)}: an e-Way Bill will be needed once it is shipped.",
                ))
        if has_challan and shipped_here and ordered and any(
            shipped_here.get(pid, _ZERO) + direct_here.get(pid, _ZERO) < qty for pid, qty in ordered.items()
        ):
            risks.append(risk("partial_delivery", "Only part of the order is going: the rest is still to ship."))
        if order.expected_delivery and order.expected_delivery < today:
            days = (today - order.expected_delivery).days
            risks.append(risk("late", f"{days} day(s) past the expected delivery date."))
        if (customer.gstin or "").strip() and getattr(customer, "gstin_verification_status", "") not in ("VALID", "VERIFIED"):
            risks.append(risk("gstin_unverified", "The customer’s GSTIN has not been verified."))
        margin_note = None
        if viewer.can_see_cost:
            from .order_gates import margin_warnings

            warnings = margin_warnings(order, items)
            if warnings:
                names = ", ".join(w["product_name"] for w in warnings[:3])
                risks.append(risk("low_margin", f"Low margin on: {names}."))
                margin_note = [w["product_name"] for w in warnings]

        summary = {
            "order": order.pk,
            "number": order.number,
            "status": status,
            "order_date": order.order_date.isoformat() if order.order_date else None,
            "expected_delivery": order.expected_delivery.isoformat() if order.expected_delivery else None,
            "customer": {
                "id": customer.pk,
                "name": customer.name,
                "phone": customer.phone,
                "pincode": customer.pincode,
                "state": customer.state,
                "status": customer.status,
                # Sequencing and map grouping need coordinates; a stop without them is placed by pincode only.
                "has_location": customer.latitude is not None and customer.longitude is not None,
            },
            "delivery_address": order.delivery_address,
            "lines": lines,
            "line_count": len(lines),
            "total_quantity": _fmt(sum(ordered.values(), _ZERO)),
            "grand_total": _money(order.grand_total),
            "bill": {
                "bill_status": bill_status,
                "payment_terms_days": terms,
                "on_credit": terms > 0,
                "amount_to_collect": _money(to_collect),
                "invoices": [
                    {
                        "id": i.pk,
                        "number": i.number or "",
                        "status": i.status,
                        "grand_total": _money(i.grand_total),
                        "balance": _money(balances.get(i.pk)) if i.status in ("COMPLETED", "RETURNED") else "0.00",
                    }
                    for i in invoices
                ],
            },
            "risks": risks,
            "ready": not any(r["level"] == BLOCK for r in risks),
            "has_warnings": any(r["level"] == WARN for r in risks),
        }
        if money_ok:
            summary["money"] = {
                "outstanding": snapshot.get("outstanding"),
                "overdue": snapshot.get("overdue_amount"),
                "available_credit": snapshot.get("available_credit"),
                "collection_status": snapshot.get("collection_status"),
                "credit_limit": _money(facts["limit"]),
                "exposure": _money(facts["exposure"]) if facts["limit"] > 0 else None,
            }
        if margin_note is not None:
            summary["low_margin_products"] = margin_note
        out[order.pk] = summary
    return out


# ---------------------------------------------------------------------------
# acknowledging risks
# ---------------------------------------------------------------------------


def unresolved_risks(summary: dict, acknowledged_codes: set[str], viewer: Viewer) -> dict:
    """What still stands between this order and the route.

    ``blocked``: Blocks nobody can accept (or the viewer may not). ``needs_ack``: Warns (and an owner's
    ``not_ready``) not yet acknowledged. ``not_allowed``: risks that need a role the viewer lacks.
    """
    blocked, needs_ack, not_allowed = [], [], []
    for item in summary["risks"]:
        code, level = item["code"], item["level"]
        if level == INFO:
            continue
        if code in acknowledged_codes and viewer.may_accept(code):
            continue
        if level == BLOCK and item["override"] == OVERRIDE_NONE:
            blocked.append(item)
        elif viewer.may_accept(code):
            needs_ack.append(item)
        else:
            not_allowed.append(item)
    return {"blocked": blocked, "needs_ack": needs_ack, "not_allowed": not_allowed}


def route_totals(summaries: list[dict]) -> dict:
    """Orders, lines, quantity, value, what to collect and how many warnings, for a set of stops."""
    qty = sum((_q(s["total_quantity"]) for s in summaries), _ZERO)
    return {
        "orders": len(summaries),
        "lines": sum(s["line_count"] for s in summaries),
        "quantity": _fmt(qty),
        "value": _money(sum((_q(s["grand_total"]) for s in summaries), _ZERO)),
        "to_collect": _money(sum((_q(s["bill"]["amount_to_collect"]) for s in summaries), _ZERO)),
        "warnings": sum(1 for s in summaries for r in s["risks"] if r["level"] == WARN),
        "blocks": sum(1 for s in summaries for r in s["risks"] if r["level"] == BLOCK),
    }


# ---------------------------------------------------------------------------
# the candidate list
# ---------------------------------------------------------------------------

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def _int_param(params, name, default, *, low=1, high=None):
    raw = params.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError(f"{name} must be a whole number.") from None
    value = max(low, value)
    return min(value, high) if high else value


def _date_param(params, name):
    raw = params.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError(f"{name} must be an ISO date (YYYY-MM-DD).") from None


def planning_candidates(company, params, viewer: Viewer) -> dict:
    """One page of orders for the planning table, each with its summary and risks."""
    from django.db.models import F, Q

    from .models import DeliveryRoute, DeliveryRouteStop, SalesOrder

    statuses = list(ROUTABLE_STATUSES)
    if str(params.get("include_drafts") or "").lower() in ("1", "true", "yes"):
        statuses.append("DRAFT")
    qs = (
        SalesOrder.objects.filter(company=company, status__in=statuses)
        .select_related("customer", "warehouse")
        .prefetch_related("items__product")
    )
    if str(params.get("show_unavailable") or "").lower() not in ("1", "true", "yes"):
        busy = DeliveryRouteStop.objects.filter(company=company).filter(
            Q(status=DeliveryRouteStop.StopStatus.DELIVERED)
            | (
                Q(route__status__in=(DeliveryRoute.Status.PLANNED, DeliveryRoute.Status.IN_TRANSIT))
                & ~Q(status__in=(
                    DeliveryRouteStop.StopStatus.FAILED,
                    DeliveryRouteStop.StopStatus.REJECTED,
                    DeliveryRouteStop.StopStatus.RETURNED,
                ))
            )
        )
        qs = qs.exclude(pk__in=busy.values("sales_order_id"))
    term = (params.get("q") or "").strip()[:100]
    if term:
        qs = qs.filter(Q(number__icontains=term) | Q(customer__name__icontains=term))
    raw_ids = (params.get("ids") or "").strip()
    if raw_ids:
        # Only these orders (the ones picked on the order list): ids=12,15,18.
        try:
            qs = qs.filter(pk__in=[int(part) for part in raw_ids.split(",") if part.strip()][:200])
        except ValueError:
            from core.exceptions import BusinessRuleError

            raise BusinessRuleError("ids must be a comma-separated list of order ids.") from None
    customer = params.get("customer")
    if customer not in (None, ""):
        try:
            qs = qs.filter(customer_id=int(customer))
        except (TypeError, ValueError):
            from core.exceptions import BusinessRuleError

            raise BusinessRuleError("customer must be a numeric id.") from None
    pincode = (params.get("pincode") or "").strip()[:10]
    if pincode:
        qs = qs.filter(customer__pincode__startswith=pincode)
    date_from, date_to = _date_param(params, "date_from"), _date_param(params, "date_to")
    if date_from:
        qs = qs.filter(Q(expected_delivery__gte=date_from) | Q(expected_delivery__isnull=True, order_date__gte=date_from))
    if date_to:
        qs = qs.filter(Q(expected_delivery__lte=date_to) | Q(expected_delivery__isnull=True, order_date__lte=date_to))
    qs = qs.order_by(F("expected_delivery").asc(nulls_last=True), "order_date", "id")

    page_size = _int_param(params, "page_size", DEFAULT_PAGE_SIZE, high=MAX_PAGE_SIZE)
    page = _int_param(params, "page", 1)
    count = qs.count()
    rows = list(qs[(page - 1) * page_size: page * page_size])
    summaries = order_summaries(company, rows, viewer=viewer)
    return {
        "count": count,
        "page": page,
        "page_size": page_size,
        "results": [summaries[o.pk] for o in rows],
    }
