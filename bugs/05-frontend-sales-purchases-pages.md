# Area 05 — Frontend Sales & Purchases Pages

**Scope:** `CustomersPage.tsx`, `InvoiceDetailPage.tsx`, `NewInvoicePage.tsx`, `QuotationsPage.tsx`, `ReceiptsPage.tsx`, `SalesHistoryPage.tsx`, `SalesReturnsPage.tsx`, `NewPurchasePage.tsx`, `PurchaseBillUploadPage.tsx`, `PurchaseDetailPage.tsx`, `PurchaseHistoryPage.tsx`, `PurchaseReturnsPage.tsx`, `SupplierPaymentsPage.tsx`, `SuppliersPage.tsx`, plus `utils/tax.ts`, `utils/money.ts`, `api/resources.ts`.

**Key structural finding:** `NewInvoicePage.tsx` and `NewPurchasePage.tsx` are near-duplicate ~1700-line files (identical helpers, layout). This is the direct root cause of several divergence bugs below (BUG-502/504/508/517): a fix applied to one twin was never ported to the other.

---

### BUG-500 — "Save & New" silently discards the success message it just set
- **Severity:** Critical
- **Category:** Bug
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:600-604` (bug), `482-504` (`resetForm`)
- **Description:** In the `complete_new` success branch, `setMessage(...)` is called then `resetForm()` runs synchronously, which itself calls `setMessage(null)` and `setError(null)`. React batches these into one update — only the final value survives, so the "Invoice saved" banner never renders, and a genuine payment-allocation failure warning gets wiped too.
- **Impact:** Cashiers using "Save & New" for rapid counter billing never see confirmation, and can believe an invoice is fully paid when the payment actually failed to record.
- **Remediation:** Don't call `setMessage(null)`/`setError(null)` inside `resetForm()`; reorder so message/error are set last.
- **Suggested test:** Complete an invoice via "Save & New" with a receipt-allocation failure mocked; assert the error banner is visible after reset.
- **Status vs prior report:** NEW.

### BUG-501 — Same message/warning-wipe bug in Purchases
- **Severity:** Critical
- **Category:** Bug
- **Location:** `web/src/pages/purchases/NewPurchasePage.tsx:589-593, 471-493`
- **Description:** Identical pattern to BUG-500 on the purchase side.
- **Status vs prior report:** NEW.

### BUG-502 — Purchase number prefix/next-number fully editable and mutates the shared numbering series
- **Severity:** Critical
- **Category:** Gap
- **Location:** `web/src/pages/purchases/NewPurchasePage.tsx:894-916, 530-532`
- **Description:** Unlike Sales (fixed, disabled), the Purchase prefix/number fields are live inputs; saving calls `updatePurchaseNumberSeries({prefix, nextNumber})`, permanently altering the company-wide purchase numbering sequence — not just this document.
- **Impact:** A staff member idly editing this field before saving can permanently reassign the company's next purchase-invoice number, creating gaps/collisions in the GST purchase register.
- **Remediation:** Mirror the Sales fix — read-only/disabled with "Assigned on Complete" helper text; move series editing to a dedicated Settings screen with confirmation if needed.
- **Status vs prior report:** CONFIRMED (UX_REVIEW.md U-05) — present in Purchases even though fixed in Sales.

### BUG-503 — Sales invoice number field verified read-only
- **Severity:** Cosmetic
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:909-929`
- **Description:** Both prefix and number fields are `disabled` with clear helper text.
- **Remediation:** Consider removing the now-dead `seriesDirty`/`updateSalesInvoiceNumberSeries` machinery (see BUG-514).
- **Status vs prior report:** ALREADY-FIXED (UX_REVIEW.md U-05).

### BUG-504 — Purchase invoice discount: "+" label next to "− ₹" adornment, and discount mode selector missing entirely
- **Severity:** High
- **Category:** Bug
- **Location:** `web/src/pages/purchases/NewPurchasePage.tsx:1386-1401`
- **Description:** Row label is `+ ${invoiceDiscount}` while the field's adornment says `- ₹` — contradictory signs on the same control. Unlike Sales, there is no AFTER_TAX/BEFORE_TAX mode selector at all, so purchase discounts are silently always "after tax" with no way to change or even see that.
- **Remediation:** Drop the `+` prefix; add the same mode selector used in `NewInvoicePage.tsx:1400-1408`.
- **Status vs prior report:** CONFIRMED (BUG_REPORT.md BUG-003/024) — present in Purchases, not Sales as originally filed. Same root cause as area 02's BUG-203.

