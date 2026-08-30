import csv
import io
from datetime import date

from django.http import HttpResponse
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import CanExport, CanImport, HasCompany, IsOwner, get_company_user
from core.services.audit import AuditService
from core.services.feature_flags import build_feature_flags
from core.services.gsp_secrets import decrypt_gsp_credentials, encrypt_gsp_credentials
from integrations.models import IntegrationConnection, IntegrationSyncRun
from integrations.permissions import assert_tally_enabled
from integrations.tally.adapter import (
    DISCLAIMER,
    build_tally_export_csv,
    commit_tally_preview,
    create_upload_run,
    push_masters_http,
    push_vouchers_http,
    update_tally_preview,
)


def _parse_iso_date(val):
    if not val:
        return None
    try:
        return date.fromisoformat(str(val).strip()[:10])
    except (ValueError, TypeError):
        return None


class TallyUploadView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanImport]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        cu = get_company_user(request)
        assert_tally_enabled(cu.company)
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "file required"}, status=status.HTTP_400_BAD_REQUEST)
        run = create_upload_run(cu.company, request.user, f)
        return Response({
            "sync_run_id": run.id,
            "status": run.status,
            "preview": run.preview,
            "errors": run.errors,
            "disclaimer": DISCLAIMER,
        }, status=status.HTTP_201_CREATED)


class TallyPreviewView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanImport]

    def post(self, request):
        cu = get_company_user(request)
        assert_tally_enabled(cu.company)
        run_id = request.data.get("sync_run_id") or request.data.get("syncRunId")
        try:
            run = IntegrationSyncRun.objects.get(pk=run_id, company=cu.company)
        except IntegrationSyncRun.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        preview = request.data.get("preview")
        if isinstance(preview, dict):
            try:
                run = update_tally_preview(cu.company, run, preview)
            except BusinessRuleError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            run.status = IntegrationSyncRun.Status.PREVIEWED
            run.save(update_fields=["status", "updated_at"])
        return Response({
            "sync_run_id": run.id,
            "preview": run.preview,
            "errors": run.errors,
            "disclaimer": DISCLAIMER,
        })


