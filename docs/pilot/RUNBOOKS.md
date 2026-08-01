# Support runbooks (Phase 1)

## PDF worker down
- Symptom: invoice Complete succeeds but `pdf_status=QUEUED/FAILED`.
- Check: `docker compose ps worker`, Celery logs.
- Fix: restart worker; use Regenerate PDF on invoice detail.
- Customer workaround: download after regenerate.

## OTP / SMS failure
- Symptom: OTP request errors “not configured”.
- Phase 1: use email/password login; set `SMS_PROVIDER` + provider credentials for phone OTP.
- Never enable `OTP_DEBUG_ECHO` in production.

## SMTP / email share failure
- Symptom: Share email queued but not delivered.
- Set `EMAIL_HOST` / user / password; verify `DEFAULT_FROM_EMAIL`.
- WhatsApp share opens a link only (Business API later).

## Discount mode questions
- **Cash discount (after tax)**: reduces amount payable; GST unchanged.
- **Discount (reduces GST)**: lowers taxable value then GST — use when commercial discount should reduce tax.

## Place of supply blocked
- Add customer/supplier state or GSTIN, or Owner enables “Assume local state for blank party” in GST settings (use sparingly).

## Database backup / restore (BUG-733)
- **Backup:** `docker compose exec db pg_dump -U ${POSTGRES_USER:-bizboard} ${POSTGRES_DB:-bizboard} > backup_$(date +%Y%m%d).sql`. Schedule this daily via host cron/ops tooling and copy the dump off-host (S3/other durable storage) — the `postgres_data` Docker volume alone is not a backup.
- **Restore drill (practice this before you need it for real):**
  1. `docker compose stop api worker` (stop writers).
  2. `docker compose exec -T db psql -U ${POSTGRES_USER:-bizboard} ${POSTGRES_DB:-bizboard} < backup_YYYYMMDD.sql`
  3. `docker compose start api worker`, then verify via `/api/v1/health/` and a spot-check invoice/customer lookup.
  4. Run this drill on a schedule (e.g. monthly) against a scratch environment, not just when a real incident forces it.
- **If the Postgres volume itself is lost/corrupted:** restore the most recent dump into a fresh `db` volume; there is currently no other backup path, so the dump cadence above is the entire recovery story.

## Migration rollback
- Identify the last-known-good migration per app: `docker compose exec api python manage.py showmigrations <app>`.
- Roll back: `docker compose exec api python manage.py migrate <app> <previous_migration_name>`.
- Data migrations should have a real reverse (not a silent no-op) — verify before relying on this for anything that mutated data, and always restore from backup first if the rollback is due to a suspected data-integrity issue rather than a pure schema mistake.

## Basic monitoring
- No dedicated monitoring stack ships with this repo yet. At minimum, poll `GET /api/v1/health/` from an external uptime checker and alert on failures/latency.
- Watch Celery queue depth (`docker compose exec worker celery -A config inspect active`) during PDF-generation bursts — a growing backlog is the earliest signal of the "PDF worker down" scenario above before customers notice.
