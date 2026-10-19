from django.db import transaction
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.idempotency import wrap_idempotent
from core.care import CarePurchaseAccess
from core.permissions import HasCompany
from core.services.audit import AuditService
from core.viewsets import CompanyScopedViewSet
from purchases.phase1_serializers import PurchaseDebitNoteSerializer

from .common import ComplaintCommon
from .models import SupplierComplaint, SupplierComplaintAttachment
from .serializers import SupplierComplaintAttachmentSerializer, SupplierComplaintSerializer
from .services import (
    assert_document_status,
    assert_within_billed,
    create_supplier_complaint,
    transition_supplier_status,
)


class SupplierComplaintViewSet(ComplaintCommon, CompanyScopedViewSet):
    """A supplier complaint has one remedy document, the purchase debit note (decision D12)."""

    queryset = SupplierComplaint.objects.all()
    serializer_class = SupplierComplaintSerializer
    permission_classes = [IsAuthenticated, HasCompany, CarePurchaseAccess]
    owner_only_actions = ("destroy",)
    audit_entity = "SupplierComplaint"
    search_fields = ("number", "description", "supplier__name", "source_invoice__number")
    party_field = "supplier"
    document_attrs = ("purchase_debit_note",)
    attachment_model = SupplierComplaintAttachment
    attachment_serializer = SupplierComplaintAttachmentSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("supplier", "source_invoice", "assigned_to__user")
        return self.filter_complaints(qs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = create_supplier_complaint(
            self.company,
            request.user,
            supplier=data["supplier"],
            category=data["category"],
            description=data["description"].strip(),
            source_invoice=data.get("source_invoice"),
        )
        if data.get("assigned_to"):
            row.assigned_to = data["assigned_to"]
            row.save(update_fields=["assigned_to", "updated_at"])
        self._audit("CREATE", row)
        return Response(SupplierComplaintSerializer(row, context={"request": request}).data, status=201)

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        row = transition_supplier_status(
            self.get_object(),
            request.user,
            new_status=request.data.get("status") or "",
            inspection_notes=request.data.get("inspection_notes"),
            resolution_note=request.data.get("resolution_note"),
        )
        return Response(SupplierComplaintSerializer(row, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="create-debit-note")
    def create_debit_note(self, request, pk=None):
        def _build():
            with transaction.atomic():
                complaint = SupplierComplaint.objects.select_for_update().get(
                    pk=self.get_object().pk, company=self.company,
                )
                assert_document_status(complaint)
                if complaint.purchase_debit_note_id is not None:
                    return Response({"id": complaint.purchase_debit_note_id, "existing": True})
                if complaint.source_invoice_id is None:
                    return Response(
                        {"detail": "Set a source purchase bill before creating a debit note."},
                        status=400,
                    )
                items = request.data.get("items") or []
                if not items:
                    return Response({"detail": "Select at least one item."}, status=400)
                assert_within_billed(complaint.source_invoice, items)
                serializer = PurchaseDebitNoteSerializer(
                    data={
                        "supplier": complaint.supplier_id,
                        "purchase_invoice": complaint.source_invoice_id,
                        "items": items,
                    },
                    context={"request": request},
                )
                serializer.is_valid(raise_exception=True)
                document = serializer.save(
                    company=self.company, created_by=request.user, updated_by=request.user,
                )
                complaint.purchase_debit_note = document
                complaint.updated_by = request.user
                complaint.save(update_fields=["purchase_debit_note", "updated_by", "updated_at"])
                AuditService.log(
                    action="complaint_document_linked", company=self.company, user=request.user,
                    entity_type="SupplierComplaint", entity_id=complaint.pk,
                    metadata={"document": "purchase_debit_note", "document_id": document.pk},
                )
            warning = None
            if SupplierComplaint.objects.filter(
                company=self.company, purchase_debit_note=document,
            ).exclude(pk=complaint.pk).exists():
                warning = "Another supplier complaint already links this debit note."
            body = {"id": document.id, "existing": False}
            if warning:
                body["warning"] = warning
            return Response(body, status=201)

        return wrap_idempotent(
            request=request, company=self.company,
            scope=f"supplier_complaint_document:{self.kwargs.get('pk')}", build=_build,
        )

    @action(detail=False, methods=["get"])
    def report(self, request):
        return Response(self.build_report())