### BUG-505 — Sales discount labeling verified clear
- **Severity:** Cosmetic
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:1396-1421`; `web/src/i18n/en.ts:194-196`
- **Description:** Labels read "Cash discount (after tax)" / "Discount (reduces GST)" with a plain `₹` adornment — no contradiction.
- **Status vs prior report:** ALREADY-FIXED (BUG_REPORT.md BUG-003/024).

### BUG-506 — Completed/finalized invoices and purchases remain fully line-item-editable with no warning
- **Severity:** Critical
- **Category:** Gap
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:802-810, 1088-1163`; `web/src/pages/purchases/NewPurchasePage.tsx:786-796, 1078-1153`
- **Description:** When editing a COMPLETED document, only the customer/supplier "Change" control is restricted — every line's quantity, price, discount, batch, HSN remain live inputs, and Save silently rewrites an already-issued, GST-filed document with no confirmation, audit prompt, or warning banner.
- **Remediation:** Make the line table read-only for COMPLETED documents (require a credit-note/return flow for corrections), or show a persistent warning before saving changes.
- **Status vs prior report:** NEW.

### BUG-507 — Primary "Save" button silently completes a draft while editing
- **Severity:** High
- **Category:** Broken-Flow
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:800-822`; `web/src/pages/purchases/NewPurchasePage.tsx:786-808`
- **Description:** While editing a DRAFT, the primary button is labeled "Save" but its `onClick` computes `mode = 'complete'` for a draft being edited — clicking "Save" finalizes/numbers the invoice. A separate, visually smaller "Save draft" button exists alongside it.
- **Remediation:** Rename the primary action to "Save & Complete" when it will finalize.
- **Status vs prior report:** NEW.

### BUG-508 — Purchases has no place-of-supply gate (asymmetric with Sales)
- **Severity:** High
- **Category:** Gap
- **Location:** `web/src/pages/purchases/NewPurchasePage.tsx:734, 788`
- **Description:** Sales gates `canComplete` on `posKnown` with a warning Alert when place-of-supply is ambiguous; Purchases has no equivalent `posKnown` anywhere in the file.
- **Impact:** A purchase from a supplier with no state/GSTIN on file can be completed with CGST/SGST vs IGST silently assumed intra-state, risking incorrect ITC claims.
- **Remediation:** Port `posKnown` gating from Sales into Purchases.
- **Status vs prior report:** NEW. (Backend-side root cause independently found as area 02's BUG-206/207.)

### BUG-509 — Payment Details section dismissible with no persistence or explanation
- **Severity:** Medium
- **Category:** UI-Optimization
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:951-1004`; `web/src/pages/purchases/NewPurchasePage.tsx:941-994`
- **Description:** An `IconButton` with literal `×` hides the Payment Terms/Due Date block with no tooltip and no persistence (unlike `showBatchCols`, which persists to `localStorage`).
- **Status vs prior report:** CONFIRMED (UX_REVIEW.md U-04).

### BUG-510 — Party autocomplete placeholder misleads rather than hints "search"
- **Severity:** Medium
- **Category:** UI-Optimization
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:887-894`; `web/src/pages/purchases/NewPurchasePage.tsx:872-879`
- **Description:** Placeholder is `"+ Add Party"`, reading as a create-CTA rather than a search hint.
- **Remediation:** `"Search or select customer…"`, keeping "+ Add Party" as the separate link already present.
- **Status vs prior report:** CONFIRMED but INACCURATE in detail (UX_REVIEW.md U-06 claimed a "Walk-in" default that does not exist in code).

### BUG-511 — Line discount percent has no upper bound; >100% silently mismatches displayed vs effective discount
- **Severity:** Medium
- **Category:** Gap
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:1127-1137`; `web/src/pages/purchases/NewPurchasePage.tsx:1117-1127`; `web/src/utils/tax.ts:36-48`
- **Description:** The discount-percent field has `min={0}` but no `max`; `calculateLineTax` clamps the resulting amount to `[0, gross]` but never clamps the displayed percent, so typing `500` shows "500%" while the actual discount is capped at 100%.
- **Remediation:** Clamp `discountPercent` to `[0, 100]` client-side and in `calculateLineTax`.
- **Status vs prior report:** NEW.

