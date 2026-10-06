# Gated modules: detailed implementation plan

Date 2026-09-30. Inputs: the real-backend audit (`docs/UX_AUDIT_GATED_MODULES_2026-09-30.md`), the ledger (`docs/ux/L2_finding_ledger.csv`, UX-M01..M20), the unified plan and the decision log (`GROWTH_OS_AND_FEATURES_UNIFIED_PLAN_2026-09-30.md`, `GROWTH_OS_DECISIONS_2026-09-30.md`).

**Decided constraints that shape this plan** (GD-4, GD-6, GD-7, GD-8): three pilots run in parallel; rollout runs beside the audit; production widens only after the promotion checklist; 10 to 12 weeks. **No business logic changes.** Anything that would change posting, tax, stock or permissions is a founder decision, not a ticket here.

Ticket IDs are `GM-nn`. Sizes: S under 1 day, M 1 to 3, L 3 to 8. Every ticket ends with the standard done-check at the bottom.

Round 5 (GD-22 to GD-37) records the selected answers and overrides round 4 where they differ: no commit now, both slices in parallel, hook logic may be rewritten with tests, all three invoice buttons stay visible (A4-1 closed), the prototype (GM-99) waits for sessions, the owner counts as a booker (GM-47 done), Customer 360 builds all five sections in one slice (GM-45), three lanes start the same week.

Round 4 answers (33 questions) are in [GATED_MODULES_DECISIONS_ROUND4_2026-09-30.md](GATED_MODULES_DECISIONS_ROUND4_2026-09-30.md). **Round 5 wins wherever the two differ.** Round 4 still sets the ticket wording it was not overruled on: GM-03 has no create button; GM-21 is closed; GM-20 heading is just "GSTR-6", "GSTR-7" and "GSTR-8"; GM-40 is a menu; campaigns and contracts use the field splits below (projects, job cards and referrals stay inline); GM-52 adds "Add contract"; GM-60 guards the confirm inside the dialog after a payload check; GM-80, GM-81, GM-33 and GM-90 use the wording below; GM-98 is the WhatsApp consent policy. GM-99 waits until the pilot sessions are scheduled.

## 0. Progress (2026-09-30, after the decisions)

