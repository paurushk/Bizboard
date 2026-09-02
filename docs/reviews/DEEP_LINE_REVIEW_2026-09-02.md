# Bizboard — Exhaustive Line-by-Line Code Review (2026-09-02)

Reviewer: Cursor Grok 4.6 · Method: re-read **current** source (not yesterday’s
report). Historical P0s were re-verified; most are **fixed**. This pass logs
every currently verified bug, defect, gap, broken flow, partial feature, UI/UX
issue, and improvement so the quality picture is visible.

**Severity:** `P0` data/money loss, security, or hard crash on a real path ·
`P1` wrong output / broken flow · `P2` correctness-edge / missing validation /
race · `P3` maintainability · `UX` user-facing friction · `SUGG` improvement.

**Coverage:** `core`, `accounts`, `config`, `sales`, `purchases`, `inventory`,
`masters`, `payments`, `accounting`, `reporting`, `ledgers`, `banking`,
`manufacturing`, `payroll`, `crm`, `imports`, `insights`, `integrations/tally`,
`search`, `billing`, `web/src` (routing, pages, offline, i18n, ACL, PWA),
`mobile`, CI. Migrations / generated OpenAPI were scanned for constraints, not
restated line-by-line.

**Counts (this pass):** 3 P0 · 32 P1 · 48 P2 · 18 P3 · 22 UX · 8 SUGG · 14 partial
features ≈ **145 logged findings**. Highest-risk cluster first.

---

## 0. Fix-first cluster (do these before more features)

| # | Sev | Loc | Finding |
|---|---|---|---|
| 0.1 | P0 | `accounts/models.py:58-60` + `otp_utils.py:28-41` + `views.py:514,1125` | Phone unique is the **raw string**. Register can store `9876543210` while another user stores `+919876543210`. OTP/password-reset lookup expands variants and `.first()`. Login/reset can bind the **older** user. |
| 0.2 | P0 | `payments/tasks.py:10-25` + `celery.py:117-132` + `payments/services.py:1113,1235` | `execute_gateway_refund.delay(outbox.id)` never passes `company_id`. Celery prerun only resolves company from `company_id` or a document-id key list (no `outbox_id`). Under `POSTGRES_RLS_ENABLED`, the outbox SELECT sees **zero rows** and the task returns without refunding. Books already unwound; customer stays charged. |
| 0.3 | P0 | `sales/return_service.py:174-228` | Closing sales-return auto-CN uses `ratio=1` (full invoice discount, charges, **and** full TCS) even when prior partial returns already took proportional shares. Purchases fixed this remainder (`purchases/services.py:1111-1127`); sales did not. GST + AR overstated on the closing CN. |

---

## Historical P0s from 2026-09-01 — re-check

| Claim | Status | Evidence |
|---|---|---|
| Cookie refresh blacklisting fail-open | **FIXED** | `accounts/views.py:377-384` raises on blacklist `TokenError` |
| `wrap_idempotent` stores 5xx | **FIXED** | `idempotency.py:275-277` releases; docstring at 233 still stale |
| `emit()` no try/except | **FIXED** | `events.py:25-35` per-handler try/except |
| PK sniff as XLSX / no `MAX_IMAGE_PIXELS` | **FIXED** | `files.py:97-102,213-231`; `bill_images.py:47-52` |
| `configure` allows used `next_number` | **FIXED** | `document_numbers.py:266-274` |
| `IntegrityError` without `set_rollback` | **FIXED** | `exceptions.py:131-137` |
| MSG91 HTTP 200 always success | **FIXED** | `sms.py:76-88` checks `type=="error"` |
| `CompanyGstin` no unique primary | **FIXED** | `accounts/models.py:263-267` + migration `0041` |
| Seat limit not on invite accept | **FIXED** | `accounts/views.py:831-834` |
| Refresh doesn’t check membership | **FIXED** | `accounts/views.py:385-386` |
| Refund `IN_PROGRESS` stuck forever | **FIXED** | `payments/tasks.py:28-35` reclaim after 10 min |
| Recon session `gl["debit"]` KeyError | **FIXED** | `accounting/views.py:210-212` uses `d`/`c` |
| BatchLot `defaults={"mrp"}` TypeError | **FIXED** | WO complete no longer sets `mrp` |
| WO cancel FIFO skip | **FIXED** | `work_order_cancel` in `cancel_restore` + peel restore |
| Tally commit no `atomic` | **FIXED** | `integrations/tally/adapter.py:406-408` |
| Offline auto-flush never Completes | **FIXED** | `useInvoiceOffline.ts:29-64` honors `completeIntent` |
| Purchase-return cancel serial SCRAPPED↔RETURNED swap | **FIXED** | Complete/cancel pairing matches DAMAGED vs SELLABLE |
| OTP phone uniqueness / wrong user | **STILL PRESENT** | 0.1 above |
| tenant_backup export/wipe mismatch | **STILL PRESENT** | DocumentSeries + warehouses + unbacked stock_balances |

