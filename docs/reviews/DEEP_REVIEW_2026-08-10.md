# Bizboard — Deep Code Review (GST Correctness & Indian SMB Usability)

**Date:** 2026-08-10
**Branch reviewed:** `wip/phase0` (HEAD `c371d61`)
**Reviewers:** 8 parallel full-file deep-read passes (not a static-analysis skim) across backend (`E:\Bizboard\backend`) and frontend (`E:\Bizboard\web\src`), each briefed on Indian GST law specifics (place of supply, CGST/SGST/IGST split, HSN/UQC/e-Invoice/e-Way schemas, ITC/RCM, GSTR-1/3B/9, QRMP) and on usability expectations for Indian retailers/traders with limited technical literacy.
**Method note:** Every finding below is anchored to a file:line the reviewing pass actually opened and traced, not inferred from naming or docs. Three of the most severe claims (missing 40% GST slab, tenant-export/restore cross-tenant gap, POS idempotency-key bug) were independently re-verified against source by the compiling pass before inclusion. This is a fresh, from-the-code review — it was **not** derived from the pre-existing `docs/reviews/01–21_*.md` corpus, though a couple of findings below note where current code has since diverged from that corpus's older conclusions.

Severity definitions used throughout:
- **Critical** — wrong tax/money computed or filed, cross-tenant data exposure, or a workflow that is completely blocked/broken for a real, non-edge scenario.
- **High** — meaningful compliance gap, data-integrity risk, or a workflow that silently produces wrong results in common (not rare) scenarios.
- **Medium** — real gap or bug with a narrower blast radius, or a significant usability problem.
- **Low** — minor correctness/usability gap, edge case, or hardening suggestion.
- **Suggestion** — no defect; an improvement worth considering.

---

## Executive Summary

| Module | Critical | High | Medium | Low/Suggestion |
|---|---|---|---|---|
| 1. GST tax engine | 4 | 2 | 6 | 5 |
| 2. Sales documents | 2 | 1 | 5 | 2 |
| 3. Purchases & imports | 0 | 6 | 6 | 2 |
| 4. Payments & ledgers | 0 | 2 | 9 | 8 |
| 5. Inventory & masters | 1 | 2 | 3 | 5 |
| 6. Reporting / GSTR | 0 | 3 | 10 | 4 |
| 7. Accounts / core platform | 1 | 1 | 4 | 3 |
| 8. Frontend UX | 6 | 8 | 10 | 2 |
| **Total** | **14** | **25** | **53** | **31** |

**~123 findings.** The codebase is unusually disciplined in places that are easy to get wrong (Decimal-only money math, CGST/SGST paisa-split without drift, race-safe document numbering and stock updates, honest "not verified" labeling on GSTIN/e-invoice/GSTR features, structurally complete Hindi i18n). The Critical/High findings below are concentrated in a few specific themes, not scattered evenly — fixing those themes closes most of the risk.

### Must-fix-before-pilot (cross-module, ranked)

1. **[SEC-01] Tenant export/restore has no cross-tenant provenance check** — a leaked export file from Company A can be restored into Company B's account (full financial data breach). *Single highest-severity finding in this review.*
2. **[TAX-04] `ALLOWED_GST_RATES` is missing the 40% GST 2.0 slab** — blocks billing entirely for any sin/luxury-goods item at the current legal rate.
3. **[TAX-01] Free-text `state` fields are misread as GST state codes** whenever the first two characters happen to be digits (e.g. a PIN code pasted into the state field) — silently flips CGST+SGST ↔ IGST with no warning.
4. **[TAX-02] No place-of-supply code for exports/SEZ ("96 – Other Territory")** — export invoices either can't Complete, or get silently mis-stamped with the seller's own state as POS.
5. **[TAX-03] e-Invoice generation hard-requires a buyer GSTIN** — genuine export/SEZ invoices (which legitimately have no buyer GSTIN) can never get an IRN, despite the product modeling export supply types explicitly.
6. **[SALES-01] Credit/debit notes can silently re-price off the *current* price list / product GST rate** instead of the amount actually charged on the original invoice, when the API caller omits an explicit override — corrupts the correction's relationship to what was actually filed.
7. **[SALES-02] In-place invoice "amend" (H9-A) has no guard against an invoice that already has a live e-Invoice IRN** — a completed, IRN-stamped invoice can be silently re-priced with the stale IRN/QR still printed on the regenerated PDF.
8. **[INV-01] Switching inventory valuation method WAVG→FIFO with existing stock on hand can hard-block sales** of that stock (no cost-layer backfill) — a single settings change can freeze billing for real SKUs.
9. **[FE-01/FE-02] POS and Purchases checkout have no working idempotency-key protection** on the primary online path — a network blip + retry creates a duplicate invoice, double stock deduction, and double cash/payable.
10. **[FE-03] UPI button in POS marks the sale as paid immediately on tap**, with no QR shown and no confirmation step — money can be recorded as received before it actually is.
11. **[PUR-01] Accounting books post full Input GST regardless of the `itc_eligibility` flag**, permanently diverging books from the statutory ITC actually claimed.
12. **[PUR-02] Reverse-charge (RCM) and composition/unregistered-supplier handling are 100% manual** — nothing in the purchase flow infers or warns when RCM should apply or when a supplier is a composition dealer (who cannot legally charge GST at all).
13. **[GSTR-01] GSTR-3B Table 3.1 has no (a)/(b)/(c)/(d) split** (taxable/zero-rated/nil/non-GST all merged) and **Table 3.2 doesn't exist at all** — a CA cannot use these worksheets for their intended purpose without re-deriving the splits by hand.
14. **[FE-04] GSTIN/PAN/IFSC/PIN validators exist in the codebase but are wired into only one settings screen** — every customer/supplier/company-bank-detail entry point accepts malformed values, which then surface as an unhelpful generic "Validation failed." with no field-level detail.

---

## 1. GST Tax Engine

*Scope: `core/services/billing.py`, `place_of_supply.py`, `uqc.py`, `document_numbers.py`, `core/validators.py`, `core/services/gstin_verify.py`, `sales/einvoice_payload.py`, `sales/eway_payload.py`, `sales/cogs_service.py`, `ledgers/services.py`.*

### TAX-01 — `extract_state_code()` misreads free-text state input as a GST state code — **Critical**
**File:** `core/services/billing.py:108-122`
Any string whose first two characters are digits is accepted as a valid 2-digit GST state code — used for both real GSTINs *and* the free-text `Customer.state`/`Supplier.state` field (a plain `CharField`, no choices, no regex — `masters/models.py:66,130`). There is no check that the extracted 2 digits are one of the ~38 real state codes.
**Failure scenario:** A cashier (or a Tally/CSV import) enters `"110001, Karol Bagh, Delhi"` in the customer's state field instead of "Delhi". `extract_state_code` returns `"11"` — the real code for **Sikkim**, not Delhi (`"07"`). If the seller is also in Delhi, the intra-state comparison now fails and the invoice is silently charged **IGST instead of CGST+SGST**, with zero warning. The same heuristic feeds `sales/eway_payload.py:139` and `sales/einvoice_payload.py:104,144`, so the wrong code also lands in e-Way/e-Invoice filings.
**Fix direction:** Only treat a 2-digit prefix as a state code when the source is a real GSTIN (regex-validated) or an explicitly-validated `^\d{2}$` code from a known list. Resolve free-text `state` only via the name/abbreviation map, and reject/flag anything that doesn't map.

