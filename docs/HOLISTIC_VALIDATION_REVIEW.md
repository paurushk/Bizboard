# BizBoard Holistic Validation — Operating Model & Review

**Status:** Canonical quality model + diagnostic review · **Date:** 2026-09-14 · **Rev:** 2.3 (C6-80 signed; 80-plan S0–S7 evidenced; 95-plan V2–V6 evidenced) · **Owner:** QA + founder  
**Inputs:** `TESTING_STRATEGY.md`, `CROSS_FLOW_IMPACT_MAP.md`, `FREEZE_SCOPE.md`, `web/src/App.tsx`, `web/src/navigation/menu.ts`, `backend/tests/personas/`, `web/e2e/`, `web/e2e-golden/`  
**Companions:** [`HOLISTIC_VALIDATION_IMPLEMENTATION_PLAN.md`](HOLISTIC_VALIDATION_IMPLEMENTATION_PLAN.md) (HOW) · [`HOLISTIC_VALIDATION_80_PLAN.md`](HOLISTIC_VALIDATION_80_PLAN.md) (session target 80% per dimension) · [`HOLISTIC_VALIDATION_95_PLAN.md`](HOLISTIC_VALIDATION_95_PLAN.md) (90 then 95; V2–V6 done, V0/V1/V7–V12 still human) · Cursor IDE canvases are not git artifacts

This file has two jobs:

1. **Operating model** — the single BizBoard Quality Model. Other docs are *views* of it, not competing frameworks.
2. **Diagnostic review** — what the current suite actually covers across every UI/channel flow, and what is still a product-truth gap.

It does **not** replace `TESTING_STRATEGY.md` (how we test) or `CROSS_FLOW_IMPACT_MAP.md` (impact/reader index). It *does* define the philosophy those documents must implement.

**Do not start by writing dozens of new tests.** First stand up the architecture in §0.4. Tests are derived from the catalogs once they exist.

---

## 0. Operating model

### 0.1 The question that changed

BizBoard is getting good at proving that **individual capabilities work**. It is not yet equally good at proving that the **entire business experience remains truthful after those capabilities interact over time**.

> A green suite currently proves that BizBoard **did not corrupt itself**. It does not yet prove that **a user can trust what BizBoard is telling them**.

That distinction is the validation philosophy. G-17 (a fully returned invoice showing **Paid**) is the canonical **product-truth failure**: API 200, books balanced, unit tests green, invariants green — and the customer still formed the wrong picture of their money.

The question is no longer “did we test the feature?” It is:

> **After a real business event happens, does BizBoard continue telling the same truthful story everywhere the user encounters it — including after the next event, a reversal, and time has passed?**

### 0.2 One quality hierarchy (resolve competing authorities)

There is **one** BizBoard Quality Model. L1–L10, T1–T7, and Q-OS are not three frameworks.

```text
                    BIZBOARD QUALITY MODEL   ← this document (§0)
                              │
              ┌───────────────┴───────────────┐
              │                               │
     VALIDATION METHOD                  QUALITY OUTPUT
     TESTING_STRATEGY.md                Q-OS backlog / frontier
     layers L1 → L10                    PRODUCT_QUALITY_BACKLOG.md
              │
     ┌────────┼────────┐
     ↓        ↓        ↓
   Flow     Impact    Truth     ← three linked graphs (§0.3)
   Graph    Graph     Graph
     │        │        │
     └────────┼────────┘
              ↓
        PRODUCT TRUTH
              ↓
     USER UNDERSTANDING
              ↓
     BUSINESS DECISION
              ↓
     LONG-TERM CONSISTENCY
```

| Artifact | Role in the model | Must not do |
|---|---|---|
| **This file** | Philosophy, graphs, operating sequence, flow-coverage diagnosis | Invent a second layer numbering |
| [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md) | Method: L1–L10, five+one questions, gap register, gates | Claim T1–T7 or Q-OS as a parallel method |
| [`CROSS_FLOW_IMPACT_MAP.md`](CROSS_FLOW_IMPACT_MAP.md) | **Impact graph** — writers/readers; evolving from field→readers to event→projections | Remain the whole framework |
| [`FREEZE_SCOPE.md`](FREEZE_SCOPE.md) / [`FREEZE_SCOPE_COVERAGE.md`](FREEZE_SCOPE_COVERAGE.md) | What is in scope; per-item gating test | — |
| [`FULL_SPECTRUM_PERSONA_VALIDATION_PLAN.md`](FULL_SPECTRUM_PERSONA_VALIDATION_PLAN.md) | **L4 view** (persona × archetype index). T1–T7 maps onto L1–L10; it is not a second pyramid | Close freeze coverage by counting dark-module tests |
| [`Q-OS_QUALITY_PIPELINE_PLAN.md`](Q-OS_QUALITY_PIPELINE_PLAN.md) | **Output** — ranked quality backlog from evidence | Define its own test layers |
| [`FLOW_CATALOG.md`](FLOW_CATALOG.md) (generated) | Machine-readable Graph 1; CI drift gate (advisory until A3) | Stay a hand-maintained Markdown table; count `dark_module` as freeze coverage |
| [`HOLISTIC_VALIDATION_80_PLAN.md`](HOLISTIC_VALIDATION_80_PLAN.md) | Session target: 80% per §0.9 dimension | Redefine High; mint C6-80 without this file’s §0.10 |
| [`HOLISTIC_VALIDATION_95_PLAN.md`](HOLISTIC_VALIDATION_95_PLAN.md) | Path to ~90 High-locked then ~95 freeze/go-live | Flip A3 early; claim Insight High without H-05; treat 95 as more goldens |

Capability correctness and data integrity are the **current edge**. Product truth, user understanding, decision quality, and long-term consistency are what this model closes.

### 0.3 Three linked graphs

Holistic validation is the intersection of three graphs, not more tests.

**Graph 1 — Flow**

```text
User → Action → Business event → Next possible actions
```

Generated from `App.tsx`, in-page money actions, and public channels. Each node has freeze disposition, persona, archetype, and coverage label (`JOURNEY` / `API-ONLY` / `SMOKE` / `FLAG-OFF` / `GAP` / `OUT`).

**Graph 2 — Impact**

```text
Business event → Canonical state → Writers → Readers / projections
```

Today’s `CROSS_FLOW_IMPACT_MAP.md` is the **field-level reader index** of this graph. The missing primitive is the **event**:

```text
SALES_RETURN
    → invoice state
    → stock, GL, AR, GST, credit/debit note
    → customer ledger, sales register, dashboard
    → attention, dunning, reports
    → invoice badge, PDF, public payment page, notifications
```

**Graph 3 — Truth**

```text
Metric → definition → formula → source documents
      → projection surfaces → user interpretation → decision
```

Identity rule: **two computations of the same named metric must agree. Two different metrics must not share a label.**

```text
Customer outstanding
        ↓
   ┌────┼────────────┐
   ↓    ↓            ↓
Ledger Dashboard   Aging   Attention
```

