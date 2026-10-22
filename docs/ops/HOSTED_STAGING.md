# Hosted staging (WP-B1, B2, B4, B5, C1, D1–D5, G2)

The first environment that is not a laptop. Everything a person must do is marked **[Human]**;
the repo already holds the code, configs and checks it runs. Fill the execution record at the
bottom as each step is done — the scorecard row moves from L1 to L2 only with a dated entry here.

## 0. Decide (founder) [Human]

- Provider and India region (Q1). Requirements: managed PostgreSQL 17 with point-in-time
  recovery, managed Redis, object storage with versioning, private networking, a VM (2 vCPU / 8 GB
  is enough for staging), and DNS you control.
- Metrics stack (Q2): a managed Prometheus-compatible service, or Prometheus + Alertmanager +
  Grafana on the same VM using `deploy/prometheus/`.
- On-call primary and backup (Q3) → `docs/ops/ONCALL_ROSTER.md`.

## 1. Provision [Human]

1. Managed Postgres 17, PITR on, private network only. Note the owner user.
2. Managed Redis, private. Object storage: one bucket for media (versioning on), one bucket in a
   **separate account** for backups.
3. VM with Docker; clone the repo at the tag to deploy into `STAGING_DIR`.
4. DNS + TLS at the edge (Cloudflare tunnel: `docker-compose.cloudflared.yml`, or the provider LB).
5. Put the edge in front of `/auth/*` with rate limits and the WAF on (`docs/ops/SECURITY_GROUPS.md`).

## 2. Configure

1. `.env` from `.env.production.example` with `DJANGO_ENV=staging`. Required (staging refuses to
   boot without them): `POSTGRES_RLS_ENABLED=1`, `APP_DB_USER`/`APP_DB_PASSWORD`,
   `MFA_ENCRYPTION_KEY`, `PLANWAVE_DATA_KEY`, `GSP_FERNET_KEY`, `OTP_PEPPER`, `SECRET_KEY`,
   `METRICS_TOKEN`, `SENTRY_DSN`, `SENTRY_RELEASE` (= the git SHA), `VITE_SENTRY_DSN`.
   Keep secrets in the provider's secret store and render `.env` at deploy time (WP-B3).
2. Pool: if PgBouncer is used, `pool_mode = session` (`deploy/pgbouncer.ini`, `docs/ops/POSTGRES.md`).
3. Backups: `BACKUP_AGE_RECIPIENT` (or GPG), `BACKUP_OFFSITE_CMD` to the backup bucket,
   `BACKUP_REQUIRE_OFFSITE=1`. Run `scripts/check_backup_age.sh` hourly from cron; it exits 1 when
   the newest encrypted dump is older than 26 h. On failure, POST to the ops pager
   (`/api/v1/ops/alert/?token=<OPS_ALERT_TOKEN>`, see `docs/ops/ALERTS.md` → Backup failed).

## 3. First deploy

Use `.github/workflows/deploy-staging.yml` (action `deploy`, the commit SHA). It resolves image
digests, saves the running digests for rollback, runs `migrate` as the owner, re-applies the app
role (`scripts/db-app-role.sh`), starts api/worker/beat/web and runs `scripts/post_deploy_smoke.py`.

Then, once:

```bash
docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml --profile migrate run --rm migrate python manage.py seed_staging
scripts/edge_tls_smoke.sh https://<staging host>
```

## 4. Prove it (each line becomes an execution-record row)

| Check | How | Pass when |
|---|---|---|
| RLS really on | `docker compose ... exec api python -c "..."` → `SELECT current_user, rolbypassrls FROM pg_roles WHERE rolname=current_user` | app role, `rolbypassrls = f` |
| Tenancy suite on the host DB | Point `DATABASE_URL` at a **scratch database** on the same Postgres instance; `pytest tests/test_rls_coverage.py tests/tenancy/ tests/test_beat_tasks_rls_postgres.py -m postgres` | all pass, none skipped (`scripts/ci_gates/check_postgres_skips.py`) |
| Sentry | `python manage.py sentry_test_event` | event visible, page received (`docs/ops/OGATE_HUMAN.md`) |
| Metrics | collector scrapes `api:8000/api/v1/metrics/` and `worker:9100` | `up == 1` for both; 100 requests → `bizboard_http_requests_total` +100 with 4 gunicorn workers |
| Alerts | fire each rule in `deploy/prometheus/alerts.yml` once (stop worker, stop beat, …) | each reaches the named phone |
| Support ID walk | `docs/ops/OGATE_GREP_WALK.md` | one ID found in UI, API log, worker log, Sentry |
| Uptime + status page | external probe on `/api/v1/health/` and `?ready=1` every minute | probe history visible; status page URL in `docs/ops/STATUS_COMMS.md` |
| Rollback | deploy N, deploy N+1, run the workflow with `rollback` | N serving again; timings recorded |
| Backup + restore | nightly backup lands off-host; run `scripts/restore_drill.sh` style restore from that file into a scratch DB; `sweep_all_tenants --sync --full --fail-on-any` as the app role | all companies CLEAN; RTO recorded |
| PITR | provider restore to timestamp T into a new instance; media from bucket versions at T | app boots, sweep CLEAN |
| Secret rotation | `docs/ops/SECRET_ROTATION.md` for app DB password, `METRICS_TOKEN`, one Fernet family | drill log rows |
| Live messaging | `post_deploy_smoke.py --live-comms --oncall-phone ... --oncall-email ...` | OTP SMS and email arrive (WP-B6) |
| Load | `docs/ops/LOAD_RESULTS_TEMPLATE.md` | results file committed |

## Execution record

| Date | Step | Result / evidence link | By |
|---|---|---|---|
| | | | |
