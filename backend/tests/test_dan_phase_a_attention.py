"""DAN-04/05/06: server-side action rules, visible detector failure, read-only feed."""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.exceptions import BusinessRuleError
from insights import attention as attention_module
from insights.attention import (
    ATTENTION_ROW_KEYS,
    _row,
    build_attention_rows,
    dismiss_attention_row,
    snooze_attention_row,
    sweep_attention_state,
)
from insights.models import AttentionRowState


def _owner(tenant):
    return tenant.company.memberships.get(user=tenant.owner)


def _fake_row(code="DEAD_STOCK", entity_id=7, severity="warning"):
    return _row(
        code=code,
        severity=severity,
        title="Fake",
        money_impact_paise=1000,
        reason="because",
        action_label="Fix",
        action_href="/inventory/products",
        source_ticket="TEST",
        entity_type="product",
        entity_id=entity_id,
    )


def _status(failed=(), truncated=()):
    return {"failed": list(failed), "truncated": list(truncated)}


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _only_rows(monkeypatch, rows, status=None):
    monkeypatch.setattr(
        attention_module, "_build_raw_rows", lambda company, as_of: (list(rows), status or _status())
    )


# --- DAN-04 ---------------------------------------------------------------

@pytest.mark.django_db
def test_gst_rows_cannot_be_dismissed_but_can_be_snoozed(tenant_a):
    cu = _owner(tenant_a)
    with pytest.raises(BusinessRuleError) as exc:
        dismiss_attention_row(tenant_a.company, cu, dedupe_key="GST_RATE_EXPOSURE:1")
    assert getattr(exc.value, "detail", None)
    assert not AttentionRowState.objects.filter(company=tenant_a.company, dedupe_key="GST_RATE_EXPOSURE:1").exists()
    out = snooze_attention_row(tenant_a.company, cu, dedupe_key="GST_RATE_EXPOSURE:1", days=3, reason="ask CA")
    assert out["snooze_until"]


