from decimal import Decimal

from rest_framework import serializers

from core.permissions import get_company_user
from core.models import FileAsset
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Customer, ExpenseCategory, Supplier
from payments.models import BankAccount

from .models import (
    Account, AccountingPeriod, BankReconSession, CashShiftAdjustment, CashShiftRegister, CostCenter,
    Expense, ExpenseCategoryAccount, FixedAsset, JournalEntry, JournalLine, RecurringExpense,
)


class CashShiftAdjustmentSerializer(serializers.ModelSerializer):
    receipt_number = serializers.CharField(source="receipt.number", read_only=True)
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CashShiftAdjustment
        fields = ["id", "receipt", "receipt_number", "amount", "reason", "approved_by_name", "created_at"]
        read_only_fields = fields

    def get_approved_by_name(self, obj) -> str:
        user = obj.approved_by
        return getattr(user, "full_name", "") or getattr(user, "email", "") or ""


class CashShiftRegisterSerializer(serializers.ModelSerializer):
    adjustments = CashShiftAdjustmentSerializer(many=True, read_only=True)
    adjustments_total = serializers.SerializerMethodField()
    adjusted_expected_cash = serializers.SerializerMethodField()
    adjusted_variance = serializers.SerializerMethodField()

    class Meta:
        model = CashShiftRegister
        fields = [
            "id", "cashier", "business_date", "opening_float", "cash_dropped", "denominations",
            "expected_cash", "counted_cash", "variance", "status", "locked_at",
            "terminal_id", "terminal_label", "opened_at", "closed_at",
            "adjustments", "adjustments_total", "adjusted_expected_cash", "adjusted_variance",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "cashier", "cash_dropped", "expected_cash", "counted_cash", "variance", "status",
            "locked_at", "closed_at", "opened_at", "denominations", "created_at", "updated_at",
            "adjustments", "adjustments_total", "adjusted_expected_cash", "adjusted_variance",
        ]

    def _adjusted(self, obj):
        from .cash_shifts import adjusted_figures

        return adjusted_figures(obj)

    def get_adjustments_total(self, obj) -> str:
        return str(self._adjusted(obj)[0])

    def get_adjusted_expected_cash(self, obj) -> str:
        return str(self._adjusted(obj)[1])

    def get_adjusted_variance(self, obj) -> str:
        return str(self._adjusted(obj)[2])


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    bank_account = CompanyPrimaryKeyRelatedField(
        queryset=BankAccount.objects.all(), required=False, allow_null=True,
    )
    expense_account = CompanyPrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True,
    )
    expense_account_name = serializers.SerializerMethodField()
    posted_to_books = serializers.SerializerMethodField()
    journal_number = serializers.CharField(source="journal_entry.number", read_only=True, default="")
    # R28: ids from another company must not resolve.
    category = CompanyPrimaryKeyRelatedField(queryset=ExpenseCategory.objects.all())
    attachment = CompanyPrimaryKeyRelatedField(queryset=FileAsset.objects.all(), required=False, allow_null=True)
    cost_center = CompanyPrimaryKeyRelatedField(queryset=CostCenter.objects.all(), required=False, allow_null=True)
    gst_amount = serializers.SerializerMethodField()
    attachment_name = serializers.CharField(source="attachment.original_name", read_only=True, default="")

    class Meta:
        model = Expense
        fields = [
            "id", "number", "expense_date", "category", "category_name",
            "party_name", "amount", "notes", "attachment", "created_at", "updated_at",
            "status", "voided_at", "void_reason",
            "payment_mode", "bank_account", "expense_account", "expense_account_name",
            "posted_to_books", "journal_number",
            "attachment_name", "cost_center", "gst_rate", "cgst_amount", "sgst_amount", "igst_amount", "gst_amount",
            "itc_eligible", "supplier_gstin", "tds_section", "tds_amount", "recurring_template",
        ]
        read_only_fields = ["number", "status", "voided_at", "void_reason", "recurring_template"]

    def get_gst_amount(self, obj):
        return str((obj.cgst_amount or 0) + (obj.sgst_amount or 0) + (obj.igst_amount or 0))

    def get_posted_to_books(self, obj):
        return obj.journal_entry_id is not None

    def get_expense_account_name(self, obj):
        account = obj.expense_account
        return f"{account.code} {account.name}" if account else ""

    def validate_expense_account(self, account):
        if account is None:
            return account
        if account.type != Account.Type.EXPENSE:
            raise serializers.ValidationError("Choose an expense account.")
        if not account.is_active:
            raise serializers.ValidationError("That account is inactive.")
        return account

    def validate(self, attrs):
        inst = self.instance
        mode = attrs.get("payment_mode", getattr(inst, "payment_mode", Expense.PaymentMode.CASH))
        bank = attrs["bank_account"] if "bank_account" in attrs else getattr(inst, "bank_account", None)
        if mode == Expense.PaymentMode.BANK and bank is None:
            raise serializers.ValidationError({"bank_account": "Choose the bank account this was paid from."})
        if mode == Expense.PaymentMode.CASH and bank is not None:
            # Cash expenses carry no bank; clear it rather than keep a misleading link.
            attrs["bank_account"] = None
        self._validate_tax(attrs, inst)
        return attrs

    def _validate_tax(self, attrs, inst):
        def val(name):
            return attrs[name] if name in attrs else (getattr(inst, name, None) or Decimal("0"))

        amount = val("amount")
        cgst, sgst, igst, tds = val("cgst_amount"), val("sgst_amount"), val("igst_amount"), val("tds_amount")
        errors = {}
        for name, v in (("cgst_amount", cgst), ("sgst_amount", sgst), ("igst_amount", igst), ("tds_amount", tds)):
            if v < 0:
                errors[name] = "Cannot be negative."
        if igst > 0 and (cgst > 0 or sgst > 0):
            errors["igst_amount"] = "Use either CGST and SGST, or IGST, not both."
        if cgst != sgst and (cgst > 0 or sgst > 0):
            errors["sgst_amount"] = "CGST and SGST are charged in equal amounts."
        if cgst + sgst + igst > amount:
            errors["cgst_amount"] = "The GST cannot be more than the amount."
        if tds > amount:
            errors["tds_amount"] = "TDS cannot be more than the amount."
        section = attrs["tds_section"] if "tds_section" in attrs else getattr(inst, "tds_section", "")
        if tds > 0 and not (section or "").strip():
            errors["tds_section"] = "Enter the TDS section (for example 194C)."
        eligible = attrs["itc_eligible"] if "itc_eligible" in attrs else getattr(inst, "itc_eligible", False)
        gstin = attrs["supplier_gstin"] if "supplier_gstin" in attrs else getattr(inst, "supplier_gstin", "")
        if eligible and cgst + sgst + igst > 0 and not gstin:
            errors["supplier_gstin"] = "Input tax credit needs the supplier GSTIN."
        if gstin:
            try:
                from core.validators import validate_gstin

                validate_gstin(gstin)
            except Exception:  # noqa: BLE001 - any validator failure is a bad GSTIN
                errors["supplier_gstin"] = "That GSTIN is not valid."
        if errors:
            raise serializers.ValidationError(errors)