| Ticket | State |
|---|---|
| GM-01 enum labels | **Done.** `utils/enumLabels.ts`, `enums.*` in en and hi, applied to complaints, supplier complaints, tickets, contracts, campaigns, referrals, insurance line, pipeline stages; tests updated |
| GM-02 create dialog | **Done** (`components/CreateDialog.tsx`, 3 tests) |
| GM-03 books state | **Done in the working tree.** One banner: no chart (copy only, no button), back-fill, or quiet when books tie. Untrusted report totals show a dash |
| GM-12 bank reconciliation | **Done.** Session fields stay hidden until a statement exists. Upload stays on Bank statements |
| GM-13 period close | **Done.** Two-line note sits on the page beside the close controls |
| GM-20 GSTR-6/7/8 | Menu hidden. Headings are now "GSTR-6", "GSTR-7" and "GSTR-8" |
| GM-33 fixed assets | **Done.** Subtitle states straight line by default and written-down value per asset |
| GM-42 campaigns dialog | **Done.** List first. Name, type, start date and budget on open; the rest under More |
| GM-44 referrals | Labels already use enum labels. The form stays inline |
| GM-45 Customer 360 | **Done in the working tree.** Dues, tickets, contracts, referrals and opportunity value. A section that is off names itself and says it is not turned on |
| GM-51 contracts dialog | **Done.** Five fields first, the rest under More. Value label says it does not create an invoice. The recurring-invoice button is gone |
| GM-52 verb labels | **Done.** Includes Add contract |
| GM-60 work order | **Done.** Row Release stays enabled. Confirm waits until serials are entered for serial-tracked components, and the reason names them |
| GM-80 billing | **Done.** Start checkout is disabled, with a reason, when no provider key is saved. A trial shows "Free trial, ends {date}" |
| GM-81 gateway | **Done.** Saving with no keys says the connection is not live |
| GM-04 | Dropped (decision GD-10) |
| GM-05 landing h1 | **Done** (`EmptyState asPage`) |
| GM-07 developer-word guard | **Done** (`i18n/developerWords.test.ts`, with a short ratchet list of technical strings) |
| GM-47 CRM checklist step | **Done (GD-36).** The booker step now counts active owners and sales staff; `test_holistic_trial.py` updated and passing |
| GM-06 / GM-53 page states | **Done in the working tree.** Complaints, supplier complaints, tickets, campaigns, contracts, projects, job cards, referrals, and insurance show loading, error, and empty |
| GM-45 opportunity total | **Done.** The total walks every page for that customer. One next action is shown |
| GM-54 insurance | **Done.** The page title is an h1. Field labels are in en and hi |
| GM-82 / GM-83 | Telegram already names the missing token. Tally ignore-error copy is in en and hi |
| GM-90 client events | **Done.** `first_lead`, `first_quote`, and `receipt_from_link` record once. `first_invoice` stays the server timestamp |
| GM-91 admin counts | **Done.** `growth_metrics` matches the lead, ticket, contract, and referral tables. Events are on the Shop floor event admin |
| GM-95 / GM-96 | Design is `docs/ops/WHATSAPP_INVOICE_TEMPLATE.md`. The template name is `invoice_with_payment_link`. Cloud send already falls back to wa.me |
| GM-98 WhatsApp consent policy | **Written** in `docs/ops/WHATSAPP_CONSENT_POLICY.md`. Reminder and campaign sending still wait for the founder to read it |
| GM-99 disclosure prototype | **Waiting (GD-33).** Do not build until the pilot staff sessions are scheduled. Production invoice and purchase editors stay unchanged |
| GM-21 merge CA needs | **Dropped.** Menu entry uses `?view=client`; it is a different view, not a duplicate route (UX-M03 downgraded) |
| GM-30, GM-31, GM-43, GM-22 copy | **Done** (licences, bills of entry, leads and opportunities sentence, GST rate note) |
| GM-40 leads capture menu | **Done** (one Lead capture menu, test). Lead source filters use labels, not raw codes |
| GM-50 create dialogs | **Done** for complaints, supplier complaints, tickets, campaigns and contracts. Projects, job cards and referrals stay inline on purpose (GD-28) |
| GM-70 consent gate audit | Not started; AI consent stays off (GD-12) |
| GM-71, GM-84 | Dropped |
| Phase 0 (GM-100) | **Done.** The 12 guard tests for QOS-0083..0094 pass (3 race tests are Postgres-only and skipped); the 12 items moved from `fixed` to `verified`; backlog doc regenerated. `qos-lint` still reports 12 problems that were already there (L8 strategy gaps, one L10 guard name) |
| Web rebuild and real-backend check | Dev web rebuilt; axe 0 serious on 12 audited routes at desktop and 393px |

## 1. What is already done (do not redo)

| Item | State |
|---|---|
| Unnamed progress bars (checklist, setup wizard, insights factors) | Fixed, uncommitted (UX-M10) |
| Lead assignee select name | Fixed, uncommitted (UX-M09); desktop target-size node still to re-check |
| Nine developer-worded subtitles, en and hi | Fixed, uncommitted (UX-M04) |
| GSTR stub body copy | Fixed, uncommitted (UX-M02 partial) |
| Resolution time formatted as a duration | Fixed, uncommitted (UX-M06); `utils/duration.ts` with test |
| Demo tooling seeds the chart of accounts; audit company on a full-module plan; policy-desk user | Done, tested (UX-M01 partial, UX-M17) |
| Honesty copy for campaigns, referrals, insurance, tickets, GST, Tally, gateway | Already on screens (UX-M19, M20). Hindi to verify |

## 2. Tracks

- **Track A, shared foundations** (one engineer, weeks 1 to 3): components that many tickets reuse.
- **Track B, module packages** (weeks 2 to 9): per-phase tickets below.
- **Track C, pilots** (weeks 2 to 12, three parallel lanes): each pilot lane consumes Track A and B output as it lands.
- **Track D, measurement** (weeks 1 to 6): events and admin dashboard.
- **Track E, WhatsApp planning** (weeks 3 to 6, needs founder credentials).
- **Track F, verification and promotion** (continuous; closes weeks 10 to 12).

## 3. Track A: shared foundations

