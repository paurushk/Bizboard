# Sales History implementation plan

Date: 9 Oct 2026
Revised: 9 Oct 2026, after review against `backend/sales/views.py` and `backend/sales/serializers.py`. That review is already applied below (parity tests, one settlement state, raw HTTP 202, one idempotency key, SH-24 before posting, pass/fail instead of scores). Re-checked the same evening: nothing in that review was missing. SH-28 was added later, from the live screen, and it ships first. The phase table now matches that order.
Screen: `/sales/history` (`web/src/pages/sales/SalesHistoryPage.tsx`)

This is the build spec. Do the phases in order. A later phase assumes the earlier checks already pass. Do not start the filter redesign while cancel can still report success for an invoice that is still completed.

The 1–10 scores from the 9 Oct review are informal context only. They are not acceptance criteria. An item is done when its check passes. The screen is done when the pass/fail list at the end is all pass.

## Product decisions

These are choices, not facts. Change them here before building if product disagrees.

| Decision | Choice |
|---|---|
| Cancel reason | Mandatory. Confirm stays disabled until the reason is non-empty. |
| Complete from this list | Confirms first. The bill is numbered and posted with the full amount still due. This screen does not collect cash. |
| Paid chip amount | Billed grand total of settled invoices, labeled “billed”. Unpaid and Partial amounts are outstanding, labeled “due”. |
| Returned bill with a balance | Due column shows the balance. It is not marked overdue. Overdue applies only to `COMPLETED`. |
| Draft and cancelled Due | Em dash. They do not sort as if that hidden balance were money owed. |
| Pending cancel | The row shows that a cancel is waiting. The server already reuses an open approval for the same invoice (`SalesInvoiceViewSet.cancel`). The UI must not look like a second cancel started a new one. |
| Selection and Back | Selection is not in the URL. Back restores filters and drops the selection, with no toast. |
| Export | CSV and Excel of the filtered register are deferred. This plan does not add them. |
| Feature flag | None. See “Clients and compatibility”. |
| Chip vs list for one moment | The payment chips and the rows are two requests. They may disagree until the mutation’s refetch finishes. The invariant is the next GET, not the in-flight pair. |

## Clients and compatibility

Checked 9 Oct 2026: `mobile/` does not call `payment-stats` or `bulk-pdf-zip`. The web list is the only caller of `getInvoicePaymentStats` and `bulkInvoicePdfZip`.

- `sort` is a new optional query param. Omitted, the order stays `-invoice_date, -id`. Old clients are unaffected.
- Zip response keeps `url` and `fileId` and adds `included` and `skipped`. Old clients that read `url` still work. An old page will not show the skipped list.
- `payment-stats` amounts change meaning (due vs billed). Only this web page displays them, and it changes in the same release as the API. A service worker can keep an old bundle until refresh. That old bundle will label the new amounts with the old words for one session. No flag. Do not rename the JSON keys. Document the new meaning in the OpenAPI description.
- `cancelSalesInvoice`’s TypeScript return type changes on purpose and breaks both web call sites. There is no second client.

## How to use this file

Each work item has an id (`SH-01`), the files to change, the behavior to implement, and the check that proves it. Mark an item done only when its check passes.

## Out of scope

- Warehouse, invoice-type, and POS-source filters.
- Reprint of cancelled bills.
- Changing `invoice_payment_state` in `backend/payments/holding.py`. Gateway holding stays `PAID_PENDING_BOOKS`. The list chip reads `settlementState` for the money bucket, and document status still wins for Draft, Cancelled, and Returned.
- Rebuilding purchase history, except the one shared date cell in SH-22.
- Promises, reminders, and bulk receive.
- CSV or Excel export of the filtered register.

## Current behavior this plan changes

Observed in the current code:

- `cancelSalesInvoice` posts `/sales/invoices/{id}/cancel/` with an empty body. Axios treats HTTP 202 as success. `unwrapData` returns the inner body. Both `SalesHistoryPage` and `InvoiceDetailPage` then show a cancel success. When the user is not the sole approver, `SalesInvoiceViewSet.cancel` returns 202 and the invoice stays `COMPLETED`. A second cancel reuses the open `ApprovalRequest` for that invoice. It does not insert another one.
- Complete in the row menu calls `completeMutation.mutate` with no confirm and no `amountReceived`. Delete and cancel use `window.confirm`. `request_fingerprint` hashes the whole body, so a confirm-flag retry is a different fingerprint than the first attempt.
- `payment_stats` sums `grand_total` and uses `filter_queryset`, so a `payment_status` filter zeros the other buckets.
- `_apply_payment_status` defines Partial as outstanding above zero and (`_live_alloc > 0` or `_cn > 0`). `paidAwareStatus` labels every completed bill with `balance > 0` as Unpaid. `get_received` is `receivable − balance`, so credit notes and settlement discounts count as received. Those two formulas are not the same function.
- List `balance` for a list response is `_list_outstanding` from `LedgerService.bulk_sales_invoice_outstanding`. The SQL `_balance` annotation in `_annotate_live_settlement` is a different expression. It also requires `receipt__status="POSTED"` on allocations. The Python outstanding path does not. Sorting on `_balance` is therefore not sorting the number the Due column shows.
- `filtersActive` ignores `paymentStatus` and `customerId`.
- Select-all replaces the selection when `selected.length === rows.length`. Selection survives filter changes and mutations.
- `bulk_pdf_zip` skips drafts and cancelled bills, returns `count` of invoices found, and raises “not found in this company” when any id is missing. That message does not say which other company, but it also does not list skipped rows.
- Record payment on the server is `CanCreatePayments` (`record_payment` in `get_permissions`). It is not `CanCreateSales`. The dialog’s only write is `recordInvoicePayment`. The list currently shows the action for `canCreateSales` instead.
- The row does not show `balance` or `dueDate`. Both are already on `SalesInvoiceSerializer`.
- `todayIso()` in `web/src/components/billing/lineHelpers.ts` uses the browser’s local calendar. Django `TIME_ZONE` is `Asia/Kolkata`. There is no per-company timezone field.
- Observed on the running Sales History screen, 9 Oct 2026, two screenshots. The unfiltered list shows eight rows, including Gopal, Unpaid, ₹155.00. After “Gopal” is typed in the Search box, the chips change to Paid 0, Partial 0, Unpaid 1 · ₹155.00, and the table paints the header only. The customer dropdown above the search box still shows the placeholder “Customer”. The search request matched. The row is not visible. The customer control is a different control and is also broken. See SH-28.

Renderer note: `EnvelopeJSONRenderer` camelizes keys and wraps success bodies as `{ success, data }`. Clients use `unwrapData`. New fields are camelCase (`approvalId`, `included`, `skipped`, `fileId`, `settlementState`).

