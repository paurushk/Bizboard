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

## Alert rules (WP-D3)

The rules live in [`deploy/prometheus/alerts.yml`](../../deploy/prometheus/alerts.yml); the
scrape config in [`deploy/prometheus/prometheus.yml`](../../deploy/prometheus/prometheus.yml).
`/metrics` sums every gunicorn worker (`PROMETHEUS_MULTIPROC_DIR`), and each Celery worker
serves its own task metrics on port 9100. `tests/test_alert_rules.py` checks that every rule
points at a section below. **page** = on-call phone now; **ticket** = ops channel, next business day.

### health-down
`BizBoardApiDown` (page). The collector cannot reach the api. Same steps as **Health down** in the
table above. Check the external uptime probe too: if it is green, the problem is the collector.

### 5xx-rate
`BizBoardHigh5xxRate` (page). More than 2% of requests fail. Open Sentry for the release in
`SENTRY_RELEASE`; the top issue is usually the cause. If it started with a deploy, roll back per
`docs/ops/FORWARD_FIX.md` (previous image digest), never by reversing a migration.

### slow-requests
`BizBoardSlowRequests` (ticket). p95 over 2 s. Check DB CPU and slow-query log, then queue depth.
Compare with the last load-test results (`docs/ops/LOAD_RESULTS_*.md`).

### ready-fail
`BizBoardDatabaseDown` (page). Same steps as **Ready fail** in the table above.

### beat-silent
`BizBoardBeatSilent` (page). Same steps as **Beat silent** in the table above. Nightly books
check, backups and reminders stop while beat is down.

### queue-backlog
`BizBoardHighPriorityBacklog` (page) / `BizBoardQueueBacklog` (ticket). Check workers are up and
consume every queue (`-Q celery,high_priority,media_heavy,reports,agents,agents_interactive`;
guard `compose_rls` enforces this). Scale workers per `docs/ops/WORKER_SCALE.md`. OTP and payment
work sit on `high_priority`: a backlog there means people cannot sign in or get paid.

### pdf-queue
`BizBoardWorkerDown` (page). Same steps as **PDF queue** in the table above.

### task-failures
`BizBoardTaskFailures` (ticket). Group the failures in Sentry by task name. One company's crash no
longer stops a nightly job (WP-E1), so check whether it is one tenant or all.

### circuit-open
`BizBoardCircuitOpen` (ticket). A payment / SMS / GSP provider is failing. Check the provider's
status page; the breaker fails closed and money paths retry from the outbox.

### webhook-4xx-burst
`BizBoardDeadLetters` (ticket). Same steps as **Webhook 4xx burst** in the table above.

### books-check
`BizBoardBooksCheckFailed` (page, business hours). See
[`LEDGER_REPAIR_RUNBOOK.md`](LEDGER_REPAIR_RUNBOOK.md). Django admin → Tenant sweep results lists
the failing companies and checks.
