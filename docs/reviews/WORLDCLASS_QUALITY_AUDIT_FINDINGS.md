# World-Class Quality Audit — Bizboard

Run date: 2026-08-21 · Tester: Cursor agent (dual-layer pass) · URL: http://localhost (Docker nginx `bizboard-nginx-1`) · Roles: Owner `demo@bizboard.local`, then Sales Staff `wc-audit-staff@bizboard.local` created in Settings → Users

## Environment

- Frontend: `http://localhost` → Bizboard login. **Do not use `:5173` on this machine** — that port is `nomey-frontend`, not Bizboard.
- API: same-origin `/api/v1/`. Host `:8000` is `nomey-backend`, not Bizboard. Bizboard API is published only via nginx.
- Docker: `bizboard-db-1` healthy, `bizboard-redis-1` healthy, **`bizboard-worker-1` unhealthy**, **`bizboard-beat-1` unhealthy**.
- Feature flags (GET `/api/v1/feature-flags/`): POS, GSTR, Tally, Accounting, AI, CRM, TDS **ON**; Manufacturing, Payroll **OFF**.
- Company: Demo Traders · GSTIN `29ABCDE1234F1Z5` (invalid check digit) · state Karnataka · `negativeStockPolicy=BLOCK` · `assumeLocalStateForBlankParty=false`.
- Seed has Owner only. This continuation created Sales Staff `wc-audit-staff@bizboard.local` (membership id 25, `canCreateSales=false` and every other capability false).
- WCAUDIT- records created: product `WCAUDIT-Widget` / `WCAUDIT-SKU-01` (id 95); purchase `PUR-00014` (id 24, COMPLETED, ₹1,180.00); sales invoice `INV-2627-F1Z5-00015` (id 57, COMPLETED, ₹531.00); receipt id 23 ₹200.00 against that invoice. Not cleaned up.

## Summary

- Findings this pass: **3 critical, 8 high, 10 medium** (WC-001–021).
- Golden chain GST/stock **passed** on purchase and intra-state sales invoice (UI = GET = stock). Partial receipt **passed** (invoice outstanding = customer ledger = ₹331.00).
- Sales register is **broken** (HTTP 500). Inter-state IGST, oversell Complete, and mobile 375×812 remain **not tested**.

## Coverage matrix

| Flow | Layer A | Layer B | Result |
|------|---------|---------|--------|
| Login empty / invalid / wrong password | Y | 401 login | Fail WC-008/009 |
| Register empty submit | Y | — | Fail WC-010 |
| Invite, no token | Y | — | Fail WC-011 |
| `/pay/not-a-real-token` | Y | — | Fail WC-012 (copy) |
| 404 `/this-route-does-not-exist` | Y | — | Pass (has recovery) |
| Logged-out `/sales/new` | Y | redirect `/login` | Pass (authz) |
| Dashboard KPIs | Y | `/dashboard/`, `/insights/daily-summary/`, `/insights/health/` | Fail WC-001 |
| Create product | Y | GET `/products/?search=WCAUDIT` | Pass + WC-006/014 |
| Purchase complete | Y | GET `/purchases/invoices/` PUR-00014 | Pass (math) + WC-007 |
| Current stock after purchase | Y | `/inventory/balances/` onHand 10.000 | Pass + WC-002/005 |
| Intra-state sales invoice qty 3 | Y | GET `/sales/invoices/` id 57; stock 10→7 | Pass (math) + WC-006 |
| Oversell qty 20 vs avail 7 | Y (typed, not Completed) | Complete blocked by mutation approval | Fail WC-016 (no inline warning); Complete not-tested |
| Inter-state IGST invoice | N | N | not-tested |
| Partial receipt ₹200 on INV-00015 | Y | invoice received 200 balance 331; receipt id 23; ledger outstanding 331 | Pass |
| Sales register `/reports/sales` | Y | GET `/reports/sales-register/` 500 | Fail WC-019 |
| Customer ledger UI + API | Y (select click intercepted) | GET `/ledgers/customers/1/` 531−200=331 | Pass Layer B + WC-020 |
| Settings → Users invite Sales Staff | Y | GET `/company/users/` membership 25 | Fail WC-017/018 |
| RBAC Sales Staff URL + GET | Y | invoices/users/receipts/dashboard 403 (not 200) | Pass API 403; Fail WC-021 home |
| POS, accounting, insights pages | N | flags only | not-tested |
| Mobile 375×812 | N | — | not-tested |

