"""Planning endpoints (MFG-14..19). All sit behind the MFG_PLANNING flag."""

from datetime import date

from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user
from core.services.audit import AuditService
from masters.models import Product
from sales.models import SalesOrder

from .models import MrpLine, MrpRun, WorkOrder
from .permissions import (
    PLAN_ROLES, BadInputIs400, WORK_ROLES, MfgRolePermission, assert_manufacturing_enabled, assert_sub_flag,
    can_see_costs,
)
from .services import planning
from .services.common import rule


def _prod(p):
    return {"id": p.pk, "name": p.name, "sku": p.sku}


def _get_product(request, company, key="product"):
    pk = request.query_params.get(key) or request.data.get(key)
    prod = Product.objects.filter(pk=pk, company=company).first() if pk else None
    if prod is None:
        raise rule("Choose a product.", "MFG_BAD_REFERENCE")
    return prod


class _PlanningView(BadInputIs400, APIView):
    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]
    mfg_roles = {}
    flag = "MFG_PLANNING"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        company = get_company_user(request).company
        assert_manufacturing_enabled(company)
        if self.flag:
            assert_sub_flag(company, self.flag)

    @property
    def company(self):
        return get_company_user(self.request).company


class ExplodeView(_PlanningView):
    """GET ?product=&qty=&expand=all|phantom|none: the indented materials list."""

    def get(self, request):
        product = _get_product(request, self.company)
        qty = request.query_params.get("qty") or 1
        rows = planning.explode(
            self.company, product, qty, expand=request.query_params.get("expand", "all"),
        )
        data = [{**r, "product": _prod(r["product"])} for r in rows]
        return Response({"product": _prod(product), "qty": qty, "rows": data})


class WhereUsedView(_PlanningView):
    def get(self, request):
        product = _get_product(request, self.company)
        return Response({"product": _prod(product), "used_in": planning.where_used(self.company, product)})


class CostRollupView(_PlanningView):
    def get(self, request):
        if not can_see_costs(request):
            raise PermissionDenied("Your role cannot see costs.", code="MFG_NO_COST_ACCESS")
        product = _get_product(request, self.company)
        return Response(planning.rollup_cost(
            self.company, product, request.query_params.get("qty") or 1,
            method=request.query_params.get("method", "CURRENT"),
        ))


class CanMakeView(_PlanningView):
    def get(self, request):
        product = _get_product(request, self.company)
        return Response(planning.max_producible(self.company, product))


class ShortagesView(_PlanningView):
    def get(self, request):
        data = []
        for entry in planning.open_order_shortages(self.company):
            wo = entry["work_order"]
            data.append({
                "work_order": {"id": wo.pk, "number": wo.number, "due_date": wo.due_date, "priority": wo.priority},
                "lines": [{**ln, "product": _prod(ln["product"])} for ln in entry["lines"]],
            })
        return Response({"orders": data})


class AtpView(_PlanningView):
    def get(self, request):
        product = _get_product(request, self.company)
        when = request.query_params.get("date")
        as_of = date.fromisoformat(when[:10]) if when else timezone.localdate()
        return Response(planning.available_to_promise(self.company, product, as_of))


class BoardView(_PlanningView):
    def get(self, request):
        return Response({"orders": planning.board(self.company)})


class SalesOrderStatusView(_PlanningView):
    """What production is doing for a sales order. Sales staff may read this."""

    flag = "MFG_PLANNING"

    def get_permissions(self):
        return [IsAuthenticated(), HasCompany()]

    def get(self, request):
        company = self.company
        so = SalesOrder.objects.filter(pk=request.query_params.get("sales_order"), company=company).first()
        if so is None:
            raise rule("Choose a sales order.", "MFG_BAD_REFERENCE")
        return Response({"sales_order": so.pk, "lines": planning.production_status_for_order(so)})


