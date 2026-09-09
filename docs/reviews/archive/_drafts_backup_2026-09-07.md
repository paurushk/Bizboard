# Functional Code Review — Bizboard (production stabilization)

Run date: 2026-09-07 · Reviewer: Claude · Build: `5ba05c7` (+ dirty working tree) · Python: 3.12.11 (`backend/.venv`; CI pins 3.14)

> Fresh independent pass against the working tree. New findings continue the permanent **CR-NNN** series from **CR-106**.
> Prior series: [`FUNCTIONAL_CODE_REVIEW_FINDINGS.md`](./FUNCTIONAL_CODE_REVIEW_FINDINGS.md) (CR-001–CR-105).
> Cross-refs at end vs `bugs/INDEX.md`, `MASTER_ISSUE_REGISTER.md`, and prior FIX_PLAN / DEEP reviews.
>
> IDs are append-only — never renumber. A false positive is marked **Invalid**, never deleted.

## Coverage summary

- Modules reviewed: **6/6** — POS, Sales, Purchase, Stock/Godown, Reporting, Accounting *(drafts complete; permanent merge in progress)*
- Findings: *(merging)*
- Test suite: **25 failed, 1214 passed, 10 skipped** in 1520s (Python 3.12.11) → `docs/reviews/_pytest_functional_review_2026-09-07.txt`
  - Notable money-path / honesty failures: GSTR suite (6), SO reservation release (2), CN confirm/paid (phase1 + sprint2), cash book, closed-period posting, B1-034 residual policy, CSV export 400, GSP/honesty (4), serial qty-amend message, CN period-before-number
  - Prior baseline at same tip was 4 failed / 1174 passed — suite grew; failure count rose (remediation vs stale tests + new regressions)

## Coverage matrix

| Module | Core write path reviewed | Reversal path | Concurrency | Tests present | Findings |
|---|---|---|---|---|---|
| POS | *(pending)* | | | | |
| Sales | `SalesService.complete` atomic; SO/DC/CN/DN/return/recurring | cancel / return / CN | SO dual-convert hole; alloc locks OK | strong A-wave; dual-convert/recurring gaps | SALES-001…SALES-009 |
| Purchase | `PurchaseService.complete` stock+AP atomic; import/BoE | cancel / return / CN/DN / BoE | return/DN lock PI; CN lock w/o company_id | strong invoice/BoE; thin note twin gates | PUR-001…PUR-009 |
| Stock/Godown | `InventoryService.post_movement`; transfer/count/serial | compensating ADJ / FIFO restore | BLOCK safe; WARN allow | A6/A10/A11–12, concurrency | STK-007…009,014–017 (CR-048–058 mostly fixed) |
| Reporting | Dashboard KPIs, aging, registers, inventory summary, GSTR, exports | n/a | GST soft_close TOCTOU (RPT-012) | A4/A5/A13/A15 strong; openings/CR-102/span gaps | RPT-001…RPT-012 |
| Accounting | PostingService.post + Complete→GL; books health | reverse / note / cancel | GST soft_close TOCTOU residual; period close locks | a2/a10/a15/phase5 | ACC-001…ACC-007 |

## Review agents

| Module | Agent | Status |
|---|---|---|
| POS | [POS review](493e78e0-0fe0-4d70-a4a0-b4350e114571) | in progress |
| Sales | [Sales review](58cb46ce-3270-47d8-b6c4-d9d26f9855df) | draft complete |
| Purchase | [Purchase review](470bc159-17c0-4d67-be4d-8dd8a3ebd218) | draft complete |
| Stock/Godown | [Stock review](5a8905d1-61b2-453d-aa6a-717e56c8ab24) | draft complete |
| Reporting | [Reporting review](ad676e68-029c-4930-b52a-344b69acf4c3) | draft complete |
| Accounting | [Accounting review](64768c8a-6108-4d96-bad6-9b9403b74e51) | draft complete |

Pytest: **done** — 25 failed, 1214 passed, 10 skipped → `docs/reviews/_pytest_functional_review_2026-09-07.txt`

## Findings

_Module drafts will be appended below. Parent merge assigns permanent CR-106+ IDs._

---

### Module drafts (raw)

_(Provisional IDs; parent renumbers to CR-106+ after all modules land.)_

---

#### Accounting draft ([Accounting review](64768c8a-6108-4d96-bad6-9b9403b74e51))

**Prior CR status (Accounting):** CR-078–081, 083–084, 086–088 FIXED; CR-082 PARTIAL; CR-085 PARTIAL; CR-089 STILL OPEN; CR-103 fixed in backfill only; CR-104 PARTIAL; CR-105 BROKEN FIX (advances folded into control compare).

### ACC-001 — CR-105 “fix” makes AR/AP control false-alarm when advances exist
- **Module:** Accounting → books health / period & FY close
- **Location:** `backend/accounting/services.py:1970–1995`, `1838–1849`; `reports.py:389–394`
- **Type:** Data-integrity | Bug
- **Severity:** Critical
- **What's wrong:** `ar = net("1200")` but `expected_ar = tagged(1200)+tagged(2300)`. Customer advances on 2300 inflate expected vs bare 1200 → `AR_CONTROL_MISMATCH` (same for AP/`1250`). That alert **blocks** soft/hard close and FY close. Docs↔GL correctly wants netted party GL; control check must stay 1200↔tagged-1200.
- **Trigger / repro:** Complete SI ₹1000; post unallocated receipt ₹400 → health `ar.healthy=False`; period close raises.
- **Consequence:** Honest books with advances cannot close; false unhealthy books.
- **Code evidence:** Control compare mixes advance accounts into expected while measuring only control net.
- **Suggested fix direction:** Control health: 1200 vs tagged-1200 only; docs↔GL (or separate advance recon) uses 1200±2300 / 2100±1250.
- **Test to add:** Advance present → AR control healthy; docs-GL uses netted party GL.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-105 (broken fix); CR-082

