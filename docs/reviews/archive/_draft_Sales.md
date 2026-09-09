# Release-Blocking Code Review: Sales Module

This document provides the release-blocking code review of the **Sales** module in Bizboard, covering `backend/sales/*`, `backend/core/services/billing.py`, and `web/src/pages/sales/*`.

---

## 1. Executive Summary & Severity Counts

| Severity | Count | Finding IDs |
| :--- | :---: | :--- |
| **Critical** | 3 | `SALES-001`, `SALES-002`, `SALES-003` |
| **High** | 6 | `SALES-004`, `SALES-005`, `SALES-006`, `SALES-007`, `SALES-008`, `SALES-009` |
| **Medium** | 4 | `SALES-010`, `SALES-011`, `SALES-012`, `SALES-013` |
| **Low** | 0 | — |
| **Total** | **13** | |

---

## 2. Flow Coverage Assessment

| Subflow / Area | Write Path & Atomicity | Reversal & Inventory | Concurrency & Idempotency | Tenancy & Subscription | Statutory & Accounting | Tests Present | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Sales Invoices** | `@transaction.atomic`, `select_for_update` on invoice & customer. Stamped GSTIN recompute. Number allocation inside txn. | Cancel restores SALE stock, FIFO peels, and serials. Gated by payments & IRN. | `wrap_idempotent` in place (`sales_invoice_complete`). | Tenant scoped. `SubscriptionWritesAllowed` enforced. | Dual-entry GL posting via `post_sale`. Stamped GSTIN ignores RCM (`SALES-004`). | Comprehensive unit & regression tests. | **Needs Fix (`SALES-004`)** |
| **Quotations** | Header + line creation. Line validation active. | Delete allowed in DRAFT. Disallowed once converted. | Not applicable (draft only, no money movements). | Scoped by tenant. Missing multi-GSTIN branch state tax split (`SALES-010`). | Preview totals available. Header discount forwarded (`CR-021`). | Tested conversion to SO & Invoice. | **Needs Fix (`SALES-010`)** |
| **Sales Orders** | Line normalization & active product checks. Reservations posted on confirm. | Unreserve on cancel. Reservation held through invoice conversion (`CR-020`). | Atomic confirm & convert. Locks order row. | **Missing `SubscriptionWritesAllowed` (`SALES-005`)**. Non-atomic header creation (`SALES-007`). | Not applicable directly to GL (reservations only). Branch tax split (`SALES-010`). | Good test coverage on reservations & conversion. | **Needs Fix (`SALES-005`, `SALES-007`, `SALES-010`)** |
| **Delivery Challans** | Stock posted if `stock_on_delivery_challan`. Preserves lot & serials. | Cancel restores stock if posted. Gated by e-way bill. **Desyncs with draft invoice (`SALES-011`)**. | **Missing `wrap_idempotent` (`SALES-006`)**. Not in `MONEY_IDEMPOTENCY_SCOPES`. | **Critical: Cross-tenant SO injection (`SALES-001`)**. Missing subscription gate (`SALES-005`). | Delivery challan series allocated. Period lock asserted (`CR-019`). | Basic dispatch & cancel tested. | **Release Blocker (`SALES-001`, `SALES-005`, `SALES-006`, `SALES-011`)** |
| **Sales Returns** | Restores sellable stock to FIFO layers. Auto-generates Credit Note. | Cancel reverses stock restore & cancels auto-CN. Gated by GST periods. | Source invoice row locked with `select_for_update` (`CR-014`). | Company scoped. Non-atomic header creation (`SALES-007`). | **Damaged scrap formula distorts GL (`SALES-003`)**. **Drops line discount in auto-CN (`SALES-002`)**. | Return stock restore & cancel tested. | **Release Blocker (`SALES-002`, `SALES-003`, `SALES-007`)** |
| **Credit Notes** | Line normalization, GST/cess rate freeze from source item. | Headroom capped (`invoiced - CNs + DNs`). Gated by GST periods. | Atomic complete with row lock on CN & invoice. | Company scoped. Non-atomic header creation (`SALES-007`). Cancel invoice ignores draft CN (`SALES-012`). | Reverses AR and GST liability. **UI cannot pass confirm flags (`SALES-008`)**. | Good test coverage on headroom & tax freeze. | **Needs Fix (`SALES-007`, `SALES-008`, `SALES-012`)** |
| **Debit Notes** | Line quantity cap enforced (`CR-018`). Value additions require confirm. | Gated by GST periods. Cancel supported. | Atomic complete with row lock on DN & invoice. | Company scoped. Unhandled 500 on `adjustable_summary` (`SALES-013`). | Additional debit posted to AR and GST. | Line cap & additional debit tested. | **Needs Fix (`SALES-007`, `SALES-013`)** |
| **Recurring Billing** | Generates DRAFT invoices on schedule. Deduplicated via `period_key`. | Invoices start as DRAFT (can be discarded). | Catch-up loop handles up to 12 overdue periods (`CR-027`). Does not skip locked periods (`CR-015`). | **Missing `SubscriptionWritesAllowed` on schedule viewset (`SALES-005`)**. | Follows standard invoice drafting rules. | Cadence and deduplication tested. | **Needs Fix (`SALES-005`)** |
| **External Sharing** | WhatsApp / Email dispatch triggers notification services. | Not applicable. | Not applicable. | Authenticated views inadvertently exposed in public URLs. | **WhatsApp PDF link & Email link require internal auth (401 Unauthorized) (`SALES-009`)**. | Mock notification tests. | **Needs Fix (`SALES-009`)** |

