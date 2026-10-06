# Master Prompt — End-to-End UI Playwright Validation (All Flows, All Links)

> Paste **everything below this line** into a fresh Cursor / Claude Code session
> that has **Playwright MCP** (or Cursor IDE browser) available and a running
> Bizboard frontend + backend. Fill in the bracketed values first if the
> environment has changed since this was written (**2026-08-26**).
>
> This is **Wave 3** of the UI walkthrough series. It now includes the
> **new-user onboarding path** (register → tax/shop/payments → catalog with
> **opening stock** → first bill) and a dedicated **product / opening stock /
> stock management** chain before the rest of the app.
>
> Earlier passes: `UX_AUDIT_MASTER_PROMPT.md`, `UX_AUDIT_WAVE2_MASTER_PROMPT.md`,
> `WORLDCLASS_QUALITY_AUDIT_MASTER_PROMPT.md`. Do **not** open those findings
> files until your own pass is complete.

---

## Role

You are a **senior QA engineer + first-time shopkeeper** of Bizboard, a GST
billing, inventory, payments, and books app for Indian SMEs.

Your job is to **validate every flow and every feature end-to-end, in the
correct business sequence**, using **only the live UI via Playwright**. You
must **click every visible link, tab, button, menu item, icon action, breadcrumb,
pagination control, and in-page shortcut**, observe the real behaviour, and
**log every bug, defect, and improvement suggestion** with evidence.

You are **not** a developer on this task. Do not open `web/src` or `backend/`
to decide what a screen “should” do. You **may** use `web/src/App.tsx`,
`web/src/navigation/menu.ts`, and `docs/onboarding/NEW_USER_ONBOARDING_PLAN.md`
**only as a coverage checklist** of URLs and onboarding steps. If the screen
is confusing, unlabeled, or broken from the UI alone, that **is** the finding.

**Do not fix code. Report only.**

## Mission (non-negotiable)

1. **Sequence first.** Run the **new-user onboarding path**, then **product +
   opening stock + stock management**, then the rest of the business chain as
   one continuous story. A signup that never reaches a Completed first bill,
   an item that never posts opening stock, or a purchase that never hits
   stock, is a failed product — not a skipped module.
2. **Click everything.** On every page: every sidebar item, header control,
   in-page link, tab, chip, row action, overflow menu, dialog button, footer
   link, empty-state CTA, and help/tooltip if clickable. Record what happened.
3. **End-to-end, not screenshot-only.** Type, save, submit, open the result,
   then prove the next module actually changed (stock, outstanding, reports,
   PDF). A page that “loaded” is not a pass.
4. **Log everything.** Bugs, defects, broken flows, validation gaps, RBAC
   leaks, console/network errors, **and** improvement suggestions. Completeness
   beats speed. A “looks fine” screen that was not actually submitted is
   **not tested**.

## Environment

Confirm which URL actually serves **Bizboard** (check page title). On mixed-dev
machines port 5173 may be a different project.

- Frontend (try in this order):
  1. `http://localhost` (Docker / nginx)
  2. `http://localhost:5173` (Vite) — **only if the title is Bizboard**
- Backend: same-origin `/api/v1/` or `http://localhost:8000/api/v1/`
  (OpenAPI at `/api/v1/docs/` if enabled)
- Owner login (seeded demo, for full-module sweep): `demo@bizboard.local` /
  `DemoPass123!` (from `seed_demo`). **Do not use this account for the
  onboarding path** — seeds are treated as complete and must not trap the
  Owner in `/setup`.
- **New Owner (onboarding path):** register a unique account during the run,
  e.g. `e2e3-owner-{timestamp}@bizboard.test` / `E2E3OwnerPass123!`. This is
  the only way to exercise Register → Login → `/setup` or the dashboard
  checklist as a first-time shopkeeper.
- If the DB is empty: `python manage.py seed_demo` from `backend/` (needed
  for the demo sweep; onboarding still uses a fresh register).
- Create a **Sales Staff** user via Settings → Users (or invite if that UI
  exists) during the run. Prefix `e2e-staff@bizboard.local`. Staff / invitees
  must **never** be forced into Owner `/setup`. Log if invite/create is broken.
- Feature flags may hide modules (POS, GSTR, AI Insights, Tally, Accounting,
  Manufacturing, Payroll, CRM, TDS, **setup wizard**). Test whatever is
  **reachable**. A nav item that 403s, or a hidden URL that still loads, is
  itself a finding.
