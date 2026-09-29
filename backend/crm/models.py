"""CRM MVP — leads and opportunities; not a full CRM suite."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import CompanyScopedModel


class Lead(CompanyScopedModel):
    class Status(models.TextChoices):
        NEW = "NEW"
        CONTACTED = "CONTACTED"
        QUALIFIED = "QUALIFIED"
        LOST = "LOST"

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    state = models.CharField(max_length=64, blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    source = models.CharField(max_length=16, null=True, blank=True)
    message = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        "accounts.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_leads",
    )
    dedupe_matched_customer = models.ForeignKey(
        "masters.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deduped_leads",
    )
    dedupe_matched_lead = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dedupe_matches",
    )
    dedupe_review = models.CharField(max_length=16, blank=True, default="")
    dedupe_candidates = models.JSONField(default=dict, blank=True)
    customer = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads",
    )
    campaign = models.ForeignKey(
        "Campaign", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads",
    )
    referral_code = models.ForeignKey(
        "ReferralCode", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads",
    )
    last_touched_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        from django.utils import timezone

        if self.last_touched_at is None or "last_touched_at" in (kwargs.get("update_fields") or []):
            self.last_touched_at = timezone.now()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None and "last_touched_at" not in update_fields:
                kwargs["update_fields"] = [*update_fields, "last_touched_at"]
        # R-077: same E.164 collapse as User so convert_lead phone twin-check works.
        raw = (self.phone or "").strip()
        if raw:
            from accounts.otp_utils import canonicalize_user_phone

            try:
                self.phone = canonicalize_user_phone(raw)
            except ValueError:
                import re

                digits = re.sub(r"\D", "", raw)
                if digits.startswith("0") and len(digits) == 11:
                    self.phone = canonicalize_user_phone(digits[1:])
                else:
                    from django.core.exceptions import ValidationError

                    raise ValidationError(
                        {"phone": "Enter a valid mobile number (E.164 or 10-digit Indian)."}
                    )
        else:
            self.phone = ""
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "source"], name="crm_lead_company_source_idx"),
            models.Index(fields=["company", "assigned_to"], name="crm_lead_company_assignee_idx"),
            models.Index(fields=["company", "dedupe_review"], name="crm_lead_company_review_idx"),
            models.Index(fields=["company", "campaign"], name="crm_lead_company_campaign_idx"),
            models.Index(fields=["company", "referral_code"], name="crm_lead_company_referral_idx"),
        ]


class LeadActivity(CompanyScopedModel):
    class Kind(models.TextChoices):
        NOTE = "NOTE"
        CALL = "CALL"
        EMAIL = "EMAIL"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.NOTE)
    body = models.TextField()
    due_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "lead activities"


class Opportunity(CompanyScopedModel):
    class Stage(models.TextChoices):
        OPEN = "OPEN"
        QUALIFIED = "QUALIFIED"
        NEGOTIATION = "NEGOTIATION"
        WON = "WON"
        LOST = "LOST"

    OPEN_STAGES = (Stage.OPEN, Stage.QUALIFIED, Stage.NEGOTIATION)

    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities")
    customer = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities",
    )
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.OPEN)
    probability = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    expected_close_date = models.DateField(null=True, blank=True)
    competitor = models.CharField(max_length=120, blank=True)
    # B9-039: stamped once, the first time stage moves to a terminal value.
    closed_at = models.DateTimeField(null=True, blank=True)
    stage_move_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "opportunities"


class Campaign(CompanyScopedModel):
    class Type(models.TextChoices):
        DIGITAL = "DIGITAL"
        REFERRAL = "REFERRAL"
        EVENT = "EVENT"
        MARKET_VISIT = "MARKET_VISIT"

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        ACTIVE = "ACTIVE"
        PAUSED = "PAUSED"
        COMPLETED = "COMPLETED"

    name = models.CharField(max_length=200)
    campaign_type = models.CharField(max_length=16, choices=Type.choices)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children",
    )
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    target_revenue = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    expected_outcome = models.CharField(max_length=255, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "parent"], name="crm_camp_co_parent_idx"),
            models.Index(fields=["company", "status"], name="crm_camp_co_status_idx"),
        ]

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be before the start date."})
        parent = self.parent
        seen = set()
        while parent is not None:
            if self.pk and parent.pk == self.pk:
                raise ValidationError({"parent": "A campaign cannot be its own ancestor."})
            if parent.pk in seen:
                break
            seen.add(parent.pk)
            if parent.company_id != self.company_id:
                raise ValidationError({"parent": "Parent campaign must belong to this company."})
            parent = parent.parent


class OpportunityLine(CompanyScopedModel):
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="opportunity_lines")
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))],
    )
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "opportunity"], name="crm_opline_company_opp_idx"),
        ]


class ReferralCode(CompanyScopedModel):
    class RewardType(models.TextChoices):
        FLAT = "FLAT"
        PERCENT = "PERCENT"

    referrer_customer = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="referral_codes",
    )
    referrer_user = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.PROTECT, related_name="referral_codes",
    )
    code = models.CharField(max_length=16)
    reward_type = models.CharField(max_length=16, choices=RewardType.choices, default=RewardType.FLAT)
    reward_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="crm_referral_code_company_uniq"),
            models.CheckConstraint(
                condition=(
                    models.Q(referrer_customer__isnull=False, referrer_user__isnull=True)
                    | models.Q(referrer_customer__isnull=True, referrer_user__isnull=False)
                ),
                name="crm_referral_code_exactly_one_referrer",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "referrer_customer"], name="crm_refcode_company_cust_idx"),
            models.Index(fields=["company", "referrer_user"], name="crm_refcode_company_user_idx"),
        ]


class ReferralReward(CompanyScopedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"
        # Paid drafts a credit note. Completing that note adjusts the customer
        # balance. Marking PAID does not send cash.
        PAID = "PAID"

    referral_code = models.ForeignKey(ReferralCode, on_delete=models.PROTECT, related_name="rewards")
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="referral_rewards")
    opportunity = models.ForeignKey(Opportunity, on_delete=models.PROTECT, related_name="referral_rewards")
    reward_amount = models.DecimalField(max_digits=10, decimal_places=2)
    reward_status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # Stable code, not free text. Set only by the self-referral auto-reject path.
    # Manual reject leaves this blank — the UI cannot invent a reason it was not given.
    rejection_reason = models.CharField(max_length=64, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)
    credit_note = models.ForeignKey(
        "sales.SalesCreditNote",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referral_rewards",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "opportunity"], name="crm_referral_reward_opp_uniq"),
        ]
        indexes = [
            models.Index(fields=["company", "reward_status"], name="crm_refrew_co_status_idx"),
            models.Index(fields=["company", "referral_code"], name="crm_refreward_company_code_idx"),
        ]


class LeadIngestJob(CompanyScopedModel):
    """Accepted lead capture that finishes after the HTTP response is queued."""

    class Kind(models.TextChoices):
        CSV = "csv", "CSV"
        WHATSAPP = "whatsapp", "WhatsApp"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        DONE = "DONE", "Done"
        FAILED = "FAILED", "Failed"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
