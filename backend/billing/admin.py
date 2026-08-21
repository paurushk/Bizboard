from django.contrib import admin

from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "seat_limit", "price_paise", "is_active")
    search_fields = ("name", "slug")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("company", "plan", "status", "trial_ends_at", "razorpay_subscription_id")
    list_filter = ("status",)
    search_fields = ("razorpay_subscription_id",)
