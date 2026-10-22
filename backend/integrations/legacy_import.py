"""WP-GR1b: one-time import from Busy, Vyapar and Marg (parties, items, opening stock, outstanding).

Each tool's standard Excel/CSV export of its party (ledger/account) and item masters is mapped onto
the rows the Tally importer already takes (``entity_type``, ``name``, ``phone``, ``gstin``,
``state``, ``opening_outstanding``, ``sku``, ``hsn_code``, ``gst_rate``, ``purchase_price``,
``selling_price``, ``opening_qty``). From there it is the same path as Tally: preview, then commit
(``tally.adapter.commit_tally_preview``: party matching, opening balance documents, opening
stock) and the same post-commit reconciliation, so totals tie the same way.

The header names below come from each tool's documented standard exports. They must be confirmed
against 2–3 real anonymised files per source from pilots (plan §7 Q8) before a source is granted
to a company; until then a file whose headers do not match is refused with the list of headers
we expected, never guessed at. Same gating as GR1a: ``ENABLE_LEGACY_IMPORT`` is off by default
and in trials, and staff grant it per pilot company with the "Grant or revoke a rollout flag"
admin action.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from core.exceptions import BusinessRuleError

SOURCES = ("busy", "vyapar", "marg")
LABELS = {"busy": "Busy", "vyapar": "Vyapar", "marg": "Marg ERP"}

# field -> header aliases (compared case-insensitively, ignoring punctuation and spaces).
_PARTY = {
    "busy": {
        "name": ("name", "account name", "ledger name"),
        "group": ("group", "parent group", "under group"),
        "phone": ("mobile no", "mobile", "phone", "contact no"),
        "gstin": ("gstin", "gst no", "gstin uin"),
        "state": ("state",),
        "balance": ("op bal", "opening balance", "op balance"),
        "drcr": ("dr cr", "drcr", "balance type"),
    },
    "vyapar": {
        "name": ("name", "party name"),
        "group": ("party type", "party group", "group"),
        "phone": ("phone no", "phone number", "phone", "mobile"),
        "gstin": ("gstin", "gst number"),
        "state": ("state",),
        "balance": ("opening balance", "balance"),
        "drcr": ("balance type", "receivable payable", "to receive to pay"),
    },
    "marg": {
        "name": ("ledger name", "name", "party name"),
        "group": ("group", "group name"),
        "phone": ("mobile", "mobile no", "phone"),
        "gstin": ("gst no", "gstin", "gstn"),
        "state": ("state",),
        "balance": ("opening balance", "op balance", "opening"),
        "drcr": ("dr cr", "drcr", "type"),
    },
}
_ITEM = {
    "busy": {
        "name": ("name", "item name"),
        "sku": ("alias", "item code", "code"),
        "hsn_code": ("hsn sac code", "hsn code", "hsn"),
        "gst_rate": ("gst rate", "tax rate", "gst"),
        "purchase_price": ("purchase price", "purc price", "purchase rate"),
        "selling_price": ("sale price", "sales price", "selling price"),
        "opening_qty": ("op stock qty", "opening stock", "op stock"),
    },
    "vyapar": {
        "name": ("item name", "name"),
        "sku": ("item code", "code"),
        "hsn_code": ("hsn", "hsn code", "hsn sac"),
        "gst_rate": ("tax rate", "gst rate", "gst"),
        "purchase_price": ("purchase price", "purchase rate"),
        "selling_price": ("sale price", "sales price", "selling price"),
        "opening_qty": ("opening stock quantity", "opening quantity", "opening stock"),
    },
    "marg": {
        "name": ("product name", "item name", "name"),
        "sku": ("product code", "item code", "code"),
        "hsn_code": ("hsn code", "hsn"),
        "gst_rate": ("gst", "gst rate", "tax"),
        "purchase_price": ("purchase rate", "p rate", "purchase price"),
        "selling_price": ("sale rate", "s rate", "selling price", "mrp"),
        "opening_qty": ("opening stock", "op stock", "opening qty"),
    },
}


def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (header or "").lower()).strip()


def _pick(row: dict[str, str], aliases: tuple[str, ...]) -> str:
    keyed = {_key(k): v for k, v in row.items()}
    for alias in aliases:
        value = keyed.get(alias)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _has(headers: set[str], aliases: tuple[str, ...]) -> bool:
    return any(a in headers for a in aliases)


def _dec(text: str) -> Decimal:
    cleaned = re.sub(r"[^0-9.\-]", "", text or "")
    try:
        return Decimal(cleaned or "0")
    except InvalidOperation:
        return Decimal("0")


def _party_type(source: str, group: str, drcr: str, balance: Decimal) -> str:
    g = (group or "").lower()
    if "creditor" in g or "supplier" in g or "payable" in g:
        return "supplier"
    if "debtor" in g or "customer" in g or "receivable" in g:
        return "customer"
    d = (drcr or "").lower()
    if source == "vyapar" and ("pay" in d):
        return "supplier"
    return "customer"


def _outstanding(entity: str, balance: Decimal, drcr: str) -> Decimal:
    """Positive = they owe us (customer) / we owe them (supplier); negative = an advance."""
    d = (drcr or "").lower()
    credit = d.startswith("cr") or "pay" in d
    debit = d.startswith("dr") or "receiv" in d
    amount = abs(balance)
    if entity == "customer":
        return -amount if credit else amount
    return -amount if debit else amount


def to_master_rows(source: str, rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict]]:
    """Map one exported sheet to Tally-importer rows. Returns (rows, errors)."""
    if source not in SOURCES:
        raise BusinessRuleError("Pick Busy, Vyapar or Marg.", code="LEGACY_SOURCE_UNKNOWN")
    if not rows:
        return [], [{"row": 1, "error": "The file is empty."}]
    headers = {_key(h) for h in rows[0].keys()}
    party_map, item_map = _PARTY[source], _ITEM[source]
    is_item = _has(headers, item_map["selling_price"]) or _has(headers, item_map["opening_qty"]) \
        or _has(headers, item_map["hsn_code"])
    is_party = _has(headers, party_map["group"]) or _has(headers, party_map["balance"]) \
        or _has(headers, party_map["gstin"])
    if not (is_item or is_party) or not (_has(headers, party_map["name"]) or _has(headers, item_map["name"])):
        expected = sorted({party_map["name"][0], party_map["balance"][0], item_map["name"][0], item_map["selling_price"][0]})
        return [], [{
            "row": 1,
            "error": f"This does not look like a {LABELS[source]} party or item export. "
                     f"We look for columns such as: {', '.join(expected)}.",
        }]
    out: list[dict[str, str]] = []
    errors: list[dict] = []
    for row in rows:
        if is_item and not is_party:
            name = _pick(row, item_map["name"])
            if not name:
                continue
            out.append({
                "entity_type": "product",
                "name": name,
                "sku": _pick(row, item_map["sku"]),
                "hsn_code": re.sub(r"\D", "", _pick(row, item_map["hsn_code"]))[:8],
                "gst_rate": str(_dec(_pick(row, item_map["gst_rate"]) or "18")),
                "purchase_price": str(_dec(_pick(row, item_map["purchase_price"]))),
                "selling_price": str(_dec(_pick(row, item_map["selling_price"]))),
                "opening_qty": str(_dec(_pick(row, item_map["opening_qty"]))),
            })
            continue
        name = _pick(row, party_map["name"])
        if not name:
            continue
        group = _pick(row, party_map["group"])
        if group and not any(w in group.lower() for w in ("debtor", "creditor", "customer", "supplier",
                                                            "receivable", "payable")):
            continue  # bank, cash, expense and tax ledgers are not parties
        balance = _dec(_pick(row, party_map["balance"]))
        drcr = _pick(row, party_map["drcr"])
        entity = _party_type(source, group, drcr, balance)
        out.append({
            "entity_type": entity,
            "name": name,
            "phone": re.sub(r"[^0-9+]", "", _pick(row, party_map["phone"]))[-13:],
            "gstin": _pick(row, party_map["gstin"]).upper().replace(" ", ""),
            "state": _pick(row, party_map["state"]),
            "opening_outstanding": str(_outstanding(entity, balance, drcr)),
        })
    return out, errors


def parse_legacy_file(source: str, file_bytes: bytes, filename: str = "") -> dict[str, Any]:
    from integrations.tally.adapter import _rows_from_upload, parse_tally_masters_rows

    rows = _rows_from_upload(file_bytes, filename)
    mapped, errors = to_master_rows(source, rows)
    preview = parse_tally_masters_rows(mapped) if mapped else parse_tally_masters_rows([])
    preview["errors"] = [*errors, *preview["errors"]]
    preview["counts"]["errors"] = len(preview["errors"])
    preview["summary"]["errors"] = len(preview["errors"])
    preview["source"] = source
    preview["source_format"] = f"{source}_export"
    return preview


def create_legacy_run(company, user, uploaded_file, source: str):
    from core.models import FileAsset
    from core.services.files import FileService

    from .models import IntegrationSyncRun

    if source not in SOURCES:
        raise BusinessRuleError("Pick Busy, Vyapar or Marg.", code="LEGACY_SOURCE_UNKNOWN")
    asset = FileService.store_upload(company=company, uploaded_file=uploaded_file, kind=FileAsset.Kind.IMPORT, user=user)
    raw = asset.file.read()
    if hasattr(asset.file, "seek"):
        asset.file.seek(0)
    preview = parse_legacy_file(source, raw, getattr(uploaded_file, "name", "") or asset.original_name or "")
    return IntegrationSyncRun.objects.create(
        company=company,
        kind=IntegrationSyncRun.Kind.LEGACY_IMPORT,
        status=IntegrationSyncRun.Status.PREVIEWED if not preview["errors"] else IntegrationSyncRun.Status.UPLOADED,
        file=asset,
        preview=preview,
        errors=preview.get("errors") or [],
        counts=preview.get("counts") or {},
        created_by=user,
    )
