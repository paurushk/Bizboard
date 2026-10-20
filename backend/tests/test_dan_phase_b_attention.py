"""DAN-08/09/10: merged customer row, escalation, set-aside lists, reopen, paging, health access."""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from core.exceptions import BusinessRuleError
from insights import attention as attention_module
from insights.attention import (
    _row,
    build_attention_feed,
    build_attention_rows,
    dismiss_attention_row,
    list_set_aside_rows,
    mark_attention_seen,
    reopen_attention_row,
    snooze_attention_row,
    sweep_attention_state,
)
from insights.models import AttentionOutcome, AttentionRowState
from tests.conftest import make_customer


def _owner(tenant):
    return tenant.company.memberships.get(user=tenant.owner)


def _status(failed=(), truncated=()):
    return {"failed": list(failed), "truncated": list(truncated)}


def _ar_row(code, customer_id, key, severity="warning", paise=1000, reason="r"):
    return _row(
        code=code, severity=severity, title=f"{code} t", money_impact_paise=paise, reason=reason,
        action_label="Open collections", action_href="/payments/collections", source_ticket="T",
        entity_type="customer", entity_id=customer_id, dedupe_key=key,
    )


def _plain_row(code, entity_id, severity="warning"):
    return _row(
        code=code, severity=severity, title=f"{code} {entity_id}", money_impact_paise=500, reason="r",
        action_label="Fix", action_href="/inventory/products", source_ticket="T",
        entity_type="product", entity_id=entity_id,
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _feed(monkeypatch, rows, status=None):
    monkeypatch.setattr(
        attention_module, "_build_raw_rows", lambda company, as_of: (list(rows), status or _status())
    )


# --- DAN-08 ---------------------------------------------------------------

@pytest.mark.django_db
def test_receivable_signals_for_one_customer_become_one_row(tenant_a, monkeypatch):
    customer = make_customer(tenant_a.company)
    _feed(monkeypatch, [
        _ar_row("AR_COLLECTION_RISK", customer.id, f"AR_COLLECTION_RISK:customer:{customer.id}", "critical", 9000),
        _ar_row("PROMISE_TO_PAY_DUE", customer.id, "PROMISE_TO_PAY_DUE:11", "warning", 4000),
        _ar_row("CREDIT_LIMIT_NEAR", customer.id, f"CREDIT_LIMIT_NEAR:customer:{customer.id}", "warning", 2000),
        _plain_row("DEAD_STOCK", 3),
    ])
    rows = build_attention_rows(tenant_a.company, company_user=_owner(tenant_a))
    merged = [r for r in rows if r["code"] == "AR_CUSTOMER"]
    assert len(merged) == 1
    assert merged[0]["dedupe_key"] == f"AR_CUSTOMER:{customer.id}"
    assert merged[0]["severity"] == "critical"
    assert merged[0]["money_impact_paise"] == 9000, "the largest amount, not a sum that double counts"
    assert merged[0]["amount_basis"] == "overdue"
    assert not [r for r in rows if r["code"] in ("AR_COLLECTION_RISK", "PROMISE_TO_PAY_DUE", "CREDIT_LIMIT_NEAR")]
    assert any(r["code"] == "DEAD_STOCK" for r in rows)


@pytest.mark.django_db
def test_a_dismissal_does_not_hide_a_new_signal_for_the_same_customer(tenant_a, monkeypatch):
    customer = make_customer(tenant_a.company)
    cu = _owner(tenant_a)
    first = _ar_row("AR_COLLECTION_RISK", customer.id, f"AR_COLLECTION_RISK:customer:{customer.id}", "warning")
    _feed(monkeypatch, [first])
    key = f"AR_CUSTOMER:{customer.id}"
    dismiss_attention_row(tenant_a.company, cu, dedupe_key=key)
    assert key not in {r["dedupe_key"] for r in build_attention_rows(tenant_a.company, company_user=cu)}

    cache.clear()
    promise = _ar_row("PROMISE_TO_PAY_DUE", customer.id, "PROMISE_TO_PAY_DUE:5", "warning")
    _feed(monkeypatch, [first, promise])
    assert key in {r["dedupe_key"] for r in build_attention_rows(tenant_a.company, company_user=cu)}

    sweep_attention_state(tenant_a.company)
    assert AttentionRowState.objects.get(company=tenant_a.company, dedupe_key=key).dismissed is False


@pytest.mark.django_db
def test_a_dismissal_stays_while_nothing_new_happens_and_severity_rise_brings_it_back(tenant_a, monkeypatch):
    customer = make_customer(tenant_a.company)
    cu = _owner(tenant_a)
    key = f"AR_CUSTOMER:{customer.id}"
    warn = _ar_row("AR_COLLECTION_RISK", customer.id, "AR_COLLECTION_RISK:customer:1", "warning")
    _feed(monkeypatch, [warn])
    dismiss_attention_row(tenant_a.company, cu, dedupe_key=key)
    cache.clear()
    _feed(monkeypatch, [warn])
    assert key not in {r["dedupe_key"] for r in build_attention_rows(tenant_a.company, company_user=cu)}
    cache.clear()
    _feed(monkeypatch, [_ar_row("AR_COLLECTION_RISK", customer.id, "AR_COLLECTION_RISK:customer:1", "critical")])
    assert key in {r["dedupe_key"] for r in build_attention_rows(tenant_a.company, company_user=cu)}


@pytest.mark.django_db
def test_copy_migration_merges_several_old_rows_without_a_unique_violation(tenant_a):
    from importlib import import_module

    from django.apps import apps as global_apps

    customer = make_customer(tenant_a.company)
    now = timezone.now()
    for key, dismissed in ((f"AR_COLLECTION_RISK:customer:{customer.id}", True), (f"CREDIT_LIMIT_NEAR:customer:{customer.id}", False)):
        AttentionRowState.objects.create(
            company=tenant_a.company, dedupe_key=key, first_seen=now - timedelta(days=3), dismissed=dismissed
        )
    migration = import_module("insights.migrations.0015_copy_customer_receivable_state")
    migration.forwards(global_apps, None)
    migration.forwards(global_apps, None)  # idempotent
    merged = AttentionRowState.objects.get(company=tenant_a.company, dedupe_key=f"AR_CUSTOMER:{customer.id}")
    assert merged.dismissed is False, "only dismissed when every old row was"
    assert AttentionRowState.objects.filter(company=tenant_a.company, dedupe_key__startswith="AR_COLLECTION_RISK").exists()


# --- DAN-09 ---------------------------------------------------------------

@pytest.mark.django_db
def test_snoozed_and_dismissed_lists_keep_rows_after_the_condition_is_gone(tenant_a, monkeypatch):
    cu = _owner(tenant_a)
    _feed(monkeypatch, [_plain_row("DEAD_STOCK", 1), _plain_row("LOW_STOCK_FAST_MOVER", 2)])
    snooze_attention_row(tenant_a.company, cu, dedupe_key="DEAD_STOCK:product:1", days=7, reason="Supplier call")
    dismiss_attention_row(tenant_a.company, cu, dedupe_key="LOW_STOCK_FAST_MOVER:product:2", reason="Not selling")

    cache.clear()
    _feed(monkeypatch, [])  # both conditions have gone
    snoozed = list_set_aside_rows(tenant_a.company, cu, status="snoozed")
    dismissed = list_set_aside_rows(tenant_a.company, cu, status="dismissed")
    assert [r["dedupe_key"] for r in snoozed] == ["DEAD_STOCK:product:1"]
    assert snoozed[0]["title"] == "DEAD_STOCK 1" and snoozed[0]["state"] == "snoozed"
    assert snoozed[0]["state_reason"] == "Supplier call" and snoozed[0]["condition_cleared"] is True
    assert snoozed[0]["state_by"]["user_id"] == tenant_a.owner.pk
    assert [r["dedupe_key"] for r in dismissed] == ["LOW_STOCK_FAST_MOVER:product:2"]
    assert dismissed[0]["state_reason"] == "Not selling"


@pytest.mark.django_db
def test_reopen_returns_the_row_and_lets_a_later_fix_count_as_resolved(tenant_a, monkeypatch):
    cu = _owner(tenant_a)
    row = _plain_row("DEAD_STOCK", 9)
    _feed(monkeypatch, [row])
    key = "DEAD_STOCK:product:9"
    dismiss_attention_row(tenant_a.company, cu, dedupe_key=key)
    assert AttentionOutcome.objects.filter(company=tenant_a.company, dedupe_key=key, outcome="dismissed").exists()
    reopen_attention_row(tenant_a.company, cu, dedupe_key=key)
    assert not AttentionOutcome.objects.filter(company=tenant_a.company, dedupe_key=key).exists()
    assert key in {r["dedupe_key"] for r in build_attention_rows(tenant_a.company, company_user=cu)}

    AttentionRowState.objects.filter(company=tenant_a.company, dedupe_key=key).update(assigned_to=cu)
    cache.clear()
    _feed(monkeypatch, [])
    sweep_attention_state(tenant_a.company)
    assert AttentionOutcome.objects.get(company=tenant_a.company, dedupe_key=key).outcome == "resolved"


@pytest.mark.django_db
def test_reopening_something_not_set_aside_is_rejected(tenant_a):
    with pytest.raises(BusinessRuleError):
        reopen_attention_row(tenant_a.company, _owner(tenant_a), dedupe_key="DEAD_STOCK:1")


@pytest.mark.django_db
def test_feed_filters_counts_and_paging(tenant_a, monkeypatch):
    cu = _owner(tenant_a)
    rows = [_plain_row("DEAD_STOCK", i, "warning") for i in range(1, 8)]
    rows.append(_plain_row("GST_RATE_EXPOSURE", 50, "critical"))
    rows.append(_plain_row("CASH_TIGHT_14D", 60, "info"))
    _feed(monkeypatch, rows)

    first = build_attention_feed(tenant_a.company, cu, limit=4)
    assert first["total_count"] == 9 and first["count"] == 9 and len(first["rows"]) == 4
    assert first["next_offset"] == 4
    assert first["critical_count"] == 1
    assert first["counts_by_category"] == {"stock": 7, "gst": 1, "money": 1}
    second = build_attention_feed(tenant_a.company, cu, limit=4, offset=4)
    assert len(second["rows"]) == 4 and second["next_offset"] == 8
    assert {r["dedupe_key"] for r in first["rows"]}.isdisjoint({r["dedupe_key"] for r in second["rows"]})

    gst = build_attention_feed(tenant_a.company, cu, category="gst")
    assert [r["code"] for r in gst["rows"]] == ["GST_RATE_EXPOSURE"]
    assert gst["total_count"] == 9, "counts ignore the filters"
    assert build_attention_feed(tenant_a.company, cu, severity="critical")["count"] == 1


@pytest.mark.django_db
def test_rows_report_age_and_new_since_last_visit(tenant_a, monkeypatch):
    cu = _owner(tenant_a)
    _feed(monkeypatch, [_plain_row("DEAD_STOCK", 1)])
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="DEAD_STOCK:product:1", first_seen=timezone.now() - timedelta(days=9)
    )
    row = build_attention_rows(tenant_a.company, company_user=cu)[0]
    assert row["age_days"] == 9 and row["is_new"] is False

    cu.last_attention_seen_at = timezone.now() - timedelta(days=12)
    cu.save(update_fields=["last_attention_seen_at"])
    assert build_attention_rows(tenant_a.company, company_user=cu)[0]["is_new"] is True, "appeared after the last visit"
    cu.last_attention_seen_at = timezone.now() - timedelta(days=2)
    cu.save(update_fields=["last_attention_seen_at"])
    assert build_attention_rows(tenant_a.company, company_user=cu)[0]["is_new"] is False
    AttentionRowState.objects.filter(company=tenant_a.company).update(first_seen=timezone.now() - timedelta(hours=3))
    assert build_attention_rows(tenant_a.company, company_user=cu)[0]["is_new"] is True


