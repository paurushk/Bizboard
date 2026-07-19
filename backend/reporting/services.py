"""
Report Service (E5.2–E5.5) — dashboards, registers and exports via
aggregated queries; API clients never scan raw document tables (§9).
"""

from datetime import date
from decimal import Decimal

from django.db.models import Count, F, Sum

from inventory.models import StockBalance
from ledgers.services import LedgerService
from masters.models import Customer, Supplier
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice

OPEN_SALES = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)


class ReportService:
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

        receivables = sum(
            (LedgerService.customer_outstanding(company, c) for c in Customer.objects.filter(company=company)),
            Decimal("0"),
        )
        payables = sum(
            (LedgerService.supplier_outstanding(company, s) for s in Supplier.objects.filter(company=company)),
            Decimal("0"),
        )
        low_stock = StockBalance.objects.filter(
            company=company, product__status="ACTIVE", on_hand__lte=F("product__reorder_level")
        ).count()

        recent = SalesInvoice.objects.filter(company=company).exclude(
            status=SalesInvoice.Status.DRAFT
        ).order_by("-completed_at")[:5]

        return {
            "sales_today": {"total": sales_today["total"] or 0, "count": sales_today["count"]},
            "sales_this_month": {"total": sales_month["total"] or 0, "count": sales_month["count"]},
            "purchases_this_month": {"total": purchases_month["total"] or 0, "count": purchases_month["count"]},
            "receivables": receivables,
            "payables": payables,
            "low_stock_count": low_stock,
            "recent_invoices": [
                {
                    "id": i.id, "number": i.number, "customer": i.customer.name,
                    "date": i.invoice_date, "status": i.status, "grand_total": i.grand_total,
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
                "id": i.id, "number": i.number, "date": i.invoice_date,
                "customer": i.customer.name, "invoice_type": i.invoice_type,
                "status": i.status, "taxable": i.taxable_total,
                "cgst": i.cgst_total, "sgst": i.sgst_total, "igst": i.igst_total,
                "grand_total": i.grand_total,
            }
            for i in qs.select_related("customer")
        ]
        totals = qs.aggregate(taxable=Sum("taxable_total"), grand=Sum("grand_total"))
        return {"rows": rows, "totals": {"taxable": totals["taxable"] or 0, "grand_total": totals["grand"] or 0}}

    @staticmethod
    def purchase_register(company, date_from=None, date_to=None, supplier_id=None, status=None):
        qs = PurchaseInvoice.objects.filter(company=company).exclude(status=PurchaseInvoice.Status.DRAFT)
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
                "id": i.id, "number": i.number, "date": i.invoice_date,
                "supplier": i.supplier.name, "status": i.status,
                "taxable": i.taxable_total, "cgst": i.cgst_total,
                "sgst": i.sgst_total, "igst": i.igst_total, "grand_total": i.grand_total,
            }
            for i in qs.select_related("supplier")
        ]
        totals = qs.aggregate(taxable=Sum("taxable_total"), grand=Sum("grand_total"))
        return {"rows": rows, "totals": {"taxable": totals["taxable"] or 0, "grand_total": totals["grand"] or 0}}

    @staticmethod
    def inventory_summary(company):
        balances = StockBalance.objects.filter(company=company).select_related("product")
        rows = []
        total_value = Decimal("0")
        for b in balances:
            value = b.on_hand * b.product.purchase_price
            total_value += value
            rows.append({
                "product_id": b.product_id, "product": b.product.name,
                "sku": b.product.sku, "on_hand": b.on_hand, "reserved": b.reserved,
                "available": b.available, "reorder_level": b.product.reorder_level,
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
                    "product_id": r["product_id"], "product": r["product__name"],
                    "quantity": r["quantity"], "amount": r["amount"],
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
                    "customer_id": r["customer_id"], "customer": r["customer__name"],
                    "invoices": r["invoices"], "amount": r["amount"],
                }
                for r in rows
            ]
        }
