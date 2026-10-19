# Reports module — implementation plan (revision 2)

Source: the 25-screen review of 2026-10-18, then a code-level review of revision 1 (same day).
Status: PLAN ONLY — nothing here is built. IDs are `RPT-nn`.
Evidence tags: **Observed** = read in code; **Verify** = confirm before building (RPT-00).

## 0. What changed in revision 2

Corrections to revision 1 (all re-checked in code unless marked):

| # | Correction | Affects |
|---|---|---|
| C1 | Server pagination does **not** exist for Cash Book or Stock Valuation. Sales/Purchases build all rows in Python, cap at 5 000 / 10 000 rows via `_assert_register_within_bound`, and only slice in the view. Purchases computes its summary bar client-side. | RPT-14 rewritten |
| C2 | `format=gstn-json` is gated by `settings.ENABLE_GSTN_JSON` **and** the company flag, and `get_permissions` only applies `CanExport` to `xlsx`, so GSTN JSON is downloadable without export rights (**permission bug**). | RPT-07 step 4, new RPT-09 item |
| C3 | `schedule_iii_balance` already folds current earnings into the Equity section as `surplus_in_profit_and_loss` and adds it to the section amount. Rendering a second "current earnings" line would double-count. Residual accounts are already caught in "other …" lines, so the "group rows by type" fallback is not needed. | RPT-01 step 2 |
| C4 | D3 and RPT-01 contradicted each other on the Balance Sheet default date. Now one rule (see D3). | D3, RPT-01 |
| C5 | Sales summary uses `COMPLETED`, customer/product tops use `NET_SALES` statuses, and `by_date` is gross `grand_total`. Changing the Revenue card alone leaves "Revenue by date" contradicting it. | RPT-04 |
| C6 | GSTR-3B has no numeric "reversed/ineligible" block (only a manual-review note). Backend does return `tax_payable_summary.net_payable_hint`; the UI ignores it and its fallback omits RCM and cess. | RPT-07 step 3 |
| C7 | `StatutoryEventsPage` has the false-empty bug (line 93); revision 1 wrongly said it was already gated. | RPT-02 |
| C8 | Under `keepPreviousData`, a failed refetch can keep old `data`. The empty-state helper must also check `isError`. | RPT-02, RPT-05 |
| C9 | Menu uses `accountingEnabled \|\| featureFlag`; route guard uses `&&`. Companies with books off see 4 menu items that land on the limited-access page. | RPT-09 |
| C10 | Invoice Profit **Rollup** (page, route, endpoint) also exposes COGS/margin and was missing from the masking scope. | RPT-12 |
| C11 | More ungated exports: Stock Valuation, Day Book (backend needs `CanExport`, so a 403), Customer Ledger (`.catch(() => {})` swallows errors), Supplier Ledger (CSV/PDF, PDF has no catch), GSTR-2B offline export. | RPT-09, RPT-13 |
| C12 | `TdsReceivablePage` (`/reports/tds-receivable`) was out of scope; it is linked under Money only. | RPT-08, RPT-12 |
| C13 | Confirmed bug: untrusted books mask the banner money (`—`) but `DataTable` still shows real rupee values. | RPT-01 |
| C14 | `t()` called at module scope (e.g. `InvoiceProfitRollupPage` column constants) does not follow a locale switch. | RPT-13 |
| C15 | `InventoryReportPage` has a Print button over a virtualized table; print loses off-screen rows. | RPT-13/14 |
| C16 | TDS/TCS worksheet views throw a bare `Http404` when not readable, and CSV streaming does not check `CanExport`. | RPT-03 |
| C17 | Moving GSTR-6/7/8 into a sub-group must keep `FLAG_GATED_NAV` applied to nested children. | RPT-08 |

Priority change: the permission/menu parity test (old RPT-09) moves to Phase 1.

## 1. Principles

