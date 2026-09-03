# Bizboard quality log — 2 Sep 2026 (night pass)

Independent re-read of **current** source. Earlier same-day reports were not copied. Historical P0s that are **fixed** are listed at the bottom, not as open defects.

**Method:** static line review of live Python/TS (services, views, serializers, pages, CI). Not a live browser E2E pass. Migrations scanned for constraints only.

**Count:** 210 findings · 14 P0 · 86 P1 · 60 P2 · 12 P3 · 18 UX · 12 GAP · 8 SUGG

| ID | Sev | Module | Location | Finding |
|---|---|---|---|---|
| N-001 | P0 | Inventory | `inventory/services.py:612-647` + `sales/cogs_service.py:201-215` | Partial sales return posts `take` qty then `restore_fifo_peels` restores **every** peel on the original SALE movement. A 3-of-10 return puts 10 back on FIFO layers. Valuation qty > physical. |
| N-002 | P0 | Inventory | `sales/return_service.py:306-320` + `inventory/services.py:544-553` | Cancel posts negative `ADJUSTMENT` `sales_return_cancel`, which is in the skip-peel list. Layers inflated by N-001 (or a full restore) stay inflated after cancel. Purchase-return cancel restores layers; sales does not. |
| N-003 | P0 | Auth | `accounts/tenant_backup.py:449-526` + `payments/models.py:230,362` | Wipe deletes `CustomerReceipt` / `SalesInvoice` / `Product` / `Account` but never `PaymentLink`, `ReconMatch`, `Bom`/`BomLine`, `FixedAsset`, `GatewayRefundOutbox`. Those FKs are `PROTECT`. Destroy-in-place raises `ProtectedError` on any tenant that used payment links, bank recon, manufacturing, or fixed assets. |
| N-004 | P0 | Auth | `tenant_backup.py:930-994` | `unbacked_live_counts` omits the same PROTECT tables, so operators get no `UNBACKED_ROWS` warning before the crash. |
| N-005 | P0 | Auth | `accounts/views.py:235-255` | `RegisterView.post` is `@transaction.atomic` and catches `IntegrityError` from `create_user`. Django marks the connection for rollback; exiting the atomic block raises `TransactionManagementError` → 500 on concurrent email/phone races instead of the intended non-enumerating 200. |
| N-006 | P0 | Auth | `accounts/models.py:49-57` + `otp_utils.py:28-41` | `canonicalize_user_phone` `ValueError` stores the raw string. Unique is exact-string. `9876543210` and `+919876543210` can coexist. OTP/reset lookup expands variants and `.first()` — login/reset can bind the older user. |
| N-007 | P0 | Masters | `masters/views.py:154-241` vs `CustomersPage.tsx:81` + `ProductsPage.tsx` + `SuppliersPage.tsx` + `PosPage.tsx:684` + `flushPosCheckout.ts:27` | Customer/supplier/product mutate (and GSTIN verify) require `IsOwner`. FE shows Add/Edit to any non-VIEWER. POS walk-in and offline POS flush call `createCustomer`. Staff checkout **403s**. |
| N-008 | P0 | GST | `sales/einvoice_eway_actions.py:481-562` | `amend_filing_identity` updates filing GSTIN / POS with Owner + period checks only. No `assert_no_live_irn`. Money amend blocks live IRN; filing amend does not. Portal identity can diverge from the local stamp. |
| N-009 | P0 | Payments | `payments/services.py:1229-1315` | Staff refund reverses allocations, marks receipts `REFUNDED`, posts refund GL, then enqueues the gateway. Failed/stuck outbox = books refunded, customer still charged. |
| N-010 | P0 | Payments | `payments/services.py:1198-1216` | Provider partial refunds (`skip_gateway=True`) append JSON only. Status stays `CAPTURED`. AR/cash stay posted. Gateway money is back; books are not. |
| N-011 | P0 | Payments | `payments/tasks.py:112-117` + `config/celery.py:117-132` | `reconcile_gateway_captures_task` calls reconcile with no `company_id`. Celery prerun leaves `app.company_id` empty. Under `POSTGRES_RLS_ENABLED`, parked captures never auto-post or auto-refund. |
| N-012 | P0 | Payments | `payments/tasks.py:93-102` | After `attempts >= 8` the beat scanner **resets attempts to 0** and re-queues. Combined with N-009, a permanently failing provider is retried forever. |
| N-013 | P0 | Sales | `sales/notes_services.py:226-248` | `cancel_credit_note` has no `sales_return_id` guard. Return cancel cancels linked CNs, but the reverse is open: stock stays restored, AR relief is reversed. |
| N-014 | P0 | Purchases | `purchases/notes_services.py:249-268` | Same unpaired CN cancel while purchase return can remain COMPLETED. |
| N-015 | P1 | Sales | `sales/services.py:1085-1110` | Invoice cancel restores only `.first()` stock-posted challan. COGS path aggregates **all** such challans. Extra challans unrestored. |
| N-016 | P1 | Sales | `sales/services.py:1081-1120` | After challan restore, challan `stock_posted` stays True / status untouched. Inventory restored; challan still claims stock posted. |
| N-017 | P1 | Purchases | `purchases/services.py:292-403` vs `sales/services.py:515-531` | Purchase H9 qty amend on COMPLETED has no serial/batch refuse. Qty up posts bare `PURCHASE` with no `SerialNumberService.receive`; qty down adjusts stock without serial scrap. Sales blocks this. |
| N-018 | P1 | Inventory | `inventory/views.py:335-381` | Allowed map includes `SOLD → RETURNED` with **no** stock movement. Serial “returned” while on_hand still sold. |
| N-019 | P1 | Inventory | `inventory/views.py:362-376` | Scrap posts `ADJUSTMENT -1` with `skip_negative_check=True`; `BusinessRuleError` swallowed. Can drive on_hand negative or status-only scrap. |
| N-020 | P1 | Inventory | `inventory/services.py:833-844` | Explicit-batch FEFO under WARN: `available < qty` takes min and **returns** — no error. SO can confirm more than reserved. Batched multi-lot path raises. |
| N-021 | P1 | Sales | `sales/services.py:856-873` | Complete stock check aggregates by product with `batch=None`. Product-level available can pass while FEFO later fails or issues wrong lots. |
| N-022 | P1 | Sales | `sales/notes_services.py:759-794` | Challan→invoice copies notes + transport. Drops `payment_terms_days`, charges, discount, round-off, `supply_type`, `price_mode`, `terms_text` that SO→invoice carries. |
| N-023 | P1 | Sales | `sales/notes_services.py:561-575` vs `497-514` | SO→challan omits `cess_amount` / `supply_nature`. Invoice convert copies both. |
| N-024 | P1 | Sales | `sales/services.py:467-479` | FEFO issues many lots; line persists only `allocations[0]`. Returns / PDF / challan identity see one lot. |
| N-025 | P1 | Sales | `sales/return_service.py:31-46` vs `purchases/services.py:855-862` | Sales return `set_items` does not require serials for `track_serial`. Empty serials skip transition; stock still restores → serials stay SOLD. |
| N-026 | P1 | Sales | `sales/cogs_service.py:187-198` | Prior SALES_RETURN qty summed by product+batch, **not warehouse**. Cross-godown returns can refuse or under-allocate. |
| N-027 | P1 | Core | `core/services/h9_amend.py:8-12` + `_update_items_in_place` | Docstring: only price/discount. Allowlist never checks `description`. Description-only edits skip `needs_amend` / Owner `confirm_amend`. |
| N-028 | P1 | Core | `h9_amend.py:59-85` | GST/cess/HSN/serial/batch checks are `if key in line` — omit the key to skip. Relies on serializer always sending fields. |
| N-029 | P1 | Core | `core/services/charges.py:11-15` + `billing.py:576-584` | `additional_charges > 0` with missing HSN or `charges_gst_rate=0` → `charge_line` is None; freight enters `grand_total` **untaxed**. |
| N-030 | P1 | Core | `billing.py:517-587` | BEFORE_TAX invoice discount allocates across line taxables only. Taxable freight is added after at full amount. Discount does not reduce freight GST. |
| N-031 | P1 | Core | `core/celery_utils.py:8-18` | `safe_delay` swallows broker errors. PDF/email/notify can vanish; UI already showed success. |
| N-032 | P1 | Core | `config/celery.py:117-132` | If `company_id` omitted, prerun SELECTs tenant rows **before** `set_rls_company`. FORCE RLS → empty; BYPASSRLS role → cross-tenant. |
| N-033 | P1 | Billing | `billing/models.py:49-55` + `services.py:67-100` | `PENDING` always write-blocks. Stub checkout (no Razorpay) creates PENDING. `company_writes_blocked` always honors `is_write_blocked()` even when `REQUIRE_SUBSCRIPTION` is False. Start-plan without a webhook bricks ERP writes. |
| N-034 | P1 | Flags | `feature_flags.py:110-127` + `billing/services.py:44-64` | `ensure_register_trial` plan `modules: {}`. Empty dict is falsy so the “omit dark module = non-grant” branch does not run. Trial / no-sub (`REQUIRE_SUBSCRIPTION` False) fail-open to env `ENABLE_MANUFACTURING` etc. |
| N-035 | P1 | Auth | `tenant_backup.py:145-276` vs wipe | Export still omits CRM, payroll, manufacturing WOs, banking statements, payment links, gateway payments, idempotency, notifications. Wipe/leftover rows diverge even when PROTECT does not fire. |
| N-036 | P1 | Auth | `accounts/views.py:526-527` | OTP verify maps `not user.has_usable_password()` to `OtpExpiredError`. Invitees with unusable password cannot OTP-login (wrong message). |
| N-037 | P1 | Core | `whatsapp.py:80-82,143-148` | Decrypt / Graph HTTP ≥400 fall back to `mode="link"` without raising. Callers that ignore `delivery_mode` treat Cloud failure as success. |
| N-038 | P1 | Search | `search/views.py:69-75,103-118` | Products searchable with sales **or** purchase capability; `selling_price` shown whenever either is true. Purchase-only staff see selling prices. |
| N-039 | P1 | Core | `idempotency.py:199-208,278-283` | HTTP 401/403/404/429 release the key. A deterministic 403/404 from `build()` is not stored; retry can re-execute side effects after a permission blip. |
| N-040 | P1 | Billing | `billing/middleware.py:28-39` vs `core/authentication.py` | Write-gate middleware only Cookie-JWT-authenticates. Bearer-only requests in non-prod skip the middleware gate; many APIViews lack `SubscriptionWritesAllowed`. |
| N-041 | P1 | Mfg | `manufacturing/services.py:27-40,124-139` | `_snapshot_bom()` deletes/recreates lines (wiping `batch` / `lot_allocations`) then `_issue_batches` runs. API lot control is dead; always FEFO. |
| N-042 | P1 | Mfg | `manufacturing/services.py:59-61` | If `line.batch` is set, returns full qty with **no** `available_quantity` check. Path is currently rare because of N-041. |
| N-043 | P1 | Mfg | `manufacturing/services.py:165-173` | Component issue marks serials `SCRAPPED` (terminal). Scrap reports include consumed manufacturing serials. Cancel restores SCRAPPED→AVAILABLE. |
| N-044 | P1 | Payroll | `payroll/views.py:101-106` + `services.py:218-219` | LOP placeholder sets `gross=net=emp.salary`. Complete only deletes inactive slips with `net=0`. Inactive employee keeps full-salary slip in GL totals. |
| N-045 | P1 | Accounting | `accounting/services.py:248-278` | ITC reclass moves **full** invoice tax even when `parked != tax`. 1390 can go negative / overstate claimable. |
| N-046 | P1 | Accounting | `accounting/services.py:784` | `post_receipt_refund` uses `timezone.localdate()`, not receipt date. Cash/GST period mismatch vs original receipt. |
| N-047 | P1 | Payments | `payments/gateway.py:378` | Cashfree `link_amount: float(Decimal)` — paise drift vs books. |
| N-048 | P1 | GST | `reporting/gstr2b.py:110-123` | Date/FY filter runs only `if row.invoice_date`. Null date → amount-only match across years can `MATCHED`. |
| N-049 | P1 | GST | `reporting/ims.py:91-100` | IMS WRONG_GSTIN looks up any PI by number (any year/status). |
| N-050 | P1 | GST | `reporting/ims_offline.py:82-108` | Offline import trusts client `ims_action` / `itc_eligibility` / `match_status`. Tampered JSON can mark ACCEPT/CLAIMABLE without `apply_ims_action`. Always `create()` — re-import without replace → IntegrityError. |
| N-051 | P1 | GST | `reporting/gst_returns.py:251-252` vs purchases `307-317` | Sales GSTR GSTIN stamp **excludes** null `company_gstin`. Purchases coalesce primary+null. Legacy sales invoices drop from GSTR when a primary GSTIN is selected. |
| N-052 | P1 | GST | `gst_returns.py:522-534,846-847` | SUPECOM still counted in B2 / 3.1(a). Easy to double-file if CA files Table 15 and B2. |
| N-053 | P1 | GST | `gst_returns.py:1169-1176,1283-1291` | Inward taxable = all non-RCM; tax heads = CLAIMABLE only. `itc.claimable` true on MATCHED without IMS ACCEPT. UI can show “claimable” while matched ITC is ₹0. |
| N-054 | P1 | Imports | `reporting/chase.py:46-61` | Chase WhatsApp destination = request phone or **user** phone, not supplier. Wrong recipient. Empty phone falls back to `"91"`. |
| N-055 | P1 | Tally | `integrations/tally/adapter.py:411-427,517-530` + `views.py:97-109` | Commit is atomic but no `select_for_update` on the sync run. Concurrent commits both pass. `force=true` commits despite parse errors — those rows never imported. |
| N-056 | P1 | CRM | `crm/services.py:13-60` | Ambiguous phone/email (≥2 matches) creates a new customer. Exact first match attaches with no confirm / no E.164 normalize. Re-convert ignores new `amount`. |
| N-057 | P1 | Insights | `insights/views.py` vs `permissions.ts` | Attention / daily APIs vs FE menu capabilities still diverge (financial-reports vs Owner/AI flags). GET daily summary mutates (upsert). |
| N-058 | P1 | Insights | `insights/alerts.py:90-107,191-193,233-249` | AP_DUE_7D compares supplier bills to CustomerReceipt inflow. Margin uses list `purchase_price` not FIFO COGS. Cash-tight/GST-health `except Exception: pass`. |
| N-059 | P1 | Frontend | `SalesHistoryPage.tsx:391-409` + `PurchaseHistoryPage.tsx:300-314` | Cancel shown for every COMPLETED doc. **No** `canCancelDocuments`. Backend 403s. Purchase Complete likewise not gated by `canCreatePurchases`. |
| N-060 | P1 | Frontend | `App.tsx:368-375` | Note/order/challan **editors** sit on `canViewSalesSurfaces`. List Complete/Cancel on notes is gated; opening `/:id` still lets viewers hit write controls that 403. Same purchase editors pattern. |
| N-061 | P1 | Offline | `NewInvoicePage.tsx` + `NewPurchasePage.tsx` | Offline queue stores create/complete. Amount received / `amountPaid` run only after online COMPLETED. Offline “Complete + payment” syncs an unpaid completed document. POS flush **does** receipt+alloc (`flushPosCheckout.ts:80-97`). Operators assume parity. |
| N-062 | P1 | Frontend | `SupplierPaymentsPage.tsx` + `listPurchasesPage({ pageSize: 50 })` | Outstanding purchases for allocation: first page only. Invoices beyond page 1 invisible. |
| N-063 | P1 | Frontend | `BankingPhasePages.tsx:220-222` | Payment links: `(await listPaymentLinksPage()).results` — no pagination UI. Links after page 1 dropped. |
| N-064 | P1 | Frontend | `InvoicePartyPanel.tsx:81-87` | Quick-create customer on invoice editor; BE Owner-only. Sales staff “new customer while billing” is a dead button. |
| N-065 | P1 | Inventory | `inventory/services.py:1078-1087` | Transfer complete serials: status AVAILABLE→AVAILABLE then bulk warehouse `.update()` without re-check after lock. Race can move serials already sold. |
| N-066 | P1 | Sales | `sales/serializers.py:44-71` + `services.py:60-62` | Line `product` queryset is unscoped `Product.objects.all()`; batch FK not company-checked in `_validate_lines`. Draft can attach a foreign batch until `post_movement`. |
| N-067 | P1 | Purchases | `purchases/serializers.py:26-27` | Same unscoped product queryset / no batch tenant check on lines. |
| N-068 | P1 | Sales | `einvoice_eway_actions.py:252-258` | Async IRN submit: stuck QUEUED never re-enqueued (`allow_queued_retry=False`). Returns 200 success-shaped while first is still queued. |
| N-069 | P1 | Sales | `notes_services.py:480-496` | SO→invoice copies charge **amount** but SO has no `charges_hsn` / `charges_gst_rate`. Invoice charge tax fields stay empty while amount > 0 (N-029). |
| N-070 | P1 | Purchases | `purchases/notes_services.py:423-455` | PO→purchase drops `company_gstin`, warehouse, ITC/TDS, cess/HSN/batch/serial/inclusive. Complete later may fail multi-GSTIN or mis-default ITC. |
| N-071 | P1 | Sales | `sales/services.py:1230-1302` | Quotation→invoice/order drops rate_override / price list / warehouse on order. OWNER override on quote lost; reservations hit default WH. |
| N-072 | P1 | Payments | `payments/holding.py:101-124` | `CAPTURED` + books posted + allocation failed still `PAID_PENDING_BOOKS` / similar. Money in advances; collection state lies. |
| N-073 | P1 | Payments | `payments/services.py:21-23,1058-1074` | Only `INVOICE_CANCELLED` / `LINK_CANCELLED` auto-refund. `AMOUNT_MISMATCH`, `ALREADY_PAID`, `LINK_EXPIRED`, `NO_LINK` retry forever as parked. Customer paid; no books; no refund. |
| N-074 | P1 | Accounting | `accounting/services.py:687-739` | `post_receipt` splits MDR to 5200 and banks `amount−fee`. Refund credits **full** amount to cash; 5200 never reversed. After fee>0 refund, cash high by fee. |
| N-075 | P1 | Payments | `payments/gateway.py:507,630` | Cashfree and PayU webhook parsers hardcode `fee=Decimal("0")`. Capture posts full amount; MDR invisible vs Razorpay path. Refund GL (N-074) then over-credits cash by a fee that was never booked. |
| N-076 | P1 | Accounting | `accounting/services.py:282-311` + `ims.py` | IMS REJECT after ACCEPT: `reclass_rejected_itc` historically only cleared 1390 while tax sits on 1310/1320/1330. 3B vs books diverge. |
| N-077 | P1 | Ledgers | `ledgers/services.py:127-148` vs `253-268` | Per-invoice outstanding is document-based even in GL mode. Party AR uses 1200/2300. Invoice PDF/API vs party ledger diverge. |
| N-078 | P1 | Ledgers | `ledgers/services.py:268,379-384` | Party outstanding floored at 0; `company_receivables` sums floored nets. Advances vanish; dashboard ≠ GL. |
| N-079 | P1 | Core | `core/views.py` FeatureFlags | `get_company_user` with no catch: multi-membership + empty `active_company` → 409 on FE boot flags. `MeView.patch` already catches this. |
| N-080 | P1 | Auth | `accounts/views.py` invite accept | Seat check is count-then-activate; `seat_limit <= 0` means unlimited. Concurrent accepts race. No-plan companies skip seats. |
| N-081 | P1 | Frontend | `usePreviewTotals` + `NewInvoicePage` | Preview error can zero/mismatch vs client totals. Complete blocked when online; offline complete without server preview can diverge tax/TCS/round-off. |
| N-082 | P1 | Offline | `invoiceDraftCache.ts:354-377` | `flushOutbox` has no cross-tab lock. POS + Outbox Sync Now can flush the same draft concurrently. |
| N-083 | P1 | CRM | `navigation/menu.ts` vs `App.tsx` + `crm/views.py` | Nav CRM = Owner-only; API convert uses `CanCreateSales`. Sales staff: deep-link works, nav hides CRM. |
| N-084 | P1 | GST | `reporting/models.py:163-172` | 2B unique skips blank `invoice_number` unless `invoice_date` is non-null. Duplicate blank+null-date ingest unconstrained. |
| N-085 | P1 | Core | `core/migrations/0008_wave19_rls_all_tenant_tables.py` | `GatewayRefundOutbox` / `DunningReminder` not in FORCE RLS table list while peers are. Cross-tenant if GUC empty. |
| N-086 | P1 | Sales | `sales/pdf/note_documents.py:239-260` | Challan PDF forces `tax_enabled=False` while model stores CGST/SGST/IGST. Statutory tax block omitted. |
| N-087 | P1 | Purchases | `purchases/pdf.py:88-91,178-179` | HSN summary uses `taxable_amount or line_total` (inclusive fallthrough inflates). Intra-state uses supplier vs company, not stamped `company_gstin`. |
| N-088 | P1 | Sales | `sales/pdf/thermal_receipt.py:158-159` | Line tax = CGST+SGST+IGST only; A4 includes cess. TCS historically omitted on thermal. |
| N-089 | P1 | Sales | `sales/services.py:808-848` | Missing HSN is warning unless e-invoice+B2B. B2B charges without HSN: warning only. Purchases with company GSTIN hard-block. GSTR Table 12 / e-invoice charge identity fragile. |
| N-090 | P1 | Inventory | `inventory/services.py:908-943` | Rebuild reserved uses SO line `quantity` not `base_quantity`. `batch=None` rebuild zeros unbatched reserved only — FEFO lot reserved stale. |
| N-091 | P1 | Inventory | `purchases/services.py:1040-1051` | Unbatched purchase return peels `order_by("-id")` (LIFO), opposite of sales FEFO. |
| N-092 | P1 | Sales | `sales/services.py:594-609` | H9 qty-down (if allowlist bypassed) posts ADJUSTMENT restore, inventing a new FIFO layer instead of `restore_fifo_peels`. |
| N-093 | P1 | Tally | `integrations/tally/adapter.py:452-467` | Customers `get_or_create(name=...)` only. Distinct parties merge; GSTIN/phone not refreshed. |
| N-094 | P1 | Payments | `payments/views.py` recon | Recon list requires `CanCreatePayments`. Viewers with `CanViewPaymentSurfaces` cannot see suggestion queue. |
| N-095 | P1 | CRM | `crm/views.py:26` | Convert gated `CanCreateSales` — no CRM-specific capability. |
| N-096 | P1 | Frontend | `CreditNotesPage` cancel CN | UI can cancel a completed auto-return CN (N-013) with no warning that the sales return stays COMPLETED. |
| N-097 | P1 | Mfg | `manufacturing/services.py:340-374` | Cancel of completed WO: multiple ISSUE moves re-transition **all** line serials each time. Second transition fails / partial cancel. |
| N-098 | P1 | Mfg | `manufacturing/services.py:234-240` | Existing FG batch: mismatched expiry only logs; stock mixes into old lot. |
| N-099 | P1 | Payroll | `payroll/services.py:161-177,223-227` | PF ceiling stays full-month ₹15k while Basic+DA prorated. PT slabs on prorated gross. ESI eligibility vs contribution basis disagree on LOP. |
| N-100 | P1 | Banking | `banking/services.py:42-55` | AA match: first UTR `icontains` ≥6–8 chars + amount±tol + ±7 days; first `select_for_update` wins. Short txn ids never match. |
| N-101 | P2 | Core | `core/csv_utils.py:21-28` | Neutralizes `=+-@`/tab/CR after lstrip space/NBSP. Unicode fullwidth `＝` and `;`/`|` DDE prefixes remain. |
| N-102 | P2 | Core | `core/throttles.py:23-34` | Missing `throttle_scope` → allow (fail-open). No company on `CompanyRateThrottle` → DRF skips. |
| N-103 | P2 | Core | `core/middleware.py:101-109` | RLS Cookie-JWT exceptions swallowed. Unauthenticated path may run with empty `app.company_id`. Clear-on-exit exceptions can leave pooled GUC. |
| N-104 | P2 | Core | `core/permissions.py:47-66` | Auto-set `active_company` `except Exception: pass`. |
| N-105 | P2 | Core | `core/events.py:25-35` | Handlers catch all; PDF/notify fail while Complete commits. |
| N-106 | P2 | Core | `sms.py:82-88,160-165` | MSG91 non-JSON HTTP 200 treated as sent. Stub SMS allowed when `DJANGO_ENV` in `("", "development", "test")`. |
| N-107 | P2 | Core | `document_numbers.py:68-80` | Any company GSTIN forces GSTIN+FY series even when `doc_number_scope=COMPANY`. |
| N-108 | P2 | Core | `place_of_supply.py:82-83` | Unknown free-text state + `assume_local_state_for_blank_party=True` forces intra-state. |
| N-109 | P2 | Core | `billing.py:667-691` | `recompute_tax_on_complete=False`: W0-02 only flips when CGST vs IGST sums mismatch. Other stamp/state mismatches leave wrong split. |
| N-110 | P2 | Core | `billing.py:800-811` vs complete | Preview TCS from rate; Complete honors `tcs_amount_manual`. Preview ≠ books. |
| N-111 | P2 | Core | `billing.py:363-414,749-760` | Draft Complete overwrites line `gst_rate` from HSN catalog unless `rate_override`. Preview `_Doc` is not rateable → preview 18%, books 5%. |
| N-112 | P2 | Core | `idempotency.py:120-133` | Stale in-flight takeover: delete then create without holding the lock across both. |
| N-113 | P2 | Core | `files.py` CREDIT_NOTE_PDF kinds | Note/challan PDF kinds fall through to ATTACHMENT size/MIME rules. |
| N-114 | P2 | Auth | `accounts/views.py:457-460,84-111,1147` | OTP rate-limit recorded before send; SMS fail still burns budget. Password-reset 200 with no mail if `FRONTEND_URL` missing. Access cookie `path=/`. |
| N-115 | P2 | Auth | `otp_utils.py:11-13,28-41` | `OTP_PEPPER` falls back to `SECRET_KEY`. `phone_lookup_values` misses leading-`0` national forms. |
| N-116 | P2 | Auth | `tenant_backup.py:333-348` | Decrypt tries company HKDF then instance Fernet — legacy blobs decrypt under another `company_id` argument before source check. |
| N-117 | P2 | Auth | `accounts/views.py` invite create | Seats vs **active** count; unlimited pending invites. Accept under `/auth/` bypasses subscription write gate. |
| N-118 | P2 | Billing | `billing/models.py:56-68` | ACTIVE + `current_period_end=None` never blocks. PAST_DUE grace anchors `updated_at` when period end missing — status webhooks reset grace. |
| N-119 | P2 | Billing | `billing/views.py:124-136` | Comment says unsigned webhooks when DEBUG; code allows `DJANGO_ENV=test`. |
| N-120 | P2 | Sales | `sales/serializers.py` tcs_amount | `tcs_amount_manual = bool(tcs_amount)` treats `0` as non-manual. Cannot force TCS=0 against a positive rate. |
| N-121 | P2 | Sales | `sales/services.py:845-857` vs TCS fold | e-Way threshold warning before `apply_tcs_fold`. Near-₹50k TCS-inclusive can miss the warning. |
| N-122 | P2 | Sales | `einvoice_eway_actions.py:69-86,191-210` | Claim lock window vs payload build; MANUAL_EWB can look in-flight. |
| N-123 | P2 | Purchases | `purchases/services.py:692-702,914-915` | Batch `get_or_create` keeps existing expiry on clash. PR Complete requires invoice COMPLETED only — blocked after another return marks RETURNED. |
| N-124 | P2 | Purchases | `purchases/services.py:347-403` | Purchase H9 qty stock path has no batch/serial guard (pairs with N-017). |
| N-125 | P2 | Inventory | `inventory/services.py:23-36,579-598,807-817` | `default_warehouse` can set a second default. WARN invents `layer_id:None` peels. FEFO recursive reserve: unlocked available then lock. |
| N-126 | P2 | Inventory | `inventory/services.py:436-440` | Running cost uses stamped `unit_cost` over layer avg when both set. |
| N-127 | P2 | Masters | `masters/pricing.py:9-73` + `serializers.py:235-245` | Overlap checked on nested replace payload only, not item-level API / DB exclusion. Matcher `order_by("-min_qty")`. Qty≤0 coerced to 1. |
| N-128 | P2 | Masters | `masters/views.py:27-52` | 60s list cache; mutations do not always bust. Stale tax/unit pickers. |
| N-129 | P2 | Payments | `payments/tasks.py:28-39` | Fresh `IN_PROGRESS` early-return looks like Celery success. Recovery depends on beat + 10 min reclaim. |
| N-130 | P2 | Payments | `webhook_views.py` | Catch-all parks `BusinessRuleError` as `BOOKS_ERROR` (incl. UTR clash). Ambiguous `provider_link_id` → 409 forever. |
| N-131 | P2 | Payments | `payments/dunning.py:216-263` | Exact overdue-day buckets; quiet hours skip the whole run (day-7 never retried). Can dunn after capture with failed allocation. IntegrityError on reminder create swallowed. |
| N-132 | P2 | Payments | `payments/recon.py:175-215` | Score can hit ≥40 from UTR/name/date without amount match. TDS payments score 0 amount points vs GL net cash. |
| N-133 | P2 | Payments | `payments/services.py:220-223` | `warn_utr_duplicate=True` never raises; suffix retry can insert duplicate UTR. Flag unused from receipt create view. |
| N-134 | P2 | GST | `gstr2b.py:26-28,91-96` | Sticky MATCHED skips rematch. `claimable_itc_from_2b` does not require `ims_action=ACCEPT`. |
| N-135 | P2 | GST | `ims.py:139-210` | `bulk_accept_exact` chunks separate atomics; invents remark; mass-ACCEPT + GL. Period-lock deemed-accept is now a no-op (good). |
| N-136 | P2 | GST | `gst_returns.py:1024-1037,996-1001` | AT table hardcodes rate/tax 0 with honesty flag. AT empty for non-primary GSTIN stamp. |
| N-137 | P2 | GST | `gst_returns.py:1309-1324` | Without 2B, `recommended_claimable` still shows `books_provisional`. Easy to over-claim. |
| N-138 | P2 | Accounting | `accounting/services.py:1356-1361` + reports FY close | Period-close WIP checks all RELEASED WOs with no period filter. FY close WIP is net 1450 as-of fy_end all history. |
| N-139 | P2 | Accounting | `accounting/services.py:693-694` | Gateway receipts post to Cash 1100 when finalize never sets `bank_account`. Bank recon vs GL bank diverge. |
| N-140 | P2 | Mfg | `manufacturing/serializers.py:61-91` | `component_lines` read_only; FG serials optional until complete. Lot/serial late errors after components issued. |
| N-141 | P2 | CRM | `crm/models.py:51-61` | No unique(lead). CRUD can create multiple opportunities per lead. |
| N-142 | P2 | Insights | `insights/alerts.py:278-292,460-466` | SALE_BELOW_COST capped 500 / one per SKU. Dead-stock sample 40 SKUs. |
| N-143 | P2 | Insights | `insights/views.py:81-88` | Every GET regenerates daily summary. Dashboard polling writes. |
| N-144 | P2 | Tally | `integrations/views.py:76-81` | Preview POST marks PREVIEWED even with errors. |
| N-145 | P2 | Tally | `adapter.py:186-207` | Post-commit recon uses whole-company AR/AP vs this import’s openings. |
| N-146 | P2 | Search | `search/views.py:32-34,36-71` | Throttle scope `search` without `CompanyRateThrottle`. No min query length. |
| N-147 | P2 | Frontend | `pwa.ts:16` | Update confirm is hardcoded English. |
| N-148 | P2 | Frontend | `api/client.ts` refresh | Any refresh failure (incl. transient network) can clear session + drafts. |
| N-149 | P2 | Frontend | `common.ts:146-161` | `fetchAllPagesMasters` silent stop at 500 pages. Journals/`listJournals` still full-crawl. Note editors load all completed invoices into Autocomplete. |
| N-150 | P2 | Frontend | `lib/native.ts:132-135` | `registerPushToken` never called. Capacitor Push + Android permission unused. |
| N-151 | P2 | Frontend | `StockCountPage` + `InventoryPhasePages` | Stock count/transfer enqueue IndexedDB; **no** auto-flush hook. Only Outbox Sync Now. Transfer list still shows DRAFT. |
| N-152 | P2 | Frontend | `InvoiceDetailPage.tsx` | `canAct` is status-only; UPI collect / payment link not gated by `canCreatePayments`. |
| N-153 | P2 | Frontend | `ConfirmDialog.tsx:29-32` | No `aria-describedby` for body. |
| N-154 | P2 | CI | `.github/workflows/ci.yml:93-126` | Mobile job: `npm ci` + tsc/grep `allowBackup`. No `cap sync`, no Android assemble. |
| N-155 | P2 | Config | `settings.py:686-687` | `POSTGRES_RLS_ENABLED` defaults off. Tenancy is app-layer until ops opts in. |
| N-156 | P2 | Config | `settings_test.py:65-66` | `UNSUBSCRIBED_SEAT_LIMIT=0` (unlimited) hides production default of 1. SQLite does not honor `SELECT FOR UPDATE`. |
| N-157 | P2 | Core | `core/models.py:164` | `AuditEvent.action` choices CREATE/UPDATE/DELETE/LOGIN; callers log `tenant.export`, `billing.checkout`. |
| N-158 | P2 | Core | `gsp_secrets` decrypt | Decrypt failure returns `{}` — indistinguishable from no credentials. |
| N-159 | P2 | Sales | `sales/services.py:307-321` | Converted-challan lot identity includes cancelled linked challans. |
| N-160 | P2 | Payments | `payments/services.py:1413` | Open-invoice health scans only 50 invoices. |
| N-161 | P3 | Core | `idempotency.py` docstring | Still talks about storing 5xx / unused `DEFAULT_TTL` in places. |
| N-162 | P3 | Core | `config/celery.py:61-91` | Dead `_company_id_from_document_disabled` duplicate. |
| N-163 | P3 | Core | `feature_flags.py:132-134` | `item_custom_fields_v2` defaults ON. |
| N-164 | P3 | Core | `core/viewsets.py:16-49` | `SubscriptionWritesAllowed` appended to list/retrieve; `perform_destroy` audits pk only. |
| N-165 | P3 | Auth | `accounts/views.py` cookie Secure | Access Secure tied to CSRF flag, not a dedicated JWT flag. |
| N-166 | P3 | Search | `search/views.py:83-101,111-116` | Invoice search includes cancelled/draft. `gst_rate` always returned for visible products. |
| N-167 | P3 | GST | `gstr2b.py:272-336` | GSTR-4/6/7/8 honesty stubs `supported: false`. Risk if UI treats as filing-ready. |
| N-168 | P3 | Frontend | `api/typedClient.ts` | Types-only; runtime still `legacy/*`. |
| N-169 | P3 | Frontend | `en.ts` switchToTamil/Gujarati | Keys still shipped; switcher no longer offers ta/gu. |
| N-170 | P3 | CD | `cd.yml` | Image bake sets manufacturing/payroll/CRM Vite flags false. |
| N-171 | P3 | Sales | `irn_guard.py` | `LIVE_IRN` unused vs broader denylist. |
| N-172 | P3 | Core | `middleware` access-log IDs | Unsalted `sha256(pk)[:12]`. |
| N-173 | UX | Frontend | History cancel uses `window.confirm`; notes use `ConfirmDialog`. Inconsistent a11y. |
| N-174 | UX | Frontend | `AppShell` nav `selected` is exact pathname — `/sales/history/123` does not highlight Sales History. |
| N-175 | UX | Frontend | Hardcoded English cluster: NewInvoice/NewPurchase supply type, price mode, TCS; Receipts UTR headers; InvoiceDetail UPI/e-way; Journals/FixedAssets/InventoryPhase; Users/Gst/Company settings helpers; `pwa.ts` reload copy; POS walk-in 403 surfaces as `pos.selectCustomer`. |
| N-176 | UX | Frontend | Hindi is money-complete; phase/settings/auth forms still English. LocaleSwitcher silently maps stored ta/gu → en with no toast. |
| N-177 | UX | Frontend | `navigation/menu.ts` has no Offline Outbox item. Chip-only. Stock/POS drafts sit until `/offline`. |
| N-178 | UX | Frontend | `DocumentEditorShell` Save & New always disabled when `isEdit` with no tooltip. Invoice unsaved-guard is lines-only. No aria-live on preview pending. DraftLineTable hides HSN on xs. |
| N-179 | UX | Frontend | GSTR-6/7/8 routed (`App.tsx`) not in `menu.ts` — URL-reachable JSON stubs look like broken reports. |
| N-180 | UX | Frontend | `OfflineOutboxPage` delete draft has no confirm. Outbox route has no role gate (queued PII on shared POS). |
| N-181 | UX | Frontend | POS: no cash-drawer ESC/POS pulse; cash allocates full grandTotal; status chip not aria-live. |
| N-182 | UX | Frontend | PartySelectPanel: invalid GSTIN checksum looks fine; warns only if both state and GSTIN missing. |
| N-183 | UX | GST | Honesty flags / SUPECOM double-count / `books_provisional` easy to miss. CA can double-file. |
| N-184 | UX | Mfg | Work Orders now collect serials as JSON/CSV textarea — easy to fail release; no per-component picker. |
| N-185 | UX | Payroll | LOP dialog exists; PF/ESI/PT numbers can still be silently wrong after LOP+inactive (N-044) with no warning chip. |
| N-186 | UX | Tally | Commit success can look like full parity. `force=` and recon warnings easy to skip. |
| N-187 | UX | Insights | Daily narrative presents AR/AP as facts; margin/alerts use list price or receipts mix. |
| N-188 | UX | Frontend | Keyboard Ctrl+S / Ctrl+Enter exist; no cheat-sheet. Complete buttons historically double-submit on some lists (CN list now disables pending). |
| N-189 | UX | Mobile | Capacitor WebView over `web/dist`. README 8h-offline / 50 drafts is web IDB. No iOS ship. No Bluetooth print plugin. |
| N-190 | UX | Onboarding | Blocking step can be catalog while `ui_step` shows payments. Progress bar can lie. |
| N-191 | GAP | GST | GSTR-4/6/7/8 / GSTR-9 worksheet aids — not portal engines. Composition / ISD / TCS collector / TDS dealers have no filing product. |
| N-192 | GAP | Auth | Tenant backup is a partial books dump, not a company clone. Sold as restore. |
| N-193 | GAP | Billing | No hosted Razorpay customer portal; no self-serve cancel/pause/change-plan. |
| N-194 | GAP | Core | Push channel: create then fail not-implemented. POS cash drawer not implemented. |
| N-195 | GAP | Sales | Invoice templates page is terms textarea + legend — no ORIGINAL/DUPLICATE, per-GSTIN header, preview. |
| N-196 | GAP | Mfg | BOM+WO only. No routing, by-products, shop-floor execution (telemetry POST only). |
| N-197 | GAP | Payroll | No Form 24Q/16, attendance import, complete state PT. |
| N-198 | GAP | CRM | No pipeline stages, activities, quote linkage, duplicate-party confirm. |
| N-199 | GAP | Masters | HSN catalog is a tiny starter list, not GSTN. Almost all HSN → None. |
| N-200 | GAP | CI | Light e2e is login/templates smoke. Golden is one invoice path. No returns, GST file, POS offline, payroll, Tally e2e. RLS job is a thin smoke. |
| N-201 | GAP | Auth | Invite URL returned to owner only — no email/SMS send of invite in that view. |
| N-202 | GAP | Frontend | `books_start_date` / `doc_number_scope` exist on company; UI does not expose them. |
| N-203 | SUGG | Inventory | Restore FIFO peels **proportional to `take`**; add `sales_return_cancel` to peel unwind (mirror purchase). |
| N-204 | SUGG | Auth | Wipe PaymentLink/ReconMatch/Bom/WO/FixedAsset first (or CASCADE). Count them in `unbacked_live_counts`. Normalize phones to E.164 at save + unique on canonical. Catch IntegrityError outside atomic / use savepoint. |
| N-205 | SUGG | Payments | Do not mark books REFUNDED until outbox SUCCEEDED. Fan-out beat tasks per `company_id`. Dead-letter after N attempts. Add RLS policies for outbox/dunning. |
| N-206 | SUGG | Masters | Allow `CanCreateSales`/`CanCreatePurchases` to create parties/products, **or** gate FE with `isOwner`. Hide history Cancel unless `canCancelDocuments`. |
| N-207 | SUGG | GST | Fail closed on 2B rows with null `invoice_date`. Owner-gate IMS mutate. Never amount-only MATCH across FY. |
| N-208 | SUGG | Offline | Queue receipt+allocation in invoice/purchase outbox (POS already does). Global flush mutex. |
| N-209 | SUGG | i18n | Hide leftover Tamil/Gujarati keys; CI: no hardcoded billing/journal strings; finish Hindi non-money namespaces. |
| N-210 | SUGG | Mfg | Apply lot/serial **after** snapshot from request payload; availability check on explicit batch; consumed serial status ≠ SCRAPPED. |

