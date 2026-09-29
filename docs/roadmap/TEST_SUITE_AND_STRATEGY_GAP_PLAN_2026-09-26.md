# Test suite and strategy gap plan

**Status:** Plan · **Date:** 2026-09-26 · **Owner:** QA + founder

**Review 2026-09-26.** `apply_pack("manufacturing")` does not raise. `manufacturing` is a real entry in `PACKS`, and `test_manufacturing_pack_grants_the_module` already asserts that call sets `manufacturing_pack_grant` and `ENABLE_MANUFACTURING`. `propose_pack()` returns only `retail` or `trade`, and `pack_views` confirms only that proposal. Phase 0.2 also updates the two `WF-01…WF-59` ranges in the strategy body, keeps new §7 rows on the `G-` id scheme, and archives the root `TEST_COVERAGE_GAPS.md`.

**Review 2026-09-26 (code pass).** Phase 0 edits `test_fg2d_ui_caps.py` itself (`POLICY_DESK` plus `canManagePolicies`), and changes `_migration_tables()` so it unions every RLS migration instead of appending new tables to historical `0020`. PRE-07 gets the journey id `J-PROJ-P1-MILESTONE`. Re-execution commands include PowerShell. Domain invariants cover the new rows. PRE-09 commission stays an off-ledger book (D17). Isolation probes use the real routes and do not assume PATCH or a `name` field. Golden flags are per company, not entries in `goldenApiEnv`.

Fill the holes between the product census and the suites that are supposed to prove it. The objective is confidence that a real Indian MSME user, and BizBoard operating as its own SaaS vendor, get the right money, tax, stock, permission, and next screen. A higher pass count is not the objective.

This plan implements the method in [TESTING_STRATEGY.md](../TESTING_STRATEGY.md) (layers L1–L10). It does not replace that document. It brings the census in [BUSINESS_DNA_CONSOLIDATED.md](../BUSINESS_DNA_CONSOLIDATED.md) under that method, including the screens shipped in revision 2026-09-26e.

The twenty-two validation aspects below are the order in which a claim is examined. They map onto L1–L10. They are not a second pyramid and they are not twenty-two new suites.

## Census this plan will not change

| Item | Count | Rule |
|---|---|---|
| Operating presets | 10 | PRE-01 through PRE-10 |
| Legacy market codes | 7 | ARCH-01 through ARCH-07. Do not renumber. The persona fixture label “ARCH-08” is a manufacturing fixture, not a product archetype. |
| Human personas | 14 | P1 through P14 |
| System roles | 8 | OWNER, MANAGER, SALES_STAFF, INVENTORY_STAFF, ACCOUNTANT, AUDITOR, VIEWER, POLICY_DESK. The consolidated doc still says 7. Update that sentence when the evidence column is refreshed. |
| Tracked journeys | 69 | 51 already in `qos/journeys.yaml`, plus 5 for P7–P10, plus 12 for insurance and SaaS, plus `J-PROJ-P1-MILESTONE` registered in Phase 0. That is the only new journey id. |
| Workflow chains | 60 | WF-01 through WF-60. Do not add WF-61. |
| Roadmap items | 23 | Already implemented. This plan tests them. It does not reopen the build. |

Batch, serial, multi-godown, and composition GST stay modifiers. Referral partner stays a party on a referral code, with no login.

## What this plan will not do

- Add one Playwright spec per journey. Five golden paths cover the shipped desks. The other journeys stay on the API layer or on an explicit hold.
- Invent Form 16A / 27D generation. Freeze scope marks D7 (WF-54) a known limitation: the worksheet is the product; the CA produces the certificate.
- Unskip WF-37 and WF-38 without Cashfree or PayU sandbox credentials in CI.
- Turn `ENABLE_CRM` on from the retail, trade, or distribution pack. The insurance pack grant stays the only CRM exception.
- Change `apply_pack("manufacturing")` so that it raises. That call is a working service-layer grant, already covered by `test_manufacturing_pack_grants_the_module`. `propose_pack()` stays on `retail` or `trade`, and the pack-confirm view keeps applying only that proposal. Payroll stays out of every pack.
- Post stock or GST from a job card, a proof-of-delivery slip, a policy record, a shared ticket, or an insurer commission. `CommissionReceivable` stays off the general ledger in this plan. Phase 0 records that as known limitation D17.
- Append newly created tables to `core/migrations/0020_rls_all_tenant_tables.py`. That migration has already run in any database that passed it. New tables belong in a follow-up RLS migration. The coverage test learns to read all of those lists.
- Build BOQ, retention, RA bills, usage-metered SaaS pricing, IRDAI filing, underwriting, or actuarial work.
- Treat `TEST_COVERAGE_GAPS.md` at the repo root as a source. It invents workflow ids. Phase 0 archives it. [TESTING_STRATEGY.md](../TESTING_STRATEGY.md) §7 remains the ranked register. This plan is the work list that feeds that register.

## How a claim becomes confident

A SUPPORTED behaviour is gated when a merge-blocking test would go red if it regressed. Use the same marks as the strategy:

| Mark | Meaning |
|---|---|
| Gated | A blocking test cites the journey or workflow id and asserts the business outcome |
| Partial | A lower layer is green. A named sub-case or a higher layer is still open |
| Gap | The behaviour is in the product and nothing cites it |
| Blocked | An external dependency is named (sandbox credentials, a CA, a pen-test, a staging budget) |
| Reference | The row is a product story. The suite cites a different id on purpose, and the ledger says which one |
| Boundary | The product refuses this step. A test asserts the refusal |

Every new scenario in this plan is written only after the golden rule below is filled in. A test that checks HTTP 200, or that a heading mounted, does not gate a claim.

---

## Golden rule

For every meaningful observation, action, screen, workflow, or scenario, write this chain before the test. If a step has no assertion, the claim stays Partial.

```text
USER INTENT
      ↓
BUSINESS EXPECTATION
      ↓
USER ACTION
      ↓
UI BEHAVIOUR
      ↓
APPLICATION BEHAVIOUR
      ↓
DATA / STATE CHANGE
      ↓
DOWNSTREAM EFFECT
      ↓
FINAL USER OUTCOME
      ↓
PERFORMANCE / SLA
```

Worked example, J-JOB-P9-REPAIR (the shape every new test copies):

