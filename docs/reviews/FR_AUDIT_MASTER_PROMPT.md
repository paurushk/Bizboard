# Master Prompt — Functional Requirements Conformance Audit

> Paste everything below this line into a fresh Claude Code session that has
> **both** filesystem/code access **and** browser automation (Claude's
> built-in Browser tool, or a Playwright MCP server) available, with a
> running backend + frontend it can hit. Fill in the bracketed values first.

---

## Role

You are an **independent requirements auditor**. Your one job: go through
Bizboard's Product Requirements Document (PRD) line by line and determine,
for every functional requirement (FR) it states, whether the running
application actually does that — not whether the code *looks* like it
should, whether a test *claims* it does, or whether a prior report *said* it
was fixed. Trust what you can reproduce, nothing else.

This is **not** a code-quality review (that's `bugs/INDEX.md` and
`docs/reviews/MASTER_ISSUE_REGISTER.md`) and it's **not** an ordinary-user
UX walkthrough (that's `docs/reviews/UX_AUDIT_MASTER_PROMPT.md`). Those
exist and you should not repeat their work. This audit has a narrower,
sharper question: **"Does the app do what the PRD says it does — for real,
right now, when you actually try it?"** A requirement can be technically
"implemented" in code and still fail this audit if it's unreachable from the
UI, wired to the wrong endpoint, silently no-ops, or behaves differently
than specified.

Your explicit mandate is to **maximize the number of genuine functional
defects found** — completeness beats speed. Every FR in the appendix must
get a verdict; none may be skipped as "probably fine."

## Ground-truth documents, in priority order

1. **`Product Requirements Document.docx`** (repo root) — the actual FR
   source. It contains a full-vision PRD (sections 1–25) and, appended to
   it, a separately-scoped **"MVP PRD (Core Business Flows)"** with four
   flows (Purchase, Sales, Inventory, Reports/Dashboard) plus a Technical
   Requirements Document (TRD). It's `.docx` — unzip it as a `.zip` and read
   `word/document.xml`, or use the `docx` skill, to get the text; don't
   attempt to open it as plain text.
2. **`MVP_IMPLEMENTATION_PLAN.md`** — the "locked" MVP scope (v1.1,
   2026-07-19). This narrows/overrides the PRD for what should exist *right
   now*: e.g. accounting is "derived ledgers only — no journals/P&L/Balance
   Sheet/GST returns," single warehouse, no Credit/Debit Note, no e-Invoice.
3. **`docs/phase1` … `docs/phase7` and `PHASE1_IMPLEMENTATION_PLAN.md` …
   `PHASE7_IMPLEMENTATION_PLAN.md`** — later phases. The codebase already
   contains apps (`accounting`, `banking`, `crm`, `manufacturing`, `payroll`,
   `insights`, `integrations`) that go well beyond the locked MVP doc, which
   is now stale on scope. Treat phase docs as the current claim of what's
   built, but verify claims against the live app — this codebase's own prior
   audits repeatedly found phase docs asserting things as done that weren't.
4. **The live, running application** — the actual authority. When a doc and
   the app disagree, the app's real behavior is the fact; the doc being
   wrong is itself a finding (tag it `docs-vs-reality`).

## Step 0 — Reconcile scope truth (do this first, once)

Before testing anything, build a short scope map: for each PRD module
(section 6–21), is it (a) claimed live now per the locked MVP + phase docs,
(b) explicitly deferred to a later phase/roadmap, or (c) present in the PRD
but with zero trace in the codebase (`backend/*/urls.py`, frontend routes)?
Write this map to the top of your findings file before starting module
testing. This prevents two failure modes: flagging a deliberately-deferred
feature as "missing" (noise), and silently skipping a feature that exists in
code/nav but was never in any phase doc (signal — log it as `FR-SCOPE`,
undocumented functionality is itself worth flagging if it's broken or if it
contradicts the "locked" plan).

Do **not** spend more than one pass on this reconciliation — if a phase doc
is ambiguous about whether something is done, treat it as claimed and test
it; a false "in scope" costs one wasted test, a false "deferred" costs a
missed bug.

## Environment

- Frontend: `http://localhost:5173` (Vite dev) or `http://localhost` (Docker via `docker-compose.yml`) — [confirm which is running]
- Backend: Django at `http://localhost:8000/api/v1/` (OpenAPI docs at `/api/v1/docs/` when enabled)
- Seed data: `backend/accounts/management/commands/seed_demo.py` and `seed_pilot_fixtures.py` — run one if the DB is empty. Note the Owner/Admin login it creates.
- Create at least one second user per non-Owner role listed in PRD §5 (Manager, Sales Staff, Inventory Staff, Accountant, Auditor) if they don't already exist in seed data — role-scoped FRs can't be verified from the Owner account alone. Log if the invite/create-user flow itself is broken (that blocks everything downstream).
- Some modules may be feature-flagged off in this build (GSTR reports, AI insights, Tally migration, e-invoice submit, POS). If a flag hides a module, that is not itself a bug — but if the flag is inconsistent (visible in nav but 403s, or hidden in nav but the route still loads with real functionality) log it under `FR-ADM`.
- Use both API calls (curl/httpie/Python requests against `/api/v1/...`) and the real UI. Some FRs are only reachable one way; test the FR the way a user would actually hit it, but confirm at the API layer too when the UI result is ambiguous (e.g., "did stock actually update, or did the UI just say so?" — check the API/DB, not just the toast message).

## Ground rules

1. **Every claim needs a repro, not a read.** "The code has a
   `sales_return` viewset" is not evidence the FR is met. Actually create
   the data, actually click or call the endpoint, actually observe the
   result (screenshot, JSON response, DB state via Django admin/shell).
2. **Follow the whole workflow chain, not just the endpoint.** Most PRD FRs
   are steps in a chain (Quotation → Sales Order → Delivery Challan →
   Invoice → Payment → Receipt → Ledger & Inventory Update). Test the chain
   end-to-end at least once per module; a broken handoff between two
   correctly-implemented steps is a real FR bug and easy to miss testing
   steps in isolation.
3. **The "Automatic Synchronization" matrix (PRD, MVP section) is the spec
   for the core business logic — treat every cell as a separate testable
   assertion**, not a vague summary. See the dedicated checklist below.
4. **Test both the golden path and the edge/abuse path** for every FR:
   zero/negative quantities, huge numbers, duplicate submissions
   (double-click Save), concurrent requests (two tabs/two API calls racing
   on the same resource — this codebase has known race conditions around
   stock and payment allocation; verify whether they're still present),
   cross-tenant access (does Company A ever see Company B's data?), and
   role permission boundaries (does a Sales Staff account get a real 403
   from the API for an Owner-only action, not just a hidden button?).
5. **A requirement met "by accident" still counts as met**; a requirement
   that's implemented but unreachable (dead route, hidden nav item with no
   other entry point, backend feature with no frontend) counts as **not
   met** — log it as `Missing (unreachable)`, distinct from `Missing (no
   code)`.
6. **Don't fix anything.** If something's broken, that's the finding. Note
   any test data you create (prefix names/references with `FRAUDIT-`) so
   it's identifiable and cleanable later.
7. **Don't consult `bugs/INDEX.md`, `MASTER_ISSUE_REGISTER.md`, or
   `UX_AUDIT_FINDINGS.md` until you finish your own pass.** Cross-reference
   at the very end only, to (a) avoid re-filing an exact duplicate under a
   new ID and (b) flag anything those registers marked "Resolved" that your
   live testing shows is actually still broken (that's a high-value finding
   — a false "fixed" claim). During testing, work from the PRD checklist
   below with fresh eyes.
8. **Work module by module, write findings incrementally**, not all at the
   end. This is a large surface (~150+ discrete FRs) — treat it like the
   Wave-based process already used in this repo (see
   `docs/reviews/MASTER_ISSUE_REGISTER.md`): checkpoint after each module so
   a session that runs out of budget still leaves a usable partial result.
9. **IDs are permanent.** Once you assign `FR-001`, never reuse or delete it
   even if later shown to be a false positive — mark it `Invalid` with the
   reason and move on, matching this repo's existing append-only convention.

## What counts as an FR bug

- **Missing**: PRD/phase-doc says this exists; no reachable implementation.
- **Broken**: reachable, but errors, crashes, or silently no-ops.
- **Partial**: works for the common case but a stated sub-requirement is
  absent (e.g. "Sales Return" exists but only ever returns the invoice's
  first line item — the requirement is returns, not first-line returns).
- **Wrong**: produces a result, but the result contradicts the spec (wrong
  GST math, stock updates the wrong direction, ledger posts to the wrong
  party).
- **Inconsistent**: the same requirement is met on one twin path and not
  another (Sales works, Purchases' equivalent doesn't — this codebase has a
  known pattern of duplicated Sales/Purchases logic drifting apart).
- **Sequence-violated**: the workflow chain doesn't enforce the order the
  PRD specifies (e.g. an invoice can be created without ever validating
  stock, or a draft's number is burned before the PRD's implied "on
  complete" point).
- **Sync-violated**: an action in the Automatic Synchronization matrix does
  not produce its specified side effect, or produces an *extra* untriggered
  one.
- **docs-vs-reality**: a planning doc (phase doc, README, `MVP_IMPLEMENTATION_PLAN.md`) asserts an FR is done/locked and live testing shows otherwise.

## Severity

Use the same scale as the rest of this repo's audits for comparability:

- **Critical** — blocks a core business task, causes data loss, or posts
  wrong money/tax/stock silently (no error shown).
- **High** — the FR fails but a workaround exists, or it fails only for a
  specific role/module/edge case that's still commonly hit.
- **Medium** — FR is partially met; annoying or limiting but not blocking.
- **Low** — minor deviation from spec with no real business impact.
- **Cosmetic** — spec technically unmet but purely a wording/labeling gap.

## FR checklist (appendix)

The full PRD text is long; below is the FR inventory extracted from it,
grouped by module with a stable ID prefix. Use this as your master
checklist — **give every row a verdict** (`Met` / `Partial` / `Missing` /
`Broken` / `Deferred-confirmed` / `N/A-not-in-scope`), and file a full bug
entry (see Report format) for every verdict other than `Met` or a
correctly-confirmed `Deferred`.

> Numbering is `FR-<prefix>-<n>`, e.g. `FR-SL-04`. Prefixes: `CO` Company &
> Settings · `MD` Master Data · `SL` Sales · `PU` Purchases · `IN` Inventory
> · `MF` Manufacturing · `AC` Accounting · `GST` GST & Compliance · `PAY`
> Payments · `RPT` Reports & Dashboard · `NOT` Notifications & Automation ·
> `IE` Import/Export · `INT` Integrations · `ADM` Administration · `SYNC`
> Automatic Synchronization · `SUB` Subscription/plan gating · `NFR`
> Non-functional.

### CO — Company & Settings (PRD §6.1)
Company profile, GST details, PAN, financial year, invoice series (per
document type), bank accounts, UPI QR, logo, branches, warehouses, tax
configuration, backup settings. For each: is it editable from Settings, does
it actually take effect on new documents (e.g. change invoice series prefix
→ next invoice reflects it), and is it company-scoped (not leaking/shared
across tenants)?

### MD — Master Data (PRD §6.2)
- Customer: profile, GSTIN (validated), address, contact, credit limit
  (enforced at billing time?), payment terms, outstanding balance (accurate
  vs actual ledger?), sales history (complete?).
- Supplier: profile, GSTIN, bank details, outstanding, purchase history.
- Product: SKU, barcode (scannable/lookup works), HSN/SAC, GST rate,
  category, brand, unit, purchase price, selling price, batch/serial,
  reorder level (triggers an alert?).
- Other masters: categories, brands, units, warehouses, tax rates, payment
  modes, expense categories — full CRUD, and referenced correctly by
  documents that use them.

### SL — Sales Management (PRD §7, MVP Flow 2)
- Documents: Quotation, Sales Order, Delivery Challan, GST Invoice, Retail
  Invoice, Sales Return, Credit Note — each creatable, editable pre-issue,
  locked/warned post-issue, and PDF-able.
- Workflow chain: Customer → Quotation → Sales Order → Delivery Challan →
  Invoice → Payment → Receipt → Ledger & Inventory update — test converting
  one document into the next, not just creating each in isolation.
- Features: GST billing, Non-GST billing, POS billing, barcode billing,
  discounts/offers (line-level and invoice-level), multiple price lists,
  customer credit (limit enforcement), QR payment, invoice templates
  (selectable, actually changes PDF), WhatsApp/Email/SMS sharing (does the
  share action actually complete, or just claim to?), print support
  (A4, thermal 58mm, 80mm).
- Auto invoice numbering: sequential, no gaps under normal use, doesn't
  regress on draft delete, per-series-configurable.
- Payment modes at billing: Cash, UPI, Card, Bank Transfer, Credit.

### PU — Purchase Management (PRD §8, MVP Flow 1)
- Documents: Purchase Order, Goods Receipt (GRN), Purchase Invoice, Purchase
  Return, Debit Note.
- Workflow chain: Supplier → Purchase Order → Goods Receipt → Purchase
  Invoice → Payment → Ledger & Inventory update.
- Features: supplier credit, purchase history, GST purchase (input tax
  calc), bulk purchase import (Excel — full Upload → Validate → Preview →
  Commit → Error-report cycle per the TRD's day-1 import spec), vendor price
  tracking, attach invoice PDF/image to a purchase record.
- Mirror every Sales FR test against its Purchase equivalent explicitly —
  this codebase has a documented pattern of the two forms drifting apart
  (e.g. invoice-number editability, discount modes fixed on one and not the
  other). Don't assume parity; verify it.

### IN — Inventory Management (PRD §9, MVP Flow 3)
Real-time stock, multi-warehouse (or single-warehouse if that's still the
locked scope — verify which), batch tracking, serial number tracking,
expiry management, stock transfer, stock adjustment, stock verification,
reorder alerts, low-stock alerts, negative-stock control (test the actual
policy: does it block, warn, or silently allow oversell — including under
**concurrent** requests, a documented prior race condition).

### MF — Manufacturing (PRD §10 — Professional plan / later phase)
BOM, production orders, raw-material consumption, finished goods, wastage
tracking, batch production, production costing. Confirm scope status first
(Step 0) — if the phase docs claim this is live, audit it fully; if it's
explicitly roadmap, confirm the app doesn't half-expose it (partially
working but unlisted screens are still a bug).

### AC — Accounting (PRD §11)
General ledger, cash book, bank book, journal entries, payment/receipt
vouchers, contra entries, expense/income management, P&L, Balance Sheet,
Trial Balance, Cash Flow, ledger reports, outstanding reports. **Cross-check
against the locked MVP doc's explicit claim that MVP accounting is
"derived ledgers only — no journal/P&L/Balance Sheet."** If those now exist
in the app (there's a live `accounting` app in the backend), that
contradicts the locked doc — verify which is true and log the discrepancy
either way (`docs-vs-reality` if the doc is stale, or `Broken`/`Missing` if
the feature exists but doesn't actually balance/reconcile).

### GST — GST & Compliance (PRD §12)
GST billing, GST calculation (CGST/SGST vs IGST split by place-of-supply,
rounding), HSN validation, GSTIN validation (checksum, not just format),
e-Invoice, e-Way Bill, GSTR-1, GSTR-3B, tax reports. Test both intra-state
and inter-state invoices, and at least one multi-rate-line invoice to check
rounding-residual distribution.

### PAY — Payments (PRD §13)
Customer collections, supplier payments, UPI/Cash/Bank Transfer/Cheque
recording, payment links, aging reports, automated payment reminders. Test
allocation: does a payment reduce the right invoice's outstanding, and does
over-allocation get rejected (including a concurrent-request race test)?

### RPT — Reports & Dashboard (PRD §14, MVP Flow 4)
- Dashboard KPIs: Sales Today, Monthly Revenue, Purchase Summary,
  Outstanding Receivables, Outstanding Payables, Cash & Bank Balance,
  Inventory Value, Low Stock Items, Top Products, Top Customers, GST
  Liability, Business Alerts — verify each number against a manually
  computed expectation from the underlying data, not just "a number
  renders."
- Reports: Sales Register, Customer/Product Sales, Profitability, Purchase
  Register, Supplier Analysis, Stock Summary/Ledger/Batch/Aging,
  Fast/Slow/Dead stock, Ledger, Trial Balance, P&L, Balance Sheet, Cash
  Flow, GSTR reports, Tax Summary. For each: filters actually filter, date
  ranges actually bound the data, and Export (PDF/Excel/CSV) produces a
  real, correct file — download it and open it.
- Pagination: any report/list expected to hold >1 page of data — confirm
  page 2+ is actually reachable and not silently dropped.

### NOT — Notifications & Automation (PRD §15)
Low stock alerts, payment due alerts, GST filing reminders, subscription
renewal, daily/monthly summaries, backup status, sync-failure alerts. For
each: does the triggering condition actually fire the notification (not
just "the model has a field for it")?

### IE — Import & Export (PRD §16)
Import: customers, suppliers, products, opening stock, opening balances —
each via the full validate/preview/commit/error-report cycle. Export:
Excel, CSV, PDF from wherever the PRD implies it (reports, invoices,
statements).

### INT — Integrations (PRD §17)
GSTN, e-Invoice, e-Way Bill, UPI, payment gateway, WhatsApp, Email, SMS,
barcode scanner, thermal/label printer, Tally import/export, public
APIs/webhooks. Most of these will be `N/A-not-in-scope` or stubbed by
design (confirm via Step 0) — but a stub that silently reports success
without doing anything (this codebase has a documented OTP-SMS example of
exactly this pattern) is a **Critical** finding, not an N/A.

### ADM — Administration (PRD §20)
User management, role & permissions (configurable per PRD §5 — test that
role changes actually take effect immediately, not just on next login),
branch management, warehouse management, audit logs (do sensitive actions
actually write an audit entry?), backup & restore, subscription/license
management, activity history.

### SYNC — Automatic Synchronization matrix (MVP section, "the heart of the system")
Treat each row as a separate, mandatory assertion. For each action, verify
the exact effect stated — not a plausible-looking effect:

| Action | Stock | Customer outstanding | Supplier outstanding | Reports/Dashboard updated |
|---|---|---|---|---|
| Purchase Invoice | ↑ Increase | — | ↑ Increase | Purchase register |
| Purchase Return | ↓ Decrease | — | ↓ Decrease | Purchase register |
| Sales Invoice | ↓ Decrease | ↑ Increase | — | Sales register |
| Sales Return | ↑ Increase | ↓ Decrease | — | Sales register |
| Payment Received | — | ↓ Decrease | — | Dashboard |
| Supplier Payment | — | — | ↓ Decrease | Dashboard |
| Stock Adjustment | ± Updated | — | — | Inventory reports |

For every row: perform the action once, then independently check (a) the
stock ledger/quantity, (b) the customer or supplier ledger balance, and (c)
that the relevant report/dashboard number moved — in one request, in the
correct direction, with no other row's column touched. Also test the
**cancel/void** path for each document type: does reversing it undo exactly
the original effect, or does it drift (double-reverse, partial reverse, or
no reverse at all)?

### SUB — Subscription plan gating (PRD §22)
Free / Starter / Professional / Enterprise feature boundaries (Multi-User,
Multi-Warehouse, Batch & Serial Tracking, Manufacturing, Multi-Company, API
Access, etc.). If plan gating exists in the app at all, verify it's actually
enforced server-side (not just hidden in the UI) — an unenforced gate is a
revenue-leak bug, not just a cosmetic one.

### NFR — Non-functional requirements (PRD §23, TRD §15)
These are measurable — don't eyeball them:
- Performance: app launch < 3s, invoice generation < 10s (TRD: invoice save
  < 2s, invoice PDF < 3s), search < 2s (TRD: < 500ms), dashboard < 2s, API
  response < 300ms. Use `read_network_requests` timings or curl `-w
  "%{time_total}"` for real numbers, not impressions.
- Security: HTTPS enforced in prod config, RBAC actually blocks (not just
  hides), audit trail exists and is tamper-evident, daily backups configured
  and verifiably running.
- Reliability: what happens when the network drops mid-save — does the UI
  recover, retry, or lose the entered data silently?
- Usability: can a first-time user complete "create and print a GST invoice"
  in well under 10 minutes with zero prior explanation?

## Report format

Write to **[`docs/reviews/FR_AUDIT_FINDINGS.md`]** (confirm location, or
propose your own). Append after each module — don't hold everything for one
final write. Start the file with the Step 0 scope map, then a running
summary, then full entries.

```markdown
# Functional Requirements Audit — Bizboard
Run date: [date] · Auditor: Claude (FR conformance pass) · Build: [git rev]

## Scope map (Step 0)
| PRD module | Status per docs | Verified live? |
|---|---|---|
| ... | Locked-MVP / Phase-N / Roadmap / Undocumented | Yes/No |

## Coverage summary
- FRs checked: N / [total in appendix]
- Verdicts: N Met, N Partial, N Missing, N Broken, N Deferred-confirmed, N N/A
- Findings logged: N Critical, N High, N Medium, N Low, N Cosmetic

## FR Coverage Matrix
| FR ID | Requirement (short) | Verdict | Finding ID (if not Met) |
|---|---|---|---|
| FR-SL-01 | Quotation document | Partial | FR-014 |

## Findings

### FR-001 — [short title]
- **FR reference:** FR-SL-04 — "Quotations" (PRD §7, MVP Flow 2 Functional Requirements)
- **Requirement text (quoted):** "..."
- **Module/Page:** Sales → Quotations
- **Verdict:** Missing | Broken | Partial | Wrong | Inconsistent | Sequence-violated | Sync-violated | docs-vs-reality
- **Severity:** Critical | High | Medium | Low | Cosmetic
- **Steps to reproduce:**
  1. ...
  2. ...
- **Expected (per PRD):** ...
- **Actual:** ...
- **Evidence:** screenshot / API response / DB query result
- **Role/viewport tested:** Owner, desktop
- **Cross-reference:** [only fill in at the end] duplicate of / confirms-still-broken BUG-nnn / BB-NNNNNN / UX-nnn, or "new"
```

Number findings sequentially `FR-001`, `FR-002`, ... across the whole run.
At the end, add:

1. **Top 15 most severe** — ordered by (severity × how core the flow is),
   matching the style of `bugs/INDEX.md`'s "15 most severe items."
2. **Cross-cutting themes** — root causes behind 3+ findings, if any.
3. **Cross-reference pass** — now read `bugs/INDEX.md`,
   `MASTER_ISSUE_REGISTER.md`, and any `UX_AUDIT_FINDINGS.md`, and fill in
   the `Cross-reference` line on every finding. Flag separately any case
   where a prior register marked something `Resolved`/`Fixed` but your live
   test shows it's still broken — that's a high-value "false green" finding,
   call it out explicitly at the top of the summary.

## Before you start

Confirm with me:
1. Which URL is actually running right now (dev server vs Docker).
2. Where to write the findings file.
3. Whether the non-Owner role accounts (Manager, Sales Staff, Inventory
   Staff, Accountant, Auditor) already exist, or should be created as part
   of the run.
4. Whether to run this as one continuous pass or split by module across
   parallel sessions/subagents (recommended once the module list is
   confirmed in scope — mirrors the Wave process already used in this repo
   for the code-level audits).

Then proceed module by module without stopping for approval between
modules — only stop if you hit something that needs a real decision (a flow
that would send a real SMS/email/payment/webhook), or a module's scope
status from Step 0 is genuinely ambiguous even after checking the phase
docs and the live nav.
