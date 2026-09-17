# Complete-gate visibility — implementation plan

**Status:** Waves 0–5 gated in suite · **Created:** 2026-09-15 · **Owner:** web + QA  
**Layer:** L6 (FE e2e + vitest). Backend reject tests are companions, not substitutes.  
**Gap register:** `TESTING_STRATEGY.md` **G-complete-gate**  
**Catalog (CI):** `web/src/completeGates/catalog.ts` + `completeGateIndex.test.ts`

This plan covers the defect class found on Create Purchase Invoice: **party + at
least one line looks enough, but Complete is still blocked (or will fail), and
the screen does not name the real reason.** Happy-path goldens never see it.

Do not cite bullet prose from reviews. Cite **`CG-NN`**.

---

## 1. What “gated” means

For every `disabled` case, a merge-blocking UI test must assert all of:

1. Party + ≥1 line are already set (`canSave` true / Save draft enabled).
2. **Save & Complete** is disabled.
3. A **specific** reason is visible (banner, field error, or tooltip) — not only
   `billing.completeDisabledReason` (“select a customer/supplier and at least
   one item”).
4. Fixing that field enables Complete (or the contrast case stays enabled).
5. Draft stays enabled except writes-blocked / saving.

For every `click-fail` case: Complete **may** stay enabled; clicking Complete
must show a named error or confirm, not a generic disable. After the user acts,
Complete succeeds or stays honestly blocked.

For `contrast` cases: prove the twin behaviour (sales FEFO blank allowed;
purchase batch required). Pin it so sales/purchase copy cannot drift.

Shared helper: `web/e2e/complete-gates/assertCompleteGate.ts`.

**Lane**

| Kind | Default lane | When to use golden |
|---|---|---|
| FE disable + copy | `web/e2e/` (mocks) | — |
| Stock / period / hold / GSTIN company | `web/e2e-golden/` | Needs live Django |
| Backend 400 without UI | `backend/tests/` | Companion only |

Mocks cannot prove closed-period or credit-hold. Do not fake those in `web/e2e/`.

---

## 2. Case register

