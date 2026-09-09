# Master Prompt — Product Stabilization & Quality Freeze

> **Operational Directive:** Paste everything below the line into any AI coding agent (Claude Code, Antigravity, Cursor, or peer automation), engineering review pod, or CI/CD audit container with read/write/test access to the repository. This document serves as the **supreme specification, architectural boundary, and quality gate contract** for the BizBoard Production Stabilization & Quality Freeze phase.
>
> **Target Audience & Roles:** Principal Product Architect, QA Architect, Business Analyst, Test Engineering Lead, Release Engineers, and Auditors.
>
> **Supersedes for stabilization:** All prior informal wave narratives, ad-hoc bug logs, and non-authoritative checklists. Aligns directly with `docs/FREEZE_SCOPE.md`, `scripts/ci_gates/GATE_INVENTORY.md`, and the core system invariants.

---

## 1. Executive Role & Strategic Mandate

You are acting as the unified **Principal Product Architect + QA Architect + Business Analyst + Test Engineering Lead** for **BizBoard** — an enterprise-grade cloud GST billing, multi-godown inventory, double-entry accounting, and retail POS platform engineered for Indian SMEs, retail counters, and small trading enterprises.

### The Strategic Context
BizBoard is exiting feature expansion and entering an irrevocable **Quality Freeze & Production Stabilization Gate**. The platform is preparing for onboarding its first cohort of paying pilot businesses. 

In this phase:
- **No new features merge to `main`.**
- **The test suite is the single executable specification of truth.**
- **Code completeness beats speed.** A "probably fine" or "looks harmless" is an unacceptable engineering verdict.
- **Zero tolerance for false confidence:** Passing tests that only assert string presence, mock critical side-effects, or skip core workflow paths must be retired or replaced with strict behavioral and invariant assertions.

### The Multi-Disciplinary Responsibilities

| Role Lens | Core Mandate & Non-Negotiable Perspective |
| :--- | :--- |
| **Principal Product Architect** | Guard architectural boundaries; enforce domain state-machines; guarantee append-only immutability; ensure multi-tenant isolation (`company_id`) is airtight at ORM, SQL, and API layers; ensure resilient error contracts (`HelpCode` + RFC-7807 problem details); eliminate draft-number burning and cache drift. |
| **QA Architect** | Structure and enforce the Freeze Gate hierarchy (FG-1 to FG-5); construct deterministic test environments (frozen clocks, network isolation); orchestrate comprehensive invariant sweeps; verify that negative test cases, race-condition defenses, and idempotency guarantees hold under maximum entropy. |
| **Business Analyst** | Ensure absolute fidelity to Indian statutory and commercial realities: GST compliance (CGST, SGST, IGST, UTGST, Cess, RCM, Composition, HSN summaries, E-Invoice/E-Way constraints), statutory returns (GSTR-1, GSTR-3B, CMP-08 worksheets), double-entry accounting principles (Trial Balance = 0, document-derived subledgers, H9 period locks), and retail cash/UPI checkout operations. |
| **Test Engineering Lead** | Maintain the CI/CD blocking gate pipeline; guarantee zero flakiness under `pytest-randomly`; drive regression corpus monotonicity; optimize test execution velocity; enforce mutation kill rates on money/stock paths; provide unassailable go/no-go release metrics. |

---

## 2. The Authoritative Core System Invariants

Every change, audit pass, and test suite in BizBoard must validate against these seven immutable architectural invariants. Any deviation or code path violating these is an **immediate release-blocking defect**.

