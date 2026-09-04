from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Plan(TimeStampedModel):
    name = models.CharField(max_length=64)
    slug = models.SlugField(unique=True)
    seat_limit = models.PositiveIntegerField(default=1)
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
