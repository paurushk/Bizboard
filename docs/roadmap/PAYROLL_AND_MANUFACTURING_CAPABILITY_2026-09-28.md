# Payroll and manufacturing — what the code actually does

**Date:** 2026-09-28
**Audience:** pricing and go-to-market. This note does not decide whether to market either module.
**Scope:** backend only. Both stay dark-gated (`ENABLE_PAYROLL`, `ENABLE_MANUFACTURING` in
`core/services/feature_flags.py` `DARK_MODULE_KEYS`). A company reaches them only with an
explicit grant, and the API still checks that grant.

The executive-summary line that called both "Not implemented" was wrong. So was treating
"don't chase payroll" or "don't chase manufacturing" as settled. They are preview modules
with an honest ceiling, not empty directories.

## Payroll

Module docstring (`backend/payroll/models.py`): "Payroll preview — employees, pay runs,
simplified PF/ESI/PT; not full statutory HRMS."

**In the code**

- Employees, one pay run per company per `YYYY-MM`, one payslip per employee per run.
- PF on basic + DA when those are set, otherwise on gross. Employee PF, employer PF split
  into EPS and EPF, EPFO admin, and EDLI. Wage ceiling field defaults to ₹15,000.
- ESI employee and employer.
- Professional tax from state slabs, including a February top-up where the slab defines one.
  A state with no PT, or a blank state, charges ₹0. It does not fall back to a flat ₹200.
- Loss-of-pay: `paid_days` / `period_days` prorates gross and the statutory amounts on it.
- TDS: new-regime projection from salary (standard deduction, slabs, 87A rebate, cess) in
  `payroll/services.py` `annual_new_regime_tax`. A non-zero `employee.tds_rate` overrides it.
  Old regime with no override computes ₹0.
- Completing a pay run posts the payroll journal when accounting is on, including employer
  PF, admin, EDLI, and employer ESI (BB-000703).
- Owner-only API. An employee with payslips cannot be deleted; they are set inactive.

**Explicitly out of scope in the code's own comments**

- HRA and Chapter VI-A declarations are not collected (`payroll/models.py` employee comment,
  `payroll/services.py` around the new-regime note). The new-regime figure is a salary-only
  estimate. The code says to verify it with a CA.
- No Form 16, no PF/ESI challan, no ECR e-filing.
- No leave or attendance system beyond the paid-days fields on a payslip.
- No arrears, no reimbursements, no full HRMS.

## Manufacturing

Module docstring (`backend/manufacturing/models.py`): "Manufacturing MVP — BOM + work orders;
not a full MES."

**In the code**

- BOM with lines (component and quantity), statuses draft / active / archived.
- Work orders: draft, release (issues components from stock), complete (receives the finished
  good), cancel. Owner-only API behind the manufacturing flag.
- The work order points at a specific BOM, so a released order does not guess which BOM.

**Documented limitation, not a bug to "fix" in passing**

`Bom` allows more than one ACTIVE bill of materials for the same finished good. There is no
version or effective date. Anything that asks "the BOM for this product" has to choose.
The model comment says a uniqueness migration is the wrong next step; versioning needs a
design decision.

**Not in this module**

Routing, capacity, shop-floor scheduling, quality holds, subcontracting, or a manufacturing
execution system.

## What this note does not change

- Whether to put either module on a price page. Default remains: keep them gated until
  someone makes that call.
- `qos/backlog/QOS-0071.yaml` still says multi-branch GSTIN is not built and is a wontfix.
  That claim is now false (`CompanyGstin` CRUD and the settings screen exist). Do not flip
  that lifecycle until a founder rewrites the rationale or reopens the item. The generated
  backlog was not regenerated for it.
