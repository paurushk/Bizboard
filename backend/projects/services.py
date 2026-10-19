from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.services.sequences import next_number
from masters.models import Product
from sales.models import SalesInvoice
from sales.services import SalesService

from .models import Project, ProjectMilestone


def _audit(project, user, action, **metadata):
    AuditService.log(
        action=action, company=project.company, user=user, entity_type="Project", entity_id=project.pk,
        metadata=metadata,
    )


def _check_dates(start, end):
    if start and end and end < start:
        raise BusinessRuleError("The end date cannot be before the start date.")


def _money(value, label):
    try:
        amount = Decimal(str(value))
    except Exception:  # noqa: BLE001
        raise BusinessRuleError(f"{label} must be a number.") from None
    if amount < 0:
        raise BusinessRuleError(f"{label} cannot be negative.")
    return amount


@transaction.atomic
def create_project(
    company, user, *, customer, name, notes="", start_date=None, end_date=None,
    contract_value=None, contract=None,
):
    if customer is None or customer.company_id != company.id:
        raise BusinessRuleError("Customer is not in this company.")
    name = (name or "").strip()
    if not name:
        raise BusinessRuleError("A project needs a name.")
    _check_dates(start_date, end_date)
    if contract is not None and (contract.company_id != company.id or contract.customer_id != customer.id):
        raise BusinessRuleError("The contract must belong to this customer.")
    project = Project.objects.create(
        company=company,
        customer=customer,
        name=name,
        notes=notes or "",
        start_date=start_date,
        end_date=end_date,
        contract_value=_money(contract_value, "Contract value") if contract_value not in (None, "") else None,
        contract=contract,
        number=next_number(company, "PROJECT", prefix="PRJ"),
        created_by=user,
        updated_by=user,
    )
    _audit(project, user, "project_created")
    return project


@transaction.atomic
def update_project(project, user, **fields):
    project = Project.objects.select_for_update().get(pk=project.pk)
    if project.status != Project.Status.OPEN:
        raise BusinessRuleError("Only an open project can be edited.")
    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise BusinessRuleError("A project needs a name.")
        project.name = name
    if "notes" in fields:
        project.notes = fields["notes"] or ""
    start = fields.get("start_date", project.start_date)
    end = fields.get("end_date", project.end_date)
    _check_dates(start, end)
    project.start_date, project.end_date = start, end
    if "contract_value" in fields:
        raw = fields["contract_value"]
        project.contract_value = None if raw in (None, "") else _money(raw, "Contract value")
    if "contract" in fields:
        contract = fields["contract"]
        if contract is not None and (
            contract.company_id != project.company_id or contract.customer_id != project.customer_id
        ):
            raise BusinessRuleError("The contract must belong to this customer.")
        project.contract = contract
    project.updated_by = user
    project.save()
    _audit(project, user, "project_updated", fields=sorted(fields))
    return project


@transaction.atomic
def add_milestone(project, user, *, name, amount, service_product, sequence=1, target_completion_date=None):
    project = Project.objects.select_for_update().get(pk=project.pk)
    if project.status != Project.Status.OPEN:
        raise BusinessRuleError("Milestones can be added only on an open project.")
    if not (name or "").strip():
        raise BusinessRuleError("A milestone needs a name.")
    if service_product is None or service_product.company_id != project.company_id:
        raise BusinessRuleError("Service product is not in this company.")
    if service_product.product_type != Product.ProductType.SERVICE:
        raise BusinessRuleError("A milestone bills a service product, not stock.")
    if Decimal(str(amount)) <= 0:
        raise BusinessRuleError("Milestone amount must be positive.")
    milestone = ProjectMilestone.objects.create(
        company=project.company,
        project=project,
        name=name.strip(),
        sequence=sequence,
        amount=amount,
        target_completion_date=target_completion_date,
        service_product=service_product,
        created_by=user,
        updated_by=user,
    )
    _audit(project, user, "milestone_added", milestone=milestone.pk, amount=str(amount))
    return milestone


