
import csv
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, models, transaction
from django.db.models import Count, Exists, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.permissions import SubscriptionWritesAllowed
from core.csv_utils import csv_safe
from core.exceptions import BusinessRuleError
from core.idempotency import (
    begin_record,
    release_record,
    request_fingerprint,
    require_idempotency_key,
    store_record,
    wrap_idempotent,
)
from core.permissions import (
    CanCancelDocuments,
    CanExport,
    CanCreatePayments,
    CanViewPaymentSurfaces,
    HasCompany,
    IsOwner,
    IsOwnerManagerOrAccountant,
    get_company_user,
)
from core.rls import stream_with_rls
from core.services.audit import AuditService
from core.throttles import CompanyRateThrottle
from core.viewsets import CompanyScopedViewSet

from .gateway import (
    decrypt_gateway_credentials,
    encrypt_gateway_credentials,
)
from .models import (
    AdvanceRefundStatus,
    BankAccount,
    BankLineMatchStatus,
    BankStatement,
    BankStatementLine,
    BankStatementStatus,
    ChequeStatus,
    CustomerAdvanceRefund,
    CustomerReceipt,
    GatewayPayment,
    PaymentAllocation,
    PaymentLink,
    PaymentLinkStatus,
    PaymentMode,
    PaymentPromise,
    PaymentSource,
    ReceiptStatus,
    ReconMatch,
    SupplierPayment,
    SupplierPaymentStatus,
)
from .promise_to_pay import create_promise, resolve_promise
from .recon import is_exact_unique_suggestion, parse_bank_csv, suggest_matches
from .upi import normalize_utr
from .serializers import (
    BankAccountSerializer,
    BankStatementLineSerializer,
    BankStatementSerializer,
    AdvanceRefundLineSerializer,
    CustomerReceiptSerializer,
    ReceiptSummarySerializer,
    GatewayPaymentSerializer,
    PaymentAllocationSerializer,
    PaymentLinkSerializer,
    PaymentPromiseSerializer,
    ReconMatchSerializer,
    SupplierPaymentSerializer,
    UpiQrSerializer,
)
from .services import PaymentService


from .webhook_views import public_frontend_base_url


class BankAccountViewSet(CompanyScopedViewSet):
    queryset = BankAccount.objects.all()
    serializer_class = BankAccountSerializer
    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), HasCompany(), (CanCreatePayments | IsOwner)()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        from payments.services import sync_company_bank_account

        sync_company_bank_account(self.company)
        return super().get_queryset()

    def perform_create(self, serializer):
        if serializer.validated_data.get("is_default"):
            BankAccount.objects.filter(company=self.company, is_default=True).update(is_default=False)
        serializer.save(company=self.company, created_by=self.request.user, updated_by=self.request.user)
        self._audit("CREATE", serializer.instance)
        self._post_opening_balance(serializer.instance)

    def perform_update(self, serializer):
        if serializer.validated_data.get("is_default"):
            BankAccount.objects.filter(company=self.company, is_default=True).exclude(
                pk=serializer.instance.pk
            ).update(is_default=False)
        serializer.save(updated_by=self.request.user)
        self._audit("UPDATE", serializer.instance)
        self._post_opening_balance(serializer.instance)

    def _post_opening_balance(self, bank_account):
        """PAY-14: keep the GL bank opening balance in step with the operational
        opening_balance field (idempotent; re-posts on an edit)."""
        if not getattr(self.company, "accounting_enabled", False):
            return
        try:
            from accounting.services import PostingService

            PostingService.post_bank_opening_balance(bank_account, user=self.request.user)
        except Exception:  # noqa: BLE001 — a GL hiccup must not fail the bank-account save
            import logging

            logging.getLogger(__name__).exception(
                "Failed to post opening balance for bank account %s", bank_account.pk
            )


RECEIPT_FILTER_PARAMETERS = [
    OpenApiParameter("q", str, description="Number, customer name, phone, UTR or reference (max 100 characters)."),
    OpenApiParameter("mode", str, enum=list(PaymentMode.values)),
    OpenApiParameter("status", str, enum=list(ReceiptStatus.values)),
    OpenApiParameter("date_from", OpenApiTypes.DATE, description="Receipt date on or after."),
    OpenApiParameter("date_to", OpenApiTypes.DATE, description="Receipt date on or before."),
    OpenApiParameter("customer", int),
    OpenApiParameter("reconciled", bool, description="true: matched to a bank line; false: not matched."),
    OpenApiParameter(
        "ordering", str,
        description="Sort column, with a leading '-' for descending: receipt_date, amount, number, "
        "customer__name or status. Ties are broken by id so pages never overlap.",
    ),
]
RECEIPT_SEARCH_MAX_LENGTH = 100
# A trigram index needs at least three characters; shorter terms would scan every branch.
RECEIPT_SEARCH_MIN_LENGTH = 3
RECEIPT_SEARCH_ID_CAP = 5000
RECEIPT_ORDERING_FIELDS = ("receipt_date", "amount", "number", "customer__name", "status")
RECEIPT_EXPORT_MAX_ROWS = 20000
_PHONE_LIKE = re.compile(r"^[\d\s+\-]{3,}$")


def _utr_duplicates_for_page(company, rows) -> dict:
    """{receipt id: warning} for the receipts of one page, in two queries.

    Same rule as ``payments.services._check_utr_duplicate`` (another live receipt or a live
    supplier payment carries the same UTR), looked up for every UTR on the page at once.
    """
    utrs = {row.utr for row in rows if row.utr}
    if not utrs:
        return {}
    live_receipts = CustomerReceipt.objects.filter(company=company, utr__in=utrs).exclude(
        status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED)
    )
    receipts_by_utr: dict[str, list[int]] = {}
    for pk, utr in live_receipts.values_list("pk", "utr"):
        receipts_by_utr.setdefault(utr, []).append(pk)
    payment_utrs = set(
        SupplierPayment.objects.filter(company=company, utr__in=utrs)
        .exclude(status=SupplierPaymentStatus.VOIDED)
        .values_list("utr", flat=True)
    )
    out = {}
    for row in rows:
        if not row.utr:
            continue
        if any(pk != row.pk for pk in receipts_by_utr.get(row.utr, ())):
            out[row.pk] = f"UTR {row.utr} was already used on another receipt."
        elif row.utr in payment_utrs:
            out[row.pk] = f"UTR {row.utr} was already used on a supplier payment."
    return out


def _query_date(params, key):
    raw = str(params.get(key) or "").strip()
    if not raw:
        return None
    try:
        parsed = parse_date(raw)
    except ValueError:
        parsed = None
    if parsed is None:
        raise ValidationError({key: "Use a valid date in YYYY-MM-DD format."})
    return parsed


def _query_choice(params, key, choices):
    raw = (params.get(key) or "").strip().upper()
    if not raw:
        return None
    if raw not in choices:
        raise ValidationError({key: f"Choose one of: {', '.join(sorted(choices))}."})
    return raw