- **`ENABLE_SETUP_WIZARD`** (backend + `VITE_ENABLE_SETUP_WIZARD` / feature-
  flags API): when **on**, a new incomplete Owner should hard-redirect `/` →
  `/setup`. When **off**, no hard redirect — dashboard **Onboarding checklist**
  only. Test the path that is actually on; if you can tell the flag is off,
  still open `/setup` by URL and log whether it bounces to `/` (expected) or
  loads anyway (finding). Do not flip the flag in config to “make it work.”
- Celery worker/beat may be unhealthy. If a flow hangs on “processing”
  (PDF, SMS, import, scheduled job), log it and note “possible worker
  dependency” — still a user-facing defect if there is no timeout/error.

### Tools (Playwright MCP)

Use the Playwright MCP tools for this session (`user-Playwright` namespace),
for example:

- `browser_navigate`, `browser_navigate_back`, `browser_tabs`
- `browser_snapshot` (accessibility tree — **primary** way to find clickable
  elements; do this after every navigation and after every major action)
- `browser_click`, `browser_hover`, `browser_type`, `browser_fill`,
  `browser_fill_form`, `browser_select_option`, `browser_press_key`,
  `browser_file_upload`, `browser_drag`, `browser_drop`
- `browser_wait_for`, `browser_resize`
- `browser_take_screenshot` — **every finding**, not just critical ones
- `browser_console_messages`, `browser_network_requests`,
  `browser_network_request`
- `browser_handle_dialog` for native confirms
- `browser_evaluate` only when you need to list all `a[href]`, buttons, or
  compare displayed totals to API JSON — not to “make the app work”

If Playwright MCP is unavailable, use Cursor IDE browser tools with the same
protocol. Do **not** fall back to reading source as a substitute for clicking.

### Test data prefix

Prefix every record you create with **`E2E3-`** (distinct from `UXAUDIT-`,
`UXWAVE2-`, `FRAUDIT-`, `WCAUDIT-`). Note in the report that this data exists
and is not cleaned up.

Examples: new owner `e2e3-owner-{ts}@bizboard.test`, customer
`E2E3-Test Customer`, goods item `E2E3-Widget`, service `E2E3-Service`,
supplier `E2E3-Test Supplier`, godown `E2E3-Godown-2`, GSTIN-style values
that are obviously fake but format-valid when the field requires a GSTIN.

## Ground rules

1. **Real interactions.** Type into fields. Click Save / Complete / Submit.
   Create a customer, supplier, product, purchase, sale, receipt, return.
   Looking is not testing.
2. **Happy path and abuse path on every form:** empty submit, invalid
   GSTIN / phone / email, negative qty, 0 qty, huge numbers, emoji / special
   characters in names, double-click Save, browser Back mid-form, refresh
   mid-form, two tabs on the same resource if feasible.
3. **Console + network after every load and every submit.** A 4xx/5xx or
   console error with no user-facing message is a bug even if the UI looks
   fine. Capture the URL, method, status, and message.
4. **Two viewports minimum:** desktop `1280×800` and mobile `375×812` (PWA).
   Resize, reload, re-run the golden chain’s key screens and the nav/drawer
   on mobile. Log layout overlap, horizontal scroll, unreachable controls.
5. **No live side effects.** Do not complete a real Razorpay/UPI payment, do
   not send live SMS / WhatsApp / email to a real number, do not submit a
   live IRN / e-way bill to NIC. If a control is about to fire one: stop,
   log `not tested (external side effect)`, screenshot the gate, move on.
6. **Do not modify code or config** to make something work. Broken is the
   finding.
7. **Work in batches. Write the report incrementally** after each stage so
   nothing is lost if the session dies. Use a todo list of stages; mark them
   complete as you go. Do not wait for approval between stages.
8. **Do not read prior findings files until Stage 17 (cross-check).** Opening
   them first inherits their blind spots.

## What to log (three classes — log all three)

### A. Bug (functional / data wrong)

Wrong number, wrong tax split, stock did not move, crash, blank page, 500,
data loss, PDF mismatch, report missing the document you just posted.

### B. Defect (flow / product broken or unsafe)

Dead-end, infinite spinner, silent failure, Save does nothing, dialog with
no primary action, RBAC leak (button visible then 403), nav shows a page the
route rejects, destructive action with no confirm, session/token weirdness.

### C. Improvement (usability, polish, accessibility, copy)

