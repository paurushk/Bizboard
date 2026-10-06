# Feature enablement and UX: one phase-wise plan (all modules)

Revised 2026-09-30. The four items that were waiting on a yes or no are decided and implemented. The ledger (`docs/ux/L1_surface_ledger.csv`, column `phase`) is the source of truth for which route belongs to which phase. That column is human-maintained: `scripts/ux_surface_diff.py` keeps it in `HUMAN_COLS` when the ledger is regenerated, and `scripts/ux_merge_crawl.py` writes it back on gated rows.

> **Numbering:** phases here are **UX-G0..G9**. They are not the Growth OS epics (GOS-G1..G5) or the rollout order (H0..H6). See [roadmap/GROWTH_OS_AND_FEATURES_UNIFIED_PLAN_2026-09-30.md](roadmap/GROWTH_OS_AND_FEATURES_UNIFIED_PLAN_2026-09-30.md), which places Growth OS and every other feature in one sequence.

**Goal:** every hidden module on in **dev only**, on UX Audit Traders. Production and the pilot profile stay frozen (`docs/FREEZE_SCOPE.md`). Integrations are screens that name the missing credential and do not claim a live connection.

## Decisions that were blocking G1

| # | Decision | Where it is enforced |
|---|---|---|
| 1 | Staging is out of scope for G1–G9 | `scripts/compose-env.ps1` refuses `BB_FULL_DEMO` and `BB_UX_G7` when the target is staging |
| 2 | One audit user per role on UX Audit Traders, plus UX Pack Control | `manage.py provision_ux_audit`. Passwords go only to `.ux-audit-credentials.local` (gitignored) |
| 3 | AI consent stays off. Provider keys are blanked for the G7 pass | `docker-compose.fulldemo.g7.yml` with `BB_UX_G7=1`. Insights pages render `AiConsentOffScreen` and do not call the provider |
| 4 | No sandbox credentials. G8 stops at the missing-credential message | Payment gateway, Telegram, billing, price lists, Account Aggregator, Tally copy. `--with-aa-consent` exists and is not used by provision |

## Correction to the earlier audit

The first crawl reported "0 serious axe findings on 141 routes". That was true only for the 82 pages that rendered. The other 59 had their module off in mock mode and showed the limited-access page, so they were never audited. They are marked `Gated-not-audited` in the ledger.

## What "enabled" means, by layer

| Layer | Mechanism | Default | Full-demo |
|---|---|---|---|
| Sidebar | `FLAG_GATED_NAV` in `web/src/navigation/menu.ts`; hidden unless the item's runtime flag is on. Replaced the hard-coded hidden lists | Off (production unchanged) | On when the flag is on |
| Deployment ceiling | `docker-compose.fulldemo.yml` (29 `ENABLE_*` variables, including `ENABLE_FIXED_ASSETS`, `ENABLE_BOE`, `ENABLE_ARCH05_STATUTORY_FORMS`) via `BB_FULL_DEMO=1` | Absent | Dev overlay only |
| Company grant | `manage.py enable_full_demo --email <user>` (refuses production; no AI consent, no credentials) | None | Once per audit company |
| New flag | `ENABLE_GSTR_EXTENDED`: GSTR-2B/4/6/7/8/9 nav only. **CMP-08 is owned by `ENABLE_GSTR`**, like GSTR-1 and 3B | Off | On |

## Routes by phase (re-bucketed from the ledger: 59 rows)

| Phase | Modules | Routes | Count |
|---|---|---|---|
| **G0 Enable** | Mechanism, real-backend login, flag check, snapshot and seed | | |
| **G1 Books and close** | Chart of accounts, journals, bank reconciliation, cost centres, periods, expenses; trial balance, P&L, balance sheet, books health | `/accounting/{accounts,journals,bank-reconciliation,cost-centers,periods,expenses}`, `/reports/{trial-balance,profit-and-loss,balance-sheet,books-health}` | 10 |
| **G2 GST and compliance** | GSTR-1, 3B, CMP-08, TDS/TCS, GST health, rate exposure, missing documents, CA needs; extended worksheets GSTR-2B/4/6/7/8/9 | `/reports/{gstr1,gstr3b,cmp08,tds-tcs,gst-health,gst-rate-exposure,missing-documents,gstr2b,gstr4,gstr6,gstr7,gstr8,gstr9}`, `/ca-needs` | 14 |
| **G3 Inventory depth and statutory** | Warehouses, transfers, serials, expiry alerts, bills of entry, fixed assets, statutory licences | `/inventory/{warehouses,transfers,serials,expiry-alerts}`, `/purchases/bills-of-entry`, `/accounting/fixed-assets`, `/settings/statutory-licences` | 7 |
| **G4 Growth** | CRM: leads, onboarding, opportunities, pipeline, campaigns, referrals | `/crm/*` | 6 |
| **G5 Service and contracts** | Complaints, supplier complaints, support and shared tickets, workshop, projects, insurance, contracts | `/complaints`, `/complaints/suppliers`, `/support/*`, `/workshop/jobs`, `/projects`, `/insurance`, `/contracts` | 8 |
| **G6 Operations** | Manufacturing (BOMs, work orders), payroll (employees, pay runs) | `/manufacturing/*`, `/payroll/*` | 4 |
| **G7 Intelligence** | Insights hub, alerts, health, cashflow, assistant | `/insights*` | 5 |
| **G8 Settings and integrations** | Payment gateway, billing, price lists, Telegram, Tally | `/settings/{payment-gateway,billing,price-lists,telegram,tally}` | 5 |
| **G9 Navigation with the full menu** | Measure and record only (see Q16) | all | |

