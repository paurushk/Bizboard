"""Per-company numbers that tune the forecast and purchase planning (INV-IDR-08).

They live in the company's ``feature_flags`` JSON beside the rollout flags, so an owner or support
can change one without a migration. Anything missing, not a whole number or out of range falls back
to the default, so a bad value never breaks the screen.
"""

from __future__ import annotations

FORECAST_WINDOW_DAYS = "FORECAST_WINDOW_DAYS"
FORECAST_COVER_DAYS = "FORECAST_COVER_DAYS"
REORDER_COVER_DAYS = "REORDER_COVER_DAYS"
PLANNING_DRAFT_PO_DAYS = "PLANNING_DRAFT_PO_DAYS"

# key -> (default, lowest, highest)
LIMITS = {
    FORECAST_WINDOW_DAYS: (30, 7, 90),
    FORECAST_COVER_DAYS: (30, 1, 180),
    REORDER_COVER_DAYS: (14, 1, 90),
    PLANNING_DRAFT_PO_DAYS: (30, 1, 365),
}


def number_setting(company, key: str) -> int:
    default, low, high = LIMITS[key]
    raw = (getattr(company, "feature_flags", None) or {}).get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default
