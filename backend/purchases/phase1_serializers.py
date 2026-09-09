from rest_framework import serializers

from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Product

from .models import (
    PurchaseCreditNote,
    PurchaseCreditNoteItem,
    PurchaseDebitNote,
    PurchaseDebitNoteItem,
    PurchaseItem,
    PurchaseOrder,
    PurchaseOrderItem,
    GoodsReceipt,
    GoodsReceiptItem,
)
from .notes_services import PurchaseNotesService
from .serializers import CompanyScopedSerializerMixin

LINE_READONLY = ["taxable_amount", "cgst", "sgst", "igst", "cess", "line_total"]
TOTAL_READONLY = [
    "subtotal", "discount_total", "taxable_total", "cgst_total", "sgst_total",
    "igst_total", "cess_total", "round_off", "grand_total",
]


class _Line(serializers.ModelSerializer):
    # CR-135: nested note/PO product PKs must be company-scoped.
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name", read_only=True)


class PurchaseCreditNoteItemSerializer(_Line):
    source_item = CompanyPrimaryKeyRelatedField(
        queryset=PurchaseItem.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = PurchaseCreditNoteItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount", "source_item",
            "hsn_code", "unit_name", "uqc_code",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY + ["hsn_code", "uqc_code"]
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class PurchaseCreditNoteSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = PurchaseCreditNoteItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = PurchaseCreditNote
        fields = [
            "id", "number", "status", "supplier", "supplier_name", "purchase_invoice",
            "supplier_note_number", "note_date", "reason", "reason_detail",
            # CR-038: expose additional_charges and discount fields
            "additional_charges", "invoice_discount", "invoice_discount_mode", "auto_round_off", "notes",
            "items", "completed_at", "cancelled_at", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "completed_at", "cancelled_at"] + TOTAL_READONLY

    def validate_supplier(self, supplier):
        self.check_company_ref(supplier, "supplier")
        return supplier

    def validate_purchase_invoice(self, invoice):
        if invoice is not None:
            self.check_company_ref(invoice, "purchase_invoice")
        return invoice

    def validate(self, attrs):
        # CR-130: supplier must match linked bill (sales CN twin).
        supplier = attrs.get("supplier") or getattr(self.instance, "supplier", None)
        invoice = attrs.get("purchase_invoice") or getattr(self.instance, "purchase_invoice", None)
        if supplier is not None and invoice is not None and supplier.pk != invoice.supplier_id:
            raise serializers.ValidationError(
                {"supplier": "Supplier must match the linked purchase bill."}
            )
        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        note = PurchaseCreditNote.objects.create(**validated_data)
        PurchaseNotesService.set_credit_note_items(
            note, [dict(l) for l in items_data], self.context["request"].user
        )
        return note

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != PurchaseCreditNote.Status.DRAFT:
            raise BusinessRuleError("Completed credit note cannot be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            PurchaseNotesService.set_credit_note_items(
                instance, [dict(l) for l in items_data], self.context["request"].user
            )
        return instance


class PurchaseDebitNoteItemSerializer(_Line):
    source_item = CompanyPrimaryKeyRelatedField(
        queryset=PurchaseItem.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = PurchaseDebitNoteItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount", "source_item",
            "hsn_code", "unit_name", "uqc_code",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY + ["hsn_code", "uqc_code"]
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class PurchaseDebitNoteSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = PurchaseDebitNoteItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = PurchaseDebitNote
        fields = [
            "id", "number", "status", "supplier", "supplier_name", "purchase_invoice",
            "supplier_note_number", "note_date", "reason", "reason_detail",
            # CR-132: additional_charges parity with purchase CN / bill
            "additional_charges", "invoice_discount", "invoice_discount_mode", "auto_round_off", "notes",
            "items", "completed_at", "cancelled_at", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "completed_at", "cancelled_at"] + TOTAL_READONLY

    def validate_supplier(self, supplier):
        self.check_company_ref(supplier, "supplier")
        return supplier

    def validate_purchase_invoice(self, invoice):
        if invoice is not None:
            self.check_company_ref(invoice, "purchase_invoice")
        return invoice

    def validate(self, attrs):
        # CR-130: supplier must match linked bill (sales DN twin).
        supplier = attrs.get("supplier") or getattr(self.instance, "supplier", None)
        invoice = attrs.get("purchase_invoice") or getattr(self.instance, "purchase_invoice", None)
        if supplier is not None and invoice is not None and supplier.pk != invoice.supplier_id:
            raise serializers.ValidationError(
                {"supplier": "Supplier must match the linked purchase bill."}
            )
        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        note = PurchaseDebitNote.objects.create(**validated_data)
        PurchaseNotesService.set_debit_note_items(
            note, [dict(l) for l in items_data], self.context["request"].user
        )
        return note

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != PurchaseDebitNote.Status.DRAFT:
            raise BusinessRuleError("Completed debit note cannot be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            PurchaseNotesService.set_debit_note_items(
                instance, [dict(l) for l in items_data], self.context["request"].user
            )
        return instance


class PurchaseOrderItemSerializer(_Line):
    class Meta:
        model = PurchaseOrderItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class PurchaseOrderSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "number", "status", "supplier", "supplier_name", "purchase_type",
            "order_date", "expected_delivery", "payment_terms_days",
            "additional_charges", "invoice_discount", "invoice_discount_mode",
            "auto_round_off", "notes", "terms_text", "items",
            "converted_purchase", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "converted_purchase"] + TOTAL_READONLY

    def validate_supplier(self, supplier):
        self.check_company_ref(supplier, "supplier")
        return supplier

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        order = PurchaseOrder.objects.create(**validated_data)
        PurchaseNotesService.set_order_items(
            order, [dict(l) for l in items_data], self.context["request"].user
        )
        return order

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != PurchaseOrder.Status.DRAFT:
            raise BusinessRuleError("Only draft orders can be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            PurchaseNotesService.set_order_items(
                instance, [dict(l) for l in items_data], self.context["request"].user
            )
        return instance


class GoodsReceiptItemSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = GoodsReceiptItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "quantity_received",
            "quantity_accepted",
            "quantity_rejected",
            "unit_price",
            "rejection_reason",
        ]


class GoodsReceiptSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    items = GoodsReceiptItemSerializer(many=True, required=False)

    class Meta:
        model = GoodsReceipt
        fields = [
            "id",
            "number",
            "status",
            "supplier",
            "supplier_name",
            "purchase_order",
            "warehouse",
            "warehouse_name",
            "receipt_date",
            "supplier_challan_number",
            "completed_at",
            "cancelled_at",
            "notes",
            "converted_purchase",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "number",
            "status",
            "completed_at",
            "cancelled_at",
            "converted_purchase",
            "created_at",
            "updated_at",
        ]

    def validate_supplier(self, supplier):
        self.check_company_ref(supplier, "supplier")
        return supplier

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        company = validated_data["company"]
        grn = GoodsReceipt.objects.create(**validated_data)
        for item in items_data:
            GoodsReceiptItem.objects.create(
                company=company,
                goods_receipt=grn,
                **dict(item)
            )
        return grn

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != GoodsReceipt.Status.DRAFT:
            raise BusinessRuleError("Only draft Goods Receipt Notes can be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            instance.items.all().delete()
            for item in items_data:
                GoodsReceiptItem.objects.create(
                    company=instance.company,
                    goods_receipt=instance,
                    **dict(item)
                )
        return instance

