from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import CompanyScopedModel, TimeStampedModel


class Plan(TimeStampedModel):
    name = models.CharField(max_length=64)
    slug = models.SlugField(unique=True)
    seat_limit = models.PositiveIntegerField(default=1)
    monthly_complete_limit = models.PositiveIntegerField(
        default=0, help_text="0 = unlimited completed sales+purchase invoices per calendar month."
    )
    storage_bytes_limit = models.PositiveBigIntegerField(
        default=0, help_text="0 = unlimited user-uploaded bytes (attachments/imports/logos)."
    )
    api_rate_per_minute = models.PositiveIntegerField(
        default=0, help_text="0 = no extra per-tenant cap beyond global DRF throttles."
    )
    modules = models.JSONField(default=dict, blank=True)
    price_paise = models.PositiveIntegerField(default=0)
    razorpay_plan_id = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price_paise", "name"]

    def __str__(self):
        return self.name


class Subscription(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending"
        TRIAL = "trial"
        ACTIVE = "active"
        PAST_DUE = "past_due"
        SUSPENDED = "suspended"

    company = models.OneToOneField(
        "accounts.Company", on_delete=models.CASCADE, related_name="saas_subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TRIAL)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    razorpay_subscription_id = models.CharField(max_length=64, blank=True, db_index=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    # B9-005: a plan switch on an already-live paying subscription is deferred
    # to the next billing cycle (no proration) — `plan`/entitlements stay on
    # what the tenant already paid for until the new Razorpay subscription's
    # webhook confirms it actually started, at which point `pending_plan` is
    # promoted to `plan`. Null for a fresh subscription or a switch that
    # doesn't need deferring (no live prior plan to protect).
    pending_plan = models.ForeignKey(
        Plan, null=True, blank=True, on_delete=models.SET_NULL, related_name="pending_subscriptions"
    )
    # The Razorpay subscription created at checkout, before it is paid. The
    # live ``razorpay_subscription_id`` stays on the subscription the tenant
    # already paid for until this one is confirmed active.
    pending_razorpay_subscription_id = models.CharField(max_length=64, blank=True, default="")
    # WP-BL3: an upgrade applies at once while its prorated charge is paid (or within the grace).
    upgrade_plan = models.ForeignKey(
        Plan, null=True, blank=True, on_delete=models.SET_NULL, related_name="upgrading_subscriptions"
    )
    upgrade_started_at = models.DateTimeField(null=True, blank=True)
    upgrade_grace_until = models.DateTimeField(null=True, blank=True)
    proration_amount_paise = models.PositiveIntegerField(default=0)
    proration_link_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    proration_paid_at = models.DateTimeField(null=True, blank=True)
    proration_link_url = models.CharField(max_length=300, blank=True, default="")
    # The new plan's subscription had its mandate approved (``subscription.authenticated``); from then
    # on the old one is set to end at its cycle end so both never charge at the same renewal.
    pending_authenticated_at = models.DateTimeField(null=True, blank=True)
    # WP-BL4: how renewals are collected and the state of the UPI Autopay / card mandate.
    payment_method = models.CharField(max_length=16, blank=True, default="")
    mandate_status = models.CharField(max_length=16, blank=True, default="")
    renewal_reminder_for = models.DateTimeField(null=True, blank=True)
    # 8.5 — expand-only SaaS dunning cadence (not AR / payments.dunning).
    last_dunning_at = models.DateTimeField(null=True, blank=True)
    last_dunning_step = models.PositiveSmallIntegerField(default=0)
    churn_reason = models.CharField(max_length=255, blank=True, default="")
    suspended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "trial_ends_at"])]

    def __str__(self):
        return f"{self.company_id}:{self.status}"

    def is_write_blocked(self) -> bool:
        if self.status == self.Status.SUSPENDED:
            # B9-007: a cancelled/suspended subscription keeps write access
            # until the paid period it was already charged for actually ends.
            if self.current_period_end and timezone.now() < self.current_period_end:
                return False
            return True
        if self.status == self.Status.PENDING:
            # B9-017: a brand-new PENDING subscription (checkout started, first
            # webhook not yet in) must not permanently write-block the tenant —
            # give it the same grace window ACTIVE gets before its first
            # confirmed period end.
            if self.current_period_end and timezone.now() < self.current_period_end:
                return False
            # Grace starts when the row last changed into this checkout state.
            # created_at is the original subscription and would block writes
            # the moment an older tenant opens checkout.
            anchor = self.updated_at or timezone.now()
            return timezone.now() >= anchor + timedelta(days=3)
        if self.status == self.Status.TRIAL:
            if self.trial_ends_at and self.trial_ends_at < timezone.now():
                return True
            return False
        if self.status == self.Status.ACTIVE:
            if self.current_period_end and self.current_period_end < timezone.now():
                return True
            if self.current_period_end is None:
                anchor = self.updated_at or timezone.now()
                return timezone.now() >= anchor + timedelta(days=30)
            return False
        if self.status == self.Status.PAST_DUE:
            # BB-000726: block PAST_DUE after optional grace from period end.
            grace_days = int(getattr(settings, "BILLING_PAST_DUE_GRACE_DAYS", 0) or 0)
            if grace_days <= 0:
                return True
            anchor = self.current_period_end or self.updated_at
            if anchor is None:
                return True
            return timezone.now() >= anchor + timedelta(days=grace_days)
        return False


