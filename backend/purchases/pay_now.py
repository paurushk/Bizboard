"""Pay-at-entry for purchase bills (Purchase review F-01 / WP-1).

Recording a payment against a bill used to be separate client calls (create payment,
then create allocation, with the bill already completed). A failure between them left
an orphan supplier advance. Here the payment and its allocation are one transaction:
both exist or neither does. The bill itself stays COMPLETED either way, because
completion (stock + ledger) is a different event from paying.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException

from core.exceptions import BusinessRuleError
from core.models import FileAsset
from core.serializers import CompanyPrimaryKeyRelatedField
from payments.models import BankAccount, PaymentMode, SupplierPayment
from payments.services import PaymentService

from .models import PurchaseInvoice


class PurchasePayNowSerializer(serializers.Serializer):
    """The payment details typed on the bill editor, validated like the payments screen."""

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    mode = serializers.ChoiceField(choices=PaymentMode.choices, default=PaymentMode.CASH)
    payment_date = serializers.DateField(required=False, allow_null=True, default=None)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    utr = serializers.CharField(required=False, allow_blank=True, max_length=64, default="")
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")
    bank_account = CompanyPrimaryKeyRelatedField(
        queryset=BankAccount.objects.all(), required=False, allow_null=True, default=None
    )
    cheque_number = serializers.CharField(required=False, allow_blank=True, max_length=32, default="")
    cheque_bank_name = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    cheque_date = serializers.DateField(required=False, allow_null=True, default=None)
    cheque_image = CompanyPrimaryKeyRelatedField(
        queryset=FileAsset.objects.all(), required=False, allow_null=True, default=None
    )
    gstin_hold_override = serializers.BooleanField(required=False, default=False)
    gstin_hold_reason = serializers.CharField(required=False, allow_blank=True, default="")


def record_payment_at_entry(invoice: PurchaseInvoice, user, pay: dict):
    """Create a supplier payment and allocate all of it to `invoice`, atomically.

    Raises (and rolls back the payment) if either step fails. Returns (payment, allocation).
    """
    with transaction.atomic():
        invoice = PurchaseInvoice.objects.select_for_update().get(
            pk=invoice.pk, company_id=invoice.company_id
        )
        if invoice.status != PurchaseInvoice.Status.COMPLETED:
            raise BusinessRuleError("Payments can only be recorded against a completed purchase.")
        amount = Decimal(str(pay["amount"])).quantize(Decimal("0.01"))
        payment = PaymentService.create_supplier_payment(
            company=invoice.company,
            supplier=invoice.supplier,
            amount=amount,
            mode=pay.get("mode") or PaymentMode.CASH,
            payment_date=pay.get("payment_date"),
            reference=pay.get("reference", ""),
            utr=pay.get("utr", ""),
            notes=pay.get("notes") or f"Against {invoice.number or invoice.pk}",
            bank_account=pay.get("bank_account"),
            cheque_number=pay.get("cheque_number", ""),
            cheque_bank_name=pay.get("cheque_bank_name", ""),
            cheque_date=pay.get("cheque_date"),
            cheque_image=pay.get("cheque_image"),
            gstin_hold_override=bool(pay.get("gstin_hold_override")),
            gstin_hold_reason=pay.get("gstin_hold_reason", ""),
            user=user,
        )
        allocation = PaymentService.allocate_supplier_payment(
            payment=payment, purchase_invoice=invoice, amount=amount, user=user
        )
    return payment, allocation


def payment_error_payload(exc: Exception) -> dict:
    """A small, stable error shape the UI can show next to a Retry button."""
    if isinstance(exc, APIException):
        detail = exc.detail
        if isinstance(detail, dict):
            message = " ".join(str(v) for v in detail.values())
        elif isinstance(detail, list):
            message = " ".join(str(v) for v in detail)
        else:
            message = str(detail)
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else str(getattr(exc, "default_code", "") or "payment_failed")
    else:
        message = "The payment could not be recorded."
        code = "payment_failed"
    payload = {"code": code, "message": message}
    extra = getattr(exc, "extra", None)
    if extra:
        payload["details"] = extra
    return payload


def payment_summary(payment: SupplierPayment, allocation) -> dict:
    return {
        "id": payment.pk,
        "number": payment.number,
        "amount": str(payment.amount),
        "mode": payment.mode,
        "allocation": allocation.pk,
    }
