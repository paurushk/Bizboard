# Freeze Scope → test coverage map

Companion to [`FREEZE_SCOPE.md`](FREEZE_SCOPE.md). Every SUPPORTED item (§A) and
every §G/§H flow marked **SUP** is listed here with the **concrete** test(s) that
gate it, or an explicit **GAP** / **not gated** line. The `FG-2x` codes in
`FREEZE_SCOPE.md` are plan labels; this file is the actual wiring.

Last reconciled: 2026-09-27. The 2026-09-16 freeze rows were not rewritten.
Changes after that date in billing, `payments/promise_to_pay.py`, CRM referrals,
and RLS migrations `0036` through `0040` are outside the freeze table. They are
gated by `test_rls_coverage._migration_tables` (the union includes every
migration whose name contains `rls`, including `0036_rls_payment_promise`) and
by the persona and roadmap tests that cite those desks. A new company table
still belongs in a follow-up RLS migration, not in `0020`.

Previous reconciliation: 2026-09-16 (SaaS dunning/recon, ZAP skip-job, no-impersonation,
freeze Table B deploy defaults, inventory-staff RBAC, chargeback ignore). Backend
suite paths are under `backend/`.

When recording a Graph-2 checklist result, cite the stable **CFT-NNN** id from
[`CROSS_FLOW_TEST_CHECKLIST.md`](CROSS_FLOW_TEST_CHECKLIST.md) — do not cite
bullet prose (wording drifts; the id does not).

## Legend

- ✅ gated — a merge-blocking test asserts it (Phase 2 gate / `invariant-sweep`)
- 🟡 partial — covered but a stated sub-case is not yet asserted
- ⛔ GAP — SUPPORTED but nothing gates it yet
- 🚫 blocked — needs an external dependency (credentials, WSL, a real broker)

---

## A. SUPPORTED