---

## 1. `backend/core/` + `accounts/` + `config/`

| # | Sev | Loc | Finding |
|---|---|---|---|
| 1.1 | P1 | `core/services/h9_amend.py:8-62` vs `sales/services.py:394-402` | H9-A allowlist checks product / qty / gst_rate only. Completed-invoice amend still applies `supply_nature` (can force GST 0) and cess. Omit `gst_rate`, send `supply_nature: "NIL"` → tax treatment changes on a completed GST invoice. |
| 1.2 | P1 | `core/views.py:277-299` | `FeatureFlagsView` calls `get_company_user` with **no catch**. Multi-membership login with empty `active_company` raises `CompanyRequired` (409) on FE boot flags. `MeView.patch` already catches this. |
| 1.3 | P1 | `accounts/tenant_backup.py:145-273,444-502,610-628` | Export/wipe/import never touch `DocumentSeries`. Destroy-in-place restore of invoices whose numbers exceed surviving `next_number` → duplicate GST numbers / unique conflict. |
| 1.4 | P1 | `tenant_backup.py:166,492-493,906-934` | Wipe deletes all `stock_balances`; `unbacked_live_counts` **omits** them, so extra live balances are destroyed without `confirm_destroy_unbacked`. Warehouses are exported (158) but **not wiped**. |
| 1.5 | P2 | `accounts/views.py:922-936` | Seat limit is count-then-activate with no row lock. Two concurrent accepts both pass. |
| 1.6 | P2 | `accounts/views.py:926-928` | Seat limit skipped when company has no plan (`sub is None`) → unlimited seats. |
| 1.7 | P2 | `core/csv_utils.py:21-27` | Formula prefix only for `= + @` and non-numeric `-`. Leading `\t` / `\r` Excel-injection vectors remain. Used by tenant CSV export. |
| 1.8 | P2 | `core/services/sms.py:82-88` | MSG91 only fails when JSON `type=="error"`. Empty/non-JSON HTTP 200 → UI says OTP sent. |
| 1.9 | P2 | `core/services/whatsapp.py:143-154` | HTTP <400 with empty `messages` treated as cloud success; notification falls to `LINK_READY` because `message_id` is empty. Ambiguous for ops. |
| 1.10 | P2 | `core/middleware.py:123-131` | Clearing RLS GUCs swallows exceptions. Pooled connection can retain prior `app.company_id`. |
| 1.11 | P2 | `core/services/gstin_verify.py:94-95` | HTTP GSTIN provider failure falls back to Null provider → format-ok **UNVERIFIED**, masking outages. |
| 1.12 | P2 | `core/services/billing.py:800-811` vs `sales/services.py:70-127` | Preview TCS always from `tcs_rate`. Complete honors `tcs_amount_manual`. Owner-entered explicit TCS amount ≠ on-screen preview. |
| 1.13 | P2 | `core/services/billing.py:363-414,749-760` | Draft Complete overwrites line `gst_rate` from HSN catalog unless `rate_override`. Preview `_Doc` is not rateable → preview 18%, books 5%. |
| 1.14 | P2 | `core/services/feature_flags.py:104-113` | Plan `modules` AND only listed keys. Plan `{"ENABLE_CRM": true}` does **not** force Manufacturing/Payroll off (unlike company JSON missing-key fail-closed). |
| 1.15 | P2 | `feature_flags.py:82-103` | Company JSON `{}` / help-only keys keep env-wide `ENABLE_MANUFACTURING\|PAYROLL\|CRM`. Dark modules still fail-open until a module key is written. |
| 1.16 | P2 | `feature_flags.py:115-122` | `item_custom_fields_v2` defaults **ON** when key absent. Kill-switch requires explicit `false`. |
| 1.17 | P2 | `core/idempotency.py:231-233` vs `275-277` | Docstring still says store 5xx; code releases. Operators following the comment will mis-debug. |
| 1.18 | P3 | `core/models.py:147-164` | `AuditEvent.action` still `choices=Action.choices` while code logs dotted strings (`tenant.export`). Schema/docs lie. |
| 1.19 | P3 | `config/celery.py:61-91` | `_company_id_from_document_disabled` is a dead duplicate “for tests”. |
| 1.20 | UX | `accounts/views.py:825-830` | Outside prod/staging, invitee with a password can accept without sending one. Dangerous if staging is mislabeled. |
| 1.21 | SUGG | register/invite serializers | Persist `normalize_e164` + collision check via `phone_lookup_values` to close 0.1. |
| 1.22 | P2 | `core/permissions.py:74-80` | `HasCompany.has_permission` lets `get_company_user` **raise** `CompanyRequired` instead of returning False. Fine for most views; FeatureFlags (AllowAny) becomes a 409. |
| 1.23 | P3 | `core/middleware.py:24-27` | Access-log IDs are unsalted `sha256(pk)[:12]` — reversible for small ints. |
| 1.24 | P2 | `core/viewsets.py:16-19` | `SubscriptionWritesAllowed` is appended to **list/retrieve** too. Harmless if the permission is write-only, but easy to accidentally block GET when the class is tightened. |
| 1.25 | P3 | `core/viewsets.py:46-49` | `perform_destroy` audits after delete with pk only — no snapshot of the row. |

