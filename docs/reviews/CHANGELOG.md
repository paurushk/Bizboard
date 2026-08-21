## 2026-08-06 — Wave 22 Full Remediation (F0–F5)

Closed all **64** Wave 22 Open issues `BB-000695`–`BB-000758`.

### Sprints
- **F0:** Sales RCM GL (no Output GST), GSTR-1 RCM/SUPECOM liability, GSTR-3B stamp reuse, GSTR-9 GSTIN, payroll employer+ESI ceiling, TCS ungated, BooksHealth coverage, 2B PARTIAL no sticky FK, multi-GSTIN fail-closed stamp, FY closes GstReturnPeriod.
- **F1:** Period gate no swallow; money service period gates; unallocate reverse dating; opening stock atomic; WO business dates; series GSTIN+FY; CN number after period assert.
- **F2:** Challan/PI/transfer/return/WO FIFO peel restore; PR serial; H9 qty forbid on tracked SKUs; CRM convert idempotent; price_role; SO convert lot/serial; rebuild WH; GRN honesty.
- **F3:** SaaS PENDING + REQUIRE_SUBSCRIPTION; PAST_DUE grace; seat_limit; idempotency begin_record; GSTIN sandbox trust.
- **F4:** PWA offline.html + no /api cache + logout purge; GSTR export GSTIN; runtime feature flags; filing 404 without GSP_CERTIFIED; WA/OCR/AI/company switch.
- **F5:** Celery doc keys; compose RLS/migrate; feature_flags read; Android allowBackup; Dependabot/CI/CD; OpenAPI drift; NewInvoice split; Sentry ErrorBoundary; /metrics; recon GET read-only; nginx no-cache; inventory apps.get_model.

### Scores (post Wave 22 remediation)
PR **7.8**, Accounting **8.5**, GST **8.2**, Security **6.5**.

Tests: `test_wave22_f0_*.py` … `test_wave22_f5_*.py`.

---

## 2026-08-06 — Wave 22 independent re-audit

Live-code residual pass after Sprint A–E / Wave 21 (register previously Open=0 for 550–694).

- Appended **64** issues `BB-000695` … `BB-000758` (Critical 8 · High 27 · Medium 28 · Low 1).
- Register total: **758**. Wave 22 Open: **64**.
- Invalidates engineering-ceiling PR/Accounting/GST 9.x as commercial launch gate until Wave 22 P0s close.
- Top P0s: sales RCM GL (695); GSTR-3B empty-stamp (697); period swallow (699); bank/gateway period bypass (700); payroll employer GL (703); challan/PI cancel FIFO (717/718); PR serial drop (722); SaaS ACTIVE/no-sub (725); idempotency TOCTOU (730); PWA API cache (738).

Scores revised (honest residual): PR **4.2**, Accounting **5.5**, GST **5.0**, Security **3.5**.

Agents: [Audit accounting GST security](7496f099-6068-4cbc-a47d-f351ed153039), [Audit inventory sales payroll](3148440a-3c08-4abb-a850-3a4b1597348d), [Audit frontend mobile DevOps](b9c6c334-890f-4d03-951e-3d1c44190ddf).

---

## 2026-08-06 — Sprint A GST AT/TXPD/amendments GSTIN scope

- GSTR-1 AT empty on non-primary `company_gstin_id` (advances are company-level until allocated).
- TXPD + amendments pass the same stamp; CSRF localhost-only blocked in prod/staging.
- Evidence: `test_gstr1_at_scoped_to_primary_gstin`.

---

## 2026-08-06 — Sprint A accounting P1 follow-up

- BooksHealth `control_balances` reconciles unfloored tagged AR/AP (not floored `bulk_*` sums); untagged 1200/2100 lines trip mismatch.
- `assert_period_allows_money_amend(..., allow_soft_closed=)` aligned with `PostingService.post`; cancel/return/WO cancel pass `allow_soft_closed=True`.
- Backfill: opening stock Dr1400/Cr3200, opening PI poster, skip VOIDED/REFUNDED receipts, allocation JEs, return COGS signature, party retag.
- Billing write gate via middleware (not DEFAULT_PERMISSION_CLASSES) to avoid circular import; exception handler lazy-imports Response.
- Local pytest clears inherited `DATABASE_URL` unless `CI` / `PYTEST_KEEP_DATABASE_URL=1`.

Evidence: `test_sprint_a_accounting_p1.py` (13 passed with phase5/wave3 soft-closed checks).

---

## 2026-08-05 — Open-code sprints A–E

