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
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    customer = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads",
    )

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

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "opportunities"
