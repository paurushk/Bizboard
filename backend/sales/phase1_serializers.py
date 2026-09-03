from rest_framework import serializers

from .models import (
    DeliveryChallan,
    DeliveryChallanItem,
    SalesCreditNote,
    SalesCreditNoteItem,
    SalesDebitNote,
    SalesDebitNoteItem,
    SalesOrder,
    SalesOrderItem,
)
from .notes_services import SalesNotesService
from .serializers import LINE_READONLY, TOTAL_READONLY, CompanyScopedSerializerMixin, _BaseLineSerializer


class SalesCreditNoteItemSerializer(_BaseLineSerializer):
    source_item = serializers.IntegerField(source="source_item_id", required=False, allow_null=True)

    class Meta:
        model = SalesCreditNoteItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount", "source_item",
            "hsn_code", "unit_name", "uqc_code", "supply_nature",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY + ["hsn_code", "uqc_code"]
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class SalesCreditNoteSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = SalesCreditNoteItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_number = serializers.CharField(source="sales_invoice.number", read_only=True)

    class Meta:
        model = SalesCreditNote
        fields = [
            "id", "number", "status", "customer", "customer_name", "sales_invoice",
            "invoice_number", "note_date", "reason", "reason_detail",
            "invoice_discount", "invoice_discount_mode", "auto_round_off",
            "additional_charges", "charges_hsn", "charges_gst_rate", "tcs_amount",
            "filing_party_gstin", "filing_place_of_supply",
            "company_gstin", "notes",
            "items", "pdf_status", "completed_at", "cancelled_at",
            "irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_status", "einvoice_error",
            "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = [
            "number", "status", "pdf_status", "completed_at", "cancelled_at",
            "irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_status", "einvoice_error",
            "tcs_amount",
        ] + TOTAL_READONLY

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        return customer

    def validate_sales_invoice(self, invoice):
        self.check_company_ref(invoice, "sales_invoice")
        return invoice

    def validate(self, attrs):
        customer = attrs.get("customer") or getattr(self.instance, "customer", None)
        invoice = attrs.get("sales_invoice") or getattr(self.instance, "sales_invoice", None)
        if customer is not None and invoice is not None and customer.pk != invoice.customer_id:
            raise serializers.ValidationError(
                {"customer": "Customer must match the linked sales invoice."}
            )
        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        inv = validated_data.get("sales_invoice")
        if inv is not None:
            validated_data.setdefault(
                "filing_party_gstin", inv.filing_party_gstin or (inv.customer.gstin or "")
            )
            validated_data.setdefault(
                "filing_place_of_supply", inv.filing_place_of_supply or (inv.customer.state or "")
            )
            if not validated_data.get("company_gstin"):
                validated_data["company_gstin"] = inv.company_gstin
        note = SalesCreditNote.objects.create(**validated_data)
        SalesNotesService.set_credit_note_items(note, [dict(l) for l in items_data], self.context["request"].user)
        return note

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != SalesCreditNote.Status.DRAFT:
            raise BusinessRuleError("Completed credit note cannot be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            SalesNotesService.set_credit_note_items(
                instance, [dict(l) for l in items_data], self.context["request"].user
            )
        return instance


