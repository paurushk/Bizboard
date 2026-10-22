"""Manufacturing reports (MFG-09, 30, 31, 32 and the report pack in MFG-X2).

Every report reads the cached money on the work order or the posted documents; none of them sums
the stock ledger on the fly except the reconciliation, whose whole job is to compare the two.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from inventory.models import MovementType, StockBalance, StockMovement
from manufacturing.models import (
    DocumentStatus, MaterialIssueLine, ProductionReceiptLine, WorkOrder, WorkOrderVariance,
)

from .common import ZERO, d, money

OPEN = ["RELEASED", "IN_PROGRESS"]


def _span(date_from, date_to):
    return date_from or date(1900, 1, 1), date_to or date(2999, 12, 31)


def wip_report(company, as_of=None):
    """Open orders with their cost in work in progress, and how long it has sat there."""
    as_of = as_of or timezone.localdate()
    rows, buckets = [], {"0-7": ZERO, "8-30": ZERO, "31-90": ZERO, "90+": ZERO}
    qs = WorkOrder.objects.filter(company=company).filter(
        Q(status__in=OPEN) | Q(status="COMPLETED", issue_mode="SEPARATE")
    ).select_related("product")
    for wo in qs:
        wip = d(wo.wip_value)
        started = wo.released_at or wo.created_at.date()
        age = (as_of - started).days
        bucket = "0-7" if age <= 7 else "8-30" if age <= 30 else "31-90" if age <= 90 else "90+"
        buckets[bucket] += wip
        rows.append({
            "id": wo.pk, "number": wo.number, "product": wo.product.name if wo.product_id else "",
            "status": wo.status, "issued": wo.cost_issued, "returned": wo.cost_returned,
            "absorbed": wo.cost_absorbed, "received": wo.cost_received, "variance": wo.cost_variance,
            "wip": money(wip), "age_days": age, "bucket": bucket, "due_date": wo.due_date,
        })
    rows.sort(key=lambda r: -r["age_days"])
    return {"as_of": as_of, "total_wip": money(sum((r["wip"] for r in rows), ZERO)), "buckets": {k: money(v) for k, v in buckets.items()}, "orders": rows}


def work_order_cost_report(company, date_from=None, date_to=None):
    """Planned against actual for orders completed in the period."""
    lo, hi = _span(date_from, date_to)
    rows = []
    qs = WorkOrder.objects.filter(
        company=company, status__in=["COMPLETED", "CLOSED"], completed_at__gte=lo, completed_at__lte=hi,
    ).select_related("product")
    for wo in qs:
        made = d(wo.qty_completed) + d(wo.qty_rework)
        planned = d(wo.estimated_unit_cost) * d(wo.qty)
        actual = d(wo.cost_issued) - d(wo.cost_returned) + d(wo.cost_absorbed)
        rows.append({
            "id": wo.pk, "number": wo.number, "product": wo.product.name if wo.product_id else "", "qty_planned": wo.qty,
            "qty_made": made, "planned_cost": money(planned), "actual_cost": money(actual),
            "difference": money(actual - planned),
            "unit_cost": money(actual / made) if made else None,
            "yield_pct": (made * 100 / d(wo.qty)).quantize(Decimal("0.1")) if d(wo.qty) else None,
        })
    return {"from": date_from, "to": date_to, "orders": rows}


def variance_report(company, date_from=None, date_to=None):
    """Material usage against what the output should have used, per item."""
    lo, hi = _span(date_from, date_to)
    agg = defaultdict(lambda: {"standard_qty": ZERO, "actual_qty": ZERO, "standard_cost": ZERO, "actual_cost": ZERO, "variance": ZERO, "orders": 0})
    qs = WorkOrderVariance.objects.filter(
        company=company, kind="USAGE", work_order__closed_at__gte=lo, work_order__closed_at__lte=hi,
    ).select_related("component")
    for v in qs:
        row = agg[v.component_id]
        row["name"] = v.component.name if v.component_id else ""
        for k in ("standard_qty", "actual_qty", "standard_cost", "actual_cost", "variance"):
            row[k] += d(getattr(v, k))
        row["orders"] += 1
    residual = WorkOrderVariance.objects.filter(
        company=company, kind="RESIDUAL", work_order__closed_at__gte=lo, work_order__closed_at__lte=hi,
    ).aggregate(t=Sum("variance"))["t"]
    return {
        "from": date_from, "to": date_to,
        "items": sorted(({**v, "component": k} for k, v in agg.items()), key=lambda r: -abs(r["variance"])),
        "residual_to_variance_account": money(residual),
    }


def yield_wastage_report(company, date_from=None, date_to=None):
    lo, hi = _span(date_from, date_to)
    rows = []
    for wo in WorkOrder.objects.filter(
        company=company, status__in=["COMPLETED", "CLOSED"], completed_at__gte=lo, completed_at__lte=hi,
    ).select_related("product"):
        made = d(wo.qty_completed) + d(wo.qty_rework) + d(wo.qty_rejected)
        rows.append({
            "id": wo.pk, "number": wo.number, "product": wo.product.name if wo.product_id else "",
            "planned": wo.qty, "good": wo.qty_completed, "rework": wo.qty_rework, "rejected": wo.qty_rejected,
            "yield_pct": (d(wo.qty_completed) * 100 / made).quantize(Decimal("0.1")) if made else None,
            "rejection_pct": (d(wo.qty_rejected) * 100 / made).quantize(Decimal("0.1")) if made else None,
        })
    scrap = (
        ProductionReceiptLine.objects.filter(
            company=company, receipt__status=DocumentStatus.POSTED, kind__in=["BY_PRODUCT", "SCRAP"],
            receipt__doc_date__gte=lo, receipt__doc_date__lte=hi,
        ).values("product__name", "kind").annotate(qty=Sum("qty_good"), value=Sum("cost_amount"))
    )
    return {"orders": rows, "scrap_and_byproducts": [
        {"product": r["product__name"], "kind": r["kind"], "qty": d(r["qty"]), "value": money(r["value"])} for r in scrap
    ]}


def consumption_report(company, date_from=None, date_to=None):
    lo, hi = _span(date_from, date_to)
    rows = (
        MaterialIssueLine.objects.filter(
            company=company, issue__status=DocumentStatus.POSTED, issue__doc_date__gte=lo, issue__doc_date__lte=hi,
        ).values("component_id", "component__name").annotate(qty=Sum("qty"), cost=Sum("cost_amount"), issues=Count("id"))
        .order_by("-cost")
    )
    return {"items": [{"product": r["component_id"], "name": r["component__name"], "qty": d(r["qty"]), "cost": money(r["cost"]), "issues": r["issues"]} for r in rows]}


def output_report(company, date_from=None, date_to=None):
    lo, hi = _span(date_from, date_to)
    rows = (
        ProductionReceiptLine.objects.filter(
            company=company, receipt__status=DocumentStatus.POSTED, receipt__doc_date__gte=lo, receipt__doc_date__lte=hi,
        ).values("product_id", "product__name", "kind").annotate(good=Sum("qty_good"), rejected=Sum("qty_rejected"), rework=Sum("qty_rework"), value=Sum("cost_amount"))
        .order_by("product__name")
    )
    return {"items": [
        {"product": r["product_id"], "name": r["product__name"], "kind": r["kind"], "good": d(r["good"]),
         "rejected": d(r["rejected"]), "rework": d(r["rework"]), "value": money(r["value"])} for r in rows
    ]}


def on_time_report(company, date_from=None, date_to=None, today=None):
    """Orders finished by their due date, and orders still open past it."""
    lo, hi = _span(date_from, date_to)
    today = today or timezone.localdate()
    done = WorkOrder.objects.filter(
        company=company, status__in=["COMPLETED", "CLOSED"], completed_at__gte=lo, completed_at__lte=hi, due_date__isnull=False,
    )
    on_time = sum(1 for wo in done if wo.completed_at <= wo.due_date)
    late_open = WorkOrder.objects.filter(
        company=company, status__in=OPEN + ["DRAFT"], due_date__lt=today,
    ).count()
    n = done.count()
    return {
        "finished_with_due_date": n, "on_time": on_time,
        "on_time_pct": (Decimal(on_time) * 100 / n).quantize(Decimal("0.1")) if n else None, "open_and_late": late_open,
        "delay_reasons": list(
            WorkOrder.objects.filter(company=company).exclude(delay_reason="").values("delay_reason").annotate(n=Count("id")).order_by("-n")
        ),
    }


# --- profitability (MFG-30) -----------------------------------------------------------------

def profitability(company, date_from=None, date_to=None, by="product"):
    """Revenue less cost of goods for finished goods sold, grouped by product, batch or customer.

    Revenue is each invoice line's taxable value for the quantity that left stock; cost is what that
    stock cost (the SALE movement's stamped cost). Lines without a stock movement are not here.
    """
    from sales.models import SalesInvoice

    lo, hi = _span(date_from, date_to)
    made_ids = set(
        WorkOrder.objects.filter(company=company).exclude(product=None).values_list("product_id", flat=True)
    )
    moves = StockMovement.objects.filter(
        company=company, movement_type=MovementType.SALE, reference_type="sales_invoice",
        movement_date__gte=lo, movement_date__lte=hi, product_id__in=made_ids,
    ).select_related("product", "batch")
    inv_ids = {int(m.reference_id) for m in moves if str(m.reference_id).isdigit()}
    invoices = {i.pk: i for i in SalesInvoice.objects.filter(company=company, pk__in=inv_ids).select_related("customer").prefetch_related("items")}
    book = defaultdict(lambda: {"qty": ZERO, "revenue": ZERO, "cost": ZERO})
    for m in moves:
        inv = invoices.get(int(m.reference_id)) if str(m.reference_id).isdigit() else None
        if inv is None:
            continue
        items = [it for it in inv.items.all() if it.product_id == m.product_id]
        item_qty = sum((d(it.quantity) for it in items), ZERO)
        if item_qty <= 0:
            continue
        qty = abs(d(m.quantity))
        revenue = sum((d(it.taxable_amount) for it in items), ZERO) * qty / item_qty
        if by == "batch":
            key = (m.batch.batch_no if m.batch_id else "(no batch)", m.product.name)
        elif by == "customer":
            key = (inv.customer.name if inv.customer_id else "(walk-in)", "")
        else:
            key = (m.product.name, "")
        row = book[key]
        row["qty"] += qty
        row["revenue"] += revenue
        row["cost"] += qty * d(m.unit_cost)
    out = []
    for (name, extra), r in book.items():
        profit = r["revenue"] - r["cost"]
        out.append({
            "name": name, "detail": extra, "qty": r["qty"], "revenue": money(r["revenue"]), "cost": money(r["cost"]),
            "profit": money(profit), "margin_pct": (profit * 100 / r["revenue"]).quantize(Decimal("0.1")) if r["revenue"] else None,
        })
    return {"by": by, "rows": sorted(out, key=lambda r: -r["profit"])}


def scrap_register(company, date_from=None, date_to=None):
    """Scrap and by-product: what came out of production, what was sold or written off, what is on hand."""
    lo, hi = _span(date_from, date_to)
    received = (
        ProductionReceiptLine.objects.filter(
            company=company, receipt__status=DocumentStatus.POSTED, kind__in=["BY_PRODUCT", "SCRAP"],
            receipt__doc_date__gte=lo, receipt__doc_date__lte=hi,
        ).values("product_id", "product__name").annotate(qty=Sum("qty_good"), value=Sum("cost_amount"))
    )
    rows = []
    for r in received:
        on_hand = StockBalance.objects.filter(company=company, product_id=r["product_id"]).aggregate(t=Sum("on_hand"))["t"]
        sold = StockMovement.objects.filter(
            company=company, product_id=r["product_id"], movement_type=MovementType.SALE, movement_date__gte=lo, movement_date__lte=hi,
        ).aggregate(t=Sum("quantity"))["t"]
        rows.append({
            "product": r["product_id"], "name": r["product__name"], "made": d(r["qty"]), "recovery_value": money(r["value"]),
            "sold": abs(d(sold)), "on_hand": d(on_hand),
        })
    return {"items": rows}


# --- reconciliation (MFG-32) --------------------------------------------------------------------

def reconciliation(company, as_of=None):
    """Compare the books with the shop floor: WIP, stock by stage, material at job workers."""
    from accounting.models import JournalLine
    from inventory.services import InventoryValuationService

    as_of = as_of or timezone.localdate()

    def gl_net(code):
        agg = JournalLine.objects.filter(
            entry__company=company, entry__status__in=["POSTED", "REVERSED"], entry__entry_date__lte=as_of,
            account__code=code,
        ).aggregate(dr=Sum("debit"), cr=Sum("credit"))
        return d(agg["dr"]) - d(agg["cr"])

    orders = WorkOrder.objects.filter(company=company).exclude(status="CANCELLED")
    wip_sub = sum((d(wo.wip_value) for wo in orders), ZERO)
    wip_gl = gl_net("1450")
    rows = InventoryValuationService.valuation(company)
    total_val = ZERO
    by_role: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_kind: dict[str, Decimal] = defaultdict(lambda: ZERO)
    from masters.models import Product
    from inventory.models import Warehouse

    roles = dict(Product.objects.filter(company=company).values_list("pk", "mfg_role"))
    kinds = dict(Warehouse.all_objects.filter(company=company).values_list("pk", "kind"))
    for row in rows:
        value = d(row.get("value"))
        total_val += value
        by_role[roles.get(row.get("product"), "") or "(unclassified)"] += value
        by_kind[kinds.get(row.get("warehouse"), "NORMAL")] += value
    inv_gl = gl_net("1400")
    from jobwork.models import JobWorkChallanLine

    at_jw = sum(
        (d(ln.qty_open) * d(ln.unit_cost) for ln in JobWorkChallanLine.objects.filter(
            company=company, challan__status="ISSUED", challan__order__direction="OUT").select_related("challan")),
        ZERO,
    )
    jw_stock = by_kind.get("JOB_WORKER", ZERO)
    return {
        "as_of": as_of,
        "wip": {"gl_1450": money(wip_gl), "work_orders": money(wip_sub), "difference": money(wip_gl - wip_sub)},
        "inventory": {
            "gl_1400": money(inv_gl), "valuation": money(total_val), "difference": money(inv_gl - total_val),
            "by_stage": {k: money(v) for k, v in sorted(by_role.items())},
            "by_godown_kind": {k: money(v) for k, v in sorted(by_kind.items())},
        },
        "job_work": {"challans_open_value": money(at_jw), "stock_at_job_workers": money(jw_stock), "difference": money(jw_stock - at_jw)},
    }
