"""Shop floor: routing, job cards, time, downtime, load, maintenance (MFG-33..36)."""

from accounting.books import posts_to_ledger
from collections import defaultdict
import functools
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.services.audit import AuditService
from core.services.feature_flags import flag_enabled

from manufacturing.models import (
    DowntimeEvent, DowntimeReason, JobCard, Machine, MaintenanceLog, MaintenancePlan, Operator, RoutingOperation,
    TimeLog, WorkCentre, WorkOrder,
)

from . import bom as bom_svc
from .common import ZERO, d, money, rule

TOKEN_SALT = "bizboard.mfg.shopfloor"
TOKEN_MAX_AGE = 12 * 3600
MAX_PIN_TRIES = 5
LOCK_MINUTES = 15


def _minutes(a, b) -> Decimal:
    return (Decimal((b - a).total_seconds()) / Decimal(60)).quantize(Decimal("0.01"))


# --- routing -----------------------------------------------------------------------------------

@transaction.atomic
def set_routing(bom, ops, user):
    """Replace a BOM revision's routing. A revision a work order has used is read-only."""
    bom_svc.assert_editable(bom)
    seen = set()
    rows = []
    for i, op in enumerate(ops):
        wc = WorkCentre.objects.filter(pk=getattr(op.get("work_centre"), "pk", op.get("work_centre")), company=bom.company).first()
        if wc is None:
            raise rule("Choose a work centre for every operation.", "MFG_BAD_REFERENCE")
        seq = int(op.get("sequence") or (i + 1) * 10)
        if seq in seen:
            raise rule("Two operations have the same sequence number.", "MFG_BAD_SEQUENCE")
        seen.add(seq)
        rows.append(RoutingOperation(
            bom=bom, company=bom.company, sequence=seq, name=(op.get("name") or wc.name)[:120], work_centre=wc,
            setup_minutes=d(op.get("setup_minutes")), run_minutes_per_unit=d(op.get("run_minutes_per_unit")),
            is_subcontract=bool(op.get("is_subcontract")), subcontract_supplier_id=op.get("subcontract_supplier") or None,
            notes=(op.get("notes") or "")[:255],
        ))
    bom.operations.all().delete()
    RoutingOperation.objects.bulk_create(rows)
    return list(bom.operations.all())


@transaction.atomic
def create_job_cards(wo, user):
    """One job card per routing operation, sized to the order. Safe to call twice."""
    if wo.bom_id is None or wo.job_cards.exists():
        return list(wo.job_cards.all())
    cards = []
    for op in wo.bom.operations.select_related("work_centre"):
        cards.append(JobCard(
            company=wo.company, work_order=wo, operation=op, sequence=op.sequence, name=op.name,
            work_centre=op.work_centre, qty_planned=wo.qty,
            planned_minutes=d(op.setup_minutes) + d(op.run_minutes_per_unit) * d(wo.qty),
            is_subcontract=op.is_subcontract, created_by=user, updated_by=user,
        ))
    JobCard.objects.bulk_create(cards)
    return list(wo.job_cards.all())


# --- running a card ----------------------------------------------------------------------------

def when(at=None):
    """The time an action happened. A tablet that was offline sends the moment of the tap; anything older than a
    day or in the future is not believed and the server's clock is used instead."""
    now = timezone.now()
    if at is None:
        return now
    if timezone.is_naive(at):
        at = timezone.make_aware(at)
    return at if now - timedelta(hours=24) <= at <= now + timedelta(minutes=1) else now


def _lock(card):
    card = JobCard.objects.select_for_update().select_related("work_order", "work_centre").get(pk=card.pk)
    if card.work_order.status not in (WorkOrder.Status.RELEASED, WorkOrder.Status.IN_PROGRESS):
        raise rule("The work order is not running.", "MFG_BAD_WO_STATUS")
    return card


def _open_log(card):
    return card.time_logs.filter(ended_at__isnull=True).order_by("-id").first()


@transaction.atomic
def start_card(card, *, user=None, operator=None, at=None) -> JobCard:
    card = _lock(card)
    if card.status == JobCard.Status.DONE or card.status == JobCard.Status.CANCELLED:
        raise rule("This job card is finished.", "MFG_CARD_DONE")
    if card.is_subcontract:
        raise rule("This operation is done by a job worker. Record it on the job work receipt.", "MFG_CARD_SUBCONTRACT")
    if _open_log(card) is not None:
        return card
    now = when(at)
    TimeLog.objects.create(job_card=card, company=card.company, user=user, operator=operator, started_at=now)
    card.status = JobCard.Status.IN_PROGRESS
    card.started_at = card.started_at or now
    card.save(update_fields=["status", "started_at", "updated_at"])
    if card.work_order.status == WorkOrder.Status.RELEASED:
        WorkOrder.objects.filter(pk=card.work_order_id).update(status=WorkOrder.Status.IN_PROGRESS)
    return card


