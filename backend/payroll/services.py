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

# --- EPF / EPS / EDLI (EPFO) ---------------------------------------------------
# Employee: 12% of PF wages. Employer 12% splits into EPS 8.33% (of PF wages
# capped at the pension ceiling ₹15,000 → max ₹1,250) and EPF 3.67% (the
# residual). Establishment also pays admin (A/c 2) and EDLI (A/c 21).
PF_EMPLOYEE_RATE = Decimal("0.12")
PF_EMPLOYER_RATE = Decimal("0.12")
EPS_RATE = Decimal("0.0833")
EPS_WAGE_CEILING = Decimal("15000")
EPS_MAX = Decimal("1250")           # 8.33% of 15,000
PF_ADMIN_RATE = Decimal("0.005")    # A/c 2 — 0.50% of PF wages, min ₹500 / establishment / month
PF_ADMIN_MIN_ESTABLISHMENT = Decimal("500")
EDLI_RATE = Decimal("0.005")        # A/c 21 — 0.50% of EPS wages, capped at ₹75
EDLI_MAX = Decimal("75")

# --- ESI --------------------------------------------------------------------
ESI_EMPLOYEE_RATE = Decimal("0.0075")   # 0.75%
ESI_EMPLOYER_RATE = Decimal("0.0325")   # 3.25%
ESI_WAGE_CEILING = Decimal("21000")

# Backwards-compat alias (older callers / tests).
PF_RATE = PF_EMPLOYEE_RATE

