"""DRF throttles key anonymous callers on the trusted X-Forwarded-For hop, not the raw header.

Without REST_FRAMEWORK["NUM_PROXIES"], DRF uses the whole X-Forwarded-For string as the
identity, so a client that sends a different value per request gets a new bucket each time.
nginx appends the peer it saw, so with one proxy the last hop is the client.
"""

from __future__ import annotations

import pytest
from django.conf import settings as django_settings
from django.test import override_settings
from rest_framework.request import Request
from rest_framework.settings import api_settings
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.throttling import AnonRateThrottle

pytestmark = pytest.mark.django_db


class _TwoPerMinute(AnonRateThrottle):
    scope = "test_two"
    rate = "2/min"


def _request(xff: str | None = None, remote: str = "10.0.0.1") -> Request:
    extra = {"REMOTE_ADDR": remote}
    if xff is not None:
        extra["HTTP_X_FORWARDED_FOR"] = xff
    return Request(APIRequestFactory().post("/x", **extra))


def test_num_proxies_follows_num_trusted_proxies():
    assert django_settings.REST_FRAMEWORK["NUM_PROXIES"] == django_settings.NUM_TRUSTED_PROXIES
    assert api_settings.NUM_PROXIES == 1


def test_spoofed_prefix_resolves_to_the_real_client_hop():
    throttle = _TwoPerMinute()
    a = throttle.get_ident(_request("1.1.1.1, 198.51.100.7"))
    b = throttle.get_ident(_request("evil, 2.2.2.2, 198.51.100.7"))
    assert a == b == "198.51.100.7"


def test_spoofed_prefix_does_not_create_a_new_bucket():
    throttle = _TwoPerMinute()
    view = object()
    allowed = [
        throttle.allow_request(_request(f"203.0.113.{i}, 198.51.100.8"), view) for i in range(3)
    ]
    assert allowed == [True, True, False]
    # A different real client still has its own bucket.
    assert throttle.allow_request(_request("203.0.113.1, 198.51.100.9"), view) is True


def test_direct_request_without_header_uses_remote_addr():
    throttle = _TwoPerMinute()
    view = object()
    assert throttle.get_ident(_request(remote="192.0.2.5")) == "192.0.2.5"
    assert throttle.allow_request(_request(remote="192.0.2.5"), view) is True
    assert throttle.allow_request(_request(remote="192.0.2.5"), view) is True
    assert throttle.allow_request(_request(remote="192.0.2.5"), view) is False
    assert throttle.allow_request(_request(remote="192.0.2.6"), view) is True


@override_settings(NUM_TRUSTED_PROXIES=2, REST_FRAMEWORK={**django_settings.REST_FRAMEWORK, "NUM_PROXIES": 2})
def test_two_proxies_pick_the_hop_the_edge_added():
    # Cloudflare / LB appends the client, nginx appends the edge's address.
    ident = _TwoPerMinute().get_ident(_request("1.1.1.1, 198.51.100.10, 172.18.0.5"))
    assert ident == "198.51.100.10"


@pytest.mark.parametrize(
    ("num", "xff"),
    [
        (1, "198.51.100.11"),
        (1, "1.1.1.1, 198.51.100.11"),
        (2, "1.1.1.1, 198.51.100.11, 172.18.0.5"),
        (2, "1.1.1.1, 2.2.2.2, 198.51.100.11, 172.18.0.5"),
    ],
)
def test_drf_throttles_and_login_lock_agree_on_the_client(num, xff):
    """planwave/ratelimit.py and the login lock use accounts.views._client_ip; DRF uses NUM_PROXIES."""
    from accounts.views import _client_ip
    from planwave.ratelimit import _client_ip as ratelimit_ip

    rest = {**django_settings.REST_FRAMEWORK, "NUM_PROXIES": num}
    with override_settings(DJANGO_ENV="production", NUM_TRUSTED_PROXIES=num, REST_FRAMEWORK=rest):
        req = _request(xff)
        assert _client_ip(req) == "198.51.100.11"
        assert _TwoPerMinute().get_ident(req) == _client_ip(req) == ratelimit_ip(req)


@override_settings(OPS_ALERT_TOKEN="")
def test_anon_endpoint_cannot_be_unthrottled_by_rotating_the_header():
    """OpsAlertWebhookThrottle (30/min): rotating a spoofed prefix used to reset the bucket."""
    client = APIClient()
    statuses = [
        client.post(
            "/api/v1/ops/alert/",
            {"message": "x"},
            format="json",
            HTTP_X_FORWARDED_FOR=f"203.0.113.{i}, 198.51.100.12",
            REMOTE_ADDR="10.0.0.1",
        ).status_code
        for i in range(31)
    ]
    assert 429 not in statuses[:30]
    assert statuses[30] == 429
