# Functional Code Review — Bizboard (production stabilization)

Run date: 2026-09-07 · Reviewer: Claude · Build: `5ba05c7` (+ dirty working tree) · Python: 3.12.11 (`backend/.venv`; CI pins 3.14)

> Fresh independent pass against the working tree. Permanent IDs continue from **CR-106**.
> Prior series: [`FUNCTIONAL_CODE_REVIEW_FINDINGS.md`](./FUNCTIONAL_CODE_REVIEW_FINDINGS.md) (CR-001–CR-105).
> **Fix plan (all 57):** [`FIX_PLAN_FUNCTIONAL_2026-09-07.md`](./FIX_PLAN_FUNCTIONAL_2026-09-07.md) (rev **2026-09-07b** — B0/A15/B2a/B2b/B8-POS).
> **Gap closure:** [`FIX_PLAN_GAP_CLOSURE_2026-09-07.md`](./FIX_PLAN_GAP_CLOSURE_2026-09-07.md) (rev b).
> Raw module drafts (pre-renumber): [`_drafts_backup_2026-09-07.md`](./_drafts_backup_2026-09-07.md).
> IDs are append-only — never renumber. A false positive is marked **Invalid**, never deleted.

## Coverage summary

- Modules reviewed: **6/6** — POS, Sales, Purchase, Stock/Godown, Reporting, Accounting
- Findings (**this pass, CR-106–CR-162**): **3 Critical**, **16 High**, **30 Medium**, **8 Low** (total **57**)
  - Plus many prior CR-001–105 items re-verified **FIXED** in tree (see per-module OK notes in draft backup)
- **Do not ship pilot** until Criticals **CR-120**, **CR-144**, **CR-157** are fixed; treat Highs in Top 10 as launch blockers for books/stock honesty
- Test suite: **25 failed, 1214 passed, 10 skipped** in 1520s → [`_pytest_functional_review_2026-09-07.txt`](./_pytest_functional_review_2026-09-07.txt)
  - Notable: GSTR (6), SO reservation (2), CN confirm/paid, cash book, closed-period, B1-034 residual, CSV export 400, GSP/honesty (4), serial qty-amend message, CN period-before-number
  - Prior baseline same tip: 4 failed / 1174 passed — suite grew; failures rose (stale tests vs remediations + regressions)

## Coverage matrix

| Module | Core write path reviewed | Reversal path | Concurrency | Tests present | Findings |
|---|---|---|---|---|---|
| POS | Multi-HTTP create→complete→receipt→alloc→thermal; offline flush | via Sales cancel/return | BLOCK stock lock OK; FE double-click race | FE unit strong; no E2E half-success/reload | CR-106–119 |
| Sales | `SalesService.complete` atomic; SO/DC/CN/DN/return/recurring | cancel / return / CN | SO dual-convert hole; alloc locks OK | A-wave strong; dual-convert/recurring gaps | CR-120–128 |
| Purchase | `PurchaseService.complete` stock+AP atomic; import/BoE | cancel / return / CN/DN / BoE | return/DN lock PI; CN lock w/o company_id | strong invoice/BoE; thin note twin gates | CR-129–137 |
| Stock/Godown | `InventoryService.post_movement`; transfer/count/serial | compensating ADJ / FIFO restore | BLOCK safe; WARN allow | A6/A10/A11–12, concurrency | CR-138–144 |
| Reporting | Dashboard KPIs, aging, registers, inventory, GSTR, exports | n/a | GST soft_close TOCTOU | A4/A5/A13/A15; openings/span gaps | CR-145–156 |
| Accounting | PostingService.post + Complete→GL; books health | reverse / note / cancel | GST TOCTOU residual; period locks | a2/a10/a15/phase5 | CR-156–162 |

## Review agents

| Module | Agent | Status |
|---|---|---|
| POS | [POS review](493e78e0-0fe0-4d70-a4a0-b4350e114571) | draft complete |
| Sales | [Sales review](58cb46ce-3270-47d8-b6c4-d9d26f9855df) | draft complete |
| Purchase | [Purchase review](470bc159-17c0-4d67-be4d-8dd8a3ebd218) | draft complete |
| Stock/Godown | [Stock review](5a8905d1-61b2-453d-aa6a-717e56c8ab24) | draft complete |
| Reporting | [Reporting review](ad676e68-029c-4930-b52a-344b69acf4c3) | draft complete |
| Accounting | [Accounting review](64768c8a-6108-4d96-bad6-9b9403b74e51) | draft complete |

## Findings

