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
        if cache.get(cache_key):
            return Response(
                {"detail": "Export is limited to once every 10 minutes per company."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        payload = build_export_payload(company)
        blob = encrypt_export_zip(payload)
        cache.set(cache_key, 1, timeout=EXPORT_CACHE_TTL)
        AuditService.log(
            action="tenant.export",
            company=company,
            user=request.user,
            entity_type="Company",
            entity_id=company.pk,
            description="Owner downloaded encrypted tenant export.",
            metadata={"bytes": len(blob), "version": payload.get("version")},
        )
        filename = f"bizboard-tenant-{company.pk}-{timezone.now().strftime('%Y%m%dT%H%M%SZ')}.bin"
        response = HttpResponse(blob, content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class TenantRestoreView(APIView):
    """Restore an encrypted tenant export into a sandbox (default) or destroy-in-place."""

    permission_classes = [IsAuthenticated, IsOwner]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        cu = get_company_user(request)
        company = cu.company
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
        cache.set(cache_key, 1, timeout=EXPORT_CACHE_TTL)
        confirm_destroy = _truthy(request.data.get("confirm_destroy"))
        typed_name = (request.data.get("typed_name") or request.data.get("typedName") or "").strip()

        if confirm_destroy:
            if typed_name != company.name:
                raise BusinessRuleError(
                    "Destroy-in-place restore requires typed_name to match the company name exactly."
                )
            restore_destroy_in_place(company=company, payload=payload, owner=request.user)
            AuditService.log(
                action="tenant.restore_destroy",
                company=company,
                user=request.user,
                entity_type="Company",
                entity_id=company.pk,
                description="Owner restored tenant export in-place after confirm_destroy.",
            )
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
        return Response(
            {
                "company_id": sandbox.pk,
                "mode": "sandbox",
                "name": sandbox.name,
            },
            status=status.HTTP_201_CREATED,
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
