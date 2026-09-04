"""Payment Service — receipts, supplier payments, allocations, links, gateway finalize."""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.events import emit
from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin

logger = logging.getLogger(__name__)


def refund_idempotency_key(gateway_payment_id, amount, seq=None) -> str:
    """Stable provider key for sync + outbox so a timeout cannot double-refund.

    ``seq`` is a per-gateway-payment logical-refund counter (B4-002). Without it,
    two legitimate equal-amount partial refunds collide on one key, the provider
    replays the first and refunds nothing while the books unwind twice. A retry
    of the *same* logical refund passes the *same* ``seq`` and so keeps its key
    stable. ``seq=None`` reproduces the pre-B4-002 key for backwards compatibility
    with outbox rows written before this change.
    """
    amt = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
    if seq is None:
        return f"bb-refund-{gateway_payment_id}-{amt}"
    return f"bb-refund-{gateway_payment_id}-{int(seq)}-{amt}"


# PAY-11: `GatewayPayment.raw_payload` is retained indefinitely — never persist
# cardholder / contact PII in it. Strip these keys anywhere in the payload; the
# reconciliation-relevant fields (ids, amount, status, fee, method, timestamps)
# are kept.
_GATEWAY_PAYLOAD_PII_KEYS = frozenset({
    "card", "card_id", "cardnum", "card_number", "cardhash", "name_on_card",
    "email", "customer_email", "contact", "customer_phone", "phone",
    "customer_name", "name", "vpa", "upi_id", "wallet_phone",
    "auth_code", "token", "customer_token", "cvv", "billing_address",
    "ip", "user_agent", "notes",
})


def redact_gateway_payload(value):
    """Recursively drop known PII keys from a provider webhook payload."""
    if isinstance(value, dict):
        return {
            k: redact_gateway_payload(v)
            for k, v in value.items()
            if str(k).lower() not in _GATEWAY_PAYLOAD_PII_KEYS
        }
    if isinstance(value, list):
        return [redact_gateway_payload(v) for v in value]
    return value

# Gateway-holding reasons that can never post to books — the capture must be
# refunded to the customer, not retried (see reconcile_gateway_captures).
# BOOKS_ERROR / PERIOD_LOCKED / UTR_CLASH can succeed later and stay retryable.
_TERMINAL_HOLDING_REASONS = (
    "INVOICE_CANCELLED",
    "LINK_CANCELLED",
    "AMOUNT_MISMATCH",
    "ALREADY_PAID",
    "LINK_EXPIRED",
    "NO_LINK",
)

from .gateway import decrypt_gateway_credentials, get_adapter
from .models import (
    BankAccount,
    BankLineMatchStatus,
    BankStatementLine,
    BankStatementStatus,
    CustomerReceipt,
    GatewayPayment,
    GatewayPaymentStatus,
    PaymentAllocation,
    PaymentLink,
    PaymentLinkStatus,
    PaymentSource,
    ReceiptStatus,
    SupplierPayment,
    SupplierPaymentStatus,
)
from .upi import normalize_utr


def sync_company_bank_account(company):
    """Keep payments.BankAccount in sync with company bill-print bank details (E2E3-033)."""
    from .models import BankAccountType

    name = (company.bank_name or "").strip()
    number = (company.bank_account or "").strip()
    ifsc = (company.bank_ifsc or "").strip()
    if not name and not number:
        return None
    display = name or "Company bank"
    masked = (("X" * max(0, len(number) - 4)) + number[-4:]) if number else ""
    existing = BankAccount.objects.filter(company=company).order_by("-is_default", "id").first()
    if existing:
        fields = []
        if existing.name != display:
            existing.name = display
            fields.append("name")
        if number and existing.account_number_masked != masked:
            existing.account_number_masked = masked
            fields.append("account_number_masked")
        if ifsc and existing.ifsc != ifsc:
            existing.ifsc = ifsc
            fields.append("ifsc")
        if fields:
            existing.save(update_fields=fields)
        return existing
    return BankAccount.objects.create(
        company=company,
        name=display,
        account_number_masked=masked,
        ifsc=ifsc,
        account_type=BankAccountType.CURRENT,
        is_default=True,
    )


def _allocated_of_payment(payment_field, payment) -> Decimal:
    return (
        PaymentAllocation.objects.filter(**{payment_field: payment}, reversed_at__isnull=True)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )


def _reverse_allocation_journals(allocation, user=None):
    from accounting.models import JournalEntry
    from accounting.services import PostingService

    company = allocation.company
    if not getattr(company, "accounting_enabled", False):
        return
    # BB-000701: reverse on original JE / money-doc date (not localdate).
    money_date = None
    if allocation.receipt_id:
        money_date = allocation.receipt.receipt_date
    elif allocation.supplier_payment_id:
        money_date = allocation.supplier_payment.payment_date
    for purpose in ("ALLOCATE_RECEIPT", "ALLOCATE_PAYMENT"):
        entry = (
            JournalEntry.objects.filter(
                company=company,
                source_type="PAYMENT_ALLOCATION",
                source_id=allocation.id,
                purpose=purpose,
                status=JournalEntry.Status.POSTED,
            )
            .select_for_update()
            .first()
        )
        if entry:
            PostingService.reverse(
                entry, user=user, entry_date=entry.entry_date or money_date
            )


def _reverse_money_document_journal(*, company, source_type, source_id, user=None, entry_date=None):
    from accounting.models import JournalEntry
    from accounting.services import PostingService

    if not getattr(company, "accounting_enabled", False):
        return
    entry = (
        JournalEntry.objects.filter(
            company=company,
            source_type=source_type,
            source_id=source_id,
            purpose="CREATE",
            status=JournalEntry.Status.POSTED,
        )
        .select_for_update()
        .first()
    )
    if entry:
        PostingService.reverse(entry, user=user, entry_date=entry_date)


def _check_utr_duplicate(*, company, utr: str, exclude_receipt_id=None, exclude_payment_id=None) -> str | None:
    """BB-000645: all-time unique (company, normalized UTR) across receipts and payments."""
    utr = normalize_utr(utr)
    if not utr:
        return None
    qs = CustomerReceipt.objects.filter(company=company, utr=utr).exclude(
        status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED)
    )
    if exclude_receipt_id:
        qs = qs.exclude(pk=exclude_receipt_id)
    if qs.exists():
        return f"UTR {utr} was already used on another receipt."
    qs2 = SupplierPayment.objects.filter(company=company, utr=utr).exclude(
        status=SupplierPaymentStatus.VOIDED
    )
    if exclude_payment_id:
        qs2 = qs2.exclude(pk=exclude_payment_id)
    if qs2.exists():
        return f"UTR {utr} was already used on a supplier payment."
    return None


def _assert_utr_unique(*, company, utr: str, exclude_receipt_id=None, exclude_payment_id=None) -> None:
    warn = _check_utr_duplicate(
        company=company,
        utr=utr,
        exclude_receipt_id=exclude_receipt_id,
        exclude_payment_id=exclude_payment_id,
    )
    if warn:
        raise BusinessRuleError(warn)


