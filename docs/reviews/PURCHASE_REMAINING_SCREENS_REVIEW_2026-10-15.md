# Purchase module — remaining screens: issues, gaps, bugs, broken flows, cognitive load

Date: 2026-10-15 · Continues [PURCHASE_OTHER_SCREENS_REVIEW_2026-10-15.md](PURCHASE_OTHER_SCREENS_REVIEW_2026-10-15.md).
Status: **all 33 findings have been worked**; see "Status after implementation" at the end. The tables before
that section are the original findings, kept as written.

**How this was done.** I read the screen code, the parts of the backend each screen calls, and the strings the
user sees. I did not run any screen in a browser. **[O]** = seen directly in code. **[V]** = a guess that needs a
running system or a person to confirm.

**Reviewed in this pass:** bill upload (page and review panel), GSTR-2B, supplier ledger, purchase register,
missing documents, supplier complaints, demand forecast, and the purchase completion rules in
`PurchaseService.complete`.

**Still not reviewed:** the smaller bill-upload parts (`BillLinesTable`, `PartyBlock`, `BillTotalsPanel`,
`SourceBillViewer`), the server import pipeline behind them, the purchase side of the Money hub, settings
`ImportPage` / `TallyMigrationPage`, and `boe_services`, `notes_services`, `grn_service` and the purchase PDF.

Priority: **P0** wrong money or data · **P1** blocks a real task or misleads · **P2** costs time or trust ·
**P3** polish.

## A. Broken flows (the user cannot finish)

| ID | P | Where | What happens |
|---|---|---|---|
| B-01 | P1 | Complete a bill that differs from its PO / GRN | The server stops with "3-way match failed … An owner or manager may pass `confirm_three_way_override=true`" ([services.py:724](../../backend/purchases/services.py)). The web app has no control that sends it: `completePurchase` and `completeWithConfirms` do not know the code. An Owner is told to use a setting that does not exist on screen, and the only way out is to edit the bill to match the order. **[O]** |
| B-02 | P1 | Complete a bill from a supplier whose GSTIN was cancelled | Hard block: "ITC is blocked until an authorised override is recorded." The API accepts `gstin_cancel_override` and a reason, but no screen offers them ([services.py:915](../../backend/purchases/services.py)). Paying such a supplier has the same gap: the payment API takes `gstin_hold_override`, the new pay-now type and dialogs do not. **[O]** |
| B-03 | P2 | Bill upload → "Retry extraction" | The three Retry buttons (failed job, stalled job, "maybe truncated") call `retryImportExtract(...).then(refetch)` with no error handler. If the retry request fails nothing is shown and the page looks frozen. **[O]** |

## B. Bugs and wrong behaviour

| ID | P | Where | What happens |
|---|---|---|---|
| G-01 | P2 | Bill upload review | The button labelled **Cancel extraction** (also used on the review screen) discards the whole import, including every row the user corrected, on one click with no confirm. The same screen has a confirm for *Undo import*. **[O]** |
| G-02 | P2 | Bill upload | Three English messages are thrown straight into the UI: "Choose a file", "No job", "Extraction failed". **[O]** |
| G-03 | P2 | Supplier ledger | Empty-state text, the WhatsApp statement text and the document **Type** column are not translated; the type shows the raw code. **[O]** |
| G-04 | P2 | GSTR-2B | Match class and IMS action show raw values (`NO_ACTION`, the match status). **[O]** |
| G-05 | P3 | GSTR-2B | After changing ITC eligibility or accepting a row, only the GSTR-2B and summary lists refresh; a purchase bill that shows the same eligibility stays stale until reloaded. **[V]** whether the two are linked. |
| G-06 | P3 | Demand forecast | Any method other than `trailing_mean` is shown as its raw code. **[O]** |
| G-07 | P3 | Purchase register | Export success is silent (only failure shows). **[O]** |

## C. Gaps (something a user needs is missing)

