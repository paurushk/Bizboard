"""Wave 16D — GSTR-2B/2A file ingest match + composition return aids.

Live GSP auto-claim stays dark. Upload `source=2A` or `2B` (default 2B).
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q, Sum

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
            number__iexact=row.invoice_number,
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
        if row.invoice_date:
            dated = [inv for inv in exact if inv.invoice_date == row.invoice_date]
            fy_matched = [
                inv
                for inv in exact
                if inv.invoice_date and inv.invoice_date.year == row.invoice_date.year
            ]
            exact = dated if dated else fy_matched
        # Never MATCH on GSTIN+number alone — require unique amount (±₹1) and date/FY when present.
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


def claimable_itc_from_2b(company, period: str, *, company_gstin_id=None) -> dict:
    """ITC amounts only from MATCHED 2B rows (feeds GSTR-3B)."""
    from purchases.models import PurchaseInvoice

    qs = Gstr2bIngest.objects.filter(
        company=company,
        period=period,
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
        itc_eligibility=Gstr2bIngest.ItcEligibility.CLAIMABLE,
    ).exclude(
        purchase_invoice__itc_eligibility__in=[
            PurchaseInvoice.ItcEligibility.INELIGIBLE,
            PurchaseInvoice.ItcEligibility.REVERSED,
        ]
    ).exclude(
        purchase_invoice__is_opening_balance=True,
    ).exclude(
        purchase_invoice__is_reverse_charge=True,
    )
    if company_gstin_id is not None:
        from accounts.models import CompanyGstin

        primary = CompanyGstin.objects.filter(
            company=company, is_primary=True, is_active=True
        ).first()
        if primary is not None and primary.id == company_gstin_id:
            qs = qs.filter(
                Q(purchase_invoice__company_gstin_id=company_gstin_id)
                | Q(purchase_invoice__company_gstin_id__isnull=True)
            )
        else:
            qs = qs.filter(purchase_invoice__company_gstin_id=company_gstin_id)
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
    from purchases.models import PurchaseInvoice
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
    taxable = max(Decimal("0.00"), taxable)

    # Inward supplies attracting reverse charge (Table 2)
    rcm_purchases = PurchaseInvoice.objects.filter(
        company=company,
        status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
        invoice_date__year=y,
        invoice_date__month__gte=q_start_m,
        invoice_date__month__lt=q_start_m + 3,
        is_reverse_charge=True,
    )
    inward_rcm_taxable = sum((Decimal(str(p.taxable_total or 0)) for p in rcm_purchases), Decimal("0"))
    inward_rcm_tax = sum(
        (
            Decimal(str(p.rcm_cgst or 0))
            + Decimal(str(p.rcm_sgst or 0))
            + Decimal(str(p.rcm_igst or 0))
            + Decimal(str(p.rcm_cess or 0))
            for p in rcm_purchases
        ),
        Decimal("0"),
    )

    flags = getattr(company, "feature_flags", None) or {}
    raw_rate = flags.get("composition_cmp08_rate") if isinstance(flags, dict) else None
    composition_rate = Decimal(str(raw_rate or "0.01"))
    est_outward_tax = (taxable * composition_rate).quantize(Decimal("0.01"))
    total_tax_payable = est_outward_tax + inward_rcm_tax

    return {
        "version": "cmp08@1.1.0",
        "aid_kind": "composition_cmp08",
        "period": period,
        "quarter_start_month": q_start_m,
        "table_1_outward_taxable": str(taxable),
        "table_2_inward_rcm_taxable": str(inward_rcm_taxable),
        "table_2_inward_rcm_tax": str(inward_rcm_tax),
        "table_3_tax_payable": str(total_tax_payable),
        "composition_rate": str(composition_rate),
        "outward_taxable": str(taxable),
        "disclaimer": (
            f"CMP-08 aid — assumed composition rate {composition_rate} "
            "(override via company feature_flags.composition_cmp08_rate; restaurants often 5%). "
            "Opening/non-GST excluded; CNs netted; Table 2 RCM included. Verify rates with CA."
        ),
    }


def build_gstr4(company, fy_label: str) -> dict:
    """Composition GSTR-4 annual aid (Wave 16D)."""
    return {
        "version": "gstr4@1.0.0",
        "aid_kind": "composition_gstr4",
        "fy": fy_label,
        "disclaimer": "GSTR-4 worksheet aid — not a portal-complete annual return.",
        "supported": False,
        "tables": {
            "4": {"note": "Table 4 (inward supplies) is not implemented."},
            "5": {"note": "Table 5 (import of services / reverse charge) is not implemented."},
            "6": {"note": "Table 6 (tax paid) is not implemented."},
            "note": "GSTR-4 tables are not implemented — this is a composition worksheet stub, not a portal file.",
        },
    }


def build_gstr8(company, period: str) -> dict:
    """E-commerce operator GSTR-8 TCS return — honest stub, not an engine."""
    return {
        "version": "gstr8@1.0.0",
        "aid_kind": "ecommerce_gstr8",
        "period": period,
        "supported": False,
        "disclaimer": (
            "GSTR-8 is the e-commerce operator TCS return. Bizboard does not implement "
            "a portal-complete GSTR-8 engine. Use this payload only as a placeholder."
        ),
        "tables": {
            "note": "GSTR-8 tables are not implemented — this is an honesty stub, not a portal file.",
        },
    }


def build_gstr6(company, period: str) -> dict:
    """ISD GSTR-6 — honest stub, not an engine."""
    return {
        "version": "gstr6@1.0.0",
        "aid_kind": "isd_gstr6",
        "period": period,
        "supported": False,
        "disclaimer": (
            "GSTR-6 is the Input Service Distributor return. Bizboard does not implement "
            "an ISD / GSTR-6 engine."
        ),
        "tables": {
            "note": "GSTR-6 tables are not implemented — this is an honesty stub, not a portal file.",
        },
    }


def build_gstr7(company, period: str) -> dict:
    """TDS under GST GSTR-7 — honest stub, not an engine."""
    return {
        "version": "gstr7@1.0.0",
        "aid_kind": "tds_gstr7",
        "period": period,
        "supported": False,
        "disclaimer": (
            "GSTR-7 is the GST TDS return. Bizboard does not implement a GSTR-7 engine."
        ),
        "tables": {
            "note": "GSTR-7 tables are not implemented — this is an honesty stub, not a portal file.",
        },
    }
