# Holistic Validation — path to 90% then 95% (executable)

**Status:** V2–V6 executed 2026-09-14 · **V0 dates blank** · **V1 not flipped** · **Companion to:** [`HOLISTIC_VALIDATION_80_PLAN.md`](HOLISTIC_VALIDATION_80_PLAN.md) (done: 80% session bar) · [`HOLISTIC_VALIDATION_IMPLEMENTATION_PLAN.md`](HOLISTIC_VALIDATION_IMPLEMENTATION_PLAN.md) · [`HOLISTIC_VALIDATION_REVIEW.md`](HOLISTIC_VALIDATION_REVIEW.md) §0.9 / §0.10 / §11 · [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md) L7 + gap register  
**Scoreboard:** living table in this file. Do not cite a Cursor canvas as if it lived in git.  
**Owner:** founder + whoever runs the sessions below  
**Prerequisite:** 80-plan S0–S7 evidenced. Do not start V-sessions to “fix 80.”

This is HOW to take each review §0.9 dimension from the **80% session bar** to **~90 (High locked in CI)** then **~95 (freeze / go-live)**. It does not replace L1–L10. It does not invent G-ids. It does not flip A3 before two consecutive green CI weeks. It does not delete a recon UI. It does not count `dark_module` PJ tests as freeze coverage. It does not claim Insight/UX **High** without H-05.

---

## Why 90 and 95 exist (and why they are not more goldens)

Percents in the 80-plan are **reviewer-confidence anchors**, not “JOURNEY routes ÷ all routes.” The review’s claim is the **band** (High vs Medium-high). This file maps those bands onto two checkable bars so work has an order:

| Bar | Meaning | What it certifies |
|---|---|---|
| **80-plan (done)** | Claim-ready-plus | A founder can defend the row in a freeze *review of the suite* — short of High / H-05 |
| **~90 — High locked** | Review **High** on L1–L10 except Insight/UX; those two stay Medium-high until H-05 | CI would go red if the row’s evidence decayed. Catalog/writer gates blocking. Honest LIM leftover only where freeze says so |
| **~95 — freeze / go-live** | L7 + live operators | Real shop / CA / clerk would act on the same numbers. A1–A6 flagged before merge to `main` |

**80% ≠ High ≠ 95%.** Insight/UX **High (~90+)** is H-05 / L7 fieldwork (locked **C6**). Automation alone cannot take those two rows past the 80-plan ceiling. Padding attention-presence tests is out of policy.

| Artifact | Success bar |
|---|---|
| Review §0.9 bands | Low → High. Insight/UX High = H-05 |
| Implementation runbook exit | High on most rows; **Medium-high** on decision quality (C6) |
| 80-plan | 80 on every chart row — **executed 2026-09-14** |
| **This 95-plan** | 90 then 95 as defined above |

---

## Scoring (so “we hit 90 / 95” is checkable)

A session may move a row **only when every rubric item for that bar is evidenced.** Then set 90 or 95 (or hold). Do not interpolate 87, 92, etc. from partial work.

