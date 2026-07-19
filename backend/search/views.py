"""Search Service — universal search across business entities (E1.11)."""

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user
from masters.models import Customer, Product, Supplier
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice

LIMIT = 10


class UniversalSearchView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return Response({"customers": [], "suppliers": [], "products": [], "invoices": []})
        company = get_company_user(request).company

        customers = Customer.objects.filter(company=company).filter(
            Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q)
        )[:LIMIT]
        suppliers = Supplier.objects.filter(company=company).filter(
            Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q)
        )[:LIMIT]
        # Product multi-mode: barcode / SKU exact hit first, then name.
        products = Product.objects.filter(company=company).filter(
            Q(barcode__iexact=q) | Q(sku__iexact=q) | Q(name__icontains=q)
        )[:LIMIT]
        sales_invoices = SalesInvoice.objects.filter(
            company=company, number__icontains=q
        ).select_related("customer")[:LIMIT]
        purchase_invoices = PurchaseInvoice.objects.filter(
            company=company, number__icontains=q
        ).select_related("supplier")[:LIMIT]

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
                    "selling_price": p.selling_price, "gst_rate": p.gst_rate, "status": p.status,
                }
                for p in products
            ],
            "invoices": [
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
            ],
        })