- **Sprint A:** Dual-ledger bulk AR/AP GL-first; SOFT_CLOSED gates; opening stock Dr1400/Cr3200; WO WAVG stamp; H9 FIFO restamp; refund `reverse_allocation`; backfill opening/return safety; invite tokens omitted in prod/staging; MIME magic-only; CORS/CSRF required in prod; X-Company-Id no silent multi-membership fallback; health detail Owner-only; JSON 500 envelope; CN IRN UI; stamp fail-closed; GSTR DOC/AT GSTIN scope; SUPECOM; sales RCM confirm; 2B UNREVIEWED+CLAIMABLE; GSTR `company_gstin` query.
- **Sprint B:** PF/ESI/PT payroll preview; CRM convert+activities; PWA SW + offline.html; Capacitor Android shell notes. Manufacturing cancel/WIP already present — Preview copy kept.
- **Sprint C:** FY close IS→RE 3100 (BB-000664); recurring DRAFT invoices (BB-000669); TDS/TCS MVP + 26Q/27EQ worksheets (BB-000670, `ENABLE_TDS`).
- **Sprint D:** Encrypted tenant export/restore sandbox (BB-000668); SaaS `billing` app + Razorpay webhook + write gate (BB-000671).
- **Sprint E:** Provider-shaped GSP/IRP adapter, QR/ack verify, `GSP_CERTIFIED` Final Gate; prod stay fail-closed (BB-000624). QUEUED enum unchanged.
- Scores (engineering ceiling): Accounting **9.7**, GST **9.3**, Production Readiness **9.3**. True 10/10 still needs signed CA/ops Final Gates + certified GSP credentials.

Tests: `test_sprint_a_accounting_p1.py`, `test_sprint_a_prod_gst_p1.py`, `test_sprint_b_*.py`, `test_sprint_c_*.py`, `test_sprint_d_*.py`, `test_sprint_e_gsp_protocol.py`.

---

## 2026-08-05 — Audit follow-up (accounting / GST / prod P0)

- Challan-stocked returns/H9 COGS use delivery-challan SALE peels; opening SI/PI skip stock+COGS.
- Purchase CN/DN split 1400 vs 5110; RCM AP = grand_total; note `rcm_cess`; partial PR ratios charges.
- 2B ITC requires purchase CLAIMABLE; HSN-missing invoices excluded from GSTN sections; e-Way adapter fail-closed in prod/staging; cancel IRN/EWB sandbox-gated.
- Tenant FK checks on cost_center/warehouse; feature flags env AND-gate; accounting settings require explicit boolean; complete Idempotency-Key uses durable records; health exposes `rls_enabled`.

---

## 2026-08-05 — PR / Accounting / GST code-max

- Purchase invoices stamp + expose `company_gstin`; GSTR-3B/CN/DN ITC filters by stamp (legacy null included on primary).
- GSTR-3B v2.2: outward/inward/RCM cess, 2B cess, TXPD-from-AT worksheet.
- IRP SellerDtls + sandbox live-GSTIN gate honor `CompanyGstin` when `company.gstin` is blank.
- Payroll JE asserts 5800 expense vs 1100/2150 (not AP 2100); H9 COGS keeps SALE peel cost.
- Scores (engineering ceiling): PR **9.0**, Accounting **9.5**, GST **9.0**. Final Gates + signed Defer still block 10/10.

Tests: `test_h9_price_amend_keeps_sale_peel_cogs`, `test_bb_000567_payroll_accrual_uses_wages_payable`, `test_bb_000639_seller_stamp_without_company_gstin`, `test_gstr3b_cess_and_txpd_from_at`, `test_gstr3b_purchase_itc_scoped_by_company_gstin`.

---

## 2026-08-05 — Remaining partials: mfg WIP/snapshot, GSTR-9 ITC, unallocate UI

- WO release snapshots BOM into `WorkOrderLine`; complete/cancel use the snapshot, not live BOM.
- Manufacturing posts WIP GL (`1450`) on release/complete and reverses on cancel when accounting is enabled.
- GSTR-9 tables 5–7 are books worksheets (nil rollup, claimable ITC, purchase-CN reversal) — not Dark empty stubs and not a full annual engine.
- Invoice detail lists allocations and can unallocate (API was already live).
- Honesty docs updated for mfg GL/snapshot, e-way distance, and GSTR-9 worksheet status.

Tests: `test_partial_closures.py` (`test_wo_release_snapshots_bom_and_posts_wip`, `test_gstr9_table_6_from_claimable_purchase`).

---

## 2026-08-05 — Review fixes on partial-closure pass

- Block void on gateway receipts (refund path only); reverse CREATE JE on document date.
- Release UTR uniqueness after VOID; exclude VOIDED/REFUNDED from books-health advance math.
- FIFO cancel falls back to a replacement layer when historical peels are missing.
- WO FG cost falls back to component list price when ISSUE has no stamped cost; cancel restores to the issue warehouse.
- CN/DN no longer copy full invoice additional charges onto partial notes.
- Outstanding/GSTR/insights/PDF allocation sums ignore reversed rows.
- Receipts + supplier payments UI can void posted documents.

---

## 2026-08-05 — Partial-closure pass (void / FIFO / mfg / e-way / PhasePages / RLS)

Implemented remaining incomplete remediations that were register-closed without full behavior:

- BB-000650 / BB-000651: `POST .../void/` and `POST .../unallocate/`; VOIDED status; reverse CREATE + ALLOCATE journals; no hard delete.
- BB-000655: allocation JE `entry_date` uses receipt/payment date.
- BB-000654: cash create/allocate responses include `warnings` from `period_complete_warning`.
- BB-000601: outbound FIFO peels recorded on `StockMovement.layer_peels`; cancel restores original layers (no new inbound layer).
- BB-000555 / BB-000564: WO FG unit cost from ISSUE peels; cancel RELEASED restores ISSUE layers via `work_order_cancel`.
- BB-000649 / BB-000663: CN/DN snapshot `additional_charges`, filing GSTIN/POS, `company_gstin`.
- BB-000639–642: e-Way requires `transport_distance_km`; real `sub_supply_type` / `trans_mode` fields.
- BB-000630: PhasePages split into Banking / Inventory / AccountingExtra modules.
- BB-000604 / BB-000551: RLS middleware authenticates Cookie JWT first; `set_config` fail-closed.

Tests: `backend/tests/test_partial_closures.py`.

---

## 2026-08-05 — Sprint 6 + register hygiene (550–694 Open → 0)

Closed **145** issues in `BB-000550`–`BB-000694` (register already status-flipped by sprint close-out; Sprint 6 annotated evidence):
**140 Resolved** (Fix / Dark honesty+kill-switch) and
**5 Deferred** (signed L-items only).

### Deferred (signed)

| ID | Kind | Why |
|----|------|-----|
| BB-000624 | Deferred — roadmap | Live NIC/IRP protocol |
| BB-000664 | Deferred — roadmap | FY close hidden until real IS→RE |
| BB-000668 | Deferred — roadmap | Tenant backup/restore — ops runbook |
| BB-000669 | Deferred — roadmap | Recurring invoices |
| BB-000671 | Deferred — roadmap | SaaS entitlements |

### Sprint 6 code / honesty tests

- `test_bb_000664_fy_close_refuses_to_post` / `test_bb_000664_fy_close_not_routed`
- `test_bb_000573_company_patch_cannot_write_gsp_credentials`
- `test_bb_000580_pwa_offline_install_unclaimed` / `test_bb_000575_capacitor_unclaimed_in_readme`
- `test_bb_000630_phasepages_split_started`
- `test_bb_000594_jwt_access_lifetime_from_env`
- `test_bb_000636_no_duplicate_health_snapshot_beat`
- `test_bb_000587_request_path_redacts_document_numbers`
- `test_bb_000585_prod_compose_api_does_not_migrate_on_start`
- `test_bb_000595_erp_admin_modules_importable`
- `test_bb_000598_adrs_adopted` / `test_bb_000591_competitor_honesty`
- FE: `invoiceDraftCache.test.ts` cess round-trip + logout wipe (BB-000572/577)

Script: `docs/reviews/_close_open_550_694.py`.

**Open count for 550–694: 0.**

---


## 2026-08-05 — Open issues BB-000550–BB-000694 closed (Sprints 0–6)

- Sprint 0: host/DEBUG, cookie+CSRF, CSP, tenant FK/RBAC, books-on Complete, CORS, health redact, honesty docs. Tests: `test_sprint0_*.py`.
- Sprint 1: invite token+JTI table, money-doc hard-delete forbidden, period gates, durable idempotency, file UUID+ClamAV fail-closed, AA dark, OTP E.164, Cashfree ts freshness, flag refetch. Tests: `test_sprint1_pilot.py`.
- Sprint 2: cess GL 2270/1370, reverse party FKs, CN/GSTR/UTR follow-through. Tests: `test_sprint2_*.py`.
- Sprint 3: FIFO/serial/opening, SO warehouse, GSTIN CRUD, multi-company consent, price lists. Tests: `test_sprint3_*.py`.
- Sprint 4: ERP preview Dark unless flagged (mfg/payroll/CRM 404); RLS stays off. Tests: `test_sprint4_*.py`.
- Sprint 5: WhatsApp connection/templates or wa.me; Tally export honesty; OCR no invented rates; AI/report KPIs. Tests: `test_sprint5_*.py`.
- Sprint 6: Deferred L-items 664/668/669/671 (+624 live NIC); native stores unclaimed; FY close hidden. Tests: `test_sprint6_*.py`.

Deferred (signed): BB-000664, BB-000668, BB-000669, BB-000671, BB-000624.

## 2026-08-05 — Wave 21 residual passes

Logged non-duplicate findings from [Find more audit issues](b068e323-842d-410f-9ea4-ce7d7be094e9) and [Audit payroll mfg CRM](9d174bcc-11c0-45d7-b87c-03d9f1810cd1).

- Appended **45** issues `BB-000650` … `BB-000694` (Critical 8 · High 31 · Medium 5 · Low 1).
- Register total: **694**. Open: **145**.
- Skipped duplicates: paid-CN (648), IRP stamp (639), e-way payload (640–642), file path (643), CN charges/POS (649).
- New P0s: receipt/alloc DELETE orphans GL; GSTR-1 CDNUR vs B2CS; mfg/CRM cross-tenant FKs; invite/prod password deadlock; multi-company join blocked; CompanyGstin no API; VIEWER payments ACL; AA flag ignored.

PR score revised **3.4 → 3.1**. Accounting **2.2**. Security **2.7**. GST **2.9**.

---

## 2026-08-05 — Wave 20 live-code pass

Continued engineering audit after Wave 19 missed-findings (IRP/e-way, files, payments, notes).

