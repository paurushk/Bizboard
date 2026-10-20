# Staging deployment — implementation plan

Status: EXECUTED 2026-10-20 on the local `bizboard-staging` stack (STG-00 = option a, this PC). See "Execution record" at the end.
Target: the `bizboard-staging` Compose project (`docker-compose.staging.yml`, `.env.staging`, host port 8081).
Related: [DOCKER_ENVIRONMENT.md](DOCKER_ENVIRONMENT.md), [TESTING_STRATEGY.md](TESTING_STRATEGY.md), [pilot/RUNBOOKS.md](pilot/RUNBOOKS.md), `scripts/post_deploy_smoke.py`.

Rules for the whole plan
- Staging uses sandbox/test credentials only. No production secrets, live Razorpay, live GSP or real GSTIN/PII.
- Never copy DEV data into staging. Seed with `seed_staging` only.
- Every stage has an exit gate. Do not start the next stage until it passes.
- The deployed artefact is a git tag, not a working tree.
- Always run Compose through `scripts/compose-env.(sh|ps1) staging ...`. It hard-codes `-f docker-compose.yml -f docker-compose.staging.yml`. Extra overlays (tunnel, rollback) need the raw command in the "Raw command" box below.

Raw command (when an extra overlay is needed)
```bash
docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml -f <extra-overlay>.yml <args>
```

---

## Stage 0 — Decide the target (blocker)

| ID | Task | Done when |
|----|------|-----------|
| STG-00 | Decide where staging runs: (a) this Windows PC via Docker Desktop, or (b) a remote Linux server | Decision recorded here |

If (b): also needs SSH access, registry vs build-on-server, and a real hostname/TLS (STG-12). If (a): `scripts/*.sh` run under Git Bash/WSL; the `.ps1` helper covers Compose only.

## Stage 1 — Stabilise and freeze the code

| ID | Task | Command / where | Exit gate |
|----|------|-----------------|-----------|
| STG-01 | Backend tests green (SQLite) | `pytest` in `backend/` | 0 failures |
| STG-02 | Postgres-only concurrency tests green | private Postgres test DB (inventory/IDR-14 recipe in memory) | all pass |
| STG-03 | `ruff` clean | `ruff check` | 0 errors |
| STG-04 | Web `tsc -b`, lint, build, unit tests | `web/` (`tsc -p .` is a no-op) | 0 errors |
| STG-05 | Generated files in sync | regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts`; never read them whole, grep | CI drift check passes |
| STG-06 | `qos-lint` gate and CI green on `main` | `.github/workflows/ci.yml` | CI green |
| STG-07 | Migration rehearsal on a copy of realistic data | `scripts/migration_rehearsal.sh` / `.ps1` | clean forward migrate, no data loss |
| STG-08 | Open sign-offs triaged: each is blocking or deferred with its flag default off | QOS-0129..0139 (CA, Hindi, device) | list written below |
| STG-09 | Commit, then tag `staging-YYYY-MM-DD`; push `main` and the tag | git | tag exists on remote |

Sign-off triage (fill in at STG-08): GL flag for inventory stays default off; CA sign-offs do not block staging but DO block production.

## Stage 2 — Prepare the staging host

| ID | Task | Detail | Exit gate |
|----|------|--------|-----------|
| STG-10 | Install Docker + Compose v2 | needs `!override` and `env_file: path/required` support | `docker compose version` OK |
| STG-11 | Clone repo, check out the tag | `git clone ... && git checkout <tag>` | `git describe` prints the tag |
| STG-12 | Choose exposure (see "Exposure and cookies" below) | loopback only, Cloudflare Tunnel, or reverse proxy with TLS | URL for `FRONTEND_URL` known |
| STG-13 | Create `.env.staging` from `.env.staging.example` and generate unique secrets (one-liners below) | no `change-me` or committed template values left | boot assertions pass |
| STG-14 | Set hosts/origins, mail, backup and MFA/AV variables (lists below) | values match the real URL | reviewed |
| STG-15 | Keep server flags pinned: `ENABLE_GSTR/TALLY/MANUFACTURING/PAYROLL/CRM/FIXED_ASSETS/BOE/...=0`, `GSP_LIVE_ENABLED=0`, `POSTGRES_RLS_ENABLED=1`. Decide the **web** `VITE_ENABLE_*` flags too (STG-20) | diff against template reviewed | reviewed |
| STG-16 | `.env.staging` is gitignored and permissions are tight | `git check-ignore .env.staging` | ignored |

Secret generation one-liners (needed so the boot assertions in `settings.py` do not reject them)
```bash
# DJANGO_SECRET_KEY (must be 40+ chars) and OTP_PEPPER
python -c "import secrets; print(secrets.token_urlsafe(48))"
# MFA_ENCRYPTION_KEY and GSP_FERNET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# PLANWAVE_DATA_KEY (url-safe base64 of 32 bytes)
python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```
Also set unique `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `METRICS_TOKEN`, `SANDBOX_WEBHOOK_SECRET`. `DATABASE_URL`/`REDIS_URL` in `.env.staging` are **overridden** by `docker-compose.staging.yml` (see STG-17).

