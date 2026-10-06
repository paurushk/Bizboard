# UX audit implementation plan

**Status:** Ready to build after the founder ratifies the decision table  
**Date:** 2026-09-29  
**Revised:** 2026-09-29, after review of this file and a spot-check of the code it cites  
**Source:** Live walk of the Docker app at `127.0.0.1` (Demo Traders), plus the items from [`UX_IMPLEMENTATION_PLAN.md`](UX_IMPLEMENTATION_PLAN.md) that the walk confirmed and the current code does not already do.  
**Finding record:** UX-001 … UX-027 in the Bizboard UX audit canvas.

This plan is the build order for those findings. It does not replace [`UX_IMPLEMENTATION_PLAN.md`](UX_IMPLEMENTATION_PLAN.md). Where the two disagree, this file wins. The adopted and rejected rows below are the full mapping, so nothing in the earlier document is dropped without a decision.

## Constraint

Stock movements, GST splits, derived ledgers, atomic purchase complete, and the credit-hold block stay as they are. Every task below is layout, copy, focus, or a local draft. A change that posts, unposts, or picks a different lot is out of this plan.

## Definition of done (every task)

A task is done only when all of these are true:

1. Its acceptance rows pass, including the test named on that task.
2. New copy exists in both `web/src/i18n/en.ts` and `web/src/i18n/hi.ts`. `web/src/i18n/fullParity.test.ts` passes (it already fails the build when a leaf key exists in only one catalog).
3. Any task that moves layout is checked at 375px width with the language set to Hindi, including the new blocker sentence, restore prompt, and credit line. Wrapped text must not cover the primary button.
4. The pull request in the ship table is the rollback unit. Revert that PR. Do not leave a half-applied `PosPage.tsx`.

## Decisions to ratify before build

These calls reverse proposals in [`UX_IMPLEMENTATION_PLAN.md`](UX_IMPLEMENTATION_PLAN.md). They were made in the audit, not by a named owner in that document. **The founder ratifies this table before anyone starts.** Until then, do not build a rejected row.

| Earlier plan | Decision | Why, checked against code |
|---|---|---|
| Remap F2 from scan to Pay & Print | **Rejected** | `NewInvoicePage.tsx` and `NewPurchasePage.tsx` already `preventDefault` on F2 and focus the barcode. `pos.subtitle` already says “Press F2 to scan barcode”. `PosPage.tsx` has no F2 listener today (only Ctrl/Cmd+B and Ctrl/Cmd+1–9). |
| New F7/F8 multi-cart | **Rejected as a second feature** | `holdAndCreateSession` and in-memory `sessionStore` already exist. The gap is persistence and the leave guard, tasks N5 and N9. |
| Proprietor PIN to override a credit hold | **Rejected** | `creditLimitExceeded` and `CreditHoldChip` already block Complete. |
| Per-GSTIN theme colors | **Rejected for this pilot** | One GSTIN per company. N8-header (task X9) shows the company name instead. |
| Split-pane bank match and a 6-second undo of a posted match | **Deferred** | Reconciliation was not walked. Undo of a posted allocation is a ledger change. |
| Optimistic cart row before the server price returns | **Rejected** | The counter already shows CGST/SGST from the priced line. A row at a guessed rate fights that. |
| RICE scores, SUS ≥ 85, 94% retention, checkout ≤ 2.5s | **Not targets** | No baseline. Signals at the end are new instrumentation unless the table says the data already exists. |
| Sticky bottom dock, scanner-first layout, draft restore, credit figures, inline short-stock, live total, 48px targets | **Adopted**, narrowed in the tasks below | See the adopted map. |

### Adopted from `UX_IMPLEMENTATION_PLAN.md`

| Earlier id | Lands as | Narrowing |
|---|---|---|
| UX-02 scanner first and focus lock | N2, N3 | F2 focuses the scanner. It does not open Pay. Adding a line does not steal focus from the scanner. |
| UX-01 sticky action dock | X1 | Title-row primary button stays on viewports under 600px. Dock padding includes `env(safe-area-inset-bottom)`. |
| UX-03 draft autosave | D1, N6 | One helper. Schema version, 36-hour TTL, revalidate party and price on restore. Logout clears it. |
| UX-04 credit badge | X3 | Uses `creditLimit` and `outstanding` already on the customer. No PIN. |
| UX-05 hold and recall | N9 (was X4) | Persist the sessions that already exist. No new F7/F8 feature. Pulled into Now. |
| FEFO tags and inline short stock | L6 | Display only. Does not choose the lot. |
| Live total, 48px targets, bottom sheets, focus ring | L7 | Scan beep stays off unless a setting is on. |
| UX-07 company color themes | X9 | Company name in the header only. |
| UX-08 shortcut cheat sheet | N2 | One line for the keys that exist, not a new map. |
| UX-09 mobile bottom sheets | L7 | POS tender confirm and receipt void first. |
| UX-10 scan beep | L7 | Default off. |

## How to ship

Estimates are planning days for one engineer who already knows this repo. They are not measurements.

