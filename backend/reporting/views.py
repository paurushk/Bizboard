import csv
import io
from datetime import date

from django.http import Http404, HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.csv_utils import csv_safe
from core.exceptions import BusinessRuleError
from core.permissions import CanExport, CanViewFinancialReports, HasCompany, IsOwner, get_company_user
from core.services.feature_flags import build_feature_flags
from core.throttles import CompanyRateThrottle

from masters.models import Customer, Supplier

from .gst_health import build_gst_health
from .gst_periods import reopen_period, soft_close_period
from .gst_returns import (
    build_ca_pack_zip,
    build_gstr1,
    build_gstr3b,
    build_gstr9,
    gstr_return_to_xlsx,
    parse_period,
    persist_snapshot,
    to_gstn_json,
)
from .models import Gstr2bIngest
from .permissions import assert_gstr_enabled
from .serializers import Gstr2bIngestSerializer
from .services import ReportService


def _tds_worksheets_readable(company) -> bool:
    """Owner may export worksheets when TDS is enabled or TDS/TCS was already posted."""
    if build_feature_flags(company=company).get("ENABLE_TDS"):
        return True
    from payments.models import SupplierPayment
    from purchases.models import PurchaseInvoice
    from sales.models import SalesInvoice

    return (
        PurchaseInvoice.objects.filter(company=company, tds_amount__gt=0).exists()
        or SalesInvoice.objects.filter(company=company, tcs_amount__gt=0).exists()
        or SupplierPayment.objects.filter(company=company, tds_amount__gt=0).exists()
    )


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        return None