class DeadLetterEvent(TimeStampedModel):
    """Parked inbound events that failed after signature verification (9.5)."""

    class Status(models.TextChoices):
        PENDING = "pending"
        REPLAYED = "replayed"
        DISCARDED = "discarded"

    company = models.ForeignKey(
        "accounts.Company",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="billing_dead_letters",
    )
    provider = models.CharField(max_length=64, db_index=True)
    event_id = models.CharField(max_length=128, db_index=True)
    payload = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    replayed_at = models.DateTimeField(null=True, blank=True)
    replayed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="replayed_dead_letters"
    )

    class Meta:
        indexes = [models.Index(fields=["provider", "status", "created_at"], name="billing_dlq_prov_st_ca_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "event_id"],
                condition=models.Q(status="pending"),
                name="billing_dlq_uniq_pending_provider_event",
            )
        ]

    def __str__(self):
        return f"{self.provider}:{self.event_id}:{self.status}"


class TenantActivation(CompanyScopedModel):
    """Setup-done and first-invoice markers for one merchant company."""

    setup_completed_at = models.DateTimeField(null=True, blank=True)
    first_invoice_at = models.DateTimeField(null=True, blank=True)
    # WP-GR2: onboarding checklist steps (billing/onboarding.py stamps each once).
    gstin_verified_at = models.DateTimeField(null=True, blank=True)
    first_item_at = models.DateTimeField(null=True, blank=True)
    first_party_at = models.DateTimeField(null=True, blank=True)
    first_purchase_at = models.DateTimeField(null=True, blank=True)
    first_payment_at = models.DateTimeField(null=True, blank=True)
    invited_user_at = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField(null=True, blank=True)
    checklist_dismissed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company"], name="uniq_tenant_activation_company"),
        ]


class VendorTenantSnapshot(CompanyScopedModel):
    """Redacted tenant health stored in the vendor company. source id is not a FK."""

    source_company_id = models.PositiveBigIntegerField()
    source_company_name = models.CharField(max_length=255)
    setup_completed_at = models.DateTimeField(null=True, blank=True)
    first_invoice_at = models.DateTimeField(null=True, blank=True)
    last_invoice_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    seats_used = models.PositiveIntegerField(default=0)
    seats_limit = models.PositiveIntegerField(default=0)
    documents_used = models.PositiveIntegerField(default=0)
    documents_limit = models.PositiveIntegerField(default=0)
    churn_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "source_company_id"],
                name="uniq_vendor_snapshot_source",
            ),
        ]


