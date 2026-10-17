# Accounting screens: deep review (2026-10-16)

Scope: Chart of Accounts, Journals, Cost Centers, Fixed Assets, Accounting Periods, Bank Reconciliation, Expenses, Day Book.

**Method:** static read of the React pages, Django views/serializers/services/tasks, the GST period guard, Books Health, and the payments reconciliation. The app was **not run**: layout, mobile and accessibility points are *Inferred*. Tests were not run.

Labels: **[O]** Observed in code · **[I]** Inferred · **[V]** Needs verification · **[U]** Unknown.

Files read: `web/src/pages/phase/{JournalsPage,FixedAssetsPage,PeriodsPage,AccountingReportsPages,AccountingExtraPages,BooksCloseSection,phaseShared}.tsx`, `web/src/pages/accounting/ExpensesPage.tsx`, `web/src/pages/reports/DayBookPage.tsx`, `web/src/components/AccountingBackfillBanner.tsx`, `web/src/navigation/menu.ts`, `backend/accounting/{views,models,serializers,services,tasks}.py`, `backend/reporting/{gst_periods,transactions}.py`, `backend/payments/views.py` (recon), `backend/masters/views.py` (ExpenseCategory), `docs/FREEZE_SCOPE.md`.

---

## 0. Context that changes how findings should be read

- **[O] Fixed assets are a declared pilot limitation** (D6, `ENABLE_FIXED_ASSETS=0`, QOS-0067: "post the monthly depreciation journal manually"). The nav item is flag-gated (`menu.ts`). Fixed-asset findings are therefore *latent* in the pilot but real the moment the flag is turned on (the demo profile does).
- **[O] Expenses work without accounting enabled** (`ExpenseViewSet` has no `AccountingEnabledMixin`). So "does an expense reach the books?" has a different answer when books are on versus off.
- **[O] Every module posts through `PostingService.post`.** It enforces books-start date, balance, period lock, GST-period lock and an idempotency key. Any weakness in these screens' guards is a weakness for all modules.

---

## 1. Chart of Accounts

**Purpose / user:** show the account list to accountant and owner. **[O]** Read-only: Code, Name, Type, System. The backend supports create/update/delete (`CanPostJournals`; system accounts protected; delete of an in-use account says "deactivate instead").

**Flow:** Entry from nav → `listAccounts` → table. No exit actions. Back-fill banner shown above when books are not yet trusted.

**Data:** reads accounts. Creates nothing. State: active/inactive exists in the model and serializer but is not displayed.

**Business logic [O]:**
- System accounts cannot be edited or deleted; accounts in use cannot be deleted.
- There is no server rule that account *type* is immutable once postings exist [V]; no uniqueness message for duplicate code seen in the view [V].

**Findings**
- **P1 [O]** No add / rename / deactivate in the UI, although the API allows it. A business with its own ledgers (e.g. "Rent – Shop 2") cannot create them without engineering help. Also no way to deactivate an account that cannot be deleted.
- **P1 [O]** Inactive accounts are *selectable* in manual journals: `validate_account` checks company only, and `PostingService.post` never checks `is_active`. Deactivation (once the UI exists) would therefore not prevent postings.
- **P2 [O]** Flat list: `parent` exists but no hierarchy, no balances, no drill-down to a ledger. A chart with no balances is a reference list, not a working screen.
- **P2 [O]** Headers ("Code", "Name", "Type", "System") are hard-coded English; `BoolChip` hard-codes "Yes"/"No".
- **P2 [I]** No search/filter; with 60+ seeded accounts plus bank accounts this is long.

**Cross-impact:** Account codes are looked up by literal code throughout posting (`_account(company, "1100")`, 1200, 2100, 1600…). Any future edit/rename UI must keep codes of system accounts immutable (already server-enforced). *HIGH* if account editing is added carelessly.

**Edge cases:** chart not seeded (handled: banner "no chart"); two admins add the same code; very long names; deactivating an account that is the default for a bank account (`bank_account` link) [V].

**Security:** read needs `CanViewFinancialReports`; write needs `CanPostJournals`. Conceptually fine. The UI shows no write controls, so role-gating is moot today.

**Automation:** none worth adding before editing exists; later: suggest a code from the type range.

**Tests:** list renders with system rows; list empty (no chart); duplicate code via API; delete in-use account → message; inactive account in journal picker.

**Scores:** purpose 8 · UX 5 · flow 4 · functionality 3 · business logic 6 · errors 5 · integration 6 · consistency 5 · a11y 5 → **4.9**. **Verdict: 🟡 READY WITH FIXES** (usable as a reference; not as a ledger manager).

---

## 2. Journals

**Purpose / user:** accountant posts manual vouchers; owner reviews. Primary action: New voucher → Save draft → Post → (Reverse).

**Flow:** list → dialog (date, narration, ≥2 lines, live balance alert) → draft saved → row action Post (confirm dialog) → POSTED → row action Reverse (confirm). Cancel closes the dialog.

