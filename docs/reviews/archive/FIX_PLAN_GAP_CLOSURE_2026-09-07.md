# Gap-Closure Fix Plan — Items Without a Prior Implementation Plan

**Date:** 2026-09-07 · **Rev:** b (aligned with fix-plan review A–F)  
**Companion:** [`FIX_PLAN_FUNCTIONAL_2026-09-07.md`](./FIX_PLAN_FUNCTIONAL_2026-09-07.md) (**rev 2026-09-07b**)

This file owns work that was missing from the first B-wave draft. The main plan is authoritative for sequencing, pilot gate, calendars, and PR splits (**B2a/B2b**, **B8-POS**, **B0 hard Depends**).

---

## 0. Completeness audit (what was missing)

| Gap | Why it lacked a plan | Resolution |
|-----|----------------------|------------|
| **CR-153** | Dropped from B checklist | **§1** → B12 |
| **CR-090…CR-105** | Promised A15 never written | **§2** → **A15** (Depends **B0**) |
| **25 pytest failures** | B0 was one-line | **§3** → B0 buckets; money-path file list in main plan §1.3 |
| **Prior PARTIAL CR-001…089** | Cross-refs only | **§4** + main §14 (PR must **name** each prior CR) |
| Dirty-tree baseline / vitest / migrations / data heal / blast radius | Scope holes in main plan | Fixed in main plan §1, §4.2, §5.1 |

**Standing rule:** Every open CR-090…162 appears in exactly one of: FIXED-verified, B/A15 PR, or product Deferred/doc.

---

## 1. CR-153 — Dashboard omits `payables_aging`

| Field | Detail |
|-------|--------|
| **ID** | **CR-153** (RPT-009) |
| **Severity** | Low |
| **PR** | **B12** |
| **Fix** | Include `payables_aging` in dashboard JSON + FE chart (default: ship buckets) |
| **Test** | `test_dashboard_json_payables_aging_sums_to_payables` |

**Checklist:** [ ] CR-153 FIXED in B12

---

## 2. PR A15 — CR-090…CR-105

**Depends:** **B0** (hard). **Sequence:** after B0, **parallel with B1–B5** (solo: per main §4.1).

### 2.1 Disposition

| ID | Plan action | Closes in |
|----|-------------|-----------|
| **CR-090** | A15-V vitest; A15-A if red | A15 |
| **CR-091** | Delegate | **B3** (CR-106/119) — B3 PR must name CR-091 |
| **CR-092** | Delegate | **B12** (CR-118) |
| **CR-093…098, 100–101** | A15-V (094 pilot-critical) | A15 |
| **CR-099** | Delegate | **B5** (CR-142) |
| **CR-102** | Delegate | **B11** (CR-147) |
| **CR-103** residual | Delegate health/FY | **B2a** (CR-158); backfill verify in A15-V |
| **CR-104** | Delegate | **B2b** (CR-156) |
| **CR-105** | Delegate | **B2a** (CR-157) |
| **CR-096** auto-return residual | Delegate | **B9** (CR-124) |
| **CR-101** dual-ledger residual | Delegate | **B7** (CR-146/159) — B7 must name CR-101 |

### 2.2 Packages

- **A15-V** — verify claimed FIXED; mark registers.
- **A15-A** — fix any red (esp. CR-094).
- **A15-X** — docs cross-link **plus** verification that target B-PR scope notes name the prior CR (main standing checklist #5). If B7 never names CR-101, A15-X is incomplete.

---

## 3. B0 detailed — 25 pytest failures

**Merge gate Python:** **3.14** (CI). Re-baseline on a **clean tip SHA** (main plan §1.2); do not treat dirty-tree 3.12.11 “25 failed” as the gate.

**Money-path:** file list in main plan §1.3 — must be **0** failures after Buckets A+B.

### 3.1 Bucket A — stale tests (update test)

| # | Test | Fix direction | Owner |
|---|------|---------------|-------|
| A1–A2 | SO reservation release-on-convert | Assert hold-until-complete (CR-020) | **B0** |
| A3–A5 | CN confirm / period | Pass confirm flags; align gate order | **B0** |
| A6 | Serial qty-amend message | Assert CR-024 message | **B0** |
| A7 | `test_b1_034_*` | **Triage only** → owned by **B11**/CR-160. **B0 must not change expectations** | **B0 triage → B11** |
| A8 | `test_csv_export` 400 | Supply both dates within 366d | **B0** |
| A9–A11 | CN PDF / closed period / cash book | Fixture or assert new contract | **B0** |

### 3.2 Bucket B — code regressions

GST suite (6) + GSTR notes (2) + CN e-invoice prepare/IRN as applicable → **B0** or **B0-G**.

### 3.3 Bucket C — GSP / honesty backlog

`test_gsp_live_*`, `test_bb_000591_*`, sprint_e QR — ticket + optional xfail; **not** money-path.

### 3.4 B0 checklist

- [ ] Clean tip SHA + pytest 3.14 baseline file
- [ ] Vitest baseline file
- [ ] Buckets A+B landed; money-path 0
- [ ] A7 triaged to B11 (no expectation flip in B0)
- [ ] Bucket C ticketed
- [ ] Skipped-test audit (main §1.5)

---

## 4. Prior PARTIAL residual matrix

Use main plan §14. **Rule:** every B-PR that closes a residual must list `Cross-closes: CR-…` in the PR body.

| Prior | Owner PR |
|-------|----------|
| 002 | B8-POS |
| 006 | B8 (114) |
| 007 | B6/B8 (110/111); A15-V 090 |
| 008 / 011 / 022 / 055 | B8/B12 doc-defer |
| 015 | B5 (121) |
| 017 / 026 | A15-V 096 + B9 (124) |
| 038 / 041 / 045 / 047 | B9/B6/B12 |
| 054 / 056 / 059 | B10 |
| 065 / 074 / 082 / 085 / 089 | B5/B7/B11/B12 |
| 043 | Product accepted — doc only |

---

## 5. PR tracker (gap wave)

| PR | Depends | Status |
|----|---------|--------|
| B0 | — | [ ] |
| B0-G | B0 optional split | [ ] |
| A15 | **B0** | [ ] |
| B12 + CR-153 | as main | [ ] |

---

## 6. Pilot gate (gap-aware)

Matches **main plan header “Pilot gate”**: B0 A+B · A15-V · B1–B7 (incl. B2a/B2b) · data remediation · baselines on CI Python · skip audit.

---

*End rev b.*
