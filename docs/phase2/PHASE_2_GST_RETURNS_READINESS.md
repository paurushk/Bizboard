# BizBoard — Phase 2: GST Returns Readiness

**Status:** Implemented in code (2026-08-02; worksheets patched 2026-08-21) — GSTR-1 SUPECOM Table 15 aid; GSTR-9 tables 4–8 books/2B worksheets; `format=gstn-json` dark. Sandbox GSP adapters; real GSP procurement remains PM track (GST-014).  
**Canonical path:** [`docs/phase2/PHASE_2_GST_RETURNS_READINESS.md`](./PHASE_2_GST_RETURNS_READINESS.md)  
**Root pointer:** [`PHASE2_IMPLEMENTATION_PLAN.md`](../../PHASE2_IMPLEMENTATION_PLAN.md)  
**Stack:** Django 5 + DRF (`backend/`) · React 18 + MUI (`web/`) · tax via `core.services.billing.compute_document_totals` · offline GSTR via `reporting/gst_returns.py` · e-Invoice/e-Way payload builders in `sales/einvoice_payload.py` + `sales/eway_payload.py` (no live IRP/NIC yet).

---

## Start gate — Phase 1 exit (read first)

| Prerequisite | Source of truth |
|--------------|-----------------|
| Phase 0 Go / pilot money Criticals closed | [`docs/pilot/GO_NO_GO.md`](../pilot/GO_NO_GO.md) |
| Phase 1 core DoD (CN/DN, outstanding helper, credit limit) | [`docs/phase1/PHASE_1_DOCUMENT_COMPLETENESS.md`](../phase1/PHASE_1_DOCUMENT_COMPLETENESS.md) §11 |
| Sales CN/DN complete + CDNR present in offline GSTR-1 | `backend/reporting/gst_returns.py` + `backend/tests/test_gst_returns.py` |
| CA sign-off on Tax Invoice + Sales CN/DN sample PDFs | Human gate (still open in Phase 1 DoD) |

**Do not start Phase 2 filing polish before CN/DN ledger + GSTR CDNR reconcile.** Returns without notes produce wrong CA packs and false confidence.

**Why this phase next:** Phase 1 closed the GST *value correction* path (CN/DN). Phase 2 closes the GST *reporting & statutory artifact* path — and must also close the *identity correction* gap (wrong GSTIN / POS) that CN/DN cannot fix (§1 D16).

### Plan map

| Document | Role |
|----------|------|
| `docs/pilot/*` | Phase 0 — pilot hardening |
| `docs/phase1/PHASE_1_DOCUMENT_COMPLETENESS.md` | Phase 1 — CN/DN, credit limit, SO/PO/DC |
| `MVP_IMPLEMENTATION_PLAN.md` §19 items 7–8 | Historical backlog labels for GSTR / e-Invoice / e-Way |
| **This file** | **Phase 2** — GST returns readiness |

### Headcount / calendar (solo senior full-stack)

| Wave | Duration | Same person? |
|------|----------|--------------|
| Phase 2.0 — Filing integrity + rate-wise GSTR-1/3B + Health | ~5–6 weeks | Yes |
| Phase 2.1 — Tax modes + GSTIN verify | ~2–3 weeks | Yes — after 2.0 |
| Phase 2.2 — E-Invoice (IRN + QR) live path | ~3–4 weeks eng (**GSP procurement starts in 2.0**) | Yes — after 2.1 data quality |
| Phase 2.3 — E-Way Bill live path | ~2–3 weeks | Yes — after 2.2 payload maturity |
| Phase 2.4 — GSTR-9 annual aid | ~2 weeks | Yes — after 2.0 stable for ≥1 FY quarter of data |
| **Calendar consequence** | **~14–18 weeks** sequential eng; GSP paperwork overlaps 2.0–2.1 | Waves **cannot** overlap at headcount 1 |

**2.0 + 2.1 (no live NIC): ~8–9 weeks** after rate-wise B2B / UQC / line-snapshot re-scope (was ~6–7).  
GSTR-9 is last because it needs clean monthly extracts, not because it is low value.

**Non-engineering track (starts Day 1 of Wave 2.0):** GSP/IRP vendor selection + contract + KYC + sandbox credentials (Q1/Q6). Calendar-dominated (often 4–8 weeks). Do **not** wait for Wave 2.2 to start paperwork — see §13.

---

## 0. Current-state snapshot (as of 2026-08-02)

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| GSTR-1 offline preview/export | Scaffold: B2B / B2CL / B2CS / CDNR + XLSX | ✅ `GstReturnPage` | **Structurally incomplete** — header-level B2B/CDNR/B2CL (not rate-wise); no HSN T12 / CDNUR / UQC; `invoice_value` can diverge from taxable+tax; not GSTN upload schema |
| GSTR-3B offline preview/export | ✅ Outward + purchase ITC hint | ✅ Same page pattern | **Partial** — RCM / import / ITC reverse = `manual_review` stubs; purchase CN/DN netting incomplete |
| GSTR-9 | ❌ | ❌ | Missing |
| Line HSN / unit snapshot | `SalesItem` / `PurchaseItem` snapshot `hsn_code` + free-text `unit_name` at line save | — | **Partial** — CN/DN lines **lack** `hsn_code`/`uqc`; no GSTN UQC code; GSTR builders do not yet prefer line snapshots; blank HSN still allowed on Complete |
| GSTIN format validation | ✅ `validate_gstin` | ✅ settings/forms | Format only |
| GSTIN live verification | ❌ | ❌ | Missing |
| GST Health Dashboard | ❌ | ❌ | Missing |
| Reverse charge | ❌ (3B stub note) | ❌ | Missing |
| Tax-inclusive pricing | ❌ | ❌ | Missing — all math is tax-exclusive today |
| E-Invoice IRN + QR | Payload prepare + mark-generated fields ✅ | API clients in `resources.ts` ✅ | **Scaffold** — no IRP call; QR not on PDF |
| E-Way Bill | Payload prepare + mark-generated (invoice + challan) ✅ | API clients ✅ | **Scaffold** — no NIC call |
| Wrong GSTIN / POS correction | ❌ | ❌ | **Roadmap gap** — CN/DN cannot fix; B2BA out without D16 |

