"""Shared helpers for the manufacturing services (rev 2, docs/MANUFACTURING_IMPLEMENTATION_PLAN.md)."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from core.exceptions import BusinessRuleError

Q2 = Decimal("0.01")
Q3 = Decimal("0.001")
Q4 = Decimal("0.0001")
ZERO = Decimal("0")


def d(value) -> Decimal:
    return Decimal(str(value if value is not None else 0))


def money(value) -> Decimal:
    return d(value).quantize(Q2, rounding=ROUND_HALF_UP)


def qty3(value) -> Decimal:
    return d(value).quantize(Q3, rounding=ROUND_HALF_UP)


def unit4(value) -> Decimal:
    return d(value).quantize(Q4, rounding=ROUND_HALF_UP)


def rule(message: str, code: str) -> BusinessRuleError:
    """A business-rule error with a stable code the UI and help text can key on."""
    return BusinessRuleError(message, code=code)


def get_settings(company):
    """The company's manufacturing settings row, created with defaults on first use."""
    from manufacturing.models import MfgSettings

    row = MfgSettings.objects.filter(company=company).first()
    if row is None:
        row, _ = MfgSettings.objects.get_or_create(company=company)
    return row


def next_number(company, scope: str, prefix: str) -> str:
    from core.services.sequences import next_number as _next

    return _next(company, scope, prefix=prefix)


def assert_doc_date(company, doc_date, *, allow_soft_closed=False, can_backdate=True, label="Entry") -> date:
    """Period gate plus the back-date window (§4.13). Returns the date to use.

    Stock and cost are always taken from the live ledger in posting order; the date only
    decides which period the document lands in. A date in the future is refused. A date
    older than ``backdate_days`` needs a role that may back-date.
    """
    from reporting.gst_periods import assert_period_allows_money_amend

    today = timezone.localdate()
    doc_date = doc_date or today
    if isinstance(doc_date, str):
        doc_date = date.fromisoformat(doc_date[:10])
    if doc_date > today:
        raise rule(f"{label} date cannot be in the future.", "MFG_FUTURE_DATE")
    window = get_settings(company).backdate_days
    if window is not None and doc_date < today - timedelta(days=int(window)) and not can_backdate:
        raise rule(
            f"{label} date is more than {window} days back. A manager must enter it.",
            "MFG_BACKDATE_NEEDS_MANAGER",
        )
    assert_period_allows_money_amend(company, doc_date, allow_soft_closed=allow_soft_closed)
    return doc_date


# --- warehouse resolution (§3.2) ------------------------------------------------------------

ROLE_TO_SETTING = {
    "RAW": "rm_warehouse",
    "PACKING": "rm_warehouse",
    "CONSUMABLE": "rm_warehouse",
    "SEMI_FINISHED": None,
    "FINISHED": "fg_warehouse",
    "SCRAP": "scrap_warehouse",
    "BY_PRODUCT": "scrap_warehouse",
}


def _role_default(company, product):
    role = getattr(product, "mfg_role", "") or ""
    attr = ROLE_TO_SETTING.get(role)
    if not attr:
        return None
    return getattr(get_settings(company), attr, None)


def resolve_issue_warehouse(wo, product, *, explicit=None, line=None):
    """Where a component comes from: the document line, the WO line, the role godown, the WO."""
    from inventory.services import InventoryService

    for candidate in (
        explicit,
        getattr(line, "source_warehouse", None),
        _role_default(wo.company, product),
        wo.warehouse,
    ):
        if candidate is not None:
            return candidate
    return InventoryService.default_warehouse(wo.company)


def resolve_receipt_warehouse(wo, product, *, kind="MAIN", explicit=None, output=None):
    """Where an output goes: the document line, the planned output, the BOM/WO godown, the role godown."""
    from inventory.services import InventoryService

    settings_row = get_settings(wo.company)
    kind_default = None
    if kind in ("SCRAP",):
        kind_default = settings_row.scrap_warehouse
    elif kind == "BY_PRODUCT":
        kind_default = settings_row.scrap_warehouse
    for candidate in (
        explicit,
        getattr(output, "target_warehouse", None),
        kind_default,
        wo.fg_warehouse,
        getattr(getattr(wo, "bom", None), "fg_warehouse", None),
        _role_default(wo.company, product),
        settings_row.fg_warehouse,
        wo.warehouse,
    ):
        if candidate is not None:
            return candidate
    return InventoryService.default_warehouse(wo.company)


# --- requirement maths (§4.14, MFG-04) ------------------------------------------------------

