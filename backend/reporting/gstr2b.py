    """Wave 16D — GSTR-2B/2A file ingest match + composition return aids.

    Live GSP auto-claim stays dark. Upload `source=2A` or `2B` (default 2B).
    """

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from reporting.models import Gstr2bIngest


def match_gstr2b_to_purchases(company, period: str, *, persist: bool = True) -> dict:
    """Match ingested 2B rows to purchase invoices by GSTIN + number + amount.

    BB-000637: ZIP/CA-pack downloads must call with persist=False (read-only preview).
    BB-000716: prefer unique amount+date match; PARTIAL does not sticky-link wrong PI.
    """
    from purchases.models import PurchaseInvoice

    rows = list(Gstr2bIngest.objects.filter(company=company, period=period))
    matched = 0
    for row in rows:
        if row.match_status == Gstr2bIngest.MatchStatus.MATCHED:
            matched += 1
            continue
        qs = PurchaseInvoice.objects.filter(
            company=company,
            status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
            supplier__gstin__iexact=row.supplier_gstin,
            number=row.invoice_number,
            is_opening_balance=False,
        )
        candidates = list(qs)
        if not candidates:
            continue
        row_tax = (
            Decimal(str(row.cgst or 0))
            + Decimal(str(row.sgst or 0))
            + Decimal(str(row.igst or 0))
            + Decimal(str(getattr(row, "cess", 0) or 0))
        )
        row_taxable = Decimal(str(row.taxable_value or 0))

        def _tax(inv):
            return (
                Decimal(str(inv.cgst_total or 0))
                + Decimal(str(inv.sgst_total or 0))
                + Decimal(str(inv.igst_total or 0))
                + Decimal(str(getattr(inv, "cess_total", 0) or 0))
            )

        exact = [
            inv
            for inv in candidates
            if abs(_tax(inv) - row_tax) <= Decimal("1.00")
            and abs(Decimal(str(inv.taxable_total or 0)) - row_taxable) <= Decimal("1.00")
        ]
        if len(exact) == 1:
            status = Gstr2bIngest.MatchStatus.MATCHED
            inv = exact[0]
            matched += 1
            if persist:
                row.match_status = status
                row.purchase_invoice = inv
                row.save(update_fields=["match_status", "purchase_invoice", "updated_at"])
            continue
        # PARTIAL or ambiguous: do not force FK (BB-000716).
        if persist:
            row.match_status = Gstr2bIngest.MatchStatus.PARTIAL
            row.purchase_invoice = None
            row.save(update_fields=["match_status", "purchase_invoice", "updated_at"])
    return {"period": period, "rows": len(rows), "matched": matched, "persisted": persist}


def claimable_itc_from_2b(company, period: str) -> dict:
    """ITC amounts only from MATCHED 2B rows (feeds GSTR-3B)."""
    from purchases.models import PurchaseInvoice

    qs = Gstr2bIngest.objects.filter(
        company=company,
        period=period,
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
        itc_eligibility=Gstr2bIngest.ItcEligibility.CLAIMABLE,
        purchase_invoice__itc_eligibility=PurchaseInvoice.ItcEligibility.CLAIMABLE,
        purchase_invoice__is_opening_balance=False,
        purchase_invoice__is_reverse_charge=False,
    )
    agg = qs.aggregate(
        cgst=Sum("cgst"),
        sgst=Sum("sgst"),
        igst=Sum("igst"),
        cess=Sum("cess"),
        taxable=Sum("taxable_value"),
    )
    return {
        "cgst": agg["cgst"] or Decimal("0"),
        "sgst": agg["sgst"] or Decimal("0"),
        "igst": agg["igst"] or Decimal("0"),
        "cess": agg["cess"] or Decimal("0"),
        "taxable": agg["taxable"] or Decimal("0"),
        "claimable": True,
        "source": "gstr2b_matched",
    }


def build_cmp08(company, period: str) -> dict:
    """Composition CMP-08 quarterly aid (Wave 16D / BB-000623)."""
    from sales.models import SalesCreditNote, SalesDebitNote, SalesInvoice

    year, month = period.split("-")
    y, m = int(year), int(month)
    q_start_m = ((m - 1) // 3) * 3 + 1
    invoices = SalesInvoice.objects.filter(
        company=company,
        status__in=(SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED),
        invoice_date__year=y,
        invoice_date__month__gte=q_start_m,
        invoice_date__month__lt=q_start_m + 3,
        is_opening_balance=False,
    ).exclude(invoice_type=SalesInvoice.InvoiceType.NON_GST)
    taxable = sum((Decimal(str(i.taxable_total or 0)) for i in invoices), Decimal("0"))
    cns = SalesCreditNote.objects.filter(
        company=company,
        status=SalesCreditNote.Status.COMPLETED,
        note_date__year=y,
        note_date__month__gte=q_start_m,
        note_date__month__lt=q_start_m + 3,
        sales_invoice__is_opening_balance=False,
    )
    dns = SalesDebitNote.objects.filter(
        company=company,
        status=SalesDebitNote.Status.COMPLETED,
        note_date__year=y,
        note_date__month__gte=q_start_m,
        note_date__month__lt=q_start_m + 3,
        sales_invoice__is_opening_balance=False,
    )
    taxable -= sum((Decimal(str(n.taxable_total or 0)) for n in cns), Decimal("0"))
    taxable += sum((Decimal(str(n.taxable_total or 0)) for n in dns), Decimal("0"))
    return {
        "version": "cmp08@1.0.1",
        "aid_kind": "composition_cmp08",
        "period": period,
        "quarter_start_month": q_start_m,
        "outward_taxable": str(taxable),
        "disclaimer": "CMP-08 aid — opening/non-GST excluded; CNs netted. Verify rates with CA.",
    }


def build_gstr4(company, fy_label: str) -> dict:
    """Composition GSTR-4 annual aid (Wave 16D)."""
    return {
        "version": "gstr4@1.0.0",
        "aid_kind": "composition_gstr4",
        "fy": fy_label,
        "disclaimer": "GSTR-4 worksheet aid — not a portal-complete annual return.",
        "tables": {},
    }
