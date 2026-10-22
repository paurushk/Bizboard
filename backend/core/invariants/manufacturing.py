"""Manufacturing invariants: a work order's cached money matches its documents, and WIP matches the books."""

from accounting.books import posts_to_ledger
from decimal import Decimal

from .base import invariant

_ZERO = Decimal("0")
_TOL = Decimal("0.01")


def _sum(rows) -> Decimal:
    return sum((Decimal(str(r or 0)) for r in rows), _ZERO)


@invariant(
    "manufacturing.wo_cost_summary_matches_documents",
    consequence="A work order's cached issued/returned/received cost disagrees with the posted documents — "
                "WIP, lists and the variance report show the wrong numbers.",
)
def wo_cost_summary_matches_documents(company) -> list[str]:
    from django.db.models import Sum

    from manufacturing.models import (
        DocumentStatus, MaterialIssueLine, MaterialReturnLine, ProductionReceipt, WorkOrder,
    )

    out = []
    posted = DocumentStatus.POSTED
    for wo in WorkOrder.objects.filter(company=company, issue_mode="SEPARATE").exclude(status="CANCELLED"):
        issued = MaterialIssueLine.objects.filter(
            issue__work_order=wo, issue__status=posted,
        ).aggregate(t=Sum("cost_amount"))["t"] or _ZERO
        returned = MaterialReturnLine.objects.filter(
            material_return__work_order=wo, material_return__status=posted,
        ).aggregate(t=Sum("cost_amount"))["t"] or _ZERO
        receipts = ProductionReceipt.objects.filter(work_order=wo, status=posted)
        received = _sum(r.total_cost for r in receipts)
        # Conversion cost reaches the order two ways: at a receipt, and from finished job cards.
        from manufacturing.models import JobCard

        absorbed = _sum(r.absorbed_cost for r in receipts) + _sum(
            c.labour_cost + c.machine_cost + c.overhead_cost
            for c in JobCard.objects.filter(work_order=wo, absorbed=True)
        )
        for label, cached, actual in (
            ("issued", wo.cost_issued, issued),
            ("returned", wo.cost_returned, returned),
            ("received", wo.cost_received, received),
            ("absorbed", wo.cost_absorbed, absorbed),
        ):
            if abs(Decimal(str(cached)) - Decimal(str(actual))) > _TOL:
                out.append(f"{wo.number or wo.pk}: cost_{label} {cached} != documents {actual}")
    return out


@invariant(
    "manufacturing.wo_line_qty_matches_documents",
    consequence="A work order line's issued/returned quantity disagrees with the posted documents — "
                "the next issue or return will be allowed or refused wrongly.",
)
def wo_line_qty_matches_documents(company) -> list[str]:
    from django.db.models import Sum

    from manufacturing.models import (
        DocumentStatus, MaterialIssueLine, MaterialReturnLine, WorkOrderLine,
    )

    out = []
    for line in WorkOrderLine.objects.filter(company=company, work_order__issue_mode="SEPARATE").exclude(
        work_order__status="CANCELLED",
    ):
        issued = MaterialIssueLine.objects.filter(
            wo_line=line, issue__status=DocumentStatus.POSTED,
        ).aggregate(t=Sum("qty"))["t"] or _ZERO
        returned = MaterialReturnLine.objects.filter(
            wo_line=line, material_return__status=DocumentStatus.POSTED,
        ).aggregate(t=Sum("qty"))["t"] or _ZERO
        if line.qty_issued != issued or line.qty_returned != returned:
            out.append(
                f"line {line.pk} of WO {line.work_order_id}: cached issued/returned "
                f"{line.qty_issued}/{line.qty_returned} != documents {issued}/{returned}"
            )
    return out


@invariant(
    "manufacturing.closed_wo_has_zero_wip",
    consequence="A closed work order still holds cost in work in progress — the books carry value for finished work.",
)
def closed_wo_has_zero_wip(company) -> list[str]:
    from manufacturing.models import WorkOrder

    return [
        f"{wo.number or wo.pk}: closed with WIP {wo.wip_value}"
        for wo in WorkOrder.objects.filter(company=company, status="CLOSED")
        if abs(wo.wip_value) > _TOL
    ]


@invariant(
    "manufacturing.wip_matches_gl",
    consequence="Work in progress on the work orders disagrees with GL 1450 — the balance sheet and the shop floor "
                "tell different stories.",
)
def wip_matches_gl(company) -> list[str]:
    if not posts_to_ledger(company):
        return []
    from accounting.models import JournalLine
    from manufacturing.models import WorkOrder

    orders = list(WorkOrder.objects.filter(company=company).exclude(status="CANCELLED"))
    if not orders:
        return []
    subledger = _sum(wo.wip_value for wo in orders)
    agg = JournalLine.objects.filter(
        # A reversed journal and its reversing entry cancel each other, so both count.
        entry__company=company, entry__status__in=["POSTED", "REVERSED"], account__code="1450",
    )
    debit = _sum(agg.values_list("debit", flat=True))
    credit = _sum(agg.values_list("credit", flat=True))
    gl = debit - credit
    if abs(gl - subledger) > _TOL:
        return [f"GL 1450 net {gl} != work-order WIP {subledger}"]
    return []


@invariant(
    "manufacturing.consumed_serial_has_trace",
    consequence="A serial number used up in production has no genealogy record — a recall cannot find where it went.",
)
def consumed_serial_has_trace(company) -> list[str]:
    from inventory.models import SerialNumber, TraceLink

    out = []
    consumed = SerialNumber.objects.filter(company=company, status="CONSUMED")
    if not consumed.exists():
        return out
    linked = set(
        TraceLink.objects.filter(company=company, reversed_at__isnull=True)
        .exclude(input_serial="").values_list("input_product_id", "input_serial")
    )
    for s in consumed.values("product_id", "serial_number"):
        if (s["product_id"], s["serial_number"]) not in linked:
            out.append(f"serial {s['serial_number']} (product {s['product_id']}) is CONSUMED with no trace link")
    return out
