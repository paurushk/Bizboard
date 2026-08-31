# Load testing

Smoke scripts are **not** a 50k soak. Staging numbers belong in `load/results/` (gitignored) and a one-line summary on the X-01 ticket log.

## Adopted SLOs (X-01)

Measured on a **50k-invoice tenant** in staging, **ex-PDF, ex-GSP**:

| Surface | p95 |
|---|---|
| Sales invoice Complete | **< 800ms** |
| Invoice list | **< 2s** |
| Dashboard | **< 500ms** |

Do not claim these pass without a dated soak file. Missing the Complete SLO is a follow-up (often W0-06 valuation), not a reason to drop indexes at random.

## k6 smoke (`k6_smoke.js`)

Light concurrency (5 VUs × 30s). Health + optional auth/create-draft.

```bash
k6 run -e BASE_URL=http://localhost:8000 load/k6_smoke.js
k6 run -e BASE_URL=... -e EMAIL=... -e PASSWORD=... load/k6_smoke.js
```

## k6 SLO scenario (`k6_slo.js`)

List + Complete of a **pre-created draft**. Thresholds match the table above. They will fail on a tiny local DB — that is expected.

```bash
k6 run -e BASE_URL=https://staging.example \
  -e EMAIL=... -e PASSWORD=... \
  -e DRAFT_INVOICE_ID=... \
  load/k6_slo.js
```

Write JSON output to `load/results/` (gitignored):

```bash
mkdir -p load/results
k6 run --out json=load/results/slo-$(date +%Y%m%d).json load/k6_slo.js
```

## 50k fixture (do not commit dumps)

See `load/SEED_50K.md`. Seed in staging, then run k6. Never check 50k SQL into git.

## Locust (`locust_smoke.py`)

Optional Python companion — same smoke scope as k6 smoke.
