from decimal import Decimal

from django.db.models import Sum
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice

from .models import (
    AdvanceRefundStatus,
    BankAccount,
    CustomerAdvanceRefund,
    BankStatement,
    BankStatementLine,
    CustomerReceipt,
    GatewayPayment,
    PaymentAllocation,
    PaymentLink,
    PaymentPromise,
    ReconMatch,
    SupplierPayment,
)
from .receipt_math import LiveTotals, cash_available, receipt_unallocated
from .upi import upi_qr_fields


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = [
            "id",
            "name",
            "account_number_masked",
            "ifsc",
            "account_type",
            "opening_balance",
            "opening_as_of",
            "is_default",
            "is_active",
            "created_at",
        ]


class ReceiptAllocationLineSerializer(serializers.Serializer):
    """One live invoice allocation on a receipt (read-only, for the voucher)."""

    sales_invoice = serializers.IntegerField(allow_null=True)
    invoice_number = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    discount_applied = serializers.DecimalField(max_digits=14, decimal_places=2)
    tds_applied = serializers.DecimalField(max_digits=14, decimal_places=2)
    allocation_id = serializers.IntegerField()


class ReceiptSummarySerializer(serializers.Serializer):
    """Totals for the receipt list filters, across every page."""

    count = serializers.IntegerField(help_text="Receipts counted as money in hand.")
    collected = serializers.DecimalField(max_digits=16, decimal_places=2)
    cheques_pending = serializers.DecimalField(max_digits=16, decimal_places=2)
    allocated = serializers.DecimalField(max_digits=16, decimal_places=2)
    advance = serializers.DecimalField(max_digits=16, decimal_places=2)
    excluded_count = serializers.IntegerField(help_text="Matching receipts left out: voided, refunded or bounced.")
    refunded = serializers.DecimalField(
        max_digits=16, decimal_places=2, help_text="Advances handed back to customers (live refunds)."
    )


class SupplierPaymentSummarySerializer(serializers.Serializer):
    """Totals for the supplier payment list filters, across every page."""

    count = serializers.IntegerField(help_text="Payments counted as money out.")
    paid = serializers.DecimalField(max_digits=16, decimal_places=2, help_text="Cleared money paid out.")
    cheques_pending = serializers.DecimalField(max_digits=16, decimal_places=2)
    advance = serializers.DecimalField(
        max_digits=16, decimal_places=2, help_text="Paid to suppliers but not yet applied to a bill."
    )
    excluded_count = serializers.IntegerField(help_text="Matching payments left out: voided or bounced.")
    payable = serializers.DecimalField(
        max_digits=16, decimal_places=2, allow_null=True,
        help_text="Owed to suppliers today. Null unless the caller may view financial reports.",
    )
    overdue = serializers.DecimalField(
        max_digits=16, decimal_places=2, allow_null=True,
        help_text="Part of payable that is past due. Null unless the caller may view financial reports.",
    )


class AdvanceRefundLineSerializer(serializers.ModelSerializer):
    """One advance refund paid out of a receipt (read-only, for the voucher and the list)."""

    class Meta:
        model = CustomerAdvanceRefund
        fields = [
            "id", "number", "amount", "mode", "refund_date", "reason", "status",
            "utr", "bank_account", "void_reason", "voided_at",
        ]
        read_only_fields = fields


class CustomerReceiptSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    bank_account_name = serializers.CharField(source="bank_account.name", read_only=True, default="")
    customer_is_walk_in = serializers.BooleanField(source="customer.is_pos_walk_in", read_only=True)
    voided_by_name = serializers.SerializerMethodField()
    allocated = serializers.SerializerMethodField()
    unallocated = serializers.SerializerMethodField()
    allocatable = serializers.SerializerMethodField()
    refunded = serializers.SerializerMethodField()
    advance_refunds = serializers.SerializerMethodField()
    reconciled = serializers.SerializerMethodField()
    allocation_lines = serializers.SerializerMethodField()
    review_flags = serializers.SerializerMethodField()
    utr_warning = serializers.SerializerMethodField()

    class Meta:
        model = CustomerReceipt
        fields = [
            "id",
            "number",
            "customer",
            "customer_name",
            "customer_is_walk_in",
            "amount",
            "tendered",
            "change_given",
            "mode",
            "receipt_date",
            "reference",
            "utr",
            "notes",
            "bank_account",
            "bank_account_name",
            "source",
            "gateway_payment",
            "status",
            "allocated",
            "unallocated",
            "allocatable",
            "refunded",
            "advance_refunds",
            "reconciled",
            "tds_deducted",
            "tds_section",
            "tds_certificate_received_on",
            "tds_certificate_ref",
            "allocate_on_clear",
            "intended_sales_invoice",
            "intended_amount",
            "advance_gst_rate",
            "utr_warning",
            "created_at",
            "cheque_number",
            "cheque_bank_name",
            "cheque_date",
            "cheque_status",
            "cheque_image",
            "paid_from_till",
            "shift",
            "settlement_discount",
            "dishonour_fee",
            "section_138_notice",
            "allocation_lines",
            "review_flags",
            "void_reason",
            "voided_at",
            "voided_by_name",
        ]
        read_only_fields = [
            "number", "source", "gateway_payment", "status", "shift",
            "tendered", "change_given",
            "dishonour_fee", "section_138_notice",
            "tds_certificate_received_on", "tds_certificate_ref",
            "void_reason", "voided_at",
            "allocate_on_clear", "intended_sales_invoice", "intended_amount",
        ]

    def validate_mode(self, value):
        if str(value).upper() == "CREDIT":
            raise serializers.ValidationError(
                "Credit is not a way of being paid. Leave the invoice unpaid, or record the "
                "cash, UPI, bank, card or cheque that came in."
            )
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        amount = attrs.get("amount")
        for field in ("settlement_discount", "tds_deducted"):
            value = attrs.get(field)
            if value is None:
                continue
            if value < 0:
                raise serializers.ValidationError({field: "Cannot be negative."})
            if amount is not None and value > amount:
                raise serializers.ValidationError(
                    {field: "Cannot be more than the amount received."}
                )
        return attrs

    def _live_allocations(self, obj):
        # Reads the prefetch when the viewset provided one (list), else one query.
        return [row for row in obj.allocations.all() if row.reversed_at is None]

    def _live_refunds(self, obj):
        return [row for row in obj.advance_refunds.all() if row.status == AdvanceRefundStatus.POSTED]

    def get_allocated(self, obj) -> Decimal:
        return sum((row.amount for row in self._live_allocations(obj)), Decimal("0"))

    def get_refunded(self, obj) -> Decimal:
        return sum((row.amount for row in self._live_refunds(obj)), Decimal("0"))

    @extend_schema_field(AdvanceRefundLineSerializer(many=True))
    def get_advance_refunds(self, obj):
        return AdvanceRefundLineSerializer(list(obj.advance_refunds.all()), many=True).data

    def get_reconciled(self, obj) -> bool:
        return bool(list(obj.recon_matches.all()) or list(obj.aa_transactions.all()))

    @extend_schema_field(ReceiptAllocationLineSerializer(many=True))
    def get_allocation_lines(self, obj):
        return [
            {
                "sales_invoice": row.sales_invoice_id,
                "invoice_number": (row.sales_invoice.number if row.sales_invoice_id else "") or "",
                "amount": row.amount,
                "discount_applied": row.discount_applied,
                "tds_applied": row.tds_applied,
                "allocation_id": row.pk,
            }
            for row in self._live_allocations(obj)
        ]

    def get_review_flags(self, obj) -> list[str]:
        """Derived warnings: nothing is stored for these.

        ``invoice_returned_after_payment``: an invoice this receipt paid was later returned or
        credit-noted, so the money may now be an advance that someone should look at.
        """
        flags = []
        for row in self._live_allocations(obj):
            invoice = row.sales_invoice
            if invoice is None:
                continue
            returned = invoice.status == "RETURNED" or any(
                note.status == "COMPLETED" and note.note_date >= obj.receipt_date
                for note in invoice.credit_notes.all()
            )
            if returned:
                flags.append("invoice_returned_after_payment")
                break
        return flags

    def get_voided_by_name(self, obj) -> str:
        user = obj.voided_by
        if user is None:
            return ""
        return getattr(user, "full_name", "") or getattr(user, "email", "") or ""

    def get_unallocated(self, obj) -> Decimal:
        # Customer Advances terms: amount + TDS - cash and TDS applied - refunds.
        live = LiveTotals.from_rows(self._live_allocations(obj))
        return receipt_unallocated(obj, live, self.get_refunded(obj))

    def get_allocatable(self, obj) -> Decimal:
        # Cash that can still be applied to invoices (excludes the TDS credit).
        live = LiveTotals.from_rows(self._live_allocations(obj))
        return cash_available(obj, live, self.get_refunded(obj))

    def get_utr_warning(self, obj):
        warn = getattr(obj, "_utr_warning", None)
        if warn:
            return warn
        if not obj.utr:
            return None
        # A list page looks the duplicates up once for the whole page (see the viewset); a
        # single receipt falls back to its own two queries.
        page_map = self.context.get("utr_duplicates")
        if page_map is not None:
            return page_map.get(obj.pk)
        from payments.services import _check_utr_duplicate

        return _check_utr_duplicate(company=obj.company, utr=obj.utr, exclude_receipt_id=obj.pk)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # CR-047: scope party FK to request company
        request = self.context.get("request")
        if not request:
            return
        from core.permissions import get_company_user

        cu = get_company_user(request)
        if cu and "customer" in self.fields:
            from masters.models import Customer

            self.fields["customer"].queryset = Customer.objects.filter(company=cu.company)
        # CR-008 / CR-136: bank_account FK must be company-scoped
        if cu and "bank_account" in self.fields:
            from payments.models import BankAccount

            self.fields["bank_account"].queryset = BankAccount.objects.filter(company=cu.company)


