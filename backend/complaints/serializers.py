from rest_framework import serializers

from accounts.models import CompanyUser
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer, Supplier
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice

from .models import Complaint, ComplaintAttachment, SupplierComplaint, SupplierComplaintAttachment


class ComplaintSerializer(serializers.ModelSerializer):
    customer = CompanyPrimaryKeyRelatedField(queryset=Customer.objects.all())
    source_invoice = CompanyPrimaryKeyRelatedField(
        queryset=SalesInvoice.objects.all(), allow_null=True, required=False
    )
    assigned_to = CompanyPrimaryKeyRelatedField(
        queryset=CompanyUser.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Complaint
        fields = [
            "id", "number", "customer", "source_invoice", "category", "description",
            "status", "inspection_notes", "sales_return", "sales_credit_note",
            "replacement_order", "assigned_to", "resolved_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "status", "sales_return", "sales_credit_note", "replacement_order",
            "resolved_at", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        invoice = attrs.get("source_invoice", getattr(self.instance, "source_invoice", None))
        customer = attrs.get("customer", getattr(self.instance, "customer", None))
        if invoice is not None and customer is not None and invoice.customer_id != customer.id:
            raise serializers.ValidationError(
                {"source_invoice": "Source invoice must belong to the complaint's customer."}
            )
        return attrs


class ComplaintAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintAttachment
        fields = ["id", "file", "created_at"]
        read_only_fields = fields


class SupplierComplaintSerializer(serializers.ModelSerializer):
    supplier = CompanyPrimaryKeyRelatedField(queryset=Supplier.objects.all())
    source_invoice = CompanyPrimaryKeyRelatedField(
        queryset=PurchaseInvoice.objects.all(), allow_null=True, required=False
    )
    assigned_to = CompanyPrimaryKeyRelatedField(
        queryset=CompanyUser.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = SupplierComplaint
        fields = [
            "id", "number", "supplier", "source_invoice", "category", "description",
            "status", "inspection_notes", "purchase_debit_note", "assigned_to",
            "resolved_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "status", "purchase_debit_note", "resolved_at", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        invoice = attrs.get("source_invoice", getattr(self.instance, "source_invoice", None))
        supplier = attrs.get("supplier", getattr(self.instance, "supplier", None))
        if invoice is not None and supplier is not None and invoice.supplier_id != supplier.id:
            raise serializers.ValidationError(
                {"source_invoice": "Source bill must belong to the complaint's supplier."}
            )
        return attrs


class SupplierComplaintAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierComplaintAttachment
        fields = ["id", "file", "created_at"]
        read_only_fields = fields
