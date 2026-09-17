"""9.1 — outbound integration inventory is complete and settings keys exist."""

from __future__ import annotations

import pytest
from django.conf import settings

from core.integration_inventory import INTEGRATIONS


def test_integration_inventory_covers_money_paths_and_settings_keys():
    names = {row["name"] for row in INTEGRATIONS}
    assert "razorpay_subscriptions" in names
    assert "razorpay_collections" in names
    assert "gsp_einvoice" in names
    assert "smtp_email" in names
    money = [row["name"] for row in INTEGRATIONS if row["money_path"]]
    assert "razorpay_subscriptions" in money
    assert "razorpay_collections" in money
    assert "cashfree_collections" in money
    for row in INTEGRATIONS:
        assert row["fallback"]
        for key in row["settings_keys"]:
            assert hasattr(settings, key), f"{row['name']} missing settings.{key}"


@pytest.mark.django_db
def test_owner_inventory_api_hides_secret_values(tenant_a):
    resp = tenant_a.client.get("/api/v1/integrations/inventory/")
    assert resp.status_code == 200, resp.data
    names = {row["name"] for row in resp.data["integrations"]}
    assert "gsp_einvoice" in names
    assert "razorpay_collections" in names
    blob = str(resp.data)
    assert "sk_live" not in blob
    assert "whsec_" not in blob
    for row in resp.data["integrations"]:
        assert isinstance(row["settings_present"], dict)
        for value in row["settings_present"].values():
            assert value in (True, False)
    staff = tenant_a.staff_client.get("/api/v1/integrations/inventory/")
    assert staff.status_code == 403