@transaction.atomic
def update_milestone(
    milestone, user, *, name=None, amount=None, target_completion_date=None, sequence=None, set_target=False,
):
    milestone = ProjectMilestone.objects.select_for_update().select_related("project").get(pk=milestone.pk)
    if milestone.status != ProjectMilestone.Status.PLANNED or milestone.sales_invoice_id:
        raise BusinessRuleError("Only a planned milestone can be edited.")
    if name is not None:
        if not str(name).strip():
            raise BusinessRuleError("A milestone needs a name.")
        milestone.name = str(name).strip()
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
    _audit(milestone.project, user, "milestone_updated", milestone=milestone.pk)
    return milestone


@transaction.atomic
def delete_milestone(milestone, user):
    milestone = ProjectMilestone.objects.select_for_update().select_related("project").get(pk=milestone.pk)
    if milestone.sales_invoice_id or milestone.status == ProjectMilestone.Status.INVOICED:
        raise BusinessRuleError("A milestone that has an invoice cannot be deleted.")
    project, milestone_id = milestone.project, milestone.pk
    milestone.delete()
    _audit(project, user, "milestone_deleted", milestone=milestone_id)


@transaction.atomic
def reorder_milestones(project, user, ordered_ids):
    project = Project.objects.select_for_update().get(pk=project.pk)
    rows = {row.pk: row for row in project.milestones.select_for_update()}
    ids = [int(pk) for pk in ordered_ids]
    if set(ids) != set(rows) or len(ids) != len(set(ids)):
        raise BusinessRuleError("Send every milestone of this project exactly once.")
    for position, pk in enumerate(ids, start=1):
        if rows[pk].sequence != position:
            rows[pk].sequence = position
            rows[pk].save(update_fields=["sequence", "updated_at"])
    _audit(project, user, "milestones_reordered")
    return project


@transaction.atomic
def mark_ready(milestone, user):
    milestone = ProjectMilestone.objects.select_for_update().select_related("project").get(pk=milestone.pk)
    if milestone.project.status != Project.Status.OPEN:
        raise BusinessRuleError("This project is not open.")
    if milestone.status != ProjectMilestone.Status.PLANNED:
        raise BusinessRuleError("Only a planned milestone can be marked ready.")
    milestone.status = ProjectMilestone.Status.READY
    milestone.updated_by = user
    milestone.save(update_fields=["status", "updated_by", "updated_at"])
    _audit(milestone.project, user, "milestone_ready", milestone=milestone.pk)
    return milestone


@transaction.atomic
def unready_milestone(milestone, user):
    """Take a READY milestone back to PLANNED so it can be edited or removed (PRJ-01)."""
    milestone = ProjectMilestone.objects.select_for_update().select_related("project").get(pk=milestone.pk)
    if milestone.status != ProjectMilestone.Status.READY or milestone.sales_invoice_id:
        raise BusinessRuleError("Only a ready milestone with no invoice can go back to planned.")
    milestone.status = ProjectMilestone.Status.PLANNED
    milestone.updated_by = user
    milestone.save(update_fields=["status", "updated_by", "updated_at"])
    _audit(milestone.project, user, "milestone_unready", milestone=milestone.pk)
    return milestone


def sync_project_milestone(invoice, *, completed: bool):
    """Keep the milestone in step with the sales invoice it points at."""
    qs = ProjectMilestone.objects.filter(sales_invoice_id=invoice.pk)
    if completed:
        qs.update(status=ProjectMilestone.Status.INVOICED, updated_at=timezone.now())
        return
    qs.update(
        sales_invoice=None,
        status=ProjectMilestone.Status.READY,
        updated_at=timezone.now(),
    )


def earlier_unbilled(milestone):
    """Names of milestones that come before this one and are not invoiced yet (for a warning)."""
    return list(
        milestone.project.milestones.exclude(pk=milestone.pk)
        .filter(sequence__lt=milestone.sequence)
        .exclude(status=ProjectMilestone.Status.INVOICED)
        .values_list("name", flat=True)
    )


