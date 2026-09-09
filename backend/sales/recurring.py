"""BB-000669: recurring sales invoice schedules — draft-only generation."""

from __future__ import annotations

import logging
from calendar import monthrange
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


def period_key_for(cadence: str, on_date: date) -> str:
    if cadence == RecurringInvoiceSchedule.Cadence.WEEKLY:
        iso_year, iso_week, _ = on_date.isocalendar()
        return f"{iso_year:04d}-W{iso_week:02d}"
    return f"{on_date.year:04d}-{on_date.month:02d}"


def advance_next_run(dt: datetime, cadence: str, anchor_day: int | None = None) -> datetime:
    if cadence == RecurringInvoiceSchedule.Cadence.WEEKLY:
        return dt + timedelta(weeks=1)
    month = dt.month + 1
    year = dt.year + (1 if month > 12 else 0)
    month = month if month <= 12 else 1
    # B2-009: clamp the *anchor* day to the target month, not the last
    # already-clamped date, so a 29-31 schedule doesn't walk backward forever.
    target = int(anchor_day) if anchor_day else dt.day
    day = min(target, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


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


@transaction.atomic
def generate_draft_for_schedule(schedule: RecurringInvoiceSchedule, *, run_date: date | None = None, user=None):
    """Create one DRAFT invoice for the period. Never completes. Skip locked/duplicate."""
    schedule = RecurringInvoiceSchedule.objects.select_for_update().get(pk=schedule.pk)
    if not schedule.is_active:
        return None
    if run_date is not None:
        on_date = run_date
    elif schedule.next_run_at:
        nxt = schedule.next_run_at
        on_date = timezone.localtime(nxt).date() if timezone.is_aware(nxt) else nxt.date()
    else:
        on_date = timezone.localdate()

    key = period_key_for(schedule.cadence, on_date)
    if RecurringInvoiceRun.objects.filter(schedule=schedule, period_key=key).exists():
        return RecurringInvoiceRun.objects.filter(schedule=schedule, period_key=key).first()
    if period_is_locked(schedule.company, on_date):
        return None

    invoice = SalesInvoice.objects.create(
        company=schedule.company,
        customer=schedule.customer,
        company_gstin=schedule.company_gstin,
        invoice_date=on_date,
        notes=schedule.notes or "",
        status=SalesInvoice.Status.DRAFT,
        # B2-026: carry the schedule's header-level charges/discount/price-mode
        # through to every generated draft, same as a one-off invoice would have.
        additional_charges=schedule.additional_charges,
        invoice_discount=schedule.invoice_discount,
        invoice_discount_mode=schedule.invoice_discount_mode,
        price_mode=schedule.price_mode,
        created_by=user,
        updated_by=user,
    )
    SalesService.set_items(invoice, _template_items(schedule.company, schedule.line_template), user)
    invoice.refresh_from_db()
    if invoice.status != SalesInvoice.Status.DRAFT:
        raise BusinessRuleError("Recurring generator must leave invoices in DRAFT.")

    run = RecurringInvoiceRun.objects.create(
        company=schedule.company,
        schedule=schedule,
        period_key=key,
        invoice=invoice,
    )
    nxt = schedule.next_run_at
    if nxt.date() <= on_date:
        schedule.next_run_at = advance_next_run(nxt, schedule.cadence, schedule.anchor_day)
        schedule.save(update_fields=["next_run_at", "updated_at"])
    return run


def process_due_schedules(*, now=None):
    now = now or timezone.now()
    created = 0
    skipped_locked = 0
    skipped_duplicate = 0
    skipped_error = 0
    for schedule in RecurringInvoiceSchedule.objects.filter(is_active=True, next_run_at__lte=now).select_related(
        "company", "customer", "company_gstin",
    ):
        try:
            _created, _locked, _dup = _process_one_schedule(schedule, now=now)
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
                if hasattr(schedule, "last_error"):
                    schedule.last_error = str(exc)[:2000] or "generation_failed"
                    schedule.save(update_fields=["last_error", "updated_at"])
            except Exception:  # noqa: BLE001
                logger.exception(
                    "recurring: could not record last_error for schedule %s", schedule.pk
                )
    return {
        "created": created,
        "skipped_locked": skipped_locked,
        "skipped_duplicate": skipped_duplicate,
        "skipped_error": skipped_error,
    }


MAX_CATCHUP_TICKS = 12  # CR-027: Cap catch-up loop per schedule run to prevent timeouts


def _process_one_schedule(schedule, *, now):
    """Run a single due schedule. Loops up to MAX_CATCHUP_TICKS while next_run_at <= now.
    Returns (created, skipped_locked, skipped_duplicate).
    """
    total_created = 0
    total_locked = 0
    total_dup = 0
    ticks = 0
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
            break
        run = generate_draft_for_schedule(schedule, run_date=on_date)
        schedule.refresh_from_db()
        if run is not None and run.invoice_id:
            if getattr(schedule, "last_error", None):
                schedule.last_error = ""
                schedule.save(update_fields=["last_error", "updated_at"])
            inv = run.invoice
            # M1-037/S101: was a bare `assert` — silently stripped under `python -O`,
            # so this invariant would go unchecked in an optimized deployment. The
            # per-schedule try/except in the caller already handles this raising.
            if inv.status != SalesInvoice.Status.DRAFT:
                raise AssertionError(
                    f"Recurring-generated invoice {inv.pk} expected DRAFT, got {inv.status!r}"
                )
            from accounts.models import CompanyUser
            from core.models import Notification
            from core.services.notifications import NotificationService

            owner = (
                CompanyUser.objects.filter(
                    company=schedule.company, role=CompanyUser.Role.OWNER
                )
                .select_related("user")
                .first()
            )
            recipient = (owner.user.email if owner and owner.user else "") or (schedule.company.email or "")
            if recipient:
                NotificationService.send(
                    company=schedule.company,
                    channel=Notification.Channel.EMAIL,
                    recipient=recipient,
                    subject="Recurring invoice draft ready",
                    body=(
                        f"Draft invoice #{inv.pk} was generated from a recurring schedule. "
                        "Complete it when ready — BizBoard never auto-completes recurring invoices."
                    ),
                )
            total_created += 1
        else:
            break
    return total_created, total_locked, total_dup