| PR | Tasks | Days | Depends on | Can run beside |
|---|---|---|---|---|
| **PR-A Unlock** | N1 | 1 | Nothing. Ship first. | PR-B, PR-C |
| **PR-B Copy** | N8 rename only, X6 sentence only, X9, L1 | 1 | Nothing | PR-A, PR-C, PR-D |
| **PR-C Home** | N7 | 1 | Nothing | PR-A, PR-B |
| **PR-D Counter** | N2, then N4, then N3, then N5. One branch, one owner. All edit `PosPage.tsx`. | 4 | Nothing, but do not split the file across people | PR-A, PR-B, PR-C |
| **PR-E Drafts** | D1, then N6 and N9 | 3 | N5’s Discard must clear the store, so land N5 before N9. D1 can start once PR-D’s branch exists, on that same branch if the PosPage owner takes N9. | Not beside another `PosPage.tsx` editor |
| **PR-F Documents** | X1, X2, X3 | 3 | Nothing | PR-A through PR-C |
| **PR-G Queues** | X5, X6 field visibility (not the image rebuild), X7, X8 heading only | 3 | Founder answer on X8 before any predicate change | PR-F |
| **PR-H Later** | L2, L3, L4, L5, L6, L7, N8 allocate button if not in PR-B | 5 | L5 waits until N9 reports storage failure | After Now |

N8’s **Allocate** button is behaviour. The **rename** to Receipts is copy and belongs in PR-B. Do not mix them.

Rollback: `git revert` of that PR. There is no new production feature flag. N4 is the risky Enter change, so `PosPage.tsx` keeps a constant `POS_ENTER_EXACT_WINS` defaulting to `true`. A hotfix that sets it to `false` restores today’s Enter behaviour without reverting the layout from N3.

## Code checked while revising this plan

| Claim | What the code does |
|---|---|
| F2 on the counter | No F2 handler in `PosPage.tsx`. The keydown effect only handles Ctrl/Cmd+B and Ctrl/Cmd+1–9. |
| Held bills | `sessionStore` is a ref. It dies with the page. |
| Active cart already stored | `localStorage` key `bizboard:pos-active-cart:${companyId}` in `PosPage.tsx`. Company only, no user id. Logout does not remove it. |
| Cash-pending restore | `restoreCashPending` in `posStatus.ts` uses **sessionStorage**, key `bizboard.pos.cashPending.${companyId}:${userId}`. `clearPosPendingStorageForUser` runs from `AuthContext.tsx` on logout and clears that sessionStorage only. |
| GSTIN blocks Complete | `companyStepIncompleteNeedsGst` in `web/src/onboarding/taxHints.ts` is true only when `registrationType === 'REGULAR'` and GSTIN is blank. Composition and unregistered are not blocked. Invoice type `NON_GST` also skips the gate. |
| Low stock equality | `low_stock_alert_payload` in `backend/inventory/views.py` includes a row when available **`<=`** reorder (company-wide and per-godown override). `insights/services.py` uses the same `<=` for the stock score. |
| i18n parity | `web/src/i18n/fullParity.test.ts` requires every `en` leaf key in `hi` and the reverse. |

---

## Slice Now

### N1 — Offline page only when the network failed (UX-001)

**Why.** `web/vite.config.ts` sets `navigateFallback: '/offline.html'` and `handlerDidError` returns the cached offline page. `networkTimeoutSeconds` is already **10**. “Try again” in `web/public/offline.html` goes to `/?reload=1`, which the same worker intercepts. “Reload without cache” unregisters the worker. Workbox `registerType` is `'prompt'`, so a new worker does not take the page until the user accepts the update. A browser already stuck on the old offline shell will not run the new worker until something unregisters the old one.

**Steps**

1. Keep the navigation timeout at **10 seconds**. Do not leave it undecided.
2. In `web/public/offline.html`, point **Try again** at the unregister-then-`location.replace` path that “Reload without cache” already uses. If `navigator.onLine` is true, the heading says the page could not be loaded. Use “You’re offline” only when `navigator.onLine` is false.
3. Leave `navigateFallbackDenylist` covering `/api/`. Serve `offline.html` only from `handlerDidError`, not as the body of a successful response.
4. Do not flip the app to `autoUpdate`. That reloads a counter mid-bill. For this release, the escape hatch for a client already stuck is the button that unregisters. After this HTML is what the worker precaches, Try again is that button.
5. Bump the precache revision of `offline.html` (any real edit does this) so the next successful load stores the new page.

**Acceptance**

- Timeout in `vite.config.ts` is 10.
- With the API healthy, after the new worker controls the page, reload shows login.
- Try again on the new offline page reaches login without a second manual unregister.
- `navigator.onLine === false` still shows “You’re offline”.
- A client stuck on the **old** shell still has “Reload without cache”. The verification checklist tells the operator to press it once per stuck browser. That is the rollout, not a code task.

