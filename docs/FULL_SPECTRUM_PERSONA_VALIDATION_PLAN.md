# BizBoard Full-Spectrum Persona & Archetype Validation Plan (T1–T7)

**Document Version:** 2.2.0
**Status:** Living document — verified snapshot below, re-verify on every change to `backend/tests/personas/`
**Last verified:** 2026-09-12, tree on top of commit `2ccb253` (+2 uncommitted tests, see §7), `pytest tests/personas/ -q` → **55 passed, 0 failed** in 83.0s (Windows, Python 3.13, default SQLite test settings, Redis running; Postgres-only concurrency tests are a separate suite — see §8)
**Scope of this document:** the persona-journey layer only (`backend/tests/personas/`, 24 files / 55 tests) — one layer (**L4**) of the whole-product strategy in `docs/TESTING_STRATEGY.md`. Manufacturing / payroll / CRM journeys are tagged `dark_module` and **do not count toward freeze coverage**.
**Repository Location:** `backend/tests/personas/`
**Core Invariant chain:** Business Archetype → Persona → Journey → Transaction → Document → Stock → GL/Subledger → Reports → Insights → Action → Outcome

---

## 0. How this document relates to the other testing docs

This plan does **not** define its own taxonomy. It narrates and indexes what already exists, in this order of authority:

| Doc | Owns | Ground truth for |
| :--- | :--- | :--- |
| [`BUSINESS_ARCHETYPES_AND_PERSONAS.md`](BUSINESS_ARCHETYPES_AND_PERSONAS.md) | *Who* we build for | Canonical `ARCH-01`…`ARCH-08` archetype codes, `P1`…`P6` + Viewer/Import/Migrator persona definitions, which modules are dark in production |
| [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md) | Whole-product test **method** | Layer model **L1–L10** (only numbering), open gap register (`G-*`), disposition per archetype. T1–T7 below **map onto** those layers. |
| [`HOLISTIC_VALIDATION_REVIEW.md`](HOLISTIC_VALIDATION_REVIEW.md) | Quality model | Philosophy, Flow / Impact / Truth graphs, architecture-first sequence. This plan is the **L4 view**, not a competing pyramid |
| [`backend/tests/personas/README.md`](../backend/tests/personas/README.md) | The persona-journey layer itself | Archetype `kind` strings (`seed_archetype`), persona-to-role mapping, the journey matrix, capability/deny-sets |
| **This document** | — | A narrative walkthrough + execution guide over the tests in `backend/tests/personas/`. T1–T7 is a *reading frame* for L4, not a second strategy |

**Persona numbering used below is copied verbatim from `README.md`** (P1-OWNER, P2-CLERK, P3-SALES, P4-CUSTODIAN, P5-ACCT, P6-CA, plus VIEWER/IMPORT/MIGRATOR). Earlier drafts of this document used an independent, inconsistent P1–P4 scheme that collided with the README's — that has been removed.

Whenever this document and `TESTING_STRATEGY.md` appear to disagree about a gap's status, `TESTING_STRATEGY.md`'s gap register (`G-*`, §7 of that doc) is authoritative; §7 below only proposes updates to it.

---

## 1. Executive Summary & Purpose

BizBoard's validation strategy extends beyond traditional transactional testing (T1–T3) into a **7-Tier Validation System (T1–T7)**.

Indian MSME owners (Kirana shopkeepers, distributors, pharmacists, manufacturers, contractors, and micro-vendors) rely on BizBoard for operational correctness, statutory compliance (GST/e-Invoicing), cash flow survival, and audit defense.

This document indexes the backend persona-journey suite that exercises that reality end to end. **Do not grow this suite by volume** to close product-truth gaps — those belong to L9 lifecycle goldens and L10 identities (`HOLISTIC_VALIDATION_REVIEW.md` §0.7). Dark-module tests (manufacturing, payroll, CRM) prove flagged-on code paths; they do not close freeze coverage.

What L4 still must prove:

1. **Multi-Archetype Cohesion** — every supported archetype's operating reality is validated through realistic operational cycles.
2. **Deep Accounting & Stock Accuracy** — inward stock, consumption, transfers, and billing strictly balance physical stock with general ledger accounts.
3. **Source-to-Dashboard Reconciliation** — invoices, registers, GL accounts, and executive dashboard KPIs foot identically to the exact rupee and paise.
4. **Actionable Intelligence** — low-stock warnings, credit limit alerts, and margin leakage notifications guide users directly toward remediating actions.
5. **Zero Tenant Contamination & Safe Retries** — multi-tenant boundaries and idempotent transaction submissions prevent double-billing and data leakage.