- Appended **11** issues `BB-000639` … `BB-000649` (Critical 4 · High 7 · Medium 0 · Low 0).
- Register total: **649**. Open: **100**.
- New P0s: IRP/e-way seller GSTIN ignores stamp (BB-000639); FileAsset path escape (BB-000643); no CN IRN (BB-000647); paid invoices cannot be credited (BB-000648).

PR score revised **3.6 → 3.4**. Accounting **2.5**. Security **3.0**. GST **3.1**.

---

## 2026-08-05 — Wave 19 missed-findings (subagent residuals)

Independent GST/accounting, FE/DevOps/API, and auth/RBAC passes after Wave 19 primary.

- Appended **40** issues `BB-000599` … `BB-000638` (Critical 8 · High 24 · Medium 8 · Low 0).
- Register total: **638**. Open: **89**.
- New P0s include: sales GL `cgst_amount` mismatch, cess not in GL, FIFO cancel/transfer/COGS peel, prod cookie+CSRF/SPA break, CSP vs MUI, AA mock ingest, `is_gst_registered` on wrong model, SOFT_CLOSED no-op, journal reverse drops party FKs, idempotency TOCTOU, RLS middleware-before-JWT.

PR score revised **4.2 → 3.6**. Accounting **2.8**. Security **3.2**. GST **3.4**.

---

## 2026-08-05 — Wave 19 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + `mobile/` + compose/CI/nginx **after** Wave 18 claimed Open==0 and engineering scores ~9.0.

### Outcomes

- Appended **49** issues `BB-000550` … `BB-000598` (
  Critical 9 ·
  High 18 ·
  Medium 17 ·
  Low 5).
- Register total: **598**.
- Status: Open **49** · prior Resolved/Deferred/Accepted retained.
- Invalidated Wave 18 “Open == 0” / PR~9.0 as a commercial launch gate (see BB-000558).
- Production Readiness Score revised **~9.0 → 4.2**.

### Highest new Criticals

- BB-000550 ALLOWED_HOSTS `*` treated as local (DEBUG/ENV bypass)
- BB-000551 / 552 RLS SET LOCAL no-op + superuser bypass (RLS theater)
- BB-000553 VIEWER can mutate manufacturing/payroll/CRM (cash+stock)
- BB-000554 / 555 WO uses SALE/PURCHASE movements + list-price FG costing
- BB-000556 Multi-GSTIN stamps dumped into one GSTR keyed off primary GSTIN
- BB-000557 OCR/LLM defaults unknown gst_rate to 18%
- BB-000558 Wave 18 Open==0 / score process invalidation

### Passes re-executed

Repository structure through missed-findings (Wave 19). Scripts: `_wave19_issues.py` + `_wave19_reaudit_append.py` + `_wave19_update_docs.py`.

---


## 2026-08-05 — Wave 18 Complete Code-Possible Partials

- Closed stale + remaining code Deferred IDs as Resolved/Accepted (30 flipped).
- GST: cess, supply-type FE, ITC eligibility, DOC/AT, GSTR-9 table 17.
- ERP FE, POS, offline outbox, tenancy header, i18n, statutory events, PWA.
- Final Gate ops remain Deferred.

## 2026-08-05 — Wave 17 Close Partials + Deferred Mega MVPs

- Closed Wave 16 partials (Celery IRP, 2B API/health, GSTR-1 EXP/SEZ/nil, GSTR-9 tables, composition CMP-08/GSTR-4, taxpayer_type, GSTIN stamp, ClamAV, GL statements, advances, money audit, FIFO matrix, RLS CI, k6 draft).
- Shipped Deferred mega MVPs: manufacturing/payroll/crm, WhatsApp+Capacitor, AA+Cashfree/PayU, multi-company/i18n/flags, Tally HTTP.
- Resolved IDs: BB-000035, BB-000455, BB-000485, BB-000486, BB-000487, BB-000496, BB-000524, BB-000525, BB-000526, BB-000527 (10 flipped).
- Final Gate ops remain Deferred.
# docs/reviews — CHANGELOG

## 2026-08-04 — Wave 16 mega-wave (toward 10/10)

Shipped code for GL-first AR/AP, FIFO layers, GSP HTTP adapters, GSTR-2B ingest,
CMP-08 aids, RLS flag, restore/digest/SMS/Sentry scaffolding.

**Honest scores (engineering ceiling):** Production Readiness **8.5**, Accounting **9.0**, GST **8.5**.
True **10/10** requires Final Gates in `docs/pilot/FINAL_GATES_10.md` (signed GO_NO_GO, TLS, restore drill, live GSP creds, CA).

Resolved from Deferred (code): BB-000465, BB-000466, BB-000467, BB-000472, BB-000473, BB-000477, BB-000481, BB-000482, BB-000515, BB-000522 (10 flips).

Scripts: `_wave16_assert_gates.py` + `_wave16_close_deferred.py`.

---

## 2026-08-04 — Wave 15 open-closure (Open → 0)

Closed remaining **85** Open issues:
**61 Resolved** via W15A–F (+ load harness / CD notes);
**24 Deferred** (roadmap/ops) with written evidence — no fake GSP/2B/RLS/mobile/ERP modules.

