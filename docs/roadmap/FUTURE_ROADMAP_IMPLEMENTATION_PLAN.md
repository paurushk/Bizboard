# Bizboard — Future Roadmap Implementation Plan (Phases 1–7)

Consolidated from the canonical per-phase plans already authored in this repo
(`docs/phase1/` … `docs/phase7/`). §§3–9 below remain the historical
ticket-level compilation. They are **not** a from-zero build schedule.

**Operative mode (2026-08-21):** **gap audit against each Definition of Done,
then schedule only the deltas.** Most of Phases 1–7 already exist on
`wip/phase0` as MVP/preview slices (historical). **As of 2026-08-31 the
implementation branch is `main`.** Do not resume the sequential
Phase-1→7 *build* calendar.

**Arbitration rule:** **code + tests win for "what exists today"**;
**canonical phase docs win for "what's intended going forward."** A
code≠doc gap is a flagged decision, not an automatic override either way.
Adopted decisions from the 61-question review are in §0. Items still
needing a named human (PM/CA/ops) stay in §0.5.

**Pilot vs engineering:** continue code work under
`docs/pilot/PHASE1_ENGINEERING_PROCEED.md` (engineering-only waiver).
**Do not make any pilot-facing or commercial claim** until
`docs/pilot/GO_NO_GO.md` is signed. Human gates (CA packs, GSP/gateway/
WhatsApp KYC, staging tenant) proceed **fixtures-only** until owners are
named.

---

## Contents