**Patterns to extend (do not invent parallel tax engines):**

- Tax: only `compute_document_totals` (+ FE `tax.ts` parity)
- Returns: **rewrite** row builders in `reporting/gst_returns.py` for rate-wise shape; keep disclaimer until GSTN JSON is certified
- Filing integrity: builders read **line snapshots only** (`item.hsn_code`, `item.uqc_code`) — never live `Product` / `Unit` masters for filed periods
- E-Invoice / E-Way: keep prepare → (optional submit) → mark-generated state machine already on `SalesInvoice` / `DeliveryChallan`
- Permissions: reuse `CanExport` / `CanViewFinancialReports`; Owner/Admin for live NIC credentials and identity-amend allowlist
- Numbers / immutability: completed money stays immutable; identity fields use D16 allowlist; value corrections stay CN/DN

---

## 1. Locked product decisions

| # | Decision | Lock |
|---|----------|------|
| D1 | Phase 2 ships **export aids + readiness**, not “one-click GSTN filing” | Portal upload / GSP auto-file is optional Wave 2.0b only after CA schema sign-off |
| D2 | **GSTR-1 / GSTR-3B first**; GSTR-9 is Wave 2.4 | Monthly cycle unblocks weekly CA value; annual waits for clean months |
| D3 | Offline BizBoard JSON/XLSX remains the default; **GSTN-compatible JSON** is an explicit sub-deliverable with golden fixtures from a CA | Feature flag **defaults off in prod**; disclaimer text is driven from the **same flag** so they cannot drift |
| D4 | **GSTIN verification** = cacheable lookup (name, status, state, taxpayer type) via approved provider/GSP; never invent portal scraping | Soft-fail: allow save with `UNVERIFIED` + Health alert |
| D5 | **Reverse charge** is purchase **header** flag; feeds GSTR-3B 3.1(d) via **separate memo tax fields** | `grand_total` stays supplier-payable (= taxable for RCM MVP); `rcm_cgst` / `rcm_sgst` / `rcm_igst` are memo-only — never overload `cgst_total`/`sgst_total`/`igst_total` (see §3.4) |
| D6 | **Tax-inclusive** is a price mode, not a second tax engine | Extract tax **once from the discounted line gross** (not per-unit), then feed exclusive amounts into `compute_document_totals`; store `price_mode` + entered inclusive unit price |
| D7 | E-Invoice = **B2B GST invoices** first (threshold/config later); CN/DN e-Invoice = Wave 2.2b | Reuse existing `einvoice_status` / `irn` / `einvoice_qr` / ack fields |
| D8 | E-Invoice live submit uses a **pluggable IRP/GSP adapter**; sandbox + production credentials per company | Prepare-only remains available when credentials absent (today’s UX) |
| D9 | E-Way = invoice + delivery challan; threshold helpers warn (≥ ₹50k interstate default — **configurable**) | Cancel/update validity via adapter; store `eway_bill_no` / `eway_valid_upto` / status |
| D10 | QR on Tax Invoice PDF only when `einvoice_status=GENERATED` and QR payload present | No fake QR |
| D11 | GST Health Dashboard is **read-derived** from documents + master data — no separate “compliance ledger” tables in 2.0 | Materialize later only if slow |
| D12 | Composition dealers: Regular GSTR-1/3B packs **hidden/disabled**; onboarding states composition return aids are **not** in Phase 2 | CMP-08 / GSTR-4 = **Phase 2.5 / later** — gating only in 2.0 (GST-009); do not silently imply composition filing support |
| D13 | No double-entry GL, Tally sync, multi-warehouse, **multi-GSTIN / multi-state registration under one Company**, or auto-payment of GST liability | One `Company.gstin` only; growing pilots that need multiple GSTINs need multi-company (later) — call this out in onboarding |
| D14 | Permissions: export stays on `can_export`; live NIC submit + credential settings + D16 identity amend = Owner/Admin only | Staff may prepare/download payloads if `can_export` |
| D15 | Sales Returns remain stock docs; **GSTR CDNR uses Sales CN/DN**, not returns | Aligns with Phase 1 D1/D9 |
| D16 | **Identity / POS correction path (required):** Owner-amend allowlist on completed sales invoices for `customer` relink is **out**; allow amending snapshotted **party GSTIN** and **place-of-supply / party state** used for filing, with `AuditLog` + Health | Default = option (a). B2BA/CDNRA tables = 2.0b only if CA rejects allowlist. Manual CA-pack workaround alone is **not** acceptable silence. CN/DN remain for **value** only |
| D17 | **GSTR-1 B2B / B2CL / CDNR / CDNUR are rate-wise** (one row per invoice × tax rate, from line aggregates) | Current header-level `_invoice_rows` / `_note_row` are **wrong** and must be rewritten before CA sign-off of exports |
| D18 | **Filing-line snapshots:** every GST-relevant document line stores `hsn_code` + `uqc_code` frozen at Complete (or earlier at line save); returns builders never resolve live Product HSN | Sales/Purchase invoice lines already snapshot `hsn_code` + free-text `unit_name` — extend with `uqc_code`, add same fields to CN/DN (+ purchase twins), migrate |
| D19 | **Invoice-value reconciliation for GSTR:** BEFORE Wave 2.0 export rewrite lands, lock Q9 | Default for 2.0: Health Critical `INVOICE_VALUE_MISMATCH` + exclude mismatched invoices from GSTN-shaped sections / issues strip; **warn** on Complete for B2B GST when `additional_charges ≠ 0` or `AFTER_TAX` discount ≠ 0 (BUG-205: charges never GST-rated). Prefer disallow (b) if CA workshop agrees — do not invent rate-wise charge allocation (a) without CA |
| D20 | Missing HSN on GST Complete: **warn** (non-blocking) + Health `HSN_MISSING` Critical | Hard-block would strand existing pilot drafts/data; warn is enough for 2.0 |
| D21 | GSP procurement is a **Wave 2.0 parallel track**, not a Wave 2.2 start item | Q1/Q6 paperwork begins with §13 slice |

