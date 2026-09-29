from django.http import Http404
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.idempotency import wrap_idempotent
from core.permissions import CanCreateSales, HasCompany
from core.services.feature_flags import flag_enabled
from core.viewsets import CompanyScopedViewSet
from inventory.models import SerialNumber
from masters.models import Product

from .models import JobCard
from .serializers import JobCardSerializer
from .services import add_line, cancel_job, convert_to_invoice, create_job, start_job


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
            job = create_job(
                self.company,
                request.user,
                customer=customer,
                complaint=request.data.get("complaint") or "",
                technician=tech,
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
        add_line(
            job,
            request.user,
            kind=request.data.get("kind"),
            product=product,
            quantity=request.data.get("quantity"),
            unit_price=request.data.get("unit_price"),
            serial=serial,
        )
        job.refresh_from_db()
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
