# Quick Order Entry — Detailed Implementation Plan

**Date:** 2026-10-12
**Source review:** [QUICK_ORDER_ENTRY_REVIEW_2026-10-12.md](QUICK_ORDER_ENTRY_REVIEW_2026-10-12.md) (§21 work packages, §22 verification)
**Screen:** `web/src/pages/sales/QuickEntryPage.tsx` · route `/sales/quick-entry` · backlog `qos/backlog/QOS-0048.yaml`

This document turns every work package (`QOE-00` … `QOE-15`) and every open decision (`D-0` … `D-5`) from the review into an executable plan: exact files, step-by-step changes, API contracts, tests, acceptance checks, risks and rollback.

**Sizing:** `S` ≤ 0.5 d · `M` 1–2 d · `L` 3–5 d (one engineer, tests included).
**Revision 2 (2026-10-12):** incorporates a second code-level review. Every claim was re-checked against the code; corrections are in Part A2. Main changes: `QOE-12b` merged into `QOE-12a`; `QOE-01`/`QOE-04` now reuse and fix the existing `POST /sales/invoices/preview-totals/` instead of adding a new endpoint; field names fixed (`credit_days`, `shipping_address`, `billing_address`); new decision **D-6** (`SalesOrder` has no `price_mode`); audit/idempotency/flag mechanics corrected; `saveRecentSku` stays at add-time (Test 3 depends on it).

## Implementation status (2026-10-12)

All packages are implemented in the working tree (uncommitted, together with the Customers-plan WIP). Rollout and rollback: [QUICK_ORDER_ENTRY_ROLLOUT.md](QUICK_ORDER_ENTRY_ROLLOUT.md).

| Decision | Taken | Where |
|---|---|---|
| D-0/D-1 | QOS-0048 originally specified a draft invoice. Both are built: **Draft bill** is the default; **Sales order** mode is behind the `QUICK_ENTRY_ORDER_MODE` company flag. | `QuickEntryPage.tsx` |
| D-2 | Save & next (stay, reset, link) + Save & open. | `QuickEntryPage.tsx` |
| D-3 | Option (c): `QUICK_ENTRY_AUTO_CONFIRM` confirms after create. A rule refusal (4xx) leaves a DRAFT and says "Needs approval"; a dropped connection or 5xx says confirming did not complete. | `QuickEntryPage.tsx` |
| D-4 | Invoice `salesperson = request.user` only when `X-Client-Source: quick_entry`; no `salesman`/`sales_channel` defaults (no user→Employee link exists); `source` in audit metadata. | `sales/views.py`, `core/viewsets.py` |
| D-5 | Decimals only for measured UQC codes; no schema change. | `utils/quantity.ts` |
| D-6 | **Added `SalesOrder.price_mode`** (migration `0071`). Orders carry the company's price mode like bills; the lock was removed. | `sales/models.py`, `phase1_serializers.py` |

Package status: QOE-00 … QOE-15 implemented, including the items first left open:
- Order/challan guards, idempotent create (orders, challans) and confirm, shared `IdempotentCreateMixin` in `core/idempotency.py` (invoice create now uses it too).
- Challan multi-GSTIN: `DeliveryChallan` has no `company_gstin`, so there is nothing to apply; the order tax split is fixed and tested.
- Credit hold: the single-customer read adds `collection_status` when the company's auto credit hold is on; Quick Entry shows the chip and warning.
- Stock: chips and lines show availability from `/sales/stock-hints/`; a short line warns only when the company blocks negative stock, otherwise informs.
- Price preview is flag-gated; without it the customer's price list still prices the line (client fallback) and the footer shows an estimated GST.
- Draft persistence includes the chosen ship-to. FAQ and help page updated. Mock flags added.
- Phone-width pass done in the mock-data dev build (375×812): layout fixed (controls stacked under the product name), Hindi toggle and Save & next work.

Still not done (cannot be done in this session):
- Hindi strings need a native review.
- The pilot with real tenants (QOE-15 step 4) and its measurements.
- Salesman attribution on orders (needs a user→Employee link; D-4).
- Audit-based metrics have no dashboard.
- Nothing is committed.

---

**Conventions:** locate code by symbol (line numbers drift — the working tree has uncommitted Customers-plan edits in the same files). Web type-check is `tsc -b` (not `tsc -p .`). Lint is 0-error and CI-gated. Backend tests that depend on concurrency/idempotency are Postgres-only.

---

## Part A — Verification results (closes review §22)

I checked the open items against the code on 2026-10-12. These findings change parts of the plan.

