# Money Hub: one screen for Money In and Money Out

**Date:** 2026-10-14
**Status:** BUILT (2026-10-14), uncommitted. Decisions D-1, D-2, D-4, D-9 and scope are in section 3.0; the implementation record, deviations and what people still have to do are in section 15.
**Trigger:** the owner finds Money In confusing and incomplete: it shows money already received but not what is still owed, what is stuck (cheques, unmatched bank credits), or what is coming. Money Out is thinner still.
**Builds on:** Money In Phase 2 ([`MONEY_IN_PHASE2_IMPLEMENTATION_PLAN.md`](MONEY_IN_PHASE2_IMPLEMENTATION_PLAN.md), built, uncommitted) and the Q-OS backlog.

---

## 1. Problem, in the code

### 1.1 What the owner sees today

| Place | Shows | Does not show |
|---|---|---|
| Sales > Receipts ([ReceiptsPage.tsx](../../web/src/pages/sales/ReceiptsPage.tsx)) | Collected, Allocated, Advance, Cheques pending, Refunded. All follow the list filters ([payments/views.py `summary`](../../backend/payments/views.py)). | Anything still owed. |
| Payments > Collections ([CollectionsWorklistPage.tsx](../../web/src/pages/CollectionsWorklistPage.tsx)) | Four ageing cohorts, open invoices, promises. Hidden unless the role can view financial reports. | Receipts, advances, cheques, TDS. |
| Reports > TDS receivable | TDS deducted by customers, awaiting certificate. | Its link to the receipts that created it. |
| Dashboard / Customer 360 | Receivables, ageing, uncleared cheques, cash position. | Payables detail, bank-unmatched, supplier side beyond one number. |
| Purchases > Supplier payments ([SupplierPaymentsPage.tsx](../../web/src/pages/purchases/SupplierPaymentsPage.tsx)) | A list and a create dialog. | **No summary of any kind.** |

Money is also split across the Sales menu (Receipts) and the Payments menu (Collections, Links, Cash book, Bank reconciliation). There is no Money Out equivalent of Collections.

### 1.2 Defects found while reading the money code

These are real inconsistencies that the hub would surface to the owner. They must be fixed or explicitly handled first (WP-0). Each is marked **verify** where the code reading needs a test to confirm it before changing anything.

| # | Finding | Where | Effect on the hub |
|---|---|---|---|
| **P-1** | `cash_totals` counts every `POSTED` non-CREDIT receipt as inflow, including **cheques still pending clearance** and cheques that later **bounced** (a bounce sets `cheque_status`, not `status`). The opening-balance code in `_cash_opening_balance` does filter to cleared cheques. The two disagree. **Verify.** | [reporting/services.py:1107](../../backend/reporting/services.py) vs `:1091` | "Cash and bank now" would be overstated. |
| **P-2** | Supplier side has **no document-basis helper for unallocated supplier payments** (advances paid). `supplier_outstanding` subtracts only allocated payments, while GL has account 1250 "Supplier Advances". A supplier paid in advance shows full payable. **Verify.** | [ledgers/services.py:856](../../backend/ledgers/services.py), [accounting/services.py:1627](../../backend/accounting/services.py) | Payables overstated; no "advances paid" tile possible. |
| **P-3** | Two definitions of company payables: `LedgerService.company_payables` (floored per party, GL-capable) and `ReportService._company_payables` / `payables_aging` (document basis, used by the dashboard). Receivables has the same pair. | [ledgers/services.py:643](../../backend/ledgers/services.py), [reporting/services.py:278](../../backend/reporting/services.py) | The hub must use exactly one. Decision D-2. |
| **P-4** | `outstanding_basis` can switch customer outstanding to GL (`_use_gl_outstanding`) while supplier outstanding is always document basis. | [ledgers/services.py:357](../../backend/ledgers/services.py) | Receivable and payable on the same page could be on different bases. Must be shown, not hidden. |
| **P-5** | Collections worklist: the predictive worklist query is gated by `ENABLE_PREDICTIVE_DUNNING`, the open-invoice query is not. Two code paths feed one screen. | CollectionsWorklistPage.tsx:56 | Hub must read open invoices, not the predictive list. |
| **P-6** | Receipts summary "Advance" changes when the user filters by month or mode, so it can never be used as a position. | `ReceiptViewSet.summary` | Hub gets its own, unfiltered endpoint. The receipts strip is relabelled "for this filter". |
| **P-7** | Customer unapplied advance, supplier advance, and per-party floors mean `sum(party) != control account` when any party is in credit (documented in R2-018 / B1-027). | ledgers/services.py:643-670 | Tiles are floored; a tie-out footer shows the unfloored GL figure and the difference. |

