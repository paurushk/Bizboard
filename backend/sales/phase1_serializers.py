from rest_framework import serializers

from masters.models import Customer, CustomerShippingAddress

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
from .expected_profit import preserve_expected_prices, strip_expected_prices
from .notes_services import SalesNotesService
from .serializers import (
    LINE_READONLY,
    TOTAL_READONLY,
    CompanyScopedSerializerMixin,
    CostMaskedLineMixin,
    SourceQuotationsMixin,
    _BaseLineSerializer,
)


def assert_customer_active(serializer, customer, noun: str):
    """Block new documents for a blocked/inactive customer (parity with SalesInvoiceSerializer).

    Applies on create or when the customer changes; an existing draft that keeps its customer can
    still be edited or cancelled.
    """
    if customer.status == Customer.Status.ACTIVE:
        return
    instance = getattr(serializer, "instance", None)
    if instance is not None and instance.customer_id == customer.pk:
        return
    raise serializers.ValidationError(f"Cannot create {noun} for {customer.billing_block_phrase}.")



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
            "invoice_number", "note_date", "reason", "reason_detail", "sales_return",
            "peeled_receipt_allocations",
            "invoice_discount", "invoice_discount_mode", "auto_round_off",
            "additional_charges", "charges_hsn", "charges_gst_rate", "tcs_amount",
            "filing_party_gstin", "filing_place_of_supply",
            "company_gstin", "notes",
            "items", "pdf_status", "completed_at", "cancelled_at",
            "irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_status", "einvoice_error",
            "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = [
            "number", "status", "pdf_status", "completed_at", "cancelled_at", "sales_return",
            "peeled_receipt_allocations",
            "irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_status", "einvoice_error",
            "tcs_amount",
        ] + TOTAL_READONLY

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        return customer

    def validate_sales_invoice(self, invoice):
        self.check_company_ref(invoice, "sales_invoice")
        return invoice

    def validate_company_gstin(self, company_gstin):
        self.check_company_ref(company_gstin, "company_gstin")
        return company_gstin

    def validate(self, attrs):
        customer = attrs.get("customer") or getattr(self.instance, "customer", None)
        invoice = attrs.get("sales_invoice") or getattr(self.instance, "sales_invoice", None)
        if customer is not None and invoice is not None and customer.pk != invoice.customer_id:
            raise serializers.ValidationError(
                {"customer": "Customer must match the linked sales invoice."}
            )
        self._reject_referral_reward_duplicate(attrs)
        return attrs

    def _reject_referral_reward_duplicate(self, attrs):
        """A referral reward is paid from the Referrals screen; a hand-made note would pay it twice."""
        import re

        match = re.fullmatch(r"\s*Referral reward (\d+)\s*", attrs.get("reason_detail") or "")
        if self.instance is not None or not match:
            return
        from core.permissions import get_company_user
        from crm.models import ReferralReward

        membership = get_company_user(self.context["request"])
        if membership and ReferralReward.objects.filter(company=membership.company, pk=int(match.group(1))).exists():
            raise serializers.ValidationError({
                "reason_detail": "That reward is paid from the Referrals page, which creates its own credit note. "
                "Use a different reason text for a separate credit note.",
            })

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

    def validate_company_gstin(self, company_gstin):
        self.check_company_ref(company_gstin, "company_gstin")
        return company_gstin

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