---

## 2. Scope split — waves

### Phase 2.0 — Filing integrity + returns export aids + GST Health

**Schema / integrity first (before builders):**

- Line snapshot: `hsn_code` + `uqc_code` on all GST filing lines (invoice + CN/DN sales & purchase)
- `Unit.uqc_code` + seeded GSTN UQC list + mapping UX
- `GstReturnPeriod` + `GstReturnSnapshot` (payload + content hash + builder version)
- D16 Owner identity-amend for party GSTIN / POS

**Then builders:**

- **Rewrite** GSTR-1 B2B / B2CL / CDNR to rate-wise line aggregates; add CDNUR, HSN Table 12 (qty + UQC), Docs detail, NIL/exempt best-effort
- Harden GSTR-3B: purchase CN/DN netting; RCM stub until 2.1
- Invoice-value mismatch handling per D19 / Q9
- Period soft-close (warn-only) + `PERIOD_CHANGED_AFTER_SNAPSHOT`
- **GST Health Dashboard** + full alert catalog (§5)
- CA pack zip
- Composition gating (Regular packs only) + onboarding honesty for CMP-08
- **GSP procurement track** (non-eng)

### Phase 2.1 — Tax modes + GSTIN live verification

- Reverse charge with **memo fields** (§3.4)
- Tax-inclusive mode (locked algorithm §3.3)
- GSTIN verify service + UI
- Feed 3B 3.1(d) from real RCM memo fields

### Phase 2.2 — E-Invoice (IRN + QR)

- Assumes sandbox credentials already obtained in 2.0 track
- IRP/GSP adapter (sandbox → prod)
- Submit / cancel IRN; PDF QR; compliance panel
- Optional CN/DN IRN (2.2b)

### Phase 2.3 — E-Way Bill

- NIC/GSP adapter; invoice + challan; transporter fields; Health expiry alerts
- Optional post-IRN e-Way

### Phase 2.4 — GSTR-9 annual aid

- Aggregate from hashed monthly snapshots; XLSX worksheets; CA disclaimer

### Phase 2.5 (explicitly later — not in core calendar)

- Composition CMP-08 / GSTR-4 aids
- B2BA/CDNRA tables (only if D16 allowlist insufficient)
- Multi-GSTIN / multi-company filing

**Rationale for order:** Line snapshots + rate-wise builders + Health catch data defects that poison IRP and CA packs. GSP paperwork runs in parallel so 2.2 is eng-bound, not vendor-bound. Tax modes before honest 3B RCM. Live NIC last.

---

## 3. Architecture

```text
                    ┌─────────────────────────┐
                    │  Masters (Customer /     │
                    │  Supplier / Company)     │
                    │  Unit.uqc_code           │
                    │  + GstinVerificationCache│
                    └───────────┬─────────────┘
                                │ snapshot at line save / Complete
┌───────────────┐      ┌────────▼────────┐      ┌──────────────────────┐
│ Billing docs  │─────▶│ compute_document │─────▶│ Totals + line         │
│ INV/CN/DN     │      │ _totals          │      │ hsn_code / uqc_code   │
│ (+ RCM memo,  │      │ (+ inclusive     │      │ frozen for filing     │
│  inclusive)   │      │  extract)        │      └──────────┬───────────┘
└───────┬───────┘      └─────────────────┘                 │
        │                                                   │
        ├──────────────▶ reporting/gst_returns.py ◀─────────┤
        │                rate-wise build_gstr1 / 3b / 9     │
        │                + GstReturnSnapshot (hash+version) │
        │                + gst_health                       │
        │                                                   │
        ├──────────────▶ sales/einvoice_payload.py          │
        │                → GstComplianceService.submit_irn  │
        │                                                   │
        └──────────────▶ sales/eway_payload.py              │
                         → GstComplianceService.submit_eway │
```

### 3.1 New modules (proposed)

| Module | Responsibility |
|--------|----------------|
| `backend/compliance/` (new app) **or** `core/services/gst_compliance.py` | Health checks, GSTIN verify client, IRP/EWB adapters, credential encryption |
| `reporting/gst_returns.py` (rewrite + extend) | Rate-wise return builders + snapshot writer |
| `reporting/gst_health.py` (new) | Pure functions → alert list for a company/period |
| `web/src/pages/reports/GstHealthPage.tsx` | Dashboard UI |
| `web/src/pages/settings/GstComplianceSettingsPage.tsx` | GSP credentials, thresholds, e-Invoice auto flags, AATO |

Prefer **`core/services` + `reporting`** first if an app is overkill; introduce `compliance` app when adapters + models exceed ~4 files.

### 3.2 Data model additions (Phase 2)

