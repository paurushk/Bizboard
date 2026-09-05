# BizBoard — Deep Line-by-Line Code Review

**Date:** 25 August 2026  
**Scope:** Current workspace source (not prior review tickets). Backend Django/DRF, frontend React/TypeScript, mobile Capacitor wrapper, CI, config.  
**Method:** Every production module was read (models, serializers, views, services, pages, API clients, tax/money/GST utils). Migrations and generated lockfiles were not treated as product bugs. Critical/High items below were re-opened in the live files and quoted.

This document replaces earlier review notes. Claims that did not hold in current source (for example frontend/backend `extractStateCode` divergence — both now require a 15-character GSTIN or an exact 2-digit code in `VALID_GST_STATE_CODES`) are **not** repeated.

## Remediation status (25 August 2026)

All P0 items and the actionable P1 money/stock/auth/GST items from this review have been implemented in the live tree. Remaining P2/P3 items that are product-scope (full CRM pipeline, live Tally sync, Account Aggregator as a real FIU, GSTR nil/exempt split, insights as certified forecasts) stay honestly scoped in README; they are not silent stubs on claimed MVP paths.

| ID | Status |
| :--- | :--- |
| P0-01 purchase amend import | Fixed (`snapshot_unit_fields` module import) |
| P0-02 SO → challan reservations / CONVERTED | Fixed |
| P0-03 damaged sales-return cancel | Fixed |
| P0-04 cash-flow GL 1100/1500 | Fixed |
| P0-05 B2CL ₹1L from 1 Aug 2024 | Fixed (`b2cl_threshold_for`) |
| P0-06 Tally SSRF | Fixed (server `TALLY_URL` + host allowlist) |
| P0-07 WO complete WIP JE | Fixed (skip JE when `issue_cost==0`) |
| P0-08 subscription gate vs cookie JWT | Fixed (middleware order + cookie auth) |
| P0-09 invite OTP before accept | Fixed (`is_active=False` until accept) |
| P0-10 bill import qty/GST invent | Fixed (reject blank on commit) |
| P0-11 void_rows one lot per SKU | Fixed (reverse all lots) |
| P0-12 opening raw batch ID | Fixed (resolve BatchLot) |
| P0-13 opening uniqueness outside lock | Fixed (recheck after `select_for_update`) |
| P0-14 bulk opening cost/guards | Fixed (`tracks_inventory` + `opening_unit_cost`) |
| P1-01..P1-07 source_item / cess extract | Fixed |
| P1-09 TCS compute | Computed from `tcs_rate` on complete; amount read-only |
| P1-10 supplier payment TDS GL | Posted to 2265 |
| P1-11 payroll salary TDS | `tds_rate` / `tds_amount` + GL 2265 |
| P1-12 journal reverse keeps POSTED | Fixed |
| P1-19 AFTER_TAX discount in GSTR expected | Fixed |
| P1-18 GSTR-9 outward cess | Included |
| P1-21 idempotency in-flight TTL | 15 minutes then retry |
| P1-23 Celery RLS | `company_id` required; no pre-GUC SELECT |
| P1-33 forgot password | Request/confirm API + UI |
| P1-36 POS inclusive row totals | Inclusive extract + cess on POS lines |
| P1-41 billing fail-open | Re-raises `APIException` |
| P1-42 public `/metrics` | Bearer `METRICS_TOKEN` |

---

## 1. Executive summary

| Severity | Count | Meaning |
| :--- | ---: | :--- |
| **Critical (P0)** | 14 | Wrong money/stock/GST, crash on a live path, or a real auth/tenant hole |
| **High (P1)** | 28 | Broken conversion, silent tax/stock drift, ACL bypass, or incomplete statutory path |
| **Medium (P2)** | 32 | Partial feature, race, stub sold as real, or operator-facing inconsistency |
| **Low (P3)** | 22 | Maintainability, copy, logging, dead branches |
| **Total** | **96** | |

**Highest-impact themes**

1. **Money and GST** — inclusive price extract ignores specific cess; bill import invents qty=1 and GST=18%; GSTR-1 still uses the old ₹2.5L B2CL cut; GSTR-9 drops cess; AFTER_TAX invoice discount strips invoices from GSTR sections.
2. **Stock** — confirmed sales order → challan never releases reservations or marks the order converted (double issue risk); damaged return cancel does not reverse scrap movements; opening-stock race and raw batch-ID crash; import void keeps only one lot per SKU.
3. **Auth / tenancy** — subscription write gate runs before cookie JWT auth; new-user invite membership is active immediately and OTP can log in before accept; Tally HTTP push takes a client URL (SSRF).
4. **Partial products** — forgot-password UI lies; GSTR-4 is empty JSON; payroll has no salary TDS; TCS fields are writable but never computed; purchase debit notes have no `source_item`.

---

## 2. Critical (P0)

### P0-01 — Completed purchase amend crashes (`NameError`)

- **Category:** Bug  
- **Where:** `backend/purchases/services.py` — `_build_purchase_items` imports `snapshot_unit_fields` locally (line 47); `_update_purchase_items_in_place` calls it at line 126 with **no import**. Module top (lines 1–19) does not import it either.  
- **Evidence:**

```47:47:backend/purchases/services.py
    from core.services.uqc import snapshot_unit_fields
```

```126:126:backend/purchases/services.py
        snap = snapshot_unit_fields(product, line)
```

- **Why it is real:** Any owner `confirm_amend` that edits lines on a **completed** purchase hits `NameError` and rolls back. H9 price-correct is unusable.  
- **Fix:** Import `snapshot_unit_fields` at module level (or inside `_update_purchase_items_in_place`).

---

### P0-02 — Confirmed sales order → challan leaves reservations and stays convertible

