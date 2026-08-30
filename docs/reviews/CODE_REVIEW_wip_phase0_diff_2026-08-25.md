# Code Review — `wip/phase0` working-tree diff (2026-08-25)

**Scope:** Uncommitted working-tree changes (`git diff HEAD`, `main` and `HEAD` are the
same commit) — 279 modified files + ~15 new backend/frontend files. Theme: item
godown + expiry tracking, product wholesale price, employee TDS, purchase-return
condition, debit-note source-item lineage, password-reset flow, HSN catalog, bill
image pipeline.

**Method:** 8 parallel finder passes (line-by-line diff scan, removed-behavior audit,
cross-file tracer, reuse, simplification, efficiency, altitude, and
API-contract/performance/test-coverage angles), each producing candidates
independently. The most severe/likely candidates were then independently
re-verified by a separate pass with **CONFIRMED / PLAUSIBLE / REFUTED** verdicts.
Findings below are grouped by verification status; within each group, most severe
first. `file:line` refers to the current working-tree content unless noted.

Only defects with a nameable failure scenario are listed. Findings that a verifier
already refuted are omitted. Style-only nits are omitted.

---

## A. Confirmed — financial / GST correctness

### A1. Purchase stock cost layers valued ~10x too high on alternate-unit buys
**File:** `backend/purchases/services.py:568-582` (`PurchaseService.complete`)
**Verdict:** CONFIRMED

Purchase completion converts line quantity to base units for stock posting
(`qty = base_quantity(item.product, item.quantity, unit_name)`) but still passes
`unit_cost=item.unit_price`, which is priced per the *original purchase unit*
(e.g. per box), not per base unit (e.g. per piece).

**Failure scenario:** Product has base unit PCS, alternate unit BOX with
`conversion_rate=10`. Purchasing 1 BOX at `unit_price=100` converts quantity to
10 (PCS) but posts the FIFO/valuation cost layer with `unit_cost=100` — the layer
values 10 pieces at ₹1,000 instead of the correct ₹100 (₹10/piece). Both FIFO and
weighted-average valuation are affected, inflating inventory value and downstream
COGS by the conversion factor on every alt-unit purchase.

### A2. Alt-unit line switch on invoices doesn't rescale price — undercharges customers
**File:** `web/src/components/billing/DraftLineTable.tsx:168`
**Verdict:** CONFIRMED