1. Show what the backend already computes before adding backend features.
2. A compliance screen never shows a "clean" state when data failed to load.
3. Every headline number says what it is (gross/net of GST, net of credit notes, as-of date) and every number on one screen uses the same definition.
4. Menu, route guard and backend permission agree, and a test enforces it.
5. Each WP is independently mergeable with tests. Gates: `tsc -b`, eslint 0-error, ruff, `qos-lint`, regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` when the API shape changes, en + hi i18n together.

## 2. Decisions

### 2.1 Recorded (2026-10-18, founder)

| # | Question | Decision | Consequence in this plan |
|---|---|---|---|
| D1 | Meaning of Sales "Revenue" | **Gross incl. GST, net of credit notes** (not the recommended net-taxable) | RPT-04: headline = invoice totals incl. GST minus credit notes; label it "Sales incl. GST (net of credit notes)". Taxable and GST shown as breakdown lines. The GSTR-1 tie-out compares the **taxable** line, not the headline. "Revenue by date" uses the same gross-net figure. |
| D2 | TDS/TCS worksheet access | **Owner + accountant** | RPT-03: new `CanViewTaxWorksheets`; CSV also needs `CanExport`. |
| D3 | Balance Sheet default as-of | **Today, capped at FY end** | RPT-01: UI sends today; backend keeps FY-end fallback and returns `as_of_defaulted`. |
| D4 | Invoice Profit and Rollup margins | **Owner + accountant** | RPT-12: mask COGS/margin for other roles on both endpoints and both pages. |
| D5 | Reports menu group labels | **Operational / GST & compliance / Books** | RPT-08: Claude drafts Hindi strings; founder reviews later. |
| D6 | GSTN JSON in the UI | **Always show** (not the recommended flag-gated option) | RPT-07: option always visible. When the flag is off the backend returns "disabled"; the UI must show that as a clear, friendly message (not a raw 400) and may mark the option "needs enabling". The `CanExport` permission fix is still required. |
| D7 | RPT-14 scope | **Option A** (keep caps and virtualisation, add server totals, budget tests) | RPT-14 as written under Option A. |
| D8 | Numeric 4(B) ITC reversed/ineligible block in GSTR-3B | **Include in RPT-07** (not the recommended separate backlog item) | RPT-07 grows by a backend item (see RPT-07 step 2). CA input on the rules is still needed before it ships. |
| D9 | Start | **Phase 1** (RPT-00, 09, 02, 10, 03, 05) | Next action once the founder says go. |

### 2.2 Original options (kept for history)

| # | Decision | Blocks | Recommendation |
|---|---|---|---|
| D1 | What does "Revenue" mean on Sales? | RPT-04 | Net sales = taxable value net of credit notes, excl. GST; gross and GST as separate lines. |
| D2 | TDS/TCS worksheets: owner-only or also accountant? | RPT-03 | Owner + accountant; CSV additionally needs `CanExport`. |
| D3 | Balance Sheet default as-of | RPT-01 | **Frontend always sends `as_of` = today (capped at FY end)**, so users see a real date. Backend keeps `as_of=None → FY end` for API callers and returns `as_of_defaulted: true` in that case. The page shows "As of <date>" in both cases. |
| D4 | Who sees Invoice Profit margins/COGS (report **and** rollup)? | RPT-12 | Owner + accountant. |
| D5 | Hindi labels for the new Reports menu groups | RPT-08 | Approve once. |
| D6 | Is GSTN JSON meant for pilot users? | RPT-07 | Only show the option when the flag is on (read from `/feature-flags`); otherwise keep it hidden. |

## 2.3 Phase 1 build status (2026-10-18, uncommitted)

| WP | Status | Notes |
|---|---|---|
| RPT-00 | Done | `persist_snapshot` writes no audit entry of its own; nav flag gating confirmed per item. |
| RPT-02 | Done | `showEmpty` in `web/src/utils/queryState.ts`; applied to rate back-scan, GSTR-2B, Statutory events. Other pages already return early on error. |
| RPT-03 | Done | `CanViewTaxWorksheets` (owner, or accountant with report access); `?preview=1` JSON; CSV also needs `CanExport`; bare 404 replaced by a readable 400; page shows tabs, totals, by-section table, readable download errors. |
| RPT-05 | Done | Cash Book and Stock Valuation keep filters and the last result while loading; no zero totals on failure. |
| RPT-09 | Done (part) | `reportAccess.ts` is the single rule for menu and route (GSTR, TDS, accounting). Export gating added to Cash Book, accounting reports, Day Book, Customer Ledger; Customer/Supplier ledger export failures now shown. `gstn-json` now needs `CanExport`. **Not gated, on purpose:** Stock Valuation CSV, Supplier Ledger CSV/PDF and GSTR-2B offline export, because their APIs do not require export rights (gating them would be a new policy). Raise if you want it. |
| RPT-10 | Done | Plain JSON preview writes no audit event; export, GSTN JSON and saved snapshot do. |
| Side fix (from RPT-08) | Done | Accounting menu items used `\|\|` while the route used `&&`; both now use `canViewAccountingReports`. |

Verification: backend 69 tests pass (new `tests/test_reports_rpt_phase1.py`); web `tsc -b` clean, eslint 0 errors; new vitest files `rptPhase1*.test.tsx`, `reportAccess.test.ts`, `queryState.test.ts`. OpenAPI snapshot was not regenerated (no schema shape change; local regeneration differs from CI in line endings and settings, so it was left to CI).

## 2.4 Phase 2 build status (2026-10-18, uncommitted)

| WP | Status | Notes |
|---|---|---|
| RPT-01 | Done | New `web/src/pages/reports/statements/` (Balance Sheet and P&L views). Balance Sheet renders the Schedule III sections only (current earnings appear once, inside Equity), asset and equity-and-liabilities sides with totals, a balanced/not-balanced check that is green only on an explicit true, the as-of date with a note when the server filled it in, cost-centre filter, preset chips on P&L, applied period shown. Untrusted books now mask the table as well as the banner (Trial Balance, P&L, Balance Sheet). Trial Balance has a totals row. Backend adds `as_of_defaulted`, a Summary sheet, Schedule III sheet and TB totals row to the Excel files. |
| Found and fixed | Done | **The Excel download of Trial Balance, P&L and Balance Sheet returned 404 for every user**: DRF read `?format=xlsx` as a renderer name. `AccountingReportView` now ignores the `format` override (keeps the camel-case JSON renderer). Covered by new tests. |
| RPT-08 | Done (part) | Reports menu is grouped Operational / GST & compliance / Books, with Month-end close first; every item id and path unchanged; TDS receivable also listed under compliance; GSTR-6/7/8 sit in a nested "More returns (not supported yet)" group and stay hidden unless their flag is on (tests confirm nested flag gating). Month-end close is a live checklist (books health, trial balance, GST health for a chosen month, each "could not check" on failure, never "all clear"). **Not done:** the accounting menu predicate fix was already delivered in Phase 1. |
| Not done / deferred | | Hindi wording for the new group labels is drafted but needs your review (D5). Browser check of the Balance Sheet, P&L and menu was not run. |

## 2.5 Phase 3 build status (2026-10-18, uncommitted)

| WP | Status | Notes |
|---|---|---|
| RPT-04 | Done | New `ReportService.sales_totals`: invoices (completed and returned) plus completed debit notes minus completed credit notes, one window. Headline = sales incl. GST net of credit notes (D1); breakdown lines for invoiced, credit notes, debit notes, before GST, GST and other; "Revenue by date" and top customers now add up to the headline (tested). Summary now has the date-span guard and a 20 000-invoice cap with a clear message. Summary failure shows an error, not stale figures. **Tie-out:** instead of a fragile computed chip, the card links to GSTR-1 (which already shows the register tie). |
| RPT-06 | Done (part) | `useReportPeriod` hook (bounded default, remembered per report, backwards range detected). Applied to Sales (current FY) and Cash Book (this month). GST month pickers keep the last valid month when cleared (GST returns, GST Health, Missing documents, TDS/TCS). **Not applied yet:** Discounts, Invoice Profit and rollup, Inventory, ledgers, TDS Receivable, Day Book (each needs a first-hand read, RPT-12). |
| RPT-07 | Done (part) | GSTR-3B shows the backend `net_payable_hint` (includes RCM and cess); no client-side sum; "not available" when absent. New ITC panel (books, safe to claim, parked, RCM, import) and a 4(B) block. Issues: full list, worst first, filter by type, paginated, each row links to its document (reuses the shared alert row). GSTR-1: collapsible HSN, documents, advances, advance adjustments, tax on advances and amendments tables when present. GSTN JSON option is always shown (D6) with a note; a failed request shows the server's message. "Save snapshot" button. |
| D8 backend | Done | `itc.reversed_ineligible` in GSTR-3B: purchase bills marked Reversed or Ineligible, per tax head with counts, plus an informational 2B-flagged count; `needs_ca_confirmation: true`. It does not decide which 4(B) sub-row a bill belongs to. |
| Not done | | B2B/CDNR rows are not individually listed with links (the page shows counts, as before). No list of saved snapshots (no API for it). The GSTR-3B Excel file does not yet carry the new 4(B) block. Hindi wording for the new strings needs review. No browser check. |

## 2.6 Phase 4 build status (2026-10-18, uncommitted)

| WP | Status | Notes |
|---|---|---|
| RPT-12 | Done (part) | **D4:** Invoice Profit and its rollup need the owner or an accountant with report access, on both API endpoints (`CanViewMargins`, 403 otherwise) and in the menu and routes; both pages now open on this financial year, remember the range, and use the safe empty state. First-hand read of Discounts, Inventory, Day Book, Customer Ledger and TDS Receivable found no further blocking defects beyond the date and print items below. Discounts now opens on this financial year. **Left unbounded on purpose:** TDS Receivable (the Money hub links to "pending" certificates, which may be older than this year). **Not read first-hand:** GSTR-9, Missing bills. Statutory events readable summary not done. |
| RPT-13 | Done (part) | Module-level `t()` in the rollup fixed (labels now follow a language switch). Cash Book and Stock Valuation text moved into the language files (English and Hindi). Inventory print now prints from a full table, not the windowed one. Export failures were fixed in Phase 1. **Not done:** one shared page layout across reports, Godown/Warehouse wording, a key-parity i18n test. |
| RPT-11 | Done (part) | Sales and Purchases register: the document number opens the invoice, credit note or debit note. Trial Balance: an account code opens the Day Book for that account for this financial year up to the as-of date (Day Book now accepts `from`/`to`). Customer Ledger and Day Book already linked. **Not done:** Cash Book rows (receipts and payments have no detail page, only lists), GST Health and rate back-scan rows. |
| RPT-14 | Done (Option A) | Purchase register returns its own `totals` (count, taxable, tax, grand total) with credit and debit notes netted; the page uses them. This also fixes the old on-screen sum, which counted a credit note's taxable value as positive. Caps, windowed tables and the default ranges remain; no true paging. The large-tenant performance budget test was not extended. |

## 2.7 Follow-ups built (2026-10-18, uncommitted)

| Item | Status | Notes |
|---|---|---|
| GSTR-3B Excel | Done | New "Payable" sheet (net payable as the page shows it) and "ITC 4B" sheet (reversed, ineligible, total). |
| GSTR-9 read first-hand | Done | Asks the server only once the year looks like 2025-26 (it used to ask on every keystroke); download no longer cancels itself; the Table 6/7/8 labels are in the language files (English and Hindi). |
| Missing bills read first-hand | Done | Month picker and last list stay on screen while another month loads; a failed load shows the error, never "nothing missing"; taxable value shown as money. |
| Statutory events | Done | Payload reads as words ("Irn: abc · Ack No: 123"), without ids or nested data. |
| i18n key parity | Already covered | `fullParity.test.ts` already checks English and Hindi keys match; no new test needed. |
| Still open | | One shared page layout, Godown/Warehouse wording (a product-wording call), links from Cash Book, GST Health and rate back-scan rows, large-company performance budget test, per-invoice B2B/CDNR rows on GSTR-1, list of saved snapshots (needs an API), browser check, Hindi wording review, OpenAPI snapshot regeneration in CI. |

## 2.8 Closing pass (2026-10-18, uncommitted)

Every code item left open in 2.2 to 2.7 was built. What remains is only what needs a person.

| Item | Result |
|---|---|
| Export buttons | Stock Valuation CSV, Supplier Ledger CSV/PDF and GSTR-2B offline export now need export rights, like every other export (one policy). |
| Godown wording | "Godown" everywhere in English (two "Warehouse" labels fixed); Hindi already says गोदाम. |
| Date defaults | Supplier Ledger opens on this financial year (opening balance carried in). **Customer Ledger and Stock Valuation stay open-ended on purpose:** a customer's balance is cumulative, and Stock Valuation's date is an "as of" that defaults to today. TDS Receivable also stays open-ended (older pending certificates). |
| Kept filters | Day Book (both tabs) keep the controls on screen while loading or on a failed load; Customer Ledger already did. |
| GSTR-1 rows | B2B, B2CL, exports, SEZ, credit/debit note tables with a link to each document (ids come beside the tables, not inside the rows, so the Excel columns and GSTN JSON are unchanged). |
| Saved snapshots | New `GET /reports/gst-snapshots/` and a list on the GSTR-1 and GSTR-3B pages that refreshes after Save. |
| Row links | Cash Book (receipt by number, payment by supplier), rate back-scan (invoice). Cash Book also has a bank-account filter. |
| Language | Remaining hard-coded English in Customer Ledger moved to the language files. |
| Shared layout | Every report page now uses the same page shell (title, actions, content): sales, purchases, discounts, invoice profit and rollup, inventory, statutory events, both ledgers, day book, GST returns (including the not-supported placeholders), GSTR-2B, GSTR-9, GST health, rate back-scan, missing bills, TDS receivable, month-end close. |
| Money Hub and Sales | Sales headline now matches the dashboard's "sales this month" for the same days (opening-balance invoices, which are dues brought in, count in neither; the customer-sales list was aligned). A test locks this in. |
| Scale | Large-company test extended: one month of the Sales summary on 50 000 invoices stays inside a time and query budget, and a whole year is refused with a clear message. |
| OpenAPI | Snapshot and generated types updated for the new endpoint (21 and 37 lines); `npm run lint` including the fetch-all-pages check passes; ruff and `makemigrations --check` clean; Q-OS lint OK. The UX surface ledger reports 7 missing surfaces, none from reports (they belong to other work in the tree). |
| Postgres | The new and related report tests (44) pass against Postgres 17 (a throwaway container, removed afterwards). |
| Browser | A Playwright spec (`web/e2e-golden/reports-rpt-walk.spec.ts`) opens all 18 reports as a fresh tenant in Chrome at desktop and 375 px: no console errors, no sideways scroll. Screenshots reviewed: Balance Sheet (balanced check, two columns), Month-end close (checklist resolves to "All clear"), Sales at phone width. |

**Cannot be closed by code (needs a person):** CA confirmation of the 4(B) split and of the Balance Sheet / P&L layout and revenue wording; your review of the Hindi wording; GSTR-6/7/8 remain honest placeholders because there is no return specification to build from.

## 3. Work packages

### RPT-00 — Verification spikes (0.5 day)
Already answered by reading the code:
- Untrusted books: banner masks, `DataTable` does not (C13).
- GSTR-3B payload: no numeric reversed/ineligible; `net_payable_hint` exists as a total only (C6).

Still to do:
- Does `persist_snapshot` write its own audit entry? (decides RPT-10 detail.)
- Which GSTR-1 tables are in the payload (HSN, docs, AT/ATADJ, amendments)?
- Does `filterNavigation` apply `FLAG_GATED_NAV` recursively to nested children (as `sales-more` suggests)?
- Which report endpoints feed the Purchases summary bar, so server totals can replace the client sum (RPT-14).
- Money Hub / GSTR-1 / P&L revenue definitions (RPT-04 tie-out).
- First-hand read of Discounts, Inventory, Day Book, GSTR-9, Missing bills, TDS Receivable for findings beyond those in C10–C12.
**Done when:** a findings section is appended to this file.

### RPT-01 — Balance Sheet and P&L as real statements (P0, ~3.5 days)
Problem: [AccountingReportsPages.tsx](web/src/pages/phase/AccountingReportsPages.tsx) renders one flat table for all four reports and ignores `schedule_iii`, `equation_holds`, `current_earnings`, `fy_from/fy_to` ([accounting/reports.py:488](backend/accounting/reports.py:488)).

Steps
1. Split out `BalanceSheetView` and `ProfitLossView` under `web/src/pages/reports/statements/`; keep TB and Books Health on the shared component; keep the one-line page re-exports so routes are unchanged.
2. Balance Sheet: render **`schedule_iii.sections` as the single source of truth**, with each section's own `amount` as its subtotal. Do **not** add a separate "current earnings" line — it is already inside Equity as `surplus_in_profit_and_loss` (C3). Show a check row `Assets = Liabilities + Equity` using the section totals, green only on explicit `equation_holds === true`, otherwise amber with the delta. Show the effective date from `as_of`, with "(default: year end)" when `as_of_defaulted`.
3. P&L: render `schedule_iii` sections with subtotals; show the applied period from `date_from`/`date_to` ("current FY" note when the user left the boxes empty).
4. Controls: preset chips (This month, Current FY, Previous FY, Q1–Q4), Balance Sheet as-of and cost-centre filter per D3.
5. **Money masking:** add a `maskMoney` prop (or per-column `render`) to `DataTable`/statement views and apply it when `!books.trusted`, so tables match the banner (C13). Cover TB, P&L, BS.
6. Trial Balance: add a totals row; account codes link to journals (RPT-11).
7. Backend (additive): `as_of_defaulted` on balance sheet; XLSX gets a Summary sheet (totals, equation check, period) and section rows for BS/P&L, totals row for TB.
8. Replace `fetch(blobUrl)` in the download handler with `triggerBlobDownload`.

Acceptance: an unbalanced company shows the amber check with the delta; Equity subtotal equals backend `equity + current_earnings` exactly once; untrusted books mask table and banner alike; the date used is always visible.
Tests: vitest (grouping, double-count guard, explicit-true chip, masking); pytest (`as_of_defaulted`, xlsx sheets); snapshot test that TB/Books Health render unchanged.
Risk: HIGH (shared component).

### RPT-02 — Never show "clean" when the load failed (P1, 0.5 day)
Files: GstRateExposure, Gstr2b, **StatutoryEvents (line 93)**, plus any hit from `grep -n "length === 0" web/src/pages/reports`.
Add one shared helper in `PageState.tsx`:
```ts
export function showEmpty(q: { isLoading: boolean; isError: boolean; data?: unknown }, rowCount: number) {
  return !q.isLoading && !q.isError && q.data !== undefined && rowCount === 0;
}
```
(`isError` check covers failed refetch under `keepPreviousData`, C8.) Keep filters visible on error.
Tests: per page, API mocked 500 → error + retry, no empty state; plus a case with previous data present then a failing refetch.

### RPT-03 — TDS/TCS permission, preview and errors (P1, 1.5 days; needs D2)
1. Apply D2 with a shared `CanViewTaxWorksheets` in [reporting/permissions.py](backend/reporting/permissions.py); keep frontend `allowTdsReports` and the menu predicate identical.
2. Add JSON preview endpoints (same row builders) with totals by section; page shows table + totals, then Download CSV. CSV path additionally requires `CanExport` (C16).
3. Replace the bare `Http404` with a clear business error when worksheets are not available ("TDS is off for this company" / "no data"), and map blob error bodies to readable text in the page.
4. Empty month message instead of a blank CSV.
Tests: role matrix (owner/accountant/staff × preview/csv), vitest for preview/errors.

### RPT-04 — One definition of revenue on Sales (P1, 2.5 days; needs D1)
1. Backend: add `ReportService.sales_totals` returning `gross`, `gst`, `taxable`, `credit_notes`, `net_taxable`, using **one status set (`NET_SALES`)** for totals, tops and by-date (C5). Make `by_date` use the same netting. Keep `totals.revenue` key, set per D1, add breakdown keys.
   **Per D1:** the headline is gross incl. GST net of credit notes; keep `taxable` as a visible breakdown line and use it for the GSTR-1 tie-out.
2. Add `assert_report_date_span` to the summary (no guard today) and a row/invoice cap with a clear "narrow the dates" message.
3. Replace the per-invoice Python loop for paid/partial/unpaid with chunked bulk outstanding (or SQL), within the cap.
4. UI: Revenue card shows net with gross/GST/credit-note breakdown; **"Revenue by date" uses the same net figure**; tie-out chip against GSTR-1 for single-month ranges when GSTR is enabled; summary error shows `ErrorState`.
5. One-line notice for 30 days that Revenue now excludes GST and credit notes.
Tests: pytest (invoice + partial credit note + advance; status set parity; by-date sum equals headline; span guard); vitest; refresh OpenAPI snapshot/types.

### RPT-05 — Keep filters while loading (P2, 1 day)
Cash Book and Stock Valuation: `placeholderData: keepPreviousData`, controls always rendered, thin progress bar when `isFetching`, error under the controls. Use `showEmpty` from RPT-02.
Tests: control stays mounted/focused while typing a date; failed refetch shows error, not stale-empty.

### RPT-06 — Date defaults and remembered choices (P2, 1.5 days)
1. `useReportPeriod(key, defaultPreset)` hook: default current month (operational) or FY (summary), remember per report in `localStorage` (try/catch), preset chips, validate `from ≤ to`, disable query with helper text on invalid/blank.
2. Apply to Sales, Cash Book, Stock Valuation (as-of today), Day Book, Discounts, Invoice Profit (+rollup), Inventory, both ledgers, TDS Receivable.
3. Month pickers on GST pages keep the last valid period on blank.
4. Backend span messages use the same words as the screens.
Note: the backend already rejects unbounded Sales/Purchases above its row caps, so a no-date default can hard-fail on large tenants — this WP removes that failure mode.
Tests: hook unit tests; Sales and Cash Book page tests.

### RPT-07 — GSTR-1 / 3B depth, correctness and drill-down (P1, 5 days)
1. **3B net payable:** read `tax_payable_summary.net_payable_hint` from the payload; delete the client fallback arithmetic (it omits RCM and cess, C6). If the field is absent show "not available". Keep the carry-forward note. Acceptance: with RCM and cess non-zero, UI worksheet net equals the backend hint.
2. 3B ITC block: show available, from 2B matched, RCM provisional, unreviewed, import, recommended claimable, and the existing manual-review note for 4(B) reversals/ineligible. **Per D8:** also add a backend numeric block `itc.reversed_ineligible` to `build_gstr3b` (table 4(B): reversed under rules 38/42/43 and Section 17(5), plus ineligible 2B rows, per tax head) with per-head totals that feed `recommended_claimable`. Needs CA confirmation of the rules before release; ship behind the existing GST honesty banner, update OpenAPI snapshot/types, and add pytest cases for each reversal type. Until the CA signs off, keep the manual-review note visible.
3. GSTR-1: collapsible sections for HSN, documents, AT/ATADJ, amendments, only where present in the payload; B2B/B2CL/CDNR rows link to the document.
4. Issues list: full paginated list with severity sort, code filter, and link to the document (replaces first-8 cap).
5. **GSTN JSON:** per D6 the option is always shown; when the flag is off, map the backend "disabled" error to a friendly message and mark the option as needing enablement; backend fix — `get_permissions` must require `CanExport` for `gstn-json`/`gstn_json` as well as `xlsx` (C2); test that a non-exporter gets 403.
6. "Save snapshot" button (`persist=1`) and a short list of recent snapshots with hash/time.
Tests: fixture-driven vitest; pytest for the permission fix and hint parity.

### RPT-08 — Menu structure, discoverability, accounting guard (P2, 1.5 days; needs D5)
1. Group Reports into Operational / GST & compliance / Books; keep all ids and paths.
2. Add "Month-end close" as the first item and turn [CloseMonthPage](web/src/pages/reports/CloseMonthPage.tsx) into a live checklist (Books Health, GST Health, TB balanced, period lock, GSTR links).
3. Cross-link **TDS Receivable** next to TDS/TCS in the compliance group (keep its Money entry).
4. GSTR-6/7/8: move to a "More returns" sub-group; **ensure `FLAG_GATED_NAV` still applies to nested children** (C17) with a test.
5. Fix the accounting predicate mismatch (C9): one shared `accountingReportsVisible(user)` used by both `menu.ts` and `App.tsx` `allowAccounting`.
6. Rebase on the uncommitted edits to `menu.ts`, `en.ts`, `hi.ts` first.
Tests: navigation tests incl. nested flag gating; e2e smoke for each menu path.

### RPT-09 — Permission parity and export gating (P1, moved to Phase 1; 1.5 days)
1. Table-driven vitest walking `navigation` + route table per role: a visible menu item must be reachable. Plus a pytest that maps each report endpoint to its DRF permission and compares against the same role fixtures. This would have caught TDS and accounting (C9).
2. Gate export buttons with `canExport(user)` on: Cash Book, accounting reports, Stock Valuation, Day Book, Customer Ledger, Supplier Ledger (CSV/PDF), GSTR-2B offline export, Sales/GST (already done).
3. Backend: `gstn-json` permission fix (shared with RPT-07 item 5; implement here once).
Tests: parity suite; render tests for a non-exporter on each page above.

### RPT-10 — GST audit-log accuracy (P1, 0.5 day)
In [GstReturnView.get](backend/reporting/views.py:1019) write the `AuditEvent` only for `xlsx`, `gstn-json`, or `persist=1` (depending on RPT-00 finding about `persist_snapshot`). Plain JSON preview writes nothing (also removes an INSERT per GET). Check `GstReturnJson` consumers.
Tests: preview 0 events, export 1, persist 1.

### RPT-11 — Drill-down links (P2, 2–3 days, after RPT-01)
Trial Balance → journals by account; Day Book → voucher; Cash Book, ledgers, Sales/Purchases, GST Health and rate-scan rows → document. Single helper in [ledgerLinks.ts](web/src/pages/reports/ledgerLinks.ts).
Tests: helper per document type; one `href` test per page.

### RPT-12 — Remaining pages and masking (P2, 2.5 days; needs D4)
- First-hand read of Discounts, Inventory, Day Book, GSTR-9, Missing bills, TDS Receivable; fix P0/P1, log the rest via qos into the backlog.
- **Invoice Profit and Invoice Profit Rollup:** apply D4 on both endpoints ([views.py:395](backend/reporting/views.py:395), :414) and both pages/routes together; add to the pending `purchase_price` masking item.
- Statutory events: readable per-event summary instead of raw `key=value`.

### RPT-13 — Localisation, consistency, export errors (P2/P3, 2 days)
1. Move hard-coded English to `en.ts`/`hi.ts`: accounting reports, Cash Book, Stock Valuation, empty states.
2. **Module-scope `t()`** (e.g. `COLUMNS_BY_GROUP` in `InvoiceProfitRollupPage`, check `SupplierLedgerPage`): move inside render/`useMemo` so labels follow locale switches (C14).
3. One download helper `triggerBlobDownload`, and **one export error path**: every export surfaces failures through `HelpErrorAlert`; remove `.catch(() => {})` in Customer Ledger and add the missing catch on the Supplier Ledger PDF (C11).
4. Single `PageShell` layout everywhere (do last to limit churn); wrap Sales chips; unify Godown/Warehouse and GSTIN casing.
5. Printing: either disable virtualization when printing (e.g. `@media print` + render-all on print) or hide Print on virtualized tables; fix Inventory (C15) and check Supplier Ledger.
6. i18n key-parity test (en ⊆ hi).

### RPT-14 — Scale and paging (P2, scoped down; 2–4 days)
Revision 1 assumed existing server paging; it does not exist (C1). Choose one scope (recommend **Option A**):
- **Option A (recommended):** keep bounded-range registers with virtualization, rely on RPT-06 defaults (current month/FY) and the existing 5 000/10 000 caps, and add **server-side totals** to `ReportService.sales_register`/`purchase_register` so the Purchases summary bar no longer sums client-side. Paginate only endpoints that already use `DefaultPagination` (Day Book ledger, Statutory events). Add large-tenant budget tests (extend `test_qos0003_large_tenant_reports.py`) for the Sales summary and Cash Book.
- **Option B:** true SQL pagination in `ReportService` (slice after `order_by`, totals via `aggregate()`), Cash Book and Stock Valuation gain paging; UI switches to paged fetch. Larger change; only if Option A budgets fail.

## 4. Sequencing

| Phase | WPs | Notes |
|---|---|---|
| 1 (week 1) | RPT-00, RPT-09, RPT-02, RPT-10, RPT-03 (after D2), RPT-05 | Parity test first so later menu/permission work is protected. |
| 2 (week 2) | RPT-01, RPT-08 | Statements plus menu/accounting guard. |
| 3 (week 3) | RPT-04 (after D1), RPT-06, RPT-07 | Number definitions, defaults, GST depth. |
| 4 (week 4) | RPT-11, RPT-12 (after D4), RPT-13, RPT-14 | Drill-down, remaining pages, sweep, scale. |

Order notes: RPT-01 and RPT-13 both edit the accounting report file — do its string moves inside RPT-01. RPT-08 touches `menu.ts`, which has uncommitted changes — commit or rebase first. RPT-07 and RPT-09 share the `gstn-json` permission fix — implement once, in RPT-09.

## 5. Verification and release

Per WP: `npm run lint`, `tsc -b`, vitest on touched pages, ruff, pytest on touched modules (private-DB recipe; concurrency tests Postgres-only), regenerate OpenAPI snapshot and types when shapes change, `qos-lint`. Browser pass for RPT-01, 05, 08 (balanced and unbalanced Balance Sheet, typing in Cash Book date, mobile width, locale switch). Non-automatable sign-offs: CA on Balance Sheet/P&L layout and XLSX (RPT-01) and revenue wording (RPT-04, with QOS-0130..0133); Hindi review of new strings.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Double-counting current earnings in Equity | Render `schedule_iii` only; explicit unit test (RPT-01). |
| Shared `DataTable`/accounting component regressions | Split rather than modify; snapshot tests. |
| Revenue definition change confuses users | D1 sign-off, breakdown, 30-day notice, by-date aligned. |
| Hiding GSTN JSON or tightening its permission surprises a pilot | D6; release note; 403 test. |
| Menu regrouping breaks bookmarks/e2e or un-gates flagged items | Keep ids/paths; nested flag-gating test. |
| Audit change hides a signal someone uses | grep and QOS check (RPT-10). |

## 7. Out of scope

New filing capability, implementing GSTR-6/7/8, new report types, mobile reports, and GL posting rules. (The 4(B) ITC block is now in scope under D8.)
