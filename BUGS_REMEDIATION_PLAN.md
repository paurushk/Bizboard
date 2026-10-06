# Remediation plan for the BizBoard defect register

**Date**: 2026-10-04
**Source**: [BUGS_LIST.md](BUGS_LIST.md) version 2.2
**Scope**: 212 findings in the register. Triage on 2026-10-04 covered every P0/P1, P2/P3 and COG item. It closed 19 (already fixed or false positive) and reclassified 1, leaving 193 open: P0 19, P1 75, P2 78, P3 21. See [BUGS_TRIAGE_2026-10-04.md](BUGS_TRIAGE_2026-10-04.md).
**Status**: plan revised after triage; no fix is implemented. 19 findings were closed at triage (no change needed); no other finding is closed.

The register used `BUG-PAY-001` and `BUG-PAY-002` twice. Triage on 2026-10-04 renamed the payroll pair: `BUG-PRL-003` is the cash-default disbursement and `BUG-PRL-004` is advances, arrears, and bonus lines. `BUG-PAY-001` (cheque bounce) and `BUG-PAY-002` (Account Aggregator consent expiry) keep their payments meaning.

Cognitive rows `BUG-COG-001` through `BUG-COG-020` were expanded on 4 Oct 2026. They are the same IDs. This plan does not create new ones.

## Changes made at triage (2026-10-04)

This plan was revised after every finding was checked against the code. The revisions are:

- **Closed, no production change** (19): the work package keeps its original failure text for history, says "Change. None", and its Done when is a regression guard only. They are BUG-SEC-001, SEC-002, SEC-003, SEC-007, SALES-005, ACC-002, ACC-005, ACC-006, INV-005, GST-005, PAY-004, PRJ-001, INS-001, INS-002, INS-003, INS-004, INS-005, CMP-001, UI-001.
- **Narrowed** (17 partial findings): the Change and Done when now cover only the gap that remains. They are BUG-SEC-004, SEC-005, SEC-006, INV-003, GST-002, PAY-002, PAY-006, MFG-001, CRM-001, UI-030, ACC-003, PUR-004, PUR-005, PRJ-003, CRM-004, UI-008, PERF-007.
- **Reclassified**: BUG-PUR-001 is P2 feature work, scheduled after the GRN fixes.
- **Shared mechanisms and decisions**: the tenant beat loop and the trial-balance check already exist, so later findings reuse them and no wave builds them.
- **COG packages** (BUG-COG-001 to 020) start from what is already shipped: invoice-type and price-mode inference, `placeOfSupplyKnown`, role presets, the GST registration confirm, and the disabled-reason hook. Each triage note says what is left.
- **File paths**: eleven paths that did not exist were corrected to the real files.

---

## 1. How to execute

Work the waves in order. Wave 1 merges before wave 2 starts. Inside a wave, follow the numbered order when two items touch the same file. Items that name different files and have no "Ships with" line can move in parallel.

One pull request per finding. The exceptions are the pairs named in "Ships with". A pull request title starts with the finding ID.

Each pull request:

1. Implements the Change section and nothing adjacent.
2. Adds the named regression test.
3. Quotes the Done when paragraph in the pull request body.
4. Runs the wave exit command plus the neighbor tests already covering that module.

### Rules that apply to every change

1. `PostingService` remains the only writer of stock movements, tax rows, and journals. A screen prefills. It does not post a second way.
2. A money write is one database transaction. Amounts quantize to `0.01` with `ROUND_HALF_UP` at the service boundary. A retry with the same `Idempotency-Key` returns the original row.
3. A cancel reverses the effects of the matching complete, in that same transaction, or the service refuses the cancel. It does not leave stock, a live bill, and a journal in three different states.
4. Check-then-set on a money or stock row takes `select_for_update` inside `transaction.atomic`, then re-reads, then writes.
5. A beat task with no company argument loads active companies with `core.rls.iter_company_ids()` and runs the body after `set_rls_company(cid)`. Company B's rows stay unchanged in a two-company test.
6. An audit event for a money mutation is written in the same transaction as the mutation. A failed audit rolls the money change back.
7. List endpoints accept `page` and `page_size`. `page_size` above 250 is clamped. Exports stream. They do not build the full table in worker memory.
8. Cognitive and copy changes keep today's payload enums, tax maths, stock rules, ITC posting, ledger derivation, and permission helpers. A hidden control posts the default the server already uses. A non-default value stays visible as a chip. English and Hindi land together.
9. `BUG-COG-017` is the exception to rule 8. It posts a match. It waits for a written founder decision. There is no undo of a posted match.
10. Do not enable a feature flag to make a bug reachable. Fix the path the flag already exposes.
11. Books-off behavior stays: `PostingService.post` returns without a journal when accounting is off. Do not call `reverse` in that state. The audit row for the document still writes.
12. Destructive commands (`erase_company`, `reset_user_mfa`, `grant_company_flag`) refuse production and staging unless `--force` is passed, and they write an audit row.

### Shared mechanisms

Build each mechanism once. Later findings call it.

| Mechanism | Build in | Later findings use it |
| --- | --- | --- |
| Tenant beat loop | Already built: `core.rls.iter_company_ids` with `set_rls_company` (BUG-SEC-001 closed) | Depreciation, reservation expiry, trial-balance check, contract refresh, recurring invoices |
| Password re-auth before MFA enrolment | BUG-SEC-010 | BUG-SEC-004 requires enrolment only after this exists |
| Idempotent paise money write | BUG-SALES-022, BUG-SALES-017, BUG-SALES-012 | Settlement discount, short-collect, credit-note cancel, cheque dishonour |
| Document audit in the money transaction | BUG-SEC-016 | Master-data audit in BUG-ACC-003 extends the same chain |
| GRN line identity and lot capture | BUG-PUR-012, BUG-PUR-008 | Cancel pair BUG-PUR-006 and BUG-PUR-007, returns BUG-PUR-009, the GRN screen BUG-PUR-011 |
| Invoice inference | BUG-COG-001, BUG-COG-002, BUG-COG-007 | Chips, ranked actions, and return prefill sit on top |
| One confirm dialog | BUG-UI-005 | Cart clear, campaign delete, won/lost, contract cancel, asset dispose |
| GrowthFilterBar plus pager | BUG-COG-G05 | Tickets, contracts, complaints, opportunities, pipeline |
| Handoff prefill | BUG-COG-006 | Complaint credit note, lead quotation, contract renewal, referral settlement |

### Decisions this plan makes

1. **GRN gets a screen** (BUG-PUR-011). The API is live and batch goods cannot be received without a place to type the lot. Help text describes that screen. Refusing the API in production is the fallback only if the screen slips past the cancel-pair fix. The cancel-pair fix (BUG-PUR-006, BUG-PUR-007) does not wait for the screen.
2. **Below-cost sales** (BUG-SALES-006) block complete unless an owner or admin records an override on the document (user, reason, time) in the audit chain. Use the credit-limit override shape if it already exists. Do not add a separate cryptographic token scheme.
3. **Trial-balance check** (BUG-ACC-002, closed): the `core-nightly-invariants` beat already runs `gl.trial_balance_zero`. Any follow-up only adds an alert or a books-health block on failure. It does not rewrite journals and does not freeze the company silently.
4. **RLS in production** (BUG-SEC-019) becomes mandatory after the beat-task tenant loop has soaked. Until that soak, application filters remain the isolation control, and startup logs a warning. After the soak, production startup fails when RLS is off.
5. **Unique bank auto-match** (BUG-COG-017) does not start until `docs/ux/founder_decisions.md` contains the decision. Cross-linking the two recon screens (BUG-ACC-017) ships without auto-post.
6. **Hiding invoice selects** (the Wave C half of BUG-COG-001, BUG-COG-002, BUG-COG-003, and the production hide in BUG-COG-004) waits for pilot session GD-33. Wave A, which infers values and leaves the select visible, ships as soon as wave 2 is green.
7. **Section 138 notice** (BUG-PAY-001) generates a stored PDF from the bounced cheque, the party, the amount, and the date. It does not file anything with a court. The fee debit note uses the company's configured dishonour charge, defaulting to the bank charge on the bounce record when that charge is present.

### Wave exit checks

| Wave | Exit |
| --- | --- |
| 1 | `python -m pytest backend/tests/tenancy/test_endpoint_isolation.py backend/tests/test_mfa.py backend/tests/errors/test_webhook_and_async_contracts.py` |
| 2 | `python -m pytest backend/tests/test_double_submit_money_paths.py backend/tests/test_idempotency_fingerprint.py backend/tests/test_audit_append_only.py` |
| 3 | `python -m pytest backend/tests/test_concurrency_races.py backend/tests/workflows/test_wf_todo_stubs.py` plus a new GRN cancel/bill cancel pair test |
| 4 | `python backend/manage.py check_invariants` and `python -m pytest backend/tests/test_series_gstin_health.py` |
| 5 | `python -m pytest backend/tests/test_growth_os.py backend/tests/personas/test_pj_crm_quote_to_order.py` |
| 6 | `python -m pytest backend/tests/test_wave22_f3_billing_idempotency.py` |
| 7 | `python -m pytest backend/tests/test_sales_invoice_serializer_queries.py backend/tests/test_qos0016_dashboard_budget.py` and `npm --prefix web run budget` |
| 8 | `npm --prefix web test web/src/pages/sales/invoiceDefaults.test.ts web/src/i18n/fullParity.test.ts` |
| 9 | `npx playwright test pos-keyboard-checkout` |
| 10 | The seven residual tests in `backend/tests/test_bug_register.py` for this wave |

Every wave also runs `python -m pytest backend/tests/test_bug_register.py -k wave{n}` once those tests exist. `backend/tests/test_bug_register.py` does not exist yet: the first pull request of wave 1 creates it as an empty module and registers the `bug_wave1` to `bug_wave10` markers in the pytest config. Tag each new test with a pytest marker `bug_wave{n}`.

---

## 2. Wave map

### Wave 1. Fail closed

Tenant context, webhook authentication, MFA, erasure, and destructive commands.

13 findings, 10 open after triage, 3 closed: P0 0, P1 5, P2 3, P3 2 (open).

