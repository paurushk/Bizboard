"""Manufacturing rows for the Needs attention feed (MFG-X2).

One detector, run only for companies that have Manufacturing on. Each sub-module's rows appear
only when its own switch is on, so a company that never turned Quality on never sees quality rows.
The feed supplies ``row`` (its row factory) so the shape stays in one place.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from core.services.feature_flags import build_feature_flags

CODES = frozenset({
    "WO_LATE", "WO_SHORTAGE", "WIP_STALE", "BATCH_ON_HOLD", "NCR_OVERDUE", "JOBWORK_AGEING", "ITC04_DUE",
    "WO_APPROVAL_WAITING",
})
CAP = 10
STALE_WIP_DAYS = 30
HOLD_DAYS = 7


def rows(company, as_of, row) -> list[dict]:
    flags = build_feature_flags(company=company)
    if not flags.get("ENABLE_MANUFACTURING"):
        return []
    out: list[dict] = []
    out += _orders(company, as_of, row, with_shortage=bool(flags.get("MFG_PLANNING")))
    if flags.get("MFG_QUALITY"):
        out += _quality(company, as_of, row)
    if flags.get("MFG_JOB_WORK"):
        out += _job_work(company, as_of, row)
    return out


def _orders(company, as_of, row, *, with_shortage: bool) -> list[dict]:
    from .models import WorkOrder
    from .services import planning

    out: list[dict] = []
    open_orders = WorkOrder.objects.filter(
        company=company, status__in=["RELEASED", "IN_PROGRESS"],
    ).select_related("product").order_by("due_date", "priority", "id")
    late = 0
    for wo in open_orders:
        name = wo.product.name if wo.product_id else wo.number
        if wo.due_date and wo.due_date < as_of and late < CAP:
            late += 1
            days = (as_of - wo.due_date).days
            out.append(row(
                code="WO_LATE", severity="critical" if days >= 7 else "warning",
                title=f"Work order {wo.number} is late", money_impact_paise=0,
                reason=f"{name} was due {wo.due_date.isoformat()} and is not finished.",
                action_label="Open work order", action_href=f"/manufacturing/work-orders/{wo.pk}",
                source_ticket="MFG-X2", entity_type="work_order", entity_id=wo.pk,
                dedupe_key=f"WO_LATE:{wo.pk}",
                params={"number": wo.number, "product": name, "days": days, "due": wo.due_date.isoformat()},
            ))
    if with_shortage:
        short = 0
        for wo in open_orders:
            if short >= CAP:
                break
            lines = [r for r in planning.work_order_availability(wo) if r["short"] > 0]
            if lines:
                short += 1
                out.append(row(
                    code="WO_SHORTAGE", severity="warning",
                    title=f"Work order {wo.number} is short of material", money_impact_paise=0,
                    reason=f"{len(lines)} material(s) are not in stock for {wo.number}.",
                    action_label="See shortages", action_href="/manufacturing/planning",
                    source_ticket="MFG-X2", entity_type="work_order", entity_id=wo.pk,
                    dedupe_key=f"WO_SHORTAGE:{wo.pk}",
                    params={"number": wo.number, "count": len(lines)},
                ))
    from .models import MaterialIssue

    for issue in MaterialIssue.objects.filter(
        company=company, status="DRAFT", approval="REQUESTED",
    ).select_related("work_order").order_by("id")[:CAP]:
        wo = issue.work_order
        out.append(row(
            code="WO_APPROVAL_WAITING", severity="warning",
            title=f"Extra material for {wo.number} is waiting for approval", money_impact_paise=0,
            reason=f"Someone asked for more material than {wo.number} needs. Approve it or turn it down.",
            action_label="Open work order", action_href=f"/manufacturing/work-orders/{wo.pk}",
            source_ticket="MFG-X2", entity_type="material_issue", entity_id=issue.pk,
            dedupe_key=f"WO_APPROVAL_WAITING:{issue.pk}",
            params={"number": wo.number},
        ))
    cutoff = as_of - timedelta(days=STALE_WIP_DAYS)       # released_at is a date, not a moment
    stale = 0
    for wo in WorkOrder.objects.filter(
        company=company, status__in=["IN_PROGRESS", "COMPLETED"], issue_mode="SEPARATE", released_at__lt=cutoff,
    ).select_related("product").order_by("released_at"):
        wip = wo.wip_value
        if wip <= 0 or stale >= CAP:
            continue
        stale += 1
        out.append(row(
            code="WIP_STALE", severity="warning",
            title=f"{wo.number} has been in progress a long time",
            money_impact_paise=int(wip * 100),
            reason=f"₹{wip} of material and cost is still sitting in {wo.number}. Finish it or close it.",
            action_label="Open work order", action_href=f"/manufacturing/work-orders/{wo.pk}",
            source_ticket="MFG-X2", entity_type="work_order", entity_id=wo.pk,
            dedupe_key=f"WIP_STALE:{wo.pk}",
            params={"number": wo.number, "amount": str(wip), "days": (as_of - wo.released_at).days},
        ))
    return out


def _quality(company, as_of, row) -> list[dict]:
    from inventory.models import BatchLot
    from quality.models import NonConformance

    out: list[dict] = []
    cutoff = timezone.now() - timedelta(days=HOLD_DAYS)
    for lot in BatchLot.objects.filter(
        company=company, quality_status__in=["HOLD", "QUARANTINE"], updated_at__lt=cutoff,
    ).select_related("product").order_by("updated_at")[:CAP]:
        out.append(row(
            code="BATCH_ON_HOLD", severity="warning",
            title=f"Batch {lot.batch_no} is still on hold", money_impact_paise=0,
            reason=f"{lot.product.name} batch {lot.batch_no} has waited over {HOLD_DAYS} days for a decision.",
            action_label="Open inspections", action_href="/manufacturing/quality",
            source_ticket="MFG-X2", entity_type="batch", entity_id=lot.pk,
            dedupe_key=f"BATCH_ON_HOLD:{lot.pk}",
            params={"batch": lot.batch_no, "product": lot.product.name, "days": HOLD_DAYS},
        ))
    for ncr in NonConformance.objects.filter(
        company=company, status__in=["OPEN", "ACTION"], due_date__lt=as_of,
    ).order_by("due_date")[:CAP]:
        out.append(row(
            code="NCR_OVERDUE", severity="warning",
            title=f"Quality problem {ncr.number} is overdue", money_impact_paise=0,
            reason=f"{ncr.number} was due {ncr.due_date.isoformat()} and is not closed.",
            action_label="Open quality problems", action_href="/manufacturing/quality",
            source_ticket="MFG-X2", entity_type="ncr", entity_id=ncr.pk,
            dedupe_key=f"NCR_OVERDUE:{ncr.pk}",
            params={"number": ncr.number, "due": ncr.due_date.isoformat()},
        ))
    return out


def _job_work(company, as_of, row) -> list[dict]:
    from jobwork.services import common as jw_common
    from jobwork.services import itc04, out as jw_out
    from jobwork.models import Itc04Filing, JobWorkChallan

    out: list[dict] = []
    late = [r for r in jw_out.ageing(company, as_of) if r["status"] in ("OVERDUE", "ALERT")][:CAP]
    for r in late:
        overdue = r["status"] == "OVERDUE"
        out.append(row(
            code="JOBWORK_AGEING", severity="critical" if overdue else "warning",
            title=("Goods at job worker are past the time limit" if overdue else "Goods at job worker are nearly due back"),
            money_impact_paise=int(r["value"] * 100),
            reason=f"{r['product']} sent on challan {r['challan']} has been out {r['days']} days (limit {r['limit_days']}).",
            action_label="Open job work", action_href="/manufacturing/job-work",
            source_ticket="MFG-X2", entity_type="jobwork_challan_line", entity_id=r["challan_line"],
            dedupe_key=f"JOBWORK_AGEING:{r['challan_line']}",
            params={
                "variant": "overdue" if overdue else "soon", "product": r["product"], "challan": r["challan"],
                "days": r["days"], "limit": r["limit_days"], "amount": str(r["value"]),
            },
        ))
    cfg = jw_common.settings_for(company)
    filed = {f.period_label for f in Itc04Filing.objects.filter(company=company, status="FILED")}
    for label, start, end, due in itc04.periods_due(cfg.itc04_frequency, as_of):
        if label in filed or end >= as_of or as_of > due + timedelta(days=30):
            continue
        if not JobWorkChallan.objects.filter(
            company=company, status="ISSUED", challan_date__gte=start, challan_date__lte=end,
        ).exists():
            continue
        days_left = (due - as_of).days
        out.append(row(
            code="ITC04_DUE", severity="critical" if days_left < 0 else "warning",
            title=f"ITC-04 for {label} is {'overdue' if days_left < 0 else 'due soon'}", money_impact_paise=0,
            reason=f"The job work return for {label} is due {due.isoformat()}.",
            action_label="Prepare ITC-04", action_href="/manufacturing/job-work",
            source_ticket="MFG-X2", entity_type="company", entity_id=company.pk,
            dedupe_key=f"ITC04_DUE:{label}",
            params={"period": label, "due": due.isoformat(), "variant": "overdue" if days_left < 0 else "soon"},
        ))
    return out
