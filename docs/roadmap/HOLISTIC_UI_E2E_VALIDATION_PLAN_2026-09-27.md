# Holistic UI, end-to-end, performance, and test-suite plan

**Status:** Executed 2026-09-27 · **Date:** 2026-09-27 · **Revised:** 2026-09-27 (review pass) · **Owner:** QA

Execution record: `TEST_EXECUTION_REPORT.md`. The fifteen ledger Gaps from section 1 are closed as Gated or Reference. I2, I3, I4, and I5 are gated in `backend/tests/test_phase0_api_slas.py` and `test_i4_catalog_import_of_5000_skus_meets_ten_seconds`. I1, WF-37, WF-38, G-7, and G-14 stay on the holds table. They were not half-built.

This is the execution plan for a full product-validation cycle on BizBoard. It follows the method in [TESTING_STRATEGY.md](../TESTING_STRATEGY.md) (layers L1–L10) and the work list in [TEST_SUITE_AND_STRATEGY_GAP_PLAN_2026-09-26.md](TEST_SUITE_AND_STRATEGY_GAP_PLAN_2026-09-26.md). It does not add a second test pyramid, a second workflow numbering scheme, or SLA numbers that the product has not defined.

The outcome of the cycle is a filled scorecard: every meaningful claim is Gated, Partial, Gap, Blocked, Reference, or Boundary, and every new Gap that is in freeze scope has a test in an existing suite that was actually run.

This cycle is one QA stream. It runs beside other in-flight roadmap work (OS vision, freeze-gate phases). The schedule in section 9 is the sequencing constraint. It is not a stop-the-line for the whole team.

---

## 0. Rules that govern every later step

### Canonical sources, in this order

1. Code: routes in `web/src/navigation/menu.ts`, pages under `web/src/pages/`, roles in `CompanyUser.Role`, workflows under `backend/tests/workflows/`.
2. Census: `qos/journeys.yaml`, [TEST_CENSUS_LEDGER.md](../TEST_CENSUS_LEDGER.md), [FREEZE_SCOPE.md](../FREEZE_SCOPE.md), [FREEZE_SCOPE_COVERAGE.md](../FREEZE_SCOPE_COVERAGE.md). The coverage map is canonical only after Step 1.0. Its header says last reconciled 2026-09-16, which is behind later billing, payments, CRM, and RLS work.
3. Method: [TESTING_STRATEGY.md](../TESTING_STRATEGY.md).
4. Formal latency targets: only the five rows in [PHASE_0_DOD.md](../pilot/PHASE_0_DOD.md) section I.

| ID | Action | Target (P95) | Class |
|---|---|---|---|
| I1 | POS barcode lookup | ≤ 100 ms | Must |
| I2 | Invoice save and complete round-trip | ≤ 800 ms | Must |
| I3 | Paginated list, 50 rows | ≤ 400 ms | Must |
| I4 | Catalog import, up to 5,000 SKUs | ≤ 10 s | Must |
| I5 | Async invoice PDF queue | ≤ 2.5 s | Should |

Anything else is a measurement with **SLA: not defined**. The 4-second heading check in `web/e2e/dashboard-budget.spec.ts` and the 35-second POS keyboard spec are test idioms. They stay test idioms. [SUPPORT_SLA.md](../pilot/SUPPORT_SLA.md) is a staffed support process, not a page-load budget.

I4 is measured by `test_i4_catalog_import_of_5000_skus_meets_ten_seconds`: 5,000 catalog rows, upload plus commit, at most 10 seconds. A smaller file is not I4.

### Ids that already exist

- Workflows: `WF-01` through `WF-60`. `WF-54` is a known-limitation pin. `WF-37` and `WF-38` are gated on the books path. They do not call Cashfree or PayU.
- Journeys: the ids in `qos/journeys.yaml`, plus the desks already on the ledger (`J-JOB-P9-REPAIR`, `J-ROUTE-P7-BEAT`, `J-PROJ-P1-MILESTONE`, insurance, SaaS).
- Roles: `OWNER`, `MANAGER`, `SALES_STAFF`, `INVENTORY_STAFF`, `ACCOUNTANT`, `AUDITOR`, `VIEWER`, `POLICY_DESK`.
- Personas: P1–P14. P8 has no login. Referral partners have no login.

### What this cycle will not do

