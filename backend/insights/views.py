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
from .attention import dismiss_attention_row, snooze_attention_row

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


def _parse_date_param(raw):
    """(date | None, error Response | None): a bad date is a 400, not a 500."""
    from datetime import date as date_cls

    if not raw:
        return None, None
    try:
        return date_cls.fromisoformat(str(raw)), None
    except ValueError:
        return None, Response(
            {"detail": "date must be in YYYY-MM-DD format."}, status=status.HTTP_400_BAD_REQUEST
        )


def _can_see_margins(request) -> bool:
    from core.permissions import CanViewMargins

    return CanViewMargins().has_permission(request, None)


def _audit(request, action, entity_type, entity_id, **meta):
    from core.services.audit import AuditService

    cu = get_company_user(request)
    AuditService.log(
        action=action, company=cu.company, user=request.user, entity_type=entity_type,
        entity_id=entity_id, description=action.replace(".", " "), metadata=meta,
    )


class DailySummaryView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewAiInsights]

    def get(self, request):
        company = get_company_user(request).company
        for_date, err = _parse_date_param(request.query_params.get("date"))
        if err is not None:
            return err
        today = timezone.localdate()
        # R-044: GET reads the last snapshot and must not insert/write.
        qs = DailyBusinessSummary.objects.filter(company=company)
        if for_date is not None:
            existing = qs.filter(summary_date=for_date).first()
        else:
            existing = qs.filter(summary_date=today).first() or qs.order_by("-summary_date").first()
        if existing is None:
            return Response({
                "id": None,
                "summary_date": (for_date or today).isoformat(),
                "kpis": {},
                "alert_codes": [],
                "narrative": "",
                "prompt_version": "",
                "email_sent_at": None,
                "created_at": None,
                "generated_at": None,
                "stale": True,
                "can_generate": get_company_user(request).role == "OWNER",
            })
        data = dict(DailyBusinessSummarySerializer(existing).data)
        data["generated_at"] = existing.updated_at.isoformat() if existing.updated_at else None
        data["stale"] = existing.summary_date < today
        data["can_generate"] = get_company_user(request).role == "OWNER"
        return Response(data)

    def post(self, request):
        """Owner: rebuild the summary and alerts. Sends nothing unless ``send`` is true."""
        cu = get_company_user(request)
        if cu.role != "OWNER":
            return Response({"detail": "Owner required."}, status=status.HTTP_403_FORBIDDEN)
        for_date, err = _parse_date_param(request.data.get("date") or request.query_params.get("date"))
        if err is not None:
            return err
        send = str(request.data.get("send") or "").lower() in {"1", "true", "yes"}
        obj = generate_daily_summary(cu.company, for_date=for_date, send_email=send)
        _audit(
            request, "insights.summary.digest_sent" if send else "insights.summary.generated",
            "DailyBusinessSummary", obj.id, summary_date=obj.summary_date.isoformat(),
        )
        data = dict(DailyBusinessSummarySerializer(obj).data)
        data["generated_at"] = obj.updated_at.isoformat() if obj.updated_at else None
        data["stale"] = obj.summary_date < timezone.localdate()
        data["can_generate"] = True
        return Response(data)


class BusinessAlertViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, HasCompany, CanViewAiInsights]
    serializer_class = BusinessAlertEventSerializer

    def get_queryset(self):
        from django.db.models import Case, IntegerField, Value, When

        company = get_company_user(self.request).company
        now = timezone.now()
        qs = BusinessAlertEvent.objects.filter(company=company)
        status_f = (self.request.query_params.get("status") or "").upper()
        if status_f == BusinessAlertEvent.Status.SNOOZED:
            qs = qs.filter(status=BusinessAlertEvent.Status.SNOOZED, snoozed_until__gt=now)
        elif status_f:
            qs = qs.filter(status=status_f)
        else:
            # INP-15: a snooze that has run out counts as open again without waiting for the nightly job.
            qs = qs.filter(
                Q(status=BusinessAlertEvent.Status.OPEN)
                | Q(status=BusinessAlertEvent.Status.SNOOZED, snoozed_until__lte=now)
            )
        severity = self.request.query_params.get("severity")
        if severity:
            qs = qs.filter(severity=severity)
        if not _can_see_margins(self.request):
            from .services import MARGIN_ALERT_CODES

            qs = qs.exclude(code__in=MARGIN_ALERT_CODES)
        # INP-04: most severe first, then newest.
        rank = Case(
            When(severity=BusinessAlertEvent.Severity.CRITICAL, then=Value(0)),
            When(severity=BusinessAlertEvent.Severity.WARNING, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
        return qs.select_related("snoozed_by").annotate(_sev_rank=rank).order_by("_sev_rank", "-created_at", "-id")

    def refresh(self, request):
        cu = get_company_user(request)
        if cu.role != "OWNER":
            return Response({"detail": "Owner required."}, status=status.HTTP_403_FORBIDDEN)
        results = upsert_alerts(cu.company)
        open_rows = [a for a in results if a.status == BusinessAlertEvent.Status.OPEN]
        _audit(request, "insights.alerts.refreshed", "Company", cu.company_id, open=len(open_rows))
        return Response(BusinessAlertEventSerializer(open_rows, many=True).data)

    def _get_alert(self, request, pk):
        company = get_company_user(request).company
        return BusinessAlertEvent.objects.filter(pk=pk, company=company).first()

    def snooze(self, request, pk=None):
        alert = self._get_alert(request, pk)
        if alert is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            days = int(request.data.get("days") or 7)
        except (TypeError, ValueError):
            return Response({"detail": "days must be a whole number."}, status=status.HTTP_400_BAD_REQUEST)
        days = max(1, min(days, 90))
        if alert.status == BusinessAlertEvent.Status.RESOLVED:
            return Response(
                {"detail": "This alert is already resolved."}, status=status.HTTP_400_BAD_REQUEST
            )
        now = timezone.now()
        alert.status = BusinessAlertEvent.Status.SNOOZED
        alert.snoozed_until = now + timedelta(days=days)
        alert.snoozed_by = request.user
        alert.snoozed_at = now
        alert.save(update_fields=["status", "snoozed_until", "snoozed_by", "snoozed_at", "updated_at"])
        _audit(request, "insights.alert.snoozed", "BusinessAlertEvent", alert.id, code=alert.code, days=days)
        return Response(BusinessAlertEventSerializer(alert).data)

    def unsnooze(self, request, pk=None):
        alert = self._get_alert(request, pk)
        if alert is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if alert.status != BusinessAlertEvent.Status.SNOOZED:
            return Response({"detail": "This alert is not snoozed."}, status=status.HTTP_400_BAD_REQUEST)
        alert.status = BusinessAlertEvent.Status.OPEN
        alert.snoozed_until = None
        alert.snoozed_by = None
        alert.snoozed_at = None
        alert.save(update_fields=["status", "snoozed_until", "snoozed_by", "snoozed_at", "updated_at"])
        _audit(request, "insights.alert.unsnoozed", "BusinessAlertEvent", alert.id, code=alert.code)
        return Response(BusinessAlertEventSerializer(alert).data)


class HealthScoreView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]  # deterministic score, no AI

    def get(self, request):
        company = get_company_user(request).company
        data = compute_health_score(company, include_margin=_can_see_margins(request))
        data["score"] = str(data["score"])
        return Response(data)


class HealthHistoryView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]  # deterministic score, no AI

    def get(self, request):
        company = get_company_user(request).company
        # R-044: GET reads last snapshots; scheduled tasks persist new ones.
        qs = BusinessHealthSnapshot.objects.filter(company=company).order_by("-as_of")[:90]
        rows = BusinessHealthSnapshotSerializer(qs, many=True).data
        if not _can_see_margins(request):
            for row in rows:
                row["factors"] = [f for f in (row.get("factors") or []) if f.get("key") != "margin"]
        return Response(rows)


