# Bizboard cognitive load reduction plan

**Date:** 2026-10-04
**Status:** Plan. Not scheduled. Nothing in this file is built by writing it.
**Source:** Cognitive load audit of 2026-10-04 (task-weighted score 3.5 / 5; page mean 1.9 / 5 across 154 surfaces). Control counts from `docs/ux/L1_surface_ledger.csv` (2026-09-30). Journeys from `docs/USER_JOURNEY_MAP_AND_IMPLEMENTATION_PLAN.md`. Personas from `docs/ux/personas_jtbd.md`.
**Related:** `docs/ux/cognitive_load_audit.md` (control-count triage), `docs/ux/founder_decisions.md`, `docs/ux/heart_metrics.md`, `docs/UX_ACTION_ITEMS.md` (A2-5, A2-6, A4-1).

**Goal:** The product absorbs GST, stock, and ledger complexity. The user keeps the commercial judgment: who, what quantity, and whether to override a limit.

**Hard constraint:** No change to money, stock, GST/TCS, ITC posting, ledger derivation, permissions, or API contracts, except where a row is marked `NEEDS-FOUNDER-DECISION`. Presentation, defaults, copy, focus, and where an existing action lives are in scope.

---

## 1. What this plan is for

The September control-count scan showed the load is concentrated. 118 of 154 page components score 1 or 2. Five surfaces score 5: Products (`/inventory/products`, 122 choices), the item dialog (102), New invoice (`/sales/new`, 120), New purchase (`/purchases/new`, 102), and Invoice detail (`/sales/history/:id`, 82).

The jobs that carry the task-weighted score:

| Job | Heuristic score (1–5) | Band |
|---|---|---|
| New purchase | 4.5 | Very high |
| GSTR / period close | 4.3 | High |
| New invoice | 4.2 | High |
| Setup to first bill, Users | 3.7 | High |
| Invoice detail, GST settings, credit note, bank match | 3.6 | High |
| Field sales order | 3.5 | High |
| Receipt allocation | 3.2 | Moderate |
| POS session | 2.7 | Moderate |
| POS cash scan of one item | 1.5 | Low |
| Default item create (after A2-7) | 1.9 | Low |

Scores are expert heuristics, not NASA-TLX. Step and field reductions later in this file are **design estimates**. `docs/ux/heart_metrics.md` has no real-backend baseline except a mock-mode POS keyboard checkout. Do not quote an estimate as a measured result.

### Already true in the code (do not rebuild)

- `web/src/pages/sales/invoiceDefaults.ts` `chooseInvoiceDefaults` sets invoice type and price mode from company registration, company price mode, and the last few walk-in bills when there are at least three. The selects are still on the header.
- `NewInvoicePage.tsx` already collapses supply type, extra GSTIN, cost centre, e-commerce GSTIN, and sales RCM behind “More tax options” (`showAdvancedTax`).
- Payment terms open when the customer has credit days or a credit limit.
- A2-7: new items start on core fields. Opening stock, lots, and serials open from a button in `ItemFormDialog.tsx`.
- A2-8: a Complete blocked only by a missing party or item focuses that field.
- A3-1: HTTP errors use plain language and a support id.
- A3-5: Collections copy is in owner language.
- A4-2: Receipt columns that are empty for the whole page are hidden.
- D-UX-6: POS shows the expiry stored on the batch the cashier typed. It does not pick a lot.
- D-UX-7: “Allocate to oldest” is off until the user confirms. The preview text exists on receipts.
- Pack sidebar (`PACK_HIDDEN_SECTIONS` in `web/src/navigation/menu.ts`) hides insights, manufacturing, payroll, CRM, and the other dark modules for a new company.

### Founder constraints this plan obeys

| Decision | Effect on this plan |
|---|---|
| GD-32 / A4-1 | Save draft, Complete, and Complete and start another all stay visible. Rank them. Do not fold them into a menu. |
| GD-33 / D-UX-2 | Hiding fields on New invoice and New purchase waits until pilot staff sessions are scheduled. Production editors stay as they are until then. Defaults that still show the control, chips, and copy can be designed and prototyped earlier. |
| D-UX-4 | Do not restructure the sidebar in this plan. Move the next action onto the document. Reopen the menu only after those actions exist. |
| D-UX-3 | No undo of a posted bank match. |
| D-UX-7 | Oldest-invoice allocation stays confirm-gated. |
| GD-23 | The founder reads new Hindi copy before it ships. |
| GD-26 | Sessions are with staff of the three pilot companies, in the pilots’ first weeks. |

---

## 2. What stays complex on purpose

Do not “simplify” these. Explain them, default them, or ask only at the moment they are actually in doubt.

- Place of supply when the party state and the GSTIN state code disagree.
- ITC when one bill mixes claimable and blocked goods.
- Credit-limit override. The clerk is blocked. The owner decides.
- Which physical batch or serial moved.
- A bank line that matches more than one receipt.
- Period lock.
- Recording an IRN generated outside Bizboard. Live NIC submit stays off in the pilot profile. One field, not a second product.
- The second confirm on sales reverse charge.
- Void, and any change to GST registration after the first save.

---

## 3. Design rule for every row

**Default → recommend → explain → allow override.**

A control that posts a default while hidden must post the same value the server would use today if the user never touched it. A non-default value is always visible as a chip that reopens the advanced block. Hiding a field is a presentation change. Dropping it from the payload is out of scope.

Shop language on the screen. Statutory language on the print, the export, and the help line.

