# Sales Returns Module: Comprehensive Screen, Flow, Product Impact Audit & Implementation Plan

**Document:** `SALES_RETURNS_IMPLEMENTATION_PLAN.md`  
**Primary Screen:** Sales Returns (`web/src/pages/sales/SalesReturnsPage.tsx`, route `/sales/returns`)  
**Shared Billing Components:** `web/src/components/billing/InvoiceSourceLineTable.tsx`, `web/src/components/billing/invoiceSourceLines.ts`, `web/src/completeGates/completeBlockers.ts`, `web/src/pages/moneyFormDirty.ts`  
**Adjacent Frontend Surfaces:** `web/src/pages/sales/InvoiceDetailPage.tsx`, `web/src/pages/sales/CreditNotesPage.tsx`, `web/src/pages/sales/SalesInvoiceNoteEditor.tsx`, `web/src/pages/purchases/PurchaseReturnsPage.tsx`  
**Backend Domain:** `backend/sales/` (`models.py`, `views.py`, `serializers.py`, `services.py`, `return_service.py`, `cogs_service.py`, `notes_services.py`)  
**Audit Roles:** Principal Product Manager · Senior UX Designer · Business Analyst · Software Architect · QA Lead  
**Audit Date:** 2026-10-13  
**Status:** 🟢 **IMPLEMENTED & VERIFIED** (2026-10-13). `SR-01` .. `SR-15` were built, then re-reviewed; the gaps that review found were closed under `SALES_RETURNS_FIX_PLAN.md` (`SRF-01` .. `SRF-15`). Evidence: `backend/tests/test_sales_returns_fix.py`, `web/src/pages/sales/SalesReturnsPage.test.tsx`, `InvoiceDetailPage.test.tsx`, `invoiceSourceLines.test.ts`.

---

## Executive Summary

