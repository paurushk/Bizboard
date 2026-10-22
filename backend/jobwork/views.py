from datetime import date

from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.idempotency import wrap_idempotent
from core.permissions import HasCompany, get_company_user
from core.services.feature_flags import build_feature_flags
from django.http import Http404
from django.utils import timezone

from manufacturing.permissions import BadInputIs400

from .models import Itc04Filing, JobWorkChallan, JobWorkOrder, JobWorkReceipt, PrincipalMaterialMovement
from .serializers import (
    ChallanIn, Itc04FilingSerializer, JobWorkChallanSerializer, JobWorkOrderSerializer, JobWorkReceiptSerializer,
    OrderIn, PrincipalLinesIn, PrincipalMovementSerializer, ReasonIn, ReceiptIn,
)
from .services import common, itc04, out, principal

VIEW_ROLES = frozenset({"OWNER", "MANAGER", "INVENTORY_STAFF", "ACCOUNTANT", "AUDITOR", "VIEWER"})
WORK_ROLES = frozenset({"OWNER", "MANAGER", "INVENTORY_STAFF"})
REVERSE_ROLES = frozenset({"OWNER", "MANAGER"})
TAX_ROLES = frozenset({"OWNER", "ACCOUNTANT"})
BACKDATE_ROLES = frozenset({"OWNER", "MANAGER"})


def assert_job_work_enabled(company):
    flags = build_feature_flags(company=company)
    if not (flags.get("ENABLE_MANUFACTURING") and flags.get("MFG_JOB_WORK")):
        raise Http404()


class JobWorkRolePermission(BasePermission):
    message = "Your role cannot do this in Job work."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None:
            return False
        table = getattr(view, "jw_roles", {}) or {}
        action_name = getattr(view, "action", None)
        if action_name in table:
            return cu.role in table[action_name]
        if request.method in SAFE_METHODS:
            return cu.role in VIEW_ROLES
        return cu.role in WORK_ROLES


class _JW(BadInputIs400):
    permission_classes = [IsAuthenticated, HasCompany, JobWorkRolePermission]
    jw_roles = {}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_job_work_enabled(get_company_user(request).company)

    @property
    def company(self):
        return get_company_user(self.request).company

    @property
    def role(self):
        return get_company_user(self.request).role

    @property
    def can_backdate(self):
        return self.role in BACKDATE_ROLES


class OrderViewSet(_JW, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = JobWorkOrderSerializer
    jw_roles = {"close": REVERSE_ROLES}

    def get_queryset(self):
        qs = JobWorkOrder.objects.filter(company=self.company).select_related("supplier", "customer")
        for key in ("direction", "status", "supplier", "customer"):
            if self.request.query_params.get(key):
                qs = qs.filter(**{key: self.request.query_params[key]})
        return qs

    def create(self, request, *args, **kwargs):
        data = OrderIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data

        def build():
            if v["direction"] == "IN":
                order = principal.create_order(
                    self.company, request.user, customer=v.get("customer"), process=v.get("process", ""),
                    notes=v.get("notes", ""),
                )
            else:
                order = out.create_order(
                    self.company, request.user, supplier=v.get("supplier"), process=v.get("process", ""),
                    expected_return_date=v.get("expected_return_date"), notes=v.get("notes", ""),
                    direct_supply_declared=v.get("direct_supply_declared", False),
                )
            return Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)

        return wrap_idempotent(request=request, company=self.company, scope="jobwork.order.create", build=build)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return Response(self.get_serializer(out.close_order(self.get_object(), request.user)).data)

    # --- job work IN: the customer's material ---
    def _principal_call(self, request, fn):
        order = self.get_object()
        data = PrincipalLinesIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data

        def build():
            ch = fn(
                order, request.user, [dict(ln) for ln in v["lines"]], challan_date=v.get("challan_date"),
                vehicle_no=v.get("vehicle_no", ""), notes=v.get("notes", ""),
            )
            return Response(JobWorkChallanSerializer(ch).data, status=status.HTTP_201_CREATED)

        return wrap_idempotent(request=request, company=self.company, scope=f"jobwork.{fn.__name__}", build=build)

    @action(detail=True, methods=["post"], url_path="receive-material")
    def receive_material(self, request, pk=None):
        return self._principal_call(request, principal.receive_material)

    @action(detail=True, methods=["post"], url_path="return-material")
    def return_material(self, request, pk=None):
        return self._principal_call(request, principal.return_material)

    @action(detail=True, methods=["post"], url_path="record-loss")
    def record_loss(self, request, pk=None):
        order = self.get_object()
        mv = principal.record_loss(
            order, request.user, product=request.data.get("product"), qty=request.data.get("qty"),
            reference=request.data.get("reference", ""),
        )
        return Response(PrincipalMovementSerializer(mv).data, status=status.HTTP_201_CREATED)