### CR-106 — Reloaded `cashPending` cannot finish payment in POS `(POS-001)`
- **Module:** POS → cash settlement resume
- **Location:** `web/src/pages/pos/PosPage.tsx:396–405`, `:959–962`, `:1632–1636`
- **Type:** Data-integrity | Broken-feature
- **Severity:** High
- **What's wrong:** sessionStorage restores mid-settlement cash, but after reload cart is empty; checkout gates on cart before resume; Cash disabled when empty.
- **Trigger / repro:** Complete OK → kill before receipt → reload `/pos` → try Cash.
- **Consequence:** COMPLETED unpaid invoice; stock gone; resume is a false promise.
- **Code evidence:** Restore sets keys only; empty-cart check precedes `cashPending` resume.
- **Suggested fix direction:** If `cashPending`, skip cart gates; “Finish payment” CTA with restored key.
- **Test to add:** `pos_reload_mid_settlement_resumes_receipt_without_cart`
- **Twin check:** n-a
- **Cross-ref:** confirms-still-broken **CR-091**

### CR-107 — Sale settlement is multi round-trip, not one server transaction `(POS-002)`
- **Module:** POS → sales + payments
- **Location:** `PosPage.tsx:614–755`; `flushPosCheckout.ts:53–144`; `sales/services.py` complete; `payments/services.py`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** Separate atomics per HTTP step; stock+GL commit before money.
- **Trigger / repro:** Drop network after complete 200, before receipt.
- **Consequence:** Unpaid COMPLETED invoices / unallocated receipts.
- **Code evidence:** Four distinct service entrypoints.
- **Suggested fix direction:** Idempotent POS checkout endpoint, or harden durable resume (CR-106/108).
- **Test to add:** `pos_checkout_half_success_matrix_complete_ok_receipt_fail`
- **Twin check:** y
- **Cross-ref:** confirms-still-broken **CR-002** (product-accepted Phase 2)

### CR-108 — UPI mid-settlement not durable across reload `(POS-003)`
- **Module:** POS → UPI
- **Location:** `PosPage.tsx:774–839` (no persist analogue)
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** UPI state only in React; reload clears; no in-POS resume.
- **Trigger / repro:** UPI → QR shown → reload.
- **Consequence:** Stock posted, payment unfinished.
- **Code evidence:** Cash has sessionStorage; UPI only `setUpiPending`.
- **Suggested fix direction:** Persist UPI pending like cash; “Confirm UPI” after restore.
- **Test to add:** `pos_upi_reload_mid_settlement_resumes_confirm`
- **Twin check:** n-a
- **Cross-ref:** **new** (UPI twin of CR-091)

### CR-109 — `cashPending` survives logout; company-scoped only `(POS-004)`
- **Module:** POS → session
- **Location:** `posStatus.ts:135–190`; `AuthContext.tsx:97–117`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** Mid-settlement snapshot not wiped on sign-out; not user-scoped.
- **Trigger / repro:** User A incomplete settlement → logout → User B same company.
- **Consequence:** Wrong operator inherits unpaid cue.
- **Code evidence:** Logout clears drafts only.
- **Suggested fix direction:** Scope `companyId:userId`; clear on logout.
- **Test to add:** `pos_logout_clears_cash_pending_storage`
- **Twin check:** n-a
- **Cross-ref:** **new**

### CR-110 — Client POS totals omit cess `(POS-005)`
- **Module:** POS → tax / tender
- **Location:** `posStatus.ts:117–123` (`computePosLineTax`)
- **Type:** Bug
- **Severity:** High
- **What's wrong:** `calculateLineTax` called without `cessRate`; UI/tender understates.
- **Trigger / repro:** Cess SKU; compare POS total vs preview/complete.
- **Consequence:** Till short or false tenderTooLow.
- **Code evidence:** cess used for inclusive extraction only.
- **Suggested fix direction:** Pass `cessRate`; prefer server gate total in UI.
- **Test to add:** `pos_cess_line_total_matches_preview`
- **Twin check:** y
- **Cross-ref:** **new** (amplifies CR-007)

### CR-111 — Tender UI shows client totals; gate uses server only at click `(POS-006)`
- **Module:** POS → cash tender UX
- **Location:** `PosPage.tsx:391–394`, `:963–996`, `:1582–1646`
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** Labels use client `grandTotal`; preview errors swallowed.
- **Trigger / repro:** Inclusive/cess divergence; Exact then Cash.
- **Consequence:** Till vs books mismatch on fallback.
- **Code evidence:** Display vs `tenderGateTotal` split; empty catch.
- **Suggested fix direction:** Drive display from gateTotal; block pay if preview fails.
- **Test to add:** `pos_tender_ui_uses_server_gate_total`
- **Twin check:** n-a
- **Cross-ref:** confirms-still-broken **CR-007** (PARTIAL; CR-090 payload fixed)

### CR-112 — Cash click guarded only by React `busy` (double-submit race) `(POS-007)`
- **Module:** POS → FE concurrency
- **Location:** `PosPage.tsx:909–916`; contrast flushGuard ref
- **Type:** Race
- **Severity:** Medium
- **What's wrong:** `busy` is async state; key minted after awaits — parallel clicks can mint two key families.
- **Trigger / repro:** Double-click Cash on slow network.
- **Consequence:** Parallel create/complete attempts.
- **Code evidence:** No checkoutGuard ref; key set late.
- **Suggested fix direction:** Ref guard; mint/persist key synchronously at click.
- **Test to add:** `pos_double_click_cash_single_gesture_key`
- **Twin check:** y
- **Cross-ref:** **new**

