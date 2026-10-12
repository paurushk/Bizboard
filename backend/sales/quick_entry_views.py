"""Quick Order Entry support endpoints (docs/QUICK_ORDER_ENTRY_IMPLEMENTATION_PLAN.md, QOE-06)."""

from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import CanCreateSales, HasCompany, get_company_user
from masters.models import Customer, Product

from .models import SalesInvoice, SalesItem, SalesOrder, SalesOrderItem

RECENT_DOCS = 40
MAX_CUSTOMERS = 6
MAX_PRODUCTS = 8


class QuickEntryRecentsView(APIView):
    """The signed-in rep's recent customers and products, active ones only.

    Looks at the rep's own recent invoices (salesperson, or creator when no salesperson was set)
    and sales orders, so each rep sees their own round rather than the whole company's.
    """

    def get_permissions(self):
        return [IsAuthenticated(), HasCompany(), CanCreateSales()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        company = get_company_user(request).company
        uid = request.user.id

        invoices = list(
            SalesInvoice.objects.filter(company=company)
            .filter(Q(salesperson_id=uid) | Q(salesperson__isnull=True, created_by_id=uid))
            .order_by("-id")
            .values_list("id", "customer_id")[:RECENT_DOCS]
        )
        orders = list(
            SalesOrder.objects.filter(company=company, created_by_id=uid)
            .order_by("-id")
            .values_list("id", "customer_id")[:RECENT_DOCS]
        )

        customer_ids: list[int] = []
        for _id, cid in sorted(invoices + orders, key=lambda row: -row[0]):
            if cid and cid not in customer_ids:
                customer_ids.append(cid)
        active = {
            c.id: c
            for c in Customer.objects.filter(
                company=company, id__in=customer_ids, status=Customer.Status.ACTIVE, is_deleted=False
            )
        }
        customers = [{"id": cid, "name": active[cid].name} for cid in customer_ids if cid in active][:MAX_CUSTOMERS]

        product_ids: list[int] = []
        rows = list(
            SalesItem.objects.filter(invoice_id__in=[i for i, _ in invoices])
            .order_by("-id")
            .values_list("product_id", flat=True)[:200]
        ) + list(
            SalesOrderItem.objects.filter(sales_order_id__in=[i for i, _ in orders])
            .order_by("-id")
            .values_list("product_id", flat=True)[:200]
        )
        for pid in rows:
            if pid not in product_ids:
                product_ids.append(pid)
        live = set(
            Product.objects.filter(
                company=company, id__in=product_ids, status="ACTIVE", is_deleted=False
            ).values_list("id", flat=True)
        )
        products = [{"id": pid} for pid in product_ids if pid in live][:MAX_PRODUCTS]
        return Response({"customers": customers, "products": products})
