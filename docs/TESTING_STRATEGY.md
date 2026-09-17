# Bizboard Testing Strategy — Persona-Centric, Evidence-Based

**Status:** Canonical testing strategy · **Created:** 2026-09-10 · **Owner:** QA + founder
**Scope:** Whole product — all 7 business archetypes, all 6 personas, SUPPORTED +
CONDITIONALLY SUPPORTED + demoted KNOWN LIMITATIONS.
**Relationship to other docs:**

| Doc | Role |
|---|---|
| [`BUSINESS_ARCHETYPES_AND_PERSONAS.md`](BUSINESS_ARCHETYPES_AND_PERSONAS.md) | *Who* we test for — archetypes, personas, buying roles, validation hypotheses H-01…H-05 |
| [`FREEZE_SCOPE.md`](FREEZE_SCOPE.md) | *What* is in scope — SUPPORTED / NOT SUPPORTED / KNOWN LIMITATIONS, frozen flag profile |
| [`FREEZE_SCOPE_COVERAGE.md`](FREEZE_SCOPE_COVERAGE.md) | *Line-item wiring* — each SUPPORTED item → its gating test or an explicit GAP |
| [`HOLISTIC_VALIDATION_REVIEW.md`](HOLISTIC_VALIDATION_REVIEW.md) | *Quality model* — one hierarchy; Flow / Impact / Truth graphs; product-truth vs capability; architecture-first sequence. Other docs are views of this model. |
| [`CROSS_FLOW_IMPACT_MAP.md`](CROSS_FLOW_IMPACT_MAP.md) | *Impact graph (Graph 2)* — writers and readers of shared state; evolving from field→readers to event→projections |
| [`COMPLETE_GATE_VISIBILITY_PLAN.md`](COMPLETE_GATE_VISIBILITY_PLAN.md) | *L6 Complete-gate class* — **CG-01…CG-37**: party + line present but Complete still blocked or silent; catalog in `web/src/completeGates/` |
| **this doc** | *How* we build confidence — layers **L1–L10**, the per-journey question set, the gap register, regression discipline, evidence/sign-off. The only layer numbering. |
| [`FULL_SPECTRUM_PERSONA_VALIDATION_PLAN.md`](FULL_SPECTRUM_PERSONA_VALIDATION_PLAN.md) | *L4 view* — persona × archetype index. T1–T7 maps onto L1–L10; not a second pyramid |
| [`Q-OS_QUALITY_PIPELINE_PLAN.md`](Q-OS_QUALITY_PIPELINE_PLAN.md) | *Quality output* — ranked backlog from evidence. Does not define test layers |
| [`pilot/UAT_CHECKLIST.md`](pilot/UAT_CHECKLIST.md), [`pilot/GO_NO_GO.md`](pilot/GO_NO_GO.md) | Human sign-off gates that consume this strategy's evidence |
| [`ca/CA_SIGN_OFF_CHECKLIST.md`](ca/CA_SIGN_OFF_CHECKLIST.md) | CA-blessed tax scenarios F1–F8, guarded by `guard_ca_tax_parity` |

`FREEZE_SCOPE_COVERAGE.md` is the authority for *per-item* status and must be
reconciled when chains land. This document is the authority for *method,
priorities, and gaps* and is reviewed at each phase boundary. Philosophy,
the three graphs, and the architecture-first sequence live in
[`HOLISTIC_VALIDATION_REVIEW.md`](HOLISTIC_VALIDATION_REVIEW.md) §0 — this
file implements them as L1–L10. Do not grow the persona suite by volume
until Graph 1 (generated flow catalog), Graph 2 (event × projection), and
Graph 3 (projection-identity registry) exist.

---

## 1. Why this document

Bizboard's test suite is its durable specification. The suite is already large
and layered (invariants, workflow chains, persona journeys, matrices, tenancy
sweeps, golden e2e, CI guards). What was missing was a single place that:

1. States the **method** — what each test layer proves and what it cannot.
2. Frames every important journey through the same **six** questions:
   **what should happen → what could go wrong → how we test it → what evidence
   proves it → whether it satisfies or delights the persona → where else it
   must be true, under what name, after the next event.**
3. Names the **gaps and weak assumptions** honestly and ranks them by
   impact × risk.
4. Defines a **regression strategy** that gives strong confidence without
   pretending every line must be individually tested.
5. Ties automated evidence to the **human sign-off gates** (pilot UAT, CA,
   Go/No-Go) and the **validation hypotheses** (H-01…H-05).

The goal is evidence-based confidence that the product is correct, resilient,
secure, usable, accessible, valuable, and pleasant for real Indian MSME users —
not a coverage percentage.

---

## 2. The confidence model

### 2.1 The ten test layers (L1–L10)

Each layer answers a different question. A claim is only "confident" when the
layers that *can* prove it agree, and at least one layer that *could have caught
a regression* exists.

| # | Layer | Question it answers | Lives in | What it **cannot** prove |
|---|---|---|---|---|
| L1 | **Invariants** (`core.invariants`) | Is the company's state *internally consistent* at rest, after any operation? | `backend/core/invariants/` — 18 registered `@invariant`s + 8 explicit callables; `assert_all_invariants(company)` | That the operation did the *right business thing* (only that it left nothing broken); mid-transaction states (opt out via `no_invariant_check`) |
| L2 | **Contracts** | Does one endpoint / envelope / serializer honour its promise (money as decimal strings, error → `HelpCode`, pagination caps, RBAC verb, tenant scope, security headers)? | `backend/tests/errors/`, `tests/tenancy/`, `tests/matrices/`, `test_money_contract.py`, OpenAPI snapshot diff in CI | That the contracts *compose* into a working flow |
| L3 | **Workflow chains** (`WF-01…WF-59`) | Does one business flow hang together end-to-end — draft → complete → stock ↓ → tax → GL balanced → AR/AP → allocation → reports agree? | `backend/tests/workflows/` (`workflow` marker); each ends in `cross_reconcile` + `assert_consistent` | That a *real role* can drive it, or that the UI exposes it |
| L4 | **Persona journeys** (`PJ-*`) | Can *this kind of user* at *this kind of business* run a normal day, seeing only what their role allows, leaving the books consistent? | `backend/tests/personas/` — 15 journeys across retail/trader/wholesale/service/migration × OWNER/SALES/ACCT/VIEWER/IMPORT/MIGRATOR | Frontend affordances; timing/latency; delight |
| L5 | **Matrices** | Does a *setting* or *place-of-supply* change behaviour the way the spec says, across the whole grid? | `tests/matrices/test_company_settings_matrix.py`, `test_gst_settings_matrix.py`, `tests/gst/test_place_of_supply_matrix.py` | Interactions outside the grid dimensions |
| L6 | **Golden e2e + FE** | Does the real browser against the real backend produce the deliverable (invoice PDF, isolation 404, role-hidden nav, no axe violations)? | `web/e2e-golden/personas-golden.spec.ts` (live Django+PG), `web/e2e/` (light, mocked), `web/e2e/personas/`, `web/e2e/a11y.spec.ts`, vitest units | Scale; network degradation; devices beyond Chromium; subjective friction |
| L7 | **Exploratory + pilot fieldwork** | Is it usable, fast, trustworthy, and *worth paying for* with real staff and real data? | `pilot/UAT_CHECKLIST.md`, `pilot/ARCH03_PILOT_RUNBOOK.md`, validation hypotheses H-01…H-05, CA sign-off | Nothing automatable replaces this; it is the top of the pyramid, not a nice-to-have |
| L8 | **Cross-flow state consistency** | When a flow writes a shared, mutable piece of business state (an invoice's status, a stock balance, a period-lock gate), do *all other* flows that read or must enforce that state still agree with it? | `docs/CROSS_FLOW_IMPACT_MAP.md` (the field-by-field fan-out registry — **Graph 2 reader index**) + `scripts/ci_gates/guards/guard_period_gate_coverage.py` (static enforcement-consistency guard) + `backend/sales/status_semantics.py` and `backend/purchases/status_semantics.py` (canonical predicates, closes CF-001 for sales and purchase invoices) + the regression tests each map entry cites | Interactions the map hasn't been extended to cover yet — it's seeded from fields that already caused a bug, not exhaustive by design (see the map's own "why this exists"). **Target:** event × projection matrix, not only field → readers. See `HOLISTIC_VALIDATION_REVIEW.md` §0.3 |
| L9 | **Lifecycle + time** | After create → pay → return → residual → report → attention, *and after the next event or close*, is the original business intent still represented on every user surface? | Lead-archetype UI goldens (ARCH-01, ARCH-03) — **not yet built**; P0 in `HOLISTIC_VALIDATION_REVIEW.md` | A single-flow chain (L3) or an API persona day (L4). Does not prove historical truth after a later event |
| L10 | **Projection identity** | Do independently computed surfaces of the *same named metric* agree? Do two *different* metrics avoid sharing a user-facing label? | Named identities in `backend/core/invariants/projection.py` (dashboard AR/AP = aging, stock available = on_hand − reserved, operational vs open-receivable sets, PDF snapshot vs live outstanding, bank-recon match_status). `reports.cross_reconcile` is registered and gated on `accounting_enabled` — GL-report agreement only; document identities stay in `projection.py` | That the user would *act* correctly on the number (decision quality stays L7 + attention assertions) |

L1–L7 each ask "does this one flow work?" L8 asks: **when this flow changes shared state, does every other flow's *interpretation* of that state still match?** L9 asks whether **intent survives the loop and the next event**. L10 asks whether **the same named metric is one number everywhere**. G-17 through G-22 (§7) are L8 failures; G-17's "Paid" badge is also an L9/L10 product-truth failure — no lower layer could have caught it because each reader's own tests only exercised the inputs its author thought to write. L8 is still light-touch relative to L1–L7 until the event catalog exists — see `HOLISTIC_VALIDATION_REVIEW.md` §0.8 (architecture first). T1–T7 in the persona plan **map onto these layers**; they are not a second pyramid.

