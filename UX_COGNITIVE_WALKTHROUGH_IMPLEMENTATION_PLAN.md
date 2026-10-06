# UX & Cognitive Walkthrough: Safe Engineering Implementation Plan

**Product:** BizBoard ERP / Billing Platform (Web & Mobile PWA)  
**Document Version:** 2.0.0 (Post-Review Alignment Revision)  
**Document Status:** Approved Safe Build Specification  
**Precedence Rule:** Subordinate to [`UX_AUDIT_IMPLEMENTATION_PLAN.md`](UX_AUDIT_IMPLEMENTATION_PLAN.md) and [`DETAILED_UX_IMPLEMENTATION_PLAN.md`](DETAILED_UX_IMPLEMENTATION_PLAN.md). Where any proposal conflicts with core accounting invariants, `UX_AUDIT_IMPLEMENTATION_PLAN.md` strictly governs.  
**Target Environment:** React 18 · TypeScript · Material UI v6 · TanStack Query · Vite  

---

## 1. Non-Negotiable Accounting & Architectural Invariants

Every task in this plan must strictly adhere to the governing constraints ratified in `UX_AUDIT_IMPLEMENTATION_PLAN.md`:

1. **Zero Unaudited Ledger Posts:** Stock movements, inventory decrements, double-entry GL journals, and derived receivables/payables must never be triggered implicitly by a UX helper, onboarding wizard, or blocker dialog.
2. **Zero Invented Business Identifiers:** Never auto-generate placeholder serial numbers (e.g., `SN-001…`) or dummy HSN codes (`9999`) on real catalog products. Real tax invoices and serialized inventory require genuine physical identifiers.
3. **No Silent Tax Geography Mutations:** Never automatically overwrite a customer or supplier's master state with the company's home state. Place of supply dictates CGST+SGST vs. IGST; silent mutations pollute subsequent tax returns (GSTR-1, GSTR-3B).
4. **No Tender Without Assigned Batch:** Hardware or retail POS checkout must **never** enable Cash or UPI tender buttons while an item marked with `trackBatch: true` has an empty `batchNo`. Batch assignments remain a mandatory statutory requirement.
5. **No Stock Adjustments Inside Invoice Completion:** Insufficient stock under policy `BLOCK` must remain a hard stop. Do not hide stock adjustments or lot injections inside an invoice "Complete" action.
6. **Hard Stops Remain Disabled:** Financial period locks (`writesBlocked`), credit holds, exceeded credit ceilings, unconfirmed reverse charge (RCM), and live e-Invoice IRN locks must keep the `Complete` button strictly disabled.
7. **Scoped Reversibility:** Any PR in this plan must be independently revertible via `git revert` with zero schema drift.

---

## 2. Phased Build Order & Pull Request Breakdown

Only 5 pull requests are authorized under this plan. Each PR addresses an empirically verified cognitive breakdown while strictly respecting the invariants above.

```text
SAFE ROLLOUT ORDER:
┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
│        CW-PR-1         │      │        CW-PR-2         │      │        CW-PR-3         │
│  Customer Form Cleanup │─────►│  Receipts Auto-Lookup  │─────►│  Setup Wizard Decouple │
│  (Delete Dup Pincode)  │      │  (Open on Active List) │      │  (Draft Only, No Post) │
└────────────────────────┘      └────────────────────────┘      └───────────┬────────────┘
                                                                            │
                                                                            ▼
                                ┌────────────────────────┐      ┌────────────────────────┐
                                │        CW-PR-5         │      │        CW-PR-4         │
                                │ Actionable Next-Step   │◄─────│  Item Dialog Hoisting  │
                                │ Guidance (Field Focus) │      │  (Hero Inputs + Tabs)  │
                                └────────────────────────┘      └────────────────────────┘
```

### Summary of Authorized PRs

