"""
Ledger Service (E5.1 / Wave 16B) — customer/supplier outstanding + statements.

When ``company.accounting_enabled`` is True and outstanding_basis is
GL_WHEN_BOOKS (PD-02): party balances are GL 1200 net of 2300 (AR) and 2100
net of 1250 (AP). ``customer_statement`` foots the same number.

When accounting is off or outstanding_basis is DOCUMENTS_ALWAYS: documents +
allocations remain the source of truth.
"""

import logging
from decimal import Decimal

from django.db.models import Case, DecimalField, F, Prefetch, Sum, Value, When

_logger = logging.getLogger(__name__)


def _floor_outstanding(raw: Decimal, *, kind: str, ref) -> Decimal:
    """LED-03: outstanding figures are floored at 0 so an over-allocation /
    double-payment data bug doesn't render as a negative balance. Floor it for
    the caller, but surface the anomaly in the log instead of swallowing it
    entirely so it can be chased down.
    """
    if raw < Decimal("-0.01"):
        _logger.warning(
            "Negative %s outstanding %.2f for %s — floored to 0. Likely "
            "over-allocation or a double payment; reconcile the sub-ledger.",
            kind,
            raw,
            ref,
        )
    return raw if raw > 0 else Decimal("0")

from payments.models import (
    CustomerReceipt,
    PaymentAllocation,
    ReceiptStatus,
    SupplierPayment,
    SupplierPaymentStatus,
)
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


def _resolve_source_numbers(pairs) -> dict:
    """R2-019: batch-resolve {(source_type, source_id): number} in one query
    per model instead of one query per statement line (N+1)."""
    by_type: dict[str, set] = {}
    for source_type, source_id in pairs:
        if source_id is None or source_type not in _SOURCE_NUMBER_MODELS:
            continue
        by_type.setdefault(source_type, set()).add(source_id)
    out: dict = {}
    for source_type, ids in by_type.items():
        model = _SOURCE_NUMBER_MODELS[source_type]
        for pk, number in model.objects.filter(pk__in=ids).values_list("pk", "number"):
            out[(source_type, pk)] = number
    return out


def _prefetched_alloc_total(parent, related_name="allocations") -> Decimal:
    """Sum allocation amounts from a Prefetch cache (avoids N+1)."""
    cached = getattr(parent, "_prefetched_objects_cache", {}).get(related_name)
    if cached is not None:
        return sum((a.amount for a in cached), Decimal("0"))
    return _sum(getattr(parent, related_name).all())


_ALLOC_PREFETCH = Prefetch(
    "allocations",
    queryset=PaymentAllocation.objects.filter(reversed_at__isnull=True).only(
        "id", "amount", "receipt_id", "supplier_payment_id"
    ),
)

OPEN_SALES_STATUSES = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)

# Same-date statement ordering: charges (invoices / debit notes) before value
# relief (returns / credit notes) before settlement (receipts / payments), then
# by id. reference_id alone is a per-table pk and diverges between Postgres and
# SQLite sequences, so it is not a stable cross-type tiebreak on its own
# (test_customer_statement_running_balance).
_STMT_TYPE_ORDER = {
    "SALES_INVOICE": 0, "SALES_DEBIT_NOTE": 0,
    "SALES_CREDIT_NOTE": 1,
    "RECEIPT": 2,
    "PURCHASE_INVOICE": 0, "PURCHASE_DEBIT_NOTE": 0,
    "PURCHASE_RETURN": 1, "PURCHASE_CREDIT_NOTE": 1,
    "PAYMENT": 2,
}