def _close_log(card, now):
    log = _open_log(card)
    if log is None:
        return ZERO
    now = max(now, log.started_at)
    log.ended_at = now
    log.minutes = _minutes(log.started_at, now)
    log.save(update_fields=["ended_at", "minutes"])
    card.minutes_worked = d(card.minutes_worked) + log.minutes
    return log.minutes


@transaction.atomic
def pause_card(card, *, user=None, operator=None, at=None) -> JobCard:
    card = _lock(card)
    if card.status != JobCard.Status.IN_PROGRESS:
        raise rule("Only a running job card can be paused.", "MFG_CARD_NOT_RUNNING")
    _close_log(card, when(at))
    card.status = JobCard.Status.PAUSED
    card.save(update_fields=["minutes_worked", "status", "updated_at"])
    return card


@transaction.atomic
def report_card(card, *, qty_good=0, qty_rejected=0, user=None, operator=None) -> JobCard:
    """Add what has been made so far (partial completion). Does not stop the clock."""
    card = _lock(card)
    if card.status in (JobCard.Status.DONE, JobCard.Status.CANCELLED):
        raise rule("This job card is finished.", "MFG_CARD_DONE")
    good, bad = d(qty_good), d(qty_rejected)
    if good < 0 or bad < 0:
        raise rule("Quantities cannot be negative.", "MFG_BAD_QTY")
    card.qty_good = d(card.qty_good) + good
    card.qty_rejected = d(card.qty_rejected) + bad
    card.save(update_fields=["qty_good", "qty_rejected", "updated_at"])
    return card


@transaction.atomic
def finish_card(card, *, qty_good=0, qty_rejected=0, user=None, operator=None, at=None) -> JobCard:
    """Stop the clock, close the card and add its labour, machine and overhead cost to the order."""
    card = _lock(card)
    if card.status in (JobCard.Status.DONE, JobCard.Status.CANCELLED):
        raise rule("This job card is finished.", "MFG_CARD_DONE")
    now = when(at)
    _close_log(card, now)
    card.qty_good = d(card.qty_good) + d(qty_good)
    card.qty_rejected = d(card.qty_rejected) + d(qty_rejected)
    hours = d(card.minutes_worked) / Decimal(60)
    wc = card.work_centre
    card.labour_cost = money(hours * d(wc.labour_rate))
    card.machine_cost = money(hours * d(wc.machine_rate))
    card.overhead_cost = money(hours * d(wc.overhead_rate))
    card.status = JobCard.Status.DONE
    card.finished_at = now
    card.save()
    # Hours on the machine drive hour-based maintenance.
    machine = Machine.objects.filter(company=card.company, work_centre=wc, is_active=True).order_by("id").first()
    if machine is not None and hours > 0:
        Machine.objects.filter(pk=machine.pk).update(run_hours=d(machine.run_hours) + hours.quantize(Decimal("0.01")))
    _absorb(card, user)
    AuditService.log(
        action="mfg.jobcard.finished", company=card.company, user=user, entity_type="JobCard",
        entity_id=str(card.pk), description=f"{card.name}: {card.minutes_worked} min, {card.qty_good} good",
    )
    return card


def _absorb(card, user):
    """Add the card's conversion cost to the work order. Only with the costing flag on."""
    total = d(card.labour_cost) + d(card.machine_cost) + d(card.overhead_cost)
    if total <= 0 or not flag_enabled(card.company, "MFG_COSTING_GL"):
        return
    wo = WorkOrder.objects.select_for_update().get(pk=card.work_order_id)
    wo.cost_absorbed = money(d(wo.cost_absorbed) + total)
    wo.save(update_fields=["cost_absorbed", "updated_at"])
    JobCard.objects.filter(pk=card.pk).update(absorbed=True)
    card.absorbed = True
    if posts_to_ledger(card.company):
        from accounting.services import PostingService

        PostingService.post_mfg_absorption(
            company=card.company, source_type="MFG_JOBCARD", source_id=card.pk, purpose="DONE",
            entry_date=timezone.localdate(), user=user, narration=f"{card.name} on {wo.number or wo.pk}",
            credits=[("5430", card.labour_cost), ("5440", d(card.machine_cost) + d(card.overhead_cost))],
        )