| PR # | Task ID | Target Component | Core Scope | Risk Profile | Est. Time |
|:---:|:---:|---|---|:---:|:---:|
| **PR-1** | `CW-01` | `CustomersPage.tsx` | Delete duplicate Pincode input; preserve pair validation | Zero Risk | 0.5 d |
| **PR-2** | `CW-02` | `ReceiptsPage.tsx` | Pre-load active customers on modal open (no 2-char block, no debtor filter) | Zero Risk | 0.5 d |
| **PR-3** | `CW-03` | `SetupWizardPage.tsx` | Decouple first bill: save draft invoice only, leave HSN blankable | Low Risk | 1.0 d |
| **PR-4** | `CW-04` | `ItemFormDialog.tsx` | Hoist Name, Sale Price, Purchase Price, GST, Unit, HSN to Hero; auto-tab to errors | Low Risk | 1.5 d |
| **PR-5** | `CW-05` | `NewInvoicePage.tsx` | Replace dead disabled button with Interactive Next-Step Guidance & Field Focus | Medium Risk | 2.0 d |

---

## 3. Detailed Component-by-Component Engineering Specifications

### 3.1 CW-PR-1: Customer Form Quality Defect Resolution
* **Target File:** `web/src/pages/sales/CustomersPage.tsx`
* **Defect Location:** Lines 500–522
* **Observed Flaw:** Pincode input is duplicated consecutively at lines 500 and 506. Latitude and Longitude are exposed as unadorned text fields that fail validation if half-filled.

#### Engineering Specification:
1. **Remove Duplicate Input:** Delete lines 505–510 containing the second `<TextField label={t('osPlan.pincode')} ... />`.
2. **Preserve Coordinate Validation Invariant:**
   * Do **not** alter lines 138–140:
     ```typescript
     if ((latitude === '') !== (longitude === '')) {
       throw new Error(t('osPlan.coordinatesPair'));
     }
     ```
   * Allow both fields to remain blank (`''`).
   * When only one coordinate is provided, the existing validation error is retained.
3. **Layout Grouping:** Wrap `latitude` and `longitude` in a compact horizontal `<Stack direction="row" spacing={1}>` labeled with helper text: `t('customers.coordinatesHelper')` (*"Optional coordinates for delivery mapping"*).
4. **Verification & Tests:**
   * Verify `CustomersPage` renders exactly one Pincode field.
   * Verify submitting a customer with blank latitude and longitude succeeds without error.
   * Verify submitting latitude without longitude triggers the existing localized `osPlan.coordinatesPair` error.

---

### 3.2 CW-PR-2: Payment Receipts Customer Lookup on Dialog Open
* **Target File:** `web/src/pages/sales/ReceiptsPage.tsx`
* **Defect Location:** Lines 114–117, Lines 441–450
* **Observed Flaw:** Query has `enabled: debouncedCustomerQuery.trim().length >= 2`. When the user opens the "Record Customer Payment" dialog, the customer list is completely empty, rendering *"No options"*. Typing 1 character continues to show *"No options"*.

#### Engineering Specification:
1. **Query Invocation Correction:**
   * Remove the 2-character minimum guard on dialog open.
   * Do **not** invent or request a `hasBalance` parameter (the backend endpoint `/api/v1/customers/` does not accept `hasBalance`).
   * Query the first page of active customers as soon as the dialog is open:
     ```typescript
     const customers = useQuery({
       queryKey: ['customers-receipt-lookup', debouncedCustomerQuery],
       queryFn: () =>
         listCustomersPage({
           q: debouncedCustomerQuery.trim() || undefined,
           status: 'ACTIVE',
           pageSize: 50,
         }),
       enabled: open && canWrite,
     });
     ```
2. **Search Narrowing:**
   * When `debouncedCustomerQuery` is blank, the dropdown displays the first 50 active customers.
   * As the user types, standard server-side string filtering (`q`) narrows the list.
3. **Option Renderer Enhancement:**
   * Use the existing optional `outstanding` balance field on `Customer` to render helpful context:
     ```tsx
     renderOption={(props, option) => (
       <li {...props} key={option.id}>
         <Box display="flex" justifyContent="space-between" width="100%" alignItems="center">
           <Typography variant="body2">{option.name}{option.phone ? ` (${option.phone})` : ''}</Typography>
           {toNumber(option.outstanding) > 0 ? (
             <Chip
               size="small"
               color="warning"
               variant="outlined"
               label={`Due: ${formatMoney(option.outstanding)}`}
               sx={{ ml: 1 }}
             />
           ) : null}
         </Box>
       </li>
     )}
     ```
4. **Verification & Tests:**
   * Run existing `web/src/pages/sales/ReceiptsPage.test.tsx`.
   * Assert that clicking `+ Record Receipt` opens the modal and triggers a query with `status: 'ACTIVE'`.
   * Assert that customers with and without open balances are visible.

