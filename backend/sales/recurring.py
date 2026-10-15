"""BB-000669: recurring sales document schedules.

A schedule spawns one document per period (draft invoice, sales order or draft
delivery challan). An invoice schedule can also ask for the invoice to be
completed on creation (``auto_complete``); if a completion gate rejects it the
invoice stays a normal DRAFT and the reason is stored on the run.
"""

from __future__ import annotations

import logging
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounting.models import AccountingPeriod
from core.exceptions import BusinessRuleError
from masters.models import Product
from reporting.models import GstReturnPeriod

from .models import RecurringInvoiceRun, RecurringInvoiceSchedule, SalesInvoice
from .services import SalesService

logger = logging.getLogger(__name__)

_MONTH_STEPS = {
    RecurringInvoiceSchedule.Cadence.MONTHLY: 1,
    RecurringInvoiceSchedule.Cadence.QUARTERLY: 3,
    RecurringInvoiceSchedule.Cadence.HALF_YEARLY: 6,
    RecurringInvoiceSchedule.Cadence.ANNUALLY: 12,
}

# Why a run was not generated; the "Run now" endpoint turns these into messages.
REASON_MESSAGES = {
    "inactive": "This schedule is paused. Resume it before running.",
    "locked": "The accounting or GST period for this run is closed. Reopen it, then run again.",
    "expired": "This schedule has passed its end date.",
    "limit_reached": "This schedule has reached its maximum number of runs.",
}


def period_key_for(cadence: str, on_date: date) -> str:
    if cadence == RecurringInvoiceSchedule.Cadence.WEEKLY:
        iso_year, iso_week, _ = on_date.isocalendar()
        return f"{iso_year:04d}-W{iso_week:02d}"
    if cadence == RecurringInvoiceSchedule.Cadence.QUARTERLY:
        return f"{on_date.year:04d}-Q{(on_date.month - 1) // 3 + 1}"
    if cadence == RecurringInvoiceSchedule.Cadence.HALF_YEARLY:
        return f"{on_date.year:04d}-H{1 if on_date.month <= 6 else 2}"
    if cadence == RecurringInvoiceSchedule.Cadence.ANNUALLY:
        return f"{on_date.year:04d}"
    return f"{on_date.year:04d}-{on_date.month:02d}"