- Add one Playwright spec per journey. Browser proof stays on the golden paths and the role-boundary spec. The other journeys stay on the API layer.
- Invent Form 16A / 27D, BOQ, retention bills, IRDAI filing, usage-metered SaaS pricing, or a journal for insurer commission (D17).
- Claim a penetration test or a k6 capacity number. The security modules and the 50,000-invoice fixture ran. They are not those claims.
- Claim an NVDA or VoiceOver session. The accessible name and axe contrast on the POS scan field were measured.
- Weaken an assertion so a suite goes green.
- Treat the repo-root notes from 2026-09-26 (`PRODUCT_DISCOVERY.md`, `WORKFLOW_CATALOG.md`, `DEFECT_REPORT.md`, and the other root finding files) as sources. `WORKFLOW_CATALOG.md` uses ids such as `WF-SALES-01`. Those ids are not in the suite. The gap plan already says a root coverage file that invents workflow ids is not a source.

### What the cycle closed

A live vendor call, a human signature, and a staging soak are outside the software. The rows below are the tests that closed the software part.

| Item | What closed it | What was not faked |
|---|---|---|
| WF-37, WF-38 | `test_wf37_refunds`, `test_wf38_mdr_settlement_reconciliation` | A live Cashfree or PayU HTTP call |
| J-TRADE-P3-FLAKYNET | Offline outbox conflict spec | A live packet-loss capture |
| J-SCALE-P1-REPORTS, G-7 | 50,000-invoice register fixture, 3 passed | A staging k6 soak |
| J-CA-P6-AUDIT, G-14 | `test_pj_ca_statutory_and_accounting_integrity_audit` | A human CA signature |
| D17 | Left as Boundary. Commission is not a journal | A posting the product does not do |
| Pen-test | Tenancy, Postgres RLS, sprint0 security, no-impersonation | A penetration test |
| I4 | `test_i4_catalog_import_of_5000_skus_meets_ten_seconds` passed | A smaller file called I4 |

### Severity rubric

Use the scale already written in [DEEP_LINE_REVIEW_2026-09-02.md](../reviews/DEEP_LINE_REVIEW_2026-09-02.md). Do not invent a second Sev1–Sev4 scale.

| Mark | Use it when |
|---|---|
| P0 | Data, money, or tax is wrong, a security boundary fails, or a real path hard-crashes |
| P1 | Wrong output or a broken flow, including a Must SLA breach on I1–I4 that does not also corrupt data |
| P2 | Edge correctness, missing validation, or a race |
| P3 | Maintainability |
| UX | User-facing friction that is still usable |
| SUGG | Improvement |

A data-corrupting SLA failure is P0. “SLA not defined” is not a severity. “Unmeasured” is a coverage Gap, not a defect.

### Golden rule, filled before any new test

```text
USER INTENT → BUSINESS EXPECTATION → USER ACTION → UI BEHAVIOUR
→ APPLICATION BEHAVIOUR → DATA / STATE CHANGE → DOWNSTREAM EFFECT
→ FINAL USER OUTCOME → PERFORMANCE / SLA
```

A test that only checks HTTP 200, or that a heading mounted, does not gate a claim.

### How to run Python

CI and every other machine run `python -m pytest` with the repo virtualenv active. `pytest.ini` already sets `DJANGO_SETTINGS_MODULE=config.settings_test`. The commands in Phase 5 use that `python`.

On this Windows box, `py -3` resolves a free-threaded build that crashes while importing the URLconf. Use CPython 3.13 from the active virtualenv. A full path under one user’s `AppData` is a local convenience. It is not part of this plan and it is not what CI runs.

---

## 1. What is already true, so the cycle starts from the ledger

The product surface is about 150 pages, a flag-aware sidebar, eight roles, public token routes (`/pay/:token`, `/portal/:token`, `/lead-form/:token`), and offline outbox. The suite is already large: workflow chains, persona days, tenancy and RBAC matrices, GST matrices, invariant sweep, 33 Playwright specs under `web/e2e/`, and golden paths.

[TEST_CENSUS_LEDGER.md](../TEST_CENSUS_LEDGER.md) already marks most presets and `WF-01`–`WF-60` as Gated, Reference, Boundary, or Blocked. The open rows are the work. Several of those Gap marks disagree with tests the gap plan says already exist. Phase 1 resolves that disagreement by reading the test, not by writing a second one.

### Open ledger rows to settle first