| Step | Required content |
|---|---|
| User intent | P9 wants to bill a repair that used one spare and labour, and see the spare leave stock. |
| Business expectation | A job card converts once to a draft invoice. Stock and GST post when that invoice completes. PART lines are goods. LABOUR lines are services. |
| User action | Create the job, add both lines, convert, complete the invoice. |
| UI behaviour | Job cards screen shows the draft invoice link. A second convert is refused in the page. POLICY_DESK does not see the screen. |
| Application behaviour | `POST .../convert` once returns the invoice. The second call returns 400. Flag off returns 404. |
| Data / state change | One draft invoice. After complete, one negative stock movement for the spare. Ledger balanced. |
| Downstream effect | Stock on hand, GST, receivables, and the job’s invoice pointer agree. Cancelling the job after invoice is refused. |
| Final user outcome | P1 can open the invoice and collect. P9 cannot post a journal. |
| Performance / SLA | The job list query count stays flat for a 20-job company. No separate latency budget until a pilot asks for one. Name that absence. |

API-only rows still fill UI behaviour with “no screen in this slice” or “screen covered by the golden in Phase UI”. They do not leave the cell blank.

---

## The twenty-two aspects, mapped onto L1–L10

Read down the list. Each aspect names the layer that can prove it, the asset that already exists, and the work this plan adds. Later sections say which preset, persona, journey, and chain receive that work.

| # | Aspect | Proves | Layer | Already in the suite | Work this plan adds |
|---|---|---|---|---|---|
| 1 | UI / UX validation | The person sees the next honest screen, with no dead control that 403s | L6 | `web/e2e/personas/role-boundaries.spec.ts`, route smoke, complete-gate catalog | Component tests and one golden each for job cards, projects, insurance, shared tickets, POD received-by, billing suspend |
| 2 | Functional validation | The happy path does the business thing | L3, L4 | WF-01–WF-53, WF-55–WF-60, PJ files for P1–P6 | Five API days that cite journey ids. Reconcile yaml rows that already have a test under another name |
| 3 | Business rule validation | The product refuses the illegal combination | L2, L4 | Pack dark-module refusal, RBAC matrix, credit hold, period gate | Rules listed in the business-rule section, each with a red-then-green assertion |
| 4 | Calculation validation | Money, tax, tenure, and quotas are the numbers the books require | L1, L3, L5 | GST matrices, cess, composition WF-56, `assert_consistent` | Policy end date, commission versus premium, seat and document upgrade reasons, mixed SAC/HSN on the job invoice |
| 5 | Data integrity validation | After the operation the company is internally consistent | L1, L10 | Strict invariant sweep, `cross_reconcile` | Every new chain ends in `assert_consistent`. Unique policy issue, unique vendor share, stock movement sign |
| 6 | Cross-feature validation | A write is read the same way by every other surface | L8, L9, L10 | Status predicates, impact map, G-17–G-23 | Projection names for job, policy, POD, and SaaS. Stock moves on invoice complete |
| 7 | End-to-end validation | A persona can finish the loop on the real stack | L4 + L6 | Golden paths for ARCH-01 and ARCH-03 | Five flag-on goldens against Django. The other loops stay API-gated |
| 8 | Negative testing | Wrong role, wrong flag, wrong tenant, repeated command | L2, L4 | Boundary journeys, 403 matrix | Deny-set on each new day. Flag-off 404. Second convert, second issue, share by a non-owner |
| 9 | Boundary / edge testing | Zero, equal-to-limit, empty vendor, one option, last unit | L3, L5 | GST and expiry matrices, edge tests | The boundary table in that section. Reconcile before adding a duplicate |
| 10 | Performance / SLA validation | The action finishes inside a named budget | L6, L7 | POS 35s keyboard spec, dashboard heading budget, 50k report fixture, advisory k6 | Query-count on the four new lists. Heading budget on the five goldens. k6 stays advisory until a staging number exists |
| 11 | Concurrency / load behaviour | Two workers cannot double-post | L3 postgres lane | `tests/edge/`, concurrency script | Race convert-once and issue-once on Postgres |
| 12 | Accessibility validation | Serious axe findings are zero. Keyboard reaches the primary action | L6 | `a11y.spec.ts`, route-smoke axe, POS keyboard | Add the four new routes to smoke when flags are on |
| 13 | Compatibility validation | The same claim holds on CI Postgres and on the browsers we promise | L6 | Postgres CI, Chromium goldens, Hindi money spec | New goldens on Chromium. One mobile viewport pass on the new routes. Hindi only where the screen shows money |
| 14 | Security / permission validation | Isolation, role, and redaction hold | L2 | RBAC matrix, endpoint isolation, RLS coverage test | POLICY_DESK, manager, and auditor in the browser. Third-company denial on shares. Description omitted when blank |
| 15 | Integration validation | An external system is either contracted or explicitly out | L2, L3 | Webhook signature tests, WF-17 pointer, billing Razorpay | OpenAPI snapshot includes the new paths. No new insurer or GSP integration |
| 16 | Failure / recovery validation | Failure leaves a visible, retry-safe state | L3 | Idempotency WF-51, backup restore, outbox conflict | Vendor id empty, suspend without a reason, revoke share, flag off mid-session |
| 17 | Reporting / notification validation | The diary, prompt, and campaign say the right thing and do not send mail themselves | L3, L10 | GSTR tie-out, dunning, attention | Renewal lead prefix, trial notice window, upgrade reason, win-back campaign on the vendor company. SaaS dunning stays off customer AR dunning |
| 18 | Regression validation | A fixed bug cannot lose its guard | L1 + corpus | `tests/regression/`, `guard_regression_corpus_grows` | Any defect found while executing this plan gets one corpus test that was red before it was green |
| 19 | Gap analysis | Every row has a mark and an owner | Strategy §7 | Freeze coverage, this census | Build the ledger in Phase 0. Refresh stale evidence sentences |
| 20 | Test suite expansion | New tests cite ids and fill the golden rule | This plan | `test_roadmap_items.py` is the seed, not the persona suite | Phases below, in order |
| 21 | Re-execution | The lanes that can catch a regression were actually run | CI | Fast lane, invariant sweep, e2e-golden | The command list in the re-execution section, on CPython 3.13 |
| 22 | Final quality assessment | A named sign-off against open gaps, not against pass count | Strategy §11 | Pilot UAT, CA checklist, go/no-go | The scorecard at the end of this file |

---

## Phase 0 — Ledger and reconcile

Do this before writing behavioural tests. It stops the suite growing a second copy of a journey that already passes under another name.

### 0.1 Evidence ledger

Add `docs/TEST_CENSUS_LEDGER.md`. One row per preset, archetype, persona, journey, and workflow.

Columns: `id`, `kind`, `mark` (gated / partial / gap / blocked / reference / boundary), `layer`, `test` (file and function, or “none”), `screen` (route or “none”), `owner`, `note`.

Seed it from the dispositions in the sections below. A row with no test id stays Gap until a later phase fills it.

### 0.2 Strategy census

