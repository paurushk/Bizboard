"""Search Service — universal search across business entities (E1.11)."""

from contextlib import contextmanager

from django.db import connection, transaction
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user
from masters.models import Customer, Product, Supplier
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice

LIMIT = 10
SEARCH_STATEMENT_TIMEOUT_MS = 5000


@contextmanager
def _search_query_guard():
    """BB-000492: cap search query time on PostgreSQL; no-op on SQLite."""
    if connection.vendor != "postgresql":
        yield
        return
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = %s", [SEARCH_STATEMENT_TIMEOUT_MS])
        yield


class UniversalSearchView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]
    throttle_scope = "search"

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response({"customers": [], "suppliers": [], "products": [], "invoices": []})
        cu = get_company_user(request)
        company = cu.company

        is_owner = cu.role == "OWNER"
        # BB-000297/Wave 12B: never surface party PII (phone/gstin) to VIEWER;
        # non-viewers still need a sales/purchase/financial capability.
        can_view_sales = cu.role != "VIEWER" and (
            is_owner or cu.can_create_sales or cu.can_view_financial_reports
        )
        can_view_purchases = cu.role != "VIEWER" and (
            is_owner or cu.can_create_purchases or cu.can_view_financial_reports
        )
        can_view_financials = is_owner or cu.can_view_financial_reports

        with _search_query_guard():
            customers = (
                Customer.objects.filter(company=company).filter(
                    Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q)
                )[:LIMIT]
                if can_view_sales
                else []
            )
            suppliers = (
                Supplier.objects.filter(company=company).filter(
                    Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q)
                )[:LIMIT]
                if can_view_purchases
                else []
            )
            products = (
                Product.objects.filter(company=company).filter(
                    Q(barcode__iexact=q) | Q(sku__iexact=q) | Q(name__icontains=q)
                )[:LIMIT]
                if (can_view_sales or can_view_purchases)
                else []
            )
            # Selling price is business-sensitive; strip it for roles without
            # sales/purchase/financial visibility (BB-000297).
            show_pricing = can_view_sales or can_view_purchases

            invoices = []
            # Exclude invoice hits unless the user can view financial reports.
            if can_view_financials:
                sales_invoices = SalesInvoice.objects.filter(
                    company=company, number__icontains=q
                ).select_related("customer")[:LIMIT]
                purchase_invoices = PurchaseInvoice.objects.filter(
                    company=company, number__icontains=q
                ).select_related("supplier")[:LIMIT]
                invoices = [
                    {
                        "id": i.id, "kind": "sales", "number": i.number,
                        "party": i.customer.name, "status": i.status, "grand_total": i.grand_total,
                    }
                    for i in sales_invoices
                ] + [
                    {
                        "id": i.id, "kind": "purchase", "number": i.number,
                        "party": i.supplier.name, "status": i.status, "grand_total": i.grand_total,
                    }
                    for i in purchase_invoices
                ]

        return Response({
            "customers": [
                {"id": c.id, "name": c.name, "phone": c.phone, "status": c.status}
                for c in customers
            ],
            "suppliers": [
                {"id": s.id, "name": s.name, "phone": s.phone} for s in suppliers
            ],
            "products": [
                {
                    "id": p.id, "name": p.name, "sku": p.sku, "barcode": p.barcode,
                    **({"selling_price": p.selling_price, "gst_rate": p.gst_rate} if show_pricing else {}),
                    "status": p.status,
                }
                for p in products
            ],
            "invoices": invoices,
        })