Unclear label, missing empty/loading/error state, inconsistent terms
(“Warehouse” vs “Godown”), buried action, no keyboard focus, poor contrast,
typo, placeholder left in, slow table with no feedback, missing pagination,
mobile drawer hard to use, extra click that a shopkeeper should not need.

If you are unsure whether it is B or C, **log it anyway** as the more severe
class. Duplicate later beats missed now.

## Severity

- **Critical** — blocks a core money/stock/tax task; data loss; wrong rupees
  or tax; cannot log in
- **High** — workaround exists but painful/non-obvious; wrong data shown
  without loss; whole viewport broken; RBAC leak
- **Medium** — annoying, inconsistent, or unclear; does not block the task
- **Low** — cosmetic, copy, minor polish
- Improvements may be Medium or Low; they are still mandatory to log.

## Coverage ledger (keep this live in the report)

After Stage 0, paste a table of **every route below**. Mark each:
`Pass` / `Fail` / `Partial` / `Blocked` / `Not reachable (flag off)` /
`Not in nav but URL works` / `In nav but 403`.

Never skip a reachable route because “it looks like the list page.”

### Unauthenticated

| Route | Notes |
|---|---|
| `/login` | blank submit, bad password, `?next=` deep-link return, `?registered=1` banner after signup |
| `/register` | **complete a real signup** in Stage 2 (not only the empty-form pass); validation, password rules; success must go to **login**, not auto-login |
| `/forgot-password` | empty / invalid email; do not spam a real inbox |
| `/reset-password` | missing/expired token error state |
| `/invite` | missing/expired token; later a real invite link if Users can copy one |
| `/pay/:token` | missing + garbage token; later retest with a real link |

### App shell (Owner)

| Route |
|---|
| `/` dashboard (checklist tiles if onboarding incomplete) |
| `/setup` (Owner wizard; `?step=tax\|shop\|payments\|catalog\|first_bill`) |
| `/settings/import?kind=PRODUCTS&return=/setup?step=catalog` (wizard import round-trip) |
| `/pos` |
| `/insights` `/insights/alerts` `/insights/health` `/insights/cashflow` `/insights/assistant` |
| `/sales/new` `/sales/bill-upload` `/sales/history` `/sales/history/:id` `/sales/history/:id/edit` |
| `/sales/quotations` `/sales/orders` `/sales/orders/new` `/sales/orders/:id` |
| `/sales/delivery-challans` `/sales/delivery-challans/new` `/sales/delivery-challans/:id` |
| `/sales/credit-notes` `/sales/credit-notes/new` `/sales/credit-notes/:id` |
| `/sales/debit-notes` `/sales/debit-notes/new` `/sales/debit-notes/:id` |
| `/sales/returns` `/sales/recurring` `/sales/customers` `/sales/receipts` |
| `/purchases/new` `/purchases/bill-upload` `/purchases/history` `/purchases/history/:id` `/purchases/history/:id/edit` |
| `/purchases/returns` `/purchases/credit-notes` `/purchases/credit-notes/new` `/purchases/credit-notes/:id` |
| `/purchases/debit-notes` `/purchases/debit-notes/new` `/purchases/debit-notes/:id` |
| `/purchases/orders` `/purchases/orders/new` `/purchases/orders/:id` |
| `/purchases/suppliers` `/purchases/payments` |
| `/payments/links` `/payments/statements` `/payments/reconciliation` |
| `/inventory/products` `/inventory/stock` `/inventory/low-stock` `/inventory/expiry-alerts` |
| `/inventory/adjustments` `/inventory/warehouses` `/inventory/stock-counts` `/inventory/transfers` `/inventory/serials` |
| `/reports/sales` `/reports/purchases` `/reports/inventory` |
| `/reports/customer-ledger` `/reports/supplier-ledger` `/reports/statutory-events` |
| `/reports/cash-book` `/reports/stock-valuation` `/reports/tds-tcs` |
| `/reports/trial-balance` `/reports/profit-and-loss` `/reports/balance-sheet` `/reports/books-health` |
| `/reports/gstr1` `/reports/gstr3b` `/reports/gstr9` `/reports/gstr2b` `/reports/gst-health` |
| `/settings/company` `/settings/gst` `/settings/units` `/settings/items` `/settings/templates` |
| `/settings/users` `/settings/import` `/settings/backup` `/settings/billing` |
| `/settings/bank-accounts` `/settings/payment-gateway` `/settings/price-lists` |
| `/settings/accounting` `/settings/ai` `/settings/tally` |
| `/accounting/accounts` `/accounting/journals` `/accounting/bank-reconciliation` |
| `/accounting/cost-centers` `/accounting/fixed-assets` `/accounting/periods` |
| `/manufacturing/boms` `/manufacturing/work-orders` |
| `/payroll/employees` `/payroll/pay-runs` |
| `/crm/leads` `/crm/opportunities` |
| `/some-nonexistent-route` → 404 page |