| ID | P | Where | Gap |
|---|---|---|---|
| H-01 | P1 | Supplier ledger | No way to open the bill or payment behind a row. Finding why a balance is wrong means copying a number and searching elsewhere. **[O]** |
| H-02 | P1 | Supplier ledger | Only Print and WhatsApp. No CSV or PDF, which is what an accountant or the supplier asks for. **[O]** |
| H-03 | P2 | Supplier ledger | Nothing explains the columns: "Paid" is the debit, "Billed" the credit, and the running balance has no sign convention (what does a negative payable mean — advance?). No opening-balance row when a date range is chosen. **[V]** for the opening balance. |
| H-04 | P2 | Purchase register | No totals (purchases, tax, ITC). Columns are whatever keys the first row has, with labels made from field names; there is no curated column set. **[O]** |
| H-05 | P2 | Purchase register | Date presets are financial year and quarter only. The common need is "last month" for a GST return. The default range is empty, so opening the page loads the whole register. **[O]** |
| H-06 | P2 | Bill upload | No visible sample or template for the CSV / Excel route. **[V]** |
| H-07 | P2 | Bill upload | No estimate of how long extraction takes. The Cancel option appears only after three minutes. **[O]** |
| H-08 | P2 | Demand forecast | Dead end: no link from a forecast row to Purchase planning or a new order. **[V]** |
| H-09 | P3 | Missing documents | The "client" and "CA" views are switched by a `?view=client` address parameter only; there is no toggle on the page. **[O]** |
| H-10 | P3 | Supplier ledger / GSTR-2B | Supplier pickers load every supplier at once and filter in the browser. **[O]** |

## D. Cognitive load

These are the places a user has to hold too much in their head, decide too many things at once, or guess.

| ID | P | Where | Problem | Suggested direction |
|---|---|---|---|---|
| C-01 | P1 | Bill upload review | The **Create draft** button turns off with no reason shown. Eight different conditions can disable it: no rows kept, invalid rows, no date, no supplier, company GSTIN not chosen, new products not confirmed, low-confidence not accepted, save in progress. The user hunts the page for the cause. **[O]** | Show one line under the button naming the first blocker, with a "Go there" link. |
| C-02 | P1 | Bill upload review | Up to **nine banners** can stack above the table (wrong direction, injection warning, extraction warnings, truncated, maybe truncated, template applied, AI accuracy, company GSTIN suggestion, no rows), then **four checkboxes** to tick (new products, non-GST, not a duplicate, accept low confidence), then three buttons. All have equal weight. **[O]** | Order by what blocks you; collapse the informational ones into one "Notes" line; ask for each confirmation only when it applies and next to what it is about. |
| C-03 | P2 | Bill upload | The AI-accuracy notice, the privacy notice and a consent tick appear on every upload. People tick without reading, or stop reading. **[O]** | Ask once per user and company; keep a short permanent line. |
| C-04 | P2 | Bill upload | After import, one banner offers **Open draft**, **Undo import** and **Reset** side by side. "Reset" does not say it starts a new upload. **[O]** | Primary: Open draft. Rename Reset to "Upload another". Put Undo in a menu. |
| C-05 | P1 | GSTR-2B | The page shows five KPI tiles, two banners, five toolbar controls, a filter, then per row an ITC dropdown and four buttons (Accept, Reject, Pending, Supplier message), then a scorecard table. Nothing says the order of work (match → review → accept / reject → export). **[O]** | A short "what to do next" strip, or group the row actions behind one menu with the likely action first. |
| C-06 | P2 | GSTR-2B | **Accept** records an acceptance in one click with a canned remark and no undo, while **Reject** asks for a reason. The asymmetry makes Accept feel trivial. **[O]** | Confirm bulk and single the same way, or make Accept undoable. |
| C-07 | P2 | GSTR-2B | The ITC dropdown disables **Claimable** for unmatched rows without saying why. **[O]** | Tooltip: "Match this bill to the supplier's filing first." |
| C-08 | P1 | Supplier complaints → debit note | Raising a debit note from a complaint needs a source invoice, a source line, a quantity and a price on the same card as the status buttons, and the button stays off without saying which field is missing. **[O]** | Step the card: choose invoice → line → quantity (default to the complained quantity) → create. |
| C-09 | P2 | Supplier complaints | Status changes are single clicks ("Move to …") including closing a complaint. **[O]** | Confirm the terminal ones. |
| C-10 | P2 | Supplier ledger | See H-03: the reader must work out debit and credit from the column names. **[O]** | Plain labels ("You bought", "You paid", "You owe") with the sign explained once. |
| C-11 | P2 | Purchase register | The user sees every field the server sends. **[O]** | A fixed, ordered, labelled column set with an "all columns" option. |
| C-12 | P1 | Completing a bill (rules) | Up to six separate confirmations can arrive in sequence or together (place of supply, duplicate bill, no reverse charge, GSTIN total change, 3-way match, cancelled GSTIN) and some are GST terms a shop clerk does not know. Two of them cannot be answered at all (B-01, B-02). **[O]** | Group them in one dialog in plain words with the consequence of each; hide the ones the user's role cannot give. |
| C-13 | P2 | Completing a bill (messages) | Some server messages are written for developers: "Enable is_reverse_charge, or pass confirm_no_rcm=true". The app replaces them when it knows the code, but any new or unmapped code falls back to this text. **[O]** | Add a test that every code the server can ask to confirm has an on-screen prompt. |

