from django.conf import settings
from django.db import models

from core.models import CompanyScopedModel


class Ticket(CompanyScopedModel):
    class Priority(models.TextChoices):
        LOW = "LOW"
        MEDIUM = "MEDIUM"
        HIGH = "HIGH"
        URGENT = "URGENT"

    class Status(models.TextChoices):
        OPEN = "OPEN"
        IN_PROGRESS = "IN_PROGRESS"
        WAITING = "WAITING"
        RESOLVED = "RESOLVED"
        CLOSED = "CLOSED"

    class Category(models.TextChoices):
        GENERAL = "GENERAL"
        NUMBER_MISMATCH = "NUMBER_MISMATCH"

    number = models.CharField(max_length=32, blank=True)
    category = models.CharField(
        max_length=32, choices=Category.choices, default=Category.GENERAL, db_index=True,
    )
    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="tickets")
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    assigned_to = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets",
    )
    sla_due_at = models.DateTimeField(null=True, blank=True)
    waiting_since = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    source_invoice = models.ForeignKey(
        "sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="support_tickets",
    )
    contract = models.ForeignKey(
        "contracts.Contract", null=True, blank=True, on_delete=models.SET_NULL, related_name="support_tickets",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_ticket_number_per_company",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "status"], name="ticket_company_status_idx"),
            models.Index(fields=["company", "assigned_to"], name="ticket_company_assignee_idx"),
            models.Index(fields=["company", "customer"], name="ticket_company_customer_idx"),
            models.Index(fields=["company", "sla_due_at"], name="ticket_company_sla_idx"),
        ]


class TicketComment(CompanyScopedModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="comments")
    body = models.TextField()
    is_internal = models.BooleanField(default=True)
    # A reply written by the vendor company on a shared ticket (SHR-03).
    from_vendor = models.BooleanField(default=False)
    author_label = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["created_at"]


class VendorTicketShare(CompanyScopedModel):
    """Redacted copy of one ticket, stored in the vendor company.

    ``company`` is the vendor company so a normal company filter can read it.
    ``source_ticket_id`` is not a foreign key.
    """

    vendor_company = models.ForeignKey(
        "accounts.Company", on_delete=models.PROTECT, related_name="vendor_ticket_shares",
    )
    source_company = models.ForeignKey(
        "accounts.Company", on_delete=models.PROTECT, related_name="shared_out_tickets",
    )
    source_ticket_id = models.PositiveBigIntegerField()
    source_number = models.CharField(max_length=32, blank=True)
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=16)
    description = models.TextField(blank=True)
    shared_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    include_description = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["vendor_company", "source_company", "source_ticket_id"],
                name="uniq_vendor_ticket_share",
            ),
        ]


class TicketAttachment(CompanyScopedModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="attachments")
    file = models.ForeignKey("core.FileAsset", on_delete=models.PROTECT, related_name="+")


class VendorTicketShareComment(CompanyScopedModel):
    """A vendor reply on a shared ticket. ``company`` is the vendor, so the vendor reads its own
    replies; the same text is written to the source ticket as a TicketComment in one bypass block."""

    share = models.ForeignKey(VendorTicketShare, on_delete=models.CASCADE, related_name="comments")
    body = models.TextField()

    class Meta:
        ordering = ["created_at"]



class PlatformTicket(CompanyScopedModel):
    """WP-PO3: a tenant asks Bizboard for help (support/platform_tickets.py).

    Not the merchant-to-buyer helpdesk (``Ticket``): no customer, no plan flag, open to every member.
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        WAITING_CUSTOMER = "WAITING_CUSTOMER", "Waiting for you"
        RESOLVED = "RESOLVED", "Resolved"

    class Severity(models.TextChoices):
        P0 = "P0", "P0 — business stopped"
        P1 = "P1", "P1 — money or stock wrong"
        P2 = "P2", "P2 — something broken"
        P3 = "P3", "P3 — question"

    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    subject = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=2, choices=Severity.choices, default=Severity.P2, db_index=True)
    tag = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    support_id = models.CharField(max_length=64, blank=True)
    route = models.CharField(max_length=200, blank=True)
    app_version = models.CharField(max_length=32, blank=True)
    error_codes = models.JSONField(default=list, blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} {self.subject}"


class PlatformTicketMessage(CompanyScopedModel):
    ticket = models.ForeignKey(PlatformTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    from_staff = models.BooleanField(default=False)
    body = models.TextField()


class TenantHealthSnapshot(CompanyScopedModel):
    """WP-PO2: one company's weekly health score (support/health.py). Staff-only, in Django admin."""

    week = models.DateField(db_index=True)
    score = models.PositiveSmallIntegerField()
    band = models.CharField(max_length=10)
    inputs = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "week"], name="uniq_health_company_week")]
        ordering = ["score"]


class DataPrivacyRequest(models.Model):
    """WP-CP2: one privacy request and what was done (docs/ops/DPDP_REQUESTS.md).

    Platform table (no RLS): a request can come from someone who is not a user of any company.
    """

    class Kind(models.TextChoices):
        ACCESS = "ACCESS", "Access / copy"
        CORRECTION = "CORRECTION", "Correction"
        ERASURE = "ERASURE", "Erasure"
        GRIEVANCE = "GRIEVANCE", "Grievance"
        CONSENT_WITHDRAWAL = "CONSENT_WITHDRAWAL", "Consent withdrawal"

    class Source(models.TextChoices):
        SELF_SERVE = "SELF_SERVE", "Self-serve in the app"
        STAFF = "STAFF", "Logged by staff"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.STAFF)
    requester = models.CharField(max_length=254)
    company_id_hint = models.PositiveBigIntegerField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    outcome = models.TextField(blank=True)
    identity_check = models.CharField(max_length=255, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        ordering = ["due_at"]


class SupportAccessGrant(CompanyScopedModel):
    """WP-ID4 (Q4, founder 2026-10-22): the owner lets Bizboard support look at the company's data,
    read-only, for at most 72 hours, tied to one platform ticket. Revocable at any time; every look
    is recorded in ``SupportAccessLog`` and shown to the owner."""

    class Scope(models.TextChoices):
        READ_ONLY = "READ_ONLY", "Read only"

    # CASCADE: a grant only exists for its ticket (PROTECT blocked deleting the company).
    ticket = models.ForeignKey(PlatformTicket, on_delete=models.CASCADE, related_name="access_grants")
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    # Blank = any Bizboard support staff member; otherwise only this staff user. PROTECT: with
    # SET_NULL, deleting the named staff account would widen the owner's consent to every staff member.
    staff_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    scope = models.CharField(max_length=16, choices=Scope.choices, default=Scope.READ_ONLY)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    revoke_reason = models.CharField(max_length=32, blank=True)  # owner | expired | ticket_closed

    class Meta:
        ordering = ["-created_at"]


class SupportAccessLog(CompanyScopedModel):
    """WP-ID4: one page support looked at under a grant (what, who, when)."""

    grant = models.ForeignKey(SupportAccessGrant, on_delete=models.CASCADE, related_name="views")
    staff_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    section = models.CharField(max_length=40)
    query = models.CharField(max_length=200, blank=True)
    rows_shown = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