### CR-113 — Serial/batch error dialog retries with `confirmBlankPos: true` `(POS-008)`
- **Module:** POS → error recovery
- **Location:** `PosPage.tsx:1660–1684`
- **Type:** Missing-validation
- **Severity:** Medium
- **What's wrong:** Serial failure retry auto-confirms blank POS / walk-in.
- **Trigger / repro:** Blank walk-in + serial fail → confirm dialog.
- **Consequence:** Place-of-supply honesty bypassed.
- **Code evidence:** Always passes confirm flags.
- **Suggested fix direction:** Retry only original failure flags.
- **Test to add:** `pos_serial_retry_does_not_auto_confirm_blank_pos`
- **Twin check:** n-a
- **Cross-ref:** **new**

### CR-114 — Offline Outbox “Sync now” flushes POS without thermal `(POS-009)`
- **Module:** POS → offline sync
- **Location:** `OfflineOutboxPage.tsx:83–111` vs `PosPage.tsx:874–887`
- **Type:** Broken-feature | Silent-failure
- **Severity:** Medium
- **What's wrong:** Outbox flush has no thermal print path.
- **Trigger / repro:** Sync offline POS from `/offline` UI.
- **Consequence:** Paid sales without counter slip.
- **Code evidence:** No `downloadInvoiceThermalPdf` in outbox sync.
- **Suggested fix direction:** Shared flush+print helper.
- **Test to add:** `offline_outbox_pos_flush_prints_thermal`
- **Twin check:** n-a
- **Cross-ref:** confirms-still-broken **CR-006** residual

### CR-115 — `ENABLE_POS` is UI sugar; money APIs ungated `(POS-010)`
- **Module:** POS → feature flags
- **Location:** `PosPage.tsx`; `feature_flags.py`; contrast manufacturing permissions
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** Flag hides nav only; RETAIL complete+receipt stay live.
- **Trigger / repro:** `ENABLE_POS=false`; API still completes retail+receipt.
- **Consequence:** False sense of disable.
- **Code evidence:** Comment admits UI sugar.
- **Suggested fix direction:** Document as UI-only (product-accepted CR-008) or gate checkout.
- **Test to add:** product-decision test
- **Twin check:** n
- **Cross-ref:** confirms-still-broken **CR-008** (product-accepted)

### CR-116 — Cash tendered / change never posted `(POS-011)`
- **Module:** POS → cash handling · **Severity:** Low · **Type:** Improvement
- **Location:** `PosPage.tsx` changeDue local; receipt = invoice total
- **Cross-ref:** confirms-still-broken **CR-011** (deferred)
- **Suggested fix / test:** Optional till session fields when product wants

### CR-117 — Stock chips 60s stale; no re-check on add `(POS-012)`
- **Module:** POS · **Severity:** Low · **Type:** Improvement
- **Location:** `PosPage.tsx:259–263`
- **Cross-ref:** confirms-still-broken **CR-013** PARTIAL
- **Note:** Server BLOCK still protects integrity

### CR-118 — Multi-flush thermal warn only last failure `(POS-013)`
- **Module:** POS · **Severity:** Low · **Type:** Silent-failure
- **Location:** `PosPage.tsx:874–887`
- **Cross-ref:** confirms-still-broken **CR-092** PARTIAL

### CR-119 — CR-001 remint fixed same-session; residual via CR-106/108 `(POS-014)`
- **Module:** POS → idempotency · **Severity:** Medium · **Type:** Data-integrity
- **What's wrong:** Same-session resume OK; reload then new cart sale can double-complete while orphan unpaid exists.
- **Suggested fix direction:** Fix CR-106/108; block new sale while pending settlement.
- **Cross-ref:** residual of **CR-001** (FIXED in-session)

---

### CR-120 — SO can convert to invoice **and** delivery challan (double stock / double AR) `(SALES-001)`
- **Module:** Sales → Orders / DC / Invoice
- **Location:** `backend/sales/notes_services.py` `convert_sales_order_to_challan` ~614–637; `complete_challan` ~770–788
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** Invoice convert checks `converted_invoice` / live challan; challan convert does **not** check `converted_invoice_id`. Completing both can double SALE/AR.
- **Trigger / repro:** Confirm SO → Convert to invoice → Convert to challan → complete both.
- **Consequence:** Double stock out, double AR. **Release-blocking.**
- **Code evidence:** Missing guard on challan convert/complete vs invoice convert.
- **Suggested fix direction:** Reject challan path when SO already invoiced; reject second invoice from DC if SO linked elsewhere.
- **Test to add:** `test_so_invoice_then_challan_blocked`
- **Twin check:** check PO fork if any
- **Cross-ref:** **new**