If those read ₹80,000 / ₹75,000 / ₹82,000 / ₹78,000, the product has failed even if **no module crashes**. That is why projection identity is an **L1-class invariant**, not ordinary reconciliation.

```text
              FLOW
               │
               ▼
            EVENT
               │
        ┌──────┴──────┐
        ▼             ▼
     IMPACT          TRUTH
        │             │
        └──────┬──────┘
               ▼
          USER DECISION
```

### 0.4 Time is part of the chain

Many BizBoard defects are not visible on the next response. The canonical validation chain is:

```text
USER ACTION
    → INTENT
    → CANONICAL STATE
    → ACCOUNTING / INVENTORY / TAX STATE
    → PROJECTIONS
    → USER SURFACES
    → USER DECISION
    → SUBSEQUENT EVENT
    → REVERSAL / AMENDMENT / RETURN
    → HISTORICAL TRUTH
```

In one sentence: **event → consequence → interpretation → decision → subsequent event → historical integrity.**

A sale is not `Create invoice → API succeeds`. It is:

`Create → Complete → stock → AR → GST → reports → dashboard → attention → later payment → return → residual → all affected surfaces remain truthful — and a closed month does not silently rewrite.`

### 0.5 API correctness ≠ user-visible correctness

These are **separate dimensions**.

| API can prove | User journey must prove |
|---|---|
| `POST /complete` → 200, status COMPLETED | Click Complete → confirm → loading → badge → stock widget → payment state → allowed next actions → dashboard → report |

Clerks do not POST the API. Coverage labels `API-ONLY`, `SMOKE`, and `JOURNEY` exist so we cannot pretend the first is the third. Smoke means “did not crash.” It is compatible with every number on the page being wrong.

### 0.6 Decision quality is a core product dimension

Beyond “is the number correct?”:

> **Would acting on this information be the right operational move?**

Example: outstanding = ₹100,000 may be arithmetically true, but if ₹60,000 is disputed, ₹20,000 is returned, and ₹20,000 is collectible, then Attention saying “Collect ₹100,000 immediately” is a **decision-quality failure**. The data is right; the business advice is wrong.

`/attention`, dashboard KPIs, dunning, health, and cash-flow are **live decision surfaces** even when `ENABLE_AI=0`. They are in scope.

### 0.7 Topology over volume

Do **not** add another 50 persona tests that only end in `assert_all_invariants`. Invariants do not see a “Paid” badge or a bad collect-now recommendation.

The problem is **insufficient test topology**, not insufficient test count. One lifecycle golden that connects Owner × Retail × sale × payment × return × residual × dashboard × attention × ledger × stock is worth more than ten isolated CRUD tests.

### 0.8 Architecture first — then derive tests

Implement in this order. Do not skip to a pile of specs.

```text
Flow Catalog (generated)
  → Event Catalog
  → Impact Matrix (event × projection)
  → Projection Identity Registry
  → Lifecycle goldens (ARCH-01, ARCH-03)
  → Decision / UX assertions
  → CI gates (new route / new writer / unlabeled metric = build blocked)
```

Target CI signal:

```text
NEW ROUTE DETECTED  /payments/refund
Coverage:
  no journey
  no projection mapping
  no persona validation
BUILD BLOCKED
```

The flow catalog is generated (`FLOW_CATALOG.md`). §2 below is a **frozen** diagnostic snapshot (P1-T6); live coverage is the generated file.

### 0.9 Confidence if the current suite is green

| Claim | Confidence |
|---|---|
| At-rest stock / GL / subledger consistency | **High (~90%)** — V3 G-11b dump→migrate→restore + Linux `mutation-audit` advisory lane; `INVARIANTS_STRICT` still red-capable |
| A named SUPPORTED workflow completes its own job (API) | **High (~80%)** — S0 catalog honesty + S1b `/purchases/history` + `/invite` journeys. Single-flow **lock** is V1 / A3 |
| The user can perform that job in the UI and see the consequence | **High (~80%)** — V2 freeze workflows are JOURNEY; published 90 waits for V1 catalog lock (**90-pending-lock**) |
| After a return / residual / amendment, every screen still tells the same story | **High (~90%)** — required `e2e-golden` ARCH-01/03 + purchase residual + accounting journal stay in CI (not `test.fixme`) |
| Attention, dunning, and dashboard are safe to act on | **Medium-high (~80%)** — C6-80 signed; residual `code`, dunning RETURNED+residual, KPI=aging. **Not High** (H-05) |
| UX / mental-model truth | **Medium-high (~80%)** — C6-80 signed; glossary, recon labels, Hindi outstanding/Returned, B14 GSTIN prompt. **Not High** (H-05 / live-shop copy / V7) |
| Historical truth after a later event | **High (~90%)** — V4 closed N **and** N−1 reject backdated Complete; as-of N snapshot unchanged after N+1 |

**Headline:** 80-plan S0–S7 plus 95-plan **V2–V6** are evidenced. Decision-quality and UX stay **Medium-high**, not High. Flow-catalog / writer-impact remain advisory until A3's two consecutive green CI weeks (**V0 dates blank; V1 not flipped**). Do not treat `dark_module` persona tests as freeze coverage — generated `FLOW_CATALOG.md` is the route-count source.

Percents in parentheses are **illustrative anchors**, not coverage %. The **band** is the claim. A later 80-plan session may publish 80% on a row only when that plan’s rubric is fully met; that still does not promote Insight/UX to **High**.

### 0.10 Founder decisions on the quality bar (locked 2026-09-14)

Product-truth and quality-bar calls that downstream plans must not mint only in themselves. Implementation plan §0a repeats the operational rows (B*, D15, B13, B14).

| Id | Decision | Locked answer |
|---|---|---|
| **C6** | May automation declare decision-quality **High**? | **No.** Runbook exit is **Medium-high**. True High is H-05 / L7 live-shop fieldwork (this file §11). |
| **C6-80** | May Insight/UX automation go past Medium-high (~70%) toward **80%**? | **Signed 2026-09-14.** Founder instructed to implement `HOLISTIC_VALIDATION_80_PLAN.md` with nothing left partial. 80% is claim-ready-plus, **still not High**. High remains H-05. |
| **A3** | Flow-catalog / writer-impact blocking on day one? | **No** — advisory until two consecutive green CI weeks. |
| **B13** | Who may close an accounting period? | **Owner only** (`IsOwner` on close/soft-close; BB-000453). Accountant posts journals and reads reports; 403 on close. |
| **B14** | Regular company, wizard skipped, empty GSTIN | Do **not** silently flip Non-GST. Prompt/block GST Complete until GSTIN is saved. Period close already treats `GSTIN_MISSING_COMPANY` as critical. |

**80% vs this table:** [`HOLISTIC_VALIDATION_80_PLAN.md`](HOLISTIC_VALIDATION_80_PLAN.md) is a *session* bar so LLM work has a checkable rubric. It does not replace Low/Medium/High. Hitting 80% on Insight/UX without C6-80 is out of policy. Hitting 80% with C6-80 still leaves a tracked gap to High (H-05).