class CreateFromSalesOrderView(_PlanningView):
    mfg_roles = {}

    def post(self, request):
        so = SalesOrder.objects.filter(pk=request.data.get("sales_order"), company=self.company).first()
        if so is None:
            raise rule("Choose a sales order.", "MFG_BAD_REFERENCE")
        created, skipped = planning.create_orders_from_sales_order(so, request.user)
        AuditService.log(
            action="mfg.wo.from_sales_order", company=self.company, user=request.user, entity_type="SalesOrder",
            entity_id=str(so.pk), description=f"{len(created)} work order(s) for {so.number or so.pk}",
        )
        return Response(
            {"created": [{"id": w.pk, "number": w.number, "qty": w.qty} for w in created], "skipped": skipped},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class WorkOrderAvailabilityView(_PlanningView):
    def get(self, request, pk):
        wo = WorkOrder.objects.filter(pk=pk, company=self.company).first()
        if wo is None:
            raise rule("Work order not found.", "MFG_BAD_REFERENCE")
        rows = planning.work_order_availability(wo)
        return Response({"work_order": wo.pk, "lines": [
            {**r, "product": _prod(r["product"]), "alternates": [
                {"product": _prod(a["product"]), "free": a["free"]} for a in r["alternates"]
            ]} for r in rows
        ]})


class SetPriorityView(_PlanningView):
    def post(self, request, pk):
        wo = WorkOrder.objects.filter(pk=pk, company=self.company).first()
        if wo is None:
            raise rule("Work order not found.", "MFG_BAD_REFERENCE")
        try:
            priority = int(request.data.get("priority"))
        except (TypeError, ValueError):
            raise rule("Priority is from 1 (most urgent) to 5.", "MFG_BAD_PRIORITY")
        if not 1 <= priority <= 5:
            raise rule("Priority is from 1 (most urgent) to 5.", "MFG_BAD_PRIORITY")
        before = wo.priority
        reason = request.data.get("delay_reason") or ""
        if reason and reason not in WorkOrder.DelayReason.values:
            raise rule("Unknown delay reason.", "MFG_BAD_DELAY_REASON")
        wo.priority = priority
        if reason:
            wo.delay_reason = reason
        if request.data.get("due_date"):
            wo.due_date = date.fromisoformat(str(request.data["due_date"])[:10])
        wo.updated_by = request.user
        wo.save(update_fields=["priority", "delay_reason", "due_date", "updated_at", "updated_by"])
        AuditService.log(
            action="mfg.wo.reprioritised", company=self.company, user=request.user, entity_type="WorkOrder",
            entity_id=str(wo.pk), description=f"{wo.number}: priority {before} to {priority}",
        )
        return Response({"id": wo.pk, "priority": wo.priority, "due_date": wo.due_date, "delay_reason": wo.delay_reason})


# --- material planning runs ------------------------------------------------------------------

def _line(ln: MrpLine):
    return {
        "id": ln.pk, "product": _prod(ln.product), "kind": ln.kind, "level": ln.level, "need_date": ln.need_date,
        "order_by": ln.order_by, "lead_time_days": ln.lead_time_days, "gross_qty": ln.gross_qty,
        "safety_qty": ln.safety_qty, "on_hand_qty": ln.on_hand_qty, "incoming_qty": ln.incoming_qty,
        "net_qty": ln.net_qty, "suggested_qty": ln.suggested_qty,
        "supplier": {"id": ln.supplier_id, "name": ln.supplier.name} if ln.supplier_id else None,
        "sources": ln.sources, "status": ln.status, "converted_type": ln.converted_type,
        "converted_id": ln.converted_id, "note": ln.note,
    }


def _run(run: MrpRun, with_lines=False):
    data = {
        "id": run.pk, "number": run.number, "as_of": run.as_of, "horizon_days": run.horizon_days,
        "status": run.status, "summary": run.summary, "created_at": run.created_at,
    }
    if with_lines:
        data["lines"] = [_line(ln) for ln in run.lines.select_related("product", "supplier")]
    return data


class MrpRunViewSet(BadInputIs400, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]
    mfg_roles = {"convert": PLAN_ROLES, "run": WORK_ROLES}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        company = get_company_user(request).company
        assert_manufacturing_enabled(company)
        assert_sub_flag(company, "MFG_PLANNING")

    @property
    def company(self):
        return get_company_user(self.request).company

    def get_queryset(self):
        return MrpRun.objects.filter(company=self.company)

    def list(self, request, *args, **kwargs):
        return Response([_run(r) for r in self.get_queryset()[:50]])

    def retrieve(self, request, *args, **kwargs):
        return Response(_run(self.get_object(), with_lines=True))

    @action(detail=False, methods=["post"])
    def run(self, request):
        """Plan material now. Nothing is created until suggestions are converted."""
        try:
            horizon = int(request.data.get("horizon_days", 30))
        except (TypeError, ValueError):
            raise rule("Horizon must be a number of days.", "MFG_BAD_QTY")
        run = planning.run_mrp(self.company, request.user, horizon_days=max(0, min(horizon, 365)))
        return Response(_run(run, with_lines=True), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        run = self.get_object()
        if run.status != MrpRun.Status.DONE:
            raise rule("A newer plan has replaced this one. Use the latest.", "MFG_MRP_SUPERSEDED")
        result = planning.convert_mrp_lines(
            run, request.user, request.data.get("lines"),
            {int(k): v for k, v in (request.data.get("suppliers") or {}).items()},
        )
        AuditService.log(
            action="mfg.mrp.converted", company=self.company, user=request.user, entity_type="MrpRun",
            entity_id=str(run.pk),
            description=f"{len(result['purchase_orders'])} purchase order(s), {len(result['work_orders'])} work order(s)",
        )
        return Response({
            "purchase_orders": [{"id": p.pk, "supplier": p.supplier.name} for p in result["purchase_orders"]],
            "work_orders": [{"id": w.pk, "number": w.number} for w in result["work_orders"]],
            "skipped": result["skipped"],
        }, status=status.HTTP_201_CREATED)
