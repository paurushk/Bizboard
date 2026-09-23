from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from core.exceptions import BusinessRuleError
from core.permissions import CanViewFinancialReports, HasCompany, IsOwner, get_company_user
from .attention import build_attention_rows, snooze_attention_row

from .assistant import confirm_proposed_action, dismiss_proposed_action, run_assistant_turn
from .models import (
    AiUsageLedger,
    AssistantThread,
    BusinessAlertEvent,
    BusinessHealthSnapshot,
    DailyBusinessSummary,
)
from .serializers import (
    AiUsageLedgerSerializer,
    AssistantMessageSerializer,
    AssistantThreadListSerializer,
    AssistantThreadSerializer,
    BusinessAlertEventSerializer,
    BusinessHealthSnapshotSerializer,
    DailyBusinessSummarySerializer,
)
from .services import (
    build_growth_hints,
    compute_health_score,
    forecast_cashflow,
    generate_daily_summary,
    upsert_alerts,
)


class CanViewAiInsights(IsAuthenticated):
    message = "AI insights permission required."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        cu = get_company_user(request)
        if cu is None:
            return False
        if not cu.company.ai_features_enabled:
            return False
        # Wave 12B: AI insights are gated on the dedicated capability only —
        # can_view_financial_reports no longer implicitly grants AI insights.
        return cu.role == "OWNER" or cu.can_view_ai_insights


class CanUseAiAssistant(IsAuthenticated):
    message = "AI assistant permission required."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        cu = get_company_user(request)
        if cu is None:
            return False
        if not cu.company.ai_features_enabled:
            return False
        return cu.role == "OWNER" or cu.can_use_ai_assistant


class DailySummaryView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewAiInsights]

    def get(self, request):
        company = get_company_user(request).company
        date_str = request.query_params.get("date")
        for_date = None
        if date_str:
            from datetime import date as date_cls

            for_date = date_cls.fromisoformat(date_str)
        for_date = for_date or timezone.localdate()
        # R-044: GET reads the last snapshot and must not insert/write.
        existing = DailyBusinessSummary.objects.filter(
            company=company, summary_date=for_date
        ).first()
        if existing is None:
            return Response({
                "id": None,
                "summary_date": for_date.isoformat(),
                "kpis": {},
                "alert_codes": [],
                "narrative": "",
                "prompt_version": "",
                "email_sent_at": None,
                "created_at": None,
            })
        return Response(DailyBusinessSummarySerializer(existing).data)

    def post(self, request):
        """Force-generate (Owner)."""
        cu = get_company_user(request)
        if cu.role != "OWNER":
            return Response({"detail": "Owner required."}, status=status.HTTP_403_FORBIDDEN)
        date_str = request.data.get("date") or request.query_params.get("date")
        for_date = None
        if date_str:
            from datetime import date as date_cls

            for_date = date_cls.fromisoformat(date_str)
        obj = generate_daily_summary(cu.company, for_date=for_date, send_email=True)
        return Response(DailyBusinessSummarySerializer(obj).data)


class BusinessAlertViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, HasCompany, CanViewAiInsights]
    serializer_class = BusinessAlertEventSerializer

    def get_queryset(self):
        company = get_company_user(self.request).company
        qs = BusinessAlertEvent.objects.filter(company=company)
        status_f = self.request.query_params.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        else:
            qs = qs.filter(status=BusinessAlertEvent.Status.OPEN)
        severity = self.request.query_params.get("severity")
        if severity:
            qs = qs.filter(severity=severity)
        return qs

    def refresh(self, request):
        cu = get_company_user(request)
        if cu.role != "OWNER":
            return Response({"detail": "Owner required."}, status=status.HTTP_403_FORBIDDEN)
        results = upsert_alerts(cu.company)
        open_rows = [a for a in results if a.status == BusinessAlertEvent.Status.OPEN]
        return Response(BusinessAlertEventSerializer(open_rows, many=True).data)

    def snooze(self, request, pk=None):
        company = get_company_user(request).company
        try:
            alert = BusinessAlertEvent.objects.get(pk=pk, company=company)
        except BusinessAlertEvent.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        days = int(request.data.get("days") or 7)
        days = max(1, min(days, 90))
        alert.status = BusinessAlertEvent.Status.SNOOZED
        alert.snoozed_until = timezone.now() + timedelta(days=days)
        alert.save(update_fields=["status", "snoozed_until", "updated_at"])
        return Response(BusinessAlertEventSerializer(alert).data)


