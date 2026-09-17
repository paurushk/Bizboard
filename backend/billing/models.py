from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


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
    # 8.5 — expand-only SaaS dunning cadence (not AR / payments.dunning).
    last_dunning_at = models.DateTimeField(null=True, blank=True)
    last_dunning_step = models.PositiveSmallIntegerField(default=0)

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
            anchor = self.created_at or self.updated_at or timezone.now()
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