## Top 10 fix-first

1. One MTD definition shared by dashboard, daily-summary, and health; regenerate summary on GET (WC-001).
2. Enforce BLOCK on every stock posting path; repair FRAUDIT Widget Pro −4 (WC-002).
3. Fix sales-register 500 so `/reports/sales` loads (WC-019).
4. Expose `can_create_sales` (and purchases/payments) on Settings → Users invite and table (WC-018).
5. Warn before invite save when all flags are off; default Sales Staff to `can_create_sales=true` or rename the role (WC-017).
6. Do not leave Dashboard in nav if GET `/dashboard/` is 403 (WC-021).
7. Restore Celery worker/beat (WC-003).
8. Unique stock balance per product+warehouse; merge duplicate SKU rows (WC-005).
9. Require unit/UQC on product create; warn qty > available under BLOCK (WC-006/016).
10. Repair demo GSTIN checksum (WC-004).

## Findings

### WC-001 — Home screen disagrees on monthly sales
- **Module/Page:** Dashboard
- **Severity:** Critical
- **Category:** Data integrity
- **Layers:** A + B
- **Steps:** Login as Owner. Read “Today’s business summary” vs KPI card “This month”. GET `/api/v1/dashboard/`, `/api/v1/insights/daily-summary/`, `/api/v1/insights/health/`.
- **Expected:** One MTD sales figure everywhere, same as posted invoices this month.
- **Actual:** Banner MTD **₹10,266.00**; card **₹8,732.00**; both cite **14** invoices. Daily summary `createdAt` 2026-08-21T00:30:01+05:30 with `salesMtdTotal=10266`. Health `mtdSales=10266` with factor text “Last 7d ₹10266.00”. Repo comment UXW2-001 claimed this was already unified.
- **Evidence:** API bodies captured 2026-08-21; dashboard screenshot after login.
- **Viewport/role:** desktop, Owner
- **Suggested fix:** Serve live `ReportService.dashboard()` on daily-summary GET; stop labeling 7-day sales as MTD.

### WC-002 — Negative stock while policy is BLOCK
- **Module/Page:** Current Stock / Dashboard alerts
- **Severity:** Critical
- **Category:** Functional bug
- **Layers:** A + B
- **Steps:** Open `/inventory/stock`. GET `/api/v1/inventory/balances/`. Read `auth/me` `negativeStockPolicy`.
- **Expected:** BLOCK forbids on-hand below zero.
- **Actual:** FRAUDIT Widget Pro `onHand=-4.000`, `available=-4.000`. Dashboard: “FRAUDIT Widget Pro — available -4”. Policy is BLOCK.
- **Evidence:** balances row id 8; stock page text.
- **Suggested fix:** Enforce policy on every movement (including race/import/adjust); add a repair job.

### WC-003 — Celery worker and beat unhealthy
- **Module/Page:** Environment
- **Severity:** High
- **Category:** Ops
- **Layers:** B
- **Actual:** `docker ps` shows `bizboard-worker-1` and `bizboard-beat-1` unhealthy. Daily summary is a stale midnight row, not live.
- **Suggested fix:** Fix worker healthcheck/logs; make GET daily-summary recompute if stale.

### WC-004 — Demo company GSTIN fails checksum
- **Module/Page:** Company / auth/me
- **Severity:** High
- **Category:** GST
- **Actual:** `gstin=29ABCDE1234F1Z5` (known-bad check digit). Seed command would repair to `…1ZW` on re-seed; this DB was not repaired. `gstinVerificationStatus=UNVERIFIED`. legalName still contains “(Audited)”.
- **Suggested fix:** Run GSTIN checksum validation on company save; repair demo seed.

