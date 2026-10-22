"""Cache counters that survive a key expiring between calls.

``cache.add(key, 0)`` followed by ``cache.incr(key)`` fails with ``ValueError`` when the key expires
between the two calls. ``incr`` first and fall back to ``add`` instead: on Redis ``INCR`` is atomic and
keeps the key's TTL, and if two callers race on a missing key exactly one ``add`` wins and the other
increments the winner's value.
"""

from __future__ import annotations


def incr(key: str, delta: int, ttl: int) -> int:
    from django.core.cache import cache

    try:
        return int(cache.incr(key, delta))
    except ValueError:
        if cache.add(key, delta, ttl):
            return int(delta)
        return int(cache.incr(key, delta))
