"""GSTR-1 section row builders — extracted from gst_returns (BB-000505)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal


def accumulate_hsn_line(hsn_buckets: dict, item, *, sign: Decimal = Decimal("1")) -> None:
    """Roll one line into the HSN summary buckets."""
    hsn = (getattr(item, "hsn_code", None) or "").strip() or "NA"
    uqc = (getattr(item, "uqc_code", None) or "").strip() or "OTH"
    rate = Decimal(str(getattr(item, "gst_rate", 0) or 0))
    key = (hsn, str(rate), uqc)
    hsn_buckets[key]["quantity"] += sign * Decimal(str(getattr(item, "quantity", 0) or 0))
    hsn_buckets[key]["taxable_value"] += sign * Decimal(str(getattr(item, "taxable_amount", 0) or 0))
    hsn_buckets[key]["cgst"] += sign * Decimal(str(getattr(item, "cgst", 0) or 0))
    hsn_buckets[key]["sgst"] += sign * Decimal(str(getattr(item, "sgst", 0) or 0))
    hsn_buckets[key]["igst"] += sign * Decimal(str(getattr(item, "igst", 0) or 0))
    hsn_buckets[key]["cess"] += sign * Decimal(str(getattr(item, "cess", 0) or 0))


def _supply_type_of(inv) -> str:
    st = (getattr(inv, "supply_type", None) or "").strip().upper()
    if st and st != "B2B":
        return st
    party = getattr(inv, "customer", None)
    tt = (getattr(party, "taxpayer_type", None) or "").strip().upper()
    if tt in ("SEZWP", "SEZWOP", "EXPWP", "EXPWOP", "DEXP"):
        return tt
    return "B2B"


def append_exp_sez_rows(*, company, inv, buckets, exp: list, sez: list) -> bool:
    """Route EXP/SEZ invoices out of B2B. Returns True if handled."""
    from .gst_returns import _filing_gstin, _filing_pos, _money

    supply = _supply_type_of(inv)
    if supply not in ("SEZWP", "SEZWOP", "EXPWP", "EXPWOP", "DEXP"):
        return False
    if supply == "DEXP":
        target = exp
        # Keep DEXP out of SEZ (BB-000622); still listed with supply_type stamp.
    else:
        target = sez if supply.startswith("SEZ") else exp
    for rate, vals in sorted(buckets.items()):
        target.append({
            "invoice_number": inv.number,
            "invoice_date": inv.invoice_date.isoformat(),
            "customer_name": inv.customer.name,
            "ctin": _filing_gstin(inv),
            "place_of_supply": _filing_pos(inv, company),
            "supply_type": supply,
            "rate": _money(rate),
            "taxable_value": _money(vals["taxable_value"]),
            "cgst": _money(vals["cgst"]),
            "sgst": _money(vals["sgst"]),
            "igst": _money(vals["igst"]),
            "cess": _money(vals.get("cess", Decimal("0"))),
            "invoice_value": _money(inv.grand_total),
        })
    return True


def append_b2_outward_rows(
    *,
    company,
    inv,
    items,
    buckets,
    b2b: list,
    b2cl: list,
    b2cs_buckets: dict,
    exp: list | None = None,
    sez: list | None = None,
    nil_bucket: dict | None = None,
    issues: list | None = None,
) -> None:
    """Classify one outward invoice into B2B / B2CL / B2CS / EXP / SEZ / nil."""
    from .gst_returns import (
        b2cl_threshold_for,
        _filing_gstin,
        _filing_pos,
        _inter_state,
        _is_b2b,
        _money,
    )

    if exp is not None and sez is not None and append_exp_sez_rows(
        company=company, inv=inv, buckets=buckets, exp=exp, sez=sez
    ):
        return

    # GSTR-08: attribute 0% lines to nil aid even on mixed-rate invoices.
    # All-zero invoices go entirely to nil (no B2B/B2CL/B2CS rows).
    has_nonzero = any(Decimal(str(r)) != 0 for r in buckets)
    if nil_bucket is not None and buckets:
        if not has_nonzero:
            for vals in buckets.values():
                amt = vals["taxable_value"]
                nil_bucket["taxable_value"] += amt
                nil_bucket["nil_rated"] = nil_bucket.get("nil_rated", Decimal("0")) + amt
            return
        for rate in [r for r in buckets if Decimal(str(r)) == 0]:
            amt = buckets[rate]["taxable_value"]
            nil_bucket["taxable_value"] += amt
            nil_bucket["nil_rated"] = nil_bucket.get("nil_rated", Decimal("0")) + amt
            del buckets[rate]

    ctin = _filing_gstin(inv)
    pos = _filing_pos(inv, company)
    if _is_b2b(ctin):
        for rate, vals in sorted(buckets.items()):
            b2b.append({
                "invoice_number": inv.number,
                "invoice_date": inv.invoice_date.isoformat(),
                "customer_name": inv.customer.name,
                "ctin": ctin,
                "place_of_supply": pos,
                "rate": _money(rate),
                "taxable_value": _money(vals["taxable_value"]),
                "cgst": _money(vals["cgst"]),
                "sgst": _money(vals["sgst"]),
                "igst": _money(vals["igst"]),
                "cess": _money(vals.get("cess", Decimal("0"))),
                "invoice_value": _money(inv.grand_total),
                "rchrg": "Y" if getattr(inv, "is_reverse_charge", False) else "N",
            })
        return

    pos_unresolved = not (pos or "").strip() or str(pos).strip().upper() in ("NA", "N/A")
    if pos_unresolved and not getattr(company, "assume_local_state_for_blank_party", False):
        if issues is not None:
            issues.append({
                "code": "POS_UNRESOLVED",
                "severity": "critical",
                "document_type": "sales_invoice",
                "document_id": inv.id,
                "number": inv.number,
                "message": "Place of supply could not be resolved; invoice excluded from B2CL/B2CS.",
            })
        return

    stamp = getattr(inv, "company_gstin", None)
    inter = _inter_state(
        company,
        pos,
        ctin,
        seller_gstin=(stamp.gstin if stamp is not None else "") or "",
        seller_state=(stamp.state if stamp is not None else "") or "",
    )
    if inter and inv.grand_total > b2cl_threshold_for(getattr(inv, "invoice_date", None)):
        for rate, vals in sorted(buckets.items()):
            b2cl.append({
                "invoice_number": inv.number,
                "invoice_date": inv.invoice_date.isoformat(),
                "customer_name": inv.customer.name,
                "place_of_supply": pos,
                "rate": _money(rate),
                "taxable_value": _money(vals["taxable_value"]),
                "igst": _money(vals["igst"]),
                "cess": _money(vals.get("cess", Decimal("0"))),
                "invoice_value": _money(inv.grand_total),
            })
        return

    for rate, vals in buckets.items():
        key = (pos, _money(rate))
        b2cs_buckets[key]["taxable_value"] += vals["taxable_value"]
        b2cs_buckets[key]["cgst"] += vals["cgst"]
        b2cs_buckets[key]["sgst"] += vals["sgst"]
        b2cs_buckets[key]["igst"] += vals["igst"]
        b2cs_buckets[key]["cess"] += vals.get("cess", Decimal("0"))


def build_note_rate_rows(
    *,
    company,
    note,
    note_kind: str,
    original_number: str,
    issues: list,
    hsn_buckets: dict,
    cdnr: list,
    cdnur: list,
    b2cs_buckets: dict | None = None,
) -> None:
    """Append CDNR/CDNUR/B2CS rate rows for one credit/debit note."""
    from .gst_returns import (
        b2cl_threshold_for,
        _filing_gstin,
        _filing_pos,
        _inter_state,
        _is_b2b,
        _money,
        _rate_buckets,
        note_value_mismatch,
    )

    # B5-006: use the note-aware predicate (matches the GSTR-1 liability filter)
    # so a note isn't in the CDNR/CDNUR section rows but out of the header totals.
    if note_value_mismatch(note):
        issues.append({
            "code": "INVOICE_VALUE_MISMATCH",
            "severity": "critical",
            "document_type": "sales_note",
            "document_id": note.id,
            "number": note.number,
            "message": "Note grand_total does not reconcile to taxable+tax (charges / AFTER_TAX discount).",
        })
        return
    inv = note.sales_invoice
    party = note.customer
    note_gstin = (getattr(note, "filing_party_gstin", None) or "").strip()
    note_pos = (getattr(note, "filing_place_of_supply", None) or "").strip()
    ctin = note_gstin or _filing_gstin(inv)
    pos = note_pos or _filing_pos(inv, company)
    items = list(note.items.all())
    sign = Decimal("-1") if note_kind == "CREDIT" else Decimal("1")
    for item in items:
        accumulate_hsn_line(hsn_buckets, item, sign=sign)

    buckets = _rate_buckets(items, invoice=inv)
    sign = Decimal("-1") if note_kind == "CREDIT" else Decimal("1")
    # Export/SEZ notes must follow the same supply-type detection as invoices —
    # never fall through into B2CS.
    supply = _supply_type_of(inv)
    if supply in ("SEZWP", "SEZWOP", "EXPWP", "EXPWOP", "DEXP"):
        for rate, vals in sorted(buckets.items()):
            cdnur.append({
                "note_kind": note_kind,
                "note_number": note.number,
                "note_date": note.note_date.isoformat(),
                "original_invoice": original_number,
                "reason": note.reason,
                "customer_name": party.name,
                "ctin": ctin,
                "place_of_supply": pos,
                "supply_type": supply,
                "rate": _money(rate),
                "taxable_value": _money(vals["taxable_value"]),
                "cgst": _money(vals["cgst"]),
                "sgst": _money(vals["sgst"]),
                "igst": _money(vals["igst"]),
                "cess": _money(vals.get("cess", Decimal("0"))),
                "note_value": _money(note.grand_total),
            })
        return
    if _is_b2b(ctin):
        target = cdnr
    else:
        stamp = getattr(inv, "company_gstin", None)
        inter = _inter_state(
            company,
            pos,
            ctin,
            seller_gstin=(stamp.gstin if stamp is not None else "") or "",
            seller_state=(stamp.state if stamp is not None else "") or "",
        )
        inv_value = Decimal(str(getattr(inv, "grand_total", 0) or 0))
        if inter and inv_value > b2cl_threshold_for(getattr(inv, "invoice_date", None)):
            target = cdnur
        else:
            if b2cs_buckets is not None:
                for rate, vals in buckets.items():
                    key = (pos, _money(rate))
                    b2cs_buckets[key]["taxable_value"] += sign * vals["taxable_value"]
                    b2cs_buckets[key]["cgst"] += sign * vals["cgst"]
                    b2cs_buckets[key]["sgst"] += sign * vals["sgst"]
                    b2cs_buckets[key]["igst"] += sign * vals["igst"]
                    b2cs_buckets[key]["cess"] += sign * vals.get("cess", Decimal("0"))
                return
            target = cdnur
    rchrg = "Y" if getattr(inv, "is_reverse_charge", False) else "N"
    for rate, vals in sorted(buckets.items()):
        target.append({
            "note_kind": note_kind,
            "note_number": note.number,
            "note_date": note.note_date.isoformat(),
            "original_invoice": original_number,
            "reason": note.reason,
            "customer_name": party.name,
            "ctin": ctin,
            "place_of_supply": pos,
            "rate": _money(rate),
            "taxable_value": _money(vals["taxable_value"]),
            "cgst": _money(vals["cgst"]),
            "sgst": _money(vals["sgst"]),
            "igst": _money(vals["igst"]),
            "cess": _money(vals.get("cess", Decimal("0"))),
            "note_value": _money(note.grand_total),
            "rchrg": rchrg,
        })


def new_hsn_buckets() -> dict:
    return defaultdict(
        lambda: {
            "quantity": Decimal("0"),
            "taxable_value": Decimal("0"),
            "cgst": Decimal("0"),
            "sgst": Decimal("0"),
            "igst": Decimal("0"),
            "cess": Decimal("0"),
        }
    )