### CR-121 — Recurring error advances `next_run_at` and skips period `(SALES-002)`
- **Module:** Sales → Recurring
- **Location:** `backend/sales/recurring.py` ~174–187
- **Type:** Silent-failure
- **Severity:** High
- **What's wrong:** Lock path fixed (CR-015); exception path still advances without run row → period never retried.
- **Trigger / repro:** Bad template product → beat → fix → next month only.
- **Consequence:** Silent missed billing.
- **Code evidence:** `except Exception` advances schedule.
- **Suggested fix direction:** Do not advance on error; retry same period_key.
- **Test to add:** Fail once → fix → same period_key draft.
- **Twin check:** n
- **Cross-ref:** **CR-015** residual

### CR-122 — Draft SO editable after convert-to-invoice `(SALES-003)`
- **Module:** Sales → Orders · **Severity:** Medium · **Type:** Missing-validation
- **Location:** `phase1_serializers.py` SO update; convert leaves DRAFT
- **What's wrong / consequence:** Source SO diverges from linked draft invoice.
- **Suggested fix / test:** Block edit when `converted_invoice_id` set; PATCH after convert → 400
- **Cross-ref:** **new**

### CR-123 — SO reservation does not track amended invoice qty `(SALES-004)`
- **Module:** Sales · **Severity:** Medium · **Type:** Race
- **Location:** confirm reserves SO qty; complete releases SO qty; draft invoice amend free
- **What's wrong:** Increase invoice qty leaves unprotected stock.
- **Test:** Reservation reflects invoice qty after amend
- **Cross-ref:** **CR-020** residual

### CR-124 — Auto sales-return CN silent-confirms paid / price-override `(SALES-005)`
- **Module:** Sales → Returns · **Severity:** Medium · **Type:** Data-integrity
- **Location:** `return_service.py` ~282–284
- **What's wrong:** Auto-CN hard-codes confirms; paid invoice return without unallocate.
- **Cross-ref:** **CR-017** / **CR-096** residual
- **Twin check:** y

### CR-125 — No partial convert (all-or-nothing chain) `(SALES-006)`
- **Module:** Sales · **Severity:** Medium · **Type:** Broken-feature
- **Cross-ref:** confirms-still-broken **CR-022** (product-accepted known limitation)

### CR-126 — Delivery challan complete lacks idempotency wrap `(SALES-007)`
- **Module:** Sales → DC · **Severity:** Medium
- **Location:** `phase1_views.py` ~324–327; not in `MONEY_IDEMPOTENCY_SCOPES`
- **What's wrong:** Stock-posting complete without wrap; retry → hard error not replay.
- **Cross-ref:** **new** (CR-030 pattern twin)
- **Twin check:** y (PUR-006)

### CR-127 — CN `select_for_update` omits `company_id` `(SALES-008)`
- **Module:** Sales → CN · **Severity:** Low · **Type:** Cross-tenant defense-in-depth
- **Location:** `notes_services.py` complete_credit_note vs DN
- **Cross-ref:** **CR-093** left CN behind · **Twin:** CR-133

### CR-128 — Dead stock-delta branch in `set_items` `(SALES-009)`
- **Module:** Sales · **Severity:** Low · **Type:** Improvement
- **Cross-ref:** **CR-024** follow-through

---

### CR-129 — Purchase CN/DN complete missing Sales twin integrity gates `(PUR-001)`
- **Module:** Purchase → notes
- **Location:** `purchases/notes_services.py:193–252`, `:321–390` vs `sales/notes_services.py`
- **Type:** Missing-validation | Sales/Purchase-inconsistency | Data-integrity
- **Severity:** High
- **What's wrong:** Only monetary headroom — no source status, date, source_item qty caps, paid/price confirms, return-reason FK.
- **Trigger / repro:** CN against DRAFT bill; or over-qty with grand_total ≤ headroom; CN on paid bill without confirm.
- **Consequence:** AP/ITC against non-posted bills; over-credit; stock-less return CN.
- **Suggested fix direction:** Port Sales gates 1:1 + FE confirms.
- **Test to add:** draft invoice / source qty / paid confirm / return-reason FK
- **Twin check:** y
- **Cross-ref:** **new** (twins CR-017/018/026/096)

### CR-130 — Purchase CN/DN allow supplier ≠ bill supplier `(PUR-002)`
- **Module:** Purchase → notes API
- **Location:** `phase1_serializers.py` CN/DN (no validate); contrast Return/Sales
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** No supplier==invoice.supplier check.
- **Trigger / repro:** CN supplier=A, invoice=B’s bill.
- **Consequence:** AP relief on wrong party; GSTR/ledgers diverge.
- **Suggested fix direction:** Same validate as Sales/Return.
- **Test to add:** `test_purchase_cn_rejects_supplier_invoice_mismatch`
- **Twin check:** y
- **Cross-ref:** **new**

