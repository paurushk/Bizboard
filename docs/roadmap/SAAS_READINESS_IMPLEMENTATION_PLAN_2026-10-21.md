# SaaS readiness — detailed implementation plan

**Date:** 2026-10-21 · **Revision:** 2 (review applied, see §0b) · **Status:** plan, nothing built · **Branch at writing:** `feat/mfg-p0-foundations` (large uncommitted tree)

This plan turns the two roadmap docs into work packages someone can pick up and
build:

- [SAAS_READINESS_ALL_DIMENSIONS_AND_NFR_2026-10-21.md](SAAS_READINESS_ALL_DIMENSIONS_AND_NFR_2026-10-21.md) — scorecard, waves SR0–SR3
- [SAAS_READINESS_DIM6_ACCOUNTING_CORRECTNESS_2026-10-21.md](SAAS_READINESS_DIM6_ACCOUNTING_CORRECTNESS_2026-10-21.md) — DIM6-01..20

Each work package (WP) gives the goal, the files involved, the steps, the tests,
"done when", dependencies, size and lane. The roadmap IDs each WP covers are in
brackets.

**Lanes:** **LLM** = can be built and tested in this repo · **Split** = built
here, a person runs it on a host or signs it · **Human** = only a person can do it.

**Sizes:** S ≤ 1 day · M 2–4 days · L 1–2 weeks (one engineer or one agent session).

---

## 0. Corrections to the roadmap found while planning

Reading the code while planning changed four roadmap items:

| Roadmap item | What the code shows | Change |
|---|---|---|
| SR1-13 MFA on phone-OTP and invite | `VerifyOtpView` (`accounts/views.py:852`) and `AcceptInviteView` (`:1193`) already return `mfa_challenge_response`. Staging refuses to boot without `MFA_ENCRYPTION_KEY`. | Now **verify and close** QOS-0103 plus decide policy for non-owner roles (WP-H1). It's not a build. |
| SR1-12 AI spend caps | `agents/policy.py` has `assert_under_daily_cap` and `assert_within_budget`; `agents/redaction.py` and `agents/untrusted.py` exist. | Now **prove on staging + show in admin + add an injection test set** (WP-I1). |
| SR1-07 fan-out | `insights.sweep_attention_state_task` and `accounting.post_monthly_depreciation` already fan out one task per company. | Copy that **existing orchestrator pattern** to the five jobs that still loop inline (WP-E1). |
| SR0-03 concurrency suites | They carry `pytest.mark.postgres`; the main CI job runs on Postgres 17, so they probably already run. | Add a **guard that fails if any `postgres`-marked test is skipped** in the Postgres job (WP-A2). |

## 0b. Review revision 2 (2026-10-21)

An external review of revision 1 was checked against the code. What was taken and what wasn't:

| # | Review point | Checked | Change in this plan |
|---|---|---|---|
| C1 | pgbouncer `pool_mode = transaction` breaks RLS, because `set_rls_company` uses `set_config(..., false)` (session level) in autocommit | **Confirmed** (`core/rls.py:34`, `deploy/pgbouncer.ini`). One tenant's GUC could leak to another tenant's request. | WP-B1 uses **session** mode. New WP-C4 is the path to transaction mode later. |
| C2 | WP-A1 chunk order breaks the migration graph; files left unassigned | **Confirmed**: `core/0064` depends on `quality/0001` and `jobwork/0001`; the new apps are added to `INSTALLED_APPS` in `settings.py`; `models.py` files were missing from chunk 1; several dirty files had no chunk. | WP-A1 rewritten: schema first, every chunk passes `manage.py check` + `makemigrations --check`, and a script proves every dirty path is assigned once. |
| C3 | No worker consumes the `agents` / `agents_interactive` queues | **Confirmed** (`config/celery.py:23-24` vs `-Q celery,high_priority,media_heavy,reports` in both compose files) | WP-B1 adds the queues; WP-D2 monitors them. |
| C4 | `docker-compose.prod.yml` connects as the DB owner with RLS defaulting off | **Confirmed** (`docker-compose.yml` sets `POSTGRES_RLS_ENABLED:-0`; prod overlay doesn't override `DATABASE_URL`) | New step in WP-B1; new guard in WP-C3. |
| C5 | `expire_proposals` and `cancel_resolved` read `AgentProposal` with no tenant set, so under FORCE RLS they see 0 rows | **Confirmed**: both pass no `company_id`, so the Celery prerun sets no GUC. `purge_steps` is **fine**: it fans out and the prerun sets the GUC from `company_id`. | WP-E1 table corrected; fix added to WP-C2. |
| C6 | Incremental sweep keyed on `AuditEvent` alone can skip a corrupted tenant forever | **Accepted** | WP-E1: forced full sweep at least weekly, wider change signal, platform checks stay in the orchestrator. |
| C7 | A trigger only on journal lines misses zero-line posted entries and DRAFT→POSTED flips | **Accepted** | WP-F6: triggers on both tables; check existing data first. |
| — | CI Postgres runs as a superuser, so RLS tests can pass vacuously | Accepted | WP-A2 adds a `bizboard_app` role lane. |
| — | Rotation drill misses `GSP_FERNET_KEY`, `PLANWAVE_DATA_KEY`, `OTP_PEPPER` | **Partly**: `accounts/mfa.py` already supports a key list (`MultiFernet`); the other keys don't | WP-B3 expanded. |
| — | Backups and RLS; restore needs the role script; media vs PITR | Accepted | WP-B4 expanded. |
| — | Multiprocess metrics: stale files, worker container metrics not visible to the api | Accepted | WP-D2 expanded. |
| — | Books-off tenants with shadow books hit period locks and missing accounts they can't see | Accepted | WP-F2 rules added. |
| — | Parity invariants fail for migrated tenants with opening balances | Accepted | WP-F4 expanded. |
| — | Migration gate should use a git worktree for the base | Accepted | WP-F8 changed. |
| — | One spend choke point for every LLM call | Accepted: there are two call paths, `core/services/llm.py` and `core/services/llm_gateway.py` | WP-I1 expanded. |
| — | No work package for SMS DLT, SPF/DKIM/DMARC, WhatsApp templates | Accepted | New WP-B6 in Wave 0/1. |
| — | No consent capture for DPDP | **Confirmed**: no ToS/privacy acceptance field found in `accounts`/`core` | New WP-H5. |

---

## 1. Workstreams at a glance

| WS | Name | WPs | Wave | Main lane |
|---|---|---|---|---|
| A | Baseline and release hygiene | A1–A4 | 0 | Split/LLM |
| B | Hosted environment + messaging registrations | B1–B6 | 0–1 | Split/Human |
| C | Tenancy and RLS | C1–C4 | 1 (C4 later) | LLM/Split |
| D | Observability and alerting | D1–D6 | 1 | LLM/Split |
| E | Scalability (per-tenant jobs) | E1–E2 | 1 | LLM |
| F | Accounting correctness (Dim 6) | F1–F10 | 0–3 | LLM/Split/Human |
| G | Performance | G1–G3 | 1 | Split |
| H | Security, identity and privacy | H1–H5 | 1–2 | Split/Human/LLM |
| I | AI agents controls | I1–I2 | 1 | LLM |
| J | Closed beta operations | J1–J8 | 2 | Human/Split |
| K | Commercial and legal | K1–K4 | 3 | Human |
| L | Mobile compatibility | L1 | 3 | LLM |
| M | Governance | M1–M3 | continuous | LLM |

---

## 2. Work packages

### WS-A — Baseline and release hygiene (Wave 0)

#### WP-A1 Commit the uncommitted tree in reviewable chunks [SR0-01, DIM6-01] — Split, L

**Goal:** a clean `git status` on money/stock paths and a tag CI has vouched for.

**Rule for every chunk:** after committing it, a clean checkout of that commit must pass `python manage.py check` and `python manage.py makemigrations --check --dry-run`. That means each app's `models.py`, its migrations, its `INSTALLED_APPS` line and the RLS migration that depends on it go in the **same** chunk. Hunk-level staging (`git add -p`) isn't available in this environment, so `config/settings.py` goes in whole with the schema chunk.

**Step 0 — assignment manifest:** write `scripts/release/commit_chunks.yaml` (chunk → list of paths/globs). A small script compares it with `git status --porcelain` and fails if any dirty path is in no chunk or in two chunks. This catches files like `accounting/reports.py`, `accounts/tenant_backup.py`, `core/idempotency.py`, `core/invariants/__init__.py`, the CI guards, `qos/backlog/QOS-0141..0153.yaml` and `web/e2e-golden/*`.

**Chunks** (in this order):

| # | Chunk | Main paths |
|---|---|---|
| 1 | **Schema foundation** — all model changes, all migrations, new apps registered | `config/settings.py` (registers `quality`, `jobwork`, `agents`), modified `models.py` in `inventory`, `masters`, `manufacturing`, `insights`; `manufacturing/migrations/0011–0015`, `inventory/migrations/0033`, `masters/migrations/0034`, `insights/migrations/0018`; `quality/` and `jobwork/` app skeletons (`apps.py`, `models.py`, `migrations/`); `agents/` app skeleton (`apps.py`, `models.py`, `migrations/`, `enums.py`); RLS migrations `core/0064`, `0065`, `0066`. Add other files only if `manage.py check` needs them. |
| 2 | Manufacturing services split + features | `manufacturing/services/` (package; `services.py` → `legacy.py`), `views*.py`, `serializers*.py`, `urls.py`, `permissions.py`, `printing.py`, `attention.py`, `demo.py`, `error_codes.py`, `management/`, `inventory/aux_warehouses.py`, `inventory/costing_refs.py`, `accounts/mfg_backup.py`, `core/invariants/manufacturing.py`, `tests/test_mfg_*`, `tests/mfg_helpers.py` |
| 3 | Job work + quality features | rest of `jobwork/` and `quality/`, `core/invariants/jobwork.py`, their tests |
| 4 | AI agents runtime | rest of `agents/`, `core/services/llm_gateway.py`, `core/services/llm_providers/`, `accounts/agents_backup.py`, `config/celery.py` (agent routes), compose worker queue change (WP-B1), `tests/agents/` |
| 5 | Shared backend fixes | `accounting/reports.py`, `accounting/services.py`, `accounts/tenant_backup.py`, `core/idempotency.py`, `core/invariants/__init__.py`, `core/services/feature_flags.py`, `insights/alerts.py`, `insights/attention.py`, `insights/event_schema.py`, `inventory/serializers.py`, `inventory/services.py`, `inventory/views.py`, `masters/serializers.py`, `purchases/grn_service.py`, `config/urls.py`, tenancy route matrix and its test |
| 6 | CI gates | `.github/workflows/ci.yml`, `scripts/ci_gates/guards/*`, `scripts/ci_gates/GATE_INVENTORY.md` |
| 7 | Web | `web/src/**`, `web/e2e-golden/**`, `web/src/api/openapi-types.ts` |
| 8 | Generated + docs + backlog | `docs/openapi-snapshot.json`, `docs/**/*.md`, `docs/PRODUCT_QUALITY_BACKLOG.md`, `qos/backlog/*.yaml` |

If chunk 1 doesn't pass `manage.py check` on its own (for example, an app's `ready()` imports a module from a later chunk), merge chunk 1 with the chunk it needs rather than committing a broken state.

