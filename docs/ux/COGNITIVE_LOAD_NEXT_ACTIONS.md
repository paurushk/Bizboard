# Bizboard cognitive load — next actions

**Date:** 2026-10-04
**Source:** Cognitive load canvas (`bizboard-cognitive-load`), 4 Oct 2026.
**Build spec:** [COGNITIVE_LOAD_REDUCTION_PLAN.md](COGNITIVE_LOAD_REDUCTION_PLAN.md). Action N below is CL-0N in that plan (action 1 = CL-01). That file has the wave order, files, and tests. This file is the canvas, written as the next action list.
**Status:** Not started. Writing this file does not build anything.

**Product.** Indian MSME trade ERP.
**Personas.** Proprietor, counter clerk, field order booker, godown custodian, resident bookkeeper, external CA.
**Goal.** The product absorbs GST, stock, and ledger complexity. The user keeps the commercial judgment: who, what quantity, and whether to override a limit.

**Method.** Heuristic scores, 4 Oct 2026. Each factor is 1–5. Weighted mean uses decision 1.2, fields 1.0, choices 1.0, navigation 0.8, memory 1.3, context switch 1.1, density 0.8, terminology 1.0, error risk 1.4, uncertainty 1.2, repetition 0.9, visual complexity 0.7 (weights sum to 12.4). Control counts are from `docs/ux/L1_surface_ledger.csv` (30 Sep 2026 static scan). These are triage scores, not NASA-TLX. Step and field reductions below are **design estimates**.

**Evidence.** New invoice header and collapsed statutory block, new purchase ITC and place of supply, `menu.ts` sales More and pack sidebar, `en.ts` godown / warehouse / receipt labels, L1 ledger, user journey map 30 Sep 2026, founder decisions GD-32 and GD-33. No live-user timing baseline exists except a mock POS keyboard checkout.

**Hard constraint.** Presentation, defaults, copy, focus, and where an existing action lives. No change to money, stock, GST/TCS, ITC posting, ledger derivation, permissions, or API contracts, except action 17, which is marked needs a founder decision. A hidden field posts the same default the server would use today. A non-default value stays visible as a chip.

---

## Score

| Measure | Value |
|---|---|
| Task-weighted load | **3.5 / 5** (high edge of moderate) |
| Mean page score, 154 surfaces | **1.9 / 5** (low) |
| Highest job | New purchase, **4.5** |
| Screens at static control-count score 5 | **5** (Products, item dialog, New invoice, New purchase, Invoice detail) |

118 of 154 page components score 1 or 2. The jobs that make or lose money sit on the five score-5 surfaces.

Frequency hypothesis used for the task weight (not analytics): POS 22%, new invoice 18%, new purchase 12%, receipt 10%, GSTR close 8%, invoice detail 6%, credit note 5%, field order 5%, sales history 5%, default item create 5%, setup 4%.

| Band | Range | Meaning |
|---|---|---|
| 1 Very low | 1.0–1.4 | Single-purpose lists, day book, many reports |
| 2 Low | 1.5–2.4 | POS cash scan, default item create after A2-7 |
| 3 Moderate | 2.5–3.4 | Receipts, sales history, collections, transfers |
| 4 High | 3.5–4.4 | New invoice, GSTR close, invoice detail, users, GST settings |
| 5 Very high | 4.5–5.0 | New purchase (4.5). No job scored a flat 5 |

The September static scan used a different formula (controls only) and did mark five screens as 5. Control-count score 5: Products 122 choices, New invoice 120, New purchase 102, item dialog 102, invoice detail 82.

### Heatmap (weighted 1–5)

| Workflow | Score |
|---|---|
| New purchase | 4.5 |
| GSTR close | 4.3 |
| New invoice | 4.2 |
| Setup to first bill | 3.7 |
| Users and permissions | 3.7 |
| Invoice detail | 3.6 |
| GST settings | 3.6 |
| Credit note | 3.6 |
| Bank match | 3.6 |
| Field sales order | 3.5 |
| Receipt allocation | 3.2 |
| Stock transfer | 3.0 |
| POS session | 2.7 |
| Collections | 2.7 |
| Sales history | 2.6 |
| Default item create | 1.9 |
| POS cash scan | 1.5 |

### Factor scores, three heaviest jobs

| Factor | Weight | Purchase | GSTR close | Invoice |
|---|---|---|---|---|
| Decisions | 1.2 | 4 | 4 | 4 |
| Fields | 1.0 | 5 | 3 | 5 |
| Choices | 1.0 | 5 | 4 | 5 |
| Navigation | 0.8 | 3 | 5 | 3 |
| Memory | 1.3 | 5 | 5 | 4 |
| Context switching | 1.1 | 4 | 5 | 4 |
| Information density | 0.8 | 5 | 4 | 5 |
| Terminology | 1.0 | 5 | 5 | 5 |
| Error risk | 1.4 | 5 | 5 | 4 |
| Uncertainty | 1.2 | 4 | 5 | 4 |
| Repetition | 0.9 | 4 | 3 | 3 |
| Visual complexity | 0.7 | 4 | 3 | 5 |
| Weighted score | | 4.5 | 4.3 | 4.2 |

### Already decided — these actions obey them

| Decision | Effect |
|---|---|
| GD-32 / A4-1 | Save draft, Complete, and Complete and start another all stay visible. Rank them. Complete is the only filled button. |
| GD-33 / D-UX-2 | Hiding fields on New invoice and New purchase waits until pilot staff sessions. Defaults, chips, and copy can ship while the control is still visible. |
| D-UX-4 | Leave the sidebar. Put the next action on the document. Reopen the menu only after those actions exist. |
| D-UX-3 | No undo of a posted bank match. |
| D-UX-6 | POS shows expiry of the batch the cashier typed. It does not pick a lot. |
| D-UX-7 | “Allocate to oldest” stays off until the user confirms. |
| GD-23 | The founder reads new Hindi copy before it ships. |
| GD-26 | Sessions are with staff of the three pilot companies. |

### What stays complex on purpose

Place of supply when the party state and the GSTIN disagree. ITC when one bill mixes claimable and blocked goods. Credit-limit override (clerk blocked, owner decides). Which physical batch or serial moved. A bank line that matches more than one receipt. Period lock. Recording an IRN generated outside Bizboard (live NIC submit stays off; one field, not a second product). The second confirm on sales reverse charge. Void, and any change to GST registration after the first save.

---

## Next actions

Priority is impact × frequency × error risk × effort saved. Complexity: **S** under a week, **M** one to two weeks, **L** a milestone. One engineer familiar with the editors. Planning estimates.

