"""BOM revisions, resolution and validation (MFG-03, MFG-04)."""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from manufacturing.models import Bom, BomLine

from .common import ZERO, d, rule


def assert_no_bom_cycle(company, root_product_id, component_ids, *, ignore_bom_id=None):
    """Refuse a component path that walks back to the finished good.

    Called before a BOM is saved and before a work order issues components.
    """
    root_id = getattr(root_product_id, "pk", root_product_id)
    pending = []
    for component in component_ids:
        cid = getattr(component, "pk", component)
        if cid == root_id:
            raise rule("A BOM cannot list its finished good as a component.", "MFG_BOM_SELF_COMPONENT")
        pending.append(cid)
    children = {}
    rows = BomLine.objects.filter(bom__company=company, bom__status=Bom.Status.ACTIVE)
    if ignore_bom_id:
        rows = rows.exclude(bom_id=ignore_bom_id)
    for parent_id, child_id in rows.values_list("bom__product_id", "component_id"):
        children.setdefault(parent_id, set()).add(child_id)
    children[root_id] = set(pending)
    stack = [(root_id, {root_id})]
    while stack:
        node, path = stack.pop()
        for child in children.get(node, ()):
            if child in path:
                raise rule("This BOM contains a cycle.", "MFG_BOM_CYCLE")
            stack.append((child, path | {child}))


# --- resolution ------------------------------------------------------------------------------

def resolve_bom(company, product, on_date=None, customer=None) -> Bom:
    """The one way code picks a BOM for a product.

    A customer-specific revision wins over the generic one. Among revisions whose dates
    cover ``on_date``, the one that took effect last wins; a tie goes to the default, then
    the highest revision number.
    """
    on_date = on_date or timezone.localdate()
    base = Bom.objects.filter(company=company, product=product, status=Bom.Status.ACTIVE)

    def pick(qs):
        rows = [
            b for b in qs
            if (b.effective_from is None or b.effective_from <= on_date)
            and (b.effective_to is None or b.effective_to >= on_date)
        ]
        if not rows:
            return None
        rows.sort(key=lambda b: (b.effective_from or on_date.min, b.is_default, b.revision_no))
        return rows[-1]

    found = None
    if customer is not None:
        found = pick(base.filter(customer=customer))
    if found is None:
        found = pick(base.filter(customer__isnull=True))
    if found is None:
        raise rule(f"'{product.name}' has no active BOM for {on_date}.", "MFG_NO_ACTIVE_BOM")
    return found


# --- revisions -------------------------------------------------------------------------------

def next_revision_no(company, product) -> int:
    last = (
        Bom.objects.filter(company=company, product=product)
        .order_by("-revision_no").values_list("revision_no", flat=True).first()
    )
    return (last or 0) + 1


def lock_bom(bom: Bom) -> None:
    """A BOM that a work order used is read-only (its recipe is part of that order's history)."""
    if bom.locked_at is None:
        Bom.objects.filter(pk=bom.pk, locked_at__isnull=True).update(locked_at=timezone.now())
        bom.locked_at = timezone.now()


def assert_editable(bom: Bom) -> None:
    if bom.is_locked:
        raise rule(
            "This BOM revision has been used by a work order and can no longer be changed. "
            "Make a new revision instead.",
            "MFG_BOM_LOCKED",
        )


@transaction.atomic
def create_revision(bom: Bom, user, reason: str = "") -> Bom:
    """Copy ``bom`` (lines, outputs, extra costs) into the next revision, as a DRAFT."""
    source = Bom.objects.select_for_update().get(pk=bom.pk)
    new = Bom.objects.create(
        company=source.company, product=source.product, name=source.name, status=Bom.Status.DRAFT,
        revision_no=next_revision_no(source.company, source.product),
        customer=source.customer, parent_revision=source, change_reason=(reason or "")[:500],
        output_qty=source.output_qty, yield_pct=source.yield_pct, fg_warehouse=source.fg_warehouse,
        notes=source.notes, created_by=user, updated_by=user,
    )
    for line in source.lines.all():
        BomLine.objects.create(
            bom=new, company=source.company, component=line.component, qty=line.qty, unit=line.unit,
            scrap_pct=line.scrap_pct, issue_method=line.issue_method, is_optional=line.is_optional,
            is_phantom=line.is_phantom, alternate_group=line.alternate_group, alternate_priority=line.alternate_priority,
            source_warehouse=line.source_warehouse, sequence=line.sequence, notes=line.notes,
        )
    for out in source.outputs.all():
        out.pk = None
        out.bom = new
        out.save()
    for cost in source.additional_costs.all():
        cost.pk = None
        cost.bom = new
        cost.save()
    return new


