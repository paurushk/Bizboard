# Indexes / query plans (7.2)

Do not add speculative indexes. Review on hosted volume (Human).

## How

```
docker compose exec api python manage.py dbshell
EXPLAIN (ANALYZE, BUFFERS)
  SELECT ... FROM sales_salesinvoice WHERE company_id = ... AND invoice_date >= ...;
```

Look for Seq Scan on tenant tables once a company has >10k invoices.

## Already in schema (examples)

- `Subscription(status, trial_ends_at)`
- `DeadLetterEvent(provider, status, created_at)`
- `razorpay_subscription_id` indexed
- Document numbers unique per company (3.4)
- `SalesInvoice(company, status, invoice_date)`
- `PurchaseInvoice(company, status, invoice_date)`
- `SalesCreditNote` / `PurchaseCreditNote(company, status, note_date)`
- `ShopFloorEvent(company, event, occurred_on)`

If EXPLAIN shows a sequential scan on `(company_id, invoice_date)` for registers, add a **concurrent** Postgres index in an expand-only migration. SQLite CI will still run the migration.