One filled button per screen. GD-32 siblings are outline buttons.

Confirm only: void, sales RCM, credit override, a change to saved GST setup, and an ambiguous bank match.

---

## 4. Sequence

Work in this order. Later waves can start design while an earlier wave is in review. Do not start Wave C on production editors before the session in Wave B.

| Wave | When | Rows | Why this order |
|---|---|---|---|
| 0. Baseline | Before any editor visual change | Measurement only | HEART T4, T5, T7, T10 have no real-backend numbers |
| A. Safe defaults and copy | Now. Does not hide a control | CL-01a, CL-02a, CL-03a, CL-15, CL-16, CL-20 | Removes decisions while the control is still visible, so GD-33 is not triggered |
| B. Session stimulus | Before GD-33 sessions | Prototype of CL-01b, CL-02b, CL-04, CL-05 | The three screens the pilot staff should react to |
| C. Editor disclosure | After sessions, if staff can complete a plain bill on the prototype | CL-01b, CL-02b, CL-03b, CL-04 | The production hide |
| D. Document actions | Parallel with A. Does not hide editor fields | CL-05, CL-06, CL-07 | Highest recall and choice cuts outside the editors |
| E. Purchase absorption | After CL-07 | CL-08, CL-09 | Highest single job score (4.5) |
| F. Monthly and admin | After D | CL-10, CL-11, CL-12, CL-13 | Lower frequency, high blast radius or high navigation |
| G. Counter and errors | Parallel with A | CL-14, CL-15 already in A | POS focus is independent of GST disclosure |
| H. Needs a decision or is context | After F | CL-17, CL-18, CL-19 | CL-17 posts money. CL-18 and CL-19 are new surfaces |

Effort letters: **S** under a week, **M** one to two weeks, **L** a milestone. One engineer familiar with the editors. These are planning estimates.

---

## 5. Wave 0 — baselines

**Output:** `docs/ux/task_baselines.csv` with one row per task below, captured on a real backend with demo or pilot-like data, desktop and 393px.

| Task id | Task | Record |
|---|---|---|
| T4 | B2B invoice, 3 lines, customer already exists, items already exist | seconds, clicks, header fields touched, whether type/price/godown were changed |
| T4b | Same bill for a walk-in with no GSTIN | same |
| T5 | Record a receipt and allocate | seconds, clicks, whether oldest-preview was used |
| T7 | Purchase bill, manual, 3 lines, supplier and items exist | seconds, clicks, fields typed that matched the item master |
| T9 | Credit note against an existing invoice | clicks, screens |
| T10 | From “month is ready” to GSTR-1 export plus the 3B worksheet open | screens, transitions |
| T2 | POS cash, one scanned item | already guarded in mock mode; repeat on the real shell if a device is available |

Also write the current header decision list for a plain bill (the four invoice types, price mode, godown) so Wave A has a before-count from the same script, not from this document’s estimates.

**Exit:** the csv exists and is cited in the PR that changes an editor. No target number is set until the baseline is in.

---

## 6. Action specifications

### CL-01 — Infer the invoice type

**Priority:** P0. **Effort:** M. **Split:** CL-01a (Wave A), CL-01b (Wave C, after sessions).

**Problem.** A regular taxpayer sees GST, Tax, Retail, and Non-GST on every bill (`NewInvoicePage.tsx` invoice type select). `chooseInvoiceDefaults` already picks `GST` or `NON_GST` from the company and from recent walk-in bills. It does not look at the customer’s GSTIN. The select stays on screen, so the user re-decides a value the system just set. Tax and Retail are still manual choices inside the regular-registration branch.

**User impact.** Every sales invoice. A wrong type is a compliance mistake.

**Root cause.** The legal enum is a visible choice even after a default was applied. The default ignores the party that was just selected.

**Solution.**

1. **CL-01a (show the control).** Extend `chooseInvoiceDefaults` (or a sibling used at party-select time) so that, when the user has not touched the type (`invoiceTypeTouched` is already in the page):
   - Company unregistered or composition: keep today’s company rule.
   - Regular registration and the selected customer has a GSTIN: `GST`.
   - Regular registration and the selected customer has no GSTIN: `RETAIL` if that value is what the company uses for B2C, otherwise the company default. Confirm the exact B2C enum with the current `preferredInvoiceType` / billing copy before coding. Do not invent a fifth type.
   - `NON_GST` only when the company default is non-GST, or the user has overridden.
   - Changing the customer may update the type only while `invoiceTypeTouched` is false.
   - The select remains visible in Wave A. Helper text states the reason in one line: “GST bill because this customer has a GSTIN.”
2. **CL-01b (after GD-33).** Replace the select on first paint with a chip that uses shop language (“Bill to a GSTIN customer” / “Bill to a walk-in”). “Change bill type” reopens the existing select. The stored enum is unchanged.

**Do not.** Change how the backend validates `invoiceType`. Do not retitle the printed invoice away from the legal name. The print keeps GST Invoice / Tax Invoice / Retail Invoice. The screen chip is the shop sentence. The help line keeps the legal name.

**Files.** `web/src/pages/sales/invoiceDefaults.ts`, `invoiceDefaults.test.ts`, `NewInvoicePage.tsx`, `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`.

**Acceptance.**

- A GSTIN customer on a regular company gets `GST` without a click, until the user opens the select and changes it.
- A later edit of the customer does not overwrite a type the user set.
- An edit of an existing invoice loads the saved type and does not re-infer.
- Chip or helper is present in English and Hindi.
- Payload `invoiceType` matches what the select would have posted.

