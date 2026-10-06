# Master UX Implementation Plan & Slice Backlog: BizBoard ERP

**Document Version:** 2.1.0 (Post-Review Revision)  
**Document Status:** Ratified Slice Backlog & Implementation Guide  
**Target Environment:** Web & Mobile PWA (`React 18` · `Vite` · `TypeScript` · `Material UI v6` · `TanStack Query`)  
**Core Architectural Constraint:** 100% preservation of core accounting invariants, double-entry ledgers, and GST calculation rules (zero backend schema or posting drift).  
**Definition of Done Standard:** All test assertions pass; 100% i18n parity between `en.ts` and `hi.ts` via `fullParity.test.ts`; zero visual clipping or button overlap at 375px mobile viewport width in Hindi.

---

## 1. Executive Blueprint & Phased Rollout Matrix

The implementation is split into isolated, pull-request-scoped units. Slices **PR-A**, **PR-B**, and **PR-C** are completely independent and can be executed and reviewed in parallel. PR-D (POS Counter) depends solely on the PWA offline shell fix from PR-A. PR-E (Drafts) builds upon the multi-cart foundations in PR-D.

```text
PR DEPENDENCY & ROLLOUT TOPOLOGY:
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│      PR-A       │        │      PR-B       │        │      PR-C       │
│  Offline Shell  │        │ Terminology &   │        │ Dashboard Rupee │
│  (Fix sw loop)  │        │   Glossary      │        │    Hierarchy    │
└────────┬────────┘        └────────┬────────┘        └────────┬────────┘
         │                          │                          │
         ▼                          │                          │
┌─────────────────┐                 │                          │
│      PR-D       │                 │                          │
│ POS Scanner     │                 │                          │
│ Ergonomics      │                 │                          │
└────────┬────────┘                 │                          │
         │                          │                          │
         ▼                          ▼                          │
┌─────────────────┐        ┌─────────────────┐                 │
│      PR-E       │        │      PR-F       │ ◄───────────────┘
│ Device Drafts   │        │ Sticky Dock &   │
│ (deviceDraft.ts)│        │ Live Credit Line│
└─────────────────┘        └────────┬────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │      PR-G       │
                           │ Purchase RCM &  │
                           │ Nav Pruning     │
                           └────────┬────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │      PR-H       │
                           │ Bank Recon      │
                           │ (Deferred Track)│
                           └─────────────────┘
```

### Detailed PR Slicing Breakdown

| Slice / PR | Primary Scope & Deliverables | Dependencies | Can Run Beside |
|---|---|---|---|
| **PR-A (Unlock)** | Offline PWA shell (`web/public/offline.html`, `web/vite.config.ts`) | None (Ship first) | PR-B, PR-C |
| **PR-B (Copy)** | Terminology cleanup: "Receipts" in nav/breadcrumbs, "Godowns" retained | None | PR-A, PR-C, PR-D |
| **PR-C (Dashboard)**| Collapse `ShopFloorFunnel` telemetry table into drawer; rupee tiles above fold | None | PR-A, PR-B |
| **PR-D (Counter)** | POS scanner hero layout, `choosePosEnter` Enter resolver, F2 focus lock | PR-A | PR-B, PR-C |
| **PR-E (Drafts)** | Local draft persistence via `deviceDraft.ts`, restore prompt & price refresh | PR-D | PR-F |
| **PR-F (Documents)**| Sticky action bar in `DocumentEditorShell`, live credit risk line | PR-B, PR-C | PR-E |
| **PR-G (Purchases)**| Verify visibility of RCM/ITC statutory controls on GST purchases | PR-F | PR-H |
| **PR-H (Recon)** | Split-pane bank reconciliation workbench (Separate Accounting Design) | Post-Now (PR-G) | Independent |

---

## 2. Component-by-Component Engineering Specifications

### 2.1 High-Speed Counter POS (`web/src/pages/pos/PosPage.tsx`)
* **Violated Heuristics:** H1 (System Status), H5 (Error Prevention), H7 (Flexibility & Efficiency), H8 (Minimalist Design)
* **Target Personas:** Retail Cashier (Kirana / Chemist), Wholesale Counter Clerk

#### A. Architectural & Layout Hierarchy
1. **Scanner Viewport Hero:**
   * Move the barcode and SKU search input to the primary top position of the interactive counter.
   * Collapse auxiliary metadata (`Customer`, `Godown/Warehouse`, and `Offline Outbox status`) into a single compact horizontal strip above the scanner.
   * Hide the walk-in manual name field unless the cashier explicitly selects a non-catalog walk-in customer mode.
