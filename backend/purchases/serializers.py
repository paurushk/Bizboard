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
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class PurchaseInvoiceSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = PurchaseInvoice
        fields = [
            "id", "number", "status", "purchase_type", "supplier", "supplier_name",
            "invoice_date", "supplier_bill_number", "notes", "attachment", "items",
            "completed_at", "cancelled_at", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "completed_at", "cancelled_at"] + TOTAL_READONLY

    def validate_supplier(self, supplier):
        self.check_company_ref(supplier, "supplier")
        return supplier

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
        items_data = validated_data.pop("items")
        invoice = PurchaseInvoice.objects.create(**validated_data)
        PurchaseService.set_items(invoice, self._prepare_items(items_data), self.context["request"].user)
        return invoice

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != PurchaseInvoice.Status.DRAFT:
            raise BusinessRuleError("Completed purchase cannot be edited; use Return or Cancel.")
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
