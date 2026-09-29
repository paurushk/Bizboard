"""Acted outcomes stay inside a 7-day window. The report does not change thresholds."""

from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import CompanyUser
from insights.attention import dismiss_attention_row, snooze_attention_row
from insights.models import AttentionOutcome, AttentionRowState
from insights.outcomes import ROW_WINDOW_DAYS, learning_report, observe_resolved_outcomes


def _member(tenant):
    return CompanyUser.objects.get(company=tenant.company, user=tenant.owner)


@pytest.mark.django_db
def test_assigned_row_that_clears_inside_seven_days_is_acted(tenant_a):
    member = _member(tenant_a)
    state = AttentionRowState.objects.create(
        company=tenant_a.company,
        dedupe_key="AR_OVERDUE_CRITICAL:9",
        first_seen=timezone.now() - timedelta(days=2),
        assigned_to=member,
    )
    observe_resolved_outcomes(tenant_a.company, live_keys=[])
    outcome = AttentionOutcome.objects.get(company=tenant_a.company, dedupe_key=state.dedupe_key)
    assert outcome.outcome == AttentionOutcome.Outcome.RESOLVED
    assert outcome.within_window is True
    assert outcome.metric_improved is False
    assert outcome.code == "AR_OVERDUE_CRITICAL"

    flags_before = dict(tenant_a.company.feature_flags or {})
    report = learning_report(tenant_a.company)
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.feature_flags == flags_before
    assert report["window_days"] == ROW_WINDOW_DAYS == 7
    assert report["acted"] == 1
    assert report["resolved_in_window"] == 1
    assert report["thresholds_changed"] is False


@pytest.mark.django_db
def test_dismiss_inside_the_window_counts_and_snooze_does_not(tenant_a):
    member = _member(tenant_a)
    AttentionRowState.objects.create(
        company=tenant_a.company,
        dedupe_key="DEAD_STOCK:3",
        first_seen=timezone.now(),
    )
    snooze_attention_row(tenant_a.company, member, dedupe_key="DEAD_STOCK:3", days=7, reason="later")
    assert AttentionOutcome.objects.filter(company=tenant_a.company).count() == 0

    dismissed = dismiss_attention_row(tenant_a.company, member, dedupe_key="LOW_STOCK_FAST_MOVER:1")
    assert dismissed["within_window"] is True
    outcome = AttentionOutcome.objects.get(dedupe_key="LOW_STOCK_FAST_MOVER:1")
    assert outcome.outcome == AttentionOutcome.Outcome.DISMISSED
    assert outcome.metric_improved is None
    report = learning_report(tenant_a.company)
    assert report["dismissed_in_window"] == 1
    assert report["metric_improved"] == 0


@pytest.mark.django_db
def test_dismiss_after_the_window_is_not_acted(tenant_a):
    member = _member(tenant_a)
    AttentionRowState.objects.create(
        company=tenant_a.company,
        dedupe_key="CASH_TIGHT_14D:1",
        first_seen=timezone.now() - timedelta(days=8),
    )
    dismiss_attention_row(tenant_a.company, member, dedupe_key="CASH_TIGHT_14D:1")
    outcome = AttentionOutcome.objects.get(dedupe_key="CASH_TIGHT_14D:1")
    assert outcome.within_window is False
    assert learning_report(tenant_a.company)["acted"] == 0
    assert learning_report(tenant_a.company)["outside_window"] == 1


@pytest.mark.django_db
def test_only_an_assigned_row_that_left_the_feed_is_resolved(tenant_a):
    member = _member(tenant_a)
    AttentionRowState.objects.create(
        company=tenant_a.company,
        dedupe_key="UNASSIGNED:1",
        first_seen=timezone.now(),
    )
    staying = AttentionRowState.objects.create(
        company=tenant_a.company,
        dedupe_key="STILL_LIVE:2",
        first_seen=timezone.now(),
        assigned_to=member,
    )
    late = AttentionRowState.objects.create(
        company=tenant_a.company,
        dedupe_key="AR_OVERDUE_CRITICAL:8",
        first_seen=timezone.now() - timedelta(days=8),
        assigned_to=member,
    )
    observe_resolved_outcomes(tenant_a.company, live_keys=["STILL_LIVE:2"])
    assert not AttentionOutcome.objects.filter(dedupe_key="UNASSIGNED:1").exists()
    assert not AttentionOutcome.objects.filter(dedupe_key=staying.dedupe_key).exists()
    late_outcome = AttentionOutcome.objects.get(dedupe_key=late.dedupe_key)
    assert late_outcome.within_window is False
    assert late_outcome.metric_improved is False
    report = learning_report(tenant_a.company)
    assert report["acted"] == 0
    assert report["metric_improved"] == 0
    assert report["by_code"][0]["code"] == "AR_OVERDUE_CRITICAL"

    observe_resolved_outcomes(tenant_a.company, live_keys=[])
    assert AttentionOutcome.objects.filter(dedupe_key=late.dedupe_key).count() == 1


@pytest.mark.django_db
def test_a_second_dismiss_does_not_replace_the_first_outcome(tenant_a):
    member = _member(tenant_a)
    first = dismiss_attention_row(tenant_a.company, member, dedupe_key="NOT_A_SOURCE:4")
    assert first["within_window"] is True
    outcome = AttentionOutcome.objects.get(dedupe_key="NOT_A_SOURCE:4")
    assert outcome.code == "NOT_A_SOURCE"
    assert outcome.metric_improved is None
    snooze_attention_row(tenant_a.company, member, dedupe_key="NOT_A_SOURCE:4", days=3, reason="later")
    assert AttentionOutcome.objects.filter(company=tenant_a.company).count() == 1
    dismiss_attention_row(tenant_a.company, member, dedupe_key="NOT_A_SOURCE:4")
    outcome.refresh_from_db()
    assert outcome.outcome == AttentionOutcome.Outcome.DISMISSED
    assert AttentionOutcome.objects.filter(company=tenant_a.company).count() == 1
