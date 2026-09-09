### Reporting draft (provisional RPT-*; awaiting CR merge)

Source: [Reporting review](9534fea3-69d0-4357-b9a6-0c71eef146b2)

### RPT-001 — Dashboard AR KPI vs AR aging use different ledgers when books are on
- **Module:** Reporting → Dashboard KPIs / AR aging
- **Location:** `backend/ledgers/services.py` (~269–393, 447–453) `bulk_customer_outstanding`; `backend/reporting/services.py` (101–167) `receivables_aging`
- **Type:** Data-integrity | Bug
- **Severity:** Critical
- **What's wrong:** When `accounting_enabled` and outstanding basis is not `DOCUMENTS_ALWAYS`, company receivables switch to GL 1200/2300 while aging always uses document invoice − CN + DN − allocation. Dashboard returns both.
- **Trigger / repro:** Enable accounting (default GL_WHEN_BOOKS), post sales + receipt with GL/doc drift or advances on 2300; compare `/api/v1/dashboard/` `receivables` vs sum of `receivables_aging`.
- **Consequence:** Paying tenants see Receivables ≠ sum(aging buckets); cards and aging chart disagree.
- **Code evidence:** `LedgerService.company_receivables` → GL path; `ReportService.receivables_aging` always document-based.
- **Suggested fix direction:** One definition — age GL party balances or drive KPI from the same document bulk used for aging; assert `sum(aging) == receivables` for both bases.
- **Test to add:** With books on, assert dashboard receivables equals sum of aging buckets (and equals document bulk when basis=DOCUMENTS_ALWAYS).
- **Twin check:** n/a (AP aging vs payables KPI — check same pattern)

### RPT-002 — AR aging allocation filter ≠ party AR document formula
- **Module:** Reporting → AR aging
- **Location:** `backend/reporting/services.py:133-138`; `backend/ledgers/services.py:889-892` vs `421-427`
- **Type:** Data-integrity | Sales/Purchase-inconsistency (internal formula drift)
- **Severity:** High
- **What's wrong:** Aging / `bulk_sales_invoice_outstanding` filters allocations only by `sales_invoice_id` + `reversed_at__isnull`. Party bulk AR also requires `receipt__isnull=False` and `supplier_payment__isnull=True` (R2-020).
- **Trigger / repro:** Allocation on a sales invoice with `supplier_payment` set (or no receipt); compare aging vs customer outstanding.
- **Consequence:** Mis-typed/cross-linked allocations change aging vs party outstanding on “document” basis.
- **Code evidence:** Filter mismatch between aging and R2-020 party filters.
- **Suggested fix direction:** Align aging and `bulk_sales_invoice_outstanding` with R2-020 filters.
- **Test to add:** Allocation with supplier_payment set must not reduce sales AR aging.
- **Twin check:** Purchase/AP aging twin filters

### RPT-003 — Inventory summary qty from StockBalance cache, not sum(StockMovement)
- **Module:** Reporting → Stock summary
- **Location:** `backend/reporting/services.py:454-490` `inventory_summary`; `backend/inventory/models.py` (StockBalance cache docstring)
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** Inventory summary reads `StockBalance` for on_hand/reserved/available. Valuation may use movements/running cost — qty and value can come from different stores. Violates “stock summary = sum(movements)” checklist.
- **Trigger / repro:** Corrupt or skip balance update, leave movements correct; open inventory report / CSV export.
- **Consequence:** Drifted balances under/overstate stock report; BS inventory_valuation may not match summary.
- **Code evidence:** Iterates StockBalance; valuation path separate.
- **Suggested fix direction:** Derive on-hand from movements (or assert balance==movement sum before report); fail closed on drift.
- **Test to add:** Force balance≠sum(movements); summary must not silently trust balance (or recon report flags drift).
- **Twin check:** n/a (Stock module owns write path)

