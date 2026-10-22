"""Shop-floor endpoints (MFG-33..36), behind the MFG_SHOP_FLOOR flag, plus the PIN-signed tablet API."""

from datetime import date

from django.http import Http404
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user
from core.serializers import CompanyPrimaryKeyRelatedField
from core.services.feature_flags import build_feature_flags
from core.viewsets import CompanyScopedViewSet
from masters.models import Supplier

from .models import (
    Bom, DowntimeEvent, DowntimeReason, JobCard, Machine, MaintenanceLog, MaintenancePlan, Operator,
    WorkCentre, WorkOrder,
)
from .permissions import (
    BadInputIs400,
    PLAN_ROLES, REVERSE_ROLES, WORK_ROLES, MfgRolePermission, assert_manufacturing_enabled, assert_sub_flag, role_of,
)
from .services import shopfloor, subcontract
from .services.common import rule


class _Floor(BadInputIs400):
    permission_classes = [IsAuthenticated, HasCompany, MfgRolePermission]
    mfg_roles = {}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        company = get_company_user(request).company
        assert_manufacturing_enabled(company)
        assert_sub_flag(company, "MFG_SHOP_FLOOR")

    @property
    def company(self):
        return get_company_user(self.request).company


_SETUP = {a: PLAN_ROLES for a in ("create", "update", "partial_update", "destroy")}


class WorkCentreSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkCentre
        fields = ["id", "code", "name", "kind", "hours_per_day", "labour_rate", "machine_rate", "overhead_rate", "is_active"]


class WorkCentreViewSet(_Floor, CompanyScopedViewSet):
    queryset = WorkCentre.objects.all()
    serializer_class = WorkCentreSerializer
    audit_entity = "WorkCentre"
    mfg_roles = _SETUP


class DowntimeReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = DowntimeReason
        fields = ["id", "code", "name", "is_planned", "is_active"]


class DowntimeReasonViewSet(_Floor, CompanyScopedViewSet):
    queryset = DowntimeReason.objects.all()
    serializer_class = DowntimeReasonSerializer
    audit_entity = "DowntimeReason"
    mfg_roles = _SETUP


class MachineSerializer(serializers.ModelSerializer):
    work_centre = CompanyPrimaryKeyRelatedField(queryset=WorkCentre.objects.all(), allow_null=True, required=False)

    class Meta:
        model = Machine
        fields = ["id", "code", "name", "work_centre", "run_hours", "is_active", "notes"]
        read_only_fields = ["run_hours"]


class MachineViewSet(_Floor, CompanyScopedViewSet):
    queryset = Machine.objects.all()
    serializer_class = MachineSerializer
    audit_entity = "Machine"
    mfg_roles = {**_SETUP, "breakdown": WORK_ROLES}

    @action(detail=True, methods=["post"])
    def breakdown(self, request, pk=None):
        log = shopfloor.report_breakdown(self.company, request.user, machine=self.get_object(), description=request.data.get("description", ""))
        return Response(MaintenanceLogSerializer(log).data, status=status.HTTP_201_CREATED)


class MaintenancePlanSerializer(serializers.ModelSerializer):
    machine = CompanyPrimaryKeyRelatedField(queryset=Machine.objects.all())

    class Meta:
        model = MaintenancePlan
        fields = ["id", "machine", "name", "interval_days", "interval_hours", "last_done_on", "last_done_hours", "is_active"]
        read_only_fields = ["last_done_on", "last_done_hours"]

    def validate(self, attrs):
        if not (attrs.get("interval_days") or attrs.get("interval_hours")):
            if not self.instance:
                raise serializers.ValidationError("Give an interval in days, in machine hours, or both.")
        return attrs


