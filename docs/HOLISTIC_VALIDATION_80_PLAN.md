# Holistic Validation — 80% per dimension (LLM-executable)

**Status:** executed 2026-09-14 · **Companion to:** [`HOLISTIC_VALIDATION_IMPLEMENTATION_PLAN.md`](HOLISTIC_VALIDATION_IMPLEMENTATION_PLAN.md) (Phases 0–7 encoded) · [`HOLISTIC_VALIDATION_REVIEW.md`](HOLISTIC_VALIDATION_REVIEW.md) §0.9 / §0.10  
**Scoreboard (repo source of truth):** the living table in this file. A Cursor IDE canvas (`confidence-80-llm-plan.canvas.tsx`) may sit beside chat; **it is not a git artifact** and must not be cited as if it lived in the tree.  
**Owner:** whoever runs the Cursor sessions below  
**C6-80:** **signed 2026-09-14** (founder: implement this plan with nothing left partial). Still not High.

This is HOW to take each review §0.9 dimension from “green suite today” to **80% reviewer confidence**. It does not replace L1–L10. It does not invent G-ids. It does not flip A3 on day one. It does not delete a recon UI. It does not count `dark_module` PJ tests as freeze coverage.

---

## Why 80% exists (and why it is not the review’s bar)

The review’s §0.9 table uses **bands** (Low / Medium / Medium-high / High). Locked **C6** (review §0.10, this runbook’s parent §0a) says the *runbook* finishes at **Medium-high** on Insight/decision; **High** there is H-05 / L7 fieldwork, not automatable.

This file is a **session target**, not a redefinition of High:

| Artifact | Success bar | What it certifies |
|---|---|---|
| Review §0.9 bands | Low → High | Qualitative reviewer confidence if the *currently defined* suite is green |
| Implementation plan exit | High on most rows; **Medium-high** on decision quality (C6) | Architecture + gates landed |
| **This 80-plan** | **80% on every chart row** | Claim-ready-plus: enough evidence that a founder can treat the row as “we would defend this in a freeze review,” **short of High / H-05** |

**80% ≠ High.** High on Insight/UX remains H-05. **80% on Insight/UX requires founder override C6-80** (review §0.10). Without that signature, stop those two rows at Medium-high (~70%). Hitting 80% does **not** close the gap to the review’s definition of done on those rows — track the remainder as H-05 / L7, not as more presence tests.

---

## Scoring (so “we hit 80%” is checkable)

Percents in this file are **not** “JOURNEY routes ÷ all routes.” They are reviewer-confidence anchors. **Baseline “Now” values are expert judgment** from review §0.9 plus 13 Sep evening golden evidence. They are not reverse-engineered from the rubric.

**Going forward, a session may move a row only when every rubric item for that row is evidenced.** Then set the percent to 80 (or hold). Do not interpolate 61, 73, etc. from partial work.

| Dimension | 80% is earned when all of these are true |
|---|---|
| At-rest (L1) | Already ≥80. Hold: `INVARIANTS_STRICT` still runs on books-on companies with docs; no new `no_invariant_check` except a documented mid-state. |
| Single-flow (L2–L3) | Of freeze-**SUPPORTED** (not OUT/dark) catalog **pages** that are named workflows, ≥80% are `JOURNEY` or explicit `LIM`. Count from generated `FLOW_CATALOG.md`. SMOKE/GAP on `/purchases/history` and `/invite` must be gone or honestly LIM. |
| Persona (L4) | One company, **Owner + Cashier + Accountant**: each role has a golden that asserts **money** and a **denied affordance**. Period close is Owner-only (B13). `dark_module` tests do not count. |
| Cross-flow (L8) | S0: catalog labels match goldens (no JOURNEY without an assertion). After a return, cashier history matches Owner. The 12 core money events have no *blank* matrix cell (LIM or GAP is allowed; empty is not). |
| Calculation (L10) | Projection identities fail CI when dashboard AR ≠ aging on a books-on company with docs. TB balanced after a lifecycle close. PDF vs live outstanding: B2/B3. |
| Historical | Closed month **N** rejects backdated Complete. A captured month-N TB / dashboard AR / aging snapshot is **byte-equal after an N+1 event**. Returned invoice stays RETURNED after close. |
| Lifecycle (L9) | ARCH-01, ARCH-03, **and** purchase-residual lifecycle goldens green; each asserts the canonical chain through residual + attention (review §9). |
| Insight / decision | **C6-80 signed**, plus: residual attention walk, dunning includes RETURNED+residual and walks to the invoice, dashboard KPI = aging = ledger, attention row has a stable `code` (P5-T3 / review §8 Explainability), G-23 residual still credit-holds. |
| UX / mental-model | **C6-80 signed**, plus glossary golden (Paid ≠ Completed ≠ Returned), recon chrome labeled not merged, Hindi outstanding + Returned, Regular-empty-GSTIN prompt (B14), **and** a founder/PM 30-minute pass on those screens. |

