from django.db import transaction

from core.exceptions import BusinessRuleError
from core.services.sequences import next_number
from masters.models import Product
from sales.models import SalesInvoice
from sales.services import SalesService

from .models import JobCard, JobCardLine


def _check_line(company, kind, product, serial):
    if product is None or product.company_id != company.id:
        raise BusinessRuleError("Product is not in this company.")
    if kind == JobCardLine.Kind.PART:
        if product.product_type != Product.ProductType.GOODS:
            raise BusinessRuleError("A part line must be a stock item.")
        if serial is not None and (serial.company_id != company.id or serial.product_id != product.id):
            raise BusinessRuleError("Serial does not match this part.")
    elif kind == JobCardLine.Kind.LABOUR:
        if product.product_type != Product.ProductType.SERVICE:
            raise BusinessRuleError("A labour line must be a service item.")
        if serial is not None:
            raise BusinessRuleError("A labour line cannot carry a serial.")
    else:
        raise BusinessRuleError("Unknown job line kind.")


@transaction.atomic
def create_job(company, user, *, customer, complaint="", technician=None, lines=None):
    if customer is None or customer.company_id != company.id:
        raise BusinessRuleError("Customer is not in this company.")
    job = JobCard.objects.create(
        company=company,
        customer=customer,
        technician=technician,
        complaint=complaint or "",
        number=next_number(company, "JOB", prefix="JOB"),
        created_by=user,
        updated_by=user,
    )
    for line in lines or []:
        add_line(job, user, **line)
    return job


@transaction.atomic
def add_line(job, user, *, kind, product, quantity, unit_price, serial=None):
    if job.status not in (JobCard.Status.DRAFT, JobCard.Status.IN_PROGRESS):
        raise BusinessRuleError("Lines can be added only while the job is open.")
    _check_line(job.company, kind, product, serial)
    return JobCardLine.objects.create(
        company=job.company,
        job=job,
        kind=kind,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
        serial=serial,
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def start_job(job, user):
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    if job.status != JobCard.Status.DRAFT:
        raise BusinessRuleError("Only a draft job can be started.")
    job.status = JobCard.Status.IN_PROGRESS
    job.updated_by = user
    job.save(update_fields=["status", "updated_by", "updated_at"])
    return job


@transaction.atomic
def cancel_job(job, user):
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    if job.sales_invoice_id is not None:
        raise BusinessRuleError("Cancel the invoice. An invoiced job stays invoiced.")
    if job.status == JobCard.Status.CANCELLED:
        return job
    job.status = JobCard.Status.CANCELLED
    job.updated_by = user
    job.save(update_fields=["status", "updated_by", "updated_at"])
    return job


def sync_job_card(invoice, *, completed: bool):
    """Keep the job card in step with the sales invoice it was converted to."""
    from django.utils import timezone

    if completed:
        return
    JobCard.objects.filter(sales_invoice_id=invoice.pk).update(
        sales_invoice=None,
        status=JobCard.Status.IN_PROGRESS,
        updated_at=timezone.now(),
    )


@transaction.atomic
def convert_to_invoice(job, user):
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    if job.sales_invoice_id is not None:
        return job.sales_invoice
    if job.status not in (JobCard.Status.DRAFT, JobCard.Status.IN_PROGRESS):
        raise BusinessRuleError("This job cannot be invoiced.")
    lines = list(job.lines.select_related("product"))
    if not lines:
        raise BusinessRuleError("Add at least one line before invoicing.")
    draft = SalesInvoice.objects.create(
        company=job.company,
        customer=job.customer,
        invoice_type=SalesInvoice.InvoiceType.GST,
        created_by=user,
        updated_by=user,
    )
    SalesService.set_items(
        draft,
        [
            {
                "product": line.product,
                "description": line.product.name,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "gst_rate": line.product.gst_rate,
            }
            for line in lines
        ],
        user,
    )
    job.sales_invoice = draft
    job.status = JobCard.Status.INVOICED
    job.updated_by = user
    job.save(update_fields=["sales_invoice", "status", "updated_by", "updated_at"])
    return draft
