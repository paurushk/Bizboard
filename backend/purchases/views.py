import io

from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import (
    CanCancelDocuments,
    CanCreatePurchases,
    CanViewPurchaseSurfaces,
    HasCompany,
    IsOwner,
)
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.viewsets import CompanyScopedViewSet
from payments.models import PaymentAllocation

from .models import PurchaseInvoice, PurchaseReturn
from .serializers import PurchaseInvoiceSerializer, PurchaseReturnSerializer
from .services import PurchaseService


class PurchaseInvoiceViewSet(CompanyScopedViewSet):
    queryset = PurchaseInvoice.objects.select_related("supplier").prefetch_related("items__product")
    serializer_class = PurchaseInvoiceSerializer

    def create(self, request, *args, **kwargs):
        """Durable Idempotency-Key with begin-of-request placeholder (same as sales)."""
        def _run():
            return super(PurchaseInvoiceViewSet, self).create(request, *args, **kwargs)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="purchase_invoice_create",
            build=_run,
        )

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if action in ("create", "complete", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), HasCompany(), CanCreatePurchases()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPurchaseSurfaces()]
        if action == "number_series":
            if self.request.method == "GET":
                return [IsAuthenticated(), HasCompany(), CanViewPurchaseSurfaces()]
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        allocated = (
            PaymentAllocation.objects.filter(purchase_invoice_id=OuterRef("pk"), reversed_at__isnull=True)
            .values("purchase_invoice_id")
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
        if params.get("supplier"):
            qs = qs.filter(supplier_id=params["supplier"])
        if params.get("date_from"):
            qs = qs.filter(invoice_date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(invoice_date__lte=params["date_to"])
        if params.get("q"):
            qs = qs.filter(number__icontains=params["q"])
        return qs

    def perform_destroy(self, instance):
        if instance.status != PurchaseInvoice.Status.DRAFT:
            raise BusinessRuleError("Only draft purchases can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        gstin = resolve_series_gstin(company)
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "PURCHASE_INVOICE", gstin=gstin))
        try:
            data = DocumentNumberService.configure(
                company,
                "PURCHASE_INVOICE",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
                gstin=gstin,
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        def _run():
            confirm_no_rcm = str(request.data.get("confirm_no_rcm") or "").lower() in (
                "true", "1", "yes",
            )
            confirm_duplicate_bill = str(
                request.data.get("confirm_duplicate_bill") or ""
            ).lower() in ("true", "1", "yes")
            invoice, warnings = PurchaseService.complete(
                self.get_object(),
                request.user,
                confirm_no_rcm=confirm_no_rcm,
                confirm_duplicate_bill=confirm_duplicate_bill,
            )
            data = self.get_serializer(invoice).data
            data["warnings"] = warnings
            return Response(data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="purchase_invoice_complete",
            build=_run,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        invoice = PurchaseService.cancel(self.get_object(), request.user)
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """Render GST Purchase Bill PDF (Rule 46 / Rule 54 CGST Rules)."""
        from .pdf import render_gst_purchase_bill

        invoice = self.get_object()
        copy = (request.query_params.get("copy") or "ORIGINAL").upper()
        content = render_gst_purchase_bill(invoice, copy=copy)
        filename = f"{invoice.number or invoice.pk}_purchase_bill.pdf"
        return FileResponse(
            io.BytesIO(content),
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )


class PurchaseReturnViewSet(CompanyScopedViewSet):
    queryset = PurchaseReturn.objects.select_related("supplier").prefetch_related("items__product")
    serializer_class = PurchaseReturnSerializer

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
            return Response(DocumentNumberService.peek(company, "PURCHASE_RETURN"))
        try:
            data = DocumentNumberService.configure(
                company,
                "PURCHASE_RETURN",
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
        if self.request.query_params.get("supplier"):
            qs = qs.filter(supplier_id=self.request.query_params["supplier"])
        return qs

    def perform_destroy(self, instance):
        if instance.status != PurchaseReturn.Status.DRAFT:
            raise BusinessRuleError("Only draft returns can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        purchase_return = PurchaseService.complete_return(self.get_object(), request.user)
        return Response(self.get_serializer(purchase_return).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        purchase_return = PurchaseService.cancel_return(self.get_object(), request.user)
        return Response(self.get_serializer(purchase_return).data)
