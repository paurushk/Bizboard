# BizBoard — Competitive Roadmap: Phased Implementation Plan

**e2e coverage added, 2026-09-23 (same day, third pass):** five
`e2e-golden/*.spec.ts` specs now exist, one per ticket
(`comp002-replenishment`, `comp003-customer-portal`, `comp005-route-profit`,
`comp006-gst-guard`, `comp007-supplier-price-history`), each a real
end-to-end run against the live backend (not mocked), following the
existing golden-suite conventions (`helpers/documents.ts`). Building them
surfaced and fixed two real gaps beyond the specs themselves:

- `playwright.golden.config.ts` never enabled the five `ENABLE_*` flags
  this work ships behind — added, plus `PORTAL_DEBUG_ECHO` (new, see below)
  and `PYTHONUNBUFFERED` (diagnostic value, harmless).
- COMP-003's e2e spec needs a way to read the customer-portal magic-link
  token without an inbox. Added `PORTAL_DEBUG_ECHO`
  (`backend/config/settings.py`), an explicit, production-hard-rejected
  opt-in echo of the token on the request-link response — same posture as
  the pre-existing `OTP_DEBUG_ECHO`, not implied by `DEBUG`. Covered by 3
  new backend tests (`test_customer_portal.py`) and a small frontend helper
  (`portalDebugHint.ts` + test) mirroring `loginOtp.ts`'s existing pattern.

