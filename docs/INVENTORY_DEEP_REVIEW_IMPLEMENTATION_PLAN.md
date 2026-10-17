# Inventory deep review — implementation plan

Date: 2026-10-16. Source: `docs/reviews/INVENTORY_DEEP_SCREEN_REVIEW_2026-10-16.md` (findings F-01 … F-30).
Scope: the 12 Inventory screens and the backend they use. Builds on `INVENTORY_REVIEW_IMPLEMENTATION_PLAN.md` (WP-00..21, already in the working tree, uncommitted).

## 1. Goals and ground rules

1. Remove every way a user can get **stuck** (F-01) or **duplicate** a stock document (F-10, F-12, F-16).
2. Make every stock-reducing action obey **one set of controls** (approval, period lock, idempotency, reason, audit, journal) — F-03, F-04.
3. Make **counts** trustworthy on a busy godown (F-05…F-09).
4. Close the **serial return** hole (F-02) before anyone relies on it.
5. Then fix correctness of planning/forecast numbers, then UX and polish.

Ground rules (apply to every work package, "WP"):
- Server enforces; UI only helps. Anything a rule needs goes in the service, not the page.
- No new migration unless the WP says so. Every migration needs `--create-db` (~9 min) for the test DB.
- Each WP ships with tests (pytest for backend, vitest for web) and a note in the section 8 record at the end of this file.
- Use the private pytest settings recipe from the earlier inventory work (own TEST DB name, `--reuse-db`, `--runxfail` to catch hidden setup errors).
- Web checks before merge: `tsc -b`, eslint (0 errors, CI-gated), vitest for touched pages.
- OpenAPI: any serializer/endpoint change → `manage.py spectacular` then `npm run gen:api-types` (CI drift check).
- Feature flags for anything that changes money or approvals (see section 6).
- Do not read the generated files listed in `CLAUDE.md`; grep them.

## 2. Work packages at a glance

| WP | Title | Findings | Wave | Effort (ideal days) | Migration | Flag |
|---|---|---|---|---|---|---|
| IDR-01 | Retry-safe idempotency on all stock writes | F-01, F-12 | 1 | 2.5 | no | no |
| IDR-02 | One stock-loss service (approval, period, reason, journal, audit) | F-03, F-04 | 1 | 4 | maybe (count line) | `STOCK_LOSS_APPROVAL_ALL_PATHS` |
| IDR-03 | Serial return through the sales-return flow | F-02, F-25 | 1 | 3 | no | no |
| IDR-04 | Count correctness: drift, multi-counter, lots, negatives | F-05, F-06, F-08, F-09 | 2 | 6 | yes (0030) | no |
| IDR-05 | Count feedback, auto-save, offline pending state | F-07 | 2 | 2 | no | no |
| IDR-06 | Expiry write-off: idempotent, safe batches, input validation, links | F-10, F-11 | 2 | 2.5 | no | no |
| IDR-07 | Transfers: shortage clarity, in-transit view, notes, list filter | F-12 (UI), F-13 | 2 | 3 | no | no |
| IDR-08 | Planning/forecast numbers: one velocity, donor cap, open POs | F-14, F-15, F-16, F-17 | 3 | 4 | no | no |
| IDR-09 | Products: filter-aware export, filters on server, price checks, refresh, messages | F-18…F-21 | 3 | 4 | no | no |
| IDR-10 | Stock list performance and print/export | F-22, F-23 | 3 | 3.5 | no | no |
| IDR-11 | Labels: ZPL parity, sticker sheets, add-without-barcode | F-24 | 4 | 3 | no | no |
| IDR-12 | Roles and cost visibility pass | F-26 | 4 | 2.5 | no | no |
| IDR-13 | Polish: i18n, chips, menu flags, docs | F-27…F-30 | 4 | 2 | no | no |
| IDR-14 | Hardening: Postgres concurrency, role matrix, browser pass | all | 5 | 4 | no | no |

Total ≈ 46 ideal days for one engineer; Wave 1 (≈ 9.5 days) is the part that must land before the module is relied on for money.

Dependencies: IDR-02 before IDR-06 and IDR-03 (they call the shared service). IDR-01 independent. IDR-04 after IDR-02 (count post uses the service). IDR-10 before IDR-09's server-side filters (shared paging API). IDR-12 after IDR-02.

---

## 3. Wave 1 — Stop the damage

### IDR-01 Retry-safe idempotency on all stock writes (F-01, F-12)

**Problem.** `wrap_idempotent` stores deterministic 4xx answers under the key (`core/idempotency.py`). Adjustment keeps one key until success; transfer dispatch/receive and count post use fixed per-document keys. After a rejection the user can neither retry the same data (old error replayed) nor change it (422 key reused).

**Design.**
- Rule: *a key identifies one attempt of one body.* The client mints a new key on every user gesture, and re-sends the **same** key only for an automatic network retry of the same request (the existing `userGestureIdempotencyKey()` in `web/src/api/client.ts` is the pattern; reuse it).
- For documents that must stay exactly-once at the document level (dispatch, receive, count post) the *document's own status* is the guard (it already is: row lock + status check in `StockTransferService.dispatch/receive` and count `post`), so the idempotency key may change between attempts without risking a double post.
- Offline queue keeps its stable key per queued item (`stock-transfer-{id}`, `stock-count-{id}`), because the replay of the *same* request is exactly what is wanted there. Only the online click path changes.
- Server side: add the deterministic stock errors that are fixable by the user to the transient list so they are released, not stored: negative-stock block, insufficient available, lot not found for godown. Add a stable `code` to those `BusinessRuleError`s first (check which codes `check_negative_stock`, `dispatch`, `receive` raise today — **verify**).

**Changes.**
- `web/src/pages/inventory/StockAdjustmentPage.tsx`: mint a new key per submit (`idempotencyKey.current = newIdempotencyKey()` in `onError` as well as `onSuccess`); keep the existing stable key only across automatic retries inside `createStockAdjustment`.
- `StockTransferPage.tsx`: dispatch/receive online path uses a per-click key; queued path keeps `stock-transfer-{id}`. `create` gets a per-submit key (F-12) and `createTransfer` accepts `{ idempotencyKey }`.
- `StockCountPage.tsx`: post online path per-click key; queued path unchanged.
- `web/src/api/legacy/inventory.ts` / `resources.ts`: `createTransfer(payload, options)`.
- Backend: `inventory/views.py` `StockTransferViewSet.create` wrap in `wrap_idempotent(scope="stock_transfer_create")`; add the error codes above to `TRANSIENT_4XX_CODES` in `core/idempotency.py` (or raise them with `code=` values already in the set, preferred).
- `core/exceptions.py`: stock errors carry `code` (e.g. `insufficient_stock`, `negative_stock_blocked`, `lot_unavailable`).

**Tests.**
- pytest: post adjustment that BLOCKs on negative stock → 400 with code → add stock → same key, same body → succeeds (released, not replayed). Same key, changed body → 422 still (guard kept) — and assert the UI never sends this combination.
- pytest: dispatch rejected for stock → restock → dispatch succeeds with a new key; dispatch twice with different keys → second returns "already dispatched" (status guard), stock moves once.
- pytest: transfer create twice with the same key → one draft; with different keys → two (expected).
- vitest: adjustment page — reject then submit again sends a different `Idempotency-Key`; success path still resets.
- vitest: offline queue still uses the stable key.