**State machine [O]:** `DRAFT → POSTED → REVERSED`. No edit or delete of a draft (`http_method_names = get, post`). Reversal creates a new `JOURNAL_REVERSAL` entry dated the *original* date.

**Business logic [O]** (server): exactly one side per line; balanced; account/cost-centre/party must belong to the company; AR/AP/advance control accounts (1200, 2100, 2300, 1250) require a customer *or* supplier tag; post is blocked by CLOSED/SOFT_CLOSED period, GST period lock, `books_start_date`, and (if the company opts in) "must be inside an OPEN period"; posting clears the balance-rollup cache; an audit event is written.

**Findings**
- **P0/P1 [O] Any POSTED journal can be reversed from this screen, including system-generated ones.** The Reverse button shows for every `status === 'POSTED'` row, and the `reverse` action calls `PostingService.reverse` with no `source_type` check. `allow_soft_closed` is set to *true* for anything that is not `MANUAL_JOURNAL`, so a sales-invoice or receipt journal can be reversed **even in a soft-closed month**, leaving the invoice COMPLETED with no GL. Books Health then reports a documents↔GL mismatch, which **blocks period close** (`period_close_blockers`). A reversal entry itself is also reversible. Fix: only allow Reverse for `MANUAL_JOURNAL`, link system rows to their source document instead, and restrict `reverse` server-side.
- **P1 [O] The UI cannot post to AR/AP/advance accounts.** The form has no customer/supplier field, and the server rejects lines on 1200/2100/2300/1250 without a tag. A legitimate adjustment (e.g. write-off against a customer) fails with a 400 the form cannot satisfy.
- **P1 [O] Draft journals cannot be edited or discarded.** A typo leaves an orphan draft permanently in the list and consumes a number from a statutory series. Also the list is unbounded and unfiltered (`listJournals()`, virtualised only above 40 rows).
- **P1 [O] No journal detail.** Post/Reverse confirmations are blind: lines, amounts and accounts are not visible from the list. The list has no amount column and no source column (manual vs invoice vs depreciation), so users cannot tell what they are reversing.
- **P1 [O] Inactive accounts selectable** (see Chart of Accounts).
- **P2 [O]** Cost centre, per-line narration, reference and party are not exposed in the form though the backend accepts them; this is why Cost Centers looks purposeless.
- **P2 [O]** Dialog state (`error`, `lines`, `narration`) is not reset on cancel; reopening shows the previous attempt and old error.
- **P2 [O]** A line with an account but no amount produces a server error ("exactly one of debit or credit") that the client's balance check does not predict; blank-account lines are silently dropped, so a user can believe a line was saved that was not.
- **P2 [O]** Plain `<select>` account picker, no search, no recent accounts; `Number(x) || 0` accepts 0.001-style values that the server quantises.
- **P2 [I]** No filters (date, status, number, source), no export, no print.
- **P3 [O]** `StatusChip` colours `REVERSED` and `OPEN`-style statuses amber ("warning") along with unknown states.

**Cross-impact:** TB, P&L, balance sheet, Books Health, rollup cache (cleared on post), audit log, document-number series `JOURNAL_ENTRY`, period close. *HIGH.* A reversal affects every report for that date.

**Edge cases:** double click on Post/Reverse (the confirm dialog closes immediately and the mutation has no `isPending` guard on the button; server idempotency by status check makes a second call fail with "Only draft journals can be posted" → looks like an error although the first succeeded) **[O]**; two users post the same draft; back-dated into a closed month; narration 10k chars; debits 0.004 off; entry date earlier than `books_start_date`; user's role lacks `can_post_journals` but sees the button (**[O]** only `writesBlocked` is checked client-side).

**Error recovery:** errors are shown by `HelpErrorAlert` outside the dialog when closed and inside when open, which is good. Closed-period errors carry a help code.

**Security:** server permission is `CanPostJournals` for create/post/reverse, view-only otherwise. Fine. Hiding the button for non-posters would remove avoidable 403s.

**Automation:** copy last voucher; recurring journal template; auto-balance last line; account search with recent items.

**Tests:** unbalanced draft rejected; one-sided lines; post into soft-closed month (rejected for manual); reverse a manual journal; **reverse a sales-invoice journal (should be refused)**; AR line without party; inactive account; double-click post; post before books start; concurrent soft-close during post.

**Regression:** HIGH (touching `post`/`reverse` touches all modules).

**Scores:** purpose 8 · UX 5 · cognitive 6 · flow 6 · functionality 5 · logic 7 · data/state 6 · errors 7 · integration 6 · consistency 7 · a11y 5 → **6.0**. **Verdict: 🟡 READY WITH FIXES** (the reverse-anything hole must be closed first).

---

## 3. Cost Centers

**Purpose:** dimension for splitting P&L by branch/project. List + Add.