**Strict sweep.** `INVARIANTS_STRICT=1` runs L1 in a `pytest_runtest_call`
hookwrapper after **every** test in the suite, not just the invariant tests — so
any test that leaves a company inconsistent fails, wherever it lives. This is the
single highest-leverage safety net and is **blocking** in CI (`invariant-sweep`
job) in both fixed and randomised order.

### 2.2 The six questions (apply to every important journey)

For each persona × archetype journey and each cross-cutting concern, answer:

1. **Should** — what is the correct outcome (state, numbers, documents, timing)?
2. **Go-wrong** — the realistic failure modes: wrong maths, lost data, race,
   permission leak, confusing dead-end, slow path, silent partial success.
3. **How** — which layer(s) test it, and the concrete test id / file.
4. **Evidence** — the artifact that proves success: a green invariant, a blessed
   snapshot, a PDF text match, a reconciliation delta of zero, a CA signature, a
   pilot metric against an H-0x threshold.
5. **Delight** — does the persona feel fast, confident, unsurprised, and
   unanxious? What measurable proxy stands in for that (keystroke count, seconds
   to complete, modal count, "did the clerk touch the mouse")?
6. **Where else / under what name / after the next event** — which other
   projections (stock, GL, AR/AP, GST, dashboard, attention, badge, channel)
   must tell the same story; whether two metrics share a label; whether a
   later return, residual, or period close still leaves historical truth intact.
   This is the product-truth question (`HOLISTIC_VALIDATION_REVIEW.md` §0).
   A journey that cannot name its Graph 2 cells is not gated.

Sections 4 and 5 apply this lens. Where question 5 or 6 has no measurable proxy today,
it is logged as a gap in §6.10 and §7.

### 2.3 What "done" means for a claim — the evidence ledger

A SUPPORTED capability is **gated** only when a *merge-blocking* test would go red
if the behaviour regressed. `FREEZE_SCOPE_COVERAGE.md` marks each item:

- ✅ gated — blocking test asserts it
- 🟡 partial — covered, but a stated sub-case is not asserted
- ⛔ GAP — SUPPORTED but nothing gates it
- 🚫 blocked — needs an external dependency (sandbox creds, WSL, real broker)

This strategy adds one rule: **every 🟡/⛔/🚫 must appear in the §7 register with
an owner and a target phase.** No silent gaps.

---

## 3. Quality dimensions → coverage map

The 14 dimensions from the testing master prompt, mapped to Bizboard's current
assets and status. "Status" is a judgement of *confidence*, not of effort spent.

| Dimension | What "good" looks like here | Current assets | Status | Gap ref |
|---|---|---|---|---|
| **Personas & archetypes** | Every archetype's core loop has a persona journey at L4; disposition (SUP/COND/OUT/deprioritized) is explicit | `PJ-*` (see `FULL_SPECTRUM_PERSONA_VALIDATION_PLAN.md`; manufacturing/payroll/CRM tagged `dark_module` and **do not count toward freeze coverage**). Route coverage counts come from generated `docs/FLOW_CATALOG.md`, not a hand-typed file/test tally. `BUSINESS_ARCHETYPES_AND_PERSONAS.md` §6–§8 | ✅ — retail/trader/wholesale/batch/serialized/contractor/manufacturing/migration covered; ARCH-07 milestone/job-work out of scope by design; G-1 and G-2 both closed | — |
| **End-to-end journeys** | Happy + alternate + failure + recovery per loop | `WF-01…WF-59`, `PJ-*`, `tests/edge/` | 🟡 — happy paths strong; recovery paths partial (H9 amend ✅, cancellation ✅, offline conflict ✅; payment-gateway refund/MDR 🚫 D3 creds) | G-3 |
| **Functional correctness** | Unit + contract + chain + regression, all green in CI | vitest (279), `pytest` (~1477 pass), `tests/regression/` corpus | ✅ | — |
| **Multi-user & permissions** | RBAC matrix + per-persona API deny-set + UI hides denied actions + tenant isolation on every endpoint | `tests/tenancy/test_rbac_matrix.py`, `test_endpoint_isolation.py`, `*_boundary` journeys, `web/e2e/personas/role-boundaries.spec.ts` | ✅ — API + FE OWNER/VIEWER/SALES/ACCT live (`role-boundaries.spec.ts`; G-4) | — |
| **UX & usability** | Discoverability, low cognitive load, feedback on every action, no dead 403 buttons | `web/e2e/personas/`, `HelpErrorAlert.test.tsx`, `validation-parity.spec.ts`, `route-smoke.spec.ts`, Complete-gate catalog (`COMPLETE_GATE_VISIBILITY_PLAN.md`) | 🟡 — G-5 route-smoke ✅; Complete-gate CG-01–CG-37 gated | G-16, G-complete-gate |
| **Accessibility** | axe clean on key screens; keyboard-only journeys; AT scenarios for POS + invoice | `web/e2e/a11y.spec.ts` (login, dashboard, invoice form, POS, a report, a settings screen — wcag2a/2aa, serious/critical = 0) plus accessible-name rules on login/dashboard/POS/invoice; route-smoke axe on top-20 desktop; `pos-keyboard-checkout.spec.ts` (chromium, 2026-09-15) | 🟡 — automated keyboard POS ✅ (G-6b); live H-02 still L7 | G-6, G-6b |
| **Performance & scalability** | Query-count flat as rows grow; report/list latency budget; 100k-invoice company; degraded network | `test_ws08_report_performance.py` (N+1 guards), `test_qos0003_large_tenant_reports.py` (50k-invoice tenant, hard-cap + flat-query proof, 3/3 local), `load-harness` CI job **executes** `load/k6_smoke.js` against a seeded Postgres tenant (thresholds: p95<2s, error rate<5%) | 🟡 — large-tenant query behavior proven locally; k6 smoke is written+advisory, **first real CI run unconfirmed** (QOS-0003); no staged 50k-tenant SLO run (`k6_slo.js`) or degraded-network journey; C7 defers the SLO soak to Phase 5 | G-7 |
| **Security, privacy & trust** | Tenant isolation, IDOR, path traversal, webhook signature, PII masking, audit immutability, injection guard, headers, boot-time secret checks | `tests/tenancy/`, `tests/errors/test_freeze_gate_contracts.py`, `test_payment_webhook_adversarial.py`, `test_llm_injection_guard.py`, `test_erasure.py`, `test_sprint0_security.py` | 🟡 — in-app ✅ including CSP header + webhook enumeration (G-8); **external pen-test = Phase 5** | G-9 |
| **Reliability & resilience** | Failure → visible state (never stuck/500), retry, idempotent replay, backup/restore round-trip, kill-switch | `tests/errors/test_async_task_state.py`, `test_backup_restore_drill.py`, `test_ops_contracts.py`, `test_wf51_idempotency_contract.py` | 🟡 — effects + beat dry-run + PDF FAILED→READY asserted in eager mode; **real-broker ordering = Phase 5** | G-10 |
| **Data & state integrity** | Balances derive correctly, transitions legal, persistence survives restart, migration/cutover clean, no corruption under concurrency | L1 invariants, `PJ-MIGRATION-*`, `reports.opening_ties_out`, `test_concurrency_races.py` (Postgres) | 🟡 — at-rest consistency ✅; concurrency Postgres-only (G-11a documented); synthetic G-11b rehearsal sweep in; **real anonymised dump = 95** | G-11 |
| **Cross-platform / environment** | SQLite(local) vs Postgres(prod) parity; browser matrix; mobile shell; Docker image runs | CI runs `backend`/`invariant-sweep`/`e2e-golden` on Postgres 17; `docker` job (compose config, hadolint, trivy); `mobile` + `mobile-apk` + `mobile-emulator-smoke` (advisory); WebKit scoped to a11y / role-boundaries / mobile-layout | 🟡 — goldens Chromium; mobile LIM accepted (G-12); local dev still SQLite; WebKit goldens = V9 | G-12 |
| **AI-specific quality** | Extraction failure → draft-with-warning not crash; cost ceiling; prompt-injection inert; grounding | `tests/errors/test_llm_extraction_failures.py`, `test_llm_injection_guard.py` (D14); FE injection warning (SR-23) | ✅ for failure + injection; ⛔ no accuracy/grounding benchmark (AI insights are `ENABLE_AI=0` — out of scope) | G-13 |
| **Business outcomes & compliance** | GST splits correct, TB=0, GSTR-1↔3B tie-out, period lock, CA accepts worksheets, dashboard KPI == drill-down | `tests/snapshots/test_gstr1_json.py`/`_gstr3b_json.py`, `test_wf27_gstr1_3b_tie_out`, `guard_ca_tax_parity` (F1–F8), `reports.cross_reconcile` | 🟡 — computation ✅; **CA acceptance (H-05) untested until pilot**; KPI==drill-down partly in `cross_reconcile` | G-14 |
| **Experience & delight** | Speed, predictability, reduced anxiety, minimal friction — with measurable proxies | H-02 (POS ≤35s) on live `pos-golden-path.spec.ts`; keyboard-only mocked `pos-keyboard-checkout.spec.ts`; H-03 / offline copy tests; dashboard heading budget `dashboard-budget.spec.ts` | 🟡 — automated proxies exist; live shop H-02/H-03 remain L7 | G-15, G-16 |

---

## 4. Personas — goals, delight, risk, coverage

Ground truth for roles: `CompanyUser.Role` + `capability_defaults_for_role`.
Journey matrix and deny-sets: `backend/tests/personas/README.md`.

### P1 — The Managing Proprietor ("Sethji") · *Economic buyer + often sole operator*

- **Goal / success criteria:** sees cash and credit position at a glance; trusts
  the numbers; believes staff cannot quietly steal or corrupt the books; no fear
  of lock-in or data loss.
- **Should:** every figure on the dashboard reconciles to a drill-down; closing a
  period actually locks it; an export gives back everything.
- **Go-wrong:** dashboard KPI diverges from the list behind it; a back-dated
  entry slips into a closed month; export misses a table; "delete company" leaves
  orphans or, worse, takes statutory docs with it.
