from datetime import timedelta

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
    snapshot_health,
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
        existing = DailyBusinessSummary.objects.filter(
            company=company, summary_date=for_date
        ).first()
        # GET is cached for the date. Regenerate only when missing or empty (stale).
        # Owner POST below force-generates.
        if existing is None or not existing.kpis:
            obj = generate_daily_summary(company, for_date=for_date)
        else:
            obj = existing
        return Response(DailyBusinessSummarySerializer(obj).data)

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
        # Ensure today's snapshot exists
        snapshot_health(company)
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

    def perform_create(self, serializer):
        cu = get_company_user(self.request)
        serializer.save(company=cu.company, created_by=self.request.user, title=serializer.validated_data.get("title") or "Chat")

    def create(self, request, *args, **kwargs):
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
}
_TELEMETRY_PII_KEYS = {
    "gstin", "phone", "email", "name", "customer", "customer_name", "customerName",
    "description", "address", "pan", "line_description", "lineDescription",
}


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, int(round((p / 100) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


class ShopFloorTelemetryView(APIView):
    """A-08: POST events (no PII); GET 7-day owner summary."""

    permission_classes = [IsAuthenticated, HasCompany]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return [IsAuthenticated(), HasCompany()]

    def post(self, request):
        from .models import ShopFloorEvent

        payload = request.data if isinstance(request.data, dict) else {}
        for key in payload:
            if str(key).lower() in _TELEMETRY_PII_KEYS:
                raise BusinessRuleError("Telemetry must not include personal data.")
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
        cu = get_company_user(request)
        ShopFloorEvent.objects.create(
            company=cu.company,
            event=event,
            duration_ms=duration_ms,
            tap_count=tap_count,
            occurred_on=timezone.localdate(),
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
        return Response({
            "days": days,
            "complete_p95_ms": _percentile(durations, 95),
            "complete_count": qs.filter(event="invoice_complete").count(),
            "offline_flush_fail": qs.filter(event="offline_flush_fail").count(),
            "offline_enqueue": qs.filter(event="offline_enqueue").count(),
            "pos_line_added": qs.filter(event="pos_line_added").count(),
        })