class HealthScoreView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewAiInsights]

    def get(self, request):
        company = get_company_user(request).company
        data = compute_health_score(company)
        data["score"] = str(data["score"])
        return Response(data)


class HealthHistoryView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewAiInsights]

    def get(self, request):
        company = get_company_user(request).company
        # R-044: GET reads last snapshots; scheduled tasks persist new ones.
        qs = BusinessHealthSnapshot.objects.filter(company=company).order_by("-as_of")[:90]
        return Response(BusinessHealthSnapshotSerializer(qs, many=True).data)


class CashflowForecastView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewAiInsights]

    def get(self, request):
        company = get_company_user(request).company
        horizon = int(request.query_params.get("horizon") or 14)
        data = forecast_cashflow(company, horizon=horizon)
        return Response(data)


class GrowthHintsView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewAiInsights]

    def get(self, request):
        company = get_company_user(request).company
        return Response({"hints": build_growth_hints(company)})


class AssistantThreadViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, HasCompany, CanUseAiAssistant]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return AssistantThread.objects.filter(company=get_company_user(self.request).company)

    def get_serializer_class(self):
        if self.action == "list":
            return AssistantThreadListSerializer
        return AssistantThreadSerializer

    def create(self, request, *args, **kwargs):
        # B9-035: `create` is fully overridden below, so a `perform_create`
        # override was dead code and has been removed.
        cu = get_company_user(request)
        thread = AssistantThread.objects.create(
            company=cu.company,
            created_by=request.user,
            title=(request.data.get("title") or "Chat")[:255],
        )
        return Response(AssistantThreadSerializer(thread).data, status=status.HTTP_201_CREATED)


class AssistantMessageCreateView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanUseAiAssistant]

    def post(self, request, thread_id):
        cu = get_company_user(request)
        try:
            thread = AssistantThread.objects.get(pk=thread_id, company=cu.company)
        except AssistantThread.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        content = (request.data.get("content") or "").strip()
        if not content:
            return Response({"detail": "content required"}, status=status.HTTP_400_BAD_REQUEST)
        from core.exceptions import BusinessRuleError

        try:
            msg = run_assistant_turn(cu.company, request.user, thread, content)
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AssistantMessageSerializer(msg).data, status=status.HTTP_201_CREATED)