**Acceptance.** No inventory screen can reach a state where a corrected retry is refused because of an earlier rejection. Documented in section 8.

**Risk.** MEDIUM — touches all stock writes. Mitigation: status guards already exist; add a regression test per endpoint that two different keys cannot double-post.

### IDR-02 One stock-loss service (F-03, F-04)

**Problem.** The second-approver rule, period gate, reason code, journal and audit are implemented separately (and unevenly) in Adjustment, Expiry write-off, Count post and Serial scrap. Count recheck is a client checkbox.

**Design.** New module `inventory/stock_loss.py`:
```
post_stock_loss(company, user, *, product, warehouse, batch, quantity (signed),
                reason, reason_code, reference_type, reference_id, movement_date,
                approval_id=None, skip_negative_check=False, source)
-> StockLossResult(status="APPLIED"|"PENDING", movement|approval)
```
Responsibilities: period gate on `movement_date`, approval check (`stock_adjustment_needs_second` with a **valuation-cost** based value, fallback to purchase price), `consume_stock_approval` / `submit_approval` / owner-exception, `post_movement`, `_post_stock_write_journal`, `AuditService.log`, reason code normalisation (add `EXPIRED`, `COUNT_DIFFERENCE`, `SCRAP`, `FOUND` to `ADJUSTMENT_REASON_CODES`).
- Adjustment view becomes a thin caller (behaviour unchanged; this is the reference implementation).
- Expiry write-off: calls the service; PENDING returns 202 like adjustment; UI shows "waiting for approval" per row.
- Serial scrap: same.
- Count post: variances are summed **per session**; the approval rule is evaluated on the session total (value and % of godown value) and on each line over the recheck limit. If approval is needed and the user is not the sole owner → session stays COUNTED with status `PENDING_APPROVAL` (new status value, additive; no data migration) and an approval is created; the approver's accept posts it. Owner-only companies use the existing owner exception.
- Server-enforced recheck: add `rechecked_line_ids` (list) to the post body; post refuses with `recheck_required` if any `needs_recheck` line is missing from it. UI sends the ticked ids. It remains self-attestation by the same user, but it is now a deliberate step recorded in the audit log, and the approval rule above is the real control for large totals.
- Flag `STOCK_LOSS_APPROVAL_ALL_PATHS` (default OFF) gates the *new* approval requirement on the three non-adjustment paths; `recheck_required` ships always. Rollout: enable per company after owner OK.

**Changes.** `inventory/stock_loss.py` (new), `inventory/views.py` (4 call sites), `inventory/serializers.py` (reason codes, count post body), `planwave/services.py` (approval payload carries `source` and session/serial ids, `consume_stock_approval` subject match for each source), `core/services/feature_flags.py` (flag), `web` count/expiry/serial pages (handle 202), approvals inbox label for new sources. Migration only if `StockCountSession.Status` choices need a DB change (choices change is state-only → still generates a migration; keep it `0030_count_pending_approval`).

**Tests.** pytest matrix: for each of {adjustment, expiry write-off, count post, serial scrap} × {below threshold, above value, above %, sole owner, second approver accepts, approver rejects, flag off} → expected APPLIED/PENDING; count post with a missing recheck id → 400 `recheck_required`; approval accepted → movement posted once (idempotent); period locked → transient error, nothing posted; journal posted only when its flag is on. vitest: expiry dialog shows "waiting for approval" per row; count page shows pending state.

**Acceptance.** The only code that calls `post_movement` for a negative ADJUSTMENT from a screen is `post_stock_loss`. Add a grep-based test (`test_no_direct_stock_loss_post`) that fails if `reference_type in {"expiry_write_off","serial_scrap","stock_count","manual_adjustment"}` appears outside the service.

**Risk.** HIGH — money + approvals. Mitigation: flag, dry-run mode that only logs "would need approval" for a week, owner sign-off on thresholds (open item O-2).

### IDR-03 Serial return through the sales-return flow (F-02, F-25)

**Problem.** `SerialNumberViewSet.transition` SOLD→AVAILABLE posts a `SALES_RETURN` movement without a return document.

**Design (recommended).**
1. Remove the "Return to stock" action from `serialActions.ts` for SOLD units; replace it with **"Create sales return"** that opens the existing sales-return/credit-note flow prefilled with the sale document found by `GET /serials/{id}/document/` and the serial number (the document endpoint exists). The return document restores stock, FIFO layers, receivable and GST through the existing, reviewed path.
2. Keep the API transition for admin repair only: require owner role, require a `reason`, require `confirm_no_document=true`, write an audit entry with the reason, and mark the movement `reference_type="serial_manual_return"` so the invariants report can list them. Default: reject for non-owners.
3. Lock + idempotency: `select_for_update` on the serial row inside the transaction; wrap `transition` in `wrap_idempotent(scope="serial_transition")` with a per-click key from the page. Scrap of a RETURNED unit with no on-hand: refuse (`409 stock_desync`) instead of setting SCRAPPED without a movement. Exclude `is_system` godowns from the `warehouse` parameter.
4. Scrap goes through `post_stock_loss` (IDR-02).

**Open question O-1 (owner/CA):** is a manual return without a document ever legitimate (e.g. unit came back before the credit note was raised)? If not, step 2 is removed entirely.

**Tests.** pytest: non-owner transition SOLD→AVAILABLE → 403; owner without confirm → 400; owner with reason → one movement, audit entry; concurrent double request (two threads/Postgres) → one movement; scrap RETURNED at zero on-hand → 409. vitest: SOLD row shows "Create sales return" link with the document path; no direct return button.

**Acceptance.** No ordinary user path adds stock for a sold serial without a return document.

---

## 4. Wave 2 — Counts, expiry, transfers

### IDR-04 Count correctness (F-05, F-06, F-08, F-09)

**Changes (all in `inventory/` + `StockCountPage.tsx`, helpers, serializers).**
- **Per-line drift (F-05).** Replace the global `resolve_conflicts` with `resolutions: {line_id: "KEEP_SERVER"|"KEEP_LOCAL"|"ADJUST_FOR_MOVEMENTS"}` (global value kept as a default for backward compatibility with queued offline requests). Add `ADJUST_FOR_MOVEMENTS`: the line records `counted_at` (timestamp of the save of that line) and the post computes `expected_now = system_qty + net movements since counted_at` then `variance = counted − expected_now` — this removes the sale double-count that `KEEP_LOCAL` causes. This needs `counted_at` on the line (migration 0030, nullable DateTimeField, set when `counted_qty` changes).
  - Movements considered: all except those created by this session; scoped to product, godown, batch, `created_at >= counted_at`.
  - Conflict modal (`StockConflictModal.tsx`) lists each drifted line with the three choices and a "apply to all" shortcut, defaulting to ADJUST_FOR_MOVEMENTS.
