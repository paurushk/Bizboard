# Bizboard UX Master Execution Plan

**Date:** 2026-09-30
**Goal:** Take Bizboard from "many UX plans" to one audited, deduplicated, prioritised, shipped and measured UX programme, with nothing left uncovered.
**Hard constraint:** No change to core business logic (money, stock, GST/TCS, ledger, permissions, API contracts). Anything that touches business logic is tagged `NEEDS-FOUNDER-DECISION` and is not built without a decision.
**Existing inputs (do not redo, reconcile):** `UX_IMPLEMENTATION_PLAN.md`, `UX_AUDIT_IMPLEMENTATION_PLAN.md`, `DETAILED_UX_IMPLEMENTATION_PLAN.md`, `UX_COGNITIVE_WALKTHROUGH_IMPLEMENTATION_PLAN.md`, `docs/USER_JOURNEY_MAP_AND_IMPLEMENTATION_PLAN.md`, `UI_UX_FINDINGS.md`, `ACCESSIBILITY_FINDINGS.md`, `FRONTEND_REVIEW.md`, `docs/PRODUCT_QUALITY_BACKLOG.md`, `docs/TESTING_STRATEGY.md`, `web/e2e/ux-audit-now.spec.ts`.
**Rule from CLAUDE.md:** never read generated files wholesale (`openapi-snapshot.json`, `openapi-types.ts`, `MASTER_ISSUE_REGISTER.md`, lockfiles). Grep them.

---

## Progress log

| Date | Step | Result |
|---|---|---|
| 2026-09-30 | 0.3 Surface ledger | Done. `scripts/ux_surface_diff.py` writes `docs/ux/L1_surface_ledger.csv`: 190 surfaces (159 routed pages, 21 redirects, 10 dialogs), 0 unrouted pages. `--check` exits non-zero on drift. All rows `Pending` audit. Not yet in CI. |
| 2026-09-30 | 0.2 / 0.4 Finding ledger | Done for the 6 existing UX docs. `docs/ux/L2_finding_ledger.csv`: 42 rows. About 24 items are Implemented-uncommitted (code and tests exist in the working tree, not yet browser-verified), 5 Not-evidenced (N7, X6, X7, L5, CW-05), 1 Partial (L7), 1 Founder-decision (X8), 8 Deferred or Won't-fix, 3 contradicted or unverified claims from older docs. The later docs (`DETAILED_UX_IMPLEMENTATION_PLAN.md`, `docs/USER_JOURNEY_MAP_AND_IMPLEMENTATION_PLAN.md`, `UX_IMPLEMENTATION_PLAN.md` beyond its backlog table) still need line-by-line ingestion. |
| 2026-09-30 | 0.5 Personas / JTBD | Done: `docs/ux/personas_jtbd.md`. |
| 2026-09-30 | 0.6 Baseline health | Vitest on the touched areas: 65 files, 318 tests, all pass. `tsc -b` found 4 errors in the uncommitted work (unused `Box`; `Product.expiryDate` does not exist; `registrationType` null typing). Fixed all four. The POS expiry chip never rendered because the API sends no expiry on Product, so the dead chip was removed and UX-025 is now Partial. Re-run of `tsc -b` after the fix is still pending (shell tool was failing). |
| 2026-09-30 | Phase 1 evidence | Done for automated measures. Crawl of 141 pages on desktop and 393px (axe WCAG 2.2 AA, touch targets, h1, overflow, render time) in mock mode with installed Chrome; static cognitive-load scan of 154 components; manual walk of Dashboard, New invoice (English and Hindi at 375px), Receipts, Collections, Attention, POS; existing POS e2e specs. Not done: user sessions, Lighthouse/INP, dark mode, real-data timings, walks of reconciliation, period close, GST returns, imports. |
| 2026-09-30 | Phase 2 synthesis | Done. `docs/ux/L2_finding_ledger.csv`: 66 rows (24 new findings UX-N01..N24). Founder decisions: `docs/ux/founder_decisions.md`. Not yet promoted to `qos/backlog/`. |
| 2026-09-30 | Phase 3 patterns | Documented in `docs/ux/patterns.md`. Components to build are listed there; none built yet except theme-level fixes. |
| 2026-09-30 | Phase 4 Wave 1 | Started and largely done for Critical accessibility: labels, contrast, focus, scroll regions, plain-language errors, Collections copy, party-aware Complete hint. Serious axe findings 6 to 0 (desktop) and 9 to 0 (mobile). Full Vitest 138 files / 620 tests pass; `tsc -b` clean. `npm run lint` is red at HEAD (37 errors) plus about 9 from uncommitted work (UX-N21). Waves 2 to 7 not started. |
| 2026-09-30 | Phases 5 and 6 | Metrics plan written (`docs/ux/heart_metrics.md`) with no baselines. Report: `docs/UX_AUDIT_2026-09-30.md`. Action items: `docs/UX_ACTION_ITEMS.md`. Ledgers not closed: L2 has open items by design; L3 has no baselines. |
| 2026-09-30 | 0.1 Working tree | Not changed. About 68 uncommitted paths remain. Waiting on the commit-or-shelve decision. |