- **How:** `PJ-*-OWNER` (retail/trader/wholesale/service), `PJ-WHOLE-ACCT`
  (period close is Owner-only, back-dated posting rejected), `test_wf31/wf44`,
  `reports.cross_reconcile`, `PJ-MIGRATION-*` (export → wipe → restore in
  `test_backup_restore_drill.py`), `test_erasure.py` +
  `tenancy.no_orphans_after_erasure` (WF-59).
- **Evidence:** green `cross_reconcile` (TB balanced, P&L == TB income−expense,
  BS equation), a closed-period `403/business-rule` on back-date, a restore that
  passes `assert_all_invariants`, an erasure that leaves zero orphans and keeps
  the tombstoned statutory set.
- **Delight:** *gap* — no automated "dashboard renders in < X ms with N months of
  data" check (G-15). Pilot proxy: proprietor can answer "who owes me money?" in
  one screen without help.

### P2 — The Counter Clerk ("frontline billing operator") · *daily end user, ARCH-01*

- **Goal / success criteria:** clears the queue fast; keyboard + scanner only;
  end-of-day till matches with no drama.
- **Should:** F2 barcode → tax-inclusive price resolves → single-action complete
  posts invoice + receipt + 100% allocation + stock movement + balanced journal →
  silent thermal slip.
- **Go-wrong:** search steals focus; modal popup blocks the next scan; input
  latency; a scanner double-fire creates two lines; offline drop loses the sale
  or duplicates it on reconnect.
- **How:** `test_wf19_pos_checkout`, `PJ-RETAIL-OWNER` / `PJ-RETAIL-SALES`
  (+ boundary deny-set: no cancel, no reports, no import, no journals),
  `web/e2e/personas/` for POS route reachability, offline: H-3 hypothesis +
  `web/e2e/personas/offline-outbox-conflict.spec.ts` ("Queued to sync" /
  "Rejected: …" / no auto-retry / discard confirms).
- **Evidence:** POS chain leaves `cross_reconcile` clean; outbox flush is
  idempotent (zero duplicate invoice numbers, zero double stock hits).
- **Delight:** **H-02** — 90% of 5-line checkouts ≤ 35 s, clerk never touches the
  mouse; **fail** if mouse-revert > 20% of lines. *Gap:* this is a pilot
  measurement, not an automated Playwright timing assertion (G-16).

### P3 — The Traveling Order Booker ("field sales rep") · *mobile/field user, ARCH-03/04*

- **Goal:** accurate stock and price on the road; book an order on the spot;
  understand why a customer is credit-blocked.
- **Should:** product lookup is company-scoped and current; quotation with slab
  price converts to order → challan → invoice; credit-limit breach is explained,
  not a silent failure.
- **Go-wrong:** stale price list on device; order booked against a customer over
  limit with no signal; offline order lost; sees another tenant's product.
- **How:** `PJ-TRADER-SALES` boundary (products `?search=` allowed, financial
  reports / import / inventory-manage denied), `test_wf06_quotation_to_invoice`,
  credit-limit path in `test_wave15_credit_limit_refund.py`, tenant scoping in
  `tests/tenancy/`.
- **Evidence:** cross-tenant product read → 404; credit-block returns a
  `HelpCode` the FE renders (`HelpErrorAlert.test.tsx`).
- **Delight:** *gap* — no field-network-degradation test (G-7). Mobile shell
  offline covers POS only (D12 pilot condition), not order booking.

### P4 — The Physical Stock Handler ("Godown custodian") · *logistics operator, ARCH-04/05/06*

- **Goal:** fast, unambiguous inwarding; batch/serial entry that isn't
  soul-crushing; count checks that reconcile.
- **Should:** typed append-only movements; balance row == Σ movements for every
  (item, godown, lot) at all times; FEFO picks earliest expiry; expired stock is
  blocked when the policy is on; inter-godown transfer nets to zero.
- **Go-wrong:** a raw `unit_cost` write bypasses `stamp_cost` and silently
  corrupts running cost / COGS / valuation / GL; transfer leaves stock in limbo;
  expired lot ships; serial reused.
- **How:** invariants `inventory.balance_equals_movements`,
  `running_cost_qty_matches_movements`, `no_expired_issue_when_blocked`,
  `transfer_pairs_net_zero`, `serial_traceability`, `batch_tenancy_consistent`;
  `guard_no_raw_unit_cost_update` (static, CI-blocking, self-tested);
  `test_wf21_stock_transfer_between_godowns`, `test_wf22_stock_adjustment_writeoff`,
  `test_wave15_fefo.py`, `test_pr5_returns_serials_fefo.py`,
  `PJ-WHOLE-OWNER` (multi-godown day).
- **Evidence:** every strict-sweep test re-checks these invariants; a broken
  journal / sequence gap is provably caught (`test_invariants_smoke.py`).
- **Delight:** **H-04a** (100% non-manual dispatches earliest-expiry-first),
  **H-04b** (100% expired-invoice attempts rejected under active policy).
  *Gap:* "manual serial typing fatigue" and "bulk scanner paste" ergonomics are
  ARCH-06 pilot boundary conditions, not automated (G-2).

### P5 — The Resident Bookkeeper ("Munshi") · *daily power user + operational gatekeeper, ARCH-03/04/05*

- **Goal:** ledgers that always balance; clean supplier bills; painless
  allocation; agreement with the bank statement.
- **Should:** derived customer/supplier ledgers reconcile to AR/AP control (no
  ledger tables); partial multi-invoice allocation never creates orphan
  balances; bank receipt posts to the per-instrument child ledger; bad-debt
  write-off hits GL correctly; bank-statement import matches and replays
  idempotently.
- **Go-wrong:** allocation rounding leaves a phantom balance; over-allocation
  accepted; a completed-doc money edit goes unlogged; import double-posts.
- **How:** `gl.party_subledger_complete`, `test_wf39_advance_payment_on_account`,
  `test_wf40_bad_debt_writeoff`, `test_wf26_bank_receipt_to_gl`,
  `test_wf41_bank_statement_import_and_matching`, `test_payment_allocation.py`,
  `test_refund_allocation_invariants.py`, `PJ-TRADER-ACCT` / `PJ-WHOLE-ACCT`,
  `audit.money_mutations_logged`.
- **Evidence:** subledger invariant green after 100 allocations (the H-01
  threshold, run in a chain); zero unexplained balance deltas.
- **Delight:** **H-01** — zero unexplained discrepancies across 100 consecutive
  allocations; **fail** on ≥1 corrupted balance needing DB surgery. *Gap:*
  "discrepancy with bank lines" is the Munshi's veto trigger — bank rec proper
  (`WF-33`) is 🟡 skipped; only statement-import matching (`WF-41`) is gated
  (G-3).

### P6 — The External CA / Tax Practitioner · *ecosystem influencer + statutory gatekeeper*

- **Goal:** file GSTR-1 / GSTR-3B straight from Bizboard worksheets without
  recalculating; a Trial Balance that ties; past periods that cannot be tampered.
- **Should:** GSTR-1 outward splits and HSN summary correct; GSTR-1 ↔ GSTR-3B
  tie out; TB = 0 across the FY boundary; closed period rejects back-dated
  posting; Tally export is well-formed.
- **Go-wrong:** tax split mismatch (POS vs place-of-supply), imbalanced journal
  in a corner case, a "correction" that doesn't net to zero, a silently editable
  past period.
- **How:** `tests/snapshots/test_gstr1_json.py` / `test_gstr3b_json.py`,
  `test_wf27_gstr1_3b_tie_out`, `tests/gst/test_place_of_supply_matrix.py`,
  `test_wf44_invoice_amendment_h9` (reverse + re-post nets to zero, stock
  immutable), `test_wf31_financial_year_close`, `guard_ca_tax_parity` (F1–F8
  CA-signed scenarios must keep their automated case in
  `tests/fixtures/tax_parity_cases.json`).
- **Evidence:** blessed GSTR JSON snapshots; `guard_ca_tax_parity` red on drift;
  H9 GL delta + `AMEND` audit event.
- **Delight / acceptance:** **H-05** — CA files client returns directly from
  Bizboard worksheets without recalculation; **fail** on rejection for mismatched
  splits or imbalanced books. This is the single most important **untested**
  claim (G-14); Stage 3 pilot, aligned to a real 1st–20th filing window.

---

## 5. Business archetypes — journeys, risks, coverage

Disposition per `BUSINESS_ARCHETYPES_AND_PERSONAS.md` §8 and `FREEZE_SCOPE.md`.
Each row of the "loop" is tested with the five-question lens; only the
non-obvious go-wrong / evidence points are called out.

### ARCH-03 — Semi-Wholesaler & Trade Merchant · **LEAD PILOT · SUPPORTED**

The full B2B loop: `PurchaseInvoice → (stock + AP atomic) → Quotation → SalesOrder
→ DeliveryChallan → SalesInvoice → derived AR → CustomerReceipt → PaymentAllocation
→ statement → period close → GSTR worksheets`.

| Step | Go-wrong | How / evidence |
|---|---|---|
| Purchase complete | stock ↑ without AP ↑ (or vice-versa) | `test_wf04_purchase.py` + `test_a2_posting_atomicity.py`; `gl.journals_balanced` |
| Quotation → order → challan → invoice | price slab lost on conversion; challan double-bills | `test_wf06`, `test_next_batch_so_challan.py`, `PJ-WHOLE-OWNER` |
| Credit / overdue audit | over-limit order booked silently | `test_wave15_credit_limit_refund.py` — breach returns explained `HelpCode` |
| Derived AR ↑ | balance table drift (there is none — derived) | `gl.party_subledger_complete` |
| Receipt + allocation | orphan balance, over-allocation | H-01 threshold; `test_payment_allocation.py` |
| Period close + GSTR | tax split / tie-out mismatch | `test_wf27`, GSTR JSON snapshots, `guard_ca_tax_parity` |
| TCS 194Q / TDS 206C | explicit withholding vs rate-derived | `test_wf34/wf35/wf36`; explicit amount overrides rate, **both logged** |

