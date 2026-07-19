from django.http import FileResponse
from rest_framework.decorators import action
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.models import Notification
from core.services.notifications import NotificationService
from core.viewsets import CompanyScopedViewSet

from .models import Quotation, SalesInvoice, SalesReturn
from .serializers import QuotationSerializer, SalesInvoiceSerializer, SalesReturnSerializer
from .services import SalesService
from .tasks import generate_invoice_pdf


class SalesInvoiceViewSet(CompanyScopedViewSet):
    queryset = SalesInvoice.objects.select_related("customer").prefetch_related("items__product")
    serializer_class = SalesInvoiceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("customer"):
            qs = qs.filter(customer_id=params["customer"])
        if params.get("invoice_type"):
            qs = qs.filter(invoice_type=params["invoice_type"])
        if params.get("date_from"):
            qs = qs.filter(invoice_date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(invoice_date__lte=params["date_to"])
        if params.get("q"):
            qs = qs.filter(number__icontains=params["q"])
        return qs

    def perform_destroy(self, instance):
        if instance.status != SalesInvoice.Status.DRAFT:
            raise BusinessRuleError("Only draft invoices can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        invoice, warnings = SalesService.complete(self.get_object(), request.user)
        data = self.get_serializer(invoice).data
        data["warnings"] = warnings
        return Response(data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        invoice = SalesService.cancel(self.get_object(), request.user)
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["get"], url_path="pdf-status")
    def pdf_status(self, request, pk=None):
        invoice = self.get_object()
        return Response({"pdf_status": invoice.pdf_status, "pdf_file": invoice.pdf_file_id})

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        if invoice.pdf_status != SalesInvoice.PdfStatus.READY or not invoice.pdf_file:
            # Generate-on-demand fallback if the async job failed (§14).
            if invoice.status in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
                generate_invoice_pdf(invoice.pk)
                invoice.refresh_from_db()
            if not invoice.pdf_file:
                raise BusinessRuleError("PDF is not ready for this invoice.")
        return FileResponse(
            invoice.pdf_file.file.open("rb"),
            as_attachment=True,
            filename=invoice.pdf_file.original_name,
        )

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """Share via Notification Service — email or whatsapp (E4.10)."""
        invoice = self.get_object()
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Only completed invoices can be shared.")
        channel = (request.data.get("channel") or "").upper()
        if channel not in (Notification.Channel.EMAIL, Notification.Channel.WHATSAPP):
            raise BusinessRuleError("channel must be 'email' or 'whatsapp'.")
        recipient = request.data.get("recipient") or (
            invoice.customer.email if channel == Notification.Channel.EMAIL else invoice.customer.phone
        )
        if not recipient:
            raise BusinessRuleError("No recipient available for this channel.")
        body = (
            f"Invoice {invoice.number} dated {invoice.invoice_date} from {invoice.company.name}. "
            f"Amount: INR {invoice.grand_total}."
        )
        notification = NotificationService.send(
            company=invoice.company, channel=channel, recipient=recipient,
            subject=f"Invoice {invoice.number}", body=body, user=request.user,
        )
        from core.serializers import NotificationSerializer

        return Response(NotificationSerializer(notification).data)


class QuotationViewSet(CompanyScopedViewSet):
    queryset = Quotation.objects.select_related("customer").prefetch_related("items__product")
    serializer_class = QuotationSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        invoice = SalesService.convert_quotation(self.get_object(), request.user)
        return Response(SalesInvoiceSerializer(invoice, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        quotation = SalesService.cancel_quotation(self.get_object(), request.user)
        return Response(self.get_serializer(quotation).data)


class SalesReturnViewSet(CompanyScopedViewSet):
    queryset = SalesReturn.objects.select_related("customer", "sales_invoice").prefetch_related("items__product")
    serializer_class = SalesReturnSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        if self.request.query_params.get("customer"):
            qs = qs.filter(customer_id=self.request.query_params["customer"])
        return qs

    def perform_destroy(self, instance):
        if instance.status != SalesReturn.Status.DRAFT:
            raise BusinessRuleError("Only draft returns can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        sales_return = SalesService.complete_return(self.get_object(), request.user)
        return Response(self.get_serializer(sales_return).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sales_return = SalesService.cancel_return(self.get_object(), request.user)
        return Response(self.get_serializer(sales_return).data)