| ID | Surface | Kind | Wave | Status | Gate |
|---|---|---|---|---|---|
| CG-01 | sales | disabled | 1 | gated | GST bill, customer has no state/GSTIN — `web/e2e/sales/complete-gates.spec.ts` |
| CG-02 | sales | disabled | 0 | gated | Regular company GSTIN empty — `web/e2e-golden/gstin-prompt.spec.ts` |
| CG-03 | sales | disabled | 1 | gated | Stock policy BLOCK, qty > available — `web/e2e/sales/complete-gates.spec.ts` |
| CG-04 | sales | disabled | 3 | gated | Tax preview pending — `web/src/completeGates/completeBlockers.test.ts` |
| CG-05 | sales | disabled | 3 | gated | Line qty is 0 — `web/e2e/sales/complete-gates.spec.ts` |
| CG-06 | sales | disabled | 2 | gated | Sales RCM on, confirm box unticked — `web/e2e/sales/complete-gates.spec.ts` |
| CG-07 | sales | disabled | 2 | gated | Credit hold / stop-credit — `web/e2e/sales/complete-gates.spec.ts` |
| CG-08 | sales | disabled | 3 | gated | Credit limit exceeded — `web/e2e/sales/complete-gates.spec.ts` |
| CG-09 | sales | disabled | 3 | gated | Serial count ≠ qty — `web/e2e/sales/complete-gates.spec.ts` |
| CG-10 | sales | contrast | 1 | gated | Blank batch still enables Complete (FEFO) — `web/e2e/sales/complete-gates.spec.ts` |
| CG-11 | sales | click-fail | 4 | gated | Date in closed GST period — `web/e2e-golden/complete-gates-golden.spec.ts` |
| CG-12 | sales | click-fail | 4 | gated | Duplicate bill / confirm-no-RCM / GSTIN recompute — `clickFailContracts.test.ts` |
| CG-13 | sales | disabled | 4 | gated | Subscription writes blocked — `DocumentEditorShell.test.tsx` |
| CG-14 | sales | disabled | 4 | gated | Completed IRN lock — `clickFailContracts.test.ts` |
| CG-15 | purchase | disabled | 1 | gated | GST bill, supplier has no state/GSTIN — `purchase-complete-gates.spec.ts` |
| CG-16 | purchase | disabled | 0 | gated | Batch-tracked line, empty batch — `purchase-batch-complete.spec.ts` |
| CG-17 | purchase | disabled | 1 | gated | Serial-tracked inbound — `purchase-complete-gates.spec.ts` |
| CG-18 | purchase | disabled | 3 | gated | Tax preview pending — `completeBlockers.test.ts` |
| CG-19 | purchase | disabled | 3 | gated | Purchase line qty is 0 — `purchase-complete-gates.spec.ts` |
| CG-20 | purchase | disabled | 2 | gated | Empty company GSTIN FE-disables purchase (aligned with sales) — `purchase-complete-gates.spec.ts` |
| CG-21 | purchase | click-fail | 4 | gated | No supplier GSTIN, RCM off — `web/e2e-golden/complete-gates-golden.spec.ts` |
| CG-22 | purchase | click-fail | 4 | gated | Duplicate supplier bill number — `web/e2e-golden/complete-gates-golden.spec.ts` |
| CG-23 | purchase | click-fail | 4 | gated | Purchase date in closed period — `web/e2e-golden/complete-gates-golden.spec.ts` |
| CG-24 | purchase | disabled | 4 | gated | Writes blocked on purchase — `DocumentEditorShell.test.tsx` |
| CG-25 | notes | disabled | 1 | gated | Note preview fallback — `note-preview-complete.spec.ts` |
| CG-26 | notes | disabled | 3 | gated | All note qtys 0 — `note-preview-complete.spec.ts` |
| CG-27 | notes | disabled | 3 | gated | Note qty above source cap — `note-preview-complete.spec.ts` |
| CG-28 | pos | disabled | 4 | gated | Cart has items; pay disabled — `pos-complete-gates.spec.ts` |
| CG-29 | pos | disabled | 4 | gated | POS batch line, no lot — `pos-complete-gates.spec.ts` |
| CG-30 | pos | click-fail | 4 | gated | POS serial missing / mismatch — `pos-complete-gates.spec.ts` |
| CG-31 | pos | disabled | 4 | gated | POS stock BLOCK at pay — `pos-complete-gates.spec.ts` |
| CG-32 | shell | disabled | 3 | gated | `saving` greys Complete — `DocumentEditorShell.test.tsx` |
| CG-33 | shell | meta | 0 | gated | Disabled Complete tooltip can be page-specific — `DocumentEditorShell.test.tsx` |
| CG-34 | order | disabled | 5 | gated | SO/PO zero qty names Save — `extra-complete-gates.spec.ts` |
| CG-35 | sales | disabled | 5 | gated | Delivery challan zero qty — `extra-complete-gates.spec.ts` |
| CG-36 | returns | disabled | 5 | gated | Returns Complete named (no line / permission) — `extra-complete-gates.spec.ts` |
| CG-37 | ops | disabled | 5 | gated | Payroll / WO Complete names writes-blocked — `clickFailContracts.test.ts` |

Baseline (not a CG): empty form / party without lines is already
`web/e2e/personas/validation-parity.spec.ts` (§H1). Do not duplicate it here.

When a row moves `gap` → `gated`, update `catalog.ts` `status` + `testFile` in
the same PR as the spec. The index test will fail if you forget.

---

## 3. Waves (build order)

### Wave 0 — suite membership (this change)

**Goal:** the class is visible in CI even before every case has a UI spec.

- Plan + catalog + index test.
- Existing gates tagged CG-02, CG-16, CG-33.
- Helper `assertCompleteGate.ts` for later specs.

**Acceptance:** `npx vitest --run src/completeGates/completeGateIndex.test.ts`
passes. Adding a new CG row to this plan without `catalog.ts` fails CI.

### Wave 1 — silent disable after party + line (P0)

**Files:** `web/e2e/sales/complete-gates.spec.ts`,
`web/e2e/purchases/purchase-batch-complete.spec.ts` (extend),
`web/e2e/purchases/purchase-serial-complete.spec.ts`,
`web/e2e/notes/note-preview-complete.spec.ts`, mocks as needed.