Also hit redirects (must not 404): `/sales/upload` → bill-upload,
`/purchases/upload` → bill-upload, `/inventory/expiry` → expiry-alerts,
`/inventory/count` → stock-counts, `/payments/recon` → reconciliation,
`/reports/profit-loss` → profit-and-loss, `/accounting/chart-of-accounts` →
accounts, `/accounting/bank-recon` → bank-reconciliation,
`/manufacturing` `/payroll` `/crm` index redirects.

## Per-page click protocol (run on EVERY page)

After `browser_navigate` or after a click that changes the view:

1. `browser_snapshot`. Wait until spinners finish (or log infinite spinner).
2. **Inventory clickables.** From the snapshot, list every:
   - sidebar / drawer nav item (expand groups)
   - header: logo, company switcher, search, notifications, help, theme,
     language, user menu, logout
   - breadcrumbs, tabs, filters, date pickers, export/print/share/PDF
   - primary CTA, secondary CTA, row kebab/overflow, inline links
   - empty-state button, pagination, sort headers
   - dialogs/drawers that open from those clicks
3. **Click each in-page control once** (not every sidebar item on every page —
   sidebar is Stage 2’s full sweep, then spot-check it still matches the page).
   For in-page links: click, observe, screenshot if surprising, then
   `browser_navigate_back` or close the dialog so you can continue the list.
4. **Observe:** destination URL, title, data loaded vs empty, error toast,
   whether the control did nothing, whether a new tab opened, whether
   unsaved changes were discarded without warning.
5. **Console + network** for that page.
6. Tick the coverage ledger. Log findings immediately.

**Do not** click Logout until Stage 15 except as a dedicated logout test.
**Do not** click billing-plan “Pay now” / live gateway checkout.

Optional but high-value: `browser_evaluate` to dump
`[...document.querySelectorAll('a[href],button,[role="button"],[role="link"]')]`
mapped to text + href, then reconcile against the snapshot so icon-only
buttons are not skipped.

## Golden business chain (run this FIRST as one sitting)

This is the product’s reason to exist. Treat it as **three linked stories**.
At every handoff, the downstream screen must show the **same numbers
immediately** (not “after refresh, maybe”). Write IDs/qty/amounts into the
report as you go.

Prefer running Chain A → B → C on the **new Owner tenant** created in Chain
A. Use `demo@bizboard.local` later for the full nav sweep and RBAC — not as
a substitute for onboarding.

### Chain A — New Owner onboarding (signup → first Completed bill)

Goal: a self-serve Owner reaches a **Completed first bill in one session**,
with GST type set so tax Complete does not fail later. First bill = guided
**sales invoice** Complete (POS only if the wizard actually offers it and
POS is on).

```
A0. /register as unique E2E3-owner-{ts}@bizboard.test
    — company name, email, password, phone, state
    — GST type / GSTIN are deferred to setup (short register)
    — success must send you to login, not auto-login (anti-enumeration)
A1. /login — ?registered=1 (or equivalent) banner in EN; try HI if a
    language switcher exists
A2. Landing
    — Wizard ON: hard redirect / or dashboard → /setup
    — Wizard OFF: dashboard Onboarding checklist (4 tiles); /setup by URL
      should bounce home
    — Seeded demo Owner must NOT be forced into /setup
A3. /setup step Tax (or checklist CTA → /settings/gst)
    — REGULAR: GSTIN required, valid format
    — UNREGISTERED: no GSTIN; later first bill is Bill of Supply / non-GST
    — COMPOSITION: GSTIN optional; must not be guided into a regular GST
      tax Complete
    — empty Regular GSTIN must block Continue
A4. Shop identity — address required; city/pincode; state from register
A5. Payments — bank and/or UPI; Skip optional must work
A6. Catalog (this is the product + opening-stock on-ramp)
    — Quick-add item: name, selling price, GST rate, HSN if Regular,
      **opening qty > 0**
    — After save: product exists AND Current stock shows that opening qty
      at the default godown (opening posts OPENING_STOCK, not a fake field
      on the item)
    — Click “Add samples” if shown; click “Import products” and complete
      the round-trip `/settings/import?kind=PRODUCTS&return=/setup?step=catalog`
      (or log if return= is dropped)
    — Continue must block if zero products
A7. First bill — Create first bill → Completed sales doc
    — Walk-in customer created if needed
    — Invoice type matches registration (GST vs BoS)
    — Celebration screen: View invoice + Go to dashboard both work
    — Stock decreased by the billed qty (usually 1)
A8. Dashboard residual checklist — hide when activation is done; leftover
    optional tiles only if you skipped payments
A9. Skip-for-now (separate pass or second new Owner if you already
    completed A7): Skip sets dismiss, no hard redirect, checklist remains
    until first Completed bill
```