---

## 1. How coverage was judged (diagnostic)

A user flow is **covered in the strategy** only if all of the following are true:

1. It is **named** as a journey, freeze item, or gap (not merely implied by “~90 pages”).
2. A **gating test** would go red if the behaviour regressed.
3. The test asserts the **user-visible consequence**, not only that a route mounted.

Coverage labels used below:

| Label | Meaning |
|---|---|
| **JOURNEY** | Browser or API drives the flow end-to-end and asserts business outcome (stock, AR/AP, tax, GL, or a named identity). |
| **API-ONLY** | Persona/workflow test exists; the UI for the same job is not journey-tested. |
| **SMOKE** | Page renders without crash / error boundary (often mocked; heading-or-Retry). Does **not** prove the job works. |
| **FLAG-OFF** | Test asserts LimitedAccess / 404 when the module is dark. Proves inaccessibility, not the flow. |
| **UNIT** | Component/unit tests (badges, helpers, a11y on a fixture). |
| **UAT** | Named only in pilot UAT / hypotheses. Not merge-blocking. |
| **GAP** | Reachable user flow with no strategy-named gate that would catch a wrong business outcome. |
| **OUT** | Freeze NOT SUPPORTED / dark. Only inaccessibility should be gated. |

Smoke is **not** journey coverage. `reports-domain.spec.ts` and `settings-domain.spec.ts` explicitly accept “heading, Retry, or limited-access landing.” That catches crashes. It does not catch a wrong total, a stale KPI, or a contradictory badge.

---

## 2. Inventory of user flows vs the strategy

> **FROZEN 2026-09-13 (P1-T6).** Do not edit this section again. Live coverage is [`FLOW_CATALOG.md`](FLOW_CATALOG.md) (generated from `web/src/App.tsx`). This snapshot is historical diagnostic prose only.

Source of truth for “does this flow exist?” is `App.tsx` + `navigation/menu.ts` + public routes + in-page actions (complete, allocate, print, share, offline flush). Freeze disposition is `FREEZE_SCOPE.md`.

### 2.1 Public / unauthenticated

| Flow | Route / channel | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| Login (password) | `/login` | A20 SUP | Named | e2e-golden + a11y | **JOURNEY** (thin) |
| Register → first company | `/register` | A19 SUP | Named | e2e-golden accounting/invoice helpers | **JOURNEY** |
| OTP login | login OTP | A26 SUP | Named | API (`test_wf18` skipped; OTP hashing elsewhere) | **API-ONLY / partial** — UI OTP path not a golden journey |
| Forgot password | `/forgot-password` | A20 implied | **Not named** | none found | **GAP** |
| Reset password | `/reset-password` | A20 implied | **Not named** | none found | **GAP** |
| Accept invite | `/invite` | A17/A19 | PJ-FTUE invite is API | no e2e of `/invite` | **API-ONLY** |
| Public payment page | `/pay/:token` | A25 SUP | Webhook/allocation named; **page not named** | none found | **GAP** (customer-facing money UI) |
| Unauthenticated deep-link | any protected URL | A20 | G-5 adjacent | `route-smoke-unauthenticated` on **20** routes only | **partial SMOKE** |
| 404 | `*` | — | Not named | none | **GAP** (low risk) |

### 2.2 First-run, home, attention

| Flow | Route | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| Setup wizard | `/setup` | A19 SUP | Named (PJ-FTUE + golden) | API FTUE; golden register→dashboard. **Wizard click-through not golden.** | **API-ONLY** |
| Owner forced into setup | `/` → `/setup` | A19 | PJ onboarding derivation | `test_cross_flow_consistency` (API) | **API-ONLY** |
| Dashboard (Sethji) | `/` | A13 + delight | Named; KPI==drill-down **partial** | page badge UNIT (G-17); no KPI identity after return | **UNIT + thin JOURNEY** |
| Staff home (no financials) | `/` → first nav | A17 | Weak assumption 6; LimitedAccess | role-boundaries; not a journey | **SMOKE / GAP** for mental model |
| Attention Center | `/attention` | Live for finance roles; **not** `ENABLE_AI` | Insights PJ exists; **route almost unmentioned** | reports-domain SMOKE; mobile-layout | **GAP as a decision UI** |
| Help | `/help` | Help v1 SUP | HelpCode mapping | `help.spec.ts`, FTUE help codes | **JOURNEY** (intents) |
| Help health | `/settings/help` | Help v2 OUT | FLAG | help.spec reaches it | **FLAG-OFF / limited** |
| Offline outbox | `/offline-outbox` | C5 LIM | H-03 named | `offline-outbox-conflict.spec.ts` | **JOURNEY** (copy/conflict) |

**Issue:** `TESTING_STRATEGY.md` treats “AI insights” as out of scope (`ENABLE_AI=0`) while `/attention` is a first-class nav item for anyone with financial reports. Attention, dunning, payment-health, and dashboard KPIs are **live decision surfaces**. Calling them “AI” and skipping them is a coverage hole, not a scope decision.

### 2.3 Counter POS (ARCH-01)

| Flow | Route / action | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| POS checkout cash/UPI | `/pos` | A23 SUP | Named (WF-19, PJ-RETAIL, H-02) | golden POS; API WF-19; keyboard spec **executed chromium (G-6b, 2026-09-15)** | **JOURNEY** backend; **UI delight proxy ✅**; live H-02 L7 |
| POS warehouse / godown pick | `/pos` + warehouses | A23 | Weak | POS golden visits warehouses | **thin JOURNEY** |
| Thermal print | POS complete | A23 | Named “when available” | not asserted in golden | **GAP** |
| POS shift / drawer | in-page | delight / PJ | `test_pj_pos_shift_and_cash_reconciliation` | **API-ONLY** | |
| Scanner double-fire / focus loss | `/pos` | H-02 | Named as go-wrong | G-16 unautomated | **UAT / GAP** |
| Offline POS draft wipe on sign-out | C5 | Named | outbox + wipe tests | **partial JOURNEY** | |

### 2.4 Sales (the core commercial loop)

