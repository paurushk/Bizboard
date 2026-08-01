# BizBoard — PERFORMANCE REPORT

> **Update (BUG-301/302, 2026-07-25):** the dashboard/ledger N+1 risks noted
> below have been fixed — customer/supplier ledger list views and
> receivables aging now use bulk SQL aggregation instead of a per-row Python
> loop. See `bugs/03-backend-inventory-payments-reporting.md` for details.

**Date:** 2026-07-24  
**Environment:** Local Docker on Windows host; demo dataset (small)  

---

## Summary

On demo data the API is snappy. Architecture choices are mostly sound (paginated lists, aggregated registers). **Dashboard receivables computation will not scale** linearly with customer count. Large-table and PDF-at-scale behavior was not load-tested.

**Performance score: 6.0 / 10** (demo) · **Unknown at 10k invoices**

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
| PDF UX | Async poller (`PdfStatusPoller`) — avoids blocking Complete |
| Memory leaks | Not profiled |
| Dark mode | Not implemented — N/A |

---

## Backend scalability risks

| Risk | Evidence | Impact at scale |
|------|----------|-----------------|
| Dashboard O(n) customers | `ReportService.dashboard` loops outstanding per customer | Slow dashboards for large masters |
| Ledger statement builds in Python lists | `LedgerService.customer_statement` | OK for single party; heavy if misused for all |
| PDF Celery dependency | Worker must be up | Queue backup delays downloads |
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

---

## Recommendations

1. Replace per-customer outstanding loop with SQL aggregation.  
2. Add DB indexes review for `(company_id, invoice_date)`, `(company_id, customer_id, status)`.  
3. Synthetic load: 10k invoices, 2k products, 500 concurrent reads.  
4. Cap export rows; stream CSV.  
5. Monitor Celery queue depth and PDF failure rate in pilot.  
6. FE: virtualize long line tables if invoices exceed ~50 lines.
