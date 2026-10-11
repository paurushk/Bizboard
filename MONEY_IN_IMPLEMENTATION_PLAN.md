# Money In (Customer Receipts) Module: Audit & Implementation Plan

**Module:** Money In / Customer Receipts (`web/src/pages/sales/ReceiptsPage.tsx`, `backend/payments/views.py` `CustomerReceiptViewSet`)
**Product:** Bizboard ERP & POS
**Date:** 2026-10-11 (implementation of OW-1..OW-14 complete; verification recorded in section 6)
**Status of the work tree:** uncommitted. Tracked as [QOS-0118](qos/backlog/QOS-0118.yaml).

---

## 1. Executive Summary & Verdict

"Money In" is the Accounts Receivable settlement and cash-inflow register. It links customer money to open sales invoices, till/bank accounts and GL journals.

### Verdict: 🟢 READY, after the commit and operator steps in section 7

The first revision of this plan marked work COMPLETED that the code did not support. A review against the code found nine mismatches (section 3). All 14 open items from that review (OW-1..OW-14, section 5) are now implemented and tested. The exit checklist in section 7 lists what remains: committing, and running the migration.

---

## 2. Scope & Personas

* **Purpose:** record and reconcile customer cash/bank payments against outstanding balances and sales invoices.
* **Personas:** retail cashier (immediate settlement), AR accountant (bulk, bank reconciliation), owner (daily inflow).
* **Boundary:** Accounts Receivable inflows only. Owner equity, vendor refunds and scrap income are out of scope.
* **Pre-existing, not changed here:** cheque lifecycle (Pending → Cleared → Bounced, dishonour fee, Section 138 notice), gateway receipts (refund, not void), idempotent create, period gate on create.

### Flow

```text
[Money In list] ──(search, mode, status, date range, totals, export CSV)
   ├─ New receipt → customer / date / amount / mode → optional invoice or oldest-first
   │                → POST /payments/receipts/  (one transaction: receipt + allocation)
   ├─ Void (needs cancel permission) → reason (required, 3-500 chars) → POST .../void/
   │                → allocations reversed, reversing JE dated today, audit fields stored
   └─ Receipt number → voucher dialog (invoices applied) → print / download A4 or thermal PDF
```

### Cross-module impact
* **Sales invoices:** allocation changes `balance` and `payment_status`; void restores them (tested, including a settlement discount).
* **GL / customer ledger:** Dr Cash (1100) or bank, Cr Customer Advances (2300); allocation moves it to Debtors. Void posts a reversal dated *today* (R2-004), possibly in a later period than the original.
* **POS shift:** a cash receipt counted in a closed till cannot be voided here.
* **Banking:** a receipt matched to a bank line cannot be voided until it is unmatched.

---

## 3. Review Findings: Earlier Plan vs Code (all resolved)

| # | Earlier claim | What the code showed | Resolution |
|---|---|---|---|
| F1 | Void reason is mandatory | UI sent an empty string; server accepted a blank reason | OW-1: server returns 400 under 3 characters; UI disables Void |
| F2 | Void was unrestricted; fixed by a frontend gate | Server already enforced `CanCancelDocuments`; the frontend change only hid the button | Plan reworded; the real gap was the missing reason (OW-1). Permission test added |
| F3 | Date filters added | Backend only; UI never sent them | OW-3: From/To date pickers wired to the list, totals and export |
| F4 | KPI cards show collected, allocated, advance | Page-only `reduce`; counted voided, bounced and pending-cheque receipts | OW-2: server `summary/` endpoint over all pages with the same filters |
| F5 | Walk-in rule enforces 100% allocation | Client-only, matched `name.includes('walk-in')`, did not require full allocation | OW-4: server rule on `Customer.is_pos_walk_in` |
| F6 | "Period-validated" date picker | Plain date input | OW-3b: no future dates (UI and server), backdated hint, server period warnings shown |
| F7 | Instant thermal/A4 print | `window.print()` on a dialog | OW-5: server-rendered voucher PDF, A4 and 80 mm thermal |
| F8 | Tests 9/9 passed | Not re-verified; no backend tests | OW-8: 35 backend tests added, frontend tests rewritten (32), results in section 6 |
| F9 | Verdict 🟢 | Self-certified | Re-earned against section 7 |

---

## 4. What Was Built

### 4.1 Backend (`backend/payments/`)

