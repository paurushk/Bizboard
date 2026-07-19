"""Audit Service — activity log (E0.11)."""

from core.models import AuditEvent


class AuditService:
    @staticmethod
    def log(*, action, company=None, user=None, entity_type="", entity_id="",
            description="", metadata=None):
        return AuditEvent.objects.create(
            company=company,
            user=user,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            description=description,
            metadata=metadata or {},
        )