---

## 2. Principles

1. **One screen to see everything; existing screens to act.** The hub never duplicates an editing workflow. It reads, links, and shows what changed afterwards.
2. **Every number has one owner function.** The hub calls existing services; it computes nothing new except where P-2 forces a new helper. Each tile's source is named in section 5.
3. **A tile equals its list.** Clicking a tile opens a list whose own total equals the tile amount, same filter, same basis. Enforced by a tie-out test per tile.
4. **Closed loop.** Every item the hub surfaces has: a way to open it, a way to resolve it, a visible change on the hub after resolving, and an audit trail. Section 7 is the matrix.
5. **Truth over reassurance.** If a figure is on a different basis, is partial, or failed to load, the tile says so. A failed tile never shows zero.
6. **Additive.** No migration is needed for Phase A. No existing endpoint changes shape; the dashboard keeps its fields until the hub is proven.
7. **Server first.** Permission, tenant scope and basis are decided on the server; the UI only renders.

---

## 3. Decisions

### 3.0 Decision record (owner, 2026-10-14)

| ID | Decision | Consequence for this plan |
|---|---|---|
| **D-1** | **Top-level "Money" menu**, children: Receipts, Collections, Payment links, Supplier payments, Bank reconciliation, Cash book, TDS receivable. Routes unchanged. | WP-4 restructures the menu; role-by-role nav test required. |
| **D-2** | **GL basis where configured** (not the recommended default). Receivable follows `outstanding_basis` (GL when books are on and `GL_WHEN_BOOKS` and back-fill is ready; documents otherwise). | See 3.1: payables are document-basis only today, so the two sides can differ in basis. WP-0 must resolve this. |
| **D-3** | Unchanged default: owner and `can_view_financial_reports` see company totals. | |
| **D-4** | **Cleared money only** for cash and bank; pending cheques shown beside it. | P-1 fix is mandatory in WP-0; dashboard and Cash Book cash may drop (12.3). |
| **D-9** | **Payables and advances paid shown side by side**, not netted, until the CA confirms. | `supplier_outstanding` is not changed. |
| **Scope** | **Phase A and Phase B in the first release**: 30-day due-date outlook (D-5) and statutory dues row (D-6) are included. | WP-6 and WP-7 are now release-blocking, not optional. WP-7 needs CA wording sign-off before release. |
| **D-5, D-6** | Both **in**, per the scope decision. | Reuse insights cashflow only if its basis matches; otherwise a separate, clearly labelled "by due date" view. |
| **D-7, D-8** | Unchanged defaults: dashboard keeps its tiles and links to the hub; no mobile work. | |

### 3.1 Open consequence of D-2 (GL basis) that needs a follow-up answer

* The company-wide payable total (`bulk_supplier_outstanding`) follows the same GL rule as the receivable total, so the two sides of the hub share one basis. `LedgerService.supplier_outstanding` (one supplier, used by the supplier ledger) is always from bills, even when books are on, so a single supplier's balance can differ from that supplier's share of a GL-basis total. (Checked in WP-1; the original plan text said the whole payable side was document-only.)
* **Plan handling:** each side carries a `basis` label (`GL` or `DOCUMENTS`) in the API and a visible badge on the tile. The net position line shows the basis of each side. The reconciliation footer shows the difference between GL and documents for both sides whichever basis is used.
* **Question for later (does not block WP-0):** should payables also move to GL when books are on, for symmetry? That changes supplier balances on the supplier ledger, statements and credit checks, so it needs its own plan and CA review. Until then payables stay document basis.
* **Extra tests:** books on with GL ready, books on with GL not ready (falls back to documents and the badge says so), books off. Receivable equals Customer 360 total in all three.

### 3.2 Original options (kept for reference)

