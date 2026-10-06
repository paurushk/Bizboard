"""Indian fiscal time buckets for sales and purchase registers (BUG-UI-032)."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _bucket_key(day: date, bucket: str) -> str:
    kind = (bucket or "").lower()
    if kind == "day":
        return day.isoformat()
    if kind == "week":
        start = day - timedelta(days=day.weekday())
        return start.isoformat()
    if kind == "month":
        return f"{day.year:04d}-{day.month:02d}"
    if kind == "fy":
        start_year = day.year if day.month >= 4 else day.year - 1
        return f"FY{start_year}-{str(start_year + 1)[-2:]}"
    raise ValueError(f"Unknown time bucket {bucket!r}")


def group_register_rows(rows, *, bucket: str, date_key: str = "date", amount_key: str = "grand_total") -> list[dict]:
    grouped: OrderedDict[str, dict] = OrderedDict()
    for row in rows or []:
        day = _as_date(row.get(date_key))
        if day is None:
            continue
        key = _bucket_key(day, bucket)
        slot = grouped.setdefault(key, {"bucket": key, "count": 0, "grand_total": Decimal("0")})
        slot["count"] += 1
        slot["grand_total"] += Decimal(str(row.get(amount_key) or 0))
    return list(grouped.values())
