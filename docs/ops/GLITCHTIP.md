# Error tracking with self-hosted GlitchTip (free Sentry alternative)

GlitchTip is an open-source error tracker and uptime monitor that accepts the Sentry protocol.
Bizboard ships it as part of its own container stack and reads it from Django admin. Sentry (paid or
free plan) still works: only the DSNs and `ERROR_TRACKER_*` values change.

## What is in Bizboard

| Piece | Where | What it does |
|---|---|---|
| Container | `docker-compose.glitchtip.yml` (profile `errors`) | GlitchTip 6.2.6 + its own Postgres + a setup step (`glitchtip-init`) |
| Setup step | `deploy/glitchtip/bootstrap.py` | Idempotent: admin, organisation `bizboard`, team `ops`, projects `bizboard-api` / `bizboard-web` with fixed keys, read-only ops token, alert rules, uptime monitors; prints the DSNs |
| API + worker errors | `config/settings.py` (`SENTRY_DSN`) | Sentry SDK → `bizboard-api`, tagged `request_id`, `company_hash`, release |
| Browser errors | `web/src/main.tsx` → `POST /api/v1/client-errors/` (`core/error_tunnel.py`) | Same-origin relay → `bizboard-web`; forwards only to `SENTRY_BROWSER_DSN` |
| Staff errors page | `/admin/ops/errors/` (superusers) | Open errors, search by Support ID or text, wiring checklist |
| Support tickets | Ticket page in admin → "Errors for this Support ID" | Links to the errors page and the tracker, filtered by that request id |
| Watcher | `core.tasks.check_error_tracker_task`, every 5 min | Telegram page (`OPS_TELEGRAM_CHAT_ID`) after two misses in a row, and once when it is back |
| Gate check | `manage.py observability_gate_check` | Shows `browser_relay_configured` and `error_tracker_readable` |

The Support ID people quote is the request id. The API and the SPA tag every event with it, so one
ID finds the matching server error, browser error and log lines (`docs/ops/OGATE_GREP_WALK.md`).

## Two ways to run it

**A. Inside the Bizboard stack** (dev, local staging, pilot host). The API reaches GlitchTip on the
stack network at `http://glitchtip:8000`, so ingestion is never public. Browsers never talk to it.
`scripts/compose-env.ps1` and `deploy-staging.yml` already add the overlay; it stays off until the
env file sets `COMPOSE_PROFILES=errors`.

**B. On its own small VM** (recommended for production: when the app host or its database is down,
which is when you need errors and pages most, the tracker must still be up):

```bash
copy .env.glitchtip.example .env.glitchtip
docker compose -p glitchtip --env-file .env.glitchtip -f docker-compose.glitchtip.yml --profile errors up -d
```

In mode B, set `GLITCHTIP_DSN_BASE_URL` to the tracker's public URL, `GLITCHTIP_MONITOR_BASE_URL` to
the app's public URL, and `GLITCHTIP_ALLOW_PRIVATE_IPS=false`. The app host needs outbound HTTPS to it.

## 1. Fill the env file

Mode A: uncomment the GlitchTip block in `.env.staging` / the host `.env`. Mode B: `.env.glitchtip`.
Generate values:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
python -c "import uuid; print(uuid.uuid4().hex)"
python -c "import secrets; print(secrets.token_hex(32))"
```

The first gives `GLITCHTIP_SECRET_KEY`, `GLITCHTIP_DB_PASSWORD` and `GLITCHTIP_ADMIN_PASSWORD`. Run the
second twice for `GLITCHTIP_API_KEY` and `GLITCHTIP_WEB_KEY`. The third gives `ERROR_TRACKER_TOKEN`.

Because the project keys are fixed, the app's DSNs are known before the first start (mode A):

```
SENTRY_DSN=http://<GLITCHTIP_API_KEY>@glitchtip:8000/1
SENTRY_BROWSER_DSN=http://<GLITCHTIP_WEB_KEY>@glitchtip:8000/2
VITE_SENTRY_DSN=<same as SENTRY_BROWSER_DSN>     # web image build arg; cd.yml reads the repo variable
SENTRY_RELEASE=<git SHA being deployed>
ERROR_TRACKER_API_URL=http://glitchtip:8000
ERROR_TRACKER_UI_URL=<the URL you open the UI on>
ERROR_TRACKER_TOKEN=<same token>
```

Mode A also needs `api` in `DJANGO_ALLOWED_HOSTS` (for example `your.domain.com,api`): the uptime
monitors call `http://api:8000`, and Django answers 400 to hosts it does not list, which would read as
"API down". `glitchtip-init` prints a `WARNING` when the monitored host is missing.

`glitchtip-init` prints the exact DSNs every run and says `MISMATCH` if the env file differs (for
example when the projects were created by hand and got other ids).

Rotating: change `ERROR_TRACKER_TOKEN` (or `GLITCHTIP_ALERT_NTFY_URL`) and deploy; the setup step
creates the new one and removes the old, so the old token stops working at once. The admin password
is only set when the admin is first created; change it later in the UI.