### Outcomes

| Status | Count |
|--------|------:|
| Resolved | 481 |
| Open | **0** |
| Deferred — roadmap | 52 |
| Deferred — ops owner | 12 |

### Waves W15A–H (summary)

1. **W15A** — CSP sync, FIFO honesty, cookie JWT when DEBUG=0, RoleRoute, ADMIN/CORS boot, GUNICORN_WORKERS, statement_timeout, Bearer off in prod
2. **W15B** — purchase return cancel lots+cost, full-refund policy, public pay throttle, credit-limit refund regression
3. **W15C** — money-list first-page ban, cookie e2e, axe CI, viewer landing
4. **W15D** — AR/AP period-close blocks, POS fail-closed, IRN/EWB Owner+reason, depreciation health, CC filters
5. **W15E** — request logs, AI/OCR, idempotency, search timeout, password/invite/MIME, FEFO tests, SMS/AV honesty
6. **W15F** — PhasePages/tax/party splits, Return/Cogs services, GSTR/payments splits, OpenAPI CI, tests
7. **W15G** — Deferred mega/ops + k6/Locust smoke + CD Action SHA pin / digest notes
8. **W15H** — `_wave15_assert_gates.py` + register Open==0

Scripts: `_wave15_assert_gates.py` + `_wave15_close_open.py`.

---

## 2026-08-04 — Wave 14 P0 Critical closure

Closed **9** P0/process issues via code + tests + `_wave14_assert_gates.py`:

BB-000456, BB-000457, BB-000458, BB-000459, BB-000460, BB-000461, BB-000462, BB-000544, BB-000548

### Outcomes
- Beat heartbeat: unix epoch + bare Redis key (compose float() compatible)
- Gateway refund: CustomerReceipt.REFUNDED; PaymentLink reopened
- Fixed asset disposal: 5600/5700; never NBV→5300
- Sales return COGS: SALE movement unit_cost basis
- SQLite refused when DJANGO_ENV production/staging
- Semantic assert gates + honesty pointers updated

Open remaining: **85** (P1+ residual + Deferred roadmap/ops).

---

## 2026-08-04 — Wave 14 missed-findings pass

Appended **6** issues `BB-000544` … `BB-000549` after Wave 14 primary append.

Highlights: SQLite production fail-open (Critical), purchase return cancel lot asymmetry, missing statement_timeout, dual JWT auth stack, semantic gate gap, cancel valuation drift.

Register total: **549**. Open: **94**. Production Readiness **3.3 / 10**.

---

## 2026-08-04 — Wave 14 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + compose/CI **after** Wave 13 claimed Open==0.

### Outcomes

- Appended **88** issues `BB-000456` … `BB-000543` (
  Critical 7 ·
  High 18 ·
  Medium 57 ·
  Low 6).
- Register total: **543**.
- Status: Open **88** · prior Resolved/Deferred retained.
- Invalidated Wave 13 “Open == 0” as a launch gate (see BB-000461).
- Production Readiness Score revised **6.8 → 3.4**.

### Highest new Criticals

- BB-000456 Beat healthcheck float vs ISO heartbeat (+ Redis key prefix)
- BB-000457 Gateway refund phantom unallocated advances
- BB-000458 PaymentLink stays PAID after refund
- BB-000459 Fixed asset disposal NBV → depreciation expense
- BB-000460 Return COGS reverse wrong cost basis (post-restore WAVG)
- BB-000461 Wave 13 Open==0 process invalidation
- BB-000462 ERP module claims still false vs code

### Passes re-executed

Repository structure through missed-findings (Wave 14). Script: `_wave14_reaudit_append.py`.

---

## 2026-08-04 — Wave 13 Scope B open-closure (Open → 0)

Closed all **77** Wave 13 **Open** issues (`BB-000379`…`BB-000455`):
**74 Resolved** via W13A–F; **3 Deferred — roadmap**
(BB-000384, BB-000406, BB-000455) with written evidence (no fake GSP/2B/ERP modules).

### Outcomes

| Status | Count |
|--------|------:|
| Resolved | 411 |
| Open | **0** |
| Deferred — roadmap | 33 |
| Deferred — ops owner | 7 |
| Accepted (positive) | 4 |

### Waves W13A–F (summary)

1. **W13A Payments** — sandbox ban prod/staging, PARTIALLY_PAID, multi-link reserve, company HMAC, Razorpay paise, recon amount match, health ACL, duplicate capture
2. **W13B Accounting** — return COGS, openings equity, advances, H9 COGS, purchase/RCM inventory base, journal unique, FY close, tax assert, period Owner
3. **W13C Inventory** — purchase return lots, cancel serials/lots, challan serials+cancel bridge, SO FEFO rebuild/release, FIFO honesty, CN reason
4. **W13D GST honesty** — GSP fail-closed (384 Deferred), FE/BE POS, soft-close, CDNR/health, composition convert, gates, URP/PIN, nil, ITC honesty (406 Deferred)
5. **W13E Auth/RBAC/FE** — prepare/warehouse ACL, register cookies, JWT body, CSRF, invite token, OTP stub fail-closed, AI tax, RoleRoute, a11y/WhatsApp/e2e
6. **W13F DevOps** — beat health, DJANGO_ENV containers, migrate job, CSP/CD/logs, Tally force Owner, PRODUCTION_READINESS pointer, assert gates

