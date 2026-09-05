from django.utils import timezone
from rest_framework import serializers

from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer

from .models import Lead, LeadActivity, Opportunity


class LeadSerializer(serializers.ModelSerializer):
    customer = CompanyPrimaryKeyRelatedField(
        queryset=Customer.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Lead
        fields = ["id", "name", "phone", "email", "state", "gstin", "address", "status", "customer", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class LeadActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadActivity
        fields = ["id", "kind", "body", "created_at", "created_by"]
        read_only_fields = ["id", "created_at", "created_by"]


class OpportunitySerializer(serializers.ModelSerializer):
    lead = CompanyPrimaryKeyRelatedField(queryset=Lead.objects.all(), allow_null=True, required=False)
    customer = CompanyPrimaryKeyRelatedField(
        queryset=Customer.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Opportunity
        fields = ["id", "lead", "customer", "title", "amount", "stage", "closed_at", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at", "closed_at"]

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

    def update(self, instance, validated_data):
        new_stage = validated_data.get("stage")
        if (
            new_stage in (Opportunity.Stage.WON, Opportunity.Stage.LOST)
            and instance.stage != new_stage
        ):
            validated_data["closed_at"] = timezone.now()
        return super().update(instance, validated_data)