**What this document is not:** a claim of full-product coverage. It covers the backend API persona layer only. Frontend/browser coverage of the same journeys is a separate layer (§8). Three of the workstreams below (Manufacturing, Payroll, CRM) exercise modules that are **disabled by default in production** (§2 caveat, §4 WS7–WS9) — their tests passing proves the code path works when the flag is forced on in the test environment, not that the feature is live for pilot users.

---

## 2. The 7-Tier Validation Architecture (reading frame for L4)

T1–T7 is how this L4 index *talks about* quality. The only layer numbering for the product is **L1–L10** in `TESTING_STRATEGY.md`. Rough map: T1–T3 → L1–L3, T4 → L4, T5 → L10, T6 → decision/attention assertions, T7 → L2 tenancy + L7.

```text
+----------------------------------------------------------------------------------------------+
|                                BIZBOARD QUALITY SYSTEM                                         |
+------+--------------------------+--------------------------------------------------------------+
| TIER | LAYER                    | SCOPE & RECONCILIATION OBJECTIVE                              |
+------+--------------------------+--------------------------------------------------------------+
|  T7  | EXPERIENCE & RESILIENCE  | Idempotency, safe network retries, multi-tenant zero          |
|      |                          | leakage, systematic RBAC permission barriers.                 |
+------+--------------------------+--------------------------------------------------------------+
|  T6  | INTELLIGENCE TRUTH       | Attention Center, fast-mover reorder alerts, credit           |
|      |                          | risk warnings, margin leakage detection & resolution.         |
+------+--------------------------+--------------------------------------------------------------+
|  T5  | REPORTING TRUTH          | Invoices == Sales Register == Dashboard KPIs == GL            |
|      |                          | Valuation == Cumulative StockMovement truth.                  |
+------+--------------------------+--------------------------------------------------------------+
|  T4  | ARCHETYPE JOURNEYS       | Kirana, Distributor, Pharma, Manufacturing, Contractor,       |
|      |                          | Micro-vendor, and cross-cutting statutory/ops journeys.       |
+------+--------------------------+--------------------------------------------------------------+
|  T3  | JOURNEY INTEGRITY        | Multi-step stateful workflows (Quote -> Challan ->            |
|      |                          | Invoice -> Receipt -> Reconciliation).                        |
+------+--------------------------+--------------------------------------------------------------+
|  T2  | BUSINESS INVARIANTS      | Invariant Engine: DR == CR, Subledger == Control GL,          |
|      |                          | Stock on Hand == Movement Sums.                               |
+------+--------------------------+--------------------------------------------------------------+
|  T1  | TRANSACTION INTEGRITY    | 5-Layer sync: Document, Inventory, Accounting, AR/AP,         |
|      |                          | GST computation.                                              |
+------+--------------------------+--------------------------------------------------------------+
```

This document's 55 tests sit mostly at **T4** (archetype/persona journeys), with **T5–T7** covered by dedicated workstreams (§4 WS2–WS4) and **T1–T3** covered by every test transitively via `assert_all_invariants()` (§5).

---

## 3. Business Archetype × Persona Coverage Matrix

Archetype `kind` strings are `seed_archetype()`'s argument in `fixtures.py`; `ARCH-0N` codes and persona IDs are `README.md`'s / `BUSINESS_ARCHETYPES_AND_PERSONAS.md`'s canonical scheme.