| Flow | Route / action | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| New GST invoice | `/sales/new` → complete | A1–A3 SUP | Named | invoice golden; WF-01/02; PJ | **JOURNEY** (happy path) |
| Edit draft / reopen | `/sales/history/:id/edit` | A1 | Implied | purchase-list has edit smoke; sales edit **not** a named journey | **GAP** (sales edit) |
| Invoice detail + badge | `/sales/history/:id` | A1 + trust | G-17 | UNIT matrix (status × payment × return) | **UNIT** — not e2e after a real return |
| Sales history list badge | `/sales/history` | G-17 | UNIT | **UNIT** | |
| Quick entry | `/sales/quick-entry` | A1 adjacent | **Not named** | `QuickEntryPage.test.tsx` UNIT only | **GAP** (reachable create-sales UI) |
| Quotations → invoice | `/sales/quotations` | A4 SUP | Named WF-06 | API WF-06; list is SMOKE | **API-ONLY** |
| Sales orders → invoice | `/sales/orders` | A4-adjacent | WF-09 | phase1-documents golden (create order); convert thin | **partial JOURNEY** |
| Delivery challan → invoice | `/sales/delivery-challans` | stock + period (G-22) | WF-10; G-22 cancel gate | API; **UI list/editor SMOKE at best** | **API-ONLY** |
| Recurring invoices | `/sales/recurring` | retainers OUT; page still in nav | WF-11 skipped | route-smoke only | **GAP** if enabled; else **FLAG** unclear |
| Sales returns | `/sales/returns` | A5 SUP | Named | phase1-documents; PJ-returns | **partial JOURNEY** |
| Credit notes | `/sales/credit-notes` | A5 SUP | Named | phase1 CN new; notes map consistent | **partial JOURNEY** |
| Debit notes (sales) | `/sales/debit-notes` | residual AR (G-20/G-23) | **Route not named**; residual only in API regressions | **no e2e** | **GAP** (the exact state-space of G-20/G-23) |
| Customers | `/sales/customers` | A12 | Named | golden visits list | **thin JOURNEY** |
| Receipts + allocate | `/sales/receipts` | A10 SUP | Named | invoice/payments golden | **JOURNEY** (happy path) |
| Partial allocation / reverse | receipts in-page | A10 + H-01 | Named API | allocation tests API | **API-ONLY** for reverse/unallocate UI |
| Bill upload (sales) | `/sales/bill-upload` | D14 LIM | LLM failure named | **no e2e of the page** | **GAP** |
| PDF / print / share | invoice detail | A14 SUP | Named snapshot | PDF text snapshot API; **UI download/share UAT G6** | **API snapshot + UAT** |
| e-invoice / e-way panel | invoice/note | C2 LIM / OUT live | PJ-einvoice API | **UI panel not golden** | **API-ONLY** |
| Credit-limit block copy | complete invoice | ARCH-03 | Named HelpCode | API + HelpErrorAlert UNIT | **API-ONLY** |
| Cancel completed invoice | detail action | A17 | PJ deny-set | API | **API-ONLY** |
| H9 amend | detail / period | A21 SUP | Named WF-44 | API | **API-ONLY** |

### 2.5 Purchases

| Flow | Route / action | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| New purchase complete | `/purchases/new` | A6 SUP | Named | purchase golden; WF-04 | **JOURNEY** |
| Purchase detail | `/purchases/history/:id` | A6 | G-17 parity UNIT | UNIT (no payment overlay) | **UNIT** |
| Purchase edit | `/purchases/history/:id/edit` | A6 | — | list-and-editor SMOKE | **SMOKE** |
| Suppliers | `/purchases/suppliers` | A12 | Named | golden | **thin JOURNEY** |
| Supplier payments | `/purchases/payments` | A11 SUP | Named | purchase golden | **JOURNEY** (happy path) |
| Purchase returns | `/purchases/returns` | A7 SUP | Named | API WF-05; UI SMOKE | **API-ONLY** |
| Purchase CN / DN | `/purchases/credit-notes`, `debit-notes` | A7 + G-18 residual AP | API G-18 | notes-and-orders SMOKE | **API-ONLY**; **UI GAP** for residual DN |
| Purchase orders | `/purchases/orders` | A6-adjacent | WF-16 | SMOKE | **SMOKE / API-ONLY** |
| Bills of Entry | `/purchases/bills-of-entry` | D10 LIM / OUT | limitation guards | FLAG-OFF intended | **OUT** — map still has live RETURNED-unlink inconsistency **ungated** |
| Bill upload (purchase) | `/purchases/bill-upload` | D14 | Named LLM | route in PROTECTED_ROUTES SMOKE | **SMOKE** |
| GRN complete/cancel | **no nav route** (service) | not frozen purchase path | G-21 API | **no UI flow** | API gated; users on frozen path do not see GRN — OK for freeze, still a writer on the map |

### 2.6 Payments, banking, public collection

| Flow | Route / action | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| Payment links | `/payments/links` | A25 | Named webhook more than UI | payments-domain SMOKE | **SMOKE** |
| Customer pays via link | `/pay/:token` | A25 | **Not named as UI** | **GAP** | **GAP** |
| Bank statements import | `/payments/statements` | WF-41 / G-3 | Named API | SMOKE + API | **API-ONLY** |
| Bank reconciliation | `/payments/reconciliation` | G-3 ✅ API | Named | SMOKE (mocked) | **API-ONLY** |
| Account Aggregator | `/payments/account-aggregator` | OUT | FLAG | SMOKE / FLAG | **OUT** |
| Gateway webhook | inbound | A25 | Named; G-8 closed | API adversarial | **JOURNEY** (API) |
| Dunning settings | company settings | share-link LIM | G-20 API | **no UI journey** | **API-ONLY** |
| Cash book | `/reports/cash-book` | A13 | implied reports | SMOKE | **SMOKE** |

### 2.7 Inventory

| Flow | Route / action | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| Products CRUD | `/inventory/products` | A8–A9 | Named lookup | item-custom-fields; products page | **partial JOURNEY** |
| Current stock | `/inventory/stock` | A9 | Named | golden after sale/purchase | **JOURNEY** (qty visible) |
| Low stock | `/inventory/low-stock` | insights WS3 | Named alert | API closed-loop; **page not golden** | **API-ONLY** |
| Expiry alerts | `/inventory/expiry-alerts` | ARCH-05 COND | H-04 API | **no e2e of page** | **GAP** (UI) |
| Adjustments | `/inventory/adjustments` | A9 | WF-22 | golden helper; API | **partial JOURNEY** |
| Warehouses | `/inventory/warehouses` | ARCH-04 COND | PJ-WHOLE | POS golden visits | **thin** |
| Stock counts | `/inventory/stock-counts` | ARCH-04 | PJ-custodian API | **no e2e** | **API-ONLY** |
| Transfers | `/inventory/transfers` | ARCH-04 | WF-21 API | **no e2e** | **API-ONLY** |
| Serials | `/inventory/serials` | ARCH-06 COND | PJ-serialized API | **no e2e** | **API-ONLY** |
| Label print | `/inventory/labels` | not freeze-named | **Not in strategy** | UNIT only | **GAP** |
| Unit-of-measure change | item dialog | stock integrity | `test_unit_change_open_documents` | API | **API-ONLY** |

### 2.8 Reports (user comes here to *understand* the business)

