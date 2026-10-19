from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F
from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.care import CareSalesAccess, assert_mutable
from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, get_company_user
from core.services.attachments import create_attachment, delete_join_row
from core.services.audit import AuditService
from core.services.feature_flags import flag_enabled
from core.viewsets import CompanyScopedViewSet

from .models import Ticket, TicketAttachment, TicketComment, VendorTicketShare
from .serializers import (
    TicketCommentSerializer,
    TicketSerializer,
    VendorReplySerializer,
    VendorTicketShareSerializer,
    live_ticket_statuses,
)
from .share import revoke_share, share_map, share_ticket, vendor_reply
from .tickets import create_ticket, tickets_past_sla_q, transition_status


class TicketViewSet(CompanyScopedViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated, HasCompany, CareSalesAccess]
    owner_only_actions = ("destroy",)
    audit_entity = "Ticket"
    search_fields = ("number", "subject", "description", "customer__name")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not flag_enabled(get_company_user(request).company, "ENABLE_SUPPORT_TICKETS"):
            raise Http404()

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "assigned_to__user", "customer", "source_invoice", "contract",
        )
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("priority"):
            qs = qs.filter(priority=params["priority"])
        if params.get("category"):
            qs = qs.filter(category=params["category"])
        if params.get("assigned_to"):
            qs = qs.filter(assigned_to_id=params["assigned_to"])
        if str(params.get("unassigned") or "").lower() in {"1", "true", "yes"}:
            qs = qs.filter(assigned_to__isnull=True)
        if params.get("customer"):
            qs = qs.filter(customer_id=params["customer"])
        if params.get("contract"):
            qs = qs.filter(contract_id=params["contract"])
        if params.get("source_invoice"):
            qs = qs.filter(source_invoice_id=params["source_invoice"])
        if str(params.get("mine") or "").lower() in {"1", "true", "yes"}:
            qs = qs.filter(assigned_to=get_company_user(self.request))
        if str(params.get("breached") or "").lower() in {"1", "true", "yes"}:
            qs = qs.filter(status__in=[Ticket.Status.OPEN, Ticket.Status.IN_PROGRESS, Ticket.Status.WAITING])
            qs = qs.filter(tickets_past_sla_q())
        hide_days = params.get("hide_closed_after_days")
        if hide_days and str(hide_days).isdigit():
            cutoff = timezone.now() - timedelta(days=int(hide_days))
            qs = qs.exclude(status=Ticket.Status.CLOSED, updated_at__lt=cutoff)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = list(page) if page is not None else list(queryset)
        context = {
            **self.get_serializer_context(),
            "share_map": share_map(self.company.pk, [row.pk for row in rows]),
        }
        data = TicketSerializer(rows, many=True, context=context).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def perform_destroy(self, instance):
        """A ticket with any history is closed, not deleted."""
        if instance.status != Ticket.Status.OPEN:
            raise BusinessRuleError("Only an open ticket can be deleted. Close the ticket instead.")
        if instance.comments.exists() or instance.attachments.exists():
            raise BusinessRuleError("This ticket has comments or files. Close it instead of deleting it.")
        if instance.job_cards.exists() or instance.complaints.exists() or instance.service_events.exists():
            raise BusinessRuleError("This ticket is linked to other records. Close it instead of deleting it.")
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
            source_invoice=data.get("source_invoice"),
            contract=data.get("contract"),
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
            rows = ticket.comments.select_related("created_by")
            return Response(TicketCommentSerializer(rows, many=True).data)
        assert_mutable(ticket, "This ticket")
        body = str(request.data.get("body") or "").strip()
        if not body:
            raise BusinessRuleError("A comment cannot be empty.")
        row = TicketComment.objects.create(
            company=self.company,
            ticket=ticket,
            body=body,
            is_internal=True,
            created_by=request.user,
            updated_by=request.user,
        )
        AuditService.log(
            action="ticket_comment",
            company=self.company,
            user=request.user,
            entity_type="Ticket",
            entity_id=ticket.pk,
            metadata={"comment_id": row.pk},
        )
        return Response(TicketCommentSerializer(row).data, status=201)

    @action(detail=True, methods=["get", "post", "delete"])
    def attachments(self, request, pk=None):
        ticket = self.get_object()
        rows = ticket.attachments.all()
        if request.method == "GET":
            return Response([{"id": row.id, "file": row.file_id} for row in rows])
        assert_mutable(ticket, "This ticket")
        if request.method == "DELETE":
            delete_join_row(rows, request.query_params.get("attachment"))
            AuditService.log(
                action="ticket_attachment_removed", company=self.company, user=request.user,
                entity_type="Ticket", entity_id=ticket.pk,
                metadata={"attachment": request.query_params.get("attachment")},
            )
            return Response(status=204)
        asset = create_attachment(self.company, request.user, request.FILES.get("file"))
        row = TicketAttachment.objects.create(
            company=self.company, ticket=ticket, file=asset, created_by=request.user, updated_by=request.user,
        )
        AuditService.log(
            action="ticket_attachment_added", company=self.company, user=request.user,
            entity_type="Ticket", entity_id=ticket.pk, metadata={"file": asset.id},
        )
        return Response({"id": row.id, "file": asset.id}, status=201)

    @action(detail=False, methods=["get"])
    def report(self, request):
        """Counts cover every ticket that matches the filters, not just the visible page."""
        base = self.get_queryset()
        resolved = base.filter(resolved_at__isnull=False)
        duration = ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
        average = resolved.aggregate(avg=Avg(duration))["avg"]
        open_states = [Ticket.Status.OPEN, Ticket.Status.IN_PROGRESS, Ticket.Status.WAITING]
        return Response({
            "by_status": list(base.order_by().values("status").annotate(count=Count("id"))),
            "by_priority": list(base.order_by().values("priority").annotate(count=Count("id"))),
            "breached": base.filter(status__in=open_states).filter(tickets_past_sla_q()).count(),
            "average_resolution_seconds": None if average is None else int(average.total_seconds()),
        })

    def handle_exception(self, exc):
        if isinstance(exc, BusinessRuleError):
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)


