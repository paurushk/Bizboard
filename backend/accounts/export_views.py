"""BB-000668: owner tenant export / restore endpoints."""

from __future__ import annotations

from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import IsOwner, get_company_user
from core.services.audit import AuditService

from .tenant_backup import (
    build_export_payload,
    decrypt_export_zip,
    encrypt_export_zip,
    restore_destroy_in_place,
    restore_to_sandbox,
)

EXPORT_CACHE_TTL = 10 * 60


class TenantExportView(APIView):
    """Owner-only encrypted tenant export.

    Distinct from instance Postgres dumps (`scripts/backup.sh`, BB-000045 / BB-000469).
    This endpoint ships a company-scoped logical backup (Fernet-wrapped zip of JSON/CSV).
    """

    permission_classes = [IsAuthenticated, IsOwner]

    def post(self, request):
        cu = get_company_user(request)
        company = cu.company
        cache_key = f"tenant-export:{company.pk}"
        # R-051: claim the 10-minute lock *before* build. A crash mid-export
        # deletes the key so the owner can retry; a dead worker unblocks when
        # the TTL expires. Never a TTL-less lock.
        if not cache.add(cache_key, 1, timeout=EXPORT_CACHE_TTL):
            return Response(
                {"detail": "Export is limited to once every 10 minutes per company."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        try:
            payload = build_export_payload(company)
            blob = encrypt_export_zip(payload)
            AuditService.log(
                action="tenant.export",
                company=company,
                user=request.user,
                entity_type="Company",
                entity_id=company.pk,
                description="Owner downloaded encrypted tenant export.",
                metadata={
                    "bytes": len(blob),
                    "version": payload.get("version"),
                    "summary": summarise_export(payload),
                },
            )
            filename = f"bizboard-tenant-{company.pk}-{timezone.now().strftime('%Y%m%dT%H%M%SZ')}.bin"
            response = HttpResponse(blob, content_type="application/octet-stream")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        except Exception:
            cache.delete(cache_key)
            raise


def summarise_export(payload: dict) -> dict:
    """What an export actually holds, counted from the export itself (SET-08).

    Stored with the audit entry so the screen can say what the last backup contained, rather than
    describing a backup in general terms.
    """
    sections = {k: len(v) for k, v in payload.items() if isinstance(v, list) and k != "file_asset_warnings"}
    files = payload.get("file_assets") or []
    return {
        "sections": len([n for n in sections.values() if n]),
        "records": sum(sections.values()) - len(files),
        "customers": sections.get("customers", 0),
        "suppliers": sections.get("suppliers", 0),
        "products": sections.get("products", 0),
        "sales_invoices": sections.get("sales_invoices", 0),
        "purchase_invoices": sections.get("purchase_invoices", 0),
        "receipts": sections.get("receipts", 0),
        "journals": sections.get("journals", 0),
        "files_with_bytes": sum(1 for f in files if f.get("bytes_b64")),
        "files_listed_only": sum(1 for f in files if not f.get("bytes_b64")),
        "file_warnings": len(payload.get("file_asset_warnings") or []),
    }


class TenantExportLastView(APIView):
    """GET /company/export/last/: when the last encrypted backup was taken, by whom, and what it held.

    Read from the audit trail, so it reflects downloads that really happened. `null` means none yet.
    Also says what the Restore button can and cannot do on this server.
    """

    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        from django.conf import settings

        from core.models import AuditEvent

        company = get_company_user(request).company
        event = (
            AuditEvent.objects.filter(company=company, action="tenant.export")
            .select_related("user")
            .order_by("-created_at", "-id")
            .first()
        )
        last = None
        if event is not None:
            meta = event.metadata or {}
            last = {
                "exported_at": event.created_at,
                "bytes": meta.get("bytes"),
                "version": meta.get("version"),
                "by": (getattr(event.user, "full_name", "") or getattr(event.user, "email", "")) if event.user else "",
                "summary": meta.get("summary"),
            }
        return Response(
            {
                "last_export": last,
                "restore_into_live_enabled": bool(getattr(settings, "TENANT_RESTORE_DESTROY_ENABLED", False)),
                "max_sandboxes": int(getattr(settings, "MAX_CONCURRENT_SANDBOXES", 3) or 0),
            }
        )


class TenantRestoreView(APIView):
    """Restore an encrypted tenant export into a sandbox (default) or destroy-in-place.

    The SPA only posts restore=sandbox. Destroy-in-place remains API-only for ops.
    """

    permission_classes = [IsAuthenticated, IsOwner]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        cu = get_company_user(request)
        company = cu.company

        def _run():
            cache_key = f"tenant-restore:{company.pk}"
            if cache.get(cache_key):
                return Response(
                    {"detail": "Restore is limited to once every 10 minutes per company."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            blob = _read_export_blob(request)
            payload = decrypt_export_zip(blob, company_id=company.pk)
            if payload.get("source_company_id") != company.pk:
                raise BusinessRuleError(
                    "Export was created for a different company and cannot be restored here."
                )
            confirm_destroy = _truthy(request.data.get("confirm_destroy"))
            restore_mode = str(request.data.get("restore") or "").strip().lower()
            # SPA contract: restore=sandbox only. confirm_destroy stays API-only.
            if confirm_destroy and restore_mode != "sandbox":
                from django.conf import settings

                if not getattr(settings, "TENANT_RESTORE_DESTROY_ENABLED", False):
                    # Restoring over live data cannot be undone, so it is not an owner self-service
                    # action: support turns it on for a case after checking with the owner.
                    raise BusinessRuleError(
                        "Restoring over your live data is done by support, not from this screen. "
                        "Restore into a sandbox copy to check the backup, then contact support.",
                        code="RESTORE_LIVE_DISABLED",
                    )
                typed_name = (request.data.get("typed_name") or request.data.get("typedName") or "").strip()
                if typed_name != company.name:
                    raise BusinessRuleError(
                        "Destroy-in-place restore requires typed_name to match the company name exactly."
                    )
                confirm_unbacked = _truthy(
                    request.data.get("confirm_destroy_unbacked")
                    or request.data.get("confirmDestroyUnbacked")
                )
                # Written before the destructive step, so a failure part-way still leaves a record.
                AuditService.log(
                    action="tenant.restore_destroy_started",
                    company=company,
                    user=request.user,
                    entity_type="Company",
                    entity_id=company.pk,
                    description="In-place restore started.",
                )
                restore_destroy_in_place(
                    company=company,
                    payload=payload,
                    owner=request.user,
                    confirm_destroy_unbacked=confirm_unbacked,
                )
                AuditService.log(
                    action="tenant.restore_destroy",
                    company=company,
                    user=request.user,
                    entity_type="Company",
                    entity_id=company.pk,
                    description="Owner restored tenant export in-place after confirm_destroy.",
                )
                cache.set(cache_key, 1, timeout=EXPORT_CACHE_TTL)
                return Response({"company_id": company.pk, "mode": "destroy_in_place", "name": company.name})

            sandbox = restore_to_sandbox(source_company=company, payload=payload, owner=request.user)
            AuditService.log(
                action="tenant.restore_sandbox",
                company=company,
                user=request.user,
                entity_type="Company",
                entity_id=sandbox.pk,
                description="Owner restored tenant export into a sandbox company.",
                metadata={"sandbox_company_id": sandbox.pk, "sandbox_name": sandbox.name},
            )
            cache.set(cache_key, 1, timeout=EXPORT_CACHE_TTL)
            return Response(
                {
                    "company_id": sandbox.pk,
                    "mode": "sandbox",
                    "name": sandbox.name,
                    "sandbox_expires_at": sandbox.sandbox_expires_at.isoformat()
                    if sandbox.sandbox_expires_at
                    else None,
                },
                status=status.HTTP_201_CREATED,
            )

        return wrap_idempotent(
            request=request,
            company=company,
            scope="tenant_restore_sandbox",
            build=_run,
        )


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _read_export_blob(request) -> bytes:
    upload = request.FILES.get("file") or request.FILES.get("export")
    if upload is not None:
        return upload.read()
    raw = request.data.get("payload") or request.data.get("blob") or ""
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    text = str(raw).strip()
    if not text:
        raise BusinessRuleError("Provide an export file or base64 payload.")
    import base64

    try:
        return base64.b64decode(text)
    except (ValueError, TypeError) as exc:
        raise BusinessRuleError("Export payload is not valid base64.") from exc
