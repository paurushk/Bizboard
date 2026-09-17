from django.contrib import admin

from core.admin import SuperuserOnlyAdminMixin

from .models import DeadLetterEvent, Plan, Subscription


@admin.register(Plan)
class PlanAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "seat_limit", "price_paise", "is_active")
    search_fields = ("name", "slug")


@admin.register(Subscription)
class SubscriptionAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("company", "plan", "status", "trial_ends_at", "razorpay_subscription_id")
    list_filter = ("status",)
    search_fields = ("razorpay_subscription_id",)


@admin.register(DeadLetterEvent)
class DeadLetterEventAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """9.5 gap fix: parked webhook/recon failures had no admin surface at all,
    so an operator could only discover or replay one by calling the API by
    hand. Read-only here (replay stays an explicit owner action via the API/
    SPA) -- this is for engineering to see what's stuck and why."""

    list_display = ("provider", "event_id", "company", "status", "attempts", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("event_id", "error")
    readonly_fields = [f.name for f in DeadLetterEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
