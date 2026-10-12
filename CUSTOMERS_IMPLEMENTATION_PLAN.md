# Customers Module: Comprehensive Screen, Flow, Product Impact Audit & Implementation Plan

**Document:** `CUSTOMERS_IMPLEMENTATION_PLAN.md`  
**Primary Screen:** Customers Directory (`web/src/pages/sales/CustomersPage.tsx`, route `/sales/customers`)  
**Detail / 360° Screen:** Customer 360° Snapshot (`web/src/pages/sales/Customer360Page.tsx`, route `/sales/customers/:id`) & Value Index (`web/src/pages/sales/customer360Value.ts`)  
**Inline Counterpart:** Sales Invoice Party Selector & Quick-Add (`web/src/pages/sales/invoice/InvoicePartyPanel.tsx`)  
**Backend Domain:** `backend/masters/` (`models.py`, `serializers.py`, `views.py`), `backend/core/services/gstin_verify.py`, `backend/ledgers/services.py`  
**Audit Roles:** Principal Product Manager · Senior UX Designer · Business Analyst · Software Architect · QA Lead  
**Audit Date:** 2026-10-11  
**Verdict:** 🟡 **READY WITH FIXES** — delivered in three releases (R1 integrity/permissions, R2 form/cache/UX, R3 enhancements); progress is tracked by the exit checklist in Part III, not by a numeric score.
**Detailed work packages:** [docs/CUSTOMERS_WORK_PACKAGES.md](docs/CUSTOMERS_WORK_PACKAGES.md) — step-by-step plan, files, tests and risks for every `CUS-xx` item, plus a "Baseline reconciliation" table of audit claims that no longer match HEAD (e.g. debounce and null-coordinate clearing already exist; shipping addresses have only `label/address/is_default`). Where the two documents disagree, the work-packages file is the more recent.
**Status (2026-10-11):** every item `CUS-01..CUS-27` is implemented; see the status section of [docs/CUSTOMERS_WORK_PACKAGES.md](docs/CUSTOMERS_WORK_PACKAGES.md) and [docs/CUSTOMERS_STATUS_SEMANTICS.md](docs/CUSTOMERS_STATUS_SEMANTICS.md). Founder decisions taken: archived customers are refused on new documents like blocked ones; Customer 360° and the strict GSTIN/state/phone rules are on by default; archive/delete is owner/manager only.
**Revision:** v2 (2026-10-11) — incorporates review comments: release split, shared GSTIN helper, legacy-data backfill, concurrency/permission/abuse hardening, new gap items `CUS-21..CUS-27`. Line numbers cited below must be re-verified against HEAD before each work item starts.


> **Read this first — where this document is out of date.** It was written from an earlier view of the code. Corrected by later work (see `docs/CUSTOMERS_WORK_PACKAGES.md` §0 and `docs/CUSTOMERS_REVIEW_2026-10-12.md`):
> rows were never clickable (the name is now a link to 360°, which is on by default); search was already debounced; clearing coordinates already sent `null`;
> the backend already validated coordinates; shipping addresses have only `label`, `address` and `is_default`; the GSTIN lookup result has no `.error` (the note is in `raw`);
> tests live in `backend/tests/`, not `backend/masters/tests/`; the example GSTIN `27AABCU9603R1ZM` had a wrong check character (`...ZN` is valid);
> `verify_gstin` is open to anyone who can create sales (throttled), not owner-only; the "10/10" scoring was dropped; INACTIVE customers are now refused on new documents.
> Line numbers cited below are from the earlier code and no longer match.

---

## Executive Summary

The **Customers** module (`CustomersPage.tsx` + `Customer360Page.tsx` + `CustomerViewSet`) is the foundational Accounts Receivable and Party Master registry for Bizboard. Every downstream revenue workflow—Sales Invoices, POS Checkout, Sales Orders, Quotations, Proforma Invoices, Credit/Debit Notes, Money In (Customer Receipts), Customer Ledger, Receivables Aging, Field Sales Visits, Collection Risk holds, and GSTR-1 / e-Invoicing—depends directly on the accuracy and invariants of `Customer` records.

A code-verified audit across the full stack (`Screen → User Goal → Interaction → Flow → Data → Business Logic → System State → Other Screens → Other Modules → Downstream Impact → Edge Cases → Regression Risk`) revealed:
- **Core Remediation Set (`CUS-01` .. `CUS-14`):** 4 P0 blockers, 5 P1 major workflow/data integrity defects, 3 P2 moderate improvements, and 2 P3 UX/localization fixes.
- **Enhancement Set (`CUS-15` .. `CUS-20`):** 6 feature/automation/API-hardening/accessibility items. These are scope additions, not defect fixes, and ship last (R3).
- **Gap Set (`CUS-21` .. `CUS-27`):** 7 items added after review: shared GSTIN helper, legacy-data backfill, credit-term permissions, customer audit history, import-path parity, backend field validation, and observability.
- **Why the numeric scorecard was removed:** per-dimension scores were unmeasured estimates and a "10.0 / 10" claim is not verifiable. Sign-off is by the exit checklist in Part III.

---

## Part I: 20-Section Product, UX, Architecture & QA Review

### 1. SCREEN PURPOSE

- **What is this screen for?**
  - **Observed:** `web/src/pages/sales/CustomersPage.tsx` (`/sales/customers`) is the primary party master directory for buyers/debtors. It supports searching, status filtering (`ACTIVE`, `BLOCKED`, `INACTIVE`), sorting (`name`, `recent`, `balance`), paginated browsing, live GSTIN portal verification, receivable balance inspection (`outstanding` + `CreditHoldChip`), status toggling (`ACTIVE` ↔ `BLOCKED`), and a modal dialog for creating/editing customer records, alongside navigation to Customer 360° (`/sales/customers/:id`) and Customer Ledger (`/reports/customer-ledger?customer=:id`).
- **Who is likely to use it?**
  - **Observed:** Guarded by `RoleRoute allow={canViewSalesSurfaces}` (`web/src/App.tsx:397-407`), admitting `OWNER`, `MANAGER`, `SALES_STAFF`, and any `ACCOUNTANT`/`AUDITOR` with `canCreateSales` or `canViewFinancialReports` (`web/src/utils/permissions.ts:88-91`).
  - **Inferred:**
    - **Billing / Sales Counter Staff:** Onboarding B2B/B2C buyers, verifying GSTIN/state before billing.
    - **Accounts Receivable / Accountants:** Reviewing customer balances, credit holds, and opening ledgers.
    - **Business Owners / Sales Managers:** Setting credit limits/days, blocking delinquent customers, reviewing 360° customer value.
- **What user problem does it solve?**
  - **Observed:** Centralizes buyer tax identity (GSTIN, state for intra/inter-state GST determination), contact details, geo-coordinates for field sales, and real-time receivable exposure.
- **What is the primary user goal & primary action?**
  - **Observed:**
    1. **Locate & evaluate a customer's receivable/credit posture** (Search/Filter → Row click to `Customer360Page` or **View Ledger**).
    2. **Create or update a customer master record** via **`+ Add`** (`CustomersPage.tsx:218-227`) or row **`Edit`** (`CustomersPage.tsx:371-380`).
- **What should the user be able to accomplish here?**
  - **Observed:** Manage contact details, GSTIN, state, billing address, and GPS coordinates; verify GSTIN; block/unblock customers; navigate to Customer 360° or Ledger.
  - **Observed (Critical Gap):** Users **should** be able to manage credit terms (`creditLimit`, `creditDays`), statutory classification (`taxpayerType`, `pan`), shipping addresses (`shippingAddress`, `shippingAddresses`), internal `notes`, custom fields (`customFields`), and POS Walk-In designation (`isPosWalkIn`). All of these exist in `backend/masters/models.py:64-162` and `backend/masters/serializers.py:140-202`, and drive downstream business rules, yet **none are exposed in the UI**.
- **What should NOT be handled on this screen?**
  - **Inferred:** Direct mutation of ledger balances without accounting vouchers, invoice creation inside the master list, or vendor/supplier management.
- **Is the purpose immediately clear?**
  - **Observed:** **Yes** as a basic contact/balance directory; **No** as an ERP credit-control and GST compliance master.

---

### 2. USER EXPERIENCE REVIEW

- **Clarity & Terminology:**
  - **Observed (Defect):** The Sort `<TextField select>` (`CustomersPage.tsx:249`) uses `label={t('common.filter')}` (**"Filter"**) right next to the Status filter, creating two controls labeled "Filter" / "Status".
  - **Observed (Defect):** Hardcoded English strings violate Hindi (`hi.ts`) i18n parity: `"GSTIN status"` (`L291`), `"Unverified"` (`L331`), `+ customer` / `Edit customer` (`L414`), `"Customer name is required"` (`L426`), `"Enter a valid 10-digit Indian mobile number"` (`L439`), `"Invalid 15-digit GSTIN checksum/format"` (`L494`), `"State or GSTIN is required for GST invoices"` (`L514`), and coordinate helper text (`L552-556`).