**Test.** Playwright in `web/e2e`: build the PWA, register the worker, stub a failed document navigation, click Try again, expect the login form. Assert the offline HTML contains the unregister call and does not use `/?reload=1` as the primary action. Hand-check one stuck browser with the checklist below.

### N2 — F2 focuses the scanner on the counter (UX-020)

**Why.** Checked: `pos.subtitle` promises F2. `PosPage.tsx` does not listen for it. Invoice and purchase do.

**Steps**

1. In the existing keydown effect, on `F2` call `searchRef.current?.focus()` and `preventDefault`. Do not open tender. Ignore F2 while a dialog is open or while focus is in the batch or serial field (those fields need typing). From anywhere else, F2 moves to the scanner.
2. Add the keys that exist to the subtitle: F2 scan, Ctrl/Cmd+B hold, Ctrl/Cmd+1–9 switch bill.

**Acceptance**

- On `/pos`, F2 focuses the scan field from the tender panel.
- F2 inside the batch field does not move focus.
- Ctrl/Cmd+Enter still completes an invoice. F2 on `/sales/new` still focuses that page’s barcode.

**Test.** In `web/src/pages/pos/PosPage.creditLimitBanner.test.tsx` (or a new `PosPage.keyboard.test.tsx`): dispatch `F2`, expect the search input to be `document.activeElement`. Dispatch `F2` while the batch input is focused, expect focus to stay.

### N4 — Enter: exact code wins, highlighted name does not also error (UX-006)

Do this before N3, on the same branch, so the scan field moves only after Enter is correct.

**Why.** The scan `TextField` `onKeyDown` always calls `tryAddByBarcode()` on Enter. That function adds a line only on an exact barcode or SKU (`F2-052`). MUI also selects the highlighted option. A name query such as `milk` therefore adds Full Cream Milk 1L and shows `pos.barcodeNotFound`. Autocomplete does not tell `onKeyDown` which row is highlighted. Options are debounced 250ms (`useDebouncedValue(productQuery, 250)`).

**Steps**

1. Track the highlighted option with `onHighlightChange`. Store it in a ref.
2. On Enter, decide in this order:
   - If the current input is an exact barcode or SKU of a known product, add that product and do not select the highlight. A scanner wedge that types a code while an old fuzzy row is still highlighted must add the code.
   - Else if the list is open, a row is highlighted, and the input is not an exact code, select that row and do not call `tryAddByBarcode`.
   - Else if the debounced options have not caught up (Enter within the 250ms window, or the input has no spaces and length ≥ 8), wait out the debounce, then exact-match. Do not select a stale highlight. If nothing matches, show `barcodeNotFound`.
3. Clear `barcodeNotFound` when `addProduct` succeeds.
4. `POS_ENTER_EXACT_WINS` defaults to `true` and gates steps 2’s exact-wins branch. `false` restores today’s always-`tryAddByBarcode` Enter.

**Acceptance**

- `milk` with Full Cream Milk 1L highlighted: one line, no barcode error.
- Exact SKU `MILK-FC-1L` typed while a different fuzzy row is highlighted: the SKU’s product, not the fuzzy row.
- Enter before options refresh, on a barcode, does not add the previously highlighted product.
- A nonsense code: not-found, no line.
- `F2-052` still holds: one fuzzy hit is not added silently when nothing is highlighted.

**Test.** `PosPage.keyboard.test.tsx` covers the four cases above. Include “exact SKU typed while a fuzzy option is highlighted”.

### N3 — Scan first, and say why tender is disabled, without eating the next scan (UX-002, UX-005)

**Why.** The scan `Autocomplete` is rendered after customer, the disabled walk-in name, godown, and serials. Tender buttons show the rupee amount and stay disabled until a batch is filled. The walk-in name field is `disabled` while its helper says the typed name will be billed.

**Do not move focus into the batch field when a line is added.** A hardware scanner would type the next barcode into the batch. The blocker stays on the tender. Focus returns to the scanner after the clerk commits a batch.

**Steps**

1. Order the counter column: scan field, line table, then one compact row for customer, godown, and serials. Serials stay collapsed unless a line tracks serials.
2. Show “Or type customer name” only after the clerk chooses a name-only sale, and then enable it. Remove the disabled field whose caption promises an action.
3. Keep tender disabled until the batch is non-empty. Render the existing sentence (`Enter a batch number for each batch-tracked item to complete`) in an element with a stable id, directly above the buttons. Set `aria-describedby` on each tender button to that id. The accessible name includes the amount, for example “Cash, ₹63.00”.
4. On Enter or blur of a batch field that now has a value, focus `searchRef`.
5. Do not auto-fill a lot. Complete still refuses an empty batch.

**Acceptance**

- A fresh `/pos` shows the scan field without passing customer, godown, and serials.
- Adding a batch-tracked line leaves focus in the scanner. A second scan is not typed into the batch field.
- `getByRole('button', { name: /Cash/i })` has `aria-describedby` pointing at the blocker text.
- After the batch is committed, focus is back on the scanner and Cash enables. Stock, tax, and the posted receipt are unchanged.

