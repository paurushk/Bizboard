"""Per-model price table for AiUsageLedger.cost_estimate (closes B9-024 for agents).

USD per 1M tokens (input, output). Maintained by hand; review when the provider or model changes.
An unknown model is recorded as cost 0 with ``priced=False`` so reports show "unpriced", not 0.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger("agents")

EFFECTIVE_FROM = "2026-10-21"
PRICES_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "claude-sonnet-4-20250514": (Decimal("3.00"), Decimal("15.00")),
    "claude-sonnet-5-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-5-5": (Decimal("1.00"), Decimal("5.00")),
}


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> tuple[Decimal, bool]:
    """Return (cost_usd, priced)."""
    price = PRICES_PER_MTOK.get((model or "").strip())
    if price is None:
        if model and model != "fake":
            logger.warning("agents.pricing: no price for model %s", model)
        return Decimal("0"), False
    cost = (Decimal(tokens_in) * price[0] + Decimal(tokens_out) * price[1]) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001")), True
