from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from accounts.models import CompanyUser
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer, Product

from .models import Campaign, Lead, LeadActivity, Opportunity, OpportunityLine, ReferralCode, ReferralReward


class LeadSerializer(serializers.ModelSerializer):
    customer = CompanyPrimaryKeyRelatedField(
        queryset=Customer.objects.all(), allow_null=True, required=False
    )
    campaign = CompanyPrimaryKeyRelatedField(
        queryset=Campaign.objects.all(), allow_null=True, required=False
    )
    customer_name = serializers.CharField(source="customer.name", read_only=True, allow_null=True, default=None)
    campaign_name = serializers.CharField(source="campaign.name", read_only=True, allow_null=True, default=None)

    def validate_campaign(self, value):
        # A paused or completed campaign keeps its history; it does not take new leads.
        unchanged = self.instance is not None and self.instance.campaign_id == getattr(value, "id", None)
        if value is not None and not unchanged and value.status not in (
            Campaign.Status.DRAFT, Campaign.Status.ACTIVE,
        ):
            raise serializers.ValidationError(
                f"{value.name} is {value.get_status_display().lower()} and is not accepting new leads."
            )
        return value

    def validate_status(self, value):
        if value not in Lead.Status.values:
            raise serializers.ValidationError("Choose a valid status.")
        if (
            value == Lead.Status.QUALIFIED
            and (self.instance is None or self.instance.status != Lead.Status.QUALIFIED)
            and (self.instance is None or not self.instance.opportunities.exists())
        ):
            # Qualified means a deal exists; Convert creates it and sets this status.
            raise serializers.ValidationError("Convert the lead to a deal to mark it qualified.")
        return value

    def validate_source(self, value):
        from .pipeline import SOURCES

        if value and value not in SOURCES:
            raise serializers.ValidationError("Unknown lead source.")
        return value or None

    def validate_gstin(self, value):
        value = (value or "").strip().upper()
        if value:
            from core.validators import GSTIN_RE

            if not GSTIN_RE.match(value):
                raise serializers.ValidationError("Enter a valid 15-character GSTIN.")
        return value

    def validate(self, attrs):
        instance = self.instance
        new_status = attrs.get("status", getattr(instance, "status", None))
        closing = new_status == Lead.Status.LOST and (instance is None or instance.status != Lead.Status.LOST)
        if closing:
            reason = (attrs.get("lost_reason") or getattr(instance, "lost_reason", "") or "").strip()
            if reason not in Opportunity.LostReason.values:
                raise serializers.ValidationError({"lost_reason": "Say why the lead was lost."})
            note = attrs.get("lost_reason_note", getattr(instance, "lost_reason_note", ""))
            if reason == Opportunity.LostReason.OTHER and not (note or "").strip():
                raise serializers.ValidationError({"lost_reason_note": "Add a short note for Other."})
        elif "lost_reason" in attrs and attrs["lost_reason"] and attrs["lost_reason"] not in Opportunity.LostReason.values:
            raise serializers.ValidationError({"lost_reason": "Choose a valid reason."})
        return attrs

    def update(self, instance, validated_data):
        validated_data["last_touched_at"] = timezone.now()
        if validated_data.get("status") == Lead.Status.LOST:
            validated_data.setdefault("lost_reason", instance.lost_reason)
        elif validated_data.get("status") and validated_data["status"] != Lead.Status.LOST:
            validated_data["lost_reason"] = ""
            validated_data["lost_reason_note"] = ""
        return super().update(instance, validated_data)

    class Meta:
        model = Lead
        fields = [
            "id", "name", "phone", "email", "state", "gstin", "address", "status",
            "lost_reason", "lost_reason_note", "duplicate_of", "dedupe_decision",
            "source", "message", "assigned_to", "dedupe_matched_customer",
            "dedupe_matched_lead", "dedupe_review", "dedupe_candidates",
            "customer", "customer_name", "campaign", "campaign_name", "referral_code",
            "last_touched_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "created_at", "updated_at", "customer_name", "campaign_name", "assigned_to", "dedupe_matched_customer",
            "dedupe_matched_lead", "dedupe_review", "dedupe_candidates", "referral_code",
            "last_touched_at", "duplicate_of", "dedupe_decision",
        ]


class LeadActivitySerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    def get_created_by_name(self, obj) -> str:
        user = obj.created_by
        if user is None:
            return ""
        return getattr(user, "full_name", "") or getattr(user, "email", "") or ""

    class Meta:
        model = LeadActivity
        fields = [
            "id", "kind", "body", "due_at", "reminded_at", "created_at", "created_by", "created_by_name",
        ]
        read_only_fields = ["id", "reminded_at", "created_at", "created_by", "created_by_name"]


class OpportunitySerializer(serializers.ModelSerializer):
    lead = CompanyPrimaryKeyRelatedField(queryset=Lead.objects.all(), allow_null=True, required=False)
    customer = CompanyPrimaryKeyRelatedField(
        queryset=Customer.objects.all(), allow_null=True, required=False
    )
    lead_name = serializers.CharField(source="lead.name", read_only=True, allow_null=True, default=None)
    customer_name = serializers.CharField(source="customer.name", read_only=True, allow_null=True, default=None)

    class Meta:
        model = Opportunity
        fields = [
            "id", "lead", "lead_name", "customer", "customer_name", "title", "amount", "probability",
            "expected_close_date", "competitor", "stage", "closed_at", "stage_move_count",
            "lost_reason", "lost_reason_note", "reopened_at",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "created_at", "updated_at", "closed_at", "stage_move_count", "reopened_at",
            "lead_name", "customer_name",
        ]

    # A closed deal keeps its numbers and parties; only these fields may still change.
    CLOSED_EDITABLE = {"competitor", "stage", "lost_reason", "lost_reason_note"}

    def validate_stage(self, value):
        # B9-039: WON/LOST are terminal -- once closed, an opportunity's
        # stage cannot be changed again (no accidental reopen/flip).
        if self.instance is not None and self.instance.stage in (
            Opportunity.Stage.WON, Opportunity.Stage.LOST,
        ) and value != self.instance.stage:
            raise serializers.ValidationError(
                f"This opportunity is already {self.instance.get_stage_display()} and cannot change stage."
            )
        return value

    def validate_amount(self, value):
        # The edit form always sends the amount back; only a real change is refused.
        if (
            self.instance is not None
            and self.instance.lines.exists()
            and Decimal(value) != Decimal(self.instance.amount or 0)
        ):
            raise serializers.ValidationError("Amount is derived from line items.")
        return value

    def validate(self, attrs):
        instance = self.instance
        if instance is not None and instance.stage in (
            Opportunity.Stage.WON, Opportunity.Stage.LOST,
        ):
            for field, value in attrs.items():
                if field in self.CLOSED_EDITABLE:
                    continue
                if getattr(instance, field) != value:
                    raise serializers.ValidationError(
                        {field: "This deal is closed. Ask an owner or manager to reopen it before changing it."}
                    )
        stage = attrs.get("stage", getattr(self.instance, "stage", None))
        if stage == Opportunity.Stage.LOST and (instance is None or instance.stage != Opportunity.Stage.LOST):
            reason = attrs.get("lost_reason") or getattr(instance, "lost_reason", "")
            note = attrs.get("lost_reason_note", getattr(instance, "lost_reason_note", ""))
            if not reason:
                raise serializers.ValidationError({"lost_reason": "Say why the deal was lost."})
            if reason == Opportunity.LostReason.OTHER and not (note or "").strip():
                raise serializers.ValidationError({"lost_reason_note": "Add a short note for Other."})
        if "customer" in attrs:
            customer = attrs.get("customer")
        else:
            customer = getattr(self.instance, "customer", None)
        if stage == Opportunity.Stage.WON and customer is None:
            raise serializers.ValidationError({"customer": "A won deal needs a customer."})
        return attrs

    def create(self, validated_data):
        stage = validated_data.get("stage")
        if "probability" not in validated_data:
            validated_data["probability"] = Opportunity.STAGE_DEFAULT_PROBABILITY.get(
                stage or Opportunity.Stage.OPEN, 0,
            )
        if stage in (Opportunity.Stage.WON, Opportunity.Stage.LOST):
            validated_data["closed_at"] = timezone.now()
        instance = super().create(validated_data)
        if instance.stage == Opportunity.Stage.WON:
            from .referrals import evaluate_referral_reward

            evaluate_referral_reward(instance)
        return instance

    def update(self, instance, validated_data):
        new_stage = validated_data.get("stage")
        if new_stage and new_stage != instance.stage:
            validated_data["stage_move_count"] = (instance.stage_move_count or 0) + 1
            if "probability" not in validated_data:
                validated_data["probability"] = Opportunity.probability_after_move(
                    instance.probability, instance.stage, new_stage,
                )
        if (
            new_stage in (Opportunity.Stage.WON, Opportunity.Stage.LOST)
            and instance.stage != new_stage
        ):
            validated_data["closed_at"] = timezone.now()
        instance = super().update(instance, validated_data)
        if (
            new_stage == Opportunity.Stage.WON
            and instance.stage == Opportunity.Stage.WON
        ):
            from .referrals import evaluate_referral_reward

            evaluate_referral_reward(instance)
        return instance