**Findings**
- **P1 [O]** `create` mutation has **no `onError`**: a duplicate code or any validation error does nothing visible; the dialog stays open and stays enabled.
- **P1 [O]** No edit, deactivate or delete in the UI, though `is_active`, `parent` and delete exist server-side. A wrongly named cost centre is permanent.
- **P1 [O]** Nothing in the product lets users *assign* a cost centre on manual journals (see Journals), and no report here shows cost-centre totals, so the feature has no visible payoff **[V: whether P&L has a cost-centre filter elsewhere]**.
- **P2 [O]** `parent` hierarchy not in the form; code auto-generated from name if blank (collision handling unknown **[V]**); hard-coded English ("No cost centers.", "Code", "Name", "Active").
- **P2 [O]** Add button does not check role (`CanPostJournals` needed on the server).

**Cross-impact:** invoices carry `cost_center` into postings (`invoice.cost_center`), so deleting or renaming one affects historical reports; deletion is PROTECT-guarded (good). *MEDIUM.*

**Tests:** duplicate code visible error; deactivate; delete in-use; non-poster role; code generated from "Café & Co".

**Scores:** purpose 6 · UX 4 · flow 4 · functionality 3 · logic 6 · errors 2 · integration 4 · consistency 5 · a11y 5 → **4.3**. **Verdict: 🔴 NOT READY** (silent failure + dead-end feature).

---

## 4. Fixed Assets

**Purpose:** register assets, see depreciation, dispose. Behind `ENABLE_FIXED_ASSETS` (off in pilot).

**State [O]:** `ACTIVE → DISPOSED`. Depreciation is posted monthly by a Celery task (`post_monthly_depreciation`), per month-end, prorated by days in the acquisition/disposal month, floored at salvage value, with a catch-up list for older months and `last_depreciation_error` for failures. Books Health raises `DEPRECIATION_FAILED` / `DEPRECIATION_CATCHUP` warnings.

**Findings**
- **P0 [O] Disposal proceeds can never be entered.** The page sends `proceeds: row.disposalProceeds`, a field that exists nowhere in the model or serializer; it is always undefined → 0. Selling an asset for ₹70,000 books the full net book value as a loss (account 5600), cash is not debited, and the confirm dialog says "Proceeds ₹0". The backend handles proceeds, gain/loss and cash vs bank correctly; the UI never asks.
- **P0/P1 [O] Acquiring an asset posts nothing.** `perform_create` only saves the register row. No journal debits 1600 Fixed Assets (no `"1600"` reference in purchase or any other posting path; only the chart seed, reports and the asset view). Yet depreciation posts Dr 5300 / Cr 1650, and disposal credits 1600 for the full cost. Unless the user separately journals the purchase into 1600, the balance sheet shows negative fixed assets after disposal and net fixed assets are understated by accumulated depreciation. *Needs verification* of how a capital purchase bill is expected to reach 1600; the D6 note ("post manually") suggests this is by design for the pilot, but the screen gives no instruction.
- **P1 [O] The "frozen after depreciation" rule exists only in the UI.** `FixedAssetSerializer` uses `fields="__all__"` with only company, depreciated_amount, status and disposed_at read-only. A PATCH can change cost, life, acquisition date, method, salvage or the three GL accounts after depreciation has posted, silently breaking the schedule.
- **P1 [O] Disposal is always dated today** (`timezone.localdate()`); no date field; a back-dated sale posts into the wrong month, or fails if the current month is closed.
- **P1 [O] Depreciation is invisible.** The table shows cost, date, life, status. Not shown: accumulated depreciation, net book value (both are available as `depreciated_amount` / `written_down_value`), method, last run, `last_depreciation_error`, catch-up months. Failures surface only in Books Health.
- **P1 [O] Skipped months are lossy.** A month that falls in a closed period is skipped and recorded as an error string (truncated to 500 chars); catch-up exists but is "explicit only" (`backfill_depreciation_catchup`), and nothing in the UI triggers it.
- **P2 [O]** Narration says "SLM depreciation" even for WDV assets. Form hides method, salvage, WDV rate, block key and the three accounts. No validation of cost > 0 or life > 0 on the API (**[V]**; `monthly_depreciation` with life 0 could divide by zero).
- **P2 [O]** Dispose uses `window.prompt`/`window.confirm` rather than the dialog used elsewhere; Save is not disabled by an empty/invalid life.
- **P3 [O]** Direct URL `/accounting/fixed-assets` is routed even when the flag is off (nav is hidden; the API returns 404, so the page shows a generic error).

**Cross-impact:** Balance sheet (tangible assets), P&L (5300, 5600, 5700), Books Health alerts, period close, nightly task. *HIGH* (when enabled).

**Edge cases:** disposal twice (guarded by status); cost fully depreciated; salvage ≥ cost; disposal in the same month as acquisition; leap-day proration; closed month; asset bought mid-month; asset disposed with proceeds > NBV (gain 5700).

**Security:** `CanPostJournals` for create/dispose; view for reports. Sensible. The `confirm: true` check is a server-side double-confirmation (good).