| Area | Change |
|---|---|
| Model | `CustomerReceipt.void_reason`, `voided_at`, `voided_by`; composite index `(company, mode, receipt_date)`. Migration `0038_receipt_void_audit` (additive; backfills the reason from old `VOIDED: ...` note lines) |
| Void | `PaymentService.void_receipt`: reason required (3-500 chars, whitespace collapsed), stored in the new fields and in the `customer_receipt.voided` audit event with the reversal date. Free-text `notes` is no longer touched. Idempotent: a repeat void keeps the first reason |
| Void guards | Refused for a receipt matched to a bank line (`ReconMatch` or AA transaction) and for a cash receipt whose till shift is CLOSED. Gateway and refunded receipts were already refused |
| Filters | `customer`, `mode`, `status`, `date_from`, `date_to`, `q`. Dates parsed (400 on bad input or an inverted range), `mode` and `status` checked against choices (400), `q` capped at 100 characters. Filters apply to `list`, `summary` and `export` only, so detail routes ignore stray query params |
| Search | Receipt number and customer name: contains. UTR and reference: starts-with. Phone: contains, only when the query looks like digits |
| `summary/` | Collected, cheques pending, allocated, advance, counted and excluded rows, across every page. Voided, refunded and bounced receipts are excluded; pending cheques are reported apart from collected money |
| `export/` | CSV of the filtered set (not one page), formula-injection safe (`csv_safe`), capped at 20,000 rows with a clear 400 |
| `voucher/` | Receipt voucher PDF (`receipt_voucher.py`): company header and GSTIN, amount in words, payment details, invoices applied, advance, signature block. `?layout=thermal` for an 80 mm roll. VOIDED receipts are stamped with the reason |
| Create | Optional `sales_invoice` + `allocate_amount` applied in the same transaction as the receipt (a failed allocation leaves no receipt behind). Future receipt dates rejected |
| Walk-in rule | A manual receipt for a customer with `is_pos_walk_in` must be fully applied (oldest-first or one invoice) or the whole request rolls back. Uses the existing flag, so renaming the customer does not bypass it |
| Serializer | New read-only fields: `customer_is_walk_in`, `allocation_lines`, `void_reason`, `voided_at`, `voided_by_name`. `allocated` and the lines come from one prefetch, removing a per-row query |
| OpenAPI | Filter parameters, summary schema, CSV and PDF responses documented; `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` regenerated |

### 4.2 Frontend (`web/src/pages/sales/`)

| Area | Change |
|---|---|
| Totals | Four cards from `summary/`: Collected, Allocated, Advance held, Cheques pending, with a note stating how many receipts are left out. If the call fails the cards hide and the list still works |
| Filters | Search, mode, status (Posted, Voided, Refunded), From date, To date, Clear, Export CSV. A back-to-front range holds the request and disables export |
| Void | `VoidReceiptDialog` (one component; bottom drawer on narrow screens). Void stays disabled until the reason is valid; the dialog states that the reversal posts today and that invoices will reopen; a refused void keeps the dialog open with the typed reason |
| Voucher | `ReceiptVoucherDialog`: details, invoices applied, void reason and who voided it, paper choice (A4 or thermal), Print and Download PDF |
| Status | Separate Status column with colour-coded chips (Posted, Voided, Refunded) and cheque chips (pending, cleared, bounced) |
| Create | Receipt and invoice allocation are one request. Walk-in notice and block. Future dates blocked, backdated hint. Server notices (period already complete) shown after save |
| Accessibility | Receipt number buttons say which voucher and customer they open; the actions column has a screen-reader header; heading levels fixed; the void dialog focuses the reason field; focus returns to the receipt number on close |
| i18n | All new strings in `en` and `hi` |

---

## 5. Open Work Items: Final Status

| ID | Pri | Item | Status | Notes |
|---|---|---|---|---|
| OW-1 | Blocker | Mandatory, structured void reason | **Done** | Server 400 for blank/short/over-long; fields and audit metadata; UI disabled until valid |
| OW-2 | Blocker | Server-side summary | **Done** | Tested with 55+ rows, voided, bounced and pending cheques, live allocations only |
| OW-3 | Blocker | Filter hardening and date range UI | **Done** | 400 on bad dates, inverted range, bad mode/status; `q` capped |
| OW-3b | High | Receipt-date UX | **Done** | Future dates rejected on server and UI; backdated hint; server warnings surfaced |
| OW-4 | Blocker | Server-enforced walk-in rule | **Done** | Used the existing `is_pos_walk_in` flag, so **no new customer field or migration**. Enforced at the manual-create API; bank-import and gateway services are not walk-in flows |
| OW-5 | High | Real receipt voucher | **Done** | A4 and thermal PDF with invoice lines. The voucher is available in English and Hindi (`?lang=hi`): Devanagari is shaped with HarfBuzz (`shaped_text.py`, bundled fonts in `payments/fonts/`) and amounts in words come from `hindi_numbers.py`. English uses core Helvetica, so the rupee sign prints as "Rs." |
| OW-6 | High | Search performance | **Done** | Starts-with on UTR and reference, capped query, composite index added. `number` and customer name stay "contains". Trigram GIN indexes were added after profiling on Postgres at 405,000 receipts (`payments.0039`, five `UPPER(col)` indexes built concurrently; search 1.2-1.4 s to 16-70 ms; an invalid leftover index is dropped and rebuilt). Terms under 3 characters cannot use them, so the API ignores such a search (Phase 2 WP-0.9) |
| OW-7 | High | Void dialog refactor | **Done** | One component; localized; stays open on failure |
| OW-8 | Blocker | Tests and gates | **Done** | See section 6 |
| OW-9 | High | Void edge cases | **Done** | Bank-matched and closed-till receipts refused; settlement discount and partly reallocated receipts restored and tested |
| OW-10 | Medium | Status presentation | **Done** | `receiptStatus.ts` |
| OW-11 | Medium | Accessibility and responsive | **Done** | axe-core checks on the list and three dialogs; 375 px layout checked in a browser (found and fixed one overflow caused by the new hidden header text) |
| OW-12 | Medium | Export | **Done** | Export respects every filter, not just the page |
| OW-13 | Medium | Tie-out | **Done** | Test: collected equals net cash (1100) and customer advances (2300) after a void, original and reversal entries included |
| OW-14 | Medium | Tracking | **Done** | QOS-0118; `qos-lint` passes, backlog regenerated |

