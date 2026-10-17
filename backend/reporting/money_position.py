"""Money hub: where the business stands on money in and money out, right now.

Read-only. Every figure is a call to the service that already owns it, so the hub cannot
drift from the screen it links to:

* receivable / payable   LedgerService.company_receivables / company_payables (party basis,
                         GL when the company is configured that way, documents otherwise)
* cash and bank          ReportService.cash_totals (cleared money only; the cash book's rule)
* advances received      LedgerService.bulk_customer_advances
* advances paid          LedgerService.supplier_advances_total
* cheques                CustomerReceipt / SupplierPayment ``cheque_status``
* bills, due dates       open sales / purchase invoices, one due-date rule (core.services.due_dates)

A section that fails is named in ``partial`` and returned as ``None``; it never reads as zero.
"""

from __future__ import annotations

import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from core.services.due_dates import effective_due_date

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
DUE_SOON_DAYS = 7
BOUNCED_WINDOW_DAYS = 30
STALE_CHEQUE_DAYS = 3
TDS_CERTIFICATE_CHASE_DAYS = 30
ACTIONS_PER_KIND = 5
TIMELINE_MAX_DAYS = 90

# Same cut-offs as ReportService.receivables_aging / payables_aging.
AGEING_BUCKETS = ("current", "days_1_30", "days_31_60", "days_61_90", "days_90_plus")


def _link(route: str, **params) -> dict:
    """Where a row opens. ``query`` is a ready query string: the API renderer camel-cases dict keys,
    which would turn ``cheque_status`` into ``chequeStatus``, so the filter names travel as text."""
    return {"route": route, "query": urlencode(params)}


