from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from accounts.models import CompanyUser
from core.exceptions import BusinessRuleError, ConflictError
from core.services.audit import AuditService
from core.services.sequences import next_number
from inventory.item_stock import tracks_inventory
from inventory.services import InventoryService
from masters.models import Product
from sales.models import SalesInvoice
from sales.services import SalesService

from .models import JobCard, JobCardLine, ServiceBay

_OPEN = (JobCard.Status.DRAFT, JobCard.Status.IN_PROGRESS)
_DONE = (JobCard.Status.CANCELLED, JobCard.Status.INVOICED)


def _audit(job, user, action, **metadata):
    AuditService.log(
        action=action, company=job.company, user=user, entity_type="JobCard", entity_id=job.pk,
        metadata=metadata,
    )


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


def job_totals(job) -> dict:
    """Taxable value, GST and total of the job's lines, to the paisa per line."""
    taxable = Decimal("0")
    gst = Decimal("0")
    for line in job.lines.all():
        base = (Decimal(str(line.quantity)) * Decimal(str(line.unit_price))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        rate = Decimal(str(getattr(line.product, "gst_rate", 0) or 0))
        taxable += base
        gst += (base * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"subtotal": taxable, "gst_total": gst, "total": taxable + gst}


def _warehouse(job):
    return job.warehouse if job.warehouse_id else InventoryService.default_warehouse(job.company)


def _same_company_customer(company, customer, obj, label):
    if obj is None:
        return
    if obj.company_id != company.id or obj.customer_id != customer.id:
        raise BusinessRuleError(f"The {label} must belong to this customer.")


def _check_technician(company, technician):
    if technician is None:
        return
    if technician.company_id != company.id or not technician.is_active:
        raise BusinessRuleError("The technician is not an active member of this company.")


def _in_transaction():
    from django.db import connection

    if not connection.in_atomic_block:
        raise RuntimeError("Bay and technician booking checks must run inside a transaction.")


def assert_bay_free(company, bay, start, end, *, ignore_job_id=None):
    if bay is None:
        return
    if start is None or end is None:
        raise BusinessRuleError("A bay booking needs a start and an end.")
    if end <= start:
        raise BusinessRuleError("The bay booking must end after it starts.")
    _in_transaction()
    # Lock the bay row so two simultaneous bookings are decided one after the other.
    bay = ServiceBay.objects.select_for_update().get(pk=bay.pk)
    if not bay.is_active:
        raise BusinessRuleError("This service bay is switched off.")
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


def assert_technician_free(company, technician, start, end, *, ignore_job_id=None, allow_overlap=False):
    """Warn when the technician already has a job in that window. The caller may confirm and go on."""
    if technician is None or start is None or end is None or allow_overlap:
        return
    _in_transaction()
    CompanyUser.objects.select_for_update().get(pk=technician.pk)
    clash = JobCard.objects.filter(
        company=company, technician=technician, scheduled_start__lt=end, scheduled_end__gt=start,
    ).exclude(status__in=_DONE)
    if ignore_job_id:
        clash = clash.exclude(pk=ignore_job_id)
    numbers = list(clash.values_list("number", flat=True)[:5])
    if numbers:
        raise ConflictError({
            "code": "technician_busy",
            "message": f"This technician is already booked for {', '.join(numbers)} in that time. "
                       "Send allow_overlap to book anyway.",
            "jobs": numbers,
        })


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


def assert_contract_live(job, contract):
    """A job may be covered only by a live contract of the same customer."""
    from contracts.ops import coverage_for

    if not coverage_for(job.company, job.customer_id, None, timezone.localdate()).filter(pk=contract.pk).exists():
        raise BusinessRuleError("That contract is not active today for this customer.")


@transaction.atomic
def create_job(
    company, user, *, customer, complaint="", technician=None, lines=None,
    registration_no="", vehicle_model="", odometer_reading=None,
    service_bay=None, scheduled_start=None, scheduled_end=None,
    contract=None, ticket=None, source_complaint=None, warehouse=None, allow_overlap=False,
):
    if customer is None or customer.company_id != company.id:
        raise BusinessRuleError("Customer is not in this company.")
    if service_bay is not None and service_bay.company_id != company.id:
        raise BusinessRuleError("Service bay is not in this company.")
    if warehouse is not None and warehouse.company_id != company.id:
        raise BusinessRuleError("Warehouse is not in this company.")
    if odometer_reading is not None and Decimal(str(odometer_reading)) < 0:
        raise BusinessRuleError("Odometer reading cannot be negative.")
    _check_technician(company, technician)
    _same_company_customer(company, customer, ticket, "ticket")
    _same_company_customer(company, customer, source_complaint, "complaint")
    _same_company_customer(company, customer, contract, "contract")
    assert_bay_free(company, service_bay, scheduled_start, scheduled_end)
    assert_technician_free(company, technician, scheduled_start, scheduled_end, allow_overlap=allow_overlap)
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
        contract=contract,
        ticket=ticket,
        source_complaint=source_complaint,
        warehouse=warehouse,
        number=next_number(company, "JOB", prefix="JOB"),
        created_by=user,
        updated_by=user,
    )
    if contract is not None:
        assert_contract_live(job, contract)
    for line in lines or []:
        add_line(job, user, **line)
    _audit(job, user, "job_created", customer=customer.pk)
    return job