**e2e coverage: all five specs green, 2026-09-23 (fourth pass).** The
apparent registration blocker noted in the third pass was **not a product
bug** — it was this session's own tooling mistake: an earlier `manage.py
migrate` run was killed mid-flight after its output looked stuck (Python
stdout is fully block-buffered when piped, so a genuinely-still-running
process can look hung for many minutes), leaving the `insights` app's
migrations unapplied. `insights.telemetry.record_event()`'s best-effort
`except Exception: logger.debug(...)` silently swallowed the resulting
`no such table: insights_shopfloorevent`, but that DB error had already set
Django's `connection.needs_rollback` flag, so the *entire* outer
registration transaction rolled back on clean exit — no exception ever
surfaced. Re-running `manage.py migrate --noinput` to completion (without
interrupting it) fully resolved it; `registerTenant()` and the rest of the
golden suite work correctly. `playwright.golden.config.ts` was also missing
`OTP_DEBUG_ECHO`, a separate, real, pre-existing gap (present since
`38a03ee`, unrelated to my new work) that broke `registerTenant()` for
*every* golden spec, not just these five — fixed alongside the migration
fix.

With that cleared, iterating each of the five new specs against the real
backend surfaced a further batch of genuine bugs — all in test/helper code
except where noted, confirmed via server logs, direct DB queries, and live
browser reproduction rather than assumption:

- `row.locator('input').nth(N)` assumed the line row's "Description"
  `<textarea>` counted as an `<input>` (it doesn't) — shifted every
  positional index by one, silently filling Unit Price where Quantity was
  intended. Fixed via `getByLabel('QTY')` / a corrected index in
  `helpers/documents.ts`'s `completePurchaseInvoice`.
- comp003 and comp006 never gave their product any stock before completing
  an invoice; `/complete/` hard-blocks on insufficient stock (BLOCK policy)
  for **every** product, not only batch-tracked ones — confirmed via a live
  400. Both now seed stock first.
- The Attention feed (`backend/insights/attention.py`) caches its raw
  per-company computation for 60s with no write-invalidation (B9-012, an
  intentional perf tradeoff) — the dashboard's own post-login fetch seeds
  that cache empty before a test creates any data, so a single post-mutation
  check inside the window deterministically sees stale data. comp002 and
  comp006 now poll with reloads past the TTL instead of fetching once.
- A transient SQLite `database is locked` error (`CFG-06` in
  `backend/config/settings.py` — a known dev-only concurrency limitation;
  confirmed live to be the app's own async telemetry beacon racing the
  invoice-number row lock inside `/complete/`) can make that call fail in a
  way the frontend swallows into a warning banner instead of blocking
  navigation, silently leaving a "completed" invoice as DRAFT. Added
  `saveAndCompleteSalesInvoice()` to `helpers/documents.ts`, which verifies
  the invoice actually reached COMPLETED and retries once via the UI if not
  — used by comp002, comp003, and comp005's shared
  `convertDraftOrderToCompletedInvoiceViaChallan()`. (Production runs
  Postgres exclusively; this class of flake cannot occur there.)
- Every 2xx API response is wrapped as `{success, data}` by
  `core/renderers.py`'s `EnvelopeJSONRenderer` (global). The app's own API
  client unwraps this transparently, but comp006's raw `page.request` calls
  didn't know that, and separately assumed wrong URL paths
  (`/api/v1/masters/customers/`, `/api/v1/inventory/products/` instead of
  the real `/api/v1/customers/`, `/api/v1/products/`).
- MUI's `Button` with `component={RouterLink}` renders as an `<a>`, whose
  implicit ARIA role is `link`, not `button` — the completion-retry helper's
  `getByRole('button', { name: 'Edit' })` could never match
  `InvoiceDetailPage`'s Edit action; fixed to `getByRole('link', ...)`.
- Assorted strict-mode locator fixes (an "Add Party" quick-add button
  sharing the exact accessible name "Add" with the real add-line button; a
  low-stock message rendering twice in the DOM; a Product combobox whose
  open option-listbox is *also* labelled "Product").

All five specs (`comp002-replenishment`, `comp003-customer-portal`,
`comp005-route-profit`, `comp006-gst-guard`,
`comp007-supplier-price-history`) pass cleanly, run together, no retries.

**Status:** implemented 2026-09-23 on `feature/sales-purchase-ux`, every
`ENABLE_*` flag default off. Engineering DoD below is checked. The only
item still open is CA sign-off before `ENABLE_GST_GUARD` is turned on for
a pilot (code is merged-ready flag-off; the flag stays off). Expands the six new
tickets in
[`COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md`](COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md)
(§2, `COMP-002/003/005/006/007/009`) into phase-by-phase, file-level build
plans. Source evidence: `docs/COMPETITIVE_ANALYSIS_BIZBOARD.md`. Source
decisions: `ROUGH_COMPETITIVE_ROADMAP_2026-09-22.md` + the resolutions in
`COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md` §0.

**Naming note:** these phases are labelled `CR-Phase 0…4` to avoid colliding
with this repo's existing `Phase 1–7` numbering (`docs/phase1/`…
`docs/phase7/`, document completeness → ecosystem/scale), which means
something different. Do not renumber this into that sequence.

**Doctrine, unchanged from the rest of `docs/roadmap/`:** every new surface
ships behind an `ENABLE_*` flag registered in
`backend/core/services/feature_flags.py`, default off. Code + tests decide
what exists. No pilot/commercial claim until `docs/pilot/GO_NO_GO.md` is
signed. Migration numbers below are the next free number per app **as of
2026-09-23** on the current branch (`feature/sales-purchase-ux`) — reconfirm
before opening a PR, since this branch is active.

**Grounding:** every model/function/file reference below was read from the
actual code on 2026-09-23, not assumed from the competitive analysis alone.
Where a design choice reuses an existing subsystem (e.g., the alerts
engine, the GSTIN-verification provider) rather than inventing a new one,
that reuse is called out explicitly — it's most of why several effort
estimates in the ticket doc are now tighter than first scoped.

**Revision note (2026-09-23, same day):** a pre-implementation review
caught three real defects in the first version of this plan — Attention
reads `build_business_alerts()` live, not the stored `BusinessAlertEvent`
inbox this plan originally targeted for COMP-002/006; COMP-002's formula
zeroed out on unconfigured `WarehouseReorderLevel` rows, silently
regressing today's low-stock alert; and COMP-006 duplicated three checks
`reporting/gst_health.py`/`gst_rate_scan.py` already do, plus proposed one
(duplicate invoice number) the database already makes unreachable. The
same pass fixed COMP-005 (taxable total, freeze at Complete, no Today row,
COGS via `invoice_sale_moves` with `abs(quantity)`). Buyer-GSTIN alerts are
`critical` so the existing `GST_GUARDRAIL` mapper names the invoice. No
implementation had started when these were caught. The ticket index in
`COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md` §2 matches this revision.

**Built (2026-09-23):** all six tickets are in the tree behind their own
flags, default off. COMP-003 ships as a 15-minute reusable magic link
(`ENABLE_CUSTOMER_PORTAL`). COMP-007 has its own flag
(`ENABLE_SUPPLIER_PRICE_HISTORY`), not `ENABLE_ACCOUNTING`. COMP-009 is
the India tax-engine seam. Sales and purchase document totals call
`get_tax_engine(company).compute_document_totals`. `billing.py` remains
the shim for the other helpers. CA sign-off for turning `ENABLE_GST_GUARD`
on is still unsigned.

**Post-implementation deep review (2026-09-23, same day):** six parallel
review-only passes (one per ticket) plus a manual read of the shared
infrastructure (feature flags, RLS migrations) found no critical issues,
two High findings, and a working set of Medium/Low findings and test gaps.
All were fixed and their regression tests added and run green
(backend: `pytest`, frontend: `vitest`) before this note was written — see
`docs/COMPETITIVE_ANALYSIS_BIZBOARD.md`-style traceability tags (`F1-00x`)
left as code comments at each fix site. Summary by ticket:

- **COMP-002** (2 High): `low_stock_alert_payload`'s company-wide aggregate
  row (no per-warehouse override configured — the common day-one case) was
  passed into `suggest_replenishment` as if its arbitrary representative
  warehouse were a real "current warehouse," so a genuinely-surplus
  warehouse could be wrongly excluded from transfer candidacy and the CTA
  could point at a meaningless destination. Fixed by tagging aggregate rows
  (`is_warehouse_specific=False`) and skipping the transfer computation for
  them entirely (F1-002). Also fixed an N+1 query pattern by precomputing
  the per-company `WarehouseReorderLevel`/`StockBalance` maps once instead
  of per low-stock row (F1-003) — this fix itself had a wrong import
  (`.models` instead of `inventory.models`) caught by actually running the
  test suite, not just by review. Added the missing end-to-end regression
  test proving the zero-config case reproduces today's exact alert, a unit
  test pinning the transfer-source selection to each candidate's *own*
  reorder level, and a query-count ceiling test.
- **COMP-006** (0 Critical/High): reviewed clean — the
  UNVERIFIED-vs-INVALID/CANCELLED/SUSPENDED logic, the per-run GSTIN cache,
  and the flag scoping were all already correct. Added six test-gap fills
  (unrecognized-status handling, flag-off on the live-lookup branch
  specifically, cache-hit-count proof, and the Today/`insights.alerts` path
  alongside the already-tested Attention path).
- **COMP-005** (2 Medium): a CANCELLED invoice still linked via
  `SalesOrder.converted_invoice` (the invoice-cancel flow's own unlink
  exclusion leaves CONVERTED orders linked), and a fully-RETURNED invoice
  (whose `taxable_total` is never reduced by the return flow), were both
  still counted as realized revenue/COGS at route-completion time — same
  for a delivery stop marked FAILED/RETURNED whose invoice was still
  COMPLETED. Fixed by excluding both cases from the sum (F1-004), folded
  into the existing "not yet invoiced" count rather than adding new
  persisted fields. Also fixed a rounding-mode inconsistency (`ROUND_HALF_UP`
  now, matching every other money `quantize()` in this codebase, not the
  Decimal context default). The COGS sign handling itself (`abs(quantity)`
  against a negative-signed SALE movement) was verified correct, not buggy.
- **COMP-003** (several Medium, 0 cross-tenant leaks): the core security
  question — can a valid token ever return another customer's or another
  company's data — passed on every code path, proven by tests, and does not
  depend on Postgres RLS being on. Fixed: the frontend never validated a
  backend-sourced pay path before `window.location.assign` (now routed
  through `safeAppPath`, matching `PublicPayPage.tsx`'s own discipline,
  F1-008); the request-link email/WhatsApp delivery ran synchronously in
  the request path, a timing side-channel for phone/email enumeration (now
  a Celery task, `deliver_customer_portal_link`, eager in tests so behavior
  is unchanged there, F1-007); the read-throttle's settings entry was dead
  configuration, never wired to the throttle class (now uses `scope`,
  F1-007b). Added the previously-zero test coverage for the one mutating
  endpoint on this surface (`CustomerPortalPayView`), including its IDOR
  case, plus default-off-flag and WhatsApp-opt-in-skip network-mock tests.
- **COMP-007** (2 Medium, the no-score/no-rank constraint confirmed intact):
  added an optional `date_from`/`date_to` filter and a `MAX_ROWS=200` cap
  with a `truncated` flag on the previously-unbounded result set (F1-010),
  and replaced the frontend's smoke-test-only coverage with real
  row-rendering, empty-state, and no-score-UI-element assertions.
- **COMP-009** (1 Medium, everything else verified clean by running 250+
  pre-existing GST/billing tests unchanged): `build_totals_preview` had
  quietly gained an extra `gst_rate` key not present in the original
  `billing.py`, contradicting the module's own "moved unchanged" docstring
  claim — reverted to restore byte-for-byte behavior. Added the top-priority
  test gap from the review: a drift-detection test asserting every name
  `billing.py` re-exports is the exact same object as `tax_engine.india`'s
  (not a local reimplementation that could silently diverge), plus a test
  pinning `build_totals_preview`'s exact response-item key set, which would
  have caught the `gst_rate` regression immediately.

All new and touched backend test files were run and pass
(`test_inventory_replenishment.py`, `test_gst_guard.py`,
`test_route_profit.py`, `test_tax_engine_registry.py`,
`test_customer_portal.py`, `test_supplier_price_history.py`,
`test_competitive_roadmap_performance.py`, plus the pre-existing
`test_phase2_gst.py`, `test_b05_attention.py`, `test_cft_checklist.py`,
`test_phase6_insights.py` regression suites and a broader
route/purchase-view/portal/payment-link sweep — 84 passed). Frontend:
`CustomerPortalPage.test.tsx`, `CustomerPortalRequestPage.test.tsx`,
`DeliveryRoutesPage.test.tsx`, `SuppliersPage.priceHistory.test.tsx` all
pass under `vitest`.

---

## Contents

- [CR-Phase 0 — Already in flight (pointer only)](#cr-phase-0--already-in-flight-pointer-only)
- [CR-Phase 1 — Unblocked near-term: COMP-002, COMP-006, COMP-005](#cr-phase-1--unblocked-near-term)
  - [COMP-002 — Replenishment suggestion](#comp-002--replenishment-suggestion)
  - [COMP-006 — GST Guard](#comp-006--gst-guard)
  - [COMP-005 — Route profit](#comp-005--route-profit)
- [CR-Phase 2 — Supplier price history: COMP-007](#cr-phase-2--supplier-price-history)
- [CR-Phase 3 — Customer self-service portal: COMP-003](#cr-phase-3--customer-self-service-portal)
- [CR-Phase 4 — Country-pack architecture boundary: COMP-009](#cr-phase-4--country-pack-architecture-boundary)
- [Cross-phase test & flag summary](#cross-phase-test--flag-summary)
- [Sequencing recap](#sequencing-recap)

---

## CR-Phase 0 — Already in flight (pointer only)

No new plan here — re-planning would create a second source of truth for
work already ticketed. See
`COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md` §1 for the full cross-reference
table. Snapshot:

| Item | Owning ticket | File |
|---|---|---|
| Production GSP (IRN, e-way, GSTR-1/3B) | `P0-01`, `B-01`, `B-02` | `WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md` |
| WhatsApp invoice + pay-link | `A-06` | same |
| AR dunning cadence | `A-07` | same |
| Tally migrate-once | `D-02` | same |
| Post-filing 2A/2B mismatch + WhatsApp | `B-03` | same |

---

## CR-Phase 1 — Unblocked near-term

Goal: ship the three tickets that need no product decision to start
(`COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md` §0 — nothing here is
`[OPEN]`). All three reuse existing subsystems rather than adding new ones,
which is why they're sequenced first.

### COMP-002 — Replenishment suggestion

**Design decision (grounded in code, corrected 2026-09-23 before implementation):** `insights/attention.py`
(`/attention`, what the dashboard links to) reads `build_business_alerts()`
directly — a list of live dicts assembled from a fixed tuple of
`(name, builder)` functions inside that call, fault-isolated via
`_run_alert_builder`. `insights.models.BusinessAlertEvent` is a **separate**
stored inbox, written by `insights/services.py:upsert_alerts()` and read by
a different endpoint — Attention does not read it. Writing a
`BusinessAlertEvent` row would **not** show up on Today. Do not do that.

Do not add a second, independently-triggered builder either. `_low_stock()`
(line ~148) already exists, already drives `LOW_STOCK_FAST_MOVER`, and
already resolves per-warehouse `WarehouseReorderLevel` via
`inventory/views.py:low_stock_alert_payload`. **Extend that function in
place** to attach a suggested quantity to the same row, under the same
trigger condition it already uses (`available <= reorder_level` and sold in
the last 14 days). This is what makes the zero-configured case behave
identically to today's alert — not a property of the formula alone, but of
reusing the same trigger.

**Corrected formula** (the original — `velocity_14d/14 * lead_time_days +
safety_stock_qty - (on_hand - reserved)`, no `reorder_level` term — returns
0 whenever stock is non-negative and both new fields are unset, silently
suppressing every existing low-stock alert on day one):

```python
if lead_time_days > 0:
    suggested_qty = max(Decimal("0"), safety_stock_qty + (velocity_14d / 14) * lead_time_days - available)
