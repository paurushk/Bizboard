"""Ops view of bill imports (staff-only tooling lives in Django admin)."""

from django.contrib import admin

from . import metrics
from .models import ImportJob


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    # The health numbers sit above the usual list.
    change_list_template = "admin/imports/importjob/change_list.html"
    list_display = (
        "id", "company", "kind", "status", "total_rows", "valid_rows", "error_rows",
        "created_by", "created_at", "committed_at",
    )
    list_filter = ("kind", "status")
    search_fields = ("id", "company__name", "failure_reason", "file_sha256")
    readonly_fields = ("preview", "errors", "created_product_ids", "extraction_heartbeat_at")
    raw_id_fields = ("file", "supplier", "customer", "purchase_invoice", "sales_invoice", "bill_template")

    def changelist_view(self, request, extra_context=None):
        # The changelist rejects query parameters it does not know, so take ours out first.
        params = request.GET.copy()
        raw_days = params.pop("stats_days", ["30"])[0]
        request.GET = params
        try:
            days = max(1, min(int(raw_days), 365))
        except (TypeError, ValueError):
            days = 30
        extra_context = {**(extra_context or {}), "bill_stats": metrics.summary(days), "stats_days": days}
        return super().changelist_view(request, extra_context=extra_context)