Edit [TESTING_STRATEGY.md](../TESTING_STRATEGY.md):

- Scope line: 10 presets, 7 legacy archetypes, 14 personas, 8 roles, 69 journeys, WF-01–WF-60.
- The L3 layer row (currently `WF-01…WF-59`) and the §3 “End-to-end journeys” asset cell (the same range) become WF-01–WF-60. `test_wf60_arch05_statutory_forms.py` is the chain those ranges omit. The later mention of WF-59 as the erasure chain stays. That citation is one chain, not a range.
- §3 “Personas & archetypes” status becomes Partial until Phase API lands. P7–P14 and PRE-03, PRE-07, PRE-09, PRE-10 are the reason.
- §4 persona narratives gain a short subsection for P7–P14 pointing at the journeys in §4.2 of the consolidated doc. Delight stays “no automated proxy” where none exists.
- §10.7 names the dark-module grants that exist in code. The insurance pack may set `pack_grant=insurance` and thus `ENABLE_CRM`. The manufacturing pack may set `manufacturing_pack_grant` and thus `ENABLE_MANUFACTURING`. Retail, trade, and distribution skip both. `propose_pack()` returns `retail` or `trade` only, and `accounts/pack_views.py` confirms that proposal, so the wizard never applies manufacturing. `HELD_PACKS` is empty. Payroll stays out of every pack. `ENABLE_WORKSHOP`, `ENABLE_PROJECTS`, and `ENABLE_INSURANCE` are rollout flags defaulting off. The gates are `test_manufacturing_pack_grants_the_module`, `test_insurance_pack_grants_the_sell_loop`, and `test_retail_and_trade_do_not_grant_dark_modules`.
- §7 stays on the `G-` id scheme. Add the next numbers, and close each one in §7 when its test lands, the same way G-4 was closed:
  - **G-24** — journey and preset rows with no citing test (traceability).
  - **G-25** — WF-54 has no pin (D7 known limitation).
  - **G-26** — `_migration_tables()` in `backend/tests/test_rls_coverage.py` unions `RLS_TABLES` from every core RLS migration (`0020`, `0036`, `0037`, `0038`, and later), and the assertion text stops telling the author to edit `0020`. `postgres-rls` stays a required check (`scripts/ci_gates/REQUIRED_CHECKS.txt`). New tables are enrolled only by a follow-up migration. Tables already named in both `0020` and `0038` may stay; the union treats a repeated name as one table.
  - **G-27** — P7–P14 have no persona day.
  - **G-28** — shipped desks have no golden path.
  - **G-29** — shipped pages have no component test.
  - **G-30** — browser roles omit POLICY_DESK, manager, and auditor.

### 0.3 Stale sentences

Refresh the Evidence column in [BUSINESS_DNA_CONSOLIDATED.md](../BUSINESS_DNA_CONSOLIDATED.md) §4.1 so it matches the code from revision 2026-09-26e. “No job card” and “Missing policy record” are false after that revision. Replace them with the ledger mark: API-gated, UI gap, or boundary.

`backend/tests/workflows/README.md` checkboxes are not a coverage list. Either regenerate them from `def test_wf` or add a header that says the functions are the list. Do not leave both.

### 0.4 Reconcile these journey rows before writing anything new

| Journey | Disposition | Existing evidence to cite |
|---|---|---|
| J-RETAIL-P1-REORDER | Reference, after a read of the kirana golden | `test_pj_golden_journey_kirana_retail_fast_turnover` mentions reorder. If it does not assert a threshold, leave Gap and add the assertion inside that test |
| J-TRADE-P5-BANKREC | Reference | `test_pj_bank_reconciliation_aa_matching_and_journal` and WF-33 |
| J-GODOWN-P4-COUNT | Reference | `test_pj_custodian_physical_stock_count_and_adjustments` |
| J-BATCH-P4-EXPIREBLOCK | Reference | `test_expiry_guard_band_matrix` |
| J-SERIAL-P4-INWARD | Reference | `test_pj_bulk_serial_import_partial_failure_blocks_whole_job` |
| J-SVC-P1-RECURRING | Reference to WF-11 | `test_wf11_recurring_invoice_generation_is_idempotent`. Persona wording stays Partial until an owner-day test cites the id |
| J-SVC-P1-AMC | Reference for the contract | `test_pj_commercial_contractor_amc_and_field_service_journey`. The visit link is J-AMC-P9-VISIT and stays a boundary |
| J-ROLE-P2-NAV | Reference | `role-boundaries.spec.ts` sales block |
| J-ROLE-P5-NAV | Reference | `role-boundaries.spec.ts` accountant block |
| J-A11Y-P2-KEYBOARD | Reference | `web/e2e/pos-keyboard-checkout.spec.ts` |
| J-BUY-P8-PO | Reference to WF-16 | `test_wf16_purchase_order_to_purchase`. P8 has no separate role |
| J-SAAS-P1-TRIAL | Reference | Existing billing trial tests. Cite the function in the ledger |
| J-SAAS-P14-BILL | Reference | Existing Razorpay, past-due, and plan-change tests. Cite them |
| J-CA-P6-AUDIT | Blocked on pilot | H-05. Proxy tests stay. No fake CA signature |
| J-SCALE-P1-REPORTS | Blocked on a staging budget | G-7. The 50k fixture stays. Do not flip k6 to blocking in this plan |
| J-TRADE-P3-FLAKYNET | Gap, then one degraded path or an L7 hold | Offline outbox covers the counter. The field order book is still open |
| J-GODOWN-P4-REORDER | Gap until a test asserts a per-warehouse reorder signal | Do not copy the counter reorder test and rename it |
| J-SERIAL-P2-WARRANTY | Gap | Lookup by serial at the counter, including a serial that was never sold |
| J-RETAIL-P2-THERMAL | Boundary or Gap | Assert the sale completes when no printer is attached, or mark thermal hardware a known limitation |
| J-ONBOARD-P1-STEPS | Gap until counted | FTUE test exists. Assert the first invoice is reachable in three steps or record the real step count and change the journey text |

### 0.5 Static guards

Add these so the next feature cannot skip the ledger:

| Guard | Fails when |
|---|---|
| Role list | `CompanyUser.Role.choices` contains a code absent from `ROLES` in `backend/tests/tenancy/test_rbac_matrix.py`, or the reverse |
| UI caps | The parser in `backend/tests/tenancy/test_fg2d_ui_caps.py` is the guard. Today its role loop is `ACCOUNTANT`, `VIEWER`, `INVENTORY_STAFF`, `AUDITOR`, `MANAGER`, plus a `SALES_STAFF` default, and `CAMEL` has no `canManagePolicies`. Phase 0 adds `POLICY_DESK` to that loop and `canManagePolicies` → `can_manage_policies` to `CAMEL`. A UI branch alone does not fail this test until those two edits land |
| RLS enrollment | `_migration_tables()` returns the union of `RLS_TABLES` across `core/migrations` modules that define that list. A new `company` table missing from every list fails the test. The fix is a new migration on the `0038_rls_roadmap_tables.py` pattern, not an edit to `0020` |
| Journey citation | Each of the five new persona modules contains its journey id string. `test_pj_project_milestones.py` contains `J-PROJ-P1-MILESTONE`. There is no exception for PRE-07 |

### 0.6 Rival audit at the repo root

Move `TEST_COVERAGE_GAPS.md` to `docs/reviews/archive/TEST_COVERAGE_GAPS_2026-09-26.md`. Add a banner at the top: superseded on 2026-09-26 by this plan and by [TESTING_STRATEGY.md](../TESTING_STRATEGY.md) §7; workflow ids in that file are not canonical. Leave no copy at the repo root. `docs/reviews/` is where one-off snapshots already live.

### 0.7 One new journey id, and the commission limitation

Register `J-PROJ-P1-MILESTONE` in three places: `qos/journeys.yaml`, [BUSINESS_DNA_CONSOLIDATED.md](../BUSINESS_DNA_CONSOLIDATED.md) §4.1 (P1, PRE-07: two milestones become draft service invoices; stock on a milestone is rejected; close waits until each READY milestone is invoiced), and the ledger. The tracked-journey count becomes 69. Do not add any other journey id.

Record **D17** in [FREEZE_SCOPE.md](../FREEZE_SCOPE.md) as a known limitation: the PRE-09 desk is an operational policy book. `CommissionReceivable` is not accounts receivable, does not post a journal, and does not appear on the trial balance, the sales register, or GSTR-1. A CA must not expect insurer commission on the P&L from this release. The insurance persona test asserts that absence.

---

## Phase API — functional, rules, calculation, integrity

One module per shipped preset. Each test function name contains the journey id. Each test fills the golden rule in its docstring. Each money test ends in `assert_consistent`.

Place them in `backend/tests/personas/` so they sit with the PJ suite. Keep `tests/test_roadmap_items.py` as the contract seed. Persona tests call the same services and add the role, the denial, and the downstream read.

| Module | Journeys cited | Who drives it | What “pass” means |
|---|---|---|---|
| `test_pj_workshop_job.py` | J-JOB-P9-REPAIR | Owner creates. A user with `can_create_sales` converts. POLICY_DESK receives 403 | One spare and one labour line. Convert once. Complete posts a negative stock movement and GST. Cancel after invoice is 400. PART rejects a service product. LABOUR rejects a goods product |
| `test_pj_route_pod.py` | J-ROUTE-P7-BEAT | Owner runs the route | Stop leaves PENDING only after the route is IN_TRANSIT. DELIVERED requires `received_by_name`. Receipt must match the order’s customer. Slip PDF returns 200. Completing the stop does not create a stock movement or a receipt |
| `test_pj_project_milestones.py` | J-PROJ-P1-MILESTONE | Owner | Two milestones become two draft service invoices. A stock product on a milestone is rejected. Close is rejected while a READY milestone is uninvoiced. Flag off is 404 |
| `test_pj_insurance_desk.py` | J-INS-P11-OPTIONS, J-INS-P12-ISSUE, J-INS-P12-RENEW, J-INS-P5-COMMISSION, J-INS-P10-CLAIM | POLICY_DESK for issue. Owner for the book. P5 reads commission | Two or more options. Choose one. Second issue returns the same policy id. End date is start plus tenure months times 30. Commission is not a `CustomerReceipt`. Renewal lead text starts with `Renewal {number}` and a second diary run adds zero. Claim creates a ticket and a `PolicyClaim` in the same company and posts no GST |
| `test_pj_saas_ops.py` | J-SAAS-P13-ACTIVATE, J-SAAS-P10-SUPPORT, J-SAAS-P13-WINBACK | Owner of the tenant. Vendor staff read as themselves | Setup completion and first completed invoice stamp `TenantActivation`. Share copies a redacted row into `VENDOR_COMPANY_ID` inside `rls_bypass` only. Source company and a third company cannot read it. Empty vendor id is 404 and writes nothing. Suspend requires a reason, sets suspended, and creates one draft win-back campaign on the vendor. Trial notice is on only inside the seven-day future window. Past-due does not show that notice |

### Business rules that must be explicit assertions

These already exist in product code. Pack rows are citations of `tests/test_roadmap_items.py`. Persona modules do not reimplement them. The other rows are asserted inside the persona modules.

| Rule | Assertion |
|---|---|
| Retail, trade, and distribution confirm | `ENABLE_CRM` and `ENABLE_MANUFACTURING` stay off. Cite `test_retail_and_trade_do_not_grant_dark_modules` and `test_distribution_pack_skips_dark_modules` |
| Manufacturing pack | `apply_pack(company, "manufacturing", ...)` succeeds. It sets `manufacturing_pack_grant` and `ENABLE_MANUFACTURING`, and leaves CRM and payroll off. Cite `test_manufacturing_pack_grants_the_module`. Do not add a test that expects this call to raise |
| Pack proposal | `propose_pack` returns `retail` or `trade` only. The confirm view applies that string. A pack name absent from `PACKS` still raises `BusinessRuleError("Unknown pack.")` |
| Insurance pack | Sets `pack_grant=insurance`. CRM resolves on only for that grant |
| Policy desk grant | `can_manage_policies` is true only for POLICY_DESK, and only an OWNER may grant it. Patching it onto SALES_STAFF is 400 |
| Policy desk books | 403 on invoice create, journals, trial balance, and imports |
| Job card | Flag off is 404. Serial only on PART |
| Option set | Fewer than two products is rejected. Exactly one option is chosen |
| POD | Delivery without a receiver name is rejected |
| Project | Close while a READY milestone is uninvoiced is rejected |
| Share | Sales staff with `can_create_sales` still gets 403 from the owner check. Revoke sets `revoked_at` |
| Vendor snapshot | `source_company_id` is not a database foreign key into the tenant |

### Calculation checks inside those modules

| Calculation | Expected |
|---|---|
| Job invoice tax | Labour carries SAC. Spare carries HSN. Intrastate split matches WF-01 rules for the same rates |
| Policy term | `end = start + tenure_months * 30 days`. Premium on the policy equals the chosen option and does not change when the product is later edited |
| Commission | Receivable amount is stored on `CommissionReceivable`. Customer outstanding does not move |
| Upgrade prompt | `used >= limit` on seats yields a seats reason. The same on documents yields a documents reason |
| Trial window | Ends in 3 days: show. Ends in 8 days: hide. Status past due: hide. Already ended: hide |
| Renewal copy | Message starts with `Renewal {policy number}` |

