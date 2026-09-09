# Fix Plan — Functional Code Review 2026-09-07 (CR-106…CR-162)

**Revision:** 2026-09-07b — incorporates plan-review comments A–F (consistency, scope, sequencing, risk, decisions).

**Findings:** [`FUNCTIONAL_CODE_REVIEW_FINDINGS_2026-09-07.md`](./FUNCTIONAL_CODE_REVIEW_FINDINGS_2026-09-07.md) (`CR-106`…`CR-162`).  
**Gap companion:** [`FIX_PLAN_GAP_CLOSURE_2026-09-07.md`](./FIX_PLAN_GAP_CLOSURE_2026-09-07.md) (CR-153, **A15** for CR-090…105, B0 pytest detail, PARTIAL matrix).  
**Prior wave:** [`FIX_PLAN_FUNCTIONAL_2026-09-06.md`](./FIX_PLAN_FUNCTIONAL_2026-09-06.md) (`A1`…`A14`, `CR-001`…`CR-089`). Do **not** renumber prior CRs; cross-close both registers when a B/A15 PR lands.

**Census:** **3 Critical · 16 High · 30 Medium · 8 Low = 57.**

**Unit of work:** PRs **B0**, **A15**, **B1**, **B2a**, **B2b**, **B3–B7**, **B8**, **B8-POS** *(optional)*, **B9–B12**.

**Effort:** **S** &lt; 2h · **M** half-day · **L** 1–2d · **XL** 3+d.

**Team size (authoritative for calendar):** assume **1 engineer** unless Product assigns more. Parallel “‖” lines are optional acceleration only — see §4.1.

**Branching:** cut each PR from current `main` after Depends. Do **not** stack onto `wip/waves-0-abcd`. Rebase or cherry-pick overlapping WIP *after* B0/A15 land on `main`. Relation to in-flight dirty-tree migrations: see §1.4.

---

## Pilot gate (read this first)

Pilot is **blocked** until **all** of the following are green:

| # | Gate | PR / artifact |
|---|------|----------------|
| 1 | **B0** Buckets A+B (money-path pytest green; Bucket C ticketed) | B0 |
| 2 | **A15-V** (esp. **CR-094** cross-tenant DC↔SO); A15-A if any red | A15 |
| 3 | Phase **0** Criticals + Highs | B1, B2a, B2b, B3–B5 |
| 4 | Phase **1** remaining Highs | B6, B7 *(depends B2a)* |
| 5 | Reproducible baseline on **CI Python** (see §1.1) + vitest baseline recorded | §1 |
| 6 | Data remediation for CR-120/144 accepted (detection + backfill + “0 remaining”) | B1 §5.1 |
| 7 | Skipped-test audit: none mask money-path | §1.5 |

Product-accepted deferrals in §0 (**CR-107**, **CR-115**, **CR-116**, **CR-125**, **CR-139**) do **not** block pilot. Phase 2+ (B8, B8-POS, B9–B12) is post-pilot unless Product pulls forward.

---

## Standing checklists (every money/stock PR)

1. New money POST → exact `scope=` in `MONEY_IDEMPOTENCY_SCOPES` **and** FE `Idempotency-Key`.
2. `transaction.atomic` + `select_for_update` covers every row a business check reads; side effects on `on_commit`.
3. **Twin-check Sales ↔ Purchase** (notes/returns/cancel/convert) before merge. If N/A (POS-only, reporting-only, accounting-only): write **`Twin: N/A — &lt;one-line reason&gt;`** in the PR description.
4. Pytest: **fails on the B0-rebaselined `main` tip**, then passes on the PR, for every Critical/High in that PR. Run on **CI Python** (§1.1).
5. Update status lines in **both** findings registers when closing a prior CR — never renumber. **Every B-PR description must name each prior CR it cross-closes** (e.g. `Cross-closes: CR-105, CR-082`). A15-X is not enough alone.
6. **Mandatory CI regression guards** for Critical bypasses (CR-120 mutex, CR-144 no raw `unit_cost` update) — not optional (§17).
7. Prefer a lightweight CI check: if PR title/body matches `CR-\d+`, both findings files must contain `FIXED in B*` / `FIXED in A15` for that ID before merge (§17).