If the wizard is off, walk the **same spine via checklist tiles**:
Company/GST → Bank → Products (with opening stock on the item form) →
New invoice Complete. Log missing opening-qty on the checklist path as a
defect/improvement — shopkeepers need opening stock before they can sell.

Do **not** use the demo account for Chain A.

### Chain B — Product, opening stock, and stock management

Run on the new Owner (or continue after A6 even if first bill is still
pending). This is **not** optional polish — it is how inventory becomes
true.

```
B1. Godowns — Inventory → Warehouses/Godowns
    — company has one default godown after register
    — add E2E3-Godown-2 (name + code)
    — UI says Godown (Warehouse in API is OK; mixed labels are a finding)
B2. Create GOODS item E2E3-Widget (full item dialog, not only wizard)
    — Basic: type Goods, name, SKU/barcode, HSN, unit, description
    — Stock: track inventory ON
    — Opening: qty 100, default godown, as-of date, unit cost
    — If batch/expiry UI exists: at least one lot (batch no + expiry)
    — Pricing: sale + purchase price, GST, MRP/wholesale if shown
    — Custom fields if Item Settings defined any
    — Save Item (and Save & New if present)
B3. Prove opening stock
    — Current stock = 100 at the chosen godown
    — Edit item: opening qty is **locked**; CTA to Adjust Stock (do not
      silently rewrite OPENING_STOCK)
    — Stock valuation / inventory report reflects 100 × unit cost
B4. Create SERVICE item E2E3-Service
    — Stock Details / godown / opening qty must be hidden or rejected
    — Current stock must not list it as on-hand goods
B5. Create non-stock GOODS (track inventory OFF) if the form allows —
    no opening qty, no godown required
B6. Opening lots / serials (if UI exists)
    — Batch item: two lots, two expiries, possibly two godowns
    — Serial item: opening serial rows; qty = number of serials
    — Batch and serial mutually exclusive on one SKU
B7. Stock operations (use E2E3-Widget; record qty after each)
    — Adjustment +5 with reason → stock 105 (opening stays 100)
    — Adjustment −5 → back; expiry write-off if reason EXPIRED exists
    — Transfer default godown → E2E3-Godown-2 qty 10 → balances split
    — Stock count / physical count at one godown if the page posts
      ADJUSTMENT
    — Low stock: set reorder, drop qty below it, page lists the item
    — Expiry alerts: lot within 7/30/60/90 days appears
    — Serials page lists serials if tracking serial
B8. Bulk opening (Settings → Import products)
    — CSV/XLSX with name, HSN, prices, godown, opening_stock
    — Preview → validate → commit; error report on a bad row
    — Re-upload of the same SKU must **not** rewrite balances
    — Unknown godown name must fail that row, not auto-create
    — Blank godown → company default
B9. Negative / gate cases
    — Sell more than on-hand when company blocks negative stock
    — Sell expired lot when block_expired_stock is on
    — Cannot edit/delete the original opening movement
```

### Chain C — Purchase, sale, cash, reports (after stock is real)

Continue on the **same tenant** so opening + purchase + sale reconcile.

```
C1.  Settings → Company / GST / Units — confirm tax profile still correct
C2.  Supplier E2E3-Test Supplier (state, GSTIN if Regular)
C3.  Purchase bill: E2E3-Widget qty 10, tax, Complete
     → stock +10 at the purchase godown; supplier outstanding = bill total
C4.  Customer E2E3-Test Customer (same-state; later inter-state if GST)
C5.  Sales invoice: qty 3, tax, Complete
     → stock −3; FEFO lot if batch on; customer outstanding = invoice total
C6.  Partial receipt → customer outstanding drops
C7.  Partial supplier payment → supplier outstanding drops
C8.  Reports: Sales, Purchases, Inventory, Customer ledger, Supplier ledger
     — documents and amounts match the UI
C9.  Dashboard widgets moved vs the post-onboarding baseline
```

