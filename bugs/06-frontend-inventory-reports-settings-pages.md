# Area 06 — Frontend Inventory, Reports, Settings, Dashboard, Auth Pages

**Scope:** `inventory/CurrentStockPage.tsx`, `LowStockPage.tsx`, `ProductsPage.tsx`, `StockAdjustmentPage.tsx`; `reports/CustomerLedgerPage.tsx`, `InventoryReportPage.tsx`, `PurchaseReportPage.tsx`, `SalesReportPage.tsx`, `SupplierLedgerPage.tsx`; `settings/BackupExportPage.tsx`, `CompanySettingsPage.tsx`, `GstSettingsPage.tsx`, `ImportPage.tsx`, `InvoiceTemplatesPage.tsx`, `UsersSettingsPage.tsx`; `DashboardPage.tsx`, `LoginPage.tsx`, `RegisterPage.tsx`, `ForbiddenPage.tsx`; plus `App.tsx` routing, `navigation/menu.ts`, `utils/permissions.ts`, `api/resources.ts`, `auth/session.ts`.

---

### BUG-600 — U-01 re-verified: ForbiddenPage is wired, but component-level guards bypass it inconsistently
- **Severity:** Medium
- **Category:** Gap
- **Location:** `CompanySettingsPage.tsx:64`, `InvoiceTemplatesPage.tsx:57`, `BackupExportPage.tsx:14`, `ImportPage.tsx:94`
- **Description:** `App.tsx`'s `RoleRoute` correctly renders `<ForbiddenPage />` on denial, and `GstSettingsPage`/`UsersSettingsPage` use it directly. But 4 sibling settings pages implement their own redundant guard that silently `Navigate`s to `/` instead.
- **Impact:** Cosmetic today (RoleRoute fires first), but landmine-prone — any future refactor loosening a RoleRoute wrapper reintroduces the exact "silently bounced, no message" bug in 4 of 6 settings pages.
- **Remediation:** Standardize on `<ForbiddenPage />` everywhere; delete the redundant component-level checks.
- **Status vs prior report:** ALREADY-FIXED at the route layer (U-01's literal claim is false), but a residual inconsistent pattern is a NEW finding.

### BUG-601 — Dashboard discards backend-computed receivables aging and recent invoices
- **Severity:** High
- **Category:** Gap
- **Location:** `DashboardPage.tsx:51-59`; `types/domain.ts:337-366`
- **Description:** `DashboardKpis` already types `receivablesAging` (current/1-30/31-60/61-90/90+) and `recentInvoices`, and the backend already computes and returns both. `DashboardPage` never reads either field, rendering only the flat `receivables` total.
- **Remediation:** Add an aging breakdown and a recent-invoices mini-table using the already-shipped fields.
- **Status vs prior report:** CONFIRMED-STILL-PRESENT (UX_REVIEW.md U-07), stronger evidence than originally cited.

### BUG-602 — Ledger pages show only aggregate outstanding; no aging is even structurally possible
- **Severity:** High
- **Category:** Gap
- **Location:** `reports/CustomerLedgerPage.tsx:47-49`; `reports/SupplierLedgerPage.tsx:47-49`; `types/domain.ts:318-326`
- **Description:** `LedgerEntry` has no `dueDate` field at all — both ledger pages render only one `outstanding` number, no per-entry aging.
- **Remediation:** Add `dueDate` to `LedgerEntry` server+client side; derive an Overdue/Due-in-N-days chip per row.
- **Status vs prior report:** CONFIRMED-STILL-PRESENT (U-07), extends the claim to the reports area.

### BUG-603 — "Hard-coded Bengaluru jurisdiction" claim is inaccurate for the reviewed frontend files
- **Severity:** Low
- **Location:** `settings/InvoiceTemplatesPage.tsx:138`; actual source `backend/accounts/management/commands/seed_demo.py:16,40,61-62`
- **Description:** The FE placeholder is generic. The Bengaluru string exists only in a Django demo-seed command, not in any settings page, and the field is fully owner-editable regardless.
- **Status vs prior report:** INACCURATE (UX_REVIEW.md U-10) as applied to the frontend files named.

### BUG-604 — "Dashboard receivables computation doesn't scale" claim is inaccurate for the frontend specifically
- **Severity:** Low
- **Location:** `DashboardPage.tsx:27-28`; `api/resources.ts:91-96`
- **Description:** `DashboardPage` calls exactly `getDashboard()` and `listLowStock()` — it does not fetch all customers/invoices client-side. Whatever scaling problem exists (see area 03's BUG-301/302) is server-side, not FE-induced.
- **Status vs prior report:** INACCURATE (BUG_REPORT.md BUG-013) as it pertains to frontend code.

### BUG-605 — Perf report "PAGE_SIZE 50 — good default" claim is false for report/list tables
- **Severity:** Medium
- **Category:** Performance
- **Location:** `reports/SalesReportPage.tsx:60-86`; `PurchaseReportPage.tsx:61-87`; `InventoryReportPage.tsx:34-55`
- **Description:** These three report tables render `query.data.rows` in full with no pagination, virtualization, or row cap.
- **Impact:** A full fiscal-year sales register (thousands of rows) renders as one giant unvirtualized MUI Table.
- **Remediation:** Add virtualization (`react-window`) or client-side pagination.
- **Status vs prior report:** INACCURATE (PERFORMANCE_REPORT.md) for these three pages specifically.

### BUG-606 — CurrentStockPage silently shows only the first 50 stock rows
- **Severity:** High
- **Category:** Broken-Flow
- **Location:** `inventory/CurrentStockPage.tsx:16,39`; `api/resources.ts:737-742`
- **Description:** `listStock()` hits a 50/page paginated endpoint but returns only page 1 via `asList()`, no "load more", no indication more pages exist.
- **Status vs prior report:** NEW. (Same systemic `asList()` bug independently found in area 05 as BUG-521.)

### BUG-607 — ProductsPage silently shows only the first 50 products
- **Severity:** High
- **Category:** Broken-Flow
- **Location:** `inventory/ProductsPage.tsx:62,171`; `api/resources.ts:154-159`
- **Description:** Same `asList()` truncation pattern for `/products/`. A retailer with >50 SKUs cannot see, edit, or search products beyond page 1 from this screen.
- **Remediation:** Same as BUG-606; also wire the already-accepted `q` search param into a visible search box.
- **Status vs prior report:** NEW.

### BUG-608 — CustomerLedgerPage's customer picker only offers the first 50 customers
- **Severity:** High
- **Category:** Broken-Flow
- **Location:** `reports/CustomerLedgerPage.tsx:20,32-39`; `api/resources.ts:112-117`
- **Description:** `listCustomers()` loads a single unpaginated fetch of a 50-per-page endpoint into an Autocomplete, with no server-side search wired despite the API already accepting `q`.
- **Impact:** For >50 customers, customers beyond page 1 cannot be selected to view their ledger at all — a functional dead end, not just slow.
- **Remediation:** Wire `Autocomplete.onInputChange` to `listCustomers({q})`, debounced.
- **Status vs prior report:** NEW.

### BUG-609 — SupplierLedgerPage / StockAdjustmentPage have the identical unpaginated-picker bug
- **Severity:** High
- **Category:** Broken-Flow
- **Location:** `reports/SupplierLedgerPage.tsx:20,32-39`; `inventory/StockAdjustmentPage.tsx:29,69-77`
- **Description:** Same unbounded-picker pattern for suppliers/products.
- **Status vs prior report:** NEW.

### BUG-610 — LowStockAlertsView is entirely unpaginated server-side; LowStockPage renders it unbounded
- **Severity:** Medium
- **Category:** Performance
- **Location:** `inventory/LowStockPage.tsx:17,40`; `backend/inventory/views.py:99-113`
- **Description:** `LowStockAlertsView` serializes every matching row with no pagination at all; `LowStockPage` renders the full array with no client pagination/virtualization.
- **Remediation:** Paginate server-side; add virtualization or client pagination.
- **Status vs prior report:** NEW (the real, verifiable performance issue BUG-013 likely intended but misattributed).

### BUG-611 — DashboardPage swallows the low-stock query's error state as "no alerts"
- **Severity:** Medium
- **Category:** Bug
- **Location:** `DashboardPage.tsx:69-84`
- **Description:** `lowStock.isError` is never checked; on failure, the UI renders the "no alerts" empty state, indistinguishable from "everything is fully stocked."
- **Impact:** A backend outage on the alerts endpoint is misreported as "no low-stock items" — a false reassurance that could delay reordering.
- **Remediation:** Add an explicit `isError` branch before the empty-state check.
- **Status vs prior report:** NEW.

### BUG-612 — `canExport` permission is defined and user-configurable, but never enforced anywhere
- **Severity:** High
- **Category:** Bug
- **Location:** `utils/permissions.ts:31-33`; `settings/UsersSettingsPage.tsx:158-161`; `reports/SalesReportPage.tsx:47-52`; `PurchaseReportPage.tsx:48-53`; `InventoryReportPage.tsx:22-27`; `settings/BackupExportPage.tsx:26-33`
- **Description:** `canExport(user)` is toggleable per-user in Users Settings (implying enforcement), but is imported and checked nowhere else. Export buttons are gated only by `canViewFinancialReports` (which defaults `true` for staff — see area 03's BUG-319) or `canManageUsers`.
- **Impact:** An owner unchecking "Can export" for a staff member gets no actual enforcement — the permission is decorative.
- **Remediation:** Gate every Export button with `canExport(user)`, or remove the checkbox if not intended to be enforced yet.
- **Status vs prior report:** NEW.

### BUG-613 — Export buttons call `window.open()` inside an async `.then()`, which popup blockers commonly block
- **Severity:** Medium
- **Category:** Bug
- **Location:** `reports/SalesReportPage.tsx:49`; `PurchaseReportPage.tsx:50`; `InventoryReportPage.tsx:24`; `settings/BackupExportPage.tsx:29`
- **Description:** All four export buttons call `window.open` after a promise resolves rather than synchronously in the click handler — commonly blocked silently by browser popup blockers, with no error shown.
- **Remediation:** Trigger a same-tab download via a hidden `<a download>` element (as `ImportPage.tsx`'s `downloadTemplate` already correctly does).
- **Status vs prior report:** NEW.

### BUG-614 — `exportReport()` never revokes its Blob object URL
- **Severity:** Low
- **Category:** Performance
- **Location:** `api/resources.ts:1003-1008`
- **Description:** `URL.createObjectURL(blob)` is never paired with `revokeObjectURL`, unlike `ImportPage.tsx:46`. Repeated exports in a long session accumulate blob references — a slow memory leak.
- **Status vs prior report:** NEW.

### BUG-615 — Export buttons have no error handling at all
- **Severity:** Medium
- **Location:** Same 4 locations as BUG-613
- **Description:** No `.catch()`, no loading/disabled state while the export is in flight — a failed export produces zero user-visible feedback and can be spam-clicked.
- **Remediation:** Convert to `useMutation` with `onError` and `disabled={isPending}`.
- **Status vs prior report:** NEW.

### BUG-616 — `exportReport` on Sales/PurchaseReportPage ignores the currently-applied date filter
- **Severity:** High
- **Category:** Broken-Flow
- **Location:** `reports/SalesReportPage.tsx:19-24,47-52`; `PurchaseReportPage.tsx:19-25,48-53`; `api/resources.ts:989-1009`
- **Description:** The on-screen table is filtered by `dateFrom`/`dateTo`, but Export calls `exportReport('sales')` with no parameters at all — a filtered view exports the full unfiltered register.
- **Impact:** A user filters "this month," exports expecting a matching CSV, and gets the full unfiltered register — a silent data-mismatch bug with GST/accounting implications.
- **Remediation:** Add date params to `exportReport` and forward current filter state.
- **Status vs prior report:** NEW. (Same root gap independently found on the backend side as area 03's BUG-323.)

### BUG-617 — CompanySettingsPage save mutation has no error handling
- **Severity:** High
- **Category:** Bug
- **Location:** `settings/CompanySettingsPage.tsx:59-62,77`
- **Description:** `useMutation` defines only `onSuccess`; no `onError`, and the JSX only checks `isSuccess`. A failed save gives zero feedback.
- **Status vs prior report:** NEW.

### BUG-618 — GstSettingsPage save mutation has no error handling (identical bug to BUG-617)
- **Severity:** High
- **Location:** `settings/GstSettingsPage.tsx:48-51,66`
- **Description:** Same pattern — arguably worse here since this is the most compliance-sensitive settings page in the app (GSTIN, registration type).
- **Status vs prior report:** NEW.

### BUG-619 — Save-error alerts render behind the open modal Dialog, effectively invisible
- **Severity:** Medium
- **Category:** UI-Optimization
- **Location:** `inventory/ProductsPage.tsx:150,213-286`; `settings/UsersSettingsPage.tsx:84,175-269`
- **Description:** Error `Alert`s are placed in the page body as a sibling before the `Dialog`, so a save failure while the Add/Edit/Invite dialog is open renders behind the modal backdrop — invisible.
- **Remediation:** Render the error inside `DialogContent`/`DialogActions`.
- **Status vs prior report:** NEW.

### BUG-620 — No duplicate SKU/barcode check on the product form
- **Severity:** Medium
- **Category:** Gap
- **Location:** `inventory/ProductsPage.tsx:69-88,280`
- **Description:** Save is disabled only by empty name/SKU; no client-side check against already-loaded products for a duplicate SKU/barcode.
- **Status vs prior report:** NEW. (Backend-side gap independently found as area 03's BUG-320.)

### BUG-621 — GST rate / HSN validators exist and are unit-tested, but are never wired into the product form
- **Severity:** High
- **Category:** Gap
- **Location:** `inventory/ProductsPage.tsx:239-244`; `utils/gst.ts:11-19`
- **Description:** `isValidHsnSac()`/`normalizeGstRate()` exist and are covered by `gst.test.ts`, but a repo-wide grep shows they're used nowhere — including the one place a GST rate/HSN is entered.
- **Impact:** A user can enter `gstRate: -5` or `999` or a malformed HSN with zero client feedback; such products then flow invalid tax rates into invoices.
- **Remediation:** Wire the validators into the form (react-hook-form rules), mirroring how `GstSettingsPage` validates GSTIN.
- **Status vs prior report:** NEW. (Backend-side counterpart independently found as area 02's BUG-210.)

### BUG-622 — Price and reorder-level fields accept negative values
- **Severity:** Medium
- **Location:** `inventory/ProductsPage.tsx:245-262`
- **Description:** `purchasePrice`/`sellingPrice`/`reorderLevel` are plain number fields with no `min` or validation.
- **Impact:** Negative values silently corrupt margin calculations and low-stock threshold logic.
- **Status vs prior report:** NEW.

### BUG-623 — StockAdjustmentPage gives no visibility into current stock, and no bound on the adjustment delta
- **Severity:** Medium
- **Location:** `inventory/StockAdjustmentPage.tsx:64-93`
- **Description:** No display of the selected product's current on-hand quantity; `quantity` validation is only "non-zero" — no integer check, no projected-balance preview, and no surfacing of the company's negative-stock policy.
- **Remediation:** Show current available quantity and the resulting projected balance before submit.
- **Status vs prior report:** NEW. (Related backend gap independently found as area 03's BUG-322 — ADJUSTMENT bypasses the negative-stock policy entirely.)

### BUG-624 — `menu.ts` doesn't hide the Reports section for users lacking `canViewFinancialReports`, even though the route guard will bounce them
- **Severity:** Medium
- **Category:** Gap
- **Location:** `navigation/menu.ts:64-74`; `App.tsx:110-116`
- **Description:** The `reports` nav node has no `visible` predicate, unlike `settings`/`bill-upload`, which correctly hide via `canAccessSettings`/`canImport`. Every user sees all 5 report links, but `App.tsx` gates the actual routes on `canViewFinancialReports` — a guaranteed dead-end click for restricted users.
- **Remediation:** Add `visible: canViewFinancialReports` to the `reports` node, matching the pattern used elsewhere in the same file.
- **Status vs prior report:** NEW. (Compounds area 03's BUG-319 — `canViewFinancialReports` defaults `true`, so this mostly matters once an owner explicitly restricts a user.)

### BUG-625 — Company `state` is editable independently from two different settings pages, risking a stale overwrite
- **Severity:** Medium
- **Category:** Bug
- **Location:** `settings/CompanySettingsPage.tsx:86`; `settings/GstSettingsPage.tsx:40,85-88`
- **Description:** `state` is editable from both pages, each initialized from its own query snapshot and each PATCHing whichever `state` value it loaded. A stale second tab/mount saving one page can silently revert a more recent `state` change made via the other.
- **Impact:** Subtle data-integrity bug for a field that directly affects CGST/SGST vs IGST computation.
- **Remediation:** Make `state` editable from one canonical location; have the other page exclude it from its PATCH payload.
- **Status vs prior report:** NEW.

### BUG-626 — Invite dialog lets any owner grant a new user the `OWNER` role with zero confirmation/safeguard
- **Severity:** Medium
- **Location:** `settings/UsersSettingsPage.tsx:197-205`
- **Description:** The role dropdown offers `OWNER` as a plain, unconfirmed option alongside `SALES_STAFF` — no confirmation step before granting full owner access to a new invitee.
- **Status vs prior report:** NEW.

### BUG-627 — No way to deactivate, remove, or reset the password of a user from the Users Settings UI
- **Severity:** Medium
- **Category:** Gap
- **Location:** `settings/UsersSettingsPage.tsx:165-167`
- **Description:** `isActive` is rendered as plain read-only text with no toggle/button anywhere, despite `updateCompanyUser`'s payload type explicitly supporting `isActive`.
- **Impact:** An owner offboarding a departing staff member (a routine, security-relevant operation) has no in-app way to do it.
- **Remediation:** Add a toggle wired to `patchMutation.mutate({id, isActive: !u.isActive})`.
- **Status vs prior report:** NEW.

### BUG-628 — OTP debug code is displayed to the user unconditionally, with no environment check on the frontend
- **Severity:** High
- **Category:** Bug
- **Location:** `LoginPage.tsx:59-60`; `api/auth.ts:67-73`
- **Description:** `setOtpHint(res.debugCode ? ... : res.detail)` displays whatever `debugCode` the API returns, with no frontend guard checking this is a dev/staging build — the frontend fully trusts the backend to never send this in production.
- **Impact:** Defense-in-depth failure: if a backend misconfiguration ever causes `debugCode` to leak in a real response, the frontend happily displays the OTP on-screen to anyone requesting it for any phone number — a complete OTP account-takeover vector with no frontend safety net.
- **Remediation:** Gate the debug-code display behind an explicit frontend environment check, never solely on field presence.
- **Status vs prior report:** NEW. (Compounds backend area 01's BUG-107-class findings on `OTP_DEBUG_ECHO`.)

### BUG-629 — "Request OTP" button bypasses form validation and has no pending/disabled state
- **Severity:** Medium
- **Location:** `LoginPage.tsx:55-64,124-126`
- **Description:** `onRequestOtp` reads `getValues('phone')` directly rather than via `handleSubmit`, bypassing the `required` rule; no `disabled` while in flight, enabling rapid-click multi-SMS sends.
- **Status vs prior report:** NEW.

### BUG-630 — No password strength/length validation or confirm-password field on Register or Invite forms
- **Severity:** Medium
- **Location:** `RegisterPage.tsx:80-85`; `settings/UsersSettingsPage.tsx:185-191`
- **Description:** Both password inputs only require non-empty — no minimum length/complexity, no confirm field. A one-character password is accepted client-side.
- **Status vs prior report:** NEW.

### BUG-631 — Company/GST "state" is a free-text field, not a controlled list of Indian states/UTs
- **Severity:** Medium
- **Category:** Gap
- **Location:** `RegisterPage.tsx:87`; `settings/GstSettingsPage.tsx:85-88`; `settings/CompanySettingsPage.tsx:86`
- **Description:** `state` is plain free text everywhere it's captured — no dropdown/autocomplete against the canonical Indian state/UT list that GST intra/inter computation depends on.
- **Impact:** A typo or spelling variance can silently break the CGST/SGST vs IGST split — a compliance-relevant data-quality gap.
- **Remediation:** Replace with a `select`/`Autocomplete` bound to the canonical state/UT list with GST state codes.
- **Status vs prior report:** NEW. (Directly compounds area 02's BUG-207, found independently on the backend side.)

### BUG-632 — Tokens and user profile stored in plain `localStorage`, not httpOnly cookies
- **Severity:** Medium
- **Location:** `auth/session.ts:7-40`
- **Description:** Access/refresh tokens and the full serialized `User` object are all stored via `localStorage`, readable by any JS on the page.
- **Impact:** Any future XSS can exfiltrate the refresh token (long-lived session takeover) and the full user record.
- **Remediation:** Consider httpOnly, SameSite cookies for the refresh token at minimum.
- **Status vs prior report:** CONFIRMED (BUG_REPORT.md BUG-006 / SECURITY_REPORT.md S-02) — architecture-level, unchanged.

### BUG-633 — Report tables never render `ReportResponse.totals`
- **Severity:** Medium
- **Category:** Gap
- **Location:** `reports/SalesReportPage.tsx`, `PurchaseReportPage.tsx`, `InventoryReportPage.tsx` (whole files); `types/domain.ts:447-450`
- **Description:** `ReportResponse` types an optional `totals` field, but no report page references it — users must manually sum a potentially very long table for a grand total.
- **Status vs prior report:** NEW.

### BUG-634 — Report/import tables use array index as React key
- **Severity:** Low
- **Location:** `reports/SalesReportPage.tsx:72`; `PurchaseReportPage.tsx:73`; `InventoryReportPage.tsx:46`; `settings/ImportPage.tsx:199`
- **Description:** `key={idx}` breaks reconciliation correctness when the underlying list re-sorts/refetches with different ordering.
- **Status vs prior report:** NEW.

### BUG-635 — Zero page-level tests exist for any of the 18 reviewed pages
- **Severity:** High
- **Category:** Test-Coverage
- **Location:** `web/src/pages/**` (entire tree under review)
- **Description:** Only 8 test files exist in `web/src`, all under `api/`, `components/`, or `utils/` — none under `pages/`.
- **Impact:** Every bug catalogued above — permission bypasses, silent error swallowing, pagination truncation, unenforced `canExport` — is exactly the class of regression page-level tests would catch.
- **Remediation:** Start with `DashboardPage.test.tsx` and `UsersSettingsPage.test.tsx` given the bugs found above.
- **Status vs prior report:** CONFIRMED (matches the review brief's own suspicion).

### BUG-636 — Hardcoded English strings bypass the i18n catalog in several table headers/labels
- **Severity:** Low
- **Category:** UI-Optimization
- **Location:** `inventory/CurrentStockPage.tsx:31-35`; `inventory/LowStockPage.tsx:26,32-36,47`
- **Description:** Several literals bypass `t()` (`"Product"`, `"SKU"`, `"No low-stock alerts"`, `label="Below reorder"` instead of `labelKey`).
- **Status vs prior report:** NEW.

### BUG-637 — `dashboard.unpaid` i18n key name doesn't describe its content
- **Severity:** Cosmetic
- **Location:** `DashboardPage.tsx:53-56`; `i18n/en.ts:285`
- **Description:** The key resolves to "Purchases this month" and binds to `purchasesThisMonth.total`, not to anything "unpaid" — a rename/copy artifact that risks future maintainer confusion.
- **Status vs prior report:** NEW.

### BUG-638 — App.tsx has a route-block formatting artifact
- **Severity:** Cosmetic
- **Location:** `App.tsx:116`
- **Description:** A closing/opening `Route` tag pair jammed on one line with irregular spacing — likely a merge artifact.
- **Status vs prior report:** NEW.

---

## Summary of most severe systemic issues

1. **Data the backend already computes is thrown away by the frontend.** `/dashboard/` returns fully-computed `receivablesAging` and `recentInvoices`, and `DashboardPage.tsx` renders neither. The same absence of due-date/aging data extends into `CustomerLedgerPage`/`SupplierLedgerPage` (`LedgerEntry` has no `dueDate` field at all).
2. **Pagination is silently broken across five list-driven pages.** `CurrentStockPage`, `ProductsPage`, and the customer/supplier/product `Autocomplete` pickers in `CustomerLedgerPage`, `SupplierLedgerPage`, and `StockAdjustmentPage` all call list endpoints paginated at 50/page, but read only page 1 via `asList()` — even though a working, tested cursor-pagination helper already exists in the same file. For any tenant past 50 products/customers/suppliers, this is data becoming unreachable through the UI. (Same root cause as area 05's BUG-521.)
3. **The permission model has both dead flags and inconsistent denial UX.** `canExport` is fully wired into Users Settings but never checked by any export button; four settings pages implement their own redundant denial UX instead of `ForbiddenPage`; the Reports nav isn't hidden for users the route layer will reject anyway — and there are zero page-level tests anywhere to catch this drift.
