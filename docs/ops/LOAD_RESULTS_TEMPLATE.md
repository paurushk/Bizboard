# Load results — <date> (WP-G2 / QOS-0003)

Copy to `docs/ops/LOAD_RESULTS_<YYYY-MM-DD>.md` for each run. Targets: `docs/ops/SLO.md`
→ *Performance targets*.

## Setup

| Item | Value |
|---|---|
| Environment | hosted staging, git SHA ______ |
| Hardware | VM ____ vCPU / ____ GB; Postgres ____ ; Redis ____ |
| Gunicorn workers / Celery concurrency | ____ / ____ |
| Data | `seed_load_tenant --invoices 50000` (large tenant) + ____ small tenants |
| Load | `k6 run load/k6_smoke.js`, `load/k6_slo.js`, `load/k6_mixed.js` at ____ VUs for ____ min |
| Soak | `load/k6_mixed.js` at ____ VUs for 8 h |

## Results

| Scenario | p95 | p99 | Error rate | Target met? |
|---|---|---|---|---|
| Sign in | | | | |
| Dashboard | | | | |
| Invoice Complete | | | | |
| Lists | | | | |
| Reports (large tenant) | | | | |
| Bill import 200 lines | | | | |
| Nightly books check (1,000 tenants) | | | | |

## Resources during the soak

| Metric | Start | Peak | End |
|---|---|---|---|
| DB CPU % | | | |
| DB connections in use | | | |
| `bizboard_celery_queue_depth` (max queue) | | | |
| API memory per worker | | | |
| Worker memory | | | |

## Breaches and follow-ups

| Breach | Cause | Fix ticket (QOS) |
|---|---|---|
| | | |