---

### 3.3 CW-PR-3: Setup Wizard Ledger Decoupling & Blank HSN
* **Target File:** `web/src/pages/setup/SetupWizardPage.tsx`
* **Defect Location:** Lines 228–256 (`addProduct`), Lines 290–320 (`createFirstBill`)
* **Observed Flaw:** 
  * Step 3 (`catalog`) rejects product creation for Regular dealers if HSN is missing.
  * Step 5 (`first_bill`) calls `createSalesInvoice` followed immediately by `completeSalesInvoice`, permanently consuming invoice series #1, decrementing inventory, and posting to double-entry ledgers with dummy data.

#### Engineering Specification:
1. **Permit Blank HSN in Wizard Product Creation:**
   * Remove lines 233–236 which blocked submission when `hsnCode` was empty:
     ```typescript
     // REMOVE:
     // if (registrationType === 'REGULAR' && !product.hsnCode.trim()) {
     //   setError(t('setup.errors.hsnRequired'));
     //   return;
     // }
     ```
   * Do **not** stamp `9999` on real items (that would pollute subsequent GSTR-1 filings). Store `hsnCode: product.hsnCode.trim() || undefined`.
   * The existing completion gate in `NewInvoicePage.tsx` (`gstinRequiredForGst` and HSN checks) will enforce entering a real HSN before any final tax invoice can be completed.
2. **Decouple First Bill From Permanent Ledger Complete:**
   * In `createFirstBill()`:
     * Call `createSalesInvoice()` to persist a **DRAFT** invoice.
     * **Do NOT call `completeSalesInvoice()`**.
     * Record the draft invoice ID in state: `setDraftInvoiceId(invoice.id)`.
   * On the success view (`currentKey === 'first_bill'`):
     * Update headline: `t('setup.draftCreatedTitle')` (*"Your First Invoice Draft is Ready"*).
     * Provide two explicit, non-destructive navigation paths:
       1. **Primary Button:** `t('setup.openDraftAction')` (*"Review & Finalize Bill"*) $\rightarrow$ Navigates to `/sales/history/${draftInvoiceId}/edit`.
       2. **Secondary Button:** `t('setup.goDashboardAction')` (*"Go to Dashboard"*) $\rightarrow$ Navigates to `/`.
3. **No Wide Purge Banner:**
   * Do not add a global "Delete Sample Data" button that risks hard-deleting database records. Because the bill is saved only as a draft, the user can easily discard or delete the draft from `/sales/history` with zero ledger footprint.
4. **Verification & Tests:**
   * Run `web/src/pages/setup/SetupWizardPage.test.tsx`.
   * Assert `completeSalesInvoice` is never invoked during the setup wizard.
   * Assert a product with blank HSN is successfully created for a Regular dealer in the wizard.

---

### 3.4 CW-PR-4: Item Master Dialog ("Core Essentials" Hero & Tab Switching)
* **Target File:** `web/src/pages/inventory/ItemFormDialog.tsx`
* **Defect Location:** Lines 54–106 and Tab Content Panels
* **Observed Flaw:** Item Name is on Tab 1, Opening Stock is on Tab 2, and Selling Price / Purchase Price are on Tab 3. Users cannot view or set prices without tabbing away.

#### Engineering Specification:
1. **Hero Grid Layout (Above Tabs):**
   * Hoist the 6 high-frequency operational fields into a permanent Hero Section above `<Tabs>`:
     1. **Item Name** (`name`) — required
     2. **Selling Price** (`sellingPrice`) — keep existing `>= 0` rule (do not reject 0)
     3. **Purchase Price** (`purchasePrice`) — daily use for retail & wholesale traders
     4. **GST Rate** (`gstRate`) — dropdown (`0%, 5%, 12%, 18%, 28%`)
     5. **Primary Unit** (`unitName`) — default `PCS`
     6. **HSN/SAC Code** (`hsnCode`) — rendered in Hero if company is Regular tax dealer
2. **Sub-Tab Partitioning (Specialized Attributes Only):**
   * **Tab 1: Identifiers & Description:** Barcode, SKU, Description, Category, Brand.
   * **Tab 2: Stock & Batch Controls:** Opening Stock Quantity (with existing confirmation dialog when $>0$), Warehouse selection, Reorder Level, Tracking (`NONE`, `BATCH`, `SERIAL`).
   * **Tab 3: Pricing Tiers & Tax Mode:** MRP, Wholesale Price, Tax Inclusive/Exclusive toggles, CESS rate/amount.
   * **Tab 4: Custom Fields:** User-defined fields.
