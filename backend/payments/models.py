from decimal import Decimal

from django.db import models
from django.utils import timezone

from core.models import CompanyScopedModel


class PaymentMode(models.TextChoices):
    CASH = "CASH"
    UPI = "UPI"
    BANK = "BANK"
    CARD = "CARD"
    CREDIT = "CREDIT"


class PaymentSource(models.TextChoices):
    MANUAL = "MANUAL"
    GATEWAY = "GATEWAY"
    BANK_IMPORT = "BANK_IMPORT"
    PAYMENT_LINK = "PAYMENT_LINK"


class ReceiptStatus(models.TextChoices):
    """BB-000457: REFUNDED receipts must not count as advances/AR cash."""

    POSTED = "POSTED"
    REFUNDED = "REFUNDED"
    VOIDED = "VOIDED"


class SupplierPaymentStatus(models.TextChoices):
    POSTED = "POSTED"
    VOIDED = "VOIDED"


class BankAccountType(models.TextChoices):
    CURRENT = "CURRENT"
    SAVINGS = "SAVINGS"
    CASH_BOX = "CASH_BOX"


class BankAccount(CompanyScopedModel):
    """Company cash/bank instrument (Phase 3.0)."""

    name = models.CharField(max_length=100)
    account_number_masked = models.CharField(max_length=32, blank=True)
    ifsc = models.CharField(max_length=16, blank=True)
    account_type = models.CharField(
        max_length=16, choices=BankAccountType.choices, default=BankAccountType.CURRENT
    )
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    opening_as_of = models.DateField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_default", "name"]
        indexes = [models.Index(fields=["company", "is_active"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(is_default=True),
                name="one_default_bank_account_per_company",
            ),
        ]

    def __str__(self):
        return self.name


class CustomerReceipt(CompanyScopedModel):
    """Money received from a customer (§8.1)."""

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="receipts")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=8, choices=PaymentMode.choices, default=PaymentMode.CASH)
    receipt_date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    utr = models.CharField(max_length=64, blank=True, db_index=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=ReceiptStatus.choices,
        default=ReceiptStatus.POSTED,
        db_index=True,
    )
    bank_account = models.ForeignKey(
        BankAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name="receipts"
    )
    source = models.CharField(
        max_length=16, choices=PaymentSource.choices, default=PaymentSource.MANUAL
    )
    gateway_payment = models.ForeignKey(
        "payments.GatewayPayment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="receipts",
    )

    class Meta:
        ordering = ["-receipt_date", "-id"]
        indexes = [
            models.Index(fields=["company", "receipt_date"]),
            models.Index(fields=["company", "utr"]),
            models.Index(fields=["company", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "utr"],
                condition=~models.Q(utr="")
                & ~models.Q(status__in=[ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED]),
                name="uniq_receipt_utr_per_company",
            ),
        ]


class SupplierPayment(CompanyScopedModel):
    """Money paid to a supplier (§8.1)."""

    supplier = models.ForeignKey("masters.Supplier", on_delete=models.PROTECT, related_name="payments")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=8, choices=PaymentMode.choices, default=PaymentMode.CASH)
    payment_date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    utr = models.CharField(max_length=64, blank=True, db_index=True)
    notes = models.TextField(blank=True)
    bank_account = models.ForeignKey(
        BankAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name="supplier_payments"
    )
    source = models.CharField(
        max_length=16, choices=PaymentSource.choices, default=PaymentSource.MANUAL
    )
    status = models.CharField(
        max_length=16,
        choices=SupplierPaymentStatus.choices,
        default=SupplierPaymentStatus.POSTED,
        db_index=True,
    )
    tds_section = models.CharField(max_length=16, blank=True)
    tds_rate = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    tds_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["-payment_date", "-id"]
        indexes = [
            models.Index(fields=["company", "payment_date"]),
            models.Index(fields=["company", "utr"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "utr"],
                condition=~models.Q(utr="") & ~models.Q(status=SupplierPaymentStatus.VOIDED),
                name="uniq_supplier_payment_utr_per_company",
            ),
        ]