class VendorTicketShareViewSet(CompanyScopedViewSet):
    """The vendor company's inbox of tickets other companies shared with it."""

    queryset = VendorTicketShare.objects.select_related("source_company")
    serializer_class = VendorTicketShareSerializer
    permission_classes = [IsAuthenticated, HasCompany, CareSalesAccess]
    http_method_names = ["get", "post", "head", "options"]
    search_fields = ("source_number", "subject", "source_company__name")

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Only rows addressed to this company are ever visible, so a company that is not the vendor
        # simply gets an empty inbox. The menu hides the page for them (IS_VENDOR_COMPANY).
        if not flag_enabled(self.company, "ENABLE_SUPPORT_TICKETS"):
            raise Http404()

    def get_queryset(self):
        qs = super().get_queryset().filter(revoked_at__isnull=True)
        wanted = self.request.query_params.get("status")
        if wanted:
            ids = [
                share.pk for share in qs
                if live_ticket_statuses([share]).get((share.source_company_id, share.source_ticket_id), share.status)
                == wanted
            ]
            qs = qs.filter(pk__in=ids)
        return qs

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = list(page) if page is not None else list(queryset)
        counts = dict(
            VendorTicketShare.objects.filter(pk__in=[row.pk for row in rows])
            .annotate(n=Count("comments"))
            .values_list("pk", "n")
        )
        context = {
            **self.get_serializer_context(),
            "live_status": live_ticket_statuses(rows),
            "reply_counts": counts,
        }
        serializer = self.get_serializer(rows, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"])
    def replies(self, request, pk=None):
        share = self.get_object()
        if request.method == "GET":
            return Response(VendorReplySerializer(share.comments.select_related("created_by"), many=True).data)
        try:
            row = vendor_reply(share, request.user, self.company, request.data.get("body"))
        except BusinessRuleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(VendorReplySerializer(row).data, status=201)
