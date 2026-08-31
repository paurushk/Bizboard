# Support runbooks (Phase 1)

## PDF worker down
- Symptom: invoice Complete succeeds but `pdf_status=QUEUED/FAILED`.
- Check: `docker compose ps worker`, Celery logs.
- Fix: restart worker; use Regenerate PDF on invoice detail.
- Customer workaround: download after regenerate.

## PDF download not ready (P0-404)
- Symptom: `GET /api/v1/sales/invoices/{id}/pdf/` returns **409** with `"PDF is generating, retry shortly"` (and current `pdf_status`).
- Meaning: stored ORIGINAL is not `READY` / missing `pdf_file`. Download **never** sync-renders PDF (avoids request hangs when the worker is down or slow).
- Behavior:
  - `QUEUED` → 409 only (no re-enqueue storm).
  - `NONE` / `FAILED` → status set to `QUEUED`, `generate_invoice_pdf.delay(...)` enqueued, then 409.
- Client: poll `GET .../pdf-status/` or retry download shortly; use `POST .../regenerate-pdf/` for explicit retry after `FAILED`.
- If 409 persists: treat as “PDF worker down” above.

## OTP / SMS failure
- Symptom: OTP request errors “not configured”.
- Phase 1: use email/password login; set `SMS_PROVIDER` + provider credentials for phone OTP.
- Never enable `OTP_DEBUG_ECHO` in production.
- Frontend: production builds hide the OTP login tab unless `VITE_ENABLE_OTP=true`. The “Dev OTP:” hint is shown only when `import.meta.env.DEV` is true **and** the API returns `debugCode`.

## Media / invoice PDF download (BUG-703 / P0-101)
- **Pilot decision:** invoice PDFs and uploads are served by the Django API via `FileResponse` after JWT + tenant checks — **not** via nginx `X-Accel-Redirect`.
- nginx `location /media/` is `internal` so direct `/media/company_N/...` URLs are not publicly enumerable.
- Clients download through authenticated API routes (e.g. `GET /api/v1/sales/invoices/{id}/pdf/`). Unauthenticated → 401; cross-tenant → 404.
- Post-pilot: optional upgrade to `X-Accel-Redirect` for offloading large files without changing the auth boundary.

## SMTP / email share failure
- Symptom: Share email queued but not delivered.
- Set `EMAIL_HOST` / user / password; verify `DEFAULT_FROM_EMAIL`.
- WhatsApp share opens a link only (Business API later).

## Discount mode questions
- **Cash discount (after tax)**: reduces amount payable; GST unchanged.
- **Discount (reduces GST)**: lowers taxable value then GST — use when commercial discount should reduce tax.

## Place of supply blocked
- Add customer/supplier state or GSTIN, or Owner enables “Assume local state for blank party” in GST settings (use sparingly).

## Database backup / restore (BUG-733 / Wave 16A)
- **Backup:** `docker compose --profile backup run --rm backup` (writes gzipped dump under `./backups/`), or `docker compose exec db pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} > backup_$(date +%Y%m%d).sql`. Schedule daily via host cron/ops tooling and copy the dump off-host (S3/other durable storage) — the `postgres_data` Docker volume alone is not a backup.
- **Restore (scripted):** `docker compose --profile restore run --rm restore` uses [`scripts/restore.sh`](../../scripts/restore.sh) against the latest `./backups/bizboard-*.sql.gz` (or `RESTORE_FILE=...`).
- **RPO / RTO:** RPO = time since last successful off-host backup; RTO = restore script duration + `migrate` check + app start. Record both after every drill.
- **Restore drill (practice this before you need it for real) — Final Gate:**
  1. `docker compose stop api worker beat` (stop all writers including Celery beat).
  2. Run restore profile (or `psql` pipe) on a scratch environment.
  3. `docker compose start api worker`, then verify via `/api/v1/health/` and a spot-check invoice/customer lookup.
  4. Date the drill in `GO_NO_GO.md`. Monthly scratch drills are ops calendar, not CI.
- **If the Postgres volume itself is lost/corrupted:** restore the most recent dump into a fresh `db` volume; there is currently no other backup path, so the dump cadence above is the entire recovery story.