class PaymentAllocation(CompanyScopedModel):
    """Links a receipt/payment to an open invoice — partial or full (§8.1)."""

    receipt = models.ForeignKey(
        CustomerReceipt, null=True, blank=True, on_delete=models.PROTECT, related_name="allocations"
    )
    supplier_payment = models.ForeignKey(
        SupplierPayment, null=True, blank=True, on_delete=models.PROTECT, related_name="allocations"
    )
    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="allocations"
    )
    purchase_invoice = models.ForeignKey(
        "purchases.PurchaseInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="allocations"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # BB-000022: exactly one payment side and one invoice side.
            models.CheckConstraint(
                condition=(
                    models.Q(receipt__isnull=False, supplier_payment__isnull=True)
                    | models.Q(receipt__isnull=True, supplier_payment__isnull=False)
                ),
                name="alloc_xor_receipt_or_supplier_payment",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(sales_invoice__isnull=False, purchase_invoice__isnull=True)
                    | models.Q(sales_invoice__isnull=True, purchase_invoice__isnull=False)
                ),
                name="alloc_xor_sales_or_purchase_invoice",
            ),
            models.UniqueConstraint(
                fields=["receipt", "sales_invoice"],
                condition=models.Q(
                    receipt__isnull=False, sales_invoice__isnull=False, reversed_at__isnull=True
                ),
                name="uniq_alloc_receipt_sales_invoice",
            ),
            models.UniqueConstraint(
                fields=["supplier_payment", "purchase_invoice"],
                condition=models.Q(
                    supplier_payment__isnull=False,
                    purchase_invoice__isnull=False,
                    reversed_at__isnull=True,
                ),
                name="uniq_alloc_supplier_payment_purchase_invoice",
            ),
        ]

class PaymentLinkStatus(models.TextChoices):
    CREATED = "CREATED"
    SENT = "SENT"
    PARTIALLY_PAID = "PARTIALLY_PAID"  # BB-000392
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PaymentLink(CompanyScopedModel):
    """Shareable payment link for an invoice or open customer amount (Phase 3.1)."""

    token = models.CharField(max_length=64, unique=True, db_index=True)
    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="payment_links"
    )
    customer = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="payment_links"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    allow_partial = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16, choices=PaymentLinkStatus.choices, default=PaymentLinkStatus.CREATED
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    provider = models.CharField(max_length=32, blank=True, default="razorpay")
    provider_link_id = models.CharField(max_length=128, blank=True)
    provider_short_url = models.URLField(blank=True)
    paid_receipt = models.ForeignKey(
        CustomerReceipt, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "status"])]
        constraints = [
            # BB-000269: unique provider link ids when set (webhook routing).
            models.UniqueConstraint(
                fields=["provider", "provider_link_id"],
                condition=~models.Q(provider_link_id=""),
                name="uniq_payment_link_provider_link_id",
            ),
        ]


class GatewayPaymentStatus(models.TextChoices):
    CREATED = "CREATED"
    CAPTURED = "CAPTURED"
    CAPTURED_PENDING_BOOKS = "CAPTURED_PENDING_BOOKS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class GatewayPayment(CompanyScopedModel):
    """Idempotent gateway settlement record (Phase 3.1)."""

    provider = models.CharField(max_length=32)
    provider_payment_id = models.CharField(max_length=128)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    fee = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    status = models.CharField(
        max_length=32, choices=GatewayPaymentStatus.choices, default=GatewayPaymentStatus.CREATED
    )
    payment_link = models.ForeignKey(
        PaymentLink, null=True, blank=True, on_delete=models.SET_NULL, related_name="gateway_payments"
    )
    raw_payload = models.JSONField(null=True, blank=True)
    holding_reason = models.CharField(max_length=64, blank=True, default="")
    holding_error = models.TextField(blank=True, default="")
    holding_since = models.DateTimeField(null=True, blank=True)
    internal_utr = models.CharField(max_length=80, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "provider", "provider_payment_id"],
                name="uniq_gateway_payment_per_provider",
            )
        ]


class BankStatementStatus(models.TextChoices):
    PREVIEW = "PREVIEW"
    COMMITTED = "COMMITTED"
    VOID = "VOID"