## How "nothing left" is guaranteed

Completeness is enforced by three ledgers created in Phase 0 and closed in Phase 6. The programme is not done until every row in each ledger has a terminal status.

| Ledger | Rows | Terminal statuses |
|---|---|---|
| **L1 Surface ledger** | every route/page (from `web/src/App` routes plus `menu.ts`), every dialog and drawer, every public page, mobile shell screens, email/PDF/print outputs | Audited → Fixed / Deferred (with reason) / Hidden-by-design |
| **L2 Finding ledger** | every UX finding, deduplicated across all existing docs and the new audit | Shipped / Deferred / Won't-fix / Founder-decision |
| **L3 Metric ledger** | every HEART metric and task KPI | Instrumented + baseline captured + target tracked |

A coverage script (Phase 0, step 0.3) diffs L1 against the real route table so no page can be missed silently. It reuses the `qos/` tooling and CI gate (`qos-lint`).

---

## Phase 0: Foundation and inventory (3 days)

| # | Task | Output | Done when |
|---|---|---|---|
| 0.1 | Freeze a baseline: tag current `main`, record the uncommitted UX work-in-progress (git status shows about 40 modified files plus new `deviceDraft`, `smartDateParser`, POS hotkeys) and decide commit vs. shelve | Clean branch `ux/programme` | Working tree reconciled |
| 0.2 | Read all input docs above. Extract every finding, task and claim into a single sheet with columns: source doc, ID, screen, issue, status claimed | `docs/ux/L2_finding_ledger.csv` | All 9+ docs ingested |
| 0.3 | Build the route inventory automatically: parse the router and `menu.ts`, list every page under `web/src/pages/**` (about 25 areas: sales, purchases, inventory, accounting, reports, settings, payments, crm, manufacturing, payroll, workshop, insights, help, public, offline, setup, pos, plus auth pages) | `docs/ux/L1_surface_ledger.csv` + script `scripts/ux_surface_diff.py` | Script exits non-zero if a route is missing from the ledger |
| 0.4 | Verify claims: for each "already fixed" claim in older plans, grep the code or run the flow. Old plans are hypotheses until verified (the journey doc itself says "Journey Hypothesis") | Status column corrected | No unverified "done" rows |
| 0.5 | Define personas and JTBD from `docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md` and `USER_ROLE_COVERAGE.md`. Map each persona to permissions in `menu.ts` and the feature flags (POS, GST, workshop, manufacturing, and so on) | `docs/ux/personas_jtbd.md` | Every persona has 5-8 jobs |
| 0.6 | Set up the audit harness: seeded test company, personas as logins, Playwright helpers in `web/e2e/helpers`, axe config from `a11y.spec.ts` | Reproducible env (see memory: Redis needed even for SQLite dev) | One command runs all flows |

**Exit gate:** L1 and L2 exist, the surface diff script passes, and personas are signed off.

---

## Phase 1: Evidence gathering (5 days)

Goal: replace hypotheses with observations. Run in parallel where possible.