| ID | Result | Consequence for the plan |
|---|---|---|
| **V-1** | **Confirmed.** `core/services/registration_gates.py::assert_may_issue_gst_tax_invoice` raises `BusinessRuleError` (`REGISTRATION_GATE`) for `UNREGISTERED` and `COMPOSITION` companies when `tax_enabled`; for `REGULAR` it requires a company GSTIN. It is called from `sales/services.py` (completion path). | `QOE-04` is a real correctness fix. Also handle the REGULAR-without-GSTIN case (surface the help code, don't just default type). |
| **V-2** | **Confirmed.** `SalesInvoiceViewSet.create` (`sales/views.py`, ~L157–193): reads `Idempotency-Key` header; `begin_record(company, scope="sales_invoice_create", raw_key, fingerprint=request_fingerprint(request))` returns a replay `Response` or claims the key; on `201` calls `store_record(..., resource_id=…)` (unwrapping `data["data"]` envelope); `finally` → `release_record` if not created. | `QOE-12a` copies this block verbatim with `scope="sales_order_create"`. |
| **V-3** | **Resolved — NOT exploitable via company switch.** `useCompanySwitcher.switchCompany` calls `qc.clear()`. | Downgrade the recents-cache issue in `QOE-06` to hygiene (add `companyId` to the key as defence in depth). Component state (`customer`, `lines`) still must reset — a mounted page is not unmounted by `qc.clear()`. |
| **V-4** | **Confirmed equivalent.** `priceList.ts::resolveListUnitPrice` applies slab selection by highest `minQty`, `maxQty`, and `discountPct` with `roundMoney`; backend `resolve_party_price` applies slab, `discount_pct`, quantize 0.01. | Fallback in `QOE-01` is viable, but the server preview remains preferred (one source of truth). |
| **V-5** | **No `ids=` filter found** on `ProductViewSet` (only `pos-catalog` with `updated_after`, and `search`/`status` params). | `QOE-03` adds a small `?ids=1,2,3` filter (cap 50) to the products list. |
| **V-6** | **Confirmed.** `UnsavedChangesGuard` takes `{when, prompt, title, body, leaveLabel, interceptLinks, onStay, onLeave}`; uses `useBlocker` on a data router, otherwise (plain `BrowserRouter`) only `beforeunload` plus optional link-click interception. **Browser Back cannot be intercepted on `BrowserRouter`.** | No `flushSync` needed: bypass by turning `when` false via state before navigating. Because Back can't be guarded, `QOE-14` (draft persistence) is **required**, not optional. |
| **V-7** | **Resolved.** `SalesChannel` has only `WALK_IN`, `ONLINE`, `DISTRIBUTOR`. `Employee` has **no visible user FK** (confirm in `payroll/models.py` before coding). `SalesInvoice.salesperson` is an FK to the auth user; `views.py` already validates a `salesperson` as an active `CompanyUser`. | `D-4` recommendation: invoice → set `salesperson = request.user` server-side; order → do not set `salesman`; do not set `sales_channel`; record `source` in audit only. |
| **V-8** | **Resolved — no decimal flag exists.** `masters.Unit` has `name`, `short_name`, `uqc_code` only. | `D-5` recommendation: decide decimals from `uqc_code` (client config set: `KGS, GMS, LTR, MLT, MTR, CMS, SQM, SQF, CBM, TON, QTL`); everything else integer-only. No schema change. `ProductSerializer` does **not** expose it (C-7) — `QOE-07` step 0 adds `unit_uqc`. |
| **V-9** | **Partly confirmed.** `invalidateInvoiceSideEffects` already invalidates: `sales-invoices`, `sales-invoice`, `customers`, `customer`, `customer-360`, `dashboard`, `products`, `stock-balance`, `stock`, `attention-rows` and others. **No `sales-orders` key and no delivery-route key** — the verified key list is in C-10 / `QOE-05` step 4 (includes `sales-orders-open`, `route-combine`). | Do not invent `morning-brief` / `delivery-routes` keys; list only keys that exist. |
| **V-10** | **Confirmed.** `QuickEntryPage.test.tsx` mocks `@/api/resources` (`createSalesInvoice`, `listSalesInvoicesPage`), `useCustomerSearch`, `useProductSearch`, `useNavigate`; label is `Widget (WID-1)`; test 2 asserts `unitPrice: 50`. It does **not** assert `gstRate` (code sends it). | `QOE-00` must change test 2. Every new `useQuery` (company, preview…) needs a mock entry in the `@/api/resources` mock or the tests will throw. |

Also verified: `createSalesOrder` in `web/src/api/legacy/sales.ts` takes **no options argument and sends no `Idempotency-Key`**, whereas `createSalesInvoice(payload, options?: {idempotencyKey})` does. `userGestureIdempotencyKey()` is just `newIdempotencyKey()` (a fresh key each call).

---

## Part A2 — Corrections from the second review (all re-verified in code)

| # | Finding | Verified? | Effect |
|---|---|---|---|
| C-1 | `Customer` has **no** `address` or `payment_terms_days`. Real fields: `billing_address`, `shipping_address`, **`credit_days`**. `CustomerShippingAddress` has only `label`, `address`, `is_default` (no active flag), related_name `shipping_addresses`, ordered `-is_default, id`. | Yes | `QOE-12a` default chain rewritten. |
| C-2 | `SalesOrder` has **no `price_mode`** (model, serializer, `createSalesOrder` type). `compute_document_totals` reads `getattr(document,"price_mode","EXCLUSIVE")`, so orders are always EXCLUSIVE. An INCLUSIVE company would see inclusive totals in the UI and exclusive totals after save. | Yes | New **D-6**; `QOE-02/04` must not send `priceMode` to orders until decided. |
| C-3 | `POST /sales/invoices/preview-totals/` already exists (`_preview_bundle` → `build_totals_preview`) and runs the full tax engine. **But** `build_totals_preview` takes `unit_price` from the request or `product.selling_price` — it never receives the customer, so price lists/slabs are ignored. | Yes | `QOE-01` fixes and extends this endpoint instead of adding `/sales/price-preview/`. |
| C-4 | `core/idempotency.py` has `wrap_idempotent(...)` (used by quotations) which **stores deterministic 4xx**; `SalesInvoiceViewSet.create` **releases the key on any non-201**. Also `MONEY_IDEMPOTENCY_SCOPES` controls in-flight reclaim behaviour. | Yes | `QOE-12a` must pick the invoice-style flow deliberately; add scopes to the set. |
| C-5 | `SalesOrderViewSet` has **no** `AuditService.log("sales.order.create")` (my earlier text was wrong). Audit comes from `CompanyScopedViewSet._audit_raw`, which passes no metadata. | Yes | Add a metadata hook in the base viewset. |
| C-6 | `SalesInvoiceViewSet.get_queryset` filters params by hand (`status, customer, invoice_type, date_from, date_to, q`); `?salesperson=` is a no-op. Historic invoices have `salesperson = NULL`. | Yes (code read) | `QOE-06` uses an OR filter. |
| C-7 | `ProductSerializer` exposes `unit_name` but **not** `uqc_code`. | Yes | `QOE-07` adds `unit_uqc` + cache bust + TS type. |
| C-8 | `SalesOrderViewSet.get_queryset` only filters `status`; `SalesOrdersPage` sends `q`, `date_from`, `date_to` (ignored), Customer 360 filters by `customer`. | Yes | Added to `QOE-12a`. |
| C-9 | `SalesOrderViewSet.confirm` has no idempotency; `confirm_sales_order` raises a generic `BusinessRuleError` with no code for "already confirmed". | Yes | Added to `QOE-12a`. |
| C-10 | Real query keys: `['sales-orders']` (list: `['sales-orders', page, status, q, from, to]`), `['sales-order', id]`, **`['sales-orders-open']`** (delivery-route dialog; separate top-level key), `['delivery-routes']`, `['route-combine']`, `['sales-order-stock', ids]`. `invalidateQueries({queryKey:['sales-orders']})` prefix-matches the paged list but **not** `sales-orders-open`. | Yes | Final list in `QOE-05`. |
| C-11 | Flags: per-company staged flags belong in `COMPANY_ROLLOUT_KEYS` (like `QUOTE_LIFECYCLE`); env flags need `ENV_FLAG_KEYS` + settings + `web/src/config/featureFlags.ts` `MOCK_FLAGS`. In Vitest `isRuntimeFlagEnabled` is false unless mocked. | Yes (code read) | `QOE-15`, test setup. |
| C-12 | **Rejected claim:** "Test 3 seeds `localStorage`". It does not — it adds a product via search, then expects the recents chip to appear immediately. | Yes | Do **not** move `saveRecentSku` to `onSuccess` (see `QOE-03`). The re-promotion concern is handled by hydration pruning instead. |

---

## Part B — Decisions (resolve at kickoff, recommendations included)

| ID | Question | Recommendation | Decide by | Unblocks |
|---|---|---|---|---|
| **D-0** | What did QOS-0048 intend? | Read `qos/backlog/QOS-0048.yaml` acceptance criteria. If it says "draft invoice/bill", take the **rename path** (Quick Bill) and skip `QOE-02` order mode and `QOE-12b`. | Product, day 1 | D-1 |
| **D-1** | Order, draft invoice, or both? | Both, behind a flag (`QOE-15`): default **Order**, secondary **Save as draft bill**. | Product | `QOE-02`, `12b` |
| **D-2** | After save? | **Save & Next** (stay, reset, link) + **Save & Open**. | Product | `QOE-08` |
| **D-3** | Who confirms a Quick Entry order? | **Option (c):** auto-confirm only if gates pass; otherwise leave DRAFT and show "Needs approval: <reason>". Needs `ENABLE_ORDER_GATES` semantics reviewed: `confirm_sales_order` runs `assert_chronic_credit_allowed` + `apply_order_gates` then reserves stock. | Product + Ops | `QOE-02` |
| **D-4** | Rep attribution | See V-7 row above. | Product | `QOE-13` |
| **D-6** | **(new)** Should `SalesOrder` get a `price_mode` column (default EXCLUSIVE, migration, serializer field, used by `set_order_items`, copied on convert-to-invoice)? | **Yes if any tenant uses INCLUSIVE pricing** (check `Company.price_mode` usage). Otherwise lock Order mode to EXCLUSIVE and show a notice for INCLUSIVE companies. Until decided, **never send `priceMode` on orders**. | Product + Eng | `QOE-02`, `QOE-04`, `QOE-12a` |
| **D-5** | Decimal quantities | See V-8 row above. | Product | `QOE-07` |

---

## Part C — Work packages

Dependency summary (details in Part D): `QOE-00` and `QOE-12a` first and in parallel; `QOE-04/05/06/03/01` can run in parallel after `QOE-00` (`QOE-04` totals display depends on `QOE-01`); `QOE-02` needs D-0/1/3/6, `12a`, `05`; R2 items are independent of each other except `14` after `08`.

---

### QOE-00 · Stop sending implicit price / GST (hotfix) — P0, S

**Goal:** the backend, not the browser, decides unit price, GST rate and cess.

**Why it is safe:** `_build_items` (`sales/services.py`) uses `resolve_unit_price(customer, product, requested_price=line.get("unit_price"), …)` and `gst_rate = line.get("gst_rate", product.gst_rate)`, `cess_* = line.get(…, product…)`. Omitting the keys makes it use the customer price list/slab and the live product rates. Serializer must accept missing `unit_price`/`gst_rate` — **verify first** by posting an item with only `{product, quantity}` in a test.

**Files:** `web/src/pages/sales/QuickEntryPage.tsx`, `QuickEntryPage.test.tsx`; backend test in `backend/tests/` (e.g. new `test_quick_entry_pricing.py`).

**Steps**
1. In `save` mutation, map items to `{ product: l.productId, quantity: l.quantity }` only. Delete `unitPrice` and `gstRate` from the payload.
2. Keep `unitPrice`/`gstRate` on `QuickLine` for display. Add a small caption under the footer total: "Prices and tax are confirmed when the order is saved" (new i18n key `quickEntry.priceNote`, en + hi) until `QOE-01` lands.
3. Update test 2: expect `items: [{ product: 7, quantity: 2 }]` and assert `unitPrice`/`gstRate` are **absent** (`expect.not.objectContaining`).
4. Backend test (the real regression guard):
   - Fixture: customer with price list; product `selling_price=100`; slab price 80.
   - `POST /sales/invoices/` with `items:[{product, quantity:1}]` → saved `unit_price == 80`.
   - Second case: product `gst_rate` changed 12→18 after "caching"; item posted without `gst_rate` → saved 18.
   - Third case (documents the intentional rule): posting `unit_price=100` still saves 100 (B8-031) — so the test pins that omission, not clamping, is what fixes it.
5. Run: `cd web && npx tsc -b && npx vitest run src/pages/sales/QuickEntryPage.test.tsx`; backend: `pytest backend/tests/test_quick_entry_pricing.py` (use the private test DB trick from project notes).

**Acceptance:** wholesale customer billed list/slab price from Quick Entry; stale cached GST can never be saved.
**Risks:** `productId` lines for products with no list price fall back to `selling_price` — same as today. A rep can no longer override price here (nor could they intentionally before; there is no price edit UI).
**Rollback:** revert the single mutation mapping.
**Definition of done:** tests green; `docs/FREEZE_SCOPE_COVERAGE.md` row for QOS-0048 updated.

---

### QOE-12a · Backend `SalesOrder` / `DeliveryChallan` parity — guards, idempotency, tax, defaults, filters — P0 security, L (absorbs former 12b)

**Goal:** `/sales/orders` and `/sales/challans` have the same safeguards as `/sales/invoices`, and orders are usable from Quick Entry (defaults, search). Merged with the former `QOE-12b` because both edit `SalesOrderSerializer`; the defaults are harmless for non-Quick-Entry callers. Ships **independently** of frontend work.

**Files:** `backend/sales/phase1_serializers.py`, `phase1_views.py`, `notes_services.py`, `backend/core/viewsets.py`, `backend/core/idempotency.py`, `backend/sales/models.py` + migration (only if D-6 = yes), `backend/tests/test_sales_order_guards.py` (new), OpenAPI snapshot + web types (regen).

**Step 1 — customer status gate**
1. Copy `SalesInvoiceSerializer.validate_customer` behaviour (`sales/serializers.py`): block only on create or customer change. Extract `assert_customer_active(customer, noun)` into `sales/` and use it from the three serializers.
2. `SalesOrderSerializer` and `DeliveryChallanSerializer` `.validate_customer`: after `check_company_ref`, call the helper when `self.instance is None or self.instance.customer_id != customer.pk`.
3. `SalesNotesService.confirm_sales_order`: raise `BusinessRuleError` (distinct code `customer_not_active`) before `assert_chronic_credit_allowed`/reservation. Same in the challan path if it moves stock.

**Step 2 — subscription gate**
`SalesOrderViewSet.get_permissions` and `DeliveryChallanViewSet.get_permissions`: write branch → `[IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales()]` (import already present). Reads unchanged.

**Step 3 — idempotency (create and confirm)**
1. **Use the invoice-style block, not `wrap_idempotent`** (C-4): `begin_record(scope="sales_order_create", fingerprint=request_fingerprint(request))` → `super().create` → on 201 `store_record(resource_id=…)` (unwrap `{success,data}` envelope as invoices do) → `finally: release_record` unless stored. Reason: the invoice flow releases the key on any non-201, so a rep can retry the same key after fixing a validation error; `wrap_idempotent` would replay the stored 4xx. Put it in a `IdempotentCreateMixin(scope)` used by the order viewset only (leave invoices untouched unless their tests stay green).
2. `confirm` action: same block with `scope="sales_order_confirm"` (keyed per order id via the fingerprint).
3. Add `"sales_order_create"` and `"sales_order_confirm"` to `MONEY_IDEMPOTENCY_SCOPES` so in-flight placeholders are not reclaimed while a stock-reserving transaction commits (confirm the set's semantics by reading its use at `idempotency.py` ~L101).
4. `confirm_sales_order`: when status is already `CONFIRMED`, raise `BusinessRuleError(..., code="order_already_confirmed")` so the client doesn't string-match English. Frontend `confirmSalesOrder` (`web/src/api/osPlan.ts`) gains `options?: {idempotencyKey?: string}`.

**Step 4 — audit metadata (C-5)**
`CompanyScopedViewSet._audit_raw` passes no metadata. Add an overridable `audit_metadata(self)` hook (default `{}`) passed to `AuditService.log(metadata=…)`; implement it on `SalesInvoiceViewSet` and `SalesOrderViewSet` to return `{"source": <allow-listed X-Client-Source>}` (`quick_entry`, `web`, `mobile`; unknown → `web`). Check `AuditService.log` accepts `metadata`; if not, add it (backward compatible).

**Step 5 — multi-GSTIN tax**
1. `set_order_items`: pass `seller_state=getattr(order.company_gstin,"state",None) or ""` and `seller_gstin=…` to `party_intra_state` (read its signature first; it already receives `supply_type`).
2. On create, default `company_gstin` with `_single_active_company_gstin(company)` when omitted.
3. Same fix in the challan item builder if it has the identical call.

**Step 6 — order defaults (former 12b, with corrected fields)**
1. Add to `SalesOrderSerializer`: `ship_to = serializers.PrimaryKeyRelatedField(queryset=CustomerShippingAddress.objects.all(), write_only=True, required=False, allow_null=True)`; restrict queryset to the company in `__init__`; `validate_ship_to` ensures `ship_to.customer_id == customer.pk`. **Pop `ship_to` in `create()`** — it is not a model field.
2. In `create()` if `delivery_address` is blank, resolve in order: `ship_to.address` → `customer.shipping_addresses.filter(is_default=True).first().address` → `customer.shipping_address` → `customer.billing_address` → `""`.
3. If `payment_terms_days` is **not in the request data** (not merely 0), set it from **`customer.credit_days`**.
4. Management command `list_orders_without_delivery_address` (read-only report) for existing data.

**Step 7 — order list filters (C-8)**
`SalesOrderViewSet.get_queryset`: add `customer` (int), `q` (number/customer name icontains), `date_from`/`date_to` on `order_date`, keep `status`. Validate dates (ignore/400 like invoices).

**Step 8 — price mode (only if D-6 = yes)**
Add `SalesOrder.price_mode` (default EXCLUSIVE), expose in serializer, make `compute_document_totals` see it (it already `getattr`s), copy to invoice in `convert_sales_order`, include in `createSalesOrder` type. Migration + backfill default. If D-6 = no: no change; frontend locks Order mode to EXCLUSIVE.

**Tests (`test_sales_order_guards.py`)**
- blocked / inactive customer → 400 on create; update without changing customer still works; confirm for newly-blocked customer → `customer_not_active`, `reserved_quantity` unchanged.
- expired subscription → 403/402 on create/confirm/convert/challan writes; GET 200.
- same key twice → one row, same body; failed (400) create releases key and a corrected retry with the same key succeeds; changed body + same key → conflict; confirm with same key twice → one reservation (Postgres).
- already confirmed → code `order_already_confirmed`.
- audit row has `metadata.source == "quick_entry"` for header; unknown → `web`.
- multi-GSTIN: CGST/SGST vs IGST by branch state.
- defaults: `ship_to` wins; default shipping address; fallback `shipping_address` then `billing_address`; `credit_days` used only when terms omitted; foreign-customer `ship_to` rejected; `RouteService.rollup` shows the address.
- filters: `q`, `customer`, `date_from/to`, `status` on `/sales/orders/`.

**Acceptance:** all pass on SQLite and Postgres; `tenancy/test_rbac_matrix.py`, endpoint-isolation and `test_business_rules.py` still green.
**Risks:** existing drafts for newly-blocked customers fail on confirm → ops report + release note. Wider `_audit_raw` change touches every viewset — keep the default `{}` identical to today's output; run the audit tests.

---

### QOE-04 · Invoice type and price mode (totals now come from `QOE-01`) — P1, S

**Goal:** documents created from Quick Entry are completable; the footer total comes from the server preview.

**Files:** `QuickEntryPage.tsx`, `invoiceDefaults.ts` (read only), tests, i18n.

**Steps**
1. Copy how `NewInvoicePage` calls `chooseInvoiceDefaults` / `inferInvoiceTypeFromParty` (inputs: company `registrationType`, customer GSTIN/type).
2. `useQuery(['company', companyId], getCompany, {staleTime: 5 min})` and `useQuery(['customer', id], getCustomer)` when a customer is chosen (needed for `gstin`, state, price list, shipping addresses; reused by `QOE-01/09`). Add both to the `@/api/resources` test mock.
3. Compute `invoiceType` (all modes) and `priceMode` (**invoice/bill mode only**). For orders send `invoiceType` but **not** `priceMode` unless D-6 = yes (C-2).
4. **Totals:** do not recompute tax on the client. Show the `QOE-01` preview totals. Until `QOE-01` ships, show Subtotal only with "Tax added on save". (`calculateInvoiceTotals` remains only as a last-resort offline display and must not claim HSN-slab accuracy.)
5. REGULAR company without GSTIN: completion fails with `COMPANY_GSTIN_REQUIRED` (V-1) → show a non-blocking warning with a link to GST settings.

**Tests:** Composition → payload `invoiceType:'NON_GST'`; INCLUSIVE company bill mode sends `priceMode:'INCLUSIVE'`; order mode omits `priceMode`; GSTIN warning. Backend integration: create `NON_GST` draft via API, `complete` succeeds.
**Acceptance:** Composition/Unregistered drafts complete; no inclusive/exclusive mismatch between screen and saved order.

---

### QOE-05 · Per-attempt idempotency key and cache invalidation — P1, S

**Goal:** retry-safe saves; lists refresh.

**Files:** `QuickEntryPage.tsx`, `api/legacy/sales.ts` (`createSalesOrder`), `invalidateInvoiceSideEffects.ts`, tests.

**Steps**
1. `createSalesOrder(payload, options?: { idempotencyKey?: string })` → `apiClient.post('/sales/orders/', payload, { headers: idempotencyHeaders(options?.idempotencyKey) })` (copy the invoice function).
2. In the page: `const attemptRef = useRef<{ key: string; sig: string } | null>(null)`. On save compute `sig = JSON.stringify({customer, mode, lines:[id,qty], note})`. If `attemptRef.current?.sig === sig` reuse its key, else generate a new one with `newIdempotencyKey()` and store. Clear `attemptRef` on success. (This makes a timeout-then-retry send the same key; editing the order changes the signature and the key.)
3. `inFlightRef`: `if (inFlightRef.current) return; inFlightRef.current = true;` in the click handler; reset in `onSettled`.
4. Invalidation: on invoice success call `invalidateInvoiceSideEffects(qc, invoice.id)`. For orders add `invalidateSalesOrderSideEffects(qc, orderId?, customerId?)` in `invalidateInvoiceSideEffects.ts` with exactly these verified keys (C-10): `['sales-orders']` (prefix-matches the paged list), `['sales-order', id]`, **`['sales-orders-open']`**, `['delivery-routes']`, `['route-combine']`, `['sales-order-stock']`, plus `['customer-360']`, `['customer']`, `['customers']`, `['dashboard']`, `['attention-rows']`, `['stock-balance']`, `['stock']`, `['products']`. If the order was auto-confirmed also invalidate `['stock-balance']`/`['stock']` (already listed). Always also invalidate `['quick-entry-recent', companyId, user.id]`. Test the helper by asserting each key with a spy on `invalidateQueries`.
5. Server dedupe is only as good as the fingerprint: confirm `request_fingerprint` includes the body so a changed payload with a reused key is rejected rather than replayed.

**Tests:** double click → 1 call; mutation rejects with network error then second click → second call carries the **same** key (assert via the mock's options arg); after editing quantity the key differs; success clears the ref; invalidate helper called (spy).
**Acceptance:** as in the review.

---

### QOE-06 · Per-rep active recents and state isolation — P1, S

**Goal:** a rep sees their own recent customers, none blocked; component state resets on company change.

**Files:** `QuickEntryPage.tsx`; backend: add `salesperson`/`created_by` filter support if missing (`sales/views.py` filterset); optionally new endpoint `GET /sales/quick-entry/recents/`.

**Steps**
1. Decide the data source. Preferred: a tiny endpoint `GET /sales/quick-entry/recents/` returning `{customers:[{id,name,status}], products:[{id}]}` for the current user (last 30 days, top 6 customers, 8 products) across orders **and** invoices, excluding non-ACTIVE customers and inactive products — one call replaces the 10-invoice fetch and the `localStorage` product list (also helps `QOE-03`). Fallback: keep `listSalesInvoicesPage({page:1,pageSize:30, salesperson: user.id})` plus filter by `status`.
2. Query key `['quick-entry-recent', companyId, user.id]`.
3. **Backend filter (C-6):** invoices — `Q(salesperson_id=user.id) | Q(salesperson__isnull=True, created_by_id=user.id)`; orders — `created_by_id=user.id`; both require `customer__status=ACTIVE` and `customer__is_deleted=False` (use the real soft-delete field name — check `Customer`). Historic invoices have `salesperson` NULL, hence the OR. `?salesperson=` is currently a no-op on `SalesInvoiceViewSet`, so the fallback path needs a hand-written filter in `get_queryset` too.
4. Replace the render-phase `seenCompanyId` block with a `useEffect` keyed on `companyId` that resets `customer`, `lines`, `pendingProduct`, `saveError`, draft (see `QOE-14`). (Even though `qc.clear()` runs on switch, component state survives.)
5. Show `Alert severity="warning"` with Retry when the recents query errors.

**Backend tests (if endpoint):** scoping by user and company; excludes blocked customers; excludes others' documents; max sizes.
**Frontend tests:** blocked customer not rendered; error alert shown; company change resets lines.
**Risk:** a brand-new rep has no recents → show hint text "Search a customer to begin".

---

### QOE-03 · Live hydration of recent products — P1, S

**Goal:** chips always reflect current product data; inactive items vanish.

**Steps**
1. Backend: add `?ids=` (comma list, max 50, ints only, 400 otherwise) to `ProductViewSet.get_queryset` (`masters/views.py`, the block that reads `status`/`search`); respect `CanViewMastersCatalog`. Test: scoping by company, cap, invalid input. (If `QOE-06`'s recents endpoint exists, return product summaries there instead and skip this.)
2. Frontend: store only `{id, name, sku}` in `localStorage['bizboard:quick-entry-recent-skus:<companyId>']` (bump the key to `…-v2`; ignore/clear old entries on read).
3. On mount: `useQuery(['products','recent',companyId, ids], () => listProducts({ids}))`. Render chips from the response; any stored id missing or `status !== 'ACTIVE'` is removed from storage in an effect.
4. **Keep `saveRecentSku` at add-time** (C-12): existing Test 3 relies on the chip appearing right after a product is added. It now stores `{id, name, sku}` only. The earlier "re-promotion of rejected products" concern is covered by hydration, which prunes inactive/missing ids on the next load.
5. Display price/GST from the fetched record (display only, per `QOE-00`).

**Tests:** seeded old-format (v1) entry ignored/cleared; inactive pruned after hydration; price shown is the server's. **Existing Test 3** keeps working only if the `@/api/resources` mock also provides the hydration call (`listProducts({ids})` returning the product) — update the mock and keep the key bump to `-v2` in the same commit.

---

### QOE-01 · Authoritative preview via the existing `preview-totals` endpoint — P1, M

**Goal:** the screen shows the exact price, tax and totals that will be saved, from one backend source. Replaces both the proposed `/sales/price-preview/` endpoint and the client-side tax math of the old `QOE-04` (C-3).

**Backend — fix and extend `POST /sales/invoices/preview-totals/`**
1. In `_preview_bundle` (`sales/views.py`) you already have `customer`. Pass it (and `request.user` role = `None`) into `build_totals_preview(...)` (`core/services/tax_engine/india.py`, new kwarg `customer=None`).
2. In the item loop, when `raw` has no `unit_price` **and** `customer` is set: `unit_price = resolve_unit_price(customer=customer, product=product, requested_price=None, role=None, quantity=raw["quantity"])`, and `_p, list_name = resolve_party_price(...)`. Keep today's behaviour when `unit_price` is supplied or no customer (so `NewInvoicePage`/POS callers that send explicit prices are unaffected).
3. Return per item (verify the current response shape first and add an `items[]` array if absent): `unit_price`, `applied_price_list_name`, `gst_rate`, `cess_rate`, `cess_amount`, `unit_name`, `uqc_code`, and — when `include_stock=1` or always for sales-create roles — `available_qty` (default warehouse, same helper the product label uses; omit if unavailable). Do not expose cost/margin to roles without `CanViewFinancialReports` (existing `include_margin` logic).
4. Because this endpoint is shared, add regression tests for `NewInvoicePage`-style calls: explicit price unchanged; no price + customer with list → list price (this is a bug fix for other screens too — mention in release notes); no customer → selling price.
5. Parity test: `preview-totals` result for `{customer, items:[{product, quantity}]}` equals the totals of the invoice created by `POST /sales/invoices/` with the same body (all of `subtotal, cgst/sgst/igst, cess, round_off, grand_total`), including an HSN value-slab case (e.g. apparel over the threshold) that client-side math cannot replicate.
6. Permissions: unchanged (reads, no `SubscriptionWritesAllowed`). Regenerate OpenAPI + types.

**Frontend**
1. Use existing `previewSalesTotals` (`api/legacy/sales.ts`); extend its type with the new per-item fields.
2. `useQuery(['qe-preview', companyId, customerId, invoiceType, signature(lines)], …, {enabled: customerId && lines.length, placeholderData: keepPreviousData})` with a 300 ms debounced signature; ignore stale responses by signature.
3. Merge into line display (`unitPrice`, `priceListName`, `gstRate`, `availableQty`, `unitName`, `uqc`), and the footer uses the **server totals** (Subtotal / GST / Round-off / Grand total). On error: fall back to catalog price with "indicative" note and hide tax lines.
4. Order mode: preview is computed as an invoice-type document, which is EXCLUSIVE unless `price_mode` is passed; honour **D-6** — for orders send `price_mode` only if D-6 = yes, else force EXCLUSIVE and show a notice for INCLUSIVE companies.
5. Fallback if the extension is rejected: `resolveListUnitPrice` for the selected customer's single price list (V-4 parity confirmed) — price only, no tax.

**Tests:** slab crossing updates price; list name chip; error fallback; stale-response ignored; totals shown equal mocked server totals; flag off (`QUICK_ENTRY_PRICE_PREVIEW`) → old display. In Vitest, mock `previewSalesTotals` and the flag helper (C-11).
**Acceptance:** displayed equals saved to the paisa.
**Risk:** touching a shared endpoint → keep the new behaviour strictly opt-in by "unit_price omitted + customer present".

---

### QOE-12b · (merged into QOE-12a)

Order defaults (delivery address, payment terms, `ship_to`) are now Step 6 of `QOE-12a`, with corrected field names (`credit_days`, `shipping_address`, `billing_address`, `shipping_addresses`).

---

### QOE-02 · Order vs draft-bill mode — P0 decision, M

**Preconditions:** D-0/1/3 decided; `12a`, `12b`, `05` merged; flag `QUICK_ENTRY_ORDER_MODE` exists (`QOE-15`).

**Steps**
1. UI: segmented control "Order | Draft bill" under the customer card (hidden when the flag is off → bill-only behaviour with renamed labels from D-0). Persist last choice per user in `localStorage` (try/catch).
2. Save handler switches on mode: Order → `createSalesOrder({customer, orderDate: todayIso(), invoiceType, priceMode, deliveryAddress?, shipTo?, notes, items:[{product,quantity}]}, {idempotencyKey})`; Bill → `createSalesInvoice(...)`.
3. (Prereqs: `QOE-12a` Step 3 gives `confirm` an idempotency key and the `order_already_confirmed` code.) D-3(c): after order create, if the flag `QUICK_ENTRY_AUTO_CONFIRM` is on call `POST /sales/orders/:id/confirm/`. Handle outcomes: success → "Order SO-123 confirmed, stock reserved"; gate failure (credit hold / margin approval) → keep DRAFT, show "Saved as draft — needs approval: <message>" with link; do **not** treat as an error toast. Confirm uses its own idempotency (a repeated confirm on a CONFIRMED order returns 400 "Cannot confirm…" — treat as success when the response code is `order_already_confirmed`; do not string-match the message). Pass an idempotency key to `confirmSalesOrder`.
4. i18n en/hi: `quickEntry.save.order`, `quickEntry.save.bill`, success/needs-approval strings. Update the context-help entry and `faqContent.tsx`.
5. Navigation per D-2: Save & Next / Save & Open to `/sales/orders/:id` or `/sales/history/:id`.

**Test setup:** mock the flag helper (`isRuntimeFlagEnabled`) — in Vitest it is false unless mocked (C-11); mock `createSalesOrder`, `confirmSalesOrder`.
**Tests:** each mode calls the right API with an idempotency key; order payload has no `priceMode` unless D-6 = yes; confirm outcomes (confirmed / gated / confirm error); labels name the document; flag off hides toggle.
**Acceptance:** an order created here appears in `/sales/orders`, counts in `sales_order_exposure`, and (when confirmed) reserves stock.

---

### QOE-07 · Inline quantity, unit-aware decimals, safe stepper — P1, S

**Steps**
0. **Prerequisite (C-7):** add `unit_uqc = serializers.CharField(source="unit.uqc_code", read_only=True)` to `ProductSerializer` (`masters/serializers.py`; it currently exposes only `unit_name`), bust `masters:products:{company}:*` list cache, add `unitUqc?: string` to `Product` in `web/src/types/domain.ts`, regenerate OpenAPI types, and add a serializer test. (If `QOE-01` returns `uqc_code` per item, use that for lines and this field for search results/chips.)
1. Add helper `quantityPolicy(unitUqc)` in `web/src/utils/quantity.ts`: `{ decimals: boolean, min: number, step: number }` — decimals only for the D-5 set; else integers, min 1.
2. Line row: stepper `−` / numeric `TextField` (`inputMode="decimal"` or `"numeric"`) / `+`. Keep text state while typing (so clearing the box doesn't delete the line); commit on blur/Enter; invalid or below min → revert and show helper "Minimum 1".
3. `bump()` clamps at `min` instead of filtering; deletion only via trash button; deleting shows a Snackbar "Removed <name> · Undo" restoring the line at its index.
4. Backend untouched (`_validate_lines` already enforces > 0).

**Tests:** type 50; type 2.5 on kg accepted, on pcs rejected; `−` at 1 stays; undo restores; empty input doesn't delete.

---

### QOE-08 · Save & Next, leave guard, URL prefill — P2, S

**Steps**
1. `const [leaving, setLeaving] = useState(false)`; `<UnsavedChangesGuard when={lines.length > 0 && !leaving} interceptLinks />`.
2. **Save & Open:** `onSuccess` → `setLeaving(true)` then navigate in an effect keyed on `leaving`/`pendingNav` (so the blocker sees `when=false` at navigation time). **Save & Next:** reset `customer`, `lines`, `note`, attempt ref; set `lastSaved = {id, number, kind}` to render a dismissible success `Alert` with `RouterLink`.
3. Because Back can't be intercepted on `BrowserRouter` (V-6) rely on `QOE-14` for that case.
4. `useSearchParams`: `?customer=<id>` → fetch customer; accept only ACTIVE and same-company (a 404/other tenant → ignore silently). `?product=<id>` → add line once (guard with a ref to avoid StrictMode double-add).

**Tests:** guard prompts with lines; no prompt after save; Save & Next resets and shows link; prefill works; invalid id ignored.

---

### QOE-14 · Draft persistence — P1, M

**Steps**
1. Read `web/src/lib/deviceDraft.ts` (used by POS and `AuthContext`) and reuse its API/namespace; if it is POS-specific, write the same pattern with `sessionStorage` key `bizboard:quick-entry-draft:<companyId>:<userId>`.
2. Persist `{customerId, mode, note, lines:[{productId, quantity}], updatedAt}` on change (debounced 400 ms, try/catch for blocked storage). Never store prices.
3. On mount, if a draft exists younger than 12 h: show `Alert` "Resume your unsaved order for <customer>?" with Resume / Discard. Resume re-fetches products/customer (customer must still be ACTIVE; drop inactive products with a note).
4. Clear on successful save, on Discard, on company/user change, and on logout (hook into the same place `deviceDraft` clears).

**Tests:** persist & restore; discard; expires; other user/company ignored; blocked storage doesn't throw.
**Scope note:** no queued offline submit (QOS-0048 exclusion stands).

---

### QOE-09 · Context on lines, credit hold, ship-to, note — P2, S

**Steps**
1. Product autocomplete label via `formatProductOptionLabel(p, avail)`; chips show `name · sku` and a `×qty` badge when already in the order.
2. Line card: name + sku caption; `₹price / unit`, line total; low-stock warning chip when quantity > `availableQty` (from the `QOE-01` preview; respects negative-stock setting — if allowed, show info instead of warning).
3. Credit: when the customer is loaded, `CreditHoldChip` for hold status; use `creditExposure.ts` helper to warn "This order would exceed the credit limit" (client-side, advisory; server gates remain authoritative at confirm).
4. Ship-to: if the customer has >1 shipping addresses (from `getCustomer`), a `Select` defaulting to the default one → `shipTo` in order payload (`QOE-12a` Step 6).
5. Optional note `TextField` (single line, maxLength per backend `notes` field) included in payload.

**Tests:** same-name variants distinguishable; low-stock warning; credit chip; ship-to default and change; note sent.

---

### QOE-10 · Locale, helper text, touch targets, ARIA — P3, S

**Steps:** `useLocale()` at component top; pass `helperText={productSearch.helperText}` and the customer equivalent; handle `reason === 'reset'`; icon buttons `size="medium"` with `sx={{ width: 44, height: 44 }}` and `gap` ≥ 1.5 between `+` and delete; aria-labels `t('quickEntry.increase') + ' ' + name`; truncated names get `title` and a second line for SKU.
**Tests:** locale toggle rerenders; helper text at 1 char; aria-label contains product name; axe check if the repo has an a11y test helper (see UX programme notes; Wave 1 a11y tests).
**Manual:** 360×640 mobile viewport check.

---

### QOE-13 · Entry links and attribution — P2, S (after Customers work lands)

**Steps**
1. `Customer360Page.tsx`: add **Quick order** button → `/sales/quick-entry?customer=${customerId}` (gate with `canCreateSales`). `SalesOrdersPage.tsx`: header button **Quick entry**. Add tests in `Customer360Page.test.tsx`; add i18n and menu/help text.
2. Backend invoice create: if `salesperson` not supplied, default `salesperson = request.user` (in `SalesInvoiceViewSet.perform_create` or serializer `create`). Test that explicit value (valid active CompanyUser) still wins and invalid user is rejected as today.
3. Orders: **no `salesman`/`sales_channel` defaults** (D-4). Send header `X-Client-Source: quick_entry` from `apiClient` call options; backend allow-lists values (`quick_entry`, `web`, `mobile`) and puts it in `AuditService.log(... metadata={"source": …})` for both invoice and order create. Unknown values → `web`.
4. Reports: no change; note in docs that attribution is via audit `source`.

---

### QOE-15 · Rollout, rollback, metrics, comms — P1, S

**Steps**
1. Register the three flags (`QUICK_ENTRY_ORDER_MODE`, `QUICK_ENTRY_AUTO_CONFIRM`, `QUICK_ENTRY_PRICE_PREVIEW`) as **per-company staged-rollout flags** in `COMPANY_ROLLOUT_KEYS` in `backend/core/services/feature_flags.py`, the way `QUOTE_LIFECYCLE` is declared (default false; enabled per pilot tenant through `company.feature_flags`). Only use `ENV_FLAG_KEYS`/`ROLLOUT_GRANTABLE_KEYS` (which also need `config/settings.py` entries) if product wants a global kill switch. Add matching entries to `MOCK_FLAGS` in `web/src/config/featureFlags.ts`. Test setup: mock `isRuntimeFlagEnabled` or call the fetch helper — it returns false by default in Vitest. Add a backend test that the flags default off and flip per company.
2. Not flagged (they are fixes): `QOE-00`, `12a`, `04`, `05`, `06`, `07`, `10`.
3. Telemetry via `lib/telemetry` (`trackShopFloor`): events `quick_entry_started`, `quick_entry_saved {mode, lines, ms}`, `quick_entry_error {code}`, `quick_entry_draft_resumed`, `quick_entry_gate_blocked`. Check the telemetry allow-list (PII: no names/amounts).
4. Pilot: enable flags for 1–2 tenants; review after 1 week: price mismatches (audit sample of 20 docs vs price lists), duplicate docs (should be 0), error rate by code, median time-to-book.
5. Comms: release notes (where orders go; blocked-customer validation; new Save & Next); update `contextHelp` + `faqContent.tsx` (en/hi); ops note for pre-existing blocked-customer drafts.
6. Rollback runbook: flags off → bill-only; hotfix commits revert independently.

---

### QOE-11 · Verification gate — P1, S

Run before each release (R0, R1, R2):

| Gate | Command / check |
|---|---|
| G1 | `cd web && npx tsc -b && npm run lint` (0 errors) and `npx vitest run src/pages/sales src/hooks src/utils` |
| G2 | `pytest` for new + `tenancy/` + `test_business_rules.py`; Postgres run for idempotency/concurrency tests |
| G3 | `manage.py spectacular` snapshot and web types regenerated and committed (CI diffs both) |
| G4 | `qos-lint` green; QOS-0048 and `FREEZE_SCOPE_COVERAGE.md` updated |
| G5 | Manual: 360×640 viewport — touch targets, numpad, leave guard, draft resume, Hindi, slow-network retry (DevTools throttle + offline during save) |
| G6 | Cross-module smoke: new order visible in `/sales/orders`, Customer 360, dashboard counts; route stop shows delivery address; blocked customer rejected |

---

## Part D — Execution schedule

| Phase | Packages | Parallel? | Gate |
|---|---|---|---|
| **0 — Prep (day 0–1)** | Resolve D-0…D-5; land/commit Customers-plan WIP; create flags | — | decisions recorded in QOS-0048 |
| **R0 — Hotfix + security (week 1–1.5)** | `QOE-00` (S) ‖ `QOE-12a` (L, now includes former 12b: defaults, filters, confirm idempotency, audit hook) | yes | G1–G4 |
| **R1 — Correctness (weeks 1–3)** | `QOE-04`, `05`, `06`, `03`, `01` (parallel, frontend page owner serialises merges); then `02` (after D-0/1/3/6 and `12a`) | partly | G1–G6 |
| **R2 — Ergonomics (weeks 3–4)** | `07`, `08` → `14`; `09`, `10`, `13` | yes | G1–G6 |
| **Rollout** | `QOE-15` pilot → widen | — | pilot exit criteria |

**Merge-conflict note:** `QOE-00/03/04/05/06/07/08/09/10/14` all edit `QuickEntryPage.tsx`. Refactor first (S, part of `QOE-00`): split the page into `QuickEntryPage.tsx` (container), `useQuickEntryDraft.ts`, `QuickEntryLines.tsx`, `quickEntryTotals.ts` so packages touch different files.

**Total effort estimate (revision 2):** R0 ≈ 5–6 d · R1 ≈ 6–8 d (no separate 12b; `QOE-01` is smaller because it reuses `preview-totals`, but touches a shared endpoint) · R2 ≈ 5–6 d · QOE-15 ≈ 1 d (single engineer ≈ 3.5–4 weeks; two engineers ≈ 2–2.5 weeks with backend/frontend split).

---

## Part E — Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Tightened `SalesOrder` validation blocks existing workflows for blocked customers | Med | Med | Validate only on create/customer-change; confirm-time check; ops report; release note |
| Auto-confirm surprises reps with approvals | Med | Med | Flag, clear "needs approval" state, pilot first |
| Preview/saved price drift | Low | High | Same backend functions; parity test; show "indicative" on error |
| Idempotency fingerprint ignores body | Low | High | Verify `request_fingerprint` content; test changed-body-same-key |
| Large merge conflicts in page file | High | Low | Split file in `QOE-00`; merge order per Part D |
| Telemetry leaks PII | Low | Med | IDs/counts only; review allow-list |
| Draft storage restores stale/inactive data | Med | Low | Re-validate on resume; 12 h expiry |
