"""SET-08: switch the weekly automatic backup on or off, and list the copies kept on the server."""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import IsOwner, get_company_user
from core.services.audit import AuditService

from .scheduled_backup import KEEP, last_scheduled_result, run_scheduled_backup, stored_backups


def _payload(company) -> dict:
    return {
        "enabled": bool(company.scheduled_backup_enabled),
        "keep": KEEP,
        "schedule": "Every Sunday at about 2:15 am",
        "backups": [
            {"id": f.pk, "created_at": f.created_at, "size": f.size, "name": f.original_name}
            for f in stored_backups(company)
        ],
        "last_run": last_scheduled_result(company),
    }


class BackupScheduleView(APIView):
    """GET the schedule and kept copies; PATCH ``{"enabled": bool}``; POST takes one copy now."""

    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        return Response(_payload(get_company_user(request).company))

    def patch(self, request):
        company = get_company_user(request).company
        if "enabled" not in request.data or not isinstance(request.data.get("enabled"), bool):
            raise BusinessRuleError("Send enabled as true or false.")
        company.scheduled_backup_enabled = request.data["enabled"]
        company.save(update_fields=["scheduled_backup_enabled", "updated_at"])
        AuditService.log(
            company=company,
            user=request.user,
            action="UPDATE",
            entity_type="Company",
            entity_id=company.pk,
            description="Automatic backup switched " + ("on." if company.scheduled_backup_enabled else "off."),
            metadata={"event": "tenant.backup_schedule", "enabled": company.scheduled_backup_enabled},
        )
        return Response(_payload(company))

    def post(self, request):
        company = get_company_user(request).company
        asset = run_scheduled_backup(company)
        if asset is None:
            raise BusinessRuleError("The backup could not be taken. Try again, or contact support if it keeps failing.")
        return Response(_payload(company), status=201)