@pytest.mark.django_db
def test_direct_api_dismiss_of_a_gst_row_is_rejected(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/insights/attention/dismiss/", {"dedupe_key": "IRN_FAILED:sales_invoice:5"}, format="json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_critical_row_needs_a_reason_to_dismiss(tenant_a, monkeypatch):
    cu = _owner(tenant_a)
    monkeypatch.setattr(attention_module, "_live_row", lambda company, key: {"severity": "critical", "code": "CASH_TIGHT_14D"})
    with pytest.raises(BusinessRuleError):
        dismiss_attention_row(tenant_a.company, cu, dedupe_key="CASH_TIGHT_14D:1")
    with pytest.raises(BusinessRuleError):
        dismiss_attention_row(tenant_a.company, cu, dedupe_key="CASH_TIGHT_14D:1", reason="ab")
    ok = dismiss_attention_row(tenant_a.company, cu, dedupe_key="CASH_TIGHT_14D:1", reason="Paid by cheque today")
    assert ok["dismissed"] is True


@pytest.mark.django_db
def test_warning_row_can_be_dismissed_without_a_reason(tenant_a, monkeypatch):
    monkeypatch.setattr(attention_module, "_live_row", lambda company, key: {"severity": "warning", "code": "DEAD_STOCK"})
    assert dismiss_attention_row(tenant_a.company, _owner(tenant_a), dedupe_key="DEAD_STOCK:2")["dismissed"] is True


@pytest.mark.django_db
def test_duplicate_payment_still_needs_a_reason(tenant_a):
    with pytest.raises(BusinessRuleError):
        dismiss_attention_row(tenant_a.company, _owner(tenant_a), dedupe_key="DUPLICATE_PAYMENT:4:x")


@pytest.mark.django_db
def test_rows_carry_server_decided_action_flags(tenant_a, monkeypatch):
    _only_rows(monkeypatch, [
        _fake_row("DEAD_STOCK", 1, "warning"),
        _fake_row("GST_RATE_EXPOSURE", 2, "warning"),
        _fake_row("CASH_TIGHT_14D", 3, "critical"),
    ])
    rows = {r["code"]: r for r in build_attention_rows(tenant_a.company, company_user=_owner(tenant_a))}
    for row in rows.values():
        assert list(row.keys())[: len(ATTENTION_ROW_KEYS)] == list(ATTENTION_ROW_KEYS)
    assert rows["DEAD_STOCK"]["dismissible"] is True and rows["DEAD_STOCK"]["requires_reason"] is False
    assert rows["GST_RATE_EXPOSURE"]["dismissible"] is False
    assert rows["GST_RATE_EXPOSURE"]["snoozable"] is True and rows["GST_RATE_EXPOSURE"]["assignable"] is True
    assert rows["CASH_TIGHT_14D"]["requires_reason"] is True


@pytest.mark.django_db
def test_assignee_who_cannot_handle_the_item_is_rejected(tenant_a):
    from insights.attention import assign_attention_row

    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_ACTION_ASSIGNMENT"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    staff = tenant_a.company.memberships.get(user=tenant_a.staff)
    staff.can_view_financial_reports = False
    staff.save(update_fields=["can_view_financial_reports"])
    with pytest.raises(BusinessRuleError):
        assign_attention_row(
            tenant_a.company, _owner(tenant_a), dedupe_key="GST_RATE_EXPOSURE:1", assignee_id=staff.id
        )
    assert not AttentionRowState.objects.filter(
        company=tenant_a.company, dedupe_key="GST_RATE_EXPOSURE:1", assigned_to=staff
    ).exists()


# --- DAN-05 ---------------------------------------------------------------

@pytest.mark.django_db
def test_a_failing_detector_shows_a_degraded_row_instead_of_all_clear(tenant_a, monkeypatch):
    def boom(company, as_of):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(attention_module, "_overdue_customer_rows", boom)
    rows = build_attention_rows(tenant_a.company, company_user=_owner(tenant_a))
    degraded = [r for r in rows if r["code"] == "FEED_DEGRADED"]
    assert len(degraded) == 1
    assert "overdue_customers" in degraded[0]["reason"]
    assert degraded[0]["dismissible"] is False and degraded[0]["snoozable"] is False


@pytest.mark.django_db
def test_degraded_status_survives_a_cache_hit(tenant_a, monkeypatch):
    calls = {"n": 0}

    def boom(company, as_of):
        calls["n"] += 1
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(attention_module, "_overdue_customer_rows", boom)
    cu = _owner(tenant_a)
    build_attention_rows(tenant_a.company, company_user=cu)
    again = build_attention_rows(tenant_a.company, company_user=cu)
    assert calls["n"] == 1, "second call should be served from the (short) cache"
    assert any(r["code"] == "FEED_DEGRADED" for r in again)


@pytest.mark.django_db
def test_a_dismissal_survives_a_failing_detector_and_lapses_when_the_check_ran(tenant_a, monkeypatch):
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="DEAD_STOCK:99", first_seen=timezone.now(), dismissed=True
    )
    _only_rows(monkeypatch, [], _status(failed=["leakage"]))
    sweep_attention_state(tenant_a.company)
    assert AttentionRowState.objects.get(company=tenant_a.company, dedupe_key="DEAD_STOCK:99").dismissed is True

    from django.core.cache import cache

    cache.clear()
    _only_rows(monkeypatch, [], _status())
    sweep_attention_state(tenant_a.company)
    assert AttentionRowState.objects.get(company=tenant_a.company, dedupe_key="DEAD_STOCK:99").dismissed is False


@pytest.mark.django_db
def test_a_capped_detector_keeps_dismissals_for_its_own_codes_only(tenant_a, monkeypatch):
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="AR_COLLECTION_RISK:customer:5", first_seen=timezone.now(), dismissed=True
    )
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="DEAD_STOCK:5", first_seen=timezone.now(), dismissed=True
    )
    _only_rows(monkeypatch, [], _status(truncated=["AR_COLLECTION_RISK"]))
    sweep_attention_state(tenant_a.company)
    states = {s.dedupe_key: s.dismissed for s in AttentionRowState.objects.filter(company=tenant_a.company)}
    assert states["AR_COLLECTION_RISK:customer:5"] is True
    assert states["DEAD_STOCK:5"] is False


