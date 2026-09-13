# Freeze Scope → test coverage map

Companion to [`FREEZE_SCOPE.md`](FREEZE_SCOPE.md). Every SUPPORTED item (§A) and
every §G/§H flow marked **SUP** is listed here with the **concrete** test(s) that
gate it, or an explicit **GAP** / **not gated** line. The `FG-2x` codes in
`FREEZE_SCOPE.md` are plan labels; this file is the actual wiring.

Last reconciled: 2026-09-10, spot-corrected 2026-09-13 (A25/H10 webhook
mis-blocking, WF-33 bank-rec staleness, determinism-probe closure) against
this session's own verified fixes — not a full re-sweep. Backend suite
paths are under `backend/`.

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
| A10 | Customer receipt + allocation | ✅ | `test_wf39_advance_payment_on_account`, `test_pj_service_owner_no_stock`, `test_pj_trader_owner_normal_day` |
| A11 | Supplier payment + allocation | 🟡 | `test_pj_trader_owner_normal_day` (receipt+allocate side), `test_wf12_purchase_credit_note`; dedicated purchase-payment + `test_wf13_purchase_debit_note_tds` still skipped |
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
| A26 | OTP login (D4) | 🟡 | `tests/test_auth.py::test_otp_*` (hashing / debug gate); dedicated `test_wf18_otp_login_and_ratelimit` still skipped — rate-limit assertion needs throttling enabled in `settings_test` |

## C. KNOWN LIMITATIONS — route guards (scope revision 2026-09-09b)

