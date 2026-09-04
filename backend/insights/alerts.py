"""Business Smart Alerts — rule engine (Phase 6.0)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import logging

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from ledgers.services import LedgerService
from masters.models import Customer
from payments.models import CustomerReceipt
from purchases.models import PurchaseInvoice
from reporting.gst_health import build_gst_health
from reporting.services import ReportService
from sales.models import SalesInvoice, SalesItem

logger = logging.getLogger(__name__)

OPEN_SALES = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)


def _company_localtime(company):
    """B9-031: wall-clock "now" in the company's locale.

    Every current tenant is in ``settings.TIME_ZONE`` (Asia/Kolkata), so this
    returns the server-local time today. It is the single seam to change when a
    per-company timezone field is added — the 6pm NO_SALES_TODAY cutoff and the
    ``as_of == now.date()`` day-boundary check must key off it, not a bare
    ``timezone.localtime()`` scattered through the module.
    """
    tzname = getattr(company, "timezone", None) or getattr(company, "time_zone", None)
    if tzname:
        try:
            from zoneinfo import ZoneInfo

            return timezone.localtime(timezone=ZoneInfo(str(tzname)))
        except Exception:  # noqa: BLE001 — bad tz string falls back to server zone
            pass
    return timezone.localtime()


def _alert(code, severity, message, **extra):
    row = {"code": code, "severity": severity, "message": message}
    row.update(extra)
    return row


def _dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def build_business_alerts(company, as_of: date | None = None) -> list[dict]:
    as_of = as_of or timezone.localdate()
    alerts: list[dict] = []

    aging = ReportService.receivables_aging(company, as_of=as_of)
    prior_as_of = (as_of.replace(day=1) - timedelta(days=1))
    prior_aging = ReportService.receivables_aging(company, as_of=prior_as_of)
    ar_total = sum(aging.values(), Decimal("0"))
    overdue_90 = aging.get("days_90_plus") or Decimal("0")
    overdue_60 = (aging.get("days_61_90") or Decimal("0")) + overdue_90
    bucket_31_60 = aging.get("days_31_60") or Decimal("0")
    prior_31_60 = prior_aging.get("days_31_60") or Decimal("0")

    if overdue_90 > 0 or (ar_total > 0 and overdue_60 / ar_total > Decimal("0.25")):
        alerts.append(_alert(
            "AR_OVERDUE_CRITICAL",
            "critical",
            f"Overdue receivables need attention (90+ bucket ₹{overdue_90}).",
            subject_key="ar",
            cta_path="/reports/customer-ledger",
            payload={"aging": {k: str(v) for k, v in aging.items()}},
        ))
    elif bucket_31_60 > 0:
        delta = bucket_31_60 - prior_31_60
        # Material MoM growth only (avoid natural aging noise)
        min_abs = Decimal("1000")
        grew = delta >= min_abs and (
            prior_31_60 <= 0 or bucket_31_60 >= prior_31_60 * Decimal("1.10")
        )
        if grew:
            alerts.append(_alert(
                "AR_OVERDUE_WARN",
                "warning",
                f"31–60 day receivables grew MoM (₹{prior_31_60} → ₹{bucket_31_60}).",
                subject_key="ar",
                cta_path="/reports/customer-ledger",
            ))

    # AP due in 7 days (outstanding, not grand_total) vs recent 7d receipts
    due_to = as_of + timedelta(days=7)
    ap_due = Decimal("0")
    for inv in PurchaseInvoice.objects.filter(
        company=company,
        status=PurchaseInvoice.Status.COMPLETED,
        due_date__gte=as_of,
        due_date__lte=due_to,
    ).only("id", "grand_total", "status"):
        ap_due += LedgerService.purchase_invoice_outstanding(inv)
    payables = ReportService._company_payables(company)
    ap_signal = min(ap_due, payables) if payables > 0 else ap_due
    if ap_signal > 0:
        alerts.append(_alert(
            "AP_DUE_7D",
            "warning",
            f"Supplier bills due in 7 days (~₹{ap_signal}).",
            subject_key="ap",
            cta_path="/reports/supplier-ledger",
            payload={"ap_due_7d": str(ap_signal)},
        ))

    # Low stock fast movers — company-wide available vs product reorder
    # unless a per-godown WarehouseReorderLevel override exists (E2E3-019).
    from inventory.views import low_stock_alert_payload

    since = as_of - timedelta(days=14)
    sold_ids = set(
        SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date__gte=since,
        ).values_list("items__product_id", flat=True).distinct()
    )
    for bal in low_stock_alert_payload(company):
        if bal.product_id not in sold_ids:
            continue
        alerts.append(_alert(
            "LOW_STOCK_FAST_MOVER",
            "warning",
            f"{bal.product.name} is below reorder and sold in the last 14 days.",
            subject_key=f"product:{bal.product_id}",
            document_type="product",
            document_id=bal.product_id,
            cta_path="/inventory/low-stock",
        ))

    # No sales today
    sales_today = SalesInvoice.objects.filter(
        company=company, status__in=OPEN_SALES, invoice_date=as_of,
    ).count()
    prior_sales = SalesInvoice.objects.filter(
        company=company, status__in=OPEN_SALES,
    ).exists()
    now = _company_localtime(company)
    if prior_sales and sales_today == 0 and now.hour >= 18 and as_of == now.date():
        alerts.append(_alert(
            "NO_SALES_TODAY",
            "info",
            "No sales invoices completed today.",
            subject_key=f"sales:{as_of.isoformat()}",
            cta_path="/sales/new",
        ))

    # Customer concentration
    month_start = as_of.replace(day=1)
    by_customer = list(
        SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date__gte=month_start, invoice_date__lte=as_of,
        )
        .values("customer_id", "customer__name")
        .annotate(total=Coalesce(Sum("grand_total"), Decimal("0")), n=Count("id"))
        .order_by("-total")
    )
    mtd = sum((r["total"] for r in by_customer), Decimal("0"))
    if by_customer and mtd > 0:
        top = by_customer[0]
        share = (top["total"] / mtd) * Decimal("100")
        if share >= Decimal("40"):
            alerts.append(_alert(
                "CUSTOMER_CONCENTRATION",
                "warning",
                f"Top customer {top['customer__name'] or 'Unknown'} is {share:.0f}% of MTD sales.",
                subject_key=f"customer:{top['customer_id']}",
                document_type="customer",
                document_id=top["customer_id"],
                cta_path="/reports/sales",
            ))

    # Credit limit near
    for cust in Customer.objects.filter(
        company=company, status=Customer.Status.ACTIVE, credit_limit__gt=0,
    ):
        exposure = LedgerService.customer_exposure_for_credit_limit(company, cust)
        limit = cust.credit_limit or Decimal("0")
        if limit > 0 and exposure >= limit * Decimal("0.8"):
            alerts.append(_alert(
                "CREDIT_LIMIT_NEAR",
                "warning",
                f"{cust.name} exposure ₹{exposure} is near credit limit ₹{limit}.",
                subject_key=f"customer:{cust.id}",
                document_type="customer",
                document_id=cust.id,
                cta_path="/sales/customers",
            ))

    # Margin drop SKU alert (sold near cost this month)
    seen_products: set[int] = set()
    for it in SalesItem.objects.filter(
        invoice__company=company,
        invoice__status__in=OPEN_SALES,
        invoice__invoice_date__gte=month_start,
    ).select_related("product")[:400]:
        if it.product_id in seen_products:
            continue
        cost = getattr(it.product, "purchase_price", None) or Decimal("0")
        price = it.unit_price or Decimal("0")
        if cost > 0 and price > 0 and (price - cost) / price < Decimal("0.05"):
            seen_products.add(it.product_id)
            alerts.append(_alert(
                "MARGIN_DROP_SKU",
                "warning",
                f"{it.product.name} sold near cost this month.",
                subject_key=f"product:{it.product_id}",
                document_type="product",
                document_id=it.product_id,
                cta_path="/inventory/products",
            ))

    # Cash tight 14d — absolute mode only (relative cumulative from 0 is too noisy)
    try:
        from insights.services import forecast_cashflow

        fc = forecast_cashflow(company, horizon=14, as_of=as_of, persist=False)
        series = fc.get("series") or []
        mode = fc.get("mode") or "relative"
        if mode == "absolute":
            tight = False
            for pt in series:
                ending = _dec(pt.get("ending_cash"))
                if ending < 0:
                    tight = True
                    break
            if tight:
                alerts.append(_alert(
                    "CASH_TIGHT_14D",
                    "critical",
                    "14-day cashflow forecast dips below zero — review collections and payables.",
                    subject_key="cash",
                    cta_path="/insights/cashflow",
                ))
    except Exception:
        logger.exception("Cashflow tight-14d alert failed for company %s", company.id)

    # Bridge to GST Health criticals
    try:
        gst = build_gst_health(company)
        critical = (gst.get("summary") or {}).get("critical") or 0
        if critical:
            alerts.append(_alert(
                "GST_HEALTH_CRITICAL_OPEN",
                "info",
                f"{critical} GST Health critical alert(s) are open — review compliance.",
                subject_key="gst",
                cta_path="/reports/gst-health",
            ))
    except Exception:
        logger.exception("GST health critical alert failed for company %s", company.id)

    return alerts


DISCOUNT_ALERT_PERCENT = Decimal("20")


def build_leakage_detectors(company, as_of: date | None = None, *, row_factory, rupees_to_paise) -> list[dict]:
    """Rules-based leakage (B-05). Deterministic — no LLM.

    Called from the Attention Center only so the legacy alerts inbox is unchanged.
    """
    from django.db.models import Count
    from inventory.models import MovementType, StockBalance, StockMovement
    from purchases.models import PurchaseInvoice, PurchaseItem
    from sales.models import SalesInvoice, SalesItem

    as_of = as_of or timezone.localdate()
    month_start = as_of.replace(day=1)
    rows: list[dict] = []
    open_sales = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)

    # Sale below cost / expected margin this month (one row per SKU).
    seen_below: set[int] = set()
    for it in (
        SalesItem.objects.filter(
            invoice__company=company,
            invoice__status__in=open_sales,
            invoice__invoice_date__gte=month_start,
        )
        .select_related("product", "invoice")[:500]
    ):
        if it.product_id in seen_below:
            continue
        cost = getattr(it.product, "purchase_price", None) or Decimal("0")
        price = it.unit_price or Decimal("0")
        qty = it.quantity or Decimal("0")
        if cost > 0 and price > 0 and price < cost:
            seen_below.add(it.product_id)
            impact = (cost - price) * qty
            rows.append(row_factory(
                code="SALE_BELOW_COST",
                severity="critical",
                title=f"{it.product.name} sold below cost",
                money_impact_paise=rupees_to_paise(impact),
                reason=f"Sold at ₹{price} vs cost ₹{cost}.",
                action_label="Review item",
                action_href="/inventory/products",
                source_ticket="B-05",
                entity_type="product",
                entity_id=it.product_id,
            ))
        elif cost > 0 and price > 0 and (price - cost) / price < Decimal("0.05"):
            # Already covered by MARGIN_DROP_SKU in build_business_alerts; skip.
            pass

    # Discount over threshold or stacked (line + header) this month.
    for inv in (
        SalesInvoice.objects.filter(
            company=company,
            status__in=open_sales,
            invoice_date__gte=month_start,
        )
        .prefetch_related("items")[:200]
    ):
        stacked = (inv.invoice_discount or Decimal("0")) > 0 and any(
            (it.discount_percent or Decimal("0")) > 0 for it in inv.items.all()
        )
        high = any(
            (it.discount_percent or Decimal("0")) >= DISCOUNT_ALERT_PERCENT
            for it in inv.items.all()
        )
        if stacked:
            rows.append(row_factory(
                code="DISCOUNT_STACKED",
                severity="warning",
                title=f"Stacked discount on {inv.number or inv.id}",
                money_impact_paise=rupees_to_paise(inv.discount_total),
                reason="Line discount and header discount both applied.",
                action_label="Open invoice",
                action_href=f"/sales/history/{inv.id}",
                source_ticket="B-05",
                entity_type="sales_invoice",
                entity_id=inv.id,
            ))
        elif high:
            rows.append(row_factory(
                code="DISCOUNT_OVER_THRESHOLD",
                severity="warning",
                title=f"High line discount on {inv.number or inv.id}",
                money_impact_paise=rupees_to_paise(inv.discount_total),
                reason=f"A line discount is ≥ {DISCOUNT_ALERT_PERCENT}%.",
                action_label="Open invoice",
                action_href=f"/sales/history/{inv.id}",
                source_ticket="B-05",
                entity_type="sales_invoice",
                entity_id=inv.id,
            ))

    # Last purchase price up, selling price flat (margin compression).
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
        sell = getattr(it.product, "selling_price", None) or Decimal("0")
        if prev > 0 and latest > prev * Decimal("1.10") and sell > 0 and sell <= prev * Decimal("1.02"):
            rows.append(row_factory(
                code="MARGIN_COMPRESSION",
                severity="warning",
                title=f"Margin compressed — {it.product.name}",
                money_impact_paise=0,
                reason=f"Purchase price rose >10% (₹{prev} → ₹{latest}) while selling price stayed flat.",
                action_label="Review item",
                action_href="/inventory/products",
                source_ticket="B-05",
                entity_type="product",
                entity_id=it.product_id,
            ))
        elif prev > 0 and latest > prev * Decimal("1.10"):
            rows.append(row_factory(
                code="PURCHASE_PRICE_JUMP",
                severity="warning",
                title=f"Supplier price jump — {it.product.name}",
                money_impact_paise=rupees_to_paise(latest - prev),
                reason=f"Latest purchase ₹{latest} is >10% above prior ₹{prev}.",
                action_label="Open purchases",
                action_href="/purchases/history",
                source_ticket="B-05",
                entity_type="product",
                entity_id=it.product_id,
            ))

    # Abnormal stock adjustment (14d).
    since = as_of - timedelta(days=14)
    adjs = (
        StockMovement.objects.filter(
            company=company,
            movement_type=MovementType.ADJUSTMENT,
            created_at__date__gte=since,
        )
        .select_related("product")[:50]
    )
    for mv in adjs:
        qty = abs(mv.quantity or Decimal("0"))
        cost = mv.unit_cost or Decimal("0")
        value = qty * cost
        if qty < Decimal("50") and value < Decimal("10000"):
            continue
        rows.append(row_factory(
            code="ABNORMAL_STOCK_ADJUSTMENT",
            severity="warning",
            title=f"Large stock adjustment — {mv.product.name}",
            money_impact_paise=rupees_to_paise(value),
            reason=mv.reason or f"Adjustment qty {qty}.",
            action_label="Open stock",
            action_href="/inventory/stock",
            source_ticket="B-05",
            entity_type="product",
            entity_id=mv.product_id,
            dedupe_key=f"ABNORMAL_STOCK_ADJUSTMENT:{mv.id}",
        ))

    # Duplicate posted receipts: same customer, amount, date.
    dupes = (
        CustomerReceipt.objects.filter(company=company, status="POSTED")
        .values("customer_id", "amount", "receipt_date")
        .annotate(n=Count("id"))
        .filter(n__gte=2)[:20]
    )
    for d in dupes:
        rows.append(row_factory(
            code="DUPLICATE_PAYMENT",
            severity="warning",
            title="Possible duplicate receipt",
            money_impact_paise=rupees_to_paise(d["amount"]),
            reason=f"{d['n']} receipts of ₹{d['amount']} on {d['receipt_date']}.",
            action_label="Review receipts",
            action_href="/sales/receipts",
            source_ticket="B-05",
            entity_type="customer",
            entity_id=d["customer_id"],
            dedupe_key=f"DUPLICATE_PAYMENT:{d['customer_id']}:{d['receipt_date']}:{d['amount']}",
        ))

    # Dead-stock money figure (on-hand × purchase_price) — complements the hint.
    sold_ids = set(
        SalesInvoice.objects.filter(
            company=company, status__in=open_sales, invoice_date__gte=as_of - timedelta(days=60),
        ).values_list("items__product_id", flat=True)
    )
    sold_ids.discard(None)
    dead_value = Decimal("0")
    dead_n = 0
    for bal in (
        StockBalance.objects.filter(company=company, on_hand__gt=0)
        .exclude(product_id__in=sold_ids)
        .select_related("product")[:40]
    ):
        dead_n += 1
        dead_value += (bal.on_hand or Decimal("0")) * (bal.product.purchase_price or Decimal("0"))
    if dead_n:
        rows.append(row_factory(
            code="DEAD_STOCK",
            severity="info",
            title="Slow / dead stock",
            money_impact_paise=rupees_to_paise(dead_value),
            reason=f"{dead_n} SKUs have stock but no sales in 60 days.",
            action_label="Open stock",
            action_href="/inventory/stock",
            source_ticket="B-05",
            entity_type="company",
            entity_id=company.id,
            dedupe_key=f"DEAD_STOCK:{company.id}",
        ))

    return rows
