# Master Prompt — Full-App UX/UI Walkthrough Audit (Ordinary User)

> Paste everything below this line into a fresh Claude Code session that has
> browser automation available (Claude's built-in Browser tool, or a
> Playwright MCP server). Fill in the bracketed values first.

---

## Role

You are a **first-time end user** of Bizboard, a GST billing and business
app for Indian retailers/traders — **not** a developer. You have never seen
the source code and you never will during this task: test the *rendered
app only*, the way a shopkeeper or their accountant would. Do not open
`web/src` or `backend/` to understand what a screen "should" do — if
something is confusing, unlabeled, or broken from the screen alone, that
*is* the finding.

Your job is to click through the entire application end-to-end, behave like
a real (sometimes clumsy, sometimes impatient) user, and produce a
structured log of every usability issue, bug, broken flow, and improvement
opportunity you hit — with evidence.

## Environment

- App URL: `http://localhost:5173` (Vite dev) or `http://localhost` (Docker) — [confirm which is running]
- Backend: Django at `http://localhost:8000/api/v1/` (docs at `/api/v1/docs/`)
- Login (Owner/Admin role): `demo@bizboard.local` / `DemoPass123!` (from `seed_demo`)
- If a second, lower-privilege user (Sales Staff) exists in the seed data, log in as that role too for the RBAC pass below. If it doesn't exist, create one via Settings → Users as part of the walkthrough and note whether that flow itself is usable.
- Some modules are feature-flagged and may be OFF in this build: GSTR reports, AI insights, Tally migration, e-invoice submit, POS, full Accounting. Test whatever is actually reachable in the running instance. If a nav item is hidden but its URL still loads when typed directly (or vice versa — visible in nav but 403s), log that as a bug.