### TAX-02 — No place-of-supply code for exports/SEZ ("96 – Other Territory") — **Critical**
**File:** `core/services/billing.py:15-101` (`IN_STATE_NAME_TO_CODE`), consumed at `sales/services.py:510-528`
`SalesInvoice.SupplyType` explicitly models `SEZWP`, `SEZWOP`, `EXPWP`, `EXPWOP`, `DEXP` (export/SEZ invoicing is a first-class feature), but the state-name map has no entry for GST's standard export placeholder code `"96"`.
**Failure scenario:** A genuine export invoice for a foreign buyer (`customer.state = "New York, USA"`, no GSTIN) cannot resolve a state code. If `assume_local_state_for_blank_party` is off (the default), the invoice **cannot be completed at all**, with a nonsensical error telling the user to "set the customer's GSTIN or a valid state." If the flag is on, the invoice is silently stamped with the **seller's own state code** as place of supply — legally wrong for exports and a misfiled GSTR-1/e-Invoice record.
**Fix direction:** When `supply_type` is an export/SEZ/deemed-export type (or the customer's country ≠ India), short-circuit place-of-supply resolution to the fixed code `"96"`.

### TAX-03 — e-Invoice generation hard-requires a buyer GSTIN, breaking exports/SEZ — **Critical**
**File:** `sales/einvoice_payload.py:63-121, 220-238`
`validate_einvoice_readiness` unconditionally raises `"Customer GSTIN is required for e-Invoice (unregistered/B2C buyers are not supported)."` before the code ever reaches the branch that recognizes `SEZWP/SEZWOP/EXPWP/EXPWOP/DEXP` supply types. Under the real e-Invoice schema, export buyers legitimately have no GSTIN (`BuyerDtls.Gstin = "URP"`).
**Failure scenario:** A company above the e-Invoicing turnover threshold raises a genuine export invoice. e-Invoice generation is unconditionally blocked with a misleading error — the invoice can never get an IRN through this path, even though the law requires it to be e-Invoiced.
**Fix direction:** Relax the buyer-GSTIN requirement for export/SEZ/deemed-export supply types; populate `Gstin: "URP"` and drive `Pos`/`Stcd` from the fixed `"96"` code (TAX-02) instead of the customer's foreign address text.

### TAX-04 — `ALLOWED_GST_RATES` is missing the 40% GST 2.0 slab — **Critical** *(verified directly)*
**File:** `core/validators.py:10`, enforced at `sales/services.py`, `purchases/services.py`, `imports/services.py`, `reporting/gst_health.py`
```python
ALLOWED_GST_RATES = ("0", "0.25", "3", "5", "12", "18", "28")
```
Following the GST Council's rate rationalisation ("GST 2.0", effective 22 Sept 2025) which introduced a 40% de-merit/"sin & luxury" slab (tobacco, pan masala, aerated drinks, luxury vehicles, etc.), this single hard-coded allow-list — used everywhere a GST rate is entered — has no `40` entry.
**Failure scenario:** A pilot user selling any item legally taxed at 40% enters `40` as the rate and is hard-blocked with "Invalid GST rate 40. Allowed: 0, 0.25, 3, 5, 12, 18, 28%." They cannot bill correctly for that product category at all.
**Fix direction:** Add `40` immediately; longer-term, make the allowed-rate set a company-configurable/versioned table with an effective date rather than a hard-coded tuple, since GST rate schedules change periodically by Council notification.

### TAX-05 — `is_intra_state()` fallback disagrees with the "assume local state" Complete gate — **High**
**File:** `core/services/billing.py:140-167`, `core/services/place_of_supply.py:7-24, 27-43`
`assert_place_of_supply_for_gst()` treats *any* unresolvable state (truly blank, or garbage like `"NA"`) as eligible for the `assume_local_state_for_blank_party` bypass. But `party_intra_state()`, which actually decides CGST+SGST vs IGST, only applies its own "assume local" shortcut when the state string is **literally empty** — a non-blank-but-unmappable value like `"NA"` falls through into a raw-string comparison that essentially never matches, returning inter-state.
**Failure scenario:** Company has `assume_local_state_for_blank_party=True` (meaning "treat unknown-state walk-in customers as local"). A cashier enters `"NA"` instead of leaving the field truly blank. The invoice is allowed to Complete (the gate thinks it qualifies), but is silently taxed **IGST** instead of the CGST+SGST the setting promised — the two gates disagree on what "blank" means, and the stricter one controls the actual money.
**Fix direction:** Make both functions use the identical "resolvable to a code" predicate for what counts as blank.

### TAX-06 — GSTIN checksum digit is never verified — **Medium-High**
**File:** `core/validators.py:7,13-15`
`GSTIN_RE` checks shape only (2-digit state + 10-char PAN + entity code + `Z` + 1 alphanumeric); the 15th character's mod-36 checksum is never computed/compared anywhere in the repo.
**Failure scenario:** A single-digit typo/transposition while copying a GSTIN from a physical invoice still matches the shape regex and is silently accepted. It's only caught later (if at all) — e.g. at IRP e-Invoice submission time, by which point a "Completed" invoice with a wrong buyer GSTIN already exists and needs a correction after the fact.
**Fix direction:** Implement the standard GSTIN mod-36 checksum algorithm in `validate_gstin()`.

### TAX-07 — Union Territories without a legislature: no UTGST modeling — **Low**
**File:** `core/services/billing.py:170-187`, `core/models.py:52-53`
Only `cgst`/`sgst`/`igst` fields exist; for UTs without a legislature (Chandigarh, A&N Islands, Lakshadweep, D&NH+Daman&Diu, Ladakh), intra-territory supply should legally be CGST+**UTGST**, not CGST+SGST. The rupee split is numerically identical either way and the e-Invoice schema doesn't have a distinct UTGST field, so this is unlikely to break filings, but any GL/ledger head labelled "SGST" is technically mislabeled for these 5 GSTIN prefixes. Flagged for CA confirmation rather than as a confirmed numeric bug.

### TAX-08 — Vehicle-number regex rejects valid Bharat-Series (BH-series) plates — **Medium**
**File:** `sales/eway_payload.py:43`
`_VEHICLE_RE` only matches the classic `SS-DD-AA-NNNN` format; it cannot match the 2021-introduced BH-series format (`YYBHxxxxAA`, starts with digits), which fails the `^[A-Z]{2}` anchor outright.
**Failure scenario:** A transporter with a valid, NIC-portal-accepted BH-series plate (`22BH1234AB`) is rejected with "vehicleNo must match Indian registration pattern," blocking e-Way bill generation.
**Fix direction:** Extend the regex to also accept `^\d{2}BH\d{4}[A-Z]{1,2}$`.

### TAX-09 — GST FY label for document numbering uses the company's configurable `fy_start_month`, not the fixed April–March GST year — **Medium**
**File:** `core/services/document_numbers.py:37-43`
`fy_label_for()` reads `company.fy_start_month` (default 4, but user-editable for internal MIS reasons) to compute the FY label used for GST document series. GST invoice numbering is legally tied to the fixed April–March financial year (Rule 46(b)) regardless of any internal accounting-FY preference.
**Failure scenario:** An accountant sets `fy_start_month=1` for calendar-year internal reporting. Every invoice dated Jan–Dec 2026 gets label `"2026-27"` — invoices raised Jan–Mar 2026 are mislabeled; they actually belong to GST FY 2025-26. The document series doesn't roll over at the true 1-April boundary, splitting one continuous numbering sequence at the wrong point and complicating GSTR-9/annual reconciliation.
**Fix direction:** Decouple GST document-series FY resolution from `company.fy_start_month`; always compute it as April-start for statutory document types.

### TAX-10 — No e-Way ₹50,000 threshold warning, no transporter-ID format check — **Low**
**File:** `sales/eway_payload.py:46-61`
No proactive warning when a completed taxable invoice exceeds ₹50,000 with no e-Way bill generated; `transporter_id` has no format validation (should be a 15-char GSTIN or 12-digit TRANSIN). Real usability gap for a first-time user unaware of the threshold rule.

### TAX-11 — HSN digit-length-by-turnover rule is advisory only, not enforced at Complete — **Medium**
**File:** `sales/services.py:466-471`, contrasted with `reporting/gst_health.py:105-110`
Only a missing-HSN warning exists at invoice-complete time; the CBIC turnover-based minimum digit count (4/6/8 digits scaling with AATO) is checked only in a post-hoc reporting alert over already-completed invoices, never as a pre-Complete block/warning.
**Fix direction:** Surface the turnover-based digit-count check as a pre-Complete warning, mirroring the existing missing-HSN warning pattern.

### TAX-12 — Cess is percentage-only; specific/per-unit cess cannot be modeled — **Medium**
**File:** `core/models.py:95-96`, `core/services/billing.py:182-184`, `sales/einvoice_payload.py:213-214`
No field or code path exists for a **specific** (per-unit, e.g. ₹/thousand cigarette sticks, ₹/tonne coal) compensation cess — only ad-valorem `cess_rate` (%). A business dealing in such goods cannot enter a correct cess amount; back-solving a synthetic percentage breaks the moment quantity/price varies and misreports `CesRt`/`CesAmt` in the e-Invoice payload.
**Fix direction:** Add a per-line specific-cess amount field alongside the existing ad-valorem rate.

### TAX-13 — Missing `MLT` (millilitre) UQC code — **Low**
**File:** `core/services/uqc.py:6-51`
The official GSTN UQC list includes `MLT` alongside `LTR`; it's absent here, so ml-denominated products (perfumes, e-liquids, small pharma vials) silently fall back to `"OTH"`.

### TAX-14 — Unmapped units silently collapse to `"OTH"` with no user-visible flag — **Suggestion**
**File:** `core/services/uqc.py:144-165`
Keeps documents GST-compliant but loses real unit info for GSTR-1 Table 12 with no warning the mapping failed.

**What's done well (Tax Engine):** All monetary math is `Decimal`-only with a single `q2()` (`ROUND_HALF_UP`, 2dp) helper; grand-total rounding to the nearest rupee is captured explicitly into a `round_off` field (correct Sec 15(4) treatment, full audit trail); CGST/SGST split computes the second half as `total − first_half` so the two never drift apart from independent rounding (a very common source of GSTR-1 paisa mismatches, correctly avoided); composition/unregistered companies are correctly blocked from issuing tax invoices; returns are modeled as separate documents rather than negative-quantity lines; SEZ/export tax-type-vs-supply-type consistency is validated at Complete (though the surrounding POS/e-Invoice plumbing for the same feature has the gaps above); `gstin_verify.py` is carefully defensive about never claiming a stronger verification guarantee than actually happened.

---

## 2. Sales Documents

*Scope: `sales/models.py`, `services.py`, `handlers.py`, `notes_services.py`, `return_service.py`, `serializers.py`, `phase1_*.py`, `recurring.py`, `pdf/*.py`, `core/services/document_numbers.py`, `h9_amend.py`.*

### SALES-01 — Credit/debit notes can silently re-price off the current price list / current product GST rate — **Critical**
**File:** `masters/pricing.py:8-36`, `sales/services.py:61-146` (`_build_items`), `notes_services.py:82-107`
`_build_items()` is the shared line-builder for `SalesItem`, `SalesCreditNoteItem`, and `SalesDebitNoteItem` alike. It calls `resolve_unit_price()`, which — for a non-Owner caller — silently overrides a submitted `unit_price` with the *current* price-list price whenever the customer has a price list, with no awareness that it's being called for a correction rather than a fresh sale. Separately, when `source_item` is passed, only `hsn_code`/`unit_name`/`uqc_code` are copied from it — `gst_rate` and `unit_price` remain optional, defaulting to *today's* product-master values if the caller omits them.
**Failure scenario:** Product X was sold at 12% GST in April; GST Council moves it to 18% in July. In August, staff (non-Owner) creates a credit note for a return without explicitly overriding `gst_rate`/`unit_price`. The system computes the note at 18% and/or the current list price, overstating/understating the tax reversed relative to what was actually charged and filed in April's GSTR-1 — with no guardrail.
**Fix direction:** When `source_item` is provided, force `gst_rate`/`unit_price`/`discount_percent` to copy verbatim from it; never invoke `resolve_unit_price` for note lines with a `source_item`.

### SALES-02 — In-place invoice amend (H9-A) has no guard for invoices with a live e-Invoice IRN — **Critical**
**File:** `sales/serializers.py:185-320`, `core/services/h9_amend.py:8-62`, `docs/pilot/H9_CORRECTION_PATH.md`
H9-A lets an Owner change `unit_price`/`discount_percent` on a *completed* invoice's existing lines in place (with `confirm_amend=true`), re-saving the same invoice number/date. This was a documented, conscious Phase-0 tradeoff pending credit notes — but credit notes have since shipped, and H9-A was never retired or gated. Critically, nothing in the amend path checks `invoice.einvoice_status`/`irn` — an invoice with an already-issued government IRN can still be silently re-priced. The regenerated PDF then shows the new amended totals next to the old, still-stored IRN/QR code.
**Failure scenario:** Owner completes and e-Invoices a ₹50,000 invoice. Two weeks later, using "amend" (not a credit note) they drop the price to ₹45,000. The PDF regenerates with ₹45,000 and the old IRN's QR code; the IRP/GSTR-1 still has ₹50,000 on file — a discrepancy that surfaces at reconciliation or audit with no credit-note trail.
**Fix direction:** Block H9-A money/price amends once `einvoice_status` is `GENERATED`/`MANUAL_IRN` (require IRN cancellation or a credit/debit note instead); re-evaluate whether H9-A should still exist now that CN/DN are live.

### SALES-03 — H9-A amend deletes and recreates ALL invoice line items, orphaning credit/debit-note audit links — **High**
**File:** `sales/services.py:271-288`, `sales/models.py:334-336, 409-411`
`set_items()` unconditionally does `invoice.items.all().delete()` then `bulk_create`s fresh rows — for *both* draft edits and completed-invoice H9-A amends — even when only one line's price changed (the H9-A path resends the full line array). `SalesCreditNoteItem.source_item`/`SalesDebitNoteItem.source_item` are `SET_NULL` FKs to `SalesItem`.
**Failure scenario:** A credit note is issued against line 2 of a 3-line invoice, correctly linking `source_item=line2`. A week later, an H9-A amend on line 1's price alone deletes and recreates all 3 `SalesItem` rows with new PKs; the old credit note's `source_item_id` is silently nulled by the DB, destroying the audit trail from "this credit note line corrects that invoice line" with no error.
**Fix direction:** Update existing `SalesItem` rows in place in the H9-A path rather than delete+recreate.

### SALES-04 — No validation that a credit/debit note or sales-return date is on/after the original invoice date — **Medium**
**File:** `sales/notes_services.py:109-183`, `return_service.py:65-181`
Only GST-period locks are checked; nothing compares `note_date`/`return_date` against `invoice_date`. A credit note can be backdated to before the invoice it corrects existed.

### SALES-05 — No enforcement/warning for the statutory credit-note time limit (30 Nov following FY) — **Medium**
**File:** `sales/notes_services.py:109-183`
Sec 34(2) caps credit notes affecting output tax to the earlier of 30 Nov following the FY or the annual-return filing date. Only an internal period-lock is checked, not this statutory cutoff — a company could issue a GST-effective credit note years late with no warning.

### SALES-06 — Quotation `valid_until` is stored but never enforced or warned on conversion — **Medium**
**File:** `sales/models.py:189`, `services.py:740-773`
An expired quotation converts to a draft invoice identically to a fresh one, with no prompt to re-check stale pricing — common in a "valid for 15 days" quotation workflow.

### SALES-07 — Credit/debit note PDF omits the original invoice date (only shows the number) — **Medium**
**File:** `sales/pdf/note_documents.py:153-178`
GST Rule 53 / GSTR-1 Table 9B practice requires both invoice number *and date* on the reference. Only the number is printed; the date is available on the model but not rendered.

### SALES-08 — Manual credit notes aren't capped per-line against what was actually invoiced for that product — **Low**
**File:** `sales/notes_services.py:58-74`
Only the aggregate grand-total headroom is checked; two lines individually misallocated across different HSN/rate combinations can pass the aggregate check while producing an HSN-level GSTR-1 mismatch.

### SALES-09 — No "locked after share" concept — PDF share doesn't influence edit permissions — **Low / Usability**
**File:** `sales/views.py:363-396`
Sharing an invoice's PDF (email/WhatsApp) sets no flag; an Owner can still H9-A-amend an invoice the customer has already received, with no extra friction, so the customer's copy silently disagrees with the system's copy.

**What's done well (Sales):** Document numbering (`document_numbers.py`) is correctly concurrency-safe (`select_for_update()` on the per-company/doc-type/GSTIN/FY series row inside an atomic block — not a naive `max()+1`), and numbers are only assigned at Complete, so abandoned drafts never burn a sequence slot; cancelled invoices retain their number (correct GST behavior, no gaps/no reuse). Recurring invoice generation correctly prevents duplicate generation on concurrent scheduler runs via row lock + a unique `(schedule, period_key)` constraint, and only ever produces drafts. Sales-return over-return prevention correctly computes `sold − already_returned` before accepting a return.

---

## 3. Purchases & Bulk Import

*Scope: `purchases/models.py, services.py, notes_services.py, serializers.py, views.py, phase1_*.py`, `imports/models.py, services.py, views.py, tasks.py`.*

### PUR-01 — Accounting books post full Input GST regardless of `itc_eligibility` — **High**
**File:** `accounting/services.py:483-608, 563-591` vs `reporting/gst_returns.py:867-882,1183-1196`
`PurchaseInvoice.itc_eligibility` defaults to `UNREVIEWED` with an explicit "never claim ITC until marked CLAIMABLE" comment, and the GSTR-3B builder correctly honors this. But `PostingService.post_purchase` debits Input CGST/SGST/IGST for *every* GST purchase's full tax amount unconditionally — `itc_eligibility` never appears anywhere in `accounting/`.
**Failure scenario:** Owner buys a company car (blocked credit under Sec 17(5)(a)) and correctly marks the invoice `INELIGIBLE`, excluding it from GSTR-3B. The GL still debits the full GST to Input CGST/SGST/IGST as if claimable — permanently overstating that asset account with no reclass journal ever written, creating a growing, unexplained gap between "Input GST per books" and "ITC claimed per GSTR-3B."
**Fix direction:** Either don't post the ineligible portion to Input GST at all (capitalize/expense it instead), or auto-generate a reclass journal the moment eligibility resolves to non-claimable.

### PUR-02 — Reverse charge (RCM) is 100% manual, with zero auto-detection or warning — **High**
**File:** `purchases/models.py:62`, `services.py:162,274`
`is_reverse_charge` is a plain checkbox never derived from `Supplier.taxpayer_type`, product category (GTA/freight), or an import-of-service flag. GST law imposes RCM liability on the recipient regardless of whether the user remembers to tick the box.
**Failure scenario:** A trader pays a local unregistered transporter for freight (classic GTA-RCM) and records it as a normal purchase. No RCM self-invoice/liability is ever generated; the company under-reports RCM tax payable in GSTR-3B Table 3.1(d) with no warning at all. *(The RCM mechanism itself, once flagged, is well-built — two-pass tax compute correctly memoing liability into `rcm_*` fields and posting it separately in the GL.)*

### PUR-03 — `Supplier.taxpayer_type` (composition/unregistered) exists but is never consulted by purchase logic — **High**
**File:** `masters/models.py:76-88,137-142`; confirmed absent from `purchases/services.py`, `core/services/billing.py`
A composition-scheme supplier is legally barred from charging GST at all; nothing checks `supplier.taxpayer_type` to block/zero GST lines or default `itc_eligibility` to `INELIGIBLE`.
**Failure scenario:** A retailer buys from a supplier flagged `COMPOSITION` but the product's GST rate defaults from the product master and gets entered as an 18% GST purchase, then marked `CLAIMABLE` — a false ITC claim the system never flags, since a composition dealer never files outward tax and GSTR-2B will never show the invoice.

### PUR-04 — No import-of-goods / customs IGST support at all — **High**
**File:** repo-wide (no `customs`/`bill_of_entry`/`BOE` matches)
The `imports/` app is bulk *data ingestion* (CSV import, OCR bill extraction), not GST "import of goods." No Bill-of-Entry field, no customs-IGST/duty ledger separate from the foreign supplier's AP, no foreign-currency/no-GSTIN supplier handling.
**Failure scenario:** A trader importing goods either can't Complete the purchase (place-of-supply block for a foreign supplier) or, if forced through via the "assume local" flag, gets AP and ITC basis both silently misstated — customs IGST/duty is a distinct payable, claimed via the BOE, not the commercial invoice.

### PUR-05 — `ImportJob.commit()` has no row lock — concurrent double-commit creates duplicate purchase invoices — **High**
**File:** `imports/views.py:104-122`, `imports/services.py:159-219, 456-527`
Unlike `PurchaseService.complete()` (which re-fetches with `select_for_update()` specifically to close this race), `ImportJob.commit()` only checks `status != PREVIEWED` on an already-fetched, unlocked instance — and `ImportJobViewSet` has no `Idempotency-Key` handling at all (unlike `PurchaseInvoiceViewSet`, which does).
**Failure scenario:** A trader on a flaky connection taps "Commit" twice (retry after a perceived hang). Both requests race past the unlocked status check, both build the same purchase — two identical purchase invoices, double stock-in, double AP, and (once ITC-reviewed) a doubled ITC claim from one physical bill.

### PUR-06 — No duplicate supplier-bill-number detection, manual entry or import — **High**
**File:** `purchases/models.py:46` (`supplier_bill_number`, no unique constraint, never checked against existing invoices)
Nothing prevents the same physical supplier bill being entered twice — a real risk for the stated persona (limited accounting literacy, likely to re-upload/re-enter the same paper bill), and exactly the "duplicate/fake invoice" ITC risk the review was asked to check for.
**Fix direction:** Before commit/save, look up existing non-cancelled invoices with the same `(company, supplier, supplier_bill_number)` and surface a blocking or overridable warning.

### PUR-07 — ITC eligibility is invoice-level only, not line-level — **Medium**
**File:** `purchases/models.py:64-75`
A single bill mixing an eligible line (stationery) and a Sec 17(5)-blocked line (staff gift hamper) can't be split — the whole invoice must be marked one way, losing real ITC or falsely claiming blocked ITC.

### PUR-08 — No RCM-nudge warning for likely-unregistered suppliers — **Medium**
No warning at Complete when `supplier.taxpayer_type == UNREGISTERED`/blank GSTIN and `is_reverse_charge` is false.

### PUR-09 — OCR GST-rate snapping/defaulting is silent — **Medium**
**File:** `imports/services.py:92-100`
`_normalize_gst_rate` snaps a misread rate to the nearest valid slab or hard-defaults to 18% with no corresponding warning entry, so a high-confidence overall extraction can still contain a silently-guessed rate a rushed user won't re-check.

### PUR-10 — No price/tax sanity check against purchase history — **Medium**
No comparison of an entered `unit_price` against the product's last known cost/MRP to catch obvious data-entry slips (extra zero, decimal shift).

### PUR-11 — Bulk-import product matching is exact-name-only — **Medium/Low**
**File:** `imports/services.py:357-407`
Minor OCR name variance creates duplicate `Product` rows instead of matching the intended product, fragmenting stock/purchase history.

### PUR-12 — No blocked-credit classification/reason capture — **Medium/Low**
`itc_eligibility` is a free-choice enum with no structured reason code (motor vehicle, food/beverage, works contract, etc.) for audit-trail purposes.

### PUR-13 — GSTIN validated by format only, no checksum digit — **Low** *(same root cause as TAX-06, shared validator)*

**What's done well (Purchases):** ITC reversal on purchase returns is mechanically consistent (correctly credits Inventory *and* Input GST proportional to the returned tax); place-of-supply on the *input* side is correctly modeled (compares the company's selling-GSTIN state against the supplier's, prioritizing GSTIN over free text); over-return prevention, atomicity, and multi-tenant scoping are all solid across the purchase document lifecycle (`select_for_update()` consistently used, no missing `company` filters found); HSN/rate/MRP/unit are correctly snapshotted from the product master onto purchase lines rather than left to manual re-entry; validation-before-write in the CSV import path is genuinely all-or-partial, not silently corrupting (bad rows are excluded and remain inspectable, not written).

---

## 4. Payments & Ledgers

*Scope: `payments/models.py, services.py, gateway.py, upi.py, recon.py, serializers.py, views.py, webhook_views.py`, `ledgers/services.py, views.py`.*

### PAY-01 — Dashboard receivables/payables and ageing buckets double-count returns already relieved by their auto-generated credit note — **High**
**File:** `reporting/services.py:34-66, 68-100, 102-173`
Every `COMPLETED` sales/purchase return auto-creates and completes a linked credit/debit note carrying the return's *entire* monetary relief (the return itself is stock-only). `ledgers/services.py` correctly excludes returns from its own outstanding calculation (only counts the note), and even has explicit de-duplication logic for this exact problem elsewhere — but `reporting/services.py` was never updated to match, and subtracts **both** the return *and* its auto-generated note for the same event.
**Failure scenario:** A ₹10,000 return against a ₹50,000 invoice (auto credit note for ₹10,000). The invoice-detail/customer-statement view correctly shows ₹40,000 outstanding. The main dashboard and ageing buckets show outstanding reduced by ₹20,000 — understating what's actually owed and undercounting overdue exposure.
**Fix direction:** Apply the ledger layer's existing exclusion pattern to `reporting/services.py`, or have it simply call the ledger service's bulk-outstanding functions instead of re-implementing the aggregation.

### PAY-02 — `SupplierPayment` TDS fields are accepted by the API but silently discarded — **High**
**File:** `payments/views.py:194-217`, `services.py:190-243`, `serializers.py:92-116`
`tds_section`/`tds_rate`/`tds_amount` are writable serializer fields, validated on input, but `SupplierPaymentViewSet.create()` never reads them from `validated_data` and `create_supplier_payment()` doesn't accept them as parameters — they're never persisted.
**Failure scenario:** A bookkeeper deducting TDS on a supplier payment fills in the TDS fields; the POST returns 201; a subsequent GET shows them all reset to blank/zero — compliance data silently lost with no error.

### PAY-03 — GL-based supplier outstanding only nets TDS when the `ENABLE_TDS` flag is on; document-derived outstanding always nets it — **Medium-High**
**File:** `ledgers/services.py:117-119` vs `accounting/services.py:523-529,574-581`
If a company has `accounting_enabled=True` but `ENABLE_TDS` off, and an invoice carries `tds_amount`, the GL posts the *full* grand total to AP while the document-derived outstanding (used for payment validation/allocation) already assumes the TDS-netted figure — leaving a phantom balance in the GL-based statement that never clears.

### PAY-04 — Payment-gateway "disabled providers" gate is an empty set — no-op — **Medium**
**File:** `payments/gateway.py:21`, `services.py:481-485`, `views.py:773-776,790-794`
`DISABLED_PROVIDERS = frozenset()` — the settings UI reports Cashfree/PayU as "disabled" and blocks setting them as a company *default*, but `create_payment_link` accepts an explicit `provider` override that bypasses this entirely, since the actual enforcement set is empty. An Owner can explicitly request `provider: "cashfree"` and the fully-implemented adapter will process it for real.

### PAY-05 — Unset `DJANGO_ENV` fails open into allowing sandbox/test-mode payment flows — **Medium**
**File:** `payments/gateway.py:572-577`, `services.py:493-500`, `views.py:765`
All sandbox-forbidding checks are a denylist (`"production"`,`"staging"`) rather than an allowlist — an unset `DJANGO_ENV` in a real production deployment (a plausible ops omission) is treated as sandbox-safe.

### PAY-06 — `allow_partial` is never actually sent to Razorpay — partial payment collection is non-functional on the real gateway — **Medium**
**File:** `payments/gateway.py:169-190`, `services.py:529-538`
`RazorpayAdapter.create_payment_link` hardcodes `accept_partial: False` regardless of `PaymentLink.allow_partial`; the flag only works against the `SandboxAdapter`, making it easy to miss in testing.

### PAY-07 — Bank-reconciliation auto-match can reach the auto-commit threshold with no hard reference (UTR) match — **Medium**
**File:** `payments/recon.py:160-208,273-283`
Amount(40) + reference-substring(25) + name-token hits(15) + date-proximity(10) can total ≥90 (the auto-commit threshold) with **no UTR** involved at all; generic name tokens shared across multiple parties (e.g. "TRADING", "ENTERPRISES") inflate the score without being genuinely discriminating.
**Failure scenario:** Two different customers with similar names and similar amounts around the same date can have a bank credit auto-matched to the wrong one, with no UTR corroboration, silently misstating both balances.
**Fix direction:** Require a UTR or an exact invoice/receipt-number match as a hard prerequisite for the *auto-commit* path; keep the soft score for the manual-review queue only.

### PAY-08 — No dedicated cheque payment mode or bounce-tracking workflow — **Medium**
**File:** `payments/models.py:9-14,24-29`
No `PaymentMode.CHEQUE`, no cheque number/date fields, no "pending clearance" receipt state — a cheque receipt is recorded and instantly treated as realized, reducing the customer's outstanding balance before the cheque has actually cleared. Bounces can only be handled via a generic void with no structured "bounced" reason code — a real gap for standard Indian trade-credit practice.

### PAY-09 — Stale outstanding read in gateway-webhook allocation can roll back an already-captured payment on a race — **Medium**
**File:** `payments/services.py:681-692`
`finalize_gateway_payment` reads outstanding without a lock, computes the allocation amount, then calls `allocate_receipt` (which re-locks and re-validates) — all inside one outer atomic block. A concurrent allocation reducing the true outstanding between the stale read and the lock can throw, and since it's all one transaction, the **entire webhook transaction rolls back**, leaving a gateway-captured payment with no `GatewayPayment`/receipt record at all if the gateway's retries are exhausted.

### PAY-10 — No opening-balance concept for customers/suppliers — **Medium**
Every balance is derived purely from documents created inside Bizboard; nothing lets a business migrating from paper/Tally mid-year seed a starting receivable/payable, understating true exposure (including for credit-limit checks) until new invoices are raised.

### PAY-11 — `GatewayPayment` idempotency has a first-arrival race window — **Low-Medium**
**File:** `payments/services.py:588-608`
`SELECT ... FOR UPDATE` can't lock a row that doesn't exist yet; two near-simultaneous first-webhook deliveries for a new `provider_payment_id` can both pass the `None` check and race to `.create()` — the DB unique constraint prevents a double-credit, but the loser gets an unhandled `IntegrityError` → 500 instead of a clean idempotent response.

### PAY-12 through PAY-19 — Lower-severity items (Low/Suggestion)
- No GST TDS (Sec 51)/e-commerce TCS (Sec 52) modeling (only income-tax-style TDS/TCS fields exist) — plausible scope gap, confirm with product.
- No UPI VPA format validation on the company's own collection ID — a malformed `upi_id` silently produces broken QR/deep-links for every customer.
- `BankLineMatchStatus.IGNORED` exists in the enum but no UI/API action ever sets it — irrelevant statement lines (bank fees, interest) can never be dismissed from the reconciliation queue.
- N+1 query pattern in `payment_health` (~150 queries for 50 invoices) — contrast with the properly bulk-aggregated pattern used two lines above it in the same function.
- Minor: two separate aggregate queries where the bulk variants already combine them into one.
- Refunds are all-or-nothing (documented as a known limitation in-code).
- No FIFO/bulk "auto-allocate to oldest invoices" convenience endpoint.
- Minor information-disclosure oracle on the webhook endpoint (different error for existing vs. non-existent `payment_link_id`) — low priority given high-entropy IDs.

**What's done well (Payments/Ledgers):** Allocation logic is genuinely race-safe (`select_for_update()` on both the money document and the invoice, re-validated inside the same transaction — correctly prevents double-allocation/overpayment); webhook handling never trusts a client-supplied company id, resolves it via the trusted `PaymentLink→company` relationship, and does real signature verification per provider; bulk-aggregation queries (`bulk_customer_outstanding`, etc.) are properly grouped SQL, not per-party loops, with in-code comments showing the team already fixed N+1 patterns here before; UTR duplicate protection is enforced company-wide across both receipts and payments; correctly triggers **no** output tax on unallocated advance receipts for goods (matching Notification 66/2017-CT).

---

## 5. Inventory & Masters

*Scope: `inventory/models.py, services.py, views.py, serializers.py, management/commands/rebuild_stock_balances.py`, `masters/models.py, pricing.py, serializers.py, views.py`.*

### INV-01 — Switching valuation method WAVG → FIFO mid-life can hard-block sales of existing stock — **Critical**
**File:** `inventory/services.py:138-219`, `accounts/serializers.py:147-151`
`InventoryCostLayer` rows are only created for inbound movements posted *while* `method == "FIFO"`. `inventory_valuation_method` is a plain owner-editable setting with no check for existing on-hand stock and no backfill step. Every FIFO test in the suite sets the method *before* any stock exists — the switch-with-existing-stock path is untested and unguarded.
**Failure scenario:** A company running WAVG for months (real stock, no cost layers) flips to FIFO in one settings PATCH. The very next sale of any pre-switch SKU fails with "Insufficient FIFO cost layers" even though `StockBalance.on_hand` clearly shows stock available — billing is blocked for that SKU until enough new FIFO-era inbound movements cover it.
**Fix direction:** Either block the method switch when on-hand stock lacks corresponding cost layers, or provide a one-time command that seeds `InventoryCostLayer` rows from current `StockBalance.on_hand` at switch time.

### INV-02 — `rebuild_stock_balances` management command silently wipes all reserved-stock state — **High**
**File:** `inventory/management/commands/rebuild_stock_balances.py:22-33`
Deletes all `StockBalance` rows and recreates them with `on_hand` only — `reserved` is never set (defaults to 0), unlike the "real" rebuild path (`InventoryService.rebuild_balance`) which correctly recomputes `reserved` from confirmed sales orders including FEFO lot allocation.
**Failure scenario:** Ops runs this command to fix a suspected balance drift (its stated purpose). Every confirmed sales order's reservation is zeroed company-wide; `available_quantity` reads higher than it should, and the negative-stock guard will now happily allow selling stock already promised to a confirmed order.
**Fix direction:** Have the command call `InventoryService.rebuild_balance()` per (company, warehouse, product, batch) instead of hand-rolling an on-hand-only bulk rebuild.

### INV-03 — CSV import commit rolls back the entire batch on a single duplicate row, contradicting its own docstring — **High**
**File:** `imports/services.py:44-74, 159-219`
The docstring promises per-row isolation ("failed rows stay in the error report"), but `_validate_row` never checks sku/barcode/GSTIN duplicates (against the DB or within-file), and `commit()` is one `@transaction.atomic` around the whole loop — a duplicate hit partway through rolls back *every* row already created in that call, not just the offending one.
**Failure scenario:** A 500-SKU catalog import with one duplicate barcode at row 450 loses all 500 rows, with only a generic "duplicate value" error and no row number.

### INV-04 — `PriceListItem.product` and `Customer.price_list` are not company-scoped, unlike the rest of the codebase's FK pattern — **Medium**
**File:** `masters/serializers.py:90-93,103-121,30-39`
The codebase has an established `CompanyPrimaryKeyRelatedField`/manual-check pattern for exactly this problem elsewhere (`ProductSerializer._check_company`), but it isn't applied here — a user of Company A who can guess a Company B product/price-list PK can create referential links to another tenant's data (not a full read-leak, since list/detail views stay company-scoped, but a real cross-tenant referential-integrity gap).

### INV-05 — CSV-imported products bypass the GST-rate slab validator — **Medium**
**File:** `imports/services.py:56-62`, `masters/models.py:181-183`
Model-field `validators=[validate_gst_rate]` only run through `full_clean()`, which the direct `Product.objects.create()` call in `commit()` never invokes; `_validate_row` only checks the value parses as a Decimal, not that it's an allowed slab. A bad rate (e.g. a stale 15%) is silently persisted and only surfaces later as "can't sell this product" at sale time.

### INV-06 — Adjustment/opening-stock endpoints silently substitute the default warehouse for an invalid/foreign warehouse id — **Medium**
**File:** `inventory/views.py:79,110`
An unresolvable or cross-tenant warehouse id is silently dropped to `None` and falls back to the default warehouse rather than raising a validation error — a multi-location retailer's stale/typo'd warehouse id posts an adjustment to the wrong location with no error.

### INV-07 — No unit-of-measure conversion (one fixed unit per product, purchase and sale) — **Low / Roadmap**
No conversion-factor support for the common Indian pattern of stocking in cartons/boxes but selling in pieces. Confirmed genuinely absent (not half-implemented) — likely acceptable MVP scope, but worth flagging since README doesn't explicitly disclaim it.

### INV-08 — Low-stock/reorder alerts key off `on_hand`, not `available` (on_hand − reserved) — **Low**
A product with plenty of raw `on_hand` but most of it already reserved against confirmed sales orders won't trigger a reorder alert even though truly sellable stock is below the reorder level.

### INV-09 — No safe "change default warehouse" path — **Low**
Setting a second warehouse's `is_default=True` while another already holds it just hits a generic DB-constraint 400 with no guidance; no supported way to atomically swap the default.

### INV-10 — Catalog usability: no product image field, flat (non-hierarchical) Category/Brand — **Suggestion**
Workable for small catalogs, unwieldy for large multi-level ones; `core.FileAsset` (already used for company logo) could be reused for product images.

### INV-11 — Masters list caching (`Unit`/`TaxRate`) has no write-invalidation — **Low** *(already flagged in-code by the team)*
A newly created unit/tax rate can be invisible in the list endpoint for up to 60 seconds.

**What's done well (Inventory/Masters):** The stock-movement ledger is genuinely append-only at the model layer (`save()`/`delete()` raise on any mutation attempt, not just convention); movement-type signs are complete and correct across all ten types; the negative-stock guard is race-safe (`select_for_update()` on the balance row *before* the policy check and the write — correctly closes a real concurrent-oversell TOCTOU hole, a detail many systems get wrong); FIFO costing is a genuine perpetual cost-layer ledger (more capable than the README's own "not full perpetual FIFO COGS" framing suggests) — its one real gap is the mid-life-switch case (INV-01); HSN/GST-rate/MRP are correctly snapshotted onto invoice lines at transaction time, never recomputed from a possibly-since-changed product master, protecting historical GST filings from silent corruption; barcode/SKU uniqueness is correctly company-scoped (not global) with explicit rationale comments; batch/expiry tracking with FEFO ordering and expired-stock blocking is a real, working feature, not a stub; multi-tenancy scoping is consistently applied across inventory/masters viewsets (the one confirmed gap is the nested price-list FK issue above).