## Phase order

| Phase | Items | Ships as |
|---|---|---|
| 0a. Search must show its rows | SH-28 | PR 1. The 9 Oct screenshots: typing Gopal updates the unpaid chip and leaves the table body blank. Later browser checks are meaningless until this passes. |
| 0. One refresh path | SH-24 | PR 2. The review asked for this before posting. It stays ahead of Phase 1. SH-28 is the only item in front of it. |
| 1. Truthful posting | SH-01 – SH-05 | PR 3. |
| 2. One settlement state | SH-06, SH-06a, SH-07, SH-09 | PR 4. SH-08 is folded into SH-24. |
| 3. Safe bulk and the right people | SH-10 – SH-15, SH-14a | PR 5. |
| 4. A register people can scan | SH-16 – SH-19, SH-21 – SH-23 | PR 6. No URL state. |
| 4b. URL state | SH-20 | PR 7, alone. Highest regression risk, and independent of posting and money. |
| 5. Proof | SH-25 – SH-27 | PR 8, with phase 4b or immediately after it. |

---

## Phase 0a — Search must show its rows

### SH-28. Customer search and the search box

Do this before any other Sales History PR. The money and posting work cannot be checked in the browser while a matching bill is invisible.

**What the screenshots show**

The Search box is the unlabeled field beside From and To (`HistoryFilterBar`, placeholder `common.search`). It is not the Customer dropdown. Typing Gopal there is sent as `q`. `payment_stats` and the list use that same `q`. The chip row updates to one unpaid bill of ₹155, which is Gopal’s row in the first screenshot. So the text search is reaching the API. The table still mounts, because the header is on screen (`rows.length > 0`). The body does not.

**Why the row is clipped**

`VirtualizedTable` (`web/src/components/VirtualizedTable.tsx`) wraps every child in a box whose height is `virtualizer.getTotalSize()`, which is the data rows only (`rowCount * rowHeight`, about 52px for one hit). `SalesHistoryPage` puts the whole `Table`, including `TableHead`, inside that box. The header is about as tall as one estimated row, so a one-row result is covered by the header. A scrollbar can appear on that short box. Eight rows survive because `8 * 52` is tall enough to show the header and the body. `SalesHistoryPage.test.tsx` mocks `VirtualizedTable` to return every row and never lays out this box, so this bug is invisible to Vitest.

A filter refetch also unmounts the table. `rows` comes from `query.data`, and a new query key has no `placeholderData`, so `rows` becomes `[]` while the search is in flight and the `rows.length > 0` branch unmounts the scroll parent. When the one row returns, the virtualizer measures again from a fresh 0-height frame and can paint `getVirtualItems()` as `[]` for that frame. The header-in-the-box bug remains even after measurement.

**Fix the list**

- Keep the previous page on screen while a new filter loads: `placeholderData: (previous) => previous` on the invoice list query. Do not unmount the table just because the key changed.
- Stop sizing the scrollport to the body rows while the header lives inside it. Render `TableHead` outside the `height: totalSize` box. The virtualizer wraps only the body rows. The scroll parent’s content height is the header plus `totalSize`.
- `minHeight` of that scroll parent is the header plus one row, so a single hit cannot collapse under the header.
- Apply this in `VirtualizedTable` if other callers put a header inside the render prop. Grep those callers. If only Sales History puts a `Table` in the render prop, fix it on this page and leave the shared component’s other callers alone. Do not reintroduce `contain: 'strict'` (UXW2B-007).

**Why the Customer box fails**

The Customer `Autocomplete` in `SalesHistoryPage` is not the working party picker.

- `onInputChange` writes every reason into `customerSearch.setQuery`, including `reset`. A reset with `''` clears the server query while the input still shows the typed name. The next request is the unfiltered first page (`useCustomerSearch` only sends `q` when the trimmed query is at least 2 characters). MUI’s default `filterOptions` then looks for that name in the first page and shows nothing when the customer is not on it.
- It does not pass `filterOptions={(options) => options}`. The server already filtered. A phone query is worse: `getOptionLabel` is the name only, so the default client filter drops a row whose phone matched and whose name did not.
- It does not pass `inputValue`, `loading`, `noOptionsText`, or `isOptionEqualToValue`. `QuickEntryPage` and `PartySelectPanel` do.

**Fix the Customer box**

Match `QuickEntryPage`’s customer autocomplete:

- `filterOptions={(options) => options}`
- `inputValue={customerSearch.query}`
- `loading={customerSearch.isFetching}`
- `noOptionsText={t('common.noResults')}`
- `isOptionEqualToValue={(a, b) => a.id === b.id}`
- `onInputChange`: call `setQuery` only for `input` and `clear`. Ignore `reset`, so a refreshed option list cannot wipe the query.
- Helper text when the trimmed query length is 1: type at least 2 characters. The hook’s minimum is `PARTY_SEARCH_MIN_CHARS`.
- Choosing an option still sets `customerId` and page 1. Clearing the box sets `customerId` to empty.
- The Search box keeps searching number, customer name, and phone. The Customer box filters by id. Both can be set. Say that in the Search label from SH-19. Until SH-19, set an accessible name on this Search field now (`history.searchLabel`), because the screenshot field has no visible label and is easy to confuse with Customer.

**Checks**

- Browser, the screenshot case: type Gopal in Search. The unpaid chip shows 1 and ₹155, and Gopal’s row is visible without scrolling the table. Clear Search. The eight rows come back.
- Browser: open Customer, type Gopal, and the option list contains Gopal. Choose it. The list request has `customer` set to that id and the row is visible. Clear it. The id param is gone.
- Vitest cannot see the clip, because it mocks `VirtualizedTable`. Add a test that does not mock it only if jsdom reports a non-zero viewport. Otherwise the browser check above is the proof, and a unit test covers the autocomplete: typing Gopal calls `listCustomersPage` with `q: 'Gopal'` and does not follow that with a call whose `q` is omitted, and choosing the option calls `listSalesInvoicesPage` with that `customer` id.
- A one-row list and an eight-row list both show their first data row on screen. The header is not the only painted row.

---

## Phase 0 — One refresh path

### SH-24. One invalidation helper

Do this before SH-01. Phase 1–3 must not grow a temporary invalidate list that this item later deletes.

**Files**

- `web/src/pages/sales/invalidateInvoiceSideEffects.ts` (new)
- `web/src/pages/sales/SalesHistoryPage.tsx`
- `web/src/pages/sales/InvoiceDetailPage.tsx` (complete `onSuccess`, cancel `onSuccess`, and the record-payment invalidation list)