class CashflowForecastView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewAiInsights]

    def get(self, request):
        company = get_company_user(request).company
        raw = request.query_params.get("horizon") or "14"
        try:
            horizon = int(raw)
        except (TypeError, ValueError):
            return Response({"detail": "horizon must be 7, 14, 30 or 90."}, status=status.HTTP_400_BAD_REQUEST)
        if horizon not in (7, 14, 30, 90):
            return Response({"detail": "horizon must be 7, 14, 30 or 90."}, status=status.HTTP_400_BAD_REQUEST)
        data = forecast_cashflow(company, horizon=horizon)
        return Response(data)


class GrowthHintsView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewAiInsights]

    def get(self, request):
        company = get_company_user(request).company
        return Response({"hints": build_growth_hints(company, include_margin=_can_see_margins(request))})


class AssistantThreadViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, HasCompany, CanUseAiAssistant]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        # INP-02 (D4): chats are private to the person who started them.
        return AssistantThread.objects.filter(
            company=get_company_user(self.request).company, created_by=self.request.user,
        )

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
            thread = AssistantThread.objects.get(pk=thread_id, company=cu.company, created_by=request.user)
        except AssistantThread.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        content = (request.data.get("content") or "").strip()
        if not content:
            return Response({"detail": "content required"}, status=status.HTTP_400_BAD_REQUEST)
        hint = None
        if request.data.get("customer_id") or request.data.get("customerId"):
            hint = {
                "action": request.data.get("action"),
                "customer_id": request.data.get("customer_id") or request.data.get("customerId"),
            }
        try:
            msg = run_assistant_turn(cu.company, request.user, thread, content, cu=cu, hint=hint)
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        # First message names the chat so the thread list is readable.
        if thread.title in ("", "Chat"):
            thread.title = content[:60]
            thread.save(update_fields=["title", "updated_at"])
        return Response(AssistantMessageSerializer(msg).data, status=status.HTTP_201_CREATED)


