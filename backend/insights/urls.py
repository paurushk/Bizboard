from django.urls import path

from .views import (
    AiUsageView,
    AssistantConfirmActionView,
    AssistantDismissActionView,
    AssistantMessageCreateView,
    AssistantThreadViewSet,
    AttentionFeedView,
    AttentionSnoozeView,
    BusinessAlertViewSet,
    CashflowForecastView,
    DailySummaryView,
    GrowthHintsView,
    HealthHistoryView,
    HealthScoreView,
    ShopFloorTelemetryView,
)
alert_list = BusinessAlertViewSet.as_view({"get": "list"})
alert_snooze = BusinessAlertViewSet.as_view({"post": "snooze"})
alert_refresh = BusinessAlertViewSet.as_view({"post": "refresh"})
thread_list = AssistantThreadViewSet.as_view({"get": "list", "post": "create"})
thread_detail = AssistantThreadViewSet.as_view({"get": "retrieve"})

urlpatterns = [
    path("daily-summary/", DailySummaryView.as_view(), name="insights-daily-summary"),
    path("alerts/", alert_list, name="insights-alerts"),
    path("alerts/refresh/", alert_refresh, name="insights-alerts-refresh"),
    path("alerts/<int:pk>/snooze/", alert_snooze, name="insights-alert-snooze"),
    path("health/", HealthScoreView.as_view(), name="insights-health"),
    path("health/history/", HealthHistoryView.as_view(), name="insights-health-history"),
    path("cashflow-forecast/", CashflowForecastView.as_view(), name="insights-cashflow"),
    path("growth-hints/", GrowthHintsView.as_view(), name="insights-hints"),
    path("attention/", AttentionFeedView.as_view(), name="insights-attention"),
    path("attention/snooze/", AttentionSnoozeView.as_view(), name="insights-attention-snooze"),
    path("assistant/threads/", thread_list, name="insights-threads"),
    path("assistant/threads/<int:pk>/", thread_detail, name="insights-thread-detail"),
    path(
        "assistant/threads/<int:thread_id>/messages/",
        AssistantMessageCreateView.as_view(),
        name="insights-thread-messages",
    ),
    path(
        "assistant/actions/confirm/",
        AssistantConfirmActionView.as_view(),
        name="insights-assistant-confirm",
    ),
    path(
        "assistant/actions/dismiss/",
        AssistantDismissActionView.as_view(),
        name="insights-assistant-dismiss",
    ),
    path("usage/", AiUsageView.as_view(), name="insights-usage"),
    path("telemetry/", ShopFloorTelemetryView.as_view(), name="insights-telemetry"),
]