- **Coverage:** ✅ strongest in the product. `PJ-TRADER-*` covers all 5 roles.
- **Delight:** desktop, A4 printer, no queue pressure — lowest operational
  friction by design. *Gap:* no "complete loop under a flaky connection" test
  (G-7); dunning **send** is share-link only (schedule logic gated by
  `test_wf42`, delivery is a stated LIM).
- **Pilot limitation:** RCM (D8) — merchants with material GTA/legal/security
  RCM exposure are screened out or record the self-invoice + ITC manually;
  `test_wf55` keeps computation-path regression only.

### ARCH-01 — Fast-Paced Counter Retailer · **PARALLEL PILOT (Stage 1) · SUPPORTED**

The rapid POS loop (see P2). Loop atoms asserted individually in
`test_wf19_pos_checkout`: invoice COMPLETED, receipt POSTED, allocation 100%,
`StockMovement` SALE(−qty), balanced journal, then `cross_reconcile`.

- **Go-wrong (product-level):** thermal PDF path unavailable → must degrade, not
  block; shared-device offline drafts are plaintext and wiped on sign-out (C5) —
  the risk is *accepted and disclosed*, and the test is that sign-out **does**
  wipe them.
- **Coverage:** ✅ backend chain + `PJ-RETAIL-*`. 🟡 FE POS keyboard journey.
- **Delight:** **H-02**. Friction points to watch (from the archetype matrix):
  modal popups, slow print render, keyboard focus loss — none has an automated
  regression guard yet (G-16).

### ARCH-04 — Multi-Godown Regional Stockist · **CONDITIONALLY SUPPORTED**

- **Boundary:** single GSTIN; inter-branch transfers are internal stock moves,
  not cross-registration supplies.
- **Should / evidence:** `inventory.transfer_pairs_net_zero`,
  `StockCountSession` variance adjustment reconciles,
  `PJ-WHOLE-OWNER` (3 godowns), location-tagged challans.
- **Go-wrong:** in-transit stock counted twice or lost; count-session variance
  posts to the wrong account.
- **Gap (G-1):** no dedicated `PJ` for a *Godown-Keeper* persona at a
  departmental (Model D) firm; count-variance edge cases are in `tests/edge/`
  but not a persona journey.

### ARCH-05 — Batch & Expiry-Sensitive Stockist (Pharma/FMCG) · **CONDITIONALLY SUPPORTED**

- **Boundary:** general batch/FEFO works; statutory drug forms (20B/21B), FSSAI
  declarations absent → **Stage 4, needs product work**.
- **Should / evidence:** mandatory batch + mfg + expiry on every inward; **H-04a**
  FEFO order; **H-04b** expiry block; `inventory.no_expired_issue_when_blocked`;
  credit notes tagged sellable vs damaged.
- **Go-wrong:** manual expiry entry fatigue → wrong dates → bad FEFO; expired lot
  dispatched under a policy the user thought was on.
- **Gap (G-2):** expiry-alert bands and "policy on/off" as a *matrix* dimension
  are not in `test_company_settings_matrix.py`; the guard-band ("near-expiry")
  case of H-04b needs an explicit parametrised test.

### ARCH-06 — High-Value Serialized Goods Dealer · **CONDITIONALLY SUPPORTED**

- **Boundary:** serial lifecycle (`AVAILABLE → SOLD → RETURNED`) verified; bulk
  scanner-paste workflow limits apply.
- **Should / evidence:** `inventory.serial_traceability`; return validates the
  serial was actually sold; warranty lookup by serial.
- **Go-wrong:** duplicate-return fraud (same serial returned twice); inward bulk
  serial paste drops or dedupes silently.
- **Gap (G-2):** no test for bulk serial ingest partial-failure semantics; no
  warranty-fraud scenario (serial returned to a different customer / after
  warranty window).

### ARCH-07 — Light Commercial Service & Spares Contractor · **SECONDARY / partly OUT**

- **In scope:** mixed SAC (service) + HSN (goods) billing; service-only company
  shape (`PJ-SERVICE-OWNER`); place of supply by service location.
- **Out of frozen scope:** milestone billing, recurring retainers, job-work
  dispatch, technician timesheets → **no pilot, revisit as Stage 5**.
- **Go-wrong:** SAC vs HSN tax treatment confusion; TDS 194C/194J on collections
  mislogged.
- **Coverage:** 🟡 `PJ-SERVICE-OWNER` + `test_wf01`-style service line in
  `test_document_edge_cases.py` (service vs stock item). RCM common here — same
  pilot limitation as ARCH-03.

### ARCH-02 — Small Composition / Neighborhood Merchant · **SERVICEABLE, DEPRIORITIZED**

- Bill of supply (no CGST/SGST/IGST) + CMP-08 worksheet exist in code
  (`test_wf56_composition_bill_of_supply`, 🟡 LIM coverage, D9) but are **not
  freeze-gated** and the archetype is excluded from the pilot for low WTP / high
  churn. Keep the computation-path regression; do not spend journey-building
  bandwidth here.

### P6 CA audit journey (cross-archetype)

Not a business archetype but a **first-class journey**: given a closed accounting
month produced by a Stage 1–2 pilot, the CA pulls GSTR-1, GSTR-3B, TB, and the
sales/purchase registers and files without recalculation. Automated proxy today =
`guard_ca_tax_parity` + GSTR JSON snapshots + `test_wf27` tie-out. Human proof =
**H-05** in Stage 3.

---

## 6. Cross-cutting test domains

### 6.1 Multi-user, permissions, isolation

- **Model:** RBAC matrix (`tests/tenancy/test_rbac_matrix.py`) is the single
  source; drift fails CI. Every `PJ-*` re-asserts its persona's *positive* set
  and a curated *deny* set (401/403/404). `tenancy.*` invariants +
  `test_endpoint_isolation.py` (URL-conf parametrised) assert every
  list/detail/mutation endpoint is `company_id`-scoped; `test_wf28` interleaves
  two tenants.
- **Gap G-4:** **Closed 2026-09-13** (code) / **docs reconciled 2026-09-15**.
  FE role-hiding for SALES_STAFF / ACCOUNTANT is live in
  `web/e2e/personas/role-boundaries.spec.ts` (`loginAsSales` /
  `loginAsAccountant`). Do not re-open this as `test.fixme`.
- **Weak assumption:** app-layer scoping is the *only* isolation guarantee
  (`POSTGRES_RLS_ENABLED=0`). RLS job is advisory. Accepted for pilot; revisit
  before GA (defense-in-depth).

### 6.2 Data & state integrity

- **At rest:** L1 invariants + strict sweep — the strongest guarantee in the
  system. Numbering gap-free (`numbering.sequences_intact`, Rule 46(b)), with a
  red-then-green gap-detection test.
- **Transitions:** `test_status_machines.py`, `test_partial_closures.py`.
- **Migration / cutover:** `PJ-MIGRATION-TRADER` / `-WHOLESALE` —
  `reports.opening_ties_out`, import idempotency at scale, partial-failure
  resume, numbering continuity (first live invoice = old last + 1), redo path,
  cross-tenant safety. Export → wipe → restore round-trip in
  `test_backup_restore_drill.py`.
- **Gap G-11:** (a) `test_concurrency_races.py` is `postgres`-marked → **never
  runs on a local SQLite dev box**; a race regression is invisible until CI.
  (b) Schema-migration rehearsal: `scripts/migration_rehearsal.sh` applies
  migrate → synthetic seed → migrate-again (budget) → `check_invariants`
  (warning unless `INVARIANTS_STRICT_REHEARSAL=1`). A real anonymised dump
  remains P3 / 95.
- **Weak assumption:** running weighted-average cost ≈ perpetual FIFO COGS (C3).
  Cost is recomputable from movements; the *accounting difference* from true FIFO
  is disclosed internally but not quantified by a test.

### 6.3 Reliability & resilience

- **Covered:** async task failure → visible `FAILED` state + recovery
  (`test_async_task_state.py`, `test_webhook_and_async_contracts.py`);
  idempotent replay of any mutating call (`test_wf51`, `IdempotencyRecord`);
  recompute commands run twice = no-op (`test_ops_contracts.py`); feature-flag
  kill-switch; celery-beat registry importable + each beat task dry-run once
  (`test_every_beat_task_dry_runs_eager`); PDF fail → `FAILED` → regenerate
  `READY` (`test_failed_invoice_pdf_ends_FAILED_and_is_recoverable`).
- **Gap G-10:** real-broker task ordering (webhook vs period close) is hidden by
  eager mode → **Phase 5** run against a real broker. Retry → user-visible
  state is no longer the leftover; it is the PDF status test above.
- **Not tested (accepted):** infra-level — TLS termination (P0, ops-owned), DB
  connection limits, secret rotation (P5).

### 6.4 Security, privacy & trust

- **Covered:** cross-tenant read/IDOR → 404 (`personas-golden.spec.ts` vs live
  backend); path traversal / CRLF in `Content-Disposition` sanitised; adversarial
  payment webhook (`test_payment_webhook_adversarial.py`) — bad/missing signature
  → 400, replayed event id → no dup; PII masking in request logs (12-hex id
  hashes, no body/headers, no query string); audit log append-only (no
  Create/Update/Destroy mixin; write verbs 403/405); boot-time
  `DJANGO_FAIL_FAST_SECRETS` aborts on weak `SECRET_KEY` / prod misconfig;
  security headers present, no `Server` version leak; formula-injection
  sanitisation on CSV/XLSX export; LLM prompt-injection inert (D14); DPDP export
  = exactly one company's data.
- **Gap G-8:** **Closed 2026-09-13** (pointer 2026-09-15). Both inbound webhooks
  have signature verification, a forgery test, and `test_webhook_enumeration.py`.
  Live refund/MDR remains D3-creds (G-3 / A25), not this gap.
- **Gap G-9:** Django emits CSP (`test_api_response_carries_hardening_headers`).
  External pen-test remains Phase 5 (`pilot/PENTEST_SOW.md`).
- **Weak assumption:** offline drafts plaintext on device, wiped on sign-out
  (C5) — the *disclosure* is the mitigation; the test only proves the wipe
  happens.