0. [Resolved decisions & gap-closure sprint (2026-08-21)](#0-resolved-decisions--gap-closure-sprint-2026-08-21)
1. [Sequencing (operative vs historical)](#1-sequencing-operative-vs-historical)
2. [Calendar & effort](#2-calendar--effort)
3. [Phase 1 — Document completeness](#phase-1--document-completeness)
4. [Phase 2 — GST returns readiness](#phase-2--gst-returns-readiness)
5. [Phase 3 — Payments & cash ops](#phase-3--payments--cash-ops)
6. [Phase 4 — Inventory depth](#phase-4--inventory-depth)
7. [Phase 5 — Light accounting](#phase-5--light-accounting)
8. [Phase 6 — AI differentiator](#phase-6--ai-differentiator)
9. [Phase 7 — Ecosystem & scale](#phase-7--ecosystem--scale)

---

## 0. Resolved decisions & gap-closure sprint (2026-08-21)

Answers from the 61-question review, verified against code where marked.
`[ADOPTED]` = recorded as the going-forward rule. `[OPEN]` = still needs a
named human. Canonical phase docs should be patched to match `[ADOPTED]`
rows; until then this section wins on conflict.

### 0.1 Adopted product / architecture decisions

| # | Topic | Decision |
|---|---|---|
| 1 | What we are starting | Gap audit + delta tickets only. Not a from-spec rebuild of any phase. |
| 2 | Unsigned Phase 0 Go | Engineering continues under `PHASE1_ENGINEERING_PROCEED.md`. Commercial/pilot claims stay blocked on a signed `GO_NO_GO.md`. **`[OPEN]` until PM confirms this waiver still holds.** |
| 4 | Source of truth | Code+tests = current reality; canonical docs = intent; gaps are decisions. |
| 5 | Sales Return vs CN (D1) | **Keep auto-CN.** `ReturnService.complete_return` posts a system `SalesCreditNote` (`AUTO_RETURN:{id}`) for AR relief. Manual CN still must not move stock and must not double-count against the auto CN. Update D1 wording in the Phase 1 canonical doc. |
| 6 | Paid-invoice CN | **Keep default:** Complete blocked when per-invoice outstanding is 0; support script / H9 until Phase 3.1 refund+unwind exists. **`[OPEN]` PM/CA if a pilot needs a refund-then-CN path sooner.** |
| 7 | Delivery Challan stock (D6) | **Option A remains default.** `Company.stock_on_delivery_challan` defaults **False** (`accounts/models.py`). When True it is a demand-gated exception that posts SALE on challan Complete — not a reversal of D6. |
| 8 | SO reservation (D5) | **Already in.** `InventoryService.reserve_stock` / `release_reservation` + FEFO lot allocation. Strike "reserved stays 0" from Phase 1/4 docs. SO work builds on reservation. |
| 9 | Documents vs GL outstanding | **Provisionally accept (a):** when `accounting_enabled`, party outstanding is GL control net (AR `1200`, AP `2100`, advances `2300`/`1250`). Documents remain the posting source; GL is the read model for books-on tenants. **Mandatory safety net:** `AR_CONTROL_MISMATCH` / `AP_CONTROL_MISMATCH` Health must stay in CI (`test_sprint_a_accounting_p1.py`, `test_wave15d_books.py`). **Do not enable accounting for any pilot until this is explicitly signed** (see §0.5). Alternative (b) — always derive from documents — is the revert path if (a) is rejected. |
| 10 | Warehouse vs Branch | **No `Branch` model today.** Stock grain stays `(company, warehouse, product)`. If/when 7.2 starts: `Branch` is a filing/org dimension that *references* warehouses; do **not** re-key `StockBalance` onto branch. |
| 11 | Manufacturing / Payroll / CRM | **Freeze, do not delete.** Real apps behind `feature_flags()` (env + company JSON + SaaS entitlement AND-gate). Off by default. Matches Future framing. |
| 12 | Recurring + POS (7.3) | **Hardening/UAT only** (tap-count, notify-on-draft). Recurring is draft-only (matches D8). Cut greenfield ECO-300/301 estimates. |
| 14 | Purchase CN/DN linkage | Link preferred, standalone allowed. |
| 15 | Credit-limit race | **Already locked.** `SalesInvoice` Complete does `Customer.objects.select_for_update()` before the exposure check (`sales/services.py`). No new ticket. Re-run `tests/test_concurrency_races.py` in the gap-closure CI pass. |
| 16 | Debit Note cap (D14) | Cap = source invoice `grand_total`, independent of prior CNs. Stacked DNs may exceed post-CN net. Intended, not a bug. |
| 17 | Thermal 80mm | **Shipped.** `sales/pdf/thermal_receipt.py` + invoice/POS download. Freeze list is stale. |
| 18 | FY series | **Shipped when a GSTIN is resolved.** `DocumentNumberService` keys series by GSTIN + April FY; Complete stamps primary `CompanyGstin` and passes `on_date`. Legacy `INV-00001` remains only when the company has no GSTIN. |
| 19–21 | GSTR-1 rate-wise / identity amend / composition gating | **Already shipped.** GST-001/002/012 done. Composition blocks Regular GSTR-1/3B/9; CMP-08/GSTR-4 is composition-only. Whether any pilot files composition is `[OPEN]`. |
| 22 | Live NIC / GSP | Stay fail-closed (`BB-000624`). Procurement is a non-eng track. Not in the gap-closure sprint. |
| 23 | Tax-inclusive + RCM | Sales RCM Output-GST GL bug **fixed** (BB-000695). Cess-in-GL/IRP/inclusive/RCM is a **targeted follow-up check** (GAP-007). BUG-205 freight/packing GST CA sign-off is `[OPEN]`. |
| 24 | B2CL threshold | **Updated to ₹2,50,000** (`gst_returns.py`). CA confirm remains `[OPEN]`. |
| 25 | UQC seed | **Shipped.** `backfill_uqc` command + Unit serializer auto-map + Health `UQC_UNMAPPED`. |
| 26 | GSTN-shaped JSON | **Available as `format=gstn-json`**, dark in production unless `ENABLE_GSTN_JSON=1`. Disclaimer: not a portal upload. |
| 27 | Gateway | Razorpay only. Cashfree/PayU exist but disabled by default and fail-closed. No code change. |
| 28 | MDR fees | **Posted when books-on.** Receipt Dr bank (net) + Dr `5200` Bank Charges (fee) / Cr advances (gross). |
| 30 | Bank auto-match | `Company.auto_match_bank_exact` defaults **False**. Matches plan. |
| 31 | Account Aggregator mocks | **Fixed (GAP-001).** Mock FIU only when `use_mock_fiu` and env is allowlisted; empty rows no longer inject mocks. |
| 33 | Webhook vs manual receipt | `select_for_update` + concurrency tests exist. Re-run suite; do not rewrite. |
| 35 | In-transit transfers | Instant/atomic. No in-transit warehouse. Matches D11. |
| 36 | FIFO | Live, selectable, default WAVG. Re-run FIFO regression before CA-signing 4.2. Keep visible. |
| 37 | `batch_no` vs `BatchLot` | Dual-write by design: ledger on FK, line snapshot is string. |
| 38 | Expired stock | `block_expired_stock` defaults True; expiry alerts fire regardless. |
| 39 | Serials (4.4) | **Already fully wired.** Remaining: coverage + whether any pilot uses it. Not a build. |
| 40 | Price lists vs GST | `PriceListItem.unit_price` has no inclusive flag; `price_mode` is on the document. Small UI label polish (GAP-008). |
| 41 | Accounting demand gate | Feature set is built; `accounting_enabled` defaults False and is unset in demo/pilot seed. Gate applies to **enabling a specific pilot**, not further construction. Resolve #9 before flipping on. |
| 44 | Historical GL backfill | `backfill_accounting_postings.py` is idempotent (`unique` on source+purpose). Run as designed — skip what's posted. |
| 45 | Cost centers / fixed assets | **Already built** (`CostCenter`, `FixedAsset`, depreciation Celery task). Enablement/CA, not construction. |
| 49–50 | AI access / writes | `ai_features_enabled` defaults False; Owner-only next slice. Assistant writes = draft invoice + reminder only; money-moving types blocked. Already matches plan. |
| 54 | Multi-GSTIN (Phase 7 D6) | **Accept `CompanyGstin`** (many GSTINs on one Company, stamp-scoped GSTR). Reverses locked D6. Remaining 7.2 work = **one user, multiple companies** (accountant serving clients), not a second GSTIN model. **`[OPEN]` until PM explicitly confirms the D6 reversal.** |
| 55 | India Stack | GSTIN verify exists. PAN/UDYAM: format + Null + optional HTTP sandbox (`IDENTITY_SANDBOX_BASE_URL`). Live certified portal still `[OPEN]`. |
| 56 | ONDC / DigiLocker / eSign / Busy / Zoho | No build found. Stay spike-only. |
| 59 | Feature-flag authority | Live for a pilot = **plan entitlement AND company `feature_flags` JSON**. Env `ENABLE_*` / `VITE_ENABLE_*` is the platform kill switch underneath both. |
| 60 | Golden fixtures | CA supplies sample-month numbers; engineering builds the harness. Needs a named CA (`[OPEN]`). |

### 0.2 Gap-closure sprint (operative engineering queue)

Do these **before** any net-new work from §§3–9. Order is risk, not phase number.

| ID | Title | Status 2026-08-21 | Notes |
|---|---|---|---|
| **GAP-001** | AA ingest mock allowlist | **Shipped** | Mock only when `use_mock_fiu` and env is `dev`/`test`/`local`. Empty rows no longer inject mocks. |
| **GAP-002** | Dashboard AR/AP onto LedgerService | **Shipped** | `ReportService._company_receivables` / `_company_payables` call `LedgerService.company_receivables` / `company_payables`. |
| **GAP-003** | UQC backfill + Health | **Shipped** | `manage.py backfill_uqc`; Unit serializer auto-maps; GST Health `UQC_UNMAPPED` on units and lines. |
| **GAP-004** | B2CL threshold ₹2,50,000 | **Shipped (CA confirm still `[OPEN]`)** | `B2CL_THRESHOLD = 250000`. Tests updated. |
| **GAP-005** | Payment Link cancel with invoice | **Shipped** | Open links cancelled on invoice cancel; webhook capture refused. |
| **GAP-006** | AR/AP control Health CI | **Confirmed** | Existing `test_control_balances_flags_untagged_ar` remains the #9 safety net. |
| **GAP-007** | Cess in GL / IRP / inclusive / RCM | **Confirmed** | GL `2270`, IRP `CesRt`/`CesAmt`, inclusive extract includes cess (BB-000611). Regression tests added. |
| **GAP-008** | Price-list tax-mode label | **Shipped** | Price lists page discloses rate vs document `price_mode`. |
| **GAP-009** | BS inventory valuation overlay | **Shipped** | Balance sheet returns `inventory_gl` / `inventory_valuation` / `inventory_note`; UI shows the overlay. GL equation unchanged. |
| **GAP-010** | Postgres concurrency + FIFO regression | **Pending local 3.12 venv** | No product change. Re-run `tests/test_concurrency_races.py` when Python 3.12 is available. |

**Sprint total ~29 pts ≈ 1.5–2.5 weeks solo**, plus human waits on GAP-004 and CoA sign-off.

### 0.3 Freeze list (do not build without a written charter)

Genuinely unbuilt or must stay dark:

- PAN / UDYAM **certified live portal** (format + Null + HTTP sandbox shipped; do not stamp VALID in prod/staging)
- ONDC, DigiLocker, Aadhaar eSign (spikes only)
- Busy / Zoho adapters
- Full GSTR-9 **portal upload** (tables 4–8 are books/2B worksheets)
- GSTR-2A / 2B **auto-claim** (file ingest + match shipped; human CLAIMABLE board is Wave B-03 in the waves plan — do not auto-claim)
- Second live gateway (Cashfree / PayU stay disabled)
- Live e-Invoice / e-Way **NIC-direct** (`BB-000624`, fail-closed). **2026-08-30:** live **GSP** IRN + GSTR-1/3B GSP upload is the P0 track in `docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md` — still fail-closed until a named GSP and secrets exist; not a from-scratch NIC stack.
- Manufacturing / Payroll / CRM — freeze enablement; do not extend
- Account Aggregator **live bank feed** (HTTP FIU fail-closed without `FIU_BASE_URL`; keep flag off)

### 0.4 Already built — enablement / hardening only

Do **not** estimate as greenfield: cost centers, fixed assets, serial tracking,
WhatsApp Cloud API (templates + `wa.me` fallback), Tally CSV/XLSX/XML,
SO stock reservation, POS, recurring invoices (draft-only), `CompanyGstin`
multi-GSTIN, rate-wise GSTR-1/CDNR, identity amend, composition gating,
Razorpay Payment Links, warehouses/batch/WAVG-FIFO, books stack behind
`accounting_enabled`.

### 0.5 Still open — named humans required

| Item | Why it blocks | Owner needed |
|---|---|---|
| Signed `GO_NO_GO.md` | Any commercial/pilot claim | PM, Eng, QA, CA, Ops |
| Confirm engineering waiver still holds (#2) | Whether gap-closure may proceed | PM |
| Sign Phase 5 #9 (GL-as-truth when books on) | Accounting enablement | PM + CA |
| Sign Phase 7 D6 reversal (`CompanyGstin`) | Stops a future rewrite | PM |
| CA CoA codes (1200 AR, 2100 AP, 2210/2220/2230 output, 1310/1320/1330 input, 2300/1250 advances, 1600/1650 FA, 2261–2266 statutory, 2240–2280 RCM, 5300/5600/5700/5500) | Health + GL-outstanding depend on these | CA |
| CA sample CN/DN PDFs; B2CL ₹2.5L; BUG-205 freight GST | GAP-004 + Phase 1 human DoD | CA |
| GSP / gateway / WhatsApp KYC; Meta template approval; DPDP opt-in basis | Live P0 / 3.1 / 7.1. **2026-08-30:** name owners in `WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md` P0 table by 2026-09-13 or P0 is RED | PM + legal |
| Staging tenant + CA-PDF environment | Golden fixtures | Ops |
| Bank CSV sample files (HDFC/ICICI/SBI placeholder) | 3.2 presets | Support |
| LLM monthly cap and who pays | 6.4 budget | PM/finance |
| Composition-dealer pilots? | Whether 2.5 CMP calendar matters | Sales |
| Copy pass (billing-first vs under-selling built modules) | #46 / #51 | Product |

---

## 1. Sequencing (operative vs historical)

### Operative (now)

```
Confirm PM waiver (#2) + fixtures-only human gates
   │
   ▼
Gap-closure sprint (GAP-001 … GAP-010)
   │  especially GAP-001 (AA fail-open) and GAP-002 (dashboard outstanding)
   ▼
Human sign-offs: CoA, #9 GL-as-truth, #54 CompanyGstin, B2CL
   │
   ▼
Enablement only, demand-gated per flag
   (books, FIFO CA pack, WABA, POS UAT, serials)
   │
   ▼
Genuinely unbuilt (charter required): PAN/UDYAM **certified** portal, 2A/2B **auto-claim**, live NIC-direct, Busy/Zoho, ONDC.

**Cursor/Cloud ticket plans:** Waves 0–D + P0 → `docs/roadmap/WAVES_0_ABCD_CURSOR_IMPLEMENTATION_PLAN.md`. Post-pilot Waves E–L → `docs/roadmap/WAVES_E_TO_L_CURSOR_IMPLEMENTATION_PLAN.md`.
```

Historical Phase-0→7 start gates in the canonical docs remain valid as
**enablement** gates (do not turn on books, live NIC, or WABA ahead of
their own DoD). They are no longer a *construction* sequence.

**Cross-cutting:** Phase 4 has no hard dependency on Phase 3. At solo
headcount the remaining *code* is the gap-closure list, not 3.0 then 4.0.

---

## 2. Calendar & effort

### Operative

| Slice | Pts | Calendar (solo) |
|---|---:|---|
| Gap-closure sprint (GAP-001–010) | ~29 | **1.5–2.5 weeks** (+ CA wait on GAP-004 / CoA) |
| Enablement / UAT of already-built modules | n/a | Demand-gated; not a build calendar |
| Frozen unbuilt (PAN/UDYAM, 2A/2B, live NIC, …) | not scheduled | Charter first |

### Historical greenfield rollup (archival — do not use for scheduling)

All figures are **points ≈ solo senior full-stack hours ÷ 2**. These assumed
from-zero waves that are now largely shipped; keep them only to read the
canonical phase docs.

| Phase | Core/high-value slice (historical) | Full phase (historical) |
|---|---|---|
| 1 — Documents | Core: ~70 pts ≈ 6–7 wks | Core + 1.5: ~98 pts ≈ 8–10 wks |
| 2 — GST returns | 2.0+2.1: ~83–102 pts ≈ 8–9 wks | Full: ~145–180 pts ≈ 14–18 wks |
| 3 — Payments | 3.0+3.1: ~68–84 pts ≈ 7–9 wks | Full: ~124–156 pts ≈ 14–18 wks |
| 4 — Inventory | 4.0+4.1: ~78–96 pts ≈ 8–10 wks | Full: ~152–190 pts ≈ 16–22 wks |
| 5 — Accounting | 5.0+5.2 thin: ~94–118 pts ≈ 10–14 wks | Core 5.0–5.3: ~122–154 pts ≈ 14–20 wks |
| 6 — AI | 6.0+6.1: ~40–50 pts ≈ 6–8 wks | Full: ~150 pts ≈ 16–22 wks |
| 7 — Ecosystem | 7.0+7.1+7.4: ~13–17 wks | 7.0–7.4: ~26–33 wks |
| **Historical total (do not schedule)** | **~58–74 weeks** | **~108–143 weeks** |

---

## Phase 1 — Document completeness

*Canonical: [`docs/phase1/PHASE_1_DOCUMENT_COMPLETENESS.md`](../phase1/PHASE_1_DOCUMENT_COMPLETENESS.md)*

**Status 2026-08-21:** Core + 1.5 are **in code**. Remaining: GAP-002
(dashboard outstanding drift), CA CN/DN PDF sign-off, paid-invoice CN
policy `[OPEN]`. D1 = auto-CN on return; D5 reservation is in; D6 challan
stock flag defaults False. Credit-limit Complete already
`select_for_update`s the customer. Thermal and FY series stay out.

Closes the correction hole Phase 0 immutability + the H9-A pilot escape hatch
leave behind: a completed, paid invoice has no proper Credit Note path.

### Start gate

| Prerequisite | Source |
|---|---|
| Phase 0 Go signed | `docs/pilot/GO_NO_GO.md` |
| Phase 0 Must-DoD Done or PM-waived | `docs/pilot/PHASE_0_DOD.md` |
| H9-A correction path live for pilot | `docs/pilot/H9_CORRECTION_PATH.md` |

**Do not start Phase 1 coding before Phase 0 Go.** Building seven new document
types on unresolved money/tenancy Criticals is the wrong risk order.

### Locked decisions (key)

> Amended by §0 (2026-08-21): auto-CN on return; SO reservation is live;
> challan stock flag defaults False; credit-limit Complete already row-locks
> the customer. Historical bullets below are the original compilation.

- **Sales Credit Note** = value correction against a completed invoice, **no stock movement**, distinct from Sales Return (qty + stock); source invoice is never mutated. **§0 D1:** a Sales Return also posts an internal system CN (`AUTO_RETURN:{id}`) for AR relief; a *manual* CN must not double-count against it.
- **Sales Debit Note** = under-charge / additional taxable value against a completed invoice; issued GST artifact (PDF + place-of-supply).
- CN Complete is blocked once `cn.grand_total > sales_invoice_outstanding(invoice)` — a fully paid invoice blocks new CNs by design (support script: H9 amend or offline dispute tracking; no fake negative outstanding).
- **Credit limit:** `0` = no limit; else block Complete when `outstanding − unallocated advances + draft total > limit`. Concurrent-Complete race is **closed** via `Customer.select_for_update()` (not an accepted risk).
- Purchase CN/DN ship as lighter **recorded** documents (no CA-grade generated PDF requirement).
- Sales Order / Purchase Order / Delivery Challan are **Phase 1.5**, not core — Delivery Challan default is non-stock (Option A). `stock_on_delivery_challan` (default False) is the demand-gated exception. **SO reservation is already implemented.**
- FY-based series reset (`INV/25-26/0001`) is **deferred** — retrofitting later risks renumbering.

### Scope by wave

- **W0 — Foundations:** number prefixes registered in the same PR as each new model (`DEFAULT_PREFIXES` + `_max_existing_seq` together); reuse Phase 0's shared line editor rather than re-estimating it.
- **W1 — Money correctness:** the **shared outstanding helper** (`sales_invoice_outstanding`, `purchase_invoice_outstanding`, `customer_exposure_for_credit_limit`, supplier twins) rewired into every consumer — ledgers, payment allocation caps, statements, reporting. This is the highest-risk ticket in the phase: outstanding logic is currently reimplemented in ~15 places. Credit limit gate and multi-line returns polish land alongside it.
- **W2 — Credit/Debit Notes, sequenced (not four-at-once):** Sales Credit Note end-to-end → Sales Debit Note (clone, opposite polarity) → Purchase CN/DN as recorded documents → registers/statements/CA sample pack.
- **Phase 1.5 (after core exit):** Sales Order → Invoice, Purchase Order → Purchase, Delivery Challan (non-stock), optional thermal 80mm printing.

### Work breakdown

| ID | Title | Wave | Pts |
|---|---|---|---:|
| DOC-103 | Multi-line sales + purchase returns UI | W1 | 3 |
| DOC-104 | Credit limit Complete gate (exposure − advances) + FE warn | W1 | 5 |
| DOC-204 | **Shared outstanding helper** + rewire ledgers, payment caps, statements, reporting | W0–W2 | **13** |
| DOC-201 | Sales Credit Note model + migration + numbering | W2 | 5 |
| DOC-202 | Sales CN service + API + tests (cap = invoice outstanding) | W2 | 8 |
| DOC-205 | Sales CN PDF + Celery pipeline | W2 | 5 |
| DOC-206 | Sales CN frontend | W2 | 5 |
| DOC-207 | Sales Debit Note (model → API → PDF → FE) | W2 | 8 |
| DOC-203 | Purchase CN/DN recorded models + API + light FE | W2 | 8 |
| DOC-208 | Sales/purchase register + tax summary include CN/DN | W2 | 5 |
| DOC-209 | Statement rows for CN/DN + E2E golden path + CA sample pack | W2–exit | 5 |
| **Core subtotal** | | | **~70 pts ≈ 6–7 wks** |
| DOC-301/302 | Sales Order + convert + FE (full money-field copy) | 1.5 | 10 |
| DOC-401/402 | Purchase Order + convert + FE | 1.5 | 10 |
| DOC-403/404 | Delivery Challan (Option A) + FE + PDF | 1.5 | 8 |
| **1.5 subtotal** | | | **~28 pts ≈ 2–3 wks** |
| DOC-501 *(optional, excluded from totals)* | Thermal 80mm invoice PDF + FE | — | 5 |

### Testing & Definition of Done

Unit/integration matrix must cover: invoice ± return ± CN ± DN ± allocated ±
unallocated receipt combinations; credit limit at 0/under/equal/over with a
customer carrying a large unallocated advance; SO/PO convert money-field
parity. E2E golden path green.

Core exit requires: shared outstanding helper live everywhere money is
derived; Sales CN/DN create/complete/cancel with no stock movement and no
source-invoice mutation; CN Complete respects per-invoice outstanding;
purchase CN/DN reflected in supplier outstanding; CN/DN visible in registers
and statements; credit limit uses advance-aware exposure; multi-line returns
in one document; CA sign-off on sample CN/DN PDFs (human gate, tracked
separately).

### Key risks

Starting before Phase 0 Go; allocation caps ignoring CN before DOC-204 lands;
reports/CA totals diverging from ledger truth without the single helper;
"paid then dispute" support load; credit-limit race under concurrent
Completes (documented, not silently fixed); four CA-grade document types
attempted in two weeks instead of sequenced.

---

## Phase 2 — GST returns readiness

*Canonical: [`docs/phase2/PHASE_2_GST_RETURNS_READINESS.md`](../phase2/PHASE_2_GST_RETURNS_READINESS.md)*

**Status 2026-08-21:** Rate-wise GSTR-1/CDNR, identity amend, composition
gating, and the RCM Output-GST GL fix are **shipped**. Remaining engineering:
GAP-003 (UQC backfill), GAP-004 (B2CL ₹2.5L after CA), GAP-007 (cess check).
Live NIC stays fail-closed (`BB-000624`). GSTN JSON stays off. Full GSTR-9
engine and 2A/2B stay frozen (worksheet aid exists).

Closes the GST **reporting & statutory artifact** path, and the **identity
correction** gap (wrong GSTIN / place of supply) that CN/DN cannot fix.

### Start gate

| Prerequisite | Source |
|---|---|
| Phase 0 Go / money Criticals closed | `docs/pilot/GO_NO_GO.md` |
| Phase 1 core DoD (CN/DN, outstanding helper, credit limit) | Phase 1 §11 |
| Sales CN/DN complete + CDNR present in offline GSTR-1 | `backend/reporting/gst_returns.py` |
| CA sign-off on Tax Invoice + Sales CN/DN sample PDFs | Human gate |

**Do not start filing polish before CN/DN ledger + GSTR CDNR reconcile** —
returns without notes produce wrong CA packs and false confidence.

### Locked decisions (key)

- Phase 2 ships **export aids + readiness**, not one-click GSTN filing. Offline BizBoard JSON/XLSX is the default; GSTN-compatible JSON is a flagged, off-in-prod sub-deliverable requiring CA-signed golden fixtures.
- **GSTR-1 B2B / B2CL / CDNR / CDNUR must be rate-wise** (one row per invoice × tax rate from line aggregates) — the current header-level builder is scaffold, not done, and must be rewritten before CA sign-off of exports.
- **Filing-line snapshots:** every GST-relevant line freezes `hsn_code` + `uqc_code` at Complete; return builders never resolve live Product HSN, so editing a product later can't rewrite already-filed months.
- Reverse charge tax lives in **memo-only fields** (`rcm_taxable/cgst/sgst/igst`) — never folded into `grand_total`/`cgst_total` etc., which feed payables, allocation caps, and registers.
- Tax-inclusive pricing is a **price mode**, not a second tax engine: extract tax once from the discounted line gross, then feed exclusive amounts into the existing `compute_document_totals`.
- **Identity correction path (required):** an Owner/Admin allowlisted amend action for filing-snapshot party GSTIN and place-of-supply on completed invoices, audited, with period-dirty flagging — CN/DN cannot fix a wrong CTIN/POS and "use CN/DN" is not an acceptable answer.
- GSP/IRP procurement (vendor KYC, contracts, sandbox credentials) is a **parallel non-engineering track starting Day 1 of Wave 2.0**, not something that waits for Wave 2.2.
- Composition dealers: Regular GSTR-1/3B packs are hidden/disabled; CMP-08/GSTR-4 is explicitly Phase 2.5, not this phase.

### Scope by wave

- **2.0 — Filing integrity + returns + Health:** line HSN/UQC snapshots, `GstReturnPeriod` + hashed `GstReturnSnapshot`, identity-amend path, rate-wise GSTR-1/CDNR/CDNUR rewrite + HSN Table 12, GSTR-3B purchase CN/DN netting, GST Health Dashboard with a full alert catalog, CA pack export, composition gating, GSP procurement track.
- **2.1 — Tax modes + GSTIN verify:** reverse charge memo fields, tax-inclusive mode, live GSTIN verification with a cacheable provider, RCM feeding 3B section 3.1(d).
- **2.2 — E-Invoice (IRN + QR):** pluggable IRP/GSP adapter, submit/cancel IRN, QR on PDF, compliance panel; assumes sandbox credentials already in hand from the 2.0 parallel track.
- **2.3 — E-Way Bill:** NIC/GSP adapter for invoice + challan, transporter fields, expiry Health alerts.
- **2.4 — GSTR-9 annual aid:** FY aggregator from hashed monthly snapshots, XLSX worksheets, CA disclaimer.
- **2.5 (explicitly later, not in this calendar):** GSTR-2A/2B auto-reconcile, CMP-08/GSTR-4, formal B2BA/CDNRA tables (only if the identity-amend allowlist proves insufficient), multi-GSTIN filing.

### Work breakdown

**Wave 2.0 — Integrity + Returns + Health (~55–68 pts)**

| ID | Title | Pts |
|---|---|---:|
| GST-000 | Line filing snapshots: `hsn_code` + `uqc_code` on CN/DN (invoice lines already have HSN) | 5 |
| GST-000b | UQC master: seed GSTN UQC list, `Unit.uqc_code`, migration mapping | 5 |
| GST-011 | `GstReturnPeriod`: OPEN/SOFT_CLOSED/CLOSED + permissions | 5 |
| GST-012 | Identity amend (party GSTIN + POS) + audit + period-dirty | 5 |
| GST-001 | Rewrite GSTR-1 B2B/B2CL rate-wise + invoice-value mismatch handling | 8 |
| GST-002 | Rewrite CDNR rate-wise + CDNUR + Docs detail + NIL/exempt + HSN Table 12 (qty+UQC) | 8 |
| GST-003 | GSTR-3B purchase CN/DN netting | 3 |
| GST-004 | Return data-quality / issues strip | 3 |
| GST-005 | `GstReturnSnapshot` persist: payload + content hash + builder version | 5 |
| GST-006 | GST Health service + API + full alert catalog | **13** |
| GST-007 | GST Health FE dashboard | 5 |
| GST-008 | CA pack zip export | 3 |
| GST-009 | Composition gating for Regular GSTR UI | 2 |
| GST-010 | CA fixture review + golden multi-rate samples | 3 |
| GST-013 | Company `aato_turnover` field + settings UX | 2 |
| GST-014 | GSP procurement track (PM, 0 eng pts, calendar-parallel) | 0 |

**Wave 2.1 — Modes + GSTIN (~28–34 pts)**

| ID | Title | Pts |
|---|---|---:|
| GST-101 | Schema: `is_reverse_charge`, `rcm_*` memo fields, `price_mode`, verification fields | 5 |
| GST-102 | Tax-inclusive derivation (discounted line gross) + BEFORE_TAX allocation + parity fixture | 8 |
| GST-103 | FE tax-inclusive toggle | 5 |
| GST-104 | RCM purchase Complete rules; payable uses `grand_total` only | 5 |
| GST-105 | GSTR-3B 3.1(d) from `rcm_*` memo | 3 |
| GST-106 | GSTIN provider + verify endpoints + cache | 5 |
| GST-107 | FE verify badges | 3 |
| GST-108 | Health alerts for verification + RCM | 2 |

**Wave 2.2 — E-Invoice (~30–38 pts)**

| ID | Title | Pts |
|---|---|---:|
| GST-201 | Encrypted GSP credentials model + settings UI | 5 |
| GST-202 | IRP adapter interface + sandbox fake + one provider | 8 |
| GST-203 | `submit-einvoice` / `cancel-einvoice` actions + tests | 5 |
| GST-204 | PDF QR render + compliance panel FE | 5 |
| GST-205 | Readiness gates + Health e-Invoice alerts | 3 |
| GST-206 | CN/DN e-Invoice (optional 2.2b) | 8 |

**Wave 2.3 — E-Way (~22–28 pts)**

| ID | Title | Pts |
|---|---|---:|
| GST-301 | Transporter/vehicle/distance fields | 3 |
| GST-302 | EWB adapter + submit/cancel | 8 |
| GST-303 | FE prepare/submit on invoice + challan | 5 |
| GST-304 | Threshold warnings + Health alerts | 3 |
| GST-305 | Optional post-IRN e-Way generate | 3 |

**Wave 2.4 — GSTR-9 (~16–20 pts)**

| ID | Title | Pts |
|---|---|---:|
| GST-401 | FY aggregator from snapshots | 8 |
| GST-402 | GSTR-9 XLSX worksheets + API | 5 |
| GST-403 | FE annual page + disclaimer | 3 |

### Testing & Definition of Done

**Mandatory reconciliation invariant:** per company × period,
`sum(B2B+B2CL+B2CS taxable) − sum(CDNR+CDNUR taxable) == sales register
taxable for the period` — this is the test that catches header-level B2B
rows and silent drops. Golden CA fixtures must include multi-rate invoices.
Re-export with unchanged documents must reproduce the same `content_hash`.

2.0 exit requires: rate-wise GSTR-1/CDNR/CDNUR green on the multi-rate
fixture; HSN Table 12 with qty+UQC; invoice-value mismatch handled and
excluded from GSTN-shaped sections; reconciliation invariant green;
GstReturnPeriod + snapshot hashing live; identity-amend path with audit;
GST Health dashboard with the full alert catalog; composition gating; CA pack
zip; GSP procurement track started. 2.1–2.4 exits are per-wave (see canonical
doc §11) — none require one-click GSTN filing, GSTR-2A/2B auto-reconcile, or
CMP-08/GSTR-4.

### Key risks

Treating the current GSTR-1 scaffold as done (it isn't — rewrite required);
a product's HSN edit silently rewriting already-filed months (prevented by
line snapshots); claiming portal-ready JSON before CA fixtures pass; RCM
breaking the payable invariant if it isn't kept memo-only; GSP vendor delay
starving Wave 2.2 if procurement doesn't start on Day 1 of Wave 2.0.

---

## Phase 3 — Payments & cash ops

*Canonical: [`docs/phase3/PHASE_3_PAYMENTS_CASH_OPS.md`](../phase3/PHASE_3_PAYMENTS_CASH_OPS.md)*

**Status 2026-08-21:** Razorpay + Payment Links + instrument/UPI path and
bank import models are **in code**. Cashfree/PayU stay disabled. Auto-match
defaults False. Remaining: GAP-001 (AA mock fail-open — **do this first**),
GAP-005 (link invalidate on invoice cancel), GAP-010 (re-run concurrency
suite). Bank CSV presets still need named sample files `[OPEN]`. Second
gateway and live AA feed stay frozen.

Moves collection from record-only receipts to Payment Links, gateway
settlement, bank statement auto-match, and an actual cash book — the next
founder-ROI item after GST filing aids, and a required input for Phase 5
bank reconciliation.

### Start gate

| Prerequisite | Source | Why |
|---|---|---|
| Phase 0 Go / money Criticals closed | `docs/pilot/GO_NO_GO.md` | Gateway money on broken tenants multiplies support |
| Phase 1 outstanding helper + CN/DN netting | Phase 1 | Auto-allocation from gateway must hit correct outstanding |
| Receipt/payment/allocation race locks green | `PaymentService` | Concurrent webhooks + manual allocate |
| Gateway vendor shortlist + KYC started (PM) | Non-eng track | Must not wait for Day 1 of the wave |

**Do not start live gateway settlement before allocation + outstanding math
is green.** A Payment Link that marks an invoice paid while outstanding math
is wrong is worse than record-only UPI.

### Locked decisions (key)

- Gateway / Payment Links always **create normal receipts** and go through `PaymentService` — never a second "paid" flag on invoices that bypasses `PaymentAllocation`. One outstanding formula, forever.
- Gateway adapter is **pluggable** (`PaymentGatewayAdapter` Protocol); ship one provider first (default Razorpay), second provider later; sandbox fake for CI.
- **Webhook is the source of settlement truth**, verified by signature, idempotent on `(company, provider, provider_payment_id)`. Manual "mark paid" stays available for cash/UPI collected offline.
- Stronger UPI = amount-locked UPI intent/QR with `txn_note` = invoice/receipt number — a static company UPI string alone is insufficient.
- Bank statement import clones the existing Import Service UX (Upload → Validate → Preview → Commit); auto-match is **suggestions first**, exact-amount + unique-reference match only when explicitly enabled — never silent force-match of ambiguous lines.
- Cashflow **tracking** (actual cash/bank movement, this phase) is explicitly distinct from Phase 6 cashflow **prediction** — the UI must label them differently.
- Refunds unwind the allocation, then post a gateway refund — no silent receipt delete (allocations stay PROTECT).
- No multi-currency, no supplier payouts via gateway, no second gateway provider or live bank-feed (Account Aggregator) in this phase's core scope.

### Scope by wave

- **3.0 — UPI + instruments hardening:** `BankAccount` master, instrument fields on receipts (UTR, bank account, card last4), amount-locked UPI QR builder, duplicate-UTR warning, missing-UPI Health-style alerts.
- **3.1 — Payment Links + gateway:** encrypted gateway credentials, `PaymentLink` model + public pay page, adapter (create link / status / refund stub), idempotent webhook → receipt + auto-allocate, invoice-detail link status panel.
- **3.2 — Bank statement import + auto reconciliation:** `BankStatement`/`BankStatementLine`, CSV presets for major banks + generic, match-scoring service producing suggestions, confirm-match or create-receipt-from-line wizard, unmatched aging.
- **3.3 — Cashflow tracking report:** cash/bank book by account and mode, inflow/outflow/net, XLSX export, optional dashboard cash-position tile.
- **3.4 (explicitly later):** second gateway provider, UPI Autopay/mandates, supplier payouts, live Account Aggregator bank feed. GSTR-2A/2B purchase reconcile lives in Phase 2.5, not here.

### Work breakdown

**Wave 3.0 — UPI + instruments (~28–34 pts)**

| ID | Title | Pts |
|---|---|---:|
| PAY-000 | `BankAccount` model + API + settings FE | 5 |
| PAY-001 | Receipt/payment instrument fields + UTR normalize/dedupe warn | 5 |
| PAY-002 | Amount-locked UPI QR builder + PDF/share integration | 5 |
| PAY-003 | Invoice detail "Pay via UPI" panel | 3 |
| PAY-004 | `require_payment_reference` company setting + FE | 2 |
| PAY-005 | Alerts: missing UPI / duplicate UTR | 3 |
| PAY-006 | Tests: QR payload, UTR uniqueness, migration | 5 |

**Wave 3.1 — Gateway + Links (~40–50 pts)**

| ID | Title | Pts |
|---|---|---:|
| PAY-100 | Gateway credentials encrypt + settings UI | 5 |
| PAY-101 | Adapter Protocol + sandbox fake + one provider | 8 |
| PAY-102 | `PaymentLink` model + create/cancel/list API | 5 |
| PAY-103 | Public pay page (mobile-first, branded) | 8 |
| PAY-104 | Webhook idempotent finalize → receipt + allocate | 8 |
| PAY-105 | Share link via WhatsApp/Email | 3 |
| PAY-106 | Invoice FE link panel + status | 5 |
| PAY-107 | Refund path stub (unwind allocation + provider refund) | 5 |
| PAY-108 | Security: rate limit + webhook replay tests | 3 |

**Wave 3.2 — Bank import + recon (~38–48 pts)**

| ID | Title | Pts |
|---|---|---:|
| PAY-200 | Statement models + upload preview/commit | 8 |
| PAY-201 | Bank CSV presets (3 banks + generic) | 5 |
| PAY-202 | MatchService scoring + suggestions API | 8 |
| PAY-203 | Confirm match + create-receipt-from-line wizard | 8 |
| PAY-204 | Recon FE queue + unmatched aging | 8 |
| PAY-205 | Auto-match exact-only policy flag + audit | 3 |
| PAY-206 | Tests: golden CSV fixtures + ambiguous non-auto | 5 |

**Wave 3.3 — Cashflow tracking (~18–24 pts)**

| ID | Title | Pts |
|---|---|---:|
| PAY-300 | Cash book report query (by account/mode) | 8 |
| PAY-301 | FE cash book + XLSX export | 5 |
| PAY-302 | Dashboard cash-position tile (optional) | 3 |
| PAY-303 | Clarify Insights forecast disclaimer vs actuals | 2 |

### Testing & Definition of Done

**Mandatory invariant:** after gateway capture, invoice outstanding equals
pre-pay outstanding minus captured amount, within paise rounding. Security
tests must cover HMAC failure, missing-signature webhooks, and public-token
enumeration.

3.0 exit: ≥1 bank account per company; amount-locked UPI QR live; UTR capture
+ duplicate warning. 3.1 exit: sandbox link → webhook → receipt + allocation
works end to end; public pay page works on mobile; credentials encrypted;
manual record-only path still works with gateway off. 3.2 exit: CSV import
for ≥1 preset + generic; suggestion queue; ambiguous lines never auto-match.
3.3 exit: cash book by account/date with export; UI distinguishes actuals
from Phase 6 forecast.

### Key risks

Double receipt from webhook racing manual entry (idempotency key mitigates);
ambiguous bank lines auto-applying to the wrong invoice (exact-only auto by
default); MDR/gateway-fee confusion in ledgers until Phase 5 posts it
properly; vendor KYC delay — mitigated by shipping 3.0 without the gateway
and using a sandbox adapter for CI.

---

## Phase 4 — Inventory depth

*Canonical: [`docs/phase4/PHASE_4_INVENTORY_DEPTH.md`](../phase4/PHASE_4_INVENTORY_DEPTH.md)*

**Status 2026-08-21:** Warehouse, transfer (instant), batch/FEFO, WAVG+FIFO,
price lists, and serials are **shipped**. Reservation is in (contradicts
historical D5). No `Branch` model — stock stays `(company, warehouse,
product)`. Remaining: GAP-008 (price-list tax-mode label), GAP-009 (BS
inventory source), GAP-010 (FIFO regression). Demand gate is retroactive —
treat as delivered-awaiting-pilot-validation, not a from-zero build.

Unblocks distributor/wholesaler pilots that need multiple stock locations or
batch/expiry tracking, and gives Phase 5 an honest valuation input for the
Balance Sheet.

### Start gate

| Prerequisite | Source | Why |
|---|---|---|
| Phase 0 Go | `docs/pilot/GO_NO_GO.md` | Multi-location on broken stock math multiplies ghosts |
| Complete/Cancel/Return movement matrix green | `InventoryService` | Transfers must reuse the same posting path |
| Append-only movement invariant tests | `StockMovement` guards | Batch/serial layers must not allow update/delete |
| Demand signal | ≥1 pilot needs multi-location or batch/expiry | Avoid building warehouse depth for retail-only shops |

**Do not start FIFO/serial before the warehouse + batch quantity ledger is
correct** — valuation on wrong quantity is expensive fiction.

### Locked decisions (key)

- Every tenant gets **one default warehouse** via data migration; documents that move stock (sales, purchase, adjustment) gain a required `warehouse`, defaulted in the UI.
- Stock transfer is a **first-class document** (`StockTransfer`, DRAFT → COMPLETED → CANCELLED) posting `TRANSFER_OUT` + `TRANSFER_IN` — not a pair of ad-hoc adjustments. Transfers are **instant** on Complete in the MVP (no in-transit warehouse) unless a pilot forces otherwise.
- Batch/lot tracking is **optional per product** (`Product.track_batch`); when on, issue/receipt requires a batch and the balance grain includes it. Products without the flag keep warehouse-only grain.
- Expired-stock sale is **blocked by default** (`block_expired_stock=true`), configurable.
- Default valuation method is **Weighted Average**; FIFO is available per company. A method change is **prospective only** — it never rewrites historical reports.
- Valuation is a **report/service**, never a second mutable stock table, mirroring the ledger-derivation philosophy used everywhere else.
- Serial tracking is **Phase 4.4, explicitly demand-gated** — chartered per vertical (electronics/appliances), not built for grocery-style pilots.
- Manufacturing/BOM stays out of Phase 4 entirely (Phase 7 Future).

### Scope by wave

- **4.0 — Multi-warehouse + stock transfer:** `Warehouse` model + default backfill, `StockBalance` migrated to `(company, warehouse, product)` uniqueness, warehouse threaded through every Complete path, `StockTransfer` document + FE, per-warehouse low-stock filters.
- **4.1 — Batch/lot ledger + expiry alerts:** `Product.track_batch` + `BatchLot`, movement/balance grain gains optional batch FK, purchase Complete creates/updates lots, sales Complete gets a FEFO (earliest-expiry-first) suggestion, expiry alerts API + page.
- **4.2 — Valuation (WAVG / FIFO):** `Company.inventory_valuation_method`, `InventoryValuationService` for stock value as-of and per-sale COGS, FIFO layers (batch-aware when present), CA-reviewed golden fixtures.
- **4.3 — Multi-price lists:** `PriceList`/`PriceListItem`, customer default list, billing editors fill from list with manual override.
- **4.4 — Serial tracking (demand-gated):** `SerialNumber` state machine (AVAILABLE → SOLD → RETURNED → SCRAPPED), capture on purchase/sales lines, transfer moves serial ownership across warehouses.

### Work breakdown

**Wave 4.0 — Warehouses + transfers (~42–52 pts)**

| ID | Title | Pts |
|---|---|---:|
| INV-000 | `Warehouse` model + default backfill + API/FE | 5 |
| INV-001 | Movement + balance warehouse grain + rebuild command | 8 |
| INV-002 | Thread warehouse through sales/purchase/return/adjustment | 8 |
| INV-003 | FE warehouse on editors + stock pages | 5 |
| INV-004 | `StockTransfer` model/service complete/cancel | 8 |
| INV-005 | Transfer FE + optional print/PDF | 5 |
| INV-006 | Low stock per warehouse | 3 |
| INV-007 | Migration tests + dual-warehouse E2E | 5 |

**Wave 4.1 — Batch / expiry (~36–44 pts)**

| ID | Title | Pts |
|---|---|---:|
| INV-100 | `track_batch` + `BatchLot` + movement/balance grain | 8 |
| INV-101 | Purchase/sales Complete batch rules + FEFO helper | 8 |
| INV-102 | Billing FE batch picker + expiry columns | 5 |
| INV-103 | Expiry alerts API + page | 5 |
| INV-104 | Block-expired issue setting | 3 |
| INV-105 | Transfer preserves/moves batch quantity | 5 |
| INV-106 | Fixtures: multi-batch FEFO | 5 |

**Wave 4.2 — Valuation (~28–36 pts)**

| ID | Title | Pts |
|---|---|---:|
| INV-200 | Company valuation method + service skeleton | 5 |
| INV-201 | WAVG engine + tests | 8 |
| INV-202 | FIFO engine + tests (batch-aware) | 8 |
| INV-203 | Sale `unit_cost` snapshot from engine | 5 |
| INV-204 | Stock valuation report + export | 5 |
| INV-205 | CA golden valuation fixtures | 3 |

**Wave 4.3 — Price lists (~18–24 pts)**

| ID | Title | Pts |
|---|---|---:|
| INV-300 | PriceList models + API | 5 |
| INV-301 | Customer default list + billing fill | 5 |
| INV-302 | FE price list admin + editor integration | 5 |
| INV-303 | Import prices | 3 |

**Wave 4.4 — Serials (~28–34 pts, demand-gated)**

| ID | Title | Pts |
|---|---|---:|
| INV-400 | Serial model + state machine | 8 |
| INV-401 | Purchase/sales serial capture | 8 |
| INV-402 | Transfer + return serial rules | 5 |
| INV-403 | FE + history report | 5 |
| INV-404 | Tests: unique serial per company | 3 |

### Testing & Definition of Done

**Mandatory invariant:** for every completed `StockTransfer`,
`sum(TRANSFER_OUT qty) == sum(TRANSFER_IN qty)` per product (and per
batch/serial). Migration tests must prove a single-warehouse tenant rebuilds
identical `on_hand` after the warehouse-grain backfill.

4.0 exit: default warehouse backfilled on all movements; transfer
complete/cancel with a quantity-conservation test; rebuild-balance command
verified on a pilot dump. 4.1 exit: FEFO suggestion + expiry alerts + correct
transfer of batch quantity. 4.2 exit: WAVG + FIFO engines pass CA golden
fixtures; sale movements snapshot `unit_cost`. 4.3 exit: ≥2 price lists with
customer default + override. 4.4 exit (only if chartered): unique serials,
full state machine, history report.

### Key risks

The `StockBalance` unique-together migration is the single riskiest step —
mitigated by expand/contract migration plus a mandatory rebuild command and a
pilot dry-run; free-text `batch_no` vs. the new `BatchLot` FK creating a dual
truth (resolved by keeping the ledger on the FK and the line snapshot as a
string); enabling FIFO before batches exist producing inaccurate valuation
(WAVG stays the default until 4.1 lands); serial tracking scope creep without
a demand gate.

---

## Phase 5 — Light accounting

*Canonical: [`docs/phase5/PHASE_5_LIGHT_ACCOUNTING.md`](../phase5/PHASE_5_LIGHT_ACCOUNTING.md)*

**Status 2026-08-21:** CoA, posting, journals, TB/P&L/BS, bank recon, cost
centers, and fixed assets are **built**. `accounting_enabled` defaults False
and is unset in demo seed. **Do not enable for a pilot** until §0 #9
(GL-as-truth) and CA CoA codes are signed, and GAP-006 Health checks are
green. Backfill command is idempotent — run as designed. 5.4/5.5 are not
"later unbuilt"; they are enablement/CA.

Adds an **optional, opt-in** double-entry projection on top of documents —
never a second place to "fix" a sale. Explicitly the last of Phases 3–5
because accounting is a projection of operational truth, not the truth
itself.

### Start gate

| Prerequisite | Source | Why |
|---|---|---|
| Phase 0 Go | `docs/pilot/GO_NO_GO.md` | Books on wrong invoices = wrong TB forever |
| Marketing still says billing-first / documents-as-truth | README/onboarding | Must not silently rebrand as "full Tally replacement" |
| **Demand gate:** ≥3 paid pilots ask for journals/TB/P&L in writing | Sales/support | Avoid speculative GL |
| Phase 3.2 bank statement import live | Phase 3 | Bank recon (5.3) needs statement lines |
| Phase 1 outstanding + CN/DN correct | Phase 1 DoD | AR/AP control accounts must tie to party ledgers |
| CA workshop on default Indian SME CoA | External | Wrong CoA = unusable TB |

**Do not start journal UI before document→GL posting rules are locked and
reconcilable to registers** — manual journals without auto-posting recreate
the dual-write problem the MVP explicitly avoided.

### Locked decisions (key)

> Amended by §0 (2026-08-21), pending PM+CA sign-off of #9: when
> `accounting_enabled`, party outstanding is read from GL control (`1200` /
> `2100`). Documents remain the *posting* source; never "edit the journal to
> fix the invoice." `AR_CONTROL_MISMATCH` / `AP_CONTROL_MISMATCH` is the
> dual-truth safety net. 5.4/5.5 are built; enablement-gated.

- **Documents remain the source of truth for mutation; GL is the books-on read model.** An invoice amount changes only via CN/DN or an allowed amend path, which re-posts or reverses the GL batch — never "edit the journal to fix the invoice."
- Standard double-entry `JournalEntry` (header) + `JournalLine` (account, debit, credit); every batch must balance; posted lines are **append-only** — corrections are reversing/contra entries, never edits.
- Auto-posting happens on document Complete / payment create / valuation period close; **drafts never post**.
- A seeded **Indian SME Chart of Accounts** ships with system-flagged accounts for AR, AP, Inventory, Cash, Bank(s), Sales, Purchase, GST output/input.
- Phase 5 is **opt-in per company** (`Company.accounting_enabled`) — pilots without demand never see the Journals nav at all.
- Bank reconciliation (5.3) clears the **GL bank account** against Phase 3's `BankStatementLine` — a distinct concept from Phase 3's receipt-matching, and the UI must explain the relationship.
- Cost centers (5.4) and fixed assets (5.5) are explicitly **later, demand-gated waves**, not part of the core 5.0–5.3 calendar.

### Scope by wave

- **5.0 — Chart of accounts + document→GL posting:** CoA models + seed, `AccountingMapping` (event → debit/credit accounts), idempotent `PostingService`, Books Health checks (`AR_CONTROL_MISMATCH`, `AP_CONTROL_MISMATCH`, `UNBALANCED_ENTRY`), feature flag.
- **5.1 — Journal vouchers:** manual journal draft/post/reverse UI, period-lock enforcement, attachment + audit.
- **5.2 — Trial Balance → P&L → Balance Sheet:** as-of/for-period reports, XLSX export, CA pack, inventory BS line sourced from Phase 4.2 valuation when available (else disclosed as an approximation).
- **5.3 — Bank reconciliation:** `BankReconSession` matching GL bank lines to Phase 3 statement lines, cleared-vs-outstanding report.
- **5.4 — Cost centers (later):** optional dimension on documents + journal lines, P&L by cost center.
- **5.5 — Fixed assets (last):** asset register, SLM depreciation job, disposal voucher.

### Work breakdown

**Wave 5.0 — CoA + posting (~48–60 pts)**

| ID | Title | Pts |
|---|---|---:|
| ACC-000 | `accounting` app + Account model + Indian SME seed | 8 |
| ACC-001 | Feature flag + permissions + nav gate | 3 |
| ACC-002 | AccountingPeriod + soft close | 5 |
| ACC-003 | PostingService skeleton + idempotency keys | 8 |
| ACC-004 | Post sales invoice + CN/DN + receipt mappings | 8 |
| ACC-005 | Post purchase + supplier payment + ITC/output GST | 8 |
| ACC-006 | Inventory/COGS posting hooks (Phase 4 aware) | 5 |
| ACC-007 | Books Health AR/AP control checks | 5 |
| ACC-008 | Backfill command for historical completed documents | 5 |
| ACC-009 | Tests: balanced entries + control-reconcile fixtures | 8 |

**Wave 5.1 — Journals (~18–24 pts)**

| ID | Title | Pts |
|---|---|---:|
| ACC-100 | Manual journal API draft/post/reverse | 8 |
| ACC-101 | Journal FE voucher editor | 8 |
| ACC-102 | Period lock blocks post | 3 |
| ACC-103 | Attachment + audit | 3 |

**Wave 5.2 — Financial statements (~28–34 pts)**

| ID | Title | Pts |
|---|---|---:|
| ACC-200 | Trial Balance report + API | 5 |
| ACC-201 | P&L report | 5 |
| ACC-202 | Balance Sheet report + equation check | 8 |
| ACC-203 | FE pages + XLSX export | 8 |
| ACC-204 | CA golden month fixture (TB/P&L/BS) | 5 |

**Wave 5.3 — Bank recon (~28–36 pts)**

| ID | Title | Pts |
|---|---|---:|
| ACC-300 | Link Account ↔ BankAccount; cash/bank posting uses it | 5 |
| ACC-301 | `BankReconSession` model + APIs | 8 |
| ACC-302 | Match GL lines ↔ statement lines (reuse Phase 3 scoring) | 8 |
| ACC-303 | Recon FE + outstanding list + report | 8 |
| ACC-304 | Tests: recon ties statement to GL | 5 |

**Wave 5.4 — Cost centers (~22–28 pts, later)**

| ID | Title | Pts |
|---|---|---:|
| ACC-400 | CostCenter model + doc field | 5 |
| ACC-401 | Journal line dimension + P&L slice | 8 |
| ACC-402 | FE + light allocation rules | 8 |

**Wave 5.5 — Fixed assets (~32–40 pts, last)**

| ID | Title | Pts |
|---|---|---:|
| ACC-500 | Asset category + register | 8 |
| ACC-501 | Capitalize from purchase / manual | 5 |
| ACC-502 | SLM depreciation job + journals | 8 |
| ACC-503 | Disposal voucher | 5 |
| ACC-504 | FE + reports | 8 |

### Testing & Definition of Done

Mandatory reconciliation invariants: every entry balances
(`sum(debit)==sum(credit)`); AR/AP control balances tie to `LedgerService`
party outstandings within paise tolerance on a golden tenant; every completed
sales invoice with accounting on has exactly one active posting batch; the
Balance Sheet equation holds on the CA fixture.

5.0 exit: seeded CoA + flag; auto-posting for core document types; idempotent
posting with correct cancel/CN reversal; AR/AP control Health green;
historical backfill command works. 5.1 exit: balanced manual journals with
period lock. 5.2 exit: TB/P&L/BS APIs + FE + export, BS equation holds. 5.3
exit: bank recon session clears GL against Phase 3 statements with a
difference report. 5.4/5.5: only after a separate PM charter and demand
signal.

### Key risks

Dual truth between GL and documents (mitigated structurally by D1 + control
Health, never by a "line edit" escape hatch); building GL ahead of the
3-pilot demand gate; claiming perpetual-inventory COGS posting without Phase
4.2 valuation in place (falls back to disclosed periodic mode); backfill
performance/locking on large historical document sets (chunked Celery,
off-peak).

---

## Phase 6 — AI differentiator

*Canonical: [`docs/phase6/PHASE_6_AI_DIFFERENTIATOR.md`](../phase6/PHASE_6_AI_DIFFERENTIATOR.md)*

**Status 2026-08-21:** Alerts, daily summary, health score watermark (30
invoices), cashflow, hints, and the tool-calling assistant (draft invoice +
reminder; money-moving blocked) are **in code**. `ai_features_enabled`
defaults False; keep Owner-only. Remaining are `[OPEN]` human items: LLM
budget/who pays, copy honesty sweep, synthetic vs real 90-day tenants. No
greenfield AI build in the gap-closure sprint.

An insight layer on top of real transaction data — decision support, not
automated accounting or tax advice. Rules-first; the LLM only grounds answers
in tool results in the final wave.

### Start gate

| Prerequisite | Source | Why |
|---|---|---|
| Phase 0 Go / money Criticals closed | `docs/pilot/GO_NO_GO.md` | Wrong invoices → wrong AI advice |
| Phase 1 core DoD | Phase 1 | Outstanding/profit signals need CN/DN netting |
| ≥90 days completed sales+purchase+receipts for ≥5 pilot companies (or realistic synthetic tenants) | Pilot metrics | Health score and cashflow forecast need history |
| LLM keys + cost budget approved for production | `LLM_PROVIDER` | Assistant + extraction share one spend pool |
| Honesty gate: no "AI accountant" or tax-advice marketing claims | Onboarding/support copy | Legal + CA trust |

**Do not start before Phase 1 outstanding math is correct.** A smart alert
claiming a customer owes ₹X when CN/DN netting is wrong destroys founder
trust faster than shipping no AI at all.

### Locked decisions (key)

- Phase 6 ships **decision support**, never automated accounting, tax filing, or bank transfers — copy says "insights from your BizBoard documents," never "AI CA."
- **Rules-first, LLM-second:** Waves 6.0–6.3 are deterministic formulas and thresholds; only 6.4's assistant uses an LLM, and only to ground answers in tool results.
- Cashflow prediction reuses **no new ledger/journal tables** — it's a projection from open documents and historical collection rates, always shown with a confidence band, never a false-precision single number.
- The Business Health Score is a transparent **0–100 composite of weighted factors** — every score change must show which factors moved it.
- The NL Assistant (6.4) is a **tool-calling agent over company-scoped read APIs only**; anything that writes (a draft invoice, a reminder) is **propose → confirm**, never auto-executed. It never answers tax-rate, place-of-supply, or GSTR-liability questions in free text — those redirect to Reports/GST Health/"ask your CA."
- A minimum-data gate (≥30 completed sales invoices, or an explicit Owner override with a "limited data" watermark) prevents nonsense 100-scores on empty tenants.
- All AI features sit behind `Company.ai_features_enabled`; Owner-only at pilot, Staff access later behind its own flag.

### Scope by wave

- **6.0 — Daily Business Summary + Smart Alerts:** a `BusinessAlert` catalog cloned from the GST Health pattern, a daily Celery-beat summary snapshot, a Dashboard insights strip + alerts drawer, optional email digest.
- **6.1 — Business Health Score + Founder Dashboard:** a weighted 0–100 score service with explainable factors, nightly snapshots for trend charts, a dedicated Founder Dashboard route.
- **6.2 — Cashflow prediction:** 7/14/30-day horizons from open AR/AP + historical collection lag, relative mode by default (no bank balance required) with an optional absolute mode from Owner-entered opening cash.
- **6.3 — Profit leak / growth hints:** deterministic hint generators (margin compression, dead stock, customer concentration, discount abuse, overdue concentration), each linking to the evidence.
- **6.4 — Natural Language Business Assistant:** a tool-calling chat agent grounded in the read-only tool registry built by 6.0–6.2, with a propose/confirm pattern for any write action.

### Work breakdown

**Wave 6.0**

| ID | Item | Pts |
|---|---|---:|
| AI-000 | `insights` app + models + migrations + permissions | 5 |
| AI-001 | Alert catalog engine + upsert + API | 8 |
| AI-002 | Daily summary service + Celery beat + snapshot | 8 |
| AI-003 | Email digest (reuse NotificationService) | 3 |
| AI-004 | FE Dashboard strip + Alerts page | 8 |
| AI-005 | Tenant isolation + alert unit tests | 5 |

**Wave 6.1**

| ID | Item | Pts |
|---|---|---:|
| AI-100 | Health score factors + weights + snapshot | 8 |
| AI-101 | Founder Dashboard FE | 8 |
| AI-102 | History sparklines + limited-data watermark | 5 |
| AI-103 | Factor unit tests with golden fixtures | 5 |

**Wave 6.2**

| ID | Item | Pts |
|---|---|---:|
| AI-200 | Collection-rate stats from history | 5 |
| AI-201 | Forecast engine + relative/absolute modes | 13 |
| AI-202 | Cashflow FE + disclaimer | 8 |
| AI-203 | Forecast property tests (horizon conservation) | 5 |

**Wave 6.3**

| ID | Item | Pts |
|---|---|---:|
| AI-300 | Hint generators (6 codes) + evidence links | 8 |
| AI-301 | FE cards on Founder Dashboard | 5 |
| AI-302 | Hint regression fixtures | 3 |

**Wave 6.4**

| ID | Item | Pts |
|---|---|---:|
| AI-400 | Extend LLM client: chat + tools + usage ledger | 8 |
| AI-401 | ToolExecutor + tenancy fail-closed | 13 |
| AI-402 | Threads/messages API | 8 |
| AI-403 | Chat FE + citation chips + propose/confirm | 13 |
| AI-404 | Safety suite (prompt injection, cross-tenant, tax refusal) | 8 |
| AI-405 | Cost budget enforcement | 5 |

**Total: ~150 pts ≈ 16–22 weeks solo.**

### Testing & Definition of Done

Tenant-isolation tests are mandatory for every tool the assistant can call —
cross-tenant tool-call attempts must fail in tests, not just in review. The
assistant's grounded-answer rate (tool citation present on money answers)
must be ≥95% in pilot scripts; tax/GSTR free-text questions must be refused
with a canned redirect.

6.0 exit: idempotent daily summaries, ≥8 alert codes with tests, snooze
works. 6.1 exit: explainable score + nightly snapshots + limited-data
watermark. 6.2 exit: 7/14/30-day forecast with confidence band, relative
mode works without opening cash. 6.3 exit: ≥5 hint types with CTA deep
links. 6.4 exit: grounded assistant answers, cross-tenant fail tests green,
tax questions refused, propose/confirm write path, usage-ledger budget
enforcement live.

### Key risks

Hallucinated outstanding/tax figures (mitigated by tool-only grounding + hard
tax-refusal rule); alert fatigue from too many Criticals (severity discipline
+ snooze); a confidently wrong score on thin data (the data-gate watermark);
LLM cost blowups (per-company monthly budget with hard fail); prompt
injection attempting to dump cross-tenant data (tool allowlist + tenancy
tests).

---

## Phase 7 — Ecosystem & scale

*Canonical: [`docs/phase7/PHASE_7_ECOSYSTEM_SCALE.md`](../phase7/PHASE_7_ECOSYSTEM_SCALE.md)*

**Status 2026-08-21:** Tally CSV/XLSX/XML + golden fixture, WhatsApp Cloud
(templates + `wa.me`), POS, recurring (draft-only), and `CompanyGstin`
(multi-GSTIN on **one** Company) are **shipped**. No `Branch` model. PAN and
UDYAM verify are **unbuilt** (freeze). D6 reversal (`CompanyGstin` vs
multiple Companies) is provisionally adopted — **PM must confirm**. 7.2
remainder = one user, many companies. 7.3 = UAT/hardening only. Busy/Zoho/
ONDC/DigiLocker/eSign stay frozen.

Migration tooling, messaging, tenancy expansion, and India Stack
verification — every wave here **amplifies** whatever money/GST/AI quality
already exists, so it deliberately comes last and is demand-gated per
integration.

### Start gate

| Prerequisite | Source | Why |
|---|---|---|
| Phase 0 Go + pilot money Criticals | `docs/pilot/GO_NO_GO.md` | Importing Tally into a broken tenant multiplies pain |
| Phase 1 + Phase 2.0 exit | Phase 1/2 docs | Migration customers expect GST-capable billing |
| Phase 6.0 alerts live, or explicit PM waiver | Phase 6 | Digests + WhatsApp Business need an insights payload |
| Paid pilot demand signal **per integration** | Sales/support | Busy/Zoho/ONDC are demand-gated — do not build speculatively |
| Legal/DPDP review for KYC + WhatsApp templates | External | India Stack + WA templates are compliance-heavy |

**Sequencing principle:** Tally import (migration) and WhatsApp Business
(retention) can start before multi-company. Multi-company/multi-branch is an
architecture wave that also unlocks multi-GSTIN. Manufacturing BOM, ONDC,
DigiLocker/Aadhaar eSign stay **Future** until the ICP expands.

### Locked decisions (key)

> Amended by §0 (2026-08-21), pending PM sign-off of #54: multi-GSTIN is
> `CompanyGstin` on one Company (stamp-scoped). Multi-company = one user,
> many Companies. WhatsApp Cloud, POS, recurring, Tally CSV/XLSX/XML are
> shipped. PAN/UDYAM remain unbuilt.

- **Tally first** among desktop-accounting migrations; Busy/Zoho only on written customer demand, sharing the same `AccountingMigration` adapter interface.
- Tally **import** covers masters + opening AR/AP + optional stock; **export** is a voucher/daybook CSV/XML aid for the CA — explicitly **not** live two-way sync in this wave.
- WhatsApp Business ships **template messages only** (invoice link, payment reminder, daily summary) — free-form chat-bot is out of scope; `wa.me` stays as the fallback share channel when WABA is down.
- Multi-company means a user may hold **multiple active memberships** with a company switcher and `active_company_id` context — this replaces the current single-active-membership constraint, which is the hardest migration in the phase.
- Multi-GSTIN is **`CompanyGstin` on one Company** (stamp-scoped GSTR), not multiple Companies. One user → many Companies remains a separate 7.2 feature.
- Recurring invoices create **drafts only**; a schedule never auto-Completes money without a human confirming.
- India Stack verification (PAN/GSTIN/UDYAM) is **soft-fail** — a failed or pending verification allows save plus a Health/Insights alert, never a hard block.
- ONDC, DigiLocker, and Aadhaar eSign get **design hooks only** (credential slots, event names) until a PM charter exists — no build.
- All external credentials are encrypted at rest, reusing the GSP secrets pattern; adapter failures never block billing Complete.

### Scope by wave

- **7.0 — Tally import/export:** guided import wizard (upload → map ledgers → preview opening AR/AP/stock → commit → error report), Tally-friendly voucher export aid with a "not certified sync" disclaimer.
- **7.1 — WhatsApp Business API:** Meta Cloud API (or BSP) adapter, template catalog, opt-in/opt-out on Customer, delivery-status webhook, `wa.me` fallback.
- **7.2 — Multi-company / multi-branch:** drop the single-active-membership constraint, company switcher, `Branch` model with stock balances becoming `(company, branch, product)`, branch-aware reports, a full tenant-isolation test rewrite.
- **7.3 — POS mode + recurring invoices:** distraction-free `/pos` route (still creates normal `SalesInvoice` + `Receipt` underneath), `RecurringInvoiceSchedule` that drafts on a cadence.
- **7.4 — India Stack verifications:** PAN + hardened GSTIN + UDYAM verify adapters, DPDP-aware caching, onboarding "verify identity" checklist.
- **7.5 (demand-gated):** Busy / Zoho adapters, only after logged customer requests.
- **7.6 / 7.7 (explicitly Future):** ONDC, DigiLocker, Aadhaar eSign (spike ADRs only for now); Manufacturing BOM (requires branch maturity from 7.2 first, and manufacturer pilots signed before scheduling).

### Work breakdown

**Wave 7.0 — Tally**

| ID | Item | Pts |
|---|---|---:|
| ECO-000 | `integrations` app + Connection + SyncRun | 5 |
| ECO-001 | Tally parse masters + mapping UI | 13 |
| ECO-002 | Opening AR/AP + stock commit | 13 |
| ECO-003 | Export voucher aid + disclaimer | 8 |
| ECO-004 | Golden fixture from sample Tally export | 8 |
| ECO-005 | Onboarding honesty + support runbook | 3 |

**Wave 7.1 — WhatsApp Business**

| ID | Item | Pts |
|---|---|---:|
| ECO-100 | Meta provider + secrets | 8 |
| ECO-101 | Templates + send invoice/reminder | 8 |
| ECO-102 | Webhook delivery status | 5 |
| ECO-103 | Opt-in UX + FE settings | 8 |
| ECO-104 | Fallback to wa.me when WABA down | 3 |

**Wave 7.2 — Multi-company / branch (hardest wave)**

| ID | Item | Pts |
|---|---|---:|
| ECO-200 | Membership constraint migration + select-company | 13 |
| ECO-201 | FE company switcher + context bugsweep | 13 |
| ECO-202 | Branch model + default backfill | 8 |
| ECO-203 | StockBalance branch migration | 13 |
| ECO-204 | Documents/reports branch filter | 8 |
| ECO-205 | Tenant isolation suite rewrite | 13 |

**Wave 7.3 — POS + recurring**

| ID | Item | Pts |
|---|---|---:|
| ECO-300 | POS page + quick pay path | 13 |
| ECO-301 | Recurring schedules + Celery drafter | 8 |
| ECO-302 | Notify drafts ready | 3 |
| ECO-303 | POS UAT checklist | 3 |

**Wave 7.4 — India Stack verifications**

| ID | Item | Pts |
|---|---|---:|
| ECO-400 | PAN/UDYAM fields + providers | 8 |
| ECO-401 | FE verify + cache | 5 |
| ECO-402 | Health/onboarding hooks | 3 |
| ECO-403 | DPDP retention note | 2 |

**Demand-gated / Future (not scheduled)**

| ID | Item | Pts |
|---|---|---:|
| ECO-500 | Busy adapter | 21 |
| ECO-501 | Zoho Books adapter | 21 |
| ECO-600 | ONDC spike ADR | 5 |
| ECO-601 | DigiLocker spike | 5 |
| ECO-602 | Aadhaar eSign spike | 5 |
| ECO-700 | BOM + production order epic | 40+ |

### Testing & Definition of Done

7.0 exit: at least one real Tally export recipe documented and green on a
golden fixture; masters + openings commit with an error report. 7.1 exit:
template sends work in sandbox/prod WABA with delivery status reflected; opt-
in enforced; `wa.me` fallback works. 7.2 exit: a user with two companies can
switch without logging out, with tenant-isolation tests passing; stock is
correctly unique per branch. 7.3 exit: POS creates a completed invoice +
payment in a UAT-verified low tap count; recurring only ever creates drafts.
7.4 exit: PAN + UDYAM soft-fail verification live alongside the existing
GSTIN provider.

### Key risks

Tally XML dialect chaos (mitigated by supporting 1–2 documented export
recipes rather than "all of Tally"); claiming "Tally sync" in marketing when
7.0 only ships import + an export aid; WhatsApp template rejection or number
ban (compliance templates only, `wa.me` always kept as fallback);
multi-company auth bugs leaking across tenants (ECO-205's full isolation
rewrite is non-negotiable); building ONDC/BOM before real demand wastes
months that should go to 7.0–7.4.

---

---

## Appendix — locked-decision patches (canonical docs still to edit)

When someone next touches the per-phase canonical files, apply these wording
fixes so they stop contradicting §0:

| Doc | Patch |
|---|---|
| Phase 1 D1 | Sales Return posts an internal system CN for AR relief; a *manual* CN still cannot touch stock and cannot double up with the auto CN. |
| Phase 1 D5 / Phase 4 reserved | Strike "reserved stays 0." Reservation is live for confirmed SOs. |
| Phase 1 D6 | Keep Option A default; document `stock_on_delivery_challan` (default False) as the demand-gated exception. |
| Phase 1 §12 Q1 | Still blocked-when-paid until 3.1 refund path; support script. |
| Phase 1 credit-limit race | No longer accepted risk — Complete already `select_for_update`s the customer. |
| Phase 2 GST-001/002/012 | Mark done. Remaining: UQC backfill, B2CL threshold, cess check. |
| Phase 5 D1 | When `accounting_enabled`, outstanding reads GL control; documents remain the posting source. Health `AR_CONTROL_MISMATCH`/`AP_CONTROL_MISMATCH` is the dual-truth safety net. Enablement-gated, not construction-gated. |
| Phase 5 5.4/5.5 | Built; remaining is CA/enablement. |
| Phase 7 D6 | Multi-GSTIN = `CompanyGstin` on one Company (stamp-scoped). Multi-company = one user, many Companies. |
| Phase 7 7.1 / 7.3 | WhatsApp Cloud, POS, recurring: shipped; hardening/UAT only. |
| Wave estimates ECO-300/301, INV-400, ACC-400/500, GST-001/002 | Stale greenfield points; do not use for scheduling. |

---

*This plan compiles the seven canonical phase documents in
`docs/phase1/`–`docs/phase7/` as of 2026-08-21, plus the 61-question
gap-audit recorded in §0. It does not replace or loosen any Phase 0
pilot-hardening gate — see the Bizboard Register for current
production-readiness status. Operative work is the gap-closure sprint in
§0.2, not the historical week totals in §2.*
