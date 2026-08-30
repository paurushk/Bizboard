# Charter template (H–L and any enablement)

Copy to `WAVE_H_COMPOSITION.md`, `WAVE_J_PAYROLL.md`, `L-05.md`, etc.

```markdown
# Charter: <WAVE or L-id>

- **PM:** name
- **Date signed:** YYYY-MM-DD
- **Eng:** name
- **CA (if money/GST/payroll):** name or n/a

## Named companies
| company_id | legal name | GSTIN | plan slug |
|---|---|---|---|
| | | | |

## Written demand
Link or paste: paying-customer request (email/ticket). Also log a row in
`docs/roadmap/charters/demand-log.md`. Wave L requires **≥3** paying requests
for that id unless PM writes a one-line exception here.

## Pricing tier
Which `billing.Plan.slug` unlocks this? (must exist in E-00 / Plan.modules)

## In scope
-

## Explicitly out of scope
-

## Success metric
-

## Exit criteria
- [ ] Matches ticket DoD in WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md
- [ ] Demo seed still has this flag **off**
- [ ] Honesty copy reviewed (no fake live portal / sync / filing)

## Honesty constraints
- Branch: FK to CompanyGstin only; no Branch.gstin string; stock stays warehouse-grained
- PAN/UDYAM: never VALID in prod from sandbox
- Payroll/MES/CRM: only named company ids
```