### ACC-002 — GST soft-close / manual JE post still TOCTOU (CR-104 residual)
- **Module:** Accounting → period gates
- **Location:** `backend/reporting/gst_periods.py:39–52`, `105–136`; `backend/accounting/views.py:231–256` (`JournalViewSet.post` not outer-atomic)
- **Type:** Race
- **Severity:** High
- **What's wrong:** (1) `assert_period_allows_money_amend` only `select_for_update`s an **existing** `GstReturnPeriod`; if none, concurrent `soft_close_period` can create+SOFT_CLOSE after assert → post into soft-closed GST month when no overlapping `AccountingPeriod`. (2) Manual journal `post` runs assert in nested txn (locks released), then flips status — race with soft_close.
- **Trigger / repro:** Concurrent soft_close + Complete with no prior GST row (Postgres); or manual JE post vs soft_close.
- **Consequence:** Money posts into a period that appears soft-closed.
- **Code evidence:** Lock only when row exists; JournalViewSet.post lacks outer `@transaction.atomic`.
- **Suggested fix direction:** Lock/create GST period row under select_for_update before assert; wrap manual post in one atomic with assert+status flip.
- **Test to add:** Concurrent soft_close + Complete (no GST row); manual JE post vs soft_close.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-104 (partial); CR-081

### ACC-003 — Empty POSTED JE still treated as “done” outside backfill (CR-103 residual)
- **Module:** Accounting → health missing-posting + FY close
- **Location:** `backend/accounting/services.py:1928–1932` `_unposted_qs`; `reports.py:360–387` FY_CLOSE early return
- **Type:** Data-integrity | Silent-failure
- **Severity:** High
- **What's wrong:** Backfill `_has_je` correctly requires `lines__isnull=False`. Health excludes any JE by `source_id` regardless of lines → orphan empty POSTED hides `DOCUMENT_MISSING_POSTING`. FY close returns early on empty POSTED FY_CLOSE and still hard-closes periods.
- **Trigger / repro:** Empty POSTED SI JE → health silent; empty FY_CLOSE JE → skips real close work but hard-closes.
- **Consequence:** Missing postings invisible; FY close idempotency wrong.
- **Code evidence:** Health/FY path does not require lines; backfill does.
- **Suggested fix direction:** Treat JE as posted only when it has lines (same predicate as backfill); refuse empty FY_CLOSE as done.
- **Test to add:** Empty POSTED SI → health alerts; empty FY_CLOSE → does not skip real close.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-103 (partial — backfill fixed)

### ACC-004 — Dual ledger can still silently diverge for ops decisions
- **Module:** Accounting → derived ledger vs live GL
- **Location:** `backend/ledgers/services.py:291–315`, `320–336`; `backend/accounting/services.py:2145–2200`, `1838–1849`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** `DOCS_GL_AR/AP_MISMATCH` are warnings only — period close ignores them. Credit limit takes `max(GL, docs)` and logs. Party outstanding can be GL while aging/UI use documents.
- **Trigger / repro:** Untagged manual 1200/2100 lines or partial backfill → drift; close still succeeds.
- **Consequence:** Ops/credit decisions on diverged truths; close does not force reconciliation.
- **Code evidence:** Warn helper exists; close blockers do not include docs↔GL mismatch.
- **Suggested fix direction:** Block close (or force DOCUMENTS_ALWAYS) when drift exceeds tolerance.
- **Test to add:** Large drift blocks close.
- **Twin check:** n-a (Reporting KPI twin)
- **Cross-ref hint:** confirms-still-broken CR-082; theme of CR-060

### ACC-005 — Purchase residual ≤ bound still absorbed; no header/line tax hard-stop
- **Module:** Accounting → purchase tax → GL
- **Location:** `backend/accounting/services.py:1175–1193` vs sales `593–612`
- **Type:** Sales/Purchase-inconsistency | Data-integrity
- **Severity:** Medium
- **What's wrong:** Residuals `≥1` and `≤ max(100, 10% grand)` still become 5110 without `additional_charges`. Sales refuses header/line tax drift > ₹0.05. Cess accounts themselves OK. `test_b1_034_*` still expects large residual to book (test debt vs CR-085).
- **Trigger / repro:** Purchase bill with mid-size tax residual within bound, no additional_charges.
- **Consequence:** Expense dump absorbs tax drift; Sales twin would refuse.
- **Code evidence:** Purchase residual absorb path vs sales hard refuse.
- **Suggested fix direction:** Align purchase with sales hard-stop; update B1-034.
- **Test to add:** Within-bound residual → refuse or audit; update B1-034.
- **Twin check:** y (Sales stricter)
- **Cross-ref hint:** confirms-still-broken CR-085 (partial)

### ACC-006 — Manual journals cannot party-tag AR/AP lines
- **Module:** Accounting → voucher / dual ledger
- **Location:** `backend/accounting/serializers.py:80–91`
- **Type:** Missing-validation | Broken-feature
- **Severity:** Medium
- **What's wrong:** No `customer`/`supplier` fields on journal line serializer → untagged 1200/2100 inflate control vs tagged ledger / docs-GL. Balanced DE + company scope OK.
- **Trigger / repro:** Post manual JE debiting 1200 without party tag.
- **Consequence:** Dual-ledger / control health drift.
- **Code evidence:** Serializer omits party FKs.
- **Suggested fix direction:** Allow optional party tags; require tag when account is AR/AP control.
- **Test to add:** Untagged 1200 line rejected or tagged required.
- **Twin check:** n-a
- **Cross-ref hint:** new (amplifies CR-082)

### ACC-007 — Feature flag dual-key (UI vs API)
- **Module:** Accounting → gating
- **Location:** `web/src/config/features.ts` (`VITE_ENABLE_ACCOUNTING`); API `accounting_enabled` only
- **Type:** Broken-feature
- **Severity:** Low
- **What's wrong:** UI and API can disagree on whether accounting surfaces are live.
- **Trigger / repro:** Enable only one of VITE vs server flag.
- **Consequence:** Nav visible + 403, or hidden + live API.
- **Code evidence:** Dual keys not synchronized.
- **Suggested fix direction:** Single source of truth from API capabilities.
- **Test to add:** Flag mismatch matrix.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-089