class RecurringExpenseSerializer(serializers.ModelSerializer):
    category = CompanyPrimaryKeyRelatedField(queryset=ExpenseCategory.objects.all())
    bank_account = CompanyPrimaryKeyRelatedField(queryset=BankAccount.objects.all(), required=False, allow_null=True)
    expense_account = CompanyPrimaryKeyRelatedField(queryset=Account.objects.all(), required=False, allow_null=True)
    cost_center = CompanyPrimaryKeyRelatedField(queryset=CostCenter.objects.all(), required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = RecurringExpense
        fields = [
            "id", "category", "category_name", "party_name", "amount", "notes", "payment_mode", "bank_account",
            "expense_account", "cost_center", "frequency", "next_date", "end_date", "is_active", "last_created_date",
        ]
        read_only_fields = ["last_created_date"]

    def validate(self, attrs):
        inst = self.instance
        mode = attrs.get("payment_mode", getattr(inst, "payment_mode", Expense.PaymentMode.CASH))
        bank = attrs["bank_account"] if "bank_account" in attrs else getattr(inst, "bank_account", None)
        if mode == Expense.PaymentMode.BANK and bank is None:
            raise serializers.ValidationError({"bank_account": "Choose the bank account this is paid from."})
        if mode == Expense.PaymentMode.CASH and bank is not None:
            attrs["bank_account"] = None
        start = attrs.get("next_date", getattr(inst, "next_date", None))
        end = attrs.get("end_date", getattr(inst, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "The end date cannot be before the next date."})
        acct = attrs.get("expense_account")
        if acct is not None and acct.type != Account.Type.EXPENSE:
            raise serializers.ValidationError({"expense_account": "Choose an expense account."})
        return attrs


class ExpenseCategoryAccountSerializer(serializers.ModelSerializer):
    category = CompanyPrimaryKeyRelatedField(queryset=ExpenseCategory.objects.all())
    account = CompanyPrimaryKeyRelatedField(queryset=Account.objects.all())
    account_name = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseCategoryAccount
        fields = ["id", "category", "account", "account_name"]

    def get_account_name(self, obj):
        return f"{obj.account.code} {obj.account.name}"

    def validate_account(self, account):
        if account.type != Account.Type.EXPENSE:
            raise serializers.ValidationError("Choose an expense account.")
        if not account.is_active:
            raise serializers.ValidationError("That account is inactive.")
        return account


class AccountSerializer(serializers.ModelSerializer):
    parent = CompanyPrimaryKeyRelatedField(
        queryset=Account.objects.all(), required=False, allow_null=True
    )
    bank_account = CompanyPrimaryKeyRelatedField(
        queryset=BankAccount.objects.all(), required=False, allow_null=True
    )

    # ACS-50: what the chart screen needs to show and guard each row.
    has_postings = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source="parent.name", read_only=True, default="")

    class Meta:
        model = Account
        fields = [
            "id", "code", "name", "type", "parent", "parent_name", "is_system", "is_control",
            "bank_account", "is_active", "has_postings", "balance",
        ]
        read_only_fields = ["is_system", "is_control", "has_postings", "balance", "parent_name"]

    def get_has_postings(self, obj):
        used = self.context.get("used_account_ids")
        if used is not None:
            return obj.pk in used
        return obj.journal_lines.exists()

    def get_balance(self, obj):
        balances = self.context.get("account_balances")
        if balances is None:
            return None
        return str(Decimal(str(balances.get(obj.pk, 0) or 0)).quantize(Decimal("0.01")))

    def _company(self):
        request = self.context.get("request")
        cu = get_company_user(request) if request else None
        return cu.company if cu else None

    def validate_code(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Enter an account code.")
        company = self._company() or getattr(self.instance, "company", None)
        if company is not None:
            clash = Account.objects.filter(company=company, code__iexact=value)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            other = clash.first()
            if other is not None:
                raise serializers.ValidationError(f"Code {value} is already used by {other.name}. Choose another code.")
        return value

    def validate(self, attrs):
        inst = self.instance
        if inst is not None:
            # A ledger with postings keeps its code and type: reports and filings are keyed on them.
            for field in ("code", "type"):
                if field in attrs and attrs[field] != getattr(inst, field) and inst.journal_lines.exists():
                    raise serializers.ValidationError(
                        {field: f"The {field} cannot change because this account already has postings. Create a new account instead."}
                    )
            if attrs.get("is_active") is False and inst.is_active:
                from django.db.models import Sum

                from .models import JournalEntry

                agg = inst.journal_lines.filter(
                    entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED]
                ).aggregate(d=Sum("debit"), c=Sum("credit"))
                balance = (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))
                if balance != 0:
                    raise serializers.ValidationError(
                        {"is_active": f"This account still has a balance of {balance}. Move it to another account first, then deactivate."}
                    )
                if inst.children.filter(is_active=True).exists():
                    raise serializers.ValidationError({"is_active": "Deactivate or move its sub-accounts first."})
        parent = attrs.get("parent")
        if parent is not None:
            if inst is not None and parent.pk == inst.pk:
                raise serializers.ValidationError({"parent": "An account cannot be its own parent."})
            node = parent
            while node is not None and inst is not None:
                if node.pk == inst.pk:
                    raise serializers.ValidationError({"parent": "That parent would make a loop in the chart."})
                node = node.parent
            acct_type = attrs.get("type") or (inst.type if inst else None)
            if acct_type and parent.type != acct_type:
                raise serializers.ValidationError({"parent": "A sub-account must be the same type as its parent."})
        return attrs


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
    # ACS-51: how much history hangs off this cost centre, so deleting is a clear choice.
    usage = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source="parent.name", read_only=True, default="")

    class Meta:
        model = CostCenter
        fields = ["id", "code", "name", "parent", "parent_name", "is_active", "usage"]
        read_only_fields = ["usage", "parent_name"]

    def get_usage(self, obj):
        counts = self.context.get("cost_center_usage")
        if counts is not None:
            return counts.get(obj.pk, {"journal_lines": 0, "invoices": 0, "expenses": 0})
        return {
            "journal_lines": obj.journal_lines.count(),
            "invoices": obj.sales_invoices.count() + obj.purchase_invoices.count(),
            "expenses": obj.expenses.count(),
        }

    def validate_code(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Enter a code.")
        request = self.context.get("request")
        cu = get_company_user(request) if request else None
        company = cu.company if cu else getattr(self.instance, "company", None)
        if company is not None:
            clash = CostCenter.objects.filter(company=company, code__iexact=value)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            other = clash.first()
            if other is not None:
                raise serializers.ValidationError(f"Code {value} is already used by {other.name}. Choose another code.")
        return value

    def validate(self, attrs):
        inst = self.instance
        parent = attrs.get("parent")
        if parent is not None and inst is not None:
            node = parent
            while node is not None:
                if node.pk == inst.pk:
                    raise serializers.ValidationError({"parent": "That parent would make a loop."})
                node = node.parent
        if inst is not None and attrs.get("is_active") is False and inst.is_active:
            if inst.children.filter(is_active=True).exists():
                raise serializers.ValidationError({"is_active": "Deactivate its sub-centres first."})
        return attrs


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
            "id", "account", "account_code", "account_name", "debit", "credit", "cost_center",
            "cost_center_name", "dimension", "narration",
            "customer", "customer_name", "supplier", "supplier_name",
            "bank_statement_line", "reconciled_at",
        ]
        read_only_fields = [
            "reconciled_at", "bank_statement_line", "account_code", "account_name",
            "cost_center_name", "customer_name", "supplier_name",
        ]

    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    cost_center_name = serializers.CharField(source="cost_center.name", read_only=True, default="")
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default="")

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
        # ACS-11: inactive accounts take no new manual postings.
        if not account.is_active:
            raise serializers.ValidationError(
                f"Account {account.code} {account.name} is inactive. Reactivate it or choose another account."
            )
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
    # ACS-10: where the entry came from, and whether the user may reverse it here.
    source_label = serializers.SerializerMethodField()
    source_path = serializers.SerializerMethodField()
    can_reverse = serializers.SerializerMethodField()
    # ACS-20/21/23: what the register and the detail drawer show.
    can_edit = serializers.SerializerMethodField()
    total_debit = serializers.SerializerMethodField()
    posted_by_name = serializers.SerializerMethodField()
    reversal_of = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = ["id", "number", "entry_date", "status", "source_type", "source_id", "purpose",
                  "narration", "reference", "client_token", "posted_at", "posted_by_name",
                  "reversed_entry", "reversal_of", "lines",
                  "source_label", "source_path", "can_reverse", "can_edit", "total_debit"]
        read_only_fields = ["status", "source_type", "source_id", "purpose", "posted_at", "reversed_entry",
                            "source_label", "source_path", "can_reverse", "can_edit", "total_debit",
                            "posted_by_name", "reversal_of"]
        extra_kwargs = {"client_token": {"write_only": True, "required": False}}

    def get_can_edit(self, obj):
        return obj.status == JournalEntry.Status.DRAFT

    def get_total_debit(self, obj):
        return sum((line.debit or Decimal("0")) for line in obj.lines.all())

    def get_posted_by_name(self, obj):
        user = obj.posted_by
        if user is None:
            return ""
        return (getattr(user, "get_full_name", lambda: "")() or getattr(user, "email", "") or "")

    def get_reversal_of(self, obj):
        # The entry this one reverses, if any (reverse side of the one-to-one).
        try:
            return obj.reversal_of.id
        except JournalEntry.reversal_of.RelatedObjectDoesNotExist:
            return None

    def get_source_label(self, obj):
        from .journal_sources import source_label

        return source_label(obj.source_type)

    def get_source_path(self, obj):
        from .journal_sources import source_path

        return source_path(obj.source_type, obj.source_id)

    def get_can_reverse(self, obj):
        from .journal_sources import is_manual

        return obj.status == JournalEntry.Status.POSTED and is_manual(obj.source_type)

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
    signed_amount = serializers.SerializerMethodField()

    class Meta:
        model = JournalLine
        fields = [
            "id", "entry_id", "entry_number", "entry_date", "narration",
            "debit", "credit", "signed_amount",
        ]

    def get_signed_amount(self, obj):
        return (obj.debit or Decimal("0")) - (obj.credit or Decimal("0"))


