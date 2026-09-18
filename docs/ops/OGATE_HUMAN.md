# O-Gate 1 — Human steps

Engineering for tags, `/metrics`, and `sentry_configured` is in the repo.
These steps still need a live Sentry org and named on-call. Do not invent
names or commit a real DSN.

## OG1-H1 — Sentry project

1. Create one Sentry org/project (browser + Django + Celery can share it).
2. Tag events with `runtime=django|celery|browser` if you split later.
3. Paste the project URL here when done: _

## OG1-H2 — Host env (not git)

On API, worker, and beat:

```
SENTRY_DSN=https://...
SENTRY_RELEASE=<deploy SHA>
SENTRY_TRACES_SAMPLE_RATE=0.1
METRICS_TOKEN=<long random>
```

SPA image rebuild:

```
VITE_SENTRY_DSN=https://...
```

Templates: `.env.production.example`, `.env.staging.example`, `web/.env.example`.

## OG1-H3 — Roster

Fill **weekday IST 09–21** primary + how they are paged in
`docs/ops/ONCALL_ROSTER.md`. Empty primary = nobody is paged.

## OG1-H3b — Page via Telegram (no-infra PagerDuty alternative)

Pilot scale doesn't need a paid on-call product. `POST /api/v1/ops/alert/`
(`core/views.py::ops_alert_webhook`) is a token-guarded relay that forwards
any alert-source POST to a fixed Telegram chat — wire it up instead of (or
until you want) PagerDuty/Grafana OnCall:

1. Create a Telegram bot with @BotFather if you don't already have
   `TELEGRAM_BOT_TOKEN` set; the same bot can serve both customer-facing
   Telegram notifications and ops paging.
2. Create a private Telegram group for on-call, add the bot to it, send one
   message, then hit `https://api.telegram.org/bot<TOKEN>/getUpdates` to read
   the group's `chat.id` (it's negative for groups, e.g. `-1001234567890`).
3. Generate a random `OPS_ALERT_TOKEN` and set it + `OPS_TELEGRAM_CHAT_ID`
   (the group id from step 2) on the API host.
4. In Sentry: Settings → Developer Settings → **New Internal Integration**.
   Enable "Alert Rule Action", and set the Webhook URL to
   `https://<api-host>/api/v1/ops/alert/?token=<OPS_ALERT_TOKEN>`. Save, then
   create/edit an alert rule to use "Send a notification via
   `<your integration name>`".
5. For uptime/health-check paging (no pilot host exists yet — do this once
   one does): point Healthchecks.io's or UptimeRobot's webhook integration at
   the same URL; both let you customize the POST body, so send
   `{"message": "..."}` — the relay also recognizes Sentry's native
   `event_alert` payload shape automatically, no template needed for Sentry.
6. Test: `curl -X POST "https://<api-host>/api/v1/ops/alert/?token=<OPS_ALERT_TOKEN>" -H 'Content-Type: application/json' -d '{"message":"ops alert test"}'`
   — confirm the message lands in the Telegram group.

The relay never 500s and never blocks the caller on a Telegram failure
(`core/services/telegram.py::send_ops_alert` is best-effort) so a broken
Telegram config can't itself take down alert delivery visibility — check
`OPS_TELEGRAM_CHAT_ID`/`TELEGRAM_BOT_TOKEN` are set if pages stop arriving.

## OG1-H4 — Test event pages a person

```
python manage.py sentry_test_event
```

Confirm: event in Sentry **and** the on-call person received the page (via
the Telegram relay above, or whatever OG1-H3b routing you chose).
Paste the event id into `docs/ops/HYPERCARE.md` day-0 and
`docs/pilot/ENV_CHECKLIST.md` row 18 / `docs/pilot/GO_NO_GO.md`.

## OG1-H5 — Metrics scrape

```
curl -fsS -H "Authorization: Bearer $METRICS_TOKEN" https://<api>/api/v1/metrics/
```

Expect 200 and series `bizboard_http_5xx_total`, `bizboard_pdf_queue_depth`,
`bizboard_circuit_open`, `bizboard_health_db`.

Local staging: set `METRICS_TOKEN` in `.env.staging` (see `.env.staging.example`).

## Apply `insights.0008`

Compose staging already runs `migrate --noinput` (`docker-compose.staging.yml`).
That applies `ShopFloorEvent` envelope columns. Confirm with:

```
python manage.py observability_gate_check
```

Expect `envelope_columns_missing=none` and `company_hash_column=False`.

## Check from the API box

```
python manage.py observability_gate_check
```
