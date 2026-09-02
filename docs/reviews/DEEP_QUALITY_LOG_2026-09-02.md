# Bizboard quality log — 2 Sep 2026

Full searchable list of the 2 Sep 2026 deep review. Use this file if the canvas preview fails.

**Count:** 206 findings · 12 P0 · 60 P1 · 63 P2 · 9 P3 · 30 UX · 19 GAP · 13 SUGG

| ID | Sev | Module | Location | Finding |
|---|---|---|---|---|
| Q-001 | P0 | Accounting | `accounting/services.py:576` | adjust_purchase_invoice_postings calls post_purchase_invoice, which does not exist (only post_purchase). Completed purchase H9 amend with accounting on AttributeErrors after reversing journals. |
| Q-002 | P0 | Payments | `payments/gateway.py:305-306` | Razorpay refund header is X-Razorpay-Idempotency. Razorpay expects X-Razorpay-Idempotency-Key. Reclaim/retry can double-refund. |
| Q-003 | P0 | Payments | `payments/services.py:1198-1211 + tasks.py` | Staff refund unwinds allocations/GL and marks receipts REFUNDED before the gateway call. Failed/stuck outbox = books refunded, customer still charged. |
| Q-004 | P0 | Payments | `payments/tasks.py:93-97` | After attempts>=8 the beat sweep never retries. created=False on get_or_create does not re-queue. Gateway refund can be stuck forever. |
| Q-005 | P0 | GST | `reporting/gst_returns.py:1402-1418` | Comment says 3.1(a) keeps RCM taxable and drops only tax. _non_rcm_sum skips every rchrg=Y key including taxable_value. Understates outward turnover. |
| Q-006 | P0 | Auth | `accounts/views.py:1060-1072` | CompanyUser PATCH can set is_active=True with no seat-limit check. Invite/accept enforce seats; reactivation bypasses the plan. |
| Q-007 | P0 | Billing | `billing/models.py:49-65` | is_write_blocked() never inspects current_period_end for ACTIVE. Expired paid periods keep writing until a webhook flips status. |
| Q-008 | P0 | Core | `feature_flags.py:104-118 + billing/services.py:36-41` | No subscription/plan returns None. Dark-module fail-closed only runs when plan_modules is a dict. Env ENABLE_MANUFACTURING etc. leak open. |
| Q-009 | P0 | Inventory | `inventory/serializers.py:137-142,230-242` | BatchLotSerializer and SerialNumberSerializer use unscoped PrimaryKeyRelatedField for product/warehouse. Cross-tenant FK create (IDOR). |
| Q-010 | P0 | Purchases | `purchases/services.py:810-820` | Purchase-invoice cancel transitions serials AVAILABLE→SCRAPPED. SCRAPPED is terminal in inventory rules. Cancel permanently scraps receivable serials. |
| Q-011 | P0 | Sales | `sales/return_service.py:114-133` | Auto-CN source_item keeps only the first matching invoice line id while qty may consume several same-SKU lines. complete_credit_note qty guard can abort the whole return. |
| Q-012 | P0 | Payroll | `payroll/services.py:221-233` | Cancel keeps prorated slip.gross + paid_days. Re-complete feeds that gross into compute_statutory which prorates again. Double-prorated PF/ESI/net. |
| Q-013 | P1 | Auth | `accounts/views.py:974-976` | Seat check runs inside atomic then the with-block ends before membership create. Concurrent invites race the limit. |
| Q-014 | P1 | Auth | `accounts/views.py:637-644` | SwitchCompanyView mints new cookies and never blacklists the previous refresh JWT. Old refresh stays valid until expiry. |
| Q-015 | P1 | Auth | `accounts/tenant_backup.py export vs wipe` | Export omits quotations/orders/challans/notes/returns/transfers. Wipe deletes them. Destroy-in-place with confirm_destroy_unbacked drops unreexported docs. |
| Q-016 | P1 | Auth | `accounts/tenant_backup.py:231-237` | Files >256KB export checksum only. Restore skips rows without bytes_b64. Large logos/PDFs never restore. |
| Q-017 | P1 | Auth | `accounts/views.py:820-835` | Outside production/staging, invite accept without password still issues JWTs for an existing user. Invite token = account takeover if env is mislabeled. |
| Q-018 | P1 | Billing | `billing/services.py:56-85` | Checkout can leave tenant PENDING (write-blocked) if Razorpay create fails after the local row, or on stub order with no webhook. |
| Q-019 | P1 | Billing | `billing/services.py:152-162` | Unknown Razorpay statuses map to None → no update. Subscription can sit non-ACTIVE after payment auth. |
| Q-020 | P1 | Billing | `accounts/views.py:256-280` | Register creates a company with no Subscription. REQUIRE_SUBSCRIPTION in production write-blocks new tenants with no trial path. |
| Q-021 | P1 | Core | `core/idempotency.py:250-263` | Transient 4xx releases the record then re-raises, discarding the built envelope. Client error shape is inconsistent. |
| Q-022 | P1 | Core | `h9_amend.py:8-81` | Allowlist now blocks qty/gst/cess/nature, but hsn_code, description, serial_numbers, batch_no, dates can still change on a price-only amend. |
| Q-023 | P1 | Core | `billing/permissions.py:37-38` | cu is None returns True on SubscriptionWritesAllowed. Authenticated users without company context skip the DRF write gate. |
| Q-024 | P1 | Sales | `sales/services.py:620-622 + serializers.py:362-405` | set_items adjust_sales_invoice_postings reverses all incl. COGS then serializer reverses COMPLETE again. Dual GL path, not one outer atomic. Mid-failure can leave COGS missing. |
| Q-025 | P1 | Sales | `sales/cogs_service.py:187-198` | already_lot sums all prior returns for product+batch (often batch=None) and subtracts that total from every sale move. Later unbatched returns can be refused. |
| Q-026 | P1 | Sales | `sales/return_service.py:174-195` | Auto-CN ratio stays 1 when invoice taxable_total is 0. Partial returns copy full discount/charges/TCS until the remainder path. |
| Q-027 | P1 | Sales | `sales/return_service.py:228-231` | Fixed cess_amount copied full onto partial CN lines via source_item. Partial returns credit full specific cess. |
| Q-028 | P1 | Sales | `sales/return_service.py:370-381` | Return cancel reverses only purpose=COGS_REVERSE. Damaged-return scrap JE (DAMAGED_SCRAP) stays posted. |
| Q-029 | P1 | Sales | `sales/serializers.py:267-290` | COMPLETED money_fields omit warehouse, invoice_date, due_date, cost_center, ecommerce_operator_gstin, invoice_type. Those mutate without confirm_amend. |
| Q-030 | P1 | Sales | `sales/pdf/thermal_receipt.py:122-230` | Thermal receipt uses company.gstin, never prints TCS. Multi-GSTIN POS shows HO GSTIN; TOTAL can hide folded TCS. |
| Q-031 | P1 | Sales | `sales/pdf/note_documents.py:118-180` | CN/DN PDF totals skip TCS, cess, additional charges. Auto-return notes print a tax narrative that disagrees with books. |
| Q-032 | P1 | Sales | `sales/notes_services.py:549-806` | SO→challan leaves reservations. cancel_sales_order does not check live challans; draft cancel_challan does not touch SO. Orphan reservations. |
| Q-033 | P1 | Sales | `sales/notes_services.py:768-781` | Challan→invoice copies qty/price/gst/batch/serial only. Drops cess, supply_nature, HSN, inclusive price. |
| Q-034 | P1 | Sales | `sales/services.py:1216-1241` | Quotation→invoice/order drops header discount/charges/terms/payment/supply. QuotationItemSerializer has no cess/HSN/inclusive. |
| Q-035 | P1 | Sales | `einvoice_eway_actions.py:67-84,392-396` | Concurrent e-Way: in_flight returns 200 success-shaped while first is still QUEUED. mark_eway_generated has no claim lock. |
| Q-036 | P1 | Sales | `einvoice_payload.py:438-444` | Note e-invoice builds from full invoice payload first. Valid CNs blocked by unrelated invoice readiness; SellerDtls tied to invoice stamp. |
| Q-037 | P1 | Purchases | `purchases/services.py:1114-1148` | Purchase auto-CN ignores additional_charges and maps first invoice line only per product. Freight/AP residue; wrong HSN on duplicate SKUs. |
| Q-038 | P1 | Purchases | `purchases/serializers.py:194-214` | COMPLETED money_fields omit company_gstin, invoice_date, warehouse, supplier_bill_number, purchase_type. Filing stamp/warehouse/bill identity drift without amend. |
| Q-039 | P1 | Purchases | `purchases/pdf.py:235-274` | PDF reads supplier_invoice_number / place_of_supply (not on model). Buyer GSTIN uses company.gstin not company_gstin stamp. |
| Q-040 | P1 | Purchases | `purchases/services.py:619-624` | Missing HSN is a warning on purchase Complete. Sales e-invoice hard-fails. GST purchases complete without HSN → GSTR/ITC breakage. |
| Q-041 | P1 | Purchases | `purchases/notes_services.py:423-436` | PO→purchase drops company_gstin, warehouse, price_mode, cess, HSN, batch, serials, inclusive price. |
| Q-042 | P1 | Payments | `payments/services.py:1168-1185` | Provider partial refunds recorded in JSON only. Status stays CAPTURED. AR/cash stay posted. |
| Q-043 | P1 | Payments | `accounting/services.py:753-776` | post_receipt_refund credits full MDR fee back to 5200 and banks only amount-fee. Gateway usually keeps MDR → bank GL overstated. |
| Q-044 | P1 | Payments | `payments/gateway.py:507,630,697` | Cashfree/PayU webhooks hardcode fee=0. Capture posts full amount; MDR invisible vs Razorpay path. |
| Q-045 | P1 | Payments | `payments/holding.py:107-121` | CAPTURED + failed allocation reports UNPAID. UI shows unpaid after money is captured. |
| Q-046 | P1 | Payments | `payments/services.py:868-882` | Expired payment-link capture parks rather than auto-refund. Money held until manual reconcile. |
| Q-047 | P1 | Inventory | `inventory/services.py:819-825` | FEFO reserve under non-BLOCK: shortfall returns without reserving remainder. SO can confirm more than reserved. |
| Q-048 | P1 | Inventory | `inventory/views.py:335-357` | Serial transition scrapes/returns without a stock movement. Serial status diverges from on_hand. |
| Q-049 | P1 | Inventory | `inventory/services.py:497-508` | Positive cancel movements with listed reference_type skip FIFO layer create. Callers that forget restore_fifo_peels leave a valuation hole. |
| Q-050 | P1 | Manufacturing | `manufacturing/services.py:64-73` | lot_allocations loads BatchLot by pk+company with no product check. Can issue the wrong SKU’s lot. |
| Q-051 | P1 | Manufacturing | `manufacturing/serializers.py:76 + services.py:27-40` | component_lines is read_only; release snapshots BOM and deletes lines. Pre-set lot/serial on lines is impossible. UI that only PATCHes WO misses component_serials → 400. |
| Q-052 | P1 | Manufacturing | `manufacturing/services.py:154-168` | Component issue marks serials SCRAPPED. Scrap reports include consumed manufacturing serials. |
| Q-053 | P1 | Accounting | `accounting/services.py:1356-1361` | period_close_blockers checks ALL RELEASED work orders with no period/released_at filter. Past WIP blocks unrelated period close. |
| Q-054 | P1 | GST | `reporting/gst_returns.py:1064-1065` | ATADJ skips receipt_date >= invoice_date. Same-day advance→invoice adjustments missing from the aid. |
| Q-055 | P1 | GST | `reporting/gst_returns.py:1024-1037` | AT table hardcodes rate/tax 0.00 with honesty flag. If CA files the aid as portal AT, advance tax is silently wrong. |
| Q-056 | P1 | GST | `reporting/gst_returns.py:702-756` | matched_invoices excludes sales RCM; section_taxable still sums B2B rchrg=Y. Spurious footing_discrepancy. |
| Q-057 | P1 | GST | `reporting/ims.py:217-238` | GST period lock deemed-ACCEPTs NO_ACTION+EXACT rows. Soft-close can auto-claim ITC without an explicit IMS decision. |
| Q-058 | P1 | GST | `reporting/views.py:715,802-892` | IMS accept / bulk-accept / offline replace gated by CanViewFinancialReports only. Accountant can ACCEPT ITC or wipe period 2B with replace=true. |
| Q-059 | P1 | GST | `reporting/models.py:163-166` | 2B unique constraint skips blank invoice_number. Duplicate blank-number ingest is unconstrained. |
| Q-060 | P1 | Tally | `integrations/tally/adapter.py:425-516` | force= can commit with preview errors. Opening-stock BusinessRuleError is a warning; status still COMMITTED. |
| Q-061 | P1 | Tally | `integrations/tally/adapter.py:452-500` | get_or_create by name/SKU only. Re-import does not refresh GSTIN/phone. Openings attach to stale parties. |
| Q-062 | P1 | CRM | `crm/services.py:13-91` | Ambiguous phone/email (≥2 matches) creates a new customer. Shared shop phones duplicate parties on convert. |
| Q-063 | P1 | Insights | `insights/views.py:52-54 vs permissions.ts:57-68` | BE AI insights: Owner or can_view_ai_insights. FE also grants canViewFinancialReports. Accountants see menu, API 403. |
| Q-064 | P1 | Insights | `insights/views.py:274-282` | Attention API is HasCompany only. FE route is financial-reports. VIEWER/sales staff can hit money attention rows via API. |
| Q-065 | P1 | Insights | `insights/alerts.py:90-107` | AP_DUE_7D compares supplier bills due to CustomerReceipt inflow. False alerts when cash is not from sales receipts. |
| Q-066 | P1 | Frontend | `web/src/api/legacy/common.ts:139-145` | fetchMoneyListFirstPage returns only page.results (PAGE_SIZE 50). Invoices, notes, receipts, journals, payment links silently drop page 2+. |
| Q-067 | P1 | Frontend | `NewPurchasePage.tsx:1064-1066` | Preview error zeros subtotal/tax/grandTotal. Sales falls back to client totals. Cashier can believe ₹0. |
| Q-068 | P1 | Frontend | `NewInvoicePage.tsx:628-651` | Mark-fully-paid / amount received uses client totals, not shownTotals from preview. Payable can mismatch the displayed grand total. |
| Q-069 | P1 | Offline | `useInvoiceOffline.ts:66-77` | Flush createReceipt/createAllocation have no idempotency key. Flaky recovery can duplicate receipts/allocations. |
| Q-070 | P1 | Offline | `flushPosCheckout.ts:80-94` | POS flush allocation has no idempotency key. Partial retry after receipt success can double-allocate. |
| Q-071 | P1 | i18n | `web/src/i18n/gu.ts + ta.ts` | Gujarati and Tamil catalogs are ...en plus the locale label. Switcher still offers them. False localization claim. |
| Q-072 | P1 | Imports | `reporting/chase.py:95-98` | Chase OCR start_extraction except Exception: pass. Status stays RECEIVED while the import job failed. |
| Q-073 | P2 | Core | `core/csv_utils.py:21-27` | CSV formula neutralization checks text[0] only. Leading space/NBSP before =/+/@ is not neutralized. |
| Q-074 | P2 | Core | `core/throttles.py:31-34` | CompanyRateThrottle cache key None when no company → DRF skips throttle (fail-open). |
| Q-075 | P2 | Core | `core/views.py:313-330` | MetricsView: non-prod/staging with empty METRICS_TOKEN is AllowAny. |
| Q-076 | P2 | Core | `core/events.py:25-35` | Handlers run inside the emitter transaction; failures swallowed. PDF/notify can silently not fire while Complete commits. |
| Q-077 | P2 | Core | `gsp_secrets.py:46-48` | Decrypt failure returns {}. Indistinguishable from no credentials. e-invoice/WhatsApp die with no alert. |
| Q-078 | P2 | Core | `whatsapp.py:80-82,143-148` | Decrypt/HTTP failures silently fall back to wa.me. Callers can treat as success unless they inspect mode. |
| Q-079 | P2 | Core | `core/middleware.py:101-109` | RLS Cookie JWT exceptions swallowed. Unauthenticated path may run with empty app.company_id. |
| Q-080 | P2 | Core | `core/permissions.py:50-55` | Auto-set active_company on single membership uses bare except Exception: pass. |
| Q-081 | P2 | Core | `document_numbers.py:68-82` | Any company GSTIN forces GSTIN+FY series keys even when doc_number_scope=COMPANY. |
| Q-082 | P2 | Auth | `accounts/serializers.py:508-516` | Clearing is_primary without promoting another can leave zero primary GSTINs. |
| Q-083 | P2 | Auth | `accounts/views.py:519-527` | OTP verify maps missing user / unusable password / no membership to OtpExpiredError. Wrong message for several failures. |
| Q-084 | P2 | Auth | `accounts/views.py:465-477` | OTP SMS failure deletes challenge after rate-limit already recorded. User burns hourly budget with no code. |
| Q-085 | P2 | Auth | `accounts/export_views.py:86` | Restore rate-limit cache set before restore succeeds. Failed restore still burns 10 minutes. |
| Q-086 | P2 | Auth | `accounts/models.py:49-57` | canonicalize_user_phone ValueError stores raw phone. Unique is exact-string; format variants can still collide conceptually. |
| Q-087 | P2 | Auth | `accounts/views.py:86-97` | Refresh cookie Secure tied to CSRF_COOKIE_SECURE, not a dedicated JWT flag. |
| Q-088 | P2 | Billing | `billing/views.py:124-136` | Unsigned webhook allowed when DJANGO_ENV=test even without test header. Dangerous if env mis-set to test on a public host. |
| Q-089 | P2 | Sales | `sales/services.py:809-820` | Missing HSN hard-fails only when e-invoice + buyer GSTIN. B2C / non-e-invoice completes with empty HSN. GSTR Table 12 gaps. |
| Q-090 | P2 | Sales | `sales/services.py:1085-1089` | Invoice cancel restores only .first() linked challan. Other converted challans unrestored if multi-link exists. |
| Q-091 | P2 | Sales | `sales/cogs_service.py:116-128` | Challan-stocked invoice COGS falls back to current valuation when challan unit_cost is 0. |
| Q-092 | P2 | Sales | `sales/services.py:583-609` | H9 qty amend (non-batch) uses ADJUSTMENT restore, not peel restore. FIFO/COGS unsafe if anything bypasses H9-A qty block. |
| Q-093 | P2 | Sales | `sales/serializers.py:456-463` | Quotations burn number on draft create. Abandoned drafts burn sequences. |
| Q-094 | P2 | Sales | `phase1_serializers.py:204-274` | SalesOrder/DeliveryChallan serializers lack supply_type / company_gstin. Convert always default B2B / primary GSTIN. |
| Q-095 | P2 | Sales | `einvoice_eway_actions.py:70` | E-way claim filters eway_bill_no=\"\" only. NULL bill numbers bypass the claim. |
| Q-096 | P2 | Sales | `notes_services.py:66-82` | CN headroom uses grand_total including TCS. Wrong on legacy rows with tcs_in_grand_total=False. |
| Q-097 | P2 | Purchases | `purchases/services.py:347-403` | Purchase H9 qty stock path has no batch/serial guard. Bypass of H9-A desyncs batch inventory. |
| Q-098 | P2 | Purchases | `purchases/services.py:692` | Purchase batch get_or_create warns and keeps existing expiry on clash. |
| Q-099 | P2 | Payments | `payments/recon.py:175-215` | Bank recon can score ≥40 from UTR/name/date without amount match. Suggestions look high-confidence with wrong amount. |
| Q-100 | P2 | Payments | `payments/dunning.py:133-228` | IntegrityError on reminder create swallowed. WA exception falls through to SMS. Duplicate or skipped cadence. |
| Q-101 | P2 | Payments | `payments/webhook_views.py:111-122` | Ambiguous provider_link_id → 409 forever; provider retries; capture delayed. |
| Q-102 | P2 | Payments | `payments/tasks.py:8,75-81` | autoretry_for=Exception after marking FAILED burns attempt counter fast toward the stuck cap. |
| Q-103 | P2 | Payments | `payments/views.py:469-473` | Invalid refund amount Decimal(str(...)) uncaught in view → 500. |
| Q-104 | P2 | Inventory | `inventory/services.py:807-817` | FEFO recursive reserve uses unlocked available_quantity then locks. Concurrent reserves can over-reserve across lots. |
| Q-105 | P2 | Inventory | `inventory/services.py:579-598` | WARN + layer shortfall invents layer_id:None peels. Later restore creates synthetic layers; cost genealogy broken. |
| Q-106 | P2 | Inventory | `inventory/services.py:923-941` | rebuild_balance FEFO reserved assignment only stamps matching batch row. Other lot reserved can be wiped. |
| Q-107 | P2 | Manufacturing | `manufacturing/services.py:206-209` | Zero issue cost falls back to purchase_price × qty. WIP GL invents cost when movements lack unit_cost. |
| Q-108 | P2 | Manufacturing | `manufacturing/services.py:229-235` | Existing FG batch: conflicting expiry logged and ignored. Wrong FEFO later. |
| Q-109 | P2 | Manufacturing | `manufacturing/services.py:321-334` | Cancel completed WO scraps FG serials only if wo.serial_numbers is set. Empty list → FG serials stay AVAILABLE after stock reverse. |
| Q-110 | P2 | Payroll | `payroll/services.py:161-176` | PF ceiling stays full-month 15000 while Basic+DA prorated. ESI eligibility on full gross, contribution on prorated. Borderline employees wrong. |
| Q-111 | P2 | Payroll | `payroll/views.py:86-92` | LOP paid_days has no upper bound vs calendar days. Nonsense data still computes. |
| Q-112 | P2 | Accounting | `accounting/reports.py:335-352` | FY close WIP GL is net 1450 as-of fy_end all history. Prior-year WIP imbalance blocks this FY. Period close vs FY close gates disagree. |
| Q-113 | P2 | GST | `reporting/gstr2b.py:102-109` | 2B match uses calendar year, not Indian FY. Wrong PI linked across FY boundary in the same calendar year. |
| Q-114 | P2 | GST | `reporting/gstr2b.py:39-41` | _invoice_still_matches_2b allows any same-year date. Sticky MATCH survives large date drift. |
| Q-115 | P2 | GST | `reporting/gst_returns.py:522-534,846` | SUPECOM Table 15 still counted in B2 / 3.1(a). Easy to double-file if CA misses the note. |
| Q-116 | P2 | GST | `reporting/ims.py:199-208` | bulk_accept_exact chunks 500 separate atomics. Mid-failure: some accepted, some not. |
| Q-117 | P2 | GST | `reporting/ims_offline.py:98-107` | Offline IMS import trusts client match_status / itc_eligibility. Tampered JSON can mark CLAIMABLE before reclassify. |
| Q-118 | P2 | GST | `reporting/gst_returns.py:996-1001` | GSTR-1 AT empty for non-primary GSTIN stamp. Multi-GSTIN advances only on primary — easy to miss. |
| Q-119 | P2 | Tally | `integrations/tally/adapter.py:186-207` | Post-commit recon uses whole-company AR/AP vs this import’s openings. Existing books make recon fail after COMMITTED. |
| Q-120 | P2 | Masters | `masters/pricing.py:41-56 vs serializers.py:235-245` | Overlap checked on nested PriceList create, not single PriceListItem API. Item-level create can overlap slabs. |
| Q-121 | P2 | Masters | `masters/views.py:27,77` | 60s list cache not invalidated on write. Stale pickers after create. |
| Q-122 | P2 | Banking | `banking/services.py:42-55` | AA match: first UTR hit wins; amount only within tolerance; null txn_date skips date window. Wrong receipt linked. |
| Q-123 | P2 | Frontend | `JournalsPage.tsx:25-28` | listJournalsPage with no pageSize / no pagination UI. Older journals invisible. |
| Q-124 | P2 | Frontend | `PayRunsPage.tsx:68,95` | Employees list pageSize 200. Companies with >200 employees: LOP dialog incomplete. |
| Q-125 | P2 | Frontend | `invoiceDraftCache.ts:27-30` | Documented plaintext outbox on shared POS devices. Invoice PII at rest in IDB/LS. |
| Q-126 | P2 | Frontend | `usePreviewTotals / NewInvoicePage` | No abort of in-flight preview. Rapid edits can apply stale totals. |
| Q-127 | P2 | Core | `core/models.py:164` | AuditEvent.action choices are CREATE/UPDATE/DELETE/LOGIN but callers log billing.checkout, tenant.export. Invalid choice values. |
| Q-128 | P2 | Core | `sms.py:201-203` | MSG91 cannot send AR dunning texts. Dunning SMS needs Twilio or console. Channel looks live, is not. |
| Q-129 | P2 | Core | `core/rls.py + settings` | POSTGRES_RLS_ENABLED default off. Tenancy is app-layer until ops opts in. RLS job in CI is optional. |
| Q-130 | P2 | Sales | `sales/return_service.py:251-267` | Scrap COGS share by qty not cost. Wrong scrap expense when damaged vs sellable lines have different unit costs. |
| Q-131 | P2 | Purchases | `purchases/services.py:914` | PR Complete requires invoice COMPLETED only. Blocked after another return marks RETURNED. |
| Q-132 | P2 | Payments | `payments/services.py:1319-1324` | Payment health cached 60s. Stuck-refund critical alert lags. |
| Q-133 | P2 | Imports | `imports/services.py:40-41` | Hard cap 20k rows / 500k cells. Large Tally dumps need split with no UI guidance. |
| Q-134 | P2 | Insights | `insights/alerts.py:278-292` | SALE_BELOW_COST capped at 500 lines / one per SKU. Misses later below-cost SKUs in busy months. |
| Q-135 | P2 | Core | `h9_amend.py:84-115` | lines_prices_unchanged ignores cess/supply_nature. Cess-only change may skip needs_amend if FE omits cess keys. |
| Q-136 | P3 | Core | `core/permissions.py:83-90` | IsOwner requires role==OWNER only. Docs say Owner/Admin; no Admin role exists. |
| Q-137 | P3 | Core | `core/models.py:209` | Notification docstring still says SMS/Push stubbed while SMS path is implemented. |
| Q-138 | P3 | Core | `config/settings.py:700-702` | WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID still defined; whatsapp.py refuses process-wide tokens. |
| Q-139 | P3 | Core | `core/idempotency.py:15` | DEFAULT_TTL retained but unused (rows are durable). Misleading API. |
| Q-140 | P3 | Billing | `config/settings_test.py:65-66` | UNSUBSCRIBED_SEAT_LIMIT=0 (unlimited) in tests hides production default of 1. |
| Q-141 | P3 | Auth | `accounts/views.py:161-163` | OTP phone rate limits are cache-only. LocMem across workers would not share caps. |
| Q-142 | P3 | Sales | `sales/services.py:741,922` | apply_tcs_fold twice on complete. Idempotent now; easy to double-fold if unfold flags regress. |
| Q-143 | P3 | Frontend | `DashboardPage.tsx:92-107` | Aging key alias soup papers over API contract drift. Bucket can silently show 0. |
| Q-144 | P3 | Masters | `masters/serializers.py product validate` | Product validate auto-creates Unit/Category/Brand from free text. Typos proliferate. |
| Q-145 | UX | Frontend | `InvoiceTemplatesPage.tsx:21-53` | Page is a static layout legend + terms textarea. Success toast 'Invoice terms saved' not i18n. No template picker, preview, or ORIGINAL/DUPLICATE variants. |
| Q-146 | UX | Frontend | `DraftLineTable.tsx:79-89` | HSN column display:none on xs. Serials header hardcoded English. Mobile invoice editor hides HSN. |
| Q-147 | UX | Frontend | `erpShared.tsx:34-38` | Manufacturing/Payroll/CRM show MvpModuleBanner. Thin CRUD, not full ERP. Operators may still treat numbers as production-grade. |
| Q-148 | UX | Frontend | `JournalsPage.tsx:77-161` | Almost entirely hardcoded English: New voucher, Post, Reverse, columns, dialogs. |
| Q-149 | UX | Frontend | `InvoiceDetailPage.tsx:822-976` | E-way / amend labels hardcoded English: Vehicle no, Transporter, Filing party GSTIN, phone placeholder 9198XXXXXXXX. |
| Q-150 | UX | Frontend | `NewInvoicePage.tsx:1252-1814` | Supply type and payment mode MenuItems hardcoded English. TCS block labels English. |
| Q-151 | UX | Frontend | `ItemFormDialog.tsx:463-1059` | Large cluster of English labels on product create despite i18n elsewhere. |
| Q-152 | UX | Frontend | `NewInvoicePage.tsx aria` | Invoice editor has almost no aria-live. Preview pending / complete failure after create is easy to miss. |
| Q-153 | UX | Frontend | `PosPage.tsx` | No cash-drawer ESC/POS pulse. Status chip visual-only; no aria-live for offline/sync/error. Cash always allocates full grandTotal — no partial pay. |
| Q-154 | UX | Frontend | `App.tsx GSTR 6/7/8 routes` | Honest stubs (supported:false) still routed in nav. Users may treat worksheets as portal files. |
| Q-155 | UX | Frontend | `permissions.ts canManageGst` | GST settings Owner-only; GSTR reports = financial reports. Accountant sees returns but cannot fix GSTIN/HSN settings that cause drops. |
| Q-156 | UX | Frontend | `OfflineOutboxPage + NewInvoice` | Complete blocked until preview.ready when online — good — but slow network feels stuck without a pending indicator. |
| Q-157 | UX | Frontend | `PartySelectPanel` | Warns only if both state and GSTIN missing. Invalid GSTIN checksum looks fine. Selected-party block is not a named region. |
| Q-158 | UX | Frontend | `Help v0 vs v2` | helpV2 staff override: staff see v2, customers may see FAQ-only v0. Inconsistent Help. |
| Q-159 | UX | Frontend | `onboarding` | Blocking step can be catalog while ui_step shows payments. Progress bar lies. |
| Q-160 | UX | Frontend | `exceptions.py nested errors` | Nested serializer errors can still render as Python repr in toasts. Unreadable for cashiers. |
| Q-161 | UX | Frontend | `GST returns UI` | Honesty flags / SUPECOM double-count / AT rate_unknown are easy to miss. CA can double-file. |
| Q-162 | UX | Frontend | `Tally commit UI` | Commit success can look like full parity. force= and  recon warnings are easy to skip. Export truncate (if still present) has no banner. |
| Q-163 | UX | Frontend | `Insights narrative` | Daily narrative presents AR/AP as facts. Margin/alerts use list price or receipts mix — copy over-promises. |
| Q-164 | UX | Frontend | `Payroll UI` | PT/ESI/PF numbers can be silently wrong after cancel→recomplete with no warning chip. |
| Q-165 | UX | Frontend | `Manufacturing WorkOrdersPage` | Release/complete require serials for serial-tracked BOM; UI never collects component_serials. Confirm copy promises stock+WIP reverse. |
| Q-166 | UX | Frontend | `LoginPage / ForgotPassword` | Validation strings and some placeholders hardcoded English. Hindi switcher does not cover auth fully. |
| Q-167 | UX | Frontend | `unitLabels.ts` | Incomplete vs GSTN UQC (QTL, TON, SQM, KME). Raw codes shown in billing. |
| Q-168 | UX | Frontend | `File download` | Content-Type guessed from filename, not asset.content_type. |
| Q-169 | UX | Frontend | `UnsavedChangesGuard` | Dirty = lines.length > 0 on invoice. Header/party/TCS edits with no lines leave without warning. After successful save, guard can still fire. |
| Q-170 | UX | Frontend | `App.tsx offline outbox` | Outbox route has no role gate. Any authenticated user sees queued drafts (PII) on a shared device. |
| Q-171 | UX | Frontend | `CreditNotesPage Complete buttons` | View ACL can show Complete/Cancel/Convert; backend 403s. Same pattern on purchase editors. |
| Q-172 | UX | Frontend | `Keyboard shortcuts` | Ctrl+S / Ctrl+Enter exist; no in-app cheat-sheet. Ctrl+S on invoice drafts even when canSave is false (no customer / empty lines) on some paths. |
| Q-173 | UX | Mobile | `mobile/README.md` | Capacitor WebView over web/dist, not native screens. 8h offline / 50 drafts is a lab claim on web IDB. No iOS ship. allowBackup=false is good. |
| Q-174 | UX | Frontend | `a11y.spec.ts` | E2E a11y is a light suite. Invoice/POS/reports lack results-count live regions and named regions on pickers. |
| Q-175 | GAP | GST | `reporting/gstr2b.py:274-324` | GSTR-4/6/7/8 are honesty stubs (supported:false). Composition / ISD / TCS / TDS dealers have no engine. |
| Q-176 | GAP | GST | `reporting/gst_returns.py:1603-1894` | GSTR-9 is a worksheet aid, not a full annual engine. Tables 6–8 / HSN labeled aids. |
| Q-177 | GAP | Auth | `accounts/tenant_backup.py` | Backup omits CRM, manufacturing, payroll, banking, import jobs, DocumentSeries, batch FKs on items, logo FKs. Partial tenant backup sold as restore. |
| Q-178 | GAP | Billing | `billing/views.py:97-100` | Hosted Razorpay customer portal not wired. No self-serve cancel/pause/change-plan APIs. |
| Q-179 | GAP | Core | `notifications.py:91-97` | Push channel: create row then fail not implemented. SMS/Push docstring still stub language. |
| Q-180 | GAP | Sales | `Invoice templates` | No multiple templates, per-GSTIN header, preview, logo/sign placement, or real ORIGINAL/DUPLICATE copies. |
| Q-181 | GAP | Manufacturing | `BOM+WO only` | No routing, by-products, shop-floor execution beyond telemetry POST, true WIP vs 1450, or FIFO restore contract on cancel. |
| Q-182 | GAP | Payroll | `pay runs + LOP` | No Form 24Q/16, attendance import, state PT completeness, employer expense split from 5800. |
| Q-183 | GAP | CRM | `leads→opportunity` | No pipeline stages, activities, quote linkage, or duplicate-party confirm on convert. |
| Q-184 | GAP | Banking | `AA UTR icontains` | Not a full Account Aggregator product. No atomic match, no ambiguous-UTR reject. |
| Q-185 | GAP | Masters | `hsn_catalog.py` | Starter rates seed a tiny HSN set; search_hsn is a static COMMON list, not GSTN. Almost all HSN → None. |
| Q-186 | GAP | Sales | `quotation API` | Quotation lines cannot set cess/HSN/inclusive. Sales/purchase return APIs omit HSN/cess. Partial commercial docs. |
| Q-187 | GAP | Core | `POS cash drawer` | No ESC/POS drawer pulse. Counter flow is receipt/thermal print only. |
| Q-188 | GAP | Auth | `invite create` | Invite URL returned to owner only. No email/SMS send of invite in this view. |
| Q-189 | GAP | Payments | `payments/gateway.py:675` | Cashfree/PayU still fail-closed stubs in places; fee parsing missing. Partial gateway product. |
| Q-190 | GAP | Frontend | `books_start_date / doc_number_scope` | Model fields exist; CompanySerializer/UI do not expose them. FY numbering scope is unconfigurable from product UI. |
| Q-191 | GAP | CI | `web/e2e + e2e-golden` | Light e2e is login/templates/upload smoke. Golden is one invoice path. No returns, GST file, POS offline, payroll, or Tally e2e. |
| Q-192 | GAP | CI | `.github/workflows/ci.yml postgres-rls` | RLS job is a thin tenant smoke, not full suite under POSTGRES_RLS_ENABLED. Default prod still RLS off. |
| Q-193 | GAP | Help | `help_codes vs BusinessRuleError` | Many BusinessRuleErrors still generic business_rule_violation. Sparse deep-links from money errors. |
| Q-194 | SUGG | Payments | `refund outbox` | Do not mark books REFUNDED until outbox SUCCEEDED; compensate on permanent failure; fix Razorpay idempotency header; re-queue FAILED. |
| Q-195 | SUGG | GST | `3.1(a)` | Fix _non_rcm_sum: include RCM taxable, exclude RCM tax only. Align comment, GSTR-1 footing, and 3B. |
| Q-196 | SUGG | Frontend | `legacy lists` | Replace fetchMoneyListFirstPage with fetchPage + UI pagination (or fetchAllPagesMasters where bounded). |
| Q-197 | SUGG | Auth | `seats` | Hold select_for_update through invite create; enforce seats on PATCH reactivate; blacklist refresh on company switch. |
| Q-198 | SUGG | i18n | `gu/ta + hardcoded` | CI check: every en.ts key in hi.ts; hide gu/ta until catalogs exist; no hardcoded billing/journal strings. |
| Q-199 | SUGG | Inventory | `serializers` | Use CompanyPrimaryKeyRelatedField on SerialNumber and BatchLot like WarehouseReorderLevel already does. |
| Q-200 | SUGG | Accounting | `H9` | Rename post_purchase_invoice → post_purchase or add alias. Wrap sales H9 adjust+serializer in one atomic. |
| Q-201 | SUGG | Core | `feature flags` | Treat plan_modules is None like fail-closed for DARK_MODULE_KEYS. Check current_period_end on ACTIVE. |
| Q-202 | SUGG | Payroll | `re-complete` | On re-complete with paid_days, always start from emp.salary (store gross_full). Single proration. |
| Q-203 | SUGG | Offline | `flush` | One flush path; always send idempotency on receipt+allocation; never Complete unpaid UPI. |
| Q-204 | SUGG | GST | `IMS` | Do not deemed-ACCEPT on soft-close. Owner-gate mutate. Unique 2B including blank-number strategy. |
| Q-205 | SUGG | PDF | `statutory` | Print TCS, POS, stamped branch GSTIN/address, supplier_bill_number on all GST PDFs and thermal. |
| Q-206 | SUGG | Observability | `ops` | Alert on GSP decrypt {}, MSG91 type=error, refund IN_PROGRESS >10m, attempts>=8, 3.1(a) vs GSTR-1 footing mismatch. |