**Steps per chunk:**
1. `git add` only the chunk's paths from the manifest. Never `git stash`: other sessions' work lives in this tree.
2. Run `ruff check`, `manage.py check`, `makemigrations --check --dry-run` and the chunk's tests.
3. After chunk 5: `manage.py spectacular` → compare to the snapshot → `npm run gen:api-types` → `npx tsc -b` → `npm run lint`.
4. Commit with a message naming the programme.

**Done when:** CI green on the final SHA, annotated tag `v1.0.0-beta` on it, and the SHA recorded in the scorecard.

**Needs:** the founder's OK to commit, and confirmation that no other session is mid-edit on these files.

#### WP-A2 Postgres-only tests can't silently skip [SR0-03] — LLM, S

- **Files:** `.github/workflows/ci.yml` (Postgres pytest job), new `scripts/ci_gates/guards/guard_no_postgres_skips.py`, `scripts/ci_gates/REQUIRED_CHECKS.txt`.
- **Steps:** have the Postgres job write `--junitxml`. The guard parses it and fails if any test with the `postgres` marker was skipped. Add the guard to `run_guards.py`.
- **Non-superuser lane:** CI's Postgres service connects as `bizboard`, a superuser that bypasses RLS, so an RLS test can pass without proving anything. Add a step that creates `bizboard_app` (`NOSUPERUSER NOBYPASSRLS`, same grants as `scripts/staging-db-role.sh`). Then run `tests/tenancy/`, `tests/test_rls_coverage.py` and the `postgres` suites with `POSTGRES_RLS_ENABLED=1`, connected as that role (migrations still run as the owner).
- **Tests:** a fixture junit file with one skipped postgres test makes the guard fail.
- **Done when:** the CI log shows the guard passing with a count of postgres tests run (expect the 10 `*_concurrency_postgres.py` files and more), and the RLS lane runs as `bizboard_app`.

#### WP-A3 Re-baseline status docs [SR0-02] — LLM, S

- Update `docs/SAAS_READINESS_EXECUTION_PLAN.md` "Status is repo evidence as of 16 Sep" to the tag date. Mark items that moved since then: MFA (4.3), RLS app role (3.3), cookie JWT (4.1).
- Refresh the scorecard's Level column.

#### WP-A4 Book long-lead people [SR0-04] — Human, S

CA engagement (one combined scope, see WP-F9), counsel (ToS, privacy, DPA, DPIA, WhatsApp consent), pentester, named on-call primary and backup, 5–10 beta businesses. **Done when** each one has a date.

---

### WS-B — Hosted environment (Wave 1)

#### WP-B1 Hosted staging [SR1-01] — Split, L

**Needs:** founder decision Q1 (provider, India region).

**Target topology** (matches `docs/ops/ADR_TOPOLOGY.md` and `docker-compose.staging.yml`):

| Part | Choice |
|---|---|
| Postgres | Managed PG 17, PITR on, private network only, `statement_timeout` per `docs/ops/POSTGRES.md` |
| Pooling | pgbouncer in **session** mode (change `pool_mode` in `deploy/pgbouncer.ini`) with `CONN_MAX_AGE=0`. Transaction mode isn't safe yet: `core/rls.py` sets the tenant with `set_config(..., false)`, which is session-level, in autocommit, so another tenant's request could get a connection that still carries the last tenant's `app.company_id`. Transaction mode comes later via WP-C4. |
| Redis | Managed, private |
| App | One VM running api, worker, beat and web through the staging Compose overlay. The worker must consume `celery,high_priority,media_heavy,reports,agents,agents_interactive` (`config/celery.py` routes agent tasks to the last two, and today no worker listens). Better: a separate small `agent-worker` service for `agents,agents_interactive` so slow model calls can't block invoices. Fix this in `docker-compose.yml` and `docker-compose.staging.yml`. |
| Media / backups | Object storage, separate bucket for backups |
| Edge | TLS via Cloudflare (`docker-compose.cloudflared.yml`) or the provider's load balancer |

