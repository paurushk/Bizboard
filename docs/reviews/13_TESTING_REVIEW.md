# Testing Review

## Wave 22 (2026-08-06)

BB-000580 presence-only theater (758); no Android CI (748); OpenAPI types ungated (750).

## Wave 21 (2026-08-05)

Missing: DELETE receipt GL, CDNUR split, cross-tenant BOM PK, prod invite without password, concurrent pay-run complete.

## Wave 20 (2026-08-05)

Missing: paid-invoice CN, secondary-GSTIN IRP payload, challan e-way distance, path-traversal upload.

## Wave 19 missed (2026-08-05)

Prod DEBUG=0 auth e2e missing (BB-000602); books-on complete untested (BB-000599); FIFO cancel untested (BB-000601).

## Wave 19 (2026-08-05)

`test_wave19.py` and `_wave19_assert_gates.py` are presence checks, not residual P0 probes (BB-000576, BB-000558). Mock flags hide ERP routes (BB-000597).


**Date:** 2026-08-02 · **Coverage assessment: 6.0 / 10**

## Backend

- Strong: tax calc, tenant isolation, stock concurrency (PG), payments, phase1–7 modules growing.
- Weak: adversarial webhooks, real GSP, composition enforcement, H9+period, return→GSTR/GL, multi-company (N/A).

## Frontend

- Strong: money/tax/permissions/client unit tests.
- Weak: ~12 test files vs ~90 pages; few component tests for invoice Complete.

## E2E

- Smoke thin; golden path present in CI.
- UAT matrix ≥5 companies **unsigned** (human).

## Gaps → register

| Topic | Priority |
|-------|----------|
| Webhook forgery tests | P1 |
| FE↔BE golden money fixtures in CI | P1 |
| Expand Playwright G1–G12 | P1 |
| Coverage gate `--cov-fail-under` | P2 |
| Load test | P1 |
| A11y axe | P2 |
| Pen-test | P1 |

## Stale docs

`TEST_REPORT.md` counts (120/26) outdated — BUG-729. Prefer live `pytest` / `npm test`.

## Score: 6.0 / 10


## Wave 8 (2026-08-03)

Light e2e job without API (BB-000221); missing adversarial payment webhook suite for BB-000196–198; process failure BB-000254 (Resolved without re-verify).

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.
