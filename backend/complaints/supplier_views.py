from django.db import transaction
from django.http import Http404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.permissions import CanCreatePurchases, HasCompany, get_company_user
from core.services.attachments import create_attachment, delete_join_row
from core.services.feature_flags import flag_enabled
from core.viewsets import CompanyScopedViewSet
from purchases.phase1_serializers import PurchaseDebitNoteSerializer

from .models import SupplierComplaint, SupplierComplaintAttachment
from .serializers import SupplierComplaintAttachmentSerializer, SupplierComplaintSerializer
from .services import assert_document_status, create_supplier_complaint, transition_supplier_status


_CLOSED_SUPPLIER_COMPLAINT = {
    SupplierComplaint.Status.RESOLVED,
    SupplierComplaint.Status.REJECTED,
}


class SupplierComplaintViewSet(CompanyScopedViewSet):
    queryset = SupplierComplaint.objects.all()
    serializer_class = SupplierComplaintSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreatePurchases]
    audit_entity = "SupplierComplaint"

    def perform_update(self, serializer):
        if serializer.instance.status in _CLOSED_SUPPLIER_COMPLAINT:
            raise BusinessRuleError("A closed complaint cannot be edited.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.status in _CLOSED_SUPPLIER_COMPLAINT:
            raise BusinessRuleError("A closed complaint cannot be deleted.")
        super().perform_destroy(instance)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(get_company_user(request).company, "ENABLE_COMPLAINTS"):
            raise Http404()

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("category"):
            qs = qs.filter(category=params["category"])
        if params.get("supplier"):
            qs = qs.filter(supplier_id=params["supplier"])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = create_supplier_complaint(
            self.company,
            request.user,
            supplier=data["supplier"],
            category=data["category"],
            description=data["description"],
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
        )
        return Response(SupplierComplaintSerializer(row, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="create-debit-note")
    def create_debit_note(self, request, pk=None):
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
        warning = None
        if SupplierComplaint.objects.filter(
            company=self.company, purchase_debit_note=document,
        ).exclude(pk=complaint.pk).exists():
            warning = "Another supplier complaint already links this debit note."
        body = {"id": document.id, "existing": False}
        if warning:
            body["warning"] = warning
        return Response(body, status=201)

    @action(detail=False, methods=["get"])
    def report(self, request):
        from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F

        resolved = self.get_queryset().filter(status=SupplierComplaint.Status.RESOLVED)
        duration = ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
        average = resolved.aggregate(avg=Avg(duration))["avg"]
        by_category = list(
            self.get_queryset().values("category").annotate(count=Count("id")).order_by("category")
        )
        with_doc = resolved.exclude(purchase_debit_note__isnull=True).count()
        return Response({
            "by_category": by_category,
            "resolved": resolved.count(),
            "resolved_with_document": with_doc,
            "resolved_without_document": resolved.count() - with_doc,
            "average_resolution_seconds": None if average is None else int(average.total_seconds()),
        })

    @action(detail=True, methods=["get", "post", "delete"])
    def attachments(self, request, pk=None):
        complaint = self.get_object()
        rows = complaint.attachments.select_related("file")
        if request.method == "GET":
            return Response(SupplierComplaintAttachmentSerializer(rows, many=True).data)
        if request.method == "DELETE":
            delete_join_row(rows, request.query_params.get("attachment"))
            return Response(status=204)
        asset = create_attachment(self.company, request.user, request.FILES.get("file"))
        row = SupplierComplaintAttachment.objects.create(
            company=self.company, complaint=complaint, file=asset,
            created_by=request.user, updated_by=request.user,
        )
        return Response(SupplierComplaintAttachmentSerializer(row).data, status=201)

    def handle_exception(self, exc):
        if isinstance(exc, BusinessRuleError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)