### BUG-512 — Per-line "+" icon doesn't add a row; it only focuses the barcode field
- **Severity:** Medium
- **Category:** UI-Optimization
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:1164-1173`; `web/src/pages/purchases/NewPurchasePage.tsx:1154-1163`
- **Description:** Each line's `AddIcon` button just calls `barcodeRef.current?.focus()` — no actual row insertion despite the implied affordance.
- **Status vs prior report:** NEW.

### BUG-513 — No unsaved-changes guard when navigating away from a long invoice/purchase form
- **Severity:** Medium
- **Category:** Gap
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx`; `web/src/pages/purchases/NewPurchasePage.tsx` (whole components)
- **Description:** No `beforeunload` listener or router navigation blocker anywhere in either page — an accidental back-press/refresh silently loses all unsaved line items.
- **Remediation:** Add a `beforeunload` handler and/or router navigation blocker guarded by `lines.length > 0`.
- **Status vs prior report:** NEW.

### BUG-514 — Dead code: `seriesDirty` / `updateSalesInvoiceNumberSeries` unreachable in Sales
- **Severity:** Low
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:260-262, 540-542`
- **Description:** Since the prefix/number fields are permanently disabled (BUG-503), this save-time series-editing path can never fire.
- **Status vs prior report:** NEW.

### BUG-515 — Full-table tax recompute and re-render on every keystroke; no row memoization
- **Severity:** Low (Medium for large invoices)
- **Category:** Performance
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:438-468, 1039-1185`; `web/src/pages/purchases/NewPurchasePage.tsx:433-463, 1029-1175`
- **Description:** `lineTaxes`/`totals` `useMemo`s recompute across the entire `lines` array on every keystroke in any line; no `React.memo` on rows.
- **Impact:** For invoices with 50+ SKUs, typing in one field measurably lags because every other row re-renders.
- **Remediation:** Extract rows into a memoized `LineRow` component keyed by `line.key`.
- **Status vs prior report:** NEW.

### BUG-516 — No sticky/pinned grand total on mobile scroll
- **Severity:** Low
- **Category:** UI-Optimization
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:1009-1010, 1368`; `web/src/pages/purchases/NewPurchasePage.tsx:999-1000, 1358`
- **Description:** Only the table header is `stickyHeader`; the totals summary bar is not sticky. A cashier scanning many items on a phone/tablet must scroll fully down to see the running total.
- **Status vs prior report:** CONFIRMED (UX_REVIEW.md U-11).

### BUG-517 — Purchases edit-hydration effect skips `setLoadedEdit(true)` on the CANCELLED early return
- **Severity:** Low
- **Location:** `web/src/pages/purchases/NewPurchasePage.tsx:328-334`
- **Description:** Sales' equivalent branch correctly calls `setLoadedEdit(true)` before returning early for a non-editable status; Purchases' CANCELLED branch omits it, allowing a repeated `setError` call on unrelated cache invalidations.
- **Status vs prior report:** NEW.

### BUG-518 — ~1700-line duplicated implementation between Sales and Purchases billing pages
- **Severity:** Medium
- **Category:** Feature-Optimization
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx` vs `web/src/pages/purchases/NewPurchasePage.tsx` (entire files)
- **Description:** Shared helpers and most layout are copy-pasted between the two files rather than shared — the direct root cause of the divergence bugs BUG-502/504/508/517.
- **Remediation:** Extract shared pieces into `components/billing/` parameterized by document type.
- **Status vs prior report:** NEW.

### BUG-519 — Share (WhatsApp/Email): no input validation, and a popup-blocked link has no clickable fallback
- **Severity:** High
- **Category:** Bug
- **Location:** `web/src/pages/sales/InvoiceDetailPage.tsx:85-93, 324-352`
- **Description:** `sharePhone`/`shareEmail` are free-text with no format validation. On success, `window.open(res.shareLink, '_blank')` is called (an async popup, commonly blocked); if blocked or no link exists, the message is inert plain text, not a clickable link.
- **Remediation:** Validate phone format before enabling the button; render the share link as a clickable `Link` in addition to attempting `window.open`.
- **Status vs prior report:** CONFIRMED (UX_REVIEW.md U-12), with a worse failure mode than originally described.