**Test.** `PosPage.keyboard.test.tsx`: add a batch item, assert `activeElement` is the scanner, fire a second Enter with another code, assert the batch input’s value is still empty. Assert the Cash button’s `aria-describedby` target contains the batch sentence. Update `PosPage.creditLimitBanner.test.tsx` if it assumes the old field order.

### N5 — Stay or Discard when leaving the counter (UX-007)

**Why.** `NewInvoicePage` and `NewPurchasePage` render `UnsavedChangesGuard`. `PosPage` does not. `sessionStore` does not survive the route change. A Hold action on this guard would drop the bill, because persistence is N9, not this task.

**Steps**

1. Render `UnsavedChangesGuard` when any session has a line, a typed walk-in name, or a non-zero tender.
2. The confirm has two actions: Stay and Discard. Copy: “This bill has items. Stay on the counter, or discard the bill?”
3. Discard clears the in-memory session and the device draft for that session (D1). Stay stays on `/pos`.
4. Suppress the guard after a successful complete, same `skipLeaveGuard` pattern as the invoice editor.

**Acceptance**

- With a line on the cart, Sales → New Invoice shows Stay and Discard. There is no Hold button.
- Stay keeps the line. Discard opens the invoice and the cart is empty, including storage.
- A completed sale does not ask.

**Test.** POS test: guard is mounted when `cart.length > 0`, and the dialog has no button named Hold. `UnsavedChangesGuard` tests stay green.

### D1 — One device-draft helper (shared by N6 and N9)

**Why.** N6 and N9 both need company- and user-scoped storage. Building two stores would diverge. Cash-pending is the wrong store to copy: it is sessionStorage and is only for a payment that already started. The active POS cart is already in `localStorage` under `bizboard:pos-active-cart:${companyId}` with no user id, and logout does not clear it. On a shared counter PC that is a leaked bill.

**Steps**

1. Add `web/src/lib/deviceDraft.ts`.
   - Key: `bizboard:draft:v1:${companyId}:${userId}:${kind}` where `kind` is `sales-invoice`, `purchase-bill`, or `pos-sessions`.
   - Value: `{ version: 1, savedAt: ISO timestamp, payload }`.
   - TTL **36 hours**. A missing version, a version other than 1, or `savedAt` older than 36 hours is discarded.
   - `read`, `write` (debounced by the caller), `remove`, `clearForUser(companyId, userId)`.
   - On quota errors, return a result the caller can show. Do not throw.
2. Call `clearForUser` from the same logout path as `clearPosPendingStorageForUser` in `AuthContext.tsx`.
3. On that same logout, remove the legacy key `bizboard:pos-active-cart:${companyId}`. Stop writing that key once N9 writes `pos-sessions` through this helper.
4. Do not put these drafts in the offline outbox, and do not store them in sessionStorage.

**Acceptance**

- A draft for company A user 1 is invisible to company B and to user 2.
- A draft older than 36 hours is not offered.
- Logout removes `pos-sessions`, `sales-invoice`, and the legacy `bizboard:pos-active-cart:` key for that user and company.
- A second user logging in on the same browser does not see the first user’s lines.

**Test.** `web/src/lib/deviceDraft.test.ts`: round-trip, wrong user, expired `savedAt`, bad version, quota throw, `clearForUser`. Extend `posStatus.test.ts` or the auth test so logout calls `clearForUser` and deletes the legacy cart key.

### N6 — Invoice draft restore (UX-022)

**Depends on D1.**

**Why.** `UnsavedChangesGuard` warns on leave. It does not restore lines. `restoreCashPending` only restores a POS payment that had started, and only for the same tab’s sessionStorage.

**Steps**

1. Debounce writes of the new sales invoice (no server id) through D1: party id, product ids, quantities, discounts, notes, invoice type, price mode. **Do not store a unit price as the price that will be posted.**
2. On mount, if a fresh draft exists, ask “Restore the bill from this device?” Restore and Discard.
3. On Restore, re-fetch the party and each product:
   - Drop a line whose product no longer exists, and say which line was dropped.
   - Set the line price from the current product price, not from the draft. If the current price differs from what the clerk last saw, show “Prices were updated.”
   - If the party is gone, restore lines only and leave Bill To empty.
4. Delete the draft after a successful server save and after Complete. Discard deletes it.
5. Do not call Complete from restore.

**Acceptance**

- Reload with a half-filled new invoice: prompt, Restore brings party and lines back at **current** prices, Discard starts empty.
- A deleted product is omitted with a message. A changed selling price is the new price, with the update note.
- A draft older than 36 hours does not prompt.
- Complete, reload: no prompt.
- Logout, then another user on that browser: no prompt.

**Test.** Hook or page test with a mocked product fetch: stale price in the stored payload is ignored; the component shows the fetched price. Expired draft is ignored.

### N9 — Persist held counter sessions (UX-024, formerly X4)

**Depends on D1 and N5.** Pulled into Now so a reload keeps the bill. N5 does not offer Hold.