@transaction.atomic
def reopen_card(card, user) -> JobCard:
    """Take a finished card back to paused, and take its cost back off the order."""
    card = JobCard.objects.select_for_update().select_related("work_order").get(pk=card.pk)
    if card.status != JobCard.Status.DONE:
        raise rule("Only a finished job card can be reopened.", "MFG_CARD_NOT_DONE")
    wo = WorkOrder.objects.select_for_update().get(pk=card.work_order_id)
    if wo.status not in (WorkOrder.Status.RELEASED, WorkOrder.Status.IN_PROGRESS):
        raise rule("Reopen the work order first.", "MFG_REVERSAL_ORDER")
    if card.absorbed:
        total = d(card.labour_cost) + d(card.machine_cost) + d(card.overhead_cost)
        if d(wo.wip_value) - total < Decimal("-0.005"):
            raise rule("Finished goods have already taken this cost. Reverse the receipts first.", "MFG_REVERSAL_ORDER")
        wo.cost_absorbed = money(d(wo.cost_absorbed) - total)
        wo.save(update_fields=["cost_absorbed", "updated_at"])
        if posts_to_ledger(card.company):
            from accounting.services import PostingService

            PostingService.reverse_mfg_document(company=card.company, source_type="MFG_JOBCARD", source_id=card.pk, user=user)
    card.status = JobCard.Status.PAUSED
    card.absorbed = False
    card.labour_cost = card.machine_cost = card.overhead_cost = ZERO
    card.finished_at = None
    card.save()
    return card


# --- downtime ------------------------------------------------------------------------------------

@transaction.atomic
def start_downtime(company, user, *, work_centre, reason, job_card=None, notes="", at=None) -> DowntimeEvent:
    if DowntimeEvent.objects.filter(company=company, work_centre=work_centre, ended_at__isnull=True).exists():
        raise rule("This work centre already has a stoppage open.", "MFG_DOWNTIME_OPEN")
    return DowntimeEvent.objects.create(
        company=company, work_centre=work_centre, reason=reason, job_card=job_card, started_at=when(at),
        notes=notes[:255], created_by=user, updated_by=user,
    )


@transaction.atomic
def end_downtime(event, user=None, at=None) -> DowntimeEvent:
    event = DowntimeEvent.objects.select_for_update().get(pk=event.pk)
    if event.ended_at is not None:
        raise rule("This stoppage has already ended.", "MFG_DOWNTIME_CLOSED")
    event.ended_at = max(when(at), event.started_at)
    event.minutes = _minutes(event.started_at, event.ended_at)
    event.save(update_fields=["ended_at", "minutes", "updated_at"])
    return event


# --- load and utilisation --------------------------------------------------------------------------

def load(company, start: date | None = None, days: int = 14):
    """Infinite-capacity load: each open card's planned minutes spread over the days to its order's due date.

    A work centre is flagged on a day when the load passes the hours it can work.
    """
    start = start or timezone.localdate()
    days = max(1, min(int(days), 90))
    end = start + timedelta(days=days - 1)
    grid = defaultdict(lambda: defaultdict(lambda: ZERO))
    centres = {wc.pk: wc for wc in WorkCentre.objects.filter(company=company, is_active=True)}
    cards = JobCard.objects.filter(
        company=company, status__in=["PLANNED", "IN_PROGRESS", "PAUSED"],
        work_order__status__in=["RELEASED", "IN_PROGRESS"],
    ).select_related("work_order")
    for card in cards:
        left = max(ZERO, d(card.planned_minutes) - d(card.minutes_worked))
        if left <= 0:
            continue
        first = max(start, card.work_order.planned_start or start)
        last = card.work_order.due_date or end
        last = max(first, min(last, end + timedelta(days=60)))
        working = [first + timedelta(days=i) for i in range((last - first).days + 1) if (first + timedelta(days=i)).weekday() != 6]
        if not working:
            working = [first]
        share = left / len(working)
        for day in working:
            if start <= day <= end:
                grid[card.work_centre_id][day] += share
    out = []
    for wc_id, wc in centres.items():
        cap = d(wc.hours_per_day) * 60
        rows = []
        for i in range(days):
            day = start + timedelta(days=i)
            used = grid[wc_id].get(day, ZERO)
            rows.append({"date": day, "minutes": used.quantize(Decimal("0.1")), "capacity": cap, "overloaded": used > cap and cap > 0})
        out.append({"work_centre": wc_id, "code": wc.code, "name": wc.name, "days": rows,
                    "overloaded_days": sum(1 for r in rows if r["overloaded"])})
    return {"from": start, "to": end, "work_centres": out}


