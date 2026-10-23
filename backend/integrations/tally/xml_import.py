"""WP-GR1a: read a Tally XML masters export (ledgers, stock items, bill-wise outstanding).

Tally (Prime / ERP 9) exports masters as XML from Gateway → Display → List of Accounts →
Export (format XML), usually UTF-16. This turns it into the same rows the CSV/XLSX importer takes
(``entity_type``, ``name``, ``gstin``, ``state``, ``opening_outstanding``, product columns), plus
``bills``: one row per open bill (``BILLALLOCATIONS.LIST``) so opening receivables and payables keep
their own references and due dates and age correctly.

Tally conventions: a debit opening balance is negative (``-5000.00`` = Dr 5,000). Sundry Debtors
are customers (their Dr balance is what they owe); Sundry Creditors are suppliers (their Cr
balance, positive in the file, is what we owe). Stock opening is ``"10 Nos"`` / value ``-1200``.

The file is untrusted: documents with a DOCTYPE or ENTITY declaration are refused, and the
standard parser never fetches external entities.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from core.exceptions import BusinessRuleError

CUSTOMER_GROUPS = {"sundry debtors"}
SUPPLIER_GROUPS = {"sundry creditors"}
# Tally's own primary groups that never hold parties: not worth a "skipped" line in the preview.
_NON_PARTY_GROUPS = {
    "bank accounts", "cash-in-hand", "duties & taxes", "direct expenses", "indirect expenses", "direct incomes",
    "indirect incomes", "sales accounts", "purchase accounts", "capital account", "fixed assets",
    "current assets", "current liabilities", "loans (liability)", "loans & advances (asset)", "provisions",
    "reserves & surplus", "stock-in-hand", "suspense a/c", "bank od a/c", "secured loans", "unsecured loans",
    "deposits (asset)", "investments", "misc. expenses (asset)", "branch / divisions",
}
_BAD_CHARREF = re.compile(r"&#(?:x0*[0-8bcef]|x0*1[0-9a-f]|0*(?:[0-8]|1[1-2]|1[4-9]|2[0-9]|3[01]));", re.I)


def looks_like_xml(file_bytes: bytes, filename: str = "") -> bool:
    if (filename or "").lower().endswith(".xml"):
        return True
    head = file_bytes[:200]
    return head.startswith((b"\xff\xfe", b"\xfe\xff")) or head.lstrip().startswith(b"<")


def _decode(file_bytes: bytes) -> str:
    if file_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = file_bytes.decode("utf-16")
    else:
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = file_bytes.decode("utf-16", errors="replace")
    if re.search(r"<!(?:DOCTYPE|ENTITY)", text, re.I):
        raise BusinessRuleError("This XML file has a DOCTYPE or ENTITY declaration, so it was not read.")
    # Tally writes control characters as character references, which XML 1.0 does not allow.
    text = _BAD_CHARREF.sub("", text)
    return re.sub(r"^<\?xml[^>]*\?>", "", text.strip())


def _txt(el, tag: str) -> str:
    found = el.find(tag)
    return (found.text or "").strip() if found is not None and found.text else ""


def _amount(raw: str) -> Decimal:
    m = re.search(r"-?[\d,]+(?:\.\d+)?", raw or "")
    if not m:
        return Decimal("0")
    try:
        return Decimal(m.group(0).replace(",", ""))
    except InvalidOperation:
        return Decimal("0")


def _qty(raw: str) -> Decimal:
    return abs(_amount(raw))


def _tally_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    for fmt in ("%Y%m%d", "%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _name(el) -> str:
    return (el.get("NAME") or _txt(el, "NAME") or _txt(el, "NAME.LIST/NAME")).strip()


def _gstin(ledger) -> str:
    for path in ("PARTYGSTIN", "GSTIN", "LEDGSTREGDETAILS.LIST/GSTIN"):
        value = _txt(ledger, path)
        if value:
            return value.upper()
    return ""


def _state(ledger) -> str:
    for path in ("LEDSTATENAME", "STATENAME", "LEDMAILINGDETAILS.LIST/STATE"):
        value = _txt(ledger, path)
        if value:
            return value
    return ""


def _gst_rate(item) -> str:
    """The item's GST rate from its latest ``GSTDETAILS.LIST``: the Integrated Tax head, else Central
    + State (Tally lists CGST 9 / SGST 9 / IGST 18 — the first GSTRATE found is half the rate).
    Blank when the item carries none (the importer then uses its default)."""
    details = list(item.iter("GSTDETAILS.LIST")) or [item]
    latest = max(details, key=lambda d: _tally_date(_txt(d, "APPLICABLEFROM")) or date.min)
    heads: dict[str, Decimal] = {}
    for detail in latest.iter("RATEDETAILS.LIST"):
        head = _txt(detail, "GSTRATEDUTYHEAD").lower()
        rate = _txt(detail, "GSTRATE")
        if head and rate:
            heads[head] = abs(_amount(rate))
    if "integrated tax" in heads:
        return format(heads["integrated tax"].normalize(), "f")
    if "central tax" in heads and ("state tax" in heads or "ut tax" in heads):
        total = heads["central tax"] + heads.get("state tax", heads.get("ut tax", Decimal("0")))
        return format(total.normalize(), "f")
    direct = _txt(latest, "GSTRATE")
    return format(abs(_amount(direct)).normalize(), "f") if direct else ""


def _hsn(item) -> str:
    for hsn in item.iter("HSNCODE"):
        if (hsn.text or "").strip():
            return re.sub(r"\D", "", hsn.text)  # "8471 30 10" -> "84713010"
    return ""


def _primary_groups(root) -> dict[str, str]:
    """Each group's top-level (primary) group, lower-cased, walking ``PARENT`` up: a party under
    "Debtors - Pune" (a sub-group of Sundry Debtors) is still a debtor."""
    parent: dict[str, str] = {}
    for group in root.iter("GROUP"):
        name = _name(group).lower()
        if name:
            parent[name] = _txt(group, "PARENT").lower()
    out: dict[str, str] = {}
    for name in parent:
        seen, cur = set(), name
        while parent.get(cur) and cur not in seen and cur not in CUSTOMER_GROUPS | SUPPLIER_GROUPS:
            seen.add(cur)
            cur = parent[cur]
        out[name] = cur
    return out


def parse_tally_xml(file_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """Returns (rows for ``parse_tally_masters_rows``, bills)."""
    try:
        # _decode refuses any DOCTYPE/ENTITY, so no entity can be declared or expanded.
        root = ET.fromstring(_decode(file_bytes))  # noqa: S314
    except ET.ParseError as exc:
        raise BusinessRuleError(f"This is not a Tally XML export we can read ({exc}).") from exc
    rows: list[dict] = []
    bills: list[dict] = []
    primary = _primary_groups(root)
    for ledger in root.iter("LEDGER"):
        name = _name(ledger)
        parent = _txt(ledger, "PARENT").lower()
        group = primary.get(parent, parent)
        if not name:
            continue
        if group not in CUSTOMER_GROUPS | SUPPLIER_GROUPS:
            # Bank, cash, tax and expense ledgers are not parties. Listed (not counted as an error)
            # so a party under a group we could not place is visible in the preview.
            if _amount(_txt(ledger, "OPENINGBALANCE")) and parent not in _NON_PARTY_GROUPS:
                rows.append({"entity_type": "skipped", "name": name, "group": _txt(ledger, "PARENT")})
            continue
        is_customer = group in CUSTOMER_GROUPS
        opening = _amount(_txt(ledger, "OPENINGBALANCE"))
        # Debtor owes us when Dr (negative in Tally); we owe a creditor when Cr (positive).
        outstanding = -opening if is_customer else opening
        rows.append({
            "entity_type": "customer" if is_customer else "supplier",
            "name": name,
            "gstin": _gstin(ledger),
            "state": _state(ledger),
            "phone": _txt(ledger, "LEDGERPHONE") or _txt(ledger, "LEDGERMOBILE"),
            "opening_outstanding": str(max(outstanding, Decimal("0"))),
        })
        for bill in ledger.iter("BILLALLOCATIONS.LIST"):
            amount = _amount(_txt(bill, "OPENINGBALANCE"))
            amount = -amount if is_customer else amount
            if amount <= 0:
                continue
            bill_date = _tally_date(_txt(bill, "BILLDATE"))
            credit_days = int(abs(_amount(_txt(bill, "BILLCREDITPERIOD")))) if _txt(bill, "BILLCREDITPERIOD") else 0
            due = bill_date + timedelta(days=credit_days) if bill_date else None
            bills.append({
                "entity_type": "customer" if is_customer else "supplier",
                "party": name,
                "ref": (_txt(bill, "NAME") or "")[:60],
                "bill_date": bill_date.isoformat() if bill_date else "",
                "due_date": due.isoformat() if due else "",
                "amount": str(amount),
            })
    for item in root.iter("STOCKITEM"):
        name = _name(item)
        if not name:
            continue
        qty = _qty(_txt(item, "OPENINGBALANCE"))
        value = abs(_amount(_txt(item, "OPENINGVALUE")))
        rate = abs(_amount(_txt(item, "OPENINGRATE"))) or ((value / qty).quantize(Decimal("0.01")) if qty else Decimal("0"))
        rows.append({
            "entity_type": "product",
            "name": name,
            "sku": (_txt(item, "PARTNO") or name)[:64],
            "hsn_code": _hsn(item),
            "gst_rate": _gst_rate(item),
            "purchase_price": str(rate),
            "selling_price": "0",
            "reorder_level": str(_qty(_txt(item, "REORDERBASE"))),
            "opening_qty": str(qty),
        })
    if not any(r.get("entity_type") != "skipped" for r in rows):
        raise BusinessRuleError(
            "No Sundry Debtors, Sundry Creditors or stock items found. Export 'List of Accounts' and "
            "'Stock Items' from Tally as XML."
        )
    return rows, bills