| Id | Ledger mark today | First action |
|---|---|---|
| J-TRADE-P5-BANKREC | Gap | Read `test_pj_bank_reconciliation_aa_matching_and_journal` and WF-33. Cite them as Reference if they assert the match. Leave Gap only if the assertion is missing, then add that assertion inside the existing test. |
| J-GODOWN-P4-COUNT | Gap | Same treatment for `test_pj_custodian_physical_stock_count_and_adjustments`. |
| J-BATCH-P4-EXPIREBLOCK | Gap | Same for `test_expiry_guard_band_matrix`. |
| J-SERIAL-P4-INWARD | Gap | Same for the bulk serial import persona. |
| J-SVC-P1-RECURRING | Gap | Cite `test_wf11_recurring_invoice_generation_is_idempotent`. Persona wording stays Partial until an owner-day test cites the id. |
| J-SVC-P1-AMC | Gap | Contract is the commercial-contractor persona. Visit creation from a contract stays the boundary `J-AMC-P9-VISIT`. |
| J-ONBOARD-P1-STEPS | Gap | Count the real steps from register to first invoice in the existing FTUE test. Record the count. Change the journey text if the “three steps” claim is wrong. |
| J-RETAIL-P1-REORDER | Gap | If the kirana golden mentions reorder but does not assert a threshold, add the assertion inside that test. |
| J-RETAIL-P2-THERMAL | Gap | Assert the sale completes with no printer attached, or mark thermal hardware a known limitation. |
| J-GODOWN-P4-REORDER | Gap | A per-warehouse reorder signal. Do not copy the counter reorder test and rename it. |
| J-SERIAL-P2-WARRANTY | Gap | Serial lookup at the counter, including a serial that was never sold. |
| J-A11Y-P2-KEYBOARD | Gap | POS keyboard spec exists. Extend `web/e2e/a11y.spec.ts` beyond login and dashboard for the cashier path, or cite the keyboard spec and mark Partial with the remaining routes named. |
| J-TRADE-P3-FLAKYNET | Blocked | Offline outbox covers the counter. Field-order degradation stays on the holds table (G-7). |
| J-SCALE-P1-REPORTS | Blocked | 50k fixture may stay. k6 stays advisory. Same holds table. |
| J-CA-P6-AUDIT | Blocked | Proxy tests stay. No fake CA signature (G-14). Same holds table. |

---

## 2. Phase 1 — Reconcile the census before any new behaviour test

Exit when the ledger, the strategy scope line, and the code agree, and no root note is still being used as a workflow id.

**Step 1.0 — Freshness check, before trusting the coverage map.** [FREEZE_SCOPE_COVERAGE.md](../FREEZE_SCOPE_COVERAGE.md) says last reconciled 2026-09-16. Diff commits after that date that touch in-scope models and migrations, including billing, `payments/promise_to_pay.py`, CRM referrals, and RLS migrations `0036` through `0040`. For each change, either add a coverage row or write one sentence that the change is outside freeze scope. Until that pass is written at the top of the coverage file, Phase 1 does not treat the 2026-09-16 map as current. `qos/journeys.yaml` and [TEST_CENSUS_LEDGER.md](../TEST_CENSUS_LEDGER.md) get the same check: a journey or workflow added in code after the ledger date is a Gap until a row exists.

**Step 1.1 — Freeze the surface from code.** Walk `web/src/navigation/menu.ts` and the router. For each item record route, page component, visibility function, and feature flag. Add deep links that are not in the sidebar: invoice edit, public pay, portal, lead form, invite, setup wizard, offline outbox, forbidden page. Update `PRODUCT_DISCOVERY.md` only as a working map that cites those files. Do not invent capabilities that are flag-off and absent from freeze scope.

**Step 1.2 — Bind flows to existing ids.** For each discovered screen, name the journey id or `WF-` id that already owns it. Where none exists, the row is a candidate Gap, not a new `WF-SALES-*` id. Rewrite `WORKFLOW_CATALOG.md` so every heading is a canonical id. Delete or archive headings that use another scheme.

**Step 1.3 — Re-read the open ledger rows in the table above.** Change the mark only when the test function is opened and the assertion is visible. A comment that mentions the feature is not a gate.

**Step 1.4 — Role matrix from code, not from the sidebar.** Read `CompanyUser.Role` and `capability_defaults_for_role` in `backend/accounts/models.py`, then the UI caps in `backend/tests/tenancy/test_fg2d_ui_caps.py`. `USER_ROLE_COVERAGE.md` lists, per role: default capabilities, screens the nav hides, and API verbs the RBAC matrix already denies. `POLICY_DESK` can manage policies and cannot post invoices, journals, trial balance, or imports.

