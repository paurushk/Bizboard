# Bizboard live quality audit — 2 Sep 2026 (evening)

Line-traced against the **current working tree**. Prior docs (`DEEP_QUALITY_LOG_2026-09-02.md`, night canvas N-ids) were used only as leads, then re-read in source.

**Count:** 206 findings · **10 P0** · **80 P1** · **60 P2** · **9 P3** · **21 UX** · **18 GAP** · **8 SUGG**

Interactive filterable copy: canvas `quality-audit-live-2026-09-02.canvas.tsx`.

## Method

- Read backend sales, purchases, payments, billing, accounts, GST, inventory, manufacturing, payroll, imports, search, celery RLS, compose, mobile, and web pages/offline/i18n.
- Did **not** assume a prior Q-id still existed. Several morning P0s are **closed** (listed below).
- Did **not** run the full pytest/e2e matrix in this pass; defects are from control-flow in source.

## Ship-blockers (P0)

| ID | Module | Location | Defect |
|---|---|---|---|
| E-001 | Payments | `payments/services.py:1302` + `tasks.py:61` | Sync refund key `bb-refund-sync-{gp.id}` vs outbox `bb-refund-outbox-{row.id}`. Gateway timeout then retry can **double-refund**. |
| E-002 | Payments | `payments/tasks.py:30-65` | Outbox never checks `gp.status==REFUNDED`. Webhook `skip_gateway` unwind + beat still refunds the provider. |
| E-003 | Payments | `payments/gateway.py:441-449` | Cashfree `x-webhook-timestamp` is **milliseconds**. Code compares to `datetime.timestamp()` (seconds); `age>300` rejects every live webhook. |
| E-004 | Payments | `payments/tasks.py:104-120` + `celery.py:117` | `retry_pending_gateway_refunds` has no `company_id`. FORCE RLS on `GatewayRefundOutbox` hides all rows. Stuck refunds never retry. |
| E-005 | Manufacturing | `manufacturing/services.py:215-297` + `accounting/services.py:1214-1256` | `issue_cost==0` → release skips Dr 1450. Complete invents `purchase_price×qty` and posts **Cr 1450**. Negative WIP / overstated FG. |
| E-006 | GST | `reporting/gst_returns.py:526-538,706-755` | E-com invoices `continue` before B2/HSN but stay in footing totals. Understated Table 12/B2, false `footing_discrepancy`, easy double-file with Table 15. |
| E-007 | GST | `ims_offline.py:91-107` + `gstr2b.py:144-159` | Offline IMS trusts client `ims_action` / `itc_eligibility` / `match_status`. GSTR-3B can show claimable ITC with no GL reclass. |
| E-008 | Mobile | `capacitor.config.ts` + `web/src/api/client.ts:14` | Packaged app uses relative `/api/v1` on a Capacitor `https://` origin. Play/APK cannot reach Django. |
| E-009 | Mobile | `accounts/views.py:89-112` + `settings.py:552` | JWT cookies default `SameSite=Lax`. Cross-origin WebView will not send httpOnly cookies even if API URL is fixed. |
| E-010 | DevOps | `docker-compose.prod.yml:42-47` | Prod API healthcheck `?ready=1` needs beat. Nginx waits on API; beat is a sibling. Cold deploy can fail forever. |

## Closed vs morning Q-log (do not re-open)

Q-001 `post_purchase` alias exists. Q-005 3.1(a) taxable uses `_all_sum`. Q-006 PATCH reactivate calls `_enforce_plan_seat_limit`. Q-007 ACTIVE checks `current_period_end` when set. Q-009 scoped FKs on serials/lots. Q-010 cancel **deletes** AVAILABLE serials (not SCRAPPED). Q-011 multi-line `source_takes`. Q-012 payroll re-complete starts from `emp.salary`. Q-023 `cu is None` fail-closed. Q-028 DAMAGED_SCRAP reversed. Q-030 thermal uses stamp GSTIN + prints TCS. Q-031 CN PDF TCS/cess. Q-033 challan→invoice copies cess/HSN. Q-040 purchase HSN hard-fail. Q-057 IMS deemed-ACCEPT removed. Q-090 all linked challans restored. Q-095 NULL e-way claim. Books unwind **after** gateway on the happy path (dual-key E-001 is the new refund P0).

## P1 (wrong books / broken flow)