Switching a sales/purchase draft line to a product's alternate unit only patches
`unitName`; `unitPrice` is never rescaled by `conversionRate` (the `DraftLine` type
doesn't even carry a `conversionRate` field). The backend mirrors this: `unit_price`
is accepted at face value and `compute_document_totals`
(`backend/core/services/billing.py:364,370`) computes `quantity × unit_price`
directly, while only `base_quantity()` (`backend/inventory/item_stock.py:74-92`)
applies the conversion, and only for stock deduction.

**Failure scenario:** Product "Widget", PCS price ₹10, alternate unit BOX
(`conversion_rate=10`). User switches a line to BOX, enters quantity=2 (2 boxes).
`unitPrice` stays 10 → invoice bills `2 × 10 = ₹20`, while `base_quantity()`
correctly removes 20 physical PCS from stock. Customer is billed ₹20 for ₹200 of
goods — a 10x revenue undercharge with no validation catching the mismatch.

### A3. Cancelling a purchase return never restores DAMAGED-condition write-offs
**File:** `backend/purchases/services.py:835-850` (write) and `:990-997` (cancel query)
**Verdict:** CONFIRMED

The new DAMAGED-condition path posts write-offs as `movement_type=ADJUSTMENT`
but reuses `reference_type="purchase_return"`. `cancel_return` only queries
`movement_type=PURCHASE_RETURN` to find what to reverse, so it never matches the
ADJUSTMENT rows.

**Failure scenario:** A purchase return with mixed sellable + DAMAGED lines is
completed then cancelled: the sellable `PURCHASE_RETURN` movements are reversed,
but the DAMAGED write-off stays applied — stock is permanently short by the
damaged quantity after cancellation. The equivalent sales-side flow
(`backend/sales/return_service.py`) correctly uses a distinct `reference_type`
and a dedicated reversal branch; purchases lacks this.

### A4. Returns of alternate-unit sales/purchases restore the wrong (smaller) stock quantity
**File:** `backend/sales/cogs_service.py:112-202` (`restore_return_stock_and_cogs`);
equivalent gap in `backend/purchases/services.py:743-887` (`complete_return`)
**Verdict:** CONFIRMED

`base_quantity()` conversion is wired into sale/purchase *completion* only.
`SalesReturnItem`/`PurchaseReturnItem` have no `unit_name` field at all, and the
restore functions use the raw stated return quantity directly against
already-base-unit-converted FIFO lots.

**Failure scenario:** A sale of 2 BOX (`conversion_rate=10`) reduces stock by 20
PCS at completion. Returning "1" (user intends 1 box = 10 PCS) passes validation
(which compares raw quantities), but `restore_return_stock_and_cogs` treats
`remaining=1` directly against the base-unit lot (`lot_qty=20`), restoring only 1
PCS instead of 10 — a silent 9-unit stock-restoration shortfall with no error.
Same gap on the purchase-return side.

### A5. `PostingService.reverse()` no longer flips journal-entry status (impact mitigated)
**File:** `backend/accounting/services.py:892-895`
**Verdict:** PLAUSIBLE (regression confirmed; catastrophic consequence refuted)

The diff removes `entry.status = JournalEntry.Status.REVERSED` from the save
call. The method's own double-reversal guard
(`entry.status != POSTED or hasattr(entry, "reversal_of")`) relies on that status
flip — `reversal_of` only detects "this entry is itself a reversal," not "this
entry was already reversed," so the guard no longer blocks a second call.
However, `PostingService.post()` is independently idempotent (looks up an
existing POSTED entry by `(company, source_type, source_id, purpose)` and returns
it unchanged) and there's a DB-level partial unique constraint
(`uniq_accounting_source_posting`) — so a second `reverse()` call resolves to the
same reversal entry rather than posting a duplicate one. The **real**, confirmed
impact: `entry.status` never becomes `REVERSED`, which breaks
`backend/tests/test_sprint4_erp_rls.py::test_cancel_pay_run_reverses_journal_and_reopens_draft`
(asserts `entry.status == REVERSED`) and any other code that branches on that
status.

**Failure scenario:** Any caller (pay-run cancellation, invoice amend, return
cancel) that checks `entry.status == REVERSED` to decide whether an entry was
already reversed will misbehave; the new test in this same diff fails as written.

### A6. Manufacturing work-order completion silently skips the accounting entry when issue cost is zero
**File:** `backend/manufacturing/services.py:181-187` (`complete_work_order`)
**Verdict:** CONFIRMED

Guard changed from always posting (falling back to a computed valuation when
`issue_cost` was 0) to `if wo.company.accounting_enabled and issue_cost > 0:`,
passing `issue_cost` directly with no fallback. `issue_cost` can genuinely be 0
(e.g. components with no recorded cost basis / opening stock with
`unit_cost=None`), and the finished-good stock movement is still posted
unconditionally, with its own independently-computed non-zero `unit_cost`.

**Failure scenario:** Components with zero cost basis make `issue_cost == 0`; the
GL entry moving value from WIP to Finished Goods is skipped, but the stock
valuation report still shows a non-zero FG value computed from
`component.purchase_price` — books and stock valuation permanently diverge with
no error or log.

### A7. Purchase invoice edit path uses inconsistent unit basis vs. completion
**File:** `backend/purchases/services.py:276` (unverified independently, but consistent with A1)
**Verdict:** PLAUSIBLE (flagged by finder, not run through a dedicated verifier)

The `adjust_stock=True` edit path computes/posts stock deltas from raw
`item.quantity` (purchase-unit terms), while initial completion (see A1) converts
to base units first — the same product's stock ledger could end up mixing two
different unit bases depending on which code path touched it.

---

## B. Confirmed — multi-tenancy / data isolation

### B1. New tenant tables ship with no RLS enrollment
**File:** `backend/inventory/migrations/0009_item_godown_expiry.py:19`
**Verdict:** CONFIRMED

`WarehouseReorderLevel`, `StockCountSession`, and `ExpiryAlertLog` are new
`CompanyScopedModel` tables (all with a `company` FK), but no companion `core`
migration adds them to the RLS enrollment list — unlike every prior tenant table
addition (e.g. `RecurringInvoiceSchedule`/`RecurringInvoiceRun` were enrolled via
`backend/core/migrations/0012_sprint_c_rls_recurring.py` in the same commit that
added them).

**Failure scenario:** If `POSTGRES_RLS_ENABLED=1` in production and any
app-level company filter is missed or bypassed (admin query, bulk script, future
serializer bug), there is no DB-level backstop preventing cross-tenant
reads/writes on stock-count sessions, reorder levels, or expiry alert logs.

### B2. Stock-count lines: unscoped product/batch FK + client-writable `system_qty`
**File:** `backend/inventory/serializers.py:217-222` (FK scoping), `:221` (`system_qty`)
**Verdict:** CONFIRMED (both sub-claims)

`StockCountLineSerializer`'s `product`/`batch` fields use DRF's default unscoped
`PrimaryKeyRelatedField` querysets; neither `StockCountSessionSerializer.create()`
nor `.update()` validates them against the session's company (unlike
sales/purchases line flows and even `StockTransferSerializer` in the same file,
which does check `product.company_id`/`batch.company_id`).
`InventoryService.post_movement` checks warehouse/batch company ownership but
never checks `product.company_id`. Separately, `system_qty` has no
`read_only=True`, so it's client-writable; `StockCountSessionViewSet.post`
computes `variance = counted_qty - system_qty` directly from the stored row with
no re-derivation from live `StockBalance`.