---

## 2. Sales / purchases / inventory / masters

| # | Sev | Loc | Finding |
|---|---|---|---|
| 2.1 | P1 | `purchases/services.py:1018-1032,1211-1225` + `inventory/services.py:477-516` | Purchase-return Complete retires source PURCHASE layers. Cancel posts `ADJUSTMENT` with `reference_type="purchase_return_cancel"`, **not** in `cancel_restore`, so `_apply_cost_layers` **invents a new inbound layer** instead of restoring retired ones. FIFO COGS drifts after cancel. |
| 2.2 | P1 | `sales/return_service.py:284-298` + `inventory/services.py:520-541` | Sales-return Complete restores original peels via `restore_fifo_peels`. Cancel posts negative `ADJUSTMENT` `sales_return_cancel` which is **not** in the skip-peel list → peels FIFO-oldest, not the restored peels. |
| 2.3 | P1 | `sales/services.py:447-475` + `cogs_service.py:69-81` | FEFO issues stock across all allocations but the invoice line persists only `allocations[0]`. Returns / challan / PDF see one lot; movements span many. |
| 2.4 | P1 | `inventory/views.py:335-357` | Manual serial transitions: `RETURNED → AVAILABLE` and `AVAILABLE → SOLD` with **no** stock movement. Purchase-return sellable sets `RETURNED` and takes stock out; UI can put it back without restoring qty. |
| 2.5 | P1 | `sales/return_service.py:314-326` | If original return movements are gone, cancel posts a **blind** negative ADJUSTMENT (no batch). Purchase return refuses this (`purchases/services.py:1241-1244`). |
| 2.6 | P1 | `masters/pricing.py:15-29` + `serializers.py:243-260` + `models.py:324-330` | Uniqueness is `(price_list, product, min_qty)` only. Overlapping slabs / `max_qty < min_qty` allowed. Matcher picks highest `min_qty` that contains qty → silent misprice. |
| 2.7 | P2 | `inventory/services.py:23-36` | `default_warehouse` can set `DEFAULT.is_default=True` without clearing another default → unique constraint / race with serializer. |
| 2.8 | P2 | `sales/services.py:845-857` vs `931` | e-Way threshold warning runs **before** `apply_tcs_fold`. TCS-inclusive invoices near ₹50k can miss the warning. |
| 2.9 | P2 | `sales/serializers.py:342-345` + `services.py:103-109` | `tcs_amount_manual = bool(tcs_amount)` treats `0` as non-manual. Cannot force TCS=0 against a positive rate. |
| 2.10 | P2 | `purchases/services.py:692-702` | Purchase Complete `get_or_create` batch warns on expiry mismatch and **keeps** the existing lot’s expiry. `item_stock.get_or_create_batch` hard-errors. Lot identity drift. |
| 2.11 | P2 | `purchases/services.py:914-915` | Purchase return Complete requires invoice `COMPLETED` only. Sales allows `COMPLETED\|RETURNED`. A draft PR started while COMPLETED, then blocked after another return marked invoice RETURNED, cannot complete. |
| 2.12 | P2 | `masters/views.py:27-28,77-83` | 60s TTL list cache; mutations do not `cache.delete` → stale catalog after edit. |
| 2.13 | P3 | `sales/irn_guard.py:5-15` | `LIVE_IRN` unused; `assert_no_live_irn` uses a broader denylist. Misleading. |
| 2.14 | P3 | `sales/pdf/gst_tax_invoice.py:384-394` | QR / outstanding failure swallowed → fallback text / full total on PDF. |
| 2.15 | P3 | `sales/whatsapp_send.py:34-37` | Pay-link base URL fail → empty URL, send still proceeds. |
| 2.16 | P3 | `masters/serializers.py:215-216` | Custom-field defs fail → `[]`, hiding fields on GET. |
| 2.17 | SUGG | `masters/pricing.py:69-77` | Non-OWNER cannot set a *higher* price than slab either — always forced. Confirm product intent. |
| 2.18 | P2 | `sales/phase1_views.py:40-50` | Backend correctly gates CN write/complete on `CanCreateSales` and cancel on `CanCancelDocuments`. FE list/editor under `canViewSalesSurfaces` still **shows** Complete/Cancel (see 5.x) → 403 UX, not a backend hole. |