2. **Focus Management & Scanner Lock Rules:**
   * **Rule 1 (Scan Completion):** Return focus to the barcode scanner (`searchRef.current?.focus()`) **only** after a successful scan when the active element is either the scanner input itself or the page body (`document.body`).
   * **Rule 2 (Editing Caret Preservation):** Never steal focus when the active element is inside a table line input (Quantity stepper, Discount %, Unit Rate, or Batch selector). A clerk typing quantities or adjustments must never have their caret ripped away.
   * **Rule 3 (Batch Navigation):** When a batch-tracked product is added, do **not** auto-focus the batch input field. The hardware scanner must remain ready for the next product code. Enter key inside the batch field may return focus to the scanner; `blur` must **not** return focus.
   * **Rule 4 (`F2` Hotkey):** Global `F2` listener calls `searchRef.current?.focus()` and `e.preventDefault()`, matching the promise in `pos.subtitle`. Ignore `F2` if a modal dialog is open or if focus is currently in a batch input.

#### B. Hardware Scanner Enter Resolution via `choosePosEnter`
Do **not** invent a new resolver function. Leverage the production-tested `choosePosEnter` in `web/src/pages/pos/posEnter.ts`:

```typescript
// web/src/pages/pos/posEnter.ts (Current canonical resolver)
export function choosePosEnter(args: {
  query: string;
  highlighted: PosEnterProduct | null;
  listOpen: boolean;
  catalog: PosEnterProduct[];
  optionsStale: boolean;
  exactWins?: boolean;
}): PosEnterChoice {
  const exactWins = args.exactWins ?? POS_ENTER_EXACT_WINS;
  const exact = exactWins ? findExactProduct(args.query, args.catalog) : undefined;
  if (exact) return { action: 'add', productId: exact.id, via: 'exact' };
  const scanPending = args.optionsStale && looksLikeHardwareScan(args.query);
  if (scanPending) return { action: 'wait' };
  if (args.listOpen && args.highlighted) {
    return { action: 'add', productId: args.highlighted.id, via: 'highlight' };
  }
  return { action: 'barcode-lookup' };
}
```

* **Exact Matches:** Case-insensitive comparison (`p.barcode.toLowerCase() === q` or `p.sku.toLowerCase() === q`).
* **Debounce Safety:** If a hardware scan ($\ge 8$ non-whitespace chars) is submitted while autocomplete options are stale, returns `{ action: 'wait' }` rather than a false not-found alert.
* **Hotfix Constant:** `POS_ENTER_EXACT_WINS` is a module constant defaulting to `true`. Changing it is an audited code deployment, not an environment flag.

#### C. Batch Blocker Transparency & Accessibility
1. Tender buttons (`Cash`, `UPI`) remain disabled until every batch-tracked line has an assigned batch.
2. Render the existing localized copy directly above tender controls:
   ```tsx
   <Typography id="pos-batch-blocker" variant="body2" color="warning.main">
     {t('pos.enterBatchToComplete')}
   </Typography>
   ```
3. Associate tender buttons via `aria-describedby="pos-batch-blocker"`.

---

### 2.2 PWA Service Worker Offline Recovery (`web/public/offline.html`)
* **Violated Heuristics:** H1 (System Status), H9 (Error Recovery)
* **Target Personas:** Retail Cashiers on intermittent internet connections

#### A. Distinct Retry vs. Hard-Reload Behavior
* **Problem in Previous Draft:** Unregistering all service workers on every retry deletes the precached application shell and offline outbox that the cashier needs during network drops.
* **Correction:**
  1. **"Try again" (`#try-again`):**
     * If `navigator.onLine === true`, execute `window.location.replace('/')`. Do **not** call `unregister()`.
     * If `navigator.onLine === false`, display inline text on the page (`#offline-alert`): *"Device is still offline. Please check your connection."* (Zero JavaScript `alert()` popups).
  2. **"Reload without cache" (`#hard-reload`):**
     * Intended as the explicit manual recovery escape hatch. Unregisters active service workers and calls `window.location.replace('/login?nocache=' + Date.now())`.

```javascript
// web/public/offline.html implementation
document.getElementById('try-again').addEventListener('click', function(e) {
  e.preventDefault();
  if (navigator.onLine) {
    window.location.replace('/');
  } else {
    var alertEl = document.getElementById('offline-alert');
    if (alertEl) {
      alertEl.textContent = 'Device is still offline. Please check your connection.';
      alertEl.style.display = 'block';
    }
  }
});

document.getElementById('hard-reload').addEventListener('click', function(e) {
  e.preventDefault();
  if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
    navigator.serviceWorker.getRegistrations().then(function(regs) {
      return Promise.all(regs.map(function(r) { return r.unregister(); }));
    }).finally(function() {
      window.location.replace('/login?nocache=' + Date.now());
    });
  } else {
    window.location.replace('/login?nocache=' + Date.now());
  }
});
```

