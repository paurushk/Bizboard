"""Insights orchestration — summary, upsert alerts, health, cashflow, hints."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventory.models import StockBalance
from ledgers.services import LedgerService
from purchases.models import PurchaseInvoice
from reporting.services import ReportService
from sales.models import SalesInvoice

from .alerts import build_business_alerts
from .models import (
    BusinessAlertEvent,
    BusinessHealthSnapshot,
    CashflowForecastRun,
    DailyBusinessSummary,
)

OPEN_SALES = (SalesInvoice.Status.COMPLETED,)
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
    for row in raw:
        subject = row.get("subject_key") or ""
        key = f"{row['code']}:{subject}"
        kept_keys.add(key)
        existing = (
            BusinessAlertEvent.objects.filter(
                company=company, code=row["code"], subject_key=subject,
            )
            .exclude(status=BusinessAlertEvent.Status.RESOLVED)
            .order_by("-created_at")
            .first()
        )
        if existing and existing.status == BusinessAlertEvent.Status.SNOOZED:
            if existing.snoozed_until and existing.snoozed_until > now:
                results.append(existing)
                continue
            existing.status = BusinessAlertEvent.Status.OPEN
            existing.snoozed_until = None
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
    # Allow retry when only FAILED rows exist
    if prior.exclude(status=Notification.Status.FAILED).exists():
        # QUEUED/other in flight — claim without re-send
        claimed = DailyBusinessSummary.objects.filter(
            pk=summary.pk, email_sent_at__isnull=True,
        ).update(email_sent_at=timezone.now())
        if claimed:
            return
        return

    claimed = DailyBusinessSummary.objects.filter(
        pk=summary.pk, email_sent_at__isnull=True,
    ).update(email_sent_at=timezone.now())
    if not claimed:
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
        if n.status == Notification.Status.FAILED:
            DailyBusinessSummary.objects.filter(pk=summary.pk).update(email_sent_at=None)
    except Exception:
        DailyBusinessSummary.objects.filter(pk=summary.pk).update(email_sent_at=None)
        raise


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


def compute_health_score(company, as_of: date | None = None) -> dict:
    as_of = as_of or timezone.localdate()
    sales_count = SalesInvoice.objects.filter(
        company=company, status__in=OPEN_SALES,
    ).count()
    limited = sales_count < MIN_SALES_FOR_FULL_SCORE

    aging = ReportService.receivables_aging(company, as_of=as_of)
    ar = sum(aging.values(), Decimal("0"))
    current = aging.get("current") or Decimal("0")
    collections_score = Decimal("100")
    if ar > 0:
        collections_score = (current / ar) * Decimal("100")

    payables = ReportService._company_payables(company)
    mtd_supplier_payments = Decimal("0")
    from payments.models import SupplierPayment

    month_start = as_of.replace(day=1)
    mtd_supplier_payments = (
        SupplierPayment.objects.filter(
            company=company,
            payment_date__gte=month_start,
            payment_date__lte=as_of,
        ).aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
        or Decimal("0")
    )
    payables_score = Decimal("80")
    if payables > 0 and mtd_supplier_payments > 0:
        ratio = min(Decimal("2"), mtd_supplier_payments / payables)
        payables_score = min(Decimal("100"), ratio * Decimal("50"))
    elif payables == 0:
        payables_score = Decimal("100")

    # Sales momentum: this 7d vs prior 7d
    d7 = as_of - timedelta(days=6)
    d14 = as_of - timedelta(days=13)
    recent = (
        SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date__gte=d7, invoice_date__lte=as_of,
        ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
        or Decimal("0")
    )
    prior = (
        SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date__gte=d14, invoice_date__lt=d7,
        ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
        or Decimal("0")
    )
    if prior > 0:
        mom = recent / prior
        sales_score = min(Decimal("100"), mom * Decimal("70"))
    elif recent > 0:
        sales_score = Decimal("70")
    else:
        sales_score = Decimal("40")

    # Margin proxy: selling vs purchase price on recent lines
    from sales.models import SalesItem

    items = SalesItem.objects.filter(
        invoice__company=company,
        invoice__status__in=OPEN_SALES,
        invoice__invoice_date__gte=month_start,
    ).select_related("product")[:500]
    margin_score = Decimal("70")
    if items:
        gross = Decimal("0")
        cost = Decimal("0")
        for it in items:
            qty = it.quantity or Decimal("0")
            gross += (it.unit_price or Decimal("0")) * qty
            cost += (getattr(it.product, "purchase_price", None) or Decimal("0")) * qty
        if gross > 0:
            m = (gross - cost) / gross
            margin_score = min(Decimal("100"), max(Decimal("0"), m * Decimal("200")))

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

    # Compliance bridge
    compliance_score = Decimal("90")
    try:
        from reporting.gst_health import build_gst_health

        gst = build_gst_health(company)
        crit = (gst.get("summary") or {}).get("critical") or 0
        compliance_score = max(Decimal("0"), Decimal("100") - Decimal(crit) * Decimal("15"))
    except Exception:
        pass

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

    factors = [
        {"key": "collections", "label": "Collections", "score": _q2(collections_score),
         "weight": str(FACTOR_WEIGHTS["collections"]),
         "detail": f"Current AR share of total AR"},
        {"key": "payables", "label": "Payables pressure", "score": _q2(payables_score),
         "weight": str(FACTOR_WEIGHTS["payables"]),
         "detail": f"AP ₹{_q2(payables)} vs MTD supplier payments ₹{_q2(mtd_supplier_payments)}"},
        {"key": "sales_momentum", "label": "Sales momentum", "score": _q2(sales_score),
         "weight": str(FACTOR_WEIGHTS["sales_momentum"]),
         "detail": f"Last 7d ₹{_q2(recent)} vs prior 7d ₹{_q2(prior)}"},
        {"key": "margin", "label": "Margin health", "score": _q2(margin_score),
         "weight": str(FACTOR_WEIGHTS["margin"]),
         "detail": "Gross margin proxy using last purchase price"},
        {"key": "stock", "label": "Stock health", "score": _q2(stock_score),
         "weight": str(FACTOR_WEIGHTS["stock"]),
         "detail": "Share of SKUs above reorder"},
        {"key": "compliance", "label": "Compliance bridge", "score": _q2(compliance_score),
         "weight": str(FACTOR_WEIGHTS["compliance"]),
         "detail": "Inverse of open GST Health criticals"},
        {"key": "data_completeness", "label": "Data completeness", "score": _q2(data_score),
         "weight": str(FACTOR_WEIGHTS["data_completeness"]),
         "detail": "HSN coverage on GST invoices"},
    ]
    score = sum(
        (Decimal(f["score"]) * Decimal(f["weight"]) for f in factors),
        Decimal("0"),
    )
    score = score.quantize(Decimal("0.01"))

    # MTD vs prior month sales (for Founder UI) — same definition as dashboard KPIs.
    dash = ReportService.dashboard(company)
    mtd_sales = _dec((dash.get("sales_this_month") or {}).get("total"))
    if month_start.month == 1:
        prior_month_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prior_month_start = month_start.replace(month=month_start.month - 1)
    prior_month_end = month_start - timedelta(days=1)
    prior_mtd = (
        SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES,
            invoice_date__gte=prior_month_start, invoice_date__lte=prior_month_end,
        ).exclude(notes="TALLY_OPENING").aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
        or Decimal("0")
    )

    return {
        "score": score,
        "grade": _grade(score),
        "factors": factors,
        "limited_data": limited,
        "as_of": as_of.isoformat(),
        "sales_count": sales_count,
        "mtd_sales": _q2(mtd_sales),
        "prior_month_sales": _q2(prior_mtd),
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


def _collection_rates_from_history(company, as_of: date) -> dict[str, Decimal]:
    """Derive rates from paid invoices when enough history; else defaults."""
    from payments.models import PaymentAllocation

    paid = (
        PaymentAllocation.objects.filter(company=company, receipt__isnull=False, reversed_at__isnull=True)
        .values("sales_invoice_id")
        .annotate(paid=Sum("amount"))
    )
    if paid.count() < 10:
        return dict(DEFAULT_COLLECTION_RATES)

    # Heuristic: higher collection share → bump current/1-30 rates slightly
    rates = dict(DEFAULT_COLLECTION_RATES)
    rates["current"] = Decimal("0.80")
    rates["days_1_30"] = Decimal("0.55")
    return rates


def forecast_cashflow(
    company, horizon: int = 14, as_of: date | None = None, *, persist: bool = False,
) -> dict:
    as_of = as_of or timezone.localdate()
    horizon = int(horizon)
    if horizon not in (7, 14, 30, 90):
        horizon = 14

    mode = "absolute" if company.opening_cash_balance is not None and company.opening_cash_as_of else "relative"
    opening = _dec(company.opening_cash_balance) if mode == "absolute" else Decimal("0")

    series = []
    cumulative = Decimal("0")
    aging = ReportService.receivables_aging(company, as_of=as_of)
    rates = _collection_rates_from_history(company, as_of)
    expected_in = Decimal("0")
    for bucket, rate in rates.items():
        expected_in += (_dec(aging.get(bucket)) * rate)

    daily_in = expected_in / Decimal(horizon) if horizon else Decimal("0")

    ap_by_day: dict[date, Decimal] = {}
    qs = PurchaseInvoice.objects.filter(
        company=company,
        status=PurchaseInvoice.Status.COMPLETED,
        due_date__gte=as_of,
        due_date__lte=as_of + timedelta(days=horizon),
    )
    for inv in qs:
        if not inv.due_date:
            continue
        outstanding = LedgerService.purchase_invoice_outstanding(inv)
        if outstanding <= 0:
            continue
        ap_by_day[inv.due_date] = ap_by_day.get(inv.due_date, Decimal("0")) + outstanding

    for i in range(horizon):
        d = as_of + timedelta(days=i + 1)
        outflow = ap_by_day.get(d, Decimal("0"))
        inflow = daily_in
        net = inflow - outflow
        cumulative += net
        ending = opening + cumulative if mode == "absolute" else cumulative
        series.append({
            "date": d.isoformat(),
            "inflow": _q2(inflow),
            "outflow": _q2(outflow),
            "net": _q2(net),
            "cumulative": _q2(cumulative),
            "ending_cash": _q2(ending),
            "low": _q2(ending * Decimal("0.85")),
            "high": _q2(ending * Decimal("1.15")),
        })

    meta = {
        "mode": mode,
        "expected_collections": _q2(expected_in),
        "collection_rates": {k: str(v) for k, v in rates.items()},
        "disclaimer": (
            "Forecast from open documents and historical collection rates. "
            "Payments are record-only — not a bank feed."
        ),
        "opening_cash": _q2(opening) if mode == "absolute" else None,
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
            model_version="v1",
            inputs_hash=inputs_hash,
        )
        run_id = run.id
    return {
        "horizon_days": horizon,
        "mode": mode,
        "series": series,
        "meta": meta,
        "run_id": run_id,
        "model_version": "v1",
    }


# ---- Growth hints (6.3) ----

def build_growth_hints(company, as_of: date | None = None) -> list[dict]:
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
        if cost > 0 and price > 0 and (price - cost) / price < Decimal("0.05"):
            compressed.append(it.product.name)
    if compressed:
        hints.append({
            "code": "MARGIN_DROP_SKU",
            "title": "Review thin-margin SKUs",
            "impact_estimate": None,
            "message": f"{len(set(compressed))} SKUs sold near cost this month.",
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
            "cta_path": "/sales/history",
            "severity": "info",
        })

    # Purchase price creep — latest purchase unit price > prior by >10%
    from purchases.models import PurchaseItem

    creep_names = []
    products_seen: set[int] = set()
    for it in (
        PurchaseItem.objects.filter(
            invoice__company=company,
            invoice__status=PurchaseInvoice.Status.COMPLETED,
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
                invoice__status=PurchaseInvoice.Status.COMPLETED,
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
            "cta_path": "/purchases/history",
            "severity": "warning",
        })

    return hints