Total 59. Corrections to the first version: journals are in G1; fixed assets are in G3 only; books health is in G1; billing, price lists and statutory licences are assigned; the Account Aggregator screen, collections, portal, stock counts, purchase planning, replenishment and delivery routes are **already audited** (`Audited-auto`) and get only a real-backend re-run, listed as "re-checks" below. `/portal/:token` was static-only and needs a generated token (G4).

**Real-backend re-checks (already audited in mock mode, not new work):** collections, customer 360, portal, payment links, delivery routes (missing `h1`), stock counts, purchase planning, replenishment, low stock, Account Aggregator, e-invoice submit screens.

## Every module phase has the same shape

1. **Snapshot** the audit company database (`scripts/backup.sh`), and record the flag check: fetch `GET /feature-flags/` after login and assert the phase's flags.
2. **Function check (smoke, 30 minutes per module, a cap):** open, list, create one record, reach the main action. Failure goes to "not ready" (Q5).
3. **Task walk (separate, 2 to 4 hours for deep modules):** GSTR-9, bank reconciliation, payroll run, work orders, period close.
4. **UX audit:** crawl at desktop and 393px on the real backend (axe WCAG 2.2 AA, targets, `h1`, overflow, console errors), static cognitive-load scan, Hindi top task, role check.
5. **Fix wave:** Critical and High (Q4). **Exit:** every phase row audited; Critical and High closed; Not-ready list reviewed by you.

## Decisions (answers to the 21 questions)

### Blockers
1. **Where it runs.** Dev only, on UX Audit Traders. Staging is out of scope. `compose-env.ps1` refuses the full-demo overlay there.
2. **Login.** `provision_ux_audit` creates owner, accountant, auditor, inventory staff, and sales staff. Passwords are written to `.ux-audit-credentials.local` and are not printed.
3. **G0 is not the blocker.** The command, history seed, snapshot scripts, and flag grant are in the repo and covered by tests.

### What "done" means
4. **Fix bar.** Critical and High fixed per phase; Medium and Low stay in the ledger and do not block exit. Money screens (period close, bank match, GST worksheets, payroll) get the same bar, with one addition: any **calculation, posting or tax defect** is not a UX fix. It goes to `BUG_REGISTER.csv` and to you, and no business logic is changed.
5. **Broken screens.** Three cases. (a) The screen loads but errors: show an honest in-page not-ready state, keep the nav item. (b) The route cannot load at all: hide the nav item for that flag until fixed. (c) Every case gets a ledger row with status `Not-ready` and a line in `docs/ux/not_ready.md`. Owner: the programme owner (me by default); you review the list at each phase exit.
6. **The 30-minute check.** A cap for the smoke check only. Deep walks are separate (phase shape step 3). Yes, documents may be created and posted on the **audit company**, never on Demo Traders. Reversal is by **database snapshot and restore per phase**, not by hand. Period close, pay runs and lock actions are done last in the phase.
7. **Seed data.** `seed_synthetic_bulk --history` writes 24 draft invoices, 12 draft purchases, 12 receipts, 6 stock-count sessions, 4 employees, and 8 leads. It refuses Demo Traders. `provision_ux_audit` runs it.
8. **Hindi, dark mode, roles.** Hindi: the top task per phase by hand, plus the automated i18n scan and a Hindi 393px crawl for every route (clipping, overflow, mixed language). Dark mode: **out of scope**; the theme is light only (`theme/index.ts`). Roles: see Q2.

