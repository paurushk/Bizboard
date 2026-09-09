# Stock & Godown — Release-Blocking Code Review

## Executive Summary & Flow Coverage

| Flow / Subsystem | Write Path | Reversal / Cancel | Concurrency Safety | Tests Present | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Movement Ledger & Invariant** | Append-only `post_movement` | Reversing compensating movements | `StockBalance` row lock (`select_for_update`) | `test_concurrency_races.py`, `test_stock_flow.py` | **FAIL** (STK-001 mutates ledger) |
| **Default Warehouse & Creation** | `InventoryService.default_warehouse` | N/A (cannot delete default) | Unique constraints + `IntegrityError` retry | `test_c01_godown.py` | **PASS** (backend) / **GAP** (STK-016 UI default) |
| **Negative Stock Policy** | `BLOCK` hard-fails; `WARN` collects strings | Same policy on issues | Concurrency-safe under `BLOCK`; broken WAVG on `WARN` | `test_a11_a12_stock_cost.py` | **FAIL** (STK-006, STK-013) |
| **Stock Transfer** | Two-sided atomic (`TRANSFER_OUT` + `IN`) | Reversing `ADJUSTMENT`s + layer restore | Locked on transfer record; no in-transit | `test_phase4_inventory.py` | **FAIL** (STK-003, STK-012, STK-013) |
| **Stock Adjustment** | Signed `ADJUSTMENT` movement | Manual compensating adjustment | Balance row lock in `post_movement` | `test_phase4_inventory.py` | **WARN** (STK-011 UI batch desync) |
| **Stock Count (Audits)** | Variance `counted - current` -> `ADJUSTMENT` | Cannot cancel once posted | Idempotency key wrapped; conflict 409 | `test_phase4_inventory.py` | **FAIL** (STK-004, STK-009, STK-010, STK-015) |
| **Serial Numbers** | `receive` + `transition` | Return -> `AVAILABLE`; scrap -> `ADJUSTMENT -1` | Row-locked `status=source`; unique constraint | `test_a6_manual_serial_return.py`, `test_pr5_returns_serials_fefo.py` | **FAIL** (STK-007 UI, STK-008 GL/cost) |
| **Batch Lots & Expiry** | `get_or_create_batch` + FEFO sort | Expiry write-off (`ADJUSTMENT -qty`) | Locked per-lot balance | `test_item_godown_expiry.py` | **FAIL** (STK-002 write-off crash) |
| **FIFO Cost Layers** | Oldest-layer peel; stamped on movement | `restore_fifo_peels` / `retire_source_layers` | Row-locked `InventoryCostLayer` | `test_a11_a12_stock_cost.py` | **FAIL** (STK-005 snapshot loss) |
| **WAVG Running Cost** | Perpetual `InventoryRunningCost` | `_apply_running_cost` signed updates | Row-locked running cost row | `test_a11_a12_stock_cost.py` | **FAIL** (STK-006 WARN doubling) |
| **Offline Sync & Conflict** | Queue -> Flush -> HTTP 409 conflict | Server merge preserves movements | Client-side outbox queue + retry guard | `useStockOffline.test.ts`, `godownConflict.test.ts` | **WARN** (STK-015 silent count drop) |
| **Tenancy & Subscription** | `CompanyScopedViewSet` / `CompanyScopedModel` | Scoped queries | Enforced via tenant filter | `test_sprint4_erp_rls.py` | **FAIL** (STK-014 gate bypassed) |

---

### Findings Count by Severity

| Severity | Count | Issue Identifiers |
| :--- | :--- | :--- |
| **Critical** | 4 | STK-001, STK-002, STK-003, STK-004 |
| **High** | 6 | STK-005, STK-006, STK-007, STK-008, STK-009, STK-010 |
| **Medium** | 5 | STK-011, STK-012, STK-013, STK-014, STK-015 |
| **Low** | 2 | STK-016, STK-017 |
| **Total** | **17** | |

---

## Detailed Findings

### STK-001 — Append-only invariant breach: `StockMovement.unit_cost` mutated via bare `.update()` on purchase price amendment
- **Module:** Stock/Godown -> Invariant / Append-only ledger
- **Location:** `backend/purchases/services.py:470`
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** The core inventory invariant states that `StockMovement` is an append-only ledger (`models.StockMovement.save()` and `delete()` explicitly raise `ValueError` on mutation). The only documented exception is `StockMovement.stamp_cost()`, which is a row-locked, single-purpose method strictly for stamping the newly calculated peel cost onto an issue. In `purchases/services.py:470` (`restamp_fifo_layers_for_price_amend`), the code executes a raw `StockMovement.objects.filter(pk=move.pk).update(unit_cost=new_cost)`. This directly rewrites historical ledger rows via QuerySet `.update()` (bypassing model guards), performs no `select_for_update` on the movement, and violates the immutable ledger contract.
- **Trigger / repro:** Complete a purchase invoice. Edit the purchase invoice unit price via H9 price amendment before stock is issued. Inspect historical `StockMovement` rows.
- **Consequence:** Historical ledger entries are retroactively modified. If reports or accounting postings previously read the original movement's cost, the physical ledger silently disagrees with historical journal entries and audit trails.
- **Code evidence:** `backend/purchases/services.py:470`:
  ```python
  StockMovement.objects.filter(pk=move.pk).update(unit_cost=new_cost)
  ```
  Contrast with `backend/inventory/models.py:157-181` which explicitly states:
  > *"This is a row-locked, single-purpose update — never route ad-hoc field changes through it, and never `.update()` a StockMovement any other way."*
