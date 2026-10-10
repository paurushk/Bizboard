import re
from datetime import date

from django.db.models import DecimalField, Exists, F, OuterRef, Prefetch, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.celery_utils import safe_delay
from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode
from core.idempotency import (
    begin_record,
    release_record,
    request_fingerprint,
    require_idempotency_key,
    store_record,
    wrap_idempotent,
)
from core.models import Notification
from billing.permissions import SubscriptionWritesAllowed
from core.permissions import (
    CanCancelDocuments,
    CanCreatePayments,
    CanCreateSales,
    CanViewFinancialReports,
    CanViewSalesSurfaces,
    HasCompany,
    IsOwner,
)
from core.services.billing import build_totals_preview
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.services.notifications import NotificationService
from core.viewsets import CompanyScopedViewSet
from masters.models import Customer, Product
from payments.models import PaymentAllocation

from .status_semantics import NO_BALANCE_STATUSES, OPEN_RECEIVABLE_STATUSES
from .einvoice_eway_actions import InvoiceEinvoiceEwayActionsMixin
from .models import Quotation, QuotationConversion, RecurringInvoiceSchedule, SalesInvoice, SalesReturn
from .serializers import (
    QuotationSerializer,
    RecurringInvoiceScheduleSerializer,
    SalesInvoiceSerializer,
    SalesReturnSerializer,
)
from .services import SalesService, _tax_enabled
from .settlement import annotate_live_settlement as _annotate_live_settlement
from .tasks import generate_invoice_pdf


def _convert_line_quantities(request):
    """Optional CFT-115 payload: items: [{id, quantity}, ...]. None = convert remaining."""
    items = request.data.get("items") if hasattr(request.data, "get") else None
    if not items:
        return None
    if not isinstance(items, list):
        raise BusinessRuleError("items must be a list of {id, quantity}.")
    out = []
    for row in items:
        if not isinstance(row, dict) or "id" not in row or "quantity" not in row:
            raise BusinessRuleError("Each convert item needs id and quantity.")
        out.append({"id": row["id"], "quantity": row["quantity"]})
    return out

_INVOICE_IDEMPOTENCY_TTL = 60 * 60 * 24  # 24h


def _apply_payment_status(qs, payment_status):
    """payment_status is one bucket name or a list of them (a bill matches any of the buckets)."""
    # A draft or cancelled invoice has no receivable: it is neither paid nor unpaid.
    if "_balance" not in getattr(qs.query, "annotations", {}):
        qs = _annotate_live_settlement(qs)
    qs = qs.filter(status__in=OPEN_RECEIVABLE_STATUSES)
    wanted = [payment_status] if isinstance(payment_status, str) else list(payment_status)
    any_settled = Q(_live_alloc__gt=0) | Q(_cn__gt=0) | Q(_settle__gt=0)
    match = Q(pk__in=[])
    if "PAID" in wanted:
        match |= Q(_balance__lte=0, grand_total__gt=0)
    if "UNPAID" in wanted:
        match |= Q(_balance__gt=0, _live_alloc=0, _cn=0, _settle=0)
    if "PARTIAL" in wanted:
        match |= Q(_balance__gt=0) & any_settled
    return qs.filter(match)


class _StatsBucketSerializer(drf_serializers.Serializer):
    count = drf_serializers.IntegerField()
    amount = drf_serializers.DecimalField(max_digits=14, decimal_places=2)


class InvoicePaymentStatsSerializer(drf_serializers.Serializer):
    """paid.amount is the billed grand total. partial.amount and unpaid.amount are outstanding."""

    paid = _StatsBucketSerializer()
    partial = _StatsBucketSerializer()
    unpaid = _StatsBucketSerializer()


class _ZipIncludedSerializer(drf_serializers.Serializer):
    id = drf_serializers.IntegerField()
    number = drf_serializers.CharField()


class _ZipSkippedSerializer(drf_serializers.Serializer):
    id = drf_serializers.IntegerField()
    number = drf_serializers.CharField(required=False)
    reason = drf_serializers.ChoiceField(choices=["not_completed", "unavailable"])


class InvoiceBulkPdfZipRequestSerializer(drf_serializers.Serializer):
    ids = drf_serializers.ListField(child=drf_serializers.IntegerField())


class InvoiceBulkPdfZipSerializer(drf_serializers.Serializer):
    url = drf_serializers.CharField()
    file_id = drf_serializers.IntegerField()
    included = _ZipIncludedSerializer(many=True)
    skipped = _ZipSkippedSerializer(many=True)