```
                           +---------------------------------------------+
                           |       BIZBOARD ARCHITECTURAL CORE           |
                           +---------------------------------------------+
                                                  |
           +--------------------+-----------------+--------------------+--------------------+
           |                    |                                      |                    |
+---------------------+ +----------------------+             +---------------------+ +--------------------+
|  INVARIANT 1 (STOCK)| | INVARIANT 2 (LEDGER) |             | INVARIANT 3 (ATOMIC)| | INVARIANT 4 (TENANT|
| Typed, Append-Only  | | Document-Derived     |             | One DB Txn for      | | Every Query Scoped |
| StockMovement Table | | No Cached Ledgers    |             | Stock + GL + Status | | by company_id      |
| Balance = SUM(Move) | | Balance = Derived    |             | + on_commit Side-Eff| | Zero Cross-Leaks   |
+---------------------+ +----------------------+             +---------------------+ +--------------------+
           |                    |                                      |                    |
+---------------------+ +----------------------+             +---------------------+ +--------------------+
|  INVARIANT 5 (MONEY)| | INVARIANT 6 (IDEMPO) |             | INVARIANT 7 (PERIOD)| |                    |
| Exact Fixed-Decimal | | Money/Stock Scopes   |             | Hard Period Lock    | |                    |
| 2dp/3dp - Zero Float| | Idempotency-Key      |             | H9 Reverse+Repost   | |                    |
+---------------------+ +----------------------+             +---------------------+ +--------------------+
```

### Invariant 1: Append-Only, Typed Stock Movements (`StockBalance == Σ StockMovement`)
- `StockMovement` rows are append-only. They are **never updated or deleted** in business logic.
- For every `(company_id, product_id, warehouse_id, batch_id)` tuple:
  `StockBalance.on_hand == sum(quantity_delta for movements)`
- Direct updates to `StockBalance.on_hand` or `StockMovement.unit_cost` outside authorized engine functions (`stamp_cost`, `post_movement`) are prohibited and blocked by static CI guards.
- Stock headroom checks must execute under pessimistic row locks (`select_for_update`) on the `StockBalance` row before deducting inventory.

### Invariant 2: Completed Business Documents are the Single Source of Truth
- There are **no static customer or supplier ledger tables**.
- Account receivables (AR), account payables (AP), party exposures, and running balances are strictly **derived from completed business documents**, debit/credit notes, returns, and payment allocations.
- No cached balance columns may exist on customer or supplier tables that could drift from underlying documents upon an amend or cancel.

### Invariant 3: Single-Transaction Atomic Document Finalization
- Finalizing a document (`SalesService.complete`, `PurchaseService.complete`, `pos_checkout`) must execute within a single `transaction.atomic()` block.
- Document status change, sequential document-number assignment (using pessimistic lock on `DocumentSeries`), inventory deduction/addition, GL journal generation, and tax ledger postings must commit together.
- External side-effects (PDF rendering, SMS/email, search indexing, webhook dispatches) must be queued exclusively via `transaction.on_commit()`.

### Invariant 4: Airtight Multi-Tenant Isolation
- Every query, filter, update, and deletion across models must be scoped explicitly by `company_id`.
- Serializers must utilize `CompanyPrimaryKeyRelatedField` rather than raw `PrimaryKeyRelatedField(queryset=Model.objects.all())` to eliminate cross-tenant object injection (IDOR).
- Background Celery tasks and WebSocket workers must re-validate tenant boundaries before accessing or mutating tenant data.

### Invariant 5: Zero Floating-Point Arithmetic Across Monetary & Quantity Boundaries
- Currency values are strictly 2 decimal places (`Decimal("0.01")`).
- Quantities are strictly up to 3 decimal places (`Decimal("0.001")`).
- Floating-point types (`float`) are banned across all API serialization, database columns, tax calculation matrices, discount distributions, and ledger postings.
- Multi-line tax rounding must apply consistent rounding rules such that:
  `Invoice Grand Total == sum(Line Taxable + Line CGST + Line SGST + Line IGST + Line Cess) + Roundoff`

### Invariant 6: Strict Mutating Idempotency
- Every mutating HTTP endpoint handling inventory, money, or state changes must mandate and respect the `Idempotency-Key` header mapped through `MONEY_IDEMPOTENCY_SCOPES`.
- Replaying a request with the same idempotency key must return the identical response payload and HTTP status code without generating duplicate movements, ledger entries, or document numbers.