- **Visual Hierarchy & Semantic Feedback:**
  - **Observed (Defect):** `gstinStatusColor()` (`CustomersPage.tsx:68-78`) maps `case 'VERIFIED': return 'success'`. However, `backend/core/services/gstin_verify.py:19-25` and `Customer.GSTIN_STATUS_CHOICES` (`models.py:65-71`) store `'VALID'`, `'INVALID'`, `'CANCELLED'`, `'SUSPENDED'`, or `'UNVERIFIED'`. Because `'VALID'` is not handled, **every verified `'VALID'` GSTIN displays an amber `warning` chip instead of green `success`**, and **`'CANCELLED'` / `'SUSPENDED'` GSTINs also display amber `warning` instead of red `error`**.
- **Discoverability & Affordances:**
  - **Observed:** Table rows (`CustomersPage.tsx:307-315`) use `cursor: 'pointer'` to open `/sales/customers/:id`, while the Actions cell calls `e.stopPropagation()`. There is no visual link styling on the customer's name or chevron icon to signal that clicking a row opens the Customer 360° workspace.
- **Feedback & Error Visibility:**
  - **Observed (Critical UX Bug):** `<HelpErrorAlert message={error} />` is rendered at `CustomersPage.tsx:230` on the base page, **outside `<Dialog>`** (`L413-571`). Any validation throw or API error during `saveMutation` renders **behind the dark modal backdrop**. Furthermore, `openCreate()` and `openEdit()` (`L138-153`) do not call `setError(null)`, leaving old error banners visible across modal sessions.
- **Error Prevention:**
  - **Observed:** Clicking **Block** (`CustomersPage.tsx:381-390`) immediately fires `PATCH /customers/:id/` with `{ status: 'BLOCKED' }` without any confirmation dialog, even for high-balance customers or the company's `isPosWalkIn` counter customer.

---

### 3. COGNITIVE LOAD

- **Information & Memory Burden:**
  - **Observed:** The table shows `Outstanding` (`c.outstanding`) and `CreditHoldChip`, but hides `creditLimit`, `creditDays`, and `creditExposure` (which nets out unallocated customer advances). Operators cannot tell from the list *why* a customer is on credit hold or how much credit headroom remains.
  - **Observed:** When onboarding a B2B customer, the operator must manually type `name`, `state`, and `billingAddress` because the **Verify** GSTIN action is only available on the table row *after* saving the customer (`CustomersPage.tsx:336-344`), rather than inside the modal to auto-populate `gstin_legal_name` and address from the GST portal.

---

### 4. USER FLOW

```text
Entry (Sidebar `/sales/customers`, Command Palette, Customer360 Back button, or Invoice/Receipt screens)
 ↓
Previous state: Parallel fetch of `GET /api/v1/customers/?page=1&page_size=25&sort=name` + `GET /api/v1/collection-risk/`
 ↓
Current screen: CustomersPage (Search / Status Filter / Sort / Paginated Table)
 ↓
User action:
  ├─ Path A: Click "+ Add" or Row "Edit" → Modal opens → Fill fields → Click "Save"
  ├─ Path B: Click "Verify" in GSTIN status column → `POST /api/v1/customers/:id/verify-gstin/`
  ├─ Path C: Click "Block" / "Unblock" → `PATCH /api/v1/customers/:id/` (`{ status }`)
  ├─ Path D: Click Row → Navigates to `/sales/customers/:id` (`Customer360Page`)
  └─ Path E: Click "View Ledger" → Navigates to `/reports/customer-ledger?customer=:id`
 ↓
System response:
  ├─ Path A: `POST` or `PATCH /customers/` → Optimistic cache update + `invalidateQueries(['customers'])` → Modal closes
  ├─ Path B/C: `invalidateQueries(['customers'])` → Row updates
 ↓
Next screen/action: Customer360Page (New Invoice, Record Receipt, Log Follow-up, WhatsApp) or Customer Ledger
```

- **Broken / Confusing Flow Steps:**
  1. **Dead-End Navigation on "View Ledger" (`Observed`):** `CustomersPage.tsx:364-370` renders **View Ledger** for all users, but `/reports/customer-ledger` is wrapped in `RoleRoute allow={canViewFinancialReports}` (`App.tsx:547-560`). A `SALES_STAFF` user clicking **View Ledger** lands on the Access Denied page.
  2. **No Edit Capability on `Customer360Page` (`Observed`):** Clicking a customer row opens `Customer360Page.tsx`, which offers `+ Sales Invoice`, `Record Receipt`, `Ledger`, and `Log follow-up`, but has **no Edit Customer button**. Users must navigate back to `/sales/customers`, re-search the customer, and click `Edit`.
  3. **Inconsistent `INACTIVE` Status Flow (`Observed`):** Users can filter the table by `status = INACTIVE` (`CustomersPage.tsx:243`), which is set on backend `DELETE /customers/:id/` when a customer has historical transactions (`views.py:345-360`). However, the UI has no Delete/Archive button, and for `INACTIVE` rows the toggle button displays **"Unblock"** (`c.status === 'ACTIVE' ? 'Block' : 'Unblock'`, `L181, L389`) and flips `INACTIVE → ACTIVE`.

---

### 5. FUNCTIONAL REVIEW

| Area | Status | Code Evidence & Findings |
|---|---|---|
| **Form Inputs** | **Incomplete (Observed)** | Exposes 8 fields (`name`, `phone`, `email`, `gstin`, `state`, `billingAddress`, `latitude`, `longitude` at `CustomersPage.tsx:52-65`). **Omits:** `creditLimit`, `creditDays`, `taxpayerType`, `pan`, `shippingAddress`, `shippingAddresses`, `notes`, `customFields`, `partyBank*`. |
| **Buttons / Actions** | **Defective (Observed)** | `+ Add`, `Edit`, `Verify`, `View Ledger`, `Block/Unblock` have mismatched permission checks against backend endpoints (see Section 12). |
| **Search (`q`)** | **Incomplete (Observed)** | `CustomerViewSet.get_queryset` (`views.py:186`) searches `name`, `phone`, and `gstin`, **omitting `email`** even though `Email` is a primary table column! Fires on every keystroke without debounce. |
| **Status Filter** | **Working (Observed)** | Filters by `All`, `ACTIVE`, `BLOCKED`, `INACTIVE` (`CustomersPage.tsx:236-247`). Backend does not validate invalid `status` query params. |
| **Sorting** | **Partial (Observed)** | Supports `name` (A–Z), `recent` (newest first), `balance` (highest outstanding first). No ascending/descending toggle. |
| **Pagination** | **Working (Observed)** | Server-side pagination (`10`, `25`, `50`, `100` per page). |
| **Client Validation** | **Flawed (Observed)** | 1) `canSave` (`L131-136`) only checks `name`, `phone`, and `state || gstin`; it leaves **Save** enabled when `gstin` is 1–14 chars or invalid, `email` is malformed, or only one coordinate (`latitude` xor `longitude`) is filled.<br>2) GSTIN input only shows inline error when `length === 15` (`L492`). |
| **Delete / Deactivate** | **Missing (Observed)** | Backend `CustomerViewSet.destroy` (`views.py:345-360`) safely archives referenced customers to `INACTIVE` or soft-deletes unreferenced ones, but no UI action exists (and `destroy` fails to protect `is_pos_walk_in`!). |
| **Portfolio KPIs & CSV Export** | **Missing (Observed)** | Unlike Money In (`ReceiptsPage.tsx`), `CustomersPage.tsx` has no summary KPI strip and no filtered CSV export button. |

---

### 6. DATA & STATE ANALYSIS

- **Data Consumed:**
  - **Observed:** Paginated `Customer` records (`GET /api/v1/customers/`) serialized with computed `outstanding` and `credit_exposure` (`serializers.py:166-167`, `views.py:336-343`), plus `GET /api/v1/collection-risk/` (`CustomersPage.tsx:101-105`) for `CreditHoldChip`.
- **Data Created & Modified:**
  - **Observed:** `POST /api/v1/customers/` (creates active customer), `PATCH /api/v1/customers/:id/` (updates fields or `status`), `POST /api/v1/customers/:id/verify-gstin/` (updates GSTIN verification fields).
- **Critical State & Cache Defects:**
  1. **GSTIN Verification State Not Reset on GSTIN Change (`Observed`):** In `backend/masters/views.py:292-327`, `CustomerViewSet.perform_update` manually sets attributes on the locked `Customer` row and saves it—bypassing `CustomerSerializer.update()`—and never resets `gstin_verification_status`, `gstin_legal_name`, `gstin_verified_at`, or `gstin_raw_payload` when `gstin` changes.
  2. **Cannot Clear GPS Coordinates Once Set (`Observed`):** In `CustomersPage.tsx:155-163`, when `latitude` and `longitude` are cleared (`coords === null`), the payload spreads `...(coords ? { latitude: coords.lat, longitude: coords.lng } : {})`, omitting both keys from the `PATCH` body so the database retains the old coordinates forever.
  3. **Corrupt Optimistic Cache Prepend & Missing Cross-Module Invalidation (`Observed`):** `saveMutation.onSuccess` (`CustomersPage.tsx:165-175`) blindly prepends the saved customer to the top of every `['customers']` query cache regardless of active `status`, `q`, or `sort` filters, and fails to invalidate `['customers-search']`, `['customers-receipt-lookup']`, `['customer', id]`, and `['customer-360', id]`.
  4. **Optimistic Concurrency (`version`) Only Checked on `PUT`, Ignored on `PATCH` (`Observed`):** `CustomerViewSet.update` (`views.py:278-290`) and `perform_update` (`views.py:302-317`) only check `version` when `not partial` (`PUT`). Because `updateCustomer` (`web/src/api/legacy/masters.ts:130-133`) uses `PATCH`, concurrent edits silently overwrite each other even if `version` is passed.

