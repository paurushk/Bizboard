"""
Report Service (E5.2–E5.5) — dashboards, registers and exports via
aggregated queries; API clients never scan raw document tables (§9).
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.exceptions import BusinessRuleError
from inventory.models import StockBalance, StockMovement, Warehouse
from ledgers.services import LedgerService
from masters.models import Product
from purchases.models import (
    PurchaseCreditNote,
    PurchaseDebitNote,
    PurchaseInvoice,
)
from sales.models import (
    SalesCreditNote,
    SalesDebitNote,
    SalesInvoice,
)

OPEN_SALES = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)
NET_SALES = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)
logger = logging.getLogger(__name__)


def _party_name(obj, attr="customer"):
    party = getattr(obj, attr, None)
    return (getattr(party, "name", None) or "").strip() or "—"


def _invoice_payment_state(invoice) -> str:
    from payments.holding import invoice_payment_state

    return invoice_payment_state(invoice)


def _as_sort_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.min


def _money(value, negate=False):
    amount = value if value is not None else Decimal("0")
    return -amount if negate else amount


# B5-010: sales_register/purchase_register build a Python list of every
# matching document with no LIMIT -- fine for a real date range, but an
# unbounded call (no date_from) on a large tenant is a multi-MB response and
# a full raw-document-table scan, exactly what this module's own docstring
# says API clients never do. Cap it with a cheap .count() before building
# the row list, rather than truncating silently (which would misrepresent a
# financial register) or changing the response shape for the common case.
MAX_REGISTER_ROWS_UNBOUNDED = 5000
MAX_REGISTER_ROWS_HARD_CAP = 10000
# CR-074: dated exports / heavy reports must stay within one FY-ish window.
MAX_REPORT_DATE_SPAN_DAYS = 366


def _assert_register_within_bound(qs, *, date_from, kind: str) -> None:
    count = qs.count()
    if not date_from and count > MAX_REGISTER_ROWS_UNBOUNDED:
        raise BusinessRuleError(
            f"{kind} has {count} documents with no start date filter -- add a "
            f"date_from (or a narrower range) to keep this under "
            f"{MAX_REGISTER_ROWS_UNBOUNDED} rows."
        )
    if count > MAX_REGISTER_ROWS_HARD_CAP:
        raise BusinessRuleError(
            f"{kind} has {count} documents, exceeding the single-query limit of "
            f"{MAX_REGISTER_ROWS_HARD_CAP} rows. Please narrow the date range or export in batches."
        )


def assert_report_date_span(date_from, date_to, *, kind: str = "Report") -> None:
    """CR-074 / CR-149: reject multi-year dated ranges (HTTP 400 via BusinessRuleError).

    If only one bound is set, treat missing ``date_to`` as today and missing
    ``date_from`` as (today - max span) so one-sided filters cannot bypass the cap.
    """
    from django.utils import timezone as dj_tz

    if not date_from and not date_to:
        return
    today = dj_tz.localdate()
    if date_from and not date_to:
        date_to = today
    elif date_to and not date_from:
        date_from = date_to - timedelta(days=MAX_REPORT_DATE_SPAN_DAYS)
    span = (date_to - date_from).days
    if span < 0:
        raise BusinessRuleError(f"{kind}: date_from must be on or before date_to.")
    if span > MAX_REPORT_DATE_SPAN_DAYS:
        raise BusinessRuleError(
            f"{kind} date range is {span} days; maximum allowed is "
            f"{MAX_REPORT_DATE_SPAN_DAYS} days. Narrow date_from/date_to."
        )


class ReportService:
    @staticmethod
    def _aging_total(buckets: dict) -> Decimal:
        return sum((buckets.get(k) or Decimal("0") for k in buckets), Decimal("0"))

    @staticmethod
    def _company_receivables(company) -> Decimal:
        """CR-060: dashboard AR = sum(receivables_aging) on document outstanding.

        Pilot choice: one code path with aging (LedgerService.bulk_sales_invoice_outstanding).
        GL party AR stays on LedgerService.company_receivables for books/recon surfaces.
        """
        return ReportService._aging_total(ReportService.receivables_aging(company))

    @staticmethod
    def _company_payables(company) -> Decimal:
        """CR-101: dashboard AP = sum(payables_aging) on document outstanding (twin of CR-060 AR).

        GL party AP stays on LedgerService.company_payables for books/recon surfaces.
        """
        return ReportService._aging_total(ReportService.payables_aging(company))

    @staticmethod
    def _invoice_balance(invoice) -> Decimal:
        try:
            return LedgerService.sales_invoice_outstanding(invoice)
        except (TypeError, ValueError, ArithmeticError) as exc:
            logger.warning("sales_invoice_outstanding failed for invoice %s: %s", getattr(invoice, "pk", None), exc)
            return Decimal(str(invoice.grand_total or 0))

    @staticmethod
    def receivables_aging(company, as_of: date | None = None):
        """Bucket open sales invoice outstanding by due date (or invoice_date + terms).

        CR-060: outstanding via LedgerService.bulk_sales_invoice_outstanding so the
        dashboard receivables KPI (sum of these buckets) shares one document basis.
        """
        as_of = as_of or timezone.localdate()
        buckets = {
            "current": Decimal("0"),
            "days_1_30": Decimal("0"),
            "days_31_60": Decimal("0"),
            "days_61_90": Decimal("0"),
            "days_90_plus": Decimal("0"),
        }
        invoices = list(
            SalesInvoice.objects.filter(
                company=company,
                status__in=OPEN_SALES,
                is_opening_balance=False,
            ).only(
                "id", "invoice_date", "due_date", "payment_terms_days"
            )
        )
        if not invoices:
            return buckets
        outstanding_by_id = LedgerService.bulk_sales_invoice_outstanding(
            company, invoice_ids=[inv.id for inv in invoices]
        )
        for inv in invoices:
            outstanding = outstanding_by_id.get(inv.id) or Decimal("0")
            if outstanding <= 0:
                continue
            due = inv.due_date or (
                inv.invoice_date + timedelta(days=inv.payment_terms_days or 0)
            )
            days = (as_of - due).days
            if days <= 0:
                buckets["current"] += outstanding
            elif days <= 30:
                buckets["days_1_30"] += outstanding
            elif days <= 60:
                buckets["days_31_60"] += outstanding
            elif days <= 90:
                buckets["days_61_90"] += outstanding
            else:
                buckets["days_90_plus"] += outstanding
        return buckets

    @staticmethod
    def dashboard(company):
        today = timezone.localdate()
        month_start = today.replace(day=1)

        # BB-000688: a fully-returned invoice flips to status RETURNED — it must
        # still count toward gross sales here (the credit-note subtraction below
        # then nets it out), otherwise a return shows as negative sales.
        sales_today = SalesInvoice.objects.filter(
            company=company, status__in=NET_SALES, invoice_date=today, is_opening_balance=False,
        ).aggregate(total=Sum("grand_total"), count=Count("id"))
        sales_month = SalesInvoice.objects.filter(
            company=company, status__in=NET_SALES, invoice_date__gte=month_start, invoice_date__lte=today, is_opening_balance=False,
        ).aggregate(total=Sum("grand_total"), count=Count("id"))
        cn_today = (
            SalesCreditNote.objects.filter(
                company=company, status=SalesCreditNote.Status.COMPLETED, note_date=today,
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )
        cn_month = (
            SalesCreditNote.objects.filter(
                company=company, status=SalesCreditNote.Status.COMPLETED, note_date__gte=month_start, note_date__lte=today,
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )
        dn_today = (
            SalesDebitNote.objects.filter(
                company=company, status=SalesDebitNote.Status.COMPLETED, note_date=today,
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )
        dn_month = (
            SalesDebitNote.objects.filter(
                company=company, status=SalesDebitNote.Status.COMPLETED, note_date__gte=month_start, note_date__lte=today,
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )
        # CR-043 / CR-045: include RETURNED and cap at today
        purchases_month = PurchaseInvoice.objects.filter(
            company=company, status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
            invoice_date__gte=month_start, invoice_date__lte=today, is_opening_balance=False,
        ).aggregate(total=Sum("grand_total"), count=Count("id"))
        # CR-064: purchases_this_month net of completed purchase CNs/DNs
        pcn_month = (
            PurchaseCreditNote.objects.filter(
                company=company, status=PurchaseCreditNote.Status.COMPLETED, note_date__gte=month_start, note_date__lte=today,
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )
        pdn_month = (
            PurchaseDebitNote.objects.filter(
                company=company, status=PurchaseDebitNote.Status.COMPLETED, note_date__gte=month_start, note_date__lte=today,
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )

        from inventory.views import low_stock_alert_payload

        low_stock = len(low_stock_alert_payload(company))

        recent = SalesInvoice.objects.filter(company=company).exclude(
            status__in=(SalesInvoice.Status.DRAFT, SalesInvoice.Status.CANCELLED)
        ).order_by("-completed_at")[:5]

        # CR-060 / CR-065 / CR-153: aging once; KPI foots to the same document outstanding.
        aging = ReportService.receivables_aging(company)
        payables_aging = ReportService.payables_aging(company)

        return {
            "sales_today": {
                "total": (sales_today["total"] or Decimal("0")) - cn_today + dn_today,
                "count": sales_today["count"],
            },
            "sales_this_month": {
                "total": (sales_month["total"] or Decimal("0")) - cn_month + dn_month,
                "count": sales_month["count"],
            },
            "purchases_this_month": {
                "total": (purchases_month["total"] or Decimal("0")) - pcn_month + pdn_month,
                "count": purchases_month["count"],
            },
            "receivables": ReportService._aging_total(aging),
            "payables": ReportService._aging_total(payables_aging),
            "low_stock_count": low_stock,
            "receivables_aging": aging,
            "payables_aging": payables_aging,
            "cash_position": ReportService.cash_position(company),
            "recent_invoices": [
                {
                    "id": i.id,
                    "number": i.number,
                    "customer": _party_name(i, "customer"),
                    "date": i.invoice_date,
                    "status": i.status,
                    "grand_total": i.grand_total,
                    "balance": ReportService._invoice_balance(i),
                    "payment_state": _invoice_payment_state(i),
                }
                for i in recent.select_related("customer")
            ],
            "product_count": Product.objects.filter(company=company).count(),
            "invoice_count": SalesInvoice.objects.filter(company=company)
            .exclude(status__in=(SalesInvoice.Status.DRAFT, SalesInvoice.Status.CANCELLED))
            .count(),
        }

    @staticmethod
    def sales_register(
        company,
        date_from=None,
        date_to=None,
        customer_id=None,
        status=None,
        warehouse_id=None,
        company_gstin_id=None,
    ):
        qs = SalesInvoice.objects.filter(company=company).exclude(status=SalesInvoice.Status.DRAFT)
        if status:
            qs = qs.filter(status=status)
        else:
            # CR-063: default register excludes cancelled (optional status= still allowed).
            qs = qs.exclude(status=SalesInvoice.Status.CANCELLED)
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)
        if company_gstin_id:
            qs = qs.filter(company_gstin_id=company_gstin_id)
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        _assert_register_within_bound(qs, date_from=date_from, kind="Sales register")
        rows = [
            {
                "id": i.id,
                "number": i.number,
                "date": i.invoice_date,
                "customer": _party_name(i, "customer"),
                "invoice_type": i.invoice_type,
                "status": i.status,
                "taxable": _money(i.taxable_total),
                "cgst": _money(i.cgst_total),
                "sgst": _money(i.sgst_total),
                "igst": _money(i.igst_total),
                "grand_total": _money(i.grand_total),
            }
            for i in qs.select_related("customer")
        ]
        totals = qs.aggregate(taxable=Sum("taxable_total"), grand=Sum("grand_total"))

        cn_qs = SalesCreditNote.objects.filter(
            company=company, status=SalesCreditNote.Status.COMPLETED
        )
        dn_qs = SalesDebitNote.objects.filter(
            company=company, status=SalesDebitNote.Status.COMPLETED
        )
        if company_gstin_id:
            cn_qs = cn_qs.filter(sales_invoice__company_gstin_id=company_gstin_id)
            dn_qs = dn_qs.filter(sales_invoice__company_gstin_id=company_gstin_id)
        if customer_id:
            cn_qs = cn_qs.filter(customer_id=customer_id)
            dn_qs = dn_qs.filter(customer_id=customer_id)
        # CR-067: warehouse filter applies to notes via parent invoice warehouse.
        if warehouse_id:
            cn_qs = cn_qs.filter(sales_invoice__warehouse_id=warehouse_id)
            dn_qs = dn_qs.filter(sales_invoice__warehouse_id=warehouse_id)
        if date_from:
            cn_qs = cn_qs.filter(note_date__gte=date_from)
            dn_qs = dn_qs.filter(note_date__gte=date_from)
        if date_to:
            cn_qs = cn_qs.filter(note_date__lte=date_to)
            dn_qs = dn_qs.filter(note_date__lte=date_to)
        for cn in cn_qs.select_related("customer"):
            rows.append({
                "id": cn.id,
                "number": cn.number,
                "date": cn.note_date,
                "customer": _party_name(cn, "customer"),
                "invoice_type": "CREDIT_NOTE",
                "status": cn.status,
                "taxable": _money(cn.taxable_total),
                "cgst": _money(cn.cgst_total),
                "sgst": _money(cn.sgst_total),
                "igst": _money(cn.igst_total),
                "grand_total": _money(cn.grand_total, negate=True),
                "doc_type": "SALES_CREDIT_NOTE",
            })
        for dn in dn_qs.select_related("customer"):
            rows.append({
                "id": dn.id,
                "number": dn.number,
                "date": dn.note_date,
                "customer": _party_name(dn, "customer"),
                "invoice_type": "DEBIT_NOTE",
                "status": dn.status,
                "taxable": _money(dn.taxable_total),
                "cgst": _money(dn.cgst_total),
                "sgst": _money(dn.sgst_total),
                "igst": _money(dn.igst_total),
                "grand_total": _money(dn.grand_total),
                "doc_type": "SALES_DEBIT_NOTE",
            })
        rows.sort(key=lambda r: (_as_sort_date(r["date"]), r["number"] or ""))
        cn_tot = cn_qs.aggregate(taxable=Sum("taxable_total"), grand=Sum("grand_total"))
        dn_tot = dn_qs.aggregate(taxable=Sum("taxable_total"), grand=Sum("grand_total"))
        return {
            "rows": rows,
            "totals": {
                "taxable": (totals["taxable"] or 0)
                - (cn_tot["taxable"] or 0)
                + (dn_tot["taxable"] or 0),
                "grand_total": (totals["grand"] or 0)
                - (cn_tot["grand"] or 0)
                + (dn_tot["grand"] or 0),
            },
        }

    @staticmethod
    def purchase_register(
        company, date_from=None, date_to=None, supplier_id=None, status=None, warehouse_id=None,
    ):
        qs = PurchaseInvoice.objects.filter(company=company).exclude(
            status=PurchaseInvoice.Status.DRAFT
        )
        if status:
            qs = qs.filter(status=status)
        else:
            # CR-063: default register excludes cancelled.
            qs = qs.exclude(status=PurchaseInvoice.Status.CANCELLED)
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        _assert_register_within_bound(qs, date_from=date_from, kind="Purchase register")
        rows = [
            {
                "id": i.id,
                "number": i.number,
                "date": i.invoice_date,
                "supplier": _party_name(i, "supplier"),
                "status": i.status,
                "taxable": _money(i.taxable_total),
                "cgst": _money(i.cgst_total),
                "sgst": _money(i.sgst_total),
                "igst": _money(i.igst_total),
                "grand_total": _money(i.grand_total),
            }
            for i in qs.select_related("supplier")
        ]
        totals = qs.aggregate(taxable=Sum("taxable_total"), grand=Sum("grand_total"))
        cn_qs = PurchaseCreditNote.objects.filter(
            company=company, status=PurchaseCreditNote.Status.COMPLETED
        )
        dn_qs = PurchaseDebitNote.objects.filter(
            company=company, status=PurchaseDebitNote.Status.COMPLETED
        )
        if supplier_id:
            cn_qs = cn_qs.filter(supplier_id=supplier_id)
            dn_qs = dn_qs.filter(supplier_id=supplier_id)
        # CR-067: warehouse filter applies to notes via parent invoice warehouse.
        if warehouse_id:
            cn_qs = cn_qs.filter(purchase_invoice__warehouse_id=warehouse_id)
            dn_qs = dn_qs.filter(purchase_invoice__warehouse_id=warehouse_id)
        if date_from:
            cn_qs = cn_qs.filter(note_date__gte=date_from)
            dn_qs = dn_qs.filter(note_date__gte=date_from)
        if date_to:
            cn_qs = cn_qs.filter(note_date__lte=date_to)
            dn_qs = dn_qs.filter(note_date__lte=date_to)
        for cn in cn_qs.select_related("supplier"):
            rows.append({
                "id": cn.id,
                "number": cn.number,
                "date": cn.note_date,
                "supplier": _party_name(cn, "supplier"),
                "status": cn.status,
                "taxable": _money(cn.taxable_total),
                "cgst": _money(cn.cgst_total),
                "sgst": _money(cn.sgst_total),
                "igst": _money(cn.igst_total),
                "grand_total": _money(cn.grand_total, negate=True),
                "doc_type": "PURCHASE_CREDIT_NOTE",
            })
        for dn in dn_qs.select_related("supplier"):
            rows.append({
                "id": dn.id,
                "number": dn.number,
                "date": dn.note_date,
                "supplier": _party_name(dn, "supplier"),
                "status": dn.status,
                "taxable": _money(dn.taxable_total),
                "cgst": _money(dn.cgst_total),
                "sgst": _money(dn.sgst_total),
                "igst": _money(dn.igst_total),
                "grand_total": _money(dn.grand_total),
                "doc_type": "PURCHASE_DEBIT_NOTE",
            })
        rows.sort(key=lambda r: (_as_sort_date(r["date"]), r["number"] or ""))
        cn_tot = cn_qs.aggregate(taxable=Sum("taxable_total"), grand=Sum("grand_total"))
        dn_tot = dn_qs.aggregate(taxable=Sum("taxable_total"), grand=Sum("grand_total"))
        return {
            "rows": rows,
            "totals": {
                "taxable": (totals["taxable"] or 0)
                - (cn_tot["taxable"] or 0)
                + (dn_tot["taxable"] or 0),
                "grand_total": (totals["grand"] or 0)
                - (cn_tot["grand"] or 0)
                + (dn_tot["grand"] or 0),
            },
        }

    @staticmethod
    def inventory_summary(company, warehouse_id=None):
        from inventory.services import InventoryValuationService

        # CR-062: on_hand from sum(StockMovement); flag StockBalance drift.
        wid = None
        if warehouse_id is not None and warehouse_id != "":
            try:
                wid = int(warehouse_id)
            except (TypeError, ValueError):
                wid = None

        move_qs = StockMovement.objects.filter(company=company)
        bal_qs = StockBalance.objects.filter(company=company).select_related(
            "product", "warehouse", "batch"
        )
        if wid is not None:
            move_qs = move_qs.filter(warehouse_id=wid)
            bal_qs = bal_qs.filter(warehouse_id=wid)

        on_hand_by_key = {
            (r["product_id"], r["warehouse_id"], r["batch_id"]): (r["qty"] or Decimal("0"))
            for r in move_qs.values("product_id", "warehouse_id", "batch_id").annotate(
                qty=Coalesce(Sum("quantity"), Decimal("0"))
            )
        }
        balances = {(b.product_id, b.warehouse_id, b.batch_id): b for b in bal_qs}
        keys = set(on_hand_by_key) | set(balances)

        orphan_product_ids = {k[0] for k in keys if k not in balances}
        orphan_wh_ids = {k[1] for k in keys if k not in balances and k[1]}
        products = {
            p.id: p for p in Product.objects.filter(company=company, pk__in=orphan_product_ids)
        } if orphan_product_ids else {}
        warehouses = {
            w.id: w for w in Warehouse.objects.filter(company=company, pk__in=orphan_wh_ids)
        } if orphan_wh_ids else {}

        valued = InventoryValuationService.valuation(company, warehouse=wid)
        value_by_key = {
            (row["warehouse"], row["product"], row["batch"]): row["value"]
            for row in valued
        }

        rows = []
        total_value = Decimal("0")
        for product_id, wh_id, batch_id in keys:
            key = (product_id, wh_id, batch_id)
            b = balances.get(key)
            on_hand = on_hand_by_key.get(key, Decimal("0"))
            reserved = (b.reserved if b else Decimal("0")) or Decimal("0")
            product = b.product if b else products.get(product_id)
            if product is None:
                continue
            warehouse = b.warehouse if b else warehouses.get(wh_id)
            batch = b.batch if b else None
            balance_on_hand = b.on_hand if b is not None else None
            drifted = balance_on_hand is not None and balance_on_hand != on_hand
            # CR-102: reserved still lives on StockBalance (no movement sum); flag when
            # reserved > on_hand (impossible after drift) so operators see bad available.
            reserved_drift = reserved < 0 or (on_hand >= 0 and reserved > on_hand)

            value = None if drifted else value_by_key.get((wh_id, product_id, batch_id))
            if value is None:
                unit = InventoryValuationService.unit_cost(
                    company, product, warehouse=warehouse, batch=batch,
                )
                value = on_hand * (unit or Decimal("0"))
            total_value += value
            available = on_hand - reserved
            row = {
                "product_id": product_id,
                "product": product.name,
                "sku": product.sku,
                "warehouse_id": wh_id,
                "warehouse": warehouse.name if warehouse else "",
                "on_hand": on_hand,
                "reserved": reserved,
                "available": available,
                "reorder_level": product.reorder_level,
                "stock_value": (value or Decimal("0")).quantize(Decimal("0.01")),
            }
            if drifted:
                row["balance_drift"] = True
                row["balance_on_hand"] = balance_on_hand
            if reserved_drift:
                row["reserved_drift"] = True
            rows.append(row)
        return {"rows": rows, "total_stock_value": total_value}

    @staticmethod
    def payables_aging(company, as_of: date | None = None):
        """Bucket open purchase invoice outstanding by due date.

        B5-008: was N+1 — one LedgerService.purchase_invoice_outstanding()
        call per invoice (each its own handful of queries), unlike
        receivables_aging's twin which precomputes CN/DN/allocation maps in
        bulk. Now uses bulk_purchase_invoice_outstanding for the same O(1)
        query shape.
        """
        from ledgers.services import LedgerService

        as_of = as_of or timezone.localdate()
        buckets = {
            "current": Decimal("0"),
            "days_1_30": Decimal("0"),
            "days_31_60": Decimal("0"),
            "days_61_90": Decimal("0"),
            "days_90_plus": Decimal("0"),
        }
        invoices = list(
            PurchaseInvoice.objects.filter(
                company=company,
                status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
                is_opening_balance=False,
            ).only("id", "grand_total", "invoice_date", "due_date", "payment_terms_days")
        )
        if not invoices:
            return buckets
        outstanding_by_id = LedgerService.bulk_purchase_invoice_outstanding(
            company, invoice_ids=[inv.id for inv in invoices]
        )
        for inv in invoices:
            outstanding = outstanding_by_id.get(inv.id) or Decimal("0")
            if outstanding <= 0:
                continue
            due = inv.due_date or (inv.invoice_date + timedelta(days=inv.payment_terms_days or 0))
            days = (as_of - due).days
            if days <= 0:
                buckets["current"] += outstanding
            elif days <= 30:
                buckets["days_1_30"] += outstanding
            elif days <= 60:
                buckets["days_31_60"] += outstanding
            elif days <= 90:
                buckets["days_61_90"] += outstanding
            else:
                buckets["days_90_plus"] += outstanding
        return buckets

    @staticmethod
    def product_sales(company, date_from=None, date_to=None):
        """CR-066 / CR-150: net completed credit/debit note lines into product rankings with date bounds."""
        assert_report_date_span(date_from, date_to, kind="Product sales")
        from collections import defaultdict

        from sales.models import SalesCreditNoteItem, SalesDebitNoteItem, SalesItem

        qs = SalesItem.objects.filter(invoice__company=company, invoice__status__in=NET_SALES)
        if date_from:
            qs = qs.filter(invoice__invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice__invoice_date__lte=date_to)
        totals: dict = defaultdict(lambda: {"quantity": Decimal("0"), "amount": Decimal("0"), "name": ""})
        for r in qs.values("product_id", "product__name").annotate(
            quantity=Sum("quantity"), amount=Sum("line_total")
        ):
            bucket = totals[r["product_id"]]
            bucket["name"] = r["product__name"]
            bucket["quantity"] += r["quantity"] or Decimal("0")
            bucket["amount"] += r["amount"] or Decimal("0")

        cn_qs = SalesCreditNoteItem.objects.filter(
            credit_note__company=company,
            credit_note__status=SalesCreditNote.Status.COMPLETED,
        )
        dn_qs = SalesDebitNoteItem.objects.filter(
            debit_note__company=company,
            debit_note__status=SalesDebitNote.Status.COMPLETED,
        )
        if date_from:
            cn_qs = cn_qs.filter(credit_note__note_date__gte=date_from)
            dn_qs = dn_qs.filter(debit_note__note_date__gte=date_from)
        if date_to:
            cn_qs = cn_qs.filter(credit_note__note_date__lte=date_to)
            dn_qs = dn_qs.filter(debit_note__note_date__lte=date_to)
        for r in cn_qs.values("product_id", "product__name").annotate(
            quantity=Sum("quantity"), amount=Sum("line_total")
        ):
            bucket = totals[r["product_id"]]
            bucket["name"] = bucket["name"] or r["product__name"]
            bucket["quantity"] -= r["quantity"] or Decimal("0")
            bucket["amount"] -= r["amount"] or Decimal("0")
        for r in dn_qs.values("product_id", "product__name").annotate(
            quantity=Sum("quantity"), amount=Sum("line_total")
        ):
            bucket = totals[r["product_id"]]
            bucket["name"] = bucket["name"] or r["product__name"]
            bucket["quantity"] += r["quantity"] or Decimal("0")
            bucket["amount"] += r["amount"] or Decimal("0")

        rows = sorted(
            (
                {
                    "product_id": pid,
                    "product": vals["name"],
                    "quantity": vals["quantity"],
                    "amount": vals["amount"],
                }
                for pid, vals in totals.items()
                if vals["quantity"] or vals["amount"]
            ),
            key=lambda row: row["amount"],
            reverse=True,
        )
        return {"rows": rows}

    @staticmethod
    def customer_sales(company, date_from=None, date_to=None):
        """CR-066 / CR-150: net completed credit/debit notes into customer sales amounts with date bounds."""
        assert_report_date_span(date_from, date_to, kind="Customer sales")
        from collections import defaultdict

        qs = SalesInvoice.objects.filter(company=company, status__in=NET_SALES)
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        totals: dict = defaultdict(
            lambda: {"invoices": 0, "amount": Decimal("0"), "name": ""}
        )
        for r in qs.values("customer_id", "customer__name").annotate(
            invoices=Count("id"), amount=Sum("grand_total")
        ):
            bucket = totals[r["customer_id"]]
            bucket["name"] = r["customer__name"]
            bucket["invoices"] = r["invoices"] or 0
            bucket["amount"] += r["amount"] or Decimal("0")

        cn_qs = SalesCreditNote.objects.filter(
            company=company, status=SalesCreditNote.Status.COMPLETED
        )
        dn_qs = SalesDebitNote.objects.filter(
            company=company, status=SalesDebitNote.Status.COMPLETED
        )
        if date_from:
            cn_qs = cn_qs.filter(note_date__gte=date_from)
            dn_qs = dn_qs.filter(note_date__gte=date_from)
        if date_to:
            cn_qs = cn_qs.filter(note_date__lte=date_to)
            dn_qs = dn_qs.filter(note_date__lte=date_to)
        for r in cn_qs.values("customer_id", "customer__name").annotate(amount=Sum("grand_total")):
            bucket = totals[r["customer_id"]]
            bucket["name"] = bucket["name"] or r["customer__name"]
            bucket["amount"] -= r["amount"] or Decimal("0")
        for r in dn_qs.values("customer_id", "customer__name").annotate(amount=Sum("grand_total")):
            bucket = totals[r["customer_id"]]
            bucket["name"] = bucket["name"] or r["customer__name"]
            bucket["amount"] += r["amount"] or Decimal("0")

        rows = sorted(
            (
                {
                    "customer_id": cid,
                    "customer": vals["name"],
                    "invoices": vals["invoices"],
                    "amount": vals["amount"],
                }
                for cid, vals in totals.items()
                if vals["invoices"] or vals["amount"]
            ),
            key=lambda row: row["amount"],
            reverse=True,
        )
        return {"rows": rows}

    @staticmethod
    def cash_book(company, date_from=None, date_to=None, bank_account_id=None):
        """Actual cash/bank movements from receipts and supplier payments (Phase 3.3)."""
        from payments.models import CustomerReceipt, ReceiptStatus, SupplierPayment, SupplierPaymentStatus

        receipts = CustomerReceipt.objects.filter(
            company=company, status=ReceiptStatus.POSTED
        ).select_related(
            "customer", "bank_account"
        )
        payments = SupplierPayment.objects.filter(
            company=company, status=SupplierPaymentStatus.POSTED
        ).select_related(
            "supplier", "bank_account"
        )
        if date_from:
            receipts = receipts.filter(receipt_date__gte=date_from)
            payments = payments.filter(payment_date__gte=date_from)
        if date_to:
            receipts = receipts.filter(receipt_date__lte=date_to)
            payments = payments.filter(payment_date__lte=date_to)
        if bank_account_id:
            receipts = receipts.filter(bank_account_id=bank_account_id)
            payments = payments.filter(bank_account_id=bank_account_id)

        rows = []
        inflow = Decimal("0")
        outflow = Decimal("0")
        for r in receipts.order_by("receipt_date", "id"):
            if r.mode == "CREDIT":
                continue
            inflow += r.amount
            rows.append(
                {
                    "date": r.receipt_date,
                    "type": "RECEIPT",
                    "number": r.number,
                    "party": r.customer.name,
                    "mode": r.mode,
                    "bank_account": r.bank_account.name if r.bank_account_id else "",
                    "source": r.source,
                    "inflow": r.amount,
                    "outflow": Decimal("0"),
                    "reference": r.utr or r.reference,
                    "id": r.id,
                }
            )
        for p in payments.order_by("payment_date", "id"):
            if p.mode == "CREDIT":
                continue
            outflow += p.amount
            rows.append(
                {
                    "date": p.payment_date,
                    "type": "SUPPLIER_PAYMENT",
                    "number": p.number,
                    "party": p.supplier.name,
                    "mode": p.mode,
                    "bank_account": p.bank_account.name if p.bank_account_id else "",
                    "source": p.source,
                    "inflow": Decimal("0"),
                    "outflow": p.amount,
                    "reference": p.utr or p.reference,
                    "id": p.id,
                }
            )
        rows.sort(key=lambda x: (x["date"], x["type"], x["id"]))
        opening = ReportService._cash_opening_balance(
            company, date_from=date_from, bank_account_id=bank_account_id
        )

        return {
            "opening": opening,
            "inflow": inflow,
            "outflow": outflow,
            "net": inflow - outflow,
            "closing": opening + inflow - outflow,
            "rows": rows,
            "kind": "document_cash_book",
            "label": "Cash book (receipts & supplier payments)",
            # CR-076: distinguish from accounting.reports.cash_flow (GL 1100/1500).
            "disclaimer": (
                "Document cash book from posted customer receipts and supplier payments — "
                "not the GL cash-flow aid (Cash 1100 / Bank 1500 journal lines), and not a "
                "bank feed forecast. With books on, compare Books Health if the two diverge."
            ),
        }

    @staticmethod
    def _cash_opening_balance(company, *, date_from=None, bank_account_id=None) -> Decimal:
        """Shared by cash_book and cash_totals so the opening-balance logic
        (bank-account opening_balance vs. company.opening_cash_balance, plus
        every pre-window receipt/payment) only lives in one place."""
        from payments.models import BankAccount, CustomerReceipt, ReceiptStatus, SupplierPayment, SupplierPaymentStatus

        initial_opening = Decimal("0")
        if bank_account_id:
            ba = BankAccount.objects.filter(company=company, pk=bank_account_id).first()
            if ba:
                initial_opening = ba.opening_balance or Decimal("0")
        elif company.opening_cash_balance is not None:
            initial_opening = company.opening_cash_balance

        if not date_from:
            return initial_opening

        pre_receipts = CustomerReceipt.objects.filter(
            company=company, status=ReceiptStatus.POSTED, receipt_date__lt=date_from
        ).exclude(mode="CREDIT")
        pre_payments = SupplierPayment.objects.filter(
            company=company, status=SupplierPaymentStatus.POSTED, payment_date__lt=date_from
        ).exclude(mode="CREDIT")
        if bank_account_id:
            pre_receipts = pre_receipts.filter(bank_account_id=bank_account_id)
            pre_payments = pre_payments.filter(bank_account_id=bank_account_id)
        # B5-009: DB-side sums instead of loading every pre-window row into
        # Python just to add up .amount.
        pre_inflow = pre_receipts.aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
        pre_outflow = pre_payments.aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
        return initial_opening + pre_inflow - pre_outflow

    @staticmethod
    def cash_totals(company, date_from=None, date_to=None, bank_account_id=None):
        """B5-009: opening/inflow/outflow/closing via pure DB aggregates --
        no per-row Python iteration, no `rows` list, no select_related joins.
        cash_book still returns the full transaction list for the Cash Book
        report page; this is for callers (cash_position/dashboard) that only
        need the four summary numbers."""
        from payments.models import CustomerReceipt, ReceiptStatus, SupplierPayment, SupplierPaymentStatus

        receipts = CustomerReceipt.objects.filter(
            company=company, status=ReceiptStatus.POSTED
        ).exclude(mode="CREDIT")
        payments = SupplierPayment.objects.filter(
            company=company, status=SupplierPaymentStatus.POSTED
        ).exclude(mode="CREDIT")
        if date_from:
            receipts = receipts.filter(receipt_date__gte=date_from)
            payments = payments.filter(payment_date__gte=date_from)
        if date_to:
            receipts = receipts.filter(receipt_date__lte=date_to)
            payments = payments.filter(payment_date__lte=date_to)
        if bank_account_id:
            receipts = receipts.filter(bank_account_id=bank_account_id)
            payments = payments.filter(bank_account_id=bank_account_id)

        inflow = receipts.aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
        outflow = payments.aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
        opening = ReportService._cash_opening_balance(
            company, date_from=date_from, bank_account_id=bank_account_id
        )
        return {
            "opening": opening,
            "inflow": inflow,
            "outflow": outflow,
            "net": inflow - outflow,
            "closing": opening + inflow - outflow,
        }

    @staticmethod
    def cash_position(company):
        """B5-009: used to call the full cash_book() twice (once unbounded)
        purely to read four numbers off it, materialising + sorting the
        tenant's entire lifetime of receipts and payments into `rows` on
        every dashboard load just to throw that list away. Now uses
        cash_totals, which never builds `rows` at all."""
        from django.utils import timezone

        first_of_month = timezone.localdate().replace(day=1)
        totals_mtd = ReportService.cash_totals(company, date_from=first_of_month)
        totals_all = ReportService.cash_totals(company)
        return {
            "closing": totals_all["closing"],
            "inflow_mtd": totals_mtd["inflow"],
            "outflow_mtd": totals_mtd["outflow"],
            "kind": "actuals",
        }