**Tests:** create → run depreciation → NBV; skipped closed month then catch-up; dispose with proceeds above/below NBV; dispose back-dated; PATCH cost after depreciation (should fail); flag off → 404 and nav hidden; zero-life asset.

**Scores:** purpose 7 · UX 4 · cognitive 6 · flow 4 · functionality 3 · logic 4 · data/state 4 · errors 4 · integration 3 · consistency 5 · a11y 4 → **4.4**. **Verdict: 🔴 NOT READY** (consistent with its "known limitation" status; do not enable beyond demo).

---

## 5. Accounting Periods

**Purpose / user:** owner locks months. Controls on one screen: books-close summary card, create period, FY-close, per-row Soft close and "Close together" (books + GST).

**State [O]:** `OPEN → SOFT_CLOSED → CLOSED` (no reverse). Server rules: owner-only; earlier open period must be closed first; period row locked during change; close is blocked by Books Health/GST critical alerts and (with Manufacturing) open work orders; overlapping periods rejected; GST period status joined by `YYYY-MM`.

**Findings**
- **P1 [O] Close-blocked errors are not actionable.** `assert_period_close_allowed` raises "Period close blocked due to health alerts: AR_CONTROL_MISMATCH, DOCS_GL_AR_MISMATCH" (codes only; the human `message` of each alert is dropped). `BooksCloseSection` shows totals and one docs↔GL line but never lists the blockers. Users learn the close failed, not why or where to fix it. Show `period_close_blockers` on the page before the user clicks.
- **P1 [O] UI offers actions the server refuses.** Buttons appear on every row; closing March while February is open returns "Close February first". Disable and explain per row.
- **P1 [O] No reopen.** The copy says closing "cannot be undone from the UI". A mistaken close (or an FY close, which zeroes P&L into 3100) needs engineering. At minimum an owner-only reopen with reason + audit entry; for FY close a reversal path.
- **P1 [O] Irreversible actions confirmed with `window.confirm`** (soft close, close, close-together, FY close), while Journals uses the app's `ConfirmDialog`. FY close is duplicated in Accounting Settings with a hard-coded English dialog. Native dialogs cannot be tested reliably, are blocked in some embedded contexts, and are weak on accessibility.
- **P1 [O] "Close together" is a two-step action in one call** (`close_period`): books close, then GST soft-close. If the second step fails after the first the response is atomic (decorator `@transaction.atomic`), good; but the UI does not say that GST ends in *soft-closed*, not closed, and the final GST "close" stays in the GST module. Confusing for users expecting a filed-and-locked month.
- **P2 [O]** Period creation is manual (name + two dates) one at a time; no "generate the financial year". The summary alerts (`gstStillOpen`, `booksStillOpen`) don't name the period.
- **P2 [O]** Status chip shows raw `SOFT_CLOSED`; OPEN and CLOSED both amber.
- **P2 [O]** `BooksCloseSection` fetches three full reports (trial balance, P&L, books health) just to show four numbers; slow for large ledgers and fully blocks the page behind a spinner.
- **P2 [O]** Unlabelled ordering of controls: create-period fields and FY-close field sit in one row with a single "Create" button; two date fields without labels linking them to their buttons.
- **P3 [I]** Past FY dates in `fyEnd` default to `nextIndianFyEnd()` — verify it picks the FY being closed, not the next one **[V]**.

**Cross-impact:** every posting module (sales, purchases, payments, inventory, payroll, depreciation, expenses *not enforced*), GST filing, FY close, Books Health, depreciation catch-up. *HIGH.*

**Edge cases:** two owners closing at once (row locked → second sees "already closed"); closing with drafts; closing when a bank statement is half-reconciled (not checked); periods with gaps; no period exists for a date (only an issue if `require_open_period_for_posting` is on); timezone at month boundary.

**Security:** server enforces `IsOwner` (stronger than the UI). Good. Accountants see read-only.

**Tests:** close out of order; close with AR mismatch (message content); concurrent post during close; reopen (when built); FY close with drafts; overlapping period create; non-owner API call.

**Scores:** purpose 7 · UX 4 · cognitive 4 · flow 5 · functionality 6 · logic 8 · data/state 7 · errors 4 · integration 8 · consistency 5 · a11y 4 → **5.6**. **Verdict: 🟡 READY WITH FIXES** (strong server rules, weak explanation and recovery).

---

## 6. Bank Reconciliation (GL ↔ statement)

**Purpose:** match GL journal lines on a bank/cash account to bank statement lines. A second, separate reconciliation lives at `/payments/reconciliation` (receipts/payments ↔ statement lines).

**Flow:** pick GL account + statement → *Create session* → pick session → pick one journal line + one statement line → *Match*. Sessions list underneath.

**Data / state [O]:** session status has `OPEN` (and others in the model) but **no endpoint or button changes it**. `gl_balance` is the all-time debit−credit of the account; `statement_balance` is the sum of statement line *amounts* (not closing balance), both frozen at creation.