---

### 7. BUSINESS LOGIC

1. **GSTIN Prefix vs. State Desync (`Observed`):**
   - In `CustomersPage.tsx:497-505`, typing a valid 2-digit GSTIN prefix auto-fills `state` only if `!f.state` (`state: matchedState && !f.state ? matchedState : f.state`). Editing a GSTIN from `27...` (`Maharashtra`) to `29...` (`Karnataka`) leaves `state` as `Maharashtra`. Furthermore, `CustomerSerializer` (`backend/masters/serializers.py:204-216`) validates GSTIN format/checksum (`validate_gstin_checksum`) but **never validates that `state` matches `GST_STATE_CODES[gstin[:2]]`**.
2. **POS Walk-In Invariants Bypassed on `PATCH` and `DELETE` (`Observed`):**
   - `CustomerViewSet.set_pos_walk_in` (`views.py:241-275`) enforces that the walk-in customer (`is_pos_walk_in=True`) cannot have a `gstin` or positive `credit_limit`. However, `CustomerSerializer` allows `PATCH /customers/:id/` to set a `gstin`, `credit_limit`, or `status='BLOCKED'` on a walk-in customer, and `CustomerViewSet.destroy` (`views.py:345-357`) allows deleting or deactivating (`INACTIVE`) the walk-in customer!
3. **Duplicate GSTIN Error Handling (`Observed`):**
   - `Customer` has `UniqueConstraint(fields=['company', 'gstin'], condition=~Q(gstin=''))` (`models.py:150-153`). Because `CustomerSerializer` does not validate uniqueness before `save()`, duplicate GSTINs raise a raw `IntegrityError` translated into a generic message (`"This conflicts with an existing record (duplicate value)."`) without naming the conflicting customer.
4. **Outstanding Balance vs. Credit Exposure Transparency (`Observed`):**
   - `CustomerSerializer` computes both `outstanding` and `credit_exposure` on list (`views.py:341-342`), where `credit_exposure` nets out unallocated customer advances (`ledgers/services.py:508-535`). However, `CustomersPage.tsx` only displays `outstanding`, hiding unallocated advances and credit limits from the operator.

---

### 8. CROSS-SCREEN IMPACT

| Dependent Screen | Trigger on Customers Screen | Downstream Effect | Why It Matters |
|---|---|---|---|
| **Create Sales Invoice** (`NewInvoicePage.tsx`, `InvoicePartyPanel.tsx`) | Editing `gstin`, `state`, `taxpayerType`, `creditLimit`, `status`, or `customFields`. | Party autocomplete (`['customers-search']`), Place of Supply tax split (`CGST+SGST` vs `IGST`), credit-limit warnings, B2B/SEZ/Export invoice flags. | Desynced `state` vs `gstin` charges wrong tax; uninvalidated `['customers-search']` serves stale customer state in the invoice editor. |
| **POS Checkout** (`PosPage.tsx`) | Blocking/deleting `isPosWalkIn` customer or adding a GSTIN to it. | Walk-in counter billing and POS credit-limit banner. | Blocking or deleting the walk-in customer breaks retail counter checkout immediately. |
| **Money In / Receipts** (`ReceiptsPage.tsx`) | Creating/editing customers; `isPosWalkIn` flag. | Receipt customer lookup (`['customers-receipt-lookup']`) and walk-in 100% allocation rule (`OW-4`). | Stale lookup cache hides newly edited customer details. |
| **Sales Orders** (`SalesOrdersPage.tsx`) | `creditLimit`, `creditDays`, `status`. | Automated order credit-hold gates (`order_gates.py`). | Without `creditLimit` and `creditDays` in the Customer UI, credit gates cannot be configured per customer. |
| **Customer 360°** (`Customer360Page.tsx`) | Updating phone, email, GSTIN, or credit terms. | Header chips, WhatsApp reminder phone link, and Customer Value Index (`customer360Value.ts`). | Missing `['customer-360', id]` cache invalidation leaves stale contact/tax data on 360° view; lack of Edit button on 360° forces round-trip navigation. |
| **Customer Ledger & Aging** (`LedgerPage.tsx`, `ReceivablesAgingPage.tsx`) | Clicking **View Ledger**; updating customer master data. | `/reports/customer-ledger?customer=:id`. | Users without `canViewFinancialReports` hit Access Denied when clicking **View Ledger**. |

---

### 9. CROSS-MODULE / PRODUCT IMPACT

- **GST Filing & e-Invoicing (`backend/gst/`, `backend/reports/`) — `HIGH`:** `taxpayer_type` (`REGULAR`, `SEZWP`, `SEZWOP`, `EXPWP`, `EXPWOP`, `DEXP`, `COMPOSITION`, `UNREGISTERED`) and `gstin` + `state` directly determine GSTR-1 table placement. Missing `taxpayer_type` in UI and `state`/`gstin` desync corrupt GSTR-1 exports.
- **Credit Control & Collections (`backend/payments/`, `backend/sales/`) — `HIGH`:** `credit_limit` and `credit_days` power collection risk scoring and invoice due dates but cannot be set in `CustomersPage.tsx`.
- **RBAC & Subscription Enforcement (`web/src/utils/permissions.ts`, `backend/masters/views.py`) — `HIGH`:** Mismatched permission gates cause avoidable `403` errors across `SALES_STAFF`, `MANAGER`, `ACCOUNTANT`, and `AUDITOR` personas.
- **Database & API Performance (`backend/masters/views.py`) — `MEDIUM`:** `GET /api/v1/customers/?sort=balance` runs `bulk_customer_outstanding` **three times** per request (`get_queryset`, `get_serializer_context` for `outstanding`, and `get_serializer_context` inside `bulk_customer_credit_exposure`) and injects an unbounded `CASE WHEN pk=...` SQL expression across all customers with balances.

---

### 10. EDGE CASES

- **Data:**
  - **1–14 char GSTIN:** Leaves Save enabled and shows no field error until submit (`CustomersPage.tsx:131-136, 492`).
  - **Half-filled coordinates (`latitude` without `longitude`):** Leaves Save enabled, throws behind modal backdrop (`L552`).
  - **Clearing coordinates on Edit:** Sends `PATCH` without `latitude`/`longitude` keys, failing to clear DB values (`L155-163`).
  - **Out-of-range coordinates (`lat > 90`):** Passes frontend `Number.isFinite` check (`L111-118`), fails on backend behind modal backdrop.
  - **Searching by Customer Email:** Returns 0 matches because `CustomerViewSet.get_queryset` (`views.py:186`) omits `Q(email__icontains=q)`.
- **User Behavior:**
  - **Single-click Block on active/walk-in customer:** Immediately blocks without confirmation (`L381-390`).
  - **Rapid search typing:** Fires un-debounced API requests on every character (`L235`).
- **System Behavior:**
  - **GSTIN Verify in `STUB` mode (no live GSP credentials):** Returns `HTTP 200` with `status='UNVERIFIED'`, bumps `customer.version`, logs audit event, and gives the user zero feedback on why verification remained `"Unverified"` (`gstin_verify.py:75-85`, `views.py:360-366`).

---

### 11. ERROR & RECOVERY

- **Modal Save Errors (`Observed`):** Rendered at `CustomersPage.tsx:230` behind `<Dialog>`. The user does not know why Save failed unless they close the dialog (losing unsaved form data).
- **Duplicate GSTIN Conflict (`Observed`):** Returns generic DB integrity message instead of field-scoped error naming the existing customer with that GSTIN.
- **Permission Errors (`Observed`):** Triggered by UI buttons (`+ Add`, `Edit`, `Block`, `Verify`, `View Ledger`) that should have been hidden or disabled for the user's role.

---

### 12. SECURITY & PERMISSIONS

1. **`canMutate` Over-Permissive in UI (`CustomersPage.tsx:120` vs `views.py:172-173`) — `Observed`:**
   - UI uses `!isViewer(user.role)`; backend requires `CanCreateSales()`. `ACCOUNTANT` and `AUDITOR` roles with `canViewFinancialReports=true` and `canCreateSales=false` see mutation buttons and hit `403`.
2. **`verify_gstin` Restricted to `IsOwner` on Backend (`views.py:174-175` vs `CustomersPage.tsx:336`) — `Observed`:**
   - Backend requires `IsOwner()`; UI shows **Verify** to all `canMutate` users (`MANAGER`, `SALES_STAFF`, `ACCOUNTANT`).
3. **Missing `useSubscriptionGate` (`CustomersPage.tsx`) — `Observed`:**
   - Does not check `writesBlocked` from `useSubscriptionGate()`, unlike `ReceiptsPage.tsx:93-95`.
4. **Unconditional `View Ledger` Navigation (`CustomersPage.tsx:364`) — `Observed`:**
   - Not gated by `canViewFinancialReports(user)`.

---

### 13. CONSISTENCY

