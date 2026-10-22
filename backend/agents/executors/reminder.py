"""REMINDER executor (R2): copy/share only. EXECUTED means the user took the message to send it.

It re-reads the ledger: if the customer has paid, or the overdue amount is no longer the one written in
the draft, the draft is stale and nothing is recorded as shared. Sending is a human act in R2; the
provider-backed send arrives in R6 as a separate L3 path that requires this approval record.
"""

from __future__ import annotations

from decimal import Decimal

from . import ExecContext, StaleProposal


def execute_reminder(proposal, ctx: ExecContext) -> dict:
    from masters.models import Customer
    from payments.dunning import customer_risk_snapshot

    payload = proposal.effective_payload
    customer = Customer.objects.filter(company=ctx.company, pk=payload.get("customer_id")).first()
    if customer is None:
        raise StaleProposal("This customer no longer exists.")
    snap = customer_risk_snapshot(ctx.company, customer, as_of=ctx.today)
    overdue = Decimal(snap["overdue_amount"])
    if overdue <= 0:
        raise StaleProposal("This customer has no overdue amount any more.")
    written = Decimal(str(payload.get("total_overdue") or "0"))
    if overdue.quantize(Decimal("0.01")) != written.quantize(Decimal("0.01")):
        raise StaleProposal("The overdue amount changed after this draft was written. Prepare it again.")
    return {
        "type": "reminder_shared",
        "customer_id": customer.id,
        "channel": "copy_or_share",
        "language": payload.get("language", "en"),
        "ref": ctx.external_ref,
        "date": ctx.today.isoformat(),
    }
