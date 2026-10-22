from rest_framework import serializers

from accounts.models import CompanyUser
from contracts.models import Contract
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer
from sales.models import SalesInvoice

from .models import (
    PlatformTicket,
    PlatformTicketMessage,
    Ticket,
    TicketComment,
    VendorTicketShare,
    VendorTicketShareComment,
)
from .tickets import effective_sla_due_at, reprioritise, sla_state


class TicketSerializer(serializers.ModelSerializer):
    customer = CompanyPrimaryKeyRelatedField(queryset=Customer.objects.all())
    assigned_to = CompanyPrimaryKeyRelatedField(
        queryset=CompanyUser.objects.all(), allow_null=True, required=False
    )
    source_invoice = CompanyPrimaryKeyRelatedField(
        queryset=SalesInvoice.objects.all(), allow_null=True, required=False
    )
    contract = CompanyPrimaryKeyRelatedField(
        queryset=Contract.objects.all(), allow_null=True, required=False
    )
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    assignee_name = serializers.SerializerMethodField()
    share_available = serializers.SerializerMethodField()
    shared = serializers.SerializerMethodField()
    shared_at = serializers.SerializerMethodField()
    share_includes_description = serializers.SerializerMethodField()
    source_invoice_number = serializers.SerializerMethodField()
    contract_number = serializers.SerializerMethodField()

    def get_assignee_name(self, obj):
        member = getattr(obj, "assigned_to", None)
        user = getattr(member, "user", None)
        if user is None:
            return ""
        return (getattr(user, "full_name", "") or getattr(user, "email", "") or "").strip()

    def get_share_available(self, obj):
        from .share import vendor_company_id

        return vendor_company_id() is not None

    def _share(self, obj):
        shares = (self.context or {}).get("share_map")
        if shares is None:
            from .share import share_map

            shares = share_map(obj.company_id, [obj.pk])
        return shares.get(obj.pk)

    def get_shared(self, obj):
        return self._share(obj) is not None

    def get_shared_at(self, obj):
        share = self._share(obj)
        return share[0].isoformat() if share else None

    def get_share_includes_description(self, obj):
        share = self._share(obj)
        return bool(share[1]) if share else False

    def get_source_invoice_number(self, obj):
        invoice = obj.source_invoice
        return (invoice.number or f"#{invoice.pk}") if invoice else ""

    def get_contract_number(self, obj):
        contract = obj.contract
        return (contract.number or f"#{contract.pk}") if contract else ""

    class Meta:
        model = Ticket
        fields = [
            "id", "number", "customer", "customer_name", "subject", "description", "category", "priority",
            "status", "assigned_to", "assignee_name", "share_available", "shared", "shared_at",
            "share_includes_description", "source_invoice", "source_invoice_number", "contract",
            "contract_number", "sla_due_at", "sla_state", "sla_remaining_seconds", "waiting_since",
            "resolved_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "status", "sla_due_at", "waiting_since", "resolved_at", "created_at", "updated_at",
        ]

    sla_state = serializers.SerializerMethodField()
    sla_remaining_seconds = serializers.SerializerMethodField()

    def get_sla_state(self, obj):
        return sla_state(obj)["state"]

    def get_sla_remaining_seconds(self, obj):
        return sla_state(obj)["remaining_seconds"]

    def validate_subject(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("A ticket needs a subject.")
        return value

    def validate(self, attrs):
        if self.instance is not None:
            if self.instance.status == Ticket.Status.CLOSED:
                raise serializers.ValidationError("A closed ticket cannot be edited. Re-open it first.")
            if "customer" in attrs and attrs["customer"].id != self.instance.customer_id:
                raise serializers.ValidationError({"customer": "The customer of a ticket cannot be changed."})
        customer = attrs.get("customer") or getattr(self.instance, "customer", None)
        invoice = attrs.get("source_invoice", getattr(self.instance, "source_invoice", None))
        contract = attrs.get("contract", getattr(self.instance, "contract", None))
        if invoice is not None and customer is not None and invoice.customer_id != customer.id:
            raise serializers.ValidationError({"source_invoice": "The invoice must belong to the ticket's customer."})
        if contract is not None and customer is not None and contract.customer_id != customer.id:
            raise serializers.ValidationError({"contract": "The contract must belong to the ticket's customer."})
        return attrs

    def update(self, instance, validated_data):
        new_priority = validated_data.pop("priority", None)
        row = super().update(instance, validated_data)
        if new_priority is not None and new_priority != row.priority:
            request = self.context.get("request")
            reprioritise(row, getattr(request, "user", None), new_priority)
        from .share import sync_share

        sync_share(row)
        return row

    def to_representation(self, instance):
        original = instance.sla_due_at
        instance.sla_due_at = effective_sla_due_at(instance)
        try:
            data = super().to_representation(instance)
        finally:
            instance.sla_due_at = original
        return data


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
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = VendorTicketShare
        fields = [
            "id", "source_company_name", "source_number", "subject", "status",
            "description", "shared_at", "reply_count",
        ]
        read_only_fields = fields

    def get_reply_count(self, obj):
        counts = (self.context or {}).get("reply_counts")
        if counts is not None:
            return counts.get(obj.pk, 0)
        return obj.comments.count()

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


class VendorReplySerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = VendorTicketShareComment
        fields = ["id", "body", "author_name", "created_at"]
        read_only_fields = fields

    def get_author_name(self, obj):
        user = obj.created_by
        return (getattr(user, "full_name", "") or getattr(user, "email", "") or "").strip()


class TicketCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TicketComment
        fields = [
            "id", "body", "is_internal", "from_vendor", "author_name", "created_by", "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "from_vendor", "author_name"]

    def get_author_name(self, obj):
        if obj.from_vendor:
            return obj.author_label or "Vendor"
        user = obj.created_by
        return (getattr(user, "full_name", "") or getattr(user, "email", "") or "").strip()


class PlatformTicketSerializer(serializers.ModelSerializer):
    """WP-PO3: a tenant's request to Bizboard support."""

    raised_by_email = serializers.CharField(source="raised_by.email", read_only=True)

    class Meta:
        model = PlatformTicket
        fields = [
            "id", "subject", "description", "severity", "tag", "status", "raised_by_email",
            "support_id", "route", "app_version", "error_codes", "sla_due_at", "first_response_at",
            "resolved_at", "created_at",
        ]
        read_only_fields = fields


class PlatformTicketMessageSerializer(serializers.ModelSerializer):
    author_email = serializers.CharField(source="author.email", read_only=True)

    class Meta:
        model = PlatformTicketMessage
        fields = ["id", "body", "from_staff", "author_email", "created_at"]
        read_only_fields = fields