| Dimension | 90% (High locked) is earned when | 95% (freeze) is earned when |
|---|---|---|
| At-rest (L1) | Mutation audit on money/tax/stock in a **Linux CI** lane (G-mutation); prod-shaped dump → `migrate` → `INVARIANTS_STRICT` sweep (G-11b); no new `no_invariant_check` except a documented mid-state | Same on a real Postgres books-on tenant with history. Hold ≥85; this row is already High |
| Single-flow (L2–L3) | Freeze-SUPPORTED **named workflow** pages that the UI can drive are JOURNEY (money/status), not LIM-by-habit. OCR / recurring / dark stay LIM or OUT. **flow-catalog** blocking (after A3) | A1–A6 flagged before `main`. Remaining LIM only where `FREEZE_SCOPE.md` says reachable-not-journeyed |
| Persona (L4) | Same-company money + denied affordance still green in CI. One additional freeze persona (P3 or P4) **money** golden if that role is in freeze — not more Owner-only loops. `dark_module` does not count | Live ARCH-03: Owner + clerk + CA see the same Returned / outstanding |
| Cross-flow (L8) | **V1 / A3:** two consecutive green CI weeks, then writer-impact **and** flow-catalog `continue-on-error` removed. Event-matrix cells LIM or GAP, never blank | QOS-0082 founder call recorded (keep both UIs or merge). Both still write `match_status` until that call |
| Calculation (L10) | Named identities still in the strict sweep on every books-on CI job. PDF snapshot vs live `/pay/:token` (B2/B3) stays | CA uses TB / aging / GSTR **without a side spreadsheet** (overlaps H-05) |
| Historical | Second closed month: N **and** N−1 reject backdated Complete; captured N snapshot byte-equal after an N+1 event | Books-on tenant with pre-GL invoices: explicit LIM **or** a backfill journey — do not leave ungated UX |
| Lifecycle (L9) | ARCH-01 + ARCH-03 + purchase residual + accounting journal goldens **green in required CI**. Optional ARCH-04 transfer/count only if it asserts money/stock, not mount | Same stories after a **live** return + residual + close. G-12 extra browsers are hygiene for 95, not the meaning of this row |
| Insight / decision | **Cannot be 90 from automation.** High requires H-05: a practicing CA files from worksheets in a live 1st–20th window with no recalc (G-14) | 3–5 CAs, not one. Residual AR still credit-holds in the wild (G-23 already API-gated) |
| UX / mental-model | **Founder/PM 30-minute pass** on glossary screens (Paid ≠ Completed ≠ Returned, recon labels, Hindi बकाया/वापस, B14 GSTIN prompt). 7.13 POS &lt; 35s stays advisory unless founder makes it a merge gate | H-02 live counter speed; H-03 offline outbox in the shop; “would I pay” / copy tone (L7). H-05 also feeds this row |

Partial credit does not raise the published percent.

---

## Founder / calendar gates (do not skip or relitigate)

Copied from review §0.10 and the 80-plan. This file does not mint new C-/A-/B- ids.

| Id | Decision | If unsigned / not elapsed |
|---|---|---|
| **C6** | Decision-quality **High** is H-05 / L7, not automatable | Do not report Insight as High |
| **C6-80** | Signed 2026-09-14 — 80% on Insight/UX allowed; still not High | — |
| **A3** | After **two consecutive green CI weeks**, flip `flow-catalog` (+ writer-impact with Phase 6 / S5b) from advisory → blocking | V1 waits. Catalog honesty still runs advisory |
| **A1–A6** | Working defaults; **flag to founder before merge to `main`** | Required for 95, not for starting V2–V6 |
| **QOS-0082** | Consolidate the two recon UIs? | Keep both; both write `match_status`. V11 is the founder call |
| **H-05** | CA files from worksheets in a live window | Blocks Insight/UX **High (~90+)** |
| **B6** | BoE stays dark | Do not enable `ENABLE_BOE` in this plan |
| **B8** | Two recon UIs until QOS-0082 | Do not merge in a V-session |
| **B13** | Period close Owner-only | Do not invent a second close-permission model |
| **B14** | Regular + empty GSTIN: prompt/block; do not flip Non-GST | Already golden’d; do not regress |

---

## Current → 90 → 95 (living scores, 2026-09-14)

Baseline **Now** moves only when the rubric above is fully met. V2–V6 are evidenced in-repo; V0/V1/V7–V12 are not.

| Dimension (chart label) | Now | 90 | 95 | Sessions | Blocked on |
|---|---:|---:|---:|---|---|
| At-rest integrity (L1) | **90** | 90 | 95 | V3 done | Live Postgres books-on tenant at 95 |
| Single-flow function (L2–L3) | 80 | 90 | 95 | V2 done; **V1** | **90-pending-lock** until A3 / V1. Freeze workflows are JOURNEY |
| Persona / archetype (L4) | **90** | 90 | 95 | V5 done; live in V10 | Live ARCH-03 clerk + CA |
| Cross-flow semantics (L8) | 80 | 90 | 95 | **V1** then V11 | A3 calendar; QOS-0082 |
| Calculation identity (L10) | **90** | 90 | 95 | V3 hold + H-05 | CA without a side spreadsheet (H-05) |
| Historical / reversal | **90** | 90 | 95 | V4 done | Pre-GL backfill is JOURNEY; live history at 95 |
| Lifecycle journey (L9) | **90** | 90 | 95 | V6 done | Live shop at 95 (V10) |
| Insight / decision | 80 | — | 95 | **V8** (H-05) | Human. No LLM path to 90 |
| UX / mental-model | 80 | 90 | 95 | **V7** then V10 | Founder/PM pass; then H-02/H-03 |

