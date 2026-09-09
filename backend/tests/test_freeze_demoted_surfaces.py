"""SR-02 / SR-03 — the KNOWN-LIMITATION surfaces from the 2026-09-09b scope
revision are inert under the pilot flag profile.

D6 fixed assets and D10 Bill of Entry get a route guard (ENABLE_FIXED_ASSETS /
ENABLE_BOE, OFF in backend/.env.pilot.example). D7 GSTR-7/8 and D9 CMP-08 /
GSTR-4 were already inert via ENABLE_GSTR=0 — this locks that in. D8 (reverse
charge) and D11 (plan quotas) are screening-controlled, not code-gated; the
tests below assert that so the FREEZE_SCOPE note stays accurate.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db


# --- D6 fixed assets, D10 Bill of Entry: route-guarded ----------------------

@override_settings(ENABLE_FIXED_ASSETS=False)
def test_fixed_assets_route_404_under_pilot_profile(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    for method, url in [
        ("get", "/api/v1/accounting/fixed-assets/"),
        ("post", "/api/v1/accounting/fixed-assets/"),
    ]:
        resp = getattr(tenant_a.client, method)(url, {}, format="json")
        assert resp.status_code == 404, (method, url, resp.status_code)


@override_settings(ENABLE_BOE=False)
def test_bill_of_entry_route_404_under_pilot_profile(tenant_a):
    for method, url in [
        ("get", "/api/v1/purchases/bills-of-entry/"),
        ("post", "/api/v1/purchases/bills-of-entry/"),
    ]:
        resp = getattr(tenant_a.client, method)(url, {}, format="json")
        assert resp.status_code == 404, (method, url, resp.status_code)


def test_fixed_assets_route_reachable_when_flag_on(tenant_a):
    """The guard actually gates — with the flag on (suite default) the route is live."""
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    resp = tenant_a.client.get("/api/v1/accounting/fixed-assets/")
    assert resp.status_code != 404, resp.status_code


def test_bill_of_entry_route_reachable_when_flag_on(tenant_a):
    resp = tenant_a.client.get("/api/v1/purchases/bills-of-entry/")
    assert resp.status_code != 404, resp.status_code


# --- D7 / D9 GST returns: already inert via ENABLE_GSTR=0 ------------------

@override_settings(ENABLE_GSTR=False)
@pytest.mark.parametrize("path", [
    "/api/v1/reports/gstr7/?period=2026-08",   # D7 — TDS return
    "/api/v1/reports/gstr8/?period=2026-08",   # D7 — TCS return
    "/api/v1/reports/cmp08/?period=2026-08",   # D9 — composition
    "/api/v1/reports/gstr4/?fy=2026-27",       # D9 — composition annual
])
def test_demoted_gst_return_routes_404_under_pilot_profile(path, tenant_a):
    resp = tenant_a.client.get(path)
    assert resp.status_code == 404, (path, resp.status_code)


# --- D8 reverse charge, D11 quotas: screening-controlled, NOT code-gated ---

def test_reverse_charge_is_not_code_gated_only_screening(tenant_a):
    """D8: `is_reverse_charge` stays an accepted invoice field. Merchants with
    material RCM exposure are screened out at onboarding, not blocked in code."""
    product = make_product(tenant_a.company, gst_rate="18")
    customer = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    resp = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id, "invoice_type": "GST", "is_reverse_charge": True,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data.get("is_reverse_charge") is True