- **Multi-counter safety (F-06).** `saveBody()` sends only changed lines (typed or skipped differing from the loaded value) with the loaded `updated_at`/version per line; the server rejects a line whose stored value changed since (409 `line_changed` with the stored value) and the page shows "X was updated by another counter". Add a partial unique constraint: one open (DRAFT/COUNTED) session per godown → `409 count_already_open` with a link to the existing session (constraint on `(company, warehouse)` where status in open states; data check first — **verify** existing duplicate open sessions and close them in the migration).
- **Lot-aware scan (F-08).** `applyScan` returns the candidate lines; when an item has more than one lot line the page opens a small "which lot?" chooser (batch no + expiry) instead of guessing. "Count equals system": keep, but (a) disabled when the session is blind (already), (b) records `filled_from_system=true` per line, (c) the review step shows these lines with a badge and counts them in the audit entry; (d) an owner setting `STOCK_COUNT_ALLOW_FILL_SYSTEM` (default on) so a company can switch it off.
- **Negative and zero lines (F-09).** Session creation includes balances with `on_hand != 0` (negative ones included, flagged "negative — count to correct"). Add "Add all items with a reorder rule or recent sales" optional create mode later (not in this WP). `cancel` takes `select_for_update` and re-checks status inside the lock.

**Tests.** pytest: sale after snapshot with each resolution (expected final on-hand equals the physical count after `ADJUST_FOR_MOVEMENTS`); concurrent line saves (second gets 409); second open session for a godown refused; negative-stock item appears on the sheet; cancel vs post race (Postgres); partial lines + offline queued legacy global resolution still works. vitest: lot chooser, fill-system badge, per-line conflict modal.

**Risk.** HIGH (stock numbers). Migration + constraint → test DB rebuild; run the full inventory suite plus the invariants suite (`balance_equals_movements`) after.

### IDR-05 Count feedback and autosave (F-07)

- Online post success → success `Alert` with "Posted: N lines changed, gain ₹x, loss ₹y" and a link to the Ledger filtered by the session; close dialog after the message is set.
- Autosave: debounce 5 s after the last edit, save only changed lines (reuses IDR-04 line-level save); show "Saved hh:mm" in the dialog; `UnsavedChangesGuard` stays for the debounce window.
- Offline pending state: derive `pendingCount` from the outbox (`listDrafts` filtered by `stock_count`) rather than component state, so it survives reload; show a "Queued" chip on the session row (same approach as transfers).
- Tests: vitest for message, autosave, outbox-derived chip.

### IDR-06 Expiry write-off (F-10, F-11)