class BankStatement(CompanyScopedModel):
    """Imported bank statement header (Phase 3.2)."""

    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="statements")
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    source_filename = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=16, choices=BankStatementStatus.choices, default=BankStatementStatus.PREVIEW
    )
    preset = models.CharField(max_length=32, blank=True, default="generic")

    class Meta:
        ordering = ["-created_at"]


class BankLineMatchStatus(models.TextChoices):
    UNMATCHED = "UNMATCHED"
    SUGGESTED = "SUGGESTED"
    MATCHED = "MATCHED"
    IGNORED = "IGNORED"


class BankStatementLine(CompanyScopedModel):
    """Single bank statement line (append-only; ignore via status)."""

    statement = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name="lines")
    txn_date = models.DateField()
    value_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # signed: credit +, debit -
    narration = models.CharField(max_length=512, blank=True)
    utr = models.CharField(max_length=64, blank=True, db_index=True)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    match_status = models.CharField(
        max_length=16, choices=BankLineMatchStatus.choices, default=BankLineMatchStatus.UNMATCHED
    )
    line_hash = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        ordering = ["txn_date", "id"]
        indexes = [models.Index(fields=["company", "match_status", "txn_date"])]
        constraints = [
            # bank_account is on statement; statement scopes uniqueness per account.
            models.UniqueConstraint(
                fields=["company", "statement", "line_hash"],
                condition=~models.Q(line_hash=""),
                name="uniq_bank_statement_line_hash",
            ),
        ]


class ReconMatch(CompanyScopedModel):
    """Confirmed link between a bank line and a receipt/payment (Phase 3.2)."""

    line = models.OneToOneField(BankStatementLine, on_delete=models.CASCADE, related_name="recon_match")
    receipt = models.ForeignKey(
        CustomerReceipt, null=True, blank=True, on_delete=models.PROTECT, related_name="recon_matches"
    )
    supplier_payment = models.ForeignKey(
        SupplierPayment, null=True, blank=True, on_delete=models.PROTECT, related_name="recon_matches"
    )
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    matched_at = models.DateTimeField(auto_now_add=True)
    matched_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-matched_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["receipt"],
                condition=models.Q(receipt__isnull=False),
                name="uniq_recon_match_receipt",
            ),
            models.UniqueConstraint(
                fields=["supplier_payment"],
                condition=models.Q(supplier_payment__isnull=False),
                name="uniq_recon_match_supplier_payment",
            ),
        ]


class GatewayRefundOutboxStatus(models.TextChoices):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class GatewayRefundOutbox(CompanyScopedModel):
    """Retry queue for gateway refunds after books have already been unwound."""

    gateway_payment = models.ForeignKey(
        GatewayPayment, on_delete=models.CASCADE, related_name="refund_outbox"
    )
    provider_payment_id = models.CharField(max_length=128)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=16,
        choices=GatewayRefundOutboxStatus.choices,
        default=GatewayRefundOutboxStatus.PENDING,
        db_index=True,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["company", "status", "next_attempt_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["gateway_payment"],
                name="uniq_refund_outbox_per_gateway_payment",
            )
        ]


class DunningReminder(CompanyScopedModel):
    """A-07: one automated AR reminder attempt per invoice per IST day."""

    class Channel(models.TextChoices):
        WHATSAPP = "WHATSAPP"
        SMS = "SMS"

    class Status(models.TextChoices):
        SENT = "SENT"
        SKIPPED = "SKIPPED"
        FAILED = "FAILED"

    invoice = models.ForeignKey(
        "sales.SalesInvoice", on_delete=models.CASCADE, related_name="dunning_reminders"
    )
    customer = models.ForeignKey(
        "masters.Customer", on_delete=models.CASCADE, related_name="dunning_reminders"
    )
    sent_on = models.DateField()
    days_overdue = models.PositiveIntegerField()
    channel = models.CharField(max_length=16, choices=Channel.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SENT)
    error = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-sent_on", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "sent_on"],
                name="uniq_dunning_invoice_per_day",
            )
        ]
        indexes = [models.Index(fields=["company", "sent_on"])]