---

## 3. Verified Findings & Release Blockers

### SALES-001 — Cross-Tenant Order Injection and State Mutation via Delivery Challan
- **Module:** Sales -> Delivery Challan
- **Location:** `backend/sales/phase1_serializers.py:274-295` & `backend/sales/notes_services.py:766-780, 993-1010`
- **Type:** Cross-tenant
- **Severity:** Critical
- **What's wrong:** In `DeliveryChallanSerializer`, there is no `validate_sales_order` validator (unlike `validate_customer` and `validate_warehouse` which call `self.check_company_ref`). Any authenticated tenant can submit a POST request creating a Delivery Challan linked to a `sales_order` ID belonging to an entirely different tenant. Subsequently, when completing the challan in `SalesNotesService.complete_challan`:
  ```python
  order = SalesOrder.objects.select_for_update().get(pk=challan.sales_order_id)
  ```
  The query retrieves the foreign tenant's order without checking `company_id=challan.company_id`. It proceeds to release reservations and mutates the victim company's order status:
  ```python
  order.status = SalesOrder.Status.CONVERTED
  order.save(update_fields=["status", "updated_by", "updated_at"])
  ```
  Furthermore, if the attacker cancels their challan, `cancel_challan` executes:
  ```python
  order = challan.sales_order
  if order is not None and order.status == SalesOrder.Status.CONVERTED:
      order.status = SalesOrder.Status.CONFIRMED
      order.save(update_fields=["status", "updated_by", "updated_at"])
  ```
  This flips the victim tenant's order back to `CONFIRMED` and re-reserves stock in the victim company's warehouse.
- **Trigger / repro:**
  1. Tenant B has a `CONFIRMED` Sales Order `#101`.
  2. Tenant A creates a Delivery Challan via POST `/api/v1/sales/delivery-challans/` specifying `"sales_order": 101`.
  3. Tenant A calls POST `/api/v1/sales/delivery-challans/{challan_id}/complete/`.
- **Consequence:** Cross-tenant privilege escalation and data tampering. Tenant A can manipulate the order lifecycle and inventory reservations of Tenant B.
- **Code evidence:**
  - `backend/sales/phase1_serializers.py:288-295`: `validate_customer` and `validate_warehouse` exist; `validate_sales_order` is completely absent.
  - `backend/sales/notes_services.py:769`: `SalesOrder.objects.select_for_update().get(pk=challan.sales_order_id)` lacks tenant filtering.
- **Suggested fix direction:**
  1. Add `validate_sales_order` to `DeliveryChallanSerializer` enforcing `self.check_company_ref(order, "sales_order")`.
  2. In `complete_challan` and `cancel_challan`, scope order lookups to `company=challan.company`.
- **Test to add:** `test_delivery_challan_cannot_link_foreign_sales_order` asserting HTTP 400 when submitting a cross-tenant `sales_order`.
- **Twin check:** Check `purchases/` goods receipt and purchase order conversions to ensure company scoping is strictly enforced.

---

### SALES-002 — Sales Return Line Item Economics Drop Discounts Causing Customer Over-Credit in Auto-CN
- **Module:** Sales -> Returns & Auto-Credit Note
- **Location:** `backend/sales/return_service.py:31-57, 245-285` & `web/src/components/billing/invoiceSourceLines.ts:32-46`
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:**
  1. `sourceLineReturnPayload` in `web/src/components/billing/invoiceSourceLines.ts` extracts `product`, `quantity`, `unitPrice`, `gstRate`, but omits `discountPercent`.
  2. In `SalesReturnItem`, `discount_percent` defaults to `0.00` because it is omitted from the return lines payload.
  3. When completing the return in `ReturnService.complete_return`, the service constructs line items for the auto-generated Credit Note using:
     ```python
     items_data.append({
         "product": item.product,
         "quantity": take,
         "unit_price": item.unit_price,
         "discount_percent": item.discount_percent, # Evaluates to 0.00!
         "gst_rate": item.gst_rate,
         "source_item": src,
     })
     ...
     SalesNotesService.complete_credit_note(
         note, user, confirm_paid_invoice=True, confirm_price_override=True
     )
     ```
  Because `confirm_price_override=True` is hardcoded, it silently bypasses price validation. If an invoice line was originally sold at ₹1,000 with a 20% discount (net taxable ₹800 + ₹144 GST = ₹944 total billed), the customer was billed ₹944. When returned, the auto-credit note issues a credit of ₹1,000 + ₹180 GST = ₹1,180 total credit!