@pytest.mark.django_db
def test_a_failed_check_does_not_record_resolved_outcomes(tenant_a, monkeypatch):
    from insights.models import AttentionOutcome

    cu = _owner(tenant_a)
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="DEAD_STOCK:42", first_seen=timezone.now(), assigned_to=cu
    )
    _only_rows(monkeypatch, [], _status(failed=["leakage"]))
    sweep_attention_state(tenant_a.company)
    assert not AttentionOutcome.objects.filter(company=tenant_a.company, dedupe_key="DEAD_STOCK:42").exists()


# --- DAN-06 ---------------------------------------------------------------

def _write_statements(ctx):
    return [
        q["sql"] for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]


@pytest.mark.django_db
def test_reading_the_feed_issues_no_writes(tenant_a, monkeypatch):
    cu = _owner(tenant_a)
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="OLD:1", first_seen=timezone.now(), dismissed=True
    )
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="DEAD_STOCK:7", first_seen=timezone.now(),
        snooze_until=timezone.now() - timedelta(hours=1), snooze_reason="later",
    )
    _only_rows(monkeypatch, [_fake_row()])
    with CaptureQueriesContext(connection) as ctx:
        rows = build_attention_rows(tenant_a.company, company_user=cu)
    assert [r["code"] for r in rows] == ["DEAD_STOCK"], "an expired snooze shows the row again"
    assert _write_statements(ctx) == []
    assert AttentionRowState.objects.get(company=tenant_a.company, dedupe_key="OLD:1").dismissed is True


@pytest.mark.django_db
def test_first_seen_does_not_advance_between_reads_and_the_sweep_stores_it(tenant_a, monkeypatch):
    cu = _owner(tenant_a)
    _only_rows(monkeypatch, [_fake_row()])
    first = build_attention_rows(tenant_a.company, company_user=cu)[0]["first_seen"]
    second = build_attention_rows(tenant_a.company, company_user=cu)[0]["first_seen"]
    assert first == second
    assert not AttentionRowState.objects.filter(company=tenant_a.company).exists()
    result = sweep_attention_state(tenant_a.company)
    assert result["created"] == 1
    assert AttentionRowState.objects.filter(company=tenant_a.company, dedupe_key="DEAD_STOCK:product:7").exists()


@pytest.mark.django_db
def test_sweep_clears_expired_snoozes_and_records_resolved_assignments(tenant_a, monkeypatch):
    from insights.models import AttentionOutcome

    cu = _owner(tenant_a)
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="DEAD_STOCK:1", first_seen=timezone.now(),
        snooze_until=timezone.now() - timedelta(minutes=5), snooze_reason="later",
    )
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="DEAD_STOCK:2", first_seen=timezone.now(), assigned_to=cu
    )
    _only_rows(monkeypatch, [])
    result = sweep_attention_state(tenant_a.company)
    assert AttentionRowState.objects.get(company=tenant_a.company, dedupe_key="DEAD_STOCK:1").snooze_until is None
    assert result["resolved"] == 1
    assert AttentionOutcome.objects.filter(company=tenant_a.company, dedupe_key="DEAD_STOCK:2").exists()


@pytest.mark.django_db
def test_sweep_covers_companies_without_ai_features(tenant_a):
    from insights.tasks import _iter_all_company_ids, sweep_attention_state_for_company

    tenant_a.company.ai_features_enabled = False
    tenant_a.company.save(update_fields=["ai_features_enabled"])
    assert tenant_a.company.pk in set(_iter_all_company_ids())
    result = sweep_attention_state_for_company.apply(args=[str(tenant_a.company.pk)])
    assert result.successful() and result.result["ok"] is True