Insight has **no 90 cell** on purpose: the next honest score is the review band **Medium-high → High**, which is H-05 (publish ~90–95 together).

### Scoreboard notes (2026-09-14)

- **V0:** week-1 / week-2 green `flow-catalog` dates — **blank**. Do not treat local catalog regen as A3.
- **V1:** not flipped. `flow-catalog` and `writer-impact` stay `continue-on-error`. `ADVISORY` stays True.
- **V2:** JOURNEY on `/purchases/orders`, `/purchases/orders/new`, `/payments/links`, `/payments/statements`, `/accounting/accounts`, `/reports/books-health`. `/purchases/orders/:id` stays LIM. OCR / recurring / quick-entry / `/ca-needs` stay LIM. Dark CRM/MFG/payroll/BoE stay OUT.
- **V3:** Linux CI `mutation-audit` remains advisory (comment cites V3). G-11b: `backend/tests/test_holistic_95.py::test_v3_g11b_export_migrate_restore_invariants` **and** `scripts/migration_rehearsal.sh` runs `check_invariants` after synthetic seed (warns unless `INVARIANTS_STRICT_REHEARSAL=1`; not a prod dump). `projection.ar_dashboard_equals_aging` still gates. No new `no_invariant_check`. Survivor triage (2026-09-16): `tests/gst/test_mutation_audit_survivors.py` pins extract_state_code / DEXP≠96 / parse_month_period / opening_is_voided. Do not claim Windows mutmut.
- **V4:** `test_v4_n_and_n_minus_1_closed_reject_backdated_complete`. 95 add-on: `v95-backfill.spec.ts` (pre-GL completed invoices show the backfill banner).
- **V5:** `v95-inventory-staff.spec.ts` + `test_v5_inventory_staff_can_transfer_cannot_journal_or_close`. Invite role Inventory staff.
- **V6:** `lifecycle-arch01`, `lifecycle-arch03`, `lifecycle-arch03-purchase`, `accounting-golden-path` remain required e2e-golden (not `test.fixme`). This session: ARCH-01, purchase residual, accounting, and ARCH-03 green locally. ARCH-03 helper now confirms the CFT-115 convert dialog. ARCH-04 topology already `inventory-ops-golden-path.spec.ts`.
- **V7 / V8 / V9 / V10 / V11 / V12:** not run. Do not claim Insight/UX High. Do not merge recon UIs. Do not flag A1–A6 as signed.

Engineering-only 2026-09-16 (does **not** fill tracker dates or raise published 90/95): invite UI `capsForRole` gated against backend defaults; open Q-OS freeze overlay in `docs/ops/QOS_FREEZE_CLASS.md`; Table B deploy defaults stay off.

### 95-sprint tracker (founder-owned; 2026-09-15)

LLM Wave 0 leftovers are in-repo (G-6b executed, AuditEvent on complete/cancel/allocate/amend, beat dry-run, G-11b rehearsal sweep, G-4/G-12 docs). Remaining LLM-doable WF stubs closed the same day: WF-14 sales-bill CSV idempotency; WF-20/23/24/25 unskipped pointers; WF-45-verify LIM pin. **The only remaining pytest skip in the workflow modules is WF-37/38 (sandbox creds).** **Do not raise Insight/UX High or Single-flow/Cross-flow published 90 from this tracker.** Fill dates when the human/ops step actually happens.

