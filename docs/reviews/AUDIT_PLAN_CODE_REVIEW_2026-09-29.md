# Code review — audit P0 plan (2026-09-29)

Scope: the implementation of the audit decisions in
[SURFACE_A_COMPETITIVE_AUDIT_2026-09-29.md](SURFACE_A_COMPETITIVE_AUDIT_2026-09-29.md):
one outstanding figure + books/back-fill, HSN behaviour, POS server total + split tender,
GSTR worksheets, promise-to-pay/collections, archetype-pack navigation.

Method: read every diff in those areas; ran the plan's own tests (93 passed); booted the
tree and exercised it live (fresh books-on company, legacy company that enabled books
mid-life, POS, split tender, receipts, worksheets, collections, invoice promise dialog);
type-check, lint, ruff, migration check, OpenAPI snapshot/type drift.

## What was already right (verified live)

| Check | Result |
|---|---|
| New signup: books on, opening stock posts to GL, TB ties, inventory GL = valuation, no back-fill nag | Pass |
| Legacy company with history and books enabled late: every surface shows the document figure (5,317.80, not ₹0) until back-fill | Pass |
| Back-fill: preview, confirm, TB ties, variance 0, all surfaces then agree (4,997.80, ₹320 advance netted, ageing foots via "advances and other") | Pass |
| ₹3,000 T-shirt → 18%; ₹2,700 shirt at 10% off → 5%; unset branded rice keeps the product rate with a notice; branded → 5% | Pass |
| POS: mismatch is a 409 with a human sentence; confirm posts at the server total | Pass |
| GSTR-1/3B worksheets tie to the registers (₹10,310) and carry "Not filed — worksheet for your CA" | Pass |
| Collections: real customer total, Remind link with normalised phone | Pass |

## Defects found and fixed

| # | Sev | Where | Defect | Fix |
|---|---|---|---|---|
| 1 | High | `payments/views.py` receipt create | Receipt and oldest-first allocation were separate transactions. If allocation failed, the receipt stayed, the idempotency key was released, and a retry posted a **second receipt**. | One `transaction.atomic()` around both. |
| 2 | High | `sales/views.py` split tender | No `confirm_totals_mismatch` path, so the reconcile dialog re-created the POS dead-end for split payments; each part allocated uncapped, so a ≤₹0.05 overshoot failed the whole checkout; nothing stopped collecting more than the bill. | Honour the confirm flag; refuse over-collection; absorb ≤₹0.05 drift in the last part. |
| 3 | High | `InvoiceDetailPage.tsx` | Promise dialog sent no amount; the API now requires one, so **every promise from an invoice failed** (and `tsc -b`, hence `npm run build`, failed). | Amount field (prefilled with the balance); Save disabled without it. |
| 4 | High | Web build | Two unused-variable compile errors (`BillingPage`, `BranchGstinsPanel`) broke `tsc -b`. | Removed. |
| 5 | Med | `accounting/tasks.py`, `views.py` | Back-fill job: an exception left the status "running" for an hour; a double click could start two runs; no way to read status; a finished run blocked the next one if a naive lock were used. | Atomic run lock that only treats `running` as a lock; failure recorded; `GET /accounting/backfill/` status; banner polls. |
| 6 | Med | `AccountingBackfillBanner.tsx` | Treated the 202 "running" body as a preview and printed "does not tie". | Handles running / done / failed and refreshes settings. |
| 7 | Med | `accounting/services.py` | `gl_basis_ready` (three ledger aggregates) ran on every list/dashboard request. Fixed ₹1 inventory tolerance could hold a busy company on the warning for ever. | 30 s shared cache (off in tests, bypassed for the hypothetical "can I enable books" check); tolerance = ₹1 or 0.1% of stock value, capped at ₹100. |
| 8 | Med | `india.py` | Apparel slab tested the pre-discount price. Stale HSN notice text stayed in `rate_override_reason`. | Test the price after line discount; always rewrite the informational notice. |
| 9 | Med | `masters/serializers.py` | `gst_supply_form` accepted any string; `gst_rate_notice` was emitted outside the schema, so it was missing from OpenAPI and the contract test failed. | Choice validation; declared field. |
| 10 | Med | `NewInvoicePage`, `NewPurchasePage` | Barcode auto-add fired on every keystroke against stale results: typing "ABC-1" added the product whose SKU is "ABC". | Only act when the results belong to the text now in the box. |
| 11 | Med | `PosPage.tsx` | Split cash and held split survived to the next customer's bill. | Reset in `clearCart`. |
| 12 | Med | `GstReturnPage.tsx` | Register-tie alert showed green when the key was simply missing. | Green only on an explicit `true`. |
| 13 | Low | `CollectionsWorklistPage.tsx` | UTC "today" (wrong for IST mornings); a promise due today shown as overdue; "Copy link" reported success with nothing copied; empty state said "No open invoices" under a full table. | Local date; overdue only when past; disabled without a link; copy fixed. |
| 14 | Low | `collections_open.py` | Phones like `098765 43210` produced a wrong wa.me number. | Normalise 0-prefixed, +91 and bare 10-digit numbers. |
| 15 | Low | `Customer360Page.tsx` | Default promise date from UTC. | Local date. |
| 16 | Low | `core/exceptions.py` | Structured confirm errors flattened to "code: X; message: …; confirm_codes: …". | Use the payload's own sentence. |
| 17 | Low | `core/migrations` | `Notification.channel` gained `IN_APP` with no migration (`makemigrations --check` failed). | `0042_notification_channel_in_app`. |
| 18 | Low | `nic_irp_crypto.py` | `ruff` S305 on two lines would fail CI. | `noqa` with the reason (NIC publishes AES-ECB). |
| 19 | Low | `docs/openapi-snapshot.json`, `openapi-types.ts` | Seven new paths missing from the snapshot. | Regenerated. |
| 20 | Test | `test_tax_engine_registry`, `test_holistic_trial`, `PosPage.creditLimitBanner`, `GstHonestyHeader` | Stale assertions: pinned preview keys, an order-dependent plan lookup, an ambiguous `/cash/` query, the old "not GSTN filing" sentence. | Updated to the decided behaviour. |

New regression tests: `backend/tests/test_audit_review_fixes.py` (split tender ×3, receipt
rollback, discount slab, stale notice, single-rate notice, supply-form validation, error
envelope, back-fill status / re-run / failure, WhatsApp digits).

## Left as is, on purpose

- `preview` says "would post 27" and the run posts 26: the dry run counts an item that
  `PostingService` then skips. Cosmetic.
- Some money strings still carry float noise (`5317.800000000000`) from the ledger and risk
  snapshot. The UI formats them; the API contract claim (no floats) is not fully met.
- `open_invoice_rows` returns every open invoice unpaginated; fine for the pilot, revisit for
  a wholesaler with thousands.
- Back-fill refuses when **any** period is closed, even one that no unposted document falls
  in. Conservative.
- GST Guard (blocking buyer-GSTIN / HSN-window checks on completion, on for trial companies)
  was not part of this plan and was skimmed only.
