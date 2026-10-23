from rest_framework import serializers

from .models import Plan, PlatformGstInvoice, SaasTdsClaim, Subscription


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = (
            "id",
            "name",
            "slug",
            "seat_limit",
            "monthly_complete_limit",
            "storage_bytes_limit",
            "api_rate_per_minute",
            "modules",
            "price_paise",
            "razorpay_plan_id",
            "is_active",
        )


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    plan_id = serializers.IntegerField(source="plan.id", read_only=True)
    write_blocked = serializers.SerializerMethodField()
    pending_plan_name = serializers.CharField(source="pending_plan.name", read_only=True, default="")
    upgrade_plan_name = serializers.CharField(source="upgrade_plan.name", read_only=True, default="")
    # WP-BL3: the unpaid prorated charge's link, so the Billing page can offer it again after a reload.
    proration_link_url = serializers.SerializerMethodField()

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
            "churn_reason",
            "suspended_at",
            "last_dunning_step",
            "pending_plan_name",
            "upgrade_plan_name",
            "upgrade_grace_until",
            "proration_amount_paise",
            "proration_paid_at",
            "proration_link_url",
            "payment_method",
            "mandate_status",
        )

    def get_proration_link_url(self, obj) -> str:
        if obj.upgrade_plan_id and obj.proration_paid_at is None:
            return obj.proration_link_url or ""
        return ""

    def get_write_blocked(self, obj) -> bool:
        company = obj.company
        if getattr(company, "billing_override_active", False):
            return False
        return obj.is_write_blocked()


class PlatformGstInvoiceSerializer(serializers.ModelSerializer):
    """WP-BL2: Bizboard's GST invoices and credit notes to this company (owner billing screen)."""

    original_number = serializers.CharField(source="original.number", default="", read_only=True)

    class Meta:
        model = PlatformGstInvoice
        fields = [
            "id", "kind", "number", "financial_year", "original_number", "created_at",
            "buyer_gstin", "buyer_legal_name", "buyer_state", "place_of_supply", "sac_code",
            "platform_gstin", "taxable_amount", "cgst", "sgst", "igst", "total",
        ]
        read_only_fields = fields


class SaasTdsClaimSerializer(serializers.ModelSerializer):
    """WP-BL1: the owner's TDS claims on Bizboard's invoices."""

    invoice_numbers = serializers.SerializerMethodField()

    class Meta:
        model = SaasTdsClaim
        fields = [
            "id", "status", "section", "rate", "taxable_total", "amount", "quarter",
            "invoice_numbers", "review_note", "created_at", "settle_by", "credit_remaining",
        ]
        read_only_fields = fields

    def get_invoice_numbers(self, obj):
        return [inv.number for inv in obj.invoices.all()]
