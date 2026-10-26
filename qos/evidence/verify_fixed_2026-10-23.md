# verify_fixed — 2026-10-23

Commit `0d829a1c` (plus working tree) · backend DB: **postgresql** · apply: True

Summary: manual 18, passed 50
Promoted to verified: 50 (QOS-0002, QOS-0008, QOS-0009, QOS-0011, QOS-0018, QOS-0022, QOS-0024, QOS-0027, QOS-0032, QOS-0033, QOS-0035, QOS-0037, QOS-0038, QOS-0039, QOS-0041, QOS-0044, QOS-0047, QOS-0048, QOS-0050, QOS-0059, QOS-0071, QOS-0098, QOS-0101, QOS-0102, QOS-0107, QOS-0108, QOS-0109, QOS-0110, QOS-0111, QOS-0112, QOS-0113, QOS-0114, QOS-0115, QOS-0116, QOS-0117, QOS-0118, QOS-0119, QOS-0120, QOS-0121, QOS-0122, QOS-0123, QOS-0124, QOS-0127, QOS-0133, QOS-0134, QOS-0140, QOS-0146, QOS-0147, QOS-0148, QOS-0153)

| Item | Kind | Result | Detail | Guard |
|---|---|---|---|---|
| QOS-0006 | manual | manual | not a backend/vitest guard | `scripts/test_concurrency_local.sh` |
| QOS-0007 | manual | manual | not a backend/vitest guard | `web/e2e/a11y.spec.ts::J-A11Y-P2-KEYBOARD POS scan field is keyboard-operable without a mouse` |
| QOS-0010 | manual | manual | not a backend/vitest guard | `web/e2e/route-smoke.spec.ts` |
| QOS-0012 | manual | manual | not a backend/vitest guard | `.github/workflows/ci.yml` |
| QOS-0013 | manual | manual | not a backend/vitest guard | `web/playwright.config.ts::webkit` |
| QOS-0016 | manual | manual | not a backend/vitest guard | `web/e2e-golden/v95-dashboard-p95.spec.ts::dashboard p95 stays within budget on twelve months of invoices` |
| QOS-0017 | manual | manual | not a backend/vitest guard | `web/e2e/pos-friction.spec.ts::opens with the scan field focused and no blocking dialog` |
| QOS-0019 | manual | manual | not a backend/vitest guard | `.github/workflows/ci.yml` |
| QOS-0023 | manual | manual | not a backend/vitest guard | `.github/workflows/ci.yml` |
| QOS-0025 | manual | manual | not a backend/vitest guard | `web/e2e/personas/role-boundaries.spec.ts` |
| QOS-0026 | manual | manual | not a backend/vitest guard | `web/e2e/mobile-layout.spec.ts` |
| QOS-0040 | manual | manual | not a backend/vitest guard | `web/e2e/pos-friction.spec.ts::exactly one tender button is emphasised as the remembered default (QOS-0040)` |
| QOS-0057 | manual | manual | not a backend/vitest guard | `docs/reviews/CR_090_104_RESTATUS_2026-09-11.md` |
| QOS-0058 | manual | manual | not a backend/vitest guard | `docs/reviews/MASTER_ISSUE_REGISTER.md` |
| QOS-0096 | manual | manual | not a backend/vitest guard | `web/e2e/route-smoke.spec.ts` |
| QOS-0099 | manual | manual | not a backend/vitest guard | `web/package.json::lint` |
| QOS-0105 | manual | manual | not a backend/vitest guard | `scripts/ci_gates/guards/guard_runtime_alignment.py` |
| QOS-0106 | manual | manual | not a backend/vitest guard | `scripts/ci_gates/guards/guard_config_consistency.py` |
| QOS-0002 | backend | passed | 1 passed | `backend/tests/errors/test_webhook_enumeration.py::test_inbound_webhook_set_is_exactly_the_known_two` |
| QOS-0008 | backend | passed | 1 passed | `backend/tests/personas/test_pj_stubs.py::test_pj_wholesale_godown_custodian` |
| QOS-0009 | backend | passed | 6 passed | `backend/tests/matrices/test_company_settings_matrix.py::test_expiry_guard_band_matrix` |
| QOS-0011 | backend | passed | 1 passed | `backend/tests/errors/test_freeze_gate_contracts.py::test_api_response_carries_hardening_headers` |
| QOS-0018 | backend | passed | 1 passed | `backend/tests/test_pr6_period_gl.py::test_completed_pcn_without_je_blocks_after_cutoff` |
| QOS-0022 | backend | passed | 1 passed | `backend/tests/test_check_invariants_command.py::test_check_invariants_clean_company_passes` |
| QOS-0024 | web | passed | 1 passed | `web/src/components/UnsavedChangesGuard.test.tsx::does not throw when rendered outside a data router (UX-001)` |
| QOS-0027 | backend | passed | 1 passed | `backend/tests/workflows/test_wf60_arch05_statutory_forms.py::test_wf60_arch05_drug_licence_soft_block_then_pdf` |
| QOS-0032 | backend | passed | 1 passed | `backend/tests/test_a07_dunning.py::test_dunning_falls_back_to_email_when_no_phone` |
| QOS-0033 | backend | passed | 1 passed | `backend/tests/snapshots/test_gstr1_json.py::test_gstr1_hsn_summary_snapshot_mixed_rate` |
| QOS-0035 | backend | passed | 1 passed | `backend/tests/test_item_godown_expiry.py::test_serial_bulk_ingest_partial_failure` |
| QOS-0037 | web | passed | 1 passed | `web/src/utils/indianStates.test.ts::decodes the leading state code of a full GSTIN` |
| QOS-0038 | web | passed | 4 passed | `web/src/components/CollectionAttentionCard.test.tsx` |
| QOS-0039 | backend | passed | 1 passed | `backend/tests/test_phase3_payments.py::test_bulk_accept_exact_matches_only_exact_class_and_is_undoable` |
| QOS-0041 | web | passed | 1 passed | `web/src/pages/help/faqContent.portalMapping.test.tsx::has a GSTR-1 and a GSTR-3B "how to file on the portal" entry` |
| QOS-0044 | backend | passed | 1 passed | `backend/tests/test_a07_dunning.py::test_auto_credit_hold_blocks_severe_overdue_customer_with_no_credit_limit` |
| QOS-0047 | web | passed | 15 passed | `web/src/pages/inventory/LabelPrintPage.test.tsx` |
| QOS-0048 | web | passed | 39 passed | `web/src/pages/sales/QuickEntryPage.test.tsx` |
| QOS-0050 | backend | passed | 1 passed | `backend/tests/errors/test_chaos_degradation.py::test_cache_outage_degrades_health_not_crash` |
| QOS-0059 | backend | passed | 1 passed | `backend/tests/test_a4_a5_reporting.py::test_qos0059_reserved_drift_does_not_understate_available` |
| QOS-0071 | backend | passed | 1 passed | `backend/tests/test_b06_020_cross_tenant_membership_gstin.py::test_company_gstins_list_excludes_other_tenant` |
| QOS-0098 | web | passed | 1 passed | `web/src/i18n/jsxLiteralRatchet.test.ts::keeps every screen free of hard-coded English between tags` |
| QOS-0101 | backend | passed | 18 passed | `backend/tests/test_backup_scripts.py` |
| QOS-0102 | backend | passed | 21 passed | `backend/tests/test_audit_append_only.py` |
| QOS-0107 | backend | passed | 8 passed | `backend/tests/test_ops_metrics_histogram.py` |
| QOS-0108 | backend | passed | 14 passed | `backend/tests/test_double_submit_money_paths.py` |
| QOS-0109 | backend | passed | 1 passed | `backend/tests/test_quotation_closure.py::test_wp1_even_split_shares_header_and_sums_to_quote` |
| QOS-0110 | backend | passed | 1 passed | `backend/tests/test_quotation_closure.py::test_wp2_restore_round_trip_keeps_ledger_revisions_and_links` |
| QOS-0111 | backend | passed | 1 passed | `backend/tests/test_quotation_closure.py::test_wp3_create_response_has_real_totals` |
| QOS-0112 | backend | passed | 1 passed | `backend/tests/test_quotation_closure.py::test_wp4_flag_off_leaves_an_orphan_and_the_sweep_releases_it` |
| QOS-0113 | backend | passed | 1 passed | `backend/tests/test_quotation_closure_cross.py::test_wp6_partly_converted_expired_quote_deadlock_is_resolved_by_close_remaining` |
| QOS-0114 | backend | passed | 1 passed | `backend/tests/test_quotation_closure_cross.py::test_salespeople_endpoint_works_for_sales_staff_without_payroll` |
| QOS-0115 | backend | passed | 1 passed | `backend/tests/test_quotation_closure_cross.py::test_product_cost_permission_matrix_omits_the_field_and_keeps_below_cost` |
| QOS-0116 | backend | passed | 1 passed | `backend/tests/test_quotation_closure_cross.py::test_wp7_list_query_count_does_not_grow_with_rows` |
| QOS-0117 | backend | passed | 1 passed | `backend/tests/test_quotation_closure_cross.py::test_wp14b_share_makes_a_link_marks_sent_and_serves_the_pdf` |
| QOS-0118 | backend | passed | 1 passed | `backend/tests/test_money_in_receipts.py::test_void_requires_a_reason_on_the_server` |
| QOS-0119 | backend | passed | 1 passed | `backend/tests/test_money_in_phase2.py::test_credit_mode_is_refused_by_the_service_and_the_api` |
| QOS-0120 | backend | passed | 1 passed | `backend/tests/test_money_in_phase2.py::test_partial_allocation_clears_the_same_amount_in_the_gl_and_on_the_invoice` |
| QOS-0121 | backend | passed | 1 passed | `backend/tests/test_money_in_phase2.py::test_refunding_part_of_an_advance_keeps_every_reader_consistent` |
| QOS-0122 | backend | passed | 1 passed | `backend/tests/test_money_in_phase2_b.py::test_cross_module_tie_out_through_cheque_tds_discount_bounce_void_and_refund` |
| QOS-0123 | backend | passed | 1 passed | `backend/tests/test_money_in_phase2.py::test_export_needs_the_export_permission_and_is_audited` |
| QOS-0124 | backend | passed | 1 passed | `backend/tests/test_customers_master.py::test_sales_staff_cannot_archive_or_unblock_by_patch` |
| QOS-0127 | backend | passed | 1 passed | `backend/tests/test_credit_debit_notes_plan.py::test_credit_note_stops_at_annual_return_filing_date` |
| QOS-0133 | backend | passed | 6 passed | `backend/tests/test_acs_concurrency_postgres.py` |
| QOS-0134 | backend | passed | 5 passed | `backend/tests/test_ccj_concurrency_postgres.py` |
| QOS-0140 | backend | passed | 3 passed | `backend/tests/test_dan_concurrency_postgres.py` |
| QOS-0146 | backend | passed | 20 passed | `backend/tests/test_mfg_revaluation.py` |
| QOS-0147 | backend | passed | 17 passed | `backend/tests/test_mfg_subcontract.py` |
| QOS-0148 | backend | passed | 2 passed | `backend/tests/test_mfg_left_outs.py` |
| QOS-0153 | backend | passed | 4 passed | `backend/tests/agents/test_races_postgres.py` |
