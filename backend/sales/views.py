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
    CanViewFinancialReports,
    CanViewSalesSurfaces,
    HasCompany,
    IsOwner,
)
from core.services.billing import build_totals_preview
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.services.notifications import NotificationService
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
            "create", "complete", "update", "partial_update", "destroy", "share",
        ):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        if action in (
            "list", "retrieve", "pdf", "pdf_status", "regenerate_pdf", "thermal_pdf",
            # B2-018: a read-only quote/preview must not need write capability
            # or an active subscription.
            "preview_totals",
        ):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        if action == "audit":
            return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]
        if action == "number_series":
            if self.request.method == "GET":
                return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action in (
            "mark_einvoice_generated",
            "mark_eway_generated",
            "submit_einvoice",
            "submit_einvoice_async",
            "amend_filing_identity",
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
        # B2-020: validate before feeding query params to the ORM so bad input
        # is a 400, not a 500 (FieldError / ValidationError / ValueError).
        from datetime import date as _date

        from core.exceptions import BusinessRuleError

        params = self.request.query_params
        status = params.get("status")
        if status:
            if status not in SalesInvoice.Status.values:
                raise BusinessRuleError(f"Unknown status {status!r}.")
            qs = qs.filter(status=status)
        if params.get("customer"):
            try:
                qs = qs.filter(customer_id=int(params["customer"]))
            except (TypeError, ValueError):
                raise BusinessRuleError("customer must be a numeric id.")
        if params.get("invoice_type"):
            qs = qs.filter(invoice_type=params["invoice_type"])
        for key, lookup in (("date_from", "invoice_date__gte"), ("date_to", "invoice_date__lte")):
            raw = params.get(key)
            if raw:
                try:
                    qs = qs.filter(**{lookup: _date.fromisoformat(str(raw)[:10])})
                except ValueError:
                    raise BusinessRuleError(f"{key} must be an ISO date (YYYY-MM-DD).")
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
        """Authoritative totals preview without persisting (Phase 1 / A-03)."""
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

        product_ids = []
        for raw in request.data.get("items") or []:
            pid = raw.get("product")
            if pid:
                product_ids.append(pid)
        products_by_id = {
            p.pk: p for p in Product.objects.filter(pk__in=product_ids, company=company)
        }
        return Response(build_totals_preview(
            company=company,
            party_state=customer.state or "",
            party_gstin=customer.gstin or "",
            data=request.data,
            products_by_id=products_by_id,
            default_price_attr="selling_price",
            tax_enabled=tax_enabled,
            seller_state=seller_state,
            seller_gstin=seller_gstin,
        ))

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        def _run():
            confirm_rcm = str(request.data.get("confirm_sales_rcm") or "").lower() in (
                "1", "true", "yes",
            )
            confirm_blank_pos = str(request.data.get("confirm_blank_pos") or "").lower() in (
                "1", "true", "yes",
            )
            confirm_gstin_total = str(request.data.get("confirm_gstin_total_change") or "").lower() in (
                "1", "true", "yes",
            )
            invoice, warnings = SalesService.complete(
                self.get_object(),
                request.user,
                confirm_sales_rcm=confirm_rcm,
                confirm_blank_pos=confirm_blank_pos,
                confirm_gstin_total_change=confirm_gstin_total,
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

    @action(detail=True, methods=["get"], url_path="audit")
    def audit(self, request, pk=None):
        """D-03: company-scoped invoice audit timeline (Owner/CA)."""
        from core.models import AuditEvent
        from core.serializers import AuditEventSerializer

        invoice = self.get_object()
        pk_s = str(invoice.pk)
        events = (
            AuditEvent.objects.filter(company=invoice.company, entity_id=pk_s)
            .filter(entity_type__in=["SalesInvoice", "salesinvoice", "sales_invoice"])
            .select_related("user")
            .order_by("-created_at")[:200]
        )
        return Response(AuditEventSerializer(events, many=True).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reason = (
            request.data.get("reason")
            or request.data.get("cancel_reason")
            or request.data.get("cancelReason")
            or ""
        )
        invoice = SalesService.cancel(self.get_object(), request.user, reason=str(reason))
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

        from core.models import AuditEvent

        AuditEvent.objects.create(
            company=invoice.company,
            user=request.user,
            action=AuditEvent.Action.CREATE,
            entity_type="SalesInvoicePdf",
            entity_id=str(invoice.pk),
            description="Invoice PDF downloaded",
            metadata={"copy": copy},
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
        from sales.whatsapp_send import (
            allow_cloud_for_customer,
            compose_invoice_whatsapp_body,
            persist_invoice_whatsapp,
        )

        if channel == Notification.Channel.WHATSAPP:
            body = compose_invoice_whatsapp_body(invoice, request)
            subject = "invoice_ready"
            allow_cloud = allow_cloud_for_customer(invoice.customer)
        else:
            from django.conf import settings as dj_settings

            base = (getattr(dj_settings, "FRONTEND_URL", "") or "").rstrip("/")
            view_url = f"{base}/sales/history/{invoice.pk}" if base else f"/sales/history/{invoice.pk}"
            body = (
                f"Invoice {invoice.number} dated {invoice.invoice_date} from {invoice.company.name}. "
                f"Amount: INR {invoice.grand_total}. "
                f"View and download the invoice: {view_url}"
            )
            subject = f"Invoice {invoice.number}"
            allow_cloud = False
        notification = NotificationService.send(
            company=invoice.company,
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            user=request.user,
            allow_cloud=allow_cloud,
        )
        from core.serializers import NotificationSerializer

        data = NotificationSerializer(notification).data
        data["pdf_url"] = f"/api/v1/sales/invoices/{invoice.pk}/pdf/"
        # BB-000743: mode for WhatsApp honesty (cloud vs link / fallback).
        if channel == Notification.Channel.WHATSAPP:
            persist_invoice_whatsapp(invoice, notification)
            data["mode"] = getattr(notification, "delivery_mode", None) or (
                "cloud" if notification.status == Notification.Status.SENT else "link"
            )
            data["whatsapp_send_status"] = invoice.whatsapp_send_status
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