| Wave | Action | Date | Who | Unblocks |
|---|---|---|---|---|
| V0 week-1 | `flow-catalog` green on `main` (CI job, not local regen) | _blank_ | ops | V1 clock |
| V0 week-2 | second consecutive green week on `main` | _blank_ | ops | V1 flip |
| V7 | 30-min glossary pass (Paid ≠ Completed ≠ Returned; two recon labels; Hindi बकाया/वापस; B14 GSTIN) | _blank_ | founder/PM | UX **90** |
| V11 | QOS-0082: keep both recon UIs **or** merge (do not implement a merge in an LLM session) | _blank_ | founder | Cross-flow **95** |
| V12 | A1–A6 working defaults flagged before merge to `main` (BoE stays dark) | _blank_ | founder | Single-flow **95** |
| V8 / H-05 | CA files from worksheets in a 1st–20th window (`docs/ca/CA_SIGN_OFF_CHECKLIST.md`) | _blank_ | CA | Insight **High** |
| V10 | Live counter H-02 + H-03 outbox + ARCH-03 residual (`docs/pilot/UAT_CHECKLIST.md`) | _blank_ | operators | L4/L9/UX **95** |
| A25 | Cashfree/PayU sandbox + `SANDBOX_WEBHOOK_SECRET` in CI, then unskip WF-37/38 | _blank_ | ops | G-3 recovery |
| V9 | WebKit goldens? default **no** unless founder asks | _blank_ | founder | G-12 hygiene |
| Wave 2 | TLS host; SMTP `sendtestemail`; Sentry `sentry_test_event`; staging k6 budget in `load/README.md`; real Celery broker | _blank_ | ops | G-7 / G-10 / Go-No-Go |
| Wave 6 | Sign `docs/pilot/GO_NO_GO.md` (do not tick boxes without the named human) | _blank_ | PM/Eng/QA/CA/Ops | freeze declaration |

**V1 flip recipe (do not run until both V0 dates are filled):** remove `continue-on-error: true` from `flow-catalog` and `writer-impact` in `.github/workflows/ci.yml`; set `ADVISORY = False` on `guard_flow_catalog_drift.py` and `guard_writer_impact_coverage.py`; update `REQUIRED_CHECKS.txt` / `GATE_INVENTORY.md`. Fix catalog drift first. Local `build_flow_catalog.py` is not A3.

**WF-37/38 unskip recipe (do not run until A25 creds exist):** replace `@pytest.mark.skip(reason=_G_SANDBOX)` in `backend/tests/workflows/test_wf_extended_stubs.py` with a real refund/MDR chain + `assert_consistent`. Signature/replay is already G-8.

---

## How an LLM session must run

Paste this block as the first message of every **automatable** V-session. Human/calendar sessions (V0, V1 wait, V7, V8, V10, V11, V12) are not LLM-completable; do not pretend they are.

```text
You are executing docs/HOLISTIC_VALIDATION_95_PLAN.md session VN.
Product-truth only. If the UI cannot drive the journey, fix the product, do not shrink the golden.

HARD RULES
- Do not flip flow-catalog or writer-impact to blocking unless this session is V1 and A3's two green CI weeks are already on the calendar (cite the two green week dates).
- Do not delete /payments/reconciliation or /accounting/bank-reconciliation (B8 / QOS-0082).
- Do not count pytest.mark.dark_module as freeze coverage.
- Do not claim High decision quality. Do not invent G-ids. Do not mint CR-/R-/P1-/P2- ids.
- Do not turn ENABLE_BOE on. Do not make POS < 35s a merge-blocking gate unless the founder asked in this session.
- BB-000265: if payment_gateway is Razorpay with empty credentials, do NOT silently remap the provider to sandbox. Tests and goldens must set provider=Sandbox via /settings/payment-gateway first.
- Windows PowerShell: use `;` not `&&`. Playwright goldens: npm run test:e2e:golden.
- Do not commit unless I ask.

ACCEPTANCE
- Named files in the session exist and the listed command is green.
- FLOW_CATALOG.md regenerated if you added/relabeled a route:
  python validation/tools/build_flow_catalog.py
- Update HOLISTIC_VALIDATION_REVIEW.md §0.9 only when the scoring rubric for that row's bar (90 or 95) is fully met. Keep the band as the claim; put the percent in parentheses.
- Do not raise a published percent on partial rubric items.
- Do not publish Insight High without H-05 evidence in this file's scoreboard notes.

TASK
<paste session task>
```

After each session: regenerate catalogs if routes/events changed, then re-score only rows whose **full** rubric for that bar passed.

---

## Wave 0 — Calendar (must elapse; not an LLM task)

### V0 — Start the A3 clock · effort none (ops)

**Why:** V1 cannot flip gates until `flow-catalog` (and, for writer-impact, the Phase 6 / S5b clock) has been **green two consecutive weeks** on the default branch.