### 1. Infer the invoice type

| | |
|---|---|
| Priority | P0 |
| Complexity | M |
| Depends on | GD-33 only if the control is hidden. Defaulting while the select stays visible can ship earlier. |

**Problem.** Regular taxpayers pick GST, Tax, Retail, or Non-GST on every bill.

**User impact.** Every sales invoice. A wrong type is a compliance mistake.

**Root cause.** The legal enum is rendered as a required choice before the customer is known. `chooseInvoiceDefaults` already picks GST or Non-GST from the company and recent walk-in bills, then the select asks again.

**Solution.** Default from company registration and whether the customer has a GSTIN. Show a chip. Override under Change bill type. Non-GST stays an explicit override. Screen chip uses shop language (“Bill to a GSTIN customer” / “Bill to a walk-in”). The printed title stays the legal name.

**Expected benefit.** Estimate: header decisions 4–6 → 1 on a plain bill. Payload enum unchanged.

**Acceptance.** A walk-in with no GSTIN posts RETAIL or the company default without a click. A GSTIN customer posts GST. The chip shows the word. Override still changes the stored type. A later customer change does not overwrite a type the user already set. Editing an existing invoice loads the saved type.

---

### 2. Price mode as a chip

| | |
|---|---|
| Priority | P0 |
| Complexity | S |
| Depends on | Same GD-33 note if the select leaves the first row. |

**Problem.** Tax exclusive versus inclusive is a per-bill decision.

**User impact.** A wrong mode changes every line amount.

**Root cause.** Company price mode is loaded, then shown again as a select.

**Solution.** Post the company mode. Chip: “Price includes GST” or “Price before GST.” Override under More. Completed bills stay locked the way they are today (`canAmendMoney`).

**Expected benefit.** One less decision on every invoice and purchase.

**Acceptance.** A new bill opens on the company mode. Changing the chip changes line maths. A completed bill does not become editable.

---

### 3. Godown only when it matters

| | |
|---|---|
| Priority | P0 |
| Complexity | S |
| Depends on | Copy in `en.ts` and `hi.ts`. Founder reads Hindi (GD-23). |

**Problem.** A one-godown shop still picks a godown. `en.ts` uses `nav.warehouses` = “Godowns” and `billing.godown` = “Warehouse” for the same object.

**User impact.** Every invoice, purchase, and transfer setup.

**Root cause.** The warehouse select is unconditional, and the label disagrees with itself.

**Solution.** If one active godown, post it and show the name as text. If several, show the select, defaulted, labelled Godown. One word everywhere on screen: **Godown**. A non-default godown on an edited bill stays visible so the user can see stock is not coming from the default location.

**Expected benefit.** Removes a field for a single-godown shop. Keeps the field when there are two or more.

**Acceptance.** Single-godown company: no select, posted id is that godown. Two godowns: select defaults to `isDefault`. Stock checks still use that id. Edit of a bill whose godown is not the default: the godown is visible.

---

### 4. Non-default statutory chip

| | |
|---|---|
| Priority | P0 |
| Complexity | S |
| Depends on | No API change. Production hide waits on GD-33. The chip can be added while the block is still collapsed. |

**Problem.** SEZ, export, RCM, extra GSTIN, and cost centre are hidden, so a non-default can be forgotten.

**User impact.** Rare bills. High error cost when the hidden value is wrong.

**Root cause.** Collapse hides state as well as controls. The user can Complete a bill that is SEZ or reverse charge without seeing that fact on the header.

**Solution.** Keep More tax options. When any value leaves its default, show a chip row that reopens the block. RCM confirm stays. No chip when supply is B2B, GSTIN is the primary one, cost centre is empty, e-commerce GSTIN is empty, and RCM is off.

**Expected benefit.** Novices never see SEZ. Experts see that this bill is not plain.

**Acceptance.** Default bill: no chip. SEZ with payment: chip visible (“SEZ, GST charged”; the code stays on the help line). Complete still requires the existing RCM confirm when RCM is on. English and Hindi.

---

### 5. One primary action on the posted invoice

| | |
|---|---|
| Priority | P0 |
| Complexity | M |
| Depends on | Independent of GD-33. Relocate actions. Do not drop a permission-gated action. |

**Problem.** Invoice detail has 82 choices and about 55 buttons.

**User impact.** Every follow-up: print, share, collect, return.

**Root cause.** Every document capability is a peer button.

**Solution.** Rank by document state. The long tail moves into one More menu. Void keeps its confirm. Status and balance stay next to the button.

| State | Filled button | Outline | Menu / destructive |
|---|---|---|---|
| Draft | Complete | Save | Discard draft, with the existing confirm |
| Posted, balance remaining, user can take payment | Record payment | Share / print | Edit if allowed, Return goods (action 6), Void |
| Posted, settled | Share / print | Record payment hidden | Return goods, Void |
| User lacks payment permission | Share / print | — | Payment actions omitted, not disabled without a reason |

**Expected benefit.** Estimate: visible peer actions about 55 → under 8, with the rest in a menu.

**Acceptance.** Keyboard and screen reader can reach void and credit note. A clerk without payment permission does not see Record payment. No action that exists today for that permission and status disappears. axe serious/critical clean on a posted invoice fixture.

---

### 6. Return goods from the invoice

| | |
|---|---|
| Priority | P0 |
| Complexity | M |
| Depends on | Existing credit-note API. The list page stays for search. Nav item stays until D-UX-4 is reopened. |

**Problem.** Credit notes sit under Sales → More. The user must recall the path and the original bill.

**User impact.** Every return. Bookkeeper and owner.

**Root cause.** The list is the navigation. The document is the context.

**Solution.** Invoice action opens the existing credit-note editor with original invoice id, lines copied (item, original qty as the max, rate, tax, godown, serials). Quantity starts blank so a careless Complete cannot return the whole bill. “Full return” is one explicit control. Start in the menu (action 5). Promote to an outline button only if the session shows the menu hid it.

**Expected benefit.** Estimate: 6 steps → 4. Memory of rates → 0.

**Acceptance.** Partial quantity posts a partial credit at the original rate and tax treatment. Quantity above the remaining returnable qty is blocked with a sentence that names the remaining qty. Serial-tracked lines still require the serials. The draft survives a validation error. The sales-more list still creates a credit note. Stock and tax reverse as they do today.

---

### 7. Place of supply only on conflict

| | |
|---|---|
| Priority | P0 |
| Complexity | M |
| Depends on | Do not change the tax engine. Change when the UI asks and which value it sends. |

