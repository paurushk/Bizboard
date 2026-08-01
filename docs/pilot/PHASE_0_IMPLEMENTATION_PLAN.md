# Phase 0 — Implementation Plan (Pilot Hardening)

**Status:** Ready to execute (rev 3 — High pull-forward + correction path + PDF assert)  
**Goal:** Controlled paid pilot (20–50 businesses)  
**Canonical DoD:** [`PHASE_0_DOD.md`](./PHASE_0_DOD.md)  
**Also:** `PRODUCTION_READINESS.md`, `bugs/INDEX.md`, `docs/ca/CA_SIGN_OFF_CHECKLIST.md`, `docs/pilot/UAT_CHECKLIST.md`, `docs/pilot/RUNBOOKS.md`

---

## 0. Day-0 blockers + headcount

### Headcount (operative)

| Field | Value |
|-------|-------|
| **Headcount** | **1–2 (default)** — blank PM override not set |
| **Schedule locked** | **§4.3 Solo (~7–8 weeks)** |
| **PM note** | Solo is the operative plan until PM writes a higher headcount here. Do not assume 4-week team parallelism. |

### Day-0 tickets

| Ticket | Work | Done when |
|--------|------|-----------|
| **P0-000** | `PHASE_0_DOD.md` on branch | Tracked in git |
| **P0-W0-00** | `git checkout -b wip/phase0` + commit all Phase 0 WIP (never leave 100+ dirty files on `main`) | Remote/local branch exists; `main` clean of this WIP |
| **P0-W0-00b** | Carve into **4–6 reviewable PRs merged to unprotected `main`** (preferred), **or** land slices on `wip/phase0` then one **explicit accepted integration merge** to `main` (document which). Do **not** pretend slice PRs exist if the only land is one megamerge without saying so. Protect `main` only after integration (P0-503) | Strategy written + executed |

**Preferred integration path:** slice PRs → `main` (unprotected) → then enable protection.  
**Accepted alternate:** slices → `wip/phase0` → single integration commit/PR to `main`, labeled as such in the merge message.

---

## 1. Executive summary

Phase 0 hardens the MVP for pilot. It does not add full CN/GSTR/GL surface — except a **named H9 correction path** if chosen.

**Exit:** [`PHASE_0_DOD.md`](./PHASE_0_DOD.md) — including **Go SHA == UAT SHA** (or re-smoke).

### 1.1 Baseline vs tree (verified)

| Area | Actual | Ticket implication |
|------|--------|-------------------|
| Media | nginx `internal`; BE uses `FileResponse` (no X-Accel) | P0-101: choose FileResponse vs build X-Accel |
| Locks | `select_for_update` present | P0-201/202 = **tests only** (budget for flaky concurrent pytest) |
| Tax math CI | Fixture loaded BE+FE; **6 cases**, CA needs **8** | P0-203 expand fixture |
| PDF discount | **BUG-204:** PDF ignores `invoice_discount_mode` | **P0-204b before PDF freeze** (CA F6 blocker) |
| OTP | BE fail-closed; **FE may still show debug OTP (BUG-628)** | P0-108 / P0-403 |
| canExport / aging | Flags/aging not enforced/rendered as UAT claims | **P0-313** (C12) |
| Additional charges GST | Never taxed (BUG-205) | **B11 / F12** CA scope decision |
| Completed edits | Lines still writable | B6 + **H9** paid-correction decision |
| PDF download | Sync generate-on-demand hang | P0-404 |
| Compose health | worker/web/nginx lack healthchecks | P0-502 document skip vs cheap check |

### 1.2 Pull-forward (do not wait for Wave 0 discovery)

These break **already-written Must** DoD rows. Ticket them **now**; fix before the gates they block.

| Bug | DoD | Ticket | Gate blocked |
|-----|-----|--------|--------------|
| **BUG-204** | B4, F6, B3 | **P0-204b** | Wave 2 PDF freeze / CA samples |
| **BUG-612** | G11, C12 | **P0-313** | UAT export rows |
| **BUG-601 / 602** | C12, UAT smoke | **P0-313** | UAT aging rows |
| **BUG-628** | A8, D3 | **P0-108** / **P0-403** | Pilot OTP honesty |
| **BUG-205** | B11, F12 | **P0-209** | CA scope / under-charging risk |

**Second tier (ticketed in Wave 1–2, not deferred to vague Wave 0 only):**