**Accounting OK notes:** PostingService.post/reverse atomic; cess/TCS/TDS amount-over-rate with audit; cancel/return reverse; backfill company-scoped; CR-078–081/083–084/086–088 appear fixed in tree.

---

#### Reporting draft ([Reporting review](ad676e68-029c-4930-b52a-344b69acf4c3))

**Prior CR status (Reporting):** CR-060/061/100/101 FIXED (dashboard AR/AP = document aging); CR-102 STILL_OPEN; most CR-062–077 FIXED with residuals below.

### RPT-001 — Opening-balance invoices inflate AR/AP aging and dashboard receivables/payables
- **Module:** Reporting → Dashboard KPIs / aging
- **Location:** `backend/reporting/services.py:139-143` (`receivables_aging`); `:594-599` (`payables_aging`); contrast `:177-210` (`is_opening_balance=False` on turnover)
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** CR-065 fixed MTD sales/purchases to exclude openings, but aging (and AR/AP KPI cards that foot aging) still include opening COMPLETED/RETURNED invoices. GSTR correctly excludes openings.
- **Trigger / repro:** Complete SI with `is_opening_balance=True`, unpaid; turnover KPIs unchanged, receivables/aging rise.
- **Consequence:** AR/AP disagree with GSTR and with sales/purchase KPIs after Tally-style openings.
- **Code evidence:** Aging queryset lacks `is_opening_balance=False`; dashboard reuses aging under a CR-065 comment.
- **Suggested fix direction:** Filter openings out of both aging paths (same predicate as GSTR/turnover).
- **Test to add:** `test_rpt001_opening_balance_excluded_from_ar_ap_aging_and_kpis`
- **Twin check:** y
- **Cross-ref hint:** CR-065 residual; amplifies CR-060/101 after openings

### RPT-002 — Party ledgers still GL-when-books while dashboard AR/AP are document aging
- **Module:** Reporting / Ledgers → Customer/Supplier ledger vs Dashboard
- **Location:** `backend/ledgers/services.py:283-288`; `:320-328` / `:933+`; contrast `reporting/services.py:100-114`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** Dashboard cards are document aging; party ledgers (and WhatsApp outstanding) still switch to GL when books on and basis ≠ DOCUMENTS_ALWAYS.
- **Trigger / repro:** Books on with posting drift/advances; compare Dashboard Receivables to Customer Ledger outstanding.
- **Consequence:** Operators cannot reconcile dashboard ↔ party statements.
- **Code evidence:** `_use_gl_outstanding` still branches ledgers; dashboard intentionally documents-only.
- **Suggested fix direction:** Same outstanding basis for ledger + aging + KPI, or hard UI label + Books Health gate.
- **Test to add:** `test_rpt002_dashboard_ar_equals_sum_customer_ledger_when_books_on`
- **Twin check:** y
- **Cross-ref hint:** CR-060/101 residual; CR-082/105 theme (twin of ACC-004)

### RPT-003 — Inventory `reserved` / `available` still from StockBalance cache (CR-102)
- **Module:** Reporting → inventory summary
- **Location:** `backend/reporting/services.py:533-553,569-570`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** `on_hand` = Σ movements; `reserved` = `StockBalance.reserved`. `reserved_drift` only flags negative or > on_hand, not drift vs open SO reservations.
- **Trigger / repro:** Corrupt `reserved` downward; available overstated; no flag if `reserved ≤ on_hand`.
- **Consequence:** Available qty wrong for ops/reorder.
- **Code evidence:** Reads cache; comment admits no movement sum for reserved.
- **Suggested fix direction:** Derive reserved from confirmed SO / reservation ledger, or always compare to `_confirmed_so_qty`.
- **Test to add:** `test_cr102_reserved_cache_drift_flags_or_corrects_available`
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-102

### RPT-004 — Inventory report UI drops `balance_drift` / `reserved_drift`
- **Module:** Reporting FE → Inventory report
- **Location:** `web/src/pages/reports/InventoryReportPage.tsx:55-64,36-45`
- **Type:** Silent-failure
- **Severity:** Medium
- **What's wrong:** API may return drift flags; FE maps only qty/value columns and never surfaces them.
- **Trigger / repro:** Force balance drift; open Inventory Reports — row looks healthy.
- **Consequence:** Backend honesty flags invisible.
- **Code evidence:** Row mapper omits drift keys; no drift column/chip.
- **Suggested fix direction:** Warning chip/row highlight when either drift flag present.
- **Test to add:** FE: drifted row renders warning
- **Twin check:** n-a
- **Cross-ref hint:** CR-062/102 UX gap

### RPT-005 — `assert_report_date_span` no-ops unless both dates set
- **Module:** Reporting → exports / registers / cash book
- **Location:** `backend/reporting/services.py:82-91`; callers in `views.py`
- **Type:** Bug
- **Severity:** High
- **What's wrong:** Span check returns early if either bound missing. `?date_from=2019-04-01` alone bypasses 366-day cap.
- **Trigger / repro:** Export/GET sales-register with only `date_from` years ago.
- **Consequence:** Multi-year materialization / timeout — CR-074 only partially closed.
- **Code evidence:** `if not date_from or not date_to: return`
- **Suggested fix direction:** Require both bounds, or treat missing `date_to` as today and enforce span.
- **Test to add:** `test_rpt005_date_from_only_rejects_or_caps_span`
- **Twin check:** y
- **Cross-ref hint:** CR-074 residual