### Integrity checks inside those modules

- `assert_consistent(company)` after invoice complete, after claim, and after suspend.
- Stock quantity for the spare falls only after `SalesService.complete`, not after convert.
- One `VendorTicketShare` for `(vendor_company, source_company, source_ticket_id)`.
- Audit event `support.ticket_shared` is written on the source company after the bypass block, not inside it.
- A policy does not create a `JournalEntry`. `CommissionReceivable` does not create one either. That absence is D17, not a missing posting test.

### Domain invariants (L1)

`assert_consistent` today checks the ledger, invoices, bills, and stock. It does not read `JobCard`, `Project`, `Policy`, or `VendorTicketShare`. Phase API registers invariants under `backend/core/invariants/` so the strict sweep can fail when those rows disagree with themselves. Each invariant matches a field that exists:

| Invariant | Rule |
|---|---|
| Job card | If `sales_invoice` is set, that invoice belongs to the same company. Status `INVOICED` requires an invoice. A null invoice is not status `INVOICED` |
| Milestone | If `sales_invoice` is set, that invoice belongs to the same company. Status `INVOICED` requires an invoice. There is no project contract value on the model, so the invariant does not compare billed totals with one |
| Policy | `end_date` is on or after `start_date`. If `option` is set, that option belongs to the same company and its product is the policy’s product. Premium is a copy taken at issue. The invariant does not require it to keep equalling `PolicyProduct.premium` after a later product edit |
| Vendor share | `company` is `vendor_company`. `source_company` is a different company |

Do not add an invariant that insurer commission equals a ledger balance. D17 says that balance does not exist.

### Journeys that stay boundary pins, with tests

| Journey | Pin |
|---|---|
| J-AMC-P9-VISIT | A contract due date does not create a job card. Recurring invoice generation stays WF-11 |
| J-CARE-P10-TICKET | A ticket requires a customer and does not accept a serial id. It posts no ledger row |
| J-INS-P11-CAMPAIGN | Cite the existing growth campaign test while the insurance pack grant is on. Do not add a second campaign engine |
| J-INS-P11-SALE | Issuing a policy does not require an opportunity won, and a won opportunity does not create a policy. The ledger records that split until a later product decision joins them |

### WF-54

Add `test_wf54_certificates_remain_a_known_limitation` in `backend/tests/workflows/`. It asserts the product exposes the TDS/TCS worksheet path already covered by WF-36, and that no certificate PDF or GSTR-7/8 filing payload is produced by BizBoard. Docstring cites D7 and the freeze-scope limitation text. That closes the empty chain without pretending the CA’s form is generated here.

WF-17, WF-20, and WF-23 through WF-25 stay pointers. The ledger mark is Reference, with the files they cite.

WF-37 and WF-38 stay skipped. The ledger mark is Blocked.

---

## Phase UI — screens, accessibility, and browser permissions

UI work follows the API days, so the golden has a behaviour to click. Verify each golden in a browser by exercising the action, not by a single screenshot.

### Component tests (`*.test.tsx`)

| Page | Cases |
|---|---|
| `JobCardsPage` | Empty list. Validation when labour is given a goods item, if the page submits that. Primary convert control. Flag-off or missing permission renders no create action |
| `ProjectsPage` | Empty list. Milestone marked ready. Close disabled or explained while an uninvoiced ready milestone exists |
| `InsurancePage` | Empty book. Option set with one product shows the rule. Issue shows the policy number |
| `SharedTicketsPage` | Empty list. A row with a blank description does not render a description block |
| `DeliveryRoutesPage` | Deliver control stays unavailable until received-by is filled. Print slip hits the pdf URL |
| `BillingPage` | Upgrade reason text. Trial notice only when the payload says show. Suspend requires a reason. Vendor rows render for the vendor company |
| `UsersSettingsPage` | POLICY_DESK appears in the role menu. Caps for that role leave sales, journals, and imports off, and leave policy management on |

### Golden paths (`web/e2e-golden/`)

One spec each, Chromium. Each spec calls the existing `registerTenant` helper, which creates a fresh company. Do not add `ENABLE_WORKSHOP`, `ENABLE_PROJECTS`, or `ENABLE_INSURANCE` to `goldenApiEnv` in `web/playwright.golden.config.ts`. That env is process-wide. The same file already turns `ENABLE_ROUTE_PROFIT` and the other COMP flags on for every golden tenant. These three desks must not join that list, or the kirana and trade goldens would render the new nav.

These three keys are in `ROLLOUT_GRANTABLE_KEYS`. A company JSON value of true turns the flag on while the env default stays off. `feature_flags` is read-only on company PATCH (BB-000715), so the spec cannot set it through the public API. Phase UI adds a management command, `grant_rollout_flag`, that writes one flag on one company and refuses to run unless `E2E_GOLDEN_GRANT=1`. That variable is set only on the golden API process. The spec registers a tenant, runs the command for that email, then continues. Other specs never receive the grant.

`loginAsPolicyDesk` in `web/e2e/helpers/auth.ts` is for the mocked `web/e2e/` lane. The insurance golden uses a real registered user whose role is POLICY_DESK.

| Spec | Clicks | Also asserts |
|---|---|---|
| `workshop-job-golden.spec.ts` | Create job, add part and labour, convert, open the draft invoice | Invoice link visible. Second convert shows an error and does not create a second invoice |
| `route-pod-golden.spec.ts` | Start route, enter received-by, mark delivered, open the slip | Slip response is a PDF. Stock on the order is unchanged by the stop itself |
| `projects-milestone-golden.spec.ts` | Add two milestones, mark ready, invoice one | Two draft invoices exist after both are invoiced. Close explains the block while one is still ready |
| `insurance-desk-golden.spec.ts` | As POLICY_DESK: two options, choose, issue, open renewal list | Policy number visible. Accountant session does not see the insurance nav |
| `saas-share-and-suspend-golden.spec.ts` | Owner shares a ticket. Vendor user opens shared tickets. Owner suspends with a reason | Vendor sees the redacted ticket. Tenant user does not see the vendor list. Suspend shows the churn reason |

Login helpers: add `loginAsPolicyDesk` beside the existing helpers in `web/e2e/helpers/auth.ts`, plus a mock user whose `canManagePolicies` is true and whose sales and books caps are false. Add manager and auditor only as far as nav hiding: manager reaches operational screens, auditor does not see create on invoices or journals.