class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    bank_account_name = serializers.CharField(source="bank_account.name", read_only=True, default="")
    allocated = serializers.SerializerMethodField()
    unallocated = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # CR-047: scope party FK to request company
        request = self.context.get("request")
        if not request:
            return
        from core.permissions import get_company_user

        cu = get_company_user(request)
        if cu and "supplier" in self.fields:
            from masters.models import Supplier

            self.fields["supplier"].queryset = Supplier.objects.filter(company=cu.company)
        # CR-136: bank_account FK must be company-scoped
        if cu and "bank_account" in self.fields:
            from payments.models import BankAccount

            self.fields["bank_account"].queryset = BankAccount.objects.filter(company=cu.company)

    class Meta:
        model = SupplierPayment
        fields = [
            "id",
            "number",
            "supplier",
            "supplier_name",
            "amount",
            "mode",
            "payment_date",
            "reference",
            "utr",
            "notes",
            "bank_account",
            "bank_account_name",
            "source",
            "status",
            "tds_section",
            "tds_rate",
            "tds_amount",
            "allocated",
            "unallocated",
            "created_at",
            "cheque_number",
            "cheque_bank_name",
            "cheque_date",
            "cheque_status",
            "cheque_image",
            "paid_from_till",
            "shift",
        ]
        read_only_fields = ["number", "source", "status", "shift"]

    def get_allocated(self, obj) -> Decimal:
        return obj.allocations.filter(reversed_at__isnull=True).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    def get_unallocated(self, obj) -> Decimal:
        return (
            Decimal(str(obj.amount or 0))
            + Decimal(str(getattr(obj, "tds_amount", 0) or 0))
            - self.get_allocated(obj)
        )


