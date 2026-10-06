# E2E coverage matrix

This file is not a second ledger. Status lives in `docs/TEST_CENSUS_LEDGER.md`. Reconciled 2026-09-27.

The fifteen critical workflows and the open rows from the 2026-09-27 plan are marked there. Rows that were Gap and already had an assertion are Reference. Rows that gained a test whose name cites the journey id are Gated.

Still Blocked, with an owner and a revisit date of 2026-10-31:

| Id | Why | Owner |
|---|---|---|
| J-TRADE-P3-FLAKYNET, J-SCALE-P1-REPORTS, G-7 | No staging network or load budget | Founder / ops |
| J-CA-P6-AUDIT, G-14 | No CA signature. Proxy tests stay | Founder + CA |
| WF-37, WF-38 | Books refund and MDR net match are tested. No live gateway HTTP call | Eng |
| I1 | POS barcode lookup <= 100ms is a browser P95. `pos-perf-sla.spec.ts` allows 500ms and does not gate I1 | QA, next browser pass |

I2, I3, I4, and I5 are gated by `backend/tests/test_phase0_api_slas.py` and `test_i4_catalog_import_of_5000_skus_meets_ten_seconds`.
