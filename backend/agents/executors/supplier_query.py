"""SUPPLIER_QUERY executor (R5): copy/share only. EXECUTED means the person took the message to send it.

It re-runs the checks: if the bill is no longer a draft, or the differences are no longer the ones the message
describes, the draft is stale and nothing is recorded as shared.
"""

from __future__ import annotations

from . import ExecContext, StaleProposal


def execute_supplier_query(proposal, ctx: ExecContext) -> dict:
    from agents.catalog.bill_check.compare import compare_bill
    from agents.catalog.bill_check.context import digest_of
    from purchases.models import PurchaseInvoice

    payload = proposal.effective_payload
    bill = PurchaseInvoice.objects.filter(company=ctx.company, pk=payload.get("bill_id")).select_related("supplier").first()
    if bill is None or bill.status != PurchaseInvoice.Status.DRAFT:
        raise StaleProposal("This bill is not a draft any more.")
    if digest_of(compare_bill(bill)["findings"]) != payload.get("findings_digest"):
        raise StaleProposal("The bill or its order changed after this message was written. Prepare it again.")
    return {
        "type": "supplier_query_shared", "bill_id": bill.pk, "supplier_id": bill.supplier_id, "channel": "copy_or_share",
        "ref": ctx.external_ref, "date": ctx.today.isoformat(),
    }


def acknowledge_bill_note(proposal, ctx: ExecContext) -> dict:
    """Owner-only findings: stale if the bill is no longer a draft or the findings changed; otherwise acknowledged."""
    from agents.catalog.bill_check.compare import compare_bill
    from agents.catalog.bill_check.context import digest_of
    from purchases.models import PurchaseInvoice

    payload = proposal.effective_payload
    bill = PurchaseInvoice.objects.filter(company=ctx.company, pk=payload.get("bill_id")).select_related("supplier").first()
    if bill is None or bill.status != PurchaseInvoice.Status.DRAFT:
        raise StaleProposal("This bill is not a draft any more.")
    if digest_of(compare_bill(bill)["findings"]) != payload.get("findings_digest"):
        raise StaleProposal("The bill or its order changed after this note was written. Prepare it again.")
    return {"type": "bill_note_acknowledged", "bill_id": bill.pk, "ref": ctx.external_ref, "date": ctx.today.isoformat()}
