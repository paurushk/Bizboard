from rest_framework import serializers

from accounts.models import CompanyUser
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer

from .models import Ticket, TicketComment, VendorTicketShare
from django.utils import timezone

from .tickets import SLA_OFFSETS, effective_sla_due_at


class TicketSerializer(serializers.ModelSerializer):
    customer = CompanyPrimaryKeyRelatedField(queryset=Customer.objects.all())
    assigned_to = CompanyPrimaryKeyRelatedField(
        queryset=CompanyUser.objects.all(), allow_null=True, required=False
    )
    assignee_name = serializers.SerializerMethodField()

    def get_assignee_name(self, obj):
        member = getattr(obj, "assigned_to", None)
        user = getattr(member, "user", None)
        if user is None:
            return ""
        return (getattr(user, "full_name", "") or getattr(user, "email", "") or "").strip()

    class Meta:
        model = Ticket
        fields = [
            "id", "number", "customer", "subject", "description", "priority", "status",
            "assigned_to", "assignee_name", "sla_due_at", "waiting_since", "resolved_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "status", "sla_due_at", "waiting_since", "resolved_at", "created_at", "updated_at",
        ]

    def update(self, instance, validated_data):
        previous = instance.priority
        row = super().update(instance, validated_data)
        if row.priority != previous and row.priority in SLA_OFFSETS:
            base = row.created_at or timezone.now()
            row.sla_due_at = base + SLA_OFFSETS[row.priority]
            row.save(update_fields=["sla_due_at", "updated_at"])
        return row

    def to_representation(self, instance):
        original = instance.sla_due_at
        instance.sla_due_at = effective_sla_due_at(instance)
        try:
            return super().to_representation(instance)
        finally:
            instance.sla_due_at = original


class VendorTicketShareSerializer(serializers.ModelSerializer):
    source_company_name = serializers.CharField(source="source_company.name", read_only=True)

    class Meta:
        model = VendorTicketShare
        fields = [
            "id", "source_company_name", "source_number", "subject", "status",
            "description", "shared_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not instance.description:
            data.pop("description", None)
        return data


class TicketCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketComment
        fields = ["id", "body", "is_internal", "created_by", "created_at"]
        read_only_fields = ["id", "created_by", "created_at"]