def test_the_sweep_is_scheduled():
    from django.conf import settings

    assert settings.CELERY_BEAT_SCHEDULE["insights-attention-sweep"]["task"] == "insights.tasks.sweep_attention_state_task"


@pytest.mark.django_db
def test_an_unrelated_failing_check_does_not_freeze_everything_else(tenant_a, monkeypatch):
    """Only the failed check's own codes keep their state; DEAD_STOCK belongs to 'leakage', not 'irn'."""
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="DEAD_STOCK:7", first_seen=timezone.now(), dismissed=True
    )
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="IRN_FAILED:sales_invoice:7", first_seen=timezone.now(), dismissed=True
    )
    _only_rows(monkeypatch, [], _status(failed=["irn"]))
    sweep_attention_state(tenant_a.company)
    states = {s.dedupe_key: s.dismissed for s in AttentionRowState.objects.filter(company=tenant_a.company)}
    assert states["IRN_FAILED:sales_invoice:7"] is True
    assert states["DEAD_STOCK:7"] is False


@pytest.mark.django_db
def test_a_failure_with_no_known_owner_freezes_everything(tenant_a, monkeypatch):
    AttentionRowState.objects.create(
        company=tenant_a.company, dedupe_key="DEAD_STOCK:8", first_seen=timezone.now(), dismissed=True
    )
    _only_rows(monkeypatch, [], _status(failed=["some_new_detector"]))
    sweep_attention_state(tenant_a.company)
    assert AttentionRowState.objects.get(company=tenant_a.company, dedupe_key="DEAD_STOCK:8").dismissed is True


@pytest.mark.django_db
def test_unknown_codes_are_refused(tenant_a):
    from core.exceptions import BusinessRuleError

    for fn in (
        lambda: dismiss_attention_row(tenant_a.company, _owner(tenant_a), dedupe_key="MADE_UP:1"),
        lambda: snooze_attention_row(tenant_a.company, _owner(tenant_a), dedupe_key="MADE_UP:1", days=1, reason="x"),
    ):
        with pytest.raises(BusinessRuleError):
            fn()
    assert not AttentionRowState.objects.filter(company=tenant_a.company, dedupe_key="MADE_UP:1").exists()


@pytest.mark.django_db
def test_every_detector_name_the_feed_can_report_has_an_owner_mapping():
    import re
    from pathlib import Path

    src = (Path(attention_module.__file__)).read_text(encoding="utf-8")
    names = set(re.findall(r'_guard\(\s*"([a-z_]+)"', src)) | set(re.findall(r'report_detector_failure\("([a-z_.]+)"\)', src))
    alerts = (Path(attention_module.__file__).parent / "alerts.py").read_text(encoding="utf-8")
    names |= {f"alerts.{n}" for n in re.findall(r'builders\.append\(\("([a-z_]+)"', alerts)}
    names |= {f"alerts.{n}" for n in re.findall(r'^\s+\("([a-z_]+)", _[a-z_]+\),', alerts, re.M)}
    assert len(names) >= 20
    missing = sorted(n for n in names if n not in attention_module.DETECTOR_CODES)
    assert missing == [], f"add these detectors to DETECTOR_CODES: {missing}"


@pytest.mark.django_db
def test_dismissing_a_snoozed_row_replaces_the_snooze(tenant_a):
    cu = _owner(tenant_a)
    key = "DEAD_STOCK:product:31"
    snooze_attention_row(tenant_a.company, cu, dedupe_key=key, days=5, reason="later")
    dismiss_attention_row(tenant_a.company, cu, dedupe_key=key, reason="not needed")
    state = AttentionRowState.objects.get(company=tenant_a.company, dedupe_key=key)
    assert state.dismissed is True and state.snooze_until is None
    snooze_attention_row(tenant_a.company, cu, dedupe_key=key, days=2, reason="again")
    state.refresh_from_db()
    assert state.dismissed is False and state.snooze_until is not None
