# Purchase module — the areas not reviewed before

Date: 2026-10-15 · Continues [PURCHASE_REMAINING_SCREENS_REVIEW_2026-10-15.md](PURCHASE_REMAINING_SCREENS_REVIEW_2026-10-15.md).
This is a findings list. **Nothing here has been fixed.**

**How this was done.** I read the code and the strings the user sees. I did not run any of it in a browser, and I did
not run the import pipeline against real bills. **[O]** = seen directly in code. **[V]** = a guess that needs a
running system, real data or a person to confirm.

**Depth, stated plainly**

| Area | Read | Not read |
|---|---|---|
| Bill-upload parts | `BillLinesTable`, `PartyBlock`, `BillTotalsPanel`, `SourceBillViewer`, `ImportedBillNotice`, `billLines.ts` — all of each | — |
| Import pipeline | `imports/views.py` (all), `bill_validation.py` (all), `start_extraction`, `parse_structured_file`, `update_preview` (first half), `commit`, `_commit_purchase`, `void_bill`, `cancel`, `switch_kind`, `tasks.py` (first half) | the LLM client, `party_match.py`, `qty_formula.py`, `enrich_preview`, the second half of `update_preview`, `_match_or_create_product`, the master-data imports other than suppliers (about 3,000 of the 3,943 lines in `services.py`) |
| Money hub (purchase side) | `MoneyHubPage` outgoing column and actions table, `MoneyOutlook` | `MoneyTiles`, `MoneyTaxDues`, and the server side (`money_position.py`, `money_views.py` belong to another session and are uncommitted) |
| Settings pages | `ImportPage` (state, mutations, confirms) and the supplier import it drives; `TallyMigrationPage` header, mutations, confirms, and the Tally adapter's opening-balance path | the rest of the page layout; the Tally export / push code |
| Backend documents | `boe_services.py`, `grn_service.py`, `reliability.py` (all); `notes_services.py` (complete and cancel paths, PO convert); `pdf.py` (the bill header, party block, HSN table, and every f-string that builds markup) | the rest of `notes_services.py` totals code, the purchase-order PDF half of `pdf.py` |

Priority: **P0** wrong money or data · **P1** blocks a real task or misleads · **P2** costs time or trust · **P3** polish.

## Summary

| Area | Verdict | P0 | P1 | P2 | P3 |
|---|---|---|---|---|---|
| Bill-upload parts (web) | 🟡 READY WITH FIXES | 0 | 0 | 5 | 3 |
| Import pipeline (server) | 🟡 READY WITH FIXES | 0 | 1 | 5 | 3 |
| Money hub, purchase side | 🟡 READY WITH FIXES | 0 | 0 | 3 | 2 |
| Settings import (suppliers) | 🟠 NEEDS WORK | 0 | 1 | 2 | 1 |
| Tally migration | 🟠 NEEDS WORK | 0 | 1 | 3 | 2 |
| Bill of entry | 🟡 READY WITH FIXES | 0 | 0 | 3 | 1 |
| Goods receipt | 🟡 READY WITH FIXES | 0 | 0 | 3 | 1 |
| Credit / debit notes, PO convert | 🟡 READY WITH FIXES | 0 | 0 | 3 | 1 |
| Purchase PDF | 🟡 READY WITH FIXES | 0 | 0 | 2 | 1 |

No P0 was found in what I read. What I read is described above, not "everything in the module".

## A. Bill-upload parts (web)

| ID | P | Where | Finding |
|---|---|---|---|
| U-01 | P2 | `billLines.ts` `localLineErrors` | The row error messages are hard-coded English and read like field names: "quantity must be > 0", "unit_price must be a number", "GST rate 7 is not an allowed slab". A negative price is reported as "must be a number". They are shown under the row name. **[O]** |
| U-02 | P2 | `BillLinesTable` | A row's problem is shown under the **Name** cell, not next to the field that is wrong (GST, price, HSN). With a wide table the person must connect "GST rate 7 is not an allowed slab" to a column that may be off screen. The field only gets a red outline and a tooltip. **[O]** |
| U-03 | P2 | `BillLinesTable` `ProductMatchCell` | A collapsed row whose product has only fuzzy matches (`candidates`, not chosen) shows the same **New product** chip as a row that will really create a product. The two cases look identical until the row is opened. With the v2 flag off, nothing forces the choice. **[O]** |
| U-04 | P2 | `BillLinesTable` | The "apply pack quantity" hint is a clickable `Typography` with no button role, no tab stop and no key handler. A keyboard user cannot accept it. **[O]** |
| U-05 | P2 | `PartyBlock` | When a party is already chosen in the picker the block returns nothing, so the person is never told if the bill printed a **different** name or GSTIN. Picking the wrong supplier from a long list is silent. **[O]** |
| U-06 | P3 | `PartyBlock` | The GSTIN box limits length and upper-cases, but does not check the checksum, unlike the Suppliers page. A mistyped GSTIN is saved to the new supplier. **[O]** |
| U-07 | P3 | `SourceBillViewer` | PDFs have no zoom (the buttons are hidden with no explanation) and an `<object>` with no fallback, so a browser or phone without a PDF viewer shows a blank box. Images have no rotate, so a sideways photo cannot be read in place. **[O]** |
| U-08 | P3 | `billLines.ts` `lineAmount` | The line total ignores cess, so it will not match a printed total on a cess item. **[O]** |