Partial credit does not raise the published percent. Automation alone **cannot** take Insight/UX above ~70% (review §11).

---

## How an LLM session must run

Paste this block as the first message of every session. Replace `SN` and the task body from the table.

```text
You are executing docs/HOLISTIC_VALIDATION_80_PLAN.md session SN.
Product-truth only. If the UI cannot drive the journey, fix the product, do not shrink the golden.

HARD RULES
- Do not flip flow-catalog or writer-impact to blocking unless this session is S5b and A3's two green CI weeks are already on the calendar.
- Do not delete /payments/reconciliation or /accounting/bank-reconciliation (B8 / QOS-0082).
- Do not count pytest.mark.dark_module as freeze coverage.
- Do not claim High decision quality. Do not invent G-ids. Do not mint CR-/R-/P1-/P2- ids.
- BB-000265: if payment_gateway is Razorpay with empty credentials, do NOT silently remap the provider to sandbox (that would accept sandbox webhook signatures against a named live provider). Tests and goldens must set provider=Sandbox via /settings/payment-gateway first. See backend/tests/test_payment_webhook_adversarial.py.
- Windows PowerShell: use `;` not `&&`. Playwright goldens: npm run test:e2e:golden.
- Do not commit unless I ask.

ACCEPTANCE
- Named files in the session exist and the listed command is green.
- FLOW_CATALOG.md regenerated if you added/relabeled a route:
  python validation/tools/build_flow_catalog.py
- Update HOLISTIC_VALIDATION_REVIEW.md §0.9 only when the scoring rubric for that row is fully met.
- Do not raise a published percent on partial rubric items.

TASK
<paste session task>
```

After each session: regenerate catalogs if routes/events changed, then re-score only rows whose **full** rubric passed.

---

## Founder gates (do not skip)

These are recorded in [`HOLISTIC_VALIDATION_REVIEW.md`](HOLISTIC_VALIDATION_REVIEW.md) §0.10 and the implementation plan §0a. Do not treat this table as the only copy.

| Id | Decision | If unsigned |
|---|---|---|
| **C6** | Decision-quality **High** is H-05 / L7, not automatable. Runbook exit = Medium-high. | Do not report Insight as High. |
| **C6-80** | Allow Insight/UX automation past Medium-high (~70%) toward **80%** (still not High). | Stop S6/S7 at 70%. Do not pad with more attention-presence tests. |
| **A3** | After **two consecutive green CI weeks**, flip `flow-catalog` + writer-impact from advisory → blocking | Catalog honesty (S0) still runs; the gate stays advisory. |
| **QOS-0082** | Consolidate the two recon UIs | Keep both; both write `match_status`. S7 only **labels** them. |
| **H-05** | CA files from worksheets in a live window | Blocks Insight/UX **High** (90%+). Not required for 80% if C6-80 is signed and S6/S7 pass. |
| **B13** | Period close / soft-close is **Owner-only** (`IsOwner`, BB-000453). Accountant may post journals and read TB; 403 on close. | S4 must not invent a second close-permission model. |
| **B14** | Regular + empty GSTIN: do **not** silently flip the company to Non-GST. Prompt/block at first GST Complete until GSTIN is saved (period close already treats `GSTIN_MISSING_COMPANY` as critical). | S7 must not leave “invoice GST then fail close” as a surprise. |

---

## Current → 80 (living scores, 2026-09-14)