| `kind` | ARCH code | Key Operating Dynamics | Personas exercised (this suite) | Primary Business Invariant | Production flag status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `retail` | ARCH-01 | Fast checkout, mixed cash/UPI, high turnover staples, drawer balance | P1-OWNER, P2-CLERK | Cash drawer balance ≡ recorded counter receipts; stockout alerts trigger at minimum buffer | Live |
| `trader` | ARCH-03 | Small B2B, GSTIN customers, batch lines, books on | P1-OWNER, P3-SALES, P5-ACCT, VIEWER, IMPORT | Credit sale AR ties to customer subledger; books stay balanced after every posting | Live |
| `wholesale` | ARCH-04 | 3 godowns, multi-godown transfers, B2B credit exposure, dunning config | P1-OWNER, P4-CUSTODIAN, P5-ACCT | Credit limit barrier blocks order completion; godown transfer nets to zero across warehouses | Live |
| `batch` | ARCH-05 | Batch tracking, FEFO dispensing, drug expiry, guard-band policy | P1-OWNER (via journey) | Expired batches blocked from sale under active policy; FEFO always picks the earliest-expiring lot first | Live |
| `serialized` | ARCH-06 | Unique serial numbers, warranty fraud guards, high-value goods | P1-OWNER (via journey) | A serial can only be sold once and returned once; duplicate return is rejected | Live |
| `contractor` | ARCH-07 | Dual quote: services (SAC) + spares (HSN), dual revenue recognition | P1-OWNER, P5-ACCT | Labor never touches physical inventory; spares decrement warehouse stock | Live |
| `service` | ARCH-07 (non-stock variant) | Single-counter or B2B pure-service billing, no inventory at all | P1-OWNER | No `StockMovement` is ever created for a service line | Live |
| `manufacturing` | ARCH-08 | Multi-level BOM, Work Orders, raw-material consumption to WIP | P1-OWNER, P4-CUSTODIAN | Component stock deducted on Work Order release; finished goods credited on completion | **Dark by default** (`ENABLE_MANUFACTURING=0` in production per `BUSINESS_ARCHETYPES_AND_PERSONAS.md` §5) — tested with the flag forced on |
| `migration` | — (cutover, not a market archetype) | Day-zero data load: item master, parties, opening stock/TB, then reconcile | P1-OWNER, P5-ACCT | Opening AR/AP/inventory control ties exactly to the opening trial balance | Live |
| (cross-archetype) | — | Micro/Gully Vendor: single-counter cash, no distinct fixture `kind` — modeled as a `retail` variant in WS1 | P1-OWNER | High-speed single-step billing with zero overhead and same-day reconciliation | Live |

Not covered anywhere in this suite (by design, not oversight): **ARCH-02** (Small Composition Merchant) and **ARCH-07's milestone/job-work sub-mode** are both explicitly deprioritized/out-of-scope per `BUSINESS_ARCHETYPES_AND_PERSONAS.md` §8 — no persona journey is expected for either.

**Cross-cutting, non-archetype-specific workstreams** (bank reconciliation, CA audit, payroll, e-invoicing/e-way, CRM lead-to-order, period close) run against whichever archetype fixture is convenient (usually `trader` or `wholesale`) rather than testing an archetype per se — see WS7–WS10 in §4.

**Payroll and CRM are also dark modules in production** (`ENABLE_PAYROLL=0`, `ENABLE_CRM=0` per the same source) — `test_pj_payroll_and_advances.py` and `test_pj_crm_quote_to_order.py` exercise them with flags forced on in the test environment, same caveat as manufacturing.

---

## 4. Master Workstream Specifications

24 files, 55 tests, grouped by concern. Each row is one test function.

### WS1 — Master Archetype Matrix (`test_pj_master_archetype_matrix.py`, 6 tests)
Full operational cycles for the primary retail/trade archetypes.

| Test | What it proves |
| :--- | :--- |
| `test_pj_archetype_kirana_retail_full_operating_cycle` | Cash float → split-tender counter sales (₹500 cash + ₹208 UPI) → fast-mover decrement → low-stock trigger at 5 units → end-of-shift drawer reconciliation |
| `test_pj_archetype_distributor_multi_godown_and_credit_risk` | 100-unit inter-godown transfer → credit exposure hits ₹50,000 limit → challan → B2B tax invoice → bank collection → subledger reconciliation |
| `test_pj_archetype_medical_pharma_fefo_and_expiry_compliance` | Multi-batch inward (10-day vs 180-day expiry) → FEFO picks the near-expiry batch first → expired-batch sale is rejected → debit note return to distributor |
| `test_pj_archetype_manufacturing_bom_and_work_order` | 2 raw components → 1 finished good BOM → WO release consumes 40 components into WIP → WO completion capitalizes 20 finished units (dark-module caveat applies, §3) |
| `test_pj_archetype_contractor_hybrid_services_and_spares` | AC service (SAC 998714) + compressor spare (HSN 841590) on one invoice → GL splits Account 4100 (Product) vs 4200 (Service) → only the spare decrements stock |
| `test_pj_archetype_micro_vendor_quick_cash_day` | Fast cash-sale sequence through a trading day → zero balance drift on the daily counter summary |

