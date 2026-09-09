from rest_framework import serializers

from core.permissions import get_company_user
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer, Supplier
from payments.models import BankAccount

from .models import Account, AccountingPeriod, BankReconSession, CostCenter, FixedAsset, JournalEntry, JournalLine


class AccountSerializer(serializers.ModelSerializer):
    parent = CompanyPrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True
    )
    bank_account = CompanyPrimaryKeyRelatedField(
        queryset=BankAccount.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Account
        fields = ["id", "code", "name", "type", "parent", "is_system", "is_control", "bank_account", "is_active"]
        read_only_fields = ["is_system", "is_control"]


class AccountingPeriodSerializer(serializers.ModelSerializer):
    gst_period_status = serializers.SerializerMethodField()

    class Meta:
        model = AccountingPeriod
        fields = ["id", "name", "start_date", "end_date", "status", "gst_period_status"]
        read_only_fields = ["status", "gst_period_status"]

    def get_gst_period_status(self, obj):
        from reporting.models import GstReturnPeriod

        period = f"{obj.start_date.year:04d}-{obj.start_date.month:02d}"
        gst = GstReturnPeriod.objects.filter(company_id=obj.company_id, period=period).first()
        return gst.status if gst is not None else GstReturnPeriod.Status.OPEN

    def validate(self, attrs):
        raw = getattr(self, "initial_data", None) or {}
        if self.instance is not None and hasattr(raw, "__contains__") and "status" in raw:
            raise serializers.ValidationError(
                {"status": "Use POST /soft-close/ or /close/ to change period status."}
            )
        # ACC-05: no overlapping periods per company — an overlapping OPEN+CLOSED
        # pair makes "is this date in a closed period?" and every period-scoped
        # report ambiguous.
        start = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end = attrs.get("end_date") or getattr(self.instance, "end_date", None)
        if start and end:
            if end < start:
                raise serializers.ValidationError({"end_date": "end_date must not precede start_date."})
            request = self.context.get("request")
            company = None
            if request is not None:
                from core.permissions import get_company_user

                cu = get_company_user(request)
                company = cu.company if cu else None
            # B1-030: fall back to the instance's company on update, and never
            # let the overlap guard be skipped just because there is no request
            # context — an internal caller must pass a resolvable company.
            if company is None:
                company = getattr(self.instance, "company", None)
            if company is None:
                raise serializers.ValidationError(
                    "Cannot validate accounting-period overlap without a company context."
                )
            if company is not None:
                clash = AccountingPeriod.objects.filter(
                    company=company, start_date__lte=end, end_date__gte=start,
                )
                if self.instance is not None:
                    clash = clash.exclude(pk=self.instance.pk)
                if clash.exists():
                    raise serializers.ValidationError(
                        "This period overlaps an existing accounting period."
                    )
        return attrs


class CostCenterSerializer(serializers.ModelSerializer):
    parent = CompanyPrimaryKeyRelatedField(
        queryset=CostCenter.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = CostCenter
        fields = ["id", "code", "name", "parent", "is_active"]


class JournalLineSerializer(serializers.ModelSerializer):
    account = CompanyPrimaryKeyRelatedField(queryset=Account.objects.all())
    cost_center = CompanyPrimaryKeyRelatedField(
        queryset=CostCenter.objects.all(), required=False, allow_null=True,
    )
    customer = CompanyPrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True,
    )
    supplier = CompanyPrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = JournalLine
        # B1-003: bank_statement_line is set only by the `match` action, never
        # by the client — an un-scoped writable FK here was a cross-tenant IDOR.
        # CR-161: customer and supplier exposed for party-tagged manual journals.
        fields = [
            "id", "account", "debit", "credit", "cost_center", "dimension",
            "customer", "supplier", "bank_statement_line", "reconciled_at",
        ]
        read_only_fields = ["reconciled_at", "bank_statement_line"]

    def _company(self):
        request = self.context.get("request")
        if not request:
            return None
        cu = get_company_user(request)
        return cu.company if cu else None

    # CR-161: party sub-ledger control accounts — a manual line touching one of
    # these must carry the matching party tag, otherwise the line silently
    # inflates the GL control balance vs the tagged party ledger / docs↔GL recon.
    # Other control accounts (Cash 1100, Inventory 1400, tax heads, 3100/3200
    # equity, …) stay manually postable — contra, opening balances and
    # adjustments legitimately hit them.
    _PARTY_CONTROL_CODES = {"1200", "2100", "2300", "1250"}
    _CUSTOMER_CONTROL_CODES = {"1200", "2300"}
    _SUPPLIER_CONTROL_CODES = {"2100", "1250"}

    def validate_account(self, account):
        # BB-000276: account must belong to the active company.
        company = self._company()
        if company is not None and account.company_id != company.id:
            raise serializers.ValidationError("Account must belong to this company.")
        return account

    def validate(self, attrs):
        # CR-161: enforce party tagging on AR/AP/advance control lines.
        account = attrs.get("account") or getattr(self.instance, "account", None)
        code = getattr(account, "code", "") or ""
        customer = attrs["customer"] if "customer" in attrs else getattr(self.instance, "customer", None)
        supplier = attrs["supplier"] if "supplier" in attrs else getattr(self.instance, "supplier", None)
        if code in self._PARTY_CONTROL_CODES and customer is None and supplier is None:
            raise serializers.ValidationError(
                f"Account '{code}' is a party control account — tag the line with a "
                "customer or supplier so the sub-ledger stays reconciled."
            )
        if code in self._CUSTOMER_CONTROL_CODES and supplier is not None:
            raise serializers.ValidationError(
                f"Account '{code}' is a receivable/customer-advance account — tag a customer, not a supplier."
            )
        if code in self._SUPPLIER_CONTROL_CODES and customer is not None:
            raise serializers.ValidationError(
                f"Account '{code}' is a payable/supplier-advance account — tag a supplier, not a customer."
            )
        return attrs

    def validate_cost_center(self, cost_center):
        if cost_center is None:
            return cost_center
        company = self._company()
        if company is not None and cost_center.company_id != company.id:
            raise serializers.ValidationError("Cost center must belong to this company.")
        return cost_center

    def validate_customer(self, customer):
        if customer is None:
            return customer
        company = self._company()
        if company is not None and customer.company_id != company.id:
            raise serializers.ValidationError("Customer must belong to this company.")
        return customer

    def validate_supplier(self, supplier):
        if supplier is None:
            return supplier
        company = self._company()
        if company is not None and supplier.company_id != company.id:
            raise serializers.ValidationError("Supplier must belong to this company.")
        return supplier


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)

    class Meta:
        model = JournalEntry
        fields = ["id", "number", "entry_date", "status", "source_type", "source_id", "purpose",
                  "narration", "posted_at", "reversed_entry", "lines"]
        read_only_fields = ["status", "source_type", "source_id", "purpose", "posted_at", "reversed_entry"]

    def validate_lines(self, lines):
        # B1-014: reject a line with BOTH sides set (or neither) here — it passes
        # the sum check but violates the journal_line_one_side DB CHECK -> 500.
        for line in lines:
            d = line.get("debit", 0) or 0
            c = line.get("credit", 0) or 0
            if (d > 0 and c > 0) or (d == 0 and c == 0):
                raise serializers.ValidationError(
                    "Each journal line must have exactly one of debit or credit."
                )
        debit = sum((line.get("debit", 0) for line in lines))
        credit = sum((line.get("credit", 0) for line in lines))
        if not lines or debit != credit:
            raise serializers.ValidationError("Journal lines must balance.")
        return lines

    def validate(self, attrs):
        # BB-000276: nested line FKs must match journal company.
        request = self.context.get("request")
        company = None
        if request:
            cu = get_company_user(request)
            company = cu.company if cu else None
        if company is not None:
            for line in attrs.get("lines") or []:
                account = line.get("account")
                if account is not None and account.company_id != company.id:
                    raise serializers.ValidationError(
                        {"lines": "Account must belong to this company."}
                    )
                cost_center = line.get("cost_center")
                if cost_center is not None and cost_center.company_id != company.id:
                    raise serializers.ValidationError(
                        {"lines": "Cost center must belong to this company."}
                    )
                customer = line.get("customer")
                if customer is not None and customer.company_id != company.id:
                    raise serializers.ValidationError(
                        {"lines": "Customer must belong to this company."}
                    )
                supplier = line.get("supplier")
                if supplier is not None and supplier.company_id != company.id:
                    raise serializers.ValidationError(
                        {"lines": "Supplier must belong to this company."}
                    )
        return attrs


