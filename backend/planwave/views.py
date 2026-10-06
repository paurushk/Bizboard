from datetime import date
from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import (
    CanCreateSales,
    CanImport,
    CanViewFinancialReports,
    HasCompany,
    IsOwner,
    IsOwnerManagerOrAccountant,
    get_company_user,
)

from .models import AnomalyReview, ApprovalRequest, EwayStubAction
from .services import (
    assert_pharmacy_sale,
    certification_export,
    clear_quarantine,
    decide_approval,
    eway_validity_days,
    map_tally_import,
    parse_bulk_invoices,
    quarantine_is_open,
    record_eway_stub,
    save_itc_check,
    section_50_interest,
    submit_approval,
    itc_claimable,
)


def _date(value, field="date"):
    """A bad or missing date is the caller's mistake: 400, not a 500."""
    from core.exceptions import BusinessRuleError

    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise BusinessRuleError(f"{field} must be a date like 2026-04-01.") from None


def _decimal(value, field="amount"):
    from decimal import InvalidOperation

    from core.exceptions import BusinessRuleError

    try:
        return Decimal(str(value if value not in (None, "") else "0"))
    except InvalidOperation:
        raise BusinessRuleError(f"{field} must be a number.") from None


def _whole(value, field="value"):
    from core.exceptions import BusinessRuleError

    try:
        return int(value or 0)
    except (TypeError, ValueError):
        raise BusinessRuleError(f"{field} must be a whole number.") from None


# What may enter the approval queue. Anything else is refused up front rather than stored.
APPROVAL_ACTIONS = frozenset({
    "stock_adjustment", "invoice_cancel", "credit_limit_override", "discount", "return_or_credit_note",
    "backdated_posting", "period_reopen", "supplier_payment", "write_off", "bulk_import_commit", "generic",
})


class NotViewerWrites(BasePermission):
    """A VIEWER may read these endpoints. Every write needs a working role."""

    message = "Viewers cannot change data."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        cu = get_company_user(request)
        return cu is not None and cu.role != "VIEWER"


class _CompanyView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, NotViewerWrites]

    @property
    def company(self):
        return get_company_user(self.request).company


class QuarantineView(_CompanyView):
    def get_permissions(self):
        # Clearing the books quarantine is an Owner decision.
        if self.request.method == "DELETE":
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return super().get_permissions()

    def get(self, request):
        return Response({"open": quarantine_is_open(self.company)})

    def delete(self, request):
        cleared = clear_quarantine(self.company, request.user)
        return Response({"cleared": cleared})


class ApprovalListCreate(_CompanyView):
    def post(self, request):
        from core.exceptions import BusinessRuleError

        action = request.data.get("action") or "generic"
        if action not in APPROVAL_ACTIONS:
            raise BusinessRuleError("That action cannot be sent for approval.")
        payload = request.data.get("payload") or {}
        if not isinstance(payload, dict):
            raise BusinessRuleError("payload must be an object.")
        row = submit_approval(
            company=self.company,
            action=action,
            requester=request.user,
            payload=payload,
        )
        return Response({"id": row.pk, "status": row.status}, status=201)


class ApprovalDecide(_CompanyView):
    def post(self, request, pk):
        # Only an Owner may approve or reject. Any other member deciding a request
        # would turn a second-pair-of-eyes control into a rubber stamp.
        member = get_company_user(request)
        if member is None or member.role != "OWNER":
            raise PermissionDenied("Only an owner can decide an approval request.")
        row = get_object_or_404(ApprovalRequest, pk=pk, company=self.company)
        flags = getattr(self.company, "feature_flags", None) or {}
        owner_exception = bool(flags.get("owner_may_self_approve")) and member.role == "OWNER"
        row = decide_approval(
            row,
            approver=request.user,
            accept=bool(request.data.get("accept")),
            owner_exception=owner_exception,
        )
        return Response({"status": row.status})


class Section50View(_CompanyView):
    def post(self, request):
        result = section_50_interest(
            tax=_decimal(request.data.get("tax"), "tax"),
            excess_itc=_decimal(request.data.get("excess_itc"), "excess_itc"),
            days=_whole(request.data.get("days"), "days"),
            on=_date(request.data.get("on"), "on"),
        )
        return Response({k: str(v) if isinstance(v, Decimal) else v for k, v in result.items()})