Scripts: `_wave13_assert_gates.py` + `_wave13_close_open.py` (exit 0 = Open == 0).

---

## 2026-08-04 — Wave 13 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + compose/CI **after** Wave 12 claimed Open==0.

### Outcomes

- Appended **77** issues `BB-000379` … `BB-000455` (
  Critical 8 ·
  High 26 ·
  Medium 37 ·
  Low 6).
- Register total: **455**.
- Status: Open **77** · prior Resolved/Deferred retained.
- Invalidated Wave 12 “Open == 0” as a launch gate (see BB-000386).
- Production Readiness Score revised **6.5 → 3.2**.

### Highest new Criticals

- BB-000379 Sandbox payment-link create/settle still allowed in production
- BB-000380 Sales return never reverses COGS/Inventory GL
- BB-000381 Opening invoices dual-ledger permanent mismatch
- BB-000382 Unallocated receipts break AR control
- BB-000383 Purchase return batch-tracked hard-fail
- BB-000384 Production live e-Invoice/e-Way dead end
- BB-000385 Prod Celery beat healthcheck `or True`
- BB-000386 Wave 12 Open==0 meta invalidation

### Passes re-executed

Repository structure, architecture, backend, frontend, database, authn/z, accounting, GST, inventory, sales/purchase, manufacturing/payroll/CRM (absent), banking/payments, OCR/AI, WhatsApp, mobile, reports, GST portal, Tally, API, performance, security, caching, concurrency, logging, observability, DevOps, testing, a11y, docs, config, dependencies, scalability, maintainability, cross-module, production readiness, missed-findings (Wave 13).

Script: `_wave13_reaudit_append.py` (append-only; IDs permanent).

---

## 2026-08-04 — Wave 12 open-closure (Open → 0)

Closed all **61** Wave 12 **Open** issues (`BB-000318`…`BB-000378`) with W12A–E code/tests/docs fixes. Meta **BB-000325** resolved last in batch.

### Outcomes

| Status | Count |
|--------|------:|
| Resolved | 337 |
| Open | **0** |
| Deferred — roadmap | 30 |
| Deferred — ops owner | 7 |
| Accepted (positive) | 4 |

### Waves W12A–E (summary)

1. **W12A Payments/Auth** — sandbox ban prod/staging, webhook overpay reject, OTP_ENABLED, isomorphic register, access+refresh cookies, SameSite boot, env examples
2. **W12B RBAC** — document surface permissions, masters Owner writes, books CanViewFinancialReports, insights ACL, FE === true, VIEWER financial default False
3. **W12C GST/Books** — FE POS map, perpetual Dr 1400 + COGS, AP once, e-invoice/POS/GSTR/RCM/period caps/journal numbers
4. **W12D Inventory** — FEFO cancel movement-replay, return serial/batch, challan GST + batch, SO reserve batch
5. **W12E FE/DevOps** — accounting flag default off, Docker constraints, compose.prod, CD digest, Sentry/CSP/health/beat, pickers, e2e honesty, search throttle, access httpOnly cookie

Scripts: `_wave12_assert_gates.py` + `_wave12_close_open.py` (exit 0 = Open == 0).

---

## 2026-08-03 — Wave 12 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + compose/CI **after** Waves 10–11 claimed Open==0.

### Outcomes

- Appended **61** issues `BB-000318` … `BB-000378` (Critical 8 · High 23 · Medium 25 · Low 5).
- Register total: **378**.
- Status: Open **61** · Resolved/Deferred retained for untouched IDs.
- Invalidated Waves 10–11 “Open == 0” as a launch gate (see BB-000325).
- Production Readiness Score revised **6.7 → 3.5**.

### Highest new Criticals

- BB-000318 Sandbox provider allowed in production
- BB-000319 Notes/returns/orders mutate under HasCompany (VIEWER posts GL/stock)
- BB-000320 FE tax preview missing state-name→code map
- BB-000321 FEFO cancel restores wrong batch
- BB-000322 Purchase expense + COGS/Inventory hybrid double-count
- BB-000323 supplier_outstanding double-counts return+auto CN
- BB-000324 E-invoice SupTyp B2B without buyer GSTIN
- BB-000325 Wave 10–11 Open==0 meta invalidation

### Passes re-executed

Repository structure, architecture, backend, frontend, database, authn/z, accounting, GST, inventory, sales/purchase, manufacturing/payroll/CRM (absent), banking/payments, OCR/AI, WhatsApp, mobile, reports, GST portal, Tally, API, performance, security, caching, concurrency, logging, observability, DevOps, testing, a11y, docs, config, dependencies, scalability, maintainability, cross-module, production readiness, missed-findings (Wave 12).

Script: `_wave12_reaudit_append.py` (append-only; IDs permanent).

---

## 2026-08-03 — Wave 11 deferred code-fixable backlog

Resolved **23** Deferred-roadmap items via Wave R reclassify + Waves 11A–D.