| Flow | Route | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| Sales / purchase / inventory registers | `/reports/sales` etc. | A13 SUP | Named `cross_reconcile` **overclaimed** (GL-only, not registered) | WS2 API identities; e2e SMOKE | **API identity partial; UI SMOKE** |
| Customer / supplier ledger | `/reports/*-ledger` | A12 SUP | Named | API; UI SMOKE | **API-ONLY** |
| Stock valuation | `/reports/stock-valuation` | A13 | Named | **golden** | **JOURNEY** (rare report that is golden) |
| TB / P&L / BS / books health | `/reports/trial-balance` etc. | A13 + C4 | Named | accounting golden TB/P&L; mocked e2e is FLAG-OFF books | **JOURNEY** when books on; **FLAG-OFF** in default e2e |
| GSTR-1/3B worksheets | `/reports/gstr1`, `gstr3b` | C1 LIM worksheets | Named snapshots + WF-27 | API; UI SMOKE | **API-ONLY** |
| GSTR-4/6/7/8/9, CMP-08, 2B, missing docs, GST health, rate exposure | `/reports/gstr*` … | C1 / composition deprioritized | computation LIM; **pages not journeys** | SMOKE only | **SMOKE** |
| TDS/TCS reports | `/reports/tds-tcs` | A24 SUP | Named computation | API WF-34–36; UI SMOKE | **API-ONLY** |
| Statutory events | `/reports/statutory-events` | — | **Not named** | SMOKE | **GAP** |
| CA-needs | `/ca-needs` | H-05 | Named as human | SMOKE alias of missing-docs | **UAT (H-05)** |

### 2.9 Insights (flagged) vs live analytics

| Flow | Route | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| Insights hub / health / cashflow / alerts | `/insights/*` | OUT (`ENABLE_AI=0`) | “out of scope” | e2e **FLAG-OFF** (enable-AI CTA) | **OUT for UI** |
| Health score / cashflow / alerts **APIs** | used by attention & PJ | **Live backend** | G-18/19 WS3; one founder sync test | API | **thin JOURNEY** — not after return/residual |
| Assistant | `/insights/assistant` | OUT | OUT | FLAG-OFF | **OUT** |

### 2.10 Accounting module (opt-in)

| Flow | Route | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| Enable accounting (no backfill) | `/settings/accounting` | C4 | Map documents backfill **product gap**; **not a test** | golden enables flag | **JOURNEY** enable; **GAP** historical-posting UX |
| Chart of accounts / journals | `/accounting/*` | C4 | WF-29, PJ-ACCT | golden journal; mocked e2e FLAG-OFF | **JOURNEY** (golden) |
| Periods close | `/accounting/periods` | A21 | Named API | API; UI not golden | **API-ONLY** |
| Accounting bank recon | `/accounting/bank-reconciliation` | overlap with payments recon | — | FLAG-OFF mocked | **GAP** (two recon UIs) |
| Cost centers | `/accounting/cost-centers` | — | **Not named** | FLAG-OFF SMOKE | **GAP** |
| Fixed assets | `/accounting/fixed-assets` | D6 OUT | limitation guard | FLAG-OFF | **OUT** |

### 2.11 Settings & admin

| Flow | Route | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| Company / GST / users | `/settings/company`, `gst`, `users` | A17 A19 | Named | settings SMOKE; GST page exists | **SMOKE / thin** |
| Series, units, items, templates | `/settings/series` … | numbering invariant | numbering API | SMOKE | **SMOKE** |
| Price lists | `/settings/price-lists` | ARCH-03 slabs | “price slab lost” as go-wrong | **no UI test** | **GAP** |
| Bank accounts / payment gateway / billing | `/settings/bank-accounts` … | A25 | — | SMOKE | **SMOKE** |
| Import | `/settings/import` | A15 SUP | Named PJ-IMPORT | API; UI SMOKE | **API-ONLY** |
| Backup / export | `/settings/backup` | A16 SUP | Named drill | API backup-restore; UI SMOKE | **API-ONLY** |
| Tally | `/settings/tally` | OUT | FLAG | FLAG-OFF SMOKE | **OUT** — map notes Tally **bypasses `complete()`** ungated as identity |
| Statutory licences | `/settings/statutory-licences` | ARCH-05 Stage 4 | WF-60 soft block | SMOKE + API | **thin** |
| Invite user (from users page) | `/settings/users` | A17 | PJ-FTUE API | role-boundaries hides button for ACCT | **API-ONLY** |

### 2.12 Dark modules (must stay inaccessible in pilot)

| Flow | Route | Freeze | Strategy | Actual tests | Verdict |
|---|---|---|---|---|---|
| Manufacturing BOM / WO | `/manufacturing/*` | OUT | PJ with flag **on** + limitation 404 | e2e `dark-modules.spec.ts` | **split** — API “works when on” can be mistaken for freeze coverage |
| Payroll | `/payroll/*` | OUT | same | dark-modules | **same split** |
| CRM leads / opportunities | `/crm/*` | OUT | same | dark-modules | **same split** |

**Issue:** `FULL_SPECTRUM_PERSONA_VALIDATION_PLAN.md` counts manufacturing/payroll/CRM PJ tests in the 55-test persona suite. `TESTING_STRATEGY.md` §3 then looks “covered.” Those tests **must not count toward freeze or product-trust confidence**.

### 2.13 In-page / non-route flows the strategy mostly misses

These are how users actually work. They are not sidebar items.

| Flow | Why it matters | Strategy | Verdict |
|---|---|---|---|
| Complete / cancel / amend from the document screen | Writes the mapped fields | API services tested; **button + confirmation + resulting badge** not e2e except invoice create | **GAP** |
| Allocate / unallocate from receipt or invoice | AR/AP identity | API H-01 | **GAP** UI |
| Return + auto CN + residual DN, then look at dashboard + history + attention + dunning | Exact G-17–G-23 class | Split across UNIT + API regressions; **no single UI journey** | **P0 GAP** |
| Print PDF, wait for READY, share link | UAT G6; A14 | snapshot API | **GAP** UI |
| WhatsApp / share-link dunning | LIM delivery | cadence API | **OUT delivery; UI copy GAP** |
| POS/invoice offline queue flush | H-03 | copy tests | **partial** |
| Feature-flag change (accounting on, GST settings, expiry policy) then **old documents still make sense** | historical integrity | matrices + period gates | **partial API; no UI** |
| Multi-tab / two users on one invoice | G-11a races | postgres-only API | **GAP** UI |
| Hindi locale on money screens | MSME | `moneyParity.test.ts` keys only | **GAP** as a user flow |

---

## 3. Coverage math (so gaps are visible)

Approximate counts from `App.tsx` + `menu.ts` (redirects excluded):

| Bucket | Count (approx.) | In strategy as a named journey | Gating test of the **job** | UI journey (golden / real backend) |
|---|---|---|---|---|
| Public routes | 6 | 2 (login, register) | 2 | 2 |
| Core commercial (sales/POS/purchase/receipts) | ~25 screens + editors | ~12 | API strong; UI ~6 goldens | Invoice, POS, purchase, payments, stock valuation, accounting enable |
| Inventory ops (count, transfer, serial, expiry, labels) | 10 | 4 API | API | 0–1 |
| Reports + attention | ~25 | 8 as “A13 reports” | identities partial API | 1 golden (valuation) + TB/P&L |
| Settings | ~18 | 4 | API import/backup | 0 job journeys |
| Insights UI | 5 | treated OUT | FLAG-OFF | 0 |
| Dark modules | 6 | wrongly counted in PJ totals | FLAG-OFF + flag-on API | 0 |
| Auth recovery / public pay / invite | 4 | 0–1 | 0 UI | **0** |

