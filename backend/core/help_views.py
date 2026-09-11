"""Help events, stuck-capture, and health rollups."""

from __future__ import annotations

import json

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.models import HelpEvent, HelpFeedback
from core.permissions import HasCompany, get_company_user
from core.services.health import RATING_NAMES as _RATING_NAMES
from core.services.health import compute_help_health
from core.services.health import staff_all_rls as _staff_all_rls

_MAX_PROPS_BYTES = 2048


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
    # B7-013: normalise "no active company" across every help view — a
    # multi-membership user with no picked company returns None here (handled as
    # a plain 403 by the caller) instead of one view 409-ing with the membership
    # list and another quietly returning an empty payload.
    from core.exceptions import CompanyRequired

    try:
        return get_company_user(request)
    except CompanyRequired:
        return None


def _no_company():
    return Response({"detail": "Select a company to continue."}, status=403)


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
        items = [item for item in raw_events[:50] if isinstance(item, dict)]

        # B7-019: fetch the latest rating row per intent_id in one query
        # instead of one SELECT per rating item, and bulk_create the
        # non-rating-update events instead of one INSERT each — this was up
        # to ~100 sequential round-trips for a full batch.
        rating_intent_ids = {
            str(item.get("intentId") or item.get("intent_id") or "")[:64]
            for item in items
            if str(item.get("name") or "").strip()[:64] in _RATING_NAMES
            and (item.get("intentId") or item.get("intent_id"))
        }
        latest_by_intent: dict[str, HelpEvent] = {}
        if rating_intent_ids:
            for row in (
                HelpEvent.objects.filter(
                    company=cu.company,
                    created_by=request.user,
                    intent_id__in=rating_intent_ids,
                    name__in=_RATING_NAMES,
                )
                .order_by("intent_id", "-created_at")
            ):
                latest_by_intent.setdefault(row.intent_id, row)

        created = 0
        to_create: list[HelpEvent] = []
        # Two ratings for the same intent_id within one batch must converge
        # onto one row (the original per-item re-query behaviour saw the
        # prior item's just-created row) — for a row this batch itself is
        # about to create (not yet in the DB), track it here and mutate the
        # same pending object in place rather than appending a second one.
        pending_by_intent: dict[str, HelpEvent] = {}
        for item in items:
            name = str(item.get("name") or "").strip()[:64]
            if not name:
                continue
            query = str(item.get("query") or "")[:2000]
            props = item.get("props") if isinstance(item.get("props"), dict) else {}
            intent_id = str(item.get("intentId") or item.get("intent_id") or "")[:64]
            is_rating = name in _RATING_NAMES and bool(intent_id)
            pending = pending_by_intent.get(intent_id) if is_rating else None
            if pending is not None:
                pending.name = name
                pending.updated_by = request.user
                pending.source = str(item.get("source") or pending.source or "")[:32]
                pending.state = str(item.get("state") or pending.state or "")[:24]
                pending.screen = str(item.get("screen") or pending.screen or "")[:128]
                pending.query = query or pending.query
                pending.props = _sanitize_props(props)
                created += 1
                continue
            existing = latest_by_intent.get(intent_id) if is_rating else None
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
            new_event = HelpEvent(
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
            to_create.append(new_event)
            if is_rating:
                pending_by_intent[intent_id] = new_event
            created += 1
        if to_create:
            HelpEvent.objects.bulk_create(to_create)
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
        staff_all = bool(getattr(request.user, "is_staff", False)) and str(
            request.query_params.get("all") or ""
        ).lower() in {"1", "true", "yes"}
        if not staff_all and cu is None:
            return _no_company()
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
    # B7-017: unlike HelpEventsView/HelpFeedbackView, this had no dedicated
    # throttle — it falls back to the default 600/min user rate despite
    # running a heavy 30-day aggregation (two 8000-row fetches + ~8 aggregate
    # queries), and a `?all=1` staff call additionally rls_bypass()es to scan
    # every tenant.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "heavy_reports"

    def get(self, request):
        cu = _cu(request)
        staff_all = bool(getattr(request.user, "is_staff", False)) and str(
            request.query_params.get("all") or ""
        ).lower() in {"1", "true", "yes"}
        # B7-013: a non-staff caller with no active company gets the same 403 as
        # the other help views, not an unhandled 409.
        if not staff_all and cu is None:
            return _no_company()
        is_owner = cu is not None and cu.role == "OWNER"
        if not staff_all and not is_owner:
            return Response({"detail": "Owner role required."}, status=403)

        result = compute_help_health(
            company=cu.company if cu is not None else None, staff_all=staff_all
        )
        return Response(result)
