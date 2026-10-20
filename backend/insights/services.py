"""Insights orchestration — summary, upsert alerts, health, cashflow, hints."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventory.models import StockBalance
from ledgers.services import LedgerService
from purchases.models import PurchaseInvoice
from purchases.status_semantics import OPEN_PAYABLE_STATUSES, OPERATIONAL_PURCHASE_STATUSES
from reporting.services import ReportService
from sales.models import SalesInvoice
from sales.status_semantics import OPERATIONAL_SALE_STATUSES

logger = logging.getLogger(__name__)

from .alerts import build_business_alerts
from .models import (
    BusinessAlertEvent,
    BusinessHealthSnapshot,
    CashflowForecastRun,
    DailyBusinessSummary,
)

# CF-001: sourced from sales.status_semantics so this can't independently
# drift from insights/alerts.py's identical OPEN_SALES again (G-17).
OPEN_SALES = OPERATIONAL_SALE_STATUSES
MIN_SALES_FOR_FULL_SCORE = 30


def _dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _q2(v: Decimal) -> str:
    return f"{v.quantize(Decimal('0.01'))}"


@transaction.atomic
def upsert_alerts(company, as_of: date | None = None) -> list[BusinessAlertEvent]:
    as_of = as_of or timezone.localdate()
    raw = build_business_alerts(company, as_of=as_of)
    now = timezone.now()
    kept_keys = set()
    results = []
    # INP-15: runs for one company take turns (a no-op on SQLite), so two refreshes cannot both
    # insert the same new alert and trip the unique constraint.
    type(company).objects.select_for_update().filter(pk=company.pk).first()
    # Lock this company's live rows for the run and collapse any
    # duplicate (code, subject) pairs left by concurrent runs: newest wins, older ones resolve.
    live = list(
        BusinessAlertEvent.objects.select_for_update()
        .filter(
            company=company,
            status__in=[BusinessAlertEvent.Status.OPEN, BusinessAlertEvent.Status.SNOOZED],
        )
        .order_by("-created_at", "-id")
    )
    by_key: dict[tuple[str, str], BusinessAlertEvent] = {}
    for ev in live:
        k = (ev.code, ev.subject_key)
        if k in by_key:
            ev.status = BusinessAlertEvent.Status.RESOLVED
            ev.save(update_fields=["status", "updated_at"])
        else:
            by_key[k] = ev
    for row in raw:
        subject = row.get("subject_key") or ""
        key = f"{row['code']}:{subject}"
        kept_keys.add(key)
        existing = by_key.get((row["code"], subject))
        if existing and existing.status == BusinessAlertEvent.Status.SNOOZED:
            if existing.snoozed_until and existing.snoozed_until > now:
                results.append(existing)
                continue
            existing.status = BusinessAlertEvent.Status.OPEN
            existing.snoozed_until = None
            existing.snoozed_by = None
        extras = {k: v for k, v in row.items() if k not in ("code", "severity", "message", "subject_key", "cta_path")}
        nested = extras.pop("payload", None)
        if isinstance(nested, dict):
            payload = {**extras, **nested}
        else:
            payload = extras
        if existing:
            existing.severity = row["severity"]
            existing.message = row["message"]
            existing.payload = payload
            existing.cta_path = row.get("cta_path") or ""
            existing.status = BusinessAlertEvent.Status.OPEN
            existing.save()
            results.append(existing)
        else:
            results.append(
                BusinessAlertEvent.objects.create(
                    company=company,
                    code=row["code"],
                    severity=row["severity"],
                    message=row["message"],
                    subject_key=subject,
                    payload=payload,
                    cta_path=row.get("cta_path") or "",
                    created_by=None,
                )
            )

    # Resolve alerts that no longer fire
    open_qs = BusinessAlertEvent.objects.filter(
        company=company,
        status__in=[BusinessAlertEvent.Status.OPEN, BusinessAlertEvent.Status.SNOOZED],
    )
    for ev in open_qs:
        key = f"{ev.code}:{ev.subject_key}"
        if key not in kept_keys:
            ev.status = BusinessAlertEvent.Status.RESOLVED
            ev.save(update_fields=["status", "updated_at"])
    return results


def get_open_alerts_readonly(company) -> list[BusinessAlertEvent]:
    """B9-011: a read-only view of the last-persisted alerts for callers
    (the AI assistant) that must not have write side-effects. Alerts are
    kept fresh by upsert_alerts() being called from generate_daily_summary's
    own scheduled task + the dashboard views; this never recomputes."""
    return list(
        BusinessAlertEvent.objects.filter(
            company=company, status=BusinessAlertEvent.Status.OPEN,
        ).order_by("-created_at")
    )


def get_daily_summary_readonly(company, for_date: date | None = None) -> DailyBusinessSummary | None:
    """B9-011: read the most recent persisted DailyBusinessSummary without
    generating one -- for callers (the AI assistant) that must not have
    write side-effects. Returns None if the scheduled task hasn't run yet
    for this company (e.g. a brand-new tenant)."""
    qs = DailyBusinessSummary.objects.filter(company=company)
    if for_date is not None:
        qs = qs.filter(summary_date=for_date)
    return qs.order_by("-summary_date").first()


def generate_daily_summary(
    company, for_date: date | None = None, *, send_email: bool = False,
) -> DailyBusinessSummary:
    for_date = for_date or timezone.localdate()
    alerts = upsert_alerts(company, as_of=for_date)
    open_alerts = [a for a in alerts if a.status == BusinessAlertEvent.Status.OPEN]
    # UXW2-001: reuse ReportService.dashboard so banner KPIs match Dashboard cards
    # (net of returns, same AR/AP aggregates, live figures).
    dash = ReportService.dashboard(company)
    sales_today = dash.get("sales_today") or {}
    sales_mtd = dash.get("sales_this_month") or {}
    kpis = {
        "sales_today_total": _q2(_dec(sales_today.get("total"))),
        "sales_today_count": int(sales_today.get("count") or 0),
        "sales_mtd_total": _q2(_dec(sales_mtd.get("total"))),
        "sales_mtd_count": int(sales_mtd.get("count") or 0),
        "receivables": _q2(_dec(dash.get("receivables"))),
        "payables": _q2(_dec(dash.get("payables"))),
        "low_stock_count": dash.get("low_stock_count") or 0,
        "open_alerts": len(open_alerts),
        "critical_alerts": sum(1 for a in open_alerts if a.severity == "critical"),
    }
    codes = [a.code for a in open_alerts]
    critical = sum(1 for a in open_alerts if a.severity == "critical")
    narrative = (
        f"Sales today ₹{kpis['sales_today_total']} ({kpis['sales_today_count']} invoices). "
        f"MTD ₹{kpis['sales_mtd_total']}. "
        f"AR ₹{kpis['receivables']} · AP ₹{kpis['payables']}. "
        f"{len(open_alerts)} open alert(s) ({critical} critical)."
    )
    obj, _ = DailyBusinessSummary.objects.update_or_create(
        company=company,
        summary_date=for_date,
        defaults={
            "kpis": kpis,
            "alert_codes": codes,
            "narrative": narrative,
            "prompt_version": "template-v1",
        },
    )
    if send_email:
        _maybe_send_digest_email(company, obj, open_alerts)
        _maybe_send_digest_whatsapp(company, obj, open_alerts)
    return obj


def _maybe_send_digest_email(company, summary: DailyBusinessSummary, open_alerts: list) -> None:
    """Idempotent daily digest — at most one email per company/date."""
    if not getattr(company, "daily_summary_email_enabled", False):
        return
    if summary.email_sent_at:
        return
    recipient = (company.email or "").strip()
    if not recipient:
        from accounts.models import CompanyUser

        owner = (
            CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER, is_active=True)
            .select_related("user")
            .order_by("id")
            .first()
        )
        recipient = (owner.user.email if owner else "") or ""
    if not recipient:
        return
    from core.models import Notification
    from core.services.notifications import NotificationService

    subject = f"BizBoard daily summary — {summary.summary_date.isoformat()}"
    prior = Notification.objects.filter(
        company=company, channel=Notification.Channel.EMAIL, subject=subject,
    )
    if prior.filter(status=Notification.Status.SENT).exists():
        DailyBusinessSummary.objects.filter(pk=summary.pk, email_sent_at__isnull=True).update(
            email_sent_at=timezone.now(),
        )
        return

    alert_lines = "\n".join(f"- [{a.severity}] {a.code}: {a.message}" for a in open_alerts[:10])
    body = (
        f"{summary.narrative}\n\n"
        f"Open alerts:\n{alert_lines or '(none)'}\n\n"
        "Insights from your BizBoard documents — not tax advice.\n"
        "Open Insights in the app for details."
    )
    try:
        n = NotificationService.send(
            company=company,
            channel=Notification.Channel.EMAIL,
            recipient=recipient,
            subject=subject,
            body=body,
        )
        n.refresh_from_db()
        # B9-028: stamp optimistically for any non-FAILED outcome (incl. a
        # queued / pending async send) so the next daily run doesn't re-send;
        # only a definite FAILED clears it for a retry.
        if n.status == Notification.Status.FAILED:
            DailyBusinessSummary.objects.filter(pk=summary.pk).update(email_sent_at=None)
        else:
            DailyBusinessSummary.objects.filter(pk=summary.pk).update(email_sent_at=timezone.now())
    except Exception:
        DailyBusinessSummary.objects.filter(pk=summary.pk).update(email_sent_at=None)
        raise


WHATSAPP_DIGEST_TEMPLATE_READY = False


def _maybe_send_digest_whatsapp(company, summary: DailyBusinessSummary, open_alerts: list) -> None:
    """Owner digest on WhatsApp. Capped at 5 items. Same day is sent once.

    INP-06: held back until a dedicated digest template is registered with the provider. Until then
    NotificationService.send would send this under the "payment_reminder" template, so the owner
    would receive their digest as a payment reminder.
    """
    if not WHATSAPP_DIGEST_TEMPLATE_READY:
        return
    if not getattr(company, "daily_summary_email_enabled", False):
        return
    from accounts.models import CompanyUser
    from core.models import Notification
    from core.services.notifications import NotificationService
    from payments.promise_to_pay import promises_due_today

    owner = (
        CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER, is_active=True)
        .select_related("user")
        .order_by("id")
        .first()
    )
    phone = ""
    if owner is not None:
        phone = (getattr(owner.user, "phone", "") or getattr(company, "phone", "") or "").strip()
    if not phone:
        return
    subject = f"BizBoard daily summary — {summary.summary_date.isoformat()}"
    if Notification.objects.filter(
        company=company, channel=Notification.Channel.WHATSAPP, subject=subject,
    ).exclude(status=Notification.Status.FAILED).exists():
        return
    lines = [f"{a.code}: {a.message}" for a in open_alerts[:5]]
    promised = list(promises_due_today(company)[:5])
    # Need room for the header AND at least one name under it, or the digest
    # ends with a dangling "Promised to pay today:" line and nothing below it.
    remaining = 5 - len(lines)
    if promised and remaining >= 2:
        lines.append("Promised to pay today:")
        for row in promised[: remaining - 1]:
            lines.append(f"- {row.customer.name}")
    body = "\n".join(lines) or "No open attention items."
    NotificationService.send(
        company=company,
        channel=Notification.Channel.WHATSAPP,
        recipient=phone,
        subject=subject,
        body=body[:1000],
    )


# ---- Health score (6.1) ----

FACTOR_WEIGHTS = {
    "collections": Decimal("0.25"),
    "payables": Decimal("0.15"),
    "sales_momentum": Decimal("0.20"),
    "margin": Decimal("0.15"),
    "stock": Decimal("0.10"),
    "compliance": Decimal("0.10"),
    "data_completeness": Decimal("0.05"),
}


def _grade(score: Decimal) -> str:
    if score >= Decimal("85"):
        return "A"
    if score >= Decimal("70"):
        return "B"
    if score >= Decimal("55"):
        return "C"
    if score >= Decimal("40"):
        return "D"
    return "F"


HEALTH_BAND_HEALTHY = Decimal("70")
HEALTH_BAND_WATCH = Decimal("45")


def health_band(score) -> str:
    """The word the dashboard shows. Thresholds live here, not in the UI."""
    value = Decimal(str(score))
    if value >= HEALTH_BAND_HEALTHY:
        return "healthy"
    if value >= HEALTH_BAND_WATCH:
        return "watch"
    return "action"


HEALTH_MIN_INVOICES_90D = 30
UNDATED_PAYABLE_GRACE_DAYS = 30
MARGIN_ALERT_CODES = frozenset({
    "MARGIN_COMPRESSION", "MARGIN_DROP_SKU", "PURCHASE_PRICE_JUMP", "SALE_BELOW_COST",
})
MARGIN_HINT_CODES = frozenset({"MARGIN_DROP_SKU", "PURCHASE_PRICE_CREEP"})


def _net_sales(company, start: date, end: date) -> Decimal:
    """Sales net of credit/debit notes, opening balances excluded: the dashboard's definition."""
    from reporting.services import NET_SALES
    from sales.models import SalesCreditNote, SalesDebitNote

    gross = (
        SalesInvoice.objects.filter(
            company=company, status__in=NET_SALES, invoice_date__gte=start,
            invoice_date__lte=end, is_opening_balance=False,
        ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
        or Decimal("0")
    )
    cn = (
        SalesCreditNote.objects.filter(
            company=company, status=SalesCreditNote.Status.COMPLETED,
            note_date__gte=start, note_date__lte=end,
        ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
        or Decimal("0")
    )
    dn = (
        SalesDebitNote.objects.filter(
            company=company, status=SalesDebitNote.Status.COMPLETED,
            note_date__gte=start, note_date__lte=end,
        ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
        or Decimal("0")
    )
    return gross - cn + dn


def _open_payables_split(company, as_of: date) -> tuple[Decimal, Decimal]:
    """(total open AP, overdue AP). A bill with no due date and no terms gets a 30-day grace."""
    outs = LedgerService.bulk_purchase_invoice_outstanding(company)
    if not outs:
        return Decimal("0"), Decimal("0")
    total = Decimal("0")
    overdue = Decimal("0")
    for inv in PurchaseInvoice.objects.filter(pk__in=list(outs)).only(
        "id", "invoice_date", "due_date", "payment_terms_days",
    ):
        amount = outs.get(inv.id) or Decimal("0")
        if amount <= 0:
            continue
        total += amount
        if inv.due_date:
            due = inv.due_date
        else:
            terms = inv.payment_terms_days or UNDATED_PAYABLE_GRACE_DAYS
            due = inv.invoice_date + timedelta(days=terms)
        if due < as_of:
            overdue += amount
    return total, overdue


def _factor(key, label, score, weight, detail, *, available=True):
    return {
        "key": key,
        "label": label,
        "score": _q2(score) if available and score is not None else None,
        "weight": str(weight),
        "detail": detail,
        "available": bool(available and score is not None),
    }


def compute_health_score(company, as_of: date | None = None, *, include_margin: bool = True) -> dict:
    as_of = as_of or timezone.localdate()
    month_start = as_of.replace(day=1)
    # INP-05: "enough data" is recent activity, not lifetime count.
    sales_count = SalesInvoice.objects.filter(
        company=company, status__in=OPEN_SALES, invoice_date__gte=as_of - timedelta(days=90),
        invoice_date__lte=as_of,
    ).count()
    limited = sales_count < HEALTH_MIN_INVOICES_90D

    aging = ReportService.receivables_aging(company, as_of=as_of)
    ar = sum(aging.values(), Decimal("0"))
    current = aging.get("current") or Decimal("0")
    collections_score = Decimal("100")
    if ar > 0:
        collections_score = (current / ar) * Decimal("100")

    # D6: share of open payables that is not yet overdue.
    ap_total, ap_overdue = _open_payables_split(company, as_of)
    payables_score = Decimal("100")
    if ap_total > 0:
        payables_score = (ap_total - ap_overdue) / ap_total * Decimal("100")

    # Sales momentum: this 7d vs prior 7d, opening-balance invoices excluded.
    d7 = as_of - timedelta(days=6)
    d14 = as_of - timedelta(days=13)
    recent = (
        SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date__gte=d7, invoice_date__lte=as_of,
            is_opening_balance=False,
        ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
        or Decimal("0")
    )
    prior = (
        SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date__gte=d14, invoice_date__lt=d7,
            is_opening_balance=False,
        ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
        or Decimal("0")
    )
    if prior > 0:
        sales_score = min(Decimal("100"), (recent / prior) * Decimal("70"))
    elif recent > 0:
        sales_score = Decimal("70")
    else:
        sales_score = Decimal("40")

    # Margin: from the per-invoice profit snapshots (cost at the time of sale).
    margin_score = None
    margin_detail = "Margin figures need margin access."
    if include_margin:
        from reporting.models import InvoiceProfitSnapshot

        agg = (
            InvoiceProfitSnapshot.objects.filter(
                company=company, invoice_date__gte=month_start, invoice_date__lte=as_of,
                invoice_status__in=list(OPEN_SALES),
            )
            .exclude(cost_basis__in=[
                InvoiceProfitSnapshot.CostBasis.ZERO_COST, InvoiceProfitSnapshot.CostBasis.NO_COGS,
            ])
            .aggregate(
                rev=Coalesce(Sum("revenue_pre_discount"), Decimal("0")),
                cogs=Coalesce(Sum("cogs_total"), Decimal("0")),
            )
        )
        rev, cogs = _dec(agg["rev"]), _dec(agg["cogs"])
        if rev > 0:
            m = (rev - cogs) / rev
            margin_score = min(Decimal("100"), max(Decimal("0"), m * Decimal("200")))
            margin_detail = f"Gross margin {(m * 100).quantize(Decimal('0.1'))}% this month on costed invoices"
        else:
            margin_detail = "No costed invoices this month yet."

    # Stock health
    bals = list(
        StockBalance.objects.filter(company=company, product__status="ACTIVE").select_related("product")
    )
    stock_score = Decimal("80")
    if bals:
        low = sum(
            1
            for b in bals
            if (b.product.reorder_level or 0) > 0
            and ((b.on_hand or 0) - (b.reserved or 0)) <= b.product.reorder_level
        )
        stock_score = Decimal("100") - Decimal(low) / Decimal(len(bals)) * Decimal("100")

    # Compliance bridge: a failure is shown as unavailable, not as a made-up 50.
    compliance_score = None
    compliance_detail = "GST health could not be read right now."
    try:
        from reporting.gst_health import build_gst_health

        gst = build_gst_health(company)
        crit = (gst.get("summary") or {}).get("critical") or 0
        compliance_score = max(Decimal("0"), Decimal("100") - Decimal(crit) * Decimal("15"))
        compliance_detail = "Inverse of open GST Health criticals"
    except Exception:
        logger.exception("GST health score failed for company %s", company.pk)

    # Data completeness — HSN on recent GST invoices
    gst_inv = SalesInvoice.objects.filter(
        company=company, status__in=OPEN_SALES, invoice_type="GST", invoice_date__gte=month_start,
    )
    total_gst = gst_inv.count()
    data_score = Decimal("80")
    if total_gst:
        missing = 0
        for inv in gst_inv.prefetch_related("items")[:200]:
            for it in inv.items.all():
                if not (it.hsn_code or "").strip():
                    missing += 1
                    break
        data_score = Decimal("100") - Decimal(missing) / Decimal(min(total_gst, 200)) * Decimal("100")

    W = FACTOR_WEIGHTS
    factors = [
        _factor("collections", "Collections", collections_score, W["collections"],
                "Current AR share of total AR"),
        _factor("payables", "Payables pressure", payables_score, W["payables"],
                f"Not-yet-overdue share of open AP (AP ₹{_q2(ap_total)}, overdue ₹{_q2(ap_overdue)}; "
                f"undated bills get {UNDATED_PAYABLE_GRACE_DAYS} days)"),
        _factor("sales_momentum", "Sales momentum", sales_score, W["sales_momentum"],
                f"Last 7d ₹{_q2(recent)} vs prior 7d ₹{_q2(prior)}"),
        _factor("margin", "Margin health", margin_score, W["margin"], margin_detail,
                available=margin_score is not None),
        _factor("stock", "Stock health", stock_score, W["stock"], "Share of SKUs above reorder"),
        _factor("compliance", "Compliance bridge", compliance_score, W["compliance"],
                compliance_detail, available=compliance_score is not None),
        _factor("data_completeness", "Data completeness", data_score, W["data_completeness"],
                "HSN coverage on GST invoices"),
    ]
    live = [f for f in factors if f["available"]]
    weight_sum = sum((Decimal(f["weight"]) for f in live), Decimal("0")) or Decimal("1")
    score = sum((Decimal(f["score"]) * Decimal(f["weight"]) for f in live), Decimal("0")) / weight_sum
    score = score.quantize(Decimal("0.01"))

    # MTD vs the same day-range of the prior month, same definition on both sides.
    mtd_sales = _net_sales(company, month_start, as_of)
    prior_month_end = month_start - timedelta(days=1)
    prior_month_start = prior_month_end.replace(day=1)
    prior_same_end = min(prior_month_end, prior_month_start + timedelta(days=as_of.day - 1))
    prior_mtd = _net_sales(company, prior_month_start, prior_same_end)
    change_pct = None
    if prior_mtd > 0:
        change_pct = _q2((mtd_sales - prior_mtd) / prior_mtd * Decimal("100"))

    return {
        "score": score,
        "grade": _grade(score),
        "grade_withheld": limited,
        "band": health_band(score),
        "factors": factors,
        "limited_data": limited,
        "as_of": as_of.isoformat(),
        "sales_count": sales_count,
        "mtd_sales": _q2(mtd_sales),
        "prior_month_sales": _q2(prior_mtd),
        "prior_month_range_end": prior_same_end.isoformat(),
        "mtd_change_percent": change_pct,
    }


def snapshot_health(company, as_of: date | None = None) -> BusinessHealthSnapshot:
    as_of = as_of or timezone.localdate()
    data = compute_health_score(company, as_of=as_of)
    obj, _ = BusinessHealthSnapshot.objects.update_or_create(
        company=company,
        as_of=as_of,
        defaults={
            "score": data["score"],
            "grade": data["grade"],
            "factors": data["factors"],
            "limited_data": data["limited_data"],
        },
    )
    return obj


# ---- Cashflow (6.2) ----

DEFAULT_COLLECTION_RATES = {
    "current": Decimal("0.70"),
    "days_1_30": Decimal("0.50"),
    "days_31_60": Decimal("0.30"),
    "days_61_90": Decimal("0.15"),
    "days_90_plus": Decimal("0.05"),
}


def _collection_rates_heuristic(company, as_of: date) -> dict[str, Decimal]:
    """B9-029: NOT derived from history despite the name/disclaimer this
    replaced — `paid` below is only ever used as an activity gate (has this
    company recorded ≥10 allocations at all?), never to compute an actual
    realised collection ratio per aging bucket from allocation timing. This
    is a fixed heuristic nudge once that gate is met, not a historical
    calculation; callers must not describe it as "historical" (see the
    `disclaimer` string in cashflow_forecast below)."""
    from payments.models import PaymentAllocation

    paid = (
        PaymentAllocation.objects.filter(company=company, receipt__isnull=False, reversed_at__isnull=True)
        .values("sales_invoice_id")
        .annotate(paid=Sum("amount"))
    )
    if paid.count() < 10:
        return dict(DEFAULT_COLLECTION_RATES)

    # Heuristic: enough collection activity on record → bump current/1-30
    # rates slightly. Still a fixed nudge, not computed from `paid`.
    rates = dict(DEFAULT_COLLECTION_RATES)
    rates["current"] = Decimal("0.80")
    rates["days_1_30"] = Decimal("0.55")
    return rates


SCENARIO_LOW = Decimal("0.6")
SCENARIO_HIGH = Decimal("1.2")
CASHFLOW_EXCLUDED = ["expenses", "payroll", "GST / TDS payments", "loan EMIs", "owner drawings"]


def _recorded_cash_since(company, since: date, until: date) -> Decimal:
    """Posted, cleared receipts minus supplier payments dated after ``since`` and up to ``until``.

    Same filters as the Cash Book (cleared cheques only, credit-mode excluded).
    """
    from payments.models import CustomerReceipt, ReceiptStatus, SupplierPayment, SupplierPaymentStatus

    cleared = ReportService._cleared_money_q()
    inflow = (
        CustomerReceipt.objects.filter(
            company=company, status=ReceiptStatus.POSTED,
            receipt_date__gt=since, receipt_date__lte=until,
        ).exclude(mode="CREDIT").filter(cleared)
        .aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
    )
    outflow = (
        SupplierPayment.objects.filter(
            company=company, status=SupplierPaymentStatus.POSTED,
            payment_date__gt=since, payment_date__lte=until,
        ).exclude(mode="CREDIT").filter(cleared)
        .aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
    )
    return _dec(inflow) - _dec(outflow)


def forecast_cashflow(
    company, horizon: int = 14, as_of: date | None = None, *, persist: bool = False,
) -> dict:
    as_of = as_of or timezone.localdate()
    horizon = int(horizon)
    if horizon not in (7, 14, 30, 90):
        horizon = 14

    has_baseline = company.opening_cash_balance is not None and company.opening_cash_as_of
    mode = "absolute" if has_baseline else "relative"
    opening = Decimal("0")
    rolled = Decimal("0")
    if mode == "absolute":
        # D1: the balance is as of ``opening_cash_as_of``; add what was recorded after it.
        opening = _dec(company.opening_cash_balance)
        if company.opening_cash_as_of < as_of:
            rolled = _recorded_cash_since(company, company.opening_cash_as_of, as_of)
    baseline = opening + rolled

    aging = ReportService.receivables_aging(company, as_of=as_of)
    rates = _collection_rates_heuristic(company, as_of)

    def _expected(mult: Decimal) -> Decimal:
        total = Decimal("0")
        for bucket, rate in rates.items():
            total += _dec(aging.get(bucket)) * min(Decimal("1"), rate * mult)
        return total

    expected_in = _expected(Decimal("1"))
    daily_in = {
        "low": _expected(SCENARIO_LOW) / Decimal(horizon),
        "base": expected_in / Decimal(horizon),
        "high": _expected(SCENARIO_HIGH) / Decimal(horizon),
    }

    # Outflows: every open bill due by the end of the window. Bills already overdue, due today or
    # with no due date are assumed payable on day 1.
    first_day = as_of + timedelta(days=1)
    last_day = as_of + timedelta(days=horizon)
    ap_by_day: dict[date, Decimal] = {}
    overdue_ap = Decimal("0")
    undated_ap = Decimal("0")
    outs = LedgerService.bulk_purchase_invoice_outstanding(company)
    if outs:
        qs = PurchaseInvoice.objects.filter(
            company=company, status__in=OPEN_PAYABLE_STATUSES, pk__in=list(outs),
        ).only("id", "due_date")
        for inv in qs:
            outstanding = outs.get(inv.id) or Decimal("0")
            if outstanding <= 0:
                continue
            if inv.due_date is None:
                day = first_day
                undated_ap += outstanding
            elif inv.due_date <= as_of:
                day = first_day
                overdue_ap += outstanding
            elif inv.due_date <= last_day:
                day = inv.due_date
            else:
                continue
            ap_by_day[day] = ap_by_day.get(day, Decimal("0")) + outstanding

    series = []
    cumulative = {"low": Decimal("0"), "base": Decimal("0"), "high": Decimal("0")}
    for i in range(horizon):
        d = first_day + timedelta(days=i)
        outflow = ap_by_day.get(d, Decimal("0"))
        for k in cumulative:
            cumulative[k] += daily_in[k] - outflow
        inflow = daily_in["base"]
        net = inflow - outflow
        endings = {k: (baseline + v) if mode == "absolute" else v for k, v in cumulative.items()}
        series.append({
            "date": d.isoformat(),
            "inflow": _q2(inflow),
            "outflow": _q2(outflow),
            "net": _q2(net),
            "cumulative": _q2(cumulative["base"]),
            "ending_cash": _q2(endings["base"]),
            "low": _q2(endings["low"]),
            "high": _q2(endings["high"]),
        })

    meta = {
        "mode": mode,
        "as_of": as_of.isoformat(),
        "expected_collections": _q2(expected_in),
        "collection_rates": {k: str(v) for k, v in rates.items()},
        "scenario": {"low": str(SCENARIO_LOW), "high": str(SCENARIO_HIGH)},
        "disclaimer": (
            "Forecast from open documents and fixed heuristic collection rates, not your payment "
            "history. The range runs collections at 60% to 120% of the base rates. Payments are "
            "record-only, not a bank feed."
        ),
        "excluded": CASHFLOW_EXCLUDED,
        "opening_cash": _q2(opening) if mode == "absolute" else None,
        "baseline_as_of": company.opening_cash_as_of.isoformat() if mode == "absolute" else None,
        "recorded_since_baseline": _q2(rolled) if mode == "absolute" else None,
        "starting_cash": _q2(baseline) if mode == "absolute" else None,
        "overdue_payables": _q2(overdue_ap),
        "undated_payables": _q2(undated_ap),
    }
    run_id = None
    if persist:
        payload = json.dumps({"series": series, "meta": meta}, sort_keys=True)
        inputs_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
        run = CashflowForecastRun.objects.create(
            company=company,
            horizon_days=horizon,
            mode=mode,
            series=series,
            meta=meta,
            model_version="v2",
            inputs_hash=inputs_hash,
        )
        run_id = run.id
    return {
        "horizon_days": horizon,
        "mode": mode,
        "series": series,
        "meta": meta,
        "run_id": run_id,
        "model_version": "v2",
    }


# ---- Growth hints (6.3) ----

def build_growth_hints(
    company, as_of: date | None = None, *, include_margin: bool = True,
) -> list[dict]:
    as_of = as_of or timezone.localdate()
    hints = []
    month_start = as_of.replace(day=1)

    # Overdue top-N
    aging = ReportService.receivables_aging(company, as_of=as_of)
    overdue = (aging.get("days_61_90") or Decimal("0")) + (aging.get("days_90_plus") or Decimal("0"))
    if overdue > 0:
        hints.append({
            "code": "OVERDUE_CONCENTRATION",
            "title": "Chase long-overdue receivables",
            "impact_estimate": _q2(overdue),
            "message": f"₹{_q2(overdue)} sits in 61+ day buckets.",
            "params": {"amount": str(_q2(overdue))},
            "cta_path": "/reports/customer-ledger",
            "severity": "warning",
        })

    # Dead stock: on hand > 0, no sales in 60d
    since = as_of - timedelta(days=60)
    sold = set(
        SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date__gte=since,
        ).values_list("items__product_id", flat=True)
    )
    dead_list = list(
        StockBalance.objects.filter(company=company, on_hand__gt=0)
        .exclude(product_id__in=[x for x in sold if x])
        .select_related("product")[:10]
    )
    if dead_list:
        hints.append({
            "code": "DEAD_STOCK",
            "title": "Move slow / dead stock",
            "impact_estimate": None,
            "message": f"{len(dead_list)} SKUs have stock but no sales in 60 days.",
            "cta_path": "/inventory/stock",
            "severity": "info",
            "evidence": [{"product_id": b.product_id, "name": b.product.name} for b in dead_list],
        })

    # Customer concentration (reuse alert logic lightly)
    by_customer = list(
        SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date__gte=month_start, invoice_date__lte=as_of,
        )
        .values("customer_id", "customer__name")
        .annotate(total=Coalesce(Sum("grand_total"), Decimal("0")))
        .order_by("-total")[:5]
    )
    mtd = sum((r["total"] for r in by_customer), Decimal("0"))
    if by_customer and mtd > 0 and by_customer[0]["total"] / mtd >= Decimal("0.40"):
        top = by_customer[0]
        hints.append({
            "code": "CUSTOMER_CONCENTRATION",
            "title": "Diversify customer mix",
            "impact_estimate": _q2(top["total"]),
            "message": f"{top['customer__name']} is a large share of MTD sales.",
            "cta_path": "/reports/sales",
            "severity": "warning",
        })

    # Margin compression: products selling near cost
    from sales.models import SalesItem

    compressed = []
    for it in SalesItem.objects.filter(
        invoice__company=company,
        invoice__status__in=OPEN_SALES,
        invoice__invoice_date__gte=month_start,
    ).select_related("product")[:300]:
        cost = getattr(it.product, "purchase_price", None) or Decimal("0")
        price = it.unit_price or Decimal("0")
        from core.services.margin import margin_below_threshold

        if margin_below_threshold(price, cost):
            compressed.append(it.product.name)
    if compressed:
        hints.append({
            "code": "MARGIN_DROP_SKU",
            "title": "Review thin-margin SKUs",
            "impact_estimate": None,
            "message": f"{len(set(compressed))} SKUs sold near cost this month.",
            "params": {"count": len(set(compressed))},
            "cta_path": "/inventory/products",
            "severity": "warning",
        })

    # Discount abuse — invoices with high line discount
    high_disc = SalesInvoice.objects.filter(
        company=company, status__in=OPEN_SALES, invoice_date__gte=month_start,
        discount_total__gt=0,
    ).count()
    if high_disc >= 5:
        hints.append({
            "code": "DISCOUNT_FREQUENCY",
            "title": "Review discounting pattern",
            "impact_estimate": None,
            "message": f"{high_disc} invoices this month carry discounts.",
            "params": {"count": high_disc},
            "cta_path": "/reports/sales-discounts",
            "severity": "info",
        })

    # Purchase price creep — latest purchase unit price > prior by >10%
    from purchases.models import PurchaseItem

    creep_names = []
    products_seen: set[int] = set()
    for it in (
        PurchaseItem.objects.filter(
            invoice__company=company,
            invoice__status__in=OPERATIONAL_PURCHASE_STATUSES,
        )
        .select_related("product", "invoice")
        .order_by("product_id", "-invoice__invoice_date", "-id")[:800]
    ):
        if it.product_id in products_seen:
            continue
        products_seen.add(it.product_id)
        prior = (
            PurchaseItem.objects.filter(
                invoice__company=company,
                invoice__status__in=OPERATIONAL_PURCHASE_STATUSES,
                product_id=it.product_id,
            )
            .exclude(id=it.id)
            .order_by("-invoice__invoice_date", "-id")
            .first()
        )
        if not prior:
            continue
        latest = it.unit_price or Decimal("0")
        prev = prior.unit_price or Decimal("0")
        if prev > 0 and latest > prev * Decimal("1.10"):
            creep_names.append(it.product.name)
    if creep_names:
        hints.append({
            "code": "PURCHASE_PRICE_CREEP",
            "title": "Purchase price creep",
            "impact_estimate": None,
            "message": f"{len(set(creep_names))} SKUs rose >10% vs prior purchase.",
            "params": {"count": len(set(creep_names))},
            "cta_path": "/purchases/history",
            "severity": "warning",
        })

    if not include_margin:
        hints = [h for h in hints if h.get("code") not in MARGIN_HINT_CODES]
    return hints