- **Suggested fix direction:** Avoid rewriting historical `PURCHASE` movements. Post a compensating cost adjustment movement (or price-variance adjustment), or if in-place restamping of unpeeled purchases is an approved architectural exception, route it strictly through a dedicated, row-locked method on `StockMovement` with an explicit audit log.
- **Test to add:** `test_purchase_price_amend_does_not_execute_bare_stock_movement_update`
- **Twin check:** Sales equivalent — n/a (Sales invoices do not retroactively amend unit costs on completed sales movements).

---

### STK-002 — Hard crash on expired batch write-off (`block_expired_stock` blocks write-off of already-expired goods)
- **Module:** Stock/Godown -> Expiry Alert & Write-off
- **Location:** `backend/inventory/views.py:584` & `backend/inventory/services.py:205-207`
- **Type:** Broken-feature
- **Severity:** Critical
- **What's wrong:** When writing off an expired batch via `ExpiryAlertsView.post` (`POST /api/v1/inventory/alerts/expiry/`), the view issues an adjustment via `InventoryService.post_movement(movement_type=MovementType.ADJUSTMENT, quantity=-qty, reason="EXPIRED", reference_type="expiry_write_off", ...)`. Because `skip_negative_check` defaults to `False`, `post_movement` executes:
  `if delta < 0 and not skip_negative_check: if batch and company.block_expired_stock and batch.expiry_date and batch.expiry_date < timezone.localdate(): raise BusinessRuleError(...)`.
  If the batch is expired (`expiry_date < today`) and `company.block_expired_stock` is active (default is True), `post_movement` raises `BusinessRuleError("Batch 'X' is expired and cannot be issued.")` and crashes the write-off! Existing tests only passed because they tested with a *near-expiry* date in the future (`date.today() + timedelta(days=3)`). Once goods actually expire, operators are permanently blocked from writing them off.
- **Trigger / repro:** Create a batch with an expiry date in the past (`yesterday`). Attempt to write it off via the Expiry Alerts screen or `POST /api/v1/inventory/alerts/expiry/`.
- **Consequence:** Operators cannot remove expired stock from the godown. The expired stock remains stuck on the balance and in the godown forever unless `block_expired_stock` is disabled company-wide.
- **Code evidence:** `backend/inventory/views.py:584-595`:
  ```python
  movement = InventoryService.post_movement(
      company=company,
      product=product,
      movement_type=MovementType.ADJUSTMENT,
      quantity=-qty,
      reason="EXPIRED",
      reference_type="expiry_write_off",
      user=request.user,
      warehouse=warehouse,
      batch=batch,
      # skip_negative_check is omitted, defaulting to False!
  )
  ```
  `backend/inventory/services.py:205-207`:
  ```python
  if delta < 0 and not skip_negative_check:
      if batch and company.block_expired_stock and batch.expiry_date and batch.expiry_date < timezone.localdate():
          raise BusinessRuleError(f"Batch '{batch.batch_no}' is expired and cannot be issued.")
  ```
- **Suggested fix direction:** In `ExpiryAlertsView.post`, pass `skip_negative_check=True` (or explicitly permit outbound movements where `reference_type == "expiry_write_off"` or `reason == "EXPIRED"` to bypass the expiry issue check in `post_movement`).
- **Test to add:** `test_write_off_batch_with_past_expiry_date_succeeds_under_block_expired_stock`
- **Twin check:** n/a (expiry write-off is inventory-specific).

---

### STK-003 — Unrestricted DELETE on COMPLETED transfers cascades and destroys transfer history, leaving orphan ledger movements
- **Module:** Stock/Godown -> Stock Transfer
- **Location:** `backend/inventory/views.py:347-371` & `backend/core/viewsets.py:46-50`
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** `StockTransferViewSet` inherits directly from `CompanyScopedViewSet` and does not override `perform_destroy` or `destroy`. A client can issue `DELETE /api/inventory/stock-transfers/{id}/` against a `COMPLETED` transfer. `CompanyScopedViewSet.perform_destroy` calls `instance.delete()`. Because `StockTransferLine.transfer` is defined with `on_delete=models.CASCADE`, Django deletes the transfer header and all transfer lines. The underlying `TRANSFER_OUT` and `TRANSFER_IN` `StockMovement` rows are left stranded with `reference_type="stock_transfer"` and `reference_id=<deleted_id>`. The transfer can never be cancelled, viewed, or audited.
- **Trigger / repro:** Complete a stock transfer. Send `DELETE /api/v1/inventory/stock-transfers/{id}/`.
- **Consequence:** Deletion of completed statutory/inventory documents. Ledger stock movements lose their source documents, breaking the link between physical godown movements and authorizations. Cancel and reconciliation paths permanently break.
- **Code evidence:** `backend/inventory/views.py:347-350`:
  ```python
  class StockTransferViewSet(CompanyScopedViewSet):
      queryset = StockTransfer.objects.select_related("from_warehouse", "to_warehouse").prefetch_related("lines")
      serializer_class = StockTransferSerializer
      permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]
      # No destroy() or perform_destroy() restriction!
  ```
  `backend/core/viewsets.py:46-49`:
  ```python
  def perform_destroy(self, instance):
      entity_id = str(instance.pk)
      instance.delete()
      self._audit_raw("DELETE", entity_id)
  ```