**Steps**
1. Record week-1 and week-2 green dates in this file’s scoreboard notes when they happen (CI job `flow-catalog` in `.github/workflows/ci.yml`, today `continue-on-error: true`).
2. Do not flip early. A3 is locked.

**Acceptance:** two dated green weeks cited. No code.

**Do not:** treat local `python validation/tools/build_flow_catalog.py` green as A3.

---

## Wave 1 — Lock the graphs (~90 on Cross-flow; lock for Single-flow)

### V1 — Flip advisory → blocking (only after V0) · effort S · **calendar-gated**

**Files:** `.github/workflows/ci.yml` (`flow-catalog`, `writer-impact` — remove `continue-on-error: true`); `scripts/ci_gates/guards/guard_flow_catalog_drift.py` and `guard_writer_impact_coverage.py` (`ADVISORY = False`); `scripts/ci_gates/REQUIRED_CHECKS.txt` comments; `scripts/ci_gates/GATE_INVENTORY.md`.

**Steps**
1. Confirm V0 dates.
2. Flip both jobs and both guards together (80-plan S5b + A3). If web lead wants flow-catalog one week later than writer-impact, record that split in the scoreboard — do not leave one advisory forever.
3. `python scripts/ci_gates/run_guards.py --include-advisory` must be redundant after the flip (advisory set is empty for these two).

**Acceptance:** a deliberate catalog or writer-without-reader diff **fails CI**. Cross-flow **90**. Single-flow lock in place (score moves with V2).

**Do not:** flip on a red catalog. Fix drift first, then flip.

---

## Wave 2 — Honest JOURNEY remaining freeze workflows (~90 Single-flow)

### V2 — LIM → JOURNEY only where the UI drives a consequence · effort M · **LLM-ok**

**Why:** 80-plan allowed honest LIM for presence-only SUPPORTED pages. 90 requires named **workflows** to be JOURNEY.

**Candidates (JOURNEY if the UI can complete a money/status job; else stay LIM with a one-line note):**

| Surface | Do this |
|---|---|
| `/purchases/orders` + `/purchases/orders/new` | Golden: create PO → visible on list with a real status |
| `/accounting/accounts` | After `enableAccounting`, CoA shows seeded `1100` (or equivalent) and a posted journal hits it |
| `/payments/statements` | Import or list a statement line; assert it exists (not heading-only) |
| `/payments/links` | List shows a link created from invoice detail (ARCH-03 already creates; assert the **list** page) |
| `/reports/books-health` | After a journal or invoice, the page shows a health consequence, not only a title |
| `/sales/bill-upload`, `/purchases/bill-upload` | **Stay LIM** (OCR aid-only) |
| `/sales/recurring`, `/sales/quick-entry` | **Stay LIM** (B7 / not freeze-journeyed) |
| `/ca-needs` | **Stay LIM** until H-05 |
| Dark `/crm` `/manufacturing` `/payroll` `/purchases/bills-of-entry` | **Stay OUT** |

**Steps**
1. Read `docs/FLOW_CATALOG.md` LIM rows with a freeze A-row.
2. For each candidate, either add `web/e2e-golden/*.spec.ts` that asserts money/status, or leave LIM.
3. `python validation/tools/build_flow_catalog.py` — do not mark JOURNEY without an assertion.

**Acceptance:** freeze-SUPPORTED **named workflow** pages are JOURNEY or explicit freeze-LIM. SMOKE/GAP/UNMAPPED remain 0 on those pages. Single-flow **90** after V1 lock (or 90-pending-lock if V0 not elapsed — publish 90 only when V1 is done).

**Do not:** relabel settings/backup/templates JOURNEY for visiting the heading.

---

## Wave 3 — At-rest and calculation stay High (~90 L1 / L10)

### V3 — Mutation lane + dump migrate · effort L · **ops + LLM**

**Why:** L1 is already High (~85%). 90 is “we would catch a silent behaviour change,” not more invariant names.

**Steps**
1. **G-mutation:** run `scripts/mutation_audit.sh` in a **Linux CI** advisory job; triage survivors on money / tax / stock modules first (`TESTING_STRATEGY.md` G-mutation). Do not claim Windows mutmut.
2. **G-11b:** CI or runbook step — restore an anonymised dump, `migrate`, `INVARIANTS_STRICT=1` sweep.
3. Confirm `backend/core/invariants/projection.py` identities still fail CI when dashboard AR ≠ aging on a books-on company with docs.
4. No new `no_invariant_check` except a documented mid-state.