## 2. Start it

```bash
.\scripts\compose-env.ps1 staging up -d
.\scripts\compose-env.ps1 staging logs glitchtip-init
```

On a host, `deploy-staging.yml` starts it and re-runs the setup step on every deploy when the profile
is on. That runs after the deploy is recorded for rollback, so a failing setup step fails the workflow
without leaving rollback pointing at the wrong images. Rebuild the web image after setting `VITE_SENTRY_DSN`: Vite bakes it into the bundle.

## 3. Reach the UI

It listens on `127.0.0.1:${GLITCHTIP_PORT}` (8095 dev, 8096 local staging) only. On a host, use an SSH
tunnel (`ssh -L 8095:127.0.0.1:8095 <host>`) or put it behind the edge with access control (Cloudflare
Access in front of `errors.<domain>`). Sign in with `GLITCHTIP_ADMIN_EMAIL`. Sign-up and organisation
creation are off; invite people from the UI.

## 4. Alerts that reach a person

The setup step creates, on both projects, "new error" alerts and, on `bizboard-api`, a "down" alert
for the uptime monitors. Recipients:

- **Email** to every member of team `ops`: the admin plus `GLITCHTIP_ALERT_EMAILS` (added as members
  with no password; they sign in after a password reset). Needs `GLITCHTIP_EMAIL_URL` (SMTP).
- **ntfy** when `GLITCHTIP_ALERT_NTFY_URL` is set: free push to the on-call phone. Install the ntfy
  app, subscribe to a long random topic (`https://ntfy.sh/<random>`), put that URL in the env file.

The Telegram relay (`/api/v1/ops/alert/`) takes its token only from a header in staging and
production (BUG-SEC-021) and GlitchTip webhooks cannot set headers, so GlitchTip pages through email
or ntfy. Bizboard's own ops pages (tracker down, backup failed, audit seal missed, break-glass) go to
Telegram (`OPS_TELEGRAM_CHAT_ID`) and, when `OPS_NTFY_URL` is set, to the same ntfy topic.

## 5. Uptime probe

Monitors "API live" (`/api/v1/health/`) and "API ready" (`/api/v1/health/?ready=1`), every 60 s,
expecting 200, against `GLITCHTIP_MONITOR_BASE_URL` (default `http://api:8000` inside the stack).
Inside the stack this watches the app process, not the public edge; for an outside view (DNS, TLS,
edge) run mode B or add one free external check on the public URL.

## 5b. Public status page (BB-128)

`glitchtip-init` creates a public status page "Bizboard" listing both monitors. The app's nginx
publishes it at `https://<app domain>/status/` (`nginx/default.conf`, `location = /status/`): GET only,
GlitchTip's cookies and security headers replaced with a strict policy (no script, no forms, no
framing), so the tracker UI stays private. Mode B: point the same location at the tracker VM, or
expose only `/status-pages/` on the tracker's edge. With the profile off it answers 503.

## 6. Prove it (execution-record rows in `HOSTED_STAGING.md`)

| Check | How | Pass when |
|---|---|---|
| Setup step | `logs glitchtip-init` | "ready", no `MISMATCH` |
| Backend event | `exec api python manage.py sentry_test_event` | issue in `bizboard-api`; alert email / ntfy push received |
| Browser event | in the app's console: `setTimeout(() => { throw new Error('browser check') })` | `POST /api/v1/client-errors/` → 200; issue in `bizboard-web` |
| Relay refuses others | `curl -X POST https://<app>/api/v1/client-errors/ --data-binary $'{"dsn":"https://k@example.com/1"}\n'` | 400 |
| Staff page | `/admin/ops/errors/`, then search the Support ID from a ticket | the matching errors listed |
| Uptime | stop `api` for 3 minutes | down alert, then recovery |
| Watcher | stop `glitchtip` for 15 minutes | one Telegram page, then one "answering again" |
| Gate | `exec api python manage.py observability_gate_check` | `browser_relay_configured=True`, `error_tracker_readable=True` |

Then fill the project URL in `docs/ops/OGATE_HUMAN.md` (OG1-H1).

## 7. Run it

- **Upgrade:** change the pinned tag in `docker-compose.glitchtip.yml` (all three services), read
  GlitchTip's release notes, deploy. It migrates on start.
- **Backups:** nightly, next to the app's dump (same cron, same encryption, off-site copy and
  retention as `scripts/backup.sh`, with `BACKUP_KIND=glitchtip`):
  `docker compose ... run --rm glitchtip-backup`. Files are `glitchtip-<stamp>.sql.gz[.gpg|.age]` in
  `GLITCHTIP_BACKUP_DIR` (default `./backups/glitchtip`), marker `LAST_SUCCESS_glitchtip`. It holds
  error history, not customer data.