| Bug | DoD | Ticket |
|-----|-----|--------|
| BUG-310 / 311 | B9 | P0-110b (or extend P0-110) |
| BUG-402 / 407 | A11 | P0-111 |
| BUG-617 / 618 | C8 Must, G1 | P0-314 |
| BUG-210 / 211 | B10 | P0-210 |
| BUG-621 | C11 | P0-315 |
| BUG-700 | A9 | P0-109 |
| BUG-301 | E8 | P0-510 |

---

## 2. Principles

1. DoD is a file.  
2. Verify before celebrate; WIP ≠ Done.  
3. Freeze WIP day-0.  
4. Solo schedule until headcount raised.  
5. Pull-forward Must-breakers before PDF freeze.  
6. P0-311 before twin Sales/Purchases fixes.  
7. Math parity ≠ PDF parity (F11).  
8. Go ships the UAT’d SHA.  
9. Named H9 correction path — no silent “use Return to fix price.”  
10. Small PRs with bug IDs; Critical/High mapped.

---

## 3. Team & ownership

Solo default: one Eng owns all waves; PM owns headcount, H9, waivers, go/no-go; CA owns F/B11; Ops owns E1/E4/E5 when available.

---

## 4. Timeline

### 4.1 Quiet gate

**Must:** zero open Criticals at Go **and** no *new* Critical after UAT sign-off.  
**Should stretch:** 14-day zero-Critical window if calendar allows.  
**Must:** Go build SHA == UAT build SHA, or 12-row smoke re-run on Go SHA.

### 4.2 Team schedule (~5–6 weeks) — only if headcount ≥ 3 written in §0

```text
Day 0     P0-000, P0-W0-00, P0-W0-00b
Week 1    Wave 0 + Wave 1 (+ P0-108/628, P0-111)
Week 2    Wave 2: P0-204b FIRST → PDF freeze → CA samples; races; H9 decision
Week 3    Wave 3 (P0-311 first) + P0-313/314/315
Week 4    Wave 4 PDF download path; Wave 5 start
Week 5–6  Wave 5–6 UAT/CA/go; SHA lock
```

### 4.3 Solo schedule (~7–8 weeks) — **OPERATIVE DEFAULT**

```text
Day 0     Branch freeze + DoD commit
Week 1    Wave 0 mapping + Wave 1 security (incl. 628, A11)
Week 2    Finish Wave 1; start Wave 2; **P0-204b**
Week 3    Wave 2 complete; PDF freeze; CA samples; H9 decision recorded
Week 4–5  Wave 3 (P0-311 → C*; P0-313 export/aging)
Week 6    Wave 4 + Wave 5
Week 7–8  Wave 6 UAT/CA/go; SHA lock; do not parallelize Wave 3/4
```

---

## 5. Wave 0 — Audit + full Critical/High mapping

**Prerequisite:** Day-0 Done.

| ID | Task | Output |
|----|------|--------|
| P0-W0-01 | Diff branch vs INDEX | Per-bug fixed/partial/open |
| P0-W0-02 | Map **all** Critical + High → ticket or waiver (incl. the ~25 Highs not previously cited) | §18.1 appendix |
| P0-W0-03…08 | Suites, media, invite, concurrent smokes | Logs |
| P0-W0-09 | Scoreboard fill | §18 |
| P0-W0-10 | pytest `postgres` marker plan | Feeds P0-208 |

Wave 0 DoD: mapping complete; open Criticals in Wave 1–2; pull-forwards already ticketed in §1.2.

---

## 6. Wave 1 — Security & tenancy (DoD A)

| Ticket | DoD | Work | Bugs |
|--------|-----|------|------|
| **P0-101** | A1 | FileResponse OK for pilot **or** X-Accel; tests | BUG-703 |
| **P0-102** | A2 | Verify invite + tests | BUG-109/701 |
| **P0-103** | A3 | Deterministic membership + FE recovery if 409 | BUG-110, BUG-702 |
| **P0-104** | A4 | Secrets/DEBUG fail-closed | BUG-101/704 |
| **P0-105** | A5 | dockerignore / no secrets in image | BUG-705–707 |
| **P0-106** | A6 | Throttles + lockout test | BUG-105/728 |
| **P0-107** | A7 | Duplicate phone | BUG-108 |
| **P0-108** | A8, D3 | Hide OTP UI when SMS off; **remove unconditional FE OTP debug display (BUG-628)**; docs password-only | BUG-102, BUG-628 |
| **P0-109** | A9 | Cross-tenant WRITE tests; **delete or complete assertion-free BUG-700 test** | BUG-721, BUG-700 |
| **P0-110** | A10 | Cancel blocked/reversed with allocations | BUG-722 |
| **P0-110b** | B9 | Allocation/receipt delete: permission + audit + no silent cascade | BUG-310, BUG-311 |
| **P0-111** | A11 | Document accept-risk **or** harden: token storage + logout on refresh reject | BUG-402, BUG-407 |

