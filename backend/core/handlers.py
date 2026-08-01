"""Core domain-event handlers: audit trail for document lifecycle events."""

from .events import subscribe
from .services.audit import AuditService


@subscribe("document.completed")
@subscribe("document.cancelled")
def audit_document_event(*, document, user=None, event="", **kwargs):
    status = getattr(document, "status", "")
    AuditService.log(
        company=document.company,
        user=user,
        action="UPDATE",
        entity_type=type(document).__name__,
        entity_id=str(document.pk),
        description=event or type(document).__name__,
        metadata={"status": status, "number": getattr(document, "number", "")},
    )


@subscribe("sales_invoice.edited")
@subscribe("purchase_invoice.edited")
def audit_edited_document_event(*, invoice, user=None, old_totals=None, **kwargs):
    """BUG-213 / H9-A: post-completion edits leave a before/after totals diff."""
    if old_totals is None:
        return
    new_totals = {
        "grand_total": str(invoice.grand_total), "taxable_total": str(invoice.taxable_total),
        "tax_total": str(invoice.cgst_total + invoice.sgst_total + invoice.igst_total),
    }
    meta = {"before": old_totals, "after": new_totals}
    if kwargs.get("amend"):
        meta["amend"] = True
    AuditService.log(
        company=invoice.company,
        user=user,
        action="UPDATE",
        entity_type=type(invoice).__name__,
        entity_id=str(invoice.pk),
        description="Completed document edited",
        metadata=meta,
    )
