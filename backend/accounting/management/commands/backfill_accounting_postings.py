from decimal import Decimal

from django.core.management.base import BaseCommand

from accounts.models import Company
from accounting.models import JournalEntry, JournalLine
from accounting.services import PostingService, seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from inventory.models import MovementType, StockMovement
from payments.models import (
    CustomerReceipt,
    PaymentAllocation,
    ReceiptStatus,
    SupplierPayment,
    SupplierPaymentStatus,
)
from purchases.models import PurchaseCreditNote, PurchaseDebitNote, PurchaseInvoice
from sales.models import SalesCreditNote, SalesDebitNote, SalesInvoice, SalesReturn


def _has_je(company, source_type, source_id, purpose) -> bool:
    return JournalEntry.objects.filter(
        company=company,
        source_type=source_type,
        source_id=source_id,
        purpose=purpose,
        status=JournalEntry.Status.POSTED,
    ).exists()


def _is_opening_invoice(invoice) -> bool:
    return bool(getattr(invoice, "is_opening_balance", False)) or (
        (getattr(invoice, "notes", None) or "").strip() == "TALLY_OPENING"
    )


def _movement_cogs(company, movement_type, reference_type, reference_id) -> Decimal:
    return sum(
        (
            Decimal(str(movement.unit_cost or 0)) * abs(Decimal(str(movement.quantity or 0)))
            for movement in StockMovement.objects.filter(
                company=company,
                movement_type=movement_type,
                reference_type=reference_type,
                reference_id=str(reference_id),
            )
        ),
        Decimal("0"),
    )


