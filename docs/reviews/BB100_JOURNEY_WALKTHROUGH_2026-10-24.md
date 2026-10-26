# BB-100 journey walk-through — 2026-10-24

Checklist rows: BB-100 (review every screen and user journey), with evidence for
BB-101 (navigation, forms, permissions) and BB-103 (error and validation feedback).

**Where:** local staging (`docker-compose.staging.yml`, Postgres with the
non-superuser app role, nginx edge) at `http://127.0.0.1:8081`. The web image was
rebuilt from the working tree on 2026-10-24, so it includes the 2026-10-23 fixes.

**Who:** the load tenant (`seed_load_tenant`, Karnataka, GSTIN 29AABCU9603R1ZJ,
books off). Two logins:
- owner, with two-step sign-in;
- sales staff (`load-staff@bizboard.local`), who can sell and see financial
  reports and exports.

**How:** a real browser (Chrome, through Playwright) signs in through the login
screen and uses the screens as a person would. The walk-through scripts live
outside the repo. This is not a substitute for a human operator; see "What this
does not cover".

## 1. Route sweep (every catalogued page)

| Run | Viewport | Pages visited | Pages flagged | Result |
| --- | --- | --- | --- | --- |
| 2026-10-23, before fixes | 1366×860 | 138 | 3 | 3 fixed in code (below) |
| 2026-10-24, rebuilt image | 1366×860 | 138 | 3 | `/help` blank (F9, fixed). `/settings/billing` and `/settings/bank-accounts` got a one-off 401 on a session refresh mid-run; both clean on re-run |
| 2026-10-24, rebuilt image | 393×852 phone | 138 | 1 | `/help` blank (F9, fixed) |
| 2026-10-24, after the F9 fix | 1366×860 | `/help` ×3, billing, bank accounts | 0 | Clean |

A page is flagged when it shows the crash screen, renders blank, logs a console
error, or gets an API 4xx/5xx.

Fixed after the first run (2026-10-23):
1. With books off, the POS till strip called the till API and failed. It is now
   hidden when the till is unavailable (`useTillAvailable`).
2. With books off, Day book loaded the chart of accounts and failed. The account
   filter is now hidden.
3. A switched-off page opened from a bookmark showed a raw "Not found". It now
   shows a "This feature is switched off" notice (`switchedOffFlag` and
   `FeatureOffNotice`).

## 2. Journeys walked

| # | Journey | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Sales invoice → PDF | Pass | INV-2627-R1ZJ-00246, ₹94, PDF ready |
| 2 | Part payment | Pass | ₹50 received, invoice shows Partial, receipt #42 |
| 3 | Sales return → credit note | Pass | Credit note ₹94; the excess over what was owed is kept as an advance |
| 4 | Purchase bill with a new supplier | Pass | Supplier created from "+ Create party". PUR-2627-R1ZJ-00001: 10 × ₹50 + 18% GST = ₹590 (CGST ₹45, SGST ₹45). Supplier owes ₹590. Stock 859 → 869 |
| 5 | Quotation → partial convert → invoice | Pass, with finding F1 | QTN-2627-R1ZJ-00001 for 3 units. Converted 2 → draft #1929 → INV-2627-R1ZJ-00247. Quote shows "Partly converted · Remaining ₹80" |
| 6 | Reports | Pass, with finding F2 | Purchases register shows the new bill (₹500 taxable, ₹90 GST). Stock valuation and inventory list the product. GSTR-1 shows the new invoice in B2CS and HSN. P&L and trial balance show the "books are off" notice, as expected for this tenant |
| 7 | Settings | Pass | Billing (no subscription, checkout closed until Razorpay is set up), Users, Security (two-step on, 10 recovery codes, signed-in devices), Backup/Export |
| 8 | Help and support | Pass, with finding F3 | FAQ search finds "return" and "two-step" answers. Contact support sent request #1, which shows as Open |
| 9 | Hindi | Pass, with finding F4 | Dashboard, new invoice, new purchase, quotations, stock, GSTR-1 and backup screens are in Hindi. Leftovers: shortcut key names and "Excel" |
| 10 | Phone (393×852) | Pass, with finding F5 | 12 key pages: no sideways page scroll; wide tables scroll inside their own region |
| 11 | Sales-staff login | Pass | All 29 menu links open, and none lands on "limited access". Blocked pages (new purchase, users, billing) are reachable only by typing the address, and then show the limited-access notice. The staff user completed INV-2627-R1ZJ-00249 |

