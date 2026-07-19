"""Payment Service — receipts, supplier payments, allocations (§5.4, §8)."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from core.events import emit
from core.exceptions import BusinessRuleError
from core.services.document_numbers import DocumentNumberService

from .models import CustomerReceipt, PaymentAllocation, SupplierPayment


def _allocated_of_payment(payment_field, payment) -> Decimal:
    return (
        PaymentAllocation.objects.filter(**{payment_field: payment})
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )


class PaymentService:
    @staticmethod
    @transaction.atomic
    def create_receipt(*, company, customer, amount, mode, receipt_date=None,
                       reference="", notes="", user=None):
        if Decimal(amount) <= 0:
            raise BusinessRuleError("Receipt amount must be greater than zero.")
        if customer.company_id != company.id:
            raise BusinessRuleError("Invalid customer reference.")
        receipt = CustomerReceipt(
            company=company, customer=customer, amount=amount, mode=mode,
            reference=reference, notes=notes, created_by=user, updated_by=user,
            number=DocumentNumberService.next_number(company, "CUSTOMER_RECEIPT"),
        )
        if receipt_date:
            receipt.receipt_date = receipt_date
        receipt.save()
        emit("document.completed", document=receipt, user=user, event="customer_receipt.created")
        return receipt

    @staticmethod
    @transaction.atomic
    def create_supplier_payment(*, company, supplier, amount, mode, payment_date=None,
                                reference="", notes="", user=None):
        if Decimal(amount) <= 0:
            raise BusinessRuleError("Payment amount must be greater than zero.")
        if supplier.company_id != company.id:
            raise BusinessRuleError("Invalid supplier reference.")
        payment = SupplierPayment(
            company=company, supplier=supplier, amount=amount, mode=mode,
            reference=reference, notes=notes, created_by=user, updated_by=user,
            number=DocumentNumberService.next_number(company, "SUPPLIER_PAYMENT"),
        )
        if payment_date:
            payment.payment_date = payment_date
        payment.save()
        emit("document.completed", document=payment, user=user, event="supplier_payment.created")
        return payment

    @staticmethod
    @transaction.atomic
    def allocate_receipt(*, receipt, sales_invoice, amount, user=None):
        from ledgers.services import LedgerService

        amount = Decimal(amount)
        if amount <= 0:
            raise BusinessRuleError("Allocation amount must be greater than zero.")
        if receipt.company_id != sales_invoice.company_id:
            raise BusinessRuleError("Receipt and invoice belong to different companies.")
        if receipt.customer_id != sales_invoice.customer_id:
            raise BusinessRuleError("Receipt customer must match the invoice customer.")
        if sales_invoice.status not in ("COMPLETED", "RETURNED"):
            raise BusinessRuleError("Allocations are only allowed against completed invoices.")

        unallocated = receipt.amount - _allocated_of_payment("receipt", receipt)
        if amount > unallocated:
            raise BusinessRuleError(
                f"Allocation {amount} exceeds unallocated receipt amount {unallocated}."
            )
        open_outstanding = LedgerService.sales_invoice_outstanding(sales_invoice)
        if amount > open_outstanding:
            raise BusinessRuleError(
                f"Allocation {amount} exceeds invoice open outstanding {open_outstanding}."
            )
        return PaymentAllocation.objects.create(
            company=receipt.company, receipt=receipt, sales_invoice=sales_invoice,
            amount=amount, created_by=user, updated_by=user,
        )

    @staticmethod
    @transaction.atomic
    def allocate_supplier_payment(*, payment, purchase_invoice, amount, user=None):
        from ledgers.services import LedgerService

        amount = Decimal(amount)
        if amount <= 0:
            raise BusinessRuleError("Allocation amount must be greater than zero.")
        if payment.company_id != purchase_invoice.company_id:
            raise BusinessRuleError("Payment and invoice belong to different companies.")
        if payment.supplier_id != purchase_invoice.supplier_id:
            raise BusinessRuleError("Payment supplier must match the invoice supplier.")
        if purchase_invoice.status != "COMPLETED":
            raise BusinessRuleError("Allocations are only allowed against completed invoices.")

        unallocated = payment.amount - _allocated_of_payment("supplier_payment", payment)
        if amount > unallocated:
            raise BusinessRuleError(
                f"Allocation {amount} exceeds unallocated payment amount {unallocated}."
            )
        open_outstanding = LedgerService.purchase_invoice_outstanding(purchase_invoice)
        if amount > open_outstanding:
            raise BusinessRuleError(
                f"Allocation {amount} exceeds invoice open outstanding {open_outstanding}."
            )
        return PaymentAllocation.objects.create(
            company=payment.company, supplier_payment=payment,
            purchase_invoice=purchase_invoice, amount=amount,
            created_by=user, updated_by=user,
        )