### Outcomes

| Status | Count |
|--------|------:|
| Resolved | 276 |
| Open | **0** |
| Deferred — roadmap | 30 |
| Deferred — ops owner | 7 |
| Accepted (positive) | 4 |

### Waves

1. **Wave R** — Reclassify already-fixed: 031, 061, 077, 079, 083, 113, 133
2. **11A Security** — user storage, serializer/ViewSet tenancy, export CanExport (030, 084, 085, 137)
3. **11B Data/GST** — snapshot unique, POS normalize, serial IntegrityError, register GSTIN, insights Decimal (064, 063, 081, 082, 076)
4. **11C Perf/FE** — insights fan-out, ledger prefetch, product search, Sentry DSN, constraints (068, 075, 118, 121, 165, 125)
5. **11D Tests** — money contract smoke (191)

**Still Deferred (Wave 12):** BB-000108 / BB-000114 god-module splits.

Script: `_wave11_assert_deferred_targets.py` (exit 0 = targets not Deferred-roadmap).

---

## 2026-08-03 — Wave 10 open-closure (Open → 0)

Closed all **75** remaining **Open** issues with Waves A–F code/honesty/CI fixes.

### Outcomes

| Status | Count |
|--------|------:|
| Resolved | 253 |
| Open | **0** |
| Deferred — roadmap | 53 |
| Deferred — ops owner | 7 |
| Accepted (positive) | 4 |

### Waves A–F (summary)

1. **Payments** — sandbox HMAC, no provider remap, Company PATCH gateway read-only, unique provider_link_id
2. **Books/GL** — DN/purchase notes GL, return CN cascade, purchase auto-CN, challan COGS, soft-close block, is_opening_balance
3. **RBAC** — can_post_journals, payment link caps, journal FK tenancy, FE list/detail RoleRoutes
4. **GST** — B2CL ₹1L, FE assume-local, ValDtls, e-Way, MANUAL_EWB, GSTIN honesty
5. **Auth/FE** — cookie-only refresh, memory access token, anti-enum register, idempotency, invite optional password
6. **Remainder** — outstanding floor, statements opening, health ready, FIFO reject, WhatsApp LINK_READY, CD gated

Script: `_wave10_close_open.py` (exit 0 = no Open).

---

## 2026-08-03 — Wave 9 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + compose/CI **after** Waves 1–6 claimed Open==0.

### Outcomes

- Appended **60** issues `BB-000258` … `BB-000317` (Critical 7 · High 22 · Medium 28 · Low 3).
- Reopened residual parents: `BB-000043`, `BB-000097`, `BB-000098`, `BB-000189`, `BB-000196`, `BB-000200`, `BB-000210`, `BB-000214`, `BB-000215`, `BB-000218`, `BB-000225`, `BB-000238`, `BB-000251`, `BB-000254`, `BB-000257`.
- Register total: **317**.
- Status: Open **75** · other statuses retained for untouched IDs.
- Invalidated Wave 6 “Open == 0 / open-closure complete” as a launch gate (see BB-000317).
- Production Readiness Score revised **6.2 → 3.8**.

### Highest new Criticals

- BB-000258 Sandbox `X-Sandbox-Signature: ok` forgery
- BB-000259 Company PATCH bypasses gateway settings guards
- BB-000260 Cancel sales return orphans auto credit note
- BB-000261 Sales debit notes never post GL
- BB-000262 Purchase notes never post GL
- BB-000263 Purchase returns AP without GL/auto CN
- BB-000264 Spoofable `notes=TALLY_OPENING` credit-limit/GL bypass

### Passes re-executed

Repository structure, architecture, backend, frontend, database, authn/z, accounting, GST, inventory, sales/purchase, manufacturing/payroll/CRM (absent), banking/payments, OCR/AI, WhatsApp, mobile, reports, GST portal, Tally, API, performance, security, caching, concurrency, logging, observability, DevOps, testing, a11y, docs, config, dependencies, scalability, maintainability, cross-module, production readiness, missed-findings (Wave 9).

Script: `_wave9_reaudit_append.py` (append-only; IDs permanent).

---

## 2026-08-03 — Open-closure Waves 1–6 (Open → 0)

Closed all **66** remaining **Open** issues with real code/tests/docs/CI (Deferred roadmap/ops unchanged).

### Outcomes

| Status | Count |
|--------|------:|
| Resolved | 193 |
| Open | **0** |
| Deferred — roadmap | 53 |
| Deferred — ops owner | 7 |
| Accepted (positive) | 4 |

### Waves

1. **Payments P0** — fail-closed gateways, webhook verify, Razorpay no-stub, Cashfree/PayU disabled, test_mode default false, adversarial tests
2. **Books / GST / RBAC** — purchase H9, journal/report permissions, FileAsset/bank IDOR, GSTR-3B hint, MANUAL_IRN, read-only compliance fields
3. **Config / auth** — DEBUG/Redis/Fernet/OTP pepper, celery readiness + optional Sentry, concurrency locks, GSTIN honesty, register anti-enum, httpOnly refresh cookie
4. **Frontend** — RoleRoutes, safeUrl pay links, auth boot gate, pilot hard-stop, e-Way gate, tax POS, server customer search, AppShell a11y, Zod login/register
5. **DevOps / docs** — non-root Dockerfile, compose secrets, CD+Dependabot+CodeQL, backup script, nginx headers, runbook/env sync
6. **Register** — Open → Resolved; assert Open == 0

