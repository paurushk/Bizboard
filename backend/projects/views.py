from decimal import Decimal, InvalidOperation

from django.http import Http404
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import CanCreateSales, HasCompany
from core.services.feature_flags import flag_enabled
from core.viewsets import CompanyScopedViewSet
from masters.models import Customer, Product

from .models import Project, ProjectMilestone
from .serializers import ProjectSerializer
from .services import add_milestone, close_project, create_project, invoice_milestone, mark_ready


class ProjectViewSet(CompanyScopedViewSet):
    queryset = Project.objects.prefetch_related("milestones")
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "Project"
    http_method_names = ["get", "post", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(self.company, "ENABLE_PROJECTS"):
            raise Http404()

    def create(self, request, *args, **kwargs):
        def _execute():
            customer = Customer.objects.filter(company=self.company, pk=request.data.get("customer")).first()
            project = create_project(self.company, request.user, customer=customer, name=request.data.get("name") or "")
            return Response(self.get_serializer(project).data, status=201)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="project_create",
            build=_execute,
        )

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
        product = Product.objects.filter(company=self.company, pk=request.data.get("service_product")).first()
        try:
            sequence = int(request.data.get("sequence") or 1)
        except (TypeError, ValueError):
            raise BusinessRuleError("Sequence must be a whole number.") from None
        try:
            amount = Decimal(str(request.data.get("amount")))
        except (InvalidOperation, TypeError, ValueError):
            raise BusinessRuleError("Amount must be a number.") from None
        add_milestone(
            project,
            request.user,
            name=request.data.get("name") or "",
            amount=amount,
            service_product=product,
            sequence=sequence,
        )
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="milestones/(?P<milestone_id>[0-9]+)/ready")
    def ready(self, request, pk=None, milestone_id=None):
        mark_ready(self._milestone(self.get_object(), milestone_id), request.user)
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="milestones/(?P<milestone_id>[0-9]+)/invoice")
    def invoice(self, request, pk=None, milestone_id=None):
        def _execute():
            invoice_milestone(self._milestone(self.get_object(), milestone_id), request.user)
            return Response(self.get_serializer(self.get_object()).data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope=f"project_milestone_invoice:{milestone_id}",
            build=_execute,
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return Response(self.get_serializer(close_project(self.get_object(), request.user)).data)