### 6.5 Performance & scalability

- **Covered:** `test_ws08_report_performance.py` — query count stays flat as rows
  grow for payables aging and the other N+1 hotspots from the 2026-09-03 review
  (proves the loop was removed, not that the fixture is small).
  `test_qos0003_large_tenant_reports.py` (QOS-0003) builds a real 50k-invoice
  tenant and proves `sales_register`'s `MAX_REGISTER_ROWS_HARD_CAP` correctly
  refuses a full-year pull instead of silently materialising it, that a
  realistic month-window query is flat and fast at this scale, and that CSV
  export completes — 3/3 passing locally.
- **Gap G-7 (P1):** the `load-harness` CI job seeds a real Postgres tenant
  (`seed_demo`), boots the real Django backend, and **executes**
  `load/k6_smoke.js` (5 VUs × 30s: health, login, invoice list, create-draft)
  against real thresholds (`p95<2s`, error rate `<5%`) — this is more than a
  presence check, and closes the "cheap smoke-level executed k6 run" this row
  used to ask for; per QOS-0003 it's written and locally-reasoned-through but
  has not yet had its first real green run on CI (no k6 binary / GitHub
  Actions access from a local session to confirm). `load/k6_slo.js` (the X-01
  SLO scenario matching the adopted p95 table in `load/README.md`) is written
  and ready but has never been run — it needs a staging deploy, which doesn't
  exist yet. What's actually still open:
  - `load-harness`'s first real CI run hasn't been confirmed green (QOS-0003);
  - it runs `continue-on-error: true` (advisory, per
    `scripts/ci_gates/REQUIRED_CHECKS.txt`) — a threshold miss doesn't block
    a merge yet, and should stay advisory until a few consecutive green runs
    are observed;
  - no staged 50k-tenant SLO run (`k6_slo.js`) — the query-flatness/hard-cap
    behavior is proven (above), but real HTTP p95 under concurrency against
    that data volume is not;
  - no degraded-network journey (field sales, counter).
  C7 formally defers the staged SLO soak to Phase 5.

### 6.6 Accessibility

- **Covered:** `web/e2e/a11y.spec.ts` — axe (wcag2a/2aa) with zero
  serious/critical on **login**, **dashboard**, and (QOS-0007, added since
  this row was last written) **the invoice form, POS, a report, and a
  settings screen** — two real fixes shipped (WCAG 1.3.1 drawer-nav list
  semantics, `aria-progressbar-name`); a basic keyboard-operability check
  also exists for the POS scan field (`Tab` + type, no mouse).
- **Gap G-6 (residual — G-6b executed 2026-09-15):**
  - keyboard-only POS add → qty → pay-ready cart is green on chromium
    (`pos-keyboard-checkout.spec.ts`); live shop H-02 remains L7;
  - accessible-name rules on login/dashboard/POS/invoice (2026-09-15).

### 6.7 Cross-platform / environment

- **Covered:** CI runs the backend suite, invariant sweep, and golden e2e on
  **Postgres 17**; `docker` job validates compose + Dockerfiles + image CVEs;
  `mobile` job asserts Capacitor config + `allowBackup=false` + no hardcoded
  server URL; `mobile-apk` builds the pilot APK; `mobile-emulator-smoke`
  (advisory) runs login → invoice → offline draft → reconnect via Maestro.
- **Gap G-12:**
  - e2e goldens are **Chromium**; WebKit is scoped to a11y / role-boundaries /
    mobile-layout (not goldens — V9 only if founder asks);
  - two mobile-viewport cases are **accepted LIM** (2026-09-15):
    `help.spec.ts` skips UniversalSearch below `sm`; `item-custom-fields.spec.ts`
    skips `/sales/new` heading on the Pixel 5 project (occluded under AppBar);
  - local dev is still SQLite → parity relies entirely on CI;
  - mobile session-persistence / deep-link / offline-on-mobile is a partial
    "mobile test lane", emulator smoke is non-blocking.

### 6.8 AI-specific

- In scope only for **LLM bill extraction** (D14) as an *AI quality* dimension.
  `ENABLE_AI=0` puts **`/insights/*` LLM surfaces** out of scope.
- **`/attention`, dunning, payment-health, credit-hold, and dashboard KPIs are
  in scope independent of `ENABLE_AI`.** They are live decision surfaces, not
  AI features. Only `/insights/*` is OUT when the flag is off.
- **Covered:** provider timeout / 5xx / 429 / malformed JSON → job `FAILED`,
  never crash / silent partial; cost-ceiling assert; injected instructions in
  uploaded bill text are inert; FE surfaces the injection warning in the bill
  preview (SR-23).
- **Gap G-13 (P2):** no extraction-**accuracy** benchmark (a corpus of real
  bill images → expected field values, with a pass threshold). Without it,
  "extraction quality regressed" is invisible. Low priority while extraction is
  draft-with-review only.

### 6.9 Business outcomes & compliance

- **Covered:** GST computation (place-of-supply matrix, cess ad-valorem +
  specific, GSTR-1/3B JSON snapshots, GSTR-1↔3B tie-out), TB=0 and FY-boundary
  close, `guard_ca_tax_parity` binding F1–F8 CA-signed scenarios to
  `tax_parity_cases.json`, `reports.cross_reconcile` (TB ↔ P&L ↔ BS; dashboard
  KPI ↔ drill-down partially).
- **Gap G-14 (P0 for confidence, blocked on humans):** **H-05** — a practicing
  CA has not yet filed from Bizboard worksheets. Everything upstream is a proxy.
  Stage 3 pilot, aligned to a live filing window, is the only real evidence.
- **Gap:** HSN summary correctness in GSTR-1 is folded into `test_wf27` but not
  snapshot-pinned on its own.

### 6.10 Experience & delight — making it measurable

Today delight is asserted only as pilot hypotheses (H-02, H-03) and a few copy
tests. To make it a **regression-guarded** property:

| Proxy | Where it would live | Threshold source |
|---|---|---|
| POS 5-line checkout wall-clock, keyboard-only | Playwright golden, `performance.now()` around the flow | H-02: ≤ 35 s |
| Dashboard first-contentful render with 12 months of data | Playwright + a seeded large-ish fixture | new budget, e.g. ≤ 2 s p95 |
| Modal / focus-loss count during POS | Playwright: count `[role=dialog]` opened, assert focus stays in the scan field | 0 blocking modals |
| Error → actionable message | already: `HelpErrorAlert.test.tsx`; extend to every `HelpCode` family | 100% resolve to a help entry (`test_help_codes_live.py`) |
| Offline states legible | already: `offline-outbox-conflict.spec.ts` | copy contract |

These are **G-15 / G-16** in the register.

---

## 7. Coverage gaps & untested risks — ranked register

Ranked by **impact × likelihood**. "Blocked" = needs an external dependency, not
effort. Reconcile with `FREEZE_SCOPE_COVERAGE.md` "Open GAPs" when items close.

**CF-001 — shared-state semantic drift.** G-17 through G-20, G-22, and G-23
are not unrelated bugs; they are instances of one defect *class*: two
independent readers (or enforcers) of the same shared business state
quietly disagreeing about what it means, because each was written and
tested in isolation (G-21/G-22 are the sibling "gate enforcement" shape of
the same root cause). Treat new instances of this class as CF-001, not as a
fresh one-off gap. For `SalesInvoice` the class itself is now closed, not
just its individual instances — see §8, weak assumption 12 for the
canonical-predicate module that replaced the scattered status-set filters.

**Trust-breaking defects are P0/P1 regardless of code-change size.** Any
defect that can produce wrong money, wrong tax, wrong stock, wrong
customer/supplier balance, unauthorized visibility, silent data loss, a
duplicate transaction, incorrect statutory output, a misleading business
insight, a false "Paid"/"Outstanding" state, or irreversible corruption gets
this classification the moment it's found, independent of how small the
underlying diff is to fix. G-17 is the canonical example: one line of wrong
precedence in a frontend helper, but it altered what a user believed about
their own money — that's why a unit-tested helper (§8, weak assumption 11)
wasn't sufficient evidence of correctness on its own.

