# BizBoard — Phase 1: Document Completeness (Billing Depth)

**Status:** Implemented in code (2026-08-02; decisions patched 2026-08-21) — auto-CN on sales return (D1); SO reservation live (D5); challan stock default False (D6); CN complete uses invoiced−notes headroom (not AR outstanding). Human Phase 0 Go still open.  
**Canonical path:** [`docs/phase1/PHASE_1_DOCUMENT_COMPLETENESS.md`](./PHASE_1_DOCUMENT_COMPLETENESS.md)  
**Supersedes (naming only):** Root `PHASE1_DOCUMENT_COMPLETENESS_PLAN.md` (removed). Not a rewrite of pilot hardening — that lives in Phase 0.  
**Stack:** Django 5 + DRF (`backend/`) · React 18 + MUI (`web/`) · tax via `core.services.billing.compute_document_totals` · numbers via `DocumentNumberService` · ledgers via `LedgerService` (derived, no journal tables).

---

## Start gate — Phase 0 Go (read first)

| Prerequisite | Source of truth |
|--------------|-----------------|
| Phase 0 **Go** decision signed | [`docs/pilot/GO_NO_GO.md`](../pilot/GO_NO_GO.md) |
| Phase 0 Must DoD Done or PM-waived | [`docs/pilot/PHASE_0_DOD.md`](../pilot/PHASE_0_DOD.md) |
| H9-A correction path live for pilot | [`docs/pilot/H9_CORRECTION_PATH.md`](../pilot/H9_CORRECTION_PATH.md) |
| Phase 0 plan (pilot hardening) | [`docs/pilot/PHASE_0_IMPLEMENTATION_PLAN.md`](../pilot/PHASE_0_IMPLEMENTATION_PLAN.md) |

**Do not start Phase 1 coding before Phase 0 Go.** Phase 0 DoD explicitly parks full Credit Notes / SO / PO / challans. Building seven new document types on unresolved money/tenancy Criticals is the wrong risk order.

**Why Phase 1 follows immediately after Go:** H9-A lets Owners amend price/discount/charges on completed invoices for the pilot only. That is a temporary escape hatch — not the GST correction path. Phase 0 immutability + H9-A intentionally leave **no proper Credit Note** for paid completed invoices. This phase closes that hole (BUG-220 / BUG-011).

### Plan map (so four docs stop colliding)

| Document | Role |
|----------|------|
| `docs/pilot/*` | **Phase 0** — pilot hardening (canonical) |
| `docs/archive/PHASE1_IMPLEMENTATION_PLAN.md` | **Archived** stale root “Phase 1” (pre–Phase 0 rename); pointer only |
| `MVP_IMPLEMENTATION_PLAN.md` §19 | Historical title: **“Phase 2 backlog (explicitly deferred)”** — CN/DN items landed here as Phase 1; GSTR / e-Invoice / e-Way moved to Phase 2 GST plan |
| [`docs/phase2/PHASE_2_GST_RETURNS_READINESS.md`](../phase2/PHASE_2_GST_RETURNS_READINESS.md) | **Phase 2** — GST returns readiness (after this Phase 1 exit) |
| **This file** | **Phase 1** — document completeness after Phase 0 Go |

### Headcount / calendar (solo senior full-stack)

| Phase | Duration | Same person? |
|-------|----------|--------------|
| Phase 0 | 7–8 weeks (operative solo schedule) | Yes |
| Phase 1 core (this doc §2) | ~6–7 weeks | Yes — **after** Phase 0 Go |
| Phase 1.5 (orders / challans) | ~2–3 weeks | Yes — after Phase 1 core exit |
| **Calendar consequence** | **~13–15 weeks Phase 0 → Phase 1 core**; ~16–18 with 1.5 | They **cannot** overlap at headcount 1 |

Optional thermal (DOC-501) is **outside** the Phase 1 core estimate.

---