```text
# Company (settings)
einvoice_enabled: bool
eway_enabled: bool
eway_threshold_amount: Decimal  # default 50000
aato_turnover: Decimal | null   # aggregate annual turnover — drives e-Invoice mandatory + HSN digit hints
gsp_provider: str               # NONE | SANDBOX | <provider>
# secrets via encrypted Credential model — never plain CharField in Company

# masters.Unit
uqc_code: CharField  # GSTN UQC (NOS, KGS, PCS, MTR, BOX, …); blank = unmapped

# Customer / Supplier
gstin_verification_status: UNVERIFIED | VALID | INVALID | CANCELLED | SUSPENDED
gstin_legal_name: str
gstin_verified_at: datetime | null
gstin_raw_payload: JSONField    # retention + access per Phase 0 DPDP (E10) — see §9

# Document lines (Sales/Purchase invoice items already have hsn_code + unit_name)
# ADD to invoice items + ALL CN/DN items (sales & purchase):
uqc_code: CharField             # frozen GSTN UQC at line save/Complete
# CN/DN also need hsn_code (+ unit_name optional) — invoice items already have hsn_code

# Sales invoice identity snapshots used for filing (D16)
# Prefer explicit fields if customer FK change is forbidden:
party_gstin_snapshot / place_of_supply  # or amend path that writes filing overlays + audit

# Purchase header (2.1)
is_reverse_charge: bool
rcm_cgst / rcm_sgst / rcm_igst / rcm_taxable  # memo only; grand_total excludes these

# Sales/Purchase header
price_mode: EXCLUSIVE | INCLUSIVE

# Return period control (own ticket GST-011)
GstReturnPeriod(company, period YYYY-MM, status OPEN|SOFT_CLOSED|CLOSED,
                closed_at, closed_by)

# Monthly snapshot for audit / GSTR-9 (GST-005)
GstReturnSnapshot(
  company, return_type, period, payload JSON,
  content_hash,           # sha256 of canonical payload bytes
  builder_version,        # e.g. "gstr1@2.0.3"
  generated_at, generated_by
)
```

E-Invoice / E-Way status fields **already exist** on `SalesInvoice` and `DeliveryChallan` (`migrations/0008_phase2_einvoice_eway.py`) — do not re-add.

### 3.3 Tax-inclusive algorithm (D6) — locked shape

**Lock before GST-102 (no “OR”):**

```text
For each line with price_mode=INCLUSIVE:
  1. line_gross_inclusive = q2(qty × entered_unit_price_inclusive)
  2. discount_amt = q2(line_gross_inclusive × discount_percent / 100)
  3. net_inclusive = q2(line_gross_inclusive − discount_amt)
  4. taxable = q2(net_inclusive × 100 / (100 + gst_rate))   # extract ONCE from discounted gross
  5. Derive exclusive unit_price for persistence / compute_document_totals
     such that existing exclusive pipeline reproduces `taxable` (parity fixture).
```

**Invoice-level `BEFORE_TAX` discount:** after line taxables exist (exclusive pipeline), allocate the document discount **proportionally across line taxables** exactly as today’s exclusive `BEFORE_TAX` path — then recompute tax. Inclusive + `BEFORE_TAX` must be a named case in the shared Phase 0 CA parity fixture (extend the existing 8 scenarios; do **not** invent a second fixture file).

`AFTER_TAX` invoice discount on inclusive docs: same as exclusive — does not change taxable; triggers D19 / `INVOICE_VALUE_MISMATCH` rules for GSTR.

CA signs the inclusive formula before FE ships. Parity: `test_billing_totals.py` + `tax.test.ts` + shared fixture.

### 3.4 Reverse charge (D5) — memo fields only

**Do not** put RCM tax into `cgst_total` / `sgst_total` / `igst_total` / `grand_total`. Those fields feed payables, allocation caps, PDFs, and registers that assume:

```text
grand_total ≈ f(taxable_total, cgst, sgst, igst, charges, discount, round_off)
```

**Locked MVP:**

```text
is_reverse_charge = True
grand_total / payable  = goods (and non-RCM) amount only  # typically taxable + non-tax charges per CA
rcm_taxable, rcm_cgst, rcm_sgst, rcm_igst  = memo liability for GSTR-3B 3.1(d) only
```

Schema lands in **GST-101** (not discovered in GST-104). GSTR-3B builder reads memo fields; ITC available excludes RCM unless CA marks eligible.

### 3.5 GSTIN verification

```text
POST /api/v1/masters/customers/{id}/verify-gstin/
POST /api/v1/masters/suppliers/{id}/verify-gstin/
POST /api/v1/company/verify-gstin/

→ GstinVerificationService.verify(gstin) → provider
→ upsert cache fields; emit audit event
→ rate-limit per company
```

```python
class GstinProvider(Protocol):
    def lookup(self, gstin: str) -> GstinLookupResult: ...
```

Ship `NullGstinProvider` (dev) + one real provider behind env keys. UI: badge Valid/Invalid + “Verify” button; Health lists stale (>90 days) verifications.

### 3.6 E-Invoice / E-Way adapter

Keep today’s flow:

1. `prepare-einvoice` → validate + JSON payload + `READY`
2. `submit-einvoice` (**new**) → IRP → `GENERATED` + IRN/ack/QR **or** `FAILED`
3. `mark-einvoice-generated` remains for **manual** IRN paste when no GSP
4. `cancel-einvoice` (**new**) within IRP rules

Same pattern for e-Way. Never call NIC synchronously from Complete without `auto_generate_einvoice`; default **manual**.

PDF: extend `gst_tax_invoice.py` to render QR image from `einvoice_qr` when present.

### 3.7 Identity / POS amend (D16)

Phase 0 immutability + Phase 1 CN/DN leave **no path** for wrong customer GSTIN or wrong place of supply. A credit note cannot fix a B2B row filed under the wrong CTIN/POS.

**Wave 2.0 (GST-012):** Owner/Admin action e.g. `POST /sales/invoices/{id}/amend-filing-identity/` with allowlisted fields:

- Party GSTIN used for filing (snapshot / overlay)
- Place of supply / party state code

Rules:

- AuditLog before/after; reason required
- Does **not** change money totals, stock, or allocations
- If a `GstReturnSnapshot` exists for that period → emit `PERIOD_CHANGED_AFTER_SNAPSHOT` and mark period dirty
- CA pack lists amended invoices