def unit_factor(product, unit) -> Decimal:
    """How many of the product's base unit one of ``unit`` is (alternate unit → conversion rate)."""
    if unit is None:
        return Decimal("1")
    alt_id = getattr(product, "alternate_unit_id", None)
    if alt_id and unit.pk == alt_id:
        raw_rate = getattr(product, "conversion_rate", None)
        rate = d(1 if raw_rate is None else raw_rate)      # a rate of 0 is a mistake, not "no conversion"
        if rate <= 0:
            raise rule("Conversion rate must be greater than zero.", "MFG_BAD_CONVERSION")
        return rate
    return Decimal("1")


def required_qty(line_qty, bom_output_qty, wo_qty, *, scrap_pct=0, factor=1, yield_pct=100) -> Decimal:
    """Base-unit quantity of a component a work order needs for ``wo_qty`` good units.

    ``line_qty`` is per ``bom_output_qty`` of output. Scrap on the line and the batch yield
    both raise the need: 98 % yield means 100 units in produce 98 good ones. Rounded once,
    at the end.
    """
    out = d(bom_output_qty)
    if out <= 0:
        raise rule("BOM batch size must be greater than zero.", "MFG_BAD_BATCH_SIZE")
    yld = d(yield_pct or 100)
    if yld <= 0:
        raise rule("Yield must be above zero.", "MFG_BAD_YIELD")
    raw = (
        d(line_qty) * (d(wo_qty) / out) * (Decimal("1") + d(scrap_pct) / Decimal("100"))
        * d(factor) * (Decimal("100") / yld)
    )
    return qty3(raw)


# --- receipt costing (§4.14) -----------------------------------------------------------------

def cost_receipt(*, pool, lines, is_final, tolerance_pct=None):
    """Value the lines of one production receipt. Pure: no database.

    ``pool`` is the work order's WIP value before this receipt (issued - returned + absorbed
    - received - variance). Each of ``lines`` is a dict with:

    * ``kind``: MAIN, CO_PRODUCT, BY_PRODUCT or SCRAP;
    * ``qty``: the stock-valued quantity this line puts into stock (good + rework + rejected
      for MAIN, since all of it carries the main product's cost);
    * ``est_unit``: the frozen estimate per unit (MAIN and CO_PRODUCT);
    * ``share``: cost share % (MAIN and CO_PRODUCT; they add up to 100);
    * ``recovery``: per-unit value for BY_PRODUCT and SCRAP (may be 0).

    Partial receipt: MAIN and CO_PRODUCT at their frozen estimate, flagged when the total
    would go beyond the pool. Final receipt: the whole remaining pool, after by-product and
    scrap recovery, split by share. With ``tolerance_pct`` set, anything above the estimate
    plus that band is taken off the MAIN line and returned as ``residual`` for the variance
    account at close.

    Returns ``(amounts, residual, exceeds_pool)``: Decimal totals in the order of ``lines``.
    """
    pool = d(pool)
    amounts = [ZERO for _ in lines]
    recovery_total = ZERO
    for i, ln in enumerate(lines):
        if ln["kind"] in ("BY_PRODUCT", "SCRAP"):
            amounts[i] = money(d(ln["qty"]) * d(ln.get("recovery") or 0))
            recovery_total += amounts[i]
    costed = [i for i, ln in enumerate(lines) if ln["kind"] in ("MAIN", "CO_PRODUCT")]
    exceeds = False
    residual = ZERO
    if is_final:
        remaining = pool - recovery_total
        if remaining < 0:
            remaining = ZERO
        shares = sum((d(lines[i].get("share") or 0) for i in costed), ZERO) or Decimal("100")
        allotted = ZERO
        last = costed[-1] if costed else None
        for i in costed:
            if i == last:
                amounts[i] = money(remaining - allotted)
            else:
                amounts[i] = money(remaining * d(lines[i].get("share") or 0) / shares)
                allotted += amounts[i]
        if tolerance_pct is not None and costed:
            expected = sum((money(d(lines[i].get("est_unit")) * d(lines[i]["qty"])) for i in costed), ZERO)
            band = money(expected * d(tolerance_pct) / Decimal("100"))
            total_costed = sum((amounts[i] for i in costed), ZERO)
            if expected > 0 and total_costed > expected + band:
                residual = total_costed - (expected + band)
                main_i = next((i for i in costed if lines[i]["kind"] == "MAIN"), costed[0])
                amounts[main_i] = money(amounts[main_i] - residual)
    else:
        for i in costed:
            amounts[i] = money(d(lines[i].get("est_unit")) * d(lines[i]["qty"]))
        total = recovery_total + sum((amounts[i] for i in costed), ZERO)
        if total > pool + Decimal("0.005"):
            exceeds = True
    return amounts, residual, exceeds