3. **Error Auto-Tab Switching:**
   * Retain all current save validations (e.g. HSN formatting, barcode uniqueness).
   * If a validation failure occurs on a field located inside an inactive tab:
     * Catch the validation error key.
     * Automatically switch the active tab index (`setTab(...)`) to the tab containing the erroneous field.
     * Set focus to that input field and render the localized inline error text.
4. **Verification & Tests:**
   * Verify that filling Name and Selling Price in the Hero section and clicking Save successfully creates the item without visiting Tab 2 or Tab 3.
   * Verify that setting invalid data in Tab 3 (e.g., negative wholesale price) and clicking Save automatically switches the active tab to Tab 3 and focuses the input.

---

### 3.5 CW-PR-5: Invoicing Actionable Next-Step Guidance & Field Focus
* **Target File:** `web/src/pages/sales/NewInvoicePage.tsx`
* **Scope Restriction:** Strictly scoped to Sales Invoice (`NewInvoicePage.tsx`). Do **not** alter `DocumentEditorShell.tsx` common logic, as it is shared with Purchases.
* **Observed Flaw:** `canComplete` in lines 1233–1243 evaluates 10 conditions. When false, the primary `Complete` button is disabled. Tooltip and alerts exist, but do not provide an immediate focus/resolution action.

#### Engineering Specification:
1. **Preserve Complete Conjunction & Hard Stops:**
   * Keep `canComplete` conjunction strictly intact:
     ```typescript
     const canComplete =
       canSave &&
       posKnown &&
       !gstinRequiredForGst &&
       !missingSerialLine &&
       !stockBlocked &&
       !creditHold &&
       !creditLimitExceeded &&
       !rcmUnconfirmed &&
       !zeroQty &&
       previewAllowsComplete(previewOnline, preview.ready, preview.error);
     ```
   * Hard statutory/accounting stops (`gstinRequiredForGst`, `creditHold`, `creditLimitExceeded`, `rcmUnconfirmed`, `writesBlocked`, `previewPending`) must keep the button disabled and continue showing their respective warning banners.
2. **Interactive Next-Step Card (Above Sticky Action Dock):**
   * When `canSave === true` and `canComplete === false`, render a high-visibility, focused **Next Step Action Card** directly above the bottom action bar:
     ```tsx
     {canSave && !canComplete && completeDisabledReason ? (
       <Paper
         elevation={2}
         sx={{
           p: 1.5,
           mb: 1,
           bgcolor: 'warning.light',
           border: '1px solid',
           borderColor: 'warning.main',
           borderRadius: 1,
         }}
       >
         <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
           <Stack direction="row" spacing={1} alignItems="center">
             <WarningAmberIcon color="warning" />
             <Typography variant="body2" fontWeight={600}>
               {completeDisabledReason}
             </Typography>
           </Stack>
           {renderBlockerFocusButton()}
         </Stack>
       </Paper>
     ) : null}
     ```
3. **Field Focus Actions (Zero Ledger Mutations):**
   * Implement `renderBlockerFocusButton()` with pure focus/navigation triggers:
     * **Missing Serial:** If `missingSerialLine` is set, render button:
       `t('billing.focusSerialAction')` (*"Go to Serial Field"*) $\rightarrow$ Executes `document.getElementById(`serial-input-${missingSerialLine.key}`)?.focus()`.
     * **Negative Stock:** If `stockBlocked` is set, render button:
       `t('billing.reviewStockAction')` (*"Review Shortfall"*) $\rightarrow$ Scrolls viewport to the stock shortfall warning alert.
     * **Place of Supply Unknown:** If `!posKnown` is set, render button:
       `t('billing.setCustomerStateAction')` (*"Select Customer State"*) $\rightarrow$ Focuses customer state input field in `InvoicePartyPanel`.
   * **STRICT PROHIBITION:**
     * Do **NOT** auto-fill sequential serial numbers (`SN-001...`).
     * Do **NOT** auto-assign company home state to the customer.
     * Do **NOT** post stock adjustments from this card or invoice completion.
