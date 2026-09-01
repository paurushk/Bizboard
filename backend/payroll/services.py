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

# R4-010: illustrative current monthly Professional Tax ladders for the states
# that have more than one slab. These DO change — a company should override via
# Company.payroll_pt_slabs; this is only the fallback when they haven't. The
# `feb_amount` key on a slab is used for Maharashtra's February top-up.
_STATE_PT_SLABS = {
    "Maharashtra": [
        {"min": "0", "max": "7500", "amount": "0"},
        {"min": "7500.01", "max": "10000", "amount": "175"},
        {"min": "10000.01", "max": None, "amount": "200", "feb_amount": "300"},
    ],
    "West Bengal": [
        {"min": "0", "max": "10000", "amount": "0"},
        {"min": "10000.01", "max": "15000", "amount": "110"},
        {"min": "15000.01", "max": "25000", "amount": "130"},
        {"min": "25000.01", "max": "40000", "amount": "150"},
        {"min": "40000.01", "max": None, "amount": "200"},
    ],
    "Tamil Nadu": [
        {"min": "0", "max": "21000", "amount": "0"},
        {"min": "21000.01", "max": "30000", "amount": "135"},
        {"min": "30000.01", "max": "45000", "amount": "315"},
        {"min": "45000.01", "max": "60000", "amount": "690"},
        {"min": "60000.01", "max": "75000", "amount": "1025"},
        {"min": "75000.01", "max": None, "amount": "1250"},
    ],
    "Andhra Pradesh": [
        {"min": "0", "max": "15000", "amount": "0"},
        {"min": "15000.01", "max": "20000", "amount": "150"},
        {"min": "20000.01", "max": None, "amount": "200"},
    ],
    "Telangana": [
        {"min": "0", "max": "15000", "amount": "0"},
        {"min": "15000.01", "max": "20000", "amount": "150"},
        {"min": "20000.01", "max": None, "amount": "200"},
    ],
    "Gujarat": [
        {"min": "0", "max": "12000", "amount": "0"},
        {"min": "12000.01", "max": None, "amount": "200"},
    ],
}


def validate_pt_slabs(slabs) -> list[str]:
    """R4-010: return warnings for a slab ladder with gaps / overlaps / bad order."""
    warnings: list[str] = []
    if not isinstance(slabs, list) or not slabs:
        return warnings
    try:
        parsed = []
        for s in slabs:
            lo = Decimal(str(s.get("min") or 0))
            hi = None if s.get("max") in (None, "", "null") else Decimal(str(s.get("max")))
            parsed.append((lo, hi))
        parsed.sort(key=lambda p: p[0])
        for i, (lo, hi) in enumerate(parsed):
            if hi is not None and hi < lo:
                warnings.append(f"PT slab starting {lo} has max {hi} below its min.")
            if i + 1 < len(parsed):
                nxt_lo = parsed[i + 1][0]
                if hi is None:
                    warnings.append("PT slab with no upper bound is not the last slab.")
                elif nxt_lo > hi + Decimal("0.01"):
                    warnings.append(f"PT slab gap between {hi} and {nxt_lo}.")
                elif nxt_lo <= hi:
                    warnings.append(f"PT slabs overlap around {hi}.")
    except (TypeError, ValueError, ArithmeticError):
        warnings.append("PT slabs are malformed.")
    return warnings


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
        if slabs:
            return list(slabs)
        raw = []
    if isinstance(raw, list) and raw:
        return list(raw)
    # R4-010: fall back to a known multi-slab state ladder before the single
    # Karnataka-style default.
    for name, slabs in _STATE_PT_SLABS.items():
        if state_key.strip().lower() == name.lower():
            return list(slabs)
    return list(DEFAULT_PT_SLABS)


def _pt_amount(gross: Decimal, slabs: list, *, month: int | None = None) -> Decimal:
    for slab in slabs or []:
        min_v = _money(slab.get("min") or 0)
        max_raw = slab.get("max")
        max_v = None if max_raw in (None, "", "null") else _money(max_raw)
        if gross >= min_v and (max_v is None or gross <= max_v):
            # Maharashtra-style February top-up.
            if month == 2 and slab.get("feb_amount") not in (None, ""):
                return _money(slab.get("feb_amount"))
            return _money(slab.get("amount") or 0)
    return _money(0)


ESI_WAGE_CEILING = Decimal("21000")


