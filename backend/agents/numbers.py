"""'No invented numbers' validator for drafted text (plan 3.9).

A draft passes only if every number it contains can be traced to the facts the deterministic layer
supplied. Indian formatting is normalised first: ``₹1,25,000.00`` == ``125000``; ``1.25 lakh`` ==
``125000``; ``2 crore`` == ``20000000``; Devanagari digits are converted. Dates are matched
separately. Small counts up to the number of cited items are allowed ("3 invoices" when 3 cited).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable

_DEVANAGARI = {ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")}
_UNIT = {"lakh": Decimal(100_000), "lakhs": Decimal(100_000), "lac": Decimal(100_000), "l": Decimal(100_000),
         "crore": Decimal(10_000_000), "crores": Decimal(10_000_000), "cr": Decimal(10_000_000),
         "k": Decimal(1000), "thousand": Decimal(1000)}
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

_DATE_NUM = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
_DATE_TXT = re.compile(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:\s+(\d{2,4}))?\b", re.I)
_NUMBER = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?:\s*(lakhs?|lac|crores?|cr|k|thousand|l)\b)?", re.I)


def _norm_digits(text: str) -> str:
    return str(text or "").translate(_DEVANAGARI)


def _year(y: str | None, default: int | None = None) -> int | None:
    if not y:
        return default
    n = int(y)
    return 2000 + n if n < 100 else n


def extract_dates(text: str) -> tuple[set[tuple], str]:
    """Return ({(day, month, year|None)}, text with dates removed)."""
    text = _norm_digits(text)
    found: set[tuple] = set()

    def num(m):
        d, mo, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
        found.add((d, mo, y))
        return " "

    def txt(m):
        found.add((int(m.group(1)), _MONTHS[m.group(2).lower()[:3]], _year(m.group(3))))
        return " "

    text = _DATE_NUM.sub(num, text)
    text = _DATE_TXT.sub(txt, text)
    return found, text


def extract_numbers(text: str) -> list[Decimal]:
    _, rest = extract_dates(text)
    out: list[Decimal] = []
    for m in _NUMBER.finditer(rest):
        try:
            value = Decimal(m.group(1).replace(",", ""))
        except InvalidOperation:
            continue
        unit = (m.group(2) or "").lower()
        if unit:
            value *= _UNIT[unit]
        out.append(value.normalize())
    return out


def fact_numbers(facts: Iterable) -> set[Decimal]:
    """Flatten any nested facts (numbers, numeric strings, dates are ignored here) to a Decimal set."""
    out: set[Decimal] = set()

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float, Decimal)):
            try:
                out.add(Decimal(str(v)).normalize())
            except InvalidOperation:
                pass
        elif isinstance(v, str):
            out.update(extract_numbers(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple, set)):
            for x in v:
                walk(x)

    walk(facts)
    # Paise facts also license their rupee form.
    for n in list(out):
        out.add((n / Decimal(100)).normalize())
    return out


def fact_dates(facts: Iterable) -> set[tuple]:
    out: set[tuple] = set()

    def walk(v):
        if isinstance(v, date):
            out.add((v.day, v.month, v.year))
        elif isinstance(v, str):
            found, _ = extract_dates(v)
            out.update(found)
            try:
                d = date.fromisoformat(v[:10])
                out.add((d.day, d.month, d.year))
            except ValueError:
                pass
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple, set)):
            for x in v:
                walk(x)

    walk(facts)
    return out


def invented_numbers(text: str, facts, *, cited_count: int = 0, allowed: Iterable = ()) -> list[str]:
    """Return numbers or dates in ``text`` that are not traceable to ``facts``. Empty list = pass."""
    allowed_set = {Decimal(str(a)).normalize() for a in allowed}
    known = fact_numbers(facts) | allowed_set
    known_dates = fact_dates(facts)
    bad: list[str] = []

    dates, _ = extract_dates(text)
    for d, mo, y in sorted(dates, key=lambda t: (t[2] or 0, t[1], t[0])):
        ok = any(kd[0] == d and kd[1] == mo and (y is None or kd[2] == y) for kd in known_dates)
        if not ok:
            bad.append(f"date {d:02d}/{mo:02d}" + (f"/{y}" if y else ""))
    for n in extract_numbers(text):
        if n in known:
            continue
        if n == n.to_integral_value() and 0 <= n <= max(cited_count, 0):
            continue
        bad.append(str(n))
    return bad


def passes(text: str, facts, **kw) -> bool:
    return not invented_numbers(text, facts, **kw)