class AssistantConfirmActionView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanUseAiAssistant]

    def post(self, request):
        cu = get_company_user(request)
        message_id = request.data.get("message_id") or request.data.get("messageId")
        if not message_id:
            return Response(
                {"detail": "message_id required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = confirm_proposed_action(cu.company, request.user, int(message_id), cu=cu)
        except (BusinessRuleError, TypeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class AssistantDismissActionView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanUseAiAssistant]

    def post(self, request):
        cu = get_company_user(request)
        message_id = request.data.get("message_id") or request.data.get("messageId")
        if not message_id:
            return Response(
                {"detail": "message_id required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = dismiss_proposed_action(cu.company, int(message_id), user=request.user)
        except (BusinessRuleError, TypeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class AiConsentView(APIView):
    """D12: the owner switches AI features (Insights, Assistant, bill scan) on or off for the company.

    Dedicated endpoint, because the company PATCH keeps ``ai_features_enabled`` read-only. Every
    change is written to the audit log.
    """

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        company = get_company_user(request).company
        return Response({"enabled": bool(company.ai_features_enabled)})

    def post(self, request):
        cu = get_company_user(request)
        raw = request.data.get("enabled")
        if isinstance(raw, str) and raw.strip().lower() in {"true", "false"}:
            raw = raw.strip().lower() == "true"
        if not isinstance(raw, bool):
            return Response({"detail": "enabled must be true or false."}, status=status.HTTP_400_BAD_REQUEST)
        company = cu.company
        before = bool(company.ai_features_enabled)
        if before != raw:
            company.ai_features_enabled = raw
            company.save(update_fields=["ai_features_enabled", "updated_at"])
            _audit(
                request, "company.ai_consent.enabled" if raw else "company.ai_consent.disabled",
                "Company", company.id, before=before, after=raw,
            )
        return Response({"enabled": raw})


class AttentionFeedView(APIView):
    """B-05: ranked AttentionRow feed. Not AI-gated — capability-filtered.

    Query: status=open|snoozed|dismissed, severity, category, assigned=mine|unassigned,
    limit, offset. ``mine=1`` is kept for older clients.
    """

    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request):
        from insights.attention import build_attention_feed, list_set_aside_rows

        cu = get_company_user(request)
        params = request.query_params
        status_filter = str(params.get("status") or "open").lower()
        if status_filter in {"snoozed", "dismissed"}:
            rows = list_set_aside_rows(cu.company, company_user=cu, status=status_filter)
            return Response({"rows": rows, "count": len(rows)})
        assigned = str(params.get("assigned") or "").lower()
        if not assigned and str(params.get("mine") or "").lower() in {"1", "true", "yes"}:
            assigned = "mine"
        try:
            limit = int(params.get("limit") or 25)
            offset = int(params.get("offset") or 0)
        except (TypeError, ValueError):
            return Response({"detail": "limit and offset must be numbers."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            build_attention_feed(
                cu.company,
                cu,
                severity=str(params.get("severity") or "").lower(),
                category=str(params.get("category") or "").lower(),
                assigned=assigned,
                limit=limit,
                offset=offset,
            )
        )


class AttentionReopenView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def post(self, request):
        from insights.attention import reopen_attention_row

        cu = get_company_user(request)
        dedupe_key = (request.data.get("dedupe_key") or request.data.get("dedupeKey") or "").strip()
        try:
            return Response(reopen_attention_row(cu.company, cu, dedupe_key=dedupe_key))
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class AttentionSeenView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def post(self, request):
        from insights.attention import mark_attention_seen

        return Response(mark_attention_seen(get_company_user(request)))


class AttentionDismissView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def post(self, request):
        cu = get_company_user(request)
        dedupe_key = (request.data.get("dedupe_key") or request.data.get("dedupeKey") or "").strip()
        if not dedupe_key:
            return Response({"detail": "dedupe_key required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = dismiss_attention_row(
                cu.company, cu, dedupe_key=dedupe_key, reason=str(request.data.get("reason") or "")
            )
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class LearningReportView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request):
        from insights.outcomes import learning_report

        cu = get_company_user(request)
        return Response(learning_report(cu.company))


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
        from insights.attention import _UNSET, assign_attention_row

        cu = get_company_user(request)
        dedupe_key = (request.data.get("dedupe_key") or request.data.get("dedupeKey") or "").strip()

        def _provided(*keys):
            # Distinguish "the client didn't send this field" (leave it
            # alone) from "the client sent it as null" (clear it) — a
            # plain .get() collapses both to None before it ever reaches
            # assign_attention_row, defeating its partial-update contract.
            for key in keys:
                if key in request.data:
                    return request.data.get(key)
            return _UNSET

        try:
            result = assign_attention_row(
                cu.company,
                cu,
                dedupe_key=dedupe_key,
                assignee_id=_provided("assigned_to", "assignedTo"),
                due_date=_provided("due_date", "dueDate"),
            )
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({"detail": str(exc) or "Invalid assigned_to or due_date."}, status=status.HTTP_400_BAD_REQUEST)
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


class CollectionsOpenInvoicesView(APIView):
    """Open invoices with days overdue, amount received, and invoice outstanding.

    This does not require ENABLE_PREDICTIVE_DUNNING and does not add a risk score.
    """

    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request):
        from payments.collections_open import open_invoice_rows

        company = get_company_user(request).company
        rows = open_invoice_rows(company)
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
    "form_abandoned",
    "draft_restored",
    "document_voided",
    "form_validation_failed",
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
_FEATURE_ALLOWLIST = _JOURNEY_ALLOWLIST | {"pos", "offline", "form"}
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
