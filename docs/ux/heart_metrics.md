# HEART metrics, task KPIs and cognitive-load targets

Status 2026-09-30. **No baselines exist yet** except where noted; targets below are proposals to be ratified after baselines are captured (action items A5-1, A5-2). Do not quote them as achieved.

## Instrumentation reality check

| Source | What exists | What it can answer |
|---|---|---|
| Frontend | Help events (`web/src/pages/help/events.ts`) and, since 2026-10-01, shop-floor task events (`web/src/lib/telemetry.ts`): `form_abandoned`, `draft_restored`, `document_voided`, `form_validation_failed`, plus the journey and first-use events | Help effectiveness, abandonment, draft restore, void rate and validation errors per form. No hesitation or back-navigation events yet |
| Backend | Documents with timestamps and `core.AuditEvent`; company and user creation times | Adoption, engagement and retention **derived from data** (first invoice time, invoices per week, active companies) without new code |
| e2e | `pos-keyboard-checkout.spec.ts` asserts a keyboard checkout budget in mock mode | Regression guard for POS, not a real-user measure |

## HEART

| Dimension | Goal | Signal | Metric | Source | Baseline | Proposed target |
|---|---|---|---|---|---|---|
| Happiness | Users feel in control | 1-question CSAT after invoice save and setup; SUS-lite in sessions; UX support tickets | CSAT, tickets per 100 active companies | New in-app prompt; support tool | none | Set after baseline; direction: tickets down |
| Engagement | Core loops used | Documents per active user per week; share of bills created by keyboard or Quick entry; use of Receipts and Collections | Invoices, receipts, reminders per active company per week | Backend derive | none | Set after baseline |
| Adoption | New users reach value | Setup completion; time from company creation to first completed invoice; first use of receipts, collections, reports | Setup completion %, median time to first invoice | Backend derive (company created to first invoice) | none | Median under 15 min to first invoice (proposal) |
| Retention | Users return | Active companies week 4, month 3 | W4 and M3 retention | Backend derive | none | Set after baseline |
| Task success | Fewer errors, faster tasks | Validation errors per form submit; abandonment; draft restore rate; undo or void rate; time on task | See task table | New client events in the form pattern | POS keyboard only, in mock mode | Reduce time and errors versus baseline by 20% on the redesigned forms (proposal) |

## Task KPIs (capture baseline first, real backend)

| # | Task | Measure | Journey | Automated today |
|---|---|---|---|---|
| T1 | Setup to first invoice | minutes, clicks | J2 | no |
| T2 | POS sale (cash, single scanned item) | seconds, keystrokes | J3 | yes (mock) |
| T3 | POS sale with customer on credit | seconds, blockers hit | J3 | no |
| T4 | B2B invoice, 3 lines, GST | seconds, clicks, fields touched | J4 | no |
| T5 | Record and allocate a receipt | seconds, clicks | J5 | no |
| T6 | Send a payment reminder | clicks | J5 | no |
| T7 | Purchase bill, manual, 3 lines | seconds, clicks | J6 | no |
| T8 | Create an item (default case) | fields, seconds | J7 | no |
| T9 | Credit note against an invoice | clicks | J8 | no |
| T10 | Month close checklist to GSTR-1 export | steps | J9 | no |

## Quality KPIs

| KPI | Current (2026-09-30, mock mode, Chrome) | Target |
|---|---|---|
| Pages with serious or critical axe findings | Before: 6 of 141 (desktop), 9 of 141 (393px). After the 2026-09-30 fixes: 0 of the 82 routes that rendered; 59 flag-gated routes were not audited yet (`UX_FEATURE_PHASES.md`) | 0 (kept by `e2e/a11y.spec.ts` for 11 routes; crawl re-run for the rest) |
| Pages without an h1 | 68 of 141 | 0 |
| Avg interactive targets under 44px at 393px | 10.3 per page (max 31) | under 3 on editors and POS |
| Pages with horizontal overflow at 393px | 0 of 141 | stay 0 |
| Hard-coded English strings (static scan) | about 190 in listed screens | near 0 |
| Render time mock mode | avg 1.4s, max 2.2s | Re-measure with real data; LCP under 2.5s, INP under 200ms |
| Console errors on page load | 137 of 141 routes (mock 500) | 0 after mock fix |

## Cognitive-load targets

| Measure | How | Target (proposal) |
|---|---|---|
| Controls on the New invoice page | Static scan and crawl | Under 60 visible at first paint (currently 120 in code, 23 inputs visible) |
| NASA-TLX-lite (3 questions, 0 to 100) after T2, T4, T5, T8 | Sessions | 30 or lower |
| Hesitation (idle over 5s before first action) and back-navigation | New client events | Down 25% from baseline |
| Fields required to save the default item | Manual | 6 or fewer |

## Review cadence

Weekly during Waves 1 to 7; a regression of over 10% on any quality KPI triggers a rollback discussion. Ops view lives in Django admin, not the customer app.