- **Trigger / repro:** Sell an item with a 20% line discount. Complete invoice. Create a Sales Return for that item from the UI and complete it. Check the resulting Credit Note amount.
- **Consequence:** Immediate financial cash loss / over-crediting accounts receivable. Customers are credited more than they originally paid. Statutory GSTR-1 credit notes report mismatched taxable values against the original invoice line.
- **Code evidence:**
  - `web/src/components/billing/invoiceSourceLines.ts:32-46`: `sourceLineReturnPayload` excludes `discountPercent`.
  - `backend/sales/return_service.py:263-264`: `item.discount_percent` comes from `SalesReturnItem` where it defaulted to `0.00`.
  - `backend/sales/return_service.py:283`: `confirm_price_override=True` suppresses backend validation.
- **Suggested fix direction:**
  1. In `invoiceSourceLines.ts`, include `discountPercent: line.discountPercent` in `sourceLineReturnPayload`.
  2. Store `discount_percent` and `source_item_id` on `SalesReturnItem`.
  3. In `complete_return`, pull `unit_price` and `discount_percent` directly from the original `SalesItem` (`src.unit_price`, `src.discount_percent`).
- **Test to add:** `test_sales_return_with_line_discount_preserves_net_credit_value` asserting credit note taxable and grand_total match the discounted invoice proportion.
- **Twin check:** `purchases/return_service.py`: Verify whether debit notes auto-generated from purchase returns carry purchase bill line discounts.

---

### SALES-003 — Damaged Return Scrap GL Formula Uses Heterogeneous Blended Cost Distorting Inventory and Scrap Expense
- **Module:** Sales -> Returns & Accounting / COGS
- **Location:** `backend/sales/return_service.py:289-306`
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** When completing a return that contains damaged items, `return_service.py` computes the scrap share posted to the General Ledger using an aggregate quantity-weighted ratio across all lines:
  ```python
  damaged_qty = sum(item.quantity for item in items if item.condition == "DAMAGED")
  total_qty = sum(item.quantity for item in items)
  scrap_share = (cogs_rev * damaged_qty / total_qty).quantize(Decimal("0.01"))
  PostingService.post_sales_return_scrap(sales_return, scrap_share, user)
  ```
  `cogs_rev` is the total aggregate COGS reversal across all products on the return. If a return contains heterogeneous products (e.g. 1 Laptop costing ₹50,000 in `SELLABLE` condition, and 1 HDMI Cable costing ₹100 in `DAMAGED` condition):
  - `total_qty = 2`
  - `damaged_qty = 1`
  - `damaged_qty / total_qty = 0.5 (50%)`
  - Total `cogs_rev = ₹50,100`
  - Calculated `scrap_share = 50% * ₹50,100 = ₹25,050`!
  `PostingService.post_sales_return_scrap` then posts:
  - **Debit Scrap Expense (5150):** ₹25,050
  - **Credit Inventory Asset (1400):** ₹25,050
  The damaged cable only cost ₹100. Physical inventory restored the laptop at ₹50,000, but GL Inventory (1400) is reduced by ₹25,050, leaving the GL inventory understated by ₹24,950 and Scrap Expense overstated by ₹24,950!
- **Trigger / repro:** Create a return containing one high-value sellable item and one low-value damaged item. Complete the return with accounting enabled.
- **Consequence:** Massive accounting balance sheet distortion. Breaches GAAP/matching principles, corrupts perpetual inventory valuation (1400) vs physical stock records, and artificially deflates profit via inflated scrap expense.
- **Code evidence:** `backend/sales/return_service.py:298-306`:
  ```python
  scrap_share = (
      (cogs_rev * damaged_qty / sum((Decimal(str(i.quantity or 0)) for i in items), Decimal("0"))).quantize(
          Decimal("0.01")
      )
  )
  ```
- **Suggested fix direction:** Compute scrap cost per line within `restore_return_stock_and_cogs` where product-specific FIFO layer unit costs are available. Sum only the actual cost of damaged lines rather than an arbitrary blended quantity fraction.
- **Test to add:** `test_damaged_return_heterogeneous_items_posts_exact_damaged_cost_to_scrap_gl`.
- **Twin check:** Check purchase returns for any scrap or rejection GL postings.

---

### SALES-004 — Inter-State RCM Sales Invoice Fails to Recompute Reverse Charge Taxes on Stamped GSTIN Branch Change
- **Module:** Sales -> RCM / Stamped GSTIN
- **Location:** `backend/core/services/billing.py:736-737` & `backend/sales/services.py:811-821`
- **Type:** Bug
- **Severity:** High
- **What's wrong:** In `core/services/billing.py`, `recompute_totals_for_stamped_gstin` early-returns whenever `is_reverse_charge` is True:
  ```python
  if getattr(document, "is_reverse_charge", False):
      return
  ```
  In `backend/sales/services.py` `complete()`:
  ```python
  tax_left = (
      Decimal(str(invoice.cgst_total or 0))
      + Decimal(str(invoice.sgst_total or 0))
      + Decimal(str(invoice.igst_total or 0))
      + Decimal(str(getattr(invoice, "cess_total", 0) or 0))
  )
  if invoice.is_reverse_charge and tax_left > 0:
      apply_rcm_memo_after_tax(invoice, items)
  ```
  On draft creation, `set_items` applies `apply_rcm_memo_after_tax`, which zeroes `cgst_total`, `sgst_total`, and `igst_total`, moving tax into `rcm_cgst`, `rcm_sgst`, or `rcm_igst`.
  At `complete()`:
  1. `recompute_totals_for_stamped_gstin` exits immediately due to the early-return guard.
  2. `tax_left` is `0`, so `apply_rcm_memo_after_tax` does not run.
  If an RCM invoice is drafted with default intra-state GSTIN (State 27 -> State 27, generating `rcm_cgst` and `rcm_sgst`), but at completion is stamped with a branch GSTIN in State 24 (Gujarat, an inter-state supply requiring IGST), the tax is never recomputed to IGST.