| ID | Question | Recommended default | If decided otherwise |
|---|---|---|---|
| **D-1** | Name and place. | Top-level menu item **Money**, first under Dashboard. Receipts, Collections, Payment links, Supplier payments, Bank reconciliation, Cash book, TDS receivable become its children (routes unchanged, so no link breaks). | Keep current menus and add the hub as one extra item: lowest risk, but the split persists. |
| **D-2** | Basis for receivables and payables on the hub. | **Document basis for both** (what the dashboard and aging already use), with a footer line showing the GL control balance and the difference when books are on (P-7). | GL basis for customers when `outstanding_basis` says so: matches Customer 360 but then AR and AP differ in basis (P-4). |
| **D-3** | Who sees the hub. | Owner and any role with `can_view_financial_reports` see everything. Roles with only `can_create_payments` see the lists they already see but not company totals. | A separate permission is possible; I advise against a new flag. |
| **D-4** | Cash and bank "now". | Cleared money only: cleared cheques, cash, bank; pending cheques shown separately; per account list. Requires P-1 fixed. | Keep the current closing figure and label it "includes uncleared cheques". |
| **D-5** | 30-day outlook. | Phase B. "Due by date" view: open invoices by `due_date`, overridden by an open promise date; bills by supplier `due_date`. Labelled as **by due date, not a forecast**. Reuse the existing insights cashflow service if its basis matches; otherwise build separately. | Skip Phase B. The hub is still complete for "now". |
| **D-6** | Statutory dues (TDS payable, GST payable). | Phase B, as a read-only row linking to the existing worksheets and GST return pages. | Leave out; owner keeps using Reports. |
| **D-7** | Dashboard tiles. | Keep Receivables, Payables, Cash on the dashboard; make each link to the hub. Remove nothing. | Remove duplicates once the hub is trusted. |
| **D-8** | Mobile app. | Hub endpoint is built so mobile can adopt it; no mobile work in this plan. | Add a mobile WP. |

---

## 4. Definitions (glossary the UI and help must use)

Every tile has a one-line plain-language definition in its info popover (en + hi). Terms:

* **Receivable:** completed, unpaid or part-paid sales bills, less discount, TDS deducted and credit notes. Source `ReportService.receivables_aging`.
* **Overdue:** receivable whose due date is before today. Due date comes from the invoice, falling back to bill date plus payment terms (as the aging already does).
* **Advance received:** customer money not yet applied to any bill (CustomerReceipt unallocated, minus refunds). It is a liability to the customer, not income.
* **Cheques pending:** cheque receipts not yet cleared (`PENDING_CLEARANCE`). Not counted as cash.
* **Bounced:** cheques returned. Counted as money **not** received; the bill is open again.
* **TDS receivable:** tax a customer deducted before paying you, awaiting their certificate. An asset (account 1270).
* **Payable:** completed, unpaid or part-paid purchase bills, less notes and advance applied. Source `ReportService.payables_aging`.
* **Advance paid:** supplier payment not yet applied to a bill (to be built, P-2).
* **Cheques issued, not cleared:** supplier cheques with `cheque_status` pending. Cash has not left the bank yet.
* **Unmatched bank lines:** statement lines with `match_status = UNMATCHED`. Money moved that the books have not explained.
* **Promised:** open `PaymentPromise` records; broken promises are those past their date and not kept.

---

## 5. Architecture

### 5.1 Backend

New module `backend/reporting/money_position.py` (read-only, no models, no migration), exposed as:

```
GET /api/v1/money/position/            -> MoneyPosition
GET /api/v1/money/timeline/?days=30    -> Phase B
```

Permission: `CanViewFinancialReports` for company totals (D-3). Tenant: `self.company` as in all views; every query filters by company. `extend_schema` on both; OpenAPI snapshot and `openapi-types.ts` regenerated in the same change.

Response shape (Decimal strings, camelCase through the existing renderer):

```
asOf, basis: { receivable: "DOCUMENTS"|"GL", payable: "DOCUMENTS" },
net: { receivable, payable, net },
cash: { cleared, byAccount:[{id,name,balance}], chequesPendingIn, chequesIssuedPending },
moneyIn: {
  outstanding, overdue, dueNext7, ageing:{...buckets},
  advances, chequesPending, chequesBounced, tdsReceivable,
  promisesDue:{count,amount}, promisesBroken:{count,amount},
  unmatchedBankCredits:{count,amount}, gatewayAwaitingSettlement:{count,amount},
  paymentLinksOpen:{count,amount}
},
moneyOut: {
  outstanding, overdue, dueNext7, ageing:{...},
  advancesPaid, chequesIssuedPending, unmatchedBankDebits:{count,amount},
  tdsDeductedNotRemitted   // Phase B
},
reconciliation: { glReceivable, glPayable, differenceReceivable, differencePayable, note },
partial: ["unmatchedBankCredits"]     // names of sections that failed to compute
```

