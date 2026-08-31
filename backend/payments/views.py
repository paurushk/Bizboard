import hashlib

from decimal import Decimal

from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.idempotency import get_record, replay_record, store_record
from core.permissions import (
    CanCancelDocuments,
    CanCreatePayments,
    CanViewPaymentSurfaces,
    HasCompany,
    IsOwner,
    get_company_user,
)
from core.services.audit import AuditService
from core.viewsets import CompanyScopedViewSet

from .gateway import (
    decrypt_gateway_credentials,
    encrypt_gateway_credentials,
    get_adapter,
    parse_webhook_probe,
)
from .models import (
    BankAccount,
    BankLineMatchStatus,
    BankStatement,
    BankStatementLine,
    BankStatementStatus,
    CustomerReceipt,
    GatewayPayment,
    PaymentAllocation,
    PaymentLink,
    PaymentLinkStatus,
    PaymentSource,
    ReconMatch,
    SupplierPayment,
)
from .recon import is_exact_unique_suggestion, parse_bank_csv, suggest_matches
from .serializers import (
    BankAccountSerializer,
    BankStatementSerializer,
    CustomerReceiptSerializer,
    GatewayPaymentSerializer,
    PaymentAllocationSerializer,
    PaymentLinkSerializer,
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

    def perform_update(self, serializer):
        if serializer.validated_data.get("is_default"):
            BankAccount.objects.filter(company=self.company, is_default=True).exclude(
                pk=serializer.instance.pk
            ).update(is_default=False)
        serializer.save(updated_by=self.request.user)
        self._audit("UPDATE", serializer.instance)


class CustomerReceiptViewSet(CompanyScopedViewSet):
    queryset = CustomerReceipt.objects.select_related("customer", "bank_account").prefetch_related(
        "allocations"
    )
    serializer_class = CustomerReceiptSerializer
    http_method_names = ["get", "post"]

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), HasCompany(), CanCreatePayments()]
        if self.action == "void":
            return [IsAuthenticated(), HasCompany(), CanCancelDocuments()]
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("customer"):
            qs = qs.filter(customer_id=self.request.query_params["customer"])
        return qs

    def create(self, request, *args, **kwargs):
        """BB-000610 / BB-000654: durable idempotency + period gate."""
        raw_key = (request.headers.get("Idempotency-Key") or "").strip()
        if raw_key:
            prior = get_record(company=self.company, scope="receipt_create", raw_key=raw_key)
            if prior is not None:
                return replay_record(prior)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from reporting.gst_periods import assert_period_allows_money_amend, period_complete_warning

        receipt_date = serializer.validated_data.get("receipt_date")
        assert_period_allows_money_amend(self.company, receipt_date)
        warning = period_complete_warning(self.company, receipt_date)
        bank_account = serializer.validated_data.get("bank_account")
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
        )
        self._audit("CREATE", receipt)
        data = self.get_serializer(receipt).data
        if warning:
            data["warnings"] = [warning]
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
        receipt = PaymentService.void_receipt(
            receipt=self.get_object(),
            user=request.user,
            reason=(request.data.get("reason") or "").strip(),
        )
        self._audit("VOID", receipt)
        return Response(self.get_serializer(receipt).data)


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
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPaymentSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("supplier"):
            qs = qs.filter(supplier_id=self.request.query_params["supplier"])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from reporting.gst_periods import assert_period_allows_money_amend, period_complete_warning

        assert_period_allows_money_amend(self.company, serializer.validated_data.get("payment_date"))
        warning = period_complete_warning(self.company, serializer.validated_data.get("payment_date"))
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
        )
        self._audit("CREATE", payment)
        data = self.get_serializer(payment).data
        if warning:
            data["warnings"] = [warning]
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        payment = PaymentService.void_supplier_payment(
            payment=self.get_object(),
            user=request.user,
            reason=(request.data.get("reason") or "").strip(),
        )
        self._audit("VOID", payment)
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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        receipt = data.get("receipt")
        payment = data.get("supplier_payment")
        if receipt and receipt.company_id != self.company.id:
            raise BusinessRuleError("Invalid receipt reference.")
        if payment and payment.company_id != self.company.id:
            raise BusinessRuleError("Invalid payment reference.")

        from reporting.gst_periods import assert_period_allows_money_amend, period_complete_warning

        gate_date = None
        if receipt is not None:
            gate_date = receipt.receipt_date
        elif payment is not None:
            gate_date = payment.payment_date
        assert_period_allows_money_amend(self.company, gate_date)
        warning = period_complete_warning(self.company, gate_date)

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
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def unallocate(self, request, pk=None):
        allocation = PaymentService.reverse_allocation(allocation=self.get_object(), user=request.user)
        AuditService.log(
            company=self.company,
            user=request.user,
            action="UNALLOCATE",
            entity_type="PaymentAllocation",
            entity_id=allocation.id,
        )
        return Response(self.get_serializer(allocation).data)


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
        gp = self.get_object()
        amount = request.data.get("amount")
        reason = request.data.get("reason") or ""
        gp = PaymentService.refund_gateway_payment(
            gateway_payment=gp,
            amount=Decimal(str(amount)) if amount is not None else None,
            user=request.user,
            reason=reason,
        )
        self._audit("UPDATE", gp)
        return Response(GatewayPaymentSerializer(gp).data)

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
        rows = parse_bank_csv(content, preset=preset)
        if not rows:
            raise BusinessRuleError("No parsable rows found in the CSV.")

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
        return Response(self.get_serializer(statement).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="commit")
    def commit(self, request, pk=None):
        statement = self.get_object()
        if statement.status == BankStatementStatus.COMMITTED:
            return Response(self.get_serializer(statement).data)
        statement.status = BankStatementStatus.COMMITTED
        statement.save(update_fields=["status", "updated_at"])

        # Optional exact auto-match
        if getattr(self.company, "auto_match_bank_exact", False):
            for line in statement.lines.filter(match_status=BankLineMatchStatus.UNMATCHED):
                suggestions = suggest_matches(company=self.company, line=line)
                if is_exact_unique_suggestion(suggestions, line):
                    s = suggestions[0]
                    self._confirm_match(
                        line=line,
                        receipt_id=s["id"] if s["type"] == "receipt" else None,
                        payment_id=s["id"] if s["type"] == "supplier_payment" else None,
                        confidence=s["confidence"],
                        user=request.user,
                        notes="auto_exact",
                    )
        self._audit("UPDATE", statement)
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
        return match


class ReconViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, HasCompany, CanCreatePayments]

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
        out = []
        for line in lines:
            suggestions = suggest_matches(company=self.company, line=line)
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
        updated = 0
        out = []
        for line in lines:
            suggestions = suggest_matches(company=self.company, line=line)
            if suggestions:
                line.match_status = BankLineMatchStatus.SUGGESTED
                line.save(update_fields=["match_status"])
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
        from masters.models import Customer

        customer = Customer.objects.filter(company=self.company, pk=customer_id).first()
        if not customer:
            raise BusinessRuleError("Customer required.")
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
        # CompanyScopedViewSet.company is a cached_property from request
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
        if "test_mode" in request.data:
            test_mode = bool(request.data.get("test_mode"))
            if test_mode and sandbox_forbidden_env():
                raise BusinessRuleError(
                    "payment_gateway_test_mode cannot be enabled outside development/test/local."
                )
            company.payment_gateway_test_mode = test_mode
        if "require_payment_reference" in request.data:
            company.require_payment_reference = bool(request.data.get("require_payment_reference"))
        if "auto_match_bank_exact" in request.data:
            company.auto_match_bank_exact = bool(request.data.get("auto_match_bank_exact"))
        if request.data.get("clear_credentials"):
            company.payment_gateway_credentials_encrypted = ""
        creds = request.data.get("credentials")
        if isinstance(creds, dict):
            existing = decrypt_gateway_credentials(company.payment_gateway_credentials_encrypted or "")
            # BB-000367: ignore empty strings (do not wipe secrets); explicit clear_credentials only.
            existing.update({k: v for k, v in creds.items() if v is not None and str(v).strip() != ""})
            company.payment_gateway_credentials_encrypted = encrypt_gateway_credentials(existing)
        company.save()
        AuditService.log(
            company=company,
            user=request.user,
            action="UPDATE",
            entity_type="PaymentGatewaySettings",
            entity_id=company.id,
        )
        return self.get(request)