class SalesOrderItemSerializer(CostMaskedLineMixin, _BaseLineSerializer):
    class Meta:
        model = SalesOrderItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount",
            "expected_price",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class SalesOrderSerializer(SourceQuotationsMixin, CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = SalesOrderItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    expected_profit = serializers.SerializerMethodField()
    fulfilment_state = serializers.SerializerMethodField()

    def get_fulfilment_state(self, obj):
        from .order_quantities import fulfilment_state

        return fulfilment_state(obj)

    def get_expected_profit(self, obj):
        from .expected_profit import can_view_expected_profit, expected_profit_for_order

        if not can_view_expected_profit(self.context.get("request")):
            return None
        return expected_profit_for_order(obj)

    class Meta:
        model = SalesOrder
        fields = [
            "id", "number", "status", "customer", "customer_name", "warehouse", "invoice_type", "price_mode",
            "order_date", "expected_delivery", "payment_terms_days",
            "additional_charges", "charges_hsn", "charges_gst_rate",
            "invoice_discount", "invoice_discount_mode",
            "auto_round_off", "notes", "terms_text", "items",
            "supply_type", "company_gstin",
            "salesman", "sales_channel", "delivery_address", "ship_to",
            "expected_profit", "source_quotations", "source_quotations_differ",
            "converted_invoice", "fulfilment_state", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "converted_invoice", "expected_profit", "fulfilment_state"] + TOTAL_READONLY

    ship_to = serializers.PrimaryKeyRelatedField(
        queryset=CustomerShippingAddress.objects.all(), write_only=True, required=False, allow_null=True
    )

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        assert_customer_active(self, customer, "an order")
        return customer

    def validate_ship_to(self, ship_to):
        if ship_to is not None:
            self.check_company_ref(ship_to, "ship_to")
        return ship_to

    def validate(self, attrs):
        attrs = super().validate(attrs)
        ship_to = attrs.get("ship_to")
        customer = attrs.get("customer") or getattr(self.instance, "customer", None)
        if ship_to is not None and customer is not None and ship_to.customer_id != customer.pk:
            raise serializers.ValidationError({"ship_to": "This address does not belong to the selected customer."})
        return attrs

    @staticmethod
    def _default_delivery_address(customer, ship_to) -> str:
        if ship_to is not None and (ship_to.address or "").strip():
            return ship_to.address
        default = customer.shipping_addresses.filter(is_default=True).first()
        if default is not None and (default.address or "").strip():
            return default.address
        return (customer.shipping_address or customer.billing_address or "").strip()

    def validate_warehouse(self, warehouse):
        if warehouse is not None:
            self.check_company_ref(warehouse, "warehouse")
        return warehouse

    def validate_company_gstin(self, company_gstin):
        if company_gstin is not None:
            self.check_company_ref(company_gstin, "company_gstin")
        return company_gstin

    def create(self, validated_data):
        request = self.context["request"]
        items_data = strip_expected_prices(request, validated_data.pop("items"))
        ship_to = validated_data.pop("ship_to", None)
        customer = validated_data["customer"]
        if not (validated_data.get("delivery_address") or "").strip():
            validated_data["delivery_address"] = self._default_delivery_address(customer, ship_to)
        # Only fall back to the customer's terms when the caller did not send any.
        if "payment_terms_days" not in self.initial_data:
            validated_data["payment_terms_days"] = customer.credit_days or 0
        if validated_data.get("company_gstin") is None:
            from .notes_services import _single_active_company_gstin

            validated_data["company_gstin"] = _single_active_company_gstin(validated_data["company"])
        order = SalesOrder.objects.create(**validated_data)
        SalesNotesService.set_order_items(order, [dict(l) for l in items_data], request.user)
        return order

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != SalesOrder.Status.DRAFT:
            raise BusinessRuleError("Only draft orders can be edited.")
        # CR-122: once converted to an invoice, SO lines/header must not diverge.
        if getattr(instance, "converted_invoice_id", None):
            raise BusinessRuleError(
                "This sales order already has an invoice and cannot be edited."
            )
        from .models import DeliveryChallan

        if DeliveryChallan.objects.filter(sales_order=instance).exclude(
            status=DeliveryChallan.Status.CANCELLED
        ).exists():
            raise BusinessRuleError(
                "This sales order already has a delivery challan and cannot be edited."
            )
        request = self.context["request"]
        items_data = preserve_expected_prices(
            request, validated_data.pop("items", None), instance.items.order_by("id")
        )
        ship_to = validated_data.pop("ship_to", None)
        if ship_to is not None and not (validated_data.get("delivery_address") or "").strip():
            # Choosing a saved address on an edit sets the delivery address (unless one was typed).
            validated_data["delivery_address"] = ship_to.address
        instance = super().update(instance, validated_data)
        if items_data is not None:
            # An edit sends the stored (exclusive) prices back; see set_order_items.
            SalesNotesService.set_order_items(
                instance, [dict(l) for l in items_data], request.user, lines_are_exclusive=True
            )
        return instance


class DeliveryChallanItemSerializer(CostMaskedLineMixin, _BaseLineSerializer):
    class Meta:
        model = DeliveryChallanItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount",
            "batch", "batch_no", "serial_numbers", "expected_price",
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
    expected_profit = serializers.SerializerMethodField()

    def get_expected_profit(self, obj):
        from .expected_profit import can_view_expected_profit, expected_profit_for_challan

        if not can_view_expected_profit(self.context.get("request")):
            return None
        return expected_profit_for_challan(obj)

    class Meta:
        model = DeliveryChallan
        fields = [
            "id", "number", "status", "customer", "customer_name", "warehouse", "sales_order",
            "challan_date", "vehicle_number", "transporter_name", "transporter_id",
            "transport_distance_km", "sub_supply_type", "trans_mode", "notes",
            "items", "pdf_status", "completed_at", "cancelled_at",
            "stock_posted", "converted_invoice", "delivery_address", "expected_profit",
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
        assert_customer_active(self, customer, "a delivery challan")
        return customer

    def validate_warehouse(self, warehouse):
        if warehouse is not None:
            self.check_company_ref(warehouse, "warehouse")
        return warehouse

    def validate_sales_order(self, sales_order):
        # CR-094: PrimaryKeyRelatedField bypasses viewset company scoping.
        if sales_order is not None:
            self.check_company_ref(sales_order, "sales_order")
            # CR-120: cannot attach SO that already has an invoice.
            if getattr(sales_order, "converted_invoice_id", None):
                from core.exceptions import BusinessRuleError

                raise BusinessRuleError(
                    "This sales order already has an invoice and cannot be linked "
                    "to a delivery challan."
                )
        return sales_order

    def create(self, validated_data):
        request = self.context["request"]
        items_data = strip_expected_prices(request, validated_data.pop("items"))
        challan = DeliveryChallan.objects.create(**validated_data)
        SalesNotesService.set_challan_items(challan, [dict(l) for l in items_data], request.user)
        return challan

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != DeliveryChallan.Status.DRAFT:
            raise BusinessRuleError("Completed challan cannot be edited.")
        request = self.context["request"]
        items_data = preserve_expected_prices(
            request, validated_data.pop("items", None), instance.items.order_by("id")
        )
        instance = super().update(instance, validated_data)
        if items_data is not None:
            SalesNotesService.set_challan_items(instance, [dict(l) for l in items_data], request.user)
        return instance