Rules:
* Each section is computed in its own `try`; a failure puts its name in `partial` and nulls it. The UI shows "could not load" for that tile only.
* Reuses: `receivables_aging`, `payables_aging`, `LedgerService.uncleared_cheque_total`, `bulk_customer_advances`, `cash_totals` (after P-1), `promise_to_pay.broken_promise_total / promises_due_today`, the TDS receivable report service, `BankStatementLine` counts, `PaymentLink` and `GatewayPayment` counts.
* New: `supplier_advances_total` (P-2), supplier cheque pending total, cleared cash by account.
* Performance: aggregate queries only, no per-row Python loops. Target under 400 ms on a company with 20k invoices; measured in the perf suite. A 30-second per-company cache, invalidated by the same signals that already refresh the dashboard, is added only if the measurement fails.

### 5.2 Frontend

* New page `web/src/pages/money/MoneyHubPage.tsx`, route `/money`, lazy-loaded, guarded like the Dashboard (`canViewFinancialReports`).
* Layout: net-position strip; two columns (Money In, Money Out); tie-out footer; "needs action" list. Phase B adds the 30-day band.
* Tiles are links with `aria-label` containing amount and count. No colour-only meaning (a11y gate).
* API in `web/src/api/legacy/money.ts`; types from the regenerated OpenAPI.
* i18n: every string in `en.ts` and `hi.ts`; the literal ratchet test stays green.
* Context help: add a `money` entry to `contextHelp` (route test in `contextHelp/routes.ts`).
* Responsive: single column below 900 px, tiles in a 2-up grid; no horizontal scroll.

---

## 6. Deep links: tiles must land on a matching list

Many target pages keep filters in component state, not in the URL, so a tile cannot open them filtered. Each needs URL-driven filters (read on mount, written on change) and a visible "Filtered from Money" chip with a one-click clear.

| Tile | Target | Filter required | Exists today? |
|---|---|---|---|
| Receivable / Overdue / Due in 7 days | Collections (`/payments/collections?cohort=`) | cohort or `due=overdue|7d` | Cohort is state only. **Add URL param.** |
| Receivable (all) | Sales history | `payment=unpaid` | **Verify**, add if absent. |
| Advances received | Receipts | `advance=1` | **Add** (backend filter on unallocated > 0). |
| Cheques pending / Bounced | Receipts | `mode=CHEQUE&cheque_status=` | `mode` exists; **add `cheque_status`.** |
| TDS receivable | `/reports/tds-receivable` | none | Exists. |
| Promises due / broken | Collections (promises block) | `promises=due|broken` | **Add.** |
| Unmatched bank credits/debits | Bank reconciliation | `match_status=UNMATCHED&direction=` | **Verify.** |
| Payment links open | Payment links | `status=` | **Verify.** |
| Payable / Overdue / Due in 7 days | Purchase history | `payment=unpaid|overdue` | **Verify**, add if absent. |
| Advances paid | Supplier payments | `advance=1` | **Add.** |
| Cheques issued pending | Supplier payments | `cheque_status=` | **Add.** |

Each added filter is a backend query param with `extend_schema`, an index check (no new full scans), and a test that the list total equals the tile.

---

## 7. Loop closure matrix: see, open, resolve, refresh, record

The owner is "in the loop" when an item moves from the hub, through resolution, and drops off the hub without a page reload, with a trace left behind.

| Item on hub | Open | Resolve action (existing screen) | Hub refresh | Record left |
|---|---|---|---|---|
| Overdue customer bill | Collections row | WhatsApp reminder, record receipt, record promise | Receipt, void and promise dialogs already invalidate receipt keys; **add `['money-position']`** | Receipt, promise, dunning log |
| Broken promise | Collections | Resolve or re-promise | invalidate | Promise resolved/reopened (exists) |
| Advance received | Receipts filtered | Apply to bills, or refund | invalidate in AllocationManager, BulkAllocate, RefundAdvance | Allocation / refund audit (exists) |
| Cheque pending | Receipts filtered | Mark cleared or bounced | invalidate in `chequeStatusMutation` | Cheque status change, bounce reversal (exists) |
| TDS receivable | TDS report | Mark certificate received (verify the action exists) | invalidate | TDS record |
| Unmatched bank credit | Bank reconciliation | Match to receipt, or create receipt from line | invalidate in recon match/create | Recon match record |
| Payment link open | Links | Mark sent, cancel; paid links auto-create receipt | webhook path: server only, hub reads fresh | Gateway record |
| Overdue supplier bill | Purchase history | Record supplier payment | invalidate in supplier payment mutation | Payment + allocation |
| Advance paid | Supplier payments | Apply to bill | invalidate | Allocation |
| Cheque issued pending | Supplier payments | Mark cleared / bounced | invalidate | Cheque status (exists) |
| Unmatched bank debit | Bank reconciliation | Match to supplier payment | invalidate | Recon match |

