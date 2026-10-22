"""Reading an order out of text with plain rules (no model). Also normalises text for matching.

This is the rules-only path: it needs no consent and no provider, and it is what the model's answer is
checked against (each line the model returns must come from the pasted text).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

MAX_LINES = 100
UNITS = {
    "kg", "kgs", "g", "gm", "gms", "l", "ltr", "ltrs", "litre", "liter", "litres", "ml", "pc", "pcs", "piece", "pieces",
    "no", "nos", "box", "boxes", "bag", "bags", "pkt", "pkts", "packet", "packets", "carton", "cartons", "ctn", "dozen",
    "doz", "bottle", "bottles", "btl", "tin", "tins", "bundle", "bundles", "set", "sets", "pair", "pairs", "bori", "peti",
}
_UNIT_ALT = "|".join(sorted(UNITS, key=len, reverse=True))
_NUM = r"\d+(?:[.,]\d+)?"
_HINT = re.compile(r"^\s*(?:order\s+from|from|customer|party|name|for|client|shop)\s*[:\-]\s*(.+?)\s*$", re.I)
_BULLET = re.compile(r"^\s*(?:[-*•]+|\d+[.)])\s+")
_QTY_FIRST = re.compile(rf"^\s*({_NUM})\s*({_UNIT_ALT})?\b\.?\s*(?:x|×|of|-|:)?\s*(.+?)\s*$", re.I)
_QTY_LAST = re.compile(rf"^\s*(.+?)\s*(?:x|×|-|:|=)?\s*({_NUM})\s*({_UNIT_ALT})?\.?\s*$", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})(?!\d)")
_STRIP = re.compile(r"[^\wऀ-ॿ ]+", re.U)


def normalize(text: str, limit: int | None = 255) -> str:
    """Lower-case, punctuation to spaces, single spaces. Devanagari is kept. ``limit`` caps the result (alias keys
    are at most 255 characters); pass None to compare against a whole pasted message."""
    return " ".join(_STRIP.sub(" ", (text or "").lower()).split())[:limit]


def phones_in(text: str) -> list[str]:
    return [re.sub(r"\D", "", m.group(1)) for m in _PHONE.finditer(text or "")]


def _qty(token: str) -> str | None:
    try:
        q = Decimal(token.replace(",", "."))
    except InvalidOperation:
        return None
    if q <= 0 or q > Decimal("1000000"):
        return None
    return format(q.normalize(), "f")


def parse_line(raw: str) -> dict | None:
    """``10 kg sugar``, ``sugar 10kg``, ``5 x Parle G``. A line with no quantity is kept with qty None."""
    line = _BULLET.sub("", raw).strip(" \t-")
    if not line:
        return None
    m = _QTY_FIRST.match(line)
    if m:
        qty, unit, name = _qty(m.group(1)), (m.group(2) or "").lower(), m.group(3)
    else:
        m = _QTY_LAST.match(line)
        if m:
            name, qty, unit = m.group(1), _qty(m.group(2)), (m.group(3) or "").lower()
        else:
            name, qty, unit = line, None, ""
    name = name.strip(" .,:;-")
    if not re.search(r"[^\W\d_]", name):  # a product needs at least one letter; "12" is not an order line
        return None
    return {"raw": raw.strip()[:300], "qty": qty, "unit": unit, "product_hint": name[:200]}


def parse_order(text: str) -> dict:
    """{customer_hint, lines:[{raw, qty, unit, product_hint}]} from pasted text, by rules only."""
    hint = ""
    lines: list[dict] = []
    for chunk in re.split(r"[\r\n;]+", text or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        h = _HINT.match(chunk)
        if h and not hint:
            hint = h.group(1)[:200]
            continue
        # A comma splits "5 kg sugar, 2 kg rice" but not a decimal ("2,5 kg" is handled by _NUM).
        for part in re.split(r",(?!\d)", chunk):
            parsed = parse_line(part)
            if parsed:
                lines.append(parsed)
    return {"customer_hint": hint, "lines": lines[:MAX_LINES]}