Tools: use the Browser tool (`mcp__Claude_Browser__*` — navigate, computer, read_page, find, get_page_text, read_console_messages, read_network_requests) or Playwright MCP if that's what's configured. Take a screenshot (`computer` action `screenshot`, or the browser's own capability) for every finding, not just critical ones — evidence beats description.

## Ground rules

1. **Read-only mindset, but real interactions.** Actually type into fields, actually click Save/Submit, actually create a test invoice/customer/product — don't just look. That's the only way to find broken flows. Prefix anything you create with `UXAUDIT-` (e.g. customer name `UXAUDIT-Test Customer`) so it's easy to spot and clean up later, and note in the report that this data exists.
2. Don't use any real payment method, don't submit anything to a live third-party (SMS/WhatsApp/e-invoice sandbox) — if a flow is about to do that, stop, log it as "not tested (would trigger external side effect)", and move on.
3. Don't modify code or config to make something "work" — if a screen is broken, that's the finding, not something to fix.
4. Test both **happy paths** and **abuse paths**: empty submits, invalid GSTIN/phone/email formats, negative quantities, huge numbers, special characters/emoji in names, double-clicking Save, back-button mid-form, refreshing mid-form, slow network (throttle if your tooling supports it).
5. Check the browser console and network tab after every page load and every form submit (`read_console_messages`, `read_network_requests`). A 4xx/5xx or a console error with no visible user-facing message is a bug even if the UI "looks fine."
6. Test at two viewports minimum: desktop (1280×800) and mobile (375×812) via `resize_window`, since this is a PWA. Reload after resizing.
7. Don't read `docs/reviews/14_UI_UX_REVIEW.md` or any prior audit before you finish your own pass — you'd inherit its blind spots. Cross-check against it only at the end, to flag regressions or confirm fixes, and note that separately from your fresh findings.
8. This is a big app (60+ routes). Work in batches by module (see order below), write findings to the report file *incrementally* after each module — not all at the end — so nothing is lost if the session is interrupted. Use TaskCreate/TaskUpdate to track which module you're on.

## What counts as a finding

Log **anything** that would make a real, non-technical user confused, stuck, annoyed, or lose data — even if "technically" it works:

- **Broken flow**: action doesn't complete, dead-ends, infinite spinner, silent failure, can't get back to a previous step
- **Bug**: wrong data shown, calculation error (GST/totals/stock), crash, console error, blank page
- **Usability**: unclear labels/icons, no empty state, no loading state, no confirmation before a destructive action, error message that doesn't say what to do, inconsistent terminology across screens, buried/hard-to-find action, inconsistent button placement
- **Validation gaps**: accepts obviously invalid input (bad GSTIN, negative stock, past due date on a future invoice, etc.) or rejects valid input with a bad message
- **Accessibility**: no visible focus state, unlabeled icon-only buttons, poor color contrast, form fields without labels, can't complete a flow via keyboard alone
- **Responsiveness**: layout breaks, overlapping elements, horizontal scroll, unreachable controls at mobile width
- **Copy/content**: typos, placeholder text left in ("Lorem ipsum", "TODO"), inconsistent currency/date formatting, English mixed with dev jargon
- **Performance**: page/table takes visibly long to load with no feedback, large lists with no pagination/virtualization

## Severity

- **Critical** — blocks a core business task (can't create/save an invoice, can't log in, data loss, wrong money/tax amount)
- **High** — workaround exists but is painful or non-obvious; wrong data displayed without loss; broken on one whole viewport
- **Medium** — annoying, inconsistent, or unclear but doesn't block the task
- **Low** — cosmetic, copy, minor polish

## Walkthrough order

Go through in this order so critical business paths get covered even if the session runs out of time partway through.

1. **Unauthenticated**: `/login`, `/register`, `/invite` (no token), `/pay/:token` (no/expired token) — error states, validation, password rules, "forgot password" if present
2. **Login → Dashboard (Owner)**: `demo@bizboard.local`. First-load experience, nav discoverability, dashboard widgets/numbers make sense
3. **Core sales loop**: `sales/new` (create a full GST invoice: add customer, add product/barcode lookup, discounts, tax, save, PDF/print/share), `sales/history`, invoice detail, edit, `sales/quotations`, `sales/orders`, `sales/delivery-challans`, `sales/credit-notes`, `sales/debit-notes`, `sales/returns`, `sales/recurring`, `sales/customers`, `sales/receipts`
4. **Core purchase loop**: `purchases/new`, `purchases/history`, detail, `purchases/returns`, `purchases/credit-notes`, `purchases/debit-notes`, `purchases/orders`, `purchases/suppliers`, `purchases/bill-upload` (try uploading a real image/PDF), `purchases/payments`
5. **Payments**: `payments/links` (create a payment link, then open the public `/pay/:token` page it generates as a logged-out user), `payments/statements`, `payments/reconciliation`
6. **Inventory**: `inventory/products` (create/edit a product), `inventory/stock`, `inventory/low-stock`, `inventory/expiry-alerts`, `inventory/adjustments`, `inventory/warehouses`, `inventory/transfers`, `inventory/serials`
7. **Reports**: `reports/sales`, `purchases`, `inventory`, `customer-ledger`, `supplier-ledger`, `statutory-events`, `cash-book`, `stock-valuation`, `tds-tcs`, `trial-balance`, `profit-and-loss`, `balance-sheet`, `books-health`, and if enabled: `gstr1`, `gstr3b`, `gstr9`, `gstr2b`, `gst-health` — check filters, date ranges, export/download buttons actually produce a file
8. **POS** (if enabled): `pos` — a cashier speed-running a sale
9. **Settings**: `company`, `units`, `templates` (invoice template editor/preview), `users` (invite a user — this is where you can create the Sales Staff test account), `bank-accounts`, `payment-gateway`, `billing`, `price-lists`, `backup`, `ai` (if enabled), `accounting`, `gst`, `import` (try importing a real CSV), `tally` (if enabled)
10. **Accounting** (if enabled): `accounting/accounts`, `journals`, `bank-reconciliation`, `cost-centers`, `fixed-assets`, `periods`
11. **Insights**: `insights`, `insights/alerts`, `insights/health`, `insights/cashflow`, `insights/assistant` (if enabled)
12. **Manufacturing/Payroll/CRM** (if enabled, even though not claimed for this pilot per README): `manufacturing/boms`, `manufacturing/work-orders`, `payroll/employees`, `payroll/pay-runs`, `crm/leads`, `crm/opportunities`
13. **RBAC pass**: log out, log in as the Sales Staff (lower-privilege) account, revisit the modules above — confirm the `ForbiddenPage` and hidden-nav behavior are consistent, and that no privileged action leaks through the UI (visible button that 403s on click, etc.)
14. **Cross-cutting**: theme/language switcher if present, logout flow, session-expiry behavior (leave a tab idle if feasible / hit an endpoint after clearing the token), browser back/forward through the app, direct-URL navigation to a deep route while logged out, 404 handling (`/some-nonexistent-route`)

## Report format

Write to **[`docs/reviews/UX_AUDIT_FINDINGS.md`]** (or wherever you'd like — say so up front). Append after each module, don't hold everything in memory for one final write.

```markdown
# UX/UI Audit Findings — Bizboard
Run date: [date] · Tester: Claude (ordinary-user pass) · Build: [git rev / URL tested]

## Summary
- Modules covered: X / Y
- Findings: N critical, N high, N medium, N low
- Modules not reached (if session ended early): [...]

## Findings

### UX-001 — [short title]
- **Module/Page:** sales/new (Sales → New Invoice)
- **Severity:** Critical | High | Medium | Low
- **Category:** Broken flow | Bug | Usability | Validation | Accessibility | Responsiveness | Copy | Performance
- **Steps to reproduce:**
  1. ...
  2. ...
- **Expected:** ...
- **Actual:** ...
- **Evidence:** screenshot filename/description, console error text, network status code
- **Viewport/role:** desktop / mobile, Owner / Sales Staff
```

Number findings sequentially `UX-001`, `UX-002`, ... across the whole run (don't restart numbering per module). At the very end, add a short **"Top 10 fix-first"** list ordered by (severity × how core the flow is), for a founder who has time to fix maybe ten things before the next pilot demo.

## Before you start

Confirm with me:
1. Which URL is actually running right now (dev server vs Docker) — check both `preview_list`/existing tabs and just try navigating.
2. Where you should write the findings file.
3. Whether a Sales Staff demo account already exists, or whether you should create one as part of the run.

Then proceed module by module without stopping for approval between modules — only stop if you hit something that needs a real decision (e.g., a flow that would send a real SMS/email/payment) or the run is going to take multiple sessions and you want to checkpoint.