**Acceptance:** L1 **90**. L10 **90** if identities still gate CI (they should already). Commands: mutation job log + migrate+sweep green.

**Do not:** add vanity identities for metrics that are not user-facing.

---

## Wave 4 — Historical second month (~90 Historical)

### V4 — N and N−1 · effort M · **LLM-ok**

**Files:** extend `backend/tests/test_holistic_80.py` (or a sibling) — do not weaken `INVARIANTS_STRICT`.

**Steps**
1. Close calendar month N; capture TB / dashboard AR / aging as-of N.
2. Complete a document in N+1; as-of N snapshot **byte-equal**.
3. Backdated Complete into **N−1** (already closed) is 4xx; N+1 is 200.
4. Returned invoice stays RETURNED after both closes.

**Acceptance:** Historical **90**. Negative-path 4xx alone is not enough (already true at 80).

**95 add-on (same wave or later):** document pre-accounting invoices as LIM **or** a backfill journey. Do not leave “old invoice, no GL” as surprise UX.

---

## Wave 5 — Persona without volume (~90 L4)

### V5 — One more freeze role, money + deny · effort M · **LLM-ok**

**Why:** Owner + cashier + accountant already 80. 90 is not three more Owner goldens.

**Steps**
1. If P3 (store ops) or P4 (warehouse) is freeze-SUPPORTED for the lead tenant, add one golden: they can complete **their** money/stock job and **cannot** close a period / post a journal (B13).
2. If that role is not in freeze, record LIM and do not invent a journey.
3. `dark_module` tests still do not count.

**Acceptance:** Persona **90**. Same-company facts still match Owner after the extra role acts.

---

## Wave 6 — Lifecycle stay-green (+ optional ARCH-04) (~90 L9)

### V6 — CI stay-green; optional fourth lifecycle · effort S–L · **LLM-ok**

**Steps**
1. Required CI job `e2e-golden` stays green: `lifecycle-arch01`, `lifecycle-arch03`, `lifecycle-arch03-purchase`, `accounting-golden-path` (not `test.fixme`).
2. Optional for topology (not volume): ARCH-04 transfer or stock-count golden that asserts **godown stock + valuation**, not a heading. Skip if freeze COND and no product owner asked.

**Acceptance:** Lifecycle **90** from (1) alone. (2) is extra topology, not a third 80-plan.

**95:** replay ARCH-01 or ARCH-03 on a live tenant after a real return (V10).

---

## Wave 7 — UX High starts here (~90 UX) · **human**

### V7 — Founder/PM 30-minute glossary pass · effort S · **not LLM**

**Screens (already golden’d — a human must read them):**
1. POS **Paid** vs invoice **Completed** vs **Returned** (`glossary-status` golden).
2. `/payments/reconciliation` vs `/accounting/bank-reconciliation` subtitles (do not merge).
3. Hindi outstanding + Returned (बकाया / वापस).
4. Regular + empty GSTIN → GST Complete prompt (B14). Do not auto-switch Non-GST.

**Acceptance:** written note in this file’s scoreboard (date + who). UX **90**. Implementation plan 7.13 (POS &lt; 35s) stays **advisory** unless founder promotes it.

**Do not:** let an LLM “pass” the screens from screenshots alone.

---

## Wave 8 — Insight High (~90–95 Insight) · **human, P0**

### V8 — H-05 live CA filing · effort XL · **not LLM**

**Why:** G-14. Worksheets + `guard_ca_tax_parity` are proxies. High is “CA files, no recalc.”

**Steps** (from `TESTING_STRATEGY.md` / `pilot/`):
1. Stage 3 pilot, real 1st–20th GST window.
2. Practicing CA files from Bizboard GSTR / CA-needs worksheets.
3. Fail the hypothesis on rejection for mismatched splits or imbalanced books.
4. Log evidence (who, period, outcome) in `pilot/` and this scoreboard.

**Acceptance:** Insight band **High (~90)** after one successful filing; **95** after 3–5 CAs or a second window. Update review §0.9 **band** from Medium-high → High only then.