### Test naming convention

| Layer | Pattern | Example |
|-------|---------|---------|
| Backend pytest | `test_crNNN_*` for this wave; keep legacy `test_bb_*` / module names when editing existing tests | `test_cr157_advance_receipt_control_healthy` |
| Frontend vitest | `pos_*` / `offline_*` **without** `test_` prefix (intentional) | `pos_reload_mid_settlement_resumes_receipt_without_cart` |

---

## 0. Locked product decisions

| ID | Decision (one choice) | Who must sign |
|----|----------------------|---------------|
| **CR-107** (≈ CR-002) | **Pilot ships durable client resume only** (CR-106/108/109/112/119). Atomic `POST /pos/checkout/` is **post-pilot**, PR **B8-POS**, feature-flagged. Accepts multi-HTTP half-success window mitigated by resume. | **Product** (not Eng-default) — required before pilot kickoff |
| **CR-115** (≈ CR-008) | `ENABLE_POS` remains **UI sugar** for pilot; document in flags README. | Product (carry) |
| **CR-116** (≈ CR-011) | Till tendered/change audit **Deferred**. Receipt = invoice total. Severity remains Low; status = Deferred. | Product (carry) |
| **CR-125** (≈ CR-022) | Partial SO/DC convert = **known limitation**; help doc only. Severity remains Medium; delivery = doc. | Product (carry) |
| **CR-139** (≈ CR-055) | Transfer DRAFT non-binding / no in-transit — **document only**. Severity remains Medium; delivery = doc. | Product (carry) |
| **CR-154** | Stock ledger report is **post-pilot** (B11). Inventory summary honesty (CR-147/148) ships in B11 for GA; may slip after pilot. | Eng default OK |
| **CR-146 / CR-159** | **Single policy:** (1) Party ledger outstanding uses the **same document-aging basis as dashboard AR/AP**. (2) Soft/hard period close **blocks** when `|docs−GL| > DOCS_GL_CLOSE_TOLERANCE` after advance-netting (see §0.1). Credit-limit may still log `max(GL, docs)` with an explicit audit. | **Product + Eng** — lock before B7 starts |
| **CR-124** (≈ CR-017) | Auto sales-return CN must **auto-unallocate** up to CN amount **or** require explicit confirm — no silent floor. | Eng (carry) |
| **CR-160** (≈ CR-085) | Purchase tax residual **aligns with Sales**: refuse header/line drift &gt; `TAX_LINE_DRIFT_MAX`. **`test_b1_034_*` owner = B11 only** (B0 may mark it Bucket A “triaged → B11”; B0 must not change expectations). | Eng |
| **Pilot data** | During B-wave: **no global write freeze**. Run **nightly detection** for CR-120 dual-fulfillment and CR-144 raw cost mutates (queries in §5.1). Heal on B1 merge + cutover checklist. | Product + Eng |

### 0.1 Money tolerances (single table)

| Constant | Value | Used by | Rationale |
|----------|------:|---------|-----------|
| `TAX_LINE_DRIFT_MAX` | **₹0.05** | CR-160 / Sales twin | Paisa-level GST line vs header; refuse unexplained residual |
| `DOCS_GL_CLOSE_TOLERANCE` | **₹1.00** | CR-159 period close | One rupee after q2 netting; blocks dishonest close without noise on rounding |
| `ADVANCE_CONTROL` | n/a (structural) | CR-157 | Control = 1200↔tagged-1200 only; never fold 2300/1250 into control expected |

Do not invent ad-hoc rupee limits in PR descriptions — reference this table.

---

## 1. Phase −1 — Baseline, Python, money-path, migrations

### 1.1 Python / merge gate

