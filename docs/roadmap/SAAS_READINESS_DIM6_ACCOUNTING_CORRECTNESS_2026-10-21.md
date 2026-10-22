# SaaS readiness roadmap — Dimension 6: Accounting Correctness

**Date:** 2026-10-21 · **Status:** engineering items DIM6-01..16 built and tested 2026-10-22 (uncommitted; DIM6-01 commit deferred by the founder); DIM6-17..20 are people items — see [handover](SAAS_READINESS_HANDOVER_2026-10-22.md) · **Owner:** Founder + Eng + CA

**Dimension 6** is the sixth row of the readiness framework in
[BUSINESS_ARCHETYPES_AND_PERSONAS.md §9](../BUSINESS_ARCHETYPES_AND_PERSONAS.md):

> *Does the derived ledger balance with GL control (TB = 0)?* — current status **VERIFIED (Invariants)**

IDs in this doc use the prefix **DIM6-** so they do not clash with the freeze
decision **D6** (fixed assets) in [FREEZE_SCOPE.md](../FREEZE_SCOPE.md).
This roadmap feeds launch gate **G5 Integrity** in
[SAAS_READINESS_EXECUTION_PLAN.md](../SAAS_READINESS_EXECUTION_PLAN.md) and does
not replace it. For all nine dimensions and the NFRs on one scale, see
[SAAS_READINESS_ALL_DIMENSIONS_AND_NFR_2026-10-21.md](SAAS_READINESS_ALL_DIMENSIONS_AND_NFR_2026-10-21.md).
The build steps for these items are workstream F of
[SAAS_READINESS_IMPLEMENTATION_PLAN_2026-10-21.md](SAAS_READINESS_IMPLEMENTATION_PLAN_2026-10-21.md).

---

## 1. Why "VERIFIED" is not yet "SaaS ready"

"Verified" today means the ledger balances **in our test suite, on our seed
data, on one machine**. A SaaS product needs four more things:

| # | SaaS question | Today | Gap |
|---|---|---|---|
| 1 | Is there **one** truth for a company's money? | `Company.accounting_enabled` defaults to **False** ([accounts/models.py:260](../../backend/accounts/models.py)). With books off, figures come from documents. With books on, they come from the GL, and turning books on later relies on backfill commands (`backfill_missing_postings`, `backfill_accounting_postings`). | Two truth models per tenant, joined by a backfill. |
| 2 | Does **everything** that moves money or stock reach the ledger? | Several postings are behind flags that are **off by default**: `ACCOUNTING_POST_STOCK_ADJUSTMENTS`, `MFG_COSTING_GL`, `ENABLE_FIXED_ASSETS` (D6). Perpetual FIFO COGS is out of scope (QOS-0072). | TB can be 0 while the books still miss stock write-offs, production cost or depreciation. |
| 3 | Do we **notice** a wrong ledger within a day across thousands of tenants? | `nightly_invariants_task` ([core/tasks.py:186](../../backend/core/tasks.py)) loops over **every company in one task, one after another**, logs an error and opens a quarantine. No paging, no metrics, no time budget. | Will not finish at scale; failures are only in logs. |
| 4 | Has **someone outside the team** accepted the numbers? | CA sign-offs open: QOS-0004 (no CA has filed from our worksheets), QOS-0129, QOS-0130, QOS-0136, QOS-0138, QOS-0141, plus the F9 sheet in [CA_SIGN_OFF_CHECKLIST.md](../ca/CA_SIGN_OFF_CHECKLIST.md). No real company has run a month in parallel with Tally/Busy. | No external proof. |

What is already solid (do not rebuild):

- Write-time balance check: `post_journal` refuses unbalanced lines
  ([accounting/services.py:621](../../backend/accounting/services.py)) and
  `JournalEntry.assert_balanced` guards posted entries.
- Invariant library in `backend/core/invariants/` — `gl.journals_balanced`,
  `gl.trial_balance_zero`, `gl.no_orphan_lines`, `gl.party_subledger_complete`,
  closed-period check, plus `money`, `inventory`, `gst`, `projection`,
  `manufacturing`, `jobwork` modules. CI runs a strict lane (`INVARIANTS_STRICT=1`).
- AR/AP agreement matrix (`test_ar_ap_agreement_matrix.py`, 14 scenarios × books on/off) — QOS-0053 verified.
- GST period soft-close lock (QOS-0054), empty-journal backfill (QOS-0055) verified.
- Ten `*_concurrency_postgres.py` suites (accounting, notes, purchases, inventory, manufacturing, …).
- Cutover recon command (`cutover_recon`), restore drill, CA tax-parity corpus F1–F8.

---

## 2. Target: what "Dim 6 SaaS ready" means

All of these must be true and evidenced:

1. **One ledger.** Every company's GL is posted from day one, whatever the UI shows. No backfill on turn-on.
2. **Complete ledger.** Every stock, money, tax and production event in a released module posts to the GL, or is explicitly listed as "not in the books" on the Trial balance screen.
3. **Documents = GL.** AR, AP, stock value, GST payable and cash/bank from documents equal their control accounts, per company and per period, checked at runtime, not only in tests.
4. **Detected in < 24 h, at any tenant count.** Ledger checks fan out per tenant, finish inside a time budget, page a human and show in Django admin.
5. **Repairable safely.** Every repair is a dry-run-first, idempotent, audited command runnable for one tenant.
6. **Survives change.** Migrations, restores and new modules cannot ship if they break TB = 0 on a seeded multi-tenant database.
7. **Externally accepted.** A practising CA has signed, and ≥ 3 real companies have closed a month with zero unexplained difference against their old books.

---

## 3. Roadmap

Lanes follow the execution plan: **LLM** (engineering, can be built here),
**Split** (engineering done here, a person must run or sign), **Human**.

### Phase 0 — Baseline (week 1)

You cannot certify a tree that is not committed or a lane that is not running.

| ID | Item | Lane | Done when |
|---|---|---|---|
| DIM6-01 | Land the uncommitted money/stock work (manufacturing, inventory, money-in, notes, accounting screens) on `main` with CI green. | Split | Clean `git status` for money paths; CI green SHA recorded here. |
| DIM6-02 | **Ledger coverage map**: one table of every event that moves money/stock/tax → posting function → GL accounts → invariant that checks it → flag. Mark every row "posted / flag-gated off / not posted". | LLM | `docs/accounting/LEDGER_COVERAGE_MAP.md` + a test that fails when a new posting source has no row. |
| DIM6-03 | Confirm all ten `*_concurrency_postgres.py` suites actually **run** (not skip) in the Postgres CI job; make them required (QOS-0133). | LLM | CI log shows them executed; job is a required check. |

### Phase 1 — One complete ledger (weeks 2–4)

| ID | Item | Lane | Done when |
|---|---|---|---|
| DIM6-04 | **Decision: "shadow books".** Post the GL for every company from creation; `accounting_enabled` only controls what the UI shows. Removes the backfill-on-turn-on path and the second truth model. | Human decision → LLM build | Decision recorded; new companies always post; flipping the switch changes no numbers. |
| DIM6-05 | Migrate existing tenants to shadow books with a dry-run backfill and a before/after invariant sweep per tenant. | Split | Every tenant: backfill dry-run diff reviewed, applied, sweep clean. |
| DIM6-06 | **Close the flag-gated postings.** For `ACCOUNTING_POST_STOCK_ADJUSTMENTS` and `MFG_COSTING_GL`: CA sign-off, then default ON for new tenants with backfill for old ones. `ENABLE_FIXED_ASSETS` stays a known limitation unless the founder reopens D6. | Split | Flags ON in prod profile, or each one shown as "not in the books" on the Trial balance screen. |
| DIM6-07 | **Documents ↔ GL parity invariants** at runtime: AR vs 1200, AP vs 2100, stock valuation vs inventory account, GST payable vs GST control accounts, cash/bank vs bank ledgers — per company, per open period. Extend the AR/AP agreement matrix into `core/invariants/`. | LLM | New `gl.*_ties_to_documents` invariants in the strict CI lane; a perturbation test proves each one can fail. |
| DIM6-08 | **Property-based ledger test**: generate random sequences of invoices, receipts, returns, notes, adjustments, transfers, production runs, voids and period closes; assert all invariants after every step. | LLM | Hypothesis suite in CI (bounded examples) + a nightly long run. |

### Phase 2 — Operate it at SaaS scale (weeks 4–8, overlaps Phase 1)