## 3. Findings

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| F1 | Medium (money shown to customers) | **Quotations did not use the HSN-table GST rate that invoices use.** `apply_effective_gst_rate` re-rated only sales and purchase invoices, so quotations and sales orders kept the product's own rate. When the two disagreed, the customer was quoted one total and invoiced another. Seen: quote ₹240 for 3 × ₹80 at 0%; invoice for 2 of them ₹189 at 18%. The totals preview also skipped re-rating when no invoice date was sent, which is always the case for quotes | **Fixed**: quotations and sales orders are re-rated like invoices (`_RATEABLE_DOCS`). The preview uses the quote or order date, else today. Both editors show the same "rate changed …% → …% by HSN table" notice as the invoice, and the order editor now shows the server's totals. Tests: `backend/tests/test_quote_order_hsn_rate.py`, `QuotationEditorPage.test.tsx`, `SalesOrderEditorPage.test.tsx`. Quotes saved before the fix keep their old totals until edited. Second pass: purchase orders too, and the purchase-order editor shows the server's totals and the notice |
| F2 | Medium (GST filing aid) | **GSTR-1 worksheet leaves out bills of supply.** A regular-GST company's NON_GST invoices (207 completed, ₹23,860 in Oct on the load tenant) are excluded by `GST_INVOICE_TYPES` (`backend/reporting/gst_returns.py`), so they are in neither Table 8 (nil/exempt/non-GST) nor Table 13 (documents issued). The worksheet does warn: "Worksheet totals do not tie to the sales register. Difference: -23860.00" | Open, waiting for the CA: options note in `docs/ca/F2_BILLS_OF_SUPPLY_IN_GST_RETURNS.md` (also affects GSTR-3B 3.1(c)/(e)); row R1 in the CA checklist |
| F3 | Low (copy) | Help page banner said "Android is a WebView shell. Offline is the PWA." | **Fixed**: plain-language text in en and hi |
| F4 | Low (Hindi) | FAQ answers on /help stayed in English when Hindi was selected | **Drafted** (D-07): 284 machine-translated entries in `web/src/pages/help/faqContent.hi.ts`, shown when Hindi is selected, with a note on the page that they are unreviewed; English is the fallback per entry. Open: native-speaker review (the draft lists the uncertain entries) |
| F5 | Low (phone UX) | On a phone, new invoice opens scrolled past "Bill To" because the item box takes focus. Desktop keyboard-shortcut hints show on phones | **Fixed**: on a touch-first device (`useCoarsePointer`) new invoice and new purchase no longer focus the item box on load, and the invoice's shortcut line is hidden. Keyboard and scanner devices keep the focus; POS keeps it for counter tablets |
| F6 | Low (noise) | New purchase asked for the bills-of-entry list while that feature is off, and got a 404 per supplier pick | **Fixed**: the query runs only when `ENABLE_BOE` is on |
| F7 | Low (noise) | For sales staff, some pages call endpoints the role may not use (`company/gstins`, `company/users`, `payments/recon`, `inventory/batches`) and get 403s | **Fixed**. Batches: reading lots now follows the stock-view rule, so sales and purchase staff can pick a lot on a line (a lot carries no cost; creating lots stays inventory-only; role matrix test updated). The GSTIN and member lists (owner-only) and bank reconciliation (payment rights) are asked for only by people allowed to see them. See F10 |
| F8 | Info (copy) | New purchase said "Completing a receipt posts stock; the purchase bill posts what you owe", but completing a bill with no goods receipt also adds stock | **Fixed** (en and hi): "A purchase bill records what you owe and adds its goods to stock. Goods already received on a Goods receipt are not added again." |
| F9 | Medium (blank screen) | **/help showed a blank screen, not even the menu, for 1–3 s on a full load.** All ~280 FAQ answers were mounted while closed (102 KB of hidden text, 5,242 DOM nodes), each inside an MUI Accordion. First text came 3.6 s after other pages | **Fixed** in two steps: answers mount only when opened, then each entry became a plain disclosure button (same roles, ids and deep links). DOM nodes 5,242 → 1,508; first text now 0.7–0.9 s after other pages (1.9–2.1 s against 1.0–1.4 s for billing, idle laptop). Tests in `HelpPageV0.test.tsx` |
| F10 | Low (design gap) | Leads (and the attention and care pickers) let a manager or the current assignee reassign, but the member list behind the picker is owner-only, so non-owners saw an empty picker | **Fixed**: new read-only `GET /api/v1/company/members/` (`accounts/team_views.py`) for any active member: membership id, display name (full name, else the part of the email before @) and role, nothing else; pending invites and other companies left out. The lead, attention and care pickers use it; `/company/users/` stays owner-only. OpenAPI snapshot and web types regenerated (only this endpoint changed). Tests: `backend/tests/test_team_members.py`, `LeadsPage.test.tsx` (manager picks a teammate). Verified live: sales staff see both teammates in the support-ticket assignee picker |

## 4. What this does not cover

- A human operator on a real device and network. Touch, screen readers, slow
  networks and printers were not exercised. BB-100 stays In Progress until a
  person repeats the journeys in `docs/onboarding/DEMO_SCRIPT.md`.
- The books-on journeys (P&L, trial balance, journals): the load tenant has
  books off. The 2026-10-20 golden run covers them on Postgres.
- Payments through Razorpay (skipped by decision on 2026-10-23).

## 5. Second pass, 2026-10-24 (batch 1)