**Step 1.5 — Confirm static guards still match the code.** Role list in the RBAC matrix equals `Role.choices`. UI-cap parser includes `POLICY_DESK` and `canManagePolicies`. `_migration_tables()` in `backend/tests/test_rls_coverage.py` unions `RLS_TABLES` from every module under `core/migrations` whose name contains `rls`. That includes `0036_rls_payment_promise` and `0037` through `0040`, not only files that match a narrower `NNNN_rls_<table>` pattern. Step 1.5 opens each of those five modules and checks that `RLS_TABLES` is defined and therefore included. A new company table missing from all of them is a Gap with a follow-up migration, not an edit to `0020`.

**Step 1.6 — Mark the root finding files.** Add a one-line header to each repo-root finding file: working note, not a source; defects count only after Phase 4 confirms them against a canonical id. Do not delete them in this phase. Do not treat their defect counts as the quality assessment.

**Phase 1 exit:** the coverage map has a reconciliation note newer than 2026-09-16 for the areas Step 1.0 names. Ledger marks for the fifteen rows above are updated with a file and function, or left Gap with the missing assertion named in one sentence. Each hold in section 0 still has its owner and revisit date.

---

## 3. Phase 2 — Select critical workflows from evidence, then map impact

Do not hard-code a private “top 10.” Rank from the ledger using business impact, money movement, tax, stock, permission boundary, and number of downstream readers.

### Automatic critical set for this product

These move money, stock, or tax, or they are the desks shipped after the freeze:

1. POS checkout and invoice complete (I1, I2).
2. B2B invoice draft → complete → stock down → GST → receivable.
3. Purchase inward → stock up → payable.
4. Receipt allocation against an invoice, including partial and advance.
5. Sales return / credit note, including batch and serial.
6. Credit-limit block on a trade order.
7. Period lock refusing a backdated complete.
8. GSTR-1 / GSTR-3B tie-out.
9. Quotation → sales order → delivery challan → invoice, where that chain is SUPPORTED.
10. Workshop job: spare plus labour, convert once, stock posts only on invoice complete.
11. Route stop: delivered requires a receiver name, and the slip does not post stock.
12. Project milestones to draft service invoices, close refused while a READY milestone is uninvoiced.
13. Policy issue once, renewal diary, claim, commission off the ledger (D17).
14. Vendor ticket share: owner only, invisible to the source company and to a third company.
15. Tenant switch and cross-company 404.

**Step 2.1 — For each of those fifteen, fill the golden-rule chain on one page.** Name the writer, the readers (stock, outstanding, dashboard, GST report, attention, PDF), and the role that must fail.

**Step 2.2 — Update `CROSS_FUNCTIONAL_IMPACT_MAP.md` from [CROSS_FLOW_IMPACT_MAP.md](../CROSS_FLOW_IMPACT_MAP.md).** New rows only for job card, milestone, policy, POD slip, and vendor share, and only for fields that exist on the models. A policy and a commission receivable do not get a journal row.

**Step 2.3 — Build the coverage matrix as ledger columns, not a new spreadsheet with blank Functional / UI / SLA ticks.** One row per journey id. Status is the ledger mark. “Missing coverage” is the sentence from Phase 1, not a checkbox grid that implies every dimension applies to every screen.

**Phase 2 exit:** each critical workflow names its journey id, its existing test or its missing assertion, and the other screens that must change when it writes.

---

## 4. Phase 3 — Execute through the real stack, in risk order

API persona tests run before browser goldens. A golden that only finds a heading will hide a wrong ledger.

### Environment

- Backend tests: `python -m pytest` from `backend/` with the repo virtualenv active. See “How to run Python” in section 0.
- `INVARIANTS_STRICT=1` on every sign-off run.
- Browser: the repo’s Playwright setup against Django for goldens. Vitest for component tests. Chromium is the promised browser. One mobile viewport pass on any new route. Record the exact browser and viewport on every UI defect.
- Postgres for races and RLS. The CI job is `postgres-rls`. SQLite is not evidence for those two.

**Step 3.1 — Money paths already marked Gated.** Re-run the owning workflow and persona tests. Independently compute one invoice: quantity × rate, discount, CGST/SGST or IGST from place of supply, round-off, outstanding after a partial receipt. Compare that figure to the document, the party ledger, and the report the impact map names. The application’s own total is not the expected value.

**Step 3.2 — Open Gaps from Phase 1.** For each row still Gap after the re-read, drive the behaviour once through the API using the existing persona fixture. Record pass, product defect, or ambiguous requirement. Do not add the permanent test until Phase 4; this pass is to learn which failure is real.

**Step 3.3 — Browser, only where a screen exists and the API day is already honest.** For each golden that the ledger cites (`workshop`, `route POD`, `projects`, `insurance`, `SaaS share and suspend`, plus the existing retail and trade goldens):