- **Trigger / repro:** Create an RCM draft invoice with intra-state customer. Complete invoice while stamping a branch GSTIN from another state.
- **Consequence:** The invoice retains intra-state `rcm_cgst` and `rcm_sgst` instead of `rcm_igst`. GSTR-1 Table 4B and e-Invoice payloads report illegal intra-state taxes for an inter-state transaction, causing tax portal rejections and statutory audit penalties.
- **Code evidence:**
  - `backend/core/services/billing.py:736-737`: `if getattr(document, "is_reverse_charge", False): return`
  - `backend/sales/services.py:811-821`: `tax_left` check fails because RCM tax is already zeroed out.
- **Suggested fix direction:** Remove the RCM early return from `recompute_totals_for_stamped_gstin`, or allow RCM memo recalculation based on the resolved `intra_now` state of the stamped GSTIN.
- **Test to add:** `test_rcm_invoice_stamped_branch_gstin_switches_cgst_sgst_to_igst`.
- **Twin check:** Review purchase RCM bills with stamped branch GSTIN for identical early returns.

---

### SALES-005 — Missing Subscription Enforcement on Sales Orders, Delivery Challans, and Recurring Schedules
- **Module:** Sales -> Permissions & Tenancy
- **Location:** `backend/sales/phase1_views.py:215-225, 282-295` & `backend/sales/views.py:640-646`
- **Type:** Broken-feature
- **Severity:** High
- **What's wrong:** Standard sales write endpoints (`SalesInvoiceViewSet`, `QuotationViewSet`, `SalesReturnViewSet`, `SalesCreditNoteViewSet`, and `SalesDebitNoteViewSet`) include `SubscriptionWritesAllowed()` in their permission classes to block write actions if a tenant's subscription is lapsed, expired, or suspended.
  However, `SalesOrderViewSet`, `DeliveryChallanViewSet`, and `RecurringInvoiceScheduleViewSet` only check `[IsAuthenticated, HasCompany, CanCreateSales]`.
  Users belonging to tenants with expired or suspended subscriptions can still:
  - Create, edit, confirm, and convert Sales Orders.
  - Create, complete, and cancel Delivery Challans (which execute physical inventory stock movements when `stock_on_delivery_challan=True`).
  - Configure and trigger recurring invoice schedule runs.
- **Trigger / repro:** Set tenant company subscription status to `EXPIRED` or `SUSPENDED`. Issue POST requests to `/api/v1/sales/sales-orders/` or `/api/v1/sales/delivery-challans/{id}/complete/`.
- **Consequence:** Paywall bypass and unbilled SaaS usage. Expired tenants continue dispatching inventory via delivery challans without an active subscription.
- **Code evidence:**
  - `backend/sales/phase1_views.py:221-222`: `action in ("create", ...): return [IsAuthenticated(), HasCompany(), CanCreateSales()]` (No `SubscriptionWritesAllowed`).
  - `backend/sales/phase1_views.py:290-291`: Challan complete permissions lack `SubscriptionWritesAllowed`.
  - `backend/sales/views.py:644-645`: Recurring schedule viewset lacks `SubscriptionWritesAllowed`.
- **Suggested fix direction:** Add `SubscriptionWritesAllowed()` to `get_permissions()` in `SalesOrderViewSet`, `DeliveryChallanViewSet`, and `RecurringInvoiceScheduleViewSet`.
- **Test to add:** `test_expired_subscription_blocks_sales_order_and_challan_actions`.
- **Twin check:** Verify whether `PurchaseOrderViewSet` and `GoodsReceiptViewSet` in `purchases/` enforce `SubscriptionWritesAllowed`.

---

### SALES-006 — Delivery Challan Complete Lacks Idempotency Wrapping and Scope Registration
- **Module:** Sales -> Delivery Challan / Idempotency
- **Location:** `backend/sales/phase1_views.py:325-328` & `backend/core/idempotency.py:32-62`
- **Type:** Missing-validation
- **Severity:** High
- **What's wrong:**
  1. `DeliveryChallanViewSet.complete` calls `SalesNotesService.complete_challan` directly without wrapping it in `wrap_idempotent()`.
  2. The scope `"delivery_challan_complete"` is omitted from `MONEY_IDEMPOTENCY_SCOPES` in `backend/core/idempotency.py`.
  When a company has `stock_on_delivery_challan=True`, completing a delivery challan is an inventory-posting state change. If an operator double-clicks or experiences a network disconnect during completion, the second request fails with HTTP 400 (`"Cannot complete challan in status COMPLETED"`) instead of safely replaying the cached HTTP 200 payload.