- **Suggested fix direction:** Override `perform_destroy` on `StockTransferViewSet` to block deletion if `instance.status != StockTransfer.Status.DRAFT` (or disallow `destroy` entirely).
- **Test to add:** `test_delete_completed_stock_transfer_raises_business_rule_error`
- **Twin check:** Sales/Purchase equivalent — `SalesInvoiceViewSet` and `PurchaseInvoiceViewSet` explicitly block deletion of non-draft invoices. `StockTransferViewSet` missed this guard.

---

### STK-004 — Unrestricted DELETE on POSTED stock count sessions destroys physical count records and audit trail
- **Module:** Stock/Godown -> Stock Count
- **Location:** `backend/inventory/views.py:642-646` & `backend/core/viewsets.py:46-50`
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** `StockCountSessionViewSet` inherits from `CompanyScopedViewSet` and does not restrict the `DELETE` action. When a stock count session is in `POSTED` status, `ADJUSTMENT` movements have already been posted to `StockMovement` referencing the session ID. Sending `DELETE /api/inventory/stock-counts/{id}/` executes `instance.delete()`. This deletes the `StockCountSession` and cascade-deletes all its `StockCountLine` records (which hold `system_qty`, `counted_qty`, and variance). The physical count audit trail is completely lost, and the posted `StockMovement` adjustments are orphaned.
- **Trigger / repro:** Create, count, and post a stock count session. Send `DELETE /api/v1/inventory/stock-counts/{id}/`.
- **Consequence:** Irreversible destruction of inventory audit evidence and count history. Auditors cannot verify why inventory balances were adjusted because the session and physical counted records were purged.
- **Code evidence:** `backend/inventory/views.py:642-646`:
  ```python
  class StockCountSessionViewSet(CompanyScopedViewSet):
      queryset = StockCountSession.objects.select_related("warehouse").prefetch_related("lines__product", "lines__batch")
      serializer_class = StockCountSessionSerializer
      permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]
      # No destroy() or perform_destroy() restriction!
  ```
- **Suggested fix direction:** Override `perform_destroy` on `StockCountSessionViewSet` to forbid deletion when `instance.status in (StockCountSession.Status.POSTED, StockCountSession.Status.COUNTED)`.
- **Test to add:** `test_delete_posted_stock_count_session_blocked`
- **Twin check:** n/a.

---

### STK-005 — `InventoryValuationSnapshot` loses FIFO cost layers, permanently degenerating post-snapshot FIFO valuation into WAVG
- **Module:** Stock/Godown -> Valuation & Snapshots
- **Location:** `backend/inventory/models.py:406-428` & `backend/inventory/services.py:1720-1730, 1812-1826`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** For high-volume companies (`>10,000` movements), `InventoryValuationService.valuation(as_of=...)` uses month-end `InventoryValuationSnapshot` to seed historical valuation state instead of replaying from genesis. However, `InventoryValuationSnapshot` only stores `qty` and `value` columns; it does not store FIFO cost layers. When `valuation()` initializes state from a snapshot, it sets `state[key]["layers"] = []`. When `_replay()` then processes subsequent sales, it finds `entry["layers"]` empty. As a result, lines 1825-1826 execute:
  `if remaining > 0: cost += remaining * pre_avg; entry["value"] -= cost`.
  Every FIFO sale after a snapshot is costed at the pre-issue weighted average (`pre_avg`), completely bypassing FIFO layering!
- **Trigger / repro:** Set company to `FIFO`. Post >10,000 movements. Run `write_month_end_snapshot`. Query `valuation(as_of=date_after_snapshot)`. Compare unit costs against perpetual `InventoryCostLayer` rows.
- **Consequence:** Historical valuation reports and COGS re-derivations produce Weighted Average values instead of FIFO values whenever the snapshot threshold optimization is active.
- **Code evidence:** `backend/inventory/services.py:1720-1730`:
  ```python
  for snap in snap_rows:
      key = (snap.warehouse_id, snap.product_id, snap.batch_id)
      state[key] = {
          "warehouse": snap.warehouse_id,
          "warehouse_name": getattr(snap.warehouse, "name", None),
          "product": snap.product_id,
          "product_name": snap.product.name if snap.product_id else None,
          "batch": snap.batch_id,
          "qty": Decimal(str(snap.qty or 0)),
          "value": Decimal(str(snap.value or 0)),
          "layers": [],  # <--- Cost layers are never stored or restored!
      }
  ```
  `backend/inventory/services.py:1825-1826`:
  ```python
  if remaining > 0:
      cost += remaining * pre_avg  # Degenerates to WAVG!
  ```
- **Suggested fix direction:** Extend `InventoryValuationSnapshot` to store active FIFO layers in a `JSONField` (or related layer snapshot model), or for FIFO companies, disable snapshot replaying and replay from the last full FIFO checkpoint.
- **Test to add:** `test_fifo_valuation_from_snapshot_preserves_distinct_layer_costs`
- **Twin check:** n/a.

