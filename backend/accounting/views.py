from decimal import Decimal
from io import BytesIO

from django.db.models import Sum
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.permissions import (
    CanExport,
    CanPostJournals,
    CanViewFinancialReports,
    HasCompany,
    IsOwner,
    get_company_user,
)
from core.viewsets import CompanyScopedViewSet

from .models import Account, AccountingPeriod, BankReconSession, CostCenter, FixedAsset, JournalEntry, JournalLine
from .reports import balance_sheet, cash_flow, close_financial_year, profit_and_loss, trial_balance
from .serializers import (
    AccountSerializer, AccountingPeriodSerializer, BankReconSessionSerializer, CostCenterSerializer,
    FixedAssetSerializer, JournalEntrySerializer,
)
from .services import BooksHealthService, PostingService, seed_chart_of_accounts


class AccountingEnabledMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not get_company_user(request).company.accounting_enabled:
            raise BusinessRuleError("Accounting is not enabled for this company.")


_MUTATE_ACTIONS = ("create", "update", "partial_update", "destroy")


class AccountViewSet(AccountingEnabledMixin, CompanyScopedViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), CanPostJournals()]
        return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]

    def perform_create(self, serializer):
        serializer.save(company=self.company, created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.is_system:
            raise BusinessRuleError("System accounts cannot be edited.")
        serializer.save(updated_by=self.request.user, company=self.company)

    def perform_destroy(self, instance):
        if instance.is_system:
            raise BusinessRuleError("System accounts cannot be deleted.")
        super().perform_destroy(instance)


class PeriodViewSet(AccountingEnabledMixin, CompanyScopedViewSet):
    queryset = AccountingPeriod.objects.all()
    serializer_class = AccountingPeriodSerializer

    def get_permissions(self):
        # BB-000453: period CLOSE / mutate is Owner-only (not Accountant CanPostJournals).
        if getattr(self, "action", None) in (*_MUTATE_ACTIONS, "soft_close", "close"):
            return [IsAuthenticated(), HasCompany(), IsOwner()]
        return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]

    def perform_create(self, serializer):
        serializer.save(company=self.company, created_by=self.request.user, updated_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="soft-close")
    def soft_close(self, request, pk=None):
        period = self.get_object()
        if period.status != AccountingPeriod.Status.OPEN:
            raise BusinessRuleError("Only open periods can be soft closed.")
        BooksHealthService.assert_period_close_allowed(
            self.company, period=BooksHealthService._period_label(period),
        )
        period.status = AccountingPeriod.Status.SOFT_CLOSED
        period.updated_by = request.user
        period.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        period = self.get_object()
        if period.status == AccountingPeriod.Status.CLOSED:
            raise BusinessRuleError("Period is already closed.")
        BooksHealthService.assert_period_close_allowed(
            self.company, period=BooksHealthService._period_label(period),
        )
        period.status = AccountingPeriod.Status.CLOSED
        period.updated_by = request.user
        period.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(self.get_serializer(period).data)


class CostCenterViewSet(AccountingEnabledMixin, CompanyScopedViewSet):
    queryset = CostCenter.objects.all()
    serializer_class = CostCenterSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in _MUTATE_ACTIONS:
            return [IsAuthenticated(), HasCompany(), CanPostJournals()]
        return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]

    def perform_create(self, serializer):
        serializer.save(company=self.company, created_by=self.request.user, updated_by=self.request.user)