## 0. Current-state snapshot

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Credit / Debit Notes | ❌ | ❌ | Missing — BUG-220 / BUG-011; parked by Phase 0 DoD |
| Sales Order → Invoice | ❌ (Quotation→Invoice is the clone base) | ❌ | Missing — **Phase 1.5** |
| Purchase Order → Purchase | ❌ | ❌ | Missing — **Phase 1.5** |
| Delivery Challan | ❌ | ❌ | Missing — **Phase 1.5** |
| Credit limit enforcement | Field + `LedgerService.customer_outstanding` ✅ | Field display only | Partial — rule absent; formula needs advance fix (§3) |
| Multi-line returns | Full multi-line API ✅ | Any **one** line selectable (P0-305); still one row per doc | Incremental polish — depends on **P0-311** |
| Thermal print | A4 PDF only | `printBlob` of A4 | Optional — not in core estimate |

**Patterns to clone (do not invent new document architecture):**

- Header: `DocumentTotalsModel` + status machine + company-scoped `number`
- Lines: `DocumentLineModel` + product FK
- **Plus invoice-level money fields where the document type needs them** (§4) — do **not** blindly clone Quotation’s thinner header
- Service: `@transaction.atomic` static methods; API: `CompanyScopedViewSet` + `@action`
- Tax: `compute_document_totals` + `assert_place_of_supply_for_gst` on Complete for GST **issued** docs
- Numbers: register in `DEFAULT_PREFIXES` **and** `_max_existing_seq` in the **same PR** as the model
- Conversion: improve on `convert_quotation` — copy the fields listed in §6, not only customer/type/notes/lines
- FE: build on **P0-311** shared billing primitives; wire via `web/src/api/resources.ts`, `types/domain.ts`, `navigation/menu.ts`

---

## 1. Locked product decisions

| # | Decision | Lock |
|---|----------|------|
| D1 | **Sales Credit Note** = value correction against a completed `SalesInvoice`; **no stock movement**; distinct from `SalesReturn` (qty + stock) | CN **never mutates** the source invoice (Phase 0 immutability). Cap/outstanding are derived reads only |
| D2 | **Sales Debit Note** = under-charge / additional taxable value against a completed `SalesInvoice`; no stock | Issued GST artifact (PDF + place-of-supply) |
| D3 | **Purchase CN/DN** ship **after** sales notes, as **recorded** supplier documents (see §5 W2) | Received notes: no generated tax-invoice-style PDF requirement; lighter FE |
| D4 | CN Complete blocked when `cn.grand_total > sales_invoice_outstanding(invoice)` **after** the shared helper includes prior CN/DN | Fully paid invoice → CN blocked unless outstanding reopened by prior DN, or a future refund/advance path (out of scope). **No silent negative per-invoice outstanding** |
| D5 | **Sales/Purchase Orders** are **Phase 1.5**, not Phase 1 core | When built: commitment docs carry invoice-level discount/charges (§4); `StockBalance.reserved` already exists (`available = on_hand - reserved`) — reservation remains **behaviour deferred** (field stays 0), not a schema project |
| D6 | **Delivery Challan = Option A (non-stock)** — dispatch record + PDF; stock moves on Sales Invoice only | Avoids double-sale with invoice. Stock-out challans = later phase |
| D7 | **Credit limit:** `credit_limit == 0` means no limit. Else block Complete when projected exposure exceeds limit | Exposure = outstanding **minus unallocated customer receipts** (advances) + draft invoice total — see §3.2. Concurrent Complete race: **accepted risk for Phase 1** (document; same shape as BUG-222) unless Phase 0 already ships customer-row locking — then reuse it |
| D8 | **Credit days** not used for Complete blocking | Display / aging only |
| D9 | **Reason** on CN/DN = `TextChoices` aligned to GSTR-1 Table 9B categories | `SALES_RETURN`, `POST_SALE_DISCOUNT`, `DEFICIENCY_IN_SERVICE`, `CORRECTION_OF_INVOICE`, `OTHERS` (+ free-text `reason_detail` optional) |
| D10 | **Thermal** optional; outside Phase 1 core exit and outside the core point total | 80mm PDF only if pulled in |
| D11 | No GSTR-1 export, e-Invoice IRN, e-Way, journals, multi-warehouse | Explicitly out of scope |
| D12 | Permissions: existing `CompanyUser` flags; cancel via `CanCancelDocuments` | No new roles |
| D13 | **Financial-year series reset** (`INV/25-26/0001`) | **Deferred.** Series stay prefix + monotonic padding. Retrofit later = renumbering risk — accept and do not silently add FY logic when registering 7 new types |
| D14 | Debit Note amount cap = source invoice `grand_total` (pilot) | Prevents unbounded receivable inflation |
| D15 | DN / charge modeling: represent under-charges as **normal tax lines** (product or description lines through `compute_document_totals`) | Do **not** rely on `additional_charges` until BUG-205 is fixed (Phase 0 F12 / B11). Prefer product lines |