@transaction.atomic
def invoice_milestone(milestone, user):
    milestone = ProjectMilestone.objects.select_for_update().select_related("project", "service_product").get(
        pk=milestone.pk
    )
    if milestone.project.status != Project.Status.OPEN:
        raise BusinessRuleError("This project is not open.")
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
            "description": f"{milestone.project.number} · {milestone.name}"[:255],
            "quantity": Decimal("1"),
            "unit_price": milestone.amount,
            "gst_rate": product.gst_rate,
        }],
        user,
    )
    milestone.sales_invoice = draft
    milestone.updated_by = user
    milestone.save(update_fields=["sales_invoice", "updated_by", "updated_at"])
    _audit(milestone.project, user, "milestone_invoiced", milestone=milestone.pk, invoice=draft.pk)
    return draft


@transaction.atomic
def close_project(project, user):
    project = Project.objects.select_for_update().get(pk=project.pk)
    if project.status != Project.Status.OPEN:
        raise BusinessRuleError("Only an open project can be closed.")
    milestones = project.milestones
    if not milestones.exists():
        raise BusinessRuleError("This project has no milestones. Cancel it instead of closing it.")
    incomplete = milestones.filter(sales_invoice__isnull=False).exclude(
        sales_invoice__status=SalesInvoice.Status.COMPLETED,
    )
    unbilled = milestones.exclude(
        status=ProjectMilestone.Status.INVOICED,
    ).filter(sales_invoice__isnull=True)
    if incomplete.exists() or unbilled.exists():
        names = list(incomplete.values_list("name", flat=True)) + list(unbilled.values_list("name", flat=True))
        raise BusinessRuleError(
            "Complete the invoice or remove the milestone for: " + ", ".join(names[:5]) + "."
        )
    milestones.filter(sales_invoice__status=SalesInvoice.Status.COMPLETED).update(
        status=ProjectMilestone.Status.INVOICED,
    )
    if not milestones.filter(status=ProjectMilestone.Status.INVOICED).exists():
        raise BusinessRuleError("Nothing has been invoiced. Cancel the project instead of closing it.")
    project.status = Project.Status.CLOSED
    project.updated_by = user
    project.save(update_fields=["status", "updated_by", "updated_at"])
    _audit(project, user, "project_closed")
    return project


@transaction.atomic
def cancel_project(project, user, reason=""):
    """Cancel a project that has billed nothing for real; drafts are discarded through Sales (PRJ-02)."""
    project = Project.objects.select_for_update().get(pk=project.pk)
    if project.status != Project.Status.OPEN:
        raise BusinessRuleError("Only an open project can be cancelled.")
    if project.milestones.filter(sales_invoice__status=SalesInvoice.Status.COMPLETED).exists():
        raise BusinessRuleError("A milestone has a completed invoice. Close the project instead of cancelling it.")
    for milestone in project.milestones.select_for_update().exclude(sales_invoice__isnull=True):
        invoice = SalesInvoice.objects.select_for_update().get(pk=milestone.sales_invoice_id)
        if invoice.status == SalesInvoice.Status.DRAFT:
            SalesService.cancel(invoice, user, reason=f"Project {project.number} cancelled")
    project.status = Project.Status.CANCELLED
    project.updated_by = user
    project.save(update_fields=["status", "updated_by", "updated_at"])
    _audit(project, user, "project_cancelled", reason=(reason or "")[:200])
    return project


def project_totals(project) -> dict:
    """Planned, invoiced and remaining amounts (ex-GST) from the milestones."""
    planned = Decimal("0")
    invoiced = Decimal("0")
    ready = Decimal("0")
    for milestone in project.milestones.all():
        amount = Decimal(str(milestone.amount))
        planned += amount
        if milestone.status == ProjectMilestone.Status.INVOICED:
            invoiced += amount
        elif milestone.status == ProjectMilestone.Status.READY:
            ready += amount
    money = Decimal("0.01")
    planned, invoiced, ready = (value.quantize(money) for value in (planned, invoiced, ready))
    percent = int((invoiced / planned * 100).to_integral_value(ROUND_HALF_UP)) if planned else 0
    over = bool(project.contract_value is not None and planned > project.contract_value)
    return {
        "planned_total": planned, "invoiced_total": invoiced, "ready_total": ready,
        "remaining_total": planned - invoiced, "percent_complete": percent, "over_budget": over,
    }