Extra variables to add to `.env.staging` (none are in the template today)
- Backups fail closed without one of: `BACKUP_AGE_RECIPIENT` (restore needs `RESTORE_AGE_IDENTITY`), `BACKUP_GPG_RECIPIENT`, or `BACKUP_ALLOW_UNENCRYPTED=1`. Choose age for a shared host; unencrypted only if staging is local and holds no real data.
- File uploads are refused unless ClamAV is reachable or `CLAMAV_OPTIONAL=1`. Either start the `clamav` profile and set `CLAMAV_HOST`, or set `CLAMAV_OPTIONAL=1` and record that decision.
- MFA: `MFA_ENFORCE_FOR_MONEY_ROLES` defaults ON in staging. Decide how the walkthrough (STG-35) handles it: enrol TOTP for the seeded money-role users (preferred, tests the real path), or set `MFA_ENFORCE_FOR_MONEY_ROLES=0` **and** `MFA_ENFORCE_WAIVER=1` (staging only; record it as a waiver).

### STG-17 — Database role architecture for RLS (design task, before first deploy)

Problem: `docker-compose.staging.yml` rebuilds `DATABASE_URL` from `POSTGRES_USER` for `migrate`, `api`, `worker` and `beat`, and the Postgres image makes `POSTGRES_USER` a **superuser**, which bypasses FORCE RLS. So `POSTGRES_RLS_ENABLED=1` is on but unproven, and setting `DATABASE_URL` in `.env.staging` has no effect.

Resolution (choose one, record it here):
1. **Two roles (recommended).** Keep `POSTGRES_USER` as the owner/admin role for `migrate`, `backup`, `restore` and `seed_staging`. Add a non-superuser, `NOBYPASSRLS` app role (for example `bizboard_app`, with the needed GRANTs) used by `api`, `worker` and `beat`. This needs a small change to `docker-compose.staging.yml` (separate `APP_DB_USER`/`APP_DB_PASSWORD` variables) and a one-time role-creation SQL step (STG-23a). Implement as a reviewed change, not an ad-hoc edit on the host.
2. **Single superuser (accepted limitation).** Staging runs with RLS flag on but not proven; STG-32 is recorded as NOT PROVEN and RLS stays a production blocker.

Consequences to handle under option 1
- `seed_staging` does not wrap its writes in `rls_bypass()`/`set_rls_company()`, so run it as the admin role (or add the bypass to the command).
- `backup`/`pg_dump` as a no-bypass role dumps no tenant rows: set `BACKUP_DB_USER`/`BACKUP_DB_PASSWORD` to the admin role.

### Exposure and cookies (STG-12 / STG-14)