**Problem.** The user is told to supply a state the GSTIN or address already contains. Purchases block Complete with `billing.placeOfSupplyRequiredSupplier` when both are insufficient.

**User impact.** Purchases and some sales. Blocks Complete.

**Root cause.** The rule is correct. The prompt fires before inference.

**Solution.**

1. Valid GSTIN and empty address state: use the GSTIN state code. Do not ask.
2. Empty GSTIN and an address state: use the address state. Do not ask.
3. Both exist and disagree: show both and block Complete until the user picks one. Copy: “GSTIN says Maharashtra. Address says Gujarat. Which state is this bill for?”
4. Both empty: focus the state or GSTIN field. Copy: “Add the supplier’s state or GSTIN. GST needs a state for this bill.”
5. Keep the draft.

**Expected benefit.** A complete supplier master removes the decision. A conflict becomes the only decision.

**Acceptance.** Known state: no prompt, IGST vs CGST/SGST matches today’s result for that state code. Conflict: the bill cannot complete until one side is chosen, and the chosen state is what is posted. Both empty: focus lands on the field. Other lines remain.

---

### 8. Purchase line fill from item and upload

| | |
|---|---|
| Priority | P0 |
| Complexity | L |
| Depends on | Upload extraction already exists (freeze item D14). The UI shows confidence. It does not silently post a bad rate. |

**Problem.** 28 inputs at first paint, the highest in the app. HSN and rate are retyped. Bill upload lives on a side route (`/purchases/bill-upload`).

**User impact.** Every supplier bill. ITC errors show up at GSTR-2B, not at entry.

**Root cause.** The editor is a blank grid even when the item master and an uploaded file exist.

**Solution.**

1. On item select, fill HSN, GST %, unit, and last purchase cost. Caption: “from item” / “last bill”. An edit drops the caption.
2. If the filled GST % disagrees with a rate the user typed, highlight the row. Do not overwrite a user-typed rate.
3. “Upload bill” is a primary path on the purchase editor. Extracted lines use the same caption (“from upload”) and the same highlight.
4. A low-confidence extracted rate is empty or marked “check this”. It is never posted as if the user typed it.

**Expected benefit.** Estimate: typed line fields 5 → 2 (item, qty) when the master matches. First-paint inputs 28 → about 12.

**Acceptance.** A matched line shows the source of the rate and posts master HSN and GST % if the user does not edit. A user-typed rate is the posted rate. An unmatched line stays editable and cannot complete with a blank item. Posting rules unchanged. The user sees every line before it posts.

---

### 9. ITC chip with a reason

| | |
|---|---|
| Priority | P1 |
| Complexity | M |
| Depends on | A maintained blocked-category list. That is data, not a new tax rule. If the list is not ready, ship the chip and the override, and leave the recommendation as a follow-up. Do not fake a block list. |

**Problem.** CLAIMABLE / INELIGIBLE / REVERSED is an expert enum on every bill. The default is already CLAIMABLE, which is right.

**User impact.** Wrong ITC is a tax error.

**Root cause.** The judgment is shown as a control instead of a conclusion.

**Solution.** Default CLAIMABLE. Chip: “GST you can claim on this bill.” If a line’s HSN or item flag is on a blocked list, recommend “GST not claimable” and name the line. The stored value becomes INELIGIBLE only after the user accepts. Do not silently flip a previously saved CLAIMABLE bill on edit. Override to Reversed stays in the advanced block.

**Expected benefit.** Ordinary bills: 0 ITC decisions. Mixed bills: a recommendation.

**Acceptance.** Normal goods: chip says claimable, value posted CLAIMABLE, no extra click. The user can switch. Saved eligibility equals the chip at save. Edit of an old bill shows the saved value until the user accepts a recommendation.

---

### 10. Period close checklist

| | |
|---|---|
| Priority | P1 |
| Complexity | L |
| Depends on | Which GSTR flags are on. Does not enable live filing. Live GSP and NIC submit stay off. |

**Problem.** GSTR close scores 4.3 because of route-hopping and acronyms, not because of one giant form.

**User impact.** Monthly, CA and bookkeeper. High anxiety.

**Root cause.** Each worksheet is a destination. The job is one period.

**Solution.** One page, “Close the month”, linked from Reports and from the owner morning list (action 19) when the month has turned. Each row opens the existing report. One line at the top: these worksheets are for the CA; filing on the portal is a separate step. Form codes are secondary text. Row titles are shop language (“Sales for the month”, “Tax to pay”). Export pack groups today’s downloads. No new file format. No new totals.

| Row | Who sees it | Existing surface |
|---|---|---|
| Outward supplies | Regular taxpayer | GSTR-1 worksheet |
| Tax payable | Regular | GSTR-3B worksheet |
| Purchases to match | When `ENABLE_GSTR_EXTENDED` and 2B is available | GSTR-2B page |
| Composition statement | Composition registration | CMP-08 path if present |
| Missing documents | Everyone who can close | Missing-documents report |
| Books health | Accountant / owner | Books-health report |

**Expected benefit.** Estimate: 5–6 transitions → 1 page.

**Acceptance.** A regular taxpayer sees outward supplies, tax payable, missing documents, and books health. The 2B row appears only when the flag is on. A composition taxpayer does not get GSTR-1 as the primary row. Each row reaches the existing report. Export bytes match that report’s own export. The worksheet disclaimer is visible without opening help.

---

### 11. Role templates on Users

| | |
|---|---|
| Priority | P1 |
| Complexity | M |
| Depends on | Templates map onto current permission functions. No new security model. No new permission bit. |

**Problem.** Eight permission checkboxes per person. `/settings/users` is 30 fields and 50 choices.

**User impact.** Every new staff member. Owner anxiety about giving away the books.

**Root cause.** The ACL is the UI.

**Solution.** Four templates that call the existing permission helpers. “Custom” opens today’s grid. The next new user defaults to the last template chosen on this company. Prefer a server-saved preference if a field already exists; otherwise local is acceptable and must be labelled “on this browser”. Existing users are not rewritten when the page loads. The PR includes a mapping table so a reviewer can diff permissions.

| Template | Intent | Must not include |
|---|---|---|
| Cashier | POS and sales create | GST settings, user admin, financial reports beyond the counter |
| Store | Purchases and stock | User admin, GST settings |
| Bookkeeper | Purchases, receipts, reports, GST worksheets | User admin |
| Owner | Current owner set | — |

**Expected benefit.** Estimate: about 8 decisions → 1 for the common case.