class SalesDebitNoteItemSerializer(_BaseLineSerializer):
    source_item = serializers.IntegerField(source="source_item_id", required=False, allow_null=True)

    class Meta:
        model = SalesDebitNoteItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount", "source_item",
            "hsn_code", "unit_name", "uqc_code", "supply_nature",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY + ["hsn_code", "uqc_code"]
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class SalesDebitNoteSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = SalesDebitNoteItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_number = serializers.CharField(source="sales_invoice.number", read_only=True)

    class Meta:
        model = SalesDebitNote
        fields = [
            "id", "number", "status", "customer", "customer_name", "sales_invoice",
            "invoice_number", "note_date", "reason", "reason_detail",
            "invoice_discount", "invoice_discount_mode", "auto_round_off",
            "additional_charges", "charges_hsn", "charges_gst_rate", "tcs_amount",
            "filing_party_gstin", "filing_place_of_supply",
            "company_gstin", "notes",
            "items", "pdf_status", "completed_at", "cancelled_at",
            "irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_status", "einvoice_error",
            "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = [
            "number", "status", "pdf_status", "completed_at", "cancelled_at",
            "irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_status", "einvoice_error",
            "tcs_amount",
        ] + TOTAL_READONLY

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        return customer

    def validate_sales_invoice(self, invoice):
        self.check_company_ref(invoice, "sales_invoice")
        return invoice

    def validate(self, attrs):
        customer = attrs.get("customer") or getattr(self.instance, "customer", None)
        invoice = attrs.get("sales_invoice") or getattr(self.instance, "sales_invoice", None)
        if customer is not None and invoice is not None and customer.pk != invoice.customer_id:
            raise serializers.ValidationError(
                {"customer": "Customer must match the linked sales invoice."}
            )
        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        inv = validated_data.get("sales_invoice")
        if inv is not None:
            validated_data.setdefault(
                "filing_party_gstin", inv.filing_party_gstin or (inv.customer.gstin or "")
            )
            validated_data.setdefault(
                "filing_place_of_supply", inv.filing_place_of_supply or (inv.customer.state or "")
            )
            if not validated_data.get("company_gstin"):
                validated_data["company_gstin"] = inv.company_gstin
        note = SalesDebitNote.objects.create(**validated_data)
        SalesNotesService.set_debit_note_items(note, [dict(l) for l in items_data], self.context["request"].user)
        return note

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != SalesDebitNote.Status.DRAFT:
            raise BusinessRuleError("Completed debit note cannot be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            SalesNotesService.set_debit_note_items(
                instance, [dict(l) for l in items_data], self.context["request"].user
            )
        return instance


class SalesOrderItemSerializer(_BaseLineSerializer):
    class Meta:
        model = SalesOrderItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class SalesOrderSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = SalesOrder
        fields = [
            "id", "number", "status", "customer", "customer_name", "warehouse", "invoice_type",
            "order_date", "expected_delivery", "payment_terms_days",
            "additional_charges", "charges_hsn", "charges_gst_rate",
            "invoice_discount", "invoice_discount_mode",
            "auto_round_off", "notes", "terms_text", "items",
            "supply_type", "company_gstin",
            "converted_invoice", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "converted_invoice"] + TOTAL_READONLY

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        return customer

    def validate_warehouse(self, warehouse):
        if warehouse is not None:
            self.check_company_ref(warehouse, "warehouse")
        return warehouse

    def validate_company_gstin(self, company_gstin):
        if company_gstin is not None:
            self.check_company_ref(company_gstin, "company_gstin")
        return company_gstin

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        order = SalesOrder.objects.create(**validated_data)
        SalesNotesService.set_order_items(order, [dict(l) for l in items_data], self.context["request"].user)
        return order

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != SalesOrder.Status.DRAFT:
            raise BusinessRuleError("Only draft orders can be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            SalesNotesService.set_order_items(
                instance, [dict(l) for l in items_data], self.context["request"].user
            )
        return instance


class DeliveryChallanItemSerializer(_BaseLineSerializer):
    class Meta:
        model = DeliveryChallanItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount",
            "batch", "batch_no", "serial_numbers",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY
        extra_kwargs = {
            "unit_price": {"required": False},
            "gst_rate": {"required": False},
            "batch": {"required": False, "allow_null": True},
            "batch_no": {"required": False, "allow_blank": True},
            "serial_numbers": {"required": False},
        }


class DeliveryChallanSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = DeliveryChallanItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = DeliveryChallan
        fields = [
            "id", "number", "status", "customer", "customer_name", "warehouse", "sales_order",
            "challan_date", "vehicle_number", "transporter_name", "transporter_id",
            "transport_distance_km", "sub_supply_type", "trans_mode", "notes",
            "items", "pdf_status", "completed_at", "cancelled_at",
            "stock_posted", "converted_invoice",
            "eway_status", "eway_bill_no", "eway_valid_upto", "eway_error",
            "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = [
            "number", "status", "pdf_status", "completed_at", "cancelled_at",
            "stock_posted", "converted_invoice",
            "eway_status", "eway_bill_no", "eway_valid_upto", "eway_error",
        ] + TOTAL_READONLY

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        return customer

    def validate_warehouse(self, warehouse):
        if warehouse is not None:
            self.check_company_ref(warehouse, "warehouse")
        return warehouse

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        challan = DeliveryChallan.objects.create(**validated_data)
        SalesNotesService.set_challan_items(
            challan, [dict(l) for l in items_data], self.context["request"].user
        )
        return challan

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != DeliveryChallan.Status.DRAFT:
            raise BusinessRuleError("Completed challan cannot be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            SalesNotesService.set_challan_items(
                instance, [dict(l) for l in items_data], self.context["request"].user
            )
        return instance