### RPT-006 — Product / customer sales endpoints skip date-span assert
- **Module:** Reporting → analytics APIs
- **Location:** `backend/reporting/views.py:155-176`
- **Type:** Improvement | Bug
- **Severity:** Medium
- **What's wrong:** Registers/cash book call span assert; product/customer sales do not.
- **Trigger / repro:** Wide/empty date window on product-sales.
- **Consequence:** Heavy aggregates over full history.
- **Code evidence:** Missing `assert_report_date_span` call.
- **Suggested fix direction:** Same span guard as registers.
- **Test to add:** Over-366d product-sales → 400
- **Twin check:** n-a
- **Cross-ref hint:** CR-074 family

### RPT-007 — Inventory report value can use RunningCost/FIFO layer cache
- **Module:** Reporting → inventory summary valuation
- **Location:** `backend/reporting/services.py:522-551`; `inventory/services.py:1622-1651`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** When on_hand matches StockBalance, value comes from valuation cache (RunningCost/layers), not pure movement replay. Drifted on_hand falls back to `unit_cost * on_hand`.
- **Trigger / repro:** Wrong RunningCost with matched qty → summary shows movement qty + cached value.
- **Consequence:** Inventory report total ≠ BS inventory_valuation / GL 1400 without a flag.
- **Code evidence:** Dual store for qty vs value.
- **Suggested fix direction:** Always value from movement-consistent engine, or flag `value_source` / variance vs GL.
- **Test to add:** Corrupt RunningCost with matched qty → flag or recompute
- **Twin check:** Accounting BS inventory_valuation
- **Cross-ref hint:** CR-062 value half

### RPT-008 — Dashboard `low_stock_count` uses StockBalance cache
- **Module:** Reporting → Dashboard KPI
- **Location:** `backend/reporting/services.py:225-227`; `inventory/views.py:54-91`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** Inventory summary on_hand = Σ movements; low-stock KPI uses `StockBalance.on_hand - reserved`.
- **Trigger / repro:** Balance drift vs movements → dashboard low-stock ≠ Inventory report.
- **Consequence:** Inconsistent ops signals.
- **Code evidence:** Different SoT for low-stock vs inventory summary.
- **Suggested fix direction:** Drive alerts from movement on_hand + consistent reserved policy.
- **Test to add:** Balance drift → low_stock_count matches movement-based available
- **Twin check:** n-a
- **Cross-ref hint:** CR-062 family

### RPT-009 — Dashboard returns AR aging buckets but not AP aging
- **Module:** Reporting FE / API
- **Location:** `backend/reporting/services.py:249-252`; `DashboardPage.tsx:89-107,253-274`
- **Type:** Broken-feature
- **Severity:** Low
- **What's wrong:** Payables KPI foots aging server-side but response omits `payables_aging`; UI only charts receivables.
- **Trigger / repro:** No AP buckets in dashboard JSON to verify CR-101 footing.
- **Consequence:** Asymmetric AR/AP UX; operators cannot visually verify AP.
- **Code evidence:** Payload/UI asymmetry.
- **Suggested fix direction:** Include `payables_aging` + FE chart, or document intentional omission.
- **Test to add:** Dashboard JSON `payables_aging` sums to payables
- **Twin check:** y
- **Cross-ref hint:** CR-101 UX completeness

### RPT-010 — No stock ledger / stock aging report in Reporting scope
- **Module:** Reporting → stock
- **Location:** Scope gap vs checklist; `ReportService.inventory_summary` only
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** Checklist requires stock summary/ledger/aging = sum(StockMovement); only summary exists.
- **Trigger / repro:** Navigate reports — no movement ledger or batch/expiry aging worksheet.
- **Consequence:** FEFO/batch aging and movement audit not operator-facing.
- **Code evidence:** No reporting API/page for stock ledger/aging.
- **Suggested fix direction:** Movement-sourced stock ledger + batch/expiry aging.
- **Test to add:** Ledger foots to Σ movements per SKU/WH
- **Twin check:** n-a
- **Cross-ref hint:** Checklist item unmet

### RPT-011 — CSV/XLSX/GSTR exports still fully materialize in memory
- **Module:** Reporting → ExportView / CashBook / GSTR xlsx
- **Location:** `backend/reporting/views.py:214-242,647-656,1298-1310`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** Even with span cap, rows → StringIO/BytesIO/Workbook in one shot; no streaming.
- **Trigger / repro:** Dense POS tenant, 366-day sales-register CSV.
- **Consequence:** Memory spikes / worker OOM under load.
- **Code evidence:** Full in-memory builders.
- **Suggested fix direction:** Streaming response; independent row-count ceiling.
- **Test to add:** Row-count ceiling 400 when exceeded
- **Twin check:** n-a
- **Cross-ref hint:** CR-074 residual

### RPT-012 — GST soft-close vs Complete TOCTOU when period row missing
- **Module:** Reporting → `gst_periods`
- **Location:** `backend/reporting/gst_periods.py:39-52`, `:123-136`
- **Type:** Race
- **Severity:** High
- **What's wrong:** If no `GstReturnPeriod` row yet, assert does not lock/create; concurrent soft_close can SOFT_CLOSE after assert passed.
- **Trigger / repro:** First soft-close of month racing Complete (Postgres).
- **Consequence:** Money posts into newly soft-closed GST month.
- **Code evidence:** Assert only locks existing row; soft_close can create under lock.
- **Suggested fix direction:** `get_or_create` + `select_for_update` in assert path.
- **Test to add:** Concurrent soft_close + complete (Postgres)
- **Twin check:** n-a (AccountingPeriod already locks)
- **Cross-ref hint:** confirms-still-broken CR-104 (same as ACC-002)

**Reporting OK notes:** CR-060/061/100/101 fixed; most CR-062–077 closed; GSTR footing/HSN/BoE/3B ITC look sound; company scoping on GSTR bases OK.

---

#### Sales draft ([Sales review](58cb46ce-3270-47d8-b6c4-d9d26f9855df))

**Prior CR status (Sales):** CR-014–016, 018–021, 023–025, 027–029, 093–096 FIXED; CR-017/026 PARTIAL; CR-022 STILL OPEN; CR-015 error-path residual → SALES-002.