**Mechanics:** one shared helper `invalidateMoney(qc)` that invalidates `['money-position']`, `['receipts']`, `['receipts-summary']`, `['collections-open-invoices']`, `['collections-worklist']`, `['payment-promises']`, `['dashboard']`, `['sales-invoices-open']`. Every mutation in the table calls it. A test per mutation asserts the hub query is invalidated. Without this, the hub would show stale numbers after the user acts, which is the exact confusion this plan is meant to remove.

**Return path:** every deep-linked page shows a breadcrumb "Money > Receipts" and the filter chip, so the owner can go back and see the tile change.

**Attention feed:** `insights/alerts.py` and `attention` already compute overdue and broken-promise alerts. Alert links point to the hub filtered target, and the hub's "needs action" list reads the same underlying service, not a copy, so the two never disagree.

**Notifications and end of day:** the Morning page (`MorningPage.tsx`) links its money line to `/money`.

---

## 8. Cross-module impact

### 8.1 Modules that change

| Module | Change | Risk | Mitigation |
|---|---|---|---|
| `reporting` | New `money_position.py`, view, URL; P-1 fix in `cash_totals`. | P-1 changes dashboard cash and Cash Book closing. | Behaviour change listed in 12.3; test names the old behaviour; Cash Book and dashboard must agree after. |
| `ledgers` | New `supplier_advances_total` (P-2). May change `supplier_outstanding`. | Changes supplier balances everywhere (supplier ledger, statements, credit checks). | Do **not** change `supplier_outstanding` in Phase A; add the helper and show "advances paid" beside payables, not netted. Netting is decision D-9 (below), after CA input. |
| `payments` | Query params on receipts and bank lines; supplier payment list filters. | Added filters must keep org scoping and ordering. | Cross-tenant tests; index review. |
| `purchases` | Supplier payments/purchase history filters. | Low. | |
| `accounting` | Read only. Books-health already compares GL to documents. | Hub footer duplicates a books-health figure. | Call `BooksHealthService.control_balances`, do not recompute. |
| `insights` | Alerts/attention links retargeted; cashflow overlap (D-5). | Two cashflow views with different bases. | Reuse or label clearly. |
| `core` | Feature flag `ENABLE_MONEY_HUB` (default off until verified), permission reuse. | Flag registry has two lists (`feature_flags.py` lines ~41 and ~102); both must be updated. | Test that the flag appears in both. |
| `search` | Optional: index "Money" so global search finds it. | Low. | |

### 8.2 Modules that feed the hub (a change there changes the hub)

Sales invoices and returns, credit/debit notes (sales and purchase), customer receipts, supplier payments, allocations and reversals, POS shifts (cash receipts in a closed till), payment links and gateway webhooks, bank statements and reconciliation, promises to pay, TDS, opening balances (`is_opening_balance` invoices are in outstanding but must be flagged in the tile footnote), customer credit limit, e-invoice cancellation, GST. **Rule:** none of these may add their own copy of an outstanding or cash formula. A grep-based architecture test (like the existing status-semantics rule) fails the build if a new file defines its own "outstanding".

### 8.3 Web surfaces touched

AppShell and `navigation/menu.ts` (menu restructure, role visibility test), `App.tsx` (route), DashboardPage (tile links), Receipts, Collections, Purchase history, Supplier payments, Bank reconciliation, Payment links, TDS report (URL filters + chips), MorningPage, AttentionPage links, contextHelp, i18n, faq/help content, Customer 360 (link to hub filtered by customer is **out of scope**; noted for later).

### 8.4 Existing tests likely to need updates

Menu tests (role-by-role nav), `DashboardPage.test.tsx` (if links change), `CollectionsWorklistPage.test.tsx` (URL cohort), `ReceiptsPage.test.tsx` (URL filters), `literalRatchet.test.ts`, OpenAPI drift check in CI, `contextHelp` route coverage test, e2e golden specs under `e2e-golden/` (money-in golden).

---

## 9. Permissions, tenancy, safety

