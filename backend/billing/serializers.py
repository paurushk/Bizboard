from rest_framework import serializers

from .models import Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            "id",
            "name",
            "slug",
            "seat_limit",
            "modules",
            "price_paise",
            "razorpay_plan_id",
            "is_active",
        )


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    plan_id = serializers.IntegerField(source="plan.id", read_only=True)
    write_blocked = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = (
            "id",
            "status",
            "trial_ends_at",
            "razorpay_subscription_id",
            "current_period_end",
            "plan",
            "plan_id",
            "write_blocked",
        )

    def get_write_blocked(self, obj) -> bool:
        company = obj.company
        if getattr(company, "billing_override_active", False):
            return False
        return obj.is_write_blocked()