# --- Professional Tax (state) --------------------------------------------------
# PR-02: full state coverage. States/UTs that levy NO professional tax map to an
# empty ladder (→ ₹0), so a Delhi/UP/Haryana employee is not charged the old
# ₹200 default. Multi-slab states carry their current monthly ladders. These DO
# change by state finance act — a company overrides via Company.payroll_pt_slabs;
# this is the fallback. `feb_amount` handles Maharashtra's February ₹300 top-up.
#
# VERIFY WITH YOUR CA / the state PT act before relying on these for filing.
_NO_PT_STATES = frozenset({
    "delhi", "nct of delhi", "haryana", "uttar pradesh", "uttarakhand",
    "rajasthan", "himachal pradesh", "jammu and kashmir", "jammu & kashmir",
    "ladakh", "arunachal pradesh", "goa", "andaman and nicobar islands",
    "chandigarh", "dadra and nagar haveli and daman and diu", "daman and diu",
    "dadra and nagar haveli", "lakshadweep", "nagaland", "chhattisgarh",
})

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
    "Karnataka": [
        {"min": "0", "max": "24999.99", "amount": "0"},
        {"min": "25000", "max": None, "amount": "200"},
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
    "Kerala": [  # Kerala PT is half-yearly; monthly-equivalent ladder.
        {"min": "0", "max": "1999.99", "amount": "0"},
        {"min": "2000", "max": "2999.99", "amount": "20"},
        {"min": "3000", "max": "4999.99", "amount": "30"},
        {"min": "5000", "max": "7499.99", "amount": "50"},
        {"min": "7500", "max": "9999.99", "amount": "75"},
        {"min": "10000", "max": "12499.99", "amount": "100"},
        {"min": "12500", "max": "16666.99", "amount": "125"},
        {"min": "16667", "max": "20833.99", "amount": "166"},
        {"min": "20834", "max": None, "amount": "208"},
    ],
    "Madhya Pradesh": [
        {"min": "0", "max": "18750", "amount": "0"},
        {"min": "18750.01", "max": "25000", "amount": "125"},
        {"min": "25000.01", "max": "33333", "amount": "167"},
        {"min": "33333.01", "max": None, "amount": "208", "feb_amount": "212"},
    ],
    "Bihar": [
        {"min": "0", "max": "25000", "amount": "0"},
        {"min": "25000.01", "max": "41666", "amount": "83.33"},
        {"min": "41666.01", "max": "83333", "amount": "166.67"},
        {"min": "83333.01", "max": None, "amount": "208.33"},
    ],
    "Assam": [
        {"min": "0", "max": "10000", "amount": "0"},
        {"min": "10000.01", "max": "15000", "amount": "150"},
        {"min": "15000.01", "max": "25000", "amount": "180"},
        {"min": "25000.01", "max": None, "amount": "208"},
    ],
    "Odisha": [
        {"min": "0", "max": "13304", "amount": "0"},
        {"min": "13304.01", "max": "25000", "amount": "125"},
        {"min": "25000.01", "max": None, "amount": "200", "feb_amount": "300"},
    ],
    "Jharkhand": [
        {"min": "0", "max": "25000", "amount": "0"},
        {"min": "25000.01", "max": "41666", "amount": "100"},
        {"min": "41666.01", "max": "66666", "amount": "150"},
        {"min": "66666.01", "max": "83333", "amount": "175"},
        {"min": "83333.01", "max": None, "amount": "208"},
    ],
    "Punjab": [
        {"min": "0", "max": "20833", "amount": "0"},
        {"min": "20833.01", "max": None, "amount": "200"},
    ],
    "Meghalaya": [
        {"min": "0", "max": "4166", "amount": "0"},
        {"min": "4166.01", "max": "6250", "amount": "16.50"},
        {"min": "6250.01", "max": "8333", "amount": "25"},
        {"min": "8333.01", "max": "12500", "amount": "41.50"},
        {"min": "12500.01", "max": "16666", "amount": "62.50"},
        {"min": "16666.01", "max": "20833", "amount": "83.33"},
        {"min": "20833.01", "max": "25000", "amount": "104.16"},
        {"min": "25000.01", "max": "29166", "amount": "125"},
        {"min": "29166.01", "max": "33333", "amount": "150"},
        {"min": "33333.01", "max": "37500", "amount": "175"},
        {"min": "37500.01", "max": "41666", "amount": "200"},
        {"min": "41666.01", "max": None, "amount": "208"},
    ],
    "Tripura": [
        {"min": "0", "max": "7500", "amount": "0"},
        {"min": "7500.01", "max": "15000", "amount": "150"},
        {"min": "15000.01", "max": None, "amount": "208"},
    ],
    "Manipur": [
        {"min": "0", "max": "4250", "amount": "0"},
        {"min": "4250.01", "max": "6250", "amount": "100"},
        {"min": "6250.01", "max": "8333", "amount": "167"},
        {"min": "8333.01", "max": "10416", "amount": "200"},
        {"min": "10416.01", "max": None, "amount": "208"},
    ],
    "Mizoram": [
        {"min": "0", "max": "5000", "amount": "0"},
        {"min": "5000.01", "max": "8000", "amount": "75"},
        {"min": "8000.01", "max": "10000", "amount": "120"},
        {"min": "10000.01", "max": "12000", "amount": "150"},
        {"min": "12000.01", "max": "15000", "amount": "180"},
        {"min": "15000.01", "max": None, "amount": "208"},
    ],
    "Sikkim": [
        {"min": "0", "max": "20000", "amount": "0"},
        {"min": "20000.01", "max": "30000", "amount": "125"},
        {"min": "30000.01", "max": "40000", "amount": "150"},
        {"min": "40000.01", "max": None, "amount": "200"},
    ],
    "Puducherry": [
        {"min": "0", "max": "16666", "amount": "0"},
        {"min": "16666.01", "max": "33333", "amount": "41.66"},
        {"min": "33333.01", "max": "50000", "amount": "83.33"},
        {"min": "50000.01", "max": "83333", "amount": "125"},
        {"min": "83333.01", "max": None, "amount": "166.66"},
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
    key = state_key.strip().lower()
    for name, slabs in _STATE_PT_SLABS.items():
        if key == name.lower():
            return list(slabs)
    # PR-02: a state that levies no professional tax (Delhi, Haryana, UP, …) or
    # an unknown/blank state → no PT. Do NOT fall back to a flat ₹200.
    return []


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


# --- Sec. 192 salary TDS (new tax regime, default from FY 2023-24) -----------
# Annual: standard deduction ₹75,000; slabs 0/0-4L, 5% 4-8L, 10% 8-12L,
# 15% 12-16L, 20% 16-20L, 25% 20-24L, 30% >24L; 87A rebate makes tax nil when
# total income ≤ ₹12,00,000 (rebate capped at ₹60,000); 4% health & education
# cess on top. This is a projection from salary alone — it does NOT know other
# income, HRA, or Chapter VI-A declarations, so treat it as an estimate and let
# `employee.tds_rate` (a flat % override) win when the payroll admin sets one.
# VERIFY WITH YOUR CA before relying on it.
NEW_REGIME_STD_DEDUCTION = Decimal("75000")
NEW_REGIME_87A_INCOME_CAP = Decimal("1200000")
NEW_REGIME_87A_MAX = Decimal("60000")
NEW_REGIME_CESS = Decimal("0.04")
_NEW_REGIME_SLABS = [
    (Decimal("400000"), Decimal("0.00")),
    (Decimal("800000"), Decimal("0.05")),
    (Decimal("1200000"), Decimal("0.10")),
    (Decimal("1600000"), Decimal("0.15")),
    (Decimal("2000000"), Decimal("0.20")),
    (Decimal("2400000"), Decimal("0.25")),
    (None, Decimal("0.30")),
]


def annual_new_regime_tax(annual_income: Decimal) -> Decimal:
    """Income tax + cess under the new regime for a projected annual income."""
    taxable = max(Decimal("0"), _money(annual_income) - NEW_REGIME_STD_DEDUCTION)
    tax = Decimal("0")
    lower = Decimal("0")
    for upper, rate in _NEW_REGIME_SLABS:
        band_top = taxable if upper is None else min(taxable, upper)
        if band_top > lower:
            tax += (band_top - lower) * rate
        lower = upper if upper is not None else lower
        if upper is not None and taxable <= upper:
            break
    # 87A rebate — nil tax up to the income cap.
    if taxable <= NEW_REGIME_87A_INCOME_CAP:
        tax = max(Decimal("0"), tax - min(tax, NEW_REGIME_87A_MAX))
    tax = tax * (Decimal("1") + NEW_REGIME_CESS)
    return _money(tax)


def compute_statutory(employee, company, *, gross=None, month: int | None = None, paid_days=None, period_days=None) -> dict:
    gross_full = _money(gross if gross is not None else employee.salary)
    pf_employee = _money(0)
    pf_employer_eps = _money(0)
    pf_employer_epf = _money(0)
    pf_admin_charges = _money(0)
    edli_charges = _money(0)
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
        ceiling = _money(employee.pf_wage_ceiling or EPS_WAGE_CEILING)
        # PF wage base = Basic + DA when configured; else the (prorated) gross.
        basic_da = _money(getattr(employee, "basic", 0) or 0) + _money(getattr(employee, "da", 0) or 0)
        if basic_da > 0:
            basic_da = _money(basic_da * prorate)
        pf_wage = basic_da if basic_da > 0 else gross_amt
        wage_base = min(pf_wage, ceiling)
        eps_base = min(pf_wage, EPS_WAGE_CEILING)
        pf_employee = _money(wage_base * PF_EMPLOYEE_RATE)
        # PR-01: employer 12% = EPS 8.33% (capped) + EPF residual; plus admin + EDLI.
        pf_employer_eps = _money(min(eps_base * EPS_RATE, EPS_MAX))
        pf_employer_epf = _money(wage_base * PF_EMPLOYER_RATE) - pf_employer_eps
        if pf_employer_epf < 0:
            pf_employer_epf = _money(0)
        pf_admin_charges = _money(wage_base * PF_ADMIN_RATE)
        edli_charges = _money(min(eps_base * EDLI_RATE, EDLI_MAX))
    pf_employer = _money(pf_employer_eps + pf_employer_epf)
    if employee.esi_applicable:
        esi_ceiling = _money(getattr(company, "esi_wage_ceiling", None) or ESI_WAGE_CEILING)
        # Eligibility is on full-month wages, not LOP-prorated gross.
        if gross_full <= esi_ceiling:
            esi_employee = _money(gross_amt * ESI_EMPLOYEE_RATE)
            esi_employer = _money(gross_amt * ESI_EMPLOYER_RATE)
    pt_amount = _pt_amount(gross_amt, _resolve_pt_slabs(company, employee), month=month)

    # TDS: an explicit flat rate on the slip's gross always wins (payroll admin
    # override). Otherwise, for the new regime, project 12× the contracted gross
    # and take 1/12 of the annual liability. Old regime with no override → 0
    # (declarations are not collected yet).
    tds_rate = _money(getattr(employee, "tds_rate", 0) or 0)
    regime = (getattr(employee, "tax_regime", "NEW") or "NEW").upper()
    if tds_rate:
        tds_amount = _money(gross_amt * tds_rate / Decimal("100"))
    elif regime == "NEW":
        annual = _money(gross_full * Decimal("12"))
        tds_amount = _money(annual_new_regime_tax(annual) / Decimal("12"))
    else:
        tds_amount = _money(0)

    deductions = _money(pf_employee + esi_employee + pt_amount + tds_amount)
    net = _money(gross_amt - deductions)
    return {
        "gross": gross_amt,
        "pf_employee": pf_employee,
        "pf_employer": pf_employer,
        "pf_employer_eps": pf_employer_eps,
        "pf_employer_epf": pf_employer_epf,
        "pf_admin_charges": pf_admin_charges,
        "edli_charges": edli_charges,
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
        if paid_days is not None:
            # Always start from contracted salary so LOP proration in
            # compute_statutory is applied once (cancel→recomplete must not
            # feed an already-prorated slip.gross back in).
            gross = None
        elif gross is not None and gross == 0:
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
    total_pf_admin = sum(
        (getattr(s, "pf_admin_charges", Decimal("0")) or Decimal("0") for s in slips), Decimal("0")
    )
    total_edli = sum(
        (getattr(s, "edli_charges", Decimal("0")) or Decimal("0") for s in slips), Decimal("0")
    )
    total_esi_er = sum((getattr(s, "esi_employer", Decimal("0")) or Decimal("0") for s in slips), Decimal("0"))
    company = locked.company
    if company.accounting_enabled and total_gross > 0:
        from accounting.services import PostingService

        # R4-011: _ensure_chart only seeds when an account is actually missing —
        # no ~50 get_or_create round-trips on every pay-run completion.
        PostingService._ensure_chart(company)
        expense = PostingService._account(company, "5800")
        credit_acct = PostingService._account(company, "1100" if pay_from_cash else "2150")
        # BB-000703 / PR-01: employer PF (EPS+EPF) + admin + EDLI + ESI are
        # employer cost — Dr expense / Cr the statutory payables (2261 PF).
        total_expense = total_gross + total_pf_er + total_pf_admin + total_edli + total_esi_er
        lines = [{"account": expense, "debit": total_expense}]
        for code, amount in (
            ("2261", total_pf + total_pf_er + total_pf_admin + total_edli),
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
            source_type="PAY_RUN",
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
                source_type="PAY_RUN",
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