**Steps:**
0. **Align the prod overlay with staging first.** Today `docker-compose.prod.yml` doesn't override `DATABASE_URL` (which `docker-compose.yml` sets to the owner role) and inherits `POSTGRES_RLS_ENABLED:-0`. So prod would run api/worker/beat as the DB owner with RLS off. Copy the staging pattern: `DATABASE_URL` from `${APP_DB_USER:?}`/`${APP_DB_PASSWORD:?}`, `POSTGRES_RLS_ENABLED: ${POSTGRES_RLS_ENABLED:-1}` on api, worker, agent-worker and beat. Migrate/backup/restore keep the owner role. WP-C3 adds a guard so this can't regress.
1. Provision from IaC (step 2.3 scripts). Record every manual click in `docs/ops/HOSTED_STAGING.md`.
2. Fill env from `docs/pilot/ENV_CHECKLIST.md`. `POSTGRES_RLS_ENABLED=1`, `MFA_ENCRYPTION_KEY`, `PLANWAVE_DATA_KEY`, `APP_DB_USER`/`APP_DB_PASSWORD` are mandatory (staging refuses to boot without them).
3. Migrate as the owner role, then run `scripts/staging-db-role.sh` so api/worker/beat connect as `bizboard_app` (NOSUPERUSER NOBYPASSRLS).
4. `seed_staging` as owner.
5. `edge_tls_smoke.sh` and `scripts/post_deploy_smoke.py` against the public URL.

**Done when:** both smokes PASS from outside the host; execution record dated in `HOSTED_STAGING.md`.

#### WP-B2 Deploy from SHA + rollback rehearsal [SR1-09] — Split, M

- **Files:** new `.github/workflows/deploy-staging.yml`; reuse the SHA-tagged image workflow (14.2) and `docker-compose.rollback.yml`.
- **Steps:** on manual dispatch with a SHA: pull images by digest → run migrate container → `staging-db-role.sh` → restart → smoke. Rollback job: redeploy the previous digest; migrations are forward-only per `docs/ops/FORWARD_FIX.md`.
- **Rehearsal:** deploy tag N, deploy N+1, roll back to N, time each step.
- **Done when:** the timed log is in `HOSTED_STAGING.md`.

#### WP-B3 Secrets manager + rotation drill [SR1-10] — Split, M

- Move every secret from `.env.staging` into the provider's secret store and inject it at deploy time.
- **Secrets in scope:**

| Secret | Rotation method |
|---|---|
| App DB password, owner DB password | Change in DB + secret store, redeploy |
| `SECRET_KEY` / JWT signing key | Redeploy; everyone has to log in again |
| `OTP_PEPPER` | Defaults to `SECRET_KEY` (`settings.py:784`). Set it separately. Rotating it invalidates OTPs in flight only. |
| `METRICS_TOKEN` | Change in secret store + scraper |
| `MFA_ENCRYPTION_KEY` | Already a key list (`MultiFernet` in `accounts/mfa.py`): add the new key first, re-encrypt, then remove the old one |
| `GSP_FERNET_KEY` (also the fallback for `TENANT_EXPORT_FERNET_KEY`) | Single key today, so it needs key-list support |
| `PLANWAVE_DATA_KEY` | Single 32-byte key today, so it needs key-list support |

- **LLM subtask (M):** give `GSP_FERNET_KEY` and `PLANWAVE_DATA_KEY` the same comma-separated key-list support `mfa.py` has. Add a `rotate_encrypted_fields [--dry-run]` command that re-encrypts every encrypted field (TOTP secrets, GSP credentials, planwave data, tenant export keys) with the first key. Tests: read with an old key, rotate, read with only the new key.
- **Drill** each row per `docs/ops/SECRET_ROTATION.md`.
- **Done when:** drill log with downtime per secret.

#### WP-B4 Off-host encrypted backups + restore drill with ledger sweep [SR1-08, DIM6-14] — Split, M

- **Files:** backup cron script, `docs/ops/BACKUP_ALERT.md`, restore drill script, new management command `sweep_all_tenants` (shared with WP-E1).
- **Steps:**
  1. Nightly `pg_dump` **as the owner role**, never `bizboard_app`. Under FORCE RLS a non-owner dump silently returns empty tables. Add a check that the dump's row count for `accounts_company` is > 0. Media sync is encrypted before upload to a bucket in a separate account, with **object versioning on**.
  2. Missed-backup alert goes to the on-call channel.
  3. The restore drill restores to a fresh DB as the owner, runs `scripts/staging-db-role.sh` (grants and default privileges for `bizboard_app`), then runs `sweep_all_tenants --fail-on-any` as the app role (per-tenant invariant table) and times RTO.
  4. A PITR drill restores to a timestamp T. Media is restored from bucket versions as of T. Redis isn't restored: it holds cache, locks and beat schedule only, and the drill confirms the app starts with an empty Redis.
- **Done when:** dated drill log shows RTO, RPO, the per-tenant sweep result (all clean) and the PITR restore.

#### WP-B5 Uptime probe + status page [SR1-06] — Split, S

External probe on `/api/v1/health/` and `?ready=1` every minute, a public status page, and incident templates from `docs/ops/STATUS_COMMS.md`.

#### WP-B6 Transactional messaging registrations — Human + Split, M (start in Wave 0)

These take weeks with outside parties and block phone-OTP login and invoice sharing for beta users, so start them in week 1.

| Item | Who | Done when |
|---|---|---|
| TRAI DLT: register the business entity, sender header(s), and OTP + transactional templates with the SMS provider | Founder | Template IDs issued and set in staging env; a real OTP arrives on a real phone |
| Email: SPF, DKIM, DMARC (`p=quarantine` after a week at `p=none`) for the sending domain, per `docs/ops/SPF_DKIM.md` | Founder/Ops | mail-tester score ≥ 9/10; invoice email lands in Gmail inbox |
| WhatsApp Business API: business verification and template approval for invoice/reminder templates (`docs/ops/WHATSAPP_INVOICE_TEMPLATE.md`) | Founder | Templates approved; one test send |
| Engineering (LLM, S): `post_deploy_smoke.py` gets an optional `--live-comms` step that sends one OTP and one email to the on-call contact | LLM | Smoke run log |

---

### WS-C — Tenancy and RLS (Wave 1)

#### WP-C1 Run the tenancy and RLS suites against the hosted database [SR1-02] — Split, S

Create a scratch database on the hosted Postgres instance (never the live staging DB). Run `tests/tenancy/`, `tests/test_rls_coverage.py` and the `postgres`-marked suites with the app role. **Done when** the log is saved to `docs/ops/HOSTED_STAGING.md`.

#### WP-C2 Pre-auth writes under FORCE RLS [SR1-02] — LLM, M

The sign-in audit row failed under FORCE RLS until `core.rls.company_scope` was added to `AuditService.log`. Other writes that happen before a tenant is set may have the same bug.

- **Inventory these endpoints and tasks:** sign-up, login (password, phone OTP, MFA verify), password reset, invite accept, payment webhooks (Razorpay, Cashfree, PayU), public payment links, customer portal links, share-PDF links, WhatsApp inbound, DLQ replay, Celery tasks started from beat with no tenant.
- **Beat tasks with no `company_id` that read RLS tables are a known bug class.** The Celery prerun (`config/celery.py`, `set_rls_company_for_task`) only sets the tenant when a `company_id` kwarg or a known document id is passed. Confirmed cases:
  - `agents.tasks.expire_proposals` → `services.expire_due()` queries `AgentProposal` with no tenant. Under FORCE RLS it sees 0 rows, so **proposals never expire**.
  - `agents.tasks.cancel_resolved` reads `AgentProposal` the same way, then loops companies inline calling `still_open` / `cancel_live_for_keys` with no tenant scope.

  **Fix:** find candidate `company_id`s under `rls_bypass()` (a read of ids only), then `.delay(company_id=...)` a per-company task. The prerun sets the GUC from the kwarg. `expire_due(company=...)` already takes a company.

  **Sweep:** write a test that lists every beat entry in `CELERY_BEAT_SCHEDULE`. For each one, it either asserts the task fans out with `company_id`, or that it only reads non-RLS tables, or that it carries an allow-list reason. Run each beat task once under FORCE RLS as the app role and assert it does real work on seeded data.