### Invariant 7: Statutory Period Closing & Immutable Audit Reversals
- Closed accounting/tax periods strictly reject any backdated creation, completion, amendment, or cancellation of documents.
- Any correction to a completed document within an open or closed period must follow the sanctioned **H9 Correction Path** (posting a strictly balanced reversing journal/movement pair and a subsequent corrected entry, maintaining an unbroken audit trail).

---

## 3. Freeze Scope Definition & Boundary Governance

Per `docs/FREEZE_SCOPE.md`, the platform perimeter is frozen into four distinct classifications. Any PR or proposal attempting to violate this boundary must be rejected.

```
+---------------------------------------------------------------------------------------+
|                                  FREEZE SCOPE TAXONOMY                                |
+---------------------------------------------------------------------------------------+
|  [A] SUPPORTED (Frozen Pilot Scope)       |  [B] NOT SUPPORTED (Dark / Flagged OFF)   |
|  - A1: Intra-state Sales Invoice          |  - Live GSTR Portal Auto-Filing           |
|  - A2: Inter-state Sales Invoice          |  - Live NIC E-Invoice / E-Way IRN         |
|  - A3: Nil-rated / Non-GST Invoice        |  - Manufacturing / BOM Work Orders (Dark) |
|  - A4: Quotations & Conversions           |  - Payroll & Attendance (Dark)            |
|  - A5: Sales Returns & Credit Notes       |  - CRM & Leads Pipeline (Dark)            |
|  - A6: Purchases (Atomic Stock + AP)      |  - WhatsApp Cloud API (Share-link only)   |
|  - A7: Purchase Returns & Debit Notes     |  - Account Aggregator Banking API         |
|  - A8: Barcode / SKU Product Lookup       |  - Postgres Row-Level Security (RLS)      |
|  - A9: Typed Append-Only Stock Movements  |  - Multi-Currency (INR Only)              |
|  - A10: Customer Receipts & Allocations   |  - Full Perpetual FIFO COGS               |
|  - A11: Supplier Payments & Allocations   |-------------------------------------------|
|  - A12: Derived Customer/Supplier Ledgers |  [C] KNOWN LIMITATIONS (Pilot Caveats)    |
|  - A13: Core Financial Reports (TB, P&L)  |  - C1: GSTR-1/3B are Offline Worksheets   |
|  - A14: PDF & Thermal Invoice Generation  |  - C2: E-Invoice Sandbox Preview Only     |
|  - A15: Data Imports (Products, Parties)  |  - C3: Running Weighted Cost Model        |
|  - A16: Statutory & Audit Exports         |  - C4: Books Module Opt-In per Company    |
|  - A17: Role-Based Access Control (RBAC)  |  - C5: Offline Drafts Plaintext on Device |
|  - A18: Company-Scoped Multi-Tenancy      |  - C6: SMS OTP requires provider config   |
|  - A19: First-Run Onboarding Wizard       |  - C8: Gateway Online Payments in Sandbox |
|  - A20: Auth & Session Management         +-------------------------------------------+
|  - A21: Period Locks & H9 Amendments      |  [D] RATIFIED EXPANSIONS (Decisions D1-14)|
|  - A22: 2dp/3dp Decimal Contract          |  - D1/A23: Counter POS (Atomic Checkout)  |
|  - A23: Counter POS & Offline Outbox      |  - D2/A24: TDS (194Q) & TCS (206C)        |
|  - A24: TDS / TCS Statutory Handling      |  - D3/A25: Online Gateway Sandbox         |
|  - A25: Payment Gateway Sandbox (Cashfree)|  - D4/A26: Mobile OTP Authentication      |
|  - A26: Mobile OTP Authentication         |  - D6: Fixed Assets & Depreciation Runs   |
|                                           |  - D7: TDS/TCS Return Worksheets & Certs  |
|                                           |  - D8: Reverse Charge Mechanism (RCM)     |
|                                           |  - D9: Composition Dealer & CMP-08 Aid    |
|                                           |  - D9b: Per-Unit Specific Cess (Pan Masala|
|                                           |  - D10: Bill of Entry (BOE) & Landed Cost |
|                                           |  - D11: Plan Limit & Quota Enforcement    |
|                                           |  - D12: Capacitor Android Shell           |
|                                           |  - D13: Automated Right-to-Erasure (DPDP) |
|                                           |  - D14: LLM Bill Extraction Hardening     |
+---------------------------------------------------------------------------------------+
```

