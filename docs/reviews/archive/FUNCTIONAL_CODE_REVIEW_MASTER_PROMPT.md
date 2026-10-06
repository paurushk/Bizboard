# Master Prompt — Functional Code Review for Production Stabilization

> Paste everything below the line into a fresh Claude Code (or equivalent
> agent) session that has **read access to the whole repo** and can run the
> backend test suite. Browser access is optional but helpful. Fill in the
> bracketed values first. This is a **code-level** review — for "does the
> running app do what the PRD says" use `FR_AUDIT_MASTER_PROMPT.md`; for
> ordinary-user UX use `UX_AUDIT_MASTER_PROMPT.md`. Do not repeat their work.

---

## Role & mission

You are a **senior engineer doing a release-blocking code review** of
Bizboard before it goes to its first paying users. The product is a
cloud GST billing / business-management system for Indian retailers and
small traders (Django 5 + DRF backend, React 18 + MUI + TanStack Query
frontend, Capacitor Android shell, PWA offline outbox).

Your job: **read the code that implements the real money-moving,
stock-moving, tax-calculating features and find everything that will bite a
real user** — bugs, silent data corruption, half-built features, missing
validation, broken edge cases, race conditions, and cross-tenant leaks.
Completeness beats speed. A "probably fine" is not a verdict.

**In scope (priority order):**

1. **POS** — `backend/sales/*` retail-invoice path, `web/src/pages/pos/*`.
   Create retail invoice → complete → record cash/UPI receipt → thermal
   PDF. Offline draft outbox + idempotency.
2. **Sales** — quotation → sales order → delivery challan → invoice →
   receipt/allocation → sales return → credit/debit note. `backend/sales/`,
   `web/src/pages/sales/`.
3. **Purchase** — bill/PO → complete (posts stock + AP atomically, no
   separate GRN) → purchase return → debit/credit note → bill import / BoE
   import. `backend/purchases/`, `web/src/pages/purchases/`.
4. **Stock & Godown** — typed append-only movements, stock balances,
   warehouses/godowns, transfer, adjustment, stock count, serial/batch,
   expiry, low-stock, negative-stock policy, offline stock, godown conflict
   resolution. `backend/inventory/`, `web/src/pages/inventory/`.
5. **Reporting** — dashboard KPIs, sales/purchase registers, stock
   summary/ledger/aging, GST worksheets (GSTR-1/2B/3B/9 aids — offline, not
   filing). `backend/reporting/`, `backend/accounting/reports.py`,
   `web/src/pages/reports/`.
6. **Accounting** — derived ledgers, GL / dual-ledger, period gates,
   cess GL, TCS/TDS, vouchers. `backend/accounting/`, `backend/ledgers/`.