---

### STK-006 — WARN oversell from zero stock corrupts `InventoryRunningCost` valuation and permanently doubles unit costs on replenishment
- **Module:** Stock/Godown -> Valuation / Negative-stock policy
- **Location:** `backend/inventory/services.py:502-538`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** Under `negative_stock_policy = "WARN"`, a tenant can sell stock when on-hand is 0. In `_apply_running_cost`, when `delta < 0` and initial `qty == 0`, `avg = (value / qty) if qty else Decimal("0")` yields 0. Thus `value` does not change (`value -= issue * 0`), and `qty` becomes `-issue` (e.g. -5). The running row now has `qty = -5, value = 0`.
  When a replenishment purchase arrives (`delta = +5` at ₹100), lines 502-504 execute:
  `qty += delta` (becomes 0) and `value += delta * cost` (becomes 0 + 500 = ₹500).
  Notice that `if qty == 0: value = Decimal("0")` is located exclusively inside `elif delta < 0:`. It is never executed on inbound `delta > 0`!
  `InventoryRunningCost` now persists `qty = 0, value = ₹500`! When the next purchase arrives (5 units at ₹100), `qty` becomes 5 and `value` becomes `500 + 500 = ₹1000`. The running `unit_cost` (`value / qty`) becomes `1000 / 5 = ₹200` for an item purchased at ₹100!
- **Trigger / repro:** Set `negative_stock_policy = "WARN"`. With 0 stock, complete an invoice selling 5 units. Then record a purchase of 5 units at ₹100. Then record another purchase of 5 units at ₹100. Check `InventoryRunningCost.unit_cost`.
- **Consequence:** Selling stock at 0 under WARN leaves ghost inventory value stranded at 0 on-hand. Subsequent purchases inherit this inflated value, corrupting the General Ledger COGS and inventory valuation reports.
- **Code evidence:** `backend/inventory/services.py:502-505`:
  ```python
  if delta > 0:
      qty += delta
      value += delta * cost
      # Notice: if qty reached 0, value is NOT reset to 0!
  elif delta < 0:
      issue = -delta
      avg = (value / qty) if qty else Decimal("0")
      value -= issue * avg
      qty -= issue
      if qty == 0:
          value = Decimal("0")
  ```
- **Suggested fix direction:** In `_apply_running_cost`, when an issue occurs at or below zero, cost the issue at the product's master purchase price (or last known cost) so `value` tracks the negative liability. When replenishing, if `qty == 0`, ensure `value` resets to `Decimal("0")`.
- **Test to add:** `test_warn_oversell_from_zero_followed_by_purchases_does_not_inflate_wavg_cost`
- **Twin check:** n/a.

---

### STK-007 — `SerialsPage` UI prompts "Mark sold" on AVAILABLE serials which always fails with 400, and hides "Mark scrapped"
- **Module:** Stock/Godown -> Serial UI
- **Location:** `web/src/pages/phase/InventoryPhasePages.tsx:521` & `backend/inventory/views.py:449-457`
- **Type:** Broken-feature
- **Severity:** High
- **What's wrong:** In `InventoryPhasePages.tsx:521` (`SerialsPage`), the action button target is hardcoded as:
  `const target = status === 'AVAILABLE' ? 'SOLD' : status === 'SOLD' ? 'RETURNED' : status === 'RETURNED' ? 'SCRAPPED' : null;`
  When a serial is `AVAILABLE`, the UI renders a button "Mark sold" that calls `transitionSerial(id, { status: 'SOLD' })`.
  However, in `SerialNumberViewSet.transition` (`backend/inventory/views.py:450`), the allowed transition map is:
  `SerialNumber.Status.AVAILABLE: {SerialNumber.Status.SCRAPPED}`.
  Transitioning an AVAILABLE serial to SOLD directly via the serial API is strictly forbidden (serials can only become SOLD through sales invoice/challan completion). Therefore, clicking "Mark sold" ALWAYS fails with HTTP 400 `{"detail": "Invalid serial status transition."}`. Furthermore, the valid transition for an AVAILABLE serial (`SCRAPPED`) is not offered in the UI at all.
- **Trigger / repro:** Open Inventory -> Serials. Find any serial with status `AVAILABLE`. Click "Mark sold".
- **Consequence:** The primary action button on every available serial produces an error alert. Operators cannot scrap defective or lost available serials from the UI.
- **Code evidence:** `web/src/pages/phase/InventoryPhasePages.tsx:520-521`:
  ```typescript
  const status = String(row.status);
  const target = status === 'AVAILABLE' ? 'SOLD' : status === 'SOLD' ? 'RETURNED' : status === 'RETURNED' ? 'SCRAPPED' : null;
  ```
  `backend/inventory/views.py:449-457`:
  ```python
  allowed = {
      SerialNumber.Status.AVAILABLE: {SerialNumber.Status.SCRAPPED},
      SerialNumber.Status.SOLD: {SerialNumber.Status.RETURNED, SerialNumber.Status.AVAILABLE},
      SerialNumber.Status.RETURNED: {SerialNumber.Status.SCRAPPED},
      SerialNumber.Status.SCRAPPED: set(),
  }
  if target not in allowed.get(serial.status, set()):
      return Response({"detail": "Invalid serial status transition."}, status=status.HTTP_400_BAD_REQUEST)
  ```