**Findings**
- **P1 [O] The session balances are not reconciliation figures.** GL balance is "as of now, all dates"; the statement figure is the net movement of the file. Their difference means nothing. A real reconciliation compares the statement closing balance with the GL balance **as at the statement date**, and shows outstanding items.
- **P1 [O] No completion.** No "difference = 0" indicator, no finalise/lock, no unmatch. A mistaken GL match is permanent from this screen (the payments side has `unmatch`; this side has none).
- **P1 [O] Two reconciliations share state inconsistently.**
  - Payments recon refuses lines already `MATCHED` (good: a GL match sets `match_status=MATCHED`, which protects the payments side).
  - The GL `match` action **does not check `match_status`**, only whether a journal line already points at the bank line. A line matched in payments recon (receipt) can therefore also be matched to a journal line → counted twice.
  - Payments `unmatch` sets the line `UNMATCHED` and deletes the `ReconMatch` but never clears `JournalLine.bank_statement_line` for a line also reconciled by GL recon, leaving the journal line "reconciled" to a line that now looks unmatched.
  - Payments recon on cheque bounce writes `bank_statement_line` onto the reversal's journal line directly, so GL recon and payments recon both write the same field.
- **P1 [I]** Matching one line at a time through three dropdowns is not workable for a statement with hundreds of lines; no auto-suggest by amount/date/reference, no multi-select, no one-to-many (bank charges, batched deposits).
- **P2 [O]** Statement lines whose `match_status` is `SUGGESTED` are treated as unmatched (filter is "not MATCHED") — acceptable, but the screen does not surface suggestions. Sign convention (debit positive) is implicit; mismatch error is generic ("amounts differ").
- **P2 [O]** Session list is cryptic (`#12 · OPEN`); account/statement columns show ids [V: serializer returns ids, not names]. Hard-coded English throughout.
- **P2 [O]** Picker of "cash/bank accounts" is a heuristic: bank-linked, or code starts 11/12, or name contains cash/bank; falls back to all ASSET accounts.
- **P3 [O]** Info banner when no statements exist is good; "distinct from payments reconciliation" banner is useful but placed after the form.

**Cross-impact:** `JournalLine.reconciled_at/bank_statement_line`, `BankStatementLine.match_status`, payments recon queues and dashboard counts, cash book. *MEDIUM→HIGH* (double counting).

**Edge cases:** statement imported twice; partial statement; line amount differs by 0.01; foreign-company ids (IDOR attempt is checked); statement voided after matches (payments blocks voiding while MATCHED); same GL line matched by two users concurrently (select_for_update guards).

**Security:** match/create need `CanPostJournals`; view needs financial-report view. IDOR protections present (company filters on both lines).

**Automation:** auto-match exact amount ± date; match by reference; propose bank charges as a journal; carry-forward of unmatched items; one-click "create journal for unmatched statement line".

**Tests:** match happy path; amount mismatch; same bank line matched in payments recon then GL recon (should be refused); payments unmatch after GL match; foreign ids; session create twice for same pair; 2,000-line statement.

**Scores:** purpose 6 · UX 3 · cognitive 3 · flow 3 · functionality 3 · logic 4 · data/state 4 · errors 5 · integration 4 · consistency 5 · a11y 4 → **4.0**. **Verdict: 🔴 NOT READY** as a reconciliation tool; it is a manual line-linker.

---

## 7. Expenses

**Purpose / user:** owner or staff records cash/bank expenses (rent, tea, fuel) with category, party, amount, attachment. Register with category and date filters.

**State [O]:** no status; create / edit / hard delete. Number from an `EXPENSE` series. Audit entry on create.

**Findings**
- **P0 [O] Expenses never reach the general ledger or P&L.** `Expense` is read by exactly three consumers: its own CRUD view, bank-feed matching (`banking/services.py`), and the cash-position list (`reporting/transactions.py`). There is no posting method, no signal, and `accounting/reports.py` never reads the model. With books enabled, an ₹80,000 rent expense appears on this screen and on the Day Book but **not** in the trial balance, P&L, balance sheet, cash/bank GL balance or bank reconciliation. P&L overstates profit, GL cash is overstated, and GL bank recon will show phantom differences. **[V]** I found no mention in `FREEZE_SCOPE.md`/`TESTING_STRATEGY.md` that this is an accepted limitation; confirm with the product owner whether another route (e.g. purchase bill, manual journal) is the intended way to book expenses. If so, the screen must say so.
- **P0 [O] Edit and delete bypass period locks.** No guard on date or period; a closed or GST-filed month's expense list can be changed or deleted (hard delete, with only an audit CREATE entry; update/delete audit coverage **[V]**).
- **P1 [O] No payment mode / bank account / paid-by.** Cash vs bank is not captured, so neither the Day Book direction nor a future GL posting can be correct; bank-feed matching must guess.
- **P1 [O] No tax fields.** No GST amount/ITC, no TDS. The docstring says "not a GST purchase invoice", but users will enter GST-bearing bills here; the input tax is lost and the amount is treated as pure expense.
- **P1 [O] "Manage categories" is shown to any user who can create payments, but category create/update/delete is `IsOwner` on the server** → a non-owner accountant gets a 403 when adding. The dialog lists categories as read-only text boxes: no rename/deactivate/delete.
- **P2 [O]** Register capped at `pageSize: 100` with no paging, total or count; filtered total not shown; no search or export; attachment shown as "Attachment #id", no preview/download; cancelling the dialog after upload leaves an orphan file; deleting an expense leaves the file.
- **P2 [O]** Form: amount column labelled "Total"; party is free text (no link to Suppliers); duplicate detection absent (same date, party and amount); save button not disabled while `writesBlocked` (subscription) although the API enforces it.
- **P2 [O]** Route registered twice in `App.tsx` (outside and inside the accounting gate) — Expenses is reachable with accounting off, which is intended but untested.
- **P2 [V]** Cross-tenant `category`/`attachment` ids are accepted by plain `PrimaryKeyRelatedField` in `ExpenseSerializer` (other serializers use `CompanyPrimaryKeyRelatedField`). On PostgreSQL RLS blocks it; on SQLite dev there is no such protection.
- **P3 [O]** Hard-coded text mix; date inputs with `InputLabelProps` boilerplate; page-level error state hides the filters on query failure.

