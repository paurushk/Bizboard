"""Fail-closed circuit breaker for outbound money-path HTTP.

Uses the Django cache so gunicorn workers share open/closed state. When the
circuit is open, callers must not proceed with a local Complete / charge.
"""

from __future__ import annotations

import time

from django.core.cache import cache

_ANY_OPEN_KEY = "cb:_any_open"


def any_open() -> bool:
    """True if a money-path circuit was tripped recently (Gate 1 /metrics gauge)."""
    try:
        return cache.get(_ANY_OPEN_KEY) is not None
    except Exception:  # noqa: BLE001
        return False


class CircuitOpenError(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Circuit '{name}' is open")


def call(name: str, fn, *, failure_threshold: int = 5, cooldown_seconds: int = 30):
    """Run ``fn``; trip open after ``failure_threshold`` consecutive failures."""
    open_key = f"cb:{name}:open_until"
    fail_key = f"cb:{name}:fails"
    open_until = cache.get(open_key)
    now = time.time()
    if open_until is not None and float(open_until) > now:
        raise CircuitOpenError(name)
    try:
        result = fn()
    except Exception:
        n = int(cache.get(fail_key) or 0) + 1
        ttl = max(int(cooldown_seconds) * 4, 60)
        cache.set(fail_key, n, timeout=ttl)
        if n >= int(failure_threshold):
            ttl = int(cooldown_seconds) + 5
            cache.set(open_key, now + int(cooldown_seconds), timeout=ttl)
            cache.set(_ANY_OPEN_KEY, "1", timeout=ttl)
        raise
    cache.delete(fail_key)
    cache.delete(open_key)
    return result


def reset(name: str) -> None:
    cache.delete(f"cb:{name}:open_until")
    cache.delete(f"cb:{name}:fails")