Chart dated 13 Sep morning is **stale**. Rows move only when the rubric above is fully met.

| Dimension (chart label) | Now | 80% | Sessions | Evidence |
|---|---:|---:|---|---|
| At-rest integrity (L1) | 85 | hold | S1a | `INVARIANTS_STRICT=1` on `test_holistic_80` / `test_holistic_remaining` |
| Single-flow function (L2–L3) | 80 | 80 | S1b | `/purchases/history` + `/invite` JOURNEY; LIM for quick-entry/bill-upload |
| Persona / archetype (L4) | 80 | 80 | S4 | `lifecycle-roles.spec.ts` + `test_holistic_80.test_cashier_cannot_complete_return_accountant_cannot_close` |
| Cross-flow semantics (L8) | 80 | 80 | S0 + S5 | Catalog overrides regenerated; cashier history Returned after Owner return |
| Calculation identity (L10) | 80 | 80 | S3 | `projection.py` on CI invariant-sweep; TB.balanced after close |
| Historical / reversal | 80 | 80 | S2b | Calendar month N TB/aging as-of unchanged after N+1; PDF snapshot; 4xx in N |
| Lifecycle journey (L9) | 80 | 80 | S2a | ARCH-01 + ARCH-03 + `lifecycle-arch03-purchase.spec.ts` |
| Insight / decision | 80 | 80 | S6 (**C6-80**) | Attention `AR_RESIDUAL_AFTER_RETURN`; dunning eligible; KPI=aging; G-23 existing. Not High |
| UX / mental-model | 80 | 80 | S7 (**C6-80**) | glossary, recon labels, Hindi outstanding/Returned, B14 GSTIN prompt. Not High |

S5b (advisory→blocking) is **out of scope** until A3's two green CI weeks. Event-matrix cells are filled (LIM/GAP allowed; none blank).

---

## Wave 0 — Catalog honesty (must be first)

### S0 — Relabel what goldens already prove · effort S

**Why:** `/pay/:token`, residual DN, Hindi chip, allocate, complete, challan convert are still **GAP** in `FLOW_CATALOG.md` even though ARCH-01/03 and ops goldens drive them. A reviewer looking at the catalog will not give Cross-flow or Lifecycle 80%.

**Steps**
1. Read `validation/overrides.yaml` and `web/e2e-golden/*.spec.ts`.
2. Override only routes/actions a golden **asserts a money/status consequence** on (not merely visits).
3. `python validation/tools/build_flow_catalog.py`
4. Fail the session if you relabel a route with no assertion (that is score inflation).

**Acceptance:** `/pay/:token`, `/sales/debit-notes/new`, `residual_debit_note`, `return_with_auto_cn`, `hindi_locale_money_screens` are JOURNEY or LIM with a cited spec path. GAP count drops only for evidenced rows.

**Do not:** mark `/sales/quick-entry` JOURNEY without a golden.

---

## Wave 1 — Hold 85 / push single-flow to 80

### S1a — At-rest no-regression · effort S

Run (do not weaken):
- `INVARIANTS_STRICT=1` locally on a books-on tenant test file if the job exists
- `pytest backend/tests/test_holistic_remaining.py backend/tests/test_wave15d_books.py -q`

**Acceptance:** 85% row unchanged. No new `no_invariant_check` except a documented mid-state test.

### S1b — Remaining SUPPORTED pages that are still SMOKE/GAP · effort M

Pick the freeze-in-scope holes, not dark GSTR:

| Surface | Do this |
|---|---|
| `/purchases/history` | Golden: complete a bill, list shows Completed, open row |
| `/invite` | Accept invite and land inside the tenant (review §8 Channel integrity; 7.4 shipped forgot/reset only — invite is still SMOKE in `FLOW_CATALOG.md`) |
| `/sales/quotations` | Already in ARCH-03 — relabel via S0 if assertion exists; else add list assertion |
| `/sales/bill-upload` | LIM if OCR is still aid-only; do not fake a JOURNEY |
| `/sales/quick-entry` | Explicit LIM in overrides (reachable, not freeze-journeyed) |

**Acceptance:** single-flow rubric ≥80% of SUPPORTED named workflow pages are JOURNEY or LIM. New specs under `web/e2e-golden/` or `web/e2e/`.

