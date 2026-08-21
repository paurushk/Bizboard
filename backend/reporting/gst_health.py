"""GST Health Dashboard — derived compliance alerts (Phase 2)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from accounts.models import Company
from core.services.billing import extract_state_code
from core.validators import ALLOWED_GST_RATES, GSTIN_RE
from core.services.uqc import normalize_uqc
from purchases.models import PurchaseInvoice
from sales.models import DeliveryChallan, SalesCreditNote, SalesDebitNote, SalesInvoice

from .gst_returns import (
    EINVOICE_AATO_THRESHOLD,
    GST_INVOICE_TYPES,
    invoice_value_mismatch,
    parse_period,
)
from .models import GstReturnPeriod, GstReturnSnapshot


# Alias kept for callers/tests — same ₹5cr AATO as e-Invoice (GSTR-14).
HSN_6_DIGIT_AATO = EINVOICE_AATO_THRESHOLD


def hsn_digits_insufficient_for_turnover(hsn: str, aato, *, is_b2b: bool = False) -> bool:
    """True when HSN digit length is below the AATO-based filing expectation.

    GSTR-14: ≥ ₹5cr → 6-digit HSN; below ₹5cr B2B → at least 4-digit HSN.
    """
    code = (hsn or "").strip()
    if not code:
        return False
    try:
        turnover = Decimal(str(aato)) if aato is not None else Decimal("0")
    except Exception:
        turnover = Decimal("0")
    if turnover >= EINVOICE_AATO_THRESHOLD:
        return len(code) < 6
    if is_b2b:
        return len(code) < 4
    return False


def _alert(code, severity, message, **extra):
    row = {"code": code, "severity": severity, "message": message}
    row.update(extra)
    return row


def build_gst_health(company, period: str | None = None) -> dict:
    if period:
        date_from, date_to = parse_period(period)
    else:
        today = timezone.localdate()
        period = f"{today.year:04d}-{today.month:02d}"
        date_from, date_to = parse_period(period)

    alerts: list[dict] = []

    # Company GSTIN
    if company.registration_type != Company.RegistrationType.UNREGISTERED:
        if not (company.gstin or "").strip():
            alerts.append(_alert(
                "GSTIN_MISSING_COMPANY", "critical",
                "Registered company has no GSTIN.",
            ))
        elif not GSTIN_RE.match(company.gstin):
            alerts.append(_alert(
                "GSTIN_INVALID_FORMAT", "critical",
                f"Company GSTIN '{company.gstin}' fails format validation.",
            ))
        else:
            status = (company.gstin_verification_status or "UNVERIFIED").upper()
            verified_at = company.gstin_verified_at
            stale = (
                verified_at is None
                or verified_at < timezone.now() - timedelta(days=90)
                or status == "UNVERIFIED"
            )
            if stale:
                alerts.append(_alert(
                    "GSTIN_UNVERIFIED", "warning",
                    "Company GSTIN has not been verified in the last 90 days.",
                ))

    pan = (getattr(company, "pan", "") or "").strip().upper()
    if pan:
        from core.validators import PAN_RE

        if not PAN_RE.match(pan):
            alerts.append(_alert(
                "IDENTITY_PAN_INVALID", "warning",
                f"Company PAN '{pan}' fails format validation.",
            ))
        elif (company.pan_verification_status or "UNVERIFIED").upper() in ("UNVERIFIED", "INVALID", "FAILED"):
            alerts.append(_alert(
                "IDENTITY_PAN_UNVERIFIED", "info",
                "Company PAN is saved but not live-verified (format check only).",
            ))
    udyam = (getattr(company, "udyam", "") or "").strip().upper()
    if udyam:
        from core.validators import UDYAM_RE

        if not UDYAM_RE.match(udyam):
            alerts.append(_alert(
                "IDENTITY_UDYAM_INVALID", "warning",
                f"Company UDYAM '{udyam}' fails format validation.",
            ))
        elif (company.udyam_verification_status or "UNVERIFIED").upper() in ("UNVERIFIED", "INVALID", "FAILED"):
            alerts.append(_alert(
                "IDENTITY_UDYAM_UNVERIFIED", "info",
                "Company UDYAM is saved but not live-verified (format check only).",
            ))

    from masters.models import Unit

    for unit in Unit.objects.filter(company=company):
        uqc = (unit.uqc_code or "").strip()
        if not uqc or uqc == "OTH":
            mapped = normalize_uqc(unit.short_name) or normalize_uqc(unit.name)
            if not mapped:
                alerts.append(_alert(
                    "UQC_UNMAPPED", "warning",
                    f"Unit '{unit.name}' has no GSTN UQC mapping.",
                    document_type="unit", document_id=unit.id,
                ))

    # E-Invoice mandatory by AATO
    aato = company.aato_turnover
    if aato is not None and aato >= EINVOICE_AATO_THRESHOLD and not company.einvoice_enabled:
        alerts.append(_alert(
            "EINVOICE_MANDATORY_NOT_ENABLED", "critical",
            f"AATO {aato} exceeds e-Invoice threshold but einvoice_enabled is false.",
        ))

    invoices = list(
        SalesInvoice.objects.filter(
            company=company,
            status__in=(SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED),
            invoice_type__in=GST_INVOICE_TYPES,
            invoice_date__gte=date_from,
            invoice_date__lte=date_to,
            is_opening_balance=False,
        )
        .select_related("customer")
        .prefetch_related("items")
    )

    for inv in invoices:
        if invoice_value_mismatch(inv):
            alerts.append(_alert(
                "INVOICE_VALUE_MISMATCH", "critical",
                f"Invoice {inv.number}: grand_total does not reconcile for GSTR.",
                document_type="sales_invoice", document_id=inv.id, number=inv.number,
            ))
        items = list(inv.items.all())
        for idx, item in enumerate(items, start=1):
            hsn = (item.hsn_code or "").strip()
            if not hsn:
                alerts.append(_alert(
                    "HSN_MISSING", "critical",
                    f"Invoice {inv.number} line {idx}: missing HSN snapshot.",
                    document_type="sales_invoice", document_id=inv.id, number=inv.number,
                ))
            else:
                party_gstin = (inv.filing_party_gstin or inv.customer.gstin or "").strip()
                is_b2b = bool(party_gstin)
                if hsn_digits_insufficient_for_turnover(hsn, aato, is_b2b=is_b2b):
                    need = "6" if (aato is not None and Decimal(str(aato)) >= EINVOICE_AATO_THRESHOLD) else "4"
                    alerts.append(_alert(
                        "HSN_DIGITS_INSUFFICIENT", "warning",
                        f"Invoice {inv.number} line {idx}: HSN '{hsn}' may need {need} digits "
                        f"({'AATO ≥ ₹5cr' if need == '6' else 'B2B below ₹5cr'}).",
                        document_type="sales_invoice", document_id=inv.id, number=inv.number,
                    ))
            uqc = (getattr(item, "uqc_code", None) or "").strip()
            unit_name = (getattr(item, "unit_name", None) or "").strip()
            if not uqc:
                alerts.append(_alert(
                    "UQC_UNMAPPED", "warning",
                    f"Invoice {inv.number} line {idx}: no GSTN UQC mapped.",
                    document_type="sales_invoice", document_id=inv.id, number=inv.number,
                ))
            elif uqc == "OTH" and unit_name and not normalize_uqc(unit_name):
                alerts.append(_alert(
                    "UQC_UNMAPPED", "warning",
                    f"Invoice {inv.number} line {idx}: unit '{unit_name}' has no GSTN UQC mapping.",
                    document_type="sales_invoice", document_id=inv.id, number=inv.number,
                ))
            rate = item.gst_rate
            if str(rate) not in ALLOWED_GST_RATES and Decimal(str(rate)) not in {
                Decimal(r) for r in ALLOWED_GST_RATES
            }:
                alerts.append(_alert(
                    "RATE_NONSTANDARD", "warning",
                    f"Invoice {inv.number} line {idx}: non-standard GST rate {rate}.",
                    document_type="sales_invoice", document_id=inv.id, number=inv.number,
                ))

        party_gstin = (inv.filing_party_gstin or inv.customer.gstin or "").strip()
        pos = (inv.filing_place_of_supply or "").strip() or extract_state_code(party_gstin) or (
            inv.customer.state or ""
        ).strip()
        if inv.invoice_type != SalesInvoice.InvoiceType.NON_GST and not pos:
            alerts.append(_alert(
                "POS_UNKNOWN", "critical",
                f"Invoice {inv.number}: place of supply unknown.",
                document_type="sales_invoice", document_id=inv.id, number=inv.number,
            ))

        # B2B-looking completed GST invoice without party GSTIN (threshold configurable).
        party_gstin_threshold = getattr(company, "party_gstin_alert_threshold", None)
        if party_gstin_threshold is None:
            party_gstin_threshold = Decimal("50000")
        if (
            inv.invoice_type == SalesInvoice.InvoiceType.GST
            and not party_gstin
            and Decimal(str(inv.grand_total or 0)) >= Decimal(str(party_gstin_threshold))
        ):
            alerts.append(_alert(
                "PARTY_GSTIN_MISSING_B2B", "warning",
                f"Invoice {inv.number}: GST invoice ≥ ₹{party_gstin_threshold} without party GSTIN.",
                document_type="sales_invoice", document_id=inv.id, number=inv.number,
            ))

        if (
            company.einvoice_enabled
            and party_gstin
            and inv.invoice_type == SalesInvoice.InvoiceType.GST
            and inv.einvoice_status
            not in (
                SalesInvoice.EInvoiceStatus.GENERATED,
                getattr(SalesInvoice.EInvoiceStatus, "MANUAL_IRN", "MANUAL_IRN"),
            )
        ):
            alerts.append(_alert(
                "EINVOICE_PENDING", "warning",
                f"Invoice {inv.number}: e-Invoice not generated.",
                document_type="sales_invoice", document_id=inv.id, number=inv.number,
            ))

        threshold = company.eway_threshold_amount or Decimal("50000")
        if (
            company.eway_enabled
            and inv.grand_total >= threshold
            and inv.eway_status != SalesInvoice.EwayStatus.GENERATED
        ):
            # Interstate heuristic
            company_code = extract_state_code(company.gstin) or extract_state_code(company.state)
            party_code = extract_state_code(party_gstin) or extract_state_code(inv.customer.state)
            if company_code and party_code and company_code != party_code:
                alerts.append(_alert(
                    "EWAY_PENDING", "warning",
                    f"Invoice {inv.number}: e-Way Bill not generated (over threshold).",
                    document_type="sales_invoice", document_id=inv.id, number=inv.number,
                ))
        if (
            inv.eway_status == SalesInvoice.EwayStatus.GENERATED
            and inv.eway_valid_upto
            and inv.eway_valid_upto < timezone.now()
        ):
            alerts.append(_alert(
                "EWAY_EXPIRED", "critical",
                f"Invoice {inv.number}: e-Way Bill expired.",
                document_type="sales_invoice", document_id=inv.id, number=inv.number,
            ))

    # Notes missing HSN
    for note in SalesCreditNote.objects.filter(
        company=company, status=SalesCreditNote.Status.COMPLETED,
        note_date__gte=date_from, note_date__lte=date_to,
        sales_invoice__invoice_type__in=GST_INVOICE_TYPES,
    ).prefetch_related("items"):
        for idx, item in enumerate(note.items.all(), start=1):
            if not (getattr(item, "hsn_code", None) or "").strip():
                alerts.append(_alert(
                    "HSN_MISSING", "critical",
                    f"Credit note {note.number} line {idx}: missing HSN snapshot.",
                    document_type="sales_credit_note", document_id=note.id, number=note.number,
                ))

    for note in SalesDebitNote.objects.filter(
        company=company, status=SalesDebitNote.Status.COMPLETED,
        note_date__gte=date_from, note_date__lte=date_to,
        sales_invoice__invoice_type__in=GST_INVOICE_TYPES,
    ).prefetch_related("items"):
        for idx, item in enumerate(note.items.all(), start=1):
            if not (getattr(item, "hsn_code", None) or "").strip():
                alerts.append(_alert(
                    "HSN_MISSING", "critical",
                    f"Debit note {note.number} line {idx}: missing HSN snapshot.",
                    document_type="sales_debit_note", document_id=note.id, number=note.number,
                ))

    # Challans e-way expired
    for challan in DeliveryChallan.objects.filter(
        company=company,
        status=DeliveryChallan.Status.COMPLETED,
        challan_date__gte=date_from,
        challan_date__lte=date_to,
        eway_status=SalesInvoice.EwayStatus.GENERATED,
        eway_valid_upto__lt=timezone.now(),
    ):
        alerts.append(_alert(
            "EWAY_EXPIRED", "critical",
            f"Challan {challan.number}: e-Way Bill expired.",
            document_type="delivery_challan", document_id=challan.id, number=challan.number,
        ))

    # Period alerts
    try:
        period_obj = GstReturnPeriod.objects.get(company=company, period=period)
        if period_obj.dirty_after_snapshot:
            alerts.append(_alert(
                "PERIOD_CHANGED_AFTER_SNAPSHOT", "critical",
                f"Period {period} changed after a GSTR snapshot was exported.",
            ))
    except GstReturnPeriod.DoesNotExist:
        pass

    # Previous month still open after ~20th (filing due hint)
    today = timezone.localdate()
    if today.day >= 20:
        prev_month = today.month - 1 or 12
        prev_year = today.year if today.month > 1 else today.year - 1
        prev = f"{prev_year:04d}-{prev_month:02d}"
        prev_obj = GstReturnPeriod.objects.filter(company=company, period=prev).first()
        if prev_obj is None or prev_obj.status == GstReturnPeriod.Status.OPEN:
            if GstReturnSnapshot.objects.filter(
                company=company, period=prev, return_type=GstReturnSnapshot.ReturnType.GSTR1
            ).exists() is False:
                alerts.append(_alert(
                    "GSTR_PERIOD_OPEN", "info",
                    f"Previous period {prev} has no GSTR-1 snapshot yet.",
                ))

    # RCM hint: unregistered supplier GST purchases
    for pur in PurchaseInvoice.objects.filter(
        company=company,
        status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
        purchase_type=PurchaseInvoice.PurchaseType.GST,
        invoice_date__gte=date_from,
        invoice_date__lte=date_to,
        is_reverse_charge=False,
    ).select_related("supplier"):
        if not (pur.supplier.gstin or "").strip():
            alerts.append(_alert(
                "RCM_UNFLAGGED_HINT", "info",
                f"Purchase {pur.number}: unregistered supplier — confirm RCM not applicable.",
                document_type="purchase_invoice", document_id=pur.id, number=pur.number,
            ))

    # Wave 17A: unmatched GSTR-2B rows for the period.
    from reporting.models import Gstr2bIngest

    unmatched_2b = Gstr2bIngest.objects.filter(
        company=company,
        period=period,
        match_status=Gstr2bIngest.MatchStatus.UNMATCHED,
    ).count()
    if unmatched_2b:
        alerts.append(_alert(
            "GSTR2B_UNMATCHED",
            "warning",
            f"{unmatched_2b} GSTR-2B row(s) unmatched for {period}.",
            count=unmatched_2b,
        ))

    summary = {"critical": 0, "warning": 0, "info": 0}
    for a in alerts:
        summary[a["severity"]] = summary.get(a["severity"], 0) + 1

    return {
        "period": period,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "summary": summary,
        "alerts": alerts,
    }