def utilisation(company, date_from: date, date_to: date):
    """Per work centre: hours worked against hours available, stoppages, good output per hour."""
    days = max(1, (date_to - date_from).days + 1)
    out = []
    for wc in WorkCentre.objects.filter(company=company, is_active=True):
        logs = TimeLog.objects.filter(
            job_card__work_centre=wc, started_at__date__gte=date_from, started_at__date__lte=date_to,
        ).aggregate(m=Sum("minutes"))["m"]
        down = DowntimeEvent.objects.filter(
            work_centre=wc, started_at__date__gte=date_from, started_at__date__lte=date_to,
        ).aggregate(m=Sum("minutes"))["m"]
        good = JobCard.objects.filter(
            work_centre=wc, finished_at__date__gte=date_from, finished_at__date__lte=date_to,
        ).aggregate(g=Sum("qty_good"), r=Sum("qty_rejected"))
        worked = d(logs)
        available = d(wc.hours_per_day) * 60 * days
        out.append({
            "work_centre": wc.pk, "code": wc.code, "name": wc.name, "worked_minutes": worked,
            "available_minutes": available,
            "utilisation_pct": (worked * 100 / available).quantize(Decimal("0.1")) if available else None,
            "downtime_minutes": d(down), "good": d(good["g"]), "rejected": d(good["r"]),
            "good_per_hour": (d(good["g"]) / (worked / 60)).quantize(Decimal("0.01")) if worked else None,
        })
    return out


def labour_productivity(company, date_from: date, date_to: date):
    """Good output and hours per operator or user from the time logs."""
    rows = defaultdict(lambda: {"minutes": ZERO, "cards": set()})
    for log in TimeLog.objects.filter(
        company=company, started_at__date__gte=date_from, started_at__date__lte=date_to,
    ).select_related("operator", "user", "job_card"):
        who = log.operator.name if log.operator_id else (log.user.full_name if log.user_id else "(unknown)")
        rows[who]["minutes"] += d(log.minutes)
        rows[who]["cards"].add(log.job_card_id)
    return [{"who": k, "hours": (v["minutes"] / 60).quantize(Decimal("0.01")), "cards": len(v["cards"])} for k, v in sorted(rows.items())]


# --- maintenance ---------------------------------------------------------------------------------

def maintenance_due(company, today: date | None = None):
    today = today or timezone.localdate()
    out = []
    for plan in MaintenancePlan.objects.filter(company=company, is_active=True, machine__is_active=True).select_related("machine"):
        due_on = (plan.last_done_on + timedelta(days=plan.interval_days)) if plan.interval_days and plan.last_done_on else None
        if plan.interval_days and plan.last_done_on is None:
            due_on = today
        hours_left = None
        if plan.interval_hours:
            hours_left = d(plan.last_done_hours) + plan.interval_hours - d(plan.machine.run_hours)
        overdue = (due_on is not None and due_on <= today) or (hours_left is not None and hours_left <= 0)
        out.append({
            "plan": plan.pk, "machine": plan.machine.name, "name": plan.name, "due_on": due_on,
            "hours_left": hours_left, "overdue": overdue,
        })
    return sorted(out, key=lambda r: (not r["overdue"], r["due_on"] or date.max))


@transaction.atomic
def complete_preventive(plan, user, *, done_on=None, cost=0, notes="") -> MaintenanceLog:
    plan = MaintenancePlan.objects.select_for_update().select_related("machine").get(pk=plan.pk)
    done_on = done_on or timezone.localdate()
    log = MaintenanceLog.objects.create(
        company=plan.company, machine=plan.machine, plan=plan, kind=MaintenanceLog.Kind.PREVENTIVE,
        reported_at=timezone.make_aware(datetime.combine(done_on, datetime.min.time())),
        resolved_at=timezone.now(), description=(notes or plan.name)[:500], cost=d(cost), created_by=user, updated_by=user,
    )
    plan.last_done_on = done_on
    plan.last_done_hours = d(plan.machine.run_hours)
    plan.save(update_fields=["last_done_on", "last_done_hours", "updated_at"])
    return log


@transaction.atomic
def report_breakdown(company, user, *, machine, description) -> MaintenanceLog:
    if MaintenanceLog.objects.filter(machine=machine, kind="BREAKDOWN", resolved_at__isnull=True).exists():
        raise rule("This machine already has an open breakdown.", "MFG_BREAKDOWN_OPEN")
    log = MaintenanceLog.objects.create(
        company=company, machine=machine, kind=MaintenanceLog.Kind.BREAKDOWN, reported_at=timezone.now(),
        description=description[:500], created_by=user, updated_by=user,
    )
    if machine.work_centre_id:
        reason, _ = DowntimeReason.objects.get_or_create(company=company, code="BREAKDOWN", defaults={"name": "Breakdown"})
        try:
            start_downtime(company, user, work_centre=machine.work_centre, reason=reason, notes=f"{machine.name} breakdown")
        except Exception:     # a stoppage is already open on the centre: keep the breakdown record
            pass
    return log


