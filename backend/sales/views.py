from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.celery_utils import safe_delay
from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode
from core.idempotency import begin_record, release_record, store_record, wrap_idempotent
from core.models import Notification
from billing.permissions import SubscriptionWritesAllowed
from core.permissions import (
    CanCancelDocuments,
    CanCreateSales,
    CanViewSalesSurfaces,
    HasCompany,
    IsOwner,
)
from core.services.billing import compute_document_totals
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.services.notifications import NotificationService
from core.services.place_of_supply import party_intra_state
from core.viewsets import CompanyScopedViewSet
from masters.models import Customer, Product
from payments.models import PaymentAllocation

from .einvoice_eway_actions import InvoiceEinvoiceEwayActionsMixin
from .models import Quotation, RecurringInvoiceSchedule, SalesInvoice, SalesReturn
from .serializers import (
    QuotationSerializer,
    RecurringInvoiceScheduleSerializer,
    SalesInvoiceSerializer,
    SalesReturnSerializer,
)
from .services import SalesService, _tax_enabled
from .tasks import generate_invoice_pdf

_INVOICE_IDEMPOTENCY_TTL = 60 * 60 * 24  # 24h


class SalesInvoiceViewSet(InvoiceEinvoiceEwayActionsMixin, CompanyScopedViewSet):
    queryset = SalesInvoice.objects.select_related("customer").prefetch_related("items__product")
    serializer_class = SalesInvoiceSerializer

    def create(self, request, *args, **kwargs):
        """BB-000610 / BB-000730: durable Idempotency-Key with begin-of-request placeholder."""
        raw_key = (request.headers.get("Idempotency-Key") or "").strip()
        claimed = None
        if raw_key:
            claimed = begin_record(
                company=self.company, scope="sales_invoice_create", raw_key=raw_key
            )
            if isinstance(claimed, Response):
                return claimed

        created_ok = False
        try:
            response = super().create(request, *args, **kwargs)
            if raw_key and response.status_code == status.HTTP_201_CREATED:
                data = getattr(response, "data", None) or {}
                if isinstance(data, dict) and isinstance(data.get("success"), bool) and "data" in data:
                    data = data.get("data") or {}
                created_id = data.get("id") if isinstance(data, dict) else ""
                store_record(
                    company=self.company,
                    scope="sales_invoice_create",
                    raw_key=raw_key,
                    response=response,
                    resource_id=str(created_id or ""),
                )
                created_ok = True
            return response
        finally:
            # Release in-flight placeholder if create did not complete successfully.
            if raw_key and claimed is not None and not isinstance(claimed, Response) and not created_ok:
                release_record(
                    company=self.company, scope="sales_invoice_create", raw_key=raw_key
                )

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in (
            "create", "complete", "update", "partial_update", "destroy",
            "preview_totals", "share",
        ):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        if action in ("list", "retrieve", "pdf", "pdf_status", "regenerate_pdf", "thermal_pdf"):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        if action == "number_series":
            if self.request.method == "GET":
                return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action in (
            "mark_einvoice_generated",
            "mark_eway_generated",
            "submit_einvoice",
            "cancel_einvoice",
            "submit_eway",
            "cancel_eway",
            "prepare_einvoice",
            "prepare_eway",
        ):
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        allocated = (
            PaymentAllocation.objects.filter(sales_invoice_id=OuterRef("pk"), reversed_at__isnull=True)
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
        # UXW2B-004: SalesInvoice.complete() assigns the real number from the
        # GSTIN-keyed series (gstin=invoice.company_gstin.gstin), but this preview
        # was peeking the un-keyed default series — showing "INV-00001" while the
        # actual save used e.g. "INV-2627-F1Z5-00011". Preview with the company's
        # current primary GSTIN so it resolves the same series completion will use.
        gstin = resolve_series_gstin(company)
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "SALES_INVOICE", gstin=gstin))
        try:
            data = DocumentNumberService.configure(
                company,
                "SALES_INVOICE",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
                gstin=gstin,
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
        supply_type = (request.data.get("supply_type") or "").strip().upper()
        from accounts.models import CompanyGstin

        seller_state = company.state or ""
        seller_gstin = company.gstin or ""
        gstin_id = request.data.get("company_gstin")
        if gstin_id:
            stamp = CompanyGstin.objects.filter(pk=gstin_id, company=company, is_active=True).first()
            if stamp is None:
                raise BusinessRuleError("Invalid company GSTIN.")
            seller_state = stamp.state or seller_state
            seller_gstin = stamp.gstin or seller_gstin
        intra = party_intra_state(
            company,
            customer.state or "",
            customer.gstin or "",
            seller_state=seller_state,
            seller_gstin=seller_gstin,
        )

        class _Doc:
            additional_charges = request.data.get("additional_charges") or 0
            invoice_discount = request.data.get("invoice_discount") or 0
            invoice_discount_mode = request.data.get("invoice_discount_mode") or "AFTER_TAX"
            auto_round_off = request.data.get("auto_round_off", True)
            cess_total = 0
            price_mode = request.data.get("price_mode") or "EXCLUSIVE"
            charges_hsn = request.data.get("charges_hsn") or ""
            charges_gst_rate = request.data.get("charges_gst_rate") or 0
            is_reverse_charge = bool(request.data.get("is_reverse_charge"))
            supply_type = request.data.get("supply_type") or ""

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
            if supply_type in ("EXPWOP", "SEZWOP"):
                item.gst_rate = 0
            item.cess_rate = raw.get("cess_rate", getattr(product, "cess_rate", 0) or 0)
            if supply_type in ("EXPWOP", "SEZWOP"):
                item.cess_rate = 0
            item.cess_amount = raw.get("cess_amount", getattr(product, "cess_amount", 0) or 0)
            item.cess = 0
            item.unit_price_inclusive = raw.get("unit_price_inclusive")
            item.supply_nature = raw.get("supply_nature") or "TAXABLE"
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
        from core.services.billing import apply_rcm_memo_after_tax

        apply_rcm_memo_after_tax(doc, items)
        from decimal import Decimal

        tcs_rate = Decimal(str(request.data.get("tcs_rate") or 0))
        tcs_amount = Decimal("0")
        if tcs_rate > 0:
            consideration = (
                Decimal(str(doc.taxable_total or 0))
                + Decimal(str(doc.cgst_total or 0))
                + Decimal(str(doc.sgst_total or 0))
                + Decimal(str(doc.igst_total or 0))
                + Decimal(str(getattr(doc, "cess_total", 0) or 0))
            )
            tcs_amount = (consideration * tcs_rate / Decimal("100")).quantize(Decimal("0.01"))
        amount_due = Decimal(str(doc.grand_total or 0)) + tcs_amount
        return Response({
            "subtotal": doc.subtotal,
            "discount_total": doc.discount_total,
            "taxable_total": doc.taxable_total,
            "cgst_total": doc.cgst_total,
            "sgst_total": doc.sgst_total,
            "igst_total": doc.igst_total,
            "cess_total": getattr(doc, "cess_total", 0),
            "round_off": doc.round_off,
            "grand_total": doc.grand_total,
            "tcs_rate": tcs_rate,
            "tcs_amount": tcs_amount,
            "amount_due": amount_due,
            "invoice_discount_mode": doc.invoice_discount_mode,
            "intra_state": intra,
            "items": [
                {
                    "taxable_amount": i.taxable_amount,
                    "cgst": i.cgst,
                    "sgst": i.sgst,
                    "igst": i.igst,
                    "cess": getattr(i, "cess", 0),
                    "line_total": i.line_total,
                }
                for i in items
            ],
        })

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        def _run():
            confirm_rcm = str(request.data.get("confirm_sales_rcm") or "").lower() in (
                "1", "true", "yes",
            )
            invoice, warnings = SalesService.complete(
                self.get_object(), request.user, confirm_sales_rcm=confirm_rcm,
            )
            data = self.get_serializer(invoice).data
            data["warnings"] = warnings
            return Response(data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="sales_invoice_complete",
            build=_run,
        )

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
        safe_delay(generate_invoice_pdf, invoice.pk, company_id=invoice.company_id)
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
            raise BusinessRuleError(
                "PDF is not ready for this invoice.",
                code=HelpCode.PDF_OR_SHARE_UNAVAILABLE,
            )

        copy = (request.query_params.get("copy") or "ORIGINAL").upper()
        if copy not in ("ORIGINAL", "DUPLICATE"):
            copy = "ORIGINAL"

        # P0-404: never sync-hang generate_invoice_pdf on download. Clients
        # must poll pdf-status / retry; use regenerate-pdf for FAILED.
        # Orphan READY (flag set but file missing) must re-enqueue or clients
        # spin forever on 409.
        if invoice.pdf_status != SalesInvoice.PdfStatus.READY or not invoice.pdf_file:
            should_enqueue = (
                invoice.pdf_status in (
                    SalesInvoice.PdfStatus.NONE,
                    SalesInvoice.PdfStatus.FAILED,
                )
                or (
                    invoice.pdf_status == SalesInvoice.PdfStatus.READY
                    and not invoice.pdf_file
                )
            )
            if should_enqueue:
                invoice.pdf_status = SalesInvoice.PdfStatus.QUEUED
                invoice.save(update_fields=["pdf_status"])
                safe_delay(generate_invoice_pdf, invoice.pk, company_id=invoice.company_id)
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

    @action(detail=True, methods=["get"], url_path="thermal-pdf")
    def thermal_pdf(self, request, pk=None):
        import io

        from .pdf import render_thermal_receipt

        invoice = self.get_object()
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Thermal receipt is not available for this invoice.")

        width_param = request.query_params.get("width", "80")
        try:
            width_mm = int(width_param)
        except (TypeError, ValueError):
            width_mm = 80
        if width_mm not in (58, 80):
            width_mm = 80

        content = render_thermal_receipt(invoice, width_mm=width_mm)
        return FileResponse(
            io.BytesIO(content),
            as_attachment=True,
            filename=f"{invoice.number or invoice.pk}_thermal_{width_mm}mm.pdf",
            content_type="application/pdf",
        )

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """Share via Notification Service — email or whatsapp (E4.10)."""
        invoice = self.get_object()
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError(
                "Only completed invoices can be shared.",
                code=HelpCode.PDF_OR_SHARE_UNAVAILABLE,
            )
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
        # BB-000743: mode for WhatsApp honesty (cloud vs link / fallback).
        if channel == Notification.Channel.WHATSAPP:
            data["mode"] = getattr(notification, "delivery_mode", None) or (
                "cloud" if notification.status == Notification.Status.SENT else "link"
            )
        return Response(data)


class QuotationViewSet(CompanyScopedViewSet):
    queryset = Quotation.objects.select_related("customer").prefetch_related("items__product")
    serializer_class = QuotationSerializer

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "convert", "convert_to_order"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "QUOTATION"))
        try:
            data = DocumentNumberService.configure(
                company,
                "QUOTATION",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        confirm_expired = str(request.data.get("confirm_expired") or "").lower() in (
            "true", "1", "yes",
        )
        invoice = SalesService.convert_quotation(
            self.get_object(), request.user, confirm_expired=confirm_expired,
        )
        return Response(SalesInvoiceSerializer(invoice, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="convert-to-order")
    def convert_to_order(self, request, pk=None):
        from .notes_serializers import SalesOrderSerializer

        confirm_expired = str(request.data.get("confirm_expired") or "").lower() in (
            "true", "1", "yes",
        )
        order = SalesService.convert_quotation_to_order(
            self.get_object(), request.user, confirm_expired=confirm_expired,
        )
        return Response(SalesOrderSerializer(order, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        quotation = SalesService.cancel_quotation(self.get_object(), request.user)
        return Response(self.get_serializer(quotation).data)


class SalesReturnViewSet(CompanyScopedViewSet):
    queryset = SalesReturn.objects.select_related("customer", "sales_invoice").prefetch_related("items__product")
    serializer_class = SalesReturnSerializer

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        return super().get_permissions()

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "SALES_RETURN"))
        try:
            data = DocumentNumberService.configure(
                company,
                "SALES_RETURN",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

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


class RecurringInvoiceScheduleViewSet(CompanyScopedViewSet):
    queryset = RecurringInvoiceSchedule.objects.select_related("customer", "company_gstin")
    serializer_class = RecurringInvoiceScheduleSerializer
    audit_entity = "RecurringInvoiceSchedule"

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "run_now":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]

    @action(detail=True, methods=["post"], url_path="run-now")
    def run_now(self, request, pk=None):
        from django.utils import timezone

        from .recurring import generate_draft_for_schedule

        schedule = self.get_object()
        run = generate_draft_for_schedule(schedule, run_date=timezone.localdate(), user=request.user)
        if run is None:
            raise BusinessRuleError("Schedule did not generate an invoice (inactive, locked period, or duplicate).")
        return Response({
            "ok": True,
            "run_id": run.id,
            "invoice_id": run.invoice_id,
            "period_key": run.period_key,
            "status": run.invoice.status if run.invoice_id else None,
        })