**Do not:** add more attention-presence goldens and call it 90.

---

## Wave 9 — Channel hygiene (95 on Lifecycle / Single-flow, not the meaning of those rows)

### V9 — G-12 browsers · effort M · **LLM-ok after founder ask**

Add a WebKit (and optionally Firefox) project for **golden + a11y** only if founder wants 95 hygiene. Fix or formally accept the two known mobile-viewport fails (`TESTING_STRATEGY.md` G-12).

**Acceptance:** does **not** by itself publish 95 on L9. It is a 95 *hygiene* checkbox.

---

## Wave 10 — Live shop (95 Persona / UX / Lifecycle)

### V10 — H-02, H-03, live residual · effort XL · **human**

| Hypothesis | 95 evidence |
|---|---|
| H-02 | Live counter: checkout usable at speed (7.13 wall-clock may become a gate **only** if founder says so) |
| H-03 | Offline outbox flush in the shop; no silent drop |
| L9 live | Return + residual + close on a real ARCH-03 tenant; cashier history matches Owner |
| L4 live | Clerk + CA see the same outstanding |

**Acceptance:** Persona / UX / Lifecycle **95** when the live notes exist. Use `pilot/UAT_CHECKLIST.md` and `pilot/ARCH03_PILOT_RUNBOOK.md`.

---

## Wave 11 — Recon product-truth (95 Cross-flow)

### V11 — QOS-0082 founder call · effort S · **human**

Keep both UIs **or** merge. Until the call: both write `match_status`; S7 labels stay. Do not implement a merge in an LLM session.

**Acceptance:** QOS-0082 `verified` or `accepted_wontfix` with rationale. Cross-flow **95**.

---

## Wave 12 — Merge to main (95 Single-flow lock)

### V12 — Flag A1–A6 · effort S · **human**

Working defaults today. **Flag to founder before merge to `main`.** Required for 95 on Single-flow, not for V2 work on a branch.

**Acceptance:** written founder flag. BoE still dark unless that flag explicitly changes B6.

---

## Session order

```text
V0  start A3 clock                          (ops, now)
V2  honest LIM→JOURNEY                      (LLM, parallel with V4–V6)
V3  mutation + dump-migrate                 (ops + LLM)
V4  second closed month                     (LLM)
V5  extra freeze persona if in scope        (LLM)
V6  lifecycle CI stay-green                 (LLM)
V7  founder/PM glossary pass                (human)     → UX 90
V1  flip gates                              (after V0)  → Cross-flow 90; lock L2
V8  H-05 CA filing                          (human)     → Insight High
V9  WebKit optional                         (LLM if asked)
V10 live H-02 / H-03 / residual             (human)     → 95 on L4/L9/UX
V11 QOS-0082                                (human)     → Cross-flow 95
V12 A1–A6 before main                       (human)     → Single-flow 95
```

V2–V6 may run in parallel **after** this file is the agreed plan. **V1 must not precede V0.** **V8 is on the critical path for Insight; nothing else substitutes.**

---

## What this plan will not do

- Redefine High as 80, or 95 as “more Playwright files.”
- Firefox/WebKit / mutation / real Celery **as a substitute** for H-05.
- Turn BoE or GSTR dark pages into freeze journeys.
- Founder-merge of the two recon UIs inside an LLM session.
- Declare Insight/UX High without H-05.
- Treat `docs/reviews/MASTER_ISSUE_REGISTER.md` as a live backlog.
- Invent G-ids or a second pyramid besides L1–L10.

When a row’s **90 or 95 rubric** is met, update [`HOLISTIC_VALIDATION_REVIEW.md`](HOLISTIC_VALIDATION_REVIEW.md) §0.9 from evidence. Keep the **band** as the claim; put the percent in parentheses.

---

## Command cheatsheet

```text
python validation/tools/build_flow_catalog.py
python validation/tools/build_event_matrix.py
python qos/tools/lint.py
INVARIANTS_STRICT=1 pytest backend/tests/test_holistic_80.py -q
cd web; npm run test:e2e:golden
```

Windows PowerShell: `;` not `&&`. Golden ports: `E2E_GOLDEN_API_PORT` / `E2E_GOLDEN_WEB_PORT` if 8000/5173 are busy.