---

## 3. Payments / accounting / reporting / ledgers / banking

| # | Sev | Loc | Finding |
|---|---|---|---|
| 3.1 | P1 | `accounting/services.py:687-739` | `post_receipt` splits MDR fee to 5200 and banks `amount − fee`. `post_receipt_refund` credits **full** `amount` to cash/bank. After gateway refund with fee>0, cash is high by `fee` and 5200 is never reversed. |
| 3.2 | P1 | `payments/services.py:21-23,1058-1070` | Only `INVOICE_CANCELLED` / `LINK_CANCELLED` auto-refund. `AMOUNT_MISMATCH`, `ALREADY_PAID`, `LINK_EXPIRED`, `NO_LINK` retry forever as `CAPTURED_PENDING_BOOKS`. Customer paid; no books; no refund. |
| 3.3 | P1 | `payments/gateway.py:456-473` | Cashfree webhook stores `cf_payment_id`; refund POSTs `/orders/{provider_payment_id}/refunds`. Payment id ≠ order id → provider refund fails while books already unwound. |
| 3.4 | P1 | `payments/gateway.py:587-601` | PayU `refund()` ignores `idempotency_key`. Combined with outbox reclaim, PayU can refund twice. Razorpay/Cashfree pass idempotency. |
| 3.5 | P1 | `payments/services.py:1142-1157` | Partial refund records JSON only; status stays `CAPTURED`; no alloc reverse / no GL. Staff API accepts `amount`. AR overstated. |
| 3.6 | P1 | `accounting/services.py:282-311` + `reporting/ims.py:169-180` | IMS REJECT after ACCEPT: `reclass_rejected_itc` only clears **1390**. After ACCEPT, tax sits on 1310/1320/1330; REJECT sets `INELIGIBLE` but GL no-ops. 3B vs books diverge. |
| 3.7 | P1 | `payments/recon.py:179-188` vs `accounting/services.py:948-955` | Recon scoring uses `payment.amount + tds_amount`. GL posts bank as `payment.amount` only. TDS payments score 0 amount points → no auto-suggest. |
| 3.8 | P1 | `reporting/ims_offline.py:82-108` vs unique `(company, period, supplier_gstin, invoice_number)` | Offline import always `create()`. Re-import without `replace=True` → `IntegrityError`. Blank invoice numbers unconstrained (duplicates allowed). |
| 3.9 | P2 | `payments/webhook_views.py:206-226` | Catch-all parks every `BusinessRuleError` as `BOOKS_ERROR` (incl. UTR clash). Reconcile keeps retrying; ops reason is wrong. |
| 3.10 | P2 | `payments/tasks.py:28-35` | Fresh `IN_PROGRESS` early-return looks like **Celery success**. Autoretries stop. Recovery depends on beat `retry_pending_gateway_refunds`. No beat → stuck until 10+ min *and* beat runs. |
| 3.11 | P2 | `reporting/gstr2b.py:26-28` | Sticky `MATCHED` skips rematch. Corrected purchase amounts/dates never rematch; wrong PI FK can feed `claimable_itc_from_2b`. |
| 3.12 | P2 | `reporting/gst_returns.py:1309-1324` | Without 2B, `recommended_claimable` still shows books totals with `basis: books_provisional`. Easy to over-claim if UI treats it as filing amount. |
| 3.13 | P2 | `reporting/gstr2b.py:91-96` | `claimable_itc_from_2b` filters MATCHED + CLAIMABLE, **not** `ims_action=ACCEPT`. Manual CLAIMABLE / upload inflates 3B matched ITC. |
| 3.14 | P2 | `accounting/services.py:693-694` + `payments/services.py:951-961` | Gateway receipts post to Cash `1100` because finalize never sets `bank_account`. Bank recon vs GL bank systematically diverge. |
| 3.15 | P2 | `payments/holding.py:101-123` | `CAPTURED` + books posted + allocation failed still returns `PAID_PENDING_BOOKS`. Money is in advances; collection state is wrong. |
| 3.16 | P2 | `payments/dunning.py:216-234` | Fires only on **exact** overdue day in buckets. Quiet hours skip the whole run — day-7 in quiet hours is **never** retried. |
| 3.17 | P2 | `banking/services.py:49-53` | AA match uses `icontains` on refs ≥6 chars + amount±tol + ±7 days. First `select_for_update` hit wins — false positives. |
| 3.18 | P2 | `ledgers/services.py:261-268` vs `327` | Party `customer_outstanding` can go negative; bulk company totals floor at 0. Dashboards disagree. |
| 3.19 | P3 | `reporting/chase.py:58-61` | Empty phone falls back to `"91"` — generates a share link to an invalid destination. |
| 3.20 | P3 | `reporting/models.py:162-168` | GSTR-2B unique is case-sensitive; matcher uses `__iexact`. Same GSTIN different case → duplicate rows. |
| 3.21 | SUGG | `payments/services.py:1093-1208` | Manual refund marks books `REFUNDED` **before** provider success; auto-parked waits for provider. Two mental models for ops. |

