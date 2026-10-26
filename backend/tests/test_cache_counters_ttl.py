"""core.services.counters keeps a TTL on every counter.

Django's Redis ``incr`` checks ``EXISTS`` and then sends ``INCRBY``. When the key expires between the
two, Redis re-creates it with no TTL; a rate-limit or lockout counter then never resets (2026-10-23:
`planwave` ``api:u<id>`` stuck at ttl -1, the user refused on every API call). These fakes replay
that interleaving.
"""

from __future__ import annotations

from unittest import mock

import pytest

from core.services import counters


class _RacyRedisCache:
    """Imitates django's RedisCache.incr when the key expires between EXISTS and INCRBY."""

    def __init__(self, existing=None):
        self.values = dict(existing or {})
        self.ttls = {k: 10 for k in self.values}
        self.expire_before_incr = set()

    def incr(self, key, delta=1):
        if key not in self.values:
            raise ValueError(f"Key '{key}' not found.")
        if key in self.expire_before_incr:  # EXISTS said yes, then the TTL ran out
            self.expire_before_incr.discard(key)
            del self.values[key]
            self.ttls.pop(key, None)
        self.values[key] = self.values.get(key, 0) + delta  # INCRBY on a missing key: no TTL
        return self.values[key]

    def add(self, key, value, timeout):
        if key in self.values:
            return False
        self.values[key], self.ttls[key] = value, timeout
        return True

    def touch(self, key, timeout):
        if key not in self.values:
            return False
        self.ttls[key] = timeout
        return True


@pytest.fixture
def racy():
    fake = _RacyRedisCache({"api:u15": 99})
    with mock.patch("django.core.cache.cache", fake):
        yield fake


def test_a_key_recreated_by_incr_gets_its_ttl_back(racy):
    racy.expire_before_incr.add("api:u15")
    assert counters.incr("api:u15", 1, 10) == 1
    assert racy.ttls["api:u15"] == 10  # without the fix: no TTL, the counter never resets


def test_normal_increment_leaves_the_window_alone(racy):
    racy.ttls["api:u15"] = 4
    assert counters.incr("api:u15", 1, 10) == 100
    assert racy.ttls["api:u15"] == 4  # a fixed window is not extended by traffic


def test_missing_key_is_seeded_with_ttl(racy):
    assert counters.incr("login_fail:x", 1, 900) == 1
    assert racy.ttls["login_fail:x"] == 900


def test_planwave_limit_resets_after_the_race(racy):
    from planwave.ratelimit import _hit

    racy.values["api:u15"] = 566
    assert _hit("api:u15", 100, 10) is False
    racy.expire_before_incr.add("api:u15")
    assert _hit("api:u15", 100, 10) is True
    assert racy.ttls["api:u15"] == 10


@pytest.mark.parametrize(
    "call",
    [
        lambda: __import__("accounts.views", fromlist=["_incr_with_ttl"])._incr_with_ttl("login_fail:a@b.c"),
        lambda: __import__("billing.reauth", fromlist=["_count_failure"])._count_failure(7),
    ],
)
def test_lockout_counters_use_the_ttl_safe_helper(racy, call):
    with mock.patch("core.services.counters.incr", wraps=counters.incr) as helper:
        call()
    helper.assert_called_once()
