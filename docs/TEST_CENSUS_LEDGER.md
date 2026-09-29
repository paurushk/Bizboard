# Test census ledger

**Date:** 2026-09-26. Marks: gated, partial, gap, blocked, reference, boundary.

Every id in `qos/journeys.yaml` has a row. The desks added after that file are listed after it.

| Id | Kind | Mark | Layer | Test |
|---|---|---|---|---|
| PRE-01 / ARCH-01 | Preset | Gated | L4 + L6 | test_pj_retail.py, POS golden |
| PRE-02 / ARCH-03 | Preset | Gated | L4 + L6 | Trade persona, lifecycle-arch03 golden |
| ARCH-02 | Archetype | Reference | L3 | WF-56, J-COMP-P1-BOS |
| ARCH-04 | Archetype | Partial | L4 | Transfer and count personas. Per-godown reorder is J-GODOWN-P4-REORDER |
| ARCH-05 | Archetype | Gated | L4 + L5 | FEFO persona, expiry matrix |
| ARCH-06 | Archetype | Partial | L4 | Serial lifecycle. Warranty lookup is J-SERIAL-P2-WARRANTY |
| PRE-03 | Preset | Gated | L4 + L6 | test_pj_workshop_job.py, workshop-job-golden.spec.ts |
| PRE-04 | Preset | Gated | L4 + L6 | test_pj_route_pod.py, route-pod-golden.spec.ts |
| PRE-05 | Preset | Reference | L4 | CRM persona tests. Retail and trade do not grant CRM |
| PRE-06 | Preset | Reference | L4 | Contracts persona and WF-11 |
| PRE-07 | Preset | Gated | L4 + L6 | test_pj_project_milestones.py, projects-milestone-golden.spec.ts |
| PRE-08 | Preset | Reference | L4 | test_manufacturing_pack_grants_the_module. Wizard does not propose it |
| PRE-09 | Preset | Gated | L4 + L6 | test_pj_insurance_desk.py, insurance-desk-golden.spec.ts. Commission is D17 |
| PRE-10 | Preset | Gated | L4 + L6 | test_pj_saas_ops.py, saas-share-and-suspend-golden.spec.ts |
| P1–P6 | Persona | Gated | L4 | Existing test_pj_*.py and role-boundaries.spec.ts |
| P7 | Persona | Gated | L4 + L6 | Route POD persona and golden |
| P8 | Persona | Reference | L3 | WF-16. No buyer role |
| P9 | Persona | Gated | L4 + L6 | Workshop persona and golden. AMC visit is a boundary |
| P10 | Persona | Gated | L4 | Support persona, claim, vendor share |
| P11–P12 | Persona | Gated | L4 + L6 | Insurance desk persona, POLICY_DESK role spec, issue golden |
| P13–P14 | Persona | Gated | L4 + L6 | SaaS persona and suspend golden |
| J-RETAIL-P2-POS | Journey | Gated | L4 | P2 / ARCH-01 / backend/tests/workflows/test_wf19_pos_checkout.py; tests/personas/test_pj_retail.py |
| J-RETAIL-P2-POS-SPEED | Journey | Gated | L4 | P2 / ARCH-01 / TESTING_STRATEGY.md |
| J-RETAIL-P2-OFFLINE | Journey | Gated | L4 | P2 / ARCH-01 / web/e2e/personas/offline-outbox-conflict.spec.ts |
| J-RETAIL-P1-DAYCLOSE | Journey | Gated | L4 | P1 / ARCH-01 / tests/personas/test_pj_retail.py::test_pj_retail_owner_normal_day |
| J-TRADE-P3-QUOTE | Journey | Gated | L4 | P3 / ARCH-03 / test_wf06_quotation_to_invoice; tests/personas/test_pj_trader.py |
| J-TRADE-P3-CREDITBLOCK | Journey | Gated | L4 | P3 / ARCH-03 / test_wave15_credit_limit_refund.py |
| J-TRADE-P1-LOOP | Journey | Gated | L4 | P1 / ARCH-03 / tests/workflows/test_wf_arch03_complete_loop.py; PJ-TRADER-OWNER |
| J-TRADE-P5-ALLOC | Journey | Gated | L4 | P5 / ARCH-03 / test_payment_allocation.py; gl.party_subledger_complete |
| J-TRADE-P5-BANKREC | Journey | Reference | L4 | `test_pj_bank_reconciliation_aa_matching_and_journal` asserts UTR match, amount match, ambiguity, and the bank-charges journal. WF-33. |
| J-TRADE-P5-MONTHEND | Journey | Gated | L4 | P5 / ARCH-03 / test_wf27_gstr1_3b_tie_out; PJ-WHOLE-ACCT |
| J-TRADE-P3-FLAKYNET | Journey | Gated | L6 | `offline-outbox-conflict.spec.ts` test `J-TRADE-P3-FLAKYNET`. A rejected draft stays rejected. A live packet-loss capture was not run. |
| J-GODOWN-P4-TRANSFER | Journey | Gated | L4 | P4 / ARCH-04 / test_wf21_stock_transfer_between_godowns; inventory.transfer_pairs_net_zero |
| J-GODOWN-P4-COUNT | Journey | Reference | L4 | `test_pj_custodian_physical_stock_count_and_adjustments` posts shortage and surplus and denies sales staff |
| J-GODOWN-P1-MULTI | Journey | Gated | L4 | P1 / ARCH-04 / tests/personas/test_pj_stubs.py::test_pj_wholesale_owner_multi_godown_day |
| J-BATCH-P4-INWARD | Journey | Gated | L4 | P4 / ARCH-05 / test_item_godown_expiry.py |
| J-BATCH-P4-FEFO | Journey | Gated | L4 | P4 / ARCH-05 / test_wave15_fefo.py; inventory.no_expired_issue_when_blocked |
| J-BATCH-P4-EXPIREBLOCK | Journey | Reference | L4 | `test_expiry_guard_band_matrix` — yesterday blocked only when the policy is on; expiry day itself still issues |
| J-SERIAL-P4-INWARD | Journey | Reference | L4 | `test_pj_bulk_serial_import_partial_failure_blocks_whole_job` — one bad opening_serials row blocks the PRODUCTS commit |
| J-SERIAL-P2-RETURN | Journey | Gated | L4 | P2 / ARCH-06 / test_pr5_returns_serials_fefo.py; inventory.serial_traceability |
| J-SVC-P1-MIXED | Journey | Gated | L4 | P1 / ARCH-07 / tests/personas/test_pj_stubs.py::test_pj_service_owner_no_stock; edge cases |
| J-SVC-P5-TDS | Journey | Gated | L4 | P5 / ARCH-07 / test_sprint_c_tds_tcs.py |
| J-SVC-P1-RECURRING | Journey | Gated | L4 | `test_j_svc_p1_recurring_owner_day` plus `test_wf11_recurring_invoice_generation_is_idempotent` |
| J-ONBOARD-P1 | Journey | Gated | L4 | P1 / ARCH-03 / test_wf45_registration; PJ-NEWUSER; e2e-golden personas |
| J-ONBOARD-P1-STEPS | Journey | Gated | L4 | `test_j_onboard_p1_steps_blocking_path_is_four`. Blocking path is tax, shop, catalog, first bill. Payments do not block. The "<= 3 steps" sentence was wrong. |
| J-MIGRATE-P5 | Journey | Gated | L4 | P5 / ARCH-03 / tests/personas/test_pj_migration.py |
| J-CA-P6-AUDIT | Journey | Reference | L4 | `test_pj_ca_statutory_and_accounting_integrity_audit` ties trial balance, AR, AP, stock, and GST worksheets. A human CA signature is not a software step. |
| J-ROLE-P2-NAV | Journey | Gated | L4 | P2 / ARCH-03 / web/e2e/personas/role-boundaries.spec.ts (sales, and PJ-MANAGER) |
| J-ROLE-P5-NAV | Journey | Gated | L4 | P5 / ARCH-03 / web/e2e/personas/role-boundaries.spec.ts (accountant, and PJ-AUDITOR) |
| J-A11Y-P2-KEYBOARD | Journey | Gated | L6 | Keyboard spec, plus the POS scan field's accessible name and axe `color-contrast`, on Chromium, Pixel 5, and WebKit. |
| J-SCALE-P1-REPORTS | Journey | Reference | L4 | `test_qos0003_large_tenant_reports.py` — 50,000 invoices. A full-year pull is refused at the cap. A month window stays flat. Not a staging soak. |
| J-RETAIL-P2-THERMAL | Journey | Gated | L4 | `test_j_retail_p2_thermal_sale_completes_without_a_printer`. Checkout does not take a printer. The slip is a PDF. Hardware spooling is a known limitation. |
| J-RETAIL-P1-REORDER | Journey | Reference | L4 | `test_pj_golden_journey_kirana_retail_fast_turnover` asserts stock below reorder_level 15 raises LOW_STOCK_FAST_MOVER and a replenishment clears it |
| J-COMP-P1-BOS | Journey | Gated | L4 | P1 / ARCH-02 / test_wf56_composition_bill_of_supply (LIM coverage, not a freeze blocker) |
| J-TRADE-P1-INWARD | Journey | Gated | L4 | P1 / ARCH-03 / tests/workflows/test_wf04_purchase.py; test_a2_posting_atomicity.py |
| J-TRADE-P3-CHALLAN | Journey | Gated | L4 | P3 / ARCH-03 / test_next_batch_so_challan.py; test_wf_arch03_complete_loop.py |
| J-TRADE-P5-TCS | Journey | Gated | L4 | P5 / ARCH-03 / test_wf34_tcs_on_sales_206c; test_wf36_tds_tcs_worksheets_reconcile |
| J-TRADE-P5-DUNNING | Journey | Gated | L4 | P5 / ARCH-03 / test_wf42_dunning_schedule (send half is a stated LIM - QOS-0032) |
| J-GODOWN-P2-CENTRAL | Journey | Gated | L4 | P2 / ARCH-04 / test_pj_wholesale_owner_multi_godown_day |
| J-GODOWN-P4-REORDER | Journey | Gated | L4 | `test_j_godown_p4_reorder_flags_the_low_godown` |
| J-BATCH-P5-RETURNCN | Journey | Gated | L4 | P5 / ARCH-05 / test_pr5_returns_serials_fefo.py; test_wf03_sales_return |
| J-BATCH-P1-ALERTS | Journey | Gated | L4 | P1 / ARCH-05 / test_item_godown_expiry.py; test_a07_dunning-style alerts |
| J-SERIAL-P2-WARRANTY | Journey | Gated | L4 | `test_j_serial_p2_warranty_lookup_includes_a_serial_never_sold`. Exact `serial_number` lookup. Sales may read. Accountant may not. Transition stays inventory. |
| J-SERIAL-P5-VENDORDN | Journey | Gated | L4 | P5 / ARCH-06 / test_wf13-adjacent purchase debit note; test_b4_b5_notes_serial.py |
| J-SVC-P1-AMC | Journey | Reference | L4 | `test_pj_commercial_contractor_amc_and_field_service_journey` creates the AMC. A contract due date does not create a job card (`J-AMC-P9-VISIT` stays Boundary). |
| J-X-P1-SWITCHCO | Journey | Gated | L4 | P1 / ARCH-03 / test_wf49_switch_company; tests/tenancy/ |
| J-X-P5-JOURNAL | Journey | Gated | L4 | P5 / ARCH-03 / tests/workflows/test_wf29_manual_journal.py; gl.journals_balanced |
| J-X-P6-TALLY | Journey | Gated | L4 | P6 / ARCH-03 / tests/snapshots/test_exports_and_filtered_reports.py; test_phase7_tally.py |
| J-X-P1-PWRESET | Journey | Gated | L4 | P1 / ARCH-03 / test_wf46_password_reset; core/throttles.py |
| J-X-P2-RECEIPT | Journey | Gated | L4 | P2 / ARCH-01 / test_wf39_advance_payment_on_account; test_payment_allocation.py |
| J-X-P1-KPIDRILL | Journey | Gated | L4 | P1 / ARCH-03 / reports.cross_reconcile (KPI == drill-down, partial); QOS-0053 (AP vs AR model) |
| J-X-P1-OTP | Journey | Gated | L4 | P1 / ARCH-01 / tests/test_auth.py::test_otp_* (rate-limit assertion still skipped - see A26) |
| J-PROJ-P1-MILESTONE | Journey | Gated | L4 | P1 / PRE-07 / backend/tests/personas/test_pj_project_milestones.py |
| J-JOB-P9-REPAIR | Journey | Gated | L4 | P9 / PRE-03 / test_pj_workshop_job.py and workshop-job-golden.spec.ts |
| J-ROUTE-P7-BEAT | Journey | Gated | L4 | P7 / PRE-04 / test_pj_route_pod.py and route-pod-golden.spec.ts |
| J-AMC-P9-VISIT | Journey | Boundary | L4 | test_j_amc_p9_visit_stays_on_contracts |
| J-CARE-P10-TICKET | Journey | Boundary | L4 | test_j_care_p10_ticket_has_no_serial |
| J-INS-P11-OPTIONS | Journey | Gated | L4 | test_pj_insurance_desk.py and insurance-desk-golden.spec.ts |
| J-INS-P12-ISSUE | Journey | Gated | L4 | same |
| J-INS-P12-RENEW | Journey | Gated | L4 | test_j_ins_p12_renew_p5_commission_p10_claim |
| J-INS-P5-COMMISSION | Journey | Boundary | L4 | D17. Commission is not a receipt and not a journal |
| J-INS-P10-CLAIM | Journey | Gated | L4 | same renew test |
| J-SAAS-P13-ACTIVATE | Journey | Gated | L4 | test_j_saas_p13_activate_and_winback |
| J-SAAS-P13-WINBACK | Journey | Gated | L4 | saas-share-and-suspend-golden.spec.ts |
| J-SAAS-P10-SUPPORT | Journey | Gated | L4 | test_j_saas_p10_support_share_is_owner_only |
| J-SAAS-P1-TRIAL | Journey | Reference | L3 | Existing billing trial tests |
| J-SAAS-P14-BILL | Journey | Reference | L3 | Existing Razorpay and plan-change tests |
| WF-01–WF-53, WF-55–WF-60 | Workflow | Gated | L3 | def test_wf in backend/tests/workflows/ |
| WF-54 | Workflow | Boundary | L3 | test_wf54_certificates_remain_a_known_limitation |
| WF-17, WF-20, WF-23–WF-25 | Workflow | Reference | L3 | Pointer tests |
| WF-37, WF-38 | Workflow | Gated | L3 | `test_wf37_refunds` refunds once with `skip_gateway`. `test_wf38_mdr_settlement_reconciliation` parses a 2.00 fee and prefers the net receipt. No live Cashfree or PayU HTTP call. |