- **New test** `backend/tests/tenancy/test_preauth_writes_rls_postgres.py` (marked `postgres`): connect as a NOBYPASSRLS role with FORCE RLS, call each endpoint with valid input, and assert no 500, the expected rows written, and no cross-tenant rows.
- **Fix pattern:** wrap the tenant-known part in `company_scope(company)`. Use `rls_bypass()` only where the code must read before the tenant is known, with a comment saying why.
- **Done when:** every row of the inventory has a passing case.

#### WP-C3 RLS for every new tenant table [M1 guard] — LLM, S

Make sure `tests/test_rls_coverage.py` fails when a new model with a `company` FK has no policy migration. Prove it with a throwaway model in a test app. Covers agents, jobwork and quality tables from chunk 1–4.

Also add `guard_compose_rls.py`: parse `docker-compose.prod.yml` and `docker-compose.staging.yml` merged with the base file. Fail if api/worker/agent-worker/beat get a `DATABASE_URL` that isn't built from `APP_DB_USER`, or if `POSTGRES_RLS_ENABLED` can default to `0`.

#### WP-C4 Make RLS safe for transaction pooling (later, before scale-out) — LLM, M

Only needed when connection count forces pgbouncer transaction mode.

- Move tenant binding to transaction scope: `ATOMIC_REQUESTS=True` (or a `connection.execute_wrapper` that opens a transaction) and `set_config('app.company_id', ..., true)` (`SET LOCAL`) at the start of each transaction. The same goes for `app.rls_bypass` and `app.help_staff_all`.
- Celery: the prerun wraps each task body in a transaction, or each per-company task sets `SET LOCAL` inside its own `atomic()` blocks.
- pgbouncer: `server_reset_query_always = 1` as belt and braces.
- **Tests (postgres, through a real pgbouncer container in CI):** two concurrent requests for different tenants interleaved on a pool of size 1 never see each other's rows. A request with no tenant sees 0 rows.
- **Done when:** this test passes in transaction mode and `deploy/pgbouncer.ini` is switched.

---

### WS-D — Observability and alerting (Wave 1)

#### WP-D1 Sentry live [SR1-03, OG1-H1..H4] — Split, S

Create the Sentry project, set `SENTRY_DSN`, `VITE_SENTRY_DSN` and `SENTRY_RELEASE` (= git SHA) on staging, then run `sentry_test_event` and confirm the page reaches the on-call phone. Follow `docs/ops/OGATE_HUMAN.md`.

#### WP-D2 Multi-process-safe metrics [SR1-04] — LLM, M

**Problem:** `core/ops_metrics.py` keeps counters (`_HTTP_5XX`, duration sums, event counts, Celery failures) in module globals. With `GUNICORN_WORKERS=2+`, each scrape reads only one worker.

**Option chosen:** `prometheus_client` in multiprocess mode. It's standard, and the `/metrics` series names stay as they are.

- **Files:** `backend/requirements.txt` (+`prometheus_client`), `core/ops_metrics.py` (globals → `Counter`/`Histogram`/`Gauge`), the `/metrics` view, gunicorn config (`PROMETHEUS_MULTIPROC_DIR`, `child_exit` hook), Compose files (tmpfs dir for api and worker).
- **New series:**

| Series | Type | Labels |
|---|---|---|
| `bizboard_http_requests_total` | counter | `route_group`, `status_class` |
| `bizboard_http_request_duration_seconds` | histogram | `route_group` |
| `bizboard_celery_task_duration_seconds` | histogram | `queue`, `task` |
| `bizboard_celery_task_failures_total` | counter | `task` |
| `bizboard_celery_queue_depth` | gauge | `queue` (read from Redis at scrape) |
| `bizboard_db_pool_in_use` | gauge | — |
| `bizboard_tenant_sweep_failures` | gauge | — (count, never company IDs) |
| `bizboard_backup_age_seconds` | gauge | — |

  Never put company IDs in labels. That causes high-cardinality cost and is a privacy risk. Per-tenant detail lives in Django admin (WP-D4). `bizboard_celery_queue_depth` covers all six queues, including `agents` and `agents_interactive`.
- **Multiprocess dir hygiene:**
  - The api entrypoint wipes `PROMETHEUS_MULTIPROC_DIR` (`rm -rf "${PROMETHEUS_MULTIPROC_DIR:?}"/*`) before `exec gunicorn`.
  - gunicorn's `child_exit` hook calls `multiprocess.mark_process_dead(worker.pid)`.
  - Gauges use an explicit `multiprocess_mode` (`livesum` or `max`).
- **Worker metrics live in other containers.** Celery task metrics are recorded in the worker containers, which the api's `/metrics` can't see. Each worker container runs its own small metrics HTTP server: `prometheus_client.start_http_server` on a private port, started from Celery's `worker_process_init`, also in multiprocess mode with its own wiped dir. The collector scrapes api and every worker. Don't share one tmpfs between containers; it breaks once the worker moves to another host.
- **Tests:** a unit test runs two simulated worker processes against the multiprocess dir and asserts the summed counter. Another test asserts a stale file from a dead pid doesn't affect gauges after `mark_process_dead`. Keep the existing `/metrics` token test.
- **Done when:** with 4 workers on staging, 100 requests give `bizboard_http_requests_total` = 100.

#### WP-D3 Dashboards + alert rules [SR1-05] — Split, M

**Needs:** founder decision Q2 (managed metrics service vs self-hosted).

- One "Ops" dashboard: request rate, errors and p95 per route group; queue depth and task p95 per queue; DB pool; backup age; tenant-sweep failures; circuit-breaker state.
- **Alerts** (each one gets a runbook section in `docs/ops/ALERTS.md`):

| Alert | Condition | Severity |
|---|---|---|
| API down | uptime probe fails 3× | Page |
| 5xx rate | > 2% for 10 min | Page |
| Queue backlog | `high_priority` depth > 500 for 10 min | Page |
| Backup missed | age > 26 h | Page |
| Ledger check failed | `bizboard_tenant_sweep_failures` > 0 | Page (business hours) |
| Error-budget burn | 50% of the 30-day budget used in 7 days | Ticket |
| Circuit open | any money-path breaker open > 15 min | Ticket |

- **Done when:** each alert is fired once on purpose and reaches the named phone.

#### WP-D4 Tenant health in Django admin [SR1-07 view, DIM6-10] — LLM, M

Ops tools go in Django admin, never in the customer SPA.

- New model `core.TenantSweepResult(company, run_id, started_at, finished_at, duration_ms, status, failing_keys JSON, quarantine_id)` plus an RLS policy and a migration.
- Admin list: filter by status, sort by last clean run; link to the quarantine row and to the repair runbook section.
- **Tests:** admin list renders; non-staff gets 403; rows are written by the WP-E1 task.

#### WP-D5 Support-ID walk on hosted staging [OG2 walk] — Split, S

Follow `docs/ops/OGATE_GREP_WALK.md`: cause one 500, take the Support ID from the UI, and find it in the API log, worker log, Sentry and `ShopFloorEvent`.

#### WP-D6 Journey Health review (product side only) [SR2-08] — Split, M

Uses the O-Gate 2 events that already exist. Write a weekly query or report: journeys started vs completed vs failed vs abandoned, plus p95. Product review only, never a page. This is the part of O-Gate 3 worth doing before beta; OpenTelemetry stays deferred.