**Test.** Unit tests on the default function for: GSTIN party, no-GSTIN party, untouched vs touched, edit mode, fewer than three historical bills, composition company. Component test that the select value follows the function.

---

### CL-02 — Price mode as a company default

**Priority:** P0. **Effort:** S. **Split:** CL-02a Wave A, CL-02b Wave C.

**Problem.** Tax exclusive vs inclusive is a per-bill select. `chooseInvoiceDefaults` already returns `companyPriceMode`. The select still asks.

**Solution.**

1. **CL-02a.** Keep the select. Stop treating a fresh bill as undecided: the value on open is the company mode (already largely true). Add one caption: “Price includes GST” or “Price before GST”, driven by the value.
2. **CL-02b.** Remove the select from the first row. The caption becomes a chip. Override lives under More tax options. Completed bills stay locked the way they are today (`canAmendMoney`).

**Do not.** Change inclusive/exclusive maths in the line calculator.

**Files.** `NewInvoicePage.tsx`, the purchase editor if it has the same select (`NewPurchasePage.tsx`), `en.ts`, `hi.ts`.

**Acceptance.** A new bill opens on the company mode. Changing the chip or the select changes line maths. A completed bill does not become editable.

**Test.** Existing invoice maths tests stay green. One test that the initial state equals `companyPriceMode`.

---

### CL-03 — Godown only when there is more than one

**Priority:** P0. **Effort:** S. **Split:** CL-03a Wave A (label), CL-03b Wave C (hide).

**Problem.** The warehouse select is unconditional. `en.ts` uses `nav.warehouses` = “Godowns” and `billing.godown` = “Warehouse” for the same object.

**Solution.**

1. **CL-03a.** One word on the bill, the purchase, the transfer, and the nav: **Godown**. Hindi equivalent agreed with the founder (GD-23). Default selection stays `isDefault`.
2. **CL-03b.** If the active godown list has length 1, do not render a select. Show the name as text. Post that id. If length is 2 or more, show the select, defaulted. A non-default godown on an edited bill is always shown, even if the company would otherwise hide the control, so the user can see stock is not coming from the default location.

**Do not.** Change per-godown stock checks. The posted `warehouseId` is the same id as today.

**Files.** `NewInvoicePage.tsx`, `NewPurchasePage.tsx`, transfer form, `en.ts`, `hi.ts`. Grep `billing.godown` and `nav.warehouses` before editing so list pages and PDFs stay consistent. PDF/print may keep a fuller phrase if the founder wants “Godown” only on screen. Record that choice in the PR.

**Acceptance.**

- One active godown: no select, posted id is that godown.
- Two godowns: select visible, default selected.
- Edit of a bill whose godown is not the default: the godown is visible.
- Stock block copy still names the quantity in that godown.

**Test.** Component test with one warehouse and with two. Hindi key parity test (`fullParity` or the existing i18n ratchet).

---

### CL-04 — Non-default statutory chip

**Priority:** P0. **Effort:** S. **Wave:** B prototype, C production. This is the disclosure pattern GD-33 is about, so production waits. The chip can be added while the block is still collapsed, which does not hide anything new.

**Problem.** Supply type, extra GSTIN, cost centre, e-commerce GSTIN, and sales RCM are inside `showAdvancedTax`. A collapsed block hides a non-default as well as the controls. The user can Complete a bill that is SEZ or reverse charge without seeing that fact on the header.

**Solution.** Under the “More tax options” link, render a chip row only when something is off the default:

- Supply type other than B2B.
- A non-primary company GSTIN selected.
- A cost centre selected.
- E-commerce GSTIN non-empty.
- Sales RCM on.

Each chip’s click opens the block (`setShowAdvancedTax(true)`). RCM still requires the existing confirm checkbox before Complete (`confirmSalesRcm`). Do not remove that checkbox.

**Defaults to treat as “no chip”:** supply B2B, primary GSTIN, empty cost centre, empty e-commerce GSTIN, RCM off.

**Files.** `NewInvoicePage.tsx`. Mirror on `NewPurchasePage.tsx` for the purchase equivalents (RCM, ITC is CL-09, place of supply is CL-07).

**Acceptance.**

- A plain bill shows no chip.
- Turning on RCM shows a chip and Complete stays disabled until the confirm checkbox is ticked.
- SEZ with payment shows a chip whose text is shop language (“SEZ, GST charged”) with the code available on the help line, not as the only label.
- English and Hindi.

**Test.** Component tests for the five non-default cases and the all-default case.

---

### CL-05 — One primary action on the posted invoice

**Priority:** P0. **Effort:** M. **Wave:** D. Independent of GD-33.

**Problem.** `InvoiceDetailPage.tsx` is a static-scan score 5 (82 choices, about 55 buttons, 5 dialogs). Print, share, collect, edit, void, and return are peers.

**Solution.** Rank by document state. Do not delete an action. Move the long tail into one “More” menu on the page.

| State | Filled button | Outline | Menu / destructive |
|---|---|---|---|
| Draft | Complete (existing path) | Save | Discard draft, with the existing confirm |
| Posted, balance remaining, user can take payment | Record payment | Share / print | Edit if allowed, Return goods (CL-06), Void |
| Posted, settled | Share / print | Record payment hidden | Return goods, Void |
| User lacks payment permission | Share / print | — | Payment actions omitted, not disabled-without-reason |

