# Test execution report

**Cycle:** 2026-09-27 · **Method:** `docs/roadmap/HOLISTIC_UI_E2E_VALIDATION_PLAN_2026-09-27.md` · **Sweep:** `INVARIANTS_STRICT=1`

## What ran

From `backend/`, CPython 3.13, `python -m pytest`, `INVARIANTS_STRICT=1`:

- Fast lane: workflows, tenancy, gst, snapshots, edge, errors, matrices, personas, regression, `test_invariants_smoke.py`, `test_sprint0_security.py`, `test_no_impersonation.py`. 327 passed, 1 skipped.
- Postgres RLS: `test_rls_coverage.py` and `tests/tenancy/` against Postgres 17 on localhost:5433 with `POSTGRES_RLS_ENABLED=1`. 29 passed. No SQLite skip.
- I1–I5 in `tests/test_phase0_api_slas.py`, including barcode search P95 and a 30-read product list whose query count stays flat after warm-up.
- `test_complete_failure_then_retry_posts_stock_once`.
- `test_wf37_refunds` and `test_wf38_mdr_settlement_reconciliation`.
- G-17 through G-22, including the four page tests for the returned-invoice badge.
- `test_qos0003_large_tenant_reports.py`: 3 passed on 50,000 invoices.

Playwright, Chromium, against the e2e mock server: `a11y.spec.ts`, `role-boundaries.spec.ts` (including reload and back after a denial), and `offline-outbox-conflict.spec.ts`. The API proxy to port 8000 was refused. The mock pages still rendered.

The same keyboard, contrast, denial, and no-horizontal-scroll checks passed on the Pixel 5 project and on WebKit.

Live Django goldens, `playwright.golden.config.ts`: workshop job, route POD, project milestone, insurance desk, SaaS share and suspend, and the Hindi money-status spec. All six passed. The grant helper now sets `OTP_PEPPER` so `grant_rollout_flag` can boot when `DJANGO_ENV=development`.

## Ledger

WF-37 and WF-38 are Gated on the books path. J-TRADE-P3-FLAKYNET is Gated by the outbox conflict spec. J-SCALE-P1-REPORTS and J-CA-P6-AUDIT are Reference. Commission stays Boundary (D17): it is not a receipt and not a journal. A live gateway capture, a signed CA filing, and a staging soak were not run. Those need a vendor sandbox, a person, and a staging host.

## Scorecard

| Dimension | Mark | Evidence |
|---|---|---|
| Functional, business rules, calculations, data integrity | Gated | Fast lane 327 passed under the invariant sweep. I2 grand total is 118.00. |
| End-to-end | Gated | Six live goldens passed against Django, including Hindi `पूर्ण`. |
| Roles | Gated | Direct URLs for viewer, sales, and policy desk stay denied after reload and back, on Chromium, Pixel 5, and WebKit. |
| Security boundaries | Gated for the suite | Tenancy, RLS on Postgres, sprint0 security, and no-impersonation passed. This is not a penetration test. |
| Negative and edge | Gated | Short stock rejects complete. After a purchase receipt, one retry posts the stock once. A second complete does not post again. |
| Cross-feature | Gated | G-17 through G-22 re-ran, including Sales history, invoice detail, dashboard, and purchase history. |
| Performance and SLA | Gated | I1–I5 passed on this machine. I1 is the product barcode search, warm-up discarded, 20 samples, P95 at most 100ms. |
| Data-volume | Reference | 50,000 invoices. Full-year register pull is refused at the cap. A month window stays flat. Not a k6 soak. |
| Accessibility | Gated | Keyboard, accessible name, and axe color-contrast on the POS scan field. Chromium, Pixel 5, WebKit. Not an NVDA or VoiceOver session. |
| Compatibility | Gated for the scoped set | Pixel 5 and WebKit on layout, keyboard, contrast, and the denial checks. |
| Localization | Gated for the money chip | Hindi golden: completed chip is `पूर्ण`, and `ग्राहक बकाया` is on the dashboard. |
| Integration | Gated for books | WF-37 refunds once without a provider HTTP call. WF-38 fee is 2.00 and the net receipt wins. |
| Reliability | Gated for repeatability | Thirty product-list reads return one count. Query count does not grow after warm-up. |
| Regression and suite completeness | Gated | Fast lane plus the G-17 page tests. |
| Failure and recovery | Gated | Validation failure then one successful complete. Outbox conflict spec. |

## Quality gate

- [x] I1 P95 taken on the barcode search
- [x] I2, I3, I4, I5 measured
- [x] Browser goldens clicked through against Django
- [x] Postgres RLS lane passed
- [x] Fast lane passed under `INVARIANTS_STRICT=1`
- [x] Role denial survives reload and back
- [x] Contrast and accessible name recorded from axe
- [x] Query counts use `CaptureQueriesContext` and `+ 2`
- [x] One independent total on I2: quantity 1 × 100 at 18% is 118.00
