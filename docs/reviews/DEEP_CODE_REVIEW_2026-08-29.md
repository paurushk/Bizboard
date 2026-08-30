# Bizboard — Deep Code Review (2026‑08‑29)

Reviewer: automated deep pass (Claude). Branch: `wip/phase0`.

Scope target: every module / file, risk‑ordered. This document is built in **waves**.
Each finding: `ID | Severity | file:line | title` then description + suggested fix.
Severities: **BLOCKER** (data loss / money wrong / cross‑tenant leak / auth bypass),
**HIGH** (wrong output in common path, silent failure), **MEDIUM** (edge‑case bug, weak
guard, compliance gap), **LOW** (style, defensive, cosmetic), **UX** (frontend/UX).

> Note: the codebase already carries hundreds of prior `BB‑xxxxx` / `BUG‑xxx` fixes and
> is defensively written. Findings below are *new* observations from this pass; some are
> "verify" items where the surrounding call‑sites must be checked to confirm impact.

---

## Wave 1 — Core infra, tenancy, tax engine

### Configuration / settings

**R1-001 | LOW | backend/config/settings.py:369**
`from celery.schedules import crontab` is imported mid‑module instead of at the top with
the other imports. Harmless but violates the file's own import ordering and trips linters
that aren't silenced here.

**R1-002 | LOW | backend/config/settings.py:376**
`CELERY_ENABLE_UTC` defaults to `0` (False) while `CELERY_TIMEZONE="Asia/Kolkata"`. Celery
strongly recommends UTC internally with a display timezone. Running beat in local time
across the March/November DST‑free but *leap‑second / clock‑change* windows is fine for
India, but any future non‑IST worker will compute schedules incorrectly. Prefer
`CELERY_ENABLE_UTC=1` + `CELERY_TIMEZONE` for display only.

**R1-003 | MEDIUM | backend/config/settings.py:435, core/views (metrics)**
`METRICS_TOKEN` defaults to `""`. Confirm the `/metrics` (and `bump_request_count`)
endpoint *refuses* to serve when the token is unset rather than serving unauthenticated.
An empty configured token that is compared with `==` to a missing header can pass.
(Verify in `core/views.py`.)

**R1-004 | LOW | backend/config/settings.py:203-209**
`MinimumLengthValidator` is used with no `OPTIONS={"min_length": …}`, so the minimum
password length is Django's default of **8**. For an accounting product handling money a
10–12 char minimum is more appropriate.

### Authentication

**R1-005 | MEDIUM | backend/core/authentication.py:20-33**
`CookieJWTAuthentication.authenticate` calls `SessionAuthentication().enforce_csrf(request)`
*after* `get_user(validated)`. If CSRF fails the DB hit for the user has already happened
(minor), but more importantly `enforce_csrf` is only invoked on the **cookie** path — the
dev‑only Bearer path (`header is not None and not cookie_only`) returns
`super().authenticate(request)` with **no CSRF check**. That is documented as intentional,
but note that in `DJANGO_ENV=development`/`test` a browser‑delivered request that happens
to send *both* a valid `Authorization` header and cookies will skip CSRF. Low real risk
(dev only) — worth a comment or an explicit "reject Bearer when Origin present" guard.

**R1-006 | MEDIUM | backend/core/middleware.py:52-66 (RequestIdMiddleware)**
The JSON access log resolves `request.user` from the raw `WSGIRequest`. DRF sets the
authenticated user on its own `Request` wrapper, and depending on DRF version it may not
propagate to `request._request.user`. Result: `user_id` / `company_id` in the structured
access log are frequently blank for authenticated API calls, undermining audit/log
correlation. Verify by hitting an authenticated endpoint and checking the emitted line.

**R1-007 | MEDIUM | backend/core/permissions.py:17-48 (get_company_user caching)**
The result is cached on `request._company_user` and the guard is
`if hasattr(request, "_company_user")`. A `None` result is therefore cached permanently.
`PostgresRlsMiddleware` (when `POSTGRES_RLS_ENABLED`) and `RequestIdMiddleware` both call
`get_company_user(request)` *before* DRF authentication runs for the **Bearer** path
(middleware only manually authenticates the *cookie* JWT). In an RLS‑enabled non‑prod
deployment using Bearer tokens, `None` is cached, then every downstream `HasCompany`
check returns 403 for a valid user. Fix: don't cache `None`, or key the cache on
`request.user.pk`.

**R1-008 | MEDIUM | backend/core/permissions.py:38-46**
A user with **2+ active memberships and no `active_company`** gets a hard
`CompanyContextConflict` (409) on *every* endpoint until they call switch‑company. There
is no implicit "most recently used" fallback and the 409 body is generic. Combined with a
frontend that doesn't special‑case this code, such users are locked out. Confirm the SPA
handles `company_context_conflict` with a company‑picker.

**R1-009 | LOW | backend/core/rls.py:13-31 & core/middleware.py:95-118**
`set_rls_company` uses `set_config(..., is_local=false)` so the GUC persists on the
pooled connection. `PostgresRlsMiddleware` sets it per request, but if an **exception is
raised before** the middleware runs (e.g. in an earlier middleware) or for a path that
short‑circuits, the previous request's `app.company_id` remains set on that connection.
With `conn_max_age=600` and no connection pooler resetting GUCs, a later unauthenticated
or differently‑scoped request that fails to overwrite the GUC inherits the prior tenant's
value. RLS is "off until soak", but before enabling it: set the GUC to `''` at the *start*
of every request (fail‑closed) and/or in a `finally`.

### Idempotency

**R1-010 | MEDIUM | backend/core/idempotency.py:181-202 (wrap_idempotent)**
On any non‑2xx response the in‑flight placeholder is deleted (`release_record`). That means
a deterministic `400`/`409`/`422` (e.g. validation failure) is **not** replayed — a client
retrying the same bad request with the same key does the full work again. More important:
a `500` also releases, so a retry after a server error that *did* commit a side effect
(e.g. row created, then serialization failed) will **double‑create**. Idempotency keys
should retain terminal 4xx and should retain 5xx that occurred after the atomic block
committed. Consider storing the outcome for 4xx and only releasing on pre‑commit failure.

**R1-011 | LOW | backend/core/idempotency.py:104-118**
Stale‑takeover threshold is a hard‑coded `15 * 60` seconds and duplicated in three places
(here and implicitly in comments). If a legitimate long operation (large import, e‑invoice
round‑trip) exceeds 15 min, a client retry will `existing.delete()` the still‑running
record and start a **second** execution. Make the TTL a named constant and size it above
the slowest protected operation.

