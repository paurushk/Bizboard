# Bill Upload / Import — Redesign Plan

Status: Phases 0–3 implemented; Phase 4 partially implemented (see commit `imports`/`core.services.llm`/`web` changes on this branch). Not built: side-by-side source-image review viewer, a settings UI for editing `SupplierBillTemplate` rows by hand, and email-forward ingestion (explicitly out of scope per §7 Phase 3).
Owner: TBD
Scope: `backend/imports/`, `backend/core/services/llm.py`, `backend/purchases/`, `backend/sales/` (existing — `SalesInvoice`/`SalesItem` already implemented, see `backend/sales/models.py:7,155`), `backend/masters/` (`Customer` model), `backend/inventory/` (stock-posting implications on commit), `web/src/pages/purchases/PurchaseBillUploadPage.tsx` (and new sales equivalent). See §11 for a full per-phase touchpoint map.

## 1. Problem statement

The upload-bill feature exists end-to-end (`ImportJob` → LLM vision extraction → review → commit) but breaks down on real-world distributor bills like the sample DMS tax invoice this plan is based on: 30+ dense line items, a vendor-specific column vocabulary (`Cs` / `Pcs` / `UPC` / `Pc Price` / `Gross Amt` / `Sch Amt` / `Disc Amt`), and only a purchase-side commit path. Today, when the model can't confidently map a column it either silently guesses (dangerous) or leaves it blank with a generic "low confidence" flag (unhelpful — doesn't tell the user *what* is uncertain or *why*).

The baseline we're designing against: **a user manually keying in a 30-line bill like this takes 20–30 minutes and is exactly the kind of repetitive, error-prone data entry software should eliminate.** Every design decision below is judged against that baseline — does it get closer to zero manual keystrokes for a bill the system has seen this vendor's format before, and does it ask smart, minimal questions (not force full manual entry) the first time it hasn't?

## 2. Design principle: optimize for zero-touch, not just "editable"

Being "reviewable" is not the goal — a bill review screen with 30 rows × 8 editable columns is still a manual-entry task with extra steps. The actual goal is:

- **First bill from a new vendor**: the user answers a handful of targeted yes/no or multiple-choice questions (not 30 rows of free text), then reviews a table that's already ~95% correct with the ambiguous parts flagged.
- **Every subsequent bill from that vendor**: near-zero questions, near-zero corrections — the system applies what it already learned.
- **Never silently guess** on something structurally ambiguous (a column's *meaning*). Only ever silently proceed on something it's actually confident about, and cross-check even that against the bill's own printed totals.

This reframes the work from "improve OCR accuracy" (which has a ceiling) to "build a system that gets smarter per-vendor and asks for help precisely, not broadly" (which compounds over time as more bills are processed across all users of a given distributor).

## 3. Current state (for reference)

- `ImportJob` (`backend/imports/models.py`) — only `Kind.PURCHASE_BILL` exists; no sales-bill ingestion at all.
- Extraction is a single LLM vision call per bill (`backend/core/services/llm.py:274`, prompt at `:14`) — general-purpose Indian-GST-invoice prompt, no per-vendor knowledge, no cross-validation against the bill's own subtotal/total columns.
- Review UI (`web/src/pages/purchases/PurchaseBillUploadPage.tsx`) shows a flat editable table; MRP is extracted but not shown; batch/expiry (supported by `PurchaseItem`) is never asked for; a front-end bug (`normalizeLines`, lines 51/55) currently re-fills deliberately-blank "unread" fields with fake defaults (`qty=1`, `gst=18`), hiding exactly the rows that need attention.
- Commit path (`BillImportService.commit`, `backend/imports/services.py:531`) creates a draft `PurchaseInvoice` only.

## 4. Target architecture

### 4.1 Multi-format ingestion

| Format | Handling |
|---|---|
| Photo (JPEG/PNG/WEBP/HEIC) | LLM vision extraction (current path, hardened — see 4.2–4.3) |
| Multi-page PDF | Rasterize pages up to a **soft cap of 20** (warn the user extraction may be slow/partial beyond this) and a **hard cap of 50** (reject with a clear message — this is almost always a non-invoice file, not a genuine bill). Extract page-by-page rather than loading the whole rasterized set into memory at once, to bound worker memory on large files. Merge line arrays with page provenance per line. |
| CSV / XLSX export from another ERP/DMS | Deterministic column-mapped import (existing `ImportService` path) — exact and free of vision-model risk. |

**UI decision, not a hidden default:** the upload screen offers two explicit entry points rather than guessing from the file type — **"Upload a bill photo/PDF"** and **"I have an export from my supplier's system"** (CSV/XLSX). The second path skips OCR entirely and, after upload, shows a lightweight column-mapping confirmation screen (map file columns → fields once per source system, reusable like the vendor bill template in §4.4). Most users won't know their distributor's export capability up front, so this is a persistent choice on the upload screen, not a one-time question — a user can try the photo path today and switch once they discover their distributor's DMS can export a file.

Email-forwarded invoices are **out of scope for this plan** — ingesting a mailbox (multi-invoice emails, non-invoice attachments, threads/replies) is a distinct product feature with its own design surface, not a variant of file upload. Track separately if prioritized.

### 4.2 Extraction pipeline with self-validation

Two categories of uncertainty need two different mechanisms — conflating them is the root cause of today's silent-guess problem:

**A. Row-level uncertainty** (a smudged digit, a stamp over one number, a value illegible on one specific line) → confidence-flag that cell only, as today, but make the flag actually visible in the review UI (fix the front-end bug that currently hides it). This is never asked as a question — it's surfaced as a flagged row for the user to glance at and correct in place.

**B. Document-level semantic ambiguity** (what does `UPC` mean on *this* vendor's invoice — a price or a per-carton unit count? Is `Pcs` total units or loose units in addition to `Cs`?) → this is not a confidence problem, it's a missing-fact problem that applies to *every* row the same way. Guessing is wrong even at "high confidence" because the model is choosing between two structurally different, both-plausible interpretations. This is resolved by asking **once per document** (not once per row), and the answer is applied uniformly across all lines.

Keeping this split explicit matters: a document-level question asked once (~3 max) keeps the clarification loop cheap; if row-level uncertainty were also routed through the question flow, a 30-line bill could generate dozens of prompts and defeat the entire "less pain than manual entry" goal.

**Arithmetic cross-validation**: every printed tax invoice already contains its own answer key — line subtotals, tax amounts, and net amounts. Once column semantics are known (from a vendor template or user answer), recompute each line's derived total from the extracted inputs and compare to the bill's printed total for that line. A mismatch beyond tolerance means one of the inputs was misread — flag that specific line (a row-level flag, category A above), don't trust the derived value blindly. Example from the sample bill: `Gross Amt = ((Cs × UPC) + Pcs) × Pc Price` — this formula, once confirmed for this vendor, becomes a standing check on every future line from them.

This cross-check has real edge cases that the template (§4.4) must account for, not just the raw formula:
- **Formula varies by vendor** — some apply discounts at line level, some as a lump sum on the invoice header (not attributable to any single line); some compute tax inclusive of MRP, others exclusive.
- **Header-level discounts** (a bill-wide rebate/scheme not broken out per line) make a pure per-line recomputation fail even when every line was read correctly — the template needs to know whether such a discount exists on this vendor's format and exclude affected lines from the per-line check (or check against the header total instead).
- **Rounding tolerance is not universal** — default to ₹0.50 per line, but store it as a per-template setting so a vendor whose printed totals round more loosely doesn't generate constant false-positive flags.

### 4.3 Clarification loop (new)

When extraction detects category-B ambiguity (a column whose role can't be determined from context or a stored vendor template), it returns a small structured question set instead of guessing:

```json
{
  "clarifications": [
    {
      "field": "upc_column",
      "question": "What does the 'UPC' column mean on this vendor's bill?",
      "options": [
        {"value": "unit_price", "label": "Price per piece"},
        {"value": "units_per_case", "label": "Pieces per carton (a count, not currency)"}
      ]
    }
  ]
}
```

- Shown as a short form **above** the line-item table, answered once, applied to the whole document immediately (recomputing dependent columns client-side, no re-upload needed).
- The answer is persisted as part of a **per-supplier bill template** (4.4) so it is never asked again for that vendor.
- Same mechanism resolves the purchase-vs-sales direction question (4.5) when GSTIN-matching against the company's own registered GSTIN is inconclusive.
- Hard cap on document-level question count per upload (e.g. 3) — if extraction is so unclear it needs more than that, fail over to **manual entry mode**, which is *not* a blank form: it's the same review screen, with every field editable (not just flagged ones), OCR-suggested values still shown as placeholders/starting points, and the cross-check simply disabled (no template exists yet to check against). A user who completes manual entry this way can save their corrections as a new vendor template on commit, so the next bill from that vendor skips manual mode entirely.

### 4.4 Per-vendor bill templates (new)

New model, `SupplierBillTemplate` (or a JSON field on `Supplier`):

- Matching signature, in priority order — **not just an exact-header match**, because vendors reorder columns between bills without changing their meaning:
  1. **GSTIN** (exact match) — primary key.
  2. **Column presence + name set**, fuzzy-matched — same columns present (`Cs`, `Pcs`, `UPC`, `Pc Price`, ...) regardless of left-to-right order. This is the real match test.
  3. **Column ordering** — used only as a confidence boost when present, never as a hard requirement; a reordered-but-otherwise-identical layout should still auto-apply the template, not trigger re-clarification.
- Stores: resolved column→field mapping, `line_total_formula` (the Gross Amt-style formula), `tax_calculation_type` (inclusive / exclusive / header-level), `rounding_tolerance` (default ₹0.50, overridable per vendor), confirmed-by/at.
- **Upload flow with a known template**: apply mapping silently, run cross-validation, surface only lines that fail the check. No clarification questions. This is the "near-zero touch on repeat bills" path that makes the whole redesign worth it — first bill from VTC Tradewings costs the user ~3 questions + a review pass; every bill after costs a glance at 0–2 flagged rows.
- **Upload flow with a stale/mismatched template** (vendor changed their invoice layout — the column *name set* itself differs, not just order): fall back to asking clarification questions again, and update the stored template.
- Template edits are user-correctable at any time from a supplier settings page (for when a user notices a systematic misinterpretation after the fact).
- **Sharing scope decision**: start **per-company only**. Cross-company/crowd-sourced templates (one user's confirmed VTC Tradewings mapping helping every other Bizboard user who buys from the same distributor) would compound the learning curve faster, but introduces data-sharing and trust questions (a malicious or simply wrong shared template silently misreading someone else's bills) that deserve a deliberate call, not a default. Revisit as a Phase 4+ feature with explicit opt-in and a confirmation-count trust score, once the per-company mechanism is proven.

### 4.5 Purchase AND sales ingestion

Today only `PURCHASE_BILL` exists. `SalesInvoice`/`SalesItem` already exist (`backend/sales/models.py:7,155`) — this is new *ingestion into* an existing model, not a new sales module. Add `Kind.SALES_BILL` (or a `direction` field) with a parallel commit path mirroring `BillImportService`, matching against `masters.Customer` instead of `Supplier`.

- **Direction inference**: a company can be registered under multiple GSTINs (branches/states), so matching against a single "the company's GSTIN" isn't sufficient. Store the **list** of the company's own registered GSTINs (all branches) in the company profile, then:
  1. Bill's GSTINs match exactly one of the company's own → direction is the opposite side (company as seller → sales; company as buyer → purchase).
  2. Both bill-party GSTINs belong to the company (intra-group/branch transfer) → ambiguous; ask via the clarification mechanism rather than guess (a stock transfer is not the same accounting event as a sale or purchase).
  3. Neither GSTIN matches → ask.
- The LLM prompt splits into a shared "read the invoice table" core plus a small direction-specific instruction for which GSTIN block is "us."
- **Sales-side specifics that differ from the purchase path**: line matching resolves against `Customer`, not `Supplier`; GST on a sales invoice is *output* tax the company is liable for (vs. input tax credit on purchases) — the commit path records what's printed on the bill rather than recalculating output tax independently, consistent with how the purchase path already treats OCR'd amounts as authoritative once validated; B2B sales additionally warrant validating the customer's GSTIN format/checksum, which the purchase path doesn't need to do for the company's own identity.

### 4.6 Review UX (redesigned)

Goal: reviewing should feel like proofreading a mostly-correct document, not filling a form.

- **Split view**: extracted table on one side, zoomable source image/PDF on the other, so a flagged row can be visually checked against the original without navigating away.
- **Flagged rows sort to the top and are expanded by default** with a clear visual marker (e.g. orange/red border); **clean rows stay visible but collapse to a compact one-line summary** (name + total) that the user can expand to verify if they choose — collapsing must never mean *hiding*, since a row the cross-check missed would otherwise commit unreviewed. A progress indicator ("2 of 30 rows flagged for review") makes clear the other 28 were checked and passed, not skipped.
- **Column tiers**: always-visible (name, qty, unit price, GST%, MRP) vs. advanced/expandable (HSN, SKU, batch, expiry) — most bills don't need the advanced tier touched at all.
- **Bulk actions**: "accept all high-confidence lines," "apply this correction to all rows with the same issue" (e.g. if GST% misread as blank across 5 rows because of one shared column-alignment issue, fixing one offers to fix all).
- **MRP shown and editable** (currently extracted but hidden — fix as part of this redesign).
- **Batch/expiry fields**: optional per line, extracted when legibly printed, otherwise a single lightweight prompt ("this bill has batch numbers — capture them?") rather than 30 empty boxes nobody fills.

## 5. Data model changes

- `imports.ImportJob`: add `direction` (`PURCHASE`/`SALES`) or split `Kind`; add `clarifications` JSON field (asked + answered) alongside existing `preview`.
- New `SupplierBillTemplate` (or `Supplier.bill_template` JSON field): column mapping, derived formulas, layout signature, confirmed_by/at.
- `PurchaseItem`/new `SalesItem` line already support batch/expiry — no schema change needed there, just wiring the import pipeline to populate them.

## 6. Walkthrough with the sample bill

1. User uploads the VTC Tradewings photo, picks "photo/PDF" (no CSV export available).
2. No `SupplierBillTemplate` exists yet for this GSTIN → extraction runs, detects the `Cs`/`Pcs`/`UPC` ambiguity, returns 1 clarification question (not per-line, once for the document).
3. User answers: "UPC = pieces per carton." System recomputes Gross Amt for all 30 lines via the confirmed formula and cross-checks against the bill's printed Gross Amt column.
4. Review screen opens with, say, 27 clean rows collapsed and 3 flagged (arithmetic mismatch) at the top, split-view against the source photo. MRP is visible and editable; HSN/SKU tucked under "advanced."
5. User fixes/confirms the 3 flagged rows (maybe 2 minutes, not 25).
6. On commit, the column mapping + formula is saved as this vendor's template.
7. Next bill from VTC Tradewings: upload → template auto-applies → 0 questions → review screen opens with everything collapsed unless the cross-check flags something → commit.

## 7. Phased rollout

**Phase 0 — Stop the bleeding (fastest, do first)**
- Remove `normalizeLines`'s fake-default fallback (`PurchaseBillUploadPage.tsx:51,55`) entirely rather than patching it — the function's name ("normalize") is itself misleading for what it does (silently fills missing data), which is how the bug was introduced unnoticed. Unread fields should render as an em dash or explicit "—" with a flag icon, never as a fabricated `0`/`""`/default value, so an unread field is visually distinct from a genuinely-zero one.
- Surface MRP as an editable review column.

**Phase 1 — Self-validating extraction**
- Extend LLM schema to also return per-line printed subtotal/total.
- Add arithmetic cross-check (computed vs. printed) as a line-level flag.
- Split confidence handling: per-value flags vs. per-column semantic-ambiguity questions.

**Phase 1b — Clarification loop + vendor templates**
- `clarifications` response shape + review-screen question UI.
- `SupplierBillTemplate` model, matching logic (GSTIN + layout signature), apply-on-upload, update-on-mismatch.

**Phase 2 — Sales-bill ingestion**
- `Kind`/`direction` addition, `SalesInvoice` commit path, GSTIN-based direction inference, direction clarification fallback.

**Phase 3 — Format breadth**
- CSV/XLSX deterministic path exposed as an explicit upload-screen entry point (§4.1), with reusable column-mapping confirmation.
- Multi-page PDF soft/hard cap + page-by-page batched extraction merge.
- Email-forward ingestion is explicitly **excluded** from this phase (and from this plan) — track as a separate future initiative if prioritized; it has its own design surface (multi-invoice emails, non-invoice attachments, threads).

**Phase 4 — Review UX overhaul**
- Split source-image/table view, flagged-rows-first sorting with visible-but-collapsed clean rows and a review progress indicator, column tiers, bulk-accept/bulk-fix actions, optional batch/expiry capture.

Sequencing rationale: Phase 0 is a live bug actively hiding failures and should ship independent of everything else. Phase 1/1b is the highest-leverage change — it's what turns "OCR that's sometimes wrong" into "a system that knows what it doesn't know and gets smarter per vendor," which is the actual fix for the pain described. Phase 2 unblocks the sales-side use case directly. Phases 3–4 broaden reach and polish the experience once the core extraction trust problem is solved.

### 7.1 Rough effort sizing (t-shirt sizes, unverified)

These are order-of-magnitude guesses for scoping conversations only — not a committed estimate, since they depend on this team's actual velocity and current codebase familiarity, which I don't have visibility into. Treat as a starting point for an engineering lead to correct, not a plan of record.

| Phase | Rough size | Depends on | Parallelizable with |
|---|---|---|---|
| 0 — Bug fix | XS (part of a day) | — | Everything — ship immediately, standalone |
| 1 — Self-validating extraction | M | Phase 0 (shares review-screen code) | — |
| 1b — Clarification loop + templates | L | Phase 1 (needs the confidence/flag split in place first) | — |
| 2 — Sales ingestion | M | Phase 1b (reuses the clarification + template machinery) | Phase 3 |
| 3 — Format breadth | M | Independent of Phase 2 | Phase 2 |
| 4 — Review UX overhaul | M–L | Phase 1b (needs flag data to sort/group by) | Can start in parallel once Phase 1 lands; doesn't block on 1b's template logic |

## 8. Success metrics

- **Review screen time** (from review screen appearing to "Commit" clicked) for a known-vendor bill — target ≤30 seconds regardless of line count, since the template + cross-check should mean nothing to fix.
- **End-to-end time** (upload → extraction → review → commit, including variable upload/extraction wait) for a known-vendor bill — target ≤2 minutes. Kept separate from review-screen time because upload/extraction latency is an infrastructure concern, not a UX-design one, and conflating them would hide which lever actually needs pulling.
- **Clarification questions per upload**, trending toward 0 as template coverage grows across a user's supplier list.
- **Post-commit line-edit rate** (edits made to committed purchase/sales invoices, a proxy for import errors that slipped through review).
- **Invoice reversal rate** — the percentage of committed invoices later fully reversed or offset by a credit/debit note. This catches the failure mode per-line metrics miss: systematic errors (wrong vendor matched, wrong invoice date, wrong total) that don't show up as a line-item correction but force undoing the whole document.
- **% of uploads using CSV/XLSX vs. photo/PDF** — track whether the explicit CSV/XLSX entry point is pulling volume away from OCR-dependent uploads over time.

## 9. Risks & mitigations

- **Vendor changes invoice layout** → template staleness detection (column *name-set* mismatch, not just reordering — see §4.4) triggers re-clarification instead of silently applying a wrong stale mapping.
- **PII/bill data sent to third-party LLM** — inherent to vision-extraction; already disclosed via consent checkbox. Two further considerations to close out before this ships broadly: (1) confirm and document each configured LLM provider's (`backend/core/services/llm.py` supports OpenAI/DeepSeek/Claude) data-retention policy for submitted images, so the consent language is accurate rather than generic; (2) a self-hosted/on-prem OCR fallback remains a real longer-term option for companies unwilling to send bill photos to a third party at all — the CSV/XLSX path (§4.1) already sidesteps this for vendors who can export, which narrows how much on-prem OCR is actually needed.
- **Clarification fatigue** — hard cap on document-level questions per upload; if exceeded, fail over to manual-entry mode (§4.3) rather than an unbounded question chain.
- **Template drift across near-identical vendors** (e.g. same distributor, different branch GSTIN) — match on GSTIN first, but allow a user to explicitly link/share a template across GSTINs for the same distributor group.

## 10. Decisions made vs. still open

**Decided (with rationale) in this revision:**
- Template sharing scope: **per-company only for the initial build** (§4.4) — cross-company sharing compounds the learning-curve benefit but introduces trust/data-sharing questions that shouldn't be a silent default; revisit explicitly once the per-company mechanism is proven.
- Email-forward ingestion is **excluded from this plan's scope** entirely, not just deprioritized — it's a distinct feature.

**Still open, needs a stakeholder call:**
- Is a self-hosted/on-prem OCR fallback worth building at all, given the CSV/XLSX path already gives privacy-conscious users (or those whose distributor supports export) a non-LLM route? Or is that a large investment for a shrinking slice of traffic once §4.1's steering takes effect?
- Effort sizing in §7.1 is a rough guess pending real estimation from whoever picks this up — needs replacing with committed numbers before this becomes a scheduling input.

## 11. Code touchpoints by phase

| Phase | Backend | Frontend |
|---|---|---|
| 0 | — | `web/src/pages/purchases/PurchaseBillUploadPage.tsx` |
| 1 | `core/services/llm.py` (schema + prompt), `imports/services.py` (`_preview_bill_line`, cross-check logic) | Review table: flag rendering |
| 1b | New `SupplierBillTemplate` model + matching service, `imports/models.py` (`clarifications` field), `imports/views.py` | New clarification-question form component |
| 2 | `imports/models.py` (`Kind`/`direction`), new sales-side `BillImportService` equivalent wired to `sales/models.py`, `masters/models.py` (`Customer` matching) | New sales upload/review page (mirrors `PurchaseBillUploadPage.tsx`) |
| 3 | `imports/services.py` (CSV/XLSX path reuse), PDF rasterization (`pypdfium2` usage in extraction task) | Upload-screen entry-point toggle, column-mapping confirmation screen |
| 4 | Possibly `inventory/` if review-screen changes affect what's shown for stock/batch implications at commit | Full review-screen redesign: split view, row grouping, bulk actions |

Note: `backend/inventory/` and `backend/purchases/`/`backend/sales/` tax/HSN fields aren't modified by this plan directly — the import pipeline populates existing fields on `PurchaseItem`/`SalesItem` (batch, expiry, HSN already supported); no new tax-calculation logic is introduced, since the design principle is to *record* what's printed on the bill (validated), not recompute GST independently.