- **Retention:** `GLITCHTIP_RETENTION_DAYS` (default 90).
- **Volume:** Postgres-only mode (no Valkey) is fine at pilot volume. If ingestion lags, add a Valkey
  service and set `VALKEY_URL`.
- **Data:** error events carry request paths, the company hash and stack traces, not customer
  names (`send_default_pii=False`, IP scrubbing on). Self-hosted in India, it is not a subprocessor.

## Evidence

### 2026-10-23, first pass (standalone)

| Check | Result |
|---|---|
| `manage.py sentry_test_event` | issue in `bizboard-api` |
| Scripted envelope through `/api/v1/client-errors/` | 200; issue in `bizboard-web` |
| Same envelope with another DSN host | 400, nothing forwarded |
| Uncaught error thrown in the running SPA | SDK posted to `/api/v1/client-errors/` → 200; issue in `bizboard-web` |

Found: GlitchTip authenticates envelopes only by the `sentry_key` query parameter (403 otherwise), so
the relay always sends the configured key.

### 2026-10-23, integrated

GlitchTip from `docker-compose.glitchtip.yml` (standalone, `-p glitchtip --profile errors`) on the dev
laptop; the working-tree API on `runserver` against a scratch SQLite database, with every
`SENTRY_*` / `ERROR_TRACKER_*` setting on.

| Check | Result |
|---|---|
| `glitchtip-init`, first run | created admin, alert member, organisation, both projects with the env keys, ops token, 3 alert rules, 2 uptime monitors; printed DSNs |
| `glitchtip-init`, second run | no changes, same DSNs (idempotent) |
| Ops token | organisation and issues API → 200; without the token → 401 |
| Ingestion over the stack network | event POSTed to `http://glitchtip:8000` from a container on the network → 200, issue created |
| Tag search | `request_id:<id>` returns exactly the matching issue; another id returns none |
| `/admin/ops/errors/` | lists both open issues; Support ID search shows the one match; wiring table all "Yes" |
| Links from the page | the search link and each issue link open the right GlitchTip screens |
| `observability_gate_check` | `browser_relay_configured=True`, `error_tracker_readable=True (ok)` |
| Watcher, GlitchTip stopped then started | miss 1: no page; miss 2: paged once; miss 3: no second page; back: one "answering again"; then ok |
| Compose renders | stack + profile, prod + profile, standalone; no GlitchTip service without the profile; `COMPOSE_PROFILES=errors` from `--env-file` turns it on |

Found: GlitchTip 6 returns a dead `permalink` (the project slug where its UI expects the
organisation), so Bizboard builds issue links from `ERROR_TRACKER_UI_URL` and the issue id.

Review pass (same day), each checked live against the running GlitchTip:

| Check | Result |
|---|---|
| Alert email | "Error in bizboard-api: …" for each new issue and "API live is down" / "API ready is down", sent to the admin and the `GLITCHTIP_ALERT_EMAILS` member |
| Token rotation | new token 200, old token 401 straight after the setup step |
| ntfy topic change | old topic removed, new one added, email recipient kept |
| Monitored host not in `DJANGO_ALLOWED_HOSTS` | setup step prints the `WARNING`; a `.domain` entry that covers it does not |

### 2026-10-23, inside local staging (mode A)

Local staging rebuilt on the current code (migrations applied, app role re-applied) with
`COMPOSE_PROFILES=errors`; GlitchTip at `http://localhost:8096`, alerts to the founder's email and a
private ntfy topic.

| Check | Result |
|---|---|
| `glitchtip-init` | admin, organisation, projects, token, alerts, monitors on `http://api:8000`; no `MISMATCH`, no host warning |
| `sentry_test_event` from the api container | issue in `bizboard-api`; email notification sent; ntfy push received on the topic |
| Uncaught error in the rebuilt SPA (`127.0.0.1:8081`) | `POST /api/v1/client-errors/` → 200; issue in `bizboard-web`; push received |
| Real errors | 8 `DisallowedHost` issues for a public hostname routed to local staging that `DJANGO_ALLOWED_HOSTS` does not list (configuration, not a code fault) |
| `observability_gate_check` | `sentry_configured=True`, `browser_relay_configured=True`, `error_tracker_readable=True` |
| Uptime monitors | first **down**: GlitchTip 6 gates monitors on private addresses with `GLITCHTIP_UPTIME_ALLOW_PRIVATE_IPS` (the general flag does not apply); fixed in the compose file, then both up, with "back up" pushes |
| `run --rm glitchtip-backup` | `glitchtip-20261023T083203Z.sql.gz`, 163 tables, own marker; the app's `LAST_SUCCESS` untouched |
| Ops page via `OPS_NTFY_URL` | `send_ops_alert` → `sent`; push on the topic |

Not yet run (first pass): GlitchTip inside a running Bizboard stack (local staging then ran a 2026-10-20 image without
this code), alert email / ntfy delivery to a phone, the uptime monitors against a live API, and
anything on a hosted environment.