Void keeps its confirm. The page keeps a status chip and the balance near the button so the choice is recognition.

**Files.** `InvoiceDetailPage.tsx`, its test, `en.ts`, `hi.ts`.

**Acceptance.**

- A clerk without payment permission does not see Record payment.
- Void and credit note are reachable by keyboard and have accessible names.
- No action that exists today for that permission and status disappears. It may move into the menu.
- axe serious/critical clean on a posted invoice fixture.

**Test.** Render tests for the three states and a user without `canCreatePayments`. One Playwright step: open a posted invoice with a balance, the filled button is the payment action.

---

### CL-06 — Return goods from the invoice

**Priority:** P0. **Effort:** M. **Wave:** D.

**Problem.** Credit notes are under Sales → More (`menu.ts` `sales-more`). The bookkeeper has to remember the path and re-enter rates that are on the invoice. Estimate: about 6 steps today, about 4 after. This estimate is not a baseline.

**Solution.** “Return goods” on the invoice (CL-05 menu, promoted to outline if returns are frequent for that company — start in the menu, promote only if the session says the menu hid it). The action opens the existing credit-note editor (`NewCreditNotePage.tsx` or the note editor already used) with:

- original invoice id,
- lines copied: item, original qty as the max, rate, tax, godown, serials that were on the line,
- quantity editable, defaulting to the full remaining returnable qty or to blank. **Default the quantity to blank** so a careless Complete cannot return the whole bill. Show “full return” as one explicit control.

The list at `/sales/credit-notes` stays for search. The nav item stays until D-UX-4 is reopened.

**Do not.** Change credit-note posting, stock reversal, or tax reversal rules.

**Files.** `InvoiceDetailPage.tsx`, credit-note editor, a prefill helper with unit tests.

**Acceptance.**

- Partial quantity posts a partial credit with the original rate and tax treatment.
- Quantity above the remaining returnable qty is blocked with a sentence that names the remaining qty.
- Serial-tracked lines require the serials, as they do today.
- Draft of the credit note survives a validation error.
- The sales-more list still opens and still creates a credit note for users who start there.

**Test.** Prefill unit test. One component test that the editor receives the invoice id and lines. Existing credit-note posting tests stay green.

---

### CL-07 — Place of supply only on conflict

**Priority:** P0. **Effort:** M. **Wave:** D, then used by Wave E.

**Problem.** Purchases call `placeOfSupplyKnown` and block Complete with `billing.placeOfSupplyRequiredSupplier` when supplier state and GSTIN are both insufficient. Sales have a similar requirement when the company does not assume local state for a blank party. The rule is correct. The prompt fires before the GSTIN state code is used as the answer.

**Solution.**

1. Derive a candidate state from the GSTIN state code when the GSTIN is valid.
2. If the address state is empty, use the GSTIN state and do not ask.
3. If the GSTIN is empty and the address state is present, use the address state and do not ask.
4. If both exist and disagree, show both values and block Complete until the user picks one. Copy: “GSTIN says Maharashtra. Address says Gujarat. Which state is this bill for?”
5. If both are empty, focus the state or GSTIN field. Copy: “Add the supplier’s state or GSTIN. GST needs a state for this bill.”
6. Do not clear the draft.

**Do not.** Change the tax engine’s intra-state vs inter-state rule. Change only when the UI asks and which value it sends.

**Files.** Shared helper next to the existing place-of-supply util (grep `placeOfSupplyKnown`), `NewPurchasePage.tsx`, `NewInvoicePage.tsx` if the sales path has the same gap, `en.ts`, `hi.ts`.

**Acceptance.**

- Supplier with a valid GSTIN and a blank state: no prompt, IGST vs CGST/SGST matches today’s result for that state code.
- Conflict: cannot complete until one side is chosen. The chosen state is what is posted.
- Both empty: focus lands on the field. Other lines remain.

**Test.** Table-driven unit tests for the four cases. One component test that conflict renders both states.

---

### CL-08 — Purchase lines filled from the item and the upload

**Priority:** P0. **Effort:** L. **Wave:** E.

**Problem.** Crawl: 28 inputs at first paint on `/purchases/new`, the highest in the app. HSN, GST %, and rate are retyped even when the item master has them. Bill upload exists (`/purchases/bill-upload`) as a side route.

**Solution.**

1. On item select, fill HSN, GST %, unit, and last purchase cost. The row shows the source in caption text (“from item” / “last bill”). The user can edit. An edit drops the “from item” caption.
2. If the filled GST % disagrees with a rate the user typed, highlight the row. Do not auto-overwrite a user-typed rate.
3. Make upload a primary path on the purchase editor (“Upload bill”), not only a menu destination. Extracted lines use the same row caption (“from upload”) and the same highlight when they disagree with the item master.
4. Confidence: a low-confidence extracted rate is shown empty or marked “check this”, never posted as if the user typed it. Follow the existing extraction behaviour (freeze item D14). Do not weaken it.

**Do not.** Post a line the user has not seen. Do not change stock or AP posting.

**Files.** `NewPurchasePage.tsx`, purchase line component, bill upload handoff, `en.ts`, `hi.ts`.

**Acceptance.**

- Selecting an item with a master HSN fills HSN and GST % and posts those values if the user does not edit.
- A user-typed rate is the posted rate.
- Upload mismatch is visible before Complete.
- An unmatched upload line stays editable and cannot complete with a blank item.
- Existing purchase complete tests stay green.

**Test.** Line-fill unit test. Upload fixture with one matched line and one unknown line.