| ID | Item | Lane | Done when |
|---|---|---|---|
| DIM6-09 | **Fan out the nightly sweep**: one Celery task per tenant (chunked queue), per-tenant time limit. Skip a tenant only if nothing changed in its ledger, stock or audit rows since its last clean pass; every tenant still gets a full sweep at least weekly. Record duration and result per tenant. | LLM | Sweep of a 1,000-tenant seeded DB finishes inside the nightly window; per-tenant result table. |
| DIM6-10 | **Alerting and ops view**: invariant failure → Sentry event + on-call page; a Django admin screen listing tenants by last sweep, failing keys and quarantine state (ops tools stay out of the customer app). | Split | Test failure fires a page; admin view shows it; time-to-detect < 24 h written as an SLO. |
| DIM6-11 | **Database backstop**: on Postgres, deferred constraint triggers on both the journal entry and journal line tables. They reject a commit that leaves a posted entry unbalanced or with no lines, including a DRAFT→POSTED flip, so a bug outside `post_journal` cannot write bad books. | LLM | Migration + tests for an unbalanced insert, an empty posted entry and a status flip, all failing at commit. |
| DIM6-12 | **Repair playbook**: the existing repair/backfill commands (`backfill_*`, `repair_bank_match_state`, `report_pos_cash_mispost`) all take `--company`, default to dry run, write an audit event, and are listed in one runbook with when to use each. | LLM | `docs/ops/LEDGER_REPAIR_RUNBOOK.md`; tests for dry-run and idempotency of each command. |
| DIM6-13 | **Migration ledger gate**: in CI, seed a multi-tenant DB at `main`, apply the branch's migrations, run the full invariant sweep; any new failure blocks merge. | LLM | Required CI job. |
| DIM6-14 | **Restore = balanced books**: the restore drill (13.3) and single-tenant restore end with a per-tenant invariant sweep; any failure fails the drill. | Split | Drill log with sweep output, run against a real off-host backup. |
| DIM6-15 | **Large-tenant timing**: run invariants and Trial balance/P&L/Balance sheet on a 3-year, high-volume tenant (`seed_load_tenant`); fix any check that does not finish in budget (links QOS-0003). | Split | Timings recorded; reports under agreed budget. |
| DIM6-16 | **New-module rule**: a feature flag that moves money or stock cannot be classified ON in `FREEZE_SCOPE.md` without a row in the coverage map (DIM6-02) and an invariant. Enforce in the existing `config_consistency` guard. | LLM | Guard fails on a test flag with no coverage row. |

### Phase 3 — External proof (weeks 6–12, calendar bound by people)

| ID | Item | Lane | Done when |
|---|---|---|---|
| DIM6-17 | **One combined CA engagement** covering F9, QOS-0004, 0129, 0130, 0136, 0138, 0141 and the DIM6-06 flags. Send one evidence pack, not seven requests. | Human | Signed letter stored in `docs/ca/`. |
| DIM6-18 | **Cutover reconciliation on real books**: ≥ 5 pilot companies' opening balances imported; `cutover_recon` shows variance 0 or explained (step 6.5). | Split | Signed recon sheet per company. |
| DIM6-19 | **Parallel month**: 2–3 pilots run one full month in Bizboard alongside Tally/Busy; compare Trial balance, P&L, Balance sheet, GSTR-1/3B worksheets at month end. | Human + Split | Zero unexplained difference; every explained difference logged. |
| DIM6-20 | **Sign G5** with the evidence above. | Human | G5 marked signed in the execution plan. |

### Continuous (after launch)

- Weekly report: tenants swept, failures, mean time to repair, trend on the `qos-history` branch.
- Every incident that changed a ledger gets a regression case in the property-based suite (DIM6-08).
- Quarterly CA spot check of three random tenants' books.

---

## 4. Sequence and critical path

```
DIM6-01 ─┬─ DIM6-02 ─┬─ DIM6-06 (needs CA) ─────────────┐
         │           └─ DIM6-16                          │
         ├─ DIM6-03                                      ├─ DIM6-17 CA ─┐
         └─ DIM6-04 decision ─ DIM6-05 ─ DIM6-07 ─ 08 ───┘              ├─ DIM6-20 G5
DIM6-09 ─ DIM6-10        DIM6-11  12  13  14  15 (parallel)             │
DIM6-18 cutover recon ─ DIM6-19 parallel month ─────────────────────────┘
```

The critical path is **people, not code**: the CA engagement (DIM6-17) and the
parallel month (DIM6-19). Book the CA and recruit the pilots in week 1 so the
engineering phases finish before they are needed.

Rough effort for the LLM lane: Phase 0 ≈ 1 week, Phase 1 ≈ 2–3 weeks,
Phase 2 ≈ 3–4 weeks. Phase 3 depends on the CA's and pilots' calendars.

---

## 5. Decisions needed from the founder

| # | Question | Recommendation |
|---|---|---|
| Q1 | Shadow books for every company (DIM6-04)? | **Yes.** One truth model is the single biggest correctness gain for a multi-tenant product. |
| Q2 | Turn on stock-adjustment and manufacturing GL posting after CA sign-off (DIM6-06)? | **Yes**, for new tenants first, then backfill old ones. |
| Q3 | Fixed assets (D6) — stay a known limitation for SaaS launch? | **Yes**, but show it on the Trial balance screen as "not in the books". |
| Q4 | Which 2–3 pilots run the parallel month (DIM6-19)? | ARCH-03 trade businesses already in the pilot list. |
| Q5 | Ledger-failure SLO? | Detect < 24 h, tenant told within 1 business day, repaired or explained within 3. |