* Server enforces `CanViewFinancialReports`; a payments-only user gets 403 on `/money/position/` and the menu item is hidden (test per role: OWNER, MANAGER, ACCOUNTANT, SALES STAFF, VIEWER; remember the accountant-by-role gotcha in memory).
* Every query company-scoped; cross-tenant test with two companies and overlapping ids.
* Hub is read-only: no POST, no side effects, safe to retry. No idempotency needed.
* No customer or supplier personal data beyond names already shown in lists; "needs action" shows names only to roles that can already see those lists.
* Subscription gate: the hub is readable when writes are blocked (it is read-only).
* Audit: hub views are not audited; actions taken from the lists keep their own audit.

---

## 10. Work packages

Effort: S under 1 day, M 1 to 3, L 3 to 6, for one engineer including tests.

### Phase A: the hub for "now"

| WP | Content | Effort |
|---|---|---|
| **WP-0** | Verify P-1 and P-2 with failing tests first. Fix P-1 (`cash_totals` consistent with opening-balance rule). Add `supplier_advances_total`. Write the tie-out tests in section 11 (red). Decide D-2 and D-9. | M |
| **WP-1** | `money_position.py`, serializer, view, URL, flag `ENABLE_MONEY_HUB`, `extend_schema`, OpenAPI regenerate, partial-failure behaviour, perf test. | L |
| **WP-2** | URL-driven filters on the target lists (section 6): backend params plus frontend state-from-URL plus "from Money" chip plus breadcrumb. | L |
| **WP-3** | `MoneyHubPage`, tiles, columns, tie-out footer, "needs action" list, loading/empty/error/partial states, en + hi, a11y, responsive, context help. | L |
| **WP-4** | Menu restructure (D-1), role visibility, route guard, dashboard tile links, Morning/Attention links, `invalidateMoney` helper wired into every mutation in section 7. | M |
| **WP-5** | Receipts strip relabelled "for this filter"; Supplier payments gets a summary strip (payables, overdue, advances paid, cheques pending) from the same hub service filtered by supplier list filters. | M |

### Phase B: outlook and statutory (after D-5, D-6)

| WP | Content | Effort |
|---|---|---|
| **WP-6** | `/money/timeline/`, due-date based, promise override, supplier due dates; 30-day band and table; clear "by due date" label. | L |
| **WP-7** | Statutory dues row: TDS payable (supplier TDS deducted, not remitted), GST payable estimate linked to the existing pages. CA review before wording is final. | M |

### Phase C: assurance and rollout

| WP | Content | Effort |
|---|---|---|
| **WP-8** | Browser golden spec: create bill, partial receipt, cheque receipt, supplier bill, supplier payment, bounce a cheque, import bank line; assert the hub after each step. Postgres run of the tie-out and concurrency tests. | M |
| **WP-9** | Docs: FREEZE_SCOPE_COVERAGE line items, TESTING_STRATEGY entry, user help page + FAQ, plan record section, Hindi review list, CA checklist items. Flag on for pilot companies, then default on. | S |

**D-9 (raise during WP-0):** should payables be shown net of supplier advances paid? Default: no, show both, until the CA confirms and P-2 is verified against GL account 1250.

---

## 11. Test plan

**Backend**
1. **Tie-out per tile:** seed a company covering every state; assert hub amount equals the list sum for the same filter, for each tile in section 6.
2. **Foot test:** `net = receivable - payable`; hub receivable equals dashboard `receivables`; payable equals dashboard `payables`; cash equals Cash Book closing for the same date; all in one test so drift fails the build.
3. **Cheque states:** pending, cleared, bounced, then bounced after allocation; cash and receivable move correctly (P-1).
4. **Supplier advance:** pay without allocation, then allocate; advance tile and payable move (P-2).
5. **Basis:** books on/off, `outstanding_basis` both values; footer difference correct; unfloored GL figure equals `control_balances`.
6. **Opening-balance invoices, returned invoices, voided receipts, reversed allocations** in the seed.
7. **Permissions per role, cross-tenant, flag off returns 404.**
8. **Partial failure:** patch one section to raise; response is 200 with `partial` and the other sections intact.
9. **Query count and time budget** (`assertNumQueries` ceiling, perf marker).
10. **Architecture test:** no new "outstanding" formula outside `ledgers` and `reporting`.

**Frontend**
Tile rendering with every state (loading, error, partial, zero, large numbers, Indian grouping), link targets, role-based menu, URL filters round trip and clear, chip and breadcrumb, invalidation after each mutation in section 7, axe on the page, mobile width, Hindi strings present, literal ratchet.