**Cross-impact:** Day Book, bank-feed matching (`AaTransaction.matched_expense`), cash book, any future P&L/GST report, document series. *HIGH* (financial reporting integrity).

**Edge cases:** amount 0.005; huge amounts (14,2 limit); future date; back-dated into closed period; deleting an expense already matched to a bank feed transaction (`matched_expense` FK behaviour **[V]**); two users editing; category deleted while in use (PROTECT); file upload fails mid-form.

**Security:** write uses `CanCreatePayments` (a payments permission for an accounting object — **[V]** intended?), read uses `CanViewFinancialReports`. Hard delete by anyone with create rights is a fraud risk without an approval/soft-delete.

**Automation:** category → default ledger; remember last category per party; duplicate warning; OCR of the attached bill; recurring expenses (rent).

**Tests:** create with books on → expect journal and report movement; edit amount → expect repost/reversal; closed-period edit/delete refused; non-owner adds category; filter + paging beyond 100; bank-feed match then delete; attachment cancel.

**Regression:** HIGH once GL posting is introduced (back-fill and cutover).

**Scores:** purpose 8 · UX 6 · cognitive 7 · flow 6 · functionality 4 · logic 2 · data/state 4 · errors 6 · integration 2 · consistency 6 · a11y 5 → **5.1** (logic and integration drag it). **Verdict: 🔴 NOT READY** while books are on.

---

## 8. Day Book

**Purpose:** "what happened on this date". **[O]** In fact a *cash-position document list*: sales invoices, receipts, payments, expenses, returns, credit/debit notes, with Inflow / Outflow / Net cards.

**Findings**
- **P1 [O] It is not ledger-based.** It reads documents (`sales_side_transactions`), not `JournalEntry`. Manual journals, purchase bills, depreciation, bank charges, inventory adjustments and FY closing entries never appear. It cannot be tied to the trial balance, and accountants (who expect a day book to be the chronological journal) will distrust it. Either rename ("Daily cash summary") or rebuild on journal lines with Dr/Cr.
- **P1 [O] Direction logic is internally odd.** Inflow counts `PAYMENT_IN` only; outflow counts `PAYMENT_OUT`, `EXPENSE`, `SALES_RETURN` and `CREDIT_NOTE`. Returns and credit notes are *non-cash* adjustments, counted as outflow, while a debit note falls into a `signed = amount` branch that affects neither card. The disclaimer says "Sales invoices appear as documents" but they are excluded from Net, so Net is not "day profit" nor "cash", it is a hybrid. Cheques count only when CLEARED, which differs from receipts in the Money module [V].
- **P1 [O] Expenses shown here are not in the books** (see Expenses) — so the Day Book and the trial balance disagree by design on the same day.
- **P2 [O]** Single date only; no previous/next, range, search, export or print; invalid date silently becomes today (`_parse_date(...) or date.today()`); today is the server date, not the company timezone **[V]**.
- **P2 [O]** Changing the date swaps the whole page for a spinner (`isLoading` early return; the filter disappears); previous data isn't kept (`keepPreviousData` unused).
- **P2 [O]** "Customer" column for all parties; no direction column; status raw text; "Open" link only when `sourcePath` exists (expenses link to `/accounting/expenses` without selecting the record).
- **P3 [I]** Throttle scope `heavy_reports` for a one-day query is fine; for a ledger-based rebuild index on `(company, entry_date)` already exists on `JournalEntry`.

**Cross-impact:** reads Sales, Payments, Banking (cheque status), Expenses, notes. It writes nothing. *LOW regression, HIGH trust impact.*

**Edge cases:** day with 5,000 transactions (no paging); date in a different FY; cancelled/void documents (excluded? **[V]**); cheque cleared next day (moves day).