**Why.** Hold and Ctrl/Cmd+B already stash another cart in `sessionStore`. That ref dies on navigation and reload. The legacy `bizboard:pos-active-cart:${companyId}` key persists one cart without a user id.

**Steps**

1. Write all POS sessions (lines, party, warehouse, tender text, batch and serial text) through D1 kind `pos-sessions`. Include `userId` in the key. Stop writing the legacy company-only key.
2. On mount, if memory is empty, restore non-expired sessions. Re-fetch each product the same way as N6. Do not restore a session that already completed.
3. Keep the Hold button and Ctrl/Cmd+B. Do not add F7/F8.
4. N5 Discard and logout both clear this kind.

**Acceptance**

- Hold a two-line bill, reload `/pos`: the bill is back, still a draft, stock unchanged, prices re-fetched.
- Complete it: reload does not bring it back.
- User 2 on the same browser does not see user 1’s held bill.
- Logout clears it.

**Test.** `deviceDraft` plus a POS mount test that seeds `pos-sessions` and expects the lines. Assert the legacy key is not written.

### N7 — Home shows the shop, not the telemetry table (UX-003, UX-004)

**Why.** `DashboardPage.tsx` renders the counter journey table (`dashboard.shopFloor`, `completeP95`) above the rupee figures. The invite banner uses `onboarding.inviteStaffDescription` (“Your first bill is complete…”) even when a regular dealer has no GSTIN.

**GSTIN rule, checked.** The complete gate uses `companyStepIncompleteNeedsGst`: registration type `REGULAR` and a blank GSTIN. Composition and unregistered companies are not blocked. A `NON_GST` invoice is not blocked. The banner must use that same predicate, not “GSTIN is empty”.

**Steps**

1. Move the journey table off the first screen. Keep it behind a collapsed “Counter diagnostics” control so the numbers are not deleted.
2. First region: today’s sales, this month, customer outstanding, supplier payables, cash, then Needs attention.
3. When `companyStepIncompleteNeedsGst(company)` is true, replace the invite banner with “Add your GSTIN before a GST bill can be completed” linking to `/settings/gst`. Do not show that sentence for composition or unregistered. Show the invite banner only when the predicate is false and `bb_invite_cta_dismissed` is not set.
4. Leave the invoice-editor GSTIN banner in place. It already uses the same predicate.

**Acceptance**

- Owner landing shows rupee figures before any p95 row.
- Regular dealer, blank GSTIN: the GSTIN banner, not “your first bill is complete”.
- Composition or unregistered, blank GSTIN: no GSTIN-required banner.
- Regular dealer with a GSTIN: invite banner behaves as today.

**Test.** `DashboardPage` test: three companies (regular blank GSTIN, regular with GSTIN, composition blank GSTIN). Assert banner presence. Assert the diagnostics table is not the first heading.

### N8 — Receipts: rename now, Allocate in the same Now slice (UX-009)

**Why.** `nav.receipts` is “Customer Payments (Payment In)”. `ReceiptsPage.tsx` shows Advance, and the row action is Void.

**Steps**

1. **PR-B (copy):** `nav.receipts` becomes “Receipts” in `en.ts` and `hi.ts`. Helper text on the page may still say payment in.
2. **Behaviour, same slice, can be the copy PR only if the test below is included:** when advance &gt; 0, the primary row button is Allocate and opens the existing allocation screen for that receipt. Void stays behind the current confirm. A fully allocated row has no Allocate button.

**Acceptance**

- Title reads Receipts in English and Hindi (`fullParity`).
- Allocate does not void. Void still confirms and uses the current API.
- Fully allocated row: no Allocate.

**Test.** `ReceiptsPage` test: a row with advance shows Allocate and Void; a fully allocated row shows Void only; Allocate’s link is the existing allocation route.

---

## Slice Next

### X1 — Sticky action dock on long documents (UX-021)

**Why.** `DocumentEditorShell.tsx` puts the save buttons in the title row. `QuickEntryPage.tsx` already uses `position: 'sticky', bottom: 8`.

**Steps**

1. Add `DocumentEditorBottomDock.tsx`. It shows grand total, tax, the existing `primaryDisabledReason` (or “Ready”), Save draft, and the primary action. It calls `onDraft` and `onPrimarySave`. It does not add a new save API.
2. Render it from `DocumentEditorShell`. `padding-bottom: env(safe-area-inset-bottom)`. `position: sticky; bottom: 0`.
3. From the `sm` breakpoint up, the dock is the only button row. **Below 600px, keep the title-row primary button** so the on-screen keyboard and browser chrome cannot hide the only Complete. The dock still shows the total and the blocker.
4. Label the control that runs `onSaveAndNew` with what that handler already does. If it completes, the label is “Complete and start another”.
5. Shortcuts stay: Ctrl/Cmd+S draft, Ctrl/Cmd+Enter complete, F2 scan.

**Acceptance**

- A 15-line invoice on a desktop height keeps Complete on screen without scrolling to the title.
- At 375px the title-row primary button is still in the document, and the dock is not covered by a home-indicator inset (the safe-area padding is on the dock).
- Missing GSTIN still disables Complete, reason visible in the dock.
- Quick Entry does not gain a second bar.