class EwayStubView(_CompanyView):
    permission_classes = [IsAuthenticated, HasCompany, NotViewerWrites, IsOwnerManagerOrAccountant]

    def post(self, request):
        from core.exceptions import BusinessRuleError

        distance = request.data.get("distance_km")
        if distance is not None and request.data.get("action") == "validity":
            return Response({"days": eway_validity_days(_decimal(distance, "distance_km"))})
        if request.data.get("action") not in EwayStubAction.Action.values:
            raise BusinessRuleError("Unknown e-way action.")
        if (request.data.get("bill_status") or "ACTIVE") not in ("ACTIVE", "CANCELLED", "EXPIRED", "COMPLETED"):
            raise BusinessRuleError("Unknown bill status.")
        row = record_eway_stub(
            company=self.company,
            document_type=request.data.get("document_type") or "invoice",
            document_id=str(request.data.get("document_id") or ""),
            action=request.data.get("action"),
            payload=request.data.get("payload") or {},
            bill_status=request.data.get("bill_status") or "ACTIVE",
            user=request.user,
        )
        return Response({"id": row.pk}, status=201)


class ItcCheckView(_CompanyView):
    # Attesting that the supplier paid the tax is an accountant-level statement.
    permission_classes = [IsAuthenticated, HasCompany, NotViewerWrites, IsOwnerManagerOrAccountant]

    def post(self, request):
        row = save_itc_check(
            self.company,
            request.data.get("source_type") or "purchase",
            request.data.get("source_id") or "0",
            invoice_held=bool(request.data.get("invoice_held")),
            goods_received=bool(request.data.get("goods_received")),
            paid_within_180=bool(request.data.get("paid_within_180")),
            supplier_tax_attested=bool(request.data.get("supplier_tax_attested")),
            return_filed_attested=bool(request.data.get("return_filed_attested")),
        )
        return Response({"claimable": itc_claimable(row)})


class CertificationView(_CompanyView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwnerManagerOrAccountant]

    def get(self, request):
        from core.services import audit_chain

        # The chain is verified here. A caller-supplied flag would let anyone certify any year.
        problems = audit_chain.verify(self.company.pk).problems
        payload = certification_export(
            self.company,
            year_start=_date(request.query_params.get("start"), "start"),
            year_end=_date(request.query_params.get("end"), "end"),
            chain_ok=not problems,
        )
        return Response(payload)


class AnomalyList(_CompanyView):
    def get(self, request):
        rows = AnomalyReview.objects.filter(company=self.company, status=AnomalyReview.Status.OPEN)
        return Response([{"id": r.pk, "kind": r.kind, "subject_id": r.subject_id} for r in rows])


class BulkInvoiceView(_CompanyView):
    permission_classes = [IsAuthenticated, HasCompany, NotViewerWrites, CanCreateSales]

    def post(self, request):
        return Response(parse_bulk_invoices(self.company, request.data.get("csv") or ""))


class TallyMapView(_CompanyView):
    permission_classes = [IsAuthenticated, HasCompany, NotViewerWrites, CanImport]

    def post(self, request):
        job = map_tally_import(
            self.company,
            financial_year=request.data.get("financial_year") or "",
            ledgers=request.data.get("ledgers") or {},
            stock_items=request.data.get("stock_items") or {},
            vouchers=request.data.get("vouchers") or [],
        )
        return Response({"id": job.pk, "voucher_count": job.voucher_count, "live_tally": False, "status": job.status})


class TallyCommitView(_CompanyView):
    """Stores the mapped file only. Live Tally stays off until a freeze exception."""

    def post(self, request):
        from django.conf import settings

        if not getattr(settings, "ENABLE_TALLY", False):
            return Response({"imported": False, "reason": "ENABLE_TALLY is off."})
        return Response({"imported": False, "reason": "Live Tally import is not enabled for this process."})


class PharmacyRegisterView(_CompanyView):
    # The register holds patient names: not for every login.
    permission_classes = [IsAuthenticated, HasCompany, IsOwnerManagerOrAccountant]

    def get(self, request):
        from django.http import HttpResponse

        from .finish import pharmacy_register_csv, pharmacy_register_pdf

        if request.query_params.get("layout") == "pdf":
            return HttpResponse(pharmacy_register_pdf(self.company), content_type="application/pdf")
        body = pharmacy_register_csv(self.company)
        return HttpResponse(body, content_type="text/csv")


class Section50CsvView(_CompanyView):
    def post(self, request):
        from django.http import HttpResponse

        from .finish import section_50_csv

        body = section_50_csv(
            tax=request.data.get("tax") or "0",
            excess_itc=request.data.get("excess_itc") or "0",
            days=request.data.get("days") or 0,
            on=_date(request.data.get("on"), "on"),
        )
        return HttpResponse(body, content_type="text/csv")


class ItcSummaryView(_CompanyView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwnerManagerOrAccountant]

    def get(self, request):
        from .finish import itc_summary

        return Response(itc_summary(self.company))

    def post(self, request):
        """Send the deadline alerts (once per bill per day). A read never sends anything."""
        from .finish import alert_itc_deadlines

        return Response({"sent": alert_itc_deadlines(self.company)})