@transaction.atomic
def update_job(job, user, **fields):
    """Edit the header of an open job (JOB-04). Each field is checked against the lines already on it."""
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    if job.status not in _OPEN:
        raise BusinessRuleError("A closed job cannot be edited.")
    company = job.company
    changed = {}
    locked = job.sales_invoice_id is not None
    if "customer" in fields and fields["customer"].pk != job.customer_id:
        if locked or job.lines.exists() or job.ticket_id or job.source_complaint_id or job.contract_id:
            raise BusinessRuleError("The customer cannot change once the job has lines, links or an invoice.")
        if fields["customer"].company_id != company.id:
            raise BusinessRuleError("Customer is not in this company.")
        job.customer = fields["customer"]
        changed["customer"] = job.customer_id
    if "technician" in fields:
        _check_technician(company, fields["technician"])
        job.technician = fields["technician"]
        assert_technician_free(
            company, job.technician, job.scheduled_start, job.scheduled_end, ignore_job_id=job.pk,
            allow_overlap=bool(fields.get("allow_overlap")),
        )
        changed["technician"] = getattr(job.technician, "pk", None)
    for name in ("complaint", "registration_no", "vehicle_model"):
        if name in fields:
            setattr(job, name, fields[name] or "")
            changed[name] = True
    if "odometer_reading" in fields:
        value = fields["odometer_reading"]
        if value is not None and Decimal(str(value)) < 0:
            raise BusinessRuleError("Odometer reading cannot be negative.")
        job.odometer_reading = value
        changed["odometer_reading"] = True
    if "contract" in fields:
        contract = fields["contract"]
        if contract is not None:
            _same_company_customer(company, job.customer, contract, "contract")
            assert_contract_live(job, contract)
        elif job.lines.filter(covered_by_contract=True).exists():
            raise BusinessRuleError("Remove the covered lines before taking the contract off the job.")
        job.contract = contract
        changed["contract"] = getattr(contract, "pk", None)
    for name, label in (("ticket", "ticket"), ("source_complaint", "complaint")):
        if name in fields:
            _same_company_customer(company, job.customer, fields[name], label)
            setattr(job, name, fields[name])
            changed[name] = getattr(fields[name], "pk", None)
    if "warehouse" in fields:
        warehouse = fields["warehouse"]
        if warehouse is not None and warehouse.company_id != company.id:
            raise BusinessRuleError("Warehouse is not in this company.")
        if job.lines.filter(kind=JobCardLine.Kind.PART).exists() and (
            getattr(warehouse, "pk", None) != job.warehouse_id
        ):
            raise BusinessRuleError("The warehouse cannot change once the job holds parts. Remove them first.")
        job.warehouse = warehouse
        changed["warehouse"] = getattr(warehouse, "pk", None)
    if locked and set(changed) - {"technician", "complaint", "registration_no", "vehicle_model", "odometer_reading"}:
        raise BusinessRuleError("Revert the invoice draft to editing before changing the job's links.")
    job.updated_by = user
    job.save()
    _audit(job, user, "job_updated", fields=sorted(changed))
    return job