## Observability (Wave 16A)
- Set `SENTRY_DSN` (+ optional `SENTRY_RELEASE`) for Django + Celery. Frontend: `VITE_SENTRY_DSN`.
- PagerDuty / on-call routing remains an ops Final Gate (BB-000509).

## Digest-pinned deploy (Wave 16A)
- Prefer `scripts/pin_image_digests.sh <api-ref> <web-ref>` → `docker-compose.digest.yml`.
- Host-side digest verification each release remains Final Gate (BB-000470).
- Run from repo root; the script writes digest compose overlay. It does **not** sign `GO_NO_GO.md`.

## TLS terminator (facts)

Django does not terminate TLS. Pilot/prod HTTPS is at the edge (Caddy, nginx, or cloud LB). When the app sits behind that terminator:

- Set `USE_TLS=1` so secure cookies, `SECURE_PROXY_SSL_HEADER`, and HSTS-related Django flags apply.
- End-user traffic must be HTTPS before any real GSTIN/PII lands (`ENV_CHECKLIST.md` E1). Plain HTTP to the browser is a hard no-go even if the app container speaks HTTP on an internal port.
- Webhooks (Razorpay, GSP) must hit the public HTTPS hostname, not a raw IP / docker port.

Certificate issuance, renewal, and HSTS preload are ops — not this runbook.

## Deploy rollback (P0-508 / E9)

Record the **image tag** (or compose build digest) and **migration head** for every pilot deploy.

### Decision tree
1. **App-only regression** (bad code, no schema/data corruption): redeploy the previous known-good **image tag**. Prefer tag rollback over “rebuild whatever is on main.”
2. **Schema-forward migration is safe to reverse** (pure additive/reversible; verified `reverse` exists):  
   `docker compose exec api python manage.py showmigrations <app>`  
   then `docker compose exec api python manage.py migrate <app> <previous_migration_name>`  
   then redeploy the matching older image.  
   **Do not** reverse data migrations that mutated money/docs unless you have a tested reverse **and** a backup.
3. **Data integrity suspected / irreversible migration / unknown blast radius:** **stop writers**, **restore from backup** (see above), then bring up the last known-good image tag. Prefer restore over clever migrate-backwards when money or tenant data may be wrong.
4. After any rollback: hit `/api/v1/health/`, spot-check complete→PDF→ledger, and note the incident in the go log.

### Image tags
- Tag releases explicitly (e.g. `bizboard-api:2026-08-01-a1b2c3d`) rather than only `:latest`.
- Keep the previous tag pullable for at least one pilot week.

## Migration rollback (detail)
- Identify the last-known-good migration per app: `docker compose exec api python manage.py showmigrations <app>`.
- Roll back: `docker compose exec api python manage.py migrate <app> <previous_migration_name>`.
- Data migrations should have a real reverse (not a silent no-op) — verify before relying on this for anything that mutated data, and always restore from backup first if the rollback is due to a suspected data-integrity issue rather than a pure schema mistake.

## Healthchecks (P0-502 / E2) — documented skips
- **Present:** `db` (`pg_isready`), `redis` (`PING`), `api` (`GET /api/v1/health/`).
- **Skipped by design:** `worker`, `web`, `nginx` compose healthchecks.
  - Worker: prefer watching Celery queue depth / `inspect active` over a flaky `celery inspect ping` healthcheck that can false-red during broker blips.
  - Web/nginx: nginx already `depends_on` api healthy; static web has no meaningful deep check worth the compose noise for pilot.
- Restart policies: `unless-stopped` on api/worker/db/redis/web/nginx.

## Basic monitoring
- No dedicated monitoring stack ships with this repo yet. At minimum, poll `GET /api/v1/health/` from an external uptime checker and alert on failures/latency.
- Watch Celery queue depth (`docker compose exec worker celery -A config inspect active`) during PDF-generation bursts — a growing backlog is the earliest signal of the "PDF worker down" scenario above before customers notice.

## On-call (placeholder)
- **Primary:** _TBD (pilot owner)_ — phone/Slack: _TBD_
- **Secondary:** _TBD_
- **Hours:** best-effort during pilot business hours (IST) unless otherwise agreed.
- **Escalate when:** `/health/` down >5m; PDF queue stuck with customer-visible 409s; backup job failed; suspected cross-tenant incident (page immediately).
- Fill names before paid pilot traffic; keep the page in the same channel as uptime alerts.