**R1-012 | LOW | backend/core/idempotency.py:29-35**
`get_cached_response` / `store_response` are dead stubs that always return `None`. If any
caller still relies on the old cache path it now silently has *no* idempotency. Grep for
callers and delete, or make them raise.

### Document numbering

**R1-013 | HIGH | backend/core/services/document_numbers.py:194, 212, 233, 269**
`fy_label` is derived **only when `gstin_key or on_date is not None`**. Whether a document
lands in the FY‑scoped series (`GSTIN/2526`) or the legacy company‑wide series (`""/""`)
therefore depends on whether the caller passes `gstin=`. If sales/purchase completion
sometimes resolves a `CompanyGstin` and sometimes doesn't (e.g. company has no
`CompanyGstin` rows yet, or `resolve_series_gstin` returns `None`), the *same doc_type for
the same company* allocates from **two different sequences**, producing visibly
non‑contiguous invoice numbers within one FY (a GST audit red flag) and, if prefixes ever
coincide, true duplicates. Fix: decide FY‑scoping by a single company‑level policy, not by
argument presence; always pass a resolved series identity.

**R1-014 | MEDIUM | backend/core/services/document_numbers.py:270-283 (next_number)**
`select_for_update()` on the `DocumentSeries` row is taken inside the caller's outer
transaction and held until that outer transaction commits. If invoice completion does
slow work *after* number allocation inside the same transaction (PDF render, e‑invoice
HTTP, ledger postings), **all concurrent completions for that company+series serialize**
behind the row lock for the full duration. Allocate the number as late as possible, or in
a short dedicated transaction with a gap‑tolerant design.

**R1-015 | MEDIUM | backend/core/services/document_numbers.py (FY rollover)**
At an FY boundary a fresh `DocumentSeries` row starts at `next_number=1`. `sync_next`
(which would continue after the max existing document) is explicitly *not* on the hot
path. A company that was numbering on the legacy `""/""` series and then gains a
`CompanyGstin` mid‑year abruptly jumps to a new series at `00001`. The old and new
prefixes differ (`INV‑…` vs `INV‑2526‑1234‑…`) so no DB collision, but the numbering
discontinuity is a compliance/UX problem with no warning surfaced to the user.

### Tax / money engine (`core/services/billing.py`, `core/services/charges.py`)

**R1-016 | MEDIUM | backend/core/services/billing.py:193-200 vs backend/core/models.py:98**
`core/models.py` documents `cess_amount` as *"specific (per‑unit) cess; when > 0
**overrides** percentage cess_rate"*. But `_apply_line_tax` **adds** them:
`item.cess = q2(ad_valorem + specific)`. `extract_exclusive_from_inclusive_line`
(lines 229‑232) also treats them additively. Either the model comment is wrong or every
consumer that reads `cess_amount` as an override (e‑invoice payload, GSTR builders) is
inconsistent with the invoice total. Pick one semantic and make model doc + all builders
agree.

**R1-017 | MEDIUM | backend/core/services/billing.py:375-383, 193-202**
NIL / EXEMPT / NON_GST lines zero `gst_rate` and `_billing_rate` but **not** `cess_rate`
/ `cess_amount`. `_apply_line_tax` computes cess whenever `tax_enabled` is true, so an
exempt line that carries a stray `cess_rate` still accrues cess into `cess_total` and the
grand total. Exempt/nil supplies must not attract cess. Zero cess for those natures too.

**R1-018 | MEDIUM | backend/core/services/billing.py:355-373, 479**
For `price_mode == "INCLUSIVE"`, `item.unit_price` is overwritten with the tax‑exclusive
unit, then `subtotal += gross` where `gross = q2(qty * exclusive_unit)`. So
`document.subtotal` for an inclusive‑priced invoice is the **exclusive** sum, while
`discount_total` is computed from the **inclusive** gross (`_inclusive_discount_amount`).
The printed Subtotal − Discount + Tax will not reconcile to Grand Total on
inclusive‑priced documents. Verify against `sales/pdf/*` and fix the subtotal basis (store
inclusive gross as subtotal, or recompute discount on the exclusive basis).

**R1-019 | MEDIUM | backend/core/services/billing.py:465-466, 319-320**
`if raw_total < 0: raw_total = 0`. A data‑entry error where `invoice_discount` exceeds
`taxable + tax` silently yields a ₹0 invoice, `round_off` computed as `0 - 0 = 0`, and
`discount_total` still showing the full (impossible) discount. No `BusinessRuleError` is
raised. Same in `apply_rcm_memo_after_tax`. Reject discounts that exceed the invoice
value.

**R1-020 | LOW | backend/core/services/billing.py:411-424**
`DISCOUNT_BEFORE_TAX` proportional allocation clamps each line's share to that line's
taxable (`share = min(share, adjusted[i])`) and then dumps the residual onto the last
line, which is also clamped to ≥ 0. With very uneven line values the clamped residual can
exceed the last line's taxable and the remaining discount is **silently dropped** — the
customer is charged more than `invoice_discount` implies. Spread the residual across lines
with remaining headroom instead of only the last line.

**R1-021 | LOW | backend/core/services/charges.py:11-16**
`additional_charges` are added to the grand total **untaxed** unless the user also fills
`charges_gst_rate` *and* `charges_hsn`. Freight/packing that forms part of a composite
supply is legally taxable at the principal rate. At minimum warn on Complete when charges
are non‑zero but untaxed on a GST invoice.

**R1-022 | LOW-MEDIUM | backend/core/services/charges.py:32-48**
`charge_line` returns a `SimpleNamespace` with no `cess_amount` attribute. Any GSTR /
e‑invoice line builder that accesses `line.cess_amount` directly (rather than
`getattr(..., 0)`) will `AttributeError` when a taxable freight line is present. Verify in
`sales/einvoice_payload.py` and `reporting/gst_returns*.py`.

**R1-023 | LOW | backend/core/validators.py:14**
`ALLOWED_GST_RATES` includes `"40"`. Confirm this is the intended GST‑2.0 sin‑goods slab
and not a stray value; if unintended it lets invoices be filed at a non‑existent rate.

