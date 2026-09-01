from decimal import Decimal

from rest_framework import serializers

from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode
from core.permissions import get_company_user
from core.services.h9_amend import (
    assert_h9a_line_allowlist,
    existing_lines_as_items_data,
    lines_prices_unchanged,
)
from masters.models import Customer, Product

from .models import (
    Quotation,
    QuotationItem,
    RecurringInvoiceSchedule,
    SalesInvoice,
    SalesItem,
    SalesReturn,
    SalesReturnItem,
)
from .services import SalesService

LINE_READONLY = ["taxable_amount", "cgst", "sgst", "igst", "cess", "line_total"]
TOTAL_READONLY = [
    "subtotal", "discount_total", "taxable_total", "cgst_total", "sgst_total",
    "igst_total", "cess_total", "round_off", "grand_total",
]
RCM_READONLY = ["rcm_taxable", "rcm_cgst", "rcm_sgst", "rcm_igst", "rcm_cess"]


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
    # Override the model field so DRF does not emit a generic `invalid` before
    # `_validate_lines` — Why? needs HelpCode.INVALID_GST_RATE on create/edit.
    gst_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)

    def validate_gst_rate(self, value):
        from core.validators import ALLOWED_GST_RATES

        allowed = tuple(Decimal(r) for r in ALLOWED_GST_RATES)
        if Decimal(str(value)) not in allowed:
            raise BusinessRuleError(
                f"Invalid GST rate {value}. Allowed: {', '.join(ALLOWED_GST_RATES)}%.",
                code=HelpCode.INVALID_GST_RATE,
            )
        return value

    class Meta:
        model = SalesItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount",
            "hsn_code", "mrp", "unit_name", "uqc_code", "unit_price_inclusive",
            "batch", "batch_no", "exp_date", "mfg_date", "serial_numbers",
            "supply_nature",
            "applied_rate",
            "rate_version",
            "rate_override",
            "rate_override_reason",
            "applied_price_list_name",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY + [
            "hsn_code", "mrp", "uqc_code", "applied_rate", "rate_version",
            "applied_price_list_name",
        ]
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
    whatsapp_offer = serializers.SerializerMethodField()
    payment_state = serializers.SerializerMethodField()

    class Meta:
        model = SalesInvoice
        fields = [
            "id", "number", "status", "invoice_type", "customer", "customer_name", "warehouse", "cost_center",
            "invoice_date", "due_date", "payment_terms_days",
            "additional_charges", "charges_hsn", "charges_gst_rate",
            "invoice_discount", "invoice_discount_mode", "auto_round_off",
            "notes", "terms_text",
            "include_bank_details", "include_payment_qr", "include_terms",
            "signature",
            "items", "pdf_status", "pdf_file",
            "einvoice_status", "irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_error",
            "eway_status", "eway_bill_no", "eway_valid_upto", "eway_error",
            "filing_party_gstin", "filing_place_of_supply", "price_mode",
            "transporter_name", "transporter_id", "vehicle_number", "transport_distance_km",
            "sub_supply_type", "trans_mode",
            "supply_type", "company_gstin", "is_reverse_charge",
            "rcm_taxable", "rcm_cgst", "rcm_sgst", "rcm_igst", "rcm_cess",
            "ecommerce_operator_gstin",
            "tcs_section", "tcs_rate", "tcs_amount",
            "received", "balance", "is_opening_balance",
            "completed_at", "cancelled_at", "created_at", "updated_at",
            "whatsapp_send_status", "whatsapp_message_id", "whatsapp_share_link",
            "whatsapp_sent_at", "whatsapp_offer",
            "payment_state",
        ] + TOTAL_READONLY
        read_only_fields = [
            "number", "status", "pdf_status", "pdf_file", "received", "balance",
            "einvoice_status", "irn", "ack_no", "ack_date", "einvoice_qr", "einvoice_error",
            "eway_status", "eway_bill_no", "eway_valid_upto", "eway_error",
            "completed_at", "cancelled_at", "is_opening_balance",
            "whatsapp_send_status", "whatsapp_message_id", "whatsapp_share_link",
            "whatsapp_sent_at", "whatsapp_offer",
            "payment_state",
        ] + TOTAL_READONLY + RCM_READONLY

    def _receivable(self, obj):
        from decimal import Decimal

        extra = Decimal("0")
        if not getattr(obj, "tcs_in_grand_total", False):
            extra = Decimal(str(getattr(obj, "tcs_amount", 0) or 0))
        return Decimal(str(obj.grand_total or 0)) + extra

    def get_balance(self, obj):
        from decimal import Decimal

        receivable = self._receivable(obj)
        if obj.status == SalesInvoice.Status.DRAFT:
            return receivable
        allocated = getattr(obj, "_allocated", None)
        if allocated is not None and self.context.get("view") and getattr(
            self.context["view"], "action", None
        ) == "list":
            return max(receivable - Decimal(str(allocated or 0)), Decimal("0"))
        from ledgers.services import LedgerService

        return LedgerService.sales_invoice_outstanding(obj)

    def get_received(self, obj):
        from decimal import Decimal

        balance = Decimal(str(self.get_balance(obj) or 0))
        return max(self._receivable(obj) - balance, Decimal("0"))

    def get_whatsapp_offer(self, obj):
        from sales.whatsapp_send import whatsapp_offer_payload

        return whatsapp_offer_payload(obj)

    def get_payment_state(self, obj):
        from payments.holding import invoice_payment_state

        if obj.status == SalesInvoice.Status.DRAFT:
            return "UNPAID"
        return invoice_payment_state(obj)

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        if customer.status == Customer.Status.BLOCKED:
            raise serializers.ValidationError("Cannot create an invoice for a blocked customer.")
        return customer

    def validate_additional_charges(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Additional charges cannot be negative.")
        return value

    def validate_transporter_id(self, value):
        # TAX-10: 15-char GSTIN or 12-digit TRANSIN when provided.
        from sales.eway_payload import validate_eway_transport

        tid = (value or "").strip()
        if not tid:
            return tid
        errors = validate_eway_transport(
            vehicle_number="",
            distance_km=1,  # skip distance check for id-only validation
            transporter_id=tid,
        )
        id_errors = [e for e in errors if "transporter_id" in e]
        if id_errors:
            raise serializers.ValidationError(id_errors[0])
        return tid.replace(" ", "").upper()

    def validate_signature(self, signature):
        if signature is not None:
            self.check_company_ref(signature, "signature")
        return signature

    def validate_warehouse(self, warehouse):
        if warehouse is not None:
            self.check_company_ref(warehouse, "warehouse")
        return warehouse

    def validate_cost_center(self, cost_center):
        if cost_center is not None:
            self.check_company_ref(cost_center, "cost_center")
        return cost_center

    def validate_company_gstin(self, company_gstin):
        if company_gstin is not None:
            self.check_company_ref(company_gstin, "company_gstin")
        return company_gstin

    def create(self, validated_data):
        from django.db import transaction
        from core.permissions import get_company_user

        items_data = validated_data.pop("items")
        # BUG-208: numbers are assigned on Complete (SalesService.complete),
        # not on draft creation — a draft that's later deleted or abandoned
        # must not permanently burn a slot in the GST-sequential series.
        # ("number" is read-only, so it was never actually present here; this
        # used to unconditionally call next_number() on every single draft.)
        with transaction.atomic():
            invoice = SalesInvoice.objects.create(**validated_data)
            # TCS: an explicit tcs_amount at create time overrides the rate (see update()).
            if validated_data.get("tcs_amount"):
                invoice.tcs_amount_manual = True
                invoice.save(update_fields=["tcs_amount_manual"])
            # BB-000728: OWNER price-list override needs membership role.
            cu = get_company_user(self.context["request"])
            invoice._price_role = getattr(cu, "role", None) if cu else None
            SalesService.set_items(invoice, [dict(l) for l in items_data], self.context["request"].user)
            return invoice

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError
        from core.permissions import get_company_user

        if instance.status in (SalesInvoice.Status.CANCELLED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Cancelled/returned invoice cannot be edited.")
        if instance.status == SalesInvoice.Status.COMPLETED and "customer" in validated_data:
            if validated_data["customer"].pk != instance.customer_id:
                raise BusinessRuleError(
                    "Cannot change customer on a completed invoice.",
                    code=HelpCode.COMPLETED_IMMUTABLE,
                )

        items_data = validated_data.pop("items", serializers.empty)
        request = self.context["request"]
        raw = getattr(request, "data", None) or {}
        confirm_raw = raw.get("confirm_amend") if hasattr(raw, "get") else None
        confirm_amend = confirm_raw in (True, "true", "True", 1, "1")

        money_fields = {
            "additional_charges", "charges_hsn", "charges_gst_rate",
            "invoice_discount", "invoice_discount_mode", "auto_round_off",
            "price_mode",
            "tcs_rate", "tcs_amount", "is_reverse_charge", "supply_type", "company_gstin",
        }
        if instance.status == SalesInvoice.Status.COMPLETED:
            for fld in ("filing_party_gstin", "filing_place_of_supply"):
                if fld in validated_data and validated_data[fld] != getattr(instance, fld):
                    raise BusinessRuleError(
                        "Use the amend-filing-identity action to change filing GSTIN or place of supply."
                    )
        money_changing = bool(money_fields & set(validated_data.keys()))
        items_in_request = items_data is not serializers.empty
        existing_qs = instance.items.select_related("product")

        lines_price_changing = False
        if instance.status == SalesInvoice.Status.COMPLETED and items_in_request:
            assert_h9a_line_allowlist(existing_qs, items_data)
            lines_price_changing = not lines_prices_unchanged(existing_qs, items_data)

        needs_amend = instance.status == SalesInvoice.Status.COMPLETED and (
            money_changing or lines_price_changing
        )
        if needs_amend:
            from reporting.gst_periods import assert_period_allows_money_amend

            assert_period_allows_money_amend(instance.company, instance.invoice_date)
            # Live e-Invoice IRN: amend would desync portal — cancel IRN or use CN/DN.
            einvoice_status = getattr(instance, "einvoice_status", None)
            irn = (getattr(instance, "irn", None) or "").strip()
            live_irn = einvoice_status in (
                SalesInvoice.EInvoiceStatus.GENERATED,
                SalesInvoice.EInvoiceStatus.MANUAL_IRN,
            ) or (
                irn
                and einvoice_status
                not in (
                    SalesInvoice.EInvoiceStatus.CANCELLED,
                    SalesInvoice.EInvoiceStatus.NONE,
                )
            )
            if live_irn:
                raise BusinessRuleError(
                    "Cannot amend an invoice with an e-Invoice IRN. "
                    "Cancel the IRN first, or issue a credit/debit note instead."
                )
            cu = get_company_user(request)
            is_owner = cu is not None and cu.role == "OWNER"
            if not confirm_amend or not is_owner:
                raise BusinessRuleError(
                    "Completed invoices require Owner confirm_amend to change "
                    "prices, discounts, or additional charges."
                )

        if items_data is serializers.empty:
            items_data = None

        # Wave 17A: money field audit trail before save.
        from core.models import log_money_change

        for fld in ("additional_charges", "invoice_discount", "grand_total", "taxable_total"):
            if fld in validated_data:
                log_money_change(
                    company=instance.company,
                    entity_type="salesinvoice",
                    entity_id=instance.pk,
                    field=fld,
                    old_value=getattr(instance, fld, ""),
                    new_value=validated_data[fld],
                    user=request.user,
                )

        # TCS: an operator-supplied tcs_amount overrides the rate at Complete
        # (owner decision 2026-08-31). Remember which one it is; a rate-only edit
        # (tcs_rate present, tcs_amount absent) reverts to rate-computed.
        if "tcs_amount" in validated_data:
            instance.tcs_amount_manual = bool(validated_data.get("tcs_amount"))
        elif "tcs_rate" in validated_data:
            instance.tcs_amount_manual = False

        instance = super().update(instance, validated_data)
        user = self.context["request"].user
        # BB-000728: OWNER price-list override needs membership role.
        cu = get_company_user(request)
        instance._price_role = getattr(cu, "role", None) if cu else None

        if instance.status == SalesInvoice.Status.COMPLETED:
            if needs_amend:
                payload = (
                    [dict(l) for l in items_data]
                    if items_data is not None
                    else existing_lines_as_items_data(instance.items)
                )
                SalesService.set_items(instance, payload, user)
                # H9: reverse prior COMPLETE (+COGS) journals and re-post at amended totals.
                if instance.company.accounting_enabled:
                    from decimal import Decimal as D

                    from accounting.models import JournalEntry
                    from accounting.services import PostingService

                    for entry in JournalEntry.objects.filter(
                        company=instance.company,
                        source_type="SALES_INVOICE",
                        source_id=instance.id,
                        purpose__in=("COMPLETE", "COGS"),
                        status=JournalEntry.Status.POSTED,
                    ):
                        PostingService.reverse(entry, user, instance.invoice_date)
                    PostingService.post_sales_invoice(instance, user)
                    # Price-only H9: keep SALE peel unit_cost. Do not revalue from remaining layers.
                    from sales.cogs_service import CogsService

                    cogs_new = D("0")
                    sale_moves = CogsService.invoice_sale_moves(instance)
                    for move in sale_moves:
                        cogs_new += D(str(move.unit_cost or 0)) * abs(D(str(move.quantity)))
                    if not cogs_new:
                        prior = JournalEntry.objects.filter(
                            company=instance.company,
                            source_type="SALES_INVOICE",
                            source_id=instance.id,
                            purpose="COGS",
                            status=JournalEntry.Status.REVERSED,
                        ).order_by("-id").first()
                        if prior is not None:
                            from accounting.models import JournalLine

                            cogs_new = sum(
                                (
                                    D(str(line.debit or 0))
                                    for line in JournalLine.objects.filter(entry=prior, account__code="5400")
                                ),
                                D("0"),
                            )
                    if cogs_new:
                        PostingService.post_sales_cogs(instance, cogs_new, user)
                # BB-000275: money amend must dirty snapshotted GST periods.
                from reporting.gst_periods import mark_period_dirty_if_snapshotted

                mark_period_dirty_if_snapshotted(instance.company, instance.invoice_date)
            # else: notes/terms-only — no set_items, no PDF requeue
            return instance

        if items_data is not None:
            SalesService.set_items(instance, [dict(l) for l in items_data], user)
        else:
            SalesService.set_items(instance, existing_lines_as_items_data(instance.items), user)
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
            "converted_order", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "converted_invoice", "converted_order"] + TOTAL_READONLY

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        return customer

    def create(self, validated_data):
        from django.db import transaction

        from core.services.document_numbers import DocumentNumberService, resolve_series_gstin

        items_data = validated_data.pop("items")
        with transaction.atomic():
            quotation = Quotation.objects.create(**validated_data)
            if not quotation.number:
                quotation.number = DocumentNumberService.next_number(
                    quotation.company,
                    "QUOTATION",
                    gstin=resolve_series_gstin(quotation.company),
                    on_date=quotation.quotation_date,
                )
                quotation.save(update_fields=["number"])
            SalesService.set_quotation_items(
                quotation, [dict(l) for l in items_data], self.context["request"].user
            )
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
            "unit_price", "discount_percent", "gst_rate", "serial_numbers", "condition",
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


class RecurringInvoiceScheduleSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = RecurringInvoiceSchedule
        fields = [
            "id", "customer", "customer_name", "company_gstin", "cadence",
            "next_run_at", "is_active", "line_template", "notes",
            "created_at", "updated_at",
        ]

    def validate_customer(self, customer):
        self.check_company_ref(customer, "customer")
        return customer

    def validate_company_gstin(self, company_gstin):
        if company_gstin is not None:
            self.check_company_ref(company_gstin, "company_gstin")
        return company_gstin

    def validate_line_template(self, value):
        items = value if isinstance(value, list) else (value or {}).get("items")
        if not items:
            raise serializers.ValidationError("line_template.items is required.")
        return value if isinstance(value, dict) else {"items": value}
