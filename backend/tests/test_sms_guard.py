"""WP-AB1: caps in front of every SMS send; a refusal never leaks whether a number is registered."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from unittest import mock

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings

from core.services import counters, sms_guard
from core.services.sms import SmsProvider
from core.services.sms_guard import SmsBlocked

PHONE = "+919820012345"
NO_CAPS = dict(SMS_PER_PHONE_HOUR=0, SMS_PER_PHONE_DAY=0, SMS_PER_RANGE_HOUR=0, SMS_PLATFORM_DAILY_CAP=0)


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    yield
    cache.clear()


def _sends(phone, n):
    ok = 0
    for _ in range(n):
        try:
            sms_guard.check_and_count(phone, "otp")
            ok += 1
        except SmsBlocked:
            pass
    return ok


@override_settings(**{**NO_CAPS, "SMS_PER_PHONE_HOUR": 3})
def test_per_phone_hour_cap_trips_exactly_at_the_boundary():
    assert _sends(PHONE, 5) == 3


@override_settings(**{**NO_CAPS, "SMS_PER_PHONE_DAY": 4})
def test_per_phone_day_cap():
    assert _sends(PHONE, 6) == 4


@override_settings(**{**NO_CAPS, "SMS_PER_RANGE_HOUR": 3, "SMS_RANGE_PREFIX_LEN": 4})
def test_number_range_cap_covers_many_numbers_in_one_series():
    sent = sum(_sends(f"+91982001{i:04d}", 1) for i in range(6))
    assert sent == 3
    # A different 4-digit series is not affected.
    assert _sends("+919900012345", 1) == 1


@override_settings(**{**NO_CAPS, "SMS_PLATFORM_DAILY_CAP": 10})
def test_platform_cap_cannot_be_overshot_under_concurrency():
    def one(i):
        try:
            sms_guard.check_and_count(f"+9198{i:08d}", "otp")
            return True
        except SmsBlocked:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed = list(pool.map(one, range(30)))
    assert sum(allowed) == 10
    assert sms_guard.status()["platform_today"] == 10


@override_settings(**{**NO_CAPS, "SMS_PER_PHONE_HOUR": 2})
def test_a_refused_send_does_not_use_up_budget_but_a_failed_provider_send_does():
    assert _sends(PHONE, 2) == 2
    with pytest.raises(SmsBlocked):
        sms_guard.check_and_count(PHONE, "otp")
    # The refusal was rolled back: every counter still reads 2, not 3 (the per-phone one refused,
    # so check it directly; the platform one is last and was never reached).
    phone_hour_key = sms_guard._counters(sms_guard._digits(PHONE), "otp")[0][0]
    assert int(cache.get(phone_hour_key) or 0) == 2
    assert sms_guard.status()["platform_today"] == 2

    cache.clear()
    with mock.patch.object(SmsProvider, "_send_otp", side_effect=RuntimeError("provider 500")):
        for _ in range(2):
            with pytest.raises(RuntimeError):
                SmsProvider.send_otp(PHONE, "123456")
    with pytest.raises(SmsBlocked):
        SmsProvider.send_otp(PHONE, "123456")


@override_settings(**NO_CAPS)
def test_international_numbers_are_refused_unless_allowed():
    with pytest.raises(SmsBlocked):
        sms_guard.check_and_count("+14155550100", "otp")
    with override_settings(SMS_ALLOW_INTERNATIONAL=True):
        sms_guard.check_and_count("+14155550100", "otp")


@override_settings(**{**NO_CAPS, "SMS_PER_PHONE_HOUR": 1})
def test_ten_digit_and_plus_91_forms_are_the_same_indian_number():
    sms_guard.check_and_count("9820012345", "text")  # stored customer phone, no country code
    for same in ("+919820012345", "09820012345", "+91 98200 12345"):
        with pytest.raises(SmsBlocked):
            sms_guard.check_and_count(same, "text")


@override_settings(**NO_CAPS)
def test_kill_switches():
    with override_settings(SMS_DISABLED=True):
        with pytest.raises(SmsBlocked):
            sms_guard.check_and_count(PHONE, "otp")
    out = StringIO()
    call_command("sms_guard", "kill", "on", stdout=out)
    assert "kill_switch=on" in out.getvalue()
    with pytest.raises(SmsBlocked):
        sms_guard.check_and_count(PHONE, "otp")
    call_command("sms_guard", "kill", "off", stdout=StringIO())
    sms_guard.check_and_count(PHONE, "otp")


@override_settings(**NO_CAPS)
def test_counter_store_down_fails_closed():
    with mock.patch("core.services.counters.incr", side_effect=ConnectionError("redis down")):
        with pytest.raises(SmsBlocked):
            sms_guard.check_and_count(PHONE, "otp")
        with override_settings(SMS_GUARD_FAIL_CLOSED=False):
            sms_guard.check_and_count(PHONE, "otp")


def test_counter_survives_a_key_expiring_between_calls():
    """The old add-then-incr pattern raised ValueError here."""
    real_incr = cache.incr
    calls = {"n": 0}

    def flaky(key, delta=1, version=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("Key not found")  # expired just now
        return real_incr(key, delta, version)

    with mock.patch.object(cache, "incr", side_effect=flaky):
        assert counters.incr("k", 1, 60) == 1
    assert counters.incr("k", 1, 60) == 2


@override_settings(**{**NO_CAPS, "SMS_PER_PHONE_HOUR": 1})
def test_otp_view_answers_the_same_when_the_guard_refuses(client, django_user_model):
    django_user_model.objects.create_user(email="otp-guard@example.com", password="x-Pass-123", phone=PHONE)
    with override_settings(SMS_PER_PHONE_HOUR=0, SMS_DISABLED=True):
        blocked = client.post("/api/v1/auth/otp/request/", {"phone": PHONE}, content_type="application/json")
    unknown = client.post("/api/v1/auth/otp/request/", {"phone": "+919811111111"}, content_type="application/json")
    assert blocked.status_code == unknown.status_code == 200
    # Compare the envelopes' data (camelCased): same answer, and no code echoed for the refused one.
    assert blocked.json()["data"].get("detail") == unknown.json()["data"].get("detail")
    assert "debugCode" not in blocked.json()["data"]


def test_keys_never_hold_the_raw_number():
    keys = [k for k, *_rest in sms_guard._counters("919820012345")]
    assert not any("9820012345" in k for k in keys)
