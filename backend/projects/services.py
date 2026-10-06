from decimal import Decimal

from django.db import transaction

from core.exceptions import BusinessRuleError
from core.services.sequences import next_number
from masters.models import Product
from sales.models import SalesInvoice
from sales.services import SalesService

from .models import Project, ProjectMilestone


@transaction.atomic
def create_project(company, user, *, customer, name):
    if customer is None or customer.company_id != company.id:
        raise BusinessRuleError("Customer is not in this company.")
    return Project.objects.create(
        company=company,
        customer=customer,
        name=name,
        number=next_number(company, "PROJECT", prefix="PRJ"),
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def add_milestone(project, user, *, name, amount, service_product, sequence=1, target_completion_date=None):
    if project.status != Project.Status.OPEN:
        raise BusinessRuleError("Milestones can be added only on an open project.")
    if service_product is None or service_product.company_id != project.company_id:
        raise BusinessRuleError("Service product is not in this company.")
    if service_product.product_type != Product.ProductType.SERVICE:
        raise BusinessRuleError("A milestone bills a service product, not stock.")
    if Decimal(str(amount)) <= 0:
        raise BusinessRuleError("Milestone amount must be positive.")
    return ProjectMilestone.objects.create(
        company=project.company,
        project=project,
        name=name,
        sequence=sequence,
        amount=amount,
        target_completion_date=target_completion_date,
        service_product=service_product,
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def update_milestone(
    milestone, user, *, name=None, amount=None, target_completion_date=None, sequence=None, set_target=False,
):
    milestone = ProjectMilestone.objects.select_for_update().get(pk=milestone.pk)
    if milestone.status != ProjectMilestone.Status.PLANNED or milestone.sales_invoice_id:
        raise BusinessRuleError("Only a planned milestone can be edited.")
    if name is not None:
        milestone.name = name
    if amount is not None:
        if Decimal(str(amount)) <= 0:
            raise BusinessRuleError("Milestone amount must be positive.")
        milestone.amount = amount
    if sequence is not None:
        milestone.sequence = sequence
    if set_target:
        milestone.target_completion_date = target_completion_date
    milestone.updated_by = user
    milestone.save()
    return milestone


@transaction.atomic
def delete_milestone(milestone, user):
    milestone = ProjectMilestone.objects.select_for_update().get(pk=milestone.pk)
    if milestone.status != ProjectMilestone.Status.PLANNED or milestone.sales_invoice_id:
        raise BusinessRuleError("Only a planned milestone can be deleted.")
    milestone.delete()


@transaction.atomic
def mark_ready(milestone, user):
    milestone = ProjectMilestone.objects.select_for_update().select_related("project").get(pk=milestone.pk)
    if milestone.project.status == Project.Status.CLOSED:
        raise BusinessRuleError("This project is closed.")
    if milestone.status != ProjectMilestone.Status.PLANNED:
        raise BusinessRuleError("Only a planned milestone can be marked ready.")
    milestone.status = ProjectMilestone.Status.READY
    milestone.updated_by = user
    milestone.save(update_fields=["status", "updated_by", "updated_at"])
    return milestone


def sync_project_milestone(invoice, *, completed: bool):
    """Keep the milestone in step with the sales invoice it points at."""
    from django.utils import timezone

    qs = ProjectMilestone.objects.filter(sales_invoice_id=invoice.pk)
    if completed:
        qs.update(status=ProjectMilestone.Status.INVOICED, updated_at=timezone.now())
        return
    qs.update(
        sales_invoice=None,
        status=ProjectMilestone.Status.READY,
        updated_at=timezone.now(),
    )


@transaction.atomic
def invoice_milestone(milestone, user):
    milestone = ProjectMilestone.objects.select_for_update().select_related("project", "service_product").get(
        pk=milestone.pk
    )
    if milestone.project.status == Project.Status.CLOSED:
        raise BusinessRuleError("This project is closed.")
    if milestone.sales_invoice_id is not None:
        invoice = SalesInvoice.objects.select_for_update().get(pk=milestone.sales_invoice_id)
        if invoice.status == SalesInvoice.Status.CANCELLED:
            milestone.sales_invoice = None
            milestone.status = ProjectMilestone.Status.READY
            milestone.updated_by = user
            milestone.save(update_fields=["sales_invoice", "status", "updated_by", "updated_at"])
        elif invoice.status == SalesInvoice.Status.COMPLETED:
            if milestone.status != ProjectMilestone.Status.INVOICED:
                milestone.status = ProjectMilestone.Status.INVOICED
                milestone.updated_by = user
                milestone.save(update_fields=["status", "updated_by", "updated_at"])
            return invoice
        else:
            return invoice
    if milestone.status != ProjectMilestone.Status.READY:
        raise BusinessRuleError("Mark the milestone ready before invoicing.")
    product = milestone.service_product
    draft = SalesInvoice.objects.create(
        company=milestone.company,
        customer=milestone.project.customer,
        created_by=user,
        updated_by=user,
    )
    SalesService.set_items(
        draft,
        [{
            "product": product,
            "description": milestone.name,
            "quantity": Decimal("1"),
            "unit_price": milestone.amount,
            "gst_rate": product.gst_rate,
        }],
        user,
    )
    milestone.sales_invoice = draft
    milestone.updated_by = user
    milestone.save(update_fields=["sales_invoice", "updated_by", "updated_at"])
    return draft


@transaction.atomic
def close_project(project, user):
    project = Project.objects.select_for_update().get(pk=project.pk)
    incomplete = project.milestones.filter(sales_invoice__isnull=False).exclude(
        sales_invoice__status=SalesInvoice.Status.COMPLETED,
    )
    unbilled = project.milestones.exclude(
        status=ProjectMilestone.Status.INVOICED,
    ).filter(sales_invoice__isnull=True)
    if incomplete.exists() or unbilled.exists():
        raise BusinessRuleError("Complete milestone invoices before closing the project.")
    project.milestones.filter(sales_invoice__status=SalesInvoice.Status.COMPLETED).update(
        status=ProjectMilestone.Status.INVOICED,
    )
    project.status = Project.Status.CLOSED
    project.updated_by = user
    project.save(update_fields=["status", "updated_by", "updated_at"])
    return project