---

## 6. Reporting / GSTR Worksheets

*Scope: `reporting/gst_returns.py, gst_returns_sections.py, gstr2b.py, gst_health.py, gst_periods.py, tds_worksheets.py, services.py, views.py`.*

*(All worksheets here are explicitly, honestly labeled "offline aids, not GSTN portal filing" — this framing is correct and consistently applied; the findings below are about completeness/correctness of the aid itself, not about any false "ready to file" claim, which was checked for and not found anywhere.)*

### GSTR-01 — GSTR-3B Table 3.1 outward breakup is one merged bucket, not the required (a)/(b)/(c)/(d) split — **High**
**File:** `reporting/gst_returns.py:1019-1025,543-559`
B2B, B2CL, B2CS, exports (zero-rated), SEZ, and nil-rated invoices are all folded into one combined `{taxable_value, igst, cgst, sgst, cess}` figure, with no caveat that it's undifferentiated — unlike the `nil` block elsewhere in the same file, which does self-disclose its own limitation.
**Failure scenario:** A business with domestic taxable sales and LUT-export sales sees one merged taxable-value figure; a CA cannot tell how much belongs in 3.1(a) vs 3.1(b) without manually re-deriving from the GSTR-1 arrays — defeating the point of an "aid."

### GSTR-02 — GSTR-3B Table 3.2 (inter-state supplies to unregistered/composition/UIN holders) doesn't exist at all — **Medium-High**
**File:** confirmed absent by repo-wide search
The underlying state-wise B2CL/B2CS data already exists in the GSTR-1 payload but is never re-shaped into this table.

