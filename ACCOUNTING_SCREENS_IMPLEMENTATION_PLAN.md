# Accounting Screens: Implementation Plan (Path to 10)

**Document:** `ACCOUNTING_SCREENS_IMPLEMENTATION_PLAN.md`
**Date:** 2026-10-16 · **Revision:** 1
**Status:** 🟡 **IN PROGRESS.** D1–D9 accepted as recommended (2026-10-16). Built, uncommitted: ACS-00 (partly), ACS-01, ACS-10 to 16. See the completion records below. Not started: ACS-20 onwards.
**Source review:** [docs/reviews/ACCOUNTING_SCREENS_DEEP_REVIEW_2026-10-16.md](docs/reviews/ACCOUNTING_SCREENS_DEEP_REVIEW_2026-10-16.md). Every work package (WP) cites the review finding it closes (`R#` = row in the review's problem register).

Screens in scope: Chart of Accounts, Journals, Cost Centers, Fixed Assets, Accounting Periods, Bank Reconciliation, Expenses, Day Book.


## Completion record: ACS-15 and ACS-16 (2026-10-17, uncommitted)

**Design choice that differs from the plan:** the on/off switch is the company's `expense_gl_start_date` alone (empty = register only), not a separate feature flag plus a date. One setting cannot disagree with itself, and the date is what the back-fill and the Books Health check need anyway. The category-to-ledger mapping lives in a new accounting table (`ExpenseCategoryAccount`), not on `ExpenseCategory`, because `masters` cannot depend on `accounting` without a migration cycle.

| WP | What was built | Where |
|---|---|---|
| ACS-15 posting | An active expense dated on or after the start date posts `Dr <expense ledger> / Cr Cash (1100) or the bank's own ledger`, dated on the expense date. Edit reverses the old entry on its own date and posts the new one; an edit that changes nothing in the ledger posts nothing (notes, attachment). Void reverses. Moving an expense before the start date takes it out of the books. A closed month or locked GST month refuses it and leaves no entry (expense and entry are saved in one transaction). The ledger is the expense's own choice, else the category's mapping, else 5000 Expenses. | `accounting/expense_posting.py` (new), `accounting/views.py` |
| ACS-15 switch and back-fill | Accounting settings returns and accepts `expense_gl_start_date` (owner only; accounting must be on; not before the books start date; empty switches off) and returns the pending count and total. `POST /accounting/expenses/post-pending/` previews (`dry_run`) or posts every pending expense, reporting a closed month instead of forcing it; `manage.py backfill_expense_postings --company N [--dry-run]` does the same from the command line. Both are safe to run again. | `accounting/views.py`, `accounting/management/commands/backfill_expense_postings.py` |
| ACS-15 health | Books Health shows a warning `EXPENSE_MISSING_POSTING`; for the month being closed, an unposted expense of that month or earlier is a close blocker (a later month does not block an earlier close). | `accounting/services.py` |
| ACS-15 mapping | `GET/POST/DELETE /accounting/expense-category-accounts/`: one expense ledger per category, owner-only to change, expense-type active accounts only. | `accounting/views.py`, `serializers.py` |
| ACS-16 capture | Payment mode (cash/bank), bank account (required for bank, dropped for cash, remembered as the last used), expense ledger override, amount must be at least 0.01, and `GET /expenses/duplicates/` (same date, amount and party, ignoring voided rows) drives a one-time duplicate warning with "Save anyway". | `accounting/serializers.py`, `views.py`, `ExpensesPage.tsx` |
| UI | Expenses form with the new fields and the ledger it will post to; "In books" column once posting is on; Manage categories lets the owner pick each category's ledger; Accounting settings has an "Expenses in the books" block (start date, pending count, preview, post). English and Hindi strings added (Hindi unreviewed). | `ExpensesPage.tsx`, `components/accounting/ExpensePostingSettings.tsx`, `AccountingExtraPages.tsx`, `i18n/*` |
| Migrations | `accounts/0062_company_expense_gl_start_date`, `accounting/0018_expense_ledger_fields` (Expense payment mode, bank, ledger, journal link; `ExpenseCategoryAccount`), `core/0060_rls_expense_category_account` (tenant RLS for the new table). | |

**Tests:** `backend/tests/test_acs_expense_gl.py` (23, all pass): switch off means no entry; cash and bank postings; mapping and override; wrong-type and inactive ledger refused; edit amount, mode and date; void; closed month leaves nothing behind; start-date validation; pending, preview, post and re-run; back-fill with a closed month; the command; Books Health warning and period-close blocker; duplicate check; owner-only mapping. With the earlier suites, 342 backend tests pass in the accounting, period, expense, settings and health areas. Web: 112 tests pass across i18n, phase, accounting and Day Book areas, including 5 new Expenses tests and 4 for the settings block. `tsc -b` clean, lint 0 errors, `ruff check .` clean, `makemigrations --check` clean, OpenAPI snapshot and types regenerated.

**Still open for ACS-15/16:**
- **CA sign-off** before any company turns posting on: it changes reported profit. Ship with every company's date empty (it is, by default).
- The "no GST/ITC on expenses" decision (D2) holds: amounts post gross to the expense ledger. The tax split stays in ACS-17.
- Not run: PostgreSQL lane (concurrent double-submit of one expense), and a real-browser pass.
- A period-close error still lists codes only (`EXPENSE_MISSING_POSTING`), not the sentence; that is ACS-30.
- Back-filling a long history one expense at a time is fine for hundreds of rows; for tens of thousands it should be chunked.

## Completion record: Phase 0 and Phase 1a (2026-10-16, uncommitted)

**Done and verified:** ACS-01, ACS-10, ACS-11, ACS-12, ACS-13, ACS-14, and the part of ACS-00 listed below.
**Not started:** ACS-15 (expense ledger posting), ACS-16 (expense capture fields), and everything from Phase 2 on.

| WP | What was built | Where |
|---|---|---|
| ACS-10 | Reverse is refused for any journal not posted as `MANUAL_JOURNAL` (code `journal_system_not_reversible`, names the source document). A reversal entry cannot be reversed again. Journal API now returns `source_label`, `source_path`, `can_reverse`. The Journals list shows a Source column that links to the document, and the Reverse button only on manual journals. | `accounting/views.py`, `accounting/journal_sources.py` (new), `accounting/serializers.py`, `JournalsPage.tsx` |
| ACS-11 | Inactive accounts are refused in manual journals and in `PostingService.post`. Reversals are exempt so an entry that used an account before it was switched off can still be unwound. | `accounting/serializers.py`, `accounting/services.py` |
| ACS-12 | Disposal takes a date (not before purchase, not in the future), proceeds, and where the money went (cash, bank aggregate, or a specific bank account). The dialog previews net book value and gain or loss and asks for the asset name. The old `disposalProceeds` bug is gone. The server posts on the chosen date, so period locks apply to it. | `accounting/views.py`, `FixedAssetsPage.tsx` |
| ACS-13 | Cost > 0, life ≥ 1, salvage < cost, rate 0–100. After depreciation has posted, the API refuses changes to cost, date, life, method, salvage, rate and the three accounts (name stays editable). A disposed asset cannot be edited. `last_depreciation_error` and the catch-up list are read-only. | `accounting/serializers.py` |
| ACS-14 | Expenses are checked against period and GST locks on create, edit (old and new date) and void. Delete became a void with a required reason (`POST /expenses/{id}/void/`; `DELETE` still works and needs a reason). Voided rows are hidden unless `include_void=1`, keep their number, are audited, and are excluded from the cash-position list and from bank-feed matching. The Expenses page has a Void dialog with a reason, a "Show voided" toggle, and shows "Manage categories" to owners only (matches the server). Migration `accounting/0017_expense_void.py`. | `accounting/models.py`, `views.py`, `serializers.py`, `reporting/transactions.py`, `banking/services.py`, `ExpensesPage.tsx` |
| ACS-00 (part) | `AccountSelect` (searchable, active accounts only, keeps a saved inactive one visible), `canPostJournals` and a single write gate on Journals and Fixed Assets, `ConfirmDialog` reason support, phase `StatusChip` with real colours and translated labels (Open, Soft-closed, Closed, Active, Disposed, Reversed, Void, Posted, Matched), translated `BoolChip`, Periods page now uses `ConfirmDialog` instead of `window.confirm` (FY close asks for the FY end date). English and Hindi strings added (Hindi needs native review, QOS-0126). | `web/src/components/accounting/*`, `ConfirmDialog.tsx`, `phaseShared.tsx`, `PeriodsPage.tsx`, `utils/permissions.ts`, `i18n/en.ts`, `i18n/hi.ts` |

**Tests:** `backend/tests/test_acs_phase1_integrity.py` (23 tests, all pass). Eighteen neighbouring accounting, period, journal, persona and workflow suites: 186 passed. Web: new tests for `AccountSelect`, `ConfirmDialog` reason, `StatusChip`/`BoolChip`, Journals (manual-only Reverse, source link, role gate), Fixed Assets disposal, Periods dialog, Expenses void and category gate; 48 web files / 263 tests in the phase, accounting, reports/DayBook, utils and i18n areas pass. `tsc -b` clean, `npm run lint` 0 errors (22 existing warnings), `ruff` clean on touched files, `makemigrations --check` clean for `accounting`. `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` regenerated.

**Left out of ACS-00 on purpose or by time (still to do):** `DataTable` money right-alignment and per-row action labels; moving the remaining hard-coded English on Chart of Accounts, Cost Centers, Bank Recon and Accounting Settings to `t()`; `AccountSelect` on Bank Recon and Fixed Assets forms; the `window.confirm` in Accounting Settings (disable accounting) and the Settings copy of FY close.
**Known gaps found while building:**
- Disposal does not post the part-month depreciation for the month of sale. The nightly job only depreciates ACTIVE assets, so that partial month is lost unless depreciation is run before disposal. Belongs with ACS-54.
- Concurrency tests (double dispose, double void) ran on SQLite only; the Postgres lane was not run.
- No real-browser check was done for the changed screens.
- A bank GL account for a disposal is created on demand by the existing `_bank_gl_account` helper; that helper reactivates an inactive per-bank ledger. Kept as is.

---

## 1. What "10" means here, and the honest ceiling

A score of 10 is not reachable by code alone. Three things need people, and they cap the score until done:

| Needs a person | Why | Cap if missing |
|---|---|---|
| **CA / accountant sign-off** on expense posting, fixed-asset acquisition posting, bank-recon rules, FY-close reversal | They change reported profit and balance sheet | Logic and integration stay ≤ 8 |
| **Native Hindi review** of all new strings (existing QOS-0126) | Consistency with the rest of the product | Consistency ≤ 9 |
| **Real-device and assistive-technology pass** (phone width, keyboard-only, screen reader) | I can verify with a browser pane and axe-style checks, not with a real screen reader | Accessibility ≤ 9 |

So the plan targets **9.0–9.5 per screen, with the last point gated on the three items above**, and defines exit criteria (section 9) rather than a self-assigned number.

### Target scorecard

| Screen | Now | After Phase 1 (integrity) | After Phase 2–3 (workflow) | After Phase 4 (polish, sign-offs) |
|---|---:|---:|---:|---:|
| Chart of Accounts | 4.9 | 5.5 | 8.5 | 9.5 |
| Journals | 6.0 | 7.5 | 9.0 | 9.5 |
| Cost Centers | 4.3 | 4.8 | 8.5 | 9.2 |
| Fixed Assets | 4.4 | 6.5 | 8.8 | 9.2 |
| Accounting Periods | 5.6 | 6.0 | 9.0 | 9.5 |
| Bank Reconciliation | 4.0 | 5.0 | 8.8 | 9.3 |
| Expenses | 5.1 | 7.5 | 9.0 | 9.5 |
| Day Book | 5.4 | 5.4 | 9.0 | 9.4 |
| **Module** | **5.0** | **6.0** | **8.9** | **9.4** |

---

## 2. Decisions needed (recommended default in bold)

| # | Question | Options | Recommended | Why |
|---|---|---|---|---|
| **D1** | Should an Expense post to the ledger? | (a) Yes, with a cutover date and flag · (b) No; relabel Expenses as a "cash memo" and require a purchase bill/journal | **(a)** | The screen is called Expenses and sits under Accounting. A register that is invisible to P&L misleads. |
| **D2** | Tax on expenses in v1 | (a) Amount is gross; no ITC · (b) GST/ITC and TDS fields now | **(a) in v1, (b) as WP-ACS-17** | Ledger correctness first; tax split changes GSTR-3B inputs and needs CA review. |
| **D3** | Reversing system journals (invoice, receipt, depreciation…) | (a) Manual journals only; system ones via cancelling the source document · (b) Allow with reason | **(a)** | Prevents document↔ledger drift that blocks period close. |
| **D4** | Fixed-asset acquisition | (a) Post on register with a funding source (Already booked / Cash-Bank / Supplier payable) · (b) Link to a purchase bill line · (c) Leave manual (D6 as documented) | **(a), with "Already booked" as the default for existing assets** | Closes the 1600 gap without forcing double-posting. (b) can follow when purchase capex exists. |
| **D5** | Bank recon target model | (a) Single shared match service for GL and payments recon, with statement closing balance and finalise · (b) Keep two engines, patch checks | **(a)** | The two engines already write the same fields; patching leaves the root cause. |
| **D6** | Day Book | (a) Rebuild on journal lines (Dr/Cr), keep the current page as "Daily cash summary" · (b) Relabel only | **(a)** | An accountant's day book must tie to the trial balance. |
| **D7** | Period reopen | (a) Owner-only reopen, reason + audit; CLOSED→SOFT_CLOSED→OPEN one step at a time; refused if GST period is closed or a later period is closed · (b) No reopen | **(a)** | Mistaken closes are otherwise a support ticket. |
| **D8** | Chart editing | (a) Create/rename/deactivate non-system accounts; code and type frozen once postings exist · (b) Read-only | **(a)** | The API already supports it. |
| **D9** | Expense delete | (a) Soft void with reason + reversing journal · (b) Hard delete | **(a)** | Hard delete of a financial record with no trail is a control gap. |

---

## 3. Delivery structure

Five phases. Phase 1 can ship on its own and removes every P0.

```
Phase 0  Foundations (shared kit, characterization tests)        ~4 d
Phase 1  Integrity: all P0 + guard holes                          ~14 d
Phase 2  Core workflows: Journals, Periods, Bank Recon            ~20 d
Phase 3  Completeness: Chart, Cost Centers, Fixed Assets,
         Day Book, Expense extras                                 ~18 d
Phase 4  Hardening: a11y/responsive, i18n, perf, docs, sign-offs  ~8 d
```

Days are engineer-days for one developer including tests; they are estimates, not commitments. Phases 2 and 3 packages are largely independent per screen and can run in parallel once Phase 0 lands (one writer per set of files).

### Dependency graph

```
ACS-00 ─┬─> every UI package
ACS-01 ─┘
ACS-10, 11, 12, 13 (independent, small)         ──> Phase 1 release
ACS-14 ─> ACS-15 ─> ACS-16 ─> ACS-17 (expenses chain)
ACS-20..24 (journals)        needs ACS-10, 11
ACS-30..35 (periods)         needs ACS-14 (expense lock) for full coverage
ACS-40..46 (bank recon)      independent; 41 before 42-45
ACS-50 (chart) ─> ACS-51 (cost centres use AccountSelect)
ACS-52..55 (fixed assets)    needs ACS-12, 13
ACS-60 (day book)            needs ACS-15 for expenses to appear
```

---

## 4. Phase 0: Foundations

### ACS-00 Shared accounting UI kit (R23, R24, R27)
**Problem:** four confirmation styles, hard-coded English, inconsistent role and subscription gating, amber status chips, no account search.
**Build (frontend):**
- `components/accounting/AccountSelect.tsx`: searchable autocomplete over active accounts, shows code + name + type, recents, optional `typeFilter`, `allowInactive` (default false). Replaces the plain `<select>` in Journals, Bank Recon, Fixed Assets.
- `hooks/useAccountingPermissions.ts`: returns `{canPostJournals, isOwner, canCreateExpenses, writesBlocked}` once, from the auth context and subscription gate; every action button uses it.
- `StatusChip` mapping extended: `OPEN` neutral/outlined, `SOFT_CLOSED` warning, `CLOSED` success/locked icon, `ACTIVE` success, `DISPOSED` default, `REVERSED` default with strike, `VOID` default; human labels via `t()` (never raw enums). `BoolChip` labels via `t()`.
- `DataTable`: right-align `money` columns, add `aria-label` on row action buttons using a `rowLabel(row)` callback, optional server pagination slot.
- `ConfirmDialog` becomes the only confirmation for irreversible actions; add `requireReason` and `requireTyping` variants (used by disposal, reopen, void, FY close).
- i18n: move all hard-coded strings in the eight screens to `t()` (en + hi keys; hi marked for review).
**Acceptance:** no `window.confirm`/`window.prompt` in `pages/phase/*Accounting*`, `FixedAssets`, `Periods`, `Journals`, `Expenses`; lint clean; `tsc -b` clean.
**Tests:** component tests for `AccountSelect` (search, inactive hidden, keyboard), `ConfirmDialog` variants, `StatusChip` mapping table.

### ACS-01 Characterization and harness
Write tests that pin today's correct behaviour before changing it, so refactors cannot regress guards: manual journal post (period, GST, books-start, balance), period close ordering, reverse of manual journal, depreciation idempotency and catch-up, GL match amount/company checks.
Create a shared test factory `accounting_company(accounting=True, with_bank=True, periods=...)`. Run the concurrency tests on PostgreSQL (they are Postgres-only per earlier findings).
**Acceptance:** suite green on SQLite and Postgres; new tests tagged `accounting_guard`.

---

## 5. Phase 1: Integrity (closes every P0 and guard hole)

### ACS-10 Restrict reversal to manual journals (R4)
**Backend:** `JournalViewSet.reverse`: refuse unless `source_type == "MANUAL_JOURNAL"` (code `journal_system_not_reversible`, message names the source document and where to cancel it). Refuse reversing a `JOURNAL_REVERSAL` entry. Remove the soft-closed bypass for manual reversals (already `allow_soft_closed=False` for manual). Internal callers of `PostingService.reverse` unchanged.
**Frontend:** Reverse button only for `sourceType === 'MANUAL_JOURNAL' && status === 'POSTED'`; for system rows show "Open source" link (`sourcePath`) instead. Serializer exposes `source_type`, `source_label`, `source_path`, `reversed_entry_number`.
**Acceptance:** API returns 400 for system journals; UI shows the link; existing document cancel flows still reverse their own entries.
**Tests:** reverse manual (ok), reverse invoice journal (400), reverse a reversal (400), soft-closed month manual reverse (400), document cancel in soft-closed month still works.
**Risk:** MEDIUM. Any script relying on reversing system entries through this endpoint breaks (grep callers; none expected in `web/`).

### ACS-11 Reject inactive accounts (R9)
**Backend:** `JournalLineSerializer.validate_account` and `PostingService.post` reject `is_active=False` unless the call is a reversal of an entry that already used it (`allow_inactive=True` for `reverse`). Same for fixed-asset account FKs and bank-linked accounts.
**Frontend:** `AccountSelect` hides inactive.
**Tests:** inactive account refused in manual journal, refused in depreciation setup, allowed in reversal.

### ACS-12 Fixed-asset disposal inputs (R3)
**Frontend:** replace `window.prompt` with a Dispose dialog: disposal date (default today, not before acquisition date), sale proceeds (default 0), received into (Cash / Bank account select), live preview "Net book value ₹X · Proceeds ₹Y → Gain/Loss ₹Z". Typing the asset name remains as the confirmation. Remove `row.disposalProceeds`.
**Backend:** `dispose` accepts `disposal_date` and `bank_account` (validated company-scoped; maps to the bank's GL account), keeps `cash_account_code` for compatibility; entry dated `disposal_date`; refuse before acquisition date and in locked periods (via `PostingService`); final partial-month depreciation is posted before disposal if the month is open (reuse `_prorate_days_in_service`).
**Acceptance:** disposal with proceeds above/below NBV produces the right gain/loss line and cash line; back-dated disposal posts in the chosen period.
**Tests:** gain, loss, zero proceeds, bank vs cash, before acquisition (400), closed period (400), twice (400).

### ACS-13 Fixed-asset server-side locks and validation (R6)
**Backend:** `FixedAssetSerializer`: `acquisition_cost > 0`, `useful_life_months ≥ 1`, `salvage_value < cost`, `wdv_annual_rate` 0–100. On update, if `depreciated_amount > 0` or any depreciation journal exists, reject changes to cost, date, life, method, salvage, rate and the three accounts (only `name` and notes editable). Explicit fields list instead of `__all__`; `last_depreciation_error` and catch-up read-only.
**Tests:** PATCH cost after depreciation (400), valid edits before depreciation, zero life (400).

### ACS-14 Expense period locks and void (R2, D9)
**Model:** `Expense.status` (`ACTIVE`/`VOID`), `voided_at`, `voided_by`, `void_reason`. Migration with default `ACTIVE`.
**Backend:** create/update/void call `assert_period_allows_money_amend(company, expense_date)` (and for update, the *old* date too). `DELETE` becomes void (requires `reason`); voided rows are excluded from lists unless `?include_void=1`. Audit CREATE/UPDATE/VOID with before/after.
**Frontend:** Delete → Void dialog with required reason; voided rows hidden by default with a toggle.
**Tests:** edit/void inside closed period (400), void keeps number (no reuse), audit entries written, list excludes void.

### ACS-15 Expense ledger posting (R1; needs D1 decision and CA sign-off)
**Model/migrations:**
- `ExpenseCategory.account` (FK `Account`, nullable, default resolved to 5000 "Expenses" if empty); seed sensible mappings for default categories (Rent, Fuel, Salaries…) to new or existing 5xxx accounts.
- `Expense.payment_mode` (`CASH`/`BANK`), `Expense.bank_account` (FK, null), `Expense.journal_entry` (FK, null).
- `Company.expense_gl_start_date` (null = off). Flag `ENABLE_EXPENSE_GL` (company flag, default off).
**Service:** `PostingService.post_expense(expense, user)`: `Dr category.account / Cr 1100 Cash or bank GL (per-bank ledger via existing _bank_gl_account)`, source `EXPENSE`, purpose `CREATE`, dated `expense_date`, narration number + party. Idempotent via the existing source key. Edit: reverse the old entry and post a new one in one transaction (or repost delta when only notes change). Void: reverse. Rule: only expenses dated on/after `expense_gl_start_date` post.
**Back-fill:** management command `backfill_expense_postings --company --from-date --dry-run`; preview page section (extends the existing accounting back-fill banner) reports count and total and whether the trial balance still ties.
**Reports:** P&L and trial balance need no change (they read the ledger). `reporting/transactions` Day Book/expense list gains a "Posted to books" badge source.
**Books Health:** new alert `EXPENSE_MISSING_POSTING` for flag-on expenses without a journal; included in period-close blockers (mirrors `DOCUMENT_MISSING_POSTING`).
**Acceptance:** with the flag on, an expense moves the P&L, the trial balance stays balanced, the bank/cash GL falls, edit/void keep it balanced, closed periods refuse, back-fill is idempotent.
**Tests:** post/edit amount/edit category/edit date across months/void; cash vs bank; flag off no posting; back-fill idempotent; TB balanced property test; concurrency (double submit) on Postgres.
**Risk:** HIGH. Changes reported profit for existing customers. Ship dark (flag off), enable per company after the back-fill preview and CA sign-off. Document the cutover in `docs/FREEZE_SCOPE_COVERAGE.md` and a QOS entry for the sign-off.

### ACS-16 Expense capture fields (R18 part)
**Frontend/backend:** Payment mode (Cash/Bank) and Bank account selector (default: last used), required when GL posting is active; expense account shown read-only from the category with an override for owners; party picker with "Supplier" autocomplete or free text; duplicate warning (same date, party, amount); amount > 0 and ≤ 14,2 digits validated both sides; `writesBlocked` respected.
**Tests:** validation matrix, duplicate warning, default payment mode.

### Phase 1 exit
All P0 rows (R1–R4) closed; guards in R6, R9 closed; Phase 1 release behind flags where needed. Re-run the review for the eight screens' guard sections.

---

## 6. Phase 2: Core workflows

### Journals

**ACS-20 Draft lifecycle (R8).** Backend: allow `PUT/PATCH` and `DELETE` on `DRAFT` only (`http_method_names` extended; guard on status; audit). Numbering: draft keeps its number; deleting a draft releases it only if it is the latest in the series, otherwise it is marked `VOID`-style cancelled so the sequence has no silent gap (follow `DocumentNumberService` conventions already used for other documents). Frontend: Edit and Discard on draft rows; dialog resets on open/close (R27).
**ACS-21 Journal detail drawer (R8).** New `GET /journals/{id}/` already returns lines; add a side drawer from any row: header (number, date, source link, posted by/at, reversal link), lines with account name, Dr/Cr, party, cost centre, totals. Post/Reverse confirmations show a compact summary of lines.
**ACS-22 Line fields (R7, R21).** Form adds per-line customer/supplier (auto-required when a control account 1200/2100/2300/1250 is chosen, with the right type), cost centre (`AccountSelect`-style picker), and line narration (new `JournalLine.narration` char field, migration). Header adds reference text. Client validation mirrors server rules including "exactly one side"; blank-account lines are flagged, not silently dropped.
**ACS-23 List usability.** Server filters (`status`, `date_from/to`, `number`, `source_type`, `q` narration, `account`), server pagination with total, amount column (total debit), source column, export (CSV/XLSX using the existing note-register export pattern). `listJournals` stops being unbounded.
**ACS-24 Draft guard rails.** Double-click protection (`isPending` disables), idempotency key on create, "already posted" response treated as success with a refresh, dirty-form warning when closing the dialog.
**Acceptance:** accountant can create, edit, discard, post and reverse a manual journal that touches AR with a customer tag without leaving the page; every row shows its source; list works with 10k journals.
**Tests:** draft edit/delete permissions and status guards; party-required matrix; filter/pagination; export; double click; number sequence behaviour on discard.

### Accounting Periods

**ACS-30 Close-readiness endpoint (R10).** `GET /periods/{id}/close-readiness/` returns ordered `blockers` (code, severity, human message, `fix_path`, count/amount where available), `earlier_open_period`, `gst_status`, and `can_soft_close`, `can_close`. Reuses `period_close_blockers`. `assert_period_close_allowed` error text now includes messages, not only codes.
**ACS-31 Periods page redesign (R10, R12).** One table: Period · Books status · GST status · Readiness (✓ / "n blockers") · Actions. Row expander shows blockers with "Fix" links (to AR mismatch, docs↔GL, WIP, depreciation errors, unreconciled bank lines as an advisory). Buttons are disabled with a visible reason ("Close March first"). Replaces `BooksCloseSection` with a lightweight endpoint `GET /accounting/close-summary/` (cached, one query set) instead of three full reports.
**ACS-32 Reopen (R11, D7).** `POST /periods/{id}/reopen/` (owner-only, requires reason): CLOSED→SOFT_CLOSED, SOFT_CLOSED→OPEN; refused if the GST period for that month is CLOSED/filed or a *later* period is CLOSED; FY-close journals prevent reopening periods inside that FY unless the FY close is reversed (ACS-34). Audit event with reason; Books Health cache cleared; notification to other owners/accountants.
**ACS-33 Generate year (R25).** `POST /periods/generate/` creates the 12 monthly periods of a chosen FY (skips existing, rejects overlap); UI "Create financial year" replaces one-at-a-time as the primary path (single create stays as advanced).
**ACS-34 FY close consolidation and reversal (R11).** One FY-close location (Periods page); Accounting Settings links to it. Preview step shows income/expense totals moving to 3100, drafts that would block, and periods to be locked. Add owner-only "Reverse FY close" which reverses the closing journals and reopens the FY's periods, subject to the same GST guard. CA sign-off required before enabling.
**ACS-35 Dialogs and copy.** All confirmations via `ConfirmDialog`; plain-language explainer for Soft close vs Close vs Close with GST (what it blocks, who can undo); the GST outcome ("GST month soft-closed; file and lock it in GST") stated explicitly.
**Acceptance:** an owner can see exactly why a month cannot close and click through to fix it; a mistaken close can be undone within the rules; no native dialogs remain.
**Tests:** readiness for each blocker type; out-of-order disabled; reopen matrix (GST closed, later closed, FY closed); generate year idempotent; FY close preview/reverse; concurrency of close vs post (Postgres).

### Bank Reconciliation

**ACS-40 Shared match service (R14, D5).** New `banking/match_service.py` (or `accounting/bank_match.py`) as the only code that sets `BankStatementLine.match_status`, `JournalLine.bank_statement_line/reconciled_at` and `ReconMatch`. Rules: a statement line is matched by exactly one engine at a time; GL match requires `match_status != MATCHED`; payments match requires no linked journal line; unmatch clears *both* sides; cheque-bounce linkage goes through the service. Data migration/management command `repair_bank_match_state` finds and reports lines with inconsistent state (matched in both, journal line linked to an UNMATCHED line) for review before fixing.
**ACS-41 Real reconciliation session (R13).** Session captures `statement_date` and `statement_closing_balance` (from statement metadata when present, otherwise entered, with a prompt on first use); computes `gl_balance_as_at` (posted lines ≤ statement date), `reconciled_total`, `outstanding_deposits`, `outstanding_payments`, `difference`. Status machine `OPEN → IN_PROGRESS → RECONCILED → FINALISED`; finalise requires difference = 0 (or an owner-approved write-off journal for small differences, configurable), locks matches, records who/when. `FINALISED` sessions are read-only except by reopen (owner, reason).
**ACS-42 Matching workspace (R15).** Replace three dropdowns with a two-pane view: statement lines left, unreconciled GL lines right, with amount/date/reference filters, keyboard selection, running totals of the selection, "Match selected" (1:1, many:1, 1:many when totals equal), and per-line unmatch. Large lists paginate server-side (extends `unreconciled-lines`).
**ACS-43 Suggestions and automation.** Server endpoint proposes matches by exact amount ± N days and reference/narration tokens; "Accept all high-confidence" with preview; rules remembered (e.g. narration "UPI-XYZ" → customer receipt) only suggested, never auto-applied silently.
**ACS-44 Create-from-statement-line.** For unmatched bank lines (charges, interest, unrecorded receipts) a drawer builds a pre-filled journal (bank vs chosen account, date from the line) and matches it in one transaction, using `PostingService` so period guards apply.
**ACS-45 Session list and context.** Show account name, statement name/period, status, difference, owner/date; filter and open a session directly; header banner explains the two engines once, with deep links.
**ACS-46 Reporting.** Reconciliation statement printable/exportable (PDF/XLSX): statement balance, outstanding items, GL balance, difference, sign-off.
**Acceptance:** an accountant can reconcile a 300-line month in one session with a zero difference, finalise it, and later see the same state from both reconciliation screens; no line can be double-matched.
**Tests:** state-machine matrix; both-engine conflict cases (matched in payments then GL and reverse); unmatch clears both; many:1 and 1:many totals; as-at balance with back-dated entries; finalise lock; 2,000-line performance budget (< 1 s list, < 300 ms match); concurrency (two users, same line) on Postgres.

### Phase 2 exit
Journals, Periods, Bank Recon reach ≥ 8.8 in re-review; no open P1 on these screens.

---

## 7. Phase 3: Completeness

### Chart of Accounts (D8)
**ACS-50.** Add/Edit/Deactivate UI for non-system accounts: code, name, type, parent, bank link, active. Server rules: code unique per company (clear message); code and type frozen once the account has postings; cannot deactivate with a non-zero balance unless a "transfer balance" journal is created (offer one-click draft); system accounts show a lock icon. List gains hierarchy (tree with indent), balance column (from the rollup, as-at date selector), search, type filter, inactive toggle, export, and a row link "View ledger" (to the existing ledger report) . Header columns via `t()`.
**Tests:** frozen-after-postings matrix; duplicate code; deactivate-with-balance; tree rendering; permissions.

### Cost Centers
**ACS-51.** Fix silent failure (`onError`, inline field errors); edit (name, code, parent), deactivate/reactivate, delete-if-unused with the existing PROTECT message translated; parent picker; usage counts (journal lines, invoices) in the table. Cost centre selector wired into Journals (ACS-22), Expenses (optional field, posted through to the GL line when ACS-15 is on), and a **Cost-centre P&L** report (income/expense by cost centre for a date range) reachable from the page header. Hard-coded strings to `t()`.
**Tests:** duplicate code error visible; deactivate hides from pickers but keeps history; report totals equal the P&L when all lines are tagged; unallocated bucket shown.

### Fixed Assets
**ACS-52 Visibility (R17).** Columns: cost, accumulated depreciation, net book value, method, last depreciation month, status badge for `last_depreciation_error` and catch-up months. Detail drawer with the depreciation schedule (posted months with journal links, future months projected) and disposal summary. Summary cards: total cost, accumulated, NBV, this month's charge.
**ACS-53 Acquisition posting (R5, D4).** Register form adds "Funding": *Already booked* (no entry; default for imports/existing), *Paid from cash/bank* (Dr 1600 / Cr cash or bank), *Supplier payable* (Dr 1600 / Cr 2100 with supplier tag). Entry dated at acquisition date, through `PostingService`; asset stores `acquisition_journal`. Existing assets get a one-time reconciliation view: "Fixed asset register vs GL 1600/1650" with the difference and a button to draft the correcting journal.
**ACS-54 Depreciation operations (R17).** "Run depreciation now" (owner/accountant, month selector, dry-run preview), "Post missed months" button for catch-up with preview and result, error list per asset with the exact month and reason; narration uses the real method (SLM/WDV); Books Health alert links here.
**ACS-55 Form completeness.** Expose method, salvage value, WDV rate, asset/accumulated/expense account (advanced section), asset category defaults (computers 3 years, vehicles, furniture) as presets; validation mirrors ACS-13. Route guard: `/accounting/fixed-assets` redirects with a message when `ENABLE_FIXED_ASSETS` is off.
**Acceptance:** register ties to GL 1600/1650 (shown on the page); depreciation failures are visible and fixable from the page; disposal verified in ACS-12.
**Tests:** funding variants; register↔GL tie-out; catch-up posting; WDV narration; flag-off redirect; leap-year proration; salvage floor.
**Note:** because Fixed Assets is a documented pilot limitation (D6), release it behind `ENABLE_FIXED_ASSETS` and update `docs/FREEZE_SCOPE.md` / QOS-0067 only after CA sign-off on ACS-53.

### Day Book (D6)
**ACS-60.** New backend `reporting/day_book.py`: ledger-based Day Book for a date or range: every posted journal line (company-wide) with voucher number, type (Sales, Receipt, Payment, Purchase, Journal, Depreciation, Expense…), account, party, Dr, Cr, narration, source link; totals with Dr = Cr check; filters by voucher type, account, cost centre, party; pagination; XLSX/PDF export; previous/next day; range up to a month. Keep the current cash view as **"Daily cash summary"** (own tab) with corrected semantics: inflow = receipts + cash sales; outflow = payments + expenses; returns, credit and debit notes are shown separately as "adjustments", not in cash Net; label what counts. Server validates the date (400 on bad input), uses the company timezone for "today". `keepPreviousData` so the page does not blank on date change.
**Cross-check:** a banner on the page shows "Ledger total for the day equals trial-balance movement" and flags a mismatch.
**Tests:** every source type appears; Dr = Cr per day; manual journal and depreciation appear; expense appears only once posted; date validation; timezone boundary; large day pagination; tie-out with trial balance movement.

### Expense extras
**ACS-17 Tax and categories (R18, R19, R22; D2 phase b).**
- Categories: manage dialog supports rename, deactivate, account mapping (ACS-15), reorder; shown only to owners (matches server); non-owners can pick existing categories only.
- Tax: optional GST amount and rate split (CGST/SGST/IGST), "ITC eligible" toggle, supplier GSTIN; when eligible and GL posting is on, post input tax to the existing ITC accounts (1310/1320/1330) so GSTR-3B inputs stay consistent; TDS amount and section, posting to 2265 with the party tag. This part needs CA sign-off and a GST-return regression run.
- Register: server pagination with total count and **filtered total**, search (party, number, notes), date presets, category and payment-mode filters, XLSX export, attachment open/download link, attachment cleanup on cancel (delete orphan upload), bulk attach.
- Recurring expenses (rent, subscriptions): template with schedule, "create due expenses" confirmation list.
- Serializer hardening: `CompanyPrimaryKeyRelatedField` for `category`, `attachment`, `bank_account` (R28).
**Tests:** category permission matrix; tax posting totals; register paging/totals; export; cross-tenant ids rejected on SQLite and Postgres; recurring generation idempotent.

---

## 8. Phase 4: Hardening

### ACS-70 Accessibility and responsive
Keyboard-only walkthrough for each screen (tab order, focus return after dialogs, Esc/Enter behaviour); labels and `aria-describedby` for helper text; row action button labels; live-region announcements for async results; contrast check on chips; tables collapse to card lists below 600 px for Journals, Expenses, Bank Recon; 44 px touch targets; no horizontal page scroll at 375 px. Run axe in Playwright for all eight routes.

### ACS-71 Performance
Budgets: Journals list 10k rows < 500 ms server, first paint < 1.5 s; Chart with 500 accounts < 300 ms; Day Book 5k lines paginated < 600 ms; close-summary < 400 ms with caching; bank workspace 2k lines smooth scrolling (virtualised). Add indexes found by `EXPLAIN` (journal line `(company, account, entry)`, expense `(company, status, expense_date)`).

### ACS-72 Cross-module regression pass
Re-run sales, purchase, payments, inventory, payroll posting suites and GST return suites after ACS-10/11/14/15/40; verify trial balance, P&L, balance sheet, Books Health and AR/AP control on the demo company before and after; verify document cancel flows.

### ACS-73 Documentation and tracking
- Update `docs/FREEZE_SCOPE_COVERAGE.md` (new section for this plan), `docs/TESTING_STRATEGY.md` gaps register, QOS backlog entries (re-mine; do not hand-edit generated `docs/PRODUCT_QUALITY_BACKLOG.md`).
- Regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` with `manage.py spectacular` (CI diffs them).
- User-facing help text for Periods, Reconciliation, Expenses.

### ACS-74 Sign-offs (people)
CA review of: expense posting and tax split, fixed-asset acquisition, FY close reversal, reconciliation write-off rule. Native Hindi review (extends QOS-0126). Real-device pass. Record each in the completion record.

---

## 9. Exit criteria (the definition of "close to 10")

1. **Correctness:** zero known P0/P1 defects from the review; trial balance balanced and equal to P&L-derived totals on a seeded year of mixed activity (property test); documents↔GL drift alert empty after every flow in the test matrix.
2. **Guards:** every money-moving action across the eight screens passes through the period, GST-period, books-start and inactive-account guards (checked by a single contract test that iterates the API routes).
3. **Recovery:** each irreversible action has a documented undo path or an explicit reason it has none (void, reverse, reopen, unmatch, finalise-reopen, FY-close reverse).
4. **UX:** no native dialogs, no silent failures, no raw enums, every error has a message and a next step, empty/loading/error states on every list, mobile at 375 px usable.
5. **Quality gates:** backend suite green on SQLite and Postgres; `tsc -b`, web lint (0 errors) and web tests green; Playwright smoke for the eight routes; axe with no serious violations; OpenAPI regenerated.
6. **Evidence:** browser verification screenshots for each screen at desktop and mobile widths recorded in the completion record.
7. **Sign-offs:** CA, Hindi reviewer, device pass recorded (cap lifted only then).

---

## 10. Test strategy summary

| Layer | What | Where |
|---|---|---|
| Unit | serializers, posting maths (gain/loss, prorating, as-at balance), state machines | `backend/accounting/tests`, `backend/banking/tests` |
| API contract | permissions per role (owner, accountant, staff), status guards, filters, pagination | pytest + DRF client |
| Property | TB always balanced; every posted journal Dr = Cr; reconciled items never exceed statement lines | hypothesis-style loops over seeded data |
| Concurrency | close vs post, double match, double submit | Postgres-only marked tests |
| Frontend | component and page tests (Vitest/RTL), including dialogs and error paths | `web/src/**.test.tsx` |
| E2E | create expense → see P&L; journal → post → reverse; month close with blocker → fix → close → reopen; reconcile a statement → finalise | Playwright (extends the accounting golden path) |
| Migration | forward on a copy of demo data; back-fill idempotency | scripted |

Known gotchas from earlier work, to apply: use a private test DB for pytest, run `tsc -b` (not `tsc -p .`), keep web lint at zero errors, mind the `node_modules` junction when running web tests from a worktree, and run Postgres-only concurrency tests explicitly.

---

## 11. Rollout and risk

| Item | Mechanism | Risk | Mitigation |
|---|---|---|---|
| Expense posting (ACS-15) | Company flag + cutover date + dry-run back-fill | HIGH (changes profit) | Dark launch; per-company enable after preview and CA sign-off; kill-switch keeps register working |
| Reverse restriction (ACS-10) | Immediate | MEDIUM (scripts) | Grep callers; release note |
| Draft delete and numbering (ACS-20) | Immediate | MEDIUM (series gaps) | Follow existing `DocumentNumberService` rules; test sequences |
| Period reopen / FY reverse (ACS-32/34) | Owner-only; FY reverse behind a flag | HIGH (reopens filed periods) | GST-closed guard; audit; notify; CA sign-off |
| Bank match service (ACS-40) | Repair command first, then switch | HIGH (shared flags) | Run `repair_bank_match_state` in report mode on production data; feature flag the new workspace; keep old screen reachable one release |
| Fixed assets (ACS-52–55) | Behind `ENABLE_FIXED_ASSETS` | LOW in pilot | Stays off in pilot profile |
| Tax on expenses (ACS-17) | Separate flag `ENABLE_EXPENSE_TAX` | HIGH (GSTR inputs) | Own regression of GSTR-3B; CA review |

Migrations (new): `accounting` (Expense status/void/payment mode/bank/journal link, JournalLine narration, FixedAsset acquisition_journal, BankReconSession statement date/closing balance/finalised fields), `masters` (ExpenseCategory.account), `accounts` (Company.expense_gl_start_date). All additive and nullable; RLS policies added for any new tenant tables.

---

## 12. Suggested sequencing and parallelism

| Sprint | Work | Notes |
|---|---|---|
| 1 | ACS-00, 01, 10, 11, 12, 13, 14 | One developer; all small; ships Phase 1a |
| 2 | ACS-15, 16 (dark) + ACS-20..24 (Journals) | Two writers: expenses backend vs journals; no shared files except `AccountSelect` |
| 3 | ACS-30..35 (Periods) + ACS-40, 41 (recon core) | Periods UI vs bank backend |
| 4 | ACS-42..46 (recon UI) + ACS-50, 51 (Chart, Cost Centers) | |
| 5 | ACS-52..55 (Fixed Assets) + ACS-60 (Day Book) + ACS-17 (expense extras) | |
| 6 | ACS-70..74 | Browser verification, sign-offs, release notes |

Each sprint ends with a re-review of the touched screens against the original 20-section prompt, and a completion record appended to this document (as in the credit-note plan).

---

## 13. Work-package index

| WP | Title | Screen | Closes | Phase | Est. days |
|---|---|---|---|---|---:|
| ACS-00 | Shared UI kit | All | R23, R24, R27 | 0 | 3 |
| ACS-01 | Characterization tests | All | — | 0 | 1.5 |
| ACS-10 | Reverse restriction | Journals | R4 | 1 | 1.5 |
| ACS-11 | Inactive accounts | Journals/Chart | R9 | 1 | 1 |
| ACS-12 | Disposal inputs | Fixed Assets | R3 | 1 | 2 |
| ACS-13 | Asset locks and validation | Fixed Assets | R6 | 1 | 1 |
| ACS-14 | Expense locks and void | Expenses | R2 | 1 | 2 |
| ACS-15 | Expense ledger posting | Expenses | R1 | 1 | 5 |
| ACS-16 | Expense capture fields | Expenses | R18 | 1 | 1.5 |
| ACS-20 | Draft lifecycle | Journals | R8 | 2 | 2 |
| ACS-21 | Detail drawer | Journals | R8 | 2 | 1.5 |
| ACS-22 | Line fields (party, cost centre) | Journals | R7, R21 | 2 | 2.5 |
| ACS-23 | Filters, paging, export | Journals | R8 | 2 | 2 |
| ACS-24 | Draft guard rails | Journals | R27 | 2 | 1 |
| ACS-30 | Close-readiness endpoint | Periods | R10 | 2 | 2 |
| ACS-31 | Periods page redesign | Periods | R10, R12, R25 | 2 | 3 |
| ACS-32 | Reopen | Periods | R11 | 2 | 2 |
| ACS-33 | Generate year | Periods | R25 | 2 | 1 |
| ACS-34 | FY close consolidation and reversal | Periods | R11 | 2 | 3 |
| ACS-35 | Dialogs and copy | Periods | R11 | 2 | 1 |
| ACS-40 | Shared match service and repair | Bank Recon | R14 | 2 | 3 |
| ACS-41 | Real reconciliation session | Bank Recon | R13 | 2 | 3 |
| ACS-42 | Matching workspace | Bank Recon | R15 | 2 | 4 |
| ACS-43 | Suggestions | Bank Recon | R15 | 2 | 2 |
| ACS-44 | Create-from-line | Bank Recon | R15 | 2 | 1.5 |
| ACS-45 | Session list and context | Bank Recon | R13 | 2 | 1 |
| ACS-46 | Reconciliation report | Bank Recon | R13 | 2 | 1.5 |
| ACS-50 | Chart management | Chart | R20 | 3 | 4 |
| ACS-51 | Cost centre completeness and report | Cost Centers | R21 | 3 | 3 |
| ACS-52 | Asset visibility | Fixed Assets | R17 | 3 | 2 |
| ACS-53 | Acquisition posting | Fixed Assets | R5 | 3 | 3 |
| ACS-54 | Depreciation operations | Fixed Assets | R17 | 3 | 2 |
| ACS-55 | Asset form completeness | Fixed Assets | R29 | 3 | 1.5 |
| ACS-60 | Ledger-based Day Book | Day Book | R16, R26 | 3 | 5 |
| ACS-17 | Expense tax, categories, register | Expenses | R18, R19, R22, R28 | 3 | 5 |
| ACS-70 | Accessibility and responsive | All | — | 4 | 3 |
| ACS-71 | Performance | All | — | 4 | 1.5 |
| ACS-72 | Cross-module regression | All | — | 4 | 2 |
| ACS-73 | Docs, OpenAPI, QOS | All | — | 4 | 1 |
| ACS-74 | Sign-offs | All | — | 4 | people |
| | **Total** | | | | **~83 days** |

---

## 14. Open items that block or shape the plan

1. Decisions D1–D9 (defaults above). D1 and D4 are the ones that must not be assumed silently.
2. CA availability for sign-offs (ACS-15, 17, 34, 53, 41 write-off rule).
3. Whether the statement import already stores a closing balance and statement date (`BankStatement` model not inspected in this review). If it does, ACS-41 shrinks by about a day; if not, the import flow needs the fields too.
4. Whether any external script or integration calls `journals/{id}/reverse/` for system entries (affects ACS-10 release note).
5. Whether the `Reports` module should own the new ledger Day Book route (`/reports/day-book`) or keep it under Accounting; the plan keeps the existing path and adds the daily cash view as a tab.