```ts
export function invalidateInvoiceSideEffects(
  qc: QueryClient,
  invoiceId?: number,
): void {
  void qc.invalidateQueries({ queryKey: ["sales-invoices"] });
  void qc.invalidateQueries({ queryKey: ["sales-invoice-payment-stats"] });
  if (invoiceId != null) {
    void qc.invalidateQueries({ queryKey: ["sales-invoice", invoiceId] });
  }
  void qc.invalidateQueries({ queryKey: ["customers"] });
  void qc.invalidateQueries({ queryKey: ["customer"] });
  void qc.invalidateQueries({ queryKey: ["customer-360"] });
  void qc.invalidateQueries({ queryKey: ["dashboard"] });
  void qc.invalidateQueries({ queryKey: ["products"] });
  void qc.invalidateQueries({ queryKey: ["stock-balance"] });
  void qc.invalidateQueries({ queryKey: ["stock"] });
  void qc.invalidateQueries({ queryKey: ["receipts"] });
  void qc.invalidateQueries({ queryKey: ["sales-invoices-open"] });
}
```

Replace the hand-written lists on history and detail. Do not chase POS, new invoice, or delivery challan in this item.

History calls it after successful complete, cancel (including pending, so the refetch shows the bill still completed), delete, and record payment.

Two requests can still be on screen together. The chips and the rows may disagree until both refetches land. That window is accepted. SH-27 checks the GET after the POST, not the overlapping pair.

**Check.** A unit test spies on `invalidateQueries` and expects each key above. Grep shows `SalesHistoryPage` has no private `invalidate` that only lists `sales-invoices`. Detail’s complete, cancel, and record-payment call the helper.

---

## Phase 1 — Truthful posting

### SH-01. Cancel result is cancelled or pending

**Files**

- `web/src/api/legacy/sales.ts` (`cancelSalesInvoice`)
- `web/src/pages/sales/SalesHistoryPage.tsx`
- `web/src/pages/sales/InvoiceDetailPage.tsx`
- `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`
- A backend test next to the existing sales invoice tests

**Read the status before unwrap.** `unwrapData` drops the HTTP status. The branch uses the Axios response:

```ts
const response = await apiClient.post(`/sales/invoices/${id}/cancel/`, {
  cancelReason: reason,
});
const body = unwrapData<Record<string, unknown>>(response.data);
if (response.status === 202) {
  if (body.status !== "PENDING" || body.approvalId == null) {
    throw new Error("Cancel returned 202 without a pending approval.");
  }
  return { outcome: "pending", invoiceId: id, approvalId: Number(body.approvalId) };
}
if (response.status === 200) {
  return { outcome: "cancelled", invoice: body as SalesInvoice };
}
throw response;
```

Do not treat `body.status === "PENDING"` on a 200 as pending. A sole-owner cancel must be 200 with the cancelled invoice. If a 200 body has no invoice `id`, throw. Do not show “waiting for approval” for that response.

The view already reads `reason`, `cancel_reason`, and `cancelReason`. Send `cancelReason`.

**Pages**

- Pending: warning “{label} is waiting for approval. It is still completed.” Call SH-24. Do not use the cancel success string. `invoiceNumberLabel` must not run on the pending body.
- Cancelled: success with the invoice number from the payload, then SH-24.
- The row shows a “Cancel pending” chip when the list says so (SH-01b below). A second click hits the same dialog. The server reuses the open approval. The success path for that second click is still the pending warning, not a new approval id presented as a new cancel.

**SH-01b, same item.** The list payload includes `cancelApprovalPending: boolean`. Implement it as `Exists` on `ApprovalRequest` with `action="invoice_cancel"`, `status=PENDING`, and `payload__invoice` equal to the invoice pk, scoped to the company. The history row renders that chip beside the status chip. Invoice detail shows the same flag if it already loads the invoice serializer.

**Backend checks, written before the UI copy is trusted**

- Non-sole approver: POST cancel returns 202, invoice GET is `COMPLETED`, one pending approval exists. POST cancel again returns 202 with the same `approvalId`. Still one row.
- Sole approver: POST cancel returns 200, not 202. GET status is `CANCELLED`.

**Page check.** The non-sole case shows the warning and the Cancel pending chip. The sole-owner case shows the cancelled success and the row is Cancelled. Neither path renders `Draft #undefined`.

### SH-02. Cancel dialog states the blockers and collects a reason

**Files.** `SalesHistoryPage.tsx`, `InvoiceDetailPage.tsx` if detail still confirms with `window.confirm` or posts immediately, `en.ts`, `hi.ts`

Do not extend `ConfirmDialog`. Its `body` is a string. Use a MUI `Dialog`, which traps focus.

- Title: Cancel {label}
- Blocker text has an id. The dialog sets `aria-describedby` to that id.
- Body: this reverses the ledger and restores stock when the bill is allowed to cancel. It will be refused if a receipt is still allocated, an IRN or e-way bill is live, or a return or credit/debit note is still on the bill.
- Reason field is required, trimmed, max 500 characters, and receives initial focus.
- Confirm label: Cancel invoice. Color: error. Disabled until the reason is non-empty and while the request is pending.
- Escape closes the dialog and returns focus to the actions button that opened the menu.

Send the trimmed reason through SH-01. An API refusal stays in an alert with the server message. Status unchanged.

**Check.** Empty reason does not POST. A bill with a live allocation shows the server message and stays Completed. The POST body contains `cancelReason`. Keyboard: Tab stays inside the dialog, Reason is focused on open, Escape returns focus to the actions button.

### SH-03. Complete asks before it posts, one key per intent

**Files**

- `web/src/pages/sales/SalesHistoryPage.tsx`
- `backend/sales/views.py` `complete`, and `backend/core/idempotency.py` only if the complete action needs a scoped fingerprint helper
- `backend/sales/services.py` if `SalesService.complete` does not already lock the row
- Tests, written so they fail before the lock and the fingerprint change

**Dialog.** Menu item opens `ConfirmDialog`. It does not call `completeMutation` directly.

- Title: Complete {label}
- Body: this assigns the tax invoice number, posts stock and the ledger, and leaves the full amount due. Record a payment after it is completed if the customer is paying now.
- Confirm label: Complete invoice.

**One idempotency key per dialog open.** Reuse it for every attempt in that gesture, including a timeout retry and a confirm-flag retry. Do not mint a new key when flags change.

**Fingerprint.** `request_fingerprint` hashes the entire body, so adding `confirmBlankPos` conflicts with the same key. For `sales_invoice_complete` only, hash the body with these keys removed: `confirm_sales_rcm`, `confirmSalesRcm`, `confirm_blank_pos`, `confirmBlankPos`, `confirm_gstin_total_change`, `confirmGstinTotalChange`, and the other confirm flags `complete` already reads. Do not change the fingerprint for other scopes. A changed amount or a different invoice id must still conflict.