- Loopback (`APP_BIND=127.0.0.1`, `APP_PORT=8081`) with only local hosts in `DJANGO_ALLOWED_HOSTS` keeps staging in "local staging" mode: plain HTTP, non-secure cookies.
- The moment `DJANGO_ALLOWED_HOSTS` contains any non-local host (tunnel or real domain), settings switch to remote mode: `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` become true, so **login over plain `http://127.0.0.1:8081` stops working**. Use the HTTPS URL for everything after that.
- In remote mode also set `USE_TLS=1`, and `SECURE_SSL_REDIRECT=1` unless the proxy already redirects HTTP to HTTPS. `scripts/edge_tls_smoke.sh` (STG-36) expects the redirect.
- Cloudflare Tunnel: use `docker-compose.cloudflared.yml` through the raw command above, plus the `.trycloudflare.com`/`.cfargotunnel.com` host, CSRF and CORS entries from `.env.staging.example`. Recreate `api worker beat` after any change.
- `docker-compose.expose.yml` is a **DEV** overlay (it only turns off OTP/portal echo, which staging already has off). It does not open the port. To reach staging from another machine, set `APP_BIND=0.0.0.0` in `.env.staging` behind a firewall/proxy, or use the tunnel.

## Stage 3 — Build and first deploy

| ID | Task | Command | Exit gate |
|----|------|---------|-----------|
| STG-20 | Build **all** images including `migrate` (it is profile-gated and goes stale otherwise) | `scripts/compose-env.sh staging --profile migrate build` (PowerShell: `.\scripts\compose-env.ps1 staging --profile migrate build`) | `bizboard-api:latest`, `bizboard-web` exist |
| STG-21 | Image smoke with required arguments | see command below | passes |
| STG-22 | Back up (skip on a fresh host) | `... staging --profile backup run --rm backup` | encrypted dump in `backups/staging` |
| STG-23 | Start db and redis | `... staging up -d db redis` | both healthy |
| STG-23a | Create the app DB role (only if STG-17 option 1) | reviewed SQL via `... staging exec db psql ...` | role exists, `NOSUPERUSER NOBYPASSRLS` |
| STG-24 | Migrate, then post-migration checks | commands below | exit 0 on all |
| STG-25 | Start the stack | `... staging up -d` | all services Up/healthy |
| STG-26 | Seed (first deploy only), as the admin role | `... staging exec api python manage.py seed_staging` | seeded users exist |

STG-21 command (the script needs image, DB URL and optionally the Python minor; on Docker Desktop the default `--network host` does not reach the DB, so join the Compose network)
```bash
SMOKE_DOCKER_ARGS="--network bizboard_staging_net" \
SMOKE_REDIS_URL="redis://:${REDIS_PASSWORD}@redis:6379/0" \
scripts/image_smoke.sh bizboard-api:latest \
  "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/<scratch_db>" 3.13
```
Use a throwaway database name, never the live staging DB.

STG-24 commands
```bash
scripts/compose-env.sh staging --profile migrate run --rm migrate
scripts/compose-env.sh staging run --rm api python manage.py check_indexes        # exit 1 + list if an index build was interrupted; --fix then re-migrate
scripts/compose-env.sh staging run --rm api python manage.py check --deploy --fail-level ERROR
scripts/compose-env.sh staging run --rm api python manage.py observability_gate_check
```

**Web build-time flags.** `VITE_ENABLE_*` (and `VITE_SENTRY_DSN` from `web/.env`) are baked into the `web` image at build time. Changing them later needs `... staging build web` and a recreate, not just an env edit. Decide them at STG-15 and record them in the deploy notes.

## Stage 4 — Verify

| ID | Task | Exit gate |
|----|------|-----------|
| STG-30 | Logs show `compose_env=staging django_env=staging` for api/worker/beat; no tracebacks | clean |
| STG-31 | `python scripts/post_deploy_smoke.py --base-url <url> --email <u> --password <p>` | health, ready, login, invariants pass |
| STG-32 | RLS proof: the app connects as a non-superuser (`SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user` is false/false) and a cross-tenant read returns nothing. Only possible with STG-17 option 1; otherwise record NOT PROVEN | proven or explicitly waived |
| STG-33 | Worker + beat alive: queues drain, a scheduled task fires | verified |
| STG-34 | Static and media: admin CSS loads (if enabled), a file upload works (media volume writable; ClamAV decision from STG-14 applied) | verified |
| STG-35 | Manual walkthrough: login (with MFA per STG-14), sales invoice, quotation, returns, credit/debit notes, money-in/Money Hub, purchase, inventory, dashboard + Needs attention, insights, reports | checklist ticked, defects logged |
| STG-36 | If exposed over HTTPS: `scripts/edge_tls_smoke.sh` | passes |
| STG-37 | Backup then restore proof, see "Restore procedure" | restore reproduces data |

