from datetime import date

from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import CanViewFinancialReports, HasCompany, get_company_user
from masters.models import Customer, Supplier

from .services import LedgerService


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (ValueError, TypeError):
        return None


class CustomerLedgerListView(APIView):
    """Outstanding summary for all customers (E5.6)."""

    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request):
        company = get_company_user(request).company
        # BUG-301: one bulk SQL aggregation instead of 3N+1 queries.
        outstanding_by_id = LedgerService.bulk_customer_outstanding(company)
        rows = [
            {
                "customer_id": c.id,
                "customer_name": c.name,
                "status": c.status,
                "outstanding": outstanding_by_id.get(c.id, 0),
            }
            for c in Customer.objects.filter(company=company)
        ]
        return Response({"results": rows})


class CustomerLedgerDetailView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request, customer_id):
        company = get_company_user(request).company
        customer = get_object_or_404(Customer, pk=customer_id, company=company)
        entries = LedgerService.customer_statement(
            company, customer,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
        )
        return Response({
            "customer_id": customer.id,
            "customer_name": customer.name,
            "outstanding": LedgerService.customer_outstanding(company, customer),
            "entries": entries,
        })


class SupplierLedgerListView(APIView):
    """Outstanding summary for all suppliers (E5.7)."""

    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request):
        company = get_company_user(request).company
        outstanding_by_id = LedgerService.bulk_supplier_outstanding(company)
        rows = [
            {
                "supplier_id": s.id,
                "supplier_name": s.name,
                "outstanding": outstanding_by_id.get(s.id, 0),
            }
            for s in Supplier.objects.filter(company=company)
        ]
        return Response({"results": rows})


class SupplierLedgerDetailView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request, supplier_id):
        company = get_company_user(request).company
        supplier = get_object_or_404(Supplier, pk=supplier_id, company=company)
        entries = LedgerService.supplier_statement(
            company, supplier,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
        )
        return Response({
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "outstanding": LedgerService.supplier_outstanding(company, supplier),
            "entries": entries,
        })