**Security:** `CanViewFinancialReports` only. Fine; shows party names and amounts, so staff without finance view are correctly blocked.

**Tests:** day with each document type; cheque pending vs cleared; credit note effect on Net; manual journal day (documents the gap); invalid date param; 1,000-row day.

**Scores:** purpose 5 · UX 6 · cognitive 7 · flow 6 · functionality 4 · logic 4 · data/state 6 · errors 6 · integration 4 · consistency 6 · a11y 6 → **5.4**. **Verdict: 🟡 READY WITH FIXES** if relabelled; 🔴 if marketed as an accountant's day book.

---

## 9. Cross-cutting findings

1. **Reconciling "documents" and "ledger" is the central weakness.** Expenses (documents only), Day Book (documents only), Fixed Assets (register only, acquisition not posted), Bank Recon (two engines, shared flags). Only Journals/Periods are ledger-native.
2. **Guard coverage is uneven.** Period locks are enforced by `PostingService.post` and the manual journal post, but not by Expense edit/delete, and bypassed by reversing system journals in soft-closed months.
3. **Server stronger than UI in permissions, weaker in invariants.** Owner-only period close and `CanPostJournals` are enforced server-side; but "frozen after depreciation" and "don't reverse system journals" exist only (or not at all) in the UI/serializer.
4. **Recovery is thin.** No reopen period, no unmatch (GL side), no edit/discard draft, no category/cost-centre edit.
5. **Consistency:** four confirmation styles (`ConfirmDialog`, `window.confirm`, `window.prompt`, ad-hoc dialog), inconsistent error surfaces (cost centre silent), hard-coded English in Chart, Cost Centers, Bank Recon, Settings, `BoolChip`; inconsistent `writesBlocked` and role checks.
6. **Status presentation:** `StatusChip` maps unknown statuses to amber, so OPEN, SOFT_CLOSED, CLOSED, ACTIVE, DISPOSED, REVERSED all look like warnings; raw enum text is shown.
7. **Accessibility / responsive [I]:** native `confirm`/`prompt`; multi-field rows (Periods: 6 controls; Bank Recon: 5 selects) that wrap on phones; unlabelled relationships between date inputs and action buttons; money cells aren't right-aligned in the shared table [V]; no row-level labels for icon-less text buttons ("Edit"/"Delete" repeated).
8. **Not verifiable without running the app:** actual wrap on mobile, keyboard order, focus return from dialogs, contrast of amber chips, timing of the virtualised table.

---

## 10. Cross-module impact map

| Change here | Lands in | Rating |
|---|---|---|
| Period close/soft-close | all posting modules, GST filing, payroll, depreciation, Books Health | HIGH |
| Journal post/reverse | TB, P&L, BS, AR/AP control, Books Health, rollup cache, audit | HIGH |
| Reverse of a system journal | source document ↔ GL drift → blocks period close | HIGH |
| Expense create/edit/delete | Day Book, bank-feed match, cash book; **not** GL/P&L | HIGH |
| Asset create/dispose/depreciate | BS, P&L, Books Health alerts, nightly task | HIGH (flag on) |
| Bank recon match | `JournalLine`/`BankStatementLine` flags, payments recon queue | MEDIUM-HIGH |
| Chart / cost-centre edits | all code lookups, documents carrying cost centre | MEDIUM |
| FY close | 3100 retained earnings, all periods, GST periods | HIGH |

---

## 11. Master problem register