## B. Import pipeline (server)

| ID | P | Where | Finding |
|---|---|---|---|
| S-01 | P1 | `bill_validation.header_errors` | The duplicate-purchase check runs **only when the supplier was picked on the upload screen** (`job.supplier_id`). The usual case is "let it find or create the supplier from the bill", so the check is skipped, and the same bill uploaded twice (two photos, different file hash) makes two drafts. Completion later asks "duplicate bill" for the same supplier, which is the only remaining guard. **[O]** for the condition; **[V]** whether the automatic supplier match (`enrich_preview`, which I did not read) fills `job.supplier` before commit, which would close this for matched suppliers. |
| S-02 | P2 | `imports/views.py` `throttled` | The message says a CSV/Excel export "is not limited", but `get_throttles` applies the rate limit to every bill-kind upload, structured files included. The promise is wrong, and the person is sent to the thing that is also limited. **[V]** on the actual rate. |
| S-03 | P2 | `imports/views.py` `create` | The AI-consent check is raised only when the `BILL_IMPORT_REVIEW_V2` flag is on. With the flag off, an API caller that omits `ai_consent` has its image sent to the AI service with no consent recorded. The web app always sends it. **[O]** |
| S-04 | P2 | `bill_validation` | Row and header messages are developer wording shown on screen: "unit_price cannot be negative", "quantity must be > 0", "name is required". Same family as U-01 on the server side. **[O]** |
| S-05 | P2 | `bill_validation.header_errors` | The supplier or buyer GSTIN on the bill is not checked for format or checksum, or for a cancelled status, before the draft exists. Both only surface later (Suppliers page, completion). **[O]** |
| S-06 | P2 | `tasks._file_to_images` / `extract_purchase_bill_task` | Failure text meant for operators reaches the person: "…or raise LLM_BILL_MAX_PAGES", and the budget message appends the raw exception detail. **[O]** |
| S-07 | P2 | `parse_structured_file` | The whole file is read into memory and parsed inside the web request. The line cap (`_guard_line_limit`) is applied **after** the rows are built, so a very large sheet is fully parsed before it is refused. File-size limits live in `FileService`, which I did not read. **[V]** |
| S-08 | P3 | `start_extraction` | A cancelled job is allowed to restart, but the refusal text says only "UPLOADED or FAILED". The two disagree. **[O]** |
| S-09 | P3 | `update_preview` | `supplier_gstin` is stored as typed, while `buyer_gstin` is upper-cased. The stale-version check is skipped if the caller omits `preview_version` (the web app always sends it). **[O]** |
| S-10 | P3 | `_commit_purchase` | When every line is 0-rated and the person has not ticked non-GST, the draft's note says "Set confirm_non_gst on preview to book as NON_GST" — a flag name, stored on the document. **[O]** |

## C. Money hub — purchase side

| ID | P | Where | Finding |
|---|---|---|---|
| M-01 | P2 | `MoneyHubPage` | The hub's links go to `/purchases/history?has_balance=1`, `overdue=1`, `due_soon=1` and `/purchases/payments?advance=1` etc. The code that reads those filters is **another session's uncommitted work**. In the committed tree these links open the unfiltered list, so the tile says ₹X overdue and the page shows everything. **[O]** |
| M-02 | P2 | `MoneyOutlook` | A day shows its first four items and "+ n more", with no way to open the rest. For a busy due date the person cannot see which supplier makes up the total. **[O]** |
| M-03 | P2 | `MoneyHubPage` actions table | The **Days** column has no sign or unit: it is not clear whether it means days overdue or days until due, and it differs by action kind. **[V]** with the server data. |
| M-04 | P3 | `MoneyHubPage` | The payable tile ("net payable") and the bill list it opens can disagree if advances are netted; the open decision on advances-netting from the Money hub plan is not reflected on the tile. **[V]** |
| M-05 | P3 | `MoneyHubPage` | Debit notes raised but not yet applied, and goods received but not billed, are not on the outgoing side at all. Whether they belong there is a product call. **[V]** |