`PROTECTED_ROUTES` (the strategy’s G-5 “top-20 smoke”) has **20** paths. The app has **~90+** reachable screens for an Owner with books and GST worksheets on. G-5 itself says keep the rest LIM. That is an accepted crash-coverage LIM, **not** an accepted product-truth LIM.

---

## 4. Strengths to preserve

Do not weaken these while expanding coverage.

1. **Strict invariant sweep** after every test (`INVARIANTS_STRICT=1`).
2. **Named class CF-001** and “trust-breaking = P0 regardless of diff size.”
3. **`sales/status_semantics.py`** (`is_open_receivable` vs `is_operational_sale`).
4. **Structural guards** (period gate, raw `unit_cost`, CA tax parity, regression corpus ratchet).
5. **Honest gap register and weak-assumption list** (especially 6, 9, 11, 12).
6. **Persona journeys that post a real day of work** and then `assert_all_invariants`.
7. **The impact map’s audit method** — one pass found G-18…G-23.
8. **Golden e2e against live Django** for invoice, POS, purchase, payments, accounting, stock valuation, multi-warehouse.
9. **Human gates** (H-05, UAT, Go/No-Go) not pretended to be automated.

---

## 5. Critical gaps (product-trust)

These remain even when the suites named in `TESTING_STRATEGY.md` are green. They are **topology** gaps: the suite is large; the graphs are not connected. Do not “fix” them by adding more isolated persona tests.

### G-FLOW-01 — Strategy does not inventory UI flows (Graph 1 missing)

`TESTING_STRATEGY.md` frames journeys as archetypes and API PJ/WF ids. It never publishes a **route/action catalog**, and the diagnostic tables in §2 of this file must not become the long-term catalog — that catalog must be **generated** from `App.tsx`. Result: quick entry, sales debit notes, label print, public pay, forgot-password, attention page, price lists, statutory events, cost centers, two bank-recon screens, and most settings are **invisible to the method**.

### G-FLOW-02 — Smoke is treated as coverage

G-5, `reports-domain.spec.ts`, `settings-domain.spec.ts`, `payments-domain.spec.ts` prove “did not crash.” The strategy’s §3 “UX 🟡” understates this: a green smoke run is compatible with every number on the page being wrong.

### G-FLOW-03 — API journey ≠ user journey (weak assumption 6, still open)

These are **separate validation dimensions**. Clerks do not POST `/api/v1/sales/invoices/{id}/complete/`. They press a button and look at a badge, stock widget, and drawer. Almost all exception paths (cancel, amend, unallocate, challan cancel, stock count post, serial return) are **API-ONLY**.

### G-FLOW-04 — The G-17 class has no end-to-end UI lifecycle (canonical product-truth gap)

There is still **no** browser journey:

`invoice → pay → full return → residual debit note → open history, detail, dashboard, attention, customer ledger → subsequent event / close`

That is the canonical **product-truth failure**: API correct, database correct, component correct, invariant correct, status unit test correct — and the customer still sees “Paid” on a returned invoice. UNIT matrices on fixtures are necessary and insufficient (weak assumption 11). This test is P0 for ARCH-01 and ARCH-03.

### G-FLOW-05 — Attention is live; insights are declared out of scope (decision quality)

`/attention` is in the default nav. Backend alerts, cashflow, health, dunning, and credit-hold run without `ENABLE_AI`. The strategy’s “AI-specific ⛔ / ENABLE_AI=0” row is being used as a reason not to identity-test **decision surfaces the owner uses every morning**.

### G-FLOW-06 — Event lineage is missing

`CROSS_FLOW_IMPACT_MAP.md` answers “who reads this **field**?” User flows are **events** (complete, return, allocate, reverse, close). There is no event × (stock, GL, AR/AP, GST, report, attention, badge, notification) matrix. Empty cells are not G-ids. Growth rule is “add after we’ve been bitten.”

### G-FLOW-07 — Projection identity is not an invariant

`reports.cross_reconcile` is not registered, not run after every test, and only checks TB + P&L. Dashboard vs daily summary vs health vs forecast vs aging is **one happy-path API test** (`test_startup_founder_onboarding_to_analytics_synchronization`) with one unpaid sale. Residual/return/close never enter it.

### G-FLOW-08 — Sparse persona × archetype × UI

Retail has no munshi/CA UI day. Wholesale has no clerk UI day. Batch/serial/count/transfer are API-only. Staff landing (`HomePage` without financial reports) is unasserted as a coherent workspace.

### G-FLOW-09 — Dark-module tests inflate “persona coverage”

Manufacturing, payroll, CRM PJ files run with flags forced on. Freeze requires them **inaccessible**. The strategy §3 table still reads as if those archetypes are covered.

### G-FLOW-10 — Historical / bypass writers

- Enabling accounting does not backfill (map: product gap; no UI warning test).
- Tally import writes COMPLETED bypassing `complete()`.
- BoE cancel silently unlinks RETURNED purchases (in the map, **not a G-id**).
- FE fallbacks `balance ?? grandTotal` and `available ?? onHand` still exist.

### G-FLOW-11 — Copy / terminology

`is_open_receivable` includes RETURNED; `is_operational_sale` does not. No test that dashboard “sales,” insights “best seller,” and attention “open sales” use different labels. Two correct numbers with the same English word is a trust defect.

---

## 6. Issues inside the two strategy documents

| Issue | Where | Why it hurts |
|---|---|---|
| L3 claims WF-01…59 each end in `cross_reconcile` | TESTING_STRATEGY §2.1 | Overclaim. Many WFs live in `test_wf_todo_stubs.py`; several are skipped; `cross_reconcile` is GL-only. |
| L4 file/journey counts drift | strategy vs FULL_SPECTRUM vs README | 15 / 24 / 55 / 28 files — readers cannot know the real gate. |
| §9 backlog still lists G-1/G-2 as next | TESTING_STRATEGY §9 | Closed in §7. Stale method docs hide real P0s. |
| G-5 “top-20” list is 20 Owner smokes | `protectedRoutes.ts` | Missing: `/attention`, `/setup`, `/sales/quick-entry`, `/sales/debit-notes`, `/sales/returns`, `/inventory/transfers`, `/pay/:token`, `/forgot-password`. |
| Map §5 still describes dunning as COMPLETED-only | CROSS_FLOW §5 | Fixed as G-20. A lying map is worse than none. |
| G-19 suggested test “currently fails” | CROSS_FLOW §3 | Test exists and passes. |
| G-23 missing from map summary table | CROSS_FLOW summary | Seventh instance of CF-001. |
| BoE RETURNED unlink documented, not promoted | CROSS_FLOW §2 | Process failure: map found it; strategy did not gate it. |
| L8 “do not pre-populate until bitten” | CROSS_FLOW intro | Explicitly refuses systematic coverage. |
| `PurchaseInvoice` predicates unstarted | both docs | GST/ITC readers still hand-write status sets. |
| Three layer systems | L1–L8 vs T1–T7 vs Q-OS | Authority declared, then ignored in counts. |
| Delight ⛔ | G-15/G-16 | H-02 is a buying hypothesis with no automated proxy that actually ran. |