- **Suggested fix direction:** In `InventoryPhasePages.tsx`, for `status === 'AVAILABLE'`, set `target = 'SCRAPPED'` (with a confirmation modal) instead of `'SOLD'`.
- **Test to add:** `test_serials_page_ui_scraps_available_serial_and_does_not_offer_sold`
- **Twin check:** n/a.

---

### STK-008 — Manual serial return bypasses GL accounting, slices only 200 items, and drops FIFO cost layers if sale move not found
- **Module:** Stock/Godown -> Serial Tracking & Accounting
- **Location:** `backend/inventory/views.py:385-432, 477-504` & `backend/inventory/services.py:647-677`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** In `SerialNumberViewSet.transition` (`SOLD -> AVAILABLE`), several critical issues occur:
  1. **No GL Posting:** When `post_movement(movement_type=MovementType.SALES_RETURN)` is called, `PostingService` is never invoked. Physical stock increases, but GL Account 1400 (Inventory) and Account 5100 (COGS) are never updated.
  2. **Truncated Historical Search:** `_sale_movement_for_serial` searches `SalesItem.objects.filter(...)[:200]`. If a product has more than 200 line items sold, older sales are never found.
  3. **FIFO Layer Loss:** If `sale_move is None` (due to older sale or imported sale), `restore_fifo_peels` is skipped. In `InventoryService._apply_cost_layers`, `MovementType.SALES_RETURN` is deliberately excluded from layer creation (lines 647-653). Consequently, `StockBalance.on_hand` increases by 1, but zero FIFO cost layers are created or restored!
- **Trigger / repro:** Sell a serial-tracked product on an invoice. Once >200 invoice items exist (or on an imported sale), transition the serial to AVAILABLE via the serials API. Check GL journal entries and FIFO layer sum vs `StockBalance.on_hand`.
- **Consequence:** General Ledger drifts from inventory asset reality. FIFO cost layers have fewer units than on-hand stock, triggering layer exhaustion errors on subsequent sales.
- **Code evidence:** `backend/inventory/views.py:397-404`:
  ```python
  for item in (
      SalesItem.objects.filter(product=serial.product, invoice__company=company)
      .select_related("invoice")
      .order_by("-invoice_id", "-id")[:200]
  ):
  ```
  `backend/inventory/services.py:647-653`:
  ```python
  if delta > 0 and movement_type in (
      MovementType.PURCHASE,
      MovementType.OPENING_STOCK,
      MovementType.TRANSFER_IN,
      MovementType.MANUFACTURE_RECEIPT,
      MovementType.ADJUSTMENT,
  ):
      # SALES_RETURN is NOT listed here!
  ```
- **Suggested fix direction:** Query `SalesItem` directly for `serial_numbers__contains=serial.serial_number` without an arbitrary slice; when `sale_move` is absent, create a fallback `InventoryCostLayer`; invoke `PostingService.post_stock_movement` for the return when accounting is enabled.
- **Test to add:** `test_manual_serial_return_creates_gl_posting_and_fallback_fifo_layer_when_sale_move_missing`
- **Twin check:** n/a.

---

### STK-009 — POSTED stock count session allows updating warehouse and header fields via PATCH/PUT
- **Module:** Stock/Godown -> Stock Count Session
- **Location:** `backend/inventory/serializers.py:409-418`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** In `StockCountSessionSerializer.update`, the status guard line 409 checks:
  `if lines is not None and instance.status not in (StockCountSession.Status.DRAFT, StockCountSession.Status.COUNTED): raise BusinessRuleError(...)`.
  If a caller submits a PATCH or PUT request *without* the `lines` key (e.g. `{"warehouse": 2, "notes": "Audited"}`), `lines is None` evaluates to True. The status check is completely bypassed! Line 418 then calls `super().update(instance, validated_data)`, allowing an operator to change the `warehouse`, `counted_on`, or `notes` on a `POSTED` or `CANCELLED` session.
- **Trigger / repro:** Create and post a stock count session for Warehouse 1. Send `PATCH /api/v1/inventory/stock-counts/{id}/` with `{"warehouse": 2}`.
- **Consequence:** A posted count session's header can be switched to a different godown, while the movements already posted in `StockMovement` remain tied to the old godown. Historical count audits show false godown assignments.
- **Code evidence:** `backend/inventory/serializers.py:409-418`:
  ```python
  if lines is not None and instance.status not in (
      StockCountSession.Status.DRAFT,
      StockCountSession.Status.COUNTED,
  ):
      raise BusinessRuleError("Only a draft or counted session can be edited.")
  ```
- **Suggested fix direction:** Make the status check unconditional at the start of `update()`: `if instance.status not in (StockCountSession.Status.DRAFT, StockCountSession.Status.COUNTED): raise BusinessRuleError(...)`.
- **Test to add:** `test_patch_posted_stock_count_header_raises_business_rule_error`
- **Twin check:** Sales/Purchase equivalent — modifying completed invoices via PATCH without lines is blocked.

---