1. **Task analysis (measured).** For each core task, script it in Playwright and record clicks, keystrokes, form fields, screens and seconds for the current UI:
   - First-time setup to first invoice
   - POS sale (cash, UPI, split, credit customer)
   - B2B invoice from quotation and sales order
   - Receipt entry and allocation
   - Collections follow-up
   - Purchase bill (manual and upload) and GRN
   - Stock transfer, count and adjustment
   - Credit and debit notes
   - Period close, GST return, CA handoff
   - Bank reconciliation
   - Data import (Tally migration, CSV)
   Output: `docs/ux/task_baselines.csv`.
2. **Automated heuristics scans.**
   - axe-core on every L1 surface in light and dark, desktop and 375px mobile.
   - Keyboard-only pass: tab order, focus trap, focus return, shortcuts (POS hotkeys).
   - Lighthouse: LCP, INP, CLS on the top 10 screens, plus a throttled 3G and low-end Android run for the Capacitor shell.
   - Contrast and touch-target audit (44px minimum).
   - i18n audit: every string in `en.ts` has an `hi.ts` counterpart, and check overflow with Hindi text.
3. **Expert walkthroughs (manual, browser tools).** For each of the 10 journeys below, walk it as each relevant persona and apply the four cognitive-walkthrough questions at every step. Screenshot each step.
4. **Heuristic evaluation.** Score each L1 surface 0-4 against Nielsen's 10. Record evidence as `file:line` or screenshot.
5. **Analytics reality check.** Find what is already instrumented (`web/src/pages/help/analytics.ts`, `events.ts`, backend `insights`). List the gaps for HEART.
6. **Real-user input (parallel, optional but strongly recommended).** 5 to 8 moderated sessions of 30 minutes with real shop owners, billing staff and accountants on the top 5 tasks, plus a 5-question in-app survey (SUS-lite). Findings from code and walkthroughs stay labelled "expert-judged" until validated here.

**Journeys (each gets a journey map, task analysis and cognitive walkthrough):**

| ID | Journey | Primary persona |
|---|---|---|
| J1 | Sign-up, invite, login, OTP, password recovery | All |
| J2 | Setup wizard, GST and company settings, pack wizard, import or migration | Owner |
| J3 | POS counter loop | Cashier |
| J4 | B2B order-to-cash (quotation, order, challan, invoice, receipt) | Sales staff |
| J5 | Collections and dunning, customer 360 | Owner, accounts |
| J6 | Procurement (PO, bill, upload, GRN, supplier payment) | Purchase staff |
| J7 | Inventory (products, stock, transfer, count, low stock, expiry, labels) | Store keeper |
| J8 | Returns and notes (credit and debit, purchase returns) | Sales and purchase |
| J9 | Accounting and period close (expenses, journals, bank recon, periods, GST returns, CA handoff) | Accountant |
| J10 | Insight and daily control (dashboard, attention, reports, insights, help, offline outbox, notifications) | Owner |

**Exit gate:** every L1 surface has heuristic scores, an axe result, a perf number, and every journey has a map.

---

### Phase 1 addendum: cognitive load and supporting frameworks

These run inside Phase 1 on every L1 surface and journey, and their outputs feed Phase 2 scoring.

