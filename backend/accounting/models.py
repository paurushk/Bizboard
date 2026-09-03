from decimal import Decimal

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
