"""SET-08: weekly encrypted backups kept on the server, for owners who switch them on.

The file is the same encrypted bundle the Download button produces. The last ``KEEP`` are kept and
older ones removed; each run, good or bad, leaves an audit entry so the Backup screen can say what
happened instead of staying silent.
"""

from __future__ import annotations

import logging

from django.core.files.base import ContentFile
from django.utils import timezone

from core.models import AuditEvent, FileAsset
from core.services.audit import AuditService

from .export_views import summarise_export
from .tenant_backup import build_export_payload, encrypt_export_zip

logger = logging.getLogger(__name__)

KEEP = 4
NAME_PREFIX = "bizboard-auto-backup-"


def stored_backups(company):
    return FileAsset.objects.filter(
        company=company, kind=FileAsset.Kind.EXPORT, original_name__startswith=NAME_PREFIX
    ).order_by("-created_at", "-id")


def run_scheduled_backup(company) -> FileAsset | None:
    """Take one backup now. Returns the stored file, or None when it could not be taken (audited)."""
    from billing.quotas import assert_storage_allowed

    try:
        payload = build_export_payload(company)
        blob = encrypt_export_zip(payload)
        assert_storage_allowed(company, additional_bytes=len(blob))
        name = f"{NAME_PREFIX}{company.pk}-{timezone.now().strftime('%Y%m%dT%H%M%SZ')}.bin"
        asset = FileAsset.objects.create(
            company=company,
            kind=FileAsset.Kind.EXPORT,
            file=ContentFile(blob, name=name),
            original_name=name,
            content_type="application/octet-stream",
            size=len(blob),
        )
    except Exception as exc:  # noqa: BLE001 - a failed backup must be recorded, never crash the batch
        logger.exception("scheduled backup failed for company %s", company.pk)
        AuditService.log(
            company=company,
            user=None,
            action="UPDATE",
            entity_type="Company",
            entity_id=company.pk,
            description="Automatic backup failed.",
            metadata={"event": "tenant.export.scheduled_failed", "error": str(exc)[:300]},
        )
        from .settings_alerts import notify_owners

        stamp = timezone.localdate().isoformat()
        notify_owners(
            company,
            "Automatic backup failed",
            "The weekly backup could not be taken. Open Settings, Backup / Export to try again.",
            f"backup-failed:{stamp}",
        )
        return None
    for old in list(stored_backups(company)[KEEP:]):
        stored = old.file
        old.delete()
        try:
            stored.delete(save=False)
        except Exception:  # noqa: BLE001 - the row is gone; an orphan file is harmless
            pass
    AuditService.log(
        company=company,
        user=None,
        action="CREATE",
        entity_type="Company",
        entity_id=company.pk,
        description="Automatic backup taken.",
        metadata={
            "event": "tenant.export.scheduled",
            "bytes": len(blob),
            "file_id": asset.pk,
            "summary": summarise_export(payload),
        },
    )
    return asset


def last_scheduled_result(company) -> dict | None:
    """The most recent automatic run, good or failed, read from the audit trail."""
    events = AuditEvent.objects.filter(company=company, entity_type="Company").order_by("-created_at", "-id")[:50]
    for event in events:
        kind = (event.metadata or {}).get("event")
        if kind in ("tenant.export.scheduled", "tenant.export.scheduled_failed"):
            return {
                "at": event.created_at,
                "ok": kind == "tenant.export.scheduled",
                "error": (event.metadata or {}).get("error", ""),
            }
    return None