def _q(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "days_1_30"
    if days_overdue <= 60:
        return "days_31_60"
    if days_overdue <= 90:
        return "days_61_90"
    return "days_90_plus"


# ---------------------------------------------------------------------------
# Open bills: one list feeds the totals, the ageing, the timeline and the action list
# ---------------------------------------------------------------------------


def open_sales_rows(company, as_of: date | None = None) -> list[dict]:
    """Open customer bills with a balance, each with its due date."""
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice
    from sales.status_semantics import OPEN_SALES_STATUSES

    as_of = as_of or timezone.localdate()
    invoices = list(
        SalesInvoice.objects.filter(company=company, status__in=OPEN_SALES_STATUSES)
        .select_related("customer")
        .only(
            "id", "number", "invoice_date", "due_date", "payment_terms_days", "customer_id",
            "customer__name",
        )
    )
    if not invoices:
        return []
    owed = LedgerService.bulk_sales_invoice_outstanding(company, [i.id for i in invoices])
    rows = []
    for invoice in invoices:
        outstanding = owed.get(invoice.id) or ZERO
        if outstanding <= 0:
            continue
        due = effective_due_date(invoice)
        rows.append({
            "id": invoice.id,
            "number": invoice.number,
            "party_id": invoice.customer_id,
            "party_name": invoice.customer.name,
            "due": due,
            "days_overdue": max((as_of - due).days, 0) if due else 0,
            "outstanding": outstanding,
        })
    return rows


def open_purchase_rows(company, as_of: date | None = None) -> list[dict]:
    """Open supplier bills with a balance, each with its due date."""
    from ledgers.services import LedgerService
    from purchases.models import PurchaseInvoice
    from purchases.status_semantics import OPEN_PAYABLE_STATUSES

    as_of = as_of or timezone.localdate()
    invoices = list(
        PurchaseInvoice.objects.filter(company=company, status__in=OPEN_PAYABLE_STATUSES)
        .select_related("supplier")
        .only(
            "id", "number", "supplier_bill_number", "invoice_date", "due_date",
            "payment_terms_days", "supplier_id", "supplier__name",
        )
    )
    if not invoices:
        return []
    owed = LedgerService.bulk_purchase_invoice_outstanding(company, [i.id for i in invoices])
    rows = []
    for invoice in invoices:
        outstanding = owed.get(invoice.id) or ZERO
        if outstanding <= 0:
            continue
        due = effective_due_date(invoice)
        rows.append({
            "id": invoice.id,
            "number": invoice.number or invoice.supplier_bill_number,
            "party_id": invoice.supplier_id,
            "party_name": invoice.supplier.name,
            "due": due,
            "days_overdue": max((as_of - due).days, 0) if due else 0,
            "outstanding": outstanding,
        })
    return rows


def _summarise_bills(rows: list[dict], headline: Decimal, as_of: date) -> dict:
    """Totals, due-soon and ageing for one side. ``headline`` is the party-basis total."""
    ageing = {key: ZERO for key in AGEING_BUCKETS}
    overdue = ZERO
    due_soon = ZERO
    overdue_count = 0
    due_soon_count = 0
    on_bills = ZERO
    soon_limit = as_of + timedelta(days=DUE_SOON_DAYS)
    for row in rows:
        owed = row["outstanding"]
        on_bills += owed
        ageing[_bucket(row["days_overdue"])] += owed
        if row["days_overdue"] > 0:
            overdue += owed
            overdue_count += 1
        elif row["due"] is not None and as_of <= row["due"] <= soon_limit:
            due_soon += owed
            due_soon_count += 1
    return {
        "outstanding": _q(headline),
        "bills": {"count": len(rows), "amount": _q(on_bills)},
        # What the party total holds that is not on an open bill: opening balances, unapplied
        # adjustments, or the GL/document difference. Shown so the ageing foots to the total.
        "not_on_a_bill": _q(headline - on_bills),
        "overdue": {"count": overdue_count, "amount": _q(overdue)},
        "due_soon": {"count": due_soon_count, "amount": _q(due_soon)},
        "ageing": {key: _q(value) for key, value in ageing.items()},
    }


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _basis(company) -> str:
    from ledgers.services import LedgerService

    return "GL" if LedgerService._use_gl_outstanding(company) else "DOCUMENTS"


def _cash(company) -> dict:
    from payments.models import BankAccount, ChequeStatus, PaymentMode, SupplierPayment, SupplierPaymentStatus
    from reporting.services import ReportService

    totals = ReportService.cash_totals(company)
    accounts = []
    for account in BankAccount.objects.filter(company=company, is_active=True).order_by("-is_default", "name"):
        closing = ReportService.cash_totals(company, bank_account_id=account.id)["closing"]
        accounts.append({"id": account.id, "name": account.name, "balance": _q(closing)})
    issued = SupplierPayment.objects.filter(
        company=company,
        status=SupplierPaymentStatus.POSTED,
        mode=PaymentMode.CHEQUE,
        cheque_status=ChequeStatus.PENDING_CLEARANCE,
    ).aggregate(n=Count("id"), t=Sum("amount"))
    return {
        "cleared": _q(totals["closing"]),
        "by_account": accounts,
        "inflow_mtd": _q(ReportService.cash_totals(company, date_from=timezone.localdate().replace(day=1))["inflow"]),
        "cheques_issued_pending": {"count": issued["n"] or 0, "amount": _q(issued["t"])},
    }


def _cheques_received_pending(company) -> dict:
    from payments.models import ChequeStatus, CustomerReceipt, PaymentMode, ReceiptStatus

    agg = CustomerReceipt.objects.filter(
        company=company,
        status=ReceiptStatus.POSTED,
        mode=PaymentMode.CHEQUE,
        cheque_status=ChequeStatus.PENDING_CLEARANCE,
    ).aggregate(n=Count("id"), t=Sum("amount"))
    return {"count": agg["n"] or 0, "amount": _q(agg["t"])}


def _cheques_bounced_recent(company, as_of: date) -> dict:
    """Cheques that came back in the last 30 days. The bill is open again; no money was received."""
    from payments.models import ChequeStatus, CustomerReceipt, ReceiptStatus

    since = timezone.make_aware(
        timezone.datetime.combine(as_of - timedelta(days=BOUNCED_WINDOW_DAYS), timezone.datetime.min.time())
    )
    agg = CustomerReceipt.objects.filter(
        company=company,
        status=ReceiptStatus.VOIDED,
        cheque_status=ChequeStatus.BOUNCED,
        updated_at__gte=since,
    ).aggregate(n=Count("id"), t=Sum("amount"))
    return {"count": agg["n"] or 0, "amount": _q(agg["t"]), "window_days": BOUNCED_WINDOW_DAYS}


def _advances_received(company) -> dict:
    from ledgers.services import LedgerService

    by_customer = LedgerService.bulk_customer_advances(company)
    positive = [value for value in by_customer.values() if value > 0]
    return {"count": len(positive), "amount": _q(sum(positive, ZERO))}


def _advances_paid(company) -> dict:
    from ledgers.services import LedgerService

    by_supplier = LedgerService.supplier_advances_by_supplier(company)
    return {"count": len(by_supplier), "amount": _q(sum(by_supplier.values(), ZERO))}


def tds_awaiting_certificate_qs(company):
    from payments.models import CustomerReceipt, ReceiptStatus

    return CustomerReceipt.objects.filter(
        company=company,
        status=ReceiptStatus.POSTED,
        tds_deducted__gt=0,
        tds_certificate_received_on__isnull=True,
    )


def _tds_receivable(company, as_of: date) -> dict:
    qs = tds_awaiting_certificate_qs(company)
    agg = qs.aggregate(n=Count("id"), t=Sum("tds_deducted"))
    stale = qs.filter(receipt_date__lte=as_of - timedelta(days=TDS_CERTIFICATE_CHASE_DAYS)).count()
    return {"count": agg["n"] or 0, "amount": _q(agg["t"]), "older_than_30_days": stale}


def _promises(company, as_of: date) -> dict:
    from payments.models import PaymentPromise
    from payments.promise_to_pay import promise_is_broken

    open_qs = PaymentPromise.objects.filter(company=company, resolved=False)
    soon = open_qs.filter(
        promised_date__gte=as_of, promised_date__lte=as_of + timedelta(days=DUE_SOON_DAYS)
    ).aggregate(n=Count("id"), t=Sum("promised_amount"))
    broken_count = 0
    broken_amount = ZERO
    for promise in open_qs.filter(promised_date__lt=as_of, promised_amount__isnull=False):
        if promise_is_broken(promise, as_of=as_of):
            broken_count += 1
            broken_amount += promise.promised_amount
    return {
        "due": {"count": soon["n"] or 0, "amount": _q(soon["t"])},
        "broken": {"count": broken_count, "amount": _q(broken_amount)},
    }


def _unmatched_bank(company) -> dict:
    from payments.models import BankLineMatchStatus, BankStatementLine, BankStatementStatus

    # Same lines as the reconciliation queue: a suggestion is not a match until a person accepts it.
    lines = BankStatementLine.objects.filter(
        company=company,
        match_status__in=(BankLineMatchStatus.UNMATCHED, BankLineMatchStatus.SUGGESTED),
        statement__status=BankStatementStatus.COMMITTED,
    )
    credits = lines.filter(amount__gt=0).aggregate(n=Count("id"), t=Sum("amount"))
    debits = lines.filter(amount__lt=0).aggregate(n=Count("id"), t=Sum("amount"))
    return {
        "credits": {"count": credits["n"] or 0, "amount": _q(credits["t"])},
        "debits": {"count": debits["n"] or 0, "amount": _q(abs(debits["t"] or ZERO))},
    }


def _gateway_and_links(company) -> dict:
    from payments.models import GatewayPayment, GatewayPaymentStatus, PaymentLink, PaymentLinkStatus

    # Same rule as the attention feed: paid at the gateway, no receipt in the books yet.
    held = GatewayPayment.objects.filter(
        company=company,
        status__in=(GatewayPaymentStatus.CAPTURED, GatewayPaymentStatus.CAPTURED_PENDING_BOOKS),
        receipts__isnull=True,
    ).aggregate(n=Count("id", distinct=True), t=Sum("amount"))
    now = timezone.now()
    links = PaymentLink.objects.filter(
        company=company,
        status__in=(PaymentLinkStatus.CREATED, PaymentLinkStatus.SENT, PaymentLinkStatus.PARTIALLY_PAID),
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).aggregate(n=Count("id"), t=Sum("amount"))
    return {
        "gateway_awaiting_books": {"count": held["n"] or 0, "amount": _q(held["t"])},
        "payment_links_open": {"count": links["n"] or 0, "amount": _q(links["t"])},
    }


# ---------------------------------------------------------------------------
# Needs action
# ---------------------------------------------------------------------------


def _actions(company, as_of: date, sales_rows: list[dict], purchase_rows: list[dict]) -> list[dict]:
    from payments.models import (
        ChequeStatus, CustomerReceipt, PaymentMode, PaymentPromise, ReceiptStatus,
        SupplierPayment, SupplierPaymentStatus,
    )
    from payments.promise_to_pay import promise_is_broken

    out: list[dict] = []

    for row in sorted((r for r in sales_rows if r["days_overdue"] > 0), key=lambda r: -r["outstanding"])[:ACTIONS_PER_KIND]:
        out.append({
            "kind": "chase_customer", "party_id": row["party_id"], "party_name": row["party_name"],
            "reference": row["number"], "amount": _q(row["outstanding"]), "days": row["days_overdue"],
            "link": _link("/payments/collections", customer=row["party_id"]),
        })
    for row in sorted((r for r in purchase_rows if r["days_overdue"] > 0), key=lambda r: -r["outstanding"])[:ACTIONS_PER_KIND]:
        out.append({
            "kind": "pay_supplier", "party_id": row["party_id"], "party_name": row["party_name"],
            "reference": row["number"], "amount": _q(row["outstanding"]), "days": row["days_overdue"],
            "link": _link("/purchases/history", overdue=1, supplier=row["party_id"]),
        })

    broken = []
    for promise in PaymentPromise.objects.filter(
        company=company, resolved=False, promised_date__lt=as_of, promised_amount__isnull=False
    ).select_related("customer").order_by("promised_date", "id"):
        if promise_is_broken(promise, as_of=as_of):
            broken.append(promise)
        if len(broken) >= ACTIONS_PER_KIND:
            break
    for promise in broken:
        out.append({
            "kind": "broken_promise", "party_id": promise.customer_id, "party_name": promise.customer.name,
            "reference": "", "amount": _q(promise.promised_amount),
            "days": (as_of - promise.promised_date).days,
            "link": _link("/payments/collections", promises="broken", customer=promise.customer_id),
        })

    stale_before = as_of - timedelta(days=STALE_CHEQUE_DAYS)
    for receipt in CustomerReceipt.objects.filter(
        company=company, status=ReceiptStatus.POSTED, mode=PaymentMode.CHEQUE,
        cheque_status=ChequeStatus.PENDING_CLEARANCE, receipt_date__lte=stale_before,
    ).select_related("customer").order_by("receipt_date", "id")[:ACTIONS_PER_KIND]:
        out.append({
            "kind": "clear_cheque_in", "party_id": receipt.customer_id, "party_name": receipt.customer.name,
            "reference": receipt.number, "amount": _q(receipt.amount), "days": (as_of - receipt.receipt_date).days,
            "link": _link("/sales/receipts", q=receipt.number),
        })
    for payment in SupplierPayment.objects.filter(
        company=company, status=SupplierPaymentStatus.POSTED, mode=PaymentMode.CHEQUE,
        cheque_status=ChequeStatus.PENDING_CLEARANCE, payment_date__lte=stale_before,
    ).select_related("supplier").order_by("payment_date", "id")[:ACTIONS_PER_KIND]:
        out.append({
            "kind": "clear_cheque_out", "party_id": payment.supplier_id, "party_name": payment.supplier.name,
            "reference": payment.number, "amount": _q(payment.amount), "days": (as_of - payment.payment_date).days,
            "link": _link("/purchases/payments", cheque_status=ChequeStatus.PENDING_CLEARANCE, supplier=payment.supplier_id),
        })
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class _Sections:
    """Runs each section in its own savepoint; a failure is recorded, not raised."""

    def __init__(self):
        self.partial: list[str] = []

    def run(self, name: str, fn):
        try:
            with transaction.atomic():
                return fn()
        except Exception:  # noqa: BLE001 - one broken tile must not blank the whole hub
            logger.exception("money hub section %s failed", name)
            self.partial.append(name)
            return None


def build_position(company, as_of: date | None = None) -> dict:
    from ledgers.services import LedgerService

    as_of = as_of or timezone.localdate()
    sections = _Sections()
    run = sections.run

    basis = run("basis", lambda: _basis(company))
    receivable = run("receivable", lambda: LedgerService.company_receivables(company))
    payable = run("payable", lambda: LedgerService.company_payables(company))
    sales_rows = run("receivable_bills", lambda: open_sales_rows(company, as_of))
    purchase_rows = run("payable_bills", lambda: open_purchase_rows(company, as_of))
    cash = run("cash", lambda: _cash(company))

    net = None
    if receivable is not None and payable is not None:
        net = {"receivable": _q(receivable), "payable": _q(payable), "net": _q(receivable - payable)}

    money_in = {
        "bills": run("money_in_bills", lambda: _summarise_bills(sales_rows, receivable, as_of))
        if sales_rows is not None and receivable is not None else None,
        "advances": run("advances_received", lambda: _advances_received(company)),
        "cheques_pending": run("cheques_pending", lambda: _cheques_received_pending(company)),
        "cheques_bounced": run("cheques_bounced", lambda: _cheques_bounced_recent(company, as_of)),
        "tds_receivable": run("tds_receivable", lambda: _tds_receivable(company, as_of)),
        "promises": run("promises", lambda: _promises(company, as_of)),
    }
    money_out = {
        "bills": run("money_out_bills", lambda: _summarise_bills(purchase_rows, payable, as_of))
        if purchase_rows is not None and payable is not None else None,
        "advances_paid": run("advances_paid", lambda: _advances_paid(company)),
        "cheques_issued_pending": cash["cheques_issued_pending"] if cash else None,
    }
    bank = run("unmatched_bank", lambda: _unmatched_bank(company))
    gateway = run("gateway", lambda: _gateway_and_links(company))
    money_in["unmatched_bank_credits"] = bank["credits"] if bank else None
    money_in["gateway_awaiting_books"] = gateway["gateway_awaiting_books"] if gateway else None
    money_in["payment_links_open"] = gateway["payment_links_open"] if gateway else None
    money_out["unmatched_bank_debits"] = bank["debits"] if bank else None

    advances_amount = (money_in["advances"] or {}).get("amount", ZERO)
    reconciliation = run(
        "reconciliation", lambda: _reconciliation(company, receivable, payable, basis, advances_amount)
    )
    actions = run("actions", lambda: _actions(company, as_of, sales_rows or [], purchase_rows or []))

    return {
        "as_of": as_of.isoformat(),
        "basis": {"receivable": basis, "payable": basis},
        "net": net,
        "cash": {k: v for k, v in (cash or {}).items() if k != "cheques_issued_pending"} if cash else None,
        "money_in": money_in,
        "money_out": money_out,
        "reconciliation": reconciliation,
        "actions": actions,
        "partial": sections.partial,
    }


def _reconciliation(company, receivable, payable, basis, advances_received) -> dict | None:
    """The headline next to the ledger control accounts, when books are on.

    On the GL basis the party receivable is the 1200 control balance less customer advances
    (2300), so that is what it is compared with; on documents it is compared with 1200 itself.
    """
    if not getattr(company, "accounting_enabled", False):
        return {"available": False, "reason": "books_off"}
    from accounting.services import BooksHealthService

    control = BooksHealthService.control_balances(company)
    # control_balances() -> {"ar": {"gl": ..., "ledger": ..., "healthy": ...}, "ap": {...}, ...}
    gl_ar = Decimal(str((control.get("ar") or {}).get("gl") or 0))
    gl_ap = Decimal(str((control.get("ap") or {}).get("gl") or 0))
    expected_ar = gl_ar - (advances_received if basis == "GL" else ZERO)
    return {
        "available": True,
        "basis": basis,
        "gl_receivable": _q(gl_ar),
        "gl_payable": _q(gl_ap),
        "advances_received": _q(advances_received),
        "difference_receivable": _q((receivable or ZERO) - expected_ar),
        "difference_payable": _q((payable or ZERO) - gl_ap),
    }


# ---------------------------------------------------------------------------
# Phase B: what falls due next (by date, not a forecast)
# ---------------------------------------------------------------------------


def build_timeline(company, days: int = 30, as_of: date | None = None) -> dict:
    """Money expected in and due out over the next ``days`` days, by due date.

    Not a prediction: an invoice with an open promise to pay is placed on the promised date;
    everything else sits on its due date. Anything already past due is reported apart as
    "overdue now" and is not placed on a future day.
    """
    from payments.models import PaymentPromise
    from reporting.services import ReportService

    as_of = as_of or timezone.localdate()
    days = max(1, min(int(days), TIMELINE_MAX_DAYS))
    horizon = as_of + timedelta(days=days)

    sales_rows = open_sales_rows(company, as_of)
    purchase_rows = open_purchase_rows(company, as_of)

    promised_on: dict[int, date] = {}
    for promise in PaymentPromise.objects.filter(
        company=company, resolved=False, invoice__isnull=False, promised_date__gte=as_of
    ).order_by("promised_date", "id"):
        promised_on.setdefault(promise.invoice_id, promise.promised_date)

    per_day: dict[date, dict] = defaultdict(lambda: {"in": ZERO, "out": ZERO, "items": []})
    overdue_in = ZERO
    overdue_out = ZERO
    beyond_in = ZERO
    beyond_out = ZERO
    for row in sales_rows:
        when = promised_on.get(row["id"]) or row["due"]
        if row["days_overdue"] > 0 and row["id"] not in promised_on:
            overdue_in += row["outstanding"]
        elif when is None or when > horizon:
            beyond_in += row["outstanding"]
        else:
            day = max(when, as_of)
            per_day[day]["in"] += row["outstanding"]
            per_day[day]["items"].append({
                "side": "in", "party": row["party_name"], "reference": row["number"],
                "amount": _q(row["outstanding"]), "promised": row["id"] in promised_on,
            })
    for row in purchase_rows:
        when = row["due"]
        if row["days_overdue"] > 0:
            overdue_out += row["outstanding"]
        elif when is None or when > horizon:
            beyond_out += row["outstanding"]
        else:
            per_day[when]["out"] += row["outstanding"]
            per_day[when]["items"].append({
                "side": "out", "party": row["party_name"], "reference": row["number"],
                "amount": _q(row["outstanding"]), "promised": False,
            })

    statutory = build_statutory(company, as_of)
    for due in statutory["items"]:
        due_on = date.fromisoformat(due["due_date"])
        if due["amount"] is not None and Decimal(due["amount"]) > 0 and as_of <= due_on <= horizon:
            per_day[due_on]["out"] += Decimal(due["amount"])
            per_day[due_on]["items"].append({
                "side": "out", "party": due["label"], "reference": due["period"],
                "amount": _q(due["amount"]), "promised": False, "estimate": True,
            })

    opening = ReportService.cash_totals(company)["closing"]
    running = opening
    timeline = []
    for day in sorted(per_day):
        entry = per_day[day]
        running = running + entry["in"] - entry["out"]
        timeline.append({
            "date": day.isoformat(),
            "inflow": _q(entry["in"]),
            "outflow": _q(entry["out"]),
            "balance": _q(running),
            "items": sorted(entry["items"], key=lambda i: -i["amount"]),
        })
    total_in = sum((e["in"] for e in per_day.values()), ZERO)
    total_out = sum((e["out"] for e in per_day.values()), ZERO)
    return {
        "as_of": as_of.isoformat(),
        "days": days,
        "basis": "DUE_DATE",
        "note": "By due date, not a forecast. A bill with an open promise to pay sits on the promised date.",
        "opening_cash": _q(opening),
        "inflow": _q(total_in),
        "outflow": _q(total_out),
        "closing_cash": _q(opening + total_in - total_out),
        "overdue_now": {"in": _q(overdue_in), "out": _q(overdue_out)},
        "beyond_horizon": {"in": _q(beyond_in), "out": _q(beyond_out)},
        "lowest_balance": _q(min((e["balance"] for e in timeline), default=opening)),
        "timeline": timeline,
    }


# ---------------------------------------------------------------------------
# Phase B: tax dues (estimates, for the CA to confirm)
# ---------------------------------------------------------------------------


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _previous_month(day: date) -> date:
    first = day.replace(day=1)
    return first - timedelta(days=1)


def _due_in_next_month(period_day: date, due_day: int) -> date:
    year, month = (period_day.year + 1, 1) if period_day.month == 12 else (period_day.year, period_day.month + 1)
    return date(year, month, min(due_day, monthrange(year, month)[1]))


def build_statutory(company, as_of: date | None = None) -> dict:
    """TDS deducted on supplier bills and the GST estimate, for the last month and this one.

    The books do not record that a tax payment was made, so these are amounts deducted or
    estimated and their due dates, not "unpaid" balances. Wording is for CA review.
    """
    from reporting.tds_worksheets import tds_worksheet_rows

    as_of = as_of or timezone.localdate()
    items: list[dict] = []
    unavailable: list[str] = []

    for period_day in (_previous_month(as_of), as_of.replace(day=1)):
        period = _month_key(period_day)
        try:
            rows = tds_worksheet_rows(company, period)
            tds_total = sum((Decimal(r["tds_amount"]) for r in rows), ZERO)
        except Exception:  # noqa: BLE001
            logger.exception("money hub: TDS worksheet failed for %s", period)
            unavailable.append(f"tds:{period}")
            continue
        items.append({
            "kind": "tds_payable", "label": "TDS deducted on supplier bills", "period": period,
            "amount": str(_q(tds_total)), "due_date": _due_in_next_month(period_day, 7).isoformat(),
            "estimate": False, "link": _link("/reports/tds-tcs", period=period),
        })

    if company.is_gst_registered:
        last = _previous_month(as_of)
        period = _month_key(last)
        try:
            from reporting.gst_returns import build_gstr3b

            summary = build_gstr3b(company, period).get("tax_payable_summary") or {}
            hint = summary.get("net_payable_hint")
            items.append({
                "kind": "gst_payable", "label": "GST for the month (estimate)", "period": period,
                "amount": str(_q(hint)) if hint is not None else None,
                "due_date": _due_in_next_month(last, 20).isoformat(),
                "estimate": True, "link": _link("/reports/gstr3b", period=period),
            })
        except Exception:  # noqa: BLE001 - composition dealers, missing GSTIN, no data
            logger.info("money hub: GST estimate unavailable for %s", period, exc_info=True)
            unavailable.append(f"gst:{period}")

    return {
        "as_of": as_of.isoformat(),
        "items": items,
        "unavailable": unavailable,
        "note": "Estimates from your books for the CA to confirm. Bizboard does not record that a tax payment was made.",
    }