| Framework | What we do | Output / metric |
|---|---|---|
| **Cognitive load (Sweller: intrinsic, extraneous, germane)** | Per screen, count decisions, visible fields, controls, distinct concepts and terms. Flag extraneous load: jargon, duplicate controls, irrelevant fields, unexplained defaults. Reduce with progressive disclosure, smart defaults and chunking | Load score 1-5 per surface in L1; extraneous-load findings tagged `COG` |
| **Hick's law** | Count choices at each decision point (menus, action bars, dropdowns). Over 7 undifferentiated options gets grouped, ranked or searchable | Choice-count column in L1 |
| **Miller's 7±2 / chunking** | Long forms (invoice, item, setup wizard, GST settings) split into logical groups or steps; long numbers and IDs grouped | Form-length audit |
| **Fitts's law and thumb zone** | Primary actions large, close and reachable on mobile and at the POS counter; small or distant targets flagged; minimum 44px | Touch-target and reach report |
| **Recognition over recall** | List what users must remember between screens (codes, rates, previous values). Replace with pickers, recents and inline context | `COG` findings |
| **Mental models and terminology** | Compare labels in the UI with owner language (Hindi and English shop terms vs. accounting terms), using `hi.ts`, help synonyms and user sessions | Terminology glossary and rename list |
| **Error taxonomy (slips vs. mistakes, Reason)** | Classify likely errors (wrong item, wrong qty, wrong party, wrong date) and match each to prevention (constraints, confirmation, undo) | Error-prevention matrix per journey |
| **Progressive disclosure and defaults** | Identify advanced fields shown to everyone (GST, batch, serial, cost centre) and gate them by pack, flag or "more options" | Disclosure map |
| **Kano model** | Classify candidate improvements as must-have, performance or delighter, so the backlog is not only fixes | Kano tag on each L2 row |
| **Emotional journey and service blueprint** | Mark anxiety points (money entry, GST filing, period close) and the backstage support each needs (help, alerts, undo) | Emotion curve per journey |
| **Measured cognitive load** | NASA-TLX-lite (3 questions) after top tasks in user sessions; time-on-task, hesitation (long idle before action), back-and-forth navigation and undo counts from telemetry | Load metrics in L3 |
| **Perceived performance** | Skeletons, optimistic updates, progress messaging; measure vs. actual timing | Perf-perception findings |
| **Accessibility as load** | Screen reader, low vision, motor, low literacy and low bandwidth users treated as first-class cases | A11Y findings |

Add to the deliverables: `docs/ux/cognitive_load_audit.md` (per-surface scores and the top 20 extraneous-load reductions). Add to Phase 5: a Cognitive Load row (NASA-TLX-lite ≤ 30/100 on top tasks, hesitation and back-navigation rates down 25%). Add to the Phase 2 scoring: a `COG` flag and a Kano tag.

---

## Phase 2: Synthesis and prioritisation (3 days)

1. **Deduplicate** into L2. One finding, one ID (`UX-###`), with links to every source doc, evidence, heuristic violated, root cause, and the fix.
2. **Root-cause grouping.** Cluster findings into systemic causes so fixes land once in shared components instead of per page. Expected clusters: form validation and error pattern, unsaved-changes guard, table and list pattern (filters, empty, loading, bulk), status chips and colour semantics, date/number/currency input, dialogs and drawers, navigation and information architecture, keyboard shortcuts, offline and sync feedback, i18n, help and empty-state links.
3. **Score every finding:**
   - Severity: Critical (blocks task or risks wrong data), High (task slowed or error-prone), Medium (friction), Low (polish).
   - Customer impact: reach (share of users) × frequency × severity, scored 1-5.
   - Complexity: S (under 1 day), M (1-3 days), L (over 3 days), XL (needs design or backend).
   - Priority = impact ÷ complexity, with Critical always first.
   - Flags: `BIZ-LOGIC` (founder decision), `BACKEND`, `DESIGN-NEEDED`, `A11Y`, `MOBILE`, `I18N`.
4. **Founder-decision list.** Collect every `BIZ-LOGIC` item, each with a recommendation, for one review meeting. Anything undecided is Deferred, never silently built.
5. **Design-system gaps.** List the missing or inconsistent patterns and define the target pattern for each (see Phase 3).

**Exit gate:** L2 fully scored, decisions list ready, backlog exported to `qos/backlog/ux.yaml` in the qos schema and passes `qos-lint`.

---

## Phase 3: Design system and patterns first (1.5 weeks)

Fix root causes once before touching individual screens. Each pattern gets a component, a doc entry, unit tests and an axe test.