- **Category:** Broken flow / Bug  
- **Where:** `backend/sales/notes_services.py` `convert_sales_order_to_challan` (473–514) vs `convert_sales_order` (427–468) and `cancel_sales_order` (524–528).  
- **Evidence:** Invoice convert and cancel both call `InventoryService.release_reservation` and (for invoice) set `order.status = CONVERTED`. Challan convert only creates a challan and copies lines — **no reservation release, no status change**.  
- **Why it is real:** Confirmed SO holds stock. Completing the challan (when stock-on-challan is on) posts SALE. The order is still `CONFIRMED`, so it can still convert to an invoice and post SALE again. Reservations stay until cancel.  
- **Fix:** On challan convert: release reservations if `CONFIRMED`; mark `CONVERTED` (or a dedicated status); block invoice convert when a stock-posted challan exists.

---

### P0-03 — Damaged sales-return cancel corrupts stock and serials

- **Category:** Bug / Stock  
- **Where:** `backend/sales/cogs_service.py` 188–201 (complete scraps via `reference_type="sales_return_damaged"`); `backend/sales/return_service.py` 203–254 (cancel).  
- **Evidence:** Cancel loads only `movement_type=SALES_RETURN` / `reference_type="sales_return"`. Damaged complete also posts `ADJUSTMENT` scrap. Serial restore always does `AVAILABLE → SOLD`; damaged units are `SCRAPPED`.  
- **Why it is real:** Cancel re-issues the restored qty (net −qty again) and never un-scraps. Serial transition fails or leaves wrong state.  
- **Fix:** Reverse `sales_return_damaged` adjustments; `SCRAPPED → SOLD` for damaged, `AVAILABLE → SOLD` for sellable; restore FIFO peels symmetrically.

---

### P0-04 — Cash-flow report queries GL codes that are not on the chart

- **Category:** Bug  
- **Where:** `backend/accounting/reports.py` 142–154 vs `backend/accounting/services.py` `CHART` 13–21.  
- **Evidence:** Report filters `code__in=["1110", "1120"]`. Seeded chart is **1100 Cash** and **1500 Bank**.  
- **Why it is real:** Direct cash-flow inflows/outflows stay zero for every tenant using the default chart.  
- **Fix:** Query `["1100", "1500"]` (and any bank-linked control accounts).

---

### P0-05 — GSTR-1 B2CL threshold is still ₹2.5 lakh (law is ₹1 lakh from 1 Aug 2024)

- **Category:** Bug / GST  
- **Where:** `backend/reporting/gst_returns.py` 38–40; used in `gst_returns_sections.py` 134–147.  
- **Evidence:**

```38:40:backend/reporting/gst_returns.py
# Notification 12/2024-CT: interstate B2C large threshold ₹1,00,000 from 1 Aug 2024.
# GAP-004: B2CL is inter-state unregistered supplies above ₹2.5 lakh (post-2021).
B2CL_THRESHOLD = Decimal("250000")
```

- **Why it is real:** Interstate B2C invoices ₹1L–₹2.5L go to B2CS instead of invoice-wise B2CL. The comment already cites the new notification.  
- **Fix:** Date-aware threshold: ₹2.5L before 1 Aug 2024, ₹1L after.

---

### P0-06 — Tally HTTP push accepts arbitrary `base_url` (SSRF)

- **Category:** Security  
- **Where:** `backend/integrations/views.py` 165–175; `integrations/tally/adapter.py` `post_tally_xml` ~529–540.  
- **Evidence:** `base_url = request.data.get("base_url") or request.data.get("baseUrl")` is passed into `requests.post`.  
- **Why it is real:** An authenticated export-capable user can make the server POST XML to any URL (cloud metadata, LAN, etc.).  
- **Fix:** Ignore client URL; use server `TALLY_URL` only, or a strict allowlist (localhost / configured Tally host) blocking link-local and metadata IPs.

---

### P0-07 — Work-order complete can credit WIP that was never debited

- **Category:** Bug / GL  
- **Where:** `backend/manufacturing/services.py` 149–187; `backend/accounting/services.py` 808–849.  
- **Evidence:** `post_work_order_release` no-ops when `amt <= 0`. Complete still posts `Dr 1400 / Cr 1450` using `issue_cost or (unit_cost * wo.qty)` where `unit_cost` falls back to component **purchase prices**.  
- **Why it is real:** WIP 1450 is credited with no matching debit; FG inventory is inflated vs actual issue cost.  
- **Fix:** If `issue_cost == 0`, skip complete JE (or post release+complete from the same valuation). Never invent WIP from master purchase prices alone.

---

### P0-08 — Subscription write gate is a no-op for cookie-JWT (production path)

- **Category:** Security / Broken flow  
- **Where:** `backend/config/settings.py` MIDDLEWARE 143–155; `backend/billing/middleware.py` 19–27; `backend/core/middleware.py` `PostgresRlsMiddleware` 95–105.  
- **Evidence:** `SubscriptionWriteGateMiddleware` runs **before** `PostgresRlsMiddleware`. Production auth is cookie JWT, which RLS middleware attaches. At the gate, `request.user` is still anonymous → gate returns immediately. DRF `SubscriptionWritesAllowed` (`billing/permissions.py` 23–31) also **fail-opens** on any `get_company_user` exception (including company-header conflict).  
- **Why it is real:** Suspended / trial-expired tenants are not blocked on the cookie path. Many account PATCH endpoints never see the DRF permission.  
- **Fix:** Authenticate cookie JWT in the billing middleware (same as RLS), or move the gate after JWT; fail-closed on company-context errors; attach the permission to all mutating company APIs.

---

### P0-09 — New-user invite activates membership before accept; phone enables OTP login

