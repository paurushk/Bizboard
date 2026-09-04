"""WS-24 — payroll statutory correctness (review B9-003, B9-015, B9-020, B9-030, B9-037)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from payroll.models import Employee, PayRun, PaySlip
from payroll.services import (
    annual_new_regime_tax,
    compute_statutory,
    complete_pay_run,
)

pytestmark = pytest.mark.django_db


def _emp(tenant, **kw):
    defaults = dict(
        company=tenant.company,
        name="P",
        code=f"E{Employee.objects.count() + 1}",
        salary=Decimal("30000.00"),
        pf_applicable=True,
        pf_wage_ceiling=Decimal("15000.00"),
        esi_applicable=False,
        pt_state="Maharashtra",
        created_by=tenant.owner,
        updated_by=tenant.owner,
    )
    defaults.update(kw)
    return Employee.objects.create(**defaults)


# --------------------------------------------------------------------------- #
# B9-003 — a zero-pay (full LOP) month
# --------------------------------------------------------------------------- #
def test_full_month_lop_yields_all_zero_slip(tenant_a):
    emp = _emp(tenant_a, salary=Decimal("50000.00"))
    c = compute_statutory(emp, tenant_a.company, paid_days=0, period_days=30, month=6)
    assert c["gross"] == Decimal("0.00")
    assert c["tds_amount"] == Decimal("0.00")  # was a phantom 1/12 of the annual projection
    assert c["deductions"] == Decimal("0.00")
    assert c["net"] == Decimal("0.00")  # was negative == -tds_amount


def test_net_never_negative_on_partial_month(tenant_a):
    # a high flat TDS rate on a heavily-LOP month must not drive net < 0
    emp = _emp(tenant_a, salary=Decimal("60000.00"), tds_rate=Decimal("40"))
    c = compute_statutory(emp, tenant_a.company, paid_days=2, period_days=30, month=6)
    assert c["net"] >= Decimal("0.00")
    assert c["deductions"] <= c["gross"]


# --------------------------------------------------------------------------- #
# B9-015 — PT keyed to the salary rate, not the prorated earnings
# --------------------------------------------------------------------------- #
def test_pt_uses_salary_rate_not_prorated_gross(tenant_a):
    emp = _emp(tenant_a, salary=Decimal("30000.00"), pt_state="Maharashtra")
    full = compute_statutory(emp, tenant_a.company, month=6)
    lop = compute_statutory(emp, tenant_a.company, paid_days=10, period_days=30, month=6)
    assert lop["pt_amount"] == full["pt_amount"]
    assert lop["gross"] < full["gross"]


# --------------------------------------------------------------------------- #
# B9-030 — marginal relief at the 12L 87A cliff
# --------------------------------------------------------------------------- #
def test_marginal_relief_at_87a_cliff():
    at_cap = annual_new_regime_tax(Decimal("1275000"))  # 12,00,000 taxable after 75k SD
    just_over = annual_new_regime_tax(Decimal("1275500"))  # 12,00,500 taxable
    # without marginal relief `just_over` jumped to ~62k; with relief the extra
    # tax cannot exceed the ₹500 by which income crossed the cap (+4% cess).
    assert at_cap == Decimal("0.00")
    assert just_over <= Decimal("520.00")


def test_new_regime_tax_high_income_unchanged():
    # well above the cliff, marginal relief is inert
    assert annual_new_regime_tax(Decimal("2075000")) > Decimal("70000")


# --------------------------------------------------------------------------- #
# B9-020 — deleting an employee with payroll history
# --------------------------------------------------------------------------- #
def test_cannot_delete_employee_with_payslips(tenant_a):
    emp = _emp(tenant_a)
    run = PayRun.objects.create(
        company=tenant_a.company, period="2026-06",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    PaySlip.objects.create(
        company=tenant_a.company, pay_run=run, employee=emp,
        gross=Decimal("30000"), net=Decimal("28000"),
    )
    resp = tenant_a.client.delete(f"/api/v1/payroll/employees/{emp.id}/")
    assert resp.status_code == 400, resp.data
    assert Employee.objects.filter(pk=emp.id).exists()


# --------------------------------------------------------------------------- #
# B9-037 — post a completed run to the GL after accounting is turned on
# --------------------------------------------------------------------------- #
def test_post_pay_run_gl_catch_up(tenant_a):
    tenant_a.company.accounting_enabled = False
    tenant_a.company.save(update_fields=["accounting_enabled"])
    emp = _emp(tenant_a, salary=Decimal("30000.00"), pf_applicable=False)
    run = PayRun.objects.create(
        company=tenant_a.company, period="2026-06",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    run = complete_pay_run(run, tenant_a.owner)
    assert run.status == PayRun.Status.COMPLETED
    assert not JournalEntry.objects.filter(
        company=tenant_a.company, source_type="PAY_RUN", source_id=run.id
    ).exists()

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)

    resp = tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run.id}/post-gl/")
    assert resp.status_code == 200, resp.data
    assert JournalEntry.objects.filter(
        company=tenant_a.company, source_type="PAY_RUN", source_id=run.id,
        purpose="PAYROLL", status=JournalEntry.Status.POSTED,
    ).exists()

    # idempotent — a second call is a 400, not a duplicate entry
    resp2 = tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run.id}/post-gl/")
    assert resp2.status_code == 400
    assert JournalEntry.objects.filter(
        company=tenant_a.company, source_type="PAY_RUN", source_id=run.id, purpose="PAYROLL",
    ).count() == 1
