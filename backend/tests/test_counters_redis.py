"""WP-AB1 on a real Redis: the shared counter is exact under concurrent workers, keeps its expiry,
and the SMS caps hold across processes. Runs only when TEST_REDIS_URL points at a throwaway Redis
(e.g. ``docker run --rm -p 127.0.0.1:56379:6379 redis:7-alpine`` and
``TEST_REDIS_URL=redis://127.0.0.1:56379/15``); the default suite uses LocMem.
"""

import os
import threading
import time
import uuid

import pytest
from django.core.cache import caches
from django.test import override_settings

REDIS = os.environ.get("TEST_REDIS_URL", "")
pytestmark = pytest.mark.skipif(not REDIS, reason="needs TEST_REDIS_URL (a throwaway Redis)")
_CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS}}


@override_settings(CACHES=_CACHES)
def test_concurrent_increments_are_exact():
    from core.services.counters import incr

    key = f"test:ctr:{uuid.uuid4().hex}"
    errors = []

    def worker():
        try:
            for _ in range(50):
                incr(key, 1, 60)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert int(caches["default"].get(key)) == 400


@override_settings(CACHES=_CACHES)
def test_the_first_increment_sets_an_expiry():
    from core.services.counters import incr

    key = f"test:ttl:{uuid.uuid4().hex}"
    assert incr(key, 1, 1) == 1
    time.sleep(1.6)
    assert caches["default"].get(key) is None
    assert incr(key, 1, 60) == 1  # starts again after expiry, no error


@override_settings(CACHES=_CACHES, SMS_PER_PHONE_HOUR=5, SMS_PER_PHONE_DAY=10, SMS_PER_RANGE_HOUR=30,
                   SMS_PLATFORM_DAILY_CAP=5000, SMS_GUARD_FAIL_CLOSED=True)
def test_per_phone_cap_holds_across_concurrent_senders():
    from core.services.sms_guard import SmsBlocked, check_and_count

    phone = "98" + str(uuid.uuid4().int)[:8]
    allowed, blocked = [], []

    def send():
        try:
            check_and_count(phone, "otp")
            allowed.append(1)
        except SmsBlocked:
            blocked.append(1)

    threads = [threading.Thread(target=send) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(allowed) == 5 and len(blocked) == 7