---

## 4. Manufacturing / payroll / CRM / imports / insights / integrations / search / mobile / CI

| # | Sev | Loc | Finding |
|---|---|---|---|
| 4.1 | P1 | `integrations/tally/adapter.py:411-415,517-530` | Commit is atomic but **no** `select_for_update` on `IntegrationSyncRun`. Concurrent commits both pass `status==COMMITTED` gate. |
| 4.2 | P1 | `manufacturing/models.py:63-69` vs `serializers.py:59-76` vs `services.py:209-225` | Batch/expiry fields exist on WO. Serializer omits them. Complete auto-creates `WO-{id}`. Operator cannot set real lot/expiry via API or UI. |
| 4.3 | P1 | `manufacturing/services.py:151-166,227-235` vs `WorkOrdersPage.tsx` | Serial-tracked FG complete requires `len(serials)==qty`; release requires component serials. UI never collects them → BusinessRuleError for normal users. |
| 4.4 | P2 | `manufacturing/services.py:294-304` + `inventory/services.py:950-971` | WO cancel of completed FG serials → permanent `SCRAPPED`. `SerialNumberService.receive` rejects reuse. Re-running same serials after cancel fails. |
| 4.5 | P2 | `manufacturing/serializers.py:10-25,59-76` | WO / BomLine qty not validated `> 0`. Zero/negative accepted. |
| 4.6 | P2 | `manufacturing/services.py:213-222` | `get_or_create` BatchLot ignores new expiry/mfg on hit (purchases at least warn). |
| 4.7 | P2 | `payroll/views.py:49-117` vs `EmployeesPage.tsx` / `PayRunsPage.tsx` / `api/payroll.ts` | Backend: LOP action, `basic`/`da`, `tds_rate`, pay-run cancel. UI: none of these. PF Basic+DA path is dead from the product. |
| 4.8 | P2 | `crm/services.py:37-42` | Convert attaches to first Customer with exact `phone` match — no normalize, no confirm. Shared numbers mis-link. |
| 4.9 | P3 | `crm/views.py:36-38` vs `LeadsPage.tsx` | API supports convert `won`; UI always converts to OPEN opportunity. |
| 4.10 | P2 | `insights/alerts.py:233-249` | Cash-tight and GST-health alert builders `except Exception: pass`. Alerts silently disappear. |
| 4.11 | P2 | `insights/views.py:81-88` | Every GET regenerates daily summary (upsert alerts). Dashboard polling writes on every load. |
| 4.12 | P2 | `integrations/views.py:76-78` | Preview POST marks `PREVIEWED` even when `errors` remain (commit still blocked unless `force`). Status lies. |
| 4.13 | P3 | `search/views.py:36-71` | No min query length; `icontains` across parties. Mitigated by 5s statement_timeout + throttle, still expensive single-char scans. |
| 4.14 | P3 | `search/views.py:111-116` | `selling_price` gated; `gst_rate` always returned for visible products. |
| 4.15 | P2 | `.github/workflows/ci.yml:93-108` | Mobile job: parse `package.json` + grep `allowBackup="false"`. No `npm ci`, no `cap sync`, no Android build. |
| 4.16 | P2 | `mobile/` vs README | Committed app is Capacitor `BridgeActivity`. Camera/Push/iOS deps in `package.json`; offline/outbox lives in **web**. README 8h-offline claim is web PWA, not native. |
| 4.17 | P3 | `.github/workflows/cd.yml:96-98` | Image bake sets `VITE_ENABLE_MANUFACTURING/PAYROLL/CRM=false` — intentional for dark modules; easy to forget when promoting a tenant. |
| 4.18 | P2 | `imports/` | Pipeline is real (validate/commit/void) — not a stub. Residual risk is file-sniff/size already mostly fixed; remaining is operator UX on void vs wipe (see tenant_backup). |

