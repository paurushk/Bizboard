# Sales / Purchase / POS UX Fix Plan — 2026-09-21

Source: 67-item issue list supplied by founder, covering Sales Invoice, Purchase
Invoice, Sales History, Quotation, Sales Order, Delivery Challan, Sales Return,
Credit/Debit Note, Recurring Invoices, Customers, Customer Ledger, Purchase
Order/Invoice, Stock Report, Reports, general usability, and POS.

**Method:** every item below was checked against the current code (backend
Django apps `sales`, `purchases`, `billing`, `ledgers`, `accounting`,
`masters`, `payments`, `reporting`; frontend `web/src/pages/{sales,purchases,
pos,reports,crm}`) before being assigned a fix, not assumed from the ticket
text alone. Several items turned out to already be implemented — those are
marked **No action** so effort isn't wasted re-building them. A handful can't
be scoped without more info from you — those are called out at the end.

**Status legend:** 🟢 Exists · 🟡 Partial · 🔴 Missing · ⚪ Needs repro/decision

**Update 2026-09-21:** the founder supplied 20 screenshots of a reference "bill book"-style
competitor app, answering #57 (the requested competitor comparison) and #51 (the
"ledger per screenshot" item) directly. Their content has been folded into the
relevant rows below as "Reference-app screenshot" notes, and into Section 6
(Customer Ledger) and Section 11 (ideas spotted that weren't in the original list).

---

## 1. Quick wins (P0) — mostly wiring/UI, existing backend support

| # | Issue | Current state | Fix |
|---|---|---|---|
| 6 | Tax vs no-tax invoice | 🟢 `invoiceType === 'NON_GST'` already gates GST fields ([NewInvoicePage.tsx](web/src/pages/sales/NewInvoicePage.tsx)) | No action |
| 8 | Test coverage for IGST/CGST/SGST by state | 🟢 [test_tax_calc_properties.py](backend/tests/test_tax_calc_properties.py), 14 files reference CGST/SGST/IGST | No action — expand only if new invoice-state fields are added below |
| 18/19 | Place of supply, CGST/SGST/IGST breakout shown on invoice creation screen | 🟢 **Live-confirmed 2026-09-21** — added a real item to a real invoice; the summary panel correctly split CGST ₹25.20 / SGST ₹25.20 | No action |
| 28 | Quotation validity date | 🟡 `Quotation.valid_until` exists in model | Verify/wire the field into `NewQuotationPage` form + PDF if not already rendered |
| 32 | Customer/product dropdown empty until typing | 🔴 `useCustomerSearch`/`useProductSearch` gated on `minChars` ([usePartySearch.ts:14,33](web/src/hooks/usePartySearch.ts)) | Fetch a default "recent/top" list when query is empty instead of blank |
| 44/45 | Credit/Debit note help text | 🟢 Already in [contextHelp/catalog/sales.ts:458-517](web/src/contextHelp/catalog/sales.ts) | Verify the `?` icon is actually visible on those pages; if so, no action |
| 46a | Recurring invoice: multiple line items | 🟢 Backend supports multi-item templates ([recurring.py:60-103](backend/sales/recurring.py)) | Verify the frontend recurring-invoice form doesn't artificially cap at one line; fix the form if it does |
| 47 | Customer search/sort | 🟡 Search + status filter exist, no sort | Add a sort dropdown (name / balance / recently active) |
| 53/55 | "What is RCM/ITC/BOE/cost center" | 🟡 Fields + inline text exist ([NewPurchasePage.tsx:1528-1980](web/src/pages/purchases/NewPurchasePage.tsx)), no tooltip | Add contextHelp entries (reuse the credit/debit-note pattern) for RCM, ITC eligibility, BOE, cost center |
| 61 | "What is e-invoicing" | 🟡 Payload builder exists but **no live IRP submission** ([einvoice_payload.py:1](backend/sales/einvoice_payload.py)) | Add help content explaining e-invoicing. **Decided 2026-09-21: real IRP submission is in scope**, tracked as its own project (not part of this fix plan) — sizing needs IRP credential/API research, NIC sandbox testing, and IRN/QR response handling; scope that separately before estimating |

## 2. Sales Invoice / Purchase Invoice (P1/P2)

| # | Issue | Current state | Fix | Effort |
|---|---|---|---|---|
| 1 | No delete, needs cancel/return | 🟢 Draft delete + `cancel` action + full `SalesReturnViewSet` already exist ([views.py:226-228,461-469,719-797](backend/sales/views.py)) | Likely a discoverability gap, not a code gap — confirm these actions are visible in the row menu; relabel if unclear | S |
| 2 | Backdated invoice, sequencing continues | 🟢 `DocumentNumberService.next_number(..., on_date=)` already resolves the right FY/GSTIN series for any date ([document_numbers.py:362](backend/core/services/document_numbers.py)) | No action — verify UI doesn't block past dates | S |
| 3 | All invoice settings centralized on Sales Invoice page | 🟡 Number series centralized; **custom fields are not** (see #26) | Reference-app screenshot shows the target shape: a single "Quick Settings" modal off the invoice page with three tabs — **Invoice Details** (prefix/sequence toggle + live number preview, custom-field visibility keyed to an "Industry Type" dropdown that suggests relevant fields e.g. PO Number/E-way Bill Number/Vehicle Number), **Party Details** (party-level custom fields), **Item Table Details** (column show/hide, item-level custom fields e.g. Brand/Batch/Exp Date, plus a "show purchase price while adding items" and a "Price History" toggle). Build this as one settings surface rather than scattering config across pages | M |
| 4 | ~~Month-based prefix (26/Sep(09)/…)~~ | — | **Discarded 2026-09-21 (founder decision) — not going in this plan.** FY-based prefix stays as-is; no month-segment work | — |
| 5 | Invoice type + brief description | 🟡 Types exist (GST/TAX/RETAIL/NON_GST), no explainer text per option | Add one-line description under each dropdown option (same contextHelp pattern as #44/45) | S |
| 7 | Grand total editable, line items auto-back-calculated | 🔴 Total is currently read-only, one-directional (items→tax→total) | Real feature build: allow editing the grand total and proportionally back-solve line amounts/discount. Needs its own spec — rounding and multi-tax-rate edge cases are non-trivial | L |
| — | **New finding, 2026-09-21: stale line-item display after preview updates the total** | 🔴 Live-confirmed. Added "A4 Copier Paper 75 GSM" (HSN 480256, same HSN-rate-table trap as the POS finding in Section 12) to a real invoice. The **document-level Total Amount correctly updates** to ₹330.00 (18%, matching what actually gets booked — the backend preview itself is correct here, confirmed via direct API calls with/without `invoice_date`). But three sub-displays on the same screen never refresh: the line's own **TAX cell stays "12% (₹33.60)"**, the line's **AMOUNT stays ₹313.60**, and the **Balance Amount box stays ₹314.00** — all stale, alongside a correct ₹330.00 footer total. A user sees a self-contradictory invoice before ever clicking Complete | These three displays are rendering from local line/form state instead of the resolved `usePreviewTotals` response; wire them to the same preview result the footer total already uses correctly | M |
| 9/10 | Cheque payment mode with details + copy; instrument ID + receiving bank for other modes | 🟡 UPI/BANK already capture reference + bank account ([payments/services.py:259-334](backend/payments/services.py)); **no CHEQUE mode at all** — `PaymentMode` enum lacks it ([payments/models.py:9-14](backend/payments/models.py)) | Add `CHEQUE` to `PaymentMode`, add cheque number/bank/date fields, add attachment upload for the cheque image/copy | M |
| 11 | Signature: upload or empty box | 🟢 Upload-based signature exists ([NewInvoicePage.tsx:1279-1287](web/src/pages/sales/NewInvoicePage.tsx)); reference-app screenshot confirms the target is exactly two options in one modal: "Upload Signature from Desktop" and "Show Empty Signature Box on Invoice" (no draw-canvas) | Add the missing second option as a toggle next to the existing upload — small addition, not a new feature | S |
| 24/25 | Line-item description shown on invoice + resizable | 🔴 `description` is carried in data mapping but has no input field in the line-items table ([NewInvoicePage.tsx:460-461,749](web/src/pages/sales/NewInvoicePage.tsx)) | Add a resizable textarea per line item (mirror the existing header notes/terms field, which is already `minRows`/`maxRows`), render it on the PDF template | M |
| 26 | Custom fields configured in settings don't show on invoice | 🔴 Confirmed bug — custom fields are scoped to `Product` only ([masters/custom_fields.py:69,75](backend/masters/custom_fields.py)); no invoice-level custom-field model exists at all | The reference app treats custom fields as **three distinct scopes** — invoice-header, party, and item/line — each configured and rendered separately (see #3's Quick Settings spec). Build the same split: an invoice-level custom-field-values model (currently entirely absent) alongside the existing product-scoped one, render both in the settings UI and on the invoice form/PDF. This is the highest-effort item in the invoice section | L |

## 3. Sales History (P1/P2)

| # | Issue | Current state | Fix | Effort |
|---|---|---|---|---|
| 12 | Draft invoices sort before completed | 🔴 Ordering is `["-invoice_date", "-id"]` only ([models.py:176](backend/sales/models.py)) | Add status-aware default ordering (drafts first) or a one-click "Drafts" quick filter | S |
| 13 | Payment confirmation on finalize (amount, discount, date, mode, remarks) | 🟡 `complete` already takes amount/mode/reference/notes/bank_account; missing explicit **discount** field and a distinct **payment date** (currently reuses invoice date) | Reference-app screenshot gives an exact target: a "Record Payment" modal with Amount Received, Payment-In Discount (separate from any line-item discount, with an info tooltip), Payment Date picker, Payment Mode dropdown, Notes — plus a live calculation panel (Invoice Pending Amt → Amount Received / Discount → Balance Amount) alongside the invoice's own Amount/Party/Due Date. Add discount + payment-date fields to the complete-invoice payload and build this modal | M |
| 14a | See which invoices are paid/partial/unpaid | 🟡 Shown as a per-row chip (`paidAwareStatus`) but not filterable | Add a payment-status filter alongside the existing status chips | M |
| 14b | Calendar-based stats by payment status (today/week/15d/month/365d/custom) | 🔴 `HistoryFilterBar` only has raw from/to date pickers ([HistoryFilterBar.tsx:75-95](web/src/components/HistoryFilterBar.tsx)) | Add date-range presets + a stats strip cross-tabbing paid/partial/unpaid counts and amounts | M |
| 16 | Share invoice option | 🔴 Row menu has Open/Edit/Complete/Print/Download/Thermal/Cancel/Delete, no Share ([SalesHistoryPage.tsx:379-475](web/src/pages/sales/SalesHistoryPage.tsx)) | Backend already has a WhatsApp-send capability ([whatsapp_send.py](backend/sales/whatsapp_send.py)) — check if it's usable and wire it (plus a generic "copy link") into the row menu | M |
| 17 | Each invoice shows profit details | 🟡 Separate reports exist ([InvoiceProfitReportPage.tsx](web/src/pages/reports/InvoiceProfitReportPage.tsx)) but not inline on the invoice/list row | Surface margin on the list row or invoice detail view — gate behind a permission if cost visibility is sensitive | M |
| 20 | HSN-wise CGST/SGST/IGST shown % and amount | 🟡 Backend aggregation exists for GSTR-1 ([gst_returns_sections.py:9-21](backend/reporting/gst_returns_sections.py)) but not surfaced as a per-invoice table. Reference-app screenshot shows the exact target: an HSN/SAC row with Taxable Value, CGST (Rate, Amount), SGST (Rate, Amount), Total Tax Amount, printed under the invoice's tax summary | Add an HSN-wise breakout table to the invoice PDF/print template (reuse the GSTR-1 aggregation logic per-invoice instead of per-period), and surface the same table as a standalone report | M |
| 21 | Search by party name, invoice number, mobile | 🟡 Backend `q` filter only matches `number__icontains` ([views.py:201-202](backend/sales/views.py)); name/mobile not searched | Extend the queryset search to join customer name + phone | M |
| 22 | Bulk action (bulk download) | 🔴 No row-selection UI in Sales History | Add checkbox selection + a bulk PDF export (zip) endpoint | M/L |
| 23 | Sales reports: summary, GSTR-1, day book, bill-wise profit | 🟡 GSTR-1 and bill-wise profit exist; `SalesReportPage` is just a CSV register, not a summary dashboard; no true "day book" (Cash Book is a partial substitute) | Reference-app screenshot confirms the target report set exactly: a "Reports" dropdown with **Sales Summary, GSTR-1 (Sales), DayBook, Bill Wise Profit** as four distinct named reports — DayBook is its own report there, not a relabeled Cash Book. Build a real sales-summary dashboard and a dedicated DayBook report, matching this naming | M |

## 4. Quotation & Sales Order (P1/P2)

Both documents share nearly identical gaps — fix once, apply to both.

| # | Issue | Current state | Fix | Effort |
|---|---|---|---|---|
| 27 | Add customer inline from quotation if missing | 🔴 Only a plain Autocomplete ([QuotationsPage.tsx:340-350](web/src/pages/sales/QuotationsPage.tsx)) | Reuse the inline-create pattern already built for `CustomersPage` | S/M |
| 29/39 | Guided bulk conversion SO→Quote→DC→Invoice | 🟡 Point-to-point `convert`/`convert_to_order`/`convert_to_challan` actions already exist ([views.py:690-701](backend/sales/views.py), [phase1_views.py:269-354](backend/sales/phase1_views.py)) | Build one guided/bulk-chain UI action rather than new backend logic — mostly a frontend orchestration task | M |
| 30/37 | No edit/delete for Quotation (SO edit exists, delete doesn't) | 🔴 Quotation has no edit route at all; SO has edit but only `cancel`, no delete | Add quotation edit route (mirror SO's `/sales/orders/:id`); add a guarded cancel/void (not hard delete) for SO once converted docs exist | M |
| 31/38 | Search by all/open/closed | 🔴 `QuotationsPage`/`SalesOrdersPage` use `DocumentListPage`, which has no search/filter at all (unlike `HistoryFilterBar` used elsewhere) | Reference-app screenshot shows the exact target: a search icon plus a status dropdown with **Show All Quotation / Show Open Quotation / Show Closed Quotation**. Swap both pages onto `HistoryFilterBar` with this option set (see cross-cutting item #58) | M |
| 33/35 | Salesman / Channel field | 🔴 No such field on Quotation/SalesOrder models | Add `salesman`/`channel` fields to both models + forms | M |
| 34/36 | Location / delivery address distinct from party address | 🔴 Not present | Add a delivery-address field separate from billing address | M |
| 40 | Expected price on SO/Quotation/Delivery Challan | 🔴 No such field | Add an expected/quoted price alongside actual — needed before #41 can compute variance | M |
| 41 | Profitability shown on SO/Quotation/DC | 🔴 Not present | **Overlaps with Section 13** — the per-SO expected-profit calculation being built for Delivery Route rollups is the same number this item needs. Build it once (Section 13, Phase 1) and surface it on the SO/Quotation/DC screens directly too, rather than building it twice | M |

## 5. Delivery, Sales Return, Notes, Recurring (P1/P2)

| # | Issue | Current state | Fix | Effort |
|---|---|---|---|---|
| 42a | ~~Delivery = SO + vehicle/driver/delivery-boy; auto-convert when linked~~ | — | **Superseded 2026-09-21** — founder clarified the actual requirement is trip-level multi-order delivery routing, not a per-challan driver field. See Section 13 for the full design; the narrower plan below is no longer being built as such | — |
| 42b | Delivery Challan return option | 🔴 `DeliveryChallanViewSet` only has `complete`/`convert`/`cancel` ([phase1_views.py:332-354](backend/sales/phase1_views.py)) | Add a return action modeled on the existing `SalesReturnViewSet` flow | M |
| 43 | Test partial sales return | 🟢 Partial-return logic already implemented ([return_service.py:63-149](backend/sales/return_service.py)) but no dedicated test found by name | Add explicit test coverage for partial/multiple partial returns against one invoice | S |
| 46b | Recurring invoice: direct-to-invoice vs. through SO/challan flow | 🟡 Currently always creates a DRAFT invoice directly ([recurring.py:126-145](backend/sales/recurring.py)) | **Decided 2026-09-21: change it.** Route recurring-invoice triggers through Sales Order → Delivery Challan → Draft Invoice instead of creating the draft invoice directly. Needs new orchestration in `recurring.py` to create/convert an SO and DC before the invoice, plus a way to configure which stage a given recurring template stops at | M |

## 6. Customer Ledger (P2 — one coherent rebuild, now fully spec'd)

All four ledger items came back missing in our code, and the founder's reference-app
screenshots (2026-09-21) answer both #51 and #57 at once — they show exactly the
target layout. Treat this as one workstream, not four patches.

**Target structure** (per-party detail page, 4 tabs):

- **Transactions** — a single combined list (not separate screens per doc type) with Date/Transaction Type/Transaction Number/Amount/Status columns, filterable by date-range preset, a **Transaction Type** dropdown (Sales, Purchase, Payment In, Payment Out, Quotation, Sales Return, Purchase Return, Credit Note, Debit Note, …), and a **Status** dropdown (All/Paid/Unpaid/Partial/Overdue/Cancelled). Rows are clickable through to the source document. Directly matches #48 and #49.
- **Profile** — General Details (party name/type/mobile/category/email/opening balance), Business Details (GSTIN/PAN/billing address/**shipping address** with a "Manage Shipping Addresses" sub-link), Credit Details (credit period/limit), Party Bank Details, and a Custom Fields panel — all editable inline. Matches #50.
- **Ledger (Statement)** — this *is* the "screenshot" referenced by #51: four KPI tiles (Total Receivable, Overdue Amount, Total Sales Amount, Total Received Amount), a date-range filter, and Download Excel / Print PDF / **Share** actions, above a Date/Voucher/Sr No/Payment Mode table.
- **Item Wise Report** — per-party, per-item Sales Qty/Sales Amount/Purchase Qty/Purchase Amount, with the same date filter. Matches #52.

| # | Issue | Current state |
|---|---|---|
| 48 | Statement with paid/unpaid/partial + jump-to-source links | 🔴 Entries are plain text, no links ([CustomerLedgerPage.tsx:183-190](web/src/pages/reports/CustomerLedgerPage.tsx)) |
| 49 | Filter by transaction type × status | 🔴 Only date-range filter exists |
| 50 | Editable customer profile from ledger | 🔴 Not present |
| 51 | "Ledger statement per screenshot" | 🟢 Resolved — screenshot supplied 2026-09-21, spec folded into the "Ledger (Statement)" tab above |
| 52 | Item-wise statement per party | 🔴 Not present |

**Fix:** rebuild `CustomerLedgerPage` as the 4-tab structure above — status column + deep links, transaction-type × status filter bar, inline edit-profile, per-party item-wise tab, plus the KPI/download/share strip. Effort: **L** (largest single item after #7 and #26).

## 7. Purchase Order / Purchase Invoice / Stock Report (P1)

| # | Issue | Current state | Fix | Effort |
|---|---|---|---|---|
| 54 | Purchase Invoice "Ship From" with address | 🔴 No such field anywhere in `backend/purchases` or the purchase frontend | Add ship-from field + address to model, form, PDF | M |
| 56 | Stock Report search/download/share/print | 🟡 `InventoryReportPage` has CSV export but no search; `CurrentStockPage` has search but export unconfirmed | Reference-app screenshot shows the target: KPI tiles (Total Stock Value, Total Stock Quantity), a Search Category filter + date filter, and **Email Excel / Download Excel / Print PDF** actions (Email Excel effectively covers "share"), plus a Favourite toggle. Unify search + export + print across both pages to this shape (part of cross-cutting #58) | M |

## 8. Point of Sale (P1/P2)

| # | Issue | Current state | Fix | Effort |
|---|---|---|---|---|
| 63 | Multiple billing screens | 🔴 No tab/hold/park mechanism in `PosPage.tsx` | Reference-app screenshot shows the target exactly: tabbed "Billing Screen 1 [CTRL+1]" / "Billing Screen 2 [CTRL+2]" / "+ Hold Bill & Create Another [CTRL+B]", each an independent cart. Add multi-cart/parked-sale sessions with the same keyboard-shortcut pattern | L |
| 64 | POS defaults to purchase price instead of sales price | 🟢 **Live-reproduced 2026-09-21, not confirmed as a bug.** Ran a real POS sale against the demo DB: cart showed ₹280.00, which matches the product's `selling_price` (₹280.00) exactly, not `purchase_price` (₹210.00). Code path confirmed correct | No action on this specific complaint. **However, see the new finding below (POS tax-rate mismatch) found during the same repro — that's a real, more serious bug in the same area** | — |
| 65 | MRP, item code, HSN, additional charges, bill-level discount | 🔴 None of these exist on POS line items today | Reference-app screenshot shows the exact column set: NO/ITEMS/ITEM CODE/MRP/SP/DISC%/QUANTITY/AMOUNT in the cart table, plus a right-panel "Add Discount [F2]" and "Add Additional Charge [F3]" acting on the whole bill (separate from per-line discount). Add these fields to the POS line-item model/UI + receipt template, matching the shortcut-driven layout | M/L |
| 66 | Payment modes: add card/net-banking/bank-transfer/cheque with proof | 🟡 Confirmed live: the POS screen itself displays a banner **"POS is cash/UPI for simple SKUs. No hold-and-recall."** — this is a declared, intentional scope limit, not an oversight. `PaymentMode` type supports BANK/CARD/CREDIT in the domain types but POS checkout UI only wires up CASH/UPI ([PosPage.tsx:1955-1979](web/src/pages/pos/PosPage.tsx)) | Wire the existing modes into POS checkout; add CHEQUE (shared with #9). Note this is a deliberate v1 scope cut, not a bug — sequencing this is a product call, not just an engineering one | M |
| 67 | Print copy too long | 🔴 **Confirmed 2026-09-21, root cause found.** Completed a real POS sale, downloaded the thermal receipt PDF (`GET /api/v1/sales/invoices/{id}/thermal-pdf/?width=80`), and inspected its `/MediaBox`: **226.77pt × 2267.72pt = 80mm × 800mm** — an 80cm-tall page for a single-line-item receipt. Root cause: [thermal_receipt.py:112](backend/sales/pdf/thermal_receipt.py) hardcodes `pagesize=(page_width, 800 * mm)` instead of computing page height from the actual content (item count + summary rows + QR) | Compute the receipt's page height from its flowable content (reportlab supports measuring a story's total height, or switch to a canvas that grows to fit), instead of a fixed 800mm. Small, well-isolated fix in one function | S |

## 9. Accounting basics (P2)

| # | Issue | Current state | Fix | Effort |
|---|---|---|---|---|
| 60/62 | Balance Sheet, P&L, Day Book, Expense missing | 🟡 BS/P&L already exist ([accounting/reports.py:98,116](backend/accounting/reports.py)); no true Day Book (Cash Book is a partial substitute); **no Expense transaction entity** — only an `ExpenseCategory` master ([masters/models.py:66](backend/masters/models.py)) | Reference-app screenshot spec: an Expenses list page (Date/Expense Number/Party/Category/Amount + row actions), a "Create Expense" button, a category filter dropdown with inline **"+ Add/Manage Category"**, and its own Reports dropdown. Build a real Expense entity (model + CRUD + list UI) to this shape; DayBook confirmed as its own distinct report (see #23), not a Cash Book relabel | L |

## 10. Cross-cutting (P1, feeds many items above)

**#58 — usability consistency.** Confirmed: `SalesHistoryPage`/`PurchaseHistoryPage`/`CustomersPage` already share `HistoryFilterBar` (search + status filter); `QuotationsPage`/`SalesOrdersPage` use the bare `DocumentListPage` with no search/filter/bulk-action at all. Standardizing every list page onto (an upgraded) `HistoryFilterBar` — with search, status filter, bulk-select, download, and print/share as shared building blocks — directly resolves #12, #14a, #21, #22, #31, #38, #47, #56, and half of #58 itself. **Recommend doing this first**, before the per-page items above, since it's the multiplier.

---

## 11. Ideas spotted in the reference app (not in the original 67 — optional backlog)

These weren't asked for, but showed up consistently enough in the screenshots to flag
as low-cost additions once the related item above is being built anyway. Not scoped
or prioritized — surface for a product call, don't build speculatively:

- **Price History** toggle on invoice item settings — shows the last 5 sales/purchase prices for that item×party pair. Natural add-on once #3's Quick Settings modal exists.
- **MRP with "% OFF" display** next to the price field on invoice line items.
- **Scan Barcode** as an alternate item-entry method alongside the item search box.
- **Per-column show/hide** on the invoice item table (beyond just custom fields — hiding e.g. Price/Item or Quantity columns entirely).
- **Favourite/pin** toggle on report pages (e.g. Stock Summary) for quick access.

## Items needing your input before scoping (⚪)

- ~~#59, #64, #67~~ — reproduced live against the running dev stack 2026-09-21. #64 did **not** reproduce (code is correct). #59 and #67 **did** reproduce, with root causes found — see Section 12.
- ~~#46b, #61~~ — resolved 2026-09-21: recurring invoices will route through SO/DC (not direct-to-invoice), and real e-invoice IRP submission is in scope as its own project. See rows above.
- ~~#51, #57~~ — resolved by the 2026-09-21 screenshots; see Section 6 and the "Reference-app screenshot" notes throughout.

## 12. Confirmed bugs found during live reproduction (2026-09-21)

All three found by logging into the running dev stack (`docker ps` showed `bizboard-api-1`/`bizboard-web-1`/`bizboard-nginx-1` already up at `localhost`) as the demo account and actually running a POS sale + opening the Discount report — not just reading code.

### #59 — Discount report crash: CONFIRMED, root cause found

Navigating to **Reports → Discounts** throws `TypeError: Cannot read properties of undefined (reading 'length')` and shows the app's error boundary ("Something went wrong"), exactly as reported.

**Root cause:** a camelCase/snake_case mismatch. Every Bizboard API response is auto-camelized by `EnvelopeJSONRenderer` ([core/renderers.py:4](backend/core/renderers.py)) — confirmed the live response was `{"data": {"totals": {"invoiceCount": ...}, "byParty": [...], "byProduct": [...], "byPeriod": [...]}}`. But [DiscountReportPage.tsx:48-52](web/src/pages/reports/DiscountReportPage.tsx) reads `data.by_party` / `data.by_product` / `data.by_period` (snake_case), and the `DiscountReportResponse` type ([types/domain.ts:1017-1030](web/src/types/domain.ts)) is typed entirely in snake_case — so `rows` resolves to `undefined`, and `rows.length` throws. Every other field access in the page (`data.totals.invoice_count`, `.line_discount_total`, etc., and each column's `key`) has the same mismatch.

**Fix:** rename every field in `DiscountReportResponse` and its usages in `DiscountReportPage.tsx` to camelCase (`byParty`, `byProduct`, `byPeriod`, `totals.invoiceCount`, `totals.lineDiscountTotal`, `totals.headerDiscountTotal`, `totals.totalDiscount`, `totals.avgDiscountPercent`, and `lineDiscount` on each row). This is the only report page with this mismatch — worth a quick check of sibling report pages/types for the same pattern, since it suggests this one wasn't run against a real backend response before merging. **Effort: S**, high confidence, ready to fix immediately.

### #67 — POS thermal receipt too long: CONFIRMED, root cause found

Completed a real POS sale (1 line item) and downloaded its thermal receipt PDF. Its page is **80mm × 800mm** — an 80cm-tall strip for one line item, almost entirely blank. Root cause and fix are in the Section 8 table (#67 row) above. **Effort: S**.

### New finding (not in the original 67) — POS live total can differ from the booked invoice total

Found while checking #64. Added "A4 Copier Paper 75 GSM" to a POS cart: the cart showed **Subtotal ₹280.00, CGST ₹16.80, SGST ₹16.80, Total ₹314.00** (12% GST) and the cashier tendered exactly ₹314 cash. After completing the sale, the actual saved invoice ([SalesInvoice #555](backend/sales/models.py)) was booked at **CGST ₹25.20, SGST ₹25.20, Grand total ₹330.00, Received ₹330.00** (18% GST) — a ₹16 discrepancy the cashier never saw before collecting cash.

**Root cause:** the product master's `gst_rate` is 12.00%, but an `HsnRate` table entry for this HSN prefix (480256) is in force from 2026-09-21 at 18% ([hsn_catalog.py:310](backend/masters/hsn_catalog.py), `rate_for()` — an authoritative, effective-dated HSN rate table that overrides the stale product-level rate). The **regular** invoice form calls a real backend preview endpoint (`usePreviewTotals` → `previewSalesTotals`, [usePreviewTotals.ts](web/src/hooks/usePreviewTotals.ts)) that correctly resolves through this table. **POS does not** — it computes the cart total entirely client-side from `line.product.gstRate` ([PosPage.tsx:167,437,446,460](web/src/pages/pos/PosPage.tsx)), never consulting the HSN rate table, so it silently shows a stale total whenever a product's rate and its HSN's authoritative rate diverge (e.g. around any GST rate change, or before product masters are bulk-updated).

**Why this matters more than most items in this plan:** this is a live money-correctness bug — a cashier can genuinely collect the wrong cash amount from a customer based on what POS displays, with no warning that the recorded total differs. Recommend treating this as **P0**, above the rest of the backlog, not folded into the general #65/#66 POS work.

**Fix options:** either (a) have POS call the same backend preview endpoint the regular invoice form uses (adds a network round-trip per cart change, mitigated by the same debounce `usePreviewTotals` already uses), or (b) at minimum, re-validate the total server-side on `complete` and block/warn if the client-submitted total doesn't match the server-computed one, rather than silently substituting the correct total after cash has already been collected. Needs a design call on option (a) vs (b) vs both — flagging rather than picking one unilaterally, since it affects POS's fast-counter UX tradeoff. **Effort: M**.

## Suggested execution order

1. **Cross-cutting list-page standardization** (#58) — unlocks the largest number of downstream items cheaply.
2. **P0 quick wins** (Section 1) — mostly verification + help text, low risk, fast to close out.
3. **Payment mode / cheque support** (#9, #10, #66) — one shared backend change (`PaymentMode` + cheque fields) serving invoices, POS, and purchase payments at once.
4. **Sales History payment-status + date-preset filters** (#13, #14a, #14b) — one coherent filter-bar upgrade.
5. **Customer Ledger rebuild** (#48–52) — largest coherent single workstream; do once #58's shared components exist to build on.
6. **Editable grand total** (#7) and **invoice-level custom fields** (#26) — the two highest-risk/highest-effort items; scope each with its own mini-spec before starting.
7. **POS structural work** (#63, #65) and **Expense/Day Book** (#60/#62) — larger builds, sequence after the above based on business priority.
8. Resolve the ⚪ clarification items in parallel with whoever filed the original ticket.

## 13. Delivery Route planning (supersedes #42a) — full design, 2026-09-21

Founder-clarified requirement: not a per-challan driver field, but a genuine new capability —
**Multiple Sales Orders → one Delivery Route → one vehicle/van → multiple customer deliveries**,
with route-level cost/profitability rollup. This is a real feature, not a small fix. Sized and
phased accordingly, not folded into the S/M/L rows above.

### What already exists vs. what's new

Grounded against the actual code before designing anything:

- `SalesOrder` ([models.py:515-545](backend/sales/models.py)) has `grand_total` (order value), `expected_delivery` date, `status` (DRAFT/CONFIRMED/CONVERTED/CANCELLED), and `customer` — usable as-is for route planning inputs.
- `DeliveryChallan` ([models.py:579-619](backend/sales/models.py)) is strictly **one per Sales Order** today (`sales_order = models.ForeignKey(SalesOrder, ...)`, singular) — there is no existing concept of one document covering multiple orders.
- `SO → Challan` conversion already works end-to-end, backend and UI ([phase1_views.py:273-276](backend/sales/phase1_views.py), wired at [SalesOrdersPage.tsx:45,108](web/src/pages/sales/SalesOrdersPage.tsx)) — nothing to fix there.
- **No per-invoice-or-order cost/margin figure exists ahead of invoice completion.** The one real profit figure in the system, `InvoiceProfitSnapshot` ([reporting/models.py:211-226](backend/reporting/models.py)), is explicitly computed from **FIFO stock-cost layers at invoice-complete time** — its own docstring states this is the *only* place a per-invoice cost exists, because COGS otherwise only posts as one aggregate GL journal entry. A Sales Order, being upstream of invoicing and stock consumption, cannot have this number. Any "Expected Profit" at the SO/Route level is necessarily an **estimate** (product's current purchase price, not a real FIFO layer) — genuinely different from, and not reconcilable to the cent with, the actual profit realized once invoices complete. The UI must label it "Expected/Estimated Profit," not "Profit," so the two numbers disagreeing later isn't mistaken for a bug (the same confusion the live-repro findings in Section 12 nearly caused).
- No delivery-cost/logistics-cost concept exists anywhere (no Expense transaction entity yet — see #60/#62).
- No delivery address distinct from billing address exists yet (#34/#36) — needed for "customer and delivery details for each SO" to be meaningful on a route.

### Design decision: Route as a planning overlay, not a replacement for Challans

Two ways to build this; recommending the first:

- **(A) Route wraps Sales Orders/Challans as a logistics/planning layer** — a new model referencing existing SOs (and their per-order Challans, created exactly as today), adding trip-level grouping, vehicle/driver, status, and a cost/profit rollup on top. GST e-way-bill and stock-movement logic on `DeliveryChallan` stays completely untouched.
- (B) Consolidate multiple orders into one physical delivery document per trip — closer to "one challan for the whole van," but e-way bill rules are generally per-consignment/invoice, so this risks a real GST-compliance rabbit hole for a feature that's fundamentally about ops visibility, not statutory filing.

**(A)** delivers everything in the requirement (grouping, rollup, status tracking) without touching compliance-sensitive document logic. Going with it unless you specifically want the consolidated-document version.

### Data model (new)

```
DeliveryRoute
  company, route_date, vehicle_number, driver_name, driver_phone,
  status: PLANNED / IN_TRANSIT / COMPLETED / CANCELLED
  estimated_logistics_cost, actual_logistics_cost (nullable — filled post-trip)
  notes

DeliveryRouteStop  (join: one row per Sales Order on a route)
  route (FK DeliveryRoute), sales_order (FK SalesOrder, unique — an SO is on at most one active route)
  sequence (delivery order within the trip)
  delivery_status: PENDING / OUT_FOR_DELIVERY / DELIVERED / FAILED / RETURNED
  delivered_at, delivery_notes
```

Route-level rollup (computed, not stored — same pattern as existing report aggregations):
`total_order_value = Σ stop.sales_order.grand_total`, `total_expected_profit = Σ per-line (unit_price − estimated_unit_cost) × qty` (new service, reusable — see #41 cross-link above), `route_profit = total_expected_profit − estimated_logistics_cost`, `margin_pct = route_profit / total_order_value`.

### API surface (new)

- `POST /sales/delivery-routes/` — create with `vehicle_number`, `driver_name`, `driver_phone`, `route_date`.
- `POST /sales/delivery-routes/{id}/add-orders/` — body: list of `sales_order` ids (only CONFIRMED, not already on an active route — validate both).
- `PATCH /sales/delivery-routes/{id}/stops/{stop_id}/` — update a single SO's `delivery_status`.
- `POST /sales/delivery-routes/{id}/complete/` — closes the route, prompts for `actual_logistics_cost`.
- `GET /sales/delivery-routes/{id}/` — full detail including the rollup fields above.

### UI

- New nav entry (Sales → Delivery Routes, alongside Delivery Challans).
- **Create flow**: from the Sales Orders list, multi-select CONFIRMED orders (reuses the bulk-select UI already planned for the cross-cutting #58 list-page work) → "Add to Delivery Route" → pick existing route or create new (vehicle/driver/date).
- **Route detail page**: table of stops — Customer, Delivery Address (needs #34/#36), Order Value, Expected Profit, Delivery Status (inline update) — with a totals footer (Total Order Value / Total Expected Profit / Est. Logistics Cost / Route Profit / Margin %), matching the worked example in the requirement. Overall route status control at the top.
- **Route manifest PDF** (cheap add, high practical value, not explicitly asked for but obviously useful): a printable run-sheet for the driver — stop sequence, customer, address, phone, order value, items count. Proposing this as part of Phase 3 rather than asking, since it's low-risk and the natural companion to a route feature; flag if you'd rather skip it.

### Phasing

1. **Phase 1 (M)** — `DeliveryRoute`/`DeliveryRouteStop` models + migration, the expected-profit calculation service (shared with #41), route CRUD API.
2. **Phase 2 (M)** — Route list + detail UI, multi-select entry point from Sales Orders.
3. **Phase 3 (S)** — per-stop delivery-status updates, route status transitions, manifest PDF.
4. **Phase 4 (S, later)** — once the Expense entity (#60/#62) exists, let `actual_logistics_cost` optionally pull from a tagged Expense record instead of manual entry, and show expected-vs-actual route profit after completion.

### Open questions before starting (yours to decide, not mine)

- Scope to Sales Orders only (as stated), or should this eventually also cover ad-hoc/POS deliveries? Defaulting to SO-only per the requirement as written.
- Who can create/manage routes — reuse `CanCreateSales`, or a separate logistics-role permission? Defaulting to reuse unless told otherwise.
- Should an SO be removable from a route after adding (e.g., customer reschedules)? Assuming yes, with the stop simply deleted and the SO freed for another route — flag if routes should be immutable once created instead.