- **Category:** Security  
- **Where:** `backend/accounts/views.py` 910–927 vs existing-user path 875–877.  
- **Evidence:** Existing users get `is_active=False`. New users: `User.objects.create_user(..., phone=data.get("phone", ""))` then `CompanyUser.objects.create(...)` with default **active** membership. `VerifyOtpView` issues JWTs for active users with that phone — no accept/password required.  
- **Why it is real:** Invitee (or anyone who can receive the OTP) can operate as staff before they accept the invite.  
- **Fix:** Create new-user memberships `is_active=False` until accept; ignore/strip phone until accept; block OTP when password is unusable or membership inactive.

---

### P0-10 — Bill import commit invents quantity 1 and GST 18%

- **Category:** Bug / Data integrity  
- **Where:** `backend/imports/services.py` `_normalize_gst_rate` 264–266; commit ~1890–1895. Preview path `_preview_bill_line` 283–289 explicitly **avoids** inventing those values.  
- **Evidence:** Commit uses `_as_decimal(line.get("quantity"), "1")` and `_normalize_gst_rate` default `"18"`.  
- **Why it is real:** Blank OCR fields become a 1-qty / 18% purchase (or sales) draft and can seed new products. Preview honesty is discarded at commit.  
- **Fix:** Reject included lines that lack qty/GST; never default those on commit.

---

### P0-11 — Import `void_rows` keeps only one movement per SKU

- **Category:** Bug  
- **Where:** `backend/imports/services.py` 1333–1354.  
- **Evidence:** `by_sku = {(m.product.sku or "").casefold(): m for m in movements}` — later lots overwrite earlier ones.  
- **Why it is real:** Multi-godown / multi-lot openings for one SKU: void reverses one movement and leaves the rest (and FIFO layers). Product cleanup may still run.  
- **Fix:** Index by `(sku, warehouse_id, batch_id)` or reverse **all** movements for that SKU.

---

### P0-12 — Opening-stock API passes raw `batch` ID into a BatchLot-shaped argument

- **Category:** Bug / Broken flow  
- **Where:** `backend/inventory/serializers.py` 54–59 (`IntegerField`); `backend/inventory/views.py` 150–157 vs AdjustmentView 109–115 which **resolves** the ID. `post_opening` (`inventory/services.py` 166–173) uses `if batch is None` then `batch.expiry_date`.  
- **Why it is real:** Client sending `"batch": 12` skips `get_or_create_batch` and then `AttributeError` on `int.expiry_date`, or takes a wrong path. Warehouse works only because `resolve_warehouse` accepts IDs.  
- **Fix:** Resolve `batch` like AdjustmentView (company + product scoped) before `post_opening`.

---

### P0-13 — Concurrent duplicate `OPENING_STOCK` (check outside lock)

- **Category:** Bug / Race  
- **Where:** `backend/inventory/services.py` 78–93 (exists check) then 95–105 (`select_for_update` on balance).  
- **Why it is real:** Two concurrent opening posts can both pass the uniqueness check and create two openings for the same SKU × godown × lot.  
- **Fix:** Recheck after locking the balance, or add a partial unique constraint on opening movements.

---

### P0-14 — Bulk opening import skips tax-exclusive cost and inventory guards

- **Category:** Bug  
- **Where:** `backend/inventory/services.py` `post_opening_movements_batch` ~209–327; called from `imports/services.py` ~889–895.  
- **Why it is real:** Writes `unit_cost` as supplied; does not call `opening_unit_cost` / inclusive→exclusive; does not call `tracks_inventory`. Inclusive purchase prices inflate FIFO/WAVG layers vs the item-stock spec.  
- **Fix:** Run the same validation/cost path as `post_opening` per row.

---

## 3. High (P1)

### P1-01 — CN/DN `source_item` not bound to the note’s invoice

- **Where:** `backend/sales/services.py` 66–90.  
- **Evidence:** Lookup is `SalesItem.objects.get(pk=..., invoice__company_id=company_id)` only.  
- **Impact:** A credit note on invoice A can inherit price/GST/HSN from a line on invoice B. Headroom checks stay on A.  
- **Fix:** Require `source_item.invoice_id == note.sales_invoice_id` (and product match).

---

### P1-02 — Auto return→CN maps `source_item` by product (first line wins)

- **Where:** `backend/sales/return_service.py` 158–175; `backend/purchases/services.py` 933–950.  
- **Impact:** Duplicate SKUs with different rates collapse. Wrong GSTR lineage.  
- **Fix:** Return lines must carry invoice line id; allocate per line.

---

### P1-03 — Mixed-condition purchase-return cancel misses damaged adjustments

- **Where:** `backend/purchases/services.py` 838–851, 991–1013.  
- **Impact:** Sellable `PURCHASE_RETURN` moves exist → damaged `ADJUSTMENT` reverse is skipped. Damaged stock never comes back.  
- **Fix:** Reverse all movements with `reference_id` of the return, including DAMAGED adjustments.

---

### P1-04 — UOM `base_quantity` used on complete, not on completed-amend stock deltas

- **Where:** Purchase complete 569–578 vs amend 279–310; sales `_sale_batches` 266–268 vs amend 410–441.  
- **Impact:** Alternate-unit docs drift stock if any qty-delta path runs (API may block qty today; service still diverges).  
- **Fix:** Always delta with `base_quantity(...)`.

---

### P1-05 — Sales CN/DN customer not validated against invoice customer

- **Where:** `backend/sales/phase1_serializers.py` (no pair check). Sales returns do enforce it (`serializers.py` 429–434).  
- **Impact:** AR can post to the wrong customer while referencing another invoice.

---

### P1-06 — Purchase return supplier not validated against linked bill supplier

- **Where:** `backend/purchases/serializers.py` 309–335.  
- **Impact:** Mismatched AP + auto credit note.

