"""Planning: explosion, cost roll-up, availability, material requirements, make-to-order (MFG-14..19)."""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError
from inventory.models import StockBalance, WarehouseReorderLevel
from inventory.services import InventoryValuationService

from manufacturing.models import Bom, MrpLine, MrpRun, WorkOrder

from . import bom as bom_svc
from .common import ZERO, d, next_number, qty3, required_qty, rule, unit_factor
from .reservation import held_for

MAX_DEPTH = 10


def _try_bom(company, product, on_date=None, customer=None):
    try:
        return bom_svc.resolve_bom(company, product, on_date, customer)
    except BusinessRuleError:
        return None


# --- explosion, where-used, cost roll-up (MFG-14) ----------------------------------------------

def explode(company, product, qty=1, on_date=None, customer=None, *, expand="all"):
    """The indented list of what ``qty`` of ``product`` needs, level by level.

    ``expand`` is "all" (open every sub-assembly that has a recipe), "phantom" (only kits) or
    "none" (one level). Returns rows with ``level``, ``product``, ``qty``, ``parent`` and
    ``has_bom``. Iterative, with the path tracked so a loop is refused, never run away.
    """
    root_bom = bom_svc.resolve_bom(company, product, on_date, customer)
    rows = []
    stack = [(root_bom, d(qty), 1, (product.pk,), product.pk)]
    while stack:
        bom, need, level, path, parent = stack.pop()
        if level > MAX_DEPTH:
            raise rule("The recipe goes deeper than 10 levels.", "MFG_BOM_TOO_DEEP")
        children = []
        for line in bom.lines.select_related("component", "unit"):
            factor = unit_factor(line.component, line.unit)
            line_qty = required_qty(
                line.qty, bom.output_qty, need, scrap_pct=line.scrap_pct, factor=factor, yield_pct=bom.yield_pct,
            )
            sub = _try_bom(company, line.component, on_date)
            row = {
                "level": level, "product": line.component, "qty": line_qty, "parent": parent,
                "has_bom": sub is not None, "phantom": line.is_phantom, "optional": line.is_optional,
                "unit": line.unit.short_name if line.unit_id else "",
            }
            rows.append(row)
            open_it = sub is not None and (expand == "all" or (expand == "phantom" and line.is_phantom))
            if open_it:
                if line.component.pk in path:
                    raise rule("This BOM contains a cycle.", "MFG_BOM_CYCLE")
                children.append((sub, line_qty, level + 1, path + (line.component.pk,), line.component.pk))
        # Depth-first, in the recipe's own order.
        stack.extend(reversed(children))
    return rows


def where_used(company, component, *, only_default=True):
    """Every recipe that uses ``component``, directly or through a sub-assembly, up to the top."""
    seen, out, frontier = {component.pk}, [], [(component, 1)]
    while frontier:
        comp, level = frontier.pop(0)
        if level > MAX_DEPTH:
            continue
        lines = Bom.objects.filter(
            company=company, status=Bom.Status.ACTIVE, lines__component=comp,
        )
        if only_default:
            lines = lines.filter(is_default=True)
        for bom in lines.select_related("product").distinct():
            line = bom.lines.get(component=comp)
            out.append({
                "level": level, "bom_id": bom.pk, "product_id": bom.product_id, "product": bom.product.name,
                "qty_per_batch": line.qty, "batch_size": bom.output_qty,
            })
            if bom.product_id not in seen:
                seen.add(bom.product_id)
                frontier.append((bom.product, level + 1))
    return out


def _unit_cost_now(company, product, method):
    if method == "PURCHASE_PRICE":
        return d(product.purchase_price)
    cost = d(InventoryValuationService.unit_cost(company, product))
    return cost if cost > 0 else d(product.purchase_price)