**Test.** `DocumentEditorShell.test.tsx`: reason text is in the dock; below the `sm` media the primary button is still rendered in the title row (assert both nodes when width is mocked, or assert the title button is not removed unconditionally).

### X2 — One payable figure; invoice defaults that a test can name (UX-008, UX-013)

**Why.** A milk line showed MRP ₹62, price ₹60, and total ₹63. New invoices open as GST / B2B, tax exclusive, 30-day terms. The empty Bill To control repeats “Bill To”.

**Heuristic (testable).** Look at the last **5** completed sales invoices for this company.

- If fewer than 3 exist, use `preferredInvoiceType(registrationType)` from `taxHints.ts` (GST for `REGULAR`, `NON_GST` otherwise) and the company’s saved price mode.
- If at least 3 of those 5 are walk-in retail (no credit customer, or invoice type retail / non-GST as the code already classifies them), default the new invoice to that type and to tax-inclusive when that was the mode on the majority of those 5.
- Otherwise keep today’s GST, tax-exclusive, 30-day default.

**Party override.** When the clerk selects a customer with payment terms set, or with `creditLimit > 0`, copy **that customer’s terms** onto the invoice and do not leave a credit customer on 0-day terms. This override runs after the heuristic.

**Steps**

1. POS: the large figure is the amount the customer pays. MRP and the exclusive rate stay at caption size. CGST and SGST stay visible as they are now.
2. Implement the heuristic and the party override in `NewInvoicePage.tsx`. Do not change tax math.
3. Bill To placeholder: “Search by name, phone, or GSTIN”. The label stays “Bill To”.

**Acceptance**

- The POS figure a clerk would read aloud equals the tender amount.
- A company whose last 5 completed bills include at least 3 walk-in retail bills opens a new invoice as retail / tax-inclusive, not 30-day B2B.
- A company with 2 completed bills uses `preferredInvoiceType`.
- Selecting a customer with 15-day terms sets terms to 15 even if the heuristic chose retail.
- Switching type to a GST invoice still splits CGST/SGST or IGST as the current calculator does.

**Test.** Pure function test for the heuristic: 5 bills with 3 walk-in; 2 bills only; customer terms override. Name the cases in the test title.

### X3 — Credit line under the customer (UX-023)

**Why.** `NewInvoicePage.tsx` already computes `creditLimitExceeded` and shows `CreditHoldChip` after the fact.

**Steps**

1. When `creditLimit > 0`, show outstanding, limit, and available (`limit - outstanding`) under the party field, using `formatMoney`.
2. Amber when outstanding is at least 80% of the limit and this bill does not exceed it. Red when `creditLimitExceeded` is already true. Red still disables Complete through the existing gate.
3. No PIN, no new API.

**Acceptance.** The three figures show as soon as the customer is selected. A bill that crosses the limit still cannot complete, with the same error as today. No limit: nothing new.

**Test.** Extend the invoice credit-limit test: customer under 80%, at 80%, and over the limit after this bill’s total.

### X5 — Attention: one Fix on setup blockers (UX-010)

**Why.** `AttentionPage.tsx` prints `attention.learningReport`. Setup rows offer Assign, Snooze, and Dismiss. Titles truncate.

**Steps**

1. Remove the learning-report line from this page. Leave the API if something else reads it.
2. A critical row whose only real action is Fix (missing company GSTIN, invalid party GSTIN) renders Fix only.
3. Wrap the full reason in the problem cell.
4. Change the visible label “Open rate back-scan” to “Review GST rates on these bills”. Keep the route.

**Acceptance.** The GSTIN row has one button, Fix, still opening GST settings. Overdue still has Send Link, Snooze, and Dismiss.

**Test.** Update `AttentionPage.test.tsx`: it currently expects “Learning report”. Replace that assertion. Add a setup row with no Dismiss button.

### X6 — Purchase copy, without hiding RCM or ITC (UX-011)

**Why.** `billing.grnGuidance` tells the clerk to use a GRN later. Complete already posts stock and the payable together. Reverse charge and ITC eligibility change the tax treatment. Hiding them behind Advanced is a compliance miss. Bills of Entry is already `visible: () => false` in `web/src/navigation/menu.ts`; the walk saw it because the running image was older than that source.

**Steps**

1. Replace `grnGuidance` with “Complete posts the stock and the supplier bill together.” English and Hindi.
2. Leave reverse charge and ITC eligibility on the GST purchase form, visible without opening Advanced.
3. Collapse Bill of Entry and ship-from (import fields outside the pilot) behind Advanced. Defaults for an untouched bill stay as they are today.
4. When purchase type is GST and the supplier has no GSTIN, show: “This supplier has no GSTIN. Turn on reverse charge if this purchase is under RCM.” Do not build an HSN-to-RCM table in this task.
5. Do not treat “rebuild the web image” as a code step. It is in the verification checklist, so the nav hide already in source is what the pilot serves.