---

### CL-09 — ITC as a chip with a reason

**Priority:** P1. **Effort:** M. **Wave:** E. Depends on a blocked-category list, which is data, not a new tax rule.

**Problem.** `itcEligibility` is `CLAIMABLE | INELIGIBLE | REVERSED`, default `CLAIMABLE`, on every purchase. The default is right. The enum is still a decision the store user should not reinterpret.

**Solution.**

- Default remains `CLAIMABLE`. Chip: “GST you can claim on this bill.”
- If any line’s HSN or item flag is on a blocked list, the chip recommends “GST not claimable” and one sentence names the line. The stored value becomes `INELIGIBLE` only after the user accepts the recommendation or leaves it accepted. **Do not silently flip a previously saved `CLAIMABLE` bill on edit** without showing the chip.
- Override to Reversed stays in the advanced block.
- If no blocked list is shipped yet, ship the chip for the default and the override, and leave the recommendation as a follow-up. Do not fake a block list.

**NEEDS-FOUNDER-DECISION** if the blocked list would change ITC on bills the user never looks at. The safe version is: recommend, show the chip, post what the chip says at save time because the user can see it.

**Files.** `NewPurchasePage.tsx`, a small eligibility helper, `en.ts`, `hi.ts`.

**Acceptance.** Ordinary lines: chip says claimable, posted value `CLAIMABLE`, no extra click. User can switch. Saved eligibility equals the chip at save. Edit of an old bill shows the saved value, not a new inference, until the user accepts a recommendation.

**Test.** Helper tests for default, recommended ineligible, and “do not override a saved value until accept”.

---

### CL-10 — Period close checklist

**Priority:** P1. **Effort:** L. **Wave:** F.

**Problem.** GSTR close scores 4.3 from navigation and terminology, not from one giant form. The user opens separate report routes. Extended forms (GSTR-2B, 4, 6, 7, 8, 9) are behind `ENABLE_GSTR_EXTENDED`. Pilot filing is a worksheet. Live GSP submit is off.

**Solution.** One page, “Close the month”, linked from Reports and from the owner morning list (CL-19) when the month has turned.

Rows, each opening the existing report in place or by a deep link that returns:

| Row | Who sees it | Existing surface |
|---|---|---|
| Outward supplies | Regular taxpayer | GSTR-1 worksheet |
| Tax payable | Regular | GSTR-3B worksheet |
| Purchases to match | When `ENABLE_GSTR_EXTENDED` and 2B is available | `Gstr2bPage.tsx` |
| Composition statement | Composition registration | CMP-08 path if present |
| Missing documents | Everyone who can close | existing missing-documents report |
| Books health | Accountant / owner | existing books-health report |

A single line at the top: these worksheets are for the CA. Filing on the portal is a separate step. Do not imply the product filed anything.

Registration type hides rows that do not apply. The form code (GSTR-1, GSTR-3B) is secondary text. The row title is shop language (“Sales for the month”, “Tax to pay”).

Export pack: the same downloads as today, grouped on this page. No new file format.

**Do not.** Enable live filing. Do not merge the worksheets into one incorrect total.

**Files.** New page under `web/src/pages/reports/`, route in `App.tsx`, nav entry under reports (a new child, not a sidebar restructure), `en.ts`, `hi.ts`.

**Acceptance.**

- Regular taxpayer sees outward supplies, tax payable, missing documents, books health.
- 2B row appears only when the flag is on.
- Composition taxpayer does not get GSTR-1 as the primary row.
- Each row reaches the existing report. Export bytes match the report’s own export.
- The worksheet disclaimer is visible without opening help.

**Test.** Route test for the two registration types and the flag off/on. No snapshot of statutory figures beyond what those report tests already lock.

---

### CL-11 — Role templates on Users

**Priority:** P1. **Effort:** M. **Wave:** F.

**Problem.** `/settings/users` is 30 fields and 50 choices. The owner maps eight capabilities per person. The ACL is the screen.

**Solution.** Four templates that call the existing permission helpers. No new security model.

| Template | Intent | Must not include |
|---|---|---|
| Cashier | POS and sales create | GST settings, user admin, financial reports beyond the counter |
| Store | Purchases and stock | User admin, GST settings |
| Bookkeeper | Purchases, receipts, reports, GST worksheets | User admin |
| Owner | Current owner set | — |

“Custom” opens today’s grid. The next new user defaults to the last template chosen on this company (local or company preference — prefer server-saved if a field already exists; otherwise local is acceptable and must be labelled as “on this browser”).

Map each template onto the current checkbox set in a table in the PR description so a reviewer can diff permissions.

**Do not.** Add a permission bit. Do not change `canCreateSales` and the other helpers.

**Files.** `UsersSettingsPage.tsx`, a `roleTemplates.ts` with tests, `en.ts`, `hi.ts`.

**Acceptance.**

- Choosing Cashier produces the checkbox set in the mapping table, and that user cannot open GST settings or user admin.
- Custom can still reproduce a combination that exists today.
- Existing users are not rewritten when the page loads.

**Test.** Unit test: each template → permission flags. Component test: switching template updates the grid. One test that load does not PATCH existing users.

---

### CL-12 — GST settings lock after first save

**Priority:** P1. **Effort:** S. **Wave:** F.

**Problem.** `/settings/gst` has 26 fields, 54 choices, 21 inputs at first paint. A casual edit changes every future bill.