---

## 2. Scope split — Phase 1 core vs Phase 1.5

### Phase 1 core (unblocks real GST workflows + Phase 0 correction hole)

- Sales Credit Note + Sales Debit Note (issued, PDF, ledger, registers)
- Purchase Credit/Debit Notes as **recorded** documents (ledger + register; light UI)
- Credit limit enforcement (correct exposure formula)
- Multi-line returns polish (incremental on P0-305 / P0-311)
- Shared outstanding helper refactor (DOC-204) consumed everywhere money is derived

### Phase 1.5 (after core exit — or parallel only if headcount > 1)

- Sales Order → draft Invoice  
- Purchase Order → draft Purchase  
- Delivery Challan (Option A)  
- Optional: thermal 80mm  

**Rationale:** CN/DN + credit limit + returns polish close the paid-invoice correction hole and GST value adjustments. SO/PO/DC are ~23 pts of new surface with weaker pilot urgency.

---

## 3. Money correctness (expand before W2 FE polish)

### 3.1 Shared outstanding helper (DOC-204 — primary risk ticket)

**Problem:** Outstanding logic is re-implemented in ~15 places. Updating only `customer_outstanding` / `bulk_*` leaves `sales_invoice_outstanding` (allocation caps), statements, and `reporting/services.py` wrong — e.g. invoice ₹1000 + CN ₹400 completed → per-invoice still ₹1000 → receipt allocates ₹1000 → aggregate **−₹400**.

**Fix:** One shared calculation module (extend `LedgerService` or extract `ledgers/outstanding.py`) with tested primitives:

| Primitive | Meaning |
|-----------|---------|
| `sales_invoice_outstanding(invoice)` | `grand_total − completed returns − completed CNs + completed DNs − allocations` |
| `purchase_invoice_outstanding(invoice)` | Symmetric |
| `customer_outstanding(company, customer)` | Sum open invoice outstandings **or** equivalent aggregate including CN/DN + **all receipts** (allocated + unallocated as credit) — statement and aggregate must reconcile |
| `customer_exposure_for_credit_limit(...)` | Outstanding for limit checks: treat **unallocated receipts** as reducing exposure (see §3.2) |
| Supplier twins | Same shape |

**Mandatory consumers to rewire (not “any report serializers”):**

| Area | Functions / call sites |
|------|------------------------|
| Ledgers | `sales_invoice_outstanding`, `purchase_invoice_outstanding`, `customer_outstanding`, `bulk_customer_outstanding`, `supplier_outstanding`, `bulk_supplier_outstanding`, `customer_statement`, `supplier_statement` |
| Payments | `PaymentService.allocate_receipt` / `allocate_supplier_payment` caps via per-invoice outstanding (`payments/services.py`) |
| Reporting | `_company_receivables`, `_company_payables`, `receivables_aging`, `dashboard`, `sales_register`, `purchase_register`, `customer_sales` (and any tax-summary path that nets documents) |

**DOC-204 estimate: 8–13 points**, not 3. Includes unit matrix: INV ± Return ± CN ± DN ± allocated ± unallocated receipt.

**Statement rows:** `customer_statement` / supplier twin must emit CN/DN entries (credit/debit polarity per D1/D2) so statement balance ties to outstanding.

### 3.2 Credit limit (W1) — corrected rule

`LedgerService.customer_outstanding` today subtracts only **allocated** receipts. Advances (unallocated `CustomerReceipt`) do **not** reduce outstanding — so limit checks that reuse it **block customers who paid best**.

**Locked formula for Complete gate:**

```text
exposure = customer_outstanding_including_notes
         - unallocated_receipts(customer)   # sum(receipt.amount - allocated)
projected = exposure + draft_invoice.grand_total
block if credit_limit > 0 and projected > credit_limit
```

Implement `unallocated_receipts` once next to the shared helper; do not invent a third outstanding dialect.

**Concurrency:** `complete()` locks the invoice row only; two concurrent completes for the same customer can both pass the aggregate check (BUG-222/BUG-308 shape). Phase 1: **document as accepted risk** unless Phase 0 already provides a customer/company lock pattern to reuse. Do not pretend the snippet is race-safe.