### RPT-004 — Sales/purchase registers include CANCELLED documents by default
- **Module:** Reporting → Registers / exports
- **Location:** `backend/reporting/services.py:266-267, 365-367`
- **Type:** Bug
- **Severity:** Critical
- **What's wrong:** Registers `.exclude(status=DRAFT)` only — cancelled remain in rows and totals. GST builders correctly use COMPLETED/RETURNED only.
- **Trigger / repro:** Complete then cancel an invoice; GET sales-register / export without status= — cancelled row still in totals.
- **Consequence:** Register totals/exports overstate turnover vs GSTR / ops truth.
- **Code evidence:** exclude DRAFT only; cancelled included.
- **Suggested fix direction:** Default to COMPLETED/RETURNED (or exclude CANCELLED); keep optional status filter.
- **Test to add:** Cancelled invoice excluded from default register totals.
- **Twin check:** y — both sales and purchase registers

### RPT-005 — Dashboard MTD purchases not net of purchase CNs/DNs
- **Module:** Reporting → Dashboard KPIs
- **Location:** `backend/reporting/services.py:207-230` vs sales path 183–206
- **Type:** Sales/Purchase-inconsistency | Bug
- **Severity:** High
- **What's wrong:** `purchases_this_month` sums COMPLETED PIs only; sales today/MTD nets CNs/DNs. Purchase register does net notes.
- **Trigger / repro:** Complete PI then completed purchase CN same month; dashboard purchases unchanged, register totals drop.
- **Consequence:** Purchase KPI disagrees with register/books after returns.
- **Code evidence:** Sales nets notes; purchases do not.
- **Suggested fix direction:** Mirror sales KPI: −CN +DN on completed notes in period.
- **Test to add:** MTD purchases after CN equals PI − CN.
- **Twin check:** y — sales already correct

### RPT-006 — Opening-balance exclusion inconsistent (notes vs is_opening_balance)
- **Module:** Reporting → Dashboard / GST / AR
- **Location:** `backend/reporting/services.py:179-209`; `backend/reporting/gst_returns.py:287,362`
- **Type:** Data-integrity | Missing-validation (predicate drift)
- **Severity:** High
- **What's wrong:** Dashboard excludes `notes="TALLY_OPENING"`; GSTR uses `is_opening_balance=False`; AR/aging have no opening filter.
- **Trigger / repro:** Opening SI/PI with `is_opening_balance=True`, notes ≠ `TALLY_OPENING`; compare dashboard vs GSTR.
- **Consequence:** Openings inflate sales KPI and AR while GSTR excludes them (or reverse).
- **Code evidence:** Two predicates + AR unfiltered.
- **Suggested fix direction:** Single predicate (`is_opening_balance`) on all financial aggregates.
- **Test to add:** Opening flag alone excludes from dashboard and AR; notes string alone not required.
- **Twin check:** y — sales and purchase openings

### RPT-007 — product_sales / customer_sales ignore credit/debit notes
- **Module:** Reporting → Sales analytics
- **Location:** `backend/reporting/services.py:542-589`
- **Type:** Bug
- **Severity:** High
- **What's wrong:** Product/customer sales sum invoice lines/totals only; dashboard sales nets notes.
- **Trigger / repro:** Invoice + completed CN; product/customer report still shows full invoice.
- **Consequence:** Rankings overstate net sales after returns.
- **Code evidence:** NET_SALES invoices only; no note netting.
- **Suggested fix direction:** Net note lines / party note totals for same date window.
- **Test to add:** product_sales after CN reflects net qty/amount.
- **Twin check:** n/a (purchase analytics twin if any)

### RPT-008 — Warehouse filter on registers not applied to note rows
- **Module:** Reporting → Sales/purchase register
- **Location:** `backend/reporting/services.py:271-315, 372-409`
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** Invoice qs filtered by warehouse_id; CN/DN qs are not.
- **Trigger / repro:** Two warehouses; CN on WH-B while filtering WH-A.
- **Consequence:** Warehouse-scoped register mixes filtered invoices with company-wide notes.
- **Code evidence:** warehouse filter only on invoice queryset.
- **Suggested fix direction:** Filter notes via parent invoice warehouse (or exclude notes when warehouse set).
- **Test to add:** Warehouse filter excludes notes for other warehouses.
- **Twin check:** y — both registers