### SALES-001 — SO can convert to invoice **and** delivery challan (double stock / double AR)
- **Module:** Sales → Orders / DC / Invoice chain
- **Location:** `backend/sales/notes_services.py` `convert_sales_order_to_challan` ~614–637; `complete_challan` ~770–788; `convert_delivery_challan` ~927–931
- **Type:** Data-integrity | Race
- **Severity:** Critical
- **What's wrong:** `convert_sales_order` blocks if live challan / checks `converted_invoice`; `convert_sales_order_to_challan` does **not** check `converted_invoice_id`. Manual DC can link an already-invoiced SO. Completing challan + invoice can each post SALE / AR.
- **Trigger / repro:** Confirm SO → Convert to invoice → Convert to challan → complete both.
- **Consequence:** Double stock out, double AR, reservation released twice. Release-blocking.
- **Code evidence:** Challan convert lacks `converted_invoice_id` guard present on invoice convert; complete_challan does not reject invoiced SO.
- **Suggested fix direction:** Reject challan convert/create/complete when SO has `converted_invoice_id`; reject DC→invoice if SO already linked to another invoice.
- **Test to add:** `test_so_invoice_then_challan_blocked`; assert single SALE qty.
- **Twin check:** Check PO→GRN+bill fork if any
- **Cross-ref hint:** new; interacts with CR-020/022

### SALES-002 — Recurring poison/error advances `next_run_at` and skips the period
- **Module:** Sales → Recurring
- **Location:** `backend/sales/recurring.py` `process_due_schedules` ~174–187
- **Type:** Silent-failure | Bug
- **Severity:** High
- **What's wrong:** Locked periods correctly do not advance (CR-015 fixed). On any exception, handler advances `next_run_at` without writing `RecurringInvoiceRun` — that `period_key` is never retried.
- **Trigger / repro:** Invalid template product; beat runs; fix template; next beat skips the failed month.
- **Consequence:** Silent missed billing for paying tenants.
- **Code evidence:** `except Exception` advances schedule.
- **Suggested fix direction:** Do not advance on error; park last_error; retry same period_key.
- **Test to add:** Fail once → fix → same period_key draft created.
- **Twin check:** n
- **Cross-ref hint:** CR-015 residual

### SALES-003 — Draft SO remains editable after convert-to-invoice
- **Module:** Sales → Orders
- **Location:** `phase1_serializers.py` `SalesOrderSerializer.update` ~235–246; `convert_sales_order` leaves DRAFT/CONFIRMED
- **Type:** Missing-validation
- **Severity:** Medium
- **What's wrong:** After convert, SO can stay DRAFT with `converted_invoice` set; serializer only blocks non-DRAFT edits.
- **Trigger / repro:** Draft SO → convert → PATCH SO items.
- **Consequence:** Source SO and invoice diverge.
- **Code evidence:** No block on `converted_invoice_id`.
- **Suggested fix direction:** Freeze SO when `converted_invoice_id` set.
- **Test to add:** Convert then PATCH SO → 400.
- **Twin check:** y (PO)
- **Cross-ref hint:** new

### SALES-004 — SO reservation qty does not track amended draft invoice qty
- **Module:** Sales → Orders + Invoice complete
- **Location:** `confirm_sales_order` reserves SO qty; `SalesService.complete` ~1066–1071 releases SO qty; draft invoice `set_items` free
- **Type:** Race | Data-integrity
- **Severity:** Medium
- **What's wrong:** Reservation is SO qty, not current invoice qty. Increase invoice qty leaves unprotected stock.
- **Trigger / repro:** Confirm SO qty 10 → convert → edit invoice to 15 → complete.
- **Consequence:** Concurrent oversell / intermittent complete failures.
- **Code evidence:** Release uses SO lines, not invoice lines.
- **Suggested fix direction:** Re-reserve to invoice qty on amend, or freeze qty to SO.
- **Test to add:** After amend, available reflects invoice qty reservation.
- **Twin check:** n-a / check PO
- **Cross-ref hint:** CR-020 residual

### SALES-005 — Auto sales-return CN silent-confirms paid / price-override
- **Module:** Sales → Returns + Credit notes
- **Location:** `return_service.py` ~282–284; headroom in `notes_services.py`
- **Type:** Data-integrity | Missing-validation
- **Severity:** Medium
- **What's wrong:** Standalone CN requires confirms (CR-096); auto-CN from return always passes confirm flags → paid invoice return without unallocate.
- **Trigger / repro:** Full receipt allocate → complete sales return.
- **Consequence:** Sticky over-allocation; AR messy.
- **Code evidence:** Hard-coded `confirm_paid_invoice=True` / price override.
- **Suggested fix direction:** Auto-unallocate up to CN amount, or require explicit return confirm.
- **Test to add:** Paid invoice + return → allocations adjusted or 400.
- **Twin check:** y (purchase return)
- **Cross-ref hint:** CR-017/096 residual

### SALES-006 — Document chain still all-or-nothing (no partial convert)
- **Module:** Sales → Quotation / SO / DC
- **Location:** convert_* functions — full line copy
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** No per-line converted qty; cannot ship/invoice 40 of 100 without splitting docs.
- **Trigger / repro:** SO 100, customer wants 40 now.
- **Consequence:** SMB dispatch friction / over-shipping drafts.
- **Code evidence:** Full-line convert only.
- **Suggested fix direction:** Track converted qty per line, or document as known limitation.
- **Test to add:** (If implementing) partial DC then invoice remainder.
- **Twin check:** y
- **Cross-ref hint:** confirms-still-broken CR-022