**GST extra (if Regular):** one intra-state invoice (CGST+SGST) and one
inter-state (IGST). Totals must match line math. PDF (if generated) must
match the screen. Do not wait forever on PDF — if stuck, log worker issue.

If any step fails, log Critical/High, screenshot, try a workaround, continue
the chain with a note that downstream proof is weakened.

## Then: full module sweep (proper sequence)

Do **not** random-walk the sidebar. After the golden chains, continue in this
order so later modules reuse `E2E3-` data.

### Stage 0 — Environment + tool check

- Confirm URL is Bizboard. Snapshot login page.
- Confirm Playwright snapshot/click/screenshot work.
- Create the findings file (empty skeleton + coverage table).
- Resize to 1280×800.
- Note whether `/setup` is reachable after a throwaway login as demo
  (should **not** trap demo). Log wizard vs checklist without changing flags.

### Stage 1 — Unauthenticated (forms only)

Login, register **empty-form / validation only** (complete signup in Stage 2),
forgot-password, reset-password (no token), invite (no token),
`/pay/not-a-real-token`. Blank submits, invalid emails, password visibility
toggle, “already have an account” links. Direct-URL `/sales/new` while logged
out must land on login **and** return to that page after login (`?next=`).

### Stage 2 — New Owner onboarding (Chain A)

**This stage is mandatory.** Do not skip it because demo login works.

1. Complete `/register` with unique E2E3 credentials. Click every link on
   the register page (login, terms if present).
2. Land on login with a registered banner. Sign in.
3. Execute Chain A in full: tax → shop → payments → **catalog with opening
   qty** → first bill → stock proof → dashboard checklist.
4. Click every wizard control: Back, Skip for now (use a **second** new
   Owner if you already completed first bill — or Skip on payments only),
   Skip optional, Add samples, Import products, Create first bill, View
   invoice, Go to dashboard. Direct URLs `/setup?step=catalog` etc.
5. Abuse: Regular without GSTIN; Composition attempting GST tax Complete;
   Continue catalog with zero products; opening qty 0 vs negative; first
   bill with no product.
6. Invitee path if you can copy an invite: accept `/invite?token=` as staff
   — must **not** enter `/setup`.

Stay logged in as this new Owner for Stages 3–5 (product/stock/purchase)
when the tenant is usable. If billing/plan blocks writes, log it and
continue those writes on demo — still keep onboarding evidence from this
stage.

### Stage 3 — Demo Owner shell, click-all-nav

New browser context. Sign in as `demo@bizboard.local`. Dashboard: widgets,
links on KPI cards, charts, “view all”. Confirm **no** setup hard-redirect.
**Expand every sidebar group and click every nav leaf once.** Record
href vs page title vs empty/error. Open user menu: profile/settings/logout
(do not logout yet). Notifications if present. Search if present.
Open `/setup` via URL (demo should not be trapped).

### Stage 4 — Settings (foundations)

Company, GST, Units, Item settings (`/settings/items` — custom field defs
used by the product form), Templates (preview invoice template), Users
(create E2E3 staff / copy invite link), Bank accounts, Payment gateway
(do not fire live pay), Billing (do not buy a plan), Price lists,
Accounting settings, AI settings, Import (see Stage 5 for product+opening
CSV), Backup/export (download if it does not hang), Tally (if enabled — do
not run a destructive migration on demo data; stop at the confirm gate).

### Stage 5 — Product, opening stock, and stock management (Chain B)

This is the inventory spine. Click every control on each of these pages.

**Products (`/inventory/products`)**
- Empty state CTA, search, filters, pagination, row open/edit.
- Full create dialog: Basic / Stock / Pricing / Custom Fields tabs.
- Goods with opening lots (godown, qty, as-of, unit cost, batch, expiry).
- Service: no stock tab / reject opening.
- Generate barcode, Find HSN if present, Save, Save & New, Cancel.
- Edit: opening locked → Adjust Stock link. Unit immutable after first
  movement if the UI claims that.
- Duplicate name warning; unique SKU.

**Opening stock proof**
- Current stock (`/inventory/stock`): godown filter, lot/expiry expand,
  numbers = opening ± later movements.
- Inventory report + stock valuation match qty × cost.
- Import products with `opening_stock` / `godown` / batch columns.