def rollup_cost(company, product, qty=1, on_date=None, customer=None, method="CURRENT"):
    """What a unit of ``product`` costs to make from its recipe, down through its sub-assemblies.

    Materials are valued by ``method`` (CURRENT stock cost, falling back to the master price, or
    PURCHASE_PRICE). Flat extra cost per batch or unit is added when the item has it.
    """
    memo: dict[int, Decimal] = {}

    def unit_cost_of(prod, depth, path):
        if prod.pk in memo:
            return memo[prod.pk]
        if depth > MAX_DEPTH:
            raise rule("The recipe goes deeper than 10 levels.", "MFG_BOM_TOO_DEEP")
        bom = _try_bom(company, prod, on_date, customer if depth == 0 else None)
        if bom is None:
            cost = _unit_cost_now(company, prod, method)
        else:
            if prod.pk in path:
                raise rule("This BOM contains a cycle.", "MFG_BOM_CYCLE")
            total = ZERO
            for line in bom.lines.select_related("component", "unit"):
                factor = unit_factor(line.component, line.unit)
                need = required_qty(
                    line.qty, bom.output_qty, 1, scrap_pct=line.scrap_pct, factor=factor, yield_pct=bom.yield_pct,
                )
                total += need * unit_cost_of(line.component, depth + 1, path + (prod.pk,))
            for extra in bom.additional_costs.all():
                total += d(extra.amount) if extra.basis == "PER_UNIT" else d(extra.amount) / d(bom.output_qty)
            cost = total
        memo[prod.pk] = cost
        return cost

    unit = unit_cost_of(product, 0, ())
    return {"product": product.pk, "unit_cost": unit.quantize(Decimal("0.0001")), "total": (unit * d(qty)).quantize(Decimal("0.01"))}


# --- availability (MFG-15) ---------------------------------------------------------------------

def _free_stock(company, product):
    """On hand less holds placed for other reasons, across ordinary godowns."""
    kinds = ("NORMAL",)
    agg = StockBalance.objects.filter(
        company=company, product=product, warehouse__kind__in=kinds, warehouse__is_system=False,
    ).aggregate(on_hand=Sum("on_hand"), reserved=Sum("reserved"))
    return d(agg["on_hand"]), d(agg["reserved"])


def work_order_availability(wo):
    """Per material: needed, held for this order, free to take, short, and the substitutes in stock."""
    rows = []
    for line in wo.component_lines.select_related("component").filter(alternate_of__isnull=True):
        need = d(line.qty_remaining)
        if need <= 0 or line.principal_supplied:
            continue
        on_hand, reserved = _free_stock(wo.company, line.component)
        held = held_for(wo, line.component)
        free = on_hand - reserved + held            # the order's own hold is available to it
        short = max(ZERO, need - free)
        row = {
            "line_id": line.pk, "product": line.component, "need": need, "held": held, "free": max(ZERO, free),
            "short": short, "alternates": [],
        }
        if short > 0:
            for alt in line.alternates.order_by("alternate_priority", "id").select_related("component"):
                a_on, a_res = _free_stock(wo.company, alt.component)
                if a_on - a_res > 0:
                    row["alternates"].append({"product": alt.component, "free": a_on - a_res})
        rows.append(row)
    return rows


def max_producible(company, product, on_date=None, customer=None):
    """The most units of ``product`` the stock on hand can make now, and what limits it.

    A kit (phantom) is never in stock; it is opened into what it is made of, so the answer is
    limited by the real materials underneath it.
    """
    rows = explode(company, product, 1, on_date, customer, expand="phantom")
    per_unit: dict[int, tuple] = {}
    for row in rows:
        if row["optional"] or (row["phantom"] and row["has_bom"]):
            continue
        item = row["product"]
        prev = per_unit.get(item.pk)
        per_unit[item.pk] = (item, (prev[1] if prev else ZERO) + d(row["qty"]))
    best, limiting = None, None
    for item, need in per_unit.values():
        if need <= 0:
            continue
        on_hand, reserved = _free_stock(company, item)
        can = max(ZERO, on_hand - reserved) / need
        if best is None or can < best:
            best, limiting = can, item
    return {
        "product": product.pk, "qty": qty3(best if best is not None else ZERO).quantize(Decimal("0.001")),
        "limited_by": limiting.pk if limiting else None,
        "limited_by_name": limiting.name if limiting else "",
    }


