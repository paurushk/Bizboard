"""
Ledger Service (E5.1) — builds customer/supplier statements and outstanding
dynamically from business documents + allocations.

There are deliberately NO customer_ledgers / supplier_ledgers tables (§12.2):
documents are the only source of truth and can never drift.
"""

from decimal import Decimal

from django.db.models import Sum

from payments.models import CustomerReceipt, PaymentAllocation, SupplierPayment
from purchases.models import PurchaseInvoice, PurchaseReturn
from sales.models import SalesInvoice, SalesReturn

OPEN_SALES_STATUSES = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)


def _sum(qs, field="amount") -> Decimal:
    return qs.aggregate(total=Sum(field))["total"] or Decimal("0")


class LedgerService:
    # ---------------- Per-invoice open outstanding ----------------

    @staticmethod
    def sales_invoice_outstanding(invoice: SalesInvoice) -> Decimal:
        """grand_total − completed returns − allocated receipts (§5.4)."""
        if invoice.status not in OPEN_SALES_STATUSES:
            return Decimal("0")
        returns = _sum(
            SalesReturn.objects.filter(sales_invoice=invoice, status=SalesReturn.Status.COMPLETED),
            "grand_total",
        )
        allocated = _sum(PaymentAllocation.objects.filter(sales_invoice=invoice))
        return invoice.grand_total - returns - allocated

    @staticmethod
    def purchase_invoice_outstanding(invoice: PurchaseInvoice) -> Decimal:
        if invoice.status != PurchaseInvoice.Status.COMPLETED:
            return Decimal("0")
        returns = _sum(
            PurchaseReturn.objects.filter(
                purchase_invoice=invoice, status=PurchaseReturn.Status.COMPLETED
            ),
            "grand_total",
        )
        allocated = _sum(PaymentAllocation.objects.filter(purchase_invoice=invoice))
        return invoice.grand_total - returns - allocated

    # ---------------- Customer ledger ----------------

    @staticmethod
    def customer_outstanding(company, customer) -> Decimal:
        invoices = _sum(
            SalesInvoice.objects.filter(company=company, customer=customer, status__in=OPEN_SALES_STATUSES),
            "grand_total",
        )
        returns = _sum(
            SalesReturn.objects.filter(company=company, customer=customer, status=SalesReturn.Status.COMPLETED),
            "grand_total",
        )
        allocated = _sum(
            PaymentAllocation.objects.filter(
                company=company, sales_invoice__customer=customer, receipt__isnull=False
            )
        )
        return invoices - returns - allocated

    @staticmethod
    def bulk_customer_outstanding(company) -> dict:
        """BUG-301: one SQL aggregation per component instead of 3 queries
        per customer — CustomerLedgerListView used to issue `3N + 1` queries
        for N customers with no pagination at all."""
        invoices = dict(
            SalesInvoice.objects.filter(company=company, status__in=OPEN_SALES_STATUSES)
            .values("customer_id").annotate(total=Sum("grand_total"))
            .values_list("customer_id", "total")
        )
        returns = dict(
            SalesReturn.objects.filter(company=company, status=SalesReturn.Status.COMPLETED)
            .values("customer_id").annotate(total=Sum("grand_total"))
            .values_list("customer_id", "total")
        )
        allocated = dict(
            PaymentAllocation.objects.filter(company=company, receipt__isnull=False)
            .values("sales_invoice__customer_id").annotate(total=Sum("amount"))
            .values_list("sales_invoice__customer_id", "total")
        )
        customer_ids = set(invoices) | set(returns) | set(allocated)
        return {
            cid: (
                (invoices.get(cid) or Decimal("0"))
                - (returns.get(cid) or Decimal("0"))
                - (allocated.get(cid) or Decimal("0"))
            )
            for cid in customer_ids
        }

    @staticmethod
    def customer_statement(company, customer, date_from=None, date_to=None):
        """Running-balance statement built dynamically from documents."""
        entries = []
        invoices = SalesInvoice.objects.filter(
            company=company, customer=customer, status__in=OPEN_SALES_STATUSES
        )
        for inv in invoices:
            entries.append({
                "date": inv.invoice_date, "type": "SALES_INVOICE", "number": inv.number,
                "reference_id": inv.pk, "debit": inv.grand_total, "credit": Decimal("0"),
            })
        for ret in SalesReturn.objects.filter(
            company=company, customer=customer, status=SalesReturn.Status.COMPLETED
        ):
            entries.append({
                "date": ret.return_date, "type": "SALES_RETURN", "number": ret.number,
                "reference_id": ret.pk, "debit": Decimal("0"), "credit": ret.grand_total,
            })
        for receipt in CustomerReceipt.objects.filter(company=company, customer=customer):
            allocated = _sum(PaymentAllocation.objects.filter(receipt=receipt))
            unallocated = receipt.amount - allocated
            entries.append({
                "date": receipt.receipt_date, "type": "RECEIPT", "number": receipt.number,
                "reference_id": receipt.pk, "debit": Decimal("0"), "credit": receipt.amount,
                "is_advance": unallocated > 0,
                "unallocated": unallocated,
            })

        entries.sort(key=lambda e: (e["date"], e["reference_id"]))
        if date_from:
            entries = [e for e in entries if e["date"] >= date_from]
        if date_to:
            entries = [e for e in entries if e["date"] <= date_to]

        balance = Decimal("0")
        for entry in entries:
            balance += entry["debit"] - entry["credit"]
            entry["balance"] = balance
        return entries

    # ---------------- Supplier ledger ----------------

    @staticmethod
    def supplier_outstanding(company, supplier) -> Decimal:
        invoices = _sum(
            PurchaseInvoice.objects.filter(
                company=company, supplier=supplier, status=PurchaseInvoice.Status.COMPLETED
            ),
            "grand_total",
        )
        returns = _sum(
            PurchaseReturn.objects.filter(
                company=company, supplier=supplier, status=PurchaseReturn.Status.COMPLETED
            ),
            "grand_total",
        )
        allocated = _sum(
            PaymentAllocation.objects.filter(
                company=company, purchase_invoice__supplier=supplier, supplier_payment__isnull=False
            )
        )
        return invoices - returns - allocated

    @staticmethod
    def bulk_supplier_outstanding(company) -> dict:
        """BUG-301 (supplier side) — same N+1 fix as bulk_customer_outstanding."""
        invoices = dict(
            PurchaseInvoice.objects.filter(company=company, status=PurchaseInvoice.Status.COMPLETED)
            .values("supplier_id").annotate(total=Sum("grand_total"))
            .values_list("supplier_id", "total")
        )
        returns = dict(
            PurchaseReturn.objects.filter(company=company, status=PurchaseReturn.Status.COMPLETED)
            .values("supplier_id").annotate(total=Sum("grand_total"))
            .values_list("supplier_id", "total")
        )
        allocated = dict(
            PaymentAllocation.objects.filter(company=company, supplier_payment__isnull=False)
            .values("purchase_invoice__supplier_id").annotate(total=Sum("amount"))
            .values_list("purchase_invoice__supplier_id", "total")
        )
        supplier_ids = set(invoices) | set(returns) | set(allocated)
        return {
            sid: (
                (invoices.get(sid) or Decimal("0"))
                - (returns.get(sid) or Decimal("0"))
                - (allocated.get(sid) or Decimal("0"))
            )
            for sid in supplier_ids
        }

    @staticmethod
    def supplier_statement(company, supplier, date_from=None, date_to=None):
        entries = []
        for inv in PurchaseInvoice.objects.filter(
            company=company, supplier=supplier, status=PurchaseInvoice.Status.COMPLETED
        ):
            entries.append({
                "date": inv.invoice_date, "type": "PURCHASE_INVOICE", "number": inv.number,
                "reference_id": inv.pk, "credit": inv.grand_total, "debit": Decimal("0"),
            })
        for ret in PurchaseReturn.objects.filter(
            company=company, supplier=supplier, status=PurchaseReturn.Status.COMPLETED
        ):
            entries.append({
                "date": ret.return_date, "type": "PURCHASE_RETURN", "number": ret.number,
                "reference_id": ret.pk, "credit": Decimal("0"), "debit": ret.grand_total,
            })
        for payment in SupplierPayment.objects.filter(company=company, supplier=supplier):
            allocated = _sum(PaymentAllocation.objects.filter(supplier_payment=payment))
            unallocated = payment.amount - allocated
            entries.append({
                "date": payment.payment_date, "type": "PAYMENT", "number": payment.number,
                "reference_id": payment.pk, "credit": Decimal("0"), "debit": payment.amount,
                "is_advance": unallocated > 0,
                "unallocated": unallocated,
            })

        entries.sort(key=lambda e: (e["date"], e["reference_id"]))
        if date_from:
            entries = [e for e in entries if e["date"] >= date_from]
        if date_to:
            entries = [e for e in entries if e["date"] <= date_to]

        balance = Decimal("0")
        for entry in entries:
            balance += entry["credit"] - entry["debit"]
            entry["balance"] = balance
        return entries