---

## 7. Wave 2 — Money, PDF freeze, correction path (DoD B + F)

| Ticket | DoD | Work | Bugs |
|--------|-----|------|------|
| **P0-204b** | B4, F6 | **FIRST in Wave 2:** PDF honors `invoice_discount_mode`; BEFORE_TAX math on PDF matches DB | BUG-204 |
| **P0-201** | B1 | Concurrent stock tests (Postgres) | BUG-222/309 |
| **P0-202** | B2 | Concurrent allocation tests | BUG-308 |
| **P0-203** | F10 | Expand `tax_parity_cases.json` to F1–F8 (round-off, multi-rate) | CA |
| **P0-204** | B4 | Purchases UI/API discount parity with Sales | BUG-203/504 |
| **P0-205** | B5 | Numbering Complete S+P | BUG-208/502 |
| **P0-206** | B6 | Immutability + allowlist + audit events | BUG-506 |
| **P0-206b** | H9, B6 | **Paid-invoice correction-path decision** (see §7.1) — implement chosen option | BUG-220 |
| **P0-207** | B7 | Confirm dialogs | BUG-520 |
| **P0-208** | B8 | Register pytest `postgres` marker; CI runs races | BUG-712 |
| **P0-209** | B11, F12 | CA+PM: GST on additional charges **or** scoped out with checklist row | BUG-205 |
| **P0-210** | B10 | Bounds validation gst_rate / unit_price / discount / additional_charges | BUG-210/211 |
| **P0-211** | B3, F11 | **PDF parity automation:** render → extract totals → assert vs DB for F1, F3, F6 | BUG-204 class |

### 7.1 Immutability + paid correction (H9) — decide before go-live

**Problem:** Option A + A10 (no cancel when allocated) + Return-as-price-fix **distorts stock** (breaks G3/G4). Full Credit Notes are Phase 1 (BUG-220). Paid + wrong price has no clean path unless H9 chooses one:

| Option | Meaning | When |
|--------|---------|------|
| **H9-A** | **Owner amend (narrow):** price/discount/additional_charges only; confirm modal; mandatory `AuditEvent`; Staff blocked; stock unchanged | Prefer if pilots will bill daily |
| **H9-B** | **Minimal credit-note-as-adjustment** (value-only, no stock) for pilot — scoped Phase 0 exception | If CA wants document trail |
| **H9-C** | **Accept hole:** onboarding + support state “paid invoices cannot change; issue manual credit outside system / wait Phase 1 CN” | Only with PM+CA written accept |

**Default recommendation:** **H9-A** for pilot. Do **not** use stock Returns to fix price.

FAQ (H2) and onboarding (H3) must state the chosen option explicitly.

### 7.2 PDF template freeze

**Only after P0-204b + P0-209 decision recorded.** Then freeze layout; send CA samples; Wave 4 may fix download reliability without tax-presentation churn.

---

## 8. Wave 3 — Counter UX (DoD C)

**Mandatory order:** **P0-311 →** then C tickets (no twin-page drift).

| Ticket | DoD | Work | Bugs |
|--------|-----|------|------|
| **P0-311** | — | Shared billing primitives | BUG-518 cluster |
| **P0-301…310** | C1–C10 | As rev 2 (via shared primitives) | see DoD |
| **P0-312** | §12 | Component tests Save & New / draft vs complete | BUG-500/501/539 |
| **P0-313** | C12, G11 | Enforce `can_export` on exports; render dashboard receivables aging (and ledger aging UX if UAT requires) | BUG-612, BUG-601, BUG-602 |
| **P0-314** | C8, G1 | Company + GST settings save error handling | BUG-617, BUG-618 |
| **P0-315** | C11 | Wire HSN/GST validators into product form | BUG-621 |

Solo: ~2 weeks for Wave 3.

---

## 9. Wave 4 — Comms & PDF ops (DoD D)

| Ticket | DoD | Work | Bugs |
|--------|-----|------|------|
| **P0-401** | D1 | SMTP | — |
| **P0-402** | D2 | WhatsApp honesty | — |
| **P0-403** | D3 | Env/runbook + FE OTP debug purge (with P0-108) | BUG-102, BUG-628 |
| **P0-404** | D4 | Download must not sync-hang `generate_invoice_pdf`; Complete non-blocking | BUG-224 + download |
| **P0-405** | D5 | OpenAPI on/off | BUG-104 |

---

## 10. Wave 5 — Deploy, DPDP, perf (DoD E)