**Acceptance.** Choosing Cashier produces the mapped checkbox set, and that user cannot open GST settings or user admin. Custom can still reproduce a combination that exists today. Loading the page does not PATCH existing users.

---

### 12. GST settings lock after first save

| | |
|---|---|
| Priority | P1 |
| Complexity | S |
| Depends on | Confirm is a protect step, justified by blast radius. Do not mutate posted invoices. |

**Problem.** 21 inputs remain editable on a screen that changes every future bill. GST settings has 26 fields and 54 choices.

**User impact.** Low frequency, very high error risk.

**Root cause.** Setup and day-to-day editing share one form.

**Solution.** After a valid GSTIN, registration type, and state are saved, show a summary (GSTIN, type, state, price mode if it lives here). “Change tax setup” reopens the form. The first change of registration type or GSTIN requires a confirm that says future bills follow the new setup and bills already issued do not change.

**Expected benefit.** Accidental edits become deliberate.

**Acceptance.** Summary is the first view when setup is complete. Confirm names the effect. In-progress invoice drafts keep the type they already resolved (action 1) until the user reopens them. Cancel returns to the summary with the old values. axe clean.

---

### 13. Products page, search first

| | |
|---|---|
| Priority | P1 |
| Complexity | M |
| Depends on | Item create is already short (A2-7). This action is the page around it. |

**Problem.** 122 choices and about 58 buttons on the catalog.

**User impact.** Item maintenance. Less often than billing, still the densest page.

**Root cause.** Import, attributes, stock, and edit are peers of search.

**Solution.** Search and Add item are primary. Import, bulk edit, and attribute tools move into one menu. Opening stock, lots, and serials stay behind the existing button in the item dialog. Do not remove a column the billing line needs from the item record.

**Expected benefit.** Default create stays near 1.9. The page stops competing with the dialog.

**Acceptance.** Add item still opens the short form. A keyboard user can reach import. No required item field is dropped from the API payload of the dialog.

---

### 14. POS focus contract

| | |
|---|---|
| Priority | P1 |
| Complexity | M |
| Depends on | Journey doc already names this residual. No change to price, tax, or tender posting. Do not add a lot picker (D-UX-6). |

**Problem.** Editing quantity can throw focus back to the scanner.

**User impact.** Every correction at the counter. Queue stress. A single cash scan scores 1.5. The full session scores 2.7. This is the main extraneous load on an otherwise light screen.

**Root cause.** A focus effect treats any blur as “return to scan.”

**Solution.** Focus returns to search only after a successful scan or an explicit shortcut. Quantity, discount, and batch keep focus until Enter or Escape. Escape returns to search and does not change the line. F1/F4/F5/F7/F8/F9 stay printed on the buttons. Do not add a mouse path as the primary path.

**Expected benefit.** Removes a hesitation on the one low-load screen that must stay low.

**Acceptance.** A test types a multi-digit quantity without the search field receiving those digits. A scan wedge still lands in search when the last committed field was search. Hold (F8) and tender keys still work when focus is on search. The existing keyboard checkout spec stays within its budget.

---

### 15. Plain blocked-Complete sentences

| | |
|---|---|
| Priority | P1 |
| Complexity | S |
| Depends on | Extends A2-8, which already focuses an empty party or item. HTTP failures stay on the A3-1 path and keep the support id. |

**Problem.** Credit, serial, place of supply, and RCM stops use system phrases.

**User impact.** Every failed Complete. The user does not know the one fix.

**Root cause.** Messages name the rule. They do not name the next control.

**Solution.** Problem, cause, one action, focus that control, keep the draft. Copy in English and Hindi.

| Blocker | Sentence |
|---|---|
| No party or no line | “Choose a customer, then add an item.” Focus the empty one. |
| Credit limit | “{name} would reach {exposure} against a limit of {limit}. Ask the owner, or reduce the bill.” |
| Missing serial | “Enter the serial for {product}.” Focus that cell. Do not clear the line. |
| Place of supply | Use action 7 copy. |
| RCM not confirmed | “You marked reverse charge. Confirm it, or turn reverse charge off.” Focus the confirm checkbox. |
| Item saved, opening stock failed | “The item exists. Opening stock did not post. Retry stock only.” Do not ask them to recreate the item. |
| Saved offline | Keep the banner. Say whether stock and the number are pending until reconnect. |
| Network / 403 / 5xx | Keep the plain class message and the support id. |

**Expected benefit.** Less re-reading. No second data entry.

**Acceptance.** Each blocker focuses a field. Lines already entered are still on screen. The founder has read the Hindi. Vitest covers each sentence key.

---

### 16. Money in / money out labels

| | |
|---|---|
| Priority | P1 |
| Complexity | S |
| Depends on | `en.ts` and `hi.ts`. Founder reads Hindi (GD-23). No route change. |

**Problem.** Receipts, supplier payments, payment links, and collections are four names for movement of cash.

**User impact.** Owner and occasional user. Mis-posted money.

**Root cause.** Ledger nouns are the navigation nouns. The owner says “payment received”. The voucher correctly says Receipt.

**Solution.**

- `nav.receipts` → “Money in”. Page title can stay “Receipt”.
- `nav.supplierPayments` → “Money out”. Page title can stay “Payment”.
- Collections stays a chase-dues label, not a third word for the same voucher.

**Expected benefit.** The owner recognizes the menu. The munshi still sees Receipt on the voucher.

**Acceptance.** Both languages. Sidebar shows the new labels. The receipt document heading still says Receipt. No route change. Glossary test covers the new pair so the words do not drift. Founder has read the Hindi.

---

### 17. Bank match interrupts only when ambiguous

| | |
|---|---|
| Priority | P2 |
| Complexity | M |
| Depends on | **Needs a founder decision** before any code. Writes into `docs/ux/founder_decisions.md` first. This posts money. No undo of a posted match (D-UX-3). |

**Problem.** Every suggestion asks for attention. The subtitle also explains a second recon product (operational match versus GL bank recon).

**User impact.** Bookkeeper, month end.

**Root cause.** The safety rule “never auto-apply ambiguous matches” was applied to unique matches too.

**Solution, only if the founder agrees.** A candidate that is unique on amount and inside the existing date tolerance is applied with the same post the user would confirm today. Two or more candidates stay in a queue. Page title: “Match bank lines.” The GL screen keeps its own name. Help can say they are different. The subtitle does not teach both jobs at once.

**Expected benefit.** Decisions fall to the collisions only.

**Acceptance if built.** Two receipts with the same amount stay unapplied. A single exact candidate posts and appears in the matched list. No journal side effect beyond today’s match action.

---