If CA later requires formal B2BA/CDNRA export tables, schedule **2.0b** — do not leave pilots with “use CN/DN” as the answer.

---

## 4. GSTR export aids — detailed scope

### 4.1 GSTR-1 (Wave 2.0) — treat current builder as scaffold

| Section | Current code | Phase 2.0 requirement |
|---------|--------------|------------------------|
| B2B | ❌ Header-level one row / invoice (`_invoice_rows`) | **Rewrite** — rate-wise rows from `invoice.items` aggregated by `gst_rate` (multi-rate F8 → multiple rows); `invoice_value` rules per D19 |
| B2CL | ❌ Header-level | **Rewrite** — rate-wise; configurable ₹2.5L threshold |
| B2CS | ✅ Already rate × POS buckets | Keep; ensure uses line snapshots |
| CDNR | ❌ Header-level (`_note_row`) | **Rewrite** — rate-wise from note lines; reason → note type documented |
| CDNUR | Missing | **Add** — rate-wise |
| HSN (Table 12) | Missing | **Add** — HSN × rate × supply type + **qty + UQC**; lines without HSN/UQC → Health + issues strip |
| Docs (Table 13) | Thin `docs` dict | Deepen issued/cancelled counts |
| NIL / Exempt | Missing | Best-effort from 0% / NON_GST + disclaimer |
| EXP / SEZ | Not modeled | **Out** |
| Amendments (B2BA/CDNRA) | Missing | **Not** “use CN/DN”. Identity → D16 allowlist; formal B2BA tables → 2.0b if needed |

**Deliverables:**

- Rate-wise `build_gstr1` + XLSX sheets that a CA can reconcile rate-wise
- Optional `format=gstn-json` behind flag (off in prod) + same-flag disclaimer
- UI: section tabs + issues strip (excluded docs + why: mismatch, missing HSN, etc.)

### 4.2 GSTR-3B (Wave 2.0 → 2.1)

| Section | Wave |
|---------|------|
| 3.1(a) Outward taxable (net of CN/DN, rate-consistent with GSTR-1) | 2.0 |
| 3.1(d) RCM inward from memo fields | 2.1 |
| 4(A) ITC from non-RCM purchases | 2.0 net purchase CN/DN |
| 4(B) ITC reverse / ineligible | manual_review + Health |
| Net payable hint | Indicative disclaimer |

### 4.3 GSTR-9 (Wave 2.4)

- FY selector; worksheets from hashed monthly snapshots; fallback re-agg
- DoD: annual XLSX reconciles to 12× monthly GSTR-1 totals within tolerance

---

## 5. GST Health Dashboard + alerts

### 5.1 Alert catalog

| Code | Severity | Rule |
|------|----------|------|
| `GSTIN_MISSING_COMPANY` | Critical | Registered company without GSTIN |
| `GSTIN_INVALID_FORMAT` | Critical | Fails `validate_gstin` |
| `GSTIN_UNVERIFIED` | Warning | No successful verify in 90 days |
| `PARTY_GSTIN_MISSING_B2B` | Warning | Large B2C mis-class risk — optional threshold |
| `HSN_MISSING` | Critical | Completed GST doc line without snapshotted HSN (Complete **warns**, does not hard-block — D20) |
| `HSN_DIGITS_INSUFFICIENT` | Warning | HSN length below turnover rule (4 vs 6); `validate_hsn` is format-only |
| `POS_UNKNOWN` | Critical | Completed GST doc without POS |
| `RATE_NONSTANDARD` | Warning | Rate not in `ALLOWED_GST_RATES` |
| `INVOICE_VALUE_MISMATCH` | Critical | `grand_total` not reconciling to taxable+taxes under GSTR rules (AFTER_TAX discount / `additional_charges` / round-off policy) — the check GSTN will fail |
| `UQC_UNMAPPED` | Warning | Line/unit without GSTN `uqc_code` → Table 12 invalid |
| `EINVOICE_PENDING` | Warning | B2B GST complete, `einvoice_enabled`, status not GENERATED |
| `EINVOICE_MANDATORY_NOT_ENABLED` | Critical | Company `aato_turnover` (or config) above e-Invoice threshold but `einvoice_enabled` is false — statutory penalty case; must **not** depend on the flag being on |
| `EWAY_PENDING` | Warning | Interstate goods invoice/challan over threshold, not GENERATED |
| `EWAY_EXPIRED` | Critical | `eway_valid_upto` < now and dispatch open |
| `GSTR_PERIOD_OPEN` | Info | Previous month still OPEN after filing due date (config) |
| `PERIOD_CHANGED_AFTER_SNAPSHOT` | Critical | Document completed/amended in a period that already has an export snapshot — makes warn-only soft-close defensible |
| `RCM_UNFLAGGED_HINT` | Info | Unregistered supplier + services HSN heuristic (soft) |

### 5.2 API / UI

```text
GET /api/v1/reports/gst-health/?period=YYYY-MM
→ { summary: {critical, warning, info}, alerts: [...], links to documents }

UI route: Reports → GST Health
Each alert row → deep link to invoice/customer
```

No email spam in 2.0; optional Owner weekly digest in 2.1.

---

## 6. Work breakdown (tickets)

Points ≈ solo senior full-stack hours/2 (same scale as Phase 1).  
**`Depends` column = within-wave ordering hints only.** §13 is the authority for cross-cutting slice order (Health may start before builders finish).

### Wave 2.0 — Integrity + Returns + Health (~55–68 pts)