@transaction.atomic
def add_line(
    job, user, *, kind, product, quantity, unit_price, serial=None, batch=None, batch_no="",
    labour_minutes=0, technician_commission_percent=0, covered_by_contract=False,
):
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    if job.status not in _OPEN:
        raise BusinessRuleError("Lines can be added only while the job is open.")
    if job.sales_invoice_id is not None:
        raise BusinessRuleError(
            "An invoice draft already exists for this job. Revert it to editing before adding lines."
        )
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
    if covered_by_contract:
        if job.contract_id is None:
            raise BusinessRuleError("Pick the contract that covers this job before marking a line covered.")
        assert_contract_live(job, job.contract)
        unit_price = Decimal("0")
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
        covered_by_contract=bool(covered_by_contract),
        created_by=user,
        updated_by=user,
    )
    if kind == JobCardLine.Kind.PART and tracks_inventory(product):
        InventoryService.reserve_stock(
            job.company, _warehouse(job), product, quantity, user=user, batch=batch,
        )
    _audit(job, user, "job_line_added", line=line.pk, kind=kind, product=product.pk, covered=bool(covered_by_contract))
    return line


def _assert_lines_editable(job):
    if job.status not in _OPEN:
        raise BusinessRuleError("Lines can be changed only while the job is open.")
    if job.sales_invoice_id is not None:
        raise BusinessRuleError(
            "An invoice draft already exists for this job. Revert it to editing before changing lines."
        )


@transaction.atomic
def update_line(job, line, user, *, quantity=None, unit_price=None, labour_minutes=None,
                technician_commission_percent=None, batch=None, serial=None, set_batch=False, set_serial=False):
    """Change a line and move its stock hold by the difference (JOB-03)."""
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    _assert_lines_editable(job)
    line = JobCardLine.objects.select_for_update(of=("self",)).select_related("product", "batch").get(pk=line.pk, job=job)
    new_qty = Decimal(str(quantity)) if quantity is not None else line.quantity
    new_price = Decimal(str(unit_price)) if unit_price is not None else line.unit_price
    new_qty, new_price = _positive_money(new_qty, new_price)
    if line.covered_by_contract:
        new_price = Decimal("0")
    new_batch = batch if set_batch else line.batch
    new_serial = serial if set_serial else line.serial
    _check_line(job.company, line.kind, line.product, new_serial)
    if new_batch is not None and (new_batch.company_id != job.company_id or new_batch.product_id != line.product_id):
        raise BusinessRuleError("Batch does not match this part.")
    holds = line.kind == JobCardLine.Kind.PART and tracks_inventory(line.product)
    if holds and (new_qty != line.quantity or new_batch != line.batch):
        warehouse = _warehouse(job)
        InventoryService.release_reservation(
            job.company, warehouse, line.product, line.quantity, user=user, batch=line.batch,
        )
        InventoryService.reserve_stock(job.company, warehouse, line.product, new_qty, user=user, batch=new_batch)
    line.quantity = new_qty
    line.unit_price = new_price
    line.batch = new_batch
    line.serial = new_serial
    if set_batch:
        line.batch_no = getattr(new_batch, "batch_no", "") or ""
    if labour_minutes is not None:
        line.labour_minutes = max(0, int(labour_minutes))
    if technician_commission_percent is not None:
        percent = Decimal(str(technician_commission_percent))
        if percent < 0:
            raise BusinessRuleError("Commission cannot be negative.")
        line.technician_commission_percent = percent
    line.updated_by = user
    line.save()
    _audit(job, user, "job_line_updated", line=line.pk)
    return line


@transaction.atomic
def remove_line(job, line, user):
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    _assert_lines_editable(job)
    line = JobCardLine.objects.select_for_update(of=("self",)).select_related("product", "batch").get(pk=line.pk, job=job)
    if line.kind == JobCardLine.Kind.PART and tracks_inventory(line.product):
        InventoryService.release_reservation(
            job.company, _warehouse(job), line.product, line.quantity, user=user, batch=line.batch,
        )
    line_id = line.pk
    line.delete()
    _audit(job, user, "job_line_removed", line=line_id)
    return job


def _release_job_reservations(job, user):
    warehouse = _warehouse(job)
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
    _audit(job, user, "job_started")
    return job