**Golden (browser)** WP-8 above, using the local Chrome config from the Money In golden recipe.

**Gates:** `tsc -b` (not `tsc -p .`), eslint 0 errors, ruff, OpenAPI drift check, `qos-lint`.

---

## 12. Rollout, behaviour changes, risks

### 12.1 Rollout
Flag `ENABLE_MONEY_HUB` off, then on for the owner's company, then on by default after one week with no tie-out alarm. Old menu items remain reachable by URL throughout.

### 12.2 Reversal
Disable the flag; the menu returns to the old structure and the page is unreachable. No data was changed, so there is nothing to undo.

### 12.3 Behaviour changes to announce
* Dashboard and Cash Book **closing cash may drop** if pending or bounced cheques were counted (P-1). Release note and a test that names the old behaviour.
* Receipts KPI labels now say "for this filter".
* Menu structure changes for all users.

### 12.4 Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Hub numbers disagree with a screen the owner trusts | Medium | Foot tests, one owner function per number, reconciliation footer |
| P-1 fix alarms users when cash drops | Medium | Release note; show pending cheques beside cash |
| Working tree is large and uncommitted (Money In Phase 2, returns, notes) | High | Commit or branch the existing work first; this plan touches `payments/views.py`, `reporting/*`, `ledgers/*` which are already modified |
| Slow on large companies | Low | Aggregates only; perf test; cache only if needed |
| Supplier due dates missing on old bills | Medium | Fall back to bill date plus terms, show "no due date" count in the tile footnote |
| Scope creep into Money Out detail pages | Medium | Phase A links to existing pages and adds one summary strip only |

---

## 13. Reverse index: owner questions to where the hub answers them

| Owner asks | Answered by |
|---|---|
| How much do I have right now? | Cash cleared, by account, pending cheques apart |
| Who owes me and since when? | Receivable, ageing, overdue, then Collections |
| What have I been paid but not yet applied? | Advances received |
| What money is stuck? | Cheques pending, bounced, unmatched bank credits, gateway awaiting settlement |
| What tax is tied up with customers? | TDS receivable |
| What did people promise? | Promises due and broken |
| Whom must I pay, by when? | Payable, overdue, due in 7 days |
| Did I overpay anyone? | Advances paid |
| What cheques have I issued that are still out? | Cheques issued, not cleared |
| What's coming in and going out this month? | Phase B timeline |
| Do the books agree? | Reconciliation footer |
| What do I do next? | "Needs action" list, each row opens the right screen |

---

## 14. Open items to confirm during WP-0

1. P-1 and P-2 reproduced by tests (they are reading-based findings today).
2. Whether the TDS receivable page has a "certificate received" action (loop row for TDS).
3. Which target pages already accept URL filters (section 6 "verify" rows).
4. Whether `insights` cashflow can serve Phase B (D-5).
5. Supplier cheque flow: confirm `PENDING_CLEARANCE` is set for issued cheques.
6. Whether global search should index the Money page.


---

## 15. Implementation record (2026-10-14)

Everything in sections 10 and 11 is built. Nothing is committed (the working tree already held other uncommitted
work). Verified: 36 new backend tests, 511 existing backend tests in the touched areas, the whole front-end
suite, `tsc -b`, eslint, ruff, OpenAPI snapshot and generated types regenerated, and the real-browser golden spec
(section 15.4).

### 15.1 What was built

