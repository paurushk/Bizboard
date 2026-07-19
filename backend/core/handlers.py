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