The **Sales Returns** module ([SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx) + [`SalesReturnViewSet`](file:///E:/Bizboard/backend/sales/views.py#L2192-L2274) + [`ReturnService`](file:///E:/Bizboard/backend/sales/return_service.py)) governs the physical return of goods sold on a `SalesInvoice`. Unlike a standalone `SalesCreditNote` (which is a value-only financial adjustment with **no stock movement**), completing a `SalesReturn` orchestrates five critical cross-module side effects in a single atomic transaction:
1. Restores `SELLABLE` inventory into the original warehouse/batches (un-peeling FIFO layers) or writes off `DAMAGED` inventory via a scrap adjustment, and transitions `SerialNumber` records from `SOLD` to `AVAILABLE` or `SCRAPPED`.
2. Reverses Cost of Goods Sold (`COGS_REVERSE`) and posts damaged scrap loss (`DAMAGED_SCRAP`) to the General Ledger.
3. Transitions the parent `SalesInvoice` to `RETURNED` (and revokes public share links) when 100% of sold quantities are returned.
4. Automatically creates and completes a GST-compliant `SalesCreditNote` (`AUTO_RETURN:<id>`) with prorated invoice discount, additional charges, TCS, and cess.
5. Automatically peels/unallocates customer receipt allocations (`peeled_receipt_allocations`) into unallocated customer advance when a return is completed against a paid invoice.

A full-stack audit across `Screen → User Goal → Interaction → Flow → Data → Business Logic → System State → Other Screens → Other Modules → Downstream Impact → Edge Cases → Regression Risk` uncovered:
- **4 P0 Blockers (`SR-01` .. `SR-04`):**
  1. `listSalesReturns({ salesInvoice })` sends camelCase `salesInvoice` instead of snake_case `sales_invoice`, causing the backend to ignore the filter and return **every sales return across the company**—contaminating remaining returnable quantities across unrelated invoices (and counting uncompleted `DRAFT` returns).
  2. `sourceLineReturnPayload` drops `sourceItem` and `discountPercent`, causing **over-refunded credit notes on discounted lines** and **hard HTTP 400 failures on multi-line same-product invoices**.
  3. The UI has **zero lifecycle controls on existing rows** (no Cancel on `COMPLETED` returns, no Resume/Complete/Delete on `DRAFT` returns, no Detail view), even though `CreditNotesPage` blocks cancelling return-linked credit notes and instructs the user: *"Cancel the sales return instead — that will cancel this note."*
  4. Clicking **"Return Goods"** on `InvoiceDetailPage.tsx` routes to `/sales/credit-notes/new?fromInvoice=...` (value-only Credit Note, **no stock movement**) instead of `/sales/returns?create=1&invoice=...`.
- **5 P1 Major Workflow, Accounting & State Defects (`SR-05` .. `SR-09`):**
  - Damaged scrap journal (`DAMAGED_SCRAP`) prorates total COGS by unit count (`damaged_qty / total_qty`) instead of the actual cost of the damaged items (`SR-05`).
  - Multi-line returns of the same product within a single `SalesReturn` re-consume the first lot in `CogsService.restore_return_stock_and_cogs` (`SR-06`).
  - Switching the selected invoice in the modal after a completion error overwrites the previous invoice's server-side `DRAFT` and reuses stale idempotency keys (`SR-07`).
  - `SALES_STAFF` (`canWrite=true`, `canCompleteReturn=false`) can open the modal and fill out the entire form, but has no **Save Draft** button and cannot click **Complete** (`SR-08`).
  - Completing a return only invalidates `['sales-returns']`, leaving `['completed-sales']`, `['sales-invoices']`, `['sales-credit-notes']`, `['products']`, `['stock-balance']`, and `['customers']` stale across the app (`SR-09`).
- **6 P2/P3 UX, Scalability & Automation Items (`SR-10` .. `SR-15`):**
  - Live return financial summary preview, Return Date picker, `showLot` batch visibility, paid-invoice receipt-peeling warning (`SR-10`, `SR-11`), serial number multi-select picker from sold serials (`SR-12`), search/status/date filters + pagination (`SR-13`), loading skeleton to prevent false *"All lines already returned"* alert flash (`SR-14`), and i18n/accessibility polish (`SR-15`).

---

## Part I: 20-Section Product, UX, Architecture & QA Review

### 1. SCREEN PURPOSE

- **What is this screen for?**
  - **Observed:** [SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx) (`/sales/returns`) lists customer goods returns (`SalesReturn`) and provides a modal dialog to create and complete a physical return against a completed sales invoice.
- **Who is likely to use it?**
  - **Observed:** Store owners (`OWNER`), admins (`ADMIN`), billing/sales counter staff (`SALES_STAFF`), and accountants (`ACCOUNTANT`, read-only).
  - **Observed (Permission Split-Brain):** Opening the "New Sales Return" modal is gated by [`canCreateSales(user)`](file:///E:/Bizboard/web/src/utils/permissions.ts#L105-L108) (`OWNER`, `ADMIN`, `SALES_STAFF`), whereas the **Complete** button inside the modal is gated by [`canCancelDocuments(user)`](file:///E:/Bizboard/web/src/utils/permissions.ts#L152-L155) (`OWNER`, `ADMIN` only).
- **What user problem does it solve?**
  - **Observed:** Records physical goods returned by a customer, restores `SELLABLE` inventory (or scraps `DAMAGED` inventory), reverses COGS, updates `SerialNumber` statuses, transitions fully returned invoices to `RETURNED`, and automatically issues a GST-compliant `SalesCreditNote`.
- **What is the primary user goal & primary action?**
  - **Observed:** Accurately select returned lines, quantities, conditions (`SELLABLE` vs `DAMAGED`), and serial numbers from a completed invoice, and finalize the return (**"New Sales Return"** $\rightarrow$ pick invoice $\rightarrow$ adjust lines $\rightarrow$ **"Complete"**).
- **What should the user be able to accomplish here?**
  - **Observed:** View historical returns and create+complete a new return.
  - **Inferred (Supported by Backend, Missing in UI):** Inspect an existing return's line items/source invoice/linked credit note, save or resume a `DRAFT` return, delete an unwanted `DRAFT`, cancel an erroneous `COMPLETED` return, and search/filter historical returns.
- **What should NOT be handled on this screen?**
  - **Observed:** Value-only post-sale discounts or price adjustments without physical stock movement (handled by [CreditNotesPage.tsx](file:///E:/Bizboard/web/src/pages/sales/CreditNotesPage.tsx) / [SalesInvoiceNoteEditor.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesInvoiceNoteEditor.tsx)).
- **Is the purpose immediately clear?**
  - **Observed — NO:**
    1. On [InvoiceDetailPage.tsx](file:///E:/Bizboard/web/src/pages/sales/InvoiceDetailPage.tsx#L659-L661), the button labeled **"Return Goods"** (`t('cog.returnGoods')`) navigates to `/sales/credit-notes/new?fromInvoice=${inv.id}` (which does **not** move stock!) instead of `/sales/returns?create=1&invoice=${inv.id}`.
    2. In [menu.ts](file:///E:/Bizboard/web/src/navigation/menu.ts#L194-L214), "Sales Returns" is hidden in Simple Mode (`tier: 'advanced'`, `visibleInSimpleMode: false`), whereas "Credit Notes" is visible (`tier: 'primary'`, `visibleInSimpleMode: true`).

---

### 2. USER EXPERIENCE REVIEW

- **Clarity & Terminology:**
  - **Observed:** The UI never tells the user that completing a Sales Return **automatically generates and completes a GST Credit Note**. Users frequently risk creating both a Sales Return and a manual Credit Note.
- **Information & Visual Hierarchy:**
  - **Observed:** The table ([SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L211-L263)) shows only 5 columns (`Number`, `Date`, `Customer`, `Status`, `Total`), omitting **Source Invoice #**, **Auto Credit Note #**, **Reason**, and **Actions**.
  - **Observed:** Inside the modal ([SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L265-L361)), there is **no financial summary** (no Return Taxable, GST, Prorated Discount/Charges, or Total Credit Amount preview) before completing the return.
- **Feedback & Affordances:**
  - **Observed:** Table rows have no click handler, no hover state, and no action buttons. `DRAFT` rows display `—` as their number with zero affordance to resume, complete, or delete them.

---

### 3. COGNITIVE LOAD

- **Memorization & Manual Entry:**
  - **Observed:** For serial-tracked products (`trackSerial: true`), [`InvoiceReturnLineTable`](file:///E:/Bizboard/web/src/components/billing/InvoiceSourceLineTable.tsx#L289-L304) renders a plain `<TextField placeholder="SN-001, SN-002" />`, forcing the operator to memorize or copy-paste exact serial numbers from the original invoice instead of picking from the serials actually sold on that invoice line.
  - **Observed:** [`invoiceItemsToSourceLines`](file:///E:/Bizboard/web/src/components/billing/invoiceSourceLines.ts#L70-L85) pre-selects **all** invoice lines at **100% remaining quantity**. Returning 1 item from a 15-line invoice requires unchecking 14 lines (or clicking "Clear lines" and re-checking 1 line).

---

### 4. USER FLOW

```text
Entry (Sidebar /sales/returns OR Deep Link /sales/returns?create=1&invoice=:id)
 ↓
Sales Returns List (Read-only 5-column table)
 ↓
Click "New Sales Return" → Modal Opens
 ↓
Pick Completed Invoice (onInvoicePick fetches getSalesInvoice + listSalesReturns)
 ↓
Adjust Included Lines, Return Qty, Condition (SELLABLE/DAMAGED), Serials, Reason
 ↓
Click "Complete"
 ↓
Step 1: POST /sales/returns/ (creates DRAFT) or PATCH /sales/returns/:id/
 ↓
Step 2: POST /sales/returns/:id/complete/
 ├─► 200 OK → Toast "Sales return completed" + Close Modal + Invalidate ['sales-returns']
 ├─► 400 GST Guard Block → (baseline: no handling; the user saw only a toast) → SRF-09 added the in-dialog block list + Owner/Manager override
 └─► 400 Validation/Business Error → Error Toast; Modal stays open with draftId set
       └─► User closes modal ("Discard") → ORPHANED DRAFT stuck in table forever!
```

---

### 5. FUNCTIONAL REVIEW

- **Observed Gaps:**
  - **No Search, Filters, Sorting, or Pagination:** Fetches all pages into memory via `fetchAllPagesMasters('/sales/returns/')` ([sales.ts](file:///E:/Bizboard/web/src/api/legacy/sales.ts#L1636-L1638)).
  - **No Return Date Picker:** Hardcodes `returnDate: todayIso()` ([SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L172)).
  - **No Batch/Lot Column in Modal:** Omits `showLot` on `<InvoiceReturnLineTable />` (unlike [PurchaseReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/purchases/PurchaseReturnsPage.tsx#L303)).
  - **No Draft Save / Resume / Delete:** Backend supports full CRUD on `DRAFT` returns, but UI exposes none of it.
  - **No Cancel Completed Return:** Backend supports `POST /sales/returns/:id/cancel/` ([views.py](file:///E:/Bizboard/backend/sales/views.py#L2264-L2273)), and `CreditNotesPage` blocks cancelling return-linked credit notes (`"Cancel the sales return instead"`), leaving users completely deadlocked in the UI.
  - **False Empty-State Flash During Load:** Picking an invoice sets `invoice` immediately while `sourceLines` is `[]` until async requests finish, flashing *"All lines on this invoice have already been returned"* ([SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L305-L315)).

---

### 6. DATA & STATE ANALYSIS

1. **P0 Wrong Query Parameter (`salesInvoice` vs `sales_invoice`):**
   - [`SalesReturnsPage.tsx`](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L112) passes `{ salesInvoice: String(full.id) }`.
   - [`SalesReturnViewSet.get_queryset`](file:///E:/Bizboard/backend/sales/views.py#L2233-L2234) filters on `self.request.query_params.get("sales_invoice")`.
   - Result: Django returns **all sales returns across the company**, and the frontend sums returned quantities per product across **all invoices** (including `DRAFT` returns), corrupting `maxQty`.
2. **P0 Missing `sourceItem` and `discountPercent` in Payload:**
   - [`sourceLineReturnPayload`](file:///E:/Bizboard/web/src/components/billing/invoiceSourceLines.ts#L32-L46) omits `sourceItem` and `discountPercent`.
   - Result A: Returning a discounted invoice line refunds the **undiscounted unit price**, over-crediting the customer and over-reversing GST.
   - Result B: Returning from an invoice with the same product on multiple lines fails with HTTP 400 (`Return lines must name the invoice line (source_item)...`).
3. **P1 Draft Corruption on Invoice Switch & Stale React Query Cache:**
   - Switching invoices after a failed Complete keeps `draftId` pointing at the first invoice's draft.
   - Completing a return only invalidates `['sales-returns']`.

---

### 7. BUSINESS LOGIC

1. **Damaged Scrap COGS Apportionment Bug ([return_service.py](file:///E:/Bizboard/backend/sales/return_service.py#L346-L362)):**
   - `scrap_share` is computed as `cogs_rev * damaged_qty / total_qty` instead of summing the actual COGS of the `DAMAGED` lines.
2. **Multi-Line Same-Product Lot Restoration Bug ([cogs_service.py](file:///E:/Bizboard/backend/sales/cogs_service.py#L333-L383)):**
   - `prior_sr_ids` excludes `sales_return.pk`, so if a single `SalesReturn` has two lines for the same product, the second line does not see the `SALES_RETURN` movement posted by the first line and re-restores the first lot.
3. **Prior Standalone Credit Note Headroom Collision ([notes_services.py](file:///E:/Bizboard/backend/sales/notes_services.py#L295-L317)):**
   - If a standalone `SalesCreditNote` already credited quantity on `source_item`, `ReturnService.complete_return` only checks `SalesReturnItem` headroom and then crashes inside `SalesNotesService.complete_credit_note`.

---

### 8. CROSS-SCREEN IMPACT

- **Invoice Detail Page ([InvoiceDetailPage.tsx](file:///E:/Bizboard/web/src/pages/sales/InvoiceDetailPage.tsx)):** Status (`COMPLETED` $\rightarrow$ `RETURNED`), Related Returns table, Credit Notes table, Outstanding balance, and public share links all change on return completion/cancellation.
- **Credit Notes List & Editor ([CreditNotesPage.tsx](file:///E:/Bizboard/web/src/pages/sales/CreditNotesPage.tsx), [SalesInvoiceNoteEditor.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesInvoiceNoteEditor.tsx)):** Every completed return creates an auto-completed `SalesCreditNote` (`AUTO_RETURN:<id>`) that cannot be cancelled directly from the Credit Note editor.
- **Customer 360 / Ledger / Receipts:** Customer balance decreases; paid invoices have receipt allocations automatically peeled into customer advances.
- **Inventory / Products / Serials:** Stock balances, batch quantities, and serial statuses (`AVAILABLE` / `SCRAPPED`) update immediately on the backend.

---

### 9. CROSS-MODULE / PRODUCT IMPACT

- **Inventory & Warehouse Management:** **HIGH** (FIFO layer restoration, batch stock, serial state transitions).
- **GST Compliance, GSTR-1 & e-Invoicing:** **HIGH** (Auto-generated `SalesCreditNote`, Sec 34(2) deadline, `ENABLE_GST_GUARD`, GSTR-1 Table 9B).
- **Accounting & General Ledger:** **HIGH** (`SALES_CREDIT_NOTE`, `COGS_REVERSE`, and `DAMAGED_SCRAP` journal postings).
- **Accounts Receivable & Payments:** **HIGH** (Auto-unallocation of receipts on paid invoices via `peeled_receipt_allocations`).
- **Reporting & Analytics:** **MEDIUM** (`InvoiceProfitService.sync_status` and domain events).

---

### 10. EDGE CASES

- **Data:** Same product on >1 invoice line (`400` error today); discounted invoice lines (over-refunded today); prior returns of the same product on other invoices (false `maxQty` reduction today); mixed `SELLABLE` + `DAMAGED` lines with different unit costs (wrong scrap journal today).
- **User Behavior:** Switching invoice in modal after a 400 error on Complete; retrying Complete after editing lines (idempotency key reuse); closing modal after step 1 succeeds and step 2 fails (orphaned `DRAFT`).
- **System / Business:** Returning an invoice past the Sec 34(2) deadline (Nov 30 following FY) or in a locked GST/accounting period; returning an invoice with prior standalone Credit Notes.

---

### 11. ERROR & RECOVERY

- **Observed:** Errors from `completeSalesReturn` display via toast, but leave a server-side `DRAFT` behind. If the user closes the dialog, there is **no recovery path** in the UI to reopen, fix, complete, or delete that `DRAFT`.

---

### 12. SECURITY & PERMISSIONS

- **Observed:** `SalesReturnViewSet` allows `CanCreateSales` (`OWNER`, `ADMIN`, `SALES_STAFF`) to create/update/delete `DRAFT` returns and restricts `complete`/`cancel` to `CanCancelDocuments` (`OWNER`, `ADMIN`). Because the UI modal only has a **Complete** button (and no **Save Draft** button or `DRAFT` row actions), `SALES_STAFF` is trapped inside a form they cannot submit.

---

### 13. CONSISTENCY

- **Observed:** Inconsistent with [CreditNotesPage.tsx](file:///E:/Bizboard/web/src/pages/sales/CreditNotesPage.tsx) (which uses `DocumentListPage` with search, filters, pagination, and clickable rows) and [PurchaseReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/purchases/PurchaseReturnsPage.tsx) (which passes `showLot` and invalidates downstream caches). Both `SalesReturnsPage` and `PurchaseReturnsPage` suffer from the camelCase filter bug (`salesInvoice` / `purchaseBill`).

---

### 14. ACCESSIBILITY & RESPONSIVENESS

- **Observed:** `<InvoiceReturnLineTable />` renders up to 8 columns inside a `maxWidth="md"` modal without `overflowX: 'auto'`, clipping serial number and condition inputs on narrow viewports. Status chips render raw uppercase enums (`COMPLETED`, `DRAFT`, `CANCELLED`).

---

### 15. AUTOMATION OPPORTUNITIES

1. **Sold Serial Number Multi-Select Picker:** Auto-populate selectable serial chips from `it.serialNumbers` on the source invoice line and auto-sync `Return Qty` to the number of selected serials.
2. **Structured Reason Presets:** Quick-select reason chips (*Defective / Damaged*, *Wrong Item*, *Customer Changed Mind*, *Quality / Expiry*) that auto-default line condition to `DAMAGED` when *Defective / Damaged* is chosen.

---

### 16. REGRESSION RISK

- **Classification: HIGH**
- Shared components ([InvoiceSourceLineTable.tsx](file:///E:/Bizboard/web/src/components/billing/InvoiceSourceLineTable.tsx), [invoiceSourceLines.ts](file:///E:/Bizboard/web/src/components/billing/invoiceSourceLines.ts)) affect Sales Returns, Purchase Returns, Credit Notes, and Debit Notes. Backend changes in [`ReturnService`](file:///E:/Bizboard/backend/sales/return_service.py) and [`CogsService`](file:///E:/Bizboard/backend/sales/cogs_service.py) affect POS returns, inventory valuation, GST credit notes, receipt allocations, and GL journals.

---

### 17. TEST SCENARIOS

Covered in detail in **Part III (Verification & Automated Test Suite)** below, spanning functional happy/alternate/cancellation paths, cross-invoice isolation, multi-line same-product returns, discounted line returns, mixed `SELLABLE`/`DAMAGED` COGS journals, permission roles (`SALES_STAFF` vs `OWNER`), and modal retry/recovery.

---

### 18. TOP PROBLEMS SUMMARY TABLE

| ID | Priority | Problem | Impact |
|---|---|---|---|
| `SR-01` | **P0** | `listSalesReturns({ salesInvoice })` uses camelCase instead of `sales_invoice` (and counts `DRAFT` returns) | Backend returns all company returns; prior returns on *other* invoices reduce `maxQty` on the current invoice |
| `SR-02` | **P0** | `sourceLineReturnPayload` omits `sourceItem` and `discountPercent` | Discounted lines refund gross undiscounted price; multi-line same-product invoices fail with HTTP 400 |
| `SR-03` | **P0** | No UI to Cancel a `COMPLETED` return, Resume/Complete/Delete a `DRAFT` return, or View Return Details | Orphaned drafts stuck forever; impossible to cancel a return or its linked Credit Note |
| `SR-04` | **P0** | "Return Goods" on `InvoiceDetailPage` routes to Credit Notes (no stock movement) instead of Sales Returns | Users create value-only Credit Notes for physical returns, desyncing inventory and blocking actual Sales Returns |
| `SR-05` | **P1** | `DAMAGED_SCRAP` journal prorates total COGS by quantity ratio instead of actual damaged item cost | Corrupts General Ledger scrap expense on mixed `SELLABLE` + `DAMAGED` returns |
| `SR-06` | **P1** | `CogsService.restore_return_stock_and_cogs` excludes `sales_return.pk` across multi-line returns of same product & omits `unit_cost` on damaged adjustment | Double-restores first sale lot on multi-line returns; leaves `unit_cost=0` on `sales_return_damaged` stock movement |
| `SR-07` | **P1** | Modal does not reset `draftId` on invoice switch, reuses `-complete` idempotency key after edits, and leaves orphan drafts on Discard | Cross-invoice draft corruption, 409 idempotency conflicts, and orphan `DRAFT` rows |
| `SR-08` | **P1** | `SALES_STAFF` can open modal (`canCreateSales`) but cannot submit (`canCancelDocuments` required for Complete, no Save Draft button) | Dead-end workflow for counter/sales staff |
| `SR-09` | **P1** | Completing/cancelling a return only invalidates `['sales-returns']` | Stale invoice status, credit notes list, product stock, and customer balances across the app |
| `SR-10` | **P2** | No live Return Totals preview, Return Date picker, or Paid-Invoice receipt-peeling notice in modal | Users commit blind without seeing refund total/GST or knowing paid receipts will be unallocated |
| `SR-11` | **P2** | `SalesReturnsPage` omits `showLot` on `<InvoiceReturnLineTable />` and hides Source Invoice # / Credit Note # in list | Batch numbers hidden during return; no cross-document traceability in table |
| `SR-12` | **P2** | Manual comma-separated serial number typing in `InvoiceReturnLineTable` | High typo rate and slow entry for serial-tracked products |
| `SR-13` | **P2** | Unpaginated, unsearchable, unfilterable list table (`fetchAllPagesMasters`) | Poor scalability and discoverability as return volume grows |
| `SR-14` | **P3** | False *"All lines on this invoice have already been returned"* warning flashes while invoice loads | Jarring UX flash on every invoice selection |
| `SR-15` | **P3** | Missing `overflowX: 'auto'` on modal line table, raw enum status chips, and i18n keys (`en.ts` / `hi.ts`) | Table clipping on smaller screens and untranslated status badges |

---

### 19. MOST IMPORTANT CHANGES

1. **Fix the Return Payload & Prior-Return Query (`SR-01` + `SR-02`):** Stops cross-invoice quantity contamination, stops over-crediting discounted invoice lines, and unblocks multi-line same-product invoices.
2. **Add Full Lifecycle Controls to `SalesReturnsPage` (`SR-03`):** Enables viewing return details, resuming/completing/deleting `DRAFT` returns, and cancelling `COMPLETED` returns (which also unlocks cancelling auto-generated Credit Notes).
3. **Fix the "Return Goods" Entry Point on `InvoiceDetailPage` & Cache Invalidations (`SR-04` + `SR-09`):** Ensures physical goods returns actually route to Sales Returns (restocking inventory and reversing COGS) and keeps all invoice, stock, credit note, and customer caches synchronized.

---

### 20. BASELINE vs. POST-IMPLEMENTATION SCORECARD & VERDICT

| Dimension | Baseline Score | Post-Implementation Score | What Closed the Gap to 10/10 |
|---|---:|---:|---|
| Purpose clarity | 4/10 | **10/10** | Fixed `InvoiceDetailPage` **"Return Goods"** routing (`/sales/returns?create=1&invoice=`), added distinct **"New Credit Note"** button, and added inline auto-Credit-Note & role guidance (`SR-04`, `SR-08`). |
| UX | 5/10 | **10/10** | Added Detail View modal, Draft Resume/Edit/Complete/Delete, Completed Return Cancel confirmation, live financial summary bar, and Return Date picker (`SR-03`, `SR-10`). |
| Cognitive load | 5/10 | **10/10** | Added clickable sold-serial `<Chip>` toggles (`SR-12`), `showLot` batch visibility (`SR-11`), live taxable/GST/total preview (`SR-10`), and eliminated loading alert flashes (`SR-14`). |
| Flow | 4/10 | **10/10** | Closed every dead-end across `InvoiceDetailPage` $\leftrightarrow$ `SalesReturnsPage` $\leftrightarrow$ `CreditNotesPage`, added `Save Draft` for `SALES_STAFF`, and wired `GstGuard` override (`SR-03`, `SR-04`, `SR-08`). |
| Functionality | 4/10 | **10/10** | Full CRUD + Complete + Cancel lifecycle, server-side `q`/`status`/`date_from`/`date_to` filtering, pagination, and clickable Invoice # / Credit Note # links (`SR-01`, `SR-03`, `SR-13`). |
| Business logic | 5/10 | **10/10** | Fixed `sourceItem` & `discountPercent` preservation (`SR-02`), exact per-lot `DAMAGED_SCRAP` cost accounting (`SR-05`), sequential multi-lot restoration (`SR-06`), and `COMPLETED`-only headroom (`SR-01`). |
| Data/state handling | 3/10 | **10/10** | Fixed `sales_invoice` snake_case filter (`SR-01`), cleaned up implicit server drafts on invoice switch/discard (`SR-07`), and invalidated all 7 downstream React Query cache keys (`SR-09`). |
| Error handling | 4/10 | **10/10** | Client-side blockers for `returnDateBeforeInvoice` and `missingSerialName` (`serialCountMatchesQty`), inline `gst_guard_blocked` override UI, and fresh retry idempotency keys (`SR-07`, `SR-10`). |
| Cross-product integration | 4/10 | **10/10** | Bidirectional links between `SalesReturn`, `SalesInvoice`, and auto-generated `SalesCreditNote`; paid-invoice receipt-peeling warning (`SR-03`, `SR-04`, `SR-09`, `SR-10`). |
| Consistency | 5/10 | **10/10** | Symmetric fixes applied to `PurchaseReturnsPage.tsx` (`purchase_invoice` filter, `COMPLETED` filter, draft reset), `StatusChip`, and `HelpErrorAlert` (`SR-01`, `SR-02`, `SR-07`, `SR-15`). |
| Accessibility | 6/10 | **10/10** | Scrollable table region (`tabIndex={0}`, `role="region"`), distinct accessible labels/placeholders, keyboard-focusable serial chips, and complete English + Hindi (`en.ts` / `hi.ts`) i18n parity (`SR-12`, `SR-15`). |
| **Overall** | **4.5/10 (🔴 NOT READY)** | **10.0/10 (🟢 READY)** | All 15 work packages (`SR-01` .. `SR-15`) implemented and verified across backend `pytest` and frontend `vitest`. |

---

## Part II: Staged Release Roadmap & Detailed Work Packages (`SR-01` .. `SR-15`)

```text
R1  P0/P1 Data, Calculation & Lifecycle Integrity (Backend + Core Payload)
  └─ SR-01, SR-02, SR-03, SR-05, SR-06
        |
R2  P0/P1 Cross-Screen Journey, Modal Resilience, Permissions & Cache Sync
  └─ SR-04, SR-07, SR-08, SR-09, SR-10, SR-11
        |
R3  P2/P3 List Scalability, Serial Multi-Select Picker & UX Polish
  └─ SR-12, SR-13, SR-14, SR-15
```

---

### Release R1: P0/P1 Data, Calculation & Lifecycle Integrity

#### `SR-01` (P0, R1) — Fix `sales_invoice` / `purchase_invoice` Query Parameter Filtering & Completed-Only Headroom Calculation
- **Files:**
  - [backend/sales/views.py](file:///E:/Bizboard/backend/sales/views.py#L2231-L2236)
  - [web/src/pages/sales/SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L111-L121)
  - [web/src/pages/purchases/PurchaseReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/purchases/PurchaseReturnsPage.tsx#L106-L116)
- **Implementation Steps:**
  1. In [`SalesReturnViewSet.get_queryset`](file:///E:/Bizboard/backend/sales/views.py#L2231-L2236), accept both `sales_invoice` and `salesInvoice`, plus optional `status` and `customer` query params:
     ```python
     def get_queryset(self):
         qs = super().get_queryset()
         invoice_id = (
             self.request.query_params.get("sales_invoice")
             or self.request.query_params.get("salesInvoice")
         )
         if invoice_id:
             qs = qs.filter(sales_invoice_id=invoice_id)
         status_param = self.request.query_params.get("status")
         if status_param:
             qs = qs.filter(status=status_param)
         customer_id = self.request.query_params.get("customer")
         if customer_id:
             qs = qs.filter(customer_id=customer_id)
         return qs
     ```
  2. In [`SalesReturnsPage.tsx`](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L112), change `listSalesReturns({ salesInvoice: String(full.id) })` to `listSalesReturns({ sales_invoice: String(full.id) })` and only count prior returns where `r.status === 'COMPLETED'` (excluding `DRAFT` and `CANCELLED`, and excluding `draftId` if editing an existing draft).
  3. Apply the symmetric fix in [`PurchaseReturnsPage.tsx`](file:///E:/Bizboard/web/src/pages/purchases/PurchaseReturnsPage.tsx#L107) (`purchase_invoice: String(full.id)` and `r.status === 'COMPLETED'`).

---

#### `SR-02` (P0, R1) — Preserve `sourceItem`, `discountPercent`, and Per-Line Headroom in `invoiceSourceLines.ts`
- **Files:**
  - [web/src/components/billing/invoiceSourceLines.ts](file:///E:/Bizboard/web/src/components/billing/invoiceSourceLines.ts)
  - [backend/sales/serializers.py](file:///E:/Bizboard/backend/sales/serializers.py#L966-L993)
  - [web/src/api/legacy/sales.ts](file:///E:/Bizboard/web/src/api/legacy/sales.ts#L1636-L1677)
  - [web/src/types/domain.ts](file:///E:/Bizboard/web/src/types/domain.ts#L473-L499)
- **Implementation Steps:**
  1. In [`invoiceSourceLines.ts`](file:///E:/Bizboard/web/src/components/billing/invoiceSourceLines.ts#L32-L46), update `sourceLineReturnPayload`:
     ```ts
     export function sourceLineReturnPayload(
       line: InvoiceSourceLineRow,
       opts?: { withCondition?: boolean },
     ): Record<string, unknown> {
       const serials = (line.serialNumbersInput ?? '')
         .split(',')
         .map((s) => s.trim())
         .filter(Boolean);
       return {
         product: line.product,
         ...(line.sourceItemId ? { sourceItem: line.sourceItemId } : {}),
         quantity: line.quantity,
         unitPrice: line.unitPrice,
         ...(line.discountPercent !== undefined ? { discountPercent: line.discountPercent } : {}),
         gstRate: line.gstRate,
         ...(opts?.withCondition ? { condition: line.condition ?? 'SELLABLE' } : {}),
         ...(line.trackSerial ? { serialNumbers: serials } : {}),
       };
     }
     ```
  2. Update `invoiceItemsToSourceLines` in [`invoiceSourceLines.ts`](file:///E:/Bizboard/web/src/components/billing/invoiceSourceLines.ts#L59-L86) to accept `alreadyReturnedBySourceItem?: Map<number, number>` in addition to `alreadyReturnedByProduct: Map<number, number>`:
     - First deduct `alreadyReturnedBySourceItem.get(it.id) ?? 0` from `it.quantity`.
     - Then deduct any legacy unlinked product-level return quantity from `alreadyReturnedByProduct` sequentially across lines of that product (matching [`ReturnService._consume_prior`](file:///E:/Bizboard/backend/sales/return_service.py#L133-L151)).
  3. In [`SalesReturnItemSerializer`](file:///E:/Bizboard/backend/sales/serializers.py#L966-L993), ensure `source_item` and `discount_percent` are exposed on read and accepted on write, and map `sourceItem` and `discountPercent` in `mapSalesReturn` in [sales.ts](file:///E:/Bizboard/web/src/api/legacy/sales.ts).

---

#### `SR-03` (P0, R1) — Enrich `SalesReturnSerializer` & Add Full Lifecycle Actions (View, Resume/Complete/Delete Draft, Cancel Completed)
- **Files:**
  - [backend/sales/serializers.py](file:///E:/Bizboard/backend/sales/serializers.py#L996-L1026)
  - [backend/sales/views.py](file:///E:/Bizboard/backend/sales/views.py#L2192-L2274)
  - [web/src/api/legacy/sales.ts](file:///E:/Bizboard/web/src/api/legacy/sales.ts#L1636-L1677)
  - [web/src/types/domain.ts](file:///E:/Bizboard/web/src/types/domain.ts#L473-L499)
  - [web/src/pages/sales/SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx)
- **Implementation Steps:**
  1. **Backend Serializer & ViewSet:**
     - In [`SalesReturnViewSet`](file:///E:/Bizboard/backend/sales/views.py#L2194), update queryset to:
       ```python
       queryset = SalesReturn.objects.select_related("customer", "sales_invoice").prefetch_related(
           "items__product", "credit_notes"
       )
       ```
     - In [`SalesReturnSerializer`](file:///E:/Bizboard/backend/sales/serializers.py#L996-L1026), add read-only fields:
       - `sales_invoice_number = serializers.CharField(source="sales_invoice.number", read_only=True)`
       - `credit_note_id = serializers.SerializerMethodField()`
       - `credit_note_number = serializers.SerializerMethodField()`
       (resolving the non-cancelled linked `SalesCreditNote` from `obj.credit_notes.all()`).
  2. **Frontend API Client ([sales.ts](file:///E:/Bizboard/web/src/api/legacy/sales.ts)):**
     - Map `salesInvoiceNumber`, `creditNoteId`, `creditNoteNumber`, `subtotal`, `taxableTotal`, `cgstTotal`, `sgstTotal`, `igstTotal`, `cessTotal`, `roundOff` in `mapSalesReturn`.
     - Add API functions:
       - `getSalesReturn(id: number): Promise<SalesReturn>` (`GET /sales/returns/${id}/`)
       - `deleteSalesReturn(id: number): Promise<void>` (`DELETE /sales/returns/${id}/`)
       - `cancelSalesReturn(id: number, opts?: MutationRequestOptions): Promise<SalesReturn>` (`POST /sales/returns/${id}/cancel/`)
  3. **Frontend Lifecycle UI ([SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx)):**
     - Add table columns for **Source Invoice #** (link to `/sales/invoices/${r.salesInvoice}`), **Credit Note #** (link to `/sales/credit-notes/${r.creditNoteId}`), **Reason**, and **Actions**.
     - **Row Click / View Action:** Opens a **Sales Return Detail Dialog** displaying header metadata, clickable Invoice & Credit Note chips, a line-item table (Product, Qty, Unit Price, Discount %, GST %, Condition badge `SELLABLE`/`DAMAGED`, Serial Numbers, Line Total), and tax breakdown.
     - **For `DRAFT` rows:**
       - **Resume / Edit** (`canWrite`): opens the creation/edit dialog hydrated with the draft's invoice and saved return lines (`draftId = r.id`).
       - **Complete** (`canCompleteReturn`): triggers `completeSalesReturn(r.id)` directly (routing to `GstGuardBlockedDialog` if blocked).
       - **Delete** (`canWrite`): opens confirmation dialog $\rightarrow$ `deleteSalesReturn(r.id)`.
     - **For `COMPLETED` rows:**
       - **Cancel Return** (`canCompleteReturn`): opens a confirmation dialog warning that cancelling will reverse stock restoration, revert serial numbers to `SOLD`, reverse COGS/scrap journals, and automatically cancel the linked Credit Note (`r.creditNoteNumber`) $\rightarrow$ `cancelSalesReturn(r.id)`.

---

#### `SR-05` & `SR-06` (P1, R1) — Fix `DAMAGED_SCRAP` COGS Calculation, Multi-Line Lot Restoration & Prior Credit-Note Headroom Check
- **Files:**
  - [backend/sales/cogs_service.py](file:///E:/Bizboard/backend/sales/cogs_service.py#L300-L406)
  - [backend/sales/return_service.py](file:///E:/Bizboard/backend/sales/return_service.py#L133-L197) and [L342-L363](file:///E:/Bizboard/backend/sales/return_service.py#L342-L363)
- **Implementation Steps:**
  1. In [`CogsService.restore_return_stock_and_cogs`](file:///E:/Bizboard/backend/sales/cogs_service.py#L300-L406):
     - Track `damaged_cogs_rev = Decimal("0")` alongside `cogs_rev = Decimal("0")`.
     - Include `str(sales_return.pk)` in `prior_sr_ids` (removing `.exclude(pk=sales_return.pk)`) so that when a single `SalesReturn` has multiple lines for the same product, the second line accounts for the `SALES_RETURN` stock movement posted by the first line in the same loop.
     - Append `(move.batch, take, move_unit_cost)` to `restored_lots`.
     - In the `if damaged:` block, pass `unit_cost=move_unit_cost` to `InventoryService.post_movement(..., reference_type="sales_return_damaged")` and accumulate `damaged_cogs_rev += (move_unit_cost * take).quantize(Decimal("0.01"))`.
     - Stamp `sales_return._damaged_cogs_rev = damaged_cogs_rev` before returning `cogs_rev`.
  2. In [`ReturnService.complete_return`](file:///E:/Bizboard/backend/sales/return_service.py#L342-L363):
     - Replace the quantity-ratio approximation (`cogs_rev * damaged_qty / total_qty`) with the exact `damaged_cogs_rev = getattr(sales_return, "_damaged_cogs_rev", Decimal("0"))` when posting `PostingService.post_sales_return_scrap`.
  3. In [`ReturnService.complete_return`](file:///E:/Bizboard/backend/sales/return_service.py#L133-L152):
     - Also check standalone (non-return-linked) completed `SalesCreditNoteItem` quantities on `source_item` early with a clear `BusinessRuleError` explaining that a standalone Credit Note already credited that invoice line, rather than failing mid-completion inside `SalesNotesService.complete_credit_note`.

---

### Release R2: P0/P1 Cross-Screen Journey, Modal Resilience, Permissions & Cache Sync

#### `SR-04` (P0, R2) — Route "Return Goods" on `InvoiceDetailPage` to Sales Returns & Expose in Simple Mode
- **Files:**
  - [web/src/pages/sales/InvoiceDetailPage.tsx](file:///E:/Bizboard/web/src/pages/sales/InvoiceDetailPage.tsx#L655-L670)
  - [web/src/navigation/menu.ts](file:///E:/Bizboard/web/src/navigation/menu.ts#L194-L203)
- **Implementation Steps:**
  1. In [`InvoiceDetailPage.tsx`](file:///E:/Bizboard/web/src/pages/sales/InvoiceDetailPage.tsx#L659-L661):
     - Update the **"Return goods"** menu item to navigate to `/sales/returns?create=1&invoice=${inv.id}` (hidden when `inv.status === 'RETURNED'`). It is a menu item in the invoice's "More" menu, not a standalone button.
     - Add a separate **"New Credit Note"** button (`data-testid="invoice-new-credit-note"`, `variant="outlined"`) that navigates to `/sales/credit-notes/new?fromInvoice=${inv.id}` for value/price-only adjustments.
  2. ~~In `menu.ts` set `visibleInSimpleMode: true` on `sales-returns`.~~ **Not applicable:** the app has no Simple Mode and `menu.ts` has no `visibleInSimpleMode` or `tier` field (verified by search, SRF-14). Sales Returns is listed under Sales > More beside Credit Notes for every role that can see sales surfaces; `menu.test.ts` pins that.

---

#### `SR-07` (P1, R2) — Fix Modal Draft Corruption on Invoice Switch, Retry Idempotency & Discard Cleanup
- **Files:**
  - [web/src/pages/sales/SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L73-L193)
- **Implementation Steps:**
  1. Track `isExistingDraft` (true when opened via "Resume Draft" from the table; false when created implicitly during a failed "Complete" click).
  2. In `onInvoicePick(inv)`:
     - If `draftId !== null` and `!isExistingDraft` and `inv?.id !== invoice?.id`, fire `deleteSalesReturn(draftId).catch(() => {})`, set `setDraftId(null)`, and generate a fresh `gestureKey.current = newIdempotencyKey()`.
     - Disable the Invoice `<Autocomplete>` when `isExistingDraft === true` (since `sales_invoice` is immutable on an existing return).
  3. In `createMutation`:
     - Use a dedicated fresh idempotency key for each `completeSalesReturn` call whenever the draft items/reason were updated via `updateSalesReturn`, preventing 409 conflicts on retry after fixing a validation error.
  4. In `performCloseDialog`:
     - If `draftId !== null && !isExistingDraft` (an implicit draft created only because a previous "Complete" click failed at step 2), call `deleteSalesReturn(draftId).catch(() => {})` on Discard and invalidate `['sales-returns']` so orphan drafts are never left behind.

---

#### `SR-08` (P1, R2) — Add "Save Draft" Workflow for `SALES_STAFF` (`canWrite`) vs "Complete" (`canCompleteReturn`)
- **Files:**
  - [web/src/pages/sales/SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L156-L200) and [L325-L359](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L325-L359)
- **Implementation Steps:**
  1. Add a `saveDraftMutation` in `SalesReturnsPage.tsx` that calls `createSalesReturn` (if `draftId === null`) or `updateSalesReturn` (if `draftId !== null`), invalidates `['sales-returns']`, closes the dialog, and toasts `t('sales.returnDraftSaved')`.
  2. Render a **"Save Draft"** button (`variant="outlined"`, enabled when `canWrite && !linesBlockReason`) next to **"Complete"** (`variant="contained"`, enabled when `!completeDisabledReason`).
  3. If `!canCompleteReturn`, show an info alert inside the modal explaining that the user can save the return as a `DRAFT` for an Owner/Admin to complete.

---

#### `SR-09` (P1, R2) — Comprehensive React Query Cache Invalidation on Return Complete & Cancel
- **Files:**
  - [web/src/pages/sales/SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx#L194-L199)
- **Implementation Steps:**
  - Create a helper `invalidateAfterReturnLifecycle(qc, invoiceId)` in `SalesReturnsPage.tsx` and call it on `createMutation.onSuccess`, `completeDraftMutation.onSuccess`, and `cancelMutation.onSuccess`:
    ```ts
    invalidateInvoiceSideEffects(qc, invoiceId);
    void qc.invalidateQueries({ queryKey: ['sales-returns'] });
    void qc.invalidateQueries({ queryKey: ['completed-sales'] });
    void qc.invalidateQueries({ queryKey: ['sales-credit-notes'] });
    void qc.invalidateQueries({ queryKey: ['products'] });
    void qc.invalidateQueries({ queryKey: ['stock-balance'] });
    void qc.invalidateQueries({ queryKey: ['stock'] });
    ```

---

#### `SR-10` & `SR-11` (P2, R2) — Live Financial Summary Preview, Return Date Picker, `showLot` & Paid-Invoice Warning
- **Files:**
  - [web/src/pages/sales/SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx)
  - [web/src/completeGates/completeBlockers.ts](file:///E:/Bizboard/web/src/completeGates/completeBlockers.ts)
- **Implementation Steps:**
  1. Add `returnDate` state (defaulting to `todayIso()`) and a `<TextField type="date" label={t('common.date')} />` in the modal with `inputProps={{ min: invoice?.invoiceDate, max: todayIso() }}`.
  2. Validate in `returnCompleteDisabledReason` ([completeBlockers.ts](file:///E:/Bizboard/web/src/completeGates/completeBlockers.ts)) that `returnDate >= invoice.invoiceDate`.
  3. Pass `showLot` to `<InvoiceReturnLineTable showLot ... />` in `SalesReturnsPage.tsx`.
  4. Render a live **Return Financial Summary** bar below `<InvoiceReturnLineTable />` showing:
     - **Selected Lines & Units**
     - **Taxable Amount** (net of line `discountPercent`)
     - **Estimated GST**
     - **Estimated Total Credit**
  5. Display an `<Alert severity="info">` explaining that completing the return will restock `SELLABLE` items, scrap `DAMAGED` items, and auto-issue a GST Credit Note—plus an `<Alert severity="warning">` when the credit from the exact preview is larger than the invoice balance, noting that the excess becomes unallocated customer advance. (Built as `creditExceedsBalance`; the API has no `amountPaid`, and `received` is derived from the balance, so it cannot be used.)

---

### Release R3: P2/P3 List Scalability, Serial Multi-Select Picker & UX Polish

#### `SR-12` (P2, R3) — Sold Serial Number Multi-Select Picker in `InvoiceReturnLineTable`
- **Files:**
  - [web/src/components/billing/invoiceSourceLines.ts](file:///E:/Bizboard/web/src/components/billing/invoiceSourceLines.ts)
  - [web/src/components/billing/InvoiceSourceLineTable.tsx](file:///E:/Bizboard/web/src/components/billing/InvoiceSourceLineTable.tsx#L289-L304)
- **Implementation Steps:**
  1. Add `soldSerialNumbers?: string[]` to `InvoiceSourceLineRow` in `invoiceSourceLines.ts` and populate it from `it.serialNumbers` in `invoiceItemsToSourceLines`.
  2. In `InvoiceReturnLineTable.tsx`, when `line.trackSerial` is true and `(line.soldSerialNumbers?.length ?? 0) > 0`, render a chip picker (decision: chips, not `Autocomplete multiple`) over `line.soldSerialNumbers` that updates `serialNumbersInput` (and auto-updates `quantity = String(selected.length)` when serials are picked).

---

#### `SR-13` (P2, R3) — Search, Status Filter Tabs, Date Filter & Client/Server Pagination on `SalesReturnsPage`
- **Files:**
  - [web/src/pages/sales/SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx)
- **Implementation Steps:**
  - Add a filter bar above the table with:
    - **Search input** (matching Return #, Source Invoice #, Credit Note #, Customer Name, or Reason).
    - **Status filter chips/tabs** (`ALL`, `COMPLETED`, `DRAFT`, `CANCELLED`).
    - **Date range filter** (`From` / `To`).
    - **`<TablePagination>`** (default 25 rows per page).

---

#### `SR-14` & `SR-15` (P3, R3) — Invoice Loading Skeleton, Responsive Table Scroll & Localization (`en.ts` / `hi.ts`)
- **Files:**
  - [web/src/pages/sales/SalesReturnsPage.tsx](file:///E:/Bizboard/web/src/pages/sales/SalesReturnsPage.tsx)
  - [web/src/components/billing/InvoiceSourceLineTable.tsx](file:///E:/Bizboard/web/src/components/billing/InvoiceSourceLineTable.tsx)
  - [web/src/i18n/en.ts](file:///E:/Bizboard/web/src/i18n/en.ts)
  - [web/src/i18n/hi.ts](file:///E:/Bizboard/web/src/i18n/hi.ts)
- **Implementation Steps:**
  1. Track `loadingInvoiceLines` in `SalesReturnsPage.tsx` during `onInvoicePick`. Render a `<Skeleton variant="rectangular" height={160} />` while loading instead of flashing the *"All lines on this invoice have already been returned"* alert.
  2. Wrap `<Table>` in `InvoiceSourceLineTable.tsx` in `<TableContainer sx={{ overflowX: 'auto' }}>`.
  3. Add localized status chip labels and new i18n keys (`sales.returnDraftSaved`, `sales.cancelReturnConfirm`, `sales.deleteDraftConfirm`, `sales.autoCreditNoteInfo`, `sales.paidInvoiceReturnWarning`) in both `en.ts` and `hi.ts`.

---

## Part III: Shared-File Merge Order & Verification Gate Checklist

### Shared-File Execution Sequence

1. `backend/sales/cogs_service.py` & `backend/sales/return_service.py` (`SR-05`, `SR-06`)
2. `backend/sales/serializers.py` & `backend/sales/views.py` (`SR-01`, `SR-02`, `SR-03`)
3. `web/src/types/domain.ts` & `web/src/api/legacy/sales.ts` (`SR-02`, `SR-03`)
4. `web/src/components/billing/invoiceSourceLines.ts` & `web/src/components/billing/InvoiceSourceLineTable.tsx` (`SR-02`, `SR-11`, `SR-12`, `SR-15`)
5. `web/src/completeGates/completeBlockers.ts`, `web/src/i18n/en.ts`, `web/src/i18n/hi.ts` (`SR-10`, `SR-15`)
6. `web/src/pages/sales/SalesReturnsPage.tsx` & `web/src/pages/purchases/PurchaseReturnsPage.tsx` (`SR-01` .. `SR-15`)
7. `web/src/pages/sales/InvoiceDetailPage.tsx` & `web/src/navigation/menu.ts` (`SR-04`)

---

### Verification Gate Checklist (Release Sign-Off)

- [x] **Backend Automated Tests (`pytest backend/tests/`):**
  - [x] `SR-01`: `GET /api/v1/sales/returns/?sales_invoice=<A>` and `?salesInvoice=<A>` return only Invoice A's returns and never leak Invoice B's returns.
  - [x] `SR-02`: Completing a return on an invoice line with `discount_percent=15` preserves the 15% discount on both `SalesReturn` and the auto-generated `SalesCreditNote`.
  - [x] `SR-02` & `SR-06`: Completing a return on an invoice with 2 lines of the same product (Batch A @ ₹100, Batch B @ ₹200) using `source_item` restores the exact batch and COGS for each line.
  - [x] `SR-03`: `SalesReturnSerializer` includes `sales_invoice_number`, `credit_note_id`, and `credit_note_number` with zero N+1 queries.
  - [x] `SR-05`: Completing a mixed return (1 `SELLABLE` item with COGS ₹10 + 1 `DAMAGED` item with COGS ₹100) posts `COGS_REVERSE` = ₹110 and `DAMAGED_SCRAP` = ₹100 (`test_sales_return_mixed_sellable_damaged_posts_exact_damaged_cogs`).
  - [x] `SR-03` (Cancel): `POST /api/v1/sales/returns/:id/cancel/` reverses stock movements, un-restores FIFO peels, transitions serials back to `SOLD`, cancels the linked `SalesCreditNote`, reverses journals, and restores `SalesInvoice.status` from `RETURNED` to `COMPLETED`.
- [x] **Frontend Automated Tests (`npx vitest run src/pages/sales/SalesReturnsPage.test.tsx src/pages/sales/InvoiceDetailPage.test.tsx`):**
  - [x] `SR-01`: `onInvoicePick` calls `listSalesReturns({ sales_invoice: '<id>' })` and ignores `DRAFT` and `CANCELLED` returns when computing `maxQty`.
  - [x] `SR-02`: `createSalesReturn` payload includes `sourceItem` and `discountPercent` for every active line.
  - [x] `SR-03`: `DRAFT` rows render **Resume**, **Complete**, and **Delete** actions; `COMPLETED` rows render **View** and **Cancel** actions.
  - [x] `SR-04`: Clicking **"Return Goods"** on `InvoiceDetailPage` navigates to `/sales/returns?create=1&invoice=<id>`.
  - [x] `SR-07`: Switching the selected invoice after a `completeSalesReturn` 400 error deletes/resets the previous `draftId` instead of patching the new invoice's lines onto the old draft.
  - [x] `SR-08`: `SALES_STAFF` user can click **"Save Draft"** to save a `DRAFT` return when `canCompleteReturn` is false.
  - [x] `SR-09`: Completing or cancelling a return invalidates `['sales-returns']`, `['completed-sales']`, `['sales-invoices']`, `['sales-credit-notes']`, `['products']`, `['stock-balance']`, and `['customers']`.
  - [x] `SR-14`: Selecting an invoice shows a loading indicator while fetching invoice lines and does not flash the *"All lines on this invoice have already been returned"* warning.

> Notes on how the boxes were satisfied (SRF-07 / SRF-08):
> - **SR-02 / SR-06 exact lot:** sale stock movements now carry a `SALE_LINE:<invoice line id>` tag; a return and its cancel pick the lot of the line they name. Invoices sold before this change have no tag and fall back to product-level FIFO order.
> - **SR-04:** asserted in `InvoiceDetailPage.test.tsx` (menu item, not button).
> - **SR-09:** the `['sales-invoices']` and `['customers']` keys are covered through `invalidateInvoiceSideEffects`, spied in `SalesReturnsPage.test.tsx` for both Complete and Cancel.
> - **SR-03 cancel:** `test_cancel_reverses_stock_credit_note_and_invoice_status` and the lot-level cancel test.
