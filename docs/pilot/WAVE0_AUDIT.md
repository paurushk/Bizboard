# Phase 0 — Wave 0 Audit

**Date:** 2026-08-01  
**Branch:** `wip/phase0`  
**Schedule:** Solo 7–8 weeks (locked)

## Suite results

| Suite | Result | Notes |
|-------|--------|-------|
| Frontend vitest | **49 passed** (12 files) | `e2e-golden` excluded from vitest |
| Frontend eslint | 0 errors / 4 warnings | react-hooks / refresh warnings only |
| Backend pytest (targeted Phase 0) | **112 passed, 2 skipped** | postgres race tests skipped on SQLite |
| Golden e2e | Manual / `npm run test:e2e:golden` | Requires migrated backend |

## Execution progress (2026-08-01)

| Wave | Status |
|------|--------|
| 0 Audit | Done — this file |
| 1 Security | Done — OTP hide, refresh logout, media/tenant tests, alloc delete |
| 2 Money/PDF | Done — PDF discount, F11 asserts, bounds, H9-A BE, concurrency tests |
| 3 UX | Done — useBillingSaveFeedback, canExport, settings/HSN |
| 4–5 Ops | Done — PDF 409, ENV_CHECKLIST, RUNBOOKS rollback, ledger N+1 noted |
| 6 Go scaffolding | Done — fixtures command, H9/ONBOARDING/SLA/GO_NO_GO docs; **live CA letter + signed UAT still human gates** |

## Pull-forward verification

| Bug | Tree state | Action |
|-----|------------|--------|
| BUG-204 | PDF reads `invoice_discount_mode` | Add automated test (P0-204b) |
| BUG-601/730 | Dashboard renders aging | Verify field names; keep |
| BUG-612 | FE hides export without `canExport` | Confirm BE enforces too |
| BUG-628 | Login shows `Dev OTP` unconditionally | Fix P0-108 |
| BUG-205 | Charges untaxed | Pilot: label non-taxable (P0-209) |

## Critical + High mapping (P0-W0-02)

| Bug | Sev | Ticket / disposition |
|-----|-----|----------------------|
| BUG-102 | Crit | P0-108 |
| BUG-108 | Crit | P0-107 |
| BUG-109 | Crit | P0-102 (WIP verify) |
| BUG-222 | Crit | P0-201 |
| BUG-500 | Crit | P0-301 / P0-311 |
| BUG-501 | Crit | P0-301 / P0-311 |
| BUG-502 | Crit | P0-205 |
| BUG-506 | Crit | P0-206 / H9-A |
| BUG-521 | Crit | P0-306 |
| BUG-523 | Crit | P0-304 |
| BUG-531 | Crit | P0-305 |
| BUG-701 | Crit | P0-102 |
| BUG-703 | Crit | P0-101 |
| BUG-101 | High | P0-104 |
| BUG-110 | High | P0-103 |
| BUG-203 | High | P0-204 |
| BUG-204 | High | P0-204b |
| BUG-205 | High | P0-209 |
| BUG-206 | High | P0-W1 follow (POS gate tax_enabled) — ticket **P0-112** |
| BUG-208 | High | P0-205 |
| BUG-210 | High | P0-210 |
| BUG-211 | High | P0-210 |
| BUG-220 | High | H9-A / Phase 1 CN — **WAIVED** full CN; H9-A covers pilot |
| BUG-224 | High | FIXED (verify) |
| BUG-301 | High | P0-510 |
| BUG-308 | High | P0-202 |
| BUG-309 | High | P0-201 |
| BUG-310 | High | P0-110b |
| BUG-311 | High | P0-110b |
| BUG-402 | High | P0-111 accept-risk |
| BUG-407 | High | P0-111 |
| BUG-504 | High | P0-204 / P0-311 |
| BUG-507 | High | P0-302 |
| BUG-508 | High | P0-303 |
| BUG-519 | High | P0-402 follow |
| BUG-520 | High | P0-207 |
| BUG-525 | High | P0-304 |
| BUG-532 | High | P0-305 |
| BUG-539 | High | P0-312 |
| BUG-601 | High | P0-313 (partial Done in WIP) |
| BUG-602 | High | P0-313 |
| BUG-606 | High | P0-306 |
| BUG-607 | High | P0-306 |
| BUG-608 | High | P0-306 |
| BUG-609 | High | P0-306 |
| BUG-612 | High | P0-313 |
| BUG-616 | High | P0-313 |
| BUG-617 | High | P0-314 |
| BUG-618 | High | P0-314 |
| BUG-621 | High | P0-315 |
| BUG-628 | High | P0-108 |
| BUG-635 | High | P0-312 |
| BUG-700 | High | P0-109 |
| BUG-702 | High | P0-103 |
| BUG-704 | High | P0-104 |
| BUG-705 | High | P0-105 / ops — **WAIVED** local `.env` gitignored |
| BUG-725 | High | P0-621 |
| Remaining Highs in INDEX | High | Mapped in Wave 0 continuation to nearest C/B ticket or **WAIVED (pilot)** with PM note in go meeting |

## Scoreboard snapshot (Must) — refreshed 2026-08-02

| DoD | Status | Notes |
|-----|--------|-------|
| A1–A11 | **Code Done** | Sign-off still open (A11 ENV accept-risk blank) |
| B1–B11 | **Code Done** | BUG-204 PDF mode fixed + tests; B11 charges non-taxable (CA F12 initials blank) |
| C1–C12 | **Code Done** | P0-311 DocumentEditorShell extracted 2026-08-02; remaining list `asList` cliffs fixed (`fetchAllPages`) |
| D1–D5 | **Code Done** | SMTP/ops spot-test on staging still human |
| E1–E10 | **Docs Ready / Ops Open** | ENV_CHECKLIST unsigned; TLS/backup/uptime need host execution |
| F1–F12 | **Code Done / CA Open** | Automated PDF asserts green; F9 letter + F12 initials blank |
| G1–G12 | **Open** | UAT matrix blank; golden e2e = `npm run test:e2e:golden` (manual vs real API) |
| H1–H9 | **Docs Ready / Sign-off Open** | H9-A implemented; signature tables blank |

### Critical/High disposition (code-verified 2026-08-02)

Mapped Crit/High in the table above are **FIXED in tree** except: BUG-220 full CN **WAIVED for Phase 0** (H9-A); BUG-705 **WAIVED**; human gates F9/G*/E*/H* signatures. P0-311 structural extraction completed (shell + NumericField + line helpers); twin pages still hold page-specific save mutations by design.

## Exit

Wave 0 audit artifact committed. Pull-forward implementation proceeds next.
**2026-08-02:** Engineering closeout advanced (P0-311, pagination). Go still blocked on CA/UAT/ENV human signatures — see `GO_NO_GO.md`.

## Wave 4–5 ops notes (2026-08-02)

| Ticket | Status | Notes |
|--------|--------|-------|
| P0-404 | Done | PDF download returns **409** + enqueues when `NONE`/`FAILED`; never sync `generate_invoice_pdf`. |
| P0-501 | Doc | TLS hard gate in `ENV_CHECKLIST.md`. |
| P0-502 | Doc | worker/web/nginx healthcheck **skipped** — see RUNBOOKS. |
| P0-506 / E10 / A11 | Done | `docs/pilot/ENV_CHECKLIST.md` (signer fields + JWT localStorage accept-risk). |
| P0-508 / H1 | Done | RUNBOOKS: deploy rollback decision tree, on-call placeholder, PDF 409. |
| P0-510 / BUG-301 | Done | Ledger list bulk aggregation already in `ledgers/services.py`; PERFORMANCE_REPORT reconciled. |

