from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Q
from django.http import Http404
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import CompanyUser
from complaints.models import Complaint
from contracts.models import Contract
from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.care import CareSalesAccess
from core.permissions import HasCompany
from core.services.feature_flags import flag_enabled
from core.viewsets import CompanyScopedViewSet
from inventory.models import BatchLot, SerialNumber, Warehouse
from masters.models import Customer, Product
from support.models import Ticket

from .models import JobCard, JobCardLine, ServiceBay
from .serializers import (
    JobCardLineSerializer,
    JobCardListSerializer,
    JobCardSerializer,
    ServiceBaySerializer,
)
from .services import (
    add_line,
    cancel_job,
    convert_to_invoice,
    create_job,
    remove_line,
    reopen_job,
    schedule_job,
    start_job,
    update_job,
    update_line,
)


def _find(model, company, raw, label):
    """Look up a company row by id. A value that was sent but matches nothing is an error, not a blank."""
    if raw in (None, ""):
        return None
    try:
        row = model.objects.filter(company=company, pk=raw).first()
    except (TypeError, ValueError):
        row = None
    if row is None:
        raise BusinessRuleError(f"The {label} was not found.")
    return row


def _when(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise BusinessRuleError("Start and end must be datetimes.")
    return parsed


def _truthy(value):
    return str(value or "").lower() in {"1", "true", "yes"}


class ServiceBayViewSet(CompanyScopedViewSet):
    """Bays the workshop books jobs into (JOB-12)."""

    queryset = ServiceBay.objects.all()
    serializer_class = ServiceBaySerializer
    permission_classes = [IsAuthenticated, HasCompany, CareSalesAccess]
    audit_entity = "ServiceBay"
    search_fields = ("name",)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(self.company, "ENABLE_WORKSHOP"):
            raise Http404()

    def get_queryset(self):
        qs = super().get_queryset()
        # Only the pick-list hides switched-off bays; a bay can still be opened, edited or deleted.
        if self.action == "list" and not _truthy(self.request.query_params.get("include_inactive")):
            qs = qs.filter(is_active=True)
        return qs

    def perform_destroy(self, instance):
        if instance.jobs.exclude(status__in=(JobCard.Status.CANCELLED, JobCard.Status.INVOICED)).exists():
            raise BusinessRuleError("This bay has open jobs. Switch it off instead of deleting it.")
        super().perform_destroy(instance)

    def handle_exception(self, exc):
        if isinstance(exc, BusinessRuleError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)


class JobCardViewSet(CompanyScopedViewSet):
    queryset = JobCard.objects.all()
    serializer_class = JobCardSerializer
    permission_classes = [IsAuthenticated, HasCompany, CareSalesAccess]
    audit_entity = "JobCard"
    # DELETE exists only for ``line``; a job itself is cancelled, never deleted.
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    search_fields = ("number", "registration_no", "vehicle_model", "customer__name", "complaint")

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(self.company, "ENABLE_WORKSHOP"):
            raise Http404()

    def get_serializer_class(self):
        if self.action == "list":
            return JobCardListSerializer
        return JobCardSerializer

    def get_queryset(self):
        qs = (
            super().get_queryset()
            .select_related(
                "customer", "technician__user", "service_bay", "sales_invoice", "contract", "ticket",
                "source_complaint", "warehouse",
            )
            .prefetch_related("lines__product")
        )
        params = self.request.query_params
        for name in ("status", "customer", "technician", "service_bay", "ticket", "contract"):
            if params.get(name):
                key = name if name == "status" else f"{name}_id"
                qs = qs.filter(**{key: params[name]})
        if params.get("registration_no"):
            qs = qs.filter(registration_no__iexact=params["registration_no"])
        day_from = parse_date(params.get("scheduled_from") or "")
        day_to = parse_date(params.get("scheduled_to") or "")
        if day_from:
            qs = qs.filter(scheduled_end__date__gte=day_from)
        if day_to:
            qs = qs.filter(scheduled_start__date__lte=day_to)
        return qs

    def _detail(self, job):
        return JobCardSerializer(self.get_queryset().get(pk=job.pk), context=self.get_serializer_context()).data

    def create(self, request, *args, **kwargs):
        def _execute():
            customer = _find(Customer, self.company, request.data.get("customer"), "customer")
            if customer is None:
                raise BusinessRuleError("Pick a customer.")
            odometer = request.data.get("odometer_reading")
            if odometer in ("", None):
                odometer = None
            else:
                try:
                    odometer = Decimal(str(odometer))
                except (InvalidOperation, TypeError, ValueError):
                    raise BusinessRuleError("Odometer reading must be a number.") from None
            job = create_job(
                self.company,
                request.user,
                customer=customer,
                complaint=request.data.get("complaint") or "",
                technician=_find(CompanyUser, self.company, request.data.get("technician"), "technician"),
                registration_no=request.data.get("registration_no") or "",
                vehicle_model=request.data.get("vehicle_model") or request.data.get("model") or "",
                odometer_reading=odometer,
                service_bay=_find(ServiceBay, self.company, request.data.get("service_bay"), "service bay"),
                scheduled_start=_when(request.data.get("scheduled_start")),
                scheduled_end=_when(request.data.get("scheduled_end")),
                contract=_find(Contract, self.company, request.data.get("contract"), "contract"),
                ticket=_find(Ticket, self.company, request.data.get("ticket"), "ticket"),
                source_complaint=_find(
                    Complaint, self.company, request.data.get("source_complaint"), "complaint",
                ),
                warehouse=_find(Warehouse, self.company, request.data.get("warehouse"), "warehouse"),
                allow_overlap=_truthy(request.data.get("allow_overlap")),
            )
            return Response(self._detail(job), status=201)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="workshop_job_create",
            build=_execute,
        )

    def partial_update(self, request, *args, **kwargs):
        job = self.get_object()
        self.check_expected_version(job)
        data = request.data
        fields = {}
        if "customer" in data:
            fields["customer"] = _find(Customer, self.company, data.get("customer"), "customer")
        if "technician" in data:
            fields["technician"] = _find(CompanyUser, self.company, data.get("technician"), "technician")
        for name in ("complaint", "registration_no", "vehicle_model"):
            if name in data:
                fields[name] = data.get(name)
        if "odometer_reading" in data:
            raw = data.get("odometer_reading")
            try:
                fields["odometer_reading"] = None if raw in ("", None) else Decimal(str(raw))
            except (InvalidOperation, TypeError, ValueError):
                raise BusinessRuleError("Odometer reading must be a number.") from None
        if "contract" in data:
            fields["contract"] = _find(Contract, self.company, data.get("contract"), "contract")
        if "ticket" in data:
            fields["ticket"] = _find(Ticket, self.company, data.get("ticket"), "ticket")
        if "source_complaint" in data:
            fields["source_complaint"] = _find(Complaint, self.company, data.get("source_complaint"), "complaint")
        if "warehouse" in data:
            fields["warehouse"] = _find(Warehouse, self.company, data.get("warehouse"), "warehouse")
        fields["allow_overlap"] = _truthy(data.get("allow_overlap"))
        update_job(job, request.user, **fields)
        return Response(self._detail(job))

    # ---- lines -------------------------------------------------------------------------------
    @action(detail=True, methods=["post"], url_path="lines")
    def lines(self, request, pk=None):
        job = self.get_object()
        product = _find(Product, self.company, request.data.get("product"), "product")
        serial = _find(SerialNumber, self.company, request.data.get("serial"), "serial")
        batch = _find(BatchLot, self.company, request.data.get("batch"), "batch")
        line_check = JobCardLineSerializer(data={
            "kind": request.data.get("kind") or JobCardLine.Kind.PART,
            "product": getattr(product, "pk", None),
            "quantity": request.data.get("quantity"),
            "unit_price": request.data.get("unit_price"),
        })
        line_check.is_valid(raise_exception=True)
        add_line(
            job,
            request.user,
            kind=request.data.get("kind"),
            product=product,
            quantity=line_check.validated_data["quantity"],
            unit_price=line_check.validated_data["unit_price"],
            serial=serial,
            batch=batch,
            batch_no=request.data.get("batch_no") or "",
            labour_minutes=request.data.get("labour_minutes") or 0,
            technician_commission_percent=request.data.get("technician_commission_percent") or 0,
            covered_by_contract=_truthy(request.data.get("covered_by_contract")),
        )
        return Response(self._detail(job))

    @action(detail=True, methods=["patch", "delete"], url_path="line")
    def line_detail(self, request, pk=None):
        """Edit or remove one line; the line id travels as ``line`` (body or query)."""
        line_id = request.data.get("line") or request.query_params.get("line")
        if not str(line_id or "").isdigit():
            raise BusinessRuleError("Say which line.")
        job = self.get_object()
        line = JobCardLine.objects.filter(company=self.company, job=job, pk=line_id).first()
        if line is None:
            raise Http404()
        if request.method == "DELETE":
            remove_line(job, line, request.user)
            return Response(self._detail(job))
        data = request.data
        kwargs = {}
        for name in ("quantity", "unit_price", "labour_minutes", "technician_commission_percent"):
            if name in data:
                kwargs[name] = data.get(name)
        if "batch" in data:
            kwargs["batch"] = _find(BatchLot, self.company, data.get("batch"), "batch")
            kwargs["set_batch"] = True
        if "serial" in data:
            kwargs["serial"] = _find(SerialNumber, self.company, data.get("serial"), "serial")
            kwargs["set_serial"] = True
        update_line(job, line, request.user, **kwargs)
        return Response(self._detail(job))

    # ---- workflow ----------------------------------------------------------------------------
    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        bay = _find(ServiceBay, self.company, request.data.get("service_bay"), "service bay")
        schedule_job(
            self.get_object(),
            request.user,
            service_bay=bay,
            scheduled_start=_when(request.data.get("scheduled_start")),
            scheduled_end=_when(request.data.get("scheduled_end")),
            allow_overlap=_truthy(request.data.get("allow_overlap")),
        )
        return Response(self._detail(self.get_object()))

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        start_job(self.get_object(), request.user)
        return Response(self._detail(self.get_object()))

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        def _execute():
            invoice = convert_to_invoice(self.get_object(), request.user)
            data = dict(self._detail(self.get_object()))
            data["sales_invoice"] = invoice.id
            data["invoice_status"] = invoice.status
            return Response(data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="workshop_job_convert",
            build=_execute,
        )

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        reopen_job(self.get_object(), request.user)
        return Response(self._detail(self.get_object()))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        cancel_job(self.get_object(), request.user)
        return Response(self._detail(self.get_object()))

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        from core.care_timeline import timeline_rows

        return Response(timeline_rows(self.company, "JobCard", self.get_object().pk))

    @action(detail=False, methods=["get"], url_path="stock-options")
    def stock_options(self, request):
        """Serials and batches a part line can be filled from, for people without the inventory right."""
        from django.db.models import F, Sum

        from inventory.models import StockBalance

        product = Product.objects.filter(company=self.company, pk=request.query_params.get("product") or 0).first()
        if product is None:
            raise BusinessRuleError("Pick a part first.")
        serials = SerialNumber.objects.filter(
            company=self.company, product=product, status=SerialNumber.Status.AVAILABLE,
        ).order_by("serial_number")[:100]
        stocked = (
            StockBalance.objects.filter(company=self.company, product=product, batch__isnull=False, on_hand__gt=0)
            .values("batch")
            .annotate(available=Sum(F("on_hand") - F("reserved")))
        )
        available = {row["batch"]: row["available"] for row in stocked}
        batches = BatchLot.objects.filter(company=self.company, pk__in=list(available)).order_by("expiry_date", "id")
        return Response({
            "track_serial": product.track_serial,
            "track_batch": product.track_batch,
            "serials": [{"id": row.id, "serial_number": row.serial_number} for row in serials],
            "batches": [
                {
                    "id": row.id, "batch_no": row.batch_no, "expiry_date": row.expiry_date,
                    "available": str(Decimal(str(available[row.id])).quantize(Decimal("0.001"))),
                }
                for row in batches
            ],
        })

    @action(detail=False, methods=["get"])
    def report(self, request):
        """Counts by status and how much of the billed work was free of charge (warranty/AMC)."""
        base = self.get_queryset()
        lines = JobCardLine.objects.filter(company=self.company, job__in=base)
        return Response({
            "by_status": list(base.order_by().values("status").annotate(count=Count("id"))),
            "covered_lines": lines.filter(covered_by_contract=True).count(),
            "paid_lines": lines.filter(covered_by_contract=False).count(),
            "jobs_with_contract": base.filter(~Q(contract=None)).count(),
        })

    def handle_exception(self, exc):
        if isinstance(exc, BusinessRuleError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)
