import csv
import io
from datetime import date

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, get_company_user

from .services import ReportService


def _parse_date(value):
    return date.fromisoformat(value) if value else None


class BaseReportView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    @property
    def company(self):
        return get_company_user(self.request).company


class DashboardView(BaseReportView):
    def get(self, request):
        return Response(ReportService.dashboard(self.company))


class SalesRegisterView(BaseReportView):
    def get(self, request):
        return Response(ReportService.sales_register(
            self.company,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
            customer_id=request.query_params.get("customer"),
            status=request.query_params.get("status"),
        ))


class PurchaseRegisterView(BaseReportView):
    def get(self, request):
        return Response(ReportService.purchase_register(
            self.company,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
            supplier_id=request.query_params.get("supplier"),
            status=request.query_params.get("status"),
        ))


class InventorySummaryView(BaseReportView):
    def get(self, request):
        return Response(ReportService.inventory_summary(self.company))


class ProductSalesView(BaseReportView):
    def get(self, request):
        return Response(ReportService.product_sales(
            self.company,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
        ))


class CustomerSalesView(BaseReportView):
    def get(self, request):
        return Response(ReportService.customer_sales(
            self.company,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
        ))


EXPORTS = {
    "sales-register": lambda company, params: ReportService.sales_register(
        company,
        date_from=_parse_date(params.get("date_from")),
        date_to=_parse_date(params.get("date_to")),
    )["rows"],
    "purchase-register": lambda company, params: ReportService.purchase_register(
        company,
        date_from=_parse_date(params.get("date_from")),
        date_to=_parse_date(params.get("date_to")),
    )["rows"],
    "inventory-summary": lambda company, params: ReportService.inventory_summary(company)["rows"],
}


class ExportView(BaseReportView):
    """CSV export of registers via Report Service (E5.8)."""

    def get(self, request, report):
        if report not in EXPORTS:
            raise BusinessRuleError(f"Unknown export '{report}'. Available: {', '.join(EXPORTS)}.")
        rows = EXPORTS[report](self.company, request.query_params)
        buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{report}.csv"'
        return response