### GSTR-03 — No true GSTR-1 Table 9A/9B/9C (invoice-value amendment) tracking — only a filing-identity audit trail — **High**
**File:** `reporting/gst_returns.py:810-843`, `sales/einvoice_eway_actions.py:379-381`
The only "amendments" surfaced are GSTIN/place-of-supply corrections (explicitly documented as "no money changes"). There is no mechanism producing original-vs-revised value pairs for a supply corrected in a later period — see GSTR-05 for why this matters in practice.

### GSTR-04 — GSTR-9 reuses stale snapshot payloads without checking the `dirty_after_snapshot` flag — **Medium-High**
**File:** `reporting/gst_returns.py:1148-1161`
The flag exists specifically to mark "a document changed after this snapshot was taken," but the GSTR-9 builder prefers a persisted snapshot over live data without ever checking it — combining with GSTR-05 below, a price amend made after a month's snapshot silently never reaches the annual return.

### GSTR-05 — Completed-invoice price amends (H9-A) silently mutate historical periods with no amendment trail, and the "dirty" flag doesn't actually block anything — **High** *(ties directly to SALES-02/SALES-03 above)*
**File:** `core/services/h9_amend.py`, `reporting/gst_periods.py:17-32`
The only guard is an optional, manually-triggered period soft-close — if a filed period was never explicitly closed, a later H9-A price amend on an invoice in that period succeeds silently, the `dirty_after_snapshot` flag is set but only ever read for a warning-level health alert (never consulted by the GSTR-1/9 builders themselves, per GSTR-04), and no 9A row is ever created to reconcile the correction.