### CR-131 — Return unit_name / base-qty headroom unsafe `(PUR-003)`
- **Module:** Purchase → returns
- **Location:** serializers omit unit_name; headroom `Sum(quantity)` vs stock base qty
- **Type:** Data-integrity
- **Severity:** High (alt-unit) / Medium otherwise
- **What's wrong:** Migration snapshots unit_name but API/headroom still document-qty.
- **Trigger / repro:** Bill BOX; return as PCS.
- **Consequence:** Over/under stock; wrong auto CN.
- **Cross-ref:** confirms-still-broken **CR-045**
- **Test to add:** alternate-unit headroom base qty

### CR-132 — Purchase DN cannot carry additional_charges `(PUR-004)`
- **Module:** Purchase → DN · **Severity:** Medium · **Type:** Broken-feature
- **Cross-ref:** confirms-still-broken **CR-038** PARTIAL

### CR-133 — Purchase CN locks invoice without `company_id` `(PUR-005)`
- **Module:** Purchase · **Severity:** Medium · **Type:** Cross-tenant defense-in-depth
- **Location:** `notes_services.py:207` vs DN
- **Cross-ref:** **new** · Twin CR-127

### CR-134 — PO convert has no idempotency scope `(PUR-006)`
- **Module:** Purchase → PO · **Severity:** Medium
- **Location:** `phase1_views.py:189–194`; not in MONEY scopes
- **Cross-ref:** **new** · Twin CR-126

### CR-135 — Nested batch / note product PKs not company-scoped at serializer `(PUR-007)`
- **Module:** Purchase · **Severity:** Medium · **Type:** Cross-tenant defense-in-depth
- **Cross-ref:** **CR-047** class residual

### CR-136 — Supplier payment bank_account FK unscoped `(PUR-008)`
- **Module:** Payments · **Severity:** Low
- **Cross-ref:** confirms-still-broken **CR-047** PARTIAL

### CR-137 — Bill-import confirm_non_gst has no FE wiring `(PUR-009)`
- **Module:** Purchase → import UI · **Severity:** Medium · **Type:** Broken-feature
- **Cross-ref:** confirms-still-broken **CR-041** PARTIAL

---

### CR-138 — Balance vs sum(movements): no runtime reconciliation `(STK-007)`
- **Module:** Stock · **Severity:** Medium · **Type:** Data-integrity
- **Location:** Report flags drift; Current Stock UI still StockBalance cache
- **Cross-ref:** confirms-still-broken **CR-054**; theme CR-062/102

### CR-139 — Transfers: no in-transit; DRAFT no reserve `(STK-008)`
- **Module:** Stock · **Severity:** Medium
- **Cross-ref:** confirms-still-broken **CR-055** (product-accepted doc)

### CR-140 — Stock-count KEEP_SERVER / conflict copy `(STK-009)`
- **Module:** Stock · **Severity:** Medium
- **Cross-ref:** confirms-still-broken **CR-056**; see CR-143

### CR-141 — FIFO verify not automated `(STK-014)`
- **Module:** Stock · **Severity:** Medium
- **Cross-ref:** confirms-still-broken **CR-059**

### CR-142 — Manual serial return resolves wrong / empty SALE move `(STK-015)`
- **Module:** Stock → Serial / FIFO
- **Location:** `inventory/views.py` `_sale_movement_for_serial` ~412–421
- **Type:** Data-integrity | Bug
- **Severity:** High
- **What's wrong:** First SalesItem containing serial wins even without SALE moves (draft shadows); multi-line SKU maps wrong peel.
- **Trigger / repro:** Complete sale SN; newer draft lists SN; manual return. Or two lines same SKU different costs.
- **Consequence:** FIFO understatement / wrong unit cost.
- **Suggested fix direction:** Prefer COMPLETED invoices with SALE moves; map by document line.
- **Test to add:** Draft-shadow + multi-line serial return
- **Twin check:** n-a
- **Cross-ref:** confirms-still-broken **CR-099**

### CR-143 — Offline stock-count flush cannot resolve 409 conflicts `(STK-016)`
- **Module:** Stock → Offline
- **Location:** `StockCountPage.tsx`; `useStockOffline.ts`; outbox flush
- **Type:** Broken-feature
- **Severity:** High
- **What's wrong:** Offline queue empty resolveConflicts; 409 fails with no conflict modal on auto-flush.
- **Trigger / repro:** Offline count → intervening sale → flush.
- **Consequence:** Counts stuck forever.
- **Suggested fix direction:** Surface conflict modal before retry.
- **Test to add:** Offline flush 409 → resolve → success
- **Cross-ref:** **new** (amplifies CR-056)

### CR-144 — Purchase price amend mutates StockMovement.unit_cost outside stamp_cost `(STK-017)`
- **Module:** Stock → Movements / purchase
- **Location:** `purchases/services.py` `restamp_fifo_layers_for_price_amend` ~470; contrast `models.py` `stamp_cost`
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** Raw QuerySet `.update(unit_cost=...)` bypasses append-only save guard / stamp_cost.
- **Trigger / repro:** H9 price-only amend on FIFO purchase with unpeeled layers.
- **Consequence:** Audit/append-only contract broken.
- **Suggested fix direction:** Use `stamp_cost` or compensating movement.
- **Test to add:** Assert restamp uses stamp_cost
- **Twin check:** y (Purchase)
- **Cross-ref:** **new** (CR-053 class)

