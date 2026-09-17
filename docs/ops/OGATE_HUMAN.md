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

## OG1-H4 — Test event pages a person

```
python manage.py sentry_test_event
```

Confirm: event in Sentry **and** the on-call person received the page.
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