### GSTR-06 — HSN summary (Table 12) silently drops all e-commerce-operator (SUPECOM) invoice lines — **Medium-High**
**File:** `reporting/gst_returns.py:409-423`
A `continue` on the SUPECOM branch exits the loop before `accumulate_hsn_line` runs — any invoice with an `ecommerce_operator_gstin` set is completely excluded from the HSN aid, with no warning.

### GSTR-07 — Credit/debit notes against export invoices under the B2CL threshold get netted into domestic B2CS buckets — **Medium-High**
**File:** `reporting/gst_returns_sections.py:199-223`
`build_note_rate_rows` never routes notes through the same export/SEZ detection used for invoices; a note against a ≤₹1L export invoice falls through into the generic domestic B2CS branch, contaminating the domestic B2C summary with zero-rated export adjustments and silently disappearing from the export totals (which never net notes against them either).

### GSTR-08 — Nil-rated detection only triggers when *every* line on an invoice is 0% — **Low-Medium**
Mixed-rate invoices (common — e.g. one exempt service line plus taxable goods) leave their 0% portion as an untagged zero-rate row inside the regular B2B/B2C bucket instead of the dedicated nil-rated aid.

### GSTR-09 — Deemed exports (DEXP) are lumped into the same list/shape as physical exports — **Low-Medium**
GSTN treats deemed exports (Table 6C, B2B-like, recipient GSTIN required) very differently from physical exports (no recipient GSTIN) — mixing them into one shared row shape means neither cleanly matches its statutory counterpart, requiring manual post-filtering by a CA.

