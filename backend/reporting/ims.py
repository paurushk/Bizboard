"""B-03 — IMS action state, Section 16(4) clock, credit-at-risk, supplier scorecard."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import Gstr2bIngest, ImsActionHistory

IMS_BULK_CHUNK = 500
EXPIRING_DAYS = 30


def section_16_4_deadline(invoice_date: date | None) -> date | None:
    """ITC claim window: 30 Nov of the year following the FY that contains invoice_date."""
    if invoice_date is None:
        return None
    fy_end_year = invoice_date.year + 1 if invoice_date.month >= 4 else invoice_date.year
    return date(fy_end_year, 11, 30)


def _tax(row) -> Decimal:
    return (
        Decimal(str(row.igst or 0))
        + Decimal(str(row.cgst or 0))
        + Decimal(str(row.sgst or 0))
        + Decimal(str(getattr(row, "cess", 0) or 0))
    )


def refresh_16_4(row: Gstr2bIngest) -> None:
    deadline = section_16_4_deadline(row.invoice_date)
    if row.section_16_4_deadline != deadline:
        row.section_16_4_deadline = deadline
        row.save(update_fields=["section_16_4_deadline", "updated_at"])


def classify_and_match(company, period: str, *, persist: bool = True) -> dict:
    """Extend 2B match with B-03 match_class + 16(4) flags. Does not auto-accept."""
    from .gstr2b import match_gstr2b_to_purchases
    from purchases.models import PurchaseInvoice

    result = match_gstr2b_to_purchases(company, period, persist=persist)
    as_of = timezone.localdate()
    rows = list(Gstr2bIngest.objects.filter(company=company, period=period))
    seen_keys: dict[str, int] = {}
    for row in rows:
        key = f"{(row.supplier_gstin or '').upper()}|{(row.invoice_number or '').strip()}"
        seen_keys[key] = seen_keys.get(key, 0) + 1

    year, month = period.split("-")
    y, m = int(year), int(month)
    book_keys = {
        ((gstin or "").upper(), (number or "").strip())
        for gstin, number in PurchaseInvoice.objects.filter(
            company=company,
            status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
            invoice_date__year=y,
            invoice_date__month=m,
            is_opening_balance=False,
        ).exclude(number="").values_list("supplier__gstin", "number")
    }
    ims_keys = {
        ((r.supplier_gstin or "").upper(), (r.invoice_number or "").strip())
        for r in rows
        if (r.invoice_number or "").strip()
    }

    for row in rows:
        refresh_16_4(row)
        deadline = row.section_16_4_deadline
        past_window = bool(deadline and as_of > deadline)
        key = f"{(row.supplier_gstin or '').upper()}|{(row.invoice_number or '').strip()}"
        klass = Gstr2bIngest.MatchClass.OTHER
        if seen_keys.get(key, 0) > 1:
            klass = Gstr2bIngest.MatchClass.DUPLICATE
        elif past_window:
            klass = Gstr2bIngest.MatchClass.POTENTIALLY_INELIGIBLE
        elif row.match_status == Gstr2bIngest.MatchStatus.MATCHED:
            klass = Gstr2bIngest.MatchClass.EXACT
        elif row.purchase_invoice_id is None and row.match_status != Gstr2bIngest.MatchStatus.MATCHED:
            # GSTIN+number hit with amount mismatch is PARTIAL from matcher.
            if row.match_status == Gstr2bIngest.MatchStatus.PARTIAL:
                klass = Gstr2bIngest.MatchClass.VALUE_MISMATCH
            else:
                other = (
                    PurchaseInvoice.objects.filter(
                        company=company,
                        number__iexact=(row.invoice_number or "").strip(),
                    )
                    .exclude(supplier__gstin__iexact=row.supplier_gstin or "")
                    .first()
                )
                if other is not None:
                    klass = Gstr2bIngest.MatchClass.WRONG_GSTIN
                else:
                    klass = Gstr2bIngest.MatchClass.MISSING_IN_BOOKS
        if persist:
            if row.match_class != klass:
                row.match_class = klass
                row.save(update_fields=["match_class", "updated_at"])

    missing_in_ims = sorted(
        f"{gstin}|{number}" if gstin else number
        for gstin, number in book_keys
        if (gstin, number) not in ims_keys
    )
    result["match_classes"] = {
        "exact": Gstr2bIngest.objects.filter(
            company=company, period=period, match_class=Gstr2bIngest.MatchClass.EXACT
        ).count(),
        "missing_in_ims": len(missing_in_ims),
    }
    result["missing_in_ims_numbers"] = missing_in_ims[:200]
    return result


def _record_history(row, action, remark, user, payload):
    ImsActionHistory.objects.create(
        company=row.company,
        ingest=row,
        action=action,
        remark=(remark or "")[:512],
        acted_by=user,
        payload=payload or {},
    )


def apply_ims_action(row: Gstr2bIngest, action: str, *, remark: str = "", user=None, payload=None) -> Gstr2bIngest:
    action = (action or "").upper()
    allowed = {c for c, _ in Gstr2bIngest.ImsAction.choices}
    if action not in allowed:
        raise BusinessRuleError("IMS action must be ACCEPT, REJECT, PENDING, or NO_ACTION.")
    if action == Gstr2bIngest.ImsAction.ACCEPT and not (remark or "").strip():
        # Bulk exact-accept uses a standard remark.
        remark = "Bulk/board accept — recorded decision."
    if action == Gstr2bIngest.ImsAction.REJECT and not (remark or "").strip():
        raise BusinessRuleError("REJECT requires a remark (the defect).")

    now = timezone.now()
    row.ims_action = action
    row.ims_remark = (remark or "")[:512]
    row.acted_at = now
    row.acted_by = user
    row.submitted_payload = payload or {"action": action, "remark": remark}
    row.ims_response = {"recorded": True, "at": now.isoformat()}
    if action == Gstr2bIngest.ImsAction.ACCEPT:
        if row.match_status == Gstr2bIngest.MatchStatus.MATCHED:
            inv = row.purchase_invoice
            if inv is not None:
                from purchases.models import PurchaseInvoice

                if inv.itc_eligibility == PurchaseInvoice.ItcEligibility.UNREVIEWED:
                    inv.itc_eligibility = PurchaseInvoice.ItcEligibility.CLAIMABLE
                    inv.save(update_fields=["itc_eligibility", "updated_at"])
                if inv.itc_eligibility == PurchaseInvoice.ItcEligibility.CLAIMABLE:
                    row.itc_eligibility = Gstr2bIngest.ItcEligibility.CLAIMABLE
                    from accounting.services import reclass_unreviewed_itc

                    reclass_unreviewed_itc(inv, user=user)
        else:
            # Accept without a books match is a recorded decision, not a claim.
            pass
    elif action == Gstr2bIngest.ImsAction.REJECT:
        row.itc_eligibility = Gstr2bIngest.ItcEligibility.INELIGIBLE
        inv = row.purchase_invoice
        if inv is not None:
            from purchases.models import PurchaseInvoice

            if inv.itc_eligibility != PurchaseInvoice.ItcEligibility.INELIGIBLE:
                inv.itc_eligibility = PurchaseInvoice.ItcEligibility.INELIGIBLE
                inv.save(update_fields=["itc_eligibility", "updated_at"])
            from accounting.services import reclass_rejected_itc

            reclass_rejected_itc(inv, user=user)
    row.save()
    _record_history(row, action, remark, user, row.submitted_payload)
    return row


def bulk_accept_exact(company, period: str, *, user=None, remark: str = "") -> dict:
    """Accept EXACT matches in chunks of 500. Idempotent: already-ACCEPT rows skip."""
    classify_and_match(company, period, persist=True)
    qs = (
        Gstr2bIngest.objects.filter(
            company=company,
            period=period,
            match_class=Gstr2bIngest.MatchClass.EXACT,
        )
        .exclude(ims_action=Gstr2bIngest.ImsAction.ACCEPT)
        .order_by("id")
    )
    ids = list(qs.values_list("id", flat=True))
    chunks = [ids[i : i + IMS_BULK_CHUNK] for i in range(0, len(ids), IMS_BULK_CHUNK)]
    accepted = 0
    note = remark or "Bulk accept exact matches — recorded decision."
    for chunk in chunks:
        with transaction.atomic():
            for row in Gstr2bIngest.objects.filter(company=company, id__in=chunk).select_related("purchase_invoice"):
                if row.ims_action == Gstr2bIngest.ImsAction.ACCEPT:
                    continue
                apply_ims_action(row, Gstr2bIngest.ImsAction.ACCEPT, remark=note, user=user)
                accepted += 1
    return {
        "period": period,
        "accepted": accepted,
        "chunks": len(chunks),
        "chunk_size": IMS_BULK_CHUNK,
    }


def deemed_accept_on_period_lock(company, period: str, *, user=None) -> int:
    """NO_ACTION EXACT matches at GST period lock are deemed ACCEPT — never silent.

    MISSING_IN_BOOKS / mismatches stay NO_ACTION so ITC is not auto-claimed.
    """
    qs = Gstr2bIngest.objects.filter(
        company=company,
        period=period,
        ims_action=Gstr2bIngest.ImsAction.NO_ACTION,
        match_class=Gstr2bIngest.MatchClass.EXACT,
    )
    n = 0
    with transaction.atomic():
        for row in qs.select_for_update().order_by("id"):
            apply_ims_action(
                row,
                Gstr2bIngest.ImsAction.ACCEPT,
                remark="Deemed accept at GST period lock (exact match, no IMS action recorded before close).",
                user=user,
                payload={"deemed": True},
            )
            n += 1
    return n


def credit_at_risk(company, period: str, *, as_of: date | None = None) -> dict:
    as_of = as_of or timezone.localdate()
    classify_and_match(company, period, persist=True)
    rows = list(Gstr2bIngest.objects.filter(company=company, period=period))
    total = Decimal("0")
    matched = Decimal("0")
    unresolved = Decimal("0")
    at_risk = Decimal("0")
    expiring = Decimal("0")
    expiring_count = 0
    ineligible = Decimal("0")
    for row in rows:
        tax = _tax(row)
        total += tax
        if row.match_status == Gstr2bIngest.MatchStatus.MATCHED:
            matched += tax
        accepted = row.ims_action == Gstr2bIngest.ImsAction.ACCEPT
        rejected = row.ims_action == Gstr2bIngest.ImsAction.REJECT
        deadline = row.section_16_4_deadline or section_16_4_deadline(row.invoice_date)
        past = bool(deadline and as_of > deadline)
        if rejected or past:
            ineligible += tax
            continue
        if not accepted:
            unresolved += tax
            at_risk += tax
            if deadline:
                days = (deadline - as_of).days
                if 0 <= days <= EXPIRING_DAYS:
                    expiring += tax
                    expiring_count += 1
    return {
        "period": period,
        "total_itc": str(total),
        "matched_itc": str(matched),
        "unresolved_itc": str(unresolved),
        "itc_at_risk": str(at_risk),
        "itc_at_risk_paise": int((at_risk * 100).to_integral_value()),
        "expiring_itc": str(expiring),
        "expiring_count": expiring_count,
        "ineligible_itc": str(ineligible),
        "row_count": len(rows),
    }


def supplier_scorecard(company, period: str) -> list[dict]:
    from masters.models import Supplier
    from purchases.models import PurchaseInvoice

    year, month = period.split("-")
    y, m = int(year), int(month)
    rows = list(Gstr2bIngest.objects.filter(company=company, period=period).select_related("purchase_invoice"))
    by_gstin: dict[str, dict] = {}
    for row in rows:
        gstin = (row.supplier_gstin or "").upper()
        bucket = by_gstin.setdefault(
            gstin,
            {
                "supplier_gstin": gstin,
                "mismatch_count": 0,
                "rejections": 0,
                "itc_affected": Decimal("0"),
                "correction_days": [],
            },
        )
        taxed = False
        if row.match_class in (
            Gstr2bIngest.MatchClass.VALUE_MISMATCH,
            Gstr2bIngest.MatchClass.WRONG_GSTIN,
            Gstr2bIngest.MatchClass.MISSING_IN_BOOKS,
            Gstr2bIngest.MatchClass.DUPLICATE,
        ):
            bucket["mismatch_count"] += 1
            taxed = True
        if row.ims_action == Gstr2bIngest.ImsAction.REJECT:
            bucket["rejections"] += 1
            taxed = True
        if taxed:
            bucket["itc_affected"] += _tax(row)
        if row.acted_at and row.created_at:
            bucket["correction_days"].append((row.acted_at.date() - row.created_at.date()).days)

    out = []
    for gstin, bucket in by_gstin.items():
        supplier = Supplier.objects.filter(company=company, gstin__iexact=gstin).first()
        purchase_value = Decimal("0")
        missing = 0
        if supplier:
            qs = PurchaseInvoice.objects.filter(
                company=company,
                supplier=supplier,
                status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
                invoice_date__year=y,
                invoice_date__month=m,
            )
            purchase_value = sum((Decimal(str(p.grand_total or 0)) for p in qs), Decimal("0"))
        days = bucket["correction_days"]
        avg = (sum(days) / len(days)) if days else 0
        out.append({
            "supplier_gstin": gstin,
            "supplier_name": supplier.name if supplier else "",
            "supplier_id": supplier.id if supplier else None,
            "purchase_value": str(purchase_value),
            "mismatch_count": bucket["mismatch_count"],
            "rejections": bucket["rejections"],
            "itc_affected": str(bucket["itc_affected"]),
            "average_correction_days": round(avg, 1),
        })
    out.sort(key=lambda r: Decimal(r["itc_affected"]), reverse=True)
    return out


def supplier_defect_message(row: Gstr2bIngest) -> dict:
    from masters.models import Supplier

    supplier = Supplier.objects.filter(
        company=row.company, gstin__iexact=row.supplier_gstin or ""
    ).first()
    defect = row.ims_remark or row.match_class or "mismatch vs GSTR-2B / IMS"
    name = supplier.name if supplier else (row.supplier_gstin or "Supplier")
    text = (
        f"Hi {name}, invoice {row.invoice_number or '—'} dated {row.invoice_date or '—'} "
        f"could not be accepted for ITC ({defect}). "
        "Please share a corrected invoice or credit note. — BizBoard IMS"
    )
    return {
        "supplier_id": supplier.id if supplier else None,
        "supplier_name": name,
        "phone": getattr(supplier, "phone", "") if supplier else "",
        "text": text,
        "ingest_id": row.id,
        "defect": defect,
    }
