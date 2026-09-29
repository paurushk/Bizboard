from decimal import Decimal

from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import CanCreateSales, HasCompany, IsOwner, get_company_user
from core.services.attachments import create_attachment, delete_join_row
from core.services.feature_flags import flag_enabled
from core.services.sequences import next_number
from core.viewsets import CompanyScopedViewSet
from support.models import Ticket

from .models import Contract, ContractDocument
from .serializers import ContractSerializer, ContractServiceEventSerializer
from .services import create_contract_schedule, log_contract_created, log_service_event
from .status import effective_contract_status, filter_by_effective_status


class ContractViewSet(CompanyScopedViewSet):
    queryset = Contract.objects.prefetch_related("covered_products")
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "Contract"

    def get_permissions(self):
        if getattr(self, "action", None) == "create_schedule":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return [IsAuthenticated(), HasCompany(), CanCreateSales()]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(get_company_user(request).company, "ENABLE_CONTRACTS"):
            raise Http404()

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related("covered_products")
        if self.request.query_params.get("customer"):
            qs = qs.filter(customer_id=self.request.query_params["customer"])
        wanted = self.request.query_params.get("status")
        if wanted:
            qs = filter_by_effective_status(qs, wanted, timezone.localdate())
        return qs

    def perform_create(self, serializer):
        instance = serializer.save(
            company=self.company,
            number=next_number(self.company, "CONTRACT", prefix="CON"),
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        log_contract_created(instance)
        self._audit("CREATE", instance)

    def perform_update(self, serializer):
        # ContractSerializer.validate_status() already restricts what can land
        # here to CANCELLED, CANCELLED->ACTIVE (un-cancel), or a same-value
        # no-op; Contract.save() re-derives the real status from dates for
        # anything other than CANCELLED. Nothing extra to do here.
        instance = serializer.save(updated_by=self.request.user, company=self.company)
        self._audit("UPDATE", instance)

    @action(detail=True, methods=["post"], url_path="create-schedule")
    def create_schedule(self, request, pk=None):
        def _build():
            try:
                schedule = create_contract_schedule(self.get_object(), request.user)
            except BusinessRuleError as exc:
                return Response({"detail": str(exc)}, status=400)
            contract = self.get_object()
            return Response({
                "id": schedule.id,
                "contract": contract.id,
                "customer": schedule.customer_id,
                "value": str(contract.value) if contract.value is not None else None,
            })

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="contract_recurring_schedule",
            build=_build,
        )

    @action(detail=True, methods=["get", "post"], url_path="service-events")
    def service_events(self, request, pk=None):
        contract = self.get_object()
        if request.method == "GET":
            rows = contract.service_events.all()
            return Response(ContractServiceEventSerializer(rows, many=True).data)
        ticket = None
        ticket_id = request.data.get("ticket")
        if ticket_id:
            ticket = Ticket.objects.filter(company=self.company, pk=ticket_id).first()
            if ticket is None:
                return Response({"detail": "Ticket was not found."}, status=400)
        row = log_service_event(
            contract, request.user, ticket=ticket, notes=request.data.get("notes") or "",
        )
        return Response(ContractServiceEventSerializer(row).data, status=201)

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        contract = self.get_object()
        events = ContractServiceEventSerializer(contract.service_events.all(), many=True).data
        return Response({"contract": ContractSerializer(contract, context={"request": request}).data, "events": events})

    @action(detail=False, methods=["get"])
    def report(self, request):
        today = timezone.localdate()
        buckets: dict[tuple[str, str], Decimal] = {}
        for row in self.get_queryset().only(
            "status", "contract_type", "end_date", "renewal_reminder_days", "value",
        ):
            status = effective_contract_status(
                row.status, row.end_date, row.renewal_reminder_days, today,
            )
            key = (status, row.contract_type)
            buckets[key] = buckets.get(key, Decimal("0")) + (row.value or Decimal("0"))
        return Response([
            {"status": bucket_status, "contract_type": contract_type, "value": str(value)}
            for (bucket_status, contract_type), value in sorted(buckets.items())
        ])

    @action(detail=True, methods=["get", "post", "delete"])
    def attachments(self, request, pk=None):
        contract = self.get_object()
        rows = contract.documents.all()
        if request.method == "GET":
            return Response([{"id": row.id, "file": row.file_id} for row in rows])
        if request.method == "DELETE":
            delete_join_row(rows, request.query_params.get("attachment"))
            return Response(status=204)
        asset = create_attachment(self.company, request.user, request.FILES.get("file"))
        row = ContractDocument.objects.create(
            company=self.company, contract=contract, file=asset,
            created_by=request.user, updated_by=request.user,
        )
        return Response({"id": row.id, "file": asset.id}, status=201)

    def handle_exception(self, exc):
        if isinstance(exc, BusinessRuleError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)
