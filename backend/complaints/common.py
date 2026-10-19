"""Behaviour shared by customer and supplier complaint viewsets."""

from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F
from django.http import Http404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.care import assert_mutable
from core.exceptions import BusinessRuleError
from core.permissions import get_company_user
from core.services.attachments import create_attachment, delete_join_row
from core.services.audit import AuditService
from core.services.feature_flags import flag_enabled

from .services import save_notes, unlink_document

CLOSED = ("RESOLVED", "REJECTED")
AGE_BUCKETS = (("0-2 days", 0, 2), ("3-7 days", 3, 7), ("8-14 days", 8, 14), ("15+ days", 15, None))


class ComplaintCommon:
    """Mixin for ``CompanyScopedViewSet`` subclasses. The class sets the hooks below."""

    party_field = "customer"
    document_attrs: tuple = ()
    attachment_model = None
    attachment_serializer = None
    flag = "ENABLE_COMPLAINTS"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(get_company_user(request).company, self.flag):
            raise Http404()

    # ---- listing -----------------------------------------------------------------------------
    def filter_complaints(self, qs):
        params = self.request.query_params
        for name in ("status", "category"):
            if params.get(name):
                qs = qs.filter(**{name: params[name]})
        if params.get(self.party_field):
            qs = qs.filter(**{f"{self.party_field}_id": params[self.party_field]})
        if params.get("assigned_to"):
            qs = qs.filter(assigned_to_id=params["assigned_to"])
        if params.get("source_invoice"):
            qs = qs.filter(source_invoice_id=params["source_invoice"])
        created_from = parse_date(params.get("created_from") or "")
        created_to = parse_date(params.get("created_to") or "")
        if created_from:
            qs = qs.filter(created_at__date__gte=created_from)
        if created_to:
            qs = qs.filter(created_at__date__lte=created_to)
        if str(params.get("mine") or "").lower() in {"1", "true", "yes"}:
            qs = qs.filter(assigned_to=get_company_user(self.request))
        return qs

    # ---- rules -------------------------------------------------------------------------------
    def perform_update(self, serializer):
        if serializer.instance.status in CLOSED:
            raise BusinessRuleError("A closed complaint cannot be edited.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.status in CLOSED:
            raise BusinessRuleError("A closed complaint cannot be deleted.")
        if any(getattr(instance, name) for name in self.document_attrs):
            raise BusinessRuleError("This complaint has a linked document. Reject or resolve it instead.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"], url_path="save-notes")
    def save_notes_action(self, request, pk=None):
        row = save_notes(self.get_object(), request.user, request.data.get("inspection_notes"))
        return Response(self.get_serializer(row).data)

    @action(detail=True, methods=["post"], url_path="unlink-document")
    def unlink(self, request, pk=None):
        default = self.document_attrs[0] if len(self.document_attrs) == 1 else ""
        row = unlink_document(self.get_object(), request.user, request.data.get("document") or default)
        return Response(self.get_serializer(row).data)

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        from core.care_timeline import timeline_rows

        return Response(timeline_rows(self.company, self.audit_entity, self.get_object().pk))

    @action(detail=True, methods=["get", "post", "delete"])
    def attachments(self, request, pk=None):
        complaint = self.get_object()
        rows = complaint.attachments.select_related("file")
        if request.method == "GET":
            return Response(self.attachment_serializer(rows, many=True).data)
        assert_mutable(complaint, "This complaint")
        if request.method == "DELETE":
            delete_join_row(rows, request.query_params.get("attachment"))
            AuditService.log(
                action="complaint_attachment_removed", company=self.company, user=request.user,
                entity_type=self.audit_entity, entity_id=complaint.pk,
                metadata={"attachment": request.query_params.get("attachment")},
            )
            return Response(status=204)
        asset = create_attachment(self.company, request.user, request.FILES.get("file"))
        row = self.attachment_model.objects.create(
            company=self.company, complaint=complaint, file=asset,
            created_by=request.user, updated_by=request.user,
        )
        AuditService.log(
            action="complaint_attachment_added", company=self.company, user=request.user,
            entity_type=self.audit_entity, entity_id=complaint.pk, metadata={"file": asset.id},
        )
        return Response(self.attachment_serializer(row).data, status=201)

    # ---- report ------------------------------------------------------------------------------
    def build_report(self):
        base = self.get_queryset()
        resolved = base.filter(status="RESOLVED")
        duration = ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
        average = resolved.aggregate(avg=Avg(duration))["avg"]
        document_filter = {f"{name}__isnull": True for name in self.document_attrs}
        with_doc = resolved.exclude(**document_filter).count()
        now = timezone.now()
        open_rows = base.exclude(status__in=CLOSED)
        ageing = []
        for label, low, high in AGE_BUCKETS:
            bucket = open_rows.filter(created_at__lte=now - timedelta(days=low))
            if high is not None:
                bucket = bucket.filter(created_at__gt=now - timedelta(days=high + 1))
            ageing.append({"bucket": label, "count": bucket.count()})
        resolved_count = resolved.count()
        return {
            "by_category": list(base.order_by().values("category").annotate(count=Count("id")).order_by("category")),
            "by_status": list(base.order_by().values("status").annotate(count=Count("id")).order_by("status")),
            "by_assignee": list(
                base.order_by().values("assigned_to").annotate(count=Count("id")).order_by("assigned_to")
            ),
            "ageing": ageing,
            "resolved": resolved_count,
            "resolved_with_document": with_doc,
            "resolved_without_document": resolved_count - with_doc,
            "average_resolution_seconds": None if average is None else int(average.total_seconds()),
        }

    def handle_exception(self, exc):
        if isinstance(exc, BusinessRuleError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)