### 18. Field order context strip

| | |
|---|---|
| Priority | P2 |
| Complexity | M |
| Depends on | Offline shows last synced values with a time. Do not invent stock or credit when offline. |

**Problem.** The order booker must remember price, credit, and stock, often on a phone with a weak signal. Field order scores 3.5.

**User impact.** Every site visit.

**Root cause.** Those facts live on other screens.

**Solution.** A strip on the sales order: they owe, credit left, stock in the selected godown for the highlighted line, and offline outbox count or “last synced at {time}”. The strip must not cover the save button at 393px. A missing figure says it is unknown rather than zero, when the API distinguishes those.

**Expected benefit.** Fewer trips to the customer ledger and the stock page.

**Acceptance.** Strip visible at 393px. Stale cache shows the time. A missing figure is labelled unknown when the API says so.

---

### 19. Owner morning list, five rows

| | |
|---|---|
| Priority | P2 |
| Complexity | M |
| Depends on | Reuse attention and collections queries. Do not add a prediction model. Collections copy stays in owner language (A3-5). Prefer extending Attention over a third list. |

**Problem.** The proprietor’s question is “what needs me,” and the app answers with modules.

**User impact.** Daily, short session.

**Root cause.** Dashboard, attention, collections, and low stock are separate destinations.

**Solution.** At most five rows, each one action, from queries that already exist:

1. Dues to chase.
2. Bills held for credit override.
3. Low stock (keep the existing `<=` rule, D-UX-1).
4. Setup still blocking the first real bill.
5. Period-close row when the month has rolled and the checklist (action 10) is not done.

A quiet day says nothing is waiting and offers New bill and POS. An empty company shows setup only.

**Expected benefit.** A five-minute session has one screen.

**Acceptance.** Each row deep-links to the existing screen. No row appears when its count is zero. Quiet state has the two links.

---

### 20. Series number as a caption

| | |
|---|---|
| Priority | P3 |
| Complexity | S |
| Depends on | No change to number allocation. |

**Problem.** Prefix and next number look like inputs. They are disabled (`billing.invoicePrefix`, `billing.invoiceNumber`). The scan counts them as fields.

**User impact.** Small, on every new bill. Adds visual fields.

**Root cause.** Read-only inputs still count as form fields in the eye and in the scan.

**Solution.** Replace the two controls with one caption: “Next bill {prefix}-{padded number}.” Series editing stays in settings. Edit mode shows the fixed number as text (`billing.invoiceNumberFixed` already exists).

**Expected benefit.** Two apparent fields removed. No behavior change.

**Acceptance.** The posted number is unchanged. The caption matches the previous helper text. Edit mode does not offer an editable number. Existing series tests stay green.

---

## Order of work

Later waves can start design while an earlier wave is in review. Do not start production editor disclosure before the session.

| Wave | When | Actions | Why |
|---|---|---|---|
| 0. Baseline | Before any editor visual change | Measurement only | HEART T4, T5, T7, T10 have no real-backend numbers |
| A. Safe defaults and copy | Now. Does not hide a control | 1a, 2a, 3a, 15, 16, 20 | Removes decisions while the control is still visible, so GD-33 is not triggered |
| B. Session stimulus | Before GD-33 sessions | Prototype of 1b, 2b, 4, 5 | The three screens the pilot staff should react to |
| C. Editor disclosure | After sessions, if staff can complete a plain bill on the prototype | 1b, 2b, 3b, 4 | The production hide |
| D. Document actions | Parallel with A | 5, 6, 7 | Highest recall and choice cuts outside the editors |
| E. Purchase absorption | After action 7 | 8, 9 | Highest single job score (4.5) |
| F. Monthly and admin | After D | 10, 11, 12, 13 | Lower frequency, high blast radius or high navigation |
| G. Counter | Parallel with A | 14 | POS focus is independent of GST disclosure |
| H. Decision or context | After F | 17, 18, 19 | 17 posts money. 18 and 19 are new surfaces |

**Wave 0 tasks to time on a real backend** (desktop and 393px): T4 B2B invoice, 3 lines, customer and items exist; T4b the same bill for a walk-in with no GSTIN; T5 record a receipt and allocate; T7 purchase bill, manual, 3 lines; T9 credit note against an existing invoice; T10 from “month is ready” to GSTR-1 export plus the 3B worksheet open; T2 POS cash, one scanned item (already guarded in mock mode).

**Session pass for Wave C.** At least four of five participants (staff of the three pilot companies, including the counter clerk and the person who enters purchase bills) complete the plain bill without asking where the invoice type went, and the bookkeeper can find the chip on a SEZ example. If they cannot, keep Wave A and do not hide the selects.

**First PRs, in this order.**

1. Actions 20, 3a, and 16. Caption, godown wording, money-in labels. Copy and presentation. No inference.
2. Action 15. Blocked-Complete sentences, both languages.
3. Actions 1a and 2a. Inference and price-mode caption while the selects stay visible.
4. Action 5. Invoice detail button rank.
5. Action 14. POS focus, with the keyboard checkout spec still green.
6. Prototype flag for Wave B covering the hidden-select versions of actions 1, 2, 3, and the chip (action 4). Dev flag, not the pilot default.

PR 6 does not become the production default until the session pass is written down.

**Do not start by redrawing the menu.** Moving credit notes onto the invoice removes the recall without a new information architecture. Reopen the menu only after the document actions exist.

---

## Audit detail the actions rest on

### Top problems

| # | Problem | Load type | Where |
|---|---|---|---|
| 1 | User classifies the bill (type, price mode, supply) before the party and lines have answered it | Extraneous decision | `/sales/new` header |
| 2 | Supplier bill retypes GSTIN, rates, HSN, and ITC that the bill and item master already contain | Memory + fields | `/purchases/new` |
| 3 | Posted invoice offers about 55 buttons. The next job (print, share, collect) does not win | Visual + choice | `/sales/history/:id` |
| 4 | Returns, credit notes, orders, and challans live under Sales → More | Recall | `menu.ts` sales-more |
| 5 | Month-end is many report routes, each with its own GST acronym | Navigation + terms | `/reports/gstr*` |
| 6 | Godown, Warehouse, and the nav label Godowns name one object | Terminology | `en.ts` |
| 7 | GST settings (54 choices) can poison every later invoice | Error risk | `/settings/gst` |
| 8 | Permission grid asks the owner to understand eight capabilities per user | Decision | `/settings/users` |
| 9 | Products page still exposes 122 choices even after opening stock was hidden on create | Choice | `/inventory/products` |
| 10 | Place of supply and RCM block Complete with a second confirmation the user must interpret | Uncertainty | Both editors |