**Failure scenario:** A user submits an arbitrary `system_qty`, letting them
fabricate the magnitude of a posted inventory `ADJUSTMENT` untethered from real
on-hand stock. Separately — if `POSTGRES_RLS_ENABLED` is off (defaults to `"0"`
per `backend/config/settings.py`) or RLS is otherwise bypassed — a cross-tenant
product/batch ID would be accepted and posted against, since no app-level check
exists. (Postgres RLS on `masters_product`, when enabled, is an independent
mitigating control the sales/purchases code doesn't rely on but this new
serializer does.)

### B3. `StockCountLine` has no `company` column at all
**File:** `backend/inventory/models.py:251`
**Verdict:** PLAUSIBLE (architectural gap, not independently re-verified)

Breaks the codebase's own defense-in-depth convention
(`DocumentLineModel` denormalizes `company` onto every line row) — `StockCountLine`
can never be enrolled in RLS even after B1 is fixed, since it has no `company` FK
to filter on.

### B4. `WarehouseReorderLevelSerializer` — same unscoped-FK class of issue
**File:** `backend/inventory/serializers.py:200`
**Verdict:** PLAUSIBLE (same pattern as B2, not independently re-verified)

`warehouse`/`product` fields use default unscoped querysets with no company
validation on create/update.

---

## C. Confirmed — concurrency, idempotency, billing gate

### C1. Company-context conflict crashes with 500 instead of the intended 409
**File:** `backend/billing/middleware.py:42-47` (`SubscriptionWriteGateMiddleware`)
**Verdict:** CONFIRMED

```python
try:
    cu = get_company_user(request)
except APIException:
    raise
except Exception:
    return self.get_response(request)
```
`get_company_user()` raises `CompanyContextConflict` (409) or DRF
`PermissionDenied` (403), both `rest_framework.exceptions.APIException`
subclasses. This middleware is plain Django WSGI middleware (last in
`MIDDLEWARE`, runs before any DRF view dispatch) with no wrapping exception
handler — Django core has no special-case for `APIException`, so it renders a
generic unhandled 500 instead of the intended 403/409 JSON body.

