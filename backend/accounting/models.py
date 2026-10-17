from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import CompanyScopedModel


class Account(CompanyScopedModel):
    class Type(models.TextChoices):
        ASSET = "ASSET"
        LIABILITY = "LIABILITY"
        EQUITY = "EQUITY"
        INCOME = "INCOME"
        EXPENSE = "EXPENSE"

    code = models.CharField(max_length=32)
    name = models.CharField(max_length=160)
    type = models.CharField(max_length=12, choices=Type.choices)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    is_system = models.BooleanField(default=False)
    is_control = models.BooleanField(default=False)
    bank_account = models.OneToOneField(
        "payments.BankAccount", null=True, blank=True, on_delete=models.SET_NULL, related_name="gl_account"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="uniq_account_code_per_company")]

    def clean(self):
        if self.parent_id and self.parent.company_id != self.company_id:
            raise ValidationError("Parent account must belong to the same company.")


class AccountingPeriod(CompanyScopedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN"
        SOFT_CLOSED = "SOFT_CLOSED"
        CLOSED = "CLOSED"

    name = models.CharField(max_length=64)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["-start_date"]
        constraints = [models.UniqueConstraint(fields=["company", "start_date", "end_date"], name="uniq_accounting_period")]

    def clean(self):
        # ACC-05: reject overlapping periods per company (serializer enforces this
        # on the API path; this covers management commands / data loads).
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError("end_date must not precede start_date.")
            if self.company_id:
                clash = AccountingPeriod.objects.filter(
                    company_id=self.company_id,
                    start_date__lte=self.end_date,
                    end_date__gte=self.start_date,
                ).exclude(pk=self.pk)
                if clash.exists():
                    raise ValidationError("This period overlaps an existing accounting period.")


class CostCenter(CompanyScopedModel):
    name = models.CharField(max_length=128)
    code = models.CharField(max_length=32)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="uniq_cost_center_code")]
        ordering = ["code"]


class JournalEntry(CompanyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        POSTED = "POSTED"
        REVERSED = "REVERSED"
        # ACS-20: a draft thrown away keeps its number, so the series has no silent gap.
        DISCARDED = "DISCARDED"

    # BB-000363: wide enough for JV-{source_type}-{purpose}-{id} without truncation collisions.
    number = models.CharField(max_length=64, blank=True)
    entry_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.PositiveBigIntegerField(null=True, blank=True)
    purpose = models.CharField(max_length=64, blank=True)
    narration = models.TextField(blank=True)
    # ACS-22: free-text voucher / document reference shown on the register.
    reference = models.CharField(max_length=120, blank=True)
    # ACS-24: client-generated token; a repeated create with the same token returns the first draft.
    client_token = models.CharField(max_length=64, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reversed_entry = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal_of")

    class Meta:
        ordering = ["-entry_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "source_type", "source_id", "purpose"],
                condition=Q(source_id__isnull=False, status="POSTED"),
                name="uniq_accounting_source_posting",
            ),
            # BB-000432: voucher numbers unique per company.
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~Q(number=""),
                name="uniq_journal_number_per_company",
            ),
            models.UniqueConstraint(
                fields=["company", "client_token"],
                condition=~Q(client_token=""),
                name="uniq_journal_client_token",
            ),
        ]
        indexes = [models.Index(fields=["company", "entry_date", "status"])]

    def assert_balanced(self):
        """ACC-10: the authoritative balance check is in ``PostingService.post``
        (before the entry is committed). This is a belt-and-braces re-check
        callable *after* lines are attached — e.g. from data-repair scripts or
        a books-health sweep. ``clean()`` cannot do it: it runs before the
        lines exist. Kept as an explicit method so nothing mistakes the old
        no-op ``clean()`` for a real guard.
        """
        totals = self.lines.aggregate(debit=models.Sum("debit"), credit=models.Sum("credit"))
        if (totals["debit"] or Decimal("0")) != (totals["credit"] or Decimal("0")):
            raise ValidationError("Posted journal entries must be balanced.")

    def clean(self):
        # Intentionally not re-checking balance here — see assert_balanced().
        # At clean()/full_clean() time an unsaved entry has no lines yet, so the
        # old aggregate check was always vacuously true (ACC-10).
        return None


