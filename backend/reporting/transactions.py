"""Shared sales-side transaction union used by Day Book and Customer Ledger."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Q

from payments.models import ChequeStatus, CustomerReceipt, PaymentMode, ReceiptStatus


def _d(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return None


def _money(value) -> Decimal:
    return Decimal(str(value or 0))


def _cheque_counts_as_cash(receipt) -> bool:
    if receipt.mode != PaymentMode.CHEQUE:
        return True
    return getattr(receipt, "cheque_status", "") == ChequeStatus.CLEARED


def sales_side_transactions(
    company,
    *,
    date_from=None,
    date_to=None,
    customer_id=None,
    txn_types=None,
    include_cash_position_only=False,
    status_filter=None,
):
    """Union of sales-side documents, newest-last after sort.

    When ``customer_id`` is set, purchase-side docs are never included.
    ``include_cash_position_only`` drops uncleared cheques and non-cash docs
    (quotations) so Day Book cash-position matches Phase 3 cheque rules.
    """
    from sales.models import (
        Quotation,
        SalesCreditNote,
        SalesDebitNote,
        SalesInvoice,
        SalesReturn,
    )

    wanted = {str(t).upper() for t in (txn_types or []) if t} or None
    rows: list[dict] = []

    def _keep(kind: str) -> bool:
        return wanted is None or kind in wanted

    if _keep("SALES"):
        qs = SalesInvoice.objects.filter(company=company).select_related("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        if include_cash_position_only:
            qs = qs.filter(status=SalesInvoice.Status.COMPLETED)
        for inv in qs.iterator(chunk_size=200):
            rows.append({
                "date": inv.invoice_date,
                "txn_type": "SALES",
                "number": inv.number,
                "amount": _money(inv.grand_total),
                "status": inv.status,
                "id": inv.id,
                "customer_id": inv.customer_id,
                "party": getattr(inv.customer, "name", ""),
                "payment_mode": "",
                "source_path": f"/sales/history/{inv.id}",
            })

    if _keep("PAYMENT_IN"):
        qs = CustomerReceipt.objects.filter(company=company).select_related("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if date_from:
            qs = qs.filter(receipt_date__gte=date_from)
        if date_to:
            qs = qs.filter(receipt_date__lte=date_to)
        if include_cash_position_only:
            qs = qs.filter(status=ReceiptStatus.POSTED)
        for rec in qs.iterator(chunk_size=200):
            if include_cash_position_only and not _cheque_counts_as_cash(rec):
                continue
            if include_cash_position_only and rec.mode == "CREDIT":
                continue
            rows.append({
                "date": rec.receipt_date,
                "txn_type": "PAYMENT_IN",
                "number": rec.number,
                "amount": _money(rec.amount),
                "status": rec.status,
                "id": rec.id,
                "customer_id": rec.customer_id,
                "party": getattr(rec.customer, "name", ""),
                "payment_mode": rec.mode,
                "cheque_status": getattr(rec, "cheque_status", "") or "",
                "source_path": "/sales/receipts",
            })

    if _keep("QUOTATION") and not include_cash_position_only:
        qs = Quotation.objects.filter(company=company).select_related("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if date_from:
            qs = qs.filter(quotation_date__gte=date_from)
        if date_to:
            qs = qs.filter(quotation_date__lte=date_to)
        for qtn in qs.iterator(chunk_size=200):
            rows.append({
                "date": qtn.quotation_date,
                "txn_type": "QUOTATION",
                "number": qtn.number,
                "amount": _money(qtn.grand_total),
                "status": qtn.status,
                "id": qtn.id,
                "customer_id": qtn.customer_id,
                "party": getattr(qtn.customer, "name", ""),
                "payment_mode": "",
                "source_path": f"/sales/quotations",
            })

    if _keep("SALES_RETURN"):
        qs = SalesReturn.objects.filter(company=company).select_related("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if date_from:
            qs = qs.filter(return_date__gte=date_from)
        if date_to:
            qs = qs.filter(return_date__lte=date_to)
        for ret in qs.iterator(chunk_size=200):
            rows.append({
                "date": ret.return_date,
                "txn_type": "SALES_RETURN",
                "number": ret.number,
                "amount": _money(ret.grand_total),
                "status": ret.status,
                "id": ret.id,
                "customer_id": ret.customer_id,
                "party": getattr(ret.customer, "name", ""),
                "payment_mode": "",
                "source_path": "/sales/returns",
            })

    if _keep("CREDIT_NOTE"):
        qs = SalesCreditNote.objects.filter(company=company).select_related("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if date_from:
            qs = qs.filter(note_date__gte=date_from)
        if date_to:
            qs = qs.filter(note_date__lte=date_to)
        for note in qs.iterator(chunk_size=200):
            rows.append({
                "date": note.note_date,
                "txn_type": "CREDIT_NOTE",
                "number": note.number,
                "amount": _money(note.grand_total),
                "status": note.status,
                "id": note.id,
                "customer_id": note.customer_id,
                "party": getattr(note.customer, "name", ""),
                "payment_mode": "",
                "source_path": "/sales/credit-notes",
            })

    if _keep("DEBIT_NOTE"):
        qs = SalesDebitNote.objects.filter(company=company).select_related("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if date_from:
            qs = qs.filter(note_date__gte=date_from)
        if date_to:
            qs = qs.filter(note_date__lte=date_to)
        for note in qs.iterator(chunk_size=200):
            rows.append({
                "date": note.note_date,
                "txn_type": "DEBIT_NOTE",
                "number": note.number,
                "amount": _money(note.grand_total),
                "status": note.status,
                "id": note.id,
                "customer_id": note.customer_id,
                "party": getattr(note.customer, "name", ""),
                "payment_mode": "",
                "source_path": "/sales/debit-notes",
            })

    if include_cash_position_only:
        from accounting.models import Expense
        from payments.models import SupplierPayment, SupplierPaymentStatus

        if _keep("EXPENSE"):
            qs = Expense.objects.filter(company=company).select_related("category")
            if date_from:
                qs = qs.filter(expense_date__gte=date_from)
            if date_to:
                qs = qs.filter(expense_date__lte=date_to)
            for exp in qs.iterator(chunk_size=200):
                rows.append({
                    "date": exp.expense_date,
                    "txn_type": "EXPENSE",
                    "number": exp.number,
                    "amount": _money(exp.amount),
                    "status": "POSTED",
                    "id": exp.id,
                    "customer_id": None,
                    "party": exp.party_name or getattr(exp.category, "name", ""),
                    "payment_mode": "",
                    "direction": "OUT",
                    "source_path": "/accounting/expenses",
                })
        if _keep("PAYMENT_OUT"):
            qs = SupplierPayment.objects.filter(
                company=company, status=SupplierPaymentStatus.POSTED,
            ).select_related("supplier")
            if date_from:
                qs = qs.filter(payment_date__gte=date_from)
            if date_to:
                qs = qs.filter(payment_date__lte=date_to)
            for pay in qs.iterator(chunk_size=200):
                if pay.mode == "CREDIT":
                    continue
                if pay.mode == PaymentMode.CHEQUE and getattr(pay, "cheque_status", "") != ChequeStatus.CLEARED:
                    continue
                rows.append({
                    "date": pay.payment_date,
                    "txn_type": "PAYMENT_OUT",
                    "number": pay.number,
                    "amount": _money(pay.amount),
                    "status": pay.status,
                    "id": pay.id,
                    "customer_id": None,
                    "party": getattr(pay.supplier, "name", ""),
                    "payment_mode": pay.mode,
                    "direction": "OUT",
                    "source_path": "/purchases/payments",
                })

    rows.sort(key=lambda r: (_d(r["date"]) or date.min, r["txn_type"], r["id"] or 0))
    _annotate_sales_payment_state(company, rows)
    wanted_status = (status_filter or "").upper()
    if wanted_status and wanted_status not in ("ALL",):
        rows = [r for r in rows if _ledger_row_matches_status(r, wanted_status)]
    return rows


def _annotate_sales_payment_state(company, rows) -> None:
    from datetime import timedelta

    from django.utils import timezone

    from ledgers.services import LedgerService
    from masters.models import Customer
    from sales.models import SalesInvoice

    sales_ids = [r["id"] for r in rows if r.get("txn_type") == "SALES" and r.get("id")]
    if not sales_ids:
        return
    balances = LedgerService.bulk_sales_invoice_outstanding(company, sales_ids)
    invoices = {
        inv.id: inv
        for inv in SalesInvoice.objects.filter(pk__in=sales_ids).only(
            "id", "due_date", "invoice_date", "payment_terms_days", "customer_id", "status",
        )
    }
    credit_days = dict(
        Customer.objects.filter(pk__in={inv.customer_id for inv in invoices.values()}).values_list(
            "id", "credit_days",
        )
    )
    today = timezone.localdate()
    for row in rows:
        if row.get("txn_type") != "SALES":
            continue
        inv = invoices.get(row["id"])
        bal = balances.get(row["id"]) or Decimal("0")
        grand = _money(row.get("amount"))
        if str(row.get("status") or "").upper() == "CANCELLED":
            row["payment_state"] = "CANCELLED"
            row["is_overdue"] = False
            continue
        if bal <= Decimal("0.05"):
            state = "PAID"
        elif bal + Decimal("0.05") >= grand:
            state = "UNPAID"
        else:
            state = "PARTIAL"
        row["payment_state"] = state
        due = None
        if inv is not None:
            due = inv.due_date
            if due is None:
                days = inv.payment_terms_days or credit_days.get(inv.customer_id) or 0
                due = inv.invoice_date + timedelta(days=int(days or 0))
        row["is_overdue"] = bool(due and due < today and state in ("UNPAID", "PARTIAL"))


def _ledger_row_matches_status(row, wanted: str) -> bool:
    wanted = (wanted or "").upper()
    if wanted == "CANCELLED":
        return str(row.get("status") or "").upper() in ("CANCELLED", "VOIDED")
    if wanted == "OVERDUE":
        return bool(row.get("is_overdue"))
    if wanted == "PAID":
        if row.get("txn_type") == "SALES":
            return row.get("payment_state") == "PAID"
        if row.get("txn_type") == "PAYMENT_IN":
            return str(row.get("status") or "").upper() == "POSTED"
        return False
    if wanted in ("UNPAID", "PARTIAL"):
        return row.get("payment_state") == wanted
    return (
        str(row.get("status") or "").upper() == wanted
        or str(row.get("payment_state") or "").upper() == wanted
    )


def customer_overdue_amount(company, customer, *, date_from=None, date_to=None) -> Decimal:
    from datetime import timedelta

    from django.utils import timezone

    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    qs = SalesInvoice.objects.filter(
        company=company, customer=customer, status=SalesInvoice.Status.COMPLETED,
    )
    if date_from:
        qs = qs.filter(invoice_date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice_date__lte=date_to)
    ids = list(qs.values_list("id", flat=True))
    if not ids:
        return Decimal("0")
    balances = LedgerService.bulk_sales_invoice_outstanding(company, ids)
    today = timezone.localdate()
    overdue = Decimal("0")
    credit_days = int(getattr(customer, "credit_days", 0) or 0)
    for inv in qs.only("id", "due_date", "invoice_date", "payment_terms_days"):
        bal = balances.get(inv.id) or Decimal("0")
        if bal <= Decimal("0.05"):
            continue
        due = inv.due_date
        if due is None:
            days = inv.payment_terms_days or credit_days
            due = inv.invoice_date + timedelta(days=int(days or 0))
        if due < today:
            overdue += bal
    return overdue


def day_book(company, on_date: date) -> dict:
    """Company-wide one-day cash-position book (CLEARED cheques only)."""
    rows = sales_side_transactions(
        company,
        date_from=on_date,
        date_to=on_date,
        include_cash_position_only=True,
        txn_types=["SALES", "PAYMENT_IN", "PAYMENT_OUT", "EXPENSE", "SALES_RETURN", "CREDIT_NOTE", "DEBIT_NOTE"],
    )
    inflow = Decimal("0")
    outflow = Decimal("0")
    out_rows = []
    for row in rows:
        kind = row["txn_type"]
        amount = _money(row["amount"])
        direction = row.get("direction")
        if kind in ("PAYMENT_IN",) or (kind == "SALES" and False):
            inflow += amount
            signed = amount
        elif kind in ("PAYMENT_OUT", "EXPENSE") or direction == "OUT":
            outflow += amount
            signed = -amount
        elif kind in ("SALES_RETURN", "CREDIT_NOTE"):
            outflow += amount
            signed = -amount
        else:
            signed = amount
        out_rows.append({**row, "inflow": amount if signed > 0 and kind == "PAYMENT_IN" else Decimal("0"),
                         "outflow": amount if signed < 0 else Decimal("0")})
    return {
        "date": on_date,
        "inflow": inflow,
        "outflow": outflow,
        "net": inflow - outflow,
        "rows": out_rows,
        "kind": "day_book",
        "label": "Day book",
        "disclaimer": (
            "Company-wide day book. Cheque receipts and payments count only when CLEARED. "
            "Sales invoices appear as documents; cash-position uses posted receipts/payments/expenses."
        ),
    }


def customer_item_wise(company, customer_id, *, date_from=None, date_to=None) -> list[dict]:
    from django.db.models import Sum

    from sales.models import SalesInvoice, SalesItem

    qs = SalesItem.objects.filter(
        invoice__company=company,
        invoice__customer_id=customer_id,
        invoice__status=SalesInvoice.Status.COMPLETED,
    )
    if date_from:
        qs = qs.filter(invoice__invoice_date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice__invoice_date__lte=date_to)
    grouped = (
        qs.values("product_id", "product__name", "product__sku")
        .annotate(sales_qty=Sum("quantity"), sales_amount=Sum("line_total"))
        .order_by("product__name")
    )
    return [
        {
            "product_id": row["product_id"],
            "product_name": row["product__name"],
            "sku": row["product__sku"] or "",
            "sales_qty": row["sales_qty"] or Decimal("0"),
            "sales_amount": row["sales_amount"] or Decimal("0"),
        }
        for row in grouped
    ]