---

## 7. Blind spots (green suite, still ships)

- Same metric, different formula (single vs bulk outstanding; `on_hand` vs `available`).
- Blessed snapshots that are not CA-anchored (weak assumption 9).
- Mid-`complete()` crash (`no_invariant_check`).
- SQLite local hiding `SELECT FOR UPDATE` races (G-11a).
- Eager Celery hiding webhook vs period-close ordering (G-10).
- Hindi/English copy mismatch on statuses.
- Two bank-reconciliation UIs (`/payments/reconciliation` vs `/accounting/bank-reconciliation`) showing different match states.
- Recurring-invoice screen in the nav while retainers are out of freeze — users can enter a half-built loop.
- Public `/pay/:token` amount vs invoice outstanding after a return.

---

## 8. Missing validation dimensions (add to the method)

Keep the existing 14 quality dimensions in `TESTING_STRATEGY.md` §3. Add these as first-class. **Decision quality** and **historical integrity** are core product dimensions, not extras.

| Dimension | Question the suite must answer |
|---|---|
| **User-flow inventory (Graph 1)** | Is every route and in-page money action in a *generated* catalog with a coverage label? |
| **Event lineage (Graph 2)** | For this event, which projections must change? |
| **Projection identity (Graph 3)** | Do independently computed surfaces foot to the same named metric? |
| **Semantic labeling (Graph 3)** | Do two predicates share a user-facing word? |
| **API vs user-visible** | Did we assert the click, badge, and next action — or only the POST? |
| **Lifecycle intent** | After create→pay→return→adjust→report→attention, is the original intent still represented? |
| **Time / subsequent event** | After the *next* event, do earlier surfaces still agree? |
| **Historical integrity** | Can a later action rewrite a closed period’s picture? |
| **Reversal completeness** | Does cancel/return unwind every projection the forward path wrote? |
| **Decision quality** | Would acting on attention/dunning/forecast be the right move? |
| **Explainability** | Can the user walk number → documents → rule? |
| **Persona-visible truth** | Roles change buttons, not arithmetic? |
| **Bypass-writer integrity** | Import/Tally/flag-flip = same projections as the UI path? |
| **Channel integrity** | Public pay, invite, OTP, share-link, webhook match in-app state? |

---

## 9. Target validation architecture

A SUPPORTED event is gated only when the **time-extended** chain is asserted:

```text
User action (UI or channel)
  → preserved intent
  → canonical state
  → stock + GL + AR/AP + GST + related docs
  → registers + dashboard + statements
  → attention / dunning / health / forecast
  → badge, empty state, help, next button
  → decision (is this safe to act on?)
  → subsequent event
  → reversal / amendment / return
  → historical truth
```

**Canonical product-truth test (P0, lead archetypes):**

```text
Invoice → Pay → Return → Residual debit note
  → History badge → Detail badge → Dashboard → Attention → Ledger → Stock
  → (optional) closed period remains unchanged
```

That is the G-17→G-23 detector. It is a **product-truth** test, not a conventional coding-bug test.

**Layers — L1–L10 is the only numbering.** T1–T7 in the persona plan maps onto these; it must not be cited as a second pyramid.

| Layer | Proves | Maps from T1–T7 (view only) | Gate |
|---|---|---|---|
| L1 Invariants | At-rest consistency | T2 | Blocking |
| **L10 Projection identity** | Named equalities in the **strict sweep** | T5 | Blocking |
| L2 Contracts | Envelope, RBAC, money strings | T1 (partial) | Blocking |
| L3 Workflow atoms | One flow’s mechanics | T1/T3 | Blocking for SUPPORTED |
| **L9 Lifecycle + time** | Intent across the loop *and* the next event | T3 | Blocking for ARCH-01, ARCH-03 |
| L4 Persona overlay | Role can run the day; same facts | T4 | Blocking API; FE for P1/P2/P5 |
| L5 Matrices | Settings × behaviour | — | Blocking for GST/expiry/accounting |
| L8 Impact graph | Reader/enforcer agreement | — | Blocking; must become event-shaped |
| L6 Golden e2e | Browser shows canonical badge/KPI | T4 UI | Blocking for money/status screens |
| L6b Generated flow catalog | Every in-scope route is JOURNEY or explicit LIM | — | Blocking list drift |
| L7 Exploratory + pilot | Trust, delight, H-05, decision-quality in the wild | T7 | Freeze/go-live |

---

## 10. Failure taxonomy (what we must detect)

| Class | Example already in this codebase | Detected today? |
|---|---|---|
| Technical | Error boundary on deep link (BB-000829) | Partial (20 routes) |
| Functional | POS complete does not allocate | Strong API / golden |
| Business-rule | Period gate missed on GRN/challan cancel | Structural guard |
| Calculation | GST split | Strong |
| Data-integrity | `on_hand` ≠ Σ movements | Strong L1 |
| Cross-flow CF-001 | Dunning vs payment-health (G-20) | Reactive, 7 fields |
| **Product-truth** | RETURNED billed as Paid (G-17) | UNIT after the bug — **the class this model exists for** |
| UX / mental-model | Same as product-truth, user interpretation | Incident-driven |
| Persona | Clerk sees financial alert / dead 403 nav | Improving; staff home GAP |
| Reporting | Register ≠ dashboard | Partial API |
| Insight / attention | DEAD_STOCK on reserved qty (G-19) | Incident tests |
| **Decision-quality** | “Collect ₹100,000” when most is uncollectible; credit-hold missed residual AR (G-23) | Almost absent |
| Channel | `/pay/:token` vs returned invoice | **No** |
| Lifecycle + time | Intent lost after return→DN→later close | Sliced tests |
| Historical | Books enabled, old invoices have no GL | Documented, ungated UX |
| Terminology | “Sales” = two predicates | **No** |
| Dark-module leakage | PJ counted as freeze coverage | Doc issue |

---

## 11. Recommended testing layers (how to use the suite)

| Must block merge | Must block freeze | Stay human |
|---|---|---|
| L1 + L10 identities; guards; writer-impact; no new raw status filters; **generated route-catalog drift** | Lead-archetype **lifecycle including residual and a subsequent event**; FE money/status on real documents; in-scope flow catalog with no silent empties; dark modules inaccessible and **not counted** | H-05 CA filing; H-02 in the wild; scanner fatigue; “would I pay”; copy tone; **decision-quality with real operators** |

---

## 12. Automation opportunities

**Architecture first (do these before a test explosion)**

1. Generate Graph 1 from `App.tsx` + in-page actions + public channels. Fail CI on an uncatalogued route.
2. Event catalog + event × projection matrix (Graph 2). Empty cell = GAP or explicit LIM.
3. Projection-identity registry (Graph 3) as registered invariants in the strict sweep.
4. AST guard: status filters must import the semantics module.
5. Writer-path CI: touching a mapped writer requires cited reader tests.

