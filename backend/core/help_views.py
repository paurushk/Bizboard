"""Help events, stuck-capture, and health rollups."""

from __future__ import annotations

import json
from collections import defaultdict
from contextlib import contextmanager
from datetime import timedelta
from statistics import median

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.models import HelpEvent, HelpFeedback
from core.permissions import HasCompany, get_company_user
# (RLS bypass is imported lazily where used — SYS-01)

_MAX_PROPS_BYTES = 2048
_TTR_ROW_CAP = 8000
_RATING_NAMES = ("faq_resolved", "faq_understood_pending", "faq_unresolved")


def _median_seconds(values: list[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


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
        events.filter(name__in=_RATING_NAMES)
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


def _sanitize_props(props: dict) -> dict:
    """Drop the query duplicate and cap JSON size (DoS / table bloat)."""
    cleaned = {key: value for key, value in props.items() if key != "query"}
    try:
        encoded = json.dumps(cleaned, default=str)
    except (TypeError, ValueError):
        return {}
    if len(encoded) > _MAX_PROPS_BYTES:
        return {"_truncated": True}
    return cleaned


def _cu(request):
    return get_company_user(request)


def _no_company():
    return Response({"detail": "No company."}, status=403)


@contextmanager
def _staff_all_rls(enabled: bool):
    # SYS-01: unified RLS bypass GUC (the per-table policy now checks
    # app.rls_bypass, not the old help-only app.help_staff_all).
    if not enabled:
        yield
        return
    from core.rls import rls_bypass

    with rls_bypass():
        yield


class HelpEventsView(APIView):
    """POST /api/v1/help-events/ — batched first-party events. Raw query stays on-box."""

    permission_classes = [IsAuthenticated, HasCompany]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "help_events"

    def post(self, request):
        cu = _cu(request)
        if cu is None:
            return _no_company()
        payload = request.data if isinstance(request.data, dict) else {}
        raw_events = payload.get("events")
        if not isinstance(raw_events, list):
            raw_events = [payload]
        created = 0
        for item in raw_events[:50]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()[:64]
            if not name:
                continue
            query = str(item.get("query") or "")[:2000]
            props = item.get("props") if isinstance(item.get("props"), dict) else {}
            intent_id = str(item.get("intentId") or item.get("intent_id") or "")[:64]
            if name in _RATING_NAMES and intent_id:
                existing = (
                    HelpEvent.objects.filter(
                        company=cu.company,
                        created_by=request.user,
                        intent_id=intent_id,
                        name__in=_RATING_NAMES,
                    )
                    .order_by("-created_at")
                    .first()
                )
                if existing is not None:
                    existing.name = name
                    existing.updated_by = request.user
                    existing.source = str(item.get("source") or existing.source or "")[:32]
                    existing.state = str(item.get("state") or existing.state or "")[:24]
                    existing.screen = str(item.get("screen") or existing.screen or "")[:128]
                    existing.query = query or existing.query
                    existing.props = _sanitize_props(props)
                    existing.save(
                        update_fields=[
                            "name",
                            "updated_by",
                            "updated_at",
                            "source",
                            "state",
                            "screen",
                            "query",
                            "props",
                        ]
                    )
                    created += 1
                    continue
            HelpEvent.objects.create(
                company=cu.company,
                created_by=request.user,
                updated_by=request.user,
                name=name,
                intent_id=intent_id,
                source=str(item.get("source") or "")[:32],
                state=str(item.get("state") or "")[:24],
                screen=str(item.get("screen") or "")[:128],
                query=query,
                props=_sanitize_props(props),
            )
            created += 1
        return Response({"accepted": created})


class HelpFeedbackView(APIView):
    """POST capture-only 'still stuck'. GET lists backlog. PATCH sets resolved_at."""

    permission_classes = [IsAuthenticated, HasCompany]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "help_feedback"

    def post(self, request):
        cu = _cu(request)
        if cu is None:
            return _no_company()
        body = request.data if isinstance(request.data, dict) else {}
        row = HelpFeedback.objects.create(
            company=cu.company,
            created_by=request.user,
            updated_by=request.user,
            query=str(body.get("query") or "")[:2000],
            screen=str(body.get("screen") or "")[:128],
            role=str(getattr(cu, "role", "") or "")[:32],
            intent_id=str(body.get("intentId") or body.get("intent_id") or "")[:64],
            note=str(body.get("note") or "")[:4000],
        )
        return Response({"id": row.id})

    def get(self, request):
        cu = _cu(request)
        if cu is None:
            return Response({"results": []})
        staff_all = bool(getattr(request.user, "is_staff", False)) and str(
            request.query_params.get("all") or ""
        ).lower() in {"1", "true", "yes"}
        qs = HelpFeedback.objects.filter(resolved_at__isnull=True)
        if not staff_all:
            if cu.role != "OWNER":
                return Response({"results": []})
            qs = qs.filter(company=cu.company)
        with _staff_all_rls(staff_all):
            rows = list(qs.select_related("company", "created_by")[:100])
        return Response(
            {
                "results": [
                    {
                        "id": r.id,
                        "company": r.company_id,
                        "company_name": r.company.name,
                        "query": r.query,
                        "screen": r.screen,
                        "role": r.role,
                        "intent_id": r.intent_id,
                        "note": r.note,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
                    }
                    for r in rows
                ]
            }
        )

    def patch(self, request):
        """Owner / staff marks a still-stuck row resolved (triage close)."""
        cu = _cu(request)
        if cu is None:
            return _no_company()
        staff_all = bool(getattr(request.user, "is_staff", False)) and str(
            request.query_params.get("all") or ""
        ).lower() in {"1", "true", "yes"}
        is_owner = cu.role == "OWNER"
        if not staff_all and not is_owner:
            return Response({"detail": "Owner role required."}, status=403)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            pk = int(body.get("id"))
        except (TypeError, ValueError):
            return Response({"detail": "id required."}, status=400)
        with _staff_all_rls(staff_all):
            qs = HelpFeedback.objects.filter(pk=pk)
            if not staff_all:
                qs = qs.filter(company=cu.company)
            row = qs.first()
            if row is None:
                return Response({"detail": "Not found."}, status=404)
            row.resolved_at = timezone.now()
            row.updated_by = request.user
            row.save(update_fields=["resolved_at", "updated_at", "updated_by"])
        return Response(
            {
                "id": row.id,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            }
        )


class HelpHealthView(APIView):
    """GET /api/v1/help-health/ — Owner: own company. is_staff + ?all=1: aggregate."""

    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        cu = _cu(request)
        staff_all = bool(getattr(request.user, "is_staff", False)) and str(
            request.query_params.get("all") or ""
        ).lower() in {"1", "true", "yes"}
        is_owner = cu is not None and cu.role == "OWNER"
        if not staff_all and not is_owner:
            return Response({"detail": "Owner role required."}, status=403)

        since = timezone.now() - timedelta(days=30)
        events = HelpEvent.objects.filter(created_at__gte=since)
        feedback = HelpFeedback.objects.filter(created_at__gte=since)
        with _staff_all_rls(staff_all):
            if not staff_all:
                events = events.filter(company=cu.company)
                feedback = feedback.filter(company=cu.company)

            opens = events.filter(name="help_open").count()
            resolved, understood, unresolved, per_intent_latest = _latest_ratings(events)
            # Capture-only rows, not also faq_unresolved events (one still-stuck + note ≠ 2).
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

            return Response(
                {
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
            )