### RPT-009 — Inventory summary warehouse query param not int-normalized
- **Module:** Reporting → Inventory summary API
- **Location:** `backend/reporting/views.py:144`
- **Type:** Missing-validation | Bug
- **Severity:** Medium
- **What's wrong:** Raw `request.query_params.get("warehouse")` vs `_int_or_none` on sibling views.
- **Trigger / repro:** `?warehouse=abc` or `warehouse=` on inventory-summary.
- **Consequence:** Inconsistent filter miss or 500.
- **Code evidence:** No `_int_or_none`.
- **Suggested fix direction:** Use `_int_or_none` like sibling views.
- **Test to add:** Non-integer warehouse returns 400 or ignored consistently.
- **Twin check:** n/a

### RPT-010 — GSTR-3B net_payable_hint subtracts full 2B ITC, not recommended_claimable
- **Module:** Reporting → GSTR-3B
- **Location:** `backend/reporting/gst_returns.py:1587-1612, 1867-1877`
- **Type:** Bug | Data-integrity
- **Severity:** Critical
- **What's wrong:** `recommended_claimable = min(books, gstr2b_matched)` when 2B matched, but `tax_payable_summary.net_payable_hint` subtracts full `itc_2b` heads.
- **Trigger / repro:** Books ITC 100, matched 2B 150 → recommended 100 but net_payable subtracts 150.
- **Consequence:** CA/UI hint understates tax payable.
- **Code evidence:** Different ITC heads for recommended vs net payable.
- **Suggested fix direction:** Net payable must use same heads as `recommended_claimable`.
- **Test to add:** net_payable_hint uses min(books,2B) when 2B > books.
- **Twin check:** n/a

### RPT-011 — GSTR RCM line tax rebuilt in report path when line taxes are zero
- **Module:** Reporting → GSTR-1 rate buckets
- **Location:** `backend/reporting/gst_returns.py:247-269`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** `_rate_buckets` recomputes `q2(taxable * rate/100)` when RCM and line taxes are zero — diverges from write-path stored taxes.
- **Trigger / repro:** Legacy RCM invoice with zero line tax fields, non-zero header RCM memos; compare section tax vs header totals.
- **Consequence:** Worksheet rate buckets diverge from invoice headers / GL by paise.
- **Code evidence:** Rebuild branch in `_rate_buckets`.
- **Suggested fix direction:** Prefer stored line/header tax; rebuild only behind explicit migration flag.
- **Test to add:** RCM zero-line-tax invoice buckets match header RCM memos, not recomputed rate.
- **Twin check:** n/a

### RPT-012 — HSN section buckets use gst_rate, rate tables use applied_rate
- **Module:** Reporting → GSTR-1 HSN vs B2
- **Location:** `backend/reporting/gst_returns_sections.py:13`; `backend/reporting/gst_returns.py:241`
- **Type:** Data-integrity | Bug
- **Severity:** High
- **What's wrong:** `accumulate_hsn_line` keys on `gst_rate`; `_rate_buckets` prefers `applied_rate`.
- **Trigger / repro:** Line with `applied_rate != gst_rate`; compare HSN rate key vs B2 rate.
- **Consequence:** HSN (and GSTR-9 table 17) disagree with B2B/B2CS rate rows.
- **Code evidence:** Different rate fields.
- **Suggested fix direction:** Same rate field as GSTR (`applied_rate` with gst_rate fallback).
- **Test to add:** applied_rate≠gst_rate → HSN and B2 same rate key.
- **Twin check:** n/a

### RPT-013 — Bill of Entry ITC period filter is Python-side full scan
- **Module:** Reporting → GSTR-3B / GSTR-9
- **Location:** `backend/reporting/gst_returns.py:1479-1484, 2031-2038`
- **Type:** Improvement | Bug (unbounded)
- **Severity:** High
- **What's wrong:** Loads all COMPLETED+ELIGIBLE BOEs then filters `resolved_itc_period() == period` in Python; GSTR-9 loops ×12 months.
- **Trigger / repro:** Many historical BOEs; generate GSTR-9 FY.
- **Consequence:** Unbounded memory/CPU on import-heavy tenants; easy to miss DB date bounds.
- **Code evidence:** Full queryset then Python period match.
- **Suggested fix direction:** Filter `itc_period` / `boe_date` in SQL to month/FY window.
- **Test to add:** BOE outside period not loaded (or assert queryset filtered).
- **Twin check:** n/a

