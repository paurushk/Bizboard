from rest_framework import serializers

from core.permissions import get_company_user
from masters.models import Customer, Product

from .models import (
    Quotation,
    QuotationItem,
    SalesInvoice,
    SalesItem,
    SalesReturn,
    SalesReturnItem,
)
from .services import SalesService

LINE_READONLY = ["taxable_amount", "cgst", "sgst", "igst", "line_total"]
TOTAL_READONLY = [
    "subtotal", "discount_total", "taxable_total", "cgst_total", "sgst_total",
    "igst_total", "round_off", "grand_total",
]


class CompanyScopedSerializerMixin:
    @property
    def company(self):
        return get_company_user(self.context["request"]).company

    def check_company_ref(self, obj, field):
        if obj is not None and obj.company_id != self.company.id:
            raise serializers.ValidationError({field: "Invalid reference."})


class _BaseLineSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name", read_only=True)


class SalesItemSerializer(_BaseLineSerializer):
    class Meta:
        model = SalesItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate",
            "hsn_code", "mrp", "unit_name",
            "batch_no", "exp_date", "mfg_date",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY + ["hsn_code", "mrp", "unit_name"]
        extra_kwargs = {
            "unit_price": {"required": False},
            "gst_rate": {"required": False},
            "batch_no": {"required": False, "allow_blank": True},
            "exp_date": {"required": False, "allow_null": True},
            "mfg_date": {"required": False, "allow_null": True},
        }


class SalesInvoiceSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = SalesItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    received = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()

    class Meta:
        model = SalesInvoice
        fields = [
            "id", "number", "status", "invoice_type", "customer", "customer_name",
            "invoice_date", "due_date", "payment_terms_days",
            "additional_charges", "invoice_discount", "invoice_discount_mode", "auto_round_off",
            "notes", "terms_text",
            "include_bank_details", "include_payment_qr", "include_terms",
            "signature",
            "items", "pdf_status", "pdf_file",
            "received", "balance",
            "completed_at", "cancelled_at", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = [
            "number", "status", "pdf_status", "pdf_file", "received", "balance",
            "completed_at", "cancelled_at",
        ] + TOTAL_READONLY

    def get_balance(self, obj):
        from decimal import Decimal

        if obj.status == SalesInvoice.Status.DRAFT:
            return obj.grand_total
        allocated = getattr(obj, "_allocated", None)
        if allocated is not None and self.context.get("view") and getattr(
            self.context["view"], "action", None
        ) == "list":
            return max(Decimal(str(obj.grand_total or 0)) - Decimal(str(allocated or 0)), Decimal("0"))
        try:
            from ledgers.services import LedgerService

            return LedgerService.sales_invoice_outstanding(obj)
        except Exception:
            from django.db.models import Sum

            from payments.models import PaymentAllocation

            allocated = (
                PaymentAllocation.objects.filter(sales_invoice=obj).aggregate(t=Sum("amount"))["t"]
                or Decimal("0")
            )
            return max(obj.grand_total - allocated, Decimal("0"))

    def get_received(self, obj):
        from decimal import Decimal

        balance = Decimal(str(self.get_balance(obj) or 0))
        return max(Decimal(str(obj.grand_total or 0)) - balance, Decimal("0"))

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        if customer.status == Customer.Status.BLOCKED:
            raise serializers.ValidationError("Cannot create an invoice for a blocked customer.")
        return customer

    def validate_signature(self, signature):
        if signature is not None:
            self.check_company_ref(signature, "signature")
        return signature

    def create(self, validated_data):
        from django.db import transaction

        items_data = validated_data.pop("items")
        # BUG-208: numbers are assigned on Complete (SalesService.complete),
        # not on draft creation — a draft that's later deleted or abandoned
        # must not permanently burn a slot in the GST-sequential series.
        # ("number" is read-only, so it was never actually present here; this
        # used to unconditionally call next_number() on every single draft.)
        with transaction.atomic():
            invoice = SalesInvoice.objects.create(**validated_data)
            SalesService.set_items(invoice, [dict(l) for l in items_data], self.context["request"].user)
            return invoice

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status in (SalesInvoice.Status.CANCELLED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Cancelled/returned invoice cannot be edited.")
        if instance.status == SalesInvoice.Status.COMPLETED and "customer" in validated_data:
            if validated_data["customer"].pk != instance.customer_id:
                raise BusinessRuleError("Cannot change customer on a completed invoice.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            SalesService.set_items(instance, [dict(l) for l in items_data], self.context["request"].user)
        else:
            # Preserve line snapshots on header-only updates.
            SalesService.set_items(
                instance,
                [
                    {
                        "product": i.product, "description": i.description,
                        "quantity": i.quantity, "unit_price": i.unit_price,
                        "discount_percent": i.discount_percent, "gst_rate": i.gst_rate,
                        "hsn_code": i.hsn_code, "mrp": i.mrp, "unit_name": i.unit_name,
                        "batch_no": i.batch_no, "exp_date": i.exp_date, "mfg_date": i.mfg_date,
                    }
                    for i in instance.items.all()
                ],
                self.context["request"].user,
            )
        return instance


class QuotationItemSerializer(_BaseLineSerializer):
    class Meta:
        model = QuotationItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class QuotationSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = QuotationItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = Quotation
        fields = [
            "id", "number", "status", "invoice_type", "customer", "customer_name",
            "quotation_date", "valid_until", "notes", "items", "converted_invoice",
            "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "converted_invoice"] + TOTAL_READONLY

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        return customer

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        quotation = Quotation.objects.create(**validated_data)
        SalesService.set_quotation_items(quotation, [dict(l) for l in items_data], self.context["request"].user)
        return quotation

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != Quotation.Status.DRAFT:
            raise BusinessRuleError("Only draft quotations can be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            SalesService.set_quotation_items(instance, [dict(l) for l in items_data], self.context["request"].user)
        return instance


class SalesReturnItemSerializer(_BaseLineSerializer):
    class Meta:
        model = SalesReturnItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class SalesReturnSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = SalesReturnItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = SalesReturn
        fields = [
            "id", "number", "status", "customer", "customer_name", "sales_invoice",
            "return_date", "reason", "items", "completed_at", "cancelled_at",
            "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "completed_at", "cancelled_at"] + TOTAL_READONLY

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        return customer

    def validate_sales_invoice(self, invoice):
        self.check_company_ref(invoice, "sales_invoice")
        return invoice

    def validate(self, attrs):
        invoice = attrs.get("sales_invoice") or getattr(self.instance, "sales_invoice", None)
        customer = attrs.get("customer") or getattr(self.instance, "customer", None)
        if invoice and customer and invoice.customer_id != customer.id:
            raise serializers.ValidationError("Return customer must match the invoice customer.")
        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        sales_return = SalesReturn.objects.create(**validated_data)
        SalesService.set_return_items(sales_return, [dict(l) for l in items_data], self.context["request"].user)
        return sales_return

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != SalesReturn.Status.DRAFT:
            raise BusinessRuleError("Completed return cannot be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            SalesService.set_return_items(instance, [dict(l) for l in items_data], self.context["request"].user)
        return instance
