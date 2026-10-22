"""Job work invariants: what the job worker holds matches what we sent less what is accounted for."""

from collections import defaultdict
from decimal import Decimal

from .base import invariant

_ZERO = Decimal("0")


@invariant(
    "jobwork.stock_at_job_worker_matches_open_challans",
    consequence="The stock in a job worker's godown disagrees with the material still open on our challans — "
                "the deemed-supply clock and ITC-04 are working from the wrong quantities.",
)
def stock_at_job_worker_matches_open_challans(company) -> list[str]:
    from inventory.models import StockBalance, Warehouse
    from jobwork.models import JobWorkChallanLine

    godowns = list(Warehouse.all_objects.filter(company=company, kind="JOB_WORKER"))
    if not godowns:
        return []
    out = []
    for wh in godowns:
        stock = defaultdict(lambda: _ZERO)
        for b in StockBalance.objects.filter(company=company, warehouse=wh):
            stock[b.product_id] += b.on_hand
        open_qty = defaultdict(lambda: _ZERO)
        for ln in JobWorkChallanLine.objects.filter(
            company=company, challan__status="ISSUED", challan__order__job_worker_warehouse=wh,
        ):
            open_qty[ln.product_id] += ln.qty - ln.qty_settled
        for pid in set(stock) | set(open_qty):
            if stock[pid] != open_qty[pid]:
                out.append(f"{wh.name}, product {pid}: stock {stock[pid]} != open on challans {open_qty[pid]}")
    return out


@invariant(
    "jobwork.settlements_match_challan_lines",
    consequence="A challan line's settled quantity disagrees with the receipts that settled it.",
)
def settlements_match_challan_lines(company) -> list[str]:
    from django.db.models import Sum

    from jobwork.models import JobWorkChallanLine

    out = []
    for ln in JobWorkChallanLine.objects.filter(company=company, challan__order__direction="OUT"):
        total = ln.settlements.filter(reversed=False).aggregate(t=Sum("qty"))["t"] or _ZERO
        if total != ln.qty_settled:
            out.append(f"challan line {ln.pk}: settled {ln.qty_settled} != receipts {total}")
        if ln.qty_settled > ln.qty:
            out.append(f"challan line {ln.pk}: settled {ln.qty_settled} is more than sent {ln.qty}")
    return out


@invariant(
    "jobwork.principal_material_non_negative",
    consequence="More of a customer's material has left our hands than ever came in.",
)
def principal_material_non_negative(company) -> list[str]:
    from django.db.models import Sum

    from jobwork.models import PrincipalMaterialMovement

    rows = (
        PrincipalMaterialMovement.objects.filter(company=company, reversed=False)
        .values("principal_id", "product_id").annotate(t=Sum("qty"))
    )
    return [
        f"principal {r['principal_id']}, product {r['product_id']}: balance {r['t']}" for r in rows if (r["t"] or _ZERO) < 0
    ]