- Backend: route through `post_stock_loss` (IDR-02) with `wrap_idempotent` per row; parse `quantity` and `days` with validation errors (`400 {"quantity": "Enter a number"}`) instead of exceptions; date: optional `movement_date` (default today; allow the lot's expiry date up to the open period).
- Frontend: send a per-row key; after a partial failure remove the successful rows from `target` (keep failures); never re-post succeeded rows; show per-row result chips (written off / waiting approval / failed + reason).
- "Return to supplier": pass `product`, `batch`, `warehouse`, `qty` to the purchase-return form (`/purchases/returns?create=1&product=…&batch=…&qty=…`) — add the param reading to the return form page (check `web/src/pages/purchases` for the return editor; extend like the PO editor does for `product`/`qty`).
- Replace the full-page spinner by keeping the controls mounted and showing a table-level loading state (`placeholderData: keepPreviousData`).
- Tests: partial failure retry does not re-post; invalid quantity returns 400; return link carries params; filters stay mounted while loading.

### IDR-07 Transfers (F-12 UI, F-13)

- Success notice after create; draft detail view can edit lines (new `PATCH` on DRAFT only, reuse serializer) — optional stretch.
- **Shortage treatment (F-13, needs O-3).** Decide with the owner/CA: (a) short quantity stays "in transit" as a claim until resolved, (b) written off as loss at receive (via `post_stock_loss`), (c) returned to source. Implement the chosen one; show it in the receive dialog ("Missing 3 units will be written off as ₹x") and in the detail table.
- "Goods in transit" panel on the Transfers page (query dispatched transfers with age, highlight > N days).
- Notes field in the create dialog; status/godown filter and search on the list.
- Tests per chosen option; vitest for panel and filters.

---

## 5. Wave 3 — Numbers and lists

### IDR-08 Planning and forecast numbers (F-14…F-17)

- **One velocity (F-14).** `suggest_replenishment` takes `velocity_per_day` from `forecast.item_velocity` (company) or a new `godown_velocity(company, warehouse_ids, product_ids)` that uses the same net-of-returns, 30-day definition at godown level. Remove the inline 14-day gross query. Update `ReplenishmentSuggestion.velocity_14d` → `velocity_per_day` (keep the old field name as an alias for one release because the API returns it).
- **Donor cap (F-15).** Transfer quantity = `min(shortfall, donor_surplus)`; if the donor cannot cover, split: transfer part, purchase remainder. Exclude `is_system` and inactive godowns from donors (filter `balances_by_product` in `reorder_maps.py`).
- **Open orders (F-16).** Add a shared `open_order_quantities(company, product_ids)` used by planning **and** forecast: DRAFT POs created in the last N days (setting, default 30; older drafts shown as "stale draft" in a warning, not counted) + CONVERTED POs whose purchase invoice is not yet COMPLETED. Add a duplicate guard on `materialize_supplier_drafts`: wrap in `wrap_idempotent(scope="purchase_planning_drafts")` keyed by the page (per gesture) and refuse to create a draft for a product+supplier that already has a DRAFT PO created in the last hour without `confirm_duplicate`. Rename `last_price` → `master_price` in the API/UI or compute the true last purchase price from the latest completed invoice line (preferred; one grouped query like `last_completed_suppliers`).
- **Forecast (F-17).** Filter to `status=ACTIVE, track_inventory=True`; compute demand over **in-stock days** (days where the balance, reconstructed from movements, was > 0; cap the lookback at 90 days; fall back to the flat mean when history is short); expose window and cover days as company settings (`FORECAST_WINDOW_DAYS`, `FORECAST_COVER_DAYS`, `REORDER_COVER_DAYS`); add search and CSV export to the page; add an "overstock / no sales in 90 days" tab (days of cover > 180 or zero sales with stock).
- Tests: pytest comparing forecast `daily_rate`, planning `days_to_stockout` and item-form suggested reorder level for the same product (must agree); donor with small surplus; stale draft; double create; inactive item excluded; out-of-stock-half-window case.

### IDR-09 Products (F-18…F-21)

- **Server-side filters.** `GET /products/` accepts `category`, `brand`, `gst_rate`, `stock_status` (`in|low|out`, using `low_stock_product_ids` and a balance aggregate), `needs_review`. The page stops loading the whole catalogue for filters; remove `allQuery` for filtering (keep a small `GET /products/filter-options/` returning distinct categories, brands, slabs).
- **Export.** `exportCsv` sends the same filter params; server-side CSV endpoint (`/products/export/`) streams rows including stock when requested; honours column prefs and cost-visibility masking.
- **"In stock" semantics.** `in` means available > 0 (includes low items); `low` and `out` remain; UI label "In stock (incl. low)".
- **Delete/deactivate.** Server: `DELETE` on a referenced product returns 200 `{deactivated: true, detail}` and sets INACTIVE (matches the client contract) **or** the client branch is removed — pick one; recommended: server deactivates (one click, no dead code), with audit entry. Open question O-4 if owners want the explicit refusal.
- **Duplicate name.** Replace the page-local check by `GET /products/?name_exact=…` debounce (case-insensitive), warn with link to the existing item. Duplicate SKU/barcode: map the unique-constraint violation to `{"sku": "Item code already used by <name>"}` in `ProductSerializer.validate_sku` (explicit query) so it is a field error.
- **Partial create.** On `onError` after the item was created, invalidate `['products']` and keep `savedNeedsStock` (already); show the item in the list.
- **Price sanity.** Warn (not block) when selling price is 0, selling price > MRP, purchase > selling; block selling price > MRP only for `gst_supply_form=BRANDED_PREPACKED` if the owner agrees (O-5). Require HSN for REGULAR dealers when turnover rule applies (O-6; keep optional until answered).
- **i18n** of the form's English literals (shared with IDR-13).
- Tests: pytest filters, export parity with list, delete → deactivated, duplicate SKU message; vitest: export sends filter params, "In stock" contains low items, partial-create refresh.

### IDR-10 Stock lists: performance, print, export (F-22, F-23)

- `GET /inventory/balances/` gains cursor paging (default 200) and `group_by=product` server aggregation (sum on hand/reserved/available + `lots` count) so the page no longer groups client-side; lots load on expand (`?product=&include=lots`).
- Item form and Adjustment: use `GET /inventory/balances/?product=<id>` (single product) instead of `listStock()`; the item form's reorder hint uses `GET /inventory/demand-forecast/?product=<id>`.
- Current stock Print: render a non-virtualized print view (`@media print` component that fetches all rows for the filter, or a "Print / PDF" server report) — do not call `window.print()` on the virtualized table. CSV export passes `q`, `warehouse`, custom-field filters to `exportReport('inventory', params)`.
- Fix the row key to `${product}-${warehouse}-${batch ?? 'none'}` (and `id` when present).
- Add sort (name, available, value) and a "negative/zero only" filter; keep filters in the URL (`useSearchParams`).
- Tests: pytest paging/aggregation parity with the old client grouping (golden dataset); vitest: print view contains all rows; keys unique; URL state round-trips.

---

## 6. Wave 4 — Labels, roles, polish

### IDR-11 Labels (F-24)
- ZPL generator takes `size`, `include_price`, `batch_id`: emits price (MRP or selling), batch and expiry lines, `^PW`/`^LL` from the chosen size; endpoint `labels.zpl?product=&copies=&size=&batch=`. Multi-row download: `POST /inventory/labels.zpl` with a list of rows (one file).
- Sticker-sheet templates (A4 3×8, 2×7) as CSS print layouts with a size selector; a "calibration test page".
- "Add items without barcode": server endpoint returning items missing barcodes with count and paging; page offers "Generate barcodes for N items" (calls `generateBarcode` in batches, with confirm) instead of silently taking 100.
- Warn per row when the code cannot be encoded as CODE128.
- Tests: ZPL snapshot with price/batch; parity checker comparing browser label text fields with ZPL fields; vitest for warning.

### IDR-12 Roles and cost visibility (F-26)
- Produce the role × endpoint matrix for the 12 screens (VIEWER, SALES, PURCHASE, INVENTORY, ACCOUNTANT, MANAGER, OWNER) × (menu visible, route allowed, API read, API write).
- Fix mismatches found: Low stock "Add rule" hidden unless `canAdjustInventory`; Godowns/Transfers/Counts action buttons hidden for read-only roles; Labels menu vs API gate aligned (decide: view or manage); serial lookup page visibility decision (O-7).
- Cost masking: apply `_can_see_costs` consistently — planning `last_price`/`master_price`, count `variance_value_estimate`, Current stock KPI value, adjustment value banner, forecast. Add a parametrized pytest that asserts no cost-named field is present in these responses for SALES.
- Tests: the matrix itself as a parametrized API test; vitest menu predicates.

### IDR-13 Polish (F-27…F-30)
- Out-of-stock chip text; real tab semantics (`Tabs`/`Tab` or `role=tab` with arrow keys) on Low stock, Forecast, Expiry.
- i18n: replace literals in `ItemFormDialog` validation messages, "Hide lots/Show lots", "All godowns", Serials column heads/status labels (`enumLabel('serialStatus', …)`), count status in dialog title; run the project's i18n key checks; Hindi review is a people task (O-8).
- Planning menu hidden unless both flags; merge Forecast into Planning as a tab (decision O-9, otherwise leave both).
- Update `INVENTORY_REVIEW_IMPLEMENTATION_PLAN.md` section 8 (reason_code exists).

---

## 7. Wave 5 — Hardening (IDR-14)

1. **Postgres concurrency suite** (they are Postgres-only): double dispatch, double receive, count post vs cancel, two counters saving, two serial returns, double expiry write-off, double planning create. Run in CI nightly if not already.
2. **Role matrix run** against a seeded company with one user per role.
3. **Browser pass** with the in-app browser: each of the 12 screens at desktop and 375 px, dark mode, Hindi locale, keyboard-only; capture issues in a short log; fix P1/P2.
4. **Invariants**: run `balance_equals_movements`, `transfer_pairs_net_zero`, `serial_traceability` and the GL-vs-valuation check before and after the test scenarios in all WPs.
5. **Performance**: seed 10k products × 3 godowns; measure Current stock, Products filter, Adjustment, Item form open (target < 1.5 s to first rows, < 300 KB per request).
6. **Backfill dry run** of `backfill_stock_adjustment_journals` on a copy (only after the CA decision O-10).

## 8. Rollout, flags and rollback

| Item | Default | Rollout | Rollback |
|---|---|---|---|
| `STOCK_LOSS_APPROVAL_ALL_PATHS` | OFF | Enable for the owner's own test company first; one week of "would-need-approval" logging; then per company | Flip off; no data change |
| Count `ADJUST_FOR_MOVEMENTS` | on for new sessions | Ship with migration; old sessions keep global resolution | Hide option in UI; server still accepts |
| One-open-session-per-godown constraint | on | Migration closes duplicates (log them) | Drop constraint (reversible migration) |
| Serial manual return (admin) | owner only | Immediate | Remove endpoint option |
| Planning open-order rules | on | Immediate | Setting for stale-draft days |
| `ACCOUNTING_POST_STOCK_ADJUSTMENTS` | OFF | Separate CA-driven decision | Unchanged from today |

Order of merge: IDR-01 → IDR-02 → IDR-03 → IDR-06 → IDR-04/05 → IDR-07 → IDR-10 → IDR-08 → IDR-09 → IDR-11/12/13 → IDR-14. Each WP is its own PR (or commit set); Wave 1 may ship together after IDR-14's concurrency subset passes.

## 9. Definition of done (every WP)

- Code + tests green: backend inventory suite, invariants suite, web `tsc -b`, eslint 0 errors, vitest for touched files.
- OpenAPI snapshot and generated types updated where API changed (CI drift check).
- Audit log entry exists for every new stock-changing path.
- Role behaviour verified for OWNER, MANAGER, INVENTORY, SALES, VIEWER.
- No new English literal outside `t()`.
- Section 10 record updated (what changed, flags, migrations, gaps left).
- Nothing committed or pushed without the owner's request (project convention for this repo's long-running tree).

