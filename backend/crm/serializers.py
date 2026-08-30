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
        fields = ["id", "lead", "customer", "title", "amount", "stage", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]