### STK-010 — Stock count posts adjustments dated TODAY instead of `session.counted_on` and validates period against TODAY
- **Module:** Stock/Godown -> Stock Count & Closed-period
- **Location:** `backend/inventory/views.py:667, 705-716`
- **Type:** Sales/Purchase-inconsistency
- **Severity:** High
- **What's wrong:** In `StockCountSessionViewSet.post`:
  1. The closed-period assertion checks `assert_period_allows_money_amend(session.company, _tz.localdate())` using today's date instead of `session.counted_on`.
  2. In `InventoryService.post_movement()`, `movement_date` is omitted, which defaults to `timezone.localdate()`.
  If physical stock counting was conducted on March 31st (month-end / FY-end) and entered as `counted_on: "2026-03-31"`, but posted on April 1st, the period check validates April 1st instead of March 31st, and the stock movements are written with `movement_date = 2026-04-01`.
- **Trigger / repro:** Create a stock count with `counted_on` set to the last day of a month. Lock/close that month. Post the count the following month. The post succeeds, but adjustments are recorded in the new month.
- **Consequence:** Month-end physical count adjustments do not land in the period being audited. Financial year-end closing balances remain unadjusted for physical variance on March 31, and distort the subsequent FY P&L.
- **Code evidence:** `backend/inventory/views.py:667`:
  ```python
  assert_period_allows_money_amend(session.company, _tz.localdate())
  ```
  `backend/inventory/views.py:705-716`:
  ```python
  InventoryService.post_movement(
      company=session.company,
      product=line.product,
      movement_type=MovementType.ADJUSTMENT,
      quantity=variance,
      reason="STOCK_COUNT",
      reference_type="stock_count",
      reference_id=session.pk,
      user=request.user,
      warehouse=session.warehouse,
      batch=line.batch,
      # movement_date is omitted!
  )
  ```
- **Suggested fix direction:** Check `assert_period_allows_money_amend(session.company, session.counted_on or _tz.localdate())` and pass `movement_date=session.counted_on or _tz.localdate()` to `post_movement`.
- **Test to add:** `test_stock_count_post_stamps_counted_on_as_movement_date_and_checks_counted_period`
- **Twin check:** Sales/Purchase equivalent — invoice complete uses `invoice.invoice_date`, not today.

---

### STK-011 — `StockAdjustmentPage` live balance and confirmation dialog pick first batch from another lot, misleading operators
- **Module:** Stock/Godown -> Stock Adjustment UI
- **Location:** `web/src/pages/inventory/StockAdjustmentPage.tsx:80-87, 155-164`
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** In `StockAdjustmentPage.tsx:80-87`:
  ```typescript
  const currentStockEntry = selectedProduct
    ? (stockQuery.data ?? []).find(
        (s) =>
          Number(s.product) === Number(selectedProduct.id) &&
          (!selectedWarehouseId || Number(s.warehouse) === Number(selectedWarehouseId)),
      )
    : null;
  ```
  `listStock()` returns a separate entry for each `(product, warehouse, batch)` combination. Using `.find()` without matching the selected `batch` grabs the first batch entry in the list. When an operator selects Batch B with on-hand quantity 2, but Batch A has on-hand quantity 100, the UI displays:
  `Recorded balance 100` and calculates projected balance from 100. When reducing 5 units, the confirmation dialog displays:
  `Reduce stock by 5? Recorded balance 100 → 95`, misleading the operator that ample stock exists, even though Batch B will go negative!
- **Trigger / repro:** Create a product with Batch A (qty 100) and Batch B (qty 2). Open Stock Adjustment, select the product, select Batch B, and enter Reduce 5. Observe the confirmation prompt.
- **Consequence:** Operators are misled by false on-hand numbers in adjustment confirmations, resulting in unexpected negative stock warnings or rejections.
- **Code evidence:** `web/src/pages/inventory/StockAdjustmentPage.tsx:80-87`:
  ```typescript
  const currentStockEntry = selectedProduct
    ? (stockQuery.data ?? []).find(
        (s) =>
          Number(s.product) === Number(selectedProduct.id) &&
          (!selectedWarehouseId || Number(s.warehouse) === Number(selectedWarehouseId)),
        // batch is completely omitted!
      )
    : null;
  ```
- **Suggested fix direction:** Include `(!selectedBatchId || Number(s.batch) === Number(selectedBatchId))` in the `.find()` predicate.
- **Test to add:** `test_stock_adjustment_page_matches_selected_batch_balance`
- **Twin check:** n/a.

---

### STK-012 — `StockTransfer` lacks in-transit status and non-binding DRAFT does not reserve stock
- **Module:** Stock/Godown -> Stock Transfer
- **Location:** `backend/inventory/models.py:214-226` & `backend/inventory/services.py:1320-1340`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** `StockTransfer.Status` only defines `DRAFT`, `COMPLETED`, and `CANCELLED`.
  1. There is no intermediate `IN_TRANSIT` (goods in transit) state. In real-world multi-godown distribution, transfers between branches take hours or days. Completing the transfer instantaneously debits source and credits destination, making goods instantly available for sale at the destination godown while still physically on a truck.
  2. `DRAFT` transfers hold zero reservation. If a draft transfer is prepared for 10 units, another cashier or operator can sell those 10 units. When the driver departs and the transfer is completed, it fails under `BLOCK` or forces the source godown negative under `WARN`.