else:
    # unconfigured: fall back to today's threshold-only behavior exactly
    suggested_qty = max(Decimal("0"), reorder_level - available)
```

**1. Data model.**
`inventory/models.py` `WarehouseReorderLevel` (line 302) currently has only
`reorder_level`. Add two optional fields:

```python
# inventory/migrations/0019_reorder_lead_time_safety_stock.py
lead_time_days = models.PositiveIntegerField(default=0)
safety_stock_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
```

Both default to zero/blank so existing rows need no backfill and no
behavior changes until an owner sets them.

**2. Service layer.**
- `inventory/services.py`: add `suggest_replenishment(company, warehouse, product, *, on_hand, reserved, reorder_level) -> ReplenishmentSuggestion` (small dataclass: `available`, `velocity_14d`, `lead_time_days`, `safety_stock_qty`, `suggested_qty`, `transfer_from_warehouse_id | None`), implementing the corrected formula above. Velocity reads `StockMovement` (trailing 14 days, same window `_low_stock()` already uses for its "sold recently" check — reuse that query's date range, don't recompute it separately) — no new table.
- Transfer-vs-purchase: query `StockBalance` for the same `product` across other warehouses in the company; among those above their own reorder level, suggest the **largest-surplus** one by name. The screen the row links to (step 4) stays editable — this is a default, not a lock.

**3. Alerts engine hook — extend `_low_stock()`, do not add a parallel builder.**
`insights/alerts.py`, inside the existing `_low_stock()` function (line
~148): for each `bal` already being iterated, call
`suggest_replenishment(...)` and attach the result to the **existing**
`LOW_STOCK_FAST_MOVER` row via `payload={"suggested_qty": ..., "transfer_from_warehouse_id": ...}`
on the same `_alert(...)` call already there — no new alert code, no new
entry in the builder tuple at line ~301, no `BusinessAlertEvent` write.

**4. API.** No new endpoint required for the suggestion itself — it rides
the existing alerts/Today API via the payload above. One new action: the
row's CTA opens the existing PurchaseOrder (or StockTransfer) create screen
pre-filled via query params (`?supplier=&product=&qty=&warehouse=`) — reuse
the existing create form, don't build a new submission path. This keeps
the "owner approves, nothing auto-creates" rule mechanically enforced:
there is no backend path that creates a PO or transfer without the owner
completing the normal create screen and saving it themselves.

**5. Frontend.** Wherever `LOW_STOCK_FAST_MOVER` rows already render on
Today: add the suggested quantity and, when present, the named transfer
source, linking to the pre-filled create screen per above. This is a row
enrichment, not a new row type.

**6. Flag.** `ENABLE_REPLENISHMENT` — register in
`feature_flags.py`'s flag list alongside `ENABLE_TDS`/`ENABLE_GSTR` etc.,
default off. Gates whether the suggestion fields are computed/shown; the
underlying `LOW_STOCK_FAST_MOVER` alert itself is unaffected either way.

**7. Tests.**
- `backend/tests/test_inventory_replenishment.py` (new): suggestion math
  for both formula branches (configured and unconfigured), transfer-source
  selection among multiple surplus warehouses, zero-velocity edge case.
- `backend/tests/test_insights_alerts.py` (existing, extend): confirm
  `LOW_STOCK_FAST_MOVER` fires under exactly the same condition as before
  this change, with the new payload fields present but the trigger
  untouched — this is the regression test that makes the DoD line below
  actually true, not just asserted.

**DoD.**
- [x] Suggested quantity and, when applicable, a named transfer source
      appear on the existing `LOW_STOCK_FAST_MOVER` Today row.
- [x] No document created without the owner completing the existing create
      screen.
- [x] `WarehouseReorderLevel` rows with `lead_time_days=0` and
      `safety_stock_qty=0` produce the **same trigger and the same
      fallback quantity** (`reorder_level - available`) as today's
      threshold-only alert — proven by the regression test in §7, not
      just claimed.
- [x] Flag default off; migration is additive-only, no data backfill.

**Effort:** 1–2 weeks (unchanged — this correction is a same-sized ticket,
just aimed at the right file).

---

### COMP-006 — GST Guard

**Corrected 2026-09-23, before any implementation started** — the original
plan proposed a new `sales/gst_guard.py` module duplicating checks that
already exist elsewhere, included a duplicate-invoice-number check the
database already makes unreachable, and left the active-GSTIN skip/fail
rule ambiguous enough to either false-alert on every invoice or false-pass
silently. Corrected design below, scoped down after reading
`reporting/gst_health.py` and `reporting/gst_rate_scan.py` in full.

**What's already built — do not reimplement.**
- `reporting/gst_health.py` already checks, per completed GST invoice:
  `HSN_MISSING`, `HSN_DIGITS_INSUFFICIENT`, `RATE_NONSTANDARD`,
  `INVOICE_VALUE_MISMATCH`, `PARTY_GSTIN_MISSING_B2B` (presence, not
  format), `POS_UNKNOWN` (place-of-supply/buyer-state completeness — this
  covers what was proposed as check 6, exactly), `EWAY_EXPIRED`, and the
  company's **own** `GSTIN_INVALID_FORMAT` / `GSTIN_UNVERIFIED`.
- `reporting/gst_rate_scan.py` (`backscan_rate_exposure`, B-06) already
  does the tax-rate-vs-HSN cross-check (proposed check 5) against the
  effective-dated `HsnRate` table.
- `SalesInvoice` has `uniq_sales_number_per_company` (company + number,
  no FY scoping) — a duplicate-number check (proposed check 4) can never
  find a row the database would have allowed to save. **Dropped, not
  built.**
- This already all feeds Today: `insights/alerts.py`'s `_gst_health()`
  builder (line ~280) surfaces a `GST_HEALTH_CRITICAL_OPEN` row whenever
  `build_gst_health()` has open critical items.

**What's actually new — the only two checks this ticket adds.**
`Customer` (`masters/models.py` line 80) already has a
`gstin_verification_status` field, same shape as `Supplier`'s — nothing
currently populates or checks it per-invoice. Add, inside
`reporting/gst_health.py`'s existing per-invoice loop (next to the
`party_gstin` / `POS_UNKNOWN` block, ~line 207):
1. **`GSTIN_FORMAT_INVALID` (buyer)** — when `party_gstin` is present but
   fails the existing GSTIN regex/checksum validator (reuse it; don't
   reimplement). `gst_health.py` already checks the company's own GSTIN
   format this way — mirror that for the buyer.
2. **`GSTIN_INACTIVE` (buyer)** — only when a live provider is configured
   (`core/services/gstin_verify.get_gstin_provider()` is not
   `NullGstinProvider`): look up `party_gstin`, and alert only when the
   result status is `INVALID`, `CANCELLED`, or `SUSPENDED`. When the
   provider is null, or the result is `UNVERIFIED` (which is exactly what
   `NullGstinProvider` returns for a format-valid GSTIN — this is not a
   failure state, it's "we don't have a live opinion"), **skip and log,
   do not alert.** This is the rule that avoids both failure modes: a
   false alert storm from treating `UNVERIFIED` as bad, and a silent
   false pass from treating it as good.

Both checks run over `GST_INVOICE_TYPES` (`reporting/gst_returns.py`,
`{GST, TAX, RETAIL}`) — the same constant every other GST-health/rate-scan
check already uses; don't hand-write a narrower list. A blank buyer GSTIN
is skipped silently (B2C), same treatment `PARTY_GSTIN_MISSING_B2B`
already gives it.

**1. Trigger point.** These run wherever `build_gst_health()` already runs
— no new trigger needed. If a "check right before I file" manual re-run is
wanted, it already exists as whatever endpoint serves `/reports/gst-health`
today; no new endpoint required for this ticket.

**2. Alerts engine hook.** None needed beyond what exists — the two new
checks are entries in `build_gst_health()`'s existing `alerts` list. No new
alert code, no new builder in `alerts.py`, no `BusinessAlertEvent` write.
Severity is **`critical`** for both (same as the company's own
`GSTIN_INVALID_FORMAT`). That is what makes them visible:
- `insights/attention.py` `_itc_and_gst_rows()` already turns each critical
  `build_gst_health()` alert into its own `GST_GUARDRAIL` Attention row,
  using the alert `message` (so the row names the invoice and the rule)
  and `document_type` / `document_id` (cap 25 critical alerts, existing).
  Set those two fields the same way `POS_UNKNOWN` does.
- `_gst_health()`'s `GST_HEALTH_CRITICAL_OPEN` row is only a count of
  `summary.critical`. A `warning` would increment neither path, so the
  check would never reach Today.
The named detail also stays on `/reports/gst-health`. Use
`core.validators.validate_gstin` (regex **and** checksum). The company
GSTIN check in this file uses `GSTIN_RE` only — do not copy that shorter
path for the buyer. Run it on the party GSTIN the invoice already uses
(`filing_party_gstin` or `customer.gstin`), not only the `Customer` field,
because the stamp can differ from the master.

**3. Flag.** `ENABLE_GST_GUARD`, default off, gating just these two new
checks inside `build_gst_health()` (not the whole function — everything
else in `gst_health.py` keeps running regardless of this flag, since it
predates this ticket).

**4. CA sign-off — gates going live, not merging code.** A CA needs to
confirm these two checks' exact behavior (especially the
skip-vs-alert line on `UNVERIFIED`) before `ENABLE_GST_GUARD` is turned on
for any pilot — same pattern already used for B2CL threshold and cess
handling (`FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md` §0.1 rows 23–24) and for
the P0 GSP track ("eng may merge fail-closed code before the contract").
Eng builds and tests behind the flag now; the flag stays off until signed.

**5. Tests.**
- `backend/tests/test_gst_guard.py` (new): buyer-GSTIN format check (valid,
  invalid, blank-skipped); active-GSTIN check for each of `INVALID` /
  `CANCELLED` / `SUSPENDED` (alert) vs. `UNVERIFIED` / null-provider
  (skip, no alert, logged); confirms no duplicate-number check exists
  anywhere in this module.
- Extend whatever test file already covers `build_gst_health()` — do not
  create a parallel one.

**DoD.**
- [x] Only the two new checks above are added; nothing from the "already
      built" list above is reimplemented.
- [x] Both new alerts are `critical`, with `document_type` and
      `document_id`, so the existing `GST_GUARDRAIL` Attention mapper names
      the invoice. `UNVERIFIED` and null-provider both skip-and-log; only
      `INVALID`/`CANCELLED`/`SUSPENDED` alert.
- [x] Runs over `GST_INVOICE_TYPES` (reused constant), blank buyer GSTIN
      skipped silently.
- [ ] CA has signed the two checks' behavior (tracked in
      `COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md` §5) before the flag is
      turned on for any pilot — not before it's merged.
- [x] Flag default off.

**Effort:** revised down to **1–1.5 weeks eng + CA review calendar** — the
scope is now two checks inside an existing function, not a new module
duplicating three already-built ones.

---

### COMP-005 — Route profit

**Design decision (grounded in code, corrected 2026-09-23 before implementation):** `DeliveryRoute` (line 767) already
has `estimated_logistics_cost` / `actual_logistics_cost`, and
`complete_route()` already persists the actual cost. COGS is not a field
on the invoice. Read it back through `CogsService.invoice_sale_moves(invoice)`,
which returns a `list[StockMovement]`: `SALE` rows whose
`reference_type="sales_invoice"`, plus `SALE` rows for delivery challans
with `converted_invoice` pointing at that invoice and `stock_posted=True`.
Sum `unit_cost * abs(quantity)`. The challan branch inside
`CogsService.post_sale_stock_and_cogs` already uses `abs` on movement
quantity; a raw `move.quantity` multiply can flip the sign. Do not write a
second `reference_type` / `reference_id` filter. Build on
`feature/sales-purchase-ux`.

**1. Data model.** `DeliveryRoute` gets three new fields to persist the
outcome (the near-term roadmap item explicitly wants an "outcome record,"
not just a live-computed number that vanishes on next page load):

```python
# sales/migrations/0052_route_profit_fields.py
realized_revenue = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
realized_cogs = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
realized_profit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
invoiced_stop_count = models.PositiveIntegerField(null=True, blank=True)
stop_count = models.PositiveIntegerField(null=True, blank=True)
```
Nullable — only populated at route Complete, so `PLANNED`/`IN_TRANSIT`
routes are unaffected. The two counts are part of the same snapshot: a
later invoice must not change "N of M" while `realized_*` stays frozen.

**Corrected 2026-09-23, before any implementation started:**
`sales/route_service.py:complete_route()` **already** accepts and persists
`actual_logistics_cost` (line ~155–166), and `DeliveryRoutesPage.tsx`
already sends it — that half of this ticket is done, not planned. What's
actually new is steps 2–5 below. Four open questions are resolved here
rather than left for whoever builds this:
- **Tax base:** taxable total, not grand total. GST collected is a
  pass-through, not revenue, and `insights/alerts.py`'s existing
  `_margin()` check (`MARGIN_DROP_SKU`) already compares pre-tax
  `unit_price` to cost — grand-total-inclusive profit would be
  inconsistent with how margin is computed everywhere else in this
  codebase.
- **Uninvoiced stops:** exclude from the sum, don't block completion.
  `complete_route()` has no invoicing precondition today and adding one is
  a new business rule outside this ticket's scope. Surface "N of M stops
  invoiced" alongside the figure so it reads as partial, not silently
  wrong.
- **Returns/credit notes after completion:** the three `realized_*` fields
  freeze at Complete. This is an outcome record, not a live report —
  retroactively mutating it when a return happens weeks later is a
  separate, later decision, not v1 scope.
- **Today row:** not required. A completed route's profit isn't an open
  exception to act on the way AR-overdue or low-stock are — nothing to do
  about it, so it doesn't compete for Today space. The route detail screen
  is the only surface.

**2. Service layer.** New `sales/route_profit_service.py`:
```python
def compute_route_financials(route) -> RouteFinancials:
    # for each DeliveryRouteStop whose sales_order.converted_invoice exists:
    #   revenue += invoice.taxable_total
    #   cogs += sum(unit_cost * abs(quantity) for move in
    #               CogsService.invoice_sale_moves(invoice))
    # invoiced_stop_count / stop_count snapshotted with the three money fields
    # profit = revenue - cogs - route.actual_logistics_cost