**Solution.** After GSTIN, registration type, and state are saved and valid, the page shows a summary (GSTIN, type, state, price mode if it lives here). “Change tax setup” opens the form. The first change of registration type or GSTIN requires a confirm that says future bills follow the new setup and bills already issued do not change.

**Do not.** Mutate posted invoices. Do not add a new GST rule.

**Files.** `GstSettingsPage.tsx`, `en.ts`, `hi.ts`.

**Acceptance.** Summary is the first view when setup is complete. Confirm names the effect. In-progress invoice drafts keep the type they already resolved (CL-01) until the user reopens them. axe clean.

**Test.** Component: complete setup renders summary. Confirm is required for registration-type change. Cancel returns to the summary with the old values.

---

### CL-13 — Products page, search first

**Priority:** P1. **Effort:** M. **Wave:** F.

**Problem.** `/inventory/products` has 122 choices and about 58 buttons. Item create itself is already short (A2-7) and scores about 1.9 on the default path. The page around it is the dense object.

**Solution.** Primary: the search box and Add item. Import, bulk edit, and attribute tools move into one menu. Do not remove a column the billing line needs from the item record. Opening stock, lots, and serials stay behind the existing button in `ItemFormDialog.tsx`.

**Files.** `ProductsPage.tsx`, `en.ts`, `hi.ts`.

**Acceptance.** Add item still opens the short form. A keyboard user can reach import. No required item field is dropped from the API payload of the dialog.

**Test.** Existing item-dialog tests stay green. One render test that the first heading-level actions are search and add.

---

### CL-14 — POS focus contract

**Priority:** P1. **Effort:** M. **Wave:** G.

**Problem.** The journey doc records that a focus effect can pull the caret from quantity back to the scan field while the clerk is typing. That is the main extraneous load on a screen that otherwise scores 1.5–2.7.

**Solution.**

- After a successful scan or an explicit “back to scan” shortcut, focus the search field.
- While the caret is in quantity, discount, or batch, keystrokes stay there until Enter or Escape.
- Escape returns to search and does not change the line.
- Do not add a lot picker (D-UX-6).

**Do not.** Change price, tax, or tender posting.

**Files.** `PosPage.tsx` and the focus helper if one exists. `pos-keyboard-checkout` e2e must stay within its budget.

**Acceptance.** A test types a multi-digit quantity without the search field receiving those digits. A scan wedge still lands in search when the last committed field was search. Hold (F8) and tender keys still work when focus is on search.

**Test.** Component or e2e as above. The existing keyboard checkout spec stays green.

---

### CL-15 — Plain language when Complete is blocked

**Priority:** P1. **Effort:** S. **Wave:** A (copy only).

**Problem.** Credit limit, missing serial, place of supply, and RCM use system phrases. A2-8 covers only the empty party/item case.

**Solution.** For each blocker, one sentence with problem, cause, and the next action, then focus the control. Keep the draft. HTTP failures stay on the A3-1 path and keep the support id. Do not mix a validation rule into the HTTP mapper.

| Blocker | Sentence shape |
|---|---|
| No party or no line | “Choose a customer, then add an item.” Focus the empty one. |
| Credit limit | “{name} would reach {exposure} against a limit of {limit}. Ask the owner, or reduce the bill.” |
| Missing serial | “Enter the serial for {product}.” Focus that cell. |
| Place of supply | Use CL-07 copy. |
| RCM not confirmed | “You marked reverse charge. Confirm it, or turn reverse charge off.” Focus the confirm checkbox. |

**Files.** `NewInvoicePage.tsx`, `NewPurchasePage.tsx`, `DocumentEditorShell.tsx` if the disabled reason lives there, `en.ts`, `hi.ts`.

**Acceptance.** Each blocker focuses a field. Lines already entered are still on screen. Founder has read the Hindi. Vitest covers each sentence key.

---

### CL-16 — Money in / money out

**Priority:** P1. **Effort:** S. **Wave:** A.

**Problem.** Receipts, supplier payments, payment links, and collections are four names for cash moving. The owner says “payment received”. The voucher correctly says Receipt.

**Solution.** Navigation labels:

- `nav.receipts` → “Money in” (page title can stay “Receipt”).
- `nav.supplierPayments` → “Money out” (page title can stay “Payment”).
- Collections stays a chase-dues label (`nav.collections`), not a third word for the same voucher.

Routes do not change. Glossary test that covers Paid / Completed / Returned should also cover this pair so the words do not drift.

**Files.** `en.ts`, `hi.ts`, glossary golden test if present (`glossary-status`).

**Acceptance.** Both languages. Sidebar shows the new labels. The receipt document heading still says Receipt. No route change. Founder has read the Hindi.

---

### CL-17 — Bank match interrupts only when ambiguous

**Priority:** P2. **Effort:** M. **Wave:** H. **`NEEDS-FOUNDER-DECISION`.**

**Problem.** `BankReconPage.tsx` (operational match) asks the user to confirm suggestions, including unique ones. The subtitle also explains that this is not the GL bank recon (`AccountingBankReconPage.tsx`). Two products, one worry.

**Solution, only if the founder agrees:**

- A candidate that is unique on amount and inside the existing date tolerance is applied with the same post the user would confirm today.
- Two or more candidates stay in a queue. The user decides.
- Page title: “Match bank lines.” The GL screen keeps its own name. Help can say they are different. The subtitle does not teach both jobs at once.
- No undo of a posted match (D-UX-3).

**Do not build** until the decision is written into `docs/ux/founder_decisions.md`.