def open_order_shortages(company):
    """Give the stock on hand to open work orders in due-date order and report who is left short."""
    pools: dict[int, Decimal] = {}
    out = []
    orders = (
        WorkOrder.objects.filter(company=company, status__in=["RELEASED", "IN_PROGRESS"])
        .order_by("due_date", "priority", "id").prefetch_related("component_lines__component")
    )
    for wo in orders:
        lines = []
        for line in wo.component_lines.filter(alternate_of__isnull=True):
            need = d(line.qty_remaining)
            if need <= 0 or line.principal_supplied:
                continue
            if line.component_id not in pools:
                on_hand, reserved = _free_stock(company, line.component)
                other_holds = reserved - held_for_all(company, line.component)
                pools[line.component_id] = max(ZERO, on_hand - other_holds)
            take = min(need, pools[line.component_id])
            pools[line.component_id] -= take
            if need - take > 0:
                lines.append({"product": line.component, "need": need, "allocated": take, "short": need - take})
        if lines:
            out.append({"work_order": wo, "lines": lines})
    return out


def held_for_all(company, component) -> Decimal:
    """Everything open work orders are holding of a component."""
    from inventory.models import StockReservation

    agg = StockReservation.objects.filter(
        company=company, product=component, reference_type="work_order", released_at__isnull=True,
    ).aggregate(t=Sum("quantity"))
    return d(agg["t"])


# --- material requirements (MFG-16) ------------------------------------------------------------

def _lead_time(company, product) -> int:
    row = WarehouseReorderLevel.objects.filter(company=company, product=product).order_by("-lead_time_days").first()
    return int(row.lead_time_days) if row else 0


def _safety(company, product) -> Decimal:
    agg = WarehouseReorderLevel.objects.filter(company=company, product=product).aggregate(t=Sum("safety_stock_qty"))
    return d(agg["t"])


def _preferred_supplier(company, product):
    from purchases.models import PurchaseItem

    item = (
        PurchaseItem.objects.filter(invoice__company=company, product=product, invoice__supplier__isnull=False)
        .select_related("invoice__supplier").order_by("-invoice__invoice_date", "-id").first()
    )
    return item.invoice.supplier if item else None


def _sales_demand(company, horizon_end):
    """{product_id: [(date, qty, source)]} for undelivered lines of open sales orders."""
    from sales.models import SalesOrder, SalesOrderItem

    out = defaultdict(list)
    items = SalesOrderItem.objects.filter(
        sales_order__company=company,
        sales_order__status__in=[SalesOrder.Status.CONFIRMED, SalesOrder.Status.PARTIALLY_CONVERTED],
    ).select_related("sales_order")
    for it in items:
        left = d(it.quantity) - max(d(it.shipped_quantity), d(it.invoiced_quantity))
        if left <= 0:
            continue
        when = it.sales_order.expected_delivery or it.sales_order.order_date
        if horizon_end and when > horizon_end:
            continue
        out[it.product_id].append((when, left, f"SO {it.sales_order.number or it.sales_order_id}"))
    return out


def _work_order_demand_and_supply(company):
    """Demand for materials from open orders, and the output they will bring."""
    demand, supply = defaultdict(list), defaultdict(Decimal)
    for wo in WorkOrder.objects.filter(company=company, status__in=["RELEASED", "IN_PROGRESS"]):
        when = wo.due_date or wo.planned_start or timezone.localdate()
        for line in wo.component_lines.filter(alternate_of__isnull=True):
            left = d(line.qty_remaining)
            if left > 0 and not line.principal_supplied:
                demand[line.component_id].append((when, left, f"WO {wo.number}"))
        planned = d(wo.qty) - d(wo.qty_completed) - d(wo.qty_rework) - d(wo.qty_rejected)
        if planned > 0 and wo.product_id:
            supply[wo.product_id] += planned
    return demand, supply


def _open_po_supply(company):
    from purchases.models import PurchaseOrder, PurchaseOrderItem

    out = defaultdict(Decimal)
    for it in PurchaseOrderItem.objects.filter(purchase_order__company=company, purchase_order__status=PurchaseOrder.Status.DRAFT):
        out[it.product_id] += d(it.quantity)
    return out


