from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice

from .models import (
    BankAccount,
    BankStatement,
    BankStatementLine,
    CustomerReceipt,
    GatewayPayment,
    PaymentAllocation,
    PaymentLink,
    ReconMatch,
    SupplierPayment,
)
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


class CustomerReceiptSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    bank_account_name = serializers.CharField(source="bank_account.name", read_only=True, default="")
    allocated = serializers.SerializerMethodField()
    unallocated = serializers.SerializerMethodField()
    utr_warning = serializers.SerializerMethodField()

    class Meta:
        model = CustomerReceipt
        fields = [
            "id",
            "number",
            "customer",
            "customer_name",
            "amount",
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
            "utr_warning",
            "created_at",
        ]
        read_only_fields = ["number", "source", "gateway_payment", "status"]

    def get_allocated(self, obj) -> Decimal:
        return obj.allocations.filter(reversed_at__isnull=True).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    def get_unallocated(self, obj) -> Decimal:
        return obj.amount - self.get_allocated(obj)

    def get_utr_warning(self, obj):
        warn = getattr(obj, "_utr_warning", None)
        if warn:
            return warn
        if not obj.utr:
            return None
        from payments.services import _check_utr_duplicate

        return _check_utr_duplicate(company=obj.company, utr=obj.utr, exclude_receipt_id=obj.pk)


class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    bank_account_name = serializers.CharField(source="bank_account.name", read_only=True, default="")
    allocated = serializers.SerializerMethodField()
    unallocated = serializers.SerializerMethodField()

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
        ]
        read_only_fields = ["number", "source", "status"]

    def get_allocated(self, obj) -> Decimal:
        return obj.allocations.filter(reversed_at__isnull=True).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    def get_unallocated(self, obj) -> Decimal:
        return obj.amount - self.get_allocated(obj)


class PaymentAllocationSerializer(serializers.ModelSerializer):
    receipt = serializers.PrimaryKeyRelatedField(
        queryset=CustomerReceipt.objects.all(), required=False, allow_null=True, default=None
    )
    supplier_payment = serializers.PrimaryKeyRelatedField(
        queryset=SupplierPayment.objects.all(), required=False, allow_null=True, default=None
    )
    sales_invoice = serializers.PrimaryKeyRelatedField(
        queryset=SalesInvoice.objects.all(), required=False, allow_null=True, default=None
    )
    purchase_invoice = serializers.PrimaryKeyRelatedField(
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
            "reversed_at",
            "created_at",
        ]
        # BB-000084: company never client-writable on allocations.
        read_only_fields = ["created_at", "reversed_at"]

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
        ]


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