class PaymentService:
    @staticmethod
    @transaction.atomic
    def create_receipt(
        *,
        company,
        customer,
        amount,
        mode,
        receipt_date=None,
        reference="",
        notes="",
        user=None,
        bank_account=None,
        utr="",
        source=PaymentSource.MANUAL,
        gateway_payment=None,
        warn_utr_duplicate=False,
        bypass_period_gate=False,
    ):
        if Decimal(amount) <= 0:
            raise BusinessRuleError("Receipt amount must be greater than zero.")
        if customer.company_id != company.id:
            raise BusinessRuleError("Invalid customer reference.")
        from reporting.gst_periods import assert_period_allows_money_amend

        gate_date = receipt_date or timezone.localdate()
        # BB-000700: gate in service (bank import / gateway settle bypass HTTP views).
        # R3-001: a verified gateway settlement is money that has already moved —
        # it must never be blocked by a closed period (would 500 the webhook and
        # lose the record while the provider retries forever).
        if not bypass_period_gate:
            assert_period_allows_money_amend(company, gate_date)
        utr_n = normalize_utr((utr or reference) if mode in ("UPI", "BANK") else utr)
        if getattr(company, "require_payment_reference", False) and mode in ("UPI", "BANK") and not utr_n:
            raise BusinessRuleError("UTR / payment reference is required for UPI and Bank receipts.")
        if bank_account and bank_account.company_id != company.id:
            raise BusinessRuleError("Invalid bank account.")
        if warn_utr_duplicate:
            warn = _check_utr_duplicate(company=company, utr=utr_n)
        else:
            _assert_utr_unique(company=company, utr=utr_n)
            warn = None

        gstin_key = resolve_series_gstin(company)
        receipt = CustomerReceipt(
            company=company,
            customer=customer,
            amount=amount,
            mode=mode,
            reference=reference,
            utr=utr_n,
            notes=notes,
            bank_account=bank_account,
            source=source,
            gateway_payment=gateway_payment,
            created_by=user,
            updated_by=user,
            number=DocumentNumberService.next_number(
                company,
                "CUSTOMER_RECEIPT",
                gstin=gstin_key,
                on_date=(receipt_date or timezone.localdate()) if gstin_key else None,
            ),
        )
        if receipt_date:
            receipt.receipt_date = receipt_date
        receipt.save()
        if company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_receipt(receipt, user)
        emit("document.completed", document=receipt, user=user, event="customer_receipt.created")
        receipt._utr_warning = warn  # transient for API
        return receipt

    @staticmethod
    @transaction.atomic
    def create_supplier_payment(
        *,
        company,
        supplier,
        amount,
        mode,
        payment_date=None,
        reference="",
        notes="",
        user=None,
        bank_account=None,
        utr="",
        source=PaymentSource.MANUAL,
        tds_section="",
        tds_rate=None,
        tds_amount=None,
    ):
        if Decimal(amount) <= 0:
            raise BusinessRuleError("Payment amount must be greater than zero.")
        if supplier.company_id != company.id:
            raise BusinessRuleError("Invalid supplier reference.")
        from reporting.gst_periods import assert_period_allows_money_amend

        gate_date = payment_date or timezone.localdate()
        # BB-000700: gate in service layer, not only HTTP views.
        assert_period_allows_money_amend(company, gate_date)
        utr_n = normalize_utr((utr or reference) if mode in ("UPI", "BANK") else utr)
        if getattr(company, "require_payment_reference", False) and mode in ("UPI", "BANK") and not utr_n:
            raise BusinessRuleError("UTR / payment reference is required for UPI and Bank payments.")
        if bank_account and bank_account.company_id != company.id:
            raise BusinessRuleError("Invalid bank account.")
        _assert_utr_unique(company=company, utr=utr_n)
        tds_amt = Decimal(str(tds_amount or 0))
        tds_rt = Decimal(str(tds_rate or 0))
        if tds_amt < 0 or tds_rt < 0:
            raise BusinessRuleError("TDS rate/amount cannot be negative.")
        if tds_amt > Decimal(str(amount)):
            raise BusinessRuleError("TDS amount cannot exceed the payment amount.")
        from purchases.models import PurchaseInvoice

        if tds_amt > 0 and PurchaseInvoice.objects.filter(
            company=company,
            supplier=supplier,
            tds_amount__gt=0,
            status=PurchaseInvoice.Status.COMPLETED,
        ).exists():
            raise BusinessRuleError(
                "This supplier already has invoices with TDS. Record TDS on the invoice only; "
                "do not also set TDS on the payment."
            )
        gstin_key = resolve_series_gstin(company)
        payment = SupplierPayment(
            company=company,
            supplier=supplier,
            amount=amount,
            mode=mode,
            reference=reference,
            utr=utr_n,
            notes=notes,
            bank_account=bank_account,
            source=source,
            tds_section=(tds_section or "").strip(),
            tds_rate=tds_rt,
            tds_amount=tds_amt,
            created_by=user,
            updated_by=user,
            number=DocumentNumberService.next_number(
                company,
                "SUPPLIER_PAYMENT",
                gstin=gstin_key,
                on_date=(payment_date or timezone.localdate()) if gstin_key else None,
            ),
        )
        if payment_date:
            payment.payment_date = payment_date
        payment.save()
        if company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_supplier_payment(payment, user)
        emit("document.completed", document=payment, user=user, event="supplier_payment.created")
        return payment

    @staticmethod
    @transaction.atomic
    def allocate_receipt(*, receipt, sales_invoice, amount, user=None):
        from ledgers.services import LedgerService
        from sales.models import SalesInvoice

        amount = Decimal(amount)
        if amount <= 0:
            raise BusinessRuleError("Allocation amount must be greater than zero.")
        if receipt.company_id != sales_invoice.company_id:
            raise BusinessRuleError("Receipt and invoice belong to different companies.")
        if receipt.customer_id != sales_invoice.customer_id:
            raise BusinessRuleError(
                "Receipt customer must match the invoice customer.",
                code=HelpCode.ALLOCATION_PARTY_MISMATCH,
            )

        receipt = CustomerReceipt.objects.select_for_update().get(pk=receipt.pk)
        sales_invoice = SalesInvoice.objects.select_for_update().get(pk=sales_invoice.pk)

        if sales_invoice.status not in ("COMPLETED", "RETURNED"):
            raise BusinessRuleError("Allocations are only allowed against completed invoices.")
        if receipt.status != ReceiptStatus.POSTED:
            raise BusinessRuleError("Only posted receipts can be allocated.")

        unallocated = receipt.amount - _allocated_of_payment("receipt", receipt)
        if amount > unallocated:
            raise BusinessRuleError(
                f"Allocation {amount} exceeds unallocated receipt amount {unallocated}.",
                code=HelpCode.ALLOCATION_EXCEEDS_UNALLOCATED,
            )
        open_outstanding = LedgerService.sales_invoice_outstanding(sales_invoice)
        if amount > open_outstanding:
            raise BusinessRuleError(
                f"Allocation {amount} exceeds invoice open outstanding {open_outstanding}."
            )
        alloc = PaymentAllocation.objects.create(
            company=receipt.company,
            receipt=receipt,
            sales_invoice=sales_invoice,
            amount=amount,
            created_by=user,
            updated_by=user,
        )
        if receipt.company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_receipt_allocation(alloc, user)
        return alloc

    @staticmethod
    @transaction.atomic
    def allocate_supplier_payment(*, payment, purchase_invoice, amount, user=None):
        from ledgers.services import LedgerService
        from purchases.models import PurchaseInvoice

        amount = Decimal(amount)
        if amount <= 0:
            raise BusinessRuleError("Allocation amount must be greater than zero.")
        if payment.company_id != purchase_invoice.company_id:
            raise BusinessRuleError("Payment and invoice belong to different companies.")
        if payment.supplier_id != purchase_invoice.supplier_id:
            raise BusinessRuleError("Payment supplier must match the invoice supplier.")

        payment = SupplierPayment.objects.select_for_update().get(pk=payment.pk)
        purchase_invoice = PurchaseInvoice.objects.select_for_update().get(pk=purchase_invoice.pk)

        if purchase_invoice.status not in ("COMPLETED", "RETURNED"):
            raise BusinessRuleError("Allocations are only allowed against completed invoices.")
        if payment.status != SupplierPaymentStatus.POSTED:
            raise BusinessRuleError("Only posted supplier payments can be allocated.")

        unallocated = (
            payment.amount
            + Decimal(str(getattr(payment, "tds_amount", 0) or 0))
            - _allocated_of_payment("supplier_payment", payment)
        )
        if amount > unallocated:
            raise BusinessRuleError(
                f"Allocation {amount} exceeds unallocated payment amount {unallocated}."
            )
        open_outstanding = LedgerService.purchase_invoice_outstanding(purchase_invoice)
        if amount > open_outstanding:
            raise BusinessRuleError(
                f"Allocation {amount} exceeds invoice open outstanding {open_outstanding}."
            )
        inv_tds = Decimal(str(getattr(purchase_invoice, "tds_amount", 0) or 0))
        pay_tds = Decimal(str(getattr(payment, "tds_amount", 0) or 0))
        if inv_tds > 0 and pay_tds > 0:
            raise BusinessRuleError(
                "This purchase already recorded TDS. Allocate the net bank amount without "
                "TDS on the supplier payment so TDS payable is not credited twice."
            )
        alloc = PaymentAllocation.objects.create(
            company=payment.company,
            supplier_payment=payment,
            purchase_invoice=purchase_invoice,
            amount=amount,
            created_by=user,
            updated_by=user,
        )
        if payment.company.accounting_enabled:
            from accounting.services import PostingService

            PostingService.post_supplier_payment_allocation(alloc, user)
        return alloc

    @staticmethod
    @transaction.atomic
    def reverse_allocation(*, allocation, user=None):
        """BB-000651: unallocate without hard-delete; reverse JE and reopen invoice headroom."""
        alloc = PaymentAllocation.objects.select_for_update().get(pk=allocation.pk)
        if alloc.reversed_at:
            return alloc
        from reporting.gst_periods import assert_period_allows_money_amend

        gate_date = None
        if alloc.receipt_id:
            gate_date = alloc.receipt.receipt_date
        elif alloc.supplier_payment_id:
            gate_date = alloc.supplier_payment.payment_date
        assert_period_allows_money_amend(alloc.company, gate_date)
        _reverse_allocation_journals(alloc, user=user)
        alloc.reversed_at = timezone.now()
        alloc.updated_by = user
        alloc.save(update_fields=["reversed_at", "updated_by", "updated_at"])
        return alloc

    @staticmethod
    @transaction.atomic
    def void_receipt(*, receipt, user=None, reason=""):
        """BB-000650: VOID receipt — reverse allocations + CREATE JE; never hard-delete."""
        rec = CustomerReceipt.objects.select_for_update().get(pk=receipt.pk)
        if rec.status == ReceiptStatus.VOIDED:
            return rec
        if rec.status == ReceiptStatus.REFUNDED:
            raise BusinessRuleError("Refunded receipts cannot be voided.")
        if rec.gateway_payment_id or rec.source == PaymentSource.GATEWAY:
            raise BusinessRuleError("Gateway receipts must be refunded, not voided.")
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(rec.company, rec.receipt_date)
        for alloc in list(rec.allocations.select_for_update().filter(reversed_at__isnull=True)):
            PaymentService.reverse_allocation(allocation=alloc, user=user)
        # R2-004: a void is a fresh event — reverse on today's date, not the
        # original receipt date (which may sit in a soft-closed period).
        _reverse_money_document_journal(
            company=rec.company,
            source_type="CUSTOMER_RECEIPT",
            source_id=rec.id,
            user=user,
        )
        note = (rec.notes or "").strip()
        void_note = f"VOIDED{(': ' + reason) if reason else ''}"
        rec.notes = f"{note}\n{void_note}".strip() if note else void_note
        rec.status = ReceiptStatus.VOIDED
        rec.updated_by = user
        rec.save(update_fields=["notes", "status", "updated_by", "updated_at"])
        emit("document.voided", document=rec, user=user, event="customer_receipt.voided")
        return rec

    @staticmethod
    @transaction.atomic
    def void_supplier_payment(*, payment, user=None, reason=""):
        """BB-000650: VOID supplier payment — reverse allocations + CREATE JE."""
        pay = SupplierPayment.objects.select_for_update().get(pk=payment.pk)
        if pay.status == SupplierPaymentStatus.VOIDED:
            return pay
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(pay.company, pay.payment_date)
        for alloc in list(pay.allocations.select_for_update().filter(reversed_at__isnull=True)):
            PaymentService.reverse_allocation(allocation=alloc, user=user)
        # R2-004: void reverses on today's date, not the original payment date.
        _reverse_money_document_journal(
            company=pay.company,
            source_type="SUPPLIER_PAYMENT",
            source_id=pay.id,
            user=user,
        )
        note = (pay.notes or "").strip()
        void_note = f"VOIDED{(': ' + reason) if reason else ''}"
        pay.notes = f"{note}\n{void_note}".strip() if note else void_note
        pay.status = SupplierPaymentStatus.VOIDED
        pay.updated_by = user
        pay.save(update_fields=["notes", "status", "updated_by", "updated_at"])
        emit("document.voided", document=pay, user=user, event="supplier_payment.voided")
        return pay

    @staticmethod
    def ensure_default_bank_account(company, user=None) -> BankAccount:
        existing = BankAccount.objects.filter(company=company, is_default=True).first()
        if existing:
            return existing
        name = "Cash" if not company.bank_account else (company.bank_name or "Primary Bank")
        acct = BankAccount.objects.create(
            company=company,
            name=name or "Primary",
            account_number_masked=(company.bank_account or "")[-4:].rjust(4, "*") if company.bank_account else "",
            ifsc=company.bank_ifsc or "",
            account_type="CASH_BOX" if not company.bank_account else "CURRENT",
            opening_balance=company.opening_cash_balance or Decimal("0"),
            opening_as_of=company.opening_cash_as_of,
            is_default=True,
            created_by=user,
            updated_by=user,
        )
        return acct

    @staticmethod
    @transaction.atomic
    def create_payment_link(
        *,
        company,
        amount,
        sales_invoice=None,
        customer=None,
        allow_partial=False,
        expires_hours=72,
        provider=None,
        notes="",
        user=None,
        public_base_url="",
    ):
        from ledgers.services import LedgerService

        amount = Decimal(amount)
        if amount <= 0:
            raise BusinessRuleError("Payment link amount must be greater than zero.")
        if sales_invoice:
            from sales.models import SalesInvoice

            sales_invoice = SalesInvoice.objects.select_for_update().get(pk=sales_invoice.pk)
            if sales_invoice.company_id != company.id:
                raise BusinessRuleError("Invalid invoice.")
            if sales_invoice.status not in ("COMPLETED", "RETURNED"):
                raise BusinessRuleError("Payment links require a completed invoice.")
            customer = sales_invoice.customer
            outstanding = LedgerService.sales_invoice_outstanding(sales_invoice)
            if amount > outstanding:
                raise BusinessRuleError(
                    f"Link amount {amount} exceeds invoice outstanding {outstanding}."
                )
            if not allow_partial and amount != outstanding:
                # Default: full outstanding
                amount = outstanding
        if not customer:
            raise BusinessRuleError("Customer is required for a payment link.")
        if customer.company_id != company.id:
            raise BusinessRuleError("Invalid customer.")

        from django.conf import settings

        from payments.gateway import DISABLED_PROVIDERS, sandbox_forbidden_env

        provider = (provider or getattr(company, "payment_gateway_provider", None) or "razorpay").lower()
        if provider in DISABLED_PROVIDERS:
            raise BusinessRuleError(
                f"Payment provider '{provider}' is not enabled. Use sandbox (test) or razorpay."
            )
        # Sandbox only in development/test/local (create path).
        if provider == "sandbox" and sandbox_forbidden_env():
            raise BusinessRuleError(
                "Payment provider 'sandbox' cannot be used outside development/test/local."
            )
        creds = decrypt_gateway_credentials(getattr(company, "payment_gateway_credentials_encrypted", "") or "")
        if provider != "sandbox" and not creds:
            # Only allowlist envs may remap empty-cred + test_mode → sandbox.
            django_env = (getattr(settings, "DJANGO_ENV", "") or "").lower().strip()
            if (
                getattr(company, "payment_gateway_test_mode", False)
                and django_env in ("development", "test", "local")
                and not sandbox_forbidden_env()
            ):
                provider = "sandbox"
            else:
                raise BusinessRuleError(
                    "Payment gateway credentials are required. Configure Razorpay or use provider=sandbox in test."
                )
        # BB-000393: one open link per invoice — prevent outstanding oversubscription.
        if sales_invoice:
            open_links = list(
                PaymentLink.objects.select_for_update().filter(
                    company=company,
                    sales_invoice=sales_invoice,
                    status__in=(
                        PaymentLinkStatus.CREATED,
                        PaymentLinkStatus.SENT,
                        PaymentLinkStatus.PARTIALLY_PAID,
                    ),
                )
            )
            reserved = sum((Decimal(str(l.amount)) for l in open_links), Decimal("0"))
            if reserved + amount > outstanding + Decimal("0.001"):
                raise BusinessRuleError(
                    f"Open payment links already reserve {reserved}; "
                    f"cannot create another link of {amount} against outstanding {outstanding}."
                )
        adapter = get_adapter(provider, creds if provider != "sandbox" else None, company_id=company.id)

        # BB-000514: ≥128-bit entropy (token_urlsafe(24) ≈ 192 bits).
        token = secrets.token_urlsafe(24)
        expires_at = timezone.now() + timedelta(hours=expires_hours)
        callback = (public_base_url or "").rstrip("/") + f"/pay/{token}"

        result = adapter.create_payment_link(
            amount=amount,
            description=notes or (sales_invoice.number if sales_invoice else f"Payment {customer.name}"),
            customer_name=customer.name or "",
            customer_email=getattr(customer, "email", "") or "",
            customer_phone=getattr(customer, "phone", "") or "",
            reference=sales_invoice.number if sales_invoice else token[:12],
            callback_url=callback,
            expire_by=int(expires_at.timestamp()),
            accept_partial=allow_partial,
            allow_partial=allow_partial,
        )

        link = PaymentLink.objects.create(
            company=company,
            token=token,
            sales_invoice=sales_invoice,
            customer=customer,
            amount=amount,
            allow_partial=allow_partial,
            status=PaymentLinkStatus.CREATED,
            expires_at=expires_at,
            provider=adapter.name if hasattr(adapter, "name") else provider,
            provider_link_id=result.provider_link_id,
            provider_short_url=result.short_url,
            notes=notes,
            created_by=user,
            updated_by=user,
        )
        emit("payment_link.created", document=link, user=user, event="payment_link.created")
        return link

    @staticmethod
    @transaction.atomic
    def cancel_payment_link(*, link, user=None):
        link = PaymentLink.objects.select_for_update().get(pk=link.pk)
        if link.status == PaymentLinkStatus.PAID:
            raise BusinessRuleError("Cannot cancel a paid payment link.")
        if link.provider_link_id and (link.provider or "") not in ("", "sandbox"):
            creds = decrypt_gateway_credentials(
                getattr(link.company, "payment_gateway_credentials_encrypted", "") or ""
            )
            adapter = get_adapter(link.provider, creds if creds else None, company_id=link.company_id)
            cancel_fn = getattr(adapter, "cancel_payment_link", None)
            if cancel_fn is None:
                raise BusinessRuleError(
                    f"Cannot cancel a live {link.provider} payment link from BizBoard. "
                    "Deactivate it in the provider dashboard first."
                )
            cancel_fn(provider_link_id=link.provider_link_id)
        # PARTIALLY_PAID may cancel remaining collection window.
        link.status = PaymentLinkStatus.CANCELLED
        link.updated_by = user
        link.save(update_fields=["status", "updated_by", "updated_at"])
        return link

    @staticmethod
    def _raise_or_park(existing, holding: bool, reason: str, message: str):
        from payments.holding import park_gateway_payment

        # Money already captured at the provider must not vanish when books
        # cannot post (closed period), even if holding-state is off.
        always_park = str(reason or "").upper() in {
            "CLOSED_PERIOD",
            "PERIOD_LOCKED",
            "GST_PERIOD_LOCKED",
            "PERIOD_CLOSED",
        }
        if holding or always_park:
            return park_gateway_payment(existing, reason, message)
        raise BusinessRuleError(message)

    @staticmethod
    @transaction.atomic
    def finalize_gateway_payment(
        *,
        company,
        provider: str,
        provider_payment_id: str,
        amount: Decimal,
        fee: Decimal = Decimal("0"),
        payment_link: PaymentLink | None = None,
        raw_payload=None,
        user=None,
    ):
        """Idempotent webhook finalize → receipt + allocate.

        W0-03: persist the provider payment id first. When GATEWAY_HOLDING_STATE
        is on, books failures park as CAPTURED_PENDING_BOOKS instead of dropping
        the capture or 4xx-ing Razorpay.
        """
        from payments.holding import (
            books_hold_reason,
            clear_holding,
            err_detail,
            gateway_holding_enabled,
            park_gateway_payment,
            suffixed_internal_utr,
        )

        if not provider_payment_id:
            raise BusinessRuleError("Missing provider payment id.")

        # PAY-11: never persist cardholder / contact PII from the webhook body.
        raw_payload = redact_gateway_payload(raw_payload) if raw_payload is not None else None

        holding = gateway_holding_enabled()

        existing = (
            GatewayPayment.objects.select_for_update()
            .filter(company=company, provider=provider, provider_payment_id=provider_payment_id)
            .first()
        )
        if existing and existing.status == GatewayPaymentStatus.CAPTURED:
            from ledgers.services import LedgerService

            link = existing.payment_link
            receipt = (
                CustomerReceipt.objects.filter(gateway_payment=existing)
                .exclude(status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED))
                .first()
            )
            if link and link.sales_invoice_id and receipt:
                try:
                    outstanding = LedgerService.sales_invoice_outstanding(link.sales_invoice)
                    unalloc = Decimal(str(receipt.amount or 0)) - _allocated_of_payment("receipt", receipt)
                    alloc_amt = min(unalloc, outstanding)
                    if alloc_amt > 0:
                        PaymentService.allocate_receipt(
                            receipt=receipt,
                            sales_invoice=link.sales_invoice,
                            amount=alloc_amt,
                            user=user,
                        )
                except BusinessRuleError:
                    logger.exception(
                        "Retry allocation for captured gateway payment %s failed",
                        existing.provider_payment_id,
                    )
            return existing

        if existing is None:
            try:
                existing = GatewayPayment.objects.create(
                    company=company,
                    provider=provider,
                    provider_payment_id=provider_payment_id,
                    amount=amount,
                    fee=fee,
                    status=GatewayPaymentStatus.CREATED,
                    payment_link=payment_link,
                    raw_payload=raw_payload,
                    created_by=user,
                    updated_by=user,
                )
            except IntegrityError:
                # First-arrival race: peer committed the unique row — re-fetch.
                existing = (
                    GatewayPayment.objects.select_for_update()
                    .filter(
                        company=company,
                        provider=provider,
                        provider_payment_id=provider_payment_id,
                    )
                    .first()
                )
                if existing is None:
                    raise
                if existing.status == GatewayPaymentStatus.CAPTURED:
                    return existing
        else:
            # R3-008: a repeat (pre-capture) webhook that reports a different
            # amount than the one we first recorded is worth a loud log line —
            # the capture below still validates against link.amount.
            if Decimal(str(existing.amount or 0)) != Decimal(str(amount or 0)):
                logger.warning(
                    "Gateway %s payment %s amount changed on repeat webhook: %s -> %s",
                    provider, provider_payment_id, existing.amount, amount,
                )
            existing.amount = amount
            existing.fee = fee
            existing.payment_link = payment_link or existing.payment_link
            existing.raw_payload = raw_payload
            existing.save()

        retrying_hold = existing.status == GatewayPaymentStatus.CAPTURED_PENDING_BOOKS

        link = payment_link or existing.payment_link
        if link is None and existing.payment_link_id:
            link = PaymentLink.objects.select_for_update().filter(pk=existing.payment_link_id).first()

        if link is None:
            return PaymentService._raise_or_park(
                existing, holding, "NO_LINK", "Gateway payment is not tied to a payment link."
            )

        link = PaymentLink.objects.select_for_update().get(pk=link.pk)
        if link.status == PaymentLinkStatus.CANCELLED and not retrying_hold:
            return PaymentService._raise_or_park(
                existing, holding, "LINK_CANCELLED", "Payment link has been cancelled."
            )
        if link.sales_invoice_id:
            from sales.models import SalesInvoice

            invoice_status = (
                SalesInvoice.objects.filter(pk=link.sales_invoice_id)
                .values_list("status", flat=True)
                .first()
            )
            if invoice_status == SalesInvoice.Status.CANCELLED:
                return PaymentService._raise_or_park(
                    existing,
                    holding,
                    "INVOICE_CANCELLED",
                    "Invoice has been cancelled; payment cannot be captured.",
                )
        # BB-000438: link already fully paid — do not mark a second provider id CAPTURED without receipt.
        if link.status == PaymentLinkStatus.PAID and link.paid_receipt_id:
            if existing.status != GatewayPaymentStatus.CAPTURED:
                if holding:
                    return park_gateway_payment(
                        existing,
                        "ALREADY_PAID",
                        "Payment link is already paid; duplicate capture parked.",
                    )
                existing.status = GatewayPaymentStatus.FAILED
                existing.save(update_fields=["status", "updated_at"])
            raise BusinessRuleError(
                "Payment link is already paid; duplicate capture ignored."
            )

        if (
            not retrying_hold
            and link.expires_at
            and link.expires_at < timezone.now()
            and link.status
            not in (
                PaymentLinkStatus.PAID,
                PaymentLinkStatus.PARTIALLY_PAID,
            )
        ):
            link.status = PaymentLinkStatus.EXPIRED
            link.save(update_fields=["status", "updated_at"])
            return PaymentService._raise_or_park(
                existing, holding, "LINK_EXPIRED", "Payment link has expired."
            )

        capture_amount = Decimal(amount)
        if not retrying_hold:
            if not link.allow_partial and capture_amount < link.amount:
                return PaymentService._raise_or_park(
                    existing,
                    holding,
                    "AMOUNT_MISMATCH",
                    f"Captured amount {capture_amount} is below link amount {link.amount}; partial capture is not allowed.",
                )
            # BB-000391: always reject over-capture (even when allow_partial).
            if capture_amount > link.amount:
                return PaymentService._raise_or_park(
                    existing,
                    holding,
                    "AMOUNT_MISMATCH",
                    f"Captured amount {capture_amount} exceeds link amount {link.amount}.",
                )

        # Sum prior captures on this link (gateway receipts).
        prior_captured = (
            GatewayPayment.objects.filter(
                payment_link=link,
                status__in=(
                    GatewayPaymentStatus.CAPTURED,
                    GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
                ),
            )
            .exclude(pk=existing.pk)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        remaining_on_link = link.amount - Decimal(str(prior_captured))
        if not retrying_hold and capture_amount > remaining_on_link:
            return PaymentService._raise_or_park(
                existing,
                holding,
                "AMOUNT_MISMATCH",
                f"Captured amount {capture_amount} exceeds remaining link balance {remaining_on_link}.",
            )

        # R3-002: staff may have pre-recorded this exact payment manually (UTR ==
        # provider id). Adopt that receipt rather than 500-ing on UTR uniqueness
        # and letting the provider retry forever.
        _utr = (existing.internal_utr or provider_payment_id)[:64]
        existing_receipt = (
            CustomerReceipt.objects.filter(gateway_payment=existing)
            .exclude(status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED))
            .first()
        )
        if existing_receipt is None:
            existing_receipt = (
                CustomerReceipt.objects.filter(company=company, utr=provider_payment_id[:64])
                .exclude(status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED))
                .first()
            )
        if existing_receipt is not None:
            from decimal import Decimal as _D

            if _D(str(existing_receipt.amount or 0)) != _D(str(capture_amount)):
                raise BusinessRuleError(
                    "Existing receipt UTR matches this capture but the amount differs. "
                    "Resolve the UTR clash before adopting the gateway payment."
                )
            if existing_receipt.customer_id and link.customer_id and existing_receipt.customer_id != link.customer_id:
                raise BusinessRuleError(
                    "Existing receipt UTR matches this capture but the customer differs."
                )
            receipt = existing_receipt
            if receipt.gateway_payment_id is None:
                receipt.gateway_payment = existing
                receipt.source = PaymentSource.PAYMENT_LINK
                receipt.save(update_fields=["gateway_payment", "source", "updated_at"])
        else:
            bank_account = BankAccount.objects.filter(company=company, is_default=True).first()
            try:
                with transaction.atomic():
                    receipt = PaymentService.create_receipt(
                        company=company,
                        customer=link.customer,
                        amount=capture_amount,
                        mode="UPI",
                        reference=provider_payment_id,
                        utr=_utr,
                        notes=f"Gateway {provider} capture",
                        user=user,
                        bank_account=bank_account,
                        source=PaymentSource.PAYMENT_LINK,
                        gateway_payment=existing,
                        warn_utr_duplicate=False,
                        # W0-03: when holding is on, do not bypass — park instead of silent post.
                        bypass_period_gate=False,
                    )
            except (BusinessRuleError, IntegrityError) as exc:
                reason = books_hold_reason(exc)
                if reason == "UTR_CLASH" and holding:
                    suffixed = suffixed_internal_utr(provider_payment_id, existing.pk)
                    existing.internal_utr = suffixed
                    existing.save(update_fields=["internal_utr", "updated_at"])
                    try:
                        with transaction.atomic():
                            receipt = PaymentService.create_receipt(
                                company=company,
                                customer=link.customer,
                                amount=capture_amount,
                                mode="UPI",
                                reference=provider_payment_id,
                                utr=suffixed,
                                notes=f"Gateway {provider} capture (UTR suffixed)",
                                user=user,
                                bank_account=bank_account,
                                source=PaymentSource.PAYMENT_LINK,
                                gateway_payment=existing,
                                warn_utr_duplicate=True,
                                bypass_period_gate=False,
                            )
                    except (BusinessRuleError, IntegrityError) as exc2:
                        return park_gateway_payment(
                            existing, books_hold_reason(exc2), err_detail(exc2)
                        )
                else:
                    return PaymentService._raise_or_park(
                        existing, holding, reason, err_detail(exc)
                    )
        # Keep the receipt even if allocation fails; never mark the link PAID
        # until the invoice is actually allocated (unallocated advance otherwise).
        allocated_ok = True
        if link.sales_invoice_id:
            from ledgers.services import LedgerService

            try:
                with transaction.atomic():
                    outstanding = LedgerService.sales_invoice_outstanding(link.sales_invoice)
                    alloc_amt = min(capture_amount, outstanding)
                    if alloc_amt > 0:
                        PaymentService.allocate_receipt(
                            receipt=receipt,
                            sales_invoice=link.sales_invoice,
                            amount=alloc_amt,
                            user=user,
                        )
                    elif outstanding > 0 and capture_amount > 0:
                        allocated_ok = False
            except BusinessRuleError:
                allocated_ok = False
                logger.exception(
                    "Gateway payment %s captured but allocation failed for invoice %s",
                    provider_payment_id,
                    link.sales_invoice_id,
                )

        clear_holding(existing)
        total_captured = Decimal(str(prior_captured)) + capture_amount
        # BB-000392: PARTIALLY_PAID until fully collected AND allocated.
        if total_captured + Decimal("0.001") >= link.amount and allocated_ok:
            link.status = PaymentLinkStatus.PAID
            link.paid_receipt = receipt
        else:
            link.status = PaymentLinkStatus.PARTIALLY_PAID
            if not link.paid_receipt_id:
                link.paid_receipt = receipt
        link.updated_by = user
        link.save(update_fields=["status", "paid_receipt", "updated_by", "updated_at"])
        emit("payment_link.paid", document=link, user=user, event="payment_link.paid")
        return existing

    @staticmethod
    def reconcile_gateway_captures(*, company_id=None, older_than_minutes: int = 5):
        """Retry parked captures. Default: park until the period is open (no silent next-period post)."""
        from datetime import timedelta as _td

        from payments.holding import gateway_holding_enabled

        if not gateway_holding_enabled():
            return 0, 0
        qs = GatewayPayment.objects.filter(
            status=GatewayPaymentStatus.CAPTURED_PENDING_BOOKS
        ).select_related("company", "payment_link")
        if company_id:
            qs = qs.filter(company_id=company_id)
        if older_than_minutes:
            cutoff = timezone.now() - _td(minutes=older_than_minutes)
            qs = qs.filter(Q(holding_since__isnull=True) | Q(holding_since__lte=cutoff))
        posted = 0
        attempted = 0
        refunded = 0
        for gp in qs.order_by("id")[:200]:
            attempted += 1
            # INVOICE_CANCELLED / LINK_CANCELLED holds can never post to books —
            # retrying finalize just re-parks them. Refund the customer instead
            # (no receipt/GL was posted, so there is nothing to unwind).
            if (gp.holding_reason or "") in _TERMINAL_HOLDING_REASONS:
                try:
                    refunded += PaymentService._auto_refund_parked_capture(gp)
                except Exception:
                    logger.exception(
                        "Auto-refund of parked capture %s failed", gp.provider_payment_id
                    )
                continue
            try:
                result = PaymentService.finalize_gateway_payment(
                    company=gp.company,
                    provider=gp.provider,
                    provider_payment_id=gp.provider_payment_id,
                    amount=gp.amount,
                    fee=gp.fee or Decimal("0"),
                    payment_link=gp.payment_link,
                    raw_payload=gp.raw_payload,
                )
                if result.status == GatewayPaymentStatus.CAPTURED:
                    posted += 1
            except Exception:
                logger.exception(
                    "Holding reconcile failed for gateway payment %s", gp.provider_payment_id
                )
        if refunded:
            logger.info("Holding reconcile auto-refunded %s terminal capture(s)", refunded)
        return posted, attempted

    @staticmethod
    def _auto_refund_parked_capture(gp) -> int:
        """Enqueue a provider refund for a capture parked against a cancelled
        invoice/link. gp.status flips to REFUNDED only once the provider confirms
        (see execute_gateway_refund). Idempotent — one outbox row per capture."""
        from .models import GatewayRefundOutbox

        with transaction.atomic():
            gp = GatewayPayment.objects.select_for_update().get(pk=gp.pk)
            if gp.status != GatewayPaymentStatus.CAPTURED_PENDING_BOOKS:
                return 0
            outbox, created = GatewayRefundOutbox.objects.get_or_create(
                company=gp.company,
                gateway_payment=gp,
                amount=gp.amount,
                defaults={
                    "provider_payment_id": gp.provider_payment_id,
                },
            )
        if created:
            from payments.tasks import execute_gateway_refund

            cid = outbox.company_id
            oid = outbox.id
            transaction.on_commit(
                lambda: execute_gateway_refund.delay(oid, company_id=cid)
            )
            return 1
        return 0

    @staticmethod
    def _unwind_refund_books(gp, *, user, refund_amount, reason="", full=True, refund_key=None):
        """Reverse allocations (full or proportional), post refund GL, reopen the link on full.

        ``refund_key`` is the per-logical-refund idempotency key. It is recorded
        in ``raw["applied_refund_keys"]`` and this call no-ops if that key is
        already present (B4-001) — so a retried ``execute_gateway_refund`` for a
        *partial* refund cannot reverse allocations / post the refund JE twice.
        ``books_unwound`` (set only on a full refund) is kept as a second guard
        for the legacy path.
        """
        from .models import GatewayPaymentStatus, PaymentLinkStatus, ReceiptStatus

        raw = gp.raw_payload if isinstance(gp.raw_payload, dict) else {}
        applied_keys = list(raw.get("applied_refund_keys") or [])
        if raw.get("books_unwound"):
            return
        if refund_key and refund_key in applied_keys:
            return
        company = gp.company
        leftover = Decimal(str(refund_amount or 0))
        receipts = list(
            CustomerReceipt.objects.filter(gateway_payment=gp)
            .select_related("gateway_payment")
            .select_for_update()
        )
        je_seq = int(raw.get("refund_je_seq") or 0)
        for receipt in receipts:
            if leftover <= 0:
                break
            for alloc in list(
                receipt.allocations.select_for_update()
                .filter(reversed_at__isnull=True)
                .order_by("-id")
            ):
                if leftover <= 0:
                    break
                alloc_amount = Decimal(str(alloc.amount or 0))
                invoice = alloc.sales_invoice
                if alloc_amount <= leftover:
                    PaymentService.reverse_allocation(allocation=alloc, user=user)
                    leftover -= alloc_amount
                else:
                    keep = alloc_amount - leftover
                    PaymentService.reverse_allocation(allocation=alloc, user=user)
                    if keep > 0 and invoice is not None:
                        PaymentService.allocate_receipt(
                            receipt=receipt, sales_invoice=invoice, amount=keep, user=user
                        )
                    leftover = Decimal("0")
            note = (receipt.notes or "").strip()
            refund_note = f"Refunded {refund_amount} via {gp.provider}" + (
                f": {reason}" if reason else ""
            )
            receipt.notes = f"{note}\n{refund_note}".strip() if note else refund_note
            if full:
                receipt.status = ReceiptStatus.REFUNDED
            receipt.updated_by = user
            receipt.save(update_fields=["notes", "status", "updated_by", "updated_at"])
        if receipts and getattr(company, "accounting_enabled", False):
            from accounting.services import PostingService
            from reporting.gst_periods import assert_period_allows_money_amend

            je_seq += 1
            # B4-008: the refund must not be blocked (the customer's money has
            # left), but it must not post into a closed/filed GST period either.
            # Post on the original receipt date when that period is open, else
            # today — same policy as void_* / _reverse_money_document_journal.
            refund_entry_date = receipts[0].receipt_date or timezone.localdate()
            try:
                assert_period_allows_money_amend(company, refund_entry_date)
            except BusinessRuleError:
                refund_entry_date = timezone.localdate()
            PostingService.post_receipt_refund(
                receipts[0],
                user=user,
                amount=refund_amount,
                purpose="REFUND" if full else f"REFUND_{je_seq}",
                entry_date=refund_entry_date,
            )
        if full and gp.payment_link_id:
            link = PaymentLink.objects.select_for_update().filter(pk=gp.payment_link_id).first()
            if link is not None:
                other_captured = GatewayPayment.objects.filter(
                    payment_link=link,
                    status__in=(
                        GatewayPaymentStatus.CAPTURED,
                        GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
                    ),
                ).exclude(pk=gp.pk).exists()
                if not other_captured:
                    link.status = (
                        PaymentLinkStatus.SENT
                        if link.status
                        in (
                            PaymentLinkStatus.PAID,
                            PaymentLinkStatus.PARTIALLY_PAID,
                            PaymentLinkStatus.SENT,
                        )
                        else PaymentLinkStatus.CREATED
                    )
                    link.paid_receipt = None
                    link.updated_by = user
                    link.save(update_fields=["status", "paid_receipt", "updated_by", "updated_at"])
        if refund_key and refund_key not in applied_keys:
            applied_keys.append(refund_key)
        raw = {
            **raw,
            "books_unwound": bool(full),
            "refund_amount": str(refund_amount),
            "refund_reason": reason,
            "refund_je_seq": je_seq,
            "applied_refund_keys": applied_keys,
        }
        gp.raw_payload = raw
        gp.save(update_fields=["raw_payload", "updated_at"])

    @staticmethod
    def _finalise_refund_state(gp, *, refund_amount, reason, full, user):
        """Move `gp` to its post-refund status and record the partial-refund entry.

        Runs inside a short transaction opened by the caller.
        """
        from .models import GatewayPaymentStatus

        raw = gp.raw_payload if isinstance(gp.raw_payload, dict) else {}
        if not full:
            partials = list(raw.get("partial_refunds") or [])
            partials.append({"amount": str(refund_amount), "reason": reason, "books": True})
            gp.raw_payload = {**raw, "partial_refunds": partials}
            gp.status = GatewayPaymentStatus.PARTIALLY_REFUNDED
            gp.updated_by = user
            gp.save(update_fields=["raw_payload", "status", "updated_by", "updated_at"])
            emit(
                "gateway_payment.partial_refund",
                document=gp, user=user, event="gateway_payment.partial_refund",
            )
            return
        gp.status = GatewayPaymentStatus.REFUNDED
        gp.updated_by = user
        gp.raw_payload = {
            **raw,
            "refund_amount": str(refund_amount),
            "refund_reason": reason,
            "books_unwound": True,
        }
        gp.save(update_fields=["status", "raw_payload", "updated_by", "updated_at"])
        emit("gateway_payment.refunded", document=gp, user=user, event="gateway_payment.refunded")

    @staticmethod
    def refund_gateway_payment(*, gateway_payment, amount=None, user=None, reason="", skip_gateway=False):
        """Refund (full or partial) of a captured gateway payment.

        B4-003: the provider HTTP call runs **outside** any DB transaction. The
        flow is three phases:
          1. short txn — lock `gp`, validate, allocate a per-refund sequence, and
             commit a durable PENDING `GatewayRefundOutbox` row carrying the
             stable idempotency key;
          2. no transaction — `adapter.refund(...)`;
          3. short txn — unwind the books (idempotent on the refund key) and mark
             the outbox row SUCCEEDED.
        A crash anywhere after phase 1 leaves the committed PENDING row, which
        `retry_pending_gateway_refunds` -> `execute_gateway_refund` completes; the
        books are unwound exactly once (guarded by `raw["applied_refund_keys"]`).

        NOTE: this must not be called inside an outer `transaction.atomic()` — the
        provider call would be back inside a transaction. The `refund` API action
        and the webhook handler do not wrap it.
        """
        from .models import (
            GatewayPaymentStatus,
            GatewayRefundOutbox,
            GatewayRefundOutboxStatus,
        )

        # ---- phase 1: lock, validate, reserve a durable outbox row -----------
        with transaction.atomic():
            gp = GatewayPayment.objects.select_for_update().get(pk=gateway_payment.pk)
            if gp.status == GatewayPaymentStatus.REFUNDED:
                return gp
            if gp.status not in (
                GatewayPaymentStatus.CAPTURED,
                GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
                GatewayPaymentStatus.PARTIALLY_REFUNDED,
            ):
                raise BusinessRuleError("Only captured gateway payments can be refunded.")

            refund_amount = Decimal(amount if amount is not None else gp.amount)
            if refund_amount <= 0:
                raise BusinessRuleError("Invalid refund amount.")

            raw = gp.raw_payload if isinstance(gp.raw_payload, dict) else {}
            already = Decimal("0")
            for prior in raw.get("partial_refunds") or []:
                try:
                    already += Decimal(str((prior or {}).get("amount") or 0))
                except Exception:
                    continue
            remaining = max(Decimal("0"), Decimal(str(gp.amount or 0)) - already)
            if refund_amount > remaining:
                raise BusinessRuleError(
                    f"Refund {refund_amount} exceeds remaining captured amount {remaining}."
                )
            is_full_unwind = remaining > 0 and refund_amount >= remaining
            company = gp.company

            # B4-002: distinct provider key per logical refund; persisted now so a
            # crash+retry of *this* refund reuses the same key.
            refund_seq = int(raw.get("refund_seq") or 0) + 1
            idem_key = refund_idempotency_key(gp.id, refund_amount, seq=refund_seq)
            gp.raw_payload = {**raw, "refund_seq": refund_seq}
            gp.save(update_fields=["raw_payload", "updated_at"])

            if skip_gateway:
                # Provider already refunded (webhook). No HTTP -> unwind here.
                PaymentService._unwind_refund_books(
                    gp, user=user, refund_amount=refund_amount, reason=reason,
                    full=is_full_unwind, refund_key=idem_key,
                )
                PaymentService._finalise_refund_state(
                    gp, refund_amount=refund_amount, reason=reason,
                    full=is_full_unwind, user=user,
                )
                return gp

            outbox, _created = GatewayRefundOutbox.objects.get_or_create(
                company=company,
                gateway_payment=gp,
                idempotency_key=idem_key,
                defaults={
                    "provider_payment_id": gp.provider_payment_id,
                    "amount": refund_amount,
                    "status": GatewayRefundOutboxStatus.PENDING,
                    "created_by": user,
                    "updated_by": user,
                },
            )

        # ---- phase 2: provider HTTP call, no transaction --------------------
        def _enqueue_retry():
            from payments.tasks import execute_gateway_refund

            execute_gateway_refund.delay(outbox.id, company_id=company.id)

        try:
            creds = decrypt_gateway_credentials(
                getattr(company, "payment_gateway_credentials_encrypted", "") or ""
            )
            adapter = get_adapter(gp.provider, creds if creds else None)
            refund_id = gp.provider_payment_id
            if gp.provider == "cashfree":
                from payments.gateway import cashfree_order_id_for_refund

                refund_id = cashfree_order_id_for_refund(
                    gp.provider_payment_id, getattr(gp, "raw_payload", None)
                )
            adapter.refund(
                provider_payment_id=refund_id,
                amount=refund_amount,
                idempotency_key=idem_key,
            )
        except Exception:
            # Provider call failed / unknown outcome. The PENDING outbox row is
            # already committed; the retry beat will finish this refund. Do NOT
            # unwind the books here.
            logger.exception(
                "Gateway refund deferred to outbox for payment %s", gp.provider_payment_id
            )
            _enqueue_retry()
            return gp

        # ---- phase 3: unwind books, close the outbox row -------------------
        with transaction.atomic():
            gp = GatewayPayment.objects.select_for_update().get(pk=gp.pk)
            PaymentService._unwind_refund_books(
                gp, user=user, refund_amount=refund_amount, reason=reason,
                full=is_full_unwind, refund_key=idem_key,
            )
            GatewayRefundOutbox.objects.filter(pk=outbox.id).update(
                status=GatewayRefundOutboxStatus.SUCCEEDED,
                last_error="",
                next_attempt_at=None,
                updated_at=timezone.now(),
            )
            PaymentService._finalise_refund_state(
                gp, refund_amount=refund_amount, reason=reason,
                full=is_full_unwind, user=user,
            )
        return gp

    @staticmethod
    def share_payment_link(*, link, channel, recipient, user=None, public_base_url=""):
        from core.services.notifications import NotificationService
        from sales.whatsapp_send import allow_cloud_for_customer, persist_invoice_whatsapp

        if link.status in (PaymentLinkStatus.CANCELLED, PaymentLinkStatus.EXPIRED):
            raise BusinessRuleError("Cannot share a cancelled or expired link.")
        path = f"/pay/{link.token}"
        url = (public_base_url.rstrip("/") + path) if public_base_url else path
        body = (
            f"Please pay {link.amount} using this secure BizBoard link: {url}"
            + (f" (Invoice {link.sales_invoice.number})" if link.sales_invoice_id else "")
        )
        customer = link.customer
        if customer is None and link.sales_invoice_id:
            customer = link.sales_invoice.customer
        allow_cloud = False
        subject = f"Payment request — {link.company.name}"
        if (channel or "").upper() == "WHATSAPP":
            subject = "payment_reminder"
            allow_cloud = allow_cloud_for_customer(customer)
        notification = NotificationService.send(
            company=link.company,
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            user=user,
            allow_cloud=allow_cloud,
        )
        if (channel or "").upper() == "WHATSAPP" and link.sales_invoice_id:
            persist_invoice_whatsapp(link.sales_invoice, notification)
        if link.status == PaymentLinkStatus.CREATED:
            link.status = PaymentLinkStatus.SENT
            link.updated_by = user
            link.save(update_fields=["status", "updated_by", "updated_at"])
        return notification

    @staticmethod
    def payment_health(*, company):
        # R3-007: this "health strip" endpoint fans out into many aggregate
        # queries (per-invoice outstanding × up to 50, bank aging, dup UTRs).
        # Cache the whole result briefly so a dashboard refresh loop doesn't
        # hammer the DB.
        from django.core.cache import cache

        cache_key = f"payment_health:{company.pk}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        result = PaymentService._payment_health_uncached(company=company)
        cache.set(cache_key, result, 60)
        return result

    @staticmethod
    def _payment_health_uncached(*, company):
        from datetime import timedelta

        from django.db.models import Count
        from ledgers.services import LedgerService

        alerts = []
        ar = LedgerService.bulk_customer_outstanding(company) if hasattr(LedgerService, "bulk_customer_outstanding") else {}
        total_ar = sum(ar.values(), Decimal("0")) if isinstance(ar, dict) else Decimal("0")
        if not (company.upi_id or "").strip() and total_ar > 0:
            alerts.append(
                {
                    "code": "UPI_ID_MISSING",
                    "severity": "critical",
                    "message": "Company UPI ID is missing while open receivables exist.",
                }
            )

        dup_utrs = (
            CustomerReceipt.objects.filter(company=company)
            .exclude(status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED))
            .exclude(utr="")
            .values("utr")
            .annotate(c=Count("id"))
            .filter(c__gt=1)
        )
        for row in dup_utrs[:20]:
            alerts.append(
                {
                    "code": "DUPLICATE_UTR",
                    "severity": "critical",
                    "message": f"UTR {row['utr']} appears on {row['c']} receipts.",
                    "utr": row["utr"],
                }
            )

        # Open completed invoices without payment link
        from sales.models import SalesInvoice

        open_invs = SalesInvoice.objects.filter(company=company, status__in=("COMPLETED", "RETURNED"))[:50]
        for inv in open_invs:
            outstanding = LedgerService.sales_invoice_outstanding(inv)
            if outstanding <= 0:
                continue
            if not PaymentLink.objects.filter(
                company=company,
                sales_invoice=inv,
                status__in=(PaymentLinkStatus.CREATED, PaymentLinkStatus.SENT, PaymentLinkStatus.PAID),
            ).exists() and not (company.upi_id or "").strip():
                alerts.append(
                    {
                        "code": "OPEN_INVOICE_NO_LINK_OR_UPI",
                        "severity": "warning",
                        "message": f"Invoice {inv.number} has outstanding {outstanding} with no payment link and no company UPI.",
                        "invoice_id": inv.id,
                    }
                )
                break  # one sample warning is enough for health strip

        unmatched = BankStatementLine.objects.filter(
            company=company,
            match_status__in=(BankLineMatchStatus.UNMATCHED, BankLineMatchStatus.SUGGESTED),
            statement__status=BankStatementStatus.COMMITTED,
        )
        aging = {"days_0_7": 0, "days_8_30": 0, "days_30_plus": 0}
        today = timezone.localdate()
        for line in unmatched.only("txn_date"):
            days = (today - line.txn_date).days
            if days <= 7:
                aging["days_0_7"] += 1
            elif days <= 30:
                aging["days_8_30"] += 1
            else:
                aging["days_30_plus"] += 1

        # R3-004: gateway refunds are recognised in the GL immediately and the
        # actual bank refund is queued via GatewayRefundOutbox. Surface rows that
        # are stuck so the books-vs-bank divergence is visible.
        from .models import GatewayRefundOutbox, GatewayRefundOutboxStatus

        failed_refunds = GatewayRefundOutbox.objects.filter(
            company=company, status=GatewayRefundOutboxStatus.FAILED
        ).count()
        stale_pending = GatewayRefundOutbox.objects.filter(
            company=company,
            status=GatewayRefundOutboxStatus.PENDING,
        ).filter(
            Q(created_at__lt=timezone.now() - timedelta(hours=6)) | Q(attempts__gte=5)
        ).count()
        stuck_refunds = failed_refunds + stale_pending
        if stuck_refunds:
            alerts.append(
                {
                    "code": "GATEWAY_REFUND_STUCK",
                    "severity": "critical",
                    "message": (
                        f"{stuck_refunds} gateway refund(s) are queued at the provider but not "
                        "confirmed yet — books stay posted until the gateway confirms."
                    ),
                }
            )

        partial_refunds = sum(
            1
            for raw in GatewayPayment.objects.filter(
                company=company, status=GatewayPaymentStatus.CAPTURED
            ).values_list("raw_payload", flat=True)
            if isinstance(raw, dict)
            and any(not (p or {}).get("books") for p in (raw.get("partial_refunds") or []))
        )
        if partial_refunds:
            alerts.append(
                {
                    "code": "GATEWAY_PARTIAL_REFUND_UNRECONCILED",
                    "severity": "critical",
                    "message": (
                        f"{partial_refunds} gateway payment(s) have a partial refund that is "
                        "not reflected in the books — post a manual credit note / adjustment."
                    ),
                }
            )

        holding_qs = GatewayPayment.objects.filter(
            company=company, status=GatewayPaymentStatus.CAPTURED_PENDING_BOOKS
        )
        holding_n = holding_qs.count()
        # INVOICE_CANCELLED / LINK_CANCELLED holds can never post to books — the
        # customer must be refunded, not "retried".
        terminal_n = holding_qs.filter(
            holding_reason__in=_TERMINAL_HOLDING_REASONS
        ).count()
        if holding_n:
            retry_n = holding_n - terminal_n
            bits = []
            if retry_n:
                bits.append(
                    f"{retry_n} paid at the provider but not posted to books — retry from "
                    "Payment links or wait for period reopen"
                )
            if terminal_n:
                bits.append(
                    f"{terminal_n} paid at the provider against a cancelled invoice/link — "
                    "refund the customer"
                )
            alerts.append(
                {
                    "code": "GATEWAY_CAPTURE_HOLDING",
                    "severity": "critical",
                    "message": f"{holding_n} gateway capture(s): " + "; ".join(bits) + ".",
                    "count": holding_n,
                    "refund_needed": terminal_n,
                }
            )

        suffixed_n = (
            GatewayPayment.objects.filter(company=company)
            .exclude(internal_utr="")
            .count()
        )
        if suffixed_n:
            alerts.append(
                {
                    "code": "GATEWAY_UTR_SUFFIXED",
                    "severity": "warning",
                    "message": (
                        f"{suffixed_n} gateway capture(s) used a suffixed internal UTR because "
                        "the provider payment id already existed on another receipt."
                    ),
                    "count": suffixed_n,
                }
            )

        return {
            "alerts": alerts,
            "summary": {
                "critical": sum(1 for a in alerts if a["severity"] == "critical"),
                "warning": sum(1 for a in alerts if a["severity"] == "warning"),
                "info": sum(1 for a in alerts if a["severity"] == "info"),
            },
            "unmatched_aging": aging,
        }