- **Trigger / repro:** Create draft transfer for all remaining stock at Godown A. Sell the stock on an invoice. Attempt to complete the transfer.
- **Consequence:** Transfer dispatch cannot be tracked independently of receipt; multi-godown merchants face race conditions between drafts and cash sales.
- **Code evidence:** `backend/inventory/models.py:214-217`:
  ```python
  class Status(models.TextChoices):
      DRAFT = "DRAFT"
      COMPLETED = "COMPLETED"
      CANCELLED = "CANCELLED"
  ```
- **Suggested fix direction:** Add an `IN_TRANSIT` status (posting `TRANSFER_OUT` on dispatch and `TRANSFER_IN` on arrival), or reserve available stock when a transfer enters pending/draft status.
- **Test to add:** `test_stock_transfer_in_transit_state_flow`
- **Twin check:** n/a.

---

### STK-013 — Frontend `StockTransferPage` ignores negative-stock `warnings`, allowing godowns to go negative silently
- **Module:** Stock/Godown -> Stock Transfer UI
- **Location:** `web/src/pages/phase/InventoryPhasePages.tsx:205-210` & `backend/inventory/services.py:1342-1346`
- **Type:** Silent-failure
- **Severity:** Medium
- **What's wrong:** In `backend/inventory/services.py:1342`, `StockTransferService.complete` checks `InventoryService.check_negative_stock` and returns a list of warnings (e.g. `Stock for 'Widget' in godown 'Main' will go negative (available 2)`). The API endpoint returns `{ ...transfer, warnings: [...] }`.
  However, in `InventoryPhasePages.tsx:205-210`, the `complete` mutation's `onSuccess` callback does not check for or display `data.warnings`. It immediately resets errors and closes:
  `onSuccess: () => { setError(''); void qc.invalidateQueries({ queryKey: ['transfers'] }); }`.
  The operator is given zero feedback that the transfer resulted in an overdrawn godown.
- **Trigger / repro:** Set `negative_stock_policy = "WARN"`. Transfer 10 units from a godown that only has 2 units. Complete the transfer in the web UI.
- **Consequence:** The transfer succeeds silently. The operator is never warned that the source godown has been driven negative.
- **Code evidence:** `web/src/pages/phase/InventoryPhasePages.tsx:205-210`:
  ```typescript
  onSuccess: () => {
    setError('');
    void qc.invalidateQueries({ queryKey: ['transfers'] });
  },
  ```
- **Suggested fix direction:** In `onSuccess`, check if `result.warnings?.length > 0` and display a prominent warning toast or dialog with the returned messages.
- **Test to add:** `test_stock_transfer_page_displays_returned_negative_stock_warnings`
- **Twin check:** Invoice complete surfaces warnings in an alert banner; `StockTransferPage` omitted it.

---

### STK-014 — `WarehouseViewSet` and Inventory `APIView` endpoints drop `SubscriptionWritesAllowed` gate
- **Module:** Stock/Godown -> Permissions & Subscription
- **Location:** `backend/inventory/views.py:302-306, 151, 223, 540`
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** `CompanyScopedViewSet.get_permissions()` enforces `SubscriptionWritesAllowed()` on all write actions.
  In `backend/inventory/views.py:302`, `WarehouseViewSet` overrides `get_permissions()`:
  ```python
  def get_permissions(self):
      if getattr(self, "action", None) in ("list", "retrieve"):
          return [IsAuthenticated(), HasCompany(), CanViewInventorySurfaces()]
      return [IsAuthenticated(), HasCompany(), CanManageInventory()]
  ```
  It does not call `super().get_permissions()`. Therefore, `SubscriptionWritesAllowed()` is dropped.
  Furthermore, `AdjustmentView`, `OpeningStockView`, and `ExpiryAlertsView` inherit from standard `rest_framework.views.APIView` and declare `permission_classes = [IsAuthenticated, HasCompany, CanManageInventory]`, omitting `SubscriptionWritesAllowed`.
- **Trigger / repro:** Expire or suspend a tenant's subscription. Authenticate as that tenant and send `POST /api/v1/inventory/warehouses/`, `POST /api/v1/inventory/adjustments/`, or `POST /api/v1/inventory/alerts/expiry/`.
- **Consequence:** Delinquent or expired tenants whose accounts should be read-only can continue to create godowns, adjust inventory, and write off stock.
- **Code evidence:** `backend/inventory/views.py:302-306`:
  ```python
  def get_permissions(self):
      if getattr(self, "action", None) in ("list", "retrieve"):
          return [IsAuthenticated(), HasCompany(), CanViewInventorySurfaces()]
      return [IsAuthenticated(), HasCompany(), CanManageInventory()]
  ```
- **Suggested fix direction:** Include `SubscriptionWritesAllowed()` in `WarehouseViewSet.get_permissions()` and in the `permission_classes` of `AdjustmentView`, `OpeningStockView`, and `ExpiryAlertsView`.
- **Test to add:** `test_inventory_adjustments_and_warehouse_mutations_blocked_when_subscription_locked`
- **Twin check:** Sales and Purchase viewsets properly inherit or declare `SubscriptionWritesAllowed`.

