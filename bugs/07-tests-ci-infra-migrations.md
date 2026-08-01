# Area 07 — Test Suites, CI Pipeline, Infra/Deploy Config, Migrations, Docs-vs-Reality

**Scope:** `backend/tests/*`, `web/e2e/*`, `web/playwright.config.ts`, CI (`.github/workflows/ci.yml`), Docker/compose/nginx config, all migrations, `.env*` files, and every planning/validation doc at repo root and in `docs/`.

## Part 1 — Verification commands actually executed

- **Backend:** `python -m pytest -q` initially failed — `pytest-django` wasn't installed in the active `python` (3.12) environment (a separate `pip` on this machine resolves to a different Python 3.11 install). After `python -m pip install -r requirements.txt -r requirements-dev.txt`: **122 passed in 26.64s**.
- **Frontend:** `npm run lint` → 0 errors, 4 warnings (hooks/react-refresh). `npm test -- --run` → **23 passed**, 12.64s. `npm run build` → succeeds in 16.92s but warns the main JS chunk is **829.16 kB** (250.86 kB gzip), no code-splitting.
- **`docker compose config`** → succeeds, but reveals the root `.env` (untracked, present only on this machine) merges live-format OpenAI/Anthropic/DeepSeek API keys straight into the printed `api`/`worker` service environments (BUG-705 below — an operational hygiene note, not a repo leak).
- **Claimed vs actual:**

| Metric | Claimed (TEST_REPORT.md / PERFORMANCE_REPORT.md) | Actual |
|---|---|---|
| Backend tests | 120 passed / 33.6s | **122 passed / 26.64s** |
| Frontend tests | 26 passed / ~20s | **23 passed / 12.64s** |

Neither number matches in either direction — see BUG-729.

**Bottom line:** all three of README's "Verification" commands **do pass right now**, but only after manually installing `pytest-django` (missing from the active environment, undocumented step), and the specific numbers in the prior reports are stale.

---

## Part 2 — Findings

### BUG-700 — Assertion-free debug test committed to the working tree, testing a real cross-tenant security scenario
- **Severity:** High
- **Category:** Test-Coverage / Bug
- **Location:** `backend/tests/test_probe4.py:1-19` (untracked — `git status` shows `?? backend/tests/test_probe4.py`)
- **Description:** Collected and run by pytest (inflating the local count by 1) but contains zero `assert` statements — only `print()`. It exercises `POST /api/v1/company/users/` inviting another tenant's owner email into this tenant, i.e. it already investigated exactly the scenario in BUG-701, but with no assertions it "passes" regardless of what the API does.
- **Impact:** A real, apparently-discovered cross-tenant issue was investigated and left as dead debugging code instead of becoming a regression test or a filed bug.
- **Remediation:** Delete the file, or convert it into a real test with assertions once BUG-701 is fixed.
- **Suggested test:** `test_owner_cannot_silently_attach_existing_user_from_other_company`.
- **Status vs prior report:** NEW.