**R1-024 | MEDIUM | backend/core/services/feature_flags.py:34-58**
Company `feature_flags` JSON can only **AND‑down** an env flag (`flags[key] = flags[key]
and bool(value)`) — it can never enable a module the env has off. If the company‑settings
UI presents these as on/off toggles, an owner enabling e.g. CRM/Payroll sees no effect
whenever the env flag is off. Either document that env is a hard ceiling and disable the
UI toggle accordingly, or allow company opt‑in for the modules that are meant to be
self‑serve.

**R1-025 | LOW | backend/core/services/document_numbers.py:156-161**
`_queryset_for` uses `__import__("accounting.models", fromlist=[...])` inline for two doc
types while every other model is a normal `from ... import`. Works, but it's an odd
inconsistency that hides a circular‑import workaround; add a comment or restructure.

---

## Wave 2 — Sales, Purchases, COGS, Ledgers, Inventory

### Sales (`sales/services.py`, `sales/cogs_service.py`)

**R2-001 | HIGH | backend/sales/services.py:555-852 (complete) & 315-329 (set_items)**
The CGST/SGST‑vs‑IGST split and every line's tax are computed in `set_items` via
`compute_document_totals(..., intra_state=party_intra_state(..., seller_state=
getattr(invoice.company_gstin,"state",...)))`. On a DRAFT, `invoice.company_gstin` is
usually **unset**, so `seller_state` falls back to `company.state`. `complete()` then
*stamps* `invoice.company_gstin` (lines 563‑577 / 767‑777) but **never re‑runs
`compute_document_totals`**. For a company with GSTINs in multiple states, an invoice
stamped under a GSTIN whose state ≠ `company.state` files the wrong tax head (IGST where
it should be CGST/SGST or vice versa), and the line totals persisted at draft time are
never corrected. Recompute totals at Complete once the filing GSTIN is known, or forbid
completing when the stamped GSTIN's state disagrees with the split already computed.
(Same defect on the purchase side — see R2‑010.)

**R2-002 | MEDIUM | backend/sales/services.py:244-325 (_update_items_in_place)**
Completed‑invoice amend (`adjust_stock` path) allows changing `gst_rate`, `unit_price`,
`discount_percent`, `quantity`, `cess_rate`, `supply_nature` in place and recomputes tax.
Only product change and add/remove‑line are blocked. Editing the taxable value or rate of
an **already‑issued** GST tax invoice in place (rather than via credit/debit note)
breaks the audit trail even with the `AMEND` statutory event, and if the period was
already filed the filed GSTR no longer matches the stored invoice. Restrict in‑place
amend to non‑monetary fields, or gate rate/price/discount changes behind the same
"use a credit/debit note" rule already applied to quantity on batch/serial SKUs.

**R2-003 | MEDIUM | backend/sales/services.py:1041-1080 (convert_quotation)**
`items_data` built from quotation lines carries only
`product, description, quantity, unit_price, discount_percent, gst_rate`. It drops
`supply_nature`, `cess_rate`, `cess_amount`, `unit_price_inclusive`, and the document
`price_mode`. Converting an inclusive‑priced quotation produces an exclusive‑priced
invoice with the wrong unit prices; converting a quotation with cess or an EXEMPT/NIL
nature silently loses that classification. `convert_quotation_to_order` (1082‑1127) has
the same gap.

**R2-004 | MEDIUM | backend/sales/services.py:854-1013 (cancel)**
Cancellation reverses the invoice's journal entries with
`PostingService.reverse(entry, user, invoice.invoice_date)` — i.e. the reversal is
**dated at the original invoice date**, which `cancel` explicitly allows to be in a
*soft‑closed* period (`allow_soft_closed=True`, line 860). Standard practice is to post
the reversal on the cancellation date. Back‑dating a reversal into a closed period
silently reopens that period's numbers.

**R2-005 | LOW-MEDIUM | backend/sales/services.py:863-866**
`cancel` blocks only when a **COMPLETED** sales return exists. A DRAFT / in‑progress
sales return against the invoice is neither blocked nor cleaned up, leaving it pointing
at a cancelled invoice.

**R2-006 | MEDIUM | backend/sales/services.py:672-719 (warnings on complete)**
Missing HSN, sub‑6‑digit HSN, e‑Way threshold, untaxed B2B charges, and WARN‑policy
negative stock are all returned as `warnings` while Complete still succeeds. If any
caller/UI ignores the `warnings` array, users file non‑compliant GSTR / move goods
without an e‑Way bill with no visible signal. Confirm the view returns `warnings` and the
SPA surfaces them prominently (and consider making "missing HSN on a B2B GST invoice" a
hard block).

**R2-007 | MEDIUM | backend/sales/cogs_service.py:77-85 & backend/inventory/services.py:1052-1060**
When `move.unit_cost` is 0 and `InventoryValuationService.unit_cost(...)` also returns 0
(new product, no purchase history, `unit_cost()` returning `rows[0]` which may be a
zero‑qty batch row), `cogs_total += 0`. The sale books **₹0 COGS** with no warning, the
COGS journal posts zero, and gross margin is overstated. Surface a warning
("N line(s) have no cost basis — COGS booked as 0") and/or fall back to
`product.purchase_price`.

**R2-008 | MEDIUM | backend/sales/cogs_service.py:191-195 (restore_return_stock_and_cogs)**
If the original SALE movements can't cover the returned quantity (challan‑sourced sale,
lots already fully consumed by earlier returns, movement `reference_id` type mismatch),
`complete_return` **hard‑raises** and the return cannot be completed at all — the user is
told to go post a manual ADJUSTMENT. A returns feature needs a WAVG‑cost fallback path
rather than a dead end.

**R2-009 | LOW | backend/sales/cogs_service.py:150-158**
`prior_sr_ids` is re‑queried on every iteration of the `for move in sale_moves` loop
(loop‑invariant). Hoist it out of the loop.

### Purchases (`purchases/services.py`, `purchases/notes_services.py`)

**R2-010 | HIGH | backend/purchases/services.py:518-706 (complete)**
Same as R2‑001: `complete()` stamps `company_gstin` (lines 622‑635) but never re‑runs
`compute_document_totals`, so the intra/inter tax split computed against `company.state`
at `set_items` time is not corrected against the filing GSTIN's state for multi‑GSTIN
companies.

**R2-011 | MEDIUM | backend/purchases/services.py:472-516 (_unregistered_rcm_gate)**
RCM is only *hard‑enforced* (`confirm_no_rcm` required) when
`taxpayer_type == UNREGISTERED` is explicitly set. The very common data state — supplier
saved with **blank `taxpayer_type` and blank GSTIN** — only produces a soft warning
(line 493‑497). Purchases from unregistered dealers therefore complete without RCM and
without a forced acknowledgement. Treat "blank GSTIN + not COMPOSITION/registered" as the
same hard gate.

