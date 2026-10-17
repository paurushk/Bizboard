"""Stock that moved while a count was being taken (INV-IDR-04).

A count line carries the system quantity at the moment it was put on the sheet (``system_qty``,
``snapshot_at``) and the moment its counted figure was last changed (``counted_at``). Sales and
receipts between those two moments were already reflected in what the counter saw on the shelf, so
the difference to post is

    counted - (system_qty + stock movements between snapshot_at and counted_at)

and not ``counted - current``, which would subtract a sale made after the counting a second time.
Movements after ``counted_at`` are not part of the count at all and are left alone.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from .models import StockMovement

KEEP_SERVER = "KEEP_SERVER"
KEEP_LOCAL = "KEEP_LOCAL"
ADJUST_FOR_MOVEMENTS = "ADJUST_FOR_MOVEMENTS"
RESOLUTIONS = frozenset({KEEP_SERVER, KEEP_LOCAL, ADJUST_FOR_MOVEMENTS})


def net_movements(company, warehouse, product, batch, after, upto) -> Decimal:
    """Signed stock movement for one count line between two moments (``after`` exclusive)."""
    qs = StockMovement.objects.filter(
        company=company, warehouse=warehouse, product=product,
        created_at__gt=after, created_at__lte=upto,
    )
    qs = qs.filter(batch=batch) if batch is not None else qs.filter(batch__isnull=True)
    return qs.aggregate(total=Sum("quantity"))["total"] or Decimal("0")


def variance_for(session, line, current: Decimal, choice: str) -> Decimal | None:
    """What to post for a line, or ``None`` to leave it alone (KEEP_SERVER)."""
    counted = Decimal(str(line.counted_qty))
    if choice == KEEP_SERVER:
        return None
    if choice == ADJUST_FOR_MOVEMENTS and line.counted_at is not None:
        after = line.snapshot_at or session.created_at
        moved = net_movements(session.company, session.warehouse, line.product, line.batch, after, line.counted_at)
        return counted - (Decimal(str(line.system_qty)) + moved)
    # KEEP_LOCAL, or no counted_at to work from (a line counted before this existed): count against now.
    return counted - current


def parse_resolutions(data) -> tuple[dict[int, str], str]:
    """Per-line choices ``{line_id: choice}`` and the single choice older clients send for every line."""
    from core.exceptions import BusinessRuleError

    per_line: dict[int, str] = {}
    raw = data.get("resolutions")
    if isinstance(raw, dict):
        for key, choice in raw.items():
            try:
                line_id = int(key)
            except (TypeError, ValueError):
                raise BusinessRuleError("resolutions must be keyed by line id.") from None
            choice = str(choice or "").upper()
            if choice not in RESOLUTIONS:
                raise BusinessRuleError(f"Unknown resolution '{choice}'.")
            per_line[line_id] = choice
    elif raw not in (None, ""):
        raise BusinessRuleError("resolutions must be an object of line id to choice.")
    default = str(data.get("resolve_conflicts") or "").upper()
    if default and default not in RESOLUTIONS:
        raise BusinessRuleError(f"Unknown resolution '{default}'.")
    return per_line, default
