# Local security scan and cross-tenant probe: 2026-10-25 (WP-1)

**Where:** local staging (`http://127.0.0.1:8081`: nginx → gunicorn → Postgres with RLS, app role
NOSUPERUSER NOBYPASSRLS), code as of 2026-10-25, uncommitted.
**What:** OWASP ZAP baseline scan, a signed-in ZAP API scan, a cross-tenant probe, dependency
checks, and a review of the backend's raw SQL.
**Rows:** BB-045, BB-144, BB-029, BB-143. These move forward only. The independent pentest on hosted staging
(`PENTEST_SCOPE.md`) is still what closes them.

## Result in one paragraph

- **Real issues found and fixed:**
  - Missing Permissions-Policy, Cross-Origin-Opener-Policy and Cross-Origin-Resource-Policy headers.
  - Unknown `/api/` paths answered with Django's HTML 404 page; they now return JSON.
  - A metrics bug found during the drill: `/api/v1/metrics/` answered 500 for good whenever the
    multiprocess directory was not writable by the app user.
- **No injection, cross-tenant read, or cross-tenant write was found.**
- **Every "High" SQL-injection alert ZAP raised was a false positive,** caused by nginx's rate
  limit answering 503 in the middle of ZAP's paired probes. It was checked deterministically: 30
  sampled alerts across all 7 batches, five payload variants each, all byte-identical responses.

## 1. ZAP baseline (passive, signed out)

`zap-baseline.py -t http://host.docker.internal:8081`: **0 FAIL, 62 PASS, 6 WARN.**

| Warning | Decision |
|---|---|
| Permissions Policy header not set (10063) | **Fixed.** Added to every header block in `nginx/default.conf` and `web/nginx.conf`. Camera and location are allowed for this site only (barcode scan, customer address pin); everything else is off. Test: `test_every_nginx_header_block_sets_permissions_policy` |
| Cross-Origin-Opener-Policy missing on the app (90004) | **Fixed.** `same-origin-allow-popups` in `web/nginx.conf` (popups: Google sign-in, payment page). The API already sends Django's `same-origin` |
| Cross-Origin-Resource-Policy missing (90004) | **Fixed for the API.** `same-site` on `/api/` responses except public links (`core/middleware.py`). Test: `test_api_responses_may_not_be_embedded_by_other_sites` |
| CSP `style-src 'unsafe-inline'` (10055) | **Accepted.** MUI/Emotion injects styles at runtime (BB-000605). Listed in the pentest brief as known |
| Cross-Origin-Embedder-Policy missing (90004) | **Accepted.** The app does not need cross-origin isolation, and `require-corp` would break Google sign-in and fonts |
| Non-storable content, Unix timestamp, "modern web app" (informational) | No action |

## 2. ZAP API scan (signed in, 7 batches)

**How it was run** (`scripts/security/run_local_api_scan.sh`):
- signed in through the normal login form as the load-tenant **sales staff** login, which has no two-step;
- cookies plus `X-CSRFToken` on every request; a pre-check confirmed an unsafe request passes CSRF;
- the definition was a filtered copy of the OpenAPI snapshot (`zap/filter_openapi.py`): 1,090
  operations, with DELETEs, sign-in, billing, payments, webhooks, messaging, erasure, exports and
  public links removed;
- local `JWT_ACCESS_MINUTES` was set to 180 for the run, so the session outlived each batch;
- each batch was capped at 20 minutes, with one thread and 150 ms between requests;
- the database was dumped before and restored after.

| Batch | Areas | FAIL | Alerts above Informational | Decision |
|---|---|---|---|---|
| 1 | sales | 0 | Unexpected content type ×2 | Unknown root paths answer the SPA's HTML: expected |
| 2 | purchases, suppliers | 0 | "SQL injection" on body fields; 503s; HTML content type | See below |
| 3 | inventory, products, masters, customers | 0 | same | See below |
| 4 | accounting, ledgers, banking, money | 0 | "SQL injection" ×7 (`page`, `page_size`, `days`) | False positive |
| 5 | reports, dashboard, search, insights, audit | 0 | content type ×2 | Expected |
| 6 | company, flags, files, … | 0 | "SQL injection" ×27; 503 ×37; CORP ×1 | False positive / 503 / fixed |
| 7 | crm, complaints, contracts, manufacturing, payroll, … | 0 | "SQL injection" ×23; 503 ×44 | False positive / 503 |