class TallyCommitView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanImport]

    def post(self, request):
        cu = get_company_user(request)
        assert_tally_enabled(cu.company)
        run_id = request.data.get("sync_run_id") or request.data.get("syncRunId")
        force = bool(request.data.get("force"))
        # BB-000452/411: force= bypasses preview errors — Owner-only + audit.
        if force and cu.role != "OWNER":
            return Response(
                {"detail": "force=true requires Owner."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            run = IntegrationSyncRun.objects.get(pk=run_id, company=cu.company)
        except IntegrationSyncRun.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            result = commit_tally_preview(cu.company, request.user, run, force=force)
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if force:
            AuditService.log(
                company=cu.company,
                user=request.user,
                action="UPDATE",
                entity_type="IntegrationSyncRun",
                entity_id=run.id,
                description="Tally commit force=true",
            )
        return Response({"sync_run_id": run.id, "result": result, "disclaimer": DISCLAIMER})


class TallyExportView(APIView):
    # BB-000137: CSV export requires CanExport (not merely CanImport).
    permission_classes = [IsAuthenticated, HasCompany, CanExport]

    def get(self, request):
        cu = get_company_user(request)
        assert_tally_enabled(cu.company)
        date_from = request.query_params.get("date_from") or request.query_params.get("dateFrom")
        date_to = request.query_params.get("date_to") or request.query_params.get("dateTo")
        df = _parse_iso_date(date_from)
        dt = _parse_iso_date(date_to)
        content = build_tally_export_csv(cu.company, date_from=df, date_to=dt)
        resp = HttpResponse(content, content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="bizboard_tally_export_aid.csv"'
        resp["X-BizBoard-Disclaimer"] = DISCLAIMER[:200]
        return resp


class TallyErrorsView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanImport]

    def get(self, request, pk):
        cu = get_company_user(request)
        assert_tally_enabled(cu.company)
        try:
            run = IntegrationSyncRun.objects.get(pk=pk, company=cu.company)
        except IntegrationSyncRun.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        fmt = (request.query_params.get("as") or request.query_params.get("download") or "json").lower()
        errors = run.errors or []
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["row", "error"])
            for err in errors:
                if isinstance(err, dict):
                    writer.writerow([err.get("row", ""), err.get("error", "")])
                else:
                    writer.writerow(["", str(err)])
            resp = HttpResponse(buf.getvalue(), content_type="text/csv")
            resp["Content-Disposition"] = f'attachment; filename="tally_errors_{pk}.csv"'
            return resp
        return Response({"errors": errors, "error_rows": len(errors)})


class TallyHttpPushView(APIView):
    """One-shot Tally XML export dump — not live or incremental sync (BB-000628)."""

    permission_classes = [IsAuthenticated, HasCompany, CanExport]

    def post(self, request):
        cu = get_company_user(request)
        assert_tally_enabled(cu.company)
        kind = (request.data.get("kind") or request.data.get("type") or "masters").lower()
        base_url = request.data.get("base_url") or request.data.get("baseUrl")
        date_from = request.data.get("date_from") or request.data.get("dateFrom")
        date_to = request.data.get("date_to") or request.data.get("dateTo")
        df = _parse_iso_date(date_from)
        dt = _parse_iso_date(date_to)
        try:
            if kind == "vouchers":
                result = push_vouchers_http(cu.company, date_from=df, date_to=dt, base_url=base_url)
            else:
                result = push_masters_http(cu.company, base_url=base_url)
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        result["mode"] = "export_dump"
        result["sync"] = False
        return Response(result)


class WhatsAppConnectionView(APIView):
    """Owner-only WhatsApp Cloud connection upsert/delete (BB-000678)."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        cu = get_company_user(request)
        conn = IntegrationConnection.objects.filter(
            company=cu.company, provider=IntegrationConnection.Provider.WHATSAPP,
        ).first()
        if conn is None:
            return Response({
                "configured": False,
                "status": None,
                "phone_number_id_masked": "",
                "cloud_enabled": bool(build_feature_flags(company=cu.company).get("ENABLE_WHATSAPP_CLOUD")),
            })
        creds = decrypt_gsp_credentials(conn.encrypted_secrets) if conn.encrypted_secrets else {}
        phone_id = (
            creds.get("phone_number_id")
            or creds.get("phoneNumberId")
            or creds.get("whatsapp_phone_number_id")
            or ""
        )
        masked = (phone_id[:2] + "…" + phone_id[-2:]) if len(phone_id) > 4 else ("…" if phone_id else "")
        return Response({
            "configured": bool((conn.encrypted_secrets or "").strip()),
            "status": conn.status,
            "phone_number_id_masked": masked,
            "cloud_enabled": bool(build_feature_flags(company=cu.company).get("ENABLE_WHATSAPP_CLOUD")),
        })

    def put(self, request):
        cu = get_company_user(request)
        if not build_feature_flags(company=cu.company).get("ENABLE_WHATSAPP_CLOUD"):
            return Response(
                {"detail": "WhatsApp Cloud is not enabled."},
                status=status.HTTP_404_NOT_FOUND,
            )
        token = (
            request.data.get("token")
            or request.data.get("access_token")
            or request.data.get("whatsapp_token")
            or ""
        ).strip()
        phone_number_id = (
            request.data.get("phone_number_id")
            or request.data.get("phoneNumberId")
            or ""
        ).strip()
        if not token or not phone_number_id:
            return Response(
                {"detail": "token and phone_number_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        encrypted = encrypt_gsp_credentials({
            "token": token,
            "phone_number_id": phone_number_id,
        })
        conn, _ = IntegrationConnection.objects.update_or_create(
            company=cu.company,
            provider=IntegrationConnection.Provider.WHATSAPP,
            defaults={
                "status": IntegrationConnection.Status.ACTIVE,
                "encrypted_secrets": encrypted,
                "updated_by": request.user,
                "created_by": request.user,
            },
        )
        AuditService.log(
            company=cu.company,
            user=request.user,
            action="UPSERT",
            entity_type="WhatsAppConnection",
            entity_id=str(conn.pk),
        )
        return Response({"configured": True, "status": conn.status})

    def delete(self, request):
        cu = get_company_user(request)
        deleted, _ = IntegrationConnection.objects.filter(
            company=cu.company, provider=IntegrationConnection.Provider.WHATSAPP,
        ).delete()
        return Response({"configured": False, "deleted": bool(deleted)})