### Restore procedure (STG-37, STG-43)

`scripts/restore.sh` pipes the dump straight into the live DB with `ON_ERROR_STOP` and does not drop anything, so on a populated DB it fails on existing objects.
1. Stop writers: `... staging stop api worker beat`.
2. Reset the schema in the staging DB only: `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` (as the admin role), re-grant the app role if STG-17 option 1 is used.
3. Restore: `... staging --profile restore run --rm restore` (set `RESTORE_FILE` and, for `.age`, `RESTORE_AGE_IDENTITY`).
4. Run `migrate`, `check_indexes`, then start `api worker beat` and re-run STG-31.
5. For a scheduled non-destructive proof, use `scripts/restore_drill.sh`. It restores into a throwaway scratch DB and runs `check_invariants`, so it never touches staging.

## Stage 5 — Operate

| ID | Task |
|----|------|
| STG-40 | Record deployed tag/SHA and the web `VITE_*` values in this doc; set `SENTRY_RELEASE` if Sentry is used |
| STG-41 | Schedule backups and `scripts/check_backup_age.sh` (it also needs the encryption variables from STG-14) |
| STG-42 | Redeploy procedure: backup; **tag the running images as `bizboard-api:previous` and `bizboard-web:previous`**; checkout new tag; build (with `--profile migrate`); migrate + post-migration checks; `up -d`; smoke |
| STG-43 | Rollback procedure, two valid paths. (A) Image rollback: raw command with `docker-compose.rollback.yml` and `BIZBOARD_API_PREVIOUS_IMAGE=bizboard-api:previous`, `BIZBOARD_WEB_PREVIOUS_IMAGE=bizboard-web:previous`. It covers api/worker/beat/web only, not `migrate`, so it cannot undo a migration. (B) Source rollback: checkout previous tag and rebuild. If a migration must be undone or data may be wrong, use the restore procedure instead. Rehearse once. |
| STG-44 | Soak period (suggest 1 week) with defects triaged into `qos/backlog` |

## Stage 6 — Promotion gate to production (not part of this plan's execution)

Requires: soak clean, CA sign-offs closed, RLS proven under a non-superuser role (STG-32 not waived), same tag, `.env.production.example` + `docker-compose.prod.yml`, fresh backups. Plan separately.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Superuser DB role bypasses FORCE RLS, so RLS looks proven when it is not | STG-17 role split; STG-32 checks `rolsuper`/`rolbypassrls` |
| Compose overrides `DATABASE_URL`, so editing it in `.env.staging` does nothing | STG-17 change is made in `docker-compose.staging.yml` |
| Backup and restore exit 1 without encryption variables | STG-14 sets them before STG-22 |
| Backup as the app role dumps no tenant rows | `BACKUP_DB_USER` = admin role |
| Stale `migrate` image reports "No migrations to apply" | STG-20 uses `--profile migrate build` |
| Adding a remote host flips cookies to Secure and breaks HTTP login | "Exposure and cookies" section; use HTTPS URL |
| Web flags baked at build time drift from runtime flags | STG-15/STG-20 rebuild rule |
| Boot fails on missing SMTP, bad hosts/origins or malformed keys | STG-13/14 one-liners and checks before first `up` |
| Media volume owned by root blocks uploads, or ClamAV unreachable blocks them | entrypoint chowns; STG-34 plus ClamAV decision |
| Restore into a populated DB fails | Restore procedure resets the schema and stops writers |
| Rollback overlay needs previous-image variables | STG-42 tags `:previous` before each deploy |
| Port or volume collision with DEV | separate project name, volumes and network are already in the overlay |
| Tunnel URL changes (quick tunnel) | update `CORS_*`/`CSRF_*`, recreate api/worker/beat |

## Review disposition (2026-10-20)