- **`InvoicePartyPanel.tsx` vs `CustomersPage.tsx` (`Observed`):** `InvoicePartyPanel.tsx:85-88` checks for duplicate GSTINs client-side and invalidates `['customers-search']`; `CustomersPage.tsx` does neither.
- **`ReceiptsPage.tsx` vs `CustomersPage.tsx` (`Observed`):** `ReceiptsPage.tsx` enforces `useSubscriptionGate()`, provides a filtered portfolio `summary/` strip, and supports `export/` CSV; `CustomersPage.tsx` has none of these.

---

### 14. ACCESSIBILITY & RESPONSIVENESS

- **Keyboard Navigation (`Observed`):** Clickable `<TableRow>` elements (`CustomersPage.tsx:307-315`) lack `tabIndex={0}`, `role="link"`, and `onKeyDown` (`Enter`/`Space`), making Customer 360° unreachable via keyboard.
- **Narrow Viewport / Mobile (`Observed`):** The 8-column table lacks responsive column visibility or horizontal overflow containment, cramping on 375px–768px screens.

---

### 15. AUTOMATION OPPORTUNITIES

1. **In-Modal "Verify & Autofill GSTIN" (`CUS-16`):** Allow verifying GSTIN inside the Create/Edit modal via `POST /api/v1/customers/lookup-gstin/` to auto-fill `name` (`legal_name`), `state`, and `taxpayerType` before saving.
2. **Always Sync `state` & `pan` from Valid GSTIN (`CUS-07`):** Automatically update `state` from `gstin.slice(0, 2)` and `pan` from `gstin.slice(2, 12)` whenever a valid GSTIN is entered.
3. **"Use Current Location" Geo-Helper (`CUS-16`):** Populate `latitude` and `longitude` via `navigator.geolocation` with one click.

---

### 16. REGRESSION RISK

- **Classification:** **`HIGH`**
- **Dependencies:** Sales Invoices, POS Checkout, Sales Orders (`order_gates.py`), Money In (`CustomerReceiptViewSet`), Customer 360°, Customer Ledger, AR Aging, Collection Risk, Field Sales, and GSTR-1 / e-Invoicing.

---

### 17. TEST SCENARIOS (HIGH-VALUE)

1. **B2B Customer Create & Edit with Credit + Tax Fields:** Set `creditLimit`, `creditDays`, `taxpayerType='SEZWP'`, `shippingAddress`, and `gstin='27AABCU9603R1ZN'` → verify persistence and state auto-selection (`Maharashtra`).
2. **GSTIN Prefix Change Updates State & Rejects Mismatch:** Change GSTIN prefix from `27...` to `29...` → verify `state` updates to `Karnataka`; attempt API `PATCH` with `gstin='29...'` and `state='Maharashtra'` → verify `400 Bad Request`.
3. **GSTIN Edit Resets Verification Status:** Verify a customer (`status='VALID'`), then edit `gstin` to a new number via `PATCH` → verify `CustomerViewSet.perform_update` resets `gstin_verification_status` to `'UNVERIFIED'` and clears `gstin_legal_name`.
4. **POS Walk-In Protection:** Attempt to block, delete/deactivate, or add a GSTIN / credit limit to the `isPosWalkIn=True` customer via UI, `PATCH`, and `DELETE` → verify UI disables them and backend returns `400 Bad Request`.
5. **Clear GPS Coordinates:** Edit a customer with existing `latitude`/`longitude`, clear both inputs, and save → verify DB stores `latitude=None, longitude=None`.
6. **Role Permission Matrix:** Verify button visibility and backend response for `OWNER`, `MANAGER`, `SALES_STAFF` (`canViewFinancialReports=false`), `ACCOUNTANT` (`canCreateSales=false`), and `VIEWER`, plus `writesBlocked=true`.
7. **In-Modal Error Rendering & Optimistic Locking:** Submit duplicate GSTIN or stale `version` on `PATCH` → verify error alert renders *inside* `<DialogContent>` without losing form state.

---

### 18. TOP PROBLEMS & RELEASE MAP

**Release map (replaces the old phase-by-score view):**

| Release | Theme | Items | Gate to ship |
|---|---|---|---|
| **R1** | Data integrity, permissions, visible errors | `CUS-21` (shared GSTIN helper), `CUS-22` (backfill report), `CUS-04`, `CUS-05`, `CUS-06`, `CUS-07`, `CUS-10`, `CUS-02`, `CUS-03`, `CUS-08`, `CUS-26` | Backend tests green; backfill report reviewed; feature flag `CUSTOMER_STRICT_VALIDATION` on in staging |
| **R2** | Form completeness, cache, UX | `CUS-01`, `CUS-23`, `CUS-09`, `CUS-12`, `CUS-13`, `CUS-14`, `CUS-11`, `CUS-19` (search/status part), `CUS-17` step 1 (shared `CustomerFormDialog`) | Vitest green; manual role-matrix pass |
| **R3** | Enhancements | `CUS-15`, `CUS-16`, `CUS-17` (rest), `CUS-18`, `CUS-19` (stub notice), `CUS-20`, `CUS-24`, `CUS-25`, `CUS-27` | a11y no-new-violations vs baseline; OpenAPI regenerated |

Effort sizing and owners are to be filled in at kickoff (open item). Each release is independently shippable and revertable; strict backend validations (`CUS-05/07/10`) sit behind `CUSTOMER_STRICT_VALIDATION` so they can be disabled without a deploy rollback.



| Priority | ID | Problem / Capability Gap | Impact | Target Phase |
|---|---|---|---|---|
| **P0** | **CUS-01** | Core credit & GST fields (`creditLimit`, `creditDays`, `taxpayerType`, `pan`, `shippingAddress`, `notes`) missing from UI. | Credit gates and GSTR-1 classifications cannot be configured from Customer Master. | Core (see release map) |
| **P0** | **CUS-02** | Modal save errors render on the background page behind `<Dialog>`, and stale errors are never cleared on open. | Users cannot see why Save failed without closing the modal and losing their typed data. | Core (see release map) |
| **P0** | **CUS-03** | Permission & subscription gate mismatches (`canMutate`, `Verify GSTIN`, `View Ledger`, `useSubscriptionGate`). | Deterministic `403 Forbidden` and Access Denied traps for `SALES_STAFF`, `MANAGER`, `ACCOUNTANT`, `AUDITOR`. | Core (see release map) |
| **P0** | **CUS-04** | POS Walk-In customer (`isPosWalkIn`) can be blocked, deleted/deactivated, or assigned a GSTIN via Edit. | Blocking/deleting walk-in breaks POS counter checkout; adding GSTIN violates walk-in invariants. | Core (see release map) |
| **P1** | **CUS-05** | Editing or clearing `gstin` does not reset `gstin_verification_status` or `gstin_legal_name` (`perform_update` bypasses `serializer.update`). | Modified GSTIN falsely retains `'VALID'` status and old taxpayer's legal name. | Core (see release map) |
| **P1** | **CUS-06** | `gstinStatusColor()` maps `'VERIFIED'` instead of `'VALID'` and omits `'CANCELLED'`/`'SUSPENDED'`. | Verified `'VALID'` GSTINs show amber warning; cancelled/suspended GSTINs show amber instead of red error. | Core (see release map) |
| **P1** | **CUS-07** | `state` does not update when GSTIN prefix changes and backend does not enforce `gstin[:2] == state`. | Wrong intra/inter-state tax (`CGST+SGST` vs `IGST`) on downstream invoices. | Core (see release map) |
| **P1** | **CUS-08** | Clearing `latitude`/`longitude` on Edit omits keys from `PATCH` instead of sending `null`; out-of-range lat/lng not checked in UI. | Saved GPS coordinates can never be removed via UI. | Core (see release map) |
| **P1** | **CUS-09** | Incomplete React Query invalidation, unfiltered optimistic prepend, and `version` locking ignored on `PATCH`. | Stale party data in Invoice, Receipt, and 360° screens; silent concurrent overwrites. | Core (see release map) |
| **P2** | **CUS-10** | Duplicate GSTIN raises generic DB `IntegrityError` instead of naming the conflicting customer. | Operator cannot tell which existing customer already has that GSTIN. | Core (see release map) |
| **P2** | **CUS-11** | `sort=balance` computes `bulk_customer_outstanding` 3 times per request and builds an unbounded SQL `CASE WHEN`. | Slow response times as customer count grows. | Core (see release map) |
| **P2** | **CUS-12** | Unconfirmed 1-click Block, `INACTIVE` rows showing "Unblock", and missing Delete/Deactivate UI action. | Accidental customer blocks and confusing lifecycle states. | Core (see release map) |
| **P3** | **CUS-13** | Sort control mislabelled as `"Filter"` (`common.filter`) and hardcoded English strings in `CustomersPage.tsx`. | Confusing toolbar labels and broken Hindi (`hi`) localization parity. | Core (see release map) |
| **P3** | **CUS-14** | Clickable table rows lack keyboard accessibility (`tabIndex`, `onKeyDown`) and search input lacks debounce. | Keyboard users cannot open Customer 360°; excessive API calls while typing search queries. | Core (see release map) |
| **Enh.** | **CUS-15** | **Portfolio Summary KPI Strip (`summary/`) & Filtered CSV Export (`export/`).** | Gives AR/Owners instant visibility into Total Active, On Credit Hold, Gross Outstanding, and Unallocated Advances + 1-click CSV export. | Enhancement (R3) |
| **Enh.** | **CUS-16** | **In-Modal "Verify & Autofill GSTIN" (`lookup-gstin/`), Custom Fields (`partyCustomFieldDefs`), Multiple Shipping Addresses & Geo-Location Helper.** | Shortens B2B onboarding and brings parity with `NewInvoicePage` party custom fields and multi-shipping addresses. | Enhancement (R3) |
| **Enh.** | **CUS-17** | **Full Lifecycle Controls: Archive/Delete Action, Owner "Set as POS Walk-In" UI Action & Direct Edit Modal on `Customer360Page`.** | Completes all CRUD + lifecycle flows across both `CustomersPage` and `Customer360Page` without dead ends. | Enhancement (R3) |
| **Enh.** | **CUS-18** | **Receivable & Advance Transparency in Table (`Outstanding` + `Advance Held` / `Credit Limit` Progress) & `PATCH` Optimistic Locking.** | Makes Books-ON vs Books-OFF receivable vs advance positions crystal clear on every row and prevents concurrent `PATCH` overwrites. | Enhancement (R3) |
| **Enh.** | **CUS-19** | **Backend Search & Filter Hardening (`email` in `q`, `q` length cap, `status` choice validation, actionable stub GSTIN notice).** | Searching by email works; invalid query params return clean `400` errors; stub GSP mode explains why status stayed Unverified. | Enhancement (R3) |
| **Enh.** | **CUS-20** | **No New `axe-core` Violations vs Baseline, Accessible Name Link + Dialog Focus Restoration, 375px Responsive Polish & OpenAPI Type Sync.** | Targets WCAG AA keyboard/screen-reader behaviour, no mobile horizontal overflow, and OpenAPI contract parity. | Enhancement (R3) |
| **P1** | **CUS-21** | Shared GSTIN helper (`masters/gstin_rules.py`): reset, state/PAN, duplicates in one place. | Stale `VALID` status and mismatches cannot come back through another write path. | R1 (done) |
| **P1** | **CUS-22** | Legacy-data audit command `customers_audit`. | Shows which stored rows the strict rules would reject on edit. | R1 (done) |
| **P1** | **CUS-23** | Credit terms limited to owner/manager. | Sales staff can no longer raise credit limits. | R2 (done) |
| **P2** | **CUS-24** | Customer change history on Customer 360°. | Who changed credit terms, GSTIN or status, and when. | R3 (done) |
| **P2** | **CUS-25** | Customer import uses the same GSTIN/state rules. | Imports no longer store stale state or PAN. | R3 (done) |
| **P1** | **CUS-26** | Server-side phone validation (coordinates were already validated). | API clients get the form's rules. | R1 (done) |
| **P3** | **CUS-27** | Observability, privacy and status semantics. | Log events and `docs/CUSTOMERS_STATUS_SEMANTICS.md`. | R3 (done) |