---

### CR-145 — Opening-balance invoices inflate AR/AP aging and dashboard KPIs `(RPT-001)`
- **Module:** Reporting → Dashboard / aging
- **Location:** `reporting/services.py` receivables/payables aging vs turnover `is_opening_balance=False`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** CR-065 fixed MTD turnover; aging (and AR/AP cards) still include openings. GSTR excludes openings.
- **Trigger / repro:** Unpaid opening SI → receivables rises, sales KPI unchanged.
- **Consequence:** AR/AP disagree with GSTR and turnover KPIs.
- **Suggested fix direction:** Filter openings from both aging paths.
- **Test to add:** `test_rpt001_opening_balance_excluded_from_ar_ap_aging_and_kpis`
- **Twin check:** y
- **Cross-ref:** **CR-065** residual; amplifies CR-060/101

### CR-146 — Party ledgers still GL-when-books while dashboard is document aging `(RPT-002)`
- **Module:** Reporting / Ledgers
- **Location:** `ledgers/services.py` `_use_gl_outstanding` vs `reporting/services.py` dashboard
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** Dashboard documents-only; party ledgers switch to GL when books on.
- **Trigger / repro:** Books on + drift/advances; compare Dashboard vs Customer Ledger.
- **Consequence:** Operators cannot reconcile.
- **Suggested fix direction:** Same outstanding basis everywhere, or hard label + health gate.
- **Test to add:** dashboard AR == sum customer ledger when books on
- **Twin check:** y
- **Cross-ref:** **CR-060/101** residual; **CR-082/105** theme · Twin ACC-004

### CR-147 — Inventory reserved/available from StockBalance cache `(RPT-003)`
- **Module:** Reporting · **Severity:** Medium
- **Cross-ref:** confirms-still-broken **CR-102**

### CR-148 — Inventory report UI drops drift flags `(RPT-004)`
- **Module:** Reporting FE · **Severity:** Medium · **Type:** Silent-failure
- **Location:** `InventoryReportPage.tsx`
- **Cross-ref:** CR-062/102 UX gap

### CR-149 — `assert_report_date_span` no-ops unless both dates set `(RPT-005)`
- **Module:** Reporting → exports
- **Location:** `reporting/services.py:82–91`
- **Type:** Bug
- **Severity:** High
- **What's wrong:** One-sided `date_from` bypasses 366-day cap.
- **Trigger / repro:** Sales-register export with only old `date_from`.
- **Consequence:** Multi-year materialization / timeout.
- **Suggested fix direction:** Require both bounds or default date_to=today + enforce span.
- **Test to add:** `test_rpt005_date_from_only_rejects_or_caps_span`
- **Twin check:** y
- **Cross-ref:** **CR-074** residual

### CR-150 — Product/customer sales skip date-span assert `(RPT-006)`
- **Module:** Reporting · **Severity:** Medium · **Cross-ref:** CR-074 family

### CR-151 — Inventory value uses RunningCost/FIFO cache `(RPT-007)`
- **Module:** Reporting · **Severity:** Medium · **Cross-ref:** CR-062 value half

### CR-152 — Dashboard low_stock_count uses StockBalance `(RPT-008)`
- **Module:** Reporting · **Severity:** Medium · **Cross-ref:** CR-062 family

### CR-153 — Dashboard omits payables_aging buckets `(RPT-009)`
- **Module:** Reporting · **Severity:** Low · **Cross-ref:** CR-101 UX

### CR-154 — No stock ledger / stock aging report `(RPT-010)`
- **Module:** Reporting · **Severity:** Medium · **Type:** Broken-feature (checklist gap)

### CR-155 — CSV/XLSX/GSTR exports fully materialize in memory `(RPT-011)`
- **Module:** Reporting · **Severity:** Medium · **Type:** Improvement · **Cross-ref:** CR-074 residual

### CR-156 — GST soft-close vs Complete TOCTOU when period row missing `(RPT-012)` / `(ACC-002)`
- **Module:** Reporting / Accounting → `gst_periods`
- **Location:** `gst_periods.py:39–52`, `:123–136`; `JournalViewSet.post` not outer-atomic
- **Type:** Race
- **Severity:** High
- **What's wrong:** Assert only locks **existing** GstReturnPeriod; if none, concurrent soft_close can SOFT_CLOSE after assert. Manual JE post races similarly.
- **Trigger / repro:** First soft-close of month racing Complete (Postgres).
- **Consequence:** Money posts into soft-closed GST month.
- **Suggested fix direction:** get_or_create + select_for_update in assert; wrap manual post atomic.
- **Test to add:** Concurrent soft_close + complete (Postgres)
- **Twin check:** n-a (AccountingPeriod already locks)
- **Cross-ref:** confirms-still-broken **CR-104** (PARTIAL)

---

