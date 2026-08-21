from django.db import models

from core.models import CompanyScopedModel


class IntegrationConnection(CompanyScopedModel):
    class Provider(models.TextChoices):
        TALLY = "TALLY"
        WHATSAPP = "WHATSAPP"
        BUSY = "BUSY"
        ZOHO = "ZOHO"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        DISABLED = "DISABLED"

    provider = models.CharField(max_length=32, choices=Provider.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    encrypted_secrets = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("company", "provider")]


class IntegrationSyncRun(CompanyScopedModel):
    class Kind(models.TextChoices):
        TALLY_IMPORT = "TALLY_IMPORT"
        TALLY_EXPORT = "TALLY_EXPORT"

    class Status(models.TextChoices):
        UPLOADED = "UPLOADED"
        PREVIEWED = "PREVIEWED"
        COMMITTED = "COMMITTED"
        FAILED = "FAILED"

    kind = models.CharField(max_length=32, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADED)
    file = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    preview = models.JSONField(default=dict, blank=True)
    errors = models.JSONField(default=list, blank=True)
    result = models.JSONField(default=dict, blank=True)
    counts = models.JSONField(default=dict, blank=True)
    failure_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "kind", "status"])]