class JournalViewSet(AccountingEnabledMixin, CompanyScopedViewSet):
    """BB-000085: company-scoped journals (was bare ModelViewSet)."""

    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        # BB-000200/316: mutate / post / reverse journals requires Owner or can_post_journals.
        if getattr(self, "action", None) in (
            "create", "update", "partial_update", "destroy", "post", "reverse",
        ):
            return [IsAuthenticated(), HasCompany(), CanPostJournals()]
        return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]

    def get_queryset(self):
        return super().get_queryset().prefetch_related("lines")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lines = serializer.validated_data.pop("lines")
        # BB-000276: reject cross-tenant account / cost_center FKs.
        for line in lines:
            account = line.get("account")
            if account is not None and account.company_id != self.company.id:
                raise BusinessRuleError("Account must belong to this company.")
            cost_center = line.get("cost_center")
            if cost_center is not None and cost_center.company_id != self.company.id:
                raise BusinessRuleError("Cost center must belong to this company.")
        number = (serializer.validated_data.get("number") or "").strip()
        if not number:
            from core.services.document_numbers import DocumentNumberService, resolve_series_gstin

            number = DocumentNumberService.next_number(
                self.company,
                "JOURNAL_ENTRY",
                gstin=resolve_series_gstin(self.company),
                on_date=serializer.validated_data.get("entry_date"),
            )
        entry = JournalEntry.objects.create(company=self.company, status=JournalEntry.Status.DRAFT,
            number=number, entry_date=serializer.validated_data.get("entry_date"),
            narration=serializer.validated_data.get("narration", ""), created_by=request.user, updated_by=request.user)
        JournalLine.objects.bulk_create([
            JournalLine(company=entry.company, entry=entry, **line) for line in lines
        ])
        return Response(self.get_serializer(entry).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        entry = self.get_object()
        if entry.status != JournalEntry.Status.DRAFT:
            raise BusinessRuleError("Only draft journals can be posted.")
        totals = entry.lines.aggregate(debit=Sum("debit"), credit=Sum("credit"))
        if not entry.lines.exists() or (totals["debit"] or 0) != (totals["credit"] or 0):
            raise BusinessRuleError("Journal lines must balance before posting.")
        if AccountingPeriod.objects.filter(
            company=self.company, start_date__lte=entry.entry_date,
            end_date__gte=entry.entry_date,
            status__in=(AccountingPeriod.Status.CLOSED, AccountingPeriod.Status.SOFT_CLOSED),
        ).exists():
            raise BusinessRuleError("Cannot post to a closed accounting period.")
        entry.status = JournalEntry.Status.POSTED
        entry.source_type, entry.source_id, entry.purpose = "MANUAL_JOURNAL", entry.id, "POST"
        entry.posted_at, entry.posted_by = timezone.now(), request.user
        entry.save(update_fields=["status", "source_type", "source_id", "purpose", "posted_at", "posted_by", "updated_at"])
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        return Response(self.get_serializer(PostingService.reverse(self.get_object(), request.user)).data)


class BankReconSessionViewSet(AccountingEnabledMixin, CompanyScopedViewSet):
    queryset = BankReconSession.objects.all()
    serializer_class = BankReconSessionSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in (*_MUTATE_ACTIONS, "match"):
            return [IsAuthenticated(), HasCompany(), CanPostJournals()]
        return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]

    def perform_create(self, serializer):
        account = serializer.validated_data["account"]
        statement = serializer.validated_data["statement"]
        if account.company_id != self.company.id or statement.company_id != self.company.id:
            raise BusinessRuleError("Account and statement must belong to this company.")
        gl = JournalLine.objects.filter(entry__company=self.company, entry__status=JournalEntry.Status.POSTED,
            account=account).aggregate(d=Sum("debit"), c=Sum("credit"))
        statement_balance = statement.lines.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        serializer.save(company=self.company, gl_balance=(gl["debit"] or 0) - (gl["credit"] or 0),
                        statement_balance=statement_balance, created_by=self.request.user, updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def match(self, request, pk=None):
        from payments.models import BankStatementLine

        session = self.get_object()
        line = JournalLine.objects.filter(entry__company=self.company, pk=request.data.get("journal_line"),
            account=session.account, bank_statement_line__isnull=True).first()
        bank_line_id = request.data.get("bank_statement_line")
        # BB-000203: scope bank statement line to this company (IDOR).
        bank_line = (
            BankStatementLine.objects.filter(company=self.company, pk=bank_line_id).first()
            if bank_line_id
            else None
        )
        if not line or not bank_line:
            raise BusinessRuleError("An unreconciled journal line and bank statement line are required.")
        line.bank_statement_line = bank_line
        line.reconciled_at = timezone.localdate()
        line.save(update_fields=["bank_statement_line", "reconciled_at"])
        return Response({"ok": True})


class FixedAssetViewSet(AccountingEnabledMixin, CompanyScopedViewSet):
    queryset = FixedAsset.objects.all()
    serializer_class = FixedAssetSerializer

    def get_permissions(self):
        if getattr(self, "action", None) in (*_MUTATE_ACTIONS, "dispose"):
            return [IsAuthenticated(), HasCompany(), CanPostJournals()]
        return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]

    def perform_create(self, serializer):
        from .services import seed_chart_of_accounts

        accounts = seed_chart_of_accounts(self.company, self.request.user)
        validated = serializer.validated_data
        serializer.save(
            company=self.company,
            created_by=self.request.user,
            updated_by=self.request.user,
            asset_account=validated.get("asset_account") or accounts["1600"],
            accumulated_depreciation_account=validated.get("accumulated_depreciation_account") or accounts["1650"],
            depreciation_expense_account=validated.get("depreciation_expense_account") or accounts["5300"],
        )

    @action(detail=True, methods=["post"])
    def dispose(self, request, pk=None):
        """BB-000459: dispose with optional proceeds; NBV never hits Depreciation (5300)."""
        from django.db import transaction

        with transaction.atomic():
            asset = FixedAsset.objects.select_for_update().get(pk=self.get_object().pk, company=self.company)
            if asset.status != FixedAsset.Status.ACTIVE:
                raise BusinessRuleError("Asset has already been disposed.")
            if asset.depreciated_amount < 0 or asset.depreciated_amount > asset.acquisition_cost:
                raise BusinessRuleError("Accumulated depreciation is invalid for disposal.")
            try:
                proceeds = Decimal(str(request.data.get("proceeds", "0") or "0"))
            except Exception as exc:
                raise BusinessRuleError("proceeds must be a number.") from exc
            if proceeds < 0:
                raise BusinessRuleError("proceeds cannot be negative.")

            accounts = seed_chart_of_accounts(self.company, request.user)
            net_book_value = asset.acquisition_cost - asset.depreciated_amount
            lines = []
            if asset.depreciated_amount > 0:
                lines.append({"account": asset.accumulated_depreciation_account, "debit": asset.depreciated_amount})
            if proceeds > 0:
                # Default cash; callers may pass bank_code=1500 for bank.
                cash_code = str(request.data.get("cash_account_code") or "1100")
                if cash_code not in ("1100", "1500"):
                    raise BusinessRuleError("cash_account_code must be 1100 (Cash) or 1500 (Bank).")
                lines.append({"account": accounts[cash_code], "debit": proceeds})
            loss = net_book_value - proceeds
            if loss > 0:
                lines.append({"account": accounts["5600"], "debit": loss})
            elif loss < 0:
                lines.append({"account": accounts["5700"], "credit": abs(loss)})
            lines.append({"account": asset.asset_account, "credit": asset.acquisition_cost})
            PostingService.post(
                company=self.company,
                source_type="FIXED_ASSET",
                source_id=asset.id,
                purpose="DISPOSAL",
                entry_date=timezone.localdate(),
                user=request.user,
                narration=f"Disposal: {asset.name}",
                lines=lines,
            )
            asset.status, asset.disposed_at = FixedAsset.Status.DISPOSED, timezone.localdate()
            asset.save(update_fields=["status", "disposed_at", "updated_at"])
        return Response(self.get_serializer(asset).data)