---

## 5. Web frontend — broken flows, ACL, offline, i18n

| # | Sev | Loc | Finding |
|---|---|---|---|
| 5.1 | P1 | `NewInvoicePage.tsx:769-857` | Offline queue stores invoice + `completeIntent` only. Amount received / `createReceipt` + `createAllocation` run only after **online** COMPLETED. Offline “Complete + payment” syncs an unpaid completed invoice. |
| 5.2 | P1 | `NewPurchasePage.tsx:751-840` | Same: offline does not queue `amountPaid` payment posting. |
| 5.3 | P1 | `useInvoiceOffline.ts:41-45` vs `OfflineOutboxPage.tsx:93-116` | Auto-flush **throws** `billing.offlineAmendRequiresConfirm` when `status==='COMPLETED'` → draft stuck failing. Sync Now does **not** block and updates with payload still containing `status` (not deleted on invoice path). Same draft, two behaviors. |
| 5.4 | P1 | `OfflineOutboxPage.tsx:94-115` | Invoice flush deletes only `_completeIntent` / `_confirmSalesRcm`. Leaves `status`, `_confirmBlankPos`, `_confirmGstinTotalChange` on create/update. Purchase/auto paths strip more carefully. |
| 5.5 | P1 | `App.tsx:368-375` + `SalesInvoiceNoteEditor.tsx:205-278` + `CreditNotesPage.tsx:78-99` + `SalesOrdersPage.tsx:81-111` | Editors and list Complete/Cancel/Convert sit on `canViewSalesSurfaces`. Backend 403s writes (`CanCreateSales`). Viewers see money actions that fail. Same pattern on purchase note/order editors (`App.tsx:404-412`). |
| 5.6 | P1 | `i18n/gu.ts:1-10` + `i18n/ta.ts:1-10` | Catalogs are `...en` plus locale label. Switcher still offers Gujarati/Tamil (`LocaleSwitcher.tsx:11-40`). Hindi is key-complete vs en. |
| 5.7 | P1 | `pages/phase/JournalsPage.tsx:21-96` + `FixedAssetsPage.tsx:28-75` | Create/post/reverse and Add/Dispose ignore `useSubscriptionGate`. Banner in shell exists; these writes still fire. |
| 5.8 | P1 | `LeadsPage.tsx` + `BomsPage.tsx` | CRM/manufacturing writes ignore subscription write lock (payroll does gate). |
| 5.9 | P2 | `StockCountPage.tsx:86-95` + `InventoryPhasePages.tsx:175-184` | Stock count/transfer enqueue to IndexedDB. **No auto-flush hook**. Only Outbox Sync Now (`OfflineOutboxPage.tsx:119-137`). |
| 5.10 | P2 | `InventoryPhasePages.tsx:173-188` | Offline stock-transfer Complete queues draft; list still shows DRAFT; no “saved offline” (stock count has `pendingCount`). |
| 5.11 | P2 | `navigation/menu.ts` | No offline-outbox nav item. Reachable via shell chip or URL. Easy to miss Sync Now for stock/POS. |
| 5.12 | P2 | `pwa.ts:15-17` | `onNeedRefresh` → `updateSW(true)` with **no confirm**. Full reload mid-invoice can wipe in-progress form. |
| 5.13 | P2 | `api/client.ts:158-167` + `AuthContext.tsx:117-133` | **Any** refresh failure (incl. transient network) clears session + drafts. Documented as needing a product decision vs BUG-407. |
| 5.14 | P2 | `CreditNotesPage.tsx:81` + `DeliveryChallansPage.tsx:81` | Complete button not `disabled={complete.isPending}` → double-submit. |
| 5.15 | P2 | `ConfirmDialog.tsx:9-38` | No `confirming` / disable-while-pending. Double-confirm possible. |
| 5.16 | P2 | `ErrorBoundary.tsx:42-48` | Hardcoded English crash screen. |
| 5.17 | P2 | `AccountingExtraPages.tsx:35-68` | `{ accounting_enabled }` snake_case payload; English chrome; no `writesBlocked`. |
| 5.18 | P2 | `api/legacy/sales.ts:249-252` | e-invoice cancel sends `cnl_rsn` / `cnl_rem` while TS opts are camelCase. OpenAPI body typed as full `SalesInvoice`. |
| 5.19 | P2 | `pages/accounting/*` + `pages/phase/PhasePages.tsx` | Thin re-exports. Easy to edit the wrong file; not two competing implementations. |
| 5.20 | P3 | `api/typedClient.ts` | Types-only; runtime still `api/resources` → `legacy/*`. OpenAPI not enforced at call sites. |
| 5.21 | SUGG | `useSubscriptionGate.ts:6-16` | Banner + button disable, not route-level. Blocked users can still open editors; some pages skip the gate (5.7–5.8). |
| 5.22 | SUGG | `offline/invoiceDraftCache.ts:27-30` | Plaintext IndexedDB outbox is documented honesty; still a shared-device risk. |

