"""
Report Service (E5.2–E5.5) — dashboards, registers and exports via
aggregated queries; API clients never scan raw document tables (§9).
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce

from inventory.models import StockBalance
from ledgers.services import LedgerService
from payments.models import PaymentAllocation
from purchases.models import PurchaseInvoice, PurchaseReturn
from sales.models import SalesInvoice, SalesReturn

OPEN_SALES = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)


class ReportService:
    @staticmethod
    def _company_receivables(company) -> Decimal:
        """SQL aggregation — avoids per-customer Python loop."""
        inv = (
            SalesInvoice.objects.filter(company=company, status__in=OPEN_SALES).aggregate(
                t=Coalesce(Sum("grand_total"), Decimal("0"))
            )["t"]
            or Decimal("0")
        )
        rets = (
            SalesReturn.objects.filter(
                company=company, status=SalesReturn.Status.COMPLETED
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )
        allocated = (
            PaymentAllocation.objects.filter(
                company=company, receipt__isnull=False
            ).aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
            or Decimal("0")
        )
        return inv - rets - allocated

    @staticmethod
    def _company_payables(company) -> Decimal:
        inv = (
            PurchaseInvoice.objects.filter(
                company=company, status=PurchaseInvoice.Status.COMPLETED
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )
        rets = (
            PurchaseReturn.objects.filter(
                company=company, status=PurchaseReturn.Status.COMPLETED
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )
        allocated = (
            PaymentAllocation.objects.filter(
                company=company, supplier_payment__isnull=False
            ).aggregate(t=Coalesce(Sum("amount"), Decimal("0")))["t"]
            or Decimal("0")
        )
        return inv - rets - allocated

    @staticmethod
    def receivables_aging(company, as_of: date | None = None):
        """Bucket open sales invoice outstanding by due date (or invoice_date + terms)."""
        as_of = as_of or date.today()
        buckets = {
            "current": Decimal("0"),
            "days_1_30": Decimal("0"),
            "days_31_60": Decimal("0"),
            "days_61_90": Decimal("0"),
            "days_90_plus": Decimal("0"),
        }
        for inv in SalesInvoice.objects.filter(company=company, status__in=OPEN_SALES).only(
            "id", "grand_total", "invoice_date", "due_date", "payment_terms_days"
        ):
            outstanding = LedgerService.sales_invoice_outstanding(inv)
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
        today = date.today()
        month_start = today.replace(day=1)

        sales_today = SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date=today
        ).aggregate(total=Sum("grand_total"), count=Count("id"))
        sales_month = SalesInvoice.objects.filter(
            company=company, status__in=OPEN_SALES, invoice_date__gte=month_start
        ).aggregate(total=Sum("grand_total"), count=Count("id"))
        purchases_month = PurchaseInvoice.objects.filter(
            company=company, status=PurchaseInvoice.Status.COMPLETED, invoice_date__gte=month_start
        ).aggregate(total=Sum("grand_total"), count=Count("id"))

        low_stock = StockBalance.objects.filter(
            company=company, product__status="ACTIVE", on_hand__lte=F("product__reorder_level")
        ).count()

        recent = SalesInvoice.objects.filter(company=company).exclude(
            status=SalesInvoice.Status.DRAFT
        ).order_by("-completed_at")[:5]

        return {
            "sales_today": {"total": sales_today["total"] or 0, "count": sales_today["count"]},
            "sales_this_month": {"total": sales_month["total"] or 0, "count": sales_month["count"]},
            "purchases_this_month": {
                "total": purchases_month["total"] or 0,
                "count": purchases_month["count"],
            },
            "receivables": ReportService._company_receivables(company),
            "payables": ReportService._company_payables(company),
            "low_stock_count": low_stock,
            "receivables_aging": ReportService.receivables_aging(company),
            "recent_invoices": [
                {
                    "id": i.id,
                    "number": i.number,
                    "customer": i.customer.name,
                    "date": i.invoice_date,
                    "status": i.status,
                    "grand_total": i.grand_total,
                }
                for i in recent.select_related("customer")
            ],
        }

    @staticmethod
    def sales_register(company, date_from=None, date_to=None, customer_id=None, status=None):
        qs = SalesInvoice.objects.filter(company=company).exclude(status=SalesInvoice.Status.DRAFT)
        if status:
            qs = qs.filter(status=status)
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        rows = [
            {
                "id": i.id,
                "number": i.number,
                "date": i.invoice_date,
                "customer": i.customer.name,
                "invoice_type": i.invoice_type,
                "status": i.status,
                "taxable": i.taxable_total,
                "cgst": i.cgst_total,
                "sgst": i.sgst_total,
                "igst": i.igst_total,
                "grand_total": i.grand_total,
            }
            for i in qs.select_related("customer")
        ]
        totals = qs.aggregate(taxable=Sum("taxable_total"), grand=Sum("grand_total"))
        return {
            "rows": rows,
            "totals": {"taxable": totals["taxable"] or 0, "grand_total": totals["grand"] or 0},
        }

    @staticmethod
    def purchase_register(company, date_from=None, date_to=None, supplier_id=None, status=None):
        qs = PurchaseInvoice.objects.filter(company=company).exclude(
            status=PurchaseInvoice.Status.DRAFT
        )
        if status:
            qs = qs.filter(status=status)
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        rows = [
            {
                "id": i.id,
                "number": i.number,
                "date": i.invoice_date,
                "supplier": i.supplier.name,
                "status": i.status,
                "taxable": i.taxable_total,
                "cgst": i.cgst_total,
                "sgst": i.sgst_total,
                "igst": i.igst_total,
                "grand_total": i.grand_total,
            }
            for i in qs.select_related("supplier")
        ]
        totals = qs.aggregate(taxable=Sum("taxable_total"), grand=Sum("grand_total"))
        return {
            "rows": rows,
            "totals": {"taxable": totals["taxable"] or 0, "grand_total": totals["grand"] or 0},
        }

    @staticmethod
    def inventory_summary(company):
        balances = StockBalance.objects.filter(company=company).select_related("product")
        rows = []
        total_value = Decimal("0")
        for b in balances:
            value = b.on_hand * b.product.purchase_price
            total_value += value
            rows.append({
                "product_id": b.product_id,
                "product": b.product.name,
                "sku": b.product.sku,
                "on_hand": b.on_hand,
                "reserved": b.reserved,
                "available": b.available,
                "reorder_level": b.product.reorder_level,
                "stock_value": value,
            })
        return {"rows": rows, "total_stock_value": total_value}

    @staticmethod
    def product_sales(company, date_from=None, date_to=None):
        from sales.models import SalesItem

        qs = SalesItem.objects.filter(invoice__company=company, invoice__status__in=OPEN_SALES)
        if date_from:
            qs = qs.filter(invoice__invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice__invoice_date__lte=date_to)
        rows = (
            qs.values("product_id", "product__name")
            .annotate(quantity=Sum("quantity"), amount=Sum("line_total"))
            .order_by("-amount")
        )
        return {
            "rows": [
                {
                    "product_id": r["product_id"],
                    "product": r["product__name"],
                    "quantity": r["quantity"],
                    "amount": r["amount"],
                }
                for r in rows
            ]
        }

    @staticmethod
    def customer_sales(company, date_from=None, date_to=None):
        qs = SalesInvoice.objects.filter(company=company, status__in=OPEN_SALES)
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        rows = (
            qs.values("customer_id", "customer__name")
            .annotate(invoices=Count("id"), amount=Sum("grand_total"))
            .order_by("-amount")
        )
        return {
            "rows": [
                {
                    "customer_id": r["customer_id"],
                    "customer": r["customer__name"],
                    "invoices": r["invoices"],
                    "amount": r["amount"],
                }
                for r in rows
            ]
        }