| Piece | Where |
|---|---|
| Position, timeline and tax-dues service (read-only) | `backend/reporting/money_position.py`, `money_views.py`, URLs `/api/v1/money/position/`, `/timeline/`, `/statutory/` |
| Cleared-money cash rule (P-1) | `ReportService._cleared_money_q`, used by `cash_totals` and `_cash_opening_balance` |
| Supplier advances (P-2) | `LedgerService.supplier_advances_total` (payment + TDS - applied, per payment, floored at zero); `supplier_outstanding` unchanged (D-9) |
| One due-date rule | `core/services/due_dates.py::effective_due_date`, used by ageing rows, collections and the hub |
| List filters | receipts: `cheque_status`, `advance`, `tds_certificate`; supplier payments: `cheque_status`, `advance`, `status`, `mode`, dates; sales invoices: `overdue` (now every open status and the shared due-date rule), `due_soon`; purchase invoices: `overdue`, `due_soon`, `has_balance`; TDS register: `certificate` |
| Supplier payments summary | `GET /payments/supplier-payments/summary/` (owed and overdue only for roles that may view financial reports) |
| TDS certificate marker | `payments/0044_receipt_tds_certificate` (two columns), `PaymentService.set_tds_certificate`, `POST /payments/receipts/{id}/tds-certificate/`; no ledger posting |
| Kill-switch | company flag `ENABLE_MONEY_HUB`, default on (`core/services/feature_flags.py`) |
| Page, tiles, outlook, tax dues | `web/src/pages/money/*`, route `/money`, `web/src/api/legacy/money.ts` |
| Menu | one `Money` group (overview, receipts, collections, supplier payments, links, portal, bank statements, reconciliation, aggregator, cash book, TDS receivable); the old Payments group, the Sales "receipts" link, the Purchases "supplier payments" link and the Reports "TDS receivable" link moved into it |
| Loop | `?via=money` hand-off bar on every target page (`MoneyHandoffBar`), `createQueryClient` marks the money queries stale after every successful write, collections rows offer "Record payment", the attention alerts for gateway money not in the books open Payment links |
| Help | context help page `money`, four FAQs, 180 strings in `docs/MONEY_HUB_HINDI_REVIEW.csv` |

### 15.2 Deviations from the plan, and why

* **Links carry a ready query string**, not a params object: the API renderer camel-cases dict keys, which would turn `cheque_status` into `chequeStatus`.
* **The kill-switch is a company rollout key** (default on), not an env flag: it reaches the web client with the other flags and needs no deployment setting.
* **Overdue now uses the shared rule on every open status.** The sales `overdue` filter used to be COMPLETED-only with a stored due date; a returned bill with a balance, or a bill with terms but no stored due date, was missed. This is a behaviour change (section 15.5).
* **Gateway tile = the attention rule** (captured at the gateway, no receipt), not only `CAPTURED_PENDING_BOOKS`, so the hub, the alert and the Payment links page agree.
* **Bank tiles count `UNMATCHED` and `SUGGESTED`** (what the reconciliation queue lists). The queue endpoint returns at most 100 lines; the page now says so instead of leaving the tile looking wrong.
* **Cash by account** shows each account's own movement and opening balance; the headline equals the cash book (company opening balance plus all movements). Account opening balances are not part of that headline, as before.
* **TDS payable** is "TDS deducted on supplier bills" (the TDS worksheet total for last month and this month), because nothing in the books records a remittance.

### 15.3 Open items from section 14, resolved

1. P-1 and P-2 were reproduced by tests (`test_money_hub_wp0.py`). P-1 was half right: a bounced cheque voids the receipt, so it was never counted; a cheque still waiting to clear was.
2. The TDS page had no "certificate received" action; it now has one (above).
3. Target pages: sales history already had `overdue` and `payment`; every other filter in section 6 was added.
4. The insights cash-flow service is a different basis (forecast); the hub's outlook is separate and labelled "by due date, not a forecast".
5. Supplier cheques are created `PENDING_CLEARANCE`; confirmed in `PaymentService.create_supplier_payment`.
6. Global search was not changed; the Money page is reachable from the menu, the dashboard and the morning page.

### 15.4 Real-browser run

`web/e2e-golden/money-hub-golden.spec.ts`, run against a copy of the dev database (`DATABASE_URL` pointed at a copy, so the working database is untouched). The result is in section 15.6.

### 15.5 Behaviour changes to announce

* Dashboard and Cash Book **cash can drop** where a cheque that has not cleared was counted in the dashboard total or in a window's opening balance (supplier cheques waiting to clear were also counted as paid out).
* Sales history **Overdue** now follows the shared due-date rule and includes returned bills that still owe money.
* The menu changed: Payments is now **Money**; Receipts, Supplier payments and TDS receivable moved into it.
* Receipts totals now say whether they follow the filters.

### 15.6 What is still for people (not code)

| Item | Who |
|---|---|
| Hindi review of the 180 new strings (`docs/MONEY_HUB_HINDI_REVIEW.csv`) and of the Hindi help page text in `contextHelp/catalog/payments.ts` | a native speaker |
| CA sign-off on the tax-dues wording and the five points in `docs/ca/CA_SIGN_OFF_CHECKLIST.md` (M1 to M5) | the company's CA |
| Whether payables should be netted off by advances paid (D-9) and whether a single supplier's balance should move to the GL basis too | founder with the CA |
| Postgres run of the new tests (nothing here takes locks; the suite was run on SQLite) | CI |