---

## Wave 2 — Lifecycle 80 + Historical 80

### S2a — Third lifecycle (purchase residual) · effort M

**New file:** `web/e2e-golden/lifecycle-arch03-purchase.spec.ts` (or extend ARCH-03 only if runtime stays ≤ 5 min; else new file per A6).

Journey: complete purchase → partial supplier payment → full purchase return → residual purchase DN → AP aging / attention → period still open.

**Acceptance:** Playwright golden green. Catalog labels `/purchases/debit-notes/new` JOURNEY. Lifecycle rubric complete (ARCH-01 + ARCH-03 + this file).

### S2b — Closed month N must not move when N+1 happens · effort M

ARCH-03 currently closes **today–today**. That is not historical truth (review §0.4 / §8 “Time / subsequent event” + “Historical integrity”).

**Clock (locked):** close a completed **calendar month N** (`start` = first of N, `end` = last of N). Operate in month **N+1** using **document dates**, not wall-clock hacks. Do not use `getByLabel('End')` without `{ exact: true }` (FY End collision).

1. In month N: complete the ARCH-03 (or S2a) money story; **capture** TB totals, dashboard AR, and customer aging for period N (API or UI text).
2. Close month N. GET returned invoice 200, status RETURNED, PDF bytes unchanged, live outstanding = residual.
3. In month N+1: post a **new** invoice (Complete → 200). New invoice dated **inside** closed N → 4xx.
4. Re-read month N TB / dashboard AR / aging — **must equal the capture from step 1**. The N+1 invoice must not rewrite N’s picture.

Backend `test_historical_invoice_readable_after_period_close` covers the document-still-readable half. This session adds the **closed-period surfaces stay still** half.

**Acceptance:** Historical rubric complete. Negative-path (4xx in N, 200 in N+1) alone is **not** enough to publish 80%.

---

## Wave 3 — Calculation identity 80

### S3 — Strict identities on CI + one golden foot · effort M

1. Wire `INVARIANTS_STRICT=1` on the **existing** invariant-sweep CI job (not a new layer). Short-circuit when the company has no relevant docs (A4).
2. After ARCH-03 (or S2b) close, golden asserts trial-balance balanced (UI Books Health or TB page).
3. Keep 2300 advances **out** of AR control (false close block). Docs↔GL = tagged 1200 vs document outstanding.
4. PDF vs live outstanding: assert PDF still shows issued total after return (B2); `/pay/:token` shows live (B3).

**Acceptance:** Calculation rubric complete. `projection.py` identities fail CI when dashboard AR ≠ aging on a books-on company with docs.

---

## Wave 4 — Persona 80

### S4 — Cashier and accountant, not only Owner · effort L

Owner `registerTenant` goldens cannot take L4 to 80%.

**Locked (B13):** period **close is Owner-only**. `AccountingPeriodViewSet.close` / `soft_close` use `IsOwner` (BB-000453). Accountant is `CanPostJournals` + `CanViewFinancialReports` and **must 403** on close. Do not “try close and branch.”

1. Helper: `inviteOrCreateStaff(page, { role: 'cashier' | 'accountant' })` against live backend (same golden config as ARCH-01).
2. **Cashier:** POS cash sale → history shows Paid. Open `/sales/returns` → Complete disabled or 403. Stock still decremented.
3. **Accountant:** post or view a journal; open TB/P&L; **POST close → 403**. Owner then closes. Arithmetic on the POS sale must match Owner’s history.
4. Do not add manufacturing/payroll UI goldens into freeze counts (`dark_module`).

**Acceptance:** Persona rubric complete. Two non-Owner roles, one company, same invoice number, different affordances, same money, Owner-only close.

---

## Wave 5 — Cross-flow 80

### S5a — Same story for the cashier · effort M

After S4’s POS sale + Owner return: cashier login sees Returned (not Paid) on history. `/pay/:token` (if cashier can open it) matches Owner.

### S5b — Writer-impact blocking (only after A3 calendar) · effort S

When two consecutive CI weeks are green: flip writer-impact (and flow-catalog if web lead agrees) from advisory to blocking. Until then, fill empty **event × projection** cells as LIM or GAP in `validation/catalog/events.yaml` — do not leave them blank.