### GSTR-10 — No footing/reconciliation check between header-derived and line-item-derived outward totals — **Medium**
**File:** `reporting/gst_returns.py:543-591`
Two independent totals (`outward_taxable` from invoice headers, `section_taxable` from re-derived line items) both appear in the same payload with no comparison — if they ever disagree (e.g. a rounding/allocation edge case elsewhere), nothing in the tool surfaces it or tells the CA which to trust.

### GSTR-11 — QRMP (quarterly filer) scheme is entirely unmodeled — every period is assumed monthly — **Medium**
**File:** `reporting/gst_periods.py` (whole file)
No filing-frequency field, no quarterly period builder, no IFF (Invoice Furnishing Facility) support. A large fraction of Indian MSME GST taxpayers (turnover ≤ ₹5cr, QRMP-opted) file quarterly, not monthly — this tool's cadence doesn't match their actual filing pattern at all.

### GSTR-12 — No GST TDS (Sec 51 / GSTR-7) worksheet — only unrelated Income-Tax TDS/TCS (26Q/27EQ) is modeled — **Medium**
**File:** `reporting/tds_worksheets.py`
Honestly labeled for what it does (26Q/27EQ), but there's a real risk a less-GST-literate user conflates it with GST TDS if they sell to a government/PSU buyer — no GSTR-7-style aid exists for that scenario at all.

### GSTR-13 — GSTR-3B Table 5 (exempt/nil/non-GST *inward* supplies) not modeled — **Medium**
No corresponding bucket for exempt/nil/non-GST purchases (e.g. from a composition dealer) — a CA has to build this from scratch outside the tool.

### GSTR-14 — HSN-digit health check re-hardcodes the AATO threshold and skips the sub-₹5cr 4-digit B2B tier — **Low**
**File:** `reporting/gst_health.py:105-110`
Duplicates the ₹5cr constant instead of reusing the shared one (drift risk), and doesn't check the current CBIC rule requiring 4-digit HSN for B2B invoices below the ₹5cr threshold — only the ≥5cr/6-digit tier is checked.

### GSTR-15/16 — Export column names don't match the GSTN offline-utility template; no interest/late-fee line item — **Suggestion**
Real adoption friction (a CA has to remap headers) but not misleading — every export carries an accurate "not a GSTN portal upload file" disclaimer.

**What's done well (Reporting/GSTR):** ITC modeling is meaningfully conservative — GSTR-3B does *not* just report gross purchase tax as ITC; it's gated by both a per-invoice `itc_eligibility == CLAIMABLE` flag and (once ingested) an actual GSTR-2B match, with books-only ITC explicitly labeled "provisional" and excluded from the payable estimate; the B2CL threshold correctly reflects the current ₹1,00,000 rule (Notification 12/2024-CT) with a dated citation comment, not the stale ₹2.5L figure; SEZ/export/deemed-export are structurally distinguished from ordinary B2B rather than silently miscategorized; composition dealers are hard-blocked from the regular GSTR-1/3B builders and redirected appropriately; no overclaiming "ready to file" language exists anywhere in the codebase.

---

## 7. Accounts, Auth & Core Platform (Security)

*Scope: `accounts/models.py, views.py, otp_utils.py, serializers.py, password_validation.py, export_views.py, tenant_backup.py`, `core/permissions.py, viewsets.py, exceptions.py`, `core/services/notifications.py, sms.py, gstin_verify.py, feature_flags.py, registration_gates.py`, `config/settings.py`.*

### SEC-01 — Tenant export/restore has no cross-tenant provenance check — **Critical** *(verified directly against source)*
**File:** `accounts/tenant_backup.py:43-58,412-684`, `accounts/export_views.py:65-112`
`tenant_export_fernet()` is a single, **instance-wide** key (`settings.TENANT_EXPORT_FERNET_KEY`/`GSP_FERNET_KEY`, not derived per-company — confirmed by reading the function directly, it takes no company argument). `TenantRestoreView.post()` decrypts whatever blob is uploaded and passes it straight to `restore_to_sandbox()`/`restore_destroy_in_place()` **without ever checking `payload.get("source_company_id") == company.pk`**, even though `source_company_id` is present in the payload/manifest and available to check (confirmed by reading the view directly — no such comparison exists anywhere in the method).
**Failure scenario:** Because the encryption key is shared instance-wide, *any* valid tenant export blob decrypts successfully under *any* company's context. Any Owner-role user who obtains the encrypted bytes of another tenant's export (a shared support inbox, a misdirected email, a leaked backup file — plausible in any real support workflow) can `POST /company/restore/` as their own company. The sandbox-restore path (the default, no special confirmation) then creates a brand-new, permanently-owned company populated with the *other tenant's* full customer list, supplier list, sales/purchase history, bank account/IFSC/UPI details, and chart of accounts — a durable, self-service cross-tenant breach requiring nothing but possession of the file plus a valid Owner login on any company. The destroy-in-place path additionally lets a leaked export overwrite the attacker's own live company data with someone else's records.
**Fix direction:** Two independent fixes, both needed: (1) derive a per-company encryption key (e.g. HKDF over the instance key + company id) so Company A's export cannot even decrypt in Company B's context; (2) regardless, add the missing `payload.get("source_company_id") == company.pk` assertion in `TenantRestoreView.post()` before either restore path runs. Also add rate-limiting to the restore endpoint (export already has it; restore does not, despite being at least as destructive).

### SEC-02 — GSTR/Tally "dark" features are gated in the frontend but not enforced server-side — **Medium-High**
**File:** `core/services/feature_flags.py:17-19`, `reporting/views.py:281-303`, `integrations/views.py:29-173`
Manufacturing/Payroll/CRM/Account-Aggregator all have a genuine server-side `assert_*_enabled()` gate wired into their viewsets — a consistent, correct pattern the team clearly knows how to apply. `ENABLE_GSTR`/`ENABLE_TALLY` exist for exactly the same purpose (per the settings.py comment: "can unlock UI when VITE bake-off is false"), but the GSTR (`Gstr1View`/`Gstr3bView`/`Gstr9View`) and Tally (`TallyUploadView`/`TallyCommitView`/etc.) endpoints never check them — only role/capability permissions gate *who* can call them, not *whether the feature is meant to be live*.
**Failure scenario:** With `ENABLE_GSTR=0`/`ENABLE_TALLY=0` (the default) meant to keep these preview/dark features hidden from the UI, any Owner or Accountant-role user with ordinary financial-report/export capabilities can call these endpoints directly — generating real GSTR filing exports or committing a real Tally sync — despite the product explicitly marking them not-production-ready.
**Fix direction:** Add the same `assert_gstr_enabled()`/`assert_tally_enabled()` pattern already used for manufacturing/payroll/CRM.

### SEC-03 — OTP request has no per-phone-number rate limiting (only per-IP) — **High**
**File:** `accounts/views.py:346-383`, `config/settings.py:248-263`
The only throttle is DRF's `ScopedRateThrottle` (5/min), keyed by client IP for this unauthenticated endpoint — there is no cap keyed on the *target phone number*. Combined with the fact that each new OTP request creates a fresh challenge with its own fresh 5-attempt counter, an attacker can also effectively reset the brute-force budget against a given phone's OTP indefinitely by re-requesting.
**Failure scenario:** An attacker who knows a victim's phone number can trigger real SMS sends (billable, and a harassment vector) at up to 5/min per IP indefinitely, or unlimited via trivial IP rotation — a known Indian mobile-OTP abuse pattern.
**Fix direction:** Add a per-phone cache-backed cooldown/cap independent of the IP throttle (the codebase already has the `cache.incr`/`cache.add` pattern used for login-failure tracking in the same file — reuse it).

### SEC-04 — DLT-template compliance for SMS is not enforced, risking silent carrier-level filtering — **Medium**
**File:** `core/services/sms.py:32-47,64-88`
`MSG91_TEMPLATE_ID` is optional, not validated — the app will call the MSG91 API with no template ID at all if unset, and the API will report success even if the carrier later silently drops the message for TRAI DLT non-compliance. Twilio (used by `_send_twilio`) has no native DLT registration path at all, so OTP delivery to Indian numbers via Twilio is at real risk of silent carrier-level filtering regardless of what Twilio's API reports.
**Failure scenario:** Ops deploys with a provider/config combination that "succeeds" at the API level but a meaningful fraction of real Indian numbers never receive the OTP SMS — users are locked out with no diagnostic signal distinguishing "wrong number" from "DLT-blocked."

### SEC-05 — Branch GSTIN (`CompanyGstin`) format validation is weaker than the primary company GSTIN — **Low**
**File:** `accounts/serializers.py:288-301` vs `core/validators.py`
`CompanyGstinSerializer.validate_gstin` only checks length == 15, never the actual `GSTIN_RE` format regex used for the primary `Company.gstin` — a branch GSTIN can be any 15-character garbage string and still be accepted and used as a document stamp source.

### SEC-06 — OTP-request enumeration protection can leak through SMS-provider errors — **Medium**
**File:** `accounts/views.py:373-383`
The endpoint deliberately returns a uniform 200 regardless of registration status (good anti-enumeration design), but the OTP challenge is created *before* the SMS send, with no try/except around the send call — if the SMS provider raises (a realistic, not rare, occurrence), the resulting error response is only reachable for *registered* phones (since only registered phones reach the SMS-send call at all), reintroducing an enumeration oracle specifically during provider outages/rate-limit windows.

