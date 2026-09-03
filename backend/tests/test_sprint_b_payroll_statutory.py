"""Sprint B: simplified PF / ESI / PT on pay-run complete + gross GL split."""

from decimal import Decimal

import pytest
from django.test import override_settings

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from payroll.models import Employee, PayRun
from payroll.services import complete_pay_run, compute_statutory

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def test_compute_pf_esi_pt_known_fixture(tenant_a):
    emp = Employee.objects.create(
        company=tenant_a.company,
        name="Statutory",
        code="ST1",
        salary=Decimal("20000.00"),
        pf_applicable=True,
        pf_wage_ceiling=Decimal("15000.00"),
        esi_applicable=True,
        pt_state="Karnataka",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    computed = compute_statutory(emp, tenant_a.company)
    assert computed["pf_employee"] == Decimal("1800.00")  # 12% of 15000
    assert computed["esi_employee"] == Decimal("150.00")  # 0.75% of 20000
    # Karnataka PT is nil below Rs.25,000/month (was a flat Rs.200 default).
    assert computed["pt_amount"] == Decimal("0.00")
    # New-regime sec-192 TDS is nil at 20k/month (annual 2.4L, below the 4L slab).
    assert computed["tds_amount"] == Decimal("0.00")
    assert computed["deductions"] == Decimal("1950.00")
    assert computed["net"] == Decimal("18050.00")
    assert computed["pf_employer"] == Decimal("1800.00")            # EPS + EPF
    assert computed["pf_employer_eps"] == Decimal("1249.50")        # 8.33% of 15000
    assert computed["pf_employer_epf"] == Decimal("550.50")         # residual
    assert computed["pf_admin_charges"] == Decimal("75.00")         # 0.5% of 15000
    assert computed["edli_charges"] == Decimal("75.00")             # 0.5% of 15000, cap 75
    assert computed["esi_employer"] == Decimal("650.00")  # 3.25% of 20000


def test_complete_pay_run_persists_statutory_and_posts_gross_split(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    Employee.objects.create(
        company=tenant_a.company,
        name="Statutory",
        code="ST2",
        salary=Decimal("20000.00"),
        pf_applicable=True,
        esi_applicable=True,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    run = PayRun.objects.create(
        company=tenant_a.company,
        period="2026-07",
        status=PayRun.Status.DRAFT,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    complete_pay_run(run, tenant_a.owner)
    slip = run.slips.get()
    assert slip.pf_employee == Decimal("1800.00")
    assert slip.esi_employee == Decimal("150.00")
    assert slip.pt_amount == Decimal("0.00")   # no PT state configured
    assert slip.net == Decimal("18050.00")
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="PAY_RUN", source_id=run.pk, purpose="PAYROLL",
    )
    codes = {line.account.code: (line.debit, line.credit) for line in entry.lines.all()}
    # 20000 gross + 1800 PF er + 75 admin + 75 EDLI + 650 ESI er
    assert codes["5800"][0] == Decimal("22600.00")
    assert codes["2261"][1] == Decimal("3750.00")  # 1800 emp + 1800 er + 75 admin + 75 EDLI
    assert codes["2262"][1] == Decimal("800.00")   # 150 emp + 650 er
    assert "2263" not in codes                       # PT is nil
    assert codes["1100"][1] == Decimal("18050.00")


def test_compute_statutory_non_zero_tds_rate(tenant_a):
    emp = Employee.objects.create(
        company=tenant_a.company,
        name="TDS",
        code="TDS1",
        salary=Decimal("50000.00"),
        pf_applicable=False,
        esi_applicable=False,
        tds_rate=Decimal("10.00"),
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    computed = compute_statutory(emp, tenant_a.company)
    assert computed["tds_amount"] == Decimal("5000.00")
    assert computed["pt_amount"] == Decimal("200.00")
    assert computed["deductions"] == Decimal("5200.00")
    assert computed["net"] == Decimal("44800.00")


def test_payroll_accrual_credits_wages_payable_for_net(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    Employee.objects.create(
        company=tenant_a.company,
        name="Accrual",
        code="ST3",
        salary=Decimal("20000.00"),
        pf_applicable=True,
        esi_applicable=False,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    run = PayRun.objects.create(
        company=tenant_a.company,
        period="2026-08",
        status=PayRun.Status.DRAFT,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    complete_pay_run(run, tenant_a.owner, pay_from_cash=False)
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="PAY_RUN", source_id=run.pk, purpose="PAYROLL",
    )
    assert entry.lines.get(account__code="2150").credit == Decimal("18200.00")  # 20000 - PF 1800 (no PT)
    assert not entry.lines.filter(account__code="1100").exists()


@override_settings(ENABLE_PAYROLL=False)
def test_payroll_gate_stays_closed_when_flag_off(tenant_a):
    resp = tenant_a.client.get("/api/v1/payroll/employees/")
    assert resp.status_code == 404


def test_employee_api_accepts_statutory_fields(tenant_a):
    created = tenant_a.client.post(
        "/api/v1/payroll/employees/",
        {
            "name": "API Emp",
            "code": "API1",
            "salary": "18000.00",
            "status": "ACTIVE",
            "pfApplicable": True,
            "pfWageCeiling": "15000.00",
            "esiApplicable": True,
            "ptState": "Karnataka",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    body = _body(created)
    assert body["pf_applicable"] is True
    assert body["esi_applicable"] is True
    run = tenant_a.client.post("/api/v1/payroll/pay-runs/", {"period": "2026-09"}, format="json")
    run_id = _body(run)["id"]
    complete = tenant_a.client.post(f"/api/v1/payroll/pay-runs/{run_id}/complete/")
    assert complete.status_code == 200, complete.data
    slip = _body(complete)["slips"][0]
    assert Decimal(str(slip["pf_employee"])) == Decimal("1800.00")
    assert Decimal(str(slip["esi_employee"])) == Decimal("135.00")
    assert Decimal(str(slip["pt_amount"])) == Decimal("0.00")  # Karnataka: nil below 25k