| ID | Title | Pts | Depends (within wave) |
|----|-------|-----|------------------------|
| GST-000 | **Line filing snapshots:** `hsn_code` + `uqc_code` on CN/DN (+ ensure invoice lines); Complete freeze; builders must use line fields only; best-effort backfill | 5 | — **first** |
| GST-000b | **UQC master:** seed GSTN UQC list; `Unit.uqc_code`; map existing units; migration for free-text `unit_name` → UQC where obvious | 5 | GST-000 |
| GST-011 | **`GstReturnPeriod`:** OPEN / SOFT_CLOSED / CLOSED; close/reopen; permissions; backdate Complete check | 5 | — |
| GST-012 | **D16 identity amend** (party GSTIN + POS) + AuditLog + period-dirty | 5 | GST-011 |
| GST-001 | **Rewrite GSTR-1 B2B/B2CL rate-wise** + `invoice_value` / D19 mismatch handling + multi-rate tests (F8) | 8 | GST-000 |
| GST-002 | **Rewrite CDNR rate-wise** + CDNUR + Docs detail + NIL/exempt; HSN Table 12 with **qty + UQC** | 8 | GST-000, GST-000b, GST-001 |
| GST-003 | GSTR-3B purchase CN/DN netting + clearer sections | 3 | Phase 1 purchase notes |
| GST-004 | Return “data quality” / issues strip (excluded docs + reasons) | 3 | GST-001 |
| GST-005 | `GstReturnSnapshot` persist on export: payload + **content_hash** + **builder_version** + regenerate | 5 | GST-001, GST-011 |
| GST-006 | GST Health service + API + full alert catalog (§5.1) | **13** | GST-000 helpful |
| GST-007 | GST Health FE dashboard + nav + i18n | 5 | GST-006 |
| GST-008 | CA pack zip export | 3 | GST-001..003 |
| GST-009 | Composition gating for Regular GSTR UI + onboarding “no CMP-08 yet” copy | 2 | — |
| GST-010 | CA fixture review + golden JSON/XLSX samples (incl. multi-rate) | 3 | GST-001..003 |
| GST-013 | Company `aato_turnover` field + settings UX (feeds `EINVOICE_MANDATORY_NOT_ENABLED` / HSN digits) | 2 | — |
| GST-014 | **GSP procurement track** (PM): vendor shortlist, contract, KYC, sandbox creds — **0 eng pts**, calendar parallel | 0 | starts with wave |

### Wave 2.1 — Modes + GSTIN (~28–34 pts)

| ID | Title | Pts | Depends (within wave) |
|----|-------|-----|------------------------|
| GST-101 | Schema: `is_reverse_charge`, **`rcm_*` memo fields**, `price_mode`, verification fields | 5 | — |
| GST-102 | BE tax-inclusive derivation (discounted line gross) + BEFORE_TAX allocation + parity fixture cases | 8 | GST-101; Q3 frozen |
| GST-103 | FE tax-inclusive toggle on Sales/Purchase editors | 5 | GST-102 |
| GST-104 | RCM purchase complete rules; payable uses `grand_total` only; memo unused by ledger | 5 | GST-101; Q2 frozen |
| GST-105 | GSTR-3B 3.1(d) from `rcm_*` memo fields | 3 | GST-104 |
| GST-106 | `GstinProvider` + verify endpoints + cache (DPDP retention) | 5 | — |
| GST-107 | FE verify badges on Customer/Supplier/Company | 3 | GST-106 |
| GST-108 | Health alerts for verification + RCM | 2 | GST-006, GST-106 |

### Wave 2.2 — E-Invoice (~30–38 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| GST-201 | Encrypted GSP credentials model + settings UI | 5 | GST-014 sandbox available |
| GST-202 | IRP adapter interface + sandbox fake + one provider | 8 | GST-201 |
| GST-203 | `submit-einvoice` / `cancel-einvoice` actions + tests | 5 | GST-202 |
| GST-204 | PDF QR render + invoice compliance panel FE | 5 | fields exist |
| GST-205 | Readiness gates + Health e-Invoice alerts | 3 | GST-006, GST-013 |
| GST-206 | CN/DN e-Invoice (optional 2.2b) | 8 | GST-203 |

### Wave 2.3 — E-Way (~22–28 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| GST-301 | Transporter/vehicle/distance fields on invoice/challan | 3 | — |
| GST-302 | EWB adapter + submit/cancel | 8 | GST-201 |
| GST-303 | FE prepare/submit UX on Invoice + Challan detail | 5 | GST-302 |
| GST-304 | Threshold warnings + Health e-Way alerts | 3 | GST-006 |
| GST-305 | Optional post-IRN e-Way generate | 3 | GST-203, GST-302 |

### Wave 2.4 — GSTR-9 (~16–20 pts)

| ID | Title | Pts | Depends |
|----|-------|-----|---------|
| GST-401 | FY aggregator from snapshots/documents | 8 | GST-005 |
| GST-402 | GSTR-9 XLSX worksheets + API | 5 | GST-401 |
| GST-403 | FE annual page + disclaimer | 3 | GST-402 |

**Core exit (2.0+2.1 without live NIC):** ~83–102 pts ≈ **8–9 weeks**  
**Full Phase 2 including IRN/EWB/GSTR-9:** ~145–180 pts ≈ **14–18 weeks** eng (+ GSP overlap)

---

## 7. Frontend surfaces

| Route / area | Work |
|--------------|------|
| Reports → GSTR-1 / GSTR-3B | Section tabs, issues strip, CA pack, composition gate, mismatch badges |
| Reports → GST Health | New |
| Reports → GSTR-9 | New (2.4) |
| Settings → GST | Verify company GSTIN; e-Invoice/e-Way toggles; thresholds; **AATO** |
| Settings → GST Compliance (GSP) | Credentials (Owner only) |
| Settings → Units | UQC mapping |
| Customers / Suppliers | Verify badge + legal name from GSTN |
| Sales/Purchase editors | Tax-inclusive toggle; RCM checkbox (purchase); HSN warn on Complete |
| Invoice detail | E-Invoice / E-Way panel; **Amend filing identity** (Owner) |
| Challan detail | E-Way panel |
| Tax Invoice PDF | QR when generated |