4. **Verification & Tests:**
   * Run existing `web/src/pages/sales/InvoiceDetailPage.test.tsx` and related tests.
   * Add test verifying that when an item requires serials, clicking the focus button moves DOM focus directly into the serial input cell.

---

## 4. Internationalization (i18n) Parity Catalog

Every new user-facing string must be declared in both `web/src/i18n/en.ts` and `web/src/i18n/hi.ts` to satisfy `web/src/i18n/fullParity.test.ts`.

| Catalog Key | English (`en.ts`) | Hindi (`hi.ts`) |
|---|---|---|
| `customers.coordinatesHelper` | "Optional coordinates for delivery mapping" | "डिलीवरी मैपिंग के लिए वैकल्पिक निर्देशांक" |
| `receipts.searchCustomerPlaceholder` | "Search active customer by name or phone…" | "सक्रिय ग्राहक को नाम या फोन से खोजें…" |
| `setup.draftCreatedTitle` | "Your First Invoice Draft is Ready" | "आपका पहला बिल ड्राफ्ट तैयार है" |
| `setup.openDraftAction` | "Review & Finalize Bill" | "बिल की समीक्षा करें और पूरा करें" |
| `setup.goDashboardAction` | "Go to Dashboard" | "डैशबोर्ड पर जाएं" |
| `billing.focusSerialAction` | "Enter Serial Numbers" | "सीरियल नंबर दर्ज करें" |
| `billing.reviewStockAction` | "Review Stock Shortfall" | "स्टॉक की कमी की समीक्षा करें" |
| `billing.setCustomerStateAction` | "Select Customer State" | "ग्राहक का राज्य चुनें" |

---

## 5. Non-Buildable & Deferred Items (Safety Decision Ledger)

The following items from initial proposals are explicitly **REJECTED** or **DEFERRED** from this implementation plan:

1. **Auto-FEFO Batch Selection on POS:**
   * *Status:* **DEFERRED TO DEDICATED POS TRACK (`UX_AUDIT_IMPLEMENTATION_PLAN.md` task L6).**
   * *Reason:* Auto-selecting lots during scanner input risks dropping batches on split lines, offline sync, or cache miss. Tender must remain disabled until an in-date lot covering the quantity is explicitly confirmed.
2. **Auto-Assigning Home State to Customer:**
   * *Status:* **REJECTED.**
   * *Reason:* Writing home state to the party master permanently books wrong tax for inter-state customers on future invoices. GST settings already possess a walk-in "assume local state" toggle for OTC sales.
3. **One-Click Inline Stock Adjustment:**
   * *Status:* **REJECTED.**
   * *Reason:* Hides inventory shortfalls inside invoice clicks, corrupting physical audit trails. Shortfalls must be resolved via the formal stock adjustment workflow or negative-stock company policy.
4. **Navigation Menu Overhaul (Sell / Buy / Money):**
   * *Status:* **REJECTED FOR THIS CYCLE.**
   * *Reason:* Navigation is already gated by permissions, runtime flags, `ALWAYS_HIDDEN_NAV`, and `PACK_HIDDEN_SECTIONS`. Re-architecting into 4 hubs breaks canonical help documentation links and routing contracts.
5. **Tally Keyboard Shortcut Remapping (`Alt+A`, `Alt+C`, table `Enter`):**
   * *Status:* **DEFERRED.**
   * *Reason:* Unspecified interaction against existing Enter resolvers and F2 barcode listeners. Requires standalone RFC before altering table focus mechanics.

---

## 6. Definition of Done & Quality Gates

A pull request under this plan can only merge when all of the following conditions are met:

1. **Accounting Invariants Unviolated:** Zero implicit ledger postings, zero invented HSN/serials, zero silent party state overwrites.
2. **Test Suite Execution:**
   * `web/src/pages/setup/SetupWizardPage.test.tsx` passes.
   * `web/src/pages/sales/ReceiptsPage.test.tsx` passes.
   * `web/src/i18n/fullParity.test.ts` passes with 100% key parity between `en.ts` and `hi.ts`.
3. **Mobile Responsive & Viewport Check:**
   * Forms verified at 375px viewport width in Hindi locale.
   * No overlapping buttons, text truncation, or obscured sticky dock actions.
4. **Clean Rollback Unit:**
   * Each PR must cleanly revert via `git revert <commit>` with zero residual database or state artifacts.
