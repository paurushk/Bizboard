"""WP-DL1: owner API for the readable export.

POST /api/v1/company/export/readable/            password (+ two-step) → starts a build
GET  /api/v1/company/export/readable/            the last exports and their state
GET  /api/v1/company/export/readable/<id>/file/  the ZIP while its link is live (owner only)
"""

from __future__ import annotations

from django.core.files.storage import default_storage
from django.http import FileResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.audit import AuditService


def _row(r) -> dict:
    return {
        "id": r.pk, "status": r.status, "size": r.size, "created_at": r.created_at,
        "ready_at": r.ready_at, "expires_at": r.expires_at, "error": r.error,
        "format_version": (r.manifest or {}).get("format_version", ""),
    }


class ReadableExportView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get_throttles(self):
        # Only starting an export is a sensitive action; the panel polls the list while it builds,
        # and those reads must not use up the owner's password-change / transfer budget.
        self.throttle_scope = "sensitive_action" if self.request.method == "POST" else None
        return super().get_throttles()

    def get(self, request):
        from .models import ReadableExport

        cu = get_company_user(request)
        return Response([_row(r) for r in ReadableExport.objects.filter(company=cu.company)[:10]])

    def post(self, request):
        from billing.reauth import require_reauth
        from support.privacy import log_request

        from .models import ReadableExport
        from .tasks import build_readable_export_task

        from datetime import timedelta

        from .readable_export import STALE_PENDING_MINUTES

        require_reauth(request)
        cu = get_company_user(request)
        stale_before = timezone.now() - timedelta(minutes=STALE_PENDING_MINUTES)
        pending = ReadableExport.objects.filter(company=cu.company, status=ReadableExport.Status.PENDING)
        pending.filter(created_at__lte=stale_before).update(
            status=ReadableExport.Status.FAILED, error="The export did not finish. Ask for a new one.",
        )
        if pending.exists():
            return Response({"detail": "An export is already being prepared."}, status=status.HTTP_409_CONFLICT)
        row = ReadableExport.objects.create(
            company=cu.company, requested_by=request.user, created_by=request.user, updated_by=request.user,
        )
        AuditService.log(
            action="tenant.export_readable", company=cu.company, user=request.user,
            entity_type="ReadableExport", entity_id=row.pk, description="Owner asked for a readable export.",
        )
        log_request(kind="ACCESS", requester=request.user.email, company=cu.company, closed=True,
                    outcome="Owner asked for the readable (CSV + PDF) export (self-serve).", user=request.user)
        try:
            build_readable_export_task.delay(row.pk, company_id=cu.company.pk)
        except Exception:  # noqa: BLE001 - broker down: fail the row instead of blocking the next request
            ReadableExport.objects.filter(pk=row.pk).update(
                status=ReadableExport.Status.FAILED, error="Could not start the export. Try again in a minute.",
            )
        row.refresh_from_db()
        return Response(_row(row), status=status.HTTP_202_ACCEPTED)


class ReadableExportFileView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request, pk: int):
        from .models import ReadableExport

        cu = get_company_user(request)
        row = ReadableExport.objects.filter(company=cu.company, pk=pk).first()
        if row is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if row.status != ReadableExport.Status.READY or not row.expires_at or row.expires_at <= timezone.now():
            return Response({"detail": "This download link has expired. Ask for a new export."},
                            status=status.HTTP_410_GONE)
        if not row.storage_path or not default_storage.exists(row.storage_path):
            return Response({"detail": "The file is gone. Ask for a new export."}, status=status.HTTP_410_GONE)
        row.downloaded_at = timezone.now()
        row.save(update_fields=["downloaded_at", "updated_at"])
        AuditService.log(
            action="tenant.export_readable_download", company=cu.company, user=request.user,
            entity_type="ReadableExport", entity_id=row.pk, description="Owner downloaded the readable export.",
        )
        resp = FileResponse(default_storage.open(row.storage_path, "rb"), content_type="application/zip",
                            as_attachment=True, filename=f"bizboard-data-{cu.company.pk}-{row.ready_at:%Y%m%d}.zip")
        resp["Cache-Control"] = "private, no-store"
        return resp
