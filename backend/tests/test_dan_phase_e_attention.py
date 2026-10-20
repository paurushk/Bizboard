"""DAN-16: who may use each attention endpoint, and that one company never sees or touches another's."""

import pytest
from django.core.cache import cache

from insights import attention as attention_module
from insights.attention import _row

ENDPOINTS_POST = (
    "/api/v1/insights/attention/dismiss/",
    "/api/v1/insights/attention/snooze/",
    "/api/v1/insights/attention/reopen/",
    "/api/v1/insights/attention/seen/",
    "/api/v1/insights/attention/assign/",
)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _feed(monkeypatch, rows):
    monkeypatch.setattr(
        attention_module, "_build_raw_rows", lambda company, as_of: (list(rows), {"failed": [], "truncated": []})
    )


def _row_for(code="DEAD_STOCK", entity_id=1):
    return _row(
        code=code, severity="warning", title="t", money_impact_paise=100, reason="r", action_label="Fix",
        action_href="/inventory/products", source_ticket="T", entity_type="product", entity_id=entity_id,
    )


def _set_staff_financial(tenant, allowed: bool):
    staff = tenant.company.memberships.get(user=tenant.staff)
    staff.can_view_financial_reports = allowed
    staff.save(update_fields=["can_view_financial_reports"])


@pytest.mark.django_db
def test_staff_without_financial_reports_is_refused_everywhere(tenant_a):
    _set_staff_financial(tenant_a, False)
    client = tenant_a.staff_client
    for status in ("open", "snoozed", "dismissed"):
        assert client.get(f"/api/v1/insights/attention/?status={status}").status_code == 403
    for url in ENDPOINTS_POST:
        resp = client.post(url, {"dedupe_key": "DEAD_STOCK:product:1", "reason": "x", "days": 1}, format="json")
        assert resp.status_code == 403, url


@pytest.mark.django_db
def test_staff_with_financial_reports_can_use_the_feed_and_set_rows_aside(tenant_a, monkeypatch):
    _set_staff_financial(tenant_a, True)
    _feed(monkeypatch, [_row_for()])
    client = tenant_a.staff_client
    assert client.get("/api/v1/insights/attention/").status_code == 200
    key = "DEAD_STOCK:product:1"
    assert client.post("/api/v1/insights/attention/snooze/", {"dedupe_key": key, "reason": "later", "days": 1}, format="json").status_code == 200
    assert client.post("/api/v1/insights/attention/reopen/", {"dedupe_key": key}, format="json").status_code == 200
    assert client.post("/api/v1/insights/attention/seen/", {}, format="json").status_code == 200


@pytest.mark.django_db
def test_anonymous_users_are_refused(tenant_a):
    from rest_framework.test import APIClient

    anon = APIClient()
    assert anon.get("/api/v1/insights/attention/").status_code in (401, 403)
    assert anon.post("/api/v1/insights/attention/dismiss/", {"dedupe_key": "X:1"}, format="json").status_code in (401, 403)


@pytest.mark.django_db
def test_one_company_cannot_see_or_reopen_anothers_set_aside_rows(tenant_a, tenant_b, monkeypatch):
    _feed(monkeypatch, [_row_for()])
    key = "DEAD_STOCK:product:1"
    assert tenant_a.client.post("/api/v1/insights/attention/dismiss/", {"dedupe_key": key}, format="json").status_code == 200

    other_list = tenant_b.client.get("/api/v1/insights/attention/?status=dismissed")
    assert other_list.status_code == 200
    assert (other_list.data.get("data") or other_list.data)["rows"] == []
    # Company B reopening the same key finds nothing set aside in its own company.
    assert tenant_b.client.post("/api/v1/insights/attention/reopen/", {"dedupe_key": key}, format="json").status_code == 400
    mine = tenant_a.client.get("/api/v1/insights/attention/?status=dismissed")
    assert [r["dedupe_key"] for r in (mine.data.get("data") or mine.data)["rows"]] == [key]


@pytest.mark.django_db
def test_seen_only_moves_the_callers_own_timestamp(tenant_a):
    owner = tenant_a.company.memberships.get(user=tenant_a.owner)
    staff = tenant_a.company.memberships.get(user=tenant_a.staff)
    _set_staff_financial(tenant_a, True)
    assert tenant_a.client.post("/api/v1/insights/attention/seen/", {}, format="json").status_code == 200
    owner.refresh_from_db()
    staff.refresh_from_db()
    assert owner.last_attention_seen_at is not None and staff.last_attention_seen_at is None


@pytest.mark.django_db
def test_paging_parameters_are_clamped(tenant_a, monkeypatch):
    _feed(monkeypatch, [_row_for(entity_id=i) for i in range(1, 4)])
    body = tenant_a.client.get("/api/v1/insights/attention/?limit=100000&offset=-5")
    assert body.status_code == 200
    data = body.data.get("data") or body.data
    assert len(data["rows"]) == 3 and data["next_offset"] is None
    assert tenant_a.client.get("/api/v1/insights/attention/?severity=nonsense&category=nonsense").status_code == 200


@pytest.mark.django_db
def test_unknown_status_value_behaves_as_open(tenant_a, monkeypatch):
    _feed(monkeypatch, [_row_for()])
    data = tenant_a.client.get("/api/v1/insights/attention/?status=whatever")
    assert data.status_code == 200
    assert (data.data.get("data") or data.data)["total_count"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["MANAGER", "SALES_STAFF", "INVENTORY_STAFF", "ACCOUNTANT", "AUDITOR", "VIEWER", "POLICY_DESK"])
def test_every_role_follows_the_financial_reports_flag_and_nothing_else(tenant_a, monkeypatch, role):
    """The API checks the flag, not the role name: an accountant without it is refused, a viewer with it is not."""
    _feed(monkeypatch, [_row_for()])
    staff = tenant_a.company.memberships.get(user=tenant_a.staff)
    staff.role = role
    staff.can_view_financial_reports = False
    staff.save(update_fields=["role", "can_view_financial_reports"])
    assert tenant_a.staff_client.get("/api/v1/insights/attention/").status_code == 403
    staff.can_view_financial_reports = True
    staff.save(update_fields=["can_view_financial_reports"])
    assert tenant_a.staff_client.get("/api/v1/insights/attention/").status_code == 200