class JournalLine(models.Model):
    # BB-000017: denormalized tenancy key (entry.company) for defense-in-depth.
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="journal_lines")
    debit = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    credit = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    cost_center = models.ForeignKey(CostCenter, null=True, blank=True, on_delete=models.PROTECT, related_name="journal_lines")
    dimension = models.CharField(max_length=64, blank=True)
    # ACS-22: what this line is for, when it differs from the voucher narration.
    narration = models.CharField(max_length=255, blank=True)
    # Wave 16B: GL-first party sub-ledger tags on control / advance accounts.
    customer = models.ForeignKey(
        "masters.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="journal_lines"
    )
    supplier = models.ForeignKey(
        "masters.Supplier", null=True, blank=True, on_delete=models.PROTECT, related_name="journal_lines"
    )
    bank_statement_line = models.ForeignKey(
        "payments.BankStatementLine", null=True, blank=True, on_delete=models.SET_NULL, related_name="gl_journal_lines"
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["account", "entry"]),
            models.Index(fields=["company", "account"], name="jl_company_account_idx"),
            models.Index(fields=["company", "account", "entry"], name="jl_company_acct_entry_idx"),
            models.Index(fields=["company", "customer", "account"], name="jl_company_customer_acct_idx"),
            models.Index(fields=["company", "supplier", "account"], name="jl_company_supplier_acct_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(debit__gte=0) & Q(credit__gte=0), name="journal_line_non_negative"),
            models.CheckConstraint(condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)), name="journal_line_one_side"),
        ]

    def clean(self):
        if self.entry_id and self.company_id and self.company_id != self.entry.company_id:
            raise ValidationError("Journal line company must match the entry company.")
        if self.account_id and self.account.company_id != self.entry.company_id:
            raise ValidationError("Account must belong to the entry company.")


class BankReconSession(CompanyScopedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN"
        # ACS-41: OPEN -> IN_PROGRESS (first match) -> RECONCILED (difference 0) -> FINALISED (locked).
        IN_PROGRESS = "IN_PROGRESS"
        RECONCILED = "RECONCILED"
        FINALISED = "FINALISED"
        CLOSED = "CLOSED"  # legacy value kept for old rows

    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="recon_sessions")
    statement = models.ForeignKey("payments.BankStatement", on_delete=models.PROTECT, related_name="gl_recon_sessions")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    gl_balance = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    statement_balance = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    # ACS-41: the bank's own closing figure and the date it is struck at.
    statement_date = models.DateField(null=True, blank=True)
    statement_closing_balance = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    finalised_at = models.DateTimeField(null=True, blank=True)
    finalised_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    write_off_entry = models.ForeignKey(JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reopen_reason = models.CharField(max_length=255, blank=True)
    # The last computed difference, so the session list can show it without recomputing every row.
    last_difference = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)


class JournalLineBankLink(models.Model):
    """ACS-42: an extra statement line tied to one ledger line (one GL line settled in several bank lines).

    The first statement line stays on ``JournalLine.bank_statement_line``; the rest live here.
    """

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True)
    journal_line = models.ForeignKey(JournalLine, on_delete=models.CASCADE, related_name="extra_bank_links")
    bank_line = models.OneToOneField("payments.BankStatementLine", on_delete=models.CASCADE, related_name="gl_extra_link")