### Memory — the system shows it at the moment of the decision

| User is asked to remember | System already has | Move |
|---|---|---|
| Customer state and GSTIN | Party master | Infer intra-state and place of supply. Ask only on conflict |
| Credit days and limit | Customer | Already applied when credit days > 0. Show “Owes · limit · available” before Complete |
| Item HSN, GST %, unit | Item master | Fill the line. Edit stays available |
| Price for this customer | Price list and last invoice | Default the line price. Show “last sold at” |
| Which godown | Default godown | Hide the picker when one active godown |
| Next invoice number | Series | Already read-only. Show it as a caption (action 20) |
| Open invoices for a receipt | Derived AR | List them on the receipt. Oldest stays a recommendation with confirm (D-UX-7) |
| Supplier bill GSTIN and rates | Supplier, items, upload | Pre-fill from master. Upload is the default path for photo bills |
| Batch expiry | Lot record | POS already shows expiry for the batch typed. Do not ask the cashier to pick a lot |
| Where credit notes live | Menu memory only | Start the credit note from the invoice |
| Which GSTR file the CA asked for | Registration type and period | Checklist names the file in owner language, with the form code as secondary text |
| Permission bits per staff member | Role | Save last role as the template for the next user |

### Decisions — default, then recommend, then explain, then allow override

| Decision | Necessary? | Treatment |
|---|---|---|
| Invoice type GST / Tax / Retail / Non-GST | The legal outcome is necessary. The menu is not, on every bill | Default from registration and whether the customer has a GSTIN. Chip. Override |
| Tax exclusive vs inclusive | Shop-level, rarely per bill | Company default. Chip. Override under More |
| Godown | Only when more than one | Default. Show picker only if 2+ active |
| Supply type SEZ / export | Rare | Already under More tax options. Chip when not B2B |
| Sales RCM + confirm checkbox | Rare and high risk | Keep the second confirm. Show the first checkbox only after More is open |
| Payment terms days | Only for credit customers | Already revealed when credit days or limit exist. Keep |
| ITC claimable / ineligible / reversed | Judgment on mixed bills | Default CLAIMABLE. Recommend ineligible from a blocked HSN list. Explain one line. Override |
| Allocate oldest invoices | Helpful, not safe to apply silently | Keep confirm (D-UX-7). Show the preview list |
| Complete vs draft vs complete-and-another | All three are real jobs | GD-32: keep all visible. Complete is the only filled button |
| Bank line match | When two receipts share an amount | Auto-apply unique matches only after the founder decision (action 17). Interrupt on ambiguity |
| Credit limit override | Owner judgment | Block the clerk. One owner action with the numbers already computed |
| Cost centre, e-commerce GSTIN | Exceptional | Stay hidden. No default decision |

### Navigation

The pack sidebar already hides insights, manufacturing, payroll, CRM, complaints, tickets, job cards, projects, insurance, and contracts for a new company. The full demo menu stays off the pilot default.

| Path | Steps (estimate) | Issue | Bring context here |
|---|---|---|---|
| Sales → New invoice | 2 | Acceptable | — |
| Sales → More → Credit notes | 3 | The job starts from a bill | Action on the invoice |
| Sales → More → Quick entry | 3 | A faster bill is hidden from the people who need speed | Secondary action on New invoice, or POS |
| Purchases → New purchase | 2 | The form is the load | — |
| Reports → one GSTR form | 2 per form, 4–6 forms in a close | The navigation is the workflow | One Period close page |
| Settings → GST | 2 | Fine once a year. Dangerous if revisited casually | Lock behind “Change tax setup” after first save |
| POS | 1 from sidebar | Good | Keep POS as a top-level item |

Returns, receipts against a bill, and delivery challans are actions on the document the user is looking at. List pages stay for search.

### Information timing

| Information | Timing today | Change |
|---|---|---|
| Invoice number and prefix | Shown as two fields before the customer | Caption: “Next bill GST-00042” |
| SEZ, export, RCM, e-commerce GSTIN | Collapsed. Good | Chip when any value is non-default |
| HSN, MRP, supply nature on lines | On the line table | Hide until the line is expanded. Keep on the printed bill |
| Customer outstanding | Available after party select | Keep beside the party |
| GL versus operational bank recon | Both vocabularies on the bank screen subtitle | One job title: Match bank lines. Mention the ledger only in help |
| Day book versus cash book | Disclaimer argues they differ | Name the page for what it counts, once |
| Paid, Completed, Returned | Three status words for different objects | One status language. Enforce on the three screens |
| Empty receipt columns | A4-2 hides columns empty for the whole page | Keep |

### Forms — minimum the user should type

| Form | Scan | First paint | Minimum the user should type |
|---|---|---|---|
| New invoice | 49 fields, 68 buttons, 120 choices | 23 inputs | Customer, date if not today, lines (item, qty). Type, price mode, godown, number pre-filled |
| New purchase | 42 fields, 60 buttons, 102 choices | 28 inputs | Supplier, supplier bill no, date, lines. GSTIN and rates from master or upload |
| Item dialog | 52 fields, 102 choices | Create path reduced (A2-7) | Name, selling price, GST %. Lots behind a button |
| GST settings | 26 fields, 54 choices | 21 inputs | Registration type, GSTIN, state. Everything else follows |
| Users | 30 fields, 50 choices | Permission grid | Name, phone, one role. Advanced permissions behind the role |
| POS tender | 22 fields, 59 choices | Cart + 4 tenders | Scan, then one tender key |

Conditional fields that stay conditional: payment terms only for a credit party, RCM confirm only after RCM is on, place of supply only when the party does not already determine it, serial numbers only on serial-tracked lines.

Progressive disclosure changes what is visible. It does not drop godown, price mode, supply type, or ITC from the API.

### Terminology

Shop language on the screen. Statutory language on the print, the export, and the help line.

