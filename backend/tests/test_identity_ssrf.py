"""HttpIdentityProvider must not fetch private or redirected addresses."""

from __future__ import annotations

import socket
import urllib.error

import pytest

from core.services.identity_verify import HttpIdentityProvider, _NoRedirect, _pin_target, open_pinned_url


def _dns(ip: str):
    def getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, port))]

    return getaddrinfo


@pytest.mark.django_db
def test_private_mapped_and_localhost_rules(settings, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(AssertionError("dns")))
    settings.DJANGO_ENV = "production"
    settings.IDENTITY_SANDBOX_BASE_URL = "http://169.254.169.254"
    assert HttpIdentityProvider()._get("/latest") == {"error": "lookup_failed"}

    settings.IDENTITY_SANDBOX_BASE_URL = "https://10.1.2.3"
    assert HttpIdentityProvider()._get("/pan/ABCDE1234F") == {"error": "lookup_failed"}
    assert isinstance(_pin_target("https://[::ffff:10.0.0.1]/pan/ABCDE1234F"), dict)
    assert isinstance(_pin_target("http://127.0.0.1:9/pan/ABCDE1234F"), dict)

    settings.DJANGO_ENV = "test"
    monkeypatch.setattr(socket, "getaddrinfo", _dns("127.0.0.1"))
    pinned = _pin_target("http://127.0.0.1:9/pan/ABCDE1234F")
    assert not isinstance(pinned, dict)
    assert pinned[0] == "127.0.0.1"
    assert pinned[1] == "127.0.0.1"


def test_redirect_handler_does_not_follow():
    with pytest.raises(urllib.error.HTTPError):
        _NoRedirect().redirect_request(None, None, 302, "found", {}, "http://169.254.169.254/")


def test_public_https_connects_to_the_pinned_address(monkeypatch):
    seen = {}

    def connect(addr, timeout):
        seen["addr"] = addr
        raise TimeoutError("stop before tls")

    monkeypatch.setattr(socket, "getaddrinfo", _dns("93.184.216.34"))
    monkeypatch.setattr(socket, "create_connection", connect)
    with pytest.raises((TimeoutError, urllib.error.URLError, OSError)):
        open_pinned_url("https://example.com/pan/ABCDE1234F")
    assert seen["addr"] == ("93.184.216.34", 443)