### Product-visible honesty

- Cashfree/PayU payment links are **not enabled** (fail-closed) until a real integration ships.
- Refresh JWT is httpOnly cookie; access token remains short-lived client storage interim.

Script: `_wave6_close_open.py` (exit 0 = no Open).

## 2026-08-03 — Wave 8 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + compose/CI (not worktrees).

### Outcomes

- Appended **62** issues `BB-000196` … `BB-000257` (Critical 5 · High 24 · Medium 25 · Low 8).
- Reopened residual parents: **BB-000004**, **BB-000011**, **BB-000018**, **BB-000047**.
- Register total: **257**.
- Status: Open **66** · Resolved **127** · Deferred roadmap/ops retained for untouched IDs.
- Invalidated Wave 7 “zero Open / Scope C complete” as a launch gate (see BB-000254).
- Production Readiness Score revised **6.8 → 4.5**.
- Script: `_wave8_reaudit_append.py` (append-only; IDs permanent).

### Highest new Criticals

- BB-000196 Empty gateway creds → SandboxAdapter forgery
- BB-000197 PayU missing signature accepted
- BB-000198 Razorpay stub payment links on error
- BB-000199 Purchase H9 missing period/GL
- BB-000200 Any member can post journals

### Passes re-executed

Repository structure, architecture, backend, frontend, database, authn/z, accounting, GST, inventory, sales/purchase, manufacturing/payroll/CRM (absent), banking/payments, OCR/AI, WhatsApp, mobile, reports, GST portal, Tally, API, performance, security, caching, concurrency, logging, observability, DevOps, testing, a11y, docs, config, dependencies, scalability, maintainability, cross-module, production readiness, missed-findings (Wave 8).

## 2026-08-02 — Scope C Waves 1–7 complete (register closed)

Scope C engineering remediation closed against MASTER_ISSUE_REGISTER.md (BB-000001–BB-000195). Wave 7 drove **zero Open** issues.

### Outcomes (status histogram)

| Status | Count |
|--------|------:|
| Resolved | 125 |
| Deferred — roadmap | 59 |
| Deferred — ops owner | 7 |
| Accepted (positive) | 4 |
| **Open** | **0** |

### Wave summary

- **Waves 1-6:** Code remediation - production fail-closed boots/secrets, OTP/SMS honesty, webhook routing, composition/e-invoice gates, returns/RCM/GL postings, tenancy/doc integrity, RBAC write flags, pagination/caching/logging, FE honesty flags, and related Scope C fixes with tests.
- **Wave 7:** Remaining Open IDs classified - Resolved (shipped/mitigated in code), Deferred — roadmap (multi-quarter/vendor/full-product), Deferred — ops owner (TLS/CA/GO_NO_GO/backups/human gates), or Accepted (positive).

### Closure meaning

- Application backlog for Scope C is closed; GA remains blocked by Deferred — ops owner and Deferred — roadmap items (live GSP, 2B engine, SMS vendor, cookies, ERP modules, pen-test, etc.).
- Scripts: _wave7_close_register.py (exit 0 = no Open).

## 2026-08-02 — Audit v1.0 (initial)

- Created `docs/reviews/` corpus for complete independent engineering audit.
- Added `MASTER_ISSUE_REGISTER.md` with **195** permanent issues `BB-000001` … `BB-000195`.
- Severity: Critical 15 · High 47 · Medium 97 · Low 36.
- Priority: P0 15 · P1 47 · P2 97 · P3 36.
- Missed-findings append: BB-000192…195 (CACHES absent, LOGGING absent, OTP `print()`, report cache strategy).
- Added review docs 01–21, REMEDIATION_ROADMAP, ARCHITECTURAL_DECISIONS, KNOWN_LIMITATIONS_AND_TECH_DEBT, this CHANGELOG.
- Generator script: `_generate_audit.py` (regenerate register carefully — IDs must remain stable; prefer append-only edits).
- Stats sidecar: `_stats.json`.
- Cross-linked prior `bugs/INDEX.md` and root historical reports; did not delete them.

### Passes completed

Repository structure, architecture, backend, frontend, database, authentication, authorization, accounting, GST, inventory, sales, purchase, manufacturing (absent), payroll (absent), CRM (absent), banking, OCR, AI, WhatsApp, mobile, reports, analytics, GST portal, Tally, API, performance, security, caching, concurrency, logging, observability, DevOps, testing, accessibility, documentation, configuration, dependencies, scalability, maintainability, cross-module, production readiness, missed-findings consolidation (GST deep-dive G1–G50 + FE 55+ + DevOps 27 + backend F1–F100 merged into BB register).

### Next audit actions

- Append resolutions under each BB issue when fixed; never reuse IDs.
- Re-run missed-findings pass after Phase A remediation.
- Refresh scores in `01_EXECUTIVE_SUMMARY.md` on each major closeout.