```
`invoice_sale_moves` (read 2026-09-23) returns that combined list of
`StockMovement` rows. Call it; do not re-query by `reference_type`.

**3. Trigger point.** `sales/route_service.py:complete_route()` — after the
existing `actual_logistics_cost` assignment and `status = COMPLETED`, and
only when `ENABLE_ROUTE_PROFIT` is on, call `compute_route_financials(route)`
and persist the three money fields plus the two stop counts before
`route.save()`. Flag off: completion behaves exactly as it does today.

**4. API.** Extend the existing route detail serializer
(`sales/route_serializers.py`) to return the three `realized_*` fields and
the snapshotted stop counts. `actual_logistics_cost` acceptance on
completion needs no change — already wired.

**5. Frontend.** Extend the existing route detail screen
(`DeliveryRoutesPage.tsx`) to show trip profit and the invoiced-stop count
after completion. No new page, no Today row.

**6. Flag.** `ENABLE_ROUTE_PROFIT`, default off.

**7. Tests.**
- `backend/tests/test_route_profit.py` (new): taxable-total-based margin
  using `abs(quantity)` off `invoice_sale_moves`; a stop with no converted
  invoice yet (excluded from the sum, reflected in the snapshotted counts,
  does not block completion); a route with zero stops (no divide-by-zero);
  `realized_*` and the two counts stay `null` on `PLANNED`/`IN_TRANSIT`;
  once set at Complete, money fields and counts are unchanged by a later
  return/CN and by a later invoice on a previously uninvoiced stop.

**DoD.**
- [x] Trip profit = Σ(taxable total − COGS via `CogsService.invoice_sale_moves`)
      across invoiced stops, minus actual logistics cost — computed and
      persisted at Complete, frozen thereafter.
- [x] Uninvoiced stops excluded from the sum, not blocking; invoiced-stop
      count snapshotted at Complete and shown alongside the figure.
- [x] No routing/dispatch/vehicle-capacity logic added — scope stays cost
      capture + margin tie-in only, per the freeze list in
      `COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md` §3.
- [x] No Today row for this ticket — route detail screen only.
- [x] Flag default off; existing routes with no realized-* data are
      unaffected (nullable fields).

**Effort:** 2–3 weeks (unchanged — resolving the open questions here
didn't change the size, just removed the ambiguity that would have stalled
implementation).

---

## CR-Phase 2 — Supplier price history

### COMP-007 — Supplier price history (no score)

**Design decision (grounded in code):** purely additive and read-only.
`purchases/models.py` already has everything needed: `PurchaseOrder` (line
332), `PurchaseInvoice` (line 9), `GoodsReceipt` (line 464), each linked to
`masters.Supplier` (line 176). No new data collection, no new write path.

**1. Data model.** None. This ticket adds zero migrations — it's a query
over existing tables.

**2. Service/API layer.** New read endpoint:
`GET /purchases/suppliers/{id}/price-history/?product={id}` → for the
given supplier+product, return each dated PO/invoice line's unit price,
ordered by date, so a jump or slow creep is visible by inspection. Implement
as a `SupplierPriceHistoryView` in `purchases/views.py` querying
`PurchaseInvoiceItem`/`PurchaseOrderItem` (whichever carries `unit_price`
per line — confirm the exact item-model field name during implementation,
not guessed here) filtered by `supplier`/`product`, no aggregation, no
scoring, no cross-supplier comparison.

**3. Frontend.** New tab/section on the existing Supplier detail page:
a simple table or sparkline of price-over-time per product. Explicitly
**not**: a score, a rank, a "switch supplier" suggestion, or any comparison
across suppliers — per the resolved scope in
`COMPETITIVE_ROADMAP_IMPLEMENTATION_PLAN.md` §0 Decision 1.

**4. Flag.** `ENABLE_SUPPLIER_PRICE_HISTORY`, default off, and not riding
`ENABLE_ACCOUNTING`. Adopted 2026-09-23: own flag, UI on `SuppliersPage`.

**5. Tests.** `backend/tests/test_supplier_price_history.py` (new):
correct ordering, correct scoping to supplier+product, empty-history case,
confirms no scoring/ranking field appears anywhere in the response payload
(a regression guard against scope creep back toward COMP-007's original,
rejected scorecard form).

**DoD.**
- [x] Price-history rows shown per supplier/product, sourced from existing
      PO/invoice data.
- [x] No score, rank, or reliability label anywhere in API or UI.
- [x] Zero new migrations.
- [x] Flag default off.

**Effort:** 1 week (confirmed — this is the smallest ticket in the plan).

---

## CR-Phase 3 — Customer self-service portal

### COMP-003 — Customer self-service portal

**Status:** built 2026-09-23 behind `ENABLE_CUSTOMER_PORTAL`, default off.
The tier call is closed: ship the magic-link portal now, flag off.

**Design decision (grounded in code):** reuse the existing public-page
pattern wholesale. `web/src/pages/public/PublicPayPage.tsx` already
establishes the pattern this should follow: token-in-URL, no login form,
`react-query` against a public (unauthenticated but token-scoped) endpoint,
MUI Card/Stack layout, `isAllowedPaymentUrl`-style URL allowlisting for
anything clickable. `payments/models.py` `PaymentLink` (line 270) is the
direct model precedent for a scoped, expiring, token-based access grant —
the new model below is deliberately shaped like it.

**1. Data model.** New model, `payments/models.py` (co-located with
`PaymentLink` since it's the closest precedent) or a new
`customers/models.py` if a dedicated app is preferred — default to
`payments/models.py` to avoid a new Django app for one model:

```python
# payments/migrations/0031_customer_portal_token.py
class CustomerPortalToken(CompanyScopedModel):
    token = models.CharField(max_length=64, unique=True, db_index=True)
    customer = models.ForeignKey("masters.Customer", on_delete=models.CASCADE, related_name="portal_tokens")
    requested_via = models.CharField(max_length=16, choices=[("EMAIL", "Email"), ("WHATSAPP", "WhatsApp")])
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
```
Short-lived (propose 15-minute expiry, re-issuable) — a magic link, not a
persistent session, matching "no password to manage."

**2. Service/API layer.**
- `POST /public/customer-portal/request-link/` — body: phone or email
  matching a known `Customer` record. Issues a `CustomerPortalToken`, sends
  it via the existing `core/services/whatsapp.py` (Cloud API + `wa.me`
  fallback, same as A-06) or email. **Rate-limit this endpoint** (reuse
  `core/throttles.py`'s `CompanyRateThrottle` pattern) — it's an
  unauthenticated enumeration surface otherwise.
- `GET /public/customer-portal/{token}/` — validates token + expiry, marks
  `last_used_at`, returns the customer's invoice list (number, date,
  status, amount, outstanding) scoped strictly to that customer — reuse
  existing `SalesInvoice` serializers with a customer-scoped queryset, not
  a new serializer from scratch.
- `GET /public/customer-portal/{token}/invoices/{id}/pdf/` — reuses the
  existing PDF generation path (`sales/pdf/gst_tax_invoice.py`) already
  used for the owner-facing download, scoped to confirm the invoice
  belongs to the token's customer before serving.
- Payment: link out to the existing `PublicPayPage` flow for anything
  outstanding — do not duplicate payment-collection logic here.

**3. Frontend.** New `web/src/pages/public/CustomerPortalRequestPage.tsx`
(phone/email entry, "we sent you a link") and
`web/src/pages/public/CustomerPortalPage.tsx` (invoice list + PDF download
+ pay-link entry points), styled consistently with `PublicPayPage.tsx`.

**4. Scope discipline (explicit, per the ticket doc).** v1 is read-only:
invoice list, status, PDF, pay. **Not** in v1: editable customer data,
order placement, support ticketing.

**5. Flag.** `ENABLE_CUSTOMER_PORTAL`, default off.

**6. DPDP/consent.** Same posture as WhatsApp Cloud sends elsewhere in this
repo (`A-06`'s `Customer.whatsapp_opt_in` gate) — sending a portal link via
WhatsApp Cloud needs the same opt-in field; email doesn't need the same
gate but should still be logged.

**7. Tests.**
- `backend/tests/test_customer_portal.py` (new): token issuance, expiry,
  single-use-vs-reusable-within-expiry decision (pick one, test it),
  scoping (customer A's token cannot see customer B's invoices — this is
  the one test that must never be allowed to regress), rate-limit on the
  request endpoint.
- Frontend: a smoke test on `CustomerPortalPage.tsx` mirroring whatever
  test coverage `PublicPayPage.tsx` already has, if any.

**DoD.**
- [x] A named customer can request a link and view/pay their own
      outstanding invoices without an owner's help.
- [x] Strict per-customer scoping, tested explicitly.
- [x] No write access beyond payment.
- [x] Request endpoint is rate-limited.
- [x] Flag default off.

**Effort:** 3–5 weeks (confirmed — new auth surface + two new frontend
pages is genuinely the largest of the five product tickets; COMP-009 is
larger but is architecture, not a product surface).

---

## CR-Phase 4 — Country-pack architecture boundary

### COMP-009 — Country-pack architecture boundary

**Status:** seam and sales/purchase totals call sites are in, 2026-09-23.
No second country. Timing is no longer open: the India pack ships now.

**Design decision (grounded in code).** `core/services/billing.py`
currently exposes 14 module-level functions with no shared interface:
`q2`, `fold_tds_from_rate`, `extract_state_code`, `place_of_supply_known`,
`is_intra_state`, `_apply_line_tax`, `extract_exclusive_from_inclusive_line`,
`apply_inclusive_prices_to_items`, `apply_rcm_memo_after_tax`,
`_document_tax_date`, `apply_effective_gst_rate`, `compute_document_totals`,
`_tax_totals_snapshot`, `recompute_totals_for_stamped_gstin`,
`build_totals_preview`. Every one of these is India-specific in content
(CGST/SGST/IGST split, RCM, GST rate lookups) even though several are
generically named (`compute_document_totals`, `q2`). This is the "hardcoded
into core, not a swappable pack" finding from the competitive analysis §13.

**Step 0 — spike, before any refactor commitment (do this regardless of
the PM timing call — it's what makes the effort estimate real).**
Grep every call site of each of the 14 functions above across `sales/`,
`purchases/`, `reporting/`, and `accounting/`. The refactor's actual size is
dominated by call-site count, not by the 14 functions themselves — this
plan does not claim to know that count yet. Budget 2–3 days for this spike
and revise the effort range below once it's done.

**1. Target shape (not yet built — this is the design to spike against).**
```
core/services/tax_engine/
    base.py     # generic interface: TaxEngine protocol —
                #   compute_document_totals(), apply_effective_rate(),
                #   is_intra_jurisdiction(), round_amount(), etc.
                #   — no India-specific vocabulary (no "GST", "CGST" at
                #   this layer)
    india.py    # current billing.py content, adapted to implement the
                # protocol: GST split, state-code table, RCM memo,
                # TDS/TCS fold, HSN/SAC lookup
    registry.py # get_tax_engine(company) -> TaxEngine — returns the
                # India pack unconditionally today; this is the only
                # place a second country would ever plug in