**Out of scope (note if broken, don't deep-review):** Manufacturing,
Payroll, CRM, AI insights, WhatsApp Cloud, AA banking, live NIC e-invoice —
all dark/preview by design. Auth/tenancy/RLS plumbing only where it touches
the flows above.

## Architecture invariants (from `README.md` — treat violations as findings)

- Completed business documents are the **source of truth**. There are **no
  customer/supplier ledger tables** — balances are derived from documents,
  returns, and payment allocations. A finding: any code that caches a
  balance and can drift, or writes a "ledger row" that a later document
  edit won't reconcile.
- **Stock movements are typed and append-only.** A finding: any path that
  mutates or deletes a `StockMovement`, or updates `StockBalance` without a
  corresponding movement.
- **Document completion and inventory effects are atomic.** A finding: a
  completion path where stock posts, ledger posts, document-number
  assignment, and status change are not all inside one
  `transaction.atomic()` with the right `select_for_update()` / `on_commit`
  ordering.
- **Every business query is scoped to `company_id`.** A finding: any
  queryset in the in-scope apps (`.objects.filter(...)`, `get_object_or_404`,
  serializer `queryset=`, `.get(pk=...)`) that is not constrained to the
  request's company. Check nested writes and `PrimaryKeyRelatedField`
  especially — they bypass viewset `get_queryset`.
- Advanced surfaces are gated by feature flags — an **inconsistent** gate
  (visible in nav but 403s, or hidden but route+API fully live) is a
  finding.

## Known fault patterns in this codebase (check whether each still holds)

The repo's own prior audits (`docs/reviews/`, `bugs/`) repeatedly found:

- **Sales/Purchase logic drift** — the two sides duplicate similar code
  (totals, discount modes, invoice-number editability, return handling) and
  diverge. For every Sales finding, check the Purchase twin and vice versa.
- **Race conditions** on stock deduction and payment/receipt allocation —
  two concurrent completes overselling stock, or over-allocating a payment
  past the invoice total. Verify `select_for_update()` covers the rows the
  check reads, and the check-then-write isn't split across transactions.
- **Idempotency gaps** — `core/idempotency.py` `MONEY_IDEMPOTENCY_SCOPES`
  is matched by exact scope string; a view passing a scope name not in the
  set silently gets no protection. Cross-check every `scope="..."` literal
  in the in-scope views against that set.
- **Stub integrations that report success without doing anything** (the
  OTP-SMS pattern). Any external call in the flows that returns a fake OK is
  a **Critical**, not an N/A.
- **Decimal handling** — quantity column is 3dp, money 2dp; validators
  (`MinValueValidator`) don't run on `bulk_create` / `.save()` without
  `full_clean()`. Look for unquantized arithmetic, float coercion, rounding
  applied per-line vs per-invoice, and rounding-residual distribution across
  multi-rate lines.
- **Draft document numbering** — numbers burned on draft create/delete
  instead of on complete; gaps; per-series config not honored; races on the
  sequence.
- **Offline outbox** (`web/src/offline/invoiceDraftCache.ts`) — same
  idempotency key must be reused on replay; a flush that generates a new key
  or double-submits is a finding. Sign-out must wipe plaintext drafts.

## How to work

1. **Trace flows, not files.** For each in-scope module pick the core
   write path (e.g. `POST .../invoices/{id}/complete`) and read every layer
   it touches: view → serializer → service → model `save`/signals →
   inventory service → ledger service → events/tasks → `on_commit` hooks.
   Draw the transaction boundary. Note every queryset and every Decimal op
   along the way.
2. **Golden path + abuse path** for every write: zero/negative/huge
   quantity, duplicate submit (same idempotency key and a fresh one),
   two concurrent requests on the same document, editing a completed
   document, completing an already-completed document, cross-company id in
   the payload, a role that shouldn't be allowed.
3. **Reversal paths.** For every document type, read the cancel/void/return
   path and confirm it undoes *exactly* the original stock + ledger effect —
   no double-reverse, partial reverse, or no-op. Returns and credit/debit
   notes especially.
4. **Reports = correctness, not rendering.** For each report/KPI, read the
   aggregation query and confirm: it's company-scoped, date filters bound
   the data, it matches the documents-as-source-of-truth model (not a stale
   cache), pagination doesn't silently drop rows, and Decimal sums don't
   lose the rounding residual. Flag any report that recomputes tax/COGS with
   logic that differs from the write path.
5. **Run the tests.** `cd backend && pytest` (Python 3.12). Note failures,
   skips, and `xfail`. If a flow you're reviewing has thin coverage, that
   gap is itself a Medium finding — name the missing test.
6. **Don't fix anything.** Every problem is a finding. Don't refactor.
7. **Checkpoint per module.** Write findings to the file incrementally so a
   session that runs out of budget still leaves a usable partial result.

## What counts as a finding

- **Bug** — code produces a wrong result, crashes, or silently no-ops on a
  realistic input.
- **Data-integrity risk** — a path that can corrupt stock, ledger balance,
  tax totals, or document numbering (drift, orphan, double-post,
  non-atomic partial write).
- **Cross-tenant** — any queryset or nested write not scoped to the request
  company. Always **Critical**.
- **Race condition** — check-then-act without the lock covering the checked
  rows; concurrent requests can violate an invariant (oversell, over-
  allocate, duplicate number).
- **Broken / half-built feature** — reachable code that errors, is wired to
  the wrong endpoint, or implements only part of its stated behavior.
- **Missing validation** — server accepts input it should reject (negative
  qty, complete without stock, allocation > outstanding, invalid GSTIN
  checksum, place-of-supply mismatch, closed-period post).
- **Sales/Purchase inconsistency** — an invariant enforced on one side and
  not its twin.
- **Silent failure** — errors swallowed, `except: pass`, a task that fails
  without surfacing, an integration stub returning fake success.
- **Improvement** (lower priority, still log) — N+1 on a hot list/report,
  missing DB index on a filtered column, a migration that will lock a big
  table, unbounded query, missing `select_related`/`prefetch_related`.

Not a finding: pure style, naming, formatting, speculative "could one day",
or anything already correctly gated as dark/preview.

## Severity (same scale as the rest of this repo's audits)

- **Critical** — blocks a core business task, loses data, or silently posts
  wrong money / tax / stock. Cross-tenant leak. Any concurrent-safe
  invariant that's actually violable.
- **High** — feature fails but a workaround exists, or it fails only for a
  specific role / module / edge case that's still commonly hit.
- **Medium** — partial implementation, missing validation with limited
  blast radius, thin/absent test coverage on a money path, N+1 on a hot
  path.
- **Low** — minor deviation, defensive gap, non-hot-path inefficiency.

## Per-module code-review checklist

### POS (`backend/sales/`, `web/src/pages/pos/`)
- The create → complete → receipt → PDF sequence: is it one server
  transaction or several round-trips that can half-succeed (invoice
  completed, receipt lost)? What does the client do if step 3 fails?
- Idempotency key: generated once per sale and reused on retry? Reused
  across the invoice-complete *and* the receipt, or a fresh one per call
  (double receipt on replay)?
- Cash/UPI receipt: does it allocate to the invoice atomically? Rounding
  of tendered vs invoice total? Change/overpayment handling.
- Offline: draft created offline, then flushed — does it dedupe against a
  sale the server already recorded? Stock check happens server-side at
  flush, not just at draft time?
- Thermal PDF "when available" — what happens when it isn't? Silent skip or
  surfaced?
- Negative stock at the counter under two terminals selling the last unit.

### Sales (`backend/sales/`, `web/src/pages/sales/`)
- `sales/services.py` `_validate_lines` and totals: per-line vs per-invoice
  rounding, discount modes (amount vs percent, line vs document), GST rate
  whitelist, `full_clean` not run on bulk paths.
- Document chain conversions (quotation→SO→DC→invoice): quantities and
  prices carried correctly, partial conversion, converting the same source
  twice, editing the source after conversion.
- Invoice complete: `transaction.atomic` boundary vs stock post vs ledger
  post vs `DocumentNumberService` vs status change vs `emit`/`on_commit`.
  What's outside the transaction?
- Place of supply / intra vs inter-state split, export/SEZ, RCM memo,
  stamped-GSTIN recompute (`recompute_totals_for_stamped_gstin`).
- Sales return / credit note: reverses exact stock + exact customer
  outstanding; can't return more than sold net of prior returns; COGS
  reversal (`cogs_service.py`).
- IRN guard (`irn_guard.py`) — can a completed/IRN'd invoice still be
  edited or voided in a way that desyncs from the (sandbox) e-invoice state?
- Receipts / allocations: over-allocation past invoice outstanding under
  concurrency; allocation to a cancelled invoice; unallocated advance
  handling.
- Recurring invoices (`recurring.py`) — catch-up on missed runs, dedupe,
  timezone of the schedule.

### Purchase (`backend/purchases/`, `web/src/pages/purchases/`)
- "Complete posts stock + AP together" — same atomicity audit as sales
  invoice complete. Twin-check every sales finding here.
- Bill import & BoE import (`boe_services.py`): validate→preview→commit
  cycle, partial commit on row error, re-commit of the same file, ITC gating
  on GSTR-2B / ICEGATE reconciliation, `purchase_type` / RCM inference.
- Purchase return / debit note: exact reversal, can't return more than
  received.
- Supplier payment: allocation correctness, concurrency, payment to wrong
  supplier via unscoped id.
- Landed cost / unit cost feeding inventory cost layers — see stock below.

### Stock & Godown (`backend/inventory/`, `web/src/pages/inventory/`)
- `InventoryService.post_movement` / `default_warehouse` — the
  `IntegrityError` fallbacks: can two concurrent callers create two
  "DEFAULT" warehouses or two `is_default=True` rows? Is the unique
  constraint actually there?
- `StockBalance` update vs `StockMovement` insert — same transaction, row
  locked? Can a balance go out of sync with the sum of movements? Is there a
  reconciliation/checksum anywhere?
- Negative-stock policy: block / warn / allow — is it consistent across
  invoice complete, POS, stock transfer, adjustment? Enforced under
  concurrency (two requests both see qty=1)?
- Stock transfer: two-sided movement atomic; in-transit state; transfer to
  same godown; transfer more than on hand.
- Stock adjustment / stock count: post creates movements with correct sign;
  count variance posting; recount after post; closed-period guard.
- Batch/serial: serial double-sale, serial on return re-enters stock,
  batch expiry blocks sale, FIFO/near-expiry selection.
- Godown conflict resolution (`web/src/pages/inventory/godownConflict.ts`,
  `StockConflictModal.tsx`) — offline stock edited on two devices: does the
  merge preserve movement history or clobber it?
- Cost layers (`InventoryCostLayer`, `InventoryRunningCost`) — layer
  consumed correctly on sale, replenished on return, valuation snapshot
  matches layer sum.

### Reporting (`backend/reporting/`, `backend/accounting/reports.py`)
- Every aggregation: company-scoped, date-bounded, excludes drafts/cancelled
  per spec, no N+1, pagination complete.
- Dashboard KPIs (`web/src/pages/DashboardPage.tsx` + backend) — each number
  recomputable by hand from documents; outstanding receivables/payables
  match the derived-ledger definition exactly.
- Stock summary/ledger/aging — matches `sum(StockMovement)` not a cache.
- GST worksheets (`gst_returns*.py`, `gstr2b.py`, `ims*.py`) — section
  totals reconcile to the invoices they summarize; rounding; period
  boundaries; amendments/returns reflected.
- Any report recomputing tax or COGS with logic that differs from the write
  path — flag the divergence.
- Export (PDF/Excel/CSV) — correct data, not just a file; large export
  streaming vs loading all rows in memory.

### Accounting (`backend/accounting/`, `backend/ledgers/`)
- Derived-ledger claim vs the live `accounting` app with GL — if journals
  exist, do they balance, and do they stay reconciled when a source
  document is edited/voided?
- Period gates — a post dated into a closed period is rejected everywhere
  (invoice, purchase, adjustment, voucher), not just in one place.
- Cess GL, TCS/TDS (`tcs_sales_gl_206c`, `tds_worksheets.py`) — explicit
  amount overrides rate (per repo decision); both provided + calculated
  logged.
- Contra / voucher entries — double-entry integrity, company scope.
- Dual-ledger — the two ledgers can't silently diverge.

## Cross-cutting checklist (apply to all in-scope apps)

- **Permissions** — every viewset/action has an explicit permission class;
  object-level checks for detail routes; a non-owner role gets a real API
  403, not just a hidden button.
- **`transaction.atomic` correctness** — boundary covers all related
  writes; `select_for_update` covers every row a business check reads;
  side effects (emails, tasks, events, PDF) are on `transaction.on_commit`,
  not fired mid-transaction.
- **Idempotency** — every money/stock-creating POST is in
  `MONEY_IDEMPOTENCY_SCOPES` with a matching scope string; replay returns
  the stored response, doesn't re-execute.
- **Decimal** — `Decimal` end-to-end, explicit `quantize`, no `float`, no
  `round()` on money, consistent rounding rule, residual distributed once.
- **Migrations** — reversible; data migrations chunked; no `AddField` with
  a non-null default on a large table without a plan; new filtered columns
  have indexes.
- **N+1 / unbounded** — list and report endpoints use
  `select_related`/`prefetch_related`; no `.count()` + loop; no
  `list(qs)` of an unbounded table.
- **Error handling** — no bare `except`, no swallowed exceptions on a write
  path; failed Celery tasks surface somewhere; client shows a real error,
  not a success toast, when the API 4xx/5xxs.
- **Frontend** — TanStack Query mutations invalidate the right keys after a
  write; optimistic updates roll back on error; forms disable submit while
  pending (double-submit); zod schema matches server validation; money
  formatted with a Decimal-safe helper, not `toFixed` on a float.

## Report format

Write to **[`docs/reviews/FUNCTIONAL_CODE_REVIEW_FINDINGS.md`]** (confirm or
propose). Append after each module. Start with a summary, then a coverage
matrix, then full entries.

```markdown
# Functional Code Review — Bizboard (production stabilization)
Run date: [date] · Reviewer: Claude · Build: [git rev]

## Coverage summary
- Modules reviewed: [n/6] — POS, Sales, Purchase, Stock/Godown, Reporting, Accounting
- Findings: N Critical, N High, N Medium, N Low
- Test suite: [pass/fail counts, notable skips/xfails]

## Coverage matrix
| Module | Core write path reviewed | Reversal path | Concurrency | Tests present | Findings |
|---|---|---|---|---|---|
| POS | POST /invoices/{id}/complete + receipt | ... | ... | thin | CR-003, CR-004 |

## Findings

### CR-001 — [short title]
- **Module:** Sales → invoice complete
- **Location:** `backend/sales/services.py:LNN` (function `complete_invoice`)
- **Type:** Bug | Data-integrity | Cross-tenant | Race | Broken-feature | Missing-validation | Sales/Purchase-inconsistency | Silent-failure | Improvement
- **Severity:** Critical | High | Medium | Low
- **What's wrong:** ...
- **Trigger / repro:** concrete inputs or sequence (two concurrent requests with qty=1, payload with `customer` id from another company, ...)
- **Consequence:** wrong stock / double receipt / cross-tenant read / crash / ...
- **Code evidence:** the specific lines and why they're wrong (transaction boundary, missing filter, unquantized op)
- **Suggested fix direction:** one or two sentences — not a patch
- **Test to add:** the assertion that would have caught this
- **Twin check:** the Purchase/Sales equivalent — same bug? (y/n/n-a)
```

Number findings `CR-001`, `CR-002`, … sequentially across the whole run.
IDs are permanent and append-only — a later false positive is marked
`Invalid` with a reason, never deleted or renumbered.

At the end add:
1. **Top 10 must-fix-before-launch** — ordered by severity × how core the
   flow is.
2. **Cross-cutting themes** — root causes behind 3+ findings.
3. **Cross-reference pass** — only now, read `bugs/INDEX.md`,
   `docs/reviews/MASTER_ISSUE_REGISTER.md`, and the recent
   `DEEP_CODE_REVIEW_*` / `FIX_PLAN_*` docs. Mark each finding new /
   duplicate-of / **confirms-still-broken** (a prior "Resolved" that your
   read shows is still wrong — call these out at the top, they're the
   highest-value result).

## Before you start, confirm with me

1. Where to write the findings file.
2. Python version / how to run the backend suite (memory says 3.12,
   CI-pinned; local `.venv` may need rebuild).
3. Whether to run as one pass or split the 6 modules across parallel
   subagents (recommended — mirrors the Wave process already used here).
4. Any module you want dropped or added to the priority list.

Then proceed module by module without stopping between modules — only stop
for a real decision (a flow that would call a real external
SMS/email/payment/GSTN endpoint from a test) or genuine scope ambiguity.
