"""Collections outcome report (AGT-208): did the drafts lead to money in?

Read-only. For the pilot review, not a billing figure.

* Draft funnel: created, executed, rejected, expired, failed, cancelled; how many executed drafts were edited.
* Treated: for each executed reminder, the posted receipts from that customer in the 7 days from approval.
* Held out: customers in the deterministic 20% holdout (only when the company opted in) get no scheduled drafts.
  For every scheduled run, we sum their receipts in the 7 days from that run, among holdout customers who owed
  overdue money on that date by today's ledger. Both groups are compared as money received per customer.
The holdout comparison is approximate (it uses today's invoice due dates); it is a signal for a human review, not proof.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .enums import ProposalStatus, Trigger
from .models import AgentProposal, AgentRun

WINDOW_DAYS = 7


def _received(company, customer_id: int, start, days: int = WINDOW_DAYS) -> Decimal:
    from payments.models import CustomerReceipt, ReceiptStatus

    total = CustomerReceipt.objects.filter(
        company=company, customer_id=customer_id, status=ReceiptStatus.POSTED,
        receipt_date__gte=start, receipt_date__lte=start + timedelta(days=days),
    ).aggregate(t=Sum("amount"))["t"]
    return Decimal(str(total or 0))


def collections_outcomes(company, *, since=None) -> dict:
    since = since or (timezone.now() - timedelta(days=30))
    props = AgentProposal.objects.filter(company=company, kind="REMINDER", created_at__gte=since)
    by_status = {s.value: props.filter(status=s).count() for s in ProposalStatus}
    executed = list(props.filter(status=ProposalStatus.EXECUTED))
    edited = sum(1 for p in executed if p.revision > 0)
    decided = sum(by_status[k] for k in ("EXECUTED", "REJECTED", "EXPIRED", "CANCELLED", "FAILED"))

    treated_customers: dict[int, Decimal] = {}
    for p in executed:
        cid = p.effective_payload.get("customer_id")
        if cid is None or p.decided_at is None:
            continue
        got = _received(company, int(cid), timezone.localtime(p.decided_at).date())
        treated_customers[int(cid)] = max(treated_customers.get(int(cid), Decimal("0")), got)

    held_total, held_customers = Decimal("0"), set()
    flags = company.feature_flags or {}
    if flags.get("AGENT_COLLECTIONS_HOLDOUT"):
        from agents.catalog.collections.context import holdout
        from sales.models import SalesInvoice
        from sales.status_semantics import OPEN_SALES_STATUSES

        runs = AgentRun.objects.filter(company=company, agent="COLLECTIONS", trigger=Trigger.SCHEDULE, created_at__gte=since)
        for run in runs:
            day = timezone.localtime(run.created_at).date()
            owing = SalesInvoice.objects.filter(
                company=company, status__in=OPEN_SALES_STATUSES, due_date__lt=day,
            ).values_list("customer_id", flat=True).distinct()
            for cid in owing:
                if cid is not None and holdout(company, cid):
                    held_customers.add(cid)
                    held_total += _received(company, cid, day)

    def per(total: Decimal, n: int) -> str:
        return str((total / n).quantize(Decimal("0.01"))) if n else "0.00"

    treated_total = sum(treated_customers.values(), Decimal("0"))
    return {
        "since": since.isoformat(),
        "funnel": by_status,
        "approval_rate": round(by_status["EXECUTED"] / decided, 3) if decided else None,
        "edited_rate": round(edited / len(executed), 3) if executed else None,
        "treated": {
            "customers": len(treated_customers), "received_within_7_days": str(treated_total),
            "per_customer": per(treated_total, len(treated_customers)),
        },
        "held_out": {
            "enabled": bool(flags.get("AGENT_COLLECTIONS_HOLDOUT")), "customers": len(held_customers),
            "received_within_7_days": str(held_total), "per_customer": per(held_total, len(held_customers)),
        },
        "note": "Approximate: the held-out comparison uses today's invoice due dates. Review with the owner; do not publish as proof.",
    }
