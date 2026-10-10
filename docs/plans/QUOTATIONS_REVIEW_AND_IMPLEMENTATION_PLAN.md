# Quotations Module: Review, Remediation Status & Implementation Plan

**Date:** 2026-10-10 (revised 2026-10-10 after code verification)  
**Roles:** Principal Product Manager, Senior UX Designer, Business Analyst, Software Architect, QA Lead  
**Scope:** [`QuotationsPage.tsx`](../../web/src/pages/sales/QuotationsPage.tsx), [`ConvertQuotationDialog.tsx`](../../web/src/pages/sales/ConvertQuotationDialog.tsx), [`quotationConvert.ts`](../../web/src/utils/quotationConvert.ts), [`sales.ts` (legacy API)](../../web/src/api/legacy/sales.ts), [`backend/sales/models.py`](../../backend/sales/models.py), [`backend/sales/views.py`](../../backend/sales/views.py) (`QuotationViewSet`), [`backend/sales/services.py`](../../backend/sales/services.py) (quotation section), [`backend/sales/serializers.py`](../../backend/sales/serializers.py) (`QuotationSerializer`), and related cross-module pipelines.

**Status:** 🔴 **NOT READY FOR PRODUCTION.** The web production build fails, and the backend has three confirmed data-integrity bugs in the new update path. See [Part III](#part-iii-open-issues--implementation-plan).

> **How this document was verified.** Each claim was checked against the working tree (uncommitted changes on top of `b84350e`). The cited test suites were run, along with `eslint` and `tsc -b` on the web app. A temporary backend test was used to probe edge cases and then deleted. Line references use symbol names because line numbers drift.

---

## Part I: Module Review

### 1. Screen purpose
- **What it's for:** Managing pre-sale price quotations: drafting quotes, negotiating line prices and discounts, tracking validity, generating PDFs, and converting accepted quotes (fully or partially) into Sales Orders or Sales Invoices.
- **Users:** Sales representatives, account executives, billing clerks, operations managers, business owners.
- **Problem solved:** Formal price negotiation without committing stock, consuming statutory document numbers, or creating receivables.
- **Primary actions:** "New Quotation" (create) and "To Order" / "Convert" (move the quote forward).
- **Out of scope:** Warehouse dispatch (Delivery Challans), stock deduction, e-Way bill / e-Invoice generation, payment allocation.

### 2. UX problems found (before this change set)
- **Clarity:** The internal cost column is labelled "Expected price", which reads like a target selling price.
- **Simplicity:** The full quote editor lived in a 600px dialog (`maxWidth="sm"`), so the 7-column line table scrolled horizontally.
- **Discoverability:** The backend supported cancellation, but the UI had no way to cancel.
- **Navigation:** Closing the edit dialog left the URL at `/sales/quotations/:id`, so a refresh reopened it.
- **Confidence:** No subtotal, tax or grand total was shown before saving.
- **Error prevention:** Quantities were truncated to whole numbers (`Math.floor`), and line quantities could not be edited without deleting the row.

### 3. Cognitive load
- Each table row offered Download, Edit, To Order, Convert, and an unconfirmed "Convert → SO → DC" shortcut.
- Adding a product meant several separate inputs, and quantities could not be corrected afterwards.
- One dialog tried to be customer creator, line grid, profit forecaster and product search at the same time.

### 4. User flow (as implemented after this change set)
```text
[Sales History / Nav / ?create=1]
       ↓
[Quotations List (/sales/quotations)]
       ↓ (Click 'New Quotation')
[Dialog (maxWidth='md')]
       ↓ (Customer, Valid Until, Salesperson, Address)
       ↓ (Quotation Date field is shown but IGNORED on create — see OPEN-05)
[Add lines (Product, decimal Qty, Unit Price, Discount)]
       ↓ (Estimated Subtotal / GST / Total preview — see OPEN-09)
[Save (POST / PATCH)]
       ↓
[List row: DRAFT, Valid Until, (Expired) badge]
       ├── Download PDF
       ├── Edit (keeps original quotationDate; lines locked if partially converted)
       ├── To Order  → ConvertQuotationDialog (expired quotes need a confirmation tick)
       ├── Convert   → ConvertQuotationDialog (expired quotes need a confirmation tick)
       └── Cancel    (only when nothing has been converted; asks for confirmation)
```

### 5. Data & state
- **Lifecycle:** `DRAFT` → `DRAFT` (partially converted, no distinct status) → `CONVERTED`, or `DRAFT` → `CANCELLED`.
- **Partial conversion:** Once any line has `converted_quantity > 0`, `SalesService.set_quotation_items` refuses to rewrite lines. The frontend always sent `items` on save, so header-only edits to a partially converted quote failed with a 400 business-rule error (not a crash). The committed serializer already supports header-only PATCHes that omit `items`.
- **Missing states:** There is no Sent / Accepted / Rejected / Expired status, no "partially converted" indicator in the list, and no revision/amend flow for quotes.

### 6. Business rules
- A customer is required (client-side check added; the backend already required it).
- Editing a quote keeps its original `quotationDate`.
- Converting an expired quote requires `confirm_expired=true`. The backend has always enforced this; the change adds the UI to send it.
- Cancel is blocked if any quantity has been converted (enforced by the backend in `cancel_quotation`).

### 7. Cross-module impact
- **Inventory (HIGH):** Removing the one-click chain convert from the UI removes an unconfirmed path to stock deduction. The `POST /sales/quotations/{id}/convert-chain/` endpoint is still live (see OPEN-13).
- **Sales Orders & Invoicing (HIGH):** Partial and full conversions keep line pricing and traceability. However, header edits after partial conversion can currently change the customer (see OPEN-04), which breaks that traceability.
- **Customer 360 (MEDIUM):** Open quotations represent pending customer commitments.
- **Search (LOW):** Search by quote number and customer name now works in the list.

### 8. Security & permissions
- List, retrieve and PDF require `CanViewSalesSurfaces`. Create, edit and convert require `CanCreateSales`. Cancel requires `CanCancelDocuments`.
- The UI shows the Cancel button based on `canCreateSales`, not `canCancelDocuments`, so some roles see a button that returns 403 (see OPEN-07).

---

## Part II: What Changed and Whether It Works

Verified status of each change in this change set:

| Change | Status |
|---|---|
| Backend search `q` (number, customer name) | ✅ Works |
| Backend `date_from` / `date_to` | ✅ Works; invalid dates return 400 |
| Backend `customer` filter | ⚠️ Works, but an invalid value is silently ignored and the UI never sends it |
| Decimal quantities (removed `Math.floor`) | ⚠️ Works, but the input clamps on every keystroke |
| Editable line quantity in the dialog | ⚠️ Works, but the field can't be cleared |
| Live totals preview | ⚠️ Estimate only; no tax-component split |
| Expired-quote confirmation in convert dialog | ✅ Works |
| Header-only update of partially converted quote | ❌ Three data-integrity bugs |
| Remove chain-convert button | ✅ Removed from UI; endpoint still live |
| Cancel action and CANCELLED filter | ⚠️ Works; wrong permission check in UI |
| Dialog widened to `md` | ✅ Works |
| Keep `quotationDate` on edit | ✅ Works for edits; ignored on create |
| Clear `/:id` from URL when dialog closes | ✅ Works |
| "Expected price" relabelled as cost | ❌ Not applied |
| New i18n strings | ❌ Keys missing; build fails |

### Backend
- **[`QuotationViewSet.get_queryset`](../../backend/sales/views.py)** now filters by `status`, `customer`, `date_from`, `date_to` and `q` (number or customer name). It is looser than the invoice list in the same file, which validates `status` and `customer`, parses dates explicitly, and caps `q` at 100 characters.
- **[`QuotationSerializer.update`](../../backend/sales/serializers.py)**: when the quote has converted quantity, it compares incoming lines with existing lines by product and quantity only. If they differ it raises a business-rule error; otherwise it skips the line rewrite. This approach causes OPEN-02, OPEN-03 and OPEN-04 and should be replaced (see Part III).

### Frontend
- **[`sales.ts`](../../web/src/api/legacy/sales.ts):** added `cancelQuotation(id)`.
- **[`ConvertQuotationDialog.tsx`](../../web/src/pages/sales/ConvertQuotationDialog.tsx):** detects an expired quote (`validUntil < todayIso()`), shows a warning and a confirmation checkbox, and passes `confirmExpired` to `onConfirm`.
- **[`QuotationsPage.tsx`](../../web/src/pages/sales/QuotationsPage.tsx):** `maxWidth="md"`, decimal quantities, editable line quantities, totals preview, original `quotationDate` kept on edit, URL cleared on close, Cancel action, CANCELLED filter, Valid Until column with an "(Expired)" badge, line inputs locked for partially converted quotes, chain-convert button removed.

### Verification results

| Check | Result |
|---|---|
| `vitest` — `QuotationsPage.test.tsx`, `ConvertQuotationDialog.test.tsx`, `quotationConvert.test.ts` | 11 / 11 passed |
| `pytest` — `test_quotation_remediation.py` (2), `test_cft_cross_flow.py` (10) | 12 / 12 passed |
| `eslint` on `QuotationsPage.tsx` | ❌ 1 error (unused `convertQuotationChain`) |
| `tsc -b` (first step of `npm run build`) | ❌ 13 errors in `QuotationsPage.tsx` |

**Gaps in the tests:**
- `test_quotation_remediation.py` passes `confirm_expired: True` but never checks that conversion is *rejected* without it.
- There are no tests for rejected line edits, the customer filter, search by quote number, or invalid filter parameters.
- The new frontend test "renders table columns and cancel button for active draft quotations" only checks the empty state.
- There are no tests for the create-date bug, the quantity input, cancel permissions, or the locked-lines UI.

---

## Part III: Open Issues & Implementation Plan

### Open issues

| ID | Priority | Issue |
|---|---|---|
| OPEN-01 | **P0** | Web production build fails |
| OPEN-02 | **P0** | A rejected edit still saves header changes |
| OPEN-03 | **P0** | Price changes on partially converted quotes are silently dropped |
| OPEN-04 | **P0** | Unrestricted header edits after partial conversion; totals go stale |
| OPEN-05 | P1 | Quotation date picker is ignored on create |
| OPEN-06 | P1 | Quantity inputs clamp on every keystroke |
| OPEN-07 | P1 | Cancel button uses the wrong permission check |
| OPEN-08 | P1 | "Expected price" label not changed |
| OPEN-09 | P2 | Totals preview is incomplete |
| OPEN-10 | P2 | List filters are looser than the invoice list's |
| OPEN-11 | P2 | Expiry warning is hard-coded English and uses the browser's date |
| OPEN-12 | P2 | Test gaps (listed in Part II) |
| OPEN-13 | P2 | Chain-convert endpoint still live with no UI |
| OPEN-14 | P3 | Lifecycle gaps |

**OPEN-01 — Web production build fails.**
- `convertQuotationChain` is imported but unused (ESLint and TS6133).
- 12 calls use the form `t('key', 'Fallback')`. The second argument to `t()` is interpolation variables, not fallback text (TS2345).
- Several keys used by these calls are missing from `en.ts` and `hi.ts`: `status.expired`, `status.quotationCancelled`, `billing.quotationLinesLocked`, `billing.estimatedTax`, `billing.selectCustomerRequired`, `common.confirmCancelQuotation`. Users would see the raw key path.

**OPEN-02 — A rejected edit still saves header changes.**
- `update()` calls `super().update()` before the line check, and `ATOMIC_REQUESTS` is off.
- Confirmed: a PATCH changing `notes` plus a line quantity returned 400, yet the new `notes` were saved.

**OPEN-03 — Price changes on partially converted quotes are silently dropped.**
- The line comparison only looks at product and quantity.
- Confirmed: a PATCH changing `unit_price` returned 200, but the price was unchanged.

**OPEN-04 — Unrestricted header edits after partial conversion.**
- Confirmed: a partially converted quote accepted a change of `customer` and `invoice_discount=100`, and `grand_total` stayed at 590.00. Totals are only recalculated in `set_quotation_items`, which this path skips.
- The customer field is also still editable in the UI.

**OPEN-05 — Quotation date picker is ignored on create.** The payload sends `editingId ? quotationDate : todayIso()`.

**OPEN-06 — Quantity inputs clamp on every keystroke.**
- `Math.max(0.001, … || 0.001)` runs on every change, so the field can't be cleared or retyped.
- Entering 0 or a negative quantity when adding a line silently becomes 0.001 instead of showing a validation error.

**OPEN-07 — Wrong permission check for Cancel.** The UI uses `canCreateSales`, but the backend requires `CanCancelDocuments`.

**OPEN-08 — "Expected price" label not changed.** `t('billing.expectedPrice', 'Est. Cost')` still renders "Expected price", because that key already exists.

**OPEN-09 — Totals preview is incomplete.**
- It shows a single "Est. GST" figure, with no CGST/SGST/IGST split.
- It ignores header discount, additional charges, cess, tax-inclusive prices and non-GST invoice types.
- It always rounds, regardless of `auto_round_off`.

**OPEN-10 — List filters are looser than the invoice list's.**
- An invalid `customer` is silently ignored, so every quote is returned.
- `status` is not validated, and `q` has no length cap.
- The UI never sends a `customer` filter.

**OPEN-11 — Expiry warning issues.** The label is hard-coded English. The expiry check uses the browser's date, while the backend uses the server's local date, so they can disagree around midnight.

**OPEN-13 — Chain-convert endpoint still live.** `POST /convert-chain/` and `convertQuotationChain` still exist. Product needs to decide whether to deprecate the endpoint or bring the shortcut back with a confirmation step, and either way publish a release note.

**OPEN-14 — Lifecycle gaps.** There is no Sent / Accepted / Rejected / Expired status, no partially-converted indicator in the list, and no revision/amend flow.

### Implementation plan (in order)

**Step 1 — Unblock the build (OPEN-01, OPEN-08)**
1. Remove the unused `convertQuotationChain` import from `QuotationsPage.tsx`.
2. Add the missing keys to `en.ts` and `hi.ts`, and change all `t('key', 'Fallback')` calls to `t('key')`.
3. Rename the `billing.expectedPrice` text to make clear it is cost, for example "Est. cost (internal)".
4. Move the expiry label in `ConvertQuotationDialog.tsx` into i18n, using the `{date}` variable.
5. Done when: `npm run lint` and `npm run build` both pass.

**Step 2 — Make the update path safe (OPEN-02, OPEN-03, OPEN-04)**
1. Remove the product/quantity comparison branch from `QuotationSerializer.update`.
2. In `QuotationsPage.tsx`, leave `items` out of the PATCH body when the quote is partially converted. The committed serializer already supports this.
3. In the backend, when any line has converted quantity, accept only these header fields: `valid_until`, `notes`, `terms_text`, `delivery_address`, `salesman`, `sales_channel`. Reject everything else, including `items`, with a business-rule error.
4. Wrap `update()` in `transaction.atomic()` and run the checks before any write.
5. In the UI, disable the customer field and the money-affecting header fields when the quote is partially converted.
6. Done when: the regression tests below pass and a rejected PATCH leaves the row unchanged.

**Step 3 — Fix UI behaviour (OPEN-05, OPEN-06, OPEN-07)**
1. Send the selected `quotationDate` on create as well as on edit.
2. Keep the raw text value in local state while the user types, and validate only on blur or save. Show an inline error for quantities ≤ 0 instead of coercing them.
3. Show the Cancel button only when `canCancelDocuments(user)` is true.

**Step 4 — Make the filters consistent (OPEN-10)**
1. Follow the invoice list's handling in `QuotationViewSet.get_queryset`: validate `status` against `Quotation.Status.values`, return 400 for a non-numeric `customer`, parse dates with `date.fromisoformat`, and cap `q` at 100 characters.
2. Add a customer filter to the list UI, or drop the backend parameter.

**Step 5 — Totals preview (OPEN-09)**
- Preferred: get the totals from the server using the same tax engine as save (a dry-run endpoint or the existing compute path).
- Fallback: label the panel "Estimate", apply header discount and charges, and respect `auto_round_off` and the invoice type.

**Step 6 — Tests (OPEN-12)**

Backend:
- Converting an expired quote without `confirm_expired` returns 400.
- A rejected PATCH on a partially converted quote leaves header fields unchanged.
- Changing customer, discount or prices after partial conversion is rejected.
- Customer filter; search by quote number; invalid `status`, `customer` and date values return 400.

Frontend:
- A new quote is created with the selected date.
- The quantity field can be cleared and retyped.
- The Cancel button is hidden without cancel permission.
- Line inputs and the customer field are locked for partially converted quotes.
- Rewrite the misnamed list test so it checks what its name says.

**Step 7 — Product decisions (OPEN-13, OPEN-14)**
- Decide what happens to chain-convert and publish a release note.
- Plan the lifecycle states, a partially-converted indicator, and quote revisions as a separate initiative.

---

## Scorecard

Scores reflect the code as it stands today. "Target" is the expected score after Steps 1–6.

| Dimension | Before | Now | Target |
|---|---:|---:|---:|
| Purpose clarity | 7 | 7 | 9 |
| UX & ergonomics | 4 | 6 | 8 |
| Cognitive load | 5 | 7 | 8 |
| User flow & state | 6 | 7 | 8 |
| Functionality & filtering | 5 | 7 | 9 |
| Business logic & validation | 6 | 5 | 9 |
| Data & state handling | 5 | 4 | 9 |
| Error handling & recovery | 4 | 6 | 8 |
| Cross-module safety | 5 | 6 | 8 |
| **Overall** | **5.2** | **6.1** | **8.4** |

The overall target stays below 9 until the lifecycle gaps in OPEN-14 are addressed.

### Release gate
Release only when all of these are true:
- OPEN-01 through OPEN-07 are closed.
- `npm run lint` and `npm run build` pass.
- The Step 6 regression tests are in place and green.