| ID | Steps |
|---|---|
| CG-01 | GST invoice, customer without state/GSTIN → banner `placeOfSupplyRequired` → Complete off → add state → on |
| CG-03 | BLOCK policy, qty > on-hand in this godown → stock alert → Complete off → reduce qty or other godown with stock → on |
| CG-10 | Sales batch item, leave FEFO blank → Complete **on** (contrast with CG-16) |
| CG-15 | GST purchase, supplier without state/GSTIN → supplier POS banner → Complete off → add GSTIN → on |
| CG-17 | Purchase serial item, empty serials → Complete click or disable + named serial reason → paste N serials → on |
| CG-25 | Open CN/DN with party + lines while preview errors → Complete **on** with `previewUnavailableClientTotals` fallback banner; do not strand |

**Acceptance:** each ID in the table is `gated` in `catalog.ts`. Mocked
`npm run test:e2e` chromium covers them.

**CG-17 product note:** purchase serials FE-disable Complete like batch
(`completeDisabledMissingSerial`). Spec asserts disable + named serial reason.

### Wave 2 — looks ready, then fails (P0)

| ID | Lane | Steps |
|---|---|---|
| CG-06 | mocked or golden | Tick RCM, leave confirm off → Complete click → `confirmSalesRcmRequired` → tick → completes |
| CG-07 | mocked | Customer `stop_credit` / Held Traders → named hold, Complete disabled |
| CG-20 | mocked + golden | Regular company, empty GSTIN, purchase GST bill → Complete **blocked** for company GSTIN (aligned with CG-02) |

### Wave 3 — remaining editor honesty (P1)

CG-04, CG-05, CG-08, CG-09, CG-18, CG-19, CG-26, CG-27, CG-32.

Prefer unit tests of a extracted `completeBlockers()` helper where the UI is
timing-sensitive (preview in flight). E2E still required for copy/tooltip.

### Wave 4 — period, confirms, POS, subscription (P1/P2)

CG-11, CG-12, CG-13, CG-14, CG-21, CG-22, CG-23, CG-24, CG-28, CG-29, CG-30, CG-31.

### Wave 5 — extra surfaces (orders, challans, returns, payroll/WO)

CG-34, CG-35, CG-36, CG-37.

---

## 4. Product follow-through (tests do not replace this)

Wave 1–5 product honesty (landed):

- `primaryDisabledReason` for every extra Complete blocker while `canSave`.
- Purchase serial required copy + FE-disable (same class as batch).
- Notes preview uses `previewFellBack` / client-totals banner (no silent strand).
- Notes over-cap is typeable and Complete-named (no silent clamp).
- CG-20: purchase company GSTIN gate aligned with sales.
- Preview totals `withMocks` so POS mock cash tender is not stranded.
- Orders / challans / returns / payroll / WO name extra Complete blockers.

---

## 5. Files

| Path | Role |
|---|---|
| `docs/COMPLETE_GATE_VISIBILITY_PLAN.md` | this plan |
| `web/src/completeGates/catalog.ts` | ID × status × test file |
| `web/src/completeGates/completeGateIndex.test.ts` | CI: plan ↔ catalog ↔ freeze map ↔ gated files |
| `web/e2e/complete-gates/assertCompleteGate.ts` | shared Playwright asserts |
| `web/e2e/purchases/purchase-batch-complete.spec.ts` | CG-16 |
| `web/e2e-golden/gstin-prompt.spec.ts` | CG-02 |
| `web/e2e/notes/note-preview-complete.spec.ts` | CG-25, CG-26, CG-27 |
| `web/e2e/pos/pos-complete-gates.spec.ts` | CG-28–CG-31 |
| `web/e2e/sales/extra-complete-gates.spec.ts` | CG-34, CG-35, CG-36 |
| `web/e2e-golden/complete-gates-golden.spec.ts` | CG-03 (live), CG-11, CG-20, CG-21, CG-22, CG-23 |
| `web/src/components/billing/DocumentEditorShell.test.tsx` | CG-33 |
| `docs/TESTING_STRATEGY.md` | G-complete-gate |
| `docs/FREEZE_SCOPE_COVERAGE.md` | CG id → test map |

---

## 6. Out of scope

- Empty form / no party / no line (§H1 validation-parity).
- Happy-path Complete on non-tracked items (existing goldens).
- Live NIC e-invoice IRN (CG-14 is a named FE lock + source contract; sandbox IRN golden is out).
- Auto-dunning `stop_credit` golden (CG-07 is mocked via Held Traders).

---

## 7. Exit

G-complete-gate is ✅ when every row in §2 is `gated` or an explicit LIM in
`FREEZE_SCOPE.md`, and `completeGateIndex.test.ts` stays green.