- **Trigger / repro:** Send two concurrent POST requests with the same `Idempotency-Key` header to `/api/v1/sales/delivery-challans/{id}/complete/`.
- **Consequence:** Frustrating UX and false alarm errors for warehouse staff; potential double-handling or confusion regarding whether goods were dispatched.
- **Code evidence:**
  - `backend/sales/phase1_views.py:325-327`:
    ```python
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        challan = SalesNotesService.complete_challan(self.get_object(), request.user)
        return Response(self.get_serializer(challan).data)
    ```
  - `backend/core/idempotency.py:32-62`: `"delivery_challan_complete"` is missing from `MONEY_IDEMPOTENCY_SCOPES`.
- **Suggested fix direction:** Add `"delivery_challan_complete"` to `MONEY_IDEMPOTENCY_SCOPES` and wrap `DeliveryChallanViewSet.complete` with `@wrap_idempotent(scope="delivery_challan_complete")`.
- **Test to add:** `test_delivery_challan_complete_idempotency_replay`.
- **Twin check:** Verify Goods Receipt note completion idempotency in `purchases/`.

---

### SALES-007 — Non-Atomic Header Creation Leaves Orphaned Records on Line Validation Failure Across 5 ViewSets
- **Module:** Sales -> Serializers / Document Creation
- **Location:** `backend/sales/serializers.py:517-521` & `backend/sales/phase1_serializers.py:84, 169, 231, 299`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** In `SalesReturnSerializer`, `SalesCreditNoteSerializer`, `SalesDebitNoteSerializer`, `SalesOrderSerializer`, and `DeliveryChallanSerializer`, the document header is created via `Model.objects.create(**validated_data)` outside of any `transaction.atomic()` block before line items are inserted via the service layer:
  ```python
  def create(self, validated_data):
      items_data = validated_data.pop("items")
      sales_return = SalesReturn.objects.create(**validated_data)
      SalesService.set_return_items(sales_return, [dict(l) for l in items_data], self.context["request"].user)
      return sales_return
  ```
  If `set_*_items()` raises a `ValidationError` or `BusinessRuleError` (e.g., negative quantity, inactive product, or invalid GST slab), the inner transaction on line creation rolls back, but the header record remains committed in the database as an orphaned `DRAFT`.
  In particular, for `SalesReturn`, `SalesService.cancel` explicitly checks:
  ```python
  if invoice.returns.filter(status="DRAFT").exists():
      raise ValidationError("Cannot cancel invoice with draft returns")
  ```
  An orphaned draft return from a failed line creation permanently prevents the parent sales invoice from ever being cancelled!
- **Trigger / repro:** POST to `/api/v1/sales/returns/` with a valid header pointing to an invoice, but with an invalid line (e.g. quantity = 0). The request fails with HTTP 400, but a draft `SalesReturn` record remains in the database.
- **Consequence:** Database pollution with zombie draft records. Source sales invoices are blocked from cancellation.
- **Code evidence:**
  - `backend/sales/serializers.py:519`: `SalesReturn.objects.create` outside atomic.
  - `backend/sales/phase1_serializers.py:84`: `SalesCreditNote.objects.create` outside atomic.
  - `backend/sales/phase1_serializers.py:169`: `SalesDebitNote.objects.create` outside atomic.
  - `backend/sales/phase1_serializers.py:231`: `SalesOrder.objects.create` outside atomic.
  - `backend/sales/phase1_serializers.py:299`: `DeliveryChallan.objects.create` outside atomic.
- **Suggested fix direction:** Decorate or wrap `create()` in `@transaction.atomic` across all five serializers.
- **Test to add:** `test_sales_return_invalid_lines_rolls_back_header`.
- **Twin check:** Inspect `purchases/phase1_serializers.py` for identical non-atomic `Model.objects.create` patterns.

---

### SALES-008 — Web UI Lacks Handlers for Backend Confirmations on CNs and Sales RCM
- **Module:** Sales -> Frontend / Confirmation Modals
- **Location:** `web/src/utils/completeWithConfirms.ts:4-55` & `web/src/api/legacy/sales.ts:803-806`
- **Type:** Broken-feature
- **Severity:** High
- **What's wrong:** The backend requires confirmation flags for sensitive operations:
  - `confirm_cn_on_paid_invoice`: required when completing a Credit Note against an invoice with payment allocations.
  - `confirm_cn_price_override`: required when a Credit Note line unit price differs from the source invoice.
  - `sales_rcm_unconfirmed`: required when completing an invoice subject to Reverse Charge.
  However, `web/src/utils/completeWithConfirms.ts` does not include these codes in `prompts` or `flagFor`:
  ```typescript
  export type CompleteExtra = {
    confirmBlankPos?: boolean;
    confirmGstinTotalChange?: boolean;
    confirmNoRcm?: boolean;
    confirmDuplicateBill?: boolean;
    confirmAdditionalDebit?: boolean;
  };
  ```
  Furthermore, `completeSalesCreditNote` in `web/src/api/legacy/sales.ts` only passes:
  ```typescript
  const { data } = await apiClient.post(`/sales/credit-notes/${id}/complete/`, {
    confirmBlankPos: Boolean(options?.confirmBlankPos),
    confirmGstinTotalChange: Boolean(options?.confirmGstinTotalChange),
  });
  ```
  It has no parameters for `confirmPaidInvoice` or `confirmPriceOverride`. When a user attempts to complete a CN on an invoice with allocations, or an RCM invoice, the backend returns HTTP 400/409 asking for confirmation, but the UI is incapable of handling it and crashes or displays an unresolvable error toast.