---

### 19. MOST IMPORTANT CHANGES (TOP 3)

1. **Complete the Customer Master Form & Protect POS Walk-In (`CUS-01` + `CUS-04` + `CUS-16`):** Expose `creditLimit`, `creditDays`, `taxpayerType`, `pan`, `shippingAddress`, `shippingAddresses`, `notes`, and `customFields` in the Customer modal (and on `Customer360Page`), add in-modal GSTIN autofill, and protect the `isPosWalkIn` customer from being blocked, deleted, or assigned a GSTIN.
2. **Enforce GSTIN & Tax-State Integrity End-to-End (`CUS-05` + `CUS-06` + `CUS-07` + `CUS-10`):** Reset verification fields inside `perform_update` when `gstin` changes, enforce `gstin[:2]` ↔ `state` consistency in both UI and `CustomerSerializer`, fix the `VALID`/`CANCELLED`/`SUSPENDED` chip colors, and return a clear duplicate-GSTIN error naming the existing customer.
3. **Fix Modal Error Visibility & Align Role/Subscription Permissions (`CUS-02` + `CUS-03`):** Render errors inside `<DialogContent>`, tighten inline validation (`canSave`), gate writes on `canCreateSales(user) && !writesBlocked`, align `verify_gstin` permissions, and guard `View Ledger` with `canViewFinancialReports(user)`.

---

### 20. EXIT CRITERIA (replaces numeric scorecard)

Per-dimension numeric scores were unmeasured estimates and have been removed. A release is "done" when its checklist in Part III passes. Dimensions to evidence (not score): purpose clarity, UX, cognitive load, flow, functionality, business logic, data/state, error handling, cross-product integration, consistency, accessibility. Accessibility is gated as **no new `axe-core` violations versus a recorded baseline** for the list page and dialogs (existing violations are logged as backlog, not blockers).

---

## Part II: Detailed Implications & Engineering Implementation Plan

### Architecture & Execution Order

No column changes are needed (`credit_limit`, `credit_days`, `taxpayer_type`, `pan`, `shipping_address`, `shipping_addresses`, `notes`, `custom_fields`, `is_pos_walk_in`, `version` already exist on `masters.Customer`). **Data, however, needs attention:** `CUS-22` produces a report/backfill for existing customers with stale `VALID` status, state/GSTIN mismatches, or inconsistent walk-in flags before strict validation is enabled.

Cross-cutting rules for every phase:
- Re-verify cited file/line numbers against HEAD before starting an item (the files changed in recent commits).
- Strict backend validations (`CUS-05/07/10`) are gated by feature flag `CUSTOMER_STRICT_VALIDATION`.
- Filter logic (`status`, `q`, `is_pos_walk_in`) is extracted once into `CustomerViewSet._filtered_queryset()` and reused by `list`, `summary/`, `export/` (do not copy it three times).
- Every new endpoint needs: permission class, company-scoped queryset (tenant-isolation test), audit entry where it exposes or changes data, and OpenAPI docs.

```text
R1  Backend integrity & permissions (backend/masters/) + minimal UI fixes
  ├─ CUS-21: shared `apply_gstin(customer, gstin)` helper (reset verification, derive state/PAN, duplicate check) used by serializer create/update, perform_update, verify, import
  ├─ CUS-22: legacy-data report/management command (stale VALID, state mismatch, duplicate-looking GSTINs, walk-in anomalies)
  ├─ CUS-04: walk-in guard in serializer (PATCH and PUT) AND destroy
  ├─ CUS-05: verification reset via CUS-21 inside perform_update
  ├─ CUS-07: state<->GSTIN validation, only when gstin or state is in the payload
  ├─ CUS-10: duplicate GSTIN error naming the customer
  ├─ CUS-26: backend validation of coordinates, phone, email
  ├─ CUS-03: permissions (verify_gstin change needs cost review, see item)
  └─ CUS-02, CUS-06, CUS-08: modal errors, chip colours, clearable coordinates
        |
R2  Form completeness, cache, UX
  ├─ CUS-17 step 1: extract reusable <CustomerFormDialog /> FIRST, then build CUS-01/CUS-23 inside it
  ├─ CUS-01, CUS-23 (credit-term permissions), CUS-09, CUS-12, CUS-13, CUS-14
  └─ CUS-11 (balance sort rewrite), CUS-19 search/status part
        |
R3  Enhancements & audit/observability
  └─ CUS-15, CUS-16, CUS-17 (rest), CUS-18, CUS-19 stub notice, CUS-20, CUS-24, CUS-25, CUS-27
        |
OpenAPI sync (docs/openapi-snapshot.json, web/src/api/openapi-types.ts) at the end of each release that changes the API.
```


---

### Detailed Core Work Items (`CUS-01` .. `CUS-14`)

#### `CUS-01` (P0) — Expose Credit Controls, GST Classification, Shipping Address & Notes in Customer UI
- **Files:** `web/src/pages/sales/CustomersPage.tsx`, `web/src/pages/sales/Customer360Page.tsx`, `web/src/api/legacy/masters.ts`, `web/src/types/domain.ts`
- **Plan:**
  1. Map `creditLimit`, `creditDays`, `creditExposure`, `taxpayerType`, `pan`, `shippingAddress`, `shippingAddresses`, `notes`, `customFields`, `isPosWalkIn`, and `version` in `mapCustomer()`, `createCustomer()`, and `updateCustomer()`.
  2. Add structured inputs in the Customer Create/Edit dialog for `taxpayerType`, `pan`, `creditLimit`, `creditDays`, `shippingAddress`, and `notes`.
  3. Display `creditLimit` (when `> 0`) and net `creditExposure` under `Outstanding` in the table.

#### `CUS-02` (P0) — Render Modal Errors Inside Dialog & Tighten Inline Form Validation
- **Files:** `web/src/pages/sales/CustomersPage.tsx`
- **Plan:**
  1. Render `<HelpErrorAlert message={modalError} />` **inside `<DialogContent>`** so errors are never hidden behind the modal backdrop.
  2. Reset `modalError` in `openCreate()`, `openEdit()`, and Dialog `onClose`.
  3. Show inline GSTIN validation error whenever `Boolean(form.gstin.trim()) && !isValidGstin(form.gstin)` (catching 1–14 char partial GSTINs immediately).
  4. Require valid GSTIN (if non-empty), valid email (if non-empty), and valid paired coordinates (`-90 <= lat <= 90`, `-180 <= lng <= 180`) in `canSave`.