### WC-005 — Duplicate stock rows for one SKU
- **Module/Page:** Current Stock
- **Severity:** High
- **Category:** Data integrity
- **Actual:** “UXWAVE2 Test Widget / UXWAVE2-SKU-001” listed twice (4 and 2 on hand). Unique (company, warehouse, product[, batch]) is not holding for this SKU.
- **Suggested fix:** DB unique constraint + merge duplicates.

### WC-006 — Product create has no unit; purchase line shows —
- **Module/Page:** Products → New Purchase
- **Severity:** High
- **Category:** GST / masters
- **Actual:** Create-product dialog has no Unit. POST product `unit: null`. Purchase line unit “—”. Completed PUR-00014 API `unitName/uqcCode=PCS` (server default). Track batch/serial checkboxes are readonly.
- **Suggested fix:** Required unit on create; show it on the line.

### WC-007 — Purchase invoices inherit sales terms
- **Module/Page:** New Purchase
- **Severity:** High
- **Category:** Copy / data
- **Actual:** Default and persisted `termsText` starts “Goods once sold will not be taken back…”. PUR-00014 stored that text.
- **Suggested fix:** Separate purchase terms (or blank) from sales invoice_terms.

### WC-008 — Logged-out pages 401 in the console
- **Module/Page:** /login, /register, /invite, /pay/:token
- **Severity:** Medium
- **Category:** API / observability
- **Actual:** GET `/api/v1/feature-flags/` 401 and POST `/api/v1/auth/refresh/` 401 on anonymous loads. `main.tsx` comments claim this was skipped (UXW2-006).
- **Suggested fix:** Do not call refresh/flags without a session.

### WC-009 — Login copy is for developers
- **Module/Page:** Login
- **Severity:** Medium
- **Category:** Usability / copy
- **Actual:** “Use a seeded owner account, or register a new company.” Wrong-password message is raw JWT: “No active account found with the given credentials.” No forgot-password. Duplicate Email/Password labels (MUI outline + legend).
- **Suggested fix:** Shopkeeper copy; mapped error; forgot-password flow.

### WC-010 — Register empty submit is almost silent
- **Module/Page:** Register
- **Severity:** Medium
- **Category:** Validation
- **Actual:** Empty Create account: only State is HTML-required (`Please fill out this field`). Company/email/password have `required: false` and no visible zod helpers. No GSTIN field.
- **Suggested fix:** Client+server required markers on all required fields.

### WC-011 — Invite page asks for a raw token
- **Module/Page:** /invite
- **Severity:** Medium
- **Category:** Usability
- **Actual:** No-token visit shows fields Invite token + New password. Copy “BizBoard” vs app “Bizboard”.
- **Suggested fix:** Invalid-link empty state; token only from query string.

### WC-012 — Public pay page mixes human copy with API jargon
- **Module/Page:** /pay/not-a-real-token
- **Severity:** Medium
- **Category:** Copy
- **Actual:** “This invoice payment link has expired or is invalid…” plus alert “Not found.” Retry present.
- **Suggested fix:** Drop raw API detail from the alert.

### WC-013 — Nav flickers disabled ERP modules
- **Module/Page:** App shell
- **Severity:** Medium
- **Category:** Feature flags
- **Actual:** First dashboard snapshot included Manufacturing and Payroll; flags are false and they vanished on later snapshots. POS/GSTR/Accounting visible (flags ON in this Docker build — original UX prompt’s “flagged off by default” is stale for this instance).
- **Suggested fix:** Don’t render nav until flags resolve; hide OFF modules from first paint.

### WC-014 — Products list is audit-polluted and unsearchable
- **Module/Page:** /inventory/products
- **Severity:** Medium
- **Category:** Usability / a11y
- **Actual:** 30+ FRAUDIT/UXWAVE2 products, many duplicate display names. No in-page search/pagination. Accessibility tree is dozens of identical “Edit” buttons. Product save had no toast (dialog just closed).
- **Suggested fix:** Search + pagination; unique accessible names; success toast; purge demo junk.

