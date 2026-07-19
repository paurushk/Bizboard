from rest_framework.decorators import action
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.viewsets import CompanyScopedViewSet

from .models import PurchaseInvoice, PurchaseReturn
from .serializers import PurchaseInvoiceSerializer, PurchaseReturnSerializer
from .services import PurchaseService


class PurchaseInvoiceViewSet(CompanyScopedViewSet):
    queryset = PurchaseInvoice.objects.select_related("supplier").prefetch_related("items__product")
    serializer_class = PurchaseInvoiceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("supplier"):
            qs = qs.filter(supplier_id=params["supplier"])
        if params.get("date_from"):
            qs = qs.filter(invoice_date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(invoice_date__lte=params["date_to"])
        return qs

    def perform_destroy(self, instance):
        if instance.status != PurchaseInvoice.Status.DRAFT:
            raise BusinessRuleError("Only draft purchases can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        invoice = PurchaseService.complete(self.get_object(), request.user)
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        invoice = PurchaseService.cancel(self.get_object(), request.user)
        return Response(self.get_serializer(invoice).data)


class PurchaseReturnViewSet(CompanyScopedViewSet):
    queryset = PurchaseReturn.objects.select_related("supplier").prefetch_related("items__product")
    serializer_class = PurchaseReturnSerializer

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