def _stmt_sort_key(e):
    return (e["date"], _STMT_TYPE_ORDER.get(e["type"], 9), e["reference_id"])


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
        tcs = Decimal("0")
        if not getattr(invoice, "tcs_in_grand_total", False):
            tcs = Decimal(str(getattr(invoice, "tcs_amount", 0) or 0))
        # BB-000097/288: never report negative open receivable (LED-03: but log it).
        raw = invoice.grand_total + tcs - credit_notes + debit_notes - allocated
        return _floor_outstanding(raw, kind="sales invoice", ref=getattr(invoice, "number", invoice.pk))

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
        return_rows = list(
            PurchaseReturn.objects.filter(
                purchase_invoice=invoice, status=PurchaseReturn.Status.COMPLETED
            ).values_list("pk", "grand_total")
        )
        cn_rows = list(
            PurchaseCreditNote.objects.filter(
                purchase_invoice=invoice, status=PurchaseCreditNote.Status.COMPLETED
            ).values_list("purchase_return_id", "grand_total")
        )
        linked_return_ids = {rid for rid, _ in cn_rows if rid is not None}
        # LED-02: a legacy / auto CN that lost its purchase_return linkage would
        # otherwise let the return be subtracted twice (once as a return, once as
        # a CN) → supplier outstanding understated. Fall back to amount matching
        # for unlinked CNs so each physical return is relieved once.
        unlinked_cn_amounts = [amt for rid, amt in cn_rows if rid is None]
        for pk, ret_total in return_rows:
            if pk in linked_return_ids:
                continue
            match = next(
                (a for a in unlinked_cn_amounts if abs(a - ret_total) <= Decimal("0.05")),
                None,
            )
            if match is not None:
                unlinked_cn_amounts.remove(match)
                linked_return_ids.add(pk)
        if linked_return_ids:
            linked_returns = sum(
                (t for pk, t in return_rows if pk in linked_return_ids), Decimal("0")
            )
            returns = max(Decimal("0"), returns - linked_returns)
        tds = Decimal(str(getattr(invoice, "tds_amount", 0) or 0))
        # BB-000097/288: never report negative open payable. Net payable = grand − TDS.
        raw = invoice.grand_total - tds - returns - credit_notes + debit_notes - allocated
        return _floor_outstanding(raw, kind="purchase invoice", ref=getattr(invoice, "number", invoice.pk))

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
    def _use_gl_outstanding(company) -> bool:
        """PD-02: GL 1200 net 2300 when books on, unless outstanding_basis=DOCUMENTS_ALWAYS."""
        if not getattr(company, "accounting_enabled", False):
            return False
        basis = getattr(company, "outstanding_basis", "GL_WHEN_BOOKS") or "GL_WHEN_BOOKS"
        return basis != "DOCUMENTS_ALWAYS"

    @staticmethod
    def customer_exposure_for_credit_limit(company, customer) -> Decimal:
        """Outstanding reduced by unallocated advances (Phase 1 D7 / §3.2).

        When PD-02 GL outstanding is on, advances are already netted — do not
        subtract them a second time.

        LED-01: a credit-limit decision must not ride on a GL figure that has
        drifted from the sub-ledger. When the GL basis is in force, cross-check
        against the document basis and take the *more conservative* (higher)
        number for the limit check, logging the drift so it can be reconciled.
        """
        if LedgerService._use_gl_outstanding(company):
            gl_outstanding = LedgerService.customer_outstanding(company, customer)
            doc_outstanding = LedgerService._customer_outstanding_documents(company, customer)
            if abs(gl_outstanding - doc_outstanding) > Decimal("1"):
                _logger.warning(
                    "Customer %s credit exposure: GL %.2f vs documents %.2f — "
                    "using the higher for the limit check; reconcile 1200/2300.",
                    getattr(customer, "pk", customer),
                    gl_outstanding,
                    doc_outstanding,
                )
            return max(gl_outstanding, doc_outstanding)
        outstanding = LedgerService.customer_outstanding(company, customer)
        return outstanding - LedgerService.customer_unallocated_receipts(company, customer)

    # ---------------- Customer ledger ----------------

    @staticmethod
    def customer_outstanding(company, customer) -> Decimal:
        """Party AR that every money surface must foot.

        PD-02 / W0-07a:
        - books on + GL_WHEN_BOOKS: GL AR 1200 debit-positive net of advances 2300
          (same number as customer_statement closing).
        - books off or DOCUMENTS_ALWAYS: invoices − allocations − completed CNs + DNs.
        """
        if LedgerService._use_gl_outstanding(company):
            ar = LedgerService._party_account_net(
                company, account_code="1200", customer=customer
            )
            advances = LedgerService._party_account_net(
                company, account_code="2300", customer=customer
            )
            return max(Decimal("0"), ar + advances)
        return LedgerService._customer_outstanding_documents(company, customer)

    @staticmethod
    def _customer_outstanding_documents(company, customer) -> Decimal:
        """Document-basis customer AR: invoices − allocations − completed CNs + DNs.
        Used directly when books are off, and as the LED-01 cross-check for the
        GL basis."""
        # Wave 3: sales returns restore stock only; AR relief is via auto credit notes.
        invoices = _sum(
            SalesInvoice.objects.filter(
                company=company, customer=customer, status__in=OPEN_SALES_STATUSES
            ),
            "grand_total",
        ) + _sum(
            SalesInvoice.objects.filter(
                company=company,
                customer=customer,
                status__in=OPEN_SALES_STATUSES,
                tcs_in_grand_total=False,
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
                supplier_payment__isnull=True,  # R2-020: AR side only
                reversed_at__isnull=True,
            )
        )
        # BB-000097/288: floor at zero (over-allocation / note edge cases).
        raw = invoices - credit_notes + debit_notes - allocated
        return _floor_outstanding(raw, kind="customer", ref=getattr(customer, "pk", customer))

    @staticmethod
    def bulk_customer_outstanding(company) -> dict:
        if LedgerService._use_gl_outstanding(company):
            from accounting.models import JournalEntry, JournalLine
            from collections import defaultdict

            nets: dict = defaultdict(lambda: Decimal("0"))
            rows = (
                JournalLine.objects.filter(
                    company=company,
                    account__code__in=("1200", "2300"),
                    entry__status=JournalEntry.Status.POSTED,
                    customer_id__isnull=False,
                )
                .values("customer_id")
                .annotate(d=Sum("debit"), c=Sum("credit"))
            )
            for row in rows:
                nets[row["customer_id"]] += (row["d"] or Decimal("0")) - (row["c"] or Decimal("0"))
            return {k: max(Decimal("0"), v) for k, v in nets.items()}
        invoices = dict(
            SalesInvoice.objects.filter(company=company, status__in=OPEN_SALES_STATUSES)
            .values("customer_id")
            .annotate(
                total=Sum("grand_total")
                + Sum(
                    Case(
                        When(tcs_in_grand_total=True, then=Value(Decimal("0"))),
                        default=F("tcs_amount"),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                )
            )
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
                company=company,
                receipt__isnull=False,
                supplier_payment__isnull=True,  # R2-020
                reversed_at__isnull=True,
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
        """Company-wide AR for dashboards (GAP-002). R2-018: this sums the
        per-party figures which are each floored at 0, so it will read HIGHER
        than the 1200 control-account balance whenever a customer is in credit.
        For GL reconciliation use BooksHealthService.control_balances()['ar']."""
        return sum(LedgerService.bulk_customer_outstanding(company).values(), Decimal("0"))

    @staticmethod
    def company_payables(company) -> Decimal:
        """Company-wide AP for dashboards (GAP-002). R2-018: see
        company_receivables — floored per-party; reconcile via control_balances()."""
        return sum(LedgerService.bulk_supplier_outstanding(company).values(), Decimal("0"))

    @staticmethod
    def customer_statement(company, customer, date_from=None, date_to=None):
        """Running-balance statement — foots customer_outstanding (PD-02)."""
        if LedgerService._use_gl_outstanding(company):
            return LedgerService._gl_party_statement(
                company,
                account_codes=["1200", "2300"],
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
                "debit": inv.grand_total
                + (
                    Decimal("0")
                    if getattr(inv, "tcs_in_grand_total", False)
                    else Decimal(str(getattr(inv, "tcs_amount", 0) or 0))
                ),
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

        entries.sort(key=_stmt_sort_key)
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
        account_code: str | None = None,
        account_codes: list[str] | None = None,
        customer=None,
        supplier=None,
        date_from=None,
        date_to=None,
        debit_positive: bool = True,
    ):
        """Build statement lines from posted JournalLine rows tagged to party."""
        from accounting.models import JournalEntry, JournalLine

        codes = list(account_codes) if account_codes else [account_code] if account_code else []
        qs = JournalLine.objects.filter(
            entry__company=company,
            entry__status=JournalEntry.Status.POSTED,
            account__code__in=codes,
        ).select_related("entry", "account")
        if customer is not None:
            qs = qs.filter(customer=customer)
        if supplier is not None:
            qs = qs.filter(supplier=supplier)
        lines = list(qs.order_by("entry__entry_date", "id"))
        # R2-019: resolve every source document number up front (one query per
        # model) instead of one query per statement line.
        source_numbers = _resolve_source_numbers(
            (line.entry.source_type or "JOURNAL", line.entry.source_id) for line in lines
        )
        entries = []
        for line in lines:
            d = Decimal(str(line.debit or 0))
            c = Decimal(str(line.credit or 0))
            source_type = line.entry.source_type or "JOURNAL"
            # UXW2B-005: show the source invoice/bill/receipt number a shopkeeper
            # actually recognizes; fall back to the internal JV number only when
            # there's no customer-facing document (manual journals, FY close, …).
            doc_number = source_numbers.get((source_type, line.entry.source_id))
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
        if LedgerService._use_gl_outstanding(company):
            # AP 2100 (credit increases payable) net of supplier advances 1250.
            ap = LedgerService._party_account_net(company, account_code="2100", supplier=supplier)
            prepaid = LedgerService._party_account_net(
                company, account_code="1250", supplier=supplier
            )
            return max(Decimal("0"), -(ap + prepaid))
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
                receipt__isnull=True,  # R2-020: AP side only
                reversed_at__isnull=True,
            )
        )
        # BB-000097/288: floor at zero (over-allocation / note edge cases).
        raw = invoices - returns - credit_notes + debit_notes - allocated
        return _floor_outstanding(raw, kind="supplier", ref=getattr(supplier, "pk", supplier))

    @staticmethod
    def bulk_supplier_outstanding(company) -> dict:
        if LedgerService._use_gl_outstanding(company):
            from accounting.models import JournalEntry, JournalLine
            from collections import defaultdict

            nets: dict = defaultdict(lambda: Decimal("0"))
            rows = (
                JournalLine.objects.filter(
                    company=company,
                    account__code__in=("2100", "1250"),
                    entry__status=JournalEntry.Status.POSTED,
                    supplier_id__isnull=False,
                )
                .values("supplier_id")
                .annotate(d=Sum("debit"), c=Sum("credit"))
            )
            for row in rows:
                nets[row["supplier_id"]] += (row["d"] or Decimal("0")) - (row["c"] or Decimal("0"))
            return {sid: max(Decimal("0"), -net) for sid, net in nets.items()}
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
                company=company,
                supplier_payment__isnull=False,
                receipt__isnull=True,  # R2-020
                reversed_at__isnull=True,
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
        if LedgerService._use_gl_outstanding(company):
            return LedgerService._gl_party_statement(
                company,
                account_codes=["2100", "1250"],
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
            tds = Decimal(str(getattr(inv, "tds_amount", 0) or 0))
            net_credit = max(Decimal("0"), inv.grand_total - tds)
            entries.append({
                "date": inv.invoice_date,
                "type": "PURCHASE_INVOICE",
                "number": inv.number,
                "reference_id": inv.pk,
                "credit": net_credit,
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
            company=company, supplier=supplier, status=SupplierPaymentStatus.POSTED
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

        entries.sort(key=_stmt_sort_key)
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