def _low_levels(company, products):
    """Depth of each product in the recipe tree (0 = never a component). Planning goes top-down."""
    parents = defaultdict(set)
    for bom in Bom.objects.filter(company=company, status=Bom.Status.ACTIVE, is_default=True).prefetch_related("lines"):
        for line in bom.lines.all():
            parents[line.component_id].add(bom.product_id)
    memo: dict[int, int] = {}

    def level(pid, trail=()):
        if pid in memo:
            return memo[pid]
        if pid in trail:
            raise rule("This BOM contains a cycle.", "MFG_BOM_CYCLE")
        lv = 0
        for par in parents.get(pid, ()):
            lv = max(lv, 1 + level(par, trail + (pid,)))
        memo[pid] = lv
        return lv

    return {pid: level(pid) for pid in products}


@transaction.atomic
def run_mrp(company, user, *, horizon_days=30, as_of=None) -> MrpRun:
    """Net what is wanted against what is on hand and coming, then suggest buying or making the rest.

    Read-only until a line is converted: it writes the run and its lines and nothing else. A new
    run supersedes the last one.
    """
    from masters.models import Product

    as_of = as_of or timezone.localdate()
    horizon_end = as_of + timedelta(days=int(horizon_days)) if horizon_days else None
    MrpRun.objects.filter(company=company, status=MrpRun.Status.DONE).update(status=MrpRun.Status.SUPERSEDED)
    run = MrpRun.objects.create(
        company=company, number=next_number(company, "mfg_mrp", "MRP"), as_of=as_of, horizon_days=horizon_days,
        parameters={"horizon_days": horizon_days}, created_by=user, updated_by=user,
    )
    demand = defaultdict(list)
    for pid, items in _sales_demand(company, horizon_end).items():
        demand[pid].extend(items)
    wo_demand, wo_supply = _work_order_demand_and_supply(company)
    for pid, items in wo_demand.items():
        demand[pid].extend(items)
    po_supply = _open_po_supply(company)

    # Every product that has demand, or that sits under a recipe we will explode.
    products = {p.pk: p for p in Product.objects.filter(company=company, pk__in=list(demand.keys()))}
    levels = _low_levels(company, list(products.keys()) or [])
    queue_levels = defaultdict(list)
    for pid in products:
        queue_levels[levels.get(pid, 0)].append(pid)

    lines, done = [], set()
    level = 0
    while True:
        batch = [pid for pid in queue_levels.get(level, []) if pid not in done]
        if not batch:
            if any(lv > level for lv in queue_levels):
                level += 1
                continue
            break
        for pid in batch:
            done.add(pid)
            product = products[pid]
            events = sorted(demand.get(pid, []), key=lambda e: e[0])
            gross = sum((e[1] for e in events), ZERO)
            safety = _safety(company, product)
            on_hand, _reserved = _free_stock(company, product)
            incoming = po_supply.get(pid, ZERO) + wo_supply.get(pid, ZERO)
            net = max(ZERO, gross + safety - on_hand - incoming)
            if net <= 0:
                continue
            need_date = events[0][0] if events else as_of
            lead = _lead_time(company, product)
            bom = _try_bom(company, product, need_date)
            kind = MrpLine.Kind.MAKE if bom is not None else MrpLine.Kind.PURCHASE
            lines.append(MrpLine(
                run=run, company=company, product=product, kind=kind, level=level, need_date=need_date,
                order_by=need_date - timedelta(days=lead), lead_time_days=lead, gross_qty=gross,
                safety_qty=safety, on_hand_qty=on_hand, incoming_qty=incoming, net_qty=net, suggested_qty=net,
                supplier=_preferred_supplier(company, product) if kind == MrpLine.Kind.PURCHASE else None,
                sources=[{"date": str(e[0]), "qty": str(e[1]), "source": e[2]} for e in events][:20],
            ))
            if bom is not None:
                # Making it creates demand for its materials, one step down, on the date it must start.
                start = need_date - timedelta(days=lead)
                for row in explode(company, product, net, need_date, expand="none"):
                    if row["optional"]:
                        continue
                    comp = row["product"]
                    demand[comp.pk].append((start, row["qty"], f"Making {product.sku or product.name}"))
                    if comp.pk not in products:
                        products[comp.pk] = comp
                        lv = _low_levels(company, [comp.pk]).get(comp.pk, level + 1)
                        queue_levels[max(lv, level + 1)].append(comp.pk)
        level += 1
        if level > MAX_DEPTH + 2:
            break
    MrpLine.objects.bulk_create(lines)
    run.summary = {
        "lines": len(lines),
        "purchase": sum(1 for ln in lines if ln.kind == MrpLine.Kind.PURCHASE),
        "make": sum(1 for ln in lines if ln.kind == MrpLine.Kind.MAKE),
    }
    run.save(update_fields=["summary", "updated_at"])
    return run