---

## 4. End-to-End Workflow Verification Chains (WF-01 to WF-59)

The freeze verification suite executes complete, unbroken multi-step business transactions. Unit tests with mocked side-effects are disallowed on these chains.

```
Typical Lifecycle Chain:
[Draft Doc] -> [Add Lines/Taxes] -> [Complete (Atomic Txn)] -> [Stock Balance Decrement]
                                                            -> [GL Balanced Journal (TB=0)]
                                                            -> [Receipt/Payment Allocation]
                                                            -> [Return / Credit/Debit Note]
                                                            -> [Reversal / Net Zero TB Verification]
```

### Tier 1: Core Revenue, POS & Outbound Logistics
- **WF-01 (Intra-State Retail POS):** Create draft POS cart → Add barcode items → Apply cash tender with overpayment → Call atomic POS checkout → Assert: Invoice status `COMPLETED`, `StockBalance` deducted, `CashReceipt` created (capped at grand total), Change returned in note, Cashier cash GL debited, CGST/SGST credited, AR balance = 0.
- **WF-02 (B2B Inter-State Tax Invoice with Cess):** Create B2B invoice with inter-state customer GSTIN → Add items with ad-valorem GST + specific per-unit Cess (D9b) → Complete invoice → Assert: IGST calculated, Cess calculated, sequential invoice number allocated without gaps, GL balanced, GSTR-1 Table 4A/B aid populated.
- **WF-03 (Quotation to Cash Cycle):** Create Quotation → Convert to Sales Order → Generate Delivery Challan → Generate Sales Invoice → Record Bank Receipt → Allocate against invoice → Assert: Stock moves on Challan/Invoice per company setting, Quotation has zero financial impact, AR reconciles to ₹0.00.
- **WF-04 (Sales Return & Credit Note with Serial Tracking):** Completed serialized sales invoice → Issue Sales Return with Credit Note for subset of items → Assert: Serial numbers return to `AVAILABLE` status, Warehouse stock increments, Output GST liability reversed in GL, Credit note linked to original invoice in GSTR-1 Table 9B.

### Tier 2: Procurement, Customs & Inbound Logistics
- **WF-05 (Standard Inbound Purchase):** Create Purchase Bill → Add multi-rate line items → Complete bill → Assert: Warehouse stock increments immediately, AP account credited, Input Tax Credit (ITC) CGST/SGST accounts debited, GSTR-2B ITC comparison aid updated.
- **WF-06 (Purchase Cancellation & Stock Headroom Invariant):** Complete purchase bill → Consume 50% of purchased stock via sales invoice → Attempt to Cancel purchase bill → Assert:
  - If `company.negative_stock_policy == "BLOCK"`: Operation **must abort with 400 Bad Request** ("insufficient headroom to cancel").
  - If `company.negative_stock_policy == "WARN"`: Operation proceeds, stock goes negative, GL reversed.
- **WF-07 (Bill of Entry & Landed Cost Capitalization - D10):** Import purchase bill → Attach Bill of Entry (BOE) → Input Basic Customs Duty (BCD), Social Welfare Surcharge, IGST on Import, and freight clearing charges → Complete BOE → Assert: Customs duties and freight capitalized into inventory unit valuation, IGST routed to Import ITC account, AP reflects clearing agent and overseas vendor liabilities.