Reuse MUI patterns from `GstReturnPage` and `GstSettingsPage`. Wire via `web/src/api/resources.ts` + `types/domain.ts` + `navigation/menu.ts`.

---

## 8. Testing strategy

| Layer | Must cover |
|-------|------------|
| Unit | Inclusive extract from discounted gross; RCM memo ≠ payable; each GSTR section **rate-wise**; health rules; UQC mapping |
| API | Export permissions; verify-gstin rate limit; identity amend audit; submit-einvoice; period bounds |
| Golden fixtures | CA-provided month → expected GSTR-1 section totals incl. **multi-rate (F8)** (`backend/tests/fixtures/gst/`) |
| **Reconciliation invariant (mandatory)** | Per company × period: `sum(B2B + B2CL + B2CS taxable) − sum(CDNR + CDNUR taxable) == sales register taxable for the period` (same exclusions as issues strip). This is the test that catches header-level B2B and silent drops — maps to §14 support metric |
| Snapshot integrity | Re-export → same `content_hash` when docs unchanged; builder_version bump changes hash policy documented |
| FE | Tax inclusive parity with BE; Health empty/critical states |
| E2E | Complete multi-rate B2B GST invoice → rate-wise GSTR-1 rows → Health clean HSN/UQC |
| Sandbox | IRP/EWB against provider sandbox before prod credentials |

**Do not** claim GSTN JSON upload support without fixture pass + CA written sign-off.

---

## 9. Security & ops

| Topic | Rule |
|-------|------|
| GSP secrets | Encrypted at rest; decrypted only in worker/request for submit; never in list serializers |
| Audit | Log verify, identity amend, IRN submit/cancel, e-Way submit/cancel with company + user |
| Third-party business data | `gstin_raw_payload` is in scope of Phase 0 **DPDP minimum (E10)** — retention period, Owner/Admin read, Staff redaction; not a new one-off PII policy |
| Rate limits | Verify + IRP submit throttles per company |
| Failure UX | IRP downtime must not block billing Complete (unless company opted into hard-block) |
| Disclaimers / flags | GSTN JSON flag **off in prod** by default; UI disclaimer bound to the same setting |
| GSP track | Owner/PM owns GST-014 calendar; eng unblocked for 2.0/2.1 without prod creds |

---

## 10. Risk register

| Risk | Mitigation |
|------|------------|
| Treating scaffold GSTR-1 as “done” | D17; GST-001/002 rewrite; reconciliation invariant test |
| Product HSN edit rewrites filed months | GST-000 line snapshots; builders ignore Product FK for HSN/UQC |
| `invoice_value` ≠ taxable+tax | D19 / Q9; `INVOICE_VALUE_MISMATCH`; BUG-205 honesty |
| Claiming portal-ready JSON too early | D1/D3; flag off in prod; CA fixtures |
| Inclusive tax paise drift FE/BE | Locked §3.3; extend Phase 0 shared fixture |
| RCM breaks payable invariant | Memo fields D5/§3.4 in GST-101 |
| No path for wrong GSTIN/POS | D16 / GST-012 — not “use CN/DN” |
| GSP vendor delay starves 2.2 | GST-014 starts in Wave 2.0 |
| GSP vendor lock-in | Adapter Protocol; prepare+manual mark always works |
| NIC schema churn | Version pin payload builders; adapter tests |
| Health alert fatigue | Critical/Warning in nav badge first |
| Composition dealers expect filing aids | D12; GST-009 gating + onboarding; CMP-08 = 2.5 |
| Multi-GSTIN mid-year outgrow | D13 explicit |
| Soft-close without dirty detection | `PERIOD_CHANGED_AFTER_SNAPSHOT` |
| Snapshot not auditable | content_hash + builder_version on GST-005 |
| Scope creep into full GL / tax payment | D13 |

---

## 11. Definition of Done

### Phase 2.0 exit (returns readiness — minimum valuable compliance)

- [ ] Line `hsn_code` + `uqc_code` snapshotted on invoice + CN/DN lines; GSTR builders never use live Product HSN
- [ ] UQC seed + `Unit.uqc_code`; `UQC_UNMAPPED` in Health
- [ ] GSTR-1 B2B / B2CL / CDNR / CDNUR are **rate-wise**; multi-rate fixture (F8) green
- [ ] HSN Table 12 includes quantity + UQC
- [ ] `INVOICE_VALUE_MISMATCH` handled per D19; issues strip lists exclusions
- [ ] Reconciliation invariant test green for golden month
- [ ] `GstReturnPeriod` + soft-close warn; `PERIOD_CHANGED_AFTER_SNAPSHOT` live
- [ ] Snapshots store payload + content_hash + builder_version
- [ ] D16 identity amend path live with audit
- [ ] GST Health dashboard with §5.1 alerts (incl. AATO / e-Invoice mandatory)
- [ ] Composition companies cannot download Regular packs; onboarding states no CMP-08
- [ ] CA pack zip; at least one CA golden month fixture
- [ ] GSP procurement track started (sandbox requested or vendor selected)
- [ ] Disclaimers unchanged: not GSTN auto-file; gstn-json flag off in prod

### Phase 2.1 exit

- [ ] Tax-inclusive mode with discounted-gross extract + BEFORE_TAX case in shared fixture
- [ ] RCM memo fields feed 3B 3.1(d); supplier payable ignores memo tax
- [ ] GSTIN verify on company/customer/supplier with DPDP-aware cache

### Phase 2.2 / 2.3 exit

- [ ] Sandbox IRN generate + QR on PDF for B2B GST invoice
- [ ] Manual mark-generated still works without GSP
- [ ] E-Way generate/cancel for invoice + challan over threshold
- [ ] Health alerts for pending/expired / mandatory-not-enabled statutory docs

### Phase 2.4 exit

