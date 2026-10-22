from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, get_company_user
from core.services.audit import AuditService
from core.viewsets import CompanyScopedViewSet

from .models import Bom, WorkOrder
from .permissions import (
    BadInputIs400,
    CLOSE_ROLES, PLAN_ROLES, REVERSE_ROLES, SETTINGS_ROLES, MfgRolePermission,
    assert_manufacturing_enabled, can_backdate, role_of,
)
from .serializers import BomSerializer, MfgSettingsSerializer, WorkOrderSerializer
from .services import cancel_work_order, complete_work_order, release_work_order
from .services import bom as bom_service
from .services import bom_import, flow
from .services.common import get_settings


class _MfgViewMixin(BadInputIs400):
    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_manufacturing_enabled(get_company_user(request).company)


class BomViewSet(_MfgViewMixin, CompanyScopedViewSet):
    queryset = Bom.objects.prefetch_related(
        "lines__component", "outputs__product", "additional_costs",
    ).select_related("product", "customer")
    serializer_class = BomSerializer
    audit_entity = "Bom"
    mfg_roles = {
        "create": PLAN_ROLES, "update": PLAN_ROLES, "partial_update": PLAN_ROLES,
        "destroy": PLAN_ROLES, "revise": PLAN_ROLES, "activate": PLAN_ROLES, "archive": PLAN_ROLES,
        "import_file": PLAN_ROLES,
    }

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("product"):
            qs = qs.filter(product_id=params["product"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("default") in ("1", "true"):
            qs = qs.filter(is_default=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        bom = self.get_object()
        if bom.is_locked or bom.work_orders.exists():
            raise BusinessRuleError(
                "This BOM revision has been used by a work order. Archive it instead of deleting it.",
                code="MFG_BOM_LOCKED",
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request):
        resp = HttpResponse(bom_import.template_csv(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="bom-import-template.csv"'
        return resp

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        resp = HttpResponse(bom_import.export_csv(self.company), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="boms.csv"'
        return resp

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser, FormParser, JSONParser])
    def import_file(self, request):
        """Upload a spreadsheet of recipes. Without ``commit=true`` it only checks the file."""
        upload = request.FILES.get("file")
        if upload is None:
            raise BusinessRuleError("Choose a file to upload.", code="MFG_IMPORT_EMPTY")
        commit = str(request.data.get("commit", "")).lower() in ("1", "true", "yes")
        activate = str(request.data.get("activate", "true")).lower() not in ("0", "false", "no")
        rows = bom_import.parse_file(upload)
        result = bom_import.run_import(self.company, request.user, rows, commit=commit, activate=activate)
        if result["errors"]:
            return Response(result, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        if result["committed"]:
            AuditService.log(
                action="mfg.bom.imported", company=self.company, user=request.user, entity_type="Bom",
                description=f"{result['created']} recipe(s) imported",
            )
        return Response(result, status=status.HTTP_201_CREATED if result["committed"] else status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        """Copy this revision into the next one, as a draft."""
        bom = self.get_object()
        new = bom_service.create_revision(bom, request.user, request.data.get("reason", ""))
        AuditService.log(
            action="mfg.bom.revised", company=bom.company, user=request.user,
            entity_type="Bom", entity_id=str(new.pk), description=f"Revision {new.revision_no} of {bom.name}",
        )
        return Response(self.get_serializer(new).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        bom = self.get_object()
        make_default = request.data.get("make_default", True)
        if isinstance(make_default, str):
            make_default = make_default.lower() not in ("0", "false", "no")
        effective_from = request.data.get("effective_from") or None
        if effective_from:
            from datetime import date

            effective_from = date.fromisoformat(str(effective_from)[:10])
        bom = bom_service.activate_revision(
            bom, request.user, make_default=bool(make_default), effective_from=effective_from,
        )
        AuditService.log(
            action="mfg.bom.activated", company=bom.company, user=request.user,
            entity_type="Bom", entity_id=str(bom.pk), description=f"Revision {bom.revision_no} active from {bom.effective_from}",
        )
        return Response(self.get_serializer(bom).data)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        bom = bom_service.archive_revision(self.get_object(), request.user)
        AuditService.log(
            action="mfg.bom.archived", company=bom.company, user=request.user,
            entity_type="Bom", entity_id=str(bom.pk), description=f"Revision {bom.revision_no} archived",
        )
        return Response(self.get_serializer(bom).data)


class WorkOrderViewSet(_MfgViewMixin, CompanyScopedViewSet):
    queryset = WorkOrder.objects.select_related("bom", "warehouse", "product").prefetch_related(
        "component_lines__component", "planned_outputs"
    )
    serializer_class = WorkOrderSerializer
    audit_entity = "WorkOrder"
    mfg_roles = {
        "cancel": REVERSE_ROLES, "destroy": REVERSE_ROLES, "close": CLOSE_ROLES, "reopen": REVERSE_ROLES,
    }

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status__in=params["status"].split(","))
        if params.get("product"):
            qs = qs.filter(product_id=params["product"])
        if params.get("due_before"):
            qs = qs.filter(due_date__lte=params["due_before"])
        return qs

    def _run(self, fn, *args, **kwargs):
        try:
            wo = fn(*args, **kwargs)
        except BusinessRuleError as exc:
            return Response(
                {"detail": str(exc), "code": exc.get_codes()}, status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(wo).data)

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        """The work orders on screen (same filters) as a spreadsheet. Costs only for roles that may see them."""
        import csv
        import io

        from core.csv_utils import csv_safe

        from .permissions import can_see_costs
        from .services.receipt import produced_so_far

        costs = can_see_costs(request)
        head = ["Number", "Item", "Status", "Planned", "Made", "Due", "Priority", "Batch", "Released", "Completed"]
        if costs:
            head += ["Material issued", "Cost received", "Variance"]
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(head)
        for wo in self.get_queryset().prefetch_related(None).order_by("-id")[:5000]:
            row = [
                csv_safe(wo.number), csv_safe(wo.product.name if wo.product_id else ""), wo.get_status_display(), wo.qty,
                produced_so_far(wo), wo.due_date or "", wo.priority, csv_safe(wo.batch_no or ""), wo.released_at or "",
                wo.completed_at or "",
            ]
            if costs:
                row += [wo.cost_issued, wo.cost_received, wo.cost_variance]
            w.writerow(row)
        resp = HttpResponse(out.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="work-orders.csv"'
        return resp

    @action(detail=True, methods=["get"], url_path="print")
    def print_sheet(self, request, pk=None):
        """The work order as a print-ready page for the floor (no costs on it)."""
        from . import printing

        return HttpResponse(printing.work_order_sheet(self.get_object()), content_type="text/html; charset=utf-8")

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        wo = self.get_object()
        return self._run(
            release_work_order, wo, request.user, component_serials=request.data.get("component_serials"),
            can_backdate=can_backdate(request),
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        wo = self.get_object()
        return self._run(complete_work_order, wo, request.user, can_backdate=can_backdate(request))

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Settle a completed order: variance report, and clear what is left in WIP."""
        return self._run(flow.close_work_order, self.get_object(), request.user, can_backdate=can_backdate(request))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._run(flow.reopen_work_order, self.get_object(), request.user, request.data.get("reason", ""))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        wo = self.get_object()
        return self._run(cancel_work_order, wo, request.user)


class MfgSettingsView(_MfgViewMixin, APIView):
    """GET the company's manufacturing settings; PATCH to change them."""

    mfg_roles = {}

    def get_serializer_context(self):
        return {"request": self.request, "view": self}

    def get(self, request):
        company = get_company_user(request).company
        return Response(MfgSettingsSerializer(get_settings(company), context=self.get_serializer_context()).data)

    def patch(self, request):
        if role_of(request) not in SETTINGS_ROLES:
            return Response({"detail": "Your role cannot change manufacturing settings."}, status=403)
        company = get_company_user(request).company
        row = get_settings(company)
        ser = MfgSettingsSerializer(row, data=request.data, partial=True, context=self.get_serializer_context())
        ser.is_valid(raise_exception=True)
        new_mode = ser.validated_data.get("default_issue_mode")
        if new_mode and new_mode != row.default_issue_mode:
            in_flight = WorkOrder.objects.filter(
                company=company, status__in=["RELEASED", "IN_PROGRESS"],
            ).exists()
            if in_flight:
                raise BusinessRuleError(
                    "Finish or cancel the released work orders before changing how materials are issued.",
                    code="MFG_MODE_SWITCH_BLOCKED",
                )
        ser.save(updated_by=request.user)
        AuditService.log(
            action="mfg.settings.changed", company=company, user=request.user,
            entity_type="MfgSettings", entity_id=str(row.pk), description="Manufacturing settings changed",
        )
        return Response(ser.data)
