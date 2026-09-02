"""Payroll preview — employees, pay runs, simplified PF/ESI/PT; not full statutory HRMS."""

from decimal import Decimal

from django.db import models

from core.models import CompanyScopedModel


class Employee(CompanyScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        INACTIVE = "INACTIVE"

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=32)
    salary = models.DecimalField(max_digits=14, decimal_places=2)
    # R4-007: PF is statutorily on Basic + DA, not gross. When these are set the
    # PF wage base uses (basic + da); when both are 0 it falls back to the gross
    # salary (legacy behaviour).
    basic = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    da = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    pf_applicable = models.BooleanField(default=False)
    pf_wage_ceiling = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("15000.00"))
    esi_applicable = models.BooleanField(default=False)
    pt_state = models.CharField(max_length=64, blank=True)
    # tds_rate is a flat-% override the payroll admin can set; when 0 and
    # tax_regime is NEW, sec-192 TDS is projected from 12× the contracted gross
    # (see payroll.services.annual_new_regime_tax). OLD regime + no override → 0
    # (Chapter VI-A / HRA declarations are not collected yet).
    tds_rate = models.DecimalField(max_digits=6, decimal_places=3, default=0)

    class TaxRegime(models.TextChoices):
        NEW = "NEW", "New regime (default)"
        OLD = "OLD", "Old regime"

    tax_regime = models.CharField(
        max_length=4, choices=TaxRegime.choices, default=TaxRegime.NEW
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_employee_code_per_company"),
        ]


class PayRun(CompanyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"

    period = models.CharField(max_length=7, help_text="YYYY-MM")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ["-period"]
        constraints = [
            models.UniqueConstraint(fields=["company", "period"], name="uniq_payrun_period_per_company"),
        ]


class PaySlip(models.Model):
    pay_run = models.ForeignKey(PayRun, on_delete=models.CASCADE, related_name="slips")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="payslips")
    gross = models.DecimalField(max_digits=14, decimal_places=2)
    # R4-008: loss-of-pay / partial-month proration. period_days is the calendar
    # days in the pay month; paid_days is how many the employee is paid for. When
    # paid_days < period_days the gross (and statutory dues on it) are prorated.
    period_days = models.PositiveSmallIntegerField(null=True, blank=True)
    paid_days = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=14, decimal_places=2)
    pf_employee = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    esi_employee = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pt_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pf_employer = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # PR-01: employer 12% split — EPS 8.33% (capped ₹1,250) + EPF residual —
    # plus EPFO admin (A/c 2) and EDLI (A/c 21). pf_employer == eps + epf.
    pf_employer_eps = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pf_employer_epf = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pf_admin_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    edli_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    esi_employer = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tds_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["pay_run", "employee"], name="uniq_payslip_employee_per_run",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pay_run_id and not self.company_id:
            self.company_id = self.pay_run.company_id
        super().save(*args, **kwargs)