| Current | Say this | Explain | Why |
|---|---|---|---|
| Godowns / Warehouse / godown | Godown | Stock location. One default | Same object, two words |
| GST invoice / Tax invoice / Retail invoice | Bill to a GSTIN customer / Bill to a walk-in | The print title stays legal | Four type names overlap in shop speech |
| Tax exclusive / Tax inclusive | Price before GST / Price includes GST | Company default shown as a chip | “Exclusive” is accountant language |
| Place of supply | Which state is this sale for? | Drives CGST+SGST or IGST | Ask only when GSTIN state and address state differ |
| Sales reverse charge (RCM) | Customer pays the GST, not you | Second confirm stays | RCM is an acronym |
| SEZWP / SEZWOP / EXPWP | SEZ, GST charged / SEZ, no GST / Export, GST charged | Codes stay on the help line | Codes are for the return |
| Receipts | Money in | Against customer bills | The voucher title stays Receipt |
| Supplier payments | Money out | Against supplier bills | Pairs with money in |
| Customer outstanding | They owe you | Hindi बकाया already in the glossary plan | “Receivables” stays in the CA export |
| Delivery challan | Delivery note | Not a tax invoice | Say it is not a bill |
| ITC eligibility | GST you can claim on this bill | Claimable unless the goods are blocked | ITC is CA language on a store screen |
| Operational match, not GL bank recon | Match this bank line | Help can mention the ledger | Two recon products in one subtitle |

Do not regress Collections (A3-5) or the Paid / Completed / Returned glossary.

### Errors

| Situation | Replacement |
|---|---|
| Complete disabled, party or item empty | Keep the focus move. Add “Choose a customer, then add an item.” |
| Credit limit | Name the customer, the exposure, and the limit. Ask the owner, or reduce the bill |
| Missing serial | Name the product. Focus the serial cell. Keep the line |
| Place of supply missing | Action 7 copy. Focus that field |
| RCM not confirmed | “You marked reverse charge. Tick confirm, or turn reverse charge off.” |
| Saved offline | Keep the banner. Say whether stock and the number are pending |
| Item saved, opening stock failed | Retry stock only. Do not recreate the item |
| Network / 403 / 5xx | Keep the class message and the support id |

**Interrupt (keep):** void, sales RCM confirm, credit-limit override, GST setup change after first save, ambiguous bank match, allocate-to-oldest confirm.

**Do not add a confirm for:** a unique bank match if action 17 is approved, a plain Complete, opening More tax options, or a second confirm after the user has already pressed “Allocate to oldest”.

### Visual — one filled button

| Screen | Competing attention | Primary | Secondary | Destructive |
|---|---|---|---|---|
| New invoice | Three completion buttons, shortcut hints, header selects | Complete | Save draft; Complete and start another | None on a draft |
| Invoice detail | 55 buttons, 5 dialogs | Share or print, else Record payment if a balance remains | Edit, duplicate | Void, delete draft |
| Products | 58 buttons | Add item, or the search box | Import | Delete item |
| POS | Search, cart, four tenders | The scan field, then the tender key that matches the last tender | Hold (F8) | Remove line |
| GST settings | 21 inputs at once | Save tax setup | Advanced rates | None |

Phone width: editors still had about 17–21 targets under 44px at 393px in the September crawl. Theme now forces 44px on icon buttons below the `sm` breakpoint (A2-4). Re-measure before calling Fitts done. POS cash and UPI are 48px on phones (A2-10).

### Context switches

| Switch | Why it hurts | Bring it in |
|---|---|---|
| Invoice → new customer | Draft anxiety | Inline create already returns the new id. Keep the draft mounted |
| Invoice → new item | Same | Same inline create. Do not navigate to Products |
| Invoice → stock screen | “Do I have it in this godown?” | Line already warns with warehouse quantity. Keep the number on the line |
| Receipt → invoice list | Matching amounts in the head | Open invoices on the receipt, with remaining balance |
| CA → GSTR-1, 3B, 2B, books health, missing documents | Five memories of the same period | Period close checklist with those panels |
| Counter → owner for credit override | Queue is waiting | Owner PIN or a queued approval. The bill stays on screen |
| Pilot e-invoice utility → IRN field | External system. Intrinsic for this release | One field “IRN from the portal” with the status |
| Field phone → desktop price list | Patchy network | Price, credit, and stock on the order. Offline outbox state visible |

### Personas

| Persona | Load they feel | Design response |
|---|---|---|
| New owner (first week) | Setup + first bill, 3.7. Fear of a wrong GST setting | Wizard ends on a real bill. GST settings lock after save |
| Occasional owner | Forgets where credit notes and receipts are | Actions on the bill. Morning list of at most five items |
| Regular bookkeeper | High tolerance for fields. Low tolerance for retyping and wrong ITC | Purchase upload and allocation speed. Do not hide the ledger |
| Expert / CA | Acronyms are fine. Hunting routes is not | Period close. Export. Keep GSTR codes in the export |
| Counter clerk | POS 1.5–2.7. Modals and focus theft are the enemy | Keyboard. One tender. No invoice-type menu |
| Field booker, phone | Order 3.5 plus network doubt | Credit left and stock on the order. Outbox visible |
| Godown | Purchase lines, batch, expiry | Scan-first lines. Expiry shorthand |
| Low digital literacy | Four invoice types, RCM, exclusive/inclusive | Defaults and chips. Hindi बकाया / वापस on status |
| High-volume operator | Anything that resets focus or asks twice | Complete and start another stays one click (GD-32) |
| Administrator | Users 3.7 | Four roles. Custom permissions under Advanced |

The same invoice screen serves the clerk and the munshi if the first paint is customer, date, lines, and total, and the statutory block opens itself only when the document is not a plain B2B or B2C bill. The chip is a button that reopens the block.

| Persona | Actions they must be able to finish | Pass |
|---|---|---|
| Proprietor | 19, 12, 5 | Five-minute list, or a summary of tax setup, without the full form |
| Counter clerk | 14, and they never see the four invoice types on POS | Quantity edit keeps focus |
| Field booker | 18 | Strip at 393px, stale data labelled |
| Godown | 8 | Item select fills HSN. Batch and expiry still available when the item needs them |
| Bookkeeper | 4, 6, 7, 9, 10 | Can see that a bill is not a plain B2B bill. Can start a return from the invoice |
| CA | 10 | Export still has GSTR-1 and 3B codes. Disclaimer says worksheet |
| New user | 1, 20 | First plain bill does not require the type menu once Wave C has passed |
| Admin | 11 | Cashier template cannot open user admin |

### Before / after (estimates, not baselines)

**New invoice, plain local bill.**

Current: open → party → read number → pick type → pick price mode → pick godown → lines → optional more tax → choose among three completion buttons → complete.

Optimized: open → party (type and state inferred) → lines with price and GST filled → review chip “GST bill · price includes GST · Main godown” → Complete. Draft and Complete-and-another stay as outline buttons.

| Measure | Current | After (estimate) | Move |
|---|---|---|---|
| Header decisions on a plain bill | 4–6 | 1 (party) | Default type, price mode, godown |
| Visible inputs at first paint | 23 | about 8–12 | Collapse. Do not delete fields |
| Choices in the component | 120 | unchanged in code; far fewer on screen | Hide |
| Screens | 1 | 1 | Keep |

