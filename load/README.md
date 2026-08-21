# Load testing (MVP harness)

This folder holds **smoke-level** load scripts — not production capacity proofs.

## k6 (`k6_smoke.js`)

MVP load harness: health check, optional auth, and a create-draft path under light concurrency (5 VUs × 30s).

```bash
k6 run -e BASE_URL=http://localhost:8000 load/k6_smoke.js
k6 run -e BASE_URL=... -e EMAIL=... -e PASSWORD=... load/k6_smoke.js
```

**Not a 10k-invoice soak or multi-tenant capacity test.** Use larger datasets, longer duration, and p95 SLOs separately before claiming scale readiness.

## Locust (`locust_smoke.py`)

Optional Python smoke companion — same scope as k6 smoke, not a soak harness.