| ID | Ticket | Files | Change | Acceptance | Tests | Size | Depends |
|---|---|---|---|---|---|---|---|
| GM-01 | Enum label helper | new `web/src/utils/enumLabels.ts`; `i18n/en.ts`, `hi.ts` | One `enumLabel(group, value)` with en and hi labels for complaint category and status, ticket priority and status, contract type, campaign type and status, referral reward type, insurance line. Unknown values fall back to a title-cased string, never the raw code | No ALL_CAPS or underscore value visible in the lists and forms listed in UX-M05 | Vitest for each group; parity test covers new keys | M | none |
| GM-02 | Create-in-a-dialog pattern | new `web/src/components/CreateDialog.tsx` (or reuse the existing MUI Dialog pattern in `CustomersPage`) | A "New X" button opens a dialog or bottom sheet below `md`; the form keeps its validation; Escape and unsaved-change guard reused | The list is the first thing on the page; the form is not rendered until opened | Vitest: closed by default, opens, submits, closes | M | none |
| GM-03 | One books-state banner, with a no-chart state | `components/AccountingBackfillBanner.tsx`; the four report pages; `pages/phase` books pages | One banner that states one of: no chart yet, books on but older documents not posted, ties. Shown once per page. Totals that cannot be trusted show a dash, not 0.00. Copy says the chart appears on the first posting. **No Create-chart button** (GD-10) | The four screens show one consistent message; no page says "enable accounting" when books are already on | Vitest per state | M | none |
| GM-04 | ~~Enabling books creates the chart~~ | | **Dropped (GD-10).** Creation stays lazy. GM-03 covers the screens | | | | |
| GM-05 | Landing page h1 | `pages/LimitedAccessLanding.tsx` | One h1 ("This module is not on yet" or the role title) | h1 count 1 on landing routes | Vitest | S | none |
| GM-06 | PageState adoption check | `components/PageState.tsx` and the pages named in UX-M16 | Force a 500 on each service page and confirm `ErrorState` shows; wrap where missing. Use `asPage` only for full-page failures | Every service page shows loading, error, empty | Vitest with a rejected query per page | M | none |
| GM-07 | i18n guard for developer words | new test in `web/src/i18n` | Fail on user-visible values containing an ALL_CAPS_UNDERSCORE token, `API`, `supported: false`, or archetype codes such as `ARCH-05` | Test green; catches UX-M04 and M12 classes | the test itself | S | none |

## 4. Track B: module packages

### G1 Books and close (10 routes)

| ID | Ticket | Files | Change | Acceptance | Size | Depends |
|---|---|---|---|---|---|---|
| GM-10 | Apply GM-03 across TB, P&L, balance sheet, books health, chart | as GM-03 | Replace four repeated banners | One banner, one action | M | GM-03 |
| GM-11 | Journals plain-language pass | `i18n`, `pages/phase` journals | Voucher, reverse, post explained in shop language; keep "reverse with an opposite entry" | Owner can explain reversal in one sentence | S | none |
| GM-12 | Bank reconciliation empty-state path | `AccountingBankReconPage` | With no statement, keep the link to Bank statements (upload stays there) and hide the session fields until a statement exists | Fields shown only when a statement exists | S | none |
| GM-13 | Periods: state the effect of close | periods page | A two-line note on the page beside the close controls, before the button is pressed. The confirm dialog keeps its text. Copy only | The note is visible before the button; the confirm still names the period | S | none |
| GM-14 | Posted-document walk (accountant role) | `web/e2e/ux-*` | Walk expenses, journals, periods, reconciliation with real posts on the audit company; restore the snapshot after | Findings logged | L | audit company |

### G2 GST and compliance (14 routes)