**Failure scenario:** Any authenticated write request with a stale/mismatched
`X-Company-Id` header (e.g. two browser tabs with different active companies)
now gets a raw 500 instead of a clean 409, on every occurrence of a previously
common condition. No test exercises this path.

### C2. Idempotency stale-record cleanup races — one retry gets an unhandled 500
**File:** `backend/core/idempotency.py:94-107` (`begin_record`)
**Verdict:** CONFIRMED

New stale-in-flight-record cleanup fetches the existing record under
`select_for_update()` inside `transaction.atomic()`, but the lock is released
before the age check / delete / recreate, which happen as separate, unlocked
statements. The recreate (`IdempotencyRecord.objects.create(...)`) is not
wrapped in `try/except IntegrityError`.

**Failure scenario:** Two retried requests with the same Idempotency-Key both
fetch the same >15-minute-stale in-flight record, both pass the age check, both
delete it, and both attempt to recreate it. The loser's create violates the
unique constraint on `(company, scope, key)` with nothing catching it —
that request gets an unhandled `IntegrityError` (500) instead of the previously
clean `IdempotencyInFlightError` (409). No test exercises the `age > 15min`
branch.

### C3. Bill-import idempotency replay reruns LLM extraction instead of returning the cached response
**File:** `backend/imports/views.py:101-115`
**Verdict:** CONFIRMED

For `ImportJob.BILL_KINDS`, when `begin_record` signals "already completed"
(returns a cached `Response`), the code calls `forget_record` then `begin_record`
again instead of replaying the cached response — deliberately, per an inline
comment, but it defeats the Idempotency-Key contract.

**Failure scenario:** A client's POST to create a bill-import job succeeds
(`ImportJob` created, LLM extraction started, response lost to a network blip).
The client retries with the same Idempotency-Key; the server deletes the prior
completion marker and creates a second `ImportJob`, rerunning LLM/OCR extraction
— risking duplicate `PurchaseInvoice`/`SalesInvoice` rows from one physical bill.