---

### P1-07 — Inclusive extractor ignores specific `cess_amount` (BE + FE)

- **Where:** `backend/core/services/billing.py` 209–234 (`rate = gst_rate + cess_rate` only); `_apply_line_tax` 194–201 uses per-unit `cess_amount` when set. `web/src/utils/tax.ts` 165–182 does not even take `cessRate`.  
- **Impact:** Inclusive MRP with cess (ad-valorem or specific) previews and posts different taxable/tax. POS and invoice editors both affected.  
- **Fix:** Include cess rate and `qty * cess_amount` in the inclusive denominator; pass cess through FE helpers.

---

### P1-08 — `PurchaseDebitNoteItem` has no `source_item`; remove-guard will `FieldError`

- **Where:** `backend/purchases/models.py` 302–309; `purchases/services.py` 154–157 filters `PurchaseDebitNoteItem.objects.filter(source_item_id__in=...)`.  
- **Impact:** DN lineage incomplete; line-removal path crashes.

---

### P1-09 — TCS fields on sales invoices are writable but never computed or posted

- **Where:** `backend/sales/models.py` 136–138; serializers expose them; `sales/services.py` has no TCS logic. Receivable uses `grand_total + tcs_amount`.  
- **Impact:** Manual `tcs_amount` inflates AR with no GL/GSTR support.

---

### P1-10 — Supplier-payment TDS stored but not posted to GL

- **Where:** `backend/payments/services.py` 233–266; `accounting/services.py` `post_supplier_payment` 643–655 posts `Dr 1250 / Cr bank` for `payment.amount` only.  
- **Impact:** TDS payable (2265) never credited; AP not cleared by the TDS leg.

---

### P1-11 — Payroll has no salary TDS (section 192)

- **Where:** `backend/payroll/services.py` `compute_statutory` 70–99 (PF/ESI/PT only); admin copy says not full statutory payroll.  
- **Impact:** Module looks like payroll; 2265 never moves for salaries.

---

### P1-12 — Journal reverse marks original `REVERSED` → drops from all GL reports

- **Where:** `backend/accounting/services.py` 868–887; reports filter `status=POSTED` (`reports.py` ~9).  
- **Impact:** Original-period TB/P&L/BS lose the original lines; only the later reversal remains. Cross-period void distorts prior P&L.  
- **Fix:** Keep original POSTED; add an opposite POSTED reversal (standard).

---

### P1-13 — Prefetch allocation totals ignore `reversed_at`

- **Where:** `backend/ledgers/services.py` 61–72, 180–183, 356–358, 650–654. Invoice outstanding **does** filter `reversed_at`.  
- **Impact:** After `reverse_allocation`, document-path unallocated / “advance” still counts reversed rows.

---

### P1-14 — Document-path supplier statement includes VOIDED payments

- **Where:** `ledgers/services.py` 650–664 — `SupplierPayment.objects.filter(company=..., supplier=...)` with no status filter. Receipts correctly use `POSTED`.  
- **Impact:** Voided payments still reduce AP on the statement.

---

### P1-15 — Bank AA match is amount-only

- **Where:** `backend/banking/services.py` 11–38. First receipt within ±tolerance; no UTR/date/party; no `select_for_update`.  
- **Impact:** Two ₹1,500 receipts bind the wrong one.

---

### P1-16 — GL bank recon `match` does not verify amounts

- **Where:** `backend/accounting/views.py` 202–221.  
- **Impact:** Any unreconciled journal line can be linked to any bank line.

---

### P1-17 — Books health misses purchase notes

- **Where:** `accounting/services.py` 983–1040 (sales CNs/DNs checked; purchase notes not). Backfill command already knows purchase notes.  
- **Impact:** Period close can pass with missing purchase-note JEs.

---

### P1-18 — GSTR-9 `outward_tax` omits cess

- **Where:** `backend/reporting/gst_returns.py` 1367–1374 — sums CGST+SGST+IGST only.  
- **Impact:** FY worksheet understates outward tax for cess commodities.

---

### P1-19 — AFTER_TAX invoice discount excludes invoices from GSTR sections

- **Where:** `reporting/gst_returns.py` 133–135 `invoice_value_mismatch` returns True whenever AFTER_TAX discount ≠ 0.  
- **Impact:** Valid invoices with after-tax discount disappear from B2B/B2C sections.

---

### P1-20 — Company PATCH does not require GSTIN for COMPOSITION

- **Where:** `backend/accounts/serializers.py` `CompanySerializer.validate` 238–255 vs register 108–116. Register requires checksum GSTIN for REGULAR **and** COMPOSITION. PATCH only when `REGULAR`.  
- **Impact:** Owner can set COMPOSITION with blank/invalid GSTIN.

---

### P1-21 — Idempotency in-flight rows can stick forever

- **Where:** `backend/core/idempotency.py` 58–94, 97–108. `begin_record` inserts `status_code=0`; crash without `release_record` → permanent `IdempotencyInFlightError`.  
- **Fix:** TTL / sweeper; `finally: release_record` on all call sites.

---

### P1-22 — Invite accept is not atomic on JTI consume

- **Where:** `backend/accounts/views.py` 724–758. JTI read → password/membership update → `consumed_at` set; no `select_for_update`.  
- **Impact:** Double-accept race.

---

### P1-23 — Celery RLS: tenant lookup runs before GUC is set

- **Where:** `backend/config/celery.py` 82–97, 26–56. When `company_id` missing, SELECT invoice/notification by PK **before** `set_rls_company`. With RLS on and empty GUC, lookup returns nothing.  
- **Fix:** Require `company_id` on every tenant task; never resolve company from PK under empty GUC.

---

### P1-24 — Company `feature_flags` can turn env-disabled modules ON