### WC-015 — Purchase editor is overcrowded for a first-time user
- **Module/Page:** /purchases/new
- **Severity:** Medium
- **Category:** Usability
- **Actual:** Cost centre, RCM (readonly checkbox looks “on”), ITC, TDS, QR, signature, freight copy “non-taxable for **pilot**”. Party autocomplete stays collapsed until a delay. GST math for 10×100@18% was correct (₹1,180; CGST/SGST ₹90).
- **Suggested fix:** Progressive disclosure for advanced GST/TDS; don’t show readonly as checked; drop “pilot” copy.

### WC-016 — BLOCK policy has no inline warning on oversell qty
- **Module/Page:** `/sales/new`
- **Severity:** Medium
- **Category:** Validation / stock
- **Layers:** A (Complete not executed)
- **Steps:** After INV-00015, on-hand was 7. New invoice, Sharma Medicals, WCAUDIT-Widget. Autocomplete showed `avail 7`. Set qty **20**. Editor computed ₹3,540 with no stock warning. Save & Complete was not submitted (mutation approval rejected).
- **Expected:** Under `negativeStockPolicy=BLOCK`, qty > available is blocked in the editor with a shopkeeper-readable reason (available 7, requested 20).
- **Actual:** Qty 20 accepted; Save & Complete stayed enabled. No alert, chip, or helper. Backend Complete path was not proven in this pass.
- **Evidence:** Screenshot `wc-oversell-qty20.png`; autocomplete `avail 7`.
- **Viewport/role:** desktop, Owner
- **Suggested fix:** Client-side BLOCK check using available qty; disable Complete; surface the same error the API would return.

### WC-017 — Invited Sales Staff starts with no create/edit rights
- **Module/Page:** Settings → Users invite
- **Severity:** High
- **Category:** AuthZ / UX
- **Layers:** A + B
- **Steps:** Invite `wc-audit-staff@bizboard.local`, role Sales staff, password set, all five checkboxes left off (form default). Save.
- **Expected:** A role named Sales staff can create sales invoices, or the form refuses to save until at least `can_create_sales` is granted.
- **Actual:** Invite succeeded. GET membership id 25: `canCreateSales=false` and every other capability false. After save, alert: “No permissions selected — a Sales Staff account created this way starts with no create/edit access anywhere…”. Warning is **after** save, not before. Invite JWT link still shown even though a password was set. Login with that password works (invite link not required).
- **Evidence:** GET `/api/v1/company/users/`; screenshot `wc-invite-sales-staff.png`.
- **Viewport/role:** desktop, Owner
- **Suggested fix:** Show the warning before Save; add `Can create sales/purchases/payments` checkboxes; default Sales staff to `can_create_sales=true`.

### WC-018 — Users settings cannot grant the flags that make Sales Staff useful
- **Module/Page:** Settings → Users
- **Severity:** High
- **Category:** AuthZ
- **Layers:** A + B
- **Steps:** Inspect invite dialog and the users table columns.
- **Expected:** Owner can grant `can_create_sales`, `can_create_purchases`, `can_create_payments` from this screen.
- **Actual:** Checkboxes are only Inventory / Import / Cancel / Reports / Export. Table a11y names are mostly `on`. Prior FRAUDIT/UXWAVE2 staff have `canCreateSales=true` from seed/API, not from this UI. A shopkeeper following Settings → Users cannot create a working salesperson.
- **Evidence:** `UsersSettingsPage.tsx` form fields; GET users list.
- **Suggested fix:** Add the three create flags to invite + table patch; label checkboxes with user+permission.

### WC-019 — Sales register is HTTP 500
- **Module/Page:** `/reports/sales`
- **Severity:** Critical
- **Category:** Functional / reports
- **Layers:** A + B
- **Steps:** Open Reports → Sales. GET `/api/v1/reports/sales-register/` and with `from=2026-08-21&to=2026-08-21`.
- **Expected:** Rows include INV-00015 taxable ₹450 / CGST ₹40.50 / SGST ₹40.50 / grand ₹531.
- **Actual:** UI: “An unexpected error occurred.” API 500 `{code: server_error, details: null}`. Invoice GET and ledger still work — the register is the broken surface.
- **Evidence:** Screenshot `wc-sales-report-500.png`; API bodies 2026-08-21.
- **Viewport/role:** desktop, Owner
- **Suggested fix:** Catch null customer/credit-note rows in `ReportService.sales_register`; return structured 4xx if dates are invalid; never 500 with empty details.