### C4. Pre-existing unlocked check-then-act on notification status (not newly introduced)
**File:** `backend/core/tasks.py:11-18` (`send_email_notification`); same pattern in
`backend/sales/tasks.py:162` (`submit_einvoice_async`'s `if invoice.irn: return`)
**Verdict:** PLAUSIBLE (pre-existing, only incidentally touched by this diff —
gained an unused-looking `company_id` kwarg)

No `select_for_update()`/`transaction.atomic()` around the read-then-write of
`notification.status`. Celery's at-least-once delivery could let two workers
both pass the `SENT` check before either writes it.

**Failure scenario:** Task delivered twice in a tight window (broker
redelivery) — both workers double-send the same notification email.

---

## D. Confirmed — security

### D1. Password-reset tokens are replayable within their lifetime; request endpoint has no rate limit
**File:** `backend/accounts/views.py:1031` (throttle), `:1060` (token validation)
**Verdict:** CONFIRMED (both sub-claims)

The reset token is `signing.dumps({"uid": user.pk}, salt=...)` with only a
`max_age` check on confirm — no single-use tracking (no DB record analogous to
the invite flow's `InviteJti` with `is_consumed`), and nothing in the payload
changes after a successful reset, so the same token validates again.
Separately, `RequestPasswordResetView`/`ConfirmPasswordResetView` are the only
sensitive `AllowAny` endpoints in the file with no `throttle_scope` — they fall
back to the generic `120/min` anon rate, unlike `register` (5/min), `login`
(10/min), `otp` (5/min).

**Failure scenario:** A leaked reset link (email forwarding, shared inbox,
browser history) can be replayed repeatedly to reset the password to
attacker-chosen values throughout the full 1-hour token lifetime, even after the
legitimate user already used it once. Separately, an attacker can mail-bomb an
arbitrary victim's inbox with reset emails at up to 120/min.

### D2. `METRICS_TOKEN` accepted via query string, compared non-constant-time
**File:** `backend/core/views.py:303`
**Verdict:** PLAUSIBLE (flagged by finder, not independently re-verified)

Accepts the metrics secret via `?token=` (proxy/log/browser-history leakage
risk) in addition to the `Authorization` header, and compares with `!=` instead
of `hmac.compare_digest` or similar constant-time comparison.

**Failure scenario:** Timing side-channel could in principle help brute-force
the token; more practically, the token leaks into access logs/proxies/browser
history via the query-string path.

---

## E. Confirmed — functional regression (non-financial)

### E1. Low-stock / reorder alerts suppressed for any product with the default (zero) reorder level
**File:** `backend/inventory/views.py` (`StockBalanceViewSet.get_queryset` ~59-67,
`LowStockAlertsView.get` ~192-206)
**Verdict:** CONFIRMED

Filter changed from `_available__lte=F("product__reorder_level")` to requiring
`_reorder__gt=0 AND _available__lte=F("_reorder")`. `Product.reorder_level`
defaults to `Decimal("0")`, so any product without an explicit reorder level
(the common case, especially for bulk-imported products) is now excluded
regardless of how negative/zero its available stock is.

**Failure scenario:** A newly imported product (reorder level never set) sells
down to zero or negative — it no longer appears in "low stock" or reorder-alert
views at all, even though it is genuinely out of stock.

---

## F. Plausible / unverified — flagged by a single finder pass, not run through independent verification

These were surfaced with a concrete failure scenario but not re-checked by a
dedicated verifier agent; treat as leads to confirm before acting.

### F1. API contract / frontend integration
- **`web/src/pages/sales/NewInvoicePage.tsx:392`** (and `NewPurchasePage.tsx`
  equivalent) — rebuilding draft lines when editing an existing invoice never
  repopulates `baseUnitName`/`alternateUnitName`, so the alternate-unit picker
  silently disappears in edit mode even though it works when first creating the
  line.
- **`backend/purchases/phase1_serializers.py:30`** — the new `source_item`
  lineage field on Purchase Credit/Debit Note items is never sent by
  `PurchaseNoteEditorPage.tsx`, unlike the sales-side equivalent which does send
  it — an asymmetric, half-wired feature.

### F2. Performance
- **`backend/inventory/views.py:311-318` + `backend/inventory/item_stock.py:282-319`**
  (`ExpiryAlertsView.get` → `record_expiry_bands`) — every GET to the Expiry
  Alerts page now does one `get_or_create` per near-expiry lot×godown row, plus
  a `Notification.create`/`send`/`refresh_from_db` the first time a band is
  crossed — new N+1 + side effects inside a request path. A tenant with 300
  batch/godown combinations near expiry triggers ~300 extra queries per page
  load.
- **`backend/purchases/services.py:267-268`** (`set_items` /
  `_update_purchase_items_in_place`) — editing a COMPLETED purchase invoice with
  `adjust_stock=True` now does per-row `.save()` instead of the
  `bulk_create`/delete-and-recreate pattern used everywhere else — a 30-80x
  query-count increase for correcting a posted bill with 30-80 lines (typical
  for the new LLM bill-extraction flow).
- **`backend/inventory/views.py:394`** (`StockCountSessionViewSet.post`) — one
  `InventoryService.post_movement` call per counted line, each doing its own
  `select_for_update`/balance fetch — ~2,000-3,000 queries (with sequential row
  locks) to post a 500-SKU stock count.
- **`backend/core/services/llm.py:564-566` + `backend/core/services/bill_images.py`**
  (`extract_purchase_bill`) — the chunked-extraction loop (up to
  `MAX_EXTRACT_CHUNKS`=4 iterations) recomputes `split_bill_image`/
  `enhance_bill_image` (full JPEG decode, autocontrast, LANCZOS upscale, crop,
  re-encode) from scratch on every chunk instead of reusing cached crops — up to
  12x redundant Pillow work per multi-page bill import (runs in a Celery task,
  so non-blocking, but materially inflates worker CPU/memory per bill).

### F3. Reuse / simplification / altitude / test coverage
- **`backend/payroll/services.py:88`** — the new `Employee.tds_rate`/
  `PaySlip.tds_amount` deduction (posted to ledger account "2265") has zero test
  that exercises a non-zero `tds_rate`.
- **`backend/purchases/models.py:307`** — the new `PurchaseDebitNoteItem.source_item`
  FK has no test, unlike the equivalent sales-side field which has an explicit
  cross-tenant-rejection test.
- **`web/src/pages/inventory/ItemFormDialog.tsx:42`** — local `GST_RATES` list
  duplicates and diverges from `web/src/utils/gst.ts`'s `ALLOWED_GST_RATES`,
  omitting the 40% slab both the frontend helper and backend validator already
  allow — items needing that rate can't be created via this dialog.
- **`web/src/pages/settings/ItemSettingsPage.tsx:22`** — `DEFAULT_DEFS`
  duplicates `ItemFormDialog.tsx`'s `DEFAULT_CUSTOM_DEFS` (identical content,
  already-diverged names) instead of sharing one constant.

---

## Summary table

| # | Area | File | Verdict | Severity |
|---|------|------|---------|----------|
| A1 | Financial | purchases/services.py:570 | CONFIRMED | Blocker |
| A2 | Financial | web DraftLineTable.tsx:168 | CONFIRMED | Blocker |
| B1 | Tenancy | inventory/migrations/0009...:19 | CONFIRMED | Blocker |
| A3 | Financial | purchases/services.py:990 | CONFIRMED | High |
| A4 | Financial | sales/cogs_service.py:134 | CONFIRMED | High |
| C1 | Availability | billing/middleware.py:44 | CONFIRMED | High |
| C2 | Concurrency | core/idempotency.py:98 | CONFIRMED | High |
| C3 | Idempotency | imports/views.py:106 | CONFIRMED | High |
| B2 | Tenancy/Fraud | inventory/serializers.py:217 | CONFIRMED | High |
| D1 | Security | accounts/views.py:1060 | CONFIRMED | Medium-High |
| A6 | Financial | manufacturing/services.py:181 | CONFIRMED | Medium |
| E1 | Functional | inventory/views.py (low-stock filter) | CONFIRMED | Medium |
| A5 | Financial | accounting/services.py:892 | PLAUSIBLE | Medium (impact mitigated) |
| A7 | Financial | purchases/services.py:276 | PLAUSIBLE | Medium |
| B3 | Tenancy | inventory/models.py:251 | PLAUSIBLE | Medium |
| B4 | Tenancy | inventory/serializers.py:200 | PLAUSIBLE | Medium |
| C4 | Concurrency | core/tasks.py:11 (pre-existing) | PLAUSIBLE | Low-Medium |
| D2 | Security | core/views.py:303 | PLAUSIBLE | Low-Medium |
| F1.1 | Frontend | NewInvoicePage.tsx:392 | Unverified | Low-Medium |
| F1.2 | Frontend | purchases/phase1_serializers.py:30 | Unverified | Low |
| F2.1 | Performance | inventory/views.py:311 | Unverified | Medium |
| F2.2 | Performance | purchases/services.py:267 | Unverified | Medium |
| F2.3 | Performance | inventory/views.py:394 | Unverified | Medium |
| F2.4 | Performance | core/services/llm.py:564 | Unverified | Low |
| F3.1 | Test coverage | payroll/services.py:88 | Unverified | Low |
| F3.2 | Test coverage | purchases/models.py:307 | Unverified | Low |
| F3.3 | Reuse | ItemFormDialog.tsx:42 | Unverified | Low |
| F3.4 | Simplification | ItemSettingsPage.tsx:22 | Unverified | Low |