@transaction.atomic
def schedule_job(job, user, *, service_bay, scheduled_start, scheduled_end, allow_overlap=False):
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    if job.status in (JobCard.Status.INVOICED, JobCard.Status.CANCELLED):
        raise BusinessRuleError("A closed job cannot be scheduled.")
    if service_bay is None or service_bay.company_id != job.company_id:
        raise BusinessRuleError("Service bay is not in this company.")
    assert_bay_free(job.company, service_bay, scheduled_start, scheduled_end, ignore_job_id=job.pk)
    assert_technician_free(
        job.company, job.technician, scheduled_start, scheduled_end, ignore_job_id=job.pk,
        allow_overlap=allow_overlap,
    )
    job.service_bay = service_bay
    job.scheduled_start = scheduled_start
    job.scheduled_end = scheduled_end
    job.updated_by = user
    job.save(update_fields=[
        "service_bay", "scheduled_start", "scheduled_end", "updated_by", "updated_at",
    ])
    _audit(job, user, "job_scheduled", bay=service_bay.pk)
    return job


@transaction.atomic
def cancel_job(job, user):
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    if job.sales_invoice_id is not None:
        if job.sales_invoice.status != SalesInvoice.Status.CANCELLED:
            raise BusinessRuleError("Cancel the invoice. An invoiced job stays invoiced.")
        # The invoice was cancelled: the link is stale, so the job can be cancelled.
        job.sales_invoice = None
    if job.status == JobCard.Status.CANCELLED:
        return job
    _release_job_reservations(job, user)
    job.status = JobCard.Status.CANCELLED
    job.updated_by = user
    job.save(update_fields=["status", "sales_invoice", "updated_by", "updated_at"])
    _audit(job, user, "job_cancelled")
    return job


@transaction.atomic
def reopen_job(job, user):
    """Throw away the draft invoice so the job can be edited again (JOB-02).

    Only a DRAFT invoice can be reverted. Cancelling it goes through Sales, which unlinks the job
    and puts it back in progress, so the job and invoice can never drift apart.
    """
    job = JobCard.objects.select_for_update().get(pk=job.pk)
    if job.sales_invoice_id is None:
        if job.status == JobCard.Status.IN_PROGRESS:
            return job
        raise BusinessRuleError("There is no invoice draft to revert.")
    invoice = SalesInvoice.objects.select_for_update().get(pk=job.sales_invoice_id)
    if invoice.status == SalesInvoice.Status.DRAFT:
        SalesService.cancel(invoice, user, reason=f"Reverted to job card {job.number}")
    elif invoice.status != SalesInvoice.Status.CANCELLED:
        raise BusinessRuleError("Only a draft invoice can be reverted. Cancel or return the invoice in Sales.")
    job.refresh_from_db()
    if job.sales_invoice_id is not None:
        job.sales_invoice = None
    if job.status != JobCard.Status.CANCELLED:
        job.status = JobCard.Status.IN_PROGRESS
    job.updated_by = user
    job.save(update_fields=["sales_invoice", "status", "updated_by", "updated_at"])
    _audit(job, user, "job_reopened")
    return job


def release_reservations_for_invoice(invoice, user=None):
    """Drop the part holds of any open job card billed by this invoice (called by complete)."""
    for job in JobCard.objects.filter(sales_invoice_id=invoice.pk).exclude(status__in=_DONE):
        _release_job_reservations(job, user)


def sync_job_card(invoice, *, completed: bool):
    """Keep the job card in step with the sales invoice it was converted to.

    INVOICED is written only when the invoice completes. A draft link leaves
    the job IN_PROGRESS so a second convert can find the same invoice.
    """
    if completed:
        jobs = list(JobCard.objects.filter(sales_invoice_id=invoice.pk).exclude(status__in=_DONE))
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
                and job.status not in _DONE
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
    if job.status not in _OPEN:
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
        warehouse=job.warehouse if job.warehouse_id else None,
        created_by=user,
        updated_by=user,
    )
    SalesService.set_items(draft, items, user)
    job.sales_invoice = draft
    job.status = JobCard.Status.IN_PROGRESS
    job.updated_by = user
    job.save(update_fields=["sales_invoice", "status", "updated_by", "updated_at"])
    _audit(job, user, "job_converted", invoice=draft.pk)
    return draft