### WC-020 — Customer ledger picker is unusable at this tenant size
- **Module/Page:** `/reports/customer-ledger`
- **Severity:** Medium
- **Category:** Usability / a11y
- **Layers:** A (API Layer B passed)
- **Steps:** Open Customer Ledger. Type “Sharma” in Customer. Click Sharma Medicals.
- **Expected:** Typeahead filters; click selects; ledger shows INV-00015 ₹531 and receipt ₹200, outstanding ₹331.
- **Actual:** Typing did not change the combobox value. Full unfiltered list (FRAUDIT/UXWAVE2 junk) opened. Click on Sharma was intercepted (`main#main-content`). GET `/ledgers/customers/1/` is correct: debit 531, credit 200, outstanding 331.
- **Evidence:** Click-intercept error; API ledger entries JV-00097 / JV-00100.
- **Suggested fix:** Filter options by query; portal the listbox above main; virtualize long lists.

### WC-021 — Zero-permission Sales Staff is denied even on Dashboard
- **Module/Page:** `/` and `/sales/new` as Sales Staff
- **Severity:** High
- **Category:** AuthZ / nav mismatch
- **Layers:** A + B
- **Steps:** Log in as `wc-audit-staff@bizboard.local`. Open `/`, `/sales/new`, `/reports/customer-ledger`. GET invoices, users, receipts, dashboard (no POST).
- **Expected:** Nav, URL, and API agree. If the user cannot see Dashboard, do not list it. 403 not 200 on privileged GETs.
- **Actual:** Login succeeded. Nav shows **only Dashboard**. `/`, `/sales/new`, and next=`/reports/customer-ledger` all show Access denied + “No modules are available yet”. GET `/sales/invoices/` 403 “Sales view permission required.” GET `/company/users/` 403 “Owner/Admin role required.” GET `/payments/receipts/` 403. GET `/dashboard/` **403** while Dashboard is the only nav item. GET `/company/` 200.
- **Evidence:** Screenshots `wc-staff-forbidden.png`, `wc-staff-home-denied.png`; GET statuses.
- **Viewport/role:** desktop, Sales Staff
- **Suggested fix:** Hide Dashboard when KPI GET is forbidden; after invite-with-no-flags, send Owner a blocking confirm; default salesperson flags so the role can sell.

## Golden-chain numbers (this continuation)

| Doc | Qty / amount | Tax split | Outstanding / stock |
|-----|----------------|-----------|---------------------|
| PUR-00014 | 10 × ₹100 | CGST 90 + SGST 90 = 180; grand 1,180 | on-hand +10 |
| INV-2627-F1Z5-00015 | 3 × ₹150 | CGST 40.50 + SGST 40.50 = 81; IGST 0; grand 531 | on-hand 10→7; received 0 then 200; balance 331 |
| Receipt id 23 | ₹200 CASH allocated to INV-00015 | — | ledger 531 − 200 = 331 |

Editor = history list ₹531.00 = GET id 57. PDF status READY (generated despite unhealthy worker).

## Not tested (must re-run)

Quotations, orders, challans, credit/debit notes, returns, recurring, customers CRUD; purchase remainder; payment links + logged-out pay of a real token; inventory adjustments/transfers/serials/expiry; remaining reports (GSTR, P&L, stock valuation, PDF vs screen); POS; GST/templates/import/backup settings; accounting journals; insights pages; **inter-state IGST invoice**; **oversell Complete vs BLOCK**; mobile 375×812; POST-as-staff 403 (GET 403s were confirmed; POST skipped).

## Cross-check (brief)

Did not re-read full prior UX/FR registers before this pass. WC-001 overlaps claimed-fixed UXW2-001 (regression). WC-008 overlaps claimed UXW2-006. WC-002 is consistent with leftover FRAUDIT race data. Duplicate IDs should be merged into MASTER_ISSUE_REGISTER on triage.
