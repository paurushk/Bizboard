"""Inventory review 2026-10-15 — INV-WP-00 verification and INV-WP-04 permissions.

* WP-04: Purchase planning and Demand forecast GET were HasCompany-only, so a VIEWER could
  read suggested quantities / last suppliers by calling the API directly (review #26).
* WP-00's GL finding (review #3) is now covered by ``test_inventory_gl_wp12.py``.
"""

from __future__ import annotations

import pytest

from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db

PLANNING = "/api/v1/inventory/purchase-planning/"
FORECAST = "/api/v1/inventory/demand-forecast/"


# ---------------------------------------------------------------- WP-04

@pytest.mark.parametrize("url", [PLANNING, FORECAST])
def test_viewer_cannot_read_planning_or_forecast(url):
    ns = seed_archetype("trader")
    resp = ns.viewer_client.get(url)
    assert resp.status_code == 403, resp.data


@pytest.mark.parametrize("url", [PLANNING, FORECAST])
@pytest.mark.parametrize("client_attr", ["owner_client", "acct_client", "sales_client"])
def test_inventory_viewing_roles_are_not_blocked(url, client_attr):
    ns = seed_archetype("trader")
    resp = getattr(ns, client_attr).get(url)
    # Planning answers 404 while ENABLE_PURCHASE_PLANNING is off; the point is it is not 403.
    assert resp.status_code != 403, resp.data


def test_planning_post_still_needs_purchase_permission():
    ns = seed_archetype("trader")
    assert ns.viewer_client.post(PLANNING, {"rows": []}, format="json").status_code == 403