@transaction.atomic
def activate_revision(bom: Bom, user, *, make_default: bool = True, effective_from=None) -> Bom:
    """Make ``bom`` ACTIVE and (by default) the default for its product and customer.

    The revision it replaces has its window closed the day before this one starts. A new
    revision cannot start before an ACTIVE revision that already started later.
    """
    bom = Bom.objects.select_for_update().get(pk=bom.pk)
    if not bom.lines.exists():
        raise rule("A recipe needs at least one material before it can be used.", "MFG_BOM_EMPTY")
    today = timezone.localdate()
    start = effective_from or bom.effective_from or today
    siblings = list(
        Bom.objects.select_for_update()
        .filter(company=bom.company, product=bom.product, customer=bom.customer, status=Bom.Status.ACTIVE)
        .exclude(pk=bom.pk)
    )
    for other in siblings:
        if other.effective_from and other.effective_from > start:
            raise rule(
                f"Revision {other.revision_no} already starts on {other.effective_from}. "
                "A new revision cannot start before it.",
                "MFG_REVISION_OVERLAP",
            )
    for other in siblings:
        # A revision that started earlier ends the day before this one starts. One that started the
        # same day keeps its window (two recipes in force at once is allowed, as it always was); the
        # default decides which one new work orders get.
        starts_same_day = other.effective_from == start
        if not starts_same_day and (other.effective_to is None or other.effective_to >= start):
            other.effective_to = start - timedelta(days=1)
        if make_default:
            other.is_default = False
        other.updated_by = user
        other.save(update_fields=["effective_to", "is_default", "updated_by", "updated_at"])
    bom.status = Bom.Status.ACTIVE
    bom.effective_from = start
    if make_default:
        bom.is_default = True
    bom.updated_by = user
    bom.save(update_fields=["status", "effective_from", "is_default", "updated_by", "updated_at"])
    return bom


@transaction.atomic
def archive_revision(bom: Bom, user) -> Bom:
    bom = Bom.objects.select_for_update().get(pk=bom.pk)
    bom.status = Bom.Status.ARCHIVED
    bom.is_default = False
    bom.updated_by = user
    bom.save(update_fields=["status", "is_default", "updated_by", "updated_at"])
    return bom


# --- validation ------------------------------------------------------------------------------

def validate_content(company, product, lines, outputs, *, output_qty=None, yield_pct=None):
    """Check a BOM payload before anything is written (B8-002: validate, then write).

    ``lines`` and ``outputs`` are lists of dicts with model instances for foreign keys.
    """
    if output_qty is not None and d(output_qty) <= 0:
        raise rule("BOM batch size must be greater than zero.", "MFG_BAD_BATCH_SIZE")
    if yield_pct is not None and not (ZERO < d(yield_pct) <= Decimal("100")):
        raise rule("Yield must be above 0 and at most 100 percent.", "MFG_BAD_YIELD")
    assert_no_bom_cycle(company, product, [ln.get("component") for ln in lines])
    for ln in lines:
        comp = ln.get("component")
        unit = ln.get("unit")
        if unit is not None:
            allowed = {getattr(comp, "unit_id", None), getattr(comp, "alternate_unit_id", None)} - {None}
            if unit.pk not in allowed:
                raise rule(
                    f"Unit '{unit.short_name}' is not a unit of '{comp.name}'. "
                    "Use its own unit or its alternate unit.",
                    "MFG_BAD_LINE_UNIT",
                )
        scrap = d(ln.get("scrap_pct") or 0)
        if not (ZERO <= scrap < Decimal("100")):
            raise rule("Scrap percentage must be from 0 to under 100.", "MFG_BAD_SCRAP_PCT")
    component_ids = {ln["component"].pk for ln in lines}
    shares = ZERO
    for out in outputs:
        prod = out.get("product")
        kind = out.get("kind")
        if prod.pk == product.pk:
            raise rule("An output cannot be the finished good itself.", "MFG_OUTPUT_IS_MAIN")
        if prod.pk in component_ids:
            raise rule(f"'{prod.name}' is both a component and an output of this BOM.", "MFG_OUTPUT_IS_COMPONENT")
        share = d(out.get("cost_share_pct") or 0)
        if kind == "CO_PRODUCT":
            shares += share
        elif share != 0:
            raise rule("By-products and scrap carry no cost share; give them a recovery rate.", "MFG_BAD_COST_SHARE")
    if shares > Decimal("100"):
        raise rule("Co-product cost shares add up to more than 100.", "MFG_BAD_COST_SHARE")


# --- snapshot with phantoms expanded ----------------------------------------------------------

MAX_PHANTOM_DEPTH = 8


def snapshot_lines(bom: Bom, wo_qty, on_date=None, *, _depth=0, _path=()) -> list[dict]:
    """The material lines for ``wo_qty`` good units of ``bom``, with phantom kits looked through.

    Each item is a dict ready to build a work order line. A phantom line (a kit that is never
    stocked) is replaced by the lines of its own recipe, scaled to what is needed.
    """
    from .common import required_qty, unit_factor

    if _depth > MAX_PHANTOM_DEPTH or bom.pk in _path:
        raise rule("A kit contains itself.", "MFG_BOM_CYCLE")
    out = []
    for line in bom.lines.select_related("component", "unit"):
        factor = unit_factor(line.component, line.unit)
        qty = required_qty(
            line.qty, bom.output_qty, wo_qty, scrap_pct=line.scrap_pct, factor=factor, yield_pct=bom.yield_pct,
        )
        if line.is_phantom:
            child = resolve_bom(bom.company, line.component, on_date)
            out.extend(snapshot_lines(child, qty, on_date, _depth=_depth + 1, _path=_path + (bom.pk,)))
            continue
        per_unit = (d(line.qty) * d(factor) / d(bom.output_qty))
        out.append({
            "component": line.component, "qty": qty, "per_unit": per_unit, "unit": line.unit,
            "scrap_pct": line.scrap_pct, "issue_method": line.issue_method, "is_optional": line.is_optional,
            "alternate_group": line.alternate_group, "alternate_priority": line.alternate_priority,
            "source_warehouse": line.source_warehouse,
        })
    return out
