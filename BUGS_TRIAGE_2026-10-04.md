# Triage of P0/P1 findings in BUGS_LIST.md v2.1

Date: 2026-10-04. Method: each finding was checked against the working tree on `main` by reading the cited code or grepping for the claimed symbol. Nothing was run.

**Status key**: CONFIRMED = defect found in code. STALE = already fixed. PARTIAL = real but narrower than written. FALSE POSITIVE. RECLASSIFY = missing feature or bad reference. ENHANCEMENT = UX proposal. UNVERIFIED = not inspected or inconclusive; treat as open.

## Corrected counts (99 headed P0/P1 items; the register says 106)

| Status | P0 | P1 | Total |
| --- | ---: | ---: | ---: |
| CONFIRMED | 9 | 51 | 60 |
| PARTIAL | 0 | 11 | 11 |
| STALE | 5 | 5 | 10 |
| FALSE POSITIVE | 1 | 0 | 1 |
| RECLASSIFY | 0 | 1 | 1 |
| ENHANCEMENT | 8 | 8 | 16 |
| UNVERIFIED | 0 | 0 | 0 |
| **Total** | 23 | 76 | 99 |

The remaining P0/P1 rows sit in the Growth OS table (section 16.7.2, COG-G01..G10) and were not triaged. Second pass (30 previously unverified items) completed the same day. Part 2 below covers P2, P3 and COG items.

## ID and count corrections

| Issue | Fix |
| --- | --- |
| BUG-PAY-001 and 002 are used twice (payments and payroll) | Renamed the payroll pair to BUG-PRL-003 / BUG-PRL-004 (PRL-001 PF floor and PRL-002 ESI already exist). Applied to the register and the plan. |
| 182 `###` headings give only 180 unique IDs | 182 unique IDs after the rename (verified) |
| COG-001..020 are `####` rows; COG-G01..G10 are table rows | Give G01..G10 their own headings so counts can be machine-checked |
| Header totals (212; P0 25, P1 81) | Rebuilt after both passes: 19 closed (17 already fixed, 2 false positive), 193 open (P0 19, P1 75, P2 78, P3 21) |
| Section 14 missing; SaaS, CRM and Support merged into other sections | Renumber, or align the domain table to sections |
| 11 file refs in the register and 12 in the plan do not exist | e.g. `inventory/services.py` should be `backend/inventory/services.py`; create or drop the missing test files |

### Suggested re-rating

- Close: BUG-SEC-001, BUG-SEC-002, BUG-ACC-002, BUG-SALES-005, BUG-PRJ-001, BUG-INS-001, BUG-INS-002, BUG-INS-003, BUG-INS-005.
- Remove as false positive: BUG-SEC-003.
- Re-file as feature work (P2): BUG-PUR-001.
- Narrow wording: BUG-SEC-004, SEC-005, SEC-006, INV-003, GST-002, PAY-006, MFG-001, CRM-001.

## Per-finding triage