## E. Carry-over from the first review (reviewed screens, still true)

These were not part of the fixes and are still open as *design* items, not defects:

- **Bill editor:** one screen holds supplier, place of supply, reverse charge, ITC, TDS, batch, serial, payment
  and number series. Defaults per supplier (ITC, reverse charge, payment terms) would remove most decisions.
- **Supplier payments:** *Clear*, *Bounce* and *Void* sit side by side in each row with no one-line
  explanation of what each does to the supplier balance.
- **Bill list:** four money filters, a status filter, a search and an icon-only row menu; first-time users do
  not find *Complete* or *Cancel*.
- **Returns dialog:** the largest dialog in the module; the live credit-note total helps, but there is no
  summary of "what will happen" before Complete.

## F. Suggested order

1. **B-01 and B-02** — give Owners and Managers a way to answer the two blocking questions, with the reason
   written down (the API already stores it for the GSTIN case). Without this a real bill can be stuck.
2. **C-01 and C-02** — bill upload is the screen most likely to be used by a new, non-technical user.
3. **H-01 and H-02** — ledger drill-down and export, the first things an accountant asks for.
4. **C-05 and C-12** — group the many GSTR-2B and completion decisions.
5. The rest are small and can be batched with the translation fixes (G-02, G-03, G-04, G-06).

## Status after implementation

Date: 2026-10-15. Verified with component tests, backend tests on SQLite and `tsc`/eslint; **not clicked through in a
browser** and **not run on Postgres**.

