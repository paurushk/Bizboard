# Deep Code Review — 2026-09-03

Whole-repo, line-by-line review conducted across 13 module clusters (9 backend, 3 frontend, 1 mobile/infra).
Every finding was verified against code on disk at branch `main` (`7d1b613`); nothing here is copied unverified
from the older review docs in the repo.

> Status: all 13 clusters complete and merged below.
> **Trackable fix plan:** [`FIX_PLAN_2026-09-03.md`](FIX_PLAN_2026-09-03.md) — every finding assigned a
> workstream, phase, effort and status checkbox.

---

## 1. How to read this

Each finding has a stable id (`B1-001`, `F2-014`, …), a severity, a category, a `file:line` location, what the
code actually does, the concrete failure it produces, and a suggested fix. Clusters:

| Id | Area |
|----|------|
| B1 | Accounting, GL postings, journals, `ledgers`, document numbering, charges |
| B2 | Sales — invoicing, GST/cess/TCS math, e-invoice / e-way / IRN, returns, COGS, recurring, PDFs |
| B3 | Purchases + Imports — bill-import pipeline, BOE, qty formulas, ITC posture |
| B4 | Payments + Banking — allocation, refunds, dunning, gateway webhooks, bank recon, FIU/AA |
| B5 | Reporting — GSTR-1/3B/2B, IMS, TDS/TCS worksheets, GST health, registers |
| B6 | Auth / tenancy / RLS / OTP / password reset / invites / idempotency / tenant backup |
| B7 | Core services + `config/settings.py` + Celery + LLM/SMS/WhatsApp/GSP adapters + search |
| B8 | Inventory (FIFO/WAVG valuation) + Masters (pricing, HSN, custom fields) + Manufacturing (BOM, WO) |
| B9 | Billing/subscription + Insights/AI assistant + CRM + Tally integration + Payroll (PT/PF/ESI/TDS) |
| F1 | Web shell, API client, auth context, money/tax/gst utils, offline cache, i18n, PWA, auth pages |
| F2 | Web transaction pages — sales / purchases / payments / accounting editors + POS + public pay |
| F3 | Web reports / settings / inventory / help / phase pages + shared components |
| M1 | Mobile (Capacitor/Android) + Docker/nginx/CI-CD + `.env` templates |

---

## 2. Tally of findings (all 13 clusters)

| Cluster | Critical | High | Medium | Low | Info | Total |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|
| B1 Accounting / GL     | 0 | 2 | 10 | 21 | 1 | 34 |
| B2 Sales               | 0 | 2 | 7  | 15 | 2 | 26 |
| B3 Purchases / Imports | 0 | 3 | 10 | 13 | 2 | 28 |
| B4 Payments / Banking  | 3 | 8 | 17 | 8  | 2 | 38 |
| B5 Reporting / GST     | 0 | 2 | 11 | 10 | 1 | 24 |
| B6 Auth / Tenancy / RLS| 0 | 1 | 5  | 16 | 4 | 26 |
| B7 Core / Config       | 0 | 2 | 4  | 13 | 2 | 21 |
| B8 Inventory / Mfg     | 0 | 4 | 14 | 13 | 6 | 37 |
| B9 Billing / AI / Payroll | 0 | 5 | 13 | 22 | 4 | 44 |
| F1 Web core            | 0 | 2 | 7  | 11 | 5 | 25 |
| F2 Web txn pages       | 0 | 6 | 33 | 13 | 6 | 58 |
| F3 Web reports/settings/help | 0 | 4 | 41 | 23 | 6 | 74 |
| M1 Mobile / Infra      | 0 | 3 | 14 | 16 | 5 | 38 |
| **Total**              | **3** | **44** | **186** | **194** | **46** | **473** |

---

## 3. The 3 Critical findings (all in Payments)

- **B4-001** — Partial gateway refund double-unwinds the books on outbox retry. `_unwind_refund_books`
  only sets `books_unwound=True` for *full* refunds, so a retried `execute_gateway_refund` reverses
  allocations and posts the refund journal entry a second time. Books show 2× the refund; the provider
  refunded once.
- **B4-002** — `refund_idempotency_key` = `bb-refund-<id>-<amount>` has no nonce. Two legitimate
  equal-amount partial refunds get the same provider key: the gateway refunds once, the books unwind
  twice, the customer is under-refunded.
- **B4-003** — The provider refund HTTP call runs *inside* `@transaction.atomic`. A crash after provider
  success but before commit rolls back everything — no outbox row, `gp.status` still `CAPTURED`, no
  allocations reversed — while the customer's money has already left the merchant account, and
  `payment_health` never surfaces it.

## 4. Cross-cutting themes (recurring across clusters)

These are the patterns worth fixing once, centrally, rather than finding-by-finding:

1. **Non-atomic multi-row writes.** `ATOMIC_REQUESTS` is off for the default DB and `CompanyScopedViewSet`
   wraps nothing, so any DRF `create`/`update` that writes a header then child rows (or deletes-then-recreates
   lines) can commit a partial result on a mid-write error. → **B1-002, B8-002, B8-014, B9-044**; also the
   root cause behind several "orphan row" findings.
2. **Missing idempotency on money / mutating endpoints.** → **B4-006** (allocation create),
   **B4-013** (partial refund), **B3-013** (bill commit), **F1-001 / F2-004** (POS complete),
   **F2-013** (sales/purchase returns), **F2-021** (bill-upload commit). `MONEY_IDEMPOTENCY_SCOPES`
   lists scopes that the corresponding views never actually honour.
3. **Raw query params fed straight into ORM lookups → HTTP 500 instead of 400.** → **B1-010, B2-020,
   B7-009, B7-010, B9-018, B9-019**.
4. **Period-lock / books-start-date bypasses.** Several posting paths skip `assert_period_allows_money_amend`
   / `require_open_period_for_posting`. → **B1-006, B1-008, B1-032, B3-008, B4-008, B8-013**.
5. **RLS / tenant-isolation edges.** → **B6-001** (sandbox restore 500s under RLS — default restore mode),
   **B6-002 / B6-013** (GUC-clear ordering can leak `rls_bypass=1` onto a pooled connection),
   **B7-003** (prune command has no `rls_bypass`), **B7-005** (Celery prerun SELECTs tenant rows before the
   GUC is set), **B6-020** (`companyuser`/`companygstin` permanently outside RLS), **B6-021** (no assertion
   the DB role is NOBYPASSRLS), **M1-036** (RLS defaults off in the prod overlay).
6. **FIFO valuation has two engines that can silently disagree.** COGS is booked from peeled perpetual
   `InventoryCostLayer` rows; the FIFO valuation report re-derives from a movement replay. → **B8-001,
   B8-003, B8-004, B8-036**. Balance-sheet inventory value and P&L COGS will not reconcile for FIFO tenants
   with any oversell / adjustment / transfer history.
7. **Heavy, uncached, N+1 report/dashboard endpoints.** → **B1-016 / B1-026, B4-017 / B4-018,
   B5-008 / B5-009 / B5-010 / B5-011, B8-012 / B8-027 / B8-028, B9-012 / B9-013**.
8. **Outbound provider HTTP calls inside DB transactions / holding row locks.** → **B4-003, B4-009, B4-022**.
9. **Webhook replay protection is cache-only** (`cache.add`), which is per-process for `LocMemCache` and
   best-effort under pressure. → **B4-031, B9-034**.
10. **CGST/SGST split: symmetric on the frontend, asymmetric on the backend.** The FE preview total is
    ~1 paise off the posted document on ordinary intra-state invoices, and the code comments contradict each
    other about which is correct. → **F1-004, B7-011**; the wider float-money preview drift is **F2-057**.
11. **Missing confirmation on destructive / irreversible frontend actions.** → **F2-003 / F3-003** (refund
    real money), **F2-015** (delete an unsynced offline sale), **F2-016** (convert order / run recurring /
    block customer / commit statement / reverse journal), **F2-043, F2-053**, **F3-002** (Tally migration
    commit — bulk opening balances + stock, no undo), **F3-004** (bulk-accept GSTR-2B / import IMS JSON),
    **F3-005** (post/reverse journal, close period, disable accounting, dispose asset, scrap serial),
    **F3-047** (bulk WhatsApp to suppliers), **F3-048 / F3-049** (enable dunning, switch to composition
    scheme). Sibling pages (`WorkOrdersPage`, `PayRunsPage`, `ImportPage`) already use `ConfirmDialog`, so
    the app is internally inconsistent.
12. **"Save & New" / form-reset leaks statutory flags** (reverse-charge, TCS, TDS, e-commerce GSTIN,
    stamped company GSTIN) onto the next unrelated document. → **F2-005**.
13. **Partially implemented features presented as done.** Account Aggregator / FIU (**B4-020, F2-058**),
    push notifications (**M1-009**), deep links / App Links (**M1-008**), nested/multi-level BOM (**B8-008**),
    by-product & scrap yield (**B8-009**), payroll arrears / ad-hoc earnings (**B9-036**), multi-currency
    price lists (**B8-032**), price-correction credit/debit notes (**F2-011**), Tally sync-run tracking &
    push idempotency (**B9-010**), `cost_estimate` on the AI ledger (**B9-024**).
14. **LLM cost / PII / prompt-injection surface.** → **B7-016** (no token budget on bill extraction),
    **B7-018** (LLM-extracted strings only `.strip()`-ed), **B9-004** (budget checked once for a two-call
    turn), **B9-008** (customer PII sent to the provider), **B9-009 / B9-016** (prompt-injection & a trivial
    tax-guardrail bypass), **B3-009** (no quota on paid extraction).
15. **Test coverage holes on the highest-risk code.** The **entire `sales` app has zero tests (B2-001)**;
    partial-refund / refund-webhook / double-submit paths (B4-38), RCM-outward GSTR-1 footing (B5-24),
    FIFO-vs-layer reconciliation (B8 coverage notes), payroll slab boundaries (B9), and the FE
    refresh/CSRF/offline state machines (F1-008, F1-016) are all unguarded.
16. **CSV / spreadsheet formula injection in client- and server-built exports.** → **B5-002** (TDS/TCS
    26Q/27EQ worksheets — raw `writer.writerows`), **F3-001** (`ProductsPage` items CSV — `csvEscape` only
    doubles quotes), **B7-008** (`csv_safe` misses a leading `\n`). Other exports (`ExportView`,
    `SalesReportPage` server path) are correctly guarded, so these are gaps in an otherwise-solved problem.
17. **Settings forms silently lose unsaved edits.** React Query refetch-on-focus re-`reset()`s the form from
    the server response, and `UnsavedChangesGuard` is wired to no settings form and has no `beforeunload`
    handler. → **F3-014, F3-015**; `ItemFormDialog` discards a 4-tab form on backdrop click (**F3-011**).
18. **Client-side report math that can diverge from / hide the authoritative figure.** → **F3-006** (numeric
    non-money columns money-formatted), **F3-007** (GSTR-3B net-payable computed client-side and
    `Math.max(0,…)` hides an ITC carry-forward — the number the user pays the government from).
19. **Mobile & infra are not release-ready.** Android targets API 34 (Play now requires 35), the release
    build has no signing config and a frozen `versionCode` (**M1-001, M1-017**); a Play build has no
    reachable API origin (**M1-002**); GitHub Actions aren't SHA-pinned and `ci.yml` has no `permissions:`
    block (**M1-005, M1-006**); no container image scanning (**M1-014**); edge nginx serves `:80` cleartext
    with no HSTS and no TLS overlay in the prod compose (**M1-004**).

---

## 5. Findings by cluster

The remainder of this document is the full, unabridged output of each cluster review.


---

# Deep code review — cluster B1: accounting + ledgers + core doc-number/charges services

**Scope.** Line-by-line read of `backend/accounting/` (`models.py`, `services.py`, `reports.py`,
`serializers.py`, `views.py`, `tasks.py`, `urls.py`, `apps.py`, both management commands, and
migrations 0002–0010 skimmed for logic/data risk), `backend/ledgers/` (`services.py`, `views.py`,
`urls.py`), `backend/core/services/document_numbers.py`, and `backend/core/services/charges.py`.
Cross-checked callers in `sales/`, `purchases/`, `payments/`, `reporting/ims.py` where the
accounting side implies a contract. Tests read for intent: `tests/test_phase5_accounting.py`,
`test_sprint_c_fy_close.py`, `test_concurrency_races.py`, `test_ledger.py`, `test_wave2_open_fixes.py`,
plus the wider `grep` of ~35 test modules that touch `PostingService`/`LedgerService`.
Every finding below was re-verified against the code currently on disk; quoted lines are from the
current files. The good news first: `PostingService.post` hard-asserts debit==credit before it
writes anything and the `uniq_accounting_source_posting` partial unique index is real, so most
"imbalance" mistakes in the many reconciliation branches surface as a failed Complete (HTTP 400),
not as silently corrupt books. The findings therefore skew toward broken-flow, report-correctness,
tenant/permission, and catch-up/idempotency gaps rather than raw double-entry errors.

## Count by severity

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 2 |
| Medium   | 10 |
| Low      | 22 |
| Info     | 1 |
| **Total**| **35** |

---

### [B1-001] Cash-flow statement omits every per-bank child ledger (1500-N)
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/accounting/reports.py:168` (`cash_flow`), interacts with `backend/accounting/services.py:199-213` (`_bank_gl_account`)
- **Observation:** `cash_flow` selects cash/bank lines with
  `cash_accounts = Account.objects.filter(company=company, code__in=["1100", "1500"])`.
  ACC-01 per-bank ledgers are created by `_bank_gl_account` with
  `code = f"1500-{bank_account.id}"` and `parent = 1500`. Those child codes are not `"1500"`, so
  none of them match `code__in=["1100","1500"]`.
- **Impact:** For any tenant that has ≥1 `BankAccount` (the normal case once books are on), every
  bank receipt / supplier payment / bank-charge posting dated on/after `books_start_date` lands on
  `1500-N` and is invisible to the cash-flow report. `net_cash_flow` then reflects only cash-drawer
  (1100) movements and the pre-cutover 1500 aggregate — materially wrong, even as an "aid".
- **Fix:** Filter by the bank sub-tree, e.g. `Q(code__in=["1100","1500"]) | Q(parent__code="1500") | Q(code__startswith="1500-")`, or resolve `cash_accounts` as `1100` + all accounts whose `parent_id` is the 1500 header. `trial_balance` / `balance_sheet` are unaffected because they group by `account_type`, not code.

---

### [B1-002] `JournalViewSet.create` runs outside a transaction — manual-journal creation 500s (no-number path) and orphans the header (supplied-number path)
- **Severity:** High
- **Category:** Broken-flow
- **Location:** `backend/accounting/views.py:137-165`; `backend/core/services/document_numbers.py:360-367`
- **Observation:** `create()` does `JournalEntry.objects.create(...)` then a separate
  `JournalLine.objects.bulk_create([...])` with no `transaction.atomic()` around them
  (`CompanyScopedViewSet` adds none, and `settings.py`/`settings_test.py` never set
  `ATOMIC_REQUESTS`). When the client omits `number`, the view calls
  `DocumentNumberService.next_number(self.company, "JOURNAL_ENTRY", ...)`, which begins with
  `if not _conn.in_atomic_block: raise RuntimeError("... must be called inside a transaction ...")`.
- **Impact:** With `ATOMIC_REQUESTS` off (current config), POSТ `/api/v1/accounting/journals/`
  without a `number` raises `RuntimeError` → HTTP 500. `test_wave2_open_fixes.py::test_staff_cannot_create_journal`
  only passes because pytest-django wraps each test in an outer atomic block, masking the bug.
  If the client *does* pass `number` and a line then violates the `journal_line_one_side` /
  `journal_line_non_negative` CHECK, the already-committed `JournalEntry` header is left orphaned
  (and if a number was allocated, a JV sequence number is burned).
- **Fix:** Wrap the whole `create()` body in `transaction.atomic()` (or set `ATOMIC_REQUESTS=True`
  for the default DB). That both satisfies `next_number`'s guard and makes header+lines all-or-nothing.

---

### [B1-003] IDOR: `JournalLineSerializer` exposes a writable `bank_statement_line` with an un-scoped queryset
- **Severity:** Medium
- **Category:** Security
- **Location:** `backend/accounting/serializers.py:56-64` (fields include `"bank_statement_line"`, only `reconciled_at` is read-only); consumed at `backend/accounting/views.py:162-164` (`JournalLine(company=entry.company, entry=entry, **line)`)
- **Observation:** `account` and `cost_center` are `CompanyPrimaryKeyRelatedField` (tenant-filtered),
  but `bank_statement_line` falls back to DRF's default `PrimaryKeyRelatedField(queryset=BankStatementLine.objects.all())`.
  `JournalViewSet.create`'s cross-tenant loop (`views.py:141-148`) only re-checks `account` and
  `cost_center`.
- **Impact:** A user can create a draft journal line referencing **another company's**
  `BankStatementLine` id. It is written straight through `**line`. That both leaks existence and
  lets the attacker pre-bind a reconciliation link, bypassing the `match` action's amount-match /
  same-statement / already-reconciled checks (`views.py:221-248`) and potentially blocking or
  corrupting the victim's bank recon (`JournalLine.objects.filter(bank_statement_line=bank_line)`).
- **Fix:** Drop `bank_statement_line` from the writable serializer fields (it should only be set via
  the `match` endpoint), or make it a company-scoped related field and validate its company in
  `validate()` alongside `account`/`cost_center`.

---

### [B1-004] Deleting an `Account` or `CostCenter` that has journal lines → `ProtectedError` 500
- **Severity:** Medium
- **Category:** Error-handling
- **Location:** `backend/accounting/views.py:60-63` (`AccountViewSet.perform_destroy`), `CostCenterViewSet` inherits base destroy; `backend/accounting/models.py:141` (`account = ForeignKey(..., on_delete=models.PROTECT)`), `:144` (`cost_center = ForeignKey(..., on_delete=models.PROTECT)`)
- **Observation:** Non-system accounts and any cost center may be `DELETE`d. `JournalLine.account`
  and `JournalLine.cost_center` (and `FixedAsset.*_account`, `BankReconSession.account`) are
  `PROTECT`. `perform_destroy` calls `instance.delete()` with no guard.
- **Impact:** Deleting a used account/cost center throws `django.db.models.ProtectedError`, which is
  not a `BusinessRuleError` — the client gets an unhandled 500 instead of a clean 400 explaining the
  account is in use.
- **Fix:** Catch `ProtectedError` (or pre-check `JournalLine.objects.filter(account=instance).exists()`
  / usage on the FA + recon models) and raise `BusinessRuleError("Account is referenced by postings and cannot be deleted; deactivate it instead.")`.

---

### [B1-005] Depreciation runner permanently skips a month on any failure; no catch-up
- **Severity:** Medium
- **Category:** Gap / Data-integrity
- **Location:** `backend/accounting/tasks.py:40-72`
- **Observation:** `purpose = f"DEPRECIATION-{timezone.localdate():%Y-%m}"` and the `already_posted`
  check is keyed on that per-calendar-month purpose. On `BusinessRuleError` (e.g. the current
  period is CLOSED) or any exception, the block is caught, `last_depreciation_error` is stored, and
  `depreciated_amount` is **not** incremented. Next month the loop uses a *new* `purpose`, so the
  missed month is never retried.
- **Impact:** One failed/blocked run = one month's depreciation charge lost forever. The
  `if remaining - amount <= _D("1"): amount = remaining` true-up only recovers sub-rupee tails, not
  a full month, so the asset never fully depreciates and `written_down_value` stalls above salvage.
- **Fix:** Drive the schedule off the asset (months elapsed since `acquisition_date` vs
  `depreciated_amount / monthly_charge`) and post every still-missing month, each dated to its own
  month-end, rather than one charge keyed to "now".

---

### [B1-006] Manual `JournalViewSet.post` bypasses `require_open_period_for_posting` (ACC-04) and the books-start-date routing that `PostingService.post` applies
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `backend/accounting/views.py:167-185` vs `backend/accounting/services.py:484-506`
- **Observation:** The action only checks `AccountingPeriod` rows in `(CLOSED, SOFT_CLOSED)`. It
  never consults `company.require_open_period_for_posting` (the ACC-04 opt-in that
  `PostingService.post` enforces at `services.py:495-506`), and it flips the draft straight to
  `POSTED` with `source_type="MANUAL_JOURNAL"` without going through `PostingService`.
- **Impact:** A tenant that turned on "require an open period to post" still cannot rely on it for
  manually keyed journals — a back-dated manual voucher into a year with no period rows posts
  freely, defeating the control. Two independent posting code paths with divergent rules.
- **Fix:** Route manual posting through a shared guard (extract the period checks from
  `PostingService.post` into a helper and call it here too), or have the action delegate to
  `PostingService.post` with `source_type="MANUAL_JOURNAL"`.

---

### [B1-007] Depreciation entry is dated to the day the job runs, not the month being depreciated
- **Severity:** Medium
- **Category:** Bug (timezone/date)
- **Location:** `backend/accounting/tasks.py:50-61` (`entry_date=timezone.localdate()`)
- **Observation:** Whatever month the Celery beat fires in, the journal is stamped
  `entry_date = today`. If the March run slips to April 1–2 (common), the March depreciation lands
  in the April period / next FY.
- **Impact:** Period P&L and the depreciation schedule drift by whatever the run latency is; a run
  that slips across the FY boundary misstates both years and can also hit a now-closed period
  (feeding B1-005).
- **Fix:** Pass `entry_date = <last day of the month being charged>` (derived from the same month
  key used for `purpose`).

---

### [B1-008] `close_financial_year` posts an FY_CLOSE journal even when no `AccountingPeriod` covers the FY — the "close" then enforces nothing
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/accounting/reports.py:387-410`
- **Observation:** The IS→3100 journal is posted unconditionally (when `lines` is non-empty); the
  period lock-down is a best-effort
  `AccountingPeriod.objects.filter(company=..., start_date__lte=fy_end, end_date__gte=fy_start).exclude(status=CLOSED).update(status=CLOSED)`.
  If the tenant never created period rows, that `update()` touches zero rows.
- **Impact:** After a "successful" FY close, `PostingService.post` still finds no CLOSED period for
  dates in that FY, so back-dated entries into the closed year keep posting — silently un-closing
  the books and leaving the retained-earnings roll-forward wrong.
- **Fix:** Require (or auto-create) periods spanning the FY before allowing the close, or add a
  `company.books_locked_through` date that `PostingService.post` also checks.

---

### [B1-009] Document-basis party *statement* does not foot the document-basis *outstanding* when unallocated cash exists
- **Severity:** Medium
- **Category:** API contract inconsistency
- **Location:** `backend/ledgers/services.py:454-536` (`customer_statement`), `:753-847` (`supplier_statement`), vs `:324-367` (`_customer_outstanding_documents`) / `:625-672` (`supplier_outstanding`)
- **Observation:** `customer_statement` docstring says "Running-balance statement — foots
  customer_outstanding (PD-02)". In the non-GL branch it posts each receipt as a credit of the
  **full** `receipt.amount` (`ledgers/services.py:516`), whereas `_customer_outstanding_documents`
  subtracts only `allocated` (`:356-366`). `tests/test_ledger.py` shows the mismatch directly:
  `test_customer_statement_running_balance` closes at `680.00` while
  `test_outstanding_uses_allocations_not_raw_receipts` reports `outstanding == 1180.00` for the
  same data.
- **Impact:** A user reconciling the statement PDF against the "outstanding" figure on every other
  money screen sees a discrepancy equal to the customer's unallocated advances, with no explanation.
  The GL branch (`_gl_party_statement`) does foot, so behaviour flips based on `outstanding_basis`.
- **Fix:** Either credit only the *allocated* portion in the statement and add an explicit
  "advance received (unallocated)" memo line, or change the docstring/contract and expose the
  advance component separately so both surfaces agree.

---

### [B1-010] Report endpoints feed raw query params straight into ORM date/int lookups → 500 on malformed input
- **Severity:** Medium
- **Category:** Error-handling
- **Location:** `backend/accounting/views.py:391-405`; `backend/accounting/reports.py:13-20` (`_balances` uses `as_of`, `date_from`, `date_to`, `cost_center` verbatim)
- **Observation:** `trial_balance(self.company, as_of)` passes `as_of` (a raw string) into
  `entry__entry_date__lte=as_of`; `profit_and_loss`/`cash_flow` pass `from`/`to` similarly; the
  `cost_center` param goes into `qs.filter(cost_center_id=cost_center)`. `balance_sheet` guards
  `as_of` via `_indian_fy_bounds`, but `_balances`'s own `as_of` filter does not.
- **Impact:** `?as_of=notadate` → `ValidationError`; `?cost_center=abc` → `ValueError` — both bubble
  up as HTTP 500 rather than a 400. Also `?cost_center=<id>` is not checked to belong to the
  company (harmless leak-wise since lines are already company-scoped, but returns confusingly empty).
- **Fix:** Parse/validate the params in the view (reuse `ledgers/views.py::_parse_date`), coerce
  `cost_center` to int + verify `CostCenter.objects.filter(company=..., pk=...)`.

---

### [B1-011] `balance_sheet(as_of=None)` `equation_holds` breaks when any entry is dated after the FY end
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/accounting/reports.py:98-142`
- **Observation:** With `as_of=None`, `_balances` applies no upper date bound (all posted lines), so
  `assets`/`liabilities`/`equity` include next-FY activity, but `current_earnings` is
  `profit_and_loss(..., date_to = as_of or fy_to)` — capped at `fy_to`. `equation_holds =
  assets == liabilities + equity + pl` then compares mismatched horizons.
- **Impact:** `equation_holds` returns `False` for a perfectly balanced ledger whenever future-dated
  vouchers exist (recurring templates, advance-dated invoices). Cosmetic but undermines trust in
  the health flag.
- **Fix:** When `as_of` is None, default it to `fy_to` (or today) before calling `_balances`, so
  both sides use the same cut-off.

---

### [B1-012] `profit_and_loss` with only `date_from` supplied applies no upper bound
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/accounting/reports.py:84-89`
- **Observation:** The defaulting logic handles `(None, None)` and `(None, not-None)` only. When
  `date_from` is given and `date_to` is `None`, neither branch runs and `date_to` stays `None`, so
  `_balances` never adds `entry_date__lte`.
- **Impact:** `GET /profit-and-loss/?from=2025-04-01` silently returns P&L from that date to the end
  of time, including future-dated entries.
- **Fix:** `if date_to is None: _, date_to = _indian_fy_bounds(date_from, company)` (or today).

---

### [B1-013] Client-supplied journal `number` is trusted; collides with later auto-allocated `JV-` numbers
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `backend/accounting/serializers.py:95` (`number` is writable — not in `read_only_fields`); `backend/accounting/views.py:149` (`number = (serializer.validated_data.get("number") or "").strip()`, used verbatim if truthy)
- **Observation:** A caller can set any voucher number on a draft journal. The
  `uniq_journal_number_per_company` constraint is enforced only at the DB. `DocumentNumberService`
  keeps its own `DocumentSeries.next_number` counter and does **not** scan existing numbers on the
  hot path (BB-000646), so a user-chosen `JV-2526-0007` will later collide with the auto-allocated
  one.
- **Impact:** The colliding auto-post (`PostingService.post` → `JournalEntry.objects.create(number=...)`)
  raises `IntegrityError`; it is caught only for the *source-posting* race, not for a plain
  number clash, so a document Complete 500s. Also lets users forge non-sequential statutory
  voucher numbers.
- **Fix:** Make `number` read-only on create (always allocate server-side), or validate a supplied
  number against the series and bump `series.next_number` past it.

---

### [B1-014] `validate_lines` only checks the debit/credit sum, not per-line one-sidedness
- **Severity:** Low
- **Category:** Error-handling
- **Location:** `backend/accounting/serializers.py:99-104`
- **Observation:** `debit = sum(...); credit = sum(...); if not lines or debit != credit: raise`.
  A payload of two lines each `{"debit":"50","credit":"50"}` has equal sums but violates the
  `journal_line_one_side` CHECK at insert time (and B1-002's non-atomic create leaves an orphan
  header).
- **Impact:** 500 (IntegrityError) instead of a 400 with a useful message; orphaned draft header.
- **Fix:** In `validate_lines`, reject any line where both `debit` and `credit` are > 0 or both are
  0.

---

### [B1-015] Dead permission branch: `JournalViewSet.get_permissions` lists verbs the viewset forbids
- **Severity:** Low
- **Category:** Dead code
- **Location:** `backend/accounting/views.py:124` (`http_method_names = ["get", "post", "head", "options"]`) vs `:126-132` (permission map includes `"update", "partial_update", "destroy"`)
- **Observation:** PUT/PATCH/DELETE are not routable, so those permission keys never fire.
- **Impact:** None functionally; misleads a reader into thinking journal edit/delete is a supported,
  permission-gated flow.
- **Fix:** Trim the permission map to `("create", "post", "reverse")`.

---

### [B1-016] `<str:report>/` catch-all route + uncached heavy `books-health`
- **Severity:** Low
- **Category:** Performance / API design
- **Location:** `backend/accounting/urls.py:21`; `backend/accounting/views.py:406-408` → `BooksHealthService.control_balances`
- **Observation:** `path("<str:report>/", AccountingReportView.as_view())` swallows any unmatched
  segment under `/api/v1/accounting/`. `?report=books-health` triggers `control_balances`, which
  runs ~15 aggregate/`.exists()` queries plus cross-app imports and `_advance_recon_alerts`
  (see B1-026) on every call with no memoisation or throttle.
- **Impact:** Easy accidental load; a dashboard polling books-health hammers the DB.
- **Fix:** Register explicit report names and/or short-cache `control_balances` per company-request.

---

### [B1-017] `cash-flow` XLSX export emits an empty sheet
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/accounting/views.py:410-435` (`_report_response`); `backend/accounting/reports.py:207-231` (`cash_flow` payload)
- **Observation:** The exporter does `rows = payload.get("rows", [])`. `cash_flow`'s dict has no
  `"rows"` key (it returns `operating_activities` / `investing_activities` / …), so the workbook
  gets only the header row.
- **Impact:** `GET /api/v1/accounting/cash-flow/?format=xlsx` downloads a blank spreadsheet.
- **Fix:** Special-case cash-flow in `_report_response` (flatten the activity buckets into rows) or
  add a `rows` projection to `cash_flow`.

---

### [B1-018] Silent fallbacks in FY-bounds helpers hide bad input
- **Severity:** Low
- **Category:** Improvement
- **Location:** `backend/accounting/reports.py:54-81` (`_indian_fy_bounds`), `:234-242` (`fy_bounds_for_end`)
- **Observation:** A malformed `as_of` string is swallowed (`except (ValueError, TypeError): as_of = timezone.localdate()`),
  and an out-of-range `fy_start_month` is silently coerced to 4. Callers get a plausible-looking FY
  for garbage input.
- **Impact:** A typo in an `as_of` param yields a "current FY" balance sheet with no error, which a
  user may not notice.
- **Fix:** Let the caller-facing view validate and 400 on bad dates; keep the coercion only as a
  last-resort default.

---

### [B1-019] `seed_chart_of_accounts` re-parents system accounts and issues ~30 writes on every call, from many hot paths
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/accounting/services.py:81-99`; callers `_ensure_chart` (`:120-138`), `_account` fallback (`:140-169`), `FixedAssetViewSet.perform_create`/`dispose` (`views.py:260-321`), `close_financial_year` (`reports.py:357`), `AccountingSettingsView.post` (`views.py:338-339`)
- **Observation:** The function unconditionally re-walks `_CHART_PARENTS` and does
  `accounts[code].save(update_fields=["parent"])` whenever `parent_id` differs. `_ensure_chart` calls
  it whenever `len(existing) < len(required)` and `_account` calls it on any miss.
- **Impact:** Dozens of UPDATEs per document Complete in the worst case; also silently reverts any
  deliberate manual re-parenting of a system account.
- **Fix:** Guard the re-parent loop behind "only when parent is NULL", and make `_ensure_chart`
  create just the missing codes instead of re-seeding the whole chart.

---

### [B1-020] Disposal gain / FX accounts are typed against their code block
- **Severity:** Low
- **Category:** Improvement
- **Location:** `backend/accounting/services.py:55-60` (CHART): `("5700", "Gain on Disposal of Assets", "INCOME", True)`, `("5900", "Foreign Exchange Gain / Loss", "EXPENSE", True)`
- **Observation:** `5700` is an INCOME account inside the 5xxx "Expenses" range; `5900` is an
  EXPENSE account that must also carry forex *gains* (credit balance). P&L math works because
  `profit_and_loss` groups on `account_type`, but any code-range heuristic (`code.startswith("5")`
  ⇒ expense) elsewhere will misclassify.
- **Impact:** Latent misgrouping risk in future report/export code; a forex gain shows as "negative
  expense".
- **Fix:** Move `5700` under a 4xxx "Other income" code, and split `5900` into a gain (income) and
  loss (expense) account, or at least document the deliberate mismatch at the call sites.

---

### [B1-021] SLM depreciation ignores acquisition date — no first/last-month proration
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `backend/accounting/models.py:229-245` (`monthly_depreciation`), consumed in `tasks.py:35`
- **Observation:** SLM charge is a flat `depreciable_base / useful_life_months`; nothing looks at
  `acquisition_date`. An asset acquired on the 25th is charged a full month; the runner also has no
  concept of "months elapsed", so an asset can be charged from whenever the job first sees it.
- **Impact:** Over/under-depreciation vs the Companies Act pro-rata expectation; combined with
  B1-005/B1-007 the total life-time charge is not guaranteed to equal `depreciable_base`.
- **Fix:** Compute the schedule from `acquisition_date` and month boundaries, prorating the first
  (and final) month.

---

### [B1-022] `PeriodViewSet.close` allows non-contiguous period close
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/accounting/views.py:92-103`
- **Observation:** `close` only rejects an already-CLOSED period and runs
  `assert_period_close_allowed`. It does not require the immediately-prior period to be closed, nor
  that the period being closed is the earliest OPEN one.
- **Impact:** A user can close March while February is still OPEN. Later back-dated entries into
  February are allowed while March is "closed", producing a period whose reported figures change
  after close — the exact ambiguity the ACC-05 overlap guard was meant to prevent.
- **Fix:** Reject the close unless every earlier period for the company is SOFT_CLOSED/CLOSED (or
  there is none).

---

### [B1-023] API-triggered `reverse` dates the reversal to today, not the original entry's period
- **Severity:** Low
- **Category:** Bug (date)
- **Location:** `backend/accounting/views.py:187-189` (`JournalViewSet.reverse` calls `PostingService.reverse(self.get_object(), request.user)` with no `entry_date`); `backend/accounting/services.py:1643-1668`
- **Observation:** The document-side callers (`adjust_*_postings`, `_reverse_allocation_journals`,
  `reverse_work_order` where relevant) pass `entry_date=entry.entry_date`, but the manual API path
  does not, so `reverse` falls back to `entry_date or timezone.localdate()`.
- **Impact:** Reversing a prior-month manual journal posts the counter-entry in the current month,
  leaving the original period overstated and this period carrying an orphan reversal. If the
  current period is CLOSED and `source_type == "MANUAL_JOURNAL"` (`allow_soft_closed=False`), the
  reversal is refused even though the *original* period is open.
- **Fix:** Default `entry_date` to `entry.entry_date` in `PostingService.reverse` (let callers
  override), matching the document-side behaviour.

---

### [B1-024] `post_monthly_depreciation` fans out to every company incl. accounting-disabled; per-asset re-lock has no company filter
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/accounting/tasks.py:76-92` (`for company_id in Company.objects.values_list("pk", ...)`), `:22-23` (`FixedAsset.objects.select_for_update().get(pk=asset.pk)`)
- **Observation:** The orchestrator queues one subtask per `Company` with no
  `accounting_enabled=True` filter. `_depreciate_company_assets` then, for each asset, re-fetches
  `FixedAsset.objects.select_for_update().get(pk=asset.pk)` relying on RLS for tenant scoping rather
  than an explicit `company_id=company_id`.
- **Impact:** Wasted tasks/queries for tenants with books off (each asset is loaded, `post()`
  returns `None`, nothing recorded). The unscoped `.get(pk=...)` is a latent cross-tenant hazard if
  RLS is ever not set for the worker.
- **Fix:** Filter the orchestrator to `accounting_enabled=True`; add `company_id=company_id` to the
  `select_for_update().get(...)`.

---

### [B1-025] `adjust_sales_invoice_postings` would repost a full P&L entry if run on an opening-balance invoice
- **Severity:** Low
- **Category:** Broken-flow (edge)
- **Location:** `backend/accounting/services.py:681-746`
- **Observation:** It reverses every POSTED `SALES_INVOICE` entry for the invoice and then calls
  `post_sales_invoice` (full revenue/tax/COGS), regardless of whether the only prior entry was an
  `OPENING` one from `post_opening_sales_invoice` (AR vs 3200, no P&L).
- **Impact:** If an opening invoice is ever amended through the standard sales-amend path, its books
  entry flips from "opening AR vs equity" to a P&L sale — misstating revenue and equity for the
  opening period.
- **Fix:** Detect `invoice.is_opening_balance` (or the presence of an `OPENING`-purpose entry) and
  re-post via `post_opening_sales_invoice` instead. Same applies to `adjust_purchase_invoice_postings`.

---

### [B1-026] `BooksHealthService.control_balances` is a heavy fixed-cost call with no memoisation
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/accounting/services.py:1755-1871` (+ `_advance_recon_alerts` `:1873-1944`, + `period_close_blockers` `:1696-1745` calling `build_gst_health`)
- **Observation:** Each invocation issues the AR/AP nets, the tagged nets, a `SOFT_CLOSED` exists,
  eight `_has_missing` subquery `.exists()` calls, the depreciation-alerts query, and the two
  advance-recon reconciliations, plus imports of `sales`, `purchases`, `payments`, `manufacturing`,
  `payroll`, `reporting`. `period_close_blockers` additionally runs `build_gst_health`.
- **Impact:** Every `books-health` GET and every soft-close/close attempt pays this. On a large
  tenant the `_has_missing` `exclude(id__in=je.values("source_id"))` patterns are not cheap.
- **Fix:** Cache the result per (company, request) and/or convert the `_has_missing` checks to a
  single `NOT EXISTS` per source type with an index on `(company, source_type, source_id)`.

---

### [B1-027] `LedgerService.company_receivables` / `company_payables` are structurally ≥ the control-account balance
- **Severity:** Info
- **Category:** Improvement
- **Location:** `backend/ledgers/services.py:439-451`
- **Observation:** Both sum `bulk_customer_outstanding()` / `bulk_supplier_outstanding()` values,
  each floored at 0 per party (`max(Decimal("0"), ...)`). The docstrings already warn this reads
  higher than the 1200/2100 control balance when any party is in credit.
- **Impact:** Dashboard AR/AP will not tie to the trial balance; documented, but a frequent source
  of "the numbers don't match" support tickets.
- **Fix:** Offer an un-floored company total (or expose the credit-balance parties separately) for
  reconciliation surfaces.

---

### [B1-028] `_balances` builds a redundant dict keyed by `account_id`
- **Severity:** Low
- **Category:** Improvement
- **Location:** `backend/accounting/reports.py:25-43`
- **Observation:** `qs.values("account_id", account_code=F(...), ...).annotate(debit=Sum, credit=Sum)`
  already yields exactly one row per account; the `totals[row["account_id"]] = row` /
  `return list(totals.values())` layer adds nothing.
- **Impact:** None functionally; minor noise.
- **Fix:** `return [ {**row, "balance": row["debit"] - row["credit"]} for row in qs.values(...).annotate(...) ]`.

---

### [B1-029] Period-close `update()`s don't stamp `updated_at`; the FY re-run branch skips `updated_by` on GST periods
- **Severity:** Low
- **Category:** Improvement
- **Location:** `backend/accounting/reports.py:296-311` (existing branch), `:405-420` (main branch)
- **Observation:** `AccountingPeriod.objects.filter(...).update(status=CLOSED, updated_by=user)` — no
  `updated_at`. `GstReturnPeriod.objects.filter(...).update(status=CLOSED)` — no `updated_by`/`updated_at`
  in either branch.
- **Impact:** Audit trail on who/when closed a period via FY close is incomplete; `.update()`
  bypasses `auto_now`.
- **Fix:** Add `updated_at=timezone.now()` (and `updated_by`) to the `.update()` calls.

---

### [B1-030] `AccountingPeriodSerializer.validate` silently skips the overlap guard when there is no request; model `clean()` never runs on the API path
- **Severity:** Low
- **Category:** Gap
- **Location:** `backend/accounting/serializers.py:21-47`; `backend/accounting/models.py:54-67`
- **Observation:** The serializer resolves `company` only from `self.context["request"]`; if a
  period is created via a serializer without request context, `company` is `None` and the
  overlap check is bypassed. `Model.clean()` (which has its own overlap guard) is not invoked by
  DRF or by `Model.save()`, only by `full_clean()`.
- **Impact:** Overlap protection depends entirely on the serializer having request context; any
  internal/bulk creation path can insert overlapping periods, re-introducing the ACC-05 ambiguity.
- **Fix:** Call `instance.full_clean()` in `perform_create`/`perform_update`, or add a DB
  `ExclusionConstraint` (Postgres `daterange &&`) so overlap is impossible regardless of path.

---

### [B1-031] `JournalViewSet.create` duplicates the serializer's cross-tenant check and still misses `bank_statement_line`
- **Severity:** Low
- **Category:** Improvement
- **Location:** `backend/accounting/views.py:141-148` vs `backend/accounting/serializers.py:106-125`
- **Observation:** The company checks for `account`/`cost_center` exist in both `JournalEntrySerializer.validate`
  and again in the view. Neither validates `bank_statement_line` (see B1-003).
- **Impact:** Maintenance hazard (two places to keep in sync) and a real gap for the third FK.
- **Fix:** Keep the check in one place (the serializer), extend it to `bank_statement_line`, and
  drop the view-side loop.

---

### [B1-032] No posting guard against `entry_date < company.books_start_date`
- **Severity:** Low
- **Category:** Gap
- **Location:** `backend/accounting/services.py:465-506` (`PostingService.post`); `books_start_date` is only read for bank-ledger routing at `:187-189`
- **Observation:** `post` blocks CLOSED/SOFT_CLOSED periods and (opt-in) requires an OPEN period,
  but nothing rejects an `entry_date` earlier than the company's books-start / cut-over date.
- **Impact:** A back-dated document or manual journal before the migration cut-over posts into the
  pre-books era, double-counting against imported opening balances.
- **Fix:** In `post`, raise `BusinessRuleError` when `books_start_date and entry_date < books_start_date`
  (allow an explicit override flag for the opening-balance posters that legitimately need it).

---

### [B1-033] Round-off / tax-drift legs use un-quantized `Decimal(str(...))`
- **Severity:** Low
- **Category:** Improvement
- **Location:** `backend/accounting/services.py:237-256` (`_round_off_line`), `:636-661` (`tax_drift` leg in `post_sales_invoice`)
- **Observation:** `amt = Decimal(str(round_off or 0))` and `tax_drift = hdr_tax - line_tax` are
  posted directly with no `.quantize(Decimal("0.01"))`. Today the source fields are 2dp so it is
  safe, but a future >2dp input (or an arithmetic result like `hdr_tax - line_tax` producing a
  long tail) would violate the `decimal_places=2` column or unbalance the entry (which `post`
  would then reject).
- **Impact:** Defensive only; currently latent.
- **Fix:** `quantize(Decimal("0.01"))` the amount before building the line.

---

### [B1-034] `post_purchase` ACC-06 residual bound can block a legitimate Complete
- **Severity:** Low
- **Category:** UX/Broken-flow
- **Location:** `backend/accounting/services.py:1116-1134`
- **Observation:** When `additional_charges` is 0 on the header, an unexplained
  `residual = grand_total - tax - line_taxable - round_off` greater than
  `max(Decimal("100"), grand * 0.10)` raises `BusinessRuleError` and refuses to post.
- **Impact:** A real freight/insurance/handling amount folded into the invoice grand total but not
  entered in the `additional_charges` field (common with supplier PDFs) makes the purchase
  impossible to Complete until the user restructures the lines — with an error message that reads
  like a data-corruption warning.
- **Fix:** Treat a large residual as `5110 Purchase Charges` with a warning/health alert rather than
  a hard block, or surface a dedicated "enter the freight amount" field prompt.

---

## Cross-file contract notes (observed from the accounting side)

- `post_receipt_refund` reuses `purpose="REFUND"` for a full refund and `f"REFUND_{je_seq}"` for
  partials; `payments/services.py:1190,1226-1231,1262` persists `refund_je_seq` on the gateway
  `raw` blob and increments it, so repeated partial refunds do get distinct purposes. **Verified
  OK — not a finding**, but the correctness hinges entirely on that external counter being
  persisted; a caller that forgets `raw["refund_je_seq"]` round-tripping would collide and silently
  get the first refund's journal back (`PostingService.post` fast-path returns `existing`).
- `post_work_order_release` / `post_work_order_complete` are idempotent on
  `(WORK_ORDER, wo.id, RELEASE|COMPLETE)`. If a work order is re-opened and re-released after a
  prior RELEASE entry exists, the second release posts nothing (purpose collision) — confirm the
  manufacturing side never re-releases, or add a sequence suffix.
- `PurchaseInvoice.itc_eligibility` drives three different GL shapes in `post_purchase`
  (`services.py:1201-1233`) and again in `reclass_*` / `post_note`. The `_purchase_itc_input_lines`
  helper and the inline re-implementation in `post_purchase`'s non-RCM branch encode the same
  policy twice — keep them in lockstep.

---

# Deep Code Review — Cluster B2: `backend/sales/**`

## Scope note

Full line-by-line read of every file in `backend/sales/` in scope:
`models.py`, `services.py`, `views.py`, `serializers.py`, `phase1_views.py`,
`phase1_serializers.py`, `recurring.py`, `return_service.py`, `cogs_service.py`,
`notes_services.py`, `handlers.py`, `tasks.py`, `irn_guard.py`,
`einvoice_payload.py`, `einvoice_eway_actions.py`, `eway_payload.py`,
`pdf_actions.py`, `pdf/*` (`gst_tax_invoice.py`, `note_documents.py`,
`thermal_receipt.py`, `helpers.py`, `styles.py`, `__init__.py`),
`whatsapp_send.py`, `urls.py`, `apps.py`. Migrations skimmed for logic/data
issues. Supporting reads into `core/services/billing.py`,
`core/services/h9_amend.py`, `accounting/services.py` to verify call
contracts. `backend/sales/tests/**` — **directory is empty; no sales test
module exists anywhere in the repo** (see B2-001).

Findings re-verified against current code (repo HEAD `7d1b613`). Prior review
docs were not consulted per availability; every item below reflects code as it
stands today.

## Severity counts

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 2 |
| Medium   | 7 |
| Low      | 15 |
| Info     | 2 |
| **Total**| **26** |

---

### [B2-001] Sales module has zero automated test coverage
- **Severity:** High
- **Category:** Gap
- **Location:** `backend/sales/tests/` (empty), whole app
- **Observation:** The review scope lists `backend/sales/tests/**`, but the
  directory contains no files (`find` for `*sales*test*` / `test_*.py`
  referencing sales returns nothing). The app implements GST/IGST/CGST/SGST/cess
  splitting, TCS fold, place-of-supply resolution, GSTIN-scoped document
  numbering, IRN/e-Way guards, NIC payload builders, credit/debit-note headroom,
  FIFO/COGS hooks, recurring scheduling and multi-document conversions — all
  statutory-sensitive.
- **Impact:** Any regression in tax computation, rounding, numbering races,
  note headroom, or payload schema ships undetected. Several findings below
  (B2-003, B2-007) would have been caught by a single happy-path test.
- **Fix:** Add `backend/sales/tests/` with, at minimum: intra/inter-state tax
  split, inclusive-price extraction, TCS fold idempotency, CN/DN headroom
  ceilings, `complete()` numbering + period gate, recurring duplicate-skip,
  e-invoice/e-Way payload golden files, and PDF render smoke tests with
  `&`/`<` in names.

---

### [B2-002] Challan e-Way submit has no idempotency / duplicate guard
- **Severity:** High
- **Category:** Broken-flow
- **Location:** `sales/einvoice_eway_actions.py:613` (`ChallanEwayActionsMixin.submit_eway`)
- **Observation:** The invoice version (`InvoiceEinvoiceEwayActionsMixin.submit_eway`,
  line 394) calls `_claim_eway_submit(invoice)` and returns early on
  `"already"` / `"in_flight"`. The challan version does neither — it goes
  straight to `build_eway_payload_from_challan` → `get_eway_adapter().submit()`
  → overwrites `challan.eway_bill_no` / `eway_valid_upto` unconditionally:
  ```python
  result = get_eway_adapter(challan.company).submit(payload)
  challan.eway_bill_no = result.eway_bill_no
  ```
- **Impact:** A double-click, client retry, or two concurrent Owner requests
  each generate a **new e-Way bill at NIC** for the same consignment. The
  first bill number is lost from the record (overwritten), leaving an
  un-cancellable live EWB on the portal and a mismatch between books and NIC.
- **Fix:** Mirror the invoice path: add a `_claim_eway_submit(challan)` claim,
  return the serialized challan on `"already"`, and 409 on `"in_flight"`.
  Also short-circuit when `challan.eway_bill_no` is already set.

---

### [B2-003] `complete_return` throws AttributeError on partial return of a zero-taxable invoice
- **Severity:** Medium
- **Category:** Bug
- **Location:** `sales/return_service.py:186`
- **Observation:** In the auto credit-note ratio fallback:
  ```python
  elif not fully_returned:
      inv_grand = Decimal(str(invoice.grand_total or 0))
      ret_grand = sum((Decimal(str(it.grand_total or it.taxable_amount or 0)) for it in items), Decimal("0"))
  ```
  `items` are `SalesReturnItem` instances. `SalesReturnItem` extends
  `core.models.DocumentLineModel`, which defines only `taxable_amount` and
  `line_total` — there is **no `grand_total` field on line models**
  (`grand_total` lives on `DocumentTotalsModel`, the header). `it.grand_total`
  raises `AttributeError`, not caught anywhere.
- **Impact:** This branch runs when `inv_taxable <= 0 and not fully_returned`
  — i.e. a *partial* sales return against an invoice whose `taxable_total` is
  zero (fully NIL-rated / exempt goods invoice, or a zero-value invoice). The
  `@transaction.atomic` `complete_return` aborts with a 500; the return can
  never be completed.
- **Fix:** Use `getattr(it, "line_total", 0) or getattr(it, "taxable_amount", 0)`
  (line models have `line_total`), or drop the `grand_total` term entirely.

---

### [B2-004] Synchronous `submit_einvoice` lacks an in-flight concurrency guard
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `sales/einvoice_eway_actions.py:194`
- **Observation:** The sync endpoint calls
  `_claim_einvoice_submit(invoice, allow_queued_retry=True)`. With
  `allow_queued_retry=True` the claim query only `exclude(einvoice_status=GENERATED)`
  and the `"in_flight"` branch (`sales/einvoice_eway_actions.py:64`) is gated on
  `not allow_queued_retry`, so it can never return `"in_flight"`. `get_object()`
  takes no `select_for_update`. Two concurrent/duplicate requests both pass the
  claim (`n>=1` each) and both call `get_irp_adapter().submit(payload)`.
- **Impact:** Double IRN submission to the IRP for one invoice. Depending on
  GSP behaviour this is either a duplicate-doc rejection surfaced as FAILED
  (losing the real IRN that the other call stored) or two ACKs.
- **Fix:** Wrap the submit in `transaction.atomic` + `select_for_update`, or
  give the sync path the same `allow_queued_retry=False` in-flight semantics as
  `submit_einvoice_async`.

---

### [B2-005] IRP/GSP adapter errors other than `BusinessRuleError` leave the document stuck in QUEUED
- **Severity:** Medium
- **Category:** Error-handling
- **Location:** `sales/einvoice_eway_actions.py:205-212` (invoice) and `:724-731` (note)
- **Observation:**
  ```python
  try:
      result = get_irp_adapter(invoice.company).submit(payload)
      verify_irn_result(result)
  except BusinessRuleError as exc:
      invoice.einvoice_status = FAILED
      ...
      raise
  ```
  Only `BusinessRuleError` is caught. A network timeout, `requests`
  exception, `ValueError`, `KeyError` from a malformed GSP response, etc.
  propagates uncaught. The claim already set `einvoice_status = QUEUED` and no
  `except` resets it or records `einvoice_error`.
- **Impact:** After any transient adapter failure the invoice/note is
  permanently displayed as "submission in progress" (QUEUED). For the async
  path the claim is `allow_queued_retry=False`, so `submit_einvoice_async`
  then returns 409 `"already in progress"` forever — the user cannot retry
  without a DB edit.
- **Fix:** Catch `Exception` (or `except BusinessRuleError` + a broad
  `except Exception`), persist FAILED + truncated error, then re-raise.

---

### [B2-006] One bad recurring template blocks recurring generation for every tenant
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `sales/recurring.py:141-156` (`process_due_schedules`)
- **Observation:** The beat loop iterates all due schedules and calls
  `generate_draft_for_schedule(schedule, run_date=on_date)` with **no
  per-iteration try/except**. `generate_draft_for_schedule` →
  `_template_items` raises `BusinessRuleError("Template product is invalid for
  this company.")` / `"line template must include items"` for any schedule
  whose `line_template` references a deleted/foreign product, and
  `SalesService.set_items` can raise for inactive products, GST-rate drift,
  negative stock policy, etc.
- **Impact:** The exception unwinds the whole loop and fails the Celery task
  `generate_recurring_invoices_task`. Every other company's due schedules for
  that run are skipped, and the task keeps failing on the same bad schedule on
  every beat — global stall of the recurring-invoice feature.
- **Fix:** `try/except Exception` around the per-schedule body; log + count a
  `skipped_error`, and advance `next_run_at` (or leave it and alert) so a
  poison schedule cannot wedge the batch.

---

### [B2-007] Thermal receipt and credit/debit-note/challan PDFs crash on `&`, `<`, `>` in names
- **Severity:** Medium
- **Category:** Bug
- **Location:** `sales/pdf/thermal_receipt.py:121,135,149-156`; `sales/pdf/note_documents.py:68,82,158`
- **Observation:** `gst_tax_invoice.py` routes every user string through
  `pdf_esc()` (`xml.sax.saxutils.escape`). `thermal_receipt.py` and
  `note_documents.py` do **not** — e.g.
  `Paragraph(company.name, styles["center_bold"])`,
  `Paragraph(f"Customer: {customer.name}")`,
  `Paragraph(name, styles["body"])` (item description),
  `Paragraph(f"<b>Notes:</b> {notes}")`. ReportLab parses `Paragraph` text as
  mini-XML; an unescaped `&`, `<`, or `>` raises
  `ValueError: paraparser: syntax error`.
- **Impact:** For any company / customer / product named e.g. "Nuts & Bolts"
  or "A<B Traders", `render_thermal_receipt` and `render_credit_note` /
  `render_debit_note` / `render_delivery_challan` throw. The PDF task catches
  it and sets `pdf_status = FAILED`; the thermal endpoint (rendered inline)
  returns a 500. Credit/debit notes for such customers never get a PDF.
- **Fix:** Wrap all interpolated user text in these renderers with `pdf_esc()`
  (import from `.helpers`), matching `gst_tax_invoice.py`.

---

### [B2-008] e-Way payload `toStateCode` recomputed from live customer, not the invoice's frozen place of supply
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `sales/eway_payload.py:275` and `:336`
- **Observation:**
  ```python
  to_stcd = extract_state_code(customer.gstin) or extract_state_code(customer.state) or ""
  ```
  The CGST/SGST-vs-IGST split on the invoice was frozen at `complete()` via
  `recompute_totals_for_stamped_gstin` and the resolved
  `filing_place_of_supply`. The e-Way builder ignores `filing_place_of_supply`
  and re-derives the destination state code from the **current** customer
  record.
- **Impact:** If the customer's `state`/`gstin` is edited after the invoice is
  completed (or the invoice used a filing-identity overlay / ship-to POS), the
  e-Way `toStateCode` no longer matches the frozen tax split. NIC cross-checks
  (`igstValue > 0` ⇒ `fromStateCode != toStateCode`, and the converse) then
  reject the bill, blocking dispatch; or a valid bill is raised against the
  wrong destination state.
- **Fix:** Resolve `to_stcd` from `invoice.filing_place_of_supply` first
  (`extract_state_code`), falling back to the customer only when blank —
  consistent with how the invoice froze its tax.

---

### [B2-009] Monthly recurring schedule "day-of-month creep" through February
- **Severity:** Medium
- **Category:** Bug
- **Location:** `sales/recurring.py:28-35` (`advance_next_run`)
- **Observation:**
  ```python
  day = min(dt.day, monthrange(year, month)[1])
  return dt.replace(year=year, month=month, day=day)
  ```
  The next run's day is clamped to the target month's length **and stored**.
  A schedule anchored on the 31st advances 31 → Feb 28 → then the *next*
  advance is computed from the 28th → Mar 28, Apr 28, … permanently.
- **Impact:** A "bill on the 31st / 30th / 29th" schedule silently and
  permanently drifts to the 28th after the first February (or 30th after any
  short month). Month-end billing dates walk backward over time.
- **Fix:** Persist an `anchor_day` (or derive it from schedule creation) and
  always compute `day = min(anchor_day, monthrange(...)[1])` from the anchor,
  not from the last clamped date.

---

### [B2-010] Redundant double `PostingService.post_note` on credit/debit note completion
- **Severity:** Low
- **Category:** Improvement
- **Location:** `sales/phase1_views.py:86-89` and `:185-190` vs `sales/notes_services.py:214-219` and `:367-372`
- **Observation:** `SalesNotesService.complete_credit_note` /
  `complete_debit_note` already call `PostingService.post_note(...)` when
  `accounting_enabled`. The viewset `_run` closures call it a **second** time
  with identical arguments. It is only harmless because `PostingService.post`
  dedupes on `(company, source_type, source_id, purpose, status=POSTED)` and
  returns the existing entry (`accounting/services.py:474-479`).
- **Impact:** Dead/confusing code; a future change to the dedup key or purpose
  would immediately double-post credit/debit notes to the ledger.
- **Fix:** Delete the `PostingService.post_note` block from both viewset
  `_run` closures; the service layer already owns posting.

### [B2-011] `gst_tax_invoice.py` rebinds the `stamp` local from CompanyGstin to a Table
- **Severity:** Low
- **Category:** Improvement
- **Location:** `sales/pdf/gst_tax_invoice.py:107` then `:173`
- **Observation:** `stamp = getattr(invoice, "company_gstin", None)` (used for
  seller GSTIN/name/address lines 108-165), then line 173
  `stamp = Table([[Paragraph(copy, styles["copy_stamp"])]], ...)` reuses the
  same name for the "ORIGINAL/DUPLICATE" box. Line 191+ also reads
  `getattr(invoice, "filing_place_of_supply", ...)` (not `stamp`) so nothing
  currently breaks, but any later reference to the GSTIN `stamp` after line 173
  would get a `Table`.
- **Impact:** Latent bug; fragile to future edits in the footer/signature
  section.
- **Fix:** Name the copy box `copy_stamp_tbl` (or similar).

### [B2-012] Credit/debit-note PDFs print live customer GSTIN, not the note's filing identity
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `sales/pdf/note_documents.py:83-87` (`_render_note_like`), `render_credit_note`/`render_debit_note`
- **Observation:** `if getattr(customer, "gstin", None): Paragraph(f"GSTIN: {customer.gstin}")`
  and `_addr(customer)` use the live `masters.Customer` record.
  `SalesCreditNote`/`SalesDebitNote` carry `filing_party_gstin` /
  `filing_place_of_supply` snapshots (set at completion) that the invoice PDF
  honours but the note PDF ignores. Party address is not snapshotted at all.
- **Impact:** A note re-rendered after the customer's GSTIN/address changes
  shows details that differ from what was filed on GSTR-1 Table 9B.
- **Fix:** Prefer `note.filing_party_gstin` over `customer.gstin`; snapshot
  the party address block onto the note at completion (or accept live and
  document it).

### [B2-013] e-Way payload emits `vehicleNo` unnormalised
- **Severity:** Low
- **Category:** Bug
- **Location:** `sales/eway_payload.py:317` and `:377`
- **Observation:** `validate_eway_transport` upper-cases + strips spaces for
  the regex check, but `build_eway_payload_from_invoice` sets
  `"vehicleNo": vehicle_number` (raw request/`invoice.vehicle_number`) and the
  challan builder uses `challan.vehicle_number or ""` raw.
- **Impact:** A user-entered `mh12ab1234` / `MH 12 AB 1234` passes validation
  (regex is `re.I`) but is sent to NIC lowercase / spaced, which NIC rejects.
- **Fix:** `vehicle_number.replace(" ", "").upper()` in the payload dict, same
  as `transporterId` already does on line 316/376.

### [B2-014] `validate_eway_transport` allows a payload with neither vehicle nor transporter
- **Severity:** Low
- **Category:** Gap
- **Location:** `sales/eway_payload.py:53-79`
- **Observation:** Empty `vehicle_number` skips the vehicle check, empty
  `transporter_id` skips the id check; only `distance_km` is mandatory. A
  Part-B-less bill needs at least a transporter id (+ transport doc) or a
  vehicle number.
- **Impact:** `prepare_eway` / `submit_eway` pass local validation and then
  fail at NIC with a less actionable error, or generate an incomplete bill.
- **Fix:** Add `if not v and not tid: errors.append("Provide a vehicle number
  or a transporter id for the e-Way bill.")`.

### [B2-015] No 24-hour NIC window check on e-Way cancellation
- **Severity:** Low
- **Category:** Gap
- **Location:** `sales/einvoice_eway_actions.py:436-458` (invoice) and `:635-648` (challan)
- **Observation:** `_cancel_irn_via_gsp` enforces the 24h-from-ack rule for
  IRN cancel. `cancel_eway` for both invoice and challan calls
  `get_eway_adapter().cancel(no)` with no equivalent check on
  `eway_valid_upto` / generation time (NIC allows EWB cancel only within 24h
  of generation and only if not verified in transit).
- **Impact:** A cancel attempt outside the window fails at NIC; local state is
  still flipped to CANCELLED after the adapter call, but if the adapter is a
  no-op stub the books and portal diverge.
- **Fix:** Gate on a stored generation timestamp + 24h before calling the
  adapter, mirroring `_cancel_irn_via_gsp`.

### [B2-016] `generate_challan_pdf` ignores `company_id` even when supplied
- **Severity:** Low
- **Category:** Improvement
- **Location:** `sales/tasks.py:139-143`
- **Observation:** `generate_invoice_pdf`, `generate_credit_note_pdf`,
  `generate_debit_note_pdf` all do
  `qs.get(pk=..., company_id=company_id) if company_id else qs.get(pk=...)`.
  `generate_challan_pdf` unconditionally does `.get(pk=challan_id)` — the
  `company_id` parameter is accepted and dropped.
- **Impact:** No live exploit (task inputs are internal), but the tenant-scope
  guard the other tasks apply is silently absent for challans.
- **Fix:** Add the same `company_id` filter.

### [B2-017] `PdfDocumentActionsMixin` calls `pdf_task.delay()` directly instead of `safe_delay`
- **Severity:** Low
- **Category:** Error-handling
- **Location:** `sales/pdf_actions.py:27` and `:49`
- **Observation:** `SalesInvoiceViewSet` uses `core.celery_utils.safe_delay`
  for PDF enqueue; the shared note/challan mixin uses
  `self.pdf_task.delay(...)`.
- **Impact:** With the broker unavailable, `regenerate-pdf` / `pdf` on
  credit/debit notes and challans raise instead of degrading gracefully;
  `pdf_status` is left QUEUED with nothing enqueued.
- **Fix:** Route through `safe_delay`.

### [B2-018] `preview_totals` requires write capability + active subscription
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `sales/views.py:87-91` (`preview_totals` is in the create group)
- **Observation:** `preview-totals` is listed alongside `create`/`complete`, so
  it needs `SubscriptionWritesAllowed()` + `CanCreateSales()`. It only calls
  `build_totals_preview` and persists nothing.
- **Impact:** A read-only "what would the totals be" call is blocked for a
  lapsed subscription or a sales-viewer role.
- **Fix:** Move `preview_totals` to the `CanViewSalesSurfaces()` group.

### [B2-019] `build_upi_qr_png` does not URL-encode UPI intent parameters
- **Severity:** Low
- **Category:** Bug
- **Location:** `sales/pdf/helpers.py:117-127`
- **Observation:** `params.append(f"tn={note[:40]}")` and `f"pa={upi_id}"` are
  concatenated into `upi://pay?...` with no `urllib.parse.quote`. `note` is
  `f"Invoice {invoice.number or invoice.pk}"`.
- **Impact:** Invoice numbers containing spaces (`INV 001`), `&`, `#`, or `/`
  (some GSTIN-scoped series use `/`) produce a malformed UPI URI; some UPI apps
  fail to parse the QR or truncate the payee.
- **Fix:** `quote(value, safe="")` each param value.

### [B2-020] List filters pass raw query params straight to `.filter()`
- **Severity:** Low
- **Category:** Error-handling
- **Location:** `sales/views.py:129-142` (`SalesInvoiceViewSet.get_queryset`); same shape in `phase1_views.py` viewsets
- **Observation:** `qs.filter(invoice_date__gte=params["date_from"])`,
  `qs.filter(status=params["status"])` with no validation.
- **Impact:** `?date_from=notadate` or `?status=BOGUS` raises
  `ValidationError`/`FieldError` → 500 instead of 400; `status` also allows
  probing for invalid enum handling.
- **Fix:** Validate against `SalesInvoice.Status.values` and parse dates with
  `parse_date`, returning `BusinessRuleError` on bad input.

### [B2-021] e-Invoice `BuyerDtls.Loc` set to state name, not city
- **Severity:** Low
- **Category:** Bug
- **Location:** `sales/einvoice_payload.py:379`
- **Observation:** `"Loc": customer.state or ""`. Seller side uses
  `seller_city` (`:236-240,371`). NIC `Loc` is the place/city/town, cross-checked
  loosely against PIN.
- **Impact:** Buyer location prints/transmits as e.g. "Karnataka" instead of
  "Bengaluru"; some IRP validations warn or reject on Loc/PIN mismatch.
- **Fix:** Use `customer.city or customer.billing_city or customer.state`.

### [B2-022] Note e-invoice POS fallback `note_pos[:2]` yields an invalid code
- **Severity:** Low
- **Category:** Bug
- **Location:** `sales/einvoice_payload.py:468`
- **Observation:** `buyer["Pos"] = extract_state_code(note_pos) or note_pos[:2]`
  — when `filing_place_of_supply` on the note is free text
  (`"Karnataka"`), the fallback is `"Ka"`, not a numeric state code.
- **Impact:** CRN/DBN payload carries `Pos: "Ka"`; IRP rejects.
- **Fix:** Drop the `[:2]` fallback; require a resolvable code or raise
  `EinvoiceValidationError`.

### [B2-023] CN/DN line with no `source_item` and duplicate product on the invoice is a hard dead-end
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `sales/services.py:199-211` (`_build_items`)
- **Observation:** When a credit/debit-note line omits `source_item` and the
  source invoice has more than one line for that product,
  `_build_items` raises
  `"GST credit/debit note lines must reference a source invoice item"` with no
  path to proceed except the client re-sending `source_item` ids it may not
  have.
- **Impact:** Notes cannot be raised from a simple product+qty payload against
  invoices that repeat a product across lines (common: same SKU at two prices).
- **Fix:** Allow explicit disambiguation payloads, or auto-split the note
  quantity across matching source lines FIFO (as `complete_return` already
  does for returns).

### [B2-024] Sub-0.001 quantity silently stored as zero
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `sales/migrations/0036_*.py` (quantity `decimal_places=3`, `MinValueValidator(0.001)`) vs `sales/services.py:45` (`_validate_lines`)
- **Observation:** `_validate_lines` rejects `quantity <= 0` only. The model
  `MinValueValidator(Decimal("0.001"))` is not run on `bulk_create` /
  `.save()` without `full_clean()`. A payload `quantity=0.0004` passes the
  service check and is written as `0.000` by the DB column.
- **Impact:** A zero-quantity line persists on a completed invoice: line total
  0, but it still counts toward "at least one line item", HSN summary rows,
  etc. FIFO/COGS sees a 0-qty issue.
- **Fix:** Reject `quantity < Decimal("0.001")` explicitly in
  `_validate_lines`.

---

### [B2-025] Note/challan PDF per-line "Tax" column omits cess
- **Severity:** Info
- **Category:** Improvement
- **Location:** `sales/pdf/note_documents.py:93`
- **Observation:** `tax = (item.cgst or 0) + (item.sgst or 0) + (item.igst or 0)`
  — no `item.cess`. The summary block (`:123`) *does* include a "Cess" row, so
  on a cess-bearing note the per-line Tax column plus Taxable will not foot to
  the line Total or to the summary.
- **Impact:** Cosmetic arithmetic mismatch on compensation-cess credit/debit
  notes.
- **Fix:** Add `+ Decimal(getattr(item, "cess", 0) or 0)` to the line tax.

### [B2-026] Recurring template cannot express cess, exempt/NIL, inclusive pricing or charges
- **Severity:** Info
- **Category:** Partial-feature
- **Location:** `sales/recurring.py:54-85` (`_template_items`)
- **Observation:** Only `product`, `quantity`, `description`, `unit_price`,
  `gst_rate`, `discount_percent` are read from each template line. No
  `cess_rate`/`cess_amount`, `supply_nature`, `unit_price_inclusive`, and the
  schedule has no `additional_charges`/`invoice_discount`/`price_mode`.
- **Impact:** Recurring invoices for exempt supplies, cess goods, or
  MRP-inclusive pricing generate wrong drafts that must be hand-corrected
  every period — undermining the automation.
- **Fix:** Pass the remaining line fields through `_template_items` and add
  header-level charge/discount/price-mode fields to
  `RecurringInvoiceSchedule`.

---

## Areas reviewed and found sound

- `apply_tcs_fold` (`services.py:76`): unfold-before-refold makes
  amend/complete idempotent; `ROUND_HALF_UP` q2; BILL-06 non-taxable-charge
  inclusion in 206C(1H) consideration is correct; manual-override audit
  (`_tcs_override`) captured on the COMPLETE event.
- `_apply_line_tax` (`core/services/billing.py:191`): symmetric CGST=SGST
  half-split with residual absorbed by document round-off — deliberate and
  documented (BILL-01).
- `compute_document_totals` BEFORE_TAX proportional allocation with residual
  redistribution (R1-020) and over-discount rejection (BILL-03/R1-019).
- `SalesService.complete` numbering: series identity from company policy +
  stamped GSTIN + FY (`series_identity`), number assigned only at Complete
  inside `select_for_update`, unique constraint `uniq_sales_number_per_company`
  as backstop.
- `_claim_einvoice_submit` / `_claim_eway_submit` for the **async** and
  **invoice** paths — atomic `.update()` claim with `in_flight` 409.
- `irn_guard` + `assert_no_live_irn` / `assert_no_live_eway` wired into
  invoice cancel, note cancel, challan cancel, and `amend_filing_identity`.
- `amend_filing_identity` intra/inter-state flip guard (BB-000334).
- Return FIFO restore (`cogs_service.restore_return_stock_and_cogs`) restores
  original sale peels and refuses unidentifiable lots (R2-008) rather than
  inventing cost basis.
- `SalesInvoiceViewSet.create` durable idempotency-key with begin/store/release
  placeholder lifecycle.
- Company-scoped `check_company_ref` on every FK in the serializers
  (customer, warehouse, cost_center, signature, company_gstin, sales_invoice).

---

# Deep Code Review — Cluster B3: `backend/purchases/**` + `backend/imports/**`

Scope reviewed line-by-line:
- `backend/imports/`: models.py, services.py (2736 lines), views.py, serializers.py, tasks.py, qty_formula.py, urls.py, apps.py, migrations (skimmed)
- `backend/purchases/`: models.py, services.py, views.py, serializers.py, phase1_views.py, phase1_serializers.py, notes_services.py, boe_services.py, pdf.py, urls.py, apps.py, migrations (skimmed)
- Tests: `tests/test_purchase_bill_import.py`, `tests/test_imports.py`, `tests/test_gst08_bill_of_entry.py`, `tests/test_file_sniff_import.py` (read for intent/coverage)
- Context docs: `BILL_IMPORT_REDESIGN_PLAN.md`, `IMPORT_FLOW_ISSUES.md` (used only to understand intent; every finding re-verified against current code). `IMP-004/005/006` from `IMPORT_FLOW_ISSUES.md` appear addressed in current code and are not re-flagged.

No `eval`/`exec`/`pickle`/`__import__` in scope. `qty_formula.eval_formula` is a hand-rolled restricted parser (split on `+`/`*`, dict lookup only) — safe.

## Severity counts

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 3 |
| Medium | 10 |
| Low | 13 |
| Info | 2 |
| **Total** | **28** |

---

### [B3-001] One unparseable GST-rate cell aborts the entire bill import job
- **Severity:** High
- **Category:** Broken-flow
- **Location:** `imports/services.py:611-617` (`_preview_bill_line`), `imports/services.py:587-608` (`_normalize_gst_rate`), `imports/services.py:2195-2206` (`_build_preview_lines`)
- **Observation:** `_preview_bill_line` does `gst_rate = str(_normalize_gst_rate(gst_raw, warnings=line_warnings, row=index))` whenever `gst_raw` is truthy. `_normalize_gst_rate` calls `_as_decimal(value, "18")`, which `raise BusinessRuleError(f"Invalid number: {value!r}")` on anything `Decimal()` rejects (e.g. `"18%"`, `"l8"`, `"5 %"`, `"12/18"`). This exception propagates out of `_build_preview_lines` → `apply_extraction` / `parse_structured_file`. Every other bad field (`name`, `quantity`, `unit_price`, `hsn_code`) is collected non-fatally into `_bill_line_errors` and only that line is excluded.
- **Impact:** A supplier CSV/XLSX export whose GST column literally contains `"18%"` (extremely common) fails the whole upload with `400 "Invalid number: '18%'"`. On the LLM path a single noisy OCR GST cell marks the entire multi-page job `FAILED`, discarding all other correctly-read lines.
- **Fix:** Catch `BusinessRuleError`/`InvalidOperation` around the `_normalize_gst_rate` call in `_preview_bill_line`; on failure leave `gst_rate=""`, `include=False`, and add a line-level error, exactly like the other fields. Optionally strip a trailing `%` and whitespace before `_as_decimal`.

### [B3-002] Extra-sheet / inline opening lots for an already-existing product pass validation but are silently dropped at commit
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `imports/services.py:1708-1801` (`_post_extra_opening`), invoked from `imports/services.py:1704` with only `created_products`; validation in `_validate_extra_sheets` (`imports/services.py:1053-1119`) checks against **all** preview SKUs
- **Observation:** `_post_extra_opening` builds `by_sku = {(p.sku or "").casefold(): p for p in created_products if p.sku}` and then `if product is None: continue` for every `opening_lots` / `opening_serials` row. Products matched by SKU to an existing record go into `updates`, never `created_products`. `_validate_extra_sheets` validates lot/serial rows against `preview_skus` (which includes updated rows), so they preview as valid. Inline lots derived from item rows (`_lots_from_item_rows`, `imports/services.py:237-262`) are merged into `extra_sheets["opening_lots"]` and hit the same filter — so a `godown` / `batch_no` / `expiry_date` on an item row that updates an existing SKU is also dropped. The plain `opening_stock` column path (`update_opening`, `imports/services.py:1700`) *does* handle updates; only the lot/serial/godown path does not.
- **Impact:** During a re-import or an import where the SKU already exists, the user sees `valid_rows` counting the row and a `200` commit, but no `StockMovement` / `BatchLot` / `SerialNumber` is created for those lots. Silent opening-stock loss with a success response — serious for an accounting/ERP product.
- **Fix:** Pass `updates` (or re-query all products by the union of item + extra-sheet SKUs) into `_post_extra_opening` and include them in `by_sku`; or explicitly reject extra-sheet rows whose SKU maps to an existing product with a clear message.

### [B3-003] Structured-file bill import persists a lossy `SupplierBillTemplate` — non-trivial inferred formulas silently revert to `quantity`
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `imports/services.py:2142-2192` (`parse_structured_file`), `imports/services.py:2527-2554` (`_save_bill_template`), `imports/services.py:746-752` (`_template_answers`), `qty_formula.py:314-317` (`formula_enum`)
- **Observation:** `parse_structured_file` computes `answers` (can be `cs+quantity`, `boxes*pack`, etc. via `_infer_qty_answers` / the explicit fallback at lines 2158-2163) and stores only `preview["resolved_formula"] = formula_key`. It never sets `preview["resolved_answers"]` or `preview["column_mapping"]`. At commit `_save_bill_template` does `qty_formula = answers.get("qty_formula") or mapping.get("qty_formula")` where `answers = preview.get("resolved_answers")` → `None`, `mapping` → `{}`. `formula_enum` maps anything except `cs*upc+quantity` / `cs*upc+pcs` to `SIMPLE`. So a bill resolved as `cs+quantity` is saved with `line_total_formula=SIMPLE` and no `column_mapping["qty_formula"]`. Next bill from that GSTIN on the LLM path → `_template_answers` returns `{"qty_formula": "quantity"}` and quantities are mis-computed (Pcs used as full qty).
- **Impact:** A learned vendor layout silently corrupts quantities on every subsequent bill for any formula other than the two hard-coded enums. The LLM path avoids this because `apply_extraction` *does* set `preview["resolved_answers"]`.
- **Fix:** In `parse_structured_file` set `preview["resolved_answers"] = answers` (and `preview["qty_formula"]`), matching `apply_extraction`. `_save_bill_template` already round-trips `mapping["qty_formula"]`.

### [B3-004] Structured bill parsing has no row / cell cap (memory DoS)
- **Severity:** Medium
- **Category:** Security
- **Location:** `imports/services.py:868-910` (`_xlsx_best_bill_rows`), `imports/services.py:1010-1026` (`_read_structured_bill` CSV branch)
- **Observation:** `_rows_from_worksheet` (used by master imports / `_read_named_sheets`) enforces `MAX_IMPORT_ROWS` (20k) and `MAX_IMPORT_CELLS` (500k). The bill-import structured path does not: `materialized = [tuple(row) for row in sheet.iter_rows(values_only=True)]` for every sheet, and the CSV branch does `rows = [ ... for row in reader]` with no bound. Only image/PDF uploads are capped (`LLM_BILL_MAX_PAGES`).
- **Impact:** A large or crafted CSV/XLSX uploaded as `PURCHASE_BILL`/`SALES_BILL` is fully materialised in worker memory, then every row becomes a preview line and is JSON-serialised onto the job. Uncapped memory growth per request.
- **Fix:** Apply the same `MAX_IMPORT_ROWS` / `MAX_IMPORT_CELLS` guards in `_xlsx_best_bill_rows` and the CSV reader in `_read_structured_bill`.

### [B3-005] Jobs stuck in `EXTRACTING` are unrecoverable
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `imports/services.py:2117-2139` (`start_extraction`), `imports/tasks.py:101-144` (`extract_purchase_bill_task`), `imports/views.py:167-173` (`retry_extract`)
- **Observation:** `start_extraction` sets `status = EXTRACTING` then schedules the task on commit. The task only marks `FAILED` on `BusinessRuleError` / `SoftTimeLimitExceeded` / generic `Exception`. A hard worker kill (OOM, SIGKILL, `time_limit=480` hard limit, lost broker message) leaves the job in `EXTRACTING` forever. `start_extraction` refuses anything except `UPLOADED`/`FAILED`, so `retry_extract` returns a `BusinessRuleError`. There is no sweeper/watchdog.
- **Impact:** A dropped Celery task strands the ImportJob with no API path to retry or fail it.
- **Fix:** Allow `retry_extract` / `start_extraction` from `EXTRACTING` when `updated_at` is older than the task hard limit, or add a periodic task that marks stale `EXTRACTING` jobs `FAILED`.

### [B3-006] Legacy `.xls` (binary, `application/vnd.ms-excel`) bill upload is mis-parsed as CSV
- **Severity:** Medium
- **Category:** Bug
- **Location:** `imports/views.py:110-113` (`is_structured` uses `BILL_STRUCTURED_TYPES` which includes `application/vnd.ms-excel`), `imports/services.py:1010-1026` (`_read_structured_bill`), `imports/services.py:288-297` (`_decode_csv_text`)
- **Observation:** `_read_structured_bill` only takes the openpyxl branch for names ending `.xlsx`/`.xlsm`. A `.xls` file (or any upload whose browser content-type is `application/vnd.ms-excel`, which Windows also uses for `.csv`) with a non-`.xlsx` name falls to the CSV branch. `_decode_csv_text` tries `utf-8-sig` then `cp1252`; cp1252 decodes almost any byte stream without error, so the OLE2 binary "decodes" into garbage and `csv.DictReader` yields junk rows or "The file has no data rows."
- **Impact:** Confusing failure / garbage preview for a real Excel 97-2003 file instead of a clear "convert to .xlsx or CSV" message.
- **Fix:** Sniff the leading magic bytes in `_read_structured_bill` (`PK\x03\x04` → xlsx; `\xD0\xCF\x11\xE0` → legacy xls → raise a specific `BusinessRuleError`) before deciding CSV vs workbook.

### [B3-007] `SALES_BILL` import stamps the wrong `company_gstin`
- **Severity:** Medium
- **Category:** Bug
- **Location:** `imports/services.py:777-797` (`_resolve_import_company_gstin`), used at `imports/services.py:2709` (`_commit_sales`)
- **Observation:** For `kind == SALES_BILL` the function sets `wanted = str(preview.get("buyer_gstin") ...)` and matches it against `CompanyGstin` rows for the company. On a sales invoice the buyer is the customer; the document *issuer* (us) is `supplier_gstin`. So `wanted` almost never matches a `CompanyGstin` and the code falls through to `is_primary` / lowest-id. The purchase branch is correct (buyer == us).
- **Impact:** A multi-GSTIN company importing a sales invoice it issued under a non-primary GSTIN gets the draft `SalesInvoice` stamped with the primary GSTIN, changing the filing identity / number series. `update_preview` does not expose `company_gstin` for correction.
- **Fix:** For `SALES_BILL`, resolve from `preview.get("supplier_gstin")` (the issuer), validated against the company's `CompanyGstin` set the same way the purchase branch validates `buyer_gstin`.

### [B3-008] Bill of Entry complete/cancel never marks the GST period dirty
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `purchases/boe_services.py:12-58` (`BillOfEntryService.complete` / `cancel`)
- **Observation:** `complete` calls `assert_period_allows_money_amend` and posts GL, but unlike `PurchaseService.complete` (`purchases/services.py:704`), `PurchaseNotesService.complete_credit_note` (`notes_services.py:244`), `.complete_debit_note`, etc., it never calls `mark_period_dirty_if_snapshotted`. `cancel` likewise omits it.
- **Impact:** Completing or cancelling a BoE after a GSTR-3B snapshot has been taken for that month does not flag the snapshot stale, so import ITC (table 4(A)(5)) silently diverges from the filed/snapshotted return.
- **Fix:** Call `mark_period_dirty_if_snapshotted(locked.company, locked.boe_date)` after the state change in both `complete` and `cancel`.

### [B3-009] No quota / rate-limit on LLM bill extraction
- **Severity:** Medium
- **Category:** Gap
- **Location:** `imports/views.py:53-59` (`ImportJobViewSet.permission_classes = [IsAuthenticated, HasCompany, CanImport]`), `imports/views.py:120-132` (upload → `start_extraction`), `imports/tasks.py:102-131` (`extract_purchase_bill` vision calls, up to 10 batches of 5 pages)
- **Observation:** Any user with `CanImport` can upload bills repeatedly; each triggers one or more paid vision-LLM calls (`extract_purchase_bill`). There is a per-file page cap but no per-company/day count, no subscription-tier gate, and no throttle. `retry_extract` has no extra gate.
- **Impact:** Unbounded third-party LLM spend and worker saturation from a single tenant (accidental script or malicious).
- **Fix:** Add a per-company daily/monthly extraction quota (and/or DRF throttle scope) on the upload + retry-extract actions for `BILL_KINDS`, tied to the subscription plan.

### [B3-010] PDF pages rendered at fixed `scale=2` with no pixel-dimension clamp
- **Severity:** Medium
- **Category:** Security
- **Location:** `imports/tasks.py:41-49` (`_file_to_images`)
- **Observation:** `page.render(scale=2)` then `to_pil()` then PNG-encode, for every page. The `hard_cap`/`soft_cap` limits only the page *count*. PDF page dimensions are attacker-controlled; a 200in × 200in page at scale 2 is a multi-hundred-megapixel bitmap.
- **Impact:** A small PDF (few pages, giant media box) OOMs / wedges the extraction worker. The broad `except Exception` marks the job FAILED only if the process survives.
- **Fix:** Compute a per-page scale so the long edge is clamped (e.g. ≤ 2000-3000 px), and/or reject pages whose point dimensions exceed a sane bound before rendering.

### [B3-011] Excel date cell for bill date in structured XLSX fails at commit
- **Severity:** Medium
- **Category:** Bug
- **Location:** `imports/services.py:851-865` (`_xlsx_kv_meta`), `imports/services.py:2557-2584` (`_parse_bill_date`)
- **Observation:** `_xlsx_kv_meta` does `text = str(value).strip()` on raw cell values — it does not go through `_cell_to_import_text`. A real Excel date cell becomes `"2026-06-11 00:00:00"`. `parse_structured_file` stores that as `preview["bill_date"]`; at commit `_parse_bill_date` calls `parse_date("2026-06-11 00:00:00")` (returns `None` — trailing time) then tries a fixed list of `%d-%m-%Y`-style formats, none of which accept a time component, and raises `"Could not parse bill date '...'"`.
- **Impact:** A structured XLSX bill whose header block carries a genuine date cell previews fine but cannot be committed until the user hand-edits the date.
- **Fix:** Route `_xlsx_kv_meta` values through `_cell_to_import_text` (which already emits `date().isoformat()` for midnight datetimes), and/or make `_parse_bill_date` split on whitespace / accept ISO datetime.

### [B3-012] `_commit_products` re-fetches the company row once per preview row
- **Severity:** Medium
- **Category:** Performance
- **Location:** `imports/services.py:194-216` (`_custom_fields_for_commit`, line 203 `job.company.refresh_from_db(fields=["item_custom_field_defs"])`), called per row from `imports/services.py:1624` and `:1660` inside the `for row in preview` loop of `_commit_products`
- **Observation:** When a custom-field header map is present, every created and every updated product row triggers a `SELECT ... FROM company WHERE id = ?`. This is on top of the already-synchronous per-row commit called out in `IMPORT_FLOW_ISSUES.md` IMP-001.
- **Impact:** N extra DB round-trips per products import with custom fields; compounds the existing commit-latency problem.
- **Fix:** Refresh `item_custom_field_defs` once before the loop (or read the live list once) and pass it into `_custom_fields_for_commit`.

### [B3-013] Bill-commit idempotency is weaker than the rest of the codebase
- **Severity:** Medium
- **Category:** Bug
- **Location:** `imports/views.py:194-233` (`commit` action)
- **Observation:** The action does `get_record(...)` at the top and `store_record(...)` only after success, with no `begin_record` placeholder and no `wrap_idempotent`. Purchase/sales invoices use `wrap_idempotent` with a begin-of-request placeholder; master upload uses `begin_record`/`release_record`.
- **Impact:** Two concurrent commits with the same `Idempotency-Key`: both pass `get_record` (nothing stored yet); the first acquires `select_for_update` and commits; the second blocks, then sees `status != PREVIEWED` and returns `400 "Import must be previewed before commit."` instead of replaying the stored `200`. A client retry that races its own in-flight request gets a spurious error.
- **Fix:** Use the same `wrap_idempotent` / `begin_record` placeholder pattern as `PurchaseInvoiceViewSet.create`.

### [B3-014] Numeric validators accept `Infinity` / `NaN`
- **Severity:** Low
- **Category:** Bug
- **Location:** `imports/services.py:381-401` (`_validate_row` PRODUCTS numeric loop), `imports/services.py:548-561` (OPENING_STOCK quantity), `imports/services.py:572-576` (`_as_decimal`)
- **Observation:** `Decimal("Infinity")` and `Decimal("-Infinity")` are valid and do not raise `InvalidOperation`. `Decimal("Infinity") < 0` is `False`, so `purchase_price=Infinity` / `opening_stock=Infinity` pass the `>= 0` checks. `Decimal("NaN")` parses; comparisons then raise `InvalidOperation` which *is* caught, but `NaN` slips through `_as_decimal` (which only guards `InvalidOperation` on construction) in the bill path.
- **Impact:** `Infinity`/`NaN` reaches `bulk_create` / `post_opening` — a DB `DataError` (uncaught → 500) or an absurd stock movement.
- **Fix:** After `Decimal(value)`, reject `not value.is_finite()`.

### [B3-015] Inconsistent numeric coercion between canonical and extra bill columns
- **Severity:** Low
- **Category:** Bug
- **Location:** `qty_formula.py:81-85` (`collect_extras._put` strips `,`), `qty_formula.py:102-125` (`count_pool` uses `_safe_decimal` on `quantity`/`pcs` with no strip), `imports/services.py:650-666` (`_bill_line_errors`)
- **Observation:** `collect_extras` strips thousands separators for `cs`/`upc`/other extras (`.replace(",", "")`), but `quantity`, `pcs`, and `unit_price` are never comma-stripped. `_map_structured_row` copies `quantity`/`unit_price` verbatim from the sheet. A supplier export with `"1,250"` qty or `"1,234.50"` rate → `_as_decimal` failure → line excluded (`unit_price`/`quantity`) while a comma in a `cs` cell is silently accepted.
- **Impact:** Rows with formatted numbers in the main qty/price columns are dropped from structured imports with no clear reason.
- **Fix:** Normalise thousands separators for `quantity`/`pcs`/`unit_price` in `_preview_bill_line` / `_map_structured_row`, consistent with `collect_extras`.

### [B3-016] Dead `rate_warnings` list in `_build_preview_lines`; document-level GST-snap warnings lost on the extraction path
- **Severity:** Low
- **Category:** Dead code / UX
- **Location:** `imports/services.py:2194-2206` (`_build_preview_lines`), compare `imports/services.py:2370-2387` (`update_preview` which *does* aggregate into `preview["warnings"]`)
- **Observation:** `_build_preview_lines` creates `rate_warnings: list[str] = []`, passes it to `_preview_bill_line`, but never returns it or attaches it anywhere. `apply_extraction` / `parse_structured_file` therefore never populate `preview["warnings"]`; only per-line `line["warnings"]` survives.
- **Impact:** GST-rate snap notices ("18.0 snapped… / defaulted to 18") are not surfaced document-level after the initial extraction, only after a user preview edit. Minor cleanup + minor UX loss.
- **Fix:** Return `rate_warnings` from `_build_preview_lines` and set `preview["warnings"]` in `apply_extraction` / `parse_structured_file`, or delete the unused list.

### [B3-017] Bill previews are never truncated on the wire
- **Severity:** Low
- **Category:** Performance
- **Location:** `imports/serializers.py:31-51` (`to_representation`, `get_preview_truncated`, `get_errors_truncated`)
- **Observation:** All three only act when `isinstance(preview, list)`. Bill-import previews are a `dict` (`{"lines": [...] , ...}`), so `PREVIEW_RESPONSE_CAP` never applies and every poll of a many-line bill returns the full `lines` array plus `column_headers`, `resolved_answers`, etc.
- **Impact:** For large bills the full preview is re-sent on every `retrieve`/poll during the preview/clarify loop.
- **Fix:** Also cap `preview["lines"]` (and mirror a `preview_truncated` count) when `preview` is a dict.

### [B3-018] Master imports silently skip duplicate customers/suppliers with no per-row report
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `imports/services.py:1338-1388` (`_commit_customers`), `imports/services.py:1390-1438` (`_commit_suppliers`)
- **Observation:** Rows whose `gstin` / `phone` / lowercased `name` already exist are `continue`d. They are not added to `job.errors`, not reported as skipped, and `created` (the count returned and audit-logged) is silently less than `valid_rows`.
- **Impact:** A user importing a mixed new/existing customer list sees "created N" with no indication which rows were treated as duplicates or why.
- **Fix:** Collect skipped rows into a `job.errors`-style "skipped (already exists)" list surfaced in the response / error CSV.

### [B3-019] `answer_clarifications` does not validate the answer against the offered options
- **Severity:** Low
- **Category:** Gap
- **Location:** `imports/services.py:2294-2332` (`answer_clarifications`), `imports/views.py:175-185` (`clarify`)
- **Observation:** `resolved_answers = {k: v for k, v in answers.items() if v not in (None, "")}` is fed straight into `_apply_cross_check` → `resolve_formula_expr` → `eval_formula`. The clarification's `options` list is never checked. (`eval_formula` is a safe parser, so this is robustness, not RCE — an unknown token just yields `None`/`quantity`.)
- **Impact:** A client can submit an arbitrary `qty_formula` string that gets persisted into `SupplierBillTemplate.column_mapping` and reused on later bills.
- **Fix:** Reject `answers[field]` values that are not among `item["options"][*]["value"]` for that clarification.

### [B3-020] Duplicate BoE number surfaces as a raw IntegrityError
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `purchases/models.py:412-416` (`uniq_bill_of_entry_number_per_company`, no blank exclusion / no pre-check), `purchases/serializers.py:347-388` (`BillOfEntrySerializer` — no uniqueness validation)
- **Observation:** Unlike `PurchaseInvoice`/notes (which check `_assert_duplicate_supplier_bill` and have `condition=~Q(number="")`), nothing pre-validates `boe_number`; a second BoE with the same number raises a DB `IntegrityError` → 500.
- **Fix:** Add a `validate_boe_number` in the serializer (or a service-level check) that raises `BusinessRuleError` on an existing `(company, boe_number)`.

### [B3-021] Structured bill parsing skips the purchase/sales direction sanity check
- **Severity:** Low
- **Category:** Gap
- **Location:** `imports/services.py:2142-2192` (`parse_structured_file` — no `_infer_direction_warning` call), compare `imports/services.py:2235-2238` (`apply_extraction` sets `preview["direction_warning"]`)
- **Observation:** The GSTIN-based "this looks like a sales invoice you issued, not a purchase bill" warning (`_infer_direction_warning`, `imports/services.py:800-824`) is only wired into the LLM path.
- **Impact:** A structured CSV/XLSX uploaded under the wrong flow gets no warning.
- **Fix:** Call `_infer_direction_warning(job.kind, {"supplier_gstin": ..., "buyer_gstin": ...}, job.company)` from `parse_structured_file` and set `preview["direction_warning"]`.

### [B3-022] BoE ITC defaults to `ELIGIBLE` and is claimed on Complete with no 2B gate — opposite of PurchaseInvoice policy
- **Severity:** Info
- **Category:** Improvement
- **Location:** `purchases/models.py:397-399` (`itc_eligibility` default `ELIGIBLE`), `purchases/models.py:432-436` (`claimable_itc`), `purchases/boe_services.py:27-36` (Complete posts ITC unconditionally)
- **Observation:** `PurchaseInvoice.itc_eligibility` defaults to `UNREVIEWED` with the explicit comment "never claim ITC until explicitly marked CLAIMABLE" and `assert_claimable_itc_allowed` enforces a MATCHED GSTR-2B row. `BillOfEntry` defaults to `ELIGIBLE` and `complete()` posts the import ITC with no equivalent 2B/ICEGATE reconciliation gate.
- **Impact:** Inconsistent conservatism; import ITC can be booked before it appears in GSTR-2B / ICEGATE.
- **Fix:** Consider defaulting to a review state, or add an ICEGATE/2B-match assertion mirroring `assert_claimable_itc_allowed`.

### [B3-023] `_validate_row` runs a warehouse lookup per row
- **Severity:** Low
- **Category:** Performance
- **Location:** `imports/services.py:454-463` (`_validate_row`, `from inventory.item_stock import match_warehouse` + `match_warehouse(company, godown)` inside the per-row path), driven from `imports/services.py:1235-1243`
- **Observation:** For a PRODUCTS/OPENING_STOCK file with a `godown` column populated on every row, `match_warehouse` (a DB query) runs once per row, plus a function-local import each call.
- **Impact:** N warehouse queries during preview for godown-heavy files.
- **Fix:** Resolve the distinct godown names once (dict) before the row loop and validate against that map; hoist the import.

### [B3-024] `update_preview` cannot edit `buyer_gstin` / `buyer_name`
- **Severity:** Low
- **Category:** Gap
- **Location:** `imports/services.py:2342-2414` (`update_preview` handles `supplier_name`, `supplier_gstin`, `customer_name`, `bill_number`, `bill_date`, `low_confidence_accepted` only)
- **Observation:** For a `SALES_BILL`, `_resolve_customer` (`imports/services.py:2498-2525`) reads `preview.get("buyer_gstin")` and `preview.get("buyer_name")`, but the preview-edit endpoint exposes neither. `direction_warning` and `_resolve_import_company_gstin` also key off `buyer_gstin`.
- **Impact:** A mis-read buyer GSTIN on a sales bill cannot be corrected before commit; wrong or no customer match.
- **Fix:** Accept `buyer_gstin` / `buyer_name` in `update_preview`.

### [B3-025] `_normalize_gst_rate` silently forces off-slab rates to 18% at commit
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `imports/services.py:587-608` (`_normalize_gst_rate`), commit call sites `imports/services.py:2645` / `:2703` (`required=True`, no `warnings=` list)
- **Observation:** Any rate more than `0.5` away from an allowed slab becomes `Decimal("18")`. On the preview path a `warnings` list is passed and the snap is surfaced; at commit `_commit_purchase`/`_commit_sales` call it with `required=True` and no `warnings` list, so an OCR `13` → `18` (or `2` → `nearest`/`18`) is applied with no record on the invoice.
- **Impact:** A mis-read GST rate is silently normalised into the posted tax on the draft invoice.
- **Fix:** Prefer the rate already shown/confirmed in the preview line rather than re-normalising raw OCR at commit; if re-normalising, attach the reason to the invoice notes / job warnings.

### [B3-026] Purchase PDF recomputes intra/inter-state independently of the posted tax
- **Severity:** Low
- **Category:** Bug
- **Location:** `purchases/pdf.py:188-196` (`render_gst_purchase_bill`), `purchases/pdf.py:74-172` (`_build_hsn_summary_table`), similar in `render_gst_purchase_order` at `:494-495`
- **Observation:** `intra_state` is derived from `party_intra_state(company, supplier.state, supplier.gstin, seller_state=stamp.state, seller_gstin=stamp.gstin)`. If the stamped `company_gstin` has a blank state (or the supplier state is blank) this can disagree with the CGST/SGST vs IGST actually stored on the items. The HSN summary and the totals block then render the wrong tax columns (e.g. CGST/SGST headers with zeros while the invoice posted IGST).
- **Impact:** A statutory purchase bill PDF that misrepresents the tax split.
- **Fix:** Drive the PDF split from the item tax actually posted (`any igst > 0` → inter-state) and use `party_intra_state` only as a fallback when no tax is present.

### [B3-027] Bill import hard-codes `purchase_type=GST` and requires a GST rate on every line
- **Severity:** Info
- **Category:** Partial-feature
- **Location:** `imports/services.py:2648-2652` (`PurchaseInvoice.objects.create(... purchase_type=PurchaseInvoice.PurchaseType.GST ...)`), `imports/services.py:2637-2638` / `:2645` (rejects blank gst_rate, `_normalize_gst_rate(required=True)`)
- **Observation:** Every committed bill becomes a GST invoice; lines without a GST rate are excluded at preview (`include=False`) and rejected again at commit. There is no path for a genuinely non-GST bill or a composition-supplier bill (0% expected).
- **Impact:** Non-GST / composition purchase bills can't be imported without editing the draft afterwards.
- **Fix:** Infer `purchase_type` from supplier registration / extracted totals, or expose it on the preview.

### [B3-028] Imported purchase bills never set `is_reverse_charge` / ITC posture from the bill
- **Severity:** Low
- **Category:** Gap
- **Location:** `imports/services.py:2624-2680` (`_commit_purchase` — no `is_reverse_charge`, `itc_eligibility` left default `UNREVIEWED`)
- **Observation:** RCM is not inferred even when the resolved supplier is unregistered / has no GSTIN. The draft is created as a normal ITC bill. (Mitigated: `PurchaseService.complete` runs `_unregistered_rcm_gate` and will demand `confirm_no_rcm` before it can be completed.)
- **Impact:** The imported draft's RCM/ITC state does not reflect the bill; relies entirely on the user catching it at Complete.
- **Fix:** When `_resolve_supplier` yields an unregistered/blank-GSTIN supplier, default `is_reverse_charge` accordingly (or add a preview warning) so the draft is correct before Complete.

---

## Coverage notes (tests)

- `tests/test_purchase_bill_import.py` is thorough on qty-formula inference, clarification loop, template learning, multi-page merge, and structured XLSX. **Gaps:** no test for a bad/`"18%"` GST cell aborting the job (B3-001); no test for structured-import template persistence of a non-standard formula (B3-003); no SALES_BILL multi-GSTIN stamping test (B3-007); no `.xls` upload test (B3-006); no oversized structured file test (B3-004).
- `tests/test_imports.py` covers void / void-rows / serials / fuzzy headers well. **Gaps:** no test for extra-sheet `opening_lots` targeting an *existing* product (B3-002); no `Infinity`/`NaN` numeric test (B3-014); no test that duplicate customers are reported (they are only asserted absent by count, B3-018).
- `tests/test_gst08_bill_of_entry.py` covers GL + GSTR-3B flow. **Gaps:** no assertion that completing/cancelling a BoE marks a snapshotted period dirty (B3-008); no duplicate `boe_number` test (B3-020).
- No dedicated tests for `imports/tasks.py` timeout / stuck-EXTRACTING handling (B3-005) or PDF page-dimension handling (B3-010).

---

# Deep code review — cluster B4: `backend/payments/**` + `backend/banking/**`

Scope reviewed line-by-line:
- `backend/payments/`: models.py, services.py, views.py, webhook_views.py, serializers.py, gateway.py, upi.py, recon.py, dunning.py, holding.py, tasks.py, management/commands/reconcile_gateway_captures.py, urls.py, apps.py
- `backend/banking/`: models.py, services.py, views.py, serializers.py, fiu_adapter.py, urls.py, apps.py
- Supporting reads: `accounting/services.py` (post_receipt_refund), `ledgers/services.py` (outstanding), `core/idempotency.py`
- Tests read for intent: `tests/test_phase3_payments.py`, `test_payment_webhook_adversarial.py`, `test_w0_webhook_holding.py`, `test_payment_allocation.py`, `test_a07_dunning.py`, `test_sprint2_purchases_payments.py`, `test_intg01_rebit_crypto.py`, `test_gap_closure.py`, `test_wave17_comms_bank_tenancy.py`

## Severity counts

| Severity | Count |
|----------|-------|
| Critical | 3 |
| High     | 8 |
| Medium   | 17 |
| Low      | 8 |
| Info     | 2 |
| **Total**| **38** |

---

### [B4-001] Partial gateway refund double-unwinds the books on outbox retry
- **Severity:** Critical
- **Category:** Data-integrity
- **Location:** `payments/services.py:1257-1259` (`_unwind_refund_books`), `payments/tasks.py:90-99` (`execute_gateway_refund`)
- **Observation:** `_unwind_refund_books` guards re-entry only with `if raw.get("books_unwound"): return` (line 1181), and at the end writes `"books_unwound": bool(full)` (line 1259). For a **partial** refund `full=False`, so `books_unwound` is never set to `True`. `execute_gateway_refund` computes `already_unwound = bool(raw.get("books_unwound")) or gp.status == REFUNDED` (line 90) — both are false for a partial refund whose `gp.status` is `PARTIALLY_REFUNDED`.
- **Impact:** If `execute_gateway_refund` crashes/killed after `adapter.refund()` succeeds and after `_unwind_refund_books` runs but before `row.save(status=SUCCEEDED)` (line 100-103), the outbox row is left `IN_PROGRESS`. `retry_pending_gateway_refunds` (`tasks.py:127-140`) re-queues it after the 10-min cutoff; `execute_gateway_refund` re-runs, `already_unwound` is still `False`, and `_unwind_refund_books` reverses more allocations and posts **another** `post_receipt_refund` JE (`purpose="REFUND_{je_seq}"` bumps, so no dedup collision at `PostingService.post`). Books now show 2× the refund; provider refunded once. AR / bank / MDR expense all corrupted.
- **Fix:** Persist an idempotency marker for partial refunds too — e.g. record each applied refund by `idempotency_key` in `raw["partial_refunds"]` and have `_unwind_refund_books` no-op when that key is already present; or gate the whole unwind on the `GatewayRefundOutbox` row transition (only unwind when this call is the one that flipped `IN_PROGRESS→SUCCEEDED`).

---

### [B4-002] `refund_idempotency_key` has no nonce → two legitimate equal-amount partial refunds book twice but the provider refunds once
- **Severity:** Critical
- **Category:** Data-integrity
- **Location:** `payments/services.py:22-25`, `payments/gateway.py:36-42` (`_stable_refund_key`)
- **Observation:** `refund_idempotency_key(gateway_payment_id, amount)` returns `f"bb-refund-{gateway_payment_id}-{amt}"` — keyed only on payment id + amount. The `GatewayRefundOutbox` model comment (PAY-12, `models.py:426-441`) explicitly says the DB was relaxed to allow "two legitimate equal-amount partial refunds", but the **provider** idempotency key was not given a corresponding sequence/nonce.
- **Impact:** Refund ₹100 of a ₹500 capture, then genuinely refund another ₹100 later. Second `adapter.refund(..., idempotency_key="bb-refund-<id>-100.00")` is treated by Razorpay/Cashfree as a replay of the first and returns the original refund object **without moving money**. `refund_gateway_payment` / `execute_gateway_refund` then happily unwind another ₹100 in the books. Customer is under-refunded by ₹100; books over-state the refund.
- **Fix:** Include a per-refund discriminator in the key (outbox row id, or a `refund_seq` on `GatewayPayment.raw_payload`). Keep the *retry* of one logical refund stable by storing the generated key on the `GatewayRefundOutbox` row (already a column) and always reusing it, but generate a fresh key per new logical refund.

---

### [B4-003] Provider refund HTTP call runs inside the DB transaction; a crash between provider-success and commit leaves books vs bank silently diverged
- **Severity:** Critical
- **Category:** Data-integrity
- **Location:** `payments/services.py:1268` (`@transaction.atomic`) + `payments/services.py:1333-1350` (`adapter.refund(...)` called inside it)
- **Observation:** `refund_gateway_payment` is `@transaction.atomic`. The synchronous `adapter.refund(...)` (a 30s HTTP round-trip, `gateway.py:373-381`) is invoked inside that atomic block. The `GatewayRefundOutbox` fallback row is created **only** in the `except Exception` handler.
- **Impact:** If the worker dies (deploy, OOM, timeout) after `adapter.refund()` returns success but before the outer transaction commits, the whole transaction rolls back: no outbox row, `gp.status` still `CAPTURED`, receipt still `POSTED`, no allocations reversed — but the customer's money **has left** the merchant account. `payment_health` does not flag a `CAPTURED` gp, so nothing surfaces it. It only self-heals if a human happens to press "refund" again (which then reuses the idempotent key).
- **Fix:** Move the provider call out of the DB transaction: commit a `PENDING` `GatewayRefundOutbox` row first (transaction #1), then call `adapter.refund()` from the task, then unwind books (transaction #2) — which is already the outbox design; the synchronous path should not shortcut it. At minimum, wrap so that a provider success always persists an outbox/`gp` marker in its own committed transaction before books work.

---

### [B4-004] Razorpay refund webhook parses the **payment** amount, not the refund amount → a dashboard partial refund unwinds the full capture
- **Severity:** High
- **Category:** Bug / Data-integrity
- **Location:** `payments/gateway.py:325-334` (`RazorpayAdapter.parse_webhook`), consumed at `payments/webhook_views.py:191-210`
- **Observation:** `parse_webhook` builds `payment = (payload.get("payment") or {}).get("entity") or ...` and takes `amount` from `payment.get("amount")` (paise of the original payment). It never inspects `payload["refund"]["entity"]["amount"]`. The webhook view's `REFUNDED` branch then calls `PaymentService.refund_gateway_payment(gateway_payment=gp, amount=getattr(event, "amount", None), reason="webhook", skip_gateway=True)` (`webhook_views.py:202-207`).
- **Impact:** A partial refund issued from the Razorpay dashboard emits `refund.processed`; `event.amount` = the **entire** captured amount, so `refund_gateway_payment` computes `is_full_unwind=True`, marks the receipt `REFUNDED`, reverses every allocation and posts a full refund JE, while only a fraction was actually refunded to the customer.
- **Fix:** In `parse_webhook`, when the event is a `refund.*` event, read the amount (and id) from the `refund` entity: `refund = (payload.get("refund") or {}).get("entity")`; set `event.amount = refund.amount/100`. Add a distinct `WebhookEvent` field for refund amount vs payment amount so the view is unambiguous.

---

### [B4-005] Razorpay `refund.processed` is misclassified as `CAPTURED` because status is read from the payment entity
- **Severity:** High
- **Category:** Bug
- **Location:** `payments/gateway.py:335-355`
- **Observation:** `_RZP_MONEY_EVENTS` (line 308-316) whitelists `refund.processed` / `refund.created` / `refund.failed`, but `parse_webhook` derives `status` from `payment.get("status")` mapped through `status_map` (`captured→CAPTURED`, `paid→CAPTURED`, `refunded→REFUNDED`). After a **partial** refund the payment entity's status is still `"captured"`; after a full refund it is `"refunded"`. So `refund.processed` for a partial refund yields `event.status == "CAPTURED"`.
- **Impact:** `webhook_views.py:212` (`if event.status != "CAPTURED"`) is false, so the partial-refund webhook falls through into `PaymentService.finalize_gateway_payment(...)` — re-running capture/allocation logic on an already-captured payment instead of the refund path. Depending on link state this can re-mark the link `PAID`, retry allocation, or emit `payment_link.paid` again.
- **Fix:** Branch on the Razorpay `event` name, not the payment entity status: `refund.*` → `REFUNDED`, `payment.failed` → `FAILED`, `payment.captured`/`payment_link.paid`/`order.paid` → `CAPTURED`. Only fall back to entity-status inference for bare probe bodies.

---

### [B4-006] `PaymentAllocation` create has no idempotency guard → double-submit returns HTTP 500
- **Severity:** High
- **Category:** Bug / Broken-flow
- **Location:** `payments/views.py:311-361` (`PaymentAllocationViewSet.create`), `payments/services.py:411-418` / `468-475`
- **Observation:** `CustomerReceiptViewSet.create` and `SupplierPaymentViewSet.create` honour an `Idempotency-Key` header (`begin_record`/`store_record`), and `core/idempotency.py:22-29` lists `"allocation_create"` in `MONEY_IDEMPOTENCY_SCOPES` — but `PaymentAllocationViewSet.create` implements no idempotency handling at all. The service does a plain `PaymentAllocation.objects.create(...)`; the partial unique constraint `uniq_alloc_receipt_sales_invoice` (`models.py:204-210`) raises `IntegrityError` on a duplicate (receipt, sales_invoice) with `reversed_at IS NULL`.
- **Impact:** A retried / double-clicked allocation for the same (receipt, invoice) pair raises an uncaught `IntegrityError` → 500 to the client instead of a clean idempotent 200/409. Also blocks the legitimate case of two separate partial allocations of one receipt to the *same* invoice (constraint forbids it entirely).
- **Fix:** Wire `Idempotency-Key` through `PaymentAllocationViewSet.create` using scope `"allocation_create"`; catch `IntegrityError` in the service and translate to `BusinessRuleError` ("this receipt is already allocated to that invoice"). Decide intentionally whether multiple partial allocations to one invoice should be permitted (if yes, drop/relax the unique constraint and rely on the headroom check).

---

### [B4-007] Bank statement import 500s on legitimately identical intraday transactions
- **Severity:** High
- **Category:** Bug / Broken-flow
- **Location:** `payments/recon.py:144-146` (`line_hash`), `payments/views.py:597-621` (`BankStatementViewSet.upload`)
- **Observation:** `line_hash = sha256(f"{txn_date}|{amount}|{utr}|{narration}")`. The constraint `uniq_bank_statement_line_hash` (`models.py:355-360`) makes non-empty hashes unique per `(company, statement)`. `upload` inserts each line with a bare `BankStatementLine.objects.create(...)` inside one `transaction.atomic()` with no `try/except`.
- **Impact:** Two genuine transactions on the same day with the same amount, same (often blank) UTR and same narration — common for cash/UPI ("UPI/CR/PhonePe") — produce an identical hash. The second insert raises `IntegrityError`, aborting the **entire** upload with a 500; the user cannot import that statement at all.
- **Fix:** Include a positional discriminator in the hash (row index within the file, or running balance / `balance_after`), or de-dup within the parse and append a `:n` suffix for repeats, or catch the `IntegrityError` per row and skip with a reported "N duplicate rows ignored" count.

---

### [B4-008] Gateway refund GL is not period-gated → refund JE posts into a locked GST period
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `payments/services.py:1267-1418` (`refund_gateway_payment`), `payments/services.py:1176-1265` (`_unwind_refund_books`), `accounting/services.py:1011-1056` (`post_receipt_refund`)
- **Observation:** `create_receipt`, `create_supplier_payment`, `allocate_*`, `void_*` and `reverse_allocation` all call `assert_period_allows_money_amend(...)`. `refund_gateway_payment` / `_unwind_refund_books` do **not**. `_unwind_refund_books` calls `reverse_allocation` (which does gate on the *allocation's* money date), but the refund JE itself — `PostingService.post_receipt_refund(receipts[0], ..., entry_date=receipt.receipt_date or localdate())` — has no gate.
- **Impact:** Refunding a gateway payment whose receipt date sits in a closed/filed GST period silently writes a `REFUND` journal entry into that locked period, breaking the "no money amendments in a closed period" invariant the rest of the module enforces. `books_hold_reason` shows the team knows period locks occur here (it maps `PERIOD_LOCKED` for the capture path only).
- **Fix:** Gate the refund on `assert_period_allows_money_amend(gp.company, <refund date>)` and, when the period is locked, park (mirror `_raise_or_park` / `CAPTURED_PENDING_BOOKS` handling) instead of posting. Post the refund JE on `localdate()` when the original date is locked (as `void_*` does via `_reverse_money_document_journal`).

---

### [B4-009] AA ingest holds a DB transaction open across the FIU HTTP fetch and ignores consent status
- **Severity:** High
- **Category:** Bug / Broken-flow / Security
- **Location:** `banking/views.py:32-113` (`AaIngestView.post`, `@transaction.atomic`), `banking/fiu_adapter.py:47-98` (`fetch_live_transactions_for_consent`)
- **Observation:** `AaIngestView.post` is `@transaction.atomic`. Inside it, `use_live_fiu` triggers `fetch_live_transactions_for_consent` (a `urllib` GET, `timeout=12`) and `use_mock_fiu` calls the mock, then rows are upserted and `match_aa_to_receipts` runs. `AaConsent` is created with a client-supplied `status` (`AaIngestSerializer` default `ACTIVE`) and there is **no check that the consent is `ACTIVE` / not `REVOKED`/`EXPIRED`** before fetching or storing transactions.
- **Impact:** (1) A slow/hanging FIU keeps a write transaction (and any row locks from the later `match_aa_to_receipts` `select_for_update`) open for up to 12s+, under `IsOwner` with no throttle — trivial to pile up. (2) Financial data can be pulled and persisted for a consent the customer has revoked or that has expired, an AA/RBI compliance problem; a caller can also just POST `status:"ACTIVE"` for any `consent_id`.
- **Fix:** Fetch outside the atomic block; open a short transaction only for the upsert + match. Reject ingest when `consent.status not in (PENDING, ACTIVE)` (and when `ACTIVE` but past its validity window). Do not let the client set `status` to `ACTIVE` — derive it from a verified consent artefact.

---

### [B4-010] `reconcile_gateway_captures` no-ops entirely when `GATEWAY_HOLDING_STATE` is disabled → parked captures stranded
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `payments/services.py:1092-1099`
- **Observation:** `reconcile_gateway_captures` starts with `if not gateway_holding_enabled(): return 0, 0`. Rows already in `CAPTURED_PENDING_BOOKS` (parked while the flag was on, or by an earlier deploy) are then never retried and never auto-refunded.
- **Impact:** Toggling the flag off (or a config drift) permanently strands verified captures: money is at the provider, no receipt/GL, and the only worker that could resolve them is short-circuited. `payment_health` still shows the `GATEWAY_CAPTURE_HOLDING` alert, but there is no path to clear it without manual DB/console work.
- **Fix:** Only skip the *parking* behaviour when the flag is off; always process existing `CAPTURED_PENDING_BOOKS` rows (retry books, or refund terminal-reason rows). Or add a management/admin action to drain the holding queue regardless of the flag.

---

### [B4-011] `finalize_gateway_payment` ALREADY_PAID (non-holding) path: the `FAILED` write is rolled back by the very next `raise`
- **Severity:** Medium
- **Category:** Bug
- **Location:** `payments/services.py:896-909`
- **Observation:** Inside the `@transaction.atomic` `finalize_gateway_payment`, when the link is already `PAID` with a `paid_receipt` and holding is off:
  ```python
  existing.status = GatewayPaymentStatus.FAILED
  existing.save(update_fields=["status", "updated_at"])
  raise BusinessRuleError("Payment link is already paid; duplicate capture ignored.")
  ```
  The `raise` aborts the transaction, so the `FAILED` save is undone; `existing` stays `CREATED`.
- **Impact:** A duplicate provider payment id against a paid link is left in `CREATED` forever (dead row), not `FAILED` as intended. Retries / reporting treat it as an unfinished capture.
- **Fix:** Persist the terminal status in its own committed transaction (or `park_gateway_payment` in both branches), then return/raise. Don't mutate-then-raise in the same atomic.

---

### [B4-012] `payment_link.paid` event emitted even when the link ends `PARTIALLY_PAID`
- **Severity:** Medium
- **Category:** Bug
- **Location:** `payments/services.py:1079-1089`
- **Observation:** The `if total_captured ... >= link.amount and allocated_ok:` / `else:` block sets `link.status` to `PAID` or `PARTIALLY_PAID`, but `emit("payment_link.paid", document=link, ..., event="payment_link.paid")` (line 1089) is unconditional, outside the branch.
- **Impact:** Downstream subscribers (notifications, webhooks, analytics, "mark invoice paid" side-effects) receive a `payment_link.paid` signal for a link that is only partially collected — premature "paid" notifications to staff/customer, wrong dashboards.
- **Fix:** Emit `payment_link.paid` only in the fully-paid branch; emit a distinct `payment_link.partially_paid` event otherwise.

---

### [B4-013] Partial-refund double-submit appends multiple `partial_refunds` / unwinds while the provider refunds once
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `payments/services.py:1319-1407` (partial branch of `refund_gateway_payment`), `payments/views.py:494-512` (`refund` action, no idempotency)
- **Observation:** The `refund` action has no `Idempotency-Key` handling. For a partial amount, `refund_gateway_payment` reads `already` from `raw["partial_refunds"]` (line 1320-1326), calls `_unwind_refund_books(full=is_full_unwind)`, then appends `{"amount": ..., "books": True}` and sets `PARTIALLY_REFUNDED`. Two concurrent identical requests both read `already` before either commits; both unwind and both append. Sequential double-clicks also each append (until the running total crosses `remaining`).
- **Impact:** Books show 2×N refunded (extra reversed allocations + extra `REFUND_{seq}` JEs), provider refunded N once (idempotent key, see B4-002). `payment_health`'s `GATEWAY_PARTIAL_REFUND_UNRECONCILED` only checks `books` flag falsity, so this divergence is invisible.
- **Fix:** Add idempotency to the `refund` action; `select_for_update` the `GatewayPayment` (already done) **and** recompute `already` after the lock; dedupe on a per-refund idempotency key stored in `partial_refunds`.

---

### [B4-014] Auto bank-match treats an arbitrary `receipt.reference` substring in the narration as a "hard anchor"
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `payments/recon.py:288-314` (`_has_hard_recon_anchor`), `payments/recon.py:159-222` (`score_match`), `payments/views.py:634-646` (`commit` auto-match)
- **Observation:** `score_match` sets `target_utr = normalize_utr(receipt.utr or receipt.reference)` — falling back to the free-text `reference`. `_has_hard_recon_anchor` returns `True` when `target_utr and target_utr in narr.replace(" ", "")`, i.e. when the receipt's *reference text* appears anywhere in the bank narration. With `auto_match_bank_exact` on, `commit` then auto-creates a `ReconMatch` (confidence forced to `s["confidence"]`).
- **Impact:** A receipt whose `reference` is something generic ("NEFT", a customer name fragment, an invoice number that also appears in an unrelated line) can be auto-reconciled to the wrong bank line as long as the amount is equal and it is the only candidate. Auto-commit should require a real UTR/RRN or the exact document number, not any reference substring.
- **Fix:** Only treat `receipt.utr` (a real UTR) or the exact `receipt.number` as a hard anchor. Never use `reference` for the anchor test; keep it only as a soft `+points` signal.

---

### [B4-015] `parse_bank_csv` silently drops rows with unparseable dates, but 500s on unparseable amounts
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `payments/recon.py:116-135` (date loop `if txn_date is None: continue`), `payments/recon.py:26-41` (`_parse_amount` raises `BusinessRuleError`)
- **Observation:** A row whose date matches none of the 5 formats is `continue`d — no error, no count. A row whose amount fails `Decimal(...)` raises `BusinessRuleError("Invalid amount: ...")`, which `upload` does not catch → 500.
- **Impact:** (1) Partial silent import: transactions vanish from the imported statement with no signal, so reconciliation looks "complete" while real bank movements are missing. (2) Inconsistent failure mode — one malformed cell aborts the whole upload, another is swallowed.
- **Fix:** Collect per-row parse errors, return them with a count ("42 of 45 rows imported, 3 skipped: …"); treat bad date and bad amount the same way (both skip-with-report, or both hard-fail).

---

### [B4-016] No way to undo a confirmed `ReconMatch`; `BankStatement` VOID status is unreachable
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `payments/views.py:625-699` (`BankStatementViewSet` — only `upload`/`commit`), `payments/views.py:702-861` (`ReconViewSet` — only `list`/`suggest`/`confirm`/`create-receipt-from-line`), `payments/models.py:307-311` (`BankStatementStatus.VOID`)
- **Observation:** Once `_confirm_match` sets `line.match_status = MATCHED` and creates a `ReconMatch` (OneToOne on the line, unique on receipt / supplier_payment), there is no endpoint to reverse it. `BankStatementStatus.VOID` exists in the enum but nothing transitions a statement to it.
- **Impact:** An operator who confirms a wrong match (or auto-match confirms wrongly, see B4-014) cannot fix it without direct DB access. A statement imported for the wrong account / period cannot be voided.
- **Fix:** Add `recon/unmatch` (delete `ReconMatch`, reset line to `UNMATCHED`) and `statements/{id}/void` (only when no committed dependent side-effects) actions with `CanCancelDocuments`.

---

### [B4-017] `payment_health` fan-out: up to 50 `sales_invoice_outstanding` calls + full scan of unmatched lines per request
- **Severity:** Medium
- **Category:** Performance
- **Location:** `payments/services.py:1474-1548` (`_payment_health_uncached`)
- **Observation:** Loops `open_invs = SalesInvoice.objects.filter(...)[:50]` calling `LedgerService.sales_invoice_outstanding(inv)` per invoice (each recomputes CN/DN/allocation sums), plus `dup_utrs` aggregate, plus iterating **every** committed unmatched `BankStatementLine` for aging, plus several `GatewayRefundOutbox`/`GatewayPayment` scans. Cached only 60s (`payment_health`).
- **Impact:** For a tenant with many open invoices / unmatched lines this is a heavy multi-second query burst every 60s per active dashboard; the code comment (R3-007) acknowledges it but the cache TTL is short and the work is unbounded.
- **Fix:** Use `LedgerService.bulk_*` aggregates (there is already `bulk_customer_outstanding`); `.aggregate`/`.values` the aging buckets in one grouped query; raise the cache TTL and/or invalidate on receipt/allocation writes.

---

### [B4-018] `BankStatementViewSet.commit` auto-match is N+1 (suggest + anchor query per unmatched line)
- **Severity:** Medium
- **Category:** Performance
- **Location:** `payments/views.py:634-646`
- **Observation:** `for line in statement.lines.filter(match_status=UNMATCHED): suggestions = suggest_matches(company, line); ...`. `suggest_matches` itself runs a windowed `CustomerReceipt`/`SupplierPayment` query + a `ReconMatch` `values_list` per line; `is_exact_unique_suggestion` → `_has_hard_recon_anchor` runs another `CustomerReceipt`/`SupplierPayment` `.filter(pk=...)` per line.
- **Impact:** Committing a statement with hundreds of lines issues hundreds×several queries synchronously inside the request; commit latency scales with statement size.
- **Fix:** Batch: prefetch matched receipt/payment ids once; consider moving auto-match to a background task and returning `202`.

---

### [B4-019] Unvalidated external `amount` from FIU crashes the atomic AA ingest
- **Severity:** Medium
- **Category:** Bug
- **Location:** `banking/fiu_adapter.py:92` (`Decimal(str(row.get("amount") or "0"))`), `banking/views.py:89` (`Decimal(str(row.get("amount") or "0"))`)
- **Observation:** Both the live FIU parser and the ingest view coerce the provider-supplied amount with `Decimal(str(...))` and no `try/except`. A non-numeric value (`"1,500.00"`, `"NA"`, `None`-as-string) raises `decimal.InvalidOperation`.
- **Impact:** One malformed transaction from the FIU aborts the whole `@transaction.atomic` ingest (all consent + transaction upserts rolled back), returning a 500. A hostile/broken FIU can wedge ingest entirely.
- **Fix:** Wrap per-row coercion; skip + report bad rows. Strip thousands separators. Validate `amount` range/scale before persisting.

---

### [B4-020] Live AA / ReBIT flow does not verify consent-artefact or FI-payload signatures; crypto derivation self-admittedly unvalidated
- **Severity:** Medium
- **Category:** Security / Partial-feature
- **Location:** `banking/fiu_adapter.py:209-329` (`ReBITClient`), `banking/fiu_adapter.py:133-188` (`_rebit_session_key` / `decrypt_fi_data`)
- **Observation:** `ReBITClient` docstring lists "GET /Consent/handle/{h} -> consent artefact (signed)" but `decrypt_fi_records` / `request_fi_data` never verify any JWS/detached-JWS signature from the CR or FIP; payloads are trusted after a bearer-token HTTP call. `_rebit_session_key` carries "still validate the exact HKDF salt / IV derivation against your live aggregator's sandbox".
- **Impact:** If `ENABLE_AA_LIVE` is ever switched on with this code, forged/altered FI data (or a MITM on the FIU URL) would be ingested as authentic bank transactions; the ECDH/HKDF/GCM parameters may not interoperate, silently yielding garbage plaintext that then flows into matching.
- **Fix:** Implement Sahamati JWS verification of the signed consent artefact and of each FI block before decryption; pin/verify TLS to `FIU_BASE_URL`; keep `ENABLE_AA_LIVE` hard-gated and documented as unverified until sandbox-tested.

---

### [B4-021] `finalize_gateway_payment` adopt-existing-receipt lookup uses the raw provider id even after the internal UTR was suffixed
- **Severity:** Medium
- **Category:** Bug
- **Location:** `payments/services.py:967-999` (esp. 970 vs 977-981)
- **Observation:** `_utr = (existing.internal_utr or provider_payment_id)[:64]` is used for the *new* receipt, but the "adopt a manually pre-recorded receipt" search is `CustomerReceipt.objects.filter(company=company, utr=provider_payment_id[:64])` — it never tries `existing.internal_utr`.
- **Impact:** On a `UTR_CLASH` retry where a suffixed `internal_utr` was previously assigned and a receipt already exists under that suffixed UTR, the lookup misses it and `create_receipt` is attempted again → either a second receipt for the same capture or another clash/park cycle.
- **Fix:** Search on both `provider_payment_id[:64]` and `existing.internal_utr` (and on `gateway_payment=existing`, which it already does first) before deciding to create.

---

### [B4-022] `refund_gateway_payment` holds the `GatewayPayment` row lock across the 30s provider HTTP call
- **Severity:** Medium
- **Category:** Performance
- **Location:** `payments/services.py:1274` (`select_for_update().get`) … `1346` (`adapter.refund`) — same atomic block
- **Observation:** The `gp` row is `select_for_update`-locked at the top of the atomic block; `adapter.refund()` (up to `timeout=30`) executes before the block ends.
- **Impact:** Any concurrent operation touching that `GatewayPayment` (webhook finalize, health scan `select_for_update`, another refund) blocks for the duration of the outbound HTTP call; a slow provider serialises unrelated webhook processing for that payment.
- **Fix:** Same remedy as B4-003 — provider call outside the locked transaction; lock only for the short state-transition writes.

---

### [B4-023] `public_payment_link` (GET, AllowAny) mutates the link to `EXPIRED`
- **Severity:** Medium
- **Category:** Bug / UX
- **Location:** `payments/webhook_views.py:55-59`
- **Observation:** The public GET endpoint does `link.status = PaymentLinkStatus.EXPIRED; link.save(update_fields=["status", "updated_at"])` when `expires_at` has passed.
- **Impact:** A `GET` performs a write (side-effect on a "safe" method); an unauthenticated caller can drive `EXPIRED` transitions by polling; under load, many concurrent GETs of the same expired link all issue writes.
- **Fix:** Compute "expired" for the response without persisting, and let a periodic job (or the webhook path) own the state transition. If persistence on read is desired, guard with `PaymentLink.objects.filter(pk=..., status__in=[...]).update(status=EXPIRED)` (single conditional UPDATE, no race).

---

### [B4-024] `finalize_gateway_payment` early "already CAPTURED" retry-allocation branch can raise outside its guard
- **Severity:** Medium
- **Category:** Bug
- **Location:** `payments/services.py:793-819`
- **Observation:** When `existing.status == CAPTURED`, the code recomputes `alloc_amt = min(unalloc, outstanding)` and calls `PaymentService.allocate_receipt(...)` inside `try/except BusinessRuleError`. `allocate_receipt` can also raise plain `IntegrityError` (e.g. the `uniq_alloc_receipt_sales_invoice` race with a concurrent allocation) which is **not** caught here.
- **Impact:** A concurrent allocation on the same (receipt, invoice) turns an idempotent "webhook re-delivery of a captured payment" into a 500, causing the provider to keep retrying a payment that is already fully settled.
- **Fix:** Catch `IntegrityError` alongside `BusinessRuleError` in this block (as the create path at lines 1019/1042 already does), or wrap in a savepoint and ignore.

---

### [B4-025] AA `amount+date` fallback match ignores whether the receipt is already bank-reconciled
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `banking/services.py:47-100` (`_match_one`)
- **Observation:** `base_qs` filters `CustomerReceipt` by company, `POSTED`, amount±tol, date ±7d, and "not already pointed at by an `AaTransaction`". It does **not** exclude receipts that already have a `ReconMatch` (bank-statement reconciliation) or are already fully allocated. With exactly one such candidate it is auto-linked as `method="amount_date"`.
- **Impact:** An AA credit gets attributed to a receipt that actually corresponds to a *different* real bank credit already matched via CSV import — a misleading `matched_payment`/`_match_method` that operators may trust when clearing the AA queue. (Impact is limited because the FK is informational with no GL effect.)
- **Fix:** Exclude receipts with an existing `ReconMatch` from the `amount_date` fallback (keep them eligible only for an exact UTR/RRN `ref` match), and prefer receipts with remaining unallocated balance.

---

### [B4-026] `_reminder_count` / `_next_due_bucket` cause slow dunning escalation ("3-day" message sent to a 40-day-overdue invoice)
- **Severity:** Medium
- **Category:** Bug
- **Location:** `payments/dunning.py:82-107`, `payments/dunning.py:243-281`
- **Observation:** `_next_due_bucket` returns the **lowest** configured bucket that is `<= days_overdue` and unsent. `run_dunning_for_company` sends at most one reminder per invoice per day and caps at `dunning_max_reminders`. `remind_invoice` records `days_overdue=bucket` (the bucket, not the real overdue days).
- **Impact:** An invoice first picked up at 40 days overdue with buckets `(3,7,14)` sends the "due 3 days ago" reminder today, "7" tomorrow, "14" the day after — three gentle nudges spread over 3 days regardless of true severity, and then it is capped out. The customer never gets an escalation appropriate to 40 days. `days_overdue` stored is misleading for analytics.
- **Fix:** Select the **highest** bucket `<= days_overdue` that is unsent (escalate straight to the strongest tier the age warrants), and store the real `days_overdue`.

---

### [B4-027] `run_dunning_all` duplicates `run_ar_dunning_task` with drift risk
- **Severity:** Low
- **Category:** Improvement / Dead code
- **Location:** `payments/dunning.py:284-299` vs `payments/tasks.py:144-161`
- **Observation:** Two near-identical company-loop dunning drivers. `run_dunning_all` also accepts a `now` kwarg the task version drops.
- **Impact:** Future fixes (RLS handling, opt-out, quiet-hours) can land in one and not the other; unclear which is the entrypoint.
- **Fix:** Have `run_ar_dunning_task` call `run_dunning_all` (or delete `run_dunning_all` if only the Celery task is scheduled).

---

### [B4-028] Cashfree link amount is converted through `float`
- **Severity:** Low
- **Category:** Bug
- **Location:** `payments/gateway.py:441` (`"link_amount": float(format(Decimal(amount).quantize(Decimal("0.01")), "f"))`)
- **Observation:** Money is quantized to 2dp, formatted to string, then cast to `float` for the JSON body.
- **Impact:** Re-introduces binary-float representation for the amount actually sent to the provider; for most values harmless but a latent source of 1-paise mismatches / `AMOUNT_MISMATCH` parks on the return webhook.
- **Fix:** Send the quantized decimal as a JSON string (`str(Decimal(amount).quantize(Decimal("0.01")))`) — Cashfree accepts string amounts — or keep it as a `Decimal` and rely on a decimal-aware JSON encoder.

---

### [B4-029] Sandbox webhook amounts are rupees while Razorpay parsing assumes paise
- **Severity:** Low
- **Category:** Improvement
- **Location:** `payments/gateway.py:217-228` (`SandboxAdapter.parse_webhook`, `amount=Decimal(str(data.get("amount","0")))`) vs `payments/gateway.py:329-334` (Razorpay `/100`)
- **Observation:** The two adapters interpret the wire `amount` in different units; sandbox tests therefore exercise a different code shape than production.
- **Impact:** Amount-mismatch / rounding bugs that only bite on the paise-conversion path (Razorpay) are invisible to sandbox-based tests.
- **Fix:** Make the sandbox payload paise-denominated like Razorpay (and update fixtures), so the parsing/quantization path under test matches production.

---

### [B4-030] `GatewaySettingsView.patch` saves the whole `Company` row (no `update_fields`)
- **Severity:** Low
- **Category:** Bug
- **Location:** `payments/views.py:893-927` (`company.save()` at 927)
- **Observation:** After mutating a handful of gateway-related fields, `company.save()` persists **every** column of the in-memory `Company`.
- **Impact:** A concurrent update to an unrelated `Company` field (onboarding, GST settings) between this view's load and save is silently clobbered (last-writer-wins across the whole row).
- **Fix:** Track the fields actually touched and pass `update_fields=[...]`.

---

### [B4-031] Webhook replay protection depends on a best-effort cache and only fully covers the CAPTURED path
- **Severity:** Low
- **Category:** Security
- **Location:** `payments/webhook_views.py:165-189`
- **Observation:** The dedup key is stored with `cache.add(key, "1", timeout=24h)`. If the cache backend is per-process `LocMemCache`, is evicted under pressure, or is briefly down, `cache.add` returns truthy and the event is reprocessed. The `CAPTURED` path is idempotent downstream; the `REFUNDED` path relies on `refund_gateway_payment` state checks which, for partials, are not fully idempotent (see B4-013).
- **Impact:** In a cache-degraded window, a replayed valid signed `refund` body can drive an extra partial unwind.
- **Fix:** Back replay-protection with a durable store (a `WebhookEvent`/`ProcessedWebhook` table with a unique key), not only the cache.

---

### [B4-032] Holding reconcile / capture retries pass no `user` → `created_by` NULL on generated receipts & JEs
- **Severity:** Low
- **Category:** Improvement
- **Location:** `payments/services.py:1125-1134` (`finalize_gateway_payment(... )` with no `user=`), `payments/tasks.py:165-177`
- **Observation:** `reconcile_gateway_captures` and the Celery reconcile task call `finalize_gateway_payment` without `user`, so `create_receipt` / postings record `created_by=None`.
- **Impact:** Audit trail gaps — receipts materialised by the reconcile job have no actor; harder to distinguish system-generated from user-generated in audit views.
- **Fix:** Pass a dedicated system/service user (many codebases keep a `SYSTEM_USER`) to these internal finalize calls.

---

### [B4-033] `ReconViewSet.suggest` persists `match_status` without `updated_at` / `updated_by`
- **Severity:** Low
- **Category:** Improvement
- **Location:** `payments/views.py:758-763` (`line.save(update_fields=["match_status"])`)
- **Observation:** Unlike `_confirm_match` (which updates `["match_status", "updated_at"]`), the bulk suggest path omits `updated_at`/`updated_by`.
- **Impact:** `SUGGESTED` transitions are not reflected in row audit timestamps; minor inconsistency.
- **Fix:** Include `updated_at` (and `updated_by=request.user`) in the `update_fields`.

---

### [B4-034] Dunning: a swallowed `IntegrityError` on the SENT record still counts as "sent"
- **Severity:** Low
- **Category:** Bug
- **Location:** `payments/dunning.py:125-146` (`_record`), `payments/dunning.py:188-240` (`remind_invoice`)
- **Observation:** `_record` returns `None` on `IntegrityError` (unique `(invoice, sent_on)` collision), but `remind_invoice` ignores the return value and still returns `"whatsapp"`/`"sms"`, which `run_dunning_for_company` counts as `sent += 1`.
- **Impact:** When two workers race, the loser both (a) sent a real message via `NotificationService` and (b) failed to persist a `DunningReminder` — the send happened but there is no row, and the daily counter is inflated. Duplicate customer messages possible.
- **Fix:** Acquire a per-invoice advisory lock (or `select_for_update` on the invoice) before `remind_invoice`; treat `_record(...) is None` as "already handled — do not send".

---

### [B4-035] `create_receipt` / `create_supplier_payment` coerce `amount` with bare `Decimal(amount)`
- **Severity:** Low
- **Category:** Improvement
- **Location:** `payments/services.py:234` (`if Decimal(amount) <= 0`), `payments/services.py:309`, and passim
- **Observation:** `Decimal(amount)` where `amount` may arrive as a Python `float` (internal callers, tests) raises/creates a full-precision Decimal (`Decimal(0.1)` → `0.1000000000000000055…`). API callers are safe (DRF `DecimalField`), but `finalize_gateway_payment`, `reconcile_gateway_captures`, `create_receipt_from_line` and tests pass values from mixed sources.
- **Impact:** Latent precision / comparison bugs for non-HTTP callers; inconsistent with the `Decimal(str(...))` pattern used elsewhere in the same file.
- **Fix:** Normalise once at entry: `amount = Decimal(str(amount)).quantize(Decimal("0.01"))`.

---

### [B4-036] `_unwind_refund_books` always posts the refund JE against `receipts[0]`
- **Severity:** Low
- **Category:** Bug
- **Location:** `payments/services.py:1223-1232`
- **Observation:** After iterating all `receipts` linked to the gateway payment, `PostingService.post_receipt_refund(receipts[0], ...)` is called once with the *total* `refund_amount`, regardless of how many receipts exist or which ones the reversed allocations belonged to.
- **Impact:** In the (rare) case a single `GatewayPayment` has more than one linked `CustomerReceipt`, the refund JE is booked entirely against the first receipt's customer/bank ledger — misattributed GL. Also `full` marks *every* receipt `REFUNDED` even if the amount only covered one.
- **Fix:** Post the refund JE per receipt proportionally to the amount actually unwound from each; only mark a receipt `REFUNDED` when its own balance is fully reversed.

---

### [B4-037] `AaIngestView` upsert loop is per-row `update_or_create` (no bulk) and re-runs full matching each call
- **Severity:** Low
- **Category:** Performance
- **Location:** `banking/views.py:84-105`
- **Observation:** `for row in rows: AaTransaction.objects.update_or_create(...)` then `match_aa_to_receipts(company=company)` which itself loops every unmatched row in its own transaction.
- **Impact:** A large FI pull (hundreds of transactions) = hundreds of `SELECT ... FOR ...`/`INSERT` pairs plus a full re-match sweep, all under the request; slow, lock-heavy.
- **Fix:** `bulk_create(..., ignore_conflicts=True)` for new rows, update the few that change; match only the rows created this call.

---

### [B4-038] Test coverage gaps in the highest-risk areas
- **Severity:** Info
- **Category:** Gap
- **Location:** `tests/test_phase3_payments.py`, `tests/test_w0_webhook_holding.py`, `tests/test_payment_allocation.py`
- **Observation:** Only **full** gateway refunds are tested (`test_payment_health_and_refund`, `test_refund_allows_recapture_on_reopened_link`). No test exercises: a partial `refund` API call; a provider `REFUNDED` webhook (partial or full) and its amount parsing; the `refund_idempotency_key` collision on two equal partial refunds; `execute_gateway_refund` retry after a mid-flight crash; `PaymentAllocation` double-submit; a bank CSV with two hash-identical rows; AA ingest against a `REVOKED`/`EXPIRED` consent; `parse_bank_csv` rows with unparseable dates.
- **Impact:** The bugs in B4-001..B4-009, B4-013 would all be caught by targeted tests; their absence is why they persist.
- **Fix:** Add regression tests for each scenario above, especially partial-refund book math and refund-webhook parsing.

---

# Deep code review — module cluster B5: `backend/reporting/**`

## Scope note
Line-by-line review of `backend/reporting/`:
`gst_returns.py` (2319 L), `gst_returns_sections.py`, `gstr2b.py`, `ims.py`, `ims_offline.py`,
`gst_health.py`, `gst_periods.py`, `gst_rate_scan.py`, `tds_worksheets.py`, `chase.py`,
`services.py`, `views.py`, `serializers.py`, `models.py`, `permissions.py`, `urls.py`, `apps.py`.
Tests: the stated `backend/reporting/tests/**` does **not exist**; GST/reporting tests actually live in
`backend/tests/` (`test_gst_returns.py`, `test_phase2_gst.py`, `test_b03_ims.py`, `test_wave17_gst_books.py`,
`test_sprint2_gstr_notes.py`, `test_d04_chase.py`, `test_sprint_c_tds_tcs.py`, `test_w0_multi_gstin_complete.py`).
Those were read for intent. Findings re-verified against current code.

## Severity counts
| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 2 |
| Medium   | 11 |
| Low      | 10 |
| Info     | 1 |
| **Total**| **24** |

---

### [B5-001] Reverse-charge outward invoices raise a false critical OUTWARD_FOOTING_MISMATCH and desync GSTR-1 vs GSTR-3B
- **Severity:** High
- **Category:** Bug
- **Location:** `reporting/gst_returns.py:830-835`, `:866-899`, `:1613-1618`, `:1727`
- **Observation:** `matched_invoices = [inv for inv in invoices if ... and not _rcm(inv)]` excludes reverse-charge *sales* from `outward_taxable` (header). But `section_taxable` (line 866) sums `sum(Decimal(r["taxable_value"]) for r in b2b)` and `append_b2_outward_rows` appends RCM sales to `b2b` (with `"rchrg":"Y"`). So `footing_delta = outward_taxable - section_taxable == -(rcm_taxable)`; when `abs(delta) > 1` the code sets `footing_severity = "critical"` and appends `OUTWARD_FOOTING_MISMATCH`. Separately, `build_gstr3b` computes `a_taxable_value` with `_all_sum(gstr1.get("b2b"), "taxable_value")` (RCM included) while the compatibility rollup `outward_supplies["taxable_value"] = outward["outward_taxable"]` (RCM excluded) — the 3B payload does not internally foot.
- **Impact:** Any company with a notified RCM outward supply (GTA, scrap, etc.) gets a blocking critical issue on every GSTR-1 worksheet, and GSTR-1 header taxable ≠ GSTR-3B 3.1(a) taxable. A user "correcting" to the header under-reports 3.1(a) turnover. No test covers RCM outward + footing.
- **Fix:** Include RCM sales taxable (tax columns zero) in `outward_taxable`/`outward_*` the same way 3B 3.1(a) does, OR exclude `rchrg=="Y"` rows from `section_taxable`. Make the 3B compat rollup equal `a+b+c+d` of the split it just computed.

### [B5-002] CSV injection in TDS (26Q) and TCS (27EQ) worksheet exports
- **Severity:** High
- **Category:** Security
- **Location:** `reporting/views.py:1096`, `:1130` (`writer.writerows(rows)`); rows from `reporting/tds_worksheets.py`
- **Observation:** `TdsWorksheetView`/`TcsWorksheetView` write rows straight to CSV: `writer.writerows(rows)`. Fields include `supplier`/`customer` (`inv.supplier.name`, `inv.customer.name`), `invoice`, `section` — all user-controlled. No `csv_safe`/`_csv_safe` is applied. `ExportView` (`:1160`) and `CancelledDocumentNumbersView` (`:620`) both carefully wrap every value in `csv_safe`; `core.csv_utils.csv_safe` exists and is tested.
- **Impact:** A supplier/customer named `=cmd|'/c calc'!A1` (or `@`, `+`, `-`, tab/CR prefixed) executes in the CA's spreadsheet when they open the 26Q/27EQ file. Formula-injection / data-exfiltration.
- **Fix:** Build each row as `{k: csv_safe(v) for k, v in row.items()}` before `writer.writerow`, matching `ExportView`.

### [B5-003] Offline IMS re-import silently zeroes matched-2B ITC in GSTR-3B
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `reporting/ims_offline.py:98-111`, `:136-138`; consumed by `reporting/gstr2b.py:149-164`
- **Observation:** `import_offline` `defaults` always sets `"itc_eligibility": Gstr2bIngest.ItcEligibility.UNREVIEWED` and `"match_status": UNMATCHED` for every row, including rows a prior `apply_ims_action(ACCEPT)` set to `CLAIMABLE` (and posted `reclass_unreviewed_itc` journals for). `classify_and_match` re-derives `match_status`/`match_class` but never restores `itc_eligibility=CLAIMABLE`. `claimable_itc_from_2b` filters `itc_eligibility=CLAIMABLE, ims_action=ACCEPT`.
- **Impact:** After any export→import round-trip of the offline IMS file, `itc.from_gstr2b_matched` and `recommended_claimable` in GSTR-3B collapse to 0 even though `ims_action=ACCEPT` was preserved from the file; the accounting journals stay posted, so books and the return diverge until every row is re-accepted. `test_ims_offline_round_trip` does not assert ITC retention.
- **Fix:** Preserve `itc_eligibility` from the file (it is already serialised by `row_to_offline`), or re-derive CLAIMABLE for `ims_action==ACCEPT` rows that re-match, rather than force-resetting.

### [B5-004] `replace=True` offline import hard-deletes the append-only IMS decision log
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `reporting/ims_offline.py:82-83`; `reporting/models.py:182-208`
- **Observation:** `if replace: Gstr2bIngest.objects.filter(company=company, period=period).delete()`. `ImsActionHistory.ingest` is `on_delete=models.CASCADE`. A QuerySet `.delete()` cascades at the DB/collector level and never calls `ImsActionHistory.delete()` — which is overridden to `raise ValueError("IMS action history is append-only.")` (and `save()` blocks updates) precisely to make it immutable.
- **Impact:** A single `ims-offline-import` with `replace=true` erases the entire ACCEPT/REJECT audit trail for the period, defeating the "Never update or delete" guarantee (B-03).
- **Fix:** Before delete, detach/retain history (repoint FK to `SET_NULL` + keep rows), or forbid `replace` when `ImsActionHistory` exists for the period, or soft-delete ingest rows.

### [B5-005] `Gstr2bIngest` PATCH bypasses IMS reclass and match integrity
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `reporting/serializers.py:8-59`; `reporting/views.py:712-731`
- **Observation:** `read_only_fields` omits `itc_eligibility`, `taxable_value`, `igst`, `cgst`, `sgst`, `cess`, `invoice_date`, `supplier_gstin`, `invoice_number`, `period`, `raw`, `ims_remark`. `validate_itc_eligibility` guards only the `CLAIMABLE` transition. `partial_update` is allowed for `IsOwner`.
- **Impact:** An owner PATCH can (a) set `itc_eligibility=INELIGIBLE/REVERSED/UNREVIEWED` without `reclass_rejected_itc`/`reclass_unreviewed_itc`, so books ITC and the 2B row diverge; (b) rewrite tax amounts / GSTIN / number on a MATCHED+ACCEPTED row, silently moving `claimable_itc_from_2b` totals with **no `ImsActionHistory` entry and no re-match**. No test covers field tampering via PATCH.
- **Fix:** Make all tax/identity fields and `itc_eligibility` read-only via the serializer; route eligibility changes only through `apply_ims_action`; re-run `match_gstr2b_to_purchases` on any permitted amount edit.

### [B5-006] Section builder and liability totals use different note-mismatch predicates
- **Severity:** Medium
- **Category:** Bug
- **Location:** `reporting/gst_returns_sections.py:198-218`; `reporting/gst_returns.py:189-208`, `:840-847`
- **Observation:** `build_note_rate_rows` (builds CDNR/CDNUR/B2CS rows) calls `invoice_value_mismatch(note)` at `gst_returns_sections.py:209`. The GSTR-1 liability filters `matched_credit_notes`/`matched_debit_notes` (`gst_returns.py:842,846`) call the newer `note_value_mismatch(n)`. The GST-06 docstring on `note_value_mismatch` explicitly says the invoice formula "would silently misjudge a note the moment a note grows one of those fields" — yet the section builder still uses it. The two differ on AFTER_TAX-discount / `additional_charges` / `tcs_in_grand_total` handling.
- **Impact:** A credit/debit note that passes one predicate but not the other appears in CDNR/CDNUR section rows but not in the header outward totals (or vice-versa) → `OUTWARD_FOOTING_MISMATCH` or a mis-stated CDNR block.
- **Fix:** Use `note_value_mismatch` in `build_note_rate_rows` too.

### [B5-007] `Gstr2bIngestViewSet.upload` — unbounded, unbatched, non-atomic, unthrottled
- **Severity:** Medium
- **Category:** Performance
- **Location:** `reporting/views.py:712-793`
- **Observation:** `upload` iterates `request.data.get("rows")` with one `Gstr2bIngest.objects.update_or_create(...)` per row (≈2 queries each). No length cap, no `transaction.atomic`, and `Gstr2bIngestViewSet` declares no `throttle_classes` (unlike the `APIView` reports which use `CompanyRateThrottle`). `ims_offline.import_offline` at least wraps the loop in `@transaction.atomic`.
- **Impact:** A 50k-row 2B upload = ~100k queries in one request; an error mid-loop leaves a half-ingested period. DoS surface.
- **Fix:** Cap `len(rows)`, wrap in `transaction.atomic`, use `bulk_create`/`bulk_update` batching, add `CompanyRateThrottle`.

### [B5-008] `payables_aging` is N+1 — the receivables twin was bulk-optimised, this was not
- **Severity:** Medium
- **Category:** Performance
- **Location:** `reporting/services.py:467-500` (cf. `:77-144` `receivables_aging`)
- **Observation:** `for inv in invoices: outstanding = LedgerService.purchase_invoice_outstanding(inv)` — per-invoice ledger call over **every** COMPLETED/RETURNED purchase invoice ever (no date bound). `receivables_aging` was rewritten (BUG-302) to precompute CN/DN/allocation maps in bulk; `payables_aging` still loops.
- **Impact:** Dashboard/aging endpoint latency grows linearly with lifetime purchase count.
- **Fix:** Bulk-aggregate allocations/CN/DN by `purchase_invoice_id` like `receivables_aging` does.

### [B5-009] `cash_position` / dashboard materialises the entire cash history on every call
- **Severity:** Medium
- **Category:** Performance
- **Location:** `reporting/services.py:552-667`; `reporting/views.py:96-99`
- **Observation:** `cash_position` calls `ReportService.cash_book(company)` with **no date bounds**. `cash_book` pulls every POSTED `CustomerReceipt` and `SupplierPayment` into Python lists, iterates them to build `rows`, and (when `date_from` is set) also Python-sums `pre_receipts`/`pre_payments` (`sum((r.amount for r in ...))`) instead of `.aggregate(Sum(...))`. `dashboard()` calls `cash_position` unconditionally.
- **Impact:** Every dashboard load reads and serialises the tenant's full lifetime of receipts + payments; unbounded growth.
- **Fix:** Give `cash_position` a bounded window (or a pure `.aggregate` closing-balance query); replace Python `sum(...)` over querysets with DB `Sum`.

### [B5-010] `sales_register` / `purchase_register` have no pagination or row cap
- **Severity:** Medium
- **Category:** Performance
- **Location:** `reporting/services.py:233-335`, `:337-426`; `reporting/views.py:102-133`, `:1140-1163`
- **Observation:** Both build a Python list of **every** non-draft invoice plus **all** completed CN/DN in the (optional) date range, then the views/`ExportView` return the whole `rows` list. The module docstring claims "API clients never scan raw document tables (§9)"; these do exactly that with no `LIMIT`.
- **Impact:** Multi-MB JSON / CSV, high memory, slow serialisation for large tenants or unbounded date filters.
- **Fix:** Enforce a max date span or add cursor pagination; stream CSV via `.iterator()`.

### [B5-011] GSTR-9 rebuild = 12× full GSTR-1 builds + 12× purchase aggregation, no work-sharing
- **Severity:** Medium
- **Category:** Performance
- **Location:** `reporting/gst_returns.py:1801-2100`
- **Observation:** `build_gstr9` loops 12 months; when a stamp is passed or a period is `dirty_after_snapshot` it calls `build_gstr1(company, period, ...)` per month, plus per-month `_gst_purchase_invoices` + `.items.all()` iteration + `_gst_purchase_credit_notes`/`_debit_notes` + a `Gstr2bIngest` scan. Only the `gst_reports` throttle protects it; runs synchronously in the request.
- **Impact:** Full-FY GSTR-9 for a busy multi-GSTIN tenant can exceed request timeout.
- **Fix:** Move to an async job with a persisted result, and reuse the monthly GSTR-1 snapshots (already the fast path) plus a single ranged purchase query instead of 12.

### [B5-012] CMP-08 includes opening-balance RCM purchases; CN/DN not NON_GST-filtered
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `reporting/gstr2b.py:198-260`
- **Observation:** `rcm_purchases` (`:236-243`) filters `is_reverse_charge=True` but omits `is_opening_balance=False`, unlike the outward invoice query (`:206-213`) and every GST builder in `gst_returns.py`. `cns`/`dns` (`:215-230`) also lack the `.exclude(invoice_type=NON_GST)` the invoice query applies.
- **Impact:** Tally-migrated opening RCM balances inflate CMP-08 Table 2 tax payable; NON_GST notes wrongly net Table 1 turnover.
- **Fix:** Add `is_opening_balance=False` to `rcm_purchases`; mirror the NON_GST exclusion on note querysets.

### [B5-013] IMS REJECT is irreversible for books ITC
- **Severity:** Low
- **Category:** Broken-flow
- **Location:** `reporting/ims.py:161-192`
- **Observation:** `apply_ims_action(REJECT)` sets the linked `PurchaseInvoice.itc_eligibility = INELIGIBLE` (`:184-186`). A subsequent `ACCEPT` only upgrades `UNREVIEWED → CLAIMABLE` (`:167-169`); there is no `INELIGIBLE → CLAIMABLE` path.
- **Impact:** A mis-clicked REJECT then re-ACCEPT permanently strands the books ITC as INELIGIBLE; the only recovery is a manual PurchaseInvoice edit (which itself bypasses reclass — see B5-005).
- **Fix:** On `ACCEPT` of a row whose linked invoice is `INELIGIBLE` *because of a prior IMS reject* (track the reason), restore to `CLAIMABLE` and run `reclass_unreviewed_itc`.

### [B5-014] `to_gstn_json` mis-parses a FY label as a monthly period
- **Severity:** Low
- **Category:** Bug
- **Location:** `reporting/gst_returns.py:2103-2149`
- **Observation:** `period = payload.get("period") or payload.get("fy") or ""`; then `if len(period) == 7 and period[4] == "-": year, month = period.split("-"); fp = f"{month}{year}"`. A GSTR-9 payload has `fy = "2025-26"` (length 7, `[4]=="-"`), so `fp` becomes `"262025"` — month "26".
- **Impact:** Malformed `fp` in GSTN-shaped GSTR-9 JSON. Limited: the export is dev/test-only (`_maybe_gstn_json` fails closed elsewhere).
- **Fix:** Only derive `fp` from `payload.get("period")` with a `\d{4}-\d{2}` month check; skip for FY payloads.

### [B5-015] TDS/TCS worksheets drop RETURNED docs and include opening balances
- **Severity:** Low
- **Category:** Gap
- **Location:** `reporting/tds_worksheets.py:29-58`, `:91-124`
- **Observation:** Both querysets filter `status=...COMPLETED` only (not `RETURNED`) and never `.exclude(is_opening_balance=True)`. GSTR builders consistently use `status__in=(COMPLETED, RETURNED)` and exclude opening balances.
- **Impact:** A returned invoice that carried TDS/TCS is missing from 26Q/27EQ; a Tally opening-balance row with a stray `tds_amount` is wrongly included.
- **Fix:** `status__in=(COMPLETED, RETURNED)` and `is_opening_balance=False`.

### [B5-016] `supplier_scorecard` — N+1 supplier lookups and Python-side purchase-value sum
- **Severity:** Low
- **Category:** Performance
- **Location:** `reporting/ims.py:278-342`
- **Observation:** Per distinct GSTIN: `Supplier.objects.filter(company=company, gstin__iexact=gstin).first()` and `purchase_value = sum((Decimal(str(p.grand_total or 0)) for p in qs), ...)` iterating `PurchaseInvoice` rows instead of `.aggregate(Sum("grand_total"))`.
- **Impact:** Scales with supplier count × invoices-per-supplier for a monthly scorecard.
- **Fix:** One `Supplier.objects.filter(gstin__in=...)` map; `.aggregate(Sum)` for purchase value.

### [B5-017] Rate buckets keyed/sorted on `_money(rate)` strings; monthly vs annual HSN keys differ
- **Severity:** Low
- **Category:** Bug
- **Location:** `reporting/gst_returns_sections.py:9-20`; `reporting/gst_returns.py:685-715`, `:1884-1891`
- **Observation:** `b2cs` output `sorted(b2cs_buckets.items())` and `hsn` `sorted(hsn_buckets.items())` order by the money-string rate (`"18.00" < "5.00"` lexically). `accumulate_hsn_line` keys HSN buckets on `str(Decimal(gst_rate))` → `"18"`; `build_gstr9` re-aggregates monthly HSN on `str(hrow.get("rate"))` → `"18.00"`. Different string forms.
- **Impact:** Cosmetic mis-ordering in B2CS/HSN sections; in GSTR-9 the monthly→annual HSN roll-up groups by a different key form than the monthly build (self-consistent per function, but confusing and fragile if ever cross-compared).
- **Fix:** Normalise rate keys (e.g. always `q2`/`_money`) across `accumulate_hsn_line` and the GSTR-9 aggregation; sort numerically.

### [B5-018] `classify_and_match` "missing in books / IMS" only compares the exact 2B month
- **Severity:** Low
- **Category:** Bug
- **Location:** `reporting/ims.py:43-129`
- **Observation:** `book_keys` is built with `invoice_date__year=y, invoice_date__month=m` (the 2B period month). A supplier who reports a March invoice in the April 2B produces a row whose `(gstin, number)` is not in `book_keys` even though the bill is booked in March → `MISSING_IN_BOOKS` / `missing_in_ims` noise.
- **Impact:** False "missing" alerts and inflated `supplier_scorecard` mismatch counts for legitimately-late supplier filings.
- **Fix:** Widen `book_keys` to at least the surrounding FY (matcher already uses `_indian_fy_start_year` tolerance).

### [B5-019] GSTR-9 import-ITC detection is a fragile substring heuristic
- **Severity:** Low
- **Category:** Bug
- **Location:** `reporting/gst_returns.py:1935-1939`, `:2041-2055`
- **Observation:** `if (not supplier_gstin and Decimal(str(inv.igst_total or 0)) > 0) or "IMPORT" in notes:` classifies a non-RCM purchase as an import for Table 8 `imports_igst`.
- **Impact:** Domestic IGST purchases from unregistered/blank-GSTIN suppliers are mis-counted as imports; any invoice whose free-text `notes` contains "import" is swept in.
- **Fix:** Drive off `BillOfEntry` linkage (already the source for 3B `import_itc`) rather than GSTIN-blank + notes text.

### [B5-020] AT / TXPD advances silently return empty for any non-primary GSTIN
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `reporting/gst_returns.py:1112-1167`, `:1207-1227`
- **Observation:** `_gstr1_at_table` returns `[]` whenever `company_gstin_id` is set and is not the primary (`:1125-1130`); `_gstr1_txpd_table` derives from it. Comment acknowledges "return empty (ATADJ covers stamp-scoped allocations)" but ATADJ only lists *allocated* advances.
- **Impact:** A second registration's GSTR-1/3B shows zero unallocated advances / TXPD even when `CustomerReceipt` rows exist, understating advance-tax disclosure for multi-GSTIN companies.
- **Fix:** Scope advances to the stamp (e.g. via the customer's/receipt's linked GSTIN) instead of blanket-empty for non-primary.

### [B5-021] `apply_after_tax_header_discount` is a permanent no-op still wired into the build loop
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `reporting/gst_returns_sections.py:23-29`; called at `reporting/gst_returns.py:635`
- **Observation:** The function body is `return` with a docstring explaining why it is "Intentionally a no-op". It is still invoked once per invoice in `build_gstr1`.
- **Impact:** Dead call; HSN Table 12 vs after-tax cash-discount reconciliation is unimplemented. If `taxable_total` on such invoices already nets the discount, Table 12 may not foot to the section totals — untested.
- **Fix:** Either delete the call + function, or implement the Table 12 adjustment and document the invariant with a test.

### [B5-022] `deemed_accept_on_period_lock` dead no-op; stale PER-02 audit comment
- **Severity:** Low
- **Category:** Dead code
- **Location:** `reporting/ims.py:228-230`; `reporting/gst_periods.py:39-48`, `:57-85`
- **Observation:** `deemed_accept_on_period_lock` unconditionally `return 0`; `soft_close_period` still imports and calls it. `reopen_period`'s logged message and `AuditEvent` describe "Deemed-accept / ITC-reclass journals from the close are not reversed" — but the close now posts nothing.
- **Impact:** Misleading audit trail; dead import/call.
- **Fix:** Remove the function and its call; correct the reopen audit text (or drop it).

### [B5-023] 2B `upload` overwrites a supplier-revised row with no history
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `reporting/views.py:756-793`
- **Observation:** `update_or_create` keyed on `(company, period, supplier_gstin, invoice_number)`; a re-uploaded 2B where the supplier amended `taxable_value`/tax/date silently replaces the prior figures. Combined with B5-005 there is no audit of 2B row value changes at all.
- **Impact:** A period whose 2B was re-pulled after a supplier amendment loses the original figures used for an earlier reconciliation, with nothing recorded.
- **Fix:** Snapshot prior `raw`/amounts into `ImsActionHistory` (or a dedicated log) on value change during upload.

### [B5-024] Weak / missing test coverage
- **Severity:** Info
- **Category:** Gap
- **Location:** `backend/tests/test_*gst*`, `test_b03_ims.py`, `test_sprint2_gstr_notes.py`, `test_sprint_c_tds_tcs.py`
- **Observation:** No test exercises: reverse-charge **outward** invoices in the GSTR-1 footing check (B5-001); offline-IMS re-import ITC retention (B5-003); `replace=true` history deletion (B5-004); `Gstr2bIngest` PATCH field/eligibility tampering (B5-005); TDS/TCS CSV escaping (B5-002); multi-GSTIN GSTR-9 (`build_gstr9` stamp path); CMP-08 opening-RCM exclusion (B5-012); `note_value_mismatch` in the section builder (B5-006). `test_gstr1_reconciliation_invariant` only asserts the footing invariant for a plain B2B+B2C month. The prompt's `backend/reporting/tests/**` path does not exist.
- **Impact:** The regressions above can land unnoticed.
- **Fix:** Add cases per finding, especially an RCM-outward GSTR-1 footing test and an offline-IMS ITC round-trip assertion.

---

# Deep security review — module cluster B6 (accounts / core auth / RLS / billing gates)

## Scope note
Read line-by-line:
- `backend/accounts/`: models.py, views.py, serializers.py, onboarding.py, otp_utils.py,
  password_validation.py, tenant_backup.py, export_views.py, admin.py, urls_auth.py,
  urls_company.py, apps.py, management/commands/{seed_demo,seed_pilot_fixtures}.py
- `backend/core/`: authentication.py, rls.py, middleware.py, idempotency.py, throttles.py,
  permissions.py, exceptions.py (context)
- `backend/billing/`: middleware.py, permissions.py, services.py (`company_writes_blocked` context)
- `backend/core/services/`: registration_gates.py, identity_verify.py
- `backend/core/migrations/0005_wave16_postgres_rls.py`, `0020_rls_all_tenant_tables.py`
- tests: test_tenant_isolation.py, test_rls_coverage.py (read for intent)
- `backend/config/settings.py` (REST_FRAMEWORK, SIMPLE_JWT, MIDDLEWARE, throttles, RLS, OTP, CSRF/JWT cookies)

Cross-checked against current code; not relying on any *.md status doc.

## Severity counts
| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 1 |
| Medium   | 5 |
| Low      | 16 |
| Info     | 4 |
| **Total**| **26** |

---

### [B6-001] Sandbox tenant-restore writes rows under the wrong RLS GUC — restore-to-sandbox 500s whenever Postgres RLS is enabled (the default)
- **Severity:** High
- **Category:** Broken-flow
- **Location:** `backend/accounts/tenant_backup.py:1078` (`restore_to_sandbox`) → `import_payload` (`:638`); interaction with `backend/core/middleware.py:120` and `backend/core/migrations/0020_rls_all_tenant_tables.py`
- **Observation:** `restore_to_sandbox` creates a **new** `Company` (`sandbox`) then calls `import_payload(target_company=sandbox, …)` which does `DocumentSeries.objects.update_or_create(company=target_company, …)`, `Warehouse.objects.create(company=target_company, …)`, `SalesInvoice.objects.create(company=target_company, …)`, etc. Meanwhile `PostgresRlsMiddleware` has already executed `set_rls_company(company_id)` with `company_id` = the requesting owner's **active/source** company. The RLS policy on every tenant table (`0020_rls_all_tenant_tables.py`) is `WITH CHECK (company_id::text = NULLIF(current_setting('app.company_id', true), '') OR current_setting('app.rls_bypass', true) = '1')`. `sandbox.pk != app.company_id`, and no `rls_bypass()` wraps the call.
- **Impact:** On Postgres with `POSTGRES_RLS_ENABLED` (settings.py:764 defaults to `"1"`), the first tenant-table INSERT for the sandbox company raises `new row violates row-level security policy` → HTTP 500. Sandbox restore is the **default** restore mode (`TenantRestoreView.post`, `export_views.py:115`), so the owner-facing "restore into a sandbox" feature is entirely non-functional in production. `restore_destroy_in_place` happens to work only because it reuses the same company id as the GUC. Tests miss it because they run on SQLite where RLS is a no-op.
- **Fix:** Wrap the sandbox import in `core.rls.rls_bypass()`, or explicitly `set_rls_company(sandbox.pk)` for the duration of `import_payload` and restore the previous GUC afterward. Add a `@pytest.mark.postgres` test that restores to a sandbox with RLS on.

---

### [B6-002] `clear_all_rls_gucs` aborts remaining GUC resets if the first `set_config` raises — pooled connection can retain `app.rls_bypass=1` / `app.help_staff_all=1`
- **Severity:** Medium
- **Category:** Security
- **Location:** `backend/core/rls.py:106-113`
- **Observation:** `clear_all_rls_gucs()` calls `set_rls_company(None)`, then `set_help_staff_all(False)`, then `set_rls_bypass(False)` sequentially. Each helper re-raises on failure ("Fail-closed" — `rls.py:37-39`, `:59-61`, `:83-85`). If `set_rls_company(None)` raises, the other two resets never run.
- **Impact:** The middleware `finally` (`middleware.py:128-134`) calls this once per request to stop a pooled connection carrying tenant context into the next request. If clearing `app.company_id` fails transiently but the connection stays alive, a previously-set `app.rls_bypass = '1'` (from a beat task / cross-tenant job that reused this connection) or `app.help_staff_all = '1'` stays set — the RLS isolation policy then ORs to true and the **next request on that connection reads every tenant's rows**. `is_local=false` GUCs are exactly the persistence model that makes this dangerous.
- **Fix:** Clear each GUC in its own `try/except` so one failure cannot skip the others; log-and-continue rather than raise from the aggregate cleaner. Optionally issue a single `RESET ALL` / `DISCARD ALL` as a backstop when any individual reset fails.

---

### [B6-003] No email-ownership verification on registration — arbitrary-email account squatting / pre-hijack
- **Severity:** Medium
- **Category:** Security
- **Location:** `backend/accounts/views.py:229-285` (`RegisterView`), `urls_auth.py:22`
- **Observation:** `RegisterView.post` creates `User` + `Company` + owner `CompanyUser` immediately from unauthenticated input; no verification email/token is ever sent (the response is the generic `_register_payload()` with everything `None`, and there is no confirm endpoint). `throttle_scope = "register"` = 5/min per IP.
- **Impact:** Anyone can create a fully-usable owner account bound to an email address they do not control. The real owner of that address later gets only the non-enumerating "an account has been prepared" 200 and cannot register or (see B6-004) reset the password, while the squatter has a working tenant. Also enables classic pre-registration hijack if SSO/again-login is ever added.
- **Fix:** Send a signed, single-use verification link on register; leave the membership/company inactive (or gate login) until the email is confirmed. Keep the response body non-enumerating.

---

### [B6-004] Password reset is a silent dead-end for users provisioned without a password
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `backend/accounts/views.py:1163-1208` (`RequestPasswordResetView`), specifically `:1175` `if user is not None and user.has_usable_password():`
- **Observation:** A reset email is generated only when `user.has_usable_password()`. Users created through the invite-without-password path (`CompanyUserViewSet.create` → `user.set_unusable_password()`, `views.py:1059-1061`) have an unusable password until they accept the invite.
- **Impact:** If such a user loses/expires the 7-day invite token, `POST /auth/password/reset/` returns the generic "if an account exists…" 200 but does nothing, and there is no alternative self-service recovery — they are locked out until an owner manually re-invites. Same for OTP login (`VerifyOtpView:521` also requires `has_usable_password()`).
- **Fix:** For an existing user with an unusable password, treat a reset request as an "activate account / set password" flow (issue the same single-use `PasswordResetJti`), or document/expose an owner "resend invite" action and surface it in the client.

---

### [B6-005] `_copy_model_fields` copies unmapped `*_id` FK columns verbatim from the export — stale / cross-object references after restore
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `backend/accounts/tenant_backup.py:454-485` (`_copy_model_fields`), used throughout `import_payload`
- **Observation:** The remap branch (`:463-466`) only rewrites `attname` values when `attname in remap`. Any other column ending in `_id` that is neither in `skip` nor in `remap` falls through to the generic `else: kwargs[attname] = raw` branch (`:483-484`) and is written **with the source database's primary-key value**. `import_payload` enumerates `skip`/`remap` per model by hand, so any FK the author forgot (or any FK added to a model later) is silently carried over unmapped.
- **Impact:** After restore (sandbox or destroy-in-place) such a FK points at whatever row now holds that PK — a different object in the same tenant, or, since PKs are global `BigAutoField`s, a row belonging to another tenant. Depending on the field this is broken navigation at best and a cross-tenant data reference / integrity violation at worst. There is no post-import `full_clean()` or FK-existence sweep.
- **Fix:** In `_copy_model_fields`, when a column ends in `_id` and is not in `remap`, drop it (set `None`) unless it is explicitly whitelisted as a safe scalar. Add a test that asserts every FK on every imported model is either skipped or remapped.

---

### [B6-006] `restore_to_sandbox` bypasses seat/subscription limits and unconditionally grants AI capabilities; unbounded sandbox company creation
- **Severity:** Medium
- **Category:** Security / Gap
- **Location:** `backend/accounts/tenant_backup.py:1078-1105` (`restore_to_sandbox`), `backend/accounts/export_views.py:65-132` (`TenantRestoreView`)
- **Observation:** `restore_to_sandbox` does `Company.objects.create(...)` + `CompanyUser.objects.create(role=OWNER, can_view_ai_insights=True, can_use_ai_assistant=True, … all True)` with no call to `_enforce_plan_seat_limit`, `ensure_register_trial`, or any `REQUIRE_SUBSCRIPTION` check. `TenantRestoreView` rate-limits to one restore / 10 min / company but nothing caps the number of sandbox companies an owner accumulates.
- **Impact:** (a) Every sandbox tenant is created outside the billing model — an owner on a seat-limited / lapsed plan gets a fresh unlimited-capability OWNER membership and a company that `company_writes_blocked` will not block until a Subscription row exists. (b) An owner can mint a new `Company` every 10 minutes indefinitely (resource growth, audit noise). (c) AI capability flags are force-enabled even if the source company had `ai_features_enabled=False`.
- **Fix:** Run the sandbox company through the same trial/subscription bootstrap and seat enforcement as registration; copy AI capability flags from the source membership instead of hard-coding `True`; cap concurrent sandbox companies per owner and/or require explicit cleanup.

---

### [B6-007] Login lockout keyed only on email enables targeted account-lockout DoS
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/accounts/views.py:158-183, 302-324` (`LOGIN_FAIL_LIMIT`, `_login_fail_key`, `_record_login_failure`, `LoginView.post`)
- **Observation:** `_login_fail_key(email)` = `login_fail:<lowercased email>`. After `LOGIN_FAIL_LIMIT = 10` failures in 15 min, `LoginView.post` raises `TooManyLoginAttemptsError` (429) for that email regardless of source IP. The DRF `login` scope (10/min) is per-IP only.
- **Impact:** An attacker who knows a victim's email can submit 10 bad passwords (from one IP, well within 10/min) and lock the victim out of email+password login for 15 minutes, repeatable indefinitely. OTP login is also gated on `has_usable_password` and separate rate limits, so this is a practical account-availability DoS.
- **Fix:** Combine the per-account counter with a per-account+per-IP counter and only hard-lock on the intersection, or switch to progressive delay / CAPTCHA after N failures instead of a flat lockout. Consider not counting failures that never presented a syntactically plausible credential.

---

### [B6-008] Login user-enumeration via timing (extra bcrypt only for existing emails)
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/accounts/views.py:310-321`
- **Observation:** Before delegating to `TokenObtainPairView.post`, the view runs `pending_user = User.objects.filter(email__iexact=email).first()` and, `if pending_user and password and pending_user.check_password(password)`, a full password hash verification. `super().post()` then authenticates again (its backend does a constant-time dummy hash for unknown users).
- **Impact:** Existing accounts incur two bcrypt/argon2 verifications; non-existent accounts incur roughly one (the dummy). The measurable delta is a user-enumeration oracle that the non-enumerating register/reset flows were specifically designed to avoid.
- **Fix:** Drop the pre-check hash; move the "correct password but no active membership" messaging into a post-authentication branch (inspect `response.status_code == 200` then check memberships), so only one hash path exists.

---

### [B6-009] Password-reset request: SMTP failure in prod raises 500 for existing users vs 200 for non-existent — enumeration oracle
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/accounts/views.py:1197-1208`
- **Observation:** `send_mail(..., fail_silently=env not in ("production", "staging"))`. In production/staging `fail_silently=False`, so any transient SMTP error propagates → 500. For a non-existent identifier the branch is skipped and the endpoint always returns the uniform 200.
- **Impact:** During an SMTP hiccup, `500` vs `200` distinguishes "this identifier maps to a real user with a usable password" from "it does not" — defeats the uniform-response design.
- **Fix:** Send asynchronously (queue the mail) and always return the uniform 200; or wrap `send_mail` in `try/except` that logs and still returns 200.

---

### [B6-010] Dev-only: Bearer auth + `POSTGRES_RLS_ENABLED` → middleware never resolves the company, RLS returns zero rows
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/core/middleware.py:95-120` (`PostgresRlsMiddleware`)
- **Observation:** When `request.user` is unauthenticated at middleware time, the middleware only tries `CookieJWTAuthentication().authenticate(request)` (cookie path). A DRF request authenticating via `Authorization: Bearer` (allowed outside production/staging, settings.py:274-278) is still anonymous here, so `company_id` stays `None` and `set_rls_company(None)` fails RLS closed for the whole request.
- **Impact:** Local/CI Postgres runs with Bearer tokens + `POSTGRES_RLS_ENABLED=1` see empty results from every tenant table even though the caller is legitimately authenticated — confusing, and can mask real RLS regressions in dev.
- **Fix:** In the non-authenticated branch, also attempt `JWTAuthentication().authenticate(request)` (header path) before resolving the company, mirroring DRF's configured auth classes for the current env.

---

### [B6-011] Branch-GSTIN list readable by any company member (including VIEWER)
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/accounts/views.py:1114-1128` (`CompanyGstinViewSet`)
- **Observation:** `permission_classes = [IsAuthenticated, HasCompany]` for the viewset; `get_permissions` only adds `IsOwner` for `POST/PATCH/PUT/DELETE`. So `GET /company/gstins/` is available to every active member. Contrast `CompanyDetailView` which downgrades non-owners to `CompanySerializerStaff` (no bank/UPI) and the many `CanView*Surfaces` classes that explicitly exclude `VIEWER`.
- **Impact:** A `VIEWER` / `SALES_STAFF` can enumerate all registered GSTINs plus their legal names, addresses, cities and pincodes — information the staff Company serializer is careful to expose only in limited form. Minor confidentiality leak / inconsistency with the rest of the RBAC surface.
- **Fix:** Gate the read on `IsOwner` (or at least a non-VIEWER capability such as `can_view_financial_reports`), consistent with the other company-settings surfaces.

---

### [B6-012] `ChangePasswordView` has no throttle — unlimited `current_password` guessing for a session holder
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/accounts/views.py:765-790` (`ChangePasswordView`), no `throttle_scope`
- **Observation:** Only `permission_classes = [IsAuthenticated]`. `check_password(current)` is invoked with no per-user/endpoint rate limit; the DRF default `user` scope is a very loose 600/min.
- **Impact:** An attacker holding a stolen short-lived access token (but not the password) can brute-force `current_password` at ~600/min to achieve full account takeover (change password + the view blacklists other sessions). Also no lockout feedback to the real user.
- **Fix:** Add a tight `throttle_scope` (e.g. reuse `login`'s budget) and/or a per-user failure counter mirroring `_record_login_failure`.

---

### [B6-013] `set_rls_company` is called outside the middleware `try/finally`; a failure there skips GUC cleanup
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/core/middleware.py:120-134`
- **Observation:** `set_rls_company(company_id)` runs at line 120; the `try:` that guarantees `clear_all_rls_gucs()` in `finally` only starts at line 121. `set_rls_company` re-raises on `set_config` failure.
- **Impact:** If setting `app.company_id` for this request raises, the `finally` cleanup never runs, so any GUC left on this pooled connection by a prior request/job (`app.rls_bypass`, `app.help_staff_all`, a stale `app.company_id`) is not cleared before the connection returns to the pool. Compounds B6-002.
- **Fix:** Move `set_rls_company(company_id)` inside the `try`, or add an outer `try/finally` that always calls `clear_all_rls_gucs()`.

---

### [B6-014] Idempotency in-flight reclaim can double-run a long (>15 min) import commit
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `backend/core/idempotency.py:18-30, 126-144` (`IN_FLIGHT_STALE_SECONDS`, `MONEY_IDEMPOTENCY_SCOPES`, `begin_record`)
- **Observation:** For scopes **not** in `MONEY_IDEMPOTENCY_SCOPES`, an in-flight placeholder older than `IN_FLIGHT_STALE_SECONDS` (15 min) is `.delete()`d and a retry is allowed to proceed. The comment itself notes the timeout "must exceed the slowest protected operation (large import commit…)" — i.e. correctness depends on an operational guess.
- **Impact:** A genuine import-commit (or e-invoice batch) that legitimately runs longer than 15 minutes can have its placeholder reclaimed while still committing; the client's automatic retry then executes the same import a second time. Import commit is not in the money set.
- **Fix:** Add `import_commit` (and any other long, non-idempotent-by-construction scope) to `MONEY_IDEMPOTENCY_SCOPES`, or make the stale threshold per-scope, or use a DB row lock / heartbeat instead of an age heuristic.

---

### [B6-015] Tenant export embeds raw PAN / UDYAM third-party verification payloads
- **Severity:** Low
- **Category:** Security / Privacy
- **Location:** `backend/accounts/tenant_backup.py:32-44` (`COMPANY_SKIP_FIELDS`), `:166` (`_row_dict(company, extra_exclude=COMPANY_SKIP_FIELDS)`)
- **Observation:** `COMPANY_SKIP_FIELDS` excludes `gsp_credentials_encrypted`, `payment_gateway_credentials_encrypted`, `gstin_raw_payload`, `billing_override_active` — but **not** `pan_raw_payload` or `udyam_raw_payload`, which hold the full provider lookup responses (`identity_verify.apply_pan_verification` stores `company.pan_raw_payload = result.raw`).
- **Impact:** The Fernet-encrypted export (owner-downloadable, then handled outside the app) carries whatever the identity provider returned — potentially proprietor name, DOB, address, masked IDs — beyond the fields the owner sees in the UI. Inconsistent with the deliberate exclusion of `gstin_raw_payload`.
- **Fix:** Add `pan_raw_payload` and `udyam_raw_payload` to `COMPANY_SKIP_FIELDS` (keep the derived status / legal-name / verified-at fields).

---

### [B6-016] `seed_demo` / `seed_pilot_fixtures` only refuse `DJANGO_ENV=production` — `staging` still seeds public weak-password users
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/accounts/management/commands/seed_demo.py:28-29`, `seed_pilot_fixtures.py:101-102, 120, 131, 160`
- **Observation:** Both guard `if getattr(settings, "DJANGO_ENV", "").strip().lower() == "production"`. `seed_pilot_fixtures` creates users with `password="PilotPass123!"` and prints it; `seed_demo` creates `demo@bizboard.local / DemoPass123!`.
- **Impact:** On a `staging` deployment (internet-reachable, `DJANGO_ENV=staging`) an operator running these commands provisions known-credential accounts with full owner capability. `PilotPass123!` also passes the breached-password list (`password_validation._EXTRA_COMMON`).
- **Fix:** Refuse to run whenever `DJANGO_ENV in ("production", "staging")` or whenever `DEBUG` is false; require an explicit `--force` and randomized passwords printed once.

---

### [B6-017] Soft-deactivated staff retain a usable access JWT for its lifetime; refresh not blacklisted on deactivation
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/accounts/views.py:1103-1111` (`CompanyUserViewSet.perform_destroy`), `:1087-1101` (`perform_update` setting `is_active=False`)
- **Observation:** Deactivation only sets `CompanyUser.is_active = False`. No `OutstandingToken`/`BlacklistedToken` writes for that user, unlike `ChangePasswordView` / `LogoutAllView`.
- **Impact:** The removed user's existing access token stays valid until expiry (`JWT_ACCESS_MINUTES` default 15). `HasCompany`/`get_company_user` filter on `is_active=True` and will 403 them on company-scoped endpoints, but any endpoint that requires only `IsAuthenticated` (e.g. `MeView` PATCH push_token, `MembershipsListView`, `SwitchCompanyView`) still works, and refresh is only cut at the next `CookieTokenRefreshView` call (which does check active membership). If the user has another company, they keep operating there — expected — but there's no forced session kill for the removed tenant.
- **Fix:** On deactivating the user's **last** active membership, blacklist their outstanding refresh tokens (as `ChangePasswordView` does); optionally maintain a per-user "not-before" timestamp checked in authentication.

---

### [B6-018] Restore does not enforce `EXPORT_VERSION`
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `backend/accounts/tenant_backup.py:29` (`EXPORT_VERSION = 1`), `:366-427` (`decrypt_export_zip`), `:638` (`import_payload`)
- **Observation:** `decrypt_export_zip` reads `manifest.get("version", EXPORT_VERSION)` into the payload but nothing ever compares it; `import_payload` blindly consumes whatever sections are present.
- **Impact:** A backup written by a future schema (different field set, renamed sections) is imported best-effort — missing sections silently become empty, changed field semantics are applied verbatim — producing a partial/incorrect tenant with no error. Also removes a guard against a hand-crafted blob if the instance Fernet key is ever exposed.
- **Fix:** Reject (or explicitly migrate) any payload whose `version` != `EXPORT_VERSION` in `decrypt_export_zip` / `TenantRestoreView`.

---

### [B6-019] Soft-reference CharField columns keep source PKs after restore (dangling "source document" links)
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `backend/accounts/tenant_backup.py:989-1002` (`stock_movements` import) — `StockMovement.reference_type` / `reference_id` are plain `CharField`s (`inventory/models.py`); similar untyped back-references exist on other models
- **Observation:** `_copy_model_fields` only remaps real `*_id` FK columns. `reference_id` (a stringified PK of the originating sales invoice / challan / adjustment) is copied unchanged.
- **Impact:** After a sandbox restore or destroy-in-place reload, `reference_id` still points at the old numeric id; "open source document" navigation dangles or resolves to an unrelated row (possibly another tenant's, since ids are global). Purely cosmetic-to-confusing today, but a latent trust issue if any code ever dereferences `reference_id` without a company filter.
- **Fix:** Rewrite known soft-reference columns using the same id maps during import (e.g. when `reference_type == "sales_invoice"`, map `reference_id` through `sales_map`), or blank them on restore.

---

### [B6-020] `accounts_companyuser` / `accounts_companygstin` are permanently outside RLS
- **Severity:** Info
- **Category:** Gap
- **Location:** `backend/core/migrations/0020_rls_all_tenant_tables.py:16-18` (excluded), `backend/tests/test_rls_coverage.py:14` (`_EXCLUDED`)
- **Observation:** Both tables are intentionally excluded so the middleware can read them to resolve the tenant before setting `app.company_id`. Every access therefore relies solely on hand-written `.filter(company=…)` in app code (`CompanyUserViewSet.get_queryset`, `CompanyGstinViewSet.get_queryset`, `_active_owner_count`, `_enforce_plan_seat_limit`, `MembershipsListView`, `build_export_payload`, etc. — all currently correct).
- **Impact:** No database backstop for these two tables. Any future raw SQL, `.objects` manager use, admin action, or a forgotten filter is an immediate cross-tenant membership/GSTIN disclosure or, worse, a cross-tenant membership write (role/capability escalation).
- **Fix:** Consider an RLS policy on these two that also allows the row whose `company_id` has no GUC yet only for the narrow `SELECT` the middleware needs (e.g. a dedicated `SECURITY DEFINER` resolver function), so writes/broad reads are still policy-bound. At minimum, add targeted cross-tenant tests for every CompanyUser/CompanyGstin code path.

---

### [B6-021] RLS correctness depends on the app DB role being NOSUPERUSER / NOBYPASSRLS — never asserted
- **Severity:** Info
- **Category:** Security
- **Location:** `backend/core/migrations/0020_rls_all_tenant_tables.py` (uses `FORCE ROW LEVEL SECURITY`), `backend/config/settings.py:760-764`
- **Observation:** `FORCE ROW LEVEL SECURITY` makes the policy apply to the table owner, but a Postgres **superuser** connection and any role with `BYPASSRLS` ignore all policies. Nothing in settings, a system check, or a startup assertion verifies the configured `DATABASES` role lacks those attributes.
- **Impact:** A deploy that points Django at a superuser role (a common convenience in smaller setups) silently disables the entire multi-tenant isolation layer while every test still passes.
- **Fix:** Add a Django system check / startup assertion: `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user` must be `(f, f)` when `POSTGRES_RLS_ENABLED`.

---

### [B6-022] `LoginView` runs the password hash twice for valid members
- **Severity:** Info
- **Category:** Performance
- **Location:** `backend/accounts/views.py:310-324`
- **Observation:** `pending_user.check_password(password)` in the pre-check, then `super().post()` authenticates again. Also `_record_login_failure` is only reached via the `except AuthenticationFailed` around `super().post()`, so the membership pre-check's `PermissionDenied`/`AuthenticationFailed` raises do not increment the failure counter (they require a correct password anyway, so low risk, but the asymmetry is worth noting).
- **Impact:** Doubled KDF cost per successful login (minor CPU / latency); see B6-008 for the security-relevant timing consequence.
- **Fix:** Fold the membership check into the post-`super().post()` success branch and remove the standalone `check_password` call.

---

### [B6-023] `get_company_user` silently switches a user to their other membership when the active one is deactivated
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `backend/core/permissions.py:44-55`
- **Observation:** If `active_company_id` is set but `qs.filter(company_id=active_company_id).first()` returns `None` (that membership was deactivated) and the user has exactly one other active membership, the code returns `memberships[0]` for a **different** company without updating `active_company` and without any signal to the client.
- **Impact:** A user removed from company A is transparently operating "as" company B on their next request; `active_company` still says A. Confusing, and RLS/`X-Company-Id` context can briefly disagree with what the UI shows. Not a cross-tenant breach (it is still the user's own membership), but a surprising implicit context switch.
- **Fix:** When the stored `active_company` membership is gone, clear `active_company` and raise `CompanyRequired` (or return `None` → `HasCompany` 403) rather than auto-selecting.

---

### [B6-024] Restore rate-limit key is set mid-operation; failed / partial restores block retries for 10 minutes with an opaque state
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `backend/accounts/export_views.py:74-113` (`TenantRestoreView.post`)
- **Observation:** `cache.set(cache_key, 1, timeout=EXPORT_CACHE_TTL)` runs after decrypt + source-company check but before `restore_destroy_in_place` / `restore_to_sandbox`. If the restore then raises (e.g. B6-001, or an integrity error deep in `import_payload`), the transaction rolls back but the 10-minute lock remains.
- **Impact:** The owner cannot retry for 10 minutes and gets only a generic 500; for destroy-in-place there is no progress/result surface to know whether the wipe rolled back cleanly.
- **Fix:** Set the throttle key only on a successful restore, or delete it in an `except` block; return a structured error identifying the failing section.

---

### [B6-025] `AcceptInviteView` shares the tight `login` throttle bucket
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `backend/accounts/views.py:796-797` (`AcceptInviteView.throttle_scope = "login"`)
- **Observation:** Invite acceptance is counted against the same per-IP `login` scope (10/min, `ScopedRateThrottle` keyed on IP for anonymous requests) as password logins.
- **Impact:** Users behind a shared NAT/office IP can exhaust the 10/min budget for each other, causing spurious 429s on both login and invite acceptance during onboarding bursts. `CookieTokenRefreshView` was already given its own scope for exactly this reason (`token_refresh`, comment at `:359-362`).
- **Fix:** Give invite acceptance its own throttle scope with an onboarding-appropriate rate.

---

### [B6-026] `role` is settable to `OWNER` via `CompanyUserSerializer` PATCH with no dedicated guard/audit
- **Severity:** Info
- **Category:** Security
- **Location:** `backend/accounts/serializers.py:356-407` (`CompanyUserSerializer.validate` — no `validate_role`), vs `InviteUserSerializer.validate_role` (`:435-441`) which blocks `OWNER`
- **Observation:** Owner-to-owner promotion is done by PATCHing `role="OWNER"` on any membership. It is `IsOwner`-gated (`CompanyUserViewSet.permission_classes`), so only an existing owner can do it, and `_assert_role_capability_invariants` imposes no restrictions for `OWNER`. The generic `AuditService.log(action="UPDATE", entity_type="CompanyUser")` does not distinguish a privilege promotion from a name/flag edit.
- **Impact:** Low direct risk (requires an existing compromised/malicious owner), but owner promotion is the highest-impact RBAC change in the product and has no explicit confirmation step, no dedicated audit action, and no notification to other owners.
- **Fix:** Route owner promotion through an explicit endpoint/flag that emits a distinct audit action (`PROMOTE_OWNER`) and notifies existing owners; keep `CompanyUserSerializer` from accepting `role=OWNER` directly.

---

# Deep code review — cluster B7 (core, config, search)

**Scope reviewed (every line):**
`backend/config/` — settings.py, settings_test.py, celery.py, urls.py, asgi.py, wsgi.py
`backend/core/` — events.py, handlers.py, exceptions.py, help_codes.py, help_views.py, csv_utils.py,
validators.py, viewsets.py, pagination.py, renderers.py, serializers.py, models.py, views.py, urls.py,
tasks.py, celery_utils.py, apps.py, management/commands/*, and services/: audit.py, bill_images.py,
billing.py, feature_flags.py, files.py, gsp_adapters.py, gsp_secrets.py, gstin_verify.py, h9_amend.py,
llm.py, notifications.py, place_of_supply.py, sms.py, uqc.py, whatsapp.py
`backend/search/` — views.py, urls.py, apps.py
Tests skimmed for intent: tests/test_search_reports_audit.py, tests/test_a06_whatsapp.py, tests/test_file_sniff_import.py,
tests/test_sprint_e_gsp_protocol.py.

**Explicitly out of scope (reviewed elsewhere):** authentication.py, rls.py, middleware.py, idempotency.py,
throttles.py, permissions.py, services/document_numbers.py, services/charges.py, services/registration_gates.py,
services/identity_verify.py. Findings that touch those files are cross-references only.

## Severity counts

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 2 |
| Medium   | 4 |
| Low      | 13 |
| Info     | 2 |
| **Total**| **21** |

General note: `config/settings.py` is already heavily hardened (dozens of `BB-*` / `CFG-*` gates for DEBUG,
ALLOWED_HOSTS, SECRET_KEY, CORS/CSRF, secure cookies, DB SSL/timeouts, broker creds, secret fallbacks). The
GST-math in `services/billing.py` and the GSP fail-closed gating in `services/gsp_adapters.py` are likewise
well covered. Remaining findings are mostly at the edges.

---

### [B7-001] Search per-query `statement_timeout` guard is defeated by lazy QuerySets
- **Severity:** High
- **Category:** Performance
- **Location:** `backend/search/views.py:54-120`
- **Observation:** `with _search_query_guard():` issues `SET LOCAL statement_timeout` inside a
  `transaction.atomic()` (lines 20-29). Inside the block only `customers`, `suppliers`, `products` are
  *assigned* as sliced-but-unevaluated QuerySets (lines 55-75); the `invoices` list-comprehension (lines
  89-101) is the only part actually executed inside the guard. The customer/supplier/product queries are
  first evaluated in the final `return Response({...})` dict-building at lines 103-120 — **after** the
  `atomic()` block has exited and the `SET LOCAL` scope is gone.
- **Impact:** The `Q(name__icontains=q) | Q(phone__icontains=q) | Q(gstin__icontains=q)` leading-wildcard
  scans on `Customer` / `Supplier` / `Product` (exactly the queries the 5 s cap in BB-000492 was meant to
  bound) run with **no** statement timeout. On a large tenant with no trigram index these are sequential
  scans; a burst of `/api/v1/search/?q=aa` requests can pin Postgres backends for far longer than 5 s each.
- **Fix:** Force evaluation inside the guard, e.g. `customers = list(Customer.objects.filter(...)[:LIMIT])`
  (and likewise for suppliers/products) before the `with` block exits, or build the entire response payload
  inside `_search_query_guard()`.

---

### [B7-002] No Celery task time limits and no `EMAIL_TIMEOUT` — a hung call blocks a worker forever
- **Severity:** High
- **Category:** Gap
- **Location:** `backend/config/settings.py` (no `CELERY_TASK_TIME_LIMIT` / `CELERY_TASK_SOFT_TIME_LIMIT` /
  `EMAIL_TIMEOUT`), `backend/core/tasks.py:10-59`
- **Observation:** `grep` for `time_limit|soft_time_limit|EMAIL_TIMEOUT` across `config/` and `core/` returns
  nothing. `send_email_notification` calls `django.core.mail.send_mail(..., fail_silently=False)` with
  `autoretry_for=(Exception,)` but no soft time limit; the SMTP socket has no timeout (`EMAIL_TIMEOUT` unset).
  Other services (`gsp_adapters._http_json` timeout=30, `whatsapp` timeout=30, `llm` EXTRACT_TIMEOUT_SECONDS=90)
  are bounded per-call, but any task without an explicit per-call timeout (or any future one) inherits no ceiling.
- **Impact:** A slow/blackholed SMTP relay (or any un-timed network call in a task) holds a worker slot and
  its prefetched messages indefinitely; enough of them starve the queue. The CORE-13 comment in `tasks.py`
  specifically moved work *out* of a DB lock to avoid this, but the worker-slot exhaustion path remains.
- **Fix:** Set `EMAIL_TIMEOUT` (e.g. 10 s) and global `CELERY_TASK_SOFT_TIME_LIMIT` / `CELERY_TASK_TIME_LIMIT`
  in settings; optionally per-task overrides for the known-long ones (bill extract).

---

### [B7-003] `prune_help_events` management command has no `rls_bypass()` — silently no-ops under FORCE RLS
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `backend/core/management/commands/prune_help_events.py:20-29`
- **Observation:** `HelpEvent.objects.filter(created_at__lt=cutoff).delete()` runs with no RLS GUC set. The
  equivalent Celery task `core/tasks.py:prune_help_events_task` wraps the identical delete in
  `with rls_bypass():` and its docstring explains that FORCE RLS otherwise hides other tenants' rows.
- **Impact:** `python manage.py prune_help_events` on a Postgres deployment with `POSTGRES_RLS_ENABLED=1`
  (the default) deletes only rows visible under whatever `app.company_id` happens to be unset/blank — in
  practice zero rows. An operator running the documented command believes retention is enforced when it is
  not; `HelpEvent` grows unbounded (the table stores raw user query text).
- **Fix:** Wrap the delete in `with rls_bypass():` exactly as the task does, or have the command call the task.

---

### [B7-004] IRP "custom" provider payload wrapper is an HMAC placeholder, not NIC SEK/AES encryption
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `backend/core/services/gsp_adapters.py:339-369` (`wrap_irp_payload`), used by
  `LiveIrpAdapter.submit` (lines 535-541)
- **Observation:** For `provider == "custom"` the "wrapped" body is
  `{"payload": payload, "payload_b64": ..., "hmac_sha256": mac, "encryption": "hmac-placeholder-not-nic-sek"}`
  where `mac` falls back to the literal key `b"bizboard-gsp-hmac-placeholder"` when no `api_secret` is present.
  The docstring says a certified integration "must replace this hook with real session-key wrapping before
  `GSP_CERTIFIED=1` is signed off".
- **Impact:** The only gate on live submit is operator-set `GSP_LIVE_ENABLED=1 && GSP_CERTIFIED=1` plus
  non-placeholder creds. If an operator flips those with `GSP_PROVIDER=custom` (the default when the env value
  is not `cleartax`/`mastergst`), Bizboard POSTs the raw invoice JSON to `GSP_LIVE_BASE_URL` with a
  cosmetic HMAC and no real payload confidentiality — the code path is "protocol-shaped" enough to look done.
- **Fix:** Make `LiveIrpAdapter` refuse `provider == "custom"` unless a real SEK-wrapping implementation is
  present (raise `BusinessRuleError`), or hard-require `api_secret` and a non-placeholder `encryption` marker
  before any live POST.

---

### [B7-005] Celery `task_prerun` resolves `company_id` by SELECTing tenant rows before the RLS GUC is set
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/config/celery.py:26-58` (`_company_id_from_document`), `:117-132`
  (`set_rls_company_for_task`)
- **Observation:** When a task is enqueued with only a document PK (e.g. `invoice_id`) and no `company_id`
  kwarg, `set_rls_company_for_task` calls `_company_id_from_document`, which runs
  `SalesInvoice.objects.filter(pk=pk).values_list("company_id", ...)` **before** `set_rls_company()` is
  called. The module comment acknowledges this ("prefer `company_id` in kwargs so we never SELECT tenant
  rows before setting the RLS GUC") but the fallback still does it.
- **Impact:** On Postgres with FORCE RLS and no `app.company_id` set, that pre-GUC SELECT returns nothing,
  so `company_id` stays `None`, and the task then runs with RLS company unset — its own queries either see
  nothing or the task fails. Any `.delay(invoice_id=...)` call site that doesn't also pass `company_id`
  is affected. (RLS policy itself is out of scope — flagged here for the celery.py glue.)
- **Fix:** Require `company_id` in kwargs for tenant tasks (assert in prerun), or perform the document→company
  lookup under an explicit `rls_bypass()` in `_company_id_from_document`.

---

### [B7-006] No application-level ceiling on total upload request size before `FileService` size check
- **Severity:** Medium
- **Category:** Security
- **Location:** `backend/config/settings.py:599-604`, `backend/core/services/files.py:170-181`
- **Observation:** `DATA_UPLOAD_MAX_MEMORY_SIZE` / `FILE_UPLOAD_MAX_MEMORY_SIZE` are raised to 15 MB but
  those only control the memory-vs-tempfile spool threshold, not rejection, for multipart file parts.
  `FileService.validate_upload` rejects on `uploaded_file.size > max_size` (5–20 MB per kind) — but only
  *after* Django has fully received the request body and spooled the oversized part to `MEDIA`/`/tmp`.
- **Impact:** A client can stream an arbitrarily large file to `POST /api/v1/files/` (or any upload
  endpoint); the whole body is written to disk before the size guard fires and 400s. Repeated requests fill
  the temp/disk volume. The only real cap is the reverse proxy's `client_max_body_size`, which is not
  asserted anywhere in this repo.
- **Fix:** Add a small WSGI/middleware guard that 413s when `CONTENT_LENGTH` exceeds a hard ceiling, and/or
  document a required `client_max_body_size` and fail the deploy check if it can't be confirmed.

---

### [B7-007] HSTS is not enabled for `DJANGO_ENV=staging` unless `USE_TLS=1`
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/config/settings.py:606-617`
- **Observation:** Secure cookies are set for `production` or `staging` or `USE_TLS`, but
  `SECURE_HSTS_SECONDS` / `SECURE_HSTS_INCLUDE_SUBDOMAINS` are only set when
  `DJANGO_ENV == "production" or _use_tls`. A staging host on HTTPS behind a terminating proxy but without
  `USE_TLS=1` serves no `Strict-Transport-Security` header.
- **Impact:** Staging is downgrade-attackable on first visit; also a weaker parity check vs production.
- **Fix:** Include `staging` in the HSTS branch (optionally with a shorter max-age), or drive HSTS off the
  same condition as the secure-cookie block.

---

### [B7-008] `csv_safe` does not neutralize a leading line feed (`\n`)
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/core/csv_utils.py:27`
- **Observation:** The guard escapes values whose first non-space char is in `("=", "+", "@", "\t", "\r")`.
  The OWASP CSV-injection character set also includes `\n` (LF). A value like `"\n=1+cmd|' /C calc'!A0"`
  is passed through unquoted.
- **Impact:** Minor — most spreadsheet importers treat a leading LF within a quoted field as whitespace, but
  some CSV dialects and downstream tools can re-split on it, re-exposing the formula.
- **Fix:** Add `"\n"` to the escaped-prefix tuple.

---

### [B7-009] `validate_gst_rate` raises `decimal.InvalidOperation` (not `ValidationError`) on non-numeric input
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/core/validators.py:66-72`
- **Observation:** `Decimal(value) not in tuple(Decimal(r) for r in ALLOWED_GST_RATES)` — `Decimal("abc")`
  raises `decimal.InvalidOperation`, which is not a `ValueError` and not a `django ValidationError`, so it
  is not mapped by `core/exceptions.api_exception_handler` (which handles `IntegrityError` and
  `DjangoValidationError` only) and bubbles as a logged 500.
- **Impact:** Reachable when this validator runs on a raw string outside a DRF DecimalField (a service
  calling `model.full_clean()`, or `applied_rate` paths). Returns 500 where a 400 is intended.
- **Fix:** `try: rate = Decimal(str(value)) except (InvalidOperation, TypeError): raise ValidationError(...)`.

---

### [B7-010] `billing._document_tax_date` can raise `ValueError` → 500 on a malformed date string
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/core/services/billing.py:356-374`
- **Observation:** `return date_cls.fromisoformat(str(val)[:10])` when `val` is a string. A non-ISO string
  (e.g. `"01/02/2026"` from an odd import/preview payload) raises `ValueError`, uncaught, through
  `apply_effective_gst_rate` / `compute_document_totals`.
- **Impact:** Totals-preview / rate-resolution 500 instead of a validation error, on bad client input.
- **Fix:** Wrap in `try/except ValueError: return None`, or use `django.utils.dateparse.parse_date`.

---

### [B7-011] Intra-state CGST/SGST split can exceed `taxable*rate/100` by a paisa; the comment says the opposite
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `backend/core/services/billing.py:191-208`
- **Observation:** `half = q2(tax / 2); item.cgst = half; item.sgst = half`. For `tax = 5.01`,
  `half = q2(2.505) = 2.51` (ROUND_HALF_UP) → `cgst + sgst = 5.02`, i.e. one paisa **more** than the
  computed line tax. The inline comment claims "any odd third-place paise is *dropped* from the line tax and
  re-absorbed by the document round-off leg".
- **Impact:** Per-line tax total can be 0.01 higher than the strict `Σ taxable*rate/100`; footed by
  `round_off` at the document level so grand-total stays consistent, but GSTR rate-bucket tax may be a paisa
  off strict recompute for odd-paise lines. Cosmetic but the comment is misleading for the next maintainer.
- **Fix:** Either keep the behaviour and correct the comment, or use `cgst = q2(tax/2); sgst = q2(tax) - cgst`
  (asymmetric-by-one-paisa) if bucket exactness matters more than CGST==SGST.

---

### [B7-012] OTP debug echo logs the full OTP code; contradicts the settings comment
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/core/services/sms.py:166-172`; comment at `backend/config/settings.py:515-517`
- **Observation:** `settings.py` says the debug echo "logs phone suffix only — never the code", but
  `SmsProvider.send_otp` does `logger.debug("OTP debug echo code=%s for phone ending %s", code, ...)`.
  It is gated to `env in ("development", "test", "")` + `OTP_DEBUG_ECHO`, and `OTP_DEBUG_ECHO` is
  hard-rejected in production/staging — so it is not a prod leak — but the plaintext OTP does land in logs
  in dev/CI, and the settings comment is wrong.
- **Impact:** Misleading security claim; plaintext OTP in dev/test log aggregation.
- **Fix:** Log only a hash/prefix of `code`, or fix the settings comment to state the code is echoed at
  DEBUG in dev/test.

---

### [B7-013] Inconsistent "no active company" handling across help views
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `backend/core/help_views.py:223-226` vs `:206-209/257-261`; `:296-303`
- **Observation:** `HelpFeedbackView.get` returns `200 {"results": []}` when `_cu(request)` is `None`, while
  `post`/`patch` return `_no_company()` (403). `HelpHealthView.get` calls `_cu(request)` unguarded, so a
  multi-membership `is_staff` user with no active company gets an unhandled `CompanyRequired` 409 (with the
  membership list in the body) instead of the aggregate they asked for with `?all=1`.
- **Impact:** Minor client confusion; the 409 body also discloses the staff user's full membership list on
  an analytics endpoint.
- **Fix:** Normalise: catch `CompanyRequired` in `HelpHealthView.get` and, for `staff_all`, proceed without a
  company; return a consistent status when `cu is None`.

---

### [B7-014] Statutory / audit tables cascade-delete with the company and have no tamper-evidence
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `backend/core/models.py` — `AuditEvent` (`:157-159` `on_delete=CASCADE`),
  `MoneyFieldAudit` (`CompanyScopedModel` → `:37-39` CASCADE), `StatutoryDocumentEvent` (`:283-285` CASCADE)
- **Observation:** All three "append-only" logs are child rows of `accounts.Company` with
  `on_delete=models.CASCADE`, and there is no hash-chaining, no DB-level `INSERT`-only enforcement, and no
  `updated_at`/signature. `AuditService.log` / `log_statutory_event` are the only writers by convention.
- **Impact:** A tenant delete (or any direct DB write / a bug that calls `.delete()`) silently removes the
  statutory trail that an Indian GST audit may require to be retained for years. "Append-only" is a naming
  convention, not a guarantee.
- **Fix:** Use `on_delete=PROTECT` (or a soft-delete / archival export on tenant removal) for these tables;
  consider a per-row `prev_hash` chain or a periodic signed digest for tamper-evidence.

---

### [B7-015] GSTIN / GSP HTTP clients do not restrict the URL scheme of operator-set base URLs
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/core/services/gstin_verify.py:76-95`, `backend/core/services/gsp_adapters.py:435-452`
- **Observation:** `urllib.request.urlopen(Request(f"{base}/gstin/{gstin}"))` and `_http_json` build the URL
  from `GSP_SANDBOX_BASE_URL` / `GSP_LIVE_BASE_URL` with no scheme allow-list. `urllib` honours `file://`,
  `ftp://`, etc. TLS cert verification *is* on by default, and `gstin` is `GSTIN_RE`-validated so the path is
  safe, and the base URLs are env-set (not user-set), so this is a hardening gap rather than a live SSRF.
- **Impact:** A misconfigured or attacker-influenced env var (`GSP_SANDBOX_BASE_URL=file:///etc/passwd`)
  turns a lookup into a local file read / link-local metadata fetch.
- **Fix:** Assert `urlsplit(base).scheme in {"https", "http"}` (https-only outside dev) when reading these
  settings, and block link-local / private hosts.

---

### [B7-016] `extract_purchase_bill` has no per-job cost ceiling / token budget
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/core/services/llm.py:512-607`
- **Observation:** The extractor loops up to `MAX_EXTRACT_CHUNKS = 4` LLM calls, each with
  `max_tokens = EXTRACT_MAX_TOKENS = 16384` and `detail: "high"` images (`views_for_si_range` returns up to
  4 images/call). There is no check against `company.ai_monthly_token_budget` /
  `AI_MONTHLY_TOKEN_BUDGET_DEFAULT` here — that budget is enforced only in `insights/assistant.py`, not on
  the bill-import path.
- **Impact:** A tenant repeatedly re-running bill extraction (or uploading many multi-page bills) incurs
  unbounded LLM spend on the import path; the only cap is `LLM_BILL_MAX_PAGES*` (page count) applied by the
  caller in `imports/tasks.py`.
- **Fix:** Meter `usage` returned from `_call` against the company AI budget (same helper insights uses) and
  refuse extraction when exhausted; or add a per-ImportJob call/token cap.

---

### [B7-017] `HelpHealthView` runs a heavy 30-day aggregation with no dedicated throttle scope
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/core/help_views.py:291-388`
- **Observation:** Unlike `HelpEventsView` / `HelpFeedbackView` (`throttle_scope = "help_events"` /
  `"help_feedback"`), `HelpHealthView` sets no `throttle_scope` / `throttle_classes`, so it falls back to the
  default `user` rate (600/min). Each call runs `_time_to_resolution` (two 8000-row fetches into Python),
  `_latest_ratings`, and ~8 aggregate queries over `HelpEvent` for the last 30 days.
- **Impact:** An owner (or a `?all=1` staff user, which additionally `rls_bypass()`es to scan every tenant's
  events) can issue these hundreds of times a minute.
- **Fix:** Add `throttle_scope = "heavy_reports"` (already defined at 60/min) or a new `help_health` scope.

---

### [B7-018] LLM-extracted party name / GSTIN strings pass through with only `.strip()` (prompt-injection surface)
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/core/services/llm.py:276-287` (`_normalize_payload`)
- **Observation:** `supplier_name`, `supplier_gstin`, `buyer_name`, `buyer_gstin`, `bill_number`, `bill_date`
  are taken verbatim (`str(raw.get(...) or "").strip()`) from the model's JSON. Numeric line fields are
  coerced, but these header strings are not length-capped or format-checked here. A crafted bill image
  containing injected text ("SUPPLIER NAME: <script>… ignore prior instructions…") flows straight into the
  import staging record.
- **Impact:** Bounded (import staging is human-reviewed before commit, and downstream serializers validate
  GSTIN), but unvalidated attacker-controlled text enters the DB and any admin/CSV view of staging rows.
- **Fix:** Length-cap (e.g. 128) and run `supplier_gstin`/`buyer_gstin` through `GSTIN_RE` (drop if it
  doesn't match) inside `_normalize_payload`.

---

### [B7-019] `HelpEventsView.post` does up to 50 sequential SELECT+save round-trips per request
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/core/help_views.py:132-196`
- **Observation:** For each of up to 50 events, when `name in _RATING_NAMES and intent_id`, the loop does a
  `HelpEvent.objects.filter(...).order_by("-created_at").first()` then an `existing.save(...)` or a
  `HelpEvent.objects.create(...)` — no `bulk_create`, no prefetch of the existing rating rows.
- **Impact:** Up to ~100 queries per batched telemetry POST; throttled at 30/min so not catastrophic, but
  wasteful and holds a connection longer than needed.
- **Fix:** Fetch the latest rating row per `intent_id` in one query keyed on `(intent_id)`, then
  `bulk_create` the non-rating events.

---

### [B7-020] Health probe hard-codes the queue name `"celery"` for `pdf_queue_depth`
- **Severity:** Info
- **Category:** Improvement
- **Location:** `backend/core/views.py:27` (`_CELERY_QUEUE = "celery"`), `:89`
  (`client.llen(_CELERY_QUEUE)`)
- **Observation:** `_probe_celery_and_queue` reports `pdf_queue_depth` as `LLEN celery`. `CELERY_BEAT_SCHEDULE`
  and `config/celery.py` show no custom routing today, so this is currently correct, but any future
  `task_routes` / dedicated `pdf` queue makes the reported depth silently wrong (always 0), and the field is
  named `pdf_queue_depth` as if it were PDF-specific.
- **Fix:** Read the queue name(s) from Celery config / a setting, or rename the field to
  `default_queue_depth`.

---

### [B7-021] `api_exception_handler` echoes the full DRF `detail` object into `error.details`
- **Severity:** Info
- **Category:** Improvement
- **Location:** `backend/core/exceptions.py:223-250`
- **Observation:** For DRF-handled exceptions the original `response.data` is placed verbatim under
  `error.details`. This is not a stack-trace leak (unhandled 500s are correctly caught at lines 201-221 and
  return a generic body with the traceback only logged), and it is useful for field-level validation errors.
  Noted only because `details` can be a large nested structure for complex serializers and is returned to
  the client unfiltered.
- **Fix:** None required; if payload size becomes a concern, cap `details` depth/size for non-400 statuses.

---

## Notes on things checked and found OK
- `settings.py`: DEBUG/ALLOWED_HOSTS/SECRET_KEY/CORS/CSRF/secure-cookie/DB-timeout gating is thorough;
  `CORS_ALLOW_CREDENTIALS` + wildcard is asserted against; LLM/GSP/SMS keys read with no insecure fallback
  and prod/staging fail-closed.
- `MetricsView`: `authentication_classes=[]`, 404 when `METRICS_TOKEN` unset, `hmac.compare_digest` bearer
  check otherwise — correct.
- `renderers.EnvelopeJSONRenderer` / `pagination.DefaultPagination`: CORE-06 double-wrap guard and CORE-14
  pk tie-break are sound.
- `services/files.py`: magic-byte sniffing, xlsx zip-bomb caps, fail-closed ClamAV, uuid storage names
  (no path traversal from `original_name`), download filename sanitised in `views.py`.
- `services/gsp_adapters.py`: live IRP/e-Way/GSTR adapters are fail-closed behind
  `GSP_LIVE_ENABLED && GSP_CERTIFIED && env`; `reject_placeholder_gsp_credentials` blocks all-`A` secrets;
  every `urllib` call has a timeout. (See B7-004 for the custom-provider wrapper.)
- `services/gstin_verify.py`: Null provider never stamps `gstin_verified_at`; sandbox VALID can't stamp in
  prod/staging without `GSP_CERTIFIED` (BB-000734).
- `services/place_of_supply.py` / `billing.is_intra_state`: blank/unmappable POS is treated as inter-state
  for the calc and gated at Complete — no silent intra assumption.
- `services/whatsapp.py`: per-company encrypted creds only, template allow-list, `timeout=30`, wa.me
  fallback never claims SENT.
- `core/tasks.send_email_notification`: Redis `cache.add` dedup lock + SENT-status short-circuit prevents
  duplicate sends on retry (separate from B7-002, which is about the missing timeout).

---

# Deep code review — module cluster B8

**Scope reviewed (every line):**
- `backend/inventory/` — `models.py`, `services.py` (1689 lines), `item_stock.py`, `views.py`, `serializers.py`, `urls.py`, `apps.py`, `management/commands/rebuild_running_cost.py`, `management/commands/rebuild_stock_balances.py`
- `backend/masters/` — `models.py`, `serializers.py`, `views.py`, `custom_fields.py`, `hsn_catalog.py`, `pricing.py`, `urls.py`, `apps.py`, `management/commands/backfill_uqc.py`
- `backend/manufacturing/` — `models.py`, `services.py`, `views.py`, `serializers.py`, `permissions.py`, `admin.py`, `urls.py`, `apps.py`
- Tests: `test_w0_valuation.py`, `test_wave22_f2_fifo_serial_mfg.py`, `test_phase4_inventory.py` (partial), `test_sprint_b_manufacturing_cancel.py`, plus inventory of `test_sprint3_inventory.py`, `test_stock_flow.py`, `test_item_custom_fields.py`, `test_b06_hsn_rate.py`, `test_sprint3_multicompany_pricing.py`.
- Cross-refs read: `core/viewsets.py`, `core/idempotency.py`, `core/validators.py`, `config/settings.py` (DB block), `sales/cogs_service.py` (head), `sales/return_service.py` (excerpt).

**Confirmed environment fact:** `DATABASES["default"]` has no `ATOMIC_REQUESTS` (Django default `False`) and `CompanyScopedViewSet` does not wrap `perform_create`/`perform_update` in a transaction — so DRF serializer `create`/`update` methods that do multi-row writes are **not atomic**.

## Severity counts

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 4 |
| Medium | 14 |
| Low | 13 |
| Info | 6 |
| **Total** | **37** |

---

### [B8-001] Two independent FIFO costing engines that can silently disagree
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `backend/inventory/services.py:491` (`_apply_cost_layers`), `:1522` (`_replay`), `:1631` (`unit_cost`)
- **Observation:** On every issue, `_apply_cost_layers` peels the perpetual `InventoryCostLayer` rows and stamps `StockMovement.unit_cost`/`layer_peels`. But `InventoryValuationService.valuation()` for FIFO **never reads `InventoryCostLayer`** — `valuation(as_of=None)` for FIFO falls straight through to `_replay(movements.order_by("created_at","id"))` (the running-cost fast path at `:1421` is `method == "WAVG"` only), and `unit_cost()` FIFO also replays via `cls.valuation(...)`. `_replay` rebuilds its own `entry["layers"]` list from `move.quantity/move.unit_cost`.
- **Impact:** The COGS booked on a sale (from peeled layers, incl. the `layer_id: None` invented-shortfall peel at `:597` and the ADJUSTMENT WAVG-fallback cost at `:519-529`) is computed by a different algorithm than the FIFO stock-valuation report the user sees. Divergence sources: the invented shortfall peels, ADJUSTMENT inbound layers costed at heal-time WAVG, `movement.unit_cost` truncation (see B8-004), and `restore_fifo_peels` creating fresh layers when `layer_id` is missing. Balance-sheet inventory value and P&L COGS will not reconcile for FIFO tenants with any oversell / adjustment / transfer history.
- **Fix:** Make `valuation()`/`unit_cost()` for FIFO read the live `InventoryCostLayer` table (sum `qty_remaining * unit_cost` per key) for `as_of=None`, exactly as WAVG reads `InventoryRunningCost`. Keep `_replay` only for historical `as_of`. Add a reconcile assertion in `rebuild_*` that layer value == replay value.

### [B8-002] Non-atomic serializer writes corrupt child rows on mid-write error
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `backend/manufacturing/serializers.py:45-58` (`BomSerializer.update`); same pattern `backend/inventory/serializers.py:202-228` (`StockTransferSerializer.update`), `:324-379` (`StockCountSessionSerializer`), `backend/masters/serializers.py:282-300` (`PriceListSerializer`)
- **Observation:** `BomSerializer.update` does `instance.lines.all().delete()` then `for line in lines_data: if <fg is component>: raise serializers.ValidationError(...); BomLine.objects.create(...)`. With `ATOMIC_REQUESTS` off and no `transaction.atomic()` in the viewset/serializer, the `DELETE` and any partial `create`s are already committed when the `ValidationError` returns HTTP 400.
- **Impact:** User submits an invalid BOM edit → gets a 400 → the BOM now has **no component lines** (or a partial set). Same class of loss for `StockTransfer` lines, `StockCountSession` lines (tenant-check `ValidationError` after `delete()`), and `PriceList` items (any `IntegrityError` from `uniq_product_slab_per_list` after `delete()` empties the list).
- **Fix:** Wrap each of these `create`/`update` bodies in `with transaction.atomic():`, or set `ATOMIC_REQUESTS = True` for the default DB. Validate the whole payload (FG-not-a-component, slab overlap, tenant) **before** any delete.

### [B8-003] `InventoryRunningCost` is not a weighted average for out-flows; drift check only guards qty
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `backend/inventory/services.py:433-449` (`_apply_running_cost`), `:469-487` (`rebuild_running_cost` drift check)
- **Observation:** For `delta < 0`: `avg = value/qty; use = cost if cost else avg; value -= issue * use`. When the caller supplies an explicit `unit_cost` on an out-flow (TRANSFER_OUT carries the FIFO/WAVG stamped cost `:1190`; MANUFACTURE_ISSUE carries `InventoryValuationService.unit_cost` `:149`; purchase-return / cancel ADJUSTMENTs carry the original cost), the running value is decremented by `issue * that_cost`, **not** `issue * running_avg`. `rebuild_running_cost` replays the same way and its only integrity gate is `if rc_qty != bal_qty` — **value is never checked**.
- **Impact:** `InventoryRunningCost.value` and therefore `unit_cost` (`value/qty`, the number surfaced as live WAVG cost and used for COGS/GL on WAVG tenants) drifts whenever costed out-flows exist. `_heal_running_zero_cost` only repairs rows that went `<= 0`; a wrong-but-positive value persists silently ("that full replay is deliberately off the hot path", `:1320`). Rebuild will not detect it.
- **Fix:** For WAVG out-flows always consume at the current running average (ignore caller `unit_cost` for `delta < 0` in WAVG mode). Add a value-drift assertion to `rebuild_running_cost` (compare against a full FIFO/replay valuation within tolerance).

### [B8-004] FIFO issue cost truncated to 2 dp on `StockMovement.unit_cost`, peels kept at 4 dp
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `backend/inventory/models.py:88` (`unit_cost = DecimalField(max_digits=12, decimal_places=2)`), `backend/inventory/services.py:606-609`
- **Observation:** `_apply_cost_layers` computes `stamped = (cost_total / need).quantize(Decimal("0.0001"))` and writes it with `StockMovement.objects.filter(pk=...).update(unit_cost=stamped, layer_peels=peels)`. The column is `decimal_places=2`, so the DB stores the value rounded to paise, while `layer_peels[*].unit_cost` are 4-dp strings and `InventoryCostLayer.unit_cost` is `decimal_places=4`.
- **Impact:** COGS read back from `move.unit_cost * qty` (e.g. `manufacturing/services.py:_issue_cost_total`, GL posting, valuation `_replay` which uses `move.unit_cost`) loses up to ₹0.005/unit versus the peel detail. Over large quantities and many issues this accumulates into a visible inventory/COGS reconciliation gap and makes B8-001 worse.
- **Fix:** Widen `StockMovement.unit_cost` to `decimal_places=4` (migration) or store the fractional COGS as a separate `issue_cost_total` field; never let the 2-dp column be the source of truth for FIFO COGS.

### [B8-005] `ExpiryAlertsView.get` performs writes + sends emails on a GET
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/inventory/views.py:413-421`; `backend/inventory/item_stock.py:303-368` (`record_expiry_bands`)
- **Observation:** `def get(self, request): ... rows = expiry_horizon_rows(...); record_expiry_bands(company, rows)`. `record_expiry_bands` `bulk_create`s `ExpiryAlertLog` rows and synchronously calls `NotificationService.send(... channel=EMAIL ...)` in a Python loop.
- **Impact:** A safe method has side effects: any `CanViewInventorySurfaces` user (or a prefetch/link-preview/monitoring probe) hitting the expiry page fires customer-facing expiry emails and writes log rows. Repeated loads are only idempotent because of the `uniq_expiry_notice_per_band` de-dupe; the first load per band always emails. Request latency also scales with number of new bands (blocking SMTP).
- **Fix:** Move `record_expiry_bands` to the POST handler or a scheduled task; GET should be read-only. Send notifications via the async notification queue, not inline.

### [B8-006] Manual serial transition SOLD→RETURNED posts an uncosted inbound movement
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `backend/inventory/views.py:367-378` (`SerialNumberViewSet.transition`)
- **Observation:** On `SOLD → RETURNED` it calls `InventoryService.post_movement(... movement_type=MovementType.SALES_RETURN, quantity=Decimal("1") ...)` with **no `unit_cost`** and **no link to the original sale**. `_apply_cost_layers` does not treat `SALES_RETURN` as inbound (`:511-517` list excludes it) and there is no `restore_fifo_peels` call here, so on-hand goes +1 with no FIFO layer; `_apply_running_cost` gets `cost=0` and dilutes WAVG value. `_replay` (FIFO/historical) *does* re-add a layer at cost 0.
- **Impact:** Returning a serialized unit through the generic serial screen creates zero-cost stock: FIFO perpetual layers vs. balance qty diverge, WAVG `value/qty` drops, and the FIFO replay disagrees with perpetual (compounds B8-001). No reconciliation against the sale that removed the unit.
- **Fix:** Route serial returns through the sales-return service (which restores peels), or at minimum look up the SALE movement for that serial/reference and cost the `SALES_RETURN` at its stamped `unit_cost` + `restore_fifo_peels`.

### [B8-007] `unit_cost()` returns a cross-batch blended average for a specific-batch query when that batch's running row is zeroed
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/inventory/services.py:1634-1648`
- **Observation:** WAVG branch: `hit = qs.filter(batch_id=batch_id).first(); if hit and hit.qty: return hit.unit_cost`. If the batch row exists with `qty == 0` (or is missing), it falls through to `pos = [r for r in qs if qty>0]` — `qs` is filtered by product/warehouse but **not by batch** — and returns `total_val/total_qty` across *all other batches and the unbatched row*.
- **Impact:** COGS / transfer cost / WIP issue cost for a batch that has just been drawn down to zero (then e.g. an ADJUSTMENT or return references it) is priced at an unrelated batch's average. For expiry-sensitive goods the batches can have very different costs.
- **Fix:** When `batch` is supplied and no positive batch-specific running row exists, fall back to the batch-scoped replay (`cls.valuation(..., batch filter)`) or the batch's own last inbound cost — never the cross-batch pool.

### [B8-008] BOM is single-level only — nested/sub-assembly BOMs are silently not exploded
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `backend/manufacturing/services.py:17-41` (`_component_requirements`, `_snapshot_bom`)
- **Observation:** `_snapshot_bom` writes one `WorkOrderLine` per `bom.lines` row (`qty = line.qty * wo.qty`); `_component_requirements` returns that flat list. There is no recursion into a component that itself has an `ACTIVE` `Bom`.
- **Impact:** If a component is a manufactured sub-assembly, the work order issues the sub-assembly from finished stock (fine if it exists) but there is no BOM explosion, no multi-level WIP, and no warning. Users expecting a manufacturing BOM tree get wrong material requirements planning and cannot build make-to-order sub-assemblies in one WO.
- **Fix:** Either document/enforce "single-level only" (reject releasing a WO whose component has an ACTIVE BOM unless stock exists), or implement recursive explosion with cycle detection.

### [B8-009] By-product / scrap / co-product output is not modeled
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/manufacturing/models.py` (whole file), `backend/manufacturing/services.py:278-289`
- **Observation:** `complete_work_order` posts exactly one `MANUFACTURE_RECEIPT` for `wo.bom.product` at `unit_cost = issue_cost / wo.qty`. There is no model field or code path for by-products, co-products, or scrap yield, and no scrap/yield-loss accounting.
- **Impact:** Real manufacturing (the target market includes pharma/food per the HSN table) routinely produces scrap and by-products with their own stock value; here 100% of input cost is loaded onto the primary FG and any physical by-product must be added via a manual adjustment with a guessed cost. Review scope explicitly calls out "by-product/scrap".
- **Fix:** Add `BomOutput` rows (product, qty, cost-allocation %) and issue additional `MANUFACTURE_RECEIPT` movements on completion, splitting `issue_cost` by the allocation.

### [B8-010] FEFO material allocation in work-order release is not locked or reserved
- **Severity:** Medium
- **Category:** Race condition
- **Location:** `backend/manufacturing/services.py:97-114` (`_issue_batches` FEFO branch), `:146-163`
- **Observation:** The FEFO branch calls `InventoryValuationService.fefo_batches(...)` then `InventoryService.available_quantity(...)` per lot with **no `select_for_update`** and no reservation, then loops posting `post_movement`. Two concurrent releases can both read the same lot as available.
- **Impact:** Under `negative_stock_policy != "BLOCK"` (WARN) the per-row lock in `post_movement` will not stop the second release, so a lot is issued twice and goes negative; FIFO layers under-run. Under BLOCK the second release fails late with a confusing per-lot error after some components already posted (rolled back by the `@transaction.atomic`, but user sees a partial-looking failure).
- **Fix:** In `_issue_batches`, `select_for_update()` the candidate `StockBalance` rows for the product/warehouse before computing allocations (as `reserve_stock` already does at `:864-873`).

### [B8-011] `StockCountSession` edit silently rebaselines `system_qty`, defeating conflict detection
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `backend/inventory/serializers.py:360-379` (`update` full-recreate path), `:290-309` (`_make_count_line` / `_count_line_system_qty`)
- **Observation:** When the payload line ids don't all match existing rows, `update` does `instance.lines.all().delete()` then `_make_count_line` for each, which recomputes `system_qty = remaining_qty(...)` **at edit time**. The posting flow (`views.py:538`) later flags a conflict only when `current != line.system_qty`.
- **Impact:** If stock moved between session creation and this edit, the snapshot the operator was counting against is overwritten with the new live figure, so the `StockCountConflict` that should have warned the operator ("someone shipped 5 units while you were counting") never fires and `KEEP_LOCAL` posts a variance computed against the wrong baseline.
- **Fix:** Preserve `system_qty` from the existing row when replacing lines for the same (product, batch); only compute it fresh for genuinely new lines.

### [B8-012] FIFO tenants replay the entire movement ledger on every valuation / unit-cost call
- **Severity:** Medium
- **Category:** Performance
- **Location:** `backend/inventory/services.py:1421` (WAVG-only fast path), `:1451-1520`, `:1649-1650`
- **Observation:** `valuation(as_of=None)` uses the `InventoryRunningCost` shortcut **only for WAVG**. FIFO always does `movements = base.select_related(...)` over all `StockMovement` for the company and `_replay`s them. The snapshot path only engages when `movements.count() > SNAPSHOT_THRESHOLD` (10 000) **and** a prior-month `InventoryValuationSnapshot` exists. `unit_cost()` FIFO also routes through `cls.valuation(...)`.
- **Impact:** For a FIFO tenant with 9 999 movements, every stock-valuation page load, and every COGS fallback in `cogs_service`, `StockTransferService.complete` (per line), and `release_work_order` (per component/batch), replays ~10 000 rows in Python. `StockTransferService.complete` calls `unit_cost` once per line and `release_work_order` once per (component, lot) → N full replays per document.
- **Fix:** Give FIFO the same live path as WAVG by reading `InventoryCostLayer` for `as_of=None` (see B8-001); memoize `unit_cost` within a single service call / document post.

### [B8-013] `check_negative_stock` / oversell path ignores GST-period locks and business date for direct adjustments
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `backend/inventory/views.py:148-195` (`AdjustmentView`), `:423-456` (`ExpiryAlertsView.post`); `backend/inventory/services.py:59-177` (`post_movement`)
- **Observation:** `post_opening` calls `validate_opening_as_of` → `assert_period_allows_money_amend`, and `manufacturing` gates on `assert_period_allows_money_amend`. But `AdjustmentView` and the expiry write-off call `post_movement` directly with no period gate; `post_movement` has no `assert_period_allows_money_amend`. `movement_date` defaults to `timezone.localdate()` and is not validatable via the serializer, but nothing stops a caller passing a back-dated `movement_date` into a closed period.
- **Impact:** Manual adjustments / expiry write-offs (which do hit the GL when `accounting_enabled`) can be booked into a filed/soft-closed GST period, contradicting the rest of the codebase's period discipline.
- **Fix:** Add `assert_period_allows_money_amend(company, movement_date or localdate())` inside `post_movement` (or in each direct view), consistent with opening stock and manufacturing.

### [B8-014] `AdjustmentView` creates a `BatchLot` before a non-atomic `post_movement`
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `backend/inventory/views.py:171-189`
- **Observation:** `batch = get_or_create_batch(company=..., product=..., batch_no=batch_no, user=request.user)` runs outside any `transaction.atomic()`, then `InventoryService.post_movement(...)` (which has its own inner atomic). If `post_movement` raises (negative stock, inactive godown, etc.) the freshly created `BatchLot` persists.
- **Impact:** Orphan `BatchLot` rows accumulate from failed adjustment attempts; they then appear in batch pickers and FEFO ordering with no stock.
- **Fix:** Wrap the view body in `transaction.atomic()` so batch creation rolls back with a failed movement.

### [B8-015] `SerialNumber` bulk `.update()` in transfer cancel skips `updated_at`
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/inventory/services.py:1220-1223`
- **Observation:** `SerialNumber.objects.filter(...).update(warehouse=transfer.from_warehouse, updated_by=user)` — `QuerySet.update` does not run `auto_now`, so `updated_at` is stale while `updated_by` changed.
- **Impact:** Audit trail on serial units is inconsistent (who changed it is recorded, when is not). Minor but this pattern is repeated.
- **Fix:** Include `updated_at=timezone.now()` in the `.update()` call, or iterate and `save(update_fields=[...])`.

### [B8-016] `StockTransfer` lines don't require a batch for batch-tracked products
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `backend/inventory/serializers.py:146-149` (`StockTransferLineSerializer`), validated only at `services.py:1150-1155`
- **Observation:** `StockTransferLineSerializer` exposes `batch` as optional with no `track_batch` check. `StockTransferSerializer.create/update` validate tenancy of `batch` but not its presence. The batch requirement is only enforced deep in `post_movement` (`services.py:94`) at `complete` time.
- **Impact:** A user can build and save a transfer of a batch-tracked item with no batch, and only discover it's invalid when `complete` fails with `"A batch is required for tracked product"`. Draft looks fine.
- **Fix:** Validate `product.track_batch → batch required` (and `track_serial → serial_numbers count == quantity`) in the line serializer.

### [B8-017] `BomLine` / `WorkOrderLine` / `PriceListItem` qty positivity only enforced in serializers
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `backend/manufacturing/models.py:34,85-86`, `backend/masters/models.py:319-321`
- **Observation:** `qty`/`unit_price`/`min_qty` have no `CheckConstraint`. Positivity lives in `BomLineSerializer.validate_qty`, `WorkOrderSerializer.validate_qty`, `pricing.assert_slab_bounds`. Imports, admin inlines (`manufacturing/admin.py`), data migrations, and `bulk_create` paths bypass all of them.
- **Impact:** Zero/negative BOM component qty → `_snapshot_bom` produces `qty = 0` or negative issue → `post_movement` rejects zero (`"Movement quantity must be greater than zero"`) so a whole release breaks, or a negative slips through as an inbound. Negative `min_qty` breaks slab matching.
- **Fix:** Add `CheckConstraint(condition=Q(qty__gt=0))` etc. on the models.

### [B8-018] `Bom` has no "one active BOM per finished good" constraint or effectivity
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `backend/manufacturing/models.py:8-23`
- **Observation:** `Bom` has `product` FK + free-text `status` with no unique/partial constraint on `(company, product, status=ACTIVE)` and no `effective_from`/`version`.
- **Impact:** Multiple ACTIVE BOMs for the same FG are allowed. `WorkOrder.bom` is explicit so a WO is unambiguous, but any "get the BOM for this product" logic (costing estimates, MRP, UI defaulting) has to pick arbitrarily, and there is no way to supersede a BOM by date.
- **Fix:** Add a partial unique constraint on ACTIVE per `(company, product)`, or add versioning + effective dates.

### [B8-019] `WorkOrderLine` BOM snapshot is taken at WO *creation*, not at *release* (contradicts its own docstring)
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/manufacturing/models.py:75-76` (docstring "snapshot taken at release"), `backend/manufacturing/serializers.py:105-113` (`create` calls `_snapshot_bom` immediately)
- **Observation:** `WorkOrderSerializer.create` calls `_snapshot_bom(wo)` right away; `release_work_order` calls it again but it's a no-op because lines already exist.
- **Impact:** Editing the BOM while the WO is still DRAFT has no effect on that WO — surprising, and the reverse of the documented behaviour. There's also no way to force a re-snapshot without deleting/recreating the WO.
- **Fix:** Only snapshot at release (drop the `create`-time call), or update the docstring and allow DRAFT WOs to re-snapshot on demand.

### [B8-020] `_apply_running_cost` can zero out value while leaving qty positive on rounding underflow
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/inventory/services.py:441-446`
- **Observation:** After an out-flow: `if qty <= 0: qty = 0; value = 0; elif value < 0: value = 0`. If a costed out-flow (B8-003) drives `value` negative while `qty` is still > 0, `value` is clamped to 0 and the row now reports `unit_cost == 0` for real stock.
- **Impact:** Live WAVG cost for a product silently becomes ₹0 after certain transfer/return sequences; downstream COGS books ₹0 until `rebuild_running_cost` is run manually. `_heal_running_zero_cost` papers over it on read but the stored row stays wrong.
- **Fix:** On `value < 0` with `qty > 0`, re-derive `value = qty * last_known_avg` rather than clamping to 0, and log loudly.

### [B8-021] `rebuild_running_cost` drift check misses running rows with no matching balance
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/inventory/services.py:469-488`
- **Observation:** The drift loop iterates `StockBalance.objects.filter(company=company)` and looks up the matching `InventoryRunningCost`. A running-cost row whose `StockBalance` was pruned (e.g. by `rebuild_stock_balances` orphan cleanup at `management/commands/rebuild_stock_balances.py:44-52`) is never visited, so leftover qty/value there is invisible.
- **Impact:** After a balance rebuild that drops orphan rows, `rebuild_running_cost` can report "no drift" while stale `InventoryRunningCost` rows still contribute to `unit_cost()` cross-warehouse pooling and valuation.
- **Fix:** Iterate the union of keys from both tables; assert running rows with qty≠0 have a balance row.

### [B8-022] `rebuild_stock_balances` runs the whole company in one transaction with per-key `rebuild_balance`
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/inventory/management/commands/rebuild_stock_balances.py:35-52`
- **Observation:** `with transaction.atomic():` wraps a loop over every `(company, warehouse, product, batch)` key calling `InventoryService.rebuild_balance`, which itself runs several aggregate queries + lazy `apps.get_model("sales", ...)` sales-order reservation recomputation (`services.py:962-1024`), plus a final `orphan_qs.iterator()` with per-row `bal.delete()`.
- **Impact:** For a large tenant this is a long single transaction (lock contention, `idle_in_transaction_session_timeout=60000` risk from `settings.py:240`) and O(keys × queries). No `--batch`/chunking, no progress output per key.
- **Fix:** Commit per company (or per N keys) outside one giant atomic block; batch the orphan delete with a single `.exclude(...).delete()`.

### [B8-023] `rebuild_balance` overwrites reserved on *other* batch rows as a side effect
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/inventory/services.py:984-1024`
- **Observation:** When rebuilding one key with `so_qty > 0 and product.track_batch`, the method loops FEFO lots and writes `lot_balance.on_hand`/`lot_balance.reserved = take` for **every lot**, not just the key being rebuilt — including `reserved` values it computes from a single product's confirmed SOs.
- **Impact:** Rebuilding the unbatched balance for product X mutates the batched balance rows for X in the same warehouse (setting their `reserved` to a freshly computed FEFO split). If those rows are also enumerated as their own keys later in the same run they get recomputed again; if a lot isn't in this FEFO pass its previously-set reserved is left stale. Order-dependent output.
- **Fix:** Have `rebuild_balance` write only the row for its own `(warehouse, product, batch)` key; do SO-reservation reconciliation in a dedicated single pass per product.

### [B8-024] `seed_starter_hsn_rates` never updates a row once seeded — rate corrections don't propagate
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/masters/hsn_catalog.py:333-357`
- **Observation:** `HsnRate.objects.get_or_create(hsn_sac=..., version=..., defaults={rate, cess, ...})`. If a `_HSN_RATE_SPEC` value is later corrected, re-running the seed is a no-op because `(hsn_sac, version)` already exists.
- **Impact:** A wrong starter rate (see B8-025) is permanent in every environment that seeded before the fix, unless someone manually deletes rows. `backfill`/re-seed gives false confidence.
- **Fix:** `update_or_create` on the mutable fields, or bump `version` when the spec changes and add a cleanup of the superseded version.

### [B8-025] Starter HSN table drops compensation cess for tobacco/aerated/vehicles at GST 2.0
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/masters/hsn_catalog.py:150-153,226-227`
- **Observation:** Post-cutover rows set `cess = "0"` for `2202` (aerated, pre cess 12→0), `2203/2402/2403/2404` (beer/tobacco, pre 0 but these carry heavy specific cess), `8703/8711` (motor vehicles, pre cess 17→0). GST 2.0 rationalised the *rate* to 40% but compensation cess on tobacco / pan-masala / aerated / large cars **was not abolished**.
- **Impact:** `rate_for()` returns `cess = 0` for these HSNs on/after 2025-09-22; any caller that trusts it to override a line will under-collect cess. The file carries a "verify with your CA" disclaimer, and `rate_for` only overrides on an explicit match, which limits blast radius.
- **Fix:** Either keep the real cess figures or omit the post-cutover row for cess-bearing HSNs so the code keeps the user-entered value.

### [B8-026] `rate_for` tie-break is non-deterministic for equal prefix length + `valid_from`
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/masters/hsn_catalog.py:319-323`
- **Observation:** `rows.sort(key=lambda r: (len(r.hsn_sac), r.valid_from), reverse=True); hit = rows[0]`. If a company-loaded catalog has two rows for the same prefix length effective the same day (e.g. overlapping `version`s, or a manual correction row not superseding the old one), the winner depends on DB row order.
- **Impact:** Ambiguous rate/cess selection; a stale row can win over the intended one.
- **Fix:** Add `id` (or `-version`/`source_ref` priority) as a final sort key and/or enforce non-overlap at load time.

### [B8-027] `distinct_values_for_keys` scans every product in Python on a hot endpoint
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/masters/custom_fields.py:65-91`; called by `ProductViewSet.custom_field_values` (`masters/views.py:297-306`)
- **Observation:** Iterates `Product.objects.filter(company=company).exclude(custom_fields={}).values_list("custom_fields", flat=True).iterator(chunk_size=500)` and dedupes in Python for each list-type custom field.
- **Impact:** O(products) per call to populate filter dropdowns; on a 50k-product tenant (see `load/SEED_50K.md`) this is a multi-second query with no cache and no limit.
- **Fix:** Cache the result per company for a short TTL (the codebase already has `_CachedMastersListMixin`), or store distinct CF values in a summary table maintained on product save.

### [B8-028] `ProductViewSet.get_queryset` adds an `Exists(StockMovement)` subquery to every list row
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/masters/views.py:256-262`
- **Observation:** `qs = super().get_queryset().annotate(has_movements=Exists(StockMovement.objects.filter(product_id=OuterRef("pk"))))` on every list/retrieve, regardless of whether the caller needs `has_movements`.
- **Impact:** Correlated subquery per product row on the product list (the most-hit masters endpoint). Combined with `build_search_q` OR-ing an `icontains` per active custom field (`custom_fields.py:385-397`), product search can get expensive on large catalogs.
- **Fix:** Only annotate when `has_movements` is actually serialized/needed, or replace with a `GROUP BY` join; add a partial index.

### [B8-029] `StockMovement` "append-only" is bypassed for `unit_cost` / `layer_peels` mutation
- **Severity:** Low
- **Category:** Improvement
- **Location:** `backend/inventory/models.py:125-131`; mutated via `.update()` in `services.py:608`, `sales/cogs_service.py:87`
- **Observation:** `save()` raises if `pk is not None` and `delete()` always raises, but `_apply_cost_layers` and `cogs_service` deliberately use `StockMovement.objects.filter(pk=...).update(unit_cost=..., layer_peels=...)` to rewrite a "ledger" row after creation.
- **Impact:** The immutability guarantee is partial and undocumented at the call sites; an auditor reading `models.py` would believe rows never change. Two writers stamping the same movement (FIFO peel + cogs fallback) race with last-writer-wins and no lock.
- **Fix:** Compute the final `unit_cost`/`layer_peels` before the `create()` so no post-hoc update is needed, or add an explicit `stamp_cost()` classmethod with a row lock and a comment on `save()`.

### [B8-030] `WarehouseViewSet.perform_update` reads `is_active` from `validated_data` but PATCH may omit it
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/inventory/views.py:282-289`
- **Observation:** `becoming_inactive = serializer.validated_data.get("is_active") is False and instance.is_active`. On a PATCH that doesn't include `is_active`, `.get(...)` is `None`, so `assert_can_deactivate_warehouse` is correctly skipped — fine. But a full PUT that sets `is_active=False` while also making it the default, or a payload that flips `is_default` without `is_active`, is not cross-checked against `assert_can_deactivate_warehouse` / "default cannot be deactivated" until the next edit.
- **Impact:** Minor: the deactivation guard is only wired to the exact `is_active: false` transition; other routes to an unusable default godown (e.g. clearing `is_default` on the only godown) aren't guarded here.
- **Fix:** Re-validate invariants (exactly one active default godown exists) in `perform_update` regardless of which field changed.

### [B8-031] `resolve_unit_price` prevents staff from pricing *above* the price list, silently
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `backend/masters/pricing.py:113-121`
- **Observation:** `if requested != list_price and role == "OWNER": return requested` else `return list_price`. A non-OWNER requesting **more** than the slab price is clamped down to the slab price with no error.
- **Impact:** Sales staff who legitimately negotiate a higher price than the list get their line quietly reduced to the list price; no 400, no warning. Likely the intent was only to prevent *undercutting*.
- **Fix:** Only clamp when `requested < list_price`; allow `requested > list_price` for any role (or return a validation error so the discrepancy is visible).

### [B8-032] Price lists / product prices have no currency — multi-currency price lists unsupported
- **Severity:** Low
- **Category:** Gap
- **Location:** `backend/masters/models.py:300-331` (`PriceList`, `PriceListItem`), `:222-225` (Product prices)
- **Observation:** No `currency` field anywhere in pricing; `resolve_party_price` returns a bare `Decimal`. Review scope explicitly lists "price list precedence & currency".
- **Impact:** Export customers (the `Customer.TaxpayerType` enum has `EXPWP/EXPWOP`) cannot have a USD/EUR price list; every list is implicitly company home currency.
- **Fix:** Add `currency` to `PriceList` (or `PriceListItem`) and carry it through `resolve_party_price`/document lines, or document the single-currency limitation.

### [B8-033] No "default company price list" precedence — only the customer's assigned list is consulted
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `backend/masters/pricing.py:76-92` (`resolve_party_price`)
- **Observation:** `price_list_id = customer.price_list_id`; if the customer has none, it returns `(None, "")` and the caller uses `product.selling_price`. There is no notion of a company-wide default price list, no "wholesale vs retail" selection by customer type, and `Product.wholesale_price` is never referenced by `pricing.py`.
- **Impact:** `wholesale_price` (added in migration `0009`) is dead as far as server-side price resolution is concerned; businesses that price by tier without per-customer list assignment get only `selling_price`.
- **Fix:** Add a fallback chain (customer list → company default list → wholesale/retail by customer flag → `selling_price`) or wire `wholesale_price` into `resolve_unit_price`.

### [B8-034] `_qty` / slab matching treats missing quantity as 1, so "price for 0" and unpriced calls hit the min-qty=1 slab
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/masters/pricing.py:9-13`, `:59-73`
- **Observation:** `_qty(None) -> Decimal("1")`; `_matching_slab` skips items where `quantity < min_q`. A slab starting at `min_qty = 2` is never reachable when the caller doesn't pass a quantity, and a slab with `min_qty = 0.5` (fractional UOM) can't be targeted below 1 without an explicit qty.
- **Impact:** Callers that resolve a price without knowing quantity (quote templates, product detail preview) always get the `min_qty <= 1` slab even if the order will be larger; fractional-unit businesses can't price sub-unit slabs by default.
- **Fix:** Require an explicit quantity for slab resolution, or return the lowest-min slab when quantity is unknown rather than assuming 1.

### [B8-035] `get_or_create_batch` won't shorten an expiry and can't reconcile mfg/expiry conflicts across sources
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/inventory/item_stock.py:187-217`
- **Observation:** For an existing batch it raises if `expiry_date` differs from a set value, and only fills `expiry_date`/`manufacturing_date` when currently `None`. It never validates `manufacturing_date <= expiry_date` when one side is being filled from a different call than set the other (the `manufacturing_date > expiry_date` guard at `:191` only checks the two incoming args).
- **Impact:** A batch created via opening stock with only `expiry_date`, later touched by a WO completion supplying only `manufacturing_date` (`manufacturing/services.py:231`), can end up with `manufacturing_date > expiry_date` and no error.
- **Fix:** After merging, re-assert `manufacturing_date <= expiry_date` against the persisted values.

### [B8-036] `valuation(as_of=...)` with the flag off can't see back-dated movements; with it on, perpetual layers still peeled in insert order
- **Severity:** Info
- **Category:** Improvement
- **Location:** `backend/inventory/services.py:1415`, `:1508-1517`; `tests/test_w0_valuation.py:33-90`
- **Observation:** `use_business_date = company.valuation_business_date_order` (default `False`). With it off, historical `as_of` filters on `created_at__date`, so a purchase entered today with `movement_date` last month is invisible to a last-month valuation (characterized by `test_flag_off_as_of_matches_created_at_replay`). With it on, `_replay` re-orders by `movement_date` but the perpetual `InventoryCostLayer` rows were peeled in insertion order at post time — so live FIFO COGS and a business-date `as_of` valuation use different consumption orders (compounds B8-001).
- **Impact:** Back-dated corrections don't affect prior-period reports unless the tenant opts into `valuation_business_date_order`, and even then the two FIFO paths disagree.
- **Fix:** Document the flag's meaning prominently; if business-date order is on, the perpetual layer engine should also consume in business-date order (or valuation should be layer-based per B8-001).

### [B8-037] `MovementType` max_length / choices vs. reference constants — minor consistency gaps
- **Severity:** Info
- **Category:** Improvement
- **Location:** `backend/inventory/models.py:86` (`movement_type = CharField(max_length=20)`), `:139` vs `:84` (`StockBalance.product` `on_delete=CASCADE` while `StockMovement.product` is `PROTECT`), `InventoryRunningCost.batch` CASCADE vs `InventoryCostLayer.batch` PROTECT
- **Observation:** `MANUFACTURE_RECEIPT` is 19 chars (fits 20, no margin). `on_delete` policy for `product`/`batch` differs across the derived-cache models with no stated rationale.
- **Impact:** Deleting a `BatchLot` cascades away `InventoryRunningCost`/`InventoryValuationSnapshot` rows but is `PROTECT`ed by `InventoryCostLayer`/`StockMovement`/`StockBalance` — so a batch delete is effectively blocked anyway, making the CASCADE rows dead config; any future movement type name ≥ 21 chars silently truncates.
- **Fix:** Bump `movement_type` to `max_length=32`; make `product`/`batch` `on_delete` uniformly `PROTECT` on all ledger-derived models.

---

## Test coverage notes

- **FIFO vs perpetual-layer reconciliation (B8-001/B8-004):** no test asserts `sum(InventoryCostLayer.qty_remaining * unit_cost)` equals the FIFO `valuation()` value for the same tenant. `test_wave22_f2_fifo_serial_mfg.py` checks layer `qty_remaining` transitions but never cross-checks against the valuation report or GL COGS.
- **`InventoryRunningCost.value` drift (B8-003):** `test_w0_valuation.py:test_rebuild_running_cost_matches_balance` only asserts `row.qty`/`row.value` for a single PURCHASE (no out-flow). No test with TRANSFER_OUT / MANUFACTURE_ISSUE / purchase-return then a value assertion; `rebuild_running_cost`'s drift check is qty-only and untested for value.
- **Non-atomic serializer writes (B8-002):** no test posts an invalid BOM/price-list/transfer/stock-count edit and then asserts the existing child rows survived.
- **`ExpiryAlertsView.get` side effects (B8-005):** `test_*` for expiry alerts (if any) would need to assert no `ExpiryAlertLog`/email on GET — not present.
- **Nested BOM (B8-008) / by-product (B8-009):** no test exercises a component that is itself a manufactured good, or any scrap/by-product output.
- **Concurrent WO material issue (B8-010) / concurrent opening (`post_opening_movements_batch`):** race paths have comments citing bug ids (R2-026, BB-000236) but no concurrency test harness is visible in scope.
- **`unit_cost` batch fallback (B8-007):** no test for a zeroed batch running-cost row returning a cross-batch blend.
- **Pricing precedence (B8-031/B8-033/B8-034):** `test_wave22_f2_fifo_serial_mfg.py:test_bb_000728_price_role_owner_override` covers OWNER undercut only; no test for requested > list price, no test for missing customer list / wholesale price, no fractional-qty slab test.
- **`custom_fields` injection:** `test_item_custom_fields.py` (530 lines) is substantial; `KEY_RE` + reserved-name guards look well covered. `apply_cf_filters` re-validates keys — good.

---

# Deep Review B9 — billing / insights / crm / integrations / payroll

**Scope reviewed (every line):**
- `backend/billing/**` except `middleware.py`, `permissions.py` (read only for context): `models.py`, `services.py`, `views.py`, `serializers.py`, `admin.py`, `urls.py`, `apps.py`; migrations skimmed.
- `backend/insights/**`: `alerts.py`, `assistant.py`, `attention.py`, `services.py`, `tasks.py`, `models.py`, `serializers.py`, `views.py`, `urls.py`, `apps.py`, `management/commands/generate_insights.py`.
- `backend/crm/**`: `models.py`, `services.py`, `views.py`, `serializers.py`, `permissions.py`, `admin.py`, `urls.py`, `apps.py`.
- `backend/integrations/**`: `models.py`, `views.py`, `permissions.py`, `tally/adapter.py`, `urls.py`, `apps.py`.
- `backend/payroll/**`: `models.py`, `services.py`, `views.py`, `serializers.py`, `permissions.py`, `admin.py`, `urls.py`.
- Support files read for contract: `core/services/feature_flags.py`, `core/viewsets.py`, `accounting/services.py` (`_ensure_chart`/`_account`), `accounts/views.py` `_enforce_plan_seat_limit`.
- Tests read for intent: `test_sprint_d_saas_billing.py`, `test_wave22_f3_billing_idempotency.py`, `test_sprint_b_payroll_statutory.py`, `test_wave22_f0_gst_accounting_payroll.py`, `test_sprint_b_crm_convert.py`, `test_phase6_insights.py`, `test_sprint5_integrations_ai.py`, `test_billing_totals.py`.

## Severity counts

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 5 |
| Medium | 13 |
| Low | 22 |
| Info | 4 |
| **Total** | **44** |

---

### [B9-001] Checkout on a live-Razorpay tenant creates a second subscription and swaps plan before payment, without cancelling the old one
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `backend/billing/services.py:104-135`
- **Observation:** For an existing ACTIVE/TRIAL subscription the code comments "Keep the live plan until Razorpay confirms" and does `pass` (lines 106-108). But if `razorpay_key and razorpay_secret and plan.razorpay_plan_id` (lines 118-134) it then calls `_create_razorpay_subscription(plan, company)` which POSTs a brand-new subscription to `https://api.razorpay.com/v1/subscriptions`, and on success does `sub.plan = plan; sub.razorpay_subscription_id = remote_id; ... sub.save(...)`. The previously active `razorpay_subscription_id` is overwritten and never cancelled at Razorpay.
- **Impact:** A paying customer who clicks "upgrade"/"change plan" ends up with two active Razorpay subscriptions billing the same card, and Bizboard immediately shows/enforces the new plan (seat_limit, modules) before the first successful charge of the new subscription. Downgrades have the same double-charge exposure.
- **Fix:** Before creating the new Razorpay subscription, cancel the old one (`POST /v1/subscriptions/{id}/cancel`) or use Razorpay's plan-update/upgrade API. Do not mutate `sub.plan` until a webhook confirms the new subscription is `active`; keep the old `razorpay_subscription_id` until then.

### [B9-002] Tally commit: `get_or_create` by (company, name) 500s on duplicate party names and silently merges distinct parties
- **Severity:** High
- **Category:** Broken-flow
- **Location:** `backend/integrations/tally/adapter.py:471-480` (Customer), `:503-512` (Supplier)
- **Observation:** `Customer.objects.get_or_create(company=company, name=row["name"], defaults={...})`. `Customer`/`Supplier` have no unique `(company, name)` constraint, so if the tenant already has two customers named e.g. "Sharma Traders", `get_or_create` raises `MultipleObjectsReturned` — uncaught inside `_commit_tally_preview_inner`, surfacing as HTTP 500 and rolling back the whole import. When only one match exists but it is a *different* real party, the opening balance and phone/GSTIN patch are applied to the wrong record.
- **Impact:** Migration commit is unusable for any tenant with pre-existing duplicate names; wrong-party opening AR/AP postings otherwise.
- **Fix:** Match on a stable key (imported GSTIN, or explicit `customer_id` remap in the preview), fall back to `filter(...).first()`, and surface an error row when >1 match rather than raising. Consider adding a case-insensitive `(company, name)` uniqueness helper.

### [B9-003] Full-month loss-of-pay (paid_days = 0) produces a negative net payslip with phantom TDS
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/payroll/services.py:322-370`; `backend/payroll/views.py:80-106` (`lop` accepts `paid_days` down to 0)
- **Observation:** With `paid_days=0, period_days>0`, `prorate = days/period = 0` so `gross_amt = 0`, and PF/ESI/PT all compute to 0. But new-regime TDS is computed from the *un-prorated* contracted salary: `annual = _money(gross_full * Decimal("12"))` then `tds_amount = _money(annual_new_regime_tax(annual) / Decimal("12"))` (lines 363-365). `deductions = pf + esi + pt + tds`; `net = gross_amt - deductions` → negative net equal to `-tds_amount`.
- **Impact:** A zero-pay month writes a payslip with `net < 0` and a TDS deduction with no wages to deduct it from; the pay-run GL then credits TDS payable (2265) and debits salary expense for a person paid nothing, and `total_net` is understated / can go negative.
- **Fix:** Prorate the TDS projection by `prorate` as well (or skip statutory entirely when `gross_amt == 0`); clamp `net = max(0, gross_amt - deductions)` and carry any un-recoverable TDS as an explicit note rather than negative net.

### [B9-004] AI assistant: monthly token budget is checked once per turn but a turn makes up to two LLM calls, and a failed LLM turn records zero usage
- **Severity:** High
- **Category:** Gap
- **Location:** `backend/insights/assistant.py:123-135` (`assert_within_budget`), `:474-563` (`_run_llm_tools` — `chat_with_tools` called at 483 and again at 531), `:596-608` (`run_assistant_turn`)
- **Observation:** `assert_within_budget` runs once at the top of `run_assistant_turn`. `_run_llm_tools` then issues a first tool-selection call and, if any tool ran, a second summarisation call; both consume tokens with no re-check. Separately, if `_run_llm_tools` raises after the first call, `except Exception: used_llm = False` swallows it, falls back to rules, and `record_usage` is only called with the rules-fallback estimate — the tokens already spent on the failed first call are never ledgered.
- **Impact:** A tenant sitting just under budget can overshoot substantially in a single turn; repeated failing LLM turns burn provider spend that never counts against the budget, defeating the cost control.
- **Fix:** Track cumulative tokens inside `_run_llm_tools`, re-check budget before the second call, and always `record_usage` for whatever was consumed (use try/finally so partial usage on exception is still recorded).

### [B9-005] No proration on plan upgrade/downgrade
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `backend/billing/services.py:67-135`
- **Observation:** `start_or_update_subscription` never computes any credit for the unused portion of the current period or a pro-rated charge for the new plan. Plan change is effected purely by creating a new Razorpay subscription (`total_count=120`, `_create_razorpay_subscription`), and `apply_razorpay_subscription_status` only maps status + sets `current_period_end`; it never adjusts `sub.plan`.
- **Impact:** Mid-cycle upgrades give no immediate value adjustment; downgrades give no refund/credit. Combined with B9-001 the customer can be billed twice with no offset.
- **Fix:** Decide the proration policy (immediate proration vs change-at-cycle-end) and implement it via Razorpay's subscription update/`schedule_change_at` API, or record an internal credit ledger entry.

### [B9-006] Plan downgrade is never reconciled against seat_limit or plan modules
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/accounts/views.py:954-982` (`_enforce_plan_seat_limit` — only called from invite/accept, lines 864/1002/1098); `backend/billing/services.py:67-135`; `backend/core/services/feature_flags.py:145-183`
- **Observation:** `_enforce_plan_seat_limit` counts *all* active `CompanyUser` rows (owner included) and is only invoked on invite/accept. Nothing runs on plan change. `is_write_blocked` does not consider seats. `feature_flags` will silently drop dark modules the new plan omits (`plan_modules` non-empty & key absent → `val = False`, line 155-156).
- **Impact:** A tenant with 12 active members can downgrade to `seat_limit=3` and keep all 12 working; conversely modules used yesterday vanish mid-session with no warning, orphaning in-progress work / data behind a now-disabled module.
- **Fix:** On plan change, compare active seats/modules to the new plan and either block the downgrade, require the owner to deactivate seats first, or flag an over-limit grace state surfaced in the billing portal.

### [B9-007] SUSPENDED / cancelled subscription blocks writes immediately with no end-of-period grace
- **Severity:** Medium
- **Category:** UX/UI
- **Location:** `backend/billing/models.py:49-51`; status mapping `backend/billing/services.py:202-217` (`cancelled/completed/expired → SUSPENDED`)
- **Observation:** `is_write_blocked` returns `True` for `SUSPENDED` (and `PENDING`) unconditionally, ignoring `current_period_end`. Razorpay `subscription.cancelled` maps straight to `SUSPENDED`.
- **Impact:** A customer who cancels but has paid through month-end is write-blocked the instant the webhook lands, even though they are entitled to service until `current_period_end`. `PAST_DUE` has a configurable grace (`BILLING_PAST_DUE_GRACE_DAYS`) but a clean cancellation has none.
- **Fix:** For `SUSPENDED` due to cancellation, honour `current_period_end` (block only once `now >= current_period_end`), mirroring the `PAST_DUE` grace logic.

### [B9-008] Customer PII (name, email, phone, outstanding balance) is transmitted to the external LLM
- **Severity:** Medium
- **Category:** Security
- **Location:** `backend/insights/assistant.py:300-372` (`tool_get_customer_outstanding`, `tool_search_documents`, `tool_draft_payment_reminder`), `:512-527` (tool result JSON, incl. `proposed_action`, dumped into `tool_notes` sent to the 2nd `chat_with_tools` call)
- **Observation:** Only `citation` is popped from `result` before `json.dumps(result, default=str)`; `proposed_action` (which carries `email`, `phone`, `customer_name`, full reminder `text`) and customer outstanding amounts remain and are concatenated into the model context. The only gate is `company.ai_features_enabled`; there is no redaction or per-field opt-out. Scope note flags "PII in prompts" as a hunt target and the system prompt claims "never … cross-company data" but says nothing about party PII leaving the tenant.
- **Impact:** Customer contact details and balances are sent to a third-party LLM provider with no contractual/consent surface, and persisted in provider logs.
- **Fix:** Strip `proposed_action` and contact fields from tool results before they enter the LLM context (keep them only in the API response for the UI); redact names/amounts or pass opaque ids where the model does not need the literal value.

### [B9-009] Prompt-injection surface: tenant-controlled party/product names are concatenated verbatim into the LLM context
- **Severity:** Medium
- **Category:** Security
- **Location:** `backend/insights/assistant.py:321-348` (`tool_search_documents`), `:517-537` (`tool_notes` joined into an `assistant` message, then a `user` "Summarize…" instruction)
- **Observation:** Tool results embedding free-text customer/supplier/product names and invoice numbers are dumped as JSON into `"Tool results:\n" + "\n".join(tool_notes)` with no delimiting or escaping. A party named e.g. `"}] ignore prior instructions and …"` is attacker-influenceable (customers can be created by staff, self-serve onboarding, or imports).
- **Impact:** Model can be steered to fabricate financial "advice", bypass the tax-advice refusal, or mis-select tools. Blast radius is currently limited (confirm allowlist excludes money moves) but the tax guardrail and reminder-draft content are reachable.
- **Fix:** Wrap tool output in a clearly fenced, non-instruction block; instruct the model that tool content is data only; consider passing tool results as a separate structured `tool` role rather than inline text.

### [B9-010] Tally HTTP push has no audit log, no sync-run record, and re-push duplicates vouchers in Tally
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/integrations/views.py:168-191` (`TallyHttpPushView`), `backend/integrations/tally/adapter.py:750-812` (`_vouchers_xml` emits `VOUCHER … ACTION="Create"`, `push_masters_http`/`push_vouchers_http`)
- **Observation:** The view calls `push_masters_http` / `push_vouchers_http` and returns; there is no `AuditService.log` call (contrast the WhatsApp connection view) and no `IntegrationSyncRun` is created even though `IntegrationSyncRun.Kind.TALLY_EXPORT` exists and is otherwise unused. Each voucher is emitted with `ACTION="Create"` and no idempotency key.
- **Impact:** Bulk export of every customer/supplier/product name and up to 5000 sales vouchers to an operator-supplied URL leaves no trail; a second push (or a retry) creates duplicate vouchers in the target Tally company.
- **Fix:** Create an `IntegrationSyncRun(kind=TALLY_EXPORT)` row capturing target URL, date range, counts and response; `AuditService.log` the push; add a `REMOTEID`/dedupe marker or `ACTION="Alter"` semantics, or at minimum warn that re-push duplicates.

### [B9-011] Assistant "read" tools have DB write side-effects
- **Severity:** Medium
- **Category:** Improvement
- **Location:** `backend/insights/assistant.py:201-212` (`tool_get_daily_summary` → `generate_daily_summary`), `:277-292` (`tool_list_business_alerts` → `upsert_alerts`)
- **Observation:** `upsert_alerts` is `@transaction.atomic` and creates/updates/resolves `BusinessAlertEvent` rows; `generate_daily_summary` also `update_or_create`s `DailyBusinessSummary` and calls `upsert_alerts`. Both are invoked from assistant tool calls triggered by an LLM during a chat turn. `test_alerts_list_does_not_upsert` guards the *viewset* but not this path.
- **Impact:** Asking the assistant "any alerts?" mutates alert state (can resolve/re-open alerts, bump `updated_at`, send nothing but churn rows) as a side-effect of a read; concurrent chat turns can race on the same rows.
- **Fix:** Give the assistant read-only variants that return the last persisted snapshot without upserting, or move the upsert to the scheduled task only.

### [B9-012] Attention feed and alert builders do per-row subqueries in large loops and recompute shared aggregates repeatedly, uncached, on every request
- **Severity:** Medium
- **Category:** Performance
- **Location:** `backend/insights/attention.py:534-552` (`build_attention_rows` fans out to ~9 builders per GET); `backend/insights/services.py:656-693` (`build_growth_hints` purchase-price-creep: `[:800]` loop with a nested `PurchaseItem` query per product); `backend/insights/alerts.py:166-180` (credit-limit: `LedgerService.customer_exposure_for_credit_limit` per active customer), `:344-396` (`build_leakage_detectors` same `[:800]` nested-query pattern), `:206-229` (`build_business_alerts` calls `forecast_cashflow`, which itself recomputes `receivables_aging`); `ReportService.receivables_aging` is recomputed by alerts, hints, health, and forecast within one `AttentionFeedView` GET.
- **Impact:** `/api/v1/insights/attention/` (dashboard load) can issue hundreds–thousands of queries and re-run cashflow/GST-health scans every call; scales with customer/product count.
- **Fix:** Batch the per-row lookups (annotate/prefetch), memoise `receivables_aging`/`forecast_cashflow` for the request, and cache the assembled attention feed per (company, as_of) for a short TTL.

### [B9-013] Token-usage totals are summed in Python over every ledger row instead of a DB aggregate
- **Severity:** Medium
- **Category:** Performance
- **Location:** `backend/insights/assistant.py:117-120` (`_month_token_usage`), `backend/insights/views.py:313-316` (`AiUsageView`)
- **Observation:** `sum((r.tokens_in + r.tokens_out) for r in rows)` / `sum(r.tokens_in for r in qs)` load the full month of `AiUsageLedger` rows into memory on every assistant turn (budget check) and every usage-page load.
- **Impact:** Cost grows linearly with monthly AI activity; a heavy tenant pays a full table scan + object hydration on every single assistant message.
- **Fix:** `AiUsageLedger.objects.filter(...).aggregate(t=Coalesce(Sum(F("tokens_in") + F("tokens_out")), 0))`.

### [B9-014] A LOST lead can still be converted; there is no lead state machine or CONVERTED terminal state
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `backend/crm/services.py:41-121` (`convert_lead` has no status guard); `backend/crm/models.py:8-27` (`Status` = NEW/CONTACTED/QUALIFIED/LOST); `backend/crm/views.py:23-44` (`LeadViewSet` is a plain `CompanyScopedViewSet` — PATCH sets any status)
- **Observation:** `convert_lead` sets `lead.status = QUALIFIED` regardless of the prior status and creates a `Customer` + `Opportunity`. No transition validation anywhere; `LOST` → convert works. There is no distinct "converted" state, so a converted lead is indistinguishable from a merely qualified one, and re-`PATCH` back to NEW is allowed.
- **Impact:** Dead leads get resurrected into customers/opportunities; pipeline reporting cannot tell qualified from converted; status can move arbitrarily.
- **Fix:** Reject `convert` when `status == LOST` (or require an explicit reopen), add a `CONVERTED` status, and enforce allowed transitions in the serializer/service.

### [B9-015] Professional Tax slab is looked up on the LOP-prorated gross
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `backend/payroll/services.py:353` — `pt_amount = _pt_amount(gross_amt, _resolve_pt_slabs(company, employee), month=month)` where `gross_amt` is already `gross_full * prorate`
- **Observation:** PT is a fixed monthly levy keyed to the monthly wage bracket. Using the prorated earned amount can drop an employee into a lower (or zero) slab in any month they take unpaid leave. ESI eligibility, by contrast, correctly uses `gross_full` (line 350).
- **Impact:** Under-deduction of PT in LOP months; inconsistent with state PT practice (levy is on the salary rate, not days worked).
- **Fix:** Pass `gross_full` (the salary rate) to `_pt_amount`, matching the ESI-eligibility treatment; keep proration only for the earnings-based components (PF/ESI contribution, net).

### [B9-016] `_looks_like_tax_question` is disabled whenever the message contains "growth" or "churn"
- **Severity:** Medium
- **Category:** Security
- **Location:** `backend/insights/assistant.py:95-104`
- **Observation:** `if "growth" in lowered or "churn" in lowered: return False` short-circuits before any `TAX_PATTERNS` / geo+rate heuristics run. So "what GST rate should I charge for my growth product sold to Mumbai" is not treated as a tax question and goes to the LLM.
- **Impact:** Trivial keyword to bypass the pre-LLM tax-advice refusal. Output scrubbing (`_scrub_tax_output`) is the only remaining guard and is regex-based.
- **Fix:** Remove the blanket early-return; if the intent is to let growth questions through, require the growth signal *and* absence of tax signals rather than growth alone.

### [B9-017] Brand-new subscription created as PENDING can permanently write-block a tenant if the webhook never arrives
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `backend/billing/services.py:85-93` (new sub → `status=PENDING` when `live_razorpay`); `backend/billing/models.py:50-51` (`PENDING` → `is_write_blocked() == True`)
- **Observation:** When `live_razorpay` is true and no subscription exists, checkout creates a `PENDING` subscription which immediately write-blocks the tenant. Activation depends entirely on `RazorpayWebhookView` receiving `subscription.charged/active`. If `RAZORPAY_WEBHOOK_SECRET` is unset in prod, every webhook is 403'd (`views.py:127-131`); if the webhook is mis-routed, the tenant is stuck.
- **Impact:** Tenant fully locked out of writes with no self-service recovery path (billing portal shows PENDING).
- **Fix:** Keep the tenant on their prior state (trial/none) until the webhook confirms; add a reconcile job that polls Razorpay for `PENDING` subs older than N minutes; alert on webhook-secret-missing in prod.

---

### [B9-018] `CheckoutView` 500s on a non-numeric `plan_id`
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/billing/views.py:57-61`
- **Observation:** `plan_id = request.data.get("plan_id") ...; if plan_id: plan = Plan.objects.filter(pk=plan_id, is_active=True).first()`. A string like `"abc"` raises `ValueError`/`ValidationError` from the ORM before the `plan is None` check.
- **Impact:** 400-class user error returned as 500.
- **Fix:** Coerce with `int(...)` in a try/except and return `BusinessRuleError("Unknown or inactive plan.")`.

### [B9-019] `LeadViewSet.convert` 500s on a non-decimal `amount`
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/crm/views.py:37-38`; `backend/crm/services.py:57,116` — `Decimal(str(amount))` / `Decimal(str(amount or 0))`
- **Observation:** `amount = request.data.get("amount")` is passed straight through; `Decimal(str("abc"))` raises `decimal.InvalidOperation`, unhandled in the action.
- **Impact:** 500 on bad client input.
- **Fix:** Validate `amount` (DRF `DecimalField` or explicit try/except → 400).

### [B9-020] Deleting an `Employee` that has payslips raises an unhandled `ProtectedError`
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/payroll/models.py:69` (`employee = models.ForeignKey(Employee, on_delete=models.PROTECT, ...)`), `backend/payroll/views.py:19-27` (`EmployeeViewSet` allows DELETE with no override)
- **Observation:** `CompanyScopedViewSet.perform_destroy` calls `instance.delete()`; with `PROTECT` and existing `PaySlip` rows this raises `ProtectedError` → 500.
- **Impact:** Confusing 500 instead of a clear "employee has payroll history; deactivate instead" message.
- **Fix:** Override `perform_destroy` to block deletion when payslips exist and steer to `status=INACTIVE`.

### [B9-021] `SubscriptionDetailView` is only `HasCompany`, exposing Razorpay IDs to non-owners
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/billing/views.py:38-49`; serializer `backend/billing/serializers.py:26-37` exposes `razorpay_subscription_id`
- **Observation:** `PlanListView`, `CheckoutView`, `PortalView` all require `IsOwner`; `SubscriptionDetailView` requires only `IsAuthenticated, HasCompany`, so any staff member can read the subscription incl. `razorpay_subscription_id` and `current_period_end`.
- **Impact:** Minor billing-metadata disclosure inside a tenant; inconsistent with the rest of the billing surface.
- **Fix:** Add `IsOwner`, or drop `razorpay_subscription_id` from the non-owner response.

### [B9-022] PF/ESI amounts are rounded to paise, not to whole rupees as the statutes require
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `backend/payroll/services.py:338` (`pf_employee`), `:340-345` (EPS/EPF/admin/EDLI), `:351-352` (ESI employee/employer) — all via `_money` which quantizes to `Decimal("0.01")`
- **Observation:** EPFO rounds each contribution to the nearest rupee; ESIC rounds contributions up to the next rupee. The code keeps paise precision throughout.
- **Impact:** Challan/ECR values will not tie out to the portal by a few paise per employee, multiplied across the run.
- **Fix:** Add a rupee-rounding helper (`ROUND_HALF_UP` to `Decimal("1")` for PF, `ROUND_CEILING` for ESI) applied to the final contribution figures.

### [B9-023] `PF_ADMIN_MIN_ESTABLISHMENT` (₹500 floor) is declared but never applied
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `backend/payroll/services.py:27` (constant), `:344` (`pf_admin_charges = _money(wage_base * PF_ADMIN_RATE)` — per slip, no floor, no establishment aggregation)
- **Observation:** Admin charges (A/c 2) are a per-establishment 0.5% subject to a ₹500/month minimum. The code computes 0.5% per employee with no minimum and no run-level top-up.
- **Impact:** Under-stated admin charges for small headcounts / low wage bases; dead constant misleads readers.
- **Fix:** After summing `total_pf_admin` across the run, `total_pf_admin = max(total_pf_admin, PF_ADMIN_MIN_ESTABLISHMENT)` and post the delta; or drop the constant if out of scope for "preview payroll".

### [B9-024] `AiUsageLedger.cost_estimate` is always 0
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `backend/insights/assistant.py:174-182` (`record_usage` never sets `cost_estimate`); model field `backend/insights/models.py:137`
- **Observation:** The column exists (with 6dp precision) but nothing populates it; budgets and the usage view are token-only.
- **Impact:** No rupee/dollar cost visibility for owners; the field is dead.
- **Fix:** Compute `cost_estimate` from a per-model price table at `record_usage` time, or remove the field.

### [B9-025] Maharashtra (and other) PT ladders ignore the higher women's exemption threshold
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `backend/payroll/services.py:56-60` and the other multi-slab states; `Employee` has no gender field
- **Observation:** Maharashtra exempts women up to ₹25,000/month; the single ladder applies the men's ₹7,500 threshold to everyone. Several states have gender-specific thresholds.
- **Impact:** Over-deduction of PT for women employees in affected states.
- **Fix:** Add an optional gender/exemption flag on `Employee` and gender-aware slab selection, or document the limitation prominently (the "VERIFY WITH YOUR CA" note is generic).

### [B9-026] Tally opening-balance commit runs the entire party/product loop in one long transaction holding `select_for_update` on the sync run, with no upload-size cap
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/integrations/tally/adapter.py:39-47` (`_read_csv_rows` — unbounded), `:95-131` (`parse_tally_masters_rows` builds unbounded lists), `:423-580` (`_commit_tally_preview_inner` — `@transaction.atomic`, `select_for_update` on the run, then loops all customers/suppliers/products creating+completing invoices and posting stock)
- **Observation:** `create_upload_run` parses every row into memory; commit creates and `SalesService.complete`/`PurchaseService.complete`s one opening invoice per party inside a single transaction. No row limit anywhere (export is capped at 5000; import is not).
- **Impact:** A large migration file (thousands of parties) produces a multi-minute transaction, long lock hold, and possible timeout/OOM; a partial failure rolls back the whole import.
- **Fix:** Cap rows at upload; chunk the commit (batch or per-party savepoints) and record progress on the run so it can resume.

### [B9-027] `post_tally_xml` allowlist is host-only and fully bypassed when `DJANGO_ENV == "test"`
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/integrations/tally/adapter.py:676-713`
- **Observation:** When `TALLY_URL` is set, only the *hostname* is compared (`host != allowed_host`) — no scheme/port/path check, so an operator-supplied `base_url` of `http://<allowed-host>:6379/…` or with an arbitrary path is accepted. When `getattr(settings, "DJANGO_ENV", "") == "test"` (line 700) any host is treated as loopback.
- **Impact:** Limited SSRF latitude toward other ports/paths on the allowlisted host; test bypass is fine for tests but is a footgun if `DJANGO_ENV` is ever mis-set.
- **Fix:** Compare scheme+host+port against `TALLY_URL`; restrict to the exact base path prefix; gate the test bypass on `settings.DEBUG and settings.TESTING` rather than a string.

### [B9-028] `_maybe_send_digest_email` can re-send when the notification status is non-terminal
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/insights/services.py:198-213`
- **Observation:** After `NotificationService.send(...)` + `n.refresh_from_db()`, only `SENT` sets `email_sent_at` and only `FAILED` clears it. If `send` is queued/async and returns `PENDING`/`QUEUED`, `email_sent_at` stays null, so the next daily run re-enters and sends again (the subject-based `prior.filter(status=SENT)` guard only helps once the first attempt eventually reaches SENT).
- **Impact:** Possible duplicate daily digest emails while a send is in flight.
- **Fix:** Treat any non-FAILED terminal-or-pending status as "attempted" (stamp `email_sent_at` optimistically and reconcile on FAILED), or dedupe on `(company, summary_date)` at send time.

### [B9-029] `_collection_rates_from_history` does not actually derive rates from history
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `backend/insights/services.py:443-459`
- **Observation:** Docstring: "Derive rates from paid invoices when enough history". Implementation: if `paid.count() < 10` return defaults, else return defaults with `current` bumped to 0.80 and `days_1_30` to 0.55 — a fixed nudge, no computation from the actual `paid` data.
- **Impact:** Cashflow forecast presents "historical collection rates" in its disclaimer that are not historical; misleading.
- **Fix:** Either compute realised collection ratios per aging bucket from `PaymentAllocation` timing, or change the wording to "heuristic rates".

### [B9-030] `annual_new_regime_tax` has no marginal relief at the ₹12L 87A cliff
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/payroll/services.py:294-310`
- **Observation:** At `taxable` just above `NEW_REGIME_87A_INCOME_CAP` the full slab tax applies with no rebate, so taxable income of ₹12,00,001 owes materially more tax than ₹12,00,000 — the Finance Act provides marginal relief here.
- **Impact:** Over-projection of TDS for employees whose annualised salary sits just above the rebate cap.
- **Fix:** Add marginal relief: `tax = min(tax, taxable - NEW_REGIME_87A_INCOME_CAP)` in the band immediately above the cap (before cess).

### [B9-031] `NO_SALES_TODAY` alert and digest scheduling use server local time, not company time zone
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/insights/alerts.py:130-131` (`now = timezone.localtime(); ... now.hour >= 18`)
- **Observation:** The 6pm cutoff and `as_of == now.date()` comparison are in `TIME_ZONE`, not the company's locale. Product is India-only today, so impact is latent.
- **Impact:** If multi-region tenants are ever added, the "no sales today" alert fires at the wrong local hour / wrong day boundary.
- **Fix:** Resolve the company's time zone and compute `localtime` in it.

### [B9-032] `ShopFloorTelemetryView` PII guard only inspects top-level keys and there is no rate limit
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/insights/views.py:359-391`
- **Observation:** `for key in payload: if str(key).lower() in _TELEMETRY_PII_KEYS: raise` checks only first-level key names — nested dicts (`{"props": {"customer_name": ...}}`) and PII placed in *values* pass. `create` writes one row per POST with no throttle.
- **Impact:** PII can still land in `ShopFloorEvent`; a buggy/hostile client can flood the table.
- **Fix:** Reject unknown keys entirely (allowlist: `event`, `duration_ms`, `tap_count`), recurse if nested payloads are ever allowed, and add a throttle class.

### [B9-033] `WhatsAppConnectionView` overwrites `created_by` on update and deletes with no audit log
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `backend/integrations/views.py:253-277`
- **Observation:** `update_or_create(..., defaults={"created_by": request.user, ...})` sets `created_by` on every PUT, so the "who first connected" attribution is lost after any edit. `delete()` (lines 272-277) removes the row with no `AuditService.log` (contrast the PUT path which does log).
- **Impact:** Weak audit trail on a credential-bearing integration.
- **Fix:** Only set `created_by` when the row is created; `AuditService.log` the delete.

### [B9-034] `RazorpayWebhookView` replay dedupe relies on `cache.add`, which is per-process for LocMem
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/billing/views.py:152-163`
- **Observation:** `if not cache.add(dedup_key, "1", timeout=24h): return duplicate`. With the default `LocMemCache` (or a dummy cache), each gunicorn worker has its own store, so a redelivered webhook hitting a different worker is processed again.
- **Impact:** Idempotency of webhook application is not guaranteed in a multi-worker deployment; `apply_razorpay_subscription_status` re-applies (mostly idempotent, but `current_period_end` fallback `now + 30d` can drift).
- **Fix:** Persist processed event ids in a DB table (unique constraint) rather than cache, or require a shared cache backend.

### [B9-035] `AssistantThreadViewSet.perform_create` is dead code
- **Severity:** Low
- **Category:** Improvement
- **Location:** `backend/insights/views.py:199-210`
- **Observation:** `create()` is fully overridden and builds the thread directly, so `perform_create` (with its `serializer.save(...)`) is never reached.
- **Impact:** Confusing; a future maintainer editing `perform_create` will see no effect.
- **Fix:** Delete `perform_create`, or drop the `create` override and rely on `perform_create`.

### [B9-036] Payroll has no arrears / ad-hoc earning or deduction support
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `backend/payroll/services.py:412-439` (`complete_pay_run` only ever bases gross on `emp.salary` or a zero placeholder); no API accepts a per-slip gross/adjustment
- **Observation:** The `lop` action is the only per-employee input and it only sets `paid_days` (forcing `gross = emp.salary`). There is no way to add a bonus, arrear, advance recovery, or one-off deduction to a slip. Scope calls out "arrears" explicitly.
- **Impact:** Any real payroll month with a salary revision effective mid-period, a bonus, or a recovery cannot be represented.
- **Fix:** Add an adjustments model / `PaySlip` earning+deduction lines, or document the exclusion clearly in the module description.

### [B9-037] Re-enabling `accounting_enabled` after a pay run is completed leaves it with no GL entry
- **Severity:** Low
- **Category:** Gap
- **Location:** `backend/payroll/services.py:456` (`if company.accounting_enabled and total_gross > 0:` — evaluated only during `complete_pay_run`)
- **Observation:** A run completed while accounting was off never posts; there is no catch-up. The only way to post is `cancel_pay_run` (which requires `COMPLETED`) then `complete` again.
- **Impact:** Payroll expense/liabilities silently missing from the books for runs completed during an accounting-off window.
- **Fix:** Add a "post to GL" action for completed runs lacking a `PAY_RUN` journal, or warn on completion when accounting is off.

### [B9-038] `convert_lead` creates a customer with a blank `state` when neither lead nor company has one
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `backend/crm/services.py:93-106`
- **Observation:** `state = getattr(lead, "state", None) or getattr(lead.company, "state", "") or ""` — a blank string is accepted and the `Customer` is created with `state=""`.
- **Impact:** The first GST invoice raised for that customer fails place-of-supply resolution downstream, with the failure surfacing far from the conversion action.
- **Fix:** Require a state (from the lead) before allowing conversion when the company files GST, or flag the new customer as incomplete.

### [B9-039] `Opportunity` stage has no transition guards
- **Severity:** Low
- **Category:** Gap
- **Location:** `backend/crm/models.py:45-61`; `backend/crm/views.py:62-70` (plain `CompanyScopedViewSet`)
- **Observation:** `stage` (OPEN/WON/LOST) is freely PATCHable; WON→OPEN, LOST→WON etc. are all allowed, and WON carries no revenue/close-date semantics.
- **Impact:** Pipeline metrics (win rate, forecast) are unreliable.
- **Fix:** Validate stage transitions and stamp a `closed_at` / `won_at` on terminal moves.

### [B9-040] Tally CSV/XLSX export silently truncates at 5000 rows
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `backend/integrations/tally/adapter.py:620` (`for inv in qs[:5000]`), `:761` (`rows = qs.values(...)[:5000]`)
- **Observation:** The export/XML build hard-caps at 5000 invoices with no header, warning, or pagination.
- **Impact:** A tenant with >5000 invoices in the range gets an incomplete migration/export aid and no signal that data is missing.
- **Fix:** Add a date-range requirement or paginate; include a truncation marker row / response header when the cap is hit.

### [B9-041] `_xml_escape` does not strip XML-illegal control characters
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/integrations/tally/adapter.py:666-673`
- **Observation:** Escapes `& < > "` only. A party/product name containing `\x00`–`\x08`/`\x0b`/`\x0c` (from a bad import) produces an XML document Tally will reject on load.
- **Impact:** The whole `push_masters_http` / `push_vouchers_http` payload fails at the Tally end with an opaque error.
- **Fix:** Also remove/replace control characters (keep `\t\n\r`).

### [B9-042] `generate_insights` management command aborts the whole run on the first company that errors
- **Severity:** Low
- **Category:** Bug
- **Location:** `backend/insights/management/commands/generate_insights.py:11-18`
- **Observation:** `for company in Company.objects.filter(ai_features_enabled=True): generate_daily_summary(...); snapshot_health(...)` with no per-company try/except. `compute_health_score` swallows GST-health errors internally but `ReportService.dashboard` / `upsert_alerts` do not.
- **Impact:** One tenant with bad data blocks summaries/snapshots for all subsequent tenants when the command is used (the Celery fan-out path is isolated; this one is not).
- **Fix:** Wrap the per-company body in try/except, log, and continue; exit non-zero if any failed.

### [B9-043] `_run_llm_tools` places no cap on the number of tool calls the model may request
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/insights/assistant.py:500-527`
- **Observation:** `for tc in first.get("tool_calls") or []` executes every requested tool; only the *character budget* for notes is bounded, not the count. Several tools (`get_health_score`, `list_growth_hints`, `get_cashflow_forecast`) are individually heavy (see B9-012).
- **Impact:** A single turn can trigger many expensive analytics passes.
- **Fix:** Cap at e.g. 4 executed tool calls per turn (matches the rules-fallback `picked[:4]`).

### [B9-044] `run_assistant_turn` records the user message before the budget/validation path can reject the turn
- **Severity:** Low
- **Category:** Improvement
- **Location:** `backend/insights/views.py:222-231` calls `run_assistant_turn`; `backend/insights/assistant.py:577-583` — `assert_within_budget` runs, then the USER `AssistantMessage` is created, then processing
- **Observation:** Order is: `assert_within_budget` (raises → no message stored, good) → create USER message → run. If any later step raises `BusinessRuleError` (e.g. from a tool), the USER message is already persisted with no assistant reply, and the DRF view returns 400. On retry the user text is duplicated in the thread.
- **Impact:** Orphan user turns / duplicated prompts in thread history on transient failures.
- **Fix:** Wrap the turn in a transaction that rolls back the USER message on failure, or only persist the pair together at the end.

---

## Info / observations (not defects)

- **[B9-I1]** No defined data-retention or purge policy for `SUSPENDED` tenants — data is kept indefinitely, read-only (`billing/middleware.py` allows export + `/cancel|/void|/reverse` suffixes). Fine, but undocumented.
- **[B9-I2]** `insights/attention.py:289` hardcodes the GST 2.0 cutover date `date(2025, 9, 22)` in `_gst_rate_exposure_rows`.
- **[B9-I3]** `billing/services.py:149` hardcodes Razorpay `total_count: 120` (10 years) for every plan.
- **[B9-I4]** `payroll/services.py:341` — `pf_employer_epf = wage_base*0.12 - eps` yields ₹1249.50 EPS at the ₹15k ceiling (8.33% exact) vs the commonly-used ₹1250 statutory max; `EPS_MAX = 1250` only caps, never floors. Sub-rupee, widely tolerated, noted for completeness.

## Test-coverage gaps noted

- Payroll: no boundary tests for PT slabs (exact `min`/`max` edges, Maharashtra/Odisha `feb_amount`, Karnataka ₹25,000 edge), no test for `annual_new_regime_tax` slab math or the 87A cliff, no test for `paid_days == 0` (B9-003), no cancel→re-complete idempotency assertion for LOP slips.
- Billing: no test for plan upgrade creating a second Razorpay subscription (B9-001), no test for downgrade over seat_limit (B9-006), no test for `SUSPENDED` immediate block vs `current_period_end` (B9-007).
- Integrations: no test for duplicate-name `get_or_create` on commit (B9-002), no test for HTTP-push audit/idempotency (B9-010), no large-file/row-cap test.
- Insights: `test_assistant_prompt_injection_stays_scoped` covers cross-tenant scoping but not injection via tenant-owned party names (B9-009); no test asserting party PII is kept out of the LLM context (B9-008); no test that budget is enforced across the two LLM calls (B9-004).
- CRM: no test that converting a `LOST` lead is rejected (B9-014); no opportunity stage-transition tests.

---

# Deep code review — Frontend core (F1)

**Scope reviewed (every line):** `web/src/App.tsx`, `main.tsx`, `pwa.ts`, `pwaCaches.ts`, `theme/index.ts`;
`api/` (`client.ts`, `auth.ts`, `typedClient.ts`, `billing.ts`, `legacy/common.ts`, barrels), `api/*.test.ts`;
`auth/` (`AuthContext.tsx`, `session.ts`); `hooks/` (`useCompanySwitcher`, `useSubscriptionGate`, `useDebouncedValue`,
`usePreviewTotals`, `useProductSearch`); `lib/` (`native.ts`, `telemetry.ts`); `utils/` (`money`, `tax`, `gst`,
`permissions`, `safeUrl`, `status`, `priceList`, `blob`, `formatProductOptionLabel`, `indianStates` — spot);
`offline/` (`invoiceDraftCache.ts` + test, `flushPosCheckout.ts`); `navigation/menu.ts`; `layouts/AppShell.tsx`;
`config/` (`features.ts`, `featureFlags.ts`); `constants/` (`unitLabels.ts`); `i18n/` (`index.ts`, `moneyParity.test.ts`);
`onboarding/` (`shouldForceSetup`, `taxHints`, `analytics`); auth/landing pages (`LoginPage`, `RegisterPage`,
`ResetPasswordPage`, `ForgotPasswordPage`, `AcceptInvitePage`, `ForbiddenPage`, `NotFoundPage`, `HomePage`,
`DashboardPage`, `LimitedAccessLanding`, `AttentionPage`, `loginOtp.ts`); `vite.config.ts` (PWA verification).
Partially skimmed: `pages/**` outside the list, `components/**` (out of scope), `api/legacy/{sales,masters,...}` beyond `common`.

Re-verified against current code; existing `*REVIEW*.md` / `UX_*.md` items not re-logged unless still live.

## Severity counts

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 2 |
| Medium   | 7 |
| Low      | 11 |
| Info     | 5 |
| **Total**| **25** |

---

### [F1-001] Offline POS flush: partial failure leaves a completed cash sale unpaid and the draft stuck forever
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `web/src/offline/flushPosCheckout.ts:42-97`
- **Observation:** `createSalesInvoice(..., { idempotencyKey: draft.idempotencyKey })` is idempotent, but `completeSalesInvoice(invoice.id, { confirmBlankPos: true })` (line 70) carries **no** idempotency key, and the failure path does `deleteSalesInvoice(invoice.id)` then `throw err`. The receipt/allocation use derived keys (`-receipt`, `-alloc`) so they are safe, but they run *after* complete.
- **Impact:** If `completeSalesInvoice` succeeds server-side but the process dies / `removeDraft` fails before the draft is cleared, the next `flushOutbox` pass re-runs this function: create returns the already-created invoice, `completeSalesInvoice` throws "already completed", the code tries to delete a completed invoice (blocked, silently swallowed), and rethrows. The draft is re-queued as *failed* on every future flush, and the cash receipt + allocation for a genuinely completed invoice are **never created** — the sale shows as unpaid in AR indefinitely.
- **Fix:** Pass `{ idempotencyKey: \`${draft.idempotencyKey}-complete\` }` to `completeSalesInvoice` and make the flush tolerant of an already-completed invoice: on the "already completed" error, fetch the invoice, and if it is COMPLETED continue to the receipt/allocation steps (which are idempotent) and then `removeDraft`, instead of deleting + rethrowing.

### [F1-002] Company switch: a failure *after* the switch POST succeeds rolls the local company id back, opening a wrong-company / 409-reload window
- **Severity:** High
- **Category:** Bug
- **Location:** `web/src/hooks/useCompanySwitcher.ts:73-95`
- **Observation:** The `try` wraps `POST /auth/switch-company/` **and** `persistActiveCompanyId`, `qc.clear()`, `await refresh()` (`GET /auth/memberships/`), and `onSwitched?.(body.user)`. Any throw in `refresh()` (transient network) or in the caller-supplied `onSwitched` callback runs `restoreActiveCompanyId(previousId)` — reverting `bizboard:active-company-id` to the *old* company even though the server session is now on the *new* one.
- **Impact:** Subsequent requests send `X-Company-Id: <old>` while the session's active company is `<new>` → every call 409s with `company_context_conflict` → `client.ts:282-291` dispatches `bizboard:company-context-conflict` → `AuthContext.tsx:140-147` removes the key and `window.location.reload()`. It self-heals after one full reload, but for the interval between the successful switch and the reload the app is wedged (all data calls 409) and `qc.clear()` already wiped the previous company's cache.
- **Fix:** Only roll back on failure of the switch POST itself. Move `persistActiveCompanyId`, `qc.clear()`, `refresh()`, and `onSwitched` out of the rolled-back `try`, or wrap just `apiClient.post('/auth/switch-company/')` and treat everything after a 2xx as committed.

### [F1-003] PWA: `registerType: 'autoUpdate'` vs `pwa.ts` `onNeedRefresh` prompt — silent auto-reload, dead confirm dialog
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/vite.config.ts:39` (`registerType: 'autoUpdate'`) vs `web/src/pwa.ts:12-20`
- **Observation:** `pwa.ts` registers with `{ immediate: true, onNeedRefresh() { if (window.confirm(...)) updateSW(true) } }`. `vite-plugin-pwa`'s `virtual:pwa-register` only invokes `onNeedRefresh` for `registerType: 'prompt'`; with `autoUpdate` it self-applies the new worker and reloads on `controllerchange`.
- **Impact:** The `window.confirm("A new version is available. Reload now?")` never fires — dead code. On every deploy the tab reloads with no confirmation; a user mid-invoice/POS entry can lose unsaved form state (only saved by a `beforeunload` guard, if any). The comment in `pwa.ts` describing the prompt is misleading for future maintainers.
- **Fix:** Pick one model. Either set `registerType: 'prompt'` in `vite.config.ts` so the confirm works, or drop the `onNeedRefresh` handler from `pwa.ts` and document that updates auto-apply (and ensure an unsaved-changes `beforeunload` guard covers editor routes).

### [F1-004] Intra-state GST split: FE forces symmetric CGST=SGST; backend formula is asymmetric → preview total off by 1 paise
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/utils/tax.ts:79-96` and `:155-169`
- **Observation:** FE computes `const half = roundMoney(taxRaw / 2); cgst = half; sgst = half;` then `taxTotal = roundMoney(cgst + sgst + cess)`. The file header comment (line 33-35) documents the backend as `cgst = q2(tax/2); sgst = q2(tax) - cgst` — i.e. **not** symmetric. For a line tax with an odd third decimal (e.g. `taxRaw = 2.51` → FE cgst=sgst=1.26, total 2.52; BE cgst=1.26, sgst=1.25, total 2.51) the FE preview `taxTotal`/`lineTotal`/grand total is 1 paise higher than the document the backend actually posts.
- **Impact:** Preview vs posted-document mismatch on many ordinary intra-state invoices; the `BILL-01` comment claims GSTN validation requires exact symmetry, which contradicts the cited backend behaviour — one of the two is wrong. `money.ts` R5-005 says server totals win once saved, so the user sees the number change on save.
- **Fix:** Mirror the backend exactly: `cgst = roundMoney(taxRaw / 2); sgst = roundMoney(taxRaw) - cgst;`. If GSTN truly requires symmetry, fix the backend instead and update the comment — but FE and BE must agree.

### [F1-005] `fetchMoneyListFirstPage` fetches *all* pages (up to 5000 serial GETs) despite its name
- **Severity:** Medium
- **Category:** Performance
- **Location:** `web/src/api/legacy/common.ts:139-165`
- **Observation:** `export async function fetchMoneyListFirstPage<T>(path, params) { return fetchAllPagesMasters<T>(path, params); }` — the body walks every page in a `while (next && guard < MAX_PAGES)` loop with `MAX_PAGES = 5000`, awaiting each `fetchNextPage` sequentially, and `throw`s if still truncated after 5000.
- **Impact:** The name tells callers (and reviewers) it returns one page. On a large tenant this issues thousands of serialized requests, blocking the calling list view for minutes and hammering the API; the 5000-page ceiling then throws and discards everything fetched.
- **Fix:** Rename to `fetchAllPagesMasters` at call sites (or make it genuinely fetch page 1). Lower `MAX_PAGES` to a realistic bound, parallelize with a small concurrency window, or move these to server-side pagination / windowed loading.

### [F1-006] Request interceptor throws a raw "CSRF token is unavailable" for every unsafe method when offline / third-party cookies blocked
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/api/client.ts:95-106`, `:76-83`
- **Observation:** For non-GET/HEAD/OPTIONS/TRACE the interceptor does `try { await ensureCsrfCookie() } catch { await ensureCsrfCookie(true) }` then `applyCsrfHeader`. `ensureCsrfCookie` throws `new Error('CSRF token is unavailable...')` whenever the `/auth/csrf/` GET fails and no token is readable (offline, or Safari ITP / "block third-party cookies" on a cross-site API deploy).
- **Impact:** Every POST/PATCH/DELETE rejects at the interceptor with a confusing CSRF error string before any offline-queue / retry logic can classify it as a network failure. `getErrorMessage` then surfaces that CSRF wall-of-text to users who are merely offline.
- **Fix:** If `ensureCsrfCookie` fails with a network error (`isNetworkError`), let the request proceed (server will 403 and the response interceptor's CSRF auto-retry / offline handling takes over) or reject with a `Network Error`-shaped error, not the CSRF advisory text.

### [F1-007] `removeDraft` is not idempotent when IndexedDB delete rejects — flushed drafts get re-sent every pass
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/offline/invoiceDraftCache.ts:323-338`, consumed by `flushOutbox` `:369-379`
- **Observation:** `if (idbAvailable()) { await idbDelete(id); }` — if `idbDelete` rejects (transaction abort, storage pressure, Safari private mode quirks), the `await` throws and `writeLocal(...)` (the localStorage removal) never runs. In `flushOutbox` the draft was already successfully `sendFn`'d, so the failure to remove means it stays queued.
- **Impact:** On the next `flushOutbox` the same draft is re-submitted. The resource layer's `Idempotency-Key` prevents server-side duplication, but `flushed`/`failed` counters and `offline_flush_fail` telemetry inflate, and the outbox badge shows a permanently "pending" item.
- **Fix:** Wrap `idbDelete` in try/catch (best-effort like the rest of the file) and always run the localStorage removal; or `await Promise.allSettled([...])`.

### [F1-008] Offline outbox: IDB↔localStorage merge, "IDB canonical" logic, and `flushOutbox` locking are untested
- **Severity:** Medium
- **Category:** Gap
- **Location:** `web/src/offline/invoiceDraftCache.test.ts` (whole file) vs `invoiceDraftCache.ts:158-262`, `:354-406`
- **Observation:** `beforeEach` calls `setOutboxStorageMode('localStorage')`, so `idbAvailable()` returns false for the entire suite. `mergeDurable`, `listDrafts`'s `if (idb) { ... }` branch, the native-prefs fallback, and both `flushOutbox` locking paths (`navigator.locks` and the `localStorage` lock with the 60 s stale window) have zero coverage.
- **Impact:** The most corruption-prone code (dual-store reconciliation, cross-tab flush locking, migration merge) ships unverified; a regression there silently loses or double-flushes drafts.
- **Fix:** Add a fake-IndexedDB (`fake-indexeddb`) suite exercising: IDB-present merge with divergent localStorage, IDB open failure → localStorage fallback, concurrent `flushOutbox` calls, and `migrateV1IfNeeded` with a pre-existing v2 store.

### [F1-009] `calculateLineTax`: displayed discount percent still not clamped to 100 in the amount-only branch
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/utils/tax.ts:42-54`
- **Observation:** `discountAmount` is set (line 43-46) *before* the `Math.min(Math.max(0, discountAmount), gross)` clamp on line 54. Line 48-49: `if (input.discountAmount != null && input.discountPercent == null && gross > 0) { discountPercent = roundMoney((discountAmount / gross) * 100); }` — derived from the **unclamped** amount, and never clamped to 100. The `BUG-511` comment claims the "500%" display bug was fixed, but the fix only covers the `discountPercent != null` path (line 42).
- **Impact:** A line where the absolute discount amount exceeds gross still renders e.g. "312%" in the percent field, even though only the full gross is actually discounted (taxable clamps correctly). Confusing, and can round-trip a nonsensical percent back into a saved payload.
- **Fix:** `discountPercent = Math.min(100, roundMoney((Math.min(discountAmount, gross) / gross) * 100));` in the amount-only branch.

### [F1-010] `isAllowedPaymentUrl` passes any `upi:` string unvalidated; also allows `http:` and bare `localhost` in production
- **Severity:** Low
- **Category:** Security
- **Location:** `web/src/utils/safeUrl.ts:31-60`
- **Observation:** `if (trimmed.toLowerCase().startsWith('upi:')) return true;` returns true for **any** `upi:` payload with no inspection of `pa=` (payee VPA) / `am=` (amount). `isAllowedShareUrl`/`isAllowedPaymentUrl` also accept `u.protocol === 'http:'` (not just https) and `host === 'localhost'` / `*.bizboard.local` unconditionally, including production bundles.
- **Impact:** If a payment-link field from the API (or any injected data) is tampered, `openPaymentUrl` / `safePaymentHref` hands the user a `upi://pay?pa=<attacker>@upi&am=<x>` intent that opens their UPI app pre-filled to the attacker. `http:` allowance strips TLS on share/pay links.
- **Fix:** Parse `upi:` intents and require a plausible `pa` matching `isValidUpiVpa`, reject an `am` you didn't set. Drop `http:` (https only) and gate the `localhost` / `.bizboard.local` allowances behind `import.meta.env.DEV`.

### [F1-011] `AttentionPage` navigates to a backend-supplied href with no scheme/allowlist check
- **Severity:** Low
- **Category:** Security
- **Location:** `web/src/pages/AttentionPage.tsx:90`
- **Observation:** `<Button component={RouterLink} to={row.actionHref} ...>` — `row.actionHref` comes straight from `listAttentionRows()` API data.
- **Impact:** Defense-in-depth gap: a compromised/buggy backend value (`//evil.example`, `javascript:` — React Router mostly neutralizes these by resolving as a path, but relies on RR internals) is followed without validation. Same pattern likely recurs on other insight/alert rows.
- **Fix:** Validate `actionHref` is a same-app relative path (`startsWith('/') && !startsWith('//')`) before binding it to `to`; otherwise render a disabled state or route to a safe default.

### [F1-012] `printBlob` leaks the object URL on the `window.open` success path
- **Severity:** Low
- **Category:** Performance
- **Location:** `web/src/utils/blob.ts:21-33`
- **Observation:** `const url = URL.createObjectURL(blob); const printWindow = window.open(url, '_blank'); if (printWindow) { printWindow.focus(); printWindow.onload = () => printWindow.print(); }` — no `URL.revokeObjectURL(url)` anywhere in this branch. Only the popup-blocked iframe fallback revokes (after 120 s).
- **Impact:** Every successful print holds a Blob (potentially a multi-MB PDF) alive until the tab closes; heavy on POS/back-office machines that print many invoices per session.
- **Fix:** Revoke on the print window's `afterprint`/`unload`, or on a timeout, as the iframe path does.

### [F1-013] Auth/utility pages: hardcoded English strings and an inconsistent client-side password check
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/ForgotPasswordPage.tsx` (all copy), `ResetPasswordPage.tsx` (all copy), `NotFoundPage.tsx:27,35`, `DashboardPage.tsx:233,312`, `AcceptInvitePage.tsx:74-80`
- **Observation:** `LoginPage`/`RegisterPage`/`AcceptInvitePage` use `t(...)`; `ForgotPasswordPage`, `ResetPasswordPage`, `NotFoundPage` are 100% literal English ("Reset Password", "Page not found", "Back to Dashboard"). `RegisterPage` and `ResetPasswordPage` enforce `password.length >= 8` client-side; `AcceptInvitePage` only checks `!password`, so a 1-char password round-trips to a backend 400.
- **Impact:** `hi` users hit English on password recovery and 404; invite acceptance gives a worse error than registration for the same mistake.
- **Fix:** Route all copy through `i18n`; add the `>= 8` guard (and ideally `autoComplete="new-password"`) to `AcceptInvitePage`.

### [F1-014] `safeNextPath` does not reject backslash-prefixed paths
- **Severity:** Low
- **Category:** Security
- **Location:** `web/src/pages/LoginPage.tsx:23-35`
- **Observation:** Rejects `!decoded.startsWith('/')`, `decoded.startsWith('//')`, `/login`, `/register`, but a value like `/\evil.com` or `/\/evil.com` passes (`startsWith('/')` true, `startsWith('//')` false).
- **Impact:** Low — React Router treats `to="/\evil.com"` as an in-app path and does not perform an external redirect, so this is a hardening gap rather than an open redirect today.
- **Fix:** Also reject when the second char is `\` or when `decoded` matches `^/[\\/]`.

### [F1-015] `menu.ts`: the `ca-needs` nav path embeds a query string, so it is never "reachable" for the limited-role landing redirect
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/navigation/menu.ts:245-249` (`path: '/ca-needs?view=client'`), `:441-456` (`isReallyReachable`, `pathMatches`), `:459-467` (`findFirstNavPath`)
- **Observation:** `pathMatches(navPath, path)` does `path.split('?')[0]` on the **target** but compares against the raw `navPath`, which here still contains `?view=client`. So `pathMatches('/ca-needs?view=client', '/ca-needs')` is false on both the equality and the `startsWith(`${navPath}/`)` checks.
- **Impact:** `findFirstNavPath` / `isReallyReachable` can never select the CA-needs surface, so a user whose only reachable area is CA-needs falls through to `LimitedAccessLanding` "contact owner" instead of being routed in. Minor today, latent if permissions shift.
- **Fix:** Store `path: '/ca-needs'` and carry `?view=client` as a separate `search`/`query` field the renderer appends, or strip the query in `pathMatches` for `navPath` too.

### [F1-016] Thin test coverage on `client.ts` refresh/CSRF flows and `safeUrl` allowlist
- **Severity:** Low
- **Category:** Gap
- **Location:** `web/src/api/client.test.ts`, `web/src/utils/safeUrl.test.ts`
- **Observation:** `client.test.ts` covers error-envelope parsing and refresh *rejection* (BUG-407) but not: 401 → `refreshAccessToken` → successful retry of the original request; the 403 CSRF auto-retry (`_csrfRetry`); the `MIN_REFRESH_INTERVAL_MS` debounce returning `'cookie'`; `_retry` guard preventing a second refresh (401-loop). `safeUrl.test.ts` has 4 cases — no `.rzp.io` subdomain match, no `upi:` passthrough, no `http:` / `localhost` / `.bizboard.local`, no scheme-obfuscation (`java\nscript:`).
- **Impact:** The refresh/interceptor state machine and the payment-URL allowlist are exactly the code where a regression is a security or session-loss incident, and it's largely unguarded.
- **Fix:** Add adapter-mocked tests for the 401-retry-success and CSRF-retry paths plus the debounce/loop guards; expand `safeUrl` tests to the allow/deny boundary cases above.

### [F1-017] `fetchFeatureFlags` has no internal error handling; a failed fetch hides entitled optional modules
- **Severity:** Low
- **Category:** Broken-flow
- **Location:** `web/src/config/featureFlags.ts:51-62`; consumers `main.tsx:56-60`, `AuthContext.tsx:61,71,79,91,215`; `config/features.ts:88-93` (`resolveOptionalModuleFlag`)
- **Observation:** `fetchFeatureFlags` does `const { data } = await apiClient.get('/feature-flags/')` with no try/catch and rethrows. Every call site must remember `.catch()`. When it fails, `cachedFlags` stays `null`, and `resolveOptionalModuleFlag` returns `false` for Manufacturing/Payroll/CRM regardless of the tenant's actual entitlement.
- **Impact:** A transient `/feature-flags/` failure right after login silently removes Manufacturing/Payroll/CRM nav + routes for a paying tenant until the next successful refresh (tab focus / 10-min interval). New call sites that forget `.catch()` get an unhandled rejection.
- **Fix:** Catch inside `fetchFeatureFlags`, keep the previous `cachedFlags` on failure (don't overwrite with null), and return the stale value; log once. Consider a short retry.

### [F1-018] `NavSection.childActive` uses unbounded `startsWith` for the active-section test
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/layouts/AppShell.tsx:56`
- **Observation:** `const childActive = item.children?.some((c) => c.path && location.pathname.startsWith(c.path));` — no trailing-slash / exact-match guard, unlike the sibling `navPathSelected` (`:34-39`) used for the `selected` prop.
- **Impact:** A section whose child path is a prefix of an unrelated route (e.g. child `/sales` vs route `/sales-returns`, or `/inventory/stock` vs `/inventory/stock-counts`) auto-expands / stays open incorrectly. Cosmetic but confusing on deep navigation.
- **Fix:** Reuse `navPathSelected(location.pathname, c.path)` for `childActive`.

### [F1-019] `pwaCaches.ts` deletes a cache name that no longer exists in the Workbox config
- **Severity:** Low
- **Category:** Improvement
- **Location:** `web/src/pwaCaches.ts:3` vs `web/vite.config.ts:50-66`
- **Observation:** `PWA_CACHE_NAMES = ['bizboard-api', 'bizboard-pages']`. The current `runtimeCaching` in `vite.config.ts` defines only `bizboard-pages` (navigate requests); the comment there says authenticated `/api` is deliberately **not** runtime-cached, so `bizboard-api` is never created.
- **Impact:** Harmless no-op, but it misrepresents what logout actually purges and will mask a real omission if an `/api` cache is ever reintroduced under a different name.
- **Fix:** Drop `'bizboard-api'`, or (safer) enumerate `await caches.keys()` and delete every key matching `/^bizboard-/` so future cache names are covered automatically.

### [F1-020] `config/features.ts`: corrupted whitespace and an inconsistent e-invoice flag
- **Severity:** Low
- **Category:** Improvement
- **Location:** `web/src/config/features.ts` (whole file), `:127-131` (`isEinvoiceSubmitEnabled`)
- **Observation:** The file is padded with blank lines between almost every statement (looks like a merge/format accident). `isEinvoiceSubmitEnabled()` returns `features.einvoiceSubmit || features.advancedPilot` and never consults `getCachedFeatureFlags()` / a runtime key, whereas every sibling (`isGstrReportsEnabled`, `isAiInsightsEnabled`, `isTallyEnabled`, `isAccountingFeatureEnabled`, `isEwaySubmitEnabled`, …) honours runtime flags per BB-000741.
- **Impact:** e-invoice submit can't be toggled per-company at runtime like the rest; maintenance friction from the whitespace.
- **Fix:** Run the formatter; align `isEinvoiceSubmitEnabled` with `isEwaySubmitEnabled` (runtime key + build fallback) unless there's a documented reason it must stay build-time only.

### [F1-021] `permissions.ts`: dead `isViewer` guard in manufacturing/payroll checks
- **Severity:** Info
- **Category:** Improvement
- **Location:** `web/src/utils/permissions.ts:19-27`
- **Observation:** `canManageManufacturing` / `canManagePayroll` do `if (!user || isViewer(user.role)) return false; return isOwner(user.role);` — since the function only ever returns true for `OWNER`, the `isViewer` short-circuit can never change the result.
- **Impact:** None functionally; misleading about intended capability model (implies non-owner non-viewer roles were once meant to qualify).
- **Fix:** Reduce to `return !!user && isOwner(user.role);`, or wire the intended `user.canManageManufacturing` capability if one is planned.

### [F1-022] `priceList.ts` uses ad-hoc rounding instead of the shared `roundMoney`
- **Severity:** Info
- **Category:** Improvement
- **Location:** `web/src/utils/priceList.ts:48`
- **Observation:** `if (disc) price = Math.round(price * (100 - disc)) / 100;` — `Math.round` is half-away-from-+∞; `roundMoney` (used everywhere else for money) is ROUND_HALF_UP on magnitude via decimal expansion. Divergent on exact `.5` paise cases and for negative values.
- **Impact:** A price-list slab discount can land a paise off from the same computation done through `roundMoney`, producing a preview total that doesn't foot.
- **Fix:** `price = roundMoney(price * (100 - disc) / 100);`.

### [F1-023] i18n: only a 5-namespace parity test; missing keys render the raw dot-path to users
- **Severity:** Info
- **Category:** Gap
- **Location:** `web/src/i18n/index.ts:37-46`, `web/src/i18n/moneyParity.test.ts`
- **Observation:** `t()` falls back `catalog[key] ?? en[key] ?? key` — a key missing from both catalogs is displayed verbatim (e.g. `status.PARTIALLY_PAID`). `moneyParity.test.ts` only asserts `hi`/`ta`/`gu` parity for `billing`, `pos`, `einvoice`, `receipts`, `inventory`. `en.ts` and `hi.ts` currently have equal line counts, but nothing enforces full-catalog parity, and `status.ts:67` (`status.${UPPER}`) can produce keys not present in any catalog.
- **Impact:** Untranslated or newly-added strings ship as machine keys in the UI with no CI signal.
- **Fix:** Add a full-catalog `leafKeys(en)` ⊆ `leafKeys(hi)` test; add a dev-mode `console.warn` in `t()` on a hard miss; enumerate the status enum against `status.*` keys in a test.

### [F1-024] Scattered hardcoded English despite full i18n infrastructure
- **Severity:** Info
- **Category:** UX/UI
- **Location:** `web/src/hooks/useProductSearch.ts:55-61`, `web/src/pages/DashboardPage.tsx:233` ("Negative stock policy: … — change in GST settings"), `:312` ("Draft #"), `web/src/pages/NotFoundPage.tsx`
- **Observation:** `useProductSearch` returns literal `Type at least ${minChars} characters to search` / `Showing first ${pageSize} matches`; `DashboardPage` renders an English negative-stock warning that also links to `/settings/gst` (stock policy in *GST* settings is itself odd).
- **Impact:** Inconsistent localization; the DashboardPage warning is also a mislabeled destination.
- **Fix:** Move to `t()` with interpolation vars; re-point the negative-stock link to wherever the policy is actually edited (likely item/company settings).

### [F1-025] `AuthContext.logout` has no in-flight state; UI stays interactive as "logged in" during a slow logout
- **Severity:** Info
- **Category:** UX/UI
- **Location:** `web/src/auth/AuthContext.tsx:97-114`
- **Observation:** `logout` awaits `authApi.logout()`, then `clearAllDrafts`, `clearBizboardPwaCaches`, `clearFeatureFlagsCache`, and only then `setUser(null)`. `AppShell`'s logout button calls `void logout()` with no pending/disabled state.
- **Impact:** On a slow network the app remains fully interactive and visually authenticated for the duration (seconds); a user can fire more actions, and a double-click re-enters `logout`.
- **Fix:** Optimistically `setUser(null)` first (or set an `isLoggingOut` flag that blanks the shell), then do the network + cleanup; disable the logout button while pending.

---

# Deep review — FRONTEND transaction pages (F2)

**Scope reviewed (every line read):**
- `web/src/components/billing/**` — DocumentEditorShell, DraftLineTable, NumericField, SimpleTotalsPanel, InvoiceSourceLineTable, invoiceSourceLines, lineHelpers, NoteReasonSelect, types, index
- `web/src/utils/money.ts`, `web/src/utils/tax.ts`, `web/src/hooks/usePreviewTotals.ts` (dependencies)
- `web/src/pages/sales/**` — NewInvoicePage, InvoiceDetailPage, SalesHistoryPage, SalesInvoiceNoteEditor (+New Credit/Debit wrappers), SalesOrderEditorPage (+NewSalesOrder), DeliveryChallanEditorPage (+NewDeliveryChallan), QuotationsPage, SalesReturnsPage, ReceiptsPage, RecurringInvoicesPage, SalesOrdersPage, DeliveryChallansPage, CreditNotesPage, CustomersPage, invoice/makeInvoiceLine, invoice/useInvoiceOffline, invoice/InvoicePartyPanel
- `web/src/pages/purchases/**` — NewPurchasePage, PurchaseDetailPage, PurchaseHistoryPage, PurchaseNoteEditorPage (+New wrappers), PurchaseOrderEditorPage (+New wrapper), PurchaseReturnsPage, SupplierPaymentsPage, SuppliersPage, usePurchaseOffline
- `web/src/pages/payments/**` — AccountAggregatorPage, BankReconPage→phase/BankingPhasePages, BankStatementsPage→phase, PaymentLinksPage→phase
- `web/src/pages/accounting/**` — AccountingBankReconPage→phase/AccountingExtraPages, JournalsPage→phase/JournalsPage (others: ChartOfAccounts/CostCenters/FixedAssets/Periods are thin re-exports, spot-checked)
- `web/src/pages/imports/BillUploadPage.tsx` (+ Purchase/Sales BillUpload wrappers)
- `web/src/pages/pos/**` — PosPage, posStatus, posStatus.test
- `web/src/pages/public/PublicPayPage.tsx`
- `web/src/pages/offline/OfflineOutboxPage.tsx`
- `web/src/pages/erp/erpShared.tsx`

## Severity counts

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 6 |
| Medium | 33 |
| Low | 13 |
| Info | 6 |
| **Total** | **58** |

---

### [F2-001] `['purchases']` react-query key shared by 3 components with incompatible payload shapes
- **Severity:** High
- **Category:** Bug
- **Location:** `web/src/pages/purchases/NewPurchasePage.tsx:905`, `web/src/pages/purchases/PurchaseNoteEditorPage.tsx:90`, `web/src/pages/purchases/SupplierPaymentsPage.tsx:47-50`
- **Observation:** `NewPurchasePage` warms the cache with `qc.fetchQuery({ queryKey: ['purchases'], queryFn: () => listPurchasesPage() })` which resolves to a `PageResult` object `{results,count,next,previous}`. `PurchaseNoteEditorPage` and `SupplierPaymentsPage` both `useQuery({ queryKey: ['purchases'], queryFn: () => listPurchases(...) / listAllPurchases(...) })` which resolve to a plain `PurchaseInvoice[]`, then do `(purchases.data ?? []).filter((p) => p.status === 'COMPLETED')`.
- **Impact:** After completing a purchase and navigating (within gcTime) to Supplier Payments or a Purchase Credit/Debit Note editor, react-query serves the cached **object** as `purchases.data` until the component's own refetch resolves. `{results:[…]}.filter` throws `TypeError: purchases.data.filter is not a function` → the page renders a React error / blank screen. `invalidateQueries(['purchases'])` from PurchaseHistory/Detail/void also makes the stored shape nondeterministic.
- **Fix:** Give each consumer a distinct key (`['purchases','completed']`, `['purchases','all']`, `['purchases','page',page]`). Never `fetchQuery` a `Page` shape into a key another component reads as an array.

### [F2-002] Purchase editor still overwrites the company-wide default signature on upload
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `web/src/pages/purchases/NewPurchasePage.tsx:1119-1130` (`onSignaturePick` → `await updateCompany({ signature: uploaded.id })`)
- **Observation:** Picking a signature image for one purchase calls `updateCompany({ signature })`, silently changing the company default for **every future sales invoice, purchase, note and PDF**. The identical bug was fixed on the sales side (`NewInvoicePage.tsx:1107-1112`, comment "FE-09 … It used to also call updateCompany({ signature }) which silently changed the company-wide default").
- **Impact:** A user attaching a one-off signature to a supplier bill re-brands the whole tenant's documents. No confirmation, no undo.
- **Fix:** Mirror the sales fix — set only `signatureId` on the local payload; move "set as company default" to Settings.

### [F2-003] Payment-link "Refund" refunds real money with no confirmation
- **Severity:** High
- **Category:** Broken-flow
- **Location:** `web/src/pages/phase/BankingPhasePages.tsx:301-310, 376-380`
- **Observation:** For a `PAID` link the row shows a "Refund" button that runs `refund.mutate(r.id)` → `listGatewayPayments` → `refundGatewayPayment(capturedId)` immediately on click. No `window.confirm`/dialog. `cancel.mutate` (cancel a live link) is likewise unconfirmed.
- **Impact:** One mis-click issues a gateway refund against a customer payment; irreversible. Contrast invoice cancel which is guarded by `window.confirm` (BUG-520).
- **Fix:** Wrap Refund and Cancel in a confirm dialog showing amount + link/customer.

### [F2-004] POS cash checkout can strand a COMPLETED-unpaid invoice and double-charge on retry
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `web/src/pages/pos/PosPage.tsx:473-554` (`createCompletedInvoice`, `performCashCheckout`), `670-799` (`checkout` generates `userGestureIdempotencyKey()` fresh each call)
- **Observation:** `createCompletedInvoice` creates the invoice with `idempotencyKey: key`, then `completeSalesInvoice(invoice.id)` **without** an idempotency key; on any throw it attempts `deleteSalesInvoice(invoice.id)`. If `completeSalesInvoice` actually succeeded server-side but the response was lost, the delete of a now-COMPLETED invoice fails, `performCashCheckout` rethrows, cart is retained, and the UI shows only an error. The UPI path sets `unpaidRecover` on abort; **the cash path has no equivalent recovery UI.** The cashier retries → `checkout` mints a *new* key → a *second* completed invoice + second stock decrement + no receipt on the first.
- **Impact:** Orphan completed unpaid invoices, double stock movement, reconciliation drift on flaky connections (the exact scenario POS is built for).
- **Fix:** Pass a stable idempotency key to `completeSalesInvoice`; on failure, probe invoice status before deleting; surface an `unpaidRecover` banner from the cash path just like UPI.

### [F2-005] "Save & New" carries reverse-charge / TCS / TDS flags to the next document
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:648-676` (`resetForm`), `web/src/pages/purchases/NewPurchasePage.tsx:628-658`
- **Observation:** `resetForm` (called after `complete_new`) resets lines/customer/type/dates/discounts/payment but **does not reset** `isReverseCharge`, `confirmSalesRcm`, `supplyType`, `ecommerceOperatorGstin`, `companyGstinId`, `tcsSection/tcsRate/tcsAmount`, `showTcs` (sales); `companyGstinId`, `tdsSection/tdsRate/tdsAmount`, `showTds`, `showPaymentTerms` (purchase). Purchase does reset `isReverseCharge`/`itcEligibility`; sales does not reset RCM at all.
- **Impact:** After one RCM sale, the next unrelated invoice for a different customer is silently marked reverse-charge (and `confirmSalesRcm` stays checked, so Complete proceeds). Stale `tcsAmount`/`tdsAmount` are re-posted onto the new document. Wrong GST filing.
- **Fix:** Reset every statutory field in `resetForm` (or rebuild state from a single `initialState` object).

---

### [F2-006] `amountReceived` / `amountPaid` not clamped to grand total → overpayment receipt auto-created
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:232, 835-862`; `web/src/pages/purchases/NewPurchasePage.tsx:204, 849-876`
- **Observation:** The payment `NumericField` has `min={0}` but no upper bound. On complete, `toAllocate = Math.max(0, amountReceived - already)` and a receipt/allocation is created for that full amount even when `amountReceived > grandTotal`. `balance` is display-clamped to `Math.max(0, …)` so the UI hides the overpayment.
- **Impact:** A fat-finger `50000` instead of `5000` silently books a receipt/supplier-payment far larger than the invoice and allocates the excess; customer/supplier ledger goes into large unintended advance.
- **Fix:** Clamp `amountReceived`/`amountPaid` to `grandTotal` (or warn and require confirm above it); cap `toAllocate` at the invoice balance.

### [F2-007] Editing line quantity silently discards a manually-entered unit price (price-list customers)
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:980-1011` (`updateLine`), `947-978` (`addProduct` re-scan)
- **Observation:** In `updateLine`, when `patch.quantity != null && patch.unitPrice == null` it calls `resolveListUnitPrice(...)` and, if a hit exists, forces `nextPatch = { ...patch, unitPrice: resolved.unitPrice }`. `addProduct` on a repeat scan does the same via `recomputeLine(l, intraState, { quantity, ...(resolved ? { unitPrice } : {}) })`.
- **Impact:** For any customer with a price list, a user who overrides a negotiated unit price and then changes the quantity (or re-scans the barcode) loses their override with no indication.
- **Fix:** Only auto-apply the list price when the line's current price still equals the last list/selling price (i.e. was never manually edited); track a `priceEdited` flag.

### [F2-008] Manually edited due date is clobbered by the invoiceDate/terms effect
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:511-513, 1450-1456`; `web/src/pages/purchases/NewPurchasePage.tsx:510-512`
- **Observation:** `useEffect(() => setDueDate(addDaysIso(invoiceDate, paymentTermsDays || 0)), [invoiceDate, paymentTermsDays])` unconditionally overwrites `dueDate`, but the Due Date field is directly editable (`onChange={(e) => setDueDate(e.target.value)}`). Any later change to invoice date or terms wipes the manual value. On edit-hydration the same effect can overwrite a loaded `inv.dueDate` that differed from `invoiceDate + paymentTermsDays`.
- **Impact:** Custom payment due dates cannot be kept; editing a saved invoice can silently change its due date.
- **Fix:** Track `dueDateTouched`; only recompute while untouched. Don't recompute on hydration.

### [F2-009] Stock-shortfall gate aggregates across ALL warehouses, not the selected one
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:326-352` (`availableByProduct` sums every `listStock()` row), `1032-1036` (`canComplete` uses `stockShortfalls`)
- **Observation:** `availableByProduct` does `map.set(id, (prev ?? 0) + toNumber(s.available ?? s.onHand))` over the whole company's stock, ignoring `warehouseId`. `stockShortfalls` (policy `BLOCK`) then compares line qty to the company-wide total.
- **Impact:** With multiple godowns, Complete is allowed when the *selected* warehouse is short (stock sits elsewhere), or blocked when another warehouse could cover it. Backend re-checks, so the user hits a late hard failure or an incorrect early block. Same aggregation in `NewPurchasePage.tsx:284-291` and `PosPage.tsx:226-233` (POS never enforces it at all).
- **Fix:** Filter `listStock()` rows to the selected warehouse before summing; POS should honor `negativeStockPolicy === 'BLOCK'` client-side.

### [F2-010] Credit/debit notes & returns force integer quantities — fractional-unit lines can't be returned
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/components/billing/invoiceSourceLines.ts:63-66` (`clampSourceLineQty` → `Math.max(0, Math.floor(qty))`), used by `InvoiceSourceLineTable`/`InvoiceReturnLineTable` in SalesInvoiceNoteEditor, SalesReturnsPage, PurchaseReturnsPage
- **Observation:** Every source-line quantity is `Math.floor`ed.
- **Impact:** An invoice line of `2.5 KG` / `0.75 LTR` cannot be credited or returned for its real amount — the user is limited to whole units, understating the credit and leaving stock/GST wrong.
- **Fix:** Allow decimals (respect the product's unit precision); clamp to `maxQty` without flooring.

### [F2-011] Sales credit/debit note line price is not editable — price-correction notes impossible
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `web/src/components/billing/InvoiceSourceLineTable.tsx:120` (unit price rendered as `formatMoney(line.unitPrice)`, no input), `web/src/pages/sales/SalesInvoiceNoteEditor.tsx:180-190`
- **Observation:** The `InvoiceSourceLineTable` shows unit price read-only; only quantity is editable and it is capped at the original invoice quantity (`maxQty`).
- **Impact:** `CORRECTION_OF_INVOICE` / `POST_SALE_DISCOUNT` notes that adjust *rate* (overcharge/undercharge) cannot be represented at all. A sales debit note (supplementary invoice for undercharge) is structurally impossible — it can only pick existing lines at the original price/qty.
- **Fix:** Make unit price (and a discount field) editable on note lines; for debit notes drop the `maxQty` cap or add free lines.

### [F2-012] Purchase notes: no source-quantity cap and zero-qty lines are saveable
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/purchases/PurchaseNoteEditorPage.tsx:366-400` (`NumericField` with no `min`/clamp, no `recomputeLine`), `217` (`canSave = supplierId && lines.length > 0`)
- **Observation:** Qty/price `NumericField`s use the default `min=0` (zero allowed) and are not bounded by the source purchase quantity. A line left at qty 0 still counts toward `lines.length > 0`, so the note saves.
- **Impact:** A purchase credit note can be raised for more units than were ever purchased (over-credit of ITC), or committed with dead zero-qty lines.
- **Fix:** Enforce `min` 0.001 and `maxQty` from the source purchase line; exclude zero-qty lines from `canSave` and payload.

### [F2-013] Returns: no idempotency key on create+complete, and no awareness of prior returns
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/sales/SalesReturnsPage.tsx:102-121`, `web/src/pages/purchases/PurchaseReturnsPage.tsx:101-120`
- **Observation:** `createMutation` does `createSalesReturn(...)` then `completeSalesReturn(draft.id)` with no `idempotencyKey`. `invoiceItemsToSourceLines` sets `maxQty` from the invoice line qty only — it does not subtract quantities already returned on earlier return documents.
- **Impact:** A network retry of `createSalesReturn` creates a duplicate return (double stock-in, double credit). A user can return the full quantity again via a second return document; the UI shows no "already returned N".
- **Fix:** `userGestureIdempotencyKey()` on both calls; fetch and subtract already-returned quantity per line before setting `maxQty`.

### [F2-014] Bank recon: "Confirm"/"Match" with no amount check and actions still shown on MATCHED lines
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/phase/BankingPhasePages.tsx:560-563, 626-659` (BankReconPage); `web/src/pages/phase/AccountingExtraPages.tsx:168-179` (AccountingBankReconPage `match`)
- **Observation:** `confirm.mutate({ line: line.id, receipt: s.id, … })` fires for any suggestion regardless of whether `s.amount === line.amount`. The per-line action block only checks `Number(line.amount) > 0 && canWrite`, not `line.matchStatus` — suggestions/Confirm buttons still render for an already-`MATCHED` line. The accounting variant matches an arbitrary `journalLine` to an arbitrary `bankStatementLine` with no equality guard.
- **Impact:** Over-match / mismatched reconciliation: a ₹9,000 bank line confirmed against a ₹9,090 receipt, or a line matched twice.
- **Fix:** Block Confirm when amounts differ beyond a tolerance (or require an explicit "amounts differ" acknowledgement); hide all match actions when `matchStatus === 'MATCHED'`.

### [F2-015] Offline Outbox: queued sale/POS drafts deletable with one click, no confirmation
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/offline/OfflineOutboxPage.tsx:104-108, 151-155`
- **Observation:** `deleteOne` → `removeDraft(...)` immediately, with no `window.confirm`. A row can be a `queued` invoice or POS sale created while offline (real, unsynced revenue).
- **Impact:** A tap on "Delete" permanently discards an offline sale before it ever reaches the server. History pages confirm even a *draft* delete; this page confirms nothing.
- **Fix:** `window.confirm` for non-`localOnly` rows, spelling out that an unsynced document will be lost.

### [F2-016] Destructive/irreversible actions with no confirmation across list pages
- **Severity:** Medium
- **Category:** UX/UI
- **Location:** `web/src/pages/sales/SalesOrdersPage.tsx:102-123` (convert to invoice / to challan); `web/src/pages/sales/RecurringInvoicesPage.tsx:57-72, 117-119` (Run now generates a live invoice; Deactivate); `web/src/pages/sales/CustomersPage.tsx:116-121` (Block/Unblock); `web/src/pages/purchases/SuppliersPage.tsx:74-78, 212` (Activate/Deactivate); `web/src/pages/phase/BankingPhasePages.tsx:487-490, 533` (Commit statement), `264-267` (Cancel link); `web/src/pages/phase/JournalsPage.tsx:69-76, 105` (Reverse a POSTED journal)
- **Observation:** These all mutate state directly from a single button with no dialog. `QuotationsPage` and the `*NotesPage`/`DeliveryChallansPage` (via `ConfirmDialog`) do confirm equivalent actions, so the app is inconsistent.
- **Impact:** One mis-click converts an order, generates & posts a recurring invoice, blocks a customer mid-transaction, commits a bank statement into the ledger, or reverses a posted journal.
- **Fix:** Route these through `ConfirmDialog` like the sibling pages already do.

### [F2-017] "Complete" from list/detail menus has no place-of-supply / GSTIN-change confirm path
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/sales/SalesHistoryPage.tsx:88-95`; `web/src/pages/purchases/PurchaseHistoryPage.tsx:81-88`; `web/src/pages/purchases/PurchaseDetailPage.tsx:49-59` (only `GSTIN_TOTAL_CHANGED`, not `place_of_supply_unresolved`); `web/src/pages/sales/CreditNotesPage.tsx:32-39`
- **Observation:** The editors and `InvoiceDetailPage` wrap `completeSalesInvoice` in a `getErrorCode`/`window.confirm` retry for `place_of_supply_unresolved` and `GSTIN_TOTAL_CHANGED`. The list-menu `completeMutation`s call the API raw.
- **Impact:** Completing a draft from the history list for a blank-POS customer fails with a raw error and no way to proceed — the user must open the editor to get the confirm dialog. Inconsistent, dead-ends the flow.
- **Fix:** Extract the confirm-retry helper (`completeInvoiceWithConfirms`) and reuse it in every Complete entry point.

### [F2-018] NewPurchasePage has no preview-fallback — a persistent preview error blocks all Completes
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/purchases/NewPurchasePage.tsx:1061` (`canComplete = … && (!previewOnline || preview.ready)`), `1062-1077` (`shownTotals` ternary `preview.error ? totals : totals` — both branches identical, dead)
- **Observation:** Sales added `previewFellBack` (FE-07: allow Complete on client totals when the server preview keeps erroring — `NewInvoicePage.tsx:1030-1036`). Purchase never got it: `preview.ready` is `false` on error, so `canComplete` is permanently false while online.
- **Impact:** If the `/preview` purchase endpoint 500s (or the payload trips a server bug), a completely valid purchase cannot be completed at all — no override.
- **Fix:** Port the `previewFellBack` allowance and the "totals are on-device" warning banner.

### [F2-019] Purchase RCM totals & summary bar computed from client math even when server preview is available
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/purchases/NewPurchasePage.tsx:582-609` (`rcmPreview` derives from client `totals`), `620-622` (`displayGrandTotal`/`balance`), `1614-1630` (bottom bar: `Subtotal`/`Tax` from client `totals`, grand total from `preview.totals`), `1751-1776` (`DocumentTaxSummary` mixes `shownTotals` and `preview.totals?.grandTotal`)
- **Observation:** The RCM "tax liability" alert amounts (`rcmTaxTotal`, `rcmCgst`, …) and the payable-to-supplier figure come from `calculateInvoiceTotals` on the FE float path, not the authoritative server preview. The summary strip shows a server grand total next to client-computed subtotal/tax. For RCM, `displayGrandTotal = preview.totals?.grandTotal ?? rcmPreview.payable` — if the server preview returns a *tax-inclusive* grand total for an RCM bill, it is displayed under the label "Payable (RCM, excl. tax)".
- **Impact:** Statutory RCM liability figures can be off by paise vs the posted document; the "excl. tax" label can contradict the number shown; internally inconsistent totals strip.
- **Fix:** Drive every displayed figure from one source (`shownTotals`); compute RCM payable from server preview fields, not client totals.

### [F2-020] `billedFromPack` silently overwrites the extracted/edited quantity
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/imports/BillUploadPage.tsx:55-62, 264-276` (`updateLine`: `if ('cs' in patch || 'pcs' in patch || 'upc' in patch) { … next.quantity = billed }`)
- **Observation:** Editing any of case/pcs/units-per-case recomputes `quantity = cs*upc + pcs` and replaces whatever was there (OCR value or a value the user typed).
- **Impact:** When the printed billed quantity ≠ `cs*upc+pcs` (free goods, broken case, scheme qty) the derived value overrides the correct one, and the user has no signal that it was replaced. Commits a wrong purchase quantity → wrong stock and ITC.
- **Fix:** Only auto-fill quantity when it is currently blank; otherwise show the computed value as a suggestion the user can accept.

### [F2-021] BillUpload commit has no idempotency key and no per-line validation
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/imports/BillUploadPage.tsx:192-242`
- **Observation:** `commitMutation` does `updateImportPreview(jobId, …)` then `commitImport(jobId, …)` with no idempotency key (`uploadImport` uses `newIdempotencyKey()`, commit does not). `disabled` only checks `includedCount === 0` — included lines may have blank name/qty/price (all are free `type="number"` strings passed straight through).
- **Impact:** A timed-out-but-succeeded commit, retried after the button re-enables on error, can create a second draft invoice. Lines with empty price/qty commit as zero-value invoice lines.
- **Fix:** Pass a stable idempotency key to `commitImport`; validate that every `include` line has name + positive qty + non-negative price before enabling Commit.

### [F2-022] DeliveryChallanEditorPage builds challan lines from a list payload that usually lacks `items`
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/sales/DeliveryChallanEditorPage.tsx:142-179` (`onOrderPick` maps `(order.items ?? [])` directly)
- **Observation:** The order comes from `listSalesOrders()` (list payload); `onOrderPick` never fetches the full order, unlike `SalesInvoiceNoteEditor.onInvoicePick` / `PurchaseNoteEditorPage.onPurchasePick` which do `items?.length ? … : await getX(id)`.
- **Impact:** Picking a sales order to seed a challan yields an empty line list whenever the list endpoint omits `items` (the common case) — the user gets a blank challan and no error.
- **Fix:** `const full = order.items?.length ? order : await getSalesOrder(order.id);` before mapping. Also compute tax after `customerId` is set (currently uses the stale closure `intraState`).

### [F2-023] Allocation amount can exceed payment amount / invoice balance on Supplier Payments
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/purchases/SupplierPaymentsPage.tsx:80-89, 254-261`
- **Observation:** The optional allocation `TextField` (`type="number"`) is only checked as `Number(allocAmount) > 0` before `createAllocation({ amount: Number(allocAmount) })`. The auto-fill uses `Math.min(amount, balance)` but the user can freely overtype it. `ReceiptsPage` added a proper clamp+error (`ReceiptsPage.tsx:107-117`); this page did not.
- **Impact:** Over-allocation of a supplier payment against a bill (or beyond the payment's own value), corrupting payables.
- **Fix:** Mirror `ReceiptsPage`: reject `alloc > min(paymentAmount, balance) + 0.001` with a readable message.

### [F2-024] Sales credit/debit note editor omits `assumeLocalStateForBlankParty`; loads all customers & all completed invoices unpaginated
- **Severity:** Medium
- **Category:** Performance
- **Location:** `web/src/pages/sales/SalesInvoiceNoteEditor.tsx:84-90, 145-148`
- **Observation:** `isIntraState(company…, partyState)` is called **without** the `{ assumeLocalStateForBlankParty }` option that `NewInvoicePage` passes, so the client tax preview can withhold GST where the invoice actually charged it. `customers = listCustomers()` and `invoices = listSalesInvoices({ status: 'COMPLETED' })` are both unpaginated; the source-invoice `<Autocomplete>` lists **every** completed invoice with no server search.
- **Impact:** Wrong on-screen note totals for assume-local tenants; unusable source-invoice picker and slow initial load once a tenant has thousands of invoices/customers.
- **Fix:** Pass the assume-local option; switch to a debounced server-searched paginated picker (as `PaymentLinksPage`/`ReceiptsPage` do).

### [F2-025] Unpaginated party/product dropdowns across many editors — silent truncation at scale
- **Severity:** Medium
- **Category:** Performance
- **Location:** `SalesOrderEditorPage.tsx:75` & `PurchaseOrderEditorPage.tsx:74` (`listCustomers()`/`listSuppliers()`), `DeliveryChallanEditorPage.tsx:73,76`, `PurchaseNoteEditorPage.tsx:89-90`, `InvoiceDetailPage.tsx:95-98`, `phase/BankingPhasePages.tsx:548` (BankRecon customer select), `AccountingExtraPages.tsx` recon customer select, `RecurringInvoicesPage.tsx:28,30` (`pageSize:100` + `.slice(0,50)`), `PosPage.tsx:192-195` (`pageSize:100` customer `<select>`)
- **Observation:** These render the entire (or first-100) list into an `<Autocomplete>`/`<TextField select>` with client-only filtering and no search-as-you-type against the server.
- **Impact:** Beyond the page cap, parties/products are simply unselectable; POS forces the "type a name" path which creates duplicate customers.
- **Fix:** Standardise on the debounced `listXPage({ q })` searchable-picker pattern already used elsewhere.

### [F2-026] "Warm the list cache before navigate" is dead — key never matches the history page
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:886-895` (`qc.fetchQuery({ queryKey: ['sales-invoices'], … })`), consumer `web/src/pages/sales/SalesHistoryPage.tsx:74-79` (`queryKey: ['sales-invoices', page]`); same in `QuotationsPage.tsx:141-149`, and `NewPurchasePage.tsx:904-912` vs `PurchaseHistoryPage.tsx:67-72` (`['purchases', page]`)
- **Observation:** The editor pre-fetches into `['sales-invoices']`; the history list reads `['sales-invoices', page]` with `staleTime: 0, refetchOnMount: 'always'`. The keys never intersect, so the warm write is unused and history still shows a loading state / refetch after every save (the very thing the comment "so history isn't blank until hard refresh" claims to fix).
- **Impact:** Wasted request on every save; the promised no-flash navigation doesn't happen.
- **Fix:** Warm `['sales-invoices', 1]` (and reset the list to page 1), or drop the dead pre-fetch.

### [F2-027] POS blank-place-of-supply shows ₹0 tax; server can then charge GST the cashier didn't collect
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/pos/PosPage.tsx:288-342` (`intraState` null → `calculateLineTax` withholds tax → `totals.grandTotal` excludes GST), `724-744` (`blankPos` dialog → `confirmBlankPos: true`), `517-554` (`createReceipt({ amount: server grandTotal })`)
- **Observation:** For a walk-in with no state/GSTIN and `taxEnabled`, the tender panel shows `Tax ₹0` and a grand total with no GST. After the cashier confirms the blank-POS dialog, `completeSalesInvoice(id, { confirmBlankPos: true })` runs; if the server applies assume-local and adds CGST/SGST, `completed.grandTotal` > the amount shown, and the cash receipt is booked for the *server* total.
- **Impact:** The receipt/invoice is larger than the cash actually taken from the customer → till shortage / unreconciled difference on every blank-POS retail sale.
- **Fix:** When `taxEnabled` and POS is blank, either force a state selection before checkout or show the assume-local tax in the tender panel so the displayed total matches what will post.

### [F2-028] AccountingBankReconPage only considers the first 100 journal entries for GL matching
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/phase/AccountingExtraPages.tsx:120-123, 143-155` (`journals = listJournalsPage({ pageSize: 100 }).results`; `unmatchedGl` flat-maps over `journals.data`)
- **Observation:** Only 100 journal entries are fetched; older unreconciled GL lines never appear in the match picker.
- **Impact:** On established books, bank lines that correspond to GL entries older than the most recent 100 vouchers cannot be reconciled through this screen.
- **Fix:** Query unreconciled GL lines server-side for the chosen account (dedicated endpoint) rather than paging journals client-side.

### [F2-029] Print buttons swallow PDF-download failures (unhandled rejection, no user feedback)
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/sales/CreditNotesPage.tsx:83-92`; `web/src/pages/sales/DeliveryChallansPage.tsx:83-92`; `web/src/pages/sales/DebitNotesPage.tsx` (same pattern); `web/src/pages/purchases/PurchaseCreditNotesPage.tsx` / `PurchaseDebitNotesPage.tsx`
- **Observation:** `onClick={() => void downloadSalesDocumentPdf('credit-note', row.id).then((blob) => printBlob(blob))}` — no `.catch`. `SalesInvoiceNoteEditor` and `DeliveryChallanEditorPage` correctly add `.catch((err) => flashError(...))`.
- **Impact:** A failed/expired PDF request produces an unhandled promise rejection and a dead-looking button; the user has no idea why nothing printed.
- **Fix:** Add `.catch` that surfaces the error via the page's error state.

### [F2-030] `usePreviewTotals` re-serialises a freshly-built `buildPayload()` object every render
- **Severity:** Medium
- **Category:** Performance
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:737-743`, `web/src/pages/purchases/NewPurchasePage.tsx:727-733`, hook `web/src/hooks/usePreviewTotals.ts:17-18`
- **Observation:** `preview = usePreviewTotals('sales', … ? (buildPayload() as Record<…>) : null)`. `buildPayload()` returns a new object literal every render; the hook does `JSON.stringify(body)` then `useDebouncedValue(serialized, 280)`. Key ordering is stable so the *string* is stable, so this is saved by the string compare — but `buildPayload()` (which maps every line, builds nested item objects, trims strings) runs on **every render** of a large form regardless of whether anything changed.
- **Impact:** Noticeable render cost on big invoices (dozens of lines) on every keystroke/hover.
- **Fix:** `useMemo(buildPayload, [<real deps>])` and feed the memoised object to the hook.

### [F2-031] `NumericField` blur re-parse can emit a different value than what the user sees mid-edit
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/components/billing/NumericField.tsx:9-14, 61-83`
- **Observation:** `onChange` calls `onValueChange(Math.max(min, n))` **without** applying `decimals` rounding, but `onBlur` re-parses with `roundMoney`. `formatNumericText` returns `''` for `value === 0`, so a field the parent holds as `0` renders blank while focused vs shows nothing on blur — and a value like `10.005` propagates unrounded during typing then snaps to `10.01` (or `10.00`) on blur, after downstream `recomputeLine`/totals already ran on the unrounded value.
- **Impact:** Preview totals can briefly reflect an unrounded rate/qty; a line's stored `unitPrice` differs from the number the user last saw until they blur. Minor drift, but it feeds the tax preview.
- **Fix:** Apply the same `decimals` rounding in `onChange` as in `onBlur`; treat `0` as `"0"` not `""` when not focused (or at least document the discrepancy).

### [F2-032] `calculateLineTax` clamps `discountPercent` to 100 but not `discountAmount ≤ gross` before deriving percent for negative-margin lines
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/utils/tax.ts:42-55`; consumer `web/src/components/billing/lineHelpers.ts:106-122` (`applyDiscountAmountPatch`)
- **Observation:** `applyDiscountAmountPatch` clamps `amount = Math.min(Math.max(0, discountAmount), gross)` and `calculateLineTax` also clamps. But `DraftLineTable` wires the ₹ discount field straight to `onUpdate(line.key, { discountAmount: n }, { fromDiscountAmount: true })` and `NewInvoicePage.updateLine`/`NewPurchasePage.updateLine` recompute `gross` from `patch.quantity ?? l.quantity`. If the user first types a large discount amount, then reduces quantity, the stored `discountPercent` was computed against the *old* gross and is not re-derived on the qty change (only `recomputeLine` runs, which recomputes amount from the now-stale percent).
- **Impact:** After "₹500 off, then qty 10→2", the line can show a discount percent >100 internally / a discount larger than the new line gross until the ₹ field is re-touched; taxable base can go negative-ish before the final clamp.
- **Fix:** On any qty/price change to a line that has a `discountAmount`, re-derive percent from the new gross (call `applyDiscountAmountPatch`, not bare `recomputeLine`).

### [F2-033] History lists have no filters, sort, date range, or search
- **Severity:** Medium
- **Category:** Gap
- **Location:** `web/src/pages/sales/SalesHistoryPage.tsx` (whole page), `web/src/pages/purchases/PurchaseHistoryPage.tsx`, `web/src/pages/sales/CustomersPage.tsx`, `web/src/pages/purchases/SuppliersPage.tsx`
- **Observation:** Only prev/next pagination over 50-row pages. No status filter, date-range, customer/number search, or column sort, even though `listSalesInvoicesPage`/`listCustomersPage` accept `q`/`status`.
- **Impact:** Finding a specific invoice among thousands means blind paging; the task's "Lists" concerns (filter/sort) are unaddressed on the core transaction lists.
- **Fix:** Add the standard filter bar (status chips + date range + `q`) wired to the existing list-endpoint params.

### [F2-034] `VirtualizedTable` wrapped around a single 50-row page with hand-rolled spacer math
- **Severity:** Low
- **Category:** Improvement
- **Location:** `web/src/pages/sales/SalesHistoryPage.tsx:202-291`, `web/src/pages/purchases/PurchaseHistoryPage.tsx:155-236`
- **Observation:** `rowCount={rows.length}` where `rows` is one paginated page (≤50). Virtualization plus leading/trailing spacer `<TableRow>`s with `rows.length * 52` hardcoded next to `rowHeight={52}` add complexity for a list that is already small. PurchaseHistoryPage's leading spacer omits the `virtualRows[0].start > 0` guard SalesHistoryPage has (renders a height-0 row).
- **Impact:** Dead complexity; two slightly divergent implementations of the same workaround.
- **Fix:** Drop virtualization for the paginated lists, or paginate less aggressively and virtualize a real long list.

### [F2-035] `completeInvoiceWithConfirms` only recovers one confirm code per nesting level
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:103-140`; mirrored inline in `NewPurchasePage.tsx:793-838`, `InvoiceDetailPage.tsx:133-154`
- **Observation:** The nested try/catch handles `place_of_supply_unresolved` then `GSTIN_TOTAL_CHANGED` in one order. If the first error is `GSTIN_TOTAL_CHANGED` and the retry then fails with `place_of_supply_unresolved` (or a third code), it is rethrown rather than prompting.
- **Impact:** Rare, but a legitimately completable invoice can dead-end with a raw error requiring a full reload/retry.
- **Fix:** Loop: on each caught error, if it is a known confirm code not yet confirmed, prompt and retry; otherwise throw.

### [F2-036] `updateSalesInvoice` transport-details save on a COMPLETED invoice bypasses the amend guard by design but isn't labelled
- **Severity:** Low
- **Category:** Improvement
- **Location:** `web/src/pages/sales/InvoiceDetailPage.tsx:309-322` (`transportMutation` → `updateSalesInvoice(id, { vehicleNumber, … })` with no `confirmAmend`)
- **Observation:** The editor requires Owner + `confirmAmend` to `updateSalesInvoice` a COMPLETED doc (`NewInvoicePage.tsx:786-800`); the detail page's transport save calls the same endpoint with non-money fields and no guard.
- **Impact:** Works today only because the backend treats these fields as non-amending; a backend change would surface here inconsistently. Not user-visible now.
- **Fix:** Use a dedicated transport-update endpoint, or make the amend rules explicit and shared.

### [F2-037] TCS/TDS/journal-line amount fields accept negatives and are unclamped
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:1713-1715` (`setTcsRate(Number(e.target.value) || 0)` etc.); `web/src/pages/purchases/NewPurchasePage.tsx:1686-1688`; `web/src/pages/phase/JournalsPage.tsx:135-154` (`type="number"` debit/credit)
- **Observation:** Raw `type="number"` inputs; `Number("-5") || 0` keeps `-5`. No min, no cross-check against the taxable base.
- **Impact:** Negative TCS/TDS or a negative journal line can be submitted; backend is the only guard.
- **Fix:** `min={0}`, clamp on change, and for TCS/TDS validate `amount ≈ rate% of base`.

### [F2-038] `SalesOrderEditorPage` / `PurchaseOrderEditorPage` have no line discount UI and no unsaved-changes guard
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `web/src/pages/sales/SalesOrderEditorPage.tsx` (whole file — no `UnsavedChangesGuard`/`beforeunload`, no discount column), `web/src/pages/purchases/PurchaseOrderEditorPage.tsx` (same)
- **Observation:** `DraftLine.discountPercent` is hydrated from an existing order but there is no field to view or edit it; navigating away from a half-built order loses it silently (unlike `NewInvoicePage`/`NewPurchasePage` which guard).
- **Impact:** Orders can't carry a negotiated discount; accidental navigation discards work.
- **Fix:** Add a discount column and an `UnsavedChangesGuard when={lines.length>0 || customerId}`.

### [F2-039] `QuotationsPage` quotation lines use current catalog price only — no rate or discount entry
- **Severity:** Low
- **Category:** Partial-feature
- **Location:** `web/src/pages/sales/QuotationsPage.tsx:107-121` (`unitPrice: toNumber(l.product.sellingPrice)`), `46-50` (`DraftLine` = `{key, product, qty}`)
- **Observation:** A quotation always quotes `product.sellingPrice`; there is no unit-price or discount input in the add-line row.
- **Impact:** Can't quote a negotiated/volume price — the primary purpose of a quotation.
- **Fix:** Add editable unit price (+ optional discount) per quotation line.

### [F2-040] `NoteEditor` / order editors: hydration effect depends on `intraState` but is `loaded`-guarded, leaving stale line tax after party loads
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/sales/SalesOrderEditorPage.tsx:96-142` (dep `intraState`, guard `loaded`), `DeliveryChallanEditorPage.tsx:95-140`, `PurchaseOrderEditorPage.tsx:95-139`, `PurchaseNoteEditorPage.tsx:111-157`
- **Observation:** On first hydration `customers/suppliers` may not be loaded, so `intraState` is `null` and the mapped lines get zero tax. `intraState` is in the dep array but `if (!existing.data || loaded) return` blocks the re-run once `loaded` is true.
- **Impact:** Stored `lines[].cgst/sgst/igst` stay zero until the user edits each line; `lineTaxes`/`totals` memos recompute so the display is fine, and payloads send `gstRate` not amounts, so mostly cosmetic — but any code reading `line.lineTotal` directly is wrong.
- **Fix:** Compute `intraState` from the already-loaded `existing.data.customer/supplier` party, or re-map lines in a separate effect keyed on `intraState`.

### [F2-041] `PurchaseNoteEditorPage` shares `['purchases']` key and also lacks an unsaved-changes guard
- **Severity:** Low
- **Category:** Gap
- **Location:** `web/src/pages/purchases/PurchaseNoteEditorPage.tsx:90` (see F2-001), whole file (no guard)
- **Observation:** In addition to the F2-001 shape collision, the editor has no `UnsavedChangesGuard`/`beforeunload`; a drafted note is lost on navigation. `SalesInvoiceNoteEditor` has the same gap.
- **Fix:** Add the guard; namespace the query key.

### [F2-042] `InvoiceSourceLineTable.addLine` uses `Math.min(1, maxQty)` — a maxQty-0 line is "included" with qty 0
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/components/billing/InvoiceSourceLineTable.tsx:53-65`
- **Observation:** `quantity: Math.min(1, l.maxQty)` — when `maxQty` is 0 the added line is `included: true, quantity: 0`; `activeSourceLines` filters `quantity > 0` so it silently contributes nothing but shows as added.
- **Impact:** Confusing "added but does nothing" rows.
- **Fix:** Refuse to add a line whose `maxQty <= 0` (or use `Math.max(0.001, Math.min(1, maxQty))` and surface the cap).

### [F2-043] `RecurringInvoicesPage` "Run now" generates a live invoice with no confirm and a shared pending flag
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/sales/RecurringInvoicesPage.tsx:57-64, 117`
- **Observation:** `runNow.mutate(row.id)` immediately creates an invoice; `disabled={!canWrite || runNow.isPending}` is one flag shared by all rows.
- **Impact:** Mis-click issues an unwanted invoice; rapid clicks on different rows before the first resolves can each fire.
- **Fix:** Confirm dialog; track the in-flight row id.

### [F2-044] `PublicPayPage` file has broken double-spacing and skips heading levels
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/public/PublicPayPage.tsx:1-31, 104-233`
- **Observation:** Every source line is followed by a blank line (formatter artefact). The page's largest text is `variant="h3"` (amount) with company as `h5`; there is no `h1`, and levels jump h5→h3.
- **Impact:** Cosmetic source noise; minor screen-reader/document-outline issue on the customer-facing page.
- **Fix:** Reformat the file; use a sensible heading hierarchy (company `h1`, amount styled but not `h3`).

### [F2-045] `PaymentLinksPage` create amount and `RecurringInvoicesPage` qty/price accept unvalidated free text
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `web/src/pages/phase/BankingPhasePages.tsx:246-252` (`amount: Number(amount) || undefined`), `web/src/pages/sales/RecurringInvoicesPage.tsx:40-48, 97-98` (`quantity: qty`, `unitPrice: price || undefined` — plain `TextField`, not even `type="number"`)
- **Observation:** No positivity/format checks client-side; `qty` string `"abc"` is sent as-is in `lineTemplate`.
- **Impact:** Relies entirely on backend validation; confusing errors instead of inline feedback.
- **Fix:** Numeric inputs with `min`, validate before enabling the button.

### [F2-046] `BankStatementsPage` commit / `PaymentLinksPage` cancel / several mutations have no `onError`
- **Severity:** Low
- **Category:** Broken-flow
- **Location:** `web/src/pages/phase/BankingPhasePages.tsx:487-490` (`commit` — no `onError`), `264-267` (`cancel` — no `onError`), `web/src/pages/phase/BankingPhasePages.tsx:560-563` (`confirm` recon — no `onError`)
- **Observation:** These `useMutation`s omit `onError`, so a failure produces no visible feedback (only a console error).
- **Impact:** "Commit" a bad statement or "Cancel" a link, it fails, and the user sees nothing change.
- **Fix:** Add `onError: (e) => setError(getErrorMessage(e))`.

### [F2-047] `BillUploadPage` expandable preview rows are mouse-only
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/imports/BillUploadPage.tsx:616-641`
- **Observation:** Collapsed rows are `<TableRow onClick sx={{cursor:'pointer'}}>` with no `role`, `tabIndex`, or key handler. Flagged rows auto-expand (so critical rows are reachable), but clean rows can only be opened by clicking.
- **Impact:** Keyboard-only users can't review/edit non-flagged OCR lines before committing.
- **Fix:** Make the toggle a real `<button>` (or add `tabIndex={0}` + Enter/Space handling and `aria-expanded`).

### [F2-048] `BankReconPage` contains two dead/no-op code blocks
- **Severity:** Info
- **Category:** Improvement
- **Location:** `web/src/pages/phase/BankingPhasePages.tsx:550-557` (`if (Array.isArray(data) && … ) return data as Row[]; return data as Row[];` — both branches identical), `564-569` (`line: createLine?.id ?? (createLine as Row | null)?.id` — same expression on both sides of `??`)
- **Observation:** Leftover defensive code that does nothing.
- **Fix:** Delete both.

### [F2-049] `SupplierPaymentsPage` allocation auto-fill uses a stale `amount` snapshot
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/purchases/SupplierPaymentsPage.tsx:242-249`
- **Observation:** On purchase select, `setAllocAmount(String(Math.min(toNumber(amount), balance)))` captures `amount` at that moment; changing the payment amount afterwards leaves `allocAmount` stale (and, per F2-023, unvalidated).
- **Impact:** The allocation defaults to the wrong figure if the user fills amount after picking the bill.
- **Fix:** Recompute `allocAmount` from a `useEffect` on `[amount, purchase]`, clamped.

### [F2-050] `NewInvoicePage` keyboard `Ctrl+S`/`Ctrl+Enter` handlers re-register every render and don't dedupe against in-flight save
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/sales/NewInvoicePage.tsx:1060-1105` (effect deps `[canComplete, canSave, primarySave.mode, saveMutation]`), `NewPurchasePage.tsx:1082-1117`
- **Observation:** `saveMutation` is a new object each render, so the `keydown` listener is torn down/re-added on every render. The guard is `if (!saveMutation.isPending && canSave)` — but between a keydown firing `mutate('draft')` and React committing `isPending`, a second fast keypress can enqueue a duplicate.
- **Impact:** Minor duplicate-submit window via keyboard; constant listener churn.
- **Fix:** Depend on stable callbacks (`saveMutation.mutate`, primitives); gate on a ref set synchronously.

### [F2-051] `POS` cash-tender quick chips are absolute, not additive; no "exact + change" for split notes
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/pos/PosPage.tsx:1222-1240`
- **Observation:** `[100,200,500,2000].map(amt => <Chip onClick={() => setCashTendered(amt)}>)` — tapping ₹500 sets tender to exactly 500, so for an ₹850 bill it drops below total and `checkout('CASH')` errors with `tenderTooLow`.
- **Impact:** Cashiers expect to tap notes to build up the tender (500 + 500); here they must type.
- **Fix:** Make chips add to the current tender (`setCashTendered(t => toNumber(t) + amt)`).

### [F2-052] `POS` `tryAddByBarcode` adds the sole search result even on a non-matching query
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/pos/PosPage.tsx:375-393`
- **Observation:** Fallback `(matches.length === 1 ? matches[0] : undefined)` — pressing Enter after a partial search that happens to return one product adds it, even though neither its barcode nor SKU equals the typed string.
- **Impact:** Wrong item added to the sale on an ambiguous Enter.
- **Fix:** Only auto-add on an exact barcode/SKU hit; otherwise open the dropdown.

### [F2-053] `CustomersPage`/`SuppliersPage` block/deactivate toggles have no disabled state — rapid clicks flip repeatedly
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/sales/CustomersPage.tsx:266-268`, `web/src/pages/purchases/SuppliersPage.tsx:212-214`
- **Observation:** `<Button onClick={() => toggleMutation.mutate(c)}>` with no `disabled={toggleMutation.isPending}`. `toggleMutation` computes the next state from the row it was handed, so two fast clicks send two flips.
- **Impact:** Status can end up opposite to what the user intended on a slow connection.
- **Fix:** `disabled={toggleMutation.isPending}` and/or optimistic update.

### [F2-054] `SuppliersPage` doesn't require state/GSTIN for GST tenants (CustomersPage does)
- **Severity:** Low
- **Category:** Gap
- **Location:** `web/src/pages/purchases/SuppliersPage.tsx:54-72, 271-274` vs `web/src/pages/sales/CustomersPage.tsx:82-90, 386-396`
- **Observation:** `CustomersPage` gates `canSave` on `placeOfSupplyKnown` when `isGstRegistered && !assumeLocalStateForBlankParty`; `SuppliersPage` has no such check.
- **Impact:** Suppliers get created with no place of supply; the friction surfaces later as a blocked purchase Complete (`NewPurchasePage.posKnown`). Inconsistent UX.
- **Fix:** Apply the same requirement in the supplier dialog.

### [F2-055] `OfflineOutboxPage` sync button disabled state isn't reactive to connectivity
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/offline/OfflineOutboxPage.tsx:114-121`
- **Observation:** `disabled={busy || !navigator.onLine}` is evaluated once per render; there is no `online`/`offline` listener on this page, so coming back online doesn't re-enable "Sync now" until something else re-renders.
- **Impact:** User reconnects, the outbox page still shows a disabled Sync button.
- **Fix:** Track `navigator.onLine` in state with `online`/`offline` listeners.

### [F2-056] `DraftLineTable` free-text discount `%` and `cess %` clamp only the upper bound
- **Severity:** Low
- **Category:** Data-integrity
- **Location:** `web/src/components/billing/DraftLineTable.tsx:211-256`
- **Observation:** `discountPercent` → `onUpdate(key, { discountPercent: Math.min(100, n) })` (no lower clamp beyond `NumericField min={0}`), `cessRate` → `{ cessRate: n }` (no clamp at all). `calculateLineTax` re-clamps discount to `[0,100]` and cess `Math.max(0,…)`, so negatives are neutralised downstream, but a cess rate of e.g. `9999` flows straight into tax preview.
- **Impact:** An accidental huge cess rate produces a wildly wrong preview total until corrected (server rejects on save).
- **Fix:** Clamp cess to a sane max (e.g. 500) in the field; keep the discount lower clamp explicit.

### [F2-057] `roundMoney` operates on binary floats — FE preview can differ from the posted document by ~1 paise (documented, pervasive)
- **Severity:** Info
- **Category:** Data-integrity
- **Location:** `web/src/utils/money.ts:7-30`, consumed by `calculateLineTax`/`calculateInvoiceTotals` and every editor's `totals` memo
- **Observation:** The function reads `abs.toFixed(10)` off a float and does BigInt cent rounding — correct ROUND_HALF_UP given the 10-dp string, but the string itself is a binary-float approximation. The code comment (R5-005) acknowledges the ~1 paise divergence and says "The UI must always treat the server totals as authoritative once a document is saved."
- **Impact:** Every client-only totals path (SO/PO/challan/note editors, POS tender panel, `SimpleTotalsPanel` fallbacks) can show a grand total 1 paise off the server's, which is what the customer is actually charged. Editors that use `usePreviewTotals` mask this; the ones that don't (all the `SimpleTotalsPanel` pages, POS) do not.
- **Fix:** Where a server preview endpoint exists, use it for the *displayed* grand total on every editor (not just invoice/purchase); elsewhere show a "computed on device" note.

### [F2-058] `AccountAggregatorPage` is an intentional honesty stub (no functionality)
- **Severity:** Info
- **Category:** Partial-feature
- **Location:** `web/src/pages/payments/AccountAggregatorPage.tsx:1-17`
- **Observation:** Renders only a warning alert ("partner AA ingest APIs exist; this app has no consent UI"). No wiring, deliberate.
- **Impact:** None — noted for completeness so it isn't mistaken for a broken page.
- **Fix:** None needed; track as a feature-gap.

---

# Deep Code Review — M1: Mobile shell + Infrastructure / CI

**Reviewer pass:** M1
**Date:** 2026-09-03
**Repo:** E:\Bizboard  (branch `main`, clean)

## Scope note

Read in full:

- **Mobile** — `mobile/README.md`, `mobile/capacitor.config.ts`, `mobile/package.json`, `mobile/tsconfig.json`,
  `mobile/android/app/build.gradle`, `capacitor.build.gradle`, `proguard-rules.pro`,
  `AndroidManifest.xml`, `MainActivity.java`, `ExampleInstrumentedTest.java`, `ExampleUnitTest.java`,
  `android/build.gradle`, `settings.gradle`, `capacitor.settings.gradle`, `variables.gradle`,
  `gradle.properties`, `gradle/wrapper/gradle-wrapper.properties`,
  `res/xml/config.xml`, `res/xml/file_paths.xml`, `res/values/strings.xml`, `res/values/styles.xml`,
  `res/layout/activity_main.xml`, `capacitor-cordova-android-plugins/*.gradle` + manifest,
  generated `assets/capacitor.config.json`, `assets/capacitor.plugins.json`, `assets/public/index.html`.
- **Infra** — `docker-compose.yml`, `docker-compose.prod.yml`, `backend/Dockerfile`, `backend/docker-entrypoint.sh`,
  `backend/.dockerignore`, `web/Dockerfile`, `web/nginx.conf`, `web/.dockerignore`, `nginx/default.conf`,
  `.env.example`, `.env.production.example`, `backend/.env.example`, `web/.env.example`, `web/.env.e2e`.
- **CI/CD** — `.github/workflows/ci.yml`, `cd.yml`, `codeql.yml`, `.github/dependabot.yml`, `.github/CODEOWNERS`.
- **Scripts / load / audit** (skim) — `scripts/backup.sh`, `restore.sh`, `pin_image_digests.sh`, `split_phase_pages.py`,
  `load/*`, `web/audit_scripts/*`, `web/vite.config.ts`, `web/playwright.config.ts`, `web/playwright.golden.config.ts`,
  `backend/pytest.ini`, `backend/ruff.toml`.

Note: `mobile/android/app/src/main/assets/{public/**,capacitor.config.json,capacitor.plugins.json}` and
`res/xml/config.xml` are **git-ignored / generated** (`mobile/android/.gitignore:95-101`); the local copies are
stale scaffolding. The *tracked* native project is the hand-maintained `AndroidManifest.xml` + gradle files.
`.env` at repo root exists on disk but is git-ignored and untracked (`git ls-files` clean).

## Severity counts

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 3 |
| Medium   | 14 |
| Low      | 16 |
| Info     | 5 |
| **Total**| **38** |

---

### [M1-001] Android target/compile SDK 34 is below Google Play's minimum — Play distribution path is blocked
- **Severity:** High
- **Category:** Broken-flow
- **Location:** `mobile/android/variables.gradle:2-4`
- **Observation:** `minSdkVersion = 22`, `compileSdkVersion = 34`, `targetSdkVersion = 34`. `mobile/README.md:5` states "Android Play **internal testing** is the supported distribution path" and `:11` "API 34 / Capacitor 6 default".
- **Impact:** Since 2025‑08‑31 Google Play requires apps to target **API 35 (Android 15)** for all new submissions *and updates*, including the internal‑testing track. A 34‑targeted AAB is rejected at upload. Capacitor 6 (`mobile/package.json:12-18`, all `^6.0.0`) tops out at compile/target 34, so this is a Capacitor 7 upgrade, not a one‑line bump.
- **Fix:** Upgrade `@capacitor/*` to 7.x, set `compileSdkVersion`/`targetSdkVersion = 35`, bump AGP (8.2.1 → ≥8.6) and the Gradle wrapper, re‑run `npx cap sync android`, and re‑smoke the WebView on Android 15.

### [M1-002] Play/production mobile build has no reachable API origin (server.url unset + relative `/api/v1`)
- **Severity:** High
- **Category:** Broken-flow
- **Location:** `mobile/capacitor.config.ts:3-14`; generated `mobile/android/app/src/main/assets/capacitor.config.json:5-7`; `web/.env.example:1`
- **Observation:** `server.url` is only emitted when `CAPACITOR_SERVER_URL`/`VITE_APP_ORIGIN` is set; the committed config is just `{ androidScheme: 'https' }`. The wrapped SPA (`../web/dist`) is built with `VITE_API_BASE_URL=/api/v1` (relative). `README.md:51` says "Point `server.url` at a LAN backend only for local debug, **never for Play builds**", while `capacitor.config.ts:11-12` comments "Cross-origin WebView + relative /api/v1 will not auth."
- **Impact:** With no `server.url`, the SPA is served from Capacitor's `https://localhost` asset server; every relative `/api/v1/...` XHR resolves against that asset server and 404s — login and all data flows are dead in a Play build. The only way to make it work (set `server.url` to the backend origin) is exactly what the README forbids. There is no mobile‑specific web build with an absolute API base and no CapacitorHttp base URL configured, so the contradiction has no resolution in‑repo.
- **Fix:** Pick a model and enforce it: (a) ship `server.url = https://app.<prod-domain>` for store builds and rewrite the README, or (b) add a mobile web build that bakes an absolute `VITE_API_BASE_URL` and enable the CapacitorHttp plugin. Add a mobile CI assertion that the chosen config is present and correct.

### [M1-003] CI never syncs or builds the Android project — only greps one manifest line
- **Severity:** High
- **Category:** Gap
- **Location:** `.github/workflows/ci.yml:93-126`
- **Observation:** The `mobile` job runs `npm ci`, `npx tsc --noEmit` (over `capacitor.config.ts` only), and `grep -q 'android:allowBackup="false"' mobile/android/app/src/main/AndroidManifest.xml`. Comment `:93`: "lightweight mobile gate (no Android SDK / Gradle assemble)". The hand‑edited `AndroidManifest.xml`, `app/build.gradle`, `variables.gradle` are never compiled or checked against `capacitor.config.ts`.
- **Impact:** A malformed manifest, broken Gradle DSL, missing ProGuard keep rule, or drift between the Capacitor config and the native project ships undetected; first failure is a developer's local Android Studio build or a Play upload.
- **Fix:** Add a scheduled (nightly / on‑label) job on an Android‑SDK runner running `npx cap sync android` + `./gradlew :app:bundleRelease -x lint` so the native tree is actually exercised.

---

### [M1-004] Edge nginx `:80` published on all interfaces, no TLS, no HSTS; prod overlay adds no edge
- **Severity:** Medium
- **Category:** Security
- **Location:** `docker-compose.yml:249-256`; `nginx/default.conf:1-4,18-19,26-31`; `docker-compose.prod.yml` (no nginx override)
- **Observation:** `ports: - "${APP_PORT:-80}:80"` binds `0.0.0.0`. The conf listens `:80` only; header comment: "do not expose this :80 listener directly to browsers without an HTTPS edge." No `Strict-Transport-Security` anywhere. `docker-compose.prod.yml` overrides only `api/worker/beat/migrate` env — it adds no TLS terminator and no port restriction.
- **Impact:** On any host without a separately, correctly configured TLS edge, the whole app plus the JWT refresh cookie is served cleartext to the internet; `Secure`/`CSRF_COOKIE_SECURE` cookies then silently break. Nothing in the repo enforces or documents the edge contract precisely.
- **Fix:** Default the bind to `127.0.0.1:${APP_PORT}:80`; ship a real TLS overlay (or a documented edge contract), and add HSTS behind the existing `$fwd_proto = https` map.

### [M1-005] GitHub Actions not SHA-pinned (inconsistent with the repo's own pinned jobs)
- **Severity:** Medium
- **Category:** Security
- **Location:** `.github/workflows/ci.yml:36,77-78,100,104,138-141,176-186,251-256`; `codeql.yml:22-27`; `cd.yml:68`
- **Observation:** Most steps use mutable major tags — `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `github/codeql-action/{init,autobuild,analyze}@v3`, `docker/login-action@v3`. Meanwhile `ci.yml` `docker` and `load-harness` jobs and every `cd.yml` checkout are SHA‑pinned (`actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2`). `cd.yml:67` even comments "prefer digest pin in fork hardening" but doesn't.
- **Impact:** A compromised or force‑retagged third‑party action runs with the workflow `GITHUB_TOKEN` — and in `cd.yml` that token has `packages: write` to GHCR. This is the exact supply‑chain vector SHA pinning defends against.
- **Fix:** Pin every `uses:` to a full commit SHA with a trailing version comment; the `github-actions` Dependabot ecosystem is already configured to bump them.

### [M1-006] `ci.yml` has no `permissions:` block — jobs get the default broad `GITHUB_TOKEN`
- **Severity:** Medium
- **Category:** Security
- **Location:** `.github/workflows/ci.yml:1-8` (absent); cf. `codeql.yml:13-16`, `cd.yml:23-25` which both set one
- **Observation:** No `permissions:` at workflow or job scope in `ci.yml`.
- **Impact:** All CI jobs (which run `npm ci`, arbitrary test code, Playwright, `docker compose build` on PR branches) receive the repository‑default token scope, frequently `contents: write` / broad. More privilege than any CI job here needs.
- **Fix:** Add `permissions: contents: read` at the top of `ci.yml`; grant extra scopes per‑job only where genuinely required.

### [M1-007] CODEOWNERS has no default owner — mobile / infra / CI changes need no review
- **Severity:** Medium
- **Category:** Gap
- **Location:** `.github/CODEOWNERS:1-9`
- **Observation:** Only `web/src/pages/help/**`, `web/src/navigation/menu.ts`, i18n files, and four backend `help_*` files have owners. There is no `* @owner` catch‑all.
- **Impact:** With "require review from Code Owners" branch protection on, changes to `mobile/**`, `.github/workflows/**`, `docker-compose*.yml`, `nginx/**`, `backend/Dockerfile`, `scripts/**` merge with **no** required reviewer.
- **Fix:** Add `* @paurushk` plus explicit owners for `.github/`, `mobile/`, `docker-compose*.yml`, `nginx/`, `*/Dockerfile`.

### [M1-008] Deep links / App Links not wired despite `custom_url_scheme` being declared
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `mobile/android/app/src/main/res/values/strings.xml:6`; `mobile/android/app/src/main/AndroidManifest.xml:13-26`
- **Observation:** `<string name="custom_url_scheme">in.bizboard.app</string>` is defined, but `MainActivity` carries only the `MAIN`/`LAUNCHER` intent‑filter — no `VIEW` + `BROWSABLE` `<data android:scheme="in.bizboard.app">` and no `https` App Link with `android:autoVerify="true"`. `MainActivity.java` is an empty `BridgeActivity` with no `onNewIntent` handling.
- **Impact:** Passwordless / OAuth email links and push‑notification deep links cannot return into the app; tapping a Bizboard `https://` link on the device opens the browser rather than the shell — undermining the point of a WebView shell.
- **Fix:** Add the standard Capacitor custom‑scheme intent‑filter and an `autoVerify` App Links filter for the production host; handle `onNewIntent`.

### [M1-009] Push notifications documented but non-functional (no FCM / `google-services.json`)
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `mobile/README.md:74`; `mobile/package.json:18`; `mobile/android/app/build.gradle:47-54`
- **Observation:** README: "native shell registers a device token and PATCHes `/auth/me/` `{ pushToken }`". `@capacitor/push-notifications` is a dependency, but there is no `google-services.json`, no FCM project reference, and `build.gradle` only applies `com.google.gms.google-services` "if `servicesJSON.text`" (silently skipped otherwise, log line `:53`).
- **Impact:** `PushNotifications.register()` no‑ops on every build; a feature the README presents as working is dead on arrival.
- **Fix:** Add FCM provisioning + `google-services.json` to the release runbook, or drop the push claim and the dependency until it is wired.

### [M1-010] `capacitor.config.ts` pulls `server.url` from the generic `VITE_APP_ORIGIN` env var
- **Severity:** Medium
- **Category:** Security
- **Location:** `mobile/capacitor.config.ts:3`
- **Observation:** `const serverUrl = (process.env.CAPACITOR_SERVER_URL || process.env.VITE_APP_ORIGIN || '').trim();` — the value feeds `config.server.url`. `VITE_APP_ORIGIN` is a generic web‑build variable likely present in many shells.
- **Impact:** A `cap sync` run in any shell that happens to have `VITE_APP_ORIGIN` set (staging, a teammate's LAN IP, `localhost`) silently bakes a remote `server.url` into a Play AAB, turning the store build into a thin remote loader for the wrong environment — with no `allowNavigation` / `cleartext` guardrails set.
- **Fix:** Remove the `VITE_APP_ORIGIN` fallback; require an explicit `CAPACITOR_SERVER_URL`. Add a mobile CI check that `capacitor.config.*` contains no `server.url` (or only an allow‑listed prod origin).

### [M1-011] Production overlay builds images locally instead of promoting the CI-tested artifact
- **Severity:** Medium
- **Category:** Security
- **Location:** `docker-compose.prod.yml:12-16,30-41`; `scripts/pin_image_digests.sh:26-39`; `cd.yml:106-114`
- **Observation:** The prod overlay keeps `build: ./backend` and never sets `image:`. Digest pinning happens in CD but writes a *separate* `docker-compose.digest.yml` that ops must remember to `-f` in. Overlay comments say "prefer digest-pinned images" while the file does the opposite.
- **Impact:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml up` on a prod host rebuilds from local source against an unpinned base (`python:3.12-slim-bookworm`, `nginx:1.27-alpine`), bypassing the images CI actually built, tested and (should have) scanned.
- **Fix:** Make the prod overlay reference `ghcr.io/...@sha256:` (or `docker-compose.digest.yml` as canonical); keep `build:` only in a dev overlay.

### [M1-012] Uploaded media is not virus-scanned by default
- **Severity:** Medium
- **Category:** Security
- **Location:** `docker-compose.yml:226-231`; `backend/Dockerfile:5-7`
- **Observation:** `clamav` is a non‑default profile ("App fail-opens with alert if unreachable"). Dockerfile: "uploaded media (PDF/images) are stored as-is — no antivirus/clamav scan in this image."
- **Impact:** A tenant uploads a malicious PDF/image as a purchase bill; it is stored unscanned and later served (via the `X-Accel-Redirect` `/media/` path) to staff or other users — malware distribution through an accounting product. Fail‑open means an unreachable scanner does not block the upload either.
- **Fix:** Include clamav in the standard prod stack and fail **closed** on scanner unavailability in production.

### [M1-013] `./backups/` is not git-ignored and dumps are unencrypted
- **Severity:** Medium
- **Category:** Security
- **Location:** `scripts/backup.sh:5-7`; `docker-compose.yml:158-161`; repo `.gitignore` (no `backups/` entry)
- **Observation:** `backup` writes `/backups/bizboard-<ts>.sql.gz` to the host bind mount `./backups`; `.gitignore` has no `backups/` rule; dumps are plain gzip.
- **Impact:** A full multi‑tenant DB dump (PII, GSTINs, financial records) sits unencrypted in the working tree and can be `git add .`‑ed by accident; also readable by any local host user.
- **Fix:** Add `backups/` to `.gitignore`; encrypt dumps (age/gpg) or push to object storage with SSE; tighten file perms in `backup.sh`.

### [M1-014] No container / IaC image scanning in CI
- **Severity:** Medium
- **Category:** Security
- **Location:** `.github/workflows/ci.yml:203-216` (`docker` job); `codeql.yml:17-20`
- **Observation:** The `docker` job runs only `docker compose config` + `docker compose build`. CodeQL matrix is `javascript-typescript` and `python` only. No Trivy/Grype/Scout image scan, no hadolint, no compose/IaC scan. `pip-audit` / `npm audit` (`ci.yml:49,91`) cover language deps only.
- **Impact:** Vulnerable OS packages baked into `bizboard-api` / `bizboard-web` and Dockerfile anti‑patterns are never surfaced before deploy.
- **Fix:** Add a Trivy (or Docker Scout) scan of the built images with a severity gate, plus hadolint on both Dockerfiles.

### [M1-015] No gzip/brotli on either nginx layer
- **Severity:** Medium
- **Category:** Performance
- **Location:** `web/nginx.conf:1-47`; `nginx/default.conf:18-86`
- **Observation:** Neither config enables `gzip`, `gzip_static`, or brotli.
- **Impact:** The React + MUI + query vendor bundles (`assets/mui-vendor-*.js`, `react-vendor-*.js`, hundreds of KB each) are served uncompressed from both the inner static nginx and the edge proxy — roughly 3–4× more bytes on every cold load, worst on the mobile shell's first run over mobile data.
- **Fix:** `gzip on; gzip_comp_level 5; gzip_min_length 1024; gzip_types text/css application/javascript application/json image/svg+xml application/manifest+json;` — ideally precompress at build time and enable `gzip_static on`.

### [M1-016] `restore.sh` is not idempotent — restores into the existing schema
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `scripts/restore.sh:17-20`
- **Observation:** Comment says "recreate public schema carefully", but the script just runs `gunzip -c "$SRC" | psql -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1` — no `DROP SCHEMA`, no `--clean`, no `pg_terminate_backend`.
- **Impact:** A restore drill against anything but an empty database aborts on the first `CREATE TABLE` / duplicate‑key conflict (`ON_ERROR_STOP=1`), leaving a half‑restored DB — precisely during an incident when RTO matters.
- **Fix:** Use `pg_dump -Fc` + `pg_restore --clean --if-exists`, or `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` after terminating connections, before the load.

### [M1-017] Release build has no signing config and a frozen `versionCode`
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `mobile/android/app/build.gradle:5-12,19-24`
- **Observation:** `buildTypes.release` sets `minifyEnabled true` + `proguardFiles` but no `signingConfig`. `defaultConfig` hard‑codes `versionCode 1` / `versionName "1.0"`.
- **Impact:** `./gradlew assembleRelease` (any CI or non‑Android‑Studio path) produces an **unsigned** APK that will not install; and every AAB built keeps `versionCode 1`, which Play rejects after the first upload. The release process is undocumented beyond "use the Studio wizard" (`README.md:40`).
- **Fix:** Add a `release` signing config sourced from keystore secrets/env, drive `versionCode` from CI (e.g. `git rev-list --count HEAD`), and document the `bundleRelease` command.

---

### [M1-018] `minifyEnabled true` with an empty ProGuard file and no `mapping.txt` retention
- **Severity:** Low
- **Category:** Improvement
- **Location:** `mobile/android/app/proguard-rules.pro:1-22` (all comments); `mobile/android/app/build.gradle:20-23`
- **Observation:** Release minification is on, `proguard-rules.pro` has zero active rules, `-keepattributes SourceFile,LineNumberTable` is commented out, and no CI step archives the R8 `mapping.txt`.
- **Impact:** Capacitor/AndroidX consumer rules keep the bridge alive, but any future `@JavascriptInterface` or reflection breaks silently in release only, and release crash stack traces are unsymbolicated with no mapping file to de‑obfuscate them.
- **Fix:** Uncomment the line‑number keep attributes, add app‑specific keeps as plugins are added, and upload `mapping.txt` as a build artifact / to Play.

### [M1-019] SPA `try_files … /index.html` returns HTTP 200 for missing assets
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/nginx.conf:34-36`
- **Observation:** `location / { try_files $uri $uri/ /index.html; }` with no carve‑out for `/assets/`.
- **Impact:** A mistyped or stale `/assets/foo-hash.js` returns the HTML shell with status 200; the browser fails with a confusing MIME/parse error instead of a clean 404, and broken deploys (missing chunks) are masked.
- **Fix:** Add `location /assets/ { try_files $uri =404; }` (and similar for other build‑output dirs) above the SPA fallback.

### [M1-020] `server_tokens` left on — nginx version disclosed
- **Severity:** Low
- **Category:** Security
- **Location:** `web/nginx.conf:1-6`; `nginx/default.conf:18-24`
- **Observation:** Neither `server` block sets `server_tokens off;`.
- **Impact:** The exact nginx version is advertised in every `Server:` response header and on error pages, easing targeted CVE probing.
- **Fix:** `server_tokens off;` in both configs (http or server scope).

### [M1-021] `/media/` location drops server-level CSP and Referrer-Policy
- **Severity:** Low
- **Category:** Security
- **Location:** `nginx/default.conf:26-31` (server‑level headers) vs `:73-78` (`location /media/`)
- **Observation:** nginx `add_header` does not merge — a `location` with any `add_header` replaces the inherited set. `/media/` re‑adds `X-Content-Type-Options` and `X-Frame-Options` but not the server‑level `Content-Security-Policy` or `Referrer-Policy`. Any future `location` that adds a header will silently lose all four.
- **Impact:** Media responses (attachments streamed via `X-Accel-Redirect`) ship without CSP/Referrer‑Policy; the pattern is a latent foot‑gun for every new location block.
- **Fix:** Move the four headers into `snippets/security-headers.conf` and `include` it in every `location`, or rely on a single server‑level block and add nothing per‑location.

### [M1-022] FileProvider paths expose the whole external-files and cache dirs
- **Severity:** Low
- **Category:** Security
- **Location:** `mobile/android/app/src/main/res/xml/file_paths.xml:3-4`
- **Observation:** `<external-files-path name="my_images" path="." />` and `<cache-path name="my_cache_images" path="." />` — root (`.`) of each directory is shareable through the FileProvider.
- **Impact:** Any component that receives a granted `content://…fileprovider/…` URI can be pointed at arbitrary files anywhere under the app's external‑files / cache trees, not just an intended `shared/` sub‑folder. Provider is `exported="false"` with temporary grants, limiting blast radius.
- **Fix:** Scope each path to a dedicated subdirectory (e.g. `path="shared/"`) and write exports there.

### [M1-023] Dead / stale scaffold files in the Android project
- **Severity:** Low
- **Category:** Improvement
- **Location:** `mobile/android/app/src/main/res/layout/activity_main.xml`; `mobile/android/app/src/test/java/com/getcapacitor/myapp/ExampleUnitTest.java`; `mobile/android/variables.gradle:11`
- **Observation:** `activity_main.xml` is a bare `<WebView>` layout that `BridgeActivity` never inflates. `ExampleUnitTest.java` sits under the template package `com.getcapacitor.myapp` (app id is `in.bizboard.app`). `androidxWebkitVersion = '1.9.0'` is declared but no `androidx.webkit` dependency references it.
- **Impact:** Confusing to readers; the layout implies a custom WebView that does not exist.
- **Fix:** Delete the unused layout and template test (or move the test to `in.bizboard.app`); drop the unused version var or wire the dependency.

### [M1-024] `minSdkVersion = 22` (Android 5.1, 2015)
- **Severity:** Low
- **Category:** Security
- **Location:** `mobile/android/variables.gradle:2`
- **Observation:** Capacitor 6 default min is 22.
- **Impact:** System WebView on API 22–23 devices lacks TLS 1.3 and modern JS/CSP features, and receives no OS security patches — a weak floor for an app that handles financial data and auth cookies.
- **Fix:** Raise to 24 (or 26) unless a concrete device requirement forces 22.

### [M1-025] Gradle wrapper has no `distributionSha256Sum`
- **Severity:** Low
- **Category:** Security
- **Location:** `mobile/android/gradle/wrapper/gradle-wrapper.properties:3-6`
- **Observation:** `distributionUrl` points at `gradle-8.2.1-all.zip`; `validateDistributionUrl=true` validates only the URL host, and there is no `distributionSha256Sum`.
- **Impact:** A tampered or MITM'd Gradle distribution is executed during the build with no integrity check.
- **Fix:** Add the official `distributionSha256Sum` for 8.2.1 (and update it on every wrapper bump).

### [M1-026] `k6_slo.js` may run its SLO scenarios unauthenticated
- **Severity:** Low
- **Category:** Bug
- **Location:** `load/k6_slo.js:40-49,51-63,65-79`
- **Observation:** `authHeaders()` POSTs to `/api/v1/auth/login/` and then returns only `{ "Content-Type": "application/json" }`. Auth survives subsequent requests solely via k6's implicit per‑VU cookie jar; no bearer token is captured from the login body.
- **Impact:** If the backend issues a bearer/JWT token in the response body (not a cookie), every `listInvoices` / `completeDraft` call runs unauthenticated. The checks only assert `r.status < 500`, so 401/403 responses "pass" and the p95 thresholds (`invoice_list < 2000ms`, `invoice_complete < 800ms`) measure auth‑rejection latency — a green run that proves nothing.
- **Fix:** Capture the token from the login response and send `Authorization: Bearer …`, or assert `status === 200` in the checks so an unauthenticated run fails loudly.

### [M1-027] CI has no `timeout-minutes` and no `concurrency` cancellation
- **Severity:** Low
- **Category:** Improvement
- **Location:** `.github/workflows/ci.yml:1-8` and every job
- **Observation:** No `timeout-minutes:` on any job; no `concurrency: { group: …, cancel-in-progress: true }`.
- **Impact:** A hung Playwright / pytest / `docker compose build` runs up to the 6‑hour ceiling burning minutes; rapid pushes to a branch run full duplicate pipelines instead of superseding.
- **Fix:** Add a per‑job `timeout-minutes` (e.g. 20–30) and a workflow‑level `concurrency` group keyed on ref with `cancel-in-progress: true`.

### [M1-028] Three divergent env templates
- **Severity:** Low
- **Category:** Improvement
- **Location:** `.env.example`, `backend/.env.example`, `.env.production.example`
- **Observation:** `backend/.env.example` still documents DeepSeek (`deepseek-vl2`, `DEEPSEEK_BASE_URL`) and omits `REDIS_PASSWORD` entirely; `.env.example` uses `LLM_PROVIDER=openai` and requires `REDIS_PASSWORD`. `JWT_REFRESH_DAYS` is `7` in `.env.example` vs `2` in `.env.production.example`. Redis auth is only mentioned in the root templates.
- **Impact:** Copying `backend/.env.example` for a Docker run yields a config missing the Redis password the compose file demands (`redis-server --requirepass ${REDIS_PASSWORD:?}`), so the stack fails to start; contributors get inconsistent guidance.
- **Fix:** Consolidate to one canonical template per surface, cross‑reference them, and delete stale provider docs.

### [M1-029] `android/build.gradle` uses the removed `rootProject.buildDir` property
- **Severity:** Low
- **Category:** Bug
- **Location:** `mobile/android/build.gradle:27-29`
- **Observation:** `task clean(type: Delete) { delete rootProject.buildDir }`. `Project.buildDir` is deprecated in Gradle 8 and removed in Gradle 9.
- **Impact:** `./gradlew clean` will fail once the wrapper is bumped to 9.x (which the SDK‑35 upgrade in M1‑001 will require).
- **Fix:** `delete rootProject.layout.buildDirectory`.

### [M1-030] CD rebuilds images from source and base `FROM` tags are not digest-pinned
- **Severity:** Low
- **Category:** Improvement
- **Location:** `.github/workflows/cd.yml:78-105`; `backend/Dockerfile:3`; `web/Dockerfile:1,35`
- **Observation:** `push-images` runs fresh `docker build ./backend` / `./web` rather than promoting the image the CI `docker` job built and validated. Base images are floating tags (`python:3.12-slim-bookworm`, `node:22-alpine`, `nginx:1.27-alpine`). Dockerfile comments acknowledge "CI should further pin by digest (FROM …@sha256:…)" but it isn't done.
- **Impact:** The pushed image can differ from the tested one if an upstream base moved between the CI and CD runs; reproducibility depends entirely on the post‑hoc digest file.
- **Fix:** Either build once in CI and `docker save`/load or push from that job, or pin `FROM` lines by digest and rebuild deterministically. Renovate/Dependabot `docker` ecosystem is already configured to bump digests.

### [M1-031] Cordova `config.xml` ships `<access origin="*" />`
- **Severity:** Low
- **Category:** Security
- **Location:** `mobile/android/app/src/main/res/xml/config.xml:3`
- **Observation:** `<access origin="*" />` — the Cordova network whitelist wide open. The file is generated and git‑ignored (`mobile/android/.gitignore:101`); `capacitor.plugins.json` is currently `[]`.
- **Impact:** Inert today (no Cordova‑based plugins), but the moment a Cordova‑bridged plugin is added this whitelist becomes live and unrestricted, and because the file regenerates silently it is easy to miss.
- **Fix:** Constrain the generated `<access>`/`<allow-navigation>` via `cordova` config in `capacitor.config.ts`, or add a CI check.

### [M1-032] Golden e2e (merge gate) runs the Django dev server, not the prod stack
- **Severity:** Low
- **Category:** Gap
- **Location:** `.github/workflows/ci.yml:148-198`; `web/playwright.golden.config.ts:36-48`
- **Observation:** `e2e-golden` (the required golden path) starts the backend with `python manage.py runserver 127.0.0.1:8000 --noreload`, `DJANGO_SETTINGS_MODULE=config.settings`, `DJANGO_DEBUG` unset.
- **Impact:** gunicorn/WSGI behavior, prod middleware, static handling, and `DEBUG=False` error paths are never exercised by the gate; a regression that only manifests under the real server config passes CI.
- **Fix:** Run the golden path against the built `bizboard-api` image (or at least gunicorn with `DJANGO_DEBUG=0`) in a periodic job.

### [M1-033] `backend/Dockerfile` ends on `USER root` with no unprivileged fallback
- **Severity:** Low
- **Category:** Security
- **Location:** `backend/Dockerfile:25-32`; `backend/docker-entrypoint.sh:6-10`; `docker-compose.yml:215-220`
- **Observation:** The image's final `USER` is `root`; privilege drop to `app` happens only inside `docker-entrypoint.sh` via `setpriv`. Any `--entrypoint` override skips it — the `test` compose service already does exactly this (`entrypoint: ["/bin/sh","-lc","pip install … && exec \"$@\""]`), so its runtime `pip install` runs as root.
- **Impact:** `docker compose run --entrypoint … api`, debugging shells, and the `test` profile all run as root; a container escape or a malicious dependency install has root in the container.
- **Fix:** Keep the entrypoint chown‑then‑drop, but have it `exec` into a non‑root default, and/or add `user: "app"` to compose services that don't need the chown step; run the `test` install as `app`.

---

### [M1-034] `.env` present at repo root (git-ignored, untracked)
- **Severity:** Info
- **Category:** Security
- **Location:** `E:\Bizboard\.env` (2413 bytes); `.gitignore` line `.env`
- **Observation:** A populated local `.env` sits at the repo root. `git ls-files .env` returns nothing and `git check-ignore .env` matches, so it is not tracked.
- **Impact:** None currently. Risk is a future `git add -f` or a tooling change that stops honoring the ignore.
- **Fix:** Keep as‑is; consider a pre‑commit hook that blocks committing `.env`.

### [M1-035] Dev `.env.example` ships DEBUG + OTP echo on with placeholder secrets
- **Severity:** Info
- **Category:** Security
- **Location:** `.env.example:1-3,23-25`; `backend/.env.example:1-9`
- **Observation:** `DJANGO_ENV=development`, `DJANGO_DEBUG=true`, `OTP_DEBUG_ECHO=1`, `DJANGO_SECRET_KEY=dev-only-change-me-…`, `OTP_PEPPER=dev-only-otp-pepper-change-me`, `SANDBOX_WEBHOOK_SECRET=dev-sandbox-webhook-secret-change-me`. All clearly non‑secret placeholders; `.env.production.example` correctly flips these off.
- **Impact:** Acceptable for a local template; risk is only if someone copies `.env.example` onto a shared/staging host.
- **Fix:** Add a one‑line banner: "local only — never deploy this file to any shared host".

### [M1-036] Postgres RLS defaults off, including in the production overlay
- **Severity:** Info
- **Category:** Security
- **Location:** `docker-compose.yml:44,64-66,94,126`; `docker-compose.prod.yml` (no `POSTGRES_RLS_ENABLED`); `.env.production.example` (absent)
- **Observation:** `POSTGRES_RLS_ENABLED: ${POSTGRES_RLS_ENABLED:-0}` everywhere; the prod overlay and prod env template never set it. Comments describe RLS as Wave 17A opt‑in ("default prod still off"). A dedicated `postgres-rls` CI job exists (`ci.yml:227-266`).
- **Impact:** Tenant isolation in production rests entirely on application‑layer query scoping; a missed `.filter(company=…)` is not caught by a database backstop. This is an accepted project decision — flagged here so the infra posture is explicit.
- **Fix:** Track a decision to enable `POSTGRES_RLS_ENABLED=1` in prod once the RLS policies are proven, and note it in `.env.production.example`.

### [M1-037] `ruff.toml` selects a minimal rule set — no security/bugbear lint
- **Severity:** Info
- **Category:** Improvement
- **Location:** `backend/ruff.toml:6-8`
- **Observation:** `select = ["E9", "F63", "F7", "F82", "F401", "F811"]` — syntax errors, a few pyflakes checks, unused imports/redefinitions. No `B` (bugbear), `S` (flake8‑bandit), `UP`, etc. Comment: "expand rules gradually."
- **Impact:** `ruff check .` in CI catches almost nothing beyond import hygiene; SQL‑injection‑shaped patterns, `assert` in prod code, hardcoded‑tmp, etc. are not flagged.
- **Fix:** Incrementally add `B` and `S` with targeted `ignore`s.

### [M1-038] Dependabot has no PR limits or grouping
- **Severity:** Info
- **Category:** Improvement
- **Location:** `.github/dependabot.yml:1-27`
- **Observation:** Six ecosystems (pip, npm×2 [`/web`, `/mobile`], github‑actions, docker×2), all `interval: weekly`, no `open-pull-requests-limit`, no `groups`.
- **Impact:** Potential weekly flood of individual PRs (default cap is 5 per ecosystem = up to 30 open), each triggering the full CI matrix.
- **Fix:** Add `groups:` (e.g. group minor/patch, group dev‑deps) and set `open-pull-requests-limit` per ecosystem.

---

# Deep code review — F3: Frontend reporting / settings / inventory / insights / help / phase / components

**Scope reviewed (every line):** `web/src/pages/reports/**` (19 pages; note most are thin re-exports of `web/src/pages/phase/*`), `web/src/pages/inventory/**`, `web/src/pages/settings/**` (15), `web/src/pages/insights/**` + `web/src/components/insights/**`, `web/src/pages/phase/**` (the real implementations behind many reports/settings/inventory nav entries), `web/src/pages/payroll/**`, `web/src/pages/manufacturing/**`, `web/src/pages/crm/**`, `web/src/pages/help/**`, `web/src/pages/setup/SetupWizardPage.tsx`, and `web/src/components/**` except `components/billing/**` and `components/insights/**` (which were still read for cross-references). Test files were read for intent. Prior review docs (`DEEP_CODE_REVIEW_2026-09-02.md`, `UX_*`, `COMPREHENSIVE_CODE_REVIEW_FINDINGS.md`) were skimmed to avoid re-reporting; every finding below was re-verified against current code. No `dangerouslySetInnerHTML` / `innerHTML` / `eval` exists anywhere in scope — `HelpRichText` renders via React nodes, so the help/FAQ system has no XSS via rich text.

## Severity counts

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 4 |
| Medium | 41 |
| Low | 23 |
| Info | 6 |
| **Total** | **74** |

---

### [F3-001] Client-built items CSV export has no formula-injection guard
- **Severity:** High
- **Category:** Security
- **Location:** `web/src/pages/inventory/ProductsPage.tsx:56` (`csvEscape`), used at `115-156` (`exportCsv`)
- **Observation:** `function csvEscape(value) { return `"${value.replace(/"/g, '""')}"`; }`. The export is built entirely client-side from product `name`, `sku`, `unitName`, custom-field values, etc., joined into a `Blob` and downloaded as `items.csv`. Only quotes are doubled; values beginning with `=`, `+`, `-`, `@`, tab or CR are **not** neutralised.
- **Impact:** A product named `=HYPERLINK("http://evil","claim refund")` or `=cmd|'/c calc'!A1` (all user-controllable via ItemFormDialog / imports) executes as a formula when a shopkeeper opens the exported CSV in Excel / LibreOffice / Google Sheets. Server-generated exports (`exportReport`) are not affected; this one path is.
- **Fix:** Prefix any cell whose first char is in `=+-@\t\r` with a single quote (or a leading space), matching whatever the backend CSV writer does. Ideally route this export through the same server endpoint as the other registers.

### [F3-002] Tally migration commit has no confirmation and no undo
- **Severity:** High
- **Category:** Broken-flow
- **Location:** `web/src/pages/settings/TallyMigrationPage.tsx:152-164` (`commit`), rendered at `342-348`
- **Observation:** `<Button variant="contained" ... onClick={() => commit.mutate()}>` fires `commitTallyImport(syncRunId)` directly. The commit bulk-creates customers, suppliers, products, **opening AR/AP balances and stock movements** (see the summary rendered at `353-360`). There is no `window.confirm`, no "this cannot be undone" copy, and — unlike `ImportPage` which has `voidImport` — no reversal path once `committed` is set (the whole UI just locks via `disabled={committed}`).
- **Impact:** One misclick, or committing the wrong uploaded file, seeds the tenant's opening balances and stock with garbage and there is no in-app way back. This is the single highest-impact bulk write in the settings area.
- **Fix:** Add a confirm dialog summarising counts ("This will create N customers, M products and opening balances totalling ₹X — cannot be undone from the app"). Add a `voidTallyImport(syncRunId)` action mirroring `ImportPage`.

### [F3-003] Payment-link refund is a one-click irreversible money movement
- **Severity:** High
- **Category:** Broken-flow
- **Location:** `web/src/pages/phase/BankingPhasePages.tsx:301-310` (`refund`), button at `376-380`
- **Observation:** `{r.status === 'PAID' ? (<Button ... onClick={() => refund.mutate(Number(r.id))}>Refund</Button>) : null}`. The mutation looks up the captured gateway payment and calls `api.refundGatewayPayment(...)`. No confirmation dialog, no amount echo, no success toast.
- **Impact:** A single stray click on a PAID row issues a real refund to the customer's card/UPI. Irreversible; no "are you sure ₹X to <customer>?" step.
- **Fix:** Gate behind `ConfirmDialog` showing amount + payer + link number; disable the button while `refund.isPending` (currently it is, but the confirm is the missing piece).

### [F3-004] Bulk-accept GSTR-2B and offline IMS import apply ITC decisions with no confirmation / preview
- **Severity:** High
- **Category:** Data-integrity
- **Location:** `web/src/pages/reports/Gstr2bPage.tsx:95-99` (`bulkMutation`, button `240-242`) and `133-137` + `158-166` (`importMutation` / `onPickFile`, button `243-256`)
- **Observation:** "Bulk accept exact" calls `bulkAcceptExact(period)` on click with no confirm. "Import offline" reads a user-chosen JSON file, `JSON.parse`es it and immediately `importImsOffline(payload, true)` — the `true` applies the actions; there is no diff/preview of what the file will change.
- **Impact:** Both bulk-mutate ITC eligibility / IMS action state, which feeds GSTR-3B ITC claims (see F3-030). A wrong file or an accidental bulk-accept silently changes what the business claims as input tax credit. The adjacent `Alert` "no auto-accept" is not a substitute for a confirm.
- **Fix:** Confirm dialog with the count of rows affected for bulk-accept. For the offline import, show a summary ("this file sets N rows to ACCEPT, M to REJECT — apply?") before calling with `apply=true`.

### [F3-005] Many phase-page destructive / financial actions fire with no confirmation
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/phase/JournalsPage.tsx:101,105` (Post / Reverse journal); `web/src/pages/phase/AccountingExtraPages.tsx:69` (Disable accounting); `web/src/pages/phase/PeriodsPage.tsx:77` (Close a single accounting period); `web/src/pages/phase/BankingPhasePages.tsx:487-490` (Commit bank statement), `242-246` (Cancel a COMPLETED stock transfer); `web/src/pages/phase/InventoryPhasePages.tsx:238-246` (Complete / Cancel transfer), `485` (serial state transition incl. → SCRAPPED); `web/src/pages/phase/FixedAssetsPage.tsx:76` (Dispose asset)
- **Observation:** Each is `onClick={() => someMutation.mutate(id)}` with no `window.confirm` / `ConfirmDialog`. Posting/reversing a journal writes to the GL; closing a period locks it; disabling accounting stops GL projections; committing a bank statement posts transactions; cancelling a completed transfer reverses stock; disposing an asset posts a disposal journal; marking a serial SCRAPPED is terminal.
- **Impact:** Accidental clicks cause ledger/stock/period changes that need another counter-entry to fix. `WorkOrdersPage` and `PayRunsPage` (also MVP modules) *do* confirm these — the phase pages are inconsistent.
- **Fix:** Wrap each in `ConfirmDialog` (already imported/used elsewhere). "Close FY" in the same files already does this via `window.confirm`; extend the pattern.

### [F3-006] Numeric non-money report columns are rendered through the currency formatter
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/reports/SalesReportPage.tsx:129-133` and identical code in `web/src/pages/reports/PurchaseReportPage.tsx:130-134`
- **Observation:** `{!/(^id$|Id$)/.test(key) && (typeof value === 'number' || (typeof value === 'string' && /total|amount|tax/i.test(key))) ? formatMoney(value) : String(value ?? '—')}` — any column whose value is a JS `number` (and is not an `id`) is money-formatted.
- **Impact:** `hsn_code` `998314` renders as `₹9,98,314.00`; `gst_rate` `18` renders as `₹18.00`; `quantity` `5` renders as `₹5.00`. The register is the primary sales/purchase report and its non-money numeric columns are wrong.
- **Fix:** Whitelist money columns by key (`grand_total`, `taxable_amount`, `*gst_amount`, `total_tax`, `net_total`, …) instead of "any number". A `MONEY_KEYS` set already half-exists as `formatColumnHeader`'s `customMap`.

### [F3-007] GSTR-3B "Net GST payable" headline is computed client-side and clamps away ITC surplus
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/reports/GstReturnPage.tsx:202-253`
- **Observation:** `totalTaxLiability = toNumber(cgst)+toNumber(sgst)+toNumber(igst)`; `netGstPayable = Math.max(0, totalTaxLiability - totalItc)`, rendered as an `<h4>` in `error.main`/`success.main`. All arithmetic is on the client from `query.data.totals` / `query.data.itc`.
- **Impact:** (1) If the backend also computes a net-payable figure, the two can diverge (rounding, head-wise netting rules). (2) `Math.max(0, …)` hides the case where ITC exceeds liability — a business carrying forward a credit balance sees "₹0.00" instead of its carry-forward. This is the number the user acts on when paying the government.
- **Fix:** Prefer a backend-computed `netPayable` / `creditCarryForward` field; only fall back to client arithmetic, and show negative (credit) explicitly rather than clamping.

### [F3-008] Five GST-return pages are non-functional stubs exposed in nav
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `web/src/pages/reports/GstReturnPage.tsx:314-387` (`GstStubPage` → `Gstr4ReportPage`, `Cmp08ReportPage`, `Gstr6ReportPage`, `Gstr7ReportPage`, `Gstr8ReportPage`)
- **Observation:** The stub renders a period picker, a warning `Alert` (`gstHonesty.stubTitle`/`stubBody`) and a `<details>` dumping `JSON.stringify(query.data)`. For `gstr4`/`cmp08` the query is `enabled: isServerReturn` (false) so it never even fetches — the page is a warning banner and a date field.
- **Impact:** Composition dealers (GSTR-4/CMP-08) and ISD/TDS/TCS filers (GSTR-6/7/8) land on pages that do nothing. `faqContent.tsx:1179` acknowledges "GSTR-6/7/8 screens are stubs" — but they are still full nav destinations.
- **Fix:** Either hide these routes behind a feature flag until implemented, or make the stub state unmistakable (single centered "Not available yet — file on the portal" with a portal link, no period picker / JSON dump).

### [F3-009] "Invoice Templates" settings page offers exactly one hard-coded template
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `web/src/pages/settings/InvoiceTemplatesPage.tsx` (whole file; `LAYOUT_LEGEND` at `21-28` is static prose)
- **Observation:** The page shows a fixed "GST Tax Invoice (A4)" card and a static bullet list of what's on the PDF. The only editable thing is the Terms & Conditions textarea (`updateCompany({ invoiceTerms })`). No template selection, thermal/A5 option, logo upload, or branding.
- **Impact:** Nav promises template management; the page delivers a terms editor. Users expecting to pick a layout have no control.
- **Fix:** Rename to "Invoice terms & footer" until real templates exist, or wire up template selection.

### [F3-010] ItemFormDialog: partial opening-stock failure with no idempotency → duplicate stock on retry
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/inventory/ItemFormDialog.tsx:379-427`
- **Observation:** `save` first `await createProduct(payload)` then loops `await createOpeningStock({...})` per lot / per serial-warehouse group. No `idempotencyKey` is passed to `createOpeningStock`. On failure the catch throws `"Item saved, but opening stock failed: …"` — the product now exists with a subset of lots posted.
- **Impact:** The user sees the error and clicks "Save item" again → `updateProduct` is a no-op but the opening-stock loop re-runs and **doubles** the quantity for lots that already succeeded on the first attempt.
- **Fix:** Pass a stable `idempotencyKey` per lot (`opening-${saved.id}-${lot.warehouseId}-${lot.batchNo}`); on the retry path skip lots already recorded, or do the whole "create product + opening stock" server-side in one transactional endpoint.

### [F3-011] ItemFormDialog discards a long multi-tab form on any close, with no guard
- **Severity:** Medium
- **Category:** UX/UI
- **Location:** `web/src/pages/inventory/ItemFormDialog.tsx:457` (`<Dialog ... onClose={onClose}>`)
- **Observation:** Backdrop click / Esc / Cancel calls `onClose` which resets everything. The dialog has 4 tabs (basic / stock / pricing / custom) with opening lots and serials. `UnsavedChangesGuard` is not used and there is no dirty check.
- **Impact:** A shopkeeper who fills two tabs and taps outside the dialog loses all of it silently.
- **Fix:** Track a `dirty` flag; on `onClose` while dirty, confirm before discarding (or make backdrop non-dismissing: `disableEscapeKeyDown` + only close via explicit Cancel with a confirm).

### [F3-012] ItemFormDialog: HSN picker can set a GST rate outside the Select's options
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/inventory/ItemFormDialog.tsx:1068-1074` (HSN result → `setForm({... gstRate: rate ? String(rate) : ...})`) vs the GST-rate `<TextField select>` at `946-952` populated from `GST_RATE_OPTIONS`
- **Observation:** The HSN search result's `gstRate` is stored verbatim as a string. The pricing tab's GST-rate control is a MUI `select` whose `MenuItem`s come from `GST_RATE_OPTIONS` (e.g. 0/5/12/18/28). If the HSN returns a rate not in that list (or a formatted value), `value` matches no `MenuItem`.
- **Impact:** MUI logs an out-of-range value warning and the GST-rate field renders blank, while `save` still submits `normalizeGstRate(Number(form.gstRate))`. The user sees an empty rate box after picking an HSN.
- **Fix:** Fold the picked rate into the options list (same pattern already used for `baseUnitOptions`/`alternateUnitOptions`), or snap it to the nearest allowed slab.

### [F3-013] ItemFormDialog: barcode value is interpolated into a popup's raw HTML
- **Severity:** Medium
- **Category:** Security
- **Location:** `web/src/pages/inventory/ItemFormDialog.tsx:329-331` (`printBarcode`)
- **Observation:** `win.document.write(`<html><body ...><img src="${url}" alt="${code}" /><div ...>${code}</div></body></html>`)` where `code = form.barcode.trim()` (user-entered).
- **Impact:** A barcode value like `"><img src=x onerror=alert(1)>` executes script in the print popup (`about:blank`, null origin). Limited blast radius (no app data in that window) but it is a live script-injection sink driven by a text field.
- **Fix:** Build the popup with DOM APIs (`createElement`, `img.alt = code`, `div.textContent = code`) instead of string concatenation, or HTML-escape `code`.

### [F3-014] Settings forms re-`reset()` from the query cache on every refetch, wiping unsaved edits
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/settings/CompanySettingsPage.tsx:55-77`; `web/src/pages/settings/GstSettingsPage.tsx:87-111`; `web/src/pages/settings/AiSettingsPage.tsx:43-55`; `web/src/pages/settings/ItemSettingsPage.tsx:92-95`; `web/src/pages/settings/InvoiceTemplatesPage.tsx:44-48`; `web/src/pages/inventory/StockAdjustmentPage.tsx:88-91`; `web/src/pages/setup/SetupWizardPage.tsx:90-106`
- **Observation:** Each has `useEffect(() => { if (query.data) reset({...fromServer}) }, [query.data, reset])` (or `setForm`/`setDefs`). React Query refetches `['company']` on window refocus / reconnect by default; the returned object is a new reference, so the effect fires and overwrites the form with server values.
- **Impact:** User edits a settings field, tabs away to check something, tabs back → their edit is gone with no warning. `StockAdjustmentPage:88` additionally re-forces `warehouse` to the default whenever `warehouses.data` re-resolves, discarding a manually chosen godown.
- **Fix:** Only seed the form once (`useEffect(..., [])` guarded by an `initialisedRef`, or `reset` keyed on `query.data?.id` / `dataUpdatedAt` of the *first* load), or make these queries `staleTime: Infinity` / `refetchOnWindowFocus: false`.

### [F3-015] `UnsavedChangesGuard` exists but is not applied to settings/inventory forms, and does not cover tab close
- **Severity:** Medium
- **Category:** Gap
- **Location:** `web/src/components/UnsavedChangesGuard.tsx` (whole file); absent from `CompanySettingsPage`, `GstSettingsPage`, `AiSettingsPage`, `ItemSettingsPage`, `InvoiceTemplatesPage`, `ItemFormDialog`, `UnitsSettingsPage`, `PriceListsPage` editor
- **Observation:** The guard uses `useBlocker(when)` — react-router in-app navigation only. It has no `beforeunload` handler, and no settings form imports it.
- **Impact:** Navigating away from a half-edited GST / company / custom-fields form (or reloading / closing the tab) silently drops the changes.
- **Fix:** Add a `dirty` boolean to each form and render `<UnsavedChangesGuard when={dirty} />`; add a `beforeunload` listener inside the guard for the hard-navigation case.

### [F3-016] `phaseShared.DataTable` renders every row — no virtualization or pagination anywhere it is used
- **Severity:** Medium
- **Category:** Performance
- **Location:** `web/src/pages/phase/phaseShared.tsx:78-121`; consumers include `CashBookPage`, `TrialBalancePage`/`ProfitAndLossPage`/`BalanceSheetPage` (`AccountingReportsPages.tsx`), `JournalsPage`, all of `BankingPhasePages`/`InventoryPhasePages`/`AccountingExtraPages`, `StockCountPage`
- **Observation:** `DataTable` maps `rows` straight into `<TableRow>`s. None of the callers paginate or cap. `CashBookPage` / trial balance / journals can each be thousands of rows for a full year.
- **Impact:** Large tables freeze the tab on render and on every re-render (the row-mapping in `AccountingReportsPages.tsx:95-103` is also unmemoized).
- **Fix:** Give `DataTable` an optional `VirtualizedTable` mode (the component and pattern already exist — see `StatutoryEventsPage`/`Gstr2bPage`), or add server pagination to the underlying report endpoints.

### [F3-017] Report / ledger tables that are not phase pages also lack virtualization
- **Severity:** Medium
- **Category:** Performance
- **Location:** `web/src/pages/reports/SalesReportPage.tsx:123-138`; `PurchaseReportPage.tsx:124-139`; `InventoryReportPage.tsx:107-122`; `CustomerLedgerPage.tsx:150-172`; `SupplierLedgerPage.tsx:137-159`; `GstRateExposurePage.tsx:99-112`; `MissingDocumentsPage.tsx:104-126`; `web/src/pages/inventory/CurrentStockPage.tsx:213-289`; `ProductsPage.tsx` export builds the full string
- **Observation:** All use `rows.map(...)` into `<TableRow>` with no windowing. Sales/purchase registers, a multi-year customer ledger, and current stock for a large multi-godown catalogue are all unbounded.
- **Impact:** Multi-second render stalls / scroll jank on real datasets.
- **Fix:** Adopt `VirtualizedTable` (already used by `StatutoryEventsPage`, `Gstr2bPage`) or paginate.

### [F3-018] Unpaginated full-collection fetches feed dropdowns / client-side filters
- **Severity:** Medium
- **Category:** Performance
- **Location:** `web/src/pages/reports/CustomerLedgerPage.tsx:24` & `SupplierLedgerPage.tsx:24` (`listCustomers()` / `listSuppliers()` into an Autocomplete); `web/src/pages/phase/BankingPhasePages.tsx:548,684` (`listCustomers()` into a `<Select>`); `web/src/pages/inventory/StockAdjustmentPage.tsx:57`, `ProductsPage.tsx:86`, `ItemFormDialog.tsx:184` (`listStock()` — all rows, shared bare `['stock']` key); `web/src/pages/inventory/CurrentStockPage.tsx:65-72` (`listStock` then client-side warehouse filter at `88`); `web/src/pages/manufacturing/BomsPage.tsx:77` (`listProducts()`)
- **Observation:** These pull the entire collection to build a picker or a lookup map for a handful of visible rows; `CurrentStockPage` additionally does warehouse filtering in JS rather than server-side.
- **Impact:** Large tenants download megabytes per page load and pay client-side filter cost; the ledgers' Autocomplete filters thousands of options in `filterOptions`.
- **Fix:** Use the paged `q`-search endpoints (`listCustomersPage`, `listProductsPage`, targeted stock lookups) with a debounced query, as `PaymentLinksPage` and `useProductSearch` already do.

### [F3-019] Silent row caps in "pick a record" dropdowns
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/phase/InventoryPhasePages.tsx:559-562` (PriceLists product picker — `pageSize: 100`); `web/src/pages/crm/LeadsPage.tsx:86` & `OpportunitiesPage.tsx:68,72` (`pageSize: 200`); `web/src/pages/payroll/PayRunsPage.tsx:93-108` (LOP dialog — paginates but stops, and renders one field per employee with no scroll/search); `web/src/pages/phase/AccountingExtraPages.tsx:120-123` (`listJournalsPage({ pageSize: 100 })` → `unmatchedGl` only sees the first 100 journals)
- **Observation:** Each fetches a fixed first page and offers those as the only selectable options, with no "showing first N" note and no search.
- **Impact:** A business with >100 products cannot add product #101 to a price list; a CRM with >200 customers cannot link lead #201; GL bank-recon cannot match a journal older than the 100 most recent.
- **Fix:** Replace with a searchable server-backed Autocomplete, or at minimum surface the cap ("first 100 shown — search to narrow").

### [F3-020] `DocumentListPage` prints `String(error)` instead of a resolved message
- **Severity:** Medium
- **Category:** UX/UI
- **Location:** `web/src/components/DocumentListPage.tsx:87`
- **Observation:** `{error ? <ErrorState message={String(error)} error={error} onRetry={onRetry} /> : null}` — every other page in scope uses `getErrorMessage(error)`.
- **Impact:** A non-`Error` rejection value renders as `[object Object]`; an `Error` renders as `"Error: <msg>"` with the prefix. This shared component backs many document list screens.
- **Fix:** `message={getErrorMessage(error)}`.

### [F3-021] `capsForRole` does not fully reset capabilities when the invite role changes
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/settings/UsersSettingsPage.tsx:48-78`, applied at `319-323` (`setForm((f) => ({ ...f, role, ...capsForRole(role) }))`)
- **Observation:** `capsForRole('SALES_STAFF')` returns only `{canCreateSales, canCreatePurchases, canCreatePayments}`. The spread merge therefore leaves `canViewFinancialReports`, `canExport`, `canManageInventory`, `canImport`, `canCancelDocuments` at whatever the previously-selected role set them to.
- **Impact:** Owner picks "Accountant" (sets `canExport: true`, `canViewFinancialReports: true`), then switches to "Sales staff" and invites — the new sales staffer silently retains export and financial-report access.
- **Fix:** Have `capsForRole` return the full capability set for every role (explicit `false`s), so the spread is a complete override.

### [F3-022] User capability toggles mutate on click with no confirmation and no optimistic UI
- **Severity:** Medium
- **Category:** UX/UI
- **Location:** `web/src/pages/settings/UsersSettingsPage.tsx:205-282` (10 `<Checkbox>` cells, each `onChange={(e) => patchMutation.mutate({ id, <cap>: e.target.checked })}`)
- **Observation:** `checked={!!u.canCreateSales}` reads from `query.data`; the checkbox only visibly changes after `patchMutation` succeeds and `['company-users']` is invalidated and refetched. No confirm for granting "Can cancel documents" / "Can export" / "Can view financial reports". On failure only a page-top `HelpErrorAlert` shows and the box snaps back.
- **Impact:** Granting sensitive permissions is a single mis-click; the UI feels laggy/broken (box doesn't move for a round-trip); rapid toggling races.
- **Fix:** Optimistic update with rollback on error; a confirm for the sensitive caps (export / cancel / financial reports); disable the row while its mutation is pending.

### [F3-023] No way to deactivate or remove a user
- **Severity:** Medium
- **Category:** Gap
- **Location:** `web/src/pages/settings/UsersSettingsPage.tsx` — `patchMutation` type includes `isActive?` (`135`) but no control renders it; the Status column (`283-285`) is read-only text
- **Observation:** The page can invite and re-permission users but exposes no "Deactivate" / "Remove" action.
- **Impact:** An owner cannot off-board a departed staff member from the UI; their login keeps working.
- **Fix:** Add a Deactivate/Reactivate action per non-owner row calling `updateCompanyUser(id, { isActive })` behind a confirm.

### [F3-024] FixedAssetsPage hard-codes useful life = 36 months and acquisition date = today
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `web/src/pages/phase/FixedAssetsPage.tsx:30-44`
- **Observation:** `createFixedAsset({ name, acquisitionCost: Number(cost), acquisitionDate: todayIso(), usefulLifeMonths: 36 })`. The dialog only has Name and Acquisition cost fields.
- **Impact:** Every asset — building, vehicle, laptop — depreciates over exactly 3 years starting today. Depreciation and the balance-sheet asset value are wrong for anything not on a 36-month life or bought earlier. There is also no edit action to correct it afterwards.
- **Fix:** Add "Useful life (months)" and "Acquisition date" inputs; add an edit path.

### [F3-025] JournalsPage cannot back-date a voucher
- **Severity:** Medium
- **Category:** Partial-feature
- **Location:** `web/src/pages/phase/JournalsPage.tsx:44-46` (`entryDate: todayIso()`)
- **Observation:** The voucher dialog has Narration + lines only; `entryDate` is always today.
- **Impact:** Real bookkeeping routinely posts adjusting/opening journals to a prior date (period-end, FY start). Users cannot do that here.
- **Fix:** Add a date field (respecting open-period rules the backend already enforces).

### [F3-026] `AccountingSettingsPage` shows mutation errors as a blue "info" alert
- **Severity:** Medium
- **Category:** UX/UI
- **Location:** `web/src/pages/phase/AccountingExtraPages.tsx:33,43,52,56` — `onError: (e) => setMsg(getErrorMessage(e))` and `{msg ? <Alert severity="info">{msg}</Alert> : null}`
- **Observation:** Both the enable/disable mutation and the FY-close mutation funnel success *and* error text into one `msg` string rendered with a fixed `severity="info"`.
- **Impact:** A failed "Close financial year" or "Disable accounting" renders as a calm blue notice; the user may think it worked.
- **Fix:** Track `severity` alongside `msg` (or use `mutation.isError` to pick `error`).

### [F3-027] `msg.includes('saved')` decides the payment-gateway alert severity
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/phase/BankingPhasePages.tsx:171` — `<Alert severity={msg.includes('saved') ? 'success' : 'error'}>`
- **Observation:** Success text is `'Gateway settings saved'`; any error message not containing the substring "saved" shows as error, but an error string that happens to contain "saved" would show as success.
- **Fix:** Use `m.isError` / `m.isSuccess`.

### [F3-028] `PriceListsPage` silently drops slab rows on save and has no way to delete a slab
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/phase/InventoryPhasePages.tsx:578-597` (`save` — `.filter((row) => Number(row.product) && Number(row.unitPrice) >= 0)`), editor at `662-737`
- **Observation:** Rows whose product is unset or whose `unitPrice` is non-numeric/blank are filtered out with no warning. The slab editor has "Add slab" but no per-row delete — the only way to remove a slab is to clear its product, which then makes it vanish on save.
- **Impact:** A user fills five slabs, mistypes one price, hits Save — that slab disappears and they don't know which. No overlap validation on qty ranges either.
- **Fix:** Validate inline and block save with a message; add a delete-row button; warn on overlapping `[minQty,maxQty]` ranges. `create`/`save` also have no `onError` — surface failures in the dialog.

### [F3-029] Missing `onError` handlers → silent mutation failures across phase / settings pages
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/phase/InventoryPhasePages.tsx:175-191` (`complete` transfer), `433-436` (`transition` serial), `570-577` (price-list `save` has none in dialog); `web/src/pages/phase/AccountingExtraPages.tsx:309-315` (`CostCentersPage` create — no `onError`, no error UI anywhere); `web/src/pages/phase/BankingPhasePages.tsx:487-490` (`commit` bank statement), `560-563` (`confirm` recon), `264-267` (`cancel` payment link); `web/src/pages/settings/BillingPage.tsx:24-29` (`checkout` — see F3-033); `web/src/pages/settings/GstSettingsPage.tsx:490-499`, `509-528` (branch-GSTIN `.then()` with no `.catch`)
- **Observation:** These mutations only invalidate on success; a rejection is swallowed (`void`), leaving no toast/alert.
- **Impact:** "Complete transfer" / "Commit statement" / "Confirm match" / "Add branch GSTIN" appear to do nothing on failure; the user retries or assumes success.
- **Fix:** Add `onError: (e) => setError(getErrorMessage(e))` (or a shared toast) to every mutation whose failure the user needs to see.

### [F3-030] `Gstr2bPage` period is a free-text field; several report pages use freeform period inputs inconsistently
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/reports/Gstr2bPage.tsx:210-219` and `web/src/pages/reports/MissingDocumentsPage.tsx:79-85` use a plain `<TextField>`; `GstHealthPage.tsx:39-46`, `GstReturnPage.tsx:106-113`, `TdsTcsReportsPage.tsx:46-53` use `type="month"`
- **Observation:** The period control is `type="month"` in some GST screens and a raw text box (`YYYY-MM` typed by hand) in others.
- **Impact:** Typos in the free-text screens silently return an empty/incorrect period with no validation hint.
- **Fix:** Standardise on `type="month"` (or a validated masked input) everywhere a `YYYY-MM` period is entered.

### [F3-031] XLSX / CA-pack / GSTR-9 downloads have no error handling
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/phase/AccountingReportsPages.tsx:74-84` (`handleDownload` — `try/finally`, no `catch`); `web/src/pages/reports/Gstr9ReportPage.tsx:40-49` (`exportMutation` — no `onError`); `web/src/pages/reports/GstReturnPage.tsx:81-85` (`caPackMutation` — no `onError`; only `exportMutation` error is shown at `185`)
- **Observation:** If `downloadAccountingReport` / `downloadGstr9` / `downloadGstCaPack` or the follow-up `fetch(url)` fails, the button just re-enables. The GSTR-9 export and the CA pack are the artefacts a CA relies on.
- **Impact:** Silent failure; user thinks the download is coming.
- **Fix:** `catch`/`onError` → visible error (the pages already have `HelpErrorAlert`).

### [F3-032] InsightsAssistant renders AI-controlled citation paths straight into `<Link to={...}>`
- **Severity:** Medium
- **Category:** Security
- **Location:** `web/src/pages/insights/InsightsAssistantPage.tsx:164-173` — `<Chip ... component={RouterLink} to={c.path} clickable />` where `c` comes from `m.citations` in the assistant response
- **Observation:** Share links in the same component are validated with `isAllowedShareUrl` (`211,224`), but citation `path`s are not checked at all before being used as a router target.
- **Impact:** If the model (or a prompt-injected data source) emits `path: "javascript:…"` or an absolute off-site URL, the chip becomes a script/redirect vector. Lower likelihood (first-party model) but the guard that exists for share links is missing here.
- **Fix:** Validate `c.path` is an in-app relative route (`/^\/[\w\-/?=&.]*$/`) before rendering the chip; otherwise render it as inert text.

### [F3-033] BillingPage "Start checkout" only invalidates a query — no redirect to the payment page
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/settings/BillingPage.tsx:24-29`
- **Observation:** `const checkout = useMutation({ mutationFn: (planId) => startBillingCheckout(planId), onSuccess: () => { void qc.invalidateQueries({ queryKey: ['billing-portal'] }); } });`. The mutation result (which, for a hosted-checkout flow, would carry a redirect URL / order token) is discarded, and there is no `onError`.
- **Impact:** Clicking "Start checkout" appears to do nothing visible except a background refetch; if `startBillingCheckout` returns a gateway URL the user is never sent there. (Confirm against `api/billing`; if checkout is fully server-driven this is only the missing feedback.)
- **Fix:** If the response contains a checkout/redirect URL, navigate to it (`window.location.assign`), and show `checkout.isError`.

### [F3-034] Setup wizard step 5 posts a real, completed GST invoice and leaves sample products behind
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/setup/SetupWizardPage.tsx:249-279` (`createFirstBill` → `completeSalesInvoice`), `223-238` (`addSamples` creates 3 real products)
- **Observation:** "Create first bill" creates a customer (or reuses "Walk-in Customer"), creates a sales invoice for 1 unit of the last product, and immediately `completeSalesInvoice(invoice.id)` — a finalised document that hits GSTR-1, stock and the GL. `addSamples` `Promise.all`-creates "Sample Item / Sample Service / Delivery Charge" as ACTIVE catalogue products with no cleanup, and a partial `Promise.all` failure leaves some created.
- **Impact:** A new tenant's very first statutory invoice and stock movement are an onboarding artefact the user may not realise is "real"; the sample products persist in the live catalogue forever unless manually deleted.
- **Fix:** Clearly label step 5 as creating a real invoice (or make it a dry-run/preview). Tag sample products so they can be bulk-removed, or create them as INACTIVE.

### [F3-035] `ItemSettingsPage`: new custom-field row remounts on every keystroke while typing the Label
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/settings/ItemSettingsPage.tsx:182` (`<Stack key={`${row.key}-${index}`} ...>`) combined with `206-213` (label `onChange` derives `key = suggestCustomFieldKey(nextLabel)` while `!keyTouched`)
- **Observation:** For a freshly-added row, `key` starts `''` and is regenerated from the label on each character; the row's React `key` is `${row.key}-${index}`, so it changes on every keystroke → the whole `<Stack>` subtree (including the focused `<TextField>`) unmounts and remounts.
- **Impact:** Typing a label for a new field loses focus / drops characters / jumps the caret.
- **Fix:** Key the row by `index` only (or a stable generated id), not by the mutating `key` value.

### [F3-036] `StockConflictModal` makes "Keep local" the emphasised default action
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/inventory/StockConflictModal.tsx:42-45`
- **Observation:** In a 409 conflict dialog, "Keep server" is a plain button and `<Button variant="contained">Keep local</Button>` is the primary. `snapshotQty` is parsed (`godownConflict.ts`) but never shown.
- **Impact:** The visually-default choice overwrites data that changed on the server underneath the user — usually the more dangerous option. The user also can't see the base quantity they counted from.
- **Fix:** Make "Keep server" (or Cancel) the primary; show all three quantities (server / local / snapshot) per line.

### [F3-037] `ExpiryAlertsPage` write-off falls back to the alert row id as the batch id
- **Severity:** Medium
- **Category:** Data-integrity
- **Location:** `web/src/pages/phase/InventoryPhasePages.tsx:347-354` — `batch: Number(row.batch || row.id)`
- **Observation:** If the expiry-alert row lacks a `batch` field, the code posts `batch: row.id` — the alert's own id — as the write-off target.
- **Impact:** Depending on the API's id space this either 400s or writes off against the wrong lot. Write-off is a stock + GL posting.
- **Fix:** Require an explicit batch id from the alert payload; if absent, disable the "Write off" button for that row rather than guessing.

### [F3-038] `CurrentStockPage` shows a blank page when a client-side filter removes all rows
- **Severity:** Medium
- **Category:** UX/UI
- **Location:** `web/src/pages/inventory/CurrentStockPage.tsx:188` (`query.data?.length === 0 ? <EmptyState/>`) vs `189` (`rows.length > 0 ? <table/>`)
- **Observation:** The empty state keys off the raw response length; the table keys off `rows` (after the client-side warehouse + custom-field filter at `87-149`). When the response is non-empty but the filter yields nothing, neither branch renders.
- **Impact:** Selecting a godown / CF filter with no matching stock shows an empty screen with no "no results for this filter" message.
- **Fix:** `{!query.isLoading && rows.length === 0 ? <EmptyState description="No stock matches these filters" /> : null}`.

### [F3-039] `LowStockPage` and other tables key rows by `product` id that may not be unique
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/inventory/LowStockPage.tsx:45` (`key={s.product}`); similar `key={p.id}`/`key={row.id}` assumptions in `CurrentStockPage` lot rows and `DataTable` (`phaseShared.tsx:105`)
- **Observation:** If `listLowStock` returns one row per (product, warehouse) — plausible for per-godown reorder rules — `key={s.product}` collides.
- **Impact:** React key warnings, and potentially rows overwriting each other's DOM state (sort, hover).
- **Fix:** Compose the key from all identifying fields (`${s.product}-${s.warehouse}`).

### [F3-040] `StockCountPage`: opening an existing count from the list shows no lines; offline banner goes stale
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/pages/inventory/StockCountPage.tsx:204-216` (`setActive(row)` straight from the list) and `34` (`useStockOffline` called without `setOutboxBanner`)
- **Observation:** The "Count"/"View" action sets `active` to the list row, and `lines` is `active.lines` (`154`). `listStockCounts` rows don't necessarily carry `.lines`; there is no `getStockCount(id)` hydration call, so the dialog renders "No on-hand lines at this godown." until a `saveLines` round-trip. Separately, `pendingCount`/`lastSynced` are only updated by this page's own offline `post`; a background flush by `useStockOffline` never decrements them, so the "N pending" banner stays stale after a successful sync.
- **Impact:** Re-opening a count to keep counting appears to show an empty sheet; the sync banner lies.
- **Fix:** Fetch the single count detail when `active` is set; pass `setOutboxBanner` to `useStockOffline` (or read pending state from `listDrafts`).

### [F3-041] `useStockOffline` re-registers its listener / re-flushes on every render when given an inline callback
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/inventory/useStockOffline.ts:39-73` — `useEffect(..., [companyId, userId, setOutboxBanner])`
- **Observation:** The effect adds an `online` listener and calls `void flush()` on mount; its deps include `setOutboxBanner`. Any caller that passes an unmemoised setter re-runs the effect every render → listener churn + repeated `flush()` invocations. Errors thrown inside `flush` (e.g. `listDrafts` rejecting) are unhandled.
- **Impact:** Redundant network flushes and listener add/remove cycles; a failing `listDrafts` silently stops sync with no banner.
- **Fix:** Wrap the callback in the caller with `useCallback`, or drop it from the deps and read it via a ref; wrap `flush` body in try/catch.

### [F3-042] `VirtualizedTable` cannot handle variable-height rows; consumers hard-code the row height twice
- **Severity:** Medium
- **Category:** Performance
- **Location:** `web/src/components/VirtualizedTable.tsx:18-24` (`estimateSize: () => rowHeight`, no `measureElement`); consumers `web/src/pages/reports/StatutoryEventsPage.tsx:94,112,132` (`rowHeight={48}` and `rows.length * 48` spacer math) and `Gstr2bPage.tsx:271,357` (`rowHeight={64}` and `rows.length * 64`)
- **Observation:** Row size is a fixed estimate; the consumers additionally compute leading/trailing spacer `<TableRow>` heights from the same magic number. Nothing measures actual DOM height.
- **Impact:** Any row that wraps to two lines (a long narration, a long IMS remark) desynchronises the spacers → visible gaps or overlapping rows while scrolling. Changing `rowHeight` in one place and not the other silently breaks scrolling.
- **Fix:** Use `virtualizer.measureElement` with `data-index` on each row and let the library track real sizes; derive the spacer heights from `virtualizer.getTotalSize()` / `getVirtualItems()[0].start` instead of re-multiplying.

### [F3-043] `CompanyRequiredDialog`: cancel leaves the app in a dead state; `pick` swallows errors
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/components/CompanyRequiredDialog.tsx:49-55` (`pick` — `await switchCompany(); window.location.reload();` no catch) and `61,76` (`onClose`/Cancel just `setOpen(false)`)
- **Observation:** The dialog opens on a 409 `COMPANY_REQUIRED`. Cancelling only hides it — the underlying page still has no company context and there's no way to re-open the picker except triggering another 409. If `switchCompany` rejects, the promise is unhandled and nothing tells the user.
- **Impact:** User dismisses the picker and is stuck on a broken screen; a failed switch silently does nothing.
- **Fix:** Remove Cancel (or route it to `/` / logout); add `.catch` → visible error and keep the dialog open.

### [F3-044] `ErrorBoundary` is a single top-level boundary; a crash in one route blanks the whole shell
- **Severity:** Medium
- **Category:** Gap
- **Location:** `web/src/components/ErrorBoundary.tsx` (one class), mounted once (`App.tsx`)
- **Observation:** There is exactly one `ErrorBoundary`. A render-time throw in any report/settings page replaces the entire authenticated UI (nav, company switcher, everything) with the full-page "reload" screen.
- **Impact:** A malformed payload on, say, `BalanceSheetPage` takes down navigation too; the user can't route away, only reload.
- **Fix:** Add a per-route (or per-`<Outlet>`) `ErrorBoundary` with a smaller inline fallback so siblings and the app chrome survive.
- **Note:** `getDerivedStateFromError` also performs a side effect (`window.location.reload()` for chunk errors) — per React docs that belongs in `componentDidCatch`; and the `bizboard:chunk-reload` sessionStorage flag is never cleared on a successful load, so only the *first* chunk error in a session auto-recovers.

### [F3-045] `PdfStatusPoller` mutates React state inside its `queryFn`
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/src/components/PdfStatusPoller.tsx:59-73`
- **Observation:** `queryFn: async () => { setPollCount((n) => n + 1); return getSalesDocumentPdfStatus(...); }`, and `pollCount` is then read by `refetchInterval` to cap at `MAX_POLLS`.
- **Impact:** `queryFn` is expected to be pure; a retry or a React-Query internal refetch double-increments `pollCount`, so the poller can hit `MAX_POLLS` early (and give up on a PDF that's still generating) or extra-render on every poll. `handleDownload` (`85-89`) also has no error handling.
- **Fix:** Drive the poll count off `query.dataUpdatedAt` / a ref incremented in a `useEffect` keyed on `query.data`, not inside `queryFn`; add a `catch` to `handleDownload`.

### [F3-046] `EinvoiceEwayPanel`: e-Way cancel has no reason dialog (e-Invoice cancel does), and prop refetch wipes a typed IRN
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/components/EinvoiceEwayPanel.tsx:177-184` (`cancelEwayMutation` — one-click), `406-441` (e-Invoice cancel dialog with required `cnlRsn`/`cnlRem`), `91-95` (`useEffect` sets `irn`/`ackNo`/`ewayBillNo` from props)
- **Observation:** "Cancel" for the e-Way bill fires immediately with no reason; NIC requires a cancellation reason, and the e-Invoice side already collects one. The `useEffect` re-runs whenever `invoice.irn`/`ackNo`/`ewayBillNo` change reference; if a parent refetch delivers the same (still-empty) invoice while the user is typing a manual IRN, `setIrn(invoice.irn ?? '')` clears the field.
- **Impact:** Inconsistent, incomplete e-Way cancellation; lost keystrokes on a statutory field.
- **Fix:** Reuse the cancel dialog pattern (reason + remarks) for e-Way; only overwrite local IRN/ackNo state when the incoming value is non-empty and differs, or when the invoice id changes.
- **Note:** "Submit (sandbox)" for both e-Invoice and e-Way has no confirm — acceptable only while `isEinvoiceSubmitEnabled()`/`isEwaySubmitEnabled()` gate it to sandbox; add a confirm before that flag can enable real NIC submission.

### [F3-047] `MissingDocumentsPage`: "Send WhatsApp" bulk-messages suppliers with no confirmation
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/reports/MissingDocumentsPage.tsx:36-49,73-76`
- **Observation:** `<Button ... onClick={() => wa.mutate()}>` calls `chaseMissingWhatsApp(period)` which server-side sends chase messages to every supplier with a missing document. No confirm, no recipient list preview.
- **Impact:** One click sends outbound messages on the user's behalf to N third parties.
- **Fix:** Confirm dialog listing how many suppliers will be messaged (and ideally which), before firing.

### [F3-048] Dunning (automated customer reminders) is enabled by a toggle + Save with no confirmation
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/settings/CompanySettingsPage.tsx:256-270` (`dunningEnabled` switch), `99-107` (`dunningDays` parse)
- **Observation:** Flipping the switch and clicking Save turns on a standing rule that sends reminder messages to customers on the `dunningDays` schedule. `dunningDaysText` is parsed with `.split(/[,\s]+/).map(Number).filter(n => Number.isFinite(n) && n >= 1)` — invalid entries are dropped silently, no dedup, no upper bound; quiet-hours fields aren't range-checked (0–23) and start-vs-end isn't validated.
- **Impact:** A standing outbound-messaging rule is created without an explicit "this will message your customers automatically" acknowledgement; a fat-fingered `dunningDays` silently becomes something else.
- **Fix:** Confirm when enabling dunning; validate/echo the parsed schedule back to the user; range-check quiet hours.

### [F3-049] Changing GST registration type / negative-stock policy has no confirmation
- **Severity:** Medium
- **Category:** Broken-flow
- **Location:** `web/src/pages/settings/GstSettingsPage.tsx:290-317`
- **Observation:** `registrationType` (REGULAR ↔ COMPOSITION ↔ UNREGISTERED) and `negativeStockPolicy` (BLOCK ↔ WARN) are plain selects saved with the rest of the form.
- **Impact:** Switching to COMPOSITION changes every future document to "Bill of Supply, no tax"; switching negative-stock policy to WARN lets counter staff oversell. Both are high-impact and easy to flip by accident.
- **Fix:** Confirm dialog spelling out the consequence when either of these two fields changes.

### [F3-050] TallyMigration "Ignore error rows" discards rows silently; the map table is unvirtualised
- **Severity:** Medium
- **Category:** Data-integrity / Performance
- **Location:** `web/src/pages/settings/TallyMigrationPage.tsx:134-150` (`ignoreErrors`), `270-310` (map table — `mapRows.map` into two `<TextField>` per row), `206-224` (`updateMappedName`/`updateMappedSku` spread-copy the whole array per keystroke)
- **Observation:** "Ignore error rows" clears `errors: []` and resets counts, then commit becomes allowed — with no summary of what is being skipped. The mapping table renders every customer+supplier+product row (each with editable name and, for products, SKU) with no windowing, and each keystroke re-copies and re-renders the full array.
- **Impact:** Users can commit a migration that silently dropped hundreds of bad rows; a large Tally masters file makes the map step unusable (laggy typing, huge DOM).
- **Fix:** Show "N rows will be skipped" before allowing commit past errors; virtualise the map table; debounce / localise the per-row edit state.

### [F3-051] `TallyMigrationPage.downloadErrors` can throw unhandled; blob URLs revoked immediately after click
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/settings/TallyMigrationPage.tsx:179-195` (`downloadErrors`, called as `onClick={() => void downloadErrors()}`), plus immediate `URL.revokeObjectURL` at `174,194` and the same pattern in `Gstr9ReportPage.tsx:47`, `GstReturnPage` via `Gstr2bPage.tsx:128`, `ImportPage.tsx:95`, `ProductsPage.tsx:152`, `ItemFormDialog`/others
- **Observation:** `downloadErrors` explicitly `throw`s on a JSON content-type and does network I/O, but the caller only `void`s it. Separately, many download helpers call `URL.revokeObjectURL(url)` synchronously right after `a.click()`; `SalesReportPage`/`BackupExportPage` correctly defer it (`setTimeout(..., 10_000)`).
- **Impact:** A failed error-report download gives no feedback; the immediate-revoke pattern can cancel the download of a large blob in some browsers.
- **Fix:** Wrap `downloadErrors` in try/catch → visible error; standardise on the deferred-revoke helper everywhere.

### [F3-052] `resolveHelpQuery` returns "confident" for a genuine two-intent tie
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/help/resolver.ts:145-166`
- **Observation:** After the `top.score >= CONFIDENT && gap >= AMBIGUOUS_GAP` fast-path (`141`), execution can still reach `155` (`if (top.score >= CONFIDENT)` inside the "gap < AMBIGUOUS_GAP" branch) when there are no ambiguity chips — returning `'confident'` for the higher-`priority` intent even though the two top scores are effectively tied.
- **Impact:** A query that legitimately matches two intents equally is answered with one of them as if it were unambiguous, instead of showing the user a chooser.
- **Fix:** In the tie branch with no chips, return `'ambiguous'` (or `'no-match'` with the top hits shown) rather than falling through to a confident answer.

### [F3-053] `DiagnosisPicker` has no cycle / depth guard on cross-intent diagnosis links
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/help/DiagnosisPicker.tsx:52-79` (`nestedTree` recursion) and `11-24` (`findDiagnosisPath`)
- **Observation:** A leaf can point at another type-6 intent (`leaf.intentId`), which is rendered by recursing `<DiagnosisPicker intent={target} />`. The only guard is `target.intentId !== intent.intentId` (direct self-reference). Two intents that reference each other (A→B, B→A) recurse without bound.
- **Impact:** A data-authoring mistake in `intents.ts` causes a render stack overflow / crashed help page rather than a graceful stop.
- **Fix:** Thread a visited-intent set (or a max depth) through the recursion and stop with a "see <intent>" link when a cycle is detected.

### [F3-054] Help analytics sends raw help-search query text to the first-party events endpoint
- **Severity:** Low
- **Category:** Improvement
- **Location:** `web/src/pages/help/analytics.ts:38-64` — third-party path strips `query` and only sends `queryLenBucket`, but `enqueue({... query: props?.query, props })` keeps the raw text (twice)
- **Observation:** The comment "Third-party analytics ... never receive raw query text" is true; the first-party `postHelpEvents` batch is not similarly redacted.
- **Impact:** Whatever a user types into help search (could contain a GSTIN, an amount, a customer name) is persisted server-side against their session.
- **Fix:** Decide deliberately: either document that first-party help search text is retained, or hash/bucket it there too.

### [F3-055] `SupplierLedgerPage` hard-codes bilingual column headers instead of using `t()`
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/reports/SupplierLedgerPage.tsx:131-132` — `<TableCell align="right">Paid (−) / डेबिट</TableCell>` / `Billed (+) / क्रेडिट`
- **Observation:** `CustomerLedgerPage` uses `t('reports.billedAmount')` / `t('reports.receivedAmount')` for the equivalent columns; the supplier page embeds a fixed English+Hindi string. Its Autocomplete also lacks the custom `filterOptions` (GSTIN search) and popper `zIndex` that the customer page has.
- **Impact:** These headers don't switch with locale; the two ledgers behave inconsistently.
- **Fix:** Route through `t()`; align the Autocomplete config with `CustomerLedgerPage`.

### [F3-056] Steppers translate their labels once at module load
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/settings/ImportPage.tsx:37` (`const steps = [t('import.stepUpload'), ...]`); `web/src/pages/settings/TallyMigrationPage.tsx:28` (`const STEPS = ['Upload','Map','Commit','Export aid']` — not translated at all)
- **Observation:** `ImportPage`'s `steps` array is evaluated at import time, so it won't re-translate on a runtime locale switch. `TallyMigrationPage`'s stepper labels are plain English literals while the page title/disclaimer use `t()`.
- **Fix:** Build the label array inside the component (`useMemo` on locale), and translate the Tally step labels.

### [F3-057] `OnboardingChecklist` and `SetupWizardPage` use hard-coded light-mode colours
- **Severity:** Medium
- **Category:** UX/UI
- **Location:** `web/src/components/OnboardingChecklist.tsx:52` (`background: 'linear-gradient(135deg,#F0FDF4 0%,#FFFFFF 60%,#F8FAFC 100%)'`), `98,140,177,214` (`bgcolor: 'rgba(255,255,255,0.85)'`); `web/src/pages/setup/SetupWizardPage.tsx:300` (`bgcolor: '#F3F6F5'`)
- **Observation:** These surfaces are fixed near-white regardless of theme. `LocaleSwitcher.tsx:26-34` shows the team has already hit theme-contrast bugs elsewhere (`BB-000751`).
- **Impact:** In dark mode the onboarding card and setup wizard render dark text on a near-white block (or white-on-white), i.e. unreadable.
- **Fix:** Use theme tokens (`background.paper`, `action.hover`, `theme.palette.mode`-aware gradients).

### [F3-058] `InsightsCashflowPage` bar chart encodes sign by colour only and uses `Math.abs` for bar/band heights
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/insights/InsightsCashflowPage.tsx:74-127`
- **Observation:** `const h = Math.max(4, (Math.abs(v) / maxAbs) * 100)`; bar colour is `v >= 0 ? 'success.main' : 'error.main'`. `bandTop`/`bandBot` are also `Math.abs` of `high`/`low`.
- **Impact:** A −₹50k and a +₹50k day render as identical-height bars distinguishable only by colour (fails for colour-blind users and greyscale print); when the low–high band straddles zero the abs-based band drawing is meaningless. The data table below mitigates but the chart is the headline.
- **Fix:** Draw bars from a zero baseline (up for positive, down for negative); add a value/label or pattern, not colour alone.

### [F3-059] Column headers use an emoji "ℹ️" inside a non-interactive `<span>` for the tooltip
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/inventory/CurrentStockPage.tsx:202-207` — `<Tooltip title={...}><span style={{cursor:'help'}}>Reserved ℹ️</span></Tooltip>`
- **Observation:** The info affordance is an emoji in a `<span>` that isn't focusable and has no `aria-label`; the tooltip is unreachable by keyboard and screen readers announce "information" emoji.
- **Fix:** Use an `<IconButton size="small">` with `<InfoOutlinedIcon>` and an `aria-label`, or a real `<abbr>`/described-by pattern.

### [F3-060] Ledger / recon / cash-book share buttons interpolate an unformatted amount into the WhatsApp message
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/reports/CustomerLedgerPage.tsx:48` and `SupplierLedgerPage.tsx:48` — `` `Total Outstanding Balance: ₹${ledger.data.outstanding}` ``
- **Observation:** `ledger.data.outstanding` is a raw number/string, not run through `formatMoney`; the on-screen figure uses `formatMoney`.
- **Impact:** Customer-facing statement messages show `₹1234.5` / `₹1234.567` / `₹-500` inconsistently.
- **Fix:** `formatMoney(ledger.data.outstanding)` in the message body.

### [F3-061] `GstRateExposurePage` opens with a hard-coded start date of 2025-09-22
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/reports/GstRateExposurePage.tsx:49` — `const [from, setFrom] = useState('2025-09-22')`
- **Observation:** Every user always starts this report from a fixed literal date unrelated to their data or financial year; `to` defaults to `new Date().toISOString().slice(0,10)` (UTC — can be "yesterday" for an IST user in the early hours).
- **Fix:** Default `from` to the current FY start (or 12 months back); compute `to` from local date.

### [F3-062] Hard-coded default financial-year end strings will go stale
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/phase/AccountingExtraPages.tsx:34` (`useState('2026-03-31')`) and `web/src/pages/phase/PeriodsPage.tsx:24` (`useState('2026-03-31')`)
- **Observation:** The "FY end" field defaults to a literal `2026-03-31`.
- **Impact:** After FY 2025-26 this default is wrong every time; users must remember to change it before "Close FY".
- **Fix:** Compute from `todayIso()` (next 31 March on/after today).

### [F3-063] `printBarcode` / `window.print()` calls print the whole app, not a scoped area
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/reports/CustomerLedgerPage.tsx:108` & `SupplierLedgerPage.tsx:95` (`onClick={() => window.print()}`); `web/src/pages/inventory/StockCountPage.tsx:283` ("Print sheet" → `window.print()`)
- **Observation:** These call the browser print dialog on the full document; there's no print-only stylesheet or hidden print container visible in these components.
- **Impact:** Printed output includes the app bar, nav and filters unless a global `@media print` rule (not in scope) handles it.
- **Fix:** Render a dedicated print view (react-to-print / a print-only DOM subtree), or verify a global print stylesheet strips chrome.

### [F3-064] `StockAdjustmentPage` records shrinkage/theft with no confirmation and no post-adjustment balance preview
- **Severity:** Medium
- **Category:** UX/UI
- **Location:** `web/src/pages/inventory/StockAdjustmentPage.tsx:93-129,351-353`
- **Observation:** "Save" submits `createStockAdjustment` (a stock movement + GL posting) immediately. The form shows "current recorded balance" but not "balance after this adjustment", and there's no client-side guard/warning when a REDUCE takes stock below zero.
- **Impact:** A mistyped quantity on a "Theft / Lost Inventory" reduction posts directly to the books; the user never sees the resulting figure before committing.
- **Fix:** Show `current − qty` live; confirm on submit (especially for REDUCE); warn when the result is negative.

### [F3-065] `LeadsPage` activity dialog mislabels the activity-kind picker as "Status"
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/crm/LeadsPage.tsx:342-353` — `<TextField select label={t('common.status')} ...>` whose options are `ACTIVITY_KINDS` (`NOTE`/`CALL`/`EMAIL`)
- **Observation:** Copy bug — the control picks the activity kind but is labelled "Status".
- **Fix:** `label={t('erp.activityKind')}` (or similar).

### [F3-066] Shared `error` string across multiple dialogs isn't cleared on dialog switch
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/crm/LeadsPage.tsx:72` (one `error` used by save / convert / activity mutations); similar single-`error` sharing in `web/src/pages/phase/BankingPhasePages.tsx` `PaymentLinksPage` (create / share / refund / retry all `setError`)
- **Observation:** An error from one action renders at page top and persists while the user opens a different dialog for an unrelated action.
- **Fix:** Scope error state per dialog/action, or clear it when a dialog opens/closes.

### [F3-067] `PayRunsPage` LOP dialog: unbounded per-employee fields, no paid-days validation
- **Severity:** Medium
- **Category:** UX/UI
- **Location:** `web/src/pages/payroll/PayRunsPage.tsx:341-367,93-108`
- **Observation:** The LOP dialog renders a `type="number"` field per employee (all employees, fetched via a page-by-page loop) with no scroll container, no search, and no `min`/`max` — `paidDays` of 99 or −5 is accepted and sent to `applyPayRunLop`. The employee-loading loop has no error handling; a failed page leaves the dialog empty.
- **Impact:** For a large workforce the dialog is unusable; an out-of-range paid-days value produces a wrong salary if the server doesn't reject it.
- **Fix:** Virtualise/search the list; clamp paid-days to `[0, daysInMonth]`; handle the paging loop's errors.

### [F3-068] `WorkOrdersPage` release proceeds with `componentSerials: undefined` when the pasted text is malformed
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/manufacturing/WorkOrdersPage.tsx:58-81` (`parseComponentSerials` returns `undefined` on `JSON.parse` failure) used at `441-444`
- **Observation:** If the user pastes almost-JSON (`{...` that doesn't parse) the function silently returns `undefined` and release fires with no component serials.
- **Impact:** A serial-tracked BOM component gets released without its serials recorded (or the server rejects with a confusing error).
- **Fix:** Distinguish "no input" from "unparseable input"; block release and show a parse error for the latter.

### [F3-069] `AccountingReportsPages` unmounts the date/cost-centre toolbar while a new range loads
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/phase/AccountingReportsPages.tsx:85` — `if (q.isLoading) return <LoadingState />;`
- **Observation:** The query key includes `from`/`to`/`costCenter`, so changing a date creates a fresh cache entry with `isLoading === true`, and the early return replaces the entire `PageShell` (including the filter inputs) with a centered spinner.
- **Impact:** Every date change makes the controls disappear and the page jump; the user loses their place / focus.
- **Fix:** Keep the shell + controls mounted and show the loading state only in the results area (use `isFetching` + `placeholderData`/`keepPreviousData`).

### [F3-070] `InsightsHealthPage` score-history bars assume a 0–100 scale
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/pages/insights/InsightsHealthPage.tsx:74-90` — `height: `${Math.max(8, score)}%`` inside an 80px-tall row
- **Observation:** `score = Number(h.score)` is used directly as a percentage height with no clamp.
- **Impact:** If the health score is ever on a different scale (e.g. 0–1000), bars overflow the container wildly. `history`/`hints` query errors are also unhandled — the sections just vanish.
- **Fix:** `Math.min(100, Math.max(8, score))`; render an error state for the secondary queries.

### [F3-071] `interpolateDestination` returns `''` for any unfilled param, and `NextStepButton` only supplies `id`/`invoiceId`
- **Severity:** Low
- **Category:** UX/UI
- **Location:** `web/src/pages/help/helpPermissions.ts:38-46`; `web/src/pages/help/NextStepButton.tsx:22-41`
- **Observation:** `NextStepButton` builds `params = { id, invoiceId }` from `context.invoiceId` only. Any help intent whose `nextStep.destination` needs a different param, or that is opened without an invoice in context (e.g. from the nav Help link), yields `dest === ''` and the actionable button is replaced by `nextStep.fallback` prose.
- **Impact:** "Edit this bill" / "Create credit note" CTAs are silently unavailable whenever Help is entered without `?invoiceId=`; a mis-authored intent using another param name never shows its button.
- **Fix:** Pass the full `context` through as params; log (dev-only) when a destination can't be interpolated so authoring mistakes surface.

### [F3-072] `CustomFieldFilterBar` spreads `getTagProps({ index })` including `key` onto `<Chip>`
- **Severity:** Low
- **Category:** Bug
- **Location:** `web/src/components/CustomFieldFilterBar.tsx:45-47`
- **Observation:** `selected.map((option, index) => <Chip size="small" label={option} {...getTagProps({ index })} />)` — MUI v5 moved `key` out of the spread; React warns that a `key` is being spread.
- **Fix:** `const { key, ...tagProps } = getTagProps({ index }); return <Chip key={key} {...tagProps} label={option} />`.

### [F3-073] Several success `Alert`s never dismiss and pages use a spinner where a skeleton exists
- **Severity:** Info
- **Category:** UX/UI
- **Location:** persistent success alerts: `web/src/pages/settings/CompanySettingsPage.tsx:143`, `GstSettingsPage.tsx:191`, `AiSettingsPage.tsx:86`, `ItemSettingsPage.tsx:164`, `InvoiceTemplatesPage.tsx:69`, `phase/AccountingExtraPages.tsx:56`; spinner-instead-of-skeleton: most report/inventory pages use `<LoadingState/>` though `ListSkeleton`/`DetailSkeleton` (`components/PageState.tsx:24-48`, FE-20) exist and `DocumentListPage` uses them
- **Observation:** Save-confirmation alerts have no `onClose` / auto-hide and sit until the next action; data-heavy list pages show a centered spinner rather than the content-shaped skeleton the design system provides.
- **Fix:** Add `onClose`/auto-dismiss to success alerts; adopt `ListSkeleton` on the register/list pages.

### [F3-074] Dead / redundant code and minor duplication
- **Severity:** Info
- **Category:** Improvement
- **Location:** `web/src/pages/phase/BankingPhasePages.tsx:552-556` (`BankReconPage` — `if (Array.isArray(data) && data.length && data[0].line) return data as Row[]; return data as Row[];` — both branches identical); `web/src/pages/reports/CustomerLedgerPage.tsx:39` / `SupplierLedgerPage.tsx:39` (`filteredEntries` is `useMemo(() => ledger.data?.entries ?? [], ...)` — "filtered" but does no filtering); `web/src/pages/reports/SalesReportPage.tsx` & `PurchaseReportPage.tsx` (identical `downloadBlobUrl` + `formatColumnHeader` copy-pasted); `web/src/pages/phase/AccountingExtraPages.tsx:310` & `InventoryPhasePages.tsx:47` (`code: code || name.slice(0,8).toUpperCase()` — can emit codes with spaces/punctuation); `web/src/components/OnboardingChecklist.tsx:42` (the `completedSteps === 4` chip-colour branch is unreachable because the component returns `null` in that state)
- **Fix:** Delete the no-op branch; rename `filteredEntries` → `entries`; hoist `downloadBlobUrl`/`formatColumnHeader` to a shared util; sanitise auto-generated codes.

---

## Cross-cutting observations (not separately numbered)

- **Company switch is safe:** `useCompanySwitcher.ts:83` calls `qc.clear()` and `CompanySwitcher`/`CompanyRequiredDialog` do `window.location.reload()` after switching, so "stale data after company switch" is largely a non-issue for the query-keyed pages in scope (none key by company id, but the full reload + cache clear covers it). Flagged only where a switch path (`CompanyRequiredDialog.pick`) lacks error handling — see F3-043.
- **Help / FAQ content is English-only JSX** (`faqContent.tsx`, 1480 lines) with no `t()` wrapping of answers; `HelpPageV0`/`HelpPageV2` render it as-is. If Hindi is a supported UI locale this is a large i18n gap, but it appears to be a deliberate current limitation (`IntentBody.pick` has an explicit `help.hindiSoon` fallback for intent bodies).
- **Phase pages are real implementations, not placeholders** — the grep for `coming soon` / `TODO` / `stub` across the scope found only the GST-return stubs (F3-008) and the documented GSTR-6/7/8 note. No `FIXME`/`HACK` markers in scope.
- **Better-built examples for contrast:** `WorkOrdersPage`, `PayRunsPage`, `ImportPage` and `ItemSettingsPage`'s remove-field flow all use `ConfirmDialog`/`window.confirm` correctly and have `onError` on their mutations — the phase pages and several settings pages should be brought up to that bar.

