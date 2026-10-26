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

## Month-end GST peak (`month_end.js`, WP-RS1)

70% of the given tenant accounts open GSTR-1 / GSTR-3B and download both as Excel within the
window while drafts keep being completed on the large tenant. See the header of the script for the
command and gates; record the run in `docs/ops/LOAD_RESULTS_TEMPLATE.md`.


## Signing in where two-step is enforced (staging, production)

Owners, accountants and anyone who can post journals must enrol in two-step there, so they cannot
sign in unattended. `seed_load_tenant` also creates **`load-staff@bizboard.local`** (sales staff with
sales, reports and export access, no journal posting, so no two-step) with the same `--password`.
Use it as `EMAIL` for `k6_smoke.js`, `k6_slo.js` and `k6_mixed.js`. Staging is cookie-only: the
scripts send the session cookies and stop at setup with a clear error when sign-in gives no
session, instead of reporting green thresholds over zero requests.

`month_end.js` `TENANTS` are owner logins, which must use two-step. Give each owner's
authenticator secret (the base32 key shown at enrolment) as
`-e TOTP_SECRETS="owner1@t1.test=BASE32,owner2@t2.test=BASE32"`; the script answers the two-step
challenge with the current code. Dry run 2026-10-24 on local staging, one enrolled owner: sign-in
through two-step, GSTR-1/3B worksheets and xlsx, dashboard, 7 requests, 0 failed.

## Dry run, 2026-10-23 (local staging, laptop; proves the scripts, not the SLOs)

k6 v1.8.1. `Load Tenant` seeded with `--invoices 60`, a 900-draft pool from `seed_draft_pool`.

| Script | Result | What it showed |
|---|---|---|
| `k6_smoke.js` | pass: 289 requests, 0 failed, p95 43 ms | works as-is |
| `k6_slo.js` (`K6_ONLY=list`, 2 min) | list 100% 2xx; Complete 26% 2xx | Completes refused 429 by the `sales_complete` cap (below) |
| `k6_mixed.js` (`SOAK_MINUTES=1`) | 47% failed | 429 from the per-user API limit (one login standing in for 25 VUs), Complete cap, and dashboard 403 before the staff login got report access |

Found and fixed in the same pass: `k6_slo.js` / `k6_mixed.js` took a bearer token that staging never
sends, so every VU skipped its work and the run "passed"; `seed_draft_pool` crashed on a tenant with
opening stock; `SOAK_MINUTES` added for short dry runs; a rate-limit counter could lose its expiry
in Redis and lock a user out of the API permanently (`core/services/counters.py`).

**Before the hosted soak, two decisions:**

1. `sales_complete` is **60 Completes per minute per company** (all its users together; founder
   decision D-11, 2026-10-24, raised from 30). Pace `COMPLETES_PER_MIN` at or under 60 per load
   company, or spread Completes over several load companies; faster than that measures 429s.
2. One login cannot stand in for many users: the per-user API limit (100 requests / 10 s) is hit
   by design. **Done 2026-10-24 (D-10):** `seed_load_tenant --staff 25` (the default) creates
   `load-staff@bizboard.local` and `load-staff-02` … `load-staff-25@bizboard.local`, all with
   `--password`, and prints them as `staff_emails=...`. Pass that list to `k6_mixed.js` as
   `-e STAFF_EMAILS=...`; setup() signs them in one every `LOGIN_GAP_S` (7 s) and VU n uses login n.
