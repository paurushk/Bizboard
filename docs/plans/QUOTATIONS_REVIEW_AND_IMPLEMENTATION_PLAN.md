# Quotations Module: Review, Remediation Status & Implementation Plan

**Date:** 2026-10-10 (revised 2026-10-10 after code verification)  
**Roles:** Principal Product Manager, Senior UX Designer, Business Analyst, Software Architect, QA Lead  
**Scope:** [`QuotationsPage.tsx`](../../web/src/pages/sales/QuotationsPage.tsx), [`ConvertQuotationDialog.tsx`](../../web/src/pages/sales/ConvertQuotationDialog.tsx), [`quotationConvert.ts`](../../web/src/utils/quotationConvert.ts), [`sales.ts` (legacy API)](../../web/src/api/legacy/sales.ts), [`backend/sales/models.py`](../../backend/sales/models.py), [`backend/sales/views.py`](../../backend/sales/views.py) (`QuotationViewSet`), [`backend/sales/services.py`](../../backend/sales/services.py) (quotation section), [`backend/sales/serializers.py`](../../backend/sales/serializers.py) (`QuotationSerializer`), and related cross-module pipelines.

**Status:** 🔴 **NOT READY FOR PRODUCTION.** The web production build fails, and the backend has three confirmed data-integrity bugs in the new update path. See [Part III](#part-iii-open-issues--implementation-plan). A later full-product review found 27 more issues (converted quotes can be deleted, conversions can't be reversed, internal cost is exposed, and others). Those issues and the plan for every finding are in [Part IV](#part-iv-full-product-review-findings--implementation-plan).

> **Status update (2026-10-10, later).** Everything in Parts III and IV is built. A deeper review found further
> problems (header charges repeated on partial conversions, backup and restore, stuck converted quantity, the
> CRM create path and others); they and their closure are in [QUOTATIONS_CLOSURE_PLAN.md](QUOTATIONS_CLOSURE_PLAN.md).
> Two statements in this document are corrected there: the Day Book does not list quotations (the report link
> change is on the customer transaction list), and the backend `Quotation.Status` never had `EXPIRED`.

> **How this document was verified.** Each claim was checked against the working tree (uncommitted changes on top of `b84350e`). That change set has since been committed unchanged as `9cb2acb`, and the defects were re-checked there. Revision 2 of the plan (Part IV.0) was verified against `9cb2acb`. The cited test suites were run, along with `eslint` and `tsc -b` on the web app. A temporary backend test was used to probe edge cases and then deleted. Line references use symbol names because line numbers drift.

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
| OPEN-15 | P2 | Editing a quote overwrites its invoice type |
| OPEN-16 | P2 | Header-only edits to unconverted quotes don't recalculate totals |

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

**OPEN-15 — Editing a quote overwrites its invoice type.** The save payload always sends `invoiceType: preferredInvoiceType(company.registrationType)`, including on edit. A quote whose type differs from the company's current preference is silently changed.

**OPEN-16 — Header-only edits to unconverted quotes don't recalculate totals.** A PATCH without `items` that changes `invoice_discount`, `additional_charges`, `customer` or `invoice_type` saves the field but never recalculates totals. The UI doesn't hit this today because it always sends `items`, but API clients do.

### Implementation plan

The step-by-step plan is in **[QUOTATIONS_IMPLEMENTATION_PLAN.md](QUOTATIONS_IMPLEMENTATION_PLAN.md)**. It covers code shapes, exact i18n keys with Hindi text, tests per phase, a manual QA script, and deploy order. In summary:

| Phase | What it does | Closes |
|---|---|---|
| 1 | Unblock the build | OPEN-01, OPEN-08, part of OPEN-11 |
| 2 | Make the backend update path safe (atomic, field whitelist after partial conversion, totals recalculation) | OPEN-02, OPEN-03, OPEN-04 (API), OPEN-16 |
| 3 | Fix the quotation editor (payload per mode, locked fields, `NumericField` quantities, cancel permission) | OPEN-04 (UI), OPEN-05, OPEN-06, OPEN-07, OPEN-15 |
| 4 | Make list filters consistent with the invoice list; add a customer picker | OPEN-10 |
| 5 | Server-calculated totals via the existing `usePreviewTotals` hook | OPEN-09 |
| 6 | Expiry decided by the server (`is_expired` field) | rest of OPEN-11 |
| 7 | Product decisions | OPEN-13 (OPEN-14 moved to Part IV, Phase 12) |

Tests (OPEN-12) are written inside each phase.

**Deploy-order constraint:** Phases 2 and 3 are one pull request, so the backend that rejects old payloads never ships without the editor that stops sending them. Phase 2 also switches quote lines to in-place updates, which Part IV Phase 9 depends on.

Phases 8–14, and additions to Phases 2, 3, 5 and 7 for the full-product findings, are in [Part IV](#part-iv-full-product-review-findings--implementation-plan).

---

## Part IV: Full-Product Review Findings & Implementation Plan

**Added:** 2026-10-10.  
**Source:** A 20-section review of Quotations as part of the whole product (CRM, sales orders, invoices, search, reports, inventory, permissions). It found 41 problems: 4 P0, 10 P1, 18 P2 and 9 P3.

**Evidence labels used below:**
- **Tested:** reproduced with a temporary backend test against the local stack (the tests were deleted afterwards).
- **Observed:** confirmed by reading the code.
- **Inferred:** follows from the code but was not reproduced.
- **Needs verification:** must be checked during implementation before relying on it.

### IV.0 Plan review response (revision 2)

A review of revision 1 of this plan and of [QUOTATIONS_IMPLEMENTATION_PLAN.md](QUOTATIONS_IMPLEMENTATION_PLAN.md) found defects in the plan itself. Each point was checked against the code at `9cb2acb` before changing the plan. Every point was accepted; the column "Where" says where the fix now lives.

| Review point | Verified | Change made | Where |
|---|---|---|---|
| A1: Phase 9's protected line foreign key breaks Phase 2's delete-and-recreate of lines | Yes: `set_quotation_items` runs `quotation.items.all().delete()` | Lines are now updated in place, matched by ID. `recompute_quotation_totals` no longer rebuilds lines. The ledger's line foreign key is `SET_NULL` with a snapshot, as a second guard. | Impl. plan §3; IV.5 |
| A2: lock and rollback assumptions | Yes: `items` is popped before `super().update()`. A `postgres` marker and `test_concurrency_races.py` pattern exist. | Notes on nested writes and the writable line `id`. Postgres-only rollback and race tests. | Impl. plan §3.2, §3.4 |
| A3: stale clients get prose-only errors | Yes: `BusinessRuleError` accepts `code` and `extra` | Error codes `quotation_lines_locked`, `quotation_fields_locked` and `quotation_not_editable`; a reload message in the UI; read-only fields confirmed | Impl. plan §3.1, §4.1 |
| A4: `recompute_quotation_totals` drops columns | Yes: `_build_items` copies only known keys | Recompute in place, writing only computed fields; a round-trip test over every column | Impl. plan §3.3, §3.4 |
| A5: ledger mapping, double release, UNKNOWN rows, legacy fields | Yes | Explicit line mapping from the created objects; release only unreleased rows under lock and recompute the cache from the ledger (no clamping); support report for UNKNOWN rows; legacy foreign keys computed, not maintained | IV.5 |
| A6: Phase 12 semantics and two sources of truth for expiry | Yes: status-dependent code is in `inventory/item_stock.py`, `sales/services.py`, `sales/serializers.py` and `crm/campaigns.py` | Start-of-phase grep checklist; computed expiry only (no stored EXPIRED, no nightly job); revision snapshots when a sent quote is edited | IV.8 |
| B1: no backend cancel-permission test | Yes | `test_cancel_requires_cancel_permission` | Impl. plan §4.5 |
| B2: tenant scoping of the ledger | Yes: and every new company table needs an RLS migration or `test_rls_coverage.py` fails | Company derived from the quote; tenant test; RLS migration | IV.5 |
| B3: `remaining_total` won't add up | Yes | Defined as indicative, excluding header discount, charges and round-off | IV.8 |
| B4: preview body misses inclusive price and cess | Yes | Full body listed; parity test covers inclusive, cess, discount modes, charges, round-off, non-GST | Impl. plan §6 |
| B5: preview permission contradiction | Resolved: preview-totals needs only `CanViewSalesSurfaces`. Margin is returned only with `CanViewFinancialReports` plus a `warehouse`, and it's based on stock cost. | Contradiction removed. OPEN-38 profit is computed from `expected_price`, not preview margin. | IV.3, Impl. plan §6 |
| B6: other cost leaks | Partly: `render_quotation` prints no cost; the Day Book row carries only `grand_total`. Sales order and challan line serializers also expose `expected_price`. | Leak checklist added, including audit diffs | IV.4 |
| B7: idempotency key reuse after a 4xx | Yes: deterministic 4xx responses are stored, and a reused key with a different body is rejected | Key rotates when the substantive payload changes. `confirm_expired` is excluded from the fingerprint, consistent with the invoice-complete rule in `SALES_HISTORY_PATH_TO_TEN_2026-10-09.md`. The user ID is added to the scope. | IV.6 |
| B8: backfill size and reversibility | Yes | Volume query, batching, and why a no-op reverse is acceptable | IV.5 |
| B9: Phase 11 too big | Yes | Split into 11a, 11b and 11c | IV.7 |
| B10: Phase 2/3 coupling is only a process rule | Yes | Phases 2 and 3 are one PR, plus a release-checklist item | Impl. plan §1, §11 |
| B11: accessibility of locked fields | Yes: disabled MUI inputs aren't focusable | Read-only instead of disabled, `aria-describedby` to the banner; keyboard and screen-reader QA step | Impl. plan §4.2, §10 |
| B12: no measurement of chain-convert removal | Yes | Endpoint call logging and a usage count; 410 only after 4 weeks of zero calls | Impl. plan §8.1, IV.3 |
| C: baseline, subtotal label, `is_expired` on closed quotes, watermark, mobile clients, owners, register note | Yes: HEAD is `9cb2acb` and the change set was committed unchanged in it | Re-baselined; `billing.subtotal`; `is_expired` only for open quotes; watermark note; evidence rule for 410; owner and date columns; register note | Impl. plan header, §2, §7, §11; IV.2, IV.9 |
| D1: ship cost masking and delete lockdown first | — | Phase 8 is now first | IV.2 |
| D2: decide the ledger design before Phase 2 | — | Done: in-place updates are part of Phase 2 | Impl. plan §3 |
| D3: one invariant test | — | `assert_quotation_invariants` helper used across quote tests, plus a Hypothesis state-machine test | IV.5 |
| D4: ship the "Partially converted" chip early | — | Moved into Phase 4 | Impl. plan §5.2 |
| D5: feature-flag the release hooks and Phase 12 | Yes: `flag_enabled(company, key)` in `core/services/feature_flags.py` | `QUOTE_CONVERSION_RELEASE` and `QUOTE_LIFECYCLE` flags | IV.5, IV.8, IV.13 |
| D6: assign tracking IDs now | — | Tracking IDs must be assigned before the first PR. The backlog files haven't been created yet. | Impl. plan §11 |

### IV.1 Finding-to-issue map

14 of the 41 findings were already tracked as OPEN-01 to OPEN-16. The other 27 are new and numbered OPEN-17 to OPEN-43. OPEN-14 moves from P3 to P1, because quotes that never expire inflate the pipeline and block product unit changes.

| # | Pri | Finding | Evidence | Issue | Phase |
|---:|---|---|---|---|---|
| 1 | P0 | Web production build fails | Tested | OPEN-01 | 1 |
| 2 | P0 | A rejected edit still saves header changes | Tested | OPEN-02 | 2 |
| 3 | P0 | Price edits on partially converted quotes are silently dropped | Tested | OPEN-03 | 2 |
| 4 | P0 | Customer and money fields can change after partial conversion | Tested | OPEN-04 | 2, 3 |
| 5 | P1 | Converted quotations can be hard-deleted | Tested | **OPEN-17** | 8 |
| 6 | P1 | Converted quantity is never released | Tested | **OPEN-18** | 9 |
| 7 | P1 | Conversion history is overwritten | Tested | **OPEN-19** | 9 |
| 8 | P1 | Campaign revenue misses most conversions | Observed | **OPEN-20** | 9 |
| 9 | P1 | Internal cost is visible to every viewer | Observed | **OPEN-21** | 8 |
| 10 | P1 | The quotation date is ignored on create | Observed | OPEN-05 | 3 |
| 11 | P1 | The quantity input fights the user | Observed | OPEN-06 | 3 |
| 12 | P1 | Cancel is shown to users who can't cancel | Tested | OPEN-07 | 3 |
| 13 | P1 | A quote can't carry its commercial terms | Observed | **OPEN-22** | 11 |
| 14 | P1 | There is no lifecycle after Draft | Observed | OPEN-14 (now P1) | 12 |
| 15 | P2 | The totals preview is a client-side estimate | Observed | OPEN-09 | 5 |
| 16 | P2 | CRM-created quotes have no number | Observed | **OPEN-23** | 10 |
| 17 | P2 | Editing overwrites the invoice type | Observed | OPEN-15 | 3 |
| 18 | P2 | Header-only API edits skip the totals recalculation | Observed | OPEN-16 | 2 |
| 19 | P2 | Date and customer checks at create are weak | Tested | **OPEN-24** | 10 |
| 20 | P2 | List filters are inconsistent | Observed | OPEN-10 | 4 |
| 21 | P2 | Global search hides quotations | Observed | **OPEN-25** | 13 |
| 22 | P2 | PDFs don't show status or terms | Observed | **OPEN-26** | 13 |
| 23 | P2 | Non-draft quotes open as editable | Observed | **OPEN-27** | 3 |
| 24 | P2 | Errors leak between dialogs | Observed | **OPEN-28** | 3 |
| 25 | P2 | The list shows no conversion progress | Observed | **OPEN-29** | 12 |
| 26 | P2 | The editor differs from other sales editors | Observed | **OPEN-30** | 11 |
| 27 | P2 | Customer price lists are bypassed | Observed | **OPEN-31** | 11 |
| 28 | P2 | The delivery address goes stale | Observed | **OPEN-32** | 3 |
| 29 | P2 | Edits and conversions can race | Inferred | **OPEN-33** | 2 |
| 30 | P2 | Create and convert aren't idempotent | Inferred | **OPEN-34** | 10 |
| 31 | P2 | There is no in-app sharing | Observed | **OPEN-35** | 13 |
| 32 | P2 | The chain-convert endpoint is still live | Observed | OPEN-13 | 7 |
| 33 | P3 | Labels are confusing | Observed | **OPEN-36** | 14 |
| 34 | P3 | The Expired badge uses the browser's date | Observed | OPEN-11 | 6 |
| 35 | P3 | The salesperson list is capped at 100 | Observed | **OPEN-37** | 11 |
| 36 | P3 | Expected profit is stale while editing | Observed | **OPEN-38** | 5 |
| 37 | P3 | No unsaved-changes prompt or edit loading state | Observed | **OPEN-39** | 11 |
| 38 | P3 | The empty state ignores filters | Observed | **OPEN-40** | 14 |
| 39 | P3 | Pagination has no totals or sorting | Observed | **OPEN-41** | 14 |
| 40 | P3 | Report rows link to the list, not the quote | Observed | **OPEN-42** | 13 |
| 41 | P3 | No cancel reason, and a native confirm box | Observed | **OPEN-43** | 14 |

OPEN-08 ("Expected price" label) and OPEN-12 (test gaps) have no separate row above: OPEN-08 is part of finding 1 and finding 9, and OPEN-12 is handled inside every phase.

### IV.2 Phase overview

Owner and target date are blank until planning. No phase starts without both.

| Order | Phase | Theme | Closes | Size | Release gate | Owner | Target |
|---:|---|---|---|---|---|---|---|
| 1 | 8 | Lock down delete and cost visibility | **OPEN-17, 21** | S | Yes | TBD | TBD |
| 2 | 1 | Unblock the build | OPEN-01, 08, part of 11 | S | Yes | TBD | TBD |
| 3 | 2 + 3 (one PR) | Safe backend updates with in-place lines, plus editor fixes | OPEN-02–07, 15, 16 (API), **27, 28, 32, 33** | M | Yes | TBD | TBD |
| 4 | 4 | List filters, plus the "Partially converted" chip | OPEN-10, most of **29** | S | Yes | TBD | TBD |
| 5 | 9 | Per-line conversion ledger | **OPEN-18, 19, 20** | L | Yes | TBD | TBD |
| 6 | 10 | Creation and validation consistency | **OPEN-23, 24, 34** | M | Yes | TBD | TBD |
| 7 | 5 | Server totals preview, plus live profit | OPEN-09, **38** | S | No | TBD | TBD |
| 7 | 6 | Server-decided expiry | rest of OPEN-11 | S | No | TBD | TBD |
| 8 | 11a | Editor route and page shell | **OPEN-30, 39** | M | Product sign-off | TBD | TBD |
| 9 | 11b | Commercial terms | **OPEN-22** | S | Product sign-off (OPEN-22 is P1) | TBD | TBD |
| 10 | 11c | Price lists and salesperson picker | **OPEN-31, 37** | M | No | TBD | TBD |
| 11 | 12 | Lifecycle and revisions | OPEN-14, rest of **29** | L | Product sign-off (OPEN-14 is P1) | TBD | TBD |
| 12 | 13 | Sharing, PDF and navigation | **OPEN-25, 26, 35, 42** | M | No | TBD | TBD |
| 13 | 14 | List polish | **OPEN-36, 40, 41, 43** | S | No | TBD | TBD |
| — | 7 | Product decisions | OPEN-13 and decisions D1–D8 below | — | D1–D4 block Phases 8, 9 and 12 | TBD | before order 1 |

**Order and dependencies:**

```text
Release gate:   8 (backend) ─► 1 ─► 2 + 3 (one PR) ─► 4 ─► 9 ─► 10
After release:  5, 6 ─► 11a ─► 11b ─► 11c ─► 12 ─► 13 ─► 14
Decisions:      7 (D1–D4) must be settled before 8, 9 and 12 start
```

- **Phase 8 goes first.** It is small and low-risk, and closes the only two issues that lose records (hard delete) or expose data (internal cost) today. Its backend part doesn't depend on the build fix or the editor. Its UI part (hiding the cost column) ships inside the Phase 2 + 3 PR.
- **Phase 9 needs Phase 8 and Phase 2.** Phase 8 ensures conversion records never point at a quote that can still be deleted. Phase 2's in-place line updates ensure quote lines referenced by conversion records aren't deleted and recreated on every save.
- **Phase 11.** It reuses `buildQuotationPayload` from Phase 3 and `usePreviewTotals` from Phase 5. If Phase 11a starts before Phases 5 and 6, do that work inside the new editor instead of in the dialog. Each of 11a, 11b and 11c ships on its own.
- **Phase 12 must come after Phase 9**, because the lifecycle states depend on conversion records being correct and reversible.

### IV.3 Additions to existing phases

#### Phase 2: also lock the row in `set_quotation_items` (OPEN-33)
- **Problem (Inferred):** `SalesService.set_quotation_items` checks `converted_quantity` without locking the quote. Both conversion services lock with `select_for_update`, but an edit doesn't. An edit that reads before a conversion commits can delete the lines the conversion just updated, wiping `converted_quantity`.
- **Change:** At the top of `set_quotation_items`, re-fetch the quote with `Quotation.objects.select_for_update().get(pk=quotation.pk)` and run the status and converted-quantity checks on that row. The serializer `update()` from Phase 2 already locks the row; this also covers the CRM path, which calls `set_quotation_items` directly.
- **Part of a larger rewrite.** Revision 2 rewrites `set_quotation_items` to update lines in place, matched by ID. The lock is part of that rewrite; see §3.2 of the [implementation plan](QUOTATIONS_IMPLEMENTATION_PLAN.md#32-code-shape).
- **Tests:** the suite has a Postgres marker. Write the race and rollback tests in `backend/tests/test_quotation_races.py`, following `tests/test_concurrency_races.py` (`django_db(transaction=True)` plus `pytest.mark.postgres`). CI runs them on Postgres 17. See §3.4 of the implementation plan.

#### Phase 3: three more editor fixes (OPEN-27, OPEN-28, OPEN-32)
- **OPEN-27, non-draft quotes open as editable (Observed).** When the loaded quote's status is not `DRAFT`, open the dialog in read-only mode: make every input read-only, hide Save, and show a status banner such as "This quotation is cancelled and can't be edited." Add `phase1.quotationReadOnly` to `en.ts` and `hi.ts`. Use the accessible read-only pattern from §4.2 of the implementation plan (`readOnly` plus `aria-describedby` pointing at the banner), not `disabled`, so keyboard and screen-reader users can still read the values and the reason.
- **OPEN-28, errors leak between dialogs (Observed).** Replace the single `error` state in `QuotationsPage.tsx` with `listError`, `editorError` and `convertError`. Clear each one when its dialog opens and closes. Pass only `convertError` to `ConvertQuotationDialog`. Clear success messages after 5 seconds, or reuse the snackbar pattern other list pages use (Needs verification: check which pattern `SalesOrdersPage.tsx` uses).
- **OPEN-32, the delivery address goes stale (Observed).** Track `addressTouched` (set when the user types in the address field). On customer change, if `!addressTouched`, replace the address with the new customer's `shippingAddress`. If the user did edit it, keep their text and show a small "Address kept from your edit" hint with a "Use customer's address" link.
- **Tests (vitest):** a cancelled quote renders read-only with no Save button; an error in the convert dialog doesn't appear in the editor after reopening; changing customer replaces an untouched address and keeps an edited one.

#### Phase 5: live expected profit (OPEN-38)
- **Problem (Observed):** The editor shows `expected_profit` from the last saved quote, not the current lines.
- **Permissions, now verified at `9cb2acb`:**
  - preview-totals requires only `CanViewSalesSurfaces`, so sales staff get totals.
  - `_preview_bundle` returns margin only when the user has `CanViewFinancialReports` **and** the request sends a `warehouse`.
  - That margin is based on warehouse stock cost, so it is not the quote's expected profit, which uses each line's `expected_price`.
  - Revision 1's "Needs verification" note here is withdrawn; it contradicted Phase 5.
- **Change:** Only for users with `canViewFinancialReports(user)`, compute expected profit on the client: the preview's per-line taxable amounts minus `quantity × expectedPrice` for each line, summed. Show it as "Expected profit (estimate)". Don't send `warehouse` and don't use the preview margin.
- **Matching the backend formula:** use the same formula as `expected_profit_for_lines` in `backend/sales/expected_profit.py`. Needs verification: read that function and copy its revenue basis (taxable value or line total) exactly. Add a test with the same fixture on both sides.
- **After saving,** the server's `expected_profit` replaces the estimate.

#### Phase 7: decisions needed before implementation
| ID | Decision | Recommendation | Blocks |
|---|---|---|---|
| D1 | Which downstream events give converted quantity back to the quote? | Deleting a draft order or invoice, and cancelling an order or invoice made directly from the quote. Not when an order's own invoice is cancelled (the order still exists). | Phase 9 |
| D2 | When a released quote has expired, what status does it return to? | The open status it had before conversion (DRAFT; after Phase 12, ACCEPTED if it was accepted). Expiry is computed (`is_expired`), never stored, so the user must confirm the expiry again to re-convert. | Phase 9, 12 |
| D3 | Should sales staff see internal cost (`expected_price`) at all? | No. Show it only with `CanViewFinancialReports`, matching `expected_profit`. | Phase 8 |
| D4 | Lifecycle states and who can set them | Add stored SENT, ACCEPTED and REJECTED. Sending sets SENT automatically; Accepted and Rejected are manual. Expiry stays computed from `valid_until` (`is_expired`), with no stored EXPIRED status and no nightly job, so there is one source of truth and nothing breaks if a job fails. | Phase 12 |
| D5 | Chain-convert endpoint (OPEN-13) | Deprecate. Log and count calls in release N, including the `User-Agent`, because mobile or integration clients may call it even though the web app doesn't. Return `410 Gone` only after at least 4 weeks of zero calls. | Phase 7 |
| D6 | Should conversion be allowed for a blocked customer's quote at create time? | Block at create and at conversion, as invoices do. | Phase 10 |
| D7 | Credit limit and GST rate checks at conversion | Use the order or invoice rules at conversion time (no new checks on the quote itself). Confirm with finance. | Phase 9 |
| D8 | What happens when a sent or accepted quote is edited? | Keep what the customer received. Before the first edit of a SENT quote, store a snapshot of the sent version (header, lines, totals) and increase a revision number. The quote moves back to DRAFT, and the PDF shows "Rev N". ACCEPTED quotes are not editable; the user must first move them back to DRAFT with a reason, which also stores a snapshot. Without this, a customer who accepted by phone could later be shown a different price with no record of the original. | Phase 12 |

**OPEN-13 implementation (if D5 is accepted):**
1. Release N:
   - add the `Deprecation: true` and `Sunset: <date>` response headers to `QuotationViewSet.convert_chain`;
   - log each call with company ID, user ID, `stop_stage` and `User-Agent`, and count calls in telemetry;
   - remove `convertQuotationChain` from `web/src/api/legacy/sales.ts`.
2. After at least 4 weeks with zero calls: make the action raise a 410 with the message "Convert the quotation to a sales order, then use the sales order screen." If calls continue, find the client from the logs first.
3. Regenerate the OpenAPI snapshot and API types each time (CI diffs both).

### IV.4 Phase 8: Lock down delete and cost visibility

**Closes:** OPEN-17, OPEN-21. **Size:** S. **Release gate:** yes. **Ships first,** before Phase 1. These are the only two issues that lose records or expose data today; both are small and backend-only apart from hiding one column.

#### OPEN-17: Converted quotations can be hard-deleted (Tested)
- **What happens now:** `QuotationViewSet` allows `destroy` with `CanCreateSales` and does not override `perform_destroy`. A test deleted a fully converted quote and got 204. The audit log keeps only the ID, and the quote disappears from campaign attribution and the Day Book.
- **Backend change:** add `perform_destroy` to `QuotationViewSet`, mirroring the invoice and order viewsets:

```python
def perform_destroy(self, instance):
    if instance.status != Quotation.Status.DRAFT or instance.items.filter(converted_quantity__gt=0).exists():
        raise BusinessRuleError("Only an unconverted draft quotation can be deleted; use Cancel instead.")
    super().perform_destroy(instance)
```

- After Phase 9, also refuse deletion when any `QuotationConversion` row exists (released or not), so history is never orphaned. The `PROTECT` foreign key from `QuotationConversion.quotation` in Phase 9 enforces this in the database too.
- **Audit:** Needs verification: how `CompanyScopedViewSet` builds the DELETE audit entry. If it stores only the ID, add the quote number, customer ID and grand total to the payload for quotations.
- **Frontend:** none. The web app has no delete action for quotes (Observed).
- **Tests (`backend/tests/test_quotation_remediation.py`):**
  - DELETE on a fully converted quote returns 400 and the quote still exists.
  - DELETE on a partially converted draft returns 400.
  - DELETE on a cancelled quote returns 400.
  - DELETE on an unconverted draft returns 204.

#### OPEN-21: Internal cost is visible to every viewer (Observed)
- **What happens now:** `QuotationItemSerializer` returns `expected_price` to anyone with `CanViewSalesSurfaces`. `QuotationSerializer.get_expected_profit` deliberately hides profit unless `can_view_expected_profit(request)`, which checks `CanViewFinancialReports`. Cost per line plus the selling price reveals the margin anyway.
- **Same leak elsewhere (Observed, out of scope but worth fixing together):** `expected_price` is also serialized on two line serializers in `backend/sales/phase1_serializers.py` (sales order and delivery challan lines). Apply the same masking there.
- **Backend change:**
  1. In `QuotationItemSerializer.to_representation`, set `expected_price` to `None` when `can_view_expected_profit(self.context.get("request"))` is false. Mark the field `allow_null=True` and regenerate the OpenAPI snapshot and types.
  2. On write, if the user can't view cost, drop any incoming `expected_price` and keep the stored value for that line. Otherwise a sales user's save would reset every cost to 0.
     - **Matching lines:** Phase 8 ships **before** Phase 2, so at first lines are still deleted and recreated, and payloads carry no line IDs. Until Phase 2 lands, match each incoming line to an existing one by product and position (the first unused existing line with the same product). Once Phase 2 lands, match by line `id` instead; the Phase 2 `set_quotation_items` sketch already does this.
     - **New lines:** use the default cost `set_quotation_items` applies today. Needs verification: where that default comes from.
  3. Phase 2's `recompute_quotation_totals` never touches `expected_price`; keep it that way.
- **Frontend change:** in `QuotationsPage.tsx` (and later in the Phase 11 editor), render the cost column only when `canViewFinancialReports(user)` is true, and don't send `expectedPrice` otherwise. Use the existing helper in `web/src/utils/permissions.ts`.
  - This ships inside the Phase 2 + 3 PR, because the web build is broken until Phase 1.
  - In the meantime, sales staff see an empty or 0 cost column. Their saves can't change costs, because the backend drops the field.
- **Other places cost can leak.** Check each one in the Phase 8 PR:

  | Place | Status at `9cb2acb` | Action |
  |---|---|---|
  | Quotation PDF (`render_quotation`) | Observed: no cost or expected-price output | None; add a test that the PDF text has no cost figure |
  | Quotation CSV or Excel export | Observed: `QuotationViewSet` has no export action | None |
  | Day Book (`reporting/transactions.py`) | Observed: quotation rows carry only `grand_total` | None |
  | `expected_profit` on list and retrieve | Observed: already gated by `can_view_expected_profit` | None |
  | Audit log diffs for quote UPDATE | Needs verification: whether `CompanyScopedViewSet`'s UPDATE audit stores field-level diffs that include line `expected_price`, and who can read the audit log | If diffs include cost and the reader permission is wider than `CanViewFinancialReports`, drop `expected_price` from quote audit payloads |
  | Sales order and delivery challan line serializers (`phase1_serializers.py`) | Observed: both serialize `expected_price` | Apply the same read mask and write rule |
  | Tenant backup export (`accounts/tenant_backup.py`) | Observed: exports quotation items | Owner-only feature (Needs verification); no change if so |

- **Tests:**
  - A user without `CanViewFinancialReports` gets `expected_price: null` on quote list and retrieve, and on sales order and challan lines.
  - The same user PATCHes lines without `expected_price`, and with `expected_price: 0`; the stored costs are unchanged in both cases. Run this before and after Phase 2 (product-and-position matching, then ID matching).
  - An owner still sees and can edit `expected_price`.
  - The quotation PDF contains no cost figure.
  - vitest (with the Phase 2 + 3 PR): the cost column is hidden and `expectedPrice` isn't sent for a sales-staff user.

### IV.5 Phase 9: Per-line conversion ledger

**Closes:** OPEN-18, OPEN-19, OPEN-20. **Size:** L. **Release gate:** yes. **Needs decisions:** D1, D2, D7.

#### Problems
- **OPEN-18, converted quantity is never released (Tested).** `_commit_quotation_conversion` adds to `QuotationItem.converted_quantity`, and nothing ever subtracts. After deleting a draft invoice made from a quote, the quote stayed CONVERTED with 10 of 10 units used, so the deal can't be converted again. Sales orders already handle this case for their own invoices with `SalesNotesService.release_order_conversion`; quotes have no equivalent.
- **OPEN-19, conversion history is overwritten (Tested).** `Quotation.converted_invoice` and `Quotation.converted_order` are single foreign keys. Each partial conversion overwrites them, so after two partial orders only the second is linked. Orders and invoices never show their source quote in the UI.
- **OPEN-20, campaign revenue misses most conversions (Observed).** `crm/campaigns.py` `_won_revenue` only counts quotes with `status=CONVERTED` and `converted_invoice` set. Quote → order → invoice, partial conversions, and quotes converted through chain-convert all count as zero.

#### Data model
Add a model in `backend/sales/models.py` (use the same company-scoped base class as `Quotation`):

```python
class QuotationConversion(models.Model):
    class Target(models.TextChoices):
        ORDER = "ORDER", "Sales order"
        INVOICE = "INVOICE", "Sales invoice"
        UNKNOWN = "UNKNOWN", "Unknown (backfilled)"

    class ReleaseReason(models.TextChoices):
        DRAFT_DELETED = "DRAFT_DELETED"
        ORDER_CANCELLED = "ORDER_CANCELLED"
        INVOICE_CANCELLED = "INVOICE_CANCELLED"
        MANUAL_REOPEN = "MANUAL_REOPEN"

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE)
    quotation = models.ForeignKey(Quotation, on_delete=models.PROTECT, related_name="conversions")
    # SET_NULL, not PROTECT: a line whose conversions were all released may later be removed in an edit.
    quotation_item = models.ForeignKey(QuotationItem, null=True, on_delete=models.SET_NULL, related_name="conversions")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    target = models.CharField(max_length=8, choices=Target.choices)
    sales_order = models.ForeignKey("SalesOrder", null=True, blank=True, on_delete=models.SET_NULL, related_name="quotation_conversions")
    sales_order_item = models.ForeignKey("SalesOrderItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    sales_invoice = models.ForeignKey(SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="quotation_conversions")
    sales_invoice_item = models.ForeignKey("SalesItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("accounts.CompanyUser", null=True, on_delete=models.SET_NULL, related_name="+")
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey("accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    release_reason = models.CharField(max_length=24, choices=ReleaseReason.choices, blank=True)
    backfilled = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["company", "quotation"]),
            models.Index(fields=["sales_order"]),
            models.Index(fields=["sales_invoice"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="quote_conversion_qty_positive"),
        ]
```

- **Model names:** the user foreign key target above assumes `accounts.CompanyUser`, which other sales models use for `credit_overridden_by`. Check `created_by` on `Quotation` and use the same target. Use `check=` instead of `condition=` in `CheckConstraint` if the project's Django version is older than 5.1.
- **Why `quotation_item` is `SET_NULL`:**
  - Revision 1 used `PROTECT`. Combined with the old delete-and-recreate of quote lines, that made the first line edit after a released conversion fail with `ProtectedError` (a 500).
  - Phase 2 now updates lines in place, so kept lines keep their IDs. Only a line the user explicitly removes is deleted, and then the conversion row keeps `product` and `unit_price` as a snapshot.
  - `quotation` stays `PROTECT`, so a quote with any conversion history can't be deleted.
- **Company is derived, never passed.** The service sets `company_id = quotation.company_id`, and `clean()` plus a service-level assertion reject a mismatch with the quote, order or invoice company. Tenant tests below cover it.
- **Row-level security.** The table has a `company` foreign key, so add it to `RLS_TABLES` in a new `core/migrations/00xx_rls_quotation_conversion.py`, following `0038_rls_roadmap_tables.py`. Otherwise `tests/test_rls_coverage.py` fails. The latest is `0053_rls_invoice_public_link.py` at `9cb2acb`.
- **Source of truth:** the ledger is the truth. `QuotationItem.converted_quantity` stays as a cached total so existing reads keep working. It is always **recomputed** from the ledger (sum of unreleased rows for the line) inside the quote lock, never adjusted by adding or subtracting. All writes go through one service (below).
- **Legacy fields are computed, not maintained.**
  - `Quotation.converted_invoice` and `converted_order` stop being written once Phase 9 lands (the backfill reads them first).
  - The serializer returns `converted_invoice` and `converted_order` computed from the latest unreleased INVOICE and ORDER conversion, marked deprecated in the help text.
  - The columns are dropped in a later release, after confirming no reader is left. At `9cb2acb` the only readers outside the serializer are `crm/campaigns.py`, rewritten below, and `accounts/tenant_backup.py`, which must stop exporting them in the same release they're dropped.

#### Migration and backfill
The next sales migration comes after `0067_invoice_cancel_reason.py`.
1. **Schema migration:** create `QuotationConversion`, plus the RLS migration above.
2. **Data migration (`RunPython`):** for every `QuotationItem` with `converted_quantity > 0`:
   - If only `quotation.converted_invoice` is set, create one INVOICE row with `quantity = converted_quantity` and `backfilled=True`.
   - If only `converted_order` is set, create one ORDER row.
   - If both or neither are set, create an UNKNOWN row. The real split can't be recovered because the links were overwritten.
   - Leave the line foreign keys empty for all backfilled rows. Copy `product` and `unit_price` from the quote line.
3. **Volume and batching.** Before release, run this count on production to size the migration:

   ```python
   QuotationItem.objects.filter(converted_quantity__gt=0).count()
   ```

   - Iterate with `.select_related("quotation").iterator(chunk_size=1000)` and write with `bulk_create(batch_size=1000)`.
   - If the count is above about 200,000, run the backfill as a management command (`backfill_quotation_conversions`, idempotent, skipping lines that already have rows) instead of inside the migration, so the deploy doesn't hold a long transaction.
4. **Reverse.** The data migration's reverse is a no-op. That's acceptable only because reversing the schema migration drops the whole table; no data is lost, since `converted_quantity` and the legacy foreign keys were never modified by the backfill.
5. **UNKNOWN rows can never be released automatically**, because they have no link to a downstream document. Quotes already stuck in CONVERTED before Phase 9 stay stuck until an owner uses Reopen (below). Give support a report:
   - a management command `report_unknown_quote_conversions` listing company, quote number, line, quantity, and whether the quote's legacy `converted_invoice` or `converted_order` still exists and its status;
   - the same count logged per company by the migration.

#### Service: `backend/sales/quotation_conversions.py`
```python
class QuotationConversionService:
    @staticmethod
    def record(quotation, plan, user, *, order=None, invoice=None): ...
    @staticmethod
    def release_for_order(order, user, reason): ...
    @staticmethod
    def release_for_invoice(invoice, user, reason): ...
    @staticmethod
    def reopen(quotation, user): ...  # manual release of UNKNOWN rows, owner only
```

- **`record`:** called from `_commit_quotation_conversion` instead of writing the legacy foreign keys.
  - **Explicit line mapping.** Change `SalesService.set_items` and `SalesNotesService.set_order_items` to return the created line objects in input order. They come from `bulk_create`, which sets primary keys on Postgres (and SQLite 3.35+).
  - Pair each planned quote line with the returned object at the same index. Don't re-read lines with `.order_by("id")`; ID order isn't guaranteed to match insertion order.
  - Raise `BusinessRuleError` if the counts differ (for example, if `set_items` ever merges lines). Never guess.
  - Create one row per planned line, then recompute each affected line's `converted_quantity` from the ledger and set the quote status.
- **`release_for_order` / `release_for_invoice`:** safe to call twice, for example on cancel followed by delete, or a retried request.
  1. Lock the affected quotes with `select_for_update`, in ID order to avoid deadlocks.
  2. Select the **unreleased** rows for the document with `select_for_update()`. If there are none, return; a second call is a no-op.
  3. Set `released_at`, `released_by` and `release_reason` on those rows.
  4. **Recompute** each affected line's `converted_quantity` as the sum of its unreleased rows. Don't subtract and don't clamp at 0. A negative or inconsistent cache would hide a bug; recomputing makes the invariant hold by construction.
  5. If the quote was CONVERTED and now has remaining quantity, move it back to its open status (decision D2).
  6. Write an audit entry on the quote. There is no legacy-field repointing, because those fields are now computed.
- **`reopen`:** for UNKNOWN backfilled rows. Owner only, with a reason, using the same audit pattern. It releases the chosen rows with reason MANUAL_REOPEN and recomputes the cache as above.
- **Invariant helper.** Add `assert_quotation_invariants(quotation)` in `backend/tests/helpers/` (or the shared test utilities module the suite already uses). For every line:
  - `converted_quantity == sum(unreleased conversion quantities)`;
  - `0 <= converted_quantity <= quantity`.
  
  For the quote, `status == CONVERTED` if and only if every line's remaining quantity is 0, for quotes not CANCELLED.

  Call it at the end of every quotation test that converts, releases or edits, starting in Phase 2 (where the ledger part is trivially empty).

#### Hooks (decision D1)
| Event | Where | Call |
|---|---|---|
| Draft invoice deleted | `SalesInvoiceViewSet.perform_destroy` in `sales/views.py`, inside the existing `transaction.atomic()` next to `release_order_conversion` | `release_for_invoice(instance, user, DRAFT_DELETED)` |
| Invoice cancelled | `SalesService.cancel` in `sales/services.py`, after the existing checks pass | `release_for_invoice(invoice, user, INVOICE_CANCELLED)` |
| Draft order deleted | `SalesOrderViewSet.perform_destroy` in `sales/phase1_views.py`, wrapped in `transaction.atomic()` | `release_for_order(instance, user, DRAFT_DELETED)` |
| Order cancelled | `SalesNotesService.cancel_sales_order` in `sales/notes_services.py` | `release_for_order(order, user, ORDER_CANCELLED)` |

- An invoice made from an order made from a quote does **not** release the quote when cancelled. Only the order's own counters change, through the existing `release_order_conversion`. The quote is released only if the order itself is later cancelled or deleted. The quote → order conversion stays valid in that case.
- A completed invoice that is cancelled releases its quote quantity (recommendation for D1). If finance disagrees, drop the second row of the table; the rest of the design is unchanged.
- **Feature flag.** Each hook runs only when `flag_enabled(company, "QUOTE_CONVERSION_RELEASE")` is true (`core/services/feature_flags.py`).
  - Ledger writing (`record`) is always on, so the history is complete from day one even where releases are off.
  - When a company's flag is later turned on, quotes whose downstream documents were deleted or cancelled while it was off can be fixed with Reopen. The `report_unknown_quote_conversions` command also lists unreleased rows whose order or invoice has since been deleted or cancelled.

#### Serializers and API
- **`QuotationSerializer.conversions`** (read-only): a list of `{id, target, document_id, document_number, document_status, quotation_item, quantity, created_at, released_at, release_reason}`. Prefetch it in `QuotationViewSet.get_queryset` with `prefetch_related("conversions__sales_order", "conversions__sales_invoice")` for retrieve only. The list view only needs the totals from Phase 12.
- **`SalesOrderSerializer` and `SalesInvoiceSerializer.source_quotations`** (read-only): `[{id, number}]` from unreleased conversions.
- **`converted_invoice` and `converted_order` on `QuotationSerializer`:** become computed read-only fields (latest unreleased conversion of each kind), with the same names and types, so clients don't break.
- **New action:** `POST /sales/quotations/{id}/reopen/` with `IsOwner`, body `{reason}`.
- Regenerate the OpenAPI snapshot and API types.

#### Campaign revenue (OPEN-20)
Rewrite `_won_revenue` in `crm/campaigns.py` to collect invoice IDs from all paths, without duplicates:
1. INVOICE conversions on quotes linked to the opportunity.
2. For ORDER conversions on those quotes: invoices with `source_order` set to the order, invoices linked by `SalesOrder.converted_invoice`, and invoices from delivery challans whose `sales_order` is the order (`DeliveryChallan.converted_invoice`).
3. Ignore released conversions. Drop the `status=CONVERTED` filter, so partially converted quotes count.

- Keep the rest of the function: completed invoices only, taxable total, net of completed credit notes.
- **Known limitation:** an order or invoice that was edited after conversion to add lines that weren't on the quote counts in full. Document this in the docstring.

#### Frontend
- **Quote editor:** add a "Conversions" panel listing each conversion with document number (linked), quantity per line, status, and "Released" for released rows.
- **Sales order editor and invoice detail:** add a "From quotation Q-…" chip that links to the quote. This uses `source_quotations`.
- **Convert dialog:** show remaining quantity per line using `quantity - convertedQuantity`. This is unchanged, but now correct after a release.
- **i18n keys:** `phase1.quotationConversions`, `phase1.fromQuotation`, `phase1.conversionReleased`, `phase1.reopenQuotation`.

#### Tests
**Backend:**
- Two partial orders: two ORDER rows; both orders show `source_quotations`; the quote's `conversions` lists both.
- Delete a draft invoice converted from a quote: the quote goes from CONVERTED to DRAFT, the line's converted quantity returns to 0, and it can be converted again.
- Cancel an order converted from a quote: quantity released, with reason ORDER_CANCELLED.
- Quote → order → invoice; cancel the invoice: the quote is **not** released and the order's invoiced quantity is.
- Deleting a quote with any conversion row returns 400, including released rows.
- Backfill: the three cases (invoice only, order only, both) create the expected rows. Running the backfill command twice creates no duplicates.
- Campaign: quote → order → invoice (completed) counts the taxable total; a partial conversion counts; a released conversion doesn't.
- **Double release:**
  - cancel an order, then call `release_for_order` again: the second call changes nothing;
  - cancel then delete a draft invoice: released once;
  - `converted_quantity` never goes negative and the invariant holds.
- **Edit after release:** convert 4 of 10, delete the order (released), then PATCH the quote's lines. With IDs, the lines update in place and the conversion rows still point at them. Without IDs, lines are replaced, the conversion rows' `quotation_item` becomes null, and their `product` and `unit_price` snapshot remains. No 500 in either case.
- **Line mapping:** a conversion with two lines of the same product maps each conversion row to the correct order line (by returned object, not by ID order).
- **Tenant scoping:**
  - a conversion row always has the quote's company;
  - company B's user gets 404 from company A's quote `conversions` and `reopen`;
  - `source_quotations` never lists another company's quote.
- **RLS:** `tests/test_rls_coverage.py` passes with the new table.
- **Flag off:** with `QUOTE_CONVERSION_RELEASE` off, deleting a draft invoice still works and records nothing as released.
- **Invariant (property test):** `hypothesis` is already a dev dependency (`hypothesis>=6.168.3`). Write a `RuleBasedStateMachine` with rules for convert, release-by-cancel, release-by-delete, edit header and edit lines. Call `assert_quotation_invariants` after every step.
- Every Phase 9 test ends with `assert_quotation_invariants`.

**Frontend:** the conversions panel renders the links; the order editor shows the "From quotation" chip.

### IV.6 Phase 10: Creation and validation consistency

**Closes:** OPEN-23, OPEN-24, OPEN-34. **Size:** M. **Release gate:** yes.

#### One create service for every entry point
- **OPEN-23, CRM-created quotes have no number (Observed).** `OpportunityViewSet.quotation` in `crm/views.py` calls `Quotation.objects.create(...)` directly.
  - It skips `DocumentNumberService.next_number`; a number is only assigned at conversion, and conversion doesn't pass `gstin` or `on_date`.
  - It also skips the delivery-address default and the `first_quote` telemetry.
  - It leaves `invoice_type` at the model default (GST), whatever the company's registration.
- **Change:** move the body of `QuotationSerializer.create` into `SalesService.create_quotation(company, header_data, items_data, user)`:
  1. Validate (below).
  2. Default `delivery_address` and `invoice_type`.
  3. Create the quote.
  4. Allocate the number with `resolve_series_gstin` and `on_date=quotation_date`.
  5. Call `set_quotation_items`.
  6. Record telemetry.
- Call it from the serializer and from the CRM action.
- **Invoice type default:** Needs verification: the backend equivalent of the web's `preferredInvoiceType(company.registrationType)`. If there isn't one, add a helper in `sales/services.py` next to the create service and use it in both places.
- **Number at conversion:** keep the `if not quotation.number` fallback in both conversion services for legacy rows, but pass `gstin=resolve_series_gstin(company)` and `on_date=quotation.quotation_date` so it matches create.
- **CRM data:** keep putting the opportunity title in `notes`. After Phase 11 the editor shows notes, so this text is no longer invisible.

#### OPEN-24: Date and customer checks at create are weak (Tested)
- `valid_until` earlier than `quotation_date` is accepted. Add `QuotationSerializer.validate()` that raises a field error on `valid_until`. Also check in `create_quotation` for non-serializer callers.
- A blocked customer can be quoted and only fails at conversion. Reject `customer.status == Customer.Status.BLOCKED` in `validate_customer` and in `create_quotation`, with the message the conversion uses ("Cannot create a quotation for a blocked customer."). This follows decision D6.
- On update, the customer is locked after conversion (Phase 2). For unconverted quotes, run the same check.
- **Frontend:** set the `min` of the Valid Until date picker to the quotation date, and show the backend field error under the field.

#### OPEN-34: Create and convert aren't idempotent (Inferred)
- **Backend:** wrap `create`, `convert` and `convert_to_order` in `QuotationViewSet` with `wrap_idempotent`, as the invoice viewset does.
  - Records are already per company (`begin_record(company=…, scope=…)`).
  - Add the user to the scope as well: `f"quotation_create:{request.user.pk}"`, and the same for `quotation_convert` and `quotation_convert_to_order`. A key can then never replay another user's response.
  - For convert, include the quote ID too (`f"quotation_convert:{user_pk}:{quotation_pk}"`).
- **How `wrap_idempotent` treats failures (checked at `9cb2acb`):**
  - 2xx responses are stored and replayed.
  - **Deterministic 4xx responses (validation errors, business rules) are also stored and replayed.** Transient 4xx responses and 5xx are released.
  - The request body is fingerprinted. Reusing a key with a different body is rejected as a reused key.
  - So reusing one key after the user corrects the form would either replay the old 400 or be rejected. Either way the corrected save fails.
- **Confirm flags are not part of the payload.** For `quotation_convert` and `quotation_convert_to_order`, set `request._idempotency_ignore_keys` to `{"confirm_expired", "confirmExpired"}` before calling `wrap_idempotent`. `request_fingerprint` already honours that attribute.
  - This matches the rule for invoice completion in [SALES_HISTORY_PATH_TO_TEN_2026-10-09.md](SALES_HISTORY_PATH_TO_TEN_2026-10-09.md): a retry that only adds a confirm flag reuses the key.
  - A changed line quantity still conflicts.
- **Frontend key rule:** one key per *substantive payload*.
  - Use `newIdempotencyKey()` and `idempotencyHeaders()` from `web/src/api/client.ts`; the existing invoice calls in `web/src/api/legacy/sales.ts` already take an `idempotencyKey` option.
  - Keep the key in a ref together with a hash of the payload it was made for, excluding confirm flags. Generate a new key only when that hash changes, for example when the user corrects a field after a 400.
  - Reuse the key for:
    - a double click;
    - a resend after a network error, timeout or 5xx;
    - a confirm-flag retry such as ticking "convert anyway" after an expiry error.
  - After a deterministic 4xx with an unchanged form, don't mint a new key for a blind resend; the stored error is the right answer. This follows the same plan's rule.

#### Tests
- A CRM quote gets a number from the series, the company's invoice type, and the customer's shipping address.
- `valid_until < quotation_date` returns 400 with a field error.
- Creating a quote for a blocked customer returns 400.
- Repeating a create or convert with the same `Idempotency-Key` and body returns the same response and creates nothing new.
- A create that fails with 400, then succeeds with a corrected body and a **new** key, creates exactly one quote.
- A convert that fails because the quote expired, then is resent with the **same** key plus `confirm_expired=true`, succeeds and creates exactly one invoice. A resend with the same key and a different line quantity is rejected as a reused key.
- The same key used by a different user doesn't replay the first user's response.
- vitest:
  - after a 400, correcting a field and saving sends a different `Idempotency-Key`;
  - resending an unchanged form, retrying after a network error, or ticking the expiry confirmation sends the same one.

### IV.7 Phase 11: Full-page quotation editor

**Closes:** OPEN-22, OPEN-30, OPEN-31, OPEN-37, OPEN-39. **Size:** L in total, split into three releases so each can ship on its own:

| Part | Scope | Closes | Release gate |
|---|---|---|---|
| **11a** | Route and editor shell: new routes, `QuotationEditorPage.tsx` with customer picker, `DraftLineTable`, totals panel, sticky footer; read-only mode; unsaved-changes prompt and loading state; remove the dialog editor | OPEN-30, OPEN-39 | Product sign-off |
| **11b** | Commercial terms section | OPEN-22 | Product sign-off; OPEN-22 is P1, so if product won't accept shipping without terms, 11a and 11b join the gate |
| **11c** | Customer price lists and the searchable salesperson picker | OPEN-31, OPEN-37 | No |

The approach below is grouped by part.

#### Problems
- **OPEN-30, the editor differs from other sales editors (Observed).** Quotes use a dialog with their own line table. Sales orders (`SalesOrderEditorPage.tsx`) and invoices use full-page editors built on `DraftLineTable`. The dialog is cramped on phones.
- **OPEN-22, a quote can't carry its commercial terms (Observed).** The model and serializer have `notes`, `terms_text`, `payment_terms_days`, `invoice_discount`, `invoice_discount_mode`, `additional_charges`, `charges_hsn`, `charges_gst_rate` and `auto_round_off`. None of them can be entered in the UI. Notes on CRM-created quotes are invisible.
- **OPEN-31, customer price lists are bypassed (Observed).** The UI fills the catalogue selling price and always sends it, so `masters.pricing.resolve_unit_price` never applies. The invoice editor uses `resolveListUnitPrice` from `@/utils/priceList` with the customer's `priceList`.
- **OPEN-37, the salesperson list is capped at 100 (Observed).** Employees are loaded with `pageSize: 100`.
- **OPEN-39, no unsaved-changes prompt or edit loading state (Observed).**

#### Approach
**11a: route and shell**
- New routes in `web/src/App.tsx`: `/sales/quotations/new` and `/sales/quotations/:id/edit`, rendering a new `QuotationEditorPage.tsx`.
  - Replace the current `sales/quotations/new` redirect to `?create=1`.
  - Keep `?create=1` working as a redirect to `/sales/quotations/new` for old links.
  - `/sales/quotations/:id` opens the editor read-only for non-draft quotes, and for draft quotes too until the user clicks Edit (same behaviour as orders, Needs verification).
- Model the page on `SalesOrderEditorPage.tsx`:
  - customer picker at the top;
  - `DraftLineTable` for lines;
  - a terms section;
  - the `usePreviewTotals` panel from Phase 5;
  - a sticky footer with Save and Convert.
- **Payload:** build it with `buildQuotationPayload(form, mode)` from Phase 3, including line `id`s. Partially converted quotes still lock the line table and money fields (Phase 2 whitelist). Locked fields use the accessible read-only pattern from Phase 3.
- **Unsaved changes:** track a dirty flag. Block navigation with the router's blocker and a `ConfirmDialog` ("Discard changes?"). Show a skeleton while the quote loads; disable Save until it has loaded.
- **Remove the dialog editor** from `QuotationsPage.tsx` once the page ships. Keep the list, filters and row actions.

**11b: commercial terms**
- **Payload:** extend `buildQuotationPayload` with the commercial fields. They're blocked after partial conversion except `notes` and `terms_text` (Phase 2 whitelist).
- **Commercial terms section:**
  - notes;
  - terms (prefilled from the company's default quote terms if one exists; Needs verification);
  - payment terms in days;
  - header discount with mode;
  - additional charges with HSN and GST rate;
  - round-off toggle.
- The Phase 5 preview body already sends these header fields, so totals update live.

**11c: price lists and salesperson**
- **Price lists:** when a product is added or the customer changes, set the unit price with `resolveListUnitPrice(priceLists, customer.priceList, product)`, as `NewInvoicePage.tsx` does. Mark the price as user-edited once typed, so a customer change doesn't overwrite it, and show a "Price list applied" hint.
- **Salesperson:** use a searchable server-side picker. If there's no shared employee picker yet, build it with the `usePartySearch` pattern (debounced, minimum 2 characters, page size 100) against the employees endpoint.

#### Tests
**vitest (`QuotationEditorPage.test.tsx`):**
- 11a: create sends the selected date; a partially converted quote locks lines and money fields (read-only and focusable); navigating away with changes shows the prompt; a cancelled quote opens read-only.
- 11b: create sends terms and charges; after partial conversion only notes and terms stay editable.
- 11c: a price-list price is applied and survives a customer change once edited; the salesperson search finds an employee beyond the first 100.

**Playwright (if the e2e suite covers sales):** create a quote, add terms, save, reopen, check the terms persist and print on the PDF (after Phase 13).

### IV.8 Phase 12: Lifecycle and expiry

**Closes:** OPEN-14, rest of OPEN-29. **Size:** L. **Needs decisions:** D2, D4, D8. **Release gate:** product sign-off (OPEN-14 is P1).

#### Problems
- **OPEN-14, there is no lifecycle after Draft (Observed).** Quotes are DRAFT, CONVERTED or CANCELLED only. Expired quotes stay open forever, inflate the pipeline, and keep blocking product unit changes: `inventory/item_stock.py` treats any DRAFT `QuotationItem` as "an open quotation".
- **OPEN-29, the list shows no conversion progress (Observed).** A partially converted quote looks like a new draft and shows the full total. Sales orders already have `PARTIALLY_CONVERTED`.

#### Step 0: usage checklist (do this before sizing the phase)
New statuses change what "open" and "draft" mean outside this module. At the start of the phase, re-run these searches on the current HEAD and list every hit in the phase PR description, with a decision for each:

```powershell
rg -n "Quotation\.Status|quotation__status|QuotationItem\.objects|Quotation\.objects" backend --glob "*.py" --glob "!**/migrations/**"
rg -n -i "quotation" backend --glob "*.py" --glob "!tests/**" --glob "!**/migrations/**" -l
rg -n "'DRAFT'|\"DRAFT\"" web/src/pages/sales/QuotationsPage.tsx web/src/pages/sales/ConvertQuotationDialog.tsx web/src/pages/crm web/src/pages/reports
```

At `9cb2acb` the hits were:

| Place | Depends on status? | Change in Phase 12 |
|---|---|---|
| `sales/services.py`: `set_quotation_items`, both convert services, `cancel_quotation`, `_commit_quotation_conversion` | Yes | Use the status sets below |
| `sales/serializers.py`: `QuotationSerializer.update` | Yes | `EDITABLE` |
| `inventory/item_stock.py` unit-change guard `("sales", "QuotationItem", "quotation__status", ("DRAFT",), …)` | Yes | Open **and not expired**; see below |
| `crm/campaigns.py` | Yes (`CONVERTED`); rewritten in Phase 9 | Re-check after Phase 9 |
| `reporting/transactions.py` (Day Book) | No: lists all statuses and shows `status` as text | Make sure new status values display; no filter change |
| `search/views.py` | No: returns `status` as text | None |
| `accounts/tenant_backup.py` | Copies rows, including status | Restore must accept the new values; add a backup/restore round-trip test |
| `masters/models.py` (customer and product delete guards) | No: checks existence only | None |
| Web: `QuotationsPage.tsx`, `ConvertQuotationDialog.tsx`, `OpportunitiesPage.tsx`, `CampaignsPage.tsx`, `CustomerLedgerPage.tsx` | Status chips and checks | Update chips and checks |

At `9cb2acb` there are no quotation references in dashboards, Customer 360 or insights code. Confirm that again in Step 0, because those areas change often.

#### Status model
- Add stored `SENT`, `ACCEPTED` and `REJECTED` to `Quotation.Status`. No data migration is needed, since existing rows stay DRAFT, CONVERTED or CANCELLED.
- **No stored EXPIRED status and no nightly job** (decision D4, revised). Expiry is computed from `valid_until` and the server date by the Phase 6 `is_expired` field. Revision 1 planned both a stored EXPIRED status and the computed field; that's two sources of truth that disagree whenever the job is late or fails, and a failed job would leave statuses the UI can't explain.
- Add class-level sets on `Quotation` and use them everywhere instead of comparing with `DRAFT`:

```python
EDITABLE = {Status.DRAFT}
CONVERTIBLE = {Status.DRAFT, Status.SENT, Status.ACCEPTED}
OPEN = {Status.DRAFT, Status.SENT, Status.ACCEPTED}
```

- **Expiry in queries:** add a queryset method `Quotation.objects.expired(on=None)` returning `status__in=OPEN, valid_until__lt=today`, and `.live()` for open and not expired.
  - The list filter `expired=true` and the "Open" filter use these.
  - `is_expired` uses `obj.status in Quotation.OPEN`.
- **Unit-change guard:** expired quotes should stop blocking product unit changes. The guard tuple in `inventory/item_stock.py` takes a status field and a list of values. Needs verification: whether the guard format can take an extra filter. If not, extend it to accept a `Q` object, and use `Q(quotation__status__in=OPEN) & (Q(quotation__valid_until__isnull=True) | Q(quotation__valid_until__gte=today))`.
- **Transitions:** put each one in `SalesService.set_quotation_status(quotation, target, user, reason="")`. It checks an allowed-transitions table and writes an audit entry.
  - DRAFT → SENT: automatic when shared (Phase 13), or a manual "Mark as sent" action.
  - SENT → ACCEPTED or REJECTED: manual, with an optional reason.
  - SENT → DRAFT: on edit, with a revision snapshot (below).
  - ACCEPTED → DRAFT: only through an explicit "Reopen for changes" action with a required reason, which also snapshots. ACCEPTED quotes are not directly editable.
  - Released conversions return the quote to the open status it had (D2).
  - Expired quotes keep their stored status; the UI shows "Expired" from `is_expired`.

#### Revisions (decision D8)
Editing a quote the customer has already received must not lose what they received.
- Add `Quotation.revision` (`PositiveIntegerField`, default 0).
- Add a `QuotationRevision` model:
  - `company` (derived from the quote);
  - `quotation` (`PROTECT`);
  - `revision`;
  - `snapshot` (JSON of header, lines and totals, built with `QuotationSerializer` without the masked cost fields);
  - `reason`, `created_by`, `created_at`.
  
  It has a `company` foreign key, so add it to an RLS migration.
- When a SENT or ACCEPTED quote moves back to DRAFT, store the snapshot of the current version and increase `revision`.
- The PDF prints "Rev N" when `revision > 0`. The editor shows a "Previous versions" list with read-only views of each snapshot.

#### Conversion progress (rest of OPEN-29)
Phase 4 already shows the "Partially converted" chip. Phase 12 adds:
- `conversion_state`: NONE, PARTIAL or FULL, from line quantities.
- `remaining_total`, defined as **indicative**: the sum over lines of `(quantity − converted_quantity) / quantity × line_total`.
  - `line_total` is the calculated line amount on `DocumentLineModel`, alongside `taxable_amount`, `cgst`, `sgst`, `igst` and `cess`. `cess_amount` is the per-unit specific-cess *input*, not a total, so don't sum it.
  - It deliberately excludes header discount, additional charges and round-off, so it won't add up to `grand_total` minus converted value.
  - The UI labels it "≈ Remaining (before header discount and charges)" and never uses it for accounting.
  - Needs verification: whether `line_total` is before or after a header discount applied in "before tax" mode.
- Annotate both in `get_queryset` for the list to avoid N+1 queries.

#### Feature flag
All Phase 12 behaviour is behind `flag_enabled(company, "QUOTE_LIFECYCLE")`. With the flag off:
- the new actions are hidden and return 403;
- statuses stay DRAFT, CONVERTED and CANCELLED;
- the unit-change guard ignores expiry.

The status sets, the computed expiry queryset methods and `conversion_state` are safe to ship unflagged.

#### Frontend
- **List:**
  - status chips for every state, an "Expired" chip from `isExpired`, the Phase 4 "Partially converted" chip, and "≈ Remaining ₹…" when `conversion_state` is PARTIAL;
  - filter options for each stored status plus "Expired";
  - the "Open" filter maps to `.live()` (backend: accept `status=OPEN` and `expired=true` in the Phase 4 validation).
- **Row and editor actions:** Mark as sent, Mark accepted, Mark rejected (with a reason dialog), Reopen for changes (with a reason), shown according to the transitions table.
- **i18n:** a status key for each state, plus action, reason and revision labels, in `en.ts` and `hi.ts`.

#### Tests
- Each allowed transition succeeds; each disallowed one returns 400.
- Editing a SENT quote stores a revision snapshot, increases `revision`, and moves it to DRAFT. The snapshot matches what was sent, including the line prices.
- An ACCEPTED quote can't be edited without Reopen; Reopen requires a reason and snapshots.
- `is_expired` and `.expired()` agree for open quotes; closed quotes are never expired.
- An expired open quote no longer blocks a product unit change; an unexpired one still does.
- `conversion_state` and `remaining_total` are correct for none, partial and full conversions, with a header discount present (to prove it's excluded).
- Tenant backup and restore round-trips the new statuses, `revision` and `QuotationRevision` rows.
- With `QUOTE_LIFECYCLE` off, the new actions return 403.
- vitest: chips and actions per status; the Expired chip comes from `isExpired`.

### IV.9 Phase 13: Sharing, PDF and navigation

**Closes:** OPEN-25, OPEN-26, OPEN-35, OPEN-42. **Size:** M.

- **OPEN-25, global search hides quotations (Observed).** `search/views.py` returns a `quotations` list, but `universalSearch` in `web/src/api/legacy/misc.ts` only maps `invoices` (and other kinds it already knows). Add `quotations?: Array<{id, number, status}>` to the response type and map each row to `{title: number, subtitle: t('nav.quotations'), path: '/sales/quotations/{id}'}`. Test with a vitest case on `universalSearch` using a mocked response.
- **OPEN-26, PDFs don't show status or terms (Observed).** `render_quotation` in `backend/sales/pdf/note_documents.py`:
  - prints notes but not `terms_text`, and doesn't show status;
  - add a diagonal watermark for CANCELLED and CONVERTED (and REJECTED after Phase 12), and "EXPIRED" when `is_expired` is true (computed, not a stored status);
  - the watermark is a visual cue, not a tamper-proof control: anyone can edit a PDF. Don't rely on it for legal purposes. The audit trail and the quote's status in the app are the record;
  - add a terms block after the totals;
  - print `valid_until` in the header if it isn't printed already (Needs verification).
  - Tests: render a cancelled quote and assert the watermark text in the PDF bytes (follow how existing PDF tests read text; Needs verification).
- **Cancelled-quote downloads (Tested):** keep allowing the download (it's the record), but the watermark makes the status clear.
- **OPEN-35, there is no in-app sharing (Observed).**
  - Reuse `ShareInvoiceDialog.tsx`. Generalise it to accept a document kind, or add a thin `ShareQuotationDialog` that passes the quote PDF URL and a message template.
  - Backend: if invoices use a public-link endpoint (see `test_invoice_public_link.py`), add the same for quotes, scoped to the PDF and expiring with `valid_until`. Needs verification: whether the invoice share flow needs a public link or sends the file.
  - Sharing moves a DRAFT quote to SENT (Phase 12) and records an audit entry with the channel.
- **OPEN-42, report rows link to the list, not the quote (Observed).** In `backend/reporting/transactions.py`, change the quotation row's `source_path` from `"/sales/quotations"` to `f"/sales/quotations/{qtn.id}"`. Check the customer ledger page builds its links from `source_path` (Needs verification) rather than hard-coding the list path.

### IV.10 Phase 14: List polish

**Closes:** OPEN-36, OPEN-40, OPEN-41, OPEN-43. **Size:** S.

- **OPEN-36, labels are confusing (Observed).**
  - The status filter says "Open" while the row chip says "Draft". After Phase 12, "Open" means the open-status group and the chips show the real status; before that, rename the filter option to "Draft".
  - Rename the row action "Convert" to "Create invoice", and "To Order" to "Create sales order".
  - The empty salesperson option should read "None", not "All".
- **OPEN-40, the empty state ignores filters (Observed).** When any filter is set and the list is empty, show "No quotations match these filters" with a "Clear filters" button. Show the "Create your first quotation" message only when no filters are set.
- **OPEN-41, pagination has no totals or sorting (Observed).**
  - Show "Showing 1–50 of N" using the `count` from the paginated response.
  - Add `ordering` to `QuotationViewSet` with an allow-list: `quotation_date`, `valid_until`, `grand_total`, `number`, `customer__name`, each with `-` for descending; default `-quotation_date,-id`.
  - Make those columns sortable in the table. Follow the sales orders or invoice list if one already does this (Needs verification).
- **OPEN-43, no cancel reason, and a native confirm box (Observed).**
  - Add `cancel_reason = CharField(max_length=500, blank=True, default="")` to `Quotation`, as migration `0067_invoice_cancel_reason.py` did for invoices.
  - `cancel_quotation(quotation, user, *, reason="")` stores it; the `cancel` action reads `reason` from the body.
  - Replace `window.confirm` with `ConfirmDialog` plus a reason field. Follow the invoice cancel UI that sends `cancelReason`.
  - Show the reason on cancelled quotes and on the PDF watermark line.
- **Tests:** a cancel with a reason stores it; the empty state with filters shows "Clear filters"; `ordering=-grand_total` sorts; an unknown ordering field is ignored or returns 400 (match the invoice list).

### IV.11 Test matrix (new phases)

| Area | Backend (pytest) | Web (vitest) | Manual QA |
|---|---|---|---|
| Delete lockdown (8) | 4 delete cases | — | Try DELETE via API as staff |
| Cost masking (8) | read mask on quote, order and challan lines; write preserve before and after Phase 2; owner sees; PDF has no cost | Cost column hidden and not sent for staff | Log in as sales staff, open a quote |
| Conversion ledger (9) | release cases, double release, edit after release, line mapping, tenant scope, RLS coverage, flag off, backfill idempotent, Hypothesis state machine | Conversions panel, "From quotation" chip | Partial order ×2, delete one, reconvert |
| Invariants (2 onwards) | `assert_quotation_invariants` at the end of every quote test | — | — |
| Campaign revenue (9) | 3 attribution cases | — | Campaign ROI after quote → order → invoice |
| Create consistency (10) | CRM number/type/address, dates, blocked customer, idempotency incl. corrected-body rotation, confirm-flag reuse and per-user scope | Valid Until `min`; key rotates only on a changed form | Create from a won opportunity |
| Editor (11a–c) | — | 11a: 4, 11b: 2, 11c: 2 cases | Full create/edit on a phone-width screen |
| Lifecycle (12) | transitions, revision snapshots, computed expiry, unit-change guard, progress fields, backup round-trip, flag off | chips, actions | Send → edit (revision) → accept → convert; let one expire |
| Share/PDF/nav (13) | watermark, terms, `source_path` | search mapping | Search for a quote number; open from Day Book |
| Polish (14) | cancel reason, ordering | empty state, sort | Cancel with reason |

### IV.12 Manual QA additions

Run these after the Part III QA script:
1. As sales staff, open a quote. The cost column is not shown, and saving doesn't change costs (check as owner).
2. Convert 4 of 10 units to an order and 3 to another order. The quote shows both orders under Conversions, and each order shows "From quotation".
3. Delete the second order (draft). The quote shows 4 of 10 converted, and a "Released" row.
4. Convert the remaining 6 to an invoice, then delete that draft invoice. The quote goes back to Draft with 6 remaining.
5. Try to delete the quote through the API. Expect 400.
6. Create a quote from a won opportunity. It has a number and the right invoice type.
7. Complete an invoice made through quote → order → invoice. The campaign ROI includes it.
8. Global search for the quote number finds the quote and opens it.
9. Cancel a quote with a reason. The PDF shows a CANCELLED watermark.
10. Cancel an order converted from a quote, then try to delete it. The quote's converted quantity is released once, not twice.
11. After step 3 (a released conversion), edit the quote's lines and save. The save succeeds, and the Conversions panel still shows the released row.
12. Send a quote, edit its price, and open "Previous versions". The sent version shows the original price, and the PDF shows "Rev 1".
13. As sales staff, try to create a quote with a past Valid Until, fix the date, and save again. Exactly one quote is created.

### IV.13 Rollout

- **Phase 8** ships first and behind no flag. The delete block and cost masking are safe for every client. Its backend part doesn't wait for the web build fix.
- **Phases 2 + 3** ship as one PR (see §11 of the implementation plan).
- **Phase 9:**
  1. Run the volume count. Deploy the schema, RLS and backfill migrations, with `record` always on and `QUOTE_CONVERSION_RELEASE` off for every company. Nothing releases yet.
  2. Check the per-company UNKNOWN counts with `report_unknown_quote_conversions`, and hand the list to support.
  3. Turn the flag on for internal or pilot companies, then for everyone.
  4. If the hooks misbehave, turn the flag off. The ledger rows are harmless on their own.
- **Phase 12:** behind `QUOTE_LIFECYCLE`, per company. The new statuses change what "open" means for the unit-change guard and reports.
  - Ship the list chips in the same release as the backend statuses, so users never see a status the UI can't display.
  - Announce the change in release notes.
  - Turn the flag on for pilot companies first.
- **Phase 7 decision D5:** deprecation headers and call logging in release N; 410 only after at least 4 weeks of zero calls.
- **New company tables** (Phase 9 `QuotationConversion`, Phase 12 `QuotationRevision`): each ships with its RLS migration in the same PR.
- **Every phase that changes serializers or actions:** regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` in the same PR (CI diffs both).

---

## Scorecard

Scores reflect the code as it stands today. "Target" is the expected score after Phases 1–6 of the implementation plan.

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

**Full-product score.** The table above scores the screen itself. The full-product review in Part IV also scores CRM, search, reports, deletes and permissions. On that wider view the module scores **4.5 / 10 now**. The expected score is about 7.5 after the release-gate phases (8, 1–4, 9, 10) and about 8.5 after Phases 11a–14.

### Release gate
Release only when all of these are true:
- Phase 8 in Part IV is merged (it ships first), closing OPEN-17 and OPEN-21.
- Phases 1–4 of the implementation plan are merged, with Phases 2 and 3 as one PR. This closes OPEN-01 to OPEN-08, OPEN-10, OPEN-15 and OPEN-16, plus the Phase 2 and 3 additions in Part IV (OPEN-27, OPEN-28, OPEN-32, OPEN-33).
- Phases 9 and 10 in Part IV are merged, closing OPEN-18 to OPEN-20, OPEN-23, OPEN-24 and OPEN-34. Phase 9's release hooks may still be flagged off for some companies, but the ledger must be writing.
- Decisions D1–D4 in Part IV are recorded.
- Every release-gate phase has a named owner and a date in IV.2.
- Product has signed off shipping without OPEN-14 (lifecycle) and OPEN-22 (commercial terms), or Phases 11a, 11b and 12 are merged too.
- `npm run lint` and `npm run build` pass.
- The regression tests for those phases are in place and green, including the Postgres-only race tests and `tests/test_rls_coverage.py` in CI.
- The manual QA script in the implementation plan (including the keyboard and stale-tab steps) and the additions in Part IV.12 pass.
- Register IDs are assigned in `qos/backlog/` and the master register, and every PR cites one.