### WS2 — Source-to-Dashboard Reporting Reconciliation (`test_pj_reporting_reconciliation.py`, 3 tests)
Absolute parity between transactional source records and summary dashboards (T5).

| Test | What it proves |
| :--- | :--- |
| `test_pj_sales_register_to_dashboard_and_gl_reconciliation` | Σ Invoice Taxable Amount ≡ Sales Register Taxable ≡ GL 4100 Credit ≡ Dashboard Revenue KPI |
| `test_pj_inventory_summary_and_valuation_reconciliation` | `StockBalance.on_hand` ≡ Σ signed `StockMovement` quantities, zero drift after purchase/sale/return/adjustment |
| `test_pj_receivables_aging_to_customer_subledger_reconciliation` | Aging buckets foot to customer subledger, Dashboard Total Receivables KPI, and GL Trade Debtors Control (1200) |

### WS3 — Actionable Intelligence & Closed-Loop Outcomes (`test_pj_insights_and_recommendations.py`, 3 tests)
Alert generation, actionable navigation, automated resolution (T6).

| Test | What it proves |
| :--- | :--- |
| `test_pj_insights_low_stock_fast_mover_alert_and_reorder_action` | Stock below reorder point → `LOW_STOCK_FAST_MOVER` alert with target `/inventory/low-stock` → inwarding resolves it |
| `test_pj_insights_customer_credit_limit_near_alert_and_action` | Outstanding > 80% of credit limit → `CREDIT_LIMIT_NEAR` alert → a receipt drops exposure below threshold → alert resolves |
| `test_pj_insights_leakage_detector_sale_below_cost` | Selling price below unit cost → `SALE_BELOW_COST` warning with the exact leakage in paise |

### WS4 — System Resilience & Tenant Security (`test_pj_resilience_and_tenant_isolation.py`, 4 tests)
Idempotent safe retries, multi-tenant isolation, RBAC matrix (T7).

| Test | What it proves |
| :--- | :--- |
| `test_pj_idempotency_safe_retry_single_transaction_effect` | 3 rapid client retries under one `Idempotency-Key` with the *same* payload → exactly 1 invoice, 1 stock movement |
| `test_pj_idempotency_key_reused_with_different_payload_replays_first_response` | **New (§7).** Negative case: same `Idempotency-Key`, a *different* payload → `core.idempotency` keys purely on (company, scope, key) with no body hash, so the first cached response is replayed and the second payload is silently never processed. Pins this as known, deliberate behavior rather than an unguarded gap. |
| `test_pj_strict_multi_tenant_isolation` | Cross-tenant reads 404/403; Tenant A cannot reference Tenant B's customer/product; dashboard scoped to authenticated company |
| `test_pj_systematic_rbac_matrix_enforcement` | Sales Staff denied journals/period-close/stock-audit (403); Munshi permitted journals but denied period close |

### WS5 — FTUE Stepper & Diagnostic Help (`test_pj_ftue_onboarding_and_help.py`, 3 tests)
Day-0 onboarding progression and error recovery.

| Test | What it proves |
| :--- | :--- |
| `test_pj_ftue_founder_onboarding_stepper_and_error_recovery` | Blank slate → invalid GSTIN maps to `add-gstin` intent → stepper `tax → shop → payments → catalog → first_bill` → `COMPLETED` unlocks dashboard |
| `test_pj_ftue_team_invite_landing_and_role_access` | Clerk, Custodian, Munshi accept invites and land on their view with no 403 bursts |
| `test_pj_ftue_help_error_code_to_intent_resolution` | Every `ALL_HELP_CODES` entry resolves through `ERROR_CODE_TO_INTENT` / `ERROR_CODE_TO_LEAF` |

### WS6 — Archetype × Role Matrix (`test_pj_stubs.py`, `test_pj_retail.py`, `test_pj_trader.py`; 13 tests)
The per-role capability/deny-set sweep referenced by the journey matrix in `README.md`. (File name `test_pj_stubs.py` is a holdover — every test in it is fully implemented, not a placeholder.)

