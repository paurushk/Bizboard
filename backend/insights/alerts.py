"""Business Smart Alerts — rule engine (Phase 6.0)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventory.models import StockBalance
from ledgers.services import LedgerService
from masters.models import Customer
from payments.models import CustomerReceipt
from purchases.models import PurchaseInvoice
from reporting.gst_health import build_gst_health
from reporting.services import ReportService
from sales.models import SalesInvoice, SalesItem

OPEN_SALES = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)


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
    recent_receipts = (
        CustomerReceipt.objects.filter(
            company=company,
            receipt_date__gte=as_of - timedelta(days=6),
            receipt_date__lte=as_of,
            status="POSTED",
        ).aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
        or Decimal("0")
    )
    if ap_signal > 0 and ap_signal > recent_receipts:
        alerts.append(_alert(
            "AP_DUE_7D",
            "warning",
            f"Supplier bills due in 7 days (~₹{ap_signal}) exceed recent 7d receipts (₹{recent_receipts}).",
            subject_key="ap",
            cta_path="/reports/supplier-ledger",
            payload={"ap_due_7d": str(ap_signal), "receipts_7d": str(recent_receipts)},
        ))

    # Low stock fast movers
    since = as_of - timedelta(days=14)
    sold_ids = set(
        SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date__gte=since,
        ).values_list("items__product_id", flat=True).distinct()
    )
    low = (
        StockBalance.objects.filter(company=company, product_id__in=sold_ids)
        .select_related("product")
        .filter(product__reorder_level__gt=0)
    )
    for bal in low:
        available = (bal.on_hand or Decimal("0")) - (bal.reserved or Decimal("0"))
        if available <= (bal.product.reorder_level or Decimal("0")):
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
    now = timezone.localtime()
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
        pass

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
        pass

    return alerts