class TwoBScoreView(_CompanyView):
    def post(self, request):
        from .finish import score_2b_rows

        return Response(score_2b_rows(request.data.get("rows") or []))


class CashflowView(_CompanyView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request):
        from masters.models import Customer

        from .finish import cashflow_for_customer

        customer = get_object_or_404(Customer, pk=request.query_params.get("customer"), company=self.company)
        return Response(cashflow_for_customer(self.company, customer))


class OverdueReportView(_CompanyView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    def get(self, request):
        from .finish import overdue_report

        return Response(overdue_report(self.company))


class GodownDashboardView(_CompanyView):
    def get(self, request):
        from .finish import godown_dashboard

        return Response(godown_dashboard(self.company))


class BulkCommitView(_CompanyView):
    permission_classes = [IsAuthenticated, HasCompany, NotViewerWrites, CanCreateSales]

    def post(self, request):
        from .finish import commit_bulk_invoices

        return Response(commit_bulk_invoices(self.company, request.data.get("csv") or "", request.user))


class RestoreMasterView(_CompanyView):
    permission_classes = [IsAuthenticated, HasCompany, NotViewerWrites, IsOwnerManagerOrAccountant]

    def post(self, request):
        from core.exceptions import BusinessRuleError

        from .finish import restore_master

        try:
            master_id = int(request.data.get("id"))
        except (TypeError, ValueError):
            raise BusinessRuleError("id must be a whole number.") from None
        row = restore_master(self.company, request.data.get("kind") or "", master_id, request.user)
        return Response({"id": row.pk, "restored": True})


class WarehouseAccessView(_CompanyView):
    # Who may work in which godown is the owner's call, not something a user grants themselves.
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request):
        from accounts.models import CompanyUser
        from inventory.models import Warehouse

        from .finish import grant_warehouse

        warehouse = get_object_or_404(Warehouse, pk=request.data.get("warehouse"), company=self.company)
        target = request.user
        if request.data.get("user"):
            member = get_object_or_404(
                CompanyUser, company=self.company, user_id=request.data.get("user"), is_active=True,
            )
            target = member.user
        row = grant_warehouse(
            self.company, target, warehouse, default=bool(request.data.get("default")),
        )
        return Response({"id": row.pk, "default": row.is_default}, status=201)


class PosHoldView(_CompanyView):
    def get(self, request):
        from django.utils import timezone

        from .models import PosCartHold

        rows = PosCartHold.objects.filter(company=self.company, released_at__isnull=True, expires_at__gt=timezone.now())
        return Response([{"id": r.pk, "label": r.label, "payload": r.payload} for r in rows])

    def post(self, request):
        from .finish import hold_pos_cart

        row = hold_pos_cart(
            self.company, label=request.data.get("label") or "Cart", payload=request.data.get("payload") or {},
            user=request.user,
        )
        return Response({"id": row.pk, "expires_at": row.expires_at.isoformat()}, status=201)


class CatalogExportView(_CompanyView):
    """CSV and PDF item list. Cost columns are omitted for roles that must not see them."""

    def get(self, request):
        from django.http import HttpResponse

        from .finish import catalog_csv, catalog_pdf

        role = getattr(get_company_user(request), "role", "") or ""
        if request.query_params.get("layout") == "pdf":
            body = catalog_pdf(self.company, role)
            response = HttpResponse(body, content_type="application/pdf")
            response["Content-Disposition"] = 'attachment; filename="catalogue.pdf"'
            return response
        body = catalog_csv(self.company, role)
        response = HttpResponse(body, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="catalogue.csv"'
        return response


class PrintBridgeView(_CompanyView):
    """Network ESC/POS is used when a printer is configured. Otherwise the PDF is the receipt."""

    def post(self, request):
        printer = (request.data.get("printer_host") or "").strip()
        if not printer:
            return Response({"delivered": False, "fallback": "pdf", "reason": "No network printer is configured."})
        return Response({"delivered": False, "fallback": "pdf", "reason": "The print bridge has no live printer in this environment."})


class PharmacyView(_CompanyView):
    def post(self, request):
        from masters.models import Product

        product = get_object_or_404(Product.all_objects, pk=request.data.get("product"), company=self.company)
        row = assert_pharmacy_sale(
            company=self.company,
            product=product,
            patient_name=request.data.get("patient_name") or "",
            prescriber_name=request.data.get("prescriber_name") or "",
            prescriber_registration=request.data.get("prescriber_registration") or "",
            prescription_note=request.data.get("prescription_note") or "",
        )
        return Response({"id": getattr(row, "pk", None)})