- [ ] GSTR-9 FY XLSX aid reconciles to monthly snapshots within agreed tolerance
- [ ] CA written acknowledgment of annual aid scope

Explicitly **not** required for Phase 2 core:

- [ ] One-click GSTN filing / payment of tax
- [ ] GSTR-2A/2B auto-reconcile (**Phase 2.5** compliance track — not Payments Phase 3)
- [ ] CMP-08 / GSTR-4 (Phase 2.5)
- [ ] Formal B2BA/CDNRA tables (2.0b only if D16 rejected)
- [ ] Export/SEZ invoice types
- [ ] Multi-GSTIN under one Company / multi-GSP marketplace
- [ ] Double-entry / GST ledgers as books of account

---

## 12. Open questions (resolve before the named wave)

| # | Question | Default | Freeze before |
|---|----------|---------|---------------|
| Q1 | Which GSP/IRP provider for v1? | Shortlist in Wave 2.0 (GST-014); sandbox fake until contract | **Start 2.0**; need answer before 2.2 eng |
| Q2 | Does RCM tax inflate purchase `grand_total` / supplier payable? | **No** — `rcm_*` memo only (§3.4) | 2.1 / GST-101 |
| Q3 | Inclusive: discount + extract + invoice `BEFORE_TAX`? | Discount on inclusive gross → extract once from net inclusive; `BEFORE_TAX` allocates on exclusive taxables like today; add to shared CA fixture | **Before GST-102** |
| Q4 | Hard-block Complete when e-Invoice required but IRP down? | **No** — warn + Health | 2.2 |
| Q5 | GSTN JSON in 2.0? | XLSX + BizBoard JSON; GSTN JSON behind flag **default off in prod**; disclaimer tied to flag | 2.0 |
| Q6 | GSTIN verify provider (same GSP or cheaper master API)? | Prefer same credentials; decide in GST-014 | Start 2.0 |
| Q7 | E-Way for intra-state above threshold? | Configured rules; default interstate focus | 2.3 |
| Q8 | Period soft-close in 2.0? | **Yes, warn-only**, justified by `PERIOD_CHANGED_AFTER_SNAPSHOT` | 2.0 / GST-011 |
| Q9 | AFTER_TAX discount / `additional_charges` vs GSTR `invoice_value`? | **2.0 default (c)+(warn):** Critical Health + exclude from GSTN-shaped export; warn on B2B GST Complete. Workshop may upgrade to **(b) disallow** on new B2B GST Completes. **(a) rate-wise modeling** only with CA — blocked by BUG-205 until charges are taxed | **Before GST-001** |
| Q10 | D16 allowlist vs build B2BA in 2.0? | **Allowlist (a)** in 2.0; B2BA = 2.0b if CA rejects | 2.0 / GST-012 |
| Q11 | AATO source: manual field vs computed from books? | Manual `aato_turnover` on Company for 2.0 (GST-013); computed later | 2.0 |

---

## 13. First implementation slice (authority for ordering)

§6 `Depends` are within-wave only. **This section wins** when they disagree.

### Engineering

1. **GST-000 / GST-000b** — line HSN+UQC snapshots + UQC master (**highest leverage; before any builder rewrite**)  
2. **GST-006 / GST-007 / GST-013** — Health dashboard (surfaces mismatch / missing HSN / UQC / AATO immediately; can proceed in parallel with builder rewrite once GST-000 landed)  
3. **GST-011 / GST-012 / GST-005** — periods, identity amend, hashed snapshots  
4. **GST-001 / GST-002** — rate-wise GSTR-1 rewrite + Table 12 (after Q9 freeze)  
5. **GST-003 / GST-004 / GST-008** — 3B netting, issues strip, CA pack  
6. **GST-009 / GST-010** — composition honesty + CA golden fixture (stop if fixtures fail)  
7. Wave 2.1 → 2.2/2.3 → 2.4 as gated above  

### Non-engineering (starts Day 1 with step 1)

- **GST-014** — GSP/IRP (+ GSTIN verify) vendor selection, contract, KYC, sandbox credentials  
- Target: sandbox keys in hand before Wave 2.2 engineering starts  

---

## 14. Success metrics (pilot graduate)

| Metric | Target |
|--------|--------|
| CA time to draft monthly GSTR-1 from BizBoard | ≤ 30 minutes for ≤ 200 B2B invoices |
| Health Critical count for active GST company | 0 before period soft-close |
| Reconciliation invariant | Green in CI for golden + pilot sample months |
| IRN success rate (sandbox then prod) | ≥ 95% of prepare-READY invoices |
| Support tickets “GSTR numbers don’t match register” | Downward trend vs pre-Phase-2 (invariant test is the engineering control) |
| GSP sandbox ready before 2.2 eng start | Yes |

---

## 15. Review changelog (2026-08-02)

Incorporated external plan review:

1. Reclassified GSTR-1 scaffold as **not done**; rate-wise rewrite + invoice_value / D19  
2. UQC master + Table 12 qty; HSN warn-on-Complete  
3. GST-000 line snapshots before builders; snapshot hash/version; period dirty alert  
4. D16 identity amend (wrong GSTIN/POS) — roadmap gap closed  
5. RCM memo fields; inclusive extract locked to discounted line gross + BEFORE_TAX in shared fixture  
6. GSP procurement in Wave 2.0; GST-006 → 13 pts; 2.0+2.1 → 8–9 weeks  
7. Five Health alerts added; composition = gate only (+ 2.5 later)  
8. Mandatory GSTR ↔ sales-register reconciliation test  
9. GstReturnPeriod ticket; multi-GSTIN in D13; §13 authoritative ordering; Q5 flag/disclaimer coupling; DPDP for verify payload  

---

*This plan implements product Phase 2 GST returns readiness after Phase 1 document completeness. It does not replace Phase 0/1 gates.*
