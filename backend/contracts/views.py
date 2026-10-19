import csv
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.care import CareSalesAccess, assert_mutable
from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.attachments import create_attachment, delete_join_row
from core.services.audit import AuditService
from core.services.feature_flags import flag_enabled
from core.services.sequences import next_number
from core.viewsets import CompanyScopedViewSet
from support.models import Ticket

from .models import Contract, ContractDocument, ContractServiceEvent
from .ops import coverage_for, renew_contract, set_schedule_active, sync_schedule_line
from .serializers import ContractRenewalSerializer, ContractSerializer, ContractServiceEventSerializer
from .services import (
    create_contract_schedule,
    log_contract_created,
    log_service_event,
    pause_ended_contract_schedules,
    resume_renewed_contract_schedules,
)
from .status import effective_contract_status, filter_by_effective_status

_OWNER_ACTIONS = {"create_schedule", "sync_schedule", "pause_schedule", "resume_schedule"}
_EDIT_WINDOW = timedelta(hours=24)
_MONTHS = {"WEEKLY": Decimal("0.25"), "MONTHLY": Decimal("1"), "QUARTERLY": Decimal("3"),
           "HALF_YEARLY": Decimal("6"), "ANNUALLY": Decimal("12")}


class ContractViewSet(CompanyScopedViewSet):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated, HasCompany, CareSalesAccess]
    owner_only_actions = ("destroy",)
    audit_entity = "Contract"
    search_fields = (
        "number", "customer__name", "notes", "product__name", "covered_products__product__name",
    )

    def get_permissions(self):
        # super() appends SubscriptionWritesAllowed: an expired plan must not write contracts.
        permissions = super().get_permissions()
        if getattr(self, "action", None) in _OWNER_ACTIONS:
            permissions.append(IsOwner())
        return permissions

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(get_company_user(request).company, "ENABLE_CONTRACTS"):
            raise Http404()

    def get_queryset(self):
        qs = (
            super().get_queryset()
            .select_related("customer", "product", "recurring_schedule")
            .prefetch_related("covered_products__product")
        )
        params = self.request.query_params
        if (params.get("q") or params.get("search")):
            qs = qs.distinct()
        if params.get("customer"):
            qs = qs.filter(customer_id=params["customer"])
        if params.get("contract_type"):
            qs = qs.filter(contract_type=params["contract_type"])
        if params.get("product"):
            from django.db.models import Q

            qs = qs.filter(
                Q(product_id=params["product"]) | Q(covered_products__product_id=params["product"])
            ).distinct()
        wanted = params.get("status")
        today = timezone.localdate()
        if wanted:
            qs = filter_by_effective_status(qs, wanted, today)
        within = params.get("expiring_within_days")
        if within and str(within).isdigit():
            qs = qs.exclude(status=Contract.Status.CANCELLED).filter(
                end_date__gte=today, end_date__lte=today + timedelta(days=int(within)),
            )
        ordering = params.get("ordering")
        if ordering in {"end_date", "-end_date", "value", "-value", "number", "-number"}:
            qs = qs.order_by(ordering, "-id")
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
        self.check_expected_version(serializer.instance)
        was_ended = serializer.instance.status in (Contract.Status.EXPIRED, Contract.Status.CANCELLED)
        instance = serializer.save(updated_by=self.request.user, company=self.company)
        if instance.recurring_schedule_id:
            schedule_ids = [instance.recurring_schedule_id]
            # An ended or cancelled contract stops its schedule; renewing or un-cancelling restarts it.
            pause_ended_contract_schedules(company_id=self.company.pk, schedule_ids=schedule_ids)
            if was_ended and instance.status in (Contract.Status.ACTIVE, Contract.Status.EXPIRING):
                resume_renewed_contract_schedules(self.company.pk, schedule_ids)
        self._audit("UPDATE", instance)

    def perform_destroy(self, instance):
        from sales.models import RecurringInvoiceSchedule

        if instance.service_events.exists() or instance.renewals.exists():
            raise BusinessRuleError("This contract has history. Cancel it instead of deleting it.")
        schedule_id = instance.recurring_schedule_id
        if schedule_id and instance.recurring_schedule.runs.exists():
            raise BusinessRuleError("This contract has billing history. Cancel it instead of deleting it.")
        super().perform_destroy(instance)
        if schedule_id:
            # Nothing else would stop a recurring schedule whose contract is gone.
            if not Contract.objects.filter(recurring_schedule_id=schedule_id).exists():
                RecurringInvoiceSchedule.objects.filter(pk=schedule_id).update(
                    is_active=False,
                    paused_reason=RecurringInvoiceSchedule.PausedReason.CONTRACT_ENDED,
                    updated_at=timezone.now(),
                )

    # ---- billing schedule --------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="create-schedule")
    def create_schedule(self, request, pk=None):
        cadence = (request.data.get("cadence") or "").strip().upper() or None

        def _build():
            try:
                schedule = create_contract_schedule(self.get_object(), request.user, cadence=cadence)
            except BusinessRuleError as exc:
                return Response({"detail": str(exc)}, status=400)
            contract = self.get_object()
            invoice_id = getattr(schedule, "draft_invoice_id", None)
            if invoice_id is None:
                latest = schedule.runs.order_by("-id").first()
                invoice_id = latest.invoice_id if latest is not None else None
            AuditService.log(
                action="contract_schedule_created", company=self.company, user=request.user,
                entity_type="Contract", entity_id=contract.pk,
                metadata={"schedule": schedule.pk, "cadence": schedule.cadence},
            )
            return Response({
                "id": schedule.id,
                "contract": contract.id,
                "customer": schedule.customer_id,
                "invoice": invoice_id,
                "cadence": schedule.cadence,
                "value": str(contract.value) if contract.value is not None else None,
            })

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="contract_recurring_schedule",
            build=_build,
        )

    @action(detail=True, methods=["post"], url_path="sync-schedule")
    def sync_schedule(self, request, pk=None):
        sync_schedule_line(self.get_object(), request.user)
        return Response(ContractSerializer(self.get_object(), context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="pause-schedule")
    def pause_schedule(self, request, pk=None):
        set_schedule_active(self.get_object(), request.user, False)
        return Response(ContractSerializer(self.get_object(), context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="resume-schedule")
    def resume_schedule(self, request, pk=None):
        set_schedule_active(self.get_object(), request.user, True)
        return Response(ContractSerializer(self.get_object(), context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def renew(self, request, pk=None):
        end = parse_date(str(request.data.get("new_end_date") or ""))
        if end is None:
            raise BusinessRuleError("Give the new end date as YYYY-MM-DD.")
        row = renew_contract(
            self.get_object(), request.user, new_end_date=end,
            value=request.data.get("value"), note=str(request.data.get("note") or "").strip(),
        )
        return Response(ContractSerializer(self.get_queryset().get(pk=row.pk), context={"request": request}).data)

    # ---- service events ----------------------------------------------------------------------
    @action(detail=True, methods=["get", "post"], url_path="service-events")
    def service_events(self, request, pk=None):
        contract = self.get_object()
        if request.method == "GET":
            rows = contract.service_events.select_related("ticket", "created_by")
            return Response(ContractServiceEventSerializer(rows, many=True).data)
        notes = str(request.data.get("notes") or "").strip()
        if not notes:
            raise BusinessRuleError("Write what was done in the service note.")
        if contract.status == Contract.Status.CANCELLED:
            raise BusinessRuleError("A cancelled contract cannot take new service events.")
        ticket = None
        ticket_id = request.data.get("ticket")
        if ticket_id:
            ticket = Ticket.objects.filter(company=self.company, pk=ticket_id).first()
            if ticket is None:
                return Response({"detail": "Ticket was not found."}, status=400)
            if ticket.customer_id != contract.customer_id:
                return Response({"detail": "That ticket belongs to a different customer."}, status=400)
        occurred = None
        if request.data.get("occurred_at"):
            occurred = parse_datetime(str(request.data["occurred_at"]))
            if occurred is None:
                day = parse_date(str(request.data["occurred_at"]))
                if day is None:
                    raise BusinessRuleError("Give the visit date and time as an ISO date.")
                occurred = timezone.make_aware(datetime.combine(day, time.min))
            if timezone.is_naive(occurred):
                occurred = timezone.make_aware(occurred)
            if occurred > timezone.now() + timedelta(minutes=5):
                raise BusinessRuleError("A service event cannot be in the future.")
        row = log_service_event(contract, request.user, ticket=ticket, notes=notes, occurred_at=occurred)
        AuditService.log(
            action="contract_service_event", company=self.company, user=request.user,
            entity_type="Contract", entity_id=contract.pk, metadata={"event": row.pk},
        )
        return Response(ContractServiceEventSerializer(row).data, status=201)

    @action(detail=True, methods=["patch", "delete"], url_path="service-event")
    def service_event_detail(self, request, pk=None):
        """Edit or remove one visit; the visit id travels as ``event`` (body or query)."""
        event_id = request.data.get("event") or request.query_params.get("event")
        if not str(event_id or "").isdigit():
            raise BusinessRuleError("Say which service event.")
        contract = self.get_object()
        event = ContractServiceEvent.objects.filter(company=self.company, contract=contract, pk=event_id).first()
        if event is None:
            raise Http404()
        if event.created_by_id != request.user.id and get_company_user(request).role != "OWNER":
            raise BusinessRuleError("Only the person who logged this event, or an owner, can change it.")
        if timezone.now() - event.created_at > _EDIT_WINDOW:
            raise BusinessRuleError("A service event can be changed only within 24 hours of logging it.")
        if request.method == "DELETE":
            event.delete()
            AuditService.log(
                action="contract_service_event_removed", company=self.company, user=request.user,
                entity_type="Contract", entity_id=contract.pk, metadata={"event": int(event_id)},
            )
            return Response(status=204)
        notes = request.data.get("notes")
        if notes is not None:
            if not str(notes).strip():
                raise BusinessRuleError("The service note cannot be empty.")
            event.notes = str(notes).strip()
        event.updated_by = request.user
        event.save()
        return Response(ContractServiceEventSerializer(event).data)

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        contract = self.get_object()
        events = ContractServiceEventSerializer(
            contract.service_events.select_related("ticket", "created_by"), many=True,
        ).data
        return Response({
            "contract": ContractSerializer(contract, context={"request": request}).data,
            "events": events,
            "renewals": ContractRenewalSerializer(contract.renewals.all(), many=True).data,
        })

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        from core.care_timeline import timeline_rows

        return Response(timeline_rows(self.company, "Contract", self.get_object().pk))

    # ---- lookups and reports -----------------------------------------------------------------
    @action(detail=False, methods=["get"])
    def coverage(self, request):
        """Which active contracts cover this product for this customer on a date (XLK-02)."""
        customer = request.query_params.get("customer")
        if not str(customer or "").isdigit():
            raise BusinessRuleError("Give the customer.")
        product = request.query_params.get("product")
        on_date = parse_date(request.query_params.get("date") or "") or timezone.localdate()
        rows = coverage_for(self.company, int(customer), int(product) if str(product or "").isdigit() else None, on_date)
        return Response([
            {
                "id": row.id, "number": row.number, "contract_type": row.contract_type,
                "start_date": row.start_date, "end_date": row.end_date,
                "has_schedule": row.recurring_schedule_id is not None,
            }
            for row in rows.prefetch_related(None)
        ])

    def _report_rows(self, request):
        today = timezone.localdate()
        include_cancelled = str(request.query_params.get("include_cancelled") or "").lower() in {"1", "true", "yes"}
        buckets: dict[tuple[str, str], Decimal] = {}
        for row in self.get_queryset().select_related(None).prefetch_related(None).only(
            "status", "contract_type", "end_date", "renewal_reminder_days", "value",
        ):
            state = effective_contract_status(row.status, row.end_date, row.renewal_reminder_days, today)
            if state == "CANCELLED" and not include_cancelled:
                continue
            key = (state, row.contract_type)
            buckets[key] = buckets.get(key, Decimal("0")) + (row.value or Decimal("0"))
        return [
            {"status": bucket_status, "contract_type": contract_type, "value": str(value)}
            for (bucket_status, contract_type), value in sorted(buckets.items())
        ]

    @action(detail=False, methods=["get"])
    def report(self, request):
        return Response(self._report_rows(request))

    @action(detail=False, methods=["get"], url_path="report/export")
    def report_export(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="contracts-report.csv"'
        writer = csv.writer(response)
        writer.writerow(["Number", "Customer", "Type", "Status", "Start", "End", "Value"])
        today = timezone.localdate()
        include_cancelled = str(request.query_params.get("include_cancelled") or "").lower() in {"1", "true", "yes"}
        for row in self.get_queryset():
            state = effective_contract_status(row.status, row.end_date, row.renewal_reminder_days, today)
            if state == "CANCELLED" and not include_cancelled:
                continue
            writer.writerow([
                row.number, row.customer.name, row.contract_type, state, row.start_date, row.end_date,
                row.value if row.value is not None else "",
            ])
        return response

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Expiries by month (next 12) and the value billed per month by live schedules."""
        today = timezone.localdate()
        months: dict[str, int] = {}
        monthly = Decimal("0")
        for row in self.get_queryset().exclude(status=Contract.Status.CANCELLED):
            if row.end_date < today:
                continue
            if row.end_date <= today + timedelta(days=366):
                key = f"{row.end_date.year:04d}-{row.end_date.month:02d}"
                months[key] = months.get(key, 0) + 1
            schedule = row.recurring_schedule
            if schedule is not None and schedule.is_active and row.value:
                monthly += row.value / _MONTHS.get(schedule.cadence, Decimal("1"))
        return Response({
            "expiring_by_month": [{"month": key, "count": months[key]} for key in sorted(months)],
            "monthly_recurring_value": str(monthly.quantize(Decimal("0.01"))),
        })

    # ---- files -------------------------------------------------------------------------------
    @action(detail=True, methods=["get", "post", "delete"])
    def attachments(self, request, pk=None):
        contract = self.get_object()
        rows = contract.documents.all()
        if request.method == "GET":
            return Response([{"id": row.id, "file": row.file_id} for row in rows])
        assert_mutable(contract, "This contract")
        if request.method == "DELETE":
            delete_join_row(rows, request.query_params.get("attachment"))
            AuditService.log(
                action="contract_document_removed", company=self.company, user=request.user,
                entity_type="Contract", entity_id=contract.pk,
                metadata={"attachment": request.query_params.get("attachment")},
            )
            return Response(status=204)
        asset = create_attachment(self.company, request.user, request.FILES.get("file"))
        row = ContractDocument.objects.create(
            company=self.company, contract=contract, file=asset,
            created_by=request.user, updated_by=request.user,
        )
        AuditService.log(
            action="contract_document_added", company=self.company, user=request.user,
            entity_type="Contract", entity_id=contract.pk, metadata={"file": asset.id},
        )
        return Response({"id": row.id, "file": asset.id}, status=201)

    def handle_exception(self, exc):
        if isinstance(exc, BusinessRuleError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)