@transaction.atomic
def convert_mrp_lines(run, user, line_ids=None, supplier_overrides=None):
    """Turn suggestions into draft purchase orders (one per supplier) and draft work orders."""
    from purchases.models import PurchaseOrder
    from purchases.notes_services import PurchaseNotesService

    supplier_overrides = supplier_overrides or {}
    company = run.company
    lines = list(
        MrpLine.objects.select_for_update(of=("self",)).filter(run=run, status=MrpLine.LineStatus.OPEN)
        .select_related("product", "supplier")
    )
    if line_ids is not None:
        wanted = {int(i) for i in line_ids}
        lines = [ln for ln in lines if ln.pk in wanted]
    made_pos, made_wos, skipped = [], [], []
    by_supplier = defaultdict(list)
    for ln in lines:
        if ln.kind == MrpLine.Kind.PURCHASE:
            supplier = None
            if supplier_overrides.get(ln.pk):
                from masters.models import Supplier

                supplier = Supplier.objects.filter(pk=supplier_overrides[ln.pk], company=company).first()
            supplier = supplier or ln.supplier
            if supplier is None:
                ln.status, ln.note = MrpLine.LineStatus.SKIPPED, "No supplier on record; choose one."
                ln.save(update_fields=["status", "note"])
                skipped.append(ln.pk)
                continue
            by_supplier[supplier.pk].append((supplier, ln))
        else:
            bom = bom_svc.resolve_bom(company, ln.product, ln.need_date)
            wo = WorkOrder.objects.create(
                company=company, bom=bom, qty=ln.suggested_qty, due_date=ln.need_date, planned_start=ln.order_by,
                issue_mode=_default_mode(company), number=next_number(company, "mfg_wo", "WO"),
                notes=f"From {run.number}", created_by=user, updated_by=user,
            )
            from .legacy import _snapshot_bom

            _snapshot_bom(wo)
            bom_svc.lock_bom(bom)
            ln.status, ln.converted_type, ln.converted_id = MrpLine.LineStatus.CONVERTED, "WorkOrder", wo.pk
            ln.save(update_fields=["status", "converted_type", "converted_id"])
            made_wos.append(wo)
    for entries in by_supplier.values():
        supplier = entries[0][0]
        po = PurchaseOrder.objects.create(
            company=company, supplier=supplier, expected_delivery=min(
                (ln.need_date for _s, ln in entries if ln.need_date), default=None,
            ), notes=f"From {run.number}", created_by=user, updated_by=user,
        )
        PurchaseNotesService.set_order_items(
            po, [{"product": ln.product, "quantity": ln.suggested_qty} for _s, ln in entries], user,
        )
        for _s, ln in entries:
            ln.status, ln.converted_type, ln.converted_id = MrpLine.LineStatus.CONVERTED, "PurchaseOrder", po.pk
            ln.save(update_fields=["status", "converted_type", "converted_id"])
        made_pos.append(po)
    return {"purchase_orders": made_pos, "work_orders": made_wos, "skipped": skipped}


def _default_mode(company):
    from .common import get_settings

    return get_settings(company).default_issue_mode


# --- make to order, available to promise (MFG-17) ------------------------------------------------

