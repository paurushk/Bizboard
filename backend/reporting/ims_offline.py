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
    created = 0
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        obj = Gstr2bIngest.objects.create(
            company=company,
            period=period,
            supplier_gstin=(raw.get("supplier_gstin") or "")[:15],
            invoice_number=(raw.get("invoice_number") or "")[:64],
            invoice_date=_parse_date(raw.get("invoice_date")),
            taxable_value=raw.get("taxable_value") or 0,
            igst=raw.get("igst") or 0,
            cgst=raw.get("cgst") or 0,
            sgst=raw.get("sgst") or 0,
            cess=raw.get("cess") or 0,
            ims_action=(raw.get("ims_action") or Gstr2bIngest.ImsAction.NO_ACTION)[:16],
            ims_remark=(raw.get("remark") or "")[:512],
            match_class=(raw.get("match_class") or "")[:32],
            itc_eligibility=(raw.get("itc_eligibility") or Gstr2bIngest.ItcEligibility.UNREVIEWED)[:12],
            raw={**raw, "source": "OFFLINE"},
        )
        if raw.get("match_status") in dict(Gstr2bIngest.MatchStatus.choices):
            obj.match_status = raw["match_status"]
            obj.save(update_fields=["match_status", "updated_at"])
        created += 1
    from .ims import classify_and_match

    classify_and_match(company, period, persist=True)
    return {"period": period, "created": created}
