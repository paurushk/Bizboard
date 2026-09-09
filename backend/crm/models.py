"""CRM MVP — leads and opportunities; not a full CRM suite."""

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
    customer = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads",
    )

    def save(self, *args, **kwargs):
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


class LeadActivity(CompanyScopedModel):
    class Kind(models.TextChoices):
        NOTE = "NOTE"
        CALL = "CALL"
        EMAIL = "EMAIL"

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.NOTE)
    body = models.TextField()

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "lead activities"


class Opportunity(CompanyScopedModel):
    class Stage(models.TextChoices):
        OPEN = "OPEN"
        WON = "WON"
        LOST = "LOST"

    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities")
    customer = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="opportunities",
    )
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.OPEN)
    # B9-039: stamped once, the first time stage moves to a terminal value.
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "opportunities"