---

### STK-015 — Stock count conflict resolution `KEEP_SERVER` silently discards physical floor counts while marking session POSTED
- **Module:** Stock/Godown -> Godown Conflict & Stock Count
- **Location:** `backend/inventory/views.py:698-701` & `web/src/pages/inventory/StockConflictModal.tsx:45`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** In `StockCountSessionViewSet.post`:
  When a 409 conflict occurs (e.g. intervening sales or receipts changed the stock on hand since the count began), the modal presents "Keep Server" (emphasized primary button) and "Keep Local".
  If the operator chooses `KEEP_SERVER`, line 700 executes:
  `if conflicts and current != line.system_qty and resolve == "KEEP_SERVER": continue`.
  The backend completely skips posting any adjustment for that line. It then marks `session.status = POSTED`.
  The session appears in the UI and reports as `POSTED`, but the physical count was discarded. If 5 items were counted on the shelf and server had 8, choosing `KEEP_SERVER` abandons the count without warning, leaving 8 on the books while recording the audit as completed.
- **Trigger / repro:** Create count session for 10 units. Count 5. Before posting, sell 2 on an invoice (server becomes 8). Post count, encounter 409, select `KEEP_SERVER`.
- **Consequence:** The physical variance (-3) is never posted to the ledger, but the audit is stamped as `POSTED`. Operators believe the floor inventory was reconciled when it was actually silently dropped.
- **Code evidence:** `backend/inventory/views.py:698-701`:
  ```python
  # CR-056: KEEP_SERVER skips adjustment for drifted lines (abandons
  # the physical count for those SKUs) while still marking POSTED.
  if conflicts and current != line.system_qty and resolve == "KEEP_SERVER":
      continue
  ```
- **Suggested fix direction:** When `KEEP_SERVER` is selected for conflicted lines, either mark the session with a status indicating partial resolution (e.g. `PARTIALLY_POSTED` / `RECOUNT_REQUIRED`), or update the count lines to reflect that the physical count was discarded.
- **Test to add:** `test_stock_count_keep_server_records_audit_exclusion_of_drifted_lines`
- **Twin check:** n/a.

---

### STK-016 — Warehouses UI lacks action to set or promote a godown as default
- **Module:** Stock/Godown -> Warehouse UI
- **Location:** `web/src/pages/phase/InventoryPhasePages.tsx:42-135`
- **Type:** Broken-feature
- **Severity:** Low
- **What's wrong:** The backend supports designating a warehouse as default (`is_default = True`), and `WarehouseSerializer` handles clearing existing defaults. However, in `InventoryPhasePages.tsx:42-135` (`WarehousesPage`), the "Add godown" dialog only accepts `Name` and `Code` inputs. In the data table rows, there is no action button or toggle to "Set as default".
- **Trigger / repro:** Create a new warehouse in the web UI. Try to set it as the company's default godown.
- **Consequence:** Users cannot change their default godown from the frontend application; they must contact support or use raw API calls.
- **Code evidence:** `web/src/pages/phase/InventoryPhasePages.tsx:113-121`:
  ```typescript
  <DialogContent>
    <Stack spacing={2} sx={{ mt: 1 }}>
      <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
      <TextField label="Code" value={code} onChange={(e) => setCode(e.target.value)} />
    </Stack>
  </DialogContent>
  ```
- **Suggested fix direction:** Add a "Set as default" action button on active non-default warehouse rows in `WarehousesPage`, which triggers `api.updateWarehouse(id, { isDefault: true })`.
- **Test to add:** `test_warehouses_page_can_set_default_godown`
- **Twin check:** n/a.

---

### STK-017 — No background job or telemetry to detect drift between `StockBalance.on_hand` and `Sum(StockMovement.quantity)`
- **Module:** Stock/Godown -> Integrity & Monitoring
- **Location:** `backend/inventory/services.py:1124` & `backend/inventory/management/commands/rebuild_stock_balances.py`
- **Type:** Improvement
- **Severity:** Low
- **What's wrong:** `StockBalance` is explicitly a derived cache (§12.1), rebuildable from `StockMovement`. While `post_movement` atomically maintains them under a row lock, any direct DB intervention, partial crash, or edge bug can introduce silent drift. A management command `rebuild_stock_balances` exists, but there is no periodic Celery health check or automated telemetry report that checks `StockBalance.on_hand == Sum(StockMovement.quantity)`.
- **Trigger / repro:** Introduce a 1-unit balance drift via manual DB update or corrupted import. Observe if any system alert fires.
- **Consequence:** Drift remains undetected in production until an operator notices a negative stock error or runs physical inventory count.
- **Code evidence:** `backend/inventory/services.py:1125-1129`:
  > *"CR-054: drift repair is ops/API via this helper / `rebuild_stock_balances`; there is no scheduled balance↔movement health check yet."*
- **Suggested fix direction:** Add a nightly Celery task (or Prometheus metric) that asserts `StockBalance.on_hand == Sum(StockMovement.quantity)` across all active tenants and flags discrepancies.
- **Test to add:** `test_nightly_integrity_task_detects_stock_balance_movement_drift`
- **Twin check:** Accounting has `backfill_missing_postings` / reconciliation checks; inventory needs similar automated verification.

---
