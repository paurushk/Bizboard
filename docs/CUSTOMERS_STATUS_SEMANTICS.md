# Customer status semantics, privacy and observability (CUS-27)

Written 2026-10-11 from the code at that date. Re-check the `grep` commands below before relying on it.

## What each customer status does today

| Status | Set by | Sales invoice | Quotation / order / challan | POS | Receipts | Lists |
|---|---|---|---|---|---|---|
| `ACTIVE` | default; **Unblock** / **Activate** | allowed | allowed | allowed | allowed | shown |
| `BLOCKED` | **Block** (confirmed in the UI) | refused (`sales/serializers.py:398`, `sales/services.py:1045`) | refused (`sales/services.py:614`, `sales/notes_services.py:804,983,1284`) | invoices complete through `SalesService`, so the same check applies; `sales/pos_policy.py` also mentions BLOCKED (not read in detail) | allowed (money in is never refused) | shown, red chip |
| `INACTIVE` | **Archive** (owner/manager only) on a customer that documents reference (`DELETE` returns 200 "marked Inactive") | refused ("inactive customer") | refused | refused | hidden from the receipt picker unless "show inactive" is ticked | shown, grey chip |

Verify with: `grep -rn "Customer.Status" backend --include=*.py | grep -v tests`.

### Decision taken (2026-10-11)
`INACTIVE` is now treated like `BLOCKED` for new invoices, quotations, orders, challans and quotation conversions (`sales/serializers.py`, `sales/services.py`, `sales/notes_services.py`; the message says "inactive customer"). Credit notes, receipts and reports still work for an inactive customer. Reactivate with **Activate** (a `PATCH` to `ACTIVE`).

### Who may change status (2026-10-12)
- Block: anyone who can create sales.
- Unblock, Activate, or archive (to INACTIVE): OWNER or MANAGER only, in the API (`CustomerSerializer._validate_status_change`) and the UI.
- Archive is refused while the customer has an outstanding balance or an unallocated advance. Archiving pauses their recurring invoice schedules; the recurring job also skips any customer who is not ACTIVE.
- A draft invoice of a blocked or archived customer can still be saved or cancelled, but not completed.

### Invariants enforced by the Customers API
- The POS walk-in customer cannot have a GSTIN or a credit limit, cannot leave `ACTIVE`, and cannot be deleted
  or archived (`CustomerSerializer._validate_walk_in`, `CustomerViewSet.destroy`). `set-pos-walk-in` needs an `ACTIVE` target.
- A changed or cleared GSTIN resets its verification status, legal name, verified-at and raw payload
  (`masters/gstin_rules.py`, applied in `CustomerSerializer.validate` and again under the row lock in `perform_update`).
- Credit limit and credit days can only be changed by `OWNER` or `MANAGER` (`CREDIT_TERM_EDITOR_ROLES`).
- `PATCH` merges field edits under a row lock. If the client sends `version`, a stale value returns `409`.

## Privacy (DPDP) notes
- Personal data on a customer: name, phone, email, billing/shipping addresses, GPS coordinates, bank account
  (role-masked in `CustomerSerializer.to_representation`).
- The customer CSV export contains phone, email, GSTIN and balances. It needs both the financial-reports and export
  permissions, is throttled (`customers_export`, 20/hour per company), is capped at 20,000 rows (refused above that, never
  silently cut), and writes an `EXPORT` audit event with the filters and row count.
- GSTIN lookups (`lookup-gstin`, `verify-gstin`) call a paid provider. They are throttled per company
  (`gstin_verify`, 30/hour), cached for ten minutes per GSTIN, and audited. `lookup-gstin` writes no customer data.
- **Retention (recommended policy, pending founder confirmation in QOS-0125).** Customer audit events are part of the tenant audit trail: append-only and hash-sealed, so they are not deleted one customer at a time. They go only when the whole tenant is erased (D13, which is off until the statutory-retention sign-off SR-40). They hold field names and masked phone, email and PAN, never the full values. The customer CSV is streamed to the caller and never stored by the app; the `EXPORT` audit event keeps the filters and row count, not the data. The History panel is visible to anyone with the financial-reports permission.
  and who may see the customer **History** panel (currently anyone with financial-reports permission).

## Pickers that keep archived customers on purpose
Customer ledger, banking and receipt (money-in) pickers still list archived customers: an archived customer can still owe or be owed money, and statements and receipts must reach them. Pickers for new documents (invoice, quotation, order, challan, recurring invoice, leads, support, contracts, complaints) list active customers only.

## Paths that deliberately skip the customer rules
- **Tenant backup restore** (`accounts/tenant_backup.py`) recreates customers exactly as exported. The data came out of a validated source, and rejecting a row would break a restore. A restore now logs a warning with the counts from the customer health check (`tenant_restore: customer audit ...`), and the owner sees them in the Customers page banner and the monthly check. `manage.py customers_audit` lists the rows.
- Seed and perf-profile scripts create customers directly.

## Observability
- Audit trail: every customer update writes an `UPDATE` event whose `metadata.changes` holds before/after for
  name, GSTIN, state, status, credit terms, taxpayer type, phone, email and PAN; credit-term changes also write a
  `customer.credit_terms` event. The **History** panel on Customer 360° reads these (`GET /customers/{id}/history/`).
- Log events (logger `masters.customers`): `customer.stale_write`, `customer.gstin_lookup`, `customer.gstin_verify`, `customer.export`. The same events are counted on `/metrics` (per worker process, like the other business-event counters, so sum across workers when you query) (`customer_stale_write`, `customer_gstin_lookup`, `customer_gstin_verify`, `customer_export`, `customer_archive_refused`).
- `masters.tasks.customers_audit_task` runs the health check on the 1st of every month (07:30 IST) and notifies each company's owners when it finds something; `manage.py customers_audit` shows the rows.
- Counters to watch in the request log: HTTP `409` rate on `/customers/*` (stale writes), `429` on
  `/customers/lookup-gstin/` and `/verify-gstin/` (throttle), and `EXPORT` audit events per company.
- `manage.py customers_audit [--company N] [--fix] [--fail-on-findings]` reports stale `VALID` statuses, state/GSTIN
  mismatches, duplicate GSTINs and walk-in anomalies. Run it before turning on `CUSTOMER_STRICT_VALIDATION`.

## Rollout switch
`CUSTOMER_STRICT_VALIDATION` (env, default **on** since 2026-10-11; set `0` to relax) turns on the rules that can reject data that is already stored:
GSTIN/state mismatch and the Indian-mobile phone rule on changed phone numbers (also applied to customer imports).
Everything else (duplicate GSTIN message, walk-in guard, credit-term roles, version check, verification reset) is always on.