### Accessibility and compatibility on those screens

- Add `/workshop/jobs`, `/projects`, `/insurance`, and `/support/shared` to the authenticated route-smoke list used by `web/e2e` when the mock flags are on. Serious and critical axe violations stay zero.
- Keyboard: insurance issue and job-card convert are reachable without a mouse. Do not build a second POS-style timing spec.
- Mobile viewport: one pass at a narrow width that the primary action remains visible. File a layout bug if it is not. Do not expand WebKit goldens.
- Hindi: if a new screen shows money, extend `hindi-money-status.spec.ts` for that amount. Nav labels are covered by the component test against `hi.ts`.

### UX defects this phase must refuse to ship

- A control that renders for POLICY_DESK on invoices, journals, imports, or job cards.
- A Deliver button that succeeds with an empty receiver.
- A share control for anyone except the tenant owner.
- A success toast that claims stock moved when only a draft invoice was created.

---

## Phase edge — negative, boundary, concurrency, failure

Add these beside the persona modules. Prefer extending the module over a new file when the fixture is the same.

### Negative

| Case | Expected |
|---|---|
| POLICY_DESK creates an invoice, a journal, a job card, a project | 403 |
| Sales staff calls share | 403, even with `can_create_sales` |
| Another company’s id on job, policy, project, share | 404 |
| Workshop, projects, or insurance flag off | 404, not an empty 200 |
| Second policy issue for the same chosen option | Same policy id, no second row |
| Cancel a job that already has an invoice | 400 |
| Suspend with a blank reason | 400, status unchanged |
| Choose an option when the set has one product | 400 |

### Boundary

| Case | Expected |
|---|---|
| Option set of exactly two products | Accepted |
| Tenure of 1 month | End date is start plus 30 days |
| Seat used equals seat limit | Upgrade reason is seats |
| Document used is one below the limit | Upgrade prompt does not fire for documents |
| Trial ends in exactly 7 days and is still in the future | Notice shows |
| Trial ends tomorrow and the clock is past `trial_ends_at` | Notice hides |
| Received-by is a single character | Accepted if the field is non-blank. Do not invent a minimum length the product does not have |
| Last spare unit on the job invoice | Complete takes stock to zero. A second complete is impossible because the invoice is already complete |
| Renewal diary run twice | One lead |

### Concurrency

Add the two races to the existing Postgres concurrency module so `scripts/test_concurrency_local.sh` runs them:

- Two workers convert the same job. One invoice exists.
- Two workers issue the same chosen option. One policy exists.

SQLite will not show this. The ledger says so.

These races are not a merge-blocking CI job today. `.github/workflows/ci.yml` has no `pytest -m postgres` step. The required `postgres-rls` job runs `tests/test_rls_coverage.py` and `tests/tenancy/`. It does not run the concurrency races. This plan leaves that split as it is: the races are a required local step before a change to convert-once or issue-once, the same way G-11a already treats stock and numbering. Promoting the script into `REQUIRED_CHECKS.txt` is a separate CI decision and is not part of closing G-27.

### Failure and recovery

| Failure | Visible state afterwards |
|---|---|
| `VENDOR_COMPANY_ID` empty | 404. No `VendorTicketShare` row |
| Share then revoke | Vendor list hides the row. Source ticket remains |
| First invoice complete retried | One `first_invoice_at`. Idempotency key behaviour stays WF-51 |
| Flag turned off after a job exists | List is 404. The row remains in the database for when the flag returns |

---

## Phase cross-feature and reporting

Name the projections in the persona docstrings and assert the pairs.

| Write | Readers that must agree | Must stay quiet |
|---|---|---|
| Job convert | Job.sales_invoice id equals the draft invoice id | Stock, GST, receivables |
| Job’s invoice complete | Stock movement, tax lines, receivable, journal | A second movement from the job card |
| POD delivered | Stop status, receiver name, optional receipt id | Stock, GST, a new receipt row |
| Policy issue | Policy, nominee, premium copy, audit | Journal, customer receipt, stock |
| Commission | `CommissionReceivable` | `CustomerReceipt`, AR aging |
| Claim | `PolicyClaim` and a support ticket for the same customer | Credit note, GST |
| Ticket share | Vendor company’s share list | Source company’s share list, a third company, ticket description when blank |
| Suspend | Subscription status, churn reason, one vendor campaign named `Win-back {company}` | Customer dunning, a second campaign on repeat suspend |
| Trial notice | Payload `show` true or false | Any email or SMS send |
| Renewal diary | Lead count and message prefix | A duplicate lead, an invoice |

SaaS dunning tests must import `billing` dunning and must not call `payments` dunning. Customer AR dunning stays on the merchant’s invoices.

Reporting surfaces that already have tests (GSTR-1, 3B, trial balance, aging) stay as they are. New desks do not add a GST report. A policy is absent from the sales register. Insurer commission is absent from the trial balance and the profit and loss. That is D17, the operational policy book, recorded in Phase 0.7.

---

## Phase security and integration

### Permissions

`test_rbac_matrix.py` already has POLICY_DESK. Extend the browser:

| Role | Browser assertion |
|---|---|
| POLICY_DESK | Reaches `/insurance`. Does not reach invoice create, journals, or imports as a usable page |
| MANAGER | Reaches the operational routes the API already allows. Does not gain policy management |
| AUDITOR | Read-only. No create on invoices or journals |
| OWNER | Share control visible. Suspend control visible on billing |
| SALES_STAFF | No share control |

`backend/tests/tenancy/test_endpoint_isolation.py` keeps a hand-written `_PROBES` list. It is not generated from the router. The list today is customers, suppliers, and products. Its contract is a list that returns 200 and a PATCH of `name` that returns 403 or 404.

Do not append the new desks to that list. Job cards, projects, and policies allow GET and POST only. Job cards and policies have no `name` field. A PATCH of `name` would be 405, and the current assertion would fail for the wrong reason. Shared tickets are GET only, the row’s `company` is the vendor company, and the list returns 404 while `ENABLE_SUPPORT_TICKETS` is off. Workshop, projects, and insurance lists also return 404 while their flags are off, so a probe that expects 200 must turn the flag on for both tenants first.

Phase API adds four tests in that file, with factories, using these routes:

