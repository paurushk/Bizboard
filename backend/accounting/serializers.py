from rest_framework import serializers

from core.permissions import get_company_user
from core.serializers import CompanyPrimaryKeyRelatedField

from .models import Account, AccountingPeriod, BankReconSession, CostCenter, FixedAsset, JournalEntry, JournalLine


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "code", "name", "type", "parent", "is_system", "is_control", "bank_account", "is_active"]
        read_only_fields = ["is_system", "is_control"]


class AccountingPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountingPeriod
        fields = ["id", "name", "start_date", "end_date", "status"]

    def validate(self, attrs):
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
    class Meta:
        model = CostCenter
        fields = ["id", "code", "name", "parent", "is_active"]


class JournalLineSerializer(serializers.ModelSerializer):
    account = CompanyPrimaryKeyRelatedField(queryset=Account.objects.all())
    cost_center = CompanyPrimaryKeyRelatedField(
        queryset=CostCenter.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = JournalLine
        # B1-003: bank_statement_line is set only by the `match` action, never
        # by the client — an un-scoped writable FK here was a cross-tenant IDOR.
        fields = ["id", "account", "debit", "credit", "cost_center", "dimension", "bank_statement_line", "reconciled_at"]
        read_only_fields = ["reconciled_at", "bank_statement_line"]

    def _company(self):
        request = self.context.get("request")
        if not request:
            return None
        cu = get_company_user(request)
        return cu.company if cu else None

    def validate_account(self, account):
        # BB-000276: account must belong to the active company.
        company = self._company()
        if company is not None and account.company_id != company.id:
            raise serializers.ValidationError("Account must belong to this company.")
        return account

    def validate_cost_center(self, cost_center):
        if cost_center is None:
            return cost_center
        company = self._company()
        if company is not None and cost_center.company_id != company.id:
            raise serializers.ValidationError("Cost center must belong to this company.")
        return cost_center


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)

    class Meta:
        model = JournalEntry
        fields = ["id", "number", "entry_date", "status", "source_type", "source_id", "purpose",
                  "narration", "posted_at", "reversed_entry", "lines"]
        read_only_fields = ["status", "source_type", "source_id", "purpose", "posted_at", "reversed_entry"]

    def validate_lines(self, lines):
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
        return attrs


class BankReconSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankReconSession
        fields = ["id", "account", "statement", "status", "gl_balance", "statement_balance"]


class FixedAssetSerializer(serializers.ModelSerializer):
    monthly_depreciation = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    written_down_value = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

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