| Test | What it proves |
| :--- | :--- |
| `test_pj_retail_owner_normal_day` | Retail owner: counter sales + stock adjustment + EOD reports |
| `test_pj_retail_sales_staff_boundary` | Retail sales staff: POS + receipts + lookup allowed; everything else denied |
| `test_pj_trader_owner_normal_day` | Trader owner: purchase → credit sale → part payment → ledger + GST worksheet stay consistent |
| `test_pj_trader_sales_staff_boundary` | Trader P3-SALES: quote/invoice/receipt allowed; cancel/journals/imports/adjustments/reports denied |
| `test_pj_trader_accountant_day` | Trader P5-ACCT: balanced JV posting, TB/P&L/aging reads allowed; create-sales/manage-inventory denied |
| `test_pj_trader_viewer_readonly` | Trader VIEWER: deny-all API surface pinned (BB-000422 masters, BUG-319 reports, every mutation) |
| `test_pj_trader_import_operator` | Trader IMPORT: bulk customer/product import with opening stock; re-run rejects every row via SKU uniqueness (idempotent) |
| `test_pj_wholesale_owner_multi_godown_day` | Wholesale owner: 3-godown inward → inter-godown transfer nets to zero → branch sale → period close |
| `test_pj_wholesale_accountant_period_close` | Wholesale P5-ACCT: balanced JV, TB/balance-sheet reads; period close is owner-only; back-dated post-close entry rejected |
| `test_pj_wholesale_godown_custodian` | **P4-CUSTODIAN** (`QOS-0008`, closes gap `G-1` — see §7): inward + inter-godown transfer allowed; financial reports/journals/export denied |
| `test_pj_service_owner_no_stock` | Service owner: GST invoice on a non-stock item never creates a `StockMovement`, even through payment allocation |
| `test_pj_newuser_register_to_first_invoice` | Fresh registration → OWNER role assigned → dashboard loads → first item/customer/invoice/receipt, invariants clean |
| `test_pj_migration_wholesale_large_cutover_with_history` | Large multi-godown cutover: 3 debtors / 2 creditors / 3 godowns of opening stock; `opening_ties_out` holds; redo (post→reverse) holds; first live invoice continues the old numbering series |

### WS7 — Specialized Archetype Journeys (4 files, 5 tests)
Deep single-archetype journeys not covered by WS1's broader sweep.

| File / Test | What it proves |
| :--- | :--- |
| `test_pj_batch_expiry.py::test_pj_batch_expiry_fefo_and_guard_journey` | FEFO picking order; active `block_expired_stock` policy rejects invoicing an expired batch (closes one part of gap `G-2`, §7) |
| `test_pj_serialized.py::test_pj_serialized_lifecycle_and_warranty_fraud_guard` | Serial-tracked sale/return lifecycle; a duplicate return of the same serial is rejected (closes another part of gap `G-2`, §7) |
| `test_pj_serialized.py::test_pj_bulk_serial_import_partial_failure_blocks_whole_job` | **New (§7).** Bulk serial ingest is the `opening_serials` sheet on a PRODUCTS import; a bad row (unknown SKU / missing serial) blocks the *entire* PRODUCTS-kind commit (all-or-nothing), so even an otherwise-valid row in the same job is never posted. Closes the last part of gap `G-2`. |
| `test_pj_contractor_hybrid.py::test_pj_contractor_hybrid_service_and_spares_journey` | Hybrid SAC service + HSN spare invoice; stock movement only for the physical spare |
| `test_pj_manufacturing_bom.py::test_pj_manufacturing_bom_work_order_lifecycle` | P1 defines BOM; P4 inwards raw material and runs the WO; release debits WIP (1450), completion credits WIP / debits FG. **Dark-module caveat applies (§3).** |

> **Note on overlap (resolved):** `test_pj_archetype_golden_journeys.py` (WS12) re-covers the Kirana, Distributor, and Pharma scenarios from WS1 at a "golden business outcome" altitude (including the alert/reorder loop that WS3 also covers). Confirmed with the test owner this is intentional layered coverage — WS1 proves transactional mechanics, WS12 proves the end-to-end business outcome including the insights/alert loop WS1 doesn't touch. Both files now carry a docstring cross-reference explaining the split; neither was deduplicated.

### WS8 — Cross-Cutting Financial & Statutory Journeys (5 files, 5 tests)
Not tied to one archetype; run against whichever fixture is convenient.