**"Server error" alerts.** Every one was **503 from nginx's per-IP rate limit** (`api_general`
30 r/s; ZAP's import and spider phase is not paced by the scanner delay). There was **no 500
from the application.** The large IDs ZAP put in paths (for example `/sales/quotations/1189744282671514792/`)
were checked directly and return a JSON 404.

**"SQL injection" alerts.** The checks:
- 30 alerts sampled across the batches, replayed as the same user with five variants each
  (`1 AND 1=1 --`, `1 AND 1=2 --`, `1 OR 1=1 --`, and the quoted forms);
- **all 30 gave identical responses** (same status, same body with the payload text removed).
  Several were 403, meaning the sales role was correctly refused;
- a review of every `cursor.execute` / `raw` / `RawSQL` / `extra` in the backend (excluding tests
  and migrations) found only fixed strings or parameterised queries. No SQL is built from request input.

**HTML content type.** Unknown `/api/` paths answered with Django's HTML 404. **Fixed:**
`core/error_pages.py` (`handler404` and `handler500` answer JSON under `/api/`; tests in
`test_api_error_pages.py`). The rest are 503 pages from the rate limit, or the SPA's HTML for non-API paths.

**First run, for the record:** the first attempt used `ascan.*` option names, which ZAP ignores
(the right prefix is `scanner.*`). It ran unthrottled into the rate limit and outlived its 15-minute
session. It was stopped and rerun; this table is from the rerun.

## 3. Cross-tenant probe (`scripts/security/tenant_probe.py`)

Through nginx and gunicorn, with the real app role and RLS on. Two companies, each with a test login
that has no two-step: Load Tenant's sales staff and the C5 pilot's sales staff. Run in both directions.

| Check | Result |
|---|---|
| Detail reads of the other company's ids (173 GET paths that have a list sibling) | **0 leaks.** Every id that could be tested returned 404. Most paths had no data of the other company visible to a sales login, so they could not be tested this way (see coverage) |
| List filters with the other company's ids | **0 leaks** (4 checks) |
| Writes naming the other company's records, with A's control request succeeding (201) | **All rejected (400, "object does not exist"):** invoice with B's customer, invoice with B's product, quotation with each, sales order with B's customer, and patching A's own draft to B's customer |
| Purchase bill with B's supplier; receipt for B's customer | Not testable with these roles (403 for the control too) |

**Coverage limits, stated plainly:** the logins available without two-step are sales staff. Owner,
Accountant and Manager surfaces, purchase and payment writes, and most detail endpoints were not
reachable this way. They are covered by:
- the Postgres tenancy suites (`tests/tenancy/`, `test_rls_coverage.py`, live cross-tenant probes
  as owners), which run in CI and in the full Postgres run of 2026-10-25;
- the independent pentest, which gets one login per role in two companies (`PENTEST_SCOPE.md` §2).

## 4. Dependencies

`npm audit --omit=dev --audit-level=high` (the CI frontend gate) found **3 high** in runtime packages,
which would have failed CI. **Fixed** by upgrading to the patched versions:

| Package | Was | Now | Advisory |
|---|---|---|---|
| `zod` (direct) | 4.6.5 | 4.6.7 | GHSA-mrhx-c7xc-m3w5 (memory exhaustion on oversized collections) |
| `follow-redirects` (via axios; Node only, not used in the browser) | 1.16.0 | 1.16.1 | GHSA-q3jh-wrc6-jgq8, GHSA-8r9p-f939-6h3c |
| `fast-uri` (via ajv) | 3.1.5 | 3.1.9 | GHSA-5jgf-p345-68v8, GHSA-f65p-4m7j-42xc |

`fast-uri` 3.1.9 was published on 2026-10-19 and is the only fixed 3.x release. The other two are
over two weeks old. After the upgrade, `npm audit` finds **0 vulnerabilities**.
`pip-audit -r backend/requirements.txt` (run in a throwaway container from the API image): **no known
vulnerabilities**.

## 5. Left for the pentest

Everything in `PENTEST_SCOPE.md` §4, particularly:
- owner and accountant roles across tenants;
- file upload and download;
- public link tokens;
- webhooks;
- rate limits behind the real edge (`NUM_TRUSTED_PROXIES`).