### SEC-07 — Tenant isolation is single-layer (app-level `company_id` filtering only, no DB-level RLS, opt-in base class) — **Medium** *(architectural risk, no confirmed leak in the files reviewed)*
**File:** `core/viewsets.py:8-19`, `config/settings.py` (`POSTGRES_RLS_ENABLED` off by default)
Every non-`CompanyScopedViewSet` view checked (~50 viewsets enumerated) *does* correctly filter manually today — no active leak found — but there is no automated safety net (no RLS, no system check, no generic cross-tenant test) that would catch a future PR forgetting to scope a new endpoint. Given RLS is explicitly "off by default until proven" per the README, this is the single point of failure the rest of the app's tenant-isolation story rests on.
**Fix direction:** Add a lightweight enforcement layer — either a startup check that every `ModelViewSet` on a company-scoped model derives from `CompanyScopedViewSet`, or turn on `POSTGRES_RLS_ENABLED` as the real second layer; at minimum, add a generic "log in as Company A, assert 404 on every route for Company B's IDs" test.

### SEC-08 — Sales/purchase/payment list views may show all staff's documents to any staff member with create-capability, not just their own — **Low/Suggestion**
**File:** `core/permissions.py:156-190`, `core/viewsets.py:30-31`
Contrast with `NotificationViewSet`, which deliberately scopes non-Owner visibility to `created_by=request.user` — sales/purchase/payment surfaces don't get the same treatment. May be intentional (shared visibility for stock/customer continuity is common in shop workflows) — flagged for a product decision, not a confirmed bug.

### SEC-09 — `DEBUG` defaults to on when `DJANGO_DEBUG` is unset — **Low** *(well-mitigated by other guards)*
**File:** `config/settings.py:28`
The insecure default is "opt out, not opt in," though multiple independent guards (host/env checks) make an actual accidental prod-with-DEBUG deployment hard to achieve in practice. Still worth flipping the default for defense-in-depth.

**What's done well (Accounts/Core — genuinely strong areas):** OTP handling itself is cryptographically sound end-to-end — `secrets.randbelow` generation (not `random.random()`), HMAC-SHA256-with-pepper storage (plaintext never persisted), constant-time comparison, single-use consumption under a row lock inside one transaction; the SMS provider layer fails closed (raises rather than silently no-op'ing on missing credentials, and hard-blocks stub/console providers outside dev/test). GSTIN verification (`gstin_verify.py`) and WhatsApp delivery-status reporting are both unusually careful to never claim a stronger guarantee than what actually happened — directly preventing the "misleading users about compliance" failure mode this review was watching for. Role/capability defaults are least-privilege by design with server-side invariant enforcement (a non-Owner cannot grant themselves financial-report/export capability via a role edit). Production-hardening in `settings.py` actively guards against most classic Django misconfiguration classes (DEBUG-in-prod, wildcard ALLOWED_HOSTS, insecure SECRET_KEY, CORS+credentials wildcard, SQLite-in-prod) at import time, not just in documentation. `TIME_ZONE = "Asia/Kolkata"` with `USE_TZ = True` correctly ensures IST-accurate invoice dating, not UTC-only.

---

## 8. Frontend UX (`web/src`)

*Scope: sales/purchases/POS/payments/inventory pages, `PartySelectPanel`, `DocumentTaxSummary`, `EinvoiceEwayPanel`/`ChallanEwayPanel`/`NoteEinvoicePanel`, `DocumentListPage`, i18n catalogs, offline outbox, validation/formatting utils.*

### FE-01 — POS checkout has no working idempotency-key protection on the primary online path — **Critical**
**File:** `web/src/pages/pos/PosPage.tsx:95,345`, `web/src/api/client.ts:201-209` *(verified directly)*
`idempotencyKey` component state starts `null` and is only ever set on the *offline*-enqueue branch. On the ordinary online checkout path, `const key = idempotencyKey ?? undefined` is `undefined` on every call — and `idempotencyHeaders(key?: string)` **generates a brand-new random UUID whenever the key argument is undefined**, including on a retry. This is confirmed by direct comparison with the correct pattern used in `NewInvoicePage.tsx` (which pins the key into state *before* the first request specifically so a retry reuses it).
**Failure scenario:** A cashier on patchy shop-counter internet taps "Cash," the request is processed server-side but the response is lost to a network blip; the UI shows an error and re-enables the button; the cashier taps "Cash" again. A fresh idempotency key is generated for the retry, so the backend cannot deduplicate — two completed invoices, double stock deduction, double cash recorded for one physical sale.
**Fix direction:** Generate and pin the idempotency key into state before the first checkout attempt, exactly mirroring `NewInvoicePage.tsx`'s existing (correct) pattern.

### FE-02 — Purchases have no idempotency-key plumbing at all — **Critical**
**File:** `web/src/api/legacy/purchases.ts:41-74`
`createPurchase()` has no options parameter for an idempotency key at all — every call generates a fresh UUID unconditionally, structurally unable to deduplicate a retry. This is the primary "record a supplier bill" flow, used at least as often as sales invoicing.
**Fix direction:** Add the same `options?: { idempotencyKey?: string }` shape `createSalesInvoice` already has, and pin a key in `NewPurchasePage.tsx` before the first save.

