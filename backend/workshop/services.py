from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.sequences import next_number
from inventory.item_stock import tracks_inventory
from inventory.services import InventoryService
from masters.models import Product
from sales.models import SalesInvoice
from sales.services import SalesService

from .models import JobCard, JobCardLine


def _positive_money(quantity, unit_price):
    try:
        qty = Decimal(str(quantity))
        price = Decimal(str(unit_price))
    except (InvalidOperation, TypeError, ValueError):
        raise BusinessRuleError("Quantity and price must be numbers.") from None
    if qty <= 0:
        raise BusinessRuleError("Quantity must be greater than zero.")
    if price < 0:
        # A zero price is legitimate: warranty parts and goodwill labour are not billed.
        raise BusinessRuleError("Price cannot be negative.")
    return qty, price


def labour_commission_amount(line) -> Decimal:
    """Commission on a labour line. This does not post a journal."""
    if line.kind != JobCardLine.Kind.LABOUR:
        return Decimal("0.00")
    percent = Decimal(str(line.technician_commission_percent or 0))
    if percent <= 0:
        return Decimal("0.00")
    base = Decimal(str(line.unit_price or 0)) * Decimal(str(line.quantity or 0))
    return (base * percent / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def assert_bay_free(company, bay, start, end, *, ignore_job_id=None):
    if bay is None:
        return
    if start is None or end is None:
        raise BusinessRuleError("A bay booking needs a start and an end.")
    if end <= start:
        raise BusinessRuleError("The bay booking must end after it starts.")
    clash = JobCard.objects.filter(
        company=company,
        service_bay=bay,
        scheduled_start__lt=end,
        scheduled_end__gt=start,
    ).exclude(status=JobCard.Status.CANCELLED)
    if ignore_job_id:
        clash = clash.exclude(pk=ignore_job_id)
    if clash.exists():
        raise BusinessRuleError("This bay is already booked for that time.")


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
def create_job(
    company, user, *, customer, complaint="", technician=None, lines=None,
    registration_no="", vehicle_model="", odometer_reading=None,
    service_bay=None, scheduled_start=None, scheduled_end=None,
):
    if customer is None or customer.company_id != company.id:
        raise BusinessRuleError("Customer is not in this company.")
    if service_bay is not None and service_bay.company_id != company.id:
        raise BusinessRuleError("Service bay is not in this company.")
    if odometer_reading is not None and Decimal(str(odometer_reading)) < 0:
        raise BusinessRuleError("Odometer reading cannot be negative.")
    assert_bay_free(company, service_bay, scheduled_start, scheduled_end)
    job = JobCard.objects.create(
        company=company,
        customer=customer,
        technician=technician,
        complaint=complaint or "",
        registration_no=registration_no or "",
        vehicle_model=vehicle_model or "",
        odometer_reading=odometer_reading,
        service_bay=service_bay,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        number=next_number(company, "JOB", prefix="JOB"),
        created_by=user,
        updated_by=user,
    )
    for line in lines or []:
        add_line(job, user, **line)
    return job


@transaction.atomic
def add_line(
    job, user, *, kind, product, quantity, unit_price, serial=None, batch=None, batch_no="",
    labour_minutes=0, technician_commission_percent=0,
):
    if job.status not in (JobCard.Status.DRAFT, JobCard.Status.IN_PROGRESS):
        raise BusinessRuleError("Lines can be added only while the job is open.")
    quantity, unit_price = _positive_money(quantity, unit_price)
    try:
        minutes = int(labour_minutes or 0)
        percent = Decimal(str(technician_commission_percent or 0))
    except (InvalidOperation, TypeError, ValueError):
        raise BusinessRuleError("Labour time and commission must be numbers.") from None
    if minutes < 0 or percent < 0:
        raise BusinessRuleError("Labour time and commission cannot be negative.")
    _check_line(job.company, kind, product, serial)
    if batch is not None and (batch.company_id != job.company_id or batch.product_id != product.id):
        raise BusinessRuleError("Batch does not match this part.")
    line = JobCardLine.objects.create(
        company=job.company,
        job=job,
        kind=kind,
        product=product,
        quantity=quantity,
        unit_price=unit_price,
        labour_minutes=minutes,
        technician_commission_percent=percent,
        serial=serial,
        batch=batch,
        batch_no=batch_no or getattr(batch, "batch_no", "") or "",
        created_by=user,
        updated_by=user,
    )
    if kind == JobCardLine.Kind.PART and tracks_inventory(product):
        warehouse = InventoryService.default_warehouse(job.company)
        InventoryService.reserve_stock(
            job.company, warehouse, product, quantity, user=user, batch=batch,
        )
    return line


def _release_job_reservations(job, user):
    warehouse = InventoryService.default_warehouse(job.company)
    for line in job.lines.select_related("product", "batch"):
        if line.kind != JobCardLine.Kind.PART or not tracks_inventory(line.product):
            continue
        InventoryService.release_reservation(
            job.company, warehouse, line.product, line.quantity, user=user, batch=line.batch,
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
def schedule_job(job, user, *, service_bay, scheduled_start, scheduled_end):
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    if job.status in (JobCard.Status.INVOICED, JobCard.Status.CANCELLED):
        raise BusinessRuleError("A closed job cannot be scheduled.")
    if service_bay is None or service_bay.company_id != job.company_id:
        raise BusinessRuleError("Service bay is not in this company.")
    assert_bay_free(job.company, service_bay, scheduled_start, scheduled_end, ignore_job_id=job.pk)
    job.service_bay = service_bay
    job.scheduled_start = scheduled_start
    job.scheduled_end = scheduled_end
    job.updated_by = user
    job.save(update_fields=[
        "service_bay", "scheduled_start", "scheduled_end", "updated_by", "updated_at",
    ])
    return job


@transaction.atomic
def cancel_job(job, user):
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    if job.sales_invoice_id is not None:
        raise BusinessRuleError("Cancel the invoice. An invoiced job stays invoiced.")
    if job.status == JobCard.Status.CANCELLED:
        return job
    _release_job_reservations(job, user)
    job.status = JobCard.Status.CANCELLED
    job.updated_by = user
    job.save(update_fields=["status", "updated_by", "updated_at"])
    return job


def release_reservations_for_invoice(invoice, user=None):
    """Drop the part holds of any open job card billed by this invoice (called by complete)."""
    for job in JobCard.objects.filter(sales_invoice_id=invoice.pk).exclude(
        status__in=(JobCard.Status.CANCELLED, JobCard.Status.INVOICED),
    ):
        _release_job_reservations(job, user)


def sync_job_card(invoice, *, completed: bool):
    """Keep the job card in step with the sales invoice it was converted to.

    INVOICED is written only when the invoice completes. A draft link leaves
    the job IN_PROGRESS so a second convert can find the same invoice.
    """
    from django.utils import timezone

    if completed:
        jobs = list(
            JobCard.objects.filter(sales_invoice_id=invoice.pk).exclude(
                status__in=(JobCard.Status.CANCELLED, JobCard.Status.INVOICED),
            )
        )
        JobCard.objects.filter(pk__in=[job.pk for job in jobs]).update(
            status=JobCard.Status.INVOICED, updated_at=timezone.now(),
        )
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
        invoice = job.sales_invoice
        if invoice.status in (
            SalesInvoice.Status.DRAFT,
            SalesInvoice.Status.COMPLETED,
            SalesInvoice.Status.RETURNED,
        ):
            if invoice.status == SalesInvoice.Status.DRAFT and job.status == JobCard.Status.DRAFT:
                job.status = JobCard.Status.IN_PROGRESS
                job.updated_by = user
                job.save(update_fields=["status", "updated_by", "updated_at"])
            elif (
                invoice.status in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)
                and job.status not in (JobCard.Status.INVOICED, JobCard.Status.CANCELLED)
            ):
                job.status = JobCard.Status.INVOICED
                job.updated_by = user
                job.save(update_fields=["status", "updated_by", "updated_at"])
            return invoice
        if invoice.status == SalesInvoice.Status.CANCELLED:
            job.sales_invoice = None
            if job.status == JobCard.Status.INVOICED:
                job.status = JobCard.Status.IN_PROGRESS
            job.updated_by = user
            job.save(update_fields=["sales_invoice", "status", "updated_by", "updated_at"])
        else:
            return invoice
    if job.status not in (JobCard.Status.DRAFT, JobCard.Status.IN_PROGRESS):
        raise BusinessRuleError("This job cannot be invoiced.")
    lines = list(job.lines.select_related("product", "serial", "batch"))
    if not lines:
        raise BusinessRuleError("Add at least one line before invoicing.")
    items = []
    for line in lines:
        payload = {
            "product": line.product,
            "description": line.product.name,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "gst_rate": line.product.gst_rate,
        }
        if line.kind == JobCardLine.Kind.PART and line.product.track_serial:
            if line.serial_id is None or Decimal(str(line.quantity)) != Decimal("1"):
                raise BusinessRuleError(
                    "A serial-tracked part needs exactly one serial before invoicing."
                )
            payload["quantity"] = Decimal("1")
            payload["serial_numbers"] = [line.serial.serial_number]
        if line.kind == JobCardLine.Kind.PART and line.product.track_batch:
            batch = line.batch
            batch_no = (line.batch_no or getattr(batch, "batch_no", "") or "").strip()
            if batch is None and not batch_no:
                raise BusinessRuleError(
                    f"A batch is required for tracked part '{line.product.name}'."
                )
            expiry = getattr(batch, "expiry_date", None)
            if expiry is not None and expiry < timezone.localdate():
                raise BusinessRuleError(
                    f"Batch '{batch_no or batch}' for '{line.product.name}' is expired."
                )
            payload["batch"] = batch
            payload["batch_no"] = batch_no
        items.append(payload)
    draft = SalesInvoice.objects.create(
        company=job.company,
        customer=job.customer,
        invoice_type=SalesInvoice.InvoiceType.GST,
        created_by=user,
        updated_by=user,
    )
    SalesService.set_items(draft, items, user)
    job.sales_invoice = draft
    job.status = JobCard.Status.IN_PROGRESS
    job.updated_by = user
    job.save(update_fields=["sales_invoice", "status", "updated_by", "updated_at"])
    return draft