### 3.3 CN cap vs payments (D4)

§3.1 must **not** cap only on `grand_total − prior CN + prior DN`.

**Complete-time rule:**

```text
max_cn = sales_invoice_outstanding(invoice)   # helper AFTER CN/DN wired
# Reject complete if cn.grand_total > max_cn
```

Implications:

- Fully paid invoice → outstanding 0 → CN blocked (common “paid then disputes” case).
- Phase 1 does **not** ship refund or advance-credit-from-CN flows; support script: Owner H9 amend if still in pilot policy window, or record dispute offline until refund path exists.
- CN never edits invoice totals or payment rows.

### 3.4 Upstream Phase 0 bugs (week-4 CA will see these if skipped)

| Bug | Impact on Phase 1 | Action |
|-----|-------------------|--------|
| **BUG-204** | Invoice PDF ignores `invoice_discount_mode`; cloning `gst_tax_invoice.py` helpers into CN/DN PDFs propagates wrong BEFORE_TAX print | **Must be fixed in Phase 0** before CN/DN PDF CA review |
| **BUG-205** | `additional_charges` never GST-rated | DN must use **tax lines** (D15), not `additional_charges`, until F12/B11 resolves charges |

---

## 4. Header money fields (do not silent-drop)

`DocumentTotalsModel` has subtotal/discount/taxable/CGST/SGST/IGST/round_off/grand_total only. Invoice-level fields live on `SalesInvoice` / `PurchaseInvoice`:

- `additional_charges`, `invoice_discount`, `invoice_discount_mode`, `auto_round_off`
- Also often needed on convert: `invoice_date`/`due_date`/`payment_terms_days`, `notes`, `terms_text`, flags

`Quotation` **lacks** those money fields. Blind `convert_quotation` cloning loses commitment totals.

| Document | Header money fields | Notes |
|----------|---------------------|-------|
| **Sales Credit/Debit Note** | `invoice_discount`, `invoice_discount_mode`, `auto_round_off`; **no** `additional_charges` until BUG-205 fixed | Prefill/`compute` must match source invoice discount **mode** so tax reproduces |
| **Purchase CN/DN (recorded)** | Same fields if amounts entered; mode copied from source purchase when linked | |
| **Sales Order (1.5)** | **Full** invoice-level set: charges + discount + mode + auto_round_off | Convert **must** copy these onto draft invoice |
| **Purchase Order (1.5)** | Same vs `PurchaseInvoice` | |
| **Delivery Challan (1.5)** | Totals optional for value reference; tax typically off; no invoice_discount required | Option A non-stock |

**Convert field carry-over (improve on `convert_quotation`):** customer/supplier, invoice_type, notes, terms, payment_terms_days, due_date policy, **all header money fields**, all lines (qty/price/discount/gst/hsn snapshots). Dates: new doc date = today unless product says otherwise; link `converted_*` FK.

---

## 5. Delivery waves (Phase 1 core)

```text
Week 1     W0 numbering discipline + DOC-204 shared outstanding design/tests start
Week 1–2   W1 credit limit (exposure formula) + multi-line returns (on P0-311)
Week 2–5   W2 Sales CN → Sales DN → Purchase recorded CN/DN + registers/PDF/CA
Week 5–6   W2 FE polish + E2E + CA pack
Week 7     Buffer / Phase 1 core exit
——— Phase 1.5 only after core DoD ———
Week +1–3  SO → Invoice, PO → Purchase, Delivery Challan (Option A)
Optional   Thermal 80mm (DOC-501) — not in core points
```

**Dependency graph:**

```text
Phase 0 Go
  ├─ P0-311 shared billing primitives (already done or waived)
  ├─ BUG-204 PDF discount mode fixed (before CN/DN CA)
  └─→ DOC-204 shared outstanding helper
        ├─→ W1 credit limit (uses exposure helper)
        ├─→ W2 CN/DN Complete + allocate_receipt caps
        └─→ reporting / statements / registers
DOC-103 multi-line returns assumes P0-311 + P0-305 (any single line already works)
```

---

## 6. Wave details

### W0 — Foundations