**Acceptance**

- RCM and ITC are visible on a new GST purchase without an extra click.
- A supplier with no GSTIN shows the warning. The clerk can still turn RCM on.
- An untouched purchase posts the same stock and AP as before.
- The GRN sentence is gone in both languages.

**Test.** `NewPurchasePage` test: RCM control is in the document on first paint; GRN guidance string is absent; unregistered supplier shows the warning.

### X7 — Shorter Sales, and which billing screen to open (UX-012)

**Steps**

1. In `menu.ts`, keep New Invoice, Receipts, and Customers directly under Sales. POS stays top-level. Group returns, notes, orders, challans, routes, recurring, upload, and quick entry under a “More” child. Same paths.
2. One sentence on `/sales/new` and `/pos`: “Counter sale: Point of Sale. Credit bill or quotation: New Invoice. Fast repeat lines: Quick Order Entry.” Link each.
3. Do not delete routes. Keep every `visible` predicate.

**Acceptance.** At a viewport height of 800px, with Sales open, Purchases is on screen or reachable without the open list covering it. All three billing routes load. A Sales Staff user still lacks the links their flags hide.

**Test.** A nav unit test: the Sales children rendered for an owner include More, and More’s children include the old paths. A permission fixture for Sales Staff still hides purchases.

### X8 — Low-stock heading, predicate unchanged until the founder says (UX-014)

**Why.** The dashboard count included items where available equals reorder, and the number is a heading. **Checked:** `low_stock_alert_payload` and the insights stock score both use `available <= reorder`. The reorder hint in `en.ts` calls it “Minimum safety stock for low-stock alerts.” Hitting the level is currently an alert, on the dashboard, the low-stock page, and the score.

**Decision.** Do **not** change `<=` to `<` in this plan. A reorder point often means “reorder when you hit it.” Changing the dashboard query alone would disagree with Attention and purchase suggestions if they share `low_stock_alert_payload`.

**Founder question, blocking any predicate change:** should available equal to reorder stay an alert everywhere? Default if the founder does not answer: **yes, keep `<=` everywhere.**

**Steps now**

1. Heading text is “Low stock”. The count is the value, not the heading. English and Hindi.
2. Leave the query as `<=`.

**If the founder says equality is not an alert:** change `low_stock_alert_payload`, the insights score, and every caller in one PR, with a test that `available == reorder` is excluded and `available < reorder` is included. Do not change only the dashboard.

**Acceptance.** Screen reader hears “Low stock” and then the number. An item at the reorder level still appears, matching the API, until the founder says otherwise.

**Test.** Dashboard test: the heading role’s name is “Low stock”, not the number. No change to `backend/tests` that assert `<=` unless the founder flips the rule.

### X9 — Company name in the header (UX-027)

**Why.** `AppShell.tsx` renders `t('app.name')` in the toolbar. The company name is not there.

**Steps.** Next to the product name, show the active company name from the same context the sidebar uses. Truncate with a tooltip of the full name. No per-company theme color. English product name stays; the company name is data, not a catalog string. If the shell has no company yet, show only Bizboard.

**Acceptance.** Signed in to Demo Traders, the header shows Bizboard and Demo Traders. At 375px the name truncates and the tooltip has the full string. A company switch updates the header.

**Test.** `AppShell` test with a company fixture: header text includes the company name. Fixture with no company: product name only.

---

## Slice Later

### L1 — One glossary (UX-015) — ship inside PR-B

| Current | Replacement |
|---|---|
| Customer Payments (Payment In) | Receipts (N8) |
| Supplier Payments (Payment Out) | Supplier payments |
| Purchase Inv Date | Purchase bill date |
| Godowns (field label on editors) | Warehouse |
| Source: MANUAL on a typed receipt | Hide Source unless the value is not manual |
| Status Completed on an unpaid invoice | Unpaid when a balance is still open. Keep Paid and Returned |

Do not rename API enums. Map them at the label. `fullParity.test.ts` is the Hindi check.

**Test.** Update the tests that assert the old English strings. Ledger totals are unchanged, so no backend test edits.

### L2 — Reject party names that are not names (UX-016)

UI and API. A UI-only check is bypassed by import and API clients.

1. Customer and supplier serializers: reject a name containing `<` or `>` or with no letter or digit. Same message the form shows: “Enter the customer’s name” / supplier equivalent.
2. The form shows that message on the field.
3. Do not rewrite historical rows. Keep rendering them as text.

**Test.** Backend test: POST a customer named `<script>alert(1)</script>` is 400. “Sharma Medicals” is accepted. A form test asserts the helper text. An existing bad name still renders as text on the receipt list.

### L3 — Short document numbers in lists (UX-017)

List link text is the trailing sequence plus the financial year when needed, for example `INV-13 · 2026-27`, so two series cannot both look like `INV-13`. The `title` attribute and the document page and the PDF keep the full number. Search matches the full number and the short form. Do not renumber posted documents.