class SalesInvoiceViewSet(InvoiceEinvoiceEwayActionsMixin, CompanyScopedViewSet):
    queryset = SalesInvoice.objects.select_related("customer").prefetch_related("items__product")
    serializer_class = SalesInvoiceSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="sort",
                required=False,
                type=str,
                enum=["date_desc", "date_asc", "total_desc", "total_asc", "due_desc", "due_asc"],
                description="Register order. due_desc and due_asc place drafts and cancelled bills last.",
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_throttles(self):
        throttles = super().get_throttles()
        if getattr(self, "action", None) == "complete":
            from core.throttles import CompanyRateThrottle

            throttles.append(CompanyRateThrottle(scope="sales_complete"))
        return throttles

    def create(self, request, *args, **kwargs):
        """BB-000610 / BB-000730: durable Idempotency-Key with begin-of-request placeholder."""
        raw_key = (request.headers.get("Idempotency-Key") or "").strip()
        claimed = None
        if raw_key:
            claimed = begin_record(
                company=self.company, scope="sales_invoice_create", raw_key=raw_key,
                fingerprint=request_fingerprint(request),
            )
            if isinstance(claimed, Response):
                return claimed

        created_ok = False
        try:
            response = super().create(request, *args, **kwargs)
            if raw_key and response.status_code == status.HTTP_201_CREATED:
                data = getattr(response, "data", None) or {}
                if isinstance(data, dict) and isinstance(data.get("success"), bool) and "data" in data:
                    data = data.get("data") or {}
                created_id = data.get("id") if isinstance(data, dict) else ""
                # The invoice is committed: never release the key past this point.
                created_ok = True
                store_record(
                    company=self.company,
                    scope="sales_invoice_create",
                    raw_key=raw_key,
                    response=response,
                    resource_id=str(created_id or ""),
                )
            return response
        finally:
            # Release in-flight placeholder if create did not complete successfully.
            if raw_key and claimed is not None and not isinstance(claimed, Response) and not created_ok:
                release_record(
                    company=self.company, scope="sales_invoice_create", raw_key=raw_key
                )

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action == "pos_checkout":
            return [
                IsAuthenticated(),
                HasCompany(),
                SubscriptionWritesAllowed(),
                CanCreateSales(),
                CanCreatePayments(),
            ]
        if action == "record_payment":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreatePayments()]
        if action == "profit_details":
            return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]
        if action == "bulk_pdf_zip_download":
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        if action in (
            "create", "complete", "update", "partial_update", "destroy", "share",
            "bulk_pdf_zip", "repeat_last", "public_link", "revoke_public_link",
        ):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        if action in (
            "list", "retrieve", "pdf", "pdf_status", "regenerate_pdf", "thermal_pdf",
            "preview_totals", "preview_pdf", "payment_stats", "hsn_summary", "export_csv",
        ):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        if action == "audit":
            return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]
        if action == "number_series":
            if self.request.method == "GET":
                return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action in (
            "mark_einvoice_generated",
            "mark_eway_generated",
            "submit_einvoice",
            "submit_einvoice_async",
            "amend_filing_identity",
            "cancel_einvoice",
            "submit_eway",
            "cancel_eway",
            "prepare_einvoice",
            "prepare_eway",
        ):
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        allocated = (
            PaymentAllocation.objects.filter(sales_invoice_id=OuterRef("pk"), reversed_at__isnull=True)
            .values("sales_invoice_id")
            .annotate(total=Sum("amount"))
            .values("total")[:1]
        )
        qs = qs.annotate(
            _allocated=Coalesce(
                Subquery(allocated, output_field=DecimalField(max_digits=14, decimal_places=2)),
                Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)),
            )
        )
        # Bulk existence check so SalesInvoiceSerializer.get_return_state can flag a
        # partial return (status stays COMPLETED) without an N+1 query per row.
        qs = qs.annotate(
            _has_completed_return=Exists(
                SalesReturn.objects.filter(
                    sales_invoice_id=OuterRef("pk"), status=SalesReturn.Status.COMPLETED
                )
            )
        )
        if getattr(self, "action", None) == "list":
            from payments.models import GatewayPayment, GatewayPaymentStatus

            qs = qs.annotate(
                _gateway_holding=Exists(
                    GatewayPayment.objects.filter(
                        payment_link__sales_invoice_id=OuterRef("pk"),
                        status=GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
                    )
                ),
                _gateway_captured=Exists(
                    GatewayPayment.objects.filter(
                        payment_link__sales_invoice_id=OuterRef("pk"),
                        status=GatewayPaymentStatus.CAPTURED,
                    )
                ),
            )
        # B2-020: validate before feeding query params to the ORM so bad input
        # is a 400, not a 500 (FieldError / ValidationError / ValueError).
        from datetime import date as _date

        from core.exceptions import BusinessRuleError

        params = self.request.query_params
        status = params.get("status")
        if status:
            if status not in SalesInvoice.Status.values:
                raise BusinessRuleError(f"Unknown status {status!r}.")
            qs = qs.filter(status=status)
        if params.get("customer"):
            try:
                qs = qs.filter(customer_id=int(params["customer"]))
            except (TypeError, ValueError):
                raise BusinessRuleError("customer must be a numeric id.")
        if params.get("invoice_type"):
            qs = qs.filter(invoice_type=params["invoice_type"])
        for key, lookup in (("date_from", "invoice_date__gte"), ("date_to", "invoice_date__lte")):
            raw = params.get(key)
            if raw:
                try:
                    qs = qs.filter(**{lookup: _date.fromisoformat(str(raw)[:10])})
                except ValueError:
                    raise BusinessRuleError(f"{key} must be an ISO date (YYYY-MM-DD).")
        term = (params.get("q") or "").strip()[:100]
        if term:
            qs = qs.filter(
                Q(number__icontains=term)
                | Q(customer__name__icontains=term)
                | Q(customer__phone__icontains=term)
            )
        if getattr(self, "action", None) not in ("list", "payment_stats", "export_csv"):
            return qs
        if "_balance" not in getattr(qs.query, "annotations", {}):
            qs = _annotate_live_settlement(qs)
        if self.action == "payment_stats":
            return qs
        from django.db.models import CharField
        from django.db.models.fields.json import KT
        from django.db.models.functions import Cast

        from planwave.models import ApprovalRequest

        # Postgres has no jsonb = bigint operator, so compare the payload id as text.
        qs = qs.annotate(
            _cancel_approval_pending=Exists(
                ApprovalRequest.objects.annotate(_invoice_ref=KT("payload__invoice")).filter(
                    company_id=OuterRef("company_id"),
                    action="invoice_cancel",
                    status=ApprovalRequest.Status.PENDING,
                    _invoice_ref=Cast(OuterRef("pk"), output_field=CharField()),
                )
            )
        )
        # One bucket, or several joined by commas (UNPAID,PARTIAL is every bill with money due).
        buckets = [
            part for part in (p.strip().upper() for p in (params.get("payment_status") or "").split(","))
            if part in ("PAID", "PARTIAL", "UNPAID")
        ]
        if buckets:
            qs = _apply_payment_status(qs, buckets)
        if (params.get("overdue") or "").lower() in ("1", "true", "yes"):
            from django.utils import timezone

            qs = qs.filter(
                status=SalesInvoice.Status.COMPLETED, due_date__lt=timezone.localdate(), _balance__gt=0,
            )
        return self._order_invoice_list(qs, params.get("sort"))

    def _order_invoice_list(self, qs, raw_sort):
        sort = (raw_sort or "date_desc").strip() or "date_desc"
        allowed = {
            "date_desc": ("-invoice_date", "-id"),
            "date_asc": ("invoice_date", "id"),
            "total_desc": ("-grand_total", "-id"),
            "total_asc": ("grand_total", "id"),
        }
        if sort in ("due_desc", "due_asc"):
            from django.db.models import Case, When

            money = DecimalField(max_digits=14, decimal_places=2, null=True)
            qs = qs.annotate(
                _due_sort=Case(
                    When(status__in=NO_BALANCE_STATUSES, then=Value(None)),
                    default=F("_balance"),
                    output_field=money,
                )
            )
            direction = F("_due_sort").desc(nulls_last=True) if sort == "due_desc" else F("_due_sort").asc(nulls_last=True)
            return qs.order_by(direction, "id")
        if sort not in allowed:
            raise BusinessRuleError("Unknown sort.")
        return qs.order_by(*allowed[sort])

    def get_serializer(self, *args, **kwargs):
        # CR-016: attach CN/DN-aware outstanding for list rows in one bulk query.
        if self.action == "list" and args and kwargs.get("many", True):
            from decimal import Decimal

            from ledgers.services import LedgerService

            instances = args[0]
            try:
                rows = list(instances) if not isinstance(instances, list) else instances
            except TypeError:
                rows = None
            if rows is not None and rows and hasattr(rows[0], "pk"):
                ids = [r.pk for r in rows if getattr(r, "pk", None)]
                outstanding = LedgerService.bulk_sales_invoice_outstanding(self.company, ids)
                for row in rows:
                    # Prefer the annotation the payment filter and due sort use,
                    # floored the same way as the ledger helper, so the Due column
                    # cannot disagree with those queries.
                    if getattr(row, "_balance", None) is not None and row.status in OPEN_RECEIVABLE_STATUSES:
                        row._list_outstanding = Decimal(str(row._balance))
                    else:
                        row._list_outstanding = outstanding.get(row.pk, Decimal("0"))
                args = (rows,) + args[1:]
                kwargs["many"] = True
        return super().get_serializer(*args, **kwargs)

    def perform_destroy(self, instance):
        if instance.status != SalesInvoice.Status.DRAFT:
            raise BusinessRuleError("Only draft invoices can be deleted; use Cancel instead.")
        from core.models import IdempotencyRecord

        IdempotencyRecord.objects.filter(
            company=self.company,
            resource_id=str(instance.pk),
        ).delete()
        from django.db import transaction

        from .notes_services import SalesNotesService

        with transaction.atomic():
            # A draft made by converting an order took quantity from it: give that back.
            SalesNotesService.release_order_conversion(
                getattr(instance, "source_order", None), instance.items.all(), unlink_invoice_id=instance.pk,
            )
            from .models import QuotationConversion
            from .quotation_conversions import QuotationConversionService

            QuotationConversionService.release_for_invoice(
                instance, self.request.user, QuotationConversion.ReleaseReason.DRAFT_DELETED
            )
            super().perform_destroy(instance)

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        # UXW2B-004: SalesInvoice.complete() assigns the real number from the
        # GSTIN-keyed series (gstin=invoice.company_gstin.gstin), but this preview
        # was peeking the un-keyed default series — showing "INV-00001" while the
        # actual save used e.g. "INV-2627-F1Z5-00011". Preview with the company's
        # current primary GSTIN so it resolves the same series completion will use.
        gstin = resolve_series_gstin(company)
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "SALES_INVOICE", gstin=gstin))
        try:
            data = DocumentNumberService.configure(
                company,
                "SALES_INVOICE",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
                gstin=gstin,
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    @action(detail=False, methods=["post"], url_path="repeat-last")
    def repeat_last(self, request):
        """Repeat-Last-Invoice: copy a customer's most recently completed
        invoice into a new, fully editable DRAFT for the same customer."""
        customer_id = request.data.get("customer")
        if not customer_id:
            raise BusinessRuleError("customer is required.")
        try:
            customer = Customer.objects.get(pk=int(customer_id), company=self.company)
        except (Customer.DoesNotExist, TypeError, ValueError):
            raise BusinessRuleError("customer is invalid for this company.")
        draft = SalesService.repeat_last_invoice(self.company, customer, request.user)
        return Response(self.get_serializer(draft).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="pos-checkout")
    def pos_checkout(self, request):
        """CR-003: Atomic POS checkout in a single database transaction.
        Creates draft invoice, completes invoice, creates receipt, and allocates.
        """
        def _execute():
            from django.db import transaction

            with transaction.atomic():
                raw_invoice = request.data.get("invoice") or request.data
                invoice_serializer = self.get_serializer(data=raw_invoice)
                invoice_serializer.is_valid(raise_exception=True)
                invoice = invoice_serializer.save(
                    company=self.company,
                    created_by=request.user,
                    updated_by=request.user,
                )
                from sales.pos_policy import apply_pos_invoice_rules, resolve_bank
                from sales.pos_shift import assert_cash_shift, stamp_receipt

                payment_preview = request.data.get("payment") or {}
                splits_preview = request.data.get("payments")
                terminal_id = str(request.data.get("terminal_id") or "")[:64]
                terminal_label = str(request.data.get("terminal_label") or "")[:64]
                invoice.terminal_id = terminal_id
                invoice.terminal_label = terminal_label
                invoice.pos_offline = bool(request.data.get("offline_credit"))
                invoice.pos_outage_id = str(request.data.get("outage_id") or "")[:64]
                salesperson = request.data.get("salesperson")
                if salesperson not in (None, ""):
                    from accounts.models import CompanyUser

                    if not str(salesperson).isdigit() or not CompanyUser.objects.filter(
                        company=self.company, user_id=int(salesperson), is_active=True,
                    ).exists():
                        raise BusinessRuleError("The salesperson is not an active user of this company.")
                    invoice.salesperson_id = int(salesperson)
                invoice.save(update_fields=[
                    "terminal_id", "terminal_label", "pos_offline", "pos_outage_id", "salesperson", "updated_at",
                ])
                if isinstance(splits_preview, list) and len(splits_preview) >= 2:
                    tender_modes = [str((part or {}).get("mode") or "") for part in splits_preview]
                else:
                    tender_modes = [str(payment_preview.get("mode") or "CASH")]
                open_shift = assert_cash_shift(self.company, request.user, terminal_id, tender_modes)
                if (request.data.get("offline") or invoice.pos_offline) and request.data.get("shift_id") not in (None, ""):
                    from accounting.models import CashShiftRegister

                    recorded = CashShiftRegister.objects.filter(
                        company=self.company, pk=request.data.get("shift_id"),
                    ).first()
                    if recorded is None or recorded.status != CashShiftRegister.Status.OPEN:
                        raise BusinessRuleError(
                            "The till that took this offline bill is closed. Review the bill before posting.",
                            code="pos_shift_closed",
                        )
                    open_shift = recorded
                offline_sync = bool(request.data.get("offline") or request.data.get("offline_credit"))
                apply_pos_invoice_rules(
                    invoice,
                    payment=payment_preview,
                    splits=splits_preview,
                    owner_pin=str(request.data.get("owner_pin") or ""),
                    expired_reason=str(request.data.get("expired_lot_reason") or ""),
                    user=request.user,
                    offline=offline_sync,
                    credit_cached_at=request.data.get("credit_cached_at"),
                )

                gst_guard_override_reason = request.data.get("gst_guard_override_reason") or None
                confirm_blank_pos = str(
                    request.data.get("confirm_blank_pos")
                    or (raw_invoice or {}).get("confirm_blank_pos")
                    or ""
                ).lower() in ("1", "true", "yes")
                pin_approved = bool(getattr(invoice, "_pos_owner_pin_ok", False))
                below_reason = str(request.data.get("below_cost_override_reason") or "")
                if pin_approved and not below_reason:
                    below_reason = "Owner PIN at the counter"
                completed, _warnings = SalesService.complete(
                    invoice,
                    user=request.user,
                    gst_guard_override_reason=gst_guard_override_reason,
                    confirm_blank_pos=confirm_blank_pos,
                    below_cost_override_reason=below_reason,
                    below_cost_owner_approved=pin_approved,
                    pharmacy_patient=str(request.data.get("pharmacy_patient") or ""),
                    pharmacy_prescriber=str(request.data.get("pharmacy_prescriber") or ""),
                    pharmacy_registration=str(request.data.get("pharmacy_registration") or ""),
                    pharmacy_prescription=str(request.data.get("pharmacy_prescription") or ""),
                    pharmacy_prescription_file=request.data.get("pharmacy_prescription_file"),
                )
                apply_raw = request.data.get("apply_advance")
                if apply_raw not in (None, "", False, 0, "0"):
                    from decimal import Decimal

                    from ledgers.services import LedgerService
                    from sales.pos_advance import apply_customer_advance

                    if str(apply_raw).lower() in ("all", "true", "1"):
                        advance_target = LedgerService.sales_invoice_outstanding(completed)
                    else:
                        advance_target = Decimal(str(apply_raw))
                    apply_customer_advance(completed, advance_target, request.user)

                payment_data = request.data.get("payment")
                splits = request.data.get("payments")
                receipt_data = None
                if isinstance(splits, list) and len(splits) >= 2:
                    from decimal import Decimal
                    from payments.models import PaymentMode
                    from payments.serializers import CustomerReceiptSerializer
                    from payments.services import PaymentService, cheque_fields_from_payload

                    from ledgers.services import LedgerService

                    grand_total = Decimal(str(completed.grand_total or 0))
                    due = Decimal(str(LedgerService.sales_invoice_outstanding(completed) or 0)).quantize(Decimal("0.01"))
                    parts = []
                    for part in splits:
                        parts.append(Decimal(str((part or {}).get("amount") or 0)))
                    split_total = sum(parts, Decimal("0"))
                    confirm_split_mismatch = str(
                        request.data.get("confirm_totals_mismatch")
                        or (payment_data or {}).get("confirm_totals_mismatch")
                        or ""
                    ).lower() in ("1", "true", "yes")
                    drift = (split_total - due).quantize(Decimal("0.01"))
                    if drift > Decimal("0.05") and apply_raw not in (None, "", False, 0, "0"):
                        overflow = drift
                        for idx in range(len(parts) - 1, -1, -1):
                            if overflow <= 0:
                                break
                            take = min(parts[idx], overflow)
                            parts[idx] = (parts[idx] - take).quantize(Decimal("0.01"))
                            overflow = (overflow - take).quantize(Decimal("0.01"))
                        split_total = sum(parts, Decimal("0"))
                        drift = (split_total - due).quantize(Decimal("0.01"))
                    if drift > Decimal("0.05"):
                        raise BusinessRuleError(
                            f"Split payments add up to {split_total}, more than the "
                            f"{due} still due."
                        )
                    if abs(drift) > Decimal("0.05") and not confirm_split_mismatch:
                        exc = BusinessRuleError(
                            (
                                f"Till total changed from {split_total} to {due}. "
                                "Re-confirm before completing."
                            ),
                            code="pos_totals_mismatch",
                            extra={
                                "confirm_codes": ["pos_totals_mismatch"],
                                "client_total": str(split_total),
                                "server_total": str(due),
                            },
                        )
                        exc.status_code = status.HTTP_409_CONFLICT
                        raise exc
                    if drift != 0 and abs(drift) <= Decimal("0.05"):
                        # Rounding drift: absorb it in the last non-zero part so the
                        # receipts foot to the bill and no allocation overshoots it.
                        for idx in range(len(parts) - 1, -1, -1):
                            if parts[idx] > 0:
                                parts[idx] = (parts[idx] - drift).quantize(Decimal("0.01"))
                                break
                    posted = []
                    for part, amount in zip(splits, parts):
                        if amount <= 0:
                            continue
                        mode_str = str((part or {}).get("mode") or "CASH").upper()
                        try:
                            mode = PaymentMode(mode_str)
                        except ValueError as exc:
                            raise BusinessRuleError(
                                f"Unknown payment mode '{mode_str}'."
                            ) from exc
                        bank_account = None
                        if mode_str in ("UPI", "CARD", "BANK", "CHEQUE"):
                            bank_account = resolve_bank(self.company, mode_str)
                        receipt = PaymentService.create_receipt(
                            company=self.company,
                            customer=completed.customer,
                            amount=amount,
                            mode=mode,
                            receipt_date=completed.invoice_date,
                            reference=(part or {}).get("reference", ""),
                            notes=(part or {}).get("notes") or "",
                            user=request.user,
                            bank_account=bank_account,
                            **cheque_fields_from_payload(part or {}, company=self.company),
                        )
                        PaymentService.allocate_receipt(
                            receipt=receipt,
                            sales_invoice=completed,
                            amount=amount,
                            user=request.user,
                        )
                        stamp_receipt(receipt, open_shift)
                        posted.append(CustomerReceiptSerializer(receipt).data)
                    receipt_data = posted[0] if posted else None
                elif payment_data:
                    from decimal import Decimal
                    from payments.models import PaymentMode
                    from payments.serializers import CustomerReceiptSerializer
                    from payments.services import PaymentService, cheque_fields_from_payload

                    tendered = payment_data.get("tendered_amount")
                    grand_total = Decimal(str(completed.grand_total or 0))
                    raw_amount = payment_data.get("amount")
                    # A short-collect of ₹0 is a deliberate choice (see the totals-
                    # mismatch reconciliation dialog) and must not be upgraded to
                    # the full total just because 0 is falsy.
                    requested = Decimal(str(raw_amount)) if raw_amount is not None else grand_total
                    # CR-003: at a retail counter the recorded receipt is what is
                    # kept against the sale — never more than the invoice total.
                    # Anything the customer hands over beyond that is change given
                    # back in cash, not an unallocated advance parked on the
                    # walk-in customer's ledger (GL 2300). A smaller `amount` is a
                    # legitimate part-payment and is left as-is.
                    amount = min(requested, grand_total)
                    from ledgers.services import LedgerService

                    still_open = Decimal(str(LedgerService.sales_invoice_outstanding(completed) or 0))
                    amount = min(amount, still_open)
                    notes = payment_data.get("notes") or ""
                    tendered_dec = Decimal(str(tendered)) if tendered is not None else requested
                    # With an advance applied the customer owes less than the bill.
                    change = tendered_dec - min(grand_total, still_open)
                    if change > 0:
                        notes = f"Tendered: ₹{tendered_dec}, Change: ₹{change}. {notes}".strip()
                    elif tendered and tendered_dec != amount:
                        notes = f"Tendered: ₹{tendered_dec}. {notes}".strip()

                    client_total = payment_data.get("expected_total") or payment_data.get("client_total")
                    confirm_mismatch = str(
                        payment_data.get("confirm_totals_mismatch")
                        or request.data.get("confirm_totals_mismatch")
                        or ""
                    ).lower() in ("1", "true", "yes")
                    if client_total not in (None, ""):
                        displayed = Decimal(str(client_total))
                        if abs(displayed - grand_total) > Decimal("0.05") and not confirm_mismatch:
                            exc = BusinessRuleError(
                                (
                                    f"Till total changed from {displayed} to {grand_total}. "
                                    "Re-confirm before completing."
                                ),
                                code="pos_totals_mismatch",
                                extra={
                                    "confirm_codes": ["pos_totals_mismatch"],
                                    "client_total": str(displayed),
                                    "server_total": str(grand_total),
                                },
                            )
                            exc.status_code = status.HTTP_409_CONFLICT
                            raise exc

                    mode_str = str(payment_data.get("mode") or "CASH").upper()
                    try:
                        mode = PaymentMode(mode_str)
                    except ValueError as exc:
                        raise BusinessRuleError(f"Unknown payment mode '{mode_str}'.") from exc
                    if mode not in (
                        PaymentMode.CASH, PaymentMode.CREDIT, PaymentMode.UPI,
                        PaymentMode.CARD, PaymentMode.BANK, PaymentMode.CHEQUE,
                    ):
                        raise BusinessRuleError(f"Unknown payment mode '{mode_str}'.")

                    # Cash stays on ledger 1100. Bank modes use the saved POS
                    # account, never a bank id the browser sent.
                    bank_account = None
                    if mode == PaymentMode.CREDIT:
                        amount = Decimal("0")
                    elif mode_str in ("UPI", "CARD", "BANK", "CHEQUE"):
                        bank_account = resolve_bank(self.company, mode_str)

                    # A short-collect of ₹0 is a deliberate "collect nothing
                    # now" choice — leave the invoice fully unpaid rather than
                    # creating a ₹0 receipt (which PaymentService itself
                    # rejects: "Receipt amount must be greater than zero").
                    # Cash handed over above the amount kept is change, not an advance.
                    change_given = Decimal("0")
                    if mode == PaymentMode.CASH:
                        change_given = max(tendered_dec - amount, Decimal("0"))
                    if amount > 0:
                        receipt = PaymentService.create_receipt(
                            company=self.company,
                            customer=completed.customer,
                            amount=amount,
                            mode=mode,
                            receipt_date=completed.invoice_date,
                            reference=payment_data.get("reference", ""),
                            notes=notes,
                            user=request.user,
                            bank_account=bank_account,
                            tendered=tendered_dec,
                            change_given=change_given,
                            **cheque_fields_from_payload(payment_data, company=self.company),
                        )
                        PaymentService.allocate_receipt(
                            receipt=receipt,
                            sales_invoice=completed,
                            amount=min(amount, completed.grand_total),
                            user=request.user,
                        )
                        stamp_receipt(receipt, open_shift)
                        receipt_data = CustomerReceiptSerializer(receipt).data
                        if mode == PaymentMode.UPI:
                            from core.services.audit import AuditService

                            AuditService.log(
                                company=self.company,
                                user=request.user,
                                action="UPDATE",
                                entity_type="SalesInvoice",
                                entity_id=str(completed.pk),
                                description=f"UPI payment received {amount} on {completed.number}",
                                metadata={"amount": str(amount), "mode": "UPI"},
                            )

                invoice_data = self.get_serializer(completed).data
                invoice_data["gst_guard_warnings"] = getattr(completed, "_gst_guard_warnings", [])
                return Response({
                    "invoice": invoice_data,
                    "receipt": receipt_data,
                }, status=status.HTTP_201_CREATED)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="pos_checkout",
            build=_execute,
        )

    def _preview_bundle(self, request):
        """Authoritative totals for a draft that has not been saved."""
        company = self.company
        customer = None
        customer_id = request.data.get("customer")
        party_state = company.state or ""
        party_gstin = ""
        if customer_id:
            try:
                customer = Customer.objects.get(pk=customer_id, company=company)
            except Customer.DoesNotExist as exc:
                raise BusinessRuleError("Invalid customer.") from exc
            party_state = customer.state or party_state
            party_gstin = customer.gstin or ""

        invoice_type = request.data.get("invoice_type") or SalesInvoice.InvoiceType.GST
        tax_enabled = _tax_enabled(invoice_type)
        from accounts.models import CompanyGstin

        seller_state = company.state or ""
        seller_gstin = company.gstin or ""
        stamp = None
        gstin_id = request.data.get("company_gstin")
        if gstin_id:
            stamp = CompanyGstin.objects.filter(pk=gstin_id, company=company, is_active=True).first()
            if stamp is None:
                raise BusinessRuleError("Invalid company GSTIN.")
            seller_state = stamp.state or seller_state
            seller_gstin = stamp.gstin or seller_gstin

        product_ids = []
        for raw in request.data.get("items") or []:
            pid = raw.get("product")
            if pid:
                product_ids.append(pid)
        products_by_id = {
            p.pk: p for p in Product.objects.filter(pk__in=product_ids, company=company)
        }
        include_margin = CanViewFinancialReports().has_permission(request, self)
        warehouse = None
        warehouse_id = request.data.get("warehouse")
        if include_margin and warehouse_id:
            from inventory.models import Warehouse

            warehouse = Warehouse.objects.filter(pk=warehouse_id, company=company).first()
        preview = build_totals_preview(
            company=company,
            party_state=party_state,
            party_gstin=party_gstin,
            data=request.data,
            products_by_id=products_by_id,
            default_price_attr="selling_price",
            tax_enabled=tax_enabled,
            seller_state=seller_state,
            seller_gstin=seller_gstin,
            include_margin=include_margin,
            warehouse=warehouse,
        )
        return {
            "company": company,
            "customer": customer,
            "products_by_id": products_by_id,
            "preview": preview,
            "invoice_type": invoice_type,
            "stamp": stamp,
        }

    @action(detail=False, methods=["post"], url_path="preview-totals")
    def preview_totals(self, request):
        """Authoritative totals preview without persisting (Phase 1 / A-03)."""
        return Response(self._preview_bundle(request)["preview"])

    @action(detail=False, methods=["post"], url_path="preview-pdf")
    def preview_pdf(self, request):
        """Sample A4 PDF of an unsaved draft, from the same renderer as the saved file."""
        import io
        from datetime import datetime
        from decimal import Decimal
        from types import SimpleNamespace

        from django.http import FileResponse
        from django.utils import timezone

        from .pdf.gst_tax_invoice import render_gst_tax_invoice

        raw_items = [r for r in (request.data.get("items") or []) if isinstance(r, dict)]
        if len(raw_items) > 300:
            raise BusinessRuleError("A preview can show at most 300 lines.")
        # Check the numbers before the tax engine sees them; it would crash on text.
        for raw in raw_items:
            for field in ("quantity", "unit_price", "unit_price_inclusive", "mrp", "discount_percent", "gst_rate"):
                value = raw.get(field)
                if value in (None, ""):
                    continue
                try:
                    if not Decimal(str(value)).is_finite():
                        raise ValueError
                except Exception:  # noqa: BLE001
                    raise BusinessRuleError("A quantity or price is not a number.") from None
        bundle = self._preview_bundle(request)
        preview = bundle["preview"]
        products_by_id = bundle["products_by_id"]
        tax_items = list(preview.get("items") or [])
        # Tax rows are matched to lines by position. If the tax engine dropped a row,
        # the taxes would land on the wrong line, so refuse rather than guess.
        if len(tax_items) != len(raw_items):
            raise BusinessRuleError("Some lines could not be previewed. Check each item.")

        def _num(value, default="0"):
            try:
                number = Decimal(str(value if value not in (None, "") else default))
            except Exception:  # noqa: BLE001
                raise BusinessRuleError("A quantity or price is not a number.") from None
            if not number.is_finite():
                raise BusinessRuleError("A quantity or price is not a number.")
            return number

        lines = []
        for raw, tax in zip(raw_items, tax_items):
            try:
                product = products_by_id.get(int(raw.get("product")))
            except (TypeError, ValueError):
                product = None
            if product is None:
                continue
            unit = getattr(product, "unit", None)
            unit_price = raw.get("unit_price")
            if unit_price is None:
                unit_price = raw.get("unit_price_inclusive") or getattr(product, "selling_price", 0)
            lines.append(SimpleNamespace(
                product=product,
                description=raw.get("description") or product.name,
                quantity=_num(raw.get("quantity")),
                unit_price=_num(unit_price),
                unit_name=getattr(unit, "name", None) or "PCS",
                mrp=_num(raw.get("mrp") or getattr(product, "mrp", 0) or 0),
                hsn_code=raw.get("hsn_code") or getattr(product, "hsn_code", "") or "",
                discount_percent=_num(raw.get("discount_percent")),
                line_total=tax.get("line_total") or 0,
                taxable_amount=tax.get("taxable_amount") or 0,
                cgst=tax.get("cgst") or 0,
                sgst=tax.get("sgst") or 0,
                igst=tax.get("igst") or 0,
                cess=tax.get("cess") or 0,
                gst_rate=tax.get("gst_rate") or 0,
                supply_nature=raw.get("supply_nature") or "TAXABLE",
                batch_no=raw.get("batch_no") or "",
                exp_date=None,
            ))
        raw_date = request.data.get("invoice_date")
        if hasattr(raw_date, "year"):
            invoice_date = raw_date
        elif raw_date:
            try:
                invoice_date = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d").date()
            except ValueError as exc:
                raise BusinessRuleError("Invoice date must be YYYY-MM-DD.") from exc
        else:
            invoice_date = timezone.localdate()
        customer = bundle["customer"]
        if customer is None:
            customer = SimpleNamespace(
                name="—", billing_address="", shipping_address="", gstin="", phone="", state="",
            )
        invoice = SimpleNamespace(
            pk=None,
            company=bundle["company"],
            customer=customer,
            company_gstin=bundle["stamp"],
            invoice_type=bundle["invoice_type"],
            number="",
            invoice_date=invoice_date,
            due_date=None,
            grand_total=preview.get("grand_total") or 0,
            taxable_total=preview.get("taxable_total") or 0,
            round_off=preview.get("round_off") or 0,
            additional_charges=request.data.get("additional_charges") or 0,
            invoice_discount=request.data.get("invoice_discount") or 0,
            invoice_discount_mode=preview.get("invoice_discount_mode") or "AFTER_TAX",
            custom_fields=request.data.get("custom_fields") or {},
            include_payment_qr=bool(request.data.get("include_payment_qr")),
            include_bank_details=bool(request.data.get("include_bank_details")),
            include_terms=bool(request.data.get("include_terms")),
            terms_text=request.data.get("terms_text") or "",
            irn="",
            einvoice_qr="",
            einvoice_status="",
            filing_place_of_supply="",
            tcs_amount=preview.get("tcs_amount") or 0,
            amount_received=Decimal("0"),
            _preview_items=lines,
        )
        content = render_gst_tax_invoice(invoice, copy="ORIGINAL")
        return FileResponse(
            io.BytesIO(content),
            as_attachment=False,
            filename="invoice-preview.pdf",
            content_type="application/pdf",
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        def _run():
            from decimal import Decimal, InvalidOperation

            from django.db import transaction

            from core.permissions import get_company_user
            from payments.services import PaymentService, cheque_fields_from_payload

            confirm_rcm = str(request.data.get("confirm_sales_rcm") or "").lower() in (
                "1", "true", "yes",
            )
            confirm_blank_pos = str(request.data.get("confirm_blank_pos") or "").lower() in (
                "1", "true", "yes",
            )
            confirm_gstin_total = str(request.data.get("confirm_gstin_total_change") or "").lower() in (
                "1", "true", "yes",
            )
            confirm_missing_licence = str(request.data.get("confirm_missing_licence") or "").lower() in (
                "1", "true", "yes",
            )
            gst_guard_override_reason = request.data.get("gst_guard_override_reason") or None
            unlock_code = request.data.get("unlock_code") or None
            below_cost_reason = str(request.data.get("below_cost_override_reason") or "")
            pharmacy_patient = request.data.get("patient_name") or ""
            pharmacy_prescriber = request.data.get("prescriber_name") or ""
            pharmacy_registration = request.data.get("prescriber_registration") or ""
            pharmacy_prescription = request.data.get("prescription_note") or ""
            raw_received = request.data.get("amount_received")
            try:
                tendered = Decimal(str(raw_received if raw_received not in (None, "") else 0))
            except InvalidOperation as exc:
                raise BusinessRuleError("Amount received is not a number.") from exc
            if not tendered.is_finite():
                raise BusinessRuleError("Amount received is not a number.")
            if tendered < 0:
                raise BusinessRuleError("Amount received cannot be negative.")
            mode = str(request.data.get("payment_mode") or "CASH").upper()
            # Credit is not a receipt. A tender on any other mode needs payments permission
            # before the invoice commits, so a sales-only user cannot leave it unpaid.
            collects = tendered > 0 and mode != "CREDIT"
            if collects:
                membership = get_company_user(request)
                allowed = (
                    membership is not None
                    and membership.role != "VIEWER"
                    and (membership.role == "OWNER" or membership.can_create_payments)
                )
                if not allowed:
                    # Retryable: the same offline draft must still be able to
                    # collect once this user is allowed to take payments.
                    raise BusinessRuleError(
                        "Payments create permission required.",
                        code="try_again",
                    )
            cheque_fields = cheque_fields_from_payload(request.data, company=self.company)
            with transaction.atomic():
                invoice, warnings = SalesService.complete(
                    self.get_object(),
                    request.user,
                    confirm_sales_rcm=confirm_rcm,
                    confirm_blank_pos=confirm_blank_pos,
                    confirm_gstin_total_change=confirm_gstin_total,
                    confirm_missing_licence=confirm_missing_licence,
                    gst_guard_override_reason=gst_guard_override_reason,
                    unlock_code=unlock_code,
                    below_cost_override_reason=below_cost_reason,
                    pharmacy_patient=pharmacy_patient,
                    pharmacy_prescriber=pharmacy_prescriber,
                    pharmacy_registration=pharmacy_registration,
                    pharmacy_prescription=pharmacy_prescription,
                )
                if collects:
                    try:
                        PaymentService.settle_completed_invoice_payment(
                            invoice=invoice,
                            user=request.user,
                            tendered=tendered,
                            mode=mode,
                            cheque_fields=cheque_fields,
                        )
                    except BusinessRuleError as exc:
                        # The invoice, stock, journals, and series number roll back
                        # with this savepoint. Release the idempotency key so the
                        # same gesture can be retried. Pass a plain string: an
                        # ErrorDetail keeps its original code and would be stored.
                        raise BusinessRuleError(str(exc.detail), code="try_again") from exc
            data = self.get_serializer(invoice).data
            data["warnings"] = warnings
            data["gst_guard_warnings"] = getattr(invoice, "_gst_guard_warnings", [])
            return Response(data)

        # Confirm flags are the same user intent as the first attempt. A timeout
        # retry must reuse the key; a new key would post a second number.
        request._idempotency_ignore_keys = frozenset({
            "confirm_sales_rcm", "confirmSalesRcm",
            "confirm_blank_pos", "confirmBlankPos",
            "confirm_gstin_total_change", "confirmGstinTotalChange",
            "confirm_missing_licence", "confirmMissingLicence",
            "confirm_no_rcm", "confirmNoRcm",
        })
        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="sales_invoice_complete",
            build=_run,
        )

    @action(detail=True, methods=["get"], url_path="audit")
    def audit(self, request, pk=None):
        """D-03: company-scoped invoice audit timeline (Owner/CA)."""
        from core.models import AuditEvent
        from core.serializers import AuditEventSerializer

        invoice = self.get_object()
        pk_s = str(invoice.pk)
        events = (
            AuditEvent.objects.filter(company=invoice.company, entity_id=pk_s)
            .filter(entity_type__in=["SalesInvoice", "salesinvoice", "sales_invoice"])
            .select_related("user")
            .order_by("-created_at")[:200]
        )
        return Response(AuditEventSerializer(events, many=True).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reason = (
            request.data.get("reason")
            or request.data.get("cancel_reason")
            or request.data.get("cancelReason")
            or ""
        )
        current = self.get_object()
        from django.db import transaction

        # Spending the approval and cancelling are one unit: a refused cancel (locked period, a
        # business rule) must give the approval back instead of burning it.
        with transaction.atomic():
            if current.status == SalesInvoice.Status.COMPLETED:
                from planwave.models import ApprovalRequest
                from planwave.services import (
                    consume_action_approval,
                    decide_approval,
                    owner_is_sole_approver,
                    submit_approval,
                )

                approval_id = request.data.get("approval_id")
                if not approval_id:
                    # Asking again after the approver said yes spends that approval.
                    from django.utils import timezone

                    approval_id = ApprovalRequest.objects.filter(
                        company=current.company, action="invoice_cancel", requester=request.user,
                        status=ApprovalRequest.Status.APPROVED, token_used_at__isnull=True,
                        expires_at__gt=timezone.now(), payload__invoice=current.pk,
                    ).order_by("-pk").values_list("pk", flat=True).first()
                approval = consume_action_approval(
                    current.company, approval_id, request.user, "invoice_cancel",
                    invoice=current.pk,
                )
                if approval is None and owner_is_sole_approver(current.company, request.user):
                    pending = submit_approval(
                        company=current.company, action="invoice_cancel", requester=request.user,
                        payload={"invoice": current.pk, "reason": str(reason)},
                    )
                    pending.reason = "Owner is the only approver."
                    pending.save(update_fields=["reason"])
                    decide_approval(pending, approver=request.user, accept=True, owner_exception=True)
                elif approval is None:
                    # Asking again while a request is open reuses it instead of piling up new ones.
                    pending = ApprovalRequest.objects.filter(
                        company=current.company, action="invoice_cancel", requester=request.user,
                        status=ApprovalRequest.Status.PENDING, payload__invoice=current.pk,
                    ).first() or submit_approval(
                        company=current.company, action="invoice_cancel", requester=request.user,
                        payload={"invoice": current.pk, "reason": str(reason)},
                    )
                    return Response({"status": "PENDING", "approval_id": pending.pk}, status=202)
            invoice = SalesService.cancel(current, request.user, reason=str(reason))
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="regenerate-pdf")
    def regenerate_pdf(self, request, pk=None):
        invoice = self.get_object()
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("PDF can only be regenerated for completed invoices.")
        invoice.pdf_status = SalesInvoice.PdfStatus.QUEUED
        invoice.save(update_fields=["pdf_status"])
        safe_delay(generate_invoice_pdf, invoice.pk, company_id=invoice.company_id)
        from insights.telemetry import record_pdf_started

        record_pdf_started(invoice.company, user=request.user)
        invoice.refresh_from_db()
        return Response({"pdf_status": invoice.pdf_status, "pdf_file": invoice.pdf_file_id})

    @extend_schema(responses=InvoicePaymentStatsSerializer)
    @action(detail=False, methods=["get"], url_path="payment-stats")
    def payment_stats(self, request):
        from django.db.models import Count, Sum

        # get_queryset leaves out the payment filter here: the chips count every bucket.
        qs = self.filter_queryset(self.get_queryset())
        qs = qs.filter(status__in=OPEN_RECEIVABLE_STATUSES)
        paid = qs.filter(_balance__lte=0, grand_total__gt=0)
        unpaid = qs.filter(_balance__gt=0, _live_alloc=0, _cn=0, _settle=0)
        partial = qs.filter(_balance__gt=0).filter(
            Q(_live_alloc__gt=0) | Q(_cn__gt=0) | Q(_settle__gt=0)
        )

        def _agg(rows, amount_field):
            data = rows.aggregate(count=Count("id"), amount=Sum(amount_field))
            return {"count": data["count"] or 0, "amount": data["amount"] or 0}

        return Response({
            "paid": _agg(paid, "grand_total"),
            "partial": _agg(partial, "_balance"),
            "unpaid": _agg(unpaid, "_balance"),
        })

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.BINARY})
    @action(detail=False, methods=["get"], url_path="export-csv")
    def export_csv(self, request):
        """The register as a spreadsheet, with the same filters and sort as the list."""
        import csv

        from django.http import HttpResponse

        limit = 5000
        qs = self.filter_queryset(self.get_queryset()).select_related("customer")
        rows = list(qs[: limit + 1])
        truncated = len(rows) > limit
        rows = rows[:limit]
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="sales-register.csv"'
        if truncated:
            response["X-Export-Truncated"] = "1"
        response.write("﻿")
        writer = csv.writer(response)
        writer.writerow(["Date", "Number", "Customer", "Phone", "Status", "Total", "Due", "Due date", "Cancel reason"])

        def _safe(value):
            # A leading = + - @ would run as a formula when the file is opened in a spreadsheet.
            text = "" if value is None else str(value)
            return "'" + text if text[:1] in ("=", "+", "-", "@") else text

        for inv in rows:
            open_bill = inv.status in OPEN_RECEIVABLE_STATUSES
            writer.writerow([
                inv.invoice_date,
                _safe(inv.number or f"Draft #{inv.pk}"),
                _safe(inv.customer.name if inv.customer_id else ""),
                _safe(inv.customer.phone if inv.customer_id else ""),
                inv.status,
                inv.grand_total,
                getattr(inv, "_balance", 0) if open_bill else "",
                inv.due_date or "",
                _safe(inv.cancel_reason),
            ])
        return response

    @action(detail=True, methods=["get"], url_path="hsn-summary")
    def hsn_summary(self, request, pk=None):
        from collections import defaultdict
        from decimal import Decimal

        from reporting.gst_returns_sections import accumulate_hsn_line

        invoice = self.get_object()
        buckets = defaultdict(lambda: {
            "quantity": Decimal("0"), "taxable_value": Decimal("0"),
            "cgst": Decimal("0"), "sgst": Decimal("0"), "igst": Decimal("0"), "cess": Decimal("0"),
        })
        for item in invoice.items.all():
            accumulate_hsn_line(buckets, item)
        rows = [
            {"hsn": k[0], "gst_rate": k[1], "uqc": k[2], **v}
            for k, v in sorted(buckets.items())
        ]
        return Response({"invoice_id": invoice.id, "rows": rows})

    @action(detail=True, methods=["post"], url_path="record-payment")
    def record_payment(self, request, pk=None):
        from decimal import Decimal as D

        invoice = self.get_object()
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Record payment is only for completed invoices.")
        from decimal import InvalidOperation

        try:
            amount = D(str(request.data.get("amount") or 0))
            discount = D(str(request.data.get("discount") or request.data.get("settlement_discount") or 0))
        except (InvalidOperation, ValueError):
            raise BusinessRuleError("Amount and discount must be numbers.") from None
        if not amount.is_finite() or not discount.is_finite():
            raise BusinessRuleError("Amount and discount must be numbers.")
        if amount <= 0:
            raise BusinessRuleError("Amount received must be greater than zero.")
        if discount < 0:
            raise BusinessRuleError("Settlement discount cannot be negative.")
        raw_key = require_idempotency_key(request)
        claimed = begin_record(
            company=invoice.company,
            scope="invoice_record_payment",
            raw_key=raw_key,
            fingerprint=request_fingerprint(request),
        )
        if isinstance(claimed, Response):
            return claimed
        from django.db import transaction

        created_ok = False
        try:
            with transaction.atomic():
                response = self._record_payment_in_transaction(
                    request, invoice, amount, discount,
                )
            # The money is committed. From here the key must never be released,
            # even if storing the replay fails, or a retry would post it twice.
            created_ok = True
            store_record(
                company=invoice.company,
                scope="invoice_record_payment",
                raw_key=raw_key,
                response=response,
                resource_id=str(invoice.pk),
            )
            return response
        finally:
            if claimed is not None and not isinstance(claimed, Response) and not created_ok:
                release_record(
                    company=invoice.company,
                    scope="invoice_record_payment",
                    raw_key=raw_key,
                )

    def _record_payment_in_transaction(self, request, invoice, amount, discount):
        from payments.services import PaymentService, cheque_fields_from_payload

        receipt = PaymentService.create_receipt(
            company=invoice.company,
            customer=invoice.customer,
            amount=amount,
            mode=(request.data.get("mode") or "CASH"),
            receipt_date=request.data.get("payment_date") or request.data.get("paymentDate") or invoice.invoice_date,
            notes=request.data.get("notes") or f"Against {invoice.number or invoice.id}",
            reference=request.data.get("reference") or "",
            user=request.user,
            settlement_discount=discount,
            **cheque_fields_from_payload(request.data, company=invoice.company),
        )
        PaymentService.allocate_receipt(
            receipt=receipt,
            sales_invoice=invoice,
            amount=amount,
            user=request.user,
        )
        return Response(self.get_serializer(invoice).data)

    @extend_schema(request=InvoiceBulkPdfZipRequestSerializer, responses=InvoiceBulkPdfZipSerializer)
    @action(detail=False, methods=["post"], url_path="bulk-pdf-zip")
    def bulk_pdf_zip(self, request):
        import io
        import zipfile

        from django.core.files.base import ContentFile

        from core.models import FileAsset
        from sales.pdf import render_gst_tax_invoice

        ids = request.data.get("ids") or request.data.get("invoice_ids") or []
        try:
            ids = list(dict.fromkeys(int(x) for x in ids))
        except (TypeError, ValueError) as exc:
            raise BusinessRuleError("ids must be a list of invoice ids.") from exc
        if not ids:
            raise BusinessRuleError("Select at least one invoice.")
        if len(ids) > 100:
            raise BusinessRuleError("Bulk download is capped at 100 invoices for the sync path.")
        found = {
            inv.pk: inv
            for inv in SalesInvoice.objects.filter(company=self.company, pk__in=ids).select_related("customer", "company")
        }
        included = []
        skipped = []
        ready = []
        for pk in ids:
            inv = found.get(pk)
            if inv is None:
                # Missing and another company's id look the same. Do not attach a number.
                skipped.append({"id": pk, "reason": "unavailable"})
                continue
            if inv.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
                skipped.append({"id": inv.pk, "number": inv.number or f"Draft #{inv.pk}", "reason": "not_completed"})
                continue
            included.append({"id": inv.pk, "number": inv.number or str(inv.pk)})
            ready.append(inv)
        if not ready:
            raise BusinessRuleError("None of the selected bills have a PDF.")
        buf = io.BytesIO()
        used_names = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for inv in ready:
                content = render_gst_tax_invoice(inv, copy="ORIGINAL")
                # Series like INV/24-25/001 would otherwise unpack into folders.
                stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", str(inv.number or inv.pk)).strip(" .-") or str(inv.pk)
                name = f"{stem}.pdf"
                if name.lower() in used_names:
                    name = f"{stem}-{inv.pk}.pdf"
                used_names.add(name.lower())
                zf.writestr(name, content)
        asset = FileAsset.objects.create(
            company=self.company,
            kind=FileAsset.Kind.EXPORT,
            original_name="invoices.zip",
            content_type="application/zip",
            size=buf.tell(),
            created_by=request.user,
            updated_by=request.user,
        )
        asset.file.save("invoices.zip", ContentFile(buf.getvalue()), save=True)
        url = request.build_absolute_uri(asset.file.url) if asset.file else ""
        return Response({
            "url": url,
            "file_id": asset.id,
            "included": included,
            "skipped": skipped,
        })

    @extend_schema(responses={(200, "application/zip"): OpenApiTypes.BINARY})
    @action(detail=False, methods=["get"], url_path=r"bulk-pdf-zip/(?P<file_id>\d+)")
    def bulk_pdf_zip_download(self, request, file_id=None):
        from django.http import Http404

        from core.models import FileAsset

        # /media/ is internal behind nginx, so the zip is served here, to the user who built it.
        asset = FileAsset.objects.filter(
            company=self.company,
            pk=file_id,
            kind=FileAsset.Kind.EXPORT,
            original_name="invoices.zip",
            created_by=request.user,
        ).first()
        if asset is None or not asset.file:
            raise Http404("The download is no longer available.")
        try:
            handle = asset.file.open("rb")
        except (FileNotFoundError, OSError) as exc:
            raise Http404("The download is no longer available.") from exc
        return FileResponse(handle, as_attachment=True, filename="invoices.zip", content_type="application/zip")

    @action(detail=True, methods=["get"], url_path="pdf-status")
    def pdf_status(self, request, pk=None):
        invoice = self.get_object()
        return Response({"pdf_status": invoice.pdf_status, "pdf_file": invoice.pdf_file_id})

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        import io

        from .pdf import render_gst_tax_invoice

        invoice = self.get_object()
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError(
                "PDF is not ready for this invoice.",
                code=HelpCode.PDF_OR_SHARE_UNAVAILABLE,
            )

        copy = (request.query_params.get("copy") or "ORIGINAL").upper()
        if copy not in ("ORIGINAL", "DUPLICATE", "TRIPLICATE"):
            copy = "ORIGINAL"

        # P0-404: never sync-hang generate_invoice_pdf on download. Clients
        # must poll pdf-status / retry; use regenerate-pdf for FAILED.
        # Orphan READY (flag set but file missing) must re-enqueue or clients
        # spin forever on 409.
        if invoice.pdf_status != SalesInvoice.PdfStatus.READY or not invoice.pdf_file:
            should_enqueue = (
                invoice.pdf_status in (
                    SalesInvoice.PdfStatus.NONE,
                    SalesInvoice.PdfStatus.FAILED,
                )
                or (
                    invoice.pdf_status == SalesInvoice.PdfStatus.READY
                    and not invoice.pdf_file
                )
            )
            if should_enqueue:
                invoice.pdf_status = SalesInvoice.PdfStatus.QUEUED
                invoice.save(update_fields=["pdf_status"])
                safe_delay(generate_invoice_pdf, invoice.pk, company_id=invoice.company_id)
            return Response(
                {
                    "detail": "PDF is generating, retry shortly",
                    "pdf_status": invoice.pdf_status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        from core.models import AuditEvent

        AuditEvent.objects.create(
            company=invoice.company,
            user=request.user,
            action=AuditEvent.Action.CREATE,
            entity_type="SalesInvoicePdf",
            entity_id=str(invoice.pk),
            description="Invoice PDF downloaded",
            metadata={"copy": copy},
        )

        # Extra copies are rendered in memory so the stored file stays ORIGINAL.
        if copy in ("DUPLICATE", "TRIPLICATE"):
            content = render_gst_tax_invoice(invoice, copy=copy)
            return FileResponse(
                io.BytesIO(content),
                as_attachment=True,
                filename=f"{invoice.number or invoice.pk}_{copy.lower()}.pdf",
                content_type="application/pdf",
            )

        return FileResponse(
            invoice.pdf_file.file.open("rb"),
            as_attachment=True,
            filename=invoice.pdf_file.original_name,
        )

    @action(detail=True, methods=["get"], url_path="thermal-pdf")
    def thermal_pdf(self, request, pk=None):
        import io

        from .pdf import render_thermal_receipt

        invoice = self.get_object()
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Thermal receipt is not available for this invoice.")

        width_param = request.query_params.get("width", "80")
        try:
            width_mm = int(width_param)
        except (TypeError, ValueError):
            width_mm = 80
        if width_mm not in (58, 80):
            width_mm = 80

        content = render_thermal_receipt(invoice, width_mm=width_mm)
        return FileResponse(
            io.BytesIO(content),
            as_attachment=True,
            filename=f"{invoice.number or invoice.pk}_thermal_{width_mm}mm.pdf",
            content_type="application/pdf",
        )

    @action(detail=True, methods=["get"], url_path="profit-details")
    def profit_details(self, request, pk=None):
        from sales.profit_details import invoice_profit_details

        return Response(invoice_profit_details(self.get_object()))

    @action(detail=True, methods=["post"], url_path="public-link")
    def public_link(self, request, pk=None):
        from sales.public_links import mint_public_link, public_invoice_url

        link = mint_public_link(self.get_object(), request.user)
        return Response({"url": public_invoice_url(link.token)})

    @action(detail=True, methods=["post"], url_path="public-link/revoke")
    def revoke_public_link(self, request, pk=None):
        from django.utils import timezone

        from sales.models import InvoicePublicLink

        invoice = self.get_object()
        updated = InvoicePublicLink.objects.filter(
            invoice=invoice, revoked_at__isnull=True,
        ).update(revoked_at=timezone.now())
        return Response({"revoked": bool(updated)})

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """Share via Notification Service — email or whatsapp (E4.10)."""
        invoice = self.get_object()
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError(
                "Only completed invoices can be shared.",
                code=HelpCode.PDF_OR_SHARE_UNAVAILABLE,
            )
        channel = (request.data.get("channel") or "").upper()
        if channel not in (Notification.Channel.EMAIL, Notification.Channel.WHATSAPP):
            raise BusinessRuleError("channel must be 'email' or 'whatsapp'.")
        send_from_business = request.data.get("send_from_business_number") in (
            True,
            "true",
            "True",
            "1",
            1,
        )
        # ACT-21: an explicit empty recipient is device share (the user picks the
        # chat). Omitting the key still uses the customer phone so existing
        # Cloud and link callers keep working. sendFromBusinessNumber keeps Cloud.
        if (
            channel == Notification.Channel.WHATSAPP
            and not send_from_business
            and "recipient" in request.data
            and not str(request.data.get("recipient") or "").strip()
        ):
            from sales.public_links import mint_public_link, public_invoice_url
            # The recipient has no login: the text must carry the public page.
            public_url = public_invoice_url(mint_public_link(invoice, request.user).token)
            text = (
                f"Invoice {invoice.number} dated {invoice.invoice_date} from {invoice.company.name}. "
                f"Amount: INR {invoice.grand_total}."
            )
            text = f"{text} View invoice: {public_url}"
            # Not SENT: the picker opening is not delivery. Do not persist WhatsApp status.
            return Response(
                {
                    "mode": "device",
                    "text": text,
                    "document_url": public_url,
                    "status": "OPENED",
                }
            )
        recipient = request.data.get("recipient") or (
            invoice.customer.email if channel == Notification.Channel.EMAIL else invoice.customer.phone
        )
        if not recipient:
            raise BusinessRuleError("No recipient available for this channel.")
        from sales.whatsapp_send import (
            cloud_allowed_for_recipient,
            compose_invoice_whatsapp_body,
            persist_invoice_whatsapp,
        )

        if channel == Notification.Channel.WHATSAPP:
            body = compose_invoice_whatsapp_body(invoice, request)
            subject = "invoice_ready"
            allow_cloud = cloud_allowed_for_recipient(invoice.customer, recipient)
        else:
            from sales.public_links import mint_public_link, public_invoice_url

            view_url = public_invoice_url(mint_public_link(invoice, request.user).token)
            body = (
                f"Invoice {invoice.number} dated {invoice.invoice_date} from {invoice.company.name}. "
                f"Amount: INR {invoice.grand_total}. "
                f"View and download the invoice: {view_url}"
            )
            subject = f"Invoice {invoice.number}"
            allow_cloud = False
        notification = NotificationService.send(
            company=invoice.company,
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            user=request.user,
            allow_cloud=allow_cloud,
        )
        from core.serializers import NotificationSerializer

        data = NotificationSerializer(notification).data
        data["pdf_url"] = f"/api/v1/sales/invoices/{invoice.pk}/pdf/"
        # BB-000743: mode for WhatsApp honesty (cloud vs link / fallback).
        if channel == Notification.Channel.WHATSAPP:
            persist_invoice_whatsapp(invoice, notification)
            data["mode"] = getattr(notification, "delivery_mode", None) or (
                "cloud" if notification.status == Notification.Status.SENT else "link"
            )
            data["whatsapp_send_status"] = invoice.whatsapp_send_status
        return Response(data)


QUOTATION_ORDERING = {
    "quotation_date": ("quotation_date", "id"),
    "valid_until": ("valid_until", "id"),
    "grand_total": ("grand_total", "id"),
    "number": ("number", "id"),
    "customer__name": ("customer__name", "id"),
}


@extend_schema_view(
    partial_update=extend_schema(
        description=(
            "Edit a draft quotation. Error codes: `quotation_not_editable` (not a draft), "
            "`quotation_lines_locked` (part of it was converted, so `items` cannot be sent) and "
            "`quotation_fields_locked` (only validity, notes, terms, delivery address, salesperson "
            "and channel may change after a partial conversion; the response lists the blocked fields), "
            "`customer_blocked`."
        )
    ),
    update=extend_schema(
        description=(
            "Replace a draft quotation. Error codes: `quotation_not_editable`, `quotation_lines_locked`, "
            "`quotation_fields_locked`, `customer_blocked`."
        )
    ),
    destroy=extend_schema(description="Delete an unconverted draft. Error code: `quotation_not_deletable`."),
)
class QuotationViewSet(CompanyScopedViewSet):
    queryset = Quotation.objects.select_related("customer", "salesman").prefetch_related(
        "items__product",
        Prefetch(
            "conversions",
            queryset=QuotationConversion.objects.select_related("sales_order", "sales_invoice"),
        ),
    )
    serializer_class = QuotationSerializer

    LIFECYCLE_ACTIONS = ("mark_sent", "mark_accepted", "mark_rejected", "reopen_for_changes")

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action in ("number_series", "reopen", "reopen_closed"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), IsOwner()]
        if action in ("cancel", "cancel_expired", "close_remaining"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in (
            "create", "update", "partial_update", "destroy", "convert", "convert_to_order", "convert_chain",
            "share", "public_link", "revoke_public_link", "duplicate",
            *self.LIFECYCLE_ACTIONS,
        ):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        if action == "revisions":
            # D-12: what was sent to the customer is for people who can change quotes.
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        if action in ("list", "retrieve", "pdf"):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        from datetime import date as _date

        qs = super().get_queryset()
        if getattr(self, "action", None) != "list":
            return qs
        params = self.request.query_params
        status_param = (params.get("status") or "").strip().upper()
        if status_param == "OPEN":
            qs = qs.live()
        elif status_param:
            if status_param not in Quotation.Status.values:
                raise BusinessRuleError(f"Unknown status {status_param!r}.")
            qs = qs.filter(status=status_param)
        if str(params.get("expired") or "").lower() in ("true", "1", "yes"):
            qs = qs.expired()
        if params.get("customer"):
            try:
                qs = qs.filter(customer_id=int(params["customer"]))
            except (TypeError, ValueError) as exc:
                raise BusinessRuleError("customer must be a numeric id.") from exc
        for key, lookup in (("date_from", "quotation_date__gte"), ("date_to", "quotation_date__lte")):
            raw = params.get(key)
            if raw:
                try:
                    qs = qs.filter(**{lookup: _date.fromisoformat(str(raw)[:10])})
                except ValueError as exc:
                    raise BusinessRuleError(f"{key} must be an ISO date (YYYY-MM-DD).") from exc
        term = (params.get("q") or "").strip()[:100]
        if term:
            qs = qs.filter(
                Q(number__icontains=term)
                | Q(customer__name__icontains=term)
                | Q(customer__phone__icontains=term)
            )
        ordering = (params.get("ordering") or "").strip()
        if ordering:
            key = ordering.lstrip("-")
            if key not in QUOTATION_ORDERING:
                raise BusinessRuleError(
                    f"ordering must be one of: {', '.join(sorted(QUOTATION_ORDERING))} (prefix - for descending)."
                )
            prefix = "-" if ordering.startswith("-") else ""
            qs = qs.order_by(*(f"{prefix}{field}" for field in QUOTATION_ORDERING[key]))
        return qs

    def create(self, request, *args, **kwargs):
        def _run():
            return super(QuotationViewSet, self).create(request, *args, **kwargs)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope=f"quotation_create:{request.user.pk}",
            build=_run,
        )

    def perform_destroy(self, instance):
        from .models import QuotationConversion

        if (
            instance.status != Quotation.Status.DRAFT
            or instance.items.filter(converted_quantity__gt=0).exists()
            or QuotationConversion.objects.filter(quotation=instance).exists()
        ):
            raise BusinessRuleError(
                "Only an unconverted draft quotation can be deleted; use Cancel instead.",
                code="quotation_not_deletable",
            )
        from core.services.audit import AuditService

        entity_id = str(instance.pk)
        metadata = {
            "number": instance.number,
            "customer": instance.customer_id,
            "grand_total": str(instance.grand_total),
        }
        instance.delete()
        AuditService.log(
            action="DELETE",
            company=self.company,
            user=self.request.user,
            entity_type="Quotation",
            entity_id=entity_id,
            description=f"Quotation {metadata['number'] or entity_id} deleted.",
            metadata=metadata,
        )

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "QUOTATION"))
        try:
            data = DocumentNumberService.configure(
                company,
                "QUOTATION",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    @staticmethod
    def _confirm_expired(request):
        value = request.data.get("confirm_expired", request.data.get("confirmExpired"))
        return str(value or "").lower() in ("true", "1", "yes")

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        quotation = self.get_object()

        def _run():
            invoice = SalesService.convert_quotation(
                quotation, request.user, confirm_expired=self._confirm_expired(request),
                line_quantities=_convert_line_quantities(request),
            )
            return Response(SalesInvoiceSerializer(invoice, context=self.get_serializer_context()).data)

        request._idempotency_ignore_keys = frozenset({"confirm_expired", "confirmExpired"})
        return wrap_idempotent(
            request=request,
            company=self.company,
            scope=f"quotation_convert:{request.user.pk}:{quotation.pk}",
            build=_run,
        )

    @action(detail=True, methods=["post"], url_path="convert-to-order")
    def convert_to_order(self, request, pk=None):
        from .phase1_serializers import SalesOrderSerializer

        quotation = self.get_object()

        def _run():
            order = SalesService.convert_quotation_to_order(
                quotation, request.user, confirm_expired=self._confirm_expired(request),
                line_quantities=_convert_line_quantities(request),
            )
            return Response(SalesOrderSerializer(order, context=self.get_serializer_context()).data)

        request._idempotency_ignore_keys = frozenset({"confirm_expired", "confirmExpired"})
        return wrap_idempotent(
            request=request,
            company=self.company,
            scope=f"quotation_convert_to_order:{request.user.pk}:{quotation.pk}",
            build=_run,
        )

    CONVERT_CHAIN_SUNSET = "Sat, 28 Nov 2026 00:00:00 GMT"
    # From this date the endpoint answers 410 Gone (closure plan WP16, decision D-14).
    CONVERT_CHAIN_SUNSET_DATE = date(2026, 11, 28)

    @extend_schema(deprecated=True)
    @action(detail=True, methods=["post"], url_path="convert-chain")
    def convert_chain(self, request, pk=None):
        """Deprecated: quote → SO → (optional draft DC) → (optional draft invoice).
        Convert to a sales order and continue from the sales order screen."""
        import logging

        from .notes_services import SalesNotesService
        from .phase1_serializers import DeliveryChallanSerializer, SalesOrderSerializer

        if timezone.localdate() >= self.CONVERT_CHAIN_SUNSET_DATE:
            gone = Response(
                {
                    "detail": "Convert the quotation to a sales order, then continue from the sales order screen.",
                    "code": "convert_chain_gone",
                },
                status=status.HTTP_410_GONE,
            )
            gone["Deprecation"] = "true"
            gone["Sunset"] = self.CONVERT_CHAIN_SUNSET
            return gone

        stop = (request.data.get("stop_stage") or request.data.get("stopStage") or "INVOICE").upper()
        logging.getLogger("bizboard.deprecated").warning(
            "deprecated quotation convert-chain call",
            extra={
                "company_id": self.company.pk,
                "user_id": request.user.pk,
                "stop_stage": stop,
                "user_agent": request.headers.get("User-Agent", "")[:200],
            },
        )
        try:
            from insights.telemetry import note_once

            note_once(self.company, "deprecated_quote_convert_chain", user=request.user, journey="growth")
        except Exception:  # noqa: BLE001 - telemetry must never fail the request
            pass
        if stop not in ("SALES_ORDER", "DELIVERY_CHALLAN", "INVOICE"):
            raise BusinessRuleError("stop_stage must be SALES_ORDER, DELIVERY_CHALLAN, or INVOICE.")
        confirm_expired = str(request.data.get("confirm_expired") or "").lower() in (
            "true", "1", "yes",
        )
        quotation = self.get_object()
        order = SalesService.convert_quotation_to_order(
            quotation, request.user, confirm_expired=confirm_expired,
            line_quantities=_convert_line_quantities(request),
        )
        challan = None
        invoice = None
        if stop in ("DELIVERY_CHALLAN", "INVOICE"):
            # Run confirmation (and its order gate) before advancing the chain —
            # convert_sales_order_to_challan otherwise refuses a DRAFT order
            # once ENABLE_ORDER_GATES is on, breaking this one-click flow.
            # confirm_sales_order re-fetches its own row internally rather
            # than mutating this reference, so pull the confirmed state back
            # before using it further — the response would otherwise still
            # serialize the pre-confirm DRAFT order.
            SalesNotesService.confirm_sales_order(
                order,
                request.user,
                override_reason=request.data.get("credit_override_reason"),
            )
            order.refresh_from_db()
            challan = SalesNotesService.convert_sales_order_to_challan(order, request.user)
        if stop == "INVOICE":
            challan = SalesNotesService.complete_challan(challan, request.user)
            invoice = SalesNotesService.convert_delivery_challan(challan, request.user)
        payload = {
            "stop_stage": stop,
            "quotation_id": quotation.id,
            "sales_order": SalesOrderSerializer(order, context=self.get_serializer_context()).data,
            "delivery_challan": (
                DeliveryChallanSerializer(challan, context=self.get_serializer_context()).data
                if challan is not None else None
            ),
            "invoice": (
                SalesInvoiceSerializer(invoice, context=self.get_serializer_context()).data
                if invoice is not None else None
            ),
        }
        response = Response(payload)
        response["Deprecation"] = "true"
        response["Sunset"] = self.CONVERT_CHAIN_SUNSET
        return response

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        import io

        from .pdf import render_quotation

        quotation = self.get_object()
        content = render_quotation(quotation)
        return FileResponse(
            io.BytesIO(content),
            as_attachment=True,
            filename=f"{quotation.number or quotation.pk}.pdf",
            content_type="application/pdf",
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reason = request.data.get("reason", request.data.get("cancel_reason", "")) or ""
        quotation = SalesService.cancel_quotation(self.get_object(), request.user, reason=str(reason))
        return Response(self.get_serializer(quotation).data)

    @action(detail=True, methods=["post"], url_path="public-link")
    def public_link(self, request, pk=None):
        from .quotation_links import mint_link, public_quotation_url

        link = mint_link(self.get_object(), request.user)
        return Response({"url": public_quotation_url(link.token), "expires_at": link.expires_at})

    @action(detail=True, methods=["post"], url_path="public-link/revoke")
    def revoke_public_link(self, request, pk=None):
        from .quotation_links import revoke_links

        return Response({"revoked": bool(revoke_links(self.get_object()))})

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """Make the PDF link, stamp ``sent_at`` and, when the lifecycle is on, move DRAFT to SENT."""
        from core.services.audit import AuditService
        from core.services.feature_flags import flag_enabled

        from .quotation_links import mint_link, public_quotation_url

        channel = str(request.data.get("channel") or "link")[:20]
        quotation = self.get_object()
        link = mint_link(quotation, request.user)
        if quotation.sent_at is None:
            Quotation.objects.filter(pk=quotation.pk).update(sent_at=timezone.now())
        if quotation.status == Quotation.Status.DRAFT and flag_enabled(self.company, "QUOTE_LIFECYCLE"):
            SalesService.set_quotation_status(quotation, Quotation.Status.SENT, request.user, reason=f"Shared by {channel}")
        AuditService.log(
            action="QUOTATION_SHARED",
            company=self.company,
            user=request.user,
            entity_type="Quotation",
            entity_id=str(quotation.pk),
            description=f"Shared by {channel}.",
            metadata={"channel": channel},
        )
        fresh = Quotation.objects.get(pk=quotation.pk)
        return Response({
            "url": public_quotation_url(link.token),
            "expires_at": link.expires_at,
            "status": fresh.status,
            "sent_at": fresh.sent_at,
        })

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        """Copy into a new draft with a new number. The source quote is not changed."""
        from datetime import timedelta

        from .services import _quotation_items_data_from_plan

        source = self.get_object()
        items = list(source.items.select_related("product").order_by("id"))
        # Cost is copied from the stored lines whoever asks, so a user who cannot see it
        # still gets a copy with the right margin.
        items_data = _quotation_items_data_from_plan([(item, item.quantity) for item in items])
        validity_days = (
            (source.valid_until - source.quotation_date).days
            if source.valid_until and source.quotation_date
            else None
        )
        today = timezone.localdate()
        header = {
            "customer": source.customer,
            "quotation_date": today,
            "valid_until": today + timedelta(days=validity_days) if validity_days is not None else None,
            "invoice_type": source.invoice_type,
            "payment_terms_days": source.payment_terms_days,
            "additional_charges": source.additional_charges,
            "charges_hsn": source.charges_hsn,
            "charges_gst_rate": source.charges_gst_rate,
            "invoice_discount": source.invoice_discount,
            "invoice_discount_mode": source.invoice_discount_mode,
            "auto_round_off": source.auto_round_off,
            "notes": source.notes,
            "terms_text": source.terms_text,
            "supply_type": source.supply_type,
            "company_gstin": source.company_gstin,
            "salesman": source.salesman,
            "sales_channel": source.sales_channel,
            "delivery_address": source.delivery_address,
            "opportunity": source.opportunity,
            "copied_from": source,
        }
        quotation = SalesService.create_quotation(self.company, request.user, header, items_data)
        return Response(
            self.get_serializer(Quotation.objects.get(pk=quotation.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="cancel-expired")
    def cancel_expired(self, request):
        """Cancel every expired open quote that nothing was converted from.

        Quotes that were partly converted cannot be cancelled; they come back in
        ``needs_close_remaining`` so the user can close what is left of them.
        """
        qs = Quotation.objects.filter(company=self.company).expired().filter(short_closed_at__isnull=True)
        customer = request.data.get("customer")
        if customer not in (None, ""):
            try:
                qs = qs.filter(customer_id=int(customer))
            except (TypeError, ValueError) as exc:
                raise BusinessRuleError("customer must be a numeric id.") from exc
        cancelled = 0
        needs_close = []
        for quotation in qs.order_by("id"):
            try:
                SalesService.cancel_quotation(quotation, request.user, reason="Expired")
                cancelled += 1
            except BusinessRuleError:
                needs_close.append({"id": quotation.id, "number": quotation.number})
        return Response({"cancelled": cancelled, "needs_close_remaining": needs_close})

    @action(detail=True, methods=["post"], url_path="close-remaining")
    def close_remaining(self, request, pk=None):
        from .quotation_conversions import QuotationConversionService

        quotation = QuotationConversionService.close_remaining(
            self.get_object(), request.user, request.data.get("reason")
        )
        return Response(self.get_serializer(Quotation.objects.get(pk=quotation.pk)).data)

    @action(detail=True, methods=["post"], url_path="reopen-closed")
    def reopen_closed(self, request, pk=None):
        from .quotation_conversions import QuotationConversionService

        quotation = QuotationConversionService.reopen_closed(
            self.get_object(), request.user, request.data.get("reason")
        )
        return Response(self.get_serializer(Quotation.objects.get(pk=quotation.pk)).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        """Owner-only: release converted quantity whose downstream document is gone
        (backfilled UNKNOWN rows, or releases missed while the rollout flag was off)."""
        from .quotation_conversions import QuotationConversionService

        quotation = self.get_object()
        ids = request.data.get("conversion_ids", request.data.get("conversionIds"))
        QuotationConversionService.reopen(quotation, request.user, request.data.get("reason"), ids)
        return Response(self.get_serializer(Quotation.objects.get(pk=quotation.pk)).data)

    def _lifecycle(self, request, target):
        from core.services.feature_flags import flag_enabled

        quotation = self.get_object()  # 404 for another tenant's quote before any flag answer
        if not flag_enabled(self.company, "QUOTE_LIFECYCLE"):
            raise PermissionDenied("Quotation lifecycle is not enabled for this company.")
        quotation = SalesService.set_quotation_status(
            quotation, target, request.user, reason=str(request.data.get("reason") or "")
        )
        return Response(self.get_serializer(quotation).data)

    @action(detail=True, methods=["post"], url_path="mark-sent")
    def mark_sent(self, request, pk=None):
        return self._lifecycle(request, Quotation.Status.SENT)

    @action(detail=True, methods=["post"], url_path="mark-accepted")
    def mark_accepted(self, request, pk=None):
        return self._lifecycle(request, Quotation.Status.ACCEPTED)

    @action(detail=True, methods=["post"], url_path="mark-rejected")
    def mark_rejected(self, request, pk=None):
        return self._lifecycle(request, Quotation.Status.REJECTED)

    @action(detail=True, methods=["post"], url_path="reopen-for-changes")
    def reopen_for_changes(self, request, pk=None):
        return self._lifecycle(request, Quotation.Status.DRAFT)

    @action(detail=True, methods=["get"])
    def revisions(self, request, pk=None):
        quotation = self.get_object()
        rows = quotation.revisions.filter(company_id=quotation.company_id).order_by("-revision")
        return Response([
            {
                "id": row.id,
                "revision": row.revision,
                "reason": row.reason,
                "created_at": row.created_at,
                "snapshot": row.snapshot,
            }
            for row in rows
        ])


class SalesReturnViewSet(CompanyScopedViewSet):
    queryset = SalesReturn.objects.select_related("customer", "sales_invoice").prefetch_related("items__product")
    serializer_class = SalesReturnSerializer

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action == "complete":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]
        return super().get_permissions()

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "SALES_RETURN"))
        try:
            data = DocumentNumberService.configure(
                company,
                "SALES_RETURN",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        if self.request.query_params.get("customer"):
            qs = qs.filter(customer_id=self.request.query_params["customer"])
        if self.request.query_params.get("sales_invoice"):
            qs = qs.filter(sales_invoice_id=self.request.query_params["sales_invoice"])
        return qs

    def create(self, request, *args, **kwargs):
        def _run():
            return super(SalesReturnViewSet, self).create(request, *args, **kwargs)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="sales_return_create",
            build=_run,
        )

    def perform_destroy(self, instance):
        if instance.status != SalesReturn.Status.DRAFT:
            raise BusinessRuleError("Only draft returns can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        def _run():
            sales_return = SalesService.complete_return(
                self.get_object(),
                request.user,
                gst_guard_override_reason=request.data.get("gst_guard_override_reason") or None,
            )
            return Response(self.get_serializer(sales_return).data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="sales_return_complete",
            build=_run,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sales_return = SalesService.cancel_return(self.get_object(), request.user)
        return Response(self.get_serializer(sales_return).data)


class RecurringInvoiceScheduleViewSet(CompanyScopedViewSet):
    queryset = RecurringInvoiceSchedule.objects.select_related("customer", "company_gstin")
    serializer_class = RecurringInvoiceScheduleSerializer
    audit_entity = "RecurringInvoiceSchedule"

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "run_now":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), HasCompany(), CanCreateSales()]
        return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]

    @action(detail=True, methods=["post"], url_path="run-now")
    def run_now(self, request, pk=None):
        from django.utils import timezone

        from .recurring import generate_draft_for_schedule

        schedule = self.get_object()
        run = generate_draft_for_schedule(schedule, run_date=timezone.localdate(), user=request.user)
        if run is None:
            raise BusinessRuleError("Schedule did not generate an invoice (inactive, locked period, or duplicate).")
        status = None
        if run.invoice_id:
            status = run.invoice.status
        elif run.delivery_challan_id:
            status = run.delivery_challan.status
        elif run.sales_order_id:
            status = run.sales_order.status
        return Response({
            "ok": True,
            "run_id": run.id,
            "invoice_id": run.invoice_id,
            "sales_order_id": run.sales_order_id,
            "delivery_challan_id": run.delivery_challan_id,
            "stop_stage": run.schedule.stop_stage,
            "period_key": run.period_key,
            "status": status,
        })


class SalespersonSearchView(APIView):
    """Names a sales user may pick as a document's salesperson.

    The payroll employee list is owner-only and needs payroll switched on, so a
    salesperson picker built on it was empty for staff and for most shops. This
    returns only id, name and code of active employees.
    """

    def get_permissions(self):
        return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from core.permissions import get_company_user
        from payroll.models import Employee

        company = get_company_user(request).company
        term = (request.query_params.get("q") or "").strip()[:60]
        qs = Employee.objects.filter(company=company, status=Employee.Status.ACTIVE)
        if term:
            qs = qs.filter(Q(name__icontains=term) | Q(code__icontains=term))
        rows = qs.order_by("name").values("id", "name", "code")[:30]
        return Response({"results": list(rows)})


class StockHintView(APIView):
    """Available quantity in the default godown for the products on a quotation.

    A quotation has no godown of its own; conversion uses the default one, so the
    hint is measured there. Read-only, and only for products whose stock is tracked.
    """

    def get_permissions(self):
        return [IsAuthenticated(), HasCompany(), CanViewSalesSurfaces()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from core.permissions import get_company_user
        from inventory.models import StockBalance, Warehouse
        from masters.models import Product

        company = get_company_user(request).company
        ids = []
        for raw in str(request.query_params.get("products") or "").split(",")[:100]:
            if raw.strip().isdigit():
                ids.append(int(raw.strip()))
        warehouse = Warehouse.objects.filter(company=company, is_default=True).first()
        if not ids or warehouse is None:
            return Response({"warehouse": getattr(warehouse, "id", None), "available": {}})
        tracked = set(
            Product.objects.filter(company=company, pk__in=ids, track_inventory=True).values_list("id", flat=True)
        )
        rows = (
            StockBalance.objects.filter(company=company, warehouse=warehouse, product_id__in=tracked)
            .values("product_id")
            .annotate(on_hand=Sum("on_hand"), reserved=Sum("reserved"))
        )
        available = {str(pid): "0.000" for pid in tracked}
        for row in rows:
            available[str(row["product_id"])] = str(max((row["on_hand"] or 0) - (row["reserved"] or 0), 0))
        return Response({"warehouse": warehouse.id, "available": available})