### SALES-007 — Delivery challan `complete` has no idempotency wrap
- **Module:** Sales → Delivery challan + Idempotency
- **Location:** `phase1_views.py` ~324–327; `MONEY_IDEMPOTENCY_SCOPES` lacks challan; FE sends no key
- **Type:** Missing-validation | Silent-failure
- **Severity:** Medium
- **What's wrong:** Invoice/return/CN completes wrapped; challan complete posts stock without `wrap_idempotent`. Retry after timeout → hard error, not cached body.
- **Trigger / repro:** Timeout after successful challan complete; retry.
- **Consequence:** Ops confusion; weak money-scope discipline when stock posts.
- **Code evidence:** No scope / no wrap / no FE key.
- **Suggested fix direction:** Mirror invoice complete idempotency.
- **Test to add:** Double-complete same key → identical 200 + single SALE set.
- **Twin check:** y (PO convert / GRN)
- **Cross-ref hint:** CR-030 pattern twin

### SALES-008 — CN `select_for_update` omits `company_id` (DN has it)
- **Module:** Sales → Credit notes
- **Location:** `notes_services.py` `complete_credit_note` ~143 vs DN ~349–352
- **Type:** Cross-tenant (defense-in-depth)
- **Severity:** Low
- **What's wrong:** DN locks `pk` + `company_id`; CN locks by `pk` only.
- **Trigger / repro:** Mismatched note.company / invoice.company via non-API path.
- **Consequence:** Cross-tenant lock/mutate if invariant bypassed.
- **Code evidence:** Asymmetric lock queries.
- **Suggested fix direction:** Same `get(pk=..., company_id=...)` as DN.
- **Test to add:** Cross-company invoice id on CN complete → 404/400.
- **Twin check:** y (PUR-005)
- **Cross-ref hint:** CR-093 fixed DN; CN left behind

### SALES-009 — Dead stock-delta branch remains in `set_items` after qty amend ban
- **Module:** Sales → Amend
- **Location:** `services.py` `set_items` ~578–612 then ~653–690
- **Type:** Improvement
- **Severity:** Low
- **What's wrong:** Qty changes raise early (CR-024); later stock-delta loop unreachable for qty≠0 — footgun if raise weakened.
- **Trigger / repro:** N/A (unreachable).
- **Consequence:** Maintenance risk.
- **Code evidence:** Dead path after raise.
- **Suggested fix direction:** Delete delta stock branch; keep price-only + GL adjust.
- **Test to add:** Existing CR-024 test sufficient.
- **Twin check:** y (purchase set_items)
- **Cross-ref hint:** CR-024 follow-through

**Sales OK notes:** Invoice complete TX boundary solid (period gate before number; stock+COGS+GL in atomic; PDF on_commit). CR-094 DC×SO tenancy fixed. IRN FAILED non-live. Alloc concurrency OK.

---

#### Purchase draft ([Purchase review](470bc159-17c0-4d67-be4d-8dd8a3ebd218))

**Prior CR status (Purchase):** CR-030/031/034–037/039/097/098 FIXED; CR-032/033 policy OK; CR-038/041/045/047 PARTIAL residuals below.

### PUR-001 — Purchase CN/DN `complete` missing Sales twin integrity gates
- **Module:** Purchase → notes
- **Location:** `backend/purchases/notes_services.py:193–252` (CN), `:321–390` (DN); contrast `sales/notes_services.py`
- **Type:** Missing-validation | Sales/Purchase-inconsistency | Data-integrity
- **Severity:** High
- **What's wrong:** Purchase note complete only enforces monetary headroom — no source status COMPLETED/RETURNED, note_date≥invoice_date, source_item qty caps, paid/price/additional confirms, or PURCHASE_RETURN reason requiring return FK.
- **Trigger / repro:** CN against DRAFT bill; or CN qty > line with grand_total ≤ headroom; or CN on fully paid bill without confirm.
- **Consequence:** AP/ITC notes against non-posted bills; over-credit; silent over-allocation; stock-less “return” CN.
- **Code evidence:** CN lock/headroom only; Sales has full gate set.
- **Suggested fix direction:** Port Sales CN/DN complete gates 1:1 + FE confirms.
- **Test to add:** draft invoice / source qty / paid confirm / return-reason FK tests.
- **Twin check:** y (Sales stricter)
- **Cross-ref hint:** new (twins CR-017/018/026/096)

### PUR-002 — Purchase CN/DN allow supplier ≠ linked bill supplier
- **Module:** Purchase → notes API
- **Location:** `phase1_serializers.py` CN ~52–59, DN ~109–116; contrast Return / Sales CN
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** Company-scoped FKs only; no `supplier.pk == purchase_invoice.supplier_id`.
- **Trigger / repro:** POST CN supplier=A, invoice=B’s bill.
- **Consequence:** AP relief on A while consuming B’s headroom; GSTR/party ledgers diverge.
- **Code evidence:** Sales/Return validate match; purchase notes do not.
- **Suggested fix direction:** Same validate as Sales/Return.
- **Test to add:** `test_purchase_cn_rejects_supplier_invoice_mismatch`
- **Twin check:** y
- **Cross-ref hint:** new

### PUR-003 — Return `unit_name` / base-qty headroom still unsafe (CR-045 residual)
- **Module:** Purchase → returns
- **Location:** `serializers.py:301–318`; `_returned_quantities` / headroom / stock convert in `services.py`
- **Type:** Data-integrity
- **Severity:** High (alt-unit SKUs) / Medium otherwise
- **What's wrong:** Migration snapshots `unit_name`, but API cannot send/read it; headroom compares document qty while stock uses base qty.
- **Trigger / repro:** Bill in BOX; return defaulting to PCS.
- **Consequence:** Over/under stock vs billed; auto CN amounts wrong.
- **Code evidence:** Serializer omits `unit_name`; headroom uses `Sum("quantity")`.
- **Suggested fix direction:** Expose unit_name; headroom in base units.
- **Test to add:** `test_purchase_return_alternate_unit_headroom_base_qty`
- **Twin check:** y
- **Cross-ref hint:** confirms-still-broken CR-045

