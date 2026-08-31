"""B-06 — back-scan billed GST vs the effective-dated HSN table."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.utils import timezone

from masters.hsn_catalog import rate_for
from sales.models import SalesInvoice, SalesItem


def _tax_delta(taxable: Decimal, billed_rate: Decimal, expected_rate: Decimal) -> Decimal:
    return (taxable * (expected_rate - billed_rate) / Decimal("100")).quantize(Decimal("0.01"))


def backscan_rate_exposure(company, *, date_from: date | None = None, date_to: date | None = None) -> dict:
    """Completed GST invoices whose snapshotted rate differs from the table on that date."""
    date_from = date_from or date(2025, 9, 1)
    date_to = date_to or timezone.localdate()
    qs = (
        SalesItem.objects.filter(
            invoice__company=company,
            invoice__status=SalesInvoice.Status.COMPLETED,
            invoice__invoice_type=SalesInvoice.InvoiceType.GST,
            invoice__invoice_date__gte=date_from,
            invoice__invoice_date__lte=date_to,
        )
        .select_related("invoice", "product")
        .order_by("invoice__invoice_date", "id")
    )
    rows = []
    exposure = Decimal("0")
    for item in qs:
        if getattr(item, "rate_override", False):
            continue
        hsn = item.hsn_code or getattr(item.product, "hsn_code", "") or ""
        resolved = rate_for(hsn, item.invoice.invoice_date)
        if not resolved:
            continue
        billed = Decimal(str(item.applied_rate or item.gst_rate or 0))
        expected = resolved["rate"]
        if billed == expected:
            continue
        taxable = Decimal(str(item.taxable_amount or 0))
        delta = _tax_delta(taxable, billed, expected)
        exposure += delta
        rows.append({
            "invoice_id": item.invoice_id,
            "invoice_number": item.invoice.number,
            "invoice_date": item.invoice.invoice_date.isoformat(),
            "hsn": hsn,
            "billed_rate": str(billed),
            "expected_rate": str(expected),
            "rate_version": resolved["version"],
            "taxable": str(taxable),
            "tax_delta": str(delta),
            "line_id": item.id,
        })
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "count": len(rows),
        "estimated_exposure": str(exposure),
        "curator_named": False,
        "disclaimer": (
            "Starter HSN table only — rates are not updated automatically until a curator is named."
        ),
        "rows": rows[:500],
    }