class CustomerReceiptViewSet(CompanyScopedViewSet):
    queryset = (
        CustomerReceipt.objects.select_related("customer", "bank_account", "voided_by")
        .prefetch_related(
            "allocations__sales_invoice__credit_notes", "advance_refunds", "recon_matches",
            "aa_transactions",
        )
    )
    serializer_class = CustomerReceiptSerializer
    http_method_names = ["get", "post", "patch"]
    # These actions read the filtered list; everything else addresses one row by id.
    _LIST_ACTIONS = ("list", "summary", "export")

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), HasCompany(), CanCreatePayments()]
        if self.action in ("void", "refund_advance", "correct_closed_till", "reassign_customer"):
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if self.action in ("set_cheque_status", "partial_update", "bulk_allocate", "send"):
            return [IsAuthenticated(), HasCompany(), CanCreatePayments()]
        if self.action == "export":
            return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces(), CanExport()]
        if self.action in ("list", "retrieve", "summary", "voucher"):
            return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces()]
        return super().get_permissions()

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.action == "export":
            throttles.append(CompanyRateThrottle("receipts_export"))
        elif self.action == "summary":
            throttles.append(CompanyRateThrottle("receipts_summary"))
        return throttles

    @extend_schema(parameters=RECEIPT_FILTER_PARAMETERS)
    def list(self, request, *args, **kwargs):
        import logging
        import time

        started = time.monotonic()
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        searched = (request.query_params.get("q") or "").strip()
        if searched:
            # For the slow-query review: how long a search took, never what was searched for.
            logging.getLogger("payments.receipt_search").info(
                "receipt.search q_len=%s rows=%s ms=%s",
                len(searched), len(rows), int((time.monotonic() - started) * 1000),
            )
        # Duplicate-UTR warnings for the whole page in two queries, not two per row.
        self._utr_duplicates = _utr_duplicates_for_page(self.company, rows)
        serializer = self.get_serializer(rows, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        page_map = getattr(self, "_utr_duplicates", None)
        if page_map is not None:
            context["utr_duplicates"] = page_map
        return context

    @staticmethod
    def _apply_ordering(qs, params):
        raw = (params.get("ordering") or "").strip()
        if not raw:
            return qs
        field = raw.lstrip("-")
        if field not in RECEIPT_ORDERING_FIELDS:
            raise ValidationError(
                {"ordering": f"Sort by one of: {', '.join(RECEIPT_ORDERING_FIELDS)}."}
            )
        direction = "-" if raw.startswith("-") else ""
        # `id` as the last key keeps the order total, so a page boundary never repeats a row.
        return qs.order_by(f"{direction}{field}", f"{direction}id")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("customer"):
            if not params["customer"].isdigit():
                raise ValidationError({"customer": "Use a customer id."})
            qs = qs.filter(customer_id=int(params["customer"]))
        if getattr(self, "action", None) in self._LIST_ACTIONS:
            qs = self._apply_list_filters(qs, params, self.company.id)
        if getattr(self, "action", None) in ("list", "export"):
            qs = self._apply_ordering(qs, params)
        return qs

    @staticmethod
    def _apply_list_filters(qs, params, company_id):
        mode = _query_choice(params, "mode", set(PaymentMode.values))
        if mode:
            qs = qs.filter(mode=mode)
        status_value = _query_choice(params, "status", set(ReceiptStatus.values))
        if status_value:
            qs = qs.filter(status=status_value)
        date_from = _query_date(params, "date_from")
        date_to = _query_date(params, "date_to")
        if date_from and date_to and date_from > date_to:
            raise ValidationError({"date_from": "The start date must be on or before the end date."})
        if date_from:
            qs = qs.filter(receipt_date__gte=date_from)
        if date_to:
            qs = qs.filter(receipt_date__lte=date_to)
        reconciled = (params.get("reconciled") or "").strip().lower()
        if reconciled in ("true", "false", "1", "0"):
            from banking.models import AaTransaction

            matched = Exists(ReconMatch.objects.filter(receipt=OuterRef("pk"))) | Exists(
                AaTransaction.objects.filter(matched_payment=OuterRef("pk"))
            )
            qs = qs.filter(matched) if reconciled in ("true", "1") else qs.exclude(matched)
        elif reconciled:
            raise ValidationError({"reconciled": "Use true or false."})
        query = (params.get("q") or "").strip()[:RECEIPT_SEARCH_MAX_LENGTH]
        if 0 < len(query) < RECEIPT_SEARCH_MIN_LENGTH:
            # Too short for any index, so a contains-search would read the whole table.
            # Only an exact receipt number is looked up.
            qs = qs.filter(number__iexact=query)
        elif query:
            # One indexable branch per field, combined by UNION. A single OR across the receipt
            # columns and a customer join (or subquery) cannot use any index, so the planner read
            # the whole receipts table for every search.
            from masters.models import Customer

            payer = models.Q(name__icontains=query)
            if _PHONE_LIKE.match(query):
                payer |= models.Q(phone__icontains=query)
            payers = Customer.all_objects.filter(payer, company_id=company_id).values("pk")
            base = CustomerReceipt.objects.filter(company_id=company_id)
            branches = [
                base.filter(number__icontains=query),
                base.filter(utr__istartswith=query),
                base.filter(reference__istartswith=query),
                base.filter(customer_id__in=payers),
            ]
            matched = branches[0].order_by().values("pk").union(
                *(branch.order_by().values("pk") for branch in branches[1:])
            )
            # Read the matching ids first (the trigram indexes make this cheap) when there are not
            # many: the planner then drives the page from a short id list instead of choosing to
            # scan and hash-join every receipt of the company. A search that matches a great many
            # rows keeps the subquery, which is the only exact way to count them.
            ids = list(matched.values_list("pk", flat=True)[: RECEIPT_SEARCH_ID_CAP + 1])
            qs = qs.filter(pk__in=ids if len(ids) <= RECEIPT_SEARCH_ID_CAP else matched)
        return qs

    @extend_schema(parameters=RECEIPT_FILTER_PARAMETERS, responses=ReceiptSummarySerializer)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Totals for the same filters as the list, across every page.

        Voided, refunded and bounced receipts are not money in hand. Cheques still
        waiting to clear are reported apart from collected money. Advances handed back to
        customers are deducted from what is collected and from the advance.
        """
        qs = self.get_queryset().prefetch_related(None).order_by()
        live = ~models.Q(status__in=[ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED]) & ~models.Q(
            cheque_status=ChequeStatus.BOUNCED
        )
        pending_q = models.Q(mode=PaymentMode.CHEQUE, cheque_status=ChequeStatus.PENDING_CLEARANCE)
        # One pass: the rows counted as money in hand, the pending cheques, and every matching row.
        agg = qs.aggregate(
            rows=Count("id"),
            n=Count("id", filter=live),
            total=Sum("amount", filter=live),
            pending=Sum("amount", filter=live & pending_q),
            tds=Sum("tds_deducted", filter=live),
        )
        counted = qs.filter(live)
        total = agg["total"] or Decimal("0")
        pending = agg["pending"] or Decimal("0")
        tds = agg["tds"] or Decimal("0")
        alloc = PaymentAllocation.objects.filter(
            company=self.company,
            reversed_at__isnull=True,
            receipt__in=counted.values("pk"),
        ).aggregate(cash=Sum("amount"), tds=Sum("tds_applied"))
        allocated = alloc["cash"] or Decimal("0")
        tds_applied = alloc["tds"] or Decimal("0")
        refunded = CustomerAdvanceRefund.objects.filter(
            company=self.company,
            status=AdvanceRefundStatus.POSTED,
            receipt__in=counted.values("pk"),
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        return Response({
            "count": agg["n"],
            "collected": total - pending - refunded,
            "cheques_pending": pending,
            "allocated": allocated,
            "advance": max(total + tds - allocated - tds_applied - refunded, Decimal("0")),
            "excluded_count": agg["rows"] - agg["n"],
            "refunded": refunded,
        })

    @extend_schema(
        parameters=RECEIPT_FILTER_PARAMETERS,
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=["get"])
    def export(self, request):
        """CSV of every receipt that matches the list filters (not just one page).

        Streamed row by row, so a 20,000-row export never sits in memory.
        """
        qs = self.get_queryset().prefetch_related(None)
        total_rows = qs.count()
        if total_rows > RECEIPT_EXPORT_MAX_ROWS:
            raise BusinessRuleError(
                f"Too many receipts to export at once (limit {RECEIPT_EXPORT_MAX_ROWS}). Narrow the date range.",
                code="export_too_large",
            )

        def per_receipt(model, value):
            # A correlated sub-select per receipt: summing over several joined tables at once
            # would multiply the rows of each.
            return Coalesce(
                Subquery(
                    model.objects.filter(receipt=OuterRef("pk"), **value["where"])
                    .values("receipt")
                    .annotate(t=Sum(value["field"]))
                    .values("t")[:1]
                ),
                Decimal("0"),
                output_field=models.DecimalField(max_digits=14, decimal_places=2),
            )

        rows = qs.annotate(
            live_allocated=per_receipt(PaymentAllocation, {"field": "amount", "where": {"reversed_at__isnull": True}}),
            live_tds_applied=per_receipt(
                PaymentAllocation, {"field": "tds_applied", "where": {"reversed_at__isnull": True}}
            ),
            live_refunded=per_receipt(
                CustomerAdvanceRefund, {"field": "amount", "where": {"status": AdvanceRefundStatus.POSTED}}
            ),
        ).order_by("receipt_date", "id")
        if not (request.query_params.get("ordering") or "").strip():
            rows = rows.order_by("receipt_date", "id")
        else:
            rows = self._apply_ordering(rows, request.query_params)

        class _Echo:
            def write(self, value):
                return value

        writer = csv.writer(_Echo())

        def lines():
            yield writer.writerow([
                "Number", "Date", "Customer", "Mode", "Status", "Amount", "Allocated", "Advance",
                "UTR", "Reference", "Cheque no", "Cheque status", "Bank account", "Void reason",
                "TDS deducted", "TDS section", "Refunded",
            ])
            two = Decimal("0.01")
            for row in rows.select_related("customer", "bank_account").iterator(chunk_size=500):
                allocated = Decimal(str(row.live_allocated or 0)).quantize(two)
                refunded = Decimal(str(row.live_refunded or 0)).quantize(two)
                tds_applied = Decimal(str(row.live_tds_applied or 0))
                dead = row.status in (ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED)
                advance = Decimal("0") if dead else (
                    row.amount + row.tds_deducted - allocated - tds_applied - refunded
                ).quantize(two)
                yield writer.writerow([
                    csv_safe(v) for v in (
                        row.number, row.receipt_date.isoformat(), row.customer.name, row.mode, row.status,
                        row.amount, allocated, advance, row.utr, row.reference, row.cheque_number,
                        row.cheque_status, row.bank_account.name if row.bank_account_id else "", row.void_reason,
                        row.tds_deducted, row.tds_section, refunded,
                    )
                ])

        AuditService.log(
            company=self.company, user=request.user, action="EXPORT",
            entity_type="CustomerReceipt", entity_id="list",
            metadata={"filters": {k: v for k, v in request.query_params.items()}, "rows": total_rows},
        )
        response = StreamingHttpResponse(
            stream_with_rls(self.company.id, lines()), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = 'attachment; filename="customer-receipts.csv"'
        return response

    @extend_schema(
        parameters=[
            OpenApiParameter("layout", str, enum=["A4", "THERMAL"], description="Paper layout."),
            OpenApiParameter("lang", str, enum=["en", "hi"], description="Voucher language."),
        ],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"])
    def voucher(self, request, pk=None):
        """Printable receipt voucher PDF. ``?layout=thermal`` for an 80 mm roll."""
        from .receipt_voucher import render_receipt_voucher_pdf

        receipt = self.get_object()
        layout = (request.query_params.get("layout") or "A4").upper()
        if layout not in ("A4", "THERMAL"):
            raise ValidationError({"layout": "Use A4 or THERMAL."})
        lang = (request.query_params.get("lang") or "en").lower()
        if lang not in ("en", "hi"):
            raise ValidationError({"lang": "Use en or hi."})
        content = render_receipt_voucher_pdf(receipt, layout=layout, lang=lang)
        AuditService.log(
            company=self.company, user=request.user, action="PRINT",
            entity_type="CustomerReceipt", entity_id=receipt.pk,
            metadata={"layout": layout, "lang": lang, "number": receipt.number},
        )
        safe_number = re.sub(r"[^A-Za-z0-9._-]", "_", receipt.number or str(receipt.pk))
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="receipt-{safe_number}.pdf"'
        return response

    def _resolve_target_invoice(self, request, receipt_amount, allocate_oldest):
        """Optional single-invoice allocation, applied in the same transaction as the receipt."""
        raw_invoice = request.data.get("sales_invoice")
        if raw_invoice in (None, ""):
            return None, None
        if allocate_oldest:
            raise ValidationError("Choose either 'allocate_oldest' or 'sales_invoice', not both.")
        from sales.models import SalesInvoice

        try:
            invoice = SalesInvoice.objects.get(company=self.company, pk=int(raw_invoice))
        except (TypeError, ValueError, SalesInvoice.DoesNotExist):
            raise ValidationError({"sales_invoice": "Invalid sales invoice."}) from None
        raw_amount = request.data.get("allocate_amount")
        try:
            amount = Decimal(str(raw_amount)) if raw_amount not in (None, "") else Decimal(str(receipt_amount))
        except InvalidOperation:
            raise ValidationError({"allocate_amount": "Enter a valid amount."}) from None
        if amount <= 0 or amount > Decimal(str(receipt_amount)):
            raise ValidationError(
                {"allocate_amount": "The amount applied must be more than 0 and no more than the receipt."}
            )
        return invoice, amount

    @staticmethod
    def _assert_walk_in_fully_applied(receipt):
        """A walk-in has no account to hold an advance, so it must settle bills in full."""
        if not receipt.customer.is_pos_walk_in:
            return
        applied = sum(
            (row.amount for row in receipt.allocations.filter(reversed_at__isnull=True)),
            Decimal("0"),
        )
        if applied != receipt.amount:
            raise BusinessRuleError(
                "A walk-in customer's payment must be applied to invoices in full. "
                "Pick a named customer to keep an advance.",
                code="walkin_full_allocation_required",
            )

    def create(self, request, *args, **kwargs):
        """BB-000610 / BB-000654: durable idempotency + period gate."""
        raw_key = require_idempotency_key(request)
        if raw_key:
            claimed = begin_record(
                company=self.company, scope="receipt_create", raw_key=raw_key,
                fingerprint=request_fingerprint(request),
            )
            if isinstance(claimed, Response):
                return claimed

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            from reporting.gst_periods import assert_period_allows_money_amend, period_complete_warning

            receipt_date = serializer.validated_data.get("receipt_date")
            if receipt_date and receipt_date > timezone.localdate():
                raise ValidationError({"receipt_date": "A receipt cannot be dated in the future."})
            assert_period_allows_money_amend(self.company, receipt_date)
            warning = period_complete_warning(self.company, receipt_date)
            bank_account = serializer.validated_data.get("bank_account")
            allocate_oldest = request.data.get("allocate_oldest") in (True, "true", "True", 1, "1")
            target_invoice, target_amount = self._resolve_target_invoice(
                request, serializer.validated_data["amount"], allocate_oldest
            )
            data_in = serializer.validated_data
            mode_in = str(data_in.get("mode", "CASH")).upper()
            if (data_in.get("settlement_discount") or 0) > 0 and not (allocate_oldest or target_invoice):
                # The discount is cleared against an invoice when the money is applied. With no
                # invoice to apply it to, it would sit on the receipt and never reach the books.
                raise BusinessRuleError(
                    "A settlement discount needs an invoice to apply to. Pick the invoice, or "
                    "apply the receipt to the oldest bills first.",
                    code="settlement_discount_needs_invoice",
                )
            # A cheque that has not cleared stays an advance when the company asks for that; what
            # the person chose is remembered and applied when the cheque clears.
            hold_cheque = (
                mode_in == "CHEQUE"
                and bool(getattr(self.company, "cheque_allocation_on_clearance", False))
                and (allocate_oldest or target_invoice is not None)
            )
            # One transaction: if the oldest-first allocation fails (closed period,
            # invoice changed underneath), the receipt must roll back too. Otherwise
            # the idempotency key is released below and a retry posts a second receipt.
            with transaction.atomic():
                receipt = PaymentService.create_receipt(
                    company=self.company,
                    customer=serializer.validated_data["customer"],
                    amount=serializer.validated_data["amount"],
                    mode=serializer.validated_data.get("mode", "CASH"),
                    receipt_date=serializer.validated_data.get("receipt_date"),
                    reference=serializer.validated_data.get("reference", ""),
                    utr=serializer.validated_data.get("utr", ""),
                    notes=serializer.validated_data.get("notes", ""),
                    bank_account=bank_account,
                    user=request.user,
                    cheque_number=serializer.validated_data.get("cheque_number", ""),
                    cheque_bank_name=serializer.validated_data.get("cheque_bank_name", ""),
                    cheque_date=serializer.validated_data.get("cheque_date"),
                    cheque_image=serializer.validated_data.get("cheque_image"),
                    settlement_discount=serializer.validated_data.get("settlement_discount") or 0,
                    tds_deducted=serializer.validated_data.get("tds_deducted") or 0,
                    tds_section=serializer.validated_data.get("tds_section", ""),
                    advance_gst_rate=serializer.validated_data.get("advance_gst_rate"),
                    require_bank_account=True,
                    allocate_on_clear=hold_cheque,
                    intended_sales_invoice=target_invoice if hold_cheque else None,
                    intended_amount=target_amount if hold_cheque else None,
                )
                if (
                    str(serializer.validated_data.get("mode", "CASH")).upper() == "CASH"
                    and serializer.validated_data.get("paid_from_till")
                ):
                    from sales.pos_shift import mark_paid_from_till

                    mark_paid_from_till(receipt, self.company, request.user)
                if hold_cheque:
                    pass
                elif allocate_oldest:
                    PaymentService.allocate_receipt_oldest_first(receipt=receipt, user=request.user)
                elif target_invoice is not None:
                    PaymentService.allocate_receipt(
                        receipt=receipt,
                        sales_invoice=target_invoice,
                        amount=target_amount,
                        user=request.user,
                    )
                self._assert_walk_in_fully_applied(receipt)
        except Exception:
            if raw_key:
                release_record(company=self.company, scope="receipt_create", raw_key=raw_key)
            raise
        self._audit("CREATE", receipt)
        data = self.get_serializer(receipt).data
        warnings = [w for w in (warning, getattr(receipt, "_cash_limit_warning", None)) if w]
        if warnings:
            data["warnings"] = warnings
        response = Response(data, status=status.HTTP_201_CREATED)
        if raw_key:
            store_record(
                company=self.company,
                scope="receipt_create",
                raw_key=raw_key,
                response=response,
                resource_id=str(receipt.pk),
            )
        return response

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        receipt = self.get_object()

        def run():
            voided = PaymentService.void_receipt(
                receipt=receipt, user=request.user, reason=request.data.get("reason") or "",
            )
            self._audit("VOID", voided)
            return Response(self.get_serializer(voided).data)

        # A retried void with the same key returns the first answer instead of failing on an
        # already-voided receipt or posting twice.
        return wrap_idempotent(request=request, company=self.company, scope="receipt_void", build=run)

    def partial_update(self, request, *args, **kwargs):
        """Edit the descriptive fields of a posted receipt (notes, reference, UTR, bank account)."""
        receipt = self.get_object()
        payload = {
            key: value for key, value in request.data.items()
            if key not in ("csrfmiddlewaretoken",)
        }
        changes = {}
        for key, value in payload.items():
            if key == "bankAccount":
                key = "bank_account"
            changes[key] = value
        if not changes:
            raise ValidationError("Send the fields to change.")
        if "bank_account" in changes and changes["bank_account"] in ("", None):
            changes["bank_account"] = None
        elif "bank_account" in changes:
            try:
                changes["bank_account"] = int(changes["bank_account"])
            except (TypeError, ValueError):
                raise ValidationError({"bank_account": "Choose a bank account."}) from None
        receipt = PaymentService.edit_receipt(receipt=receipt, changes=changes, user=request.user)
        self._audit("UPDATE", receipt)
        return Response(self.get_serializer(self.get_queryset().get(pk=receipt.pk)).data)

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Send the receipt voucher to the customer by WhatsApp or email, and log it.

        An empty ``recipient`` with WhatsApp is a device share: the text and link come back and
        the person picks the chat; nothing is recorded as delivered. Business-number (Cloud)
        sending needs the customer's WhatsApp opt-in, exactly as for invoices.
        """
        from core.models import Notification
        from core.serializers import NotificationSerializer
        from core.services.audit import record_document_event
        from core.services.notifications import NotificationService
        from sales.whatsapp_send import cloud_allowed_for_recipient

        from .receipt_share import compose_receipt_message, public_voucher_url

        receipt = self.get_object()
        if receipt.status != ReceiptStatus.POSTED:
            raise BusinessRuleError("Only a posted receipt can be sent.", code="receipt_not_sendable")
        channel = str(request.data.get("channel") or "").upper()
        if channel not in (Notification.Channel.EMAIL, Notification.Channel.WHATSAPP):
            raise BusinessRuleError("channel must be 'email' or 'whatsapp'.")
        url = public_voucher_url(receipt, request)
        text = compose_receipt_message(receipt, url)
        customer = receipt.customer
        device = (
            channel == Notification.Channel.WHATSAPP
            and "recipient" in request.data
            and not str(request.data.get("recipient") or "").strip()
        )
        if device:
            record_document_event(
                document=receipt, user=request.user, event="customer_receipt.shared",
                metadata={"channel": channel, "mode": "device"},
            )
            return Response({"mode": "device", "text": text, "document_url": url, "status": "OPENED"})
        recipient = request.data.get("recipient") or (
            customer.email if channel == Notification.Channel.EMAIL else customer.phone
        )
        if not recipient:
            raise BusinessRuleError("No recipient available for this channel.", code="no_recipient")
        allow_cloud = (
            cloud_allowed_for_recipient(customer, recipient) if channel == Notification.Channel.WHATSAPP else False
        )
        notification = NotificationService.send(
            company=receipt.company,
            channel=channel,
            recipient=recipient,
            subject=f"Receipt {receipt.number}",
            body=text,
            user=request.user,
            allow_cloud=allow_cloud,
        )
        mode = getattr(notification, "delivery_mode", None) or (
            "cloud" if notification.status == Notification.Status.SENT else "link"
        )
        record_document_event(
            document=receipt, user=request.user, event="customer_receipt.sent",
            metadata={"channel": channel, "mode": mode, "recipient": str(recipient)[:64]},
        )
        data = NotificationSerializer(notification).data
        data["mode"] = mode
        data["document_url"] = url
        return Response(data)

    @extend_schema(request=None, responses=CustomerReceiptSerializer)
    @action(detail=True, methods=["post"], url_path="reassign-customer")
    def reassign_customer(self, request, pk=None):
        """Move money that landed on the walk-in account to the customer who paid."""
        from masters.models import Customer

        receipt = self.get_object()
        try:
            target = Customer.objects.get(company=self.company, pk=int(request.data.get("customer")))
        except (TypeError, ValueError, Customer.DoesNotExist):
            raise ValidationError({"customer": "Choose the customer who paid."}) from None
        PaymentService.reassign_receipt_customer(
            receipt=receipt, new_customer=target, reason=request.data.get("reason") or "", user=request.user,
        )
        self._audit("UPDATE", receipt)
        return Response(self.get_serializer(self.get_queryset().get(pk=receipt.pk)).data)

    @extend_schema(request=None, responses=CustomerReceiptSerializer)
    @action(detail=True, methods=["post"], url_path="correct-closed-till")
    def correct_closed_till(self, request, pk=None):
        """Manager: void a cash receipt that was counted in a closed till and record why."""
        from accounting.cash_shifts import correct_closed_till_receipt

        receipt = self.get_object()
        correct_closed_till_receipt(receipt, request.data.get("reason") or "", request.user)
        self._audit("VOID", receipt)
        return Response(self.get_serializer(self.get_queryset().get(pk=receipt.pk)).data)

    @extend_schema(request=None, responses=AdvanceRefundLineSerializer)
    @action(detail=True, methods=["post"], url_path="refund-advance")
    def refund_advance(self, request, pk=None):
        """Hand back part or all of the unallocated money on this receipt, without voiding it."""
        receipt = self.get_object()

        def run():
            data = request.data
            raw_bank = data.get("bank_account")
            bank = None
            if raw_bank not in (None, ""):
                try:
                    bank = BankAccount.objects.filter(company=self.company, pk=int(raw_bank)).first()
                except (TypeError, ValueError):
                    bank = None
                if bank is None:
                    raise ValidationError({"bank_account": "Invalid bank account."})
            refund_date = _query_date(data, "refund_date") if data.get("refund_date") else None
            try:
                amount = Decimal(str(data.get("amount") or 0))
                if not amount.is_finite():
                    raise InvalidOperation
            except InvalidOperation:
                raise ValidationError({"amount": "Enter a valid amount."}) from None
            refund = PaymentService.refund_advance(
                receipt=receipt,
                amount=amount,
                mode=data.get("mode") or "CASH",
                reason=data.get("reason") or "",
                refund_date=refund_date,
                bank_account=bank,
                utr=data.get("utr") or "",
                paid_from_till=data.get("paid_from_till") in (True, "true", "True", 1, "1"),
                user=request.user,
            )
            self._audit("REFUND_ADVANCE", receipt)
            return Response(AdvanceRefundLineSerializer(refund).data, status=status.HTTP_201_CREATED)

        return wrap_idempotent(
            request=request, company=self.company, scope="receipt_refund_advance", build=run,
        )

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="bulk-allocate")
    def bulk_allocate(self, request):
        """Apply several advances oldest-bill-first. One result per receipt; one failure stops nothing.

        Receipts are taken per customer in ``(receipt_date, id)`` order, so two advances of one
        customer never compete for the same bills in a different order on a retry.
        """
        raw_key = require_idempotency_key(request)
        raw_ids = request.data.get("ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValidationError({"ids": "Send the receipt ids to apply."})
        if len(raw_ids) > 100:
            raise ValidationError({"ids": "Apply at most 100 receipts at a time."})
        try:
            ids = sorted({int(v) for v in raw_ids})
        except (TypeError, ValueError):
            raise ValidationError({"ids": "Receipt ids must be whole numbers."}) from None
        company = self.company

        def run():
            receipts = list(
                CustomerReceipt.objects.filter(company=company, pk__in=ids)
                .select_related("customer")
                .order_by("customer_id", "receipt_date", "id")
            )
            found = {r.pk for r in receipts}
            results = [
                {"id": missing, "status": "failed", "allocated": "0.00", "message": "Receipt not found."}
                for missing in ids if missing not in found
            ]
            for receipt in receipts:
                try:
                    with transaction.atomic():
                        if receipt.status != ReceiptStatus.POSTED:
                            raise BusinessRuleError("Only a posted receipt can be applied.")
                        created = PaymentService.allocate_receipt_oldest_first(
                            receipt=receipt, user=request.user,
                        )
                    total = sum((row.amount for row in created), Decimal("0"))
                    results.append({
                        "id": receipt.pk,
                        "number": receipt.number,
                        "status": "applied" if created else "skipped",
                        "allocated": str(total),
                        "message": "" if created else "No open invoice to apply it to.",
                    })
                except (BusinessRuleError, ValidationError, IntegrityError) as exc:
                    detail = getattr(exc, "detail", None)
                    message = str(detail if detail is not None else exc)
                    results.append({
                        "id": receipt.pk, "number": receipt.number, "status": "failed",
                        "allocated": "0.00", "message": message,
                    })
            self._audit_raw("BULK_ALLOCATE", ",".join(str(i) for i in ids)[:200])
            return Response({"results": sorted(results, key=lambda r: r["id"])})

        return wrap_idempotent(request=request, company=company, scope="receipt_bulk_allocate", build=run)

    @action(detail=True, methods=["post"], url_path="set-cheque-status")
    def set_cheque_status(self, request, pk=None):
        bank_charge = None
        if any(key in request.data for key in ("bank_charge", "bankCharge", "dishonour_fee")):
            bank_charge = request.data.get("bank_charge")
            if bank_charge is None:
                bank_charge = request.data.get("bankCharge")
            if bank_charge is None:
                bank_charge = request.data.get("dishonour_fee")
        receipt = PaymentService.set_cheque_status(
            receipt=self.get_object(),
            cheque_status=request.data.get("cheque_status") or request.data.get("chequeStatus") or "",
            user=request.user,
            bank_charge=bank_charge,
        )
        self._audit("CHEQUE_STATUS", receipt)
        return Response(self.get_serializer(receipt).data)


class CustomerAdvanceRefundViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Advances handed back to customers. Created from a receipt (``refund-advance``); voided here."""

    queryset = CustomerAdvanceRefund.objects.select_related("receipt", "bank_account")
    serializer_class = AdvanceRefundLineSerializer
    permission_classes = [IsAuthenticated, HasCompany]

    def get_permissions(self):
        if self.action == "void":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces()]

    @property
    def company(self):
        return get_company_user(self.request).company

    def get_queryset(self):
        qs = self.queryset.filter(company=self.company)
        receipt = self.request.query_params.get("receipt")
        if receipt:
            if not receipt.isdigit():
                raise ValidationError({"receipt": "Use a receipt id."})
            qs = qs.filter(receipt_id=int(receipt))
        return qs

    @extend_schema(request=None, responses=AdvanceRefundLineSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        refund = self.get_object()

        def run():
            voided = PaymentService.void_advance_refund(
                refund=refund, user=request.user, reason=request.data.get("reason") or "",
            )
            AuditService.log(
                company=self.company, user=request.user, action="VOID",
                entity_type="CustomerAdvanceRefund", entity_id=voided.pk,
            )
            return Response(AdvanceRefundLineSerializer(voided).data)

        return wrap_idempotent(request=request, company=self.company, scope="advance_refund_void", build=run)


class SupplierPaymentViewSet(CompanyScopedViewSet):
    queryset = SupplierPayment.objects.select_related("supplier", "bank_account").prefetch_related(
        "allocations"
    )
    serializer_class = SupplierPaymentSerializer
    http_method_names = ["get", "post"]

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), HasCompany(), CanCreatePayments()]
        if self.action == "void":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if self.action == "set_cheque_status":
            return [IsAuthenticated(), HasCompany(), CanCreatePayments()]
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        raw_supplier = self.request.query_params.get("supplier")
        if raw_supplier:
            try:
                qs = qs.filter(supplier_id=int(raw_supplier))
            except (TypeError, ValueError):
                raise BusinessRuleError("Invalid supplier ID.")
        return qs

    def create(self, request, *args, **kwargs):
        raw_key = (request.headers.get("Idempotency-Key") or "").strip()
        if raw_key:
            claimed = begin_record(
                company=self.company, scope="supplier_payment_create", raw_key=raw_key,
                fingerprint=request_fingerprint(request),
            )
            if isinstance(claimed, Response):
                return claimed

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            from reporting.gst_periods import assert_period_allows_money_amend, period_complete_warning

            assert_period_allows_money_amend(self.company, serializer.validated_data.get("payment_date"))
            warning = period_complete_warning(self.company, serializer.validated_data.get("payment_date"))
            with transaction.atomic():
                payment = PaymentService.create_supplier_payment(
                    company=self.company,
                    supplier=serializer.validated_data["supplier"],
                    amount=serializer.validated_data["amount"],
                    mode=serializer.validated_data.get("mode", "CASH"),
                    payment_date=serializer.validated_data.get("payment_date"),
                    reference=serializer.validated_data.get("reference", ""),
                    utr=serializer.validated_data.get("utr", ""),
                    notes=serializer.validated_data.get("notes", ""),
                    bank_account=serializer.validated_data.get("bank_account"),
                    tds_section=serializer.validated_data.get("tds_section", ""),
                    tds_rate=serializer.validated_data.get("tds_rate"),
                    tds_amount=serializer.validated_data.get("tds_amount"),
                    user=request.user,
                    cheque_number=serializer.validated_data.get("cheque_number", ""),
                    cheque_bank_name=serializer.validated_data.get("cheque_bank_name", ""),
                    cheque_date=serializer.validated_data.get("cheque_date"),
                    cheque_image=serializer.validated_data.get("cheque_image"),
                    gstin_hold_override=str(request.data.get("gstin_hold_override") or "").lower() in (
                        "true", "1", "yes",
                    ),
                    gstin_hold_reason=str(request.data.get("gstin_hold_reason") or ""),
                )
                if (
                    str(serializer.validated_data.get("mode", "CASH")).upper() == "CASH"
                    and serializer.validated_data.get("paid_from_till")
                ):
                    from sales.pos_shift import mark_paid_from_till

                    mark_paid_from_till(payment, self.company, request.user)
        except Exception:
            if raw_key:
                release_record(company=self.company, scope="supplier_payment_create", raw_key=raw_key)
            raise
        self._audit("CREATE", payment)
        data = self.get_serializer(payment).data
        if warning:
            data["warnings"] = [warning]
        response = Response(data, status=status.HTTP_201_CREATED)
        if raw_key:
            store_record(
                company=self.company,
                scope="supplier_payment_create",
                raw_key=raw_key,
                response=response,
                resource_id=str(payment.pk),
            )
        return response

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        payment = PaymentService.void_supplier_payment(
            payment=self.get_object(),
            user=request.user,
            reason=(request.data.get("reason") or "").strip(),
        )
        self._audit("VOID", payment)
        return Response(self.get_serializer(payment).data)

    @action(detail=True, methods=["post"], url_path="set-cheque-status")
    def set_cheque_status(self, request, pk=None):
        payment = PaymentService.set_supplier_cheque_status(
            payment=self.get_object(),
            cheque_status=request.data.get("cheque_status") or request.data.get("chequeStatus") or "",
            user=request.user,
        )
        self._audit("CHEQUE_STATUS", payment)
        return Response(self.get_serializer(payment).data)


class PaymentAllocationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = PaymentAllocation.objects.all()
    serializer_class = PaymentAllocationSerializer
    permission_classes = [IsAuthenticated, HasCompany]

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), HasCompany(), CanCreatePayments()]
        if self.action == "unallocate":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces()]
        return super().get_permissions()

    @property
    def company(self):
        return get_company_user(self.request).company

    def get_queryset(self):
        qs = self.queryset.filter(company=self.company)
        if self.request.query_params.get("receipt"):
            qs = qs.filter(receipt_id=self.request.query_params["receipt"])
        if self.request.query_params.get("supplier_payment"):
            qs = qs.filter(supplier_payment_id=self.request.query_params["supplier_payment"])
        if self.request.query_params.get("sales_invoice"):
            qs = qs.filter(sales_invoice_id=self.request.query_params["sales_invoice"])
        if self.request.query_params.get("purchase_invoice"):
            qs = qs.filter(purchase_invoice_id=self.request.query_params["purchase_invoice"])
        return qs

    def create(self, request, *args, **kwargs):
        # B4-006: honour Idempotency-Key like the receipt / supplier-payment
        # creates do, and translate the partial-unique IntegrityError on a
        # duplicate (receipt, invoice) into a clean 4xx instead of a 500.
        raw_key = require_idempotency_key(request)
        if raw_key:
            claimed = begin_record(
                company=self.company, scope="allocation_create", raw_key=raw_key,
                fingerprint=request_fingerprint(request),
            )
            if isinstance(claimed, Response):
                return claimed

        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data

            receipt = data.get("receipt")
            payment = data.get("supplier_payment")
            if not receipt and not payment:
                raise ValidationError("Either 'receipt' or 'supplier_payment' is required.")
            if receipt and payment:
                raise ValidationError("Provide exactly one of 'receipt' or 'supplier_payment'.")
            if receipt and receipt.company_id != self.company.id:
                raise BusinessRuleError("Invalid receipt reference.")
            if payment and payment.company_id != self.company.id:
                raise BusinessRuleError("Invalid payment reference.")
            sales_invoice = data.get("sales_invoice")
            if sales_invoice and sales_invoice.company_id != self.company.id:
                raise BusinessRuleError("Invalid sales invoice reference.")
            purchase_invoice = data.get("purchase_invoice")
            if purchase_invoice and purchase_invoice.company_id != self.company.id:
                raise BusinessRuleError("Invalid purchase invoice reference.")

            from reporting.gst_periods import assert_period_allows_money_amend, period_complete_warning

            gate_date = None
            if receipt is not None:
                gate_date = receipt.receipt_date
            elif payment is not None:
                gate_date = payment.payment_date
            assert_period_allows_money_amend(self.company, gate_date)
            warning = period_complete_warning(self.company, gate_date)

            try:
                if receipt:
                    allocation = PaymentService.allocate_receipt(
                        receipt=receipt,
                        sales_invoice=data["sales_invoice"],
                        amount=data["amount"],
                        user=request.user,
                    )
                else:
                    allocation = PaymentService.allocate_supplier_payment(
                        payment=payment,
                        purchase_invoice=data["purchase_invoice"],
                        amount=data["amount"],
                        user=request.user,
                    )
            except IntegrityError as exc:
                raise BusinessRuleError(
                    "This receipt/payment is already allocated to that invoice."
                ) from exc
        except Exception:
            if raw_key:
                release_record(company=self.company, scope="allocation_create", raw_key=raw_key)
            raise

        AuditService.log(
            company=self.company,
            user=request.user,
            action="CREATE",
            entity_type="PaymentAllocation",
            entity_id=allocation.id,
        )
        data = self.get_serializer(allocation).data
        if warning:
            data["warnings"] = [warning]
        response = Response(data, status=status.HTTP_201_CREATED)
        if raw_key:
            store_record(
                company=self.company,
                scope="allocation_create",
                raw_key=raw_key,
                response=response,
                resource_id=str(allocation.pk),
            )
        return response

    @action(detail=True, methods=["post"])
    def unallocate(self, request, pk=None):
        raw_key = request.headers.get("Idempotency-Key") or request.headers.get("X-Idempotency-Key")
        if raw_key:
            record_or_response = begin_record(
                company=self.company, scope="allocation_unallocate", raw_key=raw_key,
                fingerprint=request_fingerprint(request),
            )
            if isinstance(record_or_response, Response):
                return record_or_response

        try:
            reason = None
            if "reason" in request.data:
                # The receipts screen always sends one. When it is sent it must say something.
                reason = " ".join(str(request.data.get("reason") or "").split())
                if not (3 <= len(reason) <= 500):
                    raise ValidationError({"reason": "Enter a reason of 3 to 500 characters."})
            allocation = PaymentService.reverse_allocation(allocation=self.get_object(), user=request.user)
        except Exception:
            if raw_key:
                release_record(company=self.company, scope="allocation_unallocate", raw_key=raw_key)
            raise

        AuditService.log(
            company=self.company,
            user=request.user,
            action="UNALLOCATE",
            entity_type="PaymentAllocation",
            entity_id=allocation.id,
            metadata={"reason": reason} if reason else None,
        )
        response = Response(self.get_serializer(allocation).data)
        if raw_key:
            store_record(
                company=self.company,
                scope="allocation_unallocate",
                raw_key=raw_key,
                response=response,
                resource_id=str(allocation.pk),
            )
        return response


class PaymentLinkViewSet(CompanyScopedViewSet):
    queryset = PaymentLink.objects.select_related("customer", "sales_invoice")
    serializer_class = PaymentLinkSerializer
    http_method_names = ["get", "post"]

    def get_permissions(self):
        # BB-000268: create/mutate → CanCreatePayments; cancel → CanCancelDocuments.
        action = getattr(self, "action", None)
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if action in ("create", "mark_sent", "share"):
            return [IsAuthenticated(), HasCompany(), CanCreatePayments()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        from sales.models import SalesInvoice

        inv_id = request.data.get("sales_invoice")
        customer_id = request.data.get("customer")
        amount = request.data.get("amount")
        sales_invoice = None
        customer = None
        if inv_id:
            sales_invoice = SalesInvoice.objects.filter(company=self.company, pk=inv_id).first()
            if not sales_invoice:
                raise BusinessRuleError("Invoice not found.")
        if customer_id:
            from masters.models import Customer

            customer = Customer.objects.filter(company=self.company, pk=customer_id).first()
        if amount is None and sales_invoice:
            from ledgers.services import LedgerService

            amount = LedgerService.sales_invoice_outstanding(sales_invoice)
        link = PaymentService.create_payment_link(
            company=self.company,
            amount=amount,
            sales_invoice=sales_invoice,
            customer=customer,
            allow_partial=bool(request.data.get("allow_partial", False)),
            expires_hours=int(request.data.get("expires_hours") or 72),
            provider=request.data.get("provider") or None,
            notes=request.data.get("notes") or "",
            user=request.user,
            public_base_url=public_frontend_base_url(request),
        )
        self._audit("CREATE", link)
        return Response(self.get_serializer(link).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        link = self.get_object()
        link = PaymentService.cancel_payment_link(link=link, user=request.user)
        self._audit("UPDATE", link)
        return Response(self.get_serializer(link).data)

    @action(detail=True, methods=["post"], url_path="mark-sent")
    def mark_sent(self, request, pk=None):
        link = self.get_object()
        if link.status == PaymentLinkStatus.CREATED:
            link.status = PaymentLinkStatus.SENT
            link.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(link).data)

    @action(detail=True, methods=["post"], url_path="share")
    def share(self, request, pk=None):
        link = self.get_object()
        channel = (request.data.get("channel") or "WHATSAPP").upper()
        recipient = (request.data.get("recipient") or "").strip()
        if not recipient:
            raise BusinessRuleError("recipient is required.")
        notification = PaymentService.share_payment_link(
            link=link,
            channel=channel,
            recipient=recipient,
            user=request.user,
            public_base_url=public_frontend_base_url(request),
        )
        link.refresh_from_db()
        return Response(
            {
                "link": self.get_serializer(link).data,
                "notification_id": notification.id,
                "share_link": getattr(notification, "share_link", "") or "",
                "status": notification.status,
                "mode": getattr(notification, "delivery_mode", None)
                or ("cloud" if notification.status == "SENT" else "link"),
            }
        )


class GatewayPaymentViewSet(CompanyScopedViewSet):
    queryset = GatewayPayment.objects.select_related("payment_link")
    serializer_class = GatewayPaymentSerializer
    http_method_names = ["get", "post"]

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "refund":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if action == "retry_books":
            return [IsAuthenticated(), HasCompany(), CanCreatePayments()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        link_id = self.request.query_params.get("payment_link")
        if link_id:
            qs = qs.filter(payment_link_id=link_id)
        st = self.request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        return qs

    @action(detail=True, methods=["post"], url_path="refund")
    def refund(self, request, pk=None):
        # B4-013: without a request-level idempotency claim, a double-submit
        # (e.g. a UI double-click) races two refund_gateway_payment() calls
        # against the same pre-unwind "remaining" balance -- each gets its own
        # provider idempotency key and books entry, refunding/unwinding twice.
        raw_key = (request.headers.get("Idempotency-Key") or "").strip()
        if raw_key:
            claimed = begin_record(
                company=self.company, scope="gateway_payment_refund", raw_key=raw_key,
                fingerprint=request_fingerprint(request),
            )
            if isinstance(claimed, Response):
                return claimed
        gp = self.get_object()
        amount = request.data.get("amount")
        reason = request.data.get("reason") or ""
        parsed_amount = None
        if amount is not None and str(amount).strip() != "":
            try:
                parsed_amount = Decimal(str(amount))
            except (InvalidOperation, TypeError, ValueError):
                raise ValidationError({"amount": "Enter a valid refund amount."})
        try:
            gp = PaymentService.refund_gateway_payment(
                gateway_payment=gp,
                amount=parsed_amount,
                user=request.user,
                reason=reason,
            )
        except Exception:
            if raw_key:
                release_record(company=self.company, scope="gateway_payment_refund", raw_key=raw_key)
            raise
        self._audit("UPDATE", gp)
        response = Response(GatewayPaymentSerializer(gp).data)
        if raw_key:
            store_record(
                company=self.company,
                scope="gateway_payment_refund",
                raw_key=raw_key,
                response=response,
                resource_id=str(gp.pk),
            )
        return response

    @action(detail=True, methods=["post"], url_path="retry-books")
    def retry_books(self, request, pk=None):
        gp = self.get_object()
        gp = PaymentService.finalize_gateway_payment(
            company=gp.company,
            provider=gp.provider,
            provider_payment_id=gp.provider_payment_id,
            amount=gp.amount,
            fee=gp.fee,
            payment_link=gp.payment_link,
            raw_payload=gp.raw_payload,
            user=request.user,
        )
        self._audit("UPDATE", gp)
        return Response(GatewayPaymentSerializer(gp).data)


class PaymentHealthView(APIView):
    # BB-000416: payment/financial surfaces — not HasCompany-only.
    permission_classes = [IsAuthenticated, HasCompany, CanViewPaymentSurfaces]

    def get(self, request):
        company = get_company_user(request).company
        return Response(PaymentService.payment_health(company=company))


class CollectionRiskView(APIView):
    """A-07 per-customer collection risk (ageing + recommended next step)."""

    permission_classes = [IsAuthenticated, HasCompany, CanViewPaymentSurfaces]

    def get(self, request, customer_id=None):
        from masters.models import Customer
        from payments.dunning import customer_risk_snapshot, list_customer_risk

        company = get_company_user(request).company
        if customer_id is not None:
            customer = Customer.objects.filter(company=company, pk=customer_id).first()
            if customer is None:
                raise BusinessRuleError("Customer not found.")
            return Response(customer_risk_snapshot(company, customer))
        return Response({"results": list_customer_risk(company)})


class UpiQrView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanCreatePayments]

    def post(self, request):
        company = get_company_user(request).company
        ser = UpiQrSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(ser.create_payload(company))


class BankStatementViewSet(CompanyScopedViewSet):
    queryset = BankStatement.objects.select_related("bank_account").prefetch_related("lines")
    serializer_class = BankStatementSerializer
    http_method_names = ["get", "post"]

    def get_permissions(self):
        # BB-000268: upload/commit require payment create capability.
        action = getattr(self, "action", None)
        if action in ("upload", "commit", "create"):
            return [IsAuthenticated(), HasCompany(), CanCreatePayments()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces()]
        # B4-016: voiding an imported statement is a cancel-shaped action.
        if action == "void":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        return super().get_permissions()

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        bank_account_id = request.data.get("bank_account")
        preset = request.data.get("preset") or "generic"
        upload = request.FILES.get("file")
        if not bank_account_id or not upload:
            raise BusinessRuleError("bank_account and file are required.")
        bank_account = BankAccount.objects.filter(company=self.company, pk=bank_account_id).first()
        if not bank_account:
            raise BusinessRuleError("Bank account not found.")
        content = upload.read()
        rows, skipped = parse_bank_csv(content, preset=preset)
        if not rows:
            detail = "No parsable rows found in the CSV."
            if skipped:
                detail += " Skipped: " + "; ".join(skipped[:10])
            raise BusinessRuleError(detail)

        with transaction.atomic():
            statement = BankStatement.objects.create(
                company=self.company,
                bank_account=bank_account,
                period_start=min(r["txn_date"] for r in rows),
                period_end=max(r["txn_date"] for r in rows),
                source_filename=getattr(upload, "name", "")[:255],
                status=BankStatementStatus.PREVIEW,
                preset=preset,
                created_by=request.user,
                updated_by=request.user,
            )
            for r in rows:
                BankStatementLine.objects.create(
                    company=self.company,
                    statement=statement,
                    txn_date=r["txn_date"],
                    amount=r["amount"],
                    narration=r["narration"],
                    utr=r["utr"],
                    line_hash=r["line_hash"],
                    match_status=BankLineMatchStatus.UNMATCHED,
                    created_by=request.user,
                    updated_by=request.user,
                )
        self._audit("CREATE", statement)
        data = self.get_serializer(statement).data
        if skipped:
            # B4-015: don't let a partial import look "complete".
            data["skipped_rows"] = skipped
            data["skipped_count"] = len(skipped)
            data["warning"] = (
                f"{len(rows)} rows imported, {len(skipped)} skipped "
                f"({'; '.join(skipped[:5])}{'…' if len(skipped) > 5 else ''})."
            )
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="commit")
    def commit(self, request, pk=None):
        def _run():
            statement = self.get_object()
            if statement.status == BankStatementStatus.COMMITTED:
                return Response(self.get_serializer(statement).data)
            statement.status = BankStatementStatus.COMMITTED
            statement.save(update_fields=["status", "updated_at"])

            # B4-018: optional exact auto-match -- used to call suggest_matches
            # (2 queries: a windowed candidate scan + a fresh ReconMatch
            # exclusion query) plus, for any line with a single high-confidence
            # suggestion, is_exact_unique_suggestion's own
            # CustomerReceipt/SupplierPayment.filter(pk=...) UTR lookup, all
            # per line. The exclusion sets and a UTR map covering the whole
            # statement's window are now fetched once and reused across every
            # line; the exclusion sets are updated in-memory as matches are
            # confirmed so a receipt/payment auto-matched to an earlier line in
            # this same loop can't also be suggested for a later one.
            if getattr(self.company, "auto_match_bank_exact", False):
                unmatched_lines = list(statement.lines.filter(match_status=BankLineMatchStatus.UNMATCHED))
                if unmatched_lines:
                    matched_receipt_ids = set(
                        ReconMatch.objects.filter(company=self.company, receipt__isnull=False)
                        .values_list("receipt_id", flat=True)
                    )
                    matched_supplier_payment_ids = set(
                        ReconMatch.objects.filter(company=self.company, supplier_payment__isnull=False)
                        .values_list("supplier_payment_id", flat=True)
                    )
                    window_start = min(line.txn_date for line in unmatched_lines) - timedelta(days=14)
                    window_end = max(line.txn_date for line in unmatched_lines) + timedelta(days=14)
                    receipt_utr_map = {
                        rid: normalize_utr(utr)
                        for rid, utr in CustomerReceipt.objects.filter(
                            company=self.company, status="POSTED",
                            receipt_date__gte=window_start, receipt_date__lte=window_end,
                        ).values_list("id", "utr")
                    }
                    supplier_payment_utr_map = {
                        pid: normalize_utr(utr)
                        for pid, utr in SupplierPayment.objects.filter(
                            company=self.company, status=SupplierPaymentStatus.POSTED,
                            payment_date__gte=window_start, payment_date__lte=window_end,
                        ).values_list("id", "utr")
                    }
                    for line in unmatched_lines:
                        suggestions = suggest_matches(
                            company=self.company,
                            line=line,
                            exclude_receipt_ids=matched_receipt_ids,
                            exclude_supplier_payment_ids=matched_supplier_payment_ids,
                        )
                        if is_exact_unique_suggestion(
                            suggestions, line,
                            receipt_utr_map=receipt_utr_map,
                            supplier_payment_utr_map=supplier_payment_utr_map,
                        ):
                            s = suggestions[0]
                            self._confirm_match(
                                line=line,
                                receipt_id=s["id"] if s["type"] == "receipt" else None,
                                payment_id=s["id"] if s["type"] == "supplier_payment" else None,
                                confidence=s["confidence"],
                                user=request.user,
                                notes="auto_exact",
                            )
                            if s["type"] == "receipt":
                                matched_receipt_ids.add(s["id"])
                            else:
                                matched_supplier_payment_ids.add(s["id"])
            self._audit("UPDATE", statement)
            return Response(self.get_serializer(statement).data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="statement_commit",
            build=_run,
        )

    @action(detail=True, methods=["post"], url_path="void")
    def void(self, request, pk=None):
        """B4-016: a statement imported for the wrong account/period had no
        way to be voided -- BankStatementStatus.VOID existed but nothing
        transitioned to it. Refuse while any line is MATCHED so voiding
        never silently orphans a live ReconMatch; the operator unmatches
        those lines first (recon/unmatch) so the effect stays a simple,
        auditable state change with no cascading side effects."""
        statement = self.get_object()
        if statement.status == BankStatementStatus.VOID:
            return Response(self.get_serializer(statement).data)
        if statement.lines.filter(match_status=BankLineMatchStatus.MATCHED).exists():
            raise BusinessRuleError(
                "Unmatch every reconciled line on this statement before voiding it."
            )
        statement.status = BankStatementStatus.VOID
        statement.updated_by = request.user
        statement.save(update_fields=["status", "updated_by", "updated_at"])
        self._audit("VOID", statement)
        return Response(self.get_serializer(statement).data)

    def _confirm_match(self, *, line, receipt_id, payment_id, confidence, user, notes="", allow_amount_mismatch=False):
        receipt = None
        payment = None
        if receipt_id:
            receipt = CustomerReceipt.objects.filter(company=self.company, pk=receipt_id).first()
            if not receipt:
                raise BusinessRuleError("Receipt not found.")
        if payment_id:
            payment = SupplierPayment.objects.filter(company=self.company, pk=payment_id).first()
            if not payment:
                raise BusinessRuleError("Supplier payment not found.")
        if bool(receipt) == bool(payment):
            raise BusinessRuleError("Provide exactly one of receipt or supplier_payment.")
        # BB-000415: require amount equality unless Owner override.
        target_amount = receipt.amount if receipt else payment.amount
        line_abs = abs(Decimal(str(line.amount)))
        target_abs = abs(Decimal(str(target_amount)))
        if line_abs != target_abs:
            cu = get_company_user(self.request) if getattr(self, "request", None) else None
            is_owner = bool(cu and cu.role == "OWNER")
            if not (allow_amount_mismatch and is_owner):
                raise BusinessRuleError(
                    f"Bank line amount {line_abs} does not match target {target_abs}. "
                    "Owner may override with allow_amount_mismatch=true."
                )
            notes = (notes or "") + " | amount_mismatch_override"
        with transaction.atomic():
            line = BankStatementLine.objects.select_for_update().get(pk=line.pk)
            if line.match_status == BankLineMatchStatus.MATCHED:
                return line.recon_match
            if receipt and ReconMatch.objects.select_for_update().filter(receipt=receipt).exists():
                raise BusinessRuleError("This receipt is already matched to a bank line.")
            if payment and ReconMatch.objects.select_for_update().filter(
                supplier_payment=payment
            ).exists():
                raise BusinessRuleError("This supplier payment is already matched to a bank line.")
            match = ReconMatch.objects.create(
                company=self.company,
                line=line,
                receipt=receipt,
                supplier_payment=payment,
                confidence=confidence,
                matched_by=user,
                notes=notes,
                created_by=user,
                updated_by=user,
            )
            line.match_status = BankLineMatchStatus.MATCHED
            line.save(update_fields=["match_status", "updated_at"])
            # QOS-0043: learn this payee's narration pattern for future suggestions.
            from .recon import remember_payee

            remember_payee(
                company=self.company,
                line=line,
                customer_id=receipt.customer_id if receipt else None,
                supplier_id=payment.supplier_id if payment else None,
            )
        return match


class ReconViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, HasCompany, CanCreatePayments]

    def get_permissions(self):
        # B4-016: undoing a confirmed match is a cancel-shaped action.
        if getattr(self, "action", None) == "unmatch":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        return super().get_permissions()

    @property
    def company(self):
        return get_company_user(self.request).company

    def list(self, request):
        """Suggestion queue for unmatched committed lines (compute-only; BB-000754)."""
        lines = (
            BankStatementLine.objects.filter(
                company=self.company,
                match_status__in=[BankLineMatchStatus.UNMATCHED, BankLineMatchStatus.SUGGESTED],
                statement__status=BankStatementStatus.COMMITTED,
            )
            .select_related("statement", "statement__bank_account")
            .order_by("txn_date")[:100]
        )
        # B4-018: fetch the "already matched" exclusion sets once instead of
        # suggest_matches re-querying ReconMatch for every one of up to 100 lines.
        matched_receipt_ids = set(
            ReconMatch.objects.filter(company=self.company, receipt__isnull=False)
            .values_list("receipt_id", flat=True)
        )
        matched_supplier_payment_ids = set(
            ReconMatch.objects.filter(company=self.company, supplier_payment__isnull=False)
            .values_list("supplier_payment_id", flat=True)
        )
        out = []
        for line in lines:
            suggestions = suggest_matches(
                company=self.company,
                line=line,
                exclude_receipt_ids=matched_receipt_ids,
                exclude_supplier_payment_ids=matched_supplier_payment_ids,
            )
            # BB-000754: GET must not persist SUGGESTED — compute-only.
            display_status = line.match_status
            if suggestions and line.match_status == BankLineMatchStatus.UNMATCHED:
                display_status = BankLineMatchStatus.SUGGESTED
            out.append(
                {
                    "line": {
                        "id": line.id,
                        "txn_date": line.txn_date,
                        "amount": str(line.amount),
                        "narration": line.narration,
                        "utr": line.utr,
                        "match_status": display_status,
                        "bank_account": line.statement.bank_account.name,
                        "statement_id": line.statement_id,
                    },
                    "suggestions": suggestions,
                }
            )
        return Response({"results": out})

    @action(detail=False, methods=["post"], url_path="suggest")
    def suggest(self, request):
        """BB-000754: optionally persist SUGGESTED for unmatched lines with matches."""
        lines = (
            BankStatementLine.objects.filter(
                company=self.company,
                match_status=BankLineMatchStatus.UNMATCHED,
                statement__status=BankStatementStatus.COMMITTED,
            )
            .select_related("statement", "statement__bank_account")
            .order_by("txn_date")[:100]
        )
        # B4-018: same batching as list() above.
        matched_receipt_ids = set(
            ReconMatch.objects.filter(company=self.company, receipt__isnull=False)
            .values_list("receipt_id", flat=True)
        )
        matched_supplier_payment_ids = set(
            ReconMatch.objects.filter(company=self.company, supplier_payment__isnull=False)
            .values_list("supplier_payment_id", flat=True)
        )
        updated = 0
        out = []
        for line in lines:
            suggestions = suggest_matches(
                company=self.company,
                line=line,
                exclude_receipt_ids=matched_receipt_ids,
                exclude_supplier_payment_ids=matched_supplier_payment_ids,
            )
            if suggestions:
                line.match_status = BankLineMatchStatus.SUGGESTED
                line.updated_by = request.user
                # B4-033: stamp updated_at/updated_by like _confirm_match does.
                line.save(update_fields=["match_status", "updated_by", "updated_at"])
                updated += 1
            out.append(
                {
                    "line": {
                        "id": line.id,
                        "txn_date": line.txn_date,
                        "amount": str(line.amount),
                        "narration": line.narration,
                        "utr": line.utr,
                        "match_status": line.match_status,
                        "bank_account": line.statement.bank_account.name,
                        "statement_id": line.statement_id,
                    },
                    "suggestions": suggestions,
                }
            )
        return Response({"updated": updated, "results": out})

    @action(detail=False, methods=["post"], url_path="confirm")
    def confirm(self, request):
        line_id = request.data.get("line")
        receipt_id = request.data.get("receipt")
        payment_id = request.data.get("supplier_payment")
        confidence = request.data.get("confidence") or 0
        line = BankStatementLine.objects.filter(company=self.company, pk=line_id).first()
        if not line:
            raise BusinessRuleError("Statement line not found.")
        vs = BankStatementViewSet()
        vs.request = request
        vs.format_kwarg = None
        match = vs._confirm_match(
            line=line,
            receipt_id=receipt_id,
            payment_id=payment_id,
            confidence=confidence,
            user=request.user,
            notes="manual",
            allow_amount_mismatch=bool(request.data.get("allow_amount_mismatch")),
        )
        AuditService.log(
            company=self.company,
            user=request.user,
            action="CREATE",
            entity_type="ReconMatch",
            entity_id=match.id,
        )
        return Response(ReconMatchSerializer(match).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="bulk-accept-exact")
    def bulk_accept_exact(self, request):
        """QOS-0039: confirm every unmatched committed line whose sole
        suggestion is EXACT-class (>=90 confidence, exact amount, a hard UTR/
        reference anchor — same bar as the commit-time auto-match) in one
        call. Fuzzy/ambiguous suggestions are left for manual review. Each
        resulting ReconMatch is undoable individually via the existing
        `recon/unmatch` action, so this needs no separate undo mechanism."""
        lines = (
            BankStatementLine.objects.filter(
                company=self.company,
                match_status__in=[BankLineMatchStatus.UNMATCHED, BankLineMatchStatus.SUGGESTED],
                statement__status=BankStatementStatus.COMMITTED,
            )
            .select_related("statement", "statement__bank_account")
            .order_by("txn_date")[:100]
        )
        matched_receipt_ids = set(
            ReconMatch.objects.filter(company=self.company, receipt__isnull=False)
            .values_list("receipt_id", flat=True)
        )
        matched_supplier_payment_ids = set(
            ReconMatch.objects.filter(company=self.company, supplier_payment__isnull=False)
            .values_list("supplier_payment_id", flat=True)
        )
        if not lines:
            return Response({"accepted": [], "accepted_count": 0})
        window_start = min(line.txn_date for line in lines) - timedelta(days=14)
        window_end = max(line.txn_date for line in lines) + timedelta(days=14)
        receipt_utr_map = {
            rid: normalize_utr(utr)
            for rid, utr in CustomerReceipt.objects.filter(
                company=self.company, status="POSTED",
                receipt_date__gte=window_start, receipt_date__lte=window_end,
            ).values_list("id", "utr")
        }
        supplier_payment_utr_map = {
            pid: normalize_utr(utr)
            for pid, utr in SupplierPayment.objects.filter(
                company=self.company, status=SupplierPaymentStatus.POSTED,
                payment_date__gte=window_start, payment_date__lte=window_end,
            ).values_list("id", "utr")
        }
        vs = BankStatementViewSet()
        vs.request = request
        vs.format_kwarg = None
        accepted = []
        for line in lines:
            suggestions = suggest_matches(
                company=self.company,
                line=line,
                exclude_receipt_ids=matched_receipt_ids,
                exclude_supplier_payment_ids=matched_supplier_payment_ids,
            )
            if not is_exact_unique_suggestion(
                suggestions, line,
                receipt_utr_map=receipt_utr_map,
                supplier_payment_utr_map=supplier_payment_utr_map,
            ):
                continue
            s = suggestions[0]
            match = vs._confirm_match(
                line=line,
                receipt_id=s["id"] if s["type"] == "receipt" else None,
                payment_id=s["id"] if s["type"] == "supplier_payment" else None,
                confidence=s["confidence"],
                user=request.user,
                notes="bulk_accept_exact",
            )
            if s["type"] == "receipt":
                matched_receipt_ids.add(s["id"])
            else:
                matched_supplier_payment_ids.add(s["id"])
            AuditService.log(
                company=self.company,
                user=request.user,
                action="CREATE",
                entity_type="ReconMatch",
                entity_id=match.id,
                description="bulk_accept_exact",
            )
            accepted.append({"line": line.id, "match": match.id})
        return Response({"accepted": accepted, "accepted_count": len(accepted)})

    @action(detail=False, methods=["get"], url_path="needs-review")
    def needs_review(self, request):
        """Matches whose receipt later bounced: the bank took the money back, so look again."""
        rows = (
            ReconMatch.objects.filter(company=self.company, needs_review=True, receipt__isnull=False)
            .select_related("line", "line__statement__bank_account", "receipt", "receipt__customer")
            .order_by("-matched_at")[:200]
        )
        return Response({
            "results": [
                {
                    "match": m.id,
                    "line": m.line_id,
                    "line_date": m.line.txn_date,
                    "line_amount": str(m.line.amount),
                    "bank_account": m.line.statement.bank_account.name,
                    "receipt": m.receipt_id,
                    "receipt_number": m.receipt.number,
                    "customer_name": m.receipt.customer.name,
                    "reason": m.review_reason,
                }
                for m in rows
            ]
        })

    @action(detail=False, methods=["post"], url_path="match-return")
    def match_return(self, request):
        """A bounced cheque reaches the statement as a second, DEBIT line; the credit stays.

        Link that debit line to the bounced receipt: the line is marked matched, the bank line
        of the bounce's reversal journal is reconciled to it, and the receipt's original match
        stops asking for review, so both statement lines reconcile and nothing is left over.
        """
        from accounting.models import JournalEntry, JournalLine

        line_id = request.data.get("line")
        receipt_id = request.data.get("receipt")
        with transaction.atomic():
            line = (
                BankStatementLine.objects.select_for_update()
                .filter(company=self.company, pk=line_id)
                .first()
            )
            receipt = CustomerReceipt.objects.filter(company=self.company, pk=receipt_id).first()
            if line is None or receipt is None:
                raise BusinessRuleError("Statement line and receipt are required.")
            if receipt.mode != PaymentMode.CHEQUE or receipt.cheque_status != ChequeStatus.BOUNCED:
                raise BusinessRuleError(
                    "Only a bounced cheque has a return line.", code="match_return_not_bounced"
                )
            if line.amount >= 0:
                raise BusinessRuleError(
                    "A cheque return is a debit line (a negative amount) on the statement.",
                    code="match_return_not_debit",
                )
            if abs(abs(line.amount) - receipt.amount) > Decimal("0.01"):
                raise BusinessRuleError(
                    "The return line must equal the cheque amount.", code="match_return_amount"
                )
            if line.match_status == BankLineMatchStatus.MATCHED:
                raise BusinessRuleError("This statement line is already matched.")
            if receipt.company.accounting_enabled:
                create_entry = JournalEntry.objects.filter(
                    company=self.company, source_type="CUSTOMER_RECEIPT", source_id=receipt.pk,
                    purpose="CREATE",
                ).exclude(reversed_entry__isnull=True).first()
                if create_entry is not None:
                    reversal = create_entry.reversed_entry
                    bank_line = (
                        JournalLine.objects.filter(entry=reversal, credit__gt=0)
                        .exclude(account__code__in=("2300", "5200", "1270"))
                        .order_by("id")
                        .first()
                    )
                    if bank_line is not None and bank_line.bank_statement_line_id is None:
                        bank_line.bank_statement_line = line
                        bank_line.reconciled_at = timezone.now()
                        bank_line.save(update_fields=["bank_statement_line", "reconciled_at"])
            line.match_status = BankLineMatchStatus.MATCHED
            line.updated_by = request.user
            line.save(update_fields=["match_status", "updated_by", "updated_at"])
            cleared = ReconMatch.objects.filter(
                company=self.company, receipt=receipt, needs_review=True
            ).update(needs_review=False, review_reason="")
        AuditService.log(
            company=self.company, user=request.user, action="UPDATE", entity_type="BankStatementLine",
            entity_id=line.pk, description=f"Cheque return matched to receipt {receipt.number}",
        )
        return Response({"line": line.pk, "receipt": receipt.pk, "cleared_reviews": cleared})

    @action(detail=False, methods=["post"], url_path="unmatch")
    def unmatch(self, request):
        """B4-016: undo a confirmed match -- an operator who confirmed the
        wrong receipt/payment (or an auto-match that confirmed wrongly, see
        B4-014) previously had no way to fix it short of direct DB access."""
        line_id = request.data.get("line")
        line = BankStatementLine.objects.filter(company=self.company, pk=line_id).first()
        if not line:
            raise BusinessRuleError("Statement line not found.")
        with transaction.atomic():
            line = BankStatementLine.objects.select_for_update().get(pk=line.pk)
            match = ReconMatch.objects.filter(company=self.company, line=line).first()
            if match is None:
                raise BusinessRuleError("This line is not matched.")
            match_id = match.id
            match.delete()
            line.match_status = BankLineMatchStatus.UNMATCHED
            line.updated_by = request.user
            line.save(update_fields=["match_status", "updated_by", "updated_at"])
        AuditService.log(
            company=self.company,
            user=request.user,
            action="DELETE",
            entity_type="ReconMatch",
            entity_id=match_id,
            description=f"Unmatched bank statement line {line.pk}",
        )
        return Response(BankStatementLineSerializer(line).data)

    @action(detail=False, methods=["post"], url_path="create-receipt-from-line")
    def create_receipt_from_line(self, request):
        line_id = request.data.get("line")
        customer_id = request.data.get("customer")
        line = (
            BankStatementLine.objects.filter(company=self.company, pk=line_id)
            .select_related("statement__bank_account")
            .first()
        )
        if not line or line.amount <= 0:
            raise BusinessRuleError("Credit line required.")
        if line.match_status == BankLineMatchStatus.MATCHED:
            raise BusinessRuleError("This bank line is already matched.")
        from masters.models import Customer

        customer = Customer.objects.filter(company=self.company, pk=customer_id).first()
        if not customer:
            raise BusinessRuleError("Customer required.")
        if customer.is_pos_walk_in:
            # A walk-in has no account to hold the money. Pick the customer who actually paid.
            raise BusinessRuleError(
                "A walk-in customer cannot hold an advance. Pick the customer who paid this amount.",
                code="walkin_full_allocation_required",
            )
        from django.db import transaction

        with transaction.atomic():
            receipt = PaymentService.create_receipt(
                company=self.company,
                customer=customer,
                amount=line.amount,
                mode="BANK",
                receipt_date=line.txn_date,
                reference=line.utr or "",
                utr=line.utr or "",
                notes=f"Bank import: {line.narration[:200]}",
                bank_account=line.statement.bank_account,
                source=PaymentSource.BANK_IMPORT,
                user=request.user,
                warn_utr_duplicate=False,
            )
            vs = BankStatementViewSet()
            vs.request = request
            vs.format_kwarg = None
            vs.kwargs = {}
            match = vs._confirm_match(
                line=line,
                receipt_id=receipt.id,
                payment_id=None,
                confidence=100,
                user=request.user,
                notes="created_from_line",
            )
        return Response(
            {"receipt": CustomerReceiptSerializer(receipt).data, "match": ReconMatchSerializer(match).data},
            status=status.HTTP_201_CREATED,
        )


class GatewaySettingsView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        from payments.gateway import DISABLED_PROVIDERS, sandbox_forbidden_env

        company = get_company_user(request).company
        sandbox_ok = not sandbox_forbidden_env()
        disabled = sorted(set(DISABLED_PROVIDERS) | (set() if sandbox_ok else {"sandbox"}))
        enabled = ["razorpay"] + (["sandbox"] if sandbox_ok else [])
        for p in ("cashfree", "payu"):
            if p not in DISABLED_PROVIDERS:
                enabled.append(p)
        return Response(
            {
                "provider": company.payment_gateway_provider or "razorpay",
                "test_mode": company.payment_gateway_test_mode,
                "credentials_configured": bool(company.payment_gateway_credentials_encrypted),
                "require_payment_reference": company.require_payment_reference,
                "auto_match_bank_exact": company.auto_match_bank_exact,
                "cheque_allocation_on_clearance": company.cheque_allocation_on_clearance,
                "cash_269st_mode": company.cash_269st_mode,
                "advance_gst_treatment": company.advance_gst_treatment,
                "advance_gst_default_rate": (
                    str(Decimal(str(company.advance_gst_default_rate)).quantize(Decimal("0.01")))
                    if company.advance_gst_default_rate is not None else None
                ),
                "enabled_providers": enabled,
                "disabled_providers": disabled,
                "webhook_paths": {
                    "razorpay": f"/api/v1/webhooks/payments/razorpay/?company_id={company.id}",
                    "sandbox": f"/api/v1/webhooks/payments/sandbox/?company_id={company.id}",
                },
            }
        )

    def patch(self, request):
        from payments.gateway import DISABLED_PROVIDERS, sandbox_forbidden_env

        company = get_company_user(request).company
        touched: set[str] = set()  # B4-030: only save the fields we changed
        if "provider" in request.data:
            provider = str(request.data.get("provider") or "razorpay")[:32].lower()
            if provider in DISABLED_PROVIDERS:
                raise BusinessRuleError(
                    f"Payment provider '{provider}' is not enabled. Use razorpay or sandbox."
                )
            if provider == "sandbox" and sandbox_forbidden_env():
                raise BusinessRuleError(
                    "Payment provider 'sandbox' cannot be enabled outside development/test/local."
                )
            company.payment_gateway_provider = provider
            touched.add("payment_gateway_provider")
        if "test_mode" in request.data:
            test_mode = bool(request.data.get("test_mode"))
            if test_mode and sandbox_forbidden_env():
                raise BusinessRuleError(
                    "payment_gateway_test_mode cannot be enabled outside development/test/local."
                )
            company.payment_gateway_test_mode = test_mode
            touched.add("payment_gateway_test_mode")
        if "require_payment_reference" in request.data:
            company.require_payment_reference = bool(request.data.get("require_payment_reference"))
            touched.add("require_payment_reference")
        if "auto_match_bank_exact" in request.data:
            company.auto_match_bank_exact = bool(request.data.get("auto_match_bank_exact"))
            touched.add("auto_match_bank_exact")
        if "cheque_allocation_on_clearance" in request.data:
            company.cheque_allocation_on_clearance = bool(request.data.get("cheque_allocation_on_clearance"))
            touched.add("cheque_allocation_on_clearance")
        if "cash_269st_mode" in request.data:
            mode = str(request.data.get("cash_269st_mode") or "").lower()
            if mode not in ("off", "warn", "block"):
                raise BusinessRuleError("Cash limit check must be off, warn or block.")
            company.cash_269st_mode = mode
            touched.add("cash_269st_mode")
        if "advance_gst_treatment" in request.data:
            treatment = str(request.data.get("advance_gst_treatment") or "").lower()
            if treatment not in ("none", "goods", "services"):
                raise BusinessRuleError("Advance GST treatment must be none, goods or services.")
            company.advance_gst_treatment = treatment
            touched.add("advance_gst_treatment")
        if "advance_gst_default_rate" in request.data:
            raw_rate = request.data.get("advance_gst_default_rate")
            if raw_rate in (None, ""):
                company.advance_gst_default_rate = None
            else:
                try:
                    rate = Decimal(str(raw_rate))
                except InvalidOperation:
                    raise BusinessRuleError("The advance GST rate must be a number.") from None
                if rate < 0 or rate > 40:
                    raise BusinessRuleError("The advance GST rate must be between 0 and 40.")
                company.advance_gst_default_rate = rate
            touched.add("advance_gst_default_rate")
        if request.data.get("clear_credentials"):
            company.payment_gateway_credentials_encrypted = ""
            touched.add("payment_gateway_credentials_encrypted")
        creds = request.data.get("credentials")
        if isinstance(creds, dict):
            existing = decrypt_gateway_credentials(company.payment_gateway_credentials_encrypted or "")
            # BB-000367: ignore empty strings (do not wipe secrets); explicit clear_credentials only.
            existing.update({k: v for k, v in creds.items() if v is not None and str(v).strip() != ""})
            company.payment_gateway_credentials_encrypted = encrypt_gateway_credentials(existing)
            touched.add("payment_gateway_credentials_encrypted")
        if touched:
            company.save(update_fields=[*touched, "updated_at"])
        AuditService.log(
            company=company,
            user=request.user,
            action="UPDATE",
            entity_type="PaymentGatewaySettings",
            entity_id=company.id,
        )
        return self.get(request)


class PaymentPromiseViewSet(CompanyScopedViewSet):
    """Promise-to-pay: create, list open, mark resolved. See payments.promise_to_pay."""

    queryset = PaymentPromise.objects.all()
    serializer_class = PaymentPromiseSerializer
    http_method_names = ["get", "post"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "resolve"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), IsOwnerManagerOrAccountant()]
        return [IsAuthenticated(), HasCompany()]

    def get_queryset(self):
        qs = super().get_queryset().select_related("customer", "invoice")
        if self.action == "list" and self.request.query_params.get("all") != "1":
            qs = qs.filter(resolved=False)
        invoice_id = self.request.query_params.get("invoice")
        if invoice_id:
            qs = qs.filter(invoice_id=invoice_id)
        customer_id = self.request.query_params.get("customer")
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        return qs

    def perform_create(self, serializer):
        customer = serializer.validated_data["customer"]
        invoice = serializer.validated_data.get("invoice")
        if invoice is not None and invoice.customer_id != customer.id:
            raise BusinessRuleError("The invoice does not belong to this customer.")
        promise = create_promise(
            company=self.company,
            customer=customer,
            invoice=invoice,
            promised_date=serializer.validated_data["promised_date"],
            note=serializer.validated_data.get("note", ""),
            promised_amount=serializer.validated_data.get("promised_amount"),
            user=self.request.user,
        )
        serializer.instance = promise

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        promise = self.get_object()
        promise = resolve_promise(promise, user=request.user)
        return Response(self.get_serializer(promise).data)
