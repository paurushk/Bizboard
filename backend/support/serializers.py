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
    share_available = serializers.SerializerMethodField()

    def get_assignee_name(self, obj):
        member = getattr(obj, "assigned_to", None)
        user = getattr(member, "user", None)
        if user is None:
            return ""
        return (getattr(user, "full_name", "") or getattr(user, "email", "") or "").strip()

    def get_share_available(self, obj):
        from .share import vendor_company_id

        return vendor_company_id() is not None

    class Meta:
        model = Ticket
        fields = [
            "id", "number", "customer", "subject", "description", "category", "priority", "status",
            "assigned_to", "assignee_name", "share_available", "sla_due_at", "waiting_since",
            "resolved_at", "created_at", "updated_at",
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


def live_ticket_statuses(shares) -> dict:
    """{(source_company_id, source_ticket_id): status} for these share rows, in one query."""
    from collections import defaultdict

    from core.rls import rls_bypass

    from .models import Ticket

    wanted = defaultdict(set)
    for share in shares:
        wanted[share.source_company_id].add(share.source_ticket_id)
    out = {}
    if not wanted:
        return out
    with rls_bypass():
        for company_id, ticket_ids in wanted.items():
            rows = Ticket.objects.filter(company_id=company_id, pk__in=ticket_ids).values_list("pk", "status")
            for pk, status in rows:
                out[(company_id, pk)] = status
    return out


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
        # The vendor sees the source ticket's live status. The list view passes one map for the
        # whole page (a lookup per row was an N+1); a single-row read looks it up itself.
        live = (self.context or {}).get("live_status")
        if live is None:
            live = live_ticket_statuses([instance])
        status = live.get((instance.source_company_id, instance.source_ticket_id))
        if status:
            data["status"] = status
        return data


class TicketCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketComment
        fields = ["id", "body", "is_internal", "created_by", "created_at"]
        read_only_fields = ["id", "created_by", "created_at"]