| # | Item | Status | Gating test(s) |
|---|---|---|---|
| A1 | Sales invoice — GST intra-state | ✅ | `tests/workflows/test_wf01_sale_intrastate.py`, `tests/snapshots/test_gl_posting_sets.py::test_sale_intrastate_gl_posting_set`, `tests/personas/test_pj_retail.py`, `tests/personas/test_pj_trader.py` |
| A2 | Sales invoice — GST inter-state | ✅ | `tests/workflows/test_wf_todo_stubs.py::test_wf02_sale_interstate_with_cess`, `tests/gst/test_place_of_supply_matrix.py`, `tests/matrices/test_gst_settings_matrix.py` |
| A3 | Sales invoice — non-GST / nil-rated | ✅ | `test_wf56_composition_bill_of_supply` (NON_GST path), `tests/edge/test_document_edge_cases.py` |
| A4 | Quotation | ✅ | `test_wf06_quotation_to_invoice` |
| A5 | Sales return / credit note | ✅ | `test_wf03_sales_return`, `test_wf07_sales_credit_note_financial`, `tests/test_sprint2_cn_einvoice.py` |
| A6 | Purchase (no GRN) | ✅ | `tests/workflows/test_wf04_purchase.py`, `tests/snapshots/test_gl_posting_sets.py::test_purchase_gl_posting_set`, `test_pj_trader_owner_normal_day` |
| A7 | Purchase return / debit note | ✅ | `test_wf05_purchase_return`, `test_wf12_purchase_credit_note` (AP ↓ + ITC reversal), `test_wf16_purchase_order_to_purchase` (PO → invoice) |
| A8 | Product lookup | ✅ | `test_pj_retail_sales_staff_boundary`, `test_pj_trader_sales_staff_boundary` (`products/?search=` allowed, company-scoped) |
| A9 | Inventory movements & balances | ✅ | invariants `inventory.balance_equals_movements` / `running_cost_qty_matches_movements` (swept every strict test), `test_wf21_stock_transfer_between_godowns`, `test_pj_wholesale_owner_multi_godown_day`, `test_pj_retail_owner_normal_day` (write-off) |
| A10 | Customer receipt + allocation | ✅ | `test_wf39_advance_payment_on_account`, `test_pj_service_owner_no_stock`, `test_pj_trader_owner_normal_day`, `tests/test_money_in_receipts.py` (filters, summary, export, voucher, void audit, walk-in rule, one-request allocation) |
| A11 | Supplier payment + allocation | ✅ | `tests/workflows/test_a11_supplier_payment.py::test_a11_supplier_payment_partial_then_full_allocation`, `test_wf04_purchase_full_chain` (pay-in-one), `test_supplier_payment_allocation_flow`; debit-note AP enlarge is `test_wf13_purchase_debit_note` (TDS-on-purchase remains WF-35) |
| A9b | Stock adjustment / write-off | ✅ | `test_wf22_stock_adjustment_writeoff` — on_hand + running-cost value fall by qty×cost; **no auto GL** (pilot: a write-off doesn't hit P&L until booked); movement log append-only |
| A11b | Bank receipt → per-instrument GL | ✅ | `test_wf26_bank_receipt_to_gl` — a `bank_account`-tagged receipt posts to the `1500-<id>` child ledger; AR clears on allocation |
| A13b | GSTR-1 ↔ GSTR-3B tie-out | ✅ | `test_wf27_gstr1_3b_tie_out` (mixed intra/inter period) + `tests/snapshots/test_gstr1_json.py` / `test_gstr3b_json.py` |
| A12 | Customer & supplier ledgers | ✅ | invariant `gl.party_subledger_complete`, `test_wf40_bad_debt_writeoff`, `test_pj_trader_owner_normal_day` (ledger read) |
| A13 | Core reports | ✅ | `tests/snapshots/test_report_json.py` (trial_balance / profit_and_loss / balance_sheet), `test_pj_wholesale_accountant_period_close` |
| A14 | PDF / A4 invoice | ✅ | `tests/snapshots/test_gstr2b_and_pdf.py::test_gst_tax_invoice_pdf_text_snapshot` (pypdf text extraction, volatile lines redacted) |
| A15 | Imports (idempotent) | ✅ | `tests/personas/test_pj_stubs.py::test_pj_trader_import_operator` (customers + products + opening stock, replay rejected by SKU uniqueness), `tests/test_imports.py`. Supersedes skipped WF-23/24/25 |
| A16 | Exports | ✅ | `tests/snapshots/test_exports_and_filtered_reports.py` — sales-register CSV header + row snapshot, XLSX content-type + header contract; plus `tests/test_imports.py::test_export_*` (formula-injection sanitisation) |
| A17 | RBAC | ✅ | `tests/tenancy/test_rbac_matrix.py`, every `*_boundary` / role journey in `tests/personas/` |
| A18 | Tenant isolation | ✅ | `tests/tenancy/`, `test_wf28_two_tenant_interleave`, invariants `tenancy.*` |
| A19 | First-run onboarding | ✅ | `tests/personas/test_pj_stubs.py::test_pj_newuser_register_to_first_invoice`, `test_wf45_registration` |
| A20 | Auth | ✅ | `test_wf47_jwt_refresh_and_logout`, `test_wf46_password_reset`, `tests/test_auth.py` |
| A21 | Period close + correction | ✅ | `test_pj_wholesale_accountant_period_close` (close is Owner-only; back-dated posting into a closed month rejected), `test_wf44_invoice_amendment_h9` (H9 reverse+re-post). Supersedes skipped WF-20 |
| A22 | Money representation | ✅ | invariant `money.header_totals_identity`, `tests/test_money_contract.py` |
| A23 | Counter POS (D1) | ✅ | `test_wf19_pos_checkout`, `test_pj_retail_owner_normal_day`, `test_pj_retail_sales_staff_boundary` |
| A24 | TDS / TCS (D2) | ✅ | `test_wf34_tcs_on_sales_206c`, `test_wf35_tds_on_purchases_194q`, `test_wf36_tds_tcs_worksheets_reconcile` |
| A25 | Online payment collection (D3, sandbox) | 🚫 | The **live sandbox gateway** flow (`test_wf37_refunds` / `test_wf38_mdr_settlement_reconciliation`) is still skipped — needs real Cashfree/PayU sandbox credentials + `SANDBOX_WEBHOOK_SECRET` in CI, unchanged. `test_wf51_idempotency_contract` covers the replay-safety pattern generically. **`test_wf17_gateway_webhook_capture_and_replay` retargeted 2026-09-13** (was a permanently-skipped D3-blocked placeholder) — its actual scope (signature verification, replay-is-a-no-op, closed-period park+reconcile, cancelled-invoice park+auto-refund) turned out to need no live creds at all and is fully covered under other names; see H10 below and G-8 in `TESTING_STRATEGY.md`. Don't re-block A25 on WF-17 — only the genuine live-gateway E2E (refunds/MDR) remains creds-blocked |
| A26 | OTP login (D4) | ✅ | `tests/test_auth.py::test_otp_*` (hashing, debug gate, max-attempt lockout) + `test_otp_request_throttle_scope_enforced_by_drf` (DRF `otp` 5/min) + `test_wf18_otp_login_and_ratelimit` |

## C. KNOWN LIMITATIONS — route guards (scope revision 2026-09-09b)

| # | Item | Status | Gating test(s) |
|---|---|---|---|
| D6 | Fixed assets | ✅ | `tests/workflows/test_wf_limitation_guards.py` + `tests/personas/test_pj_limitation_guards.py` — route 404s under `ENABLE_FIXED_ASSETS=0`; `test_wf53_*` covers the opt-in path |
| D10 | Bill of Entry | ✅ | same files — route 404s under `ENABLE_BOE=0`; `test_wf57_*` covers the opt-in path |
| D7/D8/D9/D11 | TDS-returns / RCM / composition / plan-limits | ✅ | no separate flag (screened out / out of band). Computation-path regression kept: `test_wf55/56/58_*`; D11 quotas also gated by `tests/test_saas_quotas_and_dlq.py` |

---

## G. Previously-unscoped flows marked SUP

| Flow | Status | Gating test(s) |
|---|---|---|
| Manual journal (create/post/reverse) | ✅ | `tests/workflows/test_wf29_manual_journal.py`, invariant `gl.journals_balanced` |
| Chart of accounts management | ✅ | `test_wf30_chart_of_accounts_management` |
| Financial-year close | ✅ | `test_wf31_financial_year_close` |
| Opening balance entry | ✅ | `test_wf32_opening_balance_entry`, `test_pj_migration_trader_cutover_and_reconcile`, `test_pj_migration_wholesale_large_cutover_with_history` (callable `reports.opening_ties_out`) |
| Bank reconciliation | ✅ | `test_wf33_bank_reconciliation` is **not** skipped and passes (this row was already stale before 2026-09-13 — the module's own header claiming "each is skipped" has been corrected); `test_wf41_bank_statement_import_and_matching` covers AA statement ingest + auto/'human' match + idempotent replay. Idempotent-replay gap closed 2026-09-13: `test_phase3_payments.py::test_g3_bank_statement_bare_recommit_does_not_duplicate_auto_matches` (a bare re-commit with no Idempotency-Key doesn't duplicate `ReconMatch` rows, complementing the existing idempotency-key-path test) |
| Accounting period lifecycle | ✅ | `test_pj_wholesale_owner_multi_godown_day` (open→close), `test_pj_wholesale_accountant_period_close` |
| TCS on sales / TDS on purchase / worksheets | ✅ | WF-34 / WF-35 / WF-36 |
| Refunds / MDR reconciliation | ✅ | `test_wf37_refunds` (skip_gateway=True), `test_wf38_mdr_settlement_reconciliation` (adapter parser) in `tests/workflows/test_wf_extended.py` |
| Advance / on-account payments | ✅ | `test_wf39_advance_payment_on_account` |
| Bad-debt write-off | ✅ | `test_wf40_bad_debt_writeoff` |
| Bank statement import + matching | ✅ | `test_wf41_bank_statement_import_and_matching` |
| Dunning schedule (send = LIM) | ✅ | `test_wf42_dunning_schedule` (schedule + idempotency; send half is a stated LIM) |
| Invoice cancellation | ✅ | `test_wf43_invoice_cancellation` (+ callable `audit.statutory_events_present`) |
| Invoice amendment (H9) | ✅ | `test_wf44_invoice_amendment_h9` (GL delta, AMEND event, stock immutable) |
| RCM | 🟡 | `test_wf55_reverse_charge_purchase` — LIM coverage (D8), not a blocker |
| Composition / CMP-08 | 🟡 | `test_wf56_composition_bill_of_supply` — LIM coverage (D9) |
| Specific / per-unit cess (D9b, retained) | ✅ | `test_wf02_cess.py` (ad-valorem + specific), `test_wf02_cess_defaults_from_product_master` |
| Nil / exempt / non-GST GSTR treatment | ✅ | `test_wf27_gstr1_3b_tie_out` (skipped) → covered by `tests/snapshots/test_gstr1_json.py` + `test_gstr3b_json.py` + `test_pj_trader_owner_normal_day` (GSTR-1) |
| Registration / password reset / JWT / invite / switch-company | ✅ | WF-45 / WF-46 / WF-47 / WF-48 / WF-49 |
| Sandbox / trial expiry cleanup | ✅ | `test_wf50_and_wf59_sandbox_expiry_cascade_erasure` |
| Plan-limit enforcement | ✅ | `test_wf58_plan_limits` (LIM D11 seats/modules) + `tests/test_saas_quotas_and_dlq.py` (completes/storage/API quotas + DLQ replay) |
| Idempotency contract | ✅ | `test_wf51_idempotency_contract` |
| Concurrency / races | 🚫 | `tests/test_concurrency_races.py` is Postgres-only (`postgres` marker); runs in the `invariant-sweep` Postgres job, not local SQLite |
| Audit-trail completeness | ✅ | callable `audit.statutory_events_present` (lifecycle events, wired into WF-43/44); `tests/errors/test_freeze_gate_contracts.py` asserts the `AuditEvent` / `StatutoryDocumentEvent` viewsets expose **no** create/update/delete path **and** `test_complete_cancel_allocate_amend_write_audit_events` (complete / cancel / allocate / amend each write `AuditEvent`) |
| Money-field audit | ✅ | callable `audit.money_mutations_logged` (no-op / blank-field rows) + `tests/test_money_audit_completed.py` (completed sale/purchase line amend writes `MoneyFieldAudit` for recomputed `grand_total`) |
| Document numbering gap-free | ✅ | callable `numbering.sequences_intact` (Rule 46(b) consecutive serials), wired into WF-52 + `tests/test_invariants_smoke.py` (incl. a gap-detection red-then-green test) |
| Report cross-reconcile | ✅ | callable `reports.cross_reconcile` (TB balanced, P&L == TB income−expense, balance-sheet equation) wired into WF-01 / WF-04 + smoke |
| File assets — auth / path traversal | ✅ | `tests/errors/test_freeze_gate_contracts.py` — tenant-scoped download (cross-tenant = 404), `original_name` with `../` / CRLF / quotes sanitised in `Content-Disposition` |
| Rate limiting on auth endpoints | ✅ | A26 — DRF `otp` / `register` / login lockout asserted in `test_auth.py`; throttle classes stay on in `settings_test` |
| Pagination correctness | ✅ | `tests/errors/test_pagination_contract.py` — page-size cap, default size, stable paging (no drops/dupes across boundaries), out-of-range = 404 |
| Security headers | ✅ | `tests/errors/test_freeze_gate_contracts.py` — `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `X-Frame-Options` present; no `Server` version leak |
| Boot-time config validation | ✅ | `tests/errors/test_freeze_gate_contracts.py` — `DJANGO_FAIL_FAST_SECRETS=1` + weak `DJANGO_SECRET_KEY` aborts `django.setup()` with `ImproperlyConfigured` (subprocess) |
| Request-log PII masking | ✅ | `tests/errors/test_freeze_gate_contracts.py` — logged path has no query string / doc number, ids are 12-hex hashes, record carries no body/headers |
| HelpCode registry | ✅ | `test_freeze_gate_contracts.py::test_every_helpcode_constant_is_registered` (no orphan constant) + existing `test_help_resolution.py` / `test_help_codes_live.py` |

## H. Out-of-frame concerns marked SUP

| Concern | Status | Note |
|---|---|---|
| H1 — all frontend behaviour | ⛔ | separate FE workstream (`web/`); `web/e2e/personas/*.spec.ts` is the planned home. Not gated by the backend suite by design |
| H3 — task effects / retry / beat registry | ✅ | effects asserted (eager mode) throughout the WF chains; `test_every_beat_task_dry_runs_eager` invokes each `CELERY_BEAT_SCHEDULE` task once; retry → user-visible state is `test_failed_invoice_pdf_ends_FAILED_and_is_recoverable`. Real-broker ordering remains G-10 / Phase 5 |
| H4 — data-subject export scoping | ✅ | tenancy assertions on the export payload (`tests/tenancy/`) |
| H4 — audit-log immutability (`audit.append_only`) | ✅ | `test_freeze_gate_contracts.py` — audit viewsets have no Create/Update/Destroy mixin; write verbs 403/405 |
| H4 — PII masking in request logs | ✅ | `test_freeze_gate_contracts.py::test_request_log_masks_ids_and_carries_no_body` |
| H5 — HelpCode coverage / error→status mapping | ✅ | `tests/errors/`, `tests/test_help_codes_live.py`, `test_freeze_gate_contracts.py` (no orphan constant) |
| H5 — boot-time config validation | ✅ | `test_freeze_gate_contracts.py::test_fail_fast_secrets_rejects_weak_secret_key` |
| H6 — business-logic edge cases | ✅ | `tests/edge/test_document_edge_cases.py` |
| H7 — report cross-reconcile | ✅ | callable `reports.cross_reconcile` (WF-01/04 + smoke); `reports.pnl_reconciles_to_trial_balance` registered; filtered-report snapshots: date (`test_filtered_report_snapshots`), cost-centre (`test_cost_centre_filtered_pnl`), party + godown (`test_party_and_godown_filtered_reports`) |
| H8 — pagination correctness | ✅ | `tests/errors/test_pagination_contract.py` |
| H9 — SQLite vs Postgres parity | ✅ | `invariant-sweep` + `backend` + `e2e-golden` CI jobs run on Postgres |
| H9 — security headers / CORS / CSRF / CSP | ✅ | `test_freeze_gate_contracts.py` covers Django-emitted headers including CSP (`default-src 'none'`). External pen-test remains G-9 / Phase 5 |
| H10 — webhook signature verification (every inbound) | ✅ | **Was `🚫`, corrected 2026-09-13 — this was never actually D3/creds-blocked.** Both inbound webhooks (Razorpay billing, generic payment-gateway) have signature verification + a forgery test (`tests/errors/test_webhook_and_async_contracts.py`, `tests/test_payment_webhook_adversarial.py`), and `tests/errors/test_webhook_enumeration.py` structurally fails the build if a new, unverified webhook route appears. Don't confuse with A25 above (the live sandbox gateway E2E), which genuinely is creds-blocked |
| H10 — LLM bill extraction failure / injection | ✅ | `tests/errors/test_llm_extraction_failures.py`, `tests/errors/test_llm_injection_guard.py` (D14) |

## Split-lane SaaS / freeze ops (2026-09-16)

Not A-rows; they gate production-SaaS closeout. Human still signs Go/No-Go.

| Item | Status | Gating test(s) |
|---|---|---|
| SaaS dunning ≠ AR dunning | ✅ | `tests/test_saas_dunning_and_recon.py` |
| SaaS Razorpay subscription recon + DLQ | ✅ | `tests/test_saas_dunning_and_recon.py` |
| Chargeback payload without subscription entity ignored | ✅ | `test_chargeback_event_without_subscription_is_ignored` |
| No impersonation API | ✅ | `tests/test_no_impersonation.py`, guard `no_impersonation` |
| ZAP advisory skip without `STAGING_BASE_URL` | ✅ | `test_zap_job_skips_without_staging_url` |
| Table B flags default off in CD/compose | ✅ | guard `freeze_table_b_defaults`, `test_freeze_table_b_defaults_stay_off_in_deploy_artifacts` |
| INVENTORY_STAFF RBAC (V5) | ✅ | `tests/tenancy/test_rbac_matrix.py`, `test_v5_inventory_staff_can_transfer_cannot_journal_or_close`, `test_invite_inventory_staff_applies_capability_defaults`, `tests/tenancy/test_fg2d_ui_caps.py` |
| Dashboard render observation | 🟡 | `tests/test_qos0016_dashboard_budget.py` + `web/e2e-golden/v95-dashboard-budget.spec.ts` (not a signed SLO) |
| Open Q-OS freeze classification (1.3) | ✅ | `docs/ops/QOS_FREEZE_CLASS.md`, `tests/test_qos_freeze_class.py` |
| Freeze baseline SHA (1.2) | ✅ | `scripts/ops/freeze_baseline.py`, `test_freeze_baseline_script_hashes_scope` |
| Cutover recon counts (6.5) | ✅ | `cutover_recon`, `tests/test_cutover_recon.py` |
| V3 mutation-survivor triage | ✅ | `tests/gst/test_mutation_audit_survivors.py`, `test_v3_mutation_audit_job_is_advisory` (mutmut itself stays Linux advisory) |
| Invite UI FG-2d (Manager/Auditor) | ✅ | `tests/tenancy/test_fg2d_ui_caps.py`, `test_invite_auditor_applies_capability_defaults`, `test_invite_manager_applies_capability_defaults` |
| PCI / subprocessors (facts only) | ✅ | `docs/ops/PCI_SCOPE.md`, `docs/ops/SUBPROCESSORS.md`, `test_pci_scope_and_gateway_payload_never_keep_pan` |
| Flag lifecycle (14.7) + D6/D10 default OFF | ✅ | `docs/ops/FLAG_LIFECYCLE.md`, `tests/test_feature_flag_lifecycle.py`, prod/staging env pins, fail-closed FA/BoE getattr |
| Release notes script (C.4) | ✅ | `scripts/ops/release_notes.py`, `test_release_notes_script_buckets_money_tax_stock` |
| Integrations markdown page (9.1) | ✅ | `docs/ops/INTEGRATIONS.md` vs `INTEGRATIONS` tuple |
| Beta archetype checklist (15.1) | ✅ | `docs/pilot/BETA_ARCHETYPE_CHECKLIST.md` |
| Evidence pack + support macros | ✅ | `docs/ops/EVIDENCE_PACK.md`, `docs/ops/SUPPORT_MACROS.md` |
| Onboarding funnel events (15.3) | ✅ | `signup_completed` / `wizard_tax_confirmed` / `wizard_completed`, `tests/test_a08_telemetry.py`, `tests/test_onboarding.py` |
| SaaS cancel vs finance policy (16.4) | ✅ | `docs/ops/REFUND_CANCELLATION.md` vs `company_writes_blocked` |
| CSAT copy + feedback triage | ✅ | `docs/pilot/CSAT.md`, `docs/ops/FEEDBACK_TRIAGE.md` |
| Tenant unique catalog (3.4) | ✅ | `tests/tenancy/test_schema_constraints.py` `_REQUIRED_UNIQUES` + duplicate SKU/GSTIN/UTR IntegrityError |
| Export CSV IDOR (3.10) | ✅ | `test_sales_register_and_files_are_tenant_scoped`, `test_purchase_register_and_export_are_tenant_scoped` |
| PayU fail-closed circuit (9.3) | ✅ | `tests/test_circuit_breaker.py::test_payu_fail_closed_when_circuit_open` |
| Data categories for counsel (16.2) | ✅ | `docs/ops/DATA_CATEGORIES.md` vs `DPDP_POSTURE.md` |
| Static-only CDN (12.5) | ✅ | `docs/ops/CDN.md`, API `Cache-Control: no-store`, `web/nginx.conf` hashed assets immutable |
| Adoption rollup template (17.7) | ✅ | `docs/ops/ADOPTION_ROLLUP.md` |


---

## Open GAPs (SUPPORTED, not yet gated)

1. **Blocked on external / calendar / humans (not LLM-closable):** A25 live-gateway E2E / G3 refunds+MDR (Cashfree/PayU sandbox creds); concurrency races are Postgres-only (`pytest -m postgres` / CI — documented in CONTRIBUTING); mutation audit (Linux CI advisory); H-05 CA filing; V0/V1 flow-catalog flip; unsigned Go/No-Go. G-11b synthetic rehearsal sweep is in `scripts/migration_rehearsal.sh`; a real anonymised dump remains the 95 bar.
2. **Determinism-probe — CLOSED 2026-09-11** (per `scripts/ci_gates/GATE_INVENTORY.md`). Stays advisory in CI until 3 consecutive green runs on `main`, then flip to blocking.

## P0 / P1 issue-register sweep (C15, 2026-09-10)

Parsed `docs/reviews/MASTER_ISSUE_REGISTER.md` (758 issue blocks). **Open P0/P1: 9
— none are code defects.** All are `Deferred — ops owner`, `Accepted (positive)`,
or `Deferred — roadmap`:

| Prio | Item | Kind |
|---|---|---|
| P0 | Pilot Go/No-Go gates unsigned | governance — founder signs `GO_NO_GO.md` |
| P0 | No TLS termination at application edge | infra — reverse proxy / load balancer |
| P1 | No automated backup / restore drill in compose | ops — the **logic** is now tested (`tests/errors/test_backup_restore_drill.py` + `rebuild_*` idempotency in `test_ops_contracts.py`); the **scheduled drill** is a compose/ops task |
| P1 | Phase 1–7 shipped before Phase 0 Go | accepted process note |
| P1 | No pen-test before GA | external security engagement |
| P1 | `GO_NO_GO.md` unsigned (CA/UAT/TLS/backup) | governance |
| P1 | compose backup profile has no scheduled restore automation | ops |
| P1 | CD pushes mutable sha tags without digest pin | DevOps — deploy pipeline |
| P1 | No BizBoard SaaS subscription / entitlement billing | roadmap (out of freeze scope) |

**Conclusion:** every open P0/P1 that is a *code* concern already has a
regression test or is covered by an invariant. The residual 9 are infra,
governance, and roadmap — owned outside the test suite.

## Final verification (2026-09-10 — round 8)

Full battery re-run after the round-7 additions:

| Suite | Command | Result |
|---|---|---|
| Web unit (vitest) | `cd web && npx vitest run` | **279 passed / 42 files** (incl. new `HelpErrorAlert.test.tsx`) |
| Mock e2e (Playwright) | `cd web && npx playwright test` | **70 passed**, 2 pre-existing `[mobile]`-only fails (see below) |
| Golden e2e — deliverable | `personas-golden.spec.ts` | **2 passed** vs LIVE backend |
| Golden e2e — pre-existing | `invoice-golden-path` / `phase1-documents` | still red — pre-existing UI drift, not Freeze Gate scope (see below) |
| Backend Phase 2 gate | `INVARIANTS_STRICT=1 pytest tests/workflows tests/tenancy tests/gst tests/snapshots tests/edge tests/errors tests/matrices tests/personas tests/test_invariants_smoke.py tests/regression` | **179 passed / 11 skipped** |
| Full-suite strict invariant sweep | `INVARIANTS_STRICT=1 pytest -m "not flaky_quarantine"` | **1477 passed / 23 skipped** (9m 54s) |
| Freeze Gate guards | `python scripts/ci_gates/run_guards.py [--selftest]` | **5/5** live + **5/5** fire-on-bad-input (incl. new `ca_tax_parity`) |

**Golden persona spec State-select fix (kept):** `invoice-golden-path.spec.ts` /
`phase1-documents.spec.ts` used `getByLabel('State').fill('Karnataka')`, which
broke when the auth form's State field became a MUI `Select`
(`<div role="combobox">`). Replaced the 4 call sites with
`getByLabel('State').click()` + `getByRole('option', {name:'Karnataka'}).click()`,
and fixed `getByLabel('Password')` → `{exact:true}` (the "Show password" toggle
also matched). These two specs now get *past registration* but still fail
further along on `/inventory/products` `getByRole('button',{name:'Add'})` — the
inventory-products page UI has drifted from the spec. **Flagged as pre-existing
tech debt in non-Freeze-Gate specs; `personas-golden.spec.ts` is the Freeze Gate
deliverable and is green.**

**Mobile-project e2e: two viewport cases are accepted LIM (G-12, 2026-09-15).**
`help.spec.ts` skips UniversalSearch below the `sm` breakpoint (`testInfo.skip`
when `project.name === 'mobile'`). `item-custom-fields.spec.ts` skips the
`/sales/new` heading assertion on Pixel 5 (title under the fixed AppBar).
Chromium covers both journeys. WebKit goldens stay V9 (founder ask).

## §H1 offline-outbox + golden-e2e (2026-09-10 — round 7)

- **Offline draft-outbox conflict/sync** — `web/e2e/personas/offline-outbox-conflict.spec.ts`
  (2, green). Not a "substantial harness" after all: seed
  `localStorage['bizboard:invoice-outbox:v2:<companyId>:<userId>']` with a JSON
  array of `OutboxDraft` via `page.evaluate`. Asserts a normal draft shows
  "Queued to sync", a draft carrying `conflict: {code,message}` shows
  "Rejected: <message>" and is NOT flushable (SR-51 — no auto-retry), and
  discard asks for confirmation first.
- **Golden-e2e persona / tenant-isolation** — `web/e2e-golden/personas-golden.spec.ts`.
  Two freshly-registered OWNER tenants via `playwright.request` against the LIVE
  backend; the real DRF `CompanyScopedViewSet` 404s a cross-tenant read/IDOR,
  B's list excludes A's row, anon → 401/403. **Local run recipe** (the
  `e2e-golden` CI job does the isolated equivalent):
  `cd web && env -u DJANGO_ENV DJANGO_DEBUG=1 DJANGO_SECRET_KEY=<40+ chars>
  OTP_DEBUG_ECHO=0 REDIS_URL= CELERY_TASK_ALWAYS_EAGER=1 npm run test:e2e:golden`
  — `REDIS_URL=` (empty) is required or `config.settings` points the cache at
  `localhost:6379` and `/api/v1/health/` 500s.

## §H1 + coverage ratchet (2026-09-10 — round 6)

- **§H1 validation parity** — `web/e2e/personas/validation-parity.spec.ts`:
  `/sales/new` "Save & Complete" + "Save draft" are disabled with no customer,
  and stay disabled with a customer but no line (mirrors `SalesService.complete`
  "≥ 1 line + customer"). Offline-outbox page renders + empty state.
- **§H1 error rendering** — `web/src/pages/help/HelpErrorAlert.test.tsx` (4
  tests): a BE error envelope → assertive `role="alert"` with the parsed
  message, generic "Validation failed" → joined field details, `message` prop
  wins, empty → nothing. (Envelope parsing itself is `src/api/client.test.ts`.)
- **§H1 i18n parity** — already 100% by `src/i18n/fullParity.test.ts`.
- **Complete-gate visibility (G-complete-gate)** — party + line is not enough
  to Complete when a secondary gate is on. Plan:
  [`COMPLETE_GATE_VISIBILITY_PLAN.md`](COMPLETE_GATE_VISIBILITY_PLAN.md).
  Catalog + index: `web/src/completeGates/`. Cite **CG-NN** (not bullet prose).

  | ID | Gate |
  |---|---|
  | CG-01 | `web/e2e/sales/complete-gates.spec.ts` |
  | CG-02 | `web/e2e-golden/gstin-prompt.spec.ts` |
  | CG-03 | `web/e2e/sales/complete-gates.spec.ts` |
  | CG-04 | `web/src/completeGates/completeBlockers.test.ts` |
  | CG-05 | `web/e2e/sales/complete-gates.spec.ts` |
  | CG-06 | `web/e2e/sales/complete-gates.spec.ts` |
  | CG-07 | `web/e2e/sales/complete-gates.spec.ts` |
  | CG-08 | `web/e2e/sales/complete-gates.spec.ts` |
  | CG-09 | `web/e2e/sales/complete-gates.spec.ts` |
  | CG-10 | `web/e2e/sales/complete-gates.spec.ts` |
  | CG-11 | `web/e2e-golden/complete-gates-golden.spec.ts` |
  | CG-12 | `web/src/completeGates/clickFailContracts.test.ts` |
  | CG-13 | `web/src/components/billing/DocumentEditorShell.test.tsx` |
  | CG-14 | `web/src/completeGates/clickFailContracts.test.ts` |
  | CG-15 | `web/e2e/purchases/purchase-complete-gates.spec.ts` |
  | CG-16 | `web/e2e/purchases/purchase-batch-complete.spec.ts` |
  | CG-17 | `web/e2e/purchases/purchase-complete-gates.spec.ts` |
  | CG-18 | `web/src/completeGates/completeBlockers.test.ts` |
  | CG-19 | `web/e2e/purchases/purchase-complete-gates.spec.ts` |
  | CG-20 | `web/e2e/purchases/purchase-complete-gates.spec.ts` |
  | CG-21 | `web/e2e-golden/complete-gates-golden.spec.ts` |
  | CG-22 | `web/e2e-golden/complete-gates-golden.spec.ts` |
  | CG-23 | `web/e2e-golden/complete-gates-golden.spec.ts` |
  | CG-24 | `web/src/components/billing/DocumentEditorShell.test.tsx` |
  | CG-25 | `web/e2e/notes/note-preview-complete.spec.ts` |
  | CG-26 | `web/e2e/notes/note-preview-complete.spec.ts` |
  | CG-27 | `web/e2e/notes/note-preview-complete.spec.ts` |
  | CG-28 | `web/e2e/pos/pos-complete-gates.spec.ts` |
  | CG-29 | `web/e2e/pos/pos-complete-gates.spec.ts` |
  | CG-30 | `web/e2e/pos/pos-complete-gates.spec.ts` |
  | CG-31 | `web/e2e/pos/pos-complete-gates.spec.ts` |
  | CG-32 | `web/src/components/billing/DocumentEditorShell.test.tsx` |
  | CG-33 | `web/src/components/billing/DocumentEditorShell.test.tsx` |
  | CG-34 | `web/e2e/sales/extra-complete-gates.spec.ts` |
  | CG-35 | `web/e2e/sales/extra-complete-gates.spec.ts` |
  | CG-36 | `web/e2e/sales/extra-complete-gates.spec.ts` |
  | CG-37 | `web/src/completeGates/clickFailContracts.test.ts` |

- **`core/tasks.py` branch coverage** — `backend/tests/test_core_tasks_coverage.py`
  (6): `send_email_notification` in-flight-lock skip / SENT skip / prod
  console-backend fail-closed / locmem success; `prune_help_events_task` +
  `prune_idempotency_records_task` (keeps recent + fresh-in-flight, drops old +
  stale-in-flight).
- **Backfill/reconcile idempotency** — `backfill_accounting_postings --dry-run`
  and `reconcile_gateway_captures` added to the read-only-scan check.
- **CA sign-off wiring** — new `scripts/ci_gates/guards/guard_ca_tax_parity.py`:
  CI fails if a CA-signed scenario (F1–F8) loses its automated case in
  `tax_parity_cases.json` or the checklist stops referencing the fixture. In
  `run_guards.py` + `GATE_INVENTORY.md`.

## FE regressions fixed (2026-09-10 — round 5)

Ran the full Playwright suite; the 6 failures were all pre-existing on `main`.
Fixed:

- **`a11y.spec.ts:20` (dashboard axe, serious)** — two real WCAG fixes:
  (1) WCAG 1.3.1 — the drawer nav rendered `ListItemButton` (→ `<a>`/`<div>`)
  as a *direct* child of `<ul>`; `src/layouts/AppShell.tsx` now wraps each
  `NavSection` in `<ListItem disablePadding>`. (2) `aria-progressbar-name` —
  the `LoadingState` / HomePage `CircularProgress` had no accessible name;
  `aria-label={t('common.loading')}` added (`src/components/PageState.tsx`,
  `src/pages/HomePage.tsx`).
- **`item-custom-fields.spec.ts` ×6** — `MOCK_FLAGS` in
  `src/config/featureFlags.ts` still had `item_custom_fields_v2: false` after the
  feature graduated; the mock company already ships `itemCustomFieldDefs`. Flag
  flipped on for the mock backend.
- **`smoke.spec.ts:22`** — stale: it asserted a VIEWER lands on the
  "limited access" landing, but `/offline-outbox` (visible to any user) is now a
  reachable first-nav path, so `HomePage` redirects there. Test updated to the
  robust contract: authenticated, no error boundary, no sale/purchase CTA.
- **i18n key parity** — already fully covered by `src/i18n/fullParity.test.ts`
  (both directions). No new work.

## Now covered (2026-09-10 — round 4)

- **FE persona role boundaries RUN GREEN** — `web/e2e/personas/role-boundaries.spec.ts`
  executed via Playwright (Chromium): **10/10 passing** across OWNER / SALES /
  ACCOUNTANT / VIEWER. (Pre-existing `smoke.spec.ts:22` VIEWER-landing failure is
  a `main` issue, not introduced here.)
- **WF-GRN** — `tests/workflows/test_wf_grn.py`: goods-receipt → complete
  (accepted qty into stock) → convert to purchase bill (AP + ITC, GL balanced);
  cancel reverses received stock. Closes the 0%-covered `purchases/grn_service.py`.
- **Purchase-bill PDF text snapshot** — `test_gst_purchase_bill_pdf_text_snapshot`
  (`render_gst_purchase_bill`, pypdf, FY-code redacted) → baseline
  `gst_purchase_bill_pdf_text.json`. Closes the 0%-covered `purchases/pdf.py`.

## Now covered (2026-09-10 — round 3)

- **§H3 e-invoice submit failure** — `submit_einvoice_async` persists a visible
  `einvoice_status=FAILED` + human-readable `einvoice_error`; a retry returns a
  structured result, never an unhandled crash. `tests/errors/test_webhook_and_async_contracts.py`.
- **§H8 bulk action scope + idempotency** — `bulk_accept_exact` touches only
  EXACT-class rows; re-run accepts 0. Same file.
- **§H10 SaaS billing (Razorpay) webhook** — missing / wrong `X-Razorpay-Signature`
  → 400; valid → accepted; replayed event id → no duplicate `ProcessedWebhookEvent`.
  Same file.
- **§H5 prod config** — `DJANGO_ENV=production` without `EMAIL_HOST`, or with
  localhost-only `CORS_ALLOWED_ORIGINS`, aborts `django.setup()`.
  `tests/errors/test_freeze_gate_contracts.py`.
- **Docker deploy contract** — `docker-compose.yml` API service healthchecks
  `/api/v1/health/` and every `build:` context has a Dockerfile; a real container
  smoke runs under `DOCKER_SMOKE=1`. `tests/errors/test_ops_contracts.py`.
- **FE persona role boundaries** — `web/e2e/personas/role-boundaries.spec.ts`
  now covers OWNER / SALES / ACCOUNTANT / VIEWER (added `mockAccountantUser` +
  `loginAsSales` / `loginAsAccountant`). Runs in the `e2e` CI job.

## Now covered (2026-10-13 — sales returns fix plan)

Sales Returns (`/sales/returns`), see `SALES_RETURNS_FIX_PLAN.md` (SRF-01 .. SRF-15).

| Behaviour | Status | Tests |
|---|---|---|
| A return lists only its own invoice's returns (`sales_invoice` / `salesInvoice`), plus `q`, status and date filters | ✅ | `backend/tests/test_sales_returns_fix.py` |
| A named invoice line keeps its price and discount on the return and the auto credit note, even if the client omits them | ✅ | `backend/tests/test_sales_returns_fix.py` |
| Same product on two invoice lines: the return restores that line's own lot and reverses that line's cost; cancel undoes the same lot | ✅ | `backend/tests/test_sales_returns_fix.py` |
| Mixed SELLABLE + DAMAGED return posts exact COGS reversal and exact scrap | ✅ | `backend/tests/test_sales_returns_fix.py`, `backend/tests/test_item_godown_expiry.py` |
| Units already credited by a standalone credit note are not returnable; the refusal is early, names the note, and changes nothing | ✅ | `backend/tests/test_sales_returns_fix.py` |
| `GET /sales/invoices/:id/returnable-lines/` matches what Complete will accept | ✅ | `backend/tests/test_sales_returns_fix.py` |
| `POST /sales/returns/preview-totals/` equals the credit note actually issued and writes nothing | ✅ | `backend/tests/test_sales_returns_fix.py` |
| Cancel reverses stock, the credit note and the invoice status; a cancelled return shows no credit-note link | ✅ | `backend/tests/test_sales_returns_fix.py` |
| Staff can save a draft but not complete or cancel | ✅ | `backend/tests/test_sales_returns_fix.py`, `web/src/pages/sales/SalesReturnsPage.test.tsx` |
| Serial lines: pick sold serials, quantity follows the picks, already-returned serials are not offered | ✅ | `web/src/pages/sales/SalesReturnsPage.test.tsx`, `web/src/components/billing/invoiceSourceLines.test.ts`, `web/src/pages/purchases/PurchaseReturnsPage.test.tsx` |
| Draft lifecycle: resume, complete, delete, cancel; invoice switch and Discard never leave an orphan draft | ✅ | `web/src/pages/sales/SalesReturnsPage.test.tsx` |
| GST Guard block on Complete (dialog and list row) with Owner/Manager override | ✅ | `web/src/pages/sales/SalesReturnsPage.test.tsx` |
| Complete and Cancel refresh returns, invoices, credit notes, stock, products and customers | ✅ | `web/src/pages/sales/SalesReturnsPage.test.tsx` |
| Older (untagged) and challan-origin invoices restore the lot of the line named | ✅ | `backend/tests/test_sales_returns_fix.py` |
| A second partial return never pushes a FIFO cost layer above its original quantity; cancel undoes the right layer | ✅ | `backend/tests/test_sales_returns_fix.py` |
| A part-credited invoice that is fully returned becomes RETURNED; cancelling one of two returns reopens it | ✅ | `backend/tests/test_sales_returns_fix.py` |
| Two returns completing together cannot return more than was sold; complete racing cancel stays consistent | ⚠️ runs only on Postgres | `backend/tests/test_sales_returns_concurrency_postgres.py` (`-m postgres`) |
| Purchase returns: server headroom (base units, standalone credit notes), returned serials, filters, links, draft lifecycle, cancel | ✅ | `backend/tests/test_purchase_returns_fix.py`, `web/src/pages/purchases/PurchaseReturnsPage.test.tsx` |
| Returns screens end to end on desktop and phone | ✅ | `web/e2e/sales/returns.spec.ts` |
| The live total is rate limited and capped at 200 lines | ✅ | `backend/tests/test_sales_returns_fix.py` |
| "Return goods" on an invoice opens Sales Returns (not Credit Notes); hidden once fully returned | ✅ | `web/src/pages/sales/InvoiceDetailPage.test.tsx` |

## Now covered (2026-10-12 — bill upload review v2)

Sales and purchase bill upload (`/sales/bill-upload`, `/purchases/bill-upload`), see `UPLOAD_SALES_BILL_REVIEW.md` sections 22-25.

| Behaviour | Status | Tests |
|---|---|---|
| A bill over 50 lines keeps every row through edit and commit (both directions) | ✅ | `backend/tests/test_sales_bill_import.py` |
| A line with a problem is never dropped silently; commit lists every bad row | ✅ | `backend/tests/test_sales_bill_import.py`, `web/src/pages/imports/BillUploadPage.test.tsx` |
| Reviewed prices are kept below the customer's price list (Owner/Manager), others are told why | ✅ | `backend/tests/test_sales_bill_import.py` |
| Importing needs Import AND the right to create the document (API + UI) | ✅ | `backend/tests/test_sales_bill_import.py`, `web/src/utils/permissions.test.ts` |
| Sales and purchase layouts no longer share a template | ✅ | `backend/tests/test_sales_bill_import.py` |
| Customers/suppliers: exact match only, inactive/blocked/walk-in never bound | ✅ | `backend/tests/test_sales_bill_import.py` |
| Draft carries terms, source bill number, file; undo while still a draft | ✅ | `backend/tests/test_sales_bill_import.py`, `web/src/pages/imports/bill/ImportedBillNotice.test.tsx` |
| Review screen: autosave, resume from `?job=`, side-by-side bill with row highlight, add/delete rows | ✅ | `web/src/pages/imports/BillUploadPage.test.tsx` |
| Two simultaneous commits make one draft (needs PostgreSQL) | ⚠️ runs only on Postgres | `backend/tests/test_sales_bill_import.py` (`-m postgres`) |

## Now covered (2026-09-10 — round 2)

- **WF-15** structured-CSV purchase-bill upload + Idempotency-Key commit replay
  (WF-14 sales-bill = documented redirect). `tests/workflows/test_wf_todo_stubs.py`.
- **Recompute-command idempotency** — `rebuild_stock_balances`,
  `rebuild_running_cost`, `backfill_uqc` run twice = identical; `--dry-run` on
  `backfill_missing_postings` / `reconcile_dual_fulfillment_and_cost` is
  read-only. `tests/errors/test_ops_contracts.py`.
- **celery-beat registry** — every `CELERY_BEAT_SCHEDULE` task is importable +
  callable. Same file.
- **Async task failure is user-visible** — a failed invoice PDF ends `FAILED`
  (not stuck / not 500) and `regenerate-pdf` recovers it.
  `tests/errors/test_async_task_state.py`.
- **Cost-centre filtered P&L snapshot** — `report_cost_centre_filtered.json`.
- **`money.changes_audited`** — WF-44 now asserts the "Completed document edited"
  `AuditEvent` captured the before/after `grand_total` and `amend: true`.
- **`reports.cross_reconcile`** wired into WF-19 (POS) and WF-29 (manual journal)
  too; its P&L check now uses all-time bounds (was current-FY, false-positived on
  a prior-FY-dated POS sale).
- **Numbering under concurrency** — `tests/test_concurrency_races.py::
  test_concurrent_invoice_numbering_no_duplicate` (`postgres` marker, runs in
  CI's Postgres job).
- **Export → wipe → restore round-trip** keeps rows + `assert_all_invariants`
  clean. `tests/errors/test_backup_restore_drill.py`.

## Now covered (2026-09-10 close-out)

- `audit.append_only` + "every CRUD mutation writes an `AuditEvent`" —
  `tests/errors/test_freeze_gate_contracts.py` (structural on `CompanyScopedViewSet`
  + live create/update/delete on `/customers/`).
- Docker `/health` + `/metrics` token gate + recompute-command idempotency
  (`rebuild_running_cost` twice = no-op) + feature-flag kill-switch —
  `tests/errors/test_ops_contracts.py`.
- Party + godown filtered report snapshots —
  `tests/snapshots/test_exports_and_filtered_reports.py::test_party_and_godown_filtered_reports`.
- Diff-coverage gate flipped to **blocking, ≥80% on changed lines** in
  `.github/workflows/ci.yml`.
- FE persona counterparts — `web/e2e/personas/role-boundaries.spec.ts`
  (OWNER + VIEWER + SALES + ACCOUNTANT live; G-4 closed).

Skipped chains that are now **covered elsewhere** and left as unskipped
structural pointers (no `assert True`): WF-20 → PJ-WHOLE-ACCT + WF-44;
WF-23/24/25 → PJ-TRADER-IMPORT (+ `test_cr_016_duplicate_opening_stock_file_rejected`);
WF-17 → webhook signature/replay files.

**WF-11 / WF-13 / WF-14 / WF-15 / WF-18 / WF-45-verify / WF-46-ratelimit are
implemented** (2026-09-15: WF-14 sales-bill CSV idempotency; WF-45-verify is a
LIM pin that register has no email-verify route). Remaining genuine skips in
`test_wf_extended.py`: **WF-37/38 only** (D3 sandbox credentials).

---

## CFT index (CROSS_FLOW_TEST_CHECKLIST.md)

Cite these **CFT-NNN** ids from Graph-2 results. Review-gap cases CFT-114–120
are gated in `tests/test_cft_cross_flow.py` (CFT-120 concurrent twin is
postgres `tests/test_concurrency_races.py`). Unique assertions that were only
loosely mapped to a sibling WF/PJ test are gated in
`tests/test_cft_checklist.py`. CFT-078 / CFT-093 stay LIM / creds-blocked as
named.

| Id | Gate |
|---|---|
| CFT-NID-01 | `projection.operational_sales_not_collapsed_into_open_receivables` + `test_status_semantics.test_reporting_includes_returned_insights_exclude` |
| CFT-001 | `tests/test_cft_checklist.py::test_cft_001_012_046_047_072_draft_does_not_contaminate_committed_state` |
| CFT-002 | `test_wf01_sale_intrastate` / `test_status_machines.test_complete_assigns_number_and_status` |
| CFT-003 | `test_status_machines.test_completed_invoice_audited_edit_allows_line_change` (H9-A) |
| CFT-004 | `test_status_machines.test_cancel_completed_sale_restores_stock` / `test_wf43_invoice_cancellation` |
| CFT-005 | `test_wf03_sales_return` / `test_status_machines.test_fully_returned_invoice_marked_returned` |
| CFT-006 | `tests/test_cft_checklist.py::test_cft_006_008_partial_multiline_return_only_touches_that_line` |
| CFT-007 | `tests/test_cft_checklist.py::test_cft_007_cancel_sales_return_restores_sale` |
| CFT-008 | `tests/test_cft_checklist.py::test_cft_006_008_partial_multiline_return_only_touches_that_line` |
| CFT-009 | `tests/matrices/test_company_settings_matrix.py::test_negative_stock_policy` |
| CFT-010 | `test_wf51_idempotency_contract` / `test_cannot_complete_twice` |
| CFT-011 | `test_wf19_pos_checkout` / `test_pj_retail_owner_normal_day` |
| CFT-012 | `tests/test_cft_checklist.py::test_cft_001_012_046_047_072_draft_does_not_contaminate_committed_state` |
| CFT-013 | `test_wf04_purchase` complete |
| CFT-014 | `tests/test_cft_checklist.py::test_cft_014_016_026_030_cancel_purchase_and_purchase_return` |
| CFT-015 | `test_wf05_purchase_return` |
| CFT-016 | `tests/test_cft_checklist.py::test_cft_014_016_026_030_cancel_purchase_and_purchase_return` |
| CFT-017 | `tests/test_cft_checklist.py::test_cft_017_purchase_amend_after_sale_consumed_keeps_sale_cogs` |
| CFT-018 | `test_wf_grn_cancel_reverses_received_stock` / `test_wf_grn_cancel_blocked_in_hard_closed_period` |
| CFT-019 | `test_wf01_sale_intrastate` AR / `LedgerService.sales_invoice_outstanding` |
| CFT-020 | `test_partial_allocation_reduces_outstanding` / `test_wf39_advance_payment_on_account` |
| CFT-021 | `test_bb_000651_unallocate_reopens_invoice_and_reverses_je` |
| CFT-022 | `test_public_pay_shows_live_outstanding_after_return` / G-17 |
| CFT-023 | `tests/test_cft_checklist.py::test_cft_023_038_045_053_070_100_cancel_reverses_and_retires_number` |
| CFT-024 | `test_partial_allocation_reduces_outstanding` |
| CFT-025 | `tests/test_cft_checklist.py::test_cft_025_over_allocation_then_excess_to_other_invoice_or_advance` |
| CFT-026 | `tests/test_cft_checklist.py::test_cft_014_016_026_030_cancel_purchase_and_purchase_return` |
| CFT-027 | `tests/test_cft_checklist.py::test_cft_027_028_031_032_ap_allocate_reverse_and_over_alloc` |
| CFT-028 | `tests/test_cft_checklist.py::test_cft_027_028_031_032_ap_allocate_reverse_and_over_alloc` |
| CFT-029 | `tests/test_cft_checklist.py::test_cft_029_returned_purchase_with_residual_dn_stays_in_ap` |
| CFT-030 | `tests/test_cft_checklist.py::test_cft_014_016_026_030_cancel_purchase_and_purchase_return` |
| CFT-031 | `tests/test_cft_checklist.py::test_cft_027_028_031_032_ap_allocate_reverse_and_over_alloc` |
| CFT-032 | `tests/test_cft_checklist.py::test_cft_027_028_031_032_ap_allocate_reverse_and_over_alloc` |
| CFT-033 | `inventory.balance_equals_movements` + sale complete |
| CFT-034 | `test_wf04_purchase` complete stock |
| CFT-035 | `test_wf03_sales_return` / `test_wf05_purchase_return` |
| CFT-036 | `test_wf22_stock_adjustment_writeoff` |
| CFT-037 | `test_wf21_stock_transfer_between_godowns` |
| CFT-038 | `tests/test_cft_checklist.py::test_cft_023_038_045_053_070_100_cancel_reverses_and_retires_number` |
| CFT-039 | `test_cr_016_duplicate_opening_stock_file_rejected` |
| CFT-040 | `tests/test_cft_checklist.py::test_cft_040_042_048_reserved_available_agrees_across_surfaces` |
| CFT-041 | `test_cr062_inventory_summary_uses_movements_and_flags_drift` |
| CFT-042 | `tests/test_cft_checklist.py::test_cft_040_042_048_reserved_available_agrees_across_surfaces` |
| CFT-043 | `tests/test_cft_checklist.py::test_cft_043_044_stock_movement_recon_and_return_surfaces` |
| CFT-044 | `tests/test_cft_checklist.py::test_cft_043_044_stock_movement_recon_and_return_surfaces` |
| CFT-045 | `tests/test_cft_checklist.py::test_cft_023_038_045_053_070_100_cancel_reverses_and_retires_number` |
| CFT-046 | `tests/test_cft_checklist.py::test_cft_001_012_046_047_072_draft_does_not_contaminate_committed_state` |
| CFT-047 | `tests/test_cft_checklist.py::test_cft_001_012_046_047_072_draft_does_not_contaminate_committed_state` |
| CFT-048 | `tests/test_cft_checklist.py::test_cft_040_042_048_reserved_available_agrees_across_surfaces` |
| CFT-049 | `test_wf01` / snapshots sales report |
| CFT-050 | `tests/test_cft_checklist.py::test_cft_050_067_073_nid01_returned_counts_in_money_not_insights` |
| CFT-051 | `test_h9_price_amend_keeps_sale_peel_cogs` / `test_a11_a12_stock_cost` |
| CFT-052 | `tests/test_cft_checklist.py::test_cft_006_008_partial_multiline_return_only_touches_that_line` |
| CFT-053 | `tests/test_cft_checklist.py::test_cft_023_038_045_053_070_100_cancel_reverses_and_retires_number` |
| CFT-054 | `tests/test_cft_checklist.py::test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding` |
| CFT-055 | `test_h9_price_amend_keeps_sale_peel_cogs` (sale COGS vs live price) |
| CFT-056 | `tests/test_cft_checklist.py::test_cft_056_057_059_date_moves_period_and_later_return_stays_put` |
| CFT-057 | `tests/test_cft_checklist.py::test_cft_056_057_059_date_moves_period_and_later_return_stays_put` |
| CFT-058 | `tests/test_cft_checklist.py::test_cft_058_102_closed_blocks_amend_soft_closed_allows_cancel` |
| CFT-059 | `tests/test_cft_checklist.py::test_cft_056_057_059_date_moves_period_and_later_return_stays_put` |
| CFT-060 | `tests/test_cft_checklist.py::test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding` |
| CFT-061 | `tests/test_cft_checklist.py::test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding` |
| CFT-062 | `tests/test_cft_checklist.py::test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding` |
| CFT-063 | `tests/test_cft_checklist.py::test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding` |
| CFT-064 | `tests/test_cft_checklist.py::test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding` |
| CFT-065 | `tests/test_cft_checklist.py::test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding` |
| CFT-066 | `tests/test_cft_checklist.py::test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding` |
| CFT-067 | `tests/test_cft_checklist.py::test_cft_050_067_073_nid01_returned_counts_in_money_not_insights` |
| CFT-068 | `tests/test_cft_checklist.py::test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding` |
| CFT-069 | `tests/test_cft_checklist.py::test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding` |
| CFT-070 | `tests/test_cft_checklist.py::test_cft_023_038_045_053_070_100_cancel_reverses_and_retires_number` |
| CFT-071 | `tests/test_cft_checklist.py::test_cft_071_099_amend_updates_once_and_writes_money_audit` |
| CFT-072 | `tests/test_cft_checklist.py::test_cft_001_012_046_047_072_draft_does_not_contaminate_committed_state` |
| CFT-073 | `tests/test_cft_checklist.py::test_cft_050_067_073_nid01_returned_counts_in_money_not_insights` |
| CFT-074 | `test_products_import` / `test_imports` |
| CFT-075 | `test_cr_016_duplicate_opening_stock_file_rejected` |
| CFT-076 | `test_void_opening_stock_import_allows_reimport` |
| CFT-077 | `test_duplicate_webhook_one_receipt` / `test_wf17_gateway_webhook_capture_and_replay` |
| CFT-078 | LIM — voice-entry not in freeze |
| CFT-079 | `test_wf01_sale_intrastate` CGST+SGST |
| CFT-080 | `test_wf02_sale_interstate_with_cess` IGST |
| CFT-081 | `test_wf56_composition_bill_of_supply` / NON_GST |
| CFT-082 | `tests/test_cft_checklist.py::test_cft_082_cess_partial_return_reverses_only_returned_qty` |
| CFT-083 | `test_wf55_reverse_charge_purchase` |
| CFT-084 | `tests/test_cft_checklist.py::test_cft_084_composition_blocked_from_gstr1_cmp08_ok` |
| CFT-085 | `tests/test_cft_checklist.py::test_cft_085_itc_ineligible_excluded_from_gstr3b_claim` |
| CFT-086 | `test_discount_percent_over_100_rejected` |
| CFT-087 | `test_wf34_tcs_on_sales_206c` |
| CFT-088 | `test_wf35_tds_on_purchases_194q` |
| CFT-089 | `tests/test_cft_checklist.py::test_cft_089_explicit_tcs_logs_both_rate_and_entered_amount` |
| CFT-090 | `tests/test_cft_checklist.py::test_cft_090_tcs_reverses_on_return_in_worksheet` |
| CFT-091 | `test_wf39_advance_payment_on_account` |
| CFT-092 | `tests/test_cft_checklist.py::test_cft_092_void_receipt_is_not_a_credit_note` |
| CFT-093 | 🚫 D3 live gateway refund/MDR (`test_wf37` / `test_wf38` skipped — creds) |
| CFT-094 | `test_wf40_bad_debt_writeoff` |
| CFT-095 | `test_wf41_bank_statement_import_and_matching` |
| CFT-096 | `test_g3_bank_statement_bare_recommit_does_not_duplicate_auto_matches` |
| CFT-097 | `test_concurrent_invoice_numbering_no_duplicate` |
| CFT-098 | `tests/test_cft_checklist.py::test_cft_023_038_045_053_070_100_cancel_reverses_and_retires_number` |
| CFT-099 | `tests/test_cft_checklist.py::test_cft_071_099_amend_updates_once_and_writes_money_audit` |
| CFT-100 | `tests/test_cft_checklist.py::test_cft_023_038_045_053_070_100_cancel_reverses_and_retires_number` |
| CFT-101 | H9 amend open period `test_wf44_invoice_amendment_h9` |
| CFT-102 | `tests/test_cft_checklist.py::test_cft_058_102_closed_blocks_amend_soft_closed_allows_cancel` |
| CFT-103 | `tests/tenancy/test_rbac_matrix.py` / `test_completed_invoice_amend_requires_owner_confirm` |
| CFT-104 | `test_wf58_plan_limits` |
| CFT-105 | `test_cannot_retrieve_other_companys_invoice` / `tests/tenancy/` |
| CFT-106 | `test_gst_tax_invoice_pdf_text_snapshot` |
| CFT-107 | `tests/test_cft_checklist.py::test_cft_107_pdf_snapshot_differs_from_live_outstanding_after_return` |
| CFT-108 | `test_sales_register_export_csv_snapshot` |
| CFT-109 | `test_concurrency_races.test_concurrent_stock_oversell_blocked` |
| CFT-110 | `test_concurrency_races.test_concurrent_payment_over_allocation_blocked` |
| CFT-111 | `test_wf51_idempotency_contract` |
| CFT-112 | `tests/test_cft_checklist.py::test_cft_112_product_search_is_company_scoped` |
| CFT-113 | `test_wf06_quotation_to_invoice` |
| CFT-114 | `tests/test_cft_cross_flow.py::test_cft_114_cancel_so_after_challan_does_not_orphan_reservation` |
| CFT-115 | `tests/test_cft_cross_flow.py::test_cft_115_partial_quotation_convert_remainder_still_convertible` + `ConvertQuotationDialog` / `quotationConvert` |
| CFT-116 | `tests/test_cft_cross_flow.py::test_cft_116_live_irn_blocks_line_amend` + `web/src/utils/einvoiceLock.test.ts` + EinvoiceEwayPanel + InvoiceDetailPage live-IRN Edit |
| CFT-117 | `tests/test_a07_dunning.py::test_auto_credit_hold_blocks_severe_overdue_customer_with_no_credit_limit` + CreditHoldChip |
| CFT-118 | `tests/test_cft_cross_flow.py::test_cft_118_hold_releases_after_return_or_pay_residual_dn_keeps_hold` + `test_cft_118_payment_releases_hold` + `test_cft_118_residual_dn_keeps_hold` + CollectionAttentionCard chip-gone |
| CFT-119 | `tests/test_cft_cross_flow.py::test_cft_119_return_restores_same_batch_and_serial` + `test_cft_119_pos_return_restores_same_batch` (POS batch + serial) |
| CFT-120 | `tests/test_cft_cross_flow.py::test_cft_120_stale_amend_revision_conflicts` + `test_cft_120_amend_without_revision_is_conflict` + `test_concurrency_races.test_cft_120_concurrent_same_invoice_amend_one_wins` |
| CFT-121 | `tests/test_cft_checklist.py::test_cft_121_125_sales_lifecycle_surfaces_agree` |
| CFT-122 | `tests/test_cft_checklist.py::test_cft_121_125_sales_lifecycle_surfaces_agree` |
| CFT-123 | `tests/test_cft_checklist.py::test_cft_121_125_sales_lifecycle_surfaces_agree` |
| CFT-124 | `tests/test_cft_checklist.py::test_cft_121_125_sales_lifecycle_surfaces_agree` + **CFT-NID-01** |
| CFT-125 | `tests/test_cft_checklist.py::test_cft_121_125_sales_lifecycle_surfaces_agree` |

## FMEA closures (2026-10-03)

These rows do not add a SUPPORTED feature and do not flip a frozen flag on.
`test_fmea2_008_audit_row_once` and `test_fmea2_006_cloud_send_same_phone` are
green, so those two SUPPORTED-path rows are gated. Grant and dark rows stay
out of freeze scope.

| Finding | Freeze posture | Status | Gating test |
|---|---|---|---|
| FMEA-008 | SUPPORTED complete and cancel audit | ✅ gated | `test_fmea2_008_audit_row_once`, `test_fmea2_008_audit_failure_rolls_back` |
| FMEA-006 | Pilot share stays `wa.me`. Cloud check is dormant while `ENABLE_WHATSAPP_CLOUD=0` | ✅ gated | `test_fmea2_006_cloud_send_same_phone` |
| FMEA-014 | GSTN JSON stays off. Export needs env and company flag | 🚫 out of freeze (tightens a frozen-off export) | `test_fmea2_014_gstn_needs_env_and_flag` |
| FMEA-010 | Trial text and lock. Dict is not widened | 🚫 out of freeze | `test_fmea2_010_trial_plan_lock` |
| FMEA-001, FMEA-011 | Payroll and fixed assets. Not a freeze expansion | 🚫 out of freeze | `test_fmea2_001_pay_run_cancel_refuses_while_books_off`, `test_fmea2_011_skipped_month_keeps_error` |
| FMEA-007, FMEA-004, FMEA-005, FMEA-009, FMEA-012, FMEA-013 | Grant lanes. Off on the frozen trial plan | 🚫 out of freeze | `test_fmea2_007`, `test_fmea2_004`, `test_fmea2_005`, `test_fmea2_009`, `test_fmea2_012`, `test_fmea2_013` |
| FMEA-002, FMEA-003 | Dev command. Staging and production refused | 🚫 out of freeze | `test_fmea2_002_demo_refuses_staging`, `test_fmea2_003_demo_company_is_explicit` |
| FMEA-015, FMEA-016, FMEA-017 | Shopify and AA. Off on the frozen host | 🚫 out of freeze | `test_fmea2_015_shopify_holds_large_delta`, `test_fmea2_016_shopify_domain_unique`, `test_fmea2_017_aa_live_fetch_closed` |

## Money In hardening (2026-10-11)

No new SUPPORTED feature and no frozen flag changes. These rows record what now gates
the customer receipt screen. Tracked as QOS-0118; the plan is
[`MONEY_IN_IMPLEMENTATION_PLAN.md`](../MONEY_IN_IMPLEMENTATION_PLAN.md).

| Behaviour | Status | Gating test |
|---|---|---|
| Void needs a reason (3 to 500 characters), stored as `void_reason`, `voided_by`, `voided_at`, and in the audit event | ✅ gated | `test_money_in_receipts.py::test_void_requires_a_reason_on_the_server`, `::test_void_stores_structured_audit_fields_and_event` |
| Void is refused for a bank-matched receipt and for a receipt counted in a closed till | ✅ gated | `::test_void_blocked_when_matched_to_a_bank_line`, `::test_void_blocked_when_counted_in_a_closed_till` |
| Void restores invoices after a settlement discount or a partial reallocation | ✅ gated | `::test_void_restores_invoice_after_a_settlement_discount`, `::test_void_of_a_partly_reallocated_receipt_reverses_every_live_allocation` |
| List filters validate input (400, not 500) and never cross tenants | ✅ gated | `::test_invalid_filter_values_are_a_400_not_a_500`, `::test_filters_never_leak_another_tenants_receipts` |
| Totals cover every page and leave out voided, refunded and bounced receipts | ✅ gated | `::test_summary_covers_every_page_and_excludes_dead_money`, `::test_collected_total_ties_to_the_cash_ledger_and_customer_ledger` |
| Walk-in customer cannot hold an advance (manual receipt and bank-line receipt) | ✅ gated | `::test_walk_in_receipt_without_allocation_is_refused_by_the_api`, `::test_bank_line_receipt_refuses_a_walk_in_customer_and_accepts_a_named_one` |
| Receipt and invoice allocation commit together; future dates refused | ✅ gated | `::test_failed_atomic_allocation_leaves_no_receipt_behind`, `::test_create_rejects_a_future_receipt_date_but_allows_today_and_the_past` |
| Voucher PDF in A4 and thermal, English and Hindi (shaped Devanagari), voided stamp | ✅ gated | `::test_voucher_pdf_a4_and_thermal`, `::test_devanagari_is_shaped_not_laid_out_in_logical_order`, `::test_voucher_in_hindi_renders_on_both_layouts` |
| Gateway settlements are not blocked by the walk-in rule (the money has already moved) | 🚫 by design | none; `tests/test_w0_webhook_holding.py` covers the webhook path |


## Money In, Phase 2 (2026-10-11)

No new SUPPORTED feature and no frozen flag changes; the company settings it adds default to the
old behaviour (`cheque_allocation_on_clearance` off, `cash_269st_mode` warn, `advance_gst_treatment`
none). Tracked as QOS-0119 to QOS-0123; the plan is
[`plans/MONEY_IN_PHASE2_IMPLEMENTATION_PLAN.md`](plans/MONEY_IN_PHASE2_IMPLEMENTATION_PLAN.md).

| Work package | Behaviour | Status | Gating test |
|---|---|---|---|
| WP-1, WP-3 | CREDIT mode, a discount or TDS above the amount, a discount with no bill, and bank-type money with no bank account are refused; system callers are exempt; s.269ST cash check | ✅ gated | `test_money_in_phase2.py::test_credit_mode_is_refused_by_the_service_and_the_api`, `::test_discount_must_be_between_zero_and_the_amount`, `::test_bank_modes_need_a_bank_account_and_use_the_default`, `::test_system_callers_never_fail_on_the_bank_rule`, `::test_cash_269st_warns_by_default_and_blocks_when_asked` |
| WP-2 | Dialog clears the bill on a customer change, follows the amount, resets after a save, finds archived customers | ✅ gated | `ReceiptsPage.test.tsx` ("Phase 2 input rules"), `test_inactive_customer_with_an_open_invoice_can_still_pay` |
| WP-4 | Cheques held as advances until they clear (setting, off by default); uncleared cheques on the customer, invoice and dashboard | ✅ gated | `::test_flag_on_clearing_applies_what_the_person_asked_for`, `::test_flag_off_a_pending_cheque_can_be_applied_as_before`, `test_money_in_phase2_b.py::test_uncleared_cheques_show_on_the_customer_ledger_and_dashboard` |
| WP-5 | Each allocation stores its own discount slice; GL and invoice balance move by the same amount | ✅ gated | `::test_partial_allocation_clears_the_same_amount_in_the_gl_and_on_the_invoice`, `::test_discount_and_tds_shares_add_up_exactly_over_any_split`, `::test_unallocating_frees_the_discount_for_the_next_allocation` |
| WP-6 | Customer TDS: account 1270, settles the bill, no false advance-mismatch alert | ✅ gated | `::test_customer_tds_settles_the_invoice_and_ties_out`, `test_money_in_phase2_b.py::test_customer_outstanding_counts_the_tds_and_discount_a_receipt_cleared`, `e2e-golden/money-in-golden.spec.ts`, `::test_unallocated_receipt_with_tds_does_not_trip_the_advance_alert`, `::test_tds_is_prorated_over_partial_allocations_and_voids_cleanly` |
| WP-7 | Receipt edit (notes, reference, UTR, bank) and advance refunds, every reader of "unallocated" in agreement | ✅ gated | `::test_edit_changes_only_the_allowed_fields_and_is_audited`, `::test_bank_account_edit_repoints_the_journal_and_survives_a_void`, `::test_refunding_part_of_an_advance_keeps_every_reader_consistent` |
| WP-8 | Bank match review after a bounce; cheque-return debit line matches the bounced receipt; reconciled flag and filter | ✅ gated | `test_money_in_phase2_b.py::test_cheque_return_debit_line_matches_the_bounced_receipt`, `test_money_in_phase2.py::test_void_error_for_a_matched_receipt_names_the_line` |
| WP-9 | Correct closed till (manager), counted figures untouched, adjustments on the shift report | ✅ gated | `::test_manager_corrects_a_closed_till_and_the_counted_figures_stay`, `::test_a_cashier_cannot_correct_a_closed_till_and_open_tills_are_not_eligible` |
| WP-10 | GST on advances for services (setting, off by default): 11A, cross-period 11B, refund vouchers; reported, not posted | ✅ gated | `test_money_in_phase2_b.py::test_services_advance_is_taxed_inclusive_and_split_by_place_of_supply`, `::test_cross_period_adjustment_and_refund_voucher_reduce_the_later_period`. **CA sign-off required before the setting is turned on for any company** |
| WP-11 | Kept promises close and reopen with receipts; void reopens payment links; returned-invoice flag | ✅ gated | `::test_a_kept_promise_closes_at_once_and_a_void_reopens_it`, `::test_voiding_the_receipt_that_paid_a_link_reopens_it`, `::test_receipt_row_flags_an_invoice_returned_after_payment` |
| WP-12 | Walk-in and void-rate alerts, UTR-aware duplicate alert with a dismiss reason, move walk-in money to the payer, portal receipts | ✅ gated | `::test_walk_in_receipt_raises_an_alert_that_clears_when_applied`, `::test_walk_in_money_moves_to_a_named_customer_with_a_dated_transfer`, `::test_portal_lists_receipts_with_a_voucher_link` |
| WP-13 | Sort, page size, bulk apply (ordered, idempotent), bulk send, send by WhatsApp or email, offline outbox for cash and cheque | ✅ gated | `test_money_in_phase2.py::test_ordering_allow_list_and_stable_pages`, `test_money_in_phase2_b.py::test_bulk_allocate_is_ordered_idempotent_and_reports_each_row`, `receiptOutbox.test.ts`, `ReceiptsPage.test.tsx` ("offline") |
| WP-14 | Export needs `can_export`, streamed, throttled, audited; print audited; void and refund idempotent; Hindi voucher selectable (ActualText); invalid-index check | ✅ gated | `::test_export_needs_the_export_permission_and_is_audited`, `::test_voucher_print_is_audited`, `::test_void_is_idempotent_by_key`, `::test_hindi_voucher_text_can_be_selected_and_searched`, `::test_check_indexes_is_quiet_off_postgres` |
| WP-15 | Totals in one aggregate, no per-row UTR queries, covering indexes | ✅ gated | `::test_a_list_page_of_upi_receipts_does_not_query_per_row`, `::test_summary_is_one_aggregate_over_the_receipts`; timings in the plan |
| WP-16 | Cross-tenant, concurrency (Postgres), bounce and re-receive, void date, cross-module tie-out | ✅ gated | `::test_cross_module_tie_out_through_cheque_tds_discount_bounce_void_and_refund`, `::test_receipts_of_another_tenant_stay_invisible`, `::test_two_refunds_cannot_together_exceed_the_advance` |

## Customers master hardening (2026-10-12)

Not a freeze-table item; listed so the gating tests are findable. Plan and review: `CUSTOMERS_IMPLEMENTATION_PLAN.md`,
`docs/CUSTOMERS_WORK_PACKAGES.md`, `docs/CUSTOMERS_REVIEW_2026-10-12.md`, `docs/CUSTOMERS_STATUS_SEMANTICS.md`.

| Area | Status | Gating test(s) |
|---|---|---|
| GSTIN rules (reset, state, PAN, duplicates), walk-in guard, credit-term and status roles, optimistic locking, archive safety, summary, export, history, health, bulk verify, throttles, metrics, monthly audit | ✅ | `backend/tests/test_customers_master.py` |
| GSTIN state rules, Indian mobile format, per-user throttle key | ✅ | `backend/tests/test_party_validators.py` |
| Archived (INACTIVE) customers refused like blocked ones; drafts still saved | ✅ | `backend/tests/test_business_rules.py` |
| Recurring schedules skip non-active customers and pause on archive | ✅ | `backend/tests/test_sprint_c_recurring.py` |
| Dunning skips archived, keeps blocked | ✅ | `backend/tests/test_a07_dunning.py` |
| Bulk credit exposure and advances | ✅ | `backend/tests/test_ledger.py` |
| Customer import and bill import follow the customer rules | ✅ | `backend/tests/test_imports.py` |
| Lead conversion follows the customer rules | ✅ | `backend/tests/test_sprint_b_crm_convert.py` |
| Restore keeps customers exact and reports rule breaks | ✅ | `backend/tests/errors/test_backup_restore_drill.py` |
| GSTIN provider unreachable vs unconfigured | ✅ | `backend/tests/test_gst_guard_v2.py` |
| Tenant isolation and role table for the customer endpoints | ✅ | `backend/tests/tenancy/test_endpoint_isolation.py`, `backend/tests/tenancy/test_rbac_matrix.py` |
| Real row-lock races, export and list under RLS | ✅ Postgres only | `backend/tests/test_customers_concurrency_postgres.py` |
| Customers list, form, bulk verify, health banner, 360° edit and history, a11y | ✅ | `web/src/pages/sales/CustomersPage.test.tsx`, `Customer360Page.test.tsx` |
| Customer API helpers, cache invalidation helper, status tone, GSTIN chip, phone rule, pickers | ✅ | `web/src/api/customers.test.ts`, `web/src/pages/sales/customerQueries.test.ts`, `web/src/utils/status.test.ts`, `web/src/utils/gstinStatus.test.ts`, `web/src/utils/gst.test.ts`, `web/src/hooks/usePartySearch.test.tsx`, `web/src/pages/purchases/SuppliersPage.gstinStatus.test.tsx`, `web/src/pages/sales/RecurringInvoicesPage.test.tsx`, `web/src/pages/sales/NewInvoicePage.test.tsx` |
| Customers help pages and FAQs | ✅ | `web/src/pages/help/customersHelp.test.tsx` |
| Real browser (desktop and phone Chrome) | ✅ | `web/e2e/customers.spec.ts` |
| Q-OS backlog items | ✅ | QOS-0124 (fixed), QOS-0125 (open: retention decision, Hindi review) |

## Post-freeze: Quick Order Entry (2026-10-12)

Outside the freeze table. Gated by `backend/tests/test_sales_order_guards.py` (order/challan customer-status gate,
subscription gate, idempotent create/confirm, multi-GSTIN tax split, order defaults and filters, price mode,
Quick Entry pricing and recents, feature flags), `backend/tests/test_tax_engine_registry.py` (preview item shape),
`web/src/pages/sales/QuickEntryPage.test.tsx`, `web/src/utils/quantity.test.ts`,
`web/src/pages/sales/invalidateInvoiceSideEffects.test.ts`, `web/src/pages/sales/SalesOrdersPage.test.tsx` and
`Customer360Page.test.tsx`. Backlog item: `qos/backlog/QOS-0048.yaml`. Rollout and rollback:
[QUICK_ORDER_ENTRY_ROLLOUT.md](QUICK_ORDER_ENTRY_ROLLOUT.md).

## Recurring invoices hardening (2026-10-15)

| Item | Status | Evidence |
|---|---|---|
| Auto-complete no longer reports a false failure; gate failure keeps a Draft and stores the reason on the run; catch-up completes only the first period | ✅ | `backend/tests/test_recurring_lifecycle.py::test_auto_complete_*`, `::test_catch_up_only_*` |
| "Run now" for sales users, audited, refuses inactive customers, reports an already-generated period | ✅ | `backend/tests/test_recurring_lifecycle.py::test_run_now_*`, `backend/tests/test_sprint_c_recurring.py` |
| Locked period shows a reason on the schedule and clears when it runs; one notice per change | ✅ | `backend/tests/test_recurring_lifecycle.py::test_locked_period_*` |
| Edit keeps the anchor day; resume needs a future date and an active customer; delete blocked once runs exist | ✅ | `backend/tests/test_recurring_lifecycle.py::test_editing_*`, `::test_resume_*`, `::test_delete_*` |
| Quarterly, half-yearly, annual cadences with period keys; end date and maximum runs enforced on the beat and on Run now | ✅ | `backend/tests/test_recurring_lifecycle.py` (cadence, period-key, term tests) |
| Run history endpoint paginated and tenant scoped; list makes no per-row queries | ✅ | `backend/tests/test_recurring_lifecycle.py::test_runs_endpoint_*`, `::test_schedule_list_does_not_query_per_row` |
| Contract-owned schedules locked on the Recurring page and paused when the contract ends | ✅ | `backend/tests/test_recurring_lifecycle.py::test_contract_managed_*`, `::test_ended_contract_*` |
| Backup rows carry the new fields; restore keeps each run's invoice, order and challan link | ✅ | `backend/tests/test_recurring_lifecycle.py::test_backup_rows_*`, `backend/tests/test_recurring_followups.py::test_restore_keeps_*`, `backend/tests/errors/test_backup_restore_drill.py` |
| Recurring page: server search pickers, edit drawer with server totals, pause/resume, history, run-now result, delete | ✅ | web `pages/sales/RecurringInvoicesPage.test.tsx`, `pages/sales/recurring/recurringHelpers.test.ts` |
| Run now racing the beat or itself makes one document (Postgres row locks) | ✅ | `backend/tests/test_recurring_concurrency_postgres.py` (Postgres-only) |
| Golden path: create quarterly schedule, edit, pause, resume, run now, open draft | ✅ | `web/e2e-golden/recurring-invoices-golden.spec.ts` |
| Hindi wording of the new recurring strings | 🟡 | native-speaker review open, same as other new Hindi strings |
| Contract renewed or un-cancelled restarts only a schedule the contract ending paused; flag-off companies still pause | ✅ | `backend/tests/test_recurring_followups.py::test_cancelling_*`, `::test_a_schedule_a_person_paused_*`, `::test_a_company_with_contracts_switched_off_*` |
| Auto-completed B2B invoice is handed to the e-invoice portal only when the company uses e-invoicing and the customer has a GSTIN; state shown in history | ✅ | `backend/tests/test_recurring_followups.py::test_completed_b2b_invoice_*`, `::test_run_history_shows_the_einvoice_state_*` |
| The beat keeps a tenth of the plan's monthly completions free for manual billing | ✅ | `backend/tests/test_recurring_followups.py::test_the_beat_keeps_a_tenth_*` |
| Invoice detail links back to the schedule that made it | ✅ | `backend/tests/test_recurring_followups.py::test_a_generated_invoice_shows_*`, web `pages/sales/InvoiceDetailPage.test.tsx` |
| Server-side active/paused filter and paging; phone layout (cards and action menu); no accessibility violations in the page and edit panel | ✅ | `backend/tests/test_recurring_followups.py::test_list_filters_*`, web `RecurringInvoicesPage.test.tsx`, checked in Chrome with axe at desktop and 390px width |
