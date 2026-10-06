from django.db import transaction
from django.http import Http404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.exceptions import BusinessRuleError
from core.permissions import CanCreateSales, HasCompany, get_company_user
from core.services.attachments import create_attachment, delete_join_row
from core.services.feature_flags import flag_enabled
from core.viewsets import CompanyScopedViewSet
from sales.phase1_serializers import SalesCreditNoteSerializer, SalesOrderSerializer
from sales.serializers import SalesReturnSerializer

from .models import Complaint, ComplaintAttachment
from .serializers import ComplaintAttachmentSerializer, ComplaintSerializer
from .services import assert_document_status, create_complaint, transition_status


_CLOSED_COMPLAINT = {Complaint.Status.RESOLVED, Complaint.Status.REJECTED}


class ComplaintViewSet(CompanyScopedViewSet):
    queryset = Complaint.objects.all()
    serializer_class = ComplaintSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "Complaint"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(get_company_user(request).company, "ENABLE_COMPLAINTS"):
            raise Http404()

    def perform_update(self, serializer):
        if serializer.instance.status in _CLOSED_COMPLAINT:
            raise BusinessRuleError("A closed complaint cannot be edited.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.status in _CLOSED_COMPLAINT:
            raise BusinessRuleError("A closed complaint cannot be deleted.")
        super().perform_destroy(instance)

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("category"):
            qs = qs.filter(category=params["category"])
        if params.get("customer"):
            qs = qs.filter(customer_id=params["customer"])
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
            description=data["description"],
            source_invoice=data.get("source_invoice"),
        )
        if data.get("assigned_to"):
            row.assigned_to = data["assigned_to"]
            row.save(update_fields=["assigned_to", "updated_at"])
        self._audit("CREATE", row)
        return Response(ComplaintSerializer(row, context={"request": request}).data, status=201)

    @action(detail=True, methods=["post"], url_path="transition")
    def transition(self, request, pk=None):
        row = transition_status(
            self.get_object(),
            request.user,
            new_status=request.data.get("status") or "",
            inspection_notes=request.data.get("inspection_notes"),
        )
        return Response(ComplaintSerializer(row, context={"request": request}).data)

    def _link_document(self, request, attr, serializer_cls, extra):
        with transaction.atomic():
            complaint = Complaint.objects.select_for_update().get(pk=self.get_object().pk, company=self.company)
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
        warning = None
        if attr == "sales_return":
            if Complaint.objects.filter(company=self.company, sales_return=document).exclude(pk=complaint.pk).exists():
                warning = "Another complaint already links this return."
        body = {"id": document.id, "existing": False}
        if warning:
            body["warning"] = warning
        return Response(body, status=201)

    @action(detail=True, methods=["post"], url_path="create-return")
    def create_return(self, request, pk=None):
        return self._link_document(request, "sales_return", SalesReturnSerializer, {})

    @action(detail=True, methods=["post"], url_path="create-credit-note")
    def create_credit_note(self, request, pk=None):
        return self._link_document(request, "sales_credit_note", SalesCreditNoteSerializer, {})

    @action(detail=True, methods=["post"], url_path="create-replacement-order")
    def create_replacement_order(self, request, pk=None):
        return self._link_document(request, "replacement_order", SalesOrderSerializer, {})

    @action(detail=False, methods=["get"])
    def report(self, request):
        from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F

        resolved = self.get_queryset().filter(status=Complaint.Status.RESOLVED)
        duration = ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
        average = resolved.aggregate(avg=Avg(duration))["avg"]
        by_category = list(
            self.get_queryset().values("category").annotate(count=Count("id")).order_by("category")
        )
        with_doc = resolved.exclude(
            sales_return__isnull=True, sales_credit_note__isnull=True, replacement_order__isnull=True,
        ).count()
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
            return Response(ComplaintAttachmentSerializer(rows, many=True).data)
        if request.method == "DELETE":
            delete_join_row(rows, request.query_params.get("attachment"))
            return Response(status=204)
        asset = create_attachment(self.company, request.user, request.FILES.get("file"))
        row = ComplaintAttachment.objects.create(
            company=self.company, complaint=complaint, file=asset,
            created_by=request.user, updated_by=request.user,
        )
        return Response(ComplaintAttachmentSerializer(row).data, status=201)

    def handle_exception(self, exc):
        if isinstance(exc, BusinessRuleError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)