### PUR-004 — Purchase debit note cannot carry `additional_charges`
- **Module:** Purchase → DN
- **Location:** `PurchaseDebitNote` model (no field); CN has field+API
- **Type:** Broken-feature | Sales/Purchase-inconsistency
- **Severity:** Medium
- **What's wrong:** `set_debit_note_items` always sees additional_charges=0. Freight DN impossible via API.
- **Trigger / repro:** Attempt DN with freight; field absent.
- **Consequence:** Operators pad unit prices; AP/GL charge legs missing.
- **Code evidence:** Model/serializer lack field CN has.
- **Suggested fix direction:** Add model field + serializer + editor (mirror CN).
- **Test to add:** `test_purchase_dn_additional_charges_in_totals_and_gl`
- **Twin check:** y
- **Cross-ref hint:** confirms-still-broken CR-038

### PUR-005 — Purchase CN locks source invoice without `company_id`
- **Module:** Purchase → tenancy hardening
- **Location:** `notes_services.py:207` vs DN `:339–341`
- **Type:** Cross-tenant (defense-in-depth)
- **Severity:** Medium
- **What's wrong:** `select_for_update().get(pk=...)` without `company_id=note.company_id`.
- **Trigger / repro:** Legacy cross-company purchase_invoice_id.
- **Consequence:** Headroom/lock against wrong tenant invoice.
- **Code evidence:** Asymmetric with DN/return.
- **Suggested fix direction:** Same get(pk, company_id) as DN.
- **Test to add:** Cross-company invoice id → 404/400.
- **Twin check:** y (SALES-008)
- **Cross-ref hint:** new

### PUR-006 — PO `convert` has no idempotency scope
- **Module:** Purchase → PO
- **Location:** `phase1_views.py:189–194`; `MONEY_IDEMPOTENCY_SCOPES` lacks `purchase_order_convert`
- **Type:** Missing-validation
- **Severity:** Medium
- **What's wrong:** Convert creates draft PI + CONVERTED atomically but HTTP has no `wrap_idempotent`. Lost response → “Cannot convert” with draft already exists.
- **Trigger / repro:** Double-submit / timeout after commit.
- **Consequence:** Operator confusion; no durable replay.
- **Code evidence:** No scope in MONEY set; no wrap.
- **Suggested fix direction:** wrap_idempotent + FE gesture key.
- **Test to add:** `test_po_convert_idempotent_replay`
- **Twin check:** y (SALES-007)
- **Cross-ref hint:** new

### PUR-007 — Nested `batch` / note `product` PKs not company-scoped at serializer
- **Module:** Purchase → company_id scoping
- **Location:** `PurchaseItemSerializer.batch`; CN/DN item product default ModelSerializer
- **Type:** Cross-tenant (defense-in-depth)
- **Severity:** Medium (Low if RLS always on)
- **What's wrong:** Invoice/return product uses CompanyPrimaryKeyRelatedField; note lines and batch do not (service may still reject).
- **Trigger / repro:** Cross-tenant product/batch id without RLS.
- **Consequence:** Opaque errors or worse if path skips `_validate_lines`.
- **Code evidence:** Inconsistent field types.
- **Suggested fix direction:** CompanyPrimaryKeyRelatedField for batch and note/PO product.
- **Test to add:** batch + CN product cross-tenant.
- **Twin check:** y
- **Cross-ref hint:** CR-047 class residual

### PUR-008 — Supplier payment `bank_account` FK still unscoped (CR-047 residual)
- **Module:** Payments → supplier payment
- **Location:** `payments/serializers.py:103–121`; service checks company at `:335`
- **Type:** Missing-validation
- **Severity:** Low
- **What's wrong:** Supplier scoped; bank_account still global until service.
- **Trigger / repro:** Cross-company bank account id.
- **Consequence:** Service 400; residual before service / non-RLS.
- **Code evidence:** Serializer asymmetry.
- **Suggested fix direction:** Scope bank_account queryset like supplier.
- **Test to add:** Cross-company bank_account → 400 at serializer.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-047

### PUR-009 — Bill-import `confirm_non_gst` has no FE wiring (CR-041 residual)
- **Module:** Purchase → bill import UI
- **Location:** Backend `imports/services.py`; FE `web/src/pages/imports/*` — no confirm_non_gst
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** Backend defaults all-zero lines to GST unless confirm; SPA never sets it.
- **Trigger / repro:** Upload 0%-only bill of supply → always GST type.
- **Consequence:** Wrong purchase_type unless API/manual edit.
- **Code evidence:** No FE wiring for confirm flag.
- **Suggested fix direction:** Preview checkbox → update_preview({ confirm_non_gst }).
- **Test to add:** UI/API commit with confirm flag.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-041

**Purchase OK notes:** Bill complete stock+AP one atomic; CR-097/098 cancel/BoE draft unlink fixed; bill import all-or-nothing; supplier alloc locks + match; landed cost charges→5110 documented policy.

---

#### Stock/Godown draft ([Stock review](5a8905d1-61b2-453d-aa6a-717e56c8ab24))

**Prior CR status (Stock):** CR-048–053, 057–058 FIXED; CR-054/055/056/059 PARTIAL/accepted residuals; CR-099 STILL BROKEN (expanded as STK-015). New: STK-016 offline 409, STK-017 append-only hole.

### STK-007 — Balance vs `sum(movements)`: no runtime reconciliation (CR-054 residual)
- **Module:** Stock → StockBalance drift
- **Location:** Hot path OK `inventory/services.py` ~181–230; report flags `reporting/services.py` ~485–568; UI `CurrentStockPage.tsx` still `listStock` → StockBalance
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** Report uses movement sum + `balance_drift`; Current Stock UI is cache-first; no scheduled balance↔movement health check.
- **Trigger / repro:** Corrupt `on_hand` → Current Stock wrong; inventory summary may flag drift.
- **Consequence:** Ops screens show wrong available until rebuild.
- **Code evidence:** UI reads StockBalance; comment notes no scheduled health.
- **Suggested fix direction:** UI/ops parity with movement sum or scheduled alert.
- **Test to add:** Drift → Current Stock warns or matches movement sum.
- **Twin check:** n-a (RPT-003/008 related)
- **Cross-ref hint:** confirms-still-broken CR-054; CR-062/102 theme