| ID | Ticket | Files | Change | Acceptance | Size | Depends |
|---|---|---|---|---|---|---|
| GM-20 | GSTR-6/7/8 stubs | `pages/reports/GstReturnPage.tsx`, `i18n` | **Menu items hidden (GD-11, done).** Remaining (GD-35): direct-link headings are "GSTR-6", "GSTR-7" and "GSTR-8". The body keeps "Bizboard does not prepare this return yet" | No heading contains "(not filing)" | S | none |
| GM-21 | ~~Merge CA needs and Missing documents~~ | | **Closed.** `/ca-needs?view=client` is a different view of the same page, not a defect. Both routes stay. Ledger UX-M03 is not a defect | | | |
| GM-22 | GST rate exposure copy | `i18n` (already rewritten) | Add "who is the curator" as a plain owner instruction or remove | Text names an action | S | none |
| GM-23 | CA-role walk | e2e | Walk with the auditor user: read-only, export, no create controls | No create or write control renders | M | audit users |
| GM-24 | GSTR-2B/IMS task walk | e2e | Import a file, accept, reject, park, bulk accept | Findings logged | M | audit company |

### G3 Inventory depth and statutory (7 routes)

| ID | Ticket | Files | Change | Acceptance | Size |
|---|---|---|---|---|---|
| GM-30 | Statutory licences copy | `i18n` | Replace "ARCH-05" with "medicines and food licences" | No internal code visible | S |
| GM-31 | Bills of entry copy | `i18n` | Replace "set type NON_GST" with the label the purchase form shows | Words match the form | S |
| GM-32 | Transfers, serials, expiry: task walks | e2e | Create a transfer, record serials, write off an expired batch on the audit company | Findings logged | L |
| GM-33 | Fixed assets: depreciation explained | `i18n`, page | Sentence, en and hi: "Straight line by default; written-down value can be chosen per asset." Plus one sample row | Owner can read the register | S |

### G4 Growth (6 routes; this is Growth OS)

| ID | Ticket | Files | Change | Acceptance | Size | Depends |
|---|---|---|---|---|---|---|
| GM-40 | Leads: split capture setup from daily work | `pages/crm/LeadsPage.tsx` | **Done.** The four capture actions are one Lead capture menu, not a dialog. Search, filters and Add stay on the page | Nothing removed; menu test green | M | GM-02 |
| GM-41 | Leads: fix remaining axe target-size node | `LeadsPage.tsx` | Enlarge the failing control; re-run axe on desktop | 0 serious on `/crm/leads` | S | none |
| GM-42 | Campaigns create dialog | `pages/crm/CampaignsPage.tsx` | Apply GM-02 (GD-28). First: Name, Type, Start date, Budget. Under More: Status, Parent campaign, Target revenue, End date, Expected outcome | List first; those four fields on open | M | GM-02, GM-01 |
| GM-43 | Opportunities and Leads copy | `i18n` | Replace "lead notebook, not a CRM pipeline" with "Leads you are working. Deals live on the Pipeline page." plus a link | One clear sentence per page | S | none |
| GM-44 | Referrals: labels, form stays inline | `ReferralsPage.tsx` | Keep the three fields on the page (GD-28). Labels only, via GM-01 | No raw FLAT | S | GM-01 |
| GM-45 | Customer 360 as growth hub | `pages/sales/Customer360Page.tsx` | **All five sections in one slice (GD-37):** dues, tickets, contracts, referrals, opportunity value; each hidden when its flag is off with the line "{Section} is not turned on for your company." | Every growth journey can be finished from here | L | none |
| GM-46 | Lead-to-cash walk (J11) | e2e, posted docs on audit company | Lead, opportunity, quotation, order, invoice, receipt; restore snapshot | Findings logged; L6 behaviour confirmed | L | audit company |
| GM-47 | CRM checklist step 3 | `backend/crm/onboarding.py` | **Done (GD-36).** The booker step counts active owners and sales staff. Owner-only companies show the step done. The pilot operator note says so | Test updated and passing | S | none |

### G5 Service and contracts (8 routes)