**Test.** Two invoices that share a trailing sequence in different years render distinct link text. A search box test (or the universal-search unit) finds the row by the full number and by `INV-13`.

### L4 — One live region per alert (UX-018)

One node for the login error. One help control on the dashboard. One POS alert node.

**Test.** Testing-library: one element with text “Email or password is incorrect.” One button named “Help for this page” on the dashboard.

### L5 — Counter limitation copy only when it matters (UX-019)

Hide the permanent online-only / hold banner during a normal online sale. Show it when `navigator.onLine` is false or when D1 reports a write failure. Empty state stays “Scan or search to add items.”

**Test.** POS test: banner absent when online and the draft write succeeds; present when the draft helper returns a quota error.

### L6 — Short stock and shelf life in the cell (UX-025)

In `DraftLineTable.tsx` and the POS line:

- On quantity change, if on-hand in the selected warehouse is below the quantity and the negative-stock policy is block, show “In this warehouse: {n}. Complete will be blocked.”
- Expiry tag: red under 15 days or expired, amber 15–60, green beyond 60. The tag does not choose the lot.

**Test.** Line table test: quantity 12 against on-hand 4 renders the helper. Complete still uses the existing policy (no new block). A batch expiring in 10 days has the red tag. Hindi string does not overflow the cell at 375px (assert the string exists; the width check is on the hand-check list).

### L7 — Access and narrow screens (UX-026)

1. `aria-live="polite"` on the POS payable total and the invoice grand total.
2. `MuiButtonBase` `focus-visible` outline from the theme primary, 2px, offset 2px.
3. Tender buttons, quantity steppers, and row actions: minimum 48×48px below `sm`.
4. POS tender confirm and receipt void: `Dialog` at `md` and up, bottom `Drawer` below `md`.
5. Scan beep off unless a setting is on.

**Test.** Button style test or theme test: `focus-visible` outline is set. A render at a mocked width under `sm` gives the Cash button a min-height of 48. Void confirm uses a drawer when the matchMedia query is narrow. Totals have `aria-live="polite"`. Default settings: no audio element played on scan.

---

## Verification

After each PR:

```sh
cd web && npm test -- --run
cd web && npm run lint
```

`fullParity.test.ts` is part of `npm test`. A missing Hindi key fails that run.

Backend workflow tests (`backend/tests/workflows/`) pass with no test edits. If one fails, the UI change reached posting and the PR is reverted.

### Playwright

Add `web/e2e/ux-audit-now.spec.ts` and run it on PR-A and PR-D, not only by hand. It covers:

1. Try again leaves the offline shell when the document request fails and then succeeds.
2. F2 focuses the POS scanner.
3. Enter on a highlighted name adds one line and does not show the barcode error.
4. A second scan after a batch-tracked line does not type into the batch field.
5. Leaving `/pos` with a line offers Stay and Discard, not Hold.
6. Dashboard rupee region is above the diagnostics table.
7. A receipt row with an advance exposes Allocate.

The rows below stay as a release check on the Docker app, in English and once in Hindi at 375px. They are not a substitute for the spec.

| Check | Pass |
|---|---|
| Browser stuck on the old offline page | “Reload without cache” once, then login. New shell: Try again is enough. |
| F2 on `/pos` | Scan field focused |
| Exact SKU while a fuzzy row is highlighted | The SKU’s product |
| Leave `/pos` with a line | Stay / Discard only |
| Reload a half-filled invoice | Restore uses current prices. Logout then another user: no restore. |
| Regular dealer, no GSTIN | GSTIN banner, not the first-bill banner |
| Composition dealer, no GSTIN | No GSTIN-required banner |
| 15-line invoice at desktop width | Complete visible without scrolling to the title |
| Same invoice at 375px | Title-row primary button still present |
| GST purchase | RCM and ITC visible. No GRN sentence. |
| Web image for the pilot | Bills of Entry is absent from the sidebar |

### Signals

Do not treat these as pass/fail targets until a pilot week has a baseline. Rows marked **new** need event plumbing that does not exist yet. Do not describe them as already counted.

| Signal | Work |
|---|---|
| False barcode error after a successful add | **New.** One event when `barcodeNotFound` is set in the same turn as `addProduct`. |
| Leave-guard discards on `/pos` | **New.** Event on Discard. |
| Draft restored | **New.** `draft_restored` with `kind` and age in seconds, from D1’s read path. |
| POS completes with no pointer events | **New.** The complete handler does not receive `pointerCount` today. Add a counter of pointer events on `/pos` since the last successful tender, and send it on complete. |
| Time from first scan to successful tender | **New** unless a shop-floor timer in `telemetry.ts` already wraps this path. Confirm before reusing it. If it does not, add a start timestamp on the first `addProduct` and a duration on complete. |
| Unallocated receipt balance | **Exists** on the receipt list as Advance. Snapshot it weekly. No new event required for the first week. |
| Same-day sales credit notes | **Exists** as documents. A weekly count is a query, not a new client event. |

A Now task is done when its test and the definition of done pass. Two weeks later, look at the signals. They are not the merge gate.