### STK-008 — Transfers: no in-transit; DRAFT no reserve (CR-055 accepted)
- **Module:** Stock → transfer
- **Location:** `models.py` statuses DRAFT/COMPLETED/CANCELLED; `complete` OUT+IN atomic ~1320–1393
- **Type:** Broken-feature | Missing-validation
- **Severity:** Medium
- **What's wrong:** DRAFT non-binding; concurrent sale can empty source before complete. No in-transit state.
- **Trigger / repro:** Draft transfer qty, concurrent invoice sells source stock, then complete transfer.
- **Consequence:** Multi-godown races under load (BLOCK still prevents negative).
- **Code evidence:** Comment documents DRAFT non-binding; statuses lack IN_TRANSIT.
- **Suggested fix direction:** Reserve on draft or document as known limitation.
- **Test to add:** Concurrent sale vs draft transfer under BLOCK.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-055 (product-accepted doc)

### STK-009 — Stock-count KEEP_SERVER / conflict copy (CR-056 residual)
- **Module:** Stock → count conflict
- **Location:** `views.py` ~705–715; `StockConflictModal.tsx` ~42–47; `en.ts` copy
- **Type:** Silent-failure | Missing-validation
- **Severity:** Medium
- **What's wrong:** KEEP_SERVER skips drifted lines but still POSTED; copy does not say physical count abandoned for those SKUs; FE prefers Keep Server.
- **Trigger / repro:** Count conflict → Keep Server → POSTED without those SKUs adjusted.
- **Consequence:** Operators think count applied; drifted SKUs unchanged.
- **Code evidence:** Skip-then-POSTED; preferential Keep Server UX.
- **Suggested fix direction:** Explicit abandon copy; or refuse POSTED until all lines resolved.
- **Test to add:** KEEP_SERVER → drifted lines unchanged + UI copy asserts.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-056; see STK-016

### STK-014 — FIFO verify not automated (CR-059 residual)
- **Module:** Stock → cost layers
- **Location:** `verify_fifo_layers` ~1946–1990; `seed_fifo_layers_from_balances` can set `source_movement=None`
- **Type:** Improvement | Data-integrity
- **Severity:** Medium
- **What's wrong:** Verify not scheduled; seed can create layers without source movement.
- **Trigger / repro:** FIFO tenant after cutover without running verify.
- **Consequence:** Silent layer/on_hand drift until noticed.
- **Code evidence:** Docs-only test; no scheduled job.
- **Suggested fix direction:** Schedule verify after cutover; refuse seed without source_movement when possible.
- **Test to add:** Beyond docs-string assert.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-059

### STK-015 — Manual serial return resolves wrong / empty SALE move (CR-099)
- **Module:** Stock → Serial / FIFO
- **Location:** `inventory/views.py` `_sale_movement_for_serial` ~412–421; transition ~495–514
- **Type:** Data-integrity | Bug
- **Severity:** High
- **What's wrong:** First SalesItem whose JSON contains the serial wins even if that invoice has **no** SALE moves (draft can shadow). Multi-line same SKU maps index across all product SALE moves → wrong peel/cost.
- **Trigger / repro:** Complete sale of SN; newer draft lists same SN; manual return. Or two completed lines same SKU different costs; return second line’s serial.
- **Consequence:** FIFO understatement / wrong unit cost; qty still +1 AVAILABLE.
- **Code evidence:** Newest matching item short-circuits; empty moves skip restore_fifo_peels.
- **Suggested fix direction:** Prefer COMPLETED invoices with SALE moves; map serial→move by document line.
- **Test to add:** Draft-shadow + multi-line serial return asserts.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-099

### STK-016 — Offline stock-count flush cannot resolve 409 conflicts
- **Module:** Stock → Offline / godown conflict
- **Location:** `StockCountPage.tsx` ~92–96; `useStockOffline.ts` ~16–20; `invoiceDraftCache.ts` ~420–422
- **Type:** Broken-feature | Silent-failure
- **Severity:** High
- **What's wrong:** Offline queue stores empty `resolveConflicts`; flush posts without resolve; 409 fails outbox with no StockConflictModal on auto-flush.
- **Trigger / repro:** Queue count offline → intervening sale → online flush.
- **Consequence:** Offline counts stuck forever; “sync failed” with no Keep Server/Local path.
- **Code evidence:** No conflict modal on outbox path; online path has modal.
- **Suggested fix direction:** Surface conflict modal (or re-open count) before retry.
- **Test to add:** Offline flush 409 → conflict UI → successful resolve.
- **Twin check:** n-a
- **Cross-ref hint:** new (amplifies CR-056)

### STK-017 — Purchase price amend mutates `StockMovement.unit_cost` outside `stamp_cost`
- **Module:** Stock → Movements / purchase caller
- **Location:** `purchases/services.py` `restamp_fifo_layers_for_price_amend` ~470; contrast `models.py` `stamp_cost` ~149–180
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** Raw `StockMovement.objects.filter(pk=...).update(unit_cost=...)` bypasses model `save` guard and documented `stamp_cost` — append-only invariant hole.
- **Trigger / repro:** H9 price-only amend on FIFO purchase with unpeeled layers.
- **Consequence:** Audit/append-only contract broken; no stamp_cost lock pattern.
- **Code evidence:** QuerySet `.update` only live mutate besides stamp_cost.
- **Suggested fix direction:** Use `StockMovement.stamp_cost(...)` or compensating movement.
- **Test to add:** Assert restamp uses stamp_cost / no raw update.
- **Twin check:** y (Purchase)
- **Cross-ref hint:** new (CR-053 class of hole)

**Stock OK notes:** CR-048–053/057–058 fixed; post_movement lock-before-check; BLOCK concurrency solid; import void append-only; period gates on count/transfer; WARN running cost tracks negatives; default warehouse unique OK.
