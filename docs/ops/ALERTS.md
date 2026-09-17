# Per-alert runbooks (11.5)

Each alert must name the symptom, the check, and the customer-safe workaround.
Pages go to the names in `docs/ops/ONCALL_ROSTER.md` (still TBD until Human fills them).
Sentry/on-call close-out: `docs/ops/OGATE_HUMAN.md`. Staging Support-ID grep: `docs/ops/OGATE_GREP_WALK.md`.

| Alert | Symptom | First check | Action | Customer workaround |
|---|---|---|---|---|
| Health down | `/api/v1/health/` ≠ 200 for >5m | `docker compose ps api db redis` | Restart api; if db unhealthy, do **not** restart writers until disk/WAL is understood | “We’ll be back shortly” — do not tell them to re-complete invoices |
| Ready fail | `?ready=1` 503 | db `pg_isready`, redis `PING` | Restore network / credentials; do not flip `POSTGRES_RLS_ENABLED` | Same |
| PDF queue | Completes 200, `pdf_status=QUEUED/FAILED`, download 409 | `docker compose logs worker` | Restart worker; invoice detail → Regenerate PDF | Retry download; never complete twice |
| Beat silent | Heartbeat missing | `celery -A config inspect active` on worker; beat container | Restart beat **once**; duplicate beat double-sends dunning | AR/SaaS reminders may lag |
| Webhook 4xx burst | Gateway retries | Signature secret vs dashboard | Rotate per `SECRET_ROTATION.md`; replay DLQ `manage.py replay_dead_letter` | Payment shows unpaid until replay |
| Billing recon DLQ | `DeadLetterEvent` provider=`billing_recon` | Compare Razorpay dashboard vs `Subscription.status` | Replay or apply mapping; do **not** run `payments.dunning` | Owner sees past-due banner |
| SaaS dunning mail fail | SMTP errors in worker | `EMAIL_HOST` / console backend forbidden in prod | Fix SMTP; sweep is best-effort, AuditEvent still written | Owner still blocked by write-gate when grace ends |
| Backup failed | Dump job non-zero | Disk, `pg_dump` logs | Re-run dump; page if two consecutive failures | None — RPO slips |
| Suspected cross-tenant | Any IDOR report | Freeze writes, snapshot DB | Incident `SEV-1` — `INCIDENT_RESPONSE.md` | Disable account until cleared |

Do not invent GST filing advice in an alert reply. Worksheets are offline aids (freeze C1).