### CR-157 — CR-105 “fix” makes AR/AP control false-alarm when advances exist `(ACC-001)`
- **Module:** Accounting → books health / period & FY close
- **Location:** `accounting/services.py:1970–1995`, `1838–1849`; `reports.py:389–394`
- **Type:** Data-integrity | Bug
- **Severity:** Critical
- **What's wrong:** `ar = net("1200")` but `expected_ar = tagged(1200)+tagged(2300)`. Advances inflate expected → `AR_CONTROL_MISMATCH` **blocks** close. Control must stay 1200↔tagged-1200; netting belongs in docs↔GL.
- **Trigger / repro:** SI ₹1000 + unallocated receipt ₹400 → health unhealthy; period close raises.
- **Consequence:** Honest books with advances cannot close.
- **Suggested fix direction:** Split control check vs netted party GL compare.
- **Test to add:** Advance present → control healthy; docs-GL uses netted GL
- **Twin check:** n-a
- **Cross-ref:** confirms-still-broken **CR-105** (broken fix); **CR-082**

### CR-158 — Empty POSTED JE still “done” outside backfill `(ACC-003)`
- **Module:** Accounting → health / FY close
- **Location:** `services.py:1928–1932`; `reports.py:360–387`
- **Type:** Data-integrity | Silent-failure
- **Severity:** High
- **What's wrong:** Backfill requires lines; health/FY treat any JE by source_id as done — empty POSTED hides missing posting; empty FY_CLOSE skips real close.
- **Trigger / repro:** Empty POSTED SI JE; empty FY_CLOSE JE.
- **Consequence:** Invisible missing postings; wrong FY idempotency.
- **Suggested fix direction:** Same lines-required predicate as backfill.
- **Test to add:** Empty POSTED → health alerts; empty FY_CLOSE does not skip
- **Cross-ref:** confirms-still-broken **CR-103** (PARTIAL — backfill fixed)

### CR-159 — Dual ledger can still silently diverge for ops `(ACC-004)`
- **Module:** Accounting / Ledgers
- **Location:** `ledgers/services.py`; `accounting/services.py` docs↔GL warnings
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** DOCS_GL mismatches are warnings only; close ignores them; credit limit takes max(GL,docs).
- **Trigger / repro:** Untagged manual 1200 or partial backfill → close still succeeds.
- **Consequence:** Ops/credit on diverged truths.
- **Suggested fix direction:** Block close when drift exceeds tolerance.
- **Test to add:** Large drift blocks close
- **Cross-ref:** confirms-still-broken **CR-082**; theme CR-060 · Twin CR-146

### CR-160 — Purchase residual ≤ bound still absorbed to 5110 `(ACC-005)`
- **Module:** Accounting → purchase tax GL · **Severity:** Medium
- **Cross-ref:** confirms-still-broken **CR-085** PARTIAL · Twin Sales hard-stop
- **Note:** `test_b1_034_*` still expects residual book — failed in this suite run

### CR-161 — Manual journals cannot party-tag AR/AP lines `(ACC-006)`
- **Module:** Accounting → voucher · **Severity:** Medium
- **Location:** `serializers.py:80–91`
- **Cross-ref:** **new** (amplifies CR-082)

### CR-162 — Feature flag dual-key UI vs API `(ACC-007)`
- **Module:** Accounting · **Severity:** Low
- **Cross-ref:** confirms-still-broken **CR-089**

---

## Top 10 must-fix-before-launch

Ordered by severity × how core the flow is:

1. **CR-120** — SO→invoice **and** →challan double stock/AR (Critical, everyday sales chain)
2. **CR-144** — Purchase price amend raw-updates `StockMovement.unit_cost` (Critical, append-only invariant)
3. **CR-157** — AR/AP control health broken with advances → cannot close periods (Critical, books)
4. **CR-106 / CR-108** — POS reload cannot finish cash/UPI settlement (High, counter money)
5. **CR-129 / CR-130** — Purchase notes missing Sales gates + supplier mismatch (High, AP/ITC)
6. **CR-142** — Manual serial return wrong SALE move / FIFO (High, serial SKUs)
7. **CR-145** — Openings inflate AR/AP KPIs (High, dashboard honesty)
8. **CR-156** — GST soft-close TOCTOU when period row missing (High, period integrity)
9. **CR-121** — Recurring error skips billing periods (High, recurring revenue)
10. **CR-149** — One-sided date_from bypasses export span cap (High, DoS/ops) · **CR-143** offline count 409 stuck (High, godown) — tie; pick by tenant profile

Also stabilize pytest: **25 failures** (GSTR openings/notes, SO reservation expectations vs CR-020 hold-until-complete, CN confirms, B1-034, cash book, closed period, CSV span) — several are **tests lagging remediations**, not only new bugs.

---

## Cross-cutting themes

