"""SET-21: Settings change history: old and new values, no secrets, per area, owner only."""

from core.models import AuditEvent

HISTORY = "/api/v1/company/settings-history/"
COMPANY = "/api/v1/company/"


def _items(client, area):
    r = client.get(HISTORY, {"area": area})
    assert r.status_code == 200, r.data
    return r.data["items"]


def test_company_edit_records_old_and_new_for_the_company_area_only(tenant_a):
    old_city = tenant_a.company.city
    tenant_a.client.patch(COMPANY, {"city": "Pune", "negative_stock_policy": "WARN"}, format="json")
    company_rows = _items(tenant_a.client, "company")
    fields = {c["field"]: c for row in company_rows for c in row["changes"]}
    assert fields["city"]["from"] == old_city and fields["city"]["to"] == "Pune"
    assert "negative_stock_policy" not in fields
    gst_fields = {c["field"] for row in _items(tenant_a.client, "gst") for c in row["changes"]}
    assert "negative_stock_policy" in gst_fields and "city" not in gst_fields


def test_money_in_changes_are_recorded(tenant_a):
    tenant_a.client.patch("/api/v1/payments/money-in-rules/", {"cash_269st_mode": "block", "dunning_enabled": True}, format="json")
    fields = {c["field"]: c for row in _items(tenant_a.client, "money_in") for c in row["changes"]}
    assert fields["cash_269st_mode"]["to"] == "block" and fields["dunning_enabled"]["to"] is True


def test_series_changes_are_recorded_with_old_and_new(tenant_a):
    before = tenant_a.client.get("/api/v1/company/number-series/").data["items"][0]
    tenant_a.client.patch(
        "/api/v1/company/number-series/", {"items": [{"doc_type": before["doc_type"], "prefix": "NEWX"}]}, format="json"
    )
    rows = _items(tenant_a.client, "series")
    change = next(c for row in rows for c in row["changes"] if c["field"] == "prefix")
    assert change["from"] == before["prefix"] and change["to"] == "NEWX"
    assert rows[0]["what"] == before["doc_type"]


def test_gateway_history_never_holds_a_key_value(tenant_a):
    tenant_a.client.patch(
        "/api/v1/payments/gateway-settings/",
        {"provider": "razorpay", "credentials": {"key_id": "rzp_test_SECRETVALUE1", "key_secret": "topsecretvalue99"}},
        format="json",
    )
    rows = _items(tenant_a.client, "gateway")
    assert rows and any(c["field"] == "payment_keys" and c.get("changed") for r in rows for c in r["changes"])
    dump = str([r for r in rows]) + str(list(AuditEvent.objects.filter(company=tenant_a.company).values_list("metadata", flat=True)))
    assert "SECRETVALUE1" not in dump and "topsecretvalue99" not in dump


def test_unit_and_user_edits_show_up(tenant_a):
    from masters.models import Unit

    unit = Unit.objects.create(company=tenant_a.company, name="Box", short_name="BOX", uqc_code="BOX")
    tenant_a.client.patch(f"/api/v1/masters/units/{unit.id}/", {"name": "Boxes"}, format="json")
    assert any(c["field"] == "name" and c["to"] == "Boxes" for r in _items(tenant_a.client, "units") for c in r["changes"])


def test_owner_only_company_scoped_and_unknown_area_refused(tenant_a, tenant_b):
    assert tenant_a.staff_client.get(HISTORY, {"area": "company"}).status_code == 403
    assert tenant_a.client.get(HISTORY, {"area": "nope"}).status_code == 400
    tenant_b.client.patch(COMPANY, {"city": "Elsewhere"}, format="json")
    assert not any(c["to"] == "Elsewhere" for r in _items(tenant_a.client, "company") for c in r["changes"])
