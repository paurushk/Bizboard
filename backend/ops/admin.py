import json

from django.contrib import admin
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html

from core.exceptions import CompanyRequired
from core.permissions import get_company_user
from core.services.health import compute_help_health

from .models import CoverageAuditRun
from .tasks import run_coverage_audit_task


@admin.register(CoverageAuditRun)
class CoverageAuditRunAdmin(admin.ModelAdmin):
    """Trigger + read a 'Coverage Copilot' run. Add a blank one (all fields
    optional/computed) to kick off a new LLM gap-analysis run; the change
    view auto-refreshes every 3s while it's still PENDING/RUNNING."""

    list_display = ["id", "status", "requested_by", "created_at", "updated_at"]
    list_filter = ["status"]
    fields = ["status", "result_pretty", "failure_reason", "requested_by", "created_at", "updated_at"]
    readonly_fields = ["status", "result_pretty", "failure_reason", "requested_by", "created_at", "updated_at"]
    change_form_template = "ops/coverage_audit_run_change_form.html"

    def save_model(self, request, obj, form, change):
        if change:
            return
        obj.requested_by = request.user
        super().save_model(request, obj, form, change)
        run_coverage_audit_task.delay(obj.pk)

    def result_pretty(self, obj):
        if not obj or not obj.result:
            return "—"
        return format_html("<pre style='white-space:pre-wrap'>{}</pre>", json.dumps(obj.result, indent=2))

    result_pretty.short_description = "Result"


def _health_view(request):
    # Reached only via admin.site.admin_view(), which already enforces
    # staff-login — no separate permission decorator needed here.
    staff_all = bool(request.user.is_staff) and request.GET.get("all") == "1"
    company = None
    if not staff_all:
        try:
            cu = get_company_user(request)
        except CompanyRequired:
            cu = None
        company = cu.company if cu is not None else None
    health = compute_help_health(company=company, staff_all=staff_all)
    rows = [
        ("Window", f"{health['window_days']} days"),
        ("Scope", health["scope"]),
        ("Opens", health["opens"]),
        ("Rated", health["rated"]),
        ("Resolution rate", health["resolution_rate"]),
        ("Escalation rate", health["escalation_rate"]),
        ("Repeat-query rate", health["repeat_query_rate"]),
        ("Time to resolution (s)", health["time_to_resolution_seconds"]),
        ("Open feedback tickets", health["feedback_open"]),
        ("Searches", health["search_count"]),
        ("Zero-result rate", health["zero_result_rate"]),
    ]
    return render(request, "ops/health.html", {"health": health, "rows": rows, "staff_all": staff_all})


_original_get_urls = admin.site.get_urls


def _get_urls():
    custom = [
        path("ops/health/", admin.site.admin_view(_health_view), name="ops_health"),
    ]
    return custom + _original_get_urls()


admin.site.get_urls = _get_urls
