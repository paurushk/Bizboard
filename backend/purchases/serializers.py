from rest_framework import serializers

from core.permissions import get_company_user
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Product

from .models import PurchaseInvoice, PurchaseItem, PurchaseReturn, PurchaseReturnItem
from .services import PurchaseService

LINE_READONLY = ["taxable_amount", "cgst", "sgst", "igst", "cess", "line_total"]
TOTAL_READONLY = [
    "subtotal", "discount_total", "taxable_total", "cgst_total", "sgst_total",
    "igst_total", "cess_total", "round_off", "grand_total",
]


class CompanyScopedSerializerMixin:
    @property
    def company(self):
        return get_company_user(self.context["request"]).company

    def check_company_ref(self, obj, field):
        if obj is not None and obj.company_id != self.company.id:
            raise serializers.ValidationError({field: "Invalid reference."})


class PurchaseItemSerializer(serializers.ModelSerializer):
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = PurchaseItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate", "cess_rate", "cess_amount",
            "hsn_code", "mrp", "unit_name", "uqc_code", "unit_price_inclusive",
            "batch", "batch_no", "exp_date", "mfg_date", "serial_numbers",
            "applied_rate", "rate_version", "rate_override", "rate_override_reason",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY + ["hsn_code", "mrp", "uqc_code", "applied_rate", "rate_version"]
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
            "id", "number", "status", "purchase_type", "supplier", "supplier_name", "warehouse", "cost_center",
            "invoice_date", "due_date", "payment_terms_days",
            "additional_charges", "invoice_discount", "invoice_discount_mode", "auto_round_off",
            "supplier_bill_number", "notes", "terms_text",
            "include_bank_details", "include_payment_qr", "include_terms",
            "signature", "attachment", "items",
            "is_reverse_charge", "itc_eligibility", "rcm_taxable", "rcm_cgst", "rcm_sgst", "rcm_igst",
            "company_gstin", "price_mode",
            "tds_section", "tds_rate", "tds_amount",
            "paid", "balance",
            "completed_at", "cancelled_at", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = [
            "number", "status", "paid", "balance",
            "rcm_taxable", "rcm_cgst", "rcm_sgst", "rcm_igst",
            "completed_at", "cancelled_at",
        ] + TOTAL_READONLY

    def _payable(self, obj):
        from decimal import Decimal

        return max(
            Decimal(str(obj.grand_total or 0)) - Decimal(str(getattr(obj, "tds_amount", 0) or 0)),
            Decimal("0"),
        )

    def get_balance(self, obj):
        from decimal import Decimal

        payable = self._payable(obj)
        if obj.status == PurchaseInvoice.Status.DRAFT:
            return payable
        allocated = getattr(obj, "_allocated", None)
        if allocated is not None and self.context.get("view") and getattr(
            self.context["view"], "action", None
        ) == "list":
            return max(payable - Decimal(str(allocated or 0)), Decimal("0"))
        from ledgers.services import LedgerService

        return LedgerService.purchase_invoice_outstanding(obj)

    def get_paid(self, obj):
        from decimal import Decimal

        balance = Decimal(str(self.get_balance(obj) or 0))
        return max(self._payable(obj) - balance, Decimal("0"))

    def validate_supplier(self, supplier):
        self.check_company_ref(supplier, "supplier")
        return supplier

    def validate_company_gstin(self, company_gstin):
        if company_gstin is not None:
            self.check_company_ref(company_gstin, "company_gstin")
        return company_gstin

    def validate_warehouse(self, warehouse):
        if warehouse is not None:
            self.check_company_ref(warehouse, "warehouse")
        return warehouse

    def validate_cost_center(self, cost_center):
        if cost_center is not None:
            self.check_company_ref(cost_center, "cost_center")
        return cost_center

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

        from masters.models import Customer as _Customer

        items_data = validated_data.pop("items")
        supplier = validated_data.get("supplier")
        # Supplier reuses Customer.TaxpayerType choices (no nested enum on Supplier).
        if (
            supplier is not None
            and getattr(supplier, "taxpayer_type", None) == _Customer.TaxpayerType.COMPOSITION
            and "itc_eligibility" not in validated_data
        ):
            validated_data["itc_eligibility"] = PurchaseInvoice.ItcEligibility.INELIGIBLE
        # BUG-208: defer numbering to Complete, matching sales invoices.
        with transaction.atomic():
            invoice = PurchaseInvoice.objects.create(**validated_data)
            PurchaseService.set_items(
                invoice, self._prepare_items(items_data), self.context["request"].user
            )
            return invoice

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError
        from core.permissions import get_company_user
        from core.services.h9_amend import (
            assert_h9a_line_allowlist,
            existing_lines_as_items_data,
            lines_prices_unchanged,
        )

        if instance.status in (PurchaseInvoice.Status.CANCELLED, PurchaseInvoice.Status.RETURNED):
            raise BusinessRuleError("Cancelled/returned purchase cannot be edited.")
        if instance.status == PurchaseInvoice.Status.COMPLETED and "supplier" in validated_data:
            if validated_data["supplier"].pk != instance.supplier_id:
                raise BusinessRuleError("Cannot change supplier on a completed purchase.")

        items_data = validated_data.pop("items", serializers.empty)
        request = self.context["request"]
        raw = getattr(request, "data", None) or {}
        confirm_raw = raw.get("confirm_amend") if hasattr(raw, "get") else None
        confirm_amend = confirm_raw in (True, "true", "True", 1, "1")

        money_fields = {
            "additional_charges", "invoice_discount", "invoice_discount_mode", "auto_round_off",
            "price_mode", "is_reverse_charge", "itc_eligibility",
            "tds_rate", "tds_amount",
            "company_gstin", "invoice_date", "warehouse", "supplier_bill_number",
            "purchase_type",
        }
        money_changing = bool(money_fields & set(validated_data.keys()))
        items_in_request = items_data is not serializers.empty
        existing_qs = instance.items.select_related("product")

        lines_price_changing = False
        prepared = None
        if items_in_request:
            prepared = self._prepare_items(items_data)

        if instance.status == PurchaseInvoice.Status.COMPLETED and items_in_request:
            assert_h9a_line_allowlist(existing_qs, prepared)
            lines_price_changing = not lines_prices_unchanged(existing_qs, prepared)

        needs_amend = instance.status == PurchaseInvoice.Status.COMPLETED and (
            money_changing or lines_price_changing
        )
        if needs_amend:
            from reporting.gst_periods import assert_period_allows_money_amend

            assert_period_allows_money_amend(instance.company, instance.invoice_date)
            cu = get_company_user(request)
            is_owner = cu is not None and cu.role == "OWNER"
            if not confirm_amend or not is_owner:
                raise BusinessRuleError(
                    "Completed purchases require Owner confirm_amend to change "
                    "prices, discounts, or additional charges."
                )

        if items_data is serializers.empty:
            prepared = None

        from core.models import log_money_change

        for fld in ("additional_charges", "invoice_discount", "grand_total", "taxable_total"):
            if fld in validated_data:
                log_money_change(
                    company=instance.company,
                    entity_type="purchaseinvoice",
                    entity_id=instance.pk,
                    field=fld,
                    old_value=getattr(instance, fld, ""),
                    new_value=validated_data[fld],
                    user=request.user,
                )

        instance = super().update(instance, validated_data)
        user = self.context["request"].user

        from purchases.services import assert_claimable_itc_allowed, assert_invoice_tds_exclusive

        assert_invoice_tds_exclusive(instance)
        assert_claimable_itc_allowed(instance)

        if instance.status == PurchaseInvoice.Status.COMPLETED:
            if needs_amend:
                from django.db import transaction

                payload = prepared if prepared is not None else existing_lines_as_items_data(instance.items)
                with transaction.atomic():
                    PurchaseService.set_items(instance, payload, user)
                    instance.refresh_from_db()
                    PurchaseService.restamp_fifo_layers_for_price_amend(instance)
                    # set_items already reversed+reposted via adjust_purchase_invoice_postings.
                    from reporting.gst_periods import mark_period_dirty_if_snapshotted

                    mark_period_dirty_if_snapshotted(instance.company, instance.invoice_date)
            return instance

        if prepared is not None:
            PurchaseService.set_items(instance, prepared, user)
        else:
            PurchaseService.set_items(instance, existing_lines_as_items_data(instance.items), user)
        return instance


class PurchaseReturnItemSerializer(serializers.ModelSerializer):
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = PurchaseReturnItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate",
            "batch", "serial_numbers", "condition",
        ] + LINE_READONLY
        read_only_fields = LINE_READONLY
        extra_kwargs = {
            "unit_price": {"required": False},
            "gst_rate": {"required": False},
            "batch": {"required": False, "allow_null": True},
            "serial_numbers": {"required": False},
            "condition": {"required": False},
        }


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

    def validate(self, attrs):
        supplier = attrs.get("supplier") or getattr(self.instance, "supplier", None)
        invoice = attrs.get("purchase_invoice") or getattr(self.instance, "purchase_invoice", None)
        if supplier is not None and invoice is not None and supplier.pk != invoice.supplier_id:
            raise serializers.ValidationError(
                {"supplier": "Supplier must match the linked purchase bill."}
            )
        return attrs

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