**Lock, as a failing test first.** Two concurrent completes of the same draft must yield one invoice number and one posted row. Write that test, run it, and if it fails add `select_for_update` at the start of `SalesService.complete` and a business error when status is not `DRAFT`. Do not ship the list button on an untested lock.

**Timeout test.** Complete succeeds and the key stores the response. A second POST with the same key and extra confirm flags returns that same invoice id. The number series advances once.

Disable the menu item and the confirm button while `completeMutation.isPending`. On a network timeout, retry the same key. On a deterministic 4xx that is not a confirm code, show the error and do not mint a second key for a blind second post.

**Check.** Choosing Complete does not POST until confirm. The concurrent test and the replay-with-flags test pass. A second click while the request is in flight does not POST a second key. The completed bill’s balance equals the amount due. Dismissing the dialog leaves the draft.

### SH-04. Drafts the list cannot finish open the editor

**Files.** `SalesHistoryPage.tsx`, and `NewInvoicePage.tsx` only if it does not already show `location.state` errors.

`completeWithConfirms` still handles the confirm codes it already knows (`place_of_supply_unresolved`, `GSTIN_TOTAL_CHANGED`, and the rest of its map), using the same idempotency key from SH-03.

`below_cost`, `gst_guard_blocked`, and any pharmacy or missing-field error the list cannot collect: `navigate(\`/sales/history/${id}/edit\`, { state: { message: getErrorMessage(err) } })`. The editor shows that message. Do not build those forms on the list.

**Check.** A below-cost or GST-guard rejection opens the editor with the message. A draft with no such block completes after the confirm. The editor navigation does not send a second complete with a new key.

### SH-05. A failed list load keeps the filters

**File.** `SalesHistoryPage.tsx`

The filter block is wrapped in `!query.isError`, so a failure unmounts the filters. Render `HistoryFilterBar`, the payment chips, and the error together. Retry calls `query.refetch()`. Changing a filter fetches the new key.

**Check.** A rejected `listSalesInvoicesPage` still shows the status chips and search. Clearing the filter sends the cleared params. Retry sends the current params.

**Phase 1 done.** SH-01 through SH-05 checks pass, including the sole-approver 200 test, the pending-dedup test, the concurrent complete test, and the same-key replay test.

---

## Phase 2 — One settlement state

### SH-06. The API returns the bucket. The chip only displays it.

Do not derive Partial on the client from `received > 0`. `get_received` is `receivable − balance`. The filter is `_live_alloc > 0 or _cn > 0`. They match only while the algebra and the clamping hold.

**Files**

- `backend/sales/views.py` (`_apply_payment_status`, list serializer hook)
- `backend/sales/serializers.py`
- `web/src/utils/status.ts`
- `web/src/pages/sales/SalesHistoryPage.tsx`
- `web/src/pages/sales/InvoiceDetailPage.tsx`, because it uses `paidAwareStatus`

Add `settlement_state` on the list and detail serializer, camelized to `settlementState`. Values: `PAID`, `PARTIAL`, `UNPAID`, or `NONE`.

One function, used by the filter, the stats split, and the serializer:

- Document status not in `COMPLETED` or `RETURNED`: `NONE`. Drafts and cancelled bills are not paid, unpaid, or partial.
- Outstanding ≤ 0 and grand total > 0: `PAID`.
- Outstanding > 0 and (live allocation > 0 or credit note > 0 or settlement discount share > 0): `PARTIAL`.
- Otherwise, if outstanding > 0: `UNPAID`.

Outstanding here is the same number the list will show as Due (SH-14a). Do not compute the bucket from `_balance` and the chip from `_list_outstanding`.

`paidAwareStatus` for a `COMPLETED` row:

1. `paymentState === "PAID_PENDING_BOOKS"` stays `PAID_PENDING_BOOKS` (gateway holding, unchanged).
2. Otherwise the chip is `settlementState`.
3. Status other than `COMPLETED` returns that status. Returned, Cancelled, and Draft never become Paid or Unpaid. A returned bill may also show its `settlementState` only as a second chip if product asks later. This plan does not. Returned stays Returned. This preserves G-17.

If `settlementState` is missing on an old cached response, the chip shows the document status and does not guess Partial from `received`.

`documentStatusTone` for `PARTIAL` is `warning`.

**Check.** The G-17 returned bill still renders Returned, not Paid. A completed bill whose `settlementState` is `PARTIAL` renders Partial. The client test does not compute Partial itself.

### SH-06a. Parity tests for the one function

**File.** Backend sales tests. These are required for SH-06, not a follow-up.

For each case, create the documents, then assert the list row’s `settlementState` equals the `payment_status` bucket that contains that id, and equals the bucket `payment_stats` counts it in.

| Case | Expected bucket |
|---|---|
| Completed bill, no receipt, no note | `UNPAID` |
| Live allocation for part of the bill | `PARTIAL` |
| Credit note for part of the bill, no allocation | `PARTIAL` |
| Debit note that increases outstanding, no allocation and no credit note | `UNPAID` |
| Settlement discount that reduces outstanding, with no remaining live allocation (discount share only) | `PARTIAL` if outstanding remains, else `PAID` |
| Receipt posted, then reversed, after a partial credit note | Bucket follows what is still live. A reversed receipt is not a live allocation. |
| Draft of any amount | `NONE`, and the id is in none of the three payment filters |
| Fully returned bill with zero outstanding | Document status `RETURNED`. `settlementState` may be `PAID`. The payment filter may include it. The chip on the list is still Returned (SH-06 rule 3). |

If a case cannot be built with the current services, the test names the blocker and SH-06 is not done.

**Check.** The test module passes. There is no second Partial rule in `status.ts`.

### SH-07. Totals use that same function

**Files.** `backend/sales/views.py` `payment_stats`, the tests in `test_bug_open_sales.py`, `test_sales_purchase_ux_plan.py`, and `test_code_review_2026_10_05_b.py`, `SalesHistoryPage.tsx`, `en.ts`, `hi.ts`

`payment_stats` applies every list filter except `payment_status`, then splits with the SH-06 function. A `payment_status=UNPAID` list must not zero the Paid and Partial chips.

Amounts:

- `unpaid.amount` and `partial.amount`: sum of the same outstanding the Due column shows.
- `paid.amount`: sum of `grand_total` for the paid bucket. Label it billed, not due.
- Counts stay `Count("id")`.
- Drafts and cancelled bills stay out of all three buckets.

Existing tests assert counts. Keep those assertions. Add amount assertions for one unpaid bill of 100, one partial bill with grand total 100 and outstanding 40, and one draft of 999. Expect unpaid amount 100, partial amount 40, draft in neither.