| Pattern | Standard to set |
|---|---|
| Form pattern | inline validation on blur, error summary, required and optional marking, helper text, smart defaults, Enter and Tab behaviour |
| Unsaved-changes and draft | one guard (extend `UnsavedChangesGuard`, `deviceDraft`), consistent copy |
| Data tables and lists | search, filters, saved views, sort, sticky header, bulk actions, empty, loading (skeleton) and error states, row actions, mobile card layout |
| Feedback | toast vs. inline vs. dialog rules, undo instead of confirm where safe, destructive-action confirmation with consequences stated |
| Status system | one status-to-colour-to-label-to-icon map (`utils/status.ts`), never colour alone |
| Numeric, date and money inputs | `smartDateParser`, Indian number grouping, paste handling, keyboard steppers |
| Navigation and IA | menu grouping, naming in owner language, pack-based progressive disclosure, breadcrumbs, global search and command palette |
| Keyboard | shortcut map, discoverable via `?`, no conflicts with browser |
| Offline and sync | one visible state indicator, outbox clarity |
| Copy and i18n | plain-language style guide, error message formula (what happened, why, what to do), en and hi parity check in CI |
| Accessibility baseline | focus ring, contrast tokens in `theme/index.ts`, touch targets, reduced motion, screen-reader labels, live regions |
| Mobile | breakpoints, bottom action bars, thumb-zone actions, responsive tables |

**Exit gate:** pattern doc merged, components in place, and at least one reference screen migrated per pattern.

---

## Phase 4: Implementation in waves (about 8 weeks)

Order: Critical first, then by journey value. Each wave ships behind a feature flag where it changes behaviour, and each finding closes only with its tests.

| Wave | Scope | Findings included |
|---|---|---|
| **W1: Stop the bleeding (wk 1-2)** | All Critical findings, data-loss and wrong-entry risks, blocking a11y (keyboard traps, unlabeled controls), auth and recovery | Critical + a11y blockers |
| **W2: Money-making loops (wk 2-4)** | J3 POS, J4 sales and invoicing, J5 collections and receipts | High in J3-J5 |
| **W3: Onboarding and activation (wk 4-5)** | J1 and J2: sign-up, setup wizard, import, first-invoice guidance, empty states | High in J1-J2 |
| **W4: Back-office (wk 5-7)** | J6 purchases, J7 inventory, J8 returns and notes | High and Medium in J6-J8 |
| **W5: Control and compliance (wk 7-8)** | J9 accounting, period close, reports and GST, J10 dashboard, attention, insights, help | High and Medium in J9-J10 |
| **W6: Polish and long tail (wk 8-9)** | Remaining Medium and Low, dark mode, mobile shell, print and PDF, email templates, microcopy | Medium, Low |
| **W7: Cross-cutting hardening (wk 9)** | Performance perception, i18n full pass, regression sweep | Leftovers |

**Per-finding definition of done:**
1. Change implemented with no diff to backend business logic (guard: backend diffs limited to serializers and presentation fields, reviewed).
2. Vitest test for behaviour, and Playwright test for the journey step when applicable.
3. axe clean, keyboard path verified, 375px checked, en and hi strings both present.
4. Task baseline re-measured (clicks, time), improvement recorded.
5. L2 status updated, `FREEZE_SCOPE_COVERAGE.md` updated if the item is in scope.
6. Existing suites and `qos-lint` green (concurrency tests are Postgres-only, per memory).

**Mobile and Capacitor** is covered as its own track inside every wave. It is not a footnote. It gets the `mobile/e2e` run and a low-end Android check per wave.

---

## Phase 5: Measurement (starts in Wave 1, runs continuously)

### HEART framework

| Dimension | Goal | Signal | Metric | Instrumented? |
|---|---|---|---|---|
| **Happiness** | Users feel in control | Survey, support tickets | SUS-lite ≥ 75; UX-related tickets per 100 active users down 30% | Add in-app 1-question CSAT after invoice save and setup |
| **Engagement** | Daily use of core loops | Sessions and core actions | Invoices or POS sales per active user per week; % using keyboard or quick entry | Verify existing events, add gaps |
| **Adoption** | New users reach value fast | Onboarding funnel | Setup completion %; time to first invoice (target under 15 min); feature discovery (first use of receipts, collections, reports) | Add funnel events |
| **Retention** | Users return | Active companies | D7, D30, W4 retention; churn reasons | Backend aggregates |
| **Task success** | Fewer errors, faster tasks | Task timing and error events | POS sale time, invoice creation time, validation error rate per form, draft-recovery rate, undo usage, abandonment on forms, rage-click and dead-click count | Add telemetry wrapper in form pattern |

### Operational KPIs
- Task baselines from Phase 1 vs. after each wave (clicks, seconds).
- axe violations count per surface (target zero serious or critical).
- Lighthouse and web vitals budgets: LCP under 2.5s, INP under 200ms, CLS under 0.1 on top screens.
- Support and help volume: "how do I" queries, help-search no-result rate.
- Error rate: API 4xx surfaced to users, unhandled UI errors.

**Rules:** capture baseline before each wave ships. Review a metric dashboard weekly. Any regression of over 10% triggers a rollback discussion. Use the Django admin for the ops view (memory: staff tooling never goes into the customer SPA).

---

## Phase 6: Closure and governance (3 days)

1. Close the ledgers: run the surface diff (L1 all terminal), L2 (all terminal), L3 (all baselined).
2. Publish `docs/UX_FINAL_REPORT.md`: executive audit, journey-wise findings, screen-by-screen improvements, the prioritised backlog with what shipped, and a metric table showing before vs. after.
3. Add regression protection: keep the axe and mobile-layout e2e specs in CI, add the en and hi parity test, and add the surface diff to CI.
4. Ownership: assign a UX owner, and add a "UX checklist" to the PR template (states, keyboard, mobile, a11y, copy, i18n).
5. Update memory and docs indexes, and archive superseded UX plan files to `docs/archive` so a single source of truth remains.

---

## Deliverables checklist (the final outputs you asked for)

| Deliverable | File | Produced in |
|---|---|---|
| Executive UX audit | `docs/UX_FINAL_REPORT.md` §1 | Phase 2 and 6 |
| Journey-wise findings (J1-J10) | `docs/ux/journeys/J*.md` | Phase 1 |
| Screen-by-screen improvements | `docs/ux/screens/<area>.md` | Phase 1 and 2 |
| Prioritised UX backlog | `docs/ux/L2_finding_ledger.csv` + `qos/backlog/ux.yaml` | Phase 2 |
| Design-system pattern guide | `docs/ux/patterns.md` | Phase 3 |
| Metrics plan and dashboard | `docs/ux/heart_metrics.md` | Phase 5 |
| Founder-decision list | `docs/ux/founder_decisions.md` | Phase 2 |

---

## Timeline summary

| Phase | Duration | Cumulative |
|---|---|---|
| 0 Foundation | 3 days | wk 1 |
| 1 Evidence | 5 days | wk 2 |
| 2 Synthesis | 3 days | wk 3 |
| 3 Patterns | 1.5 weeks | wk 4 |
| 4 Implementation (W1 can start after Phase 2 for Criticals) | about 8 weeks | wk 11 to 12 |
| 5 Measurement | continuous from W1 | n/a |
| 6 Closure | 3 days | wk 12 |

Estimate assumes one full-time developer plus Claude Code agents for audit and implementation. It shortens if Phases 1 and 3 run in parallel with W1 Critical fixes.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Old plans contain unverified claims | Phase 0.4 verifies before trusting |
| Uncommitted work conflicts | Phase 0.1 reconciles first |
| UX change accidentally alters business behaviour | Backend diff guard, founder-decision tag, existing test suites, Postgres concurrency tests before release |
| Scope creep from 25+ page areas | The surface ledger has a Deferred status with a reason, and Wave 6 handles the long tail |
| Hidden or dead surfaces (`ALWAYS_HIDDEN_NAV`: bills-of-entry, telegram, fixed-assets, tickets, insurance, contracts) | Mark Hidden-by-design in L1, do not spend effort |
| Expert-only findings may miss real user pain | Phase 1 step 6 user sessions, and metrics after each wave |
| Regressions in the POS keyboard flow | Existing `pos-*` e2e specs must pass at every wave |

---

## First actions (next session)

1. Decide what to do with the current uncommitted UX changes (commit as a baseline or shelve).
2. Run Phase 0.2 and 0.3 (ledgers and surface script). This is the natural first Claude Code task.
3. Confirm whether user sessions (Phase 1.6) are possible, and who the 5 to 8 participants would be.
