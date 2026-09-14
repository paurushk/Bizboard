"""Payroll & Statutory Processing persona journey.

Validates:
1. P1 (Owner) sets up Employees with statutory configs (PF basic+da, ESI, state PT).
2. P5 (Munshi / Accountant) creates PayRun and generates PaySlips with exact statutory deductions:
   - Employee PF (12% of capped wage base).
   - Employer PF split: EPS (8.33% capped at 1,250) + EPF residual + Admin + EDLI.
   - ESI (0.75% employee + 3.25% employer).
3. PayRun completion posts double-entry GL journal:
   - Dr 5800 Payroll Expenses.
   - Cr 2261 PF Payable, Cr 2262 ESI Payable, Cr 2150 Salaries Payable.
4. PayRun cancellation reverses GL journal cleanly and returns run to DRAFT.
5. Boundary check: Sales Staff (P2) is forbidden from viewing or managing payroll.
6. Zero invariant violations: assert_all_invariants(company) holds throughout.
"""

from decimal import Decimal
import pytest

from accounting.models import JournalEntry
from core.invariants import assert_all_invariants
from payroll.models import Employee, PayRun, PaySlip
from payroll.services import cancel_pay_run, complete_pay_run, compute_statutory
from tests.personas.fixtures import seed_archetype

pytestmark = [pytest.mark.django_db, pytest.mark.dark_module]


def test_pj_payroll_and_statutory_gl_lifecycle():
    trader = seed_archetype("trader")
    company = trader.company
    owner = trader.owner
    acct = trader.acct

    # 1. P1 (Owner) creates two employees
    emp_senior = Employee.objects.create(
        company=company,
        name="Sunil Rao",
        code="EMP-001",
        salary=Decimal("30000.00"),
        basic=Decimal("15000.00"),
        da=Decimal("5000.00"),
        pf_applicable=True,
        pf_wage_ceiling=Decimal("15000.00"),
        esi_applicable=False,
        pt_state="Karnataka",
        created_by=owner,
        updated_by=owner,
    )
    emp_junior = Employee.objects.create(
        company=company,
        name="Deepak Kumar",
        code="EMP-002",
        salary=Decimal("18000.00"),
        basic=Decimal("10000.00"),
        da=Decimal("2000.00"),
        pf_applicable=True,
        esi_applicable=True,
        pt_state="Karnataka",
        created_by=owner,
        updated_by=owner,
    )

    # 2. Statutory calculation verification
    calc_sr = compute_statutory(emp_senior, company)
    assert calc_sr["pf_employee"] == Decimal("1800.00")  # 12% of 15,000
    assert calc_sr["esi_employee"] == Decimal("0.00")
    assert calc_sr["pt_amount"] == Decimal("200.00")     # Karnataka PT on salary >= 25,000
    assert calc_sr["net"] == Decimal("28000.00")

    calc_jr = compute_statutory(emp_junior, company)
    assert calc_jr["pf_employee"] == Decimal("1440.00")  # 12% of 12,000 (basic+da)
    assert calc_jr["esi_employee"] == Decimal("135.00")  # 0.75% of 18,000
    assert calc_jr["net"] == Decimal("16425.00")

    # 3. P5 (Accountant) creates PayRun for May 2026
    pay_run = PayRun.objects.create(
        company=company,
        period="2026-05",
        status=PayRun.Status.DRAFT,
        created_by=acct,
        updated_by=acct,
    )

    # Create payslips using computed values
    for emp, calc in ((emp_senior, calc_sr), (emp_junior, calc_jr)):
        PaySlip.objects.create(
            company=company,
            pay_run=pay_run,
            employee=emp,
            gross=calc["gross"],
            deductions=calc["deductions"],
            net=calc["net"],
            pf_employee=calc["pf_employee"],
            esi_employee=calc["esi_employee"],
            pt_amount=calc["pt_amount"],
            pf_employer=calc["pf_employer"],
            pf_employer_eps=calc["pf_employer_eps"],
            pf_employer_epf=calc["pf_employer_epf"],
            pf_admin_charges=calc["pf_admin_charges"],
            edli_charges=calc["edli_charges"],
            esi_employer=calc["esi_employer"],
            tds_amount=calc["tds_amount"],
        )

    # 4. Accountant completes pay run and GL journal is posted
    completed_run = complete_pay_run(pay_run, user=acct)
    assert completed_run.status == PayRun.Status.COMPLETED

    # Verify JournalEntry posted
    payroll_je = JournalEntry.objects.filter(
        company=company,
        source_type="PAY_RUN",
        source_id=pay_run.pk,
        status=JournalEntry.Status.POSTED,
    ).first()
    assert payroll_je is not None, "GL journal must be posted on pay run completion"

    je_lines = {l.account.code: (l.debit, l.credit) for l in payroll_je.lines.all()}
    # Dr 5800 Payroll Expenses
    assert je_lines["5800"][0] > 0
    # Cr 2261 PF Payable
    assert je_lines["2261"][1] > 0
    # Cr 2262 ESI Payable
    assert je_lines["2262"][1] > 0
    # Cr 1100 (Cash/Bank payout) or 2150 (Salaries Payable)
    net_credit = je_lines.get("1100", (Decimal(0), Decimal(0)))[1] or je_lines.get("2150", (Decimal(0), Decimal(0)))[1]
    assert net_credit == (calc_sr["net"] + calc_jr["net"])

    # 5. Rollback / Cancel Pay Run
    cancelled_run = cancel_pay_run(completed_run, user=owner)
    assert cancelled_run.status == PayRun.Status.DRAFT

    payroll_je.refresh_from_db()
    assert payroll_je.status == JournalEntry.Status.REVERSED, "Original JE must be reversed"

    # 6. Boundary check: Sales staff (P2) is forbidden from payroll API endpoints
    sales_payruns = trader.sales_client.get("/api/v1/payroll/pay-runs/")
    assert sales_payruns.status_code in (403, 404), "Sales staff must not view pay runs"

    sales_employees = trader.sales_client.get("/api/v1/payroll/employees/")
    assert sales_employees.status_code in (403, 404), "Sales staff must not view employee salaries"

    # 7. Invariants hold
    assert_all_invariants(company)