| Ticket | DoD | Work |
|--------|-----|------|
| **P0-501** | E1 | TLS hard gate (not Conditional-waivable) |
| **P0-502** | E2 | Healthchecks db/redis/api; document skip for worker/web/nginx (prefer queue-depth over flaky celery ping) |
| **P0-503** | E3 | Protect `main` after WIP integration |
| **P0-504** | E4 | Backup + restore drill |
| **P0-505** | E5 | Uptime + alerts |
| **P0-506** | E6 | ENV checklist signed |
| **P0-507** | E7 | CVE fix/waiver |
| **P0-508** | E9 | Deploy rollback: image tags; migration reverse vs restore-from-backup decision tree; account for new WIP migrations |
| **P0-509** | E10 | DPDP minimum |
| **P0-510** | E8 | Perf floor §10.1 incl. **ledger N+1 (BUG-301)** and report CSV; reconcile PERFORMANCE_REPORT |

### 10.1 Performance floor

| Metric | Bar | Seed |
|--------|-----|------|
| Invoice list API p95 | < 2s at ~5k invoices / company | **P0-620 must generate** (headroom for 20–50 biz pilot) |
| Ledger list / statement paths | No catastrophic N+1; usable under same seed | BUG-301 |
| Concurrent users | 20 concurrent billing smoke without error storm | staging |

---

## 11. Wave 6 — CA, UAT, governance (DoD F/G/H)

### 11.1 Docs

| Ticket | Work |
|--------|------|
| **P0-600** | Full G1–G12 × 5 matrix in UAT_CHECKLIST (keep SHA fields) |
| **P0-600b** | CA checklist Phase 0 + F12 additional-charges row |

### 11.2 CA

| Ticket | Work |
|--------|------|
| **P0-601** | Staging PDFs after freeze (post P0-204b) |
| **P0-602** | CA walkthrough |
| **P0-603** | Store letter |
| **P0-604** | Keep F10 + F11 green |

### 11.3 Fixtures / UAT / import (P0-620+ — not CA block)

| Ticket | Work |
|--------|------|
| **P0-620** | Pilot company fixtures + **5k-invoice perf seed** + reset docs | P0-605 formerly |
| **P0-621** | Execute UAT ×5; expand golden e2e | was P0-606 |
| **P0-622** | CSV import robustness | was P0-607 |
| **P0-623** | **SHA lock:** record UAT SHA; Go uses same SHA or re-smoke 12 rows and re-sign |

### 11.4 Support & governance

| Ticket | Work |
|--------|------|
| **P0-610** | Expand RUNBOOKS |
| **P0-611** | FAQ incl. H9 path |
| **P0-612** | Onboarding + privacy + H9 statement |
| **P0-613** | README honesty |
| **P0-614** | Metrics |
| **P0-615** | Quiet gate |
| **P0-616** | Support SLA / on-call |
| **P0-617** | Kill + graduation criteria |
| **P0-618** | H9 decision signed (points to §7.1 option) |

**Kill examples:** Critical money/tenancy >72h; CA withdraws; PDF success <95%/7d; PII incident.  
**Graduate examples:** ≥5 pilots weekly cycle OK 2 weeks; quiet gate met; PM+Eng start Phase 1 CN/GSTR.

### Go / No-Go

Hard gates: Criticals mapped; no open Critical money/tenancy; CA letter; TLS; **H9 signed**; **SHA match or re-smoke**; F11 PDF asserts green.

---

## 12. Test strategy

| Layer | Requirement |
|-------|-------------|
| Unit | F1–F8 math fixture |
| PDF assert | F11 render→extract→DB (F1/F3/F6) |
| API | Tenant R/W; races; cancel/alloc; alloc delete; bounds; BUG-700 gone |
| FE | tax/money + **save-path components** + settings error paths + OTP debug absent |
| E2E | Golden real API; SHA recorded |
| Perf | Invoice + ledger floors with P0-620 seed |
| Ops | Backup, rollback dry-run, download without broker hang |

---

## 13. PR / merge strategy

1. Day-0: `wip/phase0` freeze commit.  
2. **Preferred:** 4–6 slice PRs into unprotected `main`.  
3. **Alternate:** slices on `wip/phase0`, then **one labeled integration merge** to `main` (accepted; say so in merge message).  
4. Bug IDs in every PR; update scoreboard.  
5. P0-503 branch protection after integration.

---

## 14. Risk register

