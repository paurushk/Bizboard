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

    class Meta:
        model = Lead
        fields = [
            "id", "name", "phone", "email", "state", "gstin", "address", "status",
            "source", "message", "assigned_to", "dedupe_matched_customer",
            "dedupe_matched_lead", "dedupe_review", "dedupe_candidates",
            "customer", "campaign", "referral_code", "last_touched_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "created_at", "updated_at", "assigned_to", "dedupe_matched_customer",
            "dedupe_matched_lead", "dedupe_review", "dedupe_candidates", "referral_code",
            "last_touched_at",
        ]


class LeadActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadActivity
        fields = ["id", "kind", "body", "due_at", "reminded_at", "created_at", "created_by"]
        read_only_fields = ["id", "reminded_at", "created_at", "created_by"]


class OpportunitySerializer(serializers.ModelSerializer):
    lead = CompanyPrimaryKeyRelatedField(queryset=Lead.objects.all(), allow_null=True, required=False)
    customer = CompanyPrimaryKeyRelatedField(
        queryset=Customer.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Opportunity
        fields = [
            "id", "lead", "customer", "title", "amount", "probability",
            "expected_close_date", "competitor", "stage", "closed_at", "stage_move_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "closed_at", "stage_move_count"]

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
        if self.instance is not None and self.instance.lines.exists():
            raise serializers.ValidationError("Amount is derived from line items.")
        return value

    def validate(self, attrs):
        stage = attrs.get("stage", getattr(self.instance, "stage", None))
        if "customer" in attrs:
            customer = attrs.get("customer")
        else:
            customer = getattr(self.instance, "customer", None)
        if stage == Opportunity.Stage.WON and customer is None:
            raise serializers.ValidationError({"customer": "A won deal needs a customer."})
        return attrs

    def create(self, validated_data):
        stage = validated_data.get("stage")
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

    class Meta:
        model = OpportunityLine
        fields = ["id", "opportunity", "product", "description", "quantity", "unit_price", "created_at"]
        read_only_fields = ["id", "opportunity", "created_at"]


class ReferralCodeSerializer(serializers.ModelSerializer):
    referrer_customer = CompanyPrimaryKeyRelatedField(
        queryset=Customer.objects.all(), allow_null=True, required=False
    )
    referrer_user = CompanyPrimaryKeyRelatedField(
        queryset=CompanyUser.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = ReferralCode
        fields = [
            "id", "referrer_customer", "referrer_user", "code", "reward_type",
            "reward_value", "active", "created_at",
        ]
        read_only_fields = ["id", "code", "created_at"]


class ReferralRewardSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferralReward
        fields = [
            "id", "referral_code", "lead", "opportunity", "reward_amount",
            "reward_status", "rejection_reason", "paid_at", "credit_note", "created_at",
        ]
        read_only_fields = fields