- **Trigger / repro:** Attempt to complete a Credit Note in the web interface for an invoice that has receipts allocated.
- **Consequence:** Users are hard-blocked in the frontend from completing legitimate credit notes and reverse-charge sales invoices.
- **Code evidence:**
  - `web/src/utils/completeWithConfirms.ts:4-10`: Missing `confirmCnOnPaidInvoice`, `confirmCnPriceOverride`, `confirmSalesRcm`.
  - `web/src/api/legacy/sales.ts:803-806`: Only two confirm flags forwarded in request payload.
- **Suggested fix direction:** Expand `CompleteExtra`, `prompts`, and `flagFor` in `completeWithConfirms.ts` to support all sales confirm error codes, and pass them in `completeSalesCreditNote` and `completeSalesInvoice`.
- **Test to add:** Frontend component test verifying that `completeWithConfirms` catches `confirm_cn_on_paid_invoice` and prompts the user.
- **Twin check:** Check purchase debit note confirms for supplier payments in `completeWithConfirms.ts`.

---

### SALES-009 — External Customer WhatsApp and Email Invoice Links Route to Internal Authenticated Endpoints (401 Unauthorized)
- **Module:** Sales -> External Notifications / PDF Sharing
- **Location:** `backend/sales/whatsapp_send.py:13-17, 43-52` & `backend/sales/views.py:461-466`
- **Type:** Broken-feature
- **Severity:** High
- **What's wrong:** When an invoice is completed and shared with an external buyer:
  1. `compose_invoice_whatsapp_body` constructs the PDF link via `invoice_pdf_url(invoice, request)`:
     ```python
     path = f"/api/v1/sales/invoices/{invoice.pk}/pdf/"
     ```
     This endpoint is protected by:
     `permission_classes = [IsAuthenticated, HasCompany, CanViewSalesSurfaces]`
     An external customer receiving this WhatsApp link on their phone clicks it and receives an immediate `401 Unauthorized` JSON response.
  2. Similarly, in `views.py` `send_email`:
     ```python
     view_url = f"{base}/sales/history/{invoice.pk}"
     ```
     This routes to an internal authenticated dashboard route rather than a public, token-signed guest document viewer.
- **Trigger / repro:** Send an invoice via WhatsApp or Email from the sales invoice screen. Open the link in an incognito browser window (simulating the customer).
- **Consequence:** External customers cannot access or download their invoices. Renders customer communication broken and unprofessional.
- **Code evidence:**
  - `backend/sales/whatsapp_send.py:14`: Points directly to `/api/v1/sales/invoices/{invoice.pk}/pdf/`.
  - `backend/sales/views.py:92`: PDF action requires internal authentication and sales permissions.
  - `backend/sales/views.py:461`: Email body links to `/sales/history/{invoice.pk}`.
- **Suggested fix direction:** Implement a cryptographically signed token mechanism (e.g. `/api/v1/public/invoices/{signed_token}/pdf/`) allowing unauthenticated access to the specific invoice PDF within a limited expiry window, or attach the PDF binary directly to the email/WhatsApp message.
- **Test to add:** `test_external_whatsapp_pdf_link_accessible_without_user_session`.
- **Twin check:** Compare with purchase order email sharing to external suppliers.

---

### SALES-010 — Quotation and Sales Order Tax Calculation Ignores Multi-GSTIN Branch State
- **Module:** Sales -> Quotations & Orders / Tax Calculation
- **Location:** `backend/sales/services.py:1319-1325` & `backend/sales/notes_services.py:494-496`
- **Type:** Sales/Purchase-inconsistency
- **Severity:** Medium
- **What's wrong:** In `set_quotation_items`:
  ```python
  intra_state=party_intra_state(
      quotation.company,
      quotation.customer.state,
      quotation.customer.gstin or "",
      seller_state=quotation.company.state or "",
      seller_gstin=quotation.company.gstin or "",
  )
  ```
  `seller_state` is hardcoded to `quotation.company.state` (the company head office state), completely ignoring `quotation.company_gstin`.
  Similarly, in `set_order_items`:
  ```python
  intra_state=party_intra_state(
      order.company, order.customer.state, order.customer.gstin or ""
  )
  ```
  If a multi-GSTIN enterprise has its head office in Maharashtra (State 27) and a branch in Karnataka (State 29), a quotation or order issued by the Karnataka branch to a Karnataka customer compares Buyer State 29 against Company HO State 27. It classifies the transaction as inter-state and calculates IGST.
  Later, when converting the quotation or order to an invoice, `recompute_totals_for_stamped_gstin` switches the tax to CGST + SGST (intra-state), altering the tax breakdown and causing confusion for the customer.