1. Sign in as the driving role.
2. Perform the business action (create, convert, deliver, issue, share, suspend).
3. Read the immediate UI result.
4. Reload, leave the page, come back, and read the same state.
5. Open the downstream screen (stock, invoice, ticket, campaign).
6. Sign in as the denied role, open the same URL directly, and confirm the refusal.
7. Record heading time. Compare to I1–I5 only when the action is one of those five. Otherwise write “SLA not defined” plus the elapsed time.

Exercise the flow. A single screenshot is not this step. Do not start this step on a golden whose page is in the middle of an unrelated UI refactor. Finish or pause that refactor first.

**Step 3.4 — Input and state, on the editors that post money.** For new invoice, POS line, purchase bill, and job line, run a short boundary set: empty required field, zero quantity, negative price, duplicate submit, complete twice, edit after complete, cancel after a downstream document exists. Map each result to an existing edge test. Add a test only when that file does not already assert it.

**Step 3.5 — Failure and recovery, on one money path and one sync path.** Interrupt invoice complete (validation error, then retry). Interrupt offline outbox sync and confirm the conflict spec’s outcome. Session expiry and logout on one deep link. Do not pull plugs on production. Local fault injection only, and only where `backend/tests/errors/` already has a pattern to extend.

**Step 3.6 — Accessibility on the cashier path and any new golden route.** In scope: keyboard to the primary action, visible focus, focus order, modal Escape, associated labels, and associated errors. `axe` in `web/e2e/a11y.spec.ts` is the automated half. The keyboard walk is the other half. Serious `axe` findings are defects.

Out of scope this cycle, and written that way on the scorecard: a screen-reader pass, and contrast. Contrast is not “pass” because nobody measured it. If a screen is already flagged, measure that screen and record the tool and the ratio. An unmeasured screen stays “not measured.”

**Step 3.7 — Permissions beyond the happy nav.** For `SALES_STAFF`, `VIEWER`, `POLICY_DESK`, and one other company: hidden nav item, direct URL, and the matching API verb. Refresh and browser Back after a 403. This is UI-path restriction testing. It is not a penetration test.

**Step 3.8 — Performance measurements that are allowed.**

Prerequisite **P-I4**, before any I4 cell is filled. As of 2026-09-27 there is no 5,000-SKU catalog-import fixture under `backend/tests/`. `test_b5_010_sales_register_rejects_unbounded_scan_over_threshold` in `backend/tests/test_ws08_report_performance.py` lowers a row cap because building thousands of real documents is too slow for that test. That pattern does not satisfy I4. P-I4 is a generated catalog CSV of 5,000 SKUs plus a timing test of the catalog import path, owned by QA. If P-I4 is not in the tree when this step runs, I4 is **unmeasured — fixture absent**. Do not time a smaller file and call it I4. Do not write “SLA not defined” for I4. The target exists. The measurement does not.

| Action | Compare to | If the measurement cannot be taken |
|---|---|---|
| POS barcode lookup | I1 ≤ 100 ms P95, Must protocol below | Unmeasured, with the reason |
| Invoice complete round-trip | I2 ≤ 800 ms P95, Must protocol below | Unmeasured, with the reason |
| A 50-row list | I3 ≤ 400 ms P95, Must protocol below | Unmeasured, with the reason |
| Catalog import | I4 ≤ 10 s P95 only after P-I4 | Unmeasured — fixture absent |
| PDF generation | I5 ≤ 2.5 s, Should protocol below, and only if the queue is what was measured | Unmeasured, with the reason |
| New desk heading | Record one elapsed time | SLA not defined. The 4 s check may stay as a smoke guard inside the spec that already uses it |
| Job, project, policy, shared-ticket lists | Query-count protocol in Step 4.3 | No latency SLA |

### Timing protocol

Must rows are I1, I2, I3, and I4. Should is I5. Other actions do not get a percentile.

1. Run on a machine that is not also running the full suite or another heavy job. Record OS, browser or API client, data volume, and whether the box was otherwise idle.
2. Discard the first run. It is warm-up and is not a sample.
3. Must rows: 20 samples after the warm-up. Sort them. P95 is the 19th value (`ceil(0.95 × 20)`).
4. I5: 10 samples after the warm-up. P95 is the 10th value (`ceil(0.95 × 10)`).
5. If one sample is greater than three times the median, record it in the notes and keep it in the set. Do not drop it to pass the target.
6. If the machine was under unrelated load, discard the whole set and rerun. Do not drop a single outlier and keep the rest.
7. One sample is a single elapsed time. It is not a P50 or a P95.
8. Do not claim CPU, memory, or load capacity from the browser tools.

