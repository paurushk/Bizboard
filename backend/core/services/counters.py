"""Cache counters that survive a key expiring between calls.

``cache.add(key, 0)`` followed by ``cache.incr(key)`` fails with ``ValueError`` when the key expires
between the two calls. ``incr`` first and fall back to ``add`` instead: if two callers race on a
missing key exactly one ``add`` wins and the other increments the winner's value.

Django's Redis ``incr`` is not one atomic step: it checks ``EXISTS`` and then sends ``INCRBY``. When
the key expires between the two, ``INCRBY`` re-creates it **with no TTL**, and a rate-limit or
lockout counter then never resets: the user is blocked until Redis is flushed (found 2026-10-23,
`planwave` ``api:u<id>`` at ttl -1). A result equal to ``delta`` means this call created the key, so
it sets the TTL again. Exactly one racer sees that value.
"""

from __future__ import annotations


def incr(key: str, delta: int, ttl: int) -> int:
    from django.core.cache import cache

    try:
        value = int(cache.incr(key, delta))
    except ValueError:
        if cache.add(key, delta, ttl):
            return int(delta)
        value = int(cache.incr(key, delta))
    if value == delta:
        cache.touch(key, ttl)
    return value
