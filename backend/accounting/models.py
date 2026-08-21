from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
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

    # BB-000363: wide enough for JV-{source_type}-{purpose}-{id} without truncation collisions.
    number = models.CharField(max_length=64, blank=True)
    entry_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.PositiveBigIntegerField(null=True, blank=True)
    purpose = models.CharField(max_length=64, blank=True)
    narration = models.TextField(blank=True)
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
        ]
        indexes = [models.Index(fields=["company", "entry_date", "status"])]

    def clean(self):
        if self.status == self.Status.POSTED:
            totals = self.lines.aggregate(debit=models.Sum("debit"), credit=models.Sum("credit"))
            if (totals["debit"] or Decimal("0")) != (totals["credit"] or Decimal("0")):
                raise ValidationError("Posted journal entries must be balanced.")


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
        CLOSED = "CLOSED"

    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="recon_sessions")
    statement = models.ForeignKey("payments.BankStatement", on_delete=models.PROTECT, related_name="gl_recon_sessions")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    gl_balance = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    statement_balance = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))


class FixedAsset(CompanyScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        DISPOSED = "DISPOSED"

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

    @property
    def monthly_depreciation(self):
        return (self.acquisition_cost / self.useful_life_months).quantize(Decimal("0.01"))
