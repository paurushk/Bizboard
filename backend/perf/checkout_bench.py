"""POS checkout p95 comparison. The 20,000-SKU run is the nightly job, not a pull request."""

from __future__ import annotations


def exceeds_baseline(current_p95_ms: float, baseline_p95_ms: float, limit: float = 0.15) -> bool:
    """True when this run is more than `limit` slower than the recorded baseline."""
    if baseline_p95_ms <= 0:
        return False
    return float(current_p95_ms) > float(baseline_p95_ms) * (1 + limit)


def p95_ms(samples_ms: list[float]) -> float:
    if not samples_ms:
        return 0.0
    ordered = sorted(float(x) for x in samples_ms)
    index = max(0, int(round(0.95 * (len(ordered) - 1))))
    return ordered[index]
