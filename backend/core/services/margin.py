"""Shared thin-margin check. Exactly 5% does not warn."""

from __future__ import annotations

from decimal import Decimal

MARGIN_THRESHOLD = Decimal("0.05")


def margin_ratio(price, cost) -> Decimal | None:
    price = Decimal(str(price or 0))
    cost = Decimal(str(cost or 0))
    if price <= 0 or cost <= 0:
        return None
    return (price - cost) / price


def margin_below_threshold(price, cost, threshold=MARGIN_THRESHOLD) -> bool:
    ratio = margin_ratio(price, cost)
    return ratio is not None and ratio < threshold