**Acceptance:** Cross-flow rubric complete only if S0 + S5a are done. S5b is the lock so the score cannot decay; it is not required to *publish* 80% if blank cells are already LIM/GAP.

---

## Wave 6 — Insight / decision 80 (needs C6-80)

Without C6-80, ship these as **70%** and stop. That remaining gap to the review’s **High** is H-05, not more goldens.

### S6 — Actionability, not presence · effort L

| Assertion | Where |
|---|---|
| Residual attention row title/reason “residual balance after return”, action Open invoice → `/sales/history/:id` | Already in ARCH-03 — keep |
| Dunning eligible includes RETURNED + residual AR; row walks to that invoice | API + one UI click |
| Dashboard receivables KPI = aging = ledger after return (not Paid) | Golden on `/` after ARCH-01 return |
| Attention row carries a stable `code` (formula id) | Implementation plan **P5-T3**; review §8 Explainability. API contract test. |
| G-23: auto-credit-hold still sees residual AR | Existing `test_a07_dunning.py` plus one UI credit-hold chip if the control exists |

**Acceptance:** Insight rubric complete **only** with C6-80 signed. Still not High (no CA live filing).

---

## Wave 7 — UX / mental-model 80 (needs C6-80)

### S7 — Copy and status language · effort L

LLM can draft; a human must read the screens before claiming 80%. Implementation plan 7.13 (delight proxies) stays advisory — that is **not** this row’s 80%.

1. **Glossary golden:** POS Paid ≠ invoice Completed ≠ Returned. One spec asserts all three chips on the same tenant.
2. **Recon chrome:** `/payments/reconciliation` subtitle = operational match; `/accounting/bank-reconciliation` = GL match. Do not merge UIs.
3. **Hindi:** outstanding and Returned chips, not only पूर्ण (extend `hindi-money-status.spec.ts`).
4. **Skip-wizard Regular (B14):** empty GSTIN → blocking GST-settings prompt (or disable GST Complete) until GSTIN is saved. Do not auto-switch Non-GST. Do not leave Regular+empty-GSTIN+GST invoice+close-blocked as a surprise.
5. **Tokenless reset-password:** already shows missing-token + Request a new link.

**Acceptance:** UX rubric complete requires C6-80 **and** a founder/PM 30-minute pass on the glossary screens. Automation alone tops out ~65–70% on this row (review §11). The leftover from 80% to **High** is still H-05 / live-shop copy, tracked outside this plan.

---

## Session order (do not parallelize S0 with score updates)

```text
S0 catalog honesty
 → S1a hold L1 + S1b single-flow 80
 → S2a purchase lifecycle + S2b month-boundary close
 → S3 identities on CI
 → S4 cashier + accountant (Owner closes)
 → S5a cashier same story
 → [optional S5b after A3 weeks]
 → S6 / S7 only if C6-80 signed
```

S1b and S2a may run as parallel agents **after** S0, on separate branches.

---

## What this plan will not do

- Firefox/WebKit matrix, mutation testing, real Celery broker ordering.
- Turn BoE or GSTR dark pages into freeze journeys.
- Founder-merge of the two recon UIs.
- Declare Insight/UX High without H-05.
- Treat `docs/reviews/MASTER_ISSUE_REGISTER.md` as a live backlog (CR/R/BB were mined into Q-OS — see implementation plan relationship note).

## Post-80 LLM leftovers (closed in this tree)

Accounting journal golden is live (not `test.fixme`). Freeze-SUPPORTED presence-only pages are LIM; redirects are LIM (or OUT when dark); `/forgot-password` and `/reset-password` are JOURNEY via auth-recovery; SPA `/*` is LIM. Collection walk golden + credit-hold chip/settings exist. Founder/calendar items in the section above remain out of scope — do not flip A3, merge recon UIs, turn BoE on, or claim Insight/UX High.

When every signed row’s **rubric** is met, update `HOLISTIC_VALIDATION_REVIEW.md` §0.9 from evidence, not from this file’s targets. Keep the band (Low/Medium/High) as the review’s language; put the percent in parentheses as today.
