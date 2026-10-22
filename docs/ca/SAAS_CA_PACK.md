# CA review pack — one engagement for SaaS launch (WP-F9 / DIM6-17)

**For:** the practising CA engaged for launch. **Prepared:** 2026-10-22. **Status:** ready to send;
nothing in it is signed yet.

This pack replaces seven separate requests with one engagement. Each section says what BizBoard
does, where the automated evidence is, what to try on the demo company, and what we need from you.
Please return a signed copy of section 9 (or written changes against any item).

## How to review

1. We give you a login to **hosted staging** (`docs/ops/HOSTED_STAGING.md`) with two demo
   companies: *CA Review — Trading* (books on) and *CA Review — Manufacturing* (books on, costing
   switch on). Seeded with `seed_staging`, `seed_manufacturing_demo` and a simulated month.
2. Every number below can be reproduced from the screens: Reports → Trial balance / P&L / Balance
   sheet / GST worksheets, and Accounting → Journals (each entry links to its document).
3. Automated evidence = tests that run on every change. We list them so you can see what is
   already checked mechanically; you are not asked to read code.

## 1. Tax invoice presentation (F1–F8, F12) — existing sheet

Use `docs/ca/CA_SIGN_OFF_CHECKLIST.md` rows 1–9 as they stand: every PDF/DB/preview cell is backed by
a passing test. Needed from you: eyeball the live staging PDFs once, sign F9, and confirm the F12
decision (additional charges non-taxable for the pilot).

## 2. GST returns worksheets (QOS-0004 / H-05)

BizBoard prepares GSTR-1 and GSTR-3B worksheets; filing stays on the GST portal (freeze C1).
- Evidence: GSTR snapshots pinned in tests; output GST in the ledger is checked to equal the tax on
  every posted invoice (`gl.sales_output_gst_ties_to_invoices`, nightly).
- Try: close one month on the trading demo; compare worksheet totals with the GST control accounts
  (2210/2220/2230/2270) on the trial balance.
- Needed: confirm you could file from these worksheets (B2B, B2C, HSN, credit notes, ITC).

## 3. Money hub wording (QOS-0129, items M1–M5)

Items M1–M5 in `docs/ca/CA_SIGN_OFF_CHECKLIST.md`. Decision needed with the founder: should payables
be shown net of advances paid?

## 4. Accounting screens (QOS-0130)

Expense posting and its tax, fixed-asset acquisition (funding source), year-end close reversal, and
the bank-reconciliation write-off rule. Completion record: `ACCOUNTING_SCREENS_IMPLEMENTATION_PLAN.md`.
Needed: run the posting examples there on the demo company; sign or return changes **before any
company sets an expense start date**.

## 5. Stock write-offs in the ledger (flag `ACCOUNTING_POST_STOCK_ADJUSTMENTS`)

Today stock adjustments, count differences, expiry and serial write-offs change stock but are not
posted (the Trial balance says so under *Not in these books yet*). With the flag on: loss
Dr 5450 Inventory shrinkage / Cr 1400 Inventory; gain the reverse; at the movement's cost.
- Evidence: `inventory` invariants; `backfill_stock_adjustment_journals` catches up history.
- Needed: approve the accounts and the valuation basis, so we can turn the flag on by default.

## 6. Production costing (QOS-0141, flag `MFG_COSTING_GL`)

Section 4.14 of `docs/MANUFACTURING_IMPLEMENTATION_PLAN.md` and its completion record: material issue
(WIP 1450 / raw material), receipt of finished goods, overhead and labour absorption (5410–5430),
close variance (5440), standard-cost revaluation (1400 against 5420).
- Try: `simulate_manufacturing_month` on the manufacturing demo; check WIP is zero for closed work
  orders (`manufacturing.closed_wo_has_zero_wip`) and the variance postings.
- Needed: sign off the accounts and journals **before any company gets the costing switch**.

## 7. Warranty, commission and renewals (QOS-0136)

Walk one warranty job, one billed contract and one supplier debit note; confirm the stock and GST
effect (`backend/tests/test_ccj_jobs.py`).

## 8. "Amount involved" on Needs attention (QOS-0138)

Check each basis label and one merged customer row against the ledger; confirm the dashboard
receivable total reconciles with the aging buckets (`projection.ar_dashboard_equals_aging`).

## What already holds mechanically (for context)

- The database refuses a posted journal entry that is unbalanced or empty (migration
  `accounting/0023`).
- Every night, every company is checked: trial balance = 0, receivables and payables in the ledger
  equal the documents, output GST equals invoice tax, stock balances equal movements
  (`docs/accounting/LEDGER_COVERAGE_MAP.md` lists every posting and its check).
- Every company posts to the ledger from day one, even with the accounting screens switched off
  ("shadow books"), so switching books on later changes no figure.

## 9. Sign-off

| Section | Accepted as is / changes attached | Initials | Date |
|---|---|---|---|
| 1 Tax invoice presentation (F9) | | | |
| 2 GST worksheets (H-05) | | | |
| 3 Money hub wording (M1–M5) | | | |
| 4 Accounting screens | | | |
| 5 Stock write-offs in the ledger | | | |
| 6 Production costing | | | |
| 7 Warranty / commission / renewals | | | |
| 8 Amount involved | | | |

CA name: ____________________  Membership no.: ____________  Firm: ____________________

Signature: ____________________  Date: ____________

Staging build (git SHA) reviewed: ____________________