**Stock management**
- Godowns: default, add, deactivate if present.
- Adjustments: reason required; posts ADJUSTMENT; never edits opening.
- Transfers: from/to godown, same lot/serial, complete, stock splits.
- Stock counts: start count, enter qty, post variance.
- Low stock, expiry alerts (windows 7/30/60/90 if offered).
- Serials list + scan/add if present.
- After each mutation, Current stock and (if open) the item row agree.

### Stage 6 — Purchase loop (full)

Suppliers CRUD. New purchase (draft save, complete, edit rules on completed).
History + detail: PDF, print, share, cancel (if allowed), e-invoice/e-way
controls if present (**do not submit live**). Bill upload (try a sample
image/PDF). Purchase orders: create → convert/receive if the UI offers it.
Returns, purchase credit notes, purchase debit notes. Supplier payments +
allocation. Confirm stock and supplier ledger after each posting.

### Stage 7 — Sales loop (full)

Customers CRUD (GSTIN validation, blocked customer if the UI has it).
New invoice: add line, discount BEFORE_TAX vs AFTER_TAX, cess if shown,
round-off, save draft, complete, PDF/print/share, edit vs locked fields on
completed, cancel. History filters/search. Quotations: create → convert to
invoice. Sales orders: create → convert. Delivery challans. Credit notes,
debit notes, sales returns (return a **non-first** line if multiple lines —
stock + outstanding). Recurring invoices. Sales bill upload. Receipts:
full, partial, allocation, over-allocation attempt. After return/sale,
**Current stock** must move.

### Stage 8 — Payments / cash ops

Payment links: create for the E2E3 invoice; open `/pay/:token` in a **logged-out**
tab; observe pay page; **do not** complete a live charge. Bank statements
upload if present. Bank reconciliation. Cash book.

### Stage 9 — POS (if enabled)

Cashier-speed sale of E2E3-Widget: search/barcode, qty, pay cash, park/hold
if present, receipt. Confirm stock and sales history. Gate: staff without
POS permission.

### Stage 10 — Reports (every report that loads)

Filters, date range, party filter, export/CSV/PDF **actually downloads**.
Numbers must match the golden-chain documents (including **opening stock**
and later purchase/sale movements). GSTR-1 / 3B / 9 / 2B / GST health if
enabled. TDS/TCS if enabled. Trial balance, P&L, balance sheet, books
health, stock valuation, statutory events.

### Stage 11 — Accounting (if enabled)

Chart of accounts, journals (create a simple E2E3 journal if the UI allows),
cost centers, fixed assets, periods (do not close FY if irreversible — stop
at confirm), accounting bank recon.

### Stage 12 — Insights (if enabled)

Hub, alerts, health, cashflow, assistant. Ask the assistant one harmless
question. Do not paste secrets.

### Stage 13 — Manufacturing / Payroll / CRM (if enabled)

BOMs, work orders (complete one tiny E2E3 WO if stock allows). Employees
(TDS fields if shown), pay runs (do not mark a live salary payment as sent).
Leads, opportunities (convert if offered).

### Stage 14 — Public pay + 404 + redirects

Real payment-link token from Stage 8. Garbage URLs. All redirect routes in
the coverage table.

### Stage 15 — Mobile viewport

`browser_resize` 375×812, reload. Re-open: register/login, **`/setup` sticky
footer CTA** (or checklist tiles), product dialog Stock Details, current
stock, new invoice (can you complete a line?), nav drawer, one settings
page, one report. Log overflow, sticky headers covering CTAs, unreachable
Save.

### Stage 16 — RBAC + session + cross-cutting

Logout. Login as Sales Staff. Walk dashboard + every remaining nav item.
Staff must **never** land on `/setup`. Forbidden/limited landing must be
consistent: **no** privileged button that 403s; **no** hidden-but-open URL
unless that is an explicit finding. Direct-URL Owner routes as staff
(including `/setup`, settings, adjustments). Theme/language if present.
Back/forward. Idle/session: clear site data or expire token if you can do
it from the browser without attacking the server; log session-expiry UX.
404.

### Stage 17 — Cross-check (last)

Only now open:

- `docs/reviews/MASTER_ISSUE_REGISTER.md`
- `UX_AUDIT_REPORT.md` / `UX_WALKTHROUGH_AUDIT_REPORT.md`
- `docs/reviews/UX_AUDIT_WAVE2_FINDINGS.md`
- `docs/reviews/FR_AUDIT_FINDINGS.md`
- `docs/reviews/WORLDCLASS_QUALITY_AUDIT_FINDINGS.md`

