# Workflow catalog

Working index, reconciled 2026-09-27. Canonical workflow ids are `WF-01` through `WF-60` in `backend/tests/workflows/`. Canonical journey ids are in `qos/journeys.yaml` and `docs/TEST_CENSUS_LEDGER.md`.

Headings that used another scheme, including `WF-SALES-01`, are retired. They are not tests and they are not requirements.

## Critical workflows

| Workflow | Journey | What the test asserts |
|---|---|---|
| POS checkout and invoice complete | J-RETAIL-P2-POS, I1 browser / I2 API | `test_wf19_pos_checkout`; `test_i2_invoice_complete_roundtrip_p95_within_800ms` |
| B2B invoice complete | WF-01 | Stock down, GST, receivable, `assert_consistent` |
| Purchase inward | J-TRADE-P1-INWARD, WF-04 | Stock up and payable in one complete |
| Receipt allocation | J-TRADE-P5-ALLOC | Allocation tests and `gl.party_subledger_complete` |
| Sales return / credit note | WF-03, J-BATCH-P5-RETURNCN | Return posts and a second return of the same serial is refused |
| Credit-limit block | J-TRADE-P3-CREDITBLOCK | `test_wave15_credit_limit_refund.py` |
| Period lock | WF-20 | Backdated complete is refused |
| GSTR-1 / GSTR-3B | J-TRADE-P5-MONTHEND, WF-27 | Tie-out |
| Quotation to challan to invoice | J-TRADE-P3-QUOTE, J-TRADE-P3-CHALLAN | Where the chain is supported |
| Workshop job | J-JOB-P9-REPAIR | Convert once. Stock posts on invoice complete |
| Route stop | J-ROUTE-P7-BEAT | Delivered requires a receiver name. The slip does not post stock |
| Project milestones | J-PROJ-P1-MILESTONE | Close refused while a READY milestone is uninvoiced |
| Policy issue | J-INS-P12-ISSUE | Issue once. Commission is off the ledger (D17) |
| Vendor ticket share | J-SAAS-P10-SUPPORT | Owner only. Invisible to the source company and to a third company |
| Tenant switch | J-X-P1-SWITCHCO | Lists re-scope. Cross-company read is 404 |

## Holds

WF-37 and WF-38 are gated by `test_wf37_refunds` and `test_wf38_mdr_settlement_reconciliation`. Those tests do not call Cashfree or PayU. A live sandbox capture is not part of the suite.

WF-54 is a known-limitation pin: the worksheet exists, the certificate PDF does not.