---

### WS-E — Scalability: per-tenant jobs (Wave 1)

#### WP-E1 Fan out the jobs that still loop over every company [SR1-07, DIM6-09] — LLM, M

**Pattern to copy:** `insights.tasks.sweep_attention_state_task` → `sweep_attention_state_for_company.delay(id)`.

| Task | File | Today | Change |
|---|---|---|---|
| `nightly_invariants_task` | `core/tasks.py:186` | Inline loop, `run_invariants` per company | Orchestrator + `run_invariants_for_company` (`soft_time_limit`, writes `TenantSweepResult`, opens quarantine, increments the failure gauge) |
| Scheduled backups | `accounts/tasks.py:17` | Inline loop | Per-company task on the `media_heavy` queue |
| `run_settings_alerts_task` | `accounts/tasks.py:33` | Inline loop | Per-company task |
| `agents.tasks.cancel_resolved` | `agents/tasks.py:88` | Inline loop over companies with pending proposals; no tenant scope, so it sees nothing under FORCE RLS | Orchestrator finds company ids under `rls_bypass()`, then `cancel_resolved_for_company.delay(company_id=…)` (see WP-C2) |
| `agents.tasks.expire_proposals` | `agents/tasks.py:81` | One unscoped query; sees nothing under FORCE RLS | Same orchestrator pattern; per-company task calls `expire_due(company=…)` |
| `agents.tasks.purge_steps` | `agents/tasks.py:121` | Already fans out | Optional: queue only companies that have `AgentStep` rows |
| Missed audit-seal alert | `core/tasks.py:297` | Loops every company for one platform event | Send **one** ops alert to the on-call channel, not one notification per tenant. Tenants weren't affected by a late seal. |

**The orchestrator keeps the platform checks.** The tail of today's `nightly_invariants_task` runs `notify_shopify_gaps()` and the "RLS off in production" check. These stay in the orchestrator and run once a night, not once per tenant.

**Also:**
- **Incremental sweep, with a safety net.** A company is skipped only when **all** of these hold:
  1. Its last clean `TenantSweepResult` is less than **7 days** old.
  2. Its id isn't in tonight's rotation slice (`company_id % 7 == weekday`). That means every company gets a full sweep at least weekly whatever the change signal says.
  3. Nothing changed since the last clean sweep. Use `GREATEST(MAX(AuditEvent.created_at), MAX(JournalEntry.updated_at), MAX(stock movement created_at))`, not `AuditEvent` alone: a bug that writes ledger or stock rows without an audit event must not hide the company. Add `(company, updated_at)` / `(company, created_at)` indexes if the query plan needs them.
- Management command `sweep_all_tenants [--company ID] [--fail-on-any] [--sync]` reuses the per-company function (used by the restore drill, cutover and CI).
- Every per-company task sets the RLS GUC first, like `post_monthly_depreciation_for_company` does with `set_rls_company`.

**Tests:**
- The orchestrator queues N tasks for N companies (eager mode), and runs the platform checks exactly once.
- A company with ledger rows changed but no audit event is still swept; an idle company is swept on its rotation day and after 7 days.
- A failure in one company doesn't stop the others.
- Incremental mode skips a clean, unchanged company.
- A `postgres`-marked test proves each per-company task works under FORCE RLS with the app role.

**Done when:** the tests pass, and the WP-G2 run sweeps 1,000 seeded tenants inside the nightly window.

#### WP-E2 Guard against new inline loops [M1] — LLM, S

New CI guard `guard_no_inline_company_loops.py`: in `*/tasks.py`, flag `for … in Company.objects…` whose loop body does work other than `.delay(`/`.apply_async(`. Allow-list with a reason comment.

---

### WS-F — Accounting correctness (Dim 6)

#### WP-F1 Ledger coverage map + guard [DIM6-02, DIM6-16] — LLM, M

- New `docs/accounting/LEDGER_COVERAGE_MAP.md`, generated from a registry, not hand-written.
- New `backend/accounting/coverage.py` with entries of the form `POSTING_SOURCES = {source_type: {"function": ..., "accounts": [...], "invariant": "...", "flag": ... or None}}`. Seed it from `accounting/journal_sources.py`.
- **Guard:** every `source_type` that `post_journal` is ever called with (found by a test that patches `post_journal` while the WF chains run) must be in the registry.
- `guard_config_consistency.py`: a flag in the money/stock category can't be classified ON in `FREEZE_SCOPE.md` without a registry entry.
- **Done when:** the map lists every posting source, marked posted / flag-off / not posted.

#### WP-F2 Shadow books [DIM6-04, DIM6-05] — LLM + Split, L

**Needs:** founder decision Q4 (Dim 6 Q1).

**Scale:** 156 references to `accounting_enabled` across ~40 non-test modules.

**Design:**
1. Split the meaning in two:
   - `Company.post_ledger` (new, default **True**, not editable by tenants) controls whether posting functions write the GL.
   - `accounting_enabled` keeps meaning "show accounting screens and use GL figures in reports".
2. Posting functions (`accounting/services.py`, `expense_posting.py`, `payments/services.py`, `purchases/*`, `manufacturing/services/*`, `jobwork/services/out.py`, `payroll/services.py`, `ledgers/services.py`) check `post_ledger` instead of `accounting_enabled`.
3. Report and read paths (`accounting/reports.py`, `reporting/money_position.py`, `core/invariants/reports.py`, views) keep checking `accounting_enabled`.
4. Classify each of the 156 references as *posting* or *display* in a table in the PR description. Do this before any edit.

**Migration and backfill:**
- Schema migration adds `post_ledger` (default True).
- For existing companies with books off, run `backfill_missing_postings --dry-run --company X`, review the diff, then `--apply`, then `sweep_all_tenants --company X`. Do this on staging first, one tenant at a time.

**Tests:**
- Turning `accounting_enabled` off then on changes no Trial balance number. This is a new matrix case added to `test_ar_ap_agreement_matrix.py`.
- Books-off companies still pass every `gl.*` invariant.
- The WF chains pass with `accounting_enabled=False`.

**Rules for books-off companies** (`accounting_enabled=False`, `post_ledger=True`). The ledger must never get in the way of someone who can't see it:

1. **Chart of accounts:** seeded at company creation for every company (`seed_chart_of_accounts`), whatever `accounting_enabled` is. Test it on the onboarding path.
2. **Backing accounts:** creating a bank account, expense category, tax rate or other master that posting needs also creates or maps its GL account automatically, the same way it happens for books-on companies. Before building, list every master that posting reads an account from; each one needs a test that creates the master on a books-off company and posts against it.
3. **Accounting period locks:** books-off companies never get user-created accounting period locks (there's no screen for them). Statutory locks that do apply (the GST period soft-close, the credit-note time limit) already show their own messages in the document screens. If a posting still hits an accounting lock, the user sees the document-level message ("This month is closed for GST…"), never a raw accounting error. Test: void and edit across a closed GST period on a books-off company give the document message.
4. **Fiscal year:** created automatically at company creation and at each year rollover for all companies (a beat task per company), so posting never fails on a missing year.
5. **Turning books on later:** opens the accounting screens on a ledger that is already complete. No backfill and no number changes (the matrix test above).

**Risks:** rule 2 is the biggest unknown. Do that inventory first, and size the WP after it.

#### WP-F3 Flag-gated postings [DIM6-06] — Split, M

- `ACCOUNTING_POST_STOCK_ADJUSTMENTS` and `MFG_COSTING_GL` go into the CA pack (WP-F9).
- After sign-off: default ON for new companies, run `backfill_stock_adjustment_journals` for existing ones, update the `FREEZE_SCOPE.md` Table B rows.
- Until then: the Trial balance screen shows a "Not in the books yet" note listing these, driven by the WP-F1 registry, with Hindi.

#### WP-F4 Documents ↔ GL parity invariants [DIM6-07] — LLM, M

- New `core/invariants/gl_parity.py`:

| Key | Documents side | GL side |
|---|---|---|
| `gl.ar_ties_to_documents` | Sum of open sales-document outstanding | 1200 + tagged party ledgers |
| `gl.ap_ties_to_documents` | Open purchase-document outstanding | 2100 |
| `gl.stock_ties_to_valuation` | Stock valuation report | Inventory account (only where stock posting is ON) |
| `gl.gst_payable_ties` | Output tax − ITC for open periods | GST control accounts |
| `gl.bank_ties_to_ledgers` | Bank/cash balances from receipts and payments | Bank/cash accounts |

- Reuse the oracle in `test_ar_ap_agreement_matrix.py` for the documents side, so there's one definition.
- **Opening balances:** migrated companies carry opening AR/AP on control accounts through an opening journal or party opening balances, with no open invoice rows behind them. The documents side must be `open documents + party opening balances still outstanding (net of allocations against them)`. Read these from the same source the opening-balance import writes. Stock gets the same treatment: the opening stock valuation entry counts on the documents side.
- **Tests:**
  - Each key passes on WF seed data.
  - A perturbation test (edit one line directly) makes each key fail.
  - Each key passes on a company seeded through the **real opening-balance import path** (`imports` + `cutover_recon`), with part of the opening AR later collected.
- Register the keys in the strict CI lane (`INVARIANTS_STRICT=1`).

#### WP-F5 Property-based ledger test [DIM6-08] — LLM, M

- Add `hypothesis` to dev requirements.
- New `tests/property/test_ledger_state_machine.py` using a `RuleBasedStateMachine`. Rules: create sales/purchase invoice, receipt, payment, credit/debit note, return, stock adjustment, transfer, production receipt, void, close period. After every step, `run_invariants(company)` must be empty.
- **CI:** `max_examples=50`, on the Postgres job. A nightly scheduled workflow runs `max_examples=2000`.
- Every shrunk failing case is saved as a fixed regression test.

#### WP-F6 Database backstop for unbalanced entries [DIM6-11] — LLM, M

- **Migration** (Postgres only, no-op on SQLite): one check function used by two `CONSTRAINT TRIGGER … DEFERRABLE INITIALLY DEFERRED … FOR EACH ROW` triggers:
  - on the journal **line** table, `AFTER INSERT OR UPDATE OR DELETE` (checks the old and new entry ids);
  - on the journal **entry** table, `AFTER INSERT OR UPDATE OF status`. This catches a DRAFT→POSTED flip with no line change, and a posted entry inserted with no lines.

  For an entry with `status = 'POSTED'`, the check asserts `COALESCE(SUM(debit),0) = COALESCE(SUM(credit),0)` **and** `COALESCE(SUM(debit),0) > 0`, so an empty posted header is rejected (the bug class behind QOS-0055).
- **Before adding it, check the existing data:** a read-only query counts posted entries that are unbalanced or have no lines, per company. Fix or void them through WP-F7 first. Otherwise the first edit to such an entry fails. If some legitimate zero-value posted entries exist, decide with the CA whether they should be voids instead, before the `> 0` rule ships.
- Check the bulk paths (backfills, imports) still pass. They post balanced entries inside one transaction.
- **Tests (postgres):**
  - A raw SQL insert of one unbalanced line in a posted entry fails at commit.
  - A posted entry with no lines fails.
  - A DRAFT entry with unbalanced lines flipped to POSTED fails.
  - Deleting one line of a balanced posted entry fails.
  - Normal posting still works.
  - The zero-downtime-migration guard (`guard_zdt_migrations.py`) accepts it.

#### WP-F7 Repair runbook + safe commands [DIM6-12] — LLM, M

- **Commands:** `backfill_accounting_postings`, `backfill_expense_postings`, `backfill_missing_postings`, `backfill_stock_adjustment_journals`, `repair_bank_match_state`, `repair_orphan_pay_run_journals`, `report_pos_cash_mispost`.
- **Each must:** take `--company`, default to dry run with `--apply` to write, write one `AuditEvent` per applied run, and run `run_invariants` after `--apply` with the result printed.
- **Tests per command:** dry run writes nothing; running `--apply` twice does the same as once; an audit row is written.
- New `docs/ops/LEDGER_REPAIR_RUNBOOK.md`: symptom (invariant key) → command → check. The admin view (WP-D4) links to it.

#### WP-F8 Migration ledger gate in CI [DIM6-13] — LLM, M

- New CI job:
  1. `git worktree add /tmp/base origin/main`, set up a separate venv from `/tmp/base`'s requirements, then run `migrate` + `seed_load_tenant` (small size, several shards) there against the job's Postgres service.
  2. In the PR workspace, with its own venv, run `migrate` then `sweep_all_tenants --fail-on-any --sync` against the same database.

  The base worktree uses `main`'s own seed command and dependencies, so a changed seed script or requirement on the PR can't break the base step.
- Runs only when a PR touches `*/migrations/*`, to keep CI time down.
- **Done when:** a deliberately bad data migration in a test branch fails the job.

#### WP-F9 One CA engagement pack [DIM6-17, SR2-04 part] — Split → Human, M

- Build `docs/ca/SAAS_CA_PACK.md` covering: F9 sheet, QOS-0004 (GSTR worksheets), 0129 (tax-dues wording), 0130 (expense posting, asset acquisition, year-end reversal, recon write-off), 0136 (warranty/commission/renewal), 0138 (Amount involved), 0141 (production costing), plus the WP-F3 flags.
- For each item: what the system does, the automated evidence (test names), and sample PDFs/screens from hosted staging.
- The CA reviews and signs in one engagement instead of seven.

#### WP-F10 Real books: cutover recon + parallel month [DIM6-18, DIM6-19] — Human + Split, L

- **Cutover:** import each pilot's masters and opening balances. `cutover_recon` must show variance 0 or explained, and the customer signs.
- **Parallel month** (2–3 pilots): at month end, export TB, P&L, BS and the GSTR-1/3B worksheets from both systems.
- **LLM part (S):** a comparison script that reads Tally/Busy TB exports (CSV/XLSX) and Bizboard's TB, matches ledgers by name with a mapping file, and prints differences.
- **Done when:** there's zero unexplained difference and every explained one is logged.

---

### WS-G — Performance (Wave 1)

#### WP-G1 Performance targets [12.1] — Split, S

Write proposed p95 targets in `docs/ops/SLO.md` (login, dashboard, invoice Complete < 800 ms, reports, import) for the founder to sign in WP-K3.

#### WP-G2 Load, soak and large-tenant runs on hosted staging [SR1-11, DIM6-15] — Split, M

- **Data:** `seed_load_tenant` for 1 large tenant (3 years, high volume) and 1,000 small tenants.
- **Runs:** `load/k6_smoke.js` → `k6_slo.js` → `k6_mixed.js` at the target concurrency, then an 8-hour soak with `k6_mixed.js`, then the large-tenant reports (TB, P&L, BS, GSTR worksheets, dashboard) and `sweep_all_tenants`.
- **Record:** p95/p99 per scenario, error rate, DB CPU, pool saturation, queue depth (from WP-D2), memory over the soak.
- **Done when:** the results file is `docs/ops/LOAD_RESULTS_<date>.md`, QOS-0003 and QOS-0016 are updated, and there's a fix ticket for each breach.

#### WP-G3 Fix what breaches budget — LLM, M–L (unknown until G2)

Typical fixes: missing indexes (`docs/ops/INDEXES.md`), N+1 queries in report serializers, moving heavy reports to the `reports` queue, caching dashboard aggregates per company. Each fix comes with a query-count test.

---

### WS-H — Security and identity (Waves 1–2)

#### WP-H1 Close MFA (QOS-0103) + decide non-owner policy — LLM + decision, S

Confirm by test that the password, phone-OTP and invite paths all challenge enrolled users, and that owners can't skip enrolment. Decide whether admin/accountant roles need MFA. Implement it as a role setting if yes, then close QOS-0103.

#### WP-H2 Edge protection — Split, S

WAF/DDoS in front of the API (Cloudflare or the provider), rate limits at the edge for `/auth/*`, plus the existing app throttles. Document it in `docs/ops/SECURITY_GROUPS.md`.

#### WP-H3 Independent pentest [SR2-09] — Human + LLM, M

Scope: web app, API, tenant isolation, file uploads, webhooks, admin. Fix every High/Critical with a regression test, then get a retest letter.

#### WP-H4 Access review and offboarding [4.7] — Human, S

Name who has prod access. Hold a quarterly review, and offboard leavers the same day. Use `docs/ops/ACCESS_REVIEW.md`.

#### WP-H5 Consent records, data export and erasure for DPDP — LLM + Split, M

No record of ToS or privacy-policy acceptance exists in `accounts`/`core` today.

- **Model:** `accounts.LegalAcceptance(user, company nullable, document ∈ {TOS, PRIVACY, DPA, BETA}, version, accepted_at, ip_hash, user_agent)`, append-only, plus an RLS migration. Document versions live in settings, filled once counsel publishes (WP-K2).
- **Sign-up and login:** sign-up requires accepting the current ToS + privacy versions. When the version changes, the next login shows a blocking accept screen. The company owner accepts the DPA once per company.
- **Withdrawal and requests:** a settings screen shows what was accepted and when. "Download my data" uses the existing tenant export. "Close my account and delete data" files an erasure request that runs the `erase_company` / tombstone flow after the notice period, with an audit event at each step.
- **Optional consents** (WhatsApp marketing, AI features) reuse the existing consent toggles but also write a `LegalAcceptance`-style row, so there's one history.
- **Tests:** sign-up without acceptance is refused; a version bump forces re-accept; export contains every tenant table in `docs/ops/DATA_CATEGORIES.md`; erasure removes or tombstones everything the erasure playbook lists.
- **Split:** run export and erasure once on hosted staging for a seeded tenant, and record it.

---

### WS-I — AI agents controls (Wave 1)

#### WP-I1 Prove the existing controls and fill the gaps [SR1-12] — LLM, M

- **One choke point for every model call.** Today there are two paths: `core/services/llm.py` (insights assistant and older callers) and `core/services/llm_gateway.py` (agents). Route both through the gateway, or have both call one shared `reserve_spend(company, estimate)` / `settle_spend(company, actual)` function. Any bill/OCR path that calls a model goes through it too.
- **Atomic counters:** per-tenant and platform-wide daily spend in Redis (`INCRBYFLOAT` on a day key, 48 h TTL). Reserve the estimate **before** the call and settle afterwards, so concurrent runs can't overshoot. The durable record stays in the AI usage table, and a nightly job reconciles Redis against it. If Redis is unavailable, refuse the call (fail closed to rules-only).
- **Spend:** show per-company daily runs and model spend in Django admin (data from `insights` AI usage and the agent run records). The platform-wide daily cap stops all LLM calls when crossed and raises an alert.
- **Tests:** 20 concurrent reservations against a cap of 10 units let exactly 10 through; both call paths are counted.
- **Kill switch:** confirm `ENABLE_AGENTS` per tenant plus a global env switch that turns everything to rules-only. Add one if it's missing.
- **Privacy:** a test asserts that payloads sent to the provider (captured through a fake provider in `llm_providers/`) contain none of the PII keys in `agents/redaction.py`. This runs over every agent spec in the registry.
- **Prompt injection:** `tests/agents/test_injection_corpus.py` puts hostile text in customer names, item notes and uploaded bill text, and asserts that tools outside the agent's allow-list are never called and nothing is written without approval.
- **Consent:** the customer UI shows AI on/off per company (the D12 consent toggle exists; check it gates agents too).

#### WP-I2 Decide AI in paid beta [Q5] — Human, S

---

### WS-J — Closed beta operations (Wave 2)

These are mostly people work. The plan gives each one a checklist and an evidence file under `docs/pilot/beta/<company>/`.

| WP | Item | Evidence |
|---|---|---|
| J1 | Recruit and sign 5–10 businesses (beta agreement from counsel) | Signed agreements |
| J2 | Import real books + cutover recon (WP-F10) | Recon sheet signed |
| J3 | Watch unaided onboarding and the core loop, QOS-0029 | Session notes + Journey Health numbers |
| J4 | One full day with no engineer, QOS-0030 | Day log, count of manual fixes (target 0) |
| J5 | Offline outbox on real phones with a bad network, H-03 | Device list, duplicates = 0, lost = 0 |
| J6 | Staffed support channel with a response SLA; tickets tagged by `docs/ops/TICKET_TAXONOMY.md`; weekly P0–P3 triage | Weekly triage notes |
| J7 | Native Hindi review across all modules (QOS-0098, 0125, 0129, 0131, …); real-device and screen-reader pass (QOS-0132) | Signed review CSVs |
| J8 | Incident-response tabletop | Postmortem from the exercise |

---

### WS-K — Commercial and legal (Wave 3)

| WP | Item | Lane |
|---|---|---|
| K1 | Prices, trial length, GST on our own invoices; live Razorpay with daily recon (8.1, 8.6, 8.9) | Human + Split |
| K2 | ToS, privacy policy, DPA, refund policy, DPIA decision — counsel drafts, we publish | Human |
| K3 | Sign SLOs, RPO/RTO, capacity, performance targets | Human |
| K4 | Hypercare roster for days 1–7 and 8–30 | Human |

---

### WS-L — Mobile compatibility (Wave 3)

#### WP-L1 App version policy — LLM, M

- The API reads an `X-App-Version` header from `mobile/`. The server keeps `MIN_SUPPORTED_APP_VERSION` and returns a help code that makes the app show "please update".
- CI contract test: the current `mobile/` API client types are checked against the OpenAPI snapshot, so a breaking change fails.
- Document the policy: support the last 2 releases or 90 days.

---

### WS-M — Governance (continuous)

| WP | Item | Lane |
|---|---|---|
| M1 | **New-module checklist enforced in CI:** any new app or flag that touches money, stock or personal data needs an RLS migration (WP-C3), a ledger registry entry (WP-F1), an invariant, metrics, an alert or explicit "none", Hindi strings, and a runbook line. Extend `guard_config_consistency.py`. | LLM, M |
| M2 | Monthly scorecard refresh: update the Level column with evidence links; open a QOS item for every row that moved down | LLM, S |
| M3 | Quarterly: restore drill, secret rotation, access review, CA spot check of 3 random tenants | Human |

---

## 3. Order and dependencies

```
Week   1    2    3    4    5    6    7    8    9   10   11   12   13   14   15   16
A1 ████████                                                          (commit/tag)
A2-A4 ███
B6 (DLT/SPF/WhatsApp) ██████████                                      (outside parties)
B1        ████████                                                   (hosted staging)
B2-B5          ██████████
C1-C3          ██████████
D1-D5          ████████████████
E1-E2       ██████████
F1,F4,F5 ███████████████
F2 (decision wk1)  ████████████████                                  (shadow books)
F6-F8                ██████████████
G1-G3                     ████████████████
H1-H2          ██████
I1                ████████
F9 pack                     ██████ ── CA review (calendar) ──────────
J1-J8 (beta)                          ███████████████████████████████
F10 parallel month                              █████████████████████
K1-K4                                                  ██████████████████
```

**Hard dependencies:**
- A1 comes before everything (nothing gets signed against an uncommitted tree).
- B1 comes before B2–B5, C1, D1, D3, D5, G2 and all of WS-J.
- E1 comes before D4 (admin rows), B4 (sweep in the restore drill) and F8.
- F1 comes before F3 and M1. F2 and F4 come before F10.
- D2 comes before G2 (you need correct metrics to read the load test).
- F9 needs hosted staging screenshots (B1).
- B6 (SMS DLT, email DNS, WhatsApp) must finish before J3 (real users logging in by phone OTP).
- B1 step 0 (prod overlay RLS) and the agent queues ship in A1 chunk 4/5 or right after; C2's agent beat-task fix ships before agents are switched on for any tenant.
- H5 needs K2's document versions before go-live, but can be built with placeholder versions.
- C4 isn't on the critical path. Do it only when connection count needs pgbouncer transaction mode.

**Parallel work in the LLM lane:** E1, F1, F4, F5, F6, C2, C3, D2, I1, L1 touch different files and can run as separate sessions or worktrees. F2 touches many posting files, so run it alone and don't run F6 at the same time.

---

## 4. How to test (recipes)

- **SQLite fast lane:** `pytest -m "not slow and not postgres"` in `backend/`.
- **Postgres lane:** start a throwaway container (`docker run -d --name saas-pg -p 55440:5432 -e POSTGRES_PASSWORD=pw postgres:17-alpine`), point `DATABASE_URL` at it, `pytest -m postgres -p no:randomly`. Remove the container afterwards. `--create-db` on Postgres takes a long time; use `--reuse-db` after the first run. Two runs must never share one test DB.
- **Private test settings:** when another session is running tests, use a private settings module in the scratchpad (`from config.settings_test import *` with its own `DATABASES["default"]["TEST"]["NAME"]`) via `--ds`.
- **Web:** `npx tsc -b` (not `tsc -p .`), `npm run lint`, `npm test`.
- **API contract:** after any serializer or URL change: `manage.py spectacular` → snapshot, then `npm run gen:api-types`.

---

## 5. Definition of done per wave

| Wave | Done when |
|---|---|
| 0 | Tag `v1.0.0-beta` on a green SHA; guard A2 live; status docs re-baselined; every long-lead person has a date. |
| 1 | Every NFR row at **L2** with an evidence link: hosted staging, RLS proven, Sentry + alerts paging a named person, correct multi-process metrics, per-tenant jobs, backup + PITR + restore drill with clean sweep, rollback rehearsed, load/soak results, AI controls proven. Dim 6 F1–F8 merged. |
| 2 | Dimensions 2–9 at **L3**: 5–10 businesses live, cutover recon signed, a day without an engineer, parallel month with zero unexplained difference, pentest Highs fixed, Hindi review signed, CA pack signed. |
| 3 | Paid renewals reconciled; legal documents published; SLO/RPO/RTO signed; hypercare roster filled. |
| 4 | G1–G17 signed; open sign-up. |

---

## 6. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Uncommitted tree conflicts with other sessions' work | Lost work, broken commits | A1 chunks by path from a manifest; never `git stash`; check other sessions first |
| pgbouncer switched to transaction mode before C4 | One tenant's data visible to another | B1 pins session mode; C4 has a pgbouncer-in-CI test before any switch |
| Prod overlay deployed as-is | App runs as DB owner with RLS off | B1 step 0 + `guard_compose_rls.py` |
| SMS DLT approval slow | Beta users can't log in by phone OTP | B6 starts week 1; password + TOTP login works meanwhile |
| Shadow books (F2) changes numbers for books-off tenants | Customer confusion | Books-off tenants don't see GL figures; backfill per tenant with dry-run review |
| DB trigger (F6) breaks a bulk path | Failed imports | Run the full WF + import suites on Postgres before merging; deferred trigger checks only at commit |
| People items slip (CA, counsel, pentester) | Launch date slips | Book in week 1 (A4); engineering continues in parallel |
| Load test exposes deep performance issues | Wave 1 runs long | Run G2 early in week 5; keep G3 open-ended |
| New feature programmes keep starting | The tree grows again, sign-off queue grows | Founder decision Q6: freeze new programmes until Wave 1 is done |

---

## 7. Decisions needed before starting

| # | Decision | Blocks |
|---|---|---|
| Q1 | Hosting provider and India region | B1 and everything after |
| Q2 | Metrics stack (managed vs self-hosted) | D3 |
| Q3 | On-call primary and backup names | D1, D3, J8 |
| Q4 | Shadow books for every company | F2 |
| Q5 | AI agents in paid beta? | I2 |
| Q6 | Freeze new feature programmes until Wave 1 is done | A1 staying clean |
| Q7 | MFA for non-owner roles | H1 |

---

## 8. Implementation record (2026-10-22)

All engineering work packages were built and tested in the working tree; nothing is committed
(founder's call). Full detail, evidence per WP, and the 20 items only people can finish:
[SAAS_READINESS_HANDOVER_2026-10-22.md](SAAS_READINESS_HANDOVER_2026-10-22.md).

A second pass the same day closed the open and partial list where code could: the restore drill
ran end to end, the blocking strict-invariant lane was brought back to green (it was already red at
`HEAD`), the golden browser suite ran live against Postgres, and the real bugs it found are fixed with tests (a
receipt/Complete deadlock and three alerts that blocked month close among them). Handover §4.

| WP | Engineering status |
|---|---|
| A1 | Not done by choice (commit later); chunk order above stands |
| A2, A3, C1–C3, D2–D4, E1, E2, F1, F3–F8, F10, B2–B4, B6, H1, H5, I1, L1, M1, G1 | Built and tested |
| F2 | Built and tested; existing books-off tenants need `enable_shadow_books` per tenant (ops) |
| F9 | Pack written (`docs/ca/SAAS_CA_PACK.md`); CA signature is a people item |
| B1, B5, D1, D5, G2, G3, H2–H4, J*, K* | People or hosted-infrastructure items; everything they need is in the repo |
| C4 | Not built on purpose (transaction pooling not needed yet) |

Decisions taken while building (beyond §7):
- **Q4 shadow books: yes** (founder, 2026-10-22). Implemented as `Company.post_ledger`, default on;
  `accounting_enabled` now only controls screens and GL-based figures.
- **Q7 MFA for non-owners:** already enforced for every money role (owner, accountant, anyone who
  can post journals); sales staff stay optional.
- The **missed audit seal** still notifies each owner (a product feature with its own tests), now
  one task per company, plus one page to on-call.
- **Repair commands** keep their existing flags (both back-fills already need an explicit
  `--company` to write) and gain the audit row and books check.

Real defects found and fixed while building (each now has a test):
1. Prod compose ran the app as the DB owner (RLS bypassed).
2. pgbouncer template used transaction pooling with session-level tenant settings.
3. No worker consumed the `agents` / `agents_interactive` queues.
4. Eight beat tasks read tenant tables with no tenant set, so under enforced RLS they did nothing:
   agent proposal expiry and cancel, scheduled backups, settings alerts, CRM reminders, CRM stale
   imports, ITC expiry digests, invoice-zip purge.
5. The prod overlay had no pinned web image (it would have built on the host).
6. CD/CI compose validation lacked the app-role variables the overlay now requires.
7. Invoices with taxed freight could not be completed with books on.
8. Purchase credit notes against a discounted bill were unbalanced.
9. Zero-value invoices failed to complete with books on.
10. Books-health DOCS_GL alerts fired falsely for manual-journal opening balances, journal
    write-offs and bills of entry.
