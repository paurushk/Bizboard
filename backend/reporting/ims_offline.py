"""GSTN IMS offline-tool file — JSON in, JSON out (B-03). No GSP required."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db import transaction

from core.exceptions import BusinessRuleError

from .models import Gstr2bIngest

OFFLINE_VERSION = "ims-offline@1.0"


def _d(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)[:10]


def _money(value) -> str:
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def row_to_offline(row: Gstr2bIngest) -> dict:
    return {
        "supplier_gstin": (row.supplier_gstin or "").upper(),
        "invoice_number": (row.invoice_number or "").strip(),
        "invoice_date": _d(row.invoice_date),
        "taxable_value": _money(row.taxable_value),
        "igst": _money(row.igst),
        "cgst": _money(row.cgst),
        "sgst": _money(row.sgst),
        "cess": _money(getattr(row, "cess", 0)),
        "ims_action": row.ims_action or Gstr2bIngest.ImsAction.NO_ACTION,
        "remark": row.ims_remark or "",
        "match_class": row.match_class or "",
        "match_status": row.match_status,
        "itc_eligibility": row.itc_eligibility,
    }


def export_offline(company, period: str) -> dict:
    rows = list(
        Gstr2bIngest.objects.filter(company=company, period=period).order_by(
            "supplier_gstin", "invoice_number", "id"
        )
    )
    return {
        "version": OFFLINE_VERSION,
        "period": period,
        "rows": [row_to_offline(r) for r in rows],
    }


def _parse_date(raw):
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


@transaction.atomic
def import_offline(company, payload: dict, *, replace: bool = False) -> dict:
    if not isinstance(payload, dict):
        raise BusinessRuleError("Offline IMS file must be a JSON object.")
    period = (payload.get("period") or "").strip()
    if len(period) != 7 or period[4] != "-":
        raise BusinessRuleError("period must be YYYY-MM.")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise BusinessRuleError("'rows' must be a list.")
    if replace:
        Gstr2bIngest.objects.filter(company=company, period=period).delete()
    valid_actions = set(Gstr2bIngest.ImsAction.values)
    created = 0
    updated = 0
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        gstin = (raw.get("supplier_gstin") or "")[:15]
        inv_no = (raw.get("invoice_number") or "").strip()[:64]
        # The offline tool round-trips the reviewer's IMS decision — preserve
        # ims_action / remark / match_class from the file. match_status and
        # itc_eligibility stay derived (classify_and_match recomputes them).
        action = str(raw.get("ims_action") or "").strip().upper()
        if action not in valid_actions:
            action = Gstr2bIngest.ImsAction.NO_ACTION
        defaults = {
            "invoice_date": _parse_date(raw.get("invoice_date")),
            "taxable_value": raw.get("taxable_value") or 0,
            "igst": raw.get("igst") or 0,
            "cgst": raw.get("cgst") or 0,
            "sgst": raw.get("sgst") or 0,
            "cess": raw.get("cess") or 0,
            "ims_action": action,
            "ims_remark": (raw.get("remark") or "")[:512],
            "match_class": (raw.get("match_class") or "")[:64],
            "itc_eligibility": Gstr2bIngest.ItcEligibility.UNREVIEWED,
            "match_status": Gstr2bIngest.MatchStatus.UNMATCHED,
            "raw": {**raw, "source": "OFFLINE"},
        }
        lookup = {
            "company": company,
            "period": period,
            "supplier_gstin": gstin,
            "invoice_number": inv_no,
        }
        if not inv_no:
            existing = Gstr2bIngest.objects.filter(**lookup).first()
            if existing is not None:
                for key, value in defaults.items():
                    setattr(existing, key, value)
                existing.save()
                updated += 1
                continue
            Gstr2bIngest.objects.create(**lookup, **defaults)
            created += 1
            continue
        _obj, was_created = Gstr2bIngest.objects.update_or_create(
            **lookup, defaults=defaults
        )
        if was_created:
            created += 1
        else:
            updated += 1
    from .ims import classify_and_match

    classify_and_match(company, period, persist=True)
    return {"period": period, "created": created, "updated": updated}
