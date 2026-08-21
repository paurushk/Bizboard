"""
Report Service (E5.2–E5.5) — dashboards, registers and exports via
aggregated queries; API clients never scan raw document tables (§9).
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventory.models import StockBalance
from ledgers.services import LedgerService
from payments.models import PaymentAllocation
from purchases.models import (
    PurchaseCreditNote,
    PurchaseDebitNote,
    PurchaseInvoice,
    PurchaseReturn,
)
from sales.models import (
    SalesCreditNote,
    SalesDebitNote,
    SalesInvoice,
    SalesReturn,
)

OPEN_SALES = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)
NET_SALES = (SalesInvoice.Status.COMPLETED,)


def _party_name(obj, attr="customer"):
    party = getattr(obj, attr, None)
    return (getattr(party, "name", None) or "").strip() or "—"


def _as_sort_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.min


def _money(value, negate=False):
    amount = value if value is not None else Decimal("0")
    return -amount if negate else amount


class ReportService:
    @staticmethod
    def _company_receivables(company) -> Decimal:
        """GAP-002: dashboard AR is LedgerService, not a parallel SQL formula."""
        return LedgerService.company_receivables(company)

    @staticmethod
    def _company_payables(company) -> Decimal:
        """GAP-002: dashboard AP is LedgerService, not a parallel SQL formula."""
        return LedgerService.company_payables(company)

    @staticmethod
    def receivables_aging(company, as_of: date | None = None):
        """Bucket open sales invoice outstanding by due date (or invoice_date + terms)."""
        as_of = as_of or timezone.localdate()
        buckets = {
            "current": Decimal("0"),
            "days_1_30": Decimal("0"),
            "days_31_60": Decimal("0"),
            "days_61_90": Decimal("0"),
            "days_90_plus": Decimal("0"),
        }
        invoices = list(
            SalesInvoice.objects.filter(company=company, status__in=OPEN_SALES).only(
                "id", "grand_total", "tcs_amount", "invoice_date", "due_date", "payment_terms_days"
            )
        )
        if not invoices:
            return buckets
        # BUG-302: precompute CNs/allocations in bulk. Wave 3: sales returns are
        # stock-only — AR relief is via auto credit notes (do not subtract returns).
        invoice_ids = [inv.id for inv in invoices]
        cn_by_id = dict(
            SalesCreditNote.objects.filter(
                sales_invoice_id__in=invoice_ids, status=SalesCreditNote.Status.COMPLETED
            ).values("sales_invoice_id").annotate(total=Sum("grand_total"))
            .values_list("sales_invoice_id", "total")
        )
        dn_by_id = dict(
            SalesDebitNote.objects.filter(
                sales_invoice_id__in=invoice_ids, status=SalesDebitNote.Status.COMPLETED
            ).values("sales_invoice_id").annotate(total=Sum("grand_total"))
            .values_list("sales_invoice_id", "total")
        )
        allocated_by_id = dict(
            PaymentAllocation.objects.filter(
                sales_invoice_id__in=invoice_ids, reversed_at__isnull=True
            )
            .values("sales_invoice_id").annotate(total=Sum("amount"))
            .values_list("sales_invoice_id", "total")
        )
        for inv in invoices:
            tcs = Decimal(str(getattr(inv, "tcs_amount", 0) or 0))
            outstanding = (
                inv.grand_total
                + tcs
                - (cn_by_id.get(inv.id) or Decimal("0"))
                + (dn_by_id.get(inv.id) or Decimal("0"))
                - (allocated_by_id.get(inv.id) or Decimal("0"))
            )
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

        sales_today = SalesInvoice.objects.filter(
            company=company, status__in=NET_SALES, invoice_date=today
        ).exclude(notes="TALLY_OPENING").aggregate(total=Sum("grand_total"), count=Count("id"))
        sales_month = SalesInvoice.objects.filter(
            company=company, status__in=NET_SALES, invoice_date__gte=month_start
        ).exclude(notes="TALLY_OPENING").aggregate(total=Sum("grand_total"), count=Count("id"))
        returns_today = (
            SalesReturn.objects.filter(
                company=company, status=SalesReturn.Status.COMPLETED, return_date=today,
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )
        returns_month = (
            SalesReturn.objects.filter(
                company=company, status=SalesReturn.Status.COMPLETED, return_date__gte=month_start,
            ).aggregate(t=Coalesce(Sum("grand_total"), Decimal("0")))["t"]
            or Decimal("0")
        )
        purchases_month = PurchaseInvoice.objects.filter(
            company=company, status=PurchaseInvoice.Status.COMPLETED, invoice_date__gte=month_start
        ).exclude(notes="TALLY_OPENING").aggregate(total=Sum("grand_total"), count=Count("id"))

        low_stock = (
            StockBalance.objects.filter(company=company, product__status="ACTIVE")
            .annotate(_available=F("on_hand") - F("reserved"))
            .filter(_available__lte=F("product__reorder_level"))
            .count()
        )

        recent = SalesInvoice.objects.filter(company=company).exclude(
            status=SalesInvoice.Status.DRAFT
        ).order_by("-completed_at")[:5]

        return {
            "sales_today": {
                "total": (sales_today["total"] or Decimal("0")) - returns_today,
                "count": sales_today["count"],
            },
            "sales_this_month": {
                "total": (sales_month["total"] or Decimal("0")) - returns_month,
                "count": sales_month["count"],
            },
            "purchases_this_month": {
                "total": purchases_month["total"] or 0,
                "count": purchases_month["count"],
            },
            "receivables": ReportService._company_receivables(company),
            "payables": ReportService._company_payables(company),
            "low_stock_count": low_stock,
            "receivables_aging": ReportService.receivables_aging(company),
            "cash_position": ReportService.cash_position(company),
            "recent_invoices": [
                {
                    "id": i.id,
                    "number": i.number,
                    "customer": _party_name(i, "customer"),
                    "date": i.invoice_date,
                    "status": i.status,
                    "grand_total": i.grand_total,
                }
                for i in recent.select_related("customer")
            ],
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
        if customer_id:
            cn_qs = cn_qs.filter(customer_id=customer_id)
            dn_qs = dn_qs.filter(customer_id=customer_id)
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
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
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

        balances = StockBalance.objects.filter(company=company).select_related("product", "warehouse")
        if warehouse_id:
            balances = balances.filter(warehouse_id=warehouse_id)
        valued = InventoryValuationService.valuation(
            company,
            warehouse=warehouse_id,
        )
        value_by_key = {
            (row["warehouse"], row["product"], row["batch"]): row["value"]
            for row in valued
        }
        rows = []
        total_value = Decimal("0")
        for b in balances:
            value = value_by_key.get((b.warehouse_id, b.product_id, b.batch_id))
            if value is None:
                unit = InventoryValuationService.unit_cost(
                    company, b.product, warehouse=b.warehouse, batch=b.batch,
                )
                value = (b.on_hand or Decimal("0")) * (unit or Decimal("0"))
            total_value += value
            rows.append({
                "product_id": b.product_id,
                "product": b.product.name,
                "sku": b.product.sku,
                "warehouse_id": b.warehouse_id,
                "on_hand": b.on_hand,
                "reserved": b.reserved,
                "available": b.available,
                "reorder_level": b.product.reorder_level,
                "stock_value": value,
            })
        return {"rows": rows, "total_stock_value": total_value}

    @staticmethod
    def payables_aging(company, as_of: date | None = None):
        """Bucket open purchase invoice outstanding by due date."""
        from ledgers.services import LedgerService

        as_of = as_of or timezone.localdate()
        buckets = {
            "current": Decimal("0"),
            "days_1_30": Decimal("0"),
            "days_31_60": Decimal("0"),
            "days_61_90": Decimal("0"),
            "days_90_plus": Decimal("0"),
        }
        invoices = PurchaseInvoice.objects.filter(
            company=company,
            status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED),
        ).only("id", "grand_total", "invoice_date", "due_date", "payment_terms_days")
        for inv in invoices:
            outstanding = LedgerService.purchase_invoice_outstanding(inv)
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
        from sales.models import SalesItem

        qs = SalesItem.objects.filter(invoice__company=company, invoice__status__in=NET_SALES)
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
        qs = SalesInvoice.objects.filter(company=company, status__in=NET_SALES)
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

    @staticmethod
    def cash_book(company, date_from=None, date_to=None, bank_account_id=None):
        """Actual cash/bank movements from receipts and supplier payments (Phase 3.3)."""
        from payments.models import CustomerReceipt, ReceiptStatus, SupplierPayment

        receipts = CustomerReceipt.objects.filter(
            company=company, status=ReceiptStatus.POSTED
        ).select_related(
            "customer", "bank_account"
        )
        payments = SupplierPayment.objects.filter(company=company).select_related(
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
        opening = Decimal("0")
        from payments.models import BankAccount

        if bank_account_id:
            ba = BankAccount.objects.filter(company=company, pk=bank_account_id).first()
            if ba:
                opening = ba.opening_balance or Decimal("0")
        elif company.opening_cash_balance is not None:
            opening = company.opening_cash_balance
        return {
            "opening": opening,
            "inflow": inflow,
            "outflow": outflow,
            "net": inflow - outflow,
            "closing": opening + inflow - outflow,
            "rows": rows,
            "kind": "actuals",
            "disclaimer": "Cash book shows recorded receipts and payments — not a bank feed forecast.",
        }

    @staticmethod
    def cash_position(company):
        book = ReportService.cash_book(company)
        return {
            "closing": book["closing"],
            "inflow_mtd": book["inflow"],
            "outflow_mtd": book["outflow"],
            "kind": "actuals",
        }