## 10. Open decisions (need people, not code)

| ID | Question | Owner | Blocks |
|---|---|---|---|
| O-1 | Is a manual SOLD→AVAILABLE return without a return document ever allowed? | Owner/CA | IDR-03 step 2 |
| O-2 | Approval thresholds for write-off, count total, scrap (keep ₹10,000 / 10 %?), and who approves when only the owner exists | Owner | IDR-02 |
| O-3 | Transfer shortage: in-transit claim, write-off, or return to source? Accounting treatment | Owner/CA | IDR-07 |
| O-4 | Delete of a used item: auto-deactivate or explicit refusal? | Owner | IDR-09 |
| O-5 | Block or warn when selling price > MRP for branded pre-packed items? | Owner/CA | IDR-09 |
| O-6 | Make HSN mandatory for regular dealers (turnover rule)? | CA | IDR-09 |
| O-7 | Should sales users see the Serials page, or only lookup at the counter? | Owner | IDR-12 |
| O-8 | Hindi copy review for new strings | Owner/translator | IDR-13 |
| O-9 | Merge Forecast into Planning? | Owner | IDR-13 |
| O-10 | CA sign-off on shrinkage/expiry accounts; turn on GL posting; backfill policy | CA | IDR-14 step 6 |

## 11. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| IDR-01 changes every stock write path | HIGH | Per-endpoint "two keys cannot double post" regression test; status guards already present |
| IDR-02 blocks daily work when approval is required and no approver exists | HIGH | Flag, dry-run logging, owner exception, clear PENDING UX with link to approvals |
| IDR-04 migration + constraint on live data | MEDIUM | Check for duplicate open sessions first; reversible migration; rebuild test DB (~9 min) |
| Server paging changes the shape of the balances API used by other screens (POS, quick entry, route planning) | MEDIUM | Keep the old unpaged response behind `?page_size=all` until all callers are migrated; grep callers of `listStock` |
| Velocity change moves suggested quantities | MEDIUM | Show before/after for a week in logs; communicate in release note |
| Hidden callers of the idempotency scopes (offline outbox replays) | MEDIUM | Keep scope names and stable offline keys; add outbox replay test |

## 12. Suggested session split (if work is parallelised)

Disjoint-file groups that can run in parallel once IDR-01 and IDR-02 are merged:
- A: IDR-04, IDR-05 (count files: `StockCountPage.tsx`, `countHelpers.ts`, count serializers/views, `StockConflictModal.tsx`).
- B: IDR-06, IDR-07 (`ExpiryAlertsPage.tsx`, `StockTransferPage.tsx`, transfer service).
- C: IDR-08 (`planning.py`, `forecast.py`, `services.py` replenishment).
- D: IDR-09, IDR-10 (`ProductsPage.tsx`, `ItemFormDialog.tsx`, masters views, balances API) — D must precede F.
- E: IDR-11 (labels).
- F: IDR-12, IDR-13 after A–E.
Never run two groups on the same file (e.g. `inventory/views.py` is touched by A, B and IDR-03 — merge IDR-03 first or split the views file by class in a preparatory refactor, **IDR-00**, 0.5 day: move count/expiry/serial viewsets into `inventory/views_counts.py`, `views_expiry.py`, `views_serials.py` with no behaviour change).

## 13. Implementation record

(Filled as work packages land: date, files, flags, migrations, tests run, gaps left on purpose.)

### IDR-01 — retry-safe idempotency (built 2026-10-16, uncommitted)

**What changed**
- `web/src/api/client.ts`: `isDefinitiveRejection(error)` — true only for a 4xx the server answered (not 408/429, not an "in progress" 409, not a network error or 5xx). Those keep the key because the first request may have landed.
- `web/src/pages/inventory/attemptKeys.ts` (new, with tests): `AttemptKeys` hands out one key per action until it succeeds or is refused.
- Adjustment page: key renewed after a definitive refusal (it was only renewed on success).
- Transfers page: create, dispatch and receive each use a per-attempt key. Count page: online post uses a per-attempt key. The offline queue keeps its stable keys (`stock-transfer-{id}`, `stock-count-{id}`) on purpose, so a queued replay is the same request.
- `createTransfer` accepts `{ idempotencyKey }`.
- Backend: `StockTransferViewSet` is now an `IdempotentCreateMixin` (scope `stock_transfer_create`, key released on any non-201); `insufficient_stock` added to `TRANSIENT_4XX_CODES` so a refusal for stock is released instead of replayed.

**Tests added**
- `backend/tests/test_inventory_idr01_retry_keys.py` (7): refused adjustment retried with same key after restock; corrected body with same key; success still replayed once; transfer create once per key, separate for different keys, key released after a refusal; dispatch refused for stock then retried after restock.
- `attemptKeys.test.ts` (5); adjustment page (2 new: new key after refusal, same key after lost response); transfer page (1 new: new key for dispatch retry). Three existing assertions that expected the old fixed keys were loosened to `expect.any(String)`.

**Not changed / left on purpose**
- Other deterministic refusals (validation, lot not found) are still stored by the server; the per-attempt client keys cover them. A same-key replay from the offline outbox after such a refusal still replays the refusal.
- Expiry write-off, serial transition and planning drafts get their keys in IDR-06, IDR-03 and IDR-08.
- No Postgres run (the double-dispatch race needs it; planned in IDR-14).
- Note for test runs: a second `OPENING_STOCK` post is refused, so tests restock with an `ADJUSTMENT`.

### IDR-02 — one stock-loss service (built 2026-10-16, uncommitted)

**What changed**
- `backend/inventory/stock_loss.py` (new): `post_stock_loss()` is the one place that applies the closed-period gate, the second-person approval rule, the movement, the optional journal and the audit entry. Used by the manual adjustment, expiry write-off, serial scrap and stock-count posting. `gate_count_post()` holds the count rules; `count_line_needs_recheck()` replaces the copy in the serializer.
- **Approval loop closed (found while reading, not in the original review).** The adjustment screen never sent `approval_id` back, so an approved adjustment could not be applied from the UI. Now: (1) when the owner approves a single-line request (adjustment, expiry write-off) the server applies it for the requester (`planwave/views.py` `_apply_stock_approval`, response carries `applied`); (2) any request can also be spent by the requester repeating the action, because the server looks for the approved request on the same subject.
- Approval value is the dearer of the item purchase price and the valuation cost (it used the purchase price alone, 0 for an unpriced item).
- Server-enforced recheck: a count line over the recheck limit must be named in `rechecked_line_ids` or the post is refused with `recheck_required` (always on). The page sends the ticked lines; the offline queue carries them.
- Flag `STOCK_LOSS_APPROVAL_ALL_PATHS` (default OFF, company JSON true): expiry write-off, serial scrap (losses only) and stock-count posting (losses only, judged per line and as a whole) use the adjustment approval rule. Held requests return 202 `PENDING`; the count stays COUNTED; the serial keeps its status.
- Web: Expiry shows "N sent for approval", Serials shows an info notice, Counts shows a waiting notice and keeps the session in the list. New i18n keys (en, hi): `inventory.expiryPending`, `stockPendingApproval`, `countPendingApproval`.

