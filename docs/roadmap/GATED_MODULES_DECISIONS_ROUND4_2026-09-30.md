# Round 4: answers to the 33 build questions

Date 2026-09-30. These are **proposed answers, adopted as working defaults** so work is not blocked. Anything marked **Founder** needs a name, a date or a credential only you can give. Anything marked **Confirm** is a choice you can overrule; say so and the plan changes. None of these reopens the decisions already recorded (lazy chart, GSTR-6/7/8 hidden, AI consent off, three parallel pilots, no change to posting, tax, stock or permissions).

Facts I checked in the code before answering are marked **(checked)**.

> **Round 5 override.** You then answered these by choosing options (`GROWTH_OS_DECISIONS_2026-09-30.md`, GD-22 to GD-37). Where a choice differs from the proposal below (no commit now, both slices in parallel, rewrite hook logic, keep all three invoice buttons, prototype waits, owner counts as booker, Customer 360 all five at once, lanes the same week), **your choice wins** and the plan follows it.

## Before any more code

| # | Answer | Notes |
|---|---|---|
| 1 | **Superseded by GD-22. Do not commit.** Keep working uncommitted. Copy touched files aside before a risky edit. The slice list in the old answer is not a commit plan. | |
| 2 | **Superseded by GD-30. Both slices in parallel.** Gated screens and the invoice/purchase work run together. One slice at a time may edit `NewInvoicePage`, `NewPurchasePage`, `PosPage`, `DocumentEditorShell` and `DraftLineTable`. Disclosure (A2-5, A2-6) still waits for sessions (GD-33). | |
| 3 | **Section 12 of `docs/UX_ACTION_ITEMS.md` is current.** Section 11 is marked superseded so finished tickets are not rebuilt. The plan's section 0 is the per-ticket source. | Done in this update |
| 4 | **Superseded by GD-31. Rewrite hook logic where needed.** Each rewrite needs a test that fails before and passes after. Existing POS and invoice tests stay green. No change to posting, tax, stock or permissions. | |
| 5 | **Yes.** UX Audit Traders is up on the dev stack (checked today). A browser check (axe at desktop and 393px, plus a walk of the changed screen) is **required for any ticket that changes a screen**, after a web rebuild. Tickets with no UI change are exempt. Command: rebuild web, then `ux-surface-crawl.spec.ts` with `UX_ONLY_PATHS` and `UX_EMAIL/UX_PASSWORD` from `.ux-audit-credentials.local`. | Confirm |

## Scope of the broad UX items

| # | Answer | Notes |
|---|---|---|
| 6 | **Almost done already.** The real-backend crawl shows only **9 of 141 pages** without an h1 (the old "68" came from mock mode). Six are the "not on yet" and insights landing pages, now fixed. Remaining: `/invite`, `/help`, `/settings/help`. Fix those three in this pass and re-crawl; no all-routes sweep. **(checked)** | |
| 7 | **Only the screens in the current slice**, plus the guard test. The slice list you gave is right: billing, Telegram, bank reconciliation, projects, job cards, insurance, the Tally "Ignore error rows" dialog. A global sweep of the rest is a separate later slice. | Confirm |
| 8 | **No bulk migration of 51 tables.** Build one `ScrollRegion` wrapper and migrate only tables that actually overflow at 393px. The crawl currently finds 0 serious scroll-region failures, so the rest migrate when touched. | |
| 9 | **Treat the theme change as done** (icon buttons and checkboxes 44px below `sm`). Re-measure with the crawl after S1 lands. Go page by page only where the measured count stays high (invoice editors, POS, leads). Mark A2-4 "Partial, re-measure". | |
| 10 | **Yes, include lead source filters** (S, same enum helper). | |
| 11 | **Superseded by GD-23. The founder reads the Hindi.** Top tasks: log a complaint, open a ticket, add and assign a lead, add a contract, record a receipt, create an invoice, read a GST worksheet, run a pay run. A ticket with new Hindi copy is not Done until that read. Key parity stays automatic. | |

## Tickets whose wording can be built two ways

