from django.db import models

from core.models import CompanyScopedModel


class Project(CompanyScopedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN"
        CLOSED = "CLOSED"
        CANCELLED = "CANCELLED"

    number = models.CharField(max_length=32, blank=True)
    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="projects")
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_project_number_per_company",
            ),
        ]


class ProjectMilestone(CompanyScopedModel):
    class Status(models.TextChoices):
        PLANNED = "PLANNED"
        READY = "READY"
        INVOICED = "INVOICED"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    name = models.CharField(max_length=200)
    sequence = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    service_product = models.ForeignKey(
        "masters.Product", on_delete=models.PROTECT, related_name="project_milestones",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="project_milestones",
    )

    class Meta:
        ordering = ["sequence", "id"]