* **Acceptance Test:** In `web/e2e/ux-audit-now.spec.ts`, assert that clicking `#try-again` performs navigation without calling `navigator.serviceWorker.getRegistrations`.

---

### 2.3 Local Draft Persistence & Price Revalidation (`web/src/lib/deviceDraft.ts`)
* **Violated Heuristics:** H3 (User Control & Freedom), H5 (Error Prevention)
* **Target Personas:** All billing operators

#### A. Canonical Storage Contract
Use the existing canonical schema in `web/src/lib/deviceDraft.ts`:
* **Storage Key:** `draftKey(companyId: number, userId: number, kind: DraftKind)`  
  $\rightarrow$ `bizboard:draft:v1:${companyId}:${userId}:${kind}`
* **Storage Envelope:**
  ```typescript
  export type StoredDraft<T> = {
    version: 1;
    savedAt: string; // ISO 8601 string
    payload: T;
  };
  ```
* **TTL:** 36 hours (`DRAFT_TTL_MS = 36 * 60 * 60 * 1000`). Stale drafts automatically purged on read.
* **Isolation & Logout:** `clearForUser(companyId, userId)` removes all drafts and legacy cart keys when `AuthContext` executes logout.

#### B. Safe Restore & Price Revalidation Protocol
* **Revalidation Principle:** Drafts store party ID, product IDs, quantities, and discounts. Drafts must **never** post unverified historical prices directly to the ledger.
* **On Restore (`posRestore.ts` / `NewInvoicePage.tsx`):**
  1. Re-query master product prices from TanStack Query cache / server API.
  2. If an item was deleted (404), drop the line and notify the user: `t('billing.itemUnavailableDropped', { name })`. Network errors must **not** drop lines; only drop items confirmed missing.
  3. If current selling rate differs from the draft, apply the current rate and show a **single summary notification** (`t('billing.pricesUpdatedSummary')`), avoiding notification stacking on 40-line bills.

---

### 2.4 Document Sticky Action Bar & Proactive Credit Line (`web/src/components/billing/DocumentEditorShell.tsx`)
* **Violated Heuristics:** H3 (User Control), H5 (Error Prevention), H7 (Efficiency)
* **Target Personas:** Munimji / Accountant, Wholesale Billing Operator

#### A. Sticky Bottom Bar Integration
Do **not** create a redundant component. Enhance the sticky action bar already built into `DocumentEditorShell.tsx` (lines 215–251):
* **Positioning:** `position: 'sticky', bottom: 0, zIndex: 2, pb: 'env(safe-area-inset-bottom)'`.
* **Mobile Viewport Rule ($<600\text{px}$):** Retain the primary complete button in the top title row as well, ensuring accessibility when mobile virtual keyboards pop up.
* **Internationalization & Money Formatting:** All labels must use `t()` catalog keys (`t('billing.grandTotal')`, `t('common.saveDraft')`, `t('billing.complete')`, `t('billing.readyToComplete')`). Numbers must pass through `formatMoney()`.

#### B. Proactive Credit Risk Warning Line (`web/src/pages/sales/invoice/InvoicePartyPanel.tsx`)
* **Numeric Parsing:** Parse incoming string amounts using `Number(customer.outstanding || 0)` and `Number(customer.creditLimit || 0)`.
* **Dynamic Ceiling Predicate:** The check must include the bill on screen:
  $$\text{Effective Exposure} = \text{Number}(customer.outstanding) + \text{currentBillTotal}$$
* **Threshold Rules:**
  1. **Near Limit ($\ge 80\%$):** If $\text{Number}(customer.outstanding) \ge 0.8 \times \text{Number}(customer.creditLimit)$ and bill does not breach ceiling: Amber warning chip.
  2. **Ceiling Exceeded:** If $\text{Effective Exposure} > \text{Number}(customer.creditLimit)$: Red danger chip. Disable the `Complete` button from the exact same predicate the backend enforces (`creditLimitExceeded`).

---

### 2.5 Purchasing Statutory Controls & Terminology Harmonization
* **Violated Heuristics:** H2 (Real World Match), H4 (Consistency & Standards), H5 (Error Prevention)