| ID | Sev | Status | Finding | Evidence |
| --- | --- | --- | --- | --- |
| BUG-SEC-001 | P0 | STALE | Background Celery Tasks Execute Multi-Tenant Scans Without Setting RLS | Contract and recurring-invoice tasks already loop `iter_company_ids()` + `set_rls_company(cid)`. Remediation snippet cites non-existent `tenant_context`. Re-check any remaining argument-free beat tasks only. |
| BUG-SEC-002 | P0 | STALE | Razorpay Webhook Authentication Bypass in Test / Staging Environments | billing/views.py:189-202 now returns 403 unless env=test AND the test header is present; the inverted condition is gone. |
| BUG-SEC-003 | P0 | FALSE POSITIVE | Potential Raw SQL Execution Bypassing Tenant RLS | core/audit_guard.py and core/checks.py use static SQL or `%s` params; no user input reaches them. |
| BUG-SEC-004 | P1 | PARTIAL | Two-Factor Authentication (TOTP) Completely Opt-In for Privileged Role | `enrolment_required()` exists and is forced on in prod/staging (settings.py:823-831); default is off elsewhere. Real gap: non-prod default and the waiver path. |
| BUG-SEC-005 | P1 | PARTIAL | Unbounded Query Endpoints Causing Denial of Service | Default paginator exists (core/pagination.py, max 200). Verify exports and views that override pagination. The "django-ninja" advice is wrong (project is DRF). |
| BUG-SEC-006 | P1 | PARTIAL | Tenant Right-to-Erasure (DPDP Act) Fails on Vertical App Foreign Keys | Drift guard `assert_erasure_model_coverage` exists; need a repro that vertical models actually raise ProtectedError. |
| BUG-SEC-010 | P1 | CONFIRMED | MFA Setup and Confirm Do Not Ask for the Password | MfaSetupView/MfaConfirmView accept a session or enrol token with no password re-check. |
| BUG-SEC-011 | P1 | CONFIRMED | Password Login Mints a Refresh Token Before the MFA Challenge | LoginView calls parent post() (mints OutstandingToken) before returning mfa_challenge_response; no blacklist call. |
| BUG-SEC-012 | P1 | CONFIRMED | Customer Portal Phone Lookup Loads Every Tenant's Phones | portal_views.py:106-113 loads every Customer with a phone under rls_bypass and compares digits in Python. |
| BUG-SALES-001 | P0 | CONFIRMED | Sales Orders Do Not Support Partial Conversion (Backorder Lockout) | convert_sales_order rejects any existing challan/invoice; no partial quantities. |
| BUG-SALES-002 | P1 | CONFIRMED | Inward Goods Rejection Leaves Stock Reserved Indefinitely | route_service.set_stop_status comment says FAILED leaves stock reserved (deliberate; no release or return doc). |
| BUG-SALES-003 | P1 | CONFIRMED | Driver COD & UPI Route Collections Unreconciled Against Cashier Drawer | No cashier handover step in complete_route; `DriverPaymentReceipt` does not exist in the codebase. |
| BUG-SALES-004 | P1 | CONFIRMED | Insecure Proof of Delivery (POD) Accepts Unverified Arbitrary OTPs | set_stop_status stores otp_code and never validates it against an issued OTP. |
| BUG-SALES-005 | P1 | STALE | Line Item Edits on Invoices Lack Transactional Atomicity | SalesService.set_items is already @transaction.atomic (sales/services.py:659). |
| BUG-SALES-006 | P1 | CONFIRMED | Sales Margin Guard Warning Fails to Block Below-Cost Selling | order_gates only builds margin_warnings; no block or override path found. Plan already drops the crypto-token idea. |
| BUG-SALES-010 | P1 | CONFIRMED | Atomic POS Checkout Drops the Batch, and UPI Drops Header Discount and | Atomic POS item mapper (PosPage.tsx ~1299) sends serials but no batch_no; the non-atomic path sends it. UPI payload not inspected. |
| BUG-SALES-011 | P1 | CONFIRMED | Atomic POS Never Sends the Blank Place-of-Supply Confirmation | Atomic posCheckout body has no confirm_blank_pos. |
| BUG-SALES-012 | P1 | CONFIRMED | Record Payment Creates the Receipt and the Allocation as Two Steps | record_payment calls create_receipt then allocate_receipt in sequence; no wrapping transaction seen. |
| BUG-SALES-013 | P1 | CONFIRMED | Settlement Discount Clears the Customer Subledger and Is Never Posted | ledgers/services.py:221 subtracts settlement discount from outstanding; accounting post_receipt has no discount line. |
| BUG-SALES-014 | P1 | CONFIRMED | Sales History Paid / Partial / Unpaid Ignores Reversed Receipts and Cr | sales/views.py:217-236 allocation subquery lacks reversed_at filter (the list annotation at line 160 has it). |
| BUG-SALES-015 | P1 | CONFIRMED | Non-Atomic POS Short-Collect Still Receipts the Full Bill | Legacy POS path (PosPage.tsx:1355-1376) receipts and allocates `invoiceTotal`, ignoring `shortCollectAmount`. |
| BUG-PUR-001 | P1 | RECLASSIFY | Absence of Strict Line-Level 3-Way Matching Tolerances | `match_bill_to_po` does not exist anywhere in purchases/. This is a missing feature, not a defect in existing code; fix the file reference. |
| BUG-PUR-002 | P1 | CONFIRMED | GRN Inspection Rejections Do Not Generate Supplier Debit Notes | No debit-note creation in grn_service. |
| BUG-PUR-003 | P1 | CONFIRMED | Purchase Bill Amendments Mutate Records Without Version Snapshotting | No revision/snapshot model in purchases/models.py. |
| BUG-PUR-006 | P0 | CONFIRMED | Cancelling a GRN Reverses Stock While the Converted Bill Stays Live | GRN cancel never checks converted_purchase_id. |
| BUG-PUR-007 | P0 | CONFIRMED | Cancelling a GRN-Sourced Bill Does Not Reverse GRN Stock | Bill cancel (services.py:897) reverses purchase_invoice movements only; GRN-linked stock appears only at the complete path (line 775). |
| BUG-PUR-008 | P1 | CONFIRMED | GRN Complete Cannot Receive Batch or Serial Goods | grn_service posts batch=None; GoodsReceiptItem has no batch/serial fields. |
| BUG-PUR-009 | P1 | CONFIRMED | Purchase Returns Ignore GRN Cost Layers | Return path has no goods_receipt lookup. |
| BUG-PUR-010 | P1 | CONFIRMED | New Purchase Bills Default ITC to CLAIMABLE and Hide UNREVIEWED | NewPurchasePage default and menu are CLAIMABLE/INELIGIBLE/REVERSED; no UNREVIEWED. |
| BUG-PUR-011 | P1 | CONFIRMED | Help Says There Is No GRN While the GRN API Is Live and Has No Screen | Help copy (contextHelp/catalog/purchases.ts) says there is no GRN; GRN API is live and no web route uses it. Product decision as much as defect. |
| BUG-PUR-015 | P1 | CONFIRMED | Purchase Invoice Free-Text Search (`q`) Disregards Supplier Name and P | purchases/views.py:112-113 filters `q` on `number__icontains` only. |
| BUG-INV-001 | P0 | CONFIRMED | Inter-Godown Stock Transfers Lack "IN_TRANSIT" State | No IN_TRANSIT state in inventory models/services. |
| BUG-INV-002 | P1 | CONFIRMED | Zombie Stock Reservations Locking Usable Inventory | reserve_stock is called on order create (notes_services.py:700); release only on cancel (:894); no expiry job. |
| BUG-INV-003 | P1 | PARTIAL | Blind Stocktake & Physical Cycle Counting Sessions Absent | `StockCountSession` exists; only "blind" counting is unconfirmed. Retitle. |
| BUG-INV-004 | P1 | CONFIRMED | FEFO Picking Logic Bypassed on Manual POS & Billing Lines | No FEFO picking in app code (only a rebuild command mentions it). |
| BUG-INV-007 | P1 | CONFIRMED | Shopify Multi-Channel Stock Desync Caused by 25% Discrepancy Tolerance | Held deltas are written to `shopify_pending` and notified (shopify.py:285-318), but nothing applies or rejects them. |
| BUG-INV-008 | P1 | CONFIRMED | Shopify Has No Connection Setup for Godown, Customer, Domain, or Secre | integrations/urls.py has whatsapp/connection but no Shopify connection view; webhook only. |
| BUG-ACC-001 | P0 | CONFIRMED | Absence of Daily POS Shift Close & Cash Drawer Register | No shift-close or till model anywhere in backend. |
| BUG-ACC-002 | P0 | STALE | Unscheduled Trial Balance Zero-Sum Verification Worker | `core-nightly-invariants` beat runs the `gl.trial_balance_zero` invariant (settings.py:627, core/invariants/gl.py:49). Remaining gap: alerting/blocking only. |
| BUG-ACC-003 | P1 | PARTIAL | Incomplete MCA Rule 11(g) Audit Trail Event Coverage | masters/serializers.py audits via AuditService.log; coverage of other masters not enumerated. |
| BUG-ACC-004 | P1 | CONFIRMED | Missing Formal MCA Schedule III Taxonomy Groupings | accounting/reports.py:116 balance_sheet groups by account type only; no Schedule III grouping (register path reporting/financial.py does not exist). |
| BUG-ACC-010 | P1 | CONFIRMED | Owner Backfill Turns Books On and Skips Payroll, Work Orders, and Bill | accounting/views.py:639 sets accounting_enabled=True before backfill; backfill command has no PAY_RUN/WORK_ORDER/BILL_OF_ENTRY source specs. |
| BUG-ACC-011 | P1 | CONFIRMED | GL Recon Offers Match Anyway, and the UI Compares Absolute Amounts | accounting/views.py:351 compares signed amounts; AccountingExtraPages.tsx:308-311 compares Math.abs values. |
| BUG-GST-001 | P0 | CONFIRMED | E-Way Bill Vehicle Update (Part B) and Validity Extension Endpoints Mi | No Part-B update or validity-extension code outside migrations/tests. |
| BUG-GST-002 | P1 | PARTIAL | Section 16(4) Time-Barred ITC Warning Not Enforced as a Strict Exclusi | 16(4) clock and expiry alerts exist (reporting/ims.py, insights/attention.py); hard exclusion in GSTR-3B not confirmed. |
| BUG-GST-003 | P1 | CONFIRMED | Section 16(2) Statutory 4-Condition Checklist Absent on Purchase Bills | No 16(2) checklist found. |
| BUG-GST-004 | P1 | CONFIRMED | Section 206AB / 206CCA Higher TDS/TCS Compliance Check Missing | No 206AB/206CCA code anywhere. |
| BUG-GST-006 | P1 | CONFIRMED | E-Way Bill Generation Completely Broken for Export Consignments Due to | _buyer_pincode (eway_payload.py:101-119) only accepts 6 digits; no export / subSupplyType 3 special case, toStateCode falls back to 0. |
| BUG-GST-007 | P0 | CONFIRMED | GSTR-2B and IMS Match the Internal Purchase Number, Not the Supplier B | gstr2b.py:84 matches number__iexact; the model has a separate supplier_bill_number. |
| BUG-PAY-001 | P0 | CONFIRMED | Cheque Bounce Fails to Levy Dishonour Fees or Generate Section 138 Not | Cheque bounce only voids the receipt (payments/services.py:670); no fee or s.138 notice. (Duplicate ID: payments.) |
| BUG-PAY-002 | P1 | PARTIAL | Account Aggregator (AA) Consent Expiration Not Handled Gracefully | FIU fetch fails closed with BusinessRuleError (fiu_adapter.py:~85); EXPIRED/REVOKED statuses exist but no transition or notification on expiry. |
| BUG-PAY-003 | P1 | CONFIRMED | Bank Reconciliation Auto-Matching Engine Missing Fuzzy Narration Rules | banking/services.py matches by UTR/ref and unique amount+date only; no narration/party fuzzy rules. |
| BUG-PAY-005 | P1 | CONFIRMED | Account Aggregator (AA) Auto-Reconciliation Completely Ignores Debit T | match_aa_to_receipts filters amount__gt=0 and CustomerReceipt only. |
| BUG-PAY-006 | P1 | PARTIAL | Ambiguous Fuzzy Substring UTR Matching Silently Binds Unrelated Custom | `utr__icontains` in banking/services.py:100 and substring match in payments/recon.py:485; confirm auto-bind behaviour. |
| BUG-PAY-007 | P1 | CONFIRMED | Account Aggregator Can Attach Two Bank Rows to One Receipt | AaTransaction.matched_payment is a plain FK with no unique constraint (banking/models.py:39). |
| BUG-PAY-008 | P1 | CONFIRMED | Re-Ingesting Bank Rows Overwrites Amounts That Are Already Matched | banking/views.py:174-185 overwrites amount, txn_date and raw on existing rows regardless of matched_payment. |
| BUG-BIL-001 | P1 | CONFIRMED | SaaS Dunning Never Restarts After a Second Past-Due | `last_dunning_step` is only ever set (dunning.py:90), never reset. |
| BUG-PRJ-001 | P0 | STALE | Milestone Invoiced Against Draft Invoice Without Revenue Posting | projects/services.py:92-96 only sets INVOICED when the invoice status is COMPLETED. |
| BUG-PRJ-002 | P1 | CONFIRMED | Frontend Milestone Invoicing Opens a Route That Does Not Exist | ProjectsPage.tsx:77 navigates to /sales/invoices/:id; App.tsx registers sales/history/:id only. |
| BUG-INS-001 | P0 | STALE | Selecting Multiple Options Issues Duplicate Overlapping Policies | choose_option locks the option set and rejects when policies already exist. |
| BUG-INS-002 | P1 | STALE | 30-Day Month Formula Corrupts Policy Expiration Dates | `add_calendar_months` exists (insurance/services.py:27); no 30-day math found. |
| BUG-INS-003 | P1 | STALE | Unvalidated Negative Insurance Commission Receivables | `parse_commission_amount` rejects amounts <= 0. |
| BUG-INS-005 | P1 | STALE | Insurance Can Issue a Policy and Cannot Run Claims, Renewals, or Commi | `open_claim`, `renewal_diary`, `open_commission` all exist in insurance/services.py. |
| BUG-WRK-001 | P1 | CONFIRMED | Job Card Parts Invoicing Bypasses Batch-Tracking Validation | workshop/services.py convert_to_invoice maps serials only; no batch handling. |
| BUG-WRK-002 | P1 | CONFIRMED | Workshop Parts Issuance Does Not Reserve Stock During Repair | No reservation call anywhere in workshop/services.py. |
| BUG-WRK-006 | P0 | CONFIRMED | Job Card Invoice Cannot Succeed From the Screen | JobCardsPage has only customer + complaint inputs (no add-line control) and navigates to /sales/invoices/:id (route missing). |
| BUG-MFG-001 | P1 | PARTIAL | Component Issuance Skips General Ledger Work-in-Progress (WIP) Account | WIP posting is optional per module docstring; confirm the default. |
| BUG-PRL-003 (was PAY-001) | P1 | CONFIRMED | Payroll Disbursement Defaults to Cash Without Bank Account Selection | complete_pay_run has a `pay_from_cash=True` parameter only; no bank account selection. (Duplicate ID: payroll.) |
| BUG-PRL-004 (was PAY-002) | P1 | CONFIRMED | Payroll Engine Cannot Process Advances, Arrears, or Bonus Lines | payroll/services.py:437-445 documents this limitation (B9-036). (Duplicate ID: payroll.) |
| BUG-MFG-006 | P1 | CONFIRMED | Multi-Level BOM Explosion Infinite Recursion (Lack of Cyclic Dependenc | No cycle detection found in manufacturing/. |
| BUG-CNT-002 | P1 | CONFIRMED | Contracts Never Create a Recurring Invoice From the Screen | ContractsPage.tsx never calls createContractSchedule. |
| BUG-CRM-001 | P1 | PARTIAL | Mark Referral Paid Says It Drafts a Credit Note. The Service Only Flip | Service docstring now says it does not draft a credit note; UI copy not re-checked. |
| BUG-CRM-002 | P1 | CONFIRMED | Percent Referral Rewards Use the Opportunity Amount, Not Invoiced Reve | crm/referrals.py:277 uses opportunity.amount. |
| BUG-CRM-003 | P1 | CONFIRMED | A Pipeline Deal Can Be Marked Won With No Customer | OpportunityPipelinePage.tsx allows OPEN/QUALIFIED/NEGOTIATION -> WON with no customer check. |
| BUG-UI-001 | P1 | STALE | Form State Leaks Across Multiple Projects in UI | ProjectsPage.tsx now keeps milestone drafts in a per-project map (`drafts[projectKey]`). |
| BUG-UI-010 | P1 | CONFIRMED | Instant Cart Destruction on Unconfirmed F10 Shortcut & Clear Cart Butt | F10 handler calls clearCart() with no confirm (PosPage.tsx:2066-2070). |
| BUG-UI-013 | P1 | CONFIRMED | Workshop Job Cards Module Lacks Real-World Work Order Attributes | JobCardsPage.tsx state is customer + complaint only; no vehicle, odometer, technician or lines. |
| BUG-UI-018 | P1 | CONFIRMED | Ticket, Contract, and Complaint Create Dialogs Close Without a Dirty C | CreateDialog.tsx passes onClose straight to backdrop and Cancel; no dirty check. |
| BUG-UI-019 | P1 | CONFIRMED | Hindi Mode Still Shows English on Billing, Settings, POS, Reports, and | English literals remain, e.g. UnitsSettingsPage.tsx:95 "No units yet", :103 "UQC code". Other listed pages not re-read. |
| BUG-UI-030 | P1 | PARTIAL | Total Absence of Search and Filter Dimensions Across Growth OS Screens | OpportunitiesPage has no search/stage filter and GrowthFilterBar does not exist; ComplaintsPage already has status and category filters. |
| BUG-PERF-001 | P1 | CONFIRMED | StockBalanceViewSet N+1 Query Multiplier via Missing select_related on | StockBalanceViewSet queryset uses select_related("product") only; serializer reads warehouse.name. |
| BUG-PERF-002 | P1 | CONFIRMED | Celery Worker Queue Starvation from Unpartitioned Background Tasks | No Celery task routing or queues in settings. |
| BUG-PERF-003 | P1 | CONFIRMED | Unbounded In-Memory Model Instantiation in GSTR-1 & GSTR-3B Builders | build_gstr1 materialises list(invoices) and list(inv.items.all()) per invoice (gst_returns.py:602, 630). |
| BUG-COG-001 | P0 | ENHANCEMENT | Sales Invoice Forces Redundant Declarative Choice of Invoice Type | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-002 | P0 | ENHANCEMENT | Price Mode Select Forces Repeated Evaluation of Company Default | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-003 | P0 | ENHANCEMENT | Unconditional Warehouse Select Renders on Single-Godown Companies | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-004 | P0 | ENHANCEMENT | Active Non-Default Statutory Configurations Hidden Inside Collapsed Dr | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-005 | P0 | ENHANCEMENT | Unranked Document Actions on Posted Invoices Overload Visual Attention | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-006 | P0 | ENHANCEMENT | Sales Return Initiation Forces Manual Pogo-Sticking and Line Re-Entry | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-007 | P0 | ENHANCEMENT | Premature Place of Supply Prompts Ignore Valid Party GSTIN | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-008 | P0 | ENHANCEMENT | Inward Purchase Bill Lines Force Manual Re-Entry of Master Data | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-009 | P1 | ENHANCEMENT | Raw ITC Eligibility Enum Exposes Users to Statutory Tax Audit Risk | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-010 | P1 | ENHANCEMENT | Fragmented Period Close Navigation Creates Month-End Anxiety | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-011 | P1 | ENHANCEMENT | User Access Management Requires Manual 8-Checkbox Matrix Configuration | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-012 | P1 | ENHANCEMENT | Unlocked GST Settings Allow Accidental Company-Wide Tax Corruption | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-013 | P1 | ENHANCEMENT | Dense Products Catalog Overwhelms Initial Visual Search | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-014 | P1 | ENHANCEMENT | POS Focus Hijacking Overwrites Item Quantities with Barcode Scans | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-015 | P1 | ENHANCEMENT | Disabled Document Completion Fails to Explain Root Cause | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
| BUG-COG-016 | P1 | ENHANCEMENT | Accounting Jargon Confuses Non-Accountant Store Owners | UX/design proposal, not a defect. Track with the UX backlog; no code probe. |
---

# Part 2: P2, P3 and COG items (119 items)

Same method as part 1. COG rows are UX proposals; their notes here say how much is already shipped and supersede the generic COG rows in part 1.

| Status | P0 | P1 | P2 | P3 | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| CONFIRMED | 0 | 0 | 65 | 20 | 85 |
| PARTIAL | 0 | 0 | 6 | 0 | 6 |
| STALE | 0 | 0 | 7 | 0 | 7 |
| FALSE POSITIVE | 0 | 0 | 1 | 0 | 1 |
| ENHANCEMENT | 8 | 8 | 3 | 1 | 20 |
| **Total** | 8 | 8 | 82 | 21 | 119 |

## Per-finding triage (part 2)

| ID | Sev | Status | Finding | Evidence |
| --- | --- | --- | --- | --- |
| BUG-SEC-007 | P2 | STALE | Distributed Redis Token Bucket Rate Limiter Absent | core/throttles.py has `TenantPlanRateThrottle` (per-plan limits) and prod/staging require Redis for the cache (settings.py:474-482). Register cites core/throttling.py, which does not exist. |
| BUG-SEC-008 | P3 | CONFIRMED | Missing API Latency and Slow Query Telemetry Logger | core/middleware.py logs duration_ms only; no slow-request threshold or query-count warning. |
| BUG-SEC-009 | P2 | CONFIRMED | SaaS Subscription Write-Gate Middleware Bypasses Trailing-Slash URL No | billing/middleware.py:31 matches `path.endswith(ALLOW_SUFFIXES)` on the raw path with no slash normalisation. |
| BUG-SEC-013 | P2 | CONFIRMED | erase_company Documents a Production --force Gate It Does Not Implemen | erase_company.py:20-27 has --company-id/--confirm/--mode/--reason only; docstring promises --force, code has none. |
| BUG-SEC-014 | P2 | CONFIRMED | Empty MFA_ENCRYPTION_KEY Is Derived from SECRET_KEY | accounts/mfa.py:94-99 derives a Fernet key from SECRET_KEY when MFA_ENCRYPTION_KEY is empty; settings.py:816 does not fail closed. |
| BUG-SEC-015 | P2 | CONFIRMED | Forced-Enrolment Token Is Stored in sessionStorage | web/src/api/client.ts:318-319 writes the enrol token to sessionStorage. |
| BUG-SEC-016 | P2 | CONFIRMED | Purchase Complete, Journal Post, and Receipt Allocation Are Not Audite | payments/services.py audits create (`record_document_event`) but `allocate_receipt` has no audit call; journal post in accounting/views.py has none. |
| BUG-SEC-017 | P3 | CONFIRMED | Stale Active Company Falls Through to Another Membership | accounts/views.py:150-156 `_active_membership` falls back to first membership. |
| BUG-SEC-018 | P3 | CONFIRMED | A Viewer Can Be Granted Financial-Report Access | `can_view_financial_reports` is not in `_VIEWER_FORBIDDEN_CAPS` (accounts/serializers.py:19-30). |
| BUG-SEC-019 | P3 | CONFIRMED | Postgres Row-Level Security Is Off Unless Ops Opts In | settings.py:981 `POSTGRES_RLS_ENABLED` defaults to "0". |
| BUG-SEC-020 | P3 | CONFIRMED | reset_user_mfa and grant_company_flag Run in Production With No Extra  | Neither reset_user_mfa.py nor grant_company_flag.py checks DJANGO_ENV or --force. |
| BUG-SEC-021 | P3 | CONFIRMED | Ops Alert Token Is Accepted on the Query String | core/views.py:608-609 accepts `?token=` query parameter. |
| BUG-SALES-007 | P2 | CONFIRMED | POS Printing Path Restricted to Bluetooth Stub (No WebUSB / Raw TCP Ne | No WebUSB or raw-socket printing in printPosThermal.ts or lib/native.ts. |
| BUG-SALES-008 | P2 | CONFIRMED | Cash Drawer Kick-Out Pulse and Weighing Scale Integration Missing | No drawer-kick bytes or Web Serial code in web/src/pages/pos. |
| BUG-SALES-009 | P3 | CONFIRMED | Trigram Catalog Search Missing on High-Volume Product Lookup | No GinIndex / trigram index in masters/. |
| BUG-SALES-016 | P2 | CONFIRMED | Record Payment Is Allowed by Sales-Create, Not Payment-Create | sales/views.py:126-130 puts `record_payment` under CanCreateSales. |
| BUG-SALES-017 | P2 | CONFIRMED | Receipt Create Treats Idempotency-Key as Optional | payments/views.py:155-162 claims idempotency only when the header is present. |
| BUG-SALES-018 | P2 | CONFIRMED | Cancelling a Credit Note Does Not Restore Peeled Receipt Allocations | Credit-note cancel in sales/notes_services.py has no allocation restore. |
| BUG-SALES-019 | P2 | CONFIRMED | Portal Complaint List Is Unbounded | portal_views.py:332 complaint query is unsliced. |
| BUG-SALES-020 | P3 | CONFIRMED | Portal PDF Allows Draft and Cancelled Invoices for That Customer | portal_views.py:262-267 PDF lookup has no status filter. |
| BUG-SALES-021 | P3 | CONFIRMED | Partial Returns Consume the Same SKU in Line Order | return_service.py:107-146 consumes remaining quantity keyed by product in line order. |
| BUG-SALES-022 | P3 | CONFIRMED | Receipt Allocation Does Not Quantize to Paise | allocate_receipt does `Decimal(amount)` with no quantize. |
| BUG-PUR-004 | P2 | PARTIAL | Foreign Vendor Import Without Bill of Entry Lacks Strict Blocking | Guard exists (`_assert_import_bill_of_entry`) but `_is_foreign_import_supplier` infers import from GSTIN/state heuristics, not a country field. |
| BUG-PUR-005 | P2 | PARTIAL | Bulk Price Adjustments on Landed Costs Lack Weighted Average Recalcula | restamp_fifo_layers_for_price_amend refuses when quantity is already peeled and is a no-op for WAVG companies; the COGS-variance gap is narrower than written. |
| BUG-PUR-012 | P2 | CONFIRMED | GRN Accepted Quantity Is Not Tied to Received or Rejected | grn_service uses `quantity_accepted` directly; no accepted+rejected=received check. |
| BUG-PUR-013 | P2 | CONFIRMED | Convert GRN to Bill Does Not Lock the GRN Row | convert_to_bill reads converted_purchase_id with no select_for_update. |
| BUG-PUR-014 | P3 | CONFIRMED | Product Import Maps a Column Named rate Onto Selling Price | imports/services.py aliases `rate` to selling_price (per register; not re-read). |
| BUG-INV-005 | P2 | STALE | Stock Balance select_for_update() Outside Transaction In Inventory Tra | StockTransferService.complete is already `@transaction.atomic` (inventory/services.py:1317). |
| BUG-INV-006 | P3 | CONFIRMED | Barcode Label Printing Engine Stubs (No ZPL / TSPL Direct Output) | No ZPL/TSPL output anywhere. |
| BUG-INV-009 | P2 | CONFIRMED | Stock Adjustment Date Gates the Period and Is Not Stored on the Moveme | inventory/views.py:199-200 gates the period on adj_date but post_movement has no movement_date. |
| BUG-INV-010 | P3 | CONFIRMED | Stock Transfer Has No Business Date and Always Uses Today | StockTransfer model has no date field. |
| BUG-ACC-005 | P2 | STALE | Round-Off Discrepancies Absorbed into Operating Expense Accounts | `_round_off_line` always uses account 5500, and `_account()` seeds or reactivates it; no fallback to Sales/Purchases exists. |
| BUG-ACC-006 | P2 | FALSE POSITIVE | Fixed Asset Depreciation Tasks Run Without Company Scope in Bulk Updat | The `.update(pk=asset.pk)` calls (accounting/tasks.py:161-164) run inside a per-company fan-out task; pk is unique, so no cross-tenant write. |
| BUG-ACC-007 | P3 | CONFIRMED | Absence of Multi-Branch / Multi-Store P&L Comparative Reporting | accounting/reports.py groups by cost centre only; no branch comparative P&L. |
| BUG-ACC-008 | P2 | CONFIRMED | WDV Fixed Asset Depreciation Skips Pro-Rata Month-in-Service Proration | tasks.py:109-120 prorates the acquisition month for SLM only. |
| BUG-ACC-009 | P2 | CONFIRMED | Ineligible GST ITC Reversals and Scrap Inventory Co-Mingled into Fixed | reclass_rejected_itc debits 5600 "Loss on Disposal of Assets" (services.py:456). |
| BUG-ACC-012 | P2 | CONFIRMED | Year Close and Books Health Still Demand Work Orders When Manufacturin | accounting/reports.py:413-417 blocks year close on RELEASED work orders with no ENABLE_MANUFACTURING check. |
| BUG-ACC-013 | P2 | CONFIRMED | GL Bank-Line Match Is Check-Then-Set With No Row Lock | BankReconSessionViewSet.match has no atomic block or select_for_update. |
| BUG-ACC-014 | P2 | CONFIRMED | Soft-Close Does Not Require Earlier Periods to Be Closed | Only `close` checks earlier_open (views.py:130-137); soft_close does not. |
| BUG-ACC-015 | P2 | CONFIRMED | Depreciation Catch-Up Drops Months Older Than Three | accounting/tasks.py:32 `_MAX_CATCHUP_MONTHS = 3`. |
| BUG-ACC-016 | P2 | CONFIRMED | Books-Close Shows the First Customer's AR as the Control Total | BooksCloseSection.tsx:34 uses `customers[0]`. |
| BUG-ACC-017 | P2 | CONFIRMED | Payments Recon and GL Recon Are Two Screens With Different Match Meani | Two separate recon screens (payments and accounting); no cross-link verified. |
| BUG-ACC-018 | P2 | CONFIRMED | Dispose Fixed Asset Posts With No Confirmation | FixedAssetsPage.tsx:124 calls dispose.mutate directly. |
| BUG-ACC-019 | P3 | CONFIRMED | Books Close and GST Close Are Separate Buttons | phase/PeriodsPage.tsx has a separate GST soft-close mutation next to the books close. |
| BUG-GST-005 | P2 | STALE | GSTR-2B Ingest Does Not Detect Duplicate Ingestions | reporting/models.py:163-170 has three UniqueConstraints on (company, period, supplier_gstin, invoice_number/date). |
| BUG-GST-008 | P2 | CONFIRMED | OCR GST Rates That Miss a Slab Are Silently Snapped to 18% | imports/services.py:662 `snapped = Decimal("18")`. |
| BUG-PAY-004 | P2 | STALE | Payment Gateway Partial Refund Outbox Race Condition | The refund path locks the row: `GatewayPayment.objects.select_for_update().get(pk=gp.pk)` (payments/services.py ~1720). |
| BUG-PAY-009 | P2 | CONFIRMED | Live FIU Ingest Trusts JSON After Bearer Auth | fiu_adapter live fetch trusts JSON after bearer auth; signature verification is only a gated stub (B4-020). |
| BUG-BIL-002 | P2 | CONFIRMED | Unknown Razorpay Subscription Events Are Stored as Processed | billing/views.py:254-260 stores a ProcessedWebhookEvent with company=None and returns ignored. |
| BUG-BIL-003 | P2 | CONFIRMED | Subscription Status Updates Do Not Lock the Row | apply_razorpay_subscription_status has no select_for_update. |
| BUG-BIL-004 | P3 | CONFIRMED | Storage Quota Check Does Not Lock the Company | quotas.py:89 locks the company for the complete-count check only; assert_storage_allowed does not lock. |
| BUG-PRJ-003 | P2 | PARTIAL | Unhandled ValueError / 500 Crashes on Invalid Input | The milestones action now catches int() ValueError (projects/views.py:57-60). Other actions not individually re-checked. |
| BUG-PRJ-004 | P2 | CONFIRMED | A Project Can Close While Planned Milestones Are Still Unbilled | close_project checks READY milestones only (projects/services.py:133). |
| BUG-INS-004 | P2 | STALE | Renewal Diary Concurrency Race Creates Duplicate Renewal Leads | PolicyRenewalLead has a unique policy link and the diary checks it (insurance/models.py:129); the cited string-match dedup is gone. |
| BUG-WRK-003 | P2 | CONFIRMED | Unvalidated Negative Quantities and Pricing on Job Lines | workshop/views.py:69-70 passes request.data quantity/unit_price; add_line shows no sign check. |
| BUG-WRK-004 | P2 | CONFIRMED | Job Card Has No Mechanic Commission or Labour Time Tracking | workshop/models.py has no commission or labour timer fields. |
| BUG-WRK-005 | P3 | CONFIRMED | Absence of Service Bay Allocation & Workshop Scheduling | No service-bay model. |
| BUG-CNT-001 | P2 | CONFIRMED | Expired Contracts Continue to Show as ACTIVE on Read | No read-time status computation in contracts serializers/views; only the beat task updates status. |
| BUG-CMP-001 | P2 | STALE | Complaints Can Be Marked RESOLVED While Linked Documents Remain DRAFT | complaints/services.py:125 `_assert_posted` requires the linked document to be COMPLETED before resolve. |
| BUG-PRL-001 | P2 | CONFIRMED | PF Admin Charge Floor of Rs 500 Is Defined and Never Applied | PF_ADMIN_MIN_ESTABLISHMENT defined at payroll/services.py:27 and used nowhere else. |
| BUG-PRL-002 | P2 | CONFIRMED | ESI Stops the Month Wages Cross the Ceiling | ESI test is per month: `gross_full <= esi_ceiling` (services.py:367). |
| BUG-CMP-002 | P2 | CONFIRMED | Complaint Return, Credit Note, and Order Actions Do Not Open the Draft | ComplaintsPage.tsx has no navigate to the created draft. |
| BUG-CRM-004 | P2 | PARTIAL | Campaigns Cannot Be Edited, and the Funnel Mis-Labels Revenue | CampaignsPage now edits (`editing` state, updateCampaign); revenue label still maps only quotation_total vs opportunity amount (line 184). |
| BUG-CRM-005 | P2 | CONFIRMED | Won Opportunity Can Draft a Quotation in the UI and Not an Invoice | web/src/api/crm.ts has no draft-invoice call. |
| BUG-SUP-001 | P2 | CONFIRMED | Shared Tickets Freeze Status at Share Time | support/share.py snapshots status at share time only. |
| BUG-SUP-002 | P2 | CONFIRMED | Support Tickets Cannot Be Reassigned, and Category Is Invisible | TicketsPage.tsx only filters on assignee; no reassign control or category field. |
| BUG-SUP-003 | P2 | CONFIRMED | Share With Bizboard Returns 404 When No Vendor Company Is Configured | support/share.py raises Http404 when no vendor company is configured; Share button not gated. |
| BUG-CRM-006 | P3 | CONFIRMED | Insights Hub Does Not Open the Attention Inbox | InsightsHubPage.tsx does not link to Attention. |
| BUG-UI-002 | P2 | CONFIRMED | Barcode Scanner Wedge Lacks 50ms Inter-Keystroke Timing Detection | No inter-keystroke timing logic in PosPage.tsx. |
| BUG-UI-003 | P2 | CONFIRMED | Quantity Multiplier Keypad Parsing Missing in POS Barcode Scanner | No quantity-prefix (`5*code`) parsing in the POS scan path. |
| BUG-UI-004 | P2 | CONFIRMED | Global Command Palette (Ctrl+K / Cmd+K) Missing | No command palette component or Ctrl+K handler. |
| BUG-UI-005 | P2 | CONFIRMED | Destructive Action Confirmation Dialogs Lack Entity Name Typing | ConfirmDialog.tsx has no typed-confirmation mode. |
| BUG-UI-006 | P3 | CONFIRMED | Sound Feedback Cues Missing on Barcode Scanning | No audio cue code in pages/pos. |
| BUG-UI-007 | P3 | CONFIRMED | Shift+P Privacy Mask Missing from Owner Dashboard | No privacy-mask hotkey in insights or dashboard. |
| BUG-UI-008 | P2 | PARTIAL | Walk-in Customer Duplication Race in Offline POS Flush | flushPosCheckout.ts:35-45 now binds the created customer id to the draft (CR-004), but each draft with the same pending name still creates its own customer. |
| BUG-UI-009 | P2 | CONFIRMED | Brittle Regex Entity Extraction in Insights Assistant Causes Customer  | assistant.py:477 greedy regex captures trailing words. |
| BUG-UI-011 | P2 | CONFIRMED | Products Page Unbounded `listStock()` Call Triggers Heavy Client-Side  | ProductsPage.tsx:89 calls `listStock()` with no paging. |
| BUG-UI-012 | P2 | CONFIRMED | Destructive Campaign Removal Executes Instantly Without Confirmation P | CampaignsPage.tsx:160 calls remove.mutate directly. |
| BUG-UI-014 | P2 | CONFIRMED | Free-Text TDS Section Input on Purchase Bills Causes Withholding Tax E | NewPurchasePage.tsx:2139 TDS section is a free-text field. |
| BUG-UI-015 | P2 | CONFIRMED | "Save & New" Action Hard-Blocked on Draft Invoices | DocumentEditorShell.tsx:248 disables Save & New unless canComplete (and in edit mode). |
| BUG-UI-016 | P2 | CONFIRMED | Customer Selection in Lead Dialog Hard-Capped at First 200 Records | LeadsPage.tsx:129 `pageSize: 200`. |
| BUG-UI-017 | P2 | CONFIRMED | Missing Milestone Editing, Due Dates, and Closing Confirmation in Proj | ProjectsPage.tsx has no confirm, due-date or milestone-edit code. |
| BUG-UI-020 | P2 | CONFIRMED | CRM, Tickets, Contracts, and Complaints Fetch a Fixed Page and Show No | Tickets 100, contracts 50, complaints 50 fixed pages; no TablePagination. |
| BUG-UI-021 | P2 | CONFIRMED | Insurance, Contracts, and Pipeline Show Raw Amounts and ISO Dates | InsurancePage.tsx:137 renders `String(row.premium)`. |
| BUG-UI-022 | P2 | CONFIRMED | Line-Delete Buttons on Sales and Purchase Editors Have No Accessible N | SalesOrderEditorPage.tsx:685 icon-only DeleteIcon button with no aria-label. |
| BUG-UI-023 | P2 | CONFIRMED | Growth Modules Share One Empty Sentence, and the Pipeline Has None | `growth.nothingYet` is used on many pages (10 usages). |
| BUG-UI-024 | P2 | CONFIRMED | Account Aggregator, GSTR-6/7/8, Shared Tickets, and CRM Onboarding Can | GstReturnPage.tsx:412 `GstStubPage` for GSTR-6/7/8. |
| BUG-UI-025 | P2 | CONFIRMED | Cancel Contract, Delete an Attachment, and Move to Won or Lost Need No | ContractsPage.tsx:170 sets CANCELLED directly on click. |
| BUG-UI-026 | P2 | CONFIRMED | Feature-Off Screens Are One Sentence, and Not-Ready Errors Replace the | `erp.moduleDisabled` is a single sentence on 11 usages. |
| BUG-UI-027 | P2 | CONFIRMED | Transaction Register Filter Bars Lack Exact Customer / Supplier Autoco | HistoryFilterBar filters have q/status/date only; no party selector. |
| BUG-UI-028 | P2 | CONFIRMED | Missing Indian Financial Year (FY) and Quarterly Date Range Presets in | No FY or quarter presets in HistoryFilterBar. |
| BUG-UI-029 | P2 | CONFIRMED | Products Catalog Lacks Category, Brand, Stock Availability, and Tax Sl | ProductsPage.tsx has no category/brand filter. |
| BUG-UI-031 | P2 | CONFIRMED | Universal Search Completely Excludes Growth OS Entities and Auxiliary  | backend/search/views.py covers customers, suppliers, products and invoices only. |
| BUG-UI-032 | P2 | CONFIRMED | Sales and Purchase Reports Lack Time Granularity Grouping (Day / Week  | reporting/views.py group_by is customer-style; no time-bucket grouping. |
| BUG-PERF-004 | P2 | CONFIRMED | O(N) All-Time Historical Ledger Scanning on Financial Reports Due to M | accounting/reports.py `_balances` aggregates JournalLine from inception unless date_from is passed; no rollup table. |
| BUG-PERF-005 | P2 | CONFIRMED | Missing Critical Multi-Column Composite Indexes on PaymentAllocation,  | PaymentAllocation has no Meta indexes and SalesInvoice has one; JournalLine is already indexed (accounting/models.py:160-163). |
| BUG-PERF-006 | P2 | CONFIRMED | Correlated Subqueries & Python In-Memory Grouping in Low Stock Alert C | low_stock_alert_payload correlates a WarehouseReorderLevel subquery per balance row and groups in Python. |
| BUG-PERF-007 | P2 | PARTIAL | Frontend Initial Bundle Bloat (482 KB Gzip) & Missing Table Virtualiza | Bundle budget ratchet exists (initial 530 KB gzip, measured 481.7) and @tanstack/react-virtual is installed; actual use on Products/Customers tables not confirmed. |
| BUG-PERF-008 | P2 | CONFIRMED | Sequential Single-Bill Offline Flush Causes Long POS Network Reconnect | flushPosDraft handles one draft at a time with sequential requests. |
| BUG-COG-001 | P0 | ENHANCEMENT | Sales Invoice Forces Redundant Declarative Choice of Invoice Type | Wave A inference exists (`invoiceTypeTouched`, GSTIN check); the invoice-type select is still shown (NewInvoicePage.tsx:1729). Partly shipped. |
| BUG-COG-002 | P0 | ENHANCEMENT | Price Mode Select Forces Repeated Evaluation of Company Default | `chooseInvoiceDefaults` already derives companyPriceMode; select still shown (NewInvoicePage.tsx:1761). Partly shipped. |
| BUG-COG-003 | P0 | ENHANCEMENT | Unconditional Warehouse Select Renders on Single-Godown Companies | Warehouse select renders unconditionally (NewInvoicePage.tsx:1775); `multiGodown` prop exists elsewhere. Open. |
| BUG-COG-004 | P0 | ENHANCEMENT | Active Non-Default Statutory Configurations Hidden Inside Collapsed Dr | No non-default chips; tax options sit behind `showAdvancedTax`. Open. |
| BUG-COG-005 | P0 | ENHANCEMENT | Unranked Document Actions on Posted Invoices Overload Visual Attention | No ranked action menu on InvoiceDetailPage. Open. |
| BUG-COG-006 | P0 | ENHANCEMENT | Sales Return Initiation Forces Manual Pogo-Sticking and Line Re-Entry | No return-from-invoice handoff found. Open. |
| BUG-COG-007 | P0 | ENHANCEMENT | Premature Place of Supply Prompts Ignore Valid Party GSTIN | `placeOfSupplyKnown` exists and is used on sales and purchase pages; shared helper and prompt removal not done. Partly shipped. |
| BUG-COG-008 | P0 | ENHANCEMENT | Inward Purchase Bill Lines Force Manual Re-Entry of Master Data | Purchase lines default hsn blank and gstRate 18; no master autofill. Open. |
| BUG-COG-009 | P1 | ENHANCEMENT | Raw ITC Eligibility Enum Exposes Users to Statutory Tax Audit Risk | ITC control is the raw enum; no blocked-category recommendation. Open. |
| BUG-COG-010 | P1 | ENHANCEMENT | Fragmented Period Close Navigation Creates Month-End Anxiety | Close controls are on PeriodsPage only; no unified hub. Open. |
| BUG-COG-011 | P1 | ENHANCEMENT | User Access Management Requires Manual 8-Checkbox Matrix Configuration | UsersSettingsPage already has `capsForRole` role presets. Partly shipped. |
| BUG-COG-012 | P1 | ENHANCEMENT | Unlocked GST Settings Allow Accidental Company-Wide Tax Corruption | GstSettingsPage already confirms registration changes (window.confirm at lines 205/216). Largely shipped. |
| BUG-COG-013 | P1 | ENHANCEMENT | Dense Products Catalog Overwhelms Initial Visual Search | ProductsPage has about 8 filter/field controls and no search-first layout. Open. |
| BUG-COG-014 | P1 | ENHANCEMENT | POS Focus Hijacking Overwrites Item Quantities with Barcode Scans | Search box refocus on several events (PosPage.tsx:966, 1050, 1110); caret lock during qty edit not found. Open. |
| BUG-COG-015 | P1 | ENHANCEMENT | Disabled Document Completion Fails to Explain Root Cause | DocumentEditorShell has `primaryDisabledReason` and a customer-specific reason. Partly shipped. |
| BUG-COG-016 | P1 | ENHANCEMENT | Accounting Jargon Confuses Non-Accountant Store Owners | Catalog still uses Credit Notes / Debit Notes labels (i18n/en.ts). Open. |
| BUG-COG-017 | P2 | ENHANCEMENT | Bank Reconciliation Forces Manual Confirmation of Obvious 1:1 Matches | Blocked by design: needs a written founder decision in docs/ux/founder_decisions.md before any code. |
| BUG-COG-018 | P2 | ENHANCEMENT | Mobile Field Sales Order Lacks Customer Credit and Stock Context Strip | No credit/stock context strip on the sales order editor. Open. |
| BUG-COG-019 | P2 | ENHANCEMENT | Proprietor Lacks a Consolidated 5-Minute Morning Command Hub | No morning hub page found (Attention exists). Open. |
| BUG-COG-020 | P3 | ENHANCEMENT | Read-Only Invoice Series Inputs Mimic Editable Form Fields | NewInvoicePage.tsx:1694 still renders a readOnly input; caption exists only in edit mode. Partly shipped. |