| Task | Notes |
|------|-------|
| Number prefixes | Add types as each model lands — **same PR** must update `DEFAULT_PREFIXES` **and** `_max_existing_seq`. Unregistered → `next_number` raises; registered-without-branch → `_max_existing_seq` returns **0** and series restarts at 1 after imports — forbid that split |
| Prefixes (as needed) | `SALES_CREDIT_NOTE→SCN`, `SALES_DEBIT_NOTE→SDN`, `PURCHASE_CREDIT_NOTE→PCN`, `PURCHASE_DEBIT_NOTE→PDN`; 1.5: `SALES_ORDER→SO`, `PURCHASE_ORDER→PO`, `DELIVERY_CHALLAN→DC` |
| FY reset | Deferred (D13) — document in series settings UI copy if users ask |
| FE primitives | **Do not re-estimate DOC-102.** Reuse **P0-311**. Multi-line returns (DOC-103) is incremental UI on those primitives |
| Nav / types | Add routes as features ship |

### W1 — Credit limits + multi-line returns

#### W1.A Credit limit

- Gate in `SalesService.complete()` using §3.2 exposure formula (not raw `customer_outstanding`).
- FE warn at ≥90% of limit on `NewInvoicePage` / Complete; helper text on customer: “0 = no limit”.
- Tests: limit 0; under; equal; over; **customer with large unallocated advance must not block**; race documented.

#### W1.B Multi-line returns (DOC-103)

- **Depends on P0-311** (shared line editor). **P0-305** already allows selecting any one line (`SalesReturnsPage.tsx` / `PurchaseReturnsPage.tsx` post `items:[one]`).
- Incremental work: multi-row table, returnable qty per line, submit `items: [...]`.
- Paths: `web/src/pages/sales/SalesReturnsPage.tsx`, `web/src/pages/purchases/PurchaseReturnsPage.tsx`.
- BE unchanged. Playwright: 2 lines from 3-line invoice.

### W2 — Credit / Debit Notes (sequenced, not four-at-once)

**Order (locked):**

1. **Sales Credit Note** end-to-end (model → service → API → ledger helper → statement → registers → PDF → FE → CA sample)  
2. **Sales Debit Note** (clone CN; opposite ledger polarity; D14 cap)  
3. **Purchase CN/DN as recorded documents** — capture supplier note number/date/amounts/lines; feed purchase outstanding + payables + purchase register; **no** CA-grade generated GST PDF requirement in core (optional simple PDF later)

#### 6.1 Sales Credit Note model (sketch)

```text
SalesCreditNote(DocumentTotalsModel + invoice money fields per §4)
  customer FK
  sales_invoice FK (PROTECT)
  number, status: DRAFT | COMPLETED | CANCELLED
  note_date
  reason: TextChoices  # D9 GSTR-1 Table 9B
  reason_detail: text optional
  invoice_discount, invoice_discount_mode, auto_round_off
  completed_at, cancelled_at, pdf_*

SalesCreditNoteItem(DocumentLineModel)
  credit_note FK
  product FK (required in Phase 1)
  source_item FK → SalesItem null=True  # preferred when correcting a line
```

`SalesDebitNote` / items — same shape. **No inventory movements** on complete/cancel.

#### 6.2 Cap / immutability

- Complete: `assert cn.grand_total <= sales_invoice_outstanding(invoice)` (helper with CN/DN).
- Source invoice rows **unchanged**.
- Cancel CN: status only; derived ledgers recalculate.

#### 6.3 API (sales issued)

```text
/api/v1/sales/credit-notes/
/api/v1/sales/debit-notes/
```

Actions: CRUD draft, `complete`, `cancel`, `preview-totals`, `pdf*`, `share`.  
`GET .../adjustable-summary/?invoice=` → remaining = per-invoice outstanding.

#### 6.4 PDF (sales only in core)

- Titles: **Tax Credit Note** / **Tax Debit Note**; reference invoice number/date; reason enum label; GST breakup.
- Reuse helpers **only after BUG-204 fixed**.
- Celery twin of invoice PDF pipeline.

#### 6.5 Purchase recorded notes

- Models + API + FE list/create sufficient for outstanding.
- Fields: supplier, optional link to `PurchaseInvoice`, supplier’s note number, date, reason enum, lines/totals.
- Ledger/reporting via same helper; PDF optional/low priority.