```
`core/services/billing.py` stays a thin shim for helpers that are not
document totals (rounding, state codes, RCM, previews, tests). Sales and
purchase document totals now call
`get_tax_engine(company).compute_document_totals(...)`: invoices,
quotations, orders, notes, returns, and delivery challans in `sales/` and
`purchases/`. Tally import and the test suite still call the shim, which
reaches the same India function.

**2. Reference patterns to follow (from the competitive analysis, §13) —
worth re-reading before starting:** Dynamics 365 Business Central's
base-app-plus-country-extension model, and NetSuite's
SuiteTax-engine-plus-country-SuiteApp model. The pattern to avoid: SAP
Business One's patch-coupled localization, where GST currency depends on
being on the latest patch — i.e., don't let the India pack's correctness
depend on which BizBoard release a tenant happens to be on; it should be
one always-current module, not a patch-gated one.

**3. Tests.** This ticket's test plan is almost entirely regression, not
new-behavior: every existing GST-calculation test
(`backend/tests/test_*billing*.py`, `test_*gst*.py`, and the wide net of
sales/purchase invoice-completion tests that exercise `compute_document_totals`
indirectly) must pass unchanged, proving the refactor is behavior-neutral.
Add one new test asserting `get_tax_engine(company)` returns the India pack
for every existing tenant, to lock in today's single-pack reality
explicitly rather than leaving it implicit.

**DoD.**
- [x] Step 0 spike complete, effort range revised based on real call-site
      count.
- [x] All GST logic lives behind the `TaxEngine` interface in
      `core/services/tax_engine/india.py`.
- [x] `core/services/billing.py` re-exports the same public names — zero
      behavior change, zero call-site edits required elsewhere in this
      ticket.
- [x] Full existing GST/billing regression suite passes unchanged.
- [x] No second country pack exists yet — this ticket's DoD is the seam
      only, not new geography.

**Effort:** the seam plus the sales/purchase totals call sites are done.
Helpers other than `compute_document_totals` still import `billing.py`.
There is no second country pack.

---

## Cross-phase test & flag summary

| Ticket | New flag | New migration(s) | New test file(s) |
|---|---|---|---|
| COMP-002 | `ENABLE_REPLENISHMENT` | `inventory/0019_reorder_lead_time_safety_stock.py` | `test_inventory_replenishment.py` |
| COMP-006 | `ENABLE_GST_GUARD` | none | `test_gst_guard.py` |
| COMP-005 | `ENABLE_ROUTE_PROFIT` | `sales/0052_route_profit_fields.py` | `test_route_profit.py` |
| COMP-007 | `ENABLE_SUPPLIER_PRICE_HISTORY` | none | `test_supplier_price_history.py` |
| COMP-003 | `ENABLE_CUSTOMER_PORTAL` | `payments/0031_customer_portal_token.py` | `test_customer_portal.py` |
| COMP-009 | none (internal refactor) | none (structure only, no schema change) | regression only — no new fixtures |

All five product flags are registered in
`backend/core/services/feature_flags.py` and `settings.py`, default off.
COMP-009 has no flag. A company JSON grant can turn a product flag on;
`ENABLE_GST_GUARD` stays off until CA sign-off.

---

## Sequencing recap

```
CR-Phase 1 — built, flags off
   COMP-002 Replenishment
   COMP-006 GST Guard     (flag stays off until CA signs)
   COMP-005 Route profit
CR-Phase 2 — built, flag off
   COMP-007 Supplier price history
CR-Phase 3 — built, flag off
   COMP-003 Customer portal
CR-Phase 4 — seam plus sales/purchase totals call sites
   COMP-009 India tax engine (no second country)
```

Engineering for these phases is in the tree. The remaining gate is CA
sign-off before `ENABLE_GST_GUARD` is turned on for a pilot.