### Tier 3: Banking, Statutory Taxes & Dual-Entry Accounting
- **WF-08 (TDS & TCS Lifecycle - D2, D7):** 
  - Apply 206C(1H) TCS on sales exceeding ₹50L threshold → Verify TCS control GL credited.
  - Apply 194Q TDS on purchases exceeding ₹50L threshold → Verify TDS payable GL credited and supplier AP net deducted.
  - Generate quarterly TDS/TCS worksheets and Form 16A/27D aids → Verify math reconciles to GL voucher journals.
- **WF-09 (Reverse Charge Mechanism - D8):** Incur GTA (Goods Transport Agency) freight expense from unregistered transporter → Generate RCM Self-Invoice → Assert: Output GST tax liability debited to expense and credited to RCM Output Tax GL; corresponding RCM Input Tax Credit populated in GSTR-3B Table 4(A)(3).
- **WF-10 (Composition Scheme & CMP-08 - D9):** Configure company as Composition Dealer → Issue Bill of Supply (tax collected = 0) → Complete financial quarter → Generate CMP-08 quarterly aid → Assert: Total turnover calculated, composition tax rate (1% / 5% / 6%) applied accurately to turnover.
- **WF-11 (Period Close Enforcement & H9 Correction):** Close financial period for `YYYY-MM` → Attempt to post invoice or receipt in `YYYY-MM` → Assert: 400 rejection with `HelpCode("PERIOD_LOCKED")`. Trigger H9 Amend workflow on existing invoice → Assert: Reversing journal pair posted on current open date, original period remains pristine.
- **WF-12 (Automated Right-to-Erasure - D13):** Initiate DPDP erasure for designated company → Cascade delete operational records while retaining statutory tax logs per statutory retention requirement → Assert: `tenancy.no_orphans_after_erasure` holds, all PII wiped.

---

## 5. The Freeze Gate Hierarchy (FG-1 to FG-5)

The CI/CD pipeline and local release verification are partitioned into five mandatory, non-bypassable freeze gates. Every gate must be 100% green before release candidate sign-off.

```
+--------------------------------------------------------------------------------+
|                           THE FREEZE GATE HIERARCHY                            |
+--------------------------------------------------------------------------------+
  [FG-1: STATIC & CONFIG INTEGRITY]
    |-- guard_no_raw_unit_cost_update.py
    |-- guard_config_consistency.py (Flags in code == FREEZE_SCOPE.md exactly)
    |-- guard_regression_corpus_grows.py (Regression count monotonically non-decreasing)
    |-- guard_required_checks_match.py (ci.yml == REQUIRED_CHECKS.txt)
    v
  [FG-2: INVARIANT & WORKFLOW SUITE]
    |-- FG-2a: Invariant Sweeps (StockBalance==SUM, TB==0, Subledger Reconciled)
    |-- FG-2b: Money & Decimal Contract (Zero float, string scale, exact rounding)
    |-- FG-2c: Tax & Statutory Matrices (Place-of-supply, Cess, RCM, TDS/TCS)
    |-- FG-2d: Security & Multi-Tenancy (URL-conf sweep, IDOR defense, RBAC matrix)
    |-- FG-2e: Workflow Chains (WF-01 to WF-59 fully green, zero mocks on DB)
    |-- FG-2f: Golden Snapshots (Trial Balance, P&L, Balance Sheet, PDF renderings)
    |-- FG-2g: Contract Parity (Frontend TS models match DRF serializers)
    v
  [FG-3: DOMAIN RECONCILIATION & ACCOUNTING REHEARSAL]
    |-- Closed FY boundary roll-forward & retained earnings carry-over
    |-- Offline GSTR-1, GSTR-3B, CMP-08 reconciliation against ledger vouchers
    |-- Multi-rate, multi-godown stock valuation reconciliation against GL 1400
    v
  [FG-4: END-TO-END USER JOURNEYS & RESILIENCE]
    |-- Golden Playwright UI journeys (Onboarding -> POS -> Reports)
    |-- Offline outbox sync and conflict resolution (IndexedDB -> Postgres)
    |-- Error path validation (4xx problem details, zero unhandled 500s)
    v
  [FG-5: CONCURRENCY, DETERMINISM & NON-FUNCTIONAL LIMITS]
    |-- Postgres concurrent oversell & double-allocation stress tests
    |-- Frozen clock (TESTS_FREEZE_CLOCK=1) & socket ban (TESTS_NO_SOCKET=1)
    |-- Mutation testing on core engine paths (scripts/mutation_audit.sh)
+--------------------------------------------------------------------------------+
```