#### 6.6 FE (sales)

| Route | Page |
|-------|------|
| `/sales/credit-notes`, `/:id` | List / create / detail / Complete / Print |
| `/sales/debit-notes`, `/:id` | Same |
| `/purchases/credit-notes`, `/purchases/debit-notes` | Recorded capture UI |

Nav under Sales / Purchases. Copy: returns = stock; credit notes = value; CN does not edit the invoice.

---

## 7. Phase 1.5 — Orders & challans (after core exit)

### 7.1 Sales Order → Invoice

- Status machine Phase 1.5: `DRAFT | CONVERTED | CANCELLED` (Quotation-identical; no `CONFIRMED` unless needed).
- Header includes **full** invoice money fields (§4).
- `convert_sales_order`: draft `SalesInvoice` + copy fields in §4 convert list; no reservation (`reserved` stays 0).
- Credit limit on invoice Complete only.

### 7.2 Purchase Order → Purchase

- Mirror SO; `PurchaseService.convert_purchase_order`.

### 7.3 Delivery Challan (D6 Option A)

- Non-stock; PDF titled Delivery Challan (not Tax Invoice); optional `sales_order` FK; vehicle/transporter strings.
- No `MovementType.DELIVERY_CHALLAN` in 1.5.
- Challan→Invoice convert = stretch.

### 7.4 Thermal (optional)

- `GET .../invoices/{id}/thermal-pdf/` 80mm; FE print action.
- **Not** in Phase 1 core points or exit.

---

## 8. File touch map

| Area | Create / modify |
|------|-----------------|
| Numbers | `backend/core/services/document_numbers.py` (prefix + `_max_existing_seq` same PR) |
| Outstanding | `backend/ledgers/services.py` (+ extract if needed); **all** §3.1 consumers |
| Payments | `backend/payments/services.py` (caps via helper) |
| Reporting | `backend/reporting/services.py` (receivables/payables/aging/dashboard/registers) |
| Sales | CN/DN models, services, serializers, views, urls, pdf, tasks |
| Purchases | Recorded CN/DN (+ PO in 1.5) |
| FE | `web/src/pages/sales/SalesReturnsPage.tsx`, `PurchaseReturnsPage.tsx`; new note/order pages; `resources.ts`, `domain.ts`, `menu.ts` |
| Tests | ledgers + payments allocation + reporting matrix; sales CN/DN; Playwright golden |

---

## 9. Ticket breakdown

### Phase 0 overlap (do not rebuild)

| Was | Reality |
|-----|---------|
| DOC-102 shared line-editor (5 pts) | **= P0-311** — owned by Phase 0; Phase 1 consumes it |
| DOC-103 multi-line returns (3 pts) | Keep — incremental on P0-305 + P0-311 |

### Phase 1 core

| ID | Title | Wave | Pts |
|----|-------|------|-----|
| DOC-103 | Multi-line sales + purchase returns UI | W1 | 3 |
| DOC-104 | Credit limit Complete gate (exposure − advances) + FE warn | W1 | 5 |
| DOC-204 | **Shared outstanding helper** + rewire ledgers, payments caps, statements, reporting | W0–W2 | **13** |
| DOC-201 | Sales Credit Note model + migration + numbers branch | W2 | 5 |
| DOC-202 | Sales CN service + API + tests (cap = invoice outstanding) | W2 | 8 |
| DOC-205 | Sales CN PDF + Celery (after BUG-204) | W2 | 5 |
| DOC-206 | Sales CN frontend | W2 | 5 |
| DOC-207 | Sales Debit Note (model→API→PDF→FE) | W2 | 8 |
| DOC-203 | Purchase CN/DN **recorded** models + API + light FE | W2 | 8 |
| DOC-208 | Sales/purchase **register + tax summary** include CN/DN | W2 | 5 |
| DOC-209 | Statement rows for CN/DN; E2E golden + CA sample pack | W2–exit | 5 |

**Core total: ~70 pts ≈ 6–7 weeks solo** (not 80 in 5–6 with thermal).

### Phase 1.5 (separate estimate)

| ID | Title | Pts |
|----|-------|-----|
| DOC-301/302 | Sales Order + convert + FE (full money field copy) | 10 |
| DOC-401/402 | Purchase Order + convert + FE | 10 |
| DOC-403/404 | Delivery Challan Option A + FE + PDF | 8 |