@transaction.atomic
def create_orders_from_sales_order(sales_order, user):
    """A work order for each undelivered line that has a recipe, pegged to that line.

    A line that already has enough open work orders pegged to it is left alone, so asking twice
    does not double the plan. Returns ``(created, skipped)``.
    """
    company = sales_order.company
    created, skipped = [], []
    for item in sales_order.items.select_related("product"):
        left = d(item.quantity) - max(d(item.shipped_quantity), d(item.invoiced_quantity))
        if left <= 0:
            continue
        pegged = WorkOrder.objects.filter(
            company=company, sales_order_item=item,
        ).exclude(status__in=["CANCELLED"]).aggregate(t=Sum("qty"))["t"] or ZERO
        need = left - d(pegged)
        if need <= 0:
            skipped.append({"item": item.pk, "reason": "Already planned"})
            continue
        bom = _try_bom(company, item.product, sales_order.expected_delivery, sales_order.customer)
        if bom is None:
            skipped.append({"item": item.pk, "reason": "No recipe"})
            continue
        wo = WorkOrder.objects.create(
            company=company, bom=bom, qty=need, sales_order=sales_order, sales_order_item=item,
            due_date=sales_order.expected_delivery, issue_mode=_default_mode(company),
            number=next_number(company, "mfg_wo", "WO"), created_by=user, updated_by=user,
            notes=f"For sales order {sales_order.number or sales_order.pk}",
        )
        from .legacy import _snapshot_bom

        _snapshot_bom(wo)
        bom_svc.lock_bom(bom)
        created.append(wo)
    return created, skipped


def production_status_for_order(sales_order):
    """For each line of a sales order: ordered, shipped, planned in production, made, and when."""
    rows = []
    for item in sales_order.items.select_related("product"):
        wos = list(WorkOrder.objects.filter(sales_order_item=item).exclude(status="CANCELLED"))
        rows.append({
            "item": item.pk, "product": item.product.name, "ordered": d(item.quantity),
            "shipped": max(d(item.shipped_quantity), d(item.invoiced_quantity)),
            "planned": sum((d(w.qty) for w in wos), ZERO),
            "made": sum((d(w.qty_completed) for w in wos), ZERO),
            "expected": max((w.due_date for w in wos if w.due_date), default=None),
            "work_orders": [{"id": w.pk, "number": w.number, "status": w.status, "due_date": w.due_date} for w in wos],
        })
    return rows


def available_to_promise(company, product, as_of):
    """What can be promised for a date: stock now plus what is coming by then, less what is already spoken for."""
    # Holds on finished goods are mostly confirmed sales orders, which are counted as demand below,
    # so stock on hand is the supply.
    on_hand, _reserved = _free_stock(company, product)
    supply = on_hand
    for wo in WorkOrder.objects.filter(
        company=company, product=product, status__in=["RELEASED", "IN_PROGRESS"], due_date__lte=as_of,
    ):
        supply += max(ZERO, d(wo.qty) - d(wo.qty_completed) - d(wo.qty_rework) - d(wo.qty_rejected))
    demand = sum(
        (qty for when, qty, _src in _sales_demand(company, as_of).get(product.pk, []) if when <= as_of), ZERO,
    )
    return {"product": product.pk, "as_of": as_of, "supply": supply, "committed": demand, "available": max(ZERO, supply - demand)}


# --- the production board (MFG-19) -------------------------------------------------------------

def board(company, *, today=None):
    """Open work orders with the flags a planner scans for: late, due soon, short of material."""
    today = today or timezone.localdate()
    out = []
    orders = (
        WorkOrder.objects.filter(company=company, status__in=["DRAFT", "RELEASED", "IN_PROGRESS", "COMPLETED"])
        .select_related("product").order_by("due_date", "priority", "id")
    )
    for wo in orders:
        short = False
        if wo.status in ("RELEASED", "IN_PROGRESS"):
            short = any(r["short"] > 0 for r in work_order_availability(wo))
        late = bool(wo.due_date and wo.due_date < today and wo.status != "COMPLETED")
        out.append({
            "id": wo.pk, "number": wo.number, "product": wo.product.name if wo.product_id else "",
            "qty": wo.qty, "qty_done": wo.qty_completed, "status": wo.status, "priority": wo.priority,
            "due_date": wo.due_date, "late": late,
            "due_soon": bool(wo.due_date and not late and wo.due_date <= today + timedelta(days=2) and wo.status != "COMPLETED"),
            "short_material": short, "delay_reason": wo.delay_reason,
        })
    return out