- **Where:** `backend/core/services/feature_flags.py` 36–51. Overrides **replace** env flags. Plan AND only applies if a plan dict exists.  
- **Impact:** Writer of `Company.feature_flags` can unlock Manufacturing/Payroll/CRM when env says off.

---

### P1-25 — Import auto-creates free-text units (violates UQC rule)

- **Where:** `backend/imports/services.py` 951–987; `masters/serializers.py` 135–141.  
- **Impact:** `MILLILITRE` becomes a junk unit instead of `ML`. Spec: map UQC or fail.

---

### P1-26 — Opening uniqueness on import is product-level, not SKU×godown×lot

- **Where:** `backend/imports/services.py` 220–229, 807–814.  
- **Impact:** Second godown/lot for the same product is blocked even when `post_movement` would allow it.

---

### P1-27 — Opening `as_of` on extra sheets ignored on commit

- **Where:** `imports/services.py` 1098–1121 — sheet has `as_of`; `_post_extra_opening` never passes it.  
- **Impact:** Backdated openings post as “today”.

---

### P1-28 — Low-stock alerts are per balance row, not company-wide

- **Where:** `backend/inventory/views.py` 178–196.  
- **Impact:** Split stock across godowns false-alerts vs spec (compare company-wide available to reorder).

---

### P1-29 — Serial status API bypasses stock ledger

- **Where:** `backend/inventory/views.py` 270–286 — direct `AVAILABLE → SOLD` / `SCRAPPED` with no `StockMovement`.  
- **Impact:** Serial state drifts from on-hand.

---

### P1-30 — Positive adjustment with no `unit_cost` → FIFO layer @ 0

- **Where:** `inventory/serializers.py` 46–51; `services.py` 354–360.  
- **Impact:** Later COGS understated.

---

### P1-31 — Qty formula forces integer billed qty

- **Where:** `backend/imports/qty_formula.py` 142–154 `quantize(Decimal("1"))`.  
- **Impact:** Kg/Ltr/partial packs cannot reconcile.

---

### P1-32 — FEFO remainder dumped onto first lot when negative stock allowed

- **Where:** `backend/sales/services.py` 312–317.  
- **Impact:** Over-issues an arbitrary lot; COGS/batch identity wrong.

---

### P1-33 — Forgot-password page is a non-functional stub

- **Where:** `web/src/pages/ForgotPasswordPage.tsx` 18–26, 53–57. No API call; success copy claims a reset link was sent.  
- **Impact:** Users believe recovery happened. Login remains impossible without owner intervention.

---

### P1-34 — Expiry write-off UI on view-only inventory ACL

- **Where:** `web/src/App.tsx` 356–361 (`canViewInventorySurfaces`); write-off mutates via `writeOffExpiry`. API POST uses `CanManageInventory` (good) but UI still offers the action.  
- **Impact:** View-only users get a failing destructive control; if API perms ever loosen, write-off is already exposed.

---

### P1-35 — Sales returns (and quotations) create on view-only routes

- **Where:** `App.tsx` 311–314; `SalesReturnsPage.tsx` 78–97. Nav uses `canCreateSales`; URL does not.  
- **Impact:** Financial-report users without create-sales can still POST create/complete return.

---

### P1-36 — POS cart **row** totals ignore inclusive mode (footer is correct)

- **Where:** `web/src/pages/pos/PosPage.tsx` 220–244 vs 756–763. Submit still sends `priceMode` / inclusive extract.  
- **Impact:** Cashier sees inflated line amounts vs tender total.

---

### P1-37 — Opening import: batch + serial both enabled via extra sheets

- **Where:** `imports/services.py` 1078–1097 — no XOR. Spec §4/§5: one tracking mode.  
- **Impact:** Invalid product matrix on commit.

---

### P1-38 — Extra-sheet validation incomplete vs `post_opening`

- **Where:** `imports/services.py` 662–720. Missing qty>0, expiry ≥ as-of, duplicate serials, inactive godown, expired opening reject.  
- **Impact:** Bad rows reach commit then fail or post junk.

---

### P1-39 — PRODUCTS `void_rows` never marks job `VOIDED`

- **Where:** `imports/services.py` 1369–1372 — VOIDED only for `OPENING_STOCK`.  
- **Impact:** Fully voided product imports stay `COMMITTED`; re-upload blocked.

---

### P1-40 — Category not imported / not auto-created

- **Where:** `imports/services.py` `_commit_products` 990–1028 never sets `category`. Spec §16 requires match/create.

---

### P1-41 — Billing permission fail-open on any `get_company_user` error

- **Where:** `backend/billing/permissions.py` 28–31. Combined with P0-08.  
- **Fix:** Re-raise `APIException` / company conflict; only fail-open for missing auth.

---

### P1-42 — Public `/metrics` with no auth

- **Where:** `backend/core/views.py` 292–304; mounted in `config/urls.py`.  
- **Fix:** Scrape token or network ACL.

---

## 4. Medium (P2)

### P2-01 — Confirmed SO can convert to challan repeatedly  
`convert_sales_order_to_challan` does not flip status → multiple challans from one SO.

### P2-02 — Quotation → order marks `CONVERTED` with no order FK  
`sales/services.py` ~1001–1004. Audit/UI cannot trace quotation→SO.

### P2-03 — Purchase return has no unique `(company, number)` constraint  
`purchases/models.py` 152–154 indexes only. Concurrent complete can collide.

### P2-04 — Purchase `RETURNED` invoices cannot be patched (including notes)  
Sales blocks `RETURNED` early; purchase always `set_items`, which rejects non-DRAFT/COMPLETED.

### P2-05 — CN/DN cancel skips GST period gate  
Complete calls `assert_period_allows_money_amend`; cancel does not.