**R2-012 | MEDIUM | backend/purchases/services.py:645-653**
`BatchLot.objects.get_or_create(..., defaults={"expiry_date": item.exp_date, ...})` — if a
batch with that `batch_no` already exists, a *different* incoming `exp_date` /
`mfg_date` on the new purchase is silently discarded (existing lot wins). For
pharma/FEFO this is a correctness bug; at minimum warn on expiry mismatch.

**R2-013 | MEDIUM | backend/purchases/services.py:664-683 & accounting posting**
Landed‑cost allocation adds `additional_charges * line_taxable / taxable_total` into the
per‑unit inventory cost. Verify that (a) the GST charged *on* those additional charges
(`charge_line` → `igst_total`/`cgst_total`) is still claimed as ITC in
`PostingService.post_purchase` and not also capitalised into stock, and (b) the charge
allocation basis (`invoice.taxable_total`, which is the exclusive sum even for INCLUSIVE
price mode) matches the basis used for the tax split.

**R2-014 | LOW-MEDIUM | backend/purchases/services.py:883-891 vs 605-611**
`complete_return` always passes `on_date=purchase_return.return_date` to `next_number`,
so purchase returns are always FY‑scoped, while `complete` (purchase invoice) passes
`on_date` only `if series_gstin`. When `resolve_series_gstin` returns `None`, the return
lands in the `""/FY` series and the invoice in the `""/""` series — inconsistent
numbering families within one company. (Root cause is R1‑013.)

**R2-015 | LOW | backend/purchases/services.py:1024-1077 (auto purchase CN)**
`complete_return` creates + sets items on + completes a `PurchaseCreditNote` inside the
return's own transaction, cascading journal + GSTR side effects. Proportional
`ratio`‑scaled `invoice_discount` / `additional_charges` on partial returns can leave a
few paise of AP residue across multiple partial returns (rounding each CN independently).

**R2-016 | LOW | backend/purchases/services.py:409-436 (restamp_fifo_layers_for_price_amend)**
The "any qty peeled?" guard compares a *single* layer's `qty_remaining` against the whole
move's `original_qty`; if `original_qty` is 0 (bad data) the guard is skipped and layers
are restamped unconditionally.

### Ledgers (`ledgers/services.py`)

**R2-017 | MEDIUM | backend/ledgers/services.py:205-249 & 414-477**
The GL‑first `customer_outstanding` uses account **1200 only**, but
`customer_statement`/`_gl_party_statement` foots **1200 + 2300** (AR + customer
advances). Whenever a customer has an unallocated advance, the statement's closing
balance will not equal the "Outstanding" figure shown in the header/list. Same on the
supplier side: `supplier_outstanding` = 2100 only, `supplier_statement` = 2100 + 1250.
Pick one basis for both.

**R2-018 | MEDIUM | backend/ledgers/services.py:206-211, 250-271, 319-322**
`customer_outstanding` / `bulk_customer_outstanding` floor each party at
`max(0, net)`. `company_receivables` sums those floored values, so any customer in
credit contributes 0 instead of a negative amount and **the dashboard AR total no longer
reconciles to the AR control‑account (1200) balance in the trial balance**. Same for AP /
2100. Provide an un‑floored company total for reconciliation, or net credits explicitly.

**R2-019 | MEDIUM | backend/ledgers/services.py:54-64, 441-458 (_resolve_source_number)**
`_gl_party_statement` calls `_resolve_source_number` once per journal line — one extra
`SELECT` per row. For a party with hundreds of transactions this is a large N+1 on a
report endpoint. Batch‑resolve numbers per `(source_type, source_id)` set.

**R2-020 | LOW | backend/ledgers/services.py:239-246**
Legacy `customer_outstanding`'s `allocated` filter uses `receipt__isnull=False` but does
not also require `supplier_payment__isnull=True`; a malformed `PaymentAllocation` with
both FKs set would be counted on both sides. Defensive only.

**R2-021 | LOW | backend/ledgers/services.py:196-201**
`customer_outstanding` (the figure shown in the customer ledger UI) never nets unallocated
advances — only `customer_exposure_for_credit_limit` does. A customer who has prepaid but
has open invoices shows the gross invoice figure as "outstanding". Confirm this is the
intended display and that a separate "advance on account" line is shown.

### Inventory (`inventory/services.py`)

**R2-022 | HIGH | backend/inventory/services.py:947-1060 (valuation / unit_cost)**
`InventoryValuationService.valuation` replays **every `StockMovement` for the product,
with no date lower bound**, in Python, and `unit_cost()` calls it with no `as_of`.
It runs on the hot path for every COGS calc, every sales/purchase/transfer completion,
and every cancel restore. Cost is O(all historical movements) per line item. This will
not scale — a single product with tens of thousands of movements makes every document
Complete slow. Introduce a materialised running cost (the perpetual `InventoryCostLayer`
table already exists for FIFO; do the equivalent for WAVG) or at least window the replay.

**R2-023 | HIGH | backend/inventory/services.py:958-965**
`valuation` windows by `created_at__date__lte=as_of` and orders FIFO by
`created_at, id` — i.e. by **row insertion time, not transaction/document date**. Any
back‑dated purchase or post‑dated document makes as‑of stock valuation and FIFO layer
ordering wrong (a March‑dated purchase entered in April is excluded from a 31‑Mar
valuation; FIFO consumes it after later‑entered stock). Window and order by the
movement's business date.

**R2-024 | MEDIUM | backend/inventory/services.py:1052-1060 (unit_cost)**
Returns `rows[0]["unit_cost"]` when there's no batch match. `rows` is
`state.values()` in dict order; `rows[0]` can be a zeroed‑out / qty‑0 batch row, so
`unit_cost(product)` returns 0 even when other rows hold real stock at real cost. Prefer
the qty‑weighted average across rows with `qty > 0`, or the row with the largest qty.

**R2-025 | MEDIUM | backend/inventory/services.py:417-427 (_apply_cost_layers FIFO shortfall)**
On a FIFO issue that outruns available layers under a non‑BLOCK policy, the shortfall is
costed at `product.purchase_price` (a master field that may be stale or 0). Result: COGS
misstatement (or ₹0 COGS) whenever stock goes negative. Also the branch tests for
`negative_stock_policy in ("ALLOW","WARN")` but the model only defines `BLOCK` / `WARN`
— `"ALLOW"` is dead.

