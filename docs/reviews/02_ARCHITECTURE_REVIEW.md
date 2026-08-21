# Architecture Review

## Wave 22 (2026-08-06)

BB-000757 inventory↔sales coupling; BB-000725 SaaS entitlement theater; dual-ledger residuals 695/703/713.

## Wave 21 (2026-08-05)

Multi-company invite gap (BB-000673). No SaaS entitlement layer (BB-000671). No tenant DR (BB-000668).

## Wave 20 (2026-08-05)

Filing identity not an aggregate — stamp unused by statutory payloads (BB-000639). Notes are not amendments of a frozen supply (BB-000649).

## Wave 19 missed (2026-08-05)

Auth dual-stack + RLS wrong layer (BB-000602–604). Dual ledger reverse FK gap (BB-000609). FIFO not actually perpetual (BB-000601).

## Wave 19 (2026-08-05)

ERP apps bolted onto `CompanyScopedViewSet` without inventory event taxonomy, filing-GSTIN aggregate root, or GL participation. RLS middleware is not an isolation architecture (BB-000551/552). ADRs missing for these designs (BB-000598). Issues: BB-000551–556, BB-000564, BB-000583, BB-000593, BB-000598.


**Date:** 2026-08-02 · **Issues:** see MASTER_ISSUE_REGISTER (`BB-*`)

## Current architecture

```
SPA (React/Vite) ──JWT──► /api/v1 (DRF)
                              │
              CompanyScopedViewSet + HasCompany
                              │
         Domain services (Sales/Purchase/Inventory/Payment)
                              │
         Documents (source of truth) ──► LedgerService (derived AR/AP)
                              │
                    (if accounting_enabled)
                              ▼
                    PostingService → JournalEntry (GL projection)
```

**Celery + Redis:** PDF, email, imports, insights, depreciation.  
**Postgres required for production locking;** SQLite for local fallback.

## Strengths

- Document-as-truth for AR/AP (no stored party ledger tables) — correct for MSME billing.
- Append-only stock movements with balance cache + `select_for_update`.
- Tenant scoping via `CompanyScopedModel` / viewsets; isolation tests exist.
- Decimal money fields; envelope error renderer; versioned `/api/v1`.

## Critical architecture problems

| ID | Finding |
|----|---------|
| BB-000016 | Dual AR/AP vs optional GL divergence when posts incomplete |
| BB-000017 | Child rows without `company_id` weaken tenancy defense |
| BB-* EXTRA | Shared DB without Postgres RLS |
| BB-* EXTRA | Events not durable statutory audit log |
| BB-000055 | SQLite default undermines concurrency invariants |

## Module boundary assessment

| App | Cohesion | Coupling risk |
|-----|----------|---------------|
| `sales` / `purchases` | High | Billing shared OK |
| `ledgers` | High | Depends on all document types |
| `accounting` | Medium | Incomplete posting coverage → false books |
| `reporting` | Medium | GSTR builders coupled to sales models |
| `insights` | Medium | LLM + beat scheduling |
| `integrations` | Low maturity | Enums ahead of adapters |

## Patterns

| Pattern | Status |
|---------|--------|
| Multi-tenant shared schema | Present (app-layer) |
| CQRS | Not adopted |
| DDD bounded contexts | Partial (apps ≈ contexts) |
| Saga / outbox | Missing for PDF/email reliability |
| Feature flags | Weak (company toggles only) |

## Recommendations

1. Treat GL as **mandatory projection** when `accounting_enabled` — fail Complete if post fails (BB-000016).
2. Denormalize `company_id` on all child rows (BB-000017).
3. Introduce pilot **feature flags** for GSTR UI, e-invoice submit, accounting nav, AI (BB-000014).
4. Document Branch ≠ Warehouse; do not sell multi-GSTIN until designed (BB-000035).
5. Require Postgres in production boot (BB-000055).

## Score: 6.5 / 10


## Wave 8 (2026-08-03)

No architecture change. Confirmed risks: shared-DB tenancy without RLS, dual AR/AP vs GL, payment adapter sandbox escape hatch as architectural footgun. Score ~6.0.

---

## Wave 9 re-audit (2026-08-03)

Independent re-verification appended `BB-000258`…`BB-000317` (60 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **75**. Wave 6 Open==0 invalidated.

---

## Wave 12 re-audit (2026-08-03)

Independent re-verification appended `BB-000318`…`BB-000378` (61 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count was **61**; **Open: 0** after Wave 12 open-closure (2026-08-04). Waves 10–11 Open==0 invalidated historically.

---

## Wave 13 re-audit (2026-08-04)

Independent re-verification appended `BB-000379`…`BB-000455` (77 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **77**. Wave 12 Open==0 invalidated. Production Readiness **3.2 / 10**.

### Architecture impact

- Perpetual inventory GL incomplete on return lifecycle (BB-000380) — stock ≠ books after returns.
- Dual-ledger control broken by openings + advances (BB-000381/382).
- Live GSP is a stub behind enablement flags (BB-000384) — compliance architecture dishonest if claimed.
- Payment settlement path diverges from settings-surface controls (BB-000379) — defense-in-depth failure.

---

## Wave 14 re-audit (2026-08-04)

Independent re-verification appended `BB-000456`…`BB-000543` (88 issues). See MASTER_ISSUE_REGISTER.md and CHANGELOG.md. Open count: **88**. Wave 13 Open==0 invalidated. Production Readiness **3.4 / 10**.
