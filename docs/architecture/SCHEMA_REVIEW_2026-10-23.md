# Database schema review, 2026-10-23 (BB-062)

Scope: every managed Django model in the app (30 apps, 274 models), read from the model metadata
rather than by eye, against what matters for a multi-company money and stock system. Re-run the
checks with the snippets at the end; the numbers below are from this date.

## Summary

| Area | Result |
|---|---|
| Tenant scoping | Every tenant table carries `company` and is in the row-level-security migration (`tests/test_rls_coverage.py`, forced policies checked on Postgres). The 20 tables without `company` are platform-wide by design (below). |
| Money types | No money-like field is a float. Money is `Decimal(14,2)` (371 fields); unit prices `Decimal(12,2)` (up to ₹999 crore per unit); quantities `Decimal(12,3)`; rates `Decimal(5,2)`; running costs up to 4 places. |
| Delete rules | 246 `PROTECT`, 613 `SET_NULL`, 357 `CASCADE`. Every `CASCADE` from a master or a money document points at a dependent or derived row (below); no invoice, payment, return or journal can be removed by deleting a customer, item, account or godown. |
| Document numbers | Unique per company for sales invoices, purchase invoices, returns and journals. **Fixed in this review:** receipts and supplier payments had a number but no unique rule; `payments/0046` adds one (blank numbers excluded). Local staging had no duplicates (41 receipts, 1 payment) before it was added. |
| Indexes on hot lookups | Present: `Account(company, code)`, `AccountingPeriod(company, start, end)`, `DocumentSeries(company, doc_type, gstin_key, fy_label)`, `GstReturnPeriod(company, period[, status])`, `CompanyGstin(company, gstin)`, `CustomerReceipt(company, utr / status / mode+date)`. |
| Query count on the busiest write | Invoice Complete: 102 queries with the ledger off, 146 with it on (was 151; `tests/test_complete_query_budget.py` guards it, BB-067). |

## Tables without a `company` column (platform-wide, by design)

| Table | Why it is global |
|---|---|
| `accounts.Company`, `accounts.User`, `UserMfa`, `UserSession`, `LegalAcceptance` | The tenant itself and people, who can belong to several companies |
| `accounts.InviteJti`, `PasswordResetJti`, `OtpChallenge` | One-time tokens, keyed to a user or a phone/email |
| `accounts.TenantErasureLog` | Must outlive the erased company (statutory record) |
| `billing.Plan`, `PlatformInvoiceSequence`, `TrialFingerprint` | Bizboard's own price list, its GST invoice series, trial-abuse fingerprints across sign-ups |
| `core.BreakGlassSession`, `EmailOptOut`, `EmailSuppression` | Staff access record; email suppression is per address, not per company |
| `masters.HsnRate` | Shared HSN/SAC catalogue |
| `ops.CoverageAuditRun`, `planwave.BlockedCreditRule`, `support.DataPrivacyRequest` | Staff tooling and requests that may arrive before a company exists |
| `insights.AssistantMessage` | Scoped through its `AssistantThread`, which carries `company` |

## `CASCADE` from masters and money documents (all dependent rows)

Customer → shipping addresses, portal tokens, payment promises, dunning reminders, agent aliases ·
Product → price-list rows, reorder levels, running cost, valuation snapshots, agent aliases ·
Godown → reorder levels, expiry alert log, running cost, valuation snapshots ·
Sales invoice → public links, profit snapshot, payment promises, dunning reminders ·
Purchase invoice → revision history · Sales return → its items · Account → monthly balance cache.

Masters with documents cannot be deleted in the first place: documents point at them with
`PROTECT`, and stock movements and journal lines protect products and accounts.

## Notes, not defects

- `contracts.Contract.value` and renewal values are `Decimal(12,2)` (≤ ₹99.9 crore per
  contract); widen with an `AlterField` (expand-only) if a larger contract is ever expected.
- 613 `SET_NULL` keys are mostly "created by / approved by" users and optional links; they keep
  history when a user or optional record goes.

## How to re-run

```bash
cd backend
DJANGO_SETTINGS_MODULE=config.settings_test python manage.py shell -c "
from collections import Counter
from django.apps import apps; from django.db import models
ms=[m for a in apps.get_app_configs() if 'site-packages' not in a.path for m in a.get_models() if m._meta.managed and not m._meta.proxy]
print(len(ms), Counter(f.remote_field.on_delete.__name__ for m in ms for f in m._meta.fields if isinstance(f, models.ForeignKey)))
print(sorted(m._meta.label for m in ms if not any(f.name=='company' for f in m._meta.fields)))"
pytest tests/test_rls_coverage.py tests/test_complete_query_budget.py
```
