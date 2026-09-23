# BizBoard — Competitive Roadmap Implementation Plan

**Status:** decided plan, 2026-09-23. Resolves the two open calls left in
[`ROUGH_COMPETITIVE_ROADMAP_2026-09-22.md`](ROUGH_COMPETITIVE_ROADMAP_2026-09-22.md)
against the evidence in
[`docs/COMPETITIVE_ANALYSIS_BIZBOARD.md`](../COMPETITIVE_ANALYSIS_BIZBOARD.md)
and turns the rest into tickets in this repo's own format. This file does
**not** replace
[`FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md`](FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md)
or the `WAVES_*_CURSOR_IMPLEMENTATION_PLAN.md` series — where a
competitive-analysis finding is **already** a live ticket there (P0 GSP,
WhatsApp, dunning, Tally migrate-once, IMS/2B), §1 below points at it instead
of re-specifying it. Only the genuinely new items get new tickets, in §2.

**Same doctrine as the rest of `docs/roadmap/`:** code + tests win for "what
exists today"; this doc wins for "what's newly intended." Everything new
ships behind a flag, default off. Do not make any pilot-facing or commercial
claim until `docs/pilot/GO_NO_GO.md` is signed. `GATE: human` items need a
named owner before they're real, not just a ticket.

**Ticket IDs** reuse the gap-register numbering from the competitive
analysis (`COMP-001`…`COMP-011`) so a reader can trace any ticket here back
to the evidence that justified it.

**Detailed build plan:** the six new tickets in §2 have a file-level,
phase-by-phase engineering plan (data model, service layer, API, frontend,
flag names, migration numbers, test files) in
[`COMPETITIVE_ROADMAP_PHASED_PLAN.md`](COMPETITIVE_ROADMAP_PHASED_PLAN.md).
This file stays the decision/ticket index; that file is where to look
before writing code.

**Revision note (2026-09-23, same day, pre-implementation):** CR-Phase 1
tickets below were narrowed after a code read. COMP-002 extends the
existing low-stock row instead of adding an alert. COMP-006 adds two buyer
GSTIN checks inside `reporting/gst_health.py` instead of a new IRP module.
COMP-005 is route-detail profit on taxable total, frozen at Complete, with
no Today row. File-level spec is the phased plan. Build CR-Phase 1 on
`feature/sales-purchase-ux`.

---

## Contents