| ID | Ticket | Files | Change | Acceptance | Size | Depends |
|---|---|---|---|---|---|---|
| GM-50 | Complaints, supplier complaints, tickets: create dialog | the three pages | GM-02 with GM-01 labels; list, filters and report first | Form not on the page until opened | M | GM-01, GM-02 |
| GM-51 | Contracts create dialog; projects and job cards stay inline | `ContractsPage`; `ProjectsPage` and `JobCardsPage` unchanged | Contracts use GM-02 (GD-28). First: Customer, Type, Start date, End date, Value. Under More: Reminder days (default 30), Notes, Products covered. Value label: "Value is for the renewal list. It does not create an invoice." No recurring-invoice link. Projects and job cards stay inline | Contract dialog shows those five fields first | M | GM-02 |
| GM-52 | Verb labels | pages above | "Create" becomes "Log complaint", "Open ticket", "Add contract", "Start project", "Create job card" | Every button names its object | S | none |
| GM-53 | Error states | GM-06 | Forced-500 tests for the eight pages | Error state visible | M | GM-06 |
| GM-54 | Insurance: h1 and copy | `InsurancePage` | h1 present; jargon check | h1 count 1 | S | none |
| GM-55 | Complaint to credit note walk (J12) | e2e | Complaint, inspect, approve, return, credit note; portal path (L8) | Findings logged | L | audit company |
| GM-56 | Ticket SLA and contract renewal walks | e2e | SLA pause on waiting, breach badge; renewal Attention row (L12) | Findings logged | M | audit company |

### G6 Operations (4 routes)

| ID | Ticket | Files | Change | Acceptance | Size |
|---|---|---|---|---|---|
| GM-60 | Work order Release guard | `WorkOrdersPage.tsx` | The row Release button stays enabled. Step 1: confirm the page can read the product serial flag (BOM lines carry a component id). Step 2: disable the confirm inside the dialog until serials are entered for a serial-tracked component, with a reason that names the component. No service change | Reason shown; the server still enforces Release | M |
| GM-61 | Manufacturing and payroll walks | e2e | BOM, work order, release; employee, pay run on the audit company | Findings logged | L |
| GM-62 | Payroll honesty check | payroll pages | Keep "Payslips are not Form 24Q"; confirm Hindi | Both languages | S |

### G7 Intelligence (5 routes)

| ID | Ticket | Files | Change | Acceptance | Size |
|---|---|---|---|---|---|
| GM-70 | Consent gate audit | insights routes, AI settings | Audit the off state, the wording that explains consent, and where it is switched on. **Do not switch consent on** while the dev API holds live provider keys | Consent wording reviewed in en and hi | S |
| GM-71 | ~~AI output audit~~ | | **Dropped (GD-12).** Consent gate only | | |

### G8 Settings and integrations (5 routes)

| ID | Ticket | Files | Change | Acceptance | Size |
|---|---|---|---|---|---|
| GM-80 | Billing state | `settings/BillingPage` | When no payment provider is configured, show "Start checkout" disabled with a reason. Do not hide it. A trial shows "Free trial, ends {date}" instead of "No subscription". First confirm why a company that has a plan read "No subscription" | No contradiction on the page | S |
| GM-81 | Payment gateway fail-closed check | gateway page | With no keys stored, the save message is "Saved. Not live: no keys are stored, so no payment can be taken." With keys, keep "Gateway settings saved". Test mode label stays | Verified | S |
| GM-82 | Telegram screen | `TelegramSettingsPage` | State what is missing when no bot is configured | Names the missing setting | S |
| GM-83 | Tally page label pass | i18n | Keep "one-shot, not live sync"; remove hard-coded English (7 strings) | 0 literals | S |
| GM-84 | ~~Flag cache~~ | | **Dropped.** No cache exists in the backend (flags are built per request). The stale walk most likely ran before the plan change landed (UX-M18 not reproduced) | | |

## 5. Track C: three parallel pilot lanes

Each lane runs from its own audit company (created by `provision_ux_audit`; extend with a `--name` option), uses the guardrails in the decision log, and has a named contact and rollback (remove the per-company flag). **All three lanes start the same week (GD-27).** Each grant still needs an explicit go.

| Lane | Pilot (staging company) | Modules granted (per company) | Must be true before the grant | Walks |
|---|---|---|---|---|
| C1 | Distributor: **Pilot Inter-State** | `ENABLE_COMPLAINTS`, Customer 360, portal (H4.2) | Phase 0 tests green; GM-01, GM-02, GM-50 shipped; complaint to credit note walk clean | GM-55 |
| C2 | Services firm: **Pilot Multi-User** | `ENABLE_SUPPORT_TICKETS`, `ENABLE_CONTRACTS`, `ENABLE_PROJECTS`, `ENABLE_WORKSHOP` (H5.3, H5.4); CRM only if asked (plan names it, H5.1) | GM-51, GM-52, GM-53; contract value label says it does not create an invoice (H5.4, label only) | GM-56 |
| C3 | Insurance advisor: **Pilot Insurance Advisor** (new staging company) | Insurance pack (CRM, campaigns, referrals, insurance) | GM-40, GM-42, GM-44, GM-54; advisor book and renewal diary walk. CRM checklist treats the owner as a booker (GD-36); the operator note says so | GM-46 plus renewal walk |