## D. Settings import — suppliers

| ID | P | Where | Finding |
|---|---|---|---|
| I-01 | P1 | `_commit_suppliers` | Imported suppliers skip the checks the Suppliers page enforces: no GSTIN **checksum** (format only), and **no place-of-supply rule** — only `name` is required, but when GST is on and "assume local state" is off the Suppliers page needs a state or a GSTIN. A supplier imported with neither makes every bill from them stop at completion on "place of supply" (and `bulk_create` also skips the save hooks). **[O]** |
| I-02 | P2 | `ImportPage` | Commit and Undo use the browser popup (`window.confirm`), while the rest of the purchase area moved to the in-app dialog. "Choose a file" and "No import job" are English literals. **[O]** |
| I-03 | P2 | `ImportPage` | "Undo is blocked" is worked out by matching English words in the error text (`already been used|insufficient available stock|Adjust Stock`). Any rewording or Hindi message silently turns the button back on. **[O]** |
| I-04 | P3 | `_commit_suppliers` | A supplier is skipped when the **phone** already exists, though two real suppliers can share a number. Skipped rows are reported, but a person who does not read the list loses them. **[O]** |

## E. Tally migration

| ID | P | Where | Finding |
|---|---|---|---|
| T-01 | P1 | `adapter._create_opening_purchase` | The opening payable is created **dated today** (`timezone.localdate()`), not at the migration or opening date. It shows as a current-month purchase, never ages as overdue, lands in this month's registers, and fails the whole commit if today's period is closed (the completion period gate). The sales twin (`_create_opening_sales`) does the same. **[O]** |
| T-02 | P2 | `_create_opening_purchase` | If the supplier already has a completed opening bill it returns without a word. Re-importing a corrected opening balance is silently ignored; the commit summary does not say so. **[O]** |
| T-03 | P2 | `_match_or_create_party` | New suppliers and customers are created without GSTIN format or checksum checks; a conflicting GSTIN on an existing party is only a warning line. **[O]** |
| T-04 | P2 | `TallyMigrationPage` | Hard-coded English: the column help, the "Customers n · Suppliers n" lines, "No preview", "Failed to download error report". **[O]** |
| T-05 | P3 | design | Opening payables are one lump per supplier, not bill-wise, so later payments cannot be matched to the real old bills or aged correctly. **[O]** |
| T-06 | P3 | `adapter` | Each party's opening balance is committed in one transaction with the masters; a failure on the last supplier rolls back everything, with one error string. **[V]** |

## F. Bill of entry

| ID | P | Where | Finding |
|---|---|---|---|
| B-01 | P2 | `boe_services.complete` | Refusals use field names: "…set icegate_verified, or mark the ITC INELIGIBLE". **[O]** |
| B-02 | P2 | `boe_services.complete` | No cross-check that IGST fits the assessable value and duty (IGST is charged on value plus duty). A typo in either amount posts import ITC unchallenged. (The zero-assessable-value case is PB-01.) **[V]** |
| B-03 | P2 | `boe_services.cancel` | Draft purchases linked to the bill are **silently unlinked** (`bill_of_entry=None`) so they can still complete. The person who opens that draft later finds the import link gone with no message. **[O]** |
| B-04 | P3 | `BillsOfEntryPage` | The ICEGATE-verified field is a yes/no menu with no hint that, once GSTR-2B for the period is loaded, an unverified eligible bill cannot complete. **[O]** |

## G. Goods receipt

| ID | P | Where | Finding |
|---|---|---|---|
| G-01 | P2 | `grn_service.cancel` | Cancelling a receipt does **not** touch the debit note that was auto-drafted for its rejected goods. That draft can still be completed later, cutting what you owe the supplier for goods whose receipt was cancelled. **[O]** |
| G-02 | P2 | `grn_service.complete` | Stock is valued at the receipt line's price, which may be blank (0). Stock then sits at zero cost until the bill; the bill has nothing to post for received goods, so the cost may never be corrected. **[V]** (depends on how completion treats already-received goods — I saw it skips the stock, not whether it revalues). |
| G-03 | P2 | `grn_service.convert_to_bill` | A line with no receipt price takes the product master's purchase price and GST rate, silently, and not the order's. The bill then fails the 3-way match for a reason the person did not cause. **[O]** |
| G-04 | P3 | `_draft_rejection_debit_note` | For a GST-registered company the auto-drafted debit note cannot complete until the receipt has been converted to a bill (it needs a source invoice). Nothing says so. **[V]** |

