"""POS settings and counter audit events. Posting rules live in pos_policy."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.audit import AuditService
from masters.models import Customer
from django.utils import timezone

from sales.pos_policy import (
    expired_lot_policy,
    offline_credit_enabled,
    max_line_discount,
    pin_configured,
    save_pos_settings,
    tender_accounts,
    today_period_blocked,
)


def _company(request):
    return get_company_user(request).company


def _flags_value(company, key):
    return (company.feature_flags or {}).get(key)


class PosSettingsView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated(), HasCompany()]
        return [IsAuthenticated(), HasCompany(), IsOwner()]

    def get(self, request):
        company = _company(request)
        walk_in = Customer.objects.filter(company=company, is_pos_walk_in=True).first()
        blocked = today_period_blocked(company, timezone.localdate())
        return Response({
            "tender_accounts": tender_accounts(company),
            "max_line_discount": str(max_line_discount(company)),
            "max_price_discount_percent": str((_flags_value(company, "pos_max_price_discount_percent") or "")),
            "expired_lot_policy": expired_lot_policy(company),
            "pin_configured": pin_configured(company),
            "walk_in_customer_id": walk_in.id if walk_in else None,
            "period_blocked": bool(blocked),
            "period_message": blocked,
            "require_open_shift": bool(_flags_value(company, "pos_require_open_shift")),
            "offline_credit": offline_credit_enabled(company),
            "return_window_days": _flags_value(company, "pos_return_window_days") or 0,
            "catalog_warn_hours": _flags_value(company, "pos_catalog_warn_hours") or 24,
            "catalog_block_hours": _flags_value(company, "pos_catalog_block_hours") or 72,
        })

    def post(self, request):
        company = _company(request)
        save_pos_settings(company, request.data or {})
        return self.get(request)


class PosCounterEventView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def post(self, request):
        company = _company(request)
        kind = str(request.data.get("kind") or "").strip().lower()
        if kind in {"discount", "upi_received", "price_change"}:
            raise BusinessRuleError(
                "The server records this. Do not send it from the till.",
                code="pos_event_retired",
            )
        if kind != "drawer_open":
            raise BusinessRuleError("Unknown counter event.")
        company = _company(request)
        detail = str(request.data.get("detail") or kind)[:200]
        if any(ord(ch) < 32 and ch not in "\n\t" for ch in detail):
            raise BusinessRuleError("Counter event detail has unsupported characters.")
        flags = company.feature_flags or {}
        shift_id = request.data.get("shift_id")
        if flags.get("pos_require_open_shift") and not shift_id:
            raise BusinessRuleError(
                "A drawer open needs the open shift.",
                code="pos_shift_required",
            )
        if shift_id not in (None, ""):
            from accounting.models import CashShiftRegister

            if not str(shift_id).isdigit() or not CashShiftRegister.objects.filter(
                company=company, pk=int(shift_id),
            ).exists():
                raise BusinessRuleError("That till is not in this company.")
        invoice_id = str(request.data.get("invoice_id") or "")
        if invoice_id:
            from sales.models import SalesInvoice

            if not invoice_id.isdigit() or not SalesInvoice.objects.filter(company=company, pk=int(invoice_id)).exists():
                raise BusinessRuleError("That bill is not in this company.")
        AuditService.log(
            company=company,
            user=request.user,
            action="UPDATE",
            entity_type="PosCounter",
            entity_id=invoice_id,
            description=detail,
            metadata={
                "kind": kind,
                "shift_id": request.data.get("shift_id"),
                "terminal_label": str(request.data.get("terminal_label") or "")[:64],
            },
        )
        return Response({"ok": True})


def _cashier_permissions():
    from billing.permissions import SubscriptionWritesAllowed
    from core.permissions import CanCreatePayments, CanCreateSales

    return [
        IsAuthenticated(),
        HasCompany(),
        SubscriptionWritesAllowed(),
        CanCreateSales(),
        CanCreatePayments(),
    ]


class PosCollectView(APIView):
    """Take money against an invoice the counter already completed.

    Uses the same bank mapping as checkout. Cash stays on ledger 1100.
    """

    def get_permissions(self):
        return _cashier_permissions()

    def post(self, request):
        from core.idempotency import wrap_idempotent

        # A retried tap must not take the money twice.
        return wrap_idempotent(
            request=request,
            company=_company(request),
            scope="pos_collect",
            build=lambda: self._collect(request),
        )

    def _collect(self, request):
        from decimal import Decimal, InvalidOperation

        from django.db import transaction

        from payments.models import PaymentMode
        from payments.serializers import CustomerReceiptSerializer
        from payments.services import PaymentService, cheque_fields_from_payload
        from sales.models import SalesInvoice
        from sales.pos_policy import resolve_bank
        from sales.pos_shift import assert_cash_shift, stamp_receipt

        company = _company(request)
        terminal_id = str(request.data.get("terminal_id") or "")[:64]
        invoice = SalesInvoice.objects.filter(
            company=company, pk=request.data.get("invoice"),
        ).first()
        if invoice is None or invoice.status != SalesInvoice.Status.COMPLETED:
            raise BusinessRuleError("Collect against a completed bill from this company.")
        mode_str = str(request.data.get("mode") or "CASH").upper()
        try:
            mode = PaymentMode(mode_str)
        except ValueError as exc:
            raise BusinessRuleError(f"Unknown payment mode '{mode_str}'.") from exc
        if mode == PaymentMode.CREDIT:
            raise BusinessRuleError("Credit is not a collection. The bill stays unpaid.")
        raw_amount = request.data.get("amount")
        try:
            requested = Decimal(str(raw_amount)) if raw_amount not in (None, "") else None
        except InvalidOperation as exc:
            raise BusinessRuleError("Collection amount must be a number.") from exc
        bank = resolve_bank(company, mode_str) if mode_str in ("UPI", "CARD", "BANK", "CHEQUE") else None
        shift = assert_cash_shift(company, request.user, terminal_id, [mode_str])
        with transaction.atomic():
            invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk, company=company)
            from ledgers.services import LedgerService

            outstanding = Decimal(str(LedgerService.sales_invoice_outstanding(invoice) or 0))
            amount = outstanding if requested is None else requested
            if amount <= 0 or outstanding <= 0:
                raise BusinessRuleError("Nothing left to collect on this bill.")
            amount = min(amount, outstanding)
            # Date the money today so this cashier's open till includes it.
            receipt = PaymentService.create_receipt(
                company=company,
                customer=invoice.customer,
                amount=amount,
                mode=mode,
                receipt_date=timezone.localdate(),
                reference=str(request.data.get("reference") or ""),
                notes=str(request.data.get("notes") or f"POS collect {invoice.number}"),
                user=request.user,
                bank_account=bank,
                utr=str(request.data.get("utr") or request.data.get("reference") or ""),
                **cheque_fields_from_payload(request.data, company=company),
            )
            PaymentService.allocate_receipt(
                receipt=receipt,
                sales_invoice=invoice,
                amount=amount,
                user=request.user,
            )
            stamp_receipt(receipt, shift)
            if mode == PaymentMode.UPI:
                AuditService.log(
                    company=company,
                    user=request.user,
                    action="UPDATE",
                    entity_type="SalesInvoice",
                    entity_id=str(invoice.pk),
                    description=f"UPI payment received {amount} on {invoice.number}",
                    metadata={"amount": str(amount), "mode": "UPI"},
                )
        return Response({
            "invoice_id": invoice.id,
            "receipt": CustomerReceiptSerializer(receipt).data,
        }, status=201)


class PosReturnView(APIView):
    """Return the last counter bill. Cashiers complete it here.

    The general return complete action stays limited to people who can cancel
    documents. Exchange starts the replacement sale on the same customer.
    """

    def get_permissions(self):
        return _cashier_permissions()

    def post(self, request):
        from django.db import transaction

        from core.permissions import CanCancelDocuments
        from sales.models import SalesInvoice, SalesReturn
        from sales.pos_policy import pin_ok
        from sales.services import SalesService

        company = _company(request)
        # Completing a return is limited to people who can cancel documents.
        # A cashier without that right needs the owner PIN for this return.
        approver = (
            pin_ok(company, str(request.data.get("owner_pin") or ""), request.user)
            if request.data.get("owner_pin") else False
        )
        if not CanCancelDocuments().has_permission(request, self) and not approver:
            raise BusinessRuleError(
                "An owner PIN is required to return a bill at the counter.",
                code="pos_return_pin",
            )
        invoice = (
            SalesInvoice.objects.filter(company=company, pk=request.data.get("invoice"))
            .prefetch_related("items")
            .first()
        )
        replay_key = str(request.headers.get("Idempotency-Key") or request.data.get("idempotency_key") or "").strip()
        if replay_key:
            from sales.models import PosCounterRefund
            from sales.pos_refunds import refund_key_prefix, retry_pending_gateway_refunds

            replay_qs = PosCounterRefund.objects.filter(
                company=company,
                idempotency_key__startswith=refund_key_prefix(replay_key),
            ).select_related("sales_return")
            if invoice is not None:
                # The same key sent for a different bill is a new request, not a replay.
                replay_qs = replay_qs.filter(sales_return__sales_invoice=invoice)
            existing = list(replay_qs)
            if existing:
                retry_pending_gateway_refunds(existing, request.user)
                existing = list(replay_qs)
                first = existing[0].sales_return
                return Response({
                    "id": first.id,
                    "number": first.number,
                    "exchange": str(request.data.get("exchange") or "").lower() in ("1", "true", "yes"),
                    "customer_id": first.customer_id,
                    "refunds": [
                        {"id": row.id, "mode": row.mode, "amount": str(row.amount), "status": row.status}
                        for row in existing
                    ],
                    "replayed": True,
                })
        if invoice is None or invoice.status not in (
            SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED,
        ):
            raise BusinessRuleError("Return a completed bill from this company.")
        from decimal import Decimal

        from django.db.models import Sum

        from sales.models import SalesReturnItem

        returned_on_line = {
            row["source_item"]: Decimal(str(row["total"] or 0))
            for row in SalesReturnItem.objects.filter(
                sales_return__sales_invoice=invoice,
                sales_return__status="COMPLETED",
                source_item__isnull=False,
            ).values("source_item").annotate(total=Sum("quantity"))
        }
        loose_by_product = {
            row["product"]: Decimal(str(row["total"] or 0))
            for row in SalesReturnItem.objects.filter(
                sales_return__sales_invoice=invoice,
                sales_return__status="COMPLETED",
                source_item__isnull=True,
            ).values("product").annotate(total=Sum("quantity"))
        }
        items = []
        for item in invoice.items.all():
            left = Decimal(str(item.quantity)) - returned_on_line.get(item.id, Decimal("0"))
            loose = loose_by_product.get(item.product_id, Decimal("0"))
            used = min(left, loose)
            left -= used
            loose_by_product[item.product_id] = loose - used
            if left <= 0:
                continue
            items.append({
                "product": item.product,
                "description": item.description,
                "quantity": left,
                "unit_price": item.unit_price,
                "discount_percent": item.discount_percent,
                "gst_rate": item.gst_rate,
                "serial_numbers": list(item.serial_numbers or [])[:int(left)],
                "source_item": item,
            })
        if not items:
            raise BusinessRuleError("Nothing left to return on this bill.")
        wanted = request.data.get("lines")
        if isinstance(wanted, list) and wanted:
            by_source = {}
            for row in wanted:
                try:
                    by_source[int(row.get("source_item"))] = Decimal(str(row.get("quantity")))
                except (TypeError, ValueError, AttributeError) as exc:
                    raise BusinessRuleError("Each return line needs a source item and a quantity.") from exc
            picked = []
            for row in items:
                source_id = getattr(row.get("source_item"), "id", None)
                if source_id not in by_source:
                    continue
                qty = min(Decimal(str(row["quantity"])), by_source[source_id])
                if qty <= 0:
                    continue
                row = dict(row)
                row["quantity"] = qty
                row["serial_numbers"] = list(row.get("serial_numbers") or [])[:int(qty)]
                picked.append(row)
            items = picked
            if not items:
                raise BusinessRuleError("Nothing left to return on the chosen lines.")
        window = _flags_value(company, "pos_return_window_days")
        if window:
            from datetime import timedelta

            if invoice.invoice_date and invoice.invoice_date < timezone.localdate() - timedelta(days=int(window)):
                if not approver:
                    raise BusinessRuleError(
                        "This bill is outside the return window. An approver PIN is required.",
                        code="pos_return_window",
                    )
        exchange = str(request.data.get("exchange") or "").lower() in ("1", "true", "yes")
        if getattr(approver, "pk", None):
            AuditService.log(
                company=company,
                user=request.user,
                action="UPDATE",
                entity_type="SalesInvoice",
                entity_id=str(invoice.pk),
                description="Counter return approved",
                metadata={
                    "scope": "return",
                    "approver_id": approver.pk,
                    "approver_name": approver.get_full_name() or approver.username,
                },
            )
        from sales.pos_refunds import (
            default_refund_mode,
            finish_gateway_refunds,
            parse_refund_parts,
            stage_refunds,
        )
        from sales.pos_shift import assert_cash_shift, resolve_open_shift

        with transaction.atomic():
            sales_return = SalesReturn.objects.create(
                company=company,
                customer=invoice.customer,
                sales_invoice=invoice,
                reason=str(request.data.get("reason") or ("Counter exchange" if exchange else "Counter return"))[:200],
                created_by=request.user,
                updated_by=request.user,
            )
            SalesService.set_return_items(sales_return, items, request.user)
            completed = SalesService.complete_return(sales_return, request.user)
            parts = parse_refund_parts(request.data)
            refund_rows = []
            gateway_calls = []
            if parts and len(parts) == 1 and str((parts[0] or {}).get("mode") or "").upper() == "SPLIT":
                from sales.pos_refunds import proportional_refund_parts

                parts = proportional_refund_parts(completed)
            if parts:
                terminal_id = str(request.data.get("terminal_id") or "")[:64]
                shift = resolve_open_shift(company, request.user, terminal_id)
                # Cash leaving the drawer needs an open till when the company requires one.
                assert_cash_shift(
                    company, request.user, terminal_id,
                    [
                        str((part or {}).get("mode") or default_refund_mode(completed)).upper()
                        for part in parts
                    ],
                )
                refund_rows, gateway_calls = stage_refunds(
                    completed,
                    parts,
                    user=request.user,
                    shift=shift,
                    idempotency_key=str(request.headers.get("Idempotency-Key") or request.data.get("idempotency_key") or ""),
                )
        if gateway_calls:
            finish_gateway_refunds(gateway_calls, request.user)
        return Response({
            "id": completed.id,
            "number": completed.number,
            "exchange": exchange,
            "customer_id": invoice.customer_id,
            "refunds": [
                {"id": row.id, "mode": row.mode, "amount": str(row.amount), "status": row.status}
                for row in refund_rows
            ],
        }, status=201)