| # | Pri | Screen | Problem | Impact | Recommendation |
|---|---|---|---|---|---|
| 1 | P0 | Expenses | No GL posting, no P&L effect (confirm intent) | Profit/cash overstated; phantom bank-recon diffs | Post Dr expense / Cr cash-or-bank, reverse on edit/delete, cutover + back-fill, CA sign-off |
| 2 | P0 | Expenses | Edit/delete ignore period & GST locks; hard delete | Closed months altered silently | Apply `assert_period_allows_money_amend`; soft-delete with reason |
| 3 | P0 | Fixed Assets | Proceeds never sent (`disposalProceeds` undefined) | Every sale booked as full loss | Proceeds, date, cash/bank fields in dispose dialog |
| 4 | P0/P1 | Journals | Any posted journal incl. system ones can be reversed (soft-close bypass) | Doc↔GL drift, blocks period close | Allow reverse only for `MANUAL_JOURNAL`; server check |
| 5 | P1 | Fixed Assets | Acquisition never posted to 1600 | Negative/understated fixed assets | Post acquisition (or instruct and validate) |
| 6 | P1 | Fixed Assets | Frozen fields editable via API | Schedule corruption | Server-side lock when `depreciated_amount>0` |
| 7 | P1 | Journals | Cannot tag customer/supplier; AR/AP lines rejected | Adjustments impossible in UI | Add party picker when control account chosen |
| 8 | P1 | Journals | No draft edit/discard; no detail view; unbounded list | Clutter, blind confirmation | Edit/delete DRAFT, lines drawer, filters, paging |
| 9 | P1 | Journals/Chart | Inactive accounts postable | Deactivation ineffective | Reject inactive accounts in serializer and `post` |
| 10 | P1 | Periods | Close-blocked error shows codes only | User cannot fix | Show blocker messages on page and in error |
| 11 | P1 | Periods | No reopen; native confirms; duplicate FY close | Irreversible mistakes | Owner reopen with reason + audit; one FY close; `ConfirmDialog` |
| 12 | P1 | Periods | Out-of-order close buttons offered | Avoidable errors | Disable with reason |
| 13 | P1 | Bank Recon | Balances meaningless; no finish/unmatch | Cannot prove a reconciliation | Statement closing vs GL as-at date, outstanding list, finalise, unmatch |
| 14 | P1 | Bank Recon | Double-match / stale flags vs payments recon | Double counting | Check `match_status`; clear journal-line link on unmatch |
| 15 | P1 | Bank Recon | One-at-a-time manual matching | Unusable at volume | Auto-suggest, multi-select, create-journal-from-line |
| 16 | P1 | Day Book | Document-based; hybrid Net | Does not tie to books | Rebuild on journal lines or relabel |
| 17 | P1 | Fixed Assets | Depreciation/NBV/errors not visible | Failures unseen | Add columns, error badge, catch-up action |
| 18 | P1 | Expenses | No payment mode, GST/ITC, TDS | Wrong cash/tax | Add mode/bank/tax block |
| 19 | P1 | Expenses | Manage categories shown to non-owners; add-only | 403s, permanent typos | Role-gate; edit/deactivate |
| 20 | P1 | Chart | Read-only | No custom ledgers | Create/rename/deactivate with guard |
| 21 | P1 | Cost Centers | Silent create failure; no edit/deactivate; unused | Looks broken/pointless | `onError`, edit/deactivate, journal line field, report |
| 22 | P2 | Expenses | 100-row cap, no total/search/export; orphan files | Truncation, clutter | Paging, totals, cleanup |
| 23 | P2 | All | Hard-coded English; four confirm styles; uneven role/`writesBlocked` checks | Inconsistent | Shared gate hook, i18n pass |
| 24 | P2 | Shared | StatusChip colours; raw enums | Misleading statuses | Map OPEN/CLOSED/ACTIVE etc. |
| 25 | P2 | Periods | Manual period creation; `BooksCloseSection` loads 3 full reports | Slow, tedious | "Generate FY"; lightweight summary endpoint |
| 26 | P2 | Day Book | Single date, spinner swap, silent bad date | Polish/trust | Range, previous/next, `keepPreviousData`, 400 on bad date |
| 27 | P2 | Journals | Dialog state not reset; blank-account lines dropped silently | Confusion | Reset on close; validate |
| 28 | P2 | Expenses | Plain FK fields (cross-tenant on non-RLS DB) [V] | Security hardening | `CompanyPrimaryKeyRelatedField` |
| 29 | P3 | Fixed Assets | Route reachable with flag off; `prompt` for dispose | Polish | Route guard; dialog |

---

## 12. The three changes that matter most

1. **Close the books/documents gap for Expenses** (post to GL with period locks, payment mode, reversal on edit/delete). *Correctness, business value.* Everything downstream (P&L, GST, bank recon, Day Book) is wrong until this is settled.
2. **Fix the guard holes in Journals and Fixed Assets:** restrict Reverse to manual journals; send disposal proceeds/date; lock frozen asset fields server-side; reject inactive accounts. *Correctness.* Each is small and prevents silent damage to closed or reconciled periods.
3. **Make close and reconciliation workflows finishable:** list blockers and out-of-order warnings on Periods, add reopen with audit, and give Bank Recon a statement-balance vs GL-as-at difference, unmatch and finalise. *User outcome.* This is where month-end time is actually spent.

---

## 13. Consolidated scores (0–10)

| Screen | Overall | Verdict |
|---|---:|---|
| Chart of Accounts | 4.9 | 🟡 |
| Journals | 6.0 | 🟡 |
| Cost Centers | 4.3 | 🔴 |
| Fixed Assets | 4.4 | 🔴 (flag-off by design) |
| Accounting Periods | 5.6 | 🟡 |
| Bank Reconciliation | 4.0 | 🔴 |
| Expenses | 5.1 | 🔴 |
| Day Book | 5.4 | 🟡 |
| **Module overall** | **5.0** | **🔴 NOT READY** |

## 14. What remains unverified

- No browser/mobile/accessibility run; no tests executed.
- Whether any hook posts expenses outside the files searched (none found by grep across the backend).
- How a capital purchase is meant to reach account 1600.
- Update/delete audit coverage for Expenses; `matched_expense` on-delete behaviour.
- `nextIndianFyEnd()` behaviour; company timezone handling in Day Book.
- Account-type immutability and duplicate-code behaviour in the Chart.
- Tally/GST exports and the Money module were not reviewed.