| # | Answer | Notes |
|---|---|---|
| 12 | **Copy only. No "Create chart of accounts" button.** The button would change behaviour and contradicts the lazy-creation decision. Page copy says the chart appears on the first posting; totals that cannot be trusted show a dash. GM-03 is edited to remove the button. | |
| 13 | **Heading is just "GSTR-6" (and 7, 8).** The body keeps the plain "Bizboard does not prepare this return yet" sentence. | Confirm |
| 14 | **Leave both routes.** `/ca-needs?view=client` is a different view of the same page. The ledger row (UX-M03) is closed as not a defect. | |
| 15 | **Menu accepted.** The ticket wording is corrected from "dialog" to "menu". | |
| 16 | **The link is enough. Hide the ten session fields until a statement exists.** Upload stays on the Bank statements page, so there is one upload flow. | |
| 17 | **Put a two-line explanation on the page beside the close controls**, before the button is pressed. The confirm dialog keeps its text. Copy only. | |
| 18 | **Dialogs.** Campaigns, first four: **Name, Type, Start date, Budget**; under "More": Status, Parent campaign, Target revenue, End date, Expected outcome. Contracts, first five: **Customer, Type, Start date, End date, Value**; under "More": Reminder days (default 30), Notes, Products covered (the line table). Referrals: keep inline (three fields). **Projects and job cards: keep inline (two fields each)**; the ticket is amended. | Confirm |
| 19 | **Yes. "Add contract"** joins the verb labels (GM-52). | |
| 20 | **Label only:** "Value is for the renewal list. It does not create an invoice." No link to a recurring invoice. Holistic H5.4 default; no business-logic change. | Confirm |
| 21 | **Disable the confirm button inside the Release dialog until serials are entered** for serial-tracked components, with a reason that names the component. The row button stays enabled, because that is where serials are typed. **Not yet verified:** the BOM line payload carries only the component id, so the page must read the product's serial flag; GM-60 step 1 is to check that and, if needed, fetch the products for the order's BOM. | Check first |
| 22 | **Superseded by GD-36.** The owner **does** count. `crm/onboarding.py` counts active owners and sales staff. The sentence in this row that said the owner does not count is withdrawn. | Done |
| 23 | **Show "Start checkout" disabled with a reason, not hidden, and only when no payment provider is configured.** For a company on a trial plan, show "Free trial, ends {date}" instead of "No subscription". GM-80 step 1: confirm why the audit company, which has a plan, read "No subscription" (likely the response shape the page reads). | Confirm |
| 24 | **Not enough.** When no keys are stored, the save message must say "Saved. Not live: no keys are stored, so no payment can be taken." With keys, keep "Gateway settings saved". | |
| 25 | **Superseded by GD-37.** All five sections in one slice: dues, tickets, contracts, referrals, opportunity value. One-line reason when a section's flag is off: "{Section} is not turned on for your company." | |
| 26 | **"Straight line by default; written-down value can be chosen per asset."** **(checked)** The model defaults to straight line (SLM) and supports written-down value (WDV). | |
| 27 | **Add `first_lead`, `first_quote` and `receipt_from_link` only.** `first_invoice` already exists server-side (`TenantActivation.first_invoice_at`). **(checked)** | |
| 28 | **Superseded by GD-32.** Keep all three completion buttons visible. A4-1 is closed. | |

## Blocks a later step, not the UI work

| # | Answer | Notes |
|---|---|---|
| 29 | **Superseded by GD-33.** Wait until the pilot staff sessions are scheduled. Do not build the prototype before that date. Production editors stay unchanged. | |
| 30 | **Answered (GD-26).** Sessions are with staff of the three pilot companies, during the pilots' first weeks. Names come from those companies. This gates A5-7 and GM-99. | |
| 31 | **Answered (GD-24).** The company name is **Pilot Insurance Advisor**. | |
| 32 | **Answered (GD-27).** All three lanes start the same week. Each grant still needs an explicit go. | |
| 33 | **First template: the invoice with payment link** (a transactional message), second the reminder. Credentials stay in deployment secrets. **Yes, a short written consent policy is part of this plan** (new ticket GM-98): who may be messaged (the customer record already has a WhatsApp opt-in flag), what is sent, how to opt out. No reminder or campaign sending until it exists. | **Founder** for templates and credentials |

## Plan changes made from these answers

- GM-03: no create button; copy and dashes only. GM-13: on-page note. GM-20: heading "GSTR-6/7/8". GM-21 closed. GM-40: menu accepted. GM-47 closed (already built). GM-12: hide fields, keep the link.
- GM-50 and GM-51: campaigns and contracts field splits set; projects and job cards stay inline; referrals inline.
- GM-52: "Add contract" added. GM-60: confirm-in-dialog guard, with a payload check first. GM-80, GM-81, GM-33, GM-90: wording set as above.
- New GM-98 (WhatsApp consent policy) and GM-99 (prototype for disclosure).
- A3-2 reduced to three pages; A2-3 reduced to tables that overflow; A2-4 marked partial and re-measure.
