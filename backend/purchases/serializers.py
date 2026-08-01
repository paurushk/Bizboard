from rest_framework import serializers

from core.permissions import get_company_user
from masters.models import Product

from .models import PurchaseInvoice, PurchaseItem, PurchaseReturn, PurchaseReturnItem
from .services import PurchaseService

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


class PurchaseItemSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = PurchaseItem
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


class PurchaseInvoiceSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    paid = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseInvoice
        fields = [
            "id", "number", "status", "purchase_type", "supplier", "supplier_name",
            "invoice_date", "due_date", "payment_terms_days",
            "additional_charges", "invoice_discount", "invoice_discount_mode", "auto_round_off",
            "supplier_bill_number", "notes", "terms_text",
            "include_bank_details", "include_payment_qr", "include_terms",
            "signature", "attachment", "items",
            "paid", "balance",
            "completed_at", "cancelled_at", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = [
            "number", "status", "paid", "balance",
            "completed_at", "cancelled_at",
        ] + TOTAL_READONLY

    def get_balance(self, obj):
        from decimal import Decimal

        if obj.status == PurchaseInvoice.Status.DRAFT:
            return obj.grand_total
        allocated = getattr(obj, "_allocated", None)
        if allocated is not None and self.context.get("view") and getattr(
            self.context["view"], "action", None
        ) == "list":
            return max(Decimal(str(obj.grand_total or 0)) - Decimal(str(allocated or 0)), Decimal("0"))
        try:
            from ledgers.services import LedgerService

            return LedgerService.purchase_invoice_outstanding(obj)
        except Exception:
            from django.db.models import Sum

            from payments.models import PaymentAllocation

            allocated = (
                PaymentAllocation.objects.filter(purchase_invoice=obj).aggregate(t=Sum("amount"))["t"]
                or Decimal("0")
            )
            return max(obj.grand_total - allocated, Decimal("0"))

    def get_paid(self, obj):
        from decimal import Decimal

        balance = Decimal(str(self.get_balance(obj) or 0))
        return max(Decimal(str(obj.grand_total or 0)) - balance, Decimal("0"))

    def validate_supplier(self, supplier):
        self.check_company_ref(supplier, "supplier")
        return supplier

    def validate_additional_charges(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Additional charges cannot be negative.")
        return value

    def validate_signature(self, signature):
        if signature is not None:
            self.check_company_ref(signature, "signature")
        return signature

    def validate_attachment(self, attachment):
        if attachment is not None:
            self.check_company_ref(attachment, "attachment")
        return attachment

    def _prepare_items(self, items_data):
        prepared = []
        for line in items_data:
            line = dict(line)
            product = line["product"]
            if "unit_price" not in line:
                line["unit_price"] = product.purchase_price
            if "gst_rate" not in line:
                line["gst_rate"] = product.gst_rate
            prepared.append(line)
        return prepared

    def create(self, validated_data):
        from django.db import transaction

        items_data = validated_data.pop("items")
        # BUG-208: defer numbering to Complete, matching sales invoices.
        with transaction.atomic():
            invoice = PurchaseInvoice.objects.create(**validated_data)
            PurchaseService.set_items(
                invoice, self._prepare_items(items_data), self.context["request"].user
            )
            return invoice

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status == PurchaseInvoice.Status.CANCELLED:
            raise BusinessRuleError("Cancelled purchase cannot be edited.")
        if instance.status == PurchaseInvoice.Status.COMPLETED and "supplier" in validated_data:
            if validated_data["supplier"].pk != instance.supplier_id:
                raise BusinessRuleError("Cannot change supplier on a completed purchase.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            PurchaseService.set_items(instance, self._prepare_items(items_data), self.context["request"].user)
        else:
            PurchaseService.set_items(
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


class PurchaseReturnItemSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = PurchaseReturnItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class PurchaseReturnSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = PurchaseReturnItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = PurchaseReturn
        fields = [
            "id", "number", "status", "supplier", "supplier_name", "purchase_invoice",
            "return_date", "reason", "items", "completed_at", "cancelled_at",
            "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "completed_at", "cancelled_at"] + TOTAL_READONLY

    def validate_supplier(self, supplier):
        self.check_company_ref(supplier, "supplier")
        return supplier

    def validate_purchase_invoice(self, invoice):
        if invoice is not None:
            self.check_company_ref(invoice, "purchase_invoice")
        return invoice

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        purchase_return = PurchaseReturn.objects.create(**validated_data)
        PurchaseService.set_return_items(purchase_return, [dict(l) for l in items_data], self.context["request"].user)
        return purchase_return

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != PurchaseReturn.Status.DRAFT:
            raise BusinessRuleError("Completed return cannot be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            PurchaseService.set_return_items(instance, [dict(l) for l in items_data], self.context["request"].user)
        return instance
