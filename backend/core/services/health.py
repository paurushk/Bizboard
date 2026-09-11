"""Help-desk health rollups — extracted from `core.help_views.HelpHealthView`
so the same computation can back both the DRF endpoint and the `ops` Django-
admin health page without duplicating the aggregation logic."""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from datetime import timedelta
from statistics import median

from django.db.models import Count, Q
from django.utils import timezone

from core.models import HelpEvent, HelpFeedback

_TTR_ROW_CAP = 8000
RATING_NAMES = ("faq_resolved", "faq_understood_pending", "faq_unresolved")


def _median_seconds(values: list[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


@contextmanager
def staff_all_rls(enabled: bool):
    # SYS-01: unified RLS bypass GUC (the per-table policy checks
    # app.rls_bypass, not the old help-only app.help_staff_all).
    if not enabled:
        yield
        return
    from core.rls import rls_bypass

    with rls_bypass():
        yield


def _time_to_resolution(events):
    """Median seconds from last help_open to faq_resolved, same user+intent.

    Caps each side at ``_TTR_ROW_CAP`` most-recent rows so staff ``?all=1``
    cannot load an unbounded 30-day dump into Python.
    """
    resolved = list(
        events.filter(name="faq_resolved")
        .exclude(intent_id="")
        .order_by("-created_at")
        .values("company_id", "created_by_id", "intent_id", "created_at")[:_TTR_ROW_CAP]
    )
    opens = list(
        events.filter(name="help_open")
        .exclude(intent_id="")
        .order_by("-created_at")
        .values("company_id", "created_by_id", "intent_id", "created_at")[:_TTR_ROW_CAP]
    )
    resolved.reverse()
    opens.reverse()
    buckets: dict[tuple, list] = defaultdict(list)
    for row in opens:
        buckets[(row["company_id"], row["created_by_id"], row["intent_id"])].append(row["created_at"])
    deltas: list[float] = []
    per_intent: dict[str, list[float]] = defaultdict(list)
    for row in resolved:
        key = (row["company_id"], row["created_by_id"], row["intent_id"])
        prior = [ts for ts in buckets[key] if ts <= row["created_at"]]
        if not prior:
            continue
        seconds = (row["created_at"] - prior[-1]).total_seconds()
        deltas.append(seconds)
        per_intent[row["intent_id"]].append(seconds)
    return _median_seconds(deltas), {k: _median_seconds(v) for k, v in per_intent.items()}


def _latest_ratings(events):
    """Last of resolved/understood/unresolved per (company, user, intent)."""
    rows = (
        events.filter(name__in=RATING_NAMES)
        .exclude(intent_id="")
        .order_by("created_at")
        .values("company_id", "created_by_id", "intent_id", "name")
    )
    latest: dict[tuple, str] = {}
    for row in rows:
        latest[(row["company_id"], row["created_by_id"], row["intent_id"])] = row["name"]
    resolved = sum(1 for name in latest.values() if name == "faq_resolved")
    understood = sum(1 for name in latest.values() if name == "faq_understood_pending")
    unresolved = sum(1 for name in latest.values() if name == "faq_unresolved")
    per_intent: dict[str, dict[str, int]] = defaultdict(lambda: {"resolved": 0, "unresolved": 0})
    for (_company, _user, intent_id), name in latest.items():
        if name == "faq_resolved":
            per_intent[intent_id]["resolved"] += 1
        elif name == "faq_unresolved":
            per_intent[intent_id]["unresolved"] += 1
    return resolved, understood, unresolved, per_intent


def compute_help_health(*, company=None, staff_all: bool = False) -> dict:
    """30-day help-desk rollup. `company=None` + `staff_all=True` aggregates
    across every tenant (RLS-bypassed); otherwise scoped to `company`."""
    since = timezone.now() - timedelta(days=30)
    events = HelpEvent.objects.filter(created_at__gte=since)
    feedback = HelpFeedback.objects.filter(created_at__gte=since)
    with staff_all_rls(staff_all):
        if not staff_all:
            events = events.filter(company=company)
            feedback = feedback.filter(company=company)

        opens = events.filter(name="help_open").count()
        resolved, understood, unresolved, per_intent_latest = _latest_ratings(events)
        escalation_count = feedback.count()
        rated = resolved + understood + unresolved
        resolution_rate = (resolved / rated) if rated else None
        escalation_rate = (unresolved / rated) if rated else None

        searches = events.filter(name="help_search")
        zero = searches.filter(Q(state="no-match") | Q(props__result_count=0)).count()
        search_count = searches.count()

        top_zero = list(
            searches.filter(Q(state="no-match") | Q(props__result_count=0))
            .exclude(query="")
            .values("query")
            .annotate(n=Count("id"))
            .order_by("-n")[:15]
        )

        intent_stats = list(
            events.exclude(intent_id="")
            .values("intent_id")
            .annotate(
                opens=Count("id", filter=Q(name="help_open")),
                searches=Count("id", filter=Q(name="help_search")),
            )
            .order_by("-opens")[:30]
        )
        ttr_overall, ttr_by_intent = _time_to_resolution(events)
        for row in intent_stats:
            latest = per_intent_latest.get(row["intent_id"], {"resolved": 0, "unresolved": 0})
            row["resolved"] = latest["resolved"]
            row["unresolved"] = latest["unresolved"]
            denom = latest["resolved"] + latest["unresolved"]
            row["resolution_rate"] = (latest["resolved"] / denom) if denom else None
            row["time_to_resolution_seconds"] = ttr_by_intent.get(row["intent_id"])

        # Per-user (and company) repeats: the same person asking the same query ≥2 times.
        query_counts = searches.exclude(query="").values("created_by_id", "query").annotate(n=Count("id"))
        unique_pairs = query_counts.count()
        repeat_distinct = query_counts.filter(n__gte=2).count()
        repeat_query_rate = (repeat_distinct / unique_pairs) if unique_pairs else None

        repeat_query = list(
            searches.exclude(query="")
            .values("query")
            .annotate(n=Count("id"))
            .filter(n__gte=3)
            .order_by("-n")[:15]
        )

        return {
            "window_days": 30,
            "scope": "all" if staff_all else "company",
            "resolution_rate": resolution_rate,
            "escalation_rate": escalation_rate,
            "repeat_query_rate": repeat_query_rate,
            "time_to_resolution_seconds": ttr_overall,
            "opens": opens,
            "rated": rated,
            "resolved": resolved,
            "understood_pending": understood,
            "unresolved": unresolved,
            "feedback_open": feedback.filter(resolved_at__isnull=True).count(),
            "search_count": search_count,
            "zero_result_count": zero,
            "zero_result_rate": (zero / search_count) if search_count else None,
            "top_zero_queries": top_zero,
            "intents": intent_stats,
            "repeat_queries": repeat_query,
            "escalation_count": escalation_count,
        }
