"""
Ledger Service (E5.1 / Wave 16B) — customer/supplier outstanding + statements.

When ``company.accounting_enabled`` is True (GL-first path): party balances are
derived from posted ``JournalLine`` rows on control/advance accounts
(1200/2100/2300/1250) tagged with customer/supplier FKs.

When accounting is off: documents + allocations remain the source of truth
(legacy document-derived path). Books 10/10 requires accounting_enabled.
"""

from decimal import Decimal

from django.db.models import Prefetch, Sum

from payments.models import CustomerReceipt, PaymentAllocation, ReceiptStatus, SupplierPayment
from purchases.models import (
    PurchaseCreditNote,
    PurchaseDebitNote,
    PurchaseInvoice,
    PurchaseReturn,
)
from sales.models import (
    SalesCreditNote,
    SalesDebitNote,
    SalesInvoice,
    SalesReturn,
)


# UXW2B-005: map JournalEntry.source_type -> the model whose .number is the
# customer/supplier-facing document number, so GL-derived ledger statements can
# show "INV-..."/"PUR-..." instead of the internal "JV-..." journal-voucher number.
_SOURCE_NUMBER_MODELS = {
    "SALES_INVOICE": SalesInvoice,
    "SALES_CREDIT_NOTE": SalesCreditNote,
    "SALES_DEBIT_NOTE": SalesDebitNote,
    "SALES_RETURN": SalesReturn,
    "CUSTOMER_RECEIPT": CustomerReceipt,
    "PURCHASE_INVOICE": PurchaseInvoice,
    "PURCHASE_CREDIT_NOTE": PurchaseCreditNote,
    "PURCHASE_DEBIT_NOTE": PurchaseDebitNote,
    "PURCHASE_RETURN": PurchaseReturn,
    "SUPPLIER_PAYMENT": SupplierPayment,
}


def _resolve_source_number(source_type: str, source_id: int | None) -> str | None:
    """Best-effort lookup of the source document's own number for a JournalEntry.

    Returns None (caller falls back to the JV number) for source types with no
    customer-facing document (manual journals, FY close, payment allocations, …)
    or if the referenced row was since deleted.
    """
    model = _SOURCE_NUMBER_MODELS.get(source_type)
    if model is None or source_id is None:
        return None
    return model.objects.filter(pk=source_id).values_list("number", flat=True).first()


def _prefetched_alloc_total(parent, related_name="allocations") -> Decimal:
    """Sum allocation amounts from a Prefetch cache (avoids N+1)."""
    cached = getattr(parent, "_prefetched_objects_cache", {}).get(related_name)
    if cached is not None:
        return sum((a.amount for a in cached), Decimal("0"))
    return _sum(getattr(parent, related_name).all())


_ALLOC_PREFETCH = Prefetch(
    "allocations",
    queryset=PaymentAllocation.objects.only("id", "amount", "receipt_id", "supplier_payment_id"),
)

OPEN_SALES_STATUSES = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)


def _sum(qs, field="amount") -> Decimal:
    return qs.aggregate(total=Sum(field))["total"] or Decimal("0")


