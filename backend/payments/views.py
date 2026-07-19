from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, get_company_user
from core.viewsets import CompanyScopedViewSet

from .models import CustomerReceipt, PaymentAllocation, SupplierPayment
from .serializers import (
    CustomerReceiptSerializer,
    PaymentAllocationSerializer,
    SupplierPaymentSerializer,
)
from .services import PaymentService


class CustomerReceiptViewSet(CompanyScopedViewSet):
    queryset = CustomerReceipt.objects.select_related("customer").prefetch_related("allocations")
    serializer_class = CustomerReceiptSerializer
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("customer"):
            qs = qs.filter(customer_id=self.request.query_params["customer"])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = PaymentService.create_receipt(
            company=self.company,
            customer=serializer.validated_data["customer"],
            amount=serializer.validated_data["amount"],
            mode=serializer.validated_data.get("mode", "CASH"),
            receipt_date=serializer.validated_data.get("receipt_date"),
            reference=serializer.validated_data.get("reference", ""),
            notes=serializer.validated_data.get("notes", ""),
            user=request.user,
        )
        self._audit("CREATE", receipt)
        return Response(self.get_serializer(receipt).data, status=status.HTTP_201_CREATED)


class SupplierPaymentViewSet(CompanyScopedViewSet):
    queryset = SupplierPayment.objects.select_related("supplier").prefetch_related("allocations")
    serializer_class = SupplierPaymentSerializer
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("supplier"):
            qs = qs.filter(supplier_id=self.request.query_params["supplier"])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = PaymentService.create_supplier_payment(
            company=self.company,
            supplier=serializer.validated_data["supplier"],
            amount=serializer.validated_data["amount"],
            mode=serializer.validated_data.get("mode", "CASH"),
            payment_date=serializer.validated_data.get("payment_date"),
            reference=serializer.validated_data.get("reference", ""),
            notes=serializer.validated_data.get("notes", ""),
            user=request.user,
        )
        self._audit("CREATE", payment)
        return Response(self.get_serializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentAllocationViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin, viewsets.GenericViewSet,
):
    queryset = PaymentAllocation.objects.all()
    serializer_class = PaymentAllocationSerializer
    permission_classes = [IsAuthenticated, HasCompany]

    @property
    def company(self):
        return get_company_user(self.request).company

    def get_queryset(self):
        qs = self.queryset.filter(company=self.company)
        if self.request.query_params.get("receipt"):
            qs = qs.filter(receipt_id=self.request.query_params["receipt"])
        if self.request.query_params.get("supplier_payment"):
            qs = qs.filter(supplier_payment_id=self.request.query_params["supplier_payment"])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        receipt = data.get("receipt")
        payment = data.get("supplier_payment")
        if receipt and receipt.company_id != self.company.id:
            raise BusinessRuleError("Invalid receipt reference.")
        if payment and payment.company_id != self.company.id:
            raise BusinessRuleError("Invalid payment reference.")

        if receipt:
            allocation = PaymentService.allocate_receipt(
                receipt=receipt, sales_invoice=data["sales_invoice"],
                amount=data["amount"], user=request.user,
            )
        else:
            allocation = PaymentService.allocate_supplier_payment(
                payment=payment, purchase_invoice=data["purchase_invoice"],
                amount=data["amount"], user=request.user,
            )
        return Response(self.get_serializer(allocation).data, status=status.HTTP_201_CREATED)
