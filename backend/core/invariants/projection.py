"""Projection identities (Graph 3 / L10) — the same named metric is one number.

Empty company / no documents → []. Do not merge document identities into
``reports.cross_reconcile`` (that callable stays GL-report agreement only).
"""

from __future__ import annotations

from decimal import Decimal

from .base import invariant

_CENT = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value) -> Decimal:
    return Decimal(str(value or 0))


@invariant(
    "projection.ar_dashboard_equals_aging",
    consequence="Dashboard receivables KPI does not equal receivables aging total — Sethji is looking at two AR numbers.",
)
def ar_dashboard_equals_aging(company) -> list[str]:
    from reporting.services import ReportService

    dash = _q(ReportService._company_receivables(company))
    aging = _q(ReportService._aging_total(ReportService.receivables_aging(company)))
    if abs(dash - aging) > _CENT:
        return [f"dashboard AR {dash} != aging total {aging}"]
    return []


@invariant(
    "projection.ap_dashboard_equals_aging",
    consequence="Dashboard payables KPI does not equal payables aging total — AP after a purchase return/residual DN will lie.",
)
def ap_dashboard_equals_aging(company) -> list[str]:
    from reporting.services import ReportService

    dash = _q(ReportService._company_payables(company))
    aging = _q(ReportService._aging_total(ReportService.payables_aging(company)))
    if abs(dash - aging) > _CENT:
        return [f"dashboard AP {dash} != payables aging total {aging}"]
    return []


@invariant(
    "projection.open_invoice_outstanding_equals_aging",
    consequence="Sum of open-receivable invoice outstanding does not equal aging/dashboard AR — a returned invoice with residual balance is missing from one surface (G-17/G-20).",
)
def open_invoice_outstanding_equals_aging(company) -> list[str]:
    from ledgers.services import LedgerService
    from reporting.services import ReportService
    from sales.models import SalesInvoice
    from sales.status_semantics import OPEN_RECEIVABLE_STATUSES

    ids = list(
        SalesInvoice.objects.filter(company=company, status__in=OPEN_RECEIVABLE_STATUSES).values_list("pk", flat=True)[:2000]
    )
    if not ids:
        return []
    bulk = LedgerService.bulk_sales_invoice_outstanding(company, ids)
    summed = sum((_q(v) for v in bulk.values()), _ZERO)
    dash = _q(ReportService._company_receivables(company))
    if abs(summed - dash) > _CENT:
        return [f"Σ open-invoice outstanding {summed} != dashboard/aging AR {dash}"]
    return []


@invariant(
    "projection.stock_available_is_on_hand_minus_reserved",
    consequence="Available stock drifted from on_hand − reserved — POS and invoice availability will disagree with the stock screen.",
)
def stock_available_is_on_hand_minus_reserved(company) -> list[str]:
    from django.db.models import Sum

    from inventory.models import StockBalance
    from inventory.services import InventoryService
    from masters.models import Product

    out: list[str] = []
    rows = (
        StockBalance.objects.filter(company=company)
        .values("product_id")
        .annotate(on_hand=Sum("on_hand"), reserved=Sum("reserved"))
    )
    if not rows:
        return []
    for row in rows:
        expected = _q(row["on_hand"]) - _q(row["reserved"])
        product = Product.objects.filter(pk=row["product_id"]).first()
        if product is None:
            continue
        available = InventoryService.available_quantity(company, product)
        if abs(available - expected) > Decimal("0.001"):
            out.append(
                f"product#{row['product_id']}: available {available} != on_hand-reserved {expected}"
            )
    return out[:20]


@invariant(
    "projection.operational_sales_not_collapsed_into_open_receivables",
    consequence="OPERATIONAL_SALE_STATUSES collapsed into OPEN_RECEIVABLE_STATUSES — analytics would count reversed sales as standing revenue (G-17 class).",
)
def operational_sales_not_collapsed_into_open_receivables(company) -> list[str]:
    from purchases.status_semantics import OPEN_PAYABLE_STATUSES, OPERATIONAL_PURCHASE_STATUSES
    from sales.models import SalesInvoice
    from sales.status_semantics import OPEN_RECEIVABLE_STATUSES, OPERATIONAL_SALE_STATUSES

    out: list[str] = []
    if set(OPEN_RECEIVABLE_STATUSES) == set(OPERATIONAL_SALE_STATUSES):
        out.append("open-receivable and operational-sale status sets are identical")
    if SalesInvoice.Status.RETURNED not in OPEN_RECEIVABLE_STATUSES:
        out.append("RETURNED is missing from OPEN_RECEIVABLE_STATUSES")
    if SalesInvoice.Status.RETURNED in OPERATIONAL_SALE_STATUSES:
        out.append("RETURNED must not be an operational sale")
    if set(OPEN_PAYABLE_STATUSES) == set(OPERATIONAL_PURCHASE_STATUSES):
        out.append("open-payable and operational-purchase status sets are identical")
    return out


@invariant(
    "projection.pdf_snapshot_differs_from_live_outstanding_after_return",
    consequence="After a full return with no residual debit note, live outstanding still equals the invoice grand_total — PDF snapshot and /pay page would tell the same (wrong) story (B2/B3).",
)
def pdf_snapshot_differs_from_live_outstanding_after_return(company) -> list[str]:
    from ledgers.services import LedgerService
    from sales.models import SalesDebitNote, SalesInvoice

    out: list[str] = []
    returned = SalesInvoice.objects.filter(company=company, status=SalesInvoice.Status.RETURNED)
    if not returned.exists():
        return []
    for inv in returned.iterator():
        live = LedgerService.sales_invoice_outstanding(inv)
        grand = _q(inv.grand_total)
        if grand <= _ZERO:
            continue
        has_residual_dn = SalesDebitNote.objects.filter(
            company=company, sales_invoice=inv, status=SalesDebitNote.Status.COMPLETED
        ).exists()
        if has_residual_dn:
            continue
        if live == grand:
            out.append(
                f"invoice {inv.number or inv.pk}: live outstanding {live} still equals "
                f"PDF snapshot grand_total {grand} after return"
            )
    return out[:20]


@invariant(
    "projection.bank_recon_match_status_identity",
    consequence="GL bank recon matched a statement line without setting BankStatementLine.match_status=MATCHED — /payments/reconciliation and /accounting/bank-reconciliation disagree (B8).",
)
def bank_recon_match_status_identity(company) -> list[str]:
    from accounting.models import JournalLine
    from payments.models import BankLineMatchStatus

    out: list[str] = []
    qs = JournalLine.objects.filter(
        entry__company=company, bank_statement_line__isnull=False
    ).select_related("bank_statement_line")
    if not qs.exists():
        return []
    for line in qs[:50]:
        status = line.bank_statement_line.match_status
        if status != BankLineMatchStatus.MATCHED:
            out.append(
                f"journal line {line.pk} is GL-matched to statement line "
                f"{line.bank_statement_line_id} but match_status={status}"
            )
    return out