class MaintenancePlanViewSet(_Floor, CompanyScopedViewSet):
    queryset = MaintenancePlan.objects.select_related("machine")
    serializer_class = MaintenancePlanSerializer
    audit_entity = "MaintenancePlan"
    mfg_roles = {**_SETUP, "complete": WORK_ROLES}

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        done = request.data.get("done_on")
        log = shopfloor.complete_preventive(
            self.get_object(), request.user, done_on=date.fromisoformat(done[:10]) if done else None,
            cost=request.data.get("cost", 0), notes=request.data.get("notes", ""),
        )
        return Response(MaintenanceLogSerializer(log).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def due(self, request):
        return Response({"plans": shopfloor.maintenance_due(self.company)})


class MaintenanceLogSerializer(serializers.ModelSerializer):
    machine_name = serializers.CharField(source="machine.name", read_only=True)

    class Meta:
        model = MaintenanceLog
        fields = ["id", "machine", "machine_name", "plan", "kind", "reported_at", "resolved_at", "description", "cost", "downtime_minutes"]
        read_only_fields = fields


class MaintenanceLogViewSet(_Floor, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = MaintenanceLogSerializer
    mfg_roles = {"resolve": WORK_ROLES}

    def get_queryset(self):
        qs = MaintenanceLog.objects.filter(company=self.company).select_related("machine")
        if self.request.query_params.get("open") in ("1", "true"):
            qs = qs.filter(resolved_at__isnull=True)
        return qs

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        log = shopfloor.resolve_breakdown(self.get_object(), request.user, cost=request.data.get("cost", 0), notes=request.data.get("notes", ""))
        return Response(self.get_serializer(log).data)


class DowntimeEventSerializer(serializers.ModelSerializer):
    reason_name = serializers.CharField(source="reason.name", read_only=True)
    work_centre_code = serializers.CharField(source="work_centre.code", read_only=True)

    class Meta:
        model = DowntimeEvent
        fields = ["id", "work_centre", "work_centre_code", "job_card", "reason", "reason_name", "started_at", "ended_at", "minutes", "notes"]
        read_only_fields = fields


class DowntimeViewSet(_Floor, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = DowntimeEventSerializer
    mfg_roles = {"start": WORK_ROLES, "end": WORK_ROLES}

    def get_queryset(self):
        qs = DowntimeEvent.objects.filter(company=self.company).select_related("reason", "work_centre")
        if self.request.query_params.get("open") in ("1", "true"):
            qs = qs.filter(ended_at__isnull=True)
        return qs

    @action(detail=False, methods=["post"])
    def start(self, request):
        wc = WorkCentre.objects.filter(pk=request.data.get("work_centre"), company=self.company).first()
        reason = DowntimeReason.objects.filter(pk=request.data.get("reason"), company=self.company).first()
        if wc is None or reason is None:
            raise rule("Choose the work centre and the reason.", "MFG_BAD_REFERENCE")
        ev = shopfloor.start_downtime(self.company, request.user, work_centre=wc, reason=reason, notes=request.data.get("notes", ""))
        return Response(self.get_serializer(ev).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        return Response(self.get_serializer(shopfloor.end_downtime(self.get_object(), request.user)).data)


class JobCardSerializer(serializers.ModelSerializer):
    work_centre_code = serializers.CharField(source="work_centre.code", read_only=True)
    work_order_number = serializers.CharField(source="work_order.number", read_only=True)
    running = serializers.SerializerMethodField()

    class Meta:
        model = JobCard
        fields = [
            "id", "work_order", "work_order_number", "sequence", "name", "work_centre", "work_centre_code", "status",
            "qty_planned", "qty_good", "qty_rejected", "planned_minutes", "minutes_worked", "started_at", "finished_at",
            "labour_cost", "machine_cost", "overhead_cost", "is_subcontract", "running",
            "jobwork_order_id", "outside_cost",
        ]
        read_only_fields = fields

    def get_running(self, obj):
        return obj.time_logs.filter(ended_at__isnull=True).exists()


class JobCardViewSet(_Floor, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = JobCardSerializer
    mfg_roles = {"reopen": REVERSE_ROLES}

    def get_queryset(self):
        qs = JobCard.objects.filter(company=self.company).select_related("work_centre", "work_order")
        for key in ("work_order", "status", "work_centre"):
            if self.request.query_params.get(key):
                qs = qs.filter(**{key: self.request.query_params[key]})
        return qs

    @action(detail=False, methods=["post"], url_path="create-for-order")
    def create_for_order(self, request):
        wo = WorkOrder.objects.filter(pk=request.data.get("work_order"), company=self.company).first()
        if wo is None:
            raise rule("Work order not found.", "MFG_BAD_REFERENCE")
        cards = shopfloor.create_job_cards(wo, request.user)
        return Response(self.get_serializer(cards, many=True).data, status=status.HTTP_201_CREATED)

    def _do(self, request, fn, **kw):
        return Response(self.get_serializer(fn(self.get_object(), user=request.user, **kw)).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._do(request, shopfloor.start_card)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        return self._do(request, shopfloor.pause_card)

    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        return self._do(request, shopfloor.report_card, qty_good=request.data.get("qty_good", 0), qty_rejected=request.data.get("qty_rejected", 0))

    @action(detail=True, methods=["post"])
    def finish(self, request, pk=None):
        return self._do(request, shopfloor.finish_card, qty_good=request.data.get("qty_good", 0), qty_rejected=request.data.get("qty_rejected", 0))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return Response(self.get_serializer(shopfloor.reopen_card(self.get_object(), request.user)).data)

    def _outside(self):
        assert_sub_flag(self.company, "MFG_JOB_WORK")
        return self.get_object()

    @action(detail=True, methods=["get"], url_path="subcontract-defaults")
    def subcontract_defaults(self, request, pk=None):
        """What would go out for this step: the material the order still has to take, and the usual job worker."""
        card = self._outside()
        op = card.operation
        return Response({
            "supplier": op.subcontract_supplier_id if op is not None else None,
            "lines": [{"product": ln["product"], "qty": str(ln["qty"])} for ln in subcontract.default_lines(card.work_order)],
        })

    @action(detail=True, methods=["post"])
    def subcontract(self, request, pk=None):
        """Raise the job-work order and challan for a step done by a job worker."""
        from core.idempotency import wrap_idempotent
        from jobwork.serializers import ChallanLineIn, JobWorkChallanSerializer, JobWorkOrderSerializer

        class SubcontractIn(serializers.Serializer):
            supplier = serializers.IntegerField(required=False, allow_null=True)
            lines = ChallanLineIn(many=True, required=False)
            expected_return_date = serializers.DateField(required=False, allow_null=True)
            challan_date = serializers.DateField(required=False, allow_null=True)
            warehouse = serializers.IntegerField(required=False, allow_null=True)
            vehicle_no = serializers.CharField(required=False, allow_blank=True, max_length=20)
            notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
            issue = serializers.BooleanField(required=False)

        card = self._outside()
        data = SubcontractIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        worker = None
        if v.get("supplier"):
            worker = Supplier.objects.filter(pk=v["supplier"], company=self.company).first()
            if worker is None:
                raise rule("Job worker not found.", "MFG_BAD_REFERENCE")

        def build():
            order, challan = subcontract.send_out(
                card, request.user, supplier=worker, lines=[dict(ln) for ln in v.get("lines", [])] or None,
                expected_return_date=v.get("expected_return_date"), challan_date=v.get("challan_date"),
                vehicle_no=v.get("vehicle_no", ""), warehouse=v.get("warehouse"), notes=v.get("notes", ""),
                issue=bool(v.get("issue")), can_backdate=role_of(request) in PLAN_ROLES,
            )
            card.refresh_from_db()
            return Response({
                "card": self.get_serializer(card).data,
                "order": JobWorkOrderSerializer(order).data,
                "challan": JobWorkChallanSerializer(challan).data,
            }, status=status.HTTP_201_CREATED)

        return wrap_idempotent(request=request, company=self.company, scope="mfg.jobcard.subcontract", build=build)


class OperatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Operator
        fields = ["id", "code", "name", "is_active", "locked_until"]
        read_only_fields = ["locked_until"]


class OperatorViewSet(_Floor, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OperatorSerializer
    mfg_roles = {"create": PLAN_ROLES, "set_pin": PLAN_ROLES, "deactivate": PLAN_ROLES, "activate": PLAN_ROLES}

    def get_queryset(self):
        return Operator.objects.filter(company=self.company)

    def create(self, request, *args, **kwargs):
        op = shopfloor.create_operator(
            self.company, request.user, code=request.data.get("code", ""), name=request.data.get("name", ""), pin=request.data.get("pin"),
        )
        return Response(self.get_serializer(op).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="set-pin")
    def set_pin(self, request, pk=None):
        shopfloor.set_pin(self.get_object(), request.data.get("pin"))
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        op = self.get_object()
        op.is_active = False
        op.save(update_fields=["is_active", "updated_at"])
        return Response(self.get_serializer(op).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        op = self.get_object()
        op.is_active = True
        op.failed_attempts, op.locked_until = 0, None
        op.save(update_fields=["is_active", "failed_attempts", "locked_until", "updated_at"])
        return Response(self.get_serializer(op).data)


class RoutingView(_Floor, APIView):
    """GET or PUT a BOM revision's routing (its operations in order)."""

    mfg_roles = {}

    def _bom(self, pk):
        bom = Bom.objects.filter(pk=pk, company=self.company).first()
        if bom is None:
            raise rule("Recipe not found.", "MFG_BAD_REFERENCE")
        return bom

    @staticmethod
    def _row(op):
        return {
            "id": op.pk, "sequence": op.sequence, "name": op.name, "work_centre": op.work_centre_id,
            "work_centre_code": op.work_centre.code, "setup_minutes": op.setup_minutes,
            "run_minutes_per_unit": op.run_minutes_per_unit, "is_subcontract": op.is_subcontract,
            "subcontract_supplier": op.subcontract_supplier_id, "notes": op.notes,
        }

    def get(self, request, pk):
        bom = self._bom(pk)
        return Response({"bom": bom.pk, "operations": [self._row(o) for o in bom.operations.select_related("work_centre")]})

    def put(self, request, pk):
        if role_of(request) not in PLAN_ROLES:
            return Response({"detail": "Only a manager can change a routing."}, status=403)
        bom = self._bom(pk)
        ops = request.data.get("operations") or []
        if any(o.get("subcontract_supplier") and not Supplier.objects.filter(pk=o["subcontract_supplier"], company=self.company).exists() for o in ops):
            raise rule("The job worker was not found.", "MFG_BAD_REFERENCE")
        shopfloor.set_routing(bom, ops, request.user)
        return Response({"bom": bom.pk, "operations": [self._row(o) for o in bom.operations.select_related("work_centre")]})


class LoadView(_Floor, APIView):
    def get(self, request):
        start = request.query_params.get("from")
        return Response(shopfloor.load(
            self.company, date.fromisoformat(start[:10]) if start else None, int(request.query_params.get("days", 14)),
        ))


class UtilisationView(_Floor, APIView):
    def get(self, request):
        frm, to = request.query_params.get("from"), request.query_params.get("to")
        if not (frm and to):
            raise rule("Give the period: from and to dates.", "MFG_BAD_PERIOD")
        f, t = date.fromisoformat(frm[:10]), date.fromisoformat(to[:10])
        return Response({
            "work_centres": shopfloor.utilisation(self.company, f, t),
            "people": shopfloor.labour_productivity(self.company, f, t),
        })


# --- tablet API: operators sign in with a code and PIN, no account ---------------------------------

class OperatorLoginThrottle(AnonRateThrottle):
    scope = "operator_login"
    rate = "30/min"


class OperatorTokenPermission(BasePermission):
    """The request carries a valid, unexpired tablet token for an active operator of a company with shop floor on."""

    message = "Sign in with your operator code and PIN."

    def has_permission(self, request, view):
        token = request.headers.get("X-Operator-Token", "")
        operator = shopfloor.operator_from_token(token) if token else None
        if operator is None:
            return False
        flags = build_feature_flags(company=operator.company)
        if not (flags.get("ENABLE_MANUFACTURING") and flags.get("MFG_SHOP_FLOOR")):
            raise Http404()
        request.operator = operator
        return True


class TabletLoginView(BadInputIs400, APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [OperatorLoginThrottle]

    def post(self, request):
        company_id = request.data.get("company")
        try:
            company_id = int(company_id)
        except (TypeError, ValueError):
            raise rule("Wrong code or PIN.", "MFG_LOGIN_FAILED")
        token, op = shopfloor.operator_login(company_id, request.data.get("code"), request.data.get("pin"))
        flags = build_feature_flags(company=op.company)
        if not (flags.get("ENABLE_MANUFACTURING") and flags.get("MFG_SHOP_FLOOR")):
            raise Http404()
        return Response({"token": token, "operator": {"id": op.pk, "name": op.name}, "expires_in": shopfloor.TOKEN_MAX_AGE})


class _Tablet(BadInputIs400, APIView):
    authentication_classes = []
    permission_classes = [OperatorTokenPermission]


class TabletCardsView(_Tablet):
    """The job cards an operator can pick up: not finished, on running orders."""

    def get(self, request):
        op = request.operator
        qs = JobCard.objects.filter(
            company=op.company, status__in=["PLANNED", "IN_PROGRESS", "PAUSED"],
            work_order__status__in=["RELEASED", "IN_PROGRESS"], is_subcontract=False,
        ).select_related("work_centre", "work_order").order_by("work_order__due_date", "work_order__priority", "sequence")
        if request.query_params.get("work_centre"):
            qs = qs.filter(work_centre_id=request.query_params["work_centre"])
        return Response({"cards": JobCardSerializer(qs[:100], many=True).data})


def _occurred_at(request):
    """When the tap happened, for a tablet that was offline. Missing or unreadable means now."""
    from django.utils.dateparse import parse_datetime

    raw = request.data.get("occurred_at")
    return parse_datetime(raw) if isinstance(raw, str) else None


def _replayable(request, op, scope, build):
    """A tablet that lost its connection resends the same tap with the same key; the first answer comes back."""
    from core.idempotency import wrap_idempotent

    return wrap_idempotent(request=request, company=op.company, scope=f"mfg.tablet.{scope}", build=build)


class TabletCardActionView(_Tablet):
    ACTIONS = {"start": shopfloor.start_card, "pause": shopfloor.pause_card, "report": shopfloor.report_card, "finish": shopfloor.finish_card}

    def post(self, request, pk, verb):
        fn = self.ACTIONS.get(verb)
        if fn is None:
            raise Http404()
        op = request.operator
        card = JobCard.objects.filter(pk=pk, company=op.company).first()
        if card is None:
            raise Http404()
        kwargs = {"operator": op}
        if verb in ("report", "finish"):
            kwargs.update(qty_good=request.data.get("qty_good", 0), qty_rejected=request.data.get("qty_rejected", 0))
        if verb != "report":
            kwargs["at"] = _occurred_at(request)

        def build():
            return Response(JobCardSerializer(fn(card, **kwargs)).data)

        return _replayable(request, op, f"card.{verb}", build)


class TabletDowntimeView(_Tablet):
    def post(self, request, verb):
        op = request.operator
        at = _occurred_at(request)
        if verb == "start":
            wc = WorkCentre.objects.filter(pk=request.data.get("work_centre"), company=op.company).first()
            reason = DowntimeReason.objects.filter(pk=request.data.get("reason"), company=op.company, is_active=True).first()
            if wc is None or reason is None:
                raise rule("Choose the work centre and the reason.", "MFG_BAD_REFERENCE")

            def build():
                ev = shopfloor.start_downtime(
                    op.company, None, work_centre=wc, reason=reason, notes=f"{op.name}: {request.data.get('notes', '')}", at=at,
                )
                return Response(DowntimeEventSerializer(ev).data)
        elif verb == "end":
            ev = DowntimeEvent.objects.filter(pk=request.data.get("event"), company=op.company).first()
            if ev is None:
                raise Http404()

            def build():
                return Response(DowntimeEventSerializer(shopfloor.end_downtime(ev, at=at)).data)
        else:
            raise Http404()
        return _replayable(request, op, f"downtime.{verb}", build)