| Risk | Mitigation |
|------|------------|
| Dirty main | P0-W0-00 |
| Solo vs fantasy 4-week | §0 locks solo |
| CA F6 fail | P0-204b before freeze |
| UAT asserts false features | P0-313 |
| OTP debug in FE | P0-108/403 + BUG-628 |
| Additional charges GST | P0-209 / F12 |
| Paid invoice no correction | H9 named options |
| Parity green, PDF wrong | P0-211 / F11 |
| Go ≠ UAT build | P0-623 |
| Return-as-price-fix | Forbidden in H9-C messaging; prefer H9-A |
| Megamerge surprise | §13 explicit alternate |
| Ledger N+1 vs floor | P0-510 + P0-620 seed |

---

## 15. Non-goals

Full CN product (unless H9-B), SO/PO, challans, POS, recurring, GSTR, e-Invoice, GL, gateway, multi-WH, Tally, WA Business API, AI BI, pen-test, 10k GA load.

---

## 16. Exit checklist

- [ ] Day-0 freeze + DoD on branch  
- [ ] Headcount acknowledged (solo default)  
- [ ] A incl. A11; B incl. B9–B11; C incl. C8 Must / C11 / C12  
- [ ] P0-204b before PDF freeze; P0-211 F11  
- [ ] H9 signed; P0-623 SHA lock  
- [ ] Signatures on DoD  

---

## 17. First actions (ordered)

1. **P0-W0-00** — create `wip/phase0` and commit WIP (if not done).  
2. Confirm **solo schedule** with PM (or fill higher headcount in §0).  
3. Open tickets for **P0-204b, P0-313, P0-108/628, P0-209** immediately.  
4. Schedule H9 decision meeting (PM+Eng+CA input).  
5. P0-W0-00b slice strategy; Wave 0 mapping for remaining Highs.  
6. Book CA; plan freeze only after P0-204b.

---

## 18. Scoreboard template

| DoD ID | Ticket | Status | Bug IDs covered | Evidence | Owner |
|--------|--------|--------|-----------------|----------|-------|
| A1 | P0-101 | | BUG-703 | | |
| A2 | P0-102 | | BUG-109, BUG-701 | | |
| A3 | P0-103 | | BUG-110, BUG-702 | | |
| A4 | P0-104 | | BUG-101, BUG-704 | | |
| A5 | P0-105 | | BUG-705–707 | | |
| A6 | P0-106 | | BUG-105, BUG-728 | | |
| A7 | P0-107 | | BUG-108 | | |
| A8 | P0-108 | | BUG-102, BUG-628 | | |
| A9 | P0-109 | | BUG-721, BUG-700 | | |
| A10 | P0-110 | | BUG-722 | | |
| A11 | P0-111 | | BUG-402, BUG-407 | | |
| B1 | P0-201 | | BUG-222, BUG-309 | | |
| B2 | P0-202 | | BUG-308 | | |
| B3 | P0-211 | | BUG-204 class | | |
| B4 | P0-204, P0-204b | | BUG-203, BUG-204, BUG-504 | | |
| B5 | P0-205 | | BUG-208, BUG-502 | | |
| B6 | P0-206, P0-206b | | BUG-506, BUG-220 | | |
| B7 | P0-207 | | BUG-520 | | |
| B8 | P0-208 | | BUG-712 | | |
| B9 | P0-110b | | BUG-310, BUG-311 | | |
| B10 | P0-210 | | BUG-210, BUG-211 | | |
| B11 | P0-209 | | BUG-205 | | |
| C1–C10 | P0-301…310 | | (DoD) | | |
| C8+ | P0-314 | | BUG-617, BUG-618 | | |
| C11 | P0-315 | | BUG-621 | | |
| C12 | P0-313 | | BUG-601, BUG-602, BUG-612 | | |
| D1–D5 | P0-401…405 | | BUG-628 in D3 | | |
| E1–E10 | P0-501…510 | | BUG-301 in E8 | | |
| F1–F12 | P0-601…604, 209, 211 | | | | |
| G1–G12 | P0-600, 620–623 | | BUG-725 | | |
| H1–H9 | P0-610…618 | | | | |

### 18.1 Critical + High mapping appendix

Fill in P0-W0-02: every INDEX Critical/High → ticket or `WAIVED (PM, date, reason)`.

---

## 19. Revision history

| Rev | Date | Notes |
|-----|------|-------|
| 1 | 2026-08-01 | Initial |
| 2 | 2026-08-01 | DoD file, WIP freeze, bug mapping, baseline fixes, missing streams |
| 3 | 2026-08-01 | Solo locked; pull-forward 204/612/628/205; B9–B11, A11, C11–C12; H9 paid correction; F11 PDF assert; SHA lock; P0-620+ renumber; P0-508 fix; merge strategy clarified; BUG-110 on A3 |