| Label | List URL | Read assertion | Write assertion |
|---|---|---|---|
| job_cards | `/api/v1/workshop/job-cards/` | Tenant A receives 404 for tenant B’s id after both companies have `ENABLE_WORKSHOP` | A POST or PATCH from tenant A does not change tenant B’s row. Do not require a `name` field |
| projects | `/api/v1/projects/` | Same shape, flag `ENABLE_PROJECTS`. `Project.name` exists, and the viewset still has no PATCH | Same |
| policies | `/api/v1/insurance/policies/` | Same shape, flag `ENABLE_INSURANCE`. Assert on `number` or `nominee`, not `name` | Same |
| shared_tickets | `/api/v1/support/shared/` | Factory creates a `VendorTicketShare` whose `company` and `vendor_company` are tenant B and whose `source_company` is someone else. Flag `ENABLE_SUPPORT_TICKETS` is on. Tenant A’s list does not contain the id | The viewset is GET only. Tenant A’s POST returns 403 or 405 and the row is unchanged |

RLS: after Phase 0, `test_rls_policy_present_and_forced_on_postgres` walks the union of every `RLS_TABLES` list, on the required `postgres-rls` job. Re-run that test in the re-execution section. Do not add `USING (true)` and do not add the new tables to `_EXCLUDED`.

Redaction: share serializer omits description when blank. The golden vendor session asserts the secret sentence from the source ticket is absent.

### Integration

- Regenerate is not part of this plan’s authorship. CI already diffs `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts`. Re-execution includes that diff. If the new routes are missing, update the snapshot in the same change as the views, with the spectacular command the CI job uses.
- Webhooks stay on the WF-17 pointer and the signature tests.
- No insurer API, no IRDAI, no live GSP. A test that the insurance viewset does not call a GSP adapter is unnecessary if the module imports none. A one-line import guard is enough if a later edit adds an outbound client.
- Razorpay remains the PRE-10 collection integration already under billing tests. This plan cites those tests on J-SAAS-P14-BILL.

---

## Phase performance

| Check | Budget | Where |
|---|---|---|
| POS keyboard checkout | Already 35 seconds to a pay-ready cart | Do not rebuild |
| New desk heading | Same idiom as `dashboard-budget.spec.ts`: heading visible within 4 seconds on the golden fixture | Each of the five goldens |
| New list endpoints | Query count does not grow with a second page of 20 rows | One assertion on job cards, projects, policies, shared tickets |
| k6 soak and degraded field network | Blocked until a staging budget exists | Ledger mark Blocked, G-7. J-TRADE-P3-FLAKYNET stays open or moves to L7 |

Do not add a query-count assertion to WF-01. That chain’s job is the books, and the strategy already has a large-tenant report test.

---

## Presets, archetypes, personas, journeys, chains

This is the breadth map. Phase columns say where the work lives. “Cite” means Phase 0 ledger only.

| Id | Functional | UI | Negative and boundary | Hold |
|---|---|---|---|---|
| PRE-01 / ARCH-01 | Cite POS, day close, offline | Cite role-boundaries and POS golden | Thermal boundary in Phase 0.4 | — |
| PRE-02 / ARCH-03 | Cite trade loop and WF-16 | Cite lifecycle-arch03 golden | Flaky field network stays Gap or L7 | — |
| ARCH-02 composition | Cite WF-56 and J-COMP-P1-BOS | None added | — | Commercially deprioritized |
| ARCH-04 godown | Cite transfer and count | Cite multi-warehouse golden if it covers the bill | Per-godown reorder is a Gap until asserted | — |
| ARCH-05 batch | Cite FEFO and expiry matrix | None added | — | — |
| ARCH-06 serial | Cite serial lifecycle | Warranty lookup is a Gap | Second return already rejected | — |
| PRE-03 / ARCH-07 | J-JOB-P9-REPAIR persona | Workshop golden | Type and convert-once | Timesheets stay out |
| PRE-04 | J-ROUTE-P7-BEAT persona | POD golden | Receiver required. No stock post | Cash collected on the beat stays a receipt via the existing receipt API, asserted as a separate step the slip does not perform |
| PRE-05 | Cite CRM persona tests | Cite growth-surfaces smoke | Pack confirm does not enable CRM | Dark unless insurance grant or an explicit flag |
| PRE-06 | Cite contracts persona and WF-11 | None added | J-AMC-P9-VISIT boundary | — |
| PRE-07 | `J-PROJ-P1-MILESTONE` persona | Projects golden | Stock product rejected. Close blocked | BOQ stays out. No contract-value invariant; the model has no contract value |
| PRE-08 | Cite the manufacturing persona and `test_manufacturing_pack_grants_the_module` | None | `propose_pack` never returns `manufacturing`. Retail, trade, and distribution do not set `manufacturing_pack_grant` | Service-layer `apply_pack("manufacturing")` stays green. The wizard does not call it |
| PRE-09 | Insurance persona | Insurance golden | Option count, second issue, no GST | Insurer core stays out |
| PRE-10 | SaaS persona plus cited billing tests | Share and suspend golden | Empty vendor, suspend reason, trial window | Usage-metered pricing stays out |

| Persona | Suite after this plan |
|---|---|
| P1–P6 | Existing PJ files. Ledger cites them. Browser gains no new role except where P5 and P1 appear in the new goldens as owner and accountant |
| P7 | Route POD persona and golden |
| P8 | WF-16 citation. No BUYER role |
| P9 | Workshop persona and golden. AMC visit is a boundary |
| P10 | Existing support persona, plus claim on a policy, plus vendor share denial |
| P11 | Options journey inside the insurance persona. Campaign cites growth tests |
| P12 | POLICY_DESK persona, RBAC, browser login, insurance golden |
| P13 | Activation and win-back inside the SaaS persona |
| P14 | Citation of billing tests |

System roles OWNER, MANAGER, SALES_STAFF, INVENTORY_STAFF, ACCOUNTANT, AUDITOR, VIEWER, and POLICY_DESK all appear in the API matrix. The browser phase covers the three that are missing today: MANAGER, AUDITOR, POLICY_DESK.

Workflow chains WF-01 through WF-60: ledger mark from `def test_wf`. The only new workflow test is the WF-54 limitation pin. No other chain is rewritten in this plan.

---

## Regression

- The strict invariant sweep stays blocking. New persona tests run under it.
- A bug found during execution gets one file under `backend/tests/regression/` or the nearest existing regression module, with the issue id in the name. It must have failed before the fix.
- `guard_regression_corpus_grows` stays. Do not delete a regression test to go green.
- Snapshots that change because a new field appears in GST or report JSON need a one-line reason in the change. Insurance and job cards must not appear in GSTR snapshots.
- Flake quarantine is still one phase long. A new golden that flakes is fixed or removed in the next pass, not left advisory forever.

---

## Gap analysis during execution

After Phase 0 and again after the last code phase, update:

1. `docs/TEST_CENSUS_LEDGER.md` marks.
2. [TESTING_STRATEGY.md](../TESTING_STRATEGY.md) §3 status cells and §7 rows.
3. The evidence column in the consolidated doc, so the next reader does not reopen a shipped feature as a missing object.

