import io

from django.http import FileResponse
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from billing.permissions import SubscriptionWritesAllowed
from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import CanCancelDocuments, CanCreatePurchases, CanViewPurchaseSurfaces, HasCompany, IsOwner
from core.services.document_numbers import DocumentNumberService
from core.viewsets import CompanyScopedViewSet

from .models import GoodsReceipt, PurchaseCreditNote, PurchaseDebitNote, PurchaseOrder
from .notes_services import PurchaseNotesService
from .phase1_serializers import (
    GoodsReceiptSerializer,
    PurchaseCreditNoteSerializer,
    PurchaseDebitNoteSerializer,
    PurchaseOrderSerializer,
)
from .serializers import PurchaseInvoiceSerializer


class PurchaseCreditNoteViewSet(CompanyScopedViewSet):
    queryset = PurchaseCreditNote.objects.select_related("supplier").prefetch_related("items__product")
    serializer_class = PurchaseCreditNoteSerializer

    def get_permissions(self):
        # CR-037: include SubscriptionWritesAllowed on write actions
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreatePurchases()]
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
        def _run():
            # CR-031 / B2-010: PurchaseNotesService.complete_credit_note already
            # posts the note; do not call PostingService.post_note again.
            note, warnings = PurchaseNotesService.complete_credit_note(
                self.get_object(),
                request.user,
                confirm_paid_invoice=request.data.get("confirm_paid_invoice")
                in (True, "true", "True", 1, "1"),
                confirm_price_override=request.data.get("confirm_price_override")
                in (True, "true", "True", 1, "1"),
            )
            data = self.get_serializer(note).data
            data["warnings"] = warnings
            return Response(data)

        # CR-030: wrap complete in wrap_idempotent with purchase_credit_note_complete scope
        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="purchase_credit_note_complete",
            build=_run,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        note = PurchaseNotesService.cancel_credit_note(self.get_object(), request.user)
        return Response(self.get_serializer(note).data)


class PurchaseDebitNoteViewSet(CompanyScopedViewSet):
    queryset = PurchaseDebitNote.objects.select_related("supplier").prefetch_related("items__product")
    serializer_class = PurchaseDebitNoteSerializer

    def get_permissions(self):
        # CR-037: include SubscriptionWritesAllowed on write actions
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreatePurchases()]
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
        confirm = request.data.get("confirm_additional_debit") in (True, "true", "True", 1, "1")

        def _run():
            # CR-031 / B2-010: complete_debit_note already posts the note.
            note, warnings = PurchaseNotesService.complete_debit_note(
                self.get_object(),
                request.user,
                confirm_additional_debit=confirm,
            )
            data = self.get_serializer(note).data
            data["warnings"] = warnings
            return Response(data)

        # CR-030: wrap complete in wrap_idempotent with purchase_debit_note_complete scope
        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="purchase_debit_note_complete",
            build=_run,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        note = PurchaseNotesService.cancel_debit_note(self.get_object(), request.user)
        return Response(self.get_serializer(note).data)


class PurchaseOrderViewSet(CompanyScopedViewSet):
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related("items__product")
    serializer_class = PurchaseOrderSerializer

    def get_permissions(self):
        # CR-037: include SubscriptionWritesAllowed on write actions
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "convert"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreatePurchases()]
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
        # CR-134: PO convert creates a draft purchase invoice — wrap for replay.
        def _run():
            purchase = PurchaseNotesService.convert_purchase_order(self.get_object(), request.user)
            return Response(
                PurchaseInvoiceSerializer(purchase, context=self.get_serializer_context()).data
            )

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="purchase_order_convert",
            build=_run,
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


class GoodsReceiptViewSet(CompanyScopedViewSet):
    queryset = GoodsReceipt.objects.select_related("supplier", "warehouse", "purchase_order").prefetch_related("items__product")
    serializer_class = GoodsReceiptSerializer

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "complete", "convert"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreatePurchases()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPurchaseSurfaces()]
        return super().get_permissions()

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "GOODS_RECEIPT"))
        try:
            data = DocumentNumberService.configure(
                company,
                "GOODS_RECEIPT",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    def perform_destroy(self, instance):
        if instance.status != GoodsReceipt.Status.DRAFT:
            raise BusinessRuleError("Only draft Goods Receipt Notes can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        from .grn_service import GoodsReceiptService
        grn = GoodsReceiptService.complete(self.get_object(), request.user)
        return Response(self.get_serializer(grn).data)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        from .grn_service import GoodsReceiptService
        invoice = GoodsReceiptService.convert_to_bill(self.get_object(), request.user)
        return Response(PurchaseInvoiceSerializer(invoice, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        from .grn_service import GoodsReceiptService
        grn = GoodsReceiptService.cancel(self.get_object(), request.user)
        return Response(self.get_serializer(grn).data)