---

## 6. Defect Severity & Release Blocking Matrix

During the Quality Freeze, defects discovered across code reviews, automated suites, or manual verification must be classified and remediated under strict SLAs.

| Severity Level | Definition & Operational Impact | SLA / Gate Behavior | Examples in BizBoard |
| :--- | :--- | :--- | :--- |
| 🔴 **BLOCKER (P0)** | Fatal crash (500), silent data/money/stock corruption, broken multi-tenant isolation, broken atomic completion, skipped core test spec. | **Immediate Freeze Halt.** Zero merges permitted until resolved with red-then-green regression test. | - POS checkout HTTP 500.<br>- Unscoped serializer allowing cross-company read/write.<br>- StockBalance diverging from StockMovement. |
| 🟠 **CRITICAL (P1)** | Broken core statutory calculation, flawed invoice numbering sequence, failure of idempotency replaying, broken offline outbox sync. | **24-Hour Resolution.** Blocks release candidate promotion. | - Incorrect CGST/SGST split on inter-state supply.<br>- Duplicate document number issued under race condition.<br>- Over-tender booked as customer advance instead of cash change. |
| 🟡 **HIGH (P2)** | Flaky settlement UI, premature document finalization, unhandled edge-case validation failure, non-functional filter on core report. | **Must be resolved before Pilot Ratification.** | - UPI checkout committing before payment confirmation.<br>- Line discount rounding divergence against grand total > ₹0.05.<br>- Cancelled bill failing to clear serial lock. |
| 🔵 **MEDIUM (P3)** | Suboptimal error messaging, missing `HelpCode` mapping, minor UI layout glitch on rare viewport, unbounded query memory warning. | **Triaged.** Resolved if in pilot path, else documented in Known Limitations. | - Register report fetching 365 days without server pagination.<br>- Unclear copy on period-close modal. |
| ⚪ **LOW (P4)** | Cosmetic polish, non-critical translation string omission in secondary dialect. | **Post-Pilot Backlog.** Does not impede freeze. | - Minor margin discrepancy on mobile landscape view. |

---

## 7. Execution Protocol for Reviewers & Engineers

When instructed to audit, test, or stabilize any subsystem in BizBoard:

1. **Verify Environment Parity:**
   - Confirm active Python runtime is `3.13` (matching `ci.yml` and `.python-version`).
   - Run guard verification: `python scripts/ci_gates/run_guards.py --selftest`.
2. **Execute Invariant Audits:**
   - Run the invariant suite: `pytest backend/tests/test_invariants_smoke.py backend/tests/workflows/`.
   - Ensure `INVARIANTS_STRICT=1` is asserted on multi-tenant tests.
3. **Verify Anti-Flakiness Rules:**
   - Run test targets under `pytest-randomly` to ensure test independence.
   - Assert zero external network calls (`TESTS_NO_SOCKET=1`).
4. **Mandatory Red-to-Green Evidence:**
   - Any bug fix must be accompanied by a dedicated regression test in `backend/tests/regression/` or `backend/tests/test_review_2026_09_fixes.py`.
   - The test must be verified to fail against the unfixed code and pass definitively against the remediated code.
5. **Freeze Guard Monotonicity:**
   - Updating `backend/tests/regression/.corpus_count` is mandatory when adding regression tests; lowering the count is blocked by `guard_regression_corpus_grows`.

---
*Ratified by Principal Product Architect, QA Architect, Business Analyst, and Test Engineering Lead for BizBoard.*