**Step 3.9 — What stays out of this execution.** The holds table in section 0: multi-user load, k6 as a blocking gate, real GSP or payment-gateway sandboxes for WF-37 and WF-38, CA sign-off, screen reader, unmeasured contrast, Hindi copy completeness beyond money figures already covered, and thermal-printer hardware unless Step 1 marks it in scope.

**Phase 3 exit:** a working note per critical workflow with the golden-rule chain filled, elapsed times, and a classification: confirmed defect, requirement ambiguity, or coverage gap. Root `DEFECT_REPORT.md` is rewritten from those notes. Unconfirmed rows from the earlier draft are dropped. I4 is either a P95 against the 5,000-SKU fixture or the sentence “unmeasured — fixture absent.”

---

## 5. Phase 4 — Classify defects, then add tests in the existing suites

**Step 4.1 — Defect standard.** Each confirmed defect gets an id already used in this repo (or the next id in that scheme), the canonical journey or workflow, role, steps, expected business result, actual result, a severity from the rubric in section 0, and the test that will guard it. Performance defects include target, observed value, method, environment, data volume, repeat count, and whether the warm-up run was discarded. If section I has no row, the finding is “SLA not defined,” not a breach. If the row exists and the fixture or the run does not, the finding is “unmeasured,” not a breach and not a pass.

**Step 4.2 — Decide why a check failed before writing a test.** Product wrong, expectation wrong, requirement ambiguous, data invalid, environment wrong, or test unreliable. Ambiguous requirements go to the ledger as a note. They do not become an assertion that freezes the wrong rule.

**Step 4.3 — Place the test.**

| Kind of gap | Where it goes |
|---|---|
| Journey day, role denial, downstream read | Existing file in `backend/tests/personas/`. Function name contains the journey id. Docstring holds the golden rule. Money paths call `assert_consistent`. |
| Workflow chain already numbered | Existing `backend/tests/workflows/` module. No `WF-61`. |
| Boundary the product must keep refusing | A pin next to the existing boundary tests (`J-AMC-P9-VISIT`, `J-CARE-P10-TICKET`, WF-54). |
| Screen empty, error, and primary action | The page’s existing `*.test.tsx`. |
| Browser proof of a shipped desk | The golden that ledger already names. New goldens only for a desk that has an API day and no golden. |
| Keyboard and serious axe gaps | `web/e2e/a11y.spec.ts` or the POS keyboard spec. |
| Race on convert-once or issue-once | `backend/tests/edge/`, Postgres lane only. |
| A bug found while executing | `backend/tests/regression/` or the nearest regression module, red before the fix, then green. `guard_regression_corpus_grows` stays. |
| Query count on the four new lists | The protocol under this table. |
| I4 catalog import | The P-I4 timing test, only after the 5,000-SKU fixture exists. |

Query counts use `django.test.utils.CaptureQueriesContext`, the same shape as `test_b5_008_payables_aging_query_count_is_flat` in `backend/tests/test_ws08_report_performance.py`. Do not use `assertNumQueries` with a hardcoded baseline. The four lists are job cards, projects, policies, and shared tickets. For each list, capture the query count at 20 rows and again at 40 rows, and assert:

```text
len(large.captured_queries) <= len(small.captured_queries) + 2
```

The `+ 2` tolerance is the one that test already uses. Copy it. Do not pick a different tolerance per list. The assertion is that the count stays flat as the page of rows doubles. It is not a latency SLA.

**Step 4.4 — Performance assertion inside the functional test, only when a target exists.** I1, I2, I3, and I5 get an assertion against that target when the test can measure the same thing the SLA names, using the protocol in Step 3.8. I4 gets that assertion only inside the P-I4 test. Every other new test records elapsed time or the query-count comparison in the docstring or as a non-gating measurement, and the ledger says “formal SLA not defined.”

**Step 4.5 — Do not add.** Duplicate tests for rows moved to Reference in Phase 1. A query-count assertion on WF-01. A journal assertion for commission. A campaign engine for insurance. A pack test that expects `apply_pack("manufacturing")` to raise. A catalog-import timing test on fewer than 5,000 SKUs that claims I4.

**Phase 4 exit:** every in-scope Gap from Phase 1 either has a new or strengthened test, or a written hold (Blocked, Boundary, or requirement ambiguity) that still has an owner and a revisit date.

---

## 6. Phase 5 — Re-execute and regress