---

## 6. Verification Record

Run on 2026-10-11 against the uncommitted work tree.

| Check | Scope | Result |
|---|---|---|
| Web type-check | `tsc -b` | clean |
| Web lint | ESLint on the touched files | 0 errors (one existing warning in `NewInvoicePage.tsx`) |
| Web tests | full suite (`npm run test:run`), including `ReceiptsPage.test.tsx` (32 tests) | 220 files, 1227 tests, all pass |
| Backend, SQLite | `test_money_in_receipts.py` (35 new tests) with `test_partial_closures`, `test_cheque_payment`, `test_payment_allocation` | 78 passed |
| Backend, SQLite, wide | every test file that touches receipts, void, payments views or OpenAPI (about 930 tests) | 929 passed, 5 skipped (Postgres-only), 0 failed |
| Postgres 17 (throwaway container) | the new money-in tests, `test_partial_closures`, `test_payment_allocation`, `test_cheque_payment`, `test_double_submit_money_paths`, `test_invoice_postgres_atomicity`, `test_idempotency_fingerprint`, `tests/tenancy` | 155 passed, 0 skipped. This run started before the future-date check was added; that check is covered by the SQLite run (35 passed) |
| `makemigrations --check` | payments | no changes detected |
| OpenAPI drift | snapshot regenerated under `config.settings_test`; web types regenerated; contract test passes | diff limited to receipt endpoints and fields |
| `ruff check` | `payments/`, new tests | clean |
| `qos-lint` | 118 items | OK |
| Browser, 375 px | list, voucher dialog, void drawer (mock-data build) | layout correct after one fix |

**Not covered:** Playwright golden specs were not re-run against a rebuilt API. The golden payments path uses the unchanged strings `New receipt`, `Apply to specific invoice (optional)`, `Save` and `Receipt created`, but it should be run with the stack rebuilt (section 7).

---

## 7. Exit Checklist

- [x] Blocker items closed (OW-1, 2, 3, 4, 8)
- [x] Other items closed (OW-6 trigram index shipped in `payments.0039`)
- [x] Verification table filled with real results
- [x] Postgres run recorded in section 6
- [ ] Commit the changes (nothing is committed yet)
- [x] DEV: `payments` migrations applied through 0043 on 2026-10-11 (`check_indexes`: all indexes valid). Other environments: run `python manage.py migrate payments` (existing voided receipts have their reason lifted from notes)
- [x] DEV stack rebuilt (api, worker, beat, web, migrate); golden payments spec `payments-golden-path.spec.ts` passes (2026-10-11)

---

## 8. Behaviour Changes Other Callers Should Know

* `POST /payments/receipts/{id}/void/` now returns **400** without a reason of at least 3 characters. The web app is updated. Any other client (mobile, scripts) must send `reason`. A search of this repository found no other caller.
* `POST /payments/receipts/` returns 400 for a future `receipt_date`, and for a walk-in customer's receipt that is not fully applied.
* `GET /payments/receipts/` returns 400 (not 500, and not an empty list) for an invalid date, mode or status.
* The receipt note no longer receives a `VOIDED: reason` line; read `void_reason`, `voided_at` and `voided_by_name`.

## 9. Regression & Rollback

* **Ledger safety:** all mutations still use reversing journals (`_reverse_money_document_journal`); nothing is deleted.
* **Schema:** migration `0038` is additive (nullable or defaulted columns, one index). Rolling back the code leaves the columns unused; reversing the migration drops them.
* **API compatibility:** new filters, `summary/`, `export/` and `voucher/` are additive. The stricter validation in section 8 is intentional.
* **Frontend rollback:** filters default to empty, matching the old list. If `summary/` fails the cards hide and the list works.