### BUG-701 — Owners can silently attach any existing user (from any other company) to their own company, no consent required
- **Severity:** Critical
- **Category:** Bug
- **Location:** `backend/accounts/views.py:209-232`
- **Description:** Same root cause independently found by area 01 as BUG-109. When inviting by email, if a `User` with that email already exists anywhere, they're attached to the calling owner's company with no consent check — the submitted `password` is silently ignored for existing users. The 400 "User already belongs to this company" vs 201 response distinguishes membership status, an enumeration side-channel.
- **Remediation:** Require an invite/accept flow for existing users; never leak membership existence via a distinguishable 400.
- **Status vs prior report:** NEW. (= area 01's BUG-109, found independently.)

### BUG-702 — Active company resolution uses an unordered `.first()`, non-deterministic when a user belongs to multiple companies
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/core/permissions.py:9-14`
- **Description:** Same root cause independently found by area 01 as BUG-110. `get_company_user()`'s unordered `.first()` combined with BUG-701 means a multi-membership user's session can resolve to an arbitrary tenant on any given request.
- **Impact:** A serious tenant-isolation correctness bug, since the entire authorization model is built on this single, unordered lookup.
- **Status vs prior report:** NEW. (= area 01's BUG-110.)

### BUG-703 — `/media/` is served by nginx with zero authentication, and PDF filenames are fully predictable/enumerable
- **Severity:** Critical
- **Category:** Bug
- **Location:** `nginx/default.conf:41-45`; `backend/core/models.py:121-122`; `backend/sales/tasks.py:32`
- **Description:** nginx's `/media/` location serves files directly from disk via `alias`, with no auth of any kind — just `nosniff`/`X-Frame-Options` headers. The file path for every invoice PDF is `company_{company_id}/invoice_pdf/{invoice.number}.pdf`, where both `company_id` (sequential BigAutoField from 1) and `invoice.number` (sequential, e.g. `INV-00001`) are trivially guessable. The Django API enforces tenant isolation correctly (confirmed: cross-tenant `GET` returns 404), but that protection is entirely bypassed by nginx serving the underlying file directly.
- **Impact:** Any unauthenticated party reaching the nginx edge can enumerate `/media/company_1/invoice_pdf/INV-00001.pdf`, `company_2/...`, etc., and download other tenants' GST tax invoices — customer names, addresses, GSTINs, amounts — completely bypassing the JWT/tenant-scoping the rest of the API correctly enforces. This is a full cross-tenant confidential-document leak, worse than anything the existing security docs cover (they only checked API-level 404s, not the static file path).
- **Remediation:** Serve media through an authenticated Django view (X-Accel-Redirect after a permission check), or use per-file signed/expiring URLs with non-sequential path components.
- **Suggested test:** Fetch a completed invoice's PDF media URL directly (bypassing the Django `pdf/` endpoint) as an unauthenticated client / different tenant; assert rejection. No such test exists anywhere in the suite today.
- **Status vs prior report:** NEW (BUG_REPORT.md BUG-022 and SECURITY_REPORT.md S-09 only note missing headers on `/media/`, not the complete absence of auth or the enumeration vector). **This is likely the single most severe finding across the entire review.**

### BUG-704 — Shipped placeholder secret key is long enough to bypass the production "strong secret" guard
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/config/settings.py:17-28`; `.env.example:2`
- **Description:** The production guard rejects `SECRET_KEY` if unset, equal to the dev default, or under 32 characters. The repo's own `.env.example` placeholder — `replace-with-a-long-random-secret` — is 33 characters, satisfying every check despite being a publicly-committed, well-known value.
- **Impact:** A pilot deployment that copies `.env.example` to `.env` but forgets to specifically change `DJANGO_SECRET_KEY` boots successfully in production mode with a publicly known secret key, defeating JWT/session signing entirely.
- **Remediation:** Reject known placeholder values explicitly (denylist, or require generation via a documented command with entropy checking).
- **Suggested test:** Boot with `DJANGO_ENV=production` and the exact `.env.example` secret; assert `ImproperlyConfigured` is raised (currently would not raise).
- **Status vs prior report:** NEW.

### BUG-705 — Root `.env` on this machine contains live-looking third-party API keys, auto-loaded by `docker compose`
- **Severity:** High
- **Category:** Bug (operational hygiene)
- **Location:** `E:\Bizboard\.env` (untracked, no git history); `docker-compose.yml:32-34,49-51`
- **Description:** `docker compose config` output shows live-format `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`DEEPSEEK_API_KEY` values injected into the `api`/`worker` environments. Not a repo leak (correctly gitignored, no git history), but any command dumping compose config or container env prints usable keys to logs/terminal history.
- **Remediation:** Rotate these keys if this transcript/terminal history is ever shared; avoid running `docker compose config` in shared/logged contexts.
- **Status vs prior report:** NEW.

### BUG-706 — No `.dockerignore` for backend: `db.sqlite3` and other dev artifacts get baked into the production image
- **Severity:** Medium
- **Location:** `backend/Dockerfile:8-11`
- **Description:** `COPY . .` with no `.dockerignore` anywhere in the repo copies `db.sqlite3`, `media/`, `test_media/`, `__pycache__` into the image.
- **Remediation:** Add `backend/.dockerignore`.
- **Status vs prior report:** NEW.

### BUG-707 — No `.dockerignore` for web: host `node_modules` can overwrite the container's `npm ci` install
- **Severity:** Medium
- **Location:** `web/Dockerfile:1-6`
- **Description:** The unguarded `COPY . .` after `npm ci` copies the host's `node_modules` over the container's fresh install, potentially replacing Linux-container native binaries with Windows-host ones.
- **Remediation:** Add `web/.dockerignore` with `node_modules`, `dist`, `test-results`, `.env*`.
- **Status vs prior report:** NEW.

### BUG-708 — No restart policy on any docker-compose service
- **Severity:** Medium
- **Location:** `docker-compose.yml` (entire file)
- **Description:** No service declares `restart:`. If gunicorn/Celery worker/Postgres crashes, it stays dead until manually restarted.
- **Impact:** A single OOM-kill or unhandled exception in the worker silently stops all future invoice PDF generation with no automatic recovery, for a "production pilot" deployment.
- **Remediation:** Add `restart: unless-stopped` to every service.
- **Status vs prior report:** NEW.

### BUG-709 — No healthcheck for `api`, `worker`, `web`, or `nginx` services
- **Severity:** Medium
- **Location:** `docker-compose.yml:27-77`
- **Description:** Only `db`/`redis` have healthchecks. `nginx` depends on `api`/`web` with `condition: service_started`, not `service_healthy` — nginx can start routing before Django finishes migrate+boot.
- **Impact:** Race condition producing 502s during startup; no way to detect a hung/degraded container.
- **Remediation:** Add a healthcheck to `api`; change nginx's `depends_on` to `service_healthy`.
- **Status vs prior report:** NEW.

### BUG-710 — Ruff lint config only catches fatal syntax errors, not real style/bug classes
- **Severity:** Medium
- **Location:** `backend/ruff.toml:5-8`
- **Description:** `select = ["E9","F63","F7","F82","F401","F811"]` — essentially syntax errors and unused imports only. No Bugbear, security, or Django-specific rules enabled, despite a comment suggesting this was meant as a temporary bootstrap.
- **Remediation:** Incrementally expand to include `B` (bugbear) and Django-specific rules.
- **Status vs prior report:** NEW.

### BUG-711 — Backend dependencies fully unpinned, no lock file, test tooling shipped in the production image
- **Severity:** Medium
- **Location:** `backend/requirements.txt:1-20`; `backend/Dockerfile:8-9`
- **Description:** Every dependency uses `>=` with no upper bound and no lock file. `requirements.txt` itself bakes in `pytest`/`pytest-django`, so the production image installs test tooling.
- **Remediation:** Split into compiled, pinned lock files; move test tooling to `requirements-dev.txt` only.
- **Status vs prior report:** NEW.

### BUG-712 — CI runs backend tests against in-memory SQLite while production uses PostgreSQL
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/config/settings_test.py:5-10`; `.github/workflows/ci.yml:22-28`
- **Description:** Postgres-only behaviors — `UniqueConstraint(condition=Q(...))`, and critically `select_for_update()` locking semantics used for document numbering and (per area 02/03's BUG-222/309) the very stock/payment concurrency races this review found — are never exercised in CI, only against SQLite's much looser engine.
- **Impact:** `select_for_update()` calls are effectively no-ops under SQLite, so any real concurrency bug in that locking logic would pass CI and only surface under real Postgres load — directly relevant to the previously-flagged payment-allocation/stock-oversell races.
- **Remediation:** Add a Postgres service container to CI; run at least the concurrency-sensitive tests against real Postgres.
- **Status vs prior report:** NEW (extends, doesn't duplicate, the known concurrency gaps — makes them worse since even a written concurrency test wouldn't be meaningfully verified in CI without Postgres).

### BUG-713 — CI never validates `docker-compose.yml` or builds the Docker images
- **Severity:** Medium
- **Location:** `.github/workflows/ci.yml` (entire file)
- **Description:** No job runs `docker compose config`/`build` — a broken Dockerfile or compose YAML (e.g. BUG-706/707) wouldn't be caught until a manual deploy attempt.
- **Remediation:** Add a `docker compose config` (and ideally `build`) step to CI.
- **Status vs prior report:** NEW.

### BUG-714 — No dependency vulnerability scanning in CI
- **Severity:** Medium
- **Location:** `.github/workflows/ci.yml` (entire file)
- **Description:** Neither job runs `npm audit`/`pip-audit`. Running `npm audit` locally during this review turned up two real, currently-unaddressed moderate CVEs (BUG-715).
- **Remediation:** Add scanning steps to CI.
- **Status vs prior report:** NEW.

### BUG-715 — `react-router-dom` has two unaddressed moderate CVEs
- **Severity:** Medium
- **Category:** Bug
- **Location:** `web/package.json:30`
- **Description:** `npm audit` reports react-router 6.0.0–7.17.0 vulnerable to an open-redirect via backslash in `<Link>`/`useNavigate` (GHSA-wrjc-x8rr-h8h6) and a constructor-injection issue in SSR hydration (GHSA-337j-9hxr-rhxg, likely inert since Bizboard is CSR-only). Fix available via `npm audit fix`.
- **Impact:** Open-redirect risk on any page using `<Link>`/`useNavigate` with user-influenced paths — a phishing vector.
- **Remediation:** `npm audit fix` / bump to a patched version, re-run the full test/e2e suite.
- **Status vs prior report:** NEW.

### BUG-716 — Production build ships a single 829 KB JS bundle with no code-splitting
- **Severity:** Low
- **Category:** Performance
- **Location:** `web/vite.config.ts` (no `manualChunks`)
- **Description:** The whole SPA ships as one bundle, over Rollup's 500 kB warning threshold.
- **Impact:** Slower first paint on low-bandwidth mobile connections — directly relevant to the target user (Indian retailers, plausibly on budget mobile data).
- **Remediation:** Route-level `React.lazy()` code-splitting for heavy pages; `manualChunks` to separate vendor from app code.
- **Status vs prior report:** NEW.

### BUG-717 — `Quotation` model has no composite index for its most common list-filter pattern
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/sales/migrations/0001_initial.py:22-51`
- **Description:** `SalesInvoice`/`SalesReturn` both get an explicit `(company, status, date)` index; `Quotation` — identical shape, filtered the same way — gets none.
- **Remediation:** Add the equivalent index via a new migration.
- **Status vs prior report:** NEW.

### BUG-718 — `ImportJob` has no index on its list-filter columns
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/imports/migrations/0001_initial.py:19-42`
- **Description:** Ordered `['-created_at']`, realistically filtered by `company`+`status`, but has no `Meta.indexes` at all — unlike almost every other document model.
- **Status vs prior report:** NEW. (Independently found in area 03 as BUG-318.)

### BUG-719 — Multi-tenant lookup fields (name, sku, barcode, phone) are indexed alone, not composited with company
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/masters/migrations/0001_initial.py:59-60, 97-98, 139-141`
- **Description:** Every real query in this multi-tenant app also filters by `company`, but `name`/`sku`/`barcode`/`phone` all get standalone single-column indexes rather than composited with `company` — Postgres has to intersect a global name-index scan with a company filter rather than walking one composite index.
- **Remediation:** Replace standalone `db_index=True` with `Meta.indexes = [Index(fields=['company','name'])]` etc.
- **Status vs prior report:** NEW.

### BUG-720 — Data migration's reverse operation is a silent no-op, misleading about rollback semantics
- **Severity:** Low
- **Location:** `backend/accounts/migrations/0005_owner_capability_defaults.py:17-29`
- **Description:** The reverse callable for a data migration granting default capability flags to all owners is a true no-op — rolling back to `0004` "succeeds" while the granted flags silently remain.
- **Remediation:** Implement a real reverse, or document explicitly that the migration is intentionally one-way.
- **Status vs prior report:** NEW.

### BUG-721 — No test for cross-tenant WRITE attempts (only cross-tenant reads/creates are tested)
- **Severity:** Medium
- **Category:** Test-Coverage
- **Location:** `backend/tests/test_tenant_isolation.py:1-95`
- **Description:** All 9 tests check `GET` isolation or creation-reference isolation; none call `.patch()`, `.delete()`, or action endpoints (`/complete/`, `/cancel/`, `/share/`, `/regenerate-pdf/`) against another tenant's object ID. IDs are sequential BigAutoFields across the whole system, making this a realistic, cheap attack to test.
- **Remediation:** Add a table-driven test iterating over all mutating endpoints against tenant B's client using tenant A's object IDs.
- **Status vs prior report:** NEW.

### BUG-722 — Cancelling a sales invoice does not check for (or reverse) existing payment allocations
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/sales/services.py:243-268`
- **Description:** `cancel()` blocks cancellation if completed returns exist, but has no equivalent check for `PaymentAllocation` rows against the invoice. A fully or partially paid invoice can be cancelled, leaving allocations pointing at a now-CANCELLED invoice.
- **Impact:** A latent ledger-correctness bug, with no test proving what actually happens to the derived outstanding balance in this case.
- **Remediation:** Block cancellation when allocations exist (symmetric with the returns check), or explicitly define and test the orphaned-allocation behavior.
- **Status vs prior report:** NEW.

### BUG-723 — No test that a payment allocation's source/document-type must match
- **Severity:** Low
- **Category:** Test-Coverage
- **Location:** `backend/tests/test_payment_allocation.py`
- **Description:** No test that a `receipt` (customer money) can't be allocated to a `purchase_invoice`, or a `supplier_payment` to a `sales_invoice` — untested cross-field validation.
- **Status vs prior report:** NEW.

### BUG-724 — `tax_parity_cases.json` fixture is not loaded/consumed by any test
- **Severity:** Medium
- **Category:** Test-Coverage
- **Location:** `backend/tests/fixtures/tax_parity_cases.json`
- **Description:** A repo-wide search shows this file is referenced only from planning docs — zero test files actually read it. The scenarios it encodes are separately hardcoded inline elsewhere, so the fixture contributes zero coverage.
- **Remediation:** Either delete it, or write a parametrized test loading it directly, making it the actual shared FE/BE source of truth it appears intended to be.
- **Status vs prior report:** CONFIRMED (extends area 02's BUG-216 with a specific detail: the existing 3 cases aren't even wired to any test).

### BUG-725 — E2E suite is 5 route-smoke tests against fully-mocked data; zero real business-workflow coverage
- **Severity:** High
- **Category:** Test-Coverage
- **Location:** `web/e2e/smoke.spec.ts`; `web/playwright.config.ts`
- **Description:** All 5 Playwright tests run with `VITE_USE_MOCKS=true` and a manually-seeded mock session — none hit a real backend. They only check route/element presence, never a real login, form submission, or data mutation. Zero coverage of: invoice creation → complete → payment → PDF download; purchase → stock update → low-stock alert; any GST-return-affecting workflow.
- **Impact:** The single most business-critical journey in the product has no automated browser-level regression coverage against the real API at all.
- **Remediation:** Add at least one true end-to-end test against the real backend: register/login → create product/customer → create invoice → complete → verify stock decremented → receipt → allocate → download and validate the PDF.
- **Status vs prior report:** NEW (pins down the exact 5 test names and confirms 100% are mock-only with no data-mutation assertions).

### BUG-726 — No test that low-stock alerts clear once stock is replenished
- **Severity:** Low
- **Category:** Test-Coverage
- **Location:** `backend/tests/test_stock_flow.py:154-159`
- **Description:** Only tests that an alert appears when below reorder level; no companion test that restocking above it clears the alert.
- **Status vs prior report:** NEW.

### BUG-727 — No test for date-range filtering on sales/purchase registers (GSTR-relevant)
- **Severity:** Medium
- **Category:** Test-Coverage
- **Location:** `backend/tests/test_search_reports_audit.py:52-60`
- **Description:** The only register test never passes date filters — no test of boundary-date correctness for the exact workflow (monthly GSTR-1 extraction) the app exists to support.
- **Remediation:** Add a test with invoices across a month boundary, asserting correct inclusion/exclusion by `from`/`to`.
- **Status vs prior report:** NEW.

### BUG-728 — No test for OTP lockout after OTP_MAX_ATTEMPTS wrong attempts (enforced in code, never exercised)
- **Severity:** Low
- **Category:** Test-Coverage
- **Location:** `backend/accounts/views.py:147-151`; `backend/tests/test_auth.py:51-67`
- **Description:** The 5-attempt lockout branch is never exercised by any test — only one wrong then one correct attempt is tested.
- **Status vs prior report:** NEW. (Independently found in area 01 as BUG-124.)

### BUG-729 — TEST_REPORT.md / PERFORMANCE_REPORT.md test counts and timings are stale
- **Severity:** Low
- **Category:** Gap
- **Location:** `TEST_REPORT.md:12,24,43-44`; `PERFORMANCE_REPORT.md:23-24`
- **Description:** Both claim 120/120 backend tests in 33.6s and 26 frontend tests in ~20s; actual is 122/26.64s and 23/12.64s. Neither matches in either direction — partly explained by BUG-700's untracked debug file, but a real, unexplained drift remains (frontend has 3 fewer tests than claimed).
- **Remediation:** Regenerate these reports whenever the suite changes, or have CI emit authoritative numbers instead of hand-maintained Markdown.
- **Status vs prior report:** CONFIRMED — exactly the comparison requested, quantified above.

### BUG-730 — `receivables_aging` is computed by the API but never rendered anywhere in the frontend, contradicting the UAT checklist
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/reporting/services.py:68-133`; `web/src/pages/DashboardPage.tsx:55-59`; `docs/pilot/UAT_CHECKLIST.md:12`
- **Description:** The dashboard API returns a full aging-bucket breakdown; a repo-wide search of the frontend for "aging" returns zero matches. The pilot UAT checklist explicitly instructs testers to verify "receivables aging present" — currently impossible since nothing renders it.
- **Impact:** A pilot UAT run following the documented checklist will fail step 10 as written; a fully-built backend feature delivers zero user value today.
- **Remediation:** Build the aging-buckets UI, or update the UAT checklist until it exists.
- **Status vs prior report:** CONFIRMED (extends area 06's BUG-601/602 with proof the backend field exists and the frontend has literally zero code referencing it, and ties it directly to the UAT checklist).

### BUG-731 — PRODUCTION_READINESS.md's P0 checklist lists "Auth rate limiting" as still-TODO, but it is already implemented
- **Severity:** Low
- **Category:** Gap
- **Location:** `PRODUCTION_READINESS.md:49`; `backend/config/settings.py:139-150`
- **Description:** Opposite-direction doc drift from BUG-729/730 — throttle classes and scopes are already fully wired, but the checklist still shows this unchecked.
- **Remediation:** Check off the item, or replace with a more specific remaining gap.
- **Status vs prior report:** NEW.

### BUG-732 — CA_SIGN_OFF_CHECKLIST.md contains raw Python docstring syntax instead of clean Markdown
- **Severity:** Cosmetic
- **Location:** `docs/ca/CA_SIGN_OFF_CHECKLIST.md:1,17`
- **Description:** The entire file body is wrapped in `"""..."""`, rendering as literal text in any Markdown viewer — likely copy-pasted from a Python docstring without stripping quotes, in a document meant for external CA sign-off.
- **Status vs prior report:** NEW.

### BUG-733 — RUNBOOKS.md has no backup/restore, rollback, or monitoring/alerting runbook
- **Severity:** Medium
- **Category:** Gap
- **Location:** `docs/pilot/RUNBOOKS.md`
- **Description:** Only covers PDF-worker-down, OTP/SMS failure, SMTP failure, and place-of-supply questions. Nothing on restoring Postgres from backup, rolling back a bad deploy/migration, or monitoring/alerting.
- **Impact:** For a paid pilot handling real GST invoices (legal/financial records), no documented backup/restore procedure is a genuine operational risk.
- **Remediation:** Add backup/restore, migration-rollback, and basic monitoring/alerting runbooks.
- **Status vs prior report:** NEW.

### BUG-734 — Local Python environment split caused an initial false test failure; README doesn't guard against it
- **Severity:** Low
- **Category:** Gap
- **Location:** `README.md:39-40`
- **Description:** README recommends `.venv/Scripts/pip install -r requirements.txt`, which is exactly the class of command that silently installs into the wrong interpreter's site-packages when `python`/`pip` resolve to different installs (as happened during this review, on Windows).
- **Remediation:** Recommend `python -m pip install -r requirements.txt` (module-invocation form), more robust to PATH ambiguity.
- **Status vs prior report:** NEW.

---

## Summary of most severe systemic issues

1. **Tenant isolation is enforced at the Django/API layer but not underneath it.** The API correctly 404s cross-tenant access, but this is bypassed entirely at the static-file layer (BUG-703: nginx serves `/media/` with zero auth and fully predictable sequential paths, letting anyone download any tenant's GST invoice PDFs) and undermined at the account layer (BUG-701/702: an owner can silently attach another company's user to their own tenant, and which tenant a multi-membership user's session resolves to is decided by an unordered query). Together these show tenant isolation is a property of specific tested code paths, not a structural guarantee — exactly what a fully-passing `test_tenant_isolation.py` can mask. **BUG-703 is likely the single most severe finding in this entire review.**
2. **The CI/test pipeline validates a materially different system than what ships.** Tests run against in-memory SQLite while production uses PostgreSQL with real locking semantics that SQLite doesn't meaningfully enforce (BUG-712) — directly relevant to the concurrency races found elsewhere (area 02's BUG-222, area 03's BUG-308/309). CI never builds/validates the Docker images or compose file (BUG-713), and there's no dependency-vulnerability scanning, which would have caught two live `react-router-dom` CVEs in about thirty seconds (BUG-715).
3. **The project's own quality-tracking documents have drifted from reality in both directions.** Test-count/timing reports are stale (BUG-729), an untracked debug file with zero assertions sits in the suite testing exactly the security issue in BUG-701 (BUG-700), a fully-built backend feature (receivables aging) has no frontend at all despite the UAT checklist assuming it's checkable (BUG-730), and conversely the production-readiness checklist under-reports a security control that's already implemented (BUG-731) — making the documentation unreliable in either direction for a stakeholder, including the CA whose sign-off gates production per the README.