---

## Fixed since the morning 2 Sep review (do not re-open)

Verified **fixed** in current source — listed so the quality picture is not stale:

| Morning claim | Evidence now |
|---|---|
| Refund `.delay(outbox.id)` without `company_id` | `execute_gateway_refund.delay(row.id, company_id=row.company_id)`; task signature has `company_id=None` |
| Closing sales-return auto-CN `ratio=1` for remainder | `return_service.py:186-196` remainder when `fully_returned` |
| H9-A missed supply_nature / cess / HSN / serial / batch | `h9_amend.py:63-96` |
| DocumentSeries not exported/wiped; warehouses not wiped | export `document_series` + wipe deletes both |
| BatchLot/SerialNumber unscoped PK (IDOR) | `CompanyPrimaryKeyRelatedField` |
| GSTR 3.1(a) dropped RCM taxable | `_all_sum` taxable + `_non_rcm_sum` tax |
| `post_purchase_invoice` missing | alias `post_purchase_invoice = post_purchase` |
| ACTIVE never checked `current_period_end` | `billing/models.py:56-59` |
| CSV no tab/CR / leading space | `csv_safe` lstrip + tab/CR |
| LocaleSwitcher offered ta/gu English stubs | Switcher is en/hi only; stored ta/gu forced to en |
| CreditNotes list Complete/Cancel on view ACL | `canWrite` / `canCancel` |
| ConfirmDialog no busy state | `confirming` disables buttons |
| ErrorBoundary hardcoded English | uses `t()` |
| WO UI never collected serials / batch fields | `WorkOrdersPage` serial textarea + `batch_no`/`exp_date` on serializer |
| Payroll LOP / Basic+DA / cancel missing in UI | `EmployeesPage` + `PayRunsPage` LOP + `cancelPayRun` |
| CRM convert always OPEN | convert dialog has won checkbox |
| Journals ignore subscription gate | `useSubscriptionGate` |
| PWA auto-reload no confirm | `window.confirm` then `updateSW(true)` |
| POS flush allocation no idempotency | `${draft.idempotencyKey}-receipt` / `-alloc` |
| `fetchMoneyListFirstPage` 50-cap | now walks all pages (silent 500-page cap remains) |
| IMS period-lock deemed-ACCEPT | `deemed_accept_on_period_lock` is a no-op |
