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
            status=PurchaseInvoice.Status.COMPLETED,
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
    return rows


def tcs_worksheet_rows(company, period: str) -> list[dict]:
    start, end = parse_month_period(period)
    qs = (
        SalesInvoice.objects.filter(
            company=company,
            invoice_date__gte=start,
            invoice_date__lte=end,
            status=SalesInvoice.Status.COMPLETED,
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
        })
    return rows