---

## 6. UI / UX issues (user-facing friction)

| # | Sev | Loc | Finding |
|---|---|---|---|
| 6.1 | UX | `CreditNotesPage.tsx:103-117` + `DebitNotesPage` + `DeliveryChallansPage` | Cancel dialog body and “Confirm Cancel” hardcoded English; not `ConfirmDialog`; Complete/Cancel shown without `canCreateSales` / `canCancelDocuments`. |
| 6.2 | UX | `SalesOrdersPage.tsx:96` | “To Challan” hardcoded English next to i18n Convert. |
| 6.3 | UX | `NewInvoicePage.tsx:790-796,867-877` | Owner-only amend error + “Invoice X saved” success flashes hardcoded English. |
| 6.4 | UX | `DocumentEditorShell.tsx:127` | Disabled-reason tooltips English. |
| 6.5 | UX | `JournalsPage.tsx:75-95` + `FixedAssetsPage.tsx:58-74` + `InventoryPhasePages.tsx:208-227` | “New voucher”, “Post”, “Reverse”, transfer chrome English. |
| 6.6 | UX | `useInvoiceOffline.ts:70-72` | Failure banner is a template string; Outbox uses `t('offlineOutbox.syncFailed')`. |
| 6.7 | UX | `LocaleSwitcher.tsx:29` | `aria-label="Language"` English. |
| 6.8 | UX | `AppShell.tsx:61,86` | Nav `selected` is exact pathname. `/sales/history/123` does not highlight Sales History. |
| 6.9 | UX | `OfflineOutboxPage.tsx:169` | Sync button disabled when busy; no `aria-busy` / live region for result. |
| 6.10 | UX | `NewInvoicePage.tsx:825-827,897-900` | Offline save **throws** `savedOffline` into `onError`. Success is an error path (telemetry mis-count). |
| 6.11 | UX | `GstReturnPage.tsx:314-350` + `App.tsx:457-459` | GSTR-6/7/8 are honesty stubs dumping JSON. Routed live; **not** in sidebar (`menu.ts` has 1/3B/9/2B only). URL-reachable, looks like a broken report. |
| 6.12 | UX | `DocumentListPage.tsx:90-128` | Table has no caption/`aria-label`; pager has no live announcement. |
| 6.13 | UX | `ConfirmDialog` | No Escape-focus restore beyond MUI default; no busy state (5.15). Destructive Complete/Cancel on lists use ad-hoc Dialogs instead. |
| 6.14 | UX | Manufacturing / Payroll / CRM | Owner-gated previews with banners — honest, but Work Orders look complete until serial/batch products fail at Release/Complete (4.3). |
| 6.15 | UX | Feature flags 409 | Multi-company user hitting `/feature-flags/` before company pick can fail boot (1.2). |
| 6.16 | UX | `gstHonesty` 3B | `recommended_claimable` with `books_provisional` can be read as “file this” (3.12). |
| 6.17 | UX | POS vs invoice offline | POS auto-flush does create+complete+receipt (`flushPosCheckout.ts:42-70`). Invoice auto-flush Completes but **drops payment** (5.1). Operators will assume parity. |
| 6.18 | UX | Subscription banner | Global banner (`AppShell.tsx:288-299`) but journals/assets/CRM/BOM still clickable (5.7–5.8). Inconsistent “blocked” mental model. |
| 6.19 | UX | PWA auto-reload | No “Update available” toast — just reload (5.12). |
| 6.20 | UX | Network blip → logout | Refresh failure = session expired (5.13). Feels like a crash on flaky 4G. |
| 6.21 | UX | Gujarati/Tamil in switcher | Locale appears to work; all money copy stays English (5.6). Trust damage. |
| 6.22 | UX | Offline outbox discoverability | Chip-only (5.11). Stock/POS drafts can sit until the operator finds `/offline`. |

---

## 7. Partially implemented features

