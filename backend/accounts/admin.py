from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from core.admin import RlsBypassAdminMixin, SuperuserOnlyAdminMixin

from .models import Company, CompanyUser, OwnershipTransfer, User


class UserAdmin(DjangoUserAdmin):
    """Custom User has no username field — reuse Django's UserAdmin but avoid
    the default fieldsets referencing 'username' and expose the raw password
    only through the read-only hashed-value widget (never as a plain
    CharField, which silently stores whatever text is typed as the new
    'hash' — BUG-116)."""

    ordering = ["email"]
    list_display = ["email", "full_name", "phone", "is_active", "is_staff"]
    search_fields = ["email", "full_name", "phone"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("full_name", "phone")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


class TallyGrantedFilter(admin.SimpleListFilter):
    title = "Tally import granted"
    parameter_name = "tally"

    def lookups(self, request, model_admin):
        return (("yes", "Granted"), ("no", "Not granted"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(feature_flags__ENABLE_TALLY=True)
        if self.value() == "no":
            return queryset.exclude(feature_flags__ENABLE_TALLY=True)
        return queryset


class RolloutGrantForm(forms.Form):
    key = forms.ChoiceField(label="Flag")
    on = forms.TypedChoiceField(label="Set", choices=(("1", "On"), ("0", "Off")), coerce=lambda v: v == "1")
    reason = forms.CharField(min_length=5, max_length=500, widget=forms.Textarea(attrs={"rows": 2}))
    ticket = forms.CharField(required=False, max_length=64, label="Support ticket")

    def __init__(self, *args, **kwargs):
        from .rollout_grants import grantable_keys

        super().__init__(*args, **kwargs)
        self.fields["key"].choices = [(k, k) for k in grantable_keys()]


@admin.register(Company)
class CompanyAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("name", "gstin", "state", "tally_granted")
    search_fields = ("name", "gstin")
    list_filter = (TallyGrantedFilter,)
    actions = ["grant_rollout_flag"]

    @admin.display(boolean=True, description="Tally")
    def tally_granted(self, obj):
        return bool((obj.feature_flags or {}).get("ENABLE_TALLY"))

    @admin.action(description="Grant or revoke a rollout flag (e.g. Tally import for a pilot)")
    def grant_rollout_flag(self, request, queryset):
        """WP-GR1a: per-company rollout grant with a reason and a ticket, audited."""
        from django.template.response import TemplateResponse

        from .rollout_grants import set_flag

        if "apply" in request.POST:
            form = RolloutGrantForm(request.POST)
            if form.is_valid():
                d = form.cleaned_data
                for company in queryset:
                    try:
                        set_flag(company, key=d["key"], on=d["on"], staff_user=request.user,
                                 reason=d["reason"], ticket=d["ticket"])
                    except Exception as exc:  # noqa: BLE001 - report each company
                        self.message_user(request, f"{company.name}: {exc}", level="error")
                self.message_user(request, f"{d['key']} {'on' if d['on'] else 'off'} for {queryset.count()} company(ies).")
                return None
        else:
            form = RolloutGrantForm(initial={"key": "ENABLE_TALLY", "on": "1"})
        return TemplateResponse(request, "admin/rollout_grant.html", {
            **self.admin_site.each_context(request),
            "title": "Grant or revoke a rollout flag",
            "form": form,
            "companies": queryset,
            "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
        })


@admin.register(CompanyUser)
class CompanyUserAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("company", "user", "role")
    search_fields = ("user__email",)


admin.site.register(User, UserAdmin)


@admin.register(OwnershipTransfer)
class OwnershipTransferAdmin(RlsBypassAdminMixin, SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """WP-ID1: owner transfers and staff-assisted recoveries (docs/ops/OWNER_RECOVERY.md).

    Start a recovery with ``manage.py owner_recovery request``; a second staff member approves with
    the action below; current owners get 72 hours to cancel before the invite goes out.
    """

    list_display = ("company", "kind", "status", "recovery_email", "requested_by", "approved_by", "effective_at")
    list_filter = ("kind", "status")
    search_fields = ("company__name", "recovery_email")
    readonly_fields = [f.name for f in OwnershipTransfer._meta.fields if f.name != "id"]
    actions = ["approve_recovery_selected", "cancel_selected"]

    list_select_related = ("company", "requested_by", "approved_by")

    def has_add_permission(self, request):
        return False

    @admin.action(description="Approve recovery (second staff member)")
    def approve_recovery_selected(self, request, queryset):
        from core.rls import rls_bypass

        from .ownership import approve_recovery

        with rls_bypass():
            for transfer in queryset:
                try:
                    approve_recovery(transfer, staff_user=request.user)
                    self.message_user(request, f"{transfer.company}: approved; owners have 72 hours to cancel.")
                except Exception as exc:  # noqa: BLE001
                    self.message_user(request, f"{transfer.company}: {exc}", level="error")

    @admin.action(description="Cancel")
    def cancel_selected(self, request, queryset):
        from core.rls import rls_bypass

        from .ownership import cancel

        with rls_bypass():
            for transfer in queryset:
                try:
                    cancel(transfer, user=request.user, reason="Cancelled by staff")
                except Exception as exc:  # noqa: BLE001
                    self.message_user(request, f"{transfer.company}: {exc}", level="error")