#### A. Purchase Bill RCM & ITC Visibility Check (`web/src/pages/purchases/NewPurchasePage.tsx`)
* **Visibility Verification:** Confirm that Reverse Charge (`isRcm`) and ITC Eligibility controls are rendered directly within the primary GST tax panel on `NewPurchasePage`, not collapsed inside an "Advanced" accordion.
* **Supplier Warning:** When purchase type is GST and supplier has no GSTIN, verify existing copy in `billing.supplierNoGstinRcm`:
  *"This supplier has no GSTIN. Turn on reverse charge if this purchase is under RCM."*
* **GRN Guidance:** Verify existing copy in `billing.grnGuidance`:
  *"Completing this bill immediately updates stock levels and posts the supplier balance."*

#### B. Glossary Harmonization Across Catalogs (`en.ts` and `hi.ts`)
* **Receipts:** Navigation and lists use `nav.receipts` $\rightarrow$ "Receipts".
* **Godowns:** In Indian wholesale and retail trade, "Godown" is standard statutory parlance. Retain `nav.warehouses` $\rightarrow$ "Godowns".
* **Invoice Status:** Unpaid invoices with open balances show `status.unpaid` $\rightarrow$ "Unpaid", not "Completed".

---

### 2.6 Bank Reconciliation Workbench (`BankReconPage` / `AccountingBankReconPage`)
* **Status:** **DEFERRED TO DEDICATED ACCOUNTING DESIGN TRACK (PR-H)**
* **Heuristics:** H3 (User Control), H5 (Error Prevention), H8 (Minimalist Design)

#### Architectural Correction & Accounting Safety Guard
* **Rejection of Timer-Based Optimistic Post:** An 8-second auto-commit timer that posts journal entries is dangerous. If the accountant tabs away, an unwanted financial transaction would commit. In addition, an arbitrary `Ctrl+Z` shortcut could trigger accidental rollbacks during text search.
* **Governing Rules for PR-H:**
  1. **Target Routes:** Work occurs in `web/src/pages/phase/BankReconPage.tsx` and `AccountingBankReconPage.tsx` using `/api/v1/banking/`.
  2. **Explicit User Commit:** Ledger postings occur **only** on an explicit "Confirm Match" button click.
  3. **Formal Reversing Entries:** Any undo must create an idempotent reversing entry following double-entry ledger invariants.
  4. **Split-Pane Layout:** Visual matching operates in a side-by-side split pane (Imported Bank Rows on Left, ERP Ledger Entries on Right) with confidence score indicators.

---

## 3. Accessibility (WCAG 2.1) & Mobile Ergonomics Realism

1. **Target Size Standards:**
   * A $48\times48\text{px}$ target is a **WCAG 2.5.5 Level AAA** criteria and an ergonomic best practice for touch devices. The mandatory **WCAG 2.1 Level AA** requirement is $24\times24\text{px}$ (WCAG 2.5.8).
   * Enforce $44\times44\text{px}$ or $48\times48\text{px}$ touch targets on viewports $<600\text{px}$ for mobile retail usability, while documenting this accurately as a mobile ergonomic enhancement.
2. **Focus Visibility via Theme Tokens:**
   * Do not hardcode raw hex values (`#1976d2`). Use MUI theme tokens:
     ```typescript
     '&:focus-visible': {
       outline: (theme) => `2px solid ${theme.palette.primary.main}`,
       outlineOffset: '2px',
     }
     ```
3. **Polite Screen Reader Announcements:**
   * Do **not** trigger `aria-live="polite"` on every keystroke in quantity or price inputs (which talks over the cashier).
   * Announce the grand total only when a line item is committed to the cart or when the tender payment modal opens.

---

## 4. Verification Framework & Rollback Protocol

### 4.1 Verification Commands
Do **not** run `npm test` (which launches Vitest in interactive watch mode). Use the non-interactive CI test runner:

```bash
# Web verification suite
cd web
npm run test:run
npm run lint

# Backend accounting invariant verification
cd ../backend
python -m pytest tests/workflows/ test_party_name.py
```

* **i18n Parity Enforcement:** `web/src/i18n/fullParity.test.ts` runs automatically during `npm run test:run`. Any key present in `en.ts` but missing in `hi.ts` immediately fails the build.
* **Known Existing Test Suites:**
  * `web/src/pages/pos/posEnter.test.ts`
  * `web/src/lib/deviceDraft.test.ts`
  * `web/src/navigation/menu.test.ts`
  * `web/src/pages/DashboardPage.test.tsx`
  * `web/src/pages/sales/invoiceDefaults.test.ts`
  * `web/src/pages/sales/receiptAllocation.test.ts`
  * `backend/tests/test_party_name.py`

### 4.2 Rollback Units
Every pull request in the pipeline represents an atomic rollback unit (`git revert <PR-COMMIT>`). There are no multi-PR interlocked database migrations or un-versioned schema changes.