| File / Test | What it proves |
| :--- | :--- |
| `test_pj_bank_reconciliation.py::test_pj_bank_reconciliation_aa_matching_and_journal` | P5 matches AA/bank-statement credits to posted receipts by exact UTR, then by amount+date-window fallback; ambiguous duplicate-amount candidates are left unmatched rather than guessed |
| `test_pj_ca_audit.py::test_pj_ca_statutory_and_accounting_integrity_audit` | P6 external CA: TB balances to zero; AR/AP subledger-to-GL-control tie-outs; full statutory integrity sweep |
| `test_pj_period_close_and_ca_audit.py::test_pj_munshi_journals_period_close_and_ca_audit` | Balanced JV posts, unbalanced JV is rejected; Munshi can view but not close periods; CA-facing checks after close |
| `test_pj_returns_and_notes.py::test_pj_returns_and_credit_debit_notes_lifecycle` | Sales return → credit note re-inwards stock and reduces AR; clerk cannot complete a financial credit note without accountant/owner sign-off |
| `test_pj_payroll_and_advances.py::test_pj_payroll_and_statutory_gl_lifecycle` | P1 sets up employees with PF/ESI/PT configs; P5 runs payroll with exact statutory deduction math (PF 12% capped, ESI splits, EPS/EPF/Admin/EDLI). **Dark-module caveat applies (§3).** |

### WS9 — Statutory & Commerce Pipelines (2 files, 2 tests)

| File / Test | What it proves |
| :--- | :--- |
| `test_pj_einvoice_eway.py::test_pj_einvoice_and_eway_statutory_lifecycle` | High-value B2B invoice → e-Invoice IRN payload → e-Way Bill payload → invoice is locked against line edits post-IRN |
| `test_pj_crm_quote_to_order.py::test_pj_crm_lead_to_sales_order_and_challan_pipeline` | P3 qualifies a lead → converts to customer → sales order → delivery challan deducts stock while AR/Revenue stay unposted at challan stage. **Dark-module caveat applies (§3, CRM).** |

### WS10 — Operational Day Journeys (2 files, 2 tests)

| File / Test | What it proves |
| :--- | :--- |
| `test_pj_pos_shift_and_cash_reconciliation.py::test_pj_pos_counter_shift_and_cash_drawer_reconciliation` | Shift open with float → rapid counter billing with split cash/UPI tender → full allocation → drawer reconciles |
| `test_pj_stock_audit_and_adjustments.py::test_pj_custodian_physical_stock_count_and_adjustments` | P4 opens a `StockCountSession`, snapshots on-hand, enters physical counts, variance calculated and adjusted |

### WS11 — Migration & Cutover (`test_pj_migration.py`, 2 tests)
The highest-stakes journey per `README.md` — see that file's "PJ-MIGRATION" section for the full assertion list (opening reconciliation, import idempotency, partial-failure resume, numbering continuity, redo path, cross-tenant safety).

| Test | What it proves |
| :--- | :--- |
| `test_pj_migration_trader_cutover_and_reconcile` | Day-zero trader cutover: item master, parties, opening stock/TB load, then reconciled |
| `test_pj_migration_redo_wrong_opening` | A wrong opening entry is posted then reversed; invariants hold before and after |

### WS12 — Cross-Flow Consistency & Golden Journeys (2 files, 6 tests)

| File / Test | What it proves |
| :--- | :--- |
| `test_cross_flow_consistency.py::test_startup_founder_onboarding_to_analytics_synchronization` | Onboarding-state derivation ↔ Dashboard KPIs ↔ DailyBusinessSummary ↔ Health Score ↔ Cashflow Forecast ↔ Attention Center all agree |
| `test_cross_flow_consistency.py::test_multi_persona_entitlement_and_segregation_consistency` | Entitlements are consistent across personas at once, not just pairwise |
| `test_cross_flow_consistency.py::test_paise_conversion_and_rounding_accuracy` | Rounding/paise conversion is consistent across every money-touching surface |
| `test_pj_archetype_golden_journeys.py::test_pj_golden_journey_kirana_retail_fast_turnover` | Golden-path Kirana: fast multi-tender billing, low-stock alert, reorder avoids stockout (overlaps WS1 + WS3, see note under WS7) |
| `test_pj_archetype_golden_journeys.py::test_pj_golden_journey_distributor_credit_risk_and_godown_transfer` | Golden-path distributor: multi-godown rebalance + credit-risk flow (overlaps WS1) |
| `test_pj_archetype_golden_journeys.py::test_pj_golden_journey_medical_pharma_fefo_and_near_expiry_return` | Golden-path pharma: FEFO + near-expiry return (overlaps WS1) |

### WS13 — Limitation Guards (`test_pj_limitation_guards.py`, 1 test)