| ID | Gap / risk | Impact | Likelihood | State | Proposed test | Prio | Owner |
|---|---|---|---|---|---|---|---|
| **G-14** | No CA has filed from the worksheets (H-05) | Critical — the core value prop | Unknown | Blocked on pilot | Stage 3 fieldwork, live filing window, 3–5 CAs | **P0** | founder / pilot |
| **G-4** | FE role-hiding for SALES / ACCT | High — a dead 403 button erodes trust daily (P2/P5 veto) | Medium | ✅ (2026-09-13) | `loginAsSales`/`loginAsAccountant` and live (non-fixme) `role-boundaries.spec.ts` blocks already existed — the header comment was stale, not the code. The real gap was underneath: mock-mode `fetchCurrentUser()` (`web/src/api/auth.ts`) always returned `mockUser` (OWNER) regardless of who logged in, so AuthContext's boot-time "re-fetch me" silently reset every SALES/ACCT mock session back to OWNER on the next navigation — the PJ-SALES/PJ-ACCT spec blocks were passing vacuously (testing OWNER's permissions). Fixed: `fetchCurrentUser()` now resolves the mock persona from `getStoredUser()`'s email via a shared `mockUserForEmail()` helper (same convention `login()` already used). Regression: `web/src/api/auth.test.ts` (verified red-before-green). Full Playwright run not executable from this sandboxed session (Bash and the preview-server harness run in separate network sandboxes here) — run `npm run test:e2e -- e2e/personas/role-boundaries.spec.ts` to confirm PJ-SALES/PJ-ACCT pass for the right reason now | **P1** | web |
| **G-7** | Load/soak/large-tenant/degraded-network all absent | High — pilot "sized for small traders" is an untested assumption (C7) | Medium | 🟡 (scaffolded, not executed) | k6 scripts (`load/k6_smoke.js`, `load/k6_slo.js`), an advisory `load-harness` CI job (`.github/workflows/ci.yml`), a 50k-invoice bulk fixture, and a reusable `time.perf_counter()` budget-assertion idiom (all in `backend/tests/test_qos0003_large_tenant_reports.py`) already exist — verified 2026-09-13. What's actually missing is a **real budget number** from a staging-scale run (the one local run on record failed at 68% error/~9.3s p95 against a small local DB, which `load/README.md` already documents as expected, not a CI target) — not missing code. Once a real budget exists, flip `continue-on-error` off for `load-harness` | **P1** | backend / ops |
| **G-8** | Per-inbound-webhook signature verification not enumerated | High — one unverified webhook = forged financial events | Low–Med | ✅ (2026-09-13; pointer 2026-09-15) | Both inbound webhooks have signature verification, a forgery test, and `test_webhook_enumeration.py`. `test_wf17_gateway_webhook_capture_and_replay` is now a structural pointer at those files (no `assert True`, no skip). Live refund/MDR remains D3-creds 🚫 | **P1** | backend |
| **G-3** | Recovery paths partial: bank rec proper (WF-33), payment-gateway refund/MDR (WF-37/38) | High — Munshi & proprietor veto triggers | Med | ✅ WF-33 (2026-09-13) / 🚫 WF-37/38 | `test_wf33_bank_reconciliation` was already not skipped and passing (the module header claiming "each is skipped" was stale, now fixed). Idempotent-replay was already well covered for the idempotency-key path (`test_cr_017_bank_statement_commit_idempotency`); added the missing piece — a **bare** re-commit (no key) doesn't duplicate auto-match side effects, protected by both a code-level status check and a DB `OneToOneField` on `ReconMatch.line`: `test_phase3_payments.py::test_g3_bank_statement_bare_recommit_does_not_duplicate_auto_matches`. WF-37/38 remain genuinely blocked on D3 sandbox creds | **P1** | backend |
| **G-11a** | Concurrency races never run locally (Postgres-only) | High — oversell / double-allocation corrupt money | Low (CI covers) | ✅ (2026-09-15) | `CONTRIBUTING.md` verification table + concurrency-lane section name `pytest -m postgres` / `scripts/test_concurrency_local.sh` as required before allocation/stock/numbering/period-close changes | **P1** | backend |
| **G-6b** | No keyboard-only POS a11y journey | High for ARCH-01 (H-02 assumes it) | Med | ✅ (executed chromium 2026-09-15) | `web/e2e/pos-keyboard-checkout.spec.ts` — 3 SKUs keyboard-only, qty stepper via `increase quantity` aria-label, Cash pay-ready under 35s. Stops short of paid checkout (preview hits real backend). Live counter H-02 remains L7 | **P1** | web |
| **G-1** | No persona journey for Godown-Keeper at a departmental firm (Model D); ARCH-04 count-variance not a journey | Med | Med | ✅ (2026-09-12) | Closed by `PJ-WHOLE-GODOWN` = `tests/personas/test_pj_stubs.py::test_pj_wholesale_godown_custodian` (QOS-0008: inward, transfer, deny-set) + `tests/personas/test_pj_stock_audit_and_adjustments.py::test_pj_custodian_physical_stock_count_and_adjustments` (count session with variance). See `FULL_SPECTRUM_PERSONA_VALIDATION_PLAN.md` §7. | **P2** | backend |
| **G-2** | ARCH-05 near-expiry guard-band & policy on/off not a matrix dim; ARCH-06 bulk serial partial-failure & warranty-fraud untested | Med (Stage 4 archetypes) | Med | ✅ (2026-09-12) | Expiry-policy × guard-band axis — `tests/matrices/test_company_settings_matrix.py::test_expiry_guard_band_matrix` (tagged G-2/H-04b). Warranty-fraud — `tests/personas/test_pj_serialized.py::test_pj_serialized_lifecycle_and_warranty_fraud_guard`. Bulk-serial partial-failure — `tests/personas/test_pj_serialized.py::test_pj_bulk_serial_import_partial_failure_blocks_whole_job` (added 2026-09-12; bulk serial ingest is the `opening_serials` sheet on a PRODUCTS import — an earlier pass of this register incorrectly stated no such endpoint existed; it does, in `imports/services.py`, and PRODUCTS-kind commit is all-or-nothing, so the pinned behavior is "one bad row blocks the whole job," not a partial write). | **P2** | backend |
| **G-5** | Broad page-level UX (~90 pages) has ~1 smoke each at best | Med — friction compounds | High | ✅ (2026-09-15) | `web/e2e/helpers/protectedRoutes.ts` (20 freeze routes) + authenticated `route-smoke.spec.ts` (render, no error boundary, no console pageerror, axe serious/critical on desktop) and the unauthenticated twin. Long-tail settings stay LIM | **P2** | web |
| **G-9** | External pen-test; CSP was untested | Med | Low | 🟡 CSP gated (2026-09-15); pen-test Phase 5 | CSP header presence is `test_freeze_gate_contracts.py`. Pen-test = Phase 5 (`PENTEST_SOW.md`) | **P2** | ops |
| **G-10** | Real-broker task ordering hidden by eager mode | Med | Low | 🟡 | Phase 5: run WF-17 / period-close / e-invoice submit against a real broker | **P3** | backend |
| **G-12** | Chromium-only e2e; 2 mobile-viewport fails carried | Med | Med | 🟡 (mobile LIM accepted 2026-09-15; WebKit goldens = V9) | UniversalSearch skip below `sm` (`help.spec.ts`); `/sales/new` heading skip on Pixel 5 (`item-custom-fields.spec.ts`). Do not expand WebKit to goldens unless founder asks | **P3** | web |
| **G-11b** | No schema-migration rehearsal on a prod-shaped dump | Med | Low | 🟡 synthetic (2026-09-15) | `scripts/migration_rehearsal.sh` now runs `manage.py check_invariants` after migrate+seed. Synthetic bulk may be dirty — fails the script only when `INVARIANTS_STRICT_REHEARSAL=1`. Real anonymised dump remains the 95 bar. Pytest twin: `test_v3_g11b_export_migrate_restore_invariants` | **P3** | backend / ops |
| **G-13** | No LLM extraction accuracy benchmark | Low (draft-with-review) | Med | ⛔ | Corpus of ~30 real bills → expected fields → accuracy floor; advisory lane | **P3** | backend / AI |
| **G-15/16** | Delight has no automated latency/friction budgets | Med | High | ✅ automated proxy (2026-09-15) | `web/e2e/dashboard-budget.spec.ts` (heading ≤4s), `pos-friction.spec.ts` (no blocking modal, scan focus), `pos-keyboard-checkout.spec.ts` (H-02 35s keyboard cart). Live counter H-02 / H-03 remain L7 pilot | **P2** | web |
| **G-complete-gate** | Complete stays disabled (or fails) after party + line for a secondary reason, with a generic or missing explanation | High — clerk cannot finish a correct bill | High — sales/purchase `canComplete` has extra conjuncts that goldens skip | ✅ CG-01–CG-37 gated (2026-09-16) | Plan + catalog: [`COMPLETE_GATE_VISIBILITY_PLAN.md`](COMPLETE_GATE_VISIBILITY_PLAN.md). Named Complete reasons on sales/purchase/notes/POS/orders/returns; purchase GSTIN aligned with sales; notes preview fallback. Index: `web/src/completeGates/completeGateIndex.test.ts` | **P1** | web |
| **G-determinism** | `determinism-probe` advisory: 5 clock-brittle tests | Low | — | Advisory | Make the 5 fixtures' dates relative to `timezone.now()`; flip probe to blocking | **P2** | backend |
| **G-mutation** | Mutation audit blocked (mutmut = WSL/Linux only) | Med — line coverage ≠ behaviour coverage | — | Blocked (Windows) | Run `scripts/mutation_audit.sh` in a Linux CI lane (advisory), triage survivors on the money/tax/stock modules first | **P2** | backend |
| **G-17** | FE-computed display fields (status badges, derived flags) diverge from backend-authoritative state across status combinations; zero page-level render tests for status/history/detail screens | High — found live 2026-09-12: `paidAwareStatus()` checked `payment_state` before `status`, so a fully-returned invoice (auto-CN nets its balance to 0) rendered as "Paid," masking the return; `status.test.ts` only ever exercised `status='COMPLETED'` inputs, so the RETURNED×PAID combination was never hit | Med — recurs anywhere FE duplicates backend precedence logic instead of trusting one server-computed field | ✅ (2026-09-12) | Fixed the instance (`paidAwareStatus` gates on `status` first); added server-side `return_state` (NONE/PARTIAL/FULL) + `test_return_state_visibility.py`. Sibling bug fixed: `insights/alerts.py` `OPEN_SALES` wrongly included RETURNED (disagreed with `insights/services.py`'s own COMPLETED-only `OPEN_SALES` of the same name) — best-seller/fast-mover analytics counted reversed sales; regression pinned in `test_phase6_insights.py::test_low_stock_fast_mover_ignores_fully_returned_invoice` (verified red without the fix). Closed by page-level fixture-matrix render tests asserting visible badge text across status × payment_state × return_state: `SalesHistoryPage.test.tsx`, `InvoiceDetailPage.test.tsx`, `DashboardPage.test.tsx`, `PurchaseHistoryPage.test.tsx` (parity check — this list has no payment-state overlay to begin with). Traced further in `CROSS_FLOW_IMPACT_MAP.md`, which surfaced 3 more instances of the same shape — G-18/G-19/G-20 below | **P1** | web / backend |
| **G-18** | `PurchaseInvoice.status`: AP_DUE_7D alert (`insights/alerts.py::_ap`) and cash-flow forecast (`insights/services.py::forecast_cashflow`) filter `status=COMPLETED` only, excluding RETURNED — but `payables_aging`/dashboard/`LedgerService.purchase_invoice_outstanding` all treat RETURNED as balance-bearing | High — a fully-returned purchase invoice with a residual payable (partial-return/debit-note mismatch) silently never triggers an AP-due alert or shows in the 14-day outflow forecast, though it counts in payables totals | Med — same root cause as G-17, mirrored on the purchase/AP side | ✅ (2026-09-13) | Fixed: both filters now include RETURNED. Regression: `test_phase6_insights.py::test_g18_ap_due_and_cashflow_include_returned_purchase_with_residual_payable` — a real scenario (full return + post-return debit note leaves a genuine ₹50 residual payable), asserts `payables_aging`, `AP_DUE_7D`, and `forecast_cashflow` all agree | **P1** | backend |
| **G-19** | `StockBalance`: `DEAD_STOCK` alert (`insights/alerts.py:524-530`) money-values raw `on_hand` with no `reserved` subtraction, while `low_stock_alert_payload` and the health-score `stock_score` are both reserved-aware | Med — a SKU fully reserved against an open sales order (`available == 0`) can be flagged and money-valued as "dead stock" in the same breath other logic treats it as committed/unavailable | Low–Med | ✅ (2026-09-13) | Fixed: both the filter and the money-valuation now use `on_hand - reserved` (an `F()`-annotated `_available`), not just the valuation — a fully-reserved SKU no longer qualifies as a DEAD_STOCK candidate at all. Regression: `test_b05_attention.py::test_g19_dead_stock_ignores_fully_reserved_stock` (confirms a SKU reserved against a confirmed sales order) | **P2** | backend |
| **G-20** | `PaymentAllocation`: dunning (`payments/dunning.py::eligible_invoices`) filters `status=COMPLETED` only; the payment-health/UPI-reminder alert (`payments/services.py::_payment_health_uncached`) filters `status__in=(COMPLETED, RETURNED)` for the same underlying outstanding-balance question | High — a partially-paid invoice that later gets fully returned (still outstanding after auto-unallocate) shows as "needs attention" in the payment-health strip but never receives an actual dunning reminder | Med — same root cause as G-17/G-18, on the receivables-reminder side | ✅ (2026-09-13) | Fixed: `eligible_invoices()` now filters on `ledgers.services.OPEN_SALES_STATUSES` instead of `COMPLETED`-only. Regression: `test_a07_dunning.py::test_g20_eligible_invoices_matches_payment_health_for_returned_invoice` — a real scenario (partial payment, full return, CR-124 auto-unallocate nets to zero, then a post-return debit note leaves genuine residual AR), asserts the invoice is dunning-eligible | **P1** | backend |
| **G-21** | Period-lock gate (`assert_period_allows_money_amend`) not enforced: `purchases/grn_service.py::GoodsReceiptService.complete()`/`.cancel()` post valuation-carrying stock movements with no `gst_periods` import at all — sibling `PurchaseInvoice.complete()`/`.cancel()` gates consistently on `invoice_date` | Med — the underlying `StockMovement` always posts with today's date regardless (neither method passes `movement_date`), so the stock ledger itself can't be backdated; the real exposure is a GRN's own date/status changing a closed period's document/valuation picture after that period was filed | Low–Med | ✅ (2026-09-13) | Fixed: both methods now call `assert_period_allows_money_amend` on `grn.receipt_date` (`.cancel()` with `allow_soft_closed=True`, mirroring `PurchaseInvoice.cancel`). Regression: `tests/workflows/test_wf_grn.py::test_wf_grn_complete_blocked_in_soft_closed_period` / `::test_wf_grn_cancel_blocked_in_hard_closed_period`, both verified red-without-the-fix (temporarily reverted, confirmed failing, restored). Now also covered structurally by `guard_period_gate_coverage` | **P2** | backend |
| **G-22** | Period-lock gate: `sales/notes_services.py::cancel_challan()` reverses the same stock posting its own `complete_challan()` gates on `challan_date` (CR-019) before posting — `cancel_challan()` has no gate call anywhere in the function | Med — same mitigating/exposure shape as G-21 (movement date isn't backdated; the challan's own status/date retroactively changes a closed period's picture) | Low–Med | ✅ (2026-09-13) | Fixed: `cancel_challan()` now calls the gate (guarded by `challan.stock_posted`, `allow_soft_closed=True`) before reversing the stock posting. Regression: `tests/test_a10_period_centralization.py::test_g22_challan_cancel_blocked_in_hard_closed_period`, verified red-without-the-fix. Now also covered structurally by `guard_period_gate_coverage` | **P2** | backend |
| **G-period-gate-coverage** | No structural test asserted every money-amend `complete()`/`cancel()` calls `assert_period_allows_money_amend` — coverage was per-flow black-box tests only, so a newly-added flow forgetting the gate (as G-21/G-22 did) wasn't caught by anything until someone noticed in production | Med — this was the meta-gap that let G-21/G-22 ship unnoticed | Med — recurs every time a new money-amend document type is added | ✅ (2026-09-13) | Built `scripts/ci_gates/guards/guard_period_gate_coverage.py` — a static, `ast`-based registry guard (23 verified call sites across sales/purchases/notes/GRN/BoE/payments) that fails if any registered `complete()`/`cancel()` stops calling the gate. Auto-discovered and self-tested by `run_guards.py`/`--selftest` alongside `guard_no_raw_unit_cost_update`. Extend the registry (and `CROSS_FLOW_IMPACT_MAP.md` §6's call-site list) together as more sites are individually verified — don't add an entry you haven't personally confirmed | **P2** | backend |
| **G-23** | `payments/dunning.py::customer_risk_snapshot()` filtered `SalesInvoice` to `COMPLETED` only, while the per-invoice outstanding-balance calc it sums (and the already-fixed G-20) both treat `(COMPLETED, RETURNED)` as balance-bearing — same bug shape as G-20, found while designing G-20's fix, not independently rediscovered | High — this snapshot feeds `sales/services.py`'s auto-credit-hold check at invoice completion, plus the customer-risk API/attention feed; a RETURNED invoice with genuine residual AR (a post-return debit note) was invisible to aging/overdue totals and could not trigger a credit hold that should have fired | Med — same root cause as G-17/18/20 | ✅ (2026-09-13, confirmed go by user before implementing — this one changes real credit-hold behavior) | Fixed: filter now uses `ledgers.services.OPEN_SALES_STATUSES`. Regression: `test_a07_dunning.py::test_g23_customer_risk_snapshot_sees_returned_invoice_with_residual_ar`, verified red-before-green | **P1** | backend |

---

## 8. Weak assumptions to keep challenging

Each is currently *reasonable* but under-evidenced. Re-test at each phase
boundary.

1. **"SQLite local ≈ Postgres prod."** Mitigated by CI, but every dev runs
   SQLite; `SELECT … FOR UPDATE` is a no-op there, so concurrency bugs are
   invisible until CI. → G-11a.
2. **"Eager Celery ≈ real broker."** Task *effects* are asserted; task *ordering*
   and retry timing are not. → G-10.
3. **"App-layer `company_id` scoping is sufficient isolation."** It is the *only*
   guarantee (RLS off). No defense-in-depth. Fine for pilot; revisit for GA.
4. **"Worksheets are enough for the CA."** Entirely a proxy until H-05. → G-14.
5. **"Running weighted cost ≈ FIFO COGS."** The delta from true FIFO is disclosed
   but not quantified. A large price swing during the pilot could surprise a CA.
6. **"Persona journeys via API ≈ what the user experiences."** Closed for
   the four freeze roles: FE `role-boundaries.spec.ts` is live for OWNER /
   VIEWER / SALES / ACCOUNTANT (G-4). API deny-sets remain the L4 proof.
7. **"Invariants at rest are enough."** Mid-transaction inconsistency is
   deliberately not checked (`no_invariant_check`). A crash mid-`complete()` that
   commits half is caught only if a specific test exercises that crash.
8. **"84% line / 80% diff coverage means the behaviour is covered."** Coverage
   proves execution, not assertion. Mutation testing (the real check) is blocked
   on tooling. → G-mutation.
9. **"Snapshot files are correct."** A blessed golden can bless a bug. Only
   F1–F8 are CA-anchored (`guard_ca_tax_parity`); other GSTR/report snapshots
   rest on developer judgement.
10. **"The frozen flag profile is what pilots run."** Deviations are "documented
    exceptions" — but nothing tests the *deviated* profile. If a pilot host flips
    a flag, that combination is untested.
11. **"A unit-tested display helper is a tested display helper."** `paidAwareStatus()`
    had passing tests and still shipped a masked-return bug, because its tests only
    covered the inputs someone thought to write, not the full state-combination
    space the function actually receives in production. Page-level render tests
    close the loop the unit test can't. → G-17.
12. **"Each reader can independently re-derive what a status-set means."**
    Seven times now (G-17…G-20, G-23, CF-001), a reader wrote its own
    `status__in=(COMPLETED, RETURNED)` or equivalent instead of consuming one
    named, tested predicate — and drifted from a sibling reader that wrote the
    same logic slightly differently. **Closed for `SalesInvoice` 2026-09-13**:
    `backend/sales/status_semantics.py` now holds two predicates —
    `is_open_receivable()` (may still owe money: outstanding/aging/
    statements/payment-health/dunning/credit-risk) and `is_operational_sale()`
    (counts as a live sale: analytics/attribution) — derived from what was
    already correctly in use, not invented. No third "is_dunning_eligible"
    predicate: traced it and confirmed dunning eligibility is
    `is_open_receivable` plus a due-date rule, not a distinct status set.
    Migrated as a sequence of small, individually-verified, behavior-preserving
    commits (lowest-risk analytics readers first, `ledgers/services.py` and
    `reporting/services.py` last, each step touching only the import + call-site
    swap for that one reader) — exhaustively unit-tested in
    `backend/tests/test_status_semantics.py` (parametrized over the full
    `SalesInvoice.Status` enum, closing this exact weak assumption's own
    lesson — item 11 above — for the predicates themselves). **`PurchaseInvoice`
    follow-up done 2026-09-15**: `purchases/status_semantics.py` +
    `test_purchase_status_semantics.py` pins GST/IMS/ledger/reporting readers
    on `OPEN_PAYABLE_STATUSES` and insights price-creep on
    `OPERATIONAL_PURCHASE_STATUSES`; books-health unposted check uses the
    same open receivable/payable sets.

## 9. High-value tests to add next (prioritized backlog)

In priority order; each is small and closes a named gap.

1. ~~Un-`fixme` FE SALES/ACCT role boundaries~~ (G-4) — **done 2026-09-13**.
2. **Executed k6 smoke** (G-7) — still needs a staging-scale budget before flipping `load-harness` (calendar/ops).
3. ~~Webhook forgery sweep~~ (G-8) — **done**; WF-17 is a structural pointer as of 2026-09-15.
4. ~~Keyboard-only POS journey~~ (G-6b) — **executed chromium 2026-09-15**.
5. ~~WF-33 idempotent replay~~ (G-3) — **done 2026-09-13**.
6. ~~`PJ-WHOLE-GODOWN`~~ (G-1) — **done**.
7. **Large-tenant report/export timing fixture** (G-7) — 50k fixture exists; staging SLO soak is Phase 5.
8. ~~axe on invoice form + one report + one settings screen~~ (G-6) — **done**. Accessible-name rules added on login/dashboard/POS/invoice 2026-09-15.
9. ~~Expiry-policy matrix axis~~ (G-2) — **done**.
10. **Make `determinism-probe` blocking** (G-determinism) — wait for 3 green `main` runs (calendar).
11. ~~A11 supplier payment chain~~ — `tests/workflows/test_a11_supplier_payment.py` 2026-09-15.
12. ~~A26 OTP rate-limit / WF-18~~ — **done 2026-09-15**.
13. ~~Completed-doc MoneyFieldAudit~~ — `test_money_audit_completed.py` 2026-09-15.
14. ~~Complete/cancel/allocate/amend `AuditEvent`~~ — `test_complete_cancel_allocate_amend_write_audit_events` 2026-09-15.
15. ~~H3 beat dry-run + PDF retry→READY~~ — `test_every_beat_task_dry_runs_eager` + existing PDF status test 2026-09-15.
16. ~~WF-14 sales-bill CSV idempotency~~ — `test_wf14_upload_sales_bill_idempotent` 2026-09-15 (OCR UI stays LIM).
17. ~~Dangling WF skips converted to pointers / LIM pins~~ — WF-20/23/24/25 pointers; WF-45-verify LIM pin. Remaining skip: WF-37/38 only.

---

## 10. Maintainable regression strategy

The principle: **strong confidence without testing every line**, achieved by a
small number of load-bearing mechanisms.

### 10.1 The universal safety net — the strict invariant sweep

`INVARIANTS_STRICT=1` runs all L1 invariants after every test. This means a new
feature test that happens to corrupt the ledger fails **even if the author
forgot to assert consistency**. Keep this blocking. Never add
`continue-on-error`. New consistency rules go in `core/invariants/` as a new
`@invariant`, not as a one-off assertion in one test.

### 10.2 The regression corpus + red-then-green rule

- `backend/tests/regression/` holds one permanent test per fixed bug.
  `guard_regression_corpus_grows` blocks CI if a regression test is deleted
  without lowering `.corpus_count` — a fixed bug cannot silently lose its guard.
- **Every regression test must have shown red before green.**
  `test_invariants_smoke.py` proves the sweep itself can fail
  (`test_the_sweep_actually_catches_a_broken_journal`,
  `test_sequences_intact_flags_a_gap`). New regression tests should link the
  issue id and, where practical, a commit/PR showing the red run.

### 10.3 Drift detectors (static guards)

Run by `scripts/ci_gates/run_guards.py`, each self-tested by `--selftest`:

| Guard | Blocks |
|---|---|
| `guard_no_raw_unit_cost_update` | raw `unit_cost` write bypassing `stamp_cost` |
| `guard_period_gate_coverage` (G-21/G-22) | a registered money-amend `complete()`/`cancel()` dropping its `assert_period_allows_money_amend` call |
| `guard_config_consistency` (FG-1) | a feature flag in code not classified in `FREEZE_SCOPE.md` |
| `guard_regression_corpus_grows` | a deleted regression test |
| `guard_required_checks_match` | `ci.yml` jobs vs `REQUIRED_CHECKS.txt` drift |
| `guard_ca_tax_parity` | a CA-signed scenario losing its automated parity case |

Plus non-guard drift gates in the `backend` job: `makemigrations --check`,
OpenAPI snapshot `git diff --exit-code`, `helpCodes.json` vs `help_codes.py`.
**Add a guard whenever a class of regression can be detected statically** — it is
cheaper and faster than a behavioural test.

### 10.4 Snapshot discipline

- Snapshots (`tests/snapshots/`) pin GST JSON, GL posting sets, report JSON, PDF
  text, CSV/XLSX headers. Volatile lines (dates, ids, FY codes) are redacted in
  the fixture, not the assertion.
- **Re-blessing a snapshot requires a one-line reason in the PR.** A snapshot
  diff in review is a behaviour change until proven cosmetic.
- CA-facing snapshots (GSTR, tax parity) must trace to `CA_SIGN_OFF_CHECKLIST.md`.

### 10.5 Flake policy

- `flaky_quarantine` marker → non-blocking lane. A test may sit there **at most
  one phase**; then it is fixed or deleted, never left.
- `pytest-randomly` is active. Order-dependence is a bug in the polluting test
  (module cache, missing rollback) — fix it, don't `-p no:randomly`.

### 10.6 Suite speed & lanes

- Small local run target: keep under ~7 min (the `H11` blocker). The fast lane is
  `tests/workflows tests/tenancy tests/gst tests/snapshots tests/edge tests/errors
  tests/matrices tests/personas` + `test_invariants_smoke` + `tests/regression`
  (the Phase 2 gate) — run this before pushing.
- `--reuse-db` locally; CI is fresh Postgres. Run `pytest --create-db` after a
  migration change.
- Coverage ratchets: `--cov-fail-under=83` absolute floor,
  `diff-cover --fail-under=80` on changed lines. **Both only go up.**

### 10.7 What we deliberately do NOT test (anti-goals)

- NOT SUPPORTED modules (Manufacturing, Payroll, CRM, live GSP, Tally sync, AI
  insights) — the only test is that they are **inaccessible** under the pilot
  flag profile (`test_freeze_demoted_surfaces.py`,
  `test_wf_limitation_guards.py`, `test_pj_limitation_guards.py`).
- Multi-currency, multi-GSTIN, BoE/landed-cost — asserted OUT, not exercised.
- Third-party delivery (email/SMS send, WhatsApp Cloud) — adapter contract only;
  delivery is external and LIM.
- Exhaustive per-page UI coverage — one smoke per important route; the rest is an
  accepted LIM.
- Line-by-line coverage of generated code, config, and migrations.

---

## 11. Evidence & sign-off model

### 11.1 Automated evidence → pilot hypotheses

| Hypothesis | Automated proxy (must stay green) | Human proof (pilot) |
|---|---|---|
| **H-01** ledger reconciliation | `gl.party_subledger_complete` + allocation chains + `cross_reconcile` | 100 consecutive real allocations, zero unexplained deltas |
| **H-02** POS speed / usability | `web/e2e/pos-keyboard-checkout.spec.ts` (chromium, ≤35s to pay-ready cart) | 90% of checkouts ≤ 35 s, no mouse |
| **H-03** offline outbox integrity | `offline-outbox-conflict.spec.ts` + idempotency contract | 100% drafts flushed, zero dup / loss |
| **H-04a** FEFO order | `inventory.*` + `test_wave15_fefo.py` | 100% non-manual dispatches earliest-expiry-first |
| **H-04b** expiry block | `inventory.no_expired_issue_when_blocked` (+ guard-band, G-2) | 100% expired-invoice attempts rejected |
| **H-05** CA acceptance | `guard_ca_tax_parity`, GSTR snapshots, `test_wf27` | CA files directly, no recalculation |

### 11.2 Human sign-off gates (consume this evidence)

- `pilot/UAT_CHECKLIST.md` — ≥ 5 companies, matrix marked Pass/Fail/Blocked,
  SHA-locked at exit.
- `ca/CA_SIGN_OFF_CHECKLIST.md` — F1–F8 tax scenarios + invoice layouts.
- `pilot/GO_NO_GO.md` — PM / Eng / QA / CA / Ops signatures; Wave 16 Final Gates.
- Open P0/P1 in `FREEZE_SCOPE_COVERAGE.md` §"P0/P1 issue-register sweep": all 9
  residuals are infra / governance / roadmap — **no open P0/P1 is a code defect**
  as of 2026-09-10. Keep it that way: a new P0/P1 code defect blocks the freeze.

### 11.3 The freeze rule (unchanged, restated)

> When every SUPPORTED item in `FREEZE_SCOPE.md` §A is ✅ gated and every NOT
> SUPPORTED item is proven inaccessible, Bizboard freezes. This strategy adds:
> every 🟡 / ⛔ / 🚫 must have a §7 register entry with an owner and a phase.

---

## 12. Ownership, cadence, change control

| Cadence | Action | Owner |
|---|---|---|
| Every PR | fast-lane + guards + diff-cover ≥ 80% + strict sweep | author |
| Every merge to `main` | full CI matrix incl. `invariant-sweep`, `e2e-golden`, `docker` | CI |
| Weekly | triage `flaky_quarantine`, advisory lanes (`determinism-probe`, `postgres-rls`, `mobile-emulator-smoke`, mutation lane once added) | QA |
| Phase boundary | reconcile §3 status + §7 register vs `FREEZE_SCOPE_COVERAGE.md`; re-challenge §8 assumptions; ratchet coverage floors | QA + founder |
| Each pilot stage | record H-0x results; a fail extends the experiment (INCONCLUSIVE band), it does not silently pass | pilot lead |
| New feature (post-freeze: bug-fix only) | new behaviour needs a chain or journey; new consistency rule needs an `@invariant`; new regression needs red-then-green | author + reviewer |

**Change control for this document:** edits that change method, priorities, or
the §7 ranking need founder + QA sign-off. Line-item status lives in
`FREEZE_SCOPE_COVERAGE.md` and is updated there first.