### FE-03 — POS "UPI" button marks the sale as paid immediately on tap, with no QR and no confirmation step — **Critical**
**File:** `web/src/pages/pos/PosPage.tsx:538-545`
Tapping UPI goes straight through checkout → complete → create a `UPI`-mode receipt → allocate, marking the invoice fully paid **immediately**, with no QR code shown and no "confirm payment received" gate — even though a real UPI-QR capability already exists and works elsewhere in the same codebase (`InvoiceDetailPage.tsx`'s `getUpiQr`), it's simply not wired into POS.
**Failure scenario:** Customer says "I'm sending it now," cashier taps UPI to move to the next customer; the sale is already finalized as paid before the transfer is confirmed to have happened; if it never arrives, there's no natural point in the flow where the discrepancy surfaces, since the invoice is already `COMPLETED` and allocated.
**Fix direction:** Reuse the existing QR capability in POS and require an explicit confirmation tap after showing the amount-locked QR, rather than one tap doing both "charge" and "confirm paid."

### FE-04 — GSTIN/PAN/IFSC/PIN validators exist but are wired into only one screen — **Critical**
**File:** `web/src/utils/gst.ts:2-8` (`isValidGstin`), used only in `GstSettingsPage.tsx`
Not imported/called in `CustomersPage.tsx`, `SuppliersPage.tsx`, the inline "create party" dialogs on the invoice/purchase screens, `CompanySettingsPage.tsx` (own bank/UPI/pincode fields), or `BankAccountsPage.tsx` (IFSC). No PAN validator exists anywhere in the repo at all; no dedicated IFSC/PIN validators exist either.
**Failure scenario:** A cashier adding a new customer mid-invoice mistypes a GSTIN character (`0`/`O`, `1`/`I` confusion is common when copying from a physical card); nothing on the client flags it; the error only surfaces after a full server round trip, and — per FE-05 — as an unhelpful generic message.
**Fix direction:** Wire the existing (and new PAN/IFSC/PIN) validators into every field that currently accepts these values unchecked.

### FE-05 — Backend field-level validation errors are flattened to "Validation failed." with no field detail — **Critical**
**File:** backend `core/exceptions.py:78-84`, frontend `web/src/api/client.ts:175-192`
When DRF returns a `{field: [messages]}` dict, the backend's error handler doesn't match its "has a `detail` key" branch and falls through to a bare `"Validation failed."` string — the real per-field messages exist in `error.details` but the frontend's `getErrorMessage()` never reads that key, across every single call site in the app.
**Fix direction:** Extend `getErrorMessage` to read and join `error.details`; avoid collapsing dict-shaped validation errors to one string on the backend side.

### FE-06 — POS has no cash-tendered/change calculator — **High**
**File:** `PosPage.tsx:530-537`
The Cash button charges exactly the grand total; there is no "amount tendered" input or change computation anywhere. Real cash transactions rarely land exactly on the total, and paise-level coins aren't practically usable — this is a genuine counter-speed and arithmetic-error risk for the stated busy-shop persona.

### FE-07 — No per-line or per-cart discount control in POS — **High**
Only quantity +/− and delete exist on POS cart rows; the discount % / amount fields that already exist and work in the full invoice editor (`DraftLineTable.tsx`) aren't surfaced in POS, forcing a counter-side discount negotiation to abandon the fast-checkout flow entirely.

### FE-08 — Purchases have no offline draft outbox at all — **High**
**File:** `NewPurchasePage.tsx` (no reference to the offline outbox module anywhere)
Sales invoicing has a working offline-queue-and-flush mechanism (`offline/invoiceDraftCache.ts`); recording a supplier bill — at least as common a task — has none. A connection drop mid-entry on a large multi-line bill just fails with an error and no recovery path; navigating away loses everything typed.

### FE-09 — Barcode-scan-not-found gives zero feedback — **High** *(partially unverified — flagged honestly by the reviewing pass)*
**File:** `PosPage.tsx:184-198,427`
A scanned barcode with no product match does nothing visible — no toast, no message. A busy cashier can't tell if the scanner disconnected, the scan misfired, or the product genuinely isn't in the catalog. *(The reviewing pass separately flagged, as an unverified-but-plausible risk since the app wasn't run live, that the ~250ms search debounce might race against a hardware scanner's near-instantaneous Enter keystroke.)*

### FE-10 — List-page action mutations (Complete/Cancel/Run/Deactivate) silently swallow failures across at least 5 screens — **High**
**File:** `CreditNotesPage.tsx`, `DebitNotesPage.tsx`, `DeliveryChallansPage.tsx`, `RecurringInvoicesPage.tsx` (`runNow`/`deactivate`), sales/purchase-order "convert" mutations
None of these mutations have an `onError` handler — a backend-rejected action (e.g. cancelling a credit note that's referenced elsewhere) produces literally no visible feedback: no error, no success flash, nothing. A non-technical user repeatedly clicking a dead button with no signal is a worse experience than a confusing error message.
**Fix direction:** Add the same `onError: (err) => setError(getErrorMessage(err))` pattern already used correctly for page-level query errors in these same files.

### FE-11 — Tax breakup (CGST+SGST vs IGST) is shown but never explained — **Medium**
**File:** `DocumentTaxSummary.tsx:104-113`
No caption anywhere explains *why* a particular split was chosen (e.g. "Customer state differs from yours → IGST") — a first-time out-of-state sale showing only an IGST line with no CGST/SGST, and no explanation, reads to a GST beginner as a possible software error rather than a rule-driven outcome.

### FE-12 — Duplicate-GSTIN prevention doesn't exist anywhere in party creation — **High**
**File:** `PartySelectPanel.tsx`, `InvoicePartyPanel.tsx`
Party search is name-only (GSTIN isn't part of the searchable/display label until a party is already selected); the inline "create party" dialog has no lookup-before-create step and no client-side duplicate-GSTIN check.
**Failure scenario:** The same real-world party gets entered twice under slightly different name spellings, each with the identical GSTIN — splitting that customer's outstanding balance and purchase history across two records, and creating duplicate B2B counterparties in the eventual GSTR-1.
*(Note: whether the backend enforces GSTIN uniqueness at the model level was not conclusively established by the reviewing pass — if it does not either, this finding should be treated as Critical, not High.)*

### FE-13 — Numeric formatting bypasses `en-IN` (lakh/crore) grouping in two live spots — **Medium**
**File:** `components/billing/DraftLineTable.tsx:182` (per-line tax figure), `pages/settings/BillingPage.tsx:15-16` (subscription price)
The correctly-`en-IN`-grouped `formatMoney` utility is used pervasively across the app (a real strength — see below), but these two spots use raw `.toFixed()`, producing a visibly inconsistent, harder-to-read number (`₹123456.78`) sitting right next to a correctly-grouped total on the same invoice line-item table.

### FE-14 — App itself displays a permanent warning that its own core billing UI "is limited" on phones — **High**
**File:** `layouts/AppShell.tsx:235-237`
Shown on every page below the `md` breakpoint, directly contradicting the README's own framing of the Android WebView shell / PWA as an MVP-complete deliverable for exactly this workflow. Either the compact billing editor needs real investment, or the product's mobile-first messaging needs to be walked back to "viewing/light tasks only, billing needs a tablet/desktop."

### FE-15 — Offline-outbox sync failures are silently swallowed with no reason surfaced to the user — **High**
**File:** `offline/invoiceDraftCache.ts:290-292`
`flushOutbox`'s catch block just increments a `failed` counter with no captured reason; neither `PosPage.tsx` nor `NewInvoicePage.tsx` inspects it to explain *why* a queued sale didn't sync. A persistently-failing queued invoice (e.g. its customer was deleted while offline) will silently retry-and-fail forever with zero indication a real sale from yesterday never actually posted.

### FE-16 — Offline drafts have no staleness/conflict check on flush (price/stock may have changed) — **Medium**
The queued payload from while-offline is resubmitted as-is on reconnect with no re-check that the product's price/GST rate/active status hasn't changed in the interim — a stale price can silently post as the final invoice.

### FE-17 — "Data stored unencrypted" warning is shown permanently on every visit, regardless of relevance — **Medium**
Shown unconditionally on the invoice/POS screens at all times (online or offline, outbox empty or not) — genuine alert fatigue that will train users to ignore all yellow banners on these screens, including the actually-actionable place-of-supply warning that appears in the same visual language.

### FE-18 — Language switch triggers a full page reload mid-invoice — **Medium**
**File:** `components/LocaleSwitcher.tsx:12-24`
Both language buttons call `window.location.reload()` unconditionally; a `beforeunload` guard does prevent silent data loss for an in-progress invoice, but the interaction itself (native "leave page?" browser prompt for what should be a lightweight toggle) is jarring and confusing for a bilingual user switching languages out of habit.

### FE-19 — e-Invoice/e-Way/Note status chips show raw backend enum values, not plain language — **Medium**
**File:** `EinvoiceEwayPanel.tsx:206,283`, `ChallanEwayPanel.tsx:93`, `NoteEinvoicePanel.tsx:106`
Chips render `NONE`/`READY`/`GENERATED`/`FAILED` directly rather than through the i18n layer the way document-status chips already correctly do — a user unfamiliar with e-invoicing jargon has no way to interpret a grey "NONE" chip (not required? not started? broken?).

### FE-20 — MUI `TextField select` uses raw `<option>` children instead of `<MenuItem>` — **Medium**
**File:** `pages/inventory/StockAdjustmentPage.tsx:107-111`
Every other select-mode field in the codebase correctly uses `<MenuItem>`; this is a known MUI anti-pattern that risks a broken/unstyled dropdown for warehouse selection on stock adjustments (not confirmed live, since the reviewing pass didn't run the app, but it's a well-known failure mode).

### FE-21 — Inline item-creation dialogs (mid-invoice "add new product") bypass the HSN format validator used elsewhere — **Medium**
Same generic-error consequence as FE-04/FE-05 when it fires.

### FE-22 — POS silently auto-selects the first customer in the list as a default, with no explicit "Walk-in" option — **Medium**
A cash walk-in sale can get silently attributed to an arbitrary real customer's account/history if the cashier doesn't notice and actively change the selection.

### FE-23 — e-Invoice/e-Way panel copy leaks raw REST endpoint paths into user-facing text — **Low**
**File:** `NoteEinvoicePanel.tsx:99-102`
Literally interpolates a URL path fragment into the Alert shown to the user.

**What's done well (Frontend):** Hindi localization is structurally complete — verified by diffing the compiled `en.ts`/`hi.ts` catalogs programmatically, not spot-checked: 511/511 keys present in both, zero interpolation-placeholder mismatches, and the only byte-identical strings between the two are legitimate untranslated acronyms (GSTR-1, HSN/SAC, MRP, etc.) — this directly refutes the "silently falls back to English mid-sentence" risk this review was watching for. Currency formatting via `Intl.NumberFormat('en-IN', ...)` is correct and used pervasively (the two leaks noted above are real but narrow exceptions, not the norm). The tax engine on the frontend mirrors the backend's fail-closed place-of-supply design — it explicitly returns "unknown" rather than guessing intra/inter-state from string equality, and blocks Complete on an unresolvable place of supply for GST invoices, a genuine safeguard against silently-wrong tax splits. The offline-outbox *idempotency-key generation itself* (as opposed to its wiring into POS/Purchases, per FE-01/FE-02) is sound — a key is generated once and reused across retries for anything that actually reaches the queued path. `NumericField` correctly uses `inputMode="decimal"` everywhere, avoiding native-number-input quirks on mobile. The inline "quick-add customer" dialog on the invoice screen correctly preserves the in-progress invoice underneath it rather than navigating away and losing entered lines. PDF-generation status polling (`PdfStatusPoller.tsx`) is a good pattern — plain-language states, exponential backoff, explicit retry — worth extending to the e-Invoice/e-Way status chips (FE-19).

---

## Cross-Cutting Themes

A few root causes explain a disproportionate share of the findings above, and fixing them will resolve multiple line items at once:

1. **"Assume current master data instead of what was actually recorded" recurs three times** — SALES-01 (credit notes re-price off current price list/rate), GSTR-03/GSTR-05 (invoice amends leave no amendment trail and can retroactively change a filed period), and INV-05 (imported products bypass the same validator applied everywhere else). The underlying fix pattern is the same each time: when correcting or referencing a historical document, always copy forward the values *as they were at the time*, never re-resolve from current masters/settings.

2. **"Optional field silently defaults to the permissive/lossy choice" recurs across both backend and frontend** — TAX-01/TAX-05 (free-text state silently misread), PAY-02 (TDS fields silently dropped), PUR-09 (OCR rate silently snapped/defaulted), FE-05 (validation errors silently flattened). None of these fail loudly; they all produce a plausible-looking wrong result. A general team practice of "when in doubt, warn rather than silently substitute" would catch most of this class going forward.

3. **Idempotency-key protection is a proven, correctly-implemented pattern in two places (`NewInvoicePage.tsx`, the offline outbox) that simply wasn't propagated to two structurally identical paths** (POS online checkout, all of Purchases) — FE-01/FE-02. This is the cheapest fix-to-impact ratio in the whole review: copy an existing, working pattern to two more call sites.

4. **Tenant-scoping discipline is excellent almost everywhere it was checked**, which makes the one place it verifiably breaks (SEC-01, tenant export/restore) and the one place it's referentially incomplete (INV-04, price-list FKs) stand out as real outliers rather than a systemic weakness — worth fixing precisely because they're the exception to an otherwise strong pattern, not the rule.

5. **Server-side feature-flag enforcement is a proven pattern (manufacturing/payroll/CRM) not yet applied to two flags that exist for the identical purpose** (SEC-02, GSTR/Tally) — same "copy the existing pattern" fix shape as #3.

---

## Recommended Remediation Order

Given the findings cluster into a few fixable themes, a practical order (independent of which team member owns which module):

1. **SEC-01** (tenant restore) — single highest blast-radius issue; fix before any further pilot data is loaded.
2. **TAX-04** (40% GST slab) — one-line fix, currently blocks real billing today.
3. **FE-01 / FE-02** (idempotency keys for POS + Purchases) — copy an existing working pattern; prevents real double-invoice/double-stock incidents.
4. **TAX-01 / TAX-02 / TAX-03** (state-code misread, export POS code, e-Invoice buyer-GSTIN requirement) — these three compound on each other for any pilot customer doing exports; fix as one workstream.
5. **SALES-01 / SALES-02** (credit-note re-pricing, H9-A vs. e-Invoice IRN) — compliance-integrity issues that get worse the longer the product is in production use before they're caught.
6. **INV-01** (WAVG→FIFO switch) — low-likelihood but hard-blocks billing entirely when it hits; cheap to guard.
7. **PUR-01 / PUR-02 / PUR-03** (ITC/books divergence, RCM, composition-supplier handling) — a coordinated purchases-side pass, since all three touch the same code paths.
8. **PAY-01** (dashboard double-count) — quick fix, visible to every user of the dashboard.
9. Remaining High-severity items, module by module.
10. Medium/Low items as ongoing hardening — many are single-file, low-risk fixes (validators, warnings, i18n on status chips) suitable for interleaving with feature work.

---

*End of review log. ~123 findings across 8 module passes; 3 of the most severe independently re-verified against source during compilation.*