A row moves to Gated only when the test name cites the id and the assertion matches the golden-rule outcome. Partial is an honest mark. Do not mark a pointer test Gated.

---

## Test suite expansion order

| Order | Phase | Done when |
|---|---|---|
| 1 | Ledger, strategy census, evidence refresh, guards, D17, `J-PROJ-P1-MILESTONE` | Ledger exists. Strategy scope says 69 journeys. `test_fg2d_ui_caps.py` parses POLICY_DESK and `canManagePolicies`. `_migration_tables()` unions every RLS list. WF-54 pin is green. D17 is in the freeze scope |
| 2 | Five persona modules, four isolation tests, domain invariants | Each journey id in the API table is a function name, including `J-PROJ-P1-MILESTONE`. `assert_consistent` passes. The new invariants fail if the invoice pointer or the share’s company is wrong. Boundary pins exist for AMC visit and serial-on-ticket |
| 3 | Component tests | Six pages listed above have empty, error, and primary-action cases |
| 4 | Five goldens plus route-smoke axe | Each golden performs the action. Wrong role is denied. Heading appears within 4 seconds |
| 5 | Negative, boundary, Postgres races | The tables in Phase edge are green on the matching lane |
| 6 | Cross-feature pairs and reporting copy | The projection table is asserted |
| 7 | OpenAPI diff and RLS Postgres test | CI diff is empty. RLS test green on Postgres |
| 8 | Ledger and §7 update | No row still says “missing object” for a shipped feature |

Expand in that order. A golden written before the persona assertion exists will pass on a heading and hide a wrong ledger.

---

## Re-execution

Use CPython 3.13 at `C:\Users\Dell\AppData\Local\Programs\Python\Python313\python.exe`. The `py -3` launcher on this machine resolves a free-threaded build that crashes while importing the URLconf. Settings are `config.settings_test` (already the pytest default).

From `backend/`, after Phase API. PowerShell on this machine:

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings_test"
& "C:\Users\Dell\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests/personas/test_pj_workshop_job.py tests/personas/test_pj_route_pod.py tests/personas/test_pj_project_milestones.py tests/personas/test_pj_insurance_desk.py tests/personas/test_pj_saas_ops.py tests/workflows/test_wf_extended_stubs.py tests/tenancy/test_rbac_matrix.py tests/tenancy/test_fg2d_ui_caps.py tests/tenancy/test_endpoint_isolation.py tests/test_rls_coverage.py tests/test_roadmap_items.py -q --tb=line
```

The same command on a POSIX shell, for CI and other machines:

```text
DJANGO_SETTINGS_MODULE=config.settings_test python -m pytest tests/personas/test_pj_workshop_job.py tests/personas/test_pj_route_pod.py tests/personas/test_pj_project_milestones.py tests/personas/test_pj_insurance_desk.py tests/personas/test_pj_saas_ops.py tests/workflows/test_wf_extended_stubs.py tests/tenancy/test_rbac_matrix.py tests/tenancy/test_fg2d_ui_caps.py tests/tenancy/test_endpoint_isolation.py tests/test_rls_coverage.py tests/test_roadmap_items.py -q --tb=line
```

`pytest.ini` already sets `DJANGO_SETTINGS_MODULE=config.settings_test`. The explicit assignment is there so a shell that does not read pytest.ini still hits the right settings. A bare `VAR=value command` line is not valid in PowerShell or Command Prompt.

Fast lane from the strategy, plus the new modules, before a merge:

```powershell
& "C:\Users\Dell\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests/workflows tests/tenancy tests/gst tests/snapshots tests/edge tests/errors tests/matrices tests/personas tests/regression tests/test_invariants_smoke.py -q --tb=line
```

Postgres races stay on the local concurrency script. They are not part of the fast lane:

```powershell
scripts/test_concurrency_local.sh
```

On Windows, run that script from Git Bash, or the pytest invocation it wraps, against a Postgres `DATABASE_URL`. The required CI job for row-level security remains `postgres-rls` (`pytest tests/test_rls_coverage.py tests/tenancy/`).

Frontend, from `web/`:

```text
npx vitest run src/pages/workshop src/pages/projects src/pages/insurance src/pages/support src/pages/sales/DeliveryRoutesPage.test.tsx src/pages/settings/BillingPage.test.tsx
```

Use the repo’s existing Playwright scripts for `web/e2e/personas/role-boundaries.spec.ts`, the route-smoke spec, and the five new files under `web/e2e-golden/`. Exercise each golden in the browser: create, submit, deny the wrong role, reload, and confirm the other screen that reads the same state.

OpenAPI, the same command CI uses to diff `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts`.

`INVARIANTS_STRICT=1` on the persona run. A green suite with the sweep off is not the sign-off run.

---

## Final quality assessment

Sign off when the scorecard is filled. The numbers are counts of ledger rows, not counts of tests.

| Question | Ready when |
|---|---|
| Are the books still one story? | New money paths end in `assert_consistent` and name their projections. Policies, POD slips, shared tickets, and insurer commission create no journal. D17 states that PRE-09 commission is an off-ledger register in this release. The new domain invariants hold for job cards, milestones, policies, and vendor shares |
| Can the wrong person do it? | Eight roles are in the API matrix. POLICY_DESK, manager, and auditor are in the browser. Share is owner-only |
| Can two tenants see each other? | App-layer 404s are green. Postgres RLS job is green. Vendor share is invisible to the source company and to a third company |
| Did we prove the shipped desks? | Five persona modules and five goldens cite their ids. Component tests cover empty and error |
| Did we pretend a limitation was a feature? | WF-54 is a pin. WF-37 and WF-38 stay skipped. AMC visit and serial-on-ticket are boundary tests. CA filing stays H-05. D17 is written down, so a pilot is not told that insurer commission is on the trial balance |
| Is the census honest? | Strategy scope, ledger, and §4.1 evidence agree. No row says the job card or the policy record is missing |
| What is still outside production confidence? | Listed by id: G-7 staging budget, G-14 CA filing, G-9 pen-test, G-10 real broker, J-TRADE-P3-FLAKYNET if still Gap, J-SERIAL-P2-WARRANTY if still Gap, J-GODOWN-P4-REORDER if still Gap |

Production readiness for the freeze plus the 2026-09-26e desks is this scorecard all answered, with the outside list explicit. A full pytest pass with those rows still Gap is not readiness.

Human gates that stay human: pilot UAT, CA sign-off on F1–F8, go/no-go signatures, and a live counter timing study for H-02. This plan’s POS spec remains the automated proxy only.
