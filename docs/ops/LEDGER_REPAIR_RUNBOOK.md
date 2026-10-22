# Ledger repair runbook (WP-F7 / DIM6-12)

**When you are here:** the `BizBoardBooksCheckFailed` alert fired, Django admin → *Tenant sweep
results* shows a company as FAILED or ERROR, or a customer says their books look wrong.

**Rules**

1. Find the failing check first. Never run a repair "to see if it helps".
2. Every repair takes `--company`, starts as a dry run, and is re-run with the write flag only
   after you have read the dry-run output.
3. A repair that writes leaves an `AuditEvent` (`action=REPAIR`, `description` = command name)
   and prints a books check for that company (`core/repair.py`). If the books check after the
   repair is not `clean`, stop and escalate; do not chain more repairs.
4. Never edit `accounting_journalline` by hand. The database refuses to commit a posted entry
   that is unbalanced or has no lines (migration `accounting/0023`), so a hand edit fails
   anyway; fix the source document, then repost or reverse through the app or a command below.
5. Re-check: `python manage.py sweep_all_tenants --company <id> --sync --full`.

## 1. Find the failing check

```bash
python manage.py sweep_all_tenants --company <id> --sync --full
python manage.py check_invariants --company <id>
```

The first prints one line per company (`CLEAN` / `FAILED` / `ERROR`) with the failing check
names; the second prints each violation.

## 2. Check → cause → repair

| Failing check | Usual cause | Dry run | Apply |
|---|---|---|---|
| `gl.no_empty_posted_entries` | Legacy posting that crashed after the header (QOS-0055) | `backfill_accounting_postings --dry-run --company <id>` | `backfill_accounting_postings --company <id>` (re-posts; an empty header is replaced) |
| `gl.ar_ties_to_documents` with `DOCUMENT_MISSING_POSTING` on Books health | Invoices / receipts / payments completed while books were off | `backfill_accounting_postings --dry-run --company <id>` | `backfill_accounting_postings --company <id>` |
| Same, but the missing documents are credit/debit notes, returns or bills of entry | Notes or returns completed while books were off | `backfill_missing_postings --dry-run --company <id>` | `backfill_missing_postings --company <id>` |
| `gl.ar_ties_to_documents` / `gl.ap_ties_to_documents` with `AR_CONTROL_MISMATCH` / `AP_CONTROL_MISMATCH` | An untagged manual journal on 1200 / 2100 | Books health screen lists the entry | Reverse the manual journal in the app and re-post it with the customer / supplier set |
| `gl.sales_output_gst_ties_to_invoices` | An invoice edited after posting without re-posting | Open the invoice; compare GST lines with its journal | Amend the invoice through the app (it re-posts); escalate to the CA if the period is filed |
| `gl.journals_balanced`, `gl.trial_balance_zero` | Legacy bad row from before the database trigger | `check_invariants --company <id>` names the entry | Reverse the entry in the app; escalate if it came from a document |
| Expense postings missing (Books health `EXPENSE_*`) | Expenses recorded before the expense ledger start date | `backfill_expense_postings --company <id> --dry-run` | `backfill_expense_postings --company <id>` |
| Stock write-offs missing from the ledger | `ACCOUNTING_POST_STOCK_ADJUSTMENTS` was off | `backfill_stock_adjustment_journals --company-id <id>` | `... --apply` (only after the flag is on and the CA signed off) |
| `projection.bank_recon_match_status_identity` | Bank line matched on one screen and not the other | `repair_bank_match_state --company <id>` | `... --fix [--prefer gl\|payments]` |
| Payroll journal on a pay run that is not completed | Pay run re-opened after posting | `repair_orphan_pay_run_journals --company <id>` | `... --apply` |
| `inventory.balance_equals_movements` | Cached stock balance drifted | Celery `inventory.tasks.verify_stock_balances_integrity` (logs each drift) | Same task repairs from movements |
| POS cash posted to the wrong account | Till mapping changed mid-shift | `report_pos_cash_mispost` (read-only) | Manual journal reviewed by the accountant |

## 3. After the repair

- Books check after the repair says `clean` → re-run `sweep_all_tenants --company <id> --sync`
  so the admin view shows CLEAN, then close the quarantine in admin.
- Still failing → SEV-2 incident (`docs/ops/INCIDENT_RESPONSE.md`). Tell the customer their
  figures are being checked; do not tell them to re-enter documents.
- Write a regression case: add the scenario to `tests/property/test_ledger_state_machine.py`
  or the nearest flow test, so the same cause cannot come back unnoticed.

## Restores

`restore_to_sandbox` and `restore_destroy_in_place` run in one transaction, so the ledger
trigger checks the restored books at commit. A backup that contains an unbalanced or empty
posted entry (only possible for data older than migration `accounting/0023`) fails to restore
with "journal entry N is POSTED but unbalanced / has no lines". Repair the source company with
the table above, take a fresh backup, and restore that.