## H. Credit / debit notes and order conversion

| ID | P | Where | Finding |
|---|---|---|---|
| N-01 | P2 | `notes_services` | Refusals carry flag and field names: "Pass confirm_paid_invoice=true to proceed", "Pass confirm_price_override=true…", "must reference a source invoice item (source_item)". The web app replaces the two confirms by code; any other client, or a code it does not know, shows them as written. **[O]** |
| N-02 | P2 | `convert_purchase_order` | The new bill goes to the **default** warehouse, not one chosen on the order, and does not carry the order's supplier terms beyond payment days. **[V]** whether orders have a warehouse. |
| N-03 | P2 | `cancel_credit_note` | A credit note that has already been refunded or applied by a supplier payment is cancelled with no check on that. **[V]** |
| N-04 | P3 | `cancel_purchase_order` | Only a draft order can be cancelled; once converted it must be handled through the bill. That is stated nowhere on the order screen. **[O]** |

## I. Purchase PDF

| ID | P | Where | Finding |
|---|---|---|---|
| P-01 | P2 | `pdf.py` | Many values go into reportlab `Paragraph` markup **unescaped**: supplier GSTIN, phone, state, address lines, supplier bill number, batch number, place of supply. A "<" in a free-text field (supplier bill number, address, batch) breaks the PDF with a parse error; reportlab also honours tags such as `<img src=…>`, so a crafted address could try to load a file or URL. Only the names go through `pdf_esc`. **[O]** unescaped; **[V]** exploitability. |
| P-02 | P2 | `pdf.py` | The docstring and header call the printout a "statutory GST-compliant … Inward Tax Invoice". A buyer-side purchase bill is not the supplier's tax invoice; the wording can mislead an auditor. A CA question. **[V]** |
| P-03 | P3 | `pdf.py` | Hard-coded English labels throughout (fine for an English document, wrong for a Hindi-speaking shop that prints in Hindi). **[O]** |

## J. Suggested order

1. **S-01, I-01, T-01** — the three that change what is booked: duplicate bills slipping through, imported suppliers that later block every bill, and opening payables dated today.
2. **G-01, B-03, P-01** — a stale auto-drafted debit note, a silently dropped import link, and PDFs that can break or fetch files.
3. **U-01/U-02, S-04, N-01, B-01** — one pass over developer wording and where row errors appear.
4. **S-02, S-03, S-07, M-01** — honest throttle text, consent on the server, upload size, and the hub links that depend on uncommitted work.
5. Everything P3 can wait for a general polish pass.

## K. Still not reviewed

`party_match.py`, `qty_formula.py`, `enrich_preview`, the LLM client, `MoneyTiles` / `MoneyTaxDues` and the server side
of the Money hub, the remaining master-data imports (customers, products, opening stock), and the purchase-order half of
the PDF code.

## Status after the first fix pass

| ID | Status | Note |
|---|---|---|
| S-01 | Fixed | The duplicate-bill check now also runs when no supplier was picked on upload: it uses the supplier the bill's GSTIN or name matches. An unmatched (new) supplier cannot have a duplicate. |
| I-01 | Fixed | Supplier import rejects a GSTIN with a wrong check digit, and (when GST is on and "assume local state" is off) a row with neither state nor GSTIN. A blank state is filled from the GSTIN. |
| T-01 | Fixed | Tally opening payables and receivables are dated at the books-start date (or the financial-year start), not the import day. If that date falls in a closed period the commit still stops, which is correct. |

Tests: `backend/tests/test_purchase_never_reviewed_fixes.py` (6). All other findings are still open.

## Status after the second fix pass

Everything below was built and tested except where a line says otherwise.

