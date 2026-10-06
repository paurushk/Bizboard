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