class BankReconSessionSerializer(serializers.ModelSerializer):
    # GL recon matches a journal line to a statement line. Receipt matching is separate.
    match_kind = serializers.SerializerMethodField()
    other_recon_path = serializers.SerializerMethodField()
    # ACS-45: enough context to pick a session out of a list.
    account_name = serializers.CharField(source="account.name", read_only=True)
    statement_name = serializers.SerializerMethodField()
    difference = serializers.DecimalField(source="last_difference", max_digits=16, decimal_places=2, read_only=True)
    finalised_by_name = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = BankReconSession
        fields = [
            "id", "account", "account_name", "statement", "statement_name", "status", "gl_balance",
            "statement_balance", "statement_date", "statement_closing_balance", "difference",
            "finalised_at", "finalised_by_name", "reopen_reason", "created_at", "summary",
            "match_kind", "other_recon_path",
        ]
        read_only_fields = [
            "status", "gl_balance", "statement_balance", "finalised_at", "reopen_reason", "created_at",
        ]

    def get_statement_name(self, obj):
        st = obj.statement
        span = f"{st.period_start or ''} to {st.period_end or ''}".strip() if (st.period_start or st.period_end) else ""
        return " ".join(p for p in (st.bank_account.name, st.source_filename, span) if p)

    def get_finalised_by_name(self, obj):
        u = obj.finalised_by
        return (getattr(u, "email", "") or "") if u is not None else ""

    def get_summary(self, obj):
        # Only on a single session: the figures cost several queries.
        if not self.context.get("with_summary"):
            return None
        from .bank_match import session_summary

        return session_summary(obj)

    def get_match_kind(self, obj):
        return "gl_statement_line"

    def get_other_recon_path(self, obj):
        return "/payments/reconciliation"


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
    # ACS-53: who paid for it. Both must belong to this company.
    funding_bank_account = CompanyPrimaryKeyRelatedField(queryset=BankAccount.objects.all(), required=False, allow_null=True)
    funding_supplier = CompanyPrimaryKeyRelatedField(queryset=Supplier.objects.all(), required=False, allow_null=True)
    # ACS-52: what the register screen shows without a second call.
    net_book_value = serializers.SerializerMethodField()
    last_depreciation_month = serializers.SerializerMethodField()
    depreciation_errors = serializers.SerializerMethodField()
    catchup_months = serializers.SerializerMethodField()
    acquisition_journal_number = serializers.CharField(source="acquisition_journal.number", read_only=True, default="")

    class Meta:
        model = FixedAsset
        fields = "__all__"
        # BB-000084: company must never be client-writable.
        read_only_fields = [
            "company", "depreciated_amount", "status", "disposed_at",
            "last_depreciation_error", "depreciation_catchup_months", "acquisition_journal",
        ]

    def get_net_book_value(self, obj):
        return str(obj.written_down_value)

    def get_last_depreciation_month(self, obj):
        months = self.context.get("last_dep_month")
        if months is not None:
            return months.get(obj.pk, "")
        entry = (
            JournalEntry.objects.filter(
                company_id=obj.company_id, source_type="FIXED_ASSET", source_id=obj.pk,
                status=JournalEntry.Status.POSTED, purpose__startswith="DEPRECIATION-",
            ).order_by("-entry_date").first()
        )
        return entry.entry_date.strftime("%Y-%m") if entry else ""

    def get_depreciation_errors(self, obj):
        out = []
        for part in (obj.last_depreciation_error or "").split("; "):
            part = part.strip()
            if not part:
                continue
            month, _sep, reason = part.partition(": ")
            if len(month) == 7 and month[4] == "-":
                out.append({"month": month, "reason": reason})
            else:
                out.append({"month": "", "reason": part})
        return out

    def get_catchup_months(self, obj):
        return [m for m in (obj.depreciation_catchup_months or "").split(",") if m]
        extra_kwargs = {
            "company": {"read_only": True},
            "asset_account": {"required": False},
            "accumulated_depreciation_account": {"required": False},
            "depreciation_expense_account": {"required": False},
        }

    # ACS-13: once depreciation has posted the schedule inputs are history. The
    # screen greys these out, but the API must refuse them too.
    _SCHEDULE_FIELDS = (
        "acquisition_cost", "acquisition_date", "useful_life_months", "method",
        "salvage_value", "wdv_annual_rate", "block_key",
        "asset_account", "accumulated_depreciation_account", "depreciation_expense_account",
    )

    def validate(self, attrs):
        inst = self.instance
        cost = attrs.get("acquisition_cost", getattr(inst, "acquisition_cost", None))
        life = attrs.get("useful_life_months", getattr(inst, "useful_life_months", None))
        salvage = attrs.get("salvage_value", getattr(inst, "salvage_value", None)) or Decimal("0")
        rate = attrs.get("wdv_annual_rate", getattr(inst, "wdv_annual_rate", None)) or Decimal("0")
        errors = {}
        if cost is not None and cost <= 0:
            errors["acquisition_cost"] = "Cost must be greater than zero."
        if life is not None and life < 1:
            errors["useful_life_months"] = "Useful life must be at least one month."
        if salvage < 0:
            errors["salvage_value"] = "Salvage value cannot be negative."
        elif cost is not None and salvage >= cost:
            errors["salvage_value"] = "Salvage value must be less than the cost."
        if rate < 0 or rate > 100:
            errors["wdv_annual_rate"] = "Rate must be between 0 and 100."
        funding = attrs.get("funding", getattr(inst, "funding", FixedAsset.Funding.ALREADY_BOOKED))
        bank = attrs["funding_bank_account"] if "funding_bank_account" in attrs else getattr(inst, "funding_bank_account", None)
        supplier = attrs["funding_supplier"] if "funding_supplier" in attrs else getattr(inst, "funding_supplier", None)
        if funding == FixedAsset.Funding.BANK and bank is None:
            errors["funding_bank_account"] = "Choose the bank account it was paid from."
        if funding == FixedAsset.Funding.SUPPLIER and supplier is None:
            errors["funding_supplier"] = "Choose the supplier it was bought from."
        if inst is not None:
            for name in ("funding", "funding_bank_account", "funding_supplier"):
                if name in attrs and attrs[name] != getattr(inst, name):
                    errors[name] = "How the asset was paid for cannot change after it is registered."
        if errors:
            raise serializers.ValidationError(errors)
        if inst is not None:
            if inst.status != FixedAsset.Status.ACTIVE:
                raise serializers.ValidationError("A disposed asset cannot be changed.")
            if (inst.depreciated_amount or Decimal("0")) > 0:
                changed = [
                    name for name in self._SCHEDULE_FIELDS
                    if name in attrs and attrs[name] != getattr(inst, name)
                ]
                if changed:
                    raise serializers.ValidationError({
                        name: "Depreciation has already posted; this cannot be changed. Only the name can be edited."
                        for name in changed
                    })
        return attrs


class AccountingSettingsSerializer(serializers.Serializer):
    """GET/POST /accounting/settings/ — 7.9b backfill flag is part of the money contract."""

    accounting_enabled = serializers.BooleanField()
    accounting_backfill_needed = serializers.BooleanField(read_only=True)
    # ACS-15: expenses dated on or after this day post to the ledger (null = register only).
    expense_gl_start_date = serializers.DateField(allow_null=True, required=False)
    expense_gl_pending = serializers.DictField(read_only=True, required=False)