**Tests**
- `tests/test_inventory_idr02_stock_loss.py` (14): flag off unchanged; held write-off; owner approval applies it once; rejection; small write-off; sole owner; approved adjustment auto-applied; valuation-cost threshold; serial scrap held; recheck refused/accepted; small difference; costly count held then posted once; gain never held; guard that `inventory/views.py` no longer posts these movements directly.
- Two older tests updated to name the rechecked lines (`test_inventory_gl_wp12`, `test_pj_stock_audit_and_adjustments`). Web: count pending, expiry pending, count post payload.
- Regression: 63 backend inventory/approval/persona test files pass; all `src/pages/inventory` web tests, `tsc -b` and eslint clean.

**Left on purpose / still open**
- Owner decision O-2 (thresholds, who approves) still needed before turning the flag on anywhere.
- A queued offline count that was saved before this change has no recheck ids and will be refused with `recheck_required`; the counter opens the count and posts it again.
- An offline-flushed count that comes back `PENDING` is removed from the outbox without a message (needs IDR-05).
- A self-approved request (`owner_may_self_approve`) is still not spendable (the approval check refuses the same person); unchanged.
- OpenAPI snapshot: only `StockLedger` differs from a fresh generation, from earlier work, not this change.
- Postgres concurrency and the in-browser pass remain in IDR-14.

### IDR-03 - serial return through the sales-return flow (built 2026-10-16, uncommitted)

**What changed**
- `SerialNumberViewSet.transition` (`inventory/views.py`): the serial row is locked (`select_for_update`) and the status is re-checked inside the transaction, and the call is wrapped in `wrap_idempotent` (scope `serial_transition`), so a double click or two requests cannot post two stock returns.
- SOLD to AVAILABLE/RETURNED (the document-less return) is now an owner repair: non-owners get 403; the owner must send a `reason` and `confirm_no_document: true` or get 400 `sales_return_required`. The reason goes into the movement text and the audit entry. Godown parameter can no longer be the system in-transit godown.
- Serial scrap still goes through `post_stock_loss` (IDR-02). The plan's "refuse scrap of a RETURNED unit with no stock" was **not** done: `test_c02_lot_identity` shows scrapping a returned unit with no stock is deliberate (a returned unit never re-entered stock). Plan item dropped.
- Web: the SOLD row now has "Create sales return" (opens `/sales/returns?invoice=<id>`, or the challan page) and, for an owner only, "Put back without a return" with a required reason dialog. The generic Return-to-stock action is gone from `serialActions.ts`. Transition calls use per-attempt idempotency keys. New strings in en and hi.
- **Bug found and fixed (new, F-31):** the "View sale" button called `/inventory/serial-numbers/<id>/document/`, a path that does not exist (the router prefix is `serials`), so it returned 404 in the real app; the page tests mocked the API so they never saw it. URL corrected, with a backend test that pins the real path.

**Tests**
- `tests/test_inventory_idr03_serial_return.py` (7): non-owner refused; reason and confirmation required; reason recorded in movement and audit; same key replayed once; second request after the unit is back refused; document lookup path; in-transit godown refused. `test_a6_manual_serial_return` updated to send reason and confirmation.
- Web: serial page tests rewritten for the new buttons (sales return link, owner-only manual put-back with reason, manager sees no manual button); `serialActions` test updated.
- Regression: 301 backend inventory/serial/persona tests pass; 37 web inventory and i18n test files (236 tests), tsc and eslint clean.

**Open**
- O-1 (is a document-less return ever allowed?) is unanswered. If not, remove the owner path and its dialog.
- The returns page opens with the invoice picked but does not preselect the serial; the user ticks the line and serial. A `serial` query parameter would close that (small follow-up in `SalesReturnsPage`).
- A manual return still moves stock without touching the invoice, receivable or GST (that is the point of the warning text); whether COGS is reversed in the GL for it is still **[V]**.

### IDR-06 - expiry write-off (built 2026-10-16, uncommitted)

**What changed**
- `ExpiryAlertsView.post` is wrapped in `wrap_idempotent` (scope `expiry_write_off`): a double click or retry posts once. Approval and the shared stock-loss path were already done in IDR-02.
- Bad input is a message, not a server error: a non-numeric, NaN, infinite, zero or negative quantity, an unreadable date, or non-numeric `days` / `warehouse` filters now return 400. `days` is clamped to 0..3650.
- Optional `movement_date` (YYYY-MM-DD, not in the future) so a write-off can be dated when the stock went off; the period lock is checked against that date.
- The list no longer shows lots sitting in the system in-transit godown (they cannot be written off there) and each row carries `purchase_invoice`, the bill the lot came in on.
- Web: write-off rows use per-row, per-attempt keys; after a partial failure only the failed rows stay in the dialog, so pressing the button again cannot repeat the ones that went through; the filters and list stay on screen while another filter loads (`keepPreviousData`); "Return to supplier" opens the return form already on the lot's own bill (`/purchases/returns?purchase=<id>`), or a blank form when the bill cannot be traced. `PurchaseReturnsPage` now reads `?purchase=<id>`.

**Tests**
- `tests/test_inventory_idr06_expiry.py` (14 cases): same key posts once; second write-off capped by what is left; six bad quantities; bad filters; past and future dates; in-transit lots hidden; bill field present and absent.
- Web: write-off payload and key; partial failure retry (only the failed lot, new key after a refusal); return link to the bill; purchase return opens for `?purchase=`.
- Regression: 315 backend inventory/serial/persona tests; 38 web test files (260 tests); tsc and eslint clean.

**Left on purpose**
- No date picker for the write-off date in the dialog yet (API only; the dialog sends today).
- The return form opens on the bill; the user still picks the lot's lines and quantity there.
- "Sell first" still opens Quick Entry with the item only (no lot).

### IDR-04 - count correctness (built 2026-10-16, uncommitted)