| Item | Result |
| --- | --- |
| BB-074 import speed | The commit loaded every product in the company as a full object to spot existing SKUs; it now loads only the SKUs in the file (`imports/services.py`). Idle laptop, 5,000-row catalogue, upload + commit: Postgres 8.7–8.9 s warm, SQLite 7.9–10.7 s. The I4 gate (`test_i4_catalog_import_of_5000_skus_meets_ten_seconds`, best of two) passes on both. Still to confirm on the hosted server |
| `month_end.js` two-step | `TOTP_SECRETS` answers the owner two-step challenge. Dry run on local staging: owner signed in through two-step, 7 requests, 0 failed |
| F1 purchase orders | Purchase orders rate GST from the HSN table, like purchase bills. Verified live: ₹100 + 18% = ₹118 on screen and saved |
| F5, F7, F8, F9 | Fixed (table above). The sales-staff login opened 44 pages with no 4xx response |
| Tests | Backend: 1,530 passed across the import, purchase-order and batch suites; the only failure was the I4 timing test while three other jobs loaded the machine, and it passes alone on both databases. Web: 3,141 of 3,142 passed in the full suite; the one failure was a load timeout and passes alone |

## 6. Third pass, 2026-10-24 (founder decisions D-06 to D-10)

Decisions are recorded in `docs/roadmap/DECISIONS_2026-10-24.md`. Nothing is committed (D-06).

| Item | Result |
| --- | --- |
| PB-02, PB-03 | Already fixed and committed earlier (searchable supplier filter on planning; paged, server-searched supplier list). The checklist note was out of date |
| Load logins (D-10) | `seed_load_tenant --staff 25` creates one sales-staff login per k6 virtual user; `k6_mixed.js` takes them as `STAFF_EMAILS` and gives VU n login n. Dry run: 357 requests, 0 failed |
| Hindi FAQ (F4) | Drafted and wired in (row F4) |
| Legal drafts (D-07) | First drafts of the terms, privacy policy and data processing agreement for counsel in `docs/legal/drafts/` |
| NPS/CSAT (D-08) | Built behind `ENABLE_SATISFACTION_SURVEY` (off by default): a corner card asking how likely the member is to recommend Bizboard (members of 14+ days, at most every 90 days, "Not now" counts), and a 1-5 rating on resolved support requests. Staff see answers and the NPS in Django admin. New table is row-level secured. Verified live: NPS 8 and CSAT 5 recorded |
| F2 (D-09) | Options note for the CA; no code change |
| Route sweep | Desktop and phone, 138 pages each, 0 flagged |
| Postgres-only tests | Row-level security, concurrency and tenancy suites plus today's new tests on a fresh local Postgres: 543 passed, 1 skipped |

## 7. Fourth pass, 2026-10-25

| Item | Result |
| --- | --- |
| Complete cap (D-11) | `sales_complete` raised from 30 to 60 per minute per company; purchase bills stay at 30 |
| Load scripts | `k6_slo.js` uses one login per VU and runs Completes at a fixed `COMPLETES_PER_MIN` (default 50); `k6_mixed.js` writers paced the same. Local dry run of `k6_slo.js`: 353 requests, 0 failed, no 429s |
| Import speed | No further safe gain: the remainder is the ORM preparing ~225,000 values. Stays at 8.7-8.9 s |
| /help | FAQ entries use styles defined once and are memoised; first text now ~0.5 s after other pages |
| Hindi FAQ | 74 bold screen labels now use the app's own Hindi; "allocation" uses the app's word; all 262 tokens intact |
| Docs | Handover status block, full-product plan (survey built), execution plan (two-step built), sign-off pack B-6, risk register R016 |

## 8. Fifth pass, 2026-10-25 (decisions D-12 to D-15)

| Item | Result |
| --- | --- |
| F2 bills of supply (D-14) | Options B + A built behind `GST_BILL_OF_SUPPLY_RETURNS`, off for every company until the CA agrees: completing a regular company's Non-GST invoice with a TAXABLE line is refused; Non-GST invoices go to GSTR-1 Table 8 (older TAXABLE lines as exempt) and Table 13, and GSTR-3B 3.1(c)/(e). Credit/debit notes against them still left out (question for the CA). 6 tests |
| Data retention (D-13) | Owner-set period (default 90 days, 30-3650) on Settings > Backup / Export; daily job records read-only start, warns owners 30 and 7 days ahead (email + in-app, once each), erases in tombstone mode only with `DATA_RETENTION_ENFORCE` on (off). 7 backend + 2 web tests; staging: 12 companies, all active, nothing done |
| Website (D-15) | Draft in `site/` (home, pricing, Hindi home, noindex, every price marked draft). Not published |
| Found | Paid plans switch GST worksheets off (`billing/entitlements.py` freeze rule) while the trial switches them on: an upgrading customer would lose GSTR-1/3B. Needs a decision |
| Tests | Backend: 729 passed (GST returns, erasure, company settings, new tests) + 1,295 passed (all other files touching GST returns or Non-GST invoices). An earlier run broke because the new migration landed mid-run; both re-runs are clean |