class Command(BaseCommand):
    help = (
        "Post missing accounting journals for completed operational documents. "
        "Skips openings/COGS/returns that would double-post or use the wrong poster."
    )

    def handle(self, *args, **options):
        posted = 0
        skipped = 0
        for company in Company.objects.filter(accounting_enabled=True):
            seed_chart_of_accounts(company)
            si_statuses = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)
            for invoice in SalesInvoice.objects.filter(company=company, status__in=si_statuses):
                try:
                    if _is_opening_invoice(invoice):
                        if not _has_je(company, "SALES_INVOICE", invoice.id, "OPENING"):
                            if PostingService.post_opening_sales_invoice(invoice):
                                posted += 1
                        continue
                    if not _has_je(company, "SALES_INVOICE", invoice.id, "COMPLETE"):
                        if PostingService.post_sales_invoice(invoice):
                            posted += 1
                    if not _has_je(company, "SALES_INVOICE", invoice.id, "COGS"):
                        cogs = _movement_cogs(
                            company, MovementType.SALE, "sales_invoice", invoice.id
                        )
                        if cogs and PostingService.post_sales_cogs(invoice, cogs):
                            posted += 1
                except BusinessRuleError as exc:
                    skipped += 1
                    self.stderr.write(f"SI {invoice.id}: {exc}")

            pi_statuses = (PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED)
            for invoice in PurchaseInvoice.objects.filter(company=company, status__in=pi_statuses):
                try:
                    if _is_opening_invoice(invoice):
                        if not _has_je(company, "PURCHASE_INVOICE", invoice.id, "OPENING"):
                            if PostingService.post_opening_purchase_invoice(invoice):
                                posted += 1
                        continue
                    if not _has_je(company, "PURCHASE_INVOICE", invoice.id, "COMPLETE"):
                        if PostingService.post_purchase(invoice):
                            posted += 1
                except BusinessRuleError as exc:
                    skipped += 1
                    self.stderr.write(f"PI {invoice.id}: {exc}")

            for receipt in CustomerReceipt.objects.filter(company=company).exclude(
                status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED)
            ):
                try:
                    if not _has_je(company, "CUSTOMER_RECEIPT", receipt.id, "CREATE"):
                        if PostingService.post_receipt(receipt):
                            posted += 1
                except BusinessRuleError as exc:
                    skipped += 1
                    self.stderr.write(f"Receipt {receipt.id}: {exc}")

            for payment in SupplierPayment.objects.filter(company=company).exclude(
                status=SupplierPaymentStatus.VOIDED
            ):
                try:
                    if not _has_je(company, "SUPPLIER_PAYMENT", payment.id, "CREATE"):
                        if PostingService.post_supplier_payment(payment):
                            posted += 1
                except BusinessRuleError as exc:
                    skipped += 1
                    self.stderr.write(f"Payment {payment.id}: {exc}")

            for alloc in PaymentAllocation.objects.filter(
                company=company, reversed_at__isnull=True
            ).select_related("receipt", "supplier_payment"):
                try:
                    if alloc.receipt_id and not _has_je(
                        company, "PAYMENT_ALLOCATION", alloc.id, "ALLOCATE_RECEIPT"
                    ):
                        if PostingService.post_receipt_allocation(alloc):
                            posted += 1
                    elif alloc.supplier_payment_id and not _has_je(
                        company, "PAYMENT_ALLOCATION", alloc.id, "ALLOCATE_PAYMENT"
                    ):
                        if PostingService.post_supplier_payment_allocation(alloc):
                            posted += 1
                except BusinessRuleError as exc:
                    skipped += 1
                    self.stderr.write(f"Allocation {alloc.id}: {exc}")

            note_specs = (
                (SalesCreditNote, "SALES_CREDIT_NOTE", "SALES_CREDIT"),
                (SalesDebitNote, "SALES_DEBIT_NOTE", "SALES_DEBIT"),
                (PurchaseCreditNote, "PURCHASE_CREDIT_NOTE", "PURCHASE_CREDIT"),
                (PurchaseDebitNote, "PURCHASE_DEBIT_NOTE", "PURCHASE_DEBIT"),
            )
            for model, source_type, direction in note_specs:
                for note in model.objects.filter(company=company, status=model.Status.COMPLETED):
                    try:
                        if not _has_je(company, source_type, note.id, "COMPLETE"):
                            if PostingService.post_note(
                                note, source_type=source_type, direction=direction
                            ):
                                posted += 1
                    except BusinessRuleError as exc:
                        skipped += 1
                        self.stderr.write(f"{source_type} {note.id}: {exc}")

            for sales_return in SalesReturn.objects.filter(
                company=company, status=SalesReturn.Status.COMPLETED
            ):
                try:
                    if _has_je(company, "SALES_RETURN", sales_return.id, "COGS_REVERSE"):
                        continue
                    cogs = _movement_cogs(
                        company, MovementType.SALES_RETURN, "sales_return", sales_return.id
                    )
                    if not cogs:
                        invoice = sales_return.sales_invoice
                        if invoice is not None:
                            cogs = _movement_cogs(
                                company, MovementType.SALE, "sales_invoice", invoice.id
                            )
                            if invoice.items.exists() and sales_return.items.exists():
                                inv_qty = sum(
                                    (Decimal(str(i.quantity or 0)) for i in invoice.items.all()),
                                    Decimal("0"),
                                )
                                ret_qty = sum(
                                    (
                                        Decimal(str(i.quantity or 0))
                                        for i in sales_return.items.all()
                                    ),
                                    Decimal("0"),
                                )
                                if inv_qty:
                                    cogs = (cogs * ret_qty / inv_qty).quantize(Decimal("0.01"))
                    if cogs:
                        PostingService.post_sales_return_cogs(sales_return, cogs)
                        posted += 1
                except BusinessRuleError as exc:
                    skipped += 1
                    self.stderr.write(f"SalesReturn {sales_return.id}: {exc}")

            for movement in StockMovement.objects.filter(
                company=company, movement_type=MovementType.OPENING_STOCK
            ):
                try:
                    if not _has_je(company, "STOCK_MOVEMENT", movement.id, "OPENING_STOCK"):
                        if PostingService.post_opening_stock(movement):
                            posted += 1
                except BusinessRuleError as exc:
                    skipped += 1
                    self.stderr.write(f"Opening stock {movement.id}: {exc}")

            tagged = self._retag_party_lines(company)
            self.stdout.write(f"Company {company.id}: party tags updated on {tagged} lines.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill completed; evaluated {posted} documents ({skipped} skipped)."
            )
        )

    @staticmethod
    def _retag_party_lines(company) -> int:
        tagged = 0
        source_loaders = {
            "SALES_INVOICE": (
                lambda pk: SalesInvoice.objects.filter(pk=pk).first(),
                "customer_id",
                "1200",
                "customer_id",
            ),
            "PURCHASE_INVOICE": (
                lambda pk: PurchaseInvoice.objects.filter(pk=pk).first(),
                "supplier_id",
                "2100",
                "supplier_id",
            ),
            "CUSTOMER_RECEIPT": (
                lambda pk: CustomerReceipt.objects.filter(pk=pk).first(),
                "customer_id",
                "2300",
                "customer_id",
            ),
            "SUPPLIER_PAYMENT": (
                lambda pk: SupplierPayment.objects.filter(pk=pk).first(),
                "supplier_id",
                "1250",
                "supplier_id",
            ),
            "SALES_CREDIT_NOTE": (
                lambda pk: SalesCreditNote.objects.filter(pk=pk).first(),
                "customer_id",
                "1200",
                "customer_id",
            ),
            "SALES_DEBIT_NOTE": (
                lambda pk: SalesDebitNote.objects.filter(pk=pk).first(),
                "customer_id",
                "1200",
                "customer_id",
            ),
            "PURCHASE_CREDIT_NOTE": (
                lambda pk: PurchaseCreditNote.objects.filter(pk=pk).first(),
                "supplier_id",
                "2100",
                "supplier_id",
            ),
            "PURCHASE_DEBIT_NOTE": (
                lambda pk: PurchaseDebitNote.objects.filter(pk=pk).first(),
                "supplier_id",
                "2100",
                "supplier_id",
            ),
        }
        for entry in JournalEntry.objects.filter(
            company=company, status=JournalEntry.Status.POSTED, source_id__isnull=False
        ):
            spec = source_loaders.get(entry.source_type)
            if spec is None:
                if entry.source_type == "PAYMENT_ALLOCATION":
                    alloc = PaymentAllocation.objects.filter(pk=entry.source_id).select_related(
                        "receipt", "supplier_payment"
                    ).first()
                    if alloc is None:
                        continue
                    if alloc.receipt_id:
                        tagged += JournalLine.objects.filter(
                            entry=entry, customer__isnull=True, account__code__in=("1200", "2300")
                        ).update(customer_id=alloc.receipt.customer_id)
                    elif alloc.supplier_payment_id:
                        tagged += JournalLine.objects.filter(
                            entry=entry, supplier__isnull=True, account__code__in=("2100", "1250")
                        ).update(supplier_id=alloc.supplier_payment.supplier_id)
                continue
            loader, party_attr, account_code, line_field = spec
            doc = loader(entry.source_id)
            if doc is None:
                continue
            party_id = getattr(doc, party_attr, None)
            if not party_id:
                continue
            qs = JournalLine.objects.filter(entry=entry, account__code=account_code)
            if line_field == "customer_id":
                tagged += qs.filter(customer__isnull=True).update(customer_id=party_id)
            else:
                tagged += qs.filter(supplier__isnull=True).update(supplier_id=party_id)
        return tagged