Grant commands, checks and rollbacks are in `docs/ops/GROWTH_PILOT_STAGING_RUNBOOK.md` (prepared, not run; the founder approves each grant, and the contact and rollback owner is the founder for all three lanes).

Rule from GD-7: fixes ship to a pilot as they land; a module that fails its function check goes on `docs/ux/not_ready.md` and is not granted.

## 6. Track D: measurement

| ID | Ticket | Change | Acceptance | Size |
|---|---|---|---|---|
| GM-90 | Client events (GD-5) | Add `first_lead`, `first_quote` and `receipt_from_link` only. `first_invoice` stays the existing server timestamp (`TenantActivation.first_invoice_at`). No personal data | Events arrive server-side and are visible in Django admin | M |
| GM-91 | Admin dashboard | Django admin views: lead conversion, ticket SLA, contract renewals, referral conversion, collections | Numbers match the tables | M |
| GM-92 | Baselines | Capture before any pilot grant | Baseline stored per pilot | S |

## 7. Track E: native WhatsApp (QOS-0046), planning only

| ID | Ticket | Change | Acceptance | Size |
|---|---|---|---|---|
| GM-95 | Design | First template is the invoice with a payment link (GD-25). Reminder is second, and only after GM-98. Consent and opt-in, failure and fallback to the wa.me link, delivery status, rate limits | Reviewed design doc | M |
| GM-96 | Build behind `ENABLE_WHATSAPP_CLOUD` with mocks | Provider adapter, template send, webhook status, tests with a fake provider | Green without credentials | L |
| GM-97 | Credentials | Founder supplies token, phone number id and the approved invoice template to the deployment secret store, never the repo | Sandbox message sent | S |
| GM-98 | Consent policy | Written policy before any reminder or campaign sending: who may be messaged (the customer WhatsApp opt-in flag), what is sent, how to opt out | Policy reviewed; no reminder or campaign send before it exists | S |
| GM-99 | Disclosure prototype | **Waiting (GD-33).** A clickable New invoice with "More details" for the pilot staff sessions. Do not build until those sessions are scheduled. Production editors stay unchanged | Sessions have a date; then the prototype exists | M |

## 8. Track F: verification and promotion

| ID | Ticket | Change |
|---|---|---|
| GM-100 | Phase 0 run | Growth OS, referral, contract, complaint and QOS-0083..0094 guard tests; move `fixed` to `verified` with evidence |
| GM-101 | CI | Add the six a11y routes and the new module routes to the axe e2e; add the i18n guard (GM-07); keep the surface-ledger check |
| GM-102 | Lint baseline | Clear the react-hooks v7 errors (UX-N21). Hook rewrites are allowed (GD-31) when a test fails before the change and passes after, the existing POS and invoice tests stay green, and posting, tax, stock and permissions do not change |
| GM-103 | Promotion checklist per module | Freeze Gate test green; function check and task walk; Critical and High closed; Hindi top-task pass; one pilot full cycle; one user session; rollback noted. Then `FREEZE_SCOPE.md`, gate tests, and last the trial plan |

## 9. Schedule (10 to 12 weeks, one engineer plus the pilots)

| Weeks | Track A | Track B | Track C | Track D and E |
|---|---|---|---|---|
| 1 | GM-01, GM-05, GM-07 | GM-100 (Phase 0) | Pilot names, dates, contacts | GM-90 design |
| 2 to 3 | GM-02, GM-06 | G1: GM-10 to GM-13; G2: GM-20 to GM-22 | All three lanes are ready to start the same week (GD-27). Each grant still needs a go. C1 needs GM-01, GM-02, GM-50 | GM-90, GM-92 |
| 4 to 5 | GM-03 | G4: GM-42 to GM-44; G5: GM-51 to GM-54 | Lanes run together. Grants that are not ready wait for their own go | GM-91; GM-95 design; GM-98 before any reminder |
| 6 to 7 | | G6, G7, G8 tickets; walks GM-14, GM-23, GM-24, GM-32 | Fixes ship to pilots as they land | GM-96 build with mocks |
| 8 to 9 | | GM-45 (all five Customer 360 sections); GM-46, GM-55, GM-56, GM-61 walks | Pilots run a full cycle. Staff sessions happen in these weeks once scheduled (GD-26). GM-99 starts only after a session date exists | GM-97 if credentials arrive |
| 10 to 12 | GM-102 | Regression, Hindi top-task passes, Critical and High closed | Pilot review; promotion checklist for the first module | Baselines vs results |

