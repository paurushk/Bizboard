# Post-launch adoption rollup (17.7)

Weekly operator template. **Do not treat this as** a board report, KPI
SLA, or customer-facing success metric. Fill from product facts only.

## Funnel (from `ShopFloorEvent`)

| Event | This week | Prior week | Notes |
|---|---|---|---|
| `signup_completed` | | | |
| `wizard_tax_confirmed` | | | GSTIN confirm in setup wizard |
| `wizard_completed` | | | Wizard dismissed |

Source: `GET` funnel rollup on insights telemetry (`tests/test_a08_telemetry.py`).

## Freeze usage (A1–A26)

| Surface | Completes this week | Blocked Completes | HelpCode top 3 |
|---|---|---|---|
| Sales invoice | | | |
| Purchase invoice | | | |
| Receipt / supplier payment | | | |
| POS (A23) | | | |

Table B modules stay dark. Do not count GSTR screens, manufacturing,
payroll, CRM, or Tally as adoption.

## SaaS vs AR

- Cancelled SaaS subscriptions still write until `current_period_end`
  (`docs/ops/REFUND_CANCELLATION.md`).
- Customer AR dunning is not SaaS dunning.

## Human follow-ups

CSAT comments (`docs/pilot/CSAT.md`) and tickets (`docs/ops/TICKET_TAXONOMY.md`)
are copied here as counts, not quotes of customer PII.
