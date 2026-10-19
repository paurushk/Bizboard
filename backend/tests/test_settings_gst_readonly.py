"""SET-16: e-invoice, e-way switch, turnover and portal keys are not owner-writable; the threshold is."""

URL = "/api/v1/company/"


def test_owner_cannot_switch_einvoice_eway_or_set_portal_keys(tenant_a):
    before = tenant_a.client.get(URL).data
    r = tenant_a.client.patch(
        URL,
        {
            "einvoice_enabled": True,
            "eway_enabled": True,
            "aato_turnover": "99999999",
            "gsp_provider": "cleartax",
            "gsp_credentials": {"client_id": "x", "client_secret": "y"},
        },
        format="json",
    )
    assert r.status_code == 200, r.data
    after = tenant_a.client.get(URL).data
    for key in ("einvoice_enabled", "eway_enabled", "aato_turnover", "gsp_provider", "gsp_credentials_configured"):
        assert after[key] == before[key], key


def test_owner_can_change_the_eway_threshold(tenant_a):
    r = tenant_a.client.patch(URL, {"eway_threshold_amount": "75000"}, format="json")
    assert r.status_code == 200, r.data
    assert str(tenant_a.client.get(URL).data["eway_threshold_amount"]).startswith("75000")