**R2-026 | MEDIUM | backend/inventory/services.py:218-342 (post_opening_movements_batch)**
The one‑shot‑opening guard `select_for_update()`s existing `StockBalance` rows, but for a
product that has **no balance row yet** there is nothing to lock, so two concurrent
batch‑opening imports for the same new product can both pass the `already` check and both
`bulk_create` an `OPENING_STOCK` movement → doubled opening stock. Confirm a DB‑level
unique constraint on `(company, warehouse, product, batch, movement_type=OPENING_STOCK)`
exists; the code comment claims uniqueness but only an app check is visible.

**R2-027 | LOW | backend/inventory/services.py:641-702 (rebuild_balance)**
`rebuild_balance` recomputes `reserved` purely from CONFIRMED `SalesOrder` items. If it's
exposed as an admin "recalculate balances" action, running it silently discards any
reservation made via `reserve_stock` that isn't backed by a confirmed SO.

**R2-028 | LOW | backend/inventory/services.py:788-804 & 765-786**
`SerialNumberService.transition` / `receive` issue one `SELECT ... FOR UPDATE` (and one
`save`) per serial number. Bulk serial documents (hundreds of units) generate hundreds of
round‑trips inside the document transaction.

---

## Wave 3 — Payments, Gateway/Webhooks, Accounting (GL posting)

### Payments (`payments/services.py`, `payments/webhook_views.py`)

**R3-001 | HIGH | backend/payments/services.py:800-812 & 192-196**
`finalize_gateway_payment` (called from the verified webhook) runs
`PaymentService.create_receipt`, which calls
`assert_period_allows_money_amend(company, today)`. If today's period is CLOSED/soft‑closed,
`create_receipt` raises, the whole `@transaction.atomic` webhook finalize rolls back
**including the `GatewayPayment` row**, and a 5xx is returned so the provider retries
forever — meanwhile the money has been captured at the gateway and BizBoard has no record.
Webhook settlement must not be blockable by period locks; capture unconditionally into a
holding state (or bypass the gate for `source=GATEWAY`).

**R3-002 | MEDIUM-HIGH | backend/payments/services.py:800-806**
`finalize_gateway_payment` → `create_receipt(warn_utr_duplicate=False)` → `_assert_utr_unique`
with `utr = provider_payment_id`. If staff already manually recorded that payment (UTR ==
provider id), `create_receipt` raises `BusinessRuleError` **outside** the try/except that
only wraps allocation (lines 819‑833). The webhook 500s and retries forever, and the
manual + gateway receipts are never reconciled. Gateway finalize should detect and link a
pre‑existing matching receipt instead of hard‑failing on UTR uniqueness.

**R3-003 | MEDIUM-HIGH | backend/payments/webhook_views.py:161-177 & backend/payments/services.py:871-877**
A provider‑initiated **partial** refund arrives as a `REFUNDED` webhook →
`refund_gateway_payment(...)` → `if refund_amount != gp.amount: raise BusinessRuleError`
→ 400 returned → provider retries the partial‑refund webhook indefinitely and the partial
refund is **never recorded** in BizBoard (books diverge from the bank/gateway). Partial
gateway refunds need a real (even if manual‑assisted) handling path.

**R3-004 | MEDIUM | backend/payments/services.py:856-950 (refund_gateway_payment)**
The refund is recognised in the GL and the receipt marked `REFUNDED` **before** the actual
gateway refund executes (queued via `GatewayRefundOutbox` + `on_commit` Celery task). If
`execute_gateway_refund` exhausts retries (gateway rejects), the books show a refund that
never reached the customer's bank, with no compensating reversal or hard alert. Add a
"stuck refund outbox" health alert and a documented manual‑reversal procedure.