| Fact | Value |
|------|-------|
| **CI merge gate** | Python **3.14** (`.github/workflows/ci.yml`) |
| **Local review baseline (2026-09-07)** | Python **3.12.11** (`backend/.venv`) on dirty tree `5ba05c7` — **not reproducible** |
| **Rule** | Re-run B0 and all “fails then passes” evidence on **3.14** (CI image or local 3.14 venv). Do not treat 3.12.11 dirty-tree counts as the merge gate. |

### 1.2 Reproducible baseline (required before B1)

1. Commit or create an annotated stash / WIP branch tip whose tree hash is recorded (e.g. `git stash create` hash or `fix/b0-baseline` commit).
2. On that clean tip + Python 3.14: `cd backend && pytest -q` → write results to `docs/reviews/_pytest_functional_review_B0_baseline.txt`.
3. On same tip: `cd web && npm test -- --run` → write pass/fail/skip counts to `docs/reviews/_vitest_B0_baseline.txt` (**FE baseline — was missing**).
4. Put both file paths + tip SHA in the **B0** PR description. Later PRs compare against **this** baseline, not the dirty-tree 25-fail snapshot.

### 1.3 Money-path subset (defined)

**Money-path** = these paths must be **0 failures** after B0 Buckets A+B (excluding explicit Bucket C xfails):

```
tests/test_a2_posting_atomicity.py
tests/test_a4_a5_reporting.py
tests/test_a6_manual_serial_return.py
tests/test_a7_a8_a9_highs.py
tests/test_a10_period_centralization.py
tests/test_a11_a12_stock_cost.py
tests/test_a13_a14_reporting_sales.py
tests/test_a15_cr090_plus.py
tests/test_concurrency_races.py
tests/test_phase1_notes_ledger.py
tests/test_phase1_documents.py
tests/test_phase3_payments.py
tests/test_phase5_accounting.py
tests/test_sprint_a_accounting_p1.py
tests/test_pr5_returns_serials_fefo.py
tests/test_pr6_period_gl.py
tests/test_pr7_mdr_recon_dunning.py
tests/test_ws05_period_locks.py
tests/test_gst_returns.py
tests/test_next_batch_so_challan.py
tests/test_wave15_fefo.py
tests/test_wave22_f1_period_money_series.py
tests/test_wave22_f2_fifo_serial_mfg.py
tests/test_search_reports_audit.py
```

Optional marker (follow-up): `@pytest.mark.money_path` on the above — not required to start B0 if the file list is used.

**Not money-path (Bucket C):** GSP live / honesty / sprint_e QR tests — may remain xfail with ticket until e-invoice wave.

### 1.4 Migrations checklist

| Rule | Detail |
|------|--------|
| New schema | Prefer additive nullable columns → backfill → constrain; no non-null default on large tables without chunked data migration |
| B-wave likely migrations | **CR-120** fulfillment mutex/status (if not pure validation); **CR-121** `last_error` / retry fields on recurring schedule; **CR-132** `PurchaseDebitNote.additional_charges`; **CR-161** journal line party FKs |
| Ordering | Land schema in the **same PR** as the behavior that requires it; never depend on unmerged dirty-tree migrations from `accounts/0045`, `manufacturing/0010`, `payments/0027`, `purchases/0031` unless those are already on `main` |
| WIP branch | Do **not** merge B-PRs into `wip/waves-0-abcd`. If WIP already has overlapping migrations, rebase WIP onto `main` after B1/B9/B12 as needed |
| Reversibility | Every migration reversible; data migrations chunked and company-scoped where possible |

### 1.5 Skipped tests audit `[ ]`

After B0 baseline on 3.14, list all **skipped** tests. For each: one-line reason + **money-path risk Y/N**. If Y, either unskip+fix or replace with an active assertion before pilot. Record in B0 PR.

### 1.6 B0 / A15 / tooling table