def advance_next_run(dt: datetime, cadence: str, anchor_day: int | None = None) -> datetime:
    if cadence == RecurringInvoiceSchedule.Cadence.WEEKLY:
        return dt + timedelta(weeks=1)
    step = _MONTH_STEPS.get(cadence, 1)
    months = dt.month - 1 + step
    year = dt.year + months // 12
    month = months % 12 + 1
    # B2-009: clamp the *anchor* day to the target month, not the last
    # already-clamped date, so a 29-31 schedule doesn't walk backward forever.
    target = int(anchor_day) if anchor_day else dt.day
    day = min(target, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def next_future_run(schedule: RecurringInvoiceSchedule, now=None) -> datetime:
    """First occurrence of the schedule's cadence after ``now`` (used when resuming)."""
    now = now or timezone.now()
    nxt = schedule.next_run_at
    for _ in range(600):
        if nxt > now:
            break
        nxt = advance_next_run(nxt, schedule.cadence, schedule.anchor_day)
    return nxt


def period_is_locked(company, on_date: date) -> bool:
    period = f"{on_date.year:04d}-{on_date.month:02d}"
    if GstReturnPeriod.objects.filter(
        company=company,
        period=period,
        status__in=(GstReturnPeriod.Status.SOFT_CLOSED, GstReturnPeriod.Status.CLOSED),
    ).exists():
        return True
    return AccountingPeriod.objects.filter(
        company=company,
        start_date__lte=on_date,
        end_date__gte=on_date,
        status__in=(AccountingPeriod.Status.SOFT_CLOSED, AccountingPeriod.Status.CLOSED),
    ).exists()


def _template_items(company, template) -> list[dict]:
    if isinstance(template, list):
        raw_items = template
    else:
        raw_items = (template or {}).get("items") or []
    if not raw_items:
        raise BusinessRuleError("Recurring schedule line template must include items.")
    items = []
    for line in raw_items:
        product_id = line.get("product") or line.get("productId") or line.get("product_id")
        if not product_id:
            raise BusinessRuleError("Each template line needs a product.")
        try:
            product = Product.objects.get(pk=int(product_id), company=company)
        except (Product.DoesNotExist, TypeError, ValueError) as exc:
            raise BusinessRuleError("Template product is invalid for this company.") from exc
        item = {
            "product": product,
            "quantity": Decimal(str(line.get("quantity") or 1)),
            "description": line.get("description") or "",
        }
        unit_price = line.get("unit_price", line.get("unitPrice", None))
        if unit_price is not None:
            item["unit_price"] = Decimal(str(unit_price))
        gst_rate = line.get("gst_rate", line.get("gstRate", None))
        if gst_rate is not None:
            item["gst_rate"] = Decimal(str(gst_rate))
        discount = line.get("discount_percent", line.get("discountPercent", None))
        if discount is not None:
            item["discount_percent"] = Decimal(str(discount))
        # B2-026: these were silently dropped even though SalesService
        # already accepts all three on every line (_build_items) -- the
        # template just never forwarded them.
        cess_rate = line.get("cess_rate", line.get("cessRate", None))
        if cess_rate is not None:
            item["cess_rate"] = Decimal(str(cess_rate))
        supply_nature = line.get("supply_nature", line.get("supplyNature", None))
        if supply_nature is not None:
            item["supply_nature"] = str(supply_nature).upper()
        inclusive = line.get("unit_price_inclusive", line.get("unitPriceInclusive", None))
        if inclusive is not None:
            item["unit_price_inclusive"] = Decimal(str(inclusive))
        items.append(item)
    return items


@dataclass
class GenerationResult:
    """Outcome of one generation attempt.

    ``run`` is the new run, or the existing one when the period was already
    generated (``created`` False, ``reason`` "duplicate"). ``run`` is None when
    nothing was generated; ``reason`` then says why (see REASON_MESSAGES).
    """

    run: RecurringInvoiceRun | None = None
    created: bool = False
    reason: str = ""


def _describe_error(exc: Exception) -> str:
    """Readable, code-prefixed text for a completion gate that rejected the invoice."""
    from core.exceptions import _plain_detail

    detail = getattr(exc, "detail", None)
    text = _plain_detail(detail) if detail is not None else str(exc)
    code = ""
    get_codes = getattr(exc, "get_codes", None)
    if callable(get_codes):
        codes = get_codes()
        if isinstance(codes, str):
            code = codes
        elif isinstance(codes, dict):
            code = str(codes.get("code") or "")
    if code and code not in {"business_rule_violation", "error", "invalid"}:
        text = f"{code}: {text}"
    return (text or exc.__class__.__name__)[:2000]


def _finish_term(schedule: RecurringInvoiceSchedule, on_date: date) -> str:
    """Deactivate a schedule whose term is over. Returns the reason, or "" if still running."""
    reason = ""
    if schedule.end_date and on_date > schedule.end_date:
        reason = "expired"
    elif schedule.max_occurrences and schedule.total_runs_count >= schedule.max_occurrences:
        reason = "limit_reached"
    if reason:
        schedule.is_active = False
        schedule.save(update_fields=["is_active", "updated_at"])
    return reason


CATCH_UP_DEFER = (
    "Left in Draft: this is a catch-up for an earlier period. Check it, then complete it by hand."
)
QUOTA_DEFER = (
    "Left in Draft: some of the plan's monthly completions are kept free for manual billing. "
    "Complete it by hand."
)


def _queue_einvoice(invoice: SalesInvoice) -> None:
    """Send a completed B2B invoice to the e-invoice portal when the company uses e-invoicing.

    Best effort and never raises: the portal submission runs after the invoice is saved, and a
    failure shows on the invoice (e-invoice status FAILED with its reason), as for a manual submit.
    """
    company = invoice.company
    if not getattr(company, "einvoice_enabled", False) or not (invoice.customer.gstin or "").strip():
        return
    try:
        from .einvoice_eway_actions import _assert_sandbox_gsp_allowed, _claim_einvoice_submit
        from .tasks import submit_einvoice_async

        _assert_sandbox_gsp_allowed(company)
        if _claim_einvoice_submit(invoice) != "claimed":
            return
        transaction.on_commit(
            lambda: submit_einvoice_async.delay(invoice.pk, None, company_id=company.pk)
        )
    except Exception:  # noqa: BLE001
        logger.exception("recurring: could not queue the e-invoice for invoice %s", invoice.pk)


def auto_complete_budget(company) -> int | None:
    """How many invoices the beat may still auto-complete this month, or None when unlimited.

    On a plan with a monthly completion limit, a tenth of it (at least one) is kept for
    people to bill by hand, so a busy schedule cannot use up the whole month.
    """
    from billing.quotas import _plan_for, monthly_complete_count

    plan = _plan_for(company)
    limit = int(getattr(plan, "monthly_complete_limit", 0) or 0) if plan is not None else 0
    if limit <= 0:
        return None
    reserve = max(1, limit // 10)
    return max(0, limit - monthly_complete_count(company) - reserve)


@transaction.atomic
def generate_for_schedule(
    schedule: RecurringInvoiceSchedule,
    *,
    run_date: date | None = None,
    user=None,
    manual: bool = False,
    defer_reason: str = "",
) -> GenerationResult:
    """Create one document for the period. Skips locked, duplicate and finished schedules.

    A non-empty ``defer_reason`` leaves an auto-complete invoice in DRAFT and stores that
    text as the explanation (back-dated catch-up periods, or a plan's reserved completions).
    """
    schedule = RecurringInvoiceSchedule.objects.select_for_update().get(pk=schedule.pk)
    if not schedule.is_active:
        return GenerationResult(reason="inactive")
    if run_date is not None:
        on_date = run_date
    elif schedule.next_run_at:
        nxt = schedule.next_run_at
        on_date = timezone.localtime(nxt).date() if timezone.is_aware(nxt) else nxt.date()
    else:
        on_date = timezone.localdate()

    key = period_key_for(schedule.cadence, on_date)
    existing = RecurringInvoiceRun.objects.filter(schedule=schedule, period_key=key).first()
    if existing is not None:
        return GenerationResult(run=existing, reason="duplicate")
    reason = _finish_term(schedule, on_date)
    if reason:
        return GenerationResult(reason=reason)
    if period_is_locked(schedule.company, on_date):
        return GenerationResult(reason="locked")

    items = _template_items(schedule.company, schedule.line_template)
    invoice = None
    sales_order = None
    delivery_challan = None
    completion_error = ""
    stop = getattr(schedule, "stop_stage", None) or RecurringInvoiceSchedule.StopStage.INVOICE

    if stop in (
        RecurringInvoiceSchedule.StopStage.SALES_ORDER,
        RecurringInvoiceSchedule.StopStage.DELIVERY_CHALLAN,
    ):
        from inventory.services import InventoryService
        from sales.models import SalesOrder
        from sales.notes_services import SalesNotesService

        sales_order = SalesOrder.objects.create(
            company=schedule.company,
            customer=schedule.customer,
            warehouse=InventoryService.default_warehouse(schedule.company),
            company_gstin=schedule.company_gstin,
            order_date=on_date,
            notes=schedule.notes or "",
            status=SalesOrder.Status.DRAFT,
            additional_charges=schedule.additional_charges,
            invoice_discount=schedule.invoice_discount,
            invoice_discount_mode=schedule.invoice_discount_mode,
            created_by=user,
            updated_by=user,
        )
        SalesNotesService.set_order_items(sales_order, items, user)
        if stop == RecurringInvoiceSchedule.StopStage.DELIVERY_CHALLAN:
            delivery_challan = SalesNotesService.convert_sales_order_to_challan(sales_order, user)
            if delivery_challan.status != delivery_challan.Status.DRAFT:
                raise BusinessRuleError("Recurring generator must leave delivery challans in DRAFT.")
    else:
        invoice = SalesInvoice.objects.create(
            company=schedule.company,
            customer=schedule.customer,
            company_gstin=schedule.company_gstin,
            invoice_date=on_date,
            notes=schedule.notes or "",
            status=SalesInvoice.Status.DRAFT,
            additional_charges=schedule.additional_charges,
            invoice_discount=schedule.invoice_discount,
            invoice_discount_mode=schedule.invoice_discount_mode,
            price_mode=schedule.price_mode,
            created_by=user,
            updated_by=user,
        )
        SalesService.set_items(invoice, items, user)
        invoice.refresh_from_db()
        if invoice.status != SalesInvoice.Status.DRAFT:
            raise BusinessRuleError("Recurring generator must leave invoices in DRAFT.")
        if schedule.auto_complete and defer_reason:
            completion_error = defer_reason
        elif schedule.auto_complete:
            # A completion-time gate (GST Guard, credit limit, plan quota, stock,
            # below-cost ...) must not roll back the DRAFT invoice/run just
            # created -- otherwise this schedule would silently produce nothing,
            # forever, on every tick that hits the same gate. Isolate the attempt
            # in a savepoint so a failure leaves the invoice as a normal DRAFT to
            # fix by hand, and keep the reason on the run so the owner can see it.
            try:
                with transaction.atomic():
                    SalesService.complete(invoice, user)
            except Exception as exc:  # noqa: BLE001
                completion_error = _describe_error(exc)
                logger.warning(
                    "recurring: auto_complete failed for schedule %s; leaving invoice %s in DRAFT (%s)",
                    schedule.pk, invoice.pk, completion_error, exc_info=True,
                )
                invoice.refresh_from_db()
            else:
                invoice.refresh_from_db()
                _queue_einvoice(invoice)

    run = RecurringInvoiceRun.objects.create(
        company=schedule.company,
        schedule=schedule,
        period_key=key,
        invoice=invoice,
        sales_order=sales_order,
        delivery_challan=delivery_challan,
        completion_error=completion_error,
        is_manual=manual,
    )
    schedule.total_runs_count = (schedule.total_runs_count or 0) + 1
    update_fields = ["total_runs_count", "updated_at"]
    nxt = schedule.next_run_at
    if nxt.date() <= on_date:
        schedule.next_run_at = advance_next_run(nxt, schedule.cadence, schedule.anchor_day)
        update_fields.append("next_run_at")
    # Nothing left to generate: switch the schedule off now so it reads as finished.
    finished = bool(schedule.max_occurrences and schedule.total_runs_count >= schedule.max_occurrences)
    if schedule.end_date:
        following = schedule.next_run_at
        following_date = (
            timezone.localtime(following).date() if timezone.is_aware(following) else following.date()
        )
        finished = finished or following_date > schedule.end_date
    if finished:
        schedule.is_active = False
        update_fields.append("is_active")
    schedule.save(update_fields=update_fields)

    if not manual:
        from core.services.audit import AuditService

        AuditService.log(
            company=schedule.company,
            user=user,
            action="RECURRING_RUN",
            entity_type="RecurringInvoiceSchedule",
            entity_id=schedule.pk,
            metadata={"run_id": run.pk, "period_key": key, "completion_error": completion_error or None},
        )
    return GenerationResult(run=run, created=True)


def generate_draft_for_schedule(schedule: RecurringInvoiceSchedule, *, run_date: date | None = None, user=None):
    """Create one document for the period and return its run (None if nothing was generated)."""
    return generate_for_schedule(schedule, run_date=run_date, user=user).run


def _notify_owner(company, *, subject: str, body: str) -> None:
    """Email the first owner and leave an in-app notice. Never raises."""
    try:
        from accounts.models import CompanyUser
        from core.models import Notification
        from core.services.notifications import NotificationService

        owner = (
            CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER)
            .select_related("user")
            .first()
        )
        recipient = (owner.user.email if owner and owner.user else "") or (company.email or "")
        NotificationService.send(
            company=company, channel=Notification.Channel.IN_APP,
            recipient=recipient or str(company.pk), subject=subject, body=body,
        )
        if recipient:
            NotificationService.send(
                company=company, channel=Notification.Channel.EMAIL,
                recipient=recipient, subject=subject, body=body,
            )
    except Exception:  # noqa: BLE001
        logger.exception("recurring: could not notify the owner of company %s", company.pk)


def _set_last_error(schedule: RecurringInvoiceSchedule, message: str) -> None:
    """Record why generation is stuck; tell the owner only when the reason changes."""
    message = (message or "generation_failed")[:2000]
    changed = schedule.last_error != message
    schedule.last_error = message
    schedule.save(update_fields=["last_error", "updated_at"])
    if changed:
        _notify_owner(
            schedule.company,
            subject="Recurring schedule needs attention",
            body=(
                f"Recurring schedule #{schedule.pk} for {schedule.customer.name} could not run: "
                f"{message}. It will try again automatically."
            ),
        )


def process_due_schedules(*, now=None):
    from core.rls import iter_company_ids, set_rls_company

    now = now or timezone.now()
    created = 0
    skipped_locked = 0
    skipped_duplicate = 0
    skipped_error = 0
    try:
        for cid in iter_company_ids():
            set_rls_company(cid)
            created, skipped_locked, skipped_duplicate, skipped_error = _process_company_schedules(
                cid, now,
                created=created,
                skipped_locked=skipped_locked,
                skipped_duplicate=skipped_duplicate,
                skipped_error=skipped_error,
            )
    finally:
        set_rls_company(None)
    return {
        "created": created,
        "skipped_locked": skipped_locked,
        "skipped_duplicate": skipped_duplicate,
        "skipped_error": skipped_error,
    }


def _process_company_schedules(company_id, now, *, created, skipped_locked, skipped_duplicate, skipped_error):
    from accounts.models import Company

    company = Company.objects.filter(pk=company_id).first()
    # A one-element list so each schedule's loop spends from the same company-wide allowance.
    budget = [auto_complete_budget(company)] if company is not None else [None]
    for schedule in RecurringInvoiceSchedule.objects.filter(
        company_id=company_id, is_active=True, next_run_at__lte=now,
        # A blocked or archived customer gets no new drafts; the schedule resumes when they are active again.
        customer__status="ACTIVE",
    ).select_related("company", "customer", "company_gstin"):
        try:
            _created, _locked, _dup = _process_one_schedule(schedule, now=now, budget=budget)
            created += _created
            skipped_locked += _locked
            skipped_duplicate += _dup
        except Exception as exc:  # noqa: BLE001
            # CR-121: do NOT advance next_run_at on error — retry same period after fix.
            # (B2-006 still isolates poison schedules from aborting the whole batch.)
            logger.exception(
                "recurring: schedule %s failed; will retry same next_run_at", schedule.pk
            )
            skipped_error += 1
            try:
                _set_last_error(schedule, str(exc) or "generation_failed")
            except Exception:  # noqa: BLE001
                logger.exception(
                    "recurring: could not record last_error for schedule %s", schedule.pk
                )
    return created, skipped_locked, skipped_duplicate, skipped_error


MAX_CATCHUP_TICKS = 12  # CR-027: Cap catch-up loop per schedule run to prevent timeouts


def _digest_line(run: RecurringInvoiceRun) -> str:
    if run.invoice_id:
        inv = run.invoice
        label = f"Invoice {inv.number or '#' + str(inv.pk)} ({inv.status})"
    elif run.delivery_challan_id:
        label = f"Delivery challan #{run.delivery_challan_id}"
    else:
        label = f"Sales order #{run.sales_order_id}"
    line = f"- {label} for period {run.period_key}"
    if run.completion_error:
        line += f" — left in Draft, not completed: {run.completion_error}"
    return line


def _send_digest(schedule: RecurringInvoiceSchedule, runs: list[RecurringInvoiceRun]) -> None:
    """One notice per schedule per tick, however many periods were caught up."""
    if not runs:
        return
    lines = [_digest_line(r) for r in runs]
    completed = [r for r in runs if r.invoice_id and r.invoice.status == SalesInvoice.Status.COMPLETED]
    failed = [r for r in runs if r.completion_error]
    head = (
        f"{len(runs)} document(s) were generated from recurring schedule #{schedule.pk} "
        f"for {schedule.customer.name}."
    )
    if completed:
        head += f" {len(completed)} invoice(s) were completed automatically."
    if failed:
        head += " Some could not be completed automatically; review them."
    elif not completed:
        head += " They are drafts: complete them when ready."
    _notify_owner(
        schedule.company,
        subject="Recurring documents generated" if not failed else "Recurring documents need review",
        body=head + "\n" + "\n".join(lines),
    )


def _process_one_schedule(schedule, *, now, budget=None):
    """Run a single due schedule. Loops up to MAX_CATCHUP_TICKS while next_run_at <= now.
    Returns (created, skipped_locked, skipped_duplicate).
    """
    total_created = 0
    total_locked = 0
    total_dup = 0
    ticks = 0
    generated: list[RecurringInvoiceRun] = []
    auto_complete_allowed = True
    while schedule.next_run_at <= now and ticks < MAX_CATCHUP_TICKS:
        ticks += 1
        on_date = (
            timezone.localtime(schedule.next_run_at).date()
            if timezone.is_aware(schedule.next_run_at)
            else schedule.next_run_at.date()
        )
        key = period_key_for(schedule.cadence, on_date)
        if RecurringInvoiceRun.objects.filter(schedule=schedule, period_key=key).exists():
            schedule.next_run_at = advance_next_run(
                schedule.next_run_at, schedule.cadence, schedule.anchor_day
            )
            schedule.save(update_fields=["next_run_at", "updated_at"])
            total_dup += 1
            continue
        if period_is_locked(schedule.company, on_date):
            # CR-015: do not advance next_run_at — retry the same period_key after unlock.
            total_locked += 1
            _set_last_error(
                schedule,
                f"Accounting or GST period for {on_date:%d %b %Y} is closed; will retry after it is reopened.",
            )
            break
        # Only the first period of a catch-up may auto-complete, so a long outage cannot
        # finalize a dozen back-dated invoices (or use up the plan's monthly complete limit).
        defer = ""
        if not auto_complete_allowed:
            defer = CATCH_UP_DEFER
        elif budget is not None and budget[0] is not None and budget[0] <= 0:
            defer = QUOTA_DEFER
        result = generate_for_schedule(schedule, run_date=on_date, defer_reason=defer)
        schedule.refresh_from_db()
        run = result.run
        if run is None or not result.created:
            break
        auto_complete_allowed = False
        if (
            budget is not None and budget[0] is not None
            and run.invoice_id and run.invoice.status == SalesInvoice.Status.COMPLETED
        ):
            budget[0] -= 1
        if schedule.last_error:
            schedule.last_error = ""
            schedule.save(update_fields=["last_error", "updated_at"])
        generated.append(run)
        total_created += 1
    _send_digest(schedule, generated)
    return total_created, total_locked, total_dup