class PlatformGstInvoice(CompanyScopedModel):
    """Bizboard's GST invoice (or credit note) to a tenant for a captured subscription charge.

    WP-BL2: every Razorpay ``subscription.charged`` issues one (``capture_id`` = Razorpay payment
    id); the daily recon issues any a lost webhook missed. A refund issues a ``CREDIT_NOTE`` row
    pointing at the invoice (``capture_id`` = refund id). Numbers are Bizboard-wide and run per
    financial year with no gaps (``PlatformInvoiceSequence``).
    """

    class Kind(models.TextChoices):
        INVOICE = "INVOICE", "Tax invoice"
        CREDIT_NOTE = "CREDIT_NOTE", "Credit note"

    provider = models.CharField(max_length=32)
    capture_id = models.CharField(max_length=128)
    number = models.CharField(max_length=32, blank=True)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.INVOICE)
    original = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="credit_notes",
    )
    financial_year = models.CharField(max_length=7, blank=True)
    buyer_gstin = models.CharField(max_length=15, blank=True)
    buyer_legal_name = models.CharField(max_length=255, blank=True)
    buyer_state = models.CharField(max_length=64, blank=True)
    sac_code = models.CharField(max_length=8, blank=True)
    # B-07: filled only once Bizboard's own turnover makes e-invoicing mandatory.
    irn = models.CharField(max_length=64, blank=True)
    ack_no = models.CharField(max_length=32, blank=True)
    ack_date = models.DateTimeField(null=True, blank=True)
    signed_qr = models.TextField(blank=True)
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2)
    cgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    place_of_supply = models.CharField(max_length=64, blank=True)
    platform_gstin = models.CharField(max_length=15, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "provider", "capture_id"],
                name="uniq_platform_gst_capture",
            ),
        ]


class PlatformInvoiceSequence(models.Model):
    """WP-BL2: Bizboard-wide, gap-free numbers for its own GST invoices and credit notes.

    Platform table (not per tenant, no RLS): Bizboard is one supplier, so one series per document
    kind per financial year. ``series`` is e.g. ``INV:2026-27``; rows are locked while a number is
    taken, so two captures at once never share or skip a number.
    """

    series = models.CharField(max_length=16, unique=True)
    last = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.series}: {self.last}"


class SaasTdsClaim(CompanyScopedModel):
    """WP-BL1: a customer that deducts TDS on Bizboard's fees claims it back.

    The customer pays Bizboard's invoices in full online (TDS can't be withheld from a card or UPI
    charge). After the quarter they upload Form 16A for those invoices; staff check it against
    TRACES in Django admin; a verified claim is refunded against the original Razorpay payment and
    a GST credit note is not needed (TDS is not a price reduction), so the refund carries no tax.
    The amount is computed from the invoices' taxable value (TDS is on the amount before GST).
    """

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        VERIFIED = "VERIFIED", "Verified, credit waiting for the next renewal"
        SETTLED = "SETTLED", "Settled"
        REJECTED = "REJECTED", "Rejected"

    class SettleBy(models.TextChoices):
        # Q5 (founder, 2026-10-22): credit on the next renewal by default, refund on request.
        CREDIT = "CREDIT", "Credit on the next renewal"
        REFUND = "REFUND", "Refund to the original payment"

    invoices = models.ManyToManyField(PlatformGstInvoice, related_name="tds_claims")
    settle_by = models.CharField(max_length=8, choices=SettleBy.choices, default=SettleBy.CREDIT)
    credit_remaining = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # [{"invoice": <renewal invoice pk>, "refund": <razorpay refund id>, "amount": "12.00"}]
    credit_applied = models.JSONField(default=list, blank=True)
    section = models.CharField(max_length=16)
    rate = models.DecimalField(max_digits=5, decimal_places=2)
    taxable_total = models.DecimalField(max_digits=14, decimal_places=2)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    quarter = models.CharField(max_length=10)
    # SET_NULL, not PROTECT: erasing or restoring a company deletes its files, and the claim (the
    # statutory record) must not block that.
    certificate = models.ForeignKey("core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)
    refund_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]


class TrialFingerprint(models.Model):
    """WP-AB3: one free trial per business. Platform table (not per tenant, no RLS).

    Holds only keyed HMAC hashes of the GSTIN, PAN, owner phone and owner email of a company that
    started a trial, so a new sign-up by the same business starts without a trial. No clear
    personal data, so it survives tenant erasure (for counsel to confirm, DATA_CATEGORIES.md).
    """

    kind = models.CharField(max_length=8)  # gstin | pan | phone | email
    digest = models.CharField(max_length=64, db_index=True)
    company_id_hint = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["kind", "digest"])]