**Frontend**

- Remove the separate non-clickable stats row.
- Chips: “{name} {count} · due {amount}” for Unpaid and Partial, and “{name} {count} · billed {amount}” for Paid. `{name}` is the status word, so Hindi can reorder the whole string. Do not concatenate a label in code.
- Clicking a chip toggles `paymentStatus` and resets to page 1.
- Hide the chips when document status is `DRAFT` or `CANCELLED`.
- When they show, the group is labelled “Open bills”.

Regenerate the OpenAPI snapshot and `web/src/api/openapi-types.ts` if `payment-stats` has a schema. Update the description of `amount` so it does not say grand total for every bucket.

**Check.** Filter Partial: every visible completed row’s chip is Partial, and the other chips still show their own counts. Draft hides the chips. After a payment, SH-24 refetch updates the due figure. The parity cases in SH-06a are the amount source, not a client formula.

### SH-09. Empty means no results

**File.** `SalesHistoryPage.tsx`

```ts
const filtersActive = Boolean(
  filters.status ||
  filters.paymentStatus ||
  debouncedQ ||
  filters.dateFrom ||
  filters.dateTo ||
  customerId
);
```

`showEmpty` is the first-invoice state, and only when `filtersActive` is false. `showNoMatches` uses `t('common.noResults')`.

**Check.** A customer id or `payment_status: 'UNPAID'` with zero rows finds “No results found” and does not find “Create your first sale.” Zero rows and no filters still finds the first-invoice empty state.

**Phase 2 done.** SH-06, SH-06a, SH-07, and SH-09 pass. There is one settlement function on the server.

---

## Phase 3 — Safe bulk and the right people

### SH-10. Selection matches the visible rows, including after a mutation

**File.** `SalesHistoryPage.tsx`

- Clear `selected` when status, payment, search, dates, or customer change. Do not clear it when only `page` changes.
- After each successful refetch of the list, drop ids that are not in the refetched page and not known to be on another loaded page. Practical rule: keep an id only if it is in the current page results or the user has not changed page since selecting it and the id was not the target of a delete, complete, or cancel that removed it from this filter. Simpler rule that meets the check: on every list success, `setSelected((prev) => prev.filter((id) => results.some((row) => row.id === id) || prevOffPage.has(id)))`, and remove an id from `prevOffPage` when a mutation for that id succeeds. A deleted draft disappears from the count. A completed draft that leaves a Draft filter disappears from the count.
- Header checkbox, current page only:

```ts
const pageIds = rows.map((row) => row.id);
const selectedOnPage = pageIds.filter((id) => selected.includes(id));
const allOnPage = pageIds.length > 0 && selectedOnPage.length === pageIds.length;
const someOnPage = selectedOnPage.length > 0 && !allOnPage;
```

- `checked={allOnPage}`, `indeterminate={someOnPage}`.
- On change, if `allOnPage`, remove `pageIds`. Otherwise add `pageIds`. Never replace `selected` with `rows.map(...)`. Never compare `selected.length` to `rows.length`.

MUI sets `aria-checked="mixed"` from `indeterminate`.

**Check.** Select two rows on page 1, go to page 2, select-all. Page 1 ids remain and page 2 ids are added. Select-all again on page 2 removes only page 2. Change customer: `selected` is empty. Delete a selected draft: the count drops by one when the list returns. The bulk count equals `selected.length` and every selected id is still on the server in this company.

### SH-11. The zip reports what it contains, without leaking other companies

**Files.** `backend/sales/views.py` `bulk_pdf_zip`, `web/src/api/legacy/sales.ts`, `SalesHistoryPage.tsx`, `test_sales_purchase_ux_plan.py`, `en.ts`, `hi.ts`

**Response**

```json
{
  "url": "…",
  "fileId": 1,
  "included": [{ "id": 1, "number": "INV-00001" }],
  "skipped": [{ "id": 2, "number": "Draft #2", "reason": "not_completed" }]
}
```

- Cap remains 100 ids. Duplicate ids are deduped before the cap check.
- Status other than `COMPLETED` or `RETURNED`, and the row is in this company: `skipped.reason = "not_completed"`. Include the number.
- An id that is not in this company, whether it is missing or belongs to another company: `skipped` entry `{ "id": <requested id>, "reason": "unavailable" }` with no `number` and no other field. One reason for both cases. Do not use “not found” vs “other company”.
- If `included` is empty, return 400 with the bulk-none message. Do not create a file asset.
- `count` of found invoices is not the success number. Clients use `included.length`.

**Frontend.** Disable the button while the request runs. On 400, `setError`, do not open a URL. On success, download with the existing blob helper and credentials. Do not `window.open` after `await`. Success text is the full sentence “{count} PDFs downloaded.” If any skipped numbers exist, a second sentence lists those numbers. Unavailable ids are counted as “{count} bills were not included” with no numbers. Do not reuse the button label as the success string.

Regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` for this operation. CI diffs both.

**Check.** Three completed ids and one draft: 200, three included, one skipped `not_completed`, three files in the zip. All drafts: 400, no file. 101 ids: 400. An id from another company and a nonexistent id both come back `unavailable`, with the same shape, and the response body does not contain the other company’s invoice number. The page shows the included count.

### SH-12. Menu permissions match the endpoint, including record payment

**File.** `SalesHistoryPage.tsx`
**Reference.** `SalesInvoiceViewSet.get_permissions` and `RecordInvoicePaymentDialog`

| Menu item | Show when | Endpoint permission |
|---|---|---|
| Open, Print, Download, thermal | User can open the page. Print only for `COMPLETED` and `RETURNED`. | `CanViewSalesSurfaces` for pdf |
| Edit / Amend | `canCreateSales`, draft or completed | `CanCreateSales` for update |
| Complete | `canCreateSales`, draft | `CanCreateSales` |
| Delete | `canCreateSales`, draft | `CanCreateSales` for destroy |
| Share | `canCreateSales`, completed or returned | `CanCreateSales` |
| Record payment | `canCreatePayments`, completed or returned, balance > 0 | `CanCreatePayments` on `record_payment`. Confirmed in `get_permissions`. The dialog posts only `recordInvoicePayment`. |
| Sales return | `canCreateSales`, completed | Create-sales on the returns API |
| Profit | `canViewFinancialReports`, completed or returned | `CanViewFinancialReports` |
| Cancel | `canCancelDocuments`, completed | `CanCancelDocuments` |

Import `canCreatePayments`. Do not use `canCreateSales` for Record payment.

**Check.** Vitest:

- Sales-create, no payments: no Record payment. Share, Complete, and Delete show on the matching statuses.
- Payments-create, no sales-create, with financial reports so the route allows them: Record payment shows on an open completed bill. Share, Delete, Complete, and Amend do not. A test or a code comment cites `record_payment`’s permission class, and the dialog test’s network mock sees only `record-payment`, not share or complete.
- Financial reports only: Open and Print only.

### SH-13. Completed bills say Amend

**Files.** `SalesHistoryPage.tsx`, `en.ts`, `hi.ts`

`t('history.amend')` when status is `COMPLETED`. Draft keeps `t('common.edit')`. Route stays `/sales/history/:id/edit`. Do not weaken `confirm_amend`, owner, period, or IRN rules in the editor.

**Check.** The completed row’s menu item name is Amend. The draft’s is Edit. Both go to the edit route.

### SH-14. Sort uses the same outstanding as Due

**Files.** `backend/sales/views.py`, `SalesHistoryPage.tsx`, `PageParams` if it needs `sort`

**Do not sort on `_balance` until SH-14a passes.** The sort key for due is the outstanding `LedgerService.bulk_sales_invoice_outstanding` already attaches as list `balance`. If that cannot be expressed in SQL without drifting, add a queryset annotation that is a literal port of that function, including settlement discount, TCS outside grand total, debit notes, credit notes, reversed receipts, and `_floor_outstanding`. The annotation’s `receipt__status="POSTED"` filter must match the Python path or be removed from one of them so they match. SH-14a is the proof.

| `sort` | Order |
|---|---|
| omitted or `date_desc` | `-invoice_date`, `-id` |
| `date_asc` | `invoice_date`, `id` |
| `total_desc` / `total_asc` | `grand_total`, then `id` |
| `due_desc` / `due_asc` | the Due outstanding, nulls last, then `id` |

`DRAFT` and `CANCELLED` sort as null on due, in both directions. They show an em dash. They must not jump ahead of a real due because a hidden balance is non-zero. `RETURNED` uses its real outstanding, including zero.

Unknown `sort` returns 400 `Unknown sort`.

Column headers Date, Total, and Due are buttons. Cycle desc → asc → default date desc. `aria-sort` is `descending`, `ascending`, or `none`.

Page range uses the shared `PAGE_SIZE` constant in `SalesHistoryPage.tsx` (the value sent as `pageSize`), not a hard-coded `50`. If the response `count` is known: start = `(page - 1) * pageSize + 1`, end = `min(page * pageSize, count)`. Label is the single i18n string `history.range`.

Regenerate the OpenAPI snapshot for the `sort` query param as well as for SH-11.

**Query budget.** Before changing the list, record `assertNumQueries` for an unfiltered page of 50 and for `payment-stats`. After SH-14, `sort=due_desc` on 50 invoices that each have a credit note, a debit note, and an allocation must not add per-row queries. The count may include the annotation `payment_stats` already pays. It must not grow when the fixture grows from 10 rows to 50.

**Check.** `sort=nope` is 400. Default sort is unchanged. The query-count test passes. The UI sends `sort` and sets `aria-sort`. A 120-row result on page 2 uses the page size from the constant.

### SH-14a. Displayed Due is monotonic under due_desc

**File.** Backend test, required for SH-14.

Build one company with all of: a draft, a cancelled bill, a completed bill with TCS not included in grand total, a debit note, a partial credit note, a settlement discount, and a reversed receipt. GET `?sort=due_desc`.

Assert, in order:

- The `balance` values on rows that display Due (completed and returned) are monotonic non-increasing.
- Those `balance` values equal the outstanding from `LedgerService.bulk_sales_invoice_outstanding` for the same ids.
- Draft and cancelled rows are after every row with a positive due, or their `balance` is not used as the sort key. The test asserts their position, not a hidden `_balance`.
- `settlementState` on each completed row matches the payment filter bucket (SH-06a), so sort, chip, and filter are one number.

**Check.** This test passes. If it fails, fix the annotation. Do not document the drift as acceptable.

### SH-15. PDF still generating can be retried

**Files.** `SalesHistoryPage.tsx`

On the generating / 409 code, store `{ id, mode }` before the menu clears `active`. The alert says the PDF is still generating and offers Retry, which calls `runPdf` for that stored id. A generic 500 has no Retry.

**Check.** A 409 shows Retry and the retry calls `downloadInvoicePdf` with the same id. A 500 does not.

**Phase 3 done.** SH-10 through SH-15 and SH-14a pass.

---

## Phase 4 — A register people can scan

### SH-16. The page states its job

**Files.** `SalesHistoryPage.tsx`, `en.ts`, `hi.ts`

Under the title, one sentence: “Find a bill, see what is still due, collect it, or reprint it.” New invoice stays gated by `canCreateSales`.

**Check.** Heading and sentence are both present in English and Hindi. A user who cannot create sales does not see New invoice.

### SH-17. Due and due date on the row

**File.** `SalesHistoryPage.tsx`

- Due, right-aligned. `COMPLETED` and `RETURNED`: `formatMoney(balance)`. `DRAFT` and `CANCELLED`: em dash.
- Due date: SH-22 formatter, or an em dash when null.
- Overdue only when status is `COMPLETED`, due amount > 0, and `dueDate` is a `YYYY-MM-DD` strictly before today’s date in `Asia/Kolkata`. Do not use `todayIso()`. Add `todayIsoInTimeZone("Asia/Kolkata")` next to the document date helper and test it around 00:30 IST, which is still the previous evening in US time zones. A due date of today in IST is not overdue. A `RETURNED` bill with a balance shows Due and is not overdue. That is the product decision above.
- Customer name links to `/sales/customers/${id}` when `customer` is a number. The invoice number still links to the bill. The row is not a second link.
- Spacer `colSpan` includes the new columns.

**Narrow width.** Below 600px, hide the Due date column. Keep Due, date, number, customer, status, and total. Customer text truncates with the full name as `title`. Do not drop Due. The browser pass checks this width.

**Check.** An open completed bill shows balance and due date. A draft shows dashes in Due. A due date of yesterday in IST on an open completed bill is warning. A due date of today in IST is not. A returned bill with a balance is not warning. The customer link and the number link go to different routes. At 600px the Due date column is not rendered and Due still is.

### SH-18. Date control with one active preset

**Files.** `HistoryFilterBar.tsx`, its test, `SalesHistoryPage.tsx`

Other screens keep today’s chip row. New optional prop, default `"chips"`:

```ts
dateControl?: "chips" | "preset";
```

Sales History passes `"preset"`.

- One control lists `DATE_RANGE_PRESET_IDS`.
- Active id is the preset whose `dateRangeForPreset` equals the current dates. Both empty: none. Dates set and matching nothing: `custom`.
- From and To render only for `custom`.
- Choosing Custom before dates exist is local state. Reload with no dates shows none. That is accepted. The browser pass covers a custom range that does have dates, not only This month.
- Export `activeDatePreset(dateFrom, dateTo, now)` and test it, including 1 Apr and 31 Mar.

**Check.** This month shows as selected. A from/to pair that matches no preset shows Custom and the two fields. Purchase history, which omits the prop, is unchanged.

### SH-19. Search has a name

**Files.** `HistoryFilterBar.tsx` (`searchLabel`), `SalesHistoryPage.tsx`, both i18n files

Label: “Bill number, customer, or phone”, as the `TextField` label.

**Check.** `getByRole('textbox', { name: /bill number, customer, or phone/i })` finds it. A phone query still goes out as `q`.

### SH-21. Actions hit area, checkbox state, and focus return

**File.** `SalesHistoryPage.tsx`

- Actions button at least 40×40 CSS pixels. Accessible name stays `t('common.actions')`.
- Menu `onClose` returns focus to the button that opened it, if that node is still mounted.
- Table `aria-rowcount={rows.length}`.
- Header checkbox name stays `t('common.selectAllRows')`.

This is not the whole accessibility bar. SH-26 runs axe and a keyboard-only pass. SH-02 covers the cancel dialog.

**Check.** The actions button box is at least 40px. Escape from the menu focuses that button. The header checkbox is mixed when one of two visible rows is selected.

### SH-22. Document date is a time element

**Files.** `web/src/utils/documentDate.ts`, `documentDate.test.ts`, `SalesHistoryPage.tsx`, the invoice-date cell in `PurchaseHistoryPage.tsx`

```tsx
<time dateTime={iso}>{formatDocumentDate(iso)}</time>
```

`formatDocumentDate` renders `09 Oct 2026` for `2026-10-09` in `en-IN`. Empty or invalid returns an em dash. `dateTime` stays the ISO date. Do not reformat invoice detail here.

**Check.** Unit tests for a valid date, an empty string, and a non-date. The sales history cell has `dateTime="2026-09-12"`.

### SH-23. Column count and virtualization stay aligned

**File.** `SalesHistoryPage.tsx`

Recount header cells and both spacer `colSpan`s after SH-14 and SH-17. Spacer height still comes from `totalSize`.

**Check.** The virtualized-table mock still renders every row. A two-row render includes Due and Due date and does not throw.

**Phase 4 done.** SH-16 through SH-23 pass, excluding SH-20.

---

## Phase 4b — URL state (separate PR)

### SH-20. Filters live in the URL

Do this only after Phase 4. It replaces the page’s filter state. It does not belong in the posting or money PR.

**File.** `SalesHistoryPage.tsx`

| Param | Example | History |
|---|---|---|
| `q` | `INV-00013` | `replace: true` after the 300ms debounce. A burst of keystrokes must not push a Back entry per burst. The input updates immediately. |
| `status`, `payment`, `customer`, `from`, `to`, `sort` | | `push` |
| `page` | `2` | `push`. Omit when 1. |
| `sort` | `due_desc` | Omit when `date_desc`. |

Invalid `status`, `payment`, `sort`, or a non-numeric `customer` is dropped.

Customer autocomplete receives `selected`. When the URL has `customer` and the option is not in memory, load that customer and pass it as `selected`.

Selection is not in the URL. Back restores filters and clears selection. No toast. Say that in the PR.

**Check.** Unpaid plus a customer in the URL is what the list request sends, including from `MemoryRouter` initial entries. Back restores the previous discrete filter. Typing three characters updates `q` with replace, and the history length does not grow by three. A custom from/to pair survives reload and shows Custom (SH-18). Changing a filter clears selection (SH-10).

---

## Phase 5 — Proof

### SH-25. Automated tests for the slice

Run, and keep green:

- Web: `SalesHistoryPage.test.tsx`, status tests, `HistoryFilterBar` tests, `documentDate.test.ts`, `invalidateInvoiceSideEffects` test, axe on the history page render (add `@axe-core/react` or `vitest-axe` if the repo does not already have one; use whichever the web app already depends on, and add one only if none exists).
- Backend: SH-06a parity, SH-14a monotonic due, SH-14 query count, SH-01 sole-approver and pending-dedup, SH-03 concurrent complete and same-key replay, SH-11 unavailable ids, plus the existing payment-stats count tests and the 100-id zip cap.

```text
cd web && npx vitest run src/pages/sales/SalesHistoryPage.test.tsx src/components/HistoryFilterBar.test.tsx src/utils/documentDate.test.ts
cd backend && pytest tests/test_sales_purchase_ux_plan.py tests/test_bug_open_sales.py tests/test_code_review_2026_10_05_b.py -q
```

Add new backend tests to an existing sales module unless it is already too large. Do not delete a test to stay green. The G-17 Returned-not-Paid case still passes.

### SH-26. Browser pass and keyboard pass

A Vitest render is not this pass.

1. Type a customer name in Search (the Gopal case). The matching row is on screen without scrolling, and the chip count matches that row. Then pick the same customer from the Customer box. The option appears, the list request sends that customer id, and the row stays visible. This is SH-28. Do not continue the pass if this step fails.
2. Owner, mixed bills. The SH-16 sentence is visible. Due and due date show on an open bill.
3. Filter Unpaid. Rows say Unpaid. The Unpaid chip shows a due amount. Switch to Partial. Rows say Partial. The other chips stay filled.
4. Record a partial payment. Stay on the list. The row’s chip matches the refetched `settlementState`. The due total matches the refetched stats. Then open the customer and the dashboard and confirm they are not the pre-payment figures.
5. Complete a draft. The dialog appears before any complete POST. After confirm, the bill has a number and a due amount. Dismiss the dialog on a second draft. That draft remains.
6. Cancel a completed bill that has a receipt. The dialog explains the blocker, focus starts on Reason, Escape returns to the actions button. After confirm, the alert is the server refusal and the status is still Completed.
7. Non-sole approver: the warning says waiting for approval, the row shows Cancel pending, and GET is still Completed. Cancel again: still one approval. Sole owner: 200, row Cancelled, and the UI does not say waiting for approval. Skip a branch only if that user does not exist in the environment, and write that down.
8. Select two rows, change customer, selection count is 0. Select a completed bill and a draft, download. The message names one PDF and the skipped draft. An id from another company is not named.
9. Set This month, reload, the month is selected. Set a custom from/to that matches no preset, reload, Custom is selected and both dates remain.
10. At about 600px width, Due date is hidden, Due is visible, the table scrolls, and the actions control is reachable. No overlap hides Due.
11. Keyboard only: reach search, a status chip, a row checkbox, the actions button, Complete’s dialog, and Cancel’s dialog without a pointer. axe on the page reports no serious or critical violations. File anything else against the SH item that owns that control.

### SH-27. After the POST, the GET agrees

One backend integration test per action. Each test does the POST, then GET `/sales/invoices/{id}/` and GET the list row.

| Action | GET after POST |
|---|---|
| Complete | `COMPLETED`, a number, `settlementState` `UNPAID` when nothing was collected |
| Cancel, sole approver | `CANCELLED` |
| Cancel, not sole approver | `COMPLETED`, `cancelApprovalPending` true, one approval row |
| Record payment, partial | `settlementState` `PARTIAL`, balance reduced by the receipt |
| Delete draft | GET detail is 404, and the id is not in the list |

**Check.** These five tests pass. They are the server-side version of “the screen did not claim a state the next read does not show.”

---

## i18n

Add every key to `web/src/i18n/en.ts` and `web/src/i18n/hi.ts` in the same change. A key present in both files with English text in `hi.ts` is not done.

Hindi strings are drafted in that change. The PR is not done until someone who reads Hindi accepts them. If that reviewer is not available, the item stays open. Do not mark i18n done on key parity alone.

Each user-visible sentence is one string with named placeholders. Do not build a sentence by concatenating `{label}` fragments in TypeScript. Hindi word order will not match English. The two that need the most care:

- `history.range` — English `{start}–{end} of {count}`. Hindi must be a full phrase, not those three pieces glued in English order.
- `history.paymentDue` and `history.paymentBilled` — the status name, count, and amount are placeholders inside one sentence.

| Key | English |
|---|---|
| `history.subtitle` | Find a bill, see what is still due, collect it, or reprint it. |
| `history.amend` | Amend |
| `history.confirmCompleteTitle` | Complete {label} |
| `history.confirmCompleteBody` | This assigns the tax invoice number, posts stock and the ledger, and leaves the full amount due. Record a payment after it is completed if the customer is paying now. |
| `history.confirmCompleteAction` | Complete invoice |
| `history.confirmCancelTitle` | Cancel {label} |
| `history.confirmCancelBody` | This reverses the ledger and restores stock when the bill is allowed to cancel. It will be refused if a receipt is still allocated, an IRN or e-way bill is live, or a return or credit/debit note is still on the bill. |
| `history.cancelReason` | Reason |
| `history.confirmCancelAction` | Cancel invoice |
| `history.cancelPending` | {label} is waiting for approval. It is still completed. |
| `history.cancelPendingChip` | Cancel pending |
| `history.cancelled` | {label} cancelled |
| `history.completed` | {label} completed |
| `history.openBills` | Open bills |
| `history.paymentDue` | {name} {count} · due {amount} |
| `history.paymentBilled` | {name} {count} · billed {amount} |
| `history.bulkDone` | {count} PDFs downloaded |
| `history.bulkSkipped` | Skipped: {numbers} |
| `history.bulkUnavailable` | {count} bills were not included |
| `history.bulkNone` | None of the selected bills have a PDF. |
| `history.pdfGenerating` | The PDF is still generating. |
| `history.retryPdf` | Retry |
| `history.searchLabel` | Bill number, customer, or phone |
| `history.due` | Due |
| `history.dueDate` | Due date |
| `history.range` | {start}–{end} of {count} |

Replace the hard-coded English success strings in `SalesHistoryPage` with these keys.

## Regression watch

| If this changes | Also check |
|---|---|
| `paidAwareStatus` | Invoice detail. Returned must not become Paid. Missing `settlementState` must not guess Partial. |
| `HistoryFilterBar` default `dateControl` | Every caller that omits the prop, including purchase history. |
| `payment_stats` amounts | Existing count assertions. OpenAPI description of `amount`. |
| `bulk_pdf_zip` | The 100-id cap. Clients that read `url` and `fileId`. |
| `cancelSalesInvoice` return type | Both call sites. A caller that still expects a bare `SalesInvoice` will not compile. |
| List query params | POS, receipts, customer 360, quotations, and complaints call `listSalesInvoicesPage`. Omitted `sort` stays the model order. |
| Invalidation helper | Detail still refreshes `sales-invoice` for that id. |
| Due sort annotation | SH-14a. A green sort test that only checks SQL `_balance` order is not enough. |

## Suggested commit slices

1. SH-28 only. Search and Customer. Nothing else in this PR.
2. SH-24 only.
3. SH-01–SH-05, including the failing-first lock test and the 200-vs-202 tests.
4. SH-06, SH-06a, SH-07, SH-09.
5. SH-10–SH-15 and SH-14a.
6. SH-16–SH-19 and SH-21–SH-23.
7. SH-20 alone.
8. SH-25–SH-27, and the browser notes, on the PR that contains SH-20 or the one immediately after it.

## Done when

All of these pass. A score is not part of this list.

- [ ] SH-28: typing a customer name in Search shows that row without scrolling, and the Customer box returns that customer from the server and filters the list by id. A one-row result is not header-only.
- [ ] SH-24 is in place before the posting PR, and history has no private single-key invalidate.
- [ ] Non-sole cancel is 202, the invoice GET stays `COMPLETED`, and a second cancel reuses one approval. The row shows Cancel pending.
- [ ] Sole-owner cancel is 200, not 202, and the UI says cancelled.
- [ ] Complete does not POST before confirm. One idempotency key covers a timeout retry and a confirm-flag retry. Two concurrent completes create one number.
- [ ] `settlementState` is the only Partial rule. SH-06a cases pass, including debit note, settlement discount, and a reversed receipt after a credit note.
- [ ] `due_desc` order matches displayed Due. Draft and cancelled are not ordered by a hidden balance. SH-14a passes. Due sort does not add per-row queries from 10 rows to 50.
- [ ] Zip `unavailable` is the same shape for a missing id and another company’s id, with no foreign invoice number.
- [ ] Record payment is shown from `canCreatePayments` and the dialog posts only `record-payment`.
- [ ] Selection count drops when a selected row leaves the list after delete, complete, or cancel.
- [ ] `q` updates the URL with replace. Discrete filters push. Back restores filters and clears selection.
- [ ] Overdue uses the `Asia/Kolkata` date. A returned bill with a balance is not overdue.
- [ ] Below 600px, Due date is hidden and Due remains.
- [ ] Hindi strings are accepted by a Hindi-reading reviewer. `history.range` and the payment chip strings are single sentences.
- [ ] OpenAPI snapshot and `openapi-types.ts` are regenerated for `sort`, zip `included` / `skipped`, and the `payment-stats` amount description.
- [ ] SH-27: complete, sole cancel, pending cancel, partial pay, and draft delete each match the following GET.
- [ ] SH-26 browser pass and keyboard pass have no failed step. axe reports no serious or critical violations.
- [ ] No menu action’s success text names a state the following GET does not show.
