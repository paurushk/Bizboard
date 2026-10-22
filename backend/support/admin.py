"""Bizboard staff surfaces for support (Django admin, superuser only)."""

from django.contrib import admin
from django.utils import timezone

from core.admin import SuperuserOnlyAdminMixin

from .models import (
    DataPrivacyRequest,
    PlatformTicket,
    PlatformTicketMessage,
    SupportAccessGrant,
    SupportAccessLog,
    TenantHealthSnapshot,
)


class _BypassMixin:
    """Tenant rows are row-level secured; staff lists read across companies."""

    def get_queryset(self, request):
        from core.rls import rls_bypass

        with rls_bypass():
            return super().get_queryset(request)

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


class PlatformTicketMessageInline(admin.TabularInline):
    model = PlatformTicketMessage
    fields = ("created_at", "author", "from_staff", "body")
    readonly_fields = ("created_at", "author", "from_staff")
    extra = 1

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PlatformTicket)
class PlatformTicketAdmin(_BypassMixin, SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """WP-PO3: the support queue. A reply typed in the inline is emailed to the person who raised it."""

    list_display = ("id", "severity", "status", "subject", "company", "raised_by", "sla_due_at", "overdue")
    list_filter = ("status", "severity", "tag")
    search_fields = ("subject", "support_id", "company__name", "raised_by__email")
    readonly_fields = ("company", "raised_by", "support_id", "route", "app_version", "error_codes",
                       "sla_due_at", "first_response_at", "resolved_at", "created_at")
    fields = ("company", "raised_by", "subject", "description", "severity", "tag", "status", "assignee",
              "support_id", "route", "app_version", "error_codes", "sla_due_at", "first_response_at",
              "resolved_at", "created_at")
    inlines = [PlatformTicketMessageInline]
    list_select_related = ("company", "raised_by")

    @admin.display(boolean=True, description="Overdue")
    def overdue(self, obj):
        return bool(
            obj.sla_due_at and obj.status != PlatformTicket.Status.RESOLVED
            and obj.first_response_at is None and obj.sla_due_at < timezone.now()
        )

    def has_add_permission(self, request):
        return False

    def save_formset(self, request, form, formset, change):
        from .platform_tickets import add_message

        for inline_form in formset.forms:
            if not inline_form.has_changed() or inline_form.instance.pk:
                continue
            body = inline_form.cleaned_data.get("body")
            if body:
                add_message(form.instance, author=request.user, body=body, from_staff=True)
        formset.save_m2m = lambda: None


@admin.register(TenantHealthSnapshot)
class TenantHealthSnapshotAdmin(_BypassMixin, SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """WP-PO2: weekly health per company, worst first. Month view: manage.py saas_metrics."""

    list_display = ("company", "week", "score", "band")
    list_filter = ("band", "week")
    search_fields = ("company__name",)
    readonly_fields = ("company", "week", "score", "band", "inputs")
    list_select_related = ("company",)

    def has_add_permission(self, request):
        return False


@admin.register(DataPrivacyRequest)
class DataPrivacyRequestAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """WP-CP2: privacy requests and their due dates (docs/ops/DPDP_REQUESTS.md)."""

    list_display = ("id", "kind", "requester", "company_id_hint", "received_at", "due_at", "closed_at", "overdue")
    list_filter = ("kind", "source")
    search_fields = ("requester",)
    readonly_fields = ("received_at", "source")

    @admin.display(boolean=True, description="Overdue")
    def overdue(self, obj):
        return obj.closed_at is None and obj.due_at < timezone.now()

    def save_model(self, request, obj, form, change):
        from .privacy import default_due

        if not obj.due_at:
            obj.due_at = default_due()
        if obj.handled_by_id is None:
            obj.handled_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SupportAccessGrant)
class SupportAccessGrantAdmin(_BypassMixin, admin.ModelAdmin):
    """WP-ID4: grants owners gave support. Any active staff member may open a live grant meant for
    them (or for any support staff) in the read-only viewer; nobody can add or edit a grant here."""

    list_display = ("id", "company", "ticket", "staff_user", "expires_at", "revoked_at", "open_link")
    list_filter = ("revoke_reason",)
    search_fields = ("company__name",)
    readonly_fields = [f.name for f in SupportAccessGrant._meta.fields] + ["open_link"]

    def has_module_permission(self, request):
        return bool(request.user.is_active and request.user.is_staff)

    def has_view_permission(self, request, obj=None):
        return bool(request.user.is_active and request.user.is_staff)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Read-only view")
    def open_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html

        if obj.revoked_at is not None or obj.expires_at <= timezone.now():
            return "—"
        return format_html('<a href="{}">Open read-only</a>', reverse("admin:ops_support_view", args=[obj.pk]))


@admin.register(SupportAccessLog)
class SupportAccessLogAdmin(_BypassMixin, SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """WP-ID4: every page support looked at under a grant (the owner sees the same list in the app)."""

    list_display = ("created_at", "company", "grant", "staff_user", "section", "query", "rows_shown")
    list_filter = ("section",)
    readonly_fields = [f.name for f in SupportAccessLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