def _int_or_none(value):
    if value in (None, "", "undefined", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _maybe_gstn_json(request, payload):
    export_format = (request.query_params.get("format") or "json").lower()
    if export_format not in ("gstn-json", "gstn_json"):
        return None
    from django.conf import settings

    env = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
    allowed = bool(getattr(settings, "ENABLE_GSTN_JSON", False))
    if env in ("production", "staging") and not allowed:
        raise BusinessRuleError("GSTN-shaped JSON export is disabled in this environment.")
    if not allowed and env not in ("development", "dev", "test", "local"):
        raise BusinessRuleError("GSTN-shaped JSON export is disabled.")
    return Response(to_gstn_json(payload))


class BaseReportView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    @property
    def company(self):
        return get_company_user(self.request).company


class DashboardView(BaseReportView):
    def get(self, request):
        # BB-000513: KPIs are live aggregates over source documents — no CQRS rollup layer.
        return Response(ReportService.dashboard(self.company))


class SalesRegisterView(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "heavy_reports"

    def get(self, request):
        return Response(ReportService.sales_register(
            self.company,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
            customer_id=_int_or_none(request.query_params.get("customer")),
            status=request.query_params.get("status"),
            warehouse_id=_int_or_none(request.query_params.get("warehouse")),
            company_gstin_id=_int_or_none(
                request.query_params.get("company_gstin")
                or request.query_params.get("gstin")
            ),
        ))


class PurchaseRegisterView(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "heavy_reports"

    def get(self, request):
        return Response(ReportService.purchase_register(
            self.company,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
            supplier_id=_int_or_none(request.query_params.get("supplier")),
            status=request.query_params.get("status"),
            warehouse_id=_int_or_none(request.query_params.get("warehouse")),
        ))


class InventorySummaryView(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "heavy_reports"

    def get(self, request):
        return Response(ReportService.inventory_summary(
            self.company,
            warehouse_id=request.query_params.get("warehouse"),
        ))


class ProductSalesView(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "heavy_reports"

    def get(self, request):
        return Response(ReportService.product_sales(
            self.company,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
        ))


class CustomerSalesView(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "heavy_reports"

    def get(self, request):
        return Response(ReportService.customer_sales(
            self.company,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
        ))


class CashBookView(BaseReportView):
    """Cash book actuals — JSON or XLSX."""

    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "heavy_reports"

    def get_permissions(self):
        # BB-000137: XLSX export requires CanExport (JSON preview keeps financial-report ACL).
        export_format = (
            self.request.query_params.get("export")
            or self.request.query_params.get("format")
            or "json"
        ).lower()
        if export_format == "xlsx":
            return [IsAuthenticated(), HasCompany(), CanExport()]
        return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]

    def get(self, request):
        payload = ReportService.cash_book(
            self.company,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
            bank_account_id=request.query_params.get("bank_account"),
        )
        # Prefer export= over format= — DRF treats ?format= as renderer negotiation.
        export_format = (
            request.query_params.get("export")
            or request.query_params.get("format")
            or "json"
        ).lower()
        if export_format in ("json", "api"):
            return Response(payload)
        if export_format == "xlsx":
            from io import BytesIO

            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.title = "Cash book"
            headers = [
                "date",
                "type",
                "number",
                "party",
                "mode",
                "bank_account",
                "source",
                "inflow",
                "outflow",
                "reference",
            ]
            ws.append(headers)
            for row in payload.get("rows") or []:
                ws.append([row.get(h) for h in headers])
            ws2 = wb.create_sheet("Summary")
            ws2.append(["opening", payload.get("opening")])
            ws2.append(["inflow", payload.get("inflow")])
            ws2.append(["outflow", payload.get("outflow")])
            ws2.append(["closing", payload.get("closing")])
            buf = BytesIO()
            wb.save(buf)
            response = HttpResponse(
                buf.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = 'attachment; filename="cash-book.xlsx"'
            return response
        raise BusinessRuleError("Unsupported format. Use export=json or export=xlsx.")


def _customer_export(company, params):
    qs = Customer.objects.filter(company=company).order_by("name")
    status = params.get("status")
    if status:
        qs = qs.filter(status=status)
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "email": c.email,
            "gstin": c.gstin,
            "state": c.state,
            "taxpayer_type": c.taxpayer_type,
            "status": c.status,
            "billing_address": c.billing_address,
            "shipping_address": c.shipping_address,
            "credit_limit": c.credit_limit,
            "credit_days": c.credit_days,
            "gstin_verification_status": c.gstin_verification_status,
        }
        for c in qs
    ]


def _supplier_export(company, params):
    qs = Supplier.objects.filter(company=company).order_by("name")
    status = params.get("status")
    if status:
        qs = qs.filter(status=status)
    return [
        {
            "id": s.id,
            "name": s.name,
            "phone": s.phone,
            "email": s.email,
            "gstin": s.gstin,
            "state": s.state,
            "status": s.status,
            "billing_address": s.billing_address,
            "shipping_address": s.shipping_address,
            "gstin_verification_status": s.gstin_verification_status,
        }
        for s in qs
    ]


EXPORTS = {
    "sales-register": lambda company, params: ReportService.sales_register(
        company,
        date_from=_parse_date(params.get("date_from")),
        date_to=_parse_date(params.get("date_to")),
        customer_id=_int_or_none(params.get("customer")),
        status=params.get("status"),
    )["rows"],
    "sales": lambda company, params: ReportService.sales_register(
        company,
        date_from=_parse_date(params.get("date_from")),
        date_to=_parse_date(params.get("date_to")),
        customer_id=_int_or_none(params.get("customer")),
        status=params.get("status"),
    )["rows"],
    "purchase-register": lambda company, params: ReportService.purchase_register(
        company,
        date_from=_parse_date(params.get("date_from")),
        date_to=_parse_date(params.get("date_to")),
        supplier_id=_int_or_none(params.get("supplier")),
        status=params.get("status"),
    )["rows"],
    "purchases": lambda company, params: ReportService.purchase_register(
        company,
        date_from=_parse_date(params.get("date_from")),
        date_to=_parse_date(params.get("date_to")),
        supplier_id=_int_or_none(params.get("supplier")),
        status=params.get("status"),
    )["rows"],
    "inventory-summary": lambda company, params: ReportService.inventory_summary(company)["rows"],
    "inventory": lambda company, params: ReportService.inventory_summary(company)["rows"],
    "customers": lambda company, params: _customer_export(company, params),
    "customers-register": lambda company, params: _customer_export(company, params),
    "customer-list": lambda company, params: _customer_export(company, params),
    "suppliers": lambda company, params: _supplier_export(company, params),
    "suppliers-register": lambda company, params: _supplier_export(company, params),
    "supplier-list": lambda company, params: _supplier_export(company, params),
}

# BUG-323: known column names per export, used as a CSV header fallback
# when a filter narrows the result down to zero rows.
EXPORT_FIELDS = {
    "sales-register": [
        "id", "number", "date", "customer", "invoice_type", "status",
        "taxable", "cgst", "sgst", "igst", "grand_total",
    ],
    "sales": [
        "id", "number", "date", "customer", "invoice_type", "status",
        "taxable", "cgst", "sgst", "igst", "grand_total",
    ],
    "purchase-register": [
        "id", "number", "date", "supplier", "status",
        "taxable", "cgst", "sgst", "igst", "grand_total",
    ],
    "purchases": [
        "id", "number", "date", "supplier", "status",
        "taxable", "cgst", "sgst", "igst", "grand_total",
    ],
    "inventory-summary": [
        "product_id", "product", "sku", "on_hand", "reserved",
        "available", "reorder_level", "stock_value",
    ],
    "inventory": [
        "product_id", "product", "sku", "on_hand", "reserved",
        "available", "reorder_level", "stock_value",
    ],
    "customers": [
        "id", "name", "phone", "email", "gstin", "state", "taxpayer_type",
        "status", "billing_address", "shipping_address", "credit_limit", "credit_days", "gstin_verification_status",
    ],
    "customers-register": [
        "id", "name", "phone", "email", "gstin", "state", "taxpayer_type",
        "status", "billing_address", "shipping_address", "credit_limit", "credit_days", "gstin_verification_status",
    ],
    "customer-list": [
        "id", "name", "phone", "email", "gstin", "state", "taxpayer_type",
        "status", "billing_address", "shipping_address", "credit_limit", "credit_days", "gstin_verification_status",
    ],
    "suppliers": [
        "id", "name", "phone", "email", "gstin", "state", "status",
        "billing_address", "shipping_address", "gstin_verification_status",
    ],
    "suppliers-register": [
        "id", "name", "phone", "email", "gstin", "state", "status",
        "billing_address", "shipping_address", "gstin_verification_status",
    ],
    "supplier-list": [
        "id", "name", "phone", "email", "gstin", "state", "status",
        "billing_address", "shipping_address", "gstin_verification_status",
    ],
}


class GstReturnView(BaseReportView):
    """Offline GSTR-1 / GSTR-3B JSON preview or XLSX download."""

    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"
    build_fn = None

    def perform_content_negotiation(self, request, force=False):
        # DRF treats ?format= as renderer selection; we use it for json|xlsx export.
        from rest_framework.renderers import JSONRenderer

        return (JSONRenderer(), "application/json")

    def get_permissions(self):
        export_format = (self.request.query_params.get("format") or "json").lower()
        if export_format == "xlsx":
            return [IsAuthenticated(), HasCompany(), CanExport()]
        return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]

    def get(self, request):
        assert_gstr_enabled(self.company)
        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("Query parameter 'period' is required (YYYY-MM).")
        try:
            parse_period(period)
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc

        export_format = (request.query_params.get("format") or "json").lower()
        company_gstin = request.query_params.get("company_gstin") or request.query_params.get(
            "companyGstin"
        )
        payload = self.build_fn(self.company, period, company_gstin=company_gstin or None)
        from core.models import AuditEvent

        AuditEvent.objects.create(
            company=self.company,
            user=request.user,
            action=AuditEvent.Action.CREATE,
            entity_type="GstReturnJson",
            entity_id=period,
            description=f"{payload.get('return_type', 'GSTR')} downloaded",
            metadata={"format": export_format, "period": period},
        )
        if request.query_params.get("persist") in ("1", "true", "True"):
            persist_snapshot(
                self.company,
                payload.get("return_type", "GSTR-1"),
                period,
                payload,
                user=request.user,
            )

        if export_format == "json":
            return Response(payload)
        gstn = _maybe_gstn_json(request, payload)
        if gstn is not None:
            return gstn
        if export_format == "xlsx":
            content = gstr_return_to_xlsx(payload)
            filename = f"{payload['return_type'].lower().replace('-', '')}-{period}.xlsx"
            response = HttpResponse(
                content,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        raise BusinessRuleError("Unsupported format. Use format=json, format=xlsx, or format=gstn-json.")


class Gstr1View(GstReturnView):
    build_fn = staticmethod(build_gstr1)


class Gstr3bView(GstReturnView):
    build_fn = staticmethod(build_gstr3b)


class Gstr9View(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def perform_content_negotiation(self, request, force=False):
        from rest_framework.renderers import JSONRenderer

        return (JSONRenderer(), "application/json")

    def get_permissions(self):
        export_format = (self.request.query_params.get("format") or "json").lower()
        if export_format == "xlsx":
            return [IsAuthenticated(), HasCompany(), CanExport()]
        return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]

    def get(self, request):
        assert_gstr_enabled(self.company)
        fy = request.query_params.get("fy")
        if not fy:
            raise BusinessRuleError("Query parameter 'fy' is required (e.g. 2025-26).")
        company_gstin = request.query_params.get("company_gstin") or None
        payload = build_gstr9(self.company, fy, company_gstin=company_gstin)
        export_format = (request.query_params.get("format") or "json").lower()
        if export_format == "json":
            return Response(payload)
        gstn = _maybe_gstn_json(request, payload)
        if gstn is not None:
            return gstn
        if export_format == "xlsx":
            content = gstr_return_to_xlsx(payload)
            response = HttpResponse(
                content,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = f'attachment; filename="gstr9-{fy}.xlsx"'
            return response
        raise BusinessRuleError("Unsupported format. Use format=json, format=xlsx, or format=gstn-json.")


class CancelledDocumentNumbersView(BaseReportView):
    """W0-04 / PD-03: FY cancelled-number register for the CA (CSV or JSON)."""

    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "heavy_reports"

    def perform_content_negotiation(self, request, force=False):
        from rest_framework.renderers import JSONRenderer

        return (JSONRenderer(), "application/json")

    def get(self, request):
        from core.models import StatutoryDocumentEvent
        from core.services.document_numbers import gst_fy_label_for
        from purchases.models import PurchaseInvoice
        from sales.models import SalesCreditNote, SalesDebitNote, SalesInvoice

        fy = (request.query_params.get("fy") or "").strip()
        if not fy:
            raise BusinessRuleError("Query parameter 'fy' is required (e.g. 2026-27).")
        import re

        if not re.fullmatch(r"\d{4}-\d{2}", fy):
            raise BusinessRuleError("Query parameter 'fy' must look like 2026-27.")

        def _in_fy(doc_date) -> bool:
            if doc_date is None:
                return False
            return gst_fy_label_for(doc_date) == fy

        rows = []

        def _gstin(doc) -> str:
            stamp = getattr(doc, "company_gstin", None)
            if stamp is not None:
                return (getattr(stamp, "gstin", None) or "").strip().upper()
            return (getattr(self.company, "gstin", None) or "").strip().upper()

        def _reason(entity_type, entity_id, fallback=""):
            ev = (
                StatutoryDocumentEvent.objects.filter(
                    company=self.company,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    event_type=StatutoryDocumentEvent.EventType.CANCEL,
                )
                .order_by("-id")
                .first()
            )
            if ev and isinstance(ev.payload, dict):
                return str(ev.payload.get("reason") or fallback or "")
            return fallback

        for inv in (
            SalesInvoice.objects.filter(company=self.company, status=SalesInvoice.Status.CANCELLED)
            .exclude(number="")
            .select_related("company_gstin", "updated_by")
        ):
            if not _in_fy(inv.invoice_date or (inv.cancelled_at.date() if inv.cancelled_at else None)):
                continue
            rows.append({
                "number": inv.number,
                "doc_type": "SALES_INVOICE",
                "gstin": _gstin(inv),
                "date": (inv.invoice_date.isoformat() if inv.invoice_date else ""),
                "reason": _reason("sales_invoice", inv.pk),
                "user": getattr(inv.updated_by, "email", "") or "",
            })
        for inv in (
            PurchaseInvoice.objects.filter(
                company=self.company, status=PurchaseInvoice.Status.CANCELLED
            )
            .exclude(number="")
            .select_related("updated_by")
        ):
            if not _in_fy(inv.invoice_date):
                continue
            rows.append({
                "number": inv.number,
                "doc_type": "PURCHASE_INVOICE",
                "gstin": (getattr(self.company, "gstin", None) or "").strip().upper(),
                "date": (inv.invoice_date.isoformat() if inv.invoice_date else ""),
                "reason": _reason("purchase_invoice", inv.pk),
                "user": getattr(inv.updated_by, "email", "") or "",
            })
        for note in SalesCreditNote.objects.filter(
            company=self.company, status=SalesCreditNote.Status.CANCELLED
        ).exclude(number=""):
            if not _in_fy(note.note_date):
                continue
            rows.append({
                "number": note.number,
                "doc_type": "SALES_CREDIT_NOTE",
                "gstin": (getattr(self.company, "gstin", None) or "").strip().upper(),
                "date": (note.note_date.isoformat() if note.note_date else ""),
                "reason": _reason("sales_credit_note", note.pk),
                "user": "",
            })
        for note in SalesDebitNote.objects.filter(
            company=self.company, status=SalesDebitNote.Status.CANCELLED
        ).exclude(number=""):
            if not _in_fy(note.note_date):
                continue
            rows.append({
                "number": note.number,
                "doc_type": "SALES_DEBIT_NOTE",
                "gstin": (getattr(self.company, "gstin", None) or "").strip().upper(),
                "date": (note.note_date.isoformat() if note.note_date else ""),
                "reason": _reason("sales_debit_note", note.pk),
                "user": "",
            })
        rows.sort(key=lambda r: (r["date"], r["number"]))
        export_format = (request.query_params.get("format") or "json").lower()
        if export_format == "csv":
            buf = io.StringIO()
            writer = csv.DictWriter(
                buf, fieldnames=["number", "doc_type", "gstin", "date", "reason", "user"]
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({k: csv_safe(v) for k, v in row.items()})
            response = HttpResponse(buf.getvalue(), content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="cancelled-numbers-{fy}.csv"'
            return response
        return Response({"fy": fy, "columns": ["number", "doc_type", "gstin", "date", "reason", "user"], "rows": rows})


class GstHealthView(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def get(self, request):
        assert_gstr_enabled(self.company)
        period = request.query_params.get("period")
        return Response(build_gst_health(self.company, period))


class GstRateExposureView(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def get(self, request):
        from reporting.gst_rate_scan import backscan_rate_exposure

        assert_gstr_enabled(self.company)
        return Response(backscan_rate_exposure(
            self.company,
            date_from=_parse_date(request.query_params.get("date_from")),
            date_to=_parse_date(request.query_params.get("date_to")),
        ))


class GstCaPackView(BaseReportView):
    permission_classes = [IsAuthenticated, HasCompany, CanExport]
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def perform_content_negotiation(self, request, force=False):
        from rest_framework.renderers import JSONRenderer

        return (JSONRenderer(), "application/json")

    def get(self, request):
        from accounts.models import Company

        assert_gstr_enabled(self.company)
        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("Query parameter 'period' is required (YYYY-MM).")
        parse_period(period)
        company_gstin = request.query_params.get("company_gstin") or request.query_params.get(
            "companyGstin"
        )
        if self.company.registration_type == Company.RegistrationType.COMPOSITION:
            content = build_ca_pack_zip(self.company, period, gstr1=None)
        else:
            g1 = build_gstr1(self.company, period, company_gstin=company_gstin or None)
            g3 = build_gstr3b(self.company, period, gstr1=g1, company_gstin=company_gstin or None)
            persist_snapshot(self.company, "GSTR-1", period, g1, user=request.user)
            persist_snapshot(self.company, "GSTR-3B", period, g3, user=request.user)
            content = build_ca_pack_zip(self.company, period, gstr1=g1)
        response = HttpResponse(content, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="gst-ca-pack-{period}.zip"'
        return response


class GstPeriodView(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def post(self, request):
        assert_gstr_enabled(self.company)
        period = request.data.get("period")
        action = (request.data.get("action") or "").lower()
        if not period:
            raise BusinessRuleError("'period' is required.")
        cu = get_company_user(request)
        if cu.role != "OWNER":
            raise BusinessRuleError("Only Owner can close or reopen GST periods.")
        if action == "soft_close":
            obj = soft_close_period(self.company, period, request.user)
        elif action == "reopen":
            obj = reopen_period(self.company, period)
        else:
            raise BusinessRuleError("action must be soft_close or reopen.")
        return Response({
            "period": obj.period,
            "status": obj.status,
            "dirty_after_snapshot": obj.dirty_after_snapshot,
        })


class Gstr2bIngestViewSet(viewsets.ModelViewSet):
    """Wave 17A: upload/list/match GSTR-2B ingest rows."""

    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]
    serializer_class = Gstr2bIngestSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    @property
    def company(self):
        return get_company_user(self.request).company

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        assert_gstr_enabled(self.company)

    def get_queryset(self):
        qs = Gstr2bIngest.objects.filter(company=self.company)
        period = self.request.query_params.get("period")
        if period:
            qs = qs.filter(period=period)
        source = (self.request.query_params.get("source") or "").strip().upper()
        if source in ("2A", "2B"):
            qs = qs.filter(raw__source=source)
        ims_action = (self.request.query_params.get("ims_action") or "").strip().upper()
        if ims_action in dict(Gstr2bIngest.ImsAction.choices):
            qs = qs.filter(ims_action=ims_action)
        match_class = (self.request.query_params.get("match_class") or "").strip()
        if match_class:
            qs = qs.filter(match_class=match_class)
        return qs

    def perform_create(self, serializer):
        serializer.save(company=self.company)

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        """Bulk ingest rows: {period, rows: [{supplier_gstin, invoice_number, ...}]}."""
        period = request.data.get("period")
        rows = request.data.get("rows") or []
        if not period:
            raise BusinessRuleError("'period' is required.")
        parse_period(period)
        source = (request.data.get("source") or "2B").strip().upper()
        if source not in ("2A", "2B"):
            source = "2B"
        created = []
        for row in rows:
            raw = dict(row) if isinstance(row, dict) else {}
            raw["source"] = source
            supplier = (row.get("supplier_gstin") or "").strip().upper()[:15]
            invoice_number = (row.get("invoice_number") or "").strip()[:64]
            defaults = {
                "invoice_date": row.get("invoice_date") or None,
                "taxable_value": row.get("taxable_value") or 0,
                "igst": row.get("igst") or 0,
                "cgst": row.get("cgst") or 0,
                "sgst": row.get("sgst") or 0,
                "cess": row.get("cess") or 0,
                "raw": raw,
            }
            if invoice_number:
                obj, _created = Gstr2bIngest.objects.update_or_create(
                    company=self.company,
                    period=period,
                    supplier_gstin=supplier,
                    invoice_number=invoice_number,
                    defaults=defaults,
                )
            else:
                obj = Gstr2bIngest.objects.create(
                    company=self.company,
                    period=period,
                    supplier_gstin=supplier,
                    invoice_number=invoice_number,
                    **defaults,
                )
            created.append(obj.pk)
        return Response({"period": period, "created": len(created), "ids": created})

    @action(detail=False, methods=["post"], url_path="match")
    def match(self, request):
        period = request.data.get("period") or request.query_params.get("period")
        if not period:
            raise BusinessRuleError("'period' is required.")
        from reporting.gstr2b import match_gstr2b_to_purchases
        from reporting.ims import classify_and_match

        match_gstr2b_to_purchases(self.company, period)
        return Response(classify_and_match(self.company, period))

    @action(detail=True, methods=["post"], url_path="ims-act")
    def ims_act(self, request, pk=None):
        from reporting.ims import apply_ims_action

        row = self.get_object()
        action = request.data.get("action") or request.data.get("ims_action")
        remark = request.data.get("remark") or request.data.get("ims_remark") or ""
        apply_ims_action(row, action, remark=remark, user=request.user)
        row.refresh_from_db()
        return Response(self.get_serializer(row).data)

    @action(detail=False, methods=["post"], url_path="ims-bulk-accept")
    def ims_bulk_accept(self, request):
        from reporting.ims import bulk_accept_exact

        period = request.data.get("period") or request.query_params.get("period")
        if not period:
            raise BusinessRuleError("'period' is required.")
        return Response(bulk_accept_exact(self.company, period, user=request.user))

    @action(detail=False, methods=["get"], url_path="ims-summary")
    def ims_summary(self, request):
        from reporting.ims import credit_at_risk

        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("'period' is required.")
        return Response(credit_at_risk(self.company, period))

    @action(detail=False, methods=["get"], url_path="missing-documents")
    def missing_documents(self, request):
        from reporting.chase import list_missing_documents, serialize_chase_row

        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("'period' is required.")
        rows = list_missing_documents(self.company, period)
        return Response({
            "period": period,
            "count": len(rows),
            "items": [serialize_chase_row(r) for r in rows],
        })

    @action(detail=False, methods=["post"], url_path="chase-whatsapp")
    def chase_whatsapp(self, request):
        from reporting.chase import request_whatsapp

        period = request.data.get("period") or request.query_params.get("period")
        if not period:
            raise BusinessRuleError("'period' is required.")
        return Response(request_whatsapp(
            self.company,
            period,
            user=request.user,
            phone=request.data.get("phone") or "",
        ))

    @action(detail=True, methods=["post"], url_path="chase-photo")
    def chase_photo(self, request, pk=None):
        from reporting.chase import attach_photo_reply

        uploaded = request.FILES.get("file")
        if not uploaded:
            raise BusinessRuleError("A photo or PDF file is required.")
        return Response(attach_photo_reply(
            self.company, int(pk), uploaded, user=request.user,
        ), status=201)

    @action(detail=False, methods=["get"], url_path="ims-scorecard")
    def ims_scorecard(self, request):
        from reporting.ims import supplier_scorecard

        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("'period' is required.")
        return Response({"period": period, "suppliers": supplier_scorecard(self.company, period)})

    @action(detail=True, methods=["post"], url_path="supplier-message")
    def supplier_message(self, request, pk=None):
        from reporting.ims import supplier_defect_message

        row = self.get_object()
        return Response(supplier_defect_message(row))

    @action(detail=False, methods=["post"], url_path="ims-offline-import")
    def ims_offline_import(self, request):
        from reporting.ims_offline import import_offline

        payload = request.data.get("payload") if "payload" in request.data else request.data
        replace = bool(request.data.get("replace"))
        return Response(import_offline(self.company, payload, replace=replace))

    @action(detail=False, methods=["get"], url_path="ims-offline-export")
    def ims_offline_export(self, request):
        from reporting.ims_offline import export_offline

        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("'period' is required.")
        return Response(export_offline(self.company, period))

    @action(detail=False, methods=["post"], url_path="ims-gsp-pull")
    def ims_gsp_pull(self, request):
        """Fail-closed: live GSP only when P0 credentials exist."""
        from core.services.gsp_adapters import get_gstr_filing_adapter
        from reporting.ims_offline import import_offline

        period = request.data.get("period")
        if not period:
            raise BusinessRuleError("'period' is required.")
        adapter = get_gstr_filing_adapter(self.company)
        fetched = adapter.fetch_gstr2b(period)
        rows = fetched.get("rows") or fetched.get("data") or []
        if not isinstance(rows, list) or not rows:
            raise BusinessRuleError("GSP returned no 2B rows — use the GSTN offline-tool file.")
        return Response(import_offline(self.company, {"period": period, "rows": rows}, replace=False))


class Cmp08View(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def get(self, request):
        from accounts.models import Company
        from reporting.gstr2b import build_cmp08

        assert_gstr_enabled(self.company)
        if self.company.registration_type != Company.RegistrationType.COMPOSITION:
            raise BusinessRuleError("CMP-08 is only for composition dealers.")
        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("Query parameter 'period' is required (YYYY-MM).")
        parse_period(period)
        return Response(build_cmp08(self.company, period))


class Gstr4View(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def get(self, request):
        from accounts.models import Company
        from reporting.gstr2b import build_gstr4

        assert_gstr_enabled(self.company)
        if self.company.registration_type != Company.RegistrationType.COMPOSITION:
            raise BusinessRuleError("GSTR-4 is only for composition dealers.")
        fy = request.query_params.get("fy")
        if not fy:
            raise BusinessRuleError("Query parameter 'fy' is required (e.g. 2025-26).")
        return Response(build_gstr4(self.company, fy))


class Gstr8View(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def get(self, request):
        from reporting.gstr2b import build_gstr8

        assert_gstr_enabled(self.company)
        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("Query parameter 'period' is required (YYYY-MM).")
        parse_period(period)
        return Response(build_gstr8(self.company, period))


class Gstr6View(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def get(self, request):
        from reporting.gstr2b import build_gstr6

        assert_gstr_enabled(self.company)
        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("Query parameter 'period' is required (YYYY-MM).")
        parse_period(period)
        return Response(build_gstr6(self.company, period))


class Gstr7View(BaseReportView):
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def get(self, request):
        from reporting.gstr2b import build_gstr7

        assert_gstr_enabled(self.company)
        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("Query parameter 'period' is required (YYYY-MM).")
        parse_period(period)
        return Response(build_gstr7(self.company, period))


class GstFilingSandboxView(BaseReportView):
    """Wave 17B: sandbox HTTP upload_gstr1 / fetch_gstr2b when GSP_HTTP_SANDBOX=1.

    BB-000742: production/staging without GSP_CERTIFIED must not expose a live-looking
    GSTR filing upload surface — no certified Live filing adapter ships yet.
    """

    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "gst_reports"

    def post(self, request):
        from django.conf import settings

        from core.services.gsp_adapters import get_gstr_filing_adapter

        assert_gstr_enabled(self.company)
        env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
        certified = getattr(settings, "GSP_CERTIFIED", False) is True
        if env in ("production", "staging") and not certified:
            raise Http404()

        action_name = (request.data.get("action") or "").lower()
        period = request.data.get("period")
        if not period:
            raise BusinessRuleError("'period' is required.")
        parse_period(period)
        adapter = get_gstr_filing_adapter(self.company)
        result = None
        payload = None
        if action_name == "upload_gstr1":
            payload = build_gstr1(self.company, period)
            result = adapter.upload_gstr1(payload)
        elif action_name == "upload_gstr3b":
            payload = build_gstr3b(self.company, period)
            result = adapter.upload_gstr3b(payload)
        elif action_name == "fetch_gstr2b":
            result = adapter.fetch_gstr2b(period)
            return Response({"action": action_name, "result": result})
        else:
            raise BusinessRuleError("action must be upload_gstr1, upload_gstr3b, or fetch_gstr2b.")
        ack = result if isinstance(result, dict) else {"ok": True, "detail": str(result)}
        return_type = (
            "GSTR-3B" if action_name == "upload_gstr3b" else (payload or {}).get("return_type", "GSTR-1")
        )
        snap = persist_snapshot(
            self.company,
            return_type,
            period,
            payload or {},
            user=request.user,
        )
        body = dict(snap.payload or {})
        body["gsp_upload"] = ack
        snap.payload = body
        snap.save(update_fields=["payload"])
        return Response({
            "action": action_name,
            "result": ack,
            "job_id": ack.get("reference_id") or ack.get("job_id") or ack.get("ack") or "",
        })


class TdsWorksheetView(APIView):
    """BB-000670: 26Q worksheet aid CSV. Not a live IT portal upload."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        company = get_company_user(request).company
        if not _tds_worksheets_readable(company):
            raise Http404()
        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("Query parameter 'period' is required (YYYY-MM).")
        from .gst_returns import parse_period
        from .tds_worksheets import tds_worksheet_rows

        try:
            parse_period(period)
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        rows = tds_worksheet_rows(company, period)
        buffer = io.StringIO()
        fieldnames = [
            "date", "invoice", "supplier", "supplier_gstin", "section", "rate",
            "taxable", "grand_total", "tds_amount", "net_payable", "source",
        ]
        # extrasaction="ignore": a compliance export must never 500 because a
        # row helper grew an extra key.
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerow({"date": "# 26Q worksheet aid — not a live IT portal upload", "invoice": ""})
        writer.writerows(rows)
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="tds-26q-{period}.csv"'
        return response


class TcsWorksheetView(APIView):
    """BB-000670: 27EQ worksheet aid CSV. Not a live IT portal upload."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        company = get_company_user(request).company
        if not _tds_worksheets_readable(company):
            raise Http404()
        period = request.query_params.get("period")
        if not period:
            raise BusinessRuleError("Query parameter 'period' is required (YYYY-MM).")
        from .gst_returns import parse_period
        from .tds_worksheets import tcs_worksheet_rows

        try:
            parse_period(period)
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc
        rows = tcs_worksheet_rows(company, period)
        buffer = io.StringIO()
        fieldnames = [
            "date", "invoice", "customer", "customer_gstin", "section", "rate",
            "taxable", "grand_total", "tcs_amount", "receivable", "source",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerow({"date": "# 27EQ worksheet aid — not a live IT portal upload", "invoice": ""})
        writer.writerows(rows)
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="tcs-27eq-{period}.csv"'
        return response


# Backwards-compatible alias — prefer core.csv_utils.csv_safe.
_csv_safe = csv_safe


class ExportView(BaseReportView):
    """CSV export of registers via Report Service (E5.8)."""

    permission_classes = [IsAuthenticated, HasCompany, CanExport]
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "heavy_reports"

    def get(self, request, report):
        if report not in EXPORTS:
            raise BusinessRuleError(f"Unknown export '{report}'. Available: {', '.join(EXPORTS)}.")
        rows = EXPORTS[report](self.company, request.query_params)
        buffer = io.StringIO()
        # BUG-323: a filtered-to-zero-rows export used to produce a
        # completely empty file with no header, which some spreadsheet
        # tools mis-render as a corrupt/blank CSV.
        fieldnames = EXPORT_FIELDS.get(report) or (list(rows[0].keys()) if rows else [])
        if fieldnames:
            writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: _csv_safe(row.get(k)) for k in fieldnames})
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{report}.csv"'
        return response