#### `CUS-03` (P0) — Align Role Permissions (`canCreateSales`, `canViewFinancialReports`, `verify_gstin`) & Subscription Gate
- **Files:** `web/src/pages/sales/CustomersPage.tsx`, `backend/masters/views.py`
- **Plan:**
  1. Replace `const canMutate = !!user && !isViewer(user.role)` with `const canMutate = canCreateSales(user) && !writesBlocked` using `useSubscriptionGate()`.
  2. Guard **View Ledger** button with `canViewFinancialReports(user)`.
  3. **Decide, don't assume:** `verify_gstin` is `IsOwner` today (`views.py:174-175`; it is not in `_MUTATE_ACTIONS`). It calls a paid GSP and stores `gstin_raw_payload`. First confirm with the founder whether owner-only was deliberate (cost control). Default decision: widen to `CanCreateSales()` **with** a per-company throttle (e.g. 30/hour/user) and an audit entry per call; otherwise hide **Verify** in the UI for non-owners. Do not change the permission without recording the decision here.
  4. Note `pos_walk_in` (cashier get-or-create) is handled separately at `views.py:172`; keep it in the permission test matrix.

#### `CUS-04` (P0) — Protect the POS Walk-In Customer (`isPosWalkIn`) Across UI, `PATCH` & `DELETE`
- **Files:** `backend/masters/serializers.py`, `backend/masters/views.py`, `web/src/pages/sales/CustomersPage.tsx`
- **Plan:**
  1. In `CustomerSerializer.validate()`, if the customer is `is_pos_walk_in=True`, reject any non-empty `gstin`, `credit_limit > 0`, or `status != 'ACTIVE'`.
  2. In `CustomerViewSet.destroy()` (`backend/masters/views.py:345-357`), reject deleting or deactivating a customer with `is_pos_walk_in=True` (`raise BusinessRuleError("The POS walk-in party cannot be deleted or deactivated. Assign another walk-in party first.")`).
  3. In `CustomersPage.tsx`, render a `"POS Walk-In"` badge, disable **Block** and **Delete** on that row, and disable `gstin` and `creditLimit` fields when editing the walk-in customer.

#### `CUS-05` (P1) — Reset GSTIN Verification Metadata When `gstin` Changes in `perform_update`
- **Files:** `backend/masters/views.py`, `backend/masters/serializers.py`
- **Code Truth Discovered:** `CustomerViewSet.perform_update` (`backend/masters/views.py:292-327`) reloads the `Customer` row with `select_for_update()` and applies `serializer.validated_data` directly onto `locked`, **bypassing `CustomerSerializer.update()`**.
- **Plan:**
  - Implement the reset once, in the shared `apply_gstin()` helper (`CUS-21`), and call it from `perform_update()`, `CustomerSerializer.create()`/`update()`, and any import path, so no write path can leave stale `VALID` status. In `perform_update()`, compare incoming `gstin` against `(locked.gstin or "")`. Whenever `gstin` changes, set:
    ```python
    locked.gstin_verification_status = "UNVERIFIED"
    locked.gstin_legal_name = ""
    locked.gstin_verified_at = None
    locked.gstin_raw_payload = {}
    ```
  - Also fix `CustomerViewSet.destroy` (`views.py:345-357`): the INACTIVE path saves without a row lock, `version` bump, or `updated_at`, so optimistic locking cannot see archive operations. Lock the row (`select_for_update`), bump `version`, and include `updated_at` in `update_fields`.

#### `CUS-06` (P1) — Fix GSTIN Verification Chip Colors (`VALID`, `CANCELLED`, `SUSPENDED`) & Row-Scoped Verify Spinner
- **Files:** `web/src/pages/sales/CustomersPage.tsx`
- **Plan:**
  - Map `'VALID' | 'VERIFIED'` → `'success'`, `'INVALID' | 'FAILED' | 'CANCELLED' | 'SUSPENDED'` → `'error'`, and `'UNVERIFIED'` → `'warning'`.
  - Scope button loading state to the active row (`verifyGstinMutation.isPending && verifyGstinMutation.variables === c.id`).

#### `CUS-07` (P1) — Keep `state` & `pan` Synchronized with GSTIN in UI & Backend
- **Files:** `web/src/pages/sales/CustomersPage.tsx`, `backend/masters/serializers.py`
- **Plan:**
  1. In `CustomersPage.tsx`, whenever `gstin` has a valid 2-digit prefix in `GST_STATE_CODES`, always update `state: matchedState` (even if `f.state` was previously non-empty), and auto-fill `pan: val.slice(2, 12)` when a valid 15-char GSTIN is entered.
  2. In `CustomerSerializer.validate()`, when `gstin` is non-empty, derive `expected_state = GST_STATE_CODES.get(gstin[:2])`. Auto-populate `state` if blank, or raise `ValidationError({'state': ...})` if `state` conflicts with `expected_state`.
  3. **Legacy-data safety:** run this validation **only when `gstin` or `state` is present in the payload**. A PATCH of an unrelated field (e.g. phone) on a legacy customer whose state already mismatches must still succeed. Enable behind `CUSTOMER_STRICT_VALIDATION` and only after the `CUS-22` report has been reviewed.
  4. **Special GSTIN prefixes:** verify `GST_STATE_CODES` covers 96 (foreign), 97 (other territory), and the merged UT codes (26/38 Dadra & Nagar Haveli and Daman & Diu); skip the mismatch rule for codes with no single state mapping instead of rejecting valid customers.

#### `CUS-08` (P1) — Fix Clearing GPS Coordinates (`latitude` / `longitude`) & Range Validation
- **Files:** `web/src/pages/sales/CustomersPage.tsx`, `web/src/api/legacy/masters.ts`
- **Plan:**
  - Send `{ latitude: coords ? coords.lat : null, longitude: coords ? coords.lng : null }` on update so clearing coordinate inputs writes `NULL` to the database, and enforce `-90 <= lat <= 90` and `-180 <= lng <= 180` client-side.

#### `CUS-09` (P1) — Fix React Query Cache Invalidation & Optimistic Concurrency (`version`)
- **Files:** `web/src/pages/sales/CustomersPage.tsx`, `web/src/api/legacy/masters.ts`, `backend/masters/views.py`
- **Plan:**
  1. Remove the blind `setQueriesData` prepend on `['customers']` and invalidate `['customers']`, `['customers-summary']`, `['customers-search']`, `['customers-receipt-lookup']`, `['customer', id]`, and `['customer-360', id]`.
  2. Send `version` in `updateCustomer` (`PATCH`) and check `if "version" in request.data:` inside `CustomerViewSet.update()` / `perform_update()` so stale `PATCH` requests also return `409 Conflict` instead of silently overwriting concurrent edits.
  3. **Semantics to preserve:** `perform_update` intentionally lets concurrent PATCHes of *different* fields merge (see its docstring). Therefore `version` stays **optional** on `PATCH` (API/integration clients keep working); only requests that send it are checked. The web client always sends it.
  4. **409 handling in the UI:** on `409`, show an in-dialog "This customer was changed by someone else" notice with a **Reload latest** action that refetches `['customer', id]`, re-applies the dialog to the fresh `version`, and keeps the user's typed values visible. Add a test for list-dialog vs 360°-dialog collisions.

#### `CUS-10` (P2) — Friendly Duplicate GSTIN Validation Naming the Conflicting Customer
- **Files:** `backend/masters/serializers.py`
- **Plan:** Validate `(company, gstin)` uniqueness in `CustomerSerializer.validate_gstin()` and return `f"GSTIN {value} is already registered to customer '{existing.name}'."`.

#### `CUS-11` (P2) — Deduplicate `bulk_customer_outstanding` Calls on `GET /api/v1/customers/`
- **Files:** `backend/masters/views.py`, `backend/ledgers/services.py`
- **Plan:**
  1. Cache `outstanding_by_id` on the view/request and pass `outstanding_map` into `LedgerService.bulk_customer_credit_exposure(company, outstanding_map=...)` so `bulk_customer_outstanding` runs only once per request.
  2. **Remove the unbounded `Case(When(pk=...))`** (it grows with every customer that has a balance). Preferred: annotate balance via a subquery/aggregate join on the ledger tables. Fallback if the ledger cannot be expressed as a subquery: order only the filtered id list in Python by the cached map, then paginate that id list and fetch the page.
  3. Add a performance test/benchmark (e.g. 5,000 customers, `sort=balance`, assert query count and a time budget) rather than a claim.

#### `CUS-12` (P2) — Confirmation Dialog on Block/Deactivate & Distinct `INACTIVE` Status Handling
- **Files:** `web/src/pages/sales/CustomersPage.tsx`
- **Plan:** Add a confirmation dialog before blocking a customer, and show distinct badges/actions for `BLOCKED` (`"Unblock"`) vs `INACTIVE` (`"Activate"`).

#### `CUS-13` (P3) — Fix Sort Dropdown Label & Complete English/Hindi (`en.ts` / `hi.ts`) Localization
- **Files:** `web/src/pages/sales/CustomersPage.tsx`, `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`
- **Plan:** Change Sort label from `common.filter` to `common.sortBy` and localize all table headers, modal fields, tooltips, and validation strings in `en.ts` and `hi.ts`.

#### `CUS-14` (P3) — Keyboard Row Accessibility, Search Debounce & Responsive Columns
- **Files:** `web/src/pages/sales/CustomersPage.tsx`
- **Plan:** Add `250ms` search debounce, responsive column visibility, and keyboard-accessible navigation to Customer 360°.

---

