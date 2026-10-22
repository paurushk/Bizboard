"""Shared Django admin mixins."""

from django.contrib import admin


class SuperuserOnlyAdminMixin:
    """4.5 — money / tenant admin surfaces are superuser-only, not staff."""

    def has_module_permission(self, request):
        return bool(getattr(request.user, "is_superuser", False))

    def has_view_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_superuser", False))

    def has_add_permission(self, request):
        return bool(getattr(request.user, "is_superuser", False))

    def has_change_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_superuser", False))

    def has_delete_permission(self, request, obj=None):
        return bool(getattr(request.user, "is_superuser", False))


class SuperuserOnlyModelAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    pass


class RlsBypassReadOnlyAdmin(SuperuserOnlyModelAdmin):
    """Read-only, cross-tenant ops list. Rows are row-level secured, so the list and detail pages
    are rendered inside the RLS bypass (the response is rendered before the bypass ends)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        from core.rls import rls_bypass

        with rls_bypass():
            response = super().changelist_view(request, extra_context)
            if hasattr(response, "render"):
                response.render()
            return response

    def change_view(self, request, object_id, form_url="", extra_context=None):
        from core.rls import rls_bypass

        with rls_bypass():
            response = super().change_view(request, object_id, form_url, extra_context)
            if hasattr(response, "render"):
                response.render()
            return response


def _register_sweep_admin():
    from .models import TenantSweepResult

    @admin.register(TenantSweepResult)
    class TenantSweepResultAdmin(RlsBypassReadOnlyAdmin):
        """WP-D4: nightly books check per company. Repair steps: docs/ops/LEDGER_REPAIR_RUNBOOK.md."""

        list_display = ("company", "status", "full_sweep", "keys", "started_at", "duration_ms", "run_id")
        list_filter = ("status", "full_sweep")
        search_fields = ("company__name", "run_id")
        date_hierarchy = "started_at"
        list_select_related = ("company",)
        readonly_fields = [f.name for f in TenantSweepResult._meta.fields]

        @admin.display(description="Failing checks")
        def keys(self, obj):
            return ", ".join(obj.failing_keys or []) or obj.error or "-"


_register_sweep_admin()
