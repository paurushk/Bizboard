from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from .models import CustomerReceipt, PaymentAllocation, SupplierPayment


class CustomerReceiptSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    allocated = serializers.SerializerMethodField()
    unallocated = serializers.SerializerMethodField()

    class Meta:
        model = CustomerReceipt
        fields = [
            "id", "number", "customer", "customer_name", "amount", "mode",
            "receipt_date", "reference", "notes", "allocated", "unallocated", "created_at",
        ]
        read_only_fields = ["number"]

    def get_allocated(self, obj) -> Decimal:
        return obj.allocations.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    def get_unallocated(self, obj) -> Decimal:
        return obj.amount - self.get_allocated(obj)


class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    allocated = serializers.SerializerMethodField()
    unallocated = serializers.SerializerMethodField()

    class Meta:
        model = SupplierPayment
        fields = [
            "id", "number", "supplier", "supplier_name", "amount", "mode",
            "payment_date", "reference", "notes", "allocated", "unallocated", "created_at",
        ]
        read_only_fields = ["number"]

    def get_allocated(self, obj) -> Decimal:
        return obj.allocations.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    def get_unallocated(self, obj) -> Decimal:
        return obj.amount - self.get_allocated(obj)


class PaymentAllocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAllocation
        fields = [
            "id", "receipt", "supplier_payment", "sales_invoice",
            "purchase_invoice", "amount", "created_at",
        ]

    def validate(self, attrs):
        receipt = attrs.get("receipt")
        payment = attrs.get("supplier_payment")
        if bool(receipt) == bool(payment):
            raise serializers.ValidationError(
                "Provide exactly one of 'receipt' or 'supplier_payment'."
            )
        if receipt and not attrs.get("sales_invoice"):
            raise serializers.ValidationError("Receipt allocations require 'sales_invoice'.")
        if payment and not attrs.get("purchase_invoice"):
            raise serializers.ValidationError("Supplier payment allocations require 'purchase_invoice'.")
        return attrs
