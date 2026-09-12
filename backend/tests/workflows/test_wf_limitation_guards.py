"""Scope revision 2026-09-09b — KNOWN-LIMITATION route guards.

Of D6-D14, only D9b/D12/D13/D14 stay in the freeze; D6, D7, D8, D9, D10, D11
were demoted to KNOWN LIMITATIONS (docs/FREEZE_SCOPE.md section C). Two of them
are gated by a feature flag and the pilot profile turns them OFF:

  D6  fixed assets    ENABLE_FIXED_ASSETS=0  -> /api/v1/accounting/fixed-assets/ 404s
  D10 bill of entry   ENABLE_BOE=0           -> /api/v1/purchases/bills-of-entry/ 404s

These guards prove the "route 404s in the pilot profile" claim. The remaining
demoted flows (D7 TDS/TCS returns, D8 RCM, D9 composition/CMP-08, D11 plan
limits) have no separate flag — per section C they are screened out / handled
out of band and are NOT freeze-gated; their behaviour coverage lives in
test_wf_extended_stubs.py, relabelled as LIMITATION coverage (not a blocker).
"""

from __future__ import annotations

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db

FIXED_ASSETS = "/api/v1/accounting/fixed-assets/"
BILLS_OF_ENTRY = "/api/v1/purchases/bills-of-entry/"


def _books(company):
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    from accounting.services import seed_chart_of_accounts

    seed_chart_of_accounts(company)


@override_settings(ENABLE_FIXED_ASSETS=False)
def test_d6_fixed_assets_route_404s_when_disabled(tenant_a):
    _books(tenant_a.company)
    assert tenant_a.client.get(FIXED_ASSETS).status_code == 404
    assert tenant_a.client.post(
        FIXED_ASSETS,
        {"name": "X", "acquisition_date": "2026-04-01", "acquisition_cost": "1000.00",
         "useful_life_months": 12, "method": "SLM"},
        format="json",
    ).status_code == 404


@override_settings(ENABLE_BOE=False)
def test_d10_bill_of_entry_route_404s_when_disabled(tenant_a):
    _books(tenant_a.company)
    from tests.conftest import make_supplier

    sup = make_supplier(tenant_a.company)
    assert tenant_a.client.get(BILLS_OF_ENTRY).status_code == 404
    assert tenant_a.client.post(
        BILLS_OF_ENTRY,
        {"supplier": sup.id, "boe_number": "B1", "boe_date": "2026-06-01",
         "assessable_value": "1000.00", "bcd_amount": "100.00", "igst_amount": "198.00"},
        format="json",
    ).status_code == 404


@override_settings(ENABLE_FIXED_ASSETS=True)
def test_d6_fixed_assets_route_reachable_when_enabled(tenant_a):
    """When a company opts in (LIM = works with a caveat), the surface is live —
    the full acquire→depreciate→dispose correctness is WF-53."""
    _books(tenant_a.company)
    assert tenant_a.client.get(FIXED_ASSETS).status_code == 200