### P2-06 — Sales return tax split ignores `company_gstin` / filing overlays  
`return_service.py` 37–45 uses live customer state vs invoice stamp → CGST/SGST vs IGST mismatch.

### P2-07 — Preview totals ignore `price_mode`, cess, seller GSTIN  
`sales/views.py` 167–216. Preview ≠ complete.

### P2-08 — Purchase credit notes: no persisted `additional_charges`  
`purchases/services.py` 929 sets a transient attribute. Re-edit drops charges. Sales CN has a real field.

### P2-09 — `rcm_cess` missing from purchase invoice serializer fields  
Model has it; serializer 63–64 omits it.

### P2-10 — Completed `set_items` lacks `select_for_update`  
Sales/purchase amend race on stock/totals.

### P2-11 — Purchase number-series peek ignores GSTIN series  
`purchases/views.py` 111–112 vs sales peek with `resolve_series_gstin`.

### P2-12 — Purchase create idempotency is cache-only  
Sales uses durable `begin_record`. Cache miss can duplicate drafts.

### P2-13 — Viewsets double-call `PostingService.post_note`  
Idempotent today; fragile if that changes.

### P2-14 — Foreign/import purchases hard-blocked  
`purchases/services.py` 452–468 — “not supported yet”. Fail-closed but incomplete vs product claims.

### P2-15 — Composition GSTR-4 is an empty stub  
`reporting/gstr2b.py` 153–161 `tables: {}`. CA pack still writes `gstr4-*.json`.

### P2-16 — TDS worksheet ignores payment-level TDS  
`reporting/tds_worksheets.py` 29–58 — purchase invoices only.

### P2-17 — Bank recon suggestions include voided supplier payments  
`payments/recon.py` 245–249.

### P2-18 — `reconciled_at` assigned a `date` into `DateTimeField`  
`accounting/views.py` 219.

### P2-19 — CRM is convert-only (amount 0)  
`crm/services.py`. Feature-flagged UI can look complete.

### P2-20 — Account Aggregator is scaffold + mock FIU  
`banking/` — consent store + weak match (P1-15).

### P2-21 — Tally is export dump, not sync  
Voucher XML is amount-only shells; unsafe if sold as live sync (plus P0-06).

### P2-22 — GSTR nil/exempt/non-GST unsplit; AT/TXPD rate unknown  
Documented honesty gaps; still easy to file if treated as GSTN-ready.

### P2-23 — Insights cashflow/health are heuristics  
`insights/services.py` 471–533 — disclaimer present; UI can imply certainty.

### P2-24 — `DocumentLineModel.quantity` has no lower bound  
`core/models.py` 75. Negative qty → negative taxable if a serializer lets it through.

### P2-25 — `DocumentSeries.get_or_create` race on first allocate  
`document_numbers.py` 112–118. IntegrityError not retried (unlike stock balances).

### P2-26 — Global `IntegrityError` → generic “duplicate” 400  
`core/exceptions.py` 46–60. FK/not-null failures look like duplicates.

### P2-27 — `assume_local_state_for_blank_party` defaults True  
Blank POS treated as intra-state. Wrong CGST/SGST vs IGST unless owner turns it off.

### P2-28 — e-Way adapter hard-fails all prod/staging without `GSP_CERTIFIED`  
IRP only fail-closes live. Staging cannot test sandbox e-way.

### P2-29 — Live IRP invents `ack_date` when provider omits it  
`gsp_adapters.py` 209–211 `or timezone.now()`.

### P2-30 — Custom GSP wrap uses placeholder HMAC secret  
`gsp_adapters.py` 331–340.

### P2-31 — Razorpay create failure silently falls back to stub checkout  
`billing/services.py` 97–101. Client may open a non-payable `stub_order_...`.

### P2-32 — `X-Company-Id` selects tenant when `active_company` is unset  
`core/permissions.py` 27–34. Multi-membership users can operate via header without switch.

### P2-33 — Tenant restore decrypt falls back to instance-wide Fernet key  
`accounts/tenant_backup.py` 304–314.

### P2-34 — `FileAsset` PDF kinds missing from `_KIND_RULES`  
Credit/debit/challan PDFs fall through to attachment rules (images allowed).

### P2-35 — Notification SMS/Push left `QUEUED` forever  
`core/services/notifications.py` 79–82. No worker.

### P2-36 — New invoice/purchase ignore company default `priceMode`  
`NewInvoicePage.tsx` / `NewPurchasePage.tsx` reset to `'EXCLUSIVE'`. POS uses company mode.

### P2-37 — Sales/purchase orders & challans have no inclusive price mode  
Always exclusive unit price.

### P2-38 — Note editors omit `assumeLocalStateForBlankParty`  
Preview tax=0 / unknown POS while BE posts intra under assume-local.

### P2-39 — POS offline checkout leaves cart active  
`PosPage.tsx` 584–596. Re-tap Pay is ambiguous.

### P2-40 — Offline invoice flush never Completes  
`useInvoiceOffline.ts` 26–31 — create/update only. Offline “Complete” becomes draft after sync.

### P2-41 — Barcode print HTML injection  
`ItemFormDialog.tsx` 288–290 `document.write` with unescaped `code`.

### P2-42 — TDS/TCS report route ignores `ENABLE_TDS`  
Menu hides; `/reports/tds-tcs` still loads and hits API.

### P2-43 — Manufacturing / Payroll / CRM routes not flag-gated at router  
`App.tsx` 437–447 — `canManageUsers` only. `ModuleGate` stops queries but routes are live.

### P2-44 — Quotations create allowed on view route; form incomplete; pagination stuck at page 1  
`QuotationsPage.tsx` 53, 88–101.