class ChallanViewSet(_JW, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = JobWorkChallanSerializer
    jw_roles = {"reverse": REVERSE_ROLES}

    def get_queryset(self):
        qs = JobWorkChallan.objects.filter(company=self.company).select_related("order").prefetch_related("lines__product")
        for key in ("order", "status"):
            if self.request.query_params.get(key):
                qs = qs.filter(**{key: self.request.query_params[key]})
        return qs

    def create(self, request, *args, **kwargs):
        data = ChallanIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        order = JobWorkOrder.objects.filter(pk=v["order"], company=self.company).first()
        if order is None:
            raise common.rule("Job work order not found.", "JW_BAD_REFERENCE")

        def build():
            ch = out.create_challan(
                order, request.user, [dict(ln) for ln in v["lines"]], challan_date=v.get("challan_date"),
                warehouse=v.get("warehouse"), vehicle_no=v.get("vehicle_no", ""), notes=v.get("notes", ""),
            )
            return Response(self.get_serializer(ch).data, status=status.HTTP_201_CREATED)

        return wrap_idempotent(request=request, company=self.company, scope="jobwork.challan.create", build=build)

    @action(detail=True, methods=["post"])
    def issue(self, request, pk=None):
        ch = self.get_object()
        return wrap_idempotent(
            request=request, company=self.company, scope="jobwork.challan.issue",
            build=lambda: Response(self.get_serializer(out.issue_challan(ch, request.user, can_backdate=self.can_backdate)).data),
        )

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        reason = ReasonIn(data=request.data)
        reason.is_valid(raise_exception=True)
        ch = self.get_object()
        return Response(self.get_serializer(out.reverse_challan(ch, request.user, reason.validated_data["reason"])).data)


class ReceiptViewSet(_JW, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = JobWorkReceiptSerializer
    jw_roles = {"reverse": REVERSE_ROLES}

    def get_queryset(self):
        qs = JobWorkReceipt.objects.filter(company=self.company).select_related("order").prefetch_related("lines__product")
        for key in ("order", "status"):
            if self.request.query_params.get(key):
                qs = qs.filter(**{key: self.request.query_params[key]})
        return qs

    def create(self, request, *args, **kwargs):
        data = ReceiptIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        order = JobWorkOrder.objects.filter(pk=v["order"], company=self.company).first()
        if order is None:
            raise common.rule("Job work order not found.", "JW_BAD_REFERENCE")

        def build():
            rc = out.create_receipt(
                order, request.user, [dict(ln) for ln in v["lines"]], receipt_date=v.get("receipt_date"),
                warehouse=v.get("warehouse"), notes=v.get("notes", ""),
            )
            return Response(self.get_serializer(rc).data, status=status.HTTP_201_CREATED)

        return wrap_idempotent(request=request, company=self.company, scope="jobwork.receipt.create", build=build)

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        rc = self.get_object()
        return wrap_idempotent(
            request=request, company=self.company, scope="jobwork.receipt.post",
            build=lambda: Response(self.get_serializer(out.post_receipt(rc, request.user, can_backdate=self.can_backdate)).data),
        )

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        reason = ReasonIn(data=request.data)
        reason.is_valid(raise_exception=True)
        rc = self.get_object()
        return Response(self.get_serializer(out.reverse_receipt(rc, request.user, reason.validated_data["reason"])).data)


class BalanceView(_JW, APIView):
    """What job workers hold of ours, and what customers have left with us."""

    def get(self, request):
        return Response({
            "at_job_workers": out.balance_by_job_worker(self.company),
            "customers_material": principal.balance(self.company),
        })


class AgeingView(_JW, APIView):
    def get(self, request):
        as_of = request.query_params.get("as_of")
        rows = out.ageing(self.company, date.fromisoformat(as_of[:10]) if as_of else None)
        return Response({"rows": rows, "overdue": sum(1 for r in rows if r["status"] == "OVERDUE")})


class Itc04View(_JW, APIView):
    jw_roles = {}

    def _bounds(self, request):
        frm, to = request.query_params.get("from"), request.query_params.get("to")
        if not (frm and to):
            raise common.rule("Give the period: from and to dates.", "JW_BAD_PERIOD")
        return date.fromisoformat(frm[:10]), date.fromisoformat(to[:10])

    def get(self, request):
        frm, to = self._bounds(request)
        tables = itc04.build(self.company, frm, to)
        if request.query_params.get("export") == "csv":
            resp = HttpResponse(itc04.to_csv(tables), content_type="text/csv")
            resp["Content-Disposition"] = f'attachment; filename="itc04-{frm}-{to}.csv"'
            return resp
        return Response(tables)


class Itc04FilingViewSet(_JW, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = Itc04FilingSerializer
    jw_roles = {"prepare": TAX_ROLES, "mark_filed": TAX_ROLES}

    def get_queryset(self):
        return Itc04Filing.objects.filter(company=self.company)

    @action(detail=False, methods=["post"])
    def prepare(self, request):
        """Build and record the return for a period. ``fy`` is the year it starts in; ``half`` is 1 or 2 when half-yearly."""
        cfg = common.settings_for(self.company)
        try:
            fy = int(request.data.get("fy"))
        except (TypeError, ValueError):
            raise common.rule("Give the financial year, for example 2026 for 2026-27.", "JW_BAD_PERIOD")
        half = request.data.get("half")
        label, frm, to, due = itc04.period(cfg.itc04_frequency, fy, int(half) if half else None)
        filing = itc04.prepare_filing(self.company, request.user, label, frm, to)
        return Response({**self.get_serializer(filing).data, "due_date": due}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="mark-filed")
    def mark_filed(self, request, pk=None):
        filed_on = request.data.get("filed_on")
        done = itc04.mark_filed(
            self.get_object(), request.user, date.fromisoformat(filed_on[:10]) if filed_on else timezone.localdate(),
            request.data.get("acknowledgement", ""),
        )
        return Response(self.get_serializer(done).data)

    @action(detail=False, methods=["get"])
    def due(self, request):
        cfg = common.settings_for(self.company)
        rows = [
            {"label": label, "from": frm, "to": to, "due_date": due,
             "filed": Itc04Filing.objects.filter(company=self.company, period_label=label, status="FILED").exists()}
            for label, frm, to, due in itc04.periods_due(cfg.itc04_frequency, timezone.localdate())
        ]
        return Response({"frequency": cfg.itc04_frequency, "periods": rows})


class PrincipalMovementViewSet(_JW, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PrincipalMovementSerializer

    def get_queryset(self):
        qs = PrincipalMaterialMovement.objects.filter(company=self.company).select_related("principal", "product")
        for key in ("principal", "product", "kind"):
            if self.request.query_params.get(key):
                qs = qs.filter(**{key: self.request.query_params[key]})
        return qs