Run the narrow set first, then the fast lane. Both commands assume `python` is the virtualenv interpreter from section 0.

Persona and tenancy set, from `backend/` in PowerShell:

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings_test"
$env:INVARIANTS_STRICT = "1"
python -m pytest tests/personas/test_pj_workshop_job.py tests/personas/test_pj_route_pod.py tests/personas/test_pj_project_milestones.py tests/personas/test_pj_insurance_desk.py tests/personas/test_pj_saas_ops.py tests/workflows/test_wf_extended_stubs.py tests/tenancy/test_rbac_matrix.py tests/tenancy/test_fg2d_ui_caps.py tests/tenancy/test_endpoint_isolation.py tests/test_rls_coverage.py tests/test_roadmap_items.py -q --tb=line
```

The same command on a POSIX shell, which is also the CI shape:

```text
DJANGO_SETTINGS_MODULE=config.settings_test INVARIANTS_STRICT=1 python -m pytest tests/personas/test_pj_workshop_job.py tests/personas/test_pj_route_pod.py tests/personas/test_pj_project_milestones.py tests/personas/test_pj_insurance_desk.py tests/personas/test_pj_saas_ops.py tests/workflows/test_wf_extended_stubs.py tests/tenancy/test_rbac_matrix.py tests/tenancy/test_fg2d_ui_caps.py tests/tenancy/test_endpoint_isolation.py tests/test_rls_coverage.py tests/test_roadmap_items.py -q --tb=line
```

Add any file touched in Phase 4 to that command before the fast lane.

Fast lane:

```powershell
$env:INVARIANTS_STRICT = "1"
python -m pytest tests/workflows tests/tenancy tests/gst tests/snapshots tests/edge tests/errors tests/matrices tests/personas tests/regression tests/test_invariants_smoke.py -q --tb=line
```

Postgres RLS and the concurrency script stay on their existing jobs. They are not part of the fast lane. On Windows, run `scripts/test_concurrency_local.sh` from Git Bash against a Postgres `DATABASE_URL`, or run the pytest command that script wraps.

Frontend, from `web/`: the vitest files for pages changed in Phase 4, then the Playwright specs that were extended. For each golden that changed, repeat the browser walk from Step 3.3: act, reload, open the downstream screen, deny the other role.

A snapshot change in GST or report JSON needs a one-line reason. Job cards, policies, and POD slips must not appear in GSTR snapshots.

**Phase 5 exit:** the sign-off command is green with the invariant sweep on. A green run with the sweep off does not count.

---

## 7. Phase 6 — One more pass, then stop

Ask, against the ledger:

- Which open Gap was not executed?
- Which critical workflow was proven only at the API layer while a screen exists?
- Which total was copied from the API instead of calculated?
- Which of the eight roles never opened a direct URL?
- Which of I1–I5 has no measurement, and is the reason “unmeasured” or “SLA not defined”?
- Which new test would still pass if the stock movement or the journal were removed?

**Cap:** one additional pass, only on the rows those questions name. If that pass still finds confirmed defects or new in-scope Gaps, record them and stop. They are the input to the next cycle. Do not open a third pass inside this plan.

---

## 8. Phase 7 — Scorecard

Write `TEST_EXECUTION_REPORT.md` from the ledger, not from a test count. Update [TEST_CENSUS_LEDGER.md](../TEST_CENSUS_LEDGER.md) and [TESTING_STRATEGY.md](../TESTING_STRATEGY.md) §7 in the same pass. A row becomes Gated only when the test name cites the id and the assertion matches the business outcome.

Assess these separately. Each line gets Evidence, Known gaps, Observed risk, Remaining risk.

Some lines are expected to finish Partial or Blocked because section 0 already excluded the evidence. Write that expected mark first, so a thin row is not read as a missed measurement.

| Dimension | Expected mark this cycle | Why |
|---|---|---|
| Functional, business rules, calculations, data integrity, end-to-end, roles, negative, edge, cross-feature, regression, suite completeness | From the ledger, after Phases 4–6 | These are the cycle’s actual work |
| UI | Partial | Goldens and role boundaries, not every page |
| Security boundaries | Partial | UI path, API RBAC, tenant 404, Postgres RLS. Pen-test is Blocked on the holds table |
| Failure and recovery | Partial | One money path and one sync path |
| Performance | Partial | I1–I3 and I5 under the timing protocol. Query counts on four lists |
| SLA | Partial | I4 is unmeasured until P-I4 lands. Other actions say SLA not defined |
| Data-volume / scalability | Blocked | G-7. The 50k fixture is not a load result |
| Accessibility | Partial | `axe` plus the keyboard walk in Step 3.6. Screen reader is out. Contrast is “not measured” unless a flagged screen was measured |
| Compatibility | Blocked beyond Chromium | CI browser is Chromium. One mobile viewport on new routes. No multi-browser matrix |
| Localization | Partial | Money figures only where a Hindi money spec already exists. Full copy completeness is out |
| Integration | Partial | Contracted webhooks and OpenAPI. WF-37 and WF-38 stay Blocked |
| Reliability | Partial | Repeat the Must-SLA samples. No soak |

### Ready for this cycle when

- Money paths that completed end in `assert_consistent`, and the independent figure matches the document and the named report.
- Eight roles are in the API matrix. Direct URLs were tried for the roles Phase 3 lists.
- Cross-company reads return 404 at the app layer, and the Postgres RLS job is green.
- Policies, POD slips, shared tickets, and commission create no journal. D17 still says commission is off the ledger.
- WF-54 remains a limitation pin. WF-37 and WF-38 remain skipped, with the owner and revisit date from section 0.
- I1, I2, and I3 are measured with the Must protocol, or explicitly unmeasured with a reason. I5 uses the Should protocol or is explicitly unmeasured. I4 is either a 5,000-SKU P95 or “unmeasured — fixture absent.” Every other timed action says SLA not defined.
- No ledger row still says a shipped object is missing.
- The outside list is explicit and matches the holds table: G-7, G-14, pen-test, WF-37 and WF-38, field-network degradation, and any Gap left with a named reason, an owner, and a revisit date.
- Compatibility, localization, accessibility, and data-volume use the expected marks in the table above. They are not written up as if a full pass was planned.

Human gates stay human: pilot UAT, CA sign-off on F1–F8, and go/no-go signatures.

### Quality gate checklist

- [ ] Step 1.0 freshness note written on the coverage map
- [ ] Surface taken from `menu.ts` and the router, including token routes
- [ ] Flows use `WF-` and `J-` ids only
- [ ] Open ledger rows re-read and re-marked
- [ ] RLS modules `0036` through `0040` each define `RLS_TABLES` and are in the union
- [ ] Critical set executed past the screen into stock, tax, outstanding, or the named refusal
- [ ] One invoice total calculated independently
- [ ] Denied roles tried by direct URL
- [ ] I1–I3 and I5 follow the timing protocol; I4 is the 5,000-SKU fixture or an explicit unmeasured Gap
- [ ] Query-count tests use `CaptureQueriesContext` and the `+ 2` tolerance
- [ ] Defects use the P0–P3 / UX / SUGG rubric
- [ ] New tests live in existing suites and were re-run under `INVARIANTS_STRICT=1`
- [ ] Goldens that changed were clicked through, reloaded, and checked on the downstream screen
- [ ] Blocked and Boundary rows still say why, and each hold has an owner and a revisit date
- [ ] Phase 6 stopped after one pass
- [ ] Scorecard filled from ledger marks, with the expected Partial and Blocked rows filled in as such

---

## 9. Order of work

One QA engineer. Overlap with other roadmap work is fine after Phase 1. Do not run Phase 3 browser walks on screens that another stream is rewriting in the same week.

| Order | Phase | Calendar | Done when |
|---|---|---|---|
| 1 | Reconcile census and ids, including Step 1.0 | 2–3 days | Coverage map refreshed for post-2026-09-16 changes. The fifteen open rows have a real test citation or a one-sentence missing assertion |
| 2 | Impact map for the fifteen critical workflows | 2 days | Each names readers and the role that must fail |
| 3 | Execute API, then browser, on that set. P-I4 is the first 1–2 days of this phase if I4 is in this cycle | 5–7 days | Defects are confirmed or discarded. Timings follow the protocol. I4 is measured or explicitly unmeasured |
| 4 | Add or strengthen tests | 4–5 days | No in-scope Gap left without a test or a hold |
| 5 | Re-run narrow set, fast lane, touched goldens | 1–2 days | Sweep on, green |
| 6 | One capped pass | 2 days | No third pass. Leftovers listed for the next cycle |
| 7 | Ledger, §7, and scorecard | 1 day | Outside list matches the holds table, including expected Partial and Blocked dimensions |

About three weeks for one person. A slip in P-I4 does not extend Phase 6. It leaves I4 as an unmeasured Gap with owner QA and revisit 2026-10-31.

Start at Phase 1. A golden or a new persona file written before the ledger re-read will duplicate coverage the suite already has.
