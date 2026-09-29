# Missing test cases

Closed for the 2026-09-27 cycle. This file is not a backlog of unwritten tests.

Specs in the 2026-09-26 draft that used ids such as `WF-SALES-02` are withdrawn. Those ids are not in the suite.

## Added

| Test | Journey or SLA |
|---|---|
| `test_j_serial_p2_warranty_lookup_includes_a_serial_never_sold` | J-SERIAL-P2-WARRANTY |
| `test_j_godown_p4_reorder_flags_the_low_godown` | J-GODOWN-P4-REORDER |
| `test_j_onboard_p1_steps_blocking_path_is_four` | J-ONBOARD-P1-STEPS |
| `test_j_retail_p2_thermal_sale_completes_without_a_printer` | J-RETAIL-P2-THERMAL |
| `test_j_svc_p1_recurring_owner_day` | J-SVC-P1-RECURRING |
| `test_i4_catalog_import_of_5000_skus_meets_ten_seconds` | I4 |
| `test_i2_invoice_complete_roundtrip_p95_within_800ms` | I2 |
| `test_i3_fifty_row_product_list_p95_within_400ms` | I3 |
| `test_i5_invoice_pdf_generation_p95_within_2_5s` | I5 |
| `test_i1_barcode_lookup_p95_within_100ms` | I1 |
| `test_complete_failure_then_retry_posts_stock_once` | Failure then retry |
| `test_wf37_refunds` | WF-37 |
| `test_wf38_mdr_settlement_reconciliation` | WF-38 |
| `test_job_card_list_query_count_is_flat` and the project, policy, and shared-ticket twins | Query-count protocol |
| `test_product_list_repeat_stays_stable` | Repeatability |

## Not a software hold

A live Cashfree or PayU capture, a human CA signature, and a staging k6 soak need a vendor sandbox, a person, and a staging host. The books refund, the worksheet tie-out, and the 50,000-invoice register fixture are in the suite. Commission stays off the ledger until a written product decision (D17).