**R3-005 | MEDIUM | backend/payments/webhook_views.py:104-124**
`parse_webhook_probe(provider, body)` parses attacker‑controlled JSON and does a
`PaymentLink` + `company` lookup **before** signature verification (needed to pick the
verifying key, a defensible pattern). Confirm `parse_webhook_probe` cannot raise on
malformed input, and that the distinct 400 ("payment_link_id required") vs 401 ("invalid
signature") responses aren't a useful oracle for enumerating valid `provider_link_id`s
(they are guessable if short).

**R3-006 | MEDIUM | backend/payments/services.py:136-155 & payment_health:997-1013**
`_check_utr_duplicate` and the `DUPLICATE_UTR` health check both **exclude VOIDED/REFUNDED**
receipts, so a UTR freed by a void can be silently reused and will never be flagged.
Confirm the DB constraint on `(company, utr)` is a *partial* unique index that matches this
exclusion; a full unique index would `IntegrityError` on legitimate re‑use after void.

**R3-007 | LOW | backend/payments/services.py:978-1036 (payment_health)**
The health endpoint loops `LedgerService.sales_invoice_outstanding(inv)` over up to 50
completed invoices (several aggregate queries each) plus per‑line bank aging. This is an
expensive "health strip" call; cache it or precompute.

**R3-008 | LOW | backend/payments/services.py:730-734**
On a repeat (non‑captured) webhook for an existing `GatewayPayment`, `existing.amount` /
`fee` / `raw_payload` are overwritten from the new (verified but still client‑shaped)
payload. Reconcile against the provider's authoritative amount rather than last‑write‑wins.

### Accounting / GL posting (`accounting/services.py`)

**R3-009 | HIGH | backend/accounting/services.py:211-258 (PostingService.post)**
Idempotency relies on an **unlocked** `JournalEntry.objects.filter(...).first()` existence
check. Two concurrent `post()` calls for the same `(company, source_type, source_id,
purpose)` (retry + original, double‑click, webhook + manual) can both see "no existing"
and both create a full journal → **doubled revenue / tax / AR / AP**. The invoice
`select_for_update` in sales/purchase `complete` mitigates those two paths, but
`post_receipt_allocation`, `post_note`, `post_*` from Celery, and manual posting may not
all hold a serialising lock. Add a DB `UniqueConstraint(company, source_type, source_id,
purpose)` filtered to non‑reversed/posted, or `select_for_update` a guard row.

**R3-010 | HIGH | backend/accounting/services.py:590-744 (post_purchase) + core/services/billing.py**
There is **no block on an `AFTER_TAX` invoice‑level discount for purchases** (the sales
side blocks it at `sales/services.py:654-664`). With `invoice_discount_mode == AFTER_TAX`,
`compute_document_totals` leaves line taxables unreduced, so `grand_total = Σtaxable + tax
+ charges − inv_discount` while `post_purchase` builds debits from `Σtaxable + tax +
charges` and credits `2100 = grand_total`. Debits − credits = `inv_discount` ≠ 0 →
`post()` raises "must contain balanced debit and credit lines" → **the purchase cannot be
completed** for an accounting‑enabled company (or, books off, produces a document whose
value legs don't reconcile). Either mirror the sales AFTER_TAX block, or post the discount
as an explicit leg (e.g. purchase discount income / 5110 contra).

**R3-011 | MEDIUM | backend/accounting/services.py:128-134 (_account) & 109-126 (_ensure_chart)**
If a system account `code` exists but is **inactive**, `_ensure_chart` re‑seeds via
`get_or_create` (which returns the existing *inactive* row, not reactivating it), then
`_account` filters `is_active=True`, hits `DoesNotExist`, re‑seeds again, and the second
`.get(is_active=True)` raises an **unhandled exception** → 500 on every document Complete.
Deactivating/renaming any seeded account bricks posting. Reactivate on ensure, or fail
with a clear BusinessRuleError.

**R3-012 | MEDIUM | backend/accounting/services.py:618-744 (post_purchase charge inference)**
When `additional_charges` isn't on the header, charges are **inferred** as
`grand_total − tax − line_taxable − round_off` and booked to `5110 Purchase Charges`. Any
rounding drift in `line_taxable` (some lines falling back from `taxable_amount` to
`line_total` at line 601) is misclassified as expense, and if the residual makes the entry
unbalanced `post()` raises and Complete fails. Don't infer a P&L amount from a totals
gap.

**R3-013 | MEDIUM | backend/accounting/services.py:1105-1130 (control_balances)**
`AR_CONTROL_MISMATCH` / `AP_CONTROL_MISMATCH` compare `net("1200")` vs
`tagged_net("1200","customer")` with an **exact `!=`** (no tolerance band, unlike
`_advance_recon_alerts` which uses `> 1.00`). A single paise of rounding anywhere in 1200
or 2100 — or one untagged manual‑journal line — hard‑**blocks period close**
(`period_close_blockers`). Add a small tolerance and/or report the untagged lines.

**R3-014 | MEDIUM | backend/accounting/services.py:179-209, 690-708 (UNREVIEWED ITC → 1390)**
`UNREVIEWED` purchase tax is parked in `1390 ITC Unreviewed (suspense)`. Confirm that
marking a bill `CLAIMABLE` later posts a reclass `1390 → 1310/1320/1330` (and `REVERSED`
posts `1390 → 1400/expense`). If there's no reclass, ITC never reaches the Input GST
accounts and GSTR‑3B ITC vs books permanently diverges.

**R3-015 | MEDIUM | backend/accounting/services.py:273-282 (post_sales_invoice drift gate)**
Header‑vs‑line tax drift up to `0.05` is allowed to post silently. Small but it means the
GL can legitimately disagree with the filed GSTR by up to 5 paise per invoice with no
record of the discrepancy. Post the drift to `5500 Round Off` explicitly instead of
absorbing it.

**R3-016 | LOW | backend/accounting/services.py:1024**
`reverse()`'s secondary guard `hasattr(entry, "reversal_of")` never fires as intended —
either it's a reverse relation (always truthy, would break all reversals — so it must not
be) or it's simply not an attribute (always falsy → dead code). The real guard is
`entry.status != POSTED`; delete the misleading `hasattr` check or replace with
`entry.reversed_entry_id is not None`.

**R3-017 | LOW | backend/accounting/services.py:427-453 (post_opening_stock)**
`entry_date` is derived from `movement.created_at` (row insert time), not the opening
"as of" date, so opening‑stock journals are mis‑dated when opening balances are entered
later than their effective date.

---

## Wave 4 — GST returns, Payroll, Imports

### GST returns (`reporting/gst_returns.py`)

**R4-001 | MEDIUM | backend/reporting/gst_returns.py:181-221 (_rate_buckets RCM restore)**
When restoring memoised RCM tax for GSTR sections, cess is recomputed as
`taxable * cess_rate / 100` only — **specific per‑unit `cess_amount` is ignored**. RCM
invoices carrying specific cess get understated cess in GSTR‑1/3B. (Ties to R1‑016 — the
cess_amount semantics disagree across builders.)

**R4-002 | MEDIUM | backend/reporting/gst_returns.py:89-107 (_party_pos)**
When POS can't be resolved and `assume_local_state_for_blank_party` is off, `_party_pos`
returns the literal string `"NA"`, which then becomes a `b2cs_buckets` key and appears in
B2CL/B2CS rows. `"NA"` is not a valid GSTN state code — the generated GSTR‑1 JSON is
portal‑rejected, or the row is silently mis‑bucketed. Imported/legacy invoices that never
passed the Complete‑time POS gate can reach here. Surface `"NA"` POS as a hard filing
blocker instead of embedding it in section buckets.

**R4-003 | MEDIUM | backend/reporting/gst_returns.py:140-178 (invoice_value_mismatch)**
Invoices failing this identity check are dropped from GSTR sections (per BB‑000621).
Confirm every such drop raises a visible, blocking issue in `build_gstr1` (not just a
soft note) — otherwise outward tax liability is silently understated. Also note the check
does not account for the INCLUSIVE‑price subtotal/discount mismatch in R1‑018.

**R4-004 | MEDIUM | backend/reporting/gst_returns.py:1188-1217 (GSTR‑3B ITC block)**
`available_from_purchases` (books CLAIMABLE flags) is always shown alongside
`from_gstr2b_matched`. When books over‑mark CLAIMABLE relative to 2B, the higher books
figure is presented with no enforced "claim the lower of the two". The safe default
(claimable = 2B‑matched) is left entirely to the UI.

**R4-005 | LOW | backend/reporting/gst_returns.py:1118-1129**
`rcm_cess -= getattr(note,"rcm_cess",0) or getattr(note,"cess_total",0) or 0` — a
legitimately‑zero `rcm_cess` with a stale non‑zero `cess_total` would wrongly subtract
`cess_total`. Fragile `or`‑chain fallback across memo/non‑memo fields.

**R4-006 | LOW | backend/reporting/gst_returns.py:127-128 (_is_b2b)**
`_is_b2b` is `bool(party_gstin.strip())` — a stale/cancelled/invalid GSTIN string on a
customer routes the supply to the B2B table (Table 4) rather than B2CS, and no
UIN/SEZ/composition distinction is made at this point.

### Payroll (`payroll/services.py`)

**R4-007 | MEDIUM | backend/payroll/services.py:76-80 (compute_statutory PF base)**
PF is computed on `min(gross, ceiling)` where `gross` is `employee.salary` (or an
override). PF is legally on **Basic + DA**, not gross. Using gross over‑withholds PF for
employees whose basic < gross and mis‑states the PF payable / employer contribution.

**R4-008 | MEDIUM-HIGH | backend/payroll/services.py:110-174 (complete_pay_run)**
Every ACTIVE employee is paid their **full `employee.salary`** each run — there is no
LOP / attendance / days‑present proration, no mid‑month joiner/leaver handling. For a
payroll module this is a core functional gap, not an edge case.

**R4-009 | MEDIUM | backend/payroll/services.py:118-120**
`locked.slips.exclude(employee_id__in=active_ids).delete()` — if a completed run is
cancelled (→ DRAFT), an employee is then terminated, and the run re‑completed, that
employee's slip (and their earned wages for the period) is silently deleted.

**R4-010 | MEDIUM | backend/payroll/services.py:57-64 (_pt_amount) & DEFAULT_PT_SLABS**
Professional Tax is a single‑slab stub. Multi‑slab states (Maharashtra, WB, …) and
Maharashtra's February higher deduction are not modelled; a misconfigured
`payroll_pt_slabs` (gaps between slabs) silently yields PT = 0.

**R4-011 | LOW | backend/payroll/services.py:141-144**
`seed_chart_of_accounts(company, user)` is called unconditionally on every pay‑run
completion (~50 `get_or_create` round‑trips) even when the chart already exists.

**R4-012 | LOW | backend/payroll/services.py:177-207 (cancel_pay_run)**
Cancel returns the run to `DRAFT` (indistinguishable from "never run") rather than a
`CANCELLED` state; `PaySlip` rows are retained and re‑completion re‑posts. No
cancellation audit on the run itself beyond the reversal JE.

### Imports (`imports/services.py`, `imports/qty_formula.py`)

**R4-013 | MEDIUM-HIGH | backend/imports/services.py:1875-1898 (void → _cleanup_imported_product)**
`void` matches products to clean up by `sku__iexact` / `name__iexact`
(`_find_imported_product`) and then **deletes** them (or blanks sku/barcode + sets
INACTIVE). `_commit_products` has an *update* path for pre‑existing products, but the void
has no record of which rows were creates vs updates — voiding a products import that
merely **updated** existing masters can delete/deactivate pre‑existing product records.

**R4-014 | MEDIUM | backend/imports/services.py:1719-1757 & 1788-1820 (serial‑tracked opening void)**
`_commit_opening_stock` receives serial‑tracked opening stock via
`InventoryService.post_opening` (which creates `SerialNumber` rows). `void` /
`_reverse_import_movement` posts a negative ADJUSTMENT but never transitions/removes those
`SerialNumber` rows, leaving orphan AVAILABLE serials with no backing stock and blocking
re‑import of the same serials.

**R4-015 | MEDIUM | backend/imports/services.py:1261-1299 (commit)**
Only `Kind.PRODUCTS` is blocked from commit when `job.error_rows` is non‑empty (line
1273). CUSTOMERS / SUPPLIERS / OPENING_STOCK imports can be committed with known error
rows. Also `_commit_customers` / `_commit_suppliers` `bulk_create` bypass model
`full_clean()`, so a bad GSTIN/state/email that slipped past `_validate_row` is written
raw, and there is a preview→commit TOCTOU duplicate window (no re‑dedupe under the job
lock).

**R4-016 | MEDIUM | backend/imports/qty_formula.py:425-482 (apply_qty_formula)**
When the qty implied by `printed_gross_amount ÷ rate` disagrees with the
LLM/structured/formula quantity, the implied value **silently overrides** `line.quantity`
(only a soft `flag` is added). If the printed rate was OCR'd wrong, committed
stock/purchase quantity is now wrong with no error. Auto‑correction from the printed
amount should require confirmation.

**R4-017 | LOW | backend/imports/qty_formula.py:301-317 (resolve_formula_expr / formula_enum)**
A custom `qty_formula` answer string is passed straight to `eval_formula` (safe — no
`eval()`, tokens must exist in the pool) but `formula_enum` only recognises two exact
strings, so any other custom expression is persisted on the vendor template as
`FORMULA_SIMPLE` and won't round‑trip when the template is re‑applied.

**R4-018 | LOW | backend/imports/services.py:1788-1820 (_reverse_import_movement)**
Import‑void journal reversal posts with no `entry_date` → dated *today*, while the
original opening‑stock journal was dated at `movement.created_at`. Asymmetric dating.

---

## Wave 5 — Frontend & infra

### Frontend (`web/src`)

Overall the SPA is well maintained: capability‑gated lazy routes, httpOnly‑cookie auth
(no tokens in `localStorage`), no `dangerouslySetInnerHTML`, near‑zero `TODO`/
`@ts-ignore`, a careful port of the backend tax math. Findings are mostly parity /
dead‑end‑flow issues.

**R5-001 | MEDIUM | web/src/utils/tax.ts:206-322 vs backend/core/services/billing.py**
`calculateInvoiceTotals` computes an `AFTER_TAX` invoice‑level discount for any invoice,
but `SalesService.complete` (backend `sales/services.py:654-664`) **hard‑blocks**
`AFTER_TAX` discount on B2B GST invoices. The user builds the invoice, sees a correct
total, then Complete fails server‑side. Disable / warn on `AFTER_TAX` discount in the
invoice form when the customer has a GSTIN.

**R5-002 | MEDIUM | web/src/utils/tax.ts:238 & 179-204 (INCLUSIVE subtotal)**
Mirrors R1‑018: for INCLUSIVE price mode, `subtotal = Σ(gross ?? taxableAmount)`. Unless
the caller feeds the *inclusive* gross, the on‑screen Subtotal − Discount + Tax won't
foot to Grand Total for inclusive‑priced invoices, and it won't match the PDF.

**R5-003 | LOW-MEDIUM | web/src/api/client.ts:137-165 (doRefresh)**
Any failure in `doRefresh` — including a transient network error / timeout — calls
`clearTokens()` and dispatches `session-expired`, logging the user out. For a
field‑sales PWA on flaky connectivity a single 2‑second outage during a refresh ends the
session. Distinguish network errors (retry) from 401/invalid‑refresh (log out).

**R5-004 | LOW-MEDIUM | web/src/api/client.ts:19-24, 83-96**
`X-Company-Id` is read from `localStorage` and attached to every request. If a second tab
switches company, this header will disagree with the backend's `user.active_company`
until an explicit switch call, and the backend answers **409 `company_context_conflict`**
on every request (see R1‑008). Confirm a global 409 handler re‑syncs / shows a company
picker rather than surfacing raw errors.

**R5-005 | LOW | web/src/utils/money.ts:8-25 (roundMoney)**
Paise parity with the backend relies on `Number.toFixed(10)` of a binary float, then
half‑up on the 3rd decimal. Python uses exact `Decimal`. Expect occasional 1‑paise
differences between the FE preview and the posted document on adversarial inputs; make
sure the UI always shows the server totals as authoritative after save.

**R5-006 | LOW | web/src/utils/gst.ts:58 & 68**
`ALLOWED_GST_RATES` / labels include `40` (matches backend R1‑023). If the 40% slab is
not intended, it's wrong in both tiers.

### Infra (`backend/Dockerfile`, `.github/workflows/cd.yml`, compose)

**R5-007 | MEDIUM | backend/Dockerfile:24-34**
The final `USER` directive is `root`; `CMD` launches gunicorn directly. The comment says
the entrypoint drops privileges after chown‑ing the media volume — **verify
`docker-entrypoint.sh` actually `exec`s as the `app` user** (e.g. `gosu`/`su-exec`). If
it doesn't, gunicorn serves as root in production.

**R5-008 | LOW-MEDIUM | backend/Dockerfile:34**
`--workers 2` is hard‑coded (not env‑driven). Combined with `--timeout 120` and several
known‑expensive endpoints (valuation replay R2‑022, `payment_health` R3‑007, GST
reports), two sync workers will head‑of‑line block under light concurrency. Make workers
configurable and size per instance.

**R5-009 | LOW-MEDIUM | .github/workflows/cd.yml:10-15, 22-33, 47-49**
`workflow_dispatch` runs `gate` but the "Require CI success" step is `if: workflow_run`,
so a **manual dispatch pushes images without a green CI run**. Maintainer‑only, but it's
a release‑integrity gap — require an explicit "I confirm CI passed for this SHA" input or
re‑run CI checks in the gate for the dispatch path.

**R5-010 | LOW | backend/Dockerfile:1**
`python:3.12-slim` is not digest‑pinned; `constraints.txt` pins Python deps but not the
base image, so image builds are not fully reproducible.

---

## Summary & suggested priority

**Counts:** ~95 findings — Wave 1 (core/tax) 25, Wave 2 (sales/purch/ledger/inv) 28,
Wave 3 (payments/GL) 17, Wave 4 (GST/payroll/imports) 18, Wave 5 (FE/infra) 10.

### Fix first (correctness / money / data‑loss)
| ID | One‑liner |
|----|-----------|
| R3-009 | GL `post()` idempotency is an unlocked existence check → concurrent double‑posting of journals. Add a DB unique constraint. |
| R3-010 | Purchase invoice with `AFTER_TAX` invoice discount can't post (unbalanced JE) — no guard, unlike sales. |
| R2-001 / R2-010 | Multi‑GSTIN: CGST/SGST‑vs‑IGST split computed vs `company.state` at draft, never recomputed against the stamped filing GSTIN at Complete. |
| R1-013 | Document numbering FY‑scoping depends on whether a `gstin=` arg is passed → two parallel sequences / non‑contiguous invoice numbers within a FY. |
| R3-001 / R3-002 / R3-003 | Gateway webhook settlement blockable by period locks / UTR uniqueness / partial refunds → money captured with no BizBoard record; provider retries forever. |
| R2-022 / R2-023 | `InventoryValuationService.valuation` = unbounded Python replay of all movements on the hot path, windowed/ordered by row‑insert time not business date. |
| R4-013 | Import `void` can delete/deactivate pre‑existing master products that a products import merely *updated*. |
| R1-016 / R4-001 | `cess_amount` (specific cess) semantics disagree between the model doc, the tax engine (additive), and the GSTR RCM restore (ignored). |
| R2-007 | Sales of a product with no cost basis silently book ₹0 COGS, no warning. |
| R3-011 | Deactivating/renaming any seeded GL account → unhandled 500 on every document Complete. |

### Fix next (compliance / reconciliation / silent wrong output)
R1-019 (discount > invoice value → silent ₹0), R2-002 (in‑place amend of issued invoice
rate/price), R2-011 (RCM not enforced for blank‑taxpayer‑type unregistered suppliers),
R2-017/R2-018 (ledger statement ≠ outstanding header; AR total ≠ GL control),
R3-013 (period‑close blocked by zero‑tolerance control‑balance compare),
R3-014 (UNREVIEWED ITC in 1390 suspense — verify reclass on CLAIMABLE),
R4-002 (`"NA"` POS embedded in GSTR buckets), R4-008 (payroll: no LOP/proration),
R4-007 (PF on gross not Basic+DA), R2-025 (FIFO negative‑stock COGS at stale
`purchase_price`), R4-016 (import qty silently overridden from printed amount).

### Verify (needs a check at the call‑site / DB before rating)
R1-003 (metrics endpoint auth), R1-006 (structured access‑log user/company always blank),
R1-007/R1-009 (RLS GUC leakage & `get_company_user` caching `None`),
R2-026 (opening‑stock DB unique constraint), R3-005 (webhook pre‑verify probe),
R5-007 (container drops to non‑root), cess `getattr(...cess_amount)` on the synthetic
`charge_line` namespace (R1-022).

### Lower priority
The remaining LOW items are performance (N+1s in ledger statements / payment health /
serial loops), dead code, asymmetric reversal dating, and style. See each wave.

### Not defects (noted for context)
The codebase is unusually hardened — hundreds of prior `BB-xxxxx` fixes, strong settings
validation, httpOnly‑cookie auth, careful FE/BE tax‑math parity, honest
"provisional / manual_review" labelling in GST returns. Most findings above are
edge‑cases, multi‑tenant/multi‑GSTIN gaps, concurrency windows, and
compliance‑simplification stubs (payroll PT/PF, TDS, import‑of‑goods) that are already
acknowledged as out of scope in `SPECTACULAR_SETTINGS["DESCRIPTION"]`.