@transaction.atomic
def resolve_breakdown(log, user, *, cost=0, notes="") -> MaintenanceLog:
    log = MaintenanceLog.objects.select_for_update().select_related("machine").get(pk=log.pk)
    if log.kind != MaintenanceLog.Kind.BREAKDOWN or log.resolved_at is not None:
        raise rule("This breakdown is already resolved.", "MFG_BREAKDOWN_CLOSED")
    now = timezone.now()
    log.resolved_at = now
    log.cost = d(cost)
    log.downtime_minutes = _minutes(log.reported_at, now)
    if notes:
        log.description = f"{log.description} | {notes}"[:500]
    log.save()
    if log.machine.work_centre_id:
        ev = DowntimeEvent.objects.filter(work_centre_id=log.machine.work_centre_id, ended_at__isnull=True).first()
        if ev is not None:
            end_downtime(ev, user)
    return log


# --- tablet operators (PIN sign-in) -----------------------------------------------------------------

def create_operator(company, user, *, code, name, pin) -> Operator:
    pin = str(pin or "")
    if not (4 <= len(pin) <= 8 and pin.isdigit()):
        raise rule("A PIN is 4 to 8 digits.", "MFG_BAD_PIN")
    if Operator.objects.filter(company=company, code__iexact=code).exists():
        raise rule("That operator code is already used.", "MFG_OPERATOR_EXISTS")
    return Operator.objects.create(
        company=company, code=code.strip()[:24], name=name.strip()[:120], pin_hash=make_password(pin),
        created_by=user, updated_by=user,
    )


def set_pin(operator, pin):
    pin = str(pin or "")
    if not (4 <= len(pin) <= 8 and pin.isdigit()):
        raise rule("A PIN is 4 to 8 digits.", "MFG_BAD_PIN")
    operator.pin_hash = make_password(pin)
    operator.failed_attempts = 0
    operator.locked_until = None
    operator.save(update_fields=["pin_hash", "failed_attempts", "locked_until", "updated_at"])


@functools.lru_cache(maxsize=1)
def _decoy_hash() -> str:
    return make_password("0000")


def operator_login(company_id, code, pin):
    """Check a code and PIN. Five wrong PINs lock that operator for 15 minutes. Returns a signed token."""
    # The tablet has no account, so the request carries no company; name it for the row-level security session
    # (a no-op unless that is on). A wrong company simply finds no operator.
    from core.rls import set_rls_company

    try:
        set_rls_company(int(company_id))
    except (TypeError, ValueError):
        raise rule("Wrong code or PIN.", "MFG_LOGIN_FAILED") from None
    found = Operator.objects.filter(company_id=company_id, code__iexact=(code or "").strip(), is_active=True).first()
    generic = rule("Wrong code or PIN.", "MFG_LOGIN_FAILED")
    if found is None:
        check_password(str(pin or ""), _decoy_hash())      # the same time as a real check, so a code cannot be guessed by speed
        raise generic
    outcome = "ok"
    with transaction.atomic():
        op = Operator.objects.select_for_update().get(pk=found.pk)
        now = timezone.now()
        if op.locked_until and op.locked_until > now:
            outcome = "locked"
        elif not check_password(str(pin or ""), op.pin_hash):
            op.failed_attempts += 1
            if op.failed_attempts >= MAX_PIN_TRIES:
                op.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                op.failed_attempts = 0
            op.save(update_fields=["failed_attempts", "locked_until", "updated_at"])
            outcome = "wrong"
        elif op.failed_attempts:
            op.failed_attempts = 0
            op.save(update_fields=["failed_attempts", "updated_at"])
    # Raised after the block, so the count above is kept and not rolled back with the refusal.
    if outcome == "locked":
        raise rule("Too many wrong PINs. Try again in a few minutes, or ask a supervisor.", "MFG_LOGIN_LOCKED")
    if outcome == "wrong":
        raise generic
    return signing.dumps({"op": op.pk, "co": op.company_id}, salt=TOKEN_SALT), op


def operator_from_token(token):
    """The operator a tablet token belongs to, or None (bad, expired, or the operator was switched off)."""
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    from core.rls import set_rls_company

    set_rls_company(data.get("co"))          # the signed token names the company; every later query stays inside it
    return Operator.objects.filter(pk=data.get("op"), company_id=data.get("co"), is_active=True).first()