### BUG-520 — No confirmation dialog before cancelling/deleting invoices or purchases
- **Severity:** High
- **Category:** Broken-Flow
- **Location:** `web/src/pages/sales/InvoiceDetailPage.tsx:76-83, 187-196`; `web/src/pages/sales/SalesHistoryPage.tsx:96-113, 313-343`; `web/src/pages/purchases/PurchaseDetailPage.tsx:55-63, 134-143`; `web/src/pages/purchases/PurchaseHistoryPage.tsx:106-122, 270-293`
- **Description:** "Cancel" and "Delete" both fire their mutation directly on click — no `Dialog` confirmation anywhere in any of the four files.
- **Impact:** A single mis-click permanently deletes a draft or cancels a completed, potentially already-shared GST document, with no undo.
- **Remediation:** Wrap both actions in a confirmation dialog.
- **Status vs prior report:** NEW.

### BUG-521 — Systemic: customer/supplier/invoice list fetchers silently drop pagination beyond page 1
- **Severity:** Critical
- **Category:** Bug
- **Location:** `web/src/api/resources.ts:56-60` (`asList`), `112-117`, `133-138`, `200-205`
- **Description:** `asList()` extracts only `.results` and discards `.next`/`.count`. `listCustomers`/`listSuppliers`/`listSalesInvoices`/`listPurchases` (used for allocation/return dropdowns) all route through this with no "load more", unlike `listSalesInvoicesPage`/`listPurchasesPage` (History pages only), which correctly use `listPage()`.
- **Impact:** Any shop past the backend's page size (20-100) has entries silently invisible in: the New Invoice/Purchase party autocomplete, Customers/Suppliers tables, Receipts/SupplierPayments allocation pickers, Quotations customer picker, and Returns' original-document pickers. A growing shop simply can't bill or receipt against customers past the first page, with zero error.
- **Remediation:** Make the backend return all rows for reference lookups, or convert every call site to `listPage`/`fetchNextPage`.
- **Status vs prior report:** NEW. (Independently found on the inventory/reports side as area 06's BUG-606–609.)

### BUG-522 — Systemic: raw Axios `error.message` shown instead of parsed backend message
- **Severity:** Medium
- **Category:** Bug
- **Location:** `CustomersPage.tsx:88`, `QuotationsPage.tsx:107`, `ReceiptsPage.tsx:97`, `SalesReturnsPage.tsx:88`, `InvoiceDetailPage.tsx:119`, `PurchaseReturnsPage.tsx:87`, `SupplierPaymentsPage.tsx:90`, `SuppliersPage.tsx:74`, `PurchaseDetailPage.tsx:67`
- **Description:** `getErrorMessage()` correctly extracts backend detail messages, but 9 of the 13 pages pass `query.error.message` directly instead — a generic "Request failed with status code 400" instead of the actionable backend detail. `SalesHistoryPage`/`PurchaseHistoryPage` do it correctly.
- **Remediation:** Replace `query.error.message` with `getErrorMessage(query.error)` in all nine locations.
- **Status vs prior report:** NEW.

### BUG-523 — Quotations limited to exactly one line item
- **Severity:** Critical
- **Category:** Gap
- **Location:** `web/src/pages/sales/QuotationsPage.tsx:43-65, 153-174`
- **Description:** The "New quotation" dialog has a single product/qty state pair and builds `items: [{...}]` with no way to add a second line. A quotation for more than one product is impossible via this UI.
- **Remediation:** Reuse the multi-line item table pattern from `NewInvoicePage.tsx`.
- **Status vs prior report:** NEW.

### BUG-524 — Quotation dialog state not reset after successful creation
- **Severity:** Medium
- **Location:** `web/src/pages/sales/QuotationsPage.tsx:67-73`
- **Description:** `onSuccess` closes the dialog and invalidates the query but never resets `customer`/`product`/`qty` — reopening shows stale prior selections.
- **Status vs prior report:** NEW.

### BUG-525 — "Convert" button has no pending-state guard — double-submit risk
- **Severity:** High
- **Category:** Bug
- **Location:** `web/src/pages/sales/QuotationsPage.tsx:75-93, 136-141`
- **Description:** A single shared `convertMutation` instance is used for every row's Convert button, but no row disables based on `isPending` — rapid double-clicks can convert one quotation twice.
- **Status vs prior report:** NEW.

### BUG-526 — Quotation quantity field allows 0/negative values
- **Severity:** Medium
- **Location:** `web/src/pages/sales/QuotationsPage.tsx:60, 168-173`
- **Description:** `qty` is unbounded `Number(qty)` with only `!product` disabling Save.
- **Status vs prior report:** NEW.

### BUG-527 — Unallocated/advance receipts never labeled "Advance" anywhere
- **Severity:** Medium
- **Category:** Gap
- **Location:** `web/src/pages/sales/ReceiptsPage.tsx:100-127`
- **Description:** The backend already computes `is_advance`/`unallocated` (see area 03's BUG-304), but the receipts table shows no chip/label distinguishing partially-allocated receipts at all.
- **Status vs prior report:** CONFIRMED (UX_REVIEW.md U-08).

### BUG-528 — Receipt/Supplier-payment amount fields accept 0 or negative values
- **Severity:** Medium
- **Location:** `web/src/pages/sales/ReceiptsPage.tsx:140-145, 181`; `web/src/pages/purchases/SupplierPaymentsPage.tsx:133-138, 172`
- **Description:** `amount` is unbound `type="number"`; Save only checks truthiness of the string, so `"-100"` passes and submits `-100`.
- **Status vs prior report:** NEW.

### BUG-529 — Allocation pickers include already fully-paid documents; default allocation ignores existing balance
- **Severity:** Medium
- **Location:** `web/src/pages/sales/ReceiptsPage.tsx:37-40, 153-166`; `web/src/pages/purchases/SupplierPaymentsPage.tsx:37, 74-76, 146-157`
- **Description:** Both allocation pickers filter only by `status === 'COMPLETED'`, not remaining balance, and default the allocation amount to `min(amount, grandTotal)` instead of `min(amount, balance)`.
- **Status vs prior report:** NEW.

### BUG-530 — Supplier payment dialog state not reset after success
- **Severity:** Medium
- **Location:** `web/src/pages/purchases/SupplierPaymentsPage.tsx:66-72`
- **Description:** Unlike `ReceiptsPage`, which resets its fields, `onSuccess` here only closes the dialog and invalidates the query.
- **Status vs prior report:** NEW.

### BUG-531 — Sales/Purchase returns restricted to the first line item only
- **Severity:** Critical
- **Category:** Gap
- **Location:** `web/src/pages/sales/SalesReturnsPage.tsx:48-65, 134-140`; `web/src/pages/purchases/PurchaseReturnsPage.tsx:45-63`
- **Description:** Both hardcode `invoice.items[0]`/`purchase.items[0]` — there is no line-item picker at all. The Sales version even has helper text admitting the limitation ("Applies to the first line item of the invoice").
- **Impact:** For any multi-item invoice/purchase (the common case), there is no way to return anything other than item #1 — a fundamental functional gap on a highest-traffic screen.
- **Remediation:** Replace the single "qty" field with a per-item picker sourced from `invoice.items`/`purchase.items`.
- **Status vs prior report:** NEW.

### BUG-532 — Return quantity not clamped against originally sold/purchased quantity
- **Severity:** High
- **Category:** Gap
- **Location:** `web/src/pages/sales/SalesReturnsPage.tsx:60, 134-140`; `web/src/pages/purchases/PurchaseReturnsPage.tsx:57`
- **Description:** `qty` has no upper bound relative to `item.quantity` — a return greater than what was sold/bought is silently accepted client-side.
- **Status vs prior report:** NEW.

### BUG-533 — No search, filter, or pagination on Customers/Suppliers list pages
- **Severity:** Medium
- **Category:** UI-Optimization
- **Location:** `web/src/pages/sales/CustomersPage.tsx:91-130`; `web/src/pages/purchases/SuppliersPage.tsx:77-130`
- **Description:** Both render the entire fetch result in one unpaginated table with no search box — compounding BUG-521.
- **Status vs prior report:** NEW.

### BUG-534 — Purchase bill upload: no per-field validation before committing OCR-extracted lines
- **Severity:** Medium
- **Category:** Gap
- **Location:** `web/src/pages/purchases/PurchaseBillUploadPage.tsx:115-140, 360-404`
- **Description:** `quantity`/`unitPrice`/`gstRate` per preview line are free-text with no check they're non-empty/non-zero/numeric before commit is enabled (only `includedCount === 0` gates it).
- **Status vs prior report:** NEW.

### BUG-535 — Commit button can be re-clicked if the commit result lacks a purchase ID
- **Severity:** Medium
- **Location:** `web/src/pages/purchases/PurchaseBillUploadPage.tsx:141-155`
- **Description:** Navigation-away only happens when `purchaseInvoiceId` is present in the result; if absent, the page stays mounted with Commit re-enabled, risking a duplicate commit of the same job.
- **Status vs prior report:** NEW.

### BUG-536 — Fragile fallback React key can collide on duplicate product+quantity line items
- **Severity:** Low
- **Location:** `web/src/pages/sales/InvoiceDetailPage.tsx:287`; `web/src/pages/purchases/PurchaseDetailPage.tsx:216`
- **Description:** Fallback key `` `${item.product}-${item.quantity}` `` collides for two lines of the same product/quantity (e.g. two batches).
- **Status vs prior report:** NEW.

### BUG-537 — T&C default text does not hard-code Bengaluru (frontend verification)
- **Severity:** Cosmetic
- **Location:** `web/src/pages/settings/InvoiceTemplatesPage.tsx:130-140`
- **Description:** Placeholder is generic ("local jurisdiction"), not city-specific in the reviewed frontend file. (The literal Bengaluru string does exist, but only in the backend's demo seed script — see area 06's BUG-603.)
- **Status vs prior report:** INACCURATE (UX_REVIEW.md U-10) as applied to this file.

### BUG-538 — No "recalculated on save" disclaimer near preview totals
- **Severity:** Low
- **Category:** UI-Optimization
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:1247-1267, 1368-1467`; `web/src/pages/purchases/NewPurchasePage.tsx:1237-1257`
- **Description:** No UI text states totals are provisional until save — low risk today since the two calculation implementations mostly agree (see area 02's BUG-201 for the rare case where they don't), but there's no user-facing safety net if they ever drift further.
- **Status vs prior report:** INACCURATE as literally described, but the missing-affordance concern is valid — CONFIRMED (UX_REVIEW.md U-02, partial).

### BUG-539 — Zero test coverage for any of the 13 reviewed page components
- **Severity:** High
- **Category:** Test-Coverage
- **Location:** `web/src/pages/sales/*.tsx`, `web/src/pages/purchases/*.tsx` (all 13 files)
- **Description:** No `*.test.tsx`/`*.spec.tsx` exists anywhere under these directories. None of the calculation logic, state-management bugs (BUG-500/501/524/530), or validation gaps (BUG-511/526/528/532) found in this review are guarded by any automated test.
- **Remediation:** Prioritize component tests for `NewInvoicePage`/`NewPurchasePage` totals calculation and save/complete/draft mutation flows first.
- **Status vs prior report:** NEW (confirms the review brief's suspicion).

---

## Summary of most severe systemic issues

1. **The `resetForm()`-inside-`onSuccess` ordering bug (BUG-500/501)** silently wipes both the success flash message and any payment-allocation error on the "Save & New" path — a cashier can believe a receipt/payment was recorded when it actually failed, with zero visible indication.
2. **The `asList()` pagination-drop (BUG-521)** silently truncates every customer, supplier, and completed-invoice/purchase lookup used across nearly every page in this review the moment a shop's data outgrows one backend page — a scaling cliff-edge with no error surfaced.
3. **Returns are hardcoded to the first line item only (BUG-531/532)**, making sales/purchase returns non-functional for the majority of real multi-item invoices. Underlying much of the Sales/Purchase divergence (number-field editability, discount-mode UI, place-of-supply gating) is the ~1700-line duplication between the two billing pages (BUG-518): fixes visibly land in one twin and not the other, and with zero test coverage (BUG-539), nothing catches that drift automatically.