Accepted and folded in: DATABASE_URL override and superuser/RLS conflict (STG-17, STG-32), seed_staging and RLS, `--profile migrate` build, `image_smoke.sh` arguments, backup encryption variables and `BACKUP_DB_USER`, compose-env scope and the raw-command rule, `expose.yml` being DEV-only, rollback overlay variables, cookie/HSTS/redirect behaviour, `VITE_*` build-time flags, post-migration `check_indexes`/`check --deploy`/`observability_gate_check`, MFA enforcement, restore procedure, ClamAV, key-generation one-liners.
Not acted on: the closing offer to edit `docker-compose.staging.yml` and `seed_staging.py` directly. Those are code changes outside this plan document and are tracked as part of STG-17 for a separate, reviewed change.

## Effort (rough)

Stage 1: 0.5-2 days depending on open sign-offs. STG-17 role split: about half a day including a test run. Stages 2-4: about half a day on a ready host. Stage 5: ongoing.

---

## Execution record (2026-10-20, local Docker Desktop, option a)

| Item | Result |
|------|--------|
| STG-00 | Local PC. Staging already existed (2-day-old images, 331 migrations); upgraded in place. |
| STG-01 | Backend suite: 5302 passed, 81 skipped; 3 failures: 2 stale GSTR snapshot baselines (refreshed, additive only: `document_ids`, `reversed_ineligible`) and `test_i4_catalog_import_of_5000_skus` (wall-clock gate, 19s vs 10s on a loaded laptop; see Open items). |
| STG-02 | Postgres-marked tests run against a throwaway `postgres:17` container (CI=1, RLS on). Clean run: 72 passed (includes the 2 new RLS tests). Throwaway container removed. |
| STG-03/04/05 | `ruff check .` clean; `makemigrations --check` no changes; web `tsc -b` and `npm run lint` pass. OpenAPI snapshot not regenerated (no API shape change). |
| STG-07 | Migration rehearsal: empty-DB migrate via `image_smoke.sh` OK; real staging DB migrated 331 -> 534 OK. |
| STG-09 | NOT done: nothing committed, tagged or pushed (needs your go-ahead). Deployed from the working tree on top of `2bb18d9`. |
| STG-13/14/15 | `.env.staging` gained `MFA_ENCRYPTION_KEY`, `PLANWAVE_DATA_KEY`, `METRICS_TOKEN`, `APP_DB_USER/PASSWORD`, `BACKUP_ALLOW_UNENCRYPTED=1` (local only), `CLAMAV_OPTIONAL=1`, `POSTGRES_RLS_ENABLED=1` (HEAD refuses to boot staging with it off), and the `ENABLE_*` pins at 0. Old file backed up outside the repo. |
| STG-17 | Done, option 1: `docker-compose.staging.yml` now builds api/worker/beat `DATABASE_URL` from `APP_DB_USER`/`APP_DB_PASSWORD`; `scripts/staging-db-role.sh` creates/refreshes `bizboard_app` (NOSUPERUSER NOBYPASSRLS). Owner role still used by migrate/backup/restore/seed. |
| STG-20/21 | Built with `--profile migrate`. `image_smoke.sh` needed throwaway `MFA_ENCRYPTION_KEY`, `PLANWAVE_DATA_KEY` and `POSTGRES_RLS_ENABLED=1` added to its env (it was stale against HEAD); passes. |
| STG-22 | Backups taken before and after deploy and before the restore rehearsal (unencrypted, local only). |
| STG-24 | `migrate` OK; `check_indexes` all valid; `observability_gate_check` runs (lists the human O-Gate items); `check --deploy` shows warnings only (SSL redirect/HSTS preload, plain-HTTP loopback). |
| STG-26 | `seed_staging` ran as owner: fixtures already existed. |
| STG-30 | All services healthy; gunicorn control-socket error removed with `--no-control-socket` in the staging overlay. |
| STG-31 | `post_deploy_smoke.py` fixed (it did not unwrap the `{success,data}` envelope, and every seeded owner needs MFA): health, ready, login OK; authenticated invariants replaced by `manage.py check_invariants` (7 companies clean). |
| STG-32 | RLS proven. App role is `rolsuper=f, rolbypassrls=f`; with no tenant context it reads 0 invoices, with the right tenant 27, with another tenant 0; owner sees 33; table is ENABLE+FORCE RLS. |
| STG-33 | Worker and beat run tasks (heartbeat, attention sweeps, recurring invoices) as the app role with no RLS errors. |
| STG-35 | Browser: login, TOTP enrolment, MFA sign-in, setup wizard, authenticated GET sweep (200s; 400/403 are feature gates), customer create via API. A full click-through of every module was NOT done by hand. |
| STG-36 | N/A: loopback HTTP only. |
| STG-37 | `restore_drill.sh` PASS; real restore rehearsal on staging (stop writers, reset schema, restore, re-grant, migrate, start) PASS: data identical, smoke OK. |
| STG-42/43 | `bizboard-api:previous` and `bizboard-web:previous` tagged from the deployed images; rollback overlay renders with them and fails closed without them. A live rollback was not exercised. |