## 10. Risks

| Risk | Mitigation |
|---|---|
| Pilots see unaudited screens (GD-7) | Function check and honesty copy gate every grant; not-ready list; fixes ship continuously |
| Three lanes collide on `PosPage`, `NewInvoicePage`, receipts | Gated work and the invoice slice may run together (GD-30). Only one slice edits a shared file (`DocumentEditorShell`, `DraftLineTable`, the editors) at a time |
| Work stays uncommitted (GD-22) | Copy the touched files aside before a risky edit. Commit only when asked |
| Three lanes in one week (GD-27) | Three audit companies. Function check per module. Each grant still needs an explicit go |
| Hook rewrites on money screens (GD-31) | A test fails before and passes after. Existing POS and invoice tests stay green. No change to posting, tax, stock or permissions |
| Plan rule turns dark modules off for a subscribed pilot | Grant through the company's plan (H5.1); never edit the shared trial plan; provisioning does this for audit companies |
| Live LLM keys in dev | AI consent stays off everywhere (GD-12) |
| Flag cache hides a grant for minutes | GM-84 |
| Posted test documents pollute the audit company | Snapshot before each walk, restore after |

## 11. Definition of done for every ticket

1. Behaviour change with a Vitest or backend test; a Playwright step for a journey.
2. Axe clean on the touched screen at desktop and 393px.
3. Keyboard path works; targets 44px on phone.
4. New copy in `en.ts` and `hi.ts`; parity test green; no developer words (GM-07).
5. `tsc -b` clean; the ticket does not add lint errors. A hook rewrite follows GD-31.
6. Ledger row updated (`docs/ux/L2_finding_ledger.csv`), not-ready list updated if it applies.
7. No change to posting, tax, stock or permission logic. The owner-as-booker change (GD-36) is the one approved exception, and it is already shipped.
8. A ticket that changes a screen is checked in the browser on the audit company before it is called done (GD-34).
9. New Hindi copy is read by the founder before the ticket is called done (GD-23).

## 12. Decisions

**Decided (see `GROWTH_OS_DECISIONS_2026-09-30.md`, round 2):** chart creation stays lazy (GD-10); GSTR-6/7/8 hidden from the menu (GD-11); AI screens audited at the consent gate only (GD-12); all three pilot lanes widen to production on their own checklists (GD-13).

**Decided round 3 (GD-14 to GD-21):** pilots are Pilot Inter-State, Pilot Multi-User and Pilot Insurance Advisor on staging; founder owns contact and rollback; grants prepared in the runbook and approved one by one; WhatsApp sandbox first with credentials in the deployment secrets.

**Decided round 5 (GD-22 to GD-37):** keep working uncommitted; the founder reads the Hindi; insurance company is Pilot Insurance Advisor; first WhatsApp template is the invoice with a payment link; user sessions are staff of the three pilot companies; all three lanes start the same week, each grant still needs a go; campaign and contract field splits accepted; billing, gateway and contract-value wording accepted; both slices in parallel with one owner per shared file; hook rewrites allowed under the test rule; all three invoice buttons stay visible (A4-1 closed); the disclosure prototype waits for a session date; a browser check is required for every screen change; GSTR headings are "GSTR-6", "GSTR-7" and "GSTR-8"; the owner counts as a booker; Customer 360 builds all five sections in one slice.

**Still needs an explicit go, not a new decision:**

1. The go for each lane, even though they start the same week.
2. WhatsApp credentials in the deployment secret store (the template choice is made).
3. The week the pilot staff sessions actually sit (GM-99 and A2-5 wait on that date).