| Test | What it proves |
| :--- | :--- |
| `test_pj_owner_cannot_reach_demoted_routes_in_pilot_profile` | With the pilot flag profile (`ENABLE_FIXED_ASSETS=False, ENABLE_BOE=False`), even the OWNER gets a 404 (route not mounted) from D6/D10 surfaces — not a 403. Pins the "known limitation" contract per-route, not just once globally. |

---

## 5. Formal Invariant Guarantees

Every test in this suite calls `assert_all_invariants(company)` at the end of its journey (some call it at intermediate state boundaries too). That sweep mechanically checks, for every test regardless of archetype:

1. **Double-Entry Balance Guarantee** — for every `JournalEntry`, sum(debits) == sum(credits).
2. **Subledger Control Agreement** — GL Account `1200` balance == Σ customer outstanding; GL Account `2100` balance == Σ supplier outstanding.
3. **Inventory Conservation Law** — `StockBalance.on_hand` == Σ inward `StockMovement`s − Σ outward `StockMovement`s.
4. **GST Tax Accounting Parity** — Invoice Output CGST + SGST == GL `2210` Credit + GL `2220` Credit.

**These four are universal and automatic.** They are distinct from the *journey-specific* assertions each test also makes (e.g. "cash drawer equals recorded receipts," "credit limit blocks the order," "duplicate return is rejected") — those are hand-written per test and only prove the one scenario exercised, not a general property. When reading a test's docstring, treat `assert_all_invariants(company)` as the baseline guarantee and everything else as scenario-specific coverage.

---

## 6. Execution Runbook

```bash
cd backend

# Run the entire persona-journey suite (all 24 files, 55 tests)
pytest tests/personas/ -v
```

To run only a themed subset, pass the specific files, e.g. the five original "master workstreams":

```bash
pytest \
  tests/personas/test_pj_master_archetype_matrix.py \
  tests/personas/test_pj_reporting_reconciliation.py \
  tests/personas/test_pj_insights_and_recommendations.py \
  tests/personas/test_pj_resilience_and_tenant_isolation.py \
  tests/personas/test_pj_ftue_onboarding_and_help.py \
  -v
```

**Prerequisites:** Python 3.13; Redis running (required even against the default SQLite test settings — see `dev-env-bare-local-run` notes); default test settings use SQLite. Concurrency-race tests are a *separate* suite (`tests/test_concurrency_races.py` or similar) gated to Postgres only — they are not part of `tests/personas/` and are not exercised by the command above.

### Verified Benchmark Results (re-verify after every change to this directory)

| Metric | Value |
| :--- | :--- |
| Command | `pytest tests/personas/ -q` |
| Collected | 55 items (24 files) |
| Passed | 55 (100%) |
| Failed | 0 |
| Duration | 83.0s |
| Invariant violations | 0 |
| Commit | `2ccb253` (+2 new tests: `test_pj_resilience_and_tenant_isolation.py`, `test_pj_serialized.py`; uncommitted at time of writing) |
| Date | 2026-09-12 |
| Environment | Windows, Python 3.13, SQLite (default test settings), Redis running |

---

## 7. Cross-reference: gaps this suite closes (verified 2026-09-12, applied to `TESTING_STRATEGY.md`)

`TESTING_STRATEGY.md` §7 carries the authoritative open-gap register. The following were checked against actual test/source code (not just docstrings) and the register has been updated accordingly:

| Gap ID | Original ask | Closer | State in `TESTING_STRATEGY.md` |
| :--- | :--- | :--- | :--- |
| `G-1` | "No persona journey for Godown-Keeper... `PJ-WHOLE-GODOWN` — inward, transfer, count session with variance, deny-set" | `test_pj_stubs.py::test_pj_wholesale_godown_custodian` (tagged `QOS-0008`) covers inward + transfer + deny-set; `test_pj_stock_audit_and_adjustments.py::test_pj_custodian_physical_stock_count_and_adjustments` covers the count-session-with-variance half. | ✅ Closed |
| `G-2` (guard-band/policy axis) | "ARCH-05 near-expiry guard-band & policy on/off not a matrix dim" | Already fully closed — `tests/matrices/test_company_settings_matrix.py::test_expiry_guard_band_matrix` is explicitly tagged `G-2/H-04b` in its own docstring and parametrizes `block_expired` × {expired-yesterday, near-expiry-today, not-near-expiry}. | ✅ Closed |
| `G-2` (warranty-fraud) | "ARCH-06 ... warranty-fraud untested" | `test_pj_serialized.py::test_pj_serialized_lifecycle_and_warranty_fraud_guard` rejects a duplicate return of the same serial. | ✅ Closed |
| `G-2` (bulk-serial partial-failure) | "ARCH-06 bulk serial partial-failure ... untested" | **Correction:** an earlier pass of this document (v2.0.0) claimed no bulk serial-import endpoint existed. That was wrong — it only checked `imports/views.py`'s `Kind` constants and missed the `opening_serials` XLSX extra-sheet on a PRODUCTS import (`imports/services.py::_validate_extra_sheets` / `_commit_products`), already exercised happy-path in `tests/test_item_godown_expiry.py::test_opening_serials_sheet_posts_serial_opening`. `test_pj_serialized.py::test_pj_bulk_serial_import_partial_failure_blocks_whole_job` (added 2026-09-12) now covers the partial-failure case: PRODUCTS-kind commit is all-or-nothing, so a single bad `opening_serials` row blocks the whole job, including the otherwise-valid rows. | ✅ Closed |
| — (new, not a pre-existing gap ID) | §9's "no adversarial variant for idempotency" limitation, noted in v2.0.0 of this document | `test_pj_resilience_and_tenant_isolation.py::test_pj_idempotency_key_reused_with_different_payload_replays_first_response` (added 2026-09-12) pins the actual behavior: same key + different payload → first response replayed, second payload silently dropped, because `core.idempotency.begin_record` keys purely on (company, scope, key) with no body hash. | ✅ Documented (behavior is now pinned by a test; whether it should instead reject a body-mismatched retry with 409/422 is a product decision, not something this document resolves) |

No claim is made about `G-3, G-4, G-5, G-7, G-8, G-9, G-10, G-11, G-13, G-14, G-15, G-16` — none of the files in this suite touch those areas.

---

## 8. Frontend / End-to-End Counterpart

This document covers the backend API persona layer (**L4** in `TESTING_STRATEGY.md`'s layer model) only. The same journeys have a browser-driven counterpart:

- `web/e2e/personas/*.spec.ts` — Playwright specs asserting the **UI hides** what each role's API denies (the concrete form of `TESTING_STRATEGY.md` §H1).
- `web/e2e-golden/*.spec.ts` — golden-path specs against a live Django+Postgres stack (`accounting-`, `invoice-`, `payments-`, `purchase-`, `pos-`, `multi-warehouse-golden-path.spec.ts`, `phase1-documents.spec.ts`).

Per `TESTING_STRATEGY.md` gap `G-4`, FE role-hiding coverage for **SALES/ACCT is `test.fixme`** as of that document's last update — only OWNER/VIEWER FE journeys are confirmed live. A backend test in this suite passing (e.g. `test_pj_trader_sales_staff_boundary` denying journal creation via the API) does **not** by itself prove the frontend hides the corresponding button for that role; check `G-4`'s state before assuming FE parity.

---

## 9. Known Limitations of This Suite

- **Dark-module tests prove code, not production scope.** Manufacturing (WS1/WS7), Payroll (WS8), and CRM (WS9) are all `ENABLE_*=0` in production per `BUSINESS_ARCHETYPES_AND_PERSONAS.md` §5. Their tests passing means the underlying service/model logic is correct when the flag is forced on — it is not evidence these features are part of the current pilot scope.
- **ARCH-02 and ARCH-07's job-work/milestone-billing sub-mode have zero coverage here**, matching their deprioritized/out-of-scope disposition — this is a deliberate omission, not a gap.
- **Idempotency's negative case is now pinned, not just noted.** As of 2026-09-12, `test_pj_idempotency_key_reused_with_different_payload_replays_first_response` (§7) exercises "a different payload reusing the same key," and the current replay-first-response behavior was a deliberate choice to keep, not change (confirmed 2026-09-12). Other journeys still mostly assert only the happy path reaching a passing/resolved state — that broader pattern remains a limitation.
- **`G-2` is now fully closed** (§7), including bulk-serial partial-failure ingest via the `opening_serials` PRODUCTS-import sheet, which does exist (an earlier version of this document incorrectly said it didn't — corrected in §7).
- **Environment-dependent claims are not universal.** The benchmark in §6 is SQLite-only; Postgres-specific behavior (`SELECT ... FOR UPDATE`, concurrency races) is untested by this suite by design (see `TESTING_STRATEGY.md` gap `G-11a`).
