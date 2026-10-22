"""WP-AB4: public share links can't be cached, indexed or quietly spread; tokens are long."""

import inspect
import re

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

FAKE = "x" * 43
PUBLIC_PATHS = [
    f"/api/v1/public/invoices/{FAKE}/",
    f"/api/v1/public/invoices/{FAKE}/pdf/",
    f"/api/v1/public/quotations/{FAKE}/",
    f"/api/v1/public/quotations/{FAKE}/pdf/",
    f"/api/v1/public/receipt-voucher/{FAKE}/",
    f"/api/v1/public/customer-portal/{FAKE}/",
]


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_every_public_link_response_is_no_store_and_noindex_even_on_404(path):
    resp = APIClient().get(path)
    assert resp.status_code in (404, 410, 400), (path, resp.status_code)
    assert "no-store" in resp["Cache-Control"]
    assert "noindex" in resp["X-Robots-Tag"]


def test_tokens_are_minted_with_at_least_128_bits():
    """Every mint site uses secrets.token_urlsafe with >= 16 bytes (128 bits)."""
    from accounts import tenant_backup
    from payments import portal_views, services
    from sales import public_links, quotation_links

    for mod in (public_links, quotation_links, portal_views, services, tenant_backup):
        src = inspect.getsource(mod)
        for nbytes in re.findall(r"secrets\.token_urlsafe\((\d+)\)", src):
            assert int(nbytes) >= 16, f"{mod.__name__}: token_urlsafe({nbytes}) is under 128 bits"


@override_settings(PUBLIC_LINK_SPREAD_LIMIT=3)
def test_a_link_opened_from_many_networks_is_flagged_once(tenant_a):
    from unittest import mock

    from core.middleware import PublicLinkMiddleware

    calls = []
    with mock.patch("core.ops_metrics.bump_event", side_effect=calls.append):
        request = mock.Mock()
        for i in range(6):
            request.META = {"REMOTE_ADDR": f"10.0.{i}.7"}
            PublicLinkMiddleware._note_spread("tok" * 10, request)
        # Same network again does not count twice.
        request.META = {"REMOTE_ADDR": "10.0.0.99"}
        PublicLinkMiddleware._note_spread("tok" * 10, request)
    assert calls == ["public_link_spread"]


def test_non_public_paths_are_untouched(tenant_a):
    resp = tenant_a.client.get("/api/v1/customers/")
    assert resp.get("X-Robots-Tag") is None