### Scope versus the ledger
9. **Route map.** The ledger is the source of truth and the phases are re-bucketed (table above; 59 of 59 mapped).
10. **CMP-08** belongs to `ENABLE_GSTR` (its nav rule is `isGstrReportsEnabled()`; it was never in the hidden GSTR set). `ENABLE_GSTR_EXTENDED` covers only 2B, 4, 6, 7, 8, 9.
11. **Re-audit or skip.** Scope is the ledger rows that were `Gated-not-audited`. On the real backend some (TDS/TCS, Cashfree/PayU screens) are already on in the frozen pilot. They get a first real audit but are labelled "not newly enabled" and carry no freeze-doc implication.

### Flags that will not turn on by themselves
12. **CRM, manufacturing, payroll.** Checked: `enable_full_demo` prints the effective flags from `build_feature_flags`, and it reported all three on for Demo Traders, so there is no plan or pack blocker there. The rule bites only when a company has a subscription plan; each audit company gets the same check in step 1 and is created **without** a plan.
13. **AI (G7).** Consent stays off. Insights routes render the consent-off screen and do not call the summary, alert, or assistant APIs. `BB_UX_G7=1` adds `docker-compose.fulldemo.g7.yml`, which blanks `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` on api, worker, and beat.
14. **Integrations (G8).** Each screen names the missing credential and does not claim a live connection. No sandbox credentials are in the repo, so no live charge, Telegram send, or Account Aggregator fetch is part of this work. `--with-aa-consent` on `enable_full_demo` is opt-in and is not used by `provision_ux_audit`.
15. **Env-only modules.** The dev overlay includes `ENABLE_FIXED_ASSETS`, `ENABLE_BOE` and `ENABLE_ARCH05_STATUTORY_FORMS`. `backend/.env.pilot.example` pins all three at 0, and `ENABLE_GSTR_EXTENDED=0` is added (F9-2 is done for the backend file; the web example needs no build flag).

### Decisions this plan reopens
16. **Navigation (G9 vs D-UX-4).** Measure and record only. No structural nav change (grouping, search, packs) until you reopen D-UX-4. Flag-based gating, already built, is allowed.
17. **Bank reconciliation.** Confirmed: G1 walks it, may build the split pane only if D-UX-3 is approved, and builds no undo of a posted match.
18. **Existing waves.** G phases run **beside** Waves 0 to 7. On shared screens (New invoice, POS, receipts, editors) the existing waves win and the G phase rebases. G phases own the gated-module screens. The "about 4 weeks" was wrong to say it matched Waves 2 to 7; it is additional: about 2 to 3 days of audit and Critical/High fixes per phase, so **about 5 to 6 weeks for G1 to G9**, and about 10 to 12 weeks for everything with one engineer.
19. **Promotion checklist** (per module, your decision): Freeze Gate test for the module green; function check and task walk done; Critical and High closed; Hindi top-task pass; enabled for one named staging company with your approval; one user session; rollback noted. Then `docs/FREEZE_SCOPE.md` and the gate test change. G1 to G9 do not edit freeze docs or pilot examples (F9-2 excepted, now done).
20. **Parallel work.** One phase at a time per company. Two people can run two phases in parallel on **two separate audit companies**. Ledger rows are prefixed by phase (`G1-…`) and each phase edits only its own rows, so merges stay clean.
21. **Full menu.** Demo Traders and the audit company stay on the full menu for the whole programme. A fresh control company with `NAV_PACK_DEFAULT` stays on the pack sidebar so G9 can compare the two.

## Estimated order

G0, then G1 and G2 (money and compliance), then G3 to G8 in any order, G9 last.

## Status

| Phase | Status |
|---|---|
| G0 | Done. `provision_ux_audit`, `--history`, `ux_phase_snapshot.ps1` / `ux_phase_restore.ps1`, `--with-aa-consent`, staging refusal. Tests: `backend/tests/test_provision_ux_audit.py` |
| G1–G6 | Screens for the 59 gated routes already render with a heading. Load failures use `ErrorState` (heading plus message) or `ModuleNotReady`. `docs/ux/not_ready.md` has no hidden routes. Calculation and posting behaviour was not changed |
| G7 | Done. Consent-off screen on all five insights routes. Key-blanking overlay is `docker-compose.fulldemo.g7.yml` |
| G8 | Done. Fail-closed copy on payment gateway, Telegram, billing, price lists, Account Aggregator, and the existing Tally disclaimer |
| G9 | Done as measurement only. `docs/ux/g9_nav_measure.md` and the menu test `G9 full menu is larger than the pack sidebar`. No nav restructure |