1. **Sales ↔ Purchase twin drift** — Notes complete gates, supplier match, CN company_id lock, idempotency on convert/complete, additional_charges on DN (CR-127/129/130/132/133/126/134).
2. **Dual truth: documents vs GL vs StockBalance cache** — Dashboard docs vs ledger GL (CR-146/159); AR control vs advances (CR-157); reserved/on_hand/value caches (CR-138/147/151/152).
3. **Half-closed remediations** — CR-091 storage without resume UX (CR-106); CR-105 “fix” worse (CR-157); CR-103 backfill-only (CR-158); CR-104 soft_close lock without assert create (CR-156); CR-045 migration without API/headroom (CR-131).
4. **Client multi-step money without durable resume** — POS multi-HTTP (CR-107) + reload/UPI gaps (CR-106/108) + double-click (CR-112).
5. **Idempotency scope hygiene** — Challan complete / PO convert missing from `MONEY_IDEMPOTENCY_SCOPES` (CR-126/134).
6. **Offline conflict UX incomplete** — Stock count 409 (CR-143); Outbox thermal (CR-114).

---

## Cross-reference pass

Sources: prior [`FUNCTIONAL_CODE_REVIEW_FINDINGS.md`](./FUNCTIONAL_CODE_REVIEW_FINDINGS.md), [`FIX_PLAN_FUNCTIONAL_2026-09-06.md`](./FIX_PLAN_FUNCTIONAL_2026-09-06.md), [`bugs/INDEX.md`](../../bugs/INDEX.md), [`MASTER_ISSUE_REGISTER.md`](./MASTER_ISSUE_REGISTER.md), this pass’s module agents.

### Highest-value: prior “Resolved/FIXED” still wrong or broken by the fix

| Prior | This pass | Verdict |
|---|---|---|
| **CR-105** | **CR-157** | **Broken fix** — advances folded into control expected; blocks close |
| **CR-091** | **CR-106** | **Partial** — storage yes, resume UX no |
| **CR-104** | **CR-156** | **Partial** — soft_close locks existing row; assert incomplete |
| **CR-103** | **CR-158** | **Partial** — backfill fixed; health/FY still empty-JE blind |
| **CR-099** | **CR-142** | **Still broken** (expanded draft-shadow / multi-line) |
| **CR-045** | **CR-131** | **Still broken** |
| **CR-082** | **CR-159** + **CR-146** | **Still open** (warn-only dual ledger) |
| **CR-002** | **CR-107** | **Still open** (product Phase 2) |
| **CR-015** error path | **CR-121** | **Residual** |
| **CR-065** aging | **CR-145** | **Residual** (turnover fixed; aging not) |
| **CR-074** | **CR-149** | **Residual** (one-sided span) |
| **CR-102** | **CR-147** | **Still open** |
| **CR-017/096** auto-return | **CR-124** | **Residual** |
| **CR-022** | **CR-125** | **Still open** (product-accepted) |
| **CR-008/011** | **CR-115/116** | **Still open** (product-accepted / deferred) |

### Major FIXED confirmations (do not re-open as Critical)

- POS CR-001 same-session remint, CR-003–006 (PosPage path), CR-009–010, CR-012, CR-090 preview payload
- Sales CR-014/016/018–021/023–025/027/093–096; CR-094 DC×SO tenancy
- Purchase CR-030/031/034–037/039/097/098; complete stock+AP atomic
- Stock CR-048–053/057–058; BLOCK concurrency; import void append-only
- Reporting CR-060/061/100/101 dashboard AR/AP = document aging; most CR-062–077
- Accounting CR-078–081/083–084/086–088 posting atomicity / GST in post / reverse / TDS / books_start / backfill company / 2dp

### New this pass (not in CR-001–105)

**CR-108, 109, 110, 112, 113, 119 (residual framing), 120, 122, 126, 129, 130, 133, 134, 143, 144, 154, 161** (+ several Medium residuals re-filed as CR-106+ for tracking).

### bugs/INDEX.md / MASTER overlap (theme, not 1:1 ID map)

- Stock oversell race BUG-222/309 — **mitigated under BLOCK** in current tree (concurrency tests); WARN still allows by policy.
- Opening-balance / AR_CONTROL themes in MASTER (e.g. BB-000398 CDNR openings, AR_CONTROL after Tally) — **CR-145 / CR-157** confirm related honesty holes still matter for pilot.
- Soft-closed period historical BB themes — **CR-156** is the live residual.

### Product-accepted / do-not-block-pilot (still logged)

CR-107≈CR-002 Phase 2 · CR-115≈CR-008 · CR-116≈CR-011 · CR-125≈CR-022 · CR-139≈CR-055 doc-only

---

## Provisional ID → permanent CR map

| Provisional | Permanent |
|---|---|
| POS-001…014 | CR-106…119 |
| SALES-001…009 | CR-120…128 |
| PUR-001…009 | CR-129…137 |
| STK-007…009,014–017 | CR-138…144 |
| RPT-001…011 | CR-145…155 |
| RPT-012 + ACC-002 | **CR-156** (merged) |
| ACC-001 | CR-157 |
| ACC-003…007 | CR-158…162 |
