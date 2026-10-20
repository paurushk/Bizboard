"""DAN-11: rows carry the values behind their text, and the server decides the health band."""

from decimal import Decimal

import pytest
from django.core.cache import cache

from insights import attention as attention_module
from insights.attention import ATTENTION_ROW_KEYS, _row, build_attention_rows, dismiss_attention_row, list_set_aside_rows
from insights.services import health_band
from tests.conftest import make_customer


def _owner(tenant):
    return tenant.company.memberships.get(user=tenant.owner)


def _ar(code, customer_id, key, severity="warning"):
    return _row(
        code=code, severity=severity, title="t", money_impact_paise=100, reason="r", action_label="Open collections",
        action_href="/payments/collections", source_ticket="T", entity_type="customer", entity_id=customer_id,
        dedupe_key=key,
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _feed(monkeypatch, rows):
    monkeypatch.setattr(
        attention_module, "_build_raw_rows",
        lambda company, as_of: (list(rows), {"failed": [], "truncated": []}),
    )


@pytest.mark.django_db
def test_merged_row_params_carry_the_customer_count_and_each_signal(tenant_a, monkeypatch):
    one = make_customer(tenant_a.company, name="Single Co")
    many = make_customer(tenant_a.company, name="Many Co")
    _feed(monkeypatch, [
        _ar("AR_COLLECTION_RISK", one.id, "AR_COLLECTION_RISK:customer:1"),
        _ar("AR_COLLECTION_RISK", many.id, "AR_COLLECTION_RISK:customer:2"),
        _ar("PROMISE_TO_PAY_DUE", many.id, "PROMISE_TO_PAY_DUE:9"),
    ])
    rows = {r["dedupe_key"]: r for r in build_attention_rows(tenant_a.company, company_user=_owner(tenant_a))}
    single = rows[f"AR_CUSTOMER:{one.id}"]["params"]
    assert single["count"] == 1 and [sig["code"] for sig in single["signals"]] == ["AR_COLLECTION_RISK"]
    several = rows[f"AR_CUSTOMER:{many.id}"]["params"]
    assert several["customer"] == "Many Co" and several["count"] == 2
    assert {sig["code"] for sig in several["signals"]} == {"AR_COLLECTION_RISK", "PROMISE_TO_PAY_DUE"}
    for row in rows.values():
        assert list(row.keys())[: len(ATTENTION_ROW_KEYS)] == list(ATTENTION_ROW_KEYS)


@pytest.mark.django_db
def test_degraded_row_names_the_failed_checks_in_params(tenant_a, monkeypatch):
    def boom(company, as_of):
        raise RuntimeError("x")

    monkeypatch.setattr(attention_module, "_overdue_customer_rows", boom)
    row = next(r for r in build_attention_rows(tenant_a.company, company_user=_owner(tenant_a)) if r["code"] == "FEED_DEGRADED")
    assert row["params"] == {"checks": "overdue_customers"}


@pytest.mark.django_db
def test_params_survive_in_the_dismissed_list(tenant_a, monkeypatch):
    customer = make_customer(tenant_a.company, name="Keep Co")
    cu = _owner(tenant_a)
    _feed(monkeypatch, [
        _ar("AR_COLLECTION_RISK", customer.id, "AR_COLLECTION_RISK:customer:1"),
        _ar("PROMISE_TO_PAY_DUE", customer.id, "PROMISE_TO_PAY_DUE:3"),
    ])
    dismiss_attention_row(tenant_a.company, cu, dedupe_key=f"AR_CUSTOMER:{customer.id}")
    row = list_set_aside_rows(tenant_a.company, cu, status="dismissed")[0]
    assert row["params"]["customer"] == "Keep Co" and row["params"]["count"] == 2
    assert len(row["params"]["signals"]) == 2


def test_health_band_thresholds_live_on_the_server():
    assert health_band(Decimal("70")) == "healthy"
    assert health_band(Decimal("69.99")) == "watch"
    assert health_band(Decimal("45")) == "watch"
    assert health_band(Decimal("44.99")) == "action"


@pytest.mark.django_db
def test_health_endpoint_returns_the_band(tenant_a):
    body = tenant_a.client.get("/api/v1/insights/health/")
    assert body.status_code == 200
    data = body.data.get("data") or body.data
    assert data["band"] in {"healthy", "watch", "action"}