- **Trigger / repro:** In a multi-GSTIN company (HO in State A, Branch in State B), create a Quotation or Sales Order for a customer in State B using the Branch GSTIN.
- **Consequence:** Inaccurate tax quotations presented to buyers; document conversion alters tax lines.
- **Code evidence:**
  - `backend/sales/services.py:1323-1324`: Hardcoded `seller_state=quotation.company.state or ""`.
  - `backend/sales/notes_services.py:494-496`: Omits `seller_state` and `seller_gstin` from `party_intra_state`.
- **Suggested fix direction:** Use `getattr(document.company_gstin, "state", None) or document.company.state` as `seller_state` in both quotation and order services.
- **Test to add:** `test_quotation_with_branch_gstin_calculates_branch_intrastate_tax`.
- **Twin check:** Inspect purchase order tax calculations for branch GSTIN handling.

---

### SALES-011 — Cancel Delivery Challan Reverses Stock While Linked Draft Invoice Still Exists and Skips Future Deduction
- **Module:** Sales -> Delivery Challan Cancel
- **Location:** `backend/sales/notes_services.py:944-950` & `backend/sales/services.py:942-953`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:**
  1. `cancel_sales_order` forbids cancellation if `order.converted_invoice_id` exists. However, `cancel_challan` only blocks cancellation if the invoice is completed:
     ```python
     if challan.converted_invoice_id:
         inv = challan.converted_invoice
         if inv.status in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
             raise BusinessRuleError("Cannot cancel a challan whose converted invoice is completed.")
     ```
     If the converted invoice is in `DRAFT`, `cancel_challan` proceeds and cancels the challan.
  2. `cancel_challan` reverses the challan's stock movements back into inventory.
  3. The draft `SalesInvoice` still exists with `converted_invoice` pointing to the cancelled challan.
  4. When that draft invoice is completed, `services.py` checks:
     ```python
     stock_from_challan = DeliveryChallan.objects.filter(
         converted_invoice=invoice, stock_posted=True
     ).exists()
     ```
     Because this filter does NOT exclude `status=CANCELLED`, `stock_from_challan` evaluates to `True`!
     As a consequence, the completed invoice skips deducting stock!
- **Trigger / repro:**
  1. Complete delivery challan (stock posted).
  2. Convert delivery challan to invoice (invoice is in `DRAFT`).
  3. Cancel delivery challan (stock restored).
  4. Complete draft invoice.
- **Consequence:** Physical inventory is never deducted for the completed sale. Warehouse inventory is overstated, leading to phantom stock and fulfillment discrepancies.
- **Code evidence:**
  - `backend/sales/notes_services.py:946`: Allows cancellation when `inv.status == DRAFT`.
  - `backend/sales/services.py:942-944`: Does not exclude `status=DeliveryChallan.Status.CANCELLED`.
- **Suggested fix direction:**
  1. In `cancel_challan`, block cancellation if `converted_invoice_id` is set (regardless of invoice status), requiring the draft invoice to be deleted first.
  2. In `services.py`, exclude cancelled challans from `stock_from_challan`: `.exclude(status=DeliveryChallan.Status.CANCELLED)`.
- **Test to add:** `test_cancel_delivery_challan_blocked_when_draft_invoice_exists`.
- **Twin check:** Check purchase Goods Receipt cancellation vs draft purchase bills.

---

### SALES-012 — Sales Invoice Cancellation Allows Draft Credit and Debit Notes to Linger Orphaned
- **Module:** Sales -> Invoice Cancel
- **Location:** `backend/sales/services.py:1136-1142`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** In `SalesService.cancel`:
  ```python
  if invoice.returns.exclude(
      status__in=(SalesReturn.Status.COMPLETED, SalesReturn.Status.CANCELLED)
  ).exists():
      raise BusinessRuleError("Cancel or delete the draft sales return(s) against this invoice first.")
  if invoice.credit_notes.filter(status=SalesCreditNote.Status.COMPLETED).exists() or invoice.debit_notes.filter(
      status=SalesDebitNote.Status.COMPLETED
  ).exists():
      raise BusinessRuleError("Cannot cancel an invoice with completed credit or debit notes.")
  ```
  Notice that while draft returns are explicitly checked and blocked via `.exclude(status__in=(COMPLETED, CANCELLED))`, Credit Notes and Debit Notes are only checked for `status=COMPLETED`.
  If an invoice has an uncompleted `DRAFT` credit note or debit note, `SalesService.cancel` succeeds and cancels the invoice. The draft notes remain orphaned in the database. When someone subsequently attempts to complete the draft note, `complete_credit_note` raises an error because the source invoice is cancelled (`"Credit notes require a completed source invoice"`), leaving the draft note permanently stuck.
- **Trigger / repro:** Create a draft Credit Note against a completed invoice. Cancel the invoice. Attempt to interact with the draft Credit Note.
- **Consequence:** Inconsistent document lifecycle; orphaned draft notes in the tenant's workspace that cannot be completed or cleanly processed.
- **Code evidence:** `backend/sales/services.py:1136-1142`: Checks only `status=COMPLETED` for CN and DN, unlike returns which check draft state.
- **Suggested fix direction:** In `SalesService.cancel`, check `invoice.credit_notes.exclude(status=SalesCreditNote.Status.CANCELLED).exists()` and `invoice.debit_notes.exclude(status=SalesDebitNote.Status.CANCELLED).exists()`.
- **Test to add:** `test_cancel_invoice_blocked_by_draft_credit_note`.
- **Twin check:** `purchases/services.py`: Verify if cancelling a purchase invoice checks for draft debit notes.

