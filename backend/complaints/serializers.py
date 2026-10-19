from rest_framework import serializers

from accounts.models import CompanyUser
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer, Supplier
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice
from support.models import Ticket

from .models import Complaint, ComplaintAttachment, SupplierComplaint, SupplierComplaintAttachment

# Once a remedy document is linked, the parties and source invoice are fixed (CMP-02).
_DOC_FIELDS = {
    Complaint: ("sales_return_id", "sales_credit_note_id", "replacement_order_id"),
    SupplierComplaint: ("purchase_debit_note_id",),
}
_OPEN_STATES = ("OPEN", "INSPECTING")


def _member_name(member):
    user = getattr(member, "user", None)
    if user is None:
        return ""
    return (getattr(user, "full_name", "") or getattr(user, "email", "") or "").strip()


def _locked_links(instance) -> bool:
    if instance is None:
        return False
    return any(getattr(instance, name, None) for name in _DOC_FIELDS[type(instance)])


class _ComplaintRules(serializers.ModelSerializer):
    """Edit rules shared by customer and supplier complaints."""

    party_field = "customer"

    def validate(self, attrs):
        instance = self.instance
        if instance is not None:
            if instance.status in ("RESOLVED", "REJECTED"):
                raise serializers.ValidationError("A closed complaint cannot be edited.")
            if _locked_links(instance):
                for name in (self.party_field, "source_invoice"):
                    if name in attrs:
                        current = getattr(instance, f"{name}_id")
                        new = attrs[name].id if attrs[name] is not None else None
                        if new != current:
                            raise serializers.ValidationError({
                                name: "Fixed once a document is linked.",
                            })
            if instance.status not in _OPEN_STATES:
                for name in ("description", "category"):
                    if name in attrs and attrs[name] != getattr(instance, name):
                        raise serializers.ValidationError({name: "Fixed once the complaint is approved."})
        description = attrs.get("description")
        if description is not None and not description.strip():
            raise serializers.ValidationError({"description": "Describe the problem."})
        return attrs


class ComplaintSerializer(_ComplaintRules):
    party_field = "customer"
    customer = CompanyPrimaryKeyRelatedField(queryset=Customer.objects.all())
    source_invoice = CompanyPrimaryKeyRelatedField(
        queryset=SalesInvoice.objects.all(), allow_null=True, required=False
    )
    assigned_to = CompanyPrimaryKeyRelatedField(
        queryset=CompanyUser.objects.all(), allow_null=True, required=False
    )
    ticket = CompanyPrimaryKeyRelatedField(queryset=Ticket.objects.all(), allow_null=True, required=False)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    source_invoice_number = serializers.SerializerMethodField()
    assignee_name = serializers.SerializerMethodField()
    ticket_number = serializers.SerializerMethodField()

    def get_source_invoice_number(self, obj):
        invoice = obj.source_invoice
        return (invoice.number or f"#{invoice.pk}") if invoice else ""

    def get_assignee_name(self, obj):
        return _member_name(obj.assigned_to)

    def get_ticket_number(self, obj):
        return obj.ticket.number if obj.ticket else ""

    class Meta:
        model = Complaint
        fields = [
            "id", "number", "customer", "customer_name", "source_invoice", "source_invoice_number",
            "category", "description", "status", "inspection_notes", "resolution_note", "sales_return",
            "sales_credit_note", "replacement_order", "assigned_to", "assignee_name", "ticket",
            "ticket_number", "resolved_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "status", "resolution_note", "sales_return", "sales_credit_note",
            "replacement_order", "resolved_at", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        invoice = attrs.get("source_invoice", getattr(self.instance, "source_invoice", None))
        customer = attrs.get("customer", getattr(self.instance, "customer", None))
        if invoice is not None and customer is not None and invoice.customer_id != customer.id:
            raise serializers.ValidationError(
                {"source_invoice": "Source invoice must belong to the complaint's customer."}
            )
        ticket = attrs.get("ticket")
        if ticket is not None and customer is not None and ticket.customer_id != customer.id:
            raise serializers.ValidationError({"ticket": "The ticket must belong to the complaint's customer."})
        return attrs


class ComplaintAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintAttachment
        fields = ["id", "file", "created_at"]
        read_only_fields = fields


class SupplierComplaintSerializer(_ComplaintRules):
    party_field = "supplier"
    supplier = CompanyPrimaryKeyRelatedField(queryset=Supplier.objects.all())
    source_invoice = CompanyPrimaryKeyRelatedField(
        queryset=PurchaseInvoice.objects.all(), allow_null=True, required=False
    )
    assigned_to = CompanyPrimaryKeyRelatedField(
        queryset=CompanyUser.objects.all(), allow_null=True, required=False
    )
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    source_invoice_number = serializers.SerializerMethodField()
    assignee_name = serializers.SerializerMethodField()

    def get_source_invoice_number(self, obj):
        invoice = obj.source_invoice
        return (invoice.number or f"#{invoice.pk}") if invoice else ""

    def get_assignee_name(self, obj):
        return _member_name(obj.assigned_to)

    class Meta:
        model = SupplierComplaint
        fields = [
            "id", "number", "supplier", "supplier_name", "source_invoice", "source_invoice_number",
            "category", "description", "status", "inspection_notes", "resolution_note",
            "purchase_debit_note", "assigned_to", "assignee_name", "resolved_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "status", "resolution_note", "purchase_debit_note", "resolved_at",
            "created_at", "updated_at",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
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