| Work | Action | PR |
|------|--------|----|
| −1a | Reproducible tip + pytest 3.14 baseline file | B0 |
| −1b | Vitest baseline file | B0 |
| −1c | Triage 25→A/B/C per [gap §3](./FIX_PLAN_GAP_CLOSURE_2026-09-07.md#3-b0-detailed--25-pytest-failures-implementation-plan); land A+B | B0 / B0-G |
| −1d | Bucket C ticket + optional xfail | B0 |
| −1e | Skipped-test audit (§1.5) | B0 |
| −1f | Postgres available for concurrency | env |
| −1g | **A15-V** (+ A15-A if red) | A15 — **parallel with B1–B5 after B0** |

**Phase −1 success:** money-path = 0 failures; Bucket C only remaining reds/xfails with tickets; vitest baseline on file; A15-V recorded (may still be in flight in parallel).

---

## 2. How to execute

1. One PR = one merge to `main` (B8-POS is a separate PR from B8).
2. **B0 (Buckets A+B) is a hard predecessor** for B1–B12 and A15.
3. Critical/High: failing-then-passing tests on CI Python.
4. After lock changes: `test_concurrency_races.py` (+ Postgres).
5. Twin-close + name prior CRs in PR body (§ standing #5).
6. Update both findings registers; never renumber.

---

## 3. Phases (each CR in exactly one phase)

| Phase | Goal | Count | CR IDs | Sev mix | Effort | Gate |
|-------|------|------:|--------|---------|--------|------|
| **−1** | Baseline + B0 + A15 start | — | — | — | M–L | §1 success |
| **0** | Launch blockers | **13** | 120, 144, 157, 156, 158, 106, 108, **119**, 129, 130, 142, 145, 121 | 3C · 9H · 1M | 4–6 d solo | Criticals + POS resume + notes + serial + openings + recurring |
| **1** | Remaining Highs | **6** | 110, 131, 143, 146, 149, 159 | 6H | 2–3 d | Ledger=dashboard; span; offline count; cess |
| **2** | POS Medium hygiene *(no 107)* | **6** | 109, 111, 112, 113, 114, 115 | 5M · 1M-doc | L | Settlement polish |
| **2-opt** | Atomic POS checkout | **1** | 107 | 1H | XL | Post-pilot / Product |
| **3** | Sales/Purchase/Stock Medium | **12** | 122–124, 126, 132–135, 137, 138, 140, 141 | 12M | 3–4 d | Convert/idempotency/count |
| **4** | Reporting Medium + tax | **8** | 147, 148, 150–152, 154, 155, 160 | 8M | 2–3 d | Reserved/value/export/B1-034 |
| **5** | JE tags + Low defense | **5** | 161, 127, 128, 136, 162 | **1M · 4L** | 1–2 d | Party-tag JE; CN locks |
| **6** | Low + Deferred + Medium-doc | **6** | 116 *(L Deferred)*, 117, 118, 153, 125 *(M doc)*, 139 *(M doc)* | **3L · 1L-def · 2M-doc** | S–M | Docs + AP buckets |

**Check:** 13+6+6+1+12+8+5+6 = **57**.

**CR-119:** Phase **0 only** (B3 implements block-new-sale). B8 may add an **extra** integration vitest but does **not** own the CR and must not re-count it.

---

## 4. PRs (authoritative)

| PR | Phase | CR IDs | Depends | Effort | Risk | Revert / runbook |
|----|-------|--------|---------|--------|------|------------------|
| **B0** | −1 | pytest buckets A+B (+C tickets) | — | **M–L** | Med | Revert tests/code per file; restore baseline tip |
| **A15** | −1/0 | CR-090…105 verify (+fix) | **B0** | **S–L** | High if 094 | Revert A15-A only; V is tests/docs |
| **B1** | 0 | **120**, **144** + **data remediation** | **B0** | **L** | Critical | §5.1 runbook |
| **B2a** | 0 | **157**, **158** | **B0** | **M** | Critical | §5.2 runbook |
| **B2b** | 0 | **156** | **B0** | **M** | High | Revert `gst_periods` + Journal post atomic; re-run concurrency |
| **B3** | 0 | **106**, **108**, **119** | **B0** | **L** | High | Revert FE; unpaid recover still works |
| **B4** | 0 | **129**, **130** | **B0** | **L** | High | Revert purchase notes + FE confirms |
| **B5** | 0 | **142**, **145**, **121** | **B0** | **L** | High | Revert serial/aging/recurring; migration for last_error if any |
| **B6** | 1 | **110**, **131**, **143** | B0, B3 helpful | **L** | High | Revert POS tax / return units / offline |
| **B7** | 1 | **146**, **149**, **159** | **B2a**, B0 | **L** | High | Revert ledger basis + span + close blockers |
| **B8** | 2 | **109**, **111–115** | B3 | **L** | Med | Revert FE only |
| **B8-POS** | 2-opt | **107** | B3, Product sign-off §0 | **XL** | High | Feature-flag off = instant disable |
| **B9** | 3 | **122–124**, **126**, **132–135**, **137** | B4 | **XL** | Med–High | Per-path revert; DN charges migration |
| **B10** | 3 | **138**, **140**, **141** | B0 | **M** | Med | Revert stock UI/ops |
| **B11** | 4 | **147**, **148**, **150–152**, **154**, **155**, **160** | B7 helpful | **L** | Med | **Owns `test_b1_034_*`** |
| **B12** | 5+6 | **161**, **127**, **128**, **136**, **153**, **162**, **116–118**, **125** doc, **139** doc | as needed | **M** | Low | Per-area; JE party migration |

### 4.1 Calendar (one engineer — authoritative)

| Week | Work |
|------|------|
| **W0** | B0 (baseline 3.14 + vitest + buckets A/B + skip audit) |
| **W1** | A15-V/(A) ‖ B1 ‖ B2a ‖ B2b ‖ B3 *(serialize if solo: B1 → B2a → B2b → B3 → A15)* |
| **W2** | B4 → B5 → B6 → B7 |
| **W3+** | B8 → B9 → B10 → B11 → B12; **B8-POS** only after Product sign-off |

**If 3–5 engineers:** after B0, parallelize **A15 ‖ B1 ‖ B2a ‖ B2b ‖ B3 ‖ B4 ‖ B5**, then **B6 ‖ B7**, then B8+. Solo calendar above still defines the **minimum** pilot critical path: **B0 → (A15 + B1–B7)**.

Rough solo to pilot gate: **~2.5–3.5 weeks** (W0–W2). Post-pilot B8–B12: **~1–1.5 weeks**.

### 4.2 Blast-radius sizing (before / with Critical–High PRs)

Each Critical/High PR description must include a one-liner filled from a read-only query (placeholders until run):

| CR | Sizing query (sketch) | Fill before merge |
|----|----------------------|-------------------|
| **120** | Count SOs with `converted_invoice_id` set **and** a completed DC linked, or &gt;1 SALE movement for same SO lines | `N companies / N SOs dual-fulfilled` |
| **144** | Movements whose `unit_cost` differs from layer/stamp audit if available; or all H9 price-amend PIs since date | `N companies / N moves restamped` |
| **157** | Companies with tagged 2300/1250 ≠ 0 and soft-close attempted / books health unhealthy | `N companies blocked from close` |
| **145** | Sum outstanding of `is_opening_balance=True` COMPLETED invoices included in aging today | `N companies / ₹X inflated AR+AP` |
| **156** | Soft-closed GST periods created same day as first Complete | `N race-susceptible periods` |
| Others | “Pilot sample / staging only” OK if no prod yet | Note “pre-production: N/A” |

---

## 5. Phase 0 — Launch blockers (detail)

### B1 — Double fulfillment + append-only + **data remediation** `[ ]`

| CR | Sev | Fix direction | Test |
|----|-----|---------------|------|
| **120** | C | Reject challan convert/create/update/complete when `order.converted_invoice_id` set; reject DC→invoice if SO linked to a different invoice; optional fulfillment mutex field | `test_cr120_so_invoice_then_challan_blocked`; single SALE qty |
| **144** | C | Use `StockMovement.stamp_cost(...)` only; **mandatory** CI guard forbidding `StockMovement.objects*.update(unit_cost=` outside `stamp_cost` | `test_cr144_price_amend_uses_stamp_cost`; CI grep job |

#### 5.1 Data remediation (first-class — not just Revert column)

| Step | Deliverable | Acceptance |
|------|-------------|------------|
| D1 | **Detection SQL/management command** — list company_id, SO id, invoice ids, challan ids, SALE movement ids for dual-fulfillment | Runs `--dry-run`; prints counts |
| D2 | **Heal script** — compensating stock/AR strategy agreed with Product (e.g. void duplicate challan stock via compensating ADJ + note; or cancel duplicate draft). Never silent delete of movements | Dry-run then apply per company |
| D3 | **CR-144 audit** — find layers/moves restamped via raw update; re-stamp via `stamp_cost` under lock or document “cost trusted” | 0 moves still needing raw update |
| D4 | Post-heal: **0 SOs** matching D1 detector; **0** raw `unit_cost` updates in codebase (CI) | B1 merge checklist |

#### 5.1b B1 revert runbook

1. `git revert` B1 merge commit(s).  
2. Re-enable detector; expect dual-fulfillment may recur — **do not** re-run heal that assumes fixed code.  
3. Confirm CI guard removed or still fails red if bypass reintroduced.  
4. Vulnerability window: dual-convert + raw update possible again until re-merge.

**Cross-closes:** (none prior for 120/144 — new).

### B2a — Books health predicates `[ ]`

| CR | Sev | Fix direction | Test |
|----|-----|---------------|------|
| **157** | C | Control = 1200↔tagged-1200 / 2100↔tagged-2100 only; docs↔GL uses netted advances separately. Cross-closes **CR-105**. | `test_cr157_*` + close succeeds with advance |
| **158** | H | JE “done” only if `lines` exist (health + FY_CLOSE). Cross-closes **CR-103** residual. | `test_cr158_*` |

#### 5.2 B2a revert runbook

1. Revert B2a.  
2. Re-run books health on a company with advances — expect possible false `AR_CONTROL_MISMATCH` again.  
3. Do not soft-close production periods until re-merge if false blockers were the only issue.

**Production impact line:** fill §4.2 CR-157 before merge.

### B2b — GST soft-close TOCTOU `[ ]`

| CR | Sev | Fix direction | Test |
|----|-----|---------------|------|
| **156** | H | `get_or_create` + `select_for_update` in assert; Journal `post` outer atomic. Cross-closes **CR-104**. | Postgres concurrent soft_close + Complete |

**Depends:** B0 only (not B2a). **B7 depends on B2a**, not B2b.

### B3 — POS durable resume `[ ]`

| CR | Sev | Fix direction | Test |
|----|-----|---------------|------|
| **106** | H | Finish-payment CTA without cart; reuse gesture key. Cross-closes **CR-091**. | `pos_reload_mid_settlement_resumes_receipt_without_cart` |
| **108** | H | Persist UPI pending like cash | `pos_upi_reload_mid_settlement_resumes_confirm` |
| **119** | M | Block new cart sale while settlement pending | `pos_blocks_new_sale_while_settlement_pending` |

**Twin:** N/A — POS-only.

### B4 — Purchase notes = Sales integrity `[ ]`

(Unchanged intent — CR-129, CR-130.) **Cross-closes:** none prior numbers; twins CR-017/018/026/096 patterns. **Name in PR:** `Twins Sales notes gates`.

### B5 — Serial + openings + recurring `[ ]`

| CR | Notes |
|----|-------|
| **142** | Cross-closes **CR-099** |
| **145** | Cross-closes **CR-065** residual; fill ₹X blast §4.2 |
| **121** | Cross-closes **CR-015** residual; migration for `last_error` if persisted |

---

## 6. Phase 1 — Remaining Highs

### B6 — POS cess + alt-unit return + offline count `[ ]`

CR-110, 131, 143. **Twin:** 110 N/A POS; 131 y Purchase↔Sales units; 143 N/A stock offline.

### B7 — Dual ledger + span + close `[ ]`

| CR | Fix (locked) | Cross-closes |
|----|--------------|--------------|
| **146** | Document basis for party ledger when dashboard is docs | CR-060/101 residual |
| **149** | Both bounds / default `date_to=today` + ≤366d | CR-074 residual |
| **159** | Block close if `|docs−GL| > DOCS_GL_CLOSE_TOLERANCE` after CR-157 netting | CR-082 |

**PR body must name:** `Cross-closes: CR-060, CR-101, CR-074, CR-082`.

---

## 7. Phase 2 — POS hygiene; checkout separate

### B8 — Required Mediums only `[ ]`

CR-109, 111, 112, 113, 114, 115 (doc). **Does not include CR-107 or CR-119 ownership.**

Optional extra vitest (not CR ownership): receipt-fail→retry single complete covering B3 behavior.

### B8-POS — Optional atomic checkout `[ ]`

CR-107 only. **Depends:** Product §0 sign-off + B3. Feature flag default off for pilot.

---

## 8–10. Phases 3–6

(B9–B12 content unchanged in intent; highlights below.)

- **B9:** migrations for CR-132; cross-close CR-038, CR-041; CR-124 cross-closes CR-017/096 residual.  
- **B10:** CR-138/140/141 → CR-054/056/059.  
- **B11:** **sole owner** of `test_b1_034_*` expectation flip for CR-160; cross-closes CR-085, CR-102 (via 147).  
- **B12:** CR-153; Medium-doc 125/139; Deferred 116; JE party tags CR-161 (migration).

---

## 11. Per-CR checklist (all 57)

### Critical
- [ ] **CR-120** B1 (+ data remediation D1–D4)
- [ ] **CR-144** B1 (+ CI guard mandatory)
- [ ] **CR-157** B2a

### High
- [ ] **CR-106** B3 · **CR-108** B3 · **CR-110** B6 · **CR-121** B5  
- [ ] **CR-129** B4 · **CR-130** B4 · **CR-131** B6 · **CR-142** B5 · **CR-143** B6  
- [ ] **CR-145** B5 · **CR-146** B7 · **CR-149** B7 · **CR-156** B2b · **CR-158** B2a · **CR-159** B7  
- [ ] **CR-107** B8-POS *(post-pilot)*

### Medium
- [ ] **CR-109**, **111–115** B8 · **CR-119** B3 *(only)*  
- [ ] **CR-122–124**, **126**, **132–135**, **137** B9  
- [ ] **CR-138**, **140**, **141** B10  
- [ ] **CR-147**, **148**, **150–152**, **154**, **155**, **160** B11  
- [ ] **CR-161** B12 · **CR-125** B12 doc · **CR-139** B12 doc  

### Low
- [ ] **CR-116** Deferred B12 · **117**, **118**, **127**, **128**, **136**, **153**, **162** B12  

### A15
- [ ] A15-V · A15-A if needed · A15-X cross-links **and** matching B-PR scope notes  

---

## 12. File-level map

*(Unchanged — sales/purchases/POS/stock/reporting/accounting/idempotency/payments/imports as in rev-a.)*

---

## 13. Test plan matrix (Critical / High)

| CR | Backend | FE vitest | Postgres |
|----|---------|-----------|----------|
| 120, 144, 157, 158 | yes | — | 120 optional |
| 156 | yes | — | **required** |
| 106, 108, 119 | — | **required** | — |
| 129, 130 | yes | smoke | — |
| 142, 145, 121 | yes | — | — |
| 110, 143 | — | **required** | — |
| 131, 146, 149, 159 | yes | optional | — |
| 107 | yes+FE | yes | — |

---

## 14. Cross-close map

| This wave | Prior | Close in PR *(must name in PR body)* |
|-----------|-------|--------------------------------------|
| 106, 119 | 091, 001 residual | **B3** |
| 107 | 002 | **B8-POS** |
| 115, 116, 125, 139 | 008, 011, 022, 055 | **B8** / **B12** |
| 121 | 015 residual | **B5** |
| 124 | 017 / 096 residual | **B9** |
| 131 | 045 | **B6** |
| 132 | 038 | **B9** |
| 135, 136 | 047 | **B9** / **B12** |
| 137 | 041 | **B9** |
| 138, 140, 141 | 054, 056, 059 | **B10** |
| 142 | 099 | **B5** |
| 145 | 065 residual | **B5** |
| 146, 159 | 060, 101, 082 | **B7** |
| 147 | 102 | **B11** |
| 149, 150, 155 | 074 | **B7** / **B11** |
| 156 | 104 | **B2b** |
| 157 | 105 | **B2a** |
| 158 | 103 residual | **B2a** |
| 160 | 085 | **B11** |
| 162 | 089 | **B12** |

---

## 15. Success criteria

**Pilot-ready:**

1. B0 money-path **0** failures; only Bucket C xfails with tickets remain.  
2. A15-V green (**CR-094** especially); A15-A done or N/A.  
3. All 3 Criticals FIXED including **data remediation acceptance** (CR-120/144).  
4. Phase 0–1 Highs FIXED (B1–B7, B2a/b). CR-107 may stay open.  
5. POS reload finishes cash/UPI; no second complete while pending.  
6. Period close works with advances; empty JE cannot hide missing posting.  
7. Purchase CN/DN integrity; AR/AP exclude openings; ledger basis = dashboard.  
8. Vitest + pytest baselines on **CI Python** tip SHA recorded.  
9. No orphan CR-090…162 without owner PR.  
10. Skipped-test audit complete (§1.5).

**Do not use** “failure count ≤ 25” as a gate.

**GA / post-pilot:** B8, B8-POS (if signed), B9–B12.

---

## 16. Tracker

| PR | Status | Merged | Notes |
|----|--------|--------|-------|
| B0 | [ ] | | Baseline 3.14 + vitest + A/B + skips |
| A15 | [ ] | | After B0; ‖ Phase 0 |
| B1 | [ ] | | 120, 144 + heal |
| B2a | [ ] | | 157, 158 |
| B2b | [ ] | | 156 |
| B3 | [ ] | | 106, 108, 119 |
| B4 | [ ] | | 129, 130 |
| B5 | [ ] | | 142, 145, 121 |
| B6 | [ ] | | 110, 131, 143 |
| B7 | [ ] | | 146, 149, 159 (after B2a) |
| B8 | [ ] | | POS Mediums |
| B8-POS | [ ] | | 107 optional |
| B9–B12 | [ ] | | Post-pilot |

---

## 17. Risk / CI / rollback (summary)

| Control | Requirement |
|---------|-------------|
| CR-144 CI | Fail CI if `StockMovement` queryset `.update(` sets `unit_cost` outside `stamp_cost` |
| CR-120 CI | Test (or lint) that challan paths reject invoiced SO |
| Findings CI | Prefer: PR mentioning `CR-NNN` → both registers show FIXED for that ID |
| Critical revert | Use §5.1 / §5.2 runbooks — not one-line “Revert BE” |
| Nightly | Detector jobs for dual-fulfillment while pilot writes continue (§0 Pilot data) |

---

*End of plan rev 2026-09-07b. Findings IDs permanent in [`FUNCTIONAL_CODE_REVIEW_FINDINGS_2026-09-07.md`](./FUNCTIONAL_CODE_REVIEW_FINDINGS_2026-09-07.md).*