class CampaignSerializer(serializers.ModelSerializer):
    parent = CompanyPrimaryKeyRelatedField(
        queryset=Campaign.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Campaign
        fields = [
            "id", "name", "campaign_type", "parent", "budget", "target_revenue",
            "expected_outcome", "start_date", "end_date", "status",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date cannot be before the start date."})
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        if parent is not None and self.instance is not None:
            seen = set()
            node = parent
            while node is not None:
                if node.pk == self.instance.pk:
                    raise serializers.ValidationError({"parent": "A campaign cannot be its own ancestor."})
                if node.pk in seen:
                    break
                seen.add(node.pk)
                node = node.parent
        return attrs


class OpportunityLineSerializer(serializers.ModelSerializer):
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = OpportunityLine
        fields = [
            "id", "opportunity", "product", "product_name", "description", "quantity", "unit_price",
            "created_at",
        ]
        read_only_fields = ["id", "opportunity", "product_name", "created_at"]


class ReferralCodeSerializer(serializers.ModelSerializer):
    referrer_customer = CompanyPrimaryKeyRelatedField(
        queryset=Customer.objects.all(), allow_null=True, required=False
    )
    referrer_user = CompanyPrimaryKeyRelatedField(
        queryset=CompanyUser.objects.all(), allow_null=True, required=False
    )
    referrer_name = serializers.SerializerMethodField()
    uses = serializers.IntegerField(source="lead_count", read_only=True, default=0)
    rewards_earned = serializers.IntegerField(source="reward_count", read_only=True, default=0)

    def get_referrer_name(self, obj) -> str:
        if obj.referrer_customer_id:
            return obj.referrer_customer.name
        member = obj.referrer_user
        user = getattr(member, "user", None)
        return (getattr(user, "get_full_name", lambda: "")() or getattr(user, "email", "")) if user else ""

    class Meta:
        model = ReferralCode
        fields = [
            "id", "referrer_customer", "referrer_user", "referrer_name", "code", "reward_type",
            "reward_value", "active", "deactivated_at", "uses", "rewards_earned", "created_at",
        ]
        read_only_fields = [
            "id", "code", "created_at", "referrer_name", "deactivated_at", "uses", "rewards_earned",
        ]


class ReferralRewardSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source="lead.name", read_only=True)
    customer_name = serializers.SerializerMethodField()
    referrer_name = serializers.SerializerMethodField()
    code = serializers.CharField(source="referral_code.code", read_only=True)
    opportunity_title = serializers.CharField(source="opportunity.title", read_only=True)

    def get_customer_name(self, obj) -> str:
        customer = obj.opportunity.customer
        return customer.name if customer is not None else ""

    def get_referrer_name(self, obj) -> str:
        code = obj.referral_code
        if code.referrer_customer_id:
            return code.referrer_customer.name
        user = getattr(code.referrer_user, "user", None)
        return (getattr(user, "get_full_name", lambda: "")() or getattr(user, "email", "")) if user else ""

    class Meta:
        model = ReferralReward
        fields = [
            "id", "referral_code", "code", "lead", "lead_name", "opportunity", "opportunity_title",
            "customer_name", "referrer_name", "reward_amount", "basis", "review_note",
            "reward_status", "rejection_reason", "paid_at", "credit_note", "created_at",
        ]
        read_only_fields = fields
