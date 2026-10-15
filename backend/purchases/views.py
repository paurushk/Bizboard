import io

from django.db.models import DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.permissions import SubscriptionWritesAllowed
from core.exceptions import BusinessRuleError
from core.idempotency import wrap_idempotent
from core.permissions import (
    CanCancelDocuments,
    CanCreatePurchases,
    CanViewPurchaseSurfaces,
    HasCompany,
    IsOwner,
    get_company_user,
)
from core.services.billing import build_totals_preview
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.viewsets import CompanyScopedViewSet
from masters.models import Product, Supplier
from payments.models import PaymentAllocation

from .boe_services import BillOfEntryService
from .models import BillOfEntry, PurchaseInvoice, PurchaseItem, PurchaseOrder, PurchaseOrderItem, PurchaseReturn
from .serializers import (
    BillOfEntrySerializer,
    PurchaseInvoiceSerializer,
    PurchaseReturnableLineSerializer,
    PurchaseReturnPreviewSerializer,
    PurchaseReturnSerializer,
)
from .pay_now import PurchasePayNowSerializer, payment_error_payload, payment_summary, record_payment_at_entry
from .services import PurchaseService


class PurchaseInvoiceViewSet(CompanyScopedViewSet):
    queryset = PurchaseInvoice.objects.select_related("supplier", "bill_of_entry").prefetch_related("items__product")
    serializer_class = PurchaseInvoiceSerializer

    @action(detail=True, methods=["get"], url_path="source-bill")
    def source_bill(self, request, pk=None):
        """The bill this draft was created from, for anyone who may open the invoice."""
        from django.http import Http404

        from core.services.files import FileService

        invoice = self.get_object()
        if not invoice.attachment_id:
            raise Http404("This invoice has no source bill.")
        return FileService.inline_response(invoice.attachment)

    def get_throttles(self):
        throttles = super().get_throttles()
        if getattr(self, "action", None) == "complete":
            from core.throttles import CompanyRateThrottle

            throttles.append(CompanyRateThrottle(scope="purchase_complete"))
        return throttles

    def create(self, request, *args, **kwargs):
        """Durable Idempotency-Key with begin-of-request placeholder (same as sales)."""
        def _run():
            return super(PurchaseInvoiceViewSet, self).create(request, *args, **kwargs)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="purchase_invoice_create",
            build=_run,
        )

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "complete", "record_payment", "update", "partial_update", "destroy", "preview_totals"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreatePurchases()]
        if action in ("list", "retrieve", "returnable_lines"):
            return [IsAuthenticated(), HasCompany(), CanViewPurchaseSurfaces()]
        if action == "number_series":
            if self.request.method == "GET":
                return [IsAuthenticated(), HasCompany(), CanViewPurchaseSurfaces()]
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return super().get_permissions()

    @extend_schema(responses=PurchaseReturnableLineSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="returnable-lines")
    def returnable_lines(self, request, pk=None):
        """Per purchase line: bought / returned / credited by standalone notes / returnable."""
        return Response(PurchaseService.returnable_lines(self.get_object()))

    def get_queryset(self):
        qs = super().get_queryset()
        allocated = (
            PaymentAllocation.objects.filter(purchase_invoice_id=OuterRef("pk"), reversed_at__isnull=True)
            .values("purchase_invoice_id")
            .annotate(total=Sum("amount"))
            .values("total")[:1]
        )
        qs = qs.annotate(
            _allocated=Coalesce(
                Subquery(allocated, output_field=DecimalField(max_digits=14, decimal_places=2)),
                Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)),
            )
        )
        # R-038: validate before feeding query params to the ORM so bad input
        # is a 400, not a 500 (same pattern as sales invoices).
        from datetime import date as _date

        params = self.request.query_params
        status = params.get("status")
        if status:
            if status not in PurchaseInvoice.Status.values:
                raise BusinessRuleError(f"Unknown status {status!r}.")
            qs = qs.filter(status=status)
        if params.get("supplier"):
            try:
                qs = qs.filter(supplier_id=int(params["supplier"]))
            except (TypeError, ValueError):
                raise BusinessRuleError("supplier must be a numeric id.")
        for key, lookup in (("date_from", "invoice_date__gte"), ("date_to", "invoice_date__lte")):
            raw = params.get(key)
            if raw:
                try:
                    qs = qs.filter(**{lookup: _date.fromisoformat(str(raw)[:10])})
                except ValueError:
                    raise BusinessRuleError(f"{key} must be an ISO date (YYYY-MM-DD).")
        if params.get("q"):
            term = params["q"]
            qs = qs.filter(
                Q(number__icontains=term)
                | Q(supplier__name__icontains=term)
                | Q(supplier__phone__icontains=term)
            )
        return qs

    def get_serializer(self, *args, **kwargs):
        # CR-016 twin: attach CN/DN-aware outstanding for list rows in one bulk query.
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
                outstanding = LedgerService.bulk_purchase_invoice_outstanding(
                    self.company, invoice_ids=ids
                )
                for row in rows:
                    row._list_outstanding = outstanding.get(row.pk, Decimal("0"))
                args = (rows,) + args[1:]
                kwargs["many"] = True
        return super().get_serializer(*args, **kwargs)

    def perform_destroy(self, instance):
        if instance.status != PurchaseInvoice.Status.DRAFT:
            raise BusinessRuleError("Only draft purchases can be deleted; use Cancel instead.")
        from core.models import IdempotencyRecord

        IdempotencyRecord.objects.filter(
            company=self.company,
            resource_id=str(instance.pk),
        ).delete()
        super().perform_destroy(instance)

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        gstin = resolve_series_gstin(company)
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "PURCHASE_INVOICE", gstin=gstin))
        try:
            data = DocumentNumberService.configure(
                company,
                "PURCHASE_INVOICE",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
                gstin=gstin,
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    @action(detail=False, methods=["post"], url_path="preview-totals")
    def preview_totals(self, request):
        """A-03: authoritative purchase totals without persisting."""
        company = self.company
        supplier_id = request.data.get("supplier")
        if not supplier_id:
            raise BusinessRuleError("supplier is required")
        try:
            supplier = Supplier.objects.get(pk=supplier_id, company=company)
        except Supplier.DoesNotExist as exc:
            raise BusinessRuleError("Invalid supplier.") from exc
        purchase_type = request.data.get("purchase_type") or request.data.get("invoice_type") or PurchaseInvoice.PurchaseType.GST
        tax_enabled = str(purchase_type).upper() != PurchaseInvoice.PurchaseType.NON_GST
        from accounts.models import CompanyGstin

        seller_state = company.state or ""
        seller_gstin = company.gstin or ""
        gstin_id = request.data.get("company_gstin")
        if gstin_id:
            stamp = CompanyGstin.objects.filter(pk=gstin_id, company=company, is_active=True).first()
            if stamp is None:
                raise BusinessRuleError("Invalid company GSTIN.")
            seller_state = stamp.state or seller_state
            seller_gstin = stamp.gstin or seller_gstin
        product_ids = [raw.get("product") for raw in (request.data.get("items") or []) if raw.get("product")]
        products_by_id = {
            p.pk: p for p in Product.objects.filter(pk__in=product_ids, company=company).select_related("unit")
        }
        return Response(build_totals_preview(
            company=company,
            party_state=supplier.state or "",
            party_gstin=supplier.gstin or "",
            data=request.data,
            products_by_id=products_by_id,
            default_price_attr="purchase_price",
            tax_enabled=tax_enabled,
            seller_state=seller_state,
            seller_gstin=seller_gstin,
        ))

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        def _run():
            confirm_no_rcm = str(request.data.get("confirm_no_rcm") or "").lower() in (
                "true", "1", "yes",
            )
            confirm_duplicate_bill = str(
                request.data.get("confirm_duplicate_bill") or ""
            ).lower() in ("true", "1", "yes")
            confirm_blank_pos = str(request.data.get("confirm_blank_pos") or "").lower() in (
                "true", "1", "yes",
            )
            confirm_gstin_total = str(request.data.get("confirm_gstin_total_change") or "").lower() in (
                "true", "1", "yes",
            )
            confirm_three_way = str(request.data.get("confirm_three_way_override") or "").lower() in (
                "true", "1", "yes",
            )
            invoice, warnings = PurchaseService.complete(
                self.get_object(),
                request.user,
                confirm_no_rcm=confirm_no_rcm,
                confirm_duplicate_bill=confirm_duplicate_bill,
                confirm_blank_pos=confirm_blank_pos,
                confirm_gstin_total_change=confirm_gstin_total,
                confirm_three_way_override=confirm_three_way,
                gstin_cancel_override=str(request.data.get("gstin_cancel_override") or "").lower() in (
                    "true", "1", "yes",
                ),
                gstin_cancel_reason=str(request.data.get("gstin_cancel_reason") or ""),
                three_way_reason=str(request.data.get("three_way_reason") or ""),
            )
            data = self.get_serializer(invoice).data
            data["warnings"] = warnings
            # WP-1: optional pay-at-entry. Completion is already committed; a payment
            # problem is reported next to it (never raised) so the user gets a Retry
            # instead of a flash that vanishes on navigation.
            raw_pay = request.data.get("pay_now")
            if raw_pay:
                data["payment"], data["payment_error"] = self._pay_now(invoice, raw_pay)
                if data["payment"]:
                    invoice.refresh_from_db()
                    data.update(
                        {k: v for k, v in self.get_serializer(invoice).data.items() if k in ("paid", "balance")}
                    )
            return Response(data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="purchase_invoice_complete",
            build=_run,
        )

    def _audit_payment(self, payment):
        from core.services.audit import AuditService

        AuditService.log(
            company=self.company,
            user=self.request.user,
            action="CREATE",
            entity_type="SupplierPayment",
            entity_id=str(payment.pk),
            metadata={"source": "purchase_pay_now"},
        )

    def _pay_now(self, invoice, raw_pay):
        """Returns (payment_summary | None, error | None). Payment + allocation are one transaction."""
        serializer = PurchasePayNowSerializer(data=raw_pay, context=self.get_serializer_context())
        try:
            serializer.is_valid(raise_exception=True)
            payment, allocation = record_payment_at_entry(invoice, self.request.user, serializer.validated_data)
        except APIException as exc:
            return None, payment_error_payload(exc)
        self._audit_payment(payment)
        return payment_summary(payment, allocation), None

    @extend_schema(request=PurchasePayNowSerializer)
    @action(detail=True, methods=["post"], url_path="record-payment")
    def record_payment(self, request, pk=None):
        """Pay a completed bill from the bill itself: payment + allocation in one transaction."""

        def _run():
            serializer = PurchasePayNowSerializer(data=request.data, context=self.get_serializer_context())
            serializer.is_valid(raise_exception=True)
            invoice = self.get_object()
            payment, allocation = record_payment_at_entry(invoice, request.user, serializer.validated_data)
            self._audit_payment(payment)
            invoice.refresh_from_db()
            data = self.get_serializer(invoice).data
            data["payment"] = payment_summary(payment, allocation)
            return Response(data, status=201)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="purchase_invoice_record_payment",
            build=_run,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reverse_allocations = str(request.data.get("reverse_allocations") or "").lower() in ("true", "1", "yes")
        invoice = PurchaseService.cancel(
            self.get_object(), request.user, reverse_allocations=reverse_allocations
        )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """Render GST Purchase Bill PDF (Rule 46 / Rule 54 CGST Rules)."""
        from .pdf import render_gst_purchase_bill

        invoice = self.get_object()
        copy = (request.query_params.get("copy") or "ORIGINAL").upper()
        content = render_gst_purchase_bill(invoice, copy=copy)
        filename = f"{invoice.number or invoice.pk}_purchase_bill.pdf"
        return FileResponse(
            io.BytesIO(content),
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )


class PurchaseReturnViewSet(CompanyScopedViewSet):
    queryset = PurchaseReturn.objects.select_related("supplier", "purchase_invoice").prefetch_related(
        "items__product", "credit_notes"
    )
    serializer_class = PurchaseReturnSerializer

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "number_series":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "complete", "preview_totals"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreatePurchases()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPurchaseSurfaces()]
        return super().get_permissions()

    def get_throttles(self):
        # The live total fires on every (debounced) edit; give it its own budget.
        if getattr(self, "action", None) == "preview_totals":
            self.throttle_scope = "return_preview"
        return super().get_throttles()

    @extend_schema(request=PurchaseReturnSerializer, responses=PurchaseReturnPreviewSerializer)
    @action(detail=False, methods=["post"], url_path="preview-totals")
    def preview_totals(self, request):
        """Exact purchase credit-note totals for a return that has not been saved."""
        from django.utils import timezone

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if len(data["items"]) > 200:
            raise BusinessRuleError("Preview is limited to 200 lines.")
        if data.get("purchase_invoice") is None:
            raise BusinessRuleError("Pick the purchase to preview a return against.")
        result = PurchaseService.preview_return_totals(
            company=self.company,
            supplier=data["supplier"],
            invoice=data["purchase_invoice"],
            return_date=data.get("return_date") or timezone.localdate(),
            items_data=data["items"],
            user=request.user,
        )
        return Response(result)

    @action(detail=False, methods=["get", "patch"], url_path="number-series")
    def number_series(self, request):
        company = self.company
        if request.method == "GET":
            return Response(DocumentNumberService.peek(company, "PURCHASE_RETURN"))
        try:
            data = DocumentNumberService.configure(
                company,
                "PURCHASE_RETURN",
                prefix=request.data.get("prefix"),
                next_number=request.data.get("next_number"),
                padding=request.data.get("padding"),
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        return Response(data)

    def get_queryset(self):
        # CR-046: validate query params against status enum and int supplier
        qs = super().get_queryset()
        params = self.request.query_params
        status = params.get("status")
        if status:
            if status not in PurchaseReturn.Status.values:
                raise BusinessRuleError(f"Unknown status {status!r}.")
            qs = qs.filter(status=status)
        if params.get("supplier"):
            try:
                qs = qs.filter(supplier_id=int(params["supplier"]))
            except (TypeError, ValueError):
                raise BusinessRuleError("supplier must be a numeric id.")
        for key, lookup in (("date_from", "return_date__gte"), ("date_to", "return_date__lte")):
            if params.get(key):
                qs = qs.filter(**{lookup: params[key]})
        text = (params.get("q") or "").strip()
        if text:
            qs = qs.filter(
                Q(number__icontains=text)
                | Q(purchase_invoice__number__icontains=text)
                | Q(supplier__name__icontains=text)
                | Q(reason__icontains=text)
                | Q(credit_notes__number__icontains=text)
            ).distinct()
        bill_id = (
            params.get("purchase_invoice")
            or params.get("purchase_bill")
            or params.get("purchaseBill")
        )
        if bill_id:
            try:
                qs = qs.filter(purchase_invoice_id=int(bill_id))
            except (TypeError, ValueError):
                raise BusinessRuleError("purchase_invoice must be a numeric id.")
        return qs

    def create(self, request, *args, **kwargs):
        def _run():
            return super(PurchaseReturnViewSet, self).create(request, *args, **kwargs)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="purchase_return_create",
            build=_run,
        )

    def perform_destroy(self, instance):
        if instance.status != PurchaseReturn.Status.DRAFT:
            raise BusinessRuleError("Only draft returns can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        def _run():
            purchase_return = PurchaseService.complete_return(self.get_object(), request.user)
            return Response(self.get_serializer(purchase_return).data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="purchase_return_complete",
            build=_run,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        purchase_return = PurchaseService.cancel_return(self.get_object(), request.user)
        return Response(self.get_serializer(purchase_return).data)


class BillOfEntryViewSet(CompanyScopedViewSet):
    """GST-08: customs Bill of Entry for imports of goods (ITC → GSTR-3B 4(A)(5))."""

    queryset = BillOfEntry.objects.select_related("supplier")
    serializer_class = BillOfEntrySerializer

    def initial(self, request, *args, **kwargs):
        # Scope revision 2026-09-09b: D10 Bill of Entry / import purchase + landed
        # cost is a KNOWN LIMITATION for the pilot — the surface is inaccessible
        # when ENABLE_BOE is off (backend/.env.pilot.example sets it to 0).
        from django.conf import settings
        from django.http import Http404

        if not getattr(settings, "ENABLE_BOE", False):
            raise Http404()
        super().initial(request, *args, **kwargs)

    def get_permissions(self):
        action = getattr(self, "action", None)
        if action == "cancel":
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCancelDocuments()]
        if action in ("create", "update", "partial_update", "destroy", "complete"):
            return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreatePurchases()]
        if action in ("list", "retrieve"):
            return [IsAuthenticated(), HasCompany(), CanViewPurchaseSurfaces()]
        return super().get_permissions()

    def get_queryset(self):
        # CR-046: validate query params against status enum and int supplier
        qs = super().get_queryset()
        params = self.request.query_params
        status = params.get("status")
        if status:
            if status not in BillOfEntry.Status.values:
                raise BusinessRuleError(f"Unknown status {status!r}.")
            qs = qs.filter(status=status)
        if params.get("supplier"):
            try:
                qs = qs.filter(supplier_id=int(params["supplier"]))
            except (TypeError, ValueError):
                raise BusinessRuleError("supplier must be a numeric id.")
        if params.get("period"):
            qs = qs.filter(boe_date__startswith=params["period"])
        return qs

    def create(self, request, *args, **kwargs):
        def _run():
            return super(BillOfEntryViewSet, self).create(request, *args, **kwargs)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="bill_of_entry_create",
            build=_run,
        )

    def perform_destroy(self, instance):
        if instance.status != BillOfEntry.Status.DRAFT:
            raise BusinessRuleError("Only a draft Bill of Entry can be deleted; use Cancel instead.")
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        def _run():
            boe = BillOfEntryService.complete(self.get_object(), request.user)
            return Response(self.get_serializer(boe).data)

        return wrap_idempotent(
            request=request,
            company=self.company,
            scope="bill_of_entry_complete",
            build=_run,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        boe = BillOfEntryService.cancel(self.get_object(), request.user)
        return Response(self.get_serializer(boe).data)


class SupplierPriceHistoryView(APIView):
    """Dated unit prices for one supplier and product. No score or rank (COMP-007)."""

    permission_classes = [IsAuthenticated, HasCompany, CanViewPurchaseSurfaces]

    # F1-010: unbounded before this — a long-lived supplier+product pair with
    # years of weekly reorders could return an unbounded payload. Capped to
    # the most recent N rows (chronological order is still oldest-first for
    # rendering; only the population is capped, from the recent end).
    MAX_ROWS = 200

    def get(self, request, supplier_id):
        from datetime import date as _date

        from core.services.feature_flags import flag_enabled
        from rest_framework import status as http_status

        company = get_company_user(request).company
        if not flag_enabled(company, "ENABLE_SUPPLIER_PRICE_HISTORY"):
            return Response({"detail": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
        product_id = request.query_params.get("product")
        if not product_id:
            return Response({"detail": "product is required."}, status=http_status.HTTP_400_BAD_REQUEST)
        supplier = Supplier.objects.filter(company=company, pk=supplier_id).first()
        if supplier is None:
            return Response({"detail": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)
        product = Product.objects.filter(company=company, pk=product_id).first()
        if product is None:
            return Response({"detail": "Not found."}, status=http_status.HTTP_404_NOT_FOUND)

        date_from = date_to = None
        try:
            raw_from = request.query_params.get("date_from")
            if raw_from:
                date_from = _date.fromisoformat(str(raw_from)[:10])
            raw_to = request.query_params.get("date_to")
            if raw_to:
                date_to = _date.fromisoformat(str(raw_to)[:10])
        except ValueError:
            return Response(
                {"detail": "date_from/date_to must be an ISO date (YYYY-MM-DD)."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        invoice_items = (
            PurchaseItem.objects.filter(
                company=company,
                product=product,
                invoice__supplier=supplier,
                invoice__status__in=(
                    PurchaseInvoice.Status.COMPLETED,
                    PurchaseInvoice.Status.RETURNED,
                ),
            )
            .select_related("invoice")
            .order_by("invoice__invoice_date", "id")
        )
        if date_from:
            invoice_items = invoice_items.filter(invoice__invoice_date__gte=date_from)
        if date_to:
            invoice_items = invoice_items.filter(invoice__invoice_date__lte=date_to)

        rows = []
        for item in invoice_items:
            rows.append({
                "source": "PURCHASE_INVOICE",
                "document_id": item.invoice_id,
                "document_number": item.invoice.number,
                "document_date": item.invoice.invoice_date,
                "quantity": item.quantity,
                "unit_price": f"{item.unit_price:.2f}" if item.unit_price is not None else "0.00",
            })
        order_items = (
            PurchaseOrderItem.objects.filter(
                company=company,
                product=product,
                purchase_order__supplier=supplier,
                purchase_order__status=PurchaseOrder.Status.CONVERTED,
            )
            .select_related("purchase_order")
            .order_by("purchase_order__order_date", "id")
        )
        if date_from:
            order_items = order_items.filter(purchase_order__order_date__gte=date_from)
        if date_to:
            order_items = order_items.filter(purchase_order__order_date__lte=date_to)
        for item in order_items:
            rows.append({
                "source": "PURCHASE_ORDER",
                "document_id": item.purchase_order_id,
                "document_number": item.purchase_order.number,
                "document_date": item.purchase_order.order_date,
                "quantity": item.quantity,
                "unit_price": f"{item.unit_price:.2f}" if item.unit_price is not None else "0.00",
            })
        rows.sort(key=lambda row: (row["document_date"], row["source"], row["document_id"]))
        total_count = len(rows)
        truncated = total_count > self.MAX_ROWS
        if truncated:
            rows = rows[-self.MAX_ROWS:]
        from core.services.flag_observability import log_flag_event
        from purchases.reliability import supply_metrics

        log_flag_event(company, "ENABLE_SUPPLIER_PRICE_HISTORY", "price_history_read")
        metrics = supply_metrics(company, supplier, product)
        return Response({
            "supplier_id": supplier.id,
            "product_id": product.id,
            "rows": rows,
            "total_count": total_count,
            "truncated": truncated,
            "lead_time_days": metrics["lead_time_days"],
            "fill_rate": metrics["fill_rate"],
            "over_receipt": metrics["over_receipt"],
        })