**Acceptance if built.** Two receipts with the same amount stay unapplied. A single exact candidate posts and appears in the matched list. No journal side effect beyond today’s match action.

---

### CL-18 — Field order context strip

**Priority:** P2. **Effort:** M. **Wave:** H.

**Problem.** The order booker (P3) scores 3.5 because price, credit, and stock live on other screens, often on a phone with a weak signal.

**Solution.** On the sales order editor, a strip:

- they owe (outstanding),
- credit left,
- stock in the selected godown for the highlighted line,
- offline outbox count, or “last synced at {time}” when the figures are cached.

The strip must not cover the save button at 393px.

**Do not.** Invent stock or credit when offline. Label the sync time.

**Files.** Sales order editor (`SalesOrderEditorPage.tsx` / `NewSalesOrderPage.tsx`), `en.ts`, `hi.ts`.

**Acceptance.** Strip visible at 393px. Stale cache shows the time. A missing figure says it is unknown rather than zero, if the API distinguishes those.

---

### CL-19 — Owner morning list, five rows

**Priority:** P2. **Effort:** M. **Wave:** H.

**Problem.** The proprietor’s job (personas doc, J10) is “what needs me in five minutes”. Dashboard, attention, collections, and low stock are separate destinations.

**Solution.** At most five rows, each one action, built from queries that already exist:

1. Dues to chase (collections / outstanding).
2. Bills held for credit override.
3. Low stock (keep the existing `<=` rule, D-UX-1).
4. Setup still blocking the first real bill.
5. Period-close row when the month has rolled and the checklist (CL-10) is not done.

A quiet day says nothing is waiting and offers New bill and POS. Empty company shows setup only. This is not a forecast. Do not add a prediction model. Collections copy stays in owner language (A3-5).

**Files.** Dashboard or Attention, whichever already aggregates these. Prefer extending Attention over a third list.

**Acceptance.** Each row deep-links to the existing screen. No row appears when its count is zero. Quiet state has the two links.

---

### CL-20 — Series number as a caption

**Priority:** P3. **Effort:** S. **Wave:** A.

**Problem.** Prefix and next number are disabled inputs (`billing.invoicePrefix`, `billing.invoiceNumber`). They look like questions. The scan counts them as fields.

**Solution.** Replace the two controls with one caption: “Next bill {prefix}-{padded number}.” Series editing stays in settings. Edit mode shows the fixed number as text (`billing.invoiceNumberFixed` already exists).

**Do not.** Change number allocation.

**Files.** `NewInvoicePage.tsx`, purchase equivalent if it shows a read-only number the same way, `en.ts`, `hi.ts`.

**Acceptance.** The posted number is unchanged. The caption matches the previous helper text (`prefix` + padding). Edit mode does not offer an editable number.

**Test.** Existing series tests stay green. One render test that the text contains the padded number.

---

## 7. Session protocol (Wave B, unblocks Wave C)

GD-33 says production editors do not hide fields until pilot staff sessions exist. This is the session.

**Stimulus, three screens, prototype or build-behind-a-flag. Not the production default.**

1. Plain bill: customer, date, lines, total. No type select, no price-mode select, no godown select (one-godown company). Caption for the next number. Chip absent.
2. Same bill after the user opens “More” and sets SEZ or RCM: chips visible, RCM confirm still required.
3. Posted invoice: filled button is Record payment or Share, other actions in a menu.

**Participants.** Staff of the three pilot companies (GD-26), plus one bookkeeper if the pilot has one. The proprietor alone is not enough. The counter clerk and the person who enters purchase bills must each try screen 1.

**Tasks.** T4, T4b, and one SEZ or RCM bill if anyone in the room has issued one. Otherwise use a scripted SEZ example and ask “would you have known this bill was different?”

**Pass for Wave C.** At least four of five participants complete the plain bill without asking where the invoice type went, and the bookkeeper can find the chip on the SEZ example. If they cannot, keep Wave A (defaults visible) and do not hide the selects.

**Record.** One page in `docs/ux/` with who (role, not a private name if they prefer), task, finished or not, and the words they used for godown, receipt, and invoice type. That page feeds CL-16 and CL-03 if the words differ.

---

## 8. Copy and terminology checklist

Ship with any wave that touches strings. Both `en.ts` and `hi.ts`. Founder reads Hindi (GD-23).

| Current | Screen | Print / export / help |
|---|---|---|
| Godowns / Warehouse | Godown | Godown, unless a statutory format requires Warehouse |
| GST / Tax / Retail invoice | Bill to a GSTIN customer / Bill to a walk-in | Legal title unchanged |
| Tax exclusive / inclusive | Price before GST / Price includes GST | Can stay as the mode name in settings |
| Place of supply | Which state is this bill for? | “Place of supply” on the return export |
| Sales RCM | Customer pays the GST, not you | “Reverse charge” on the invoice print |
| SEZWP, SEZWOP, EXPWP, EXPWOP, DEXP | SEZ, GST charged / SEZ, no GST / Export, GST charged / Export, no GST / Deemed export | Codes on the help line and the JSON |
| Receipts (nav) | Money in | Voucher title Receipt |
| Supplier payments (nav) | Money out | Voucher title Payment |
| ITC eligibility | GST you can claim on this bill | `itcEligibility` enum unchanged |
| Bank recon subtitle | Match bank lines | GL screen keeps its name |

Do not regress Collections (A3-5) or the Paid / Completed / Returned glossary.

---

## 9. Error and interruption rules

