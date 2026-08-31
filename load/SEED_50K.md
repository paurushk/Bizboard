# Seed a 50k-invoice staging tenant (X-01)

Do **not** commit SQL dumps or generated invoices.

## Shape

- 1 company, ~1k products, ~50k **completed** sales invoices (ex-PDF generation, ex-GSP).
- Use a dedicated staging database. Never point this at a pilot with real GSTINs.

## Approach

1. Snapshot an empty-ish staging company (masters + openings only).
2. Disable PDF queue (`CELERY` no-op or `pdf_status` left NONE) so Complete is the measured path.
3. Loop `POST /api/v1/sales/invoices/` + `POST .../complete/` **or** a management command that calls `SalesService.complete` in-process. Idempotency keys per invoice.
4. Confirm `SalesInvoice.objects.filter(status="COMPLETED").count() >= 50000`.
5. Capture `EXPLAIN ANALYZE` on invoice list and Complete before/after the soak.

A management command may live later; this ticket only documents the fixture. If you add a command, keep it behind `DJANGO_ENV=staging` and refuse production.

## After seed

Run `load/k6_slo.js` and store JSON under `load/results/` (gitignored). Paste p95 numbers into `docs/roadmap/ticket-logs/X-01.md`. Pass **or** fail with numbers — never a claimed pass without a file.
