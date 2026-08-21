"""
GSTR-1 / GSTR-3B / GSTR-9 builders from completed GST documents.

Offline CA aids — not GSTN portal upload schema unless feature flag enabled.
Builder version: gstr1@2.0.0 — rate-wise B2B/CDNR, line HSN/UQC snapshots only.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.utils import timezone

from core.services.billing import extract_state_code, is_intra_state, q2
from core.services.uqc import normalize_uqc
from purchases.models import PurchaseCreditNote, PurchaseDebitNote, PurchaseInvoice
from sales.models import SalesCreditNote, SalesDebitNote, SalesInvoice

from .models import GstReturnPeriod, GstReturnSnapshot
from .gst_returns_sections import (
    accumulate_hsn_line,
    append_b2_outward_rows,
    build_note_rate_rows,
    new_hsn_buckets,
)

BUILDER_VERSION_GSTR1 = "gstr1@2.0.0"
BUILDER_VERSION_GSTR3B = "gstr3b@2.2.0"
BUILDER_VERSION_GSTR9 = "gstr9@2.2.0"

# Notification 12/2024-CT: interstate B2C large threshold ₹1,00,000 from 1 Aug 2024.
# GAP-004: B2CL is inter-state unregistered supplies above ₹2.5 lakh (post-2021).
B2CL_THRESHOLD = Decimal("250000")
GST_INVOICE_TYPES = {
    SalesInvoice.InvoiceType.GST,
    SalesInvoice.InvoiceType.TAX,
    SalesInvoice.InvoiceType.RETAIL,
}
# AATO default for e-Invoice mandatory alert (₹5 crore) — override via company.aato_turnover.
EINVOICE_AATO_THRESHOLD = Decimal("50000000")


def parse_period(period: str) -> tuple[date, date]:
    try:
        year_str, month_str = period.split("-", 1)
        year, month = int(year_str), int(month_str)
        if month < 1 or month > 12:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid period '{period}'. Expected YYYY-MM.") from exc
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _money(value: Decimal | None) -> str:
    return str(q2(value or Decimal("0")))


def _sum_fields(rows: list[dict], *keys: str) -> dict[str, str]:
    totals = {key: Decimal("0") for key in keys}
    for row in rows:
        for key in keys:
            totals[key] += Decimal(str(row.get(key, "0")))
    return {key: _money(val) for key, val in totals.items()}


def _party_pos(company, party_state: str, party_gstin: str, *, filing_pos: str = "") -> str:
    if (filing_pos or "").strip():
        return filing_pos.strip()
    code = extract_state_code(party_gstin)
    if code:
        return code
    state = (party_state or "").strip()
    if state:
        return state
    if company.assume_local_state_for_blank_party:
        return extract_state_code(company.gstin) or (company.state or "").strip() or "NA"
    return "NA"


def _filing_gstin(invoice: SalesInvoice) -> str:
    overlay = (getattr(invoice, "filing_party_gstin", None) or "").strip()
    if overlay:
        return overlay
    return (invoice.customer.gstin or "").strip()


def _filing_pos(invoice: SalesInvoice, company) -> str:
    overlay = (getattr(invoice, "filing_place_of_supply", None) or "").strip()
    return _party_pos(
        company,
        invoice.customer.state or "",
        _filing_gstin(invoice),
        filing_pos=overlay,
    )


def _is_b2b(party_gstin: str) -> bool:
    return bool((party_gstin or "").strip())


def _inter_state(company, party_state: str, party_gstin: str, *, seller_gstin: str = "", seller_state: str = "") -> bool:
    return not is_intra_state(
        seller_state or company.state or "",
        party_state or "",
        company_gstin=seller_gstin or company.gstin or "",
        party_gstin=party_gstin or "",
    )


def invoice_value_mismatch(invoice) -> bool:
    """
    True when grand_total cannot equal taxable + taxes + charges ± round-off/discount.
    BB-000621: additional_charges must not silently drop invoices from GSTR sections.
    """
    taxable = Decimal(str(invoice.taxable_total or 0))
    tax = (
        Decimal(str(invoice.cgst_total or 0))
        + Decimal(str(invoice.sgst_total or 0))
        + Decimal(str(invoice.igst_total or 0))
        + Decimal(str(getattr(invoice, "cess_total", 0) or 0))
    )
    round_off = Decimal(str(invoice.round_off or 0))
    charges = Decimal(str(getattr(invoice, "additional_charges", 0) or 0))
    discount = Decimal(str(getattr(invoice, "invoice_discount", 0) or 0))
    mode = getattr(invoice, "invoice_discount_mode", "AFTER_TAX")
    if discount != 0 and mode == "AFTER_TAX":
        return True
    expected = q2(taxable + tax + round_off + charges)
    grand = q2(Decimal(str(invoice.grand_total or 0)))
    return expected != grand


def _rate_buckets(items) -> dict[Decimal, dict]:
    buckets: dict[Decimal, dict] = defaultdict(
        lambda: {
            "taxable_value": Decimal("0"),
            "cgst": Decimal("0"),
            "sgst": Decimal("0"),
            "igst": Decimal("0"),
            "cess": Decimal("0"),
        }
    )
    for item in items:
        rate = Decimal(str(item.gst_rate or 0))
        buckets[rate]["taxable_value"] += Decimal(str(item.taxable_amount or 0))
        buckets[rate]["cgst"] += Decimal(str(item.cgst or 0))
        buckets[rate]["sgst"] += Decimal(str(item.sgst or 0))
        buckets[rate]["igst"] += Decimal(str(item.igst or 0))
        buckets[rate]["cess"] += Decimal(str(getattr(item, "cess", 0) or 0))
    return buckets


def _gst_sales_invoices(company, date_from: date, date_to: date, *, company_gstin_id=None):
    qs = (
        SalesInvoice.objects.filter(
            company=company,
            status__in=(SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED),
            invoice_type__in=GST_INVOICE_TYPES,
            invoice_date__gte=date_from,
            invoice_date__lte=date_to,
            # BB-000335: Tally-migration opening balances are not real supplies —
            # they must never inflate GSTR-1/3B outward tax liability.
            is_opening_balance=False,
        )
        .select_related("customer", "company_gstin")
        .prefetch_related("items")
    )
    if company_gstin_id is not None:
        qs = qs.filter(company_gstin_id=company_gstin_id)
    return qs


def _gst_credit_notes(company, date_from: date, date_to: date, *, company_gstin_id=None):
    qs = (
        SalesCreditNote.objects.filter(
            company=company,
            status=SalesCreditNote.Status.COMPLETED,
            note_date__gte=date_from,
            note_date__lte=date_to,
            sales_invoice__invoice_type__in=GST_INVOICE_TYPES,
            # BB-000398: exclude notes against opening invoices.
            sales_invoice__is_opening_balance=False,
        )
        .select_related("customer", "sales_invoice", "sales_invoice__company_gstin")
        .prefetch_related("items")
    )
    if company_gstin_id is not None:
        qs = qs.filter(sales_invoice__company_gstin_id=company_gstin_id)
    return qs


def _gst_debit_notes(company, date_from: date, date_to: date, *, company_gstin_id=None):
    qs = (
        SalesDebitNote.objects.filter(
            company=company,
            status=SalesDebitNote.Status.COMPLETED,
            note_date__gte=date_from,
            note_date__lte=date_to,
            sales_invoice__invoice_type__in=GST_INVOICE_TYPES,
            sales_invoice__is_opening_balance=False,
        )
        .select_related("customer", "sales_invoice", "sales_invoice__company_gstin")
        .prefetch_related("items")
    )
    if company_gstin_id is not None:
        qs = qs.filter(sales_invoice__company_gstin_id=company_gstin_id)
    return qs


def _gst_purchase_invoices(company, date_from: date, date_to: date, *, company_gstin_id=None):
    qs = PurchaseInvoice.objects.filter(
        company=company,
        status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
        purchase_type=PurchaseInvoice.PurchaseType.GST,
        invoice_date__gte=date_from,
        invoice_date__lte=date_to,
        # BB-000335: opening balances are not real purchases — must never inflate
        # GSTR-2B-matching ITC claims or 3B inward liability.
        is_opening_balance=False,
    ).select_related("supplier", "company_gstin").prefetch_related("items")
    return _filter_purchase_gstin(qs, company, company_gstin_id, field="company_gstin_id")


def _filter_purchase_gstin(qs, company, company_gstin_id, *, field: str):
    if company_gstin_id is None:
        return qs
    from django.db.models import Q

    from accounts.models import CompanyGstin

    primary = CompanyGstin.objects.filter(company=company, is_primary=True, is_active=True).first()
    if primary is not None and primary.id == company_gstin_id:
        return qs.filter(Q(**{field: company_gstin_id}) | Q(**{field: None}))
    return qs.filter(**{field: company_gstin_id})


def _gst_purchase_credit_notes(company, date_from: date, date_to: date, *, company_gstin_id=None):
    """GST purchase CNs on non-RCM invoices — eligible for non-RCM ITC netting."""
    qs = PurchaseCreditNote.objects.filter(
        company=company,
        status=PurchaseCreditNote.Status.COMPLETED,
        note_date__gte=date_from,
        note_date__lte=date_to,
        purchase_invoice__purchase_type=PurchaseInvoice.PurchaseType.GST,
        purchase_invoice__is_reverse_charge=False,
        purchase_invoice__is_opening_balance=False,
    ).select_related("purchase_invoice")
    return _filter_purchase_gstin(qs, company, company_gstin_id, field="purchase_invoice__company_gstin_id")


def _gst_purchase_debit_notes(company, date_from: date, date_to: date, *, company_gstin_id=None):
    qs = PurchaseDebitNote.objects.filter(
        company=company,
        status=PurchaseDebitNote.Status.COMPLETED,
        note_date__gte=date_from,
        note_date__lte=date_to,
        purchase_invoice__purchase_type=PurchaseInvoice.PurchaseType.GST,
        purchase_invoice__is_reverse_charge=False,
        purchase_invoice__is_opening_balance=False,
    )
    return _filter_purchase_gstin(qs, company, company_gstin_id, field="purchase_invoice__company_gstin_id")


def _gst_purchase_credit_notes_rcm(company, date_from: date, date_to: date, *, company_gstin_id=None):
    """BB-000336: purchase CNs on RCM invoices — netted into 3.1(d), not 4(A)(3)."""
    qs = PurchaseCreditNote.objects.filter(
        company=company,
        status=PurchaseCreditNote.Status.COMPLETED,
        note_date__gte=date_from,
        note_date__lte=date_to,
        purchase_invoice__purchase_type=PurchaseInvoice.PurchaseType.GST,
        purchase_invoice__is_reverse_charge=True,
        purchase_invoice__is_opening_balance=False,
    )
    return _filter_purchase_gstin(qs, company, company_gstin_id, field="purchase_invoice__company_gstin_id")


def _gst_purchase_debit_notes_rcm(company, date_from: date, date_to: date, *, company_gstin_id=None):
    """BB-000336: purchase DNs on RCM invoices — netted into 3.1(d), not 4(A)(3)."""
    qs = PurchaseDebitNote.objects.filter(
        company=company,
        status=PurchaseDebitNote.Status.COMPLETED,
        note_date__gte=date_from,
        note_date__lte=date_to,
        purchase_invoice__purchase_type=PurchaseInvoice.PurchaseType.GST,
        purchase_invoice__is_reverse_charge=True,
        purchase_invoice__is_opening_balance=False,
    )
    return _filter_purchase_gstin(qs, company, company_gstin_id, field="purchase_invoice__company_gstin_id")


def assert_not_composition_for_regular_returns(company):
    from core.exceptions import BusinessRuleError
    from accounts.models import Company

    if company.registration_type == Company.RegistrationType.COMPOSITION:
        raise BusinessRuleError(
            "Composition dealers cannot export Regular GSTR-1/GSTR-3B packs. "
            "Use /api/v1/reports/cmp08/ and /api/v1/reports/gstr4/ instead."
        )


def _resolve_filing_gstin_id(company, invoices, *, company_gstin=None):
    """BB-000556: GSTR is per CompanyGstin stamp. Fail closed on mixed stamps."""
    from accounts.models import CompanyGstin
    from core.exceptions import BusinessRuleError

    if company_gstin in (None, "", "all"):
        stamp_ids = {getattr(inv, "company_gstin_id", None) for inv in invoices}
        stamp_ids.discard(None)
        if len(stamp_ids) > 1:
            raise BusinessRuleError(
                "Period contains invoices stamped with multiple GSTINs. "
                "Pass company_gstin to file each registration separately."
            )
        if len(stamp_ids) == 1:
            return next(iter(stamp_ids))
        primary = CompanyGstin.objects.filter(
            company=company, is_primary=True, is_active=True
        ).first()
        return primary.id if primary else None

    if isinstance(company_gstin, int) or str(company_gstin).isdigit():
        row = CompanyGstin.objects.filter(company=company, pk=int(company_gstin)).first()
    else:
        row = CompanyGstin.objects.filter(
            company=company, gstin__iexact=str(company_gstin).strip()
        ).first()
    if row is None:
        raise BusinessRuleError("Unknown company_gstin for this company.")
    return row.id


def build_gstr1(company, period: str, *, company_gstin=None) -> dict:
    assert_not_composition_for_regular_returns(company)
    date_from, date_to = parse_period(period)
    preview = list(_gst_sales_invoices(company, date_from, date_to))
    stamp_id = _resolve_filing_gstin_id(company, preview, company_gstin=company_gstin)
    invoices = list(_gst_sales_invoices(company, date_from, date_to, company_gstin_id=stamp_id))
    credit_notes = list(_gst_credit_notes(company, date_from, date_to, company_gstin_id=stamp_id))
    debit_notes = list(_gst_debit_notes(company, date_from, date_to, company_gstin_id=stamp_id))

    issues: list[dict] = []
    b2b: list[dict] = []
    b2cl: list[dict] = []
    exp: list[dict] = []
    sez: list[dict] = []
    b2cs_buckets: dict[tuple, dict] = defaultdict(
        lambda: {
            "taxable_value": Decimal("0"),
            "cgst": Decimal("0"),
            "sgst": Decimal("0"),
            "igst": Decimal("0"),
            "cess": Decimal("0"),
        }
    )
    hsn_buckets = new_hsn_buckets()
    nil_bucket = {"taxable_value": Decimal("0")}
    supecom_rows: list[dict] = []

    for inv in invoices:
        items = list(inv.items.all())
        for idx, item in enumerate(items, start=1):
            hsn_raw = (item.hsn_code or "").strip()
            uqc_raw = (getattr(item, "uqc_code", None) or "").strip()
            if not hsn_raw:
                issues.append({
                    "code": "HSN_MISSING",
                    "severity": "critical",
                    "document_type": "sales_invoice",
                    "document_id": inv.id,
                    "number": inv.number,
                    "message": f"Line {idx}: missing HSN snapshot.",
                })
            unit_name = (getattr(item, "unit_name", None) or "").strip()
            uqc_unmapped = not uqc_raw or (
                uqc_raw == "OTH" and unit_name and not normalize_uqc(unit_name)
            )
            if uqc_unmapped:
                issues.append({
                    "code": "UQC_UNMAPPED",
                    "severity": "warning",
                    "document_type": "sales_invoice",
                    "document_id": inv.id,
                    "number": inv.number,
                    "message": f"Line {idx}: no GSTN UQC mapped.",
                })

        if invoice_value_mismatch(inv):
            issues.append({
                "code": "INVOICE_VALUE_MISMATCH",
                "severity": "critical",
                "document_type": "sales_invoice",
                "document_id": inv.id,
                "number": inv.number,
                "message": "grand_total does not reconcile to taxable+tax (charges / AFTER_TAX discount).",
            })
            # Exclude from GSTN-shaped sections; HSN/UQC issues already recorded above.
            continue
        # Missing HSN is recorded as an issue above — still include the invoice in
        # B2 sections so the worksheet remains useful for remediation.
        ecom = (getattr(inv, "ecommerce_operator_gstin", None) or "").strip()
        if ecom:
            party_gstin = (inv.filing_party_gstin or getattr(inv.customer, "gstin", "") or "").strip()
            supecom_rows.append({
                "invoice_number": inv.number,
                "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else "",
                "ecommerce_operator_gstin": ecom,
                "taxable_value": _money(inv.taxable_total),
                "invoice_value": _money(inv.grand_total),
                "section": "15A" if party_gstin else "15B",
                "party_gstin": party_gstin,
            })
            # Still accumulate HSN for SUPECOM lines; only skip B2 section routing.
            for item in items:
                accumulate_hsn_line(hsn_buckets, item)
            continue

        buckets = _rate_buckets(items)

        for item in items:
            accumulate_hsn_line(hsn_buckets, item)

        append_b2_outward_rows(
            company=company,
            inv=inv,
            items=items,
            buckets=buckets,
            b2b=b2b,
            b2cl=b2cl,
            b2cs_buckets=b2cs_buckets,
            exp=exp,
            sez=sez,
            nil_bucket=nil_bucket,
        )

    cdnr: list[dict] = []
    cdnur: list[dict] = []

    for note in credit_notes:
        build_note_rate_rows(
            company=company,
            note=note,
            note_kind="CREDIT",
            original_number=note.sales_invoice.number,
            issues=issues,
            hsn_buckets=hsn_buckets,
            cdnr=cdnr,
            cdnur=cdnur,
            b2cs_buckets=b2cs_buckets,
        )
    for note in debit_notes:
        build_note_rate_rows(
            company=company,
            note=note,
            note_kind="DEBIT",
            original_number=note.sales_invoice.number,
            issues=issues,
            hsn_buckets=hsn_buckets,
            cdnr=cdnr,
            cdnur=cdnur,
            b2cs_buckets=b2cs_buckets,
        )

    b2cs = [
        {
            "place_of_supply": pos,
            "rate": rate,
            "taxable_value": _money(vals["taxable_value"]),
            "cgst": _money(vals["cgst"]),
            "sgst": _money(vals["sgst"]),
            "igst": _money(vals["igst"]),
            "cess": _money(vals.get("cess", Decimal("0"))),
        }
        for (pos, rate), vals in sorted(b2cs_buckets.items())
        if vals["taxable_value"] or vals["cgst"] or vals["sgst"] or vals["igst"] or vals.get("cess")
    ]

    cdnr.sort(key=lambda r: (r["note_date"], r["note_number"], r["rate"]))
    cdnur.sort(key=lambda r: (r["note_date"], r["note_number"], r["rate"]))

    hsn = [
        {
            "hsn": hsn_code,
            "rate": rate,
            "uqc": uqc,
            "quantity": _money(vals["quantity"]),
            "taxable_value": _money(vals["taxable_value"]),
            "cgst": _money(vals["cgst"]),
            "sgst": _money(vals["sgst"]),
            "igst": _money(vals["igst"]),
            "cess": _money(vals.get("cess", Decimal("0"))),
        }
        for (hsn_code, rate, uqc), vals in sorted(hsn_buckets.items())
    ]

    cancelled_qs = SalesInvoice.objects.filter(
        company=company,
        status=SalesInvoice.Status.CANCELLED,
        invoice_date__gte=date_from,
        invoice_date__lte=date_to,
        invoice_type__in=GST_INVOICE_TYPES,
    )
    if stamp_id is not None:
        cancelled_qs = cancelled_qs.filter(company_gstin_id=stamp_id)
    cancelled_inv = cancelled_qs.count()

    docs = {
        "invoices_issued": len(invoices),
        "invoices_cancelled": cancelled_inv,
        "credit_notes_issued": len(credit_notes),
        "debit_notes_issued": len(debit_notes),
    }
    doc_table = _gstr1_doc_table(company, date_from, date_to, invoices, cancelled_inv, credit_notes, debit_notes)
    at_table = _gstr1_at_table(company, date_from, date_to, company_gstin_id=stamp_id)
    atadj_table = _gstr1_atadj_table(company, date_from, date_to, company_gstin_id=stamp_id)
    txpd_table = _gstr1_txpd_table(company, date_from, date_to, company_gstin_id=stamp_id)

    # Liability / register totals: exclude INVOICE_VALUE_MISMATCH from outward
    # so GSTR-3B aligns with GSTR-1 section coverage (BB-000038 / G16).
    matched_invoices = [
        inv for inv in invoices
        if not invoice_value_mismatch(inv)
        and not getattr(inv, "is_reverse_charge", False)
        and not (getattr(inv, "ecommerce_operator_gstin", None) or "").strip()  # BB-000707 SUPECOM
    ]
    # BB-000361: notes must be gated the same way — a mismatched note is
    # already excluded from cdnr/cdnur above, so it must not still move totals.
    # BB-000696: notes on sales RCM parents must not move regular outward liability.
    def _note_parent_is_sales_rcm(note) -> bool:
        parent = getattr(note, "sales_invoice", None) or getattr(note, "invoice", None)
        return bool(parent and getattr(parent, "is_reverse_charge", False))

    matched_credit_notes = [
        n for n in credit_notes
        if not invoice_value_mismatch(n) and not _note_parent_is_sales_rcm(n)
    ]
    matched_debit_notes = [
        n for n in debit_notes
        if not invoice_value_mismatch(n) and not _note_parent_is_sales_rcm(n)
    ]
    outward_taxable = sum((inv.taxable_total for inv in matched_invoices), Decimal("0"))
    outward_cgst = sum((inv.cgst_total for inv in matched_invoices), Decimal("0"))
    outward_sgst = sum((inv.sgst_total for inv in matched_invoices), Decimal("0"))
    outward_igst = sum((inv.igst_total for inv in matched_invoices), Decimal("0"))
    outward_cess = sum((Decimal(str(getattr(inv, "cess_total", 0) or 0)) for inv in matched_invoices), Decimal("0"))
    for note in matched_credit_notes:
        outward_taxable -= note.taxable_total
        outward_cgst -= note.cgst_total
        outward_sgst -= note.sgst_total
        outward_igst -= note.igst_total
        outward_cess -= Decimal(str(getattr(note, "cess_total", 0) or 0))
    for note in matched_debit_notes:
        outward_taxable += note.taxable_total
        outward_cgst += note.cgst_total
        outward_sgst += note.sgst_total
        outward_igst += note.igst_total
        outward_cess += Decimal(str(getattr(note, "cess_total", 0) or 0))

    section_taxable = (
        sum(Decimal(r["taxable_value"]) for r in b2b)
        + sum(Decimal(r["taxable_value"]) for r in b2cl)
        + sum(Decimal(r["taxable_value"]) for r in b2cs)
        + sum(Decimal(r["taxable_value"]) for r in exp)
        + sum(Decimal(r["taxable_value"]) for r in sez)
        + nil_bucket["taxable_value"]
        - sum(Decimal(r["taxable_value"]) for r in cdnr if r["note_kind"] == "CREDIT")
        - sum(Decimal(r["taxable_value"]) for r in cdnur if r["note_kind"] == "CREDIT")
        + sum(Decimal(r["taxable_value"]) for r in cdnr if r["note_kind"] == "DEBIT")
        + sum(Decimal(r["taxable_value"]) for r in cdnur if r["note_kind"] == "DEBIT")
    )

    # Wave 17B: amendments from filing identity audit trail when present.
    amendments = _gstr1_amendments(company, date_from, date_to, company_gstin_id=stamp_id)

    footing_delta = outward_taxable - section_taxable
    footing_mismatch = abs(footing_delta) > Decimal("0.01")
    if footing_mismatch:
        issues.append({
            "code": "OUTWARD_FOOTING_MISMATCH",
            "severity": "warning",
            "document_type": "gstr1",
            "document_id": None,
            "number": period,
            "message": (
                f"Header outward_taxable {_money(outward_taxable)} differs from "
                f"section_net_taxable {_money(section_taxable)} "
                f"(delta {_money(footing_delta)})."
            ),
        })

    totals = {
        "outward_taxable": _money(outward_taxable),
        "outward_cgst": _money(outward_cgst),
        "outward_sgst": _money(outward_sgst),
        "outward_igst": _money(outward_igst),
        "outward_cess": _money(outward_cess),
        "section_net_taxable": _money(section_taxable),
        "footing_discrepancy": footing_mismatch,
        "footing_delta": _money(footing_delta) if footing_mismatch else "0.00",
        "b2b": _sum_fields(b2b, "taxable_value", "cgst", "sgst", "igst", "cess"),
        "b2cl": _sum_fields(b2cl, "taxable_value", "igst", "cess"),
        "b2cs": _sum_fields(b2cs, "taxable_value", "cgst", "sgst", "igst", "cess"),
        "exp": _sum_fields(exp, "taxable_value", "igst", "cess"),
        "sez": _sum_fields(sez, "taxable_value", "cgst", "sgst", "igst", "cess"),
        "cdnr": _sum_fields(cdnr, "taxable_value", "cgst", "sgst", "igst", "cess"),
        "cdnur": _sum_fields(cdnur, "taxable_value", "cgst", "sgst", "igst", "cess"),
    }

    return {
        "return_type": "GSTR-1",
        "builder_version": BUILDER_VERSION_GSTR1,
        "period": period,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "company_gstin_id": stamp_id,
        "company": {
            "name": company.name,
            "gstin": company.gstin or "",
            "state": company.state or "",
        },
        "b2b": sorted(b2b, key=lambda r: (r["invoice_date"], r["invoice_number"], r["rate"])),
        "b2cl": sorted(b2cl, key=lambda r: (r["invoice_date"], r["invoice_number"], r["rate"])),
        "b2cs": b2cs,
        "exp": sorted(exp, key=lambda r: (r["invoice_date"], r["invoice_number"], r["rate"])),
        "sez": sorted(sez, key=lambda r: (r["invoice_date"], r["invoice_number"], r["rate"])),
        "cdnr": cdnr,
        "cdnur": cdnur,
        "hsn": hsn,
        "nil": {
            "taxable_value": _money(nil_bucket["taxable_value"]),
            "nil_rated": _money(nil_bucket["taxable_value"]),
            "exempt": "0.00",
            "non_gst": "0.00",
            "aid_kind": "nil_unsplit",
            "note": (
                "0% GST line taxable (including mixed-rate invoices) accumulates here as "
                "nil-rated aid — exempt vs zero-rated vs non-GST is not split (BB-000621 / GSTR-08)."
            ),
        },
        "amendments": amendments,
        "docs": docs,
        "doc": doc_table,
        "at": at_table,
        "atadj": atadj_table,
        "txpd": txpd_table,
        "supecom": {
            "supported": bool(supecom_rows),
            "table": "15",
            "15A": [r for r in supecom_rows if r.get("section") == "15A"],
            "15B": [r for r in supecom_rows if r.get("section") == "15B"],
            "rows": supecom_rows,
            "note": (
                "Table 15 aid: 15A = supplies through e-commerce to registered buyers; "
                "15B = unregistered. Do not file SUPECOM from this worksheet without CA review."
            ),
        },
        "totals": totals,
        "issues": issues,
        "disclaimer": "Offline export for CA review — not a GSTN portal upload file.",
    }


def _gstr1_doc_table(company, date_from, date_to, invoices, cancelled_inv, credit_notes, debit_notes) -> list[dict]:
    """GSTR-1 DOC: invoice series summary (prefix from document number)."""
    from collections import defaultdict

    series: dict[str, dict] = defaultdict(lambda: {"from": "", "to": "", "total": 0, "cancelled": 0})
    for inv in invoices:
        num = inv.number or ""
        prefix = "".join(ch for ch in num if not ch.isdigit()) or "INV"
        bucket = series[prefix]
        bucket["total"] += 1
        if not bucket["from"] or num < bucket["from"]:
            bucket["from"] = num
        if not bucket["to"] or num > bucket["to"]:
            bucket["to"] = num
    rows = [
        {
            "nature": "Invoices for outward supply",
            "sr_from": vals["from"],
            "sr_to": vals["to"],
            "total_number": vals["total"],
            "cancelled": 0,
            "series": prefix,
        }
        for prefix, vals in sorted(series.items())
    ]
    rows.append({
        "nature": "Cancelled invoices",
        "sr_from": "",
        "sr_to": "",
        "total_number": cancelled_inv,
        "cancelled": cancelled_inv,
        "series": "",
    })
    rows.append({
        "nature": "Credit notes",
        "sr_from": "",
        "sr_to": "",
        "total_number": len(credit_notes),
        "cancelled": 0,
        "series": "",
    })
    rows.append({
        "nature": "Debit notes",
        "sr_from": "",
        "sr_to": "",
        "total_number": len(debit_notes),
        "cancelled": 0,
        "series": "",
    })
    return rows


def _gstr1_at_table(company, date_from, date_to, *, company_gstin_id=None) -> list[dict]:
    """GSTR-1 AT aid: unallocated customer receipts in period (advances).

    Advances are company-level until allocated to a stamped invoice. When a
    non-primary ``company_gstin_id`` is requested, return empty (ATADJ covers
    stamp-scoped allocations). Primary / unset stamp includes all unallocated.
    """
    from django.db.models import Sum as DjSum

    from accounts.models import CompanyGstin
    from core.services.billing import extract_state_code
    from payments.models import CustomerReceipt, PaymentAllocation, ReceiptStatus

    if company_gstin_id is not None:
        primary = CompanyGstin.objects.filter(
            company=company, is_primary=True, is_active=True
        ).first()
        if primary is not None and primary.id != company_gstin_id:
            return []

    rows = []
    receipts = CustomerReceipt.objects.filter(
        company=company,
        receipt_date__gte=date_from,
        receipt_date__lte=date_to,
        status=ReceiptStatus.POSTED,
    ).select_related("customer")
    for rec in receipts:
        allocated = (
            PaymentAllocation.objects.filter(receipt=rec, reversed_at__isnull=True).aggregate(t=DjSum("amount"))["t"]
            or Decimal("0")
        )
        unalloc = Decimal(str(rec.amount or 0)) - Decimal(str(allocated or 0))
        if unalloc <= 0:
            continue
        customer = rec.customer
        pos = (
            extract_state_code(getattr(customer, "gstin", "") or "")
            or extract_state_code(getattr(customer, "state", "") or "")
            or ""
        )
        rows.append({
            "receipt_number": rec.number,
            "receipt_date": rec.receipt_date.isoformat() if rec.receipt_date else "",
            "place_of_supply": pos,
            "rate": "0.00",
            "cgst": "0.00",
            "sgst": "0.00",
            "igst": "0.00",
            "gross_advance": _money(unalloc),
            "tax_status": "rate_unknown",
            "note": "Unallocated receipt is an advance aid pending CA rate — not GSTN AT tax.",
            "aid_kind": "unallocated_receipt",
            "honesty": "rate_unknown_do_not_file_as_at",
        })
    return rows


def _gstr1_atadj_table(company, date_from, date_to, *, company_gstin_id=None) -> list[dict]:
    """BB-000621: ATADJ aid when advances are allocated to invoices."""
    from payments.models import PaymentAllocation

    rows = []
    allocs = (
        PaymentAllocation.objects.filter(
            company=company,
            receipt__isnull=False,
            sales_invoice__isnull=False,
            reversed_at__isnull=True,
            sales_invoice__invoice_date__gte=date_from,
            sales_invoice__invoice_date__lte=date_to,
        )
        .select_related("receipt", "sales_invoice", "receipt__customer")
    )
    if company_gstin_id is not None:
        allocs = allocs.filter(sales_invoice__company_gstin_id=company_gstin_id)
    for alloc in allocs:
        rec = alloc.receipt
        inv = alloc.sales_invoice
        if rec is None or inv is None:
            continue
        if rec.receipt_date and rec.receipt_date > inv.invoice_date:
            continue
        rows.append({
            "receipt_number": rec.number,
            "receipt_date": rec.receipt_date.isoformat() if rec.receipt_date else "",
            "invoice_number": inv.number,
            "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else "",
            "adjusted_amount": _money(alloc.amount),
            "aid_kind": "atadj_allocation",
            "note": "Advance allocation aid — rate unknown; do not double-count with AT.",
        })
    return rows


def _gstr1_txpd_table(company, date_from, date_to, *, company_gstin_id=None) -> list[dict]:
    """TXPD aid mirrors AT advances — tax rate unknown until invoiced."""
    at_rows = _gstr1_at_table(company, date_from, date_to, company_gstin_id=company_gstin_id)
    if not at_rows:
        return [{
            "aid_kind": "txpd_none",
            "supported": True,
            "note": "No unallocated advances in period — TXPD is nil for this aid.",
        }]
    return [
        {
            **row,
            "aid_kind": "txpd_from_at",
            "note": (
                "TXPD aid copies unallocated advances (AT). Tax rate is unknown — "
                "do not file as GSTN TXPD without CA rate split."
            ),
        }
        for row in at_rows
    ]


def _gstr1_amendments(company, date_from: date, date_to: date, *, company_gstin_id=None) -> list[dict]:
    """Build amendment rows from AuditEvent filing-identity changes when available."""
    from core.models import AuditEvent
    from sales.models import SalesInvoice

    qs = AuditEvent.objects.filter(
        company=company,
        entity_type="salesinvoice",
        description__icontains="amend_filing_identity",
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    ).order_by("created_at")[:500]
    allowed_ids = None
    if company_gstin_id is not None:
        allowed_ids = set(
            SalesInvoice.objects.filter(
                company=company, company_gstin_id=company_gstin_id
            ).values_list("id", flat=True)
        )
    rows = []
    for row in qs:
        if allowed_ids is not None and row.entity_id not in allowed_ids:
            continue
        meta = row.metadata if isinstance(getattr(row, "metadata", None), dict) else {}
        rows.append({
            "document_id": row.entity_id,
            "changed_at": row.created_at.isoformat() if row.created_at else "",
            "old_gstin": meta.get("old_gstin", ""),
            "new_gstin": meta.get("new_gstin", ""),
            "old_pos": meta.get("old_pos", ""),
            "new_pos": meta.get("new_pos", ""),
            "aid_kind": "amendment_audit",
        })
    return rows


def build_gstr3b(company, period: str, gstr1: dict | None = None, *, company_gstin=None) -> dict:
    assert_not_composition_for_regular_returns(company)
    date_from, date_to = parse_period(period)
    if gstr1 is None:
        gstr1 = build_gstr1(company, period, company_gstin=company_gstin)
    # BB-000697: never resolve stamp from []; reuse GSTR-1 stamp or explicit param.
    stamp_id = gstr1.get("company_gstin_id")
    if stamp_id is None and company_gstin is not None:
        stamp_id = getattr(company_gstin, "id", company_gstin)
    if stamp_id is None:
        stamp_id = _resolve_filing_gstin_id(
            company,
            gstr1.get("_stamp_invoices") or [],
            company_gstin=company_gstin,
        )
    purchases = list(_gst_purchase_invoices(company, date_from, date_to, company_gstin_id=stamp_id))
    purchase_cns = list(_gst_purchase_credit_notes(company, date_from, date_to, company_gstin_id=stamp_id))
    purchase_dns = list(_gst_purchase_debit_notes(company, date_from, date_to, company_gstin_id=stamp_id))
    purchase_cns_rcm = list(_gst_purchase_credit_notes_rcm(company, date_from, date_to, company_gstin_id=stamp_id))
    purchase_dns_rcm = list(_gst_purchase_debit_notes_rcm(company, date_from, date_to, company_gstin_id=stamp_id))

    non_rcm = [p for p in purchases if not getattr(p, "is_reverse_charge", False)]
    rcm = [p for p in purchases if getattr(p, "is_reverse_charge", False)]
    itc_eligible = [
        p
        for p in non_rcm
        if (getattr(p, "itc_eligibility", "UNREVIEWED") or "UNREVIEWED") == "CLAIMABLE"
    ]

    def _note_claimable(note) -> bool:
        inv = getattr(note, "purchase_invoice", None)
        return inv is not None and (getattr(inv, "itc_eligibility", "UNREVIEWED") or "UNREVIEWED") == "CLAIMABLE"

    inward_taxable = sum((inv.taxable_total for inv in non_rcm), Decimal("0"))
    inward_cgst = sum((inv.cgst_total for inv in itc_eligible), Decimal("0"))
    inward_sgst = sum((inv.sgst_total for inv in itc_eligible), Decimal("0"))
    inward_igst = sum((inv.igst_total for inv in itc_eligible), Decimal("0"))
    inward_cess = sum(
        (Decimal(str(getattr(inv, "cess_total", 0) or 0)) for inv in itc_eligible),
        Decimal("0"),
    )
    for note in purchase_cns:
        inward_taxable -= note.taxable_total
        if _note_claimable(note):
            inward_cgst -= note.cgst_total
            inward_sgst -= note.sgst_total
            inward_igst -= note.igst_total
            inward_cess -= Decimal(str(getattr(note, "cess_total", 0) or 0))
    for note in purchase_dns:
        inward_taxable += note.taxable_total
        if _note_claimable(note):
            inward_cgst += note.cgst_total
            inward_sgst += note.sgst_total
            inward_igst += note.igst_total
            inward_cess += Decimal(str(getattr(note, "cess_total", 0) or 0))

    rcm_taxable = sum(
        (Decimal(str(getattr(p, "rcm_taxable", None) or p.taxable_total or 0)) for p in rcm),
        Decimal("0"),
    )
    rcm_cgst = sum((Decimal(str(getattr(p, "rcm_cgst", 0) or 0)) for p in rcm), Decimal("0"))
    rcm_sgst = sum((Decimal(str(getattr(p, "rcm_sgst", 0) or 0)) for p in rcm), Decimal("0"))
    rcm_igst = sum((Decimal(str(getattr(p, "rcm_igst", 0) or 0)) for p in rcm), Decimal("0"))
    rcm_cess = sum((Decimal(str(getattr(p, "rcm_cess", 0) or 0)) for p in rcm), Decimal("0"))
    # BB-000336: RCM credit/debit notes reduce/increase the RCM liability itself
    # (3.1(d)) — they must never net into the non-RCM ITC block above.
    for note in purchase_cns_rcm:
        rcm_taxable -= Decimal(str(getattr(note, "rcm_taxable", None) or note.taxable_total or 0))
        rcm_cgst -= Decimal(str(getattr(note, "rcm_cgst", 0) or 0))
        rcm_sgst -= Decimal(str(getattr(note, "rcm_sgst", 0) or 0))
        rcm_igst -= Decimal(str(getattr(note, "rcm_igst", 0) or 0))
        rcm_cess -= Decimal(str(getattr(note, "rcm_cess", 0) or getattr(note, "cess_total", 0) or 0))
    for note in purchase_dns_rcm:
        rcm_taxable += Decimal(str(getattr(note, "rcm_taxable", None) or note.taxable_total or 0))
        rcm_cgst += Decimal(str(getattr(note, "rcm_cgst", 0) or 0))
        rcm_sgst += Decimal(str(getattr(note, "rcm_sgst", 0) or 0))
        rcm_igst += Decimal(str(getattr(note, "rcm_igst", 0) or 0))
        rcm_cess += Decimal(str(getattr(note, "rcm_cess", 0) or getattr(note, "cess_total", 0) or 0))

    outward = gstr1["totals"]
    itc_available = {
        "igst": _money(inward_igst),
        "cgst": _money(inward_cgst),
        "sgst": _money(inward_sgst),
        "cess": _money(inward_cess),
        "total_tax": _money(inward_igst + inward_cgst + inward_sgst + inward_cess),
    }
    # BB-000279: RCM books also post Dr Input ITC — surface as provisional until 2B.
    rcm_itc_provisional = {
        "label": "provisional",
        "provisional": True,
        "claimable": False,
        "count": len(rcm),
        "igst": _money(rcm_igst),
        "cgst": _money(rcm_cgst),
        "sgst": _money(rcm_sgst),
        "cess": _money(rcm_cess),
        "total_tax": _money(rcm_igst + rcm_cgst + rcm_sgst + rcm_cess),
        "note": (
            "Provisional RCM Input ITC from books (matches RCM liability above) — "
            "not GSTR-2B matched. Do not auto-claim."
        ),
    }
    manual_review = [
        {
            "section": "4(A)(5) ITC on imports",
            "status": "manual_review",
            "note": "Import of goods/services ITC is not tracked — manual review required.",
        },
        {
            "section": "4(B) ITC reversed / ineligible",
            "status": "manual_review",
            "note": (
                "Purchase/2B ITC eligibility flags exclude ineligible/reversed from claimable ITC. "
                "Confirm Sec 17 / other reversals offline."
            ),
        },
    ]
    if not rcm:
        manual_review.insert(
            0,
            {
                "section": "3.1(d) Inward supplies liable to reverse charge",
                "status": "manual_review",
                "note": "No RCM-flagged purchases in period — confirm none offline.",
            },
        )

    # Wave 16D: claimable ITC only from matched GSTR-2B rows.
    from reporting.gstr2b import claimable_itc_from_2b

    itc_2b = claimable_itc_from_2b(company, period)
    from reporting.models import Gstr2bIngest

    has_2b_rows = Gstr2bIngest.objects.filter(company=company, period=period).exists()
    has_2b = has_2b_rows and (
        Decimal(str(itc_2b.get("cgst") or 0))
        + Decimal(str(itc_2b.get("sgst") or 0))
        + Decimal(str(itc_2b.get("igst") or 0))
        + Decimal(str(itc_2b.get("cess") or 0))
    ) > 0
    itc_block = {
        "provisional": not has_2b,
        "claimable": has_2b,
        "available_from_purchases": itc_available,
        "from_gstr2b_matched": {
            "igst": _money(itc_2b["igst"]),
            "cgst": _money(itc_2b["cgst"]),
            "sgst": _money(itc_2b["sgst"]),
            "cess": _money(itc_2b.get("cess") or 0),
            "total_tax": _money(
                itc_2b["igst"] + itc_2b["cgst"] + itc_2b["sgst"] + Decimal(str(itc_2b.get("cess") or 0))
            ),
            "claimable": has_2b,
            "source": itc_2b["source"],
        },
        "rcm_provisional": rcm_itc_provisional,
        "manual_review": manual_review,
        "note": (
            "ITC claimable only after GSTR-2B match (Wave 16D). "
            "Books provisional ITC is informational until matched."
            if not has_2b
            else "ITC claimable from matched GSTR-2B rows."
        ),
    }

    # Table 3.1 (a)/(b)/(c)/(d) split from GSTR-1 sections (honest labels).
    def _sec_money(sec: dict | None, key: str) -> Decimal:
        if not sec:
            return Decimal("0")
        return Decimal(str(sec.get(key, "0") or 0))

    b2b_t = outward.get("b2b") or {}
    b2cl_t = outward.get("b2cl") or {}
    b2cs_t = outward.get("b2cs") or {}
    exp_t = outward.get("exp") or {}
    sez_t = outward.get("sez") or {}
    nil_payload = gstr1.get("nil") or {}

    # Signed note nets: export-typed CDNUR → zero-rated; else taxable (a).
    a_note_taxable = Decimal("0")
    a_note_igst = Decimal("0")
    a_note_cgst = Decimal("0")
    a_note_sgst = Decimal("0")
    a_note_cess = Decimal("0")
    b_note_taxable = Decimal("0")
    b_note_igst = Decimal("0")
    b_note_cgst = Decimal("0")
    b_note_sgst = Decimal("0")
    b_note_cess = Decimal("0")
    for row in gstr1.get("cdnr") or []:
        sign = Decimal("-1") if row.get("note_kind") == "CREDIT" else Decimal("1")
        a_note_taxable += sign * Decimal(str(row.get("taxable_value") or 0))
        a_note_igst += sign * Decimal(str(row.get("igst") or 0))
        a_note_cgst += sign * Decimal(str(row.get("cgst") or 0))
        a_note_sgst += sign * Decimal(str(row.get("sgst") or 0))
        a_note_cess += sign * Decimal(str(row.get("cess") or 0))
    for row in gstr1.get("cdnur") or []:
        sign = Decimal("-1") if row.get("note_kind") == "CREDIT" else Decimal("1")
        supply = (row.get("supply_type") or "").upper()
        bucket_taxable = sign * Decimal(str(row.get("taxable_value") or 0))
        bucket_igst = sign * Decimal(str(row.get("igst") or 0))
        bucket_cgst = sign * Decimal(str(row.get("cgst") or 0))
        bucket_sgst = sign * Decimal(str(row.get("sgst") or 0))
        bucket_cess = sign * Decimal(str(row.get("cess") or 0))
        if supply in ("SEZWP", "SEZWOP", "EXPWP", "EXPWOP", "DEXP"):
            b_note_taxable += bucket_taxable
            b_note_igst += bucket_igst
            b_note_cgst += bucket_cgst
            b_note_sgst += bucket_sgst
            b_note_cess += bucket_cess
        else:
            a_note_taxable += bucket_taxable
            a_note_igst += bucket_igst
            a_note_cgst += bucket_cgst
            a_note_sgst += bucket_sgst
            a_note_cess += bucket_cess

    # (a) taxable other than zero-rated: B2B/B2CL/B2CS ± non-export notes
    a_taxable_value = (
        _sec_money(b2b_t, "taxable_value")
        + _sec_money(b2cl_t, "taxable_value")
        + _sec_money(b2cs_t, "taxable_value")
        + a_note_taxable
    )
    a_igst = (
        _sec_money(b2b_t, "igst")
        + _sec_money(b2cl_t, "igst")
        + _sec_money(b2cs_t, "igst")
        + a_note_igst
    )
    a_cgst = _sec_money(b2b_t, "cgst") + _sec_money(b2cs_t, "cgst") + a_note_cgst
    a_sgst = _sec_money(b2b_t, "sgst") + _sec_money(b2cs_t, "sgst") + a_note_sgst
    a_cess = (
        _sec_money(b2b_t, "cess")
        + _sec_money(b2cl_t, "cess")
        + _sec_money(b2cs_t, "cess")
        + a_note_cess
    )

    # (b) zero-rated (exports / SEZ)
    b_taxable_value = (
        _sec_money(exp_t, "taxable_value") + _sec_money(sez_t, "taxable_value") + b_note_taxable
    )
    b_igst = _sec_money(exp_t, "igst") + _sec_money(sez_t, "igst") + b_note_igst
    b_cgst = _sec_money(sez_t, "cgst") + b_note_cgst
    b_sgst = _sec_money(sez_t, "sgst") + b_note_sgst
    b_cess = _sec_money(exp_t, "cess") + _sec_money(sez_t, "cess") + b_note_cess

    # (c) nil-rated / exempt
    c_taxable_value = Decimal(str(nil_payload.get("taxable_value") or 0))
    # (d) non-GST outward
    d_taxable_value = Decimal(str(nil_payload.get("non_gst") or 0))

    # Table 3.2 — inter-state supplies made to unregistered persons (B2CL + IGST B2CS).
    table_32_by_pos: dict[str, dict] = {}
    for row in gstr1.get("b2cl") or []:
        pos = row.get("place_of_supply") or ""
        bucket = table_32_by_pos.setdefault(
            pos,
            {"place_of_supply": pos, "taxable_value": Decimal("0"), "igst": Decimal("0")},
        )
        bucket["taxable_value"] += Decimal(str(row.get("taxable_value") or 0))
        bucket["igst"] += Decimal(str(row.get("igst") or 0))
    for row in gstr1.get("b2cs") or []:
        igst = Decimal(str(row.get("igst") or 0))
        if igst <= 0:
            continue
        pos = row.get("place_of_supply") or ""
        bucket = table_32_by_pos.setdefault(
            pos,
            {"place_of_supply": pos, "taxable_value": Decimal("0"), "igst": Decimal("0")},
        )
        bucket["taxable_value"] += Decimal(str(row.get("taxable_value") or 0))
        bucket["igst"] += igst
    table_32 = [
        {
            "place_of_supply": pos,
            "taxable_value": _money(vals["taxable_value"]),
            "igst": _money(vals["igst"]),
        }
        for pos, vals in sorted(table_32_by_pos.items())
        if vals["taxable_value"] or vals["igst"]
    ]

    return {
        "return_type": "GSTR-3B",
        "builder_version": BUILDER_VERSION_GSTR3B,
        "period": period,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "company": gstr1["company"],
        "outward_supplies": {
            "a_taxable_other_than_zero_rated": {
                "label": "3.1(a) Outward taxable supplies (other than zero rated, nil rated and exempted)",
                "taxable_value": _money(a_taxable_value),
                "igst": _money(a_igst),
                "cgst": _money(a_cgst),
                "sgst": _money(a_sgst),
                "cess": _money(a_cess),
            },
            "b_zero_rated": {
                "label": "3.1(b) Outward taxable supplies (zero rated)",
                "taxable_value": _money(b_taxable_value),
                "igst": _money(b_igst),
                "cgst": _money(b_cgst),
                "sgst": _money(b_sgst),
                "cess": _money(b_cess),
            },
            "c_nil_rated_exempt": {
                "label": "3.1(c) Other outward supplies (nil rated, exempted)",
                "taxable_value": _money(c_taxable_value),
                "igst": "0.00",
                "cgst": "0.00",
                "sgst": "0.00",
                "cess": "0.00",
            },
            "d_non_gst": {
                "label": "3.1(e) Non-GST outward supplies",
                "taxable_value": _money(d_taxable_value),
                "igst": "0.00",
                "cgst": "0.00",
                "sgst": "0.00",
                "cess": "0.00",
                "note": "Labeled 3.1(e) per GSTN form; (d) on the form is inward RCM.",
            },
            # Compatibility rollup (sum of a–d outward buckets).
            "taxable_value": outward["outward_taxable"],
            "igst": outward["outward_igst"],
            "cgst": outward["outward_cgst"],
            "sgst": outward["outward_sgst"],
            "cess": outward.get("outward_cess", "0.00"),
        },
        "table_3_2_inter_state_unregistered": {
            "label": "3.2 Supplies made to unregistered persons (inter-state)",
            "rows": table_32,
            "taxable_value": _money(sum((r["taxable_value"] for r in table_32_by_pos.values()), Decimal("0"))),
            "igst": _money(sum((r["igst"] for r in table_32_by_pos.values()), Decimal("0"))),
        },
        "inward_supplies": {
            "from_purchases": {
                "count": len(non_rcm),
                "taxable_value": _money(inward_taxable),
                "igst": _money(inward_igst),
                "cgst": _money(inward_cgst),
                "sgst": _money(inward_sgst),
                "cess": _money(inward_cess),
            },
            "reverse_charge": {
                "count": len(rcm),
                "taxable_value": _money(rcm_taxable),
                "igst": _money(rcm_igst),
                "cgst": _money(rcm_cgst),
                "sgst": _money(rcm_sgst),
                "cess": _money(rcm_cess),
            },
        },
        "itc": itc_block,
        "tax_on_advances": {
            "txpd": gstr1.get("txpd") or [],
            "at": gstr1.get("at") or [],
            "atadj": gstr1.get("atadj") or [],
            "note": (
                "TXPD aid is copied from GSTR-1 unallocated advances (AT). "
                "Tax rate is unknown — do not file as GSTN TXPD without CA rate split."
            ),
        },
        "tax_payable_summary": {
            "outward_tax": _money(
                Decimal(outward["outward_igst"])
                + Decimal(outward["outward_cgst"])
                + Decimal(outward["outward_sgst"])
                + Decimal(outward.get("outward_cess", "0") or 0)
            ),
            "itc_available": itc_available["total_tax"],
            "itc_provisional": not has_2b,
            "itc_claimable": has_2b,
            # Wave 16D: subtract matched 2B ITC when present; else do not subtract provisional.
            "net_payable_hint": _money(
                Decimal(outward["outward_igst"])
                + Decimal(outward["outward_cgst"])
                + Decimal(outward["outward_sgst"])
                + Decimal(outward.get("outward_cess", "0") or 0)
                + (rcm_cgst + rcm_sgst + rcm_igst + rcm_cess)
                - (
                    itc_2b["igst"] + itc_2b["cgst"] + itc_2b["sgst"] + Decimal(str(itc_2b.get("cess") or 0))
                    if has_2b
                    else Decimal("0")
                )
            ),
            "note": (
                "Net payable subtracts matched GSTR-2B ITC when present; "
                "otherwise excludes provisional books ITC."
            ),
        },
        "issues": gstr1.get("issues", []),
        "disclaimer": "Offline export for CA review — not a GSTN portal upload file.",
    }


def build_gstr9(company, fy_label: str, *, company_gstin=None) -> dict:
    """
    FY outward + minimal inward aid (not a full GSTR-9 engine).
    fy_label like '2025-26' (April–March when fy_start_month=4).
    Prefer summing monthly GSTR-1 snapshots; fallback re-agg.
    BB-000698: company_gstin scopes monthly builders and purchase ITC.
    """
    assert_not_composition_for_regular_returns(company)
    try:
        start_y, end_yy = fy_label.split("-")
        start_year = int(start_y)
        end_year = int(end_yy) if len(end_yy) == 4 else 2000 + int(end_yy)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid FY '{fy_label}'. Expected e.g. 2025-26.") from exc

    fy_start = company.fy_start_month or 4
    months = []
    y, m = start_year, fy_start
    for _ in range(12):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1

    # Resolve stamp once for the FY (empty preview + explicit param).
    stamp_id = _resolve_filing_gstin_id(company, [], company_gstin=company_gstin) if company_gstin is not None else None
    if stamp_id is None and company_gstin is None:
        # Prefer primary when multi-GSTIN without explicit param — still scoped.
        from accounts.models import CompanyGstin

        primary = CompanyGstin.objects.filter(company=company, is_primary=True, is_active=True).first()
        stamp_id = primary.id if primary else None

    monthly = []
    outward_taxable = Decimal("0")
    outward_tax = Decimal("0")
    inward_taxable = Decimal("0")
    inward_tax = Decimal("0")
    hsn_fy: dict[tuple, dict] = defaultdict(
        lambda: {
            "quantity": Decimal("0"),
            "taxable_value": Decimal("0"),
            "cgst": Decimal("0"),
            "sgst": Decimal("0"),
            "igst": Decimal("0"),
            "cess": Decimal("0"),
        }
    )
    hsn_inward = new_hsn_buckets()
    nil_fy = Decimal("0")
    itc6_taxable = Decimal("0")
    itc6_cgst = Decimal("0")
    itc6_sgst = Decimal("0")
    itc6_igst = Decimal("0")
    itc6_cess = Decimal("0")
    itc7_taxable = Decimal("0")
    itc7_cgst = Decimal("0")
    itc7_sgst = Decimal("0")
    itc7_igst = Decimal("0")
    itc7_cess = Decimal("0")
    itc8a_tax = Decimal("0")
    itc8_import = Decimal("0")
    for period in months:
        snap = (
            GstReturnSnapshot.objects.filter(
                company=company,
                return_type=GstReturnSnapshot.ReturnType.GSTR1,
                period=period,
            )
            .order_by("-generated_at")
            .first()
        )
        period_ctrl = GstReturnPeriod.objects.filter(company=company, period=period).first()
        dirty = bool(period_ctrl and period_ctrl.dirty_after_snapshot)
        # Prefer snapshot only when clean; rebuild live when period was dirtied.
        if snap and stamp_id is None and not dirty:
            payload = snap.payload
        else:
            payload = build_gstr1(company, period, company_gstin=stamp_id or company_gstin)
        totals = payload.get("totals", {})
        nil_fy += Decimal(str((payload.get("nil") or {}).get("taxable_value", "0") or 0))
        for hrow in payload.get("hsn", []) or []:
            key = (hrow.get("hsn", "NA"), str(hrow.get("rate", "0")), hrow.get("uqc", "OTH"))
            hsn_fy[key]["quantity"] += Decimal(str(hrow.get("quantity", "0") or 0))
            hsn_fy[key]["taxable_value"] += Decimal(str(hrow.get("taxable_value", "0") or 0))
            hsn_fy[key]["cgst"] += Decimal(str(hrow.get("cgst", "0") or 0))
            hsn_fy[key]["sgst"] += Decimal(str(hrow.get("sgst", "0") or 0))
            hsn_fy[key]["igst"] += Decimal(str(hrow.get("igst", "0") or 0))
            hsn_fy[key]["cess"] += Decimal(str(hrow.get("cess", "0") or 0))
        ot = Decimal(str(totals.get("outward_taxable", "0")))
        tax = (
            Decimal(str(totals.get("outward_cgst", "0")))
            + Decimal(str(totals.get("outward_sgst", "0")))
            + Decimal(str(totals.get("outward_igst", "0")))
        )
        outward_taxable += ot
        outward_tax += tax

        date_from, date_to = parse_period(period)
        purchases = list(_gst_purchase_invoices(company, date_from, date_to, company_gstin_id=stamp_id))
        for inv in purchases:
            if getattr(inv, "is_reverse_charge", False):
                continue
            for item in inv.items.all():
                accumulate_hsn_line(hsn_inward, item)
        non_rcm = [p for p in purchases if not getattr(p, "is_reverse_charge", False)]
        for inv in non_rcm:
            if getattr(inv, "itc_eligibility", "") != PurchaseInvoice.ItcEligibility.CLAIMABLE:
                continue
            itc6_taxable += Decimal(str(inv.taxable_total or 0))
            itc6_cgst += Decimal(str(inv.cgst_total or 0))
            itc6_sgst += Decimal(str(inv.sgst_total or 0))
            itc6_igst += Decimal(str(inv.igst_total or 0))
            itc6_cess += Decimal(str(getattr(inv, "cess_total", 0) or 0))
        from reporting.models import Gstr2bIngest

        for row in Gstr2bIngest.objects.filter(company=company, period=period):
            itc8a_tax += (
                Decimal(str(row.cgst or 0))
                + Decimal(str(row.sgst or 0))
                + Decimal(str(row.igst or 0))
                + Decimal(str(getattr(row, "cess", 0) or 0))
            )
        for inv in non_rcm:
            supplier_gstin = (getattr(getattr(inv, "supplier", None), "gstin", None) or "").strip()
            notes = (getattr(inv, "notes", "") or "").upper()
            if (not supplier_gstin and Decimal(str(inv.igst_total or 0)) > 0) or "IMPORT" in notes:
                itc8_import += Decimal(str(inv.igst_total or 0)) + Decimal(str(getattr(inv, "cess_total", 0) or 0))
        period_inward_taxable = sum((inv.taxable_total for inv in non_rcm), Decimal("0"))
        period_inward_tax = sum(
            (
                Decimal(str(inv.cgst_total or 0))
                + Decimal(str(inv.sgst_total or 0))
                + Decimal(str(inv.igst_total or 0))
                for inv in non_rcm
            ),
            Decimal("0"),
        )
        purchase_cns = list(_gst_purchase_credit_notes(company, date_from, date_to, company_gstin_id=stamp_id))
        purchase_dns = list(_gst_purchase_debit_notes(company, date_from, date_to, company_gstin_id=stamp_id))
        for note in purchase_cns:
            parent = getattr(note, "purchase_invoice", None)
            if parent is not None and getattr(parent, "itc_eligibility", "") == PurchaseInvoice.ItcEligibility.CLAIMABLE:
                itc7_taxable += Decimal(str(note.taxable_total or 0))
                itc7_cgst += Decimal(str(note.cgst_total or 0))
                itc7_sgst += Decimal(str(note.sgst_total or 0))
                itc7_igst += Decimal(str(note.igst_total or 0))
                itc7_cess += Decimal(str(getattr(note, "cess_total", 0) or 0))
            period_inward_taxable -= note.taxable_total
            period_inward_tax -= (
                Decimal(str(note.cgst_total or 0))
                + Decimal(str(note.sgst_total or 0))
                + Decimal(str(note.igst_total or 0))
            )
        for note in purchase_dns:
            period_inward_taxable += note.taxable_total
            period_inward_tax += (
                Decimal(str(note.cgst_total or 0))
                + Decimal(str(note.sgst_total or 0))
                + Decimal(str(note.igst_total or 0))
            )
        inward_taxable += period_inward_taxable
        inward_tax += period_inward_tax

        monthly.append({
            "period": period,
            "outward_taxable": _money(ot),
            "outward_tax": _money(tax),
            "inward_taxable": _money(period_inward_taxable),
            "inward_tax": _money(period_inward_tax),
            "from_snapshot": bool(snap) and stamp_id is None,
        })

    return {
        "return_type": "GSTR-9",
        "aid_kind": "outward_fy_aid",
        "title": "GSTR-9 worksheet aid (tables 4–8 + HSN 17/18)",
        "builder_version": BUILDER_VERSION_GSTR9,
        "fy": fy_label,
        "fy_end_year": end_year,
        "company_gstin_id": stamp_id,
        "company": {"name": company.name, "gstin": company.gstin or "", "state": company.state or ""},
        "monthly": monthly,
        "annual": {
            "outward_taxable": _money(outward_taxable),
            "outward_tax": _money(outward_tax),
            "inward_taxable": _money(inward_taxable),
            "inward_tax": _money(inward_tax),
        },
        "tables": {
            "4": {
                "aid_kind": "outward_supplies",
                "taxable_value": _money(outward_taxable),
                "tax": _money(outward_tax),
                "note": "Aggregated from monthly GSTR-1 aids.",
            },
            "5": {
                "aid_kind": "outward_nil_exempt_monthly_rollup",
                "taxable_value": _money(nil_fy),
                "note": "Sum of monthly GSTR-1 nil taxable aid (nil/exempt/zero-rated unsplit).",
            },
            "6": {
                "aid_kind": "itc_claimable_fy_books",
                "status": "WORKSHEET",
                "taxable_value": _money(itc6_taxable),
                "cgst": _money(itc6_cgst),
                "sgst": _money(itc6_sgst),
                "igst": _money(itc6_igst),
                "cess": _money(itc6_cess),
                "tax": _money(itc6_cgst + itc6_sgst + itc6_igst + itc6_cess),
                "note": (
                    "FY ITC from non-RCM purchases marked CLAIMABLE. Worksheet aid only — "
                    "not a filed GSTR-9 Table 6 engine."
                ),
            },
            "7": {
                "aid_kind": "itc_reversal_purchase_cn_fy",
                "status": "WORKSHEET",
                "taxable_value": _money(itc7_taxable),
                "cgst": _money(itc7_cgst),
                "sgst": _money(itc7_sgst),
                "igst": _money(itc7_igst),
                "cess": _money(itc7_cess),
                "tax": _money(itc7_cgst + itc7_sgst + itc7_igst + itc7_cess),
                "note": (
                    "FY ITC reversal aid from completed purchase credit notes on claimable "
                    "non-RCM invoices. Not a full Table 7 (rules 37/42/43) engine."
                ),
            },
            "8": {
                "aid_kind": "itc_2b_vs_books_fy",
                "status": "WORKSHEET",
                "itc_as_per_2b": _money(itc8a_tax),
                "itc_as_per_books": _money(itc6_cgst + itc6_sgst + itc6_igst + itc6_cess),
                "variance": _money(
                    (itc6_cgst + itc6_sgst + itc6_igst + itc6_cess) - itc8a_tax
                ),
                "imports_igst": _money(itc8_import),
                "tax": _money(itc8a_tax + itc8_import),
                "note": (
                    "Table 8 worksheet: 2B ingest vs claimable books ITC for the FY, plus "
                    "IGST on purchases without supplier GSTIN (import-like). Not GSTR-2A live."
                ),
            },
            "17": {
                "aid_kind": "hsn_outward",
                "rows": [
                    {
                        "hsn": hsn_code,
                        "rate": rate,
                        "uqc": uqc,
                        "quantity": _money(vals["quantity"]),
                        "taxable_value": _money(vals["taxable_value"]),
                        "cgst": _money(vals["cgst"]),
                        "sgst": _money(vals["sgst"]),
                        "igst": _money(vals["igst"]),
                        "cess": _money(vals.get("cess", Decimal("0"))),
                    }
                    for (hsn_code, rate, uqc), vals in sorted(hsn_fy.items())
                ],
                "note": "Aggregated from monthly GSTR-1 HSN sections.",
            },
            "18": {
                "aid_kind": "hsn_inward",
                "rows": [
                    {
                        "hsn": hsn_code,
                        "rate": rate,
                        "uqc": uqc,
                        "quantity": _money(vals["quantity"]),
                        "taxable_value": _money(vals["taxable_value"]),
                        "cgst": _money(vals["cgst"]),
                        "sgst": _money(vals["sgst"]),
                        "igst": _money(vals["igst"]),
                        "cess": _money(vals.get("cess", Decimal("0"))),
                    }
                    for (hsn_code, rate, uqc), vals in sorted(hsn_inward.items())
                ],
                "note": "Aggregated from completed GST purchase HSN lines (non-RCM).",
            },
        },
        "disclaimer": (
            "GSTR-9 worksheet aid for CA — tables 4–8 best-effort from books/2B ingest; "
            "17/18 HSN from books. Not a complete portal upload."
        ),
    }


def to_gstn_json(payload: dict) -> dict:
    """Map BizBoard worksheet payloads to a GSTN-shaped fixture (not a live upload)."""
    rt = (payload.get("return_type") or "").upper().replace("_", "-")
    company = payload.get("company") or {}
    gstin = company.get("gstin") or ""
    period = payload.get("period") or payload.get("fy") or ""
    fp = ""
    if len(period) == 7 and period[4] == "-":
        year, month = period.split("-")
        fp = f"{month}{year}"
    shaped = {
        "gstin": gstin,
        "fp": fp,
        "fy": payload.get("fy") or "",
        "return_type": rt,
        "builder_version": payload.get("builder_version"),
        "b2b": payload.get("b2b") or [],
        "b2cl": payload.get("b2cl") or [],
        "b2cs": payload.get("b2cs") or [],
        "cdnr": payload.get("cdnr") or [],
        "cdnur": payload.get("cdnur") or [],
        "exp": payload.get("exp") or [],
        "hsn": payload.get("hsn") or payload.get("tables", {}).get("17", {}).get("rows") or [],
        "supecom": payload.get("supecom") or {},
        "tables": payload.get("tables") or {},
        "disclaimer": (
            "GSTN-shaped fixture for CA tooling — not a GSTN portal upload file. "
            "Do not submit this JSON to GSTN."
        ),
    }
    return shaped


def canonical_payload_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def content_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def persist_snapshot(company, return_type: str, period: str, payload: dict, user=None) -> GstReturnSnapshot:
    rt_map = {
        "GSTR-1": GstReturnSnapshot.ReturnType.GSTR1,
        "GSTR1": GstReturnSnapshot.ReturnType.GSTR1,
        "GSTR-3B": GstReturnSnapshot.ReturnType.GSTR3B,
        "GSTR3B": GstReturnSnapshot.ReturnType.GSTR3B,
        "GSTR-9": GstReturnSnapshot.ReturnType.GSTR9,
        "GSTR9": GstReturnSnapshot.ReturnType.GSTR9,
    }
    rt = rt_map.get(return_type, return_type)
    version = payload.get("builder_version") or BUILDER_VERSION_GSTR1
    h = content_hash(payload)
    # BB-000064: replace existing row for same company+type+period (one snapshot).
    existing = GstReturnSnapshot.objects.filter(
        company=company, return_type=rt, period=period,
    ).first()
    if existing and existing.content_hash == h:
        return existing
    obj, _ = GstReturnSnapshot.objects.update_or_create(
        company=company,
        return_type=rt,
        period=period,
        defaults={
            "payload": payload,
            "content_hash": h,
            "builder_version": version,
            "generated_at": timezone.now(),
            "generated_by": user,
        },
    )
    return obj


def _sheet_from_rows(workbook, title: str, rows: list[dict]):
    sheet = workbook.create_sheet(title=title[:31])
    if not rows:
        sheet.append(["No records"])
        return
    headers = list(rows[0].keys())
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])


def gstr_return_to_xlsx(payload: dict) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    meta = workbook.create_sheet("Summary")
    meta.append(["Return", payload.get("return_type", "")])
    meta.append(["Period", payload.get("period") or payload.get("fy", "")])
    meta.append(["Builder", payload.get("builder_version", "")])
    meta.append(["Company", payload.get("company", {}).get("name", "")])
    meta.append(["GSTIN", payload.get("company", {}).get("gstin", "")])
    meta.append(["Disclaimer", payload.get("disclaimer", "")])

    rtype = payload.get("return_type")
    if rtype == "GSTR-1":
        _sheet_from_rows(workbook, "B2B", payload.get("b2b", []))
        _sheet_from_rows(workbook, "B2CL", payload.get("b2cl", []))
        _sheet_from_rows(workbook, "B2CS", payload.get("b2cs", []))
        _sheet_from_rows(workbook, "CDNR", payload.get("cdnr", []))
        _sheet_from_rows(workbook, "CDNUR", payload.get("cdnur", []))
        _sheet_from_rows(workbook, "HSN", payload.get("hsn", []))
        _sheet_from_rows(workbook, "Issues", payload.get("issues", []))
        docs = payload.get("docs", {})
        doc_sheet = workbook.create_sheet("DOCS")
        for key, value in docs.items():
            doc_sheet.append([key, value])
        totals = payload.get("totals", {})
        total_sheet = workbook.create_sheet("Totals")
        for section, values in totals.items():
            if isinstance(values, dict):
                total_sheet.append([section])
                for k, v in values.items():
                    total_sheet.append(["", k, v])
            else:
                total_sheet.append([section, values])
    elif rtype == "GSTR-9":
        _sheet_from_rows(workbook, "Monthly", payload.get("monthly", []))
        annual = payload.get("annual", {})
        sheet = workbook.create_sheet("Annual")
        for k, v in annual.items():
            sheet.append([k, v])
    else:
        outward = payload.get("outward_supplies", {})
        outward_sheet = workbook.create_sheet("Outward")
        for key, value in outward.items():
            if isinstance(value, dict):
                outward_sheet.append([key])
                for k, v in value.items():
                    outward_sheet.append(["", k, v])
            else:
                outward_sheet.append([key, value])
        table32 = payload.get("table_3_2_inter_state_unregistered") or {}
        t32_sheet = workbook.create_sheet("Table32")
        t32_sheet.append(["place_of_supply", "taxable_value", "igst"])
        for row in table32.get("rows") or []:
            t32_sheet.append([
                row.get("place_of_supply"),
                row.get("taxable_value"),
                row.get("igst"),
            ])
        inward = payload.get("inward_supplies", {}).get("from_purchases", {})
        inward_sheet = workbook.create_sheet("Inward")
        for key, value in inward.items():
            inward_sheet.append([key, value])
        rcm = payload.get("inward_supplies", {}).get("reverse_charge", {})
        rcm_sheet = workbook.create_sheet("RCM")
        for key, value in rcm.items():
            rcm_sheet.append([key, value])
        itc_sheet = workbook.create_sheet("ITC")
        for key, value in payload.get("itc", {}).get("available_from_purchases", {}).items():
            itc_sheet.append([key, value])
        review_sheet = workbook.create_sheet("ManualReview")
        review_sheet.append(["section", "status", "note"])
        for row in payload.get("itc", {}).get("manual_review", []):
            review_sheet.append([row.get("section"), row.get("status"), row.get("note")])

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_ca_pack_zip(company, period: str, gstr1: dict | None = None) -> bytes:
    from accounts.models import Company
    from reporting.gstr2b import build_cmp08, build_gstr4, claimable_itc_from_2b, match_gstr2b_to_purchases
    from reporting.models import Gstr2bIngest

    match_summary = match_gstr2b_to_purchases(company, period, persist=False)
    itc_2b = claimable_itc_from_2b(company, period)
    unmatched = Gstr2bIngest.objects.filter(
        company=company, period=period, match_status=Gstr2bIngest.MatchStatus.UNMATCHED
    ).count()
    summary = {
        "period": period,
        "gstr2b_match": match_summary,
        "gstr2b_unmatched": unmatched,
        "claimable_itc": {k: str(v) for k, v in itc_2b.items()},
    }
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if company.registration_type == Company.RegistrationType.COMPOSITION:
            cmp08 = build_cmp08(company, period)
            y = int(period[:4])
            gstr4 = build_gstr4(company, f"{y}-{str(y + 1)[-2:]}")
            zf.writestr(f"cmp08-{period}.json", json.dumps(cmp08, indent=2, default=str))
            zf.writestr(f"gstr4-{period}.json", json.dumps(gstr4, indent=2, default=str))
        else:
            g1 = gstr1 if gstr1 is not None else build_gstr1(company, period)
            g3 = build_gstr3b(company, period, gstr1=g1)
            zf.writestr(f"gstr1-{period}.xlsx", gstr_return_to_xlsx(g1))
            zf.writestr(f"gstr3b-{period}.xlsx", gstr_return_to_xlsx(g3))
            zf.writestr(f"gstr1-{period}.json", json.dumps(g1, indent=2, default=str))
            zf.writestr(f"gstr3b-{period}.json", json.dumps(g3, indent=2, default=str))
        zf.writestr(f"gstr2b-match-{period}.json", json.dumps(summary, indent=2, default=str))
    return buf.getvalue()