| # | Item | Status | Gating test(s) |
|---|---|---|---|
| D6 | Fixed assets | ✅ | `tests/workflows/test_wf_limitation_guards.py` + `tests/personas/test_pj_limitation_guards.py` — route 404s under `ENABLE_FIXED_ASSETS=0`; `test_wf53_*` covers the opt-in path |
| D10 | Bill of Entry | ✅ | same files — route 404s under `ENABLE_BOE=0`; `test_wf57_*` covers the opt-in path |
| D7/D8/D9/D11 | TDS-returns / RCM / composition / plan-limits | 🟡 | no separate flag (screened out / out of band). Computation-path regression kept: `test_wf55/56/58_*`, relabelled "not a freeze blocker" |

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
| Refunds / MDR reconciliation | 🚫 | WF-37 / WF-38 skipped — D3 sandbox credentials |
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
| Plan-limit enforcement | 🟡 | `test_wf58_plan_limits` — LIM coverage (D11) |
| Idempotency contract | ✅ | `test_wf51_idempotency_contract` |
| Concurrency / races | 🚫 | `tests/test_concurrency_races.py` is Postgres-only (`postgres` marker); runs in the `invariant-sweep` Postgres job, not local SQLite |
| Audit-trail completeness | ✅ | callable `audit.statutory_events_present` (lifecycle events, wired into WF-43/44); `tests/errors/test_freeze_gate_contracts.py` asserts the `AuditEvent` / `StatutoryDocumentEvent` viewsets expose **no** create/update/delete path. 🟡 "every mutation writes an `AuditEvent`" still not asserted |
| Money-field audit | 🟡 | callable `audit.money_mutations_logged` (no-op / blank-field rows). ⛔ "every completed-doc money change is logged" not yet asserted |
| Document numbering gap-free | ✅ | callable `numbering.sequences_intact` (Rule 46(b) consecutive serials), wired into WF-52 + `tests/test_invariants_smoke.py` (incl. a gap-detection red-then-green test) |
| Report cross-reconcile | ✅ | callable `reports.cross_reconcile` (TB balanced, P&L == TB income−expense, balance-sheet equation) wired into WF-01 / WF-04 + smoke |
| File assets — auth / path traversal | ✅ | `tests/errors/test_freeze_gate_contracts.py` — tenant-scoped download (cross-tenant = 404), `original_name` with `../` / CRLF / quotes sanitised in `Content-Disposition` |
| Rate limiting on auth endpoints | 🟡 | see A26 — needs throttling in `settings_test` |
| Pagination correctness | ✅ | `tests/errors/test_pagination_contract.py` — page-size cap, default size, stable paging (no drops/dupes across boundaries), out-of-range = 404 |
| Security headers | ✅ | `tests/errors/test_freeze_gate_contracts.py` — `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `X-Frame-Options` present; no `Server` version leak |
| Boot-time config validation | ✅ | `tests/errors/test_freeze_gate_contracts.py` — `DJANGO_FAIL_FAST_SECRETS=1` + weak `DJANGO_SECRET_KEY` aborts `django.setup()` with `ImproperlyConfigured` (subprocess) |
| Request-log PII masking | ✅ | `tests/errors/test_freeze_gate_contracts.py` — logged path has no query string / doc number, ids are 12-hex hashes, record carries no body/headers |
| HelpCode registry | ✅ | `test_freeze_gate_contracts.py::test_every_helpcode_constant_is_registered` (no orphan constant) + existing `test_help_resolution.py` / `test_help_codes_live.py` |

## H. Out-of-frame concerns marked SUP

| Concern | Status | Note |
|---|---|---|
| H1 — all frontend behaviour | ⛔ | separate FE workstream (`web/`); `web/e2e/personas/*.spec.ts` is the planned home. Not gated by the backend suite by design |
| H3 — task effects / retry / beat registry | 🟡 | effects asserted (eager mode) throughout the WF chains; explicit retry→user-state + beat dry-run tests not added |
| H4 — data-subject export scoping | ✅ | tenancy assertions on the export payload (`tests/tenancy/`) |
| H4 — audit-log immutability (`audit.append_only`) | ✅ | `test_freeze_gate_contracts.py` — audit viewsets have no Create/Update/Destroy mixin; write verbs 403/405 |
| H4 — PII masking in request logs | ✅ | `test_freeze_gate_contracts.py::test_request_log_masks_ids_and_carries_no_body` |
| H5 — HelpCode coverage / error→status mapping | ✅ | `tests/errors/`, `tests/test_help_codes_live.py`, `test_freeze_gate_contracts.py` (no orphan constant) |
| H5 — boot-time config validation | ✅ | `test_freeze_gate_contracts.py::test_fail_fast_secrets_rejects_weak_secret_key` |
| H6 — business-logic edge cases | ✅ | `tests/edge/test_document_edge_cases.py` |
| H7 — report cross-reconcile | ✅ | callable `reports.cross_reconcile` (WF-01/04 + smoke); `reports.pnl_reconciles_to_trial_balance` registered; filtered-report snapshots in `tests/snapshots/test_exports_and_filtered_reports.py`. 🟡 party/godown/cost-centre filter snapshots still not added |
| H8 — pagination correctness | ✅ | `tests/errors/test_pagination_contract.py` |
| H9 — SQLite vs Postgres parity | ✅ | `invariant-sweep` + `backend` + `e2e-golden` CI jobs run on Postgres |
| H9 — security headers / CORS / CSRF / CSP | 🟡 | `test_freeze_gate_contracts.py` covers the Django-emitted headers; CSP is not implemented in-app (edge/CDN concern) — stated, not gated |
| H10 — webhook signature verification (every inbound) | ✅ | **Was `🚫`, corrected 2026-09-13 — this was never actually D3/creds-blocked.** Both inbound webhooks (Razorpay billing, generic payment-gateway) have signature verification + a forgery test (`tests/errors/test_webhook_and_async_contracts.py`, `tests/test_payment_webhook_adversarial.py`), and `tests/errors/test_webhook_enumeration.py` structurally fails the build if a new, unverified webhook route appears. Don't confuse with A25 above (the live sandbox gateway E2E), which genuinely is creds-blocked |
| H10 — LLM bill extraction failure / injection | ✅ | `tests/errors/test_llm_extraction_failures.py`, `tests/errors/test_llm_injection_guard.py` (D14) |

---

## Open GAPs (SUPPORTED, not yet gated)

1. **H7** — cost-centre filter snapshot still missing (date, party and godown
   filters + the TB↔P&L↔BS cross-reconcile are covered).
2. **Determinism-probe — CLOSED 2026-09-11** (per `scripts/ci_gates/GATE_INVENTORY.md`,
   which is the more current source for this item than this row was). The
   throttle-timer crash fix (above) plus re-anchoring the 5 clock-brittle
   fixtures to the real/frozen clock instead of hardcoded literals
   (`test_a07_dunning`, `test_b03_ims`, `test_item_godown_expiry`,
   `test_pr6_period_gl`, `test_sprint_a_prod_gst_p1`) brought
   `TESTS_FREEZE_CLOCK=1` to **1488 passed / 0 failed / 23 skip**. `determinism-probe`
   stays advisory in CI until it's shown green on `main` for 3 consecutive
   runs (a CI-history fact this doc can't itself confirm), then flip to blocking.
3. **Blocked on external deps:** A25 live-gateway E2E / G3 refunds+MDR
   (Cashfree/PayU sandbox creds — **H10 webhook signature verification is
   NOT in this list**, corrected 2026-09-13, see H10's row above); concurrency
   races (Postgres-only, runs in CI not locally); mutation audit (WSL/Linux only).

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

**Mobile-project e2e failures are pre-existing and net-improved.** Baselined by
stashing all working-tree changes: without this session's work the `[mobile]`
(Pixel 5) project fails **5** tests across `help.spec.ts` + `item-custom-fields.spec.ts`;
with it, **2** (`MOCK_FLAGS.item_custom_fields_v2 = true` fixed 3). The residual 2
are mobile-viewport layout issues unrelated to Freeze Gate scope:
`help.spec.ts:55` (universal-search combobox not rendered at Pixel 5 width) and
`item-custom-fields.spec.ts:46` (`/sales/new` heading behind the mobile nav
drawer). Zero regressions introduced; chromium project is fully green.

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
- FE persona counterparts scaffolded — `web/e2e/personas/role-boundaries.spec.ts`
  (OWNER + VIEWER live; SALES / ACCOUNTANT `test.fixme` pending mock logins).

Skipped chains that are now **covered elsewhere** and left as thin redirect
skips (docstring points at the real test): WF-20 → PJ-WHOLE-ACCT + WF-44;
WF-23/24/25 → PJ-TRADER-IMPORT.

Still genuinely skipped in `test_wf_todo_stubs.py`: WF-11 (recurring invoice),
WF-13 (purchase debit note + TDS), WF-14/15 (LLM bill upload — D14-adjacent),
WF-18 (D4 blocked). **WF-17 corrected 2026-09-13** — retargeted to real
(unskipped) coverage, no longer D3-blocked; see A25/H10 above. In
`test_wf_extended_stubs.py`: **WF-33 corrected 2026-09-13** — was already
unskipped and passing, the module header claiming otherwise was stale (now
fixed); not in this list anymore. WF-37/38 (D3, genuinely blocked),
WF-45-verify / WF-46-ratelimit (need the flow /
throttling in `settings_test`).
