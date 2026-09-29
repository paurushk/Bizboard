"""Indian PIN coordinates for route distance.

Exact matches come from the vendored centroid file. A PIN that is not in
that file uses the mean of every known PIN that shares the longest prefix
(5 digits, then 4, 3, 2, 1). That still places the stop in the right
postal region instead of treating the PIN as a number.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "in_pincode_centroids.json"


@lru_cache(maxsize=1)
def _exact() -> dict[str, tuple[float, float]]:
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    return {pin: (float(pair[0]), float(pair[1])) for pin, pair in raw.items()}


@lru_cache(maxsize=8)
def _prefix_means(length: int) -> dict[str, tuple[float, float]]:
    buckets: dict[str, list[tuple[float, float]]] = {}
    for pin, point in _exact().items():
        buckets.setdefault(pin[:length], []).append(point)
    means = {}
    for prefix, points in buckets.items():
        lat = sum(point[0] for point in points) / len(points)
        lon = sum(point[1] for point in points) / len(points)
        means[prefix] = (lat, lon)
    return means


def coordinates_for_pincode(pincode: str) -> tuple[float, float] | None:
    pin = (pincode or "").strip()
    if not pin.isdigit():
        return None
    exact = _exact()
    if pin in exact:
        return exact[pin]
    for length in (5, 4, 3, 2, 1):
        if len(pin) < length:
            continue
        hit = _prefix_means(length).get(pin[:length])
        if hit is not None:
            return hit
    return None


def coordinates_for_stop(stop) -> tuple[float, float] | None:
    """Prefer an explicit lat/long. Otherwise look the PIN up."""
    lat = getattr(stop, "latitude", None)
    lon = getattr(stop, "longitude", None)
    if lat is not None and lon is not None:
        return (float(lat), float(lon))
    return coordinates_for_pincode(getattr(stop, "pincode", "") or "")