### RPT-014 — GSTR-9 Table 8 note still describes obsolete import heuristic
- **Module:** Reporting → GSTR-9
- **Location:** `backend/reporting/gst_returns.py:2150-2153`
- **Type:** Silent-failure (honesty) | Broken-feature (docs vs code)
- **Severity:** Medium
- **What's wrong:** Import ITC now from BillOfEntry but table 8 note still says “IGST on purchases without supplier GSTIN”.
- **Trigger / repro:** Read GSTR-9 table 8 notes in API response.
- **Consequence:** CA misreads worksheet basis.
- **Code evidence:** Stale note string vs BOE source at 2023–2038.
- **Suggested fix direction:** Align note with BOE source.
- **Test to add:** Snapshot/assert note text mentions BoE.
- **Twin check:** n/a

### RPT-015 — Exports and cash book materialize full payloads (no streaming)
- **Module:** Reporting → Export / memory
- **Location:** `backend/reporting/views.py:1254-1270, 189-238`
- **Type:** Improvement
- **Severity:** High
- **What's wrong:** ExportView builds full row list → StringIO CSV; cash book XLSX / GSTR XLSX / CA zip in-memory. Dated large ranges unbounded (5000 cap only when date_from missing).
- **Trigger / repro:** Export sales-register for multi-year date_from/date_to.
- **Consequence:** Memory spikes / timeouts for multi-year tenants.
- **Code evidence:** Full materialization; no max span on dated exports.
- **Suggested fix direction:** Require max span; stream CSV; paginate JSON registers.
- **Test to add:** Oversized range returns 400 with clear max-span error.
- **Twin check:** n/a

### RPT-016 — Cancelled-numbers register N+1 + loads all cancelled docs
- **Module:** Reporting → Statutory cancelled register
- **Location:** `backend/reporting/views.py:539-611`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** Per-doc `_reason(...)` query; FY filter in Python after fetching all cancelled.
- **Trigger / repro:** Large cancelled history; open cancelled-numbers register.
- **Consequence:** Slow/heavy; not date-SQL-bounded.
- **Code evidence:** Loop with per-doc reason query; FY filter post-fetch.
- **Suggested fix direction:** Prefetch cancel events; filter FY in DB.
- **Test to add:** Prefetch/assert query count bounded.
- **Twin check:** n/a

### RPT-017 — Cash book (receipts/payments) ≠ GL cash-flow aid
- **Module:** Reporting → Cash reports
- **Location:** `backend/reporting/services.py:592-761`; `backend/accounting/reports.py:181-257`
- **Type:** Data-integrity (dual story)
- **Severity:** Medium
- **What's wrong:** Dashboard cash_position / cash book from posted receipts & supplier payments; accounting cash_flow from JournalLines on 1100/1500*.
- **Trigger / repro:** Books on with journals that don't match receipt docs 1:1.
- **Consequence:** Two “cash” stories for same company when books on.
- **Code evidence:** Different source tables.
- **Suggested fix direction:** Label clearly and/or reconcile; don’t mix KPI sources without disclaimer.
- **Test to add:** With books on, document mismatch surfaces in health/recon or UI label.
- **Twin check:** Accounting module

### RPT-018 — Accounting cash_flow iterates every cash journal line in Python
- **Module:** Reporting / Accounting → cash_flow
- **Location:** `backend/accounting/reports.py:212-226`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** `for line in qs:` with select_related but no aggregation.
- **Trigger / repro:** High-volume cash journal history; open cash-flow report.
- **Consequence:** Slow cash-flow for high-volume tenants.
- **Code evidence:** Python loop over all lines.
- **Suggested fix direction:** `values(source_type).annotate(Sum(...))`.
- **Test to add:** Query count / timing smoke for large fixture.
- **Twin check:** n/a

#### Reporting coverage notes
- Aggregations generally company-scoped; registers/dashboard draft-out but cancelled-in (RPT-004).
- Stock summary qty uses StockBalance (RPT-003); GST worksheets solid with footing checks; issues RPT-010–014.
- Feature flags: backend `assert_gstr_enabled`; frontend `VITE_ENABLE_GSTR`. Live GSP gated. Offline 2B = paying path.
- Highest priority: RPT-001, RPT-003, RPT-004, RPT-010.
