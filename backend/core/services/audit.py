"""Audit Service — activity log (E0.11)."""

from core.models import AuditEvent


class AuditService:
    @staticmethod
    def log(*, action, company=None, user=None, entity_type="", entity_id="",
            description="", metadata=None):
        from core.observability import current_client_ip

        meta = dict(metadata or {})
        ip = current_client_ip()
        if ip and "ip" not in meta:
            meta["ip"] = ip
        return AuditEvent.objects.create(
            company=company,
            user=user,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            description=description,
            metadata=meta,
        )


def before_status_for_event(event: str) -> str:
    """Prior status implied by a posting event name, when the caller did not pass one."""
    name = event or ""
    if name.endswith(".completed") or name.endswith(".posted"):
        return "DRAFT"
    if name.endswith(".cancelled") or name.endswith(".voided"):
        return "COMPLETED"
    if name.endswith(".reversed"):
        return "POSTED"
    return ""


def record_document_event(*, document, user=None, event="", metadata=None, before=None):
    """Write the document audit row inside the caller's money transaction.

    Does not catch. A failed insert rolls the invoice, receipt, or note back.
    That outage is intentional: a completed document with no audit row is worse
    than a refused complete. ``before`` is the prior field snapshot; ``after``
    is the document as recorded.
    """
    status = getattr(document, "status", "")
    meta = {
        "status": status,
        "number": getattr(document, "number", ""),
        "after": {"status": str(status) if status != "" else "", "number": str(getattr(document, "number", "") or "")},
    }
    if before is None:
        implied = before_status_for_event(event)
        if implied:
            before = {"status": implied}
    if before is not None:
        meta["before"] = before
    if metadata:
        meta.update(metadata)
    return AuditService.log(
        company=document.company,
        user=user,
        action="UPDATE",
        entity_type=type(document).__name__,
        entity_id=str(document.pk),
        description=event or type(document).__name__,
        metadata=meta,
    )


def record_edited_document_event(*, invoice, user=None, old_totals=None, amend=False):
    """Before/after totals for a completed-document edit, in the money transaction."""
    if old_totals is None:
        return None
    new_totals = {
        "grand_total": str(invoice.grand_total),
        "taxable_total": str(invoice.taxable_total),
        "tax_total": str(invoice.cgst_total + invoice.sgst_total + invoice.igst_total),
    }
    meta = {"before": old_totals, "after": new_totals}
    description = "Completed document edited"
    if amend:
        meta["amend"] = True
        description = "sales_invoice.amended"
    return AuditService.log(
        company=invoice.company,
        user=user,
        action="UPDATE",
        entity_type=type(invoice).__name__,
        entity_id=str(invoice.pk),
        description=description,
        metadata=meta,
    )
