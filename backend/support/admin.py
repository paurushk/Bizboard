"""Bizboard staff surfaces for support (Django admin, superuser only)."""

from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from core.admin import RlsBypassAdminMixin, SuperuserOnlyAdminMixin

from .models import (
    DataPrivacyRequest,
    PlatformTicket,
    PlatformTicketMessage,
    SatisfactionResponse,
    SupportAccessGrant,
    SupportAccessLog,
    TenantHealthSnapshot,
)


# Tenant rows are row-level secured; staff lists read across companies.
_BypassMixin = RlsBypassAdminMixin


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
    readonly_fields = ("company", "raised_by", "support_id", "matching_errors", "route", "app_version",
                       "error_codes", "sla_due_at", "first_response_at", "resolved_at", "created_at")
    fields = ("company", "raised_by", "subject", "description", "severity", "tag", "status", "assignee",
              "support_id", "matching_errors", "route", "app_version", "error_codes", "sla_due_at",
              "first_response_at", "resolved_at", "created_at")
    inlines = [PlatformTicketMessageInline]
    list_select_related = ("company", "raised_by")

    @admin.display(boolean=True, description="Overdue")
    def overdue(self, obj):
        return bool(
            obj.sla_due_at and obj.status != PlatformTicket.Status.RESOLVED
            and obj.first_response_at is None and obj.sla_due_at < timezone.now()
        )

    @admin.display(description="Errors for this Support ID")
    def matching_errors(self, obj):
        """Every API and browser error is tagged with the request id people quote as the Support ID."""
        from core import error_tracker

        if not error_tracker.request_id_query(obj.support_id or ""):
            return "No Support ID on this ticket."
        links = [format_html('<a href="{}?q={}">Show in Bizboard</a>', reverse("admin:ops_errors"), obj.support_id)]
        tracker = error_tracker.request_id_url(obj.support_id)
        if tracker:
            links.append(format_html('<a href="{}" target="_blank" rel="noopener noreferrer">Open in tracker</a>', tracker))
        return format_html(" &middot; ".join(["{}"] * len(links)), *links)

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "status" in form.changed_data and obj.status == PlatformTicket.Status.RESOLVED:
            from .access import revoke_for_ticket

            if obj.resolved_at is None:
                obj.resolved_at = timezone.now()
                obj.save(update_fields=["resolved_at", "updated_at"])
            revoke_for_ticket(obj, user=request.user)  # closing the request ends support's access now

    def save_formset(self, request, form, formset, change):
        """A reply typed in the inline is sent through ``add_message`` (email + status), never saved
        as a bare row. ``formset.save(commit=False)`` still runs: Django's change message reads the
        formset's new/changed/deleted lists it fills."""
        from .platform_tickets import add_message

        instances = formset.save(commit=False)
        for message in instances:
            if message.pk or not (message.body or "").strip():
                continue
            add_message(form.instance, author=request.user, body=message.body, from_staff=True)
        if "status" in form.changed_data and form.cleaned_data.get("status"):
            # A status picked in the same submit (e.g. reply and resolve) wins over the reply's
            # automatic "waiting for customer".
            form.instance.status = form.cleaned_data["status"]
            form.instance.save(update_fields=["status", "updated_at"])
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

    def has_delete_permission(self, request, obj=None):
        return False  # the owner's record of every look support took


@admin.register(SatisfactionResponse)
class SatisfactionResponseAdmin(SuperuserOnlyAdminMixin, _BypassMixin, admin.ModelAdmin):
    """BB-136: NPS answers and support CSAT, across companies. The list header shows the NPS of
    the answered rows in the current filter (promoters 9-10 minus detractors 0-6)."""

    list_display = ("created_at", "company", "user", "kind", "score", "platform_ticket", "short_comment")
    list_filter = ("kind", "created_at")
    search_fields = ("comment", "company__name", "user__email")
    readonly_fields = ("company", "user", "kind", "score", "comment", "platform_ticket", "created_at")
    fields = readonly_fields

    @admin.display(description="Comment")
    def short_comment(self, obj):
        return (obj.comment or "")[:80]

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        from .satisfaction import nps_score_summary

        response = super().changelist_view(request, extra_context=extra_context)
        try:
            rows = response.context_data["cl"].queryset.filter(kind=SatisfactionResponse.Kind.NPS)
        except (AttributeError, KeyError):
            return response
        summary = nps_score_summary(rows)
        if summary["nps"] is not None:
            self.message_user(
                request,
                f"NPS {summary['nps']} from {summary['answered']} answers "
                f"({summary['promoters']} promoters, {summary['passives']} passives, {summary['detractors']} detractors).",
            )
        return response