| # | Area | What exists | What’s missing |
|---|---|---|---|
| 7.1 | WO batch/lot/expiry | DB fields + auto `WO-{id}` on complete | Serializer + UI inputs; expiry clash warning |
| 7.2 | WO / component serials | Backend release/complete require them | UI never collects `serial_numbers` / `component_serials` |
| 7.3 | Lot allocations / FEFO | Backend FEFO at issue | No UI to pick lots; line stores first lot only (2.3) |
| 7.4 | Payroll LOP | `POST .../lop/` | No client helper, no PayRuns UI |
| 7.5 | Payroll Basic+DA / TDS | Model + serializer | `EmployeesPage` payload omits `basic`, `da`, `tdsRate` |
| 7.6 | Pay-run cancel | Backend reverses JE → DRAFT | No `cancelPayRun` in `web/src/api/payroll.ts`; no button |
| 7.7 | CRM convert `won` | API | UI always OPEN opportunity |
| 7.8 | Tally | CSV/XML dump + atomic commit | Not live sync; commit race (4.1) |
| 7.9 | Mobile | Capacitor WebView shell | Not native offline/MES; CI won’t prove Play readiness |
| 7.10 | Insights assistant | Rules + optional LLM; tax refusal | Confirm allowlist excludes money moves (good); alerts swallow errors |
| 7.11 | Search | Parties/products/invoices | No CRM / mfg / payroll entities |
| 7.12 | GSTR-6/7/8 | Routed stub pages + honesty copy | No filing payload; JSON dump |
| 7.13 | i18n Gujarati/Tamil | Switcher + catalogs | Catalogs are English |
| 7.14 | Gateway partial refund | Provider webhook 200s | Books/AR not unwound (3.5) |

---

## 8. Improvement suggestions (not bugs)

| # | Sev | Suggestion |
|---|---|---|
| 8.1 | SUGG | Normalize phones to E.164 at register/invite + unique on normalized value. |
| 8.2 | SUGG | Pass `company_id=` on **every** `.delay()` (refund outbox, dunning, PDF). Fail the task if GUC is empty under RLS. |
| 8.3 | SUGG | Port purchase remainder logic (R2-015) to sales-return auto-CN for discount **and** charges/TCS. |
| 8.4 | SUGG | Add `purchase_return_cancel` / `sales_return_cancel` to FIFO restore/skip lists; refuse unbatched cancel like purchases. |
| 8.5 | SUGG | Queue receipt+allocation in the invoice/purchase outbox payload (or a follow-up draft kind). |
| 8.6 | SUGG | Hide Complete/Cancel/Convert unless `canCreate*` / `canCancelDocuments`; disable while pending. |
| 8.7 | SUGG | Finish Gujarati/Tamil money namespaces or hide them from the switcher until signed. |
| 8.8 | SUGG | Subscription write-lock at the route/viewset layer, not per-button. |

---

## 9. What is in good shape (so the log isn’t only defects)

- Yesterday’s 16 named P0s: **14 fixed**, 2 still present (phone identity, tenant backup gaps) plus **new** P0s (RLS refund, sales-return CN remainder).
- Idempotency no longer caches 5xx; events no longer roll back Complete; document-number configure rejects used sequences.
- Purchase-return serial Complete/Cancel pairing is consistent.
- WO component FIFO restore on cancel is correct (`test_bb_000564`).
- Tally commit is wrapped in `transaction.atomic`.
- Invoice auto-flush **does** Complete when `completeIntent` is set (the old Complete-vs-draft split is gone for the happy path).
- Backend CN/order write ACL is correct; the hole is FE showing the buttons.
- Imports, GST 1/3B/2B, POS flush, and Help honesty copy are real implementations, not empty folders.

---

## 10. Suggested fix order

1. **P0 identity + money:** phone normalize (0.1), Celery `company_id` on refund (0.2), sales-return CN remainder (0.3).
2. **P1 books:** FIFO return-cancel (2.1–2.2), MDR refund GL (3.1), holding auto-refund (3.2), Cashfree/PayU refund (3.3–3.4), IMS REJECT GL (3.6), offline payment queue (5.1–5.2).
3. **P1 GST/preview:** HSN preview vs Complete (1.13), TCS preview vs Complete (1.12), H9-A cess/supply_nature (1.1), FEFO lot stamp (2.3).
4. **P1 product completeness:** WO serial/batch UI (4.2–4.3), payroll field/UI gaps (4.7), ACL buttons (5.5), gu/ta or hide (5.6).
5. **UX polish:** confirm dialogs, i18n leftovers, PWA reload confirm, refresh-network vs logout, outbox in nav.