**Interrupt (keep):** void, sales RCM confirm, credit-limit override, GST setup change after first save (CL-12), ambiguous bank match, allocate-to-oldest confirm (D-UX-7).

**Do not add a confirm for:** a unique bank match if CL-17 is approved, a plain Complete, opening More tax options, or a second confirm after the user has already pressed “Allocate to oldest”.

**On every validation block:** draft remains, focus moves, the sentence names the fix (CL-15).

**Partial failure:** “The item exists. Opening stock did not post. Retry stock only.” Do not ask the user to recreate the item. Same shape anywhere a parent record is saved and a child post fails.

---

## 10. Persona checks

A row is not done if it only works for the bookkeeper.

| Persona | Rows that must be tried as that person | Pass |
|---|---|---|
| P1 Proprietor | CL-19, CL-12, CL-05 | Five-minute list, or a summary of tax setup, without the full form |
| P2 Counter clerk | CL-14, and they never see CL-01’s four types on POS | Quantity edit keeps focus. POS has no invoice-type menu |
| P3 Field booker | CL-18 | Strip at 393px, stale data labelled |
| P4 Godown | CL-08 | Scan or item select fills HSN. Batch and expiry still available when the item needs them |
| P5 Bookkeeper | CL-04, CL-06, CL-07, CL-09, CL-10 | Can see that a bill is not a plain B2B bill. Can start a return from the invoice |
| P6 CA | CL-10 | Export still has GSTR-1 and 3B codes. Disclaimer says worksheet |
| New user | CL-01, CL-20, setup path | First plain bill does not require the type menu once Wave C has passed |
| Admin | CL-11 | Cashier template cannot open user admin |

One invoice screen serves all of them: first paint is the plain bill, the chip is how the expert re-enters statutory options.

---

## 11. Test and release gates

Every PR in this plan:

1. States which CL id it implements.
2. Does not change posting, tax maths, stock, or permission helpers unless the id is CL-17 and the founder line is already in `founder_decisions.md`.
3. Adds or updates a Vitest. Adds a Playwright step when the row names one.
4. `en.ts` and `hi.ts` together. Parity test green.
5. axe: no new serious or critical finding on the touched route.
6. 393px: the primary button is visible and at least 44px. Hindi does not cover it.
7. For editor rows: a non-default statutory value is visible without opening devtools.
8. Cites the Wave 0 baseline row if it claims a reduction. Otherwise the PR says “estimate only”.

**Definition of done for the programme:**

- Wave A shipped.
- Wave B session recorded, and Wave C either shipped or explicitly stopped with the session notes.
- CL-05, CL-06, CL-07 shipped.
- CL-08 shipped or split with the upload half still open and the item-fill half shipped.
- CL-10, CL-11, CL-12 shipped.
- T4 header-fields-touched is lower than the Wave 0 csv on the same script.
- No open P0 row without a Deferred reason in this file’s progress log.

---

## 12. Risks

| Risk | What to do |
|---|---|
| Hiding invoice type causes a silent NON_GST or RETAIL bill | Wave A keeps the select. Wave C requires the session pass. The chip must show whenever the type is not the company’s plain default |
| Customer GSTIN inference fights `chooseInvoiceDefaults` history rule | Party-select inference runs only while `invoiceTypeTouched` is false, and it overrides the history guess at the moment a real customer is chosen. Document the order in the unit test name |
| Purchase upload posts a bad rate | Low confidence stays blank or “check this”. Never silent |
| ITC recommendation flips old bills | Edit shows the saved value until the user accepts |
| Menu labels “Money in” confuse the bookkeeper | Page title stays Receipt. Session notes can revert the nav word without a route change |
| Period close becomes a second GSTR engine | Rows only link or embed existing reports. No new totals |
| Role templates grant too much | The PR includes the permission mapping table. Cashier test asserts settings and user admin are closed |
| GD-33 delay stalls everything | Wave A, D, G, and CL-20 do not wait |

---

## 13. Out of scope

- Sidebar information architecture (D-UX-4). Revisit only after CL-05 and CL-06 have been live.
- Remapping shortcuts to Tally keys (D-UX-5).
- Live GSP filing, live NIC e-invoice, and e-way submit.
- A new prediction or dunning model.
- Undo of a posted bank match.
- Changing the tax, stock, credit-hold, or permission engines.
- Hiding Save draft or Complete and start another (GD-32).
- Auto-picking a POS lot (D-UX-6).
- Applying oldest allocation without the confirm (D-UX-7).

---

## 14. Progress log

| Date | Id | Result |
|---|---|---|
| 2026-10-04 | — | Plan written. No row started. |

Update this table when a row ships, is deferred, or is stopped by the Wave B session.

---

## 15. Suggested first PRs

Small enough to review. Each one is a single CL slice.

1. **CL-20 + CL-03a + CL-16.** Caption, godown wording, money-in labels. Copy and presentation. No inference.
2. **CL-15.** Blocked-Complete sentences, both languages.
3. **CL-01a + CL-02a.** Inference and price-mode caption while the selects stay visible. Unit tests on `invoiceDefaults`.
4. **CL-05.** Invoice detail button rank. Feature-flag it if the page is too hot to ship in one step.
5. **CL-14.** POS focus, with the keyboard checkout spec still green.
6. **Prototype flag for Wave B** covering CL-01b, CL-02b, CL-03b, CL-04, behind a dev flag, not the pilot default, so the session has something to touch.

PR 6 does not become the production default until the session pass in section 7 is written down.
