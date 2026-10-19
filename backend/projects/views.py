from datetime import date
from decimal import Decimal, InvalidOperation

from django.http import Http404
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from contracts.models import Contract
from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.care import CareSalesAccess
from core.permissions import HasCompany
from core.services.feature_flags import flag_enabled
from core.viewsets import CompanyScopedViewSet
from masters.models import Customer, Product

from .models import Project, ProjectMilestone
from .serializers import ProjectListSerializer, ProjectSerializer
from .services import (
    add_milestone,
    cancel_project,
    close_project,
    create_project,
    delete_milestone,
    earlier_unbilled,
    invoice_milestone,
    mark_ready,
    reorder_milestones,
    unready_milestone,
    update_milestone,
    update_project,
)


def _whole_number(value, label):
    if value in (None, ""):
        raise BusinessRuleError(f"{label} is required.")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BusinessRuleError(f"{label} must be a whole number.") from None


def _money(value, label):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise BusinessRuleError(f"{label} must be a number.") from None


def _day(value, label="Date"):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    parsed = parse_date(str(value)[:10])
    if parsed is None:
        raise BusinessRuleError(f"{label} must be YYYY-MM-DD.")
    return parsed


class ProjectViewSet(CompanyScopedViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, HasCompany, CareSalesAccess]
    owner_only_actions = ("cancel",)
    audit_entity = "Project"
    http_method_names = ["get", "post", "patch", "head", "options"]
    search_fields = ("number", "name", "customer__name")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(self.company, "ENABLE_PROJECTS"):
            raise Http404()

    def get_serializer_class(self):
        return ProjectListSerializer if self.action == "list" else ProjectSerializer

    def get_queryset(self):
        qs = (
            super().get_queryset()
            .select_related("customer", "contract")
            .prefetch_related("milestones__service_product", "milestones__sales_invoice")
        )
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("customer"):
            qs = qs.filter(customer_id=params["customer"])
        if params.get("contract"):
            qs = qs.filter(contract_id=params["contract"])
        return qs

    def _detail(self, project):
        return ProjectSerializer(self.get_queryset().get(pk=project.pk), context=self.get_serializer_context()).data

    def create(self, request, *args, **kwargs):
        def _execute():
            customer_id = _whole_number(request.data.get("customer"), "Customer")
            customer = Customer.objects.filter(company=self.company, pk=customer_id).first()
            contract = None
            if request.data.get("contract"):
                contract = Contract.objects.filter(company=self.company, pk=request.data["contract"]).first()
                if contract is None:
                    raise BusinessRuleError("The contract was not found.")
            project = create_project(
                self.company, request.user, customer=customer, name=request.data.get("name") or "",
                notes=request.data.get("notes") or "",
                start_date=_day(request.data.get("start_date"), "Start date"),
                end_date=_day(request.data.get("end_date"), "End date"),
                contract_value=request.data.get("contract_value"), contract=contract,
            )
            return Response(self._detail(project), status=201)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="project_create",
            build=_execute,
        )

    def partial_update(self, request, *args, **kwargs):
        project = self.get_object()
        self.check_expected_version(project)
        data = request.data
        fields = {}
        for name in ("name", "notes", "contract_value"):
            if name in data:
                fields[name] = data.get(name)
        for name, label in (("start_date", "Start date"), ("end_date", "End date")):
            if name in data:
                fields[name] = _day(data.get(name), label)
        if "contract" in data:
            raw = data.get("contract")
            contract = None
            if raw not in (None, ""):
                contract = Contract.objects.filter(company=self.company, pk=raw).first()
                if contract is None:
                    raise BusinessRuleError("The contract was not found.")
            fields["contract"] = contract
        update_project(project, request.user, **fields)
        return Response(self._detail(project))

    def _milestone(self, project, milestone_id):
        milestone = ProjectMilestone.objects.filter(
            company=self.company, project=project, pk=milestone_id,
        ).first()
        if milestone is None:
            raise Http404("Milestone was not found on this project.")
        return milestone

    @action(detail=True, methods=["post"], url_path="milestones")
    def milestones(self, request, pk=None):
        project = self.get_object()
        product_id = _whole_number(request.data.get("service_product"), "Service product")
        product = Product.objects.filter(company=self.company, pk=product_id).first()
        sequence = _whole_number(request.data.get("sequence") or (project.milestones.count() + 1), "Sequence")
        amount = _money(request.data.get("amount"), "Amount")
        add_milestone(
            project,
            request.user,
            name=request.data.get("name") or "",
            amount=amount,
            service_product=product,
            sequence=sequence,
            target_completion_date=_day(request.data.get("target_completion_date"), "Target date"),
        )
        return Response(self._detail(project))

    @action(detail=True, methods=["post"], url_path="milestones/(?P<milestone_id>[0-9]+)/edit")
    def edit_milestone(self, request, pk=None, milestone_id=None):
        amount = request.data.get("amount")
        sequence = request.data.get("sequence")
        project = self.get_object()
        update_milestone(
            self._milestone(project, milestone_id),
            request.user,
            name=request.data.get("name"),
            amount=_money(amount, "Amount") if amount not in (None, "") else None,
            sequence=_whole_number(sequence, "Sequence") if sequence not in (None, "") else None,
            target_completion_date=_day(request.data.get("target_completion_date"), "Target date"),
            set_target="target_completion_date" in request.data,
        )
        return Response(self._detail(project))

    @action(detail=True, methods=["post"], url_path="milestones/(?P<milestone_id>[0-9]+)/delete")
    def remove_milestone(self, request, pk=None, milestone_id=None):
        project = self.get_object()
        delete_milestone(self._milestone(project, milestone_id), request.user)
        return Response(self._detail(project))

    @action(detail=True, methods=["post"], url_path="milestones/(?P<milestone_id>[0-9]+)/ready")
    def ready(self, request, pk=None, milestone_id=None):
        project = self.get_object()
        mark_ready(self._milestone(project, milestone_id), request.user)
        return Response(self._detail(project))

    @action(detail=True, methods=["post"], url_path="milestone-unready")
    def unready(self, request, pk=None):
        """Take a READY milestone back to PLANNED; the milestone id travels as ``milestone``."""
        project = self.get_object()
        milestone_id = _whole_number(request.data.get("milestone"), "Milestone")
        unready_milestone(self._milestone(project, milestone_id), request.user)
        return Response(self._detail(project))

    @action(detail=True, methods=["post"], url_path="milestones/reorder")
    def reorder(self, request, pk=None):
        project = self.get_object()
        reorder_milestones(project, request.user, request.data.get("order") or [])
        return Response(self._detail(project))

    @action(detail=True, methods=["post"], url_path="milestones/(?P<milestone_id>[0-9]+)/invoice")
    def invoice(self, request, pk=None, milestone_id=None):
        def _execute():
            project = self.get_object()
            milestone = self._milestone(project, milestone_id)
            warning = earlier_unbilled(milestone)
            invoice_milestone(milestone, request.user)
            data = dict(self._detail(project))
            if warning:
                data["warning"] = "Earlier milestones are not invoiced yet: " + ", ".join(warning[:5]) + "."
            return Response(data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope=f"project_milestone_invoice:{milestone_id}",
            build=_execute,
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        project = self.get_object()
        close_project(project, request.user)
        return Response(self._detail(project))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        project = self.get_object()
        cancel_project(project, request.user, reason=str(request.data.get("reason") or ""))
        return Response(self._detail(project))

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        from core.care_timeline import timeline_rows

        return Response(timeline_rows(self.company, "Project", self.get_object().pk))

    def handle_exception(self, exc):
        if isinstance(exc, BusinessRuleError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)