class AssistantConfirmActionView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanUseAiAssistant]

    def post(self, request):
        cu = get_company_user(request)
        message_id = request.data.get("message_id") or request.data.get("messageId")
        from core.exceptions import BusinessRuleError

        if not message_id:
            return Response(
                {"detail": "message_id required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = confirm_proposed_action(cu.company, request.user, int(message_id))
        except (BusinessRuleError, TypeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class AssistantDismissActionView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanUseAiAssistant]

    def post(self, request):
        cu = get_company_user(request)
        message_id = request.data.get("message_id") or request.data.get("messageId")
        from core.exceptions import BusinessRuleError

        if not message_id:
            return Response(
                {"detail": "message_id required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = dismiss_proposed_action(cu.company, int(message_id))
        except (BusinessRuleError, TypeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class AttentionFeedView(APIView):
    """B-05: ranked AttentionRow feed. Not AI-gated — capability-filtered."""

    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request):
        cu = get_company_user(request)
        rows = build_attention_rows(cu.company, company_user=cu)
        mine = str(request.query_params.get("mine") or "").lower() in {"1", "true", "yes"}
        if mine and rows and "assigned_to" in rows[0]:
            rows = [row for row in rows if row.get("assigned_to") == cu.id]
        elif mine and rows and "assigned_to" not in rows[0]:
            pass
        return Response({"rows": rows, "count": len(rows)})


class AttentionSnoozeView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def post(self, request):
        cu = get_company_user(request)
        dedupe_key = (request.data.get("dedupe_key") or request.data.get("dedupeKey") or "").strip()
        if not dedupe_key:
            return Response({"detail": "dedupe_key required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = snooze_attention_row(
                cu.company,
                cu,
                dedupe_key=dedupe_key,
                days=request.data.get("days") or 7,
                reason=request.data.get("reason") or "",
            )
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (TypeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class AttentionAssignView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def post(self, request):
        from insights.attention import assign_attention_row

        cu = get_company_user(request)
        dedupe_key = (request.data.get("dedupe_key") or request.data.get("dedupeKey") or "").strip()
        try:
            result = assign_attention_row(
                cu.company,
                cu,
                dedupe_key=dedupe_key,
                assignee_id=request.data.get("assigned_to") or request.data.get("assignedTo"),
                due_date=request.data.get("due_date") or request.data.get("dueDate"),
            )
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({"detail": "due_date must be YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class CollectionsWorklistView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request):
        from core.services.feature_flags import flag_enabled
        from payments.predictive_dunning import collections_worklist

        company = get_company_user(request).company
        if not flag_enabled(company, "ENABLE_PREDICTIVE_DUNNING"):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        rows = collections_worklist(company)
        return Response({"rows": rows, "count": len(rows)})


class Customer360View(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request, customer_id):
        from core.services.feature_flags import flag_enabled
        from insights.customer_360 import can_open_customer_360, customer_360
        from masters.models import Customer

        cu = get_company_user(request)
        if not flag_enabled(cu.company, "ENABLE_CUSTOMER_360"):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_open_customer_360(cu):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        customer = Customer.objects.filter(company=cu.company, pk=customer_id).first()
        if customer is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(customer_360(cu.company, customer, cu))


class AiUsageView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        company = get_company_user(request).company
        start = timezone.localdate().replace(day=1)
        qs = AiUsageLedger.objects.filter(company=company, created_at__date__gte=start)
        total_in = sum(r.tokens_in for r in qs)
        total_out = sum(r.tokens_out for r in qs)
        budget = company.ai_monthly_token_budget
        return Response({
            "period_start": start.isoformat(),
            "tokens_in": total_in,
            "tokens_out": total_out,
            "tokens_total": total_in + total_out,
            "budget": budget,
            "recent": AiUsageLedgerSerializer(qs.order_by("-created_at")[:20], many=True).data,
        })


_TELEMETRY_EVENTS = {
    "invoice_complete",
    "pos_line_added",
    "offline_enqueue",
    "offline_flush_fail",
    "complete_duration_ms",
    "time_to_first_invoice_ms",
    "signup_completed",
    "wizard_tax_confirmed",
    "wizard_completed",
    "journey_started",
    "journey_failed",
}

_ALLOWED_TELEMETRY_KEYS = {
    "event",
    "duration_ms",
    "tap_count",
    "journey",
    "feature",
    "role",
    "session_id",
    "request_id",
    "success",
    "failure_reason",
}
_IGNORED_TELEMETRY_KEYS = {"company_id", "company_hash", "companyId", "companyHash"}
_JOURNEY_ALLOWLIST = {"signup", "invoice_complete", "pdf", "payment"}
_FEATURE_ALLOWLIST = _JOURNEY_ALLOWLIST | {"pos", "offline"}
_FAILURE_REASONS = {"validation", "help_code", "timeout", "5xx", "offline", "unknown"}


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, int(round((p / 100) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def _clip(value, max_len: int) -> str:
    text = str(value or "").strip()
    return text[:max_len] if text else ""


def _allowlisted(value: str, allowed: set[str]) -> str:
    return value if value in allowed else ""


class ShopFloorTelemetryView(APIView):
    """A-08: POST events (no PII); GET 7-day owner summary."""

    permission_classes = [IsAuthenticated, HasCompany]
    # B9-032: own throttle bucket so a scripted client can't flood the table.
    throttle_scope = "telemetry"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle

        return [ScopedRateThrottle()] if self.request.method == "POST" else []

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return [IsAuthenticated(), HasCompany()]

    def post(self, request):
        from core.observability import current_request_id

        from .models import ShopFloorEvent

        payload = request.data if isinstance(request.data, dict) else {}
        # B9-032 / OG2-E7: strict allowlist. company_id / company_hash are
        # ignored (never stored); any other extra key is 400.
        for key in payload:
            name = str(key)
            if name in _IGNORED_TELEMETRY_KEYS:
                continue
            if name not in _ALLOWED_TELEMETRY_KEYS:
                raise BusinessRuleError(
                    "Telemetry accepts only: event, duration_ms, tap_count, "
                    "journey, feature, role, session_id, request_id, success, "
                    "failure_reason."
                )
        event = str(payload.get("event") or "").strip()
        if event not in _TELEMETRY_EVENTS:
            raise BusinessRuleError("Unknown telemetry event.")
        duration = payload.get("duration_ms")
        taps = payload.get("tap_count")
        try:
            duration_ms = int(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration_ms = None
        try:
            tap_count = int(taps) if taps is not None else None
        except (TypeError, ValueError):
            tap_count = None
        if duration_ms is not None and duration_ms > 24 * 60 * 60 * 1000:
            duration_ms = None

        journey = _allowlisted(_clip(payload.get("journey"), 40), _JOURNEY_ALLOWLIST)
        feature = _allowlisted(_clip(payload.get("feature"), 40), _FEATURE_ALLOWLIST)
        failure_reason = _clip(payload.get("failure_reason"), 16)
        if failure_reason and failure_reason not in _FAILURE_REASONS:
            raise BusinessRuleError("Unknown failure_reason.")
        if event == "journey_failed":
            if not journey:
                raise BusinessRuleError("journey is required for journey_failed.")
            if not failure_reason:
                raise BusinessRuleError("failure_reason is required for journey_failed.")
        if event == "journey_started" and not journey:
            raise BusinessRuleError("journey is required for journey_started.")

        cu = get_company_user(request)
        # Server stamps: never trust client role / success / invoice_complete journey.
        role = (getattr(cu, "role", None) or "")[:16]
        success = None
        if event == "invoice_complete":
            journey = "invoice_complete"
            success = True
        elif event == "journey_failed":
            success = False
        elif event == "journey_started":
            success = None

        request_id = _clip(payload.get("request_id"), 64)
        if not request_id:
            request_id = _clip(
                getattr(request, "request_id", None) or current_request_id(),
                64,
            )
        session_id = _clip(payload.get("session_id"), 36)

        ShopFloorEvent.objects.create(
            company=cu.company,
            event=event,
            duration_ms=duration_ms,
            tap_count=tap_count,
            occurred_on=timezone.localdate(),
            journey=journey,
            feature=feature,
            role=role,
            session_id=session_id,
            request_id=request_id,
            success=success,
            failure_reason=failure_reason if event == "journey_failed" else "",
            created_by=request.user,
            updated_by=request.user,
        )
        return Response({"ok": True}, status=status.HTTP_201_CREATED)

    def get(self, request):
        from .models import ShopFloorEvent

        company = get_company_user(request).company
        days = 7
        start = timezone.localdate() - timedelta(days=days - 1)
        qs = ShopFloorEvent.objects.filter(company=company, occurred_on__gte=start)
        durations = sorted(
            int(r.duration_ms)
            for r in qs.filter(event__in=("complete_duration_ms", "invoice_complete"))
            if r.duration_ms
        )
        alloc_total = qs.filter(event="allocation_reconciled").count()
        alloc_bad = qs.filter(event="allocation_reconciled", tap_count__gte=1).count()
        enqueued = qs.filter(event="offline_enqueue").count()
        flush_fail = qs.filter(event="offline_flush_fail").count()
        # SR-54 / H-02: pointer presses during a checkout (0 == keyboard + scanner only)
        checkout_taps = list(
            qs.filter(event="invoice_complete", tap_count__isnull=False).values_list("tap_count", flat=True)
        )
        keyboard_only = sum(1 for tc in checkout_taps if tc == 0)
        return Response({
            "days": days,
            # H-02 — counter checkout speed + keyboard-only rate
            "complete_p95_ms": _percentile(durations, 95),
            "complete_count": qs.filter(event="invoice_complete").count(),
            "pos_line_added": qs.filter(event="pos_line_added").count(),
            "checkouts_measured": len(checkout_taps),
            "keyboard_only_checkouts": keyboard_only,
            "keyboard_only_rate": (
                round(keyboard_only / len(checkout_taps), 3) if checkout_taps else None
            ),
            # H-01 — B2B ledger reconciliation (pass: 0 discrepancies / 100 allocations)
            "allocations": alloc_total,
            "allocation_discrepancies": alloc_bad,
            "allocation_ok": alloc_total == 0 or alloc_bad == 0,
            # H-03 — offline outbox integrity (pass: 0 flush failures)
            "offline_enqueue": enqueued,
            "offline_flush_fail": flush_fail,
            "offline_ok": flush_fail == 0,
            # cadence
            "periods_closed": qs.filter(event="period_closed").count(),
            # 15.3 unaided-onboarding funnel (counts only; no PII)
            "funnel": {
                "signup_completed": qs.filter(event="signup_completed").count(),
                "wizard_tax_confirmed": qs.filter(event="wizard_tax_confirmed").count(),
                "wizard_completed": qs.filter(event="wizard_completed").count(),
                # Read-side UNION: Gate 2 writers only emit invoice_complete.
                "invoice_complete": qs.filter(
                    Q(event="invoice_complete")
                    | Q(event="journey_completed", journey="invoice_complete")
                ).count(),
                "invoice_complete_started": qs.filter(
                    event="journey_started", journey="invoice_complete"
                ).count(),
                "invoice_complete_failed": qs.filter(
                    event="journey_failed", journey="invoice_complete"
                ).count(),
                "invoice_complete_failed_by_reason": _failed_by_reason(qs, "invoice_complete"),
                "signup_failed": qs.filter(
                    event="journey_failed", journey="signup"
                ).count(),
                "signup_failed_by_reason": _failed_by_reason(qs, "signup"),
                "pdf_started": qs.filter(event="journey_started", journey="pdf").count(),
                "pdf_failed": qs.filter(event="journey_failed", journey="pdf").count(),
                "pdf_failed_by_reason": _failed_by_reason(qs, "pdf"),
                "payment_started": qs.filter(
                    event="journey_started", journey="payment"
                ).count(),
                "payment_completed": qs.filter(event="allocation_reconciled").count(),
                "payment_failed": qs.filter(
                    event="journey_failed", journey="payment"
                ).count(),
                "payment_failed_by_reason": _failed_by_reason(qs, "payment"),
            },
        })


def _failed_by_reason(qs, journey: str) -> dict:
    counts = {reason: 0 for reason in sorted(_FAILURE_REASONS)}
    rows = (
        qs.filter(event="journey_failed", journey=journey)
        .values("failure_reason")
        .annotate(n=Count("id"))
    )
    for row in rows:
        key = row["failure_reason"] or "unknown"
        if key in counts:
            counts[key] += row["n"]
        else:
            counts["unknown"] += row["n"]
    return counts
