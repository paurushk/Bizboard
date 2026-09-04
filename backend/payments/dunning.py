"""A-07: Owner-opt-in AR dunning cadence (WhatsApp Cloud then SMS). Default off."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import IntegrityError
from django.utils import timezone

IST = ZoneInfo("Asia/Kolkata")
DEFAULT_DUNNING_DAYS = (3, 7, 14)

NEXT_STEP_FOLLOW_UP = "follow_up"
NEXT_STEP_SEND_STATEMENT = "send_statement"
NEXT_STEP_SEND_LINK = "send_link"
NEXT_STEP_REDUCE_CREDIT = "reduce_credit"
NEXT_STEP_STOP_CREDIT = "stop_credit"


def _ist_now(now: datetime | None = None) -> datetime:
    dt = now or timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.astimezone(IST)


def _ist_today(now: datetime | None = None) -> date:
    return _ist_now(now).date()


def configured_days(company) -> list[int]:
    raw = getattr(company, "dunning_days", None) or []
    days = []
    for item in raw:
        try:
            n = int(item)
        except (TypeError, ValueError):
            continue
        if n >= 1:
            days.append(n)
    return sorted(set(days)) or list(DEFAULT_DUNNING_DAYS)


def in_quiet_hours(company, now: datetime | None = None) -> bool:
    local = _ist_now(now)
    start = int(getattr(company, "dunning_quiet_hours_start", 21) or 21) % 24
    end = int(getattr(company, "dunning_quiet_hours_end", 8) or 8) % 24
    hour = local.hour
    if start == end:
        return False
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


def is_paid_pending_books(invoice) -> bool:
    from payments.models import GatewayPayment, GatewayPaymentStatus

    return GatewayPayment.objects.filter(
        company_id=invoice.company_id,
        payment_link__sales_invoice=invoice,
        status=GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
    ).exists()


def _outstanding(invoice) -> Decimal:
    from ledgers.services import LedgerService

    return Decimal(str(LedgerService.sales_invoice_outstanding(invoice) or 0))


def _step_already_sent(invoice, bucket: int) -> bool:
    from payments.models import DunningReminder

    return DunningReminder.objects.filter(
        invoice=invoice, days_overdue=bucket, status=DunningReminder.Status.SENT
    ).exists()


def _next_due_bucket(days_overdue: int, buckets: list[int], invoice) -> int | None:
    """B4-026: the STRONGEST configured step warranted by the current age that
    is still unsent — so an invoice first picked up at 40 days overdue escalates
    straight to the "14 days" tier instead of getting three gentle nudges for
    3/7/14 spread over three days and then capping out."""
    for bucket in sorted(buckets, reverse=True):
        if days_overdue >= bucket and not _step_already_sent(invoice, bucket):
            return bucket
    return None


def _already_sent_today(invoice, sent_on: date) -> bool:
    from payments.models import DunningReminder

    # PAY-13: a SKIPPED row (missing phone earlier today) must not block a real
    # send once the number is fixed — only SENT/FAILED count as "handled today".
    return (
        DunningReminder.objects.filter(invoice=invoice, sent_on=sent_on)
        .exclude(status=DunningReminder.Status.SKIPPED)
        .exists()
    )


def _reminder_count(invoice) -> int:
    from payments.models import DunningReminder

    return DunningReminder.objects.filter(
        invoice=invoice, status=DunningReminder.Status.SENT
    ).count()


def eligible_invoices(company, *, as_of: date):
    from sales.models import SalesInvoice

    return (
        SalesInvoice.objects.filter(
            company=company,
            status=SalesInvoice.Status.COMPLETED,
            due_date__isnull=False,
            due_date__lt=as_of,
        )
        .select_related("customer", "company")
        .order_by("due_date", "id")
    )


def _record(invoice, *, sent_on, days_overdue, channel, status, error=""):
    from payments.models import DunningReminder

    # PAY-13: don't pile up SKIPPED rows for the same invoice/day — the unique
    # constraint no longer covers them, so de-dupe here instead.
    if status == DunningReminder.Status.SKIPPED and DunningReminder.objects.filter(
        invoice=invoice, sent_on=sent_on, status=DunningReminder.Status.SKIPPED
    ).exists():
        return None
    try:
        return DunningReminder.objects.create(
            company=invoice.company,
            invoice=invoice,
            customer=invoice.customer,
            sent_on=sent_on,
            days_overdue=days_overdue,
            channel=channel,
            status=status,
            error=(error or "")[:500],
        )
    except IntegrityError:
        return None


def _send_whatsapp(invoice, body) -> bool:
    from core.models import Notification
    from core.services.notifications import NotificationService
    from sales.whatsapp_send import allow_cloud_for_customer

    customer = invoice.customer
    phone = (customer.phone or "").strip()
    if not phone:
        return False
    if not allow_cloud_for_customer(customer):
        return False
    n = NotificationService.send(
        company=invoice.company,
        channel=Notification.Channel.WHATSAPP,
        recipient=phone,
        subject="payment_reminder",
        body=body,
        allow_cloud=True,
    )
    return n.status == Notification.Status.SENT and getattr(n, "delivery_mode", None) == "cloud"


def _send_sms(invoice, body) -> bool:
    from core.models import Notification
    from core.services.notifications import NotificationService

    phone = (invoice.customer.phone or "").strip()
    if not phone:
        return False
    n = NotificationService.send(
        company=invoice.company,
        channel=Notification.Channel.SMS,
        recipient=phone,
        subject="payment_reminder",
        body=body,
    )
    return n.status in (Notification.Status.SENT, Notification.Status.QUEUED)


def remind_invoice(invoice, *, sent_on: date, days_overdue: int) -> str:
    company = invoice.company
    body = (
        f"Payment reminder from {company.name}: invoice {invoice.number} "
        f"for INR {_outstanding(invoice)} was due on {invoice.due_date}. Please pay."
    )
    if getattr(company, "dunning_channel_whatsapp", True):
        try:
            if _send_whatsapp(invoice, body):
                _record(
                    invoice,
                    sent_on=sent_on,
                    days_overdue=days_overdue,
                    channel="WHATSAPP",
                    status="SENT",
                )
                return "whatsapp"
        except Exception as exc:
            last_wa = str(exc)[:400]
        else:
            last_wa = ""
    else:
        last_wa = ""
    if getattr(company, "dunning_channel_sms", True):
        try:
            if _send_sms(invoice, body):
                _record(
                    invoice,
                    sent_on=sent_on,
                    days_overdue=days_overdue,
                    channel="SMS",
                    status="SENT",
                )
                return "sms"
        except Exception as exc:
            _record(
                invoice,
                sent_on=sent_on,
                days_overdue=days_overdue,
                channel="SMS",
                status="FAILED",
                error=str(exc)[:500],
            )
            return "failed"
    _record(
        invoice,
        sent_on=sent_on,
        days_overdue=days_overdue,
        channel="SMS",
        status="FAILED",
        error=(last_wa or "No Cloud WhatsApp or SMS channel available.")[:500],
    )
    return "failed"


def run_dunning_for_company(company, *, now: datetime | None = None) -> dict:
    if not getattr(company, "dunning_enabled", False):
        return {"sent": 0, "skipped": 0, "reason": "disabled"}
    if in_quiet_hours(company, now):
        return {"sent": 0, "skipped": 0, "reason": "quiet_hours"}
    as_of = _ist_today(now)
    buckets = configured_days(company)
    max_n = int(getattr(company, "dunning_max_reminders", 3) or 3)
    sent = skipped = 0
    for invoice in eligible_invoices(company, as_of=as_of):
        customer = invoice.customer
        if getattr(customer, "dunning_opt_out", False):
            skipped += 1
            continue
        if not (customer.phone or "").strip():
            skipped += 1
            continue
        days_overdue = (as_of - invoice.due_date).days
        bucket = _next_due_bucket(days_overdue, buckets, invoice)
        if bucket is None:
            continue
        if _already_sent_today(invoice, as_of):
            skipped += 1
            continue
        if _reminder_count(invoice) >= max_n:
            skipped += 1
            continue
        if _outstanding(invoice) <= 0:
            skipped += 1
            continue
        if is_paid_pending_books(invoice):
            skipped += 1
            continue
        result = remind_invoice(invoice, sent_on=as_of, days_overdue=bucket)
        if result in ("whatsapp", "sms"):
            sent += 1
        else:
            skipped += 1
    return {"sent": sent, "skipped": skipped, "reason": "ok"}


def run_dunning_all(*, now: datetime | None = None) -> dict:
    from core.rls import iter_company_ids, set_rls_company
    from accounts.models import Company

    totals = {"sent": 0, "skipped": 0, "companies": 0}
    for cid in iter_company_ids():
        set_rls_company(cid)
        company = Company.objects.filter(pk=cid, dunning_enabled=True).first()
        if company is None:
            continue
        result = run_dunning_for_company(company, now=now)
        totals["sent"] += result.get("sent", 0)
        totals["skipped"] += result.get("skipped", 0)
        totals["companies"] += 1
    set_rls_company(None)
    return totals


def _age_bucket(days: int) -> str:
    if days <= 0:
        return "current"
    if days <= 30:
        return "1_30"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    return "90_plus"


def _avg_payment_delay_days(company, customer) -> int | None:
    from payments.models import PaymentAllocation

    delays = []
    allocs = (
        PaymentAllocation.objects.filter(
            company=company,
            sales_invoice__customer=customer,
            receipt__isnull=False,
            reversed_at__isnull=True,
        )
        .select_related("sales_invoice", "receipt")
        .order_by("-id")[:50]
    )
    for alloc in allocs:
        inv = alloc.sales_invoice
        rec = alloc.receipt
        if not inv or not rec or not inv.due_date:
            continue
        paid_on = getattr(rec, "receipt_date", None) or rec.created_at.date()
        delays.append((paid_on - inv.due_date).days)
    if not delays:
        return None
    return int(round(sum(delays) / len(delays)))


def customer_risk_snapshot(company, customer, *, as_of: date | None = None) -> dict:
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    as_of = as_of or _ist_today()
    outstanding = Decimal(str(LedgerService.customer_outstanding(company, customer) or 0))
    credit_limit = Decimal(str(getattr(customer, "credit_limit", 0) or 0))
    available = credit_limit - outstanding if credit_limit > 0 else None
    ageing = {"current": Decimal("0"), "1_30": Decimal("0"), "31_60": Decimal("0"),
              "61_90": Decimal("0"), "90_plus": Decimal("0")}
    overdue = Decimal("0")
    invoices = SalesInvoice.objects.filter(
        company=company,
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
    )
    for inv in invoices:
        os_amt = _outstanding(inv)
        if os_amt <= 0:
            continue
        due = inv.due_date or inv.invoice_date
        days = (as_of - due).days if due else 0
        ageing[_age_bucket(days)] += os_amt
        if days > 0:
            overdue += os_amt
    avg_delay = _avg_payment_delay_days(company, customer)
    if credit_limit > 0 and outstanding > credit_limit:
        status = "stop_credit"
        next_step = NEXT_STEP_STOP_CREDIT
    elif overdue > 0 and (ageing["90_plus"] > 0 or (avg_delay or 0) > 21):
        status = "overdue_severe"
        next_step = NEXT_STEP_REDUCE_CREDIT
    elif overdue > 0:
        status = "overdue"
        next_step = NEXT_STEP_SEND_LINK
    elif outstanding > 0:
        status = "open"
        next_step = NEXT_STEP_FOLLOW_UP
    else:
        status = "clear"
        next_step = NEXT_STEP_FOLLOW_UP
    if overdue > 0 and next_step == NEXT_STEP_SEND_LINK and ageing["61_90"] + ageing["90_plus"] == 0:
        next_step = NEXT_STEP_SEND_LINK
    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "outstanding": str(outstanding),
        "overdue_amount": str(overdue),
        "ageing": {k: str(v) for k, v in ageing.items()},
        "average_payment_delay_days": avg_delay,
        "credit_limit": str(credit_limit),
        "available_credit": str(available) if available is not None else None,
        "collection_status": status,
        "recommended_next_step": next_step,
        "dunning_opt_out": bool(getattr(customer, "dunning_opt_out", False)),
    }


def list_customer_risk(company, *, as_of: date | None = None, limit: int = 50) -> list[dict]:
    from masters.models import Customer

    as_of = as_of or _ist_today()
    rows = []
    for customer in Customer.objects.filter(company=company).order_by("name")[:500]:
        snap = customer_risk_snapshot(company, customer, as_of=as_of)
        if Decimal(snap["outstanding"]) <= 0:
            continue
        rows.append(snap)
        if len(rows) >= limit:
            break
    rows.sort(key=lambda r: Decimal(r["overdue_amount"]), reverse=True)
    return rows