### Detailed Enhancement Work Items (`CUS-15` .. `CUS-20`) — Release R3

These are feature additions rather than defect fixes: workflow closure, less manual typing, portfolio-level visibility, strict query validation, and accessibility parity with `Money In` (`ReceiptsPage.tsx`) and `Sales Invoice` (`NewInvoicePage.tsx`). Ship after R1/R2 are stable.

---

#### `CUS-15` (R3) — Portfolio Summary KPI Strip (`summary/`) & Filtered CSV Export (`export/`)

- **Problem:**
  - Unlike `ReceiptsPage.tsx` (`OW-2` & `OW-12`), `CustomersPage.tsx` shows individual paginated rows without telling the owner/accountant the **total receivable balance across the filtered customer set**, how many customers are currently **on Credit Hold / Over Credit Limit**, or how much **Unallocated Advance** is held.
  - There is also no way to export the filtered customer list (e.g., all `BLOCKED` customers or customers sorted by `balance`) to CSV for collection meetings or audit review.
- **Implementation Plan:**
  0. **Security:** `summary/` and `export/` expose the whole party master (phone, email, GSTIN, balances). Require `canViewFinancialReports`-equivalent backend permission (not just `CanCreateSales`), write an audit entry for every export, include a tenant-isolation test, and when the 20,000-row cap truncates, say so in a response header and a UI warning (no silent truncation). Use the shared `_filtered_queryset()`.
  1. **Backend (`backend/masters/views.py`):**
     - Add `@action(detail=False, methods=["get"], url_path="summary")`:
       - Applies the same `status` and `q` filters as `list`.
       - Computes and returns `{ total_count, active_count, blocked_count, over_credit_limit_count, total_outstanding, total_unallocated_advance, net_credit_exposure }`.
     - Add `@action(detail=False, methods=["get"], url_path="export")`:
       - Streams a formula-injection-safe (`csv_safe`) CSV of the filtered queryset (capped at 20,000 rows), including `Name`, `Phone`, `Email`, `GSTIN`, `GSTIN Status`, `Taxpayer Type`, `State`, `Status`, `Credit Limit`, `Credit Days`, `Outstanding`, and `Credit Exposure`.
  2. **Frontend (`web/src/pages/sales/CustomersPage.tsx`):**
     - Render a 4-card KPI strip above the filter bar: **Active Customers**, **Total Outstanding**, **Advances Held / Net Exposure**, and **Over Credit Limit / Blocked**.
     - Add an **Export CSV** button in the filter bar respecting active `q`, `status`, and `sort` parameters.

---

#### `CUS-16` (R3) — In-Modal "Verify & Autofill GSTIN" (`lookup-gstin/`), Custom Fields (`partyCustomFieldDefs`), Multi-Shipping Addresses & Geo Helper

- **Problem:**
  1. Currently, an operator onboarding a B2B customer must manually type the legal name, state, and address, save the customer, and *only then* click **Verify** in the table row.
  2. `NewInvoicePage.tsx` (`ACT-27`) and `CustomerSerializer` (`serializers.py:140-202`) support company-configured party custom fields (`company.partyCustomFieldDefs` → `Customer.custom_fields`, e.g., Drug License No., FSSAI No.) and multiple `shippingAddresses` (`CustomerAddress`), yet `CustomersPage.tsx` cannot view or edit either of them!
  3. Entering GPS coordinates requires looking up decimal latitude/longitude externally.
- **Implementation Plan:**
  0. **Abuse/cost control:** `lookup-gstin/` calls a paid external provider. Add a per-user/company throttle, an audit entry, short-TTL caching per GSTIN, and a defined response when the provider is in STUB mode or errors (explicit `provider_unavailable` status, never a silent empty result). Tied to the `CUS-03` verify decision.
  1. **In-Modal GSTIN Lookup (`POST /api/v1/customers/lookup-gstin/`):**
     - Add a collection action on `CustomerViewSet` (`CanCreateSales`) that takes `{ gstin }`, validates the checksum, calls `get_gstin_provider().lookup(gstin)`, and returns `{ gstin, status, legal_name, state, pan, error }`.
     - Inside the Customer Create/Edit modal, place a **"Verify & Autofill"** button next to the GSTIN input. When clicked on a valid 15-char GSTIN, it auto-fills `name` (if empty, or offers 1-click apply of `legal_name`), `state`, `pan`, and `taxpayerType`.
  2. **Custom Fields & Shipping Addresses Parity:**
     - Read `company.partyCustomFieldDefs` (same as `InvoicePartyPanel.tsx`) and render inputs for each defined custom field inside the Customer modal (`form.customFields`).
     - Support adding/editing structured `shippingAddresses` (`label`, `line1`, `city`, `state`, `pincode`, `isDefault`) in an expandable section.
  3. **One-Click Geo-Location Helper:**
     - Add a **"Use Current Location"** button (`navigator.geolocation.getCurrentPosition`) next to the Latitude/Longitude fields for field sales staff.

---

#### `CUS-17` (R2 step 1 / R3) — Complete Lifecycle Controls: Archive/Delete UI, Owner "Set as POS Walk-In" & Direct Edit Modal on `Customer360Page`

- **Problem:**
  1. `Customer360Page.tsx` is a read-only header with transaction tabs; operators inspecting a customer's 360° profile cannot edit the customer without navigating back to `/sales/customers`.
  2. `CustomerViewSet` has a tested `destroy()` endpoint (which soft-deletes unreferenced customers or marks referenced ones `INACTIVE`) and `set_pos_walk_in()` endpoint, but neither is reachable from the UI.
- **Implementation Plan:**
  1. **(R2, do first — before building CUS-01/CUS-23 inside the page)** Extract the Customer Create/Edit modal into a reusable `<CustomerFormDialog />` component used by both `CustomersPage.tsx` and `Customer360Page.tsx` so clicking **Edit Customer** on `Customer360Page` opens the dialog in-place and immediately refreshes `['customer', id]` and `['customer-360', id]`.
  2. Add an **Archive / Delete** action in the row menu (and `Customer360Page`) with a confirmation dialog; if the backend responds with `status=200` (`"marked Inactive instead of deleting"`), show an informative notice and refresh the list.
  3. For `OWNER` users (`isOwner(user)`), provide a **"Set as POS Walk-In"** action on eligible customers (active, no GSTIN, zero credit limit) wired to `POST /api/v1/customers/set-pos-walk-in/`.

---

#### `CUS-18` (R3) — Receivable, Credit Exposure & Advance Transparency + `PATCH` Optimistic Concurrency

- **Problem:**
  - When a customer has paid an unallocated advance receipt, `outstanding` (in Books-OFF mode) shows gross unpaid invoices while `creditExposure` nets out the advance. Hiding `creditExposure` and `creditLimit` in the table makes credit-hold badges look contradictory.
  - `CustomerViewSet.update` (`views.py:278-290`) only checks `version` on `PUT`, ignoring `version` on `PATCH`.
- **Implementation Plan:**
  1. In the `Outstanding` column of `CustomersPage.tsx`:
     - Show `formatCurrency(c.outstanding)` as the primary figure.
     - If `c.creditLimit > 0`, show a subtle caption `Limit: ₹X` (highlighted in red/amber if `c.creditExposure > c.creditLimit`).
     - If `c.creditExposure < c.outstanding`, show a green/info sub-caption `Net exposure: ₹Y (after advance)`.
  2. In `CustomerViewSet.update()` and `perform_update()`, enforce optimistic concurrency whenever `"version" in request.data` (both `PUT` and `PATCH`), returning HTTP `409 Conflict` with the latest serialized record if `int(request.data["version"]) != locked.version`.

---

#### `CUS-19` (R3) — Backend Search & Query Filter Hardening (`email` in `q`, `q` Cap, `status` Validation, Stub GSP Notice)

- **Problem:**
  1. `CustomerViewSet.get_queryset` (`views.py:186`) filters `Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q)`—**omitting `email__icontains=q`** despite `Email` being a primary column in the table!
  2. Passing an invalid `status=FOO` query param silently returns 0 rows instead of `400 Bad Request`, and `q` has no length cap.
  3. In `STUB` GSTIN provider mode, `verify_gstin` returns HTTP `200` with `gstin_verification_status='UNVERIFIED'` and no top-level warning explaining that live GSP credentials are not configured.
- **Implementation Plan:**
  1. Update `CustomerViewSet.get_queryset()`:
     - Validate `status_filter` against `Customer.Status.values` (confirm it includes `INACTIVE`, which `destroy` sets; raise `ValidationError({'status': 'Invalid status filter.'})` on unknown values).
     - Cap `q` at 100 characters (`q = q.strip()[:100]`) and include `Q(email__icontains=q)`.
  2. In `verify_gstin` (`views.py:360-366`), include `"verification_error": result.error` in the response payload when `result.error` is present so the UI can display a clear warning banner/toast (`"Live GSTIN verification provider is not configured..."`).

---

#### `CUS-20` (R3) — Automated `axe-core` A11y Pass, Focus Restoration, 375px Mobile Layout & OpenAPI Sync

