"""Payroll service — complete pay run with simplified PF/ESI/PT and optional GL."""

import calendar
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from core.exceptions import BusinessRuleError

from .models import Employee, PayRun, PaySlip

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MONEY = Decimal("0.01")
PF_RATE = Decimal("0.12")
ESI_EMPLOYEE_RATE = Decimal("0.0075")
ESI_EMPLOYER_RATE = Decimal("0.0325")
DEFAULT_PT_SLABS = [{"min": "15000.01", "max": None, "amount": "200"}]


def pay_period_month_end(period: str) -> date:
    if not PERIOD_RE.match(period or ""):
        raise BusinessRuleError("Pay period must be YYYY-MM.")
    year = int(period[:4])
    month = int(period[5:7])
    return date(year, month, calendar.monthrange(year, month)[1])


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _resolve_pt_slabs(company, employee) -> list:
    raw = getattr(company, "payroll_pt_slabs", None) or []
    state_key = (getattr(employee, "pt_state", "") or getattr(company, "state", "") or "").strip()
    if isinstance(raw, dict):
        aliases = {
            "KA": "Karnataka",
            "ka": "Karnataka",
            "Karnataka": "KA",
            "karnataka": "KA",
        }
        slabs = raw.get(state_key)
        if slabs is None and state_key:
            slabs = raw.get(state_key.title()) or raw.get(state_key.upper()) or raw.get(state_key.lower())
            if slabs is None and state_key in aliases:
                slabs = raw.get(aliases[state_key])
        if not slabs:
            return list(DEFAULT_PT_SLABS)
        return list(slabs)
    if isinstance(raw, list) and raw:
        return list(raw)
    return list(DEFAULT_PT_SLABS)


def _pt_amount(gross: Decimal, slabs: list) -> Decimal:
    for slab in slabs or []:
        min_v = _money(slab.get("min") or 0)
        max_raw = slab.get("max")
        max_v = None if max_raw in (None, "", "null") else _money(max_raw)
        if gross >= min_v and (max_v is None or gross <= max_v):
            return _money(slab.get("amount") or 0)
    return _money(0)


ESI_WAGE_CEILING = Decimal("21000")


def compute_statutory(employee, company, *, gross=None) -> dict:
    gross_amt = _money(gross if gross is not None else employee.salary)
    pf_employee = _money(0)
    pf_employer = _money(0)
    esi_employee = _money(0)
    esi_employer = _money(0)
    if employee.pf_applicable:
        ceiling = _money(employee.pf_wage_ceiling or Decimal("15000"))
        wage_base = min(gross_amt, ceiling)
        pf_employee = _money(wage_base * PF_RATE)
        pf_employer = _money(wage_base * PF_RATE)
    # BB-000704: ESI only when gross within statutory wage ceiling (default ₹21,000).
    if employee.esi_applicable:
        esi_ceiling = _money(getattr(company, "esi_wage_ceiling", None) or ESI_WAGE_CEILING)
        if gross_amt <= esi_ceiling:
            esi_employee = _money(gross_amt * ESI_EMPLOYEE_RATE)
            esi_employer = _money(gross_amt * ESI_EMPLOYER_RATE)
    pt_amount = _pt_amount(gross_amt, _resolve_pt_slabs(company, employee))
    deductions = _money(pf_employee + esi_employee + pt_amount)
    net = _money(gross_amt - deductions)
    return {
        "gross": gross_amt,
        "pf_employee": pf_employee,
        "pf_employer": pf_employer,
        "esi_employee": esi_employee,
        "esi_employer": esi_employer,
        "pt_amount": pt_amount,
        "deductions": deductions,
        "net": net,
    }


def _credit_line(account, amount: Decimal):
    if amount <= 0:
        return None
    return {"account": account, "credit": amount}


@transaction.atomic
def complete_pay_run(pay_run: PayRun, user, *, pay_from_cash: bool = True) -> PayRun:
    locked = PayRun.objects.select_for_update().get(pk=pay_run.pk)
    if locked.status == PayRun.Status.COMPLETED:
        raise BusinessRuleError("Pay run already completed.")
    from reporting.gst_periods import assert_period_allows_money_amend

    assert_period_allows_money_amend(locked.company, pay_period_month_end(locked.period))
    slips = list(locked.slips.select_related("employee"))
    if not slips:
        active = Employee.objects.filter(company=locked.company, status=Employee.Status.ACTIVE)
        for emp in active:
            computed = compute_statutory(emp, locked.company)
            PaySlip.objects.create(pay_run=locked, employee=emp, **computed)
        slips = list(locked.slips.select_related("employee"))
    total_gross = sum((s.gross for s in slips), Decimal("0"))
    total_net = sum((s.net for s in slips), Decimal("0"))
    total_pf = sum((getattr(s, "pf_employee", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    total_esi = sum((getattr(s, "esi_employee", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    total_pt = sum((getattr(s, "pt_amount", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    total_pf_er = sum((getattr(s, "pf_employer", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    total_esi_er = sum((getattr(s, "esi_employer", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    company = locked.company
    if company.accounting_enabled and total_gross > 0:
        from accounting.services import PostingService, seed_chart_of_accounts

        seed_chart_of_accounts(company, user)
        expense = PostingService._account(company, "5800")
        credit_acct = PostingService._account(company, "1100" if pay_from_cash else "2150")
        # BB-000703: employer PF/ESI — Dr expense / Cr same statutory payables.
        employer_cost = total_pf_er + total_esi_er
        lines = [{"account": expense, "debit": total_gross + employer_cost}]
        for code, amount in (
            ("2261", total_pf + total_pf_er),
            ("2262", total_esi + total_esi_er),
            ("2263", total_pt),
        ):
            line = _credit_line(PostingService._account(company, code), amount)
            if line:
                lines.append(line)
        net_line = _credit_line(credit_acct, total_net)
        if net_line:
            lines.append(net_line)
        PostingService.post(
            company=company,
            source_type="PayRun",
            source_id=locked.pk,
            purpose="PAYROLL",
            entry_date=pay_period_month_end(locked.period),
            lines=lines,
            user=user,
        )
    locked.status = PayRun.Status.COMPLETED
    locked.updated_by = user
    locked.save(update_fields=["status", "updated_by", "updated_at"])
    return locked
