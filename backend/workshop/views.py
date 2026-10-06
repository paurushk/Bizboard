from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.http import Http404
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import CanCreateSales, HasCompany
from core.services.feature_flags import flag_enabled
from core.viewsets import CompanyScopedViewSet
from inventory.models import BatchLot, SerialNumber
from masters.models import Product

from .models import JobCard, ServiceBay
from .serializers import JobCardLineSerializer, JobCardSerializer
from .services import add_line, cancel_job, convert_to_invoice, create_job, schedule_job, start_job


def _bay_for(company, raw):
    if raw in (None, ""):
        return None
    try:
        return ServiceBay.objects.filter(company=company, pk=raw).first()
    except (TypeError, ValueError):
        return None


def _when(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise BusinessRuleError("Start and end must be datetimes.")
    return parsed


class JobCardViewSet(CompanyScopedViewSet):
    queryset = JobCard.objects.prefetch_related("lines")
    serializer_class = JobCardSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "JobCard"
    http_method_names = ["get", "post", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(self.company, "ENABLE_WORKSHOP"):
            raise Http404()

    def create(self, request, *args, **kwargs):
        def _execute():
            customer_id = request.data.get("customer")
            from masters.models import Customer

            customer = Customer.objects.filter(company=self.company, pk=customer_id).first()
            tech = None
            if request.data.get("technician"):
                from accounts.models import CompanyUser

                tech = CompanyUser.objects.filter(company=self.company, pk=request.data["technician"]).first()
            bay = _bay_for(self.company, request.data.get("service_bay"))
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
                technician=tech,
                registration_no=request.data.get("registration_no") or "",
                vehicle_model=request.data.get("vehicle_model") or request.data.get("model") or "",
                odometer_reading=odometer,
                service_bay=bay,
                scheduled_start=_when(request.data.get("scheduled_start")),
                scheduled_end=_when(request.data.get("scheduled_end")),
            )
            return Response(self.get_serializer(job).data, status=201)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="workshop_job_create",
            build=_execute,
        )

    @action(detail=True, methods=["post"], url_path="lines")
    def lines(self, request, pk=None):
        job = self.get_object()
        product = Product.objects.filter(company=self.company, pk=request.data.get("product")).first()
        serial = None
        if request.data.get("serial"):
            serial = SerialNumber.objects.filter(company=self.company, pk=request.data["serial"]).first()
        batch = None
        if request.data.get("batch"):
            batch = BatchLot.objects.filter(company=self.company, pk=request.data["batch"]).first()
        line_check = JobCardLineSerializer(data={
            "kind": request.data.get("kind") or JobCardLineSerializer.Meta.model.Kind.PART,
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
        )
        job.refresh_from_db()
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        bay = _bay_for(self.company, request.data.get("service_bay"))
        job = schedule_job(
            self.get_object(),
            request.user,
            service_bay=bay,
            scheduled_start=_when(request.data.get("scheduled_start")),
            scheduled_end=_when(request.data.get("scheduled_end")),
        )
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return Response(self.get_serializer(start_job(self.get_object(), request.user)).data)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        def _execute():
            invoice = convert_to_invoice(self.get_object(), request.user)
            job = self.get_object()
            data = self.get_serializer(job).data
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
    def cancel(self, request, pk=None):
        return Response(self.get_serializer(cancel_job(self.get_object(), request.user)).data)