### P2-45 — Sales/purchase returns, quotations, supplier payments: `const [page] = useState(1)` with no pager  
Only first API page shown.

### P2-46 — Recurring invoices: single line, no GST/discount/warehouse  
Far thinner than invoice editor.

### P2-47 — Stock transfer UI is single-line; API accepts `lines[]`

### P2-48 — Non-PRODUCTS imports commit partial valid rows  
Only PRODUCTS blocks when `error_rows > 0`.

### P2-49 — File-hash idempotency only for PRODUCTS validate  
Opening stock / bills can double-apply.

### P2-50 — Void reverse peels FIFO by age, not source opening layer  
Wrong costs retire if other inbound layers exist.

### P2-51 — Expiry alert GET crashes on non-numeric `days`  
`int(request.query_params.get("days", 30))` → 500.

### P2-52 — GET expiry alerts mutates DB / can email  
`item_stock.py` `record_expiry_bands`. Spec Phase-1: no notifications.

### P2-53 — HSN helper catalog is tiny (~60 codes) + first-N search  
`masters/hsn_catalog.py` 69–81.

### P2-54 — Bill product match by name alone  
OCR collision attaches wrong master.

### P2-55 — LLM GST coerce drops unknown rates to `""` then commit may force 18  
Ties to P0-10.

### P2-56 — `should_probe_remaining_rows` always continues after ≥8 lines  
Extra vision cost; unnumbered rows can duplicate.

### P2-57 — Masters list cache 60s without invalidation  
Stale unit/tax lists after create.

### P2-58 — Stock count unique constraint allows duplicate null batches  
Postgres NULL ≠ NULL. Same pattern as balances already fixed with `NullsNotDistinct`.

### P2-59 — Stock count `system_qty` stale until post  
Snapshot at session create; movements before post produce wrong variance.

### P2-60 — Transfer lines missing batch/serial validation at create  
Fails only at complete.

### P2-61 — `business_date` ignores company timezone  
`inventory/item_stock.py` 33–34 `timezone.localdate()`.

### P2-62 — Opening as-of only stored in `reason` string  
Ledger `created_at` is now; period locks cannot use opening date.

### P2-63 — Sales/purchase returns drop discount and cess on create  
`SalesReturnsPage.tsx` 88–94; purchase notes omit `discountPercent`.

### P2-64 — CN/DN `maxQty` keyed by product, not source line  
`invoiceSourceLines.ts` 39–60. Duplicate products overwrite.

### P2-65 — `clampSourceLineQty` floors to integers  
Kg/partial qty cannot be credited accurately.

### P2-66 — POS ignores cess entirely  
No `cessRate` on line tax or payload.

### P2-67 — Per-item `sellingTaxInclusive` unused at billing  
Doc/company `priceMode` only.

### P2-68 — Register GSTIN not checksum-validated on FE; register session may skip flag refresh

### P2-69 — `isReallyReachable` treats `/pos` like any sales view  
POS needs create + flag; menu helper overstates access.

### P2-70 — Search returns party phones to sales-capable roles  
PII; confirm intentional.

---

## 5. Low (P3) / improvements

| ID | Location | Note |
| :--- | :--- | :--- |
| P3-01 | `core/middleware.py`, OTP SMS, billing | Silent `except` / `pass` in hot paths; add metrics |
| P3-02 | `accounts/views.py` JWT body | Access token in JSON outside prod/staging even when `DEBUG=0` |
| P3-03 | `core/validators.py` vs `llm.py` | Allowed GST includes 40%; LLM coerce omits it |
| P3-04 | `core/models.py` cess_rate | No slab validator |
| P3-05 | `AuditEvent.action` | Billing logs free-form strings not in choices |
| P3-06 | `CompanySerializerStaff` | Exposes `aato_turnover` to non-owners |
| P3-07 | `document_numbers.peek` | Unnecessary `select_for_update` |
| P3-08 | `gsp_secrets.py` | Bad ciphertext returns `{}` (looks unconfigured) |
| P3-09 | `core/events.py` | One failing subscriber aborts the rest inside the document TX |
| P3-10 | `whatsapp.py` | Credential errors become silent wa.me |
| P3-11 | Sales/purchase PDF | `pass` on logo/render errors |
| P3-12 | Sales `set_items` | Large qty-amend branch that H9-A forbids — dead / confusing |
| P3-13 | Purchase in-place update | Allows product change/line delete; sales does not; API H9-A blocks it |
| P3-14 | Delivery challan | `tax_enabled=False` by design — document convert→invoice re-tax |
| P3-15 | Sales complete | POS from live customer then stamps filing overlays separately |
| P3-16 | Import template | Missing description, category, unit, tax inclusive, MRP, reorder |
| P3-17 | `bill_images.py` | SI≤15 top else bottom — mid-table blur |
| P3-18 | `InventoryValuationService` docstring | Says WAVG only; FIFO layers exist |
| P3-19 | Opening serializer `quantity` min 0 | Service rejects ≤0 unless serials fill qty |
| P3-20 | Transfer cancel as ADJUSTMENT | Pollutes movement-type analytics |
| P3-21 | Rebuild reserved from confirmed SOs only | Document if POS/draft reserves unused |
| P3-22 | Dual `pages/phase/*` re-exports | Thin aliases; real duplication is list-dialogs vs full editors |

---

## 6. Broken and partial flows (operator view)