class UnreconciledGlLineSerializer(serializers.ModelSerializer):
    """F2-028: a flat, paginable view of one account's still-unreconciled GL
    lines for the bank-reconciliation picker (no client-side journal paging)."""

    entry_id = serializers.IntegerField(source="entry.id", read_only=True)
    entry_number = serializers.CharField(source="entry.number", read_only=True)
    entry_date = serializers.DateField(source="entry.entry_date", read_only=True)
    narration = serializers.CharField(source="entry.narration", read_only=True)

    class Meta:
        model = JournalLine
        fields = [
            "id", "entry_id", "entry_number", "entry_date", "narration",
            "debit", "credit",
        ]


class BankReconSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankReconSession
        fields = ["id", "account", "statement", "status", "gl_balance", "statement_balance"]


class FixedAssetSerializer(serializers.ModelSerializer):
    monthly_depreciation = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    written_down_value = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    asset_account = CompanyPrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True
    )
    accumulated_depreciation_account = CompanyPrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True
    )
    depreciation_expense_account = CompanyPrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = FixedAsset
        fields = "__all__"
        # BB-000084: company must never be client-writable.
        read_only_fields = ["company", "depreciated_amount", "status", "disposed_at"]
        extra_kwargs = {
            "company": {"read_only": True},
            "asset_account": {"required": False},
            "accumulated_depreciation_account": {"required": False},
            "depreciation_expense_account": {"required": False},
        }