| ID | Result | What was done / where |
|---|---|---|
| B-01 | Fixed | Server refusal now has the code `THREE_WAY_MATCH_FAILED` with the list of differences and `can_override`. The app asks for a written reason (Owner/Manager only), retries with the override, and the approval and reason are written to the audit log. A role that cannot approve is told so in words. [`completeWithConfirms.ts`](../../web/src/utils/completeWithConfirms.ts), [`services.py`](../../backend/purchases/services.py) |
| B-02 | Fixed | `SUPPLIER_GSTIN_CANCELLED` (supplier name, date) on bill completion **and** on payments (including the bill page's Record payment and Retry). Owner/Accountant gives a reason in one dialog; the server still enforces the role. [`overrideRetry.ts`](../../web/src/utils/overrideRetry.ts) |
| B-03 | Fixed | The three Retry buttons share one handler that shows "Could not restart reading the bill: …". |
| G-01 | Fixed | The review screen's button is now **Discard this upload** and asks first. |
| G-02 | Fixed | The three messages are translated. |
| G-03 | Fixed | Ledger: empty states, WhatsApp text and the Type column are translated (Type uses `enums.ledgerType`). |
| G-04 | Fixed | GSTR-2B match class, match status and IMS action use plain words in the table and filter. |
| G-05 | Fixed | Eligibility change, accept, bulk accept and match now also refresh purchase bills. |
| G-06 | Fixed | Forecast method uses `enums.forecastMethod`; an unknown method falls back to Title case. |
| G-07 | Fixed | Register export shows "Export started…". |
| H-01 | Fixed | Ledger rows link to the bill / credit note / debit note; payments open the Supplier payments list for that supplier (needs the Money hub's supplier filter to narrow it) and returns open the returns list (they have no page of their own). The API now sends `source_id` because on the GL path `reference_id` is the journal entry. |
| H-02 | Fixed | **Export CSV** on the ledger (formula-safe `toCsv`, includes the opening row). There is still no PDF; Print covers that. |
| H-03 | Fixed | Columns renamed (see C-10), one help line explains the sign, a negative balance is described as an advance, and a **Balance brought forward** row appears when a start date is chosen (`opening_balance` from the API). |
| H-04 | Fixed | Totals strip (bills, taxable, GST, total) above the register. ITC is **not** in the register data, so it is not shown. |
| H-05 | Fixed | **This month** and **Last month** presets; the page opens on the current financial year instead of the whole register. |
| H-06 | Fixed | **Download a sample CSV** on the CSV/Excel route (headers the importer understands). |
| H-07 | Fixed | Cancel is available from the start. The wait is described from this browser's own last uploads ("usually about N min here (your last K uploads)", median, needs at least 2). With no history it keeps the generic hint. Timings are measured in the page, not on the server. |
| H-08 | Fixed | Each forecast row has **Plan a purchase** (opens a new order with a month of cover as the quantity, editable) and the page links to Purchase planning. |
| H-09 | Fixed | CA view / Client view toggle on Missing documents; the address parameter still works. |
| H-10 | Fixed for the ledger | The ledger picker is now server-searched. GSTR-2B has **no supplier picker**, so that part of the finding did not apply. |
| C-01 | Fixed | A line under the button names the first blocker ("You cannot create the draft yet: enter the bill date."). |
| C-02 | Fixed | Template note, AI-accuracy warning **and** the extraction warnings are now one notice. Direction and injection warnings stay separate on purpose (they change what you do). Confirmations sit under one heading. |
| C-03 | Fixed | The agreement is remembered in this browser; a short line replaces the notice, with **Ask me again**. |
| C-04 | Fixed | Open the draft is the main action, Upload another file next, and **Undo this import** moved into a "More actions" menu. |
| C-05 | Fixed | One "Order of work" line, Accept as the only visible row action, Reject / Pending / Supplier message under a menu. |
| C-06 | Fixed | Accept now opens the same dialog as Reject (remark pre-filled, optional). |
| C-07 | Fixed | The disabled option says "Claimable (match this bill to the supplier first)". |
| C-08 | Fixed | The card is a three-step flow: bill, faulty line, then quantity and price (shown only once a line is chosen), with the reason line under the button. There is still no complained-quantity field on the complaint, so quantity starts at 1. |
| C-09 | Fixed | Moving a complaint to a status with nowhere further to go (Rejected, Resolved) asks first. |
| C-10 | Fixed | "Reduces what you owe" / "Adds to what you owe" / "You owe after this". |
| C-11 | Fixed | Fixed, labelled columns with a **Show all columns** option. |
| C-12 | Fixed | The four GST prompts (place of supply, filing-GSTIN total change, reverse charge, duplicate bill) are rewritten in plain words with the consequence, in English and Hindi. |
| C-13 | Fixed | A web test checks that each confirm code the purchase service can ask for has a prompt, and a backend test checks the code list has not grown without one. |

### Design items carried over (section E)

| Item | Result |
|---|---|
| Bill editor decisions per supplier | Fixed: ITC treatment, reverse charge, payment terms and TDS start from the last bill from that supplier (this browser only, with a note on the screen). Place of supply comes from the supplier master. Not shared across devices (would need a server field). |
| Clear / Bounce / Void | Fixed: a help line and a tooltip on each; the bounce confirmation no longer says "receipt". |
| Bill list discoverability | Fixed: visible **Complete** on draft rows and **Cancel** on completed rows (both ask first), plus a hint about the three-dot menu. Delete stays in the menu on purpose. |
| Returns dialog summary | Fixed: "what will happen" line under the totals. |

### Also closed from the earlier review

PB-02 (planning supplier filter is now server-searched), PB-03 (Suppliers list is paged and searched on the server),
the note-editor cancel confirm now has its own test, the "Draft #n" title is translated, the purchase-note refresh
now also refreshes the dashboard, attention rows and journals, and the lint ban on `window.confirm` now covers the
purchase-adjacent screens listed in `web/eslint.config.js`.

### Still open

- **PB-01** (zero assessable value on a bill of entry): left as a CA question. Making it a hard rule would change
  how many existing bills of entry complete.
- **CA sign-off** of CA checklist P1–P3.
- **Postgres run** of `test_purchase_pay_now_concurrency_postgres.py`.
- **Browser check** of everything above.
- **Hindi review** of the new strings (`docs/PURCHASE_HINDI_REVIEW.csv`).
- **Editor split** (WP-11) was optional and not done.
- **Not reviewed yet:** bill-upload line table / party block / totals panel / source viewer and the server import
  pipeline, the purchase side of the Money hub, settings import and Tally migration pages, and the backend bill of
  entry, note, goods receipt and PDF code.

### Closed in the follow-up pass (partials)

H-07, C-02, C-04, C-08, C-12, per-supplier TDS default, bill-list Cancel, the remaining hard-coded English in
Purchase history, Supplier payments and Suppliers.

Left as they are, with reasons: no PDF ledger export (Print covers it), no ITC total in the register (the register
data does not contain ITC), defaults are not shared across devices (needs a server field and migration), and
`web/src/utils/noteQueries.ts` remains untracked because it belongs to another session.
