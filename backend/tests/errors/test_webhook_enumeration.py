"""QOS-0002 — every inbound webhook route rejects an unsigned request.

The individual forgery / replay contracts live in
``test_payment_webhook_adversarial.py`` (payment gateway) and
``test_webhook_and_async_contracts.py`` (SaaS billing). This is the *meta* test:
it walks the URLconf, asserts the set of inbound-webhook endpoints is exactly the
known two, and asserts each one refuses a POST that carries no signature — so a
future third webhook cannot be merged without a signature check (and without
someone updating ``KNOWN_WEBHOOKS`` here, which forces the forgery test too).
"""

from __future__ import annotations

import json

import pytest
from django.test import override_settings
from django.urls import URLResolver, get_resolver
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

# name -> a concrete path that resolves it (kwargs filled with a dummy value).
KNOWN_WEBHOOKS = {
    "v1:billing-razorpay-webhook": "/api/v1/billing/razorpay/webhook/",
    "v1:payment-webhook": "/api/v1/webhooks/payments/sandbox/",
    "v1:telegram-webhook": "/api/v1/telegram/webhook/",
}


def _walk(resolver, prefix="", ns=""):
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            child_ns = f"{ns}{p.namespace}:" if p.namespace else ns
            yield from _walk(p, prefix + str(p.pattern), child_ns)
        else:
            name = f"{ns}{p.name}" if p.name else None
            yield name, prefix + str(p.pattern)


def _webhook_routes():
    found = {}
    for name, pat in _walk(get_resolver()):
        blob = f"{name or ''} {pat}".lower()
        if "webhook" in blob or "/hook" in blob:
            found[name] = pat
    return found


def test_inbound_webhook_set_is_exactly_the_known_two():
    names = {n for n in _webhook_routes() if n}
    assert names == set(KNOWN_WEBHOOKS), (
        "Inbound webhook routes changed. Add the new one to KNOWN_WEBHOOKS here AND "
        "give it a signature-forgery + replay test (see test_payment_webhook_adversarial.py "
        f"/ test_webhook_and_async_contracts.py).\n  found: {sorted(names)}\n  known: {sorted(KNOWN_WEBHOOKS)}"
    )


@pytest.mark.parametrize("name,url", sorted(KNOWN_WEBHOOKS.items()))
@override_settings(DJANGO_ENV="production")
def test_webhook_fails_closed_on_unsigned_post_in_production(name, url):
    """With the production posture (and no signing secret configured), an unsigned
    webhook must be refused — never accepted, never a 5xx crash. The test-env
    convenience path that lets an unsigned POST through when DJANGO_ENV=test is
    deliberately not exercised here."""
    body = json.dumps({"event": "probe", "payload": {}}).encode()
    resp = APIClient().post(url, data=body, content_type="application/json")
    assert resp.status_code in (400, 401, 403), (
        f"{name} ({url}) accepted an unsigned webhook in production posture with "
        f"{resp.status_code}: {getattr(resp, 'data', resp.content)!r}"
    )