For each of your findings: if exact duplicate, reference the old ID and mark
`duplicate`. If a prior report claimed **fixed** and it is still broken,
flag **regression** prominently. New issues stay as `E2E3-NNN`.

## Abuse / negative cases (sprinkle into the matching stage)

**Onboarding**
- Register success looks like an error / auto-login
- Regular tax step continues without GSTIN
- Composition guided into GST tax invoice Complete
- Staff/invitee forced into `/setup`
- Seeded demo Owner trapped in `/setup`
- Wizard Skip does not dismiss; or dismiss still hard-redirects
- Import from catalog step drops `return=/setup?step=catalog`
- First bill Complete with zero products / silent failure

**Product / opening stock / stock**
- Opening qty accepted on a SERVICE item
- Opening qty editable after the first OPENING_STOCK post
- Re-import of the same SKU rewrites current stock
- Unknown godown name auto-creates a location
- Transfer to the same godown, or qty greater than source balance
- Negative stock sale when company blocks it
- Expired lot sale when `block_expired_stock` is on
- Adjustment without a reason if the UI requires one

**Documents**
- Completed invoice line freely editable (qty/product/GST)
- Blank party state on GST complete (unless assume-local)
- Double Complete / double receipt
- CSV import with a bad row — error report must be usable, no silent poison
- Unauthenticated `/media/` PDF URL if you can discover a PDF path from the
  UI (do not brute-force); must not serve privately

## Report format

Write to **`docs/reviews/E2E_UI_PLAYWRIGHT_VALIDATION_FINDINGS.md`**.

Append after **each stage**. Do not hold findings in memory until the end.

```markdown
# E2E UI Playwright Validation — Bizboard
Run date: [ISO date] · Tester: [agent] · URL: [url] · git: [short sha]
Roles: New Owner `[e2e3-owner-…]`; Demo Owner `demo@bizboard.local`; Staff `[email]`
Viewport: 1280×800 then 375×812
Test data prefix: E2E3-
Wizard flag observed: on | off | unknown

## Summary
- Stages completed: X / 17
- Routes: Pass / Fail / Partial / Blocked / Flag-off
- Findings: N critical, N high, N medium, N low
- Improvements: N
- Chain A onboarding: Pass / Fail (failed step: …)
- Chain B product/opening/stock: Pass / Fail (failed step: …)
- Chain C purchase/sale/reports: Pass / Fail (failed step: …)
- Modules not reached: […]

## Coverage ledger
| Route | Result | Notes |

## Golden chain evidence
### Chain A — Onboarding
| Step | Result | Evidence |
### Chain B — Product / opening stock / stock
| Item/godown | Opening qty | After ops | Downstream proof |
### Chain C — Purchase / sale / cash
| Step | Doc/ID | Amount / qty | Downstream proof |

## Findings

### E2E3-001 — [short title]
- **Class:** Bug | Defect | Improvement
- **Module/Page:** sales/new (Sales → New Invoice)
- **Severity:** Critical | High | Medium | Low
- **Category:** Broken flow | Data/calc | Validation | RBAC | API/console |
  Accessibility | Responsiveness | Copy | Performance | Suggestion
- **Steps to reproduce:**
  1. …
  2. …
- **Expected:** …
- **Actual:** …
- **Impact:** …
- **Suggested fix / improvement:** …
- **Evidence:** screenshot file, console text, network method+status+url
- **Viewport / role:** desktop|mobile, New Owner|Demo Owner|Staff
- **Cross-check:** new | duplicate of BB-… / UXW2-… | regression of …

## Improvements backlog (also listed as E2E3-n above)
Short bullets grouped by module for a founder skimming.

## Top 10 fix-first
Ordered by (severity × how core the flow is).
```

Number findings sequentially `E2E3-001`, `E2E3-002`, … across the whole run.
Screenshots: `docs/reviews/screenshots_e2e3/` with names
`E2E3-001_short_slug.png`.

## Before you start

If URL and Owner credentials above still match this machine, **do not wait
for confirmation**. Confirm the running URL in one navigation, then start
Stage 0.

Only stop mid-run if:

- a flow would send a real SMS / email / payment / IRN, or
- the app is down, or
- you need a new session to continue — then checkpoint the findings file
  and coverage ledger so the next session resumes at the next incomplete
  stage.

Proceed stage by stage until the coverage ledger has a result on every
reachable route and Chains A–C have been executed once on desktop
(and onboarding + product/stock + invoice on mobile).
