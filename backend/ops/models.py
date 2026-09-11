from django.conf import settings
from django.db import models


class CoverageAuditRun(models.Model):
    """A single 'Coverage Copilot' run: a deterministic repo scan (see
    ops.coverage_scan) handed to an LLM to prioritize/synthesize gaps.

    Deliberately has NO `company` FK — this is a cross-tenant engineering
    tool triggered by a Django superuser via /admin/, not tenant data, so
    it's excluded from RLS enrollment (see tests/test_rls_coverage.py's
    _EXCLUDED set, same category as accounts_companygstin).
    """

    class Status(models.TextChoices):
        PENDING = "PENDING"
        RUNNING = "RUNNING"
        DONE = "DONE"
        FAILED = "FAILED"

    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    result = models.JSONField(default=list, blank=True)
    failure_reason = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"CoverageAuditRun#{self.pk} [{self.status}]"
