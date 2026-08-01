from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.models import Notification
from core.permissions import CanCancelDocuments, HasCompany
from core.services.billing import compute_document_totals
from core.services.document_numbers import DocumentNumberService
from core.services.notifications import NotificationService
from core.services.place_of_supply import party_intra_state
from core.viewsets import CompanyScopedViewSet
from masters.models import Customer, Product
from payments.models import PaymentAllocation

from .models import Quotation, SalesInvoice, SalesReturn
from .serializers import QuotationSerializer, SalesInvoiceSerializer, SalesReturnSerializer
from .services import SalesService, _tax_enabled
from .tasks import generate_invoice_pdf


class SalesInvoiceViewSet(CompanyScopedViewSet):
    queryset = SalesInvoice.objects.select_related("customer").prefetch_related("items__product")
    serializer_class = SalesInvoiceSerializer

    def get_permissions(self):
        if getattr(self, "action", None) == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        allocated = (
            PaymentAllocation.objects.filter(sales_invoice_id=OuterRef("pk"))
            .values("sales_invoice_id")
            .annotate(total=Sum("amount"))
            .values("total")[:1]
        )
        qs = qs.annotate(
            _allocated=Coalesce(
                Subquery(allocated, output_field=DecimalField(max_digits=14, decimal_places=2)),
                Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)),
            )
        )
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

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "SALES_INVOICE"))
        try:
            data = DocumentNumberService.configure(
                company,
                "SALES_INVOICE",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    @action(detail=False, methods=["post"], url_path="preview-totals")
    def preview_totals(self, request):
        """Authoritative totals preview without persisting (Phase 1)."""
        company = self.company
        customer_id = request.data.get("customer")
        if not customer_id:
            raise BusinessRuleError("customer is required")
        try:
            customer = Customer.objects.get(pk=customer_id, company=company)
        except Customer.DoesNotExist as exc:
            raise BusinessRuleError("Invalid customer.") from exc

        invoice_type = request.data.get("invoice_type") or SalesInvoice.InvoiceType.GST
        tax_enabled = _tax_enabled(invoice_type)
        intra = party_intra_state(company, customer.state or "", customer.gstin or "")

        class _Doc:
            additional_charges = request.data.get("additional_charges") or 0
            invoice_discount = request.data.get("invoice_discount") or 0
            invoice_discount_mode = request.data.get("invoice_discount_mode") or "AFTER_TAX"
            auto_round_off = request.data.get("auto_round_off", True)

        class _Item:
            pass

        items = []
        for raw in request.data.get("items") or []:
            product_id = raw.get("product")
            try:
                product = Product.objects.get(pk=product_id, company=company)
            except Product.DoesNotExist as exc:
                raise BusinessRuleError("Invalid product.") from exc
            item = _Item()
            item.quantity = raw.get("quantity") or 0
            item.unit_price = raw.get("unit_price", product.selling_price)
            item.discount_percent = raw.get("discount_percent") or 0
            item.gst_rate = raw.get("gst_rate", product.gst_rate)
            items.append(item)

        doc = _Doc()
        compute_document_totals(
            doc,
            items,
            tax_enabled=tax_enabled,
            intra_state=intra,
            additional_charges=doc.additional_charges,
            invoice_discount=doc.invoice_discount,
            auto_round_off=doc.auto_round_off,
            invoice_discount_mode=doc.invoice_discount_mode,
        )
        return Response({
            "subtotal": doc.subtotal,
            "discount_total": doc.discount_total,
            "taxable_total": doc.taxable_total,
            "cgst_total": doc.cgst_total,
            "sgst_total": doc.sgst_total,
            "igst_total": doc.igst_total,
            "round_off": doc.round_off,
            "grand_total": doc.grand_total,
            "invoice_discount_mode": doc.invoice_discount_mode,
            "intra_state": intra,
            "items": [
                {
                    "taxable_amount": i.taxable_amount,
                    "cgst": i.cgst,
                    "sgst": i.sgst,
                    "igst": i.igst,
                    "line_total": i.line_total,
                }
                for i in items
            ],
        })

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

    @action(detail=True, methods=["post"], url_path="regenerate-pdf")
    def regenerate_pdf(self, request, pk=None):
        invoice = self.get_object()
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("PDF can only be regenerated for completed invoices.")
        invoice.pdf_status = SalesInvoice.PdfStatus.QUEUED
        invoice.save(update_fields=["pdf_status"])
        generate_invoice_pdf.delay(invoice.pk)
        invoice.refresh_from_db()
        return Response({"pdf_status": invoice.pdf_status, "pdf_file": invoice.pdf_file_id})

    @action(detail=True, methods=["get"], url_path="pdf-status")
    def pdf_status(self, request, pk=None):
        invoice = self.get_object()
        return Response({"pdf_status": invoice.pdf_status, "pdf_file": invoice.pdf_file_id})

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        import io

        from .pdf import render_gst_tax_invoice

        invoice = self.get_object()
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("PDF is not ready for this invoice.")

        copy = (request.query_params.get("copy") or "ORIGINAL").upper()
        if copy not in ("ORIGINAL", "DUPLICATE"):
            copy = "ORIGINAL"

        # P0-404: never sync-hang generate_invoice_pdf on download. Clients
        # must poll pdf-status / retry; use regenerate-pdf for FAILED.
        if invoice.pdf_status != SalesInvoice.PdfStatus.READY or not invoice.pdf_file:
            if invoice.pdf_status in (
                SalesInvoice.PdfStatus.NONE,
                SalesInvoice.PdfStatus.FAILED,
            ):
                invoice.pdf_status = SalesInvoice.PdfStatus.QUEUED
                invoice.save(update_fields=["pdf_status"])
                generate_invoice_pdf.delay(invoice.pk)
            return Response(
                {
                    "detail": "PDF is generating, retry shortly",
                    "pdf_status": invoice.pdf_status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        # DUPLICATE is rendered in-memory so the stored file stays ORIGINAL.
        if copy == "DUPLICATE":
            content = render_gst_tax_invoice(invoice, copy="DUPLICATE")
            return FileResponse(
                io.BytesIO(content),
                as_attachment=True,
                filename=f"{invoice.number or invoice.pk}_duplicate.pdf",
                content_type="application/pdf",
            )

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
        pdf_path = f"/api/v1/sales/invoices/{invoice.pk}/pdf/"
        body = (
            f"Invoice {invoice.number} dated {invoice.invoice_date} from {invoice.company.name}. "
            f"Amount: INR {invoice.grand_total}. "
            f"Download PDF: {pdf_path}"
        )
        notification = NotificationService.send(
            company=invoice.company, channel=channel, recipient=recipient,
            subject=f"Invoice {invoice.number}", body=body, user=request.user,
        )
        from core.serializers import NotificationSerializer

        data = NotificationSerializer(notification).data
        data["pdf_url"] = pdf_path
        return Response(data)


class QuotationViewSet(CompanyScopedViewSet):
    queryset = Quotation.objects.select_related("customer").prefetch_related("items__product")
    serializer_class = QuotationSerializer

    def get_permissions(self):
        if getattr(self, "action", None) == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        return super().get_permissions()

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
