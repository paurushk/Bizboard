# Database Review

## Wave 22 (2026-08-06)

FIFO layer identity on cancel paths (717–720, 724); opening stock non-atomic with GL (705).

## Wave 21 (2026-08-05)

BB-000667 serial unique too wide; BB-000660 opening stock ignores batch.

## Wave 20 (2026-08-05)

BB-000646 sequence full-scan; BB-000645 missing unique(company,utr).

## Wave 19 missed (2026-08-05)

BB-000601 FIFO layer cancel/transfer; BB-000604 RLS auth order.

## Wave 19 (2026-08-05)

Child tables without `company_id` (BomLine, PaySlip, StockTransferLine) omitted from Wave 19 RLS list. Superuser runtime role. Document series uniqueness ignores GSTIN. Issues: BB-000552, BB-000562, BB-000569.


**Date:** 2026-08-02

## Engines

| Env | Engine | Notes |
|-----|--------|-------|
| Local default | SQLite | `select_for_update` ineffective — BB-000055 |
| CI / intended prod | PostgreSQL 17 | Required for concurrency correctness |

## Schema strengths

- Monetary fields as `DecimalField`.
- Invoice number `UniqueConstraint` per company (sales/purchase invoices).
- Warehouse default partial uniqueness pattern exists.
- Append-only `StockMovement`; balance cache table.
- GL idempotency via `(source_type, source_id, purpose)`.

## Issues

| ID | Finding |
|----|---------|
| BB-000017 | Child lines lack `company_id` |
| BB-000021 | Non-invoice docs lack unique numbers |
| BB-000022 | PaymentAllocation missing XOR constraints |
| BB-000048 | GstReturnSnapshot uniqueness |
| BB-000049 | Bank line_hash not unique |
| BB-000053 | BankAccount.is_default race |
| BB-000057 | HSN/UQC backfill migration risk |
| BB-* | Soft-delete inconsistent (Product only) |

## Indexing / query risks

- Party ledger statements still loop-prone at scale (BB medium N+1).
- GSTR builders load month invoices — needs pre-aggregation for large tenants.
- No proven index plan for 10k-invoice dashboards (load unproven).

## Recommendations

1. Fail boot without `DATABASE_URL` postgres in production.
2. Add missing Unique/CheckConstraints listed above.
3. Denormalize tenant keys on children.
4. Batched data migrations only.

## Score: 6.0 / 10


## Wave 8 (2026-08-03)

No new schema Criticals. Residual concurrency: StockBalance get_or_create race (BB-000235); document number sync_next unlocked (BB-000234).

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.

---

## Wave 14 missed-findings (2026-08-04)

Appended `BB-000544`…`BB-000549` (6). Open **94**. See MASTER_ISSUE_REGISTER.md.