class FixedAsset(CompanyScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        DISPOSED = "DISPOSED"

    class Method(models.TextChoices):
        SLM = "SLM", "Straight line"
        WDV = "WDV", "Written down value"

    name = models.CharField(max_length=160)
    asset_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="fixed_assets")
    accumulated_depreciation_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="depreciating_assets")
    depreciation_expense_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="depreciation_assets")
    acquisition_date = models.DateField()
    acquisition_cost = models.DecimalField(max_digits=16, decimal_places=2)
    useful_life_months = models.PositiveIntegerField()
    depreciated_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    last_depreciation_error = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    disposed_at = models.DateField(null=True, blank=True)
    # ACC-09: WDV / block depreciation. `salvage_value` is the residual the
    # asset is never depreciated below (SLM base = cost − salvage; WDV floor).
    # `wdv_annual_rate` is the Income-Tax block rate as a percent (e.g. 15, 40) —
    # VERIFY THE RATE AND BLOCK GROUPING WITH YOUR CA. `block_key` groups assets
    # into an IT-Act block of assets for reporting.
    method = models.CharField(max_length=3, choices=Method.choices, default=Method.SLM)
    salvage_value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    wdv_annual_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    block_key = models.CharField(max_length=64, blank=True, default="")
    # Months older than the automatic catch-up window that still need a charge.
    # Comma-separated YYYY-MM. Cleared as an explicit backfill posts them.
    depreciation_catchup_months = models.CharField(max_length=800, blank=True, default="")

    # ACS-53: how the purchase was paid, and the entry that booked it.
    class Funding(models.TextChoices):
        ALREADY_BOOKED = "ALREADY_BOOKED", "Already booked"
        CASH = "CASH", "Paid from cash"
        BANK = "BANK", "Paid from bank"
        SUPPLIER = "SUPPLIER", "On credit from a supplier"

    funding = models.CharField(max_length=16, choices=Funding.choices, default=Funding.ALREADY_BOOKED)
    funding_bank_account = models.ForeignKey(
        "payments.BankAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    funding_supplier = models.ForeignKey(
        "masters.Supplier", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    acquisition_journal = models.ForeignKey(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    # ACS-55: the preset the asset was created from (computers, vehicles...), kept for reporting.
    category = models.CharField(max_length=32, blank=True, default="")

    @property
    def depreciable_base(self) -> Decimal:
        base = (self.acquisition_cost or Decimal("0")) - (self.salvage_value or Decimal("0"))
        return base if base > 0 else Decimal("0")

    @property
    def written_down_value(self) -> Decimal:
        return (self.acquisition_cost or Decimal("0")) - (self.depreciated_amount or Decimal("0"))

    @property
    def monthly_depreciation(self):
        """This month's charge, before the remaining-balance clamp the runner
        applies. SLM: (cost − salvage) / life. WDV: opening WDV × rate / 12,
        never taking the book value below salvage."""
        if (self.method or self.Method.SLM) == self.Method.WDV:
            rate = Decimal(str(self.wdv_annual_rate or 0))
            if rate <= 0:
                return Decimal("0.00")
            opening = self.written_down_value
            room = opening - (self.salvage_value or Decimal("0"))
            if room <= 0:
                return Decimal("0.00")
            charge = (opening * rate / Decimal("100") / Decimal("12")).quantize(Decimal("0.01"))
            return min(charge, room) if charge > 0 else Decimal("0.00")
        if not self.useful_life_months:
            return Decimal("0.00")
        return (self.depreciable_base / self.useful_life_months).quantize(Decimal("0.01"))


class CashShiftRegister(CompanyScopedModel):
    """One cashier's till for one business day. Locked rows cannot be edited."""

    class Status(models.TextChoices):
        OPEN = "OPEN"
        CLOSED = "CLOSED"

    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cash_shifts",
    )
    business_date = models.DateField()
    opening_float = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cash_dropped = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    terminal_id = models.CharField(max_length=64, blank=True, default="")
    terminal_label = models.CharField(max_length=64, blank=True, default="")
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    denominations = models.JSONField(default=dict, blank=True)
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    counted_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    variance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-business_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "terminal_id"],
                condition=models.Q(status="OPEN") & ~models.Q(terminal_id=""),
                name="uniq_open_cash_shift_per_terminal",
            ),
        ]


class CashShiftAdjustment(CompanyScopedModel):
    """A manager's correction to a till that has already been counted and locked.

    The shift's counted cash, expected cash and variance stay exactly as they were on the day.
    The correction (a cash receipt voided after the count) is recorded here instead, so the shift
    report can show what changed afterwards, by whom and why.
    """

    shift = models.ForeignKey(CashShiftRegister, on_delete=models.PROTECT, related_name="adjustments")
    receipt = models.ForeignKey(
        "payments.CustomerReceipt", on_delete=models.PROTECT, related_name="till_adjustments"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=500)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="shift_adjustment_amount_positive"),
        ]


class CashDrop(CompanyScopedModel):
    """One removal of cash from an open drawer. `cash_dropped` on the shift is the cached sum."""

    shift = models.ForeignKey(CashShiftRegister, on_delete=models.CASCADE, related_name="drops")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=200, blank=True, default="")
    dropped_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-dropped_at", "-id"]