**New purchase.**

Current: supplier → retype GSTIN and state → type every line rate and HSN → decide ITC → complete.

Optimized: photo or supplier → bill number and date → lines matched to items with rates suggested → ITC chip “GST claimable” → review payable, including reverse charge if on → complete.

| Measure | Current | After (estimate) | Move |
|---|---|---|---|
| Inputs at first paint | 28 | about 12 | Pre-fill GSTIN, rates, HSN |
| Manual tax calculations | 0 if masters are right; user still checks | 0, with a mismatch highlight | Automate |
| ITC decision on a normal bill | 1 explicit | 0 until a blocked HSN | Default |

**Month close.** Current: open GSTR-1, then 3B, then 2B if the flag is on, then books health, then missing documents. Estimate 5–6 navigation transitions. Optimized: Period close → this month’s checklist → each row opens its worksheet in place → one export pack for the CA. Forms the user must name: 3 or more acronyms → 1 checklist, codes as secondary.

**Credit note.** Current: Sales → More → Credit notes → find the invoice → copy lines. Estimate 6 steps and a memory of the original bill. Optimized: open invoice → Return goods → quantities → review tax reversal → post. Estimate 4 steps. Original rates pre-filled.

### Reduction levers

| Lever | What moves |
|---|---|
| Eliminate | Re-deciding invoice type, price mode, and godown after the system has set them. Recreating an item after opening stock failed |
| Automate | Tax split, series number, round-off, per-godown stock, place of supply when GSTIN and address agree, unique bank match (after the founder decision) |
| Pre-fill | HSN, GST %, last cost, GSTIN, customer credit line, next number |
| Recommend | ITC on a blocked HSN, oldest-invoice allocation (still confirmed), invoice type from the customer’s GSTIN |
| Simplify | Blocked-Complete sentences. Shop words on the screen, statutory words on the print |
| Consolidate | Period close. Return goods on the invoice. Morning list |
| Hide | SEZ, RCM, cost centre, serials, opening stock, godown when there is one, permission grid behind a role |
| Explain | Chip when a bill is not a plain local bill. Worksheet disclaimer on period close |
| Guide | First bill ends the setup wizard. Morning list on a quiet day offers New bill and POS |
| Protect | Void, sales RCM, credit override, GST setup change, ambiguous bank match, allocate-to-oldest |

---

## Principles to enforce

| Principle | Enforce it as |
|---|---|
| Recognition over recall | The next action lives on the document the user already opened |
| The system remembers | Party, item, series, godown, and price list fill the document |
| The system calculates | Tax split, totals, round-off, credit exposure, godown quantity |
| The system recommends | Invoice type, ITC, oldest allocation. User confirms the risky ones |
| Do not re-enter known facts | GSTIN and HSN come from the master or the upload |
| Do not show it early | SEZ, RCM, cost centre, serials, opening stock stay behind an explicit open |
| Defaults | Company price mode, default godown, CLAIMABLE ITC, today’s date |
| One primary action | Filled button. GD-32 siblings are outline buttons |
| Fewer choices | Role templates. Bill type chip. Godown hidden when unique |
| Stay in context | Inline party and item create. Period close panels. Credit strip on the order |
| Preserve work | Draft, offline outbox, and “item saved but stock failed” retry |
| Errors name the fix | Problem, cause, focus the field |
| Status is visible | Non-default chip. Outbox. Credit line. Held POS bills |
| Progressive disclosure | First paint is the plain bill. Experts reopen the chip |
| Few interruptions | Confirm void, RCM, credit override, tax-setup change, ambiguous bank match |
| Common task is fast | POS scan and Complete and start another |
| Uncommon task is findable | From the document, not from memory of Sales → More |
| Business rules feel simple | The return and the ledger keep the real rule. The screen states the consequence in shop language |

---

## Acceptance for every action

| Gate | Check |
|---|---|
| Business logic | Posted tax, stock, ITC, credit hold, and permissions match the previous API contract |
| No silent statutory change | A hidden control posts the same default the server would have used |
| Non-default stays visible | SEZ, RCM, extra GSTIN, non-default godown, and non-default price mode show a chip |
| Work is kept | A validation block does not clear the draft. Offline outbox rules stay |
| Both languages | New copy in `en.ts` and `hi.ts`. Founder reads the Hindi |
| Access | axe serious/critical clean on the touched route. 44px targets at 393px. Keyboard reaches the overflow actions |
| Plain bill task | After a baseline is captured (HEART T4): fewer header decisions. Do not quote a time until that baseline exists |
| POS | Quantity edit does not lose keystrokes. Keyboard checkout budget stays green |
| Protect list | Void, RCM confirm, credit override, GST setup change, and ambiguous bank match still interrupt |

A PR states which action it implements, adds or updates a Vitest, adds a Playwright step when the action names one, keeps `en.ts` and `hi.ts` in parity, and cites the Wave 0 baseline if it claims a reduction. Otherwise the PR says “estimate only”.

**Programme done when:** Wave A has shipped. The Wave B session is recorded, and Wave C has either shipped or been explicitly stopped with the session notes. Actions 5, 6, and 7 have shipped. Action 8 has shipped, or the item-fill half has shipped and the upload half is still open. Actions 10, 11, and 12 have shipped. T4 header-fields-touched is lower than the Wave 0 csv on the same script. No open P0 is left without a deferred reason in the reduction plan’s progress log.

---

## Recommendation

Ship the absorption layer on the two editors and the posted invoice. Leave the tax engine, the stock engine, and the menu structure alone until the document itself carries the next action.

The first session with pilot staff is a prototype of three screens: a plain bill that opens with customer and lines only, a chip row when the bill is SEZ or reverse charge, and an invoice page whose filled button is Record payment or Share. That is the GD-33 stimulus.

A proprietor can issue a local bill without learning invoice types. A bookkeeper can see that a bill is not local, because the chip says so. A CA still receives GSTR-1 and 3B with the real codes. The complexity stays in the document and the checklist.

**Out of scope.** Sidebar restructure (D-UX-4). Remapping shortcuts to Tally keys (D-UX-5). Live GSP filing, live NIC e-invoice, and e-way submit. A new prediction or dunning model. Undo of a posted bank match. Changing the tax, stock, credit-hold, or permission engines. Hiding Save draft or Complete and start another (GD-32). Auto-picking a POS lot (D-UX-6). Applying oldest allocation without the confirm (D-UX-7).