0. [Resolved decisions](#0-resolved-decisions)
1. [Already planned elsewhere — cross-reference, don't re-plan](#1-already-planned-elsewhere--cross-reference-dont-re-plan)
2. [New tickets from the competitive analysis](#2-new-tickets-from-the-competitive-analysis)
3. [Freeze list additions](#3-freeze-list-additions)
4. [Already built — enablement / positioning only](#4-already-built--enablement--positioning-only)
5. [Still open — named humans required](#5-still-open--named-humans-required)
6. [Sequencing](#6-sequencing)
7. [Effort](#7-effort-rough-t-shirt-sizes-solo)

---

## 0. Resolved decisions

| # | Topic | Decision | Status |
|---|---|---|---|
| 1 | Supplier data shape (COMP-007) | Raw price-history rows (jump/creep) only. No judged reliability score, ever, without a written charter — matches "no row that cannot be checked" and the roadmap's existing refusal to let anything act on a judgment the owner didn't make. | `[ADOPTED 2026-09-23]` |
| 2 | Customer self-service portal priority (COMP-003) | Built now, behind `ENABLE_CUSTOMER_PORTAL`, default off. 15-minute reusable magic link (email, or WhatsApp only when `whatsapp_opt_in`). Invoice list, PDF, and pay reuse the existing payment link. Not a logged-in customer account, and not editable customer data, orders, or tickets. | `[ADOPTED 2026-09-23]` |
| 3 | Route optimization (the solver, not the profit report) | Partner, don't build. A mature, largely solved OR problem (VRP-class); Google OR-Tools / Mapbox Optimization API / OSRM are the commodity building blocks if this is ever revisited. Not scheduled. | `[ADOPTED]` — matches `ROUGH_COMPETITIVE_ROADMAP` "leave off" list |
| 4 | Automation-rule builder as a platform | Not building. No `AutomationRule`/`WorkflowRule` class exists today (only fixed cron + read-only alerts), and a general rule-engine platform rates high effort for this segment — Odoo's Studio is the one comparable done well, and it's gated to Odoo's Enterprise tier with partner support most of this buyer segment doesn't have. | `[ADOPTED]` |
| 5 | Country-pack architecture (COMP-009) — timing | Seam shipped: GST math lives in `core/services/tax_engine/india.py`; `get_tax_engine(company)` always returns the India pack. Sales and purchase document totals call that engine. `billing.py` still re-exports the other helpers. No second country. | `[ADOPTED 2026-09-23]` |

---

## 1. Already planned elsewhere — cross-reference, don't re-plan

The competitive analysis's "must-have parity" findings turn out to already
be live, dated, owned tickets in `WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md`
and `FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md`. Re-planning them here would
just create a second, drifting source of truth. Status snapshot as of this
plan's date — always defer to the source file for anything current.

| Competitive-analysis finding | Existing ticket(s) | Current status | Source |
|---|---|---|---|
| Production GSP for IRN, e-way bill, GSTR-1/3B filing (COMP-010) | **P0 track**: `P0-01` (human procurement), `B-01` (live IRN/e-way, fail-closed), `B-02` (GSTR-1/3B GSP upload) | GSP contract + sandbox tenant target 2026-10-11 (T0+6w); first production IRN target 2026-11-22 (T0+12w); first GSTR-1 GSP upload target 2026-12-20 (T0+16w). **RED until the owner table in the P0 track is filled** — this is the human procurement step the analysis's own "partner, don't build a GSP" recommendation [§12, §18] maps onto directly. | `WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md` §"P0 track" |
| WhatsApp for invoice PDF + payment link | `A-06` | Eng slice specified: Cloud API send with `wa.me` fallback on failure, DPDP opt-in gate (`Customer.whatsapp_opt_in`), honest UI ("WhatsApp Cloud" vs. "Open WhatsApp with message" — no false "delivered"). | `WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md` §A-06 |
| AR dunning cadence | `A-07` | Eng slice specified: owner opt-in 3/7/14-day cadence, WhatsApp then SMS fallback, skips paid-pending-books invoices. Matches this analysis's "rule-based cascade, stop before the ML-prediction tier" call [§9 Category verdict]. | `WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md` §A-07 |
| Tally import with a CA-signable difference report | `D-02` "Leave Tally once" | Hardens existing `backend/imports/services.py` CSV/XLSX import; explicitly **import-only, never sync** (UI copy must say "migrate," not "sync" — grepped for and enforced). Backup/restore parity or refuse destroy-in-place. | `WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md` §D-02 |
| Post-filing supplier mismatch detection ("who defected on GST") | `B-03` IMS + ITC control | Ingests IMS/2B (via GSP once P0-01 lands, or the GSTN offline-tool file with **no** GSP dependency), matches against books, identifies the supplier, generates a WhatsApp message. **Distinct from GST Guard (COMP-006, §2 below)**: B-03 checks what suppliers filed against BizBoard's purchases, after the fact; GST Guard checks BizBoard's own outgoing sales invoices before submission. Do not merge these two tickets — different data direction, different timing. | `WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md` §B-03 |
| Bank reconciliation trust gating | `Company.auto_match_bank_exact`, defaults `False` | Already matches "measure the match rate before trusting it" [§9] — this is an adopted decision, not an open question. | `FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md` §0.1 row 30 |
| Cash forecast | `insights/services.py forecast_cashflow` | Already built: AR-aging-weighted cash-in + AP-due-date cash-out over 7/14/30/90-day horizons, explicit heuristic disclaimer, refreshed daily via Celery beat. The medium-term roadmap item is about gating its visibility on bank-import trust, not building the forecast. | Codebase audit, 2026-09-22 |
| WhatsApp Cloud API, Tally CSV/XLSX/XML import, serial tracking, warehouses/batch/WAVG-FIFO, recurring invoices (draft-only), SO stock reservation, POS | Listed under "already built — enablement/hardening only" | Do not estimate any of these as greenfield. | `FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md` §0.4 |

---

## 2. New tickets from the competitive analysis

Everything below is genuinely absent from `WAVES_0_ABCD`, `WAVES_E_TO_L`,
`WAVES_M_TO_S`, and `FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md` — confirmed by
grep across `docs/roadmap/` before writing this section, not assumed.

### COMP-002 — Replenishment suggestion (reorder quantity, not just alert)

| | |
|---|---|
| Source | Competitive analysis §7, §18, §20 — gap register's own "must-have parity" tier |
| GATE | eng |
| Files | `inventory/models.py` (`WarehouseReorderLevel`), `inventory/services.py`, `insights/alerts.py` (`_low_stock`) |

**Problem.** Today's reorder logic is a threshold alert (`on_hand - reserved
<= reorder_level`, and sold in the last 14 days) with no suggested
quantity. Cin7 and NetSuite both auto-draft a purchase order for the owner
to review; Zoho Books/BUSY are threshold-only, same as BizBoard today.

**Plan.**
1. Add `lead_time_days` and `safety_stock_qty` on `WarehouseReorderLevel`
   (warehouse + product, not the supplier). Velocity window is a fixed 14
   days, the same window `_low_stock()` already uses. No company setting
   in v1.
2. Do not add a second alert. Extend `_low_stock()` in place, same trigger.
   When `lead_time_days > 0`, `suggested_qty = max(0, safety_stock_qty +
   velocity_14d/14 * lead_time_days - available)`. Otherwise
   `suggested_qty = max(0, reorder_level - available)`. Attention already
   reads this builder live. Do not write `BusinessAlertEvent`.
3. If other warehouses are above their own reorder level, name the
   largest-surplus warehouse on the row. The existing Purchase Order or
   Stock Transfer create screen opens pre-filled and stays editable.
   Nothing is created until the owner saves that screen.
4. `ENABLE_REPLENISHMENT` gates the suggestion payload only. The existing
   low-stock alert still fires when the flag is off.

**DoD.**
- [x] The existing `LOW_STOCK_FAST_MOVER` row shows the suggested quantity
      and, when applicable, the named transfer source.
- [x] Unconfigured reorder rows (`lead_time_days=0`, `safety_stock_qty=0`)
      keep today's trigger and use `reorder_level - available`.
- [x] No document (PO or transfer) is created until the owner saves the
      existing create screen.
- [x] Flag default off; the low-stock alert itself is unchanged for a
      tenant that doesn't opt in.

---

### COMP-003 — Customer self-service portal (built, `ENABLE_CUSTOMER_PORTAL` default off)

| | |
|---|---|
| Source | Competitive analysis §4 (Master Feature Matrix), gap register COMP-003 |
| GATE | eng + PM (tier decision) |
| Files | `web/src/pages/public/PublicPayPage.tsx` (existing public surface to extend or sit beside), existing document/invoice APIs |

**Problem.** BizBoard's only customer-facing surface today is a bare
payment-link page. Zoho Books (Premium tier+), Odoo, QuickBooks, and Xero
all give a customer a real "log in, see my invoice history, download PDFs,
pay what's outstanding" view. This is a confirmed parity gap, not a
differentiation opportunity — closing it is about not losing a larger
customer who expects it, not about winning on it.

**Plan (scoped for when triaged in — not blocking on the tier decision).**
1. A customer-scoped, low-friction auth (magic link tied to a known phone/
   email on the `Customer` record — no password to manage, matching the
   product's existing anti-friction posture).
2. Read-only: invoice list, status (unpaid/paid/paid-pending-books — reuse
   the state machine payments already has), PDF download, pay-link entry
   point for anything outstanding.
3. Explicitly **not** in v1: editable customer data, order placement,
   support ticketing — those are separate, larger bets not evidenced as
   near-term needs in this research pass.

**DoD.**
- [x] A named customer can view and pay their own outstanding invoices
      without an owner's help.
- [x] No write access beyond payment.
- [x] Flag default off.

---

### COMP-005 — Route profit (cost capture + margin tie-in)

| | |
|---|---|
| Source | Competitive analysis §15, §18, §21 — the single strongest evidence-backed whitespace finding in the whole analysis |
| GATE | eng |
| Files | `sales/models.py` (`DeliveryRoute`), `sales/route_service.py` (`complete_route`, already stores `actual_logistics_cost`), `sales/cogs_service.py` (`invoice_sale_moves`), `sales/route_serializers.py`, `web/src/pages/sales/DeliveryRoutesPage.tsx` |

**Problem.** No route-optimization vendor researched (Onfleet, Circuit,
Locus, FarEye) was confirmed to tie route cost back to the margin of what
was actually delivered on it — one vendor (Mapline) claims "profitability"
in marketing copy only, with no case study found. BizBoard already holds
both halves of this — route cost fields on `DeliveryRoute`, and per-SO
margin via `cogs_service.py` — that pure logistics point-tools structurally
lack. This is already scoped as a near-term item in
`ROUGH_COMPETITIVE_ROADMAP` ("route completion... trip profit"); this
ticket is that item's build spec, not a new decision.

**Plan.**
1. Actual fuel + driver cost is already captured: `complete_route()`
   persists `actual_logistics_cost`, and `DeliveryRoutesPage.tsx` already
   sends it. Do not rebuild that prompt.
2. On Complete, when `ENABLE_ROUTE_PROFIT` is on, snapshot trip profit.
   Revenue is each invoiced stop's `taxable_total` (tax out). COGS is
   `unit_cost * abs(quantity)` over `CogsService.invoice_sale_moves(invoice)`.
   Profit = that margin minus `actual_logistics_cost`. Uninvoiced stops are
   excluded and do not block completion. Store invoiced-stop count and
   stop count in the same snapshot.
3. Show that snapshot on the route detail screen only. No Today row — a
   completed trip is not an open exception.
4. Freeze the snapshot at Complete. A later return, credit note, or
   invoice does not rewrite it.
5. **Do not** build route optimization/sequencing in this ticket — see
   Decision 3 in §0.

**DoD.**
- [x] Route completion already asks for actual logistics cost; this ticket
      does not add a second prompt.
- [x] Trip profit (taxable revenue − COGS − actual logistics cost) and the
      invoiced-stop count are persisted at Complete and shown on the route
      detail screen.
- [x] Uninvoiced stops are excluded, not a completion blocker. The count
      does not move after Complete.
- [x] No routing/dispatch/vehicle-capacity logic added — that stays frozen
      (§3). No Today row.
- [x] Flag default off. Flag off leaves `complete_route()` as it is today.

---

### COMP-006 — GST Guard (pre-filing validation, not post-filing reconciliation)

| | |
|---|---|
| Source | Competitive analysis §7, §15, §18 — second-strongest evidence-backed whitespace finding |
| GATE | eng + CA (sign-off before the flag is turned on for a pilot, not before merge) |
| Files | `reporting/gst_health.py` (extend the existing per-invoice loop), `core/services/gstin_verify.py`, `core/validators.py` (`validate_gstin`) |
| Distinct from | `B-03` (IMS/ITC control) — see §1. Also distinct from checks already in `gst_health.py` and `gst_rate_scan.py` (HSN presence/digits, place of supply, rate-vs-HSN, company GSTIN). Do not reimplement those. |

**Problem.** Buyer GSTIN format/checksum and live active-status are not
checked. `gst_health.py` checks the company's own GSTIN format, and
`PARTY_GSTIN_MISSING_B2B` checks that a buyer GSTIN is present. Nothing
checks the buyer's format or live status. `Customer.gstin_verification_status`
exists and is not filled by a per-invoice check. HSN, place of supply, and
rate-vs-HSN are already built. Duplicate invoice numbers cannot occur:
`uniq_sales_number_per_company` already rejects them.

**Plan.**
1. Inside `build_gst_health()`, for invoices in the existing
   `GST_INVOICE_TYPES` set (`GST`, `TAX`, `RETAIL`), add two critical
   alerts when a buyer GSTIN is present:
   - `GSTIN_FORMAT_INVALID` via `validate_gstin` (regex and checksum) on
     `filing_party_gstin` or `customer.gstin`.
   - `GSTIN_INACTIVE` via `gstin_verify.get_gstin_provider()`, only when
     the provider is not `NullGstinProvider` and the lookup status is
     `INVALID`, `CANCELLED`, or `SUSPENDED`.
2. Blank buyer GSTIN: skip silently. Null provider, or status
   `UNVERIFIED`: skip and log. Do not treat `UNVERIFIED` as a failure or
   as a pass.
3. No new module, no new `alerts.py` builder, no `BusinessAlertEvent`.
   Critical alerts already become named `GST_GUARDRAIL` Attention rows
   (and increment the existing `GST_HEALTH_CRITICAL_OPEN` count). A
   mismatch still does not block Complete.
4. `ENABLE_GST_GUARD` gates only these two checks. CA sign-off gates
   turning that flag on for a pilot. Engineering may merge the code
   behind the default-off flag before sign-off — same posture as the P0
   GSP track.

**DoD.**
- [x] Only the two buyer-GSTIN checks above are added.
- [x] `UNVERIFIED` and a null provider skip and log. `INVALID`,
      `CANCELLED`, and `SUSPENDED` alert.
- [x] Blank buyer GSTIN is skipped. Invoice types follow
      `GST_INVOICE_TYPES`, Retail included.
- [x] Each failing check is a critical `gst_health` alert that names the
      invoice, so the existing Attention mapper can show it. No new Today
      row type.
- [ ] CA has signed the two checks before the flag is turned on for a
      pilot, not before the code is merged.
- [x] Flag default off. Complete's blocking behavior is unchanged.

---

### COMP-007 — Supplier price history (resolved scope: no score)

| | |
|---|---|
| Source | Competitive analysis §15, §18, Appendix A #6 — resolved per Decision 1 in §0 |
| GATE | eng |
| Files | `purchases/models.py` (`PurchaseOrder`, `PurchaseInvoice`, `GoodsReceipt`), `masters/models.py` (`Supplier`) |

**Problem/resolution.** The competitive analysis's default recommendation
was a rule-based reliability *scorecard* (on-time %, lead-time variance).
This roadmap's decision (§0.1) is narrower: **rows of price history per
supplier per item — jump and creep — with no judged score, rank, or
"reliability" label of any kind.** The underlying PO/GRN/invoice-timestamp
data both readings agree is valuable; this ticket ships only the checkable
version.

**Plan.**
1. For a given supplier + item, show price paid over time (each PO/invoice
   line, dated) so a jump or a slow creep is visible by inspection.
2. No aggregate score, no ranking against other suppliers, no automatic
   "switch supplier" suggestion.
3. If a future ticket ever proposes a scored version, it needs a written
   charter per Decision 1 — this ticket is not that charter.

**DoD.**
- [x] Price-history view exists per supplier/item, sourced from existing PO/
      invoice data — no new data collection required.
- [x] No score, rank, or reliability label anywhere in the UI or API for
      this ticket.

---

### COMP-009 — Country-pack architecture boundary (India stays the only pack shipped)

| | |
|---|---|
| Source | Competitive analysis §13 — the single highest architectural-priority finding in the whole analysis |
| GATE | eng (architecture), PM (timing — see §5) |
| Files | `core/services/billing.py` (GST math + inline `IN_STATE_NAME_TO_CODE` table — the thing being extracted from), `sales/`, `purchases/` tax call sites |

**Problem.** GST math lives directly in `core/services/billing.py` today,
not behind a swappable interface. Two reference patterns are worth building
toward: Dynamics 365 Business Central's base-app-plus-country-extension
model, and NetSuite's SuiteTax-engine-plus-country-SuiteApp model. The
pattern to avoid is SAP Business One's patch-coupled localization, where
GST currency depends on being on the latest patch. This is not urgent by
calendar — it's urgent by **sequencing**: cheaper to build the seam now,
while India is the only country, than to retrofit it once a second
country's rules are layered on top (Odoo's own docs warn about exactly this
retrofit risk for their own localization modules).

**Plan.**
1. Define a generic Tax Engine interface (rate lookup, rounding,
   inclusive/exclusive pricing, document-totals computation) that
   `core/services/billing.py`'s current logic can sit behind, without
   changing behavior for India.
2. Move India-specific rules (CGST/SGST/IGST split, RCM memo, HSN/SAC,
   TDS/TCS, the state-code table) behind that interface as the first and
   only pack.
3. **Do not** start a second country pack as part of this ticket — this is
   purely the seam, not new geography. A second pack is a separate,
   design-partner-gated bet per `ROUGH_COMPETITIVE_ROADMAP`'s long-term
   section.

**DoD.**
- [x] All GST-specific logic in `core/services/billing.py` sits behind a
      named interface, not inline.
- [x] Zero behavior change for any existing India tenant — this is a
      refactor with a regression suite, not a feature.
- [x] No second country pack exists yet; this ticket's DoD is the seam
      only.

---

## 3. Freeze list additions

Do not build any of these without a written charter, same rule as
`FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md` §0.3:

- **Supplier reliability score / rank** — see Decision 1 (§0) and COMP-007.
  Price-history rows are the resolved, shippable form; a score is not.
- **Automation-rule builder / workflow-rules-as-platform** — see Decision 4
  (§0). Odoo's Studio is the comparable, and it needs partner/technical
  support this segment mostly doesn't have.
- **Route optimization solver, dispatch stack, vehicle-capacity routing,
  pick-and-pack control tower, live delivery tracking** — see Decision 3
  (§0). Partner (OR-Tools/Mapbox/OSRM) if ever revisited; COMP-005 above
  captures the actual value (route profit) without this.
- **Proprietary GSP infrastructure** — the P0 track already partners with a
  named GSP; do not duplicate that as an in-house build.
- **Autonomous (non-confirm-gated) AI actions** — the existing AI
  assistant's re-auth-before-money-move design is a considered choice
  [§10], not a gap to close.
- **Generic chatbot / general NL-query breadth** — already GA and often
  free at Zoho (Zia), QuickBooks (Intuit Assist), and Xero (JAX);
  competing on breadth means competing against shipped incumbent features.
  "Must point at a document" stays the constraint.

---

## 4. Already built — enablement / positioning only

Not greenfield — confirmed by the 2026-09-22 codebase audit. Do not
estimate any of these as new construction if they resurface in a future
planning pass:

- **Batch + serial tracking on the same SKU, simultaneously** (COMP-011).
  Zoho Inventory can only do one or the other per item; BizBoard already
  does both. A real, checkable advantage — worth not losing track of, not
  worth re-scoping.
- **Confirm-gated AI assistant** (`insights/assistant.py`) — tool-grounded,
  refuses tax advice via explicit pattern match, requires re-authentication
  before any money-moving action, meters usage per company. This is what
  `ROUGH_COMPETITIVE_ROADMAP`'s long-term "assistant that runs an Attention
  action only after the user confirms" is describing — it already exists,
  gated behind a view permission and not positioned as a headline feature.
  The open work is adoption/positioning, not construction. [§10]
- **Today / Action Center substrate** — dashboard, attention-queue widget,
  collection-attention card, dedicated Insights hub. Already the most
  mature surface in the codebase per the audit. The near-term roadmap item
  is about making it the home screen and keeping it ranked by money, not
  building it from zero.
- **Cashflow forecast** (`insights/services.py forecast_cashflow`) — see §1.

---

## 5. Still open — named humans required

Adopted 2026-09-23 and no longer blocking: COMP-003 is built behind
`ENABLE_CUSTOMER_PORTAL` (default off); COMP-007 uses its own
`ENABLE_SUPPLIER_PRICE_HISTORY` (default off) on the suppliers page;
COMP-009's seam is in `core/services/tax_engine/` with no second country.

| Item | Why it blocks | Owner needed |
|---|---|---|
| GST Guard rule-set sign-off (COMP-006) | CA confirms the two buyer-GSTIN checks (format/checksum, and skip-vs-alert on `UNVERIFIED`) before `ENABLE_GST_GUARD` is turned on for a pilot. Does not block merging the default-off code. The flag stays off until this signature exists. | CA |
| P0 GSP owner table (COMP-010, cross-referenced not owned here) | P0 stays RED until filled — this plan doesn't change that, just notes the dependency | PM + Legal (per `WAVES_0_ABCD` §P0 track) |

---

## 6. Sequencing

```
Already-planned track (unchanged by this doc):
   P0 GSP (P0-01/B-01/B-02) ── A-06 WhatsApp ── A-07 dunning ── D-02 Tally
   ── B-03 IMS/2B                                          [WAVES_0_ABCD]

New-ticket track (this doc) — engineering complete 2026-09-23, flags off:
   COMP-002 Replenishment suggestion
   COMP-006 GST Guard          (flag stays off until CA signs §5)
   COMP-005 Route profit
   COMP-007 Supplier price history   (own flag, suppliers page)
   COMP-003 Customer portal          (15-minute reusable magic link)
   COMP-009 Tax-engine seam          (India pack + billing shim;
                                      no second country, no call-site move)
```

All six engineering slices are in the tree. Turning `ENABLE_GST_GUARD` on
for a pilot still waits on the CA signature in §5. P0 GSP stays on the
already-planned track and is not part of this build.

---

## 7. Effort (rough T-shirt sizes, solo)

Not a commitment — same caveat as every other estimate in this repo's
planning docs. Ranges, not dates.

| Ticket | Rough size | Why |
|---|---|---|
| COMP-002 Replenishment suggestion | 1–2 weeks | Two fields on `WarehouseReorderLevel` plus a suggested quantity on the existing low-stock row. Fixed 14-day window. |
| COMP-006 GST Guard | 1–1.5 weeks eng + CA review calendar | Two checks inside `build_gst_health()` (buyer GSTIN format and live status). HSN, place of supply, rate-vs-HSN, and duplicate numbers are already covered or unreachable. |
| COMP-005 Route profit | 2–3 weeks | Actual logistics cost is already captured. New work is the frozen taxable-profit snapshot and the route detail display. |
| COMP-007 Supplier price history | 1 week | Read-only view over existing PO/invoice data; deliberately no scoring logic. |
| COMP-003 Customer self-service portal | 3–5 weeks | New auth surface (magic link), new customer-facing frontend, reuse of existing document APIs. |
| COMP-009 Country-pack boundary | Seam + totals call sites done | Sales and purchase `compute_document_totals` go through `get_tax_engine(company)`. Other helpers stay on the `billing.py` shim. No second country. |

---

**Bottom line:** all six tickets are implemented on
`feature/sales-purchase-ux`, each behind its own `ENABLE_*` flag, default
off. Spec is the corrected plan in `COMPETITIVE_ROADMAP_PHASED_PLAN.md`.
The one remaining human gate is CA sign-off before `ENABLE_GST_GUARD` is
turned on for a pilot. P0 GSP (COMP-010) is still owned by the waves plan,
not this one.