class Expense(CompanyScopedModel):
    """Cash/bank expense voucher — not a GST purchase invoice."""

    number = models.CharField(max_length=32, blank=True, db_index=True)
    expense_date = models.DateField(default=timezone.localdate)
    category = models.ForeignKey(
        "masters.ExpenseCategory", on_delete=models.PROTECT, related_name="expenses",
    )
    party_name = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    notes = models.TextField(blank=True)
    attachment = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    # ACS-14: an expense is voided with a reason, never hard-deleted.
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        VOID = "VOID"

    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    void_reason = models.CharField(max_length=300, blank=True)
    # ACS-15/16: how it was paid and which ledger it hits.
    class PaymentMode(models.TextChoices):
        CASH = "CASH"
        BANK = "BANK"

    payment_mode = models.CharField(max_length=8, choices=PaymentMode.choices, default=PaymentMode.CASH)
    bank_account = models.ForeignKey(
        "payments.BankAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    expense_account = models.ForeignKey(
        "accounting.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    journal_entry = models.ForeignKey(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    # ACS-51: which cost centre the expense belongs to; it rides through to the ledger line.
    cost_center = models.ForeignKey(
        "accounting.CostCenter", null=True, blank=True, on_delete=models.PROTECT, related_name="expenses",
    )
    # ACS-17: GST included in `amount`, split by head. ITC is only claimed when the box is ticked.
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    cgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    sgst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    igst_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    itc_eligible = models.BooleanField(default=False)
    supplier_gstin = models.CharField(max_length=15, blank=True)
    # Tax the company deducted from what it paid out; it owes this to the government.
    tds_section = models.CharField(max_length=10, blank=True)
    tds_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    # ACS-17: set when a recurring template created this expense (one per template and date).
    recurring_template = models.ForeignKey(
        "accounting.RecurringExpense", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_expenses",
    )

    class Meta:
        ordering = ["-expense_date", "-id"]
        # ACS-71: the register filters on company, status and date together.
        indexes = [
            models.Index(fields=["company", "expense_date"]),
            models.Index(fields=["company", "status", "expense_date"], name="exp_company_status_date_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_expense_number_per_company",
            )
        ]

    def __str__(self):
        return self.number or f"Expense #{self.pk}"


class RecurringExpense(CompanyScopedModel):
    """ACS-17: a template for an expense that repeats (rent, a subscription)."""

    class Frequency(models.TextChoices):
        MONTHLY = "MONTHLY"
        QUARTERLY = "QUARTERLY"
        YEARLY = "YEARLY"

    category = models.ForeignKey("masters.ExpenseCategory", on_delete=models.PROTECT, related_name="recurring_expenses")
    party_name = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    notes = models.TextField(blank=True)
    payment_mode = models.CharField(max_length=8, choices=Expense.PaymentMode.choices, default=Expense.PaymentMode.CASH)
    bank_account = models.ForeignKey("payments.BankAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    expense_account = models.ForeignKey("accounting.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    cost_center = models.ForeignKey("accounting.CostCenter", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY)
    next_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_created_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["next_date", "id"]


class ExpenseCategoryAccount(CompanyScopedModel):
    """ACS-15: the expense ledger a category posts to by default."""

    category = models.OneToOneField(
        "masters.ExpenseCategory", on_delete=models.CASCADE, related_name="ledger_mapping",
    )
    account = models.ForeignKey("accounting.Account", on_delete=models.PROTECT, related_name="+")


class AccountMonthlyBalance(models.Model):
    """Closed-month debit/credit rollup so reports do not rescan history (BUG-PERF-004)."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="account_monthly_balances",
    )
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="monthly_balances")
    period = models.DateField(help_text="First day of the month.")
    debit = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    credit = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "account", "period"],
                name="uniq_account_month_balance",
            ),
        ]
        indexes = [models.Index(fields=["company", "period"], name="acct_month_bal_co_period_idx")]


class AccountBalanceRollup(models.Model):
    """Checkpoint: rollup rows match JournalLine through max_line_id."""

    company = models.OneToOneField(
        "accounts.Company", on_delete=models.CASCADE, related_name="account_balance_rollup",
    )
    max_line_id = models.PositiveBigIntegerField(default=0)
    refreshed_at = models.DateTimeField(auto_now=True)