- **Implementation Plan:**
  1. Render the Customer Name cell as a semantic keyboard-focusable link (`<Link component={ RouterLink } to={`/sales/customers/${c.id}`}>`) with an accessible `aria-label`, and restore focus to the triggering button when closing the Create/Edit or Block/Delete dialogs.
  2. Wrap the table in a responsive container and hide non-essential columns (`Email`, `GSTIN status`, `State`) on `xs` viewports while displaying State and GSTIN status as compact sub-chips under the customer name on mobile so 375px screens have zero horizontal overflow.
  3. Add `@axe-core/react` / `vitest-axe` checks in `CustomersPage.test.tsx` covering the main table, Create/Edit dialog, and Block confirmation dialog.
  4. Document `summary/`, `export/`, and `lookup-gstin/` in OpenAPI and regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts`.

---

### Gap Work Items (`CUS-21` .. `CUS-27`) — added after review

#### `CUS-21` (P1, R1) — Shared `apply_gstin()` Helper
- **Files:** `backend/masters/services.py` (new or existing), `backend/masters/serializers.py`, `backend/masters/views.py`, `backend/core/services/gstin_verify.py`
- **Plan:** One function owns GSTIN side effects: normalise, checksum, duplicate check (naming the customer, `CUS-10`), derive/validate `state` (`CUS-07`), derive `pan`, and reset verification metadata when the value changes (`CUS-05`). Called from serializer `create`/`update`, `perform_update`, verify, and any import. Unit-test it directly.

#### `CUS-22` (P1, R1) — Legacy Data Report / Backfill
- **Plan:** Management command `customers_audit` (read-only by default, `--fix` for safe repairs) listing, per company: `VALID` status with changed/blank GSTIN, `gstin[:2]` vs `state` mismatches, GSTINs duplicated ignoring case/whitespace, multiple or missing walk-in rows, walk-ins with GSTIN/credit limit/non-ACTIVE status. Reviewed before `CUSTOMER_STRICT_VALIDATION` is enabled in production.

#### `CUS-23` (P1, R2) — Credit-Term Permissions
- **Plan:** `credit_limit` and `credit_days` drive holds, so restrict edits to `OWNER`/`MANAGER` (decision to confirm); `SALES_STAFF` sees them read-only. Enforce in the serializer (reject changes from other roles with a clear message), hide/disable in the UI, and audit credit-term changes with old/new values.

#### `CUS-24` (P2, R3) — Customer Change History
- **Plan:** Show a "History" tab/section on `Customer360Page` from existing audit rows (who changed credit limit, GSTIN, status, when), reusing `AuditService` entries; no new table.

#### `CUS-25` (P2, R3) — Import / Bulk-Upload Parity
- **Plan:** Locate the customer import path (if any) and route it through `apply_gstin()` and the same serializer validations; add row-level error reporting for duplicate GSTIN and state mismatch. If no import exists, record that and defer the feature to a separate plan.

#### `CUS-26` (P1, R1) — Backend Field Validation
- **Plan:** Server-side validation for latitude/longitude range and pairing (both or neither), phone format, and email format in `CustomerSerializer`, so API clients get the same rules as the UI. Add serializer tests.

#### `CUS-27` (P3, R3) — Observability & Privacy
- **Plan:** Counters/logs for 409 stale-write rate, `lookup-gstin`/verify provider errors and latency, export row counts and truncation; note PII handling (phone, email, GPS, exports) against DPDP obligations and decide retention/access rules. Also define downstream semantics in docs: what a `BLOCKED` vs `INACTIVE` customer can still do (open orders, quotations, POS, receipts).

**Explicitly out of scope for this plan (tracked separately):** mobile app (`mobile/`) parity, duplicate-customer merge tool, and name/phone duplicate detection beyond GSTIN.

---

## Part III: Shared-File Merge Order & Verification Checklist

### Shared-File Sequence

1. `backend/masters/serializers.py` + helper (`CUS-21` → `CUS-04` → `CUS-05` → `CUS-07` → `CUS-10` → `CUS-26` → `CUS-23`)
2. `backend/ledgers/services.py` & `backend/masters/views.py` (`CUS-03` → `CUS-04` → `CUS-05` → `CUS-11` → `CUS-19` → `CUS-15` → `CUS-16` → `CUS-18`)
3. `web/src/types/domain.ts` & `web/src/api/legacy/masters.ts` (`CUS-01` → `CUS-08` → `CUS-09` → `CUS-15` → `CUS-16` → `CUS-17`)
4. `web/src/i18n/en.ts` & `web/src/i18n/hi.ts` (`CUS-13`)
5. `web/src/pages/sales/CustomersPage.tsx` & `web/src/pages/sales/Customer360Page.tsx` (`CUS-01` .. `CUS-20`)
6. `docs/openapi-snapshot.json` & `web/src/api/openapi-types.ts` (`CUS-20`)

### Verification Gate Checklist (Per-Release Sign-Off)

Tick the items belonging to the release being shipped (R1: backend + permission + error items; R2: form/cache/UX items; R3: summary/export/lookup/a11y items).

- [ ] **Additional backend cases (added after review):**
  - [ ] Concurrent `PATCH` with and without `version`: different-field edits without `version` still merge; stale `version` returns `409`.
  - [ ] Walk-in guard applies on `PUT` as well as `PATCH` and `DELETE`.
  - [ ] Legacy-data PATCH: an unrelated-field PATCH on a customer with mismatched state/GSTIN still succeeds (`CUS-07` regression).
  - [ ] GSTIN prefixes 96/97/26/38 do not cause false mismatch rejections.
  - [ ] `lookup-gstin/`, `summary/`, `export/`: permission matrix, throttling (lookup), audit entry (export), truncation signal, and **tenant isolation** (company A cannot see company B).
  - [ ] `destroy` on a referenced customer bumps `version`/`updated_at`.
  - [ ] `CUS-23`: `SALES_STAFF` cannot change `credit_limit`/`credit_days`; `OWNER`/`MANAGER` can, with audit rows.
  - [ ] `CUS-26`: out-of-range or half-filled coordinates, bad phone/email rejected by the API.
  - [ ] `sort=balance` benchmark (5,000 customers) meets the agreed query-count/time budget.
  - [ ] `CUS-22` command runs read-only against a copy of production-like data and its output is reviewed before enabling `CUSTOMER_STRICT_VALIDATION`.
- [ ] **Backend Tests (`pytest backend/masters/tests/`):**
  - [ ] `CUS-04` / `CUS-17`: `PATCH` and `DELETE` on `is_pos_walk_in=True` customer reject `gstin`, `credit_limit > 0`, `status != 'ACTIVE'`, and deletion/deactivation with `400`.
  - [ ] `CUS-05`: `PATCH` changing `gstin` on a `'VALID'` verified customer resets `gstin_verification_status` to `'UNVERIFIED'` and clears `gstin_legal_name` inside `perform_update`.
  - [ ] `CUS-07`: `POST`/`PATCH` with `gstin='27AABCU9603R1ZN'` and `state='Karnataka'` returns `400`; blank `state` auto-populates `'Maharashtra'`.
  - [ ] `CUS-10`: `POST`/`PATCH` with duplicate `gstin` in the same company returns `400` naming the conflicting customer.
  - [ ] `CUS-03`: `POST /api/v1/customers/:id/verify-gstin/` succeeds for `SALES_STAFF` with `can_create_sales=True` and returns `403` for `ACCOUNTANT` with `can_create_sales=False`.
  - [ ] `CUS-15`: `GET /api/v1/customers/summary/` and `GET /api/v1/customers/export/` respect `q` and `status` filters and produce formula-safe CSV rows.
  - [ ] `CUS-16`: `POST /api/v1/customers/lookup-gstin/` validates checksum and returns state/PAN/legal name without requiring an existing customer ID.
  - [ ] `CUS-18`: `PATCH /api/v1/customers/:id/` with stale `version` returns `409 Conflict`.
  - [ ] `CUS-19`: `GET /api/v1/customers/?q=user@example.com` finds customer by email; `?status=INVALID` returns `400`.
- [ ] **Frontend & Accessibility Tests (`npx vitest run src/pages/sales/CustomersPage.test.tsx`):**
  - [ ] Renders Credit, Tax, Shipping Addresses, and Custom Fields (`creditLimit`, `creditDays`, `taxpayerType`, `pan`, `shippingAddress`, `notes`, `customFields`) in the modal and submits them.
  - [ ] In-modal **Verify & Autofill** populates `name`, `state`, `pan`, and `taxpayerType` from GSTIN lookup.
  - [ ] Displays server/validation error alerts *inside* the open `<Dialog>` without closing or losing inputs.
  - [ ] Updates `state` automatically even when editing an existing GSTIN from one state prefix to another.
  - [ ] Maps `'VALID'` GSTIN status to green (`success`) chip and `'CANCELLED'`/`'SUSPENDED'`/`'INVALID'` to red (`error`) chip.
  - [ ] Hides mutation buttons when `canCreateSales` is false or `writesBlocked` is true; hides **View Ledger** when `canViewFinancialReports` is false.
  - [ ] Protects `isPosWalkIn` customer row from blocking/deletion and requires confirmation before blocking or archiving regular customers.
  - [ ] Passes `axe-core` audit with **no new violations versus the recorded baseline** and supports full keyboard navigation + focus restoration.
  - [ ] 409 stale-write shows the in-dialog "Reload latest" notice without losing typed values.
  - [ ] Role matrix incl. `pos_walk_in` cashier flow and `verify_gstin` decision from `CUS-03`.
