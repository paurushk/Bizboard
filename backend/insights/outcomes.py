"""Outcome tracking for attention rows.

Approval is assignment. Dismiss and snooze are not approval. An acted
outcome is an assigned row that then clears, or a dismiss, inside seven
days of first_seen. The learning report is read-only.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from insights.event_schema import EVENT_SOURCES
from insights.models import AttentionOutcome, AttentionRowState

ROW_WINDOW_DAYS = 7


def code_for_key(dedupe_key: str) -> str:
    code = (dedupe_key or "").split(":", 1)[0]
    if code in EVENT_SOURCES:
        return code
    return code or "UNKNOWN"


def _within_window(first_seen, now) -> bool:
    if first_seen is None:
        return False
    return now <= first_seen + timedelta(days=ROW_WINDOW_DAYS)


def observe_resolved_outcomes(company, live_keys, now=None) -> int:
    """Assigned rows whose condition has left the feed are resolved.

    The row leaving the feed is the measurable improvement. Snooze does
    not call this. A second observation of the same key is ignored.
    """
    now = now or timezone.now()
    live = set(live_keys)
    already = set(
        AttentionOutcome.objects.filter(company=company).values_list("dedupe_key", flat=True)
    )
    states = AttentionRowState.objects.filter(company=company, assigned_to__isnull=False)
    created = []
    for state in states:
        if state.dedupe_key in live or state.dedupe_key in already:
            continue
        within = _within_window(state.first_seen, now)
        created.append(
            AttentionOutcome(
                company=company,
                dedupe_key=state.dedupe_key,
                code=code_for_key(state.dedupe_key),
                outcome=AttentionOutcome.Outcome.RESOLVED,
                within_window=within,
                # Leaving the feed is not proof the metric improved. A lapsed
                # contract, a capped list, or a waiting ticket used to be
                # recorded as a success.
                metric_improved=False,
                recorded_at=now,
            )
        )
    if created:
        AttentionOutcome.objects.bulk_create(created, ignore_conflicts=True)
    return len(created)


def record_dismissal(company, state, now=None) -> AttentionOutcome:
    """Dismiss is an acted outcome inside the window. It is not approval."""
    now = now or timezone.now()
    within = _within_window(state.first_seen, now)
    outcome, _created = AttentionOutcome.objects.get_or_create(
        company=company,
        dedupe_key=state.dedupe_key,
        defaults={
            "code": code_for_key(state.dedupe_key),
            "outcome": AttentionOutcome.Outcome.DISMISSED,
            "within_window": within,
            "metric_improved": None,
            "recorded_at": now,
        },
    )
    return outcome


def learning_report(company) -> dict:
    """A report a person reads. This function does not change thresholds."""
    qs = AttentionOutcome.objects.filter(company=company)
    acted = qs.filter(within_window=True)
    by_code = list(
        qs.values("code").annotate(
            acted=Count("id", filter=Q(within_window=True)),
            metric_improved=Count("id", filter=Q(metric_improved=True)),
        ).order_by("code")
    )
    return {
        "window_days": ROW_WINDOW_DAYS,
        "acted": acted.count(),
        "resolved_in_window": acted.filter(outcome=AttentionOutcome.Outcome.RESOLVED).count(),
        "dismissed_in_window": acted.filter(outcome=AttentionOutcome.Outcome.DISMISSED).count(),
        "outside_window": qs.filter(within_window=False).count(),
        "metric_improved": qs.filter(metric_improved=True).count(),
        "by_code": by_code,
        "thresholds_changed": False,
    }
