> **Historical / superseded (2026-08-03):** See docs/reviews/ for the live engineering audit.

# BizBoard — PERFORMANCE REPORT

> **Update (BUG-301 / P0-510, 2026-08-01):** customer/supplier ledger **list**
> views use `LedgerService.bulk_customer_outstanding` /
> `bulk_supplier_outstanding` (three company-scoped aggregations + one party
> list query) instead of per-party `customer_outstanding` / `supplier_outstanding`
> (`3N+1`). Dashboard company receivables/payables were already SQL aggregates;
> receivables aging still warrants a follow-up under BUG-302 if invoice volume
> grows. See `bugs/03-backend-inventory-payments-reporting.md` and
> `docs/pilot/WAVE0_AUDIT.md`.

**Date:** 2026-07-24  
**Environment:** Local Docker on Windows host; demo dataset (small)  

---

## Summary

On demo data the API is snappy. Architecture choices are mostly sound (paginated lists, aggregated registers). **Ledger list N+1 (BUG-301) is fixed** for Phase 0. Large-table and PDF-at-scale behavior was not load-tested against the P0-620 seed yet.

**Performance score: 6.5 / 10** (demo) · **Unknown at 10k invoices**

---

## Measured latency (live probes)

| Endpoint | Latency |
|----------|--------:|
| `GET /dashboard/` | **56 ms** |
| `GET /sales/invoices/` | **53 ms** |
| `GET /reports/sales-register/` | **25 ms** |
| Backend pytest suite | **33.6 s** (120 tests) |
| Frontend Vitest | **~20 s** (26 tests) |

> These are single-request warm-path figures on a quiet local stack — not p95 under load.

---

## Frontend observations

| Topic | Finding |
|-------|---------|
| Initial load | Vite/nginx static — acceptable for MVP; no Lighthouse run this session |
| Invoice page | Heavy form; MUI + many controlled fields — watch re-renders on each keystroke |
| Tables | Server pagination PAGE_SIZE 50 — good default |
| PDF UX | Async poller (`PdfStatusPoller`) — avoids blocking Complete; download returns 409 while generating (P0-404) |
| Memory leaks | Not profiled |
| Dark mode | Not implemented — N/A |

---

## Backend scalability risks

| Risk | Evidence | Impact at scale |
|------|----------|-----------------|
| ~~Ledger list 3N+1~~ | **Fixed (P0-510):** bulk aggregation in `ledgers/services.py` | Was catastrophic for large masters; now O(1) queries vs party count |
| Dashboard receivables aging | `ReportService` may still loop open invoices (BUG-302) | Slow dashboards with many open invoices |
| Ledger statement builds in Python lists | `LedgerService.customer_statement` | OK for single party; heavy if misused for all |
| PDF Celery dependency | Worker must be up | Queue backup → download 409s until worker catches up |
| LLM bill import | External API + image pages | Timeout/cost; cap pages (`LLM_BILL_MAX_PAGES`) |
| Search | Present; not benchmarked | Add trigram/index review |

---

## Not tested (explicit gaps)

- 1,000 products / 10,000 invoices datasets  
- Concurrent invoice completion races beyond unit tests  
- Browser memory over long sessions  
- Multi-tab edit conflicts UX  
- CDN/TLS latency  
- Worker saturation under PDF burst  
- P0-620 seed p95 floors (invoice list <2s; ledger list usable)

### Load harness scope (BB-000129)

`load/k6_smoke.js` is an **MVP smoke harness** (5 VUs × 30s: health + optional auth + draft create). It is **not** a 10k-invoice soak or multi-tenant capacity proof — see `load/README.md`.

---

## Recommendations

1. ~~Replace per-customer outstanding loop with SQL aggregation.~~ **Done for ledger lists (P0-510).**  
2. Add DB indexes review for `(company_id, invoice_date)`, `(company_id, customer_id, status)`.  
3. Synthetic load: 10k invoices, 2k products, 500 concurrent reads (P0-620).  
4. Cap export rows; stream CSV.  
5. Monitor Celery queue depth and PDF failure rate in pilot.  
6. FE: virtualize long line tables if invoices exceed ~50 lines; handle PDF download 409 with retry/poll.  
7. Paginate ledger list JSON if master counts grow into thousands (payload size, not query count).