class LedgerService:
    # ---------------- Per-invoice open outstanding ----------------

    @staticmethod
    def sales_invoice_outstanding(invoice: SalesInvoice) -> Decimal:
        """grand_total − CNs + DNs − allocations (Wave 3: returns relieve AR via auto CN)."""
        if invoice.status not in OPEN_SALES_STATUSES:
            return Decimal("0")
        credit_notes = _sum(
            SalesCreditNote.objects.filter(
                sales_invoice=invoice, status=SalesCreditNote.Status.COMPLETED
            ),
            "grand_total",
        )
        debit_notes = _sum(
            SalesDebitNote.objects.filter(
                sales_invoice=invoice, status=SalesDebitNote.Status.COMPLETED
            ),
            "grand_total",
        )
        allocated = _sum(PaymentAllocation.objects.filter(sales_invoice=invoice, reversed_at__isnull=True))
        tcs = Decimal(str(getattr(invoice, "tcs_amount", 0) or 0))
        # BB-000097/288: never report negative open receivable.
        return max(Decimal("0"), invoice.grand_total + tcs - credit_notes + debit_notes - allocated)

    @staticmethod
    def purchase_invoice_outstanding(invoice: PurchaseInvoice) -> Decimal:
        if invoice.status not in (
            PurchaseInvoice.Status.COMPLETED,
            PurchaseInvoice.Status.RETURNED,
        ):
            return Decimal("0")
        returns = _sum(
            PurchaseReturn.objects.filter(
                purchase_invoice=invoice, status=PurchaseReturn.Status.COMPLETED
            ),
            "grand_total",
        )
        credit_notes = _sum(
            PurchaseCreditNote.objects.filter(
                purchase_invoice=invoice, status=PurchaseCreditNote.Status.COMPLETED
            ),
            "grand_total",
        )
        debit_notes = _sum(
            PurchaseDebitNote.objects.filter(
                purchase_invoice=invoice, status=PurchaseDebitNote.Status.COMPLETED
            ),
            "grand_total",
        )
        allocated = _sum(PaymentAllocation.objects.filter(purchase_invoice=invoice, reversed_at__isnull=True))
        # BB-000281: when auto CNs exist for returns, do not also subtract return totals.
        auto_cn_return_ids = set(
            PurchaseCreditNote.objects.filter(
                purchase_invoice=invoice,
                status=PurchaseCreditNote.Status.COMPLETED,
                purchase_return__isnull=False,
            ).values_list("purchase_return_id", flat=True)
        )
        if auto_cn_return_ids:
            linked_returns = _sum(
                PurchaseReturn.objects.filter(
                    pk__in=auto_cn_return_ids, status=PurchaseReturn.Status.COMPLETED
                ),
                "grand_total",
            )
            returns = max(Decimal("0"), returns - linked_returns)
        tds = Decimal(str(getattr(invoice, "tds_amount", 0) or 0))
        # BB-000097/288: never report negative open payable. Net payable = grand − TDS.
        return max(Decimal("0"), invoice.grand_total - tds - returns - credit_notes + debit_notes - allocated)

    # ---------------- Advances / credit-limit exposure ----------------

    @staticmethod
    def _party_account_net(company, *, account_code: str, customer=None, supplier=None) -> Decimal:
        """Net debit−credit on posted journal lines for a party-tagged control account."""
        from accounting.models import JournalEntry, JournalLine

        qs = JournalLine.objects.filter(
            company=company,
            account__code=account_code,
            entry__status=JournalEntry.Status.POSTED,
        )
        if customer is not None:
            qs = qs.filter(customer=customer)
        if supplier is not None:
            qs = qs.filter(supplier=supplier)
        agg = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
        return (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))

    @staticmethod
    def customer_unallocated_receipts(company, customer) -> Decimal:
        if getattr(company, "accounting_enabled", False):
            # Advances liability 2300: credit increases advance; net credit = unallocated.
            net = LedgerService._party_account_net(company, account_code="2300", customer=customer)
            return max(Decimal("0"), -net)
        total = Decimal("0")
        receipts = CustomerReceipt.objects.filter(
            company=company, customer=customer, status=ReceiptStatus.POSTED
        ).prefetch_related(_ALLOC_PREFETCH)
        for receipt in receipts:
            allocated = _prefetched_alloc_total(receipt)
            total += max(Decimal("0"), receipt.amount - allocated)
        return total

    @staticmethod
    def customer_exposure_for_credit_limit(company, customer) -> Decimal:
        """Outstanding reduced by unallocated advances (Phase 1 D7 / §3.2)."""
        return LedgerService.customer_outstanding(company, customer) - LedgerService.customer_unallocated_receipts(
            company, customer
        )

    # ---------------- Customer ledger ----------------

    @staticmethod
    def customer_outstanding(company, customer) -> Decimal:
        if getattr(company, "accounting_enabled", False):
            # AR asset 1200: debit increases receivable.
            return max(Decimal("0"), LedgerService._party_account_net(
                company, account_code="1200", customer=customer
            ))
        # Wave 3: sales returns restore stock only; AR relief is via auto credit notes.
        invoices = _sum(
            SalesInvoice.objects.filter(
                company=company, customer=customer, status__in=OPEN_SALES_STATUSES
            ),
            "grand_total",
        ) + _sum(
            SalesInvoice.objects.filter(
                company=company, customer=customer, status__in=OPEN_SALES_STATUSES
            ),
            "tcs_amount",
        )
        credit_notes = _sum(
            SalesCreditNote.objects.filter(
                company=company, customer=customer, status=SalesCreditNote.Status.COMPLETED
            ),
            "grand_total",
        )
        debit_notes = _sum(
            SalesDebitNote.objects.filter(
                company=company, customer=customer, status=SalesDebitNote.Status.COMPLETED
            ),
            "grand_total",
        )
        allocated = _sum(
            PaymentAllocation.objects.filter(
                company=company,
                sales_invoice__customer=customer,
                receipt__isnull=False,
                reversed_at__isnull=True,
            )
        )
        # BB-000097/288: floor at zero (over-allocation / note edge cases).
        return max(Decimal("0"), invoices - credit_notes + debit_notes - allocated)

    @staticmethod
    def bulk_customer_outstanding(company) -> dict:
        if getattr(company, "accounting_enabled", False):
            from accounting.models import JournalEntry, JournalLine

            rows = (
                JournalLine.objects.filter(
                    company=company,
                    account__code="1200",
                    entry__status=JournalEntry.Status.POSTED,
                    customer_id__isnull=False,
                )
                .values("customer_id")
                .annotate(d=Sum("debit"), c=Sum("credit"))
            )
            return {
                row["customer_id"]: max(
                    Decimal("0"),
                    (row["d"] or Decimal("0")) - (row["c"] or Decimal("0")),
                )
                for row in rows
            }
        invoices = dict(
            SalesInvoice.objects.filter(company=company, status__in=OPEN_SALES_STATUSES)
            .values("customer_id")
            .annotate(total=Sum("grand_total") + Sum("tcs_amount"))
            .values_list("customer_id", "total")
        )
        credit_notes = dict(
            SalesCreditNote.objects.filter(company=company, status=SalesCreditNote.Status.COMPLETED)
            .values("customer_id")
            .annotate(total=Sum("grand_total"))
            .values_list("customer_id", "total")
        )
        debit_notes = dict(
            SalesDebitNote.objects.filter(company=company, status=SalesDebitNote.Status.COMPLETED)
            .values("customer_id")
            .annotate(total=Sum("grand_total"))
            .values_list("customer_id", "total")
        )
        allocated = dict(
            PaymentAllocation.objects.filter(
                company=company, receipt__isnull=False, reversed_at__isnull=True
            )
            .values("sales_invoice__customer_id")
            .annotate(total=Sum("amount"))
            .values_list("sales_invoice__customer_id", "total")
        )
        customer_ids = set(invoices) | set(credit_notes) | set(debit_notes) | set(allocated)
        return {
            cid: max(
                Decimal("0"),
                (invoices.get(cid) or Decimal("0"))
                - (credit_notes.get(cid) or Decimal("0"))
                + (debit_notes.get(cid) or Decimal("0"))
                - (allocated.get(cid) or Decimal("0")),
            )
            for cid in customer_ids
        }

    @staticmethod
    def company_receivables(company) -> Decimal:
        """Company-wide AR — single source for dashboards (GAP-002)."""
        return sum(LedgerService.bulk_customer_outstanding(company).values(), Decimal("0"))

    @staticmethod
    def company_payables(company) -> Decimal:
        """Company-wide AP — single source for dashboards (GAP-002)."""
        return sum(LedgerService.bulk_supplier_outstanding(company).values(), Decimal("0"))

    @staticmethod
    def customer_statement(company, customer, date_from=None, date_to=None):
        """Running-balance statement — GL-first when accounting_enabled."""
        if getattr(company, "accounting_enabled", False):
            return LedgerService._gl_party_statement(
                company,
                account_code="1200",
                customer=customer,
                date_from=date_from,
                date_to=date_to,
                debit_positive=True,
            )
        entries = []
        for inv in SalesInvoice.objects.filter(
            company=company, customer=customer, status__in=OPEN_SALES_STATUSES
        ).select_related("customer"):
            entries.append({
                "date": inv.invoice_date,
                "type": "SALES_INVOICE",
                "number": inv.number,
                "reference_id": inv.pk,
                "debit": inv.grand_total,
                "credit": Decimal("0"),
            })
        # Sales returns are stock-only for AR; credit notes carry the value relief.
        for cn in SalesCreditNote.objects.filter(
            company=company, customer=customer, status=SalesCreditNote.Status.COMPLETED
        ).select_related("customer", "sales_invoice"):
            entries.append({
                "date": cn.note_date,
                "type": "SALES_CREDIT_NOTE",
                "number": cn.number,
                "reference_id": cn.pk,
                "debit": Decimal("0"),
                "credit": cn.grand_total,
            })
        for dn in SalesDebitNote.objects.filter(
            company=company, customer=customer, status=SalesDebitNote.Status.COMPLETED
        ).select_related("customer", "sales_invoice"):
            entries.append({
                "date": dn.note_date,
                "type": "SALES_DEBIT_NOTE",
                "number": dn.number,
                "reference_id": dn.pk,
                "debit": dn.grand_total,
                "credit": Decimal("0"),
            })
        for receipt in CustomerReceipt.objects.filter(
            company=company, customer=customer, status=ReceiptStatus.POSTED
        ).select_related("customer").prefetch_related(_ALLOC_PREFETCH):
            allocated = _prefetched_alloc_total(receipt)
            unallocated = receipt.amount - allocated
            entries.append({
                "date": receipt.receipt_date,
                "type": "RECEIPT",
                "number": receipt.number,
                "reference_id": receipt.pk,
                "debit": Decimal("0"),
                "credit": receipt.amount,
                "is_advance": unallocated > 0,
                "unallocated": unallocated,
            })

        entries.sort(key=lambda e: (e["date"], e["reference_id"]))
        # BB-000098/289: opening from pre-range activity, then filter the window.
        opening = Decimal("0")
        if date_from:
            for e in entries:
                if e["date"] < date_from:
                    opening += e["debit"] - e["credit"]
            entries = [e for e in entries if e["date"] >= date_from]
        if date_to:
            entries = [e for e in entries if e["date"] <= date_to]

        balance = opening
        for entry in entries:
            balance += entry["debit"] - entry["credit"]
            entry["balance"] = balance
        return entries

    @staticmethod
    def _gl_party_statement(
        company,
        *,
        account_code: str,
        customer=None,
        supplier=None,
        date_from=None,
        date_to=None,
        debit_positive: bool = True,
    ):
        """Build statement lines from posted JournalLine rows tagged to party."""
        from accounting.models import JournalEntry, JournalLine

        qs = JournalLine.objects.filter(
            entry__company=company,
            entry__status=JournalEntry.Status.POSTED,
            account__code=account_code,
        ).select_related("entry", "account")
        if customer is not None:
            qs = qs.filter(customer=customer)
        if supplier is not None:
            qs = qs.filter(supplier=supplier)
        lines = list(qs.order_by("entry__entry_date", "id"))
        entries = []
        for line in lines:
            d = Decimal(str(line.debit or 0))
            c = Decimal(str(line.credit or 0))
            source_type = line.entry.source_type or "JOURNAL"
            # UXW2B-005: show the source invoice/bill/receipt number a shopkeeper
            # actually recognizes; fall back to the internal JV number only when
            # there's no customer-facing document (manual journals, FY close, …).
            doc_number = _resolve_source_number(source_type, line.entry.source_id)
            entries.append({
                "date": line.entry.entry_date,
                "type": source_type,
                "number": doc_number or line.entry.number or "",
                "jv_number": line.entry.number or "",
                "reference_id": line.entry_id,
                "debit": d,
                "credit": c,
                "source": "gl",
            })
        opening = Decimal("0")
        if date_from:
            for e in entries:
                if e["date"] < date_from:
                    if debit_positive:
                        opening += e["debit"] - e["credit"]
                    else:
                        opening += e["credit"] - e["debit"]
            entries = [e for e in entries if e["date"] >= date_from]
        if date_to:
            entries = [e for e in entries if e["date"] <= date_to]
        balance = opening
        for entry in entries:
            if debit_positive:
                balance += entry["debit"] - entry["credit"]
            else:
                balance += entry["credit"] - entry["debit"]
            entry["balance"] = balance
        return entries

    # ---------------- Supplier ledger ----------------

    @staticmethod
    def _auto_cn_linked_return_ids(company, supplier=None) -> set:
        """BB-000323: return ids already relieved by an auto (return-linked) credit
        note. Mirrors purchase_invoice_outstanding's BB-000281 handling so
        supplier-level views never double-count the same return via both the
        PurchaseReturn total and its auto-generated PurchaseCreditNote."""
        qs = PurchaseCreditNote.objects.filter(
            company=company,
            status=PurchaseCreditNote.Status.COMPLETED,
            purchase_return__isnull=False,
        )
        if supplier is not None:
            qs = qs.filter(supplier=supplier)
        return set(qs.values_list("purchase_return_id", flat=True))

    @staticmethod
    def supplier_outstanding(company, supplier) -> Decimal:
        if getattr(company, "accounting_enabled", False):
            # AP liability 2100: credit increases payable → outstanding = −net (debit−credit).
            net = LedgerService._party_account_net(company, account_code="2100", supplier=supplier)
            return max(Decimal("0"), -net)
        inv_qs = PurchaseInvoice.objects.filter(
            company=company,
            supplier=supplier,
            status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
        )
        invoices = _sum(inv_qs, "grand_total") - _sum(inv_qs, "tds_amount")
        # BB-000323: exclude returns already relieved via an auto CN to avoid
        # double-counting (once as a return, once as the linked credit note).
        auto_cn_return_ids = LedgerService._auto_cn_linked_return_ids(company, supplier)
        returns = _sum(
            PurchaseReturn.objects.filter(
                company=company, supplier=supplier, status=PurchaseReturn.Status.COMPLETED
            ).exclude(pk__in=auto_cn_return_ids),
            "grand_total",
        )
        credit_notes = _sum(
            PurchaseCreditNote.objects.filter(
                company=company, supplier=supplier, status=PurchaseCreditNote.Status.COMPLETED
            ),
            "grand_total",
        )
        debit_notes = _sum(
            PurchaseDebitNote.objects.filter(
                company=company, supplier=supplier, status=PurchaseDebitNote.Status.COMPLETED
            ),
            "grand_total",
        )
        allocated = _sum(
            PaymentAllocation.objects.filter(
                company=company,
                purchase_invoice__supplier=supplier,
                supplier_payment__isnull=False,
                reversed_at__isnull=True,
            )
        )
        # BB-000097/288: floor at zero (over-allocation / note edge cases).
        return max(Decimal("0"), invoices - returns - credit_notes + debit_notes - allocated)

    @staticmethod
    def bulk_supplier_outstanding(company) -> dict:
        if getattr(company, "accounting_enabled", False):
            from accounting.models import JournalEntry, JournalLine

            rows = (
                JournalLine.objects.filter(
                    company=company,
                    account__code="2100",
                    entry__status=JournalEntry.Status.POSTED,
                    supplier_id__isnull=False,
                )
                .values("supplier_id")
                .annotate(d=Sum("debit"), c=Sum("credit"))
            )
            return {
                row["supplier_id"]: max(
                    Decimal("0"),
                    (row["c"] or Decimal("0")) - (row["d"] or Decimal("0")),
                )
                for row in rows
            }
        invoices = dict(
            PurchaseInvoice.objects.filter(
                company=company,
                status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
            )
            .values("supplier_id")
            .annotate(total=Sum("grand_total") - Sum("tds_amount"))
            .values_list("supplier_id", "total")
        )
        # BB-000323: exclude returns already relieved via an auto CN (see
        # supplier_outstanding) so bulk supplier balances match per-supplier ones.
        auto_cn_return_ids = LedgerService._auto_cn_linked_return_ids(company)
        returns = dict(
            PurchaseReturn.objects.filter(company=company, status=PurchaseReturn.Status.COMPLETED)
            .exclude(pk__in=auto_cn_return_ids)
            .values("supplier_id")
            .annotate(total=Sum("grand_total"))
            .values_list("supplier_id", "total")
        )
        credit_notes = dict(
            PurchaseCreditNote.objects.filter(
                company=company, status=PurchaseCreditNote.Status.COMPLETED
            )
            .values("supplier_id")
            .annotate(total=Sum("grand_total"))
            .values_list("supplier_id", "total")
        )
        debit_notes = dict(
            PurchaseDebitNote.objects.filter(
                company=company, status=PurchaseDebitNote.Status.COMPLETED
            )
            .values("supplier_id")
            .annotate(total=Sum("grand_total"))
            .values_list("supplier_id", "total")
        )
        allocated = dict(
            PaymentAllocation.objects.filter(
                company=company, supplier_payment__isnull=False, reversed_at__isnull=True
            )
            .values("purchase_invoice__supplier_id")
            .annotate(total=Sum("amount"))
            .values_list("purchase_invoice__supplier_id", "total")
        )
        supplier_ids = set(invoices) | set(returns) | set(credit_notes) | set(debit_notes) | set(allocated)
        return {
            sid: max(
                Decimal("0"),
                (invoices.get(sid) or Decimal("0"))
                - (returns.get(sid) or Decimal("0"))
                - (credit_notes.get(sid) or Decimal("0"))
                + (debit_notes.get(sid) or Decimal("0"))
                - (allocated.get(sid) or Decimal("0")),
            )
            for sid in supplier_ids
        }

    @staticmethod
    def supplier_statement(company, supplier, date_from=None, date_to=None):
        if getattr(company, "accounting_enabled", False):
            return LedgerService._gl_party_statement(
                company,
                account_code="2100",
                supplier=supplier,
                date_from=date_from,
                date_to=date_to,
                debit_positive=False,
            )
        entries = []
        for inv in PurchaseInvoice.objects.filter(
            company=company,
            supplier=supplier,
            status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
        ).select_related("supplier"):
            entries.append({
                "date": inv.invoice_date,
                "type": "PURCHASE_INVOICE",
                "number": inv.number,
                "reference_id": inv.pk,
                "credit": inv.grand_total,
                "debit": Decimal("0"),
            })
        # BB-000323: skip return rows already relieved via an auto CN so the
        # statement doesn't show the same value twice (return + linked CN).
        auto_cn_return_ids = LedgerService._auto_cn_linked_return_ids(company, supplier)
        for ret in PurchaseReturn.objects.filter(
            company=company, supplier=supplier, status=PurchaseReturn.Status.COMPLETED
        ).exclude(pk__in=auto_cn_return_ids).select_related("supplier", "purchase_invoice"):
            entries.append({
                "date": ret.return_date,
                "type": "PURCHASE_RETURN",
                "number": ret.number,
                "reference_id": ret.pk,
                "credit": Decimal("0"),
                "debit": ret.grand_total,
            })
        for cn in PurchaseCreditNote.objects.filter(
            company=company, supplier=supplier, status=PurchaseCreditNote.Status.COMPLETED
        ).select_related("supplier", "purchase_invoice", "purchase_return"):
            entries.append({
                "date": cn.note_date,
                "type": "PURCHASE_CREDIT_NOTE",
                "number": cn.number,
                "reference_id": cn.pk,
                "credit": Decimal("0"),
                "debit": cn.grand_total,
            })
        for dn in PurchaseDebitNote.objects.filter(
            company=company, supplier=supplier, status=PurchaseDebitNote.Status.COMPLETED
        ).select_related("supplier", "purchase_invoice"):
            entries.append({
                "date": dn.note_date,
                "type": "PURCHASE_DEBIT_NOTE",
                "number": dn.number,
                "reference_id": dn.pk,
                "credit": dn.grand_total,
                "debit": Decimal("0"),
            })
        for payment in SupplierPayment.objects.filter(
            company=company, supplier=supplier
        ).select_related("supplier").prefetch_related(_ALLOC_PREFETCH):
            allocated = _prefetched_alloc_total(payment)
            unallocated = payment.amount - allocated
            entries.append({
                "date": payment.payment_date,
                "type": "PAYMENT",
                "number": payment.number,
                "reference_id": payment.pk,
                "credit": Decimal("0"),
                "debit": payment.amount,
                "is_advance": unallocated > 0,
                "unallocated": unallocated,
            })

        entries.sort(key=lambda e: (e["date"], e["reference_id"]))
        # BB-000098/289: opening from pre-range activity, then filter the window.
        opening = Decimal("0")
        if date_from:
            for e in entries:
                if e["date"] < date_from:
                    opening += e["credit"] - e["debit"]
            entries = [e for e in entries if e["date"] >= date_from]
        if date_to:
            entries = [e for e in entries if e["date"] <= date_to]

        balance = opening
        for entry in entries:
            balance += entry["credit"] - entry["debit"]
            entry["balance"] = balance
        return entries
