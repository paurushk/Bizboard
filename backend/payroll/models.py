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
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    pf_applicable = models.BooleanField(default=False)
    pf_wage_ceiling = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("15000.00"))
    esi_applicable = models.BooleanField(default=False)
    pt_state = models.CharField(max_length=64, blank=True)

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
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="payslips")
    gross = models.DecimalField(max_digits=14, decimal_places=2)
    deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=14, decimal_places=2)
    pf_employee = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    esi_employee = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pt_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pf_employer = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    esi_employer = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["pay_run", "employee"], name="uniq_payslip_employee_per_run",
            ),
        ]
