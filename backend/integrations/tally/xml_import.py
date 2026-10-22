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
    for rate in item.iter("GSTRATE"):
        if (rate.text or "").strip():
            return str(abs(_amount(rate.text)))
    for detail in item.iter("RATEDETAILS.LIST"):
        if _txt(detail, "GSTRATEDUTYHEAD").lower() == "integrated tax":
            return str(abs(_amount(_txt(detail, "GSTRATE"))))
    return "18"


def _hsn(item) -> str:
    for hsn in item.iter("HSNCODE"):
        if (hsn.text or "").strip():
            return hsn.text.strip()
    return ""


def parse_tally_xml(file_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """Returns (rows for ``parse_tally_masters_rows``, bills)."""
    try:
        # _decode refuses any DOCTYPE/ENTITY, so no entity can be declared or expanded.
        root = ET.fromstring(_decode(file_bytes))  # noqa: S314
    except ET.ParseError as exc:
        raise BusinessRuleError(f"This is not a Tally XML export we can read ({exc}).") from exc
    rows: list[dict] = []
    bills: list[dict] = []
    for ledger in root.iter("LEDGER"):
        name = _name(ledger)
        group = _txt(ledger, "PARENT").lower()
        if not name or group not in CUSTOMER_GROUPS | SUPPLIER_GROUPS:
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
    if not rows:
        raise BusinessRuleError(
            "No Sundry Debtors, Sundry Creditors or stock items found. Export 'List of Accounts' and "
            "'Stock Items' from Tally as XML."
        )
    return rows, bills
