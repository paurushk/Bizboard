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
from decimal import Decimal
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


_NUMBER = re.compile(r"^\(?-?\d+(?:\.\d+)?\)?$")


def _balance(text: str) -> tuple[Decimal, str] | None:
    """Parse one money cell: ``1,23,456.00``, ``Rs. 1,500``, ``₹500``, ``(500)``, ``-300``, and a
    trailing ``Dr``/``Cr``. Returns (amount with its sign, "dr"/"cr"/""), or None when the cell is
    not one number (refused as a row error instead of read as 0)."""
    raw = (text or "").strip()
    if not raw or raw in ("-", "--"):
        return Decimal("0"), ""
    side = ""
    m = re.search(r"\b(dr|cr|debit|credit)\.?\s*$", raw, re.I)
    if m:
        side = "dr" if m.group(1).lower().startswith("d") else "cr"
        raw = raw[: m.start()].strip()
    raw = re.sub(r"^(rs\.?|inr|₹)\s*", "", raw, flags=re.I).replace(",", "").replace(" ", "")
    if not _NUMBER.match(raw):
        return None
    negative = raw.startswith("(") or raw.startswith("-")
    value = Decimal(raw.strip("()").lstrip("-"))
    return (-value if negative else value), side


def _dec(text: str) -> Decimal:
    parsed = _balance(text)
    return parsed[0] if parsed else Decimal("0")


def _side(drcr: str, inline: str, signed: Decimal) -> str:
    """Which side the opening balance is on: the Dr/Cr column, else the cell's own suffix, else
    its sign (Busy and Marg export a credit balance as a negative number)."""
    d = (drcr or "").strip().lower()
    if d.startswith(("dr", "debit", "d")) or "receiv" in d:
        return "dr"
    if d.startswith(("cr", "credit", "c")) or "pay" in d:
        return "cr"
    if inline:
        return inline
    if signed < 0:
        return "cr"
    return "dr" if signed > 0 else ""


def _party_type(group: str, side: str) -> str:
    g = (group or "").lower()
    if "creditor" in g or "supplier" in g:
        return "supplier"
    if "debtor" in g or "customer" in g:
        return "customer"
    # No group: a credit balance is someone we owe (a supplier), a debit one owes us.
    return "supplier" if side == "cr" else "customer"


def _outstanding(entity: str, amount: Decimal, side: str) -> Decimal:
    """Positive = they owe us (customer) / we owe them (supplier); negative = an advance."""
    amount = abs(amount)
    if entity == "customer":
        return -amount if side == "cr" else amount
    return -amount if side == "dr" else amount


_PARTY_GROUP_WORDS = ("debtor", "creditor", "customer", "supplier")
_TOTAL_ROW = re.compile(r"^(grand\s+)?(sub\s*)?total\b", re.I)


def to_master_rows(source: str, rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict]]:
    """Map one exported sheet to Tally-importer rows. Returns (rows, errors). Each mapped row keeps
    its file row number (``_row``) so the preview's errors point at the right line; rows that are not
    parties (bank, cash, expense ledgers) or are report totals are listed as ``skipped`` errors-free
    notes in the preview."""
    if source not in SOURCES:
        raise BusinessRuleError("Pick Busy, Vyapar or Marg.", code="LEGACY_SOURCE_UNKNOWN")
    if not rows:
        return [], [{"row": 1, "error": "The file is empty."}]
    headers = {_key(h) for h in rows[0].keys()}
    party_map, item_map = _PARTY[source], _ITEM[source]
    # Score each kind on the columns only it has, so an item list with a "Group" column is still
    # read as items, and an ambiguous sheet is refused rather than guessed.
    item_score = sum(_has(headers, item_map[f]) for f in ("selling_price", "opening_qty", "hsn_code", "purchase_price"))
    party_score = sum(_has(headers, party_map[f]) for f in ("balance", "drcr", "gstin", "phone"))
    has_name = _has(headers, party_map["name"]) or _has(headers, item_map["name"])
    expected = sorted({party_map["name"][0], party_map["balance"][0], item_map["name"][0], item_map["selling_price"][0]})
    if not has_name or (item_score == 0 and party_score == 0) or (item_score and item_score == party_score):
        return [], [{
            "row": 1,
            "error": f"This does not look like a {LABELS[source]} party or item export. "
                     f"We look for columns such as: {', '.join(expected)}.",
        }]
    is_item = item_score > party_score
    out: list[dict[str, str]] = []
    errors: list[dict] = []
    for line, row in enumerate(rows, start=2):
        name = _pick(row, item_map["name"] if is_item else party_map["name"])
        if not name:
            continue
        if _TOTAL_ROW.match(name):
            out.append({"entity_type": "skipped", "name": name, "_row": str(line), "why": "a total row"})
            continue
        if is_item:
            out.append({
                "_row": str(line),
                "entity_type": "product",
                "name": name,
                "sku": _pick(row, item_map["sku"]),
                "hsn_code": _pick(row, item_map["hsn_code"]),
                "gst_rate": _pick(row, item_map["gst_rate"]),
                "purchase_price": str(_dec(_pick(row, item_map["purchase_price"]))),
                "selling_price": str(_dec(_pick(row, item_map["selling_price"]))),
                "opening_qty": str(abs(_dec(_pick(row, item_map["opening_qty"])))),
            })
            continue
        group = _pick(row, party_map["group"])
        if group and not any(w in group.lower() for w in _PARTY_GROUP_WORDS):
            # Bank, cash, expense, tax and "... Payable" ledgers are not parties.
            out.append({"entity_type": "skipped", "name": name, "_row": str(line), "why": f"group {group}"})
            continue
        balance_text = _pick(row, party_map["balance"])
        parsed = _balance(balance_text)
        if parsed is None:
            errors.append({"row": line, "error": f"Opening balance '{balance_text}' for '{name}' is not a number"})
            continue
        amount, inline_side = parsed
        side = _side(_pick(row, party_map["drcr"]), inline_side, amount)
        entity = _party_type(group, side)
        out.append({
            "_row": str(line),
            "entity_type": entity,
            "name": name,
            "phone": _pick(row, party_map["phone"]),
            "gstin": _pick(row, party_map["gstin"]).upper().replace(" ", ""),
            "state": _pick(row, party_map["state"]),
            "opening_outstanding": str(_outstanding(entity, amount, side)),
        })
    if not any(r["entity_type"] != "skipped" for r in out) and not errors:
        errors.append({"row": 1, "error": f"No parties or items were found in this {LABELS[source]} file."})
    return out, errors


def parse_legacy_file(source: str, file_bytes: bytes, filename: str = "") -> dict[str, Any]:
    from integrations.tally.adapter import _rows_from_upload, parse_tally_masters_rows

    rows = _rows_from_upload(file_bytes, filename)
    mapped, errors = to_master_rows(source, rows)
    skipped = [r for r in mapped if r["entity_type"] == "skipped"]
    mapped = [r for r in mapped if r["entity_type"] != "skipped"]
    preview = parse_tally_masters_rows(mapped)
    preview["errors"] = [*errors, *preview["errors"]]
    preview["counts"]["errors"] = len(preview["errors"])
    preview["summary"]["errors"] = len(preview["errors"])
    preview["notes"] = [
        *preview.get("notes", []),
        *({"row": int(r["_row"]), "warning": f"'{r['name']}' was not imported ({r['why']})."} for r in skipped[:200]),
    ]
    preview["counts"]["skipped"] = len(skipped)
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