---

### SALES-013 — Unhandled 500 Internal Server Errors in `adjustable_summary` and Query Parameter Filtering
- **Module:** Sales -> API / Views Error Handling
- **Location:** `backend/sales/phase1_views.py:123` & `backend/sales/views.py:596-597`
- **Type:** Silent-failure
- **Severity:** Medium
- **What's wrong:**
  1. In `SalesDebitNoteViewSet.adjustable_summary`:
     ```python
     invoice = SalesInvoice.objects.get(pk=invoice_id, company=company)
     ```
     If `invoice_id` is invalid, deleted, or belongs to another tenant, the view raises an uncaught `SalesInvoice.DoesNotExist`, causing Django to return HTTP 500 Internal Server Error instead of HTTP 404 or 400.
  2. In `SalesReturnViewSet.get_queryset`:
     ```python
     if self.request.query_params.get("customer"):
         qs = qs.filter(customer_id=self.request.query_params["customer"])
     ```
     If the frontend query string passes a non-numeric value (e.g. `?customer=undefined`, common during React component initial render), PostgreSQL and Django ORM raise a `ValueError` / `DataError`, resulting in an unhandled HTTP 500 crash.
- **Trigger / repro:**
  - Call GET `/api/v1/sales/debit-notes/adjustable-summary/?invoice=999999`
  - Call GET `/api/v1/sales/returns/?customer=undefined`
- **Consequence:** HTTP 500 crashes exposed to clients, Sentry error flooding, and degraded API reliability.
- **Code evidence:**
  - `backend/sales/phase1_views.py:123`: Raw `.get()` without 404 handling.
  - `backend/sales/views.py:596-597`: Unvalidated query param passed directly to integer field filter.
- **Suggested fix direction:** Use `get_object_or_404(SalesInvoice, pk=invoice_id, company=company)` in `adjustable_summary`, and validate that query params are integers before filtering by ID.
- **Test to add:** `test_adjustable_summary_missing_invoice_returns_404`, `test_returns_invalid_customer_query_param_handled`.
- **Twin check:** Review purchase note adjustable summaries in `purchases/phase1_views.py`.

---

## 4. Verified Resolved / Prior Hypotheses Disproved

During our in-depth audit of recent changes (`CR-014` through `CR-028`), several hypotheses from initial exploratory notes were verified as **already resolved**:

1. **Concurrent sales returns over-return stock (Old SALES-001):**
   - *Status:* **Resolved in CR-014.**
   - *Evidence:* `ReturnService.complete_return` explicitly acquires a lock on the source invoice via:
     `invoice = SalesInvoice.objects.select_for_update().get(pk=sales_return.sales_invoice_id)`
     preventing concurrent return completion races on the same invoice.

2. **Recurring schedule permanently skips locked periods (Old SALES-002 / SALES-014):**
   - *Status:* **Resolved in CR-015 & CR-027.**
   - *Evidence:* When a GST period is locked, `_process_one_schedule` does NOT advance `next_run_at`. A multi-period catch-up loop processes up to `MAX_CATCHUP_TICKS = 12` periods once unlocked.

3. **Invoice list balance ignores credit/debit notes (Old SALES-003):**
   - *Status:* **Resolved in CR-016.**
   - *Evidence:* The invoice list serializer now annotates balance via `LedgerService.bulk_sales_invoice_outstanding`, properly factoring in completed Credit and Debit Notes.

4. **Debit notes lack per-line quantity cap (Old SALES-005):**
   - *Status:* **Resolved in CR-018.**
   - *Evidence:* `complete_debit_note` verifies that line quantities do not exceed `source_item.quantity` unless explicit additional debit confirmation is provided.

5. **Delivery challan complete does not gate closed periods (Old SALES-006):**
   - *Status:* **Resolved in CR-019.**
   - *Evidence:* `complete_challan` invokes `assert_period_allows_money_amend(challan.company, challan.challan_date)` before allocating numbers or modifying stock.

6. **Confirmed SO -> Invoice conversion drops reservation (Old SALES-007):**
   - *Status:* **Resolved in CR-020.**
   - *Evidence:* Reservations are preserved through conversion and only released upon invoice completion or cancellation.

7. **Quotation totals ignore header discount / charges (Old SALES-008):**
   - *Status:* **Resolved in CR-021.**
   - *Evidence:* `set_quotation_items` now forwards `invoice_discount`, `additional_charges`, and `auto_round_off` into `compute_document_totals`.

8. **Invoice complete late period gate (Old SALES-010):**
   - *Status:* **Resolved in CR-023.**
   - *Evidence:* `assert_period_allows_money_amend` is now executed prior to document number allocation and status mutation.

9. **IRN FAILED status asymmetry (Old SALES-012):**
   - *Status:* **Resolved in CR-025.**
   - *Evidence:* IRN guard logic harmonized between amendment and cancellation workflows.