def compute_statutory(employee, company, *, gross=None, month: int | None = None, paid_days=None, period_days=None) -> dict:
    gross_full = _money(gross if gross is not None else employee.salary)
    pf_employee = _money(0)
    pf_employer = _money(0)
    esi_employee = _money(0)
    esi_employer = _money(0)
    prorate = Decimal("1")
    if paid_days is not None and period_days:
        days = Decimal(str(paid_days))
        period = Decimal(str(period_days))
        if period > 0 and days < period:
            prorate = days / period
    gross_amt = _money(gross_full * prorate)
    if employee.pf_applicable:
        ceiling = _money(employee.pf_wage_ceiling or Decimal("15000"))
        # R4-007: PF wage base = Basic + DA when configured; else fall back to
        # the gross salary (legacy behaviour). Prorate Basic+DA the same as gross.
        basic_da = _money(getattr(employee, "basic", 0) or 0) + _money(getattr(employee, "da", 0) or 0)
        if basic_da > 0:
            basic_da = _money(basic_da * prorate)
        pf_wage = basic_da if basic_da > 0 else gross_amt
        wage_base = min(pf_wage, ceiling)
        pf_employee = _money(wage_base * PF_RATE)
        pf_employer = _money(wage_base * PF_RATE)
    if employee.esi_applicable:
        esi_ceiling = _money(getattr(company, "esi_wage_ceiling", None) or Decimal("21000"))
        # Eligibility is on full-month wages, not LOP-prorated gross.
        if gross_full <= esi_ceiling:
            esi_employee = _money(gross_amt * ESI_EMPLOYEE_RATE)
            esi_employer = _money(gross_amt * ESI_EMPLOYER_RATE)
    pt_amount = _pt_amount(gross_amt, _resolve_pt_slabs(company, employee), month=month)
    tds_rate = _money(getattr(employee, "tds_rate", 0) or 0)
    tds_amount = _money(gross_amt * tds_rate / Decimal("100")) if tds_rate else _money(0)
    deductions = _money(pf_employee + esi_employee + pt_amount + tds_amount)
    net = _money(gross_amt - deductions)
    return {
        "gross": gross_amt,
        "pf_employee": pf_employee,
        "pf_employer": pf_employer,
        "esi_employee": esi_employee,
        "esi_employer": esi_employer,
        "pt_amount": pt_amount,
        "tds_amount": tds_amount,
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
    _pt_month = int(locked.period[5:7]) if PERIOD_RE.match(locked.period or "") else None
    _period_end = pay_period_month_end(locked.period)
    _period_days = _period_end.day  # calendar days in the pay month
    active = Employee.objects.filter(company=locked.company, status=Employee.Status.ACTIVE)
    active_by_id = {emp.id: emp for emp in active}
    # R4-009: drop only never-finalised (zero-net) slips for employees who are no
    # longer active. A slip that carries real pay (net > 0) means the person was
    # employed during the period — keep it so a reopen→re-complete cycle doesn't
    # wipe their wages.
    locked.slips.exclude(employee_id__in=active_by_id.keys()).filter(net=0).delete()
    for emp in active:
        existing_slip = locked.slips.filter(employee=emp).first()
        gross = getattr(existing_slip, "gross", None)
        paid_days = getattr(existing_slip, "paid_days", None)
        # LOP endpoint used to stamp gross=0 as a placeholder — treat that as missing.
        if paid_days is not None and (gross is None or gross == 0):
            gross = None
        base_gross = _money(gross if gross is not None else emp.salary)
        computed = compute_statutory(
            emp,
            locked.company,
            gross=base_gross,
            month=_pt_month,
            paid_days=paid_days,
            period_days=_period_days,
        )
        computed["period_days"] = _period_days
        computed["paid_days"] = paid_days
        PaySlip.objects.update_or_create(
            pay_run=locked,
            company=locked.company,
            employee=emp,
            defaults=computed,
        )
    slips = list(locked.slips.select_related("employee"))
    total_gross = sum((s.gross for s in slips), Decimal("0"))
    total_net = sum((s.net for s in slips), Decimal("0"))
    total_pf = sum((getattr(s, "pf_employee", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    total_esi = sum((getattr(s, "esi_employee", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    total_pt = sum((getattr(s, "pt_amount", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    total_tds = sum((getattr(s, "tds_amount", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    total_pf_er = sum((getattr(s, "pf_employer", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    total_esi_er = sum((getattr(s, "esi_employer", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    company = locked.company
    if company.accounting_enabled and total_gross > 0:
        from accounting.services import PostingService

        # R4-011: _ensure_chart only seeds when an account is actually missing —
        # no ~50 get_or_create round-trips on every pay-run completion.
        PostingService._ensure_chart(company)
        expense = PostingService._account(company, "5800")
        credit_acct = PostingService._account(company, "1100" if pay_from_cash else "2150")
        # BB-000703: employer PF/ESI — Dr expense / Cr same statutory payables.
        total_expense = total_gross + total_pf_er + total_esi_er
        lines = [{"account": expense, "debit": total_expense}]
        for code, amount in (
            ("2261", total_pf + total_pf_er),
            ("2262", total_esi + total_esi_er),
            ("2263", total_pt),
            ("2265", total_tds),
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


@transaction.atomic
def cancel_pay_run(pay_run: PayRun, user) -> PayRun:
    locked = PayRun.objects.select_for_update().get(pk=pay_run.pk)
    if locked.status != PayRun.Status.COMPLETED:
        raise BusinessRuleError("Only completed pay runs can be cancelled.")
    from reporting.gst_periods import assert_period_allows_money_amend

    assert_period_allows_money_amend(
        locked.company, pay_period_month_end(locked.period), allow_soft_closed=True
    )
    if locked.company.accounting_enabled:
        from accounting.models import JournalEntry
        from accounting.services import PostingService

        entry = (
            JournalEntry.objects.filter(
                company=locked.company,
                source_type="PayRun",
                source_id=locked.pk,
                purpose="PAYROLL",
                status=JournalEntry.Status.POSTED,
            )
            .select_for_update()
            .first()
        )
        if entry:
            # R2-004: reversal posts on the cancellation date, not the pay period.
            PostingService.reverse(entry, user=user)
    # Cancel returns the run to DRAFT so its period can be re-run
    # (test_cancel_pay_run_reverses_journal_and_reopens_draft). R4-009 keeps the
    # finalised slips (net > 0) for anyone who left mid-period rather than
    # deleting their wages on the re-complete.
    locked.status = PayRun.Status.DRAFT
    locked.updated_by = user
    locked.save(update_fields=["status", "updated_by", "updated_at"])
    return locked