@pytest.mark.django_db
def test_mark_seen_stores_the_visit_time_per_person(tenant_a):
    cu = _owner(tenant_a)
    assert cu.last_attention_seen_at is None
    mark_attention_seen(cu)
    cu.refresh_from_db()
    assert cu.last_attention_seen_at is not None


@pytest.mark.django_db
def test_api_endpoints_for_status_reopen_seen_and_bad_paging(tenant_a, monkeypatch):
    _feed(monkeypatch, [_plain_row("DEAD_STOCK", 4)])
    client = tenant_a.client
    ok = client.get("/api/v1/insights/attention/?limit=1")
    assert ok.status_code == 200
    body = ok.data.get("data") or ok.data
    assert body["total_count"] == 1 and "counts_by_severity" in body
    assert client.get("/api/v1/insights/attention/?limit=abc").status_code == 400

    done = client.post("/api/v1/insights/attention/dismiss/", {"dedupe_key": "DEAD_STOCK:product:4"}, format="json")
    assert done.status_code == 200, done.data
    dismissed = client.get("/api/v1/insights/attention/?status=dismissed")
    assert dismissed.status_code == 200
    drows = (dismissed.data.get("data") or dismissed.data)["rows"]
    assert [r["dedupe_key"] for r in drows] == ["DEAD_STOCK:product:4"]

    assert client.post("/api/v1/insights/attention/reopen/", {"dedupe_key": "DEAD_STOCK:product:4"}, format="json").status_code == 200
    assert client.post("/api/v1/insights/attention/reopen/", {"dedupe_key": "DEAD_STOCK:product:4"}, format="json").status_code == 400
    assert client.post("/api/v1/insights/attention/seen/", {}, format="json").status_code == 200
    assert tenant_a.staff_client.post("/api/v1/insights/attention/seen/", {}, format="json").status_code == 403


# --- DAN-10 ---------------------------------------------------------------

@pytest.mark.django_db
def test_health_score_does_not_need_ai_features(tenant_a):
    tenant_a.company.ai_features_enabled = False
    tenant_a.company.save(update_fields=["ai_features_enabled"])
    assert tenant_a.client.get("/api/v1/insights/health/").status_code == 200
    assert tenant_a.client.get("/api/v1/insights/health/history/").status_code == 200
