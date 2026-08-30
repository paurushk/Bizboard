from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import (
    CanCancelDocuments,
    CanCreateSales,
    CanViewSalesSurfaces,
    HasCompany,
    IsOwner,
)
from core.services.document_numbers import DocumentNumberService
from core.viewsets import CompanyScopedViewSet
from ledgers.services import LedgerService

from .einvoice_eway_actions import ChallanEwayActionsMixin, NoteEinvoiceActionsMixin
from .models import DeliveryChallan, SalesCreditNote, SalesDebitNote, SalesOrder
from .notes_services import SalesNotesService
from .pdf_actions import PdfDocumentActionsMixin
from .phase1_serializers import (
    DeliveryChallanSerializer,
    SalesCreditNoteSerializer,
    SalesDebitNoteSerializer,
    SalesOrderSerializer,
)
from .serializers import SalesInvoiceSerializer
from .tasks import generate_challan_pdf, generate_credit_note_pdf, generate_debit_note_pdf


class SalesCreditNoteViewSet(NoteEinvoiceActionsMixin, PdfDocumentActionsMixin, CompanyScopedViewSet):
    queryset = SalesCreditNote.objects.select_related(
        "customer", "sales_invoice"
    ).prefetch_related("items__product")
    serializer_class = SalesCreditNoteSerializer
    pdf_task = generate_credit_note_pdf
    completed_statuses = (SalesCreditNote.Status.COMPLETED,)

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        if action in ("list", "retrieve", "pdf", "pdf_status", "regenerate_pdf", "adjustable_summary"):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        if self.request.query_params.get("customer"):
            qs = qs.filter(customer_id=self.request.query_params["customer"])
        return qs

    def perform_destroy(self, instance):
        if instance.status != SalesCreditNote.Status.DRAFT:
            raise BusinessRuleError("Only draft credit notes can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "SALES_CREDIT_NOTE"))
        try:
            data = DocumentNumberService.configure(
                company,
                "SALES_CREDIT_NOTE",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        def _run():
            note, warnings = SalesNotesService.complete_credit_note(self.get_object(), request.user)
            if note.company.accounting_enabled:
                from accounting.services import PostingService

                PostingService.post_note(note, source_type="SALES_CREDIT_NOTE", direction="SALES_CREDIT", user=request.user)
            data = self.get_serializer(note).data
            data["warnings"] = warnings
            return Response(data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="sales_credit_note_complete",
            build=_run,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        note = SalesNotesService.cancel_credit_note(self.get_object(), request.user)
        return Response(self.get_serializer(note).data)

    @action(detail=False, methods=["get"], url_path="adjustable-summary")
    def adjustable_summary(self, request):
        from core.permissions import get_company_user

        from .models import SalesInvoice

        invoice_id = request.query_params.get("invoice")
        if not invoice_id:
            raise BusinessRuleError("invoice query parameter is required.")
        company = get_company_user(request).company
        invoice = SalesInvoice.objects.get(pk=invoice_id, company=company)
        outstanding = LedgerService.sales_invoice_outstanding(invoice)
        from .notes_services import _sales_note_headroom

        return Response({
            "invoice_id": invoice.id,
            "invoice_number": invoice.number,
            "grand_total": invoice.grand_total,
            "outstanding": outstanding,
            "creditable_headroom": _sales_note_headroom(invoice),
        })


class SalesDebitNoteViewSet(NoteEinvoiceActionsMixin, PdfDocumentActionsMixin, CompanyScopedViewSet):
    queryset = SalesDebitNote.objects.select_related(
        "customer", "sales_invoice"
    ).prefetch_related("items__product")
    serializer_class = SalesDebitNoteSerializer
    pdf_task = generate_debit_note_pdf
    completed_statuses = (SalesDebitNote.Status.COMPLETED,)

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        if action in ("list", "retrieve", "pdf", "pdf_status", "regenerate_pdf"):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def perform_destroy(self, instance):
        if instance.status != SalesDebitNote.Status.DRAFT:
            raise BusinessRuleError("Only draft debit notes can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "SALES_DEBIT_NOTE"))
        try:
            data = DocumentNumberService.configure(
                company,
                "SALES_DEBIT_NOTE",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        confirm = request.data.get("confirm_additional_debit") in (True, "true", "True", 1, "1")

        def _run():
            note, warnings = SalesNotesService.complete_debit_note(
                self.get_object(), request.user, confirm_additional_debit=confirm
            )
            if note.company.accounting_enabled:
                from accounting.services import PostingService

                PostingService.post_note(
                    note, source_type="SALES_DEBIT_NOTE", direction="SALES_DEBIT", user=request.user
                )
            data = self.get_serializer(note).data
            data["warnings"] = warnings
            return Response(data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="sales_debit_note_complete",
            build=_run,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        note = SalesNotesService.cancel_debit_note(self.get_object(), request.user)
        return Response(self.get_serializer(note).data)


class SalesOrderViewSet(CompanyScopedViewSet):
    queryset = SalesOrder.objects.select_related("customer").prefetch_related("items__product")
    serializer_class = SalesOrderSerializer

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "confirm", "convert", "convert_to_challan"):
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def perform_destroy(self, instance):
        if instance.status != SalesOrder.Status.DRAFT:
            raise BusinessRuleError("Only draft orders can be deleted.")
        super().perform_destroy(instance)

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "SALES_ORDER"))
        try:
            data = DocumentNumberService.configure(
                company,
                "SALES_ORDER",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        order = SalesNotesService.confirm_sales_order(self.get_object(), request.user)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        invoice = SalesNotesService.convert_sales_order(self.get_object(), request.user)
        return Response(SalesInvoiceSerializer(invoice, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="convert-to-challan")
    def convert_to_challan(self, request, pk=None):
        challan = SalesNotesService.convert_sales_order_to_challan(self.get_object(), request.user)
        return Response(DeliveryChallanSerializer(challan, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = SalesNotesService.cancel_sales_order(self.get_object(), request.user)
        return Response(self.get_serializer(order).data)


class DeliveryChallanViewSet(ChallanEwayActionsMixin, PdfDocumentActionsMixin, CompanyScopedViewSet):
    queryset = DeliveryChallan.objects.select_related("customer").prefetch_related("items__product")
    serializer_class = DeliveryChallanSerializer
    pdf_task = generate_challan_pdf
    completed_statuses = (DeliveryChallan.Status.COMPLETED,)

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if action in ("mark_eway_generated", "submit_eway", "cancel_eway"):
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action in ("create", "update", "partial_update", "destroy", "complete", "convert"):
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        if action in ("list", "retrieve", "pdf", "pdf_status", "regenerate_pdf"):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def perform_destroy(self, instance):
        if instance.status != DeliveryChallan.Status.DRAFT:
            raise BusinessRuleError("Only draft challans can be deleted.")
        super().perform_destroy(instance)

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "DELIVERY_CHALLAN"))
        try:
            data = DocumentNumberService.configure(
                company,
                "DELIVERY_CHALLAN",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        challan = SalesNotesService.complete_challan(self.get_object(), request.user)
        return Response(self.get_serializer(challan).data)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        invoice = SalesNotesService.convert_delivery_challan(self.get_object(), request.user)
        return Response(SalesInvoiceSerializer(invoice, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        challan = SalesNotesService.cancel_challan(self.get_object(), request.user)
        return Response(self.get_serializer(challan).data)
