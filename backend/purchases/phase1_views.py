import io

from django.http import FileResponse
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.permissions import CanCancelDocuments, CanCreatePurchases, CanViewPurchaseSurfaces, HasCompany, IsOwner
from core.services.document_numbers import DocumentNumberService
from core.viewsets import CompanyScopedViewSet

from .models import PurchaseCreditNote, PurchaseDebitNote, PurchaseOrder
from .notes_services import PurchaseNotesService
from .phase1_serializers import (
    PurchaseCreditNoteSerializer,
    PurchaseDebitNoteSerializer,
    PurchaseOrderSerializer,
)
from .serializers import PurchaseInvoiceSerializer


class PurchaseCreditNoteViewSet(CompanyScopedViewSet):
    queryset = PurchaseCreditNote.objects.select_related("supplier").prefetch_related("items__product")
    serializer_class = PurchaseCreditNoteSerializer

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated(), HasCompany(), CanCreatePurchases()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPurchaseSurfaces()]
        return super().get_permissions()

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "PURCHASE_CREDIT_NOTE"))
        try:
            data = DocumentNumberService.configure(
                company,
                "PURCHASE_CREDIT_NOTE",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    def perform_destroy(self, instance):
        if instance.status != PurchaseCreditNote.Status.DRAFT:
            raise BusinessRuleError("Only draft notes can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        note, warnings = PurchaseNotesService.complete_credit_note(self.get_object(), request.user)
        if note.company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_note(note, source_type="PURCHASE_CREDIT_NOTE", direction="PURCHASE_CREDIT", user=request.user)
        data = self.get_serializer(note).data
        data["warnings"] = warnings
        return Response(data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        note = PurchaseNotesService.cancel_credit_note(self.get_object(), request.user)
        return Response(self.get_serializer(note).data)


class PurchaseDebitNoteViewSet(CompanyScopedViewSet):
    queryset = PurchaseDebitNote.objects.select_related("supplier").prefetch_related("items__product")
    serializer_class = PurchaseDebitNoteSerializer

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated(), HasCompany(), CanCreatePurchases()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPurchaseSurfaces()]
        return super().get_permissions()

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "PURCHASE_DEBIT_NOTE"))
        try:
            data = DocumentNumberService.configure(
                company,
                "PURCHASE_DEBIT_NOTE",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    def perform_destroy(self, instance):
        if instance.status != PurchaseDebitNote.Status.DRAFT:
            raise BusinessRuleError("Only draft notes can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        note, warnings = PurchaseNotesService.complete_debit_note(self.get_object(), request.user)
        if note.company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_note(note, source_type="PURCHASE_DEBIT_NOTE", direction="PURCHASE_DEBIT", user=request.user)
        data = self.get_serializer(note).data
        data["warnings"] = warnings
        return Response(data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        note = PurchaseNotesService.cancel_debit_note(self.get_object(), request.user)
        return Response(self.get_serializer(note).data)


class PurchaseOrderViewSet(CompanyScopedViewSet):
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related("items__product")
    serializer_class = PurchaseOrderSerializer

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "convert"):
            return [IsAuthenticated(), HasCompany(), CanCreatePurchases()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPurchaseSurfaces()]
        return super().get_permissions()

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "PURCHASE_ORDER"))
        try:
            data = DocumentNumberService.configure(
                company,
                "PURCHASE_ORDER",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    def perform_destroy(self, instance):
        if instance.status != PurchaseOrder.Status.DRAFT:
            raise BusinessRuleError("Only draft orders can be deleted.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        purchase = PurchaseNotesService.convert_purchase_order(self.get_object(), request.user)
        return Response(
            PurchaseInvoiceSerializer(purchase, context=self.get_serializer_context()).data
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = PurchaseNotesService.cancel_purchase_order(self.get_object(), request.user)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """Render GST Purchase Order PDF."""
        from .pdf import render_gst_purchase_order

        order = self.get_object()
        content = render_gst_purchase_order(order)
        filename = f"{order.number or order.pk}_purchase_order.pdf"
        return FileResponse(
            io.BytesIO(content),
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )
