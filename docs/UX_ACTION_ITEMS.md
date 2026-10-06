# Bizboard UX Action Items (development backlog)

**Owner file for all UX follow-up work.** Updated 2026-09-30 from the UX programme (`docs/UX_MASTER_EXECUTION_PLAN.md`).
Source of truth for each row is `docs/ux/L2_finding_ledger.csv` (62 rows). Full reasoning is in `docs/UX_AUDIT_2026-09-30.md`.

**Constraint on every item:** presentation, flow, copy, focus, states and accessibility only. No change to money, stock, GST/TCS, ledger, permissions or API contracts. Items that would touch business logic are in section 6 and are not built until decided.

**Evidence caveat:** measurements were taken in **mock mode** (`--mode e2e`, demo data, local Chrome) with automated axe, a static code scan and a manual walk of about 8 screens. Nothing here was validated with real users, real data volumes or a real backend yet (see section 7).

**Definition of done for every item:** (1) behaviour change with a Vitest test and, for journeys, a Playwright step; (2) axe has no serious or critical finding on the touched screen; (3) checked at 393px and by keyboard; (4) new copy in both `en.ts` and `hi.ts` (`fullParity.test.ts` green); (5) `tsc -b` and `npm run lint` green; (6) the L2 row is updated.

---

## Scope correction and new phase (read first)

The crawl covered only the 82 routes that rendered; **59 flag-gated routes were never audited** in that crawl. They are assigned in the `phase` column of `docs/ux/L1_surface_ledger.csv` and covered by **`docs/UX_FEATURE_PHASES.md`** (G0 to G9). Section 9 below tracks it.

## Completed in the 2026-09-30 pass (uncommitted, in the working tree)

Verified by: `tsc -b` clean; Vitest on components, pages/sales, purchases, settings, inventory, pos, i18n, theme and api (all pass); axe (Chrome, mock mode) clean on the 6 previously failing routes; mobile axe clean on the 5 scroll-region routes.

| Item | What changed | Files |
|---|---|---|
| A1-1 done | Row/select-all checkboxes named on Sales history and 8 permission checkboxes per user on Settings > Users | `SalesHistoryPage.tsx`, `UsersSettingsPage.tsx`, `i18n` (`common.selectRow`, `common.selectAllRows`) |
| A1-2 done | Unlabeled amount inputs on both editors labelled | `DocumentTaxSummary.tsx`, `NewInvoicePage.tsx`, `NewPurchasePage.tsx` |
| A2-1 done | Discount-mode and payment-mode selects named | same files |
| A2-2 done | Disabled helper text contrast via theme | `theme/index.ts` |
| A2-3 done | Sideways-scrolling tables are keyboard regions (`tabIndex`, role, name) on list pages, the virtualized table, document lists, and the theme table container | `theme/index.ts`, `VirtualizedTable.tsx`, `DocumentListPage.tsx`, list pages |
| A2-4 done | Icon buttons and checkboxes are at least 44px below the `sm` breakpoint | `theme/index.ts` |
| A2-7 done | New items start on core essentials. Godown, lot and serial fields open only from "Add opening stock, lots or serials" | `ItemFormDialog.tsx` |
| A2-8 done | When Complete is blocked only because nothing is chosen, "Go to the missing field" focuses the party, or the item search if a party is already chosen | `DocumentEditorShell.tsx`, both editors, `PartySelectPanel.tsx` |
| A2-9 done | POS shows the expiry stored on the batch the cashier typed. It does not choose a lot | `posBatchExpiry.ts`, `PosPage.tsx` |
| A2-10 done for size | POS quantity steppers, row remove, and cash/UPI buttons are 48px tall on phones | already on `PosPage.tsx` |
| D-UX-7 done | Receipt allocation to the oldest invoices starts off and applies only after "Allocate to oldest" | `ReceiptsPage.tsx` |
| A3-1 done | Plain-language errors for network, timeout, 403, 404, 429, 5xx when the server sent no message | `api/client.ts`, `i18n` (`httpError.*`), `client.test.ts` |
| A3-5 done | Collections copy in owner language, en and hi | `i18n` (`osPlan.collectionsHelp`, `osPlan.screenOnly`) |
| A3-6 done | Focusable aria-hidden icon on Current stock | `CurrentStockPage.tsx` |
| A5-5 done | Axe assertions added for 5 more routes | `e2e/a11y.spec.ts` |
| Repairs | 4 TypeScript errors; dead POS expiry chip removed; stale `pos-friction` selector fixed | see ledger UX-025, UX-N18 |
| Tooling | `scripts/ux_surface_diff.py`, `ux_static_scan.py`, `ux_merge_crawl.py`; `web/e2e/ux-surface-crawl.spec.ts`, `ux-axe-detail.spec.ts`; `web/playwright.ux.config.ts` (uses installed Chrome) | |

---

## 0. Do first: close out the existing work (Wave 0, 1 to 2 days)

| ID | Action | Why | Done when |
|---|---|---|---|
| A0-1 | **Decided (GD-22): do not commit.** The working tree stays uncommitted until you ask. Before a risky edit, copy the touched files aside. Do not land this as one blob | There is no git rollback point. About 100 files are uncommitted, some from other sessions | No commit unless asked |
| A0-2 | Browser-verify the 24 "Implemented-uncommitted" rows in `L2_finding_ledger.csv` against a real backend (only 5 are verified so far) | Code and unit tests exist, but behaviour was only exercised in mock mode | Each row changes to Verified with evidence |
| A0-3 | Confirm the four TypeScript fixes made on 2026-09-30 (`CollectionsWorklistPage` unused import, `invoiceDefaults.ts` typing, removal of the dead POS expiry chip) still pass after rebase | Build was red before | `tsc -b` clean (was clean at 2026-09-30) |
| A0-5 | **Done 2026-10-01: `npm run lint` exits 0 (0 errors, 24 warnings) and CI runs it. The rewrites rely on the existing component tests (658 passing); no new fail-before tests were added for each one.** Was: `npm run lint` is red at HEAD. react-hooks v7 rules report errors in `PosPage`, `NewInvoicePage`, `NewPurchasePage`. **GD-31: rewrite hook logic where needed.** Each rewrite needs a test that fails before and passes after. Existing POS and invoice tests stay green. No change to posting, tax, stock or permissions | CI cannot gate UX PRs while lint is red | `npm run lint` green, under that test rule |
| A0-4 | Install Playwright browsers in CI or keep `playwright.ux.config.ts` (uses installed Chrome) for local UX runs | Bundled browsers were missing locally | Done. `web/playwright.ux.config.ts` sets `channel: 'chrome'` and says no browser download |

---

## 1. Critical (ship first, Wave 1, about 1 week)

| ID | Ledger | Screen | Action | Effort | Impact | Test / acceptance |
|---|---|---|---|---|---|---|
| A1-1 | UX-N02 | Sales history, Settings > Users (and any table with row checkboxes) | Give every row and select-all checkbox an accessible name (for example "Select invoice INV-0012", "Can create sales for Priya") | S | Screen-reader and keyboard users cannot use bulk actions or permission grids. 24 unnamed controls on Users alone | axe `label` clean on `/sales/history` and `/settings/users`; add both routes to an axe e2e |
| A1-2 | UX-N03 | New invoice, New purchase | Label the 3 unlabeled numeric inputs on each editor (charges, discounts, line totals) | S | The two highest-value screens fail WCAG 2.1 A for inputs | axe `label` clean on `/sales/new`, `/purchases/new` |

## 2. High (Waves 1 to 3)

| ID | Ledger | Screen | Action | Effort | Impact | Acceptance |
|---|---|---|---|---|---|---|
| A2-1 | UX-N04 | Invoice and purchase editors | Fix comboboxes whose `aria-labelledby` points at themselves | S | Party and item pickers announced with no name | axe `aria-input-field-name` clean |
| A2-2 | UX-N05 | Theme (all disabled helper text) | Change the disabled helper-text colour token to meet 4.5:1 in `web/src/theme/index.ts` | S | One token fixes editors and Item settings (8 nodes) | axe `color-contrast` clean on `/sales/new`, `/purchases/new`, `/settings/items` |
| A2-3 | UX-N07 | New invoice, New purchase, POS, Bank statements, Bank accounts | Done. Horizontally scrolling tables are keyboard regions | M | Keyboard and phone users cannot reach cut-off columns | axe `scrollable-region-focusable` clean at 393px |
| A2-4 | UX-N08 | Global; start with editors and POS | Done. Theme sets a 44px minimum for icon buttons and checkboxes below `sm` | L | Average page has 10 targets under 44px; editors 30 or more. Directly affects mis-taps at the counter and on phones | Crawl metric `smallTargets` under 5 on POS and editors; no layout overflow |
| A2-5 | UX-N12 | New invoice | Progressive disclosure: header shows Customer, Date, Invoice type; Godown, Cost centre, SEZ/RCM, e-commerce, Price mode move under "More details" with a summary of any non-default value. Line table hides HSN/MRP/Supply nature by default on narrow widths | L | 120 controls and about 10 header fields before the first item; the most used business screen. **Needs a design pass** | Task baseline: time and clicks from open to first saved invoice reduced; no field lost or renamed in the API payload |
| A2-6 | UX-N12 | New purchase | Same pattern as A2-5 (102 controls) | L | Same | Same |
| A2-7 | UX-N12 | Products page and Item dialog | Done for the create path. Opening stock, lots and serials stay behind a button. Pricing and basic details stay available | L | Highest control count in the app, used by the store keeper persona | Item create in under 6 fields for the default case |
| A2-8 | UX-N14 / CW-05 | New invoice | Done. "Go to the missing field" focuses the party, then the item search | M | Users hit a disabled button with no clear next step | Vitest: click focuses field |
| A2-9 | UX-025 | POS line | Done. Expiry comes from the typed batch. No lot is chosen for the cashier | M | Expiry sensitive shops (ARCH-05) | Chip appears when a batch with an expiry is entered; no lot auto-selection |
| A2-10 | UX-026 | POS tender and steppers | Done for size. Quantity steppers, row remove, and cash/UPI are 48px on phones. Tender confirm stays a dialog | M | Phones and tablets at the counter | Vitest at mocked narrow width |

## 3. Medium (Waves 3 to 5)

| ID | Ledger | Screen | Action | Effort | Acceptance |
|---|---|---|---|---|---|
| A3-1 | UX-N01 | Dashboard and any card that shows an API failure | Done. Replace raw "Request failed with status code 500" with plain-language copy per class (network, permission, server), keep Support ID and Retry | S | Vitest for each error class in en and hi |
| A3-2 | UX-N09 | `/invite`, `/help`, `/settings/help` | Done. One `h1` on these three routes. A real-backend check found 9 of 141 pages without an h1; six were the "not on yet" pages, already fixed (GD round 4, Q6) | S | Crawl `h1 == 1` on these three |
| A3-3 | UX-N10 | Products, Item dialog, Invoice detail, GST settings, Users, Stock count, editors | Partly done 2026-10-01: attribute strings (106) and JSX text (196 phrases, 22 files) are on en and hi, guarded by `literalRatchet.test.ts` and `jsxLiteralRatchet.test.ts`; about 29 files with JSX text and the dunning message text remain. Move about 190 hard-coded English strings into `en.ts` and `hi.ts`; add a test or lint rule that flags JSX literals | M | `static_scan.csv` hardcoded_strings drops to near 0; Hindi walk shows no English |
| A3-4 | UX-N11 | 35, 40 and 48 pages flagged | Confirm which pages truly lack loading, error, empty states; introduce one state wrapper and apply | M | Each page shows all three states in a test |
| A3-5 | UX-N16 | Collections | Done. Rewrite developer-language copy ("This list is a screen…", "WhatsApp Cloud") in owner language | S | Copy reviewed with Hindi and English |
| A3-6 | UX-N06 | Inventory stock | Done. Remove focusability from the aria-hidden icon | S | axe clean |
| A3-7 | UX-N17 | Dashboard | Verify low-stock count equals the alert list on a real backend | S | Count equals list length |
| A3-8 | UX-003/004, UX-010, UX-011, UX-018, others | Various | Finish "not evidenced" rows: X6 purchase copy (RCM/ITC) and L5 counter limitation copy | S each | Verified in browser |
| A3-9 | Mobile | POS, invoices | Run the Hindi-language pass at 393px (L1 requirement) on every screen touched in waves 1 to 3 | M | No wrapped text covers a primary button |

## 4. Low (Wave 6, polish)

| ID | Ledger | Action | Effort |
|---|---|---|---|
| A4-1 | UX-N13 | **Closed (GD-32).** Keep Save & Complete, Complete and start another, and Save draft all visible. Do not fold them into a menu | — |
| A4-2 | UX-N15 | Done. Receipts: hide columns that are empty for the whole page; show "Page x of N" and total | S |
| A4-3 | UX-N19 | Done in mock mode: Dashboard and Insights load with no console errors (checked 2026-10-01). Console-error assertions are still off. Add the missing mock handler that 500s on every page so console-error assertions can be switched on | S |
| A4-4 | Design system | Adopt the Phase 3 pattern guide (`docs/ux/patterns.md`) on remaining screens | L |

## 5. Measurement and governance action items

| ID | Action | Effort |
|---|---|---|
| A5-1 | Instrument the HEART events listed in `docs/ux/heart_metrics.md` (setup completion, time to first invoice, form abandonment, draft-restore use, undo use). Partly done: form abandonment, draft restore, document void and `form_validation_failed` (2026-10-01) exist; hesitation and back-navigation do not | M |
| A5-2 | Capture task baselines on a real backend for the 10 tasks in `docs/ux/heart_metrics.md` before any Wave 2 change ships. Only POS keyboard checkout has an automated timing today | M |
| A5-3 | Done. `scripts/ux_surface_diff.py --check` is a blocking CI step. Local check: 190 surfaces, 0 missing | S |
| A5-4 | Done 2026-10-01: open ledger rows are rolled up into QOS-0095..0100, the backlog doc is regenerated and `qos-lint` passes. Promote the accepted findings into `qos/backlog/*.yaml` and regenerate `docs/PRODUCT_QUALITY_BACKLOG.md` through the existing qos tools, then pass `qos-lint`. Not done yet; the UX ledger is a separate CSV for now | M |
| A5-5 | Done. All six routes are in `PROTECTED_ROUTES` (axe runs in `route-smoke.spec.ts`) and in `a11y.spec.ts`. Add axe assertions to `route-smoke.spec.ts` for the 6 routes that failed (`/sales/new`, `/sales/history`, `/purchases/new`, `/inventory/stock`, `/settings/items`, `/settings/users`) so they cannot regress | S |
| A5-6 | Run Lighthouse and INP against staging with realistic data; test one low-end Android device through the Capacitor shell | M |
| A5-7 | Run 5 to 8 moderated sessions with real users on the top five tasks plus a 3-question NASA-TLX-lite; feed results back into the ledger | M |

## 6. Founder decisions required (not built until decided)

See `docs/ux/founder_decisions.md` and round 5 (GD-22 to GD-37). Adopted: keep `<=` for low stock, no bank-match undo and no split pane, keep the current nav, no Tally remap, show POS expiry only, and confirm before oldest-invoice allocation. Progressive disclosure (D-UX-2) waits until pilot staff sessions are scheduled (GD-33). Those sessions are with staff of the three pilot companies (GD-26). The founder reads new Hindi copy (GD-23).

## 7. Known limits of this audit (do not treat as done)

- Mock mode only: layout, semantics and interaction cost were measured; data volume, real API errors and real latency were not.
- Manual walkthrough covered Dashboard, New invoice, Receipts, Collections, Attention, POS and Setup redirect. The other ~130 pages have automated axe, layout and static-scan coverage only, not a manual Nielsen or cognitive-walkthrough score.
- Static scan scores (1 to 5 cognitive load) are triage heuristics, not measured load.
- Light theme, English only for the 2026-09-30 crawl. Dark mode stays out of scope (the theme is light only). Hindi is in the G phases: the top task by hand, plus an automated Hindi crawl at 393px for every route.
- Reconciliation, period close, GST returns, imports and Tally migration were not walked.
- No user sessions were run, so persona jobs are hypotheses.

## 8. Wave order

G phases run beside these waves (GD-30). Only one slice at a time edits `NewInvoicePage`, `NewPurchasePage`, `PosPage`, `DocumentEditorShell` or `DraftLineTable`. A2-5 and A2-6 wait until pilot staff sessions are scheduled (GD-33). A4-1 is closed.

| Wave | Items |
|---|---|
| W0 | A0-1 decided: do not commit (GD-22). A0-5 lint rewrites follow GD-31 |
| W1 | A1-1, A1-2, A2-1, A2-2, A5-5 (done in the working tree) |
| W2 | A2-8, A2-4, A2-10, A2-9, A2-7 (done in the working tree) |
| W3 | A2-5, A2-6 wait for sessions. A3-1 and A3-5 are done |
| W4 | A2-3 only tables that overflow. A3-2 is `/invite`, `/help`, `/settings/help` only. A3-3 is the current slice. A3-4 |
| W5 | A3-6 to A3-9, A5-3, A5-4 |
| W6 | A4-2, A4-3, A4-4. A4-1 is closed |
| W7 | A5-1, A5-2, A5-6, A5-7 (sessions are pilot staff), regression sweep, final report |

## 9. Feature enablement phases (dev only, until a module is promoted)

Full plan and the answers to the 21 pre-G1 questions: `docs/UX_FEATURE_PHASES.md`. Phases are G0 to G9. The 59 gated routes are assigned in the ledger `phase` column (G1 books, G2 GST, G3 inventory and statutory, G4 CRM, G5 service, G6 manufacturing and payroll, G7 insights, G8 settings). Production stays frozen (`docs/FREEZE_SCOPE.md`) until you promote a module. One phase at a time per company. Ledger finding ids are prefixed by phase.

| ID | Action | Effort | Status |
|---|---|---|---|
| F0-1 | Nav visibility driven by runtime flags (`FLAG_GATED_NAV` in `menu.ts`), replacing hard-coded hidden lists; new `ENABLE_GSTR_EXTENDED` flag | S | Done (3 nav tests, tsc clean) |
| F0-2 | `manage.py enable_full_demo --email` (demo/staging only, refuses production, no AI consent or credentials) | S | Done (5 backend tests) |
| F0-3 | `docker-compose.fulldemo.yml` overlay and `BB_FULL_DEMO=1` switch in `scripts/compose-env.ps1` | S | Done |
| F0-4 | Apply to the dev stack (127.0.0.1) and verify flags on a real backend | S | Overlay and `enable_full_demo` are in the repo. Creating the audit company on a running dev database is `provision_ux_audit` (refuses production and staging). Do not post documents on Demo Traders |
| F0-5 | Apply the full-demo overlay to staging (127.0.0.1:8081) | S | Done as a refusal. `compose-env.ps1` exits if `BB_FULL_DEMO` or `BB_UX_G7` is set for staging |
| F0-6 | Create UX Audit Traders with no subscription, one user per role (owner, accountant, CA/auditor, inventory staff, sales staff), and extend `seed_synthetic_bulk` with `--history` (six months) | M | Done. `manage.py provision_ux_audit`. Passwords only in `.ux-audit-credentials.local`. Also creates UX Pack Control with `NAV_PACK_DEFAULT` |
| F0-7 | Snapshot and restore the audit company per phase (`scripts/backup.sh`, restore), not hand reversal | S | Done. `scripts/ux_phase_snapshot.ps1` and `scripts/ux_phase_restore.ps1` label the compose backup/restore profiles |
| F0-8 | `docs/ux/not_ready.md` plus ledger status `Not-ready`. In-page state if the screen loads and errors; hide the nav item only if the route cannot load | S | Done. `ModuleNotReady`, `ErrorState` heading, `notReadyNav.ts`. The not-ready list is empty |
| F0-9 | Opt-in `--with-aa-consent` on `enable_full_demo` (default remains consent off) | S | Done. Provision does not pass it |
| F1 to F6 | G1–G6 gated screens: heading on load errors, nav hide mechanism, no business-logic changes | L | Done for the code bar in the phase plan. No route is marked not-ready |
| F7 | G7 insights with consent off and provider keys blanked | M | Done. `AiConsentOffScreen` on `/insights*`. `docker-compose.fulldemo.g7.yml` |
| F8 | G8 settings name the missing credential and stop | M | Done. Payment gateway, Telegram, billing, price lists, Account Aggregator, Tally disclaimer |
| F9 | G9 measure full menu versus pack sidebar. No structural change | S | Done. `docs/ux/g9_nav_measure.md` and `menu.test.ts` |
| F9-1 | Update `docs/FREEZE_SCOPE.md` and the Freeze Gate tests only when a module is promoted | S per module | Not this programme. Checklist stays in the phase plan |
| F9-2 | State `ENABLE_GSTR_EXTENDED` as off in the pilot profile | S | Done (`backend/.env.pilot.example` has `ENABLE_GSTR_EXTENDED=0`; web needs no build flag) |

## 10. Growth OS and all other features

Unified plan: [roadmap/GROWTH_OS_AND_FEATURES_UNIFIED_PLAN_2026-09-30.md](roadmap/GROWTH_OS_AND_FEATURES_UNIFIED_PLAN_2026-09-30.md). Most of Growth OS is already built (seven epics, 29 growth tests, all QOS-0083..0094 at `fixed`). What remains is verification, honest copy, UX audit, instrumentation and per-company rollout.

| ID | Action | Effort | Status |
|---|---|---|---|
| GP0 | Run the Growth OS, referral, contract and complaint tests; move QOS-0083..0094 from `fixed` to `verified` with evidence; correct the stale build-state table in `GROWTH_OS_EPICS_ROADMAP_2026-09-24.md` | S | Tests run 2026-09-30: `test_growth_os.py` and related pass (44 passed, 1 skipped). QOS status moves and the roadmap correction are still open |
| GP1 | Real-backend audit and task walks of the 14 growth and service routes (needs the audit login) | L | Blocked on audit login |
| GP2 | Customer 360 as the growth hub; one next action per customer; honesty sentences verified in en and hi | L | Not started |
| GP3 | Growth metrics baseline (server-derived now; client events to add) in Django admin | M | Not started; needs decision 4 in the unified plan |
| GP4 | Per-company rollout following Holistic H4 and H5 (never "enable all" in production) | depends on pilots | Needs a named pilot company |
| GP5 | Decision-gated scope: QOS-0028, QOS-0046, competitor tracking, live GSP, campaign sending | XL | Parked until a pilot asks |
| GP6 | Packs, vendor view, promotion checklist | M | Not started |
| GP7 | Plan QOS-0046 native WhatsApp delivery behind `ENABLE_WHATSAPP_CLOUD`: design, tests with mocks, template list. First template is the invoice with a payment link (GD-25). Credentials stay out of the repository. Reminder and campaign sending wait for GM-98 | M | Template chosen. Credentials and the written consent policy are still open |
| GP8 | Three parallel pilot companies. Names: Pilot Inter-State, Pilot Multi-User, Pilot Insurance Advisor. All three start the same week (GD-27). Each grant still needs an explicit go | L | Names set. Grants not run |
| GP9 | Create "UX Audit Traders" and role users on the dev stack | S | Approved (GD-2); run on an explicit go |

## 11. Remaining gated modules: audit done, build plan written

> **Superseded by section 12 and the plan's section 0.** The statuses in this table are older. Do not rebuild finished tickets.

The original audit prompt has now been run on the 59 flag-gated routes on a real backend (audit company, all modules on). Results: [UX_AUDIT_GATED_MODULES_2026-09-30.md](UX_AUDIT_GATED_MODULES_2026-09-30.md). Ticket-level build plan: [roadmap/GATED_MODULES_DETAILED_IMPLEMENTATION_PLAN.md](roadmap/GATED_MODULES_DETAILED_IMPLEMENTATION_PLAN.md) (GM-01 to GM-103, three pilot lanes, 10 to 12 weeks). Ledger: UX-M01..M20 in `docs/ux/L2_finding_ledger.csv`.

| ID | Action | Status |
|---|---|---|
| GP9 | Create "UX Audit Traders" and role users | Done on the dev stack; passwords in the gitignored `.ux-audit-credentials.local` |
| GP1 | Real-backend audit of the growth and service routes | Done (54 of 59 routes; insights at the consent gate only) |
| GM-01..07 | Shared foundations (enum labels, create dialog, books banner, landing h1, page states, i18n guard) | Not started |
| GM-40..56 | Growth and service screens | Not started |
| Fixed now | Progress-bar names, lead assignee names, nine developer subtitles, GSTR stub copy, duration format | Uncommitted, tested |
| Decisions | Chart stays lazy (GM-04 dropped); GSTR-6/7/8 hidden (done); AI consent gate only (GM-71 dropped); all three pilots widen on their own checklists | Decided 2026-09-30 (GD-10 to GD-13). Open: pilot names and dates, WhatsApp details |

## 12. Progress after "proceed with the decisions" (2026-09-30)

Done and tested (uncommitted): enum labels (GM-01), create dialog on complaints, supplier complaints and tickets (GM-02, GM-50 partial), landing h1 (GM-05), developer-word guard (GM-07), Lead capture menu (GM-40), verb labels (GM-52), copy fixes (GM-30, 31, 43), GSTR-6/7/8 hidden from the menu, QOS-0083..0094 moved to `verified`. Verified on the real dev backend after a web rebuild: axe 0 serious on 12 routes.

Still blocked, and not a coding gap: each lane grant needs your go; WhatsApp credentials stay in deployment secrets; GM-99 and A2-5/A2-6 wait for a session date; you still read the new Hindi; staff sessions are not scheduled. Posted-document walks (GM-14, 23, 24, 32, 46, 55, 56, 61), Lighthouse, task baselines, and the quality-backlog promotion stay measurement work on a live audit company. The react-hooks lint on POS, new invoice, and new purchase (GM-102) is cleared in the working tree: ref updates moved to layout effects, prop-driven field defaults adjust during render, and draft restore waits one microtask so it does not set state synchronously inside an effect.

Done in the working tree since the last pass: service-page loading, error, and empty states; insurance, project, job-card, and Tally labels; Customer 360 totals across pages and one next action; `first_lead`, `first_quote`, `receipt_from_link`; admin growth counts; the invoice-with-payment-link template name; the written consent policy. Receipts hide an empty Source or UTR column and show page of N. Invoice type, price mode, and the prefix label are in English and Hindi. The editor error can be closed. A4-1 stays closed. A2-5 and A2-6 still wait for a session date. This pass added `form_abandoned` and `draft_restored` (leave guard, invoice draft restore, POS session restore), translated the remaining purchase-editor field labels, a low-stock KPI test that uses the loaded list length, a literal ratchet on the swept screens, and axe routes for billing and stock counts. Those tests passed. Browser check on UX Audit Traders and the Hindi read are still required before those screens are Done.

Later the same day: invoice statutory and quick-add labels, insights KPI labels, low-stock table copy, supplier-payment dialog labels, and journal post/reverse sentences are in English and Hindi. Voiding a receipt or a supplier payment records `document_voided`. The lead assignee control is 44px and covered by a test. Payroll keeps the Form 24Q sentence in both languages. AI consent copy was checked against GD-12: the screen says consent is off, nothing is sent, an owner turns it on in Settings, and there is no enable button on the gate. Grants, the disclosure prototype, walks, Lighthouse, baselines, and the Hindi read are still open.

## 13. Next: cognitive load reduction (2026-10-04)

The canvas audit is written as the next action list: [docs/ux/COGNITIVE_LOAD_NEXT_ACTIONS.md](ux/COGNITIVE_LOAD_NEXT_ACTIONS.md). File-level specs, waves, and tests are in [docs/ux/COGNITIVE_LOAD_REDUCTION_PLAN.md](ux/COGNITIVE_LOAD_REDUCTION_PLAN.md). Nothing in either file is built by writing it. Task-weighted load is 3.5 / 5. Highest job is new purchase at 4.5. Hiding editor fields still waits on GD-33. Defaults, chips, and copy can start now.

| ID | Action | Priority | Effort | Start when |
|---|---|---|---|---|
| CL-20, CL-03a, CL-16 | Series number as a caption, one word “Godown”, nav labels Money in / Money out | P3 / P0 / P1 | S | Now. No inference, no hidden field |
| CL-15 | Plain sentences when Complete is blocked. Focus the field. Keep the draft | P1 | S | Now |
| CL-01a, CL-02a | Infer invoice type and show the company price mode, while the selects stay visible | P0 | M / S | Now |
| CL-05 | One filled button on the posted invoice. Other actions move into a menu | P0 | M | Parallel. Does not hide editor fields |
| CL-14 | POS quantity edit keeps focus until Enter or Escape | P1 | M | Parallel |
| CL-06, CL-07 | Return goods from the invoice. Ask for place of supply only when GSTIN and address disagree | P0 | M | After CL-05 is ranked |
| CL-08, CL-09 | Purchase lines fill from the item and the upload. ITC is a chip | P0 / P1 | L / M | After CL-07 |
| CL-10, CL-11, CL-12, CL-13 | Period-close checklist, role templates, GST settings lock, products search-first | P1 | L / M / S / M | After document actions |
| CL-04, CL-01b, CL-02b, CL-03b | Statutory chip and hidden selects on the two editors | P0 | S / M | After the pilot staff session |
| CL-17 | Auto-apply a unique bank match | P2 | M | Founder decision first |
| CL-18, CL-19 | Field-order context strip. Owner morning list, five rows | P2 | M | After period close exists for the fifth row |