**Then derive**

- One Playwright lifecycle golden per lead archetype (the P0 product-truth test).
- Decision/UX assertions on attention + dashboard for that same fixture.
- Promote BoE RETURNED unlink to a G-id or accepted LIM.

**Do not**

- Add another 50 persona tests that only end in `assert_all_invariants`.
- Treat heading-or-Retry domain specs as journey coverage.
- Count flag-on manufacturing/payroll/CRM toward freeze.
- Hand-maintain a second Markdown catalog as the long-term Graph 1.

---

## 13. Concrete changes — `CROSS_FLOW_IMPACT_MAP.md`

This file is **Graph 2’s current reader index**. Keep the field entries. Evolve the *top* primitive from field to event.

**Add**

1. Event catalog (complete, cancel, return, CN/DN, allocate, reverse, void, amend, close, count, transfer, import, flag-flip, **public-pay, invite, OTP**) with projection columns including **channel** and **historical period**.
2. Calculation-identity registry (outstanding, available, net vs operational sales, dashboard vs summary vs health vs forecast).
3. `PurchaseInvoice` predicate module (already called out as unstarted).
4. Fields with 3+ readers not yet mapped: `Receipt.status`, challan/order status, serial/lot, period status, credit limit, UoM, IRN lock, onboarding flags, POS shift, feature flags.
5. Machine-readable `writers[]` / `required_tests[]`.
6. G-23 in the summary table; BoE RETURNED unlink as G-id or LIM.

**Fix**

- Stale G-20/G-19 text; “all six fixed” while G-23 and BoE remain.
- Replace “don’t pre-populate until bitten” with: any new money **event** or 3-reader field must be catalogued before merge (Graph 2 completeness).

**Keep**

Writer lists, per-reader assumptions, negative results, CF-001 name, period-gate sibling shape.

---

## 14. Concrete changes — `TESTING_STRATEGY.md`

This file is **validation method** under the Quality Model. One layer system: L1–L10.

**Add**

1. Pointer to this operating model (§0) as philosophy; Q-OS as output; FULL_SPECTRUM as L4 view.
2. L9 (lifecycle + time) and L10 (projection identity) in §2.1.
3. Sixth journey question: **“Where else must this be true, under what name, and after the next event?”**
4. Rule: `/attention` and dashboard KPIs are in scope even when `ENABLE_AI=0` (decision quality).
5. Rule: FE must not re-derive money/status the API already has; if it does, combination tests are the gate.
6. Rule: dark-module PJ tests sit in a flagged lane and **do not** close archetype coverage.
7. Mandatory UI lifecycle for ARCH-01 and ARCH-03 including residual DN/CN **and a subsequent event**.
8. Public channels: `/pay/:token`, `/invite`, `/forgot-password` as named A20/A25/A19 sub-flows.
9. Explicit: **do not** grow L4 by volume; grow Graph 1/2/3 completeness.

**Correct**

- L3 `cross_reconcile` claim.
- L4 counts vs the live tree.
- §9 vs §7 (closed gaps still listed as next).
- G-5: generate the catalog **or** admit smoke ≠ UX.

**Do not remove**

Five questions, gap register, weak assumptions, evidence ledger, trust-breaking = P0, strict sweep, H-05.

---

## 15. Prioritized recommendations

**Do not implement dozens of new tests first.** Sequence is architecture → a few topology-rich goldens → remaining P1 UI holes.

### P0 — validation architecture + the one product-truth detector

1. **Machine-readable user-flow catalog (Graph 1)** generated from the router/actions; uncatalogued SUPPORTED route blocks CI. §2 of this file is the diagnostic snapshot until that exists.
2. **Event × projection matrix (Graph 2)** for the 12 money/stock events. Empty cells become G-ids.
3. **Projection-identity invariant (Graph 3 / L10)** in the strict sweep: dashboard = summary = health inputs = aging = subledger. Distinct names for operational sales vs open receivables.
4. **ARCH-01 + ARCH-03 UI lifecycle (L9):** create → complete → (partial) pay → return → residual note → history + detail + dashboard + attention + ledger + stock. This is the G-17–G-23 class detector.
5. **Treat `/attention` and dashboard as live decision surfaces**, independent of `ENABLE_AI`.
6. **Eliminate or gate FE-derived financial fallbacks** (`balance ?? grandTotal`, `available ?? onHand`).
7. **Status semantic enforcement** (AST guard; then `PurchaseInvoice` module).

### P1

8. `PurchaseInvoice` `status_semantics` + GST readers.
9. Writer-diff → required reader tests in CI.
10. Historical-integrity pack after period close (time / subsequent event).
11. Public payment / invite / setup wizard click-through journeys.
12. UI for stock count / transfer / serial / purchase residual DN / challan cancel.
13. Dark-module coverage separated from freeze confidence.
14. Documentation reconciliation (stale G-ids, L3 overclaim, T1–T7 as view-only).

### P2

15. Forgot/reset password e2e.
16. Label printing, price lists, statutory events, cost centers, dual recon UI identity.
17. Explainability: every attention row traces to documents + formula id.
18. Hindi money/status as a user flow, not only key parity.
19. Delight proxies (POS wall-clock, dashboard budget) advisory then blocking.
20. Expand mapped fields (receipt, challan, serial, lot, credit limit, UoM, IRN, flags).

---

## 16. Target state — Product Quality / Holistic Validation System

Not a larger test suite. A system that derives tests from graphs.

**Primitive.** A **user-visible business event** (including public channels and *time*).

**Completeness.** Flow catalog and event × projection matrix make absence visible. Unfilled cells are G-ids.

**Identity.** Same named metric agrees in the strict sweep. Different metrics do not share a label.

**Lifecycle + time.** Lead archetypes run create→pay→return→residual→report→attention **and** a subsequent event / close, in one UI test.

**Decision.** Attention/dunning/forecast are asserted for *actionability*, not only presence.

**Persona.** Roles change affordances, not arithmetic.

**Guard.** Every defect *class* gets a structural detector.

**Human.** H-05, wild-POS timing, and “worth paying for” stay at the top of the pyramid.

**Build order**

```text
Flow Catalog → Event Catalog → Impact Matrix → Projection Identity Registry
  → Lifecycle Goldens → Decision/UX assertions → CI gates
```

---

## 17. Direct answer

**Are all user flows covered in the current testing strategy?**  
No. Core API happy paths and a handful of golden UI loops are. The majority of reachable screens, exception/residual/channel flows, decision surfaces, and historical truth after a later event are not.

**If every current test passes, can a user trust BizBoard?**  
We can trust that the books did not silently unbalance. We cannot yet trust that every surface still tells the same story after capabilities interact over time.

**What to do next:** stand up the three graphs and the generated catalog. Then write the two lead-archetype lifecycle goldens. Do not grow the persona suite by volume until those primitives exist.
