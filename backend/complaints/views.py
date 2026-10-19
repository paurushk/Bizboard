from django.db import transaction
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.care import CareSalesAccess
from core.permissions import HasCompany
from core.services.audit import AuditService
from core.viewsets import CompanyScopedViewSet
from sales.phase1_serializers import SalesCreditNoteSerializer, SalesOrderSerializer
from sales.serializers import SalesReturnSerializer

from .common import ComplaintCommon
from .models import Complaint, ComplaintAttachment
from .serializers import ComplaintAttachmentSerializer, ComplaintSerializer
from .services import (
    assert_document_status,
    assert_within_returnable,
    create_complaint,
    transition_status,
)


class ComplaintViewSet(ComplaintCommon, CompanyScopedViewSet):
    queryset = Complaint.objects.all()
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated, HasCompany, CareSalesAccess]
    owner_only_actions = ("destroy",)
    audit_entity = "Complaint"
    search_fields = ("number", "description", "customer__name", "source_invoice__number")
    party_field = "customer"
    document_attrs = ("sales_return", "sales_credit_note", "replacement_order")
    attachment_model = ComplaintAttachment
    attachment_serializer = ComplaintAttachmentSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "customer", "source_invoice", "assigned_to__user", "ticket",
        )
        qs = self.filter_complaints(qs)
        if self.request.query_params.get("ticket"):
            qs = qs.filter(ticket_id=self.request.query_params["ticket"])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = create_complaint(
            self.company,
            request.user,
            customer=data["customer"],
            category=data["category"],
            description=data["description"].strip(),
            source_invoice=data.get("source_invoice"),
        )
        extra = []
        if data.get("assigned_to"):
            row.assigned_to = data["assigned_to"]
            extra.append("assigned_to")
        if data.get("ticket"):
            row.ticket = data["ticket"]
            extra.append("ticket")
        if extra:
            row.save(update_fields=[*extra, "updated_at"])
        self._audit("CREATE", row)
        return Response(ComplaintSerializer(row, context={"request": request}).data, status=201)

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        row = transition_status(
            self.get_object(),
            request.user,
            new_status=request.data.get("status") or "",
            inspection_notes=request.data.get("inspection_notes"),
            resolution_note=request.data.get("resolution_note"),
        )
        return Response(ComplaintSerializer(row, context={"request": request}).data)

    def _link_document(self, request, attr, serializer_cls, extra):
        def _build():
            with transaction.atomic():
                complaint = Complaint.objects.select_for_update().get(
                    pk=self.get_object().pk, company=self.company,
                )
                assert_document_status(complaint)
                existing = getattr(complaint, attr)
                if existing is not None:
                    return Response({"id": existing.id, "existing": True})
                if attr == "sales_credit_note" and complaint.sales_return_id:
                    raise BusinessRuleError(
                        "This complaint already has a sales return. Do not add a separate credit note."
                    )
                if attr == "sales_return" and complaint.sales_credit_note_id:
                    raise BusinessRuleError(
                        "This complaint already has a credit note. Do not add a sales return."
                    )
                if attr != "replacement_order" and complaint.source_invoice_id is None:
                    return Response({"detail": "Set a source invoice before creating this document."}, status=400)
                items = request.data.get("items") or []
                if not items:
                    return Response({"detail": "Select at least one item."}, status=400)
                if attr != "replacement_order":
                    assert_within_returnable(complaint.source_invoice, items)
                payload = {
                    "customer": complaint.customer_id,
                    "items": items,
                    **extra,
                }
                if attr != "replacement_order":
                    payload["sales_invoice"] = complaint.source_invoice_id
                serializer = serializer_cls(data=payload, context={"request": request})
                serializer.is_valid(raise_exception=True)
                document = serializer.save(
                    company=self.company, created_by=request.user, updated_by=request.user,
                )
                setattr(complaint, attr, document)
                complaint.updated_by = request.user
                complaint.save(update_fields=[attr, "updated_by", "updated_at"])
                AuditService.log(
                    action="complaint_document_linked", company=self.company, user=request.user,
                    entity_type="Complaint", entity_id=complaint.pk,
                    metadata={"document": attr, "document_id": document.pk},
                )
            warning = None
            if attr == "sales_return":
                if Complaint.objects.filter(
                    company=self.company, sales_return=document,
                ).exclude(pk=complaint.pk).exists():
                    warning = "Another complaint already links this return."
            body = {"id": document.id, "existing": False}
            if warning:
                body["warning"] = warning
            return Response(body, status=201)

        return wrap_idempotent(
            request=request, company=self.company,
            scope=f"complaint_document:{self.kwargs.get('pk')}:{attr}", build=_build,
        )

    @action(detail=True, methods=["post"], url_path="create-return")
    def create_return(self, request, pk=None):
        return self._link_document(request, "sales_return", SalesReturnSerializer, {})

    @action(detail=True, methods=["post"], url_path="create-credit-note")
    def create_credit_note(self, request, pk=None):
        return self._link_document(request, "sales_credit_note", SalesCreditNoteSerializer, {})

    @action(detail=True, methods=["post"], url_path="create-replacement-order")
    def create_replacement_order(self, request, pk=None):
        return self._link_document(request, "replacement_order", SalesOrderSerializer, {})

    @action(detail=True, methods=["post"], url_path="create-ticket")
    def create_ticket(self, request, pk=None):
        """Open a support ticket for this complaint and link the two (XLK-01)."""
        from support.models import Ticket
        from support.tickets import create_ticket as make_ticket

        complaint = self.get_object()
        if complaint.ticket_id:
            return Response({"id": complaint.ticket_id, "existing": True})
        ticket = make_ticket(
            self.company, request.user, customer=complaint.customer,
            subject=f"{complaint.number}: {complaint.description[:120]}",
            description=complaint.description, priority=Ticket.Priority.MEDIUM,
            source_invoice=complaint.source_invoice,
        )
        complaint.ticket = ticket
        complaint.updated_by = request.user
        complaint.save(update_fields=["ticket", "updated_by", "updated_at"])
        return Response({"id": ticket.id, "existing": False}, status=201)

    @action(detail=False, methods=["get"])
    def report(self, request):
        return Response(self.build_report())