class PaymentAllocationSerializer(serializers.ModelSerializer):
    receipt = CompanyPrimaryKeyRelatedField(
        queryset=CustomerReceipt.objects.all(), required=False, allow_null=True, default=None
    )
    supplier_payment = CompanyPrimaryKeyRelatedField(
        queryset=SupplierPayment.objects.all(), required=False, allow_null=True, default=None
    )
    sales_invoice = CompanyPrimaryKeyRelatedField(
        queryset=SalesInvoice.objects.all(), required=False, allow_null=True, default=None
    )
    purchase_invoice = CompanyPrimaryKeyRelatedField(
        queryset=PurchaseInvoice.objects.all(), required=False, allow_null=True, default=None
    )

    class Meta:
        model = PaymentAllocation
        fields = [
            "id",
            "receipt",
            "supplier_payment",
            "sales_invoice",
            "purchase_invoice",
            "amount",
            "discount_applied",
            "tds_applied",
            "reversed_at",
            "created_at",
        ]
        # BB-000084: company never client-writable on allocations.
        read_only_fields = ["created_at", "reversed_at", "discount_applied", "tds_applied"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # BB-000085: FK querysets scoped to request company.
        request = self.context.get("request")
        if not request:
            return
        from core.permissions import get_company_user

        cu = get_company_user(request)
        if cu is None:
            return
        company = cu.company
        for f_name, model_cls in (
            ("receipt", CustomerReceipt),
            ("supplier_payment", SupplierPayment),
            ("sales_invoice", SalesInvoice),
            ("purchase_invoice", PurchaseInvoice),
        ):
            if f_name in self.fields:
                self.fields[f_name].queryset = model_cls.objects.filter(company=company)
                self.fields[f_name].required = False
                self.fields[f_name].allow_null = True

    def validate(self, attrs):
        receipt = attrs.get("receipt")
        payment = attrs.get("supplier_payment")
        if bool(receipt) == bool(payment):
            raise serializers.ValidationError(
                "Provide exactly one of 'receipt' or 'supplier_payment'."
            )
        if receipt and not attrs.get("sales_invoice"):
            raise serializers.ValidationError("Receipt allocations require 'sales_invoice'.")
        if payment and not attrs.get("purchase_invoice"):
            raise serializers.ValidationError("Supplier payment allocations require 'purchase_invoice'.")
        return attrs


class PaymentLinkSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")
    invoice_number = serializers.CharField(source="sales_invoice.number", read_only=True, default="")
    public_path = serializers.SerializerMethodField()

    class Meta:
        model = PaymentLink
        fields = [
            "id",
            "token",
            "sales_invoice",
            "invoice_number",
            "customer",
            "customer_name",
            "amount",
            "allow_partial",
            "status",
            "expires_at",
            "provider",
            "provider_link_id",
            "provider_short_url",
            "paid_receipt",
            "notes",
            "public_path",
            "created_at",
        ]
        read_only_fields = [
            "token",
            "status",
            "provider_link_id",
            "provider_short_url",
            "paid_receipt",
        ]

    def get_public_path(self, obj):
        return f"/pay/{obj.token}"


class GatewayPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = GatewayPayment
        fields = [
            "id",
            "provider",
            "provider_payment_id",
            "amount",
            "fee",
            "status",
            "payment_link",
            "created_at",
            "holding_reason",
            "holding_error",
            "holding_since",
            "internal_utr",
        ]


class BankStatementLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankStatementLine
        fields = [
            "id",
            "statement",
            "txn_date",
            "value_date",
            "amount",
            "narration",
            "utr",
            "balance_after",
            "match_status",
            "line_hash",
        ]


class BankStatementSerializer(serializers.ModelSerializer):
    lines = BankStatementLineSerializer(many=True, read_only=True)
    bank_account_name = serializers.CharField(source="bank_account.name", read_only=True)
    line_count = serializers.SerializerMethodField()
    unmatched_count = serializers.SerializerMethodField()

    class Meta:
        model = BankStatement
        fields = [
            "id",
            "bank_account",
            "bank_account_name",
            "period_start",
            "period_end",
            "source_filename",
            "status",
            "preset",
            "line_count",
            "unmatched_count",
            "lines",
            "created_at",
        ]

    def get_line_count(self, obj):
        return obj.lines.count()

    def get_unmatched_count(self, obj):
        return obj.lines.filter(match_status="UNMATCHED").count()


class ReconMatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconMatch
        fields = [
            "id",
            "line",
            "receipt",
            "supplier_payment",
            "confidence",
            "matched_at",
            "matched_by",
            "notes",
            "needs_review",
            "review_reason",
        ]
        read_only_fields = ["needs_review", "review_reason"]


class PaymentPromiseSerializer(serializers.ModelSerializer):
    customer = CompanyPrimaryKeyRelatedField(queryset=Customer.objects.all())
    invoice = CompanyPrimaryKeyRelatedField(
        queryset=SalesInvoice.objects.all(), required=False, allow_null=True, default=None
    )
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default="")
    amount_label = serializers.SerializerMethodField()
    broken = serializers.SerializerMethodField()

    class Meta:
        model = PaymentPromise
        fields = [
            "id",
            "customer",
            "customer_name",
            "invoice",
            "invoice_number",
            "promised_date",
            "promised_amount",
            "amount_label",
            "broken",
            "note",
            "resolved",
            "resolved_at",
            "created_at",
        ]
        read_only_fields = ["resolved", "resolved_at", "amount_label", "broken"]

    def validate(self, attrs):
        if self.instance is None and attrs.get("promised_amount") is None:
            raise serializers.ValidationError(
                {"promised_amount": "Enter the amount the customer promised."}
            )
        return attrs

    def validate_promised_amount(self, value):
        if value is None or Decimal(str(value)) <= 0:
            raise serializers.ValidationError("Enter the amount the customer promised.")
        return value

    def get_amount_label(self, obj) -> str:
        from payments.promise_to_pay import promise_amount_label

        return promise_amount_label(obj)

    def get_broken(self, obj) -> bool:
        from payments.promise_to_pay import promise_is_broken

        return promise_is_broken(obj)


class UpiQrSerializer(serializers.Serializer):
    upi_id = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=40)
    sales_invoice = serializers.IntegerField(required=False)

    def create_payload(self, company):
        from sales.models import SalesInvoice

        data = self.validated_data
        upi_id = data.get("upi_id") or company.upi_id
        amount = data.get("amount")
        note = data.get("note") or ""
        inv_id = data.get("sales_invoice")
        if inv_id:
            inv = SalesInvoice.objects.filter(company=company, pk=inv_id).first()
            if inv:
                from ledgers.services import LedgerService

                amount = amount or LedgerService.sales_invoice_outstanding(inv)
                note = note or (inv.number or "")
        return upi_qr_fields(
            upi_id=upi_id,
            amount=amount,
            note=note,
            payee_name=company.legal_name or company.name,
        )
