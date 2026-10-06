from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F
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

from .models import Ticket, TicketAttachment, TicketComment, VendorTicketShare
from .serializers import (
    TicketCommentSerializer,
    TicketSerializer,
    VendorTicketShareSerializer,
    live_ticket_statuses,
)
from .share import revoke_share, share_ticket
from .tickets import create_ticket, transition_status


class TicketViewSet(CompanyScopedViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    audit_entity = "Ticket"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(get_company_user(request).company, "ENABLE_SUPPORT_TICKETS"):
            raise Http404()

    def get_queryset(self):
        qs = super().get_queryset().select_related("assigned_to__user")
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("priority"):
            qs = qs.filter(priority=params["priority"])
        if params.get("assigned_to"):
            qs = qs.filter(assigned_to_id=params["assigned_to"])
        if params.get("customer"):
            qs = qs.filter(customer_id=params["customer"])
        if str(params.get("mine") or "").lower() in {"1", "true", "yes"}:
            qs = qs.filter(assigned_to=get_company_user(self.request))
        return qs

    def perform_destroy(self, instance):
        from core.rls import rls_bypass

        with rls_bypass():
            VendorTicketShare.objects.filter(
                source_company_id=instance.company_id,
                source_ticket_id=instance.pk,
            ).delete()
        super().perform_destroy(instance)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = create_ticket(
            self.company,
            request.user,
            customer=data["customer"],
            subject=data["subject"],
            description=data.get("description") or "",
            priority=data.get("priority") or Ticket.Priority.MEDIUM,
            category=data.get("category") or Ticket.Category.GENERAL,
            assigned_to=data.get("assigned_to"),
        )
        self._audit("CREATE", row)
        return Response(TicketSerializer(row, context={"request": request}).data, status=201)

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        include = bool(request.data.get("include_description") or request.data.get("includeDescription"))
        share_ticket(self.get_object(), request.user, include_description=include)
        return Response({"shared": True})

    @action(detail=True, methods=["post"], url_path="stop-sharing")
    def stop_sharing(self, request, pk=None):
        revoke_share(self.get_object(), request.user)
        return Response({"shared": False})

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        row = transition_status(self.get_object(), request.user, new_status=request.data.get("status") or "")
        return Response(TicketSerializer(row, context={"request": request}).data)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        ticket = self.get_object()
        if request.method == "GET":
            return Response(TicketCommentSerializer(ticket.comments.all(), many=True).data)
        row = TicketComment.objects.create(
            company=self.company,
            ticket=ticket,
            body=request.data.get("body") or "",
            is_internal=True,
            created_by=request.user,
            updated_by=request.user,
        )
        return Response(TicketCommentSerializer(row).data, status=201)

    @action(detail=True, methods=["get", "post", "delete"])
    def attachments(self, request, pk=None):
        ticket = self.get_object()
        rows = ticket.attachments.all()
        if request.method == "GET":
            return Response([{"id": row.id, "file": row.file_id} for row in rows])
        if request.method == "DELETE":
            delete_join_row(rows, request.query_params.get("attachment"))
            return Response(status=204)
        asset = create_attachment(self.company, request.user, request.FILES.get("file"))
        row = TicketAttachment.objects.create(
            company=self.company, ticket=ticket, file=asset, created_by=request.user, updated_by=request.user,
        )
        return Response({"id": row.id, "file": asset.id}, status=201)

    @action(detail=False, methods=["get"])
    def report(self, request):
        resolved = self.get_queryset().filter(resolved_at__isnull=False)
        duration = ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
        average = resolved.aggregate(avg=Avg(duration))["avg"]
        return Response({
            "by_status": list(self.get_queryset().values("status").annotate(count=Count("id"))),
            "average_resolution_seconds": None if average is None else int(average.total_seconds()),
        })

    def handle_exception(self, exc):
        if isinstance(exc, BusinessRuleError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)


class VendorTicketShareViewSet(CompanyScopedViewSet):
    queryset = VendorTicketShare.objects.select_related("source_company")
    serializer_class = VendorTicketShareSerializer
    permission_classes = [IsAuthenticated, HasCompany, CanCreateSales]
    http_method_names = ["get", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(self.company, "ENABLE_SUPPORT_TICKETS"):
            raise Http404()

    def get_queryset(self):
        return super().get_queryset().filter(revoked_at__isnull=True)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = list(page) if page is not None else list(queryset)
        context = {**self.get_serializer_context(), "live_status": live_ticket_statuses(rows)}
        serializer = self.get_serializer(rows, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