**What changed**
- **Migration `inventory/0031_stock_count_line_versions`** (state-checked: `makemigrations --check` is clean). New line fields `snapshot_at`, `counted_at`, `filled_from_system`, `version`; a partial unique constraint `uniq_open_stock_count_per_godown` (one DRAFT/COUNTED count per godown). The migration first cancels older duplicate open counts (keeps the newest) and notes it on them. The test database had to be rebuilt (about 14 minutes).
- **Drift per line.** `inventory/count_drift.py`. Post takes `resolutions: {line_id: KEEP_SERVER | KEEP_LOCAL | ADJUST_FOR_MOVEMENTS}`; the old single `resolve_conflicts` still works. `ADJUST_FOR_MOVEMENTS` (now the default in the dialog) posts `counted - (system_qty + stock movements between the line snapshot and the moment it was counted)`, so a sale made after the counting is not subtracted again and a sale made before it is not missed. Lines counted before this change (no `counted_at`) fall back to counting against now.
- **No overwriting another counter.** A line save may carry the `version` it was loaded at; a stale one is refused with 409 `STOCK_COUNT_LINE_CHANGED` listing the other counter's figure. Clients that send no version are not checked (offline queue, old tabs). The page now sends only the lines it changed, sends nothing when nothing changed, and an empty `lines` list is a no-op (it used to delete every line).
- **Negative balances are on the sheet** (`on_hand != 0`, was `> 0`), so a count can correct them.
- **Cancel** takes the row lock and re-checks the status inside it.
- **"Count equals system"** marks each line it fills (`filled_from_system`); the review shows a "Not counted: system quantity" badge and the posted audit entry counts them. Typing in the box clears the mark.
- **Scanning** a code that fits several lots opens a "Which lot did you count?" chooser instead of guessing.
- **Web**: the conflict dialog gives each drifted line its own choice (with "same answer for all"); the 409 "line changed" case reloads the session, keeps the counter's other edits and names the lines. New strings in en and hi. OpenAPI snapshot and generated types regenerated (they also pick up the earlier `StockLedger` drift).

**Tests**
- `tests/test_inventory_idr04_counts.py` (14): one open count per godown; negative balance on the sheet and corrected; stale version refused with the other value; no-version client accepted; same value does not bump the version; empty list changes nothing; sale after the count not subtracted twice (and `KEEP_LOCAL` shown to add it back); sale before the count part of the count; real loss still posted; mixed answers per line; unknown answer refused; fill mark set and cleared; posted count cannot be cancelled.
- Web: lot chooser, changed-lines-only save with versions, no call when nothing changed, other-counter message and reload, per-line conflict answers posted together, fill badge in review; conflict parser tests.
- Regression: 353 backend inventory/serial/persona tests; 49 web test files (335 tests); tsc and eslint clean.

**Left on purpose**
- The server's recheck rule still uses the sheet-vs-counted difference (what the review screen shows). A line the counter keeps with `KEEP_LOCAL` can post a bigger real difference than the sheet shows; the dialog says so.
- No setting to switch "count equals system" off per company (the plan's optional item); it is recorded and badged instead.
- Autosave and the pending-offline chip are IDR-05.
- Concurrency under Postgres (two counters saving at once, post vs cancel) is still IDR-14; SQLite tests cover the version check but not row-lock races.
- The migration's duplicate-closing step is not covered by a test (the constraint now prevents building the duplicate state).

### IDR-05 - count feedback, autosave and offline state (built 2026-10-16, uncommitted; web only)

**What changed** (`StockCountPage.tsx`, `useStockOffline.ts`, strings in en and hi; no backend or migration)
- **Posted message.** A successful online post now shows a green notice: how many lines were adjusted, the gain and loss, how many lines were left alone because stock moved, and a "View stock ledger" link filtered to the godown. Before, the dialog just closed.
- **Autosave.** Counts save by themselves 5 seconds after the last edit (`AUTOSAVE_MS`), only the changed lines, only while online. A status line in the dialog says "Not saved yet. It saves by itself...", "Saving...", "Saved hh:mm" or, if the background save fails, a warning (no error box). A save clears only what it sent, so a figure typed while it was in flight is kept. Manual Save counts and the review step use the same path.
- **Offline state.** "Queued" chip on the count list for sessions waiting in the outbox, and the pending figure in the header now comes from the outbox (it survives a reload) and refreshes when the outbox is flushed.
- **Held counts.** When a queued count is sent and the server is waiting for the owner (202), the outbox banner says so instead of silently dropping the draft. `flushStockDraft` now returns `{ heldForApproval }`.

**Tests** (`StockCountPage.test.tsx` 22, `useStockOffline.test.tsx`): posted message and ledger link; Queued chip and pending figure; autosave after the delay without pressing Save; a figure typed during a save is kept; a failed background save shows the warning and no alert; offline flush of a held count sets the banner. Regression: 37 web inventory test files (252 tests), offline and layout tests, tsc and eslint clean.

**Left on purpose**
- The 5-second delay is a constant, not a setting.
- Autosave only runs in count mode, not during review (nothing is typed there).
- A count that was queued, then flushed while the page was closed and conflicted, still depends on the conflict dialog reopening when the page is next opened (existing behaviour).
- No in-browser pass yet (IDR-14).

### IDR-07 - transfers (built 2026-10-16, uncommitted)

**Decision taken for O-3 (not yet confirmed by the owner or the CA).** The short quantity stays in the in-transit godown as a *claim*, exactly as before, so nothing in the books changes by default. What is new is that the claim is visible and can be settled by an owner or manager: **write off** (a stock loss, through the shared stock-loss service) or **return to the source godown**. If the CA wants a different treatment it is a change in `StockTransferService.resolve_shortage` only.

- **Backend.** Migration `0032` adds `StockTransfer.dispatched_at` and `StockTransferLine.shortage_resolution`. `POST /inventory/transfers/<id>/resolve-shortage/` (owner or manager, idempotent) takes `[{line, action: WRITE_OFF|RETURN}]`; a line can be settled once; a write-off that needs approval comes back as pending. Cancelling a transfer after a shortage was settled no longer restores that quantity a second time. The list takes `status`, `warehouse`, `q` and `open_shortage`.
- **Web.** Transfers page: a "Goods in transit" panel with the age in days (flagged late from 3 days), a "Missing goods to settle" panel with Write off / Return to source for owners and managers, a status filter (incl. "With missing goods") and search, a notes box on the new draft, a notice after a draft is created, a warning in the receive dialog saying a short quantity stays in transit as a claim, and the settlement shown in the details table.
- **Tests.** `tests/test_inventory_idr07_transfers.py` (8): dispatch time stamped; write-off clears the claim and books the loss; return puts it back in the source; settle once only; no shortage, no settle; role gate; cancel after settling; list filters. Web: helpers (transit days, open shortages, filter), panel with late flag, settle button and notice, hidden for other roles, search.

**Left on purpose:** accounting treatment of the write-off follows the existing flag (`ACCOUNTING_POST_STOCK_ADJUSTMENTS`, off); no edit of a draft's lines (the plan's optional stretch).

### IDR-10 - stock lists (built 2026-10-16, uncommitted)

- **Backend.** `GET /inventory/balances/by-product/` groups, sorts (`ordering`: name, available, on_hand, plus or minus) and pages on the server (`page_size` up to 200) with the same filters as the flat list, `negative=1` for out/zero/negative items, and a `summary` (items, in stock, out) over the whole filtered set. The flat list gained `negative=1`. The stock CSV (`/exports/inventory/`) now follows the page's `warehouse` and `q`. `_GroupedPagination` avoids the default class's primary-key tiebreak, which would split every group back into rows.
- **Web.** Current stock reads the grouped endpoint with "Show more items" paging; lots load only when an item is opened; sort, "only out of stock or negative", godown and search live in the URL; row keys include product, godown and lot; **Print** fetches every row for the current filters into a plain table (the windowed table is hidden on paper); the KPI chips come from the server's summary; a person who may not read the books sees no stock value (not "0"). The item form and the adjustment page ask for one item's balances instead of the whole catalogue.
- **Tests.** `tests/test_inventory_idr10_stock_lists.py` (8): grouped totals equal the sum of the flat rows, summary, paging and order, godown and negative filters, search parity, tenant isolation, CSV follows the filters. Web: 10 Current stock tests (server summary, godown, URL state, sort and filter, load more, lots on open, print of 300 rows, CSV parameters, no value for a person without access).

