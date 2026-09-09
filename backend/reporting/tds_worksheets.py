"""BB-000670: 26Q / 27EQ worksheet aids — not live IT portal upload."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Q

from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice


def parse_month_period(period: str) -> tuple[date, date]:
    year_s, month_s = period.split("-", 1)
    year, month = int(year_s), int(month_s)
    if month < 1 or month > 12:
        raise ValueError("period must be YYYY-MM")
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    from datetime import timedelta

    return start, end - timedelta(days=1)


def tds_worksheet_rows(company, period: str) -> list[dict]:
    start, end = parse_month_period(period)
    qs = (
        PurchaseInvoice.objects.filter(
            company=company,
            invoice_date__gte=start,
            invoice_date__lte=end,
            is_opening_balance=False,  # B5-015
            status__in=(
                PurchaseInvoice.Status.COMPLETED,
                PurchaseInvoice.Status.RETURNED,
            ),
        )
        .filter(Q(tds_amount__gt=0) | ~Q(tds_section=""))
        .select_related("supplier")
        .order_by("invoice_date", "id")
    )
    rows = []
    for inv in qs:
        rows.append({
            "date": inv.invoice_date.isoformat(),
            "invoice": inv.number,
            "supplier": inv.supplier.name,
            "supplier_gstin": getattr(inv.supplier, "gstin", "") or "",
            "section": inv.tds_section or "",
            "rate": str(inv.tds_rate or Decimal("0")),
            "taxable": str(inv.taxable_total or Decimal("0")),
            "grand_total": str(inv.grand_total or Decimal("0")),
            "tds_amount": str(inv.tds_amount or Decimal("0")),
            "net_payable": str(
                (inv.grand_total or Decimal("0")) - (inv.tds_amount or Decimal("0"))
            ),
            "source": "purchase_invoice",
        })
    from payments.models import SupplierPayment, SupplierPaymentStatus

    pay_qs = (
        SupplierPayment.objects.filter(
            company=company,
            payment_date__gte=start,
            payment_date__lte=end,
            status=SupplierPaymentStatus.POSTED,
        )
        .filter(Q(tds_amount__gt=0) | ~Q(tds_section=""))
        .select_related("supplier")
        .order_by("payment_date", "id")
    )
    for pay in pay_qs:
        rows.append({
            "date": pay.payment_date.isoformat(),
            "invoice": pay.number or "",
            "supplier": pay.supplier.name,
            "supplier_gstin": getattr(pay.supplier, "gstin", "") or "",
            "section": pay.tds_section or "",
            "rate": str(pay.tds_rate or Decimal("0")),
            "taxable": str(pay.amount or Decimal("0")),
            "grand_total": str(pay.amount or Decimal("0")),
            "tds_amount": str(pay.tds_amount or Decimal("0")),
            "net_payable": str(
                (pay.amount or Decimal("0")) - (pay.tds_amount or Decimal("0"))
            ),
            "source": "supplier_payment",
        })

    # CR-052: Include purchase credit notes and debit notes
    from purchases.models import PurchaseCreditNote, PurchaseDebitNote

    pcn_qs = (
        PurchaseCreditNote.objects.filter(
            company=company,
            note_date__gte=start,
            note_date__lte=end,
            status=PurchaseCreditNote.Status.COMPLETED,
        )
        .filter(
            Q(purchase_invoice__tds_amount__gt=0) | ~Q(purchase_invoice__tds_section="")
        )
        .select_related("supplier", "purchase_invoice")
        .order_by("note_date", "id")
    )
    for pcn in pcn_qs:
        inv = pcn.purchase_invoice
        tds_rate = inv.tds_rate or Decimal("0") if inv else Decimal("0")
        note_tds = ((pcn.taxable_total or Decimal("0")) * tds_rate / Decimal("100")).quantize(Decimal("0.01")) if tds_rate else Decimal("0")
        rows.append({
            "date": pcn.note_date.isoformat(),
            "invoice": pcn.number,
            "supplier": pcn.supplier.name,
            "supplier_gstin": getattr(pcn.supplier, "gstin", "") or "",
            "section": inv.tds_section if inv else "",
            "rate": str(tds_rate),
            "taxable": str(-(pcn.taxable_total or Decimal("0"))),
            "grand_total": str(-(pcn.grand_total or Decimal("0"))),
            "tds_amount": str(-note_tds),
            "net_payable": str(-((pcn.grand_total or Decimal("0")) - note_tds)),
            "source": "purchase_credit_note",
        })

    pdn_qs = (
        PurchaseDebitNote.objects.filter(
            company=company,
            note_date__gte=start,
            note_date__lte=end,
            status=PurchaseDebitNote.Status.COMPLETED,
        )
        .filter(
            Q(purchase_invoice__tds_amount__gt=0) | ~Q(purchase_invoice__tds_section="")
        )
        .select_related("supplier", "purchase_invoice")
        .order_by("note_date", "id")
    )
    for pdn in pdn_qs:
        inv = pdn.purchase_invoice
        tds_rate = inv.tds_rate or Decimal("0") if inv else Decimal("0")
        note_tds = ((pdn.taxable_total or Decimal("0")) * tds_rate / Decimal("100")).quantize(Decimal("0.01")) if tds_rate else Decimal("0")
        rows.append({
            "date": pdn.note_date.isoformat(),
            "invoice": pdn.number,
            "supplier": pdn.supplier.name,
            "supplier_gstin": getattr(pdn.supplier, "gstin", "") or "",
            "section": inv.tds_section if inv else "",
            "rate": str(tds_rate),
            "taxable": str(pdn.taxable_total or Decimal("0")),
            "grand_total": str(pdn.grand_total or Decimal("0")),
            "tds_amount": str(note_tds),
            "net_payable": str((pdn.grand_total or Decimal("0")) - note_tds),
            "source": "purchase_debit_note",
        })

    return rows


def tcs_worksheet_rows(company, period: str) -> list[dict]:
    start, end = parse_month_period(period)
    qs = (
        SalesInvoice.objects.filter(
            company=company,
            invoice_date__gte=start,
            invoice_date__lte=end,
            is_opening_balance=False,  # B5-015
            status__in=(
                SalesInvoice.Status.COMPLETED,
                SalesInvoice.Status.RETURNED,
            ),
        )
        .filter(Q(tcs_amount__gt=0) | ~Q(tcs_section=""))
        .select_related("customer")
        .order_by("invoice_date", "id")
    )
    rows = []
    for inv in qs:
        rows.append({
            "date": inv.invoice_date.isoformat(),
            "invoice": inv.number,
            "customer": inv.customer.name,
            "customer_gstin": getattr(inv.customer, "gstin", "") or "",
            "section": inv.tcs_section or "",
            "rate": str(inv.tcs_rate or Decimal("0")),
            "taxable": str(inv.taxable_total or Decimal("0")),
            "grand_total": str(inv.grand_total or Decimal("0")),
            "tcs_amount": str(inv.tcs_amount or Decimal("0")),
            "receivable": str(
                (inv.grand_total or Decimal("0"))
                + (
                    Decimal("0")
                    if getattr(inv, "tcs_in_grand_total", False)
                    else (inv.tcs_amount or Decimal("0"))
                )
            ),
            "source": "sales_invoice",
        })

    # CR-052: Include sales credit notes and debit notes
    from sales.models import SalesCreditNote, SalesDebitNote

    scn_qs = (
        SalesCreditNote.objects.filter(
            company=company,
            note_date__gte=start,
            note_date__lte=end,
            status=SalesCreditNote.Status.COMPLETED,
        )
        .filter(
            Q(tcs_amount__gt=0)
            | Q(sales_invoice__tcs_amount__gt=0)
            | ~Q(sales_invoice__tcs_section="")
        )
        .select_related("customer", "sales_invoice")
        .order_by("note_date", "id")
    )
    for scn in scn_qs:
        inv = scn.sales_invoice
        tcs_amount = scn.tcs_amount or Decimal("0")
        if not tcs_amount and inv and inv.tcs_rate:
            tcs_amount = ((scn.grand_total or Decimal("0")) * inv.tcs_rate / Decimal("100")).quantize(Decimal("0.01"))
        rows.append({
            "date": scn.note_date.isoformat(),
            "invoice": scn.number,
            "customer": scn.customer.name,
            "customer_gstin": getattr(scn.customer, "gstin", "") or "",
            "section": getattr(inv, "tcs_section", "") if inv else "",
            "rate": str(getattr(inv, "tcs_rate", Decimal("0")) if inv else Decimal("0")),
            "taxable": str(-(scn.taxable_total or Decimal("0"))),
            "grand_total": str(-(scn.grand_total or Decimal("0"))),
            "tcs_amount": str(-tcs_amount),
            "receivable": str(-(scn.grand_total or Decimal("0")) - tcs_amount),
            "source": "sales_credit_note",
        })

    sdn_qs = (
        SalesDebitNote.objects.filter(
            company=company,
            note_date__gte=start,
            note_date__lte=end,
            status=SalesDebitNote.Status.COMPLETED,
        )
        .filter(
            Q(tcs_amount__gt=0)
            | Q(sales_invoice__tcs_amount__gt=0)
            | ~Q(sales_invoice__tcs_section="")
        )
        .select_related("customer", "sales_invoice")
        .order_by("note_date", "id")
    )
    for sdn in sdn_qs:
        inv = sdn.sales_invoice
        tcs_amount = sdn.tcs_amount or Decimal("0")
        if not tcs_amount and inv and inv.tcs_rate:
            tcs_amount = ((sdn.grand_total or Decimal("0")) * inv.tcs_rate / Decimal("100")).quantize(Decimal("0.01"))
        rows.append({
            "date": sdn.note_date.isoformat(),
            "invoice": sdn.number,
            "customer": sdn.customer.name,
            "customer_gstin": getattr(sdn.customer, "gstin", "") or "",
            "section": getattr(inv, "tcs_section", "") if inv else "",
            "rate": str(getattr(inv, "tcs_rate", Decimal("0")) if inv else Decimal("0")),
            "taxable": str(sdn.taxable_total or Decimal("0")),
            "grand_total": str(sdn.grand_total or Decimal("0")),
            "tcs_amount": str(tcs_amount),
            "receivable": str((sdn.grand_total or Decimal("0")) + tcs_amount),
            "source": "sales_debit_note",
        })

    return rows