E-011 Purchase H9 dual GL, no outer atomic · E-012 Cancelled SO resurrected by draft challan complete · E-013 Challan→invoice NON_GST when `Company.gstin` blank · E-014 CN headroom race · E-015 Sales H9 dual COGS (Q-024) · E-016 e-Way in_flight 200 (Q-035) · E-017 Note e-invoice validates full invoice (Q-036) · E-018 Purchase auto-CN first SKU line · E-019 Purchase auto-CN ratio=1 on 0 taxable · E-020 SO→invoice always B2B / untaxed freight · E-021 FEFO line stores first lot only · E-022 Unbatched `already_lot` (Q-025) · E-023 Quotation→invoice drops commercial header (Q-034) · E-024 Partial refunds share one sync key · E-025 One outbox row overwrites amount · E-026 Plan switch before Razorpay confirm · E-027 ACTIVE + null `current_period_end` never blocks · E-028 Receipt idempotency check-then-act · E-029 OTP consumed before eligibility checks · E-030 Seat `select_for_update` outside atomic · E-031 Celery doc-id SELECT before RLS GUC · E-032 AR dunning beat dead under RLS · E-033 Cashfree `float` money · E-034 Holding off + closed period drops captures · E-035 Stale idempotency reclaim · E-036 Razorpay `authenticated` → ACTIVE · E-037 Refund health copy inverted · E-038 E-com CN/DN still in CDNR · E-039 3B “claimable” ignores IMS ACCEPT · E-040 2B upload/GSP/chase not Owner-gated · E-041 Blank 2B invoice_number always create · E-042 Period close misses null `released_at` · E-043 Supplier statement vs documents-basis outstanding · E-044 Sales RCM footing (Q-056) · E-045 Tally `force=` (Q-060) · E-046 Tally stale GSTIN (Q-061) · E-047 Tally recon whole-company (Q-119) · E-048 FEFO TOCTOU (Q-104) · E-049 `rebuild_balance` one lot (Q-106) · E-050 Manual serial scrap desync · E-051 `receive` revives SCRAPPED · E-052 Price slab overlap (Q-120) · E-053 IMS GET writes · E-054 Chase WhatsApp fake REQUESTED · E-055 POS online allocation no idempotency · E-056 Invoice Complete receipt/alloc no keys · E-057 Purchase offline pay/alloc no keys · E-058 Stock transfer flush no key · E-059 Mark-fully-paid client totals (Q-068) · E-060 Invoice detail Complete without create ACL · E-061 Purchase editor no GSTIN picker · E-062 POS online drops `cessRate` · E-063 UPI backdrop vs Collect later · E-064 Journals/periods silent mutation errors · E-065 Search purchase → `/sales/history/:id` · E-066 Import missing date = today · E-067 PDF page truncate silent · E-068 Bill import ignores create idempotency · E-069 Push/scan vapor on Capacitor · E-070 `VITE_API_BASE` vs `VITE_API_BASE_URL` · E-071 ClamAV unwired · E-072 CI skips prod compose + mobile APK · E-073 Party import duplicates · E-074 GSTR-4/CMP-08 no FE routes · E-075 AA APIs no UI · E-076 Insights FE/BE ACL drift (Q-063) · E-077 H9 omitted keys (Q-022) · E-078 Backup vs wipe gap (Q-015/177) · E-079 Untaxed freight still in grand_total · E-080 Assets/periods first page only · E-081 `fetchAllPagesMasters` 500-page silent stop · E-082 POS client totals only · E-083 Switch company no JWT blacklist (Q-014) · E-084 Partial refunds stay CAPTURED (Q-042) · E-085 Refund JE returns full MDR (Q-043) · E-086 FEFO shortfall policy (Q-047) · E-087 WO `component_lines` read_only (Q-051) · E-088 CRM re-convert ignores amount · E-089 Async IRN success-shaped in_flight · E-090 Stale PRODUCTION_READINESS scores.

## P2 / P3 / UX / GAP / SUGG

Full file:line text is in the canvas register (filter by severity). Highlights:

- **P2 money/docs:** quotation series burn, CN TCS headroom, scrap COGS by qty, challan leftover COMPLETED after invoice cancel, PO→bill default GSTIN, PayU/Razorpay replay, fee=0 Cashfree/PayU, OTP burn on SMS fail, PF ceiling not LOP-prorated, AT rate_unknown, bulk IMS not one txn, FIFO WARN synthetic peels, WO cancel ghost FG serials, search too narrow, bill commit drops cess/batch/serial, thermal print swallow, AA first-UTR, RLS default off.
- **UX:** purchase footer client vs preview mix, journals/billing/auth English, HSN hidden on xs, GSTR stubs in routes, GST settings Owner-only vs accountant reports, Help v2 vs v0, unsaved-changes = lines only, Complete grey with no reason, outbox ungated PII.
- **GAP:** GSTR-4/6/7/8/9 not engines; no billing portal; push unused; manufacturing/payroll/CRM MVP; no Form 16/24Q; HSN catalog toy; no cash drawer; invite not emailed; `books_start_date` / `doc_number_scope` not in UI; thin e2e/RLS CI.
- **SUGG:** E-199–E-206 fix order (refund keys, e-com GSTR, FE idempotency, SO/challan, WIP JE pair, mobile same-site, i18n CI, ops alerts).

## Suggested fix order

1. One refund idempotency key per payment+amount; skip if `REFUNDED`; pass `company_id` on beat.
2. Cashfree timestamp: ms/1000 (or digit-length detect).
3. WIP complete must not Cr 1450 unless release Dr exists.
4. E-com GSTR routing + offline IMS ignore client ITC; Owner-gate 2B mutate.
5. Refuse challan complete if SO CANCELLED; use CompanyGstin for convert tax type.
6. One atomic for purchase H9 GL.
7. Idempotency on every FE receipt/allocation/payment/transfer.
8. Mobile: same-site API **or** stop claiming a shipping app.
9. Prod health liveness without beat; CI `compose -f docker-compose.prod.yml config`.
10. i18n + pagination on accounting lists.

## What this pass did not do

- Full pytest / Playwright golden / load test.
- Line-by-line of every migration and every i18n string.
- Re-derive the entire morning Q-101–Q-206 table when the same file:line was already confirmed still-open (those are folded into E-ids above).