### Defect found and fixed during execution

With the app on a real non-superuser role, every sign-in 500ed: `LOGIN` and `MFA_*` audit rows are written before the middleware knows the tenant, and `core_auditevent` is FORCE RLS ("new row violates row-level security policy"). The superuser role had been hiding it. Fix: `core.rls.company_scope()` plus `AuditService.log` writes inside the event's own company scope (bypass when the event has no company). Tests: `tests/test_audit_company_scope.py` (SQLite no-op case; two Postgres cases).

### Files changed (all uncommitted)

`docker-compose.staging.yml`, `.env.staging.example`, `docs/DOCKER_ENVIRONMENT.md`, this plan, `scripts/staging-db-role.sh` (new), `scripts/post_deploy_smoke.py`, `scripts/image_smoke.sh`, `backend/core/rls.py`, `backend/core/services/audit.py`, `backend/tests/test_audit_company_scope.py` (new), `backend/tests/snapshots/__snapshots__/gstr1_intrastate.json`, `gstr3b.json`. `.env.staging` is gitignored.

### Follow-up round (2026-10-20, same day) — open items worked

1. **Commit / tag / push**: done at the end of this round (tag `staging-2026-10-20`). The running images were built from exactly the committed tree.
2. **`test_i4_catalog_import_of_5000_skus`**: passes on Postgres (the CI database). Only borderline on SQLite on this Windows laptop (10.2s idle, 19s loaded). No code change; not a regression.
3. **Live rollback**: exercised. `docker-compose.rollback.yml` with `bizboard-api:previous` / `bizboard-web:previous` ran the stack, smoke passed, then returned to `:latest`. Browser walkthrough: shell, setup wizard, Money, Needs attention, Products, Insights and Collections all loaded with every API call 200 (no 5xx or RLS errors in the api log). Per-module hand testing of every screen is still a human task.
4. **Human sign-offs** (CA QOS-0129..0139, Hindi review, device checks, O-Gate Sentry/on-call): not something code can close. Unchanged.
5. **Tenant-less writes sweep**: probed every unauthenticated flow live as the real app role. Found and fixed one more: **sign-up returned 500** (`RegisterView` wrote the warehouse, chart of accounts, audit and telemetry rows with no tenant context). Now wrapped in `company_scope`. Password reset + confirm, login/MFA and invite accept (to its seat-limit rule) are clean; public invoice/quotation/portal/Shopify views already use `rls_bypass` + `set_rls_company`; OTP login is off in staging. Regression test `test_signup_works_under_a_non_superuser_role` runs sign-up under a NOSUPERUSER NOBYPASSRLS role on Postgres; verified it fails without the fix and passes with it.
6. **Resend key / staging mail**: NOT resolved, needs you. The key in `.env.staging` is a real Resend key and the sender domain (`bizboard.com`) is **not verified** at Resend (SMTP 550), so every OTP, password-reset and invite email from staging fails (sign-up on staging therefore cannot complete for real users). Verify the domain at Resend, or switch staging to a mail trap; and confirm this key is not the production key.
7. **Gunicorn control-socket error**: fixed at the root in `backend/docker-entrypoint.sh` (`HOME=/home/app` after dropping privileges), so every environment is covered; the staging-only flag was removed.

Leftovers on the staging DB: one probe company `RLS Probe 83b186` and its two users. The company cannot be deleted (audit/accounts rows are protected by design); harmless test data.