| ID | Status | Note |
|---|---|---|
| U-01 | Fixed | Row errors are plain words and translated (English and Hindi). |
| U-02 | Fixed | The error shows under the field that is wrong. Errors for columns that are hidden stay under the name. |
| U-03 | Fixed | A collapsed row with only similar matches shows "Similar product found: choose", not "New product". |
| U-04 | Fixed | The pack-quantity hint is a real button. |
| U-05 | Fixed | When a party was picked, a different name or GSTIN printed on the bill is pointed out. |
| U-06 | Fixed | A 15-character GSTIN with a wrong check digit is flagged while typing. |
| U-07 | Fixed | Images can be rotated; a PDF shows an "Open in a new tab" link and a note that zoom is not available. |
| U-08 | Fixed | The line total includes cess. |
| S-01 | Fixed | See the first pass. |
| S-02 | Fixed | Only scans (image or PDF) are rate-limited; CSV/Excel uploads are not. |
| S-03 | Fixed | A photo without recorded consent is refused whatever the flag says. |
| S-04 | Fixed | Row messages from the server are plain words. |
| S-05 | Fixed | A bill's supplier or buyer GSTIN with a wrong check digit, and a chosen supplier whose GSTIN is cancelled, show as warnings before the draft exists. |
| S-06 | Fixed | No operator wording (setting names, raw exception text) reaches the person. |
| S-07 | Fixed in part | A file over 15 MB or over the line limit is refused before preview lines are built. The sheet is still read into memory once; the upload size limit itself lives in the file service. |
| S-08 | Fixed | The refusal says in words when scanning can be restarted. |
| S-09 | Fixed in part | Supplier GSTIN is upper-cased. `preview_version` stays optional on purpose so scripts that edit one field keep working; the web app always sends it. |
| S-10 | Fixed | The draft note tells the person which box to tick. |
| M-01 | Open (other session) | The Money hub, its server code and these filters are another session's uncommitted work. Nothing for me to commit; the links work in the working tree. |
| M-02 | Fixed | A busy day can be expanded to every item. (Money hub files are uncommitted, see M-01.) |
| M-03 | Fixed | The column is "How long" and each row says overdue, past the promise, or since entered. |
| M-04 | Fixed | The payable tile says it is before advances already paid. |
| M-05 | Fixed | The outgoing column says debit notes not yet applied and goods received but not billed are not counted. Counting them would be a product change. |
| I-02 | Fixed | In-app confirm dialogs and translated messages. |
| I-03 | Fixed | The Undo block is keyed on a server code (`IMPORT_STOCK_USED`), not English words. |
| I-04 | Fixed | A shared phone number no longer skips a supplier. |
| T-01 | Fixed | See the first pass. |
| T-02 | Fixed | A second opening balance for the same party is reported in the commit warnings. |
| T-03 | Fixed | A Tally row with a bad GSTIN is an error row. |
| T-04 | Fixed | Translated text. |
| T-05 | Not changed | Opening payables stay one lump per supplier. Bill-wise opening needs the old bill list, which a Tally masters file does not carry. |
| T-06 | Fixed in part | The error names the party that stopped the commit. It is still one transaction by design, so nothing is half imported. |
| B-01 | Fixed | Plain wording. |
| B-02 | Fixed | IGST above 40% of assessable value plus basic duty is refused; so is IGST with no assessable value (this also settles PB-01 on the safe side, CA to confirm). |
| B-03 | Fixed | A draft purchase that loses its Bill of Entry link gets a note saying so. |
| B-04 | Fixed | A hint under the ICEGATE field. |
| G-01 | Fixed | Cancelling a receipt cancels its draft rejection debit note, and refuses if that note is already completed. |
| G-02 | Fixed | A receipt line without a price takes stock in at the product's purchase price. |
| G-03 | Fixed in part | A bill built from a receipt line without a price says the price came from the product. Receipts carry no link to the order, so the order price cannot be used. |
| G-04 | Fixed | The draft debit note's text says to convert the receipt first (GST-registered companies). |
| N-01 | Fixed | Plain wording, no flag or field names. |
| N-02 | Checked, no change | Purchase orders have no warehouse field, so the default warehouse is the only choice; payment days, charges, discount and terms already carry over. |
| N-03 | Checked, no change | Credit notes have no refund or application link, so there is nothing to check; cancelling one simply restores the payable. |
| N-04 | Fixed | A converted order says it is managed from the purchase bill. |
| P-01 | Fixed | Every free-text value in the purchase PDF is escaped. |
| P-02 | Fixed | The wording no longer calls it a tax invoice. A CA can still comment. |
| P-03 | Not changed | The PDF is an English statutory-style document by design. |

Tests: `backend/tests/test_purchase_never_reviewed_fixes.py` (18 backend) and new cases in `PartyBlock.test.tsx` and `billLines.test.ts`.
