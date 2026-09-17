# SLI / SLO draft (11.4 / 12.1)

Draft only. Numbers are starting points for Human to sign; they are not a
customer SLA and not a refund policy.

| SLI | Measurement | Draft SLO | Where it lives |
|---|---|---|---|
| API availability | `GET /api/v1/health/` success from external probe | 99.5% / 30d excluding Human-approved maintenance | Uptime checker (Final Gate) |
| Ready probe | `GET /api/v1/health/?ready=1` db+redis | 99% / 30d | Same |
| Invoice complete → PDF ready | `pdf_status=READY` within 120s of complete | 99% of completes | Celery worker + PDF runbook |
| PDF download | Authenticated `GET .../pdf/` is 200 or 409 (never 500) | 99.9% | PDF download runbook |
| Webhook ingest | Signed Razorpay/Cashfree/PayU POST returns 2xx | 99.5% | HMAC + DLQ |
| Backup | Off-host dump succeeded in last 24h | 100% of days | Backup restore drill |
| Tenant isolation | No cross-tenant 200 on IDOR corpus | 100% | FG-2d / tenancy tests |

Error budget: burn 50% in 7 days → incident; freeze feature work until
availability recovers. **Go/No-Go signatures stay Human.**

These numbers stay draft until a Human signs them. Continuously observed
production SLIs and burn-rate alerts are **O-Gate 3** in
[`docs/OBSERVABILITY_IMPLEMENTATION_PLAN.md`](../OBSERVABILITY_IMPLEMENTATION_PLAN.md).
O-Gate 1 is Sentry + on-call + basic `/metrics`. O-Gate 2 adds request
correlation, the Complete journey funnel, and required `failure_reason`.
O-Gate 3 is Journey Health, Experience proxies, production SLIs, and
privacy-safe cohorts.
