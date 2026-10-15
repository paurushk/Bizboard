# Purchase module — second pass: returns, notes, bills of entry, planning, suppliers

Date: 2026-10-15 · Follows [PURCHASE_REVIEW_FIX_PLAN.md](../plans/PURCHASE_REVIEW_FIX_PLAN.md) WP-12.

**Depth, stated plainly.** I read each screen's mutations, confirmations, permission checks, error and empty
states, cache refresh and the tests that already exist. I did not re-derive the GST maths of the return and
note editors (they have their own server previews and tests), and I did not run any screen in a browser.
Labels: **[O]** observed in code · **[V]** needs a person or a running system to verify.

## Summary

| Screen | Verdict | Fixed in this pass | Logged, not fixed |
|---|---|---|---|
| Purchase returns | 🟢 READY | Completing a draft from the list had no confirm | none |
| Credit / debit notes (lists + editor) | 🟢 READY | Cancelling a completed note from the editor had no confirm | none |
| Bills of entry | 🟢 READY | Complete had no confirm | PB-01 (CA question) |
| Purchase planning | 🟢 READY | none needed | PB-02 |
| Suppliers | 🟡 READY WITH FIXES | Verify gave no feedback; one untranslated message | PB-03 |

## Purchase returns — [PurchaseReturnsPage.tsx](../../web/src/pages/purchases/PurchaseReturnsPage.tsx)

Good [O]: permission gates include the subscription write block; create, complete and cancel carry
idempotency keys; the credit-note total comes from the server preview; serial and batch picks are validated;
cancel and delete already ask; the lifecycle refresh covers returns, credit notes, bills, stock, suppliers and
dashboard; headroom is capped at the server's returnable quantity.

Fixed: the **Complete** button on a draft row posted the return (stock out, supplier credited) on one click.
It now asks through the in-app dialog and says what happens. Tests: confirmed → completes once; declined →
no call.

## Credit and debit notes — [PurchaseNoteEditorPage.tsx](../../web/src/pages/purchases/PurchaseNoteEditorPage.tsx), [PurchaseCreditNotesPage.tsx](../../web/src/pages/purchases/PurchaseCreditNotesPage.tsx), [PurchaseDebitNotesPage.tsx](../../web/src/pages/purchases/PurchaseDebitNotesPage.tsx)

Good [O]: the list pages confirm cancel; Complete runs the confirm-code retry (paid invoice, price override,
additional debit); CSV export is gated by `canExport`; the editor locks a completed note (`readOnly`).

Fixed: the editor's **Cancel document** button on a completed note reversed ledger entries on one click, while
the list page asked. It now asks, with the same wording as the list.

## Bills of entry — [BillsOfEntryPage.tsx](../../web/src/pages/purchases/BillsOfEntryPage.tsx)

Good [O]: write and cancel permissions, subscription block, cancel confirm, one action at a time (`pendingId`).

Fixed: **Complete** made customs duty and IGST claimable as ITC on one click. It now asks and says so.

- **PB-01 (P3, open — needs a CA answer).** The create form sends an empty amount as `0`. The server already
  refuses to *complete* a bill of entry with no BCD, IGST or cess ("needs a non-zero ... amount"), so a
  dutiless BoE cannot post. It does not check the **assessable value**, so a BoE with duty but a zero
  assessable value can complete. Whether that is ever legitimate is a tax question; if not, require it
  server-side at completion and mark the field required. **[V]** with the CA (added to
  [CA_SIGN_OFF_CHECKLIST.md](../ca/CA_SIGN_OFF_CHECKLIST.md)).

## Purchase planning — [PurchasePlanningPage.tsx](../../web/src/pages/purchases/PurchasePlanningPage.tsx)

Good [O]: create-drafts disables while pending and shows the server error (I first thought it failed silently;
it does not — the error is rendered under the help text); a single draft opens it, several go to the list;
suppliers needing a choice are counted; transfer rows are kept out of purchase drafts.

- **PB-02 (P3, open).** The supplier filter lists the first 200 suppliers only (`pageSize: 200`). A company
  with more cannot filter the plan by the rest. The same pattern was fixed on goods receipts with a searchable
  selector; reuse it here. No data risk — the plan can still be read unfiltered.

## Suppliers — [SuppliersPage.tsx](../../web/src/pages/purchases/SuppliersPage.tsx)

Good [O]: duplicate-GSTIN and checksum validation on save, place-of-supply requirement mirrors Customers,
sticky name column on mobile, price history behind a feature flag.

Fixed: **Verify** changed a chip with no message; it now confirms the check ran. The "valid 15-character
GSTIN" error was hard-coded English; it now uses the shared translated message.

- **PB-03 (P3, open).** The list loads every supplier (`listSuppliers`) and filters in the browser. Fine for
  hundreds, slow for tens of thousands. Move to the paged, server-searched list when a company reports it.
  Deactivating a supplier is one click; it is reversible, so no confirm was added.

## What was deliberately not changed

- `completeWithConfirms` still falls back to `window.confirm` when no dialog host is mounted (tests, embeds).
  Every real screen mounts the host in the app shell, and the lint rule added in WP-8 stops purchase pages
  from calling `confirm` directly.