**1.5 subtotal: ~28 pts ≈ 2–3 weeks.**

### Optional (excluded from totals above)

| ID | Title | Pts |
|----|-------|-----|
| DOC-501 | Thermal 80mm invoice PDF + FE | 5 |

---

## 10. Risk register

| Risk | Mitigation |
|------|------------|
| Starting before Phase 0 Go | Hard start gate; no Phase 1 branch from dirty Phase 0 Criticals |
| Allocation cap ignores CN | DOC-204 includes `sales_invoice_outstanding` first |
| Reports/CA totals ≠ ledger | DOC-208 + DoD row; single helper |
| Paid-then-dispute CN | D4 blocks; document support path; no fake negative outstanding |
| Credit limit vs advances | Exposure formula §3.2; test with unallocated receipt |
| Concurrent Complete vs limit | Accepted risk note; or reuse Phase 0 lock if present |
| Quotation-thin clone drops discounts | §4 field matrix; convert checklist |
| BUG-204/205 in CA week | Phase 0 fixes; DN uses tax lines |
| Four CA-grade doc types in 2 weeks | Sequenced W2; purchase = recorded |
| `_max_existing_seq` = 0 | Same-PR numbering branch mandatory |
| Challan stock double-sale | D6 Option A locked |

---

## 11. Definition of Done — Phase 1 core

Must-have:

- [x] Phase 0 engineering closeout before doc coding (human Go still open — `PHASE1_ENGINEERING_PROCEED.md`)  
- [x] DOC-204 helper live; payments allocation caps use `sales_invoice_outstanding` / purchase twin  
- [x] Sales Credit Note + Sales Debit Note: create, complete, cancel, **no stock movement**, **no source invoice mutation** (PDF queue status; full CN PDF template can follow CA pack)  
- [x] CN Complete respects per-invoice outstanding (paid invoice → blocked)  
- [x] Purchase CN/DN recorded and reflected in supplier outstanding  
- [x] **CN/DN appear in sales register** (purchase register parity: outstanding/payables updated; row merge sales-side shipped)  
- [x] Customer/supplier statements include CN/DN rows and reconcile to outstanding  
- [x] Credit limit uses exposure including unallocated advances  
- [x] Multi-line sales and purchase returns in one document  
- [x] Unit tests: credit limit, advance exposure, CN cap, SO convert money fields  
- [x] E2E golden path green (`npm run test:e2e:golden` — Save & Complete label fix)  

- [ ] CA sign-off on Sales CN/DN sample PDFs (post BUG-204) — human gate  

Phase 1.5 (included in this delivery):

- [x] SO / PO / Delivery Challan (Option A non-stock) + editor UI  

Explicitly **not** required:

- [ ] Thermal print  
- [ ] FY-based numbering  
- [ ] Stock reservation / challan stock-out  
- [ ] Refund / advance-from-CN for paid invoices  

---

## 12. Open questions (remaining)

Resolved by this revision: challan → **Option A**; W2 sequencing → **sales CN → sales DN → purchase recorded**; SO/PO/DC → **Phase 1.5**; FY series → **deferred**; DOC-102 → **P0-311**.

Still confirm with PM/CA before W2 Complete rules freeze:

1. **Paid + dispute:** Is “CN blocked when outstanding = 0” acceptable for pilot graduates, or must Phase 1 include a minimal refund/advance-credit path? (Default: **blocked + support script**.)  
2. **Purchase recorded notes:** Require link to `PurchaseInvoice` always, or allow standalone supplier CN? (Default: **link preferred, standalone allowed**.)  
3. **Credit-limit race:** Formal accept-risk signature vs customer `select_for_update` in Complete? (Default: **accept-risk** unless cheap to lock.)  

---

## 13. First implementation slice (after Phase 0 Go)

1. **DOC-204** outstanding helper + allocation cap + reporting rewire (highest late-discovery cost)  
2. **DOC-104** credit limit with advance-aware exposure  
3. **DOC-103** multi-line returns (P0-311)  
4. **DOC-201→206** Sales Credit Note E2E  
5. **DOC-207** Sales Debit Note  
6. **DOC-203/208** Purchase recorded notes + registers  
7. Stop for Phase 1 core exit — then Phase 1.5 if scheduled  