| # | ID | Sev | Finding |
| ---: | --- | --- | --- |
| 1 | [BUG-SEC-003](#bug-sec-003) | P0, closed (false positive) | Potential Raw SQL Execution Bypassing Tenant RLS |
| 2 | [BUG-SEC-001](#bug-sec-001) | P0, closed (already fixed) | Background Celery Tasks Execute Multi-Tenant Scans Without Setting RLS Context |
| 3 | [BUG-SEC-002](#bug-sec-002) | P0, closed (already fixed) | Razorpay Webhook Authentication Bypass in Test / Staging Environments |
| 4 | [BUG-SEC-014](#bug-sec-014) | P2 | Empty MFA_ENCRYPTION_KEY Is Derived from SECRET_KEY |
| 5 | [BUG-SEC-015](#bug-sec-015) | P2 | Forced-Enrolment Token Is Stored in sessionStorage |
| 6 | [BUG-SEC-011](#bug-sec-011) | P1 | Password Login Mints a Refresh Token Before the MFA Challenge |
| 7 | [BUG-SEC-010](#bug-sec-010) | P1 | MFA Setup and Confirm Do Not Ask for the Password |
| 8 | [BUG-SEC-004](#bug-sec-004) | P1 | Two-Factor Authentication (TOTP) Completely Opt-In for Privileged Roles |
| 9 | [BUG-SEC-012](#bug-sec-012) | P1 | Customer Portal Phone Lookup Loads Every Tenant's Phones |
| 10 | [BUG-SEC-006](#bug-sec-006) | P1 | Tenant Right-to-Erasure (DPDP Act) Fails on Vertical App Foreign Keys |
| 11 | [BUG-SEC-013](#bug-sec-013) | P2 | erase_company Documents a Production --force Gate It Does Not Implement |
| 12 | [BUG-SEC-020](#bug-sec-020) | P3 | reset_user_mfa and grant_company_flag Run in Production With No Extra Confirm |
| 13 | [BUG-SEC-021](#bug-sec-021) | P3 | Ops Alert Token Is Accepted on the Query String |

### Wave 2. Money writes

Atomic, idempotent, paise-quantized postings, row locks, and audit of those writes.

16 findings, 12 open after triage, 4 closed: P0 0, P1 3, P2 7, P3 2 (open).

| # | ID | Sev | Finding |
| ---: | --- | --- | --- |
| 1 | [BUG-SALES-022](#bug-sales-022) | P3 | Receipt Allocation Does Not Quantize to Paise |
| 2 | [BUG-SALES-017](#bug-sales-017) | P2 | Receipt Create Treats Idempotency-Key as Optional |
| 3 | [BUG-SALES-012](#bug-sales-012) | P1 | Record Payment Creates the Receipt and the Allocation as Two Steps |
| 4 | [BUG-SALES-015](#bug-sales-015) | P1 | Non-Atomic POS Short-Collect Still Receipts the Full Bill |
| 5 | [BUG-SALES-013](#bug-sales-013) | P1 | Settlement Discount Clears the Customer Subledger and Is Never Posted |
| 6 | [BUG-SALES-018](#bug-sales-018) | P2 | Cancelling a Credit Note Does Not Restore Peeled Receipt Allocations |
| 7 | [BUG-SALES-016](#bug-sales-016) | P2 | Record Payment Is Allowed by Sales-Create, Not Payment-Create |
| 8 | [BUG-SALES-005](#bug-sales-005) | P1, closed (already fixed) | Line Item Edits on Invoices Lack Transactional Atomicity |
| 9 | [BUG-SEC-016](#bug-sec-016) | P2 | Purchase Complete, Journal Post, and Receipt Allocation Are Not Audited |
| 10 | [BUG-PUR-013](#bug-pur-013) | P2 | Convert GRN to Bill Does Not Lock the GRN Row |
| 11 | [BUG-ACC-013](#bug-acc-013) | P2 | GL Bank-Line Match Is Check-Then-Set With No Row Lock |
| 12 | [BUG-BIL-003](#bug-bil-003) | P2 | Subscription Status Updates Do Not Lock the Row |
| 13 | [BUG-BIL-004](#bug-bil-004) | P3 | Storage Quota Check Does Not Lock the Company |
| 14 | [BUG-INV-005](#bug-inv-005) | P2, closed (already fixed) | Stock Balance select_for_update() Outside Transaction In Inventory Transfer |
| 15 | [BUG-PAY-004](#bug-pay-004) | P2, closed (already fixed) | Payment Gateway Partial Refund Outbox Race Condition |
| 16 | [BUG-INS-004](#bug-ins-004) | P2, closed (already fixed) | Renewal Diary Concurrency Race Creates Duplicate Renewal Leads |

### Wave 3. Stock and document lifecycle

Cancels reverse the matching complete. Transfers, POS, GRN, job cards, milestones, and policies keep one story.

23 findings, 21 open after triage, 2 closed: P0 5, P1 12, P2 3, P3 1 (open).

| # | ID | Sev | Finding |
| ---: | --- | --- | --- |
| 1 | [BUG-PUR-012](#bug-pur-012) | P2 | GRN Accepted Quantity Is Not Tied to Received or Rejected |
| 2 | [BUG-PUR-008](#bug-pur-008) | P1 | GRN Complete Cannot Receive Batch or Serial Goods |
| 3 | [BUG-PUR-006](#bug-pur-006) | P0 | Cancelling a GRN Reverses Stock While the Converted Bill Stays Live |
| 4 | [BUG-PUR-007](#bug-pur-007) | P0 | Cancelling a GRN-Sourced Bill Does Not Reverse GRN Stock |
| 5 | [BUG-PUR-009](#bug-pur-009) | P1 | Purchase Returns Ignore GRN Cost Layers |
| 6 | [BUG-INV-001](#bug-inv-001) | P0 | Inter-Godown Stock Transfers Lack "IN_TRANSIT" State |
| 7 | [BUG-INV-010](#bug-inv-010) | P3 | Stock Transfer Has No Business Date and Always Uses Today |
| 8 | [BUG-INV-009](#bug-inv-009) | P2 | Stock Adjustment Date Gates the Period and Is Not Stored on the Movement |
| 9 | [BUG-INV-002](#bug-inv-002) | P1 | Zombie Stock Reservations Locking Usable Inventory |
| 10 | [BUG-SALES-002](#bug-sales-002) | P1 | Inward Goods Rejection Leaves Stock Reserved Indefinitely |
| 11 | [BUG-SALES-001](#bug-sales-001) | P0 | Sales Orders Do Not Support Partial Conversion (Backorder Lockout) |
| 12 | [BUG-SALES-010](#bug-sales-010) | P1 | Atomic POS Checkout Drops the Batch, and UPI Drops Header Discount and Charges |
| 13 | [BUG-SALES-011](#bug-sales-011) | P1 | Atomic POS Never Sends the Blank Place-of-Supply Confirmation |
| 14 | [BUG-UI-008](#bug-ui-008) | P2 | Walk-in Customer Duplication Race in Offline POS Flush |
| 15 | [BUG-UI-010](#bug-ui-010) | P1 | Instant Cart Destruction on Unconfirmed F10 Shortcut & Clear Cart Button |
| 16 | [BUG-INV-004](#bug-inv-004) | P1 | FEFO Picking Logic Bypassed on Manual POS & Billing Lines |
| 17 | [BUG-INV-008](#bug-inv-008) | P1 | Shopify Has No Connection Setup for Godown, Customer, Domain, or Secret |
| 18 | [BUG-INV-007](#bug-inv-007) | P1 | Shopify Multi-Channel Stock Desync Caused by 25% Discrepancy Tolerance Freeze |
| 19 | [BUG-WRK-002](#bug-wrk-002) | P1 | Workshop Parts Issuance Does Not Reserve Stock During Repair |
| 20 | [BUG-WRK-001](#bug-wrk-001) | P1 | Job Card Parts Invoicing Bypasses Batch-Tracking Validation |
| 21 | [BUG-WRK-006](#bug-wrk-006) | P0 | Job Card Invoice Cannot Succeed From the Screen |
| 22 | [BUG-PRJ-001](#bug-prj-001) | P0, closed (already fixed) | Milestone Invoiced Against Draft Invoice Without Revenue Posting |
| 23 | [BUG-INS-001](#bug-ins-001) | P0, closed (already fixed) | Selecting Multiple Options Issues Duplicate Overlapping Policies |

### Wave 4. GST, books, and collections

Statutory match keys, ITC, e-way, the till, the trial balance, and cash that must hit the ledger.

50 findings, 46 open after triage, 4 closed: P0 4, P1 24, P2 15, P3 3 (open).

| # | ID | Sev | Finding |
| ---: | --- | --- | --- |
| 1 | [BUG-GST-007](#bug-gst-007) | P0 | GSTR-2B and IMS Match the Internal Purchase Number, Not the Supplier Bill Number |
| 2 | [BUG-GST-005](#bug-gst-005) | P2, closed (already fixed) | GSTR-2B Ingest Does Not Detect Duplicate Ingestions |
| 3 | [BUG-PUR-010](#bug-pur-010) | P1 | New Purchase Bills Default ITC to CLAIMABLE and Hide UNREVIEWED |
| 4 | [BUG-GST-003](#bug-gst-003) | P1 | Section 16(2) Statutory 4-Condition Checklist Absent on Purchase Bills |
| 5 | [BUG-GST-002](#bug-gst-002) | P1 | Section 16(4) Time-Barred ITC Warning Not Enforced as a Strict Exclusion |
| 6 | [BUG-GST-008](#bug-gst-008) | P2 | OCR GST Rates That Miss a Slab Are Silently Snapped to 18% |
| 7 | [BUG-GST-001](#bug-gst-001) | P0 | E-Way Bill Vehicle Update (Part B) and Validity Extension Endpoints Missing |
| 8 | [BUG-GST-006](#bug-gst-006) | P1 | E-Way Bill Generation Completely Broken for Export Consignments Due to 6-Digit Buyer PIN Enforcement |
| 9 | [BUG-GST-004](#bug-gst-004) | P1 | Section 206AB / 206CCA Higher TDS/TCS Compliance Check Missing |
| 10 | [BUG-UI-014](#bug-ui-014) | P2 | Free-Text TDS Section Input on Purchase Bills Causes Withholding Tax Errors |
| 11 | [BUG-PUR-001](#bug-pur-001) | P2 (was P1) | Absence of Strict Line-Level 3-Way Matching Tolerances |
| 12 | [BUG-PUR-002](#bug-pur-002) | P1 | GRN Inspection Rejections Do Not Generate Supplier Debit Notes |
| 13 | [BUG-PUR-003](#bug-pur-003) | P1 | Purchase Bill Amendments Mutate Records Without Version Snapshotting |
| 14 | [BUG-PUR-004](#bug-pur-004) | P2 | Foreign Vendor Import Without Bill of Entry Lacks Strict Blocking |
| 15 | [BUG-PUR-005](#bug-pur-005) | P2 | Bulk Price Adjustments on Landed Costs Lack Weighted Average Recalculation |
| 16 | [BUG-PUR-011](#bug-pur-011) | P1 | Help Says There Is No GRN While the GRN API Is Live and Has No Screen |
| 17 | [BUG-PUR-014](#bug-pur-014) | P3 | Product Import Maps a Column Named rate Onto Selling Price |
| 18 | [BUG-PUR-015](#bug-pur-015) | P1 | Purchase Invoice Free-Text Search (q) Disregards Supplier Name and Phone |
| 19 | [BUG-ACC-001](#bug-acc-001) | P0 | Absence of Daily POS Shift Close & Cash Drawer Register |
| 20 | [BUG-ACC-002](#bug-acc-002) | P0, closed (already fixed) | Unscheduled Trial Balance Zero-Sum Verification Worker |
| 21 | [BUG-ACC-010](#bug-acc-010) | P1 | Owner Backfill Turns Books On and Skips Payroll, Work Orders, and Bills of Entry |
| 22 | [BUG-ACC-006](#bug-acc-006) | P2, closed (false positive) | Fixed Asset Depreciation Tasks Run Without Company Scope in Bulk Updates |
| 23 | [BUG-ACC-008](#bug-acc-008) | P2 | WDV Fixed Asset Depreciation Skips Pro-Rata Month-in-Service Proration |
| 24 | [BUG-ACC-015](#bug-acc-015) | P2 | Depreciation Catch-Up Drops Months Older Than Three |
| 25 | [BUG-ACC-005](#bug-acc-005) | P2, closed (already fixed) | Round-Off Discrepancies Absorbed into Operating Expense Accounts |
| 26 | [BUG-ACC-009](#bug-acc-009) | P2 | Ineligible GST ITC Reversals and Scrap Inventory Co-Mingled into Fixed Asset Disposal P&L (Account 5600) |
| 27 | [BUG-ACC-003](#bug-acc-003) | P1 | Incomplete MCA Rule 11(g) Audit Trail Event Coverage |
| 28 | [BUG-ACC-004](#bug-acc-004) | P1 | Missing Formal MCA Schedule III Taxonomy Groupings |
| 29 | [BUG-ACC-011](#bug-acc-011) | P1 | GL Recon Offers Match Anyway, and the UI Compares Absolute Amounts |
| 30 | [BUG-ACC-014](#bug-acc-014) | P2 | Soft-Close Does Not Require Earlier Periods to Be Closed |
| 31 | [BUG-ACC-016](#bug-acc-016) | P2 | Books-Close Shows the First Customer's AR as the Control Total |
| 32 | [BUG-ACC-012](#bug-acc-012) | P2 | Year Close and Books Health Still Demand Work Orders When Manufacturing Is Off |
| 33 | [BUG-ACC-017](#bug-acc-017) | P2 | Payments Recon and GL Recon Are Two Screens With Different Match Meanings |
| 34 | [BUG-ACC-018](#bug-acc-018) | P2 | Dispose Fixed Asset Posts With No Confirmation |
| 35 | [BUG-SALES-014](#bug-sales-014) | P1 | Sales History Paid / Partial / Unpaid Ignores Reversed Receipts and Credit Notes |
| 36 | [BUG-SALES-003](#bug-sales-003) | P1 | Driver COD & UPI Route Collections Unreconciled Against Cashier Drawer |
| 37 | [BUG-SALES-004](#bug-sales-004) | P1 | Insecure Proof of Delivery (POD) Accepts Unverified Arbitrary OTPs |
| 38 | [BUG-SALES-006](#bug-sales-006) | P1 | Sales Margin Guard Warning Fails to Block Below-Cost Selling |
| 39 | [BUG-SALES-019](#bug-sales-019) | P2 | Portal Complaint List Is Unbounded |
| 40 | [BUG-SALES-020](#bug-sales-020) | P3 | Portal PDF Allows Draft and Cancelled Invoices for That Customer |
| 41 | [BUG-SALES-021](#bug-sales-021) | P3 | Partial Returns Consume the Same SKU in Line Order |
| 42 | [BUG-PAY-001](#bug-pay-001) | P0 | Cheque Bounce Fails to Levy Dishonour Fees or Generate Section 138 Notice |
| 43 | [BUG-PAY-006](#bug-pay-006) | P1 | Ambiguous Fuzzy Substring UTR Matching Silently Binds Unrelated Customer Receipts |
| 44 | [BUG-PAY-007](#bug-pay-007) | P1 | Account Aggregator Can Attach Two Bank Rows to One Receipt |
| 45 | [BUG-PAY-008](#bug-pay-008) | P1 | Re-Ingesting Bank Rows Overwrites Amounts That Are Already Matched |
| 46 | [BUG-PAY-005](#bug-pay-005) | P1 | Account Aggregator (AA) Auto-Reconciliation Completely Ignores Debit Transactions |
| 47 | [BUG-PAY-002](#bug-pay-002) | P1 | Account Aggregator (AA) Consent Expiration Not Handled Gracefully |
| 48 | [BUG-PAY-003](#bug-pay-003) | P1 | Bank Reconciliation Auto-Matching Engine Missing Fuzzy Narration Rules |
| 49 | [BUG-PAY-009](#bug-pay-009) | P2 | Live FIU Ingest Trusts JSON After Bearer Auth |
| 50 | [BUG-INV-003](#bug-inv-003) | P1 | Blind Stocktake & Physical Cycle Counting Sessions Absent |

### Wave 5. Vertical modules

Projects, insurance, workshop, manufacturing, payroll, contracts, complaints, CRM, and support.

32 findings, 27 open after triage, 5 closed: P0 0, P1 10, P2 15, P3 2 (open).

| # | ID | Sev | Finding |
| ---: | --- | --- | --- |
| 1 | [BUG-PRJ-002](#bug-prj-002) | P1 | Frontend Milestone Invoicing Opens a Route That Does Not Exist |
| 2 | [BUG-PRJ-004](#bug-prj-004) | P2 | A Project Can Close While Planned Milestones Are Still Unbilled |
| 3 | [BUG-PRJ-003](#bug-prj-003) | P2 | Unhandled ValueError / 500 Crashes on Invalid Input |
| 4 | [BUG-UI-001](#bug-ui-001) | P1, closed (already fixed) | Form State Leaks Across Multiple Projects in UI |
| 5 | [BUG-UI-017](#bug-ui-017) | P2 | Missing Milestone Editing, Due Dates, and Closing Confirmation in Projects |
| 6 | [BUG-INS-002](#bug-ins-002) | P1, closed (already fixed) | 30-Day Month Formula Corrupts Policy Expiration Dates |
| 7 | [BUG-INS-003](#bug-ins-003) | P1, closed (already fixed) | Unvalidated Negative Insurance Commission Receivables |
| 8 | [BUG-INS-005](#bug-ins-005) | P1, closed (already fixed) | Insurance Can Issue a Policy and Cannot Run Claims, Renewals, or Commission Receipt |
| 9 | [BUG-WRK-003](#bug-wrk-003) | P2 | Unvalidated Negative Quantities and Pricing on Job Lines |
| 10 | [BUG-WRK-004](#bug-wrk-004) | P2 | Job Card Has No Mechanic Commission or Labour Time Tracking |
| 11 | [BUG-WRK-005](#bug-wrk-005) | P3 | Absence of Service Bay Allocation & Workshop Scheduling |
| 12 | [BUG-UI-013](#bug-ui-013) | P1 | Workshop Job Cards Module Lacks Real-World Work Order Attributes |
| 13 | [BUG-MFG-006](#bug-mfg-006) | P1 | Multi-Level BOM Explosion Infinite Recursion (Lack of Cyclic Dependency Validation) |
| 14 | [BUG-MFG-001](#bug-mfg-001) | P1 | Component Issuance Skips General Ledger Work-in-Progress (WIP) Account |
| 15 | [BUG-PRL-003](#bug-prl-003) | P1 | Payroll Disbursement Defaults to Cash Without Bank Account Selection |
| 16 | [BUG-PRL-004](#bug-prl-004) | P1 | Payroll Engine Cannot Process Advances, Arrears, or Bonus Lines |
| 17 | [BUG-PRL-001](#bug-prl-001) | P2 | PF Admin Charge Floor of Rs 500 Is Defined and Never Applied |
| 18 | [BUG-PRL-002](#bug-prl-002) | P2 | ESI Stops the Month Wages Cross the Ceiling |
| 19 | [BUG-CNT-001](#bug-cnt-001) | P2 | Expired Contracts Continue to Show as ACTIVE on Read |
| 20 | [BUG-CNT-002](#bug-cnt-002) | P1 | Contracts Never Create a Recurring Invoice From the Screen |
| 21 | [BUG-CMP-001](#bug-cmp-001) | P2, closed (already fixed) | Complaints Can Be Marked RESOLVED While Linked Documents Remain DRAFT |
| 22 | [BUG-CMP-002](#bug-cmp-002) | P2 | Complaint Return, Credit Note, and Order Actions Do Not Open the Draft |
| 23 | [BUG-CRM-003](#bug-crm-003) | P1 | A Pipeline Deal Can Be Marked Won With No Customer |
| 24 | [BUG-CRM-002](#bug-crm-002) | P1 | Percent Referral Rewards Use the Opportunity Amount, Not Invoiced Revenue |
| 25 | [BUG-CRM-001](#bug-crm-001) | P1 | Mark Referral Paid Says It Drafts a Credit Note. The Service Only Flips Status. |
| 26 | [BUG-CRM-005](#bug-crm-005) | P2 | Won Opportunity Can Draft a Quotation in the UI and Not an Invoice |
| 27 | [BUG-CRM-004](#bug-crm-004) | P2 | Campaigns Cannot Be Edited, and the Funnel Mis-Labels Revenue |
| 28 | [BUG-SUP-001](#bug-sup-001) | P2 | Shared Tickets Freeze Status at Share Time |
| 29 | [BUG-SUP-002](#bug-sup-002) | P2 | Support Tickets Cannot Be Reassigned, and Category Is Invisible |
| 30 | [BUG-SUP-003](#bug-sup-003) | P2 | Share With Bizboard Returns 404 When No Vendor Company Is Configured |
| 31 | [BUG-CRM-006](#bug-crm-006) | P3 | Insights Hub Does Not Open the Attention Inbox |
| 32 | [BUG-UI-024](#bug-ui-024) | P2 | Account Aggregator, GSTR-6/7/8, Shared Tickets, and CRM Onboarding Cannot Finish the Task |

### Wave 6. SaaS billing and abuse limits

Dunning, webhook event handling, the subscription write gate, and a distributed rate limit.

4 findings, 3 open after triage, 1 closed: P0 0, P1 1, P2 2, P3 0 (open).

| # | ID | Sev | Finding |
| ---: | --- | --- | --- |
| 1 | [BUG-BIL-001](#bug-bil-001) | P1 | SaaS Dunning Never Restarts After a Second Past-Due |
| 2 | [BUG-BIL-002](#bug-bil-002) | P2 | Unknown Razorpay Subscription Events Are Stored as Processed |
| 3 | [BUG-SEC-009](#bug-sec-009) | P2 | SaaS Subscription Write-Gate Middleware Bypasses Trailing-Slash URL Normalization |
| 4 | [BUG-SEC-007](#bug-sec-007) | P2, closed (already fixed) | Distributed Redis Token Bucket Rate Limiter Absent |

### Wave 7. Query cost and scale

Pagination caps, N+1 removal, indexes, streaming returns, and the client bundle.

11 findings, 11 open after triage, 0 closed: P0 0, P1 4, P2 6, P3 1 (open).

| # | ID | Sev | Finding |
| ---: | --- | --- | --- |
| 1 | [BUG-SEC-005](#bug-sec-005) | P1 | Unbounded Query Endpoints Causing Denial of Service |
| 2 | [BUG-PERF-001](#bug-perf-001) | P1 | StockBalanceViewSet N+1 Query Multiplier via Missing select_related on Warehouse and BatchLot |
| 3 | [BUG-PERF-002](#bug-perf-002) | P1 | Celery Worker Queue Starvation from Unpartitioned Background Tasks |
| 4 | [BUG-PERF-003](#bug-perf-003) | P1 | Unbounded In-Memory Model Instantiation in GSTR-1 & GSTR-3B Builders |
| 5 | [BUG-PERF-004](#bug-perf-004) | P2 | O(N) All-Time Historical Ledger Scanning on Financial Reports Due to Missing Account Period Balance Rollups |
| 6 | [BUG-PERF-005](#bug-perf-005) | P2 | Missing Critical Multi-Column Composite Indexes on PaymentAllocation, SalesInvoice, and JournalLine |
| 7 | [BUG-PERF-006](#bug-perf-006) | P2 | Correlated Subqueries & Python In-Memory Grouping in Low Stock Alert Calculation |
| 8 | [BUG-PERF-008](#bug-perf-008) | P2 | Sequential Single-Bill Offline Flush Causes Long POS Network Reconnection Delays |
| 9 | [BUG-PERF-007](#bug-perf-007) | P2 | Frontend Initial Bundle Bloat (482 KB Gzip) & Missing Table Virtualization on High-Volume Master Screens |
| 10 | [BUG-UI-011](#bug-ui-011) | P2 | Products Page Unbounded listStock() Call Triggers Heavy Client-Side Memory Overhead |
| 11 | [BUG-SALES-009](#bug-sales-009) | P3 | Trigram Catalog Search Missing on High-Volume Product Lookup |

### Wave 8. Cognitive load and shared screens

Inference, one primary action, shop-floor language, and growth handoffs. Presentation only, except BUG-COG-017.

39 findings, 39 open after triage, 0 closed: P0 10, P1 16, P2 11, P3 2 (open).

| # | ID | Sev | Finding |
| ---: | --- | --- | --- |
| 1 | [BUG-COG-020](#bug-cog-020) | P3 | Read-Only Invoice Series Inputs Mimic Editable Form Fields |
| 2 | [BUG-COG-016](#bug-cog-016) | P1 | Accounting Jargon Confuses Non-Accountant Store Owners |
| 3 | [BUG-COG-015](#bug-cog-015) | P1 | Disabled Document Completion Fails to Explain Root Cause |
| 4 | [BUG-COG-001](#bug-cog-001) | P0 | Sales Invoice Forces Redundant Declarative Choice of Invoice Type |
| 5 | [BUG-COG-002](#bug-cog-002) | P0 | Price Mode Select Forces Repeated Evaluation of Company Default |
| 6 | [BUG-COG-003](#bug-cog-003) | P0 | Unconditional Warehouse Select Renders on Single-Godown Companies |
| 7 | [BUG-UI-019](#bug-ui-019) | P1 | Hindi Mode Still Shows English on Billing, Settings, POS, Reports, and Login |
| 8 | [BUG-COG-014](#bug-cog-014) | P1 | POS Focus Hijacking Overwrites Item Quantities with Barcode Scans |
| 9 | [BUG-COG-005](#bug-cog-005) | P0 | Unranked Document Actions on Posted Invoices Overload Visual Attention |
| 10 | [BUG-COG-006](#bug-cog-006) | P0 | Sales Return Initiation Forces Manual Pogo-Sticking and Line Re-Entry |
| 11 | [BUG-COG-007](#bug-cog-007) | P0 | Premature Place of Supply Prompts Ignore Valid Party GSTIN |
| 12 | [BUG-COG-008](#bug-cog-008) | P0 | Inward Purchase Bill Lines Force Manual Re-Entry of Master Data |
| 13 | [BUG-COG-009](#bug-cog-009) | P1 | Raw ITC Eligibility Enum Exposes Users to Statutory Tax Audit Risk |
| 14 | [BUG-COG-004](#bug-cog-004) | P0 | Active Non-Default Statutory Configurations Hidden Inside Collapsed Drawer |
| 15 | [BUG-UI-015](#bug-ui-015) | P2 | "Save & New" Action Hard-Blocked on Draft Invoices |
| 16 | [BUG-COG-010](#bug-cog-010) | P1 | Fragmented Period Close Navigation Creates Month-End Anxiety |
| 17 | [BUG-ACC-019](#bug-acc-019) | P3 | Books Close and GST Close Are Separate Buttons |
| 18 | [BUG-COG-011](#bug-cog-011) | P1 | User Access Management Requires Manual 8-Checkbox Matrix Configuration |
| 19 | [BUG-COG-012](#bug-cog-012) | P1 | Unlocked GST Settings Allow Accidental Company-Wide Tax Corruption |
| 20 | [BUG-COG-013](#bug-cog-013) | P1 | Dense Products Catalog Overwhelms Initial Visual Search |
| 21 | [BUG-COG-017](#bug-cog-017) | P2 | Bank Reconciliation Forces Manual Confirmation of Obvious 1:1 Matches |
| 22 | [BUG-COG-018](#bug-cog-018) | P2 | Mobile Field Sales Order Lacks Customer Credit and Stock Context Strip |
| 23 | [BUG-COG-019](#bug-cog-019) | P2 | Proprietor Lacks a Consolidated 5-Minute Morning Command Hub |
| 24 | [BUG-COG-G01](#bug-cog-g01) | P0 | Lead-to-Cash Broken Handoff (Forces Re-entry of Quote, Items & Pricing) |
| 25 | [BUG-COG-G02](#bug-cog-g02) | P0 | Customer Complaint Resolution Disconnected from Credit Note Generation |
| 26 | [BUG-COG-G03](#bug-cog-g03) | P1 | HTML5 Drag-and-Drop Kanban Pipeline Completely Fails on Mobile Viewports |
| 27 | [BUG-COG-G04](#bug-cog-g04) | P1 | Unconfirmed Immediate Deal Closure and Contract Cancellation |
| 28 | [BUG-UI-025](#bug-ui-025) | P2 | Cancel Contract, Delete an Attachment, and Move to Won or Lost Need No Confirm |
| 29 | [BUG-COG-G05](#bug-cog-g05) | P1 | Absence of Search, Date Horizons, and Entity Filtering Across Growth OS Registers |
| 30 | [BUG-UI-020](#bug-ui-020) | P2 | CRM, Tickets, Contracts, and Complaints Fetch a Fixed Page and Show No Pager |
| 31 | [BUG-UI-030](#bug-ui-030) | P1 | Total Absence of Search and Filter Dimensions Across Growth OS Screens |
| 32 | [BUG-COG-G06](#bug-cog-g06) | P1 | Contract Expiry Attention Fails to Offer One-Click Renewal Invoicing |
| 33 | [BUG-COG-G07](#bug-cog-g07) | P1 | Support Ticket SLA Breach Indicators Lack Elapsed Time & Paused Context |
| 34 | [BUG-COG-G08](#bug-cog-g08) | P2 | Growth OS First-Run Experience Presents an Uninformative Empty Desert |
| 35 | [BUG-UI-023](#bug-ui-023) | P2 | Growth Modules Share One Empty Sentence, and the Pipeline Has None |
| 36 | [BUG-COG-G09](#bug-cog-g09) | P2 | Customer 360 Workspace Functions as a Read-Only Dead End |
| 37 | [BUG-COG-G10](#bug-cog-g10) | P2 | Referral Reward Approval Disconnected from Financial Settlement |
| 38 | [BUG-UI-016](#bug-ui-016) | P2 | Customer Selection in Lead Dialog Hard-Capped at First 200 Records |
| 39 | [BUG-UI-018](#bug-ui-018) | P1 | Ticket, Contract, and Complaint Create Dialogs Close Without a Dirty Check |

### Wave 9. Counter hardware and remaining UI

Printers, scanner, command palette, confirms, filters, empty states, and accessible names.

17 findings, 17 open after triage, 0 closed: P0 0, P1 0, P2 16, P3 1 (open).

| # | ID | Sev | Finding |
| ---: | --- | --- | --- |
| 1 | [BUG-SALES-007](#bug-sales-007) | P2 | POS Printing Path Restricted to Bluetooth Stub (No WebUSB / Raw TCP Network ESC/POS) |
| 2 | [BUG-SALES-008](#bug-sales-008) | P2 | Cash Drawer Kick-Out Pulse and Weighing Scale Integration Missing |
| 3 | [BUG-INV-006](#bug-inv-006) | P3 | Barcode Label Printing Engine Stubs (No ZPL / TSPL Direct Output) |
| 4 | [BUG-UI-002](#bug-ui-002) | P2 | Barcode Scanner Wedge Lacks 50ms Inter-Keystroke Timing Detection |
| 5 | [BUG-UI-003](#bug-ui-003) | P2 | Quantity Multiplier Keypad Parsing Missing in POS Barcode Scanner |
| 6 | [BUG-UI-004](#bug-ui-004) | P2 | Global Command Palette (Ctrl+K / Cmd+K) Missing |
| 7 | [BUG-UI-005](#bug-ui-005) | P2 | Destructive Action Confirmation Dialogs Lack Entity Name Typing |
| 8 | [BUG-UI-012](#bug-ui-012) | P2 | Destructive Campaign Removal Executes Instantly Without Confirmation Prompt |
| 9 | [BUG-UI-009](#bug-ui-009) | P2 | Brittle Regex Entity Extraction in Insights Assistant Causes Customer Name Parsing Failures |
| 10 | [BUG-UI-021](#bug-ui-021) | P2 | Insurance, Contracts, and Pipeline Show Raw Amounts and ISO Dates |
| 11 | [BUG-UI-022](#bug-ui-022) | P2 | Line-Delete Buttons on Sales and Purchase Editors Have No Accessible Name |
| 12 | [BUG-UI-026](#bug-ui-026) | P2 | Feature-Off Screens Are One Sentence, and Not-Ready Errors Replace the Page Title |
| 13 | [BUG-UI-027](#bug-ui-027) | P2 | Transaction Register Filter Bars Lack Exact Customer / Supplier Autocomplete Dropdown |
| 14 | [BUG-UI-028](#bug-ui-028) | P2 | Missing Indian Financial Year (FY) and Quarterly Date Range Presets in Filter Bars and Reports |
| 15 | [BUG-UI-029](#bug-ui-029) | P2 | Products Catalog Lacks Category, Brand, Stock Availability, and Tax Slab Filters |
| 16 | [BUG-UI-031](#bug-ui-031) | P2 | Universal Search Completely Excludes Growth OS Entities and Auxiliary Documents |
| 17 | [BUG-UI-032](#bug-ui-032) | P2 | Sales and Purchase Reports Lack Time Granularity Grouping (Day / Week / Month / FY) and Line-Level Product… |

### Wave 10. Residual hardening

Observability, role edges, RLS startup, and small UX extras.

7 findings, 7 open after triage, 0 closed: P0 0, P1 0, P2 0, P3 7 (open).

| # | ID | Sev | Finding |
| ---: | --- | --- | --- |
| 1 | [BUG-SEC-008](#bug-sec-008) | P3 | Missing API Latency and Slow Query Telemetry Logger |
| 2 | [BUG-SEC-017](#bug-sec-017) | P3 | Stale Active Company Falls Through to Another Membership |
| 3 | [BUG-SEC-018](#bug-sec-018) | P3 | A Viewer Can Be Granted Financial-Report Access |
| 4 | [BUG-SEC-019](#bug-sec-019) | P3 | Postgres Row-Level Security Is Off Unless Ops Opts In |
| 5 | [BUG-ACC-007](#bug-acc-007) | P3 | Absence of Multi-Branch / Multi-Store P&L Comparative Reporting |
| 6 | [BUG-UI-006](#bug-ui-006) | P3 | Sound Feedback Cues Missing on Barcode Scanning |
| 7 | [BUG-UI-007](#bug-ui-007) | P3 | Shift+P Privacy Mask Missing from Owner Dashboard |

---

## 3. Work packages

The Change text is the register's remediation, kept specific to the cited lines. Where this plan adds a constraint, it is under Constraint.

## Wave 1. Fail closed

Land raw SQL parameterization and the tenant beat loop first. MFA enforcement is last in this wave, after setup requires the password and login no longer stores a usable refresh token.

<a id="bug-sec-003"></a>

### BUG-SEC-003. Potential Raw SQL Execution Bypassing Tenant RLS

> **Triage 2026-10-04: CLOSED. False positive.** core/audit_guard.py and core/checks.py use static SQL or `%s` params; no user input reaches them. No production change is needed.

**Severity**: P0. **Order in wave**: 1. **Domain**: Security.

**Failure.**

Raw SQL string formatting used in low-level schema maintenance checks without explicit query parameterization or company filtering.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_sec_003` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_sec_003` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-001"></a>

### BUG-SEC-001. Background Celery Tasks Execute Multi-Tenant Scans Without Setting RLS Context

> **Triage 2026-10-04: CLOSED. Already fixed.** Contract and recurring-invoice tasks already loop `iter_company_ids()` + `set_rls_company(cid)`. Remediation snippet cites non-existent `tenant_context`. Re-check any remaining argument-free beat tasks only. No production change is needed.

**Severity**: P0. **Order in wave**: 2. **Domain**: Security.

**Failure.**

Celery beat invokes tasks with no arguments. The Celery prerun signal handler sets `app.company_id` to `None`. In PostgreSQL with `FORCE ROW LEVEL SECURITY`, tenant-scoped queries either return empty querysets (silent job abortion) or execute with database-level superuser permissions, bypassing tenant isolation entirely.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_sec_001` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_sec_001` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-002"></a>

### BUG-SEC-002. Razorpay Webhook Authentication Bypass in Test / Staging Environments

> **Triage 2026-10-04: CLOSED. Already fixed.** billing/views.py:189-202 now returns 403 unless env=test AND the test header is present; the inverted condition is gone. No production change is needed.

**Severity**: P0. **Order in wave**: 3. **Domain**: Security.

**Failure.**

```python
if not webhook_secret and settings.DJANGO_ENV == "test":
    if request.headers.get("X-Bizboard-Test-Webhook") and settings.DJANGO_ENV != "test":
        return Response(status=403)
```
The header check requires `and settings.DJANGO_ENV != "test"`, which is mathematically impossible given the outer `settings.DJANGO_ENV == "test"` condition.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_sec_002` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_sec_002` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-014"></a>

### BUG-SEC-014. Empty MFA_ENCRYPTION_KEY Is Derived from SECRET_KEY

> **Triage 2026-10-04: CONFIRMED.** accounts/mfa.py:94-99 derives a Fernet key from SECRET_KEY when MFA_ENCRYPTION_KEY is empty; settings.py:816 does not fail closed.

**Severity**: P2. **Order in wave**: 4. **Domain**: Security.

**Failure.**

When `MFA_ENCRYPTION_KEY` is empty, the code derives a Fernet key from `hashlib.sha256("bizboard-mfa|" + SECRET_KEY)`. Unlike `OTP_PEPPER`, startup does not fail closed.

**If it stays.** Rotating SECRET_KEY makes every stored authenticator undecryptable. The MFA key is not an independent secret.

**Change.**

Raise `ImproperlyConfigured` in production and staging when `MFA_ENCRYPTION_KEY` is empty.

**Files.**

`backend/accounts/mfa.py`

**Done when.**

`test_bug_sec_014` fails on today's code and passes after the change. The test shows this failure is gone: Rotating SECRET_KEY makes every stored authenticator undecryptable. The MFA key is not an independent secret.

**Test.** `test_bug_sec_014` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-015"></a>

### BUG-SEC-015. Forced-Enrolment Token Is Stored in sessionStorage

> **Triage 2026-10-04: CONFIRMED.** web/src/api/client.ts:318-319 writes the enrol token to sessionStorage.

**Severity**: P2. **Order in wave**: 5. **Domain**: Security.

**Failure.**

On an enrolment-required refresh body, the client writes `bizboard:enrol-token` to `sessionStorage`.

**If it stays.** Any script running on the page can read the token and complete MFA setup for a money role within the token lifetime.

**Change.**

Keep the enrol token in memory only.

**Files.**

`web/src/api/client.ts`

**Done when.**

`test_bug_sec_015` fails on today's code and passes after the change. The test shows this failure is gone: Any script running on the page can read the token and complete MFA setup for a money role within the token lifetime.

**Test.** `test_bug_sec_015` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-sec-011"></a>

### BUG-SEC-011. Password Login Mints a Refresh Token Before the MFA Challenge

> **Triage 2026-10-04: CONFIRMED.** LoginView calls parent post() (mints OutstandingToken) before returning mfa_challenge_response; no blacklist call.

**Severity**: P1. **Order in wave**: 6. **Domain**: Security.

**Failure.**

`LoginView` calls `TokenObtainPairView.post` first. When MFA is enabled it returns `mfa_challenge_response` and does not set cookies, but the parent view has already created an `OutstandingToken` row containing a usable refresh JWT. That row is not blacklisted.

**If it stays.** Anyone who can read OutstandingToken.token (backup, database access, admin) can refresh and skip the MFA step. Every MFA login leaves a dangling valid refresh.

**Change.**

Authenticate the password without minting tokens, or blacklist the pair before returning `mfa_required`.

**Files.**

`backend/accounts/views.py` (`LoginView.post`)

**Done when.**

`test_bug_sec_011` fails on today's code and passes after the change. The test shows this failure is gone: Anyone who can read OutstandingToken.token (backup, database access, admin) can refresh and skip the MFA step. Every MFA login leaves a dangling valid refresh.

**Test.** `test_bug_sec_011` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-010"></a>

### BUG-SEC-010. MFA Setup and Confirm Do Not Ask for the Password

> **Triage 2026-10-04: CONFIRMED.** MfaSetupView/MfaConfirmView accept a session or enrol token with no password re-check.

**Severity**: P1. **Order in wave**: 7. **Domain**: Security.

**Failure.**

Setup and confirm accept the logged-in session (or an enrol token) and write a new TOTP secret. Disable uses `_ReauthMixin` and requires the password plus a current second factor. Setup does not.

**If it stays.** A stolen session for a user who has not finished enrolment can bind the attacker's authenticator. Disable then requires the password the attacker may not have, locking out the real user.

**Change.**

Require the same password re-check used by disable before setup and confirm for session actors.

**Files.**

`backend/accounts/mfa_views.py` (`MfaSetupView`, `MfaConfirmView`)

**Done when.**

`test_bug_sec_010` fails on today's code and passes after the change. The test shows this failure is gone: A stolen session for a user who has not finished enrolment can bind the attacker's authenticator. Disable then requires the password the attacker may not have, locking out the real user.

**Test.** `test_bug_sec_010` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-004"></a>

### BUG-SEC-004. Two-Factor Authentication (TOTP) Completely Opt-In for Privileged Roles

> **Triage 2026-10-04: PARTIAL.** `enrolment_required()` exists and is forced on in prod/staging (settings.py:823-831); default is off elsewhere. Real gap: non-prod default and the waiver path.

**Severity**: P1. **Order in wave**: 8. **Domain**: Security.

**Failure.**

MFA is implemented, but no enforcement guard requires enrollment for `OWNER`, `ADMIN`, or `ACCOUNTANT` users.

**If it stays.** Account takeover of business owner credentials via credential stuffing or phishing with zero 2FA challenge.

**Change.**

Keep the existing `enrolment_required()` gate in `accounts/mfa_service.py`; it already blocks login for Owner and Accountant when `MFA_ENFORCE_FOR_MONEY_ROLES` is on, and production and staging force it on. Close the remaining holes: default the setting on in every environment except an explicit `DJANGO_ENV=test`, write an audit event whenever the `MFA_ENFORCE_WAIVER` path is used, and decide whether the Admin role joins `user_has_money_role`.

**Files.**

- `backend/accounts/mfa_service.py`
  - `backend/config/settings.py`

**Ships with.** After BUG-SEC-010 and BUG-SEC-011. Mandatory MFA comes after enrolment cannot be bound by a stolen session and login does not leave a usable refresh token.

**Done when.**

`test_bug_sec_004` asserts that an Owner with no authenticator cannot sign in under the default staging settings and that using the waiver writes an audit row.

**Test.** `test_bug_sec_004` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-012"></a>

### BUG-SEC-012. Customer Portal Phone Lookup Loads Every Tenant's Phones

> **Triage 2026-10-04: CONFIRMED.** portal_views.py:106-113 loads every Customer with a phone under rls_bypass and compares digits in Python.

**Severity**: P1. **Order in wave**: 9. **Domain**: Security.

**Failure.**

Under `rls_bypass()`, a phone request loads every `Customer` with a non-blank phone and compares digits in Python.

**If it stays.** Phone numbers from all companies are materialized in the worker. The scan grows with the whole customer table.

**Change.**

Match a normalized phone column in the database. Do not pull every phone into application memory.

**Files.**

`backend/payments/portal_views.py`

**Done when.**

`test_bug_sec_012` fails on today's code and passes after the change. The test shows this failure is gone: Phone numbers from all companies are materialized in the worker. The scan grows with the whole customer table.

**Test.** `test_bug_sec_012` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-006"></a>

### BUG-SEC-006. Tenant Right-to-Erasure (DPDP Act) Fails on Vertical App Foreign Keys

> **Triage 2026-10-04: PARTIAL.** Drift guard `assert_erasure_model_coverage` exists; need a repro that vertical models actually raise ProtectedError.

**Severity**: P1. **Order in wave**: 10. **Domain**: Security.

**Failure.**

When executing tenant tombstoning/erasure under the Digital Personal Data Protection (DPDP) Act, `TOMBSTONE_RETAINED` omits models from `projects`, `insurance`, `workshop`, `manufacturing`, `contracts`, `payroll`, and `complaints`.

**If it stays.** Executing owner deletion raises a django.db.models.ProtectedError and crashes mid-transaction, leaving the tenant half-deleted.

**Change.**

Write the failing case first: run `erase_company` against a company that has rows in projects, insurance, workshop, manufacturing, contracts, payroll, and complaints. Fix only the models the test shows raising `ProtectedError`, by adding them to `TOMBSTONE_RETAINED` or `PROTECT_MODELS_HANDLED` in `accounts/erasure.py`. The SR-41 drift guard already covers declared company foreign keys.

**Files.**

`backend/accounts/erasure.py` (`TOMBSTONE_RETAINED`)

**Done when.**

`test_bug_sec_006` erases a seeded company with vertical-app data in tombstone and hard modes without an exception and leaves no orphan PII.

**Test.** `test_bug_sec_006` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-013"></a>

### BUG-SEC-013. erase_company Documents a Production --force Gate It Does Not Implement

> **Triage 2026-10-04: CONFIRMED.** erase_company.py:20-27 has --company-id/--confirm/--mode/--reason only; docstring promises --force, code has none.

**Severity**: P2. **Order in wave**: 11. **Domain**: Security.

**Failure.**

The command docstring says it refuses non-production shells unless `--force` is given. `add_arguments` and `handle` implement neither the environment check nor `--force`.

**If it stays.** A shell plus the exact company name can erase a tenant in any environment.

**Change.**

Refuse `DJANGO_ENV` of production or staging unless `--force` is passed, matching the seed commands.

**Files.**

`backend/accounts/management/commands/erase_company.py`

**Done when.**

`test_bug_sec_013` fails on today's code and passes after the change. The test shows this failure is gone: A shell plus the exact company name can erase a tenant in any environment.

**Test.** `test_bug_sec_013` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-020"></a>

### BUG-SEC-020. reset_user_mfa and grant_company_flag Run in Production With No Extra Confirm

> **Triage 2026-10-04: CONFIRMED.** Neither reset_user_mfa.py nor grant_company_flag.py checks DJANGO_ENV or --force.

**Severity**: P3. **Order in wave**: 12. **Domain**: Security.

**Failure.**

MFA reset needs only `--email`. Flag grant mutates live `feature_flags` in any environment. Seed and demo commands refuse production; these two do not.

**If it stays.** Anyone with manage.py on the host can remove MFA or enable a module with one argument.

**Change.**

Refuse production unless `--force` is passed, and audit the flag grant.

**Files.**

- `backend/accounts/management/commands/reset_user_mfa.py`
  - `backend/core/management/commands/grant_company_flag.py`

**Done when.**

`test_bug_sec_020` fails on today's code and passes after the change. The test shows this failure is gone: Anyone with manage.py on the host can remove MFA or enable a module with one argument.

**Test.** `test_bug_sec_020` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-021"></a>

### BUG-SEC-021. Ops Alert Token Is Accepted on the Query String

> **Triage 2026-10-04: CONFIRMED.** core/views.py:608-609 accepts `?token=` query parameter.

**Severity**: P3. **Order in wave**: 13. **Domain**: Security.

**Failure.**

The ops alert check accepts `?token=` as well as `X-Ops-Alert-Token`.

**If it stays.** The token can be stored in proxy logs and Referer.

**Change.**

Accept the header only in production.

**Files.**

`backend/core/views.py`

**Done when.**

`test_bug_sec_021` fails on today's code and passes after the change. The test shows this failure is gone: The token can be stored in proxy logs and Referer.

**Test.** `test_bug_sec_021` in `backend/tests/test_bug_register.py`.

## Wave 2. Money writes

Quantize, then require the idempotency key, then wrap receipt create and allocation in one transaction. Short-collect, settlement discount, and credit-note cancel sit on that transaction. Locks on GRN convert, GL match, subscription status, storage quota, stock transfer, gateway refund, and renewal diary can proceed in parallel with the receipt work because they touch different rows.

<a id="bug-sales-022"></a>

### BUG-SALES-022. Receipt Allocation Does Not Quantize to Paise

> **Triage 2026-10-04: CONFIRMED.** allocate_receipt does `Decimal(amount)` with no quantize.

**Severity**: P3. **Order in wave**: 1. **Domain**: Sales.

**Failure.**

Allocation does `Decimal(amount)` and does not quantize to `0.01`.

**If it stays.** A float JSON payload can store sub-paisa noise.

**Change.**

Quantize to `0.01` at allocate entry.

**Files.**

`backend/payments/services.py` (`allocate_receipt`). `create_receipt` quantizes at about line 285.

**Done when.**

`test_bug_sales_022` fails on today's code and passes after the change. The test shows this failure is gone: A float JSON payload can store sub-paisa noise.

**Test.** `test_bug_sales_022` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-017"></a>

### BUG-SALES-017. Receipt Create Treats Idempotency-Key as Optional

> **Triage 2026-10-04: CONFIRMED.** payments/views.py:155-162 claims idempotency only when the header is present.

**Severity**: P2. **Order in wave**: 2. **Domain**: Sales.

**Failure.**

The view claims an idempotency record only when the header is present.

**If it stays.** Any client that omits the header can create a second receipt on retry. See also **BUG-SALES-012** for the invoice record-payment action.

**Change.**

Require the key on receipt create, allocate, and record-payment.

**Files.**

`backend/payments/views.py`

**Ships with.** Same key rule on receipt create, allocate, and record-payment.

**Done when.**

`test_bug_sales_017` fails on today's code and passes after the change. The test shows this failure is gone: Any client that omits the header can create a second receipt on retry. See also **BUG-SALES-012** for the invoice record-payment action.

**Test.** `test_bug_sales_017` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-012"></a>

### BUG-SALES-012. Record Payment Creates the Receipt and the Allocation as Two Steps

> **Triage 2026-10-04: CONFIRMED.** record_payment calls create_receipt then allocate_receipt in sequence; no wrapping transaction seen.

**Severity**: P1. **Order in wave**: 3. **Domain**: Sales.

**Failure.**

`create_receipt` and `allocate_receipt` each run in their own transaction. The action is not wrapped once and does not claim an idempotency key.

**If it stays.** A double-click, or an allocation failure after the receipt exists, leaves an unallocated advance or posts a second receipt.

**Change.**

Wrap create and allocate in one `transaction.atomic` and require an `Idempotency-Key`.

**Files.**

`backend/sales/views.py` (`record_payment`). The dialog in `web/src/components/RecordInvoicePaymentDialog.tsx` sends no `Idempotency-Key`.

**Ships with.** After BUG-SALES-022 and BUG-SALES-017. One transaction calls the quantized allocator and claims the idempotency key.

**Done when.**

`test_bug_sales_012` fails on today's code and passes after the change. The test shows this failure is gone: A double-click, or an allocation failure after the receipt exists, leaves an unallocated advance or posts a second receipt.

**Test.** `test_bug_sales_012` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-sales-015"></a>

### BUG-SALES-015. Non-Atomic POS Short-Collect Still Receipts the Full Bill

> **Triage 2026-10-04: CONFIRMED.** Legacy POS path (PosPage.tsx:1355-1376) receipts and allocates `invoiceTotal`, ignoring `shortCollectAmount`.

**Severity**: P1. **Order in wave**: 4. **Domain**: Sales.

**Failure.**

When atomic checkout is off, the receipt and allocation use `invoiceTotal` and ignore `extras.shortCollectAmount`.

**If it stays.** A cashier who records a short collection still settles the sale in full.

**Change.**

Use `shortCollectAmount` for the receipt and the allocation on the legacy path.

**Files.**

`web/src/pages/pos/PosPage.tsx` legacy checkout after complete (the atomic branch honors `shortCollectAmount` near line 1315).

**Done when.**

`test_bug_sales_015` fails on today's code and passes after the change. The test shows this failure is gone: A cashier who records a short collection still settles the sale in full.

**Test.** `test_bug_sales_015` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-sales-013"></a>

### BUG-SALES-013. Settlement Discount Clears the Customer Subledger and Is Never Posted

> **Triage 2026-10-04: CONFIRMED.** ledgers/services.py:221 subtracts settlement discount from outstanding; accounting post_receipt has no discount line.

**Severity**: P1. **Order in wave**: 5. **Domain**: Sales.

**Failure.**

The discount is stored on the receipt and reduces party outstanding. The receipt journal debits cash and credits advances for the cash amount only. Allocation moves that same cash amount to AR.

**If it stays.** The invoice looks fully paid while the general ledger still holds the discounted rupees in accounts receivable.

**Change.**

Post the discount as a settlement write-off in the same receipt when books are on.

**Files.**

- `backend/ledgers/services.py` (outstanding subtracts the discount)
  - `backend/accounting/services.py` (`post_receipt` posts `receipt.amount` only)
  - `backend/sales/views.py`

**Ships with.** After BUG-SALES-012. The discount posts inside that same receipt transaction when books are on.

**Done when.**

`test_bug_sales_013` fails on today's code and passes after the change. The test shows this failure is gone: The invoice looks fully paid while the general ledger still holds the discounted rupees in accounts receivable.

**Test.** `test_bug_sales_013` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-018"></a>

### BUG-SALES-018. Cancelling a Credit Note Does Not Restore Peeled Receipt Allocations

> **Triage 2026-10-04: CONFIRMED.** Credit-note cancel in sales/notes_services.py has no allocation restore.

**Severity**: P2. **Order in wave**: 6. **Domain**: Sales.

**Failure.**

Completing a credit note against a paid invoice unallocates receipts. Cancel reverses the journal and status and does not put those allocations back.

**If it stays.** After cancel, the invoice looks due again and the cash remains an unallocated advance.

**Change.**

Re-apply the peeled allocations up to the restored outstanding, or block cancel until the advance is handled.

**Files.**

`backend/sales/notes_services.py` (unallocate on complete) and cancel near lines 379–411.

**Done when.**

`test_bug_sales_018` fails on today's code and passes after the change. The test shows this failure is gone: After cancel, the invoice looks due again and the cash remains an unallocated advance.

**Test.** `test_bug_sales_018` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-016"></a>

### BUG-SALES-016. Record Payment Is Allowed by Sales-Create, Not Payment-Create

> **Triage 2026-10-04: CONFIRMED.** sales/views.py:126-130 puts `record_payment` under CanCreateSales.

**Severity**: P2. **Order in wave**: 7. **Domain**: Sales.

**Failure.**

`record_payment` is gated by `CanCreateSales`. Creating a receipt on the payments API uses `CanCreatePayments`.

**If it stays.** A sales writer without payment permission can still collect and settle an invoice.

**Change.**

Require `CanCreatePayments` on `record_payment`.

**Files.**

`backend/sales/views.py`

**Done when.**

`test_bug_sales_016` fails on today's code and passes after the change. The test shows this failure is gone: A sales writer without payment permission can still collect and settle an invoice.

**Test.** `test_bug_sales_016` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-005"></a>

### BUG-SALES-005. Line Item Edits on Invoices Lack Transactional Atomicity

> **Triage 2026-10-04: CLOSED. Already fixed.** SalesService.set_items is already @transaction.atomic (sales/services.py:659). No production change is needed.

**Severity**: P1. **Order in wave**: 8. **Domain**: Sales.

**Failure.**

`SalesService.set_items` lacks a `@transaction.atomic` decorator. It modifies line items in-place, calculates GST totals, and updates invoice records in separate queries.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_sales_005` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_sales_005` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-016"></a>

### BUG-SEC-016. Purchase Complete, Journal Post, and Receipt Allocation Are Not Audited

> **Triage 2026-10-04: CONFIRMED.** payments/services.py audits create (`record_document_event`) but `allocate_receipt` has no audit call; journal post in accounting/views.py has none.

**Severity**: P2. **Order in wave**: 9. **Domain**: Security.

**Failure.**

Purchase completion records an audit event only inside the books-on posting branch. Manual journal post flips status with no `AuditEvent`. Receipt and payment create/void are audited; allocation is not. Master-data audit gaps remain **BUG-ACC-003**.

**If it stays.** Stock-moving purchases with books off, journal posts, and AR/AP applications cannot be attributed.

**Change.**

Record the document event on every purchase complete, journal post, and allocate/unallocate, inside the same transaction as the money change.

**Files.**

- `backend/purchases/services.py` (audit only when `accounting_enabled`)
  - `backend/accounting/views.py` (journal `post`)
  - `backend/payments/services.py` (`allocate_receipt`)

**Ships with.** After the receipt transaction shape in BUG-SALES-012 is stable. The audit row commits with the money change.

**Done when.**

`test_bug_sec_016` fails on today's code and passes after the change. The test shows this failure is gone: Stock-moving purchases with books off, journal posts, and AR/AP applications cannot be attributed.

**Test.** `test_bug_sec_016` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-013"></a>

### BUG-PUR-013. Convert GRN to Bill Does Not Lock the GRN Row

> **Triage 2026-10-04: CONFIRMED.** convert_to_bill reads converted_purchase_id with no select_for_update.

**Severity**: P2. **Order in wave**: 10. **Domain**: Purchases.

**Failure.**

The method checks `converted_purchase_id` without `select_for_update`. Complete and cancel do lock the row.

**If it stays.** Two concurrent converts can create two draft bills. One link overwrites the other and leaves an orphan draft.

**Change.**

Lock the GRN row before the check and the create.

**Files.**

`backend/purchases/grn_service.py` (`convert_to_bill`)

**Done when.**

`test_bug_pur_013` fails on today's code and passes after the change. The test shows this failure is gone: Two concurrent converts can create two draft bills. One link overwrites the other and leaves an orphan draft.

**Test.** `test_bug_pur_013` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-013"></a>

### BUG-ACC-013. GL Bank-Line Match Is Check-Then-Set With No Row Lock

> **Triage 2026-10-04: CONFIRMED.** BankReconSessionViewSet.match has no atomic block or select_for_update.

**Severity**: P2. **Order in wave**: 11. **Domain**: Accounting.

**Failure.**

The action does not run in `transaction.atomic` and does not `select_for_update` the journal line or the bank line.

**If it stays.** Concurrent matches can dual-link one bank line.

**Change.**

Lock both rows in one transaction and re-check before save.

**Files.**

`backend/accounting/views.py` `BankReconSessionViewSet.match`

**Done when.**

`test_bug_acc_013` fails on today's code and passes after the change. The test shows this failure is gone: Concurrent matches can dual-link one bank line.

**Test.** `test_bug_acc_013` in `backend/tests/test_bug_register.py`.

<a id="bug-bil-003"></a>

### BUG-BIL-003. Subscription Status Updates Do Not Lock the Row

> **Triage 2026-10-04: CONFIRMED.** apply_razorpay_subscription_status has no select_for_update.

**Severity**: P2. **Order in wave**: 12. **Domain**: Billing.

**Failure.**

The function does not `select_for_update` the subscription row.

**If it stays.** Overlapping webhook and recon runs can flip plan or status backwards.

**Change.**

Lock the subscription for the status write.

**Files.**

`backend/billing/services.py` `apply_razorpay_subscription_status`

**Done when.**

`test_bug_bil_003` fails on today's code and passes after the change. The test shows this failure is gone: Overlapping webhook and recon runs can flip plan or status backwards.

**Test.** `test_bug_bil_003` in `backend/tests/test_bug_register.py`.

<a id="bug-bil-004"></a>

### BUG-BIL-004. Storage Quota Check Does Not Lock the Company

> **Triage 2026-10-04: CONFIRMED.** quotas.py:89 locks the company for the complete-count check only; assert_storage_allowed does not lock.

**Severity**: P3. **Order in wave**: 13. **Domain**: Billing.

**Failure.**

The storage check reads usage and allows the upload without `select_for_update`. Complete-count checks lock.

**If it stays.** Concurrent uploads can pass a quota that the sum then exceeds.

**Change.**

Lock the company or the usage row around the check and the create.

**Files.**

`backend/billing/quotas.py`

**Done when.**

`test_bug_bil_004` fails on today's code and passes after the change. The test shows this failure is gone: Concurrent uploads can pass a quota that the sum then exceeds.

**Test.** `test_bug_bil_004` in `backend/tests/test_bug_register.py`.

<a id="bug-inv-005"></a>

### BUG-INV-005. Stock Balance select_for_update() Outside Transaction In Inventory Transfer

> **Triage 2026-10-04: CLOSED. Already fixed.** StockTransferService.complete is already `@transaction.atomic` (inventory/services.py:1317). No production change is needed.

**Severity**: P2. **Order in wave**: 14. **Domain**: Inventory.

**Failure.**

`StockBalance.objects.select_for_update().get_or_create(...)` executed without ensuring enclosing transaction boundaries across all caller pathways.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_inv_005` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_inv_005` in `backend/tests/test_bug_register.py`.

<a id="bug-pay-004"></a>

### BUG-PAY-004. Payment Gateway Partial Refund Outbox Race Condition

> **Triage 2026-10-04: CLOSED. Already fixed.** The refund path locks the row: `GatewayPayment.objects.select_for_update().get(pk=gp.pk)` (payments/services.py ~1720). No production change is needed.

**Severity**: P2. **Order in wave**: 15. **Domain**: Payments.

**Failure.**

Initiating multiple partial refunds against a single gateway payment in rapid succession does not lock the parent `GatewayPayment` row.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_pay_004` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_pay_004` in `backend/tests/test_bug_register.py`.

<a id="bug-ins-004"></a>

### BUG-INS-004. Renewal Diary Concurrency Race Creates Duplicate Renewal Leads

> **Triage 2026-10-04: CLOSED. Already fixed.** PolicyRenewalLead has a unique policy link and the diary checks it (insurance/models.py:129); the cited string-match dedup is gone. No production change is needed.

**Severity**: P2. **Order in wave**: 16. **Domain**: Insurance.

**Failure.**

Deduplication checks use an unindexed string check:
```python
Lead.objects.filter(customer_name=name, message__startswith="Renewal for...").exists()
```
Two concurrent cron workers both evaluate `exists()` to False and create duplicate renewal leads.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_ins_004` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_ins_004` in `backend/tests/test_bug_register.py`.

## Wave 3. Stock and document lifecycle

GRN quantity identity and lot capture come before the cancel pair. BUG-PUR-006 and BUG-PUR-007 merge together. In-transit transfers land before transfer business dates. Shopify connection lands before the pending-delta apply action. Job-card parts reservation and batch validation land before the screen can create an invoice.

<a id="bug-pur-012"></a>

### BUG-PUR-012. GRN Accepted Quantity Is Not Tied to Received or Rejected

> **Triage 2026-10-04: CONFIRMED.** grn_service uses `quantity_accepted` directly; no accepted+rejected=received check.

**Severity**: P2. **Order in wave**: 1. **Domain**: Purchases.

**Failure.**

Complete posts whatever `quantity_accepted` says. The serializer does not require `accepted + rejected = received`.

**If it stays.** Stock can exceed the quantity on the challan.

**Change.**

Enforce that identity before complete.

**Files.**

`backend/purchases/grn_service.py`. `GoodsReceiptItem` only enforces `>= 0`.

**Done when.**

`test_bug_pur_012` fails on today's code and passes after the change. The test shows this failure is gone: Stock can exceed the quantity on the challan.

**Test.** `test_bug_pur_012` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-008"></a>

### BUG-PUR-008. GRN Complete Cannot Receive Batch or Serial Goods

> **Triage 2026-10-04: CONFIRMED.** grn_service posts batch=None; GoodsReceiptItem has no batch/serial fields.

**Severity**: P1. **Order in wave**: 2. **Domain**: Purchases.

**Failure.**

Complete posts `batch=None` and does not receive serials. `GoodsReceiptItem` has no batch or serial fields. Inventory posting requires a batch when `track_batch` is set.

**If it stays.** Batch items fail GRN complete. Serial items can gain quantity with no serial register rows.

**Change.**

Capture lot and serial on the GRN line and pass them into the movement.

**Files.**

`backend/purchases/grn_service.py`

**Done when.**

`test_bug_pur_008` fails on today's code and passes after the change. The test shows this failure is gone: Batch items fail GRN complete. Serial items can gain quantity with no serial register rows.

**Test.** `test_bug_pur_008` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-006"></a>

### BUG-PUR-006. Cancelling a GRN Reverses Stock While the Converted Bill Stays Live

> **Triage 2026-10-04: CONFIRMED.** GRN cancel never checks converted_purchase_id.

**Severity**: P0. **Order in wave**: 3. **Domain**: Purchases.

**Failure.**

Cancel posts `PURCHASE_RETURN` for accepted quantity and never checks `converted_purchase_id`. There is no goods-receipt screen; the API is live. Help text that says there is no GRN is **BUG-PUR-011**.

**If it stays.** After GRN, convert, and complete bill, cancelling the GRN removes stock while the bill, payables, and ITC remain.

**Change.**

Refuse GRN cancel while a non-cancelled converted bill exists.

**Files.**

`backend/purchases/grn_service.py` (`GoodsReceiptService.cancel`)

**Ships with.** Ship in one pull request with BUG-PUR-007. Stock, the bill, and serials move together.

**Done when.**

`test_bug_pur_006` fails on today's code and passes after the change. The test shows this failure is gone: After GRN, convert, and complete bill, cancelling the GRN removes stock while the bill, payables, and ITC remain.

**Test.** `test_bug_pur_006` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-007"></a>

### BUG-PUR-007. Cancelling a GRN-Sourced Bill Does Not Reverse GRN Stock

> **Triage 2026-10-04: CONFIRMED.** Bill cancel (services.py:897) reverses purchase_invoice movements only; GRN-linked stock appears only at the complete path (line 775).

**Severity**: P0. **Order in wave**: 4. **Domain**: Purchases.

**Failure.**

Cancel reverses movements with `reference_type="purchase_invoice"` only. GRN complete posts `reference_type="goods_receipt"` and the bill-complete path skips a second stock post. The same cancel deletes AVAILABLE serials that were received on the bill.

**If it stays.** The bill is cancelled, serials may disappear, and the GRN quantity stays on hand.

**Change.**

Unwind the linked goods-receipt movements in the same cancel, and tie serial removal to that unwind.

**Files.**

`backend/purchases/services.py`

**Ships with.** Ship in one pull request with BUG-PUR-006.

**Done when.**

`test_bug_pur_007` fails on today's code and passes after the change. The test shows this failure is gone: The bill is cancelled, serials may disappear, and the GRN quantity stays on hand.

**Test.** `test_bug_pur_007` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-009"></a>

### BUG-PUR-009. Purchase Returns Ignore GRN Cost Layers

> **Triage 2026-10-04: CONFIRMED.** Return path has no goods_receipt lookup.

**Severity**: P1. **Order in wave**: 5. **Domain**: Purchases.

**Failure.**

Return retirement and `_return_unit_cost` query `reference_type="purchase_invoice"` only. GRN stock is `reference_type="goods_receipt"`, so cost falls back to the line price.

**If it stays.** Returns reduce on-hand, leave orphan FIFO layers, and value the return at the bill price instead of the receipt cost.

**Change.**

Retire and cost from the linked `goods_receipt` movements as well as the bill.

**Files.**

`backend/purchases/services.py`

**Done when.**

`test_bug_pur_009` fails on today's code and passes after the change. The test shows this failure is gone: Returns reduce on-hand, leave orphan FIFO layers, and value the return at the bill price instead of the receipt cost.

**Test.** `test_bug_pur_009` in `backend/tests/test_bug_register.py`.

<a id="bug-inv-001"></a>

### BUG-INV-001. Inter-Godown Stock Transfers Lack "IN_TRANSIT" State

> **Triage 2026-10-04: CONFIRMED.** No IN_TRANSIT state in inventory models/services.

**Severity**: P0. **Order in wave**: 6. **Domain**: Inventory.

**Failure.**

Inter-warehouse transfers jump directly from `DRAFT` to `COMPLETED`. When goods are loaded onto a truck for a multi-day journey between distant godowns, they immediately appear on the destination warehouse ledger.

**If it stays.** During transit, stock can be falsely sold or billed at the destination godown while physically on the road. In-transit theft or damage cannot be isolated.

**Change.**

```
DRAFT -> DISPATCHED (Deducted from source, added to IN_TRANSIT) -> RECEIVED (Added to destination)
```

**Files.**

- `backend/inventory/services.py` (`StockTransferService.complete`)
  - `backend/inventory/models.py` (`StockTransfer`)

**Done when.**

`test_bug_inv_001` fails on today's code and passes after the change. The test shows this failure is gone: During transit, stock can be falsely sold or billed at the destination godown while physically on the road. In-transit theft or damage cannot be isolated.

**Test.** `test_bug_inv_001` in `backend/tests/test_bug_register.py`.

<a id="bug-inv-010"></a>

### BUG-INV-010. Stock Transfer Has No Business Date and Always Uses Today

> **Triage 2026-10-04: CONFIRMED.** StockTransfer model has no date field.

**Severity**: P3. **Order in wave**: 7. **Domain**: Inventory.

**Failure.**

Period gating and the movement date are "today" only.

**If it stays.** A late transfer cannot be attributed to a past open day.

**Change.**

Store a transfer date and gate and post with it.

**Files.**

`backend/inventory/services.py` `StockTransferService.complete` uses `timezone.localdate()`. `StockTransfer` has no transfer date. Missing in-transit state is **BUG-INV-001**.

**Done when.**

`test_bug_inv_010` fails on today's code and passes after the change. The test shows this failure is gone: A late transfer cannot be attributed to a past open day.

**Test.** `test_bug_inv_010` in `backend/tests/test_bug_register.py`.

<a id="bug-inv-009"></a>

### BUG-INV-009. Stock Adjustment Date Gates the Period and Is Not Stored on the Movement

> **Triage 2026-10-04: CONFIRMED.** inventory/views.py:199-200 gates the period on adj_date but post_movement has no movement_date.

**Severity**: P2. **Order in wave**: 8. **Domain**: Inventory.

**Failure.**

The serializer accepts `date`. The movement defaults to today.

**If it stays.** An API backdated adjustment appears on the wrong stock day.

**Change.**

Pass `movement_date=adj_date` into `post_movement`.

**Files.**

`backend/inventory/views.py` adjustment action (period check uses `adj_date`; `post_movement` is called without `movement_date`).

**Done when.**

`test_bug_inv_009` fails on today's code and passes after the change. The test shows this failure is gone: An API backdated adjustment appears on the wrong stock day.

**Test.** `test_bug_inv_009` in `backend/tests/test_bug_register.py`.

<a id="bug-inv-002"></a>

### BUG-INV-002. Zombie Stock Reservations Locking Usable Inventory

> **Triage 2026-10-04: CONFIRMED.** reserve_stock is called on order create (notes_services.py:700); release only on cancel (:894); no expiry job.

**Severity**: P1. **Order in wave**: 9. **Domain**: Inventory.

**Failure.**

Reservations are placed when draft sales orders or quotes are created. However, no periodic Celery worker cleans up stale reservations after a configurable expiry threshold (e.g. 24 hours).

**If it stays.** Available inventory (on_hand - reserved) steadily declines, causing false out-of-stock rejections on active orders.

**Change.**

Deploy a Celery beat task running every 15 minutes to release expired reservations.

**Files.**

`backend/inventory/services.py` (`reserve_stock`)

**Done when.**

`test_bug_inv_002` fails on today's code and passes after the change. The test shows this failure is gone: Available inventory (on_hand - reserved) steadily declines, causing false out-of-stock rejections on active orders.

**Test.** `test_bug_inv_002` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-002"></a>

### BUG-SALES-002. Inward Goods Rejection Leaves Stock Reserved Indefinitely

> **Triage 2026-10-04: CONFIRMED.** route_service.set_stop_status comment says FAILED leaves stock reserved (deliberate; no release or return doc).

**Severity**: P1. **Order in wave**: 10. **Domain**: Sales.

**Failure.**

Marking a delivery stop `FAILED` (e.g., customer doorstep cash refusal) leaves the stock reservation untouched. It neither restores available inventory at the origin godown nor creates a return transit record.

**If it stays.** Sellable stock remains artificially locked as "Reserved", preventing other customers from purchasing it.

**Change.**

Automatically release stock reservations and spawn a `DeliveryChallanReturn` document when a stop status moves to `FAILED` or `REJECTED`.

**Files.**

`backend/sales/route_service.py` (`set_stop_status`)

**Done when.**

`test_bug_sales_002` fails on today's code and passes after the change. The test shows this failure is gone: Sellable stock remains artificially locked as "Reserved", preventing other customers from purchasing it.

**Test.** `test_bug_sales_002` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-001"></a>

### BUG-SALES-001. Sales Orders Do Not Support Partial Conversion (Backorder Lockout)

> **Triage 2026-10-04: CONFIRMED.** convert_sales_order rejects any existing challan/invoice; no partial quantities.

**Severity**: P0. **Order in wave**: 11. **Domain**: Sales.

**Failure.**

```python
if order.converted_invoice_id:
    raise BusinessRuleError("This sales order already has an invoice.")
if DeliveryChallan.objects.filter(sales_order=order).exclude(status=CANCELLED).exists():
    raise BusinessRuleError("This sales order already has a delivery challan.")
```
Conversion requires 100% quantity fulfillment in a single document. If a customer orders 100 units and only 40 are available, converting the 40 locks the sales order forever from fulfilling the remaining 60 units.

**If it stays.** Distributorships and wholesale retailers cannot manage backorders, partial shipments, or split-challan dispatches.

**Change.**

Support `line_quantities` on conversion; maintain `shipped_quantity` and `invoiced_quantity` counters on `SalesOrderItem`. Transition status to `PARTIALLY_CONVERTED` until all lines are fulfilled.

**Files.**

`backend/sales/notes_services.py` (`convert_sales_order`)

**Ships with.** Partial conversion stores shipped and invoiced quantities per line. A second convert of the remainder is allowed. A second convert of an already invoiced quantity is refused.

**Done when.**

`test_bug_sales_001` fails on today's code and passes after the change. The test shows this failure is gone: Distributorships and wholesale retailers cannot manage backorders, partial shipments, or split-challan dispatches.

**Test.** `test_bug_sales_001` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-010"></a>

### BUG-SALES-010. Atomic POS Checkout Drops the Batch, and UPI Drops Header Discount and Charges

> **Triage 2026-10-04: CONFIRMED.** Atomic POS item mapper (PosPage.tsx ~1299) sends serials but no batch_no; the non-atomic path sends it. UPI payload not inspected.

**Severity**: P1. **Order in wave**: 12. **Domain**: Sales.

**Failure.**

The atomic cash item mapper copies serials and not `batch_no`. Cash and UPI do not share one payload builder.

**If it stays.** Batch-tracked sales can leave the cashier's lot. A UPI sale can bill a different total from the cart.

**Change.**

Build one line and header payload for cash and UPI, including batch, discount, and charges.

**Files.**

`web/src/pages/pos/PosPage.tsx`. The non-atomic path sends `batchNo` near line 1174. The UPI atomic payload near line 1485 also omits `invoice_discount` and `additional_charges`.

**Done when.**

`test_bug_sales_010` fails on today's code and passes after the change. The test shows this failure is gone: Batch-tracked sales can leave the cashier's lot. A UPI sale can bill a different total from the cart.

**Test.** `test_bug_sales_010` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-sales-011"></a>

### BUG-SALES-011. Atomic POS Never Sends the Blank Place-of-Supply Confirmation

> **Triage 2026-10-04: CONFIRMED.** Atomic posCheckout body has no confirm_blank_pos.

**Severity**: P1. **Order in wave**: 13. **Domain**: Sales.

**Failure.**

The dialog retry passes `confirmBlankPos` into the client function. The atomic request body never includes it, and the checkout endpoint does not forward it.

**If it stays.** After the cashier confirms a walk-in with no place of supply, atomic checkout still fails.

**Change.**

Accept `confirm_blank_pos` on `pos_checkout` and send it from the atomic retry.

**Files.**

`web/src/pages/pos/PosPage.tsx`. `pos_checkout` in `backend/sales/views.py` calls `SalesService.complete` without `confirm_blank_pos`, which the regular complete action does accept.

**Done when.**

`test_bug_sales_011` fails on today's code and passes after the change. The test shows this failure is gone: After the cashier confirms a walk-in with no place of supply, atomic checkout still fails.

**Test.** `test_bug_sales_011` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-ui-008"></a>

### BUG-UI-008. Walk-in Customer Duplication Race in Offline POS Flush

> **Triage 2026-10-04: PARTIAL.** flushPosCheckout.ts:35-45 now binds the created customer id to the draft (CR-004), but each draft with the same pending name still creates its own customer.

**Severity**: P2. **Order in wave**: 14. **Domain**: Web and hardware.

**Failure.**

In `flushPosDraft`, when multiple offline drafts exist for the same pending walk-in customer (e.g. multiple sales to "Walk-in Cash"), `createCustomer({ name: pendingName })` is executed for each draft without idempotency keys or pre-checking existing customer records.

**If it stays.** Flushing a queue of 20 offline walk-in bills creates 20 duplicate customer records in the database.

**Change.**

The draft already binds its created customer id (CR-004). Remaining gap: in `flushPosDraft`, resolve the pending walk-in name against customers created earlier in the same flush (or a shared idempotency key per pending name) so several drafts with the same name reuse one customer.

**Files.**

`web/src/offline/flushPosCheckout.ts` (`flushPosDraft`)

**Done when.**

`flushPosCheckout` test: three offline drafts with the same walk-in name create exactly one customer.

**Test.** `test_bug_ui_008` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-010"></a>

### BUG-UI-010. Instant Cart Destruction on Unconfirmed F10 Shortcut & Clear Cart Button

> **Triage 2026-10-04: CONFIRMED.** F10 handler calls clearCart() with no confirm (PosPage.tsx:2066-2070).

**Severity**: P1. **Order in wave**: 15. **Domain**: Web and hardware.

**Failure.**

Pressing `F10` on the POS keyboard or clicking the "Clear Cart" button executes `clearCart()` synchronously without displaying an alert or triggering `ConfirmDialog`.

**If it stays.** In a busy retail checkout environment, an accidental brush against the F10 key or an inadvertent mouse click instantly deletes an entire 50-item basket with scanned serials and split tenders, forcing the cashier to rescan every item from scratch while queues mount.

**Change.**

Wrap `clearCart()` behind a confirmation dialog (`ConfirmDialog`) whenever `lines.length > 0`:
```tsx
const handleClearCartRequest = () => {
  if (lines.length === 0) return;
  setConfirmClearCartOpen(true);
};
```

**Files.**

- `web/src/pages/pos/PosPage.tsx` (Keyboard handler for `F10`)
  - `web/src/pages/pos/PosPage.tsx` ("Clear Cart" button)

**Done when.**

`test_bug_ui_010` fails on today's code and passes after the change. The test shows this failure is gone: In a busy retail checkout environment, an accidental brush against the F10 key or an inadvertent mouse click instantly deletes an entire 50-item basket with scanned serials and split tenders, forcing the cashier to rescan every item from…

**Test.** `test_bug_ui_010` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-inv-004"></a>

### BUG-INV-004. FEFO Picking Logic Bypassed on Manual POS & Billing Lines

> **Triage 2026-10-04: CONFIRMED.** No FEFO picking in app code (only a rebuild command mentions it).

**Severity**: P1. **Order in wave**: 16. **Domain**: Inventory.

**Failure.**

While `fefo_batches()` exists as a helper, billing line item creation allows manual batch selection without hard-blocking batches nearing expiry or picking older batches over nearer-expiry batches.

**If it stays.** Near-expiry pharmaceutical or FMCG batches remain on the shelf while fresher batches are sold, resulting in dead stock and regulatory penalties.

**Change.**

Make FEFO batch allocation mandatory for pharmaceutical/FMCG categories unless explicitly overridden by an administrator.

**Files.**

`inventory/services.py` (`fefo_batches`)

**Done when.**

`test_bug_inv_004` fails on today's code and passes after the change. The test shows this failure is gone: Near-expiry pharmaceutical or FMCG batches remain on the shelf while fresher batches are sold, resulting in dead stock and regulatory penalties.

**Test.** `test_bug_inv_004` in `backend/tests/test_bug_register.py`.

<a id="bug-inv-008"></a>

### BUG-INV-008. Shopify Has No Connection Setup for Godown, Customer, Domain, or Secret

> **Triage 2026-10-04: CONFIRMED.** integrations/urls.py has whatsapp/connection but no Shopify connection view; webhook only.

**Severity**: P1. **Order in wave**: 17. **Domain**: Inventory.

**Failure.**

WhatsApp has a connection view. Shopify does not. Held stock deltas and the missing apply action remain **BUG-INV-007** and are not repeated here.

**If it stays.** Webhooks keep skipping with no screen to set the godown and customer.

**Change.**

Add owner connection create/update (domain, secret, warehouse, customer), the same shape as WhatsApp.

**Files.**

`backend/integrations/urls.py` exposes `shopify/webhook/` only. Order ingest in `backend/integrations/shopify.py` requires `metadata.warehouse_id` and `customer_id`.

**Ships with.** Land before BUG-INV-007. A pending-delta screen needs a connection to attach to.

**Done when.**

`test_bug_inv_008` fails on today's code and passes after the change. The test shows this failure is gone: Webhooks keep skipping with no screen to set the godown and customer.

**Test.** `test_bug_inv_008` in `backend/tests/test_bug_register.py`.

<a id="bug-inv-007"></a>

### BUG-INV-007. Shopify Multi-Channel Stock Desync Caused by 25% Discrepancy Tolerance Freeze

> **Triage 2026-10-04: CONFIRMED.** Held deltas are written to `shopify_pending` and notified (shopify.py:285-318), but nothing applies or rejects them.

**Severity**: P1. **Order in wave**: 18. **Domain**: Inventory.

**Failure.**

When Shopify inventory webhooks report stock shifts exceeding a 25% tolerance band (`band = max(1, 0.25 * on_hand)`), the update is diverted into `conn.metadata["shopify_pending"]` with status `pending_review`. However, no UI screen, alert notification, Celery reminder, or manual resolution API exists anywhere in BizBoard to review, approve, or apply pending stock adjustments.

**If it stays.** Restocks from batch shipments (e.g. from 10 to 100 units) or flash sales are permanently stranded in metadata. Shopify and physical BizBoard inventory drift apart indefinitely without alerting operations.

**Change.**

Add an approval/review endpoint `POST /api/v1/integrations/shopify/pending/<item_key>/apply` and surface a pending reconciliation badge on the Integrations dashboard.

**Files.**

`backend/integrations/shopify.py`, `backend/integrations/shopify.py`

**Ships with.** After BUG-INV-008. Apply stays inside the existing 25% hold. Do not auto-post a large delta.

**Done when.**

`test_bug_inv_007` fails on today's code and passes after the change. The test shows this failure is gone: Restocks from batch shipments (e.g. from 10 to 100 units) or flash sales are permanently stranded in metadata. Shopify and physical BizBoard inventory drift apart indefinitely without alerting operations.

**Test.** `test_bug_inv_007` in `backend/tests/test_bug_register.py`.

<a id="bug-wrk-002"></a>

### BUG-WRK-002. Workshop Parts Issuance Does Not Reserve Stock During Repair

> **Triage 2026-10-04: CONFIRMED.** No reservation call anywhere in workshop/services.py.

**Severity**: P1. **Order in wave**: 19. **Domain**: Workshop.

**Failure.**

Adding parts to a job card creates a line item, but does **not** create a stock reservation in `StockReservation`. Parts physically installed on a vehicle remain available on the shelf in the system.

**If it stays.** Counter clerks can sell the same physical parts at the retail counter, causing invoice completion failures when the job card is billed.

**Change.**

Automatically reserve stock upon adding a part line to an active job card.

**Files.**

`backend/workshop/services.py` (`add_line`)

**Done when.**

`test_bug_wrk_002` fails on today's code and passes after the change. The test shows this failure is gone: Counter clerks can sell the same physical parts at the retail counter, causing invoice completion failures when the job card is billed.

**Test.** `test_bug_wrk_002` in `backend/tests/test_bug_register.py`.

<a id="bug-wrk-001"></a>

### BUG-WRK-001. Job Card Parts Invoicing Bypasses Batch-Tracking Validation

> **Triage 2026-10-04: CONFIRMED.** workshop/services.py convert_to_invoice maps serials only; no batch handling.

**Severity**: P1. **Order in wave**: 20. **Domain**: Workshop.

**Failure.**

Converting job cards to invoices maps serial numbers for serial-tracked items, but completely omits `batch` and `batch_no` for batch-tracked spare parts (e.g. engine oils, brake pads, fluids).

**If it stays.** Completing the generated sales invoice fails batch validation or picks arbitrary batches, breaking warehouse traceability.

**Change.**

Add batch selection fields to `JobCardLine` for batch-tracked products and validate batch expiry dates prior to conversion.

**Files.**

`backend/workshop/services.py` (`convert_to_invoice`)

**Done when.**

`test_bug_wrk_001` fails on today's code and passes after the change. The test shows this failure is gone: Completing the generated sales invoice fails batch validation or picks arbitrary batches, breaking warehouse traceability.

**Test.** `test_bug_wrk_001` in `backend/tests/test_bug_register.py`.

<a id="bug-wrk-006"></a>

### BUG-WRK-006. Job Card Invoice Cannot Succeed From the Screen

> **Triage 2026-10-04: CONFIRMED.** JobCardsPage has only customer + complaint inputs (no add-line control) and navigates to /sales/invoices/:id (route missing).

**Severity**: P0. **Order in wave**: 21. **Domain**: Workshop.

**Failure.**

The Invoice button is shown for every job that is not `INVOICED` or `CANCELLED`. The API raises "Add at least one line before invoicing." The page has no add-line, start, or cancel control. Convert sets the job to `IN_PROGRESS` and links a draft; the button label says Invoice and stays available. On success the page navigates to `/sales/invoices/:id`, which is not a route (`sales/history/:id` is). Batch omission on convert is **BUG-WRK-001**. Parts are not reserved, **BUG-WRK-002**.

**If it stays.** Every Invoice click from the screen errors. A job that already has lines (created through the API) lands on Not Found. The same missing route on projects is **BUG-PRJ-002**.

**Change.**

Add lines in the UI, hide Invoice until lines exist, label the action "Create draft invoice", and open `/sales/history/:id`.

**Files.**

- `web/src/pages/workshop/JobCardsPage.tsx`
  - `backend/workshop/services.py`
  - `web/src/api/roadmap.ts` exposes list, create, and convert only

**Ships with.** After BUG-WRK-001 and BUG-WRK-002. The screen can add a line, then open `/sales/history/:id`.

**Done when.**

`test_bug_wrk_006` fails on today's code and passes after the change. The test shows this failure is gone: Every Invoice click from the screen errors. A job that already has lines (created through the API) lands on Not Found. The same missing route on projects is **BUG-PRJ-002**.

**Test.** `test_bug_wrk_006` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-prj-001"></a>

### BUG-PRJ-001. Milestone Invoiced Against Draft Invoice Without Revenue Posting

> **Triage 2026-10-04: CLOSED. Already fixed.** projects/services.py:92-96 only sets INVOICED when the invoice status is COMPLETED. No production change is needed.

**Severity**: P0. **Order in wave**: 22. **Domain**: Projects.

**Failure.**

`invoice_milestone` links the milestone to a `DRAFT` `SalesInvoice` and marks `milestone.status = INVOICED` without invoking `SalesService.complete(invoice)`. No receivables, revenue, or GST entries are posted to the general ledger.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_prj_001` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_prj_001` in `backend/tests/test_bug_register.py`.

<a id="bug-ins-001"></a>

### BUG-INS-001. Selecting Multiple Options Issues Duplicate Overlapping Policies

> **Triage 2026-10-04: CLOSED. Already fixed.** choose_option locks the option set and rejects when policies already exist. No production change is needed.

**Severity**: P0. **Order in wave**: 23. **Domain**: Insurance.

**Failure.**

When a prospect lead has multiple quoted options, selecting two options in quick succession creates two overlapping, active in-force policies under the same customer without checking existing policy state.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_ins_001` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_ins_001` in `backend/tests/test_bug_register.py`.

## Wave 4. GST, books, and collections

Match GSTR-2B on the supplier bill number before changing the ITC default and before excluding time-barred credit. The till and the trial-balance worker are the books P0s. The worker uses the tenant loop from wave 1 and only raises books-health. Cheque dishonour posts a fee document. It does not file a court case.

<a id="bug-gst-007"></a>

### BUG-GST-007. GSTR-2B and IMS Match the Internal Purchase Number, Not the Supplier Bill Number

> **Triage 2026-10-04: CONFIRMED.** gstr2b.py:84 matches number__iexact; the model has a separate supplier_bill_number.

**Severity**: P0. **Order in wave**: 1. **Domain**: GST.

**Failure.**

Portal 2B invoice numbers are the supplier's bill numbers. Bizboard's `PurchaseInvoice.number` is the internal series. Tests seed 2B rows with `pi.number`, so the suite does not catch a real portal file. Duplicate ingest is a separate defect, **BUG-GST-005**. Time-barred ITC is **BUG-GST-002**.

**If it stays.** Real 2B uploads stay unmatched, so claimable ITC and the IMS missing-in-books scorecard are wrong.

**Change.**

Match `supplier_bill_number` first, and fall back to `number` only when that field is blank. Use the same key in IMS.

**Files.**

- `backend/reporting/gstr2b.py` (`number__iexact=row.invoice_number`)
  - `backend/reporting/ims.py` builds book keys from `PurchaseInvoice.number`
  - `backend/purchases/models.py` stores the supplier's number on `supplier_bill_number`

**Ships with.** Before BUG-PUR-010 and BUG-GST-002. The match key is the supplier bill number.

**Done when.**

`test_bug_gst_007` fails on today's code and passes after the change. The test shows this failure is gone: Real 2B uploads stay unmatched, so claimable ITC and the IMS missing-in-books scorecard are wrong.

**Test.** `test_bug_gst_007` in `backend/tests/test_bug_register.py`.

<a id="bug-gst-005"></a>

### BUG-GST-005. GSTR-2B Ingest Does Not Detect Duplicate Ingestions

> **Triage 2026-10-04: CLOSED. Already fixed.** reporting/models.py:163-170 has three UniqueConstraints on (company, period, supplier_gstin, invoice_number/date). No production change is needed.

**Severity**: P2. **Order in wave**: 2. **Domain**: GST.

**Failure.**

Re-importing a GSTR-2B JSON file for the same period relies on application-level filtering rather than a database unique constraint on `(company_id, gstin, invoice_number, period)`.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_gst_005` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_gst_005` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-010"></a>

### BUG-PUR-010. New Purchase Bills Default ITC to CLAIMABLE and Hide UNREVIEWED

> **Triage 2026-10-04: CONFIRMED.** NewPurchasePage default and menu are CLAIMABLE/INELIGIBLE/REVERSED; no UNREVIEWED.

**Severity**: P1. **Order in wave**: 3. **Domain**: Purchases.

**Failure.**

The screen does not offer the backend default. Statutory checklist gaps remain **BUG-GST-003**.

**If it stays.** Every new bill is marked claimable before review.

**Change.**

Default the control to `UNREVIEWED` and include that option.

**Files.**

`web/src/pages/purchases/NewPurchasePage.tsx` (default `'CLAIMABLE'` and a menu of CLAIMABLE / INELIGIBLE / REVERSED). Model default is `UNREVIEWED`.

**Ships with.** After BUG-GST-007. New bills default to UNREVIEWED.

**Done when.**

`test_bug_pur_010` fails on today's code and passes after the change. The test shows this failure is gone: Every new bill is marked claimable before review.

**Test.** `test_bug_pur_010` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-gst-003"></a>

### BUG-GST-003. Section 16(2) Statutory 4-Condition Checklist Absent on Purchase Bills

> **Triage 2026-10-04: CONFIRMED.** No 16(2) checklist found.

**Severity**: P1. **Order in wave**: 4. **Domain**: GST.

**Failure.**

Instead of validating the 4 statutory conditions mandated by Section 16(2) of the CGST Act (tax invoice possessed, goods received, tax deposited by supplier, return filed by supplier), the system relies on a single manual enum (`CLAIMABLE`/`INELIGIBLE`).

**If it stays.** Inward ITC claims lack defensible statutory evidence during departmental GST audits.

**Change.**

Build a formal Section 16(2) checklist verifying GRN receipt, 2B match, and supplier filing status before marking ITC claimable.

**Files.**

`backend/reporting/ims.py`

**Done when.**

`test_bug_gst_003` fails on today's code and passes after the change. The test shows this failure is gone: Inward ITC claims lack defensible statutory evidence during departmental GST audits.

**Test.** `test_bug_gst_003` in `backend/tests/test_bug_register.py`.

<a id="bug-gst-002"></a>

### BUG-GST-002. Section 16(4) Time-Barred ITC Warning Not Enforced as a Strict Exclusion

> **Triage 2026-10-04: PARTIAL.** 16(4) clock and expiry alerts exist (reporting/ims.py, insights/attention.py); hard exclusion in GSTR-3B not confirmed.

**Severity**: P1. **Order in wave**: 5. **Domain**: GST.

**Failure.**

The Invoice Management System calculates the statutory November 30 time-barring deadline, but only displays an alert chip. It does not actively exclude time-barred purchase bills from populating Table 4(A) in GSTR-3B filings.

**If it stays.** Taxpayers accidentally claim invalid input tax credit, triggering demand notices, 18% statutory interest, and penalty proceedings under Section 73/74.

**Change.**

The Section 16(4) clock and expiry alerts already exist in `reporting/ims.py` and `insights/attention.py`. Add the missing exclusion: GSTR-3B ITC lines past the 16(4) deadline drop out of claimable ITC unless the user records an override with a reason.

**Files.**

`backend/reporting/ims.py`

**Done when.**

`test_bug_gst_002` shows a purchase past its 16(4) deadline is excluded from GSTR-3B claimable ITC and returns when an override is recorded.

**Test.** `test_bug_gst_002` in `backend/tests/test_bug_register.py`.

<a id="bug-gst-008"></a>

### BUG-GST-008. OCR GST Rates That Miss a Slab Are Silently Snapped to 18%

> **Triage 2026-10-04: CONFIRMED.** imports/services.py:662 `snapped = Decimal("18")`.

**Severity**: P2. **Order in wave**: 6. **Domain**: GST.

**Failure.**

The importer sets the rate to `Decimal("18")` and keeps a warning string. It does not drop the line or require a confirm.

**If it stays.** A misread 0%, 5%, or 12% line can land on the draft bill as 18% tax.

**Change.**

Leave the line unmatched and require an explicit rate.

**Files.**

`backend/imports/services.py` (rate snap when the value is not near an allowed slab)

**Done when.**

`test_bug_gst_008` fails on today's code and passes after the change. The test shows this failure is gone: A misread 0%, 5%, or 12% line can land on the draft bill as 18% tax.

**Test.** `test_bug_gst_008` in `backend/tests/test_bug_register.py`.

<a id="bug-gst-001"></a>

### BUG-GST-001. E-Way Bill Vehicle Update (Part B) and Validity Extension Endpoints Missing

> **Triage 2026-10-04: CONFIRMED.** No Part-B update or validity-extension code outside migrations/tests.

**Severity**: P0. **Order in wave**: 7. **Domain**: GST.

**Failure.**

The system implements `generate`, `fetch`, and `cancel` for E-Way Bills, but completely lacks endpoints for **Updating Part B Vehicle Numbers** (breakdown during transit) and **Extending Validity** (traffic/transit delay before expiry).

**If it stays.** When a transport vehicle breaks down, the driver cannot update the E-Way Bill Part B. Consignments are detained and penalized with 200% tax penalties by GST flying squads.

**Change.**

Implement `update_eway_vehicle(ewb_no, vehicle_no, reason_code)` and `extend_eway_validity(ewb_no, reason_code, remaining_distance)`.

**Files.**

`backend/sales/einvoice_eway_actions.py`

**Done when.**

`test_bug_gst_001` fails on today's code and passes after the change. The test shows this failure is gone: When a transport vehicle breaks down, the driver cannot update the E-Way Bill Part B. Consignments are detained and penalized with 200% tax penalties by GST flying squads.

**Test.** `test_bug_gst_001` in `backend/tests/test_bug_register.py`.

<a id="bug-gst-006"></a>

### BUG-GST-006. E-Way Bill Generation Completely Broken for Export Consignments Due to 6-Digit Buyer PIN Enforcement

> **Triage 2026-10-04: CONFIRMED.** _buyer_pincode (eway_payload.py:101-119) only accepts 6 digits; no export / subSupplyType 3 special case, toStateCode falls back to 0.

**Severity**: P1. **Order in wave**: 8. **Domain**: GST.

**Failure.**

NIC E-Way Bill schema for Export / SEZ outward supplies (`subSupplyType = 3`) explicitly mandates `toPincode: 999999` and `toStateCode: 99` (Other Territory / Overseas). However, `_buyer_pincode()` enforces a strict 6-digit regex (`re.fullmatch(r"\d{6}", raw)`) against the foreign customer's postal code and throws a `BusinessRuleError`.

**If it stays.** Any exporter attempting to generate an e-Way bill for an export shipment (e.g. consignments dispatched to port / air cargo with foreign customer addresses) is blocked with an unhandled validation error.

**Change.**

Detect export supplies in `eway_payload.py` (`invoice.sub_supply_type == "3"` or `is_export_or_sez_supply(invoice.supply_type)`), bypass `_buyer_pincode`, and emit `toStateCode: 99`, `toPincode: 999999`, and `toGstin: "URP"`.

**Files.**

- `backend/sales/eway_payload.py` (`_buyer_pincode`)
  - `backend/sales/eway_payload.py`, `backend/sales/eway_payload.py` (`build_eway_payload_from_invoice`)

**Done when.**

`test_bug_gst_006` fails on today's code and passes after the change. The test shows this failure is gone: Any exporter attempting to generate an e-Way bill for an export shipment (e.g. consignments dispatched to port / air cargo with foreign customer addresses) is blocked with an unhandled validation error.

**Test.** `test_bug_gst_006` in `backend/tests/test_bug_register.py`.

<a id="bug-gst-004"></a>

### BUG-GST-004. Section 206AB / 206CCA Higher TDS/TCS Compliance Check Missing

> **Triage 2026-10-04: CONFIRMED.** No 206AB/206CCA code anywhere.

**Severity**: P1. **Order in wave**: 9. **Domain**: GST.

**Failure.**

The system does not verify whether suppliers/customers are "specified persons" (non-filers of income tax returns for the prior year) under Sections 206AB and 206CCA.

**If it stays.** Taxpayers deduct TDS/TCS at standard rates (e.g. 0.1%) instead of the mandatory higher rate (e.g. 5%), incurring tax shortfall liabilities.

**Change.**

Add a PAN compliance verification utility flagging non-filers and automatically applying higher withholding tax rates.

**Files.**

`backend/accounting/services.py`

**Done when.**

`test_bug_gst_004` fails on today's code and passes after the change. The test shows this failure is gone: Taxpayers deduct TDS/TCS at standard rates (e.g. 0.1%) instead of the mandatory higher rate (e.g. 5%), incurring tax shortfall liabilities.

**Test.** `test_bug_gst_004` in `backend/tests/test_bug_register.py`.

<a id="bug-ui-014"></a>

### BUG-UI-014. Free-Text TDS Section Input on Purchase Bills Causes Withholding Tax Errors

> **Triage 2026-10-04: CONFIRMED.** NewPurchasePage.tsx:2139 TDS section is a free-text field.

**Severity**: P2. **Order in wave**: 10. **Domain**: Web and hardware.

**Failure.**

The TDS Section field is a free-form input (`placeholder="194C"`) with no statutory dropdown selector, threshold enforcement, or auto-populating TDS rate percentage.

**If it stays.** Accounts payable operators enter inconsistent section strings (e.g. "194C", "Sec 194-C", "194 C Contractor") and guess tax rates (e.g. 1% vs 2% for individuals vs companies under 194C), generating discrepancies during quarterly Form 26Q return preparation.

**Change.**

Replace free-text input with a standard Indian Income Tax TDS Section dropdown (`194C - Contractors (1%/2%)`, `194J - Professional Fees (2%/10%)`, `194I - Rent (2%/10%)`, `194Q - Purchase of Goods (0.1%)`) that automatically defaults the statutory withholding rate based on vendor PAN/constitution.

**Files.**

`web/src/pages/purchases/NewPurchasePage.tsx`

**Done when.**

`test_bug_ui_014` fails on today's code and passes after the change. The test shows this failure is gone: Accounts payable operators enter inconsistent section strings (e.g. "194C", "Sec 194-C", "194 C Contractor") and guess tax rates (e.g. 1% vs 2% for individuals vs companies under 194C), generating discrepancies during quarterly Form 26Q…

**Test.** `test_bug_ui_014` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-pur-001"></a>

### BUG-PUR-001. Absence of Strict Line-Level 3-Way Matching Tolerances

> **Triage 2026-10-04: RECLASSIFIED as P2 feature work.** `match_bill_to_po` does not exist anywhere in purchases/. This is a missing feature, not a defect in existing code; fix the file reference.

**Severity**: P2 (reclassified from P1: missing feature). **Order in wave**: 11. **Domain**: Purchases.

**Failure.**

Inward vendor bills check aggregate invoice totals against Purchase Orders without strict line-item quantity and rate variance verification against the Goods Receipt Note (GRN).

**If it stays.** Discrepancies on individual line items (e.g., vendor inflates rate by 20% on one line and lowers another) go completely unnoticed.

**Change.**

This is new capability, not a defect fix: there is no bill-to-PO matching code today. Build line-level matching (quantity and rate variance against the PO and the GRN, with a manager override) after the GRN fixes in wave 3 land. Do not start before BUG-PUR-012 and BUG-PUR-008.

**Files.**

`backend/purchases/services.py` (`match_bill_to_po`)

**Done when.**

`test_bug_pur_001` fails on today's code and passes after the change. The test shows this failure is gone: Discrepancies on individual line items (e.g., vendor inflates rate by 20% on one line and lowers another) go completely unnoticed.

**Test.** `test_bug_pur_001` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-002"></a>

### BUG-PUR-002. GRN Inspection Rejections Do Not Generate Supplier Debit Notes

> **Triage 2026-10-04: CONFIRMED.** No debit-note creation in grn_service.

**Severity**: P1. **Order in wave**: 12. **Domain**: Purchases.

**Failure.**

When warehouse receiving marks `quantity_rejected` and `rejection_reason` on an incoming GRN, no automatic workflow creates a draft Purchase Debit Note.

**If it stays.** Accounting routinely pays vendor bills in full because physical rejections at the loading dock fail to link to the finance accounts payable ledger.

**Change.**

Auto-generate a draft `PurchaseDebitNote` upon completing a GRN with rejected line items.

**Files.**

`backend/purchases/models.py` (`GoodsReceiptNoteLine`)

**Done when.**

`test_bug_pur_002` fails on today's code and passes after the change. The test shows this failure is gone: Accounting routinely pays vendor bills in full because physical rejections at the loading dock fail to link to the finance accounts payable ledger.

**Test.** `test_bug_pur_002` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-003"></a>

### BUG-PUR-003. Purchase Bill Amendments Mutate Records Without Version Snapshotting

> **Triage 2026-10-04: CONFIRMED.** No revision/snapshot model in purchases/models.py.

**Severity**: P1. **Order in wave**: 13. **Domain**: Purchases.

**Failure.**

Amendments to completed purchase bills mutate the record in-place, preserving only previous totals. Full line-item snapshots are not preserved in an immutable history table.

**If it stays.** Violates MCA Rule 11(g) requirements for audit trail integrity on accounting records.

**Change.**

Create a `PurchaseInvoiceRevision` snapshot table storing full document state prior to every mutation.

**Files.**

`backend/purchases/views.py`

**Done when.**

`test_bug_pur_003` fails on today's code and passes after the change. The test shows this failure is gone: Violates MCA Rule 11(g) requirements for audit trail integrity on accounting records.

**Test.** `test_bug_pur_003` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-004"></a>

### BUG-PUR-004. Foreign Vendor Import Without Bill of Entry Lacks Strict Blocking

> **Triage 2026-10-04: PARTIAL.** Guard exists (`_assert_import_bill_of_entry`) but `_is_foreign_import_supplier` infers import from GSTIN/state heuristics, not a country field.

**Severity**: P2. **Order in wave**: 14. **Domain**: Purchases.

**Failure.**

Guard verifies that foreign import suppliers carry a Bill of Entry (BOE), but allows bypass if the supplier is not explicitly tagged with `country != 'IN'`.

**If it stays.** Import purchases can be posted as domestic GST purchases, leading to incorrect GSTR-3B Table 4(A)(1) reporting.

**Change.**

Replace the GSTIN/state guess in `_is_foreign_import_supplier` with an explicit supplier country (add the field if it is missing). Keep the Bill of Entry guard that already exists.

**Files.**

`backend/purchases/services.py` (`_assert_import_bill_of_entry`)

**Done when.**

`test_bug_pur_004` shows a supplier with country other than IN cannot complete a purchase without its own completed Bill of Entry, even with a blank GSTIN and state.

**Test.** `test_bug_pur_004` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-005"></a>

### BUG-PUR-005. Bulk Price Adjustments on Landed Costs Lack Weighted Average Recalculation

> **Triage 2026-10-04: PARTIAL.** restamp_fifo_layers_for_price_amend refuses when quantity is already peeled and is a no-op for WAVG companies; the COGS-variance gap is narrower than written.

**Severity**: P2. **Order in wave**: 15. **Domain**: Purchases.

**Failure.**

Amending prices on a completed purchase updates FIFO layers, but does not re-compute Weighted Average Cost (WAC) for already-consumed stock movements.

**If it stays.** COGS on already-sold items reflects outdated purchase costs, misstating monthly gross profit.

**Change.**

Narrow to the real gap. FIFO companies are already refused when quantity has been consumed. For WAVG companies, `restamp_fifo_layers_for_price_amend` returns without changing cost. Decide with the founder: refuse the price amend once stock is consumed (as FIFO does) or post a COGS variance journal.

**Files.**

`backend/purchases/services.py` (`restamp_fifo_layers_for_price_amend`)

**Done when.**

`test_bug_pur_005` amends a purchase price after part of the stock was sold on a WAVG company and sees either a refusal or a balanced variance journal.

**Test.** `test_bug_pur_005` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-011"></a>

### BUG-PUR-011. Help Says There Is No GRN While the GRN API Is Live and Has No Screen

> **Triage 2026-10-04: CONFIRMED.** Help copy (contextHelp/catalog/purchases.ts) says there is no GRN; GRN API is live and no web route uses it. Product decision as much as defect.

**Severity**: P1. **Order in wave**: 16. **Domain**: Purchases.

**Failure.**

Product copy says bill complete is the inward. The API can still complete, convert, and cancel GRNs, which is how **BUG-PUR-006** and **BUG-PUR-007** are reachable.

**If it stays.** Staff follow the help text. Integrations can hit the stock traps.

**Change.**

Ship a GRN screen, or refuse the GRN API outside lab builds.

**Files.**

`web/src/contextHelp/catalog/purchases.ts`. API: `GoodsReceiptService` in `backend/purchases/grn_service.py`. No `web` route posts a GRN.

**Ships with.** Decision: ship a GRN screen. Batch and serial entry for BUG-PUR-008 needs a surface, and help must describe that surface.

**Done when.**

`test_bug_pur_011` fails on today's code and passes after the change. The test shows this failure is gone: Staff follow the help text. Integrations can hit the stock traps.

**Test.** `test_bug_pur_011` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-pur-014"></a>

### BUG-PUR-014. Product Import Maps a Column Named rate Onto Selling Price

> **Triage 2026-10-04: CONFIRMED.** imports/services.py aliases `rate` to selling_price (per register; not re-read).

**Severity**: P3. **Order in wave**: 17. **Domain**: Purchases.

**Failure.**

A bare `rate` header is treated as selling price.

**If it stays.** A purchase-oriented CSV can overwrite selling prices.

**Change.**

Map only explicit `selling_price` and `purchase_price` headers.

**Files.**

`backend/imports/services.py` (`selling_price` aliases include `rate`)

**Done when.**

`test_bug_pur_014` fails on today's code and passes after the change. The test shows this failure is gone: A purchase-oriented CSV can overwrite selling prices.

**Test.** `test_bug_pur_014` in `backend/tests/test_bug_register.py`.

<a id="bug-pur-015"></a>

### BUG-PUR-015. Purchase Invoice Free-Text Search (`q`) Disregards Supplier Name and Phone

> **Triage 2026-10-04: CONFIRMED.** purchases/views.py:112-113 filters `q` on `number__icontains` only.

**Severity**: P1. **Order in wave**: 18. **Domain**: Purchases.

**Failure.**

`PurchaseInvoiceViewSet` filters `q` solely against `number__icontains=params["q"]`. In contrast, `SalesInvoiceViewSet` (`backend/sales/views.py#L206-L212`) queries `number`, `customer__name`, and `customer__phone`.

**If it stays.** Store operators and accountants entering a supplier's company name or contact number in the Purchase History search box receive zero results, forcing manual pagination or document number lookup.

**Change.**

Expand `PurchaseInvoiceViewSet` query parameters to match sales search ergonomics:
```python
if params.get("q"):
    term = params["q"]
    qs = qs.filter(
        Q(number__icontains=term)
        | Q(supplier__name__icontains=term)
        | Q(supplier__phone__icontains=term)
    )
```

**Files.**

`backend/purchases/views.py` (`PurchaseInvoiceViewSet.get_queryset`)

**Done when.**

`test_bug_pur_015` fails on today's code and passes after the change. The test shows this failure is gone: Store operators and accountants entering a supplier's company name or contact number in the Purchase History search box receive zero results, forcing manual pagination or document number lookup.

**Test.** `test_bug_pur_015` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-001"></a>

### BUG-ACC-001. Absence of Daily POS Shift Close & Cash Drawer Register

> **Triage 2026-10-04: CONFIRMED.** No shift-close or till model anywhere in backend.

**Severity**: P0. **Order in wave**: 19. **Domain**: Accounting.

**Failure.**

No shift register or day-close model exists. Cashiers cannot enter physical cash denomination counts (₹500, ₹200, ₹100 notes) to calculate cashier cash over/short variances.

**If it stays.** Daily cash discrepancies cannot be isolated to individual cashiers or shifts. Registers cannot be frozen against retroactive edits.

**Change.**

Create a `CashShiftRegister` entity with opening float, physical cash denomination breakdown, expected system cash, variance calculation, and day-lock mechanism.

**Files.**

`backend/accounting/views.py`

**Done when.**

`test_bug_acc_001` fails on today's code and passes after the change. The test shows this failure is gone: Daily cash discrepancies cannot be isolated to individual cashiers or shifts. Registers cannot be frozen against retroactive edits.

**Test.** `test_bug_acc_001` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-002"></a>

### BUG-ACC-002. Unscheduled Trial Balance Zero-Sum Verification Worker

> **Triage 2026-10-04: CLOSED. Already fixed.** `core-nightly-invariants` beat runs the `gl.trial_balance_zero` invariant (settings.py:627, core/invariants/gl.py:49). Remaining gap: alerting/blocking only. No production change is needed.

**Severity**: P0. **Order in wave**: 20. **Domain**: Accounting.

**Failure.**

Zero-sum double-entry verification exists only as a CLI command (`python manage.py check_invariants`). No background Celery worker continuously asserts $\sum \text{Debit} - \sum \text{Credit} = 0$.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_acc_002` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_acc_002` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-010"></a>

### BUG-ACC-010. Owner Backfill Turns Books On and Skips Payroll, Work Orders, and Bills of Entry

> **Triage 2026-10-04: CONFIRMED.** accounting/views.py:639 sets accounting_enabled=True before backfill; backfill command has no PAY_RUN/WORK_ORDER/BILL_OF_ENTRY source specs.

**Severity**: P1. **Order in wave**: 21. **Domain**: Accounting.

**Failure.**

Enable happens before a healthy posting pass. The backfill command does not cover every source that books-health later requires.

**If it stays.** "Backfill done" can leave books on with missing journals. The report looks successful while historical documents in a closed period stay unposted.

**Change.**

Post those sources before enabling books, and return skipped documents grouped by period.

**Files.**

`backend/accounting/views.py` owner backfill sets `accounting_enabled=True` before posting finishes. `backend/accounting/management/commands/backfill_accounting_postings.py` never posts `PAY_RUN`, `WORK_ORDER`, or `BILL_OF_ENTRY`. Closed-period `BusinessRuleError`s increment `skipped` with no reason list.

**Done when.**

`test_bug_acc_010` fails on today's code and passes after the change. The test shows this failure is gone: "Backfill done" can leave books on with missing journals. The report looks successful while historical documents in a closed period stay unposted.

**Test.** `test_bug_acc_010` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-006"></a>

### BUG-ACC-006. Fixed Asset Depreciation Tasks Run Without Company Scope in Bulk Updates

> **Triage 2026-10-04: CLOSED. False positive.** The `.update(pk=asset.pk)` calls (accounting/tasks.py:161-164) run inside a per-company fan-out task; pk is unique, so no cross-tenant write. No production change is needed.

**Severity**: P2. **Order in wave**: 22. **Domain**: Accounting.

**Failure.**

`FixedAsset.objects.filter(pk=asset.pk).update(last_depreciation_error=str(exc))` updates records without explicit `company=asset.company` scope in an error handler.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_acc_006` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_acc_006` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-008"></a>

### BUG-ACC-008. WDV Fixed Asset Depreciation Skips Pro-Rata Month-in-Service Proration

> **Triage 2026-10-04: CONFIRMED.** tasks.py:109-120 prorates the acquisition month for SLM only.

**Severity**: P2. **Order in wave**: 23. **Domain**: Accounting.

**Failure.**

The acquisition month proration logic in `post_monthly_depreciation` explicitly checks `if (locked.method or FixedAsset.Method.SLM) == FixedAsset.Method.SLM`. Assets depreciated under WDV (Written Down Value) bypass this branch completely.

**If it stays.** Assets acquired on the 29th or 30th of a month under WDV are charged a full 30-day depreciation expense in their initial month, violating Schedule II of the Indian Companies Act, 2013 and Section 32 of the Income Tax Act.

**Change.**

Remove the SLM-only guard and apply the `days_in_service / days_in_month` proration factor to both SLM and WDV methods for acquisition and disposal periods.

**Files.**

`backend/accounting/tasks.py`

**Done when.**

`test_bug_acc_008` fails on today's code and passes after the change. The test shows this failure is gone: Assets acquired on the 29th or 30th of a month under WDV are charged a full 30-day depreciation expense in their initial month, violating Schedule II of the Indian Companies Act, 2013 and Section 32 of the Income Tax Act.

**Test.** `test_bug_acc_008` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-015"></a>

### BUG-ACC-015. Depreciation Catch-Up Drops Months Older Than Three

> **Triage 2026-10-04: CONFIRMED.** accounting/tasks.py:32 `_MAX_CATCHUP_MONTHS = 3`.

**Severity**: P2. **Order in wave**: 24. **Domain**: Accounting.

**Failure.**

Months beyond the window are never queued. WDV proration is a separate defect, **BUG-ACC-008**.

**If it stays.** If the scheduler is down for more than three months, those older months are skipped for good.

**Change.**

Persist the skipped months, alert, and offer an explicit backfill.

**Files.**

`backend/accounting/tasks.py` (`_MAX_CATCHUP_MONTHS = 3`)

**Done when.**

`test_bug_acc_015` fails on today's code and passes after the change. The test shows this failure is gone: If the scheduler is down for more than three months, those older months are skipped for good.

**Test.** `test_bug_acc_015` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-005"></a>

### BUG-ACC-005. Round-Off Discrepancies Absorbed into Operating Expense Accounts

> **Triage 2026-10-04: CLOSED. Already fixed.** `_round_off_line` always uses account 5500, and `_account()` seeds or reactivates it; no fallback to Sales/Purchases exists. No production change is needed.

**Severity**: P2. **Order in wave**: 25. **Domain**: Accounting.

**Failure.**

Round-off suspense lines are generated, but if the round-off account (`5500`) is missing, fallback logic absorbs rounding fractions into `Sales` or `Purchases` directly.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_acc_005` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_acc_005` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-009"></a>

### BUG-ACC-009. Ineligible GST ITC Reversals and Scrap Inventory Co-Mingled into Fixed Asset Disposal P&L (Account 5600)

> **Triage 2026-10-04: CONFIRMED.** reclass_rejected_itc debits 5600 "Loss on Disposal of Assets" (services.py:456).

**Severity**: P2. **Order in wave**: 26. **Domain**: Accounting.

**Failure.**

Both `reclass_rejected_itc` (reversing ineligible purchase GST ITC) and `post_sales_return_scrap` (writing off damaged return inventory) debit account `5600` ("Loss on Disposal of Assets").

**If it stays.** Operating shrinkage and non-creditable statutory taxes are co-mingled with Capital Fixed Asset Disposals on the P&L statement, violating Schedule III reporting disclosures.

**Change.**

Post damaged inventory scrap to account `5450` ("Inventory Scrap & Shrinkage Loss") and ineligible tax reversals to `5250` ("Non-Deductible Tax Expense").

**Files.**

- `backend/accounting/services.py` (`reclass_rejected_itc`)
  - `backend/accounting/services.py` (`post_sales_return_scrap`)

**Done when.**

`test_bug_acc_009` fails on today's code and passes after the change. The test shows this failure is gone: Operating shrinkage and non-creditable statutory taxes are co-mingled with Capital Fixed Asset Disposals on the P&L statement, violating Schedule III reporting disclosures.

**Test.** `test_bug_acc_009` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-003"></a>

### BUG-ACC-003. Incomplete MCA Rule 11(g) Audit Trail Event Coverage

> **Triage 2026-10-04: PARTIAL.** masters/serializers.py audits via AuditService.log; coverage of other masters not enumerated.

**Severity**: P1. **Order in wave**: 27. **Domain**: Accounting.

**Failure.**

The cryptographic SHA-256 audit chain seals operational postings, but omits master record modifications (Customer/Supplier edits, Bank Account changes, Tax Rate updates, Role assignments).

**If it stays.** Fails statutory MCA Rule 11(g) requirements mandating that *all* accounting and operational records maintain an edit log.

**Change.**

`masters/serializers.py` already audits through `AuditService.log`. List every master model (suppliers, products, units, tax rates, price lists, accounts, bank accounts), add the missing audit calls, and add a test that fails when a new master has none.

**Files.**

`backend/core/services/audit_chain.py`

**Done when.**

`test_bug_acc_003` edits one row of each master model and finds an audit event for each.

**Test.** `test_bug_acc_003` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-004"></a>

### BUG-ACC-004. Missing Formal MCA Schedule III Taxonomy Groupings

> **Triage 2026-10-04: CONFIRMED.** accounting/reports.py:116 balance_sheet groups by account type only; no Schedule III grouping (register path reporting/financial.py does not exist).

**Severity**: P1. **Order in wave**: 28. **Domain**: Accounting.

**Failure.**

Balance Sheet and P&L statements generate generic T-shaped statements without formal MCA Schedule III taxonomy (Non-Current vs Current Assets/Liabilities, Tangible Assets, Long-Term Borrowings).

**If it stays.** Chartered Accountants cannot export statutory filings directly without manual re-grouping in Excel or Tally.

**Change.**

Map Chart of Accounts codes to formal Schedule III taxonomy categories.

**Files.**

`backend/accounting/reports.py`

**Done when.**

`test_bug_acc_004` fails on today's code and passes after the change. The test shows this failure is gone: Chartered Accountants cannot export statutory filings directly without manual re-grouping in Excel or Tally.

**Test.** `test_bug_acc_004` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-011"></a>

### BUG-ACC-011. GL Recon Offers Match Anyway, and the UI Compares Absolute Amounts

> **Triage 2026-10-04: CONFIRMED.** accounting/views.py:351 compares signed amounts; AccountingExtraPages.tsx:308-311 compares Math.abs values.

**Severity**: P1. **Order in wave**: 29. **Domain**: Accounting.

**Failure.**

The screen confirms a forced match the API always rejects. The picker uses absolute values; the API uses signed values.

**If it stays.** Opposite-sign pairs look matchable. The user confirms and still gets an error.

**Change.**

Compare signed amounts in the picker, and remove the confirm-and-proceed path unless the API grows an explicit override.

**Files.**

- `web/src/pages/phase/AccountingExtraPages.tsx` (confirm on mismatched absolute amounts, then call match)
  - `backend/accounting/views.py` `BankReconSessionViewSet.match` rejects `|je − bank| > 0.01` using signed amounts

**Done when.**

`test_bug_acc_011` fails on today's code and passes after the change. The test shows this failure is gone: Opposite-sign pairs look matchable. The user confirms and still gets an error.

**Test.** `test_bug_acc_011` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-acc-014"></a>

### BUG-ACC-014. Soft-Close Does Not Require Earlier Periods to Be Closed

> **Triage 2026-10-04: CONFIRMED.** Only `close` checks earlier_open (views.py:130-137); soft_close does not.

**Severity**: P2. **Order in wave**: 30. **Domain**: Accounting.

**Failure.**

Hard close checks `earlier_open`. Soft close does not.

**If it stays.** Later months can freeze while earlier OPEN periods still accept back-dated posts.

**Change.**

Apply the same earlier-period rule to soft-close.

**Files.**

`backend/accounting/views.py` `soft_close` versus `close`

**Done when.**

`test_bug_acc_014` fails on today's code and passes after the change. The test shows this failure is gone: Later months can freeze while earlier OPEN periods still accept back-dated posts.

**Test.** `test_bug_acc_014` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-016"></a>

### BUG-ACC-016. Books-Close Shows the First Customer's AR as the Control Total

> **Triage 2026-10-04: CONFIRMED.** BooksCloseSection.tsx:34 uses `customers[0]`.

**Severity**: P2. **Order in wave**: 31. **Domain**: Accounting.

**Failure.**

The widget uses `customers[0]` and labels it beside the trial-balance match.

**If it stays.** The checklist can look healthy or broken based on one party, not control AR.

**Change.**

Show the AR control total, or the docs-versus-GL alert, not `customers[0]`.

**Files.**

`web/src/pages/phase/BooksCloseSection.tsx`

**Done when.**

`test_bug_acc_016` fails on today's code and passes after the change. The test shows this failure is gone: The checklist can look healthy or broken based on one party, not control AR.

**Test.** `test_bug_acc_016` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-acc-012"></a>

### BUG-ACC-012. Year Close and Books Health Still Demand Work Orders When Manufacturing Is Off

> **Triage 2026-10-04: CONFIRMED.** accounting/reports.py:413-417 blocks year close on RELEASED work orders with no ENABLE_MANUFACTURING check.

**Severity**: P2. **Order in wave**: 32. **Domain**: Accounting.

**Failure.**

Year close and health do not use the same feature-flag gate as period close.

**If it stays.** A stale work order prevents year close, or soft/hard close stays blocked, for a tenant with manufacturing off.

**Change.**

Include work orders only when manufacturing is enabled.

**Files.**

`backend/accounting/reports.py` year close always blocks on `WorkOrder.RELEASED`. Period close gates that check on `ENABLE_MANUFACTURING`. `backend/accounting/services.py` books health includes work orders in missing postings with no flag.

**Done when.**

`test_bug_acc_012` fails on today's code and passes after the change. The test shows this failure is gone: A stale work order prevents year close, or soft/hard close stays blocked, for a tenant with manufacturing off.

**Test.** `test_bug_acc_012` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-017"></a>

### BUG-ACC-017. Payments Recon and GL Recon Are Two Screens With Different Match Meanings

> **Triage 2026-10-04: CONFIRMED.** Two separate recon screens (payments and accounting); no cross-link verified.

**Severity**: P2. **Order in wave**: 33. **Domain**: Accounting.

**Failure.**

One screen matches receipts and payments. The other matches a GL line to a statement line. Neither shows the other match.

**If it stays.** An operator can believe the bank is reconciled and still see unmatched lines on the other screen.

**Change.**

Cross-link both screens and label which match each row has.

**Files.**

`/payments/reconciliation` versus `/accounting/bank-reconciliation`. Copy in the English catalog notes that they differ.

**Ships with.** Labels and cross-links only. Auto-apply of a unique match is BUG-COG-017.

**Done when.**

`test_bug_acc_017` fails on today's code and passes after the change. The test shows this failure is gone: An operator can believe the bank is reconciled and still see unmatched lines on the other screen.

**Test.** `test_bug_acc_017` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-018"></a>

### BUG-ACC-018. Dispose Fixed Asset Posts With No Confirmation

> **Triage 2026-10-04: CONFIRMED.** FixedAssetsPage.tsx:124 calls dispose.mutate directly.

**Severity**: P2. **Order in wave**: 34. **Domain**: Accounting.

**Failure.**

Dispose calls the mutation on click. Journals and periods use a confirm dialog. Other destructive confirms are **BUG-UI-005** and **BUG-UI-025**.

**If it stays.** An accidental click posts an irreversible disposal.

**Change.**

Confirm with net book value and proceeds before dispose.

**Files.**

`web/src/pages/phase/FixedAssetsPage.tsx`

**Done when.**

`test_bug_acc_018` fails on today's code and passes after the change. The test shows this failure is gone: An accidental click posts an irreversible disposal.

**Test.** `test_bug_acc_018` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-sales-014"></a>

### BUG-SALES-014. Sales History Paid / Partial / Unpaid Ignores Reversed Receipts and Credit Notes

> **Triage 2026-10-04: CONFIRMED.** sales/views.py:217-236 allocation subquery lacks reversed_at filter (the list annotation at line 160 has it).

**Severity**: P1. **Order in wave**: 35. **Domain**: Sales.

**Failure.**

The filter sums `PaymentAllocation` rows for posted receipts and compares them to `grand_total`. It does not exclude `reversed_at`. The list annotation near line 160 does exclude reversed rows. Credit notes are ignored, so a fully credited invoice still looks unpaid.

**If it stays.** Voided receipts still look paid. Relieved invoices still look unpaid.

**Change.**

Filter on live outstanding, and exclude allocations with `reversed_at` set.

**Files.**

`backend/sales/views.py`

**Done when.**

`test_bug_sales_014` fails on today's code and passes after the change. The test shows this failure is gone: Voided receipts still look paid. Relieved invoices still look unpaid.

**Test.** `test_bug_sales_014` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-003"></a>

### BUG-SALES-003. Driver COD & UPI Route Collections Unreconciled Against Cashier Drawer

> **Triage 2026-10-04: CONFIRMED.** No cashier handover step in complete_route; `DriverPaymentReceipt` does not exist in the codebase.

**Severity**: P1. **Order in wave**: 36. **Domain**: Sales.

**Failure.**

Delivery routes complete without requiring a cashier handover session. Cash collected on the road by delivery drivers never posts to a `DriverPaymentReceipt` or reconciles against physical till balances.

**If it stays.** Cash collected by drivers sits in operational limbo without financial accountability.

**Change.**

Require cashier verification of physical cash and UPI reference settlements before allowing a delivery route to transition to `CLOSED`.

**Files.**

`backend/sales/route_service.py` (`complete_route`)

**Done when.**

`test_bug_sales_003` fails on today's code and passes after the change. The test shows this failure is gone: Cash collected by drivers sits in operational limbo without financial accountability.

**Test.** `test_bug_sales_003` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-004"></a>

### BUG-SALES-004. Insecure Proof of Delivery (POD) Accepts Unverified Arbitrary OTPs

> **Triage 2026-10-04: CONFIRMED.** set_stop_status stores otp_code and never validates it against an issued OTP.

**Severity**: P1. **Order in wave**: 37. **Domain**: Sales.

**Failure.**

The POD completion action accepts arbitrary user-supplied digits for `otp` without validating against an active OTP record. Geo-coordinates are completely optional and unverified.

**If it stays.** Delivery personnel can falsely mark deliveries as complete without customer consent.

**Change.**

Implement cryptographically secure OTP generation dispatched via SMS/WhatsApp with verification against the server secret before marking stops `DELIVERED`.

**Files.**

`backend/sales/route_service.py` (`complete_pod`)

**Done when.**

`test_bug_sales_004` fails on today's code and passes after the change. The test shows this failure is gone: Delivery personnel can falsely mark deliveries as complete without customer consent.

**Test.** `test_bug_sales_004` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-006"></a>

### BUG-SALES-006. Sales Margin Guard Warning Fails to Block Below-Cost Selling

> **Triage 2026-10-04: CONFIRMED.** order_gates only builds margin_warnings; no block or override path found. Plan already drops the crypto-token idea.

**Severity**: P1. **Order in wave**: 38. **Domain**: Sales.

**Failure.**

Margin calculation only emits an informational warning during order creation. It does not enforce a floor price or block below-cost invoice billing.

**If it stays.** Counter clerks and sales reps can bill goods below purchase cost without manager authorization.

**Change.**

Block completion of below-cost invoices unless a cryptographically signed owner override token is provided.

**Files.**

`backend/sales/order_gates.py` (`margin_warning`)

**Done when.**

`test_bug_sales_006` fails on today's code and passes after the change. The test shows this failure is gone: Counter clerks and sales reps can bill goods below purchase cost without manager authorization.

**Test.** `test_bug_sales_006` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-019"></a>

### BUG-SALES-019. Portal Complaint List Is Unbounded

> **Triage 2026-10-04: CONFIRMED.** portal_views.py:332 complaint query is unsliced.

**Severity**: P2. **Order in wave**: 39. **Domain**: Sales.

**Failure.**

The complaint query orders by `-id` and does not slice. The portal invoice list is capped.

**If it stays.** A busy customer token can return an unbounded payload. Broader unpaginated APIs are **BUG-SEC-005**.

**Change.**

Cap or paginate the portal complaint list.

**Files.**

`backend/payments/portal_views.py`

**Done when.**

`test_bug_sales_019` fails on today's code and passes after the change. The test shows this failure is gone: A busy customer token can return an unbounded payload. Broader unpaginated APIs are **BUG-SEC-005**.

**Test.** `test_bug_sales_019` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-020"></a>

### BUG-SALES-020. Portal PDF Allows Draft and Cancelled Invoices for That Customer

> **Triage 2026-10-04: CONFIRMED.** portal_views.py:262-267 PDF lookup has no status filter.

**Severity**: P3. **Order in wave**: 40. **Domain**: Sales.

**Failure.**

The PDF lookup filters by company, customer, and primary key, with no status gate.

**If it stays.** A customer token can fetch a draft or cancelled invoice that the portal list would not show.

**Change.**

Restrict the PDF to the same statuses as the portal list.

**Files.**

`backend/payments/portal_views.py`

**Done when.**

`test_bug_sales_020` fails on today's code and passes after the change. The test shows this failure is gone: A customer token can fetch a draft or cancelled invoice that the portal list would not show.

**Test.** `test_bug_sales_020` in `backend/tests/test_bug_register.py`.

<a id="bug-sales-021"></a>

### BUG-SALES-021. Partial Returns Consume the Same SKU in Line Order

> **Triage 2026-10-04: CONFIRMED.** return_service.py:107-146 consumes remaining quantity keyed by product in line order.

**Severity**: P3. **Order in wave**: 41. **Domain**: Sales.

**Failure.**

Remaining quantity is keyed by `product_id` and consumed in line order. Credit notes can name the source line. Returns do not.

**If it stays.** Two lines of the same product at different rates can return against the wrong line.

**Change.**

Require `source_item` on return lines and consume that line.

**Files.**

`backend/sales/return_service.py`

**Done when.**

`test_bug_sales_021` fails on today's code and passes after the change. The test shows this failure is gone: Two lines of the same product at different rates can return against the wrong line.

**Test.** `test_bug_sales_021` in `backend/tests/test_bug_register.py`.

<a id="bug-pay-001"></a>

### BUG-PAY-001. Cheque Bounce Fails to Levy Dishonour Fees or Generate Section 138 Notice

> **Triage 2026-10-04: CONFIRMED.** Cheque bounce only voids the receipt (payments/services.py:670); no fee or s.138 notice. (Duplicate ID: payments.)

**Severity**: P0. **Order in wave**: 42. **Domain**: Payments.

**Failure.**

When a cheque bounces, the service voids the receipt and re-opens the invoices. However, it does not debit bank penalty charges to the customer, reverse early payment discounts, or generate a Section 138 Negotiable Instruments Act statutory legal notice.

**If it stays.** Businesses absorb bank cheque bounce charges; the 30-day statutory notice clock under Section 138 is missed, forfeiting criminal legal recourse.

**Change.**

Automatically post a debit note for bank penalty charges, reverse cash discounts, and generate a standardized Section 138 Demand Notice PDF.

**Files.**

`backend/payments/services.py` (`dishonour_cheque`)

**Done when.**

`test_bug_pay_001` fails on today's code and passes after the change. The test shows this failure is gone: Businesses absorb bank cheque bounce charges; the 30-day statutory notice clock under Section 138 is missed, forfeiting criminal legal recourse.

**Test.** `test_bug_pay_001` in `backend/tests/test_bug_register.py`.

<a id="bug-pay-006"></a>

### BUG-PAY-006. Ambiguous Fuzzy Substring UTR Matching Silently Binds Unrelated Customer Receipts

> **Triage 2026-10-04: PARTIAL.** `utr__icontains` in banking/services.py:100 and substring match in payments/recon.py:485; confirm auto-bind behaviour.

**Severity**: P1. **Order in wave**: 43. **Domain**: Payments.

**Failure.**

The UTR reference query uses `Q(reference__icontains=r) | Q(utr__icontains=r)`. When multiple receipts match a partial substring, `_rank_receipts` picks `ranked[0]` unconditionally without checking if `len(ranked) == 1`.

**If it stays.** An AA transaction with a common numeric substring ref silently links to an unrelated customer's receipt, misallocating bank reconciliation credit.

**Change.**

Replace `utr__icontains` in `banking/services.py` and the substring match in `payments/recon.py` with an exact match on a normalised UTR. A partial hit may suggest a match; it never auto-binds a receipt.

**Files.**

`backend/banking/services.py`

**Done when.**

`test_bug_pay_006` shows a bank row whose narration merely contains a shorter UTR does not bind to that receipt.

**Test.** `test_bug_pay_006` in `backend/tests/test_bug_register.py`.

<a id="bug-pay-007"></a>

### BUG-PAY-007. Account Aggregator Can Attach Two Bank Rows to One Receipt

> **Triage 2026-10-04: CONFIRMED.** AaTransaction.matched_payment is a plain FK with no unique constraint (banking/models.py:39).

**Severity**: P1. **Order in wave**: 44. **Domain**: Payments.

**Failure.**

The matcher locks the receipt and writes `matched_payment` without checking that another AA row already points at it. Substring UTR collisions remain **BUG-PAY-006**. Debit matching remains **BUG-PAY-005**.

**If it stays.** Cash operations trust a match that is not unique.

**Change.**

After `select_for_update`, refuse the match if another `AaTransaction` already points at that receipt, and add a partial unique constraint on `matched_payment`.

**Files.**

`backend/banking/services.py` AA match. `AaTransaction.matched_payment` in `backend/banking/models.py` has no uniqueness constraint.

**Done when.**

`test_bug_pay_007` fails on today's code and passes after the change. The test shows this failure is gone: Cash operations trust a match that is not unique.

**Test.** `test_bug_pay_007` in `backend/tests/test_bug_register.py`.

<a id="bug-pay-008"></a>

### BUG-PAY-008. Re-Ingesting Bank Rows Overwrites Amounts That Are Already Matched

> **Triage 2026-10-04: CONFIRMED.** banking/views.py:174-185 overwrites amount, txn_date and raw on existing rows regardless of matched_payment.

**Severity**: P1. **Order in wave**: 45. **Domain**: Payments.

**Failure.**

`bulk_update` rewrites `amount`, `txn_date`, and `raw` for existing `txn_id`s, including rows with `matched_payment_id` set.

**If it stays.** A later FIU or client ingest changes the amount under a receipt link and does not clear the match.

**Change.**

Skip amount and date updates when `matched_payment_id` is set, or unmatch first.

**Files.**

`backend/banking/views.py` AA bulk update

**Done when.**

`test_bug_pay_008` fails on today's code and passes after the change. The test shows this failure is gone: A later FIU or client ingest changes the amount under a receipt link and does not clear the match.

**Test.** `test_bug_pay_008` in `backend/tests/test_bug_register.py`.

<a id="bug-pay-005"></a>

### BUG-PAY-005. Account Aggregator (AA) Auto-Reconciliation Completely Ignores Debit Transactions

> **Triage 2026-10-04: CONFIRMED.** match_aa_to_receipts filters amount__gt=0 and CustomerReceipt only.

**Severity**: P1. **Order in wave**: 46. **Domain**: Payments.

**Failure.**

`match_aa_to_receipts` filters strictly by `amount__gt=0` and only queries against `CustomerReceipt`. There is no matching pipeline or rules engine for bank debits (`amount__lt=0`), such as supplier payments, payroll disbursements, bank charges, or GST challan debits.

**If it stays.** 100% of outbound bank payments fail to auto-reconcile, forcing accountants to manually key journal voucher lines for all banking debits.

**Change.**

Implement `match_aa_to_payments` pairing debit AA transactions with `PaymentVoucher` / `Expense` records by reference/UTR or amount+date.

**Files.**

- `backend/banking/services.py` (`_match_one`)
  - `backend/banking/services.py` (`match_aa_to_receipts`)

**Done when.**

`test_bug_pay_005` fails on today's code and passes after the change. The test shows this failure is gone: 100% of outbound bank payments fail to auto-reconcile, forcing accountants to manually key journal voucher lines for all banking debits.

**Test.** `test_bug_pay_005` in `backend/tests/test_bug_register.py`.

<a id="bug-pay-002"></a>

### BUG-PAY-002. Account Aggregator (AA) Consent Expiration Not Handled Gracefully

> **Triage 2026-10-04: PARTIAL.** FIU fetch fails closed with BusinessRuleError (fiu_adapter.py:~85); EXPIRED/REVOKED statuses exist but no transition or notification on expiry.

**Severity**: P1. **Order in wave**: 47. **Domain**: Payments.

**Failure.**

When an Account Aggregator consent token expires or is revoked by the bank, background bank statement synchronization crashes with an unhandled exception rather than transitioning consent to `EXPIRED` and notifying the accountant.

**If it stays.** Background banking sync tasks fail repeatedly without alerting the user to re-authenticate.

**Change.**

Fail-closed already holds (the live fetch raises a business-rule error). Add the missing state change: when the FIU rejects a consent as expired or revoked, set the consent to `EXPIRED` or `REVOKED` (both statuses exist in `banking/models.py`) and notify the accountant.

**Files.**

`backend/banking/fiu_adapter.py`

**Done when.**

`test_bug_pay_002` simulates an expired-consent response and sees the consent status change and one notification.

**Test.** `test_bug_pay_002` in `backend/tests/test_bug_register.py`.

<a id="bug-pay-003"></a>

### BUG-PAY-003. Bank Reconciliation Auto-Matching Engine Missing Fuzzy Narration Rules

> **Triage 2026-10-04: CONFIRMED.** banking/services.py matches by UTR/ref and unique amount+date only; no narration/party fuzzy rules.

**Severity**: P1. **Order in wave**: 48. **Domain**: Payments.

**Failure.**

Bank reconciliation matches exclusively on exact amounts and exact reference strings. Fuzzy narration matching (e.g. matching `NEFT-CMS-INFOSYS-1234` to `Infosys Ltd`) is not supported.

**If it stays.** Accountants must manually reconcile 80%+ of imported bank transactions one by one.

**Change.**

Implement a rule-based fuzzy matching engine matching on extracted party names, UTR numbers, and amount proximity.

**Files.**

`backend/banking/services.py`

**Done when.**

`test_bug_pay_003` fails on today's code and passes after the change. The test shows this failure is gone: Accountants must manually reconcile 80%+ of imported bank transactions one by one.

**Test.** `test_bug_pay_003` in `backend/tests/test_bug_register.py`.

<a id="bug-pay-009"></a>

### BUG-PAY-009. Live FIU Ingest Trusts JSON After Bearer Auth

> **Triage 2026-10-04: CONFIRMED.** fiu_adapter live fetch trusts JSON after bearer auth; signature verification is only a gated stub (B4-020).

**Severity**: P2. **Order in wave**: 49. **Domain**: Payments.

**Failure.**

The live helper accepts HTTP JSON after bearer auth. The ReBIT client is separately fail-closed and is not the path this ingest uses.

**If it stays.** A compromised FIU URL or an unsigned payload can inject bank rows.

**Change.**

Route live ingest through signature-verified ReBIT decrypt, or refuse live mode until verification exists.

**Files.**

`backend/banking/fiu_adapter.py` `fetch_live_transactions_for_consent`, called from `backend/banking/views.py`. Consent-expiry handling is **BUG-PAY-002**.

**Done when.**

`test_bug_pay_009` fails on today's code and passes after the change. The test shows this failure is gone: A compromised FIU URL or an unsigned payload can inject bank rows.

**Test.** `test_bug_pay_009` in `backend/tests/test_bug_register.py`.

<a id="bug-inv-003"></a>

### BUG-INV-003. Blind Stocktake & Physical Cycle Counting Sessions Absent

> **Triage 2026-10-04: PARTIAL.** `StockCountSession` exists; only "blind" counting is unconfirmed. Retitle.

**Severity**: P1. **Order in wave**: 50. **Domain**: Inventory.

**Failure.**

Adjustments exist only as manual one-off entries. There is no structured "Blind Stock Counting Session" where warehouse auditors submit physical counts without seeing system quantities.

**If it stays.** Warehouse physical audits suffer from confirmation bias and unmonitored shrinkage.

**Change.**

Retitle to "Blind count mode". `StockCountSession` (DRAFT, COUNTED, posted) already exists with variance review. Add a `blind` option that hides expected quantity from the counter screen and reveals it at review. Skip this item if the founder does not want blind counts.

**Files.**

`backend/inventory/views.py`

**Done when.**

`test_bug_inv_003` shows that a blind session never returns expected quantity to the counter endpoint and that review still shows variance.

**Test.** `test_bug_inv_003` in `backend/tests/test_bug_register.py`.

## Wave 5. Vertical modules

Fix routes and validation before new fields. A won deal requires a customer before a lead can hand off to a quotation. Payroll bank selection and statutory floors are independent of CRM. Manufacturing WIP posting follows the cycle check on the BOM, so a cyclic BOM never posts.

<a id="bug-prj-002"></a>

### BUG-PRJ-002. Frontend Milestone Invoicing Opens a Route That Does Not Exist

> **Triage 2026-10-04: CONFIRMED.** ProjectsPage.tsx:77 navigates to /sales/invoices/:id; App.tsx registers sales/history/:id only.

**Severity**: P1. **Order in wave**: 1. **Domain**: Projects.

**Failure.**

After invoice, the page finds the clicked milestone and navigates to `/sales/invoices/${salesInvoice}`. `web/src/App.tsx` registers invoice detail at `sales/history/:id` only. An earlier note that the page opened the first invoice on the project is stale: the find is by milestone id.

**If it stays.** The operator lands on Not Found instead of the draft invoice. Job cards have the same missing route, filed as **BUG-WRK-006**.

**Change.**

Navigate to `/sales/history/${id}`.

**Files.**

`web/src/pages/projects/ProjectsPage.tsx`

**Ships with.** Same route fix as the success path in BUG-WRK-006: `/sales/history/:id`.

**Done when.**

`test_bug_prj_002` fails on today's code and passes after the change. The test shows this failure is gone: The operator lands on Not Found instead of the draft invoice. Job cards have the same missing route, filed as **BUG-WRK-006**.

**Test.** `test_bug_prj_002` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-prj-004"></a>

### BUG-PRJ-004. A Project Can Close While Planned Milestones Are Still Unbilled

> **Triage 2026-10-04: CONFIRMED.** close_project checks READY milestones only (projects/services.py:133).

**Severity**: P2. **Order in wave**: 2. **Domain**: Projects.

**Failure.**

The unbilled check filters `status=READY` and `sales_invoice` null. `PLANNED` milestones are ignored. Draft-invoice revenue posting is **BUG-PRJ-001**.

**If it stays.** The project closes while planned work is never billed.

**Change.**

Block close on any milestone that is not invoiced or cancelled.

**Files.**

`backend/projects/services.py` `close_project`

**Done when.**

`test_bug_prj_004` fails on today's code and passes after the change. The test shows this failure is gone: The project closes while planned work is never billed.

**Test.** `test_bug_prj_004` in `backend/tests/test_bug_register.py`.

<a id="bug-prj-003"></a>

### BUG-PRJ-003. Unhandled ValueError / 500 Crashes on Invalid Input

> **Triage 2026-10-04: PARTIAL.** The milestones action now catches int() ValueError (projects/views.py:57-60). Other actions not individually re-checked.

**Severity**: P2. **Order in wave**: 3. **Domain**: Projects.

**Failure.**

Actions parse raw `request.data` directly using `int()` without DRF serializers or `get_object_or_404`. Invalid input raises unhandled `ValueError`.

**If it stays.** Malformed client requests crash with HTTP 500 instead of clean HTTP 400 validation errors.

**Change.**

The milestones action already catches a bad `sequence`. Review the other actions in `projects/views.py` for bare `int()` or `Decimal()` on `request.data` and route each through a serializer or `get_object_or_404`.

**Files.**

`backend/projects/views.py`

**Done when.**

`test_bug_prj_003` posts non-numeric ids and amounts to each project action and receives a 400 or 404, never a 500.

**Test.** `test_bug_prj_003` in `backend/tests/test_bug_register.py`.

<a id="bug-ui-001"></a>

### BUG-UI-001. Form State Leaks Across Multiple Projects in UI

> **Triage 2026-10-04: CLOSED. Already fixed.** ProjectsPage.tsx now keeps milestone drafts in a per-project map (`drafts[projectKey]`). No production change is needed.

**Severity**: P1. **Order in wave**: 4. **Domain**: Web and hardware.

**Failure.**

Milestone inputs were previously bound to top-level page state rather than isolated per project card.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_ui_001` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_ui_001` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-017"></a>

### BUG-UI-017. Missing Milestone Editing, Due Dates, and Closing Confirmation in Projects

> **Triage 2026-10-04: CONFIRMED.** ProjectsPage.tsx has no confirm, due-date or milestone-edit code.

**Severity**: P2. **Order in wave**: 5. **Domain**: Web and hardware.

**Failure.**

In `ProjectsPage`:
  1. The "Close Project" button updates project status immediately without a confirmation prompt, even if milestones remain unbilled.
  2. Milestones render only name and status; target completion dates and milestone contract values are missing.
  3. There is no UI action to edit milestone details or delete an incorrectly added milestone prior to billing.

**If it stays.** Project managers cannot track timeline adherence or commercial milestone values, and accidental clicks immediately close projects prematurely.

**Change.**

1. Add a confirmation modal to "Close Project" checking for unbilled completed milestones.
  2. Enrich milestone cards with `amount` and `target_completion_date`.
  3. Add edit and delete action buttons to pending milestones.

**Files.**

- `web/src/pages/projects/ProjectsPage.tsx` ("Close Project" button)
  - `web/src/pages/projects/ProjectsPage.tsx` (Milestone cards)

**Done when.**

`test_bug_ui_017` fails on today's code and passes after the change. The test shows this failure is gone: Project managers cannot track timeline adherence or commercial milestone values, and accidental clicks immediately close projects prematurely.

**Test.** `test_bug_ui_017` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ins-002"></a>

### BUG-INS-002. 30-Day Month Formula Corrupts Policy Expiration Dates

> **Triage 2026-10-04: CLOSED. Already fixed.** `add_calendar_months` exists (insurance/services.py:27); no 30-day math found. No production change is needed.

**Severity**: P1. **Order in wave**: 6. **Domain**: Insurance.

**Failure.**

```python
end_date = start_date + timedelta(days=tenure_months * 30)
```
Hardcodes every month to 30 days. A 12-month policy beginning January 1, 2026 ends December 27, 2026 (5 days early).

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_ins_002` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_ins_002` in `backend/tests/test_bug_register.py`.

<a id="bug-ins-003"></a>

### BUG-INS-003. Unvalidated Negative Insurance Commission Receivables

> **Triage 2026-10-04: CLOSED. Already fixed.** `parse_commission_amount` rejects amounts <= 0. No production change is needed.

**Severity**: P1. **Order in wave**: 7. **Domain**: Insurance.

**Failure.**

Custom view action accepts raw `amount` without serializer validation. Negative numbers and arbitrary strings are accepted without checking for $amount > 0$.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_ins_003` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_ins_003` in `backend/tests/test_bug_register.py`.

<a id="bug-ins-005"></a>

### BUG-INS-005. Insurance Can Issue a Policy and Cannot Run Claims, Renewals, or Commission Receipt

> **Triage 2026-10-04: CLOSED. Already fixed.** `open_claim`, `renewal_diary`, `open_commission` all exist in insurance/services.py. No production change is needed.

**Severity**: P1. **Order in wave**: 8. **Domain**: Insurance.

**Failure.**

The screen covers products, options, and issue. Endorse, cancel, claim, commission, KYC, and renewal diary exist on the backend (or as models) and are not called from the page. Nothing in services moves commission to `RECEIVED`. Duplicate issue is **BUG-INS-001**. Date math is **BUG-INS-002**. Negative commission is **BUG-INS-003**. Renewal races are **BUG-INS-004**.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_ins_005` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_ins_005` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-wrk-003"></a>

### BUG-WRK-003. Unvalidated Negative Quantities and Pricing on Job Lines

> **Triage 2026-10-04: CONFIRMED.** workshop/views.py:69-70 passes request.data quantity/unit_price; add_line shows no sign check.

**Severity**: P2. **Order in wave**: 9. **Domain**: Workshop.

**Failure.**

`JobCardViewSet.lines` takes `request.data.get("quantity")` and `unit_price` without schema validation, allowing negative quantities or rates to be stored in the database.

**If it stays.** Distorts job card totals and allows unauthorized discounts or credits.

**Change.**

Validate line payloads using `JobCardLineSerializer` with positive decimal constraints.

**Files.**

`backend/workshop/views.py`

**Done when.**

`test_bug_wrk_003` fails on today's code and passes after the change. The test shows this failure is gone: Distorts job card totals and allows unauthorized discounts or credits.

**Test.** `test_bug_wrk_003` in `backend/tests/test_bug_register.py`.

<a id="bug-wrk-004"></a>

### BUG-WRK-004. Job Card Has No Mechanic Commission or Labour Time Tracking

> **Triage 2026-10-04: CONFIRMED.** workshop/models.py has no commission or labour timer fields.

**Severity**: P2. **Order in wave**: 10. **Domain**: Workshop.

**Failure.**

Job cards assign a technician, but have no start/stop labor timers or mechanic commission rates.

**If it stays.** Workshop owners cannot track technician productivity or compute commission payouts.

**Change.**

Add `labour_minutes` and `technician_commission_percent` to `JobCardLine`.

**Files.**

`backend/workshop/models.py`

**Done when.**

`test_bug_wrk_004` fails on today's code and passes after the change. The test shows this failure is gone: Workshop owners cannot track technician productivity or compute commission payouts.

**Test.** `test_bug_wrk_004` in `backend/tests/test_bug_register.py`.

<a id="bug-wrk-005"></a>

### BUG-WRK-005. Absence of Service Bay Allocation & Workshop Scheduling

> **Triage 2026-10-04: CONFIRMED.** No service-bay model.

**Severity**: P3. **Order in wave**: 11. **Domain**: Workshop.

**Failure.**

No service bay model exists; job cards cannot be scheduled by bay or lift capacity.

**If it stays.** Workshop service advisors cannot prevent bay overbooking.

**Change.**

Implement a `ServiceBay` entity with scheduling conflict detection.

**Files.**

`backend/workshop/models.py`

**Done when.**

`test_bug_wrk_005` fails on today's code and passes after the change. The test shows this failure is gone: Workshop service advisors cannot prevent bay overbooking.

**Test.** `test_bug_wrk_005` in `backend/tests/test_bug_register.py`.

<a id="bug-ui-013"></a>

### BUG-UI-013. Workshop Job Cards Module Lacks Real-World Work Order Attributes

> **Triage 2026-10-04: CONFIRMED.** JobCardsPage.tsx state is customer + complaint only; no vehicle, odometer, technician or lines.

**Severity**: P1. **Order in wave**: 12. **Domain**: Web and hardware.

**Failure.**

The current `JobCardsPage` is an MVP skeleton containing only `customerId` and a free-text `complaint` field. It omits essential automotive/device workshop attributes: Vehicle/Asset Registration Number, VIN/Chassis/IMEI, Odometer Reading / Hours Run, Assigned Service Technician, Billable Spare Parts line items, and Labour/Service charge line items.

**If it stays.** Service centers and vehicle workshops cannot use the module for operational repairs or generate itemized workshop repair estimates/invoices.

**Change.**

Expand `JobCardsPage` and backend `JobCard` model to include:
  1. Asset metadata: `registration_no`, `model`, `odometer_reading`.
  2. Assigned technician / mechanic ID.
  3. Child line tables for Parts Requisitioned (linking to inventory stock deduction) and Labour Charges (with GST).
  4. One-click "Convert to Invoice" action.

**Files.**

`web/src/pages/workshop/JobCardsPage.tsx`

**Done when.**

`test_bug_ui_013` fails on today's code and passes after the change. The test shows this failure is gone: Service centers and vehicle workshops cannot use the module for operational repairs or generate itemized workshop repair estimates/invoices.

**Test.** `test_bug_ui_013` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-mfg-006"></a>

### BUG-MFG-006. Multi-Level BOM Explosion Infinite Recursion (Lack of Cyclic Dependency Validation)

> **Triage 2026-10-04: CONFIRMED.** No cycle detection found in manufacturing/.

**Severity**: P1. **Order in wave**: 13. **Domain**: Manufacturing, payroll, contracts, complaints.

**Failure.**

`BomSerializer` only checks 1-hop direct self-reference (`component == finished_good`). It does not perform a topological sort or depth-first search for multi-hop cyclic graphs (e.g., Finished Good A requires Sub-assembly B, and Sub-assembly B requires Finished Good A).

**If it stays.** Creating circular sub-assemblies triggers unbounded recursion (RecursionError) or worker thread lockups during multi-level BOM explosion, MRP planning, and standard cost roll-ups.

**Change.**

Implement a cycle-detection DFS helper before saving BOM lines in `BomSerializer.validate()`: traverse component BOM trees and raise `ValidationError` if any downstream child path refers back to the root product.

**Files.**

- `backend/manufacturing/serializers.py` (`BomSerializer.create`)
  - `backend/manufacturing/serializers.py` (`BomSerializer.update`)
  - `backend/manufacturing/services.py`

**Done when.**

`test_bug_mfg_006` fails on today's code and passes after the change. The test shows this failure is gone: Creating circular sub-assemblies triggers unbounded recursion (RecursionError) or worker thread lockups during multi-level BOM explosion, MRP planning, and standard cost roll-ups.

**Test.** `test_bug_mfg_006` in `backend/tests/test_bug_register.py`.

<a id="bug-mfg-001"></a>

### BUG-MFG-001. Component Issuance Skips General Ledger Work-in-Progress (WIP) Account

> **Triage 2026-10-04: PARTIAL.** WIP posting is optional per module docstring; confirm the default.

**Severity**: P1. **Order in wave**: 14. **Domain**: Manufacturing, payroll, contracts, complaints.

**Failure.**

While WIP account `1450` exists in the chart of accounts, releasing work orders does not post an interim journal debiting WIP and crediting Raw Materials. Inventory is only netted at final completion.

**If it stays.** Mid-month financial statements overstate raw materials and understate work-in-progress inventory.

**Change.**

Confirm the default of the optional WIP posting setting in `manufacturing/services.py`. If it defaults off, post component issue to the WIP account whenever accounting is enabled, and keep the setting only as an opt-out for tenants without books.

**Files.**

`backend/accounting/services.py` (`post_work_order_release`)

**Done when.**

`test_bug_mfg_001` issues components on a books-on company and finds a WIP journal line.

**Test.** `test_bug_mfg_001` in `backend/tests/test_bug_register.py`.

<a id="bug-prl-003"></a>

### BUG-PRL-003. Payroll Disbursement Defaults to Cash Without Bank Account Selection

> **Triage 2026-10-04: CONFIRMED.** complete_pay_run has a `pay_from_cash=True` parameter only; no bank account selection. (Duplicate ID: payroll.)

**Severity**: P1. **Order in wave**: 15. **Domain**: Manufacturing, payroll, contracts, complaints.

**Failure.**

```python
credit_acct = PostingService._account(company, "1100" if pay_from_cash else "2150")
```
  `complete_pay_run` offers only physical cash (`1100`) or wages payable (`2150`). It does not allow the accountant to select a specific Bank Account (`1500`) for direct NEFT/RTGS salary disbursement.

**If it stays.** Paying salaries pushes the physical cash drawer into massive negative balances; bank balances are unaffected.

**Change.**

Add a `bank_account_id` parameter to `complete_pay_run` allowing direct bank ledger crediting.

**Files.**

`backend/payroll/services.py`

**Done when.**

`test_bug_prl_003` fails on today's code and passes after the change. The test shows this failure is gone: Paying salaries pushes the physical cash drawer into massive negative balances; bank balances are unaffected.

**Test.** `test_bug_prl_003` in `backend/tests/test_bug_register.py`.

<a id="bug-prl-004"></a>

### BUG-PRL-004. Payroll Engine Cannot Process Advances, Arrears, or Bonus Lines

> **Triage 2026-10-04: CONFIRMED.** payroll/services.py:437-445 documents this limitation (B9-036). (Duplicate ID: payroll.)

**Severity**: P1. **Order in wave**: 16. **Domain**: Manufacturing, payroll, contracts, complaints.

**Failure.**

The pay run service accepts only `paid_days` and prorates basic salary. There is no line-item schema for salary advances, overtime, arrears, or performance bonuses.

**If it stays.** Companies cannot run real-world monthly payroll without manual offline adjustments.

**Change.**

Build an `EarningDeductionLine` schema on `PaySlip` supporting custom components.

**Files.**

`backend/payroll/services.py`

**Done when.**

`test_bug_prl_004` fails on today's code and passes after the change. The test shows this failure is gone: Companies cannot run real-world monthly payroll without manual offline adjustments.

**Test.** `test_bug_prl_004` in `backend/tests/test_bug_register.py`.

<a id="bug-prl-001"></a>

### BUG-PRL-001. PF Admin Charge Floor of Rs 500 Is Defined and Never Applied

> **Triage 2026-10-04: CONFIRMED.** PF_ADMIN_MIN_ESTABLISHMENT defined at payroll/services.py:27 and used nowhere else.

**Severity**: P2. **Order in wave**: 17. **Domain**: Manufacturing, payroll, contracts, complaints.

**Failure.**

The floor constant is unused. Admin charges are only half a percent of wages. Bank selection on disbursement is **BUG-PRL-003** in this section. Arrears and bonus lines are **BUG-PRL-004**.

**If it stays.** An establishment under the floor under-accrues PF admin charges.

**Change.**

Floor the establishment total at Rs 500 when any PF wages exist.

**Files.**

`backend/payroll/services.py` (`PF_ADMIN_MIN_ESTABLISHMENT` versus `wage_base * 0.5%` only)

**Done when.**

`test_bug_prl_001` fails on today's code and passes after the change. The test shows this failure is gone: An establishment under the floor under-accrues PF admin charges.

**Test.** `test_bug_prl_001` in `backend/tests/test_bug_register.py`.

<a id="bug-prl-002"></a>

### BUG-PRL-002. ESI Stops the Month Wages Cross the Ceiling

> **Triage 2026-10-04: CONFIRMED.** ESI test is per month: `gross_full <= esi_ceiling` (services.py:367).

**Severity**: P2. **Order in wave**: 18. **Domain**: Manufacturing, payroll, contracts, complaints.

**Failure.**

Each month is tested on its own. There is no record that the employee already entered the contribution period.

**If it stays.** Once wages cross the ceiling mid-period, ESI stops even where the period should continue.

**Change.**

Track contribution-period membership and continue ESI through that period.

**Files.**

`backend/payroll/services.py` ESI branch on `gross_full <= esi_ceiling`

**Done when.**

`test_bug_prl_002` fails on today's code and passes after the change. The test shows this failure is gone: Once wages cross the ceiling mid-period, ESI stops even where the period should continue.

**Test.** `test_bug_prl_002` in `backend/tests/test_bug_register.py`.

<a id="bug-cnt-001"></a>

### BUG-CNT-001. Expired Contracts Continue to Show as ACTIVE on Read

> **Triage 2026-10-04: CONFIRMED.** No read-time status computation in contracts serializers/views; only the beat task updates status.

**Severity**: P2. **Order in wave**: 19. **Domain**: Manufacturing, payroll, contracts, complaints.

**Failure.**

Contract status is updated only when the model is explicitly saved or when the Celery beat task runs. Read operations (`GET /contracts`) return the stored DB value without re-checking `end_date < today`.

**If it stays.** Contracts that expired hours or days ago appear as ACTIVE on UI dashboards.

**Change.**

Dynamically compute status on serialization if the stored status is `ACTIVE` but `end_date < timezone.localdate()`.

**Files.**

`backend/contracts/models.py`

**Done when.**

`test_bug_cnt_001` fails on today's code and passes after the change. The test shows this failure is gone: Contracts that expired hours or days ago appear as ACTIVE on UI dashboards.

**Test.** `test_bug_cnt_001` in `backend/tests/test_bug_register.py`.

<a id="bug-cnt-002"></a>

### BUG-CNT-002. Contracts Never Create a Recurring Invoice From the Screen

> **Triage 2026-10-04: CONFIRMED.** ContractsPage.tsx never calls createContractSchedule.

**Severity**: P1. **Order in wave**: 20. **Domain**: Manufacturing, payroll, contracts, complaints.

**Failure.**

Create does not call the schedule API. Product sits under an optional "More" block. Value is optional. Expired-but-still-ACTIVE display is **BUG-CNT-001**.

**If it stays.** Warranty and AMC contracts never generate invoices through the product UI.

**Change.**

Require product and value for billable types, then create the schedule from the contract screen.

**Files.**

- `web/src/pages/contracts/ContractsPage.tsx`
  - `backend/contracts/services.py` (schedule requires product and value)
  - `web/src/api/growth.ts` `createContractSchedule` is unused by the page

**Ships with.** Backend creates the schedule invoice. BUG-COG-G06 is the button.

**Done when.**

`test_bug_cnt_002` fails on today's code and passes after the change. The test shows this failure is gone: Warranty and AMC contracts never generate invoices through the product UI.

**Test.** `test_bug_cnt_002` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-cmp-001"></a>

### BUG-CMP-001. Complaints Can Be Marked RESOLVED While Linked Documents Remain DRAFT

> **Triage 2026-10-04: CLOSED. Already fixed.** complaints/services.py:125 `_assert_posted` requires the linked document to be COMPLETED before resolve. No production change is needed.

**Severity**: P2. **Order in wave**: 21. **Domain**: Manufacturing, payroll, contracts, complaints.

**Failure.**

When a complaint creates a replacement order or credit note, the document is saved as a `DRAFT`. The complaint can still be transitioned to `RESOLVED` without completing the document.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_cmp_001` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_cmp_001` in `backend/tests/test_bug_register.py`.

<a id="bug-cmp-002"></a>

### BUG-CMP-002. Complaint Return, Credit Note, and Order Actions Do Not Open the Draft

> **Triage 2026-10-04: CONFIRMED.** ComplaintsPage.tsx has no navigate to the created draft.

**Severity**: P2. **Order in wave**: 22. **Domain**: Manufacturing, payroll, contracts, complaints.

**Failure.**

The page prints the new document id and does not navigate. The API creates a draft. Resolve later requires a completed document when one is linked.

**If it stays.** The operator creates a draft, then cannot finish it from the complaint, and resolve fails.

**Change.**

Navigate to the created sales document, the same way a completed invoice should open.

**Files.**

`web/src/pages/complaints/ComplaintsPage.tsx`. Create-return, credit note, and order return an id. Resolving while the linked document is still draft is **BUG-CMP-001**.

**Ships with.** The service opens the existing draft. BUG-COG-G02 is the prefilled credit-note action on top.

**Done when.**

`test_bug_cmp_002` fails on today's code and passes after the change. The test shows this failure is gone: The operator creates a draft, then cannot finish it from the complaint, and resolve fails.

**Test.** `test_bug_cmp_002` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-crm-003"></a>

### BUG-CRM-003. A Pipeline Deal Can Be Marked Won With No Customer

> **Triage 2026-10-04: CONFIRMED.** OpportunityPipelinePage.tsx allows OPEN/QUALIFIED/NEGOTIATION -> WON with no customer check.

**Severity**: P1. **Order in wave**: 23. **Domain**: CRM and support.

**Failure.**

The board does not require a customer before WON. The billing APIs do.

**If it stays.** The deal is won and cannot produce a quotation or invoice.

**Change.**

Require a customer before WON.

**Files.**

- `web/src/pages/crm/OpportunityPipelinePage.tsx` one-click move to WON
  - `backend/crm/views.py` quotation and invoice actions return 400 when `customer_id` is null

**Done when.**

`test_bug_crm_003` fails on today's code and passes after the change. The test shows this failure is gone: The deal is won and cannot produce a quotation or invoice.

**Test.** `test_bug_crm_003` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-crm-002"></a>

### BUG-CRM-002. Percent Referral Rewards Use the Opportunity Amount, Not Invoiced Revenue

> **Triage 2026-10-04: CONFIRMED.** crm/referrals.py:277 uses opportunity.amount.

**Severity**: P1. **Order in wave**: 24. **Domain**: CRM and support.

**Failure.**

The two calculations do not share a revenue base.

**If it stays.** Percent rewards can be approved on an amount that was never billed.

**Change.**

Base the percent on completed invoice taxable value, or block the reward until an invoice completes.

**Files.**

`backend/crm/referrals.py` reward amount uses `opportunity.amount`. Campaign ROI in `backend/crm/campaigns.py` uses completed invoice taxable value.

**Done when.**

`test_bug_crm_002` fails on today's code and passes after the change. The test shows this failure is gone: Percent rewards can be approved on an amount that was never billed.

**Test.** `test_bug_crm_002` in `backend/tests/test_bug_register.py`.

<a id="bug-crm-001"></a>

### BUG-CRM-001. Mark Referral Paid Says It Drafts a Credit Note. The Service Only Flips Status.

> **Triage 2026-10-04: PARTIAL.** Service docstring now says it does not draft a credit note; UI copy not re-checked.

**Severity**: P1. **Order in wave**: 25. **Domain**: CRM and support.

**Failure.**

The hint says marking paid drafts a credit note. The function sets `reward_status` to `PAID` and does not set the `credit_note` foreign key. The docstring says it does not draft a note.

**If it stays.** The reward looks settled. The customer balance is unchanged.

**Change.**

The service docstring now states that mark-paid does not draft a credit note. Fix only the UI copy that implies a draft is created. No service change.

**Files.**

- `web/src/i18n/en.ts` `markPaidHint`
  - `backend/crm/referrals.py` `mark_reward_paid`

**Ships with.** The service drafts and links the credit note, or the hint changes. BUG-COG-G10 is the settlement choice on the screen.

**Done when.**

The referral page no longer says a credit note is drafted; a web test asserts the new wording in English and Hindi.

**Test.** `test_bug_crm_001` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-crm-005"></a>

### BUG-CRM-005. Won Opportunity Can Draft a Quotation in the UI and Not an Invoice

> **Triage 2026-10-04: CONFIRMED.** web/src/api/crm.ts has no draft-invoice call.

**Severity**: P2. **Order in wave**: 26. **Domain**: CRM and support.

**Failure.**

The invoice action is unused. No customer on Won is **BUG-CRM-003**.

**If it stays.** The operator leaves CRM and retypes lines to bill.

**Change.**

Add Draft invoice next to the quotation action.

**Files.**

`backend/crm/views.py` `draft-invoice`. `web/src/api/crm.ts` only wires `createQuotationFromOpportunity`.

**Done when.**

`test_bug_crm_005` fails on today's code and passes after the change. The test shows this failure is gone: The operator leaves CRM and retypes lines to bill.

**Test.** `test_bug_crm_005` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-crm-004"></a>

### BUG-CRM-004. Campaigns Cannot Be Edited, and the Funnel Mis-Labels Revenue

> **Triage 2026-10-04: PARTIAL.** CampaignsPage now edits (`editing` state, updateCampaign); revenue label still maps only quotation_total vs opportunity amount (line 184).

**Severity**: P2. **Order in wave**: 27. **Domain**: CRM and support.

**Failure.**

Funnel loads metrics into `editing` and never opens the create dialog. The UI maps any revenue source other than `quotation_total` to "opportunity amount". The backend emits `completed_invoice_taxable_net` and `no_completed_invoice`.

**If it stays.** Status, budget, and parent cannot be changed. ROI rows explain the wrong revenue basis.

**Change.**

Editing already works (`editing` state and `updateCampaign`). The remaining fix is the funnel label: map the backend revenue sources `completed_invoice_taxable_net` and `no_completed_invoice` to their own labels instead of "opportunity amount" (`CampaignsPage.tsx`, line 184).

**Files.**

`web/src/pages/crm/CampaignsPage.tsx`. Delete-without-confirm is **BUG-UI-012**.

**Done when.**

A web test renders each revenue source with its own label in English and Hindi.

**Test.** `test_bug_crm_004` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-sup-001"></a>

### BUG-SUP-001. Shared Tickets Freeze Status at Share Time

> **Triage 2026-10-04: CONFIRMED.** support/share.py snapshots status at share time only.

**Severity**: P2. **Order in wave**: 28. **Domain**: CRM and support.

**Failure.**

Share snapshots `status`. Later resolve or close does not write the share row.

**If it stays.** The shared-tickets page keeps the status from the moment of sharing.

**Change.**

Update the share row on transition, or read the live ticket.

**Files.**

`backend/support/share.py`. Ticket `transition` does not update `VendorTicketShare`.

**Done when.**

`test_bug_sup_001` fails on today's code and passes after the change. The test shows this failure is gone: The shared-tickets page keeps the status from the moment of sharing.

**Test.** `test_bug_sup_001` in `backend/tests/test_bug_register.py`.

<a id="bug-sup-002"></a>

### BUG-SUP-002. Support Tickets Cannot Be Reassigned, and Category Is Invisible

> **Triage 2026-10-04: CONFIRMED.** TicketsPage.tsx only filters on assignee; no reassign control or category field.

**Severity**: P2. **Order in wave**: 29. **Domain**: CRM and support.

**Failure.**

Assignee is display and filter only. Create auto-assigns `SALES_STAFF` only. The form has no category.

**If it stays.** Tickets cannot be moved to the right owner. Categories such as number mismatch are unused.

**Change.**

Add assignee and category on create and on the ticket.

**Files.**

`web/src/pages/support/TicketsPage.tsx`. Create sends subject and priority. `backend/support/models.py` has category choices.

**Done when.**

`test_bug_sup_002` fails on today's code and passes after the change. The test shows this failure is gone: Tickets cannot be moved to the right owner. Categories such as number mismatch are unused.

**Test.** `test_bug_sup_002` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-sup-003"></a>

### BUG-SUP-003. Share With Bizboard Returns 404 When No Vendor Company Is Configured

> **Triage 2026-10-04: CONFIRMED.** support/share.py raises Http404 when no vendor company is configured; Share button not gated.

**Severity**: P2. **Order in wave**: 30. **Domain**: CRM and support.

**Failure.**

The button is not gated on configuration. The API uses 404 for a setup gap.

**If it stays.** Owners click Share and see an error that looks like the ticket is gone.

**Change.**

Hide Share until a vendor company is configured, and return a clear 400.

**Files.**

`backend/support/share.py` raises `Http404` when `vendor_id` is none. `web/src/pages/support/TicketsPage.tsx` still shows Share.

**Done when.**

`test_bug_sup_003` fails on today's code and passes after the change. The test shows this failure is gone: Owners click Share and see an error that looks like the ticket is gone.

**Test.** `test_bug_sup_003` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

<a id="bug-crm-006"></a>

### BUG-CRM-006. Insights Hub Does Not Open the Attention Inbox

> **Triage 2026-10-04: CONFIRMED.** InsightsHubPage.tsx does not link to Attention.

**Severity**: P3. **Order in wave**: 31. **Domain**: CRM and support.

**Failure.**

The hub uses legacy alerts and hints. Attention rows live on another page with no link from the hub.

**If it stays.** Operators who start at Insights never reach assignment and snooze.

**Change.**

Link Attention from the hub.

**Files.**

`web/src/pages/insights/InsightsHubPage.tsx` versus `web/src/pages/AttentionPage.tsx`

**Done when.**

`test_bug_crm_006` fails on today's code and passes after the change. The test shows this failure is gone: Operators who start at Insights never reach assignment and snooze.

**Test.** `test_bug_crm_006` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-024"></a>

### BUG-UI-024. Account Aggregator, GSTR-6/7/8, Shared Tickets, and CRM Onboarding Cannot Finish the Task

> **Triage 2026-10-04: CONFIRMED.** GstReturnPage.tsx:412 `GstStubPage` for GSTR-6/7/8.

**Severity**: P2. **Order in wave**: 32. **Domain**: Web and hardware.

**Failure.**

The routes render honesty walls or non-interactive lists.

**If it stays.** Deep links and flags open a task the user cannot complete.

**Change.**

Hide the route until it has a happy path, or link each step to a real screen.

**Files.**

- `web/src/pages/payments/AccountAggregatorPage.tsx` (warning only)
  - GSTR-6/7/8 stub in `web/src/pages/reports/GstReturnPage.tsx`, routed from `web/src/App.tsx`
  - `web/src/pages/support/SharedTicketsPage.tsx` (one line per row, no action)
  - `web/src/pages/crm/CrmOnboardingPage.tsx` (checklist is not clickable)

**Done when.**

`test_bug_ui_024` fails on today's code and passes after the change. The test shows this failure is gone: Deep links and flags open a task the user cannot complete.

**Test.** `test_bug_ui_024` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

## Wave 6. SaaS billing and abuse limits

Dunning must be able to start a second cycle. Unknown gateway events stay unprocessed so a later known handler can run. The write gate normalizes the trailing slash before it compares allow-suffixes.

<a id="bug-bil-001"></a>

### BUG-BIL-001. SaaS Dunning Never Restarts After a Second Past-Due

> **Triage 2026-10-04: CONFIRMED.** `last_dunning_step` is only ever set (dunning.py:90), never reset.

**Severity**: P1. **Order in wave**: 1. **Domain**: Billing.

**Failure.**

The step counter only moves forward. Leaving `PAST_DUE` does not reset it. Email is best-effort; there is no in-app step.

**If it stays.** After recover and past-due again, owners get no further dunning emails. An owner with a dead inbox learns only when writes start failing.

**Change.**

Reset `last_dunning_step` when status leaves `PAST_DUE`, and show the step on the billing page and the dashboard.

**Files.**

- `backend/billing/services.py` `apply_razorpay_subscription_status` sets `ACTIVE` without clearing `last_dunning_step`
  - `backend/billing/dunning.py` skips when `last_dunning_step >= step`

**Done when.**

`test_bug_bil_001` fails on today's code and passes after the change. The test shows this failure is gone: After recover and past-due again, owners get no further dunning emails. An owner with a dead inbox learns only when writes start failing.

**Test.** `test_bug_bil_001` in `backend/tests/test_bug_register.py`.

<a id="bug-bil-002"></a>

### BUG-BIL-002. Unknown Razorpay Subscription Events Are Stored as Processed

> **Triage 2026-10-04: CONFIRMED.** billing/views.py:254-260 stores a ProcessedWebhookEvent with company=None and returns ignored.

**Severity**: P2. **Order in wave**: 2. **Domain**: Billing.

**Failure.**

The view inserts `ProcessedWebhookEvent` and returns ignored when no local subscription exists. The test-environment signature hole is **BUG-SEC-002**, not this race.

**If it stays.** If the local row appears a moment later, Razorpay retries are treated as duplicates and the status never applies.

**Change.**

Do not dedup an event that matched no local subscription.

**Files.**

`backend/billing/views.py` webhook handler

**Done when.**

`test_bug_bil_002` fails on today's code and passes after the change. The test shows this failure is gone: If the local row appears a moment later, Razorpay retries are treated as duplicates and the status never applies.

**Test.** `test_bug_bil_002` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-009"></a>

### BUG-SEC-009. SaaS Subscription Write-Gate Middleware Bypasses Trailing-Slash URL Normalization

> **Triage 2026-10-04: CONFIRMED.** billing/middleware.py:31 matches `path.endswith(ALLOW_SUFFIXES)` on the raw path with no slash normalisation.

**Severity**: P2. **Order in wave**: 3. **Domain**: Security.

**Failure.**

`ALLOW_SUFFIXES = ("/cancel/", "/void/", "/reverse/")`. `SubscriptionWriteGateMiddleware` executes before Django's `CommonMiddleware` (which appends trailing slashes). If an HTTP client issues a POST to `/api/v1/sales/invoices/123/cancel` (no trailing slash), `path.endswith(ALLOW_SUFFIXES)` evaluates to `False`, immediately returning a 403 `subscription_blocked` response before Django can redirect.

**If it stays.** Lapsed or trial-expired tenants attempting to unwind, cancel, or tidy up draft vouchers before account close receive a 403 Forbidden error if their HTTP client omits the trailing slash.

**Change.**

Normalize path or match `path.rstrip("/") + "/"` against `ALLOW_SUFFIXES`.

**Files.**

`backend/billing/middleware.py`, `backend/billing/middleware.py`

**Done when.**

`test_bug_sec_009` fails on today's code and passes after the change. The test shows this failure is gone: Lapsed or trial-expired tenants attempting to unwind, cancel, or tidy up draft vouchers before account close receive a 403 Forbidden error if their HTTP client omits the trailing slash.

**Test.** `test_bug_sec_009` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-007"></a>

### BUG-SEC-007. Distributed Redis Token Bucket Rate Limiter Absent

> **Triage 2026-10-04: CLOSED. Already fixed.** core/throttles.py has `TenantPlanRateThrottle` (per-plan limits) and prod/staging require Redis for the cache (settings.py:474-482). Register cites core/throttling.py, which does not exist. No production change is needed.

**Severity**: P2. **Order in wave**: 4. **Domain**: Security.

**Failure.**

Throttling uses standard DRF `AnonRateThrottle` and `UserRateThrottle` stored in in-memory cache fallback. No distributed token-bucket rate limiter per tenant tier exists.

**Change.**

None. The code already does what this finding asks for, or the finding does not apply (see the triage note above).

**Done when.**

`test_bug_sec_007` is added as a regression guard, passes on today's code, and stays in CI. No production file changes.

**Test.** `test_bug_sec_007` in `backend/tests/test_bug_register.py`.

## Wave 7. Query cost and scale

Correctness waves are already merged, so query changes cannot hide a wrong total. Cap page size in the shared pagination class, then remove the N+1 and add indexes. GSTR builders stream. The bundle budget is the last check.

<a id="bug-sec-005"></a>

### BUG-SEC-005. Unbounded Query Endpoints Causing Denial of Service

> **Triage 2026-10-04: PARTIAL.** Default paginator exists (core/pagination.py, max 200). Verify exports and views that override pagination. The "django-ninja" advice is wrong (project is DRF).

**Severity**: P1. **Order in wave**: 1. **Domain**: Security.

**Failure.**

Default querysets allow unpaginated or high-limit exports (`?limit=100000`) without hard database result capping or streaming cursor pagination.

**If it stays.** Memory exhaustion (OOM crashes) on the Django worker processes when tenants with 50,000+ transactions request reports.

**Change.**

The default paginator (`core/pagination.py`, max 200) already covers ordinary list views. Audit `JournalEntryViewSet`, `StockMovementViewSet`, and every export action for a custom pagination class or an unsliced queryset. Clamp `page_size` to 250 where it is higher and stream CSV exports.

**Files.**

- `backend/accounting/views.py` (`JournalEntryViewSet`)
  - `backend/inventory/views.py` (`StockMovementViewSet`)

**Done when.**

`test_bug_sec_005` requests `page_size=100000` on the journal and stock-movement lists and receives at most 250 rows; an export of a large fixture does not build the full list in memory.

**Test.** `test_bug_sec_005` in `backend/tests/test_bug_register.py`.

<a id="bug-perf-001"></a>

### BUG-PERF-001. StockBalanceViewSet N+1 Query Multiplier via Missing select_related on Warehouse and BatchLot

> **Triage 2026-10-04: CONFIRMED.** StockBalanceViewSet queryset uses select_related("product") only; serializer reads warehouse.name.

**Severity**: P1. **Order in wave**: 2. **Domain**: Performance.

**Failure.**

`StockBalanceViewSet` declares `queryset = StockBalance.objects.select_related("product")`. However, `StockBalanceSerializer` references `warehouse.name`, `batch.batch_no`, and `batch.expiry_date`. Neither `warehouse` nor `batch` is included in `select_related`.

**If it stays.** Fetching a paginated list of 100 stock items executes **201 individual SQL queries** ($1 + 100 + 100$) instead of a single JOIN query. Under POS checkout and inventory audit concurrency, this exhausts database connection pool threads and triggers query timeouts.

**Change.**

```python
# backend/inventory/views.py: update queryset definition
queryset = StockBalance.objects.select_related("product", "warehouse", "batch")
```

**Files.**

- `backend/inventory/views.py` (`StockBalanceViewSet.queryset`)
  - `backend/inventory/serializers.py` (`StockBalanceSerializer`)

**Done when.**

`test_bug_perf_001` fails on today's code and passes after the change. The test shows this failure is gone: Fetching a paginated list of 100 stock items executes **201 individual SQL queries** ($1 + 100 + 100$) instead of a single JOIN query. Under POS checkout and inventory audit concurrency, this exhausts database connection pool threads and…

**Test.** `test_bug_perf_001` in `backend/tests/test_bug_register.py`.

<a id="bug-perf-002"></a>

### BUG-PERF-002. Celery Worker Queue Starvation from Unpartitioned Background Tasks

> **Triage 2026-10-04: CONFIRMED.** No Celery task routing or queues in settings.

**Severity**: P1. **Order in wave**: 3. **Domain**: Performance.

**Failure.**

All Celery tasks (fast OTP dispatches, payment gateway webhooks, heavy PDF rendering, OCR document ingestion, and recurring invoice schedules) run in a single shared default `celery` queue without priority queue routing.

**If it stays.** When an operator initiates a batch invoice PDF export or bill scan OCR job, heavy Weasyprint / CPU threads block the queue. Real-time customer OTPs and payment webhook confirmations sit queued behind long-running PDF jobs, resulting in gateway timeouts and dropped payments.

**Change.**

Define dedicated queues with priority routing:
```python
CELERY_TASK_ROUTES = {
    "core.tasks.send_otp_*": {"queue": "high_priority"},
    "payments.tasks.process_webhook_*": {"queue": "high_priority"},
    "sales.tasks.generate_invoice_pdf": {"queue": "media_heavy"},
    "ocr.tasks.process_bill_image": {"queue": "media_heavy"},
    "reporting.tasks.*": {"queue": "reports"},
    "*": {"queue": "default"},
}
```

**Files.**

`backend/config/settings.py` (Celery broker configuration)

**Done when.**

`test_bug_perf_002` fails on today's code and passes after the change. The test shows this failure is gone: When an operator initiates a batch invoice PDF export or bill scan OCR job, heavy Weasyprint / CPU threads block the queue. Real-time customer OTPs and payment webhook confirmations sit queued behind long-running PDF jobs, resulting in…

**Test.** `test_bug_perf_002` in `backend/tests/test_bug_register.py`.

<a id="bug-perf-003"></a>

### BUG-PERF-003. Unbounded In-Memory Model Instantiation in GSTR-1 & GSTR-3B Builders

> **Triage 2026-10-04: CONFIRMED.** build_gstr1 materialises list(invoices) and list(inv.items.all()) per invoice (gst_returns.py:602, 630).

**Severity**: P1. **Order in wave**: 4. **Domain**: Performance.

**Failure.**

`build_gstr1` and `build_gstr3b` fetch `invoices = list(_gst_sales_invoices(...))` and evaluate `items = list(inv.items.all())` for every invoice in Python memory in a synchronous HTTP request.

**If it stays.** For mid-size distributors with 30,000 monthly invoices and 150,000 line items, instantiating full Django ORM models allocates **400 MB to 700 MB of heap memory** per request. Concurrent return generation by accountants triggers Gunicorn worker OOM kills (SIGKILL / 502 Bad Gateway).

**Change.**

1. Stream records using `.iterator(chunk_size=1000)` and lightweight dictionary projections (`.values(...)`) rather than full ORM instances.
  2. Offload return compilation to background Celery tasks with cached results in `GstReturnSnapshot`.

**Files.**

- `backend/reporting/gst_returns.py` (`build_gstr1`)
  - `backend/reporting/gst_returns.py` (`_gst_sales_invoices`)

**Done when.**

`test_bug_perf_003` fails on today's code and passes after the change. The test shows this failure is gone: For mid-size distributors with 30,000 monthly invoices and 150,000 line items, instantiating full Django ORM models allocates **400 MB to 700 MB of heap memory** per request. Concurrent return generation by accountants triggers Gunicorn…

**Test.** `test_bug_perf_003` in `backend/tests/test_bug_register.py`.

<a id="bug-perf-004"></a>

### BUG-PERF-004. O(N) All-Time Historical Ledger Scanning on Financial Reports Due to Missing Account Period Balance Rollups

> **Triage 2026-10-04: CONFIRMED.** accounting/reports.py `_balances` aggregates JournalLine from inception unless date_from is passed; no rollup table.

**Severity**: P2. **Order in wave**: 5. **Domain**: Performance.

**Failure.**

`trial_balance` and `profit_and_loss` compute account balances by aggregating all posted `JournalLine` rows from day one of company inception:
  `JournalLine.objects.filter(entry__company=company, entry__status="POSTED").values("account_id").annotate(...)`.
There are no monthly balance rollup tables or incremental roll-forward snapshots. Additionally, filtering on `entry__company=company` forces an unnecessary table JOIN on `accounting_journalentry`.

**If it stays.** As transaction volume grows to hundreds of thousands of postings, opening Trial Balance or P&L degrades from sub-second to 5-10+ seconds.

**Change.**

1. Filter directly on `company=company` leveraging the denormalized `company_id` column on `JournalLine`.
  2. Implement an `AccountMonthlyBalance` rollup table updated on period close or ledger commit so reports aggregate at most one current month's lines plus the prior monthly closing balance ($O(1)$ query complexity).

**Files.**

`backend/accounting/reports.py` (`_balances` & `trial_balance`)

**Done when.**

`test_bug_perf_004` fails on today's code and passes after the change. The test shows this failure is gone: As transaction volume grows to hundreds of thousands of postings, opening Trial Balance or P&L degrades from sub-second to 5-10+ seconds.

**Test.** `test_bug_perf_004` in `backend/tests/test_bug_register.py`.

<a id="bug-perf-005"></a>

### BUG-PERF-005. Missing Critical Multi-Column Composite Indexes on PaymentAllocation, SalesInvoice, and JournalLine

> **Triage 2026-10-04: CONFIRMED.** PaymentAllocation has no Meta indexes and SalesInvoice has one; JournalLine is already indexed (accounting/models.py:160-163).

**Severity**: P2. **Order in wave**: 6. **Domain**: Performance.

**Failure.**

High-frequency multi-column filtering patterns lack matching composite indexes in PostgreSQL:
  1. `PaymentAllocation`: Missing `(sales_invoice, reversed_at)` and `(purchase_invoice, reversed_at)` — checks for active allocations perform index scans with heap filter passes.
  2. `SalesInvoice`: Missing `(company, customer, status, invoice_date)` — Customer 360 and ledger statements perform bitmap index scans across all company invoices.
  3. `JournalLine`: Missing `(company, entry_date, account)` — date-bounded GL ledger lookups force index joins against `JournalEntry`.

**If it stays.** High database disk I/O, increased buffer cache churn, and degraded API response times as table rows scale past 100,000.

**Change.**

Add explicit composite indexes in the model `Meta.indexes` lists and run Django migrations.

**Files.**

- `backend/payments/models.py` (`PaymentAllocation.Meta`)
  - `backend/sales/models.py` (`SalesInvoice.Meta`)
  - `backend/accounting/models.py` (`JournalLine.Meta`)

**Done when.**

`test_bug_perf_005` fails on today's code and passes after the change. The test shows this failure is gone: High database disk I/O, increased buffer cache churn, and degraded API response times as table rows scale past 100,000.

**Test.** `test_bug_perf_005` in `backend/tests/test_bug_register.py`.

<a id="bug-perf-006"></a>

### BUG-PERF-006. Correlated Subqueries & Python In-Memory Grouping in Low Stock Alert Calculation

> **Triage 2026-10-04: CONFIRMED.** low_stock_alert_payload correlates a WarehouseReorderLevel subquery per balance row and groups in Python.

**Severity**: P2. **Order in wave**: 7. **Domain**: Performance.

**Failure.**

`low_stock_alert_payload` executes a correlated `Subquery` on `WarehouseReorderLevel` for every row in `StockBalance`, then fetches all active balances into memory with `list(...)` and iterates in Python using `defaultdict` to compute company-wide totals.

**If it stays.** In companies with 15,000+ SKUs across multiple godowns, low stock dashboard widgets execute 15,000+ correlated subquery evaluations and allocate tens of megabytes of Python heap, delaying dashboard rendering.

**Change.**

Replace correlated subquery and Python iteration with a single database-level SQL aggregation (`GROUP BY product_id HAVING SUM(on_hand - reserved) <= product.reorder_level`).

**Files.**

`backend/inventory/views.py` (`low_stock_alert_payload` & `_effective_reorder_annotation`)

**Done when.**

`test_bug_perf_006` fails on today's code and passes after the change. The test shows this failure is gone: In companies with 15,000+ SKUs across multiple godowns, low stock dashboard widgets execute 15,000+ correlated subquery evaluations and allocate tens of megabytes of Python heap, delaying dashboard rendering.

**Test.** `test_bug_perf_006` in `backend/tests/test_bug_register.py`.

<a id="bug-perf-008"></a>

### BUG-PERF-008. Sequential Single-Bill Offline Flush Causes Long POS Network Reconnection Delays

> **Triage 2026-10-04: CONFIRMED.** flushPosDraft handles one draft at a time with sequential requests.

**Severity**: P2. **Order in wave**: 8. **Domain**: Performance.

**Failure.**

When an offline POS terminal regains connectivity, `flushPosDraft` loops through all queued drafts sequentially, executing individual HTTP `POST` requests for customer resolution, draft creation, stock hold, and invoice completion per bill.

**If it stays.** Syncing a backlog of 30 offline orders requires over 60 sequential HTTP network round-trips taking 20–40 seconds, during which cashier UI is locked or exposed to connection drops.

**Change.**

Implement a bulk sync endpoint (`POST /api/v1/sales/pos/batch-sync/`) accepting an array of offline checkouts and committing them within a single atomic database transaction.

**Files.**

`web/src/offline/flushPosCheckout.ts` (`flushPosDraft`)

**Done when.**

`test_bug_perf_008` fails on today's code and passes after the change. The test shows this failure is gone: Syncing a backlog of 30 offline orders requires over 60 sequential HTTP network round-trips taking 20–40 seconds, during which cashier UI is locked or exposed to connection drops.

**Test.** `test_bug_perf_008` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-perf-007"></a>

### BUG-PERF-007. Frontend Initial Bundle Bloat (482 KB Gzip) & Missing Table Virtualization on High-Volume Master Screens

> **Triage 2026-10-04: PARTIAL.** Bundle budget ratchet exists (initial 530 KB gzip, measured 481.7) and @tanstack/react-virtual is installed; actual use on Products/Customers tables not confirmed.

**Severity**: P2. **Order in wave**: 9. **Domain**: Performance.

**Failure.**

1. Top-level bundle includes direct destructured imports from `@mui/material` and `@mui/icons-material`, bloating initial parse time.
  2. While `VirtualizedTable` is implemented, high-volume master pages (`ProductsPage`, `CustomersPage`, `QuotationsPage`, `SalesOrdersPage`) render unvirtualized standard HTML tables.

**If it stays.** Mobile devices and budget POS terminals experience long Time-To-Interactive (TTI > 3.5s) on cold load and frame drops during table scrolling.

**Change.**

The bundle ratchet (`web/bundle-budget.json`) and `@tanstack/react-virtual` already exist. Apply virtualisation to the Products and Customers tables and trim the largest initial imports until initial gzip is under 500 KB, then lower the ratchet.

**Files.**

- `web/bundle-budget.json` (Measured: 481.7 KB initial gzip)
  - `web/src/pages/inventory/ProductsPage.tsx`
  - `web/src/pages/sales/CustomersPage.tsx`

**Done when.**

`npm --prefix web run budget` passes with the lowered ratchet; a 5,000-row fixture renders only the visible rows.

**Test.** `test_bug_perf_007` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-011"></a>

### BUG-UI-011. Products Page Unbounded `listStock()` Call Triggers Heavy Client-Side Memory Overhead

> **Triage 2026-10-04: CONFIRMED.** ProductsPage.tsx:89 calls `listStock()` with no paging.

**Severity**: P2. **Order in wave**: 10. **Domain**: Web and hardware.

**Failure.**

While `listProductsPage` is paginated to 50 records per page, `stockQuery` executes `listStock()` without pagination parameters, downloading the entire stock balance table across all godowns/warehouses for the tenant into client memory on every catalog page load.

**If it stays.** For mid-size retailers and distributors with 10,000+ SKUs, page load downloads multi-megabyte payloads, causing noticeable UI freeze, high memory consumption, and potential mobile browser tab crashes.

**Change.**

Add a server-side stock balance lookup endpoint scoped to the current page's product IDs (`/api/v1/inventory/stock/by-products/?product_ids=...`), or embed `current_stock` directly inside `listProductsPage` response serializer.

**Files.**

`web/src/pages/inventory/ProductsPage.tsx` (`stockQuery`)

**Done when.**

`test_bug_ui_011` fails on today's code and passes after the change. The test shows this failure is gone: For mid-size retailers and distributors with 10,000+ SKUs, page load downloads multi-megabyte payloads, causing noticeable UI freeze, high memory consumption, and potential mobile browser tab crashes.

**Test.** `test_bug_ui_011` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-sales-009"></a>

### BUG-SALES-009. Trigram Catalog Search Missing on High-Volume Product Lookup

> **Triage 2026-10-04: CONFIRMED.** No GinIndex / trigram index in masters/.

**Severity**: P3. **Order in wave**: 11. **Domain**: Sales.

**Failure.**

Catalog lookups use SQL `icontains` without PostgreSQL `pg_trgm` or GIN indexing.

**If it stays.** Search latency degrades severely (>1.5s) once the catalog exceeds 10,000 SKUs.

**Change.**

Add `GinIndex(fields=['name', 'sku', 'barcode'], opclasses=['gin_trgm_ops'])`.

**Files.**

`backend/masters/models.py`

**Done when.**

`test_bug_sales_009` fails on today's code and passes after the change. The test shows this failure is gone: Search latency degrades severely (>1.5s) once the catalog exceeds 10,000 SKUs.

**Test.** `test_bug_sales_009` in `backend/tests/test_bug_register.py`.

## Wave 8. Cognitive load and shared screens

Start with captions and copy that do not hide a control: series caption, shop-floor nav words, blocker text, invoice-type inference with the select still visible, price-mode caption, and the word Godown. Rank invoice actions, then returns, place of supply, purchase autofill, and ITC explanation. The period-close hub includes the single books-and-GST close. Growth handoffs come after wave 5 services exist. Hiding selects waits for GD-33. Auto-match waits for the founder note.

<a id="bug-cog-020"></a>

### BUG-COG-020. Read-Only Invoice Series Inputs Mimic Editable Form Fields

> **Triage 2026-10-04: UX PROPOSAL.** NewInvoicePage.tsx:1694 still renders a readOnly input; caption exists only in edit mode. Partly shipped.

**Severity**: P3. **Order in wave**: 1. **Domain**: Cognitive load.

**Alias**: CL-20.

**Failure.**

Read-only inputs still look like form fields.

**If it stays.** Small, on every new bill. The operator pauses on a control that cannot be edited.

**Change.**

Replace the two controls with one caption: "Next bill {prefix}-{padded number}." Series editing stays in settings. Edit mode shows the fixed number as text.

**Files.**

- `web/src/pages/sales/NewInvoicePage.tsx` (`billing.invoicePrefix`, `billing.invoiceNumber`)
  - Purchase equivalent if it shows a read-only number the same way
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Depends on.** Series allocation is unchanged. Edit mode already has `billing.invoiceNumberFixed`. Apply the same caption on the purchase editor if it shows a read-only number the same way.

**Leave unchanged.** Change number allocation.

**Done when.**

The posted number is unchanged. The caption matches the previous helper text (prefix plus padding). Edit mode does not offer an editable number. Existing series tests stay green. One render test that the text contains the padded number.

**Test.** `test_bug_cog_020` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Two apparent fields removed. The posted number is unchanged.

<a id="bug-cog-016"></a>

### BUG-COG-016. Accounting Jargon Confuses Non-Accountant Store Owners

> **Triage 2026-10-04: UX PROPOSAL.** Catalog still uses Credit Notes / Debit Notes labels (i18n/en.ts). Open.

**Severity**: P1. **Order in wave**: 2. **Domain**: Cognitive load.

**Alias**: CL-16.

**Failure.**

Ledger nouns are the navigation nouns.

**If it stays.** Owner and occasional user. Money can be posted on the wrong side because the menu words do not match shop speech.

**Change.**

- `nav.receipts` → "Money in". Page title can stay "Receipt".
  - `nav.supplierPayments` → "Money out". Page title can stay "Payment".
  - Collections stays the chase-dues label.

**Files.**

- `web/src/navigation/menu.ts`
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`
  - Glossary golden test if present (`glossary-status`)

**Depends on.** Founder reads the Hindi (GD-23). Routes do not change. The voucher title stays Receipt or Payment. Collections stays a chase-dues label (`nav.collections`), not a third word for the same voucher. Glossary test that covers Paid / Completed / Returned should also cover this pair. Do not regress Collections copy (A3-5).

**Done when.**

Both languages. Sidebar shows the new labels. The receipt document heading still says Receipt. No route change. Glossary test covers the pair. The founder has read the Hindi.

**Test.** `test_bug_cog_016` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** The owner recognizes the menu. The munshi still sees Receipt on the voucher. Session notes can revert the nav word without a route change.

<a id="bug-cog-015"></a>

### BUG-COG-015. Disabled Document Completion Fails to Explain Root Cause

> **Triage 2026-10-04: UX PROPOSAL.** DocumentEditorShell has `primaryDisabledReason` and a customer-specific reason. Partly shipped.

**Severity**: P1. **Order in wave**: 3. **Domain**: Cognitive load.

**Alias**: CL-15.

**Failure.**

Messages name the rule. They do not name the fix. A2-8 covers only the empty party or item case.

**If it stays.** Every failed Complete. The user re-reads, guesses, and sometimes re-enters lines that are still on the draft.

**Change.**

For each blocker, one sentence with the problem, the cause, and the next action, then focus the control. Keep the draft.

  | Blocker | Sentence |
  |---|---|
  | No party or no line | "Choose a customer, then add an item." Focus the empty one. |
  | Credit limit | "{name} would reach {exposure} against a limit of {limit}. Ask the owner, or reduce the bill." |
  | Missing serial | "Enter the serial for {product}." Focus that cell. Do not clear the line. |
  | Place of supply | Use the CL-07 sentences. |
  | RCM not confirmed | "You marked reverse charge. Confirm it, or turn reverse charge off." Focus the confirm checkbox. |
  | Item saved, opening stock failed | "The item exists. Opening stock did not post. Retry stock only." Do not ask them to recreate the item. |
  | Saved offline | Keep the banner. Say whether stock and the number are pending until reconnect. |
  | Network / 403 / 5xx | Keep the plain class message and the support id. |

**Files.**

- `web/src/pages/sales/NewInvoicePage.tsx`
  - `web/src/pages/purchases/NewPurchasePage.tsx`
  - `web/src/completeGates/completeBlockers.ts`
  - `DocumentEditorShell.tsx` if the disabled reason lives there
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Depends on.** HTTP failures stay on the A3-1 path and keep the support id. Do not mix a validation rule into the HTTP mapper. Place-of-supply copy is CL-07. Founder reads the Hindi (GD-23).

**Done when.**

Each blocker focuses a field. Lines already entered are still on screen. The founder has read the Hindi. Vitest covers each sentence key. Support id remains on HTTP failures only.

**Test.** `test_bug_cog_015` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Less re-reading. The draft stays. No second data entry.

<a id="bug-cog-001"></a>

### BUG-COG-001. Sales Invoice Forces Redundant Declarative Choice of Invoice Type

> **Triage 2026-10-04: UX PROPOSAL.** Wave A inference exists (`invoiceTypeTouched`, GSTIN check); the invoice-type select is still shown (NewInvoicePage.tsx:1729). Partly shipped.

**Severity**: P0. **Order in wave**: 4. **Domain**: Cognitive load.

**Alias**: CL-01.

**Failure.**

The legal enum is a visible choice even after `chooseInvoiceDefaults` has run. That function uses company registration and recent walk-in bills. It does not look at the customer's GSTIN. The select then asks again.

**If it stays.** Every sales invoice. A wrong type is a compliance mistake.

**Change.**

1. *CL-01a, Wave A, select stays visible.* While `invoiceTypeTouched` is false: unregistered or composition companies keep today's company rule; a regular company and a customer with a GSTIN posts `GST`; a regular company and a customer with no GSTIN posts `RETAIL` if that is the company's B2C value, otherwise the company default. Confirm the exact B2C enum against `preferredInvoiceType` before coding. Do not invent a fifth type. Changing the customer may update the type only while the user has not touched the select. Helper text: "GST bill because this customer has a GSTIN."
  2. *CL-01b, Wave C, after the pilot session.* Replace the select on first paint with a chip in shop language ("Bill to a GSTIN customer" / "Bill to a walk-in"). "Change bill type" reopens the existing select. The stored enum is unchanged.

**Files.**

- `web/src/pages/sales/NewInvoicePage.tsx`
  - `web/src/pages/sales/invoiceDefaults.ts` (`chooseInvoiceDefaults`)
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Depends on.** Company registration and the selected customer's GSTIN. `invoiceTypeTouched` must stay false for inference to run. Non-GST stays an explicit override. Printed title stays the legal name.

**Gate.** Wave A (select stays visible, inference runs) ships now. Wave C (chip replaces the select) waits for the pilot staff session GD-33.

**Leave unchanged.** Change how the backend validates `invoiceType`. Do not retitle the printed invoice.

**Done when.**

A GSTIN customer on a regular company gets `GST` without a click, until the user opens the select and changes it. A walk-in with no GSTIN posts `RETAIL` or the company default. A later customer edit does not overwrite a type the user set. An edit of an existing invoice loads the saved type and does not re-infer. Chip or helper is present in English and Hindi. Payload `invoiceType` matches what the select would have posted. Unit tests cover GSTIN party, no-GSTIN party, untouched vs touched, edit mode, fewer than three historical bills, and a composition company.

**Test.** `test_bug_cog_001` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Estimate: header decisions on a plain bill 4–6 → 1. Payload enum unchanged.

<a id="bug-cog-002"></a>

### BUG-COG-002. Price Mode Select Forces Repeated Evaluation of Company Default

> **Triage 2026-10-04: UX PROPOSAL.** `chooseInvoiceDefaults` already derives companyPriceMode; select still shown (NewInvoicePage.tsx:1761). Partly shipped.

**Severity**: P0. **Order in wave**: 5. **Domain**: Cognitive load.

**Alias**: CL-02.

**Failure.**

The company price mode is loaded, then shown again as a select, so a fresh bill still looks undecided.

**If it stays.** A wrong mode changes every line amount.

**Change.**

1. *CL-02a.* Keep the select. The value on open is the company mode. Caption, driven by the value: "Price includes GST" or "Price before GST".
  2. *CL-02b, after the session.* Remove the select from the first row. The caption becomes a chip. Override lives under More tax options. Completed bills stay locked the way they are today (`canAmendMoney`).

**Files.**

- `web/src/pages/sales/NewInvoicePage.tsx`
  - `web/src/pages/purchases/NewPurchasePage.tsx`
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Depends on.** `chooseInvoiceDefaults` already returns `companyPriceMode`. Same inclusive/exclusive maths.

**Gate.** Wave A keeps the select and captions it. Removing the select from the first row waits for GD-33.

**Leave unchanged.** Change inclusive/exclusive maths in the line calculator.

**Done when.**

A new bill opens on the company mode. Changing the chip or the select changes line maths. A completed bill does not become editable. Existing invoice maths tests stay green. One test asserts the initial state equals `companyPriceMode`.

**Test.** `test_bug_cog_002` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** One less decision on every invoice and purchase.

<a id="bug-cog-003"></a>

### BUG-COG-003. Unconditional Warehouse Select Renders on Single-Godown Companies

> **Triage 2026-10-04: UX PROPOSAL.** Warehouse select renders unconditionally (NewInvoicePage.tsx:1775); `multiGodown` prop exists elsewhere. Open.

**Severity**: P0. **Order in wave**: 6. **Domain**: Cognitive load.

**Alias**: CL-03.

**Failure.**

The warehouse select is unconditional. `en.ts` names the nav item Godowns and the bill field Warehouse.

**If it stays.** Every invoice, purchase, and transfer setup for a single-location shop.

**Change.**

1. *CL-03a.* One word on the bill, the purchase, the transfer, and the nav: **Godown**. Default selection stays `isDefault`.
  2. *CL-03b.* If the active list has length 1, do not render a select. Show the name as text. Post that id. If length is 2 or more, show the select, defaulted. A non-default godown on an edited bill is always shown, so the user can see stock is not coming from the default location.

**Files.**

- `web/src/pages/sales/NewInvoicePage.tsx`
  - `web/src/pages/purchases/NewPurchasePage.tsx`
  - Transfer form
  - `web/src/i18n/en.ts` (`nav.warehouses` = "Godowns", `billing.godown` = "Warehouse"), `web/src/i18n/hi.ts`

**Depends on.** Active godown list and `isDefault`. Hindi word agreed with the founder (GD-23). Grep `billing.godown` and `nav.warehouses` so list pages stay consistent. PDF may keep a fuller phrase if the founder wants "Godown" only on screen. Record that choice in the PR.

**Gate.** Renaming the field to Godown ships now. Hiding the select when there is one godown waits for GD-33.

**Leave unchanged.** Change per-godown stock checks. The posted `warehouseId` is the same id as today.

**Done when.**

One active godown: no select, posted id is that godown. Two godowns: select visible, default selected. Edit of a bill whose godown is not the default: the godown is visible. Stock block copy still names the quantity in that godown. Component test with one warehouse and with two. Hindi key parity stays green.

**Test.** `test_bug_cog_003` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** The select disappears when there is one active godown. It stays, defaulted, when there are two or more.

<a id="bug-ui-019"></a>

### BUG-UI-019. Hindi Mode Still Shows English on Billing, Settings, POS, Reports, and Login

> **Triage 2026-10-04: CONFIRMED.** English literals remain, e.g. UnitsSettingsPage.tsx:95 "No units yet", :103 "UQC code". Other listed pages not re-read.

**Severity**: P1. **Order in wave**: 7. **Domain**: Web and hardware.

**Failure.**

Those strings are literals. They do not go through `t()`.

**If it stays.** A Hindi session still confirms, validates, and labels core screens in English.

**Change.**

Move the strings into the Hindi catalog.

**Files.**

- `web/src/pages/settings/BillingPage.tsx` (suspend confirm and plan notices)
  - `web/src/pages/settings/UsersSettingsPage.tsx` (capability confirm)
  - `web/src/pages/settings/UnitsSettingsPage.tsx` ("No units yet", "UQC code")
  - `web/src/pages/settings/SeriesSettingsPage.tsx` (series names)
  - `web/src/pages/insights/InsightsCashflowPage.tsx`
  - `web/src/pages/pos/PosPage.tsx` and `web/src/components/RecordInvoicePaymentDialog.tsx`
  - `web/src/pages/reports/InventoryReportPage.tsx` column headers
  - `web/src/pages/LoginPage.tsx` and `web/src/pages/setup/SetupWizardPage.tsx` (validation and sample names)

**Ships with.** Every new string in this wave goes through `t()` in English and Hindi in the same pull request.

**Done when.**

`test_bug_ui_019` fails on today's code and passes after the change. The test shows this failure is gone: A Hindi session still confirms, validates, and labels core screens in English.

**Test.** `test_bug_ui_019` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-014"></a>

### BUG-COG-014. POS Focus Hijacking Overwrites Item Quantities with Barcode Scans

> **Triage 2026-10-04: UX PROPOSAL.** Search box refocus on several events (PosPage.tsx:966, 1050, 1110); caret lock during qty edit not found. Open.

**Severity**: P1. **Order in wave**: 8. **Domain**: Cognitive load.

**Alias**: CL-14.

**Failure.**

A focus effect treats blur as "return to scan."

**If it stays.** Every correction at the counter, with a customer waiting. A single cash scan scores 1.5. The full session scores 2.7. This is the main extraneous load on that screen.

**Change.**

- After a successful scan or an explicit "back to scan" shortcut, focus the search field.
  - While the caret is in quantity, discount, or batch, keystrokes stay there until Enter or Escape.
  - Escape returns to search and does not change the line.

**Files.**

- `web/src/pages/pos/PosPage.tsx`
  - The focus helper, if one exists

**Depends on.** Existing POS keyboard path. D-UX-6 stays: show the expiry of the batch the cashier typed, and do not add a lot picker. `pos-keyboard-checkout` e2e must stay within its budget. F1/F4/F5/F7/F8/F9 stay printed on the buttons. Do not add a mouse path as the primary path.

**Leave unchanged.** Change price, tax, or tender posting. Do not add a lot picker.

**Done when.**

A test types a multi-digit quantity without the search field receiving those digits. A scan wedge still lands in search when the last committed field was search. Hold (F8) and tender keys still work when focus is on search. The existing keyboard checkout spec stays green.

**Test.** `test_bug_cog_014` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** A multi-digit quantity survives. The scanner still works when the last committed field was search.

<a id="bug-cog-005"></a>

### BUG-COG-005. Unranked Document Actions on Posted Invoices Overload Visual Attention

> **Triage 2026-10-04: UX PROPOSAL.** No ranked action menu on InvoiceDetailPage. Open.

**Severity**: P0. **Order in wave**: 9. **Domain**: Cognitive load.

**Alias**: CL-05.

**Failure.**

Every document capability is a peer button. The next job (print, share, collect) does not win.

**If it stays.** Every follow-up after a bill.

**Change.**

Rank by document state. The page keeps a status chip and the balance near the button.

  | State | Filled button | Outline | Menu / destructive |
  |---|---|---|---|
  | Draft | Complete | Save | Discard draft, with the existing confirm |
  | Posted, balance remaining, user can take payment | Record payment | Share / print | Edit if allowed, Return goods (CL-06), Void |
  | Posted, settled | Share / print | Record payment hidden | Return goods, Void |
  | User lacks payment permission | Share / print | — | Payment actions omitted, not disabled without a reason |

**Files.**

- `web/src/pages/sales/InvoiceDetailPage.tsx`
  - Its test, `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Depends on.** GD-32 keeps Save draft, Complete, and Complete and start another visible on the editor. This row is the posted invoice, not that footer. Do not drop a permission-gated action. Relocate it. Void keeps its confirm. CL-06 is the Return goods entry.

**Done when.**

A clerk without payment permission does not see Record payment. Void and credit note are reachable by keyboard and have accessible names. No action that exists today for that permission and status disappears. axe serious/critical clean on a posted invoice fixture. Render tests for the three states and a user without `canCreatePayments`. One Playwright step: open a posted invoice with a balance, the filled button is the payment action.

**Test.** `test_bug_cog_005` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Estimate: visible peer actions about 55 → under 8, with the rest in one More menu.

<a id="bug-cog-006"></a>

### BUG-COG-006. Sales Return Initiation Forces Manual Pogo-Sticking and Line Re-Entry

> **Triage 2026-10-04: UX PROPOSAL.** No return-from-invoice handoff found. Open.

**Severity**: P0. **Order in wave**: 10. **Domain**: Cognitive load.

**Alias**: CL-06.

**Failure.**

The list is the navigation. The document is the context.

**If it stays.** Every return. Bookkeeper and owner.

**Change.**

"Return goods" opens the existing credit-note editor with the original invoice id and lines copied: item, original qty as the max, rate, tax, godown, and serials that were on the line. Quantity is editable and **defaults to blank** so a careless Complete cannot return the whole bill. "Full return" is one explicit control.

**Files.**

- `web/src/pages/sales/InvoiceDetailPage.tsx`
  - `web/src/pages/sales/NewCreditNotePage.tsx`
  - A prefill helper with unit tests

**Ships with.** After BUG-COG-005. Return goods is one of the ranked actions. Quantity defaults to blank.

**Depends on.** CL-05 menu. Existing credit-note API and editor. The list at `/sales/credit-notes` stays for search. The nav item stays until D-UX-4 is reopened. Start in the menu. Promote to an outline button only if the session shows the menu hid it.

**Leave unchanged.** Change credit-note posting, stock reversal, or tax reversal rules.

**Done when.**

Partial quantity posts a partial credit with the original rate and tax treatment. Quantity above the remaining returnable qty is blocked with a sentence that names the remaining qty. Serial-tracked lines require the serials, as they do today. The credit-note draft survives a validation error. The sales-more list still opens and still creates a credit note. Prefill unit test. One component test that the editor receives the invoice id and lines. Existing posting tests stay green.

**Test.** `test_bug_cog_006` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Estimate: about 6 steps → about 4. Memory of original rates → 0. This estimate is not a baseline.

<a id="bug-cog-007"></a>

### BUG-COG-007. Premature Place of Supply Prompts Ignore Valid Party GSTIN

> **Triage 2026-10-04: UX PROPOSAL.** `placeOfSupplyKnown` exists and is used on sales and purchase pages; shared helper and prompt removal not done. Partly shipped.

**Severity**: P0. **Order in wave**: 11. **Domain**: Cognitive load.

**Alias**: CL-07.

**Failure.**

The rule is correct. The prompt fires before the GSTIN state code is used as the answer.

**If it stays.** Purchases and some sales. Blocks Complete. The user has to stop and interpret a statutory field.

**Change.**

1. Derive a candidate state from the GSTIN state code when the GSTIN is valid.
  2. If the address state is empty, use the GSTIN state and do not ask.
  3. If the GSTIN is empty and the address state is present, use the address state and do not ask.
  4. If both exist and disagree, show both values and block Complete until the user picks one. Copy: "GSTIN says Maharashtra. Address says Gujarat. Which state is this bill for?"
  5. If both are empty, focus the state or GSTIN field. Copy: "Add the supplier's state or GSTIN. GST needs a state for this bill."
  6. Do not clear the draft.

**Files.**

- `web/src/pages/purchases/NewPurchasePage.tsx`
  - `web/src/pages/sales/NewInvoicePage.tsx` if the sales path has the same gap
  - Place-of-supply util (grep `placeOfSupplyKnown`)
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Ships with.** After BUG-COG-006 on the purchase editor. Do not clear the draft.

**Depends on.** Existing `placeOfSupplyKnown`. Shared helper next to that util. Sales path gets the same treatment if it has the same gap.

**Leave unchanged.** Change the tax engine's intra-state vs inter-state rule. Change only when the UI asks and which value it sends.

**Done when.**

Supplier with a valid GSTIN and a blank state: no prompt, and IGST vs CGST/SGST matches today's result for that state code. Conflict: cannot complete until one side is chosen, and the chosen state is what is posted. Both empty: focus lands on the field and other lines remain. Table-driven unit tests for the four cases. One component test that conflict renders both states.

**Test.** `test_bug_cog_007` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** A complete supplier master removes the decision. A conflict becomes the only decision.

<a id="bug-cog-008"></a>

### BUG-COG-008. Inward Purchase Bill Lines Force Manual Re-Entry of Master Data

> **Triage 2026-10-04: UX PROPOSAL.** Purchase lines default hsn blank and gstRate 18; no master autofill. Open.

**Severity**: P0. **Order in wave**: 12. **Domain**: Cognitive load.

**Alias**: CL-08.

**Failure.**

The editor is a blank grid even when the item master and an uploaded file exist.

**If it stays.** Every supplier bill. A wrong ITC claim or a duplicate bill is discovered at GSTR-2B, not at entry.

**Change.**

1. On item select, fill HSN, GST %, unit, and last purchase cost. Caption: "from item" or "last bill". The user can edit. An edit drops the caption.
  2. If the filled GST % disagrees with a rate the user typed, highlight the row. Do not overwrite a user-typed rate.
  3. "Upload bill" is a primary path on the purchase editor, not only a menu destination. Extracted lines use the same caption ("from upload") and the same highlight when they disagree with the item master.
  4. A low-confidence extracted rate is shown empty or marked "check this". It is never posted as if the user typed it.

**Files.**

- `web/src/pages/purchases/NewPurchasePage.tsx`
  - Purchase line component and the bill-upload handoff
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Ships with.** After BUG-COG-007. Autofill captions the source and never overwrites a typed rate.

**Depends on.** Item master HSN, GST %, unit, and last purchase cost. Bill upload already exists as a side route. Extraction confidence follows freeze item D14. Do not weaken it.

**Leave unchanged.** Post a line the user has not seen. Do not change stock or AP posting.

**Done when.**

Selecting an item with a master HSN fills HSN and GST % and posts those values if the user does not edit. A user-typed rate is the posted rate. An upload mismatch is visible before Complete. An unmatched upload line stays editable and cannot complete with a blank item. Existing purchase complete tests stay green. Line-fill unit test. Upload fixture with one matched line and one unknown line.

**Test.** `test_bug_cog_008` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Estimate: typed line fields 5 → 2 (item, qty) when the master matches. First-paint inputs 28 → about 12.

<a id="bug-cog-009"></a>

### BUG-COG-009. Raw ITC Eligibility Enum Exposes Users to Statutory Tax Audit Risk

> **Triage 2026-10-04: UX PROPOSAL.** ITC control is the raw enum; no blocked-category recommendation. Open.

**Severity**: P1. **Order in wave**: 13. **Domain**: Cognitive load.

**Alias**: CL-09.

**Failure.**

The judgment is shown as a control instead of a conclusion.

**If it stays.** Wrong ITC is a tax error, often found at GSTR-2B.

**Change.**

- Default remains `CLAIMABLE`. Chip: "GST you can claim on this bill."
  - If any line's HSN or item flag is on a blocked list, the chip recommends "GST not claimable" and one sentence names the line. The stored value becomes `INELIGIBLE` only after the user accepts the recommendation or leaves it accepted.
  - Do not silently flip a previously saved `CLAIMABLE` bill on edit. Show the chip first.
  - Override to Reversed stays in the advanced block.

**Files.**

- `web/src/pages/purchases/NewPurchasePage.tsx` (`itcEligibility`)
  - A small eligibility helper
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Ships with.** After BUG-COG-008 and BUG-PUR-010. The screen explains ITC. It does not invent a new posting rule.

**Depends on.** `itcEligibility` already defaults to `CLAIMABLE`. If no blocked list is shipped yet, ship the chip and the override, and leave the recommendation as a follow-up. Do not fake a block list. A blocked list that would change ITC on bills the user never looks at needs a founder decision. The safe version is: recommend, show the chip, post what the chip says at save time because the user can see it.

**Done when.**

Ordinary lines: chip says claimable, posted value `CLAIMABLE`, no extra click. The user can switch. Saved eligibility equals the chip at save. Edit of an old bill shows the saved value, not a new inference, until the user accepts a recommendation. Helper tests for default, recommended ineligible, and "do not override a saved value until accept".

**Test.** `test_bug_cog_009` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Ordinary bills: 0 ITC decisions. Mixed bills: a recommendation the user can see.

<a id="bug-cog-004"></a>

### BUG-COG-004. Active Non-Default Statutory Configurations Hidden Inside Collapsed Drawer

> **Triage 2026-10-04: UX PROPOSAL.** No non-default chips; tax options sit behind `showAdvancedTax`. Open.

**Severity**: P0. **Order in wave**: 14. **Domain**: Cognitive load.

**Alias**: CL-04.

**Failure.**

Collapse hides state as well as controls. A bill can be SEZ or reverse charge without that fact on the header.

**If it stays.** Rare bills. High error cost when the hidden value is wrong.

**Change.**

Under the More tax options link, render a chip row only when something is off the default:
  - Supply type other than B2B. Shop language on the chip ("SEZ, GST charged" / "SEZ, no GST" / "Export, GST charged"). The code stays on the help line.
  - A non-primary company GSTIN selected.
  - A cost centre selected.
  - E-commerce GSTIN non-empty.
  - Sales RCM on.
Each chip click opens the block. RCM still requires the existing confirm checkbox before Complete. Defaults that show no chip: supply B2B, primary GSTIN, empty cost centre, empty e-commerce GSTIN, RCM off.

**Files.**

- `web/src/pages/sales/NewInvoicePage.tsx` (`showAdvancedTax`)
  - `web/src/pages/purchases/NewPurchasePage.tsx`
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Depends on.** Existing `showAdvancedTax` collapse. Sales RCM still uses `confirmSalesRcm`. Purchase mirror is the purchase equivalents; ITC is CL-09 and place of supply is CL-07.

**Gate.** Chips for non-default statutory values can ship. Hiding the underlying controls on production waits for GD-33.

**Done when.**

A plain bill shows no chip. Turning on RCM shows a chip and Complete stays disabled until the confirm checkbox is ticked. SEZ with payment shows a chip. English and Hindi. Component tests for the five non-default cases and the all-default case.

**Test.** `test_bug_cog_004` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** A plain bill shows nothing extra. A non-plain bill shows a chip the expert can reopen. Novices are not asked to learn SEZ on day one.

<a id="bug-ui-015"></a>

### BUG-UI-015. "Save & New" Action Hard-Blocked on Draft Invoices

> **Triage 2026-10-04: CONFIRMED.** DocumentEditorShell.tsx:248 disables Save & New unless canComplete (and in edit mode).

**Severity**: P2. **Order in wave**: 15. **Domain**: Web and hardware.

**Failure.**

The "Save & New" button in `DocumentEditorShell` is disabled whenever `!canComplete` evaluates to true (`disabled={saving || !canComplete}`).

**If it stays.** In batch data-entry operations where clerks prepare multiple draft vouchers for later review and approval, clerks cannot use "Save & New" to quickly save a draft and begin the next voucher. They are forced to save as draft, exit to document list, and click "New Invoice" again.

**Change.**

Decouple "Save & New" from `canComplete` so that drafting workflows can trigger "Save as Draft & New":
```tsx
<button
  disabled={saving || (!canSaveDraft && !canComplete)}
  onClick={canComplete ? onSaveAndNew : onSaveDraftAndNew}
>
  {canComplete ? "Save & New" : "Save Draft & New"}
</button>
```

**Files.**

`web/src/components/billing/DocumentEditorShell.tsx`

**Done when.**

`test_bug_ui_015` fails on today's code and passes after the change. The test shows this failure is gone: In batch data-entry operations where clerks prepare multiple draft vouchers for later review and approval, clerks cannot use "Save & New" to quickly save a draft and begin the next voucher. They are forced to save as draft, exit to…

**Test.** `test_bug_ui_015` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-010"></a>

### BUG-COG-010. Fragmented Period Close Navigation Creates Month-End Anxiety

> **Triage 2026-10-04: UX PROPOSAL.** Close controls are on PeriodsPage only; no unified hub. Open.

**Severity**: P1. **Order in wave**: 16. **Domain**: Cognitive load.

**Alias**: CL-10.

**Failure.**

Each worksheet is a destination. The job is one period.

**If it stays.** Monthly, for the CA and the bookkeeper. High anxiety. Memory load is the period, the GSTIN, and which worksheet is a filing aid.

**Change.**

One page, "Close the month". Each row opens the existing report in place or by a deep link that returns. A single line at the top: these worksheets are for the CA. Filing on the portal is a separate step. Do not imply the product filed anything. The form code is secondary text. The row title is shop language ("Sales for the month", "Tax to pay"). Export pack groups today's downloads. No new file format.

  | Row | Who sees it | Existing surface |
  |---|---|---|
  | Outward supplies | Regular taxpayer | GSTR-1 worksheet |
  | Tax payable | Regular | GSTR-3B worksheet |
  | Purchases to match | When `ENABLE_GSTR_EXTENDED` and 2B is available | GSTR-2B page |
  | Composition statement | Composition registration | CMP-08 path if present |
  | Missing documents | Everyone who can close | Missing-documents report |
  | Books health | Accountant / owner | Books-health report |

**Files.**

- New page under `web/src/pages/reports/`, route in `App.tsx`, a new child under reports (not a sidebar restructure)
  - Existing: GSTR-1 worksheet, GSTR-3B worksheet, `web/src/pages/reports/Gstr2bPage.tsx`, missing-documents report, books-health report, CMP-08 path if present
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Ships with.** One period-close hub. BUG-ACC-019 is the single books-and-GST action inside it.

**Depends on.** Existing report pages. `ENABLE_GSTR_EXTENDED` for the 2B row. Registration type hides rows that do not apply. Linked from Reports and from the owner morning list (CL-19) when the month has turned. Pilot filing stays a worksheet. Live GSP submit stays off.

**Leave unchanged.** Enable live filing. Do not merge the worksheets into one incorrect total.

**Done when.**

A regular taxpayer sees outward supplies, tax payable, missing documents, and books health. The 2B row appears only when the flag is on. A composition taxpayer does not get GSTR-1 as the primary row. Each row reaches the existing report. Export bytes match that report's own export. The worksheet disclaimer is visible without opening help. Route test for the two registration types and the flag off/on.

**Test.** `test_bug_cog_010` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Estimate: 5–6 navigation transitions → 1 page, with panels inside. Forms the user must name: 3 or more acronyms → 1 checklist, codes as secondary text.

<a id="bug-acc-019"></a>

### BUG-ACC-019. Books Close and GST Close Are Separate Buttons

> **Triage 2026-10-04: CONFIRMED.** phase/PeriodsPage.tsx has a separate GST soft-close mutation next to the books close.

**Severity**: P3. **Order in wave**: 17. **Domain**: Accounting.

**Failure.**

The page offers two closes. Warnings appear only after one of them runs.

**If it stays.** Filing and posting can be frozen on different months.

**Change.**

Offer one action that closes books and GST for the month, with one confirmation.

**Files.**

`web/src/pages/accounting/PeriodsPage.tsx`

**Ships with.** Ship with BUG-COG-010.

**Done when.**

`test_bug_acc_019` fails on today's code and passes after the change. The test shows this failure is gone: Filing and posting can be frozen on different months.

**Test.** `test_bug_acc_019` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-011"></a>

### BUG-COG-011. User Access Management Requires Manual 8-Checkbox Matrix Configuration

> **Triage 2026-10-04: UX PROPOSAL.** UsersSettingsPage already has `capsForRole` role presets. Partly shipped.

**Severity**: P1. **Order in wave**: 18. **Domain**: Cognitive load.

**Alias**: CL-11.

**Failure.**

Adding a team member exposes the permission grid with no role preset.

**If it stays.** Every new staff member. Owner anxiety about giving away the books. A tired pass through the grid grants more than the job needs.

**Change.**

Four templates that call the existing permission helpers. "Custom" opens today's grid. The next new user defaults to the last template chosen on this company. Existing users are not rewritten when the page loads.

  | Template | Intent | Must not include |
  |---|---|---|
  | Cashier | POS and sales create | GST settings, user admin, financial reports beyond the counter |
  | Store | Purchases and stock | User admin, GST settings |
  | Bookkeeper | Purchases, receipts, reports, GST worksheets | User admin |
  | Owner | Current owner set | — |

**Files.**

- `web/src/pages/settings/UsersSettingsPage.tsx`
  - A `roleTemplates.ts` with tests
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Depends on.** Existing permission helpers. No new security model and no new permission bit. Prefer a server-saved last template if a field already exists. Otherwise local is acceptable and must be labelled "on this browser". The PR includes a mapping table so a reviewer can diff the checkbox set.

**Leave unchanged.** Add a permission bit. Do not change `canCreateSales` and the other helpers.

**Done when.**

Choosing Cashier produces the checkbox set in the mapping table, and that user cannot open GST settings or user admin. Custom can still reproduce a combination that exists today. Loading the page does not PATCH existing users. Unit test: each template → permission flags. Component test: switching template updates the grid. One test that load does not rewrite existing users.

**Test.** `test_bug_cog_011` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Estimate: about 8 decisions → 1 for the common case.

<a id="bug-cog-012"></a>

### BUG-COG-012. Unlocked GST Settings Allow Accidental Company-Wide Tax Corruption

> **Triage 2026-10-04: UX PROPOSAL.** GstSettingsPage already confirms registration changes (window.confirm at lines 205/216). Largely shipped.

**Severity**: P1. **Order in wave**: 19. **Domain**: Cognitive load.

**Alias**: CL-12.

**Failure.**

Setup and day-to-day editing share one open form.

**If it stays.** Low frequency, very high error risk.

**Change.**

After GSTIN, registration type, and state are saved and valid, the page shows a summary (GSTIN, type, state, and price mode if it lives here). "Change tax setup" opens the form. The first change of registration type or GSTIN requires a confirm that says future bills follow the new setup and bills already issued do not change.

**Files.**

- `web/src/pages/settings/GstSettingsPage.tsx`
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Depends on.** A valid saved GSTIN, registration type, and state. In-progress invoice drafts keep the type they already resolved under CL-01 until the user reopens them.

**Leave unchanged.** Mutate posted invoices. Do not add a new GST rule.

**Done when.**

Summary is the first view when setup is complete. Confirm names the effect. Cancel returns to the summary with the old values. In-progress drafts keep their already resolved type. axe clean. Component test: complete setup renders the summary. Confirm is required for a registration-type change.

**Test.** `test_bug_cog_012` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Accidental edits become deliberate. The summary is what the owner sees on a later visit.

<a id="bug-cog-013"></a>

### BUG-COG-013. Dense Products Catalog Overwhelms Initial Visual Search

> **Triage 2026-10-04: UX PROPOSAL.** ProductsPage has about 8 filter/field controls and no search-first layout. Open.

**Severity**: P1. **Order in wave**: 20. **Domain**: Cognitive load.

**Alias**: CL-13.

**Failure.**

Maintenance tools are peers of the two jobs people open the page for: find an item, or add one.

**If it stays.** Item maintenance. Less often than billing, still the highest choice count.

**Change.**

Primary: the search box and Add item. Import, bulk edit, and attribute tools move into one menu. Do not remove a column the billing line needs from the item record. Opening stock, lots, and serials stay behind the existing button in the item dialog.

**Files.**

- `web/src/pages/inventory/ProductsPage.tsx`
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Depends on.** A2-7 already shortened item create (name, selling price, GST %. Lots behind a button). Default item create scores about 1.9. This row is the page around that dialog. The static scan counted 122 choices and about 58 buttons.

**Done when.**

Add item still opens the short form. A keyboard user can reach import. No required item field is dropped from the API payload of the dialog. Existing item-dialog tests stay green. One render test that the first heading-level actions are search and add.

**Test.** `test_bug_cog_013` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Default create stays near 1.9. The page stops competing with the dialog.

<a id="bug-cog-017"></a>

### BUG-COG-017. Bank Reconciliation Forces Manual Confirmation of Obvious 1:1 Matches

> **Triage 2026-10-04: UX PROPOSAL.** Blocked by design: needs a written founder decision in docs/ux/founder_decisions.md before any code.

**Severity**: P2. **Order in wave**: 21. **Domain**: Cognitive load.

**Alias**: CL-17.

**Failure.**

The safety rule "never auto-apply an ambiguous match" was applied to unique matches too.

**If it stays.** Bookkeeper, at month end. Decisions that are already unique still interrupt.

**Change.**

Build this only after a founder line exists in `docs/ux/founder_decisions.md`. This posts a match and there is no undo (D-UX-3).

1. A candidate that is unique on amount and inside the existing date tolerance is applied with the same post the user would confirm today.
2. Two or more candidates stay in a queue. The user decides.
3. Page title: "Match bank lines." Help can say the GL screen is different. The subtitle does not teach both jobs at once.
4. The operational match screen and `AccountingBankReconPage` stay two products.

**Files.**

- `web/src/pages/payments/BankReconPage.tsx` (operational match)
  - GL screen keeps its own name (`AccountingBankReconPage`)

**Ships with.** Blocked until `docs/ux/founder_decisions.md` records the decision. BUG-ACC-017 (cross-links and labels) can ship earlier and does not auto-post.

**Depends on.** Needs a founder decision before any code. Write the decision into `docs/ux/founder_decisions.md` first.

**Gate.** No code until the founder decision is written. Two products stay two products.

**Done when.**

Two receipts with the same amount stay unapplied. A single exact candidate posts and appears in the matched list. No journal side effect beyond today's match action.

**Test.** `test_bug_cog_017` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Decisions fall to the collisions only.

<a id="bug-cog-018"></a>

### BUG-COG-018. Mobile Field Sales Order Lacks Customer Credit and Stock Context Strip

> **Triage 2026-10-04: UX PROPOSAL.** No credit/stock context strip on the sales order editor. Open.

**Severity**: P2. **Order in wave**: 22. **Domain**: Cognitive load.

**Alias**: CL-18.

**Failure.**

Those facts live on the customer ledger and the stock page. The order screen does not bring them in.

**If it stays.** Every site visit. The booker leaves the order, or phones the shop, while the customer waits.

**Change.**

A strip on the order: they owe (outstanding), credit left, stock in the selected godown for the highlighted line, and offline outbox count or "last synced at {time}" when the figures are cached. The strip must not cover the save button at 393px. A missing figure says it is unknown rather than zero, when the API distinguishes those.

**Files.**

- Sales order editor (`SalesOrderEditorPage.tsx` / `NewSalesOrderPage.tsx`)
  - `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`

**Depends on.** Outstanding, credit left, and godown stock already exist on other screens. Offline must not invent those figures. Label the sync time. The API distinction between unknown and zero must be preserved.

**Leave unchanged.** Invent stock or credit when offline.

**Done when.**

Strip visible at 393px. Stale cache shows the time. A missing figure is labelled unknown when the API says so. The primary save stays visible.

**Test.** `test_bug_cog_018` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** Fewer trips to the customer ledger and the stock page.

<a id="bug-cog-019"></a>

### BUG-COG-019. Proprietor Lacks a Consolidated 5-Minute Morning Command Hub

> **Triage 2026-10-04: UX PROPOSAL.** No morning hub page found (Attention exists). Open.

**Severity**: P2. **Order in wave**: 23. **Domain**: Cognitive load.

**Alias**: CL-19.

**Failure.**

The morning question is one list. The product answers with modules.

**If it stays.** Daily, short session, often under interruption.

**Change.**

At most five rows, each one action:
  1. Dues to chase (collections / outstanding).
  2. Bills held for credit override.
  3. Low stock.
  4. Setup still blocking the first real bill.
  5. Period-close row when the month has rolled and the CL-10 checklist is not done.
A quiet day says nothing is waiting and offers New bill and POS. An empty company shows setup only.

**Files.**

- `web/src/pages/DashboardPage.tsx`
  - `web/src/pages/AttentionPage.tsx`

**Depends on.** Queries that already exist for collections, credit holds, low stock, and setup. The fifth row needs CL-10. Keep the existing low-stock `<=` rule (D-UX-1). Collections copy stays in owner language (A3-5). Prefer extending Attention over a third list. This is not a forecast.

**Leave unchanged.** Add a prediction or dunning model.

**Done when.**

Each row deep-links to the existing screen. No row appears when its count is zero. Quiet state has the two links. Empty company sees setup only.

**Test.** `test_bug_cog_019` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

**Expected benefit.** A five-minute session has one screen. A quiet day does not invent work.

<a id="bug-cog-g01"></a>

### BUG-COG-G01. Lead-to-Cash Broken Handoff (Forces Re-entry of Quote, Items & Pricing)

**Severity**: P0. **Order in wave**: 24. **Domain**: Cognitive load.

**Alias**: CL-G01.

**Failure.**

Converting a qualified lead creates a `Customer` and an `Opportunity`, but halts there. It provides zero direct pathway to generate a Quotation, Sales Order, or Invoice with captured requirements.

**If it stays.** Sales reps must navigate away to /sales/quotations/new, re-search the newly created customer, and manually re-type items, quantities, and agreed prices discussed in the CRM.

**Change.**

Add a direct 1-click action in the Lead Conversion modal: `[Convert & Create Quotation]` or `[Convert & Create Sales Order]`. The target document editor opens with the customer, contact person, billing address, and pre-selected opportunity lines pre-filled.

**Files.**

- `web/src/pages/crm/LeadsPage.tsx` (`convertLead`)
  - `web/src/pages/sales/QuotationsPage.tsx`

**Ships with.** After BUG-CRM-003 and BUG-CRM-005. Won requires a customer. The screen can draft a quotation or an invoice.

**Done when.**

One click from a converted lead opens a pre-populated quotation draft without manual re-entry.

**Test.** `test_bug_cog_g01` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-g02"></a>

### BUG-COG-G02. Customer Complaint Resolution Disconnected from Credit Note Generation

**Severity**: P0. **Order in wave**: 25. **Domain**: Cognitive load.

**Alias**: CL-G02.

**Failure.**

When resolving an approved complaint with a credit note or goods return, the user must manually select from an unpaginated 20-invoice dropdown, manually find `sourceItem` ID, and manually re-enter unit price and quantity.

**If it stays.** High cognitive fatigue and extreme error risk of issuing credit notes with wrong tax buckets, wrong HSN codes, or mismatched original invoice rates.

**Change.**

Auto-populate complaint item lines from the original sales invoice selected during complaint logging. Provide a single primary action: `[Issue Credit Note]`, which navigates directly to `NewCreditNotePage` prefilled with customer, invoice ID, returned item, original tax rate, and godown.

**Files.**

`web/src/pages/complaints/ComplaintsPage.tsx` (`ComplaintDetail`)

**Ships with.** After BUG-CMP-002 and BUG-COG-006. One prefill path into the credit note.

**Done when.**

Approved complaint transitions directly into a pre-filled credit note draft with intact original tax math.

**Test.** `test_bug_cog_g02` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-g03"></a>

### BUG-COG-G03. HTML5 Drag-and-Drop Kanban Pipeline Completely Fails on Mobile Viewports

**Severity**: P1. **Order in wave**: 26. **Domain**: Cognitive load.

**Alias**: CL-G03.

**Failure.**

Pipeline stages rely exclusively on desktop HTML5 mouse drag-and-drop events (`onDragOver`, `onDrop`). Touchscreens cannot fire HTML5 drag events. Additionally, rendering 5 horizontal Kanban columns on a 393px phone screen causes illegible squishing.

**If it stays.** Field sales reps and mobile proprietors cannot update deal stages from smartphones or tablets.

**Change.**

On viewports $< 768\text{px}$, transform the board into a stacked card list with a clear Stage Transition Dropdown / Bottom Sheet on each deal card: `Move to: [ Qualified | Negotiation | Won | Lost ]`.

**Files.**

`web/src/pages/crm/OpportunityPipelinePage.tsx` (`dropOn`)

**Done when.**

Deal stages can be smoothly advanced via touch taps on mobile devices without horizontal overflow.

**Test.** `test_bug_cog_g03` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-g04"></a>

### BUG-COG-G04. Unconfirmed Immediate Deal Closure and Contract Cancellation

**Severity**: P1. **Order in wave**: 27. **Domain**: Cognitive load.

**Alias**: CL-G04.

**Failure.**

Dragging a deal into `WON` or `LOST`, or clicking cancel on an AMC/warranty contract immediately mutates status on the backend with zero confirmation or validation dialog (`BUG-UI-025`).

**If it stays.** Accidental slips permanently close active deals or terminate customer contracts without an audit trail or capture of loss reasons.

**Change.**

Render a lightweight confirmation modal capturing commercial context:
  - *Opportunity Won*: Confirm final deal value and prompt: `[Create Sales Order Now]`.
  - *Opportunity Lost*: Require selecting a Lost Reason (`Price`, `Competitor`, `Budget`, `Feature Gap`).
  - *Contract Cancel*: Require explicit confirmation detailing the termination effective date.

**Files.**

- `web/src/pages/crm/OpportunityPipelinePage.tsx` (`move.mutate`)
  - `web/src/pages/contracts/ContractsPage.tsx`

**Ships with.** Ship with BUG-UI-025.

**Done when.**

State transitions to terminal states require explicit confirmation with captured reasons.

**Test.** `test_bug_cog_g04` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-025"></a>

### BUG-UI-025. Cancel Contract, Delete an Attachment, and Move to Won or Lost Need No Confirm

> **Triage 2026-10-04: CONFIRMED.** ContractsPage.tsx:170 sets CANCELLED directly on click.

**Severity**: P2. **Order in wave**: 28. **Domain**: Web and hardware.

**Failure.**

These actions mutate immediately. Campaign delete is **BUG-UI-012**. POS clear-cart is **BUG-UI-010**. Typed confirms are **BUG-UI-005**. Project close is **BUG-UI-017**. Asset dispose is **BUG-ACC-018**. Job-card invoice confirm is part of **BUG-WRK-006**.

**If it stays.** A mis-tap cancels a contract, drops evidence, or closes a deal.

**Change.**

Confirm those three actions.

**Files.**

- `web/src/pages/contracts/ContractsPage.tsx` sets status `CANCELLED` on click
  - `web/src/pages/growth/widgets.tsx` attachment delete
  - `web/src/pages/crm/OpportunityPipelinePage.tsx` WON and LOST

**Ships with.** Same confirm as BUG-COG-G04. Won, lost, and contract cancel share one dialog.

**Done when.**

`test_bug_ui_025` fails on today's code and passes after the change. The test shows this failure is gone: A mis-tap cancels a contract, drops evidence, or closes a deal.

**Test.** `test_bug_ui_025` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-g05"></a>

### BUG-COG-G05. Absence of Search, Date Horizons, and Entity Filtering Across Growth OS Registers

**Severity**: P1. **Order in wave**: 29. **Domain**: Cognitive load.

**Alias**: CL-G05.

**Failure.**

Listing screens execute unparameterized queries without text search bars, date range filters (Current Month, FY, custom), or customer entity autocompletes (`BUG-UI-030`).

**If it stays.** Once records exceed 20 rows, users are forced to perform manual visual scans across pageless tables to locate specific tickets, contracts, or complaints.

**Change.**

Implement a unified `GrowthFilterBar` providing: (1) Free-text search, (2) Asynchronous Customer autocomplete, (3) Status filter chips, and (4) Date/Expiry horizons (e.g. "Expiring in 30 days" for contracts; "SLA Breached" for tickets).

**Files.**

- `web/src/pages/crm/OpportunitiesPage.tsx`
  - `web/src/pages/support/TicketsPage.tsx`
  - `web/src/pages/complaints/ComplaintsPage.tsx`
  - `web/src/pages/contracts/ContractsPage.tsx`

**Ships with.** Ship with BUG-UI-020 and BUG-UI-030.

**Done when.**

Filter bar allows isolating records by customer, status, and date horizon in $< 2$ clicks.

**Test.** `test_bug_cog_g05` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-020"></a>

### BUG-UI-020. CRM, Tickets, Contracts, and Complaints Fetch a Fixed Page and Show No Pager

> **Triage 2026-10-04: CONFIRMED.** Tickets 100, contracts 50, complaints 50 fixed pages; no TablePagination.

**Severity**: P2. **Order in wave**: 30. **Domain**: Web and hardware.

**Failure.**

The queries request one large page. The screens have no `TablePagination` or load-more.

**If it stays.** Rows past the cap cannot be reached, or the page is one long unscanned list.

**Change.**

Add pagination and show the total.

**Files.**

`web/src/pages/support/TicketsPage.tsx` (`pageSize: 100`). Campaigns and pipeline use 100. Contracts and complaints use 50. Lead customer cap is **BUG-UI-016**. Bundle size is **BUG-PERF-007**.

**Ships with.** Ship with BUG-COG-G05. One GrowthFilterBar, one pager, one total.

**Done when.**

`test_bug_ui_020` fails on today's code and passes after the change. The test shows this failure is gone: Rows past the cap cannot be reached, or the page is one long unscanned list.

**Test.** `test_bug_ui_020` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-030"></a>

### BUG-UI-030. Total Absence of Search and Filter Dimensions Across Growth OS Screens

> **Triage 2026-10-04: PARTIAL.** OpportunitiesPage has no search/stage filter and GrowthFilterBar does not exist; ComplaintsPage already has status and category filters.

**Severity**: P1. **Order in wave**: 31. **Domain**: Web and hardware.

**Failure.**

Growth OS listing screens call unparameterized or minimally parameterized `listXPage({ pageSize: 50/100 })` endpoints without search inputs, date range pickers, or entity lookups.

**If it stays.** As soon as customer complaints, support tickets, contracts, or deals exceed 20 rows, staff cannot find specific records, track SLA breaches, or filter upcoming contract renewals.

**Change.**

Add search and stage / expected-close filters to `OpportunitiesPage`, and search to `CampaignsPage`. `ComplaintsPage` already has status and category filters. `GrowthFilterBar` (BUG-COG-G05) does not exist yet, so build it once there and reuse it here.

**Files.**

- `web/src/pages/crm/OpportunitiesPage.tsx` (No search, no stage filter, no expected close month filter)
  - `web/src/pages/crm/CampaignsPage.tsx` (No search, no campaign type filter, no active status filter)
  - `web/src/pages/complaints/ComplaintsPage.tsx` (No search bar, no customer filter, no invoice # filter, no date range)
  - `web/src/pages/complaints/SupplierComplaintsPage.tsx` (No search bar, no supplier filter, no purchase bill # filter, no date range)
  - `web/src/pages/support/TicketsPage.tsx` (No search bar, no customer filter, no status dropdown, no SLA breached filter, no date filter)
  - `web/src/pages/contracts/ContractsPage.tsx` (No search bar, no customer filter, no contract type filter, no 30/60/90-day expiry horizon)

**Ships with.** Ship with BUG-COG-G05.

**Done when.**

Web tests show each of the three pages filters by text and by its main dimension without refetching unrelated pages.

**Test.** `test_bug_ui_030` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-g06"></a>

### BUG-COG-G06. Contract Expiry Attention Fails to Offer One-Click Renewal Invoicing

**Severity**: P1. **Order in wave**: 32. **Domain**: Cognitive load.

**Alias**: CL-G06.

**Failure.**

When a contract (AMC, warranty, subscription) approaches expiry, the system notifies the user on the Attention page, but provides no direct action to renew the contract or invoice the customer.

**If it stays.** Bookkeepers must navigate to /sales/new, re-select the customer, look up contract rates, and manually key start/end dates into invoice line descriptions.

**Change.**

Add a prominent `[Renew & Generate Invoice]` action on contract rows. Clicking this opens `NewInvoicePage` with: customer pre-selected, contract product line added, renewal period stated in description, and linked recurring schedule configured.

**Files.**

- `web/src/pages/contracts/ContractsPage.tsx`
  - `web/src/pages/AttentionPage.tsx`

**Ships with.** After BUG-CNT-002. The screen action creates the recurring invoice the service already owes.

**Done when.**

Contract renewal directly drafts a sales invoice with correct party and service parameters.

**Test.** `test_bug_cog_g06` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-g07"></a>

### BUG-COG-G07. Support Ticket SLA Breach Indicators Lack Elapsed Time & Paused Context

**Severity**: P1. **Order in wave**: 33. **Domain**: Cognitive load.

**Alias**: CL-G07.

**Failure.**

Ticket rows display static status chips without indicating remaining SLA duration or clarifying that the SLA clock is paused when status is set to `WAITING` (waiting for customer feedback).

**If it stays.** Support staff experience false urgency, or mistakenly leave customer-blocked tickets to breach SLAs because the pause mechanism is invisible.

**Change.**

Replace static text with dynamic contextual SLA badges:
  - *Active SLA*: `[ 2h 15m remaining ]` (Green $\rightarrow$ Amber $\rightarrow$ Red).
  - *Paused SLA*: `[ Clock Paused: Waiting on Customer ]` (Grey / Informational).
  - *Breached*: `[ Breached by 45m ]` (Red with error tone).

**Files.**

`web/src/pages/support/TicketsPage.tsx`

**Done when.**

Ticket queue visibly distinguishes between running SLA timers, paused states, and breached deadlines.

**Test.** `test_bug_cog_g07` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-g08"></a>

### BUG-COG-G08. Growth OS First-Run Experience Presents an Uninformative Empty Desert

**Severity**: P2. **Order in wave**: 34. **Domain**: Cognitive load.

**Alias**: CL-G08.

**Failure.**

All Growth OS screens share a single generic empty sentence: "Nothing here yet" (`BUG-UI-023`). The Opportunity Pipeline renders 5 blank grey columns with zero instructions.

**If it stays.** New users exploring CRM or Service modules cannot discern the module's business purpose or how to begin.

**Change.**

Build dedicated empty states for each Growth OS surface:
  - *Pipeline*: "Track deals from initial pitch to closed sale. [Add First Deal]".
  - *Contracts*: "Manage warranties, AMCs, and recurring service agreements. [Add First Contract]".
  - *Complaints*: "Log customer issues and generate GST return credit notes seamlessly. [Log Customer Complaint]".

**Files.**

`t('growth.nothingYet')` in `web/src/pages/complaints/ComplaintsPage.tsx`, `web/src/pages/support/TicketsPage.tsx`, `web/src/pages/contracts/ContractsPage.tsx`, `web/src/pages/crm/OpportunityPipelinePage.tsx`

**Ships with.** Ship with BUG-UI-023.

**Done when.**

First-run empty states communicate the core business benefit and present a single prominent CTA.

**Test.** `test_bug_cog_g08` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-023"></a>

### BUG-UI-023. Growth Modules Share One Empty Sentence, and the Pipeline Has None

> **Triage 2026-10-04: CONFIRMED.** `growth.nothingYet` is used on many pages (10 usages).

**Severity**: P2. **Order in wave**: 35. **Domain**: Web and hardware.

**Failure.**

One generic empty string. The pipeline handles loading and error and never an empty board.

**If it stays.** A new user sees "Nothing here yet" or a blank kanban.

**Change.**

Write a per-screen empty state with the create action.

**Files.**

`t('growth.nothingYet')` on job cards, contracts, tickets, campaigns, complaints, insurance, referrals, and projects. `web/src/pages/crm/OpportunityPipelinePage.tsx` renders five empty columns.

**Ships with.** Ship with BUG-COG-G08. One empty-state component.

**Done when.**

`test_bug_ui_023` fails on today's code and passes after the change. The test shows this failure is gone: A new user sees "Nothing here yet" or a blank kanban.

**Test.** `test_bug_ui_023` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-g09"></a>

### BUG-COG-G09. Customer 360 Workspace Functions as a Read-Only Dead End

**Severity**: P2. **Order in wave**: 36. **Domain**: Cognitive load.

**Alias**: CL-G09.

**Failure.**

Customer 360 aggregates financial dues, ticket history, open contracts, and CRM deals, but provides zero contextual transaction creation actions.

**If it stays.** After reviewing a customer's history, the operator must leave the 360 dashboard, find the relevant sidebar module, and re-select the customer to take action.

**Change.**

Add a quick-action command bar to the Customer 360 header: `[ + New Invoice ]`, `[ + New Quotation ]`, `[ + Log Ticket ]`, `[ + Add Contract ]`. Clicking any button opens that creation flow with the customer automatically bound.

**Files.**

`web/src/pages/sales/Customer360Page.tsx`

**Done when.**

Operators can initiate sales, service, or contract documents directly from Customer 360 without navigating the sidebar.

**Test.** `test_bug_cog_g09` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-cog-g10"></a>

### BUG-COG-G10. Referral Reward Approval Disconnected from Financial Settlement

**Severity**: P2. **Order in wave**: 37. **Domain**: Cognitive load.

**Alias**: CL-G10.

**Failure.**

Marking a referral reward as `PAID` merely records a flag in the database without adjusting customer receivables, issuing a credit note, or creating a cash payment voucher.

**If it stays.** Store owners assume approving a ₹500 referral reward automatically reduced the customer's balance, leading to accounting discrepancies during payment collection.

**Change.**

When approving a referral reward, prompt for settlement mode:
  1. *Apply to Ledger*: Drafts a ₹500 Credit Note / Incentive Voucher crediting the customer's account.
  2. *Cash/Bank Payout*: Generates an operational Money Out (Payment) entry.
  3. *Settled Outside Bizboard*: Records the flag with explicit explanatory copy that no accounting entry was posted.

**Files.**

`web/src/pages/crm/ReferralsPage.tsx`

**Ships with.** After BUG-CRM-001. The button calls the service. It does not only flip status.

**Done when.**

Approving a referral reward explicitly states its financial effect and allows 1-click credit note generation.

**Test.** `test_bug_cog_g10` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-016"></a>

### BUG-UI-016. Customer Selection in Lead Dialog Hard-Capped at First 200 Records

> **Triage 2026-10-04: CONFIRMED.** LeadsPage.tsx:129 `pageSize: 200`.

**Severity**: P2. **Order in wave**: 38. **Domain**: Web and hardware.

**Failure.**

`customersQuery` calls `listCustomersPage({ page: 1, pageSize: 200 })` and renders a non-searchable native HTML `<select>` element. Any existing customer beyond the first 200 alphabetically cannot be selected when creating or converting leads.

**If it stays.** Sales reps in companies with more than 200 customers cannot link incoming leads to existing client accounts, leading to duplicate customer record creation.

**Change.**

Replace static `<select>` with an asynchronous searchable combobox / autocomplete component (`CustomerAutocomplete`) querying the backend search endpoint with debounce.

**Files.**

- `web/src/pages/crm/LeadsPage.tsx`
  - `web/src/pages/crm/LeadsPage.tsx`

**Done when.**

`test_bug_ui_016` fails on today's code and passes after the change. The test shows this failure is gone: Sales reps in companies with more than 200 customers cannot link incoming leads to existing client accounts, leading to duplicate customer record creation.

**Test.** `test_bug_ui_016` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-018"></a>

### BUG-UI-018. Ticket, Contract, and Complaint Create Dialogs Close Without a Dirty Check

> **Triage 2026-10-04: CONFIRMED.** CreateDialog.tsx passes onClose straight to backdrop and Cancel; no dirty check.

**Severity**: P1. **Order in wave**: 39. **Domain**: Web and hardware.

**Failure.**

Cancel and backdrop call `onClose` with no dirty flag. Those flows are not wrapped in `UnsavedChangesGuard`.

**If it stays.** A half-written ticket, contract, or complaint disappears.

**Change.**

Confirm when the draft is dirty.

**Files.**

`web/src/components/CreateDialog.tsx`. Callers include tickets, contracts, and complaints. Project form bleed is **BUG-UI-001**.

**Done when.**

`test_bug_ui_018` fails on today's code and passes after the change. The test shows this failure is gone: A half-written ticket, contract, or complaint disappears.

**Test.** `test_bug_ui_018` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

## Wave 9. Counter hardware and remaining UI

Printer and scanner work share the POS payload from wave 3. Confirms reuse the dialog from BUG-UI-005. Filters reuse one bar component. Money and dates reuse `formatMoney` and the shared date formatter.

<a id="bug-sales-007"></a>

### BUG-SALES-007. POS Printing Path Restricted to Bluetooth Stub (No WebUSB / Raw TCP Network ESC/POS)

> **Triage 2026-10-04: CONFIRMED.** No WebUSB or raw-socket printing in printPosThermal.ts or lib/native.ts.

**Severity**: P2. **Order in wave**: 1. **Domain**: Sales.

**Failure.**

Thermal receipt printing is implemented only as a Capacitor mobile Bluetooth stub. Direct browser WebUSB and network ESC/POS socket streams are unimplemented.

**If it stays.** Desktop counter billing cannot trigger instant receipt printing on standard USB/Ethernet thermal printers.

**Change.**

Add WebUSB and raw network socket ESC/POS printing drivers.

**Files.**

- `web/src/pages/pos/printPosThermal.ts`
  - `web/src/lib/native.ts`

**Done when.**

`test_bug_sales_007` fails on today's code and passes after the change. The test shows this failure is gone: Desktop counter billing cannot trigger instant receipt printing on standard USB/Ethernet thermal printers.

**Test.** `test_bug_sales_007` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-sales-008"></a>

### BUG-SALES-008. Cash Drawer Kick-Out Pulse and Weighing Scale Integration Missing

> **Triage 2026-10-04: CONFIRMED.** No drawer-kick bytes or Web Serial code in web/src/pages/pos.

**Severity**: P2. **Order in wave**: 2. **Domain**: Sales.

**Failure.**

No standard printer kick pulse (`0x1b 0x70 0x00 0x19 0xfa`) is transmitted upon cash tender completion; no Web Serial API driver exists for electronic RS-232 weighing scales.

**If it stays.** Cashiers must manually unlock cash drawers with physical keys; grocers cannot read weighing scale measurements directly into billing lines.

**Change.**

Embed drawer kick command in ESC/POS byte generator and implement a Web Serial interface for RS-232 scales.

**Files.**

`web/src/pages/pos/PosPage.tsx`

**Done when.**

`test_bug_sales_008` fails on today's code and passes after the change. The test shows this failure is gone: Cashiers must manually unlock cash drawers with physical keys; grocers cannot read weighing scale measurements directly into billing lines.

**Test.** `test_bug_sales_008` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-inv-006"></a>

### BUG-INV-006. Barcode Label Printing Engine Stubs (No ZPL / TSPL Direct Output)

> **Triage 2026-10-04: CONFIRMED.** No ZPL/TSPL output anywhere.

**Severity**: P3. **Order in wave**: 3. **Domain**: Inventory.

**Failure.**

Generating barcode labels renders a basic HTML page. Direct ZPL (Zebra) or TSPL (TCS) raw printer output commands are not generated.

**If it stays.** Warehouse thermal label printers print blurry, unaligned labels when rasterized through browser print dialogs.

**Change.**

Add a raw ZPL string generator endpoint for barcode thermal printers.

**Files.**

`backend/inventory/views.py`

**Done when.**

`test_bug_inv_006` fails on today's code and passes after the change. The test shows this failure is gone: Warehouse thermal label printers print blurry, unaligned labels when rasterized through browser print dialogs.

**Test.** `test_bug_inv_006` in `backend/tests/test_bug_register.py`.

<a id="bug-ui-002"></a>

### BUG-UI-002. Barcode Scanner Wedge Lacks 50ms Inter-Keystroke Timing Detection

> **Triage 2026-10-04: CONFIRMED.** No inter-keystroke timing logic in PosPage.tsx.

**Severity**: P2. **Order in wave**: 4. **Domain**: Web and hardware.

**Failure.**

Enter-key barcode lookup does not measure keystroke latency (<50ms). Fast manual keyboard typing can inadvertently trigger barcode lookup logic.

**If it stays.** Cashiers typing notes or quantities trigger false "Barcode Not Found" modal errors.

**Change.**

Buffer input characters and confirm hardware scanner timing before dispatching barcode lookups.

**Files.**

`web/src/pages/pos/PosPage.tsx` (`tryAddByBarcode`)

**Done when.**

`test_bug_ui_002` fails on today's code and passes after the change. The test shows this failure is gone: Cashiers typing notes or quantities trigger false "Barcode Not Found" modal errors.

**Test.** `test_bug_ui_002` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-003"></a>

### BUG-UI-003. Quantity Multiplier Keypad Parsing Missing in POS Barcode Scanner

> **Triage 2026-10-04: CONFIRMED.** No quantity-prefix (`5*code`) parsing in the POS scan path.

**Severity**: P2. **Order in wave**: 5. **Domain**: Web and hardware.

**Failure.**

Barcode reader requires exact string matching. It cannot parse quantity prefix syntax like `5*8901030383`.

**If it stays.** Cashiers scanning 10 identical items must scan the physical barcode 10 consecutive times.

**Change.**

Add regex parsing for `^(\d+)\*(.+)$` to populate quantity automatically.

**Files.**

`web/src/pages/pos/PosPage.tsx`

**Done when.**

`test_bug_ui_003` fails on today's code and passes after the change. The test shows this failure is gone: Cashiers scanning 10 identical items must scan the physical barcode 10 consecutive times.

**Test.** `test_bug_ui_003` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-004"></a>

### BUG-UI-004. Global Command Palette (Ctrl+K / Cmd+K) Missing

> **Triage 2026-10-04: CONFIRMED.** No command palette component or Ctrl+K handler.

**Severity**: P2. **Order in wave**: 6. **Domain**: Web and hardware.

**Failure.**

No universal keyboard shortcut or command omnibar exists for searching customers, invoices, and navigating modules.

**If it stays.** Heavy keyboard users must reach for the mouse to navigate menus, slowing down power users.

**Change.**

Implement a global command palette triggered by `Ctrl+K`.

**Files.**

`web/src/components/`

**Done when.**

`test_bug_ui_004` fails on today's code and passes after the change. The test shows this failure is gone: Heavy keyboard users must reach for the mouse to navigate menus, slowing down power users.

**Test.** `test_bug_ui_004` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-005"></a>

### BUG-UI-005. Destructive Action Confirmation Dialogs Lack Entity Name Typing

> **Triage 2026-10-04: CONFIRMED.** ConfirmDialog.tsx has no typed-confirmation mode.

**Severity**: P2. **Order in wave**: 7. **Domain**: Web and hardware.

**Failure.**

Destructive actions (cancelling completed invoices, voiding receipts, deleting masters) require only a single button click without typing the entity number/name.

**If it stays.** Operators accidentally cancel critical financial vouchers due to misclicks.

**Change.**

Require users to type `CONFIRM` or the document number before executing destructive cancellations.

**Files.**

`web/src/components/ConfirmDialog.tsx`

**Done when.**

`test_bug_ui_005` fails on today's code and passes after the change. The test shows this failure is gone: Operators accidentally cancel critical financial vouchers due to misclicks.

**Test.** `test_bug_ui_005` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-012"></a>

### BUG-UI-012. Destructive Campaign Removal Executes Instantly Without Confirmation Prompt

> **Triage 2026-10-04: CONFIRMED.** CampaignsPage.tsx:160 calls remove.mutate directly.

**Severity**: P2. **Order in wave**: 8. **Domain**: Web and hardware.

**Failure.**

The "Remove" button in `CampaignsPage` executes `remove.mutate(row.id)` immediately on click without opening a confirmation modal or displaying an undo toast.

**If it stays.** Operators clicking adjacent action buttons (e.g. "Funnel" or "Edit") can accidentally delete marketing campaigns, unlinking historical tracking and metrics.

**Change.**

Guard the mutation with a standard `ConfirmDialog` modal: "Are you sure you want to delete campaign {name}? This will unlink historical campaign conversions."

**Files.**

`web/src/pages/crm/CampaignsPage.tsx`

**Done when.**

`test_bug_ui_012` fails on today's code and passes after the change. The test shows this failure is gone: Operators clicking adjacent action buttons (e.g. "Funnel" or "Edit") can accidentally delete marketing campaigns, unlinking historical tracking and metrics.

**Test.** `test_bug_ui_012` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-009"></a>

### BUG-UI-009. Brittle Regex Entity Extraction in Insights Assistant Causes Customer Name Parsing Failures

> **Triage 2026-10-04: CONFIRMED.** assistant.py:477 greedy regex captures trailing words.

**Severity**: P2. **Order in wave**: 9. **Domain**: Web and hardware.

**Failure.**

The fallback rule extractor uses `re.search(r"(?:to|for)\s+([A-Za-z][A-Za-z0-9 .&'-]{1,60})", content, re.I)`. A prompt like "Draft reminder for Rahul for invoice 101" greedily captures `"Rahul for invoice 101"` as the customer name. A prompt like "Sales totals for March" extracts `"March"` as the customer name.

**If it stays.** Assistant attempts customer ledger queries with garbled names and crashes with "Customer not found in this company."

**Change.**

Terminate customer name extraction at prepositions/keywords (`for`, `on`, `regarding`, `invoice`, `amount`) or validate candidate name against active tenant customer list.

**Files.**

`backend/insights/assistant.py` (`_run_rules_fallback`)

**Done when.**

`test_bug_ui_009` fails on today's code and passes after the change. The test shows this failure is gone: Assistant attempts customer ledger queries with garbled names and crashes with "Customer not found in this company."

**Test.** `test_bug_ui_009` in `backend/tests/test_bug_register.py`.

<a id="bug-ui-021"></a>

### BUG-UI-021. Insurance, Contracts, and Pipeline Show Raw Amounts and ISO Dates

> **Triage 2026-10-04: CONFIRMED.** InsurancePage.tsx:137 renders `String(row.premium)`.

**Severity**: P2. **Order in wave**: 10. **Domain**: Web and hardware.

**Failure.**

These screens interpolate API values. Sales uses `formatMoney` and a date formatter.

**If it stays.** Amounts look like raw strings. Dates stay ISO.

**Change.**

Use the shared money and date formatters.

**Files.**

- `web/src/pages/insurance/InsurancePage.tsx` (`String(row.premium)`)
  - `web/src/pages/contracts/ContractsPage.tsx`
  - `web/src/pages/crm/OpportunityPipelinePage.tsx`

**Done when.**

`test_bug_ui_021` fails on today's code and passes after the change. The test shows this failure is gone: Amounts look like raw strings. Dates stay ISO.

**Test.** `test_bug_ui_021` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-022"></a>

### BUG-UI-022. Line-Delete Buttons on Sales and Purchase Editors Have No Accessible Name

> **Triage 2026-10-04: CONFIRMED.** SalesOrderEditorPage.tsx:685 icon-only DeleteIcon button with no aria-label.

**Severity**: P2. **Order in wave**: 11. **Domain**: Web and hardware.

**Failure.**

The button contains only `DeleteIcon`, with no `aria-label`.

**If it stays.** A screen reader announces "button". The target is smaller than a comfortable touch size.

**Change.**

Add an accessible name and a larger touch target.

**Files.**

- `web/src/pages/sales/SalesOrderEditorPage.tsx`
  - `web/src/pages/purchases/PurchaseOrderEditorPage.tsx`
  - Delivery challan and purchase-note editors use the same icon-only delete

**Done when.**

`test_bug_ui_022` fails on today's code and passes after the change. The test shows this failure is gone: A screen reader announces "button". The target is smaller than a comfortable touch size.

**Test.** `test_bug_ui_022` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-026"></a>

### BUG-UI-026. Feature-Off Screens Are One Sentence, and Not-Ready Errors Replace the Page Title

> **Triage 2026-10-04: CONFIRMED.** `erp.moduleDisabled` is a single sentence on 11 usages.

**Severity**: P2. **Order in wave**: 12. **Domain**: Web and hardware.

**Failure.**

Disabled modules do not explain the gate. Not-ready replaces the screen title.

**If it stays.** There is no path to settings or help, and the failed screen name disappears.

**Change.**

Keep the screen title, explain the gate, and link settings or help when the role allows it.

**Files.**

`t('erp.moduleDisabled')` on job cards, insurance, contracts, tickets, complaints, and projects. `web/src/components/ModuleNotReady.tsx` always uses the generic not-ready heading.

**Done when.**

`test_bug_ui_026` fails on today's code and passes after the change. The test shows this failure is gone: There is no path to settings or help, and the failed screen name disappears.

**Test.** `test_bug_ui_026` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-027"></a>

### BUG-UI-027. Transaction Register Filter Bars Lack Exact Customer / Supplier Autocomplete Dropdown

> **Triage 2026-10-04: CONFIRMED.** HistoryFilterBar filters have q/status/date only; no party selector.

**Severity**: P2. **Order in wave**: 13. **Domain**: Web and hardware.

**Failure.**

Backend `SalesInvoiceViewSet` and `PurchaseInvoiceViewSet` have native support for exact indexed queries (`customer_id` and `supplier_id`), but `HistoryFilterBar` only exposes a free-text input `q`.

**If it stays.** Store operators cannot cleanly select a party to isolate their invoices. Free-text search triggers slow table-wide icontains queries and risks matching unrelated phone numbers or invoice series substrings.

**Change.**

Add an asynchronous Customer / Supplier autocomplete selector directly into `HistoryFilterBar` and bind it to the existing backend query parameters.

**Files.**

- `web/src/components/HistoryFilterBar.tsx`
  - `web/src/pages/sales/SalesHistoryPage.tsx`
  - `web/src/pages/purchases/PurchaseHistoryPage.tsx`

**Done when.**

`test_bug_ui_027` fails on today's code and passes after the change. The test shows this failure is gone: Store operators cannot cleanly select a party to isolate their invoices. Free-text search triggers slow table-wide icontains queries and risks matching unrelated phone numbers or invoice series substrings.

**Test.** `test_bug_ui_027` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-028"></a>

### BUG-UI-028. Missing Indian Financial Year (FY) and Quarterly Date Range Presets in Filter Bars and Reports

> **Triage 2026-10-04: CONFIRMED.** No FY or quarter presets in HistoryFilterBar.

**Severity**: P2. **Order in wave**: 14. **Domain**: Web and hardware.

**Failure.**

Preset dates are hardcoded to western calendar horizons (`today`, `thisWeek`, `last15`, `thisMonth`, `last365`). Indian commercial operations run on the fiscal calendar (`1st April - 31st March`) and quarterly GST return cycles (`Q1: Apr-Jun`, `Q2: Jul-Sep`, `Q3: Oct-Dec`, `Q4: Jan-Mar`).

**If it stays.** Operators and tax accountants must manually compute and enter calendar start and end dates whenever preparing monthly GST filings, quarterly reviews, or year-end reconciliations.

**Change.**

Expand `DATE_RANGE_PRESET_IDS` to include `currentFY`, `previousFY`, and `Q1`-`Q4` presets using an Indian fiscal year offset helper.

**Files.**

- `web/src/components/HistoryFilterBar.tsx` (`DATE_RANGE_PRESET_IDS`, `dateRangeForPreset`)
  - `web/src/pages/reports/SalesReportPage.tsx`
  - `web/src/pages/reports/PurchaseReportPage.tsx`

**Done when.**

`test_bug_ui_028` fails on today's code and passes after the change. The test shows this failure is gone: Operators and tax accountants must manually compute and enter calendar start and end dates whenever preparing monthly GST filings, quarterly reviews, or year-end reconciliations.

**Test.** `test_bug_ui_028` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-029"></a>

### BUG-UI-029. Products Catalog Lacks Category, Brand, Stock Availability, and Tax Slab Filters

> **Triage 2026-10-04: CONFIRMED.** ProductsPage.tsx has no category/brand filter.

**Severity**: P2. **Order in wave**: 15. **Domain**: Web and hardware.

**Failure.**

`ProductsPage` only provides a free-text search box (`search`) and custom field chips (`cfFilters`). It provides zero dropdown filters for Category, Brand, Stock Status (`In Stock`, `Low Stock`, `Out of Stock`, `Negative Stock`), or GST Tax Slabs (`0%`, `5%`, `12%`, `18%`, `28%`).

**If it stays.** Retail and wholesale stores carrying over 1,000 SKUs cannot filter items for reordering, brand inventory counts, or statutory GST rate audits without exporting entire registers to CSV.

**Change.**

Integrate Category, Brand, Stock Availability, and GST Rate dropdown controls into the top filter bar of `ProductsPage`.

**Files.**

`web/src/pages/inventory/ProductsPage.tsx`

**Done when.**

`test_bug_ui_029` fails on today's code and passes after the change. The test shows this failure is gone: Retail and wholesale stores carrying over 1,000 SKUs cannot filter items for reordering, brand inventory counts, or statutory GST rate audits without exporting entire registers to CSV.

**Test.** `test_bug_ui_029` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-031"></a>

### BUG-UI-031. Universal Search Completely Excludes Growth OS Entities and Auxiliary Documents

> **Triage 2026-10-04: CONFIRMED.** backend/search/views.py covers customers, suppliers, products and invoices only.

**Severity**: P2. **Order in wave**: 16. **Domain**: Web and hardware.

**Failure.**

The omnibar search backend queries only `Customer`, `Supplier`, `Product`, and `SalesInvoice`/`PurchaseInvoice`. It omits Quotations, Delivery Challans, Credit Notes, Debit Notes, Payment Receipts, and all Growth OS entities (Tickets, Complaints, Contracts, Leads).

**If it stays.** Entering a valid ticket number, RMA complaint number, AMC contract number, or quotation number into the top navigation bar yields "No results found", confusing users.

**Change.**

Extend `UniversalSearchView` to query Growth OS entities (`Ticket`, `Complaint`, `Contract`, `Opportunity`) and auxiliary sales/purchase documents with appropriate role-based permission checks.

**Files.**

`backend/search/views.py` (`UniversalSearchView`)

**Done when.**

`test_bug_ui_031` fails on today's code and passes after the change. The test shows this failure is gone: Entering a valid ticket number, RMA complaint number, AMC contract number, or quotation number into the top navigation bar yields "No results found", confusing users.

**Test.** `test_bug_ui_031` in `backend/tests/test_bug_register.py`.

<a id="bug-ui-032"></a>

### BUG-UI-032. Sales and Purchase Reports Lack Time Granularity Grouping (Day / Week / Month / FY) and Line-Level Product Filtering

> **Triage 2026-10-04: CONFIRMED.** reporting/views.py group_by is customer-style; no time-bucket grouping.

**Severity**: P2. **Order in wave**: 17. **Domain**: Web and hardware.

**Failure.**

Reports accept only raw `dateFrom` and `dateTo` inputs. The interface lacks controls to group transaction aggregations by Day, Week, Month, or Financial Year, and provides no line-level product or category filter.

**If it stays.** Business owners cannot visualize revenue trends across weeks or months without manually exporting raw transaction dumps and creating pivot tables in external spreadsheet applications.

**Change.**

Add a time-granularity group-by toggle (`[ Day | Week | Month | FY ]`) and product/category filter dropdowns to the Sales and Purchase Report pages.

**Files.**

- `web/src/pages/reports/SalesReportPage.tsx`
  - `web/src/pages/reports/PurchaseReportPage.tsx`
  - `backend/reporting/views.py`

**Done when.**

`test_bug_ui_032` fails on today's code and passes after the change. The test shows this failure is gone: Business owners cannot visualize revenue trends across weeks or months without manually exporting raw transaction dumps and creating pivot tables in external spreadsheet applications.

**Test.** `test_bug_ui_032` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes; `backend/tests/test_bug_register.py`.

## Wave 10. Residual hardening

These are real defects with smaller blast radius. RLS startup failure waits for the wave 1 soak. The other six can ship any time after wave 1.

<a id="bug-sec-008"></a>

### BUG-SEC-008. Missing API Latency and Slow Query Telemetry Logger

> **Triage 2026-10-04: CONFIRMED.** core/middleware.py logs duration_ms only; no slow-request threshold or query-count warning.

**Severity**: P3. **Order in wave**: 1. **Domain**: Security.

**Failure.**

`RequestIdMiddleware` logs request duration, but lacks slow-query thresholds (>500ms), SQL query count logging, and OpenTelemetry span propagation.

**If it stays.** Inability to isolate production performance regressions before they cause outages.

**Change.**

Add automated warnings when a single HTTP request executes >30 database queries or takes >800ms.

**Files.**

`backend/core/middleware.py`

**Done when.**

`test_bug_sec_008` fails on today's code and passes after the change. The test shows this failure is gone: Inability to isolate production performance regressions before they cause outages.

**Test.** `test_bug_sec_008` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-017"></a>

### BUG-SEC-017. Stale Active Company Falls Through to Another Membership

> **Triage 2026-10-04: CONFIRMED.** accounts/views.py:150-156 `_active_membership` falls back to first membership.

**Severity**: P3. **Order in wave**: 2. **Domain**: Security.

**Failure.**

If `active_company_id` does not match a membership, the helper returns `qs.order_by("id").first()` instead of clearing the selection the way `get_company_user` does.

**If it stays.** Login, logout, and password-change audits can be filed against another company.

**Change.**

Clear a stale company and require an explicit pick.

**Files.**

`backend/accounts/views.py` (`_active_membership`)

**Done when.**

`test_bug_sec_017` fails on today's code and passes after the change. The test shows this failure is gone: Login, logout, and password-change audits can be filed against another company.

**Test.** `test_bug_sec_017` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-018"></a>

### BUG-SEC-018. A Viewer Can Be Granted Financial-Report Access

> **Triage 2026-10-04: CONFIRMED.** `can_view_financial_reports` is not in `_VIEWER_FORBIDDEN_CAPS` (accounts/serializers.py:19-30).

**Severity**: P3. **Order in wave**: 3. **Domain**: Security.

**Failure.**

`can_view_financial_reports` is not in the viewer forbidden list. Report APIs honor that capability. Payment list surfaces still deny the viewer role.

**If it stays.** An owner can turn a viewer into a finance reader without using the auditor role.

**Change.**

Add `can_view_financial_reports` to `_VIEWER_FORBIDDEN_CAPS`.

**Files.**

`backend/accounts/serializers.py` (`_VIEWER_FORBIDDEN_CAPS`)

**Done when.**

`test_bug_sec_018` fails on today's code and passes after the change. The test shows this failure is gone: An owner can turn a viewer into a finance reader without using the auditor role.

**Test.** `test_bug_sec_018` in `backend/tests/test_bug_register.py`.

<a id="bug-sec-019"></a>

### BUG-SEC-019. Postgres Row-Level Security Is Off Unless Ops Opts In

> **Triage 2026-10-04: CONFIRMED.** settings.py:981 `POSTGRES_RLS_ENABLED` defaults to "0".

**Severity**: P3. **Order in wave**: 4. **Domain**: Security.

**Failure.**

`POSTGRES_RLS_ENABLED` defaults to false. This is separate from **BUG-SEC-001**, which is Celery tasks that do not set company context when RLS is on.

**If it stays.** A missed company filter is not caught by the database.

**Change.**

Require RLS in production after the soak, or fail startup when it is off.

**Files.**

`backend/config/settings.py`

**Gate.** Turn RLS on in production only after BUG-SEC-001 has soaked. Startup fails closed when production has RLS off.

**Done when.**

`test_bug_sec_019` fails on today's code and passes after the change. The test shows this failure is gone: A missed company filter is not caught by the database.

**Test.** `test_bug_sec_019` in `backend/tests/test_bug_register.py`.

<a id="bug-acc-007"></a>

### BUG-ACC-007. Absence of Multi-Branch / Multi-Store P&L Comparative Reporting

> **Triage 2026-10-04: CONFIRMED.** accounting/reports.py groups by cost centre only; no branch comparative P&L.

**Severity**: P3. **Order in wave**: 5. **Domain**: Accounting.

**Failure.**

P&L reporting groups by company and cost-centre only; it cannot generate side-by-side comparative P&L statements across multiple retail stores with allocated shared overheads.

**If it stays.** Business owners cannot evaluate store-by-store net profitability.

**Change.**

Add a comparative store P&L matrix with overhead distribution keys.

**Files.**

`backend/accounting/reports.py`

**Done when.**

`test_bug_acc_007` fails on today's code and passes after the change. The test shows this failure is gone: Business owners cannot evaluate store-by-store net profitability.

**Test.** `test_bug_acc_007` in `backend/tests/test_bug_register.py`.

<a id="bug-ui-006"></a>

### BUG-UI-006. Sound Feedback Cues Missing on Barcode Scanning

> **Triage 2026-10-04: CONFIRMED.** No audio cue code in pages/pos.

**Severity**: P3. **Order in wave**: 6. **Domain**: Web and hardware.

**Failure.**

No audio cues exist for scan success, duplicate scan, or barcode error.

**If it stays.** Cashiers must keep eyes glued to the monitor to verify item registration rather than focusing on customer packing.

**Change.**

Integrate Web Audio API synthesized beeps (high beep for success, low buzz for error).

**Files.**

`web/src/pages/pos/PosPage.tsx`

**Done when.**

`test_bug_ui_006` fails on today's code and passes after the change. The test shows this failure is gone: Cashiers must keep eyes glued to the monitor to verify item registration rather than focusing on customer packing.

**Test.** `test_bug_ui_006` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

<a id="bug-ui-007"></a>

### BUG-UI-007. Shift+P Privacy Mask Missing from Owner Dashboard

> **Triage 2026-10-04: CONFIRMED.** No privacy-mask hotkey in insights or dashboard.

**Severity**: P3. **Order in wave**: 7. **Domain**: Web and hardware.

**Failure.**

No hotkey exists to mask sensitive currency figures (revenue, net profit, cash in hand) when customers or bystanders stand near the screen.

**If it stays.** Business owners cannot keep the dashboard open at retail counters without exposing confidential financial metrics.

**Change.**

Implement `Shift+P` CSS blur masking on all currency elements.

**Files.**

`web/src/pages/insights/`

**Done when.**

`test_bug_ui_007` fails on today's code and passes after the change. The test shows this failure is gone: Business owners cannot keep the dashboard open at retail counters without exposing confidential financial metrics.

**Test.** `test_bug_ui_007` in `web` unit test next to the page, plus `web/src/i18n/fullParity.test.ts` when copy changes.

---

## 4. Traceability

| Check | Count |
| --- | ---: |
| Findings in BUGS_LIST.md | 212 |
| Closed at triage (already fixed or false positive) | 19 |
| Open findings with a wave and a work package | 193 |
| Open P0 findings | 19 |
| Open P1 findings | 75 |
| Open P2 findings | 78 |
| Open P3 findings | 21 |

A finding is closed only when its Done when paragraph is true on a merged pull request and the named test is in CI. The 19 rows closed at triage are the only exception; they need their regression test and nothing else.
