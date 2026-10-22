"""QOS-0147: a routing step done by a job worker, raised from the work order.

From a subcontract job card the factory raises the job-work order and challan for the step (with the
material that goes out), and the job worker's return receipt writes back to the card: the quantity that
came back, what the job worker charged, and, when the goods are one of the work order's materials, a draft
issue so they go into the order. The charge is already in the cost of the returned goods, so it is shown
on the card but never absorbed into the work order a second time.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from manufacturing.models import DocumentStatus, JobCard, MaterialIssue, WorkOrder

from .common import ZERO, d, rule

OPEN_ORDER = (WorkOrder.Status.RELEASED, WorkOrder.Status.IN_PROGRESS)
NOTE = "From job work receipt "


def _card(card_id, company) -> JobCard:
    # of=("self",): the join to the nullable routing step cannot be locked on PostgreSQL.
    card = JobCard.objects.select_for_update(of=("self",)).select_related("work_order", "operation").filter(
        pk=getattr(card_id, "pk", card_id), company=company,
    ).first()
    if card is None:
        raise rule("That job card was not found.", "MFG_NOT_FOUND")
    return card


def default_lines(wo) -> list[dict]:
    """The material the order still has to take: what a step normally sends out."""
    by_product: dict[int, Decimal] = {}
    for wl in wo.component_lines.select_related("component").filter(alternate_of__isnull=True):
        if wl.qty_remaining > 0 and wl.issue_method != "BACKFLUSH" and not wl.principal_supplied:
            by_product[wl.component_id] = by_product.get(wl.component_id, ZERO) + wl.qty_remaining
    return [{"product": product, "qty": qty} for product, qty in by_product.items()]


@transaction.atomic
def send_out(card, user, *, supplier=None, lines=None, expected_return_date=None, challan_date=None,
             vehicle_no="", warehouse=None, notes="", issue=False, can_backdate=True):
    """Raise the job-work order and challan for a subcontract step. Returns (order, challan)."""
    from jobwork.services import out

    card = _card(card, card.company)
    wo = card.work_order
    if not card.is_subcontract:
        raise rule("This step is done in the factory, not by a job worker.", "MFG_SUBCONTRACT_NOT_STEP")
    if card.jobwork_order_id:
        raise rule("Job work has already been raised for this step.", "MFG_SUBCONTRACT_RAISED")
    if card.status in (JobCard.Status.DONE, JobCard.Status.CANCELLED):
        raise rule("This job card is finished.", "MFG_CARD_DONE")
    if wo.status not in OPEN_ORDER:
        raise rule("The work order is not running.", "MFG_BAD_WO_STATUS")
    worker = supplier or (card.operation.subcontract_supplier if card.operation_id else None)
    if worker is None:
        raise rule("Choose the job worker for this step.", "MFG_SUBCONTRACT_NO_WORKER")
    lines = list(lines) if lines else default_lines(wo)
    if not lines:
        raise rule("There is no material left to send. Add the lines that go out.", "MFG_SUBCONTRACT_NO_LINES")
    order = out.create_order(
        wo.company, user, supplier=worker, process=card.name, expected_return_date=expected_return_date,
        notes=(notes or f"{wo.number}, step {card.sequence}")[:500],
    )
    order.work_order_id, order.job_card_id = wo.pk, card.pk
    order.save(update_fields=["work_order_id", "job_card_id", "updated_at"])
    challan = out.create_challan(
        order, user, lines, challan_date=challan_date, warehouse=warehouse, vehicle_no=vehicle_no,
        notes=f"{wo.number}, step {card.sequence}",
    )
    card.jobwork_order_id = order.pk
    card.save(update_fields=["jobwork_order_id", "updated_at"])
    if issue:
        challan = out.issue_challan(challan, user, can_backdate=can_backdate)
    return order, challan


# --- what job work tells the card ----------------------------------------------------------------

def _card_of(order):
    if not order.work_order_id or not order.job_card_id:
        return None
    return JobCard.objects.select_for_update(of=("self",)).select_related("work_order").filter(
        pk=order.job_card_id, company=order.company,
    ).first()


def on_challan_issued(order) -> None:
    card = _card_of(order)
    if card is None or card.status in (JobCard.Status.DONE, JobCard.Status.CANCELLED):
        return
    now = timezone.now()
    card.status = JobCard.Status.IN_PROGRESS
    card.started_at = card.started_at or now
    card.save(update_fields=["status", "started_at", "updated_at"])
    if card.work_order.status == WorkOrder.Status.RELEASED:
        WorkOrder.objects.filter(pk=card.work_order_id).update(status=WorkOrder.Status.IN_PROGRESS)


def _all_back(order) -> bool:
    from jobwork.models import JobWorkChallanLine

    open_lines = JobWorkChallanLine.objects.filter(challan__order=order, challan__status="ISSUED")
    return bool(open_lines.exists()) and all(ln.qty_open <= 0 for ln in open_lines)


def on_receipt_posted(order, receipt, user) -> None:
    from jobwork.models import JobWorkReceiptLine

    card = _card_of(order)
    if card is None:
        return
    processed = list(receipt.lines.filter(kind=JobWorkReceiptLine.Kind.PROCESSED).select_related("product", "batch"))
    qty = sum((d(ln.qty) for ln in processed), ZERO)
    charge = sum((d(ln.charge_amount) for ln in processed), ZERO)
    card.qty_good = d(card.qty_good) + qty
    card.outside_cost = d(card.outside_cost) + charge
    if _all_back(order):
        card.status = JobCard.Status.DONE
        card.finished_at = timezone.now()
    card.save(update_fields=["qty_good", "outside_cost", "status", "finished_at", "updated_at"])
    _draft_issue_for_returned_goods(card, receipt, processed, user)


def on_receipt_reversed(order, receipt) -> None:
    from jobwork.models import JobWorkReceiptLine

    card = _card_of(order)
    if card is None:
        return
    processed = list(receipt.lines.filter(kind=JobWorkReceiptLine.Kind.PROCESSED))
    card.qty_good = max(ZERO, d(card.qty_good) - sum((d(ln.qty) for ln in processed), ZERO))
    card.outside_cost = max(ZERO, d(card.outside_cost) - sum((d(ln.charge_amount) for ln in processed), ZERO))
    if card.status == JobCard.Status.DONE:
        card.status = JobCard.Status.IN_PROGRESS
        card.finished_at = None
    card.save(update_fields=["qty_good", "outside_cost", "status", "finished_at", "updated_at"])
    MaterialIssue.objects.filter(
        company=card.company, work_order_id=card.work_order_id, status=DocumentStatus.DRAFT,
        notes=f"{NOTE}{receipt.number}",
    ).delete()


def on_order_closed(order) -> None:
    """The job-work order was closed. A step nothing came back from goes back to waiting, so it can be raised again."""
    card = _card_of(order)
    if card is None or card.status in (JobCard.Status.DONE, JobCard.Status.CANCELLED):
        return
    if d(card.qty_good) > 0:
        card.status = JobCard.Status.DONE
        card.finished_at = card.finished_at or timezone.now()
    else:
        card.status = JobCard.Status.PLANNED
        card.started_at = None
        card.jobwork_order_id = None
    card.save(update_fields=["status", "started_at", "finished_at", "jobwork_order_id", "updated_at"])


def _draft_issue_for_returned_goods(card, receipt, processed, user) -> None:
    """When the goods that came back are one of the order's materials, draft the issue that takes them in."""
    from . import issue as issue_svc

    wo = card.work_order
    if wo.issue_mode != WorkOrder.IssueMode.SEPARATE or wo.status not in OPEN_ORDER:
        return
    wanted = []
    for ln in processed:
        wl = wo.component_lines.filter(component_id=ln.product_id, alternate_of__isnull=True).first()
        if wl is None:
            # Not one of the order's materials: it goes in as extra material, which a manager approves.
            wanted.append({
                "component": ln.product_id, "qty": d(ln.qty), "warehouse": receipt.warehouse_id, "batch": ln.batch_id,
                "extra_reason": f"Returned from job worker ({receipt.number})",
            })
            continue
        if wl.qty_remaining <= 0:
            continue
        wanted.append({
            "wo_line": wl, "qty": min(d(ln.qty), wl.qty_remaining), "warehouse": receipt.warehouse_id,
            "batch": ln.batch_id,
        })
    if not wanted:
        return
    # A convenience: if the draft cannot be made, the goods are still recorded as received.
    try:
        with transaction.atomic():
            issue_svc.create_issue(wo, user, wanted, notes=f"{NOTE}{receipt.number}")
    except BusinessRuleError:
        return


# --- gates ------------------------------------------------------------------------------------------

def assert_nothing_out_with_job_worker(wo) -> None:
    """A work order cannot finish or be cancelled while one of its steps is still at a job worker."""
    out = wo.job_cards.filter(is_subcontract=True, status=JobCard.Status.IN_PROGRESS, jobwork_order_id__isnull=False)
    if out.exists():
        step = out.first()
        raise rule(
            f"Step '{step.name}' is still with the job worker. Record what came back, or close the job work, first.",
            "MFG_SUBCONTRACT_OPEN",
        )