class AccountingSettingsView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request):
        company = get_company_user(request).company
        if "accounting_enabled" not in request.data:
            raise BusinessRuleError("accounting_enabled is required.")
        raw = request.data.get("accounting_enabled")
        if isinstance(raw, str):
            enabled = raw.strip().lower() in {"1", "true", "yes", "on"}
        else:
            enabled = bool(raw)
        company.accounting_enabled = enabled
        company.save(update_fields=["accounting_enabled", "updated_at"])
        if enabled:
            seed_chart_of_accounts(company, request.user)
        return Response({"accounting_enabled": company.accounting_enabled})


class FinancialYearCloseView(AccountingEnabledMixin, APIView):
    """BB-000664: Owner-only FY close — POST {fyEnd, confirm: true}."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    @property
    def company(self):
        return get_company_user(self.request).company

    def post(self, request):
        from datetime import date as date_cls

        if not self.company.accounting_enabled:
            raise BusinessRuleError("Accounting is not enabled for this company.")
        data = request.data or {}
        raw_end = data.get("fyEnd") or data.get("fy_end")
        confirm = data.get("confirm")
        if confirm not in (True, "true", "True", 1, "1"):
            raise BusinessRuleError("confirm must be true to close the financial year.")
        if not raw_end:
            raise BusinessRuleError("fyEnd is required (YYYY-MM-DD).")
        try:
            fy_end = date_cls.fromisoformat(str(raw_end)[:10])
        except ValueError as exc:
            raise BusinessRuleError("fyEnd must be YYYY-MM-DD.") from exc
        entry = close_financial_year(self.company, fy_end, user=request.user)
        payload = {
            "ok": True,
            "fy_end": fy_end.isoformat(),
            "journal_id": entry.id if entry is not None else None,
        }
        return Response(payload)


class AccountingReportView(AccountingEnabledMixin, APIView):
    permission_classes = [IsAuthenticated, HasCompany, CanViewFinancialReports]

    @property
    def company(self):
        return get_company_user(self.request).company

    def get_permissions(self):
        # BB-000293: XLSX export requires CanExport.
        export_format = (self.request.query_params.get("format") or "json").lower()
        if export_format == "xlsx":
            return [IsAuthenticated(), HasCompany(), CanExport()]
        return [IsAuthenticated(), HasCompany(), CanViewFinancialReports()]

    def get(self, request, report):
        as_of = request.query_params.get("as_of")
        date_from, date_to = request.query_params.get("from"), request.query_params.get("to")
        if report == "trial-balance":
            return self._report_response(report, trial_balance(self.company, as_of), request)
        if report == "profit-and-loss":
            return self._report_response(report, profit_and_loss(self.company, date_from, date_to, request.query_params.get("cost_center")), request)
        if report == "balance-sheet":
            return self._report_response(
                report, balance_sheet(self.company, as_of, request.query_params.get("cost_center")), request,
            )
        if report == "cash-flow":
            return self._report_response(
                report, cash_flow(self.company, date_from, date_to, request.query_params.get("cost_center")), request,
            )
        if report == "books-health":
            return Response(BooksHealthService.control_balances(self.company))
        raise BusinessRuleError("Unknown accounting report.")

    def _report_response(self, report, payload, request):
        if request.query_params.get("format") != "xlsx":
            return Response(payload)
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = report.replace("-", " ").title()
        sheet.append(["Code", "Account", "Type", "Debit", "Credit", "Balance"])
        rows = payload.get("rows", [])
        if isinstance(rows, dict):
            rows = [row for group in rows.values() for row in group]
        for row in rows:
            sheet.append([
                row.get("account_code", ""), row.get("account_name", ""),
                row.get("account_type", ""), row.get("debit", 0),
                row.get("credit", 0), row.get("balance", 0),
            ])
        output = BytesIO()
        workbook.save(output)
        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{report}.xlsx"'
        return response