| Flow | Status in current code |
| :--- | :--- |
| Quotation → Invoice | Works (expired needs `confirm_expired`) |
| Quotation → SO | Works; **no FK** to the order |
| SO confirm → reserve | Works |
| SO → Invoice | Releases reservation; marks CONVERTED |
| SO → Challan | **Broken** — reservations + status (P0-02) |
| Challan → Invoice | Works; skips SALE if stock already posted |
| Return → auto CN | Works with **product-key** FK weakness (P1-02) |
| PO → Bill | Works |
| Purchase completed price amend | **Crashes** (P0-01) |
| Damaged sales return cancel | **Corrupts stock/serials** (P0-03) |
| Forgot password | **Stub** (P1-33) |
| POS inclusive | Submit OK; **row display wrong** (P1-36) |
| Offline POS | Enqueues; **cart not cleared**; invoice offline **never completes** |
| Bill OCR commit | Draft only; **invents qty/GST** (P0-10) |
| GSTR-4 composition | **Empty tables** |
| GSTR-1 B2CL | **Wrong threshold** (P0-05) |
| Cash-flow statement | **Always empty** on default chart (P0-04) |
| Tally | Export dump + **SSRF** if HTTP push used |
| Payroll | PF/ESI/PT only; **no TDS 192** |
| Manufacturing WO | Complete JE unsafe when issue_cost=0 (P0-07) |
| CRM | Lead convert + activities; not a pipeline |
| Account Aggregator | Mock + amount-only match |
| e-Invoice live | Gated; sandbox/preview; staging e-way harder than IRP |
| SMS/Push notifications | **Queued forever** |
| Inclusive + cess | **Wrong extract** FE and BE |
| Multi-GSTIN series on purchase peek | Preview number can disagree with complete |

README already states manufacturing, payroll, CRM, live NIC, GSTR-2B ITC match, native mobile, and bidirectional Tally are **not claimed** for pilot. The bugs above still fire **inside claimed MVP** (sales/purchase complete, stock, GSTR aids, cash-flow, invites, bill import).

---

## 7. Module coverage (what was actually read)

Production Python/TS was reviewed in these trees. Migrations were sampled only where they define constraints.

| Module | Files of record | Outcome |
| :--- | :--- | :--- |
| `backend/config` | settings, urls, celery | Subscription middleware order; Celery RLS; public metrics |
| `backend/core` | billing, idempotency, auth, feature flags, GSP, files, notifications, exceptions | Inclusive cess; stuck keys; fail-open billing perm |
| `backend/accounts` | views, serializers, tenant_backup | Invite OTP; COMPOSITION GSTIN; restore key fallback |
| `backend/billing` | middleware, permissions, services | Cookie-JWT miss; Razorpay stub fallback |
| `backend/sales` | models, serializers, services, notes, return, cogs, views, pdf | SO→challan; damaged cancel; TCS stub; source_item |
| `backend/purchases` | models, serializers, services, phase1 | Missing import; DN source_item; supplier match; unique number |
| `backend/inventory` | models, serializers, views, services, item_stock | Opening race/batch ID; serial API; low stock; expiry GET side effects |
| `backend/imports` | services, tasks, qty_formula, views | Qty/GST defaults; void_rows; UQC; as_of; category |
| `backend/masters` | models, serializers, views, hsn_catalog | SKU uniqueness OK; UQC auto-create; stale list cache |
| `backend/accounting` | services, reports, views | Cash-flow codes; reverse drops history; recon amounts |
| `backend/payments` / `ledgers` / `banking` | services, recon | TDS not posted; voided payments; AA match |
| `backend/reporting` | gst_returns, gstr2b, tds_worksheets | B2CL; GSTR-9 cess; GSTR-4 stub; AFTER_TAX exclusion |
| `backend/payroll` | services, models | No salary TDS |
| `backend/manufacturing` | services | WIP JE when issue_cost=0 |
| `backend/crm` | services, models | Thin convert |
| `backend/insights` | services, alerts, assistant | Heuristic cashflow |
| `backend/integrations` | tally adapter, views | SSRF; dump not sync |
| `backend/search` | views | Phone PII |
| `web/src/utils` | tax, money, gst, permissions, safeUrl | Inclusive extract; POS/state helpers aligned on GSTIN |
| `web/src/pages` | sales, purchases, POS, inventory, settings, reports, auth | Forgot password; ACL; inclusive default; notes payloads |
| `web/src/components/billing` | source lines, drafts | maxQty by product; integer clamp |
| `web/src/App.tsx` | routes | View vs create; module flags |
| `mobile/` | capacitor.config only | Wrapper around `web/dist`; no native app logic |
| CI | `.github/workflows/ci.yml` | Postgres 17 for backend tests — good |

---

## 8. Suggested fix order

1. **Unblock money/stock:** P0-01 (import), P0-02 (SO→challan), P0-03 (damaged cancel), P0-10 (bill qty/GST), P1-07 (inclusive+cess FE+BE).  
2. **Stop silent books lies:** P0-04 (cash-flow codes), P0-05 (B2CL), P1-18/P1-19 (GSTR-9 cess / AFTER_TAX), P1-12 (journal reverse).  
3. **Auth:** P0-08/P1-41 (subscription gate), P0-09 (invite), P0-06 (Tally URL).  
4. **Inventory integrity:** P0-11–P0-14, P1-26–P1-30, P1-32.  
5. **Operator honesty:** P1-33 forgot-password; GSTR-4 stub; TCS/TDS/payroll labels; POS row totals; view vs create ACL.

---

## 9. Notes on methodology

- Findings are from **current files**, not from `docs/reviews/*` or the previous `COMPREHENSIVE_CODE_REVIEW_FINDINGS.md`.  
- Line numbers will shift after patches; search the quoted identifiers.  
- Frontend/backend `extractStateCode` **is aligned** in this snapshot (15-char GSTIN or exact 2-digit valid code). That older ticket is closed.  
- Pilot README already disclaims live GSTN filing, native mobile, and full manufacturing/payroll/CRM. Those modules were still reviewed because they are shipped behind flags and can be turned on.

---

*End of report.*