**Left on purpose:** the old unpaged `listStock()` stays for POS, sales and purchase editors (they filter by item ids); only Current stock, the item form and the adjustment page moved. Value as a sort key is not offered (cost masking).

### IDR-08 - planning and forecast numbers (built 2026-10-16, uncommitted; no migration)

- **One pace (F-14, F-17).** `inventory/forecast.py` now has one definition used by the forecast, Purchase planning and the item form's suggested reorder level: net units sold (less returns) divided by the days the item was actually in stock in the window (a day counts when it had stock at its start or end, or sold), falling back to the flat mean when fewer than 7 such days exist. `godown_velocity` is the same measure per godown, replacing the inline 14-day gross query in `suggest_replenishment` (which now returns `velocity_per_day`; `velocity_14d` stays as a property for the alerts API). The window (30), cover (30), reorder cover (14) and draft-order age (30) are company settings in the `feature_flags` JSON (`FORECAST_WINDOW_DAYS`, `FORECAST_COVER_DAYS`, `REORDER_COVER_DAYS`, `PLANNING_DRAFT_PO_DAYS`; bad values fall back). Inactive and non-stocked items are no longer forecast.
- **Donor cap (F-15).** A donor godown gives at most its surplus; the rest becomes a purchase row. The in-transit godown and switched-off godowns are never donors.
- **Open orders (F-16).** `open_order_quantities` is shared: recent draft purchase orders and orders converted into a bill that is not yet completed count; older drafts are returned as `stale_drafts` and shown as a warning instead. `last_price` is now the price on the latest completed bill (item master price if never bought) and `master_price` is returned beside it. Creating drafts is idempotent per key and a second draft for the same supplier and item within an hour is refused unless `confirm_duplicate`.
- **Forecast page.** Search, CSV download, a "Not moving" tab (over six months of cover, or stock and no sales in 90 days), the in-stock-days basis shown in the method column.
- **Tests.** `tests/test_inventory_idr08_numbers.py` (14); the existing forecast, planning and replenishment tests were updated for the 30-day pace and the duplicate guard. Web: forecast search, overstock tab and CSV; planning stale warning, separate transfer and purchase rows, key per attempt and the duplicate confirmation.

**Left on purpose:** converted-order counting is tested through the query but not with a real bill; Planning and Forecast stay separate pages (O-9).

### IDR-09 - products (built 2026-10-16, uncommitted; no migration)

- **Server filters.** `GET /products/` takes `category`, `brand` (ids), `gst_rate`, `stock_status` (`in` = anything available, low items included; `low` = the Low stock page's rule; `out` = nothing available or never stocked) and `name_exact`. `GET /products/filter-options/` lists the categories, brands and slabs in use. The page no longer downloads the whole catalogue to fill a menu or filter; the CSV export sends the same search and filters.
- **Codes.** A used item code or barcode is now a field error naming the other item (it was an unhandled constraint error).
- **Item form.** Server-side duplicate-name check with the other item's code; warnings (not blocks) for a zero price, a price above MRP and a cost above the price; a failed opening stock refreshes the item list.
- **Delete.** Already deactivates a used item and says so (server returns 200 with the message); the client contract matches. O-4 stays "auto-deactivate" until the owner says otherwise.
- **Tests.** `tests/test_inventory_idr09_products.py` (10); web Items-page filter tests rewritten for the server filters, plus item-form tests.

**Left on purpose:** O-5 (block selling price above MRP for branded pre-packed goods) and O-6 (mandatory HSN) are not enforced; a warning only.

### IDR-11 - labels (built 2026-10-16, uncommitted; no migration)

- **ZPL.** The thermal label now carries name, barcode, price (MRP, else selling price; can be left off), and the lot with its expiry; `^PW`/`^LL` follow the chosen size. `GET /inventory/labels.zpl?product&copies&size&batch&price` and `POST` with `{labels:[...]}` for one file (at most 500 labels). A code that CODE128 cannot encode is refused by item name.
- **Page.** A4 sticker sheets (3 x 8 and 2 x 7) as a print grid, a test page to check alignment, "Download all as one ZPL file", a warning on a row whose code cannot be a barcode, and "Add all items without a barcode" now reads a server list with the real count ("100 of 250 added"). "Give N items a barcode" (asks first) is offered to people who may edit items; **`generate-barcode` on an item was open to any non-viewer and is now an inventory right.**
- **Tests.** `tests/test_inventory_idr11_labels.py` (11); web label page and helper tests, including the same fixtures as the server test so the browser label and the ZPL read the same.

### IDR-12 - roles and cost visibility (built 2026-10-16, uncommitted)

- **Matrix.** `tests/test_inventory_idr12_roles.py` (25) writes the role x screen matrix by hand for OWNER, MANAGER, INVENTORY_STAFF, SALES_STAFF, ACCOUNTANT, AUDITOR and VIEWER (reads and writes), and checks that a salesperson sees no cost field in any inventory response. Web `navigation/inventoryRoles.test.ts` checks the menu per role against the same table.
- **Fixes found by it.** Purchase planning returned `last_price` and `master_price` to anyone who could open it: now only to people who may see item cost. `generate-barcode` was open to every non-viewer (above). The web's "may view inventory" rule now matches the server (adds people who sell or buy), the Labels menu entry and route follow the read right, Low stock shows the reorder rules and "Add rule" only to people who may change them, and Current stock shows no "stock value: 0" to someone the books refuse.
- **Decisions taken:** serial lookup stays open to the counter (`CanReadSerials`) while the Serials page stays for inventory users (O-7 unchanged). Count variance values are visible to everyone who can open counts, because they can already see item cost.

### IDR-13 - polish (built 2026-10-16, uncommitted)

- Real tabs (`ChipTabs`: tablist, one tab stop, arrow keys, Home/End, labelled panel) on Low stock, Demand forecast and Expiry alerts.
- The "Out of stock" tab says "Out of stock (no reorder rule)" instead of "At or below reorder".
- Strings: the item form's 13 validation messages, serial column heads and statuses (`enumLabel('serialStatus')`), the count status in the dialog title (`countStatus`), Hide/Show lots and All godowns (in IDR-10). en and hi added; i18n ratchet tests pass. Hindi wording still needs a native review (O-8).
- The Purchase planning menu entry now needs both `ENABLE_PURCHASE_PLANNING` and `ENABLE_REPLENISHMENT`. The stale "known gaps" in `INVENTORY_REVIEW_IMPLEMENTATION_PLAN.md` were struck through.
