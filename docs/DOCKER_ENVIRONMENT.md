# Docker environments (DEV / STAGING / production)

BizBoard can run three isolated Compose projects. **DEV is the stack already
running on this machine** (`http://127.0.0.1`). **STAGING is a second local
stack** (`http://127.0.0.1:8081`). **Production** is a third path
(`docker-compose.prod.yml`) and is not this laptop.

Do not copy DEV data into STAGING. Do not put production secrets in either
local env file.

Full ops for a deployed pilot/prod host: [`pilot/RUNBOOKS.md`](pilot/RUNBOOKS.md).

## Architecture

```text
docker-compose.yml                 shared service graph
docker-compose.dev.yml             pins project `bizboard` + existing volumes
docker-compose.staging.yml         project `bizboard-staging` + new volumes
docker-compose.prod.yml            digest-pinned production overlay (unchanged)
```

| | DEV | STAGING |
|---|---|---|
| Compose project | `bizboard` | `bizboard-staging` |
| URL | http://127.0.0.1 | http://127.0.0.1:8081 |
| Env file | `.env` (or `.env.dev`) | `.env.staging` |
| `DJANGO_ENV` | `development` | `staging` |
| Postgres volume | `bizboard_postgres_data` | `bizboard_staging_postgres` |
| Redis volume | `bizboard_redis_data` | `bizboard_staging_redis` |
| Media / static | `bizboard_media_data` / `bizboard_static_data` | `bizboard_staging_media` / `bizboard_staging_static` |
| Network | `bizboard_default` | `bizboard_staging_net` |
| Backups | `./backups/dev` (overlay) or `./backups` | `./backups/staging` |
| Seed | `seed_demo` / `seed_pilot_fixtures` | `seed_staging` only |

`pip_cache` (`bizboard_pip_cache`) is a **build cache** and may be shared. It
holds no tenant data.

Workers and beat in each project use that project's `DATABASE_URL` /
`REDIS_URL` only. Celery beat stays **one replica per environment**.

## Commands

Helper (PowerShell): `.\scripts\compose-env.ps1 <dev|staging> <compose args>`
Helper (bash): `scripts/compose-env.sh <dev|staging> <compose args>`

### DEV (current local stack)

```sh
copy .env.example .env          # first time only
docker compose up -d            # still valid — project `bizboard`
# or
.\scripts\compose-env.ps1 dev up -d

docker compose --profile migrate run --rm migrate
docker compose exec api python manage.py seed_demo
```

Open **http://127.0.0.1** (or http://localhost). Demo login after `seed_demo`:
`demo@bizboard.local` / `DemoPass123!`.

### STAGING (new isolated stack)

```sh
copy .env.staging.example .env.staging
.\scripts\compose-env.ps1 staging --profile migrate run --rm migrate
.\scripts\compose-env.ps1 staging up -d
.\scripts\compose-env.ps1 staging exec api python manage.py seed_staging
```

Open **http://127.0.0.1:8081**. Seeded users (password `PilotPass123!`):

| Company | Email |
|---|---|
| C1 Pilot Retail GST | `pilot-c1@bizboard.local` |
| C2 Pilot Inter-State | `pilot-c2@bizboard.local` |
| C3 Pilot Non-GST Shop | `pilot-c3@bizboard.local` |
| C4 Pilot Multi-Rate | `pilot-c4@bizboard.local` |
| C5 Pilot Multi-User | `pilot-c5@bizboard.local` |

Reset seed (staging DB only):

```sh
.\scripts\compose-env.ps1 staging exec api python manage.py seed_staging --reset
```

### Backup / restore

```sh
# DEV (overlay writes ./backups/dev)
.\scripts\compose-env.ps1 dev --profile backup run --rm backup
.\scripts\compose-env.ps1 dev --profile restore run --rm restore

# STAGING (writes ./backups/staging — cannot pick a DEV dump by “latest”)
.\scripts\compose-env.ps1 staging --profile backup run --rm backup
.\scripts\compose-env.ps1 staging --profile restore run --rm restore
```

Restore overwrites **that project's** database only. The weekly
`scripts/restore_drill.sh` still uses throwaway scratch containers, not these
volumes.

### Reset one environment (does not touch the other)

```sh
# STAGING only — deletes staging volumes
.\scripts\compose-env.ps1 staging down -v

# DEV only — deletes current local data. Do not run by accident.
.\scripts\compose-env.ps1 dev down -v
```

Stopping one stack (`stop` / `down` without `-v`) leaves the other running.

## Configuration

| File | Committed? | Purpose |
|---|---|---|
| `.env.example` / `.env.dev.example` | yes | DEV template |
| `.env` / `.env.dev` | **no** | local DEV secrets |
| `.env.staging.example` | yes | STAGING template (sandbox/test only) |
| `.env.staging` | **no** | local STAGING secrets |
| `.env.production.example` | yes | real production template |

Staging Django is production-like: `DEBUG=0`, no SQLite, SMTP host required,
sandbox payment provider banned, dedicated `OTP_PEPPER` / `GSP_FERNET_KEY`.
Loopback Compose staging (`ALLOWED_HOSTS` only localhost / 127.0.0.1) may
serve the SPA over HTTP; a **remote** staging hostname still requires HTTPS
and non-localhost CORS.

`seed_demo` and `seed_pilot_fixtures` still refuse `DJANGO_ENV=staging`.
Use `seed_staging` instead. Never run any seed in production.

## Safety rules

1. Never share Postgres, Redis, or media volumes between DEV and STAGING.
2. Never restore `./backups/dev` into STAGING (or the reverse).
3. Never copy production secrets into `.env.staging`.
4. Never point either local stack at a production database.
5. Do not `compose up --scale beat=N`.
6. Production deploy remains `docker-compose.yml` + `docker-compose.prod.yml`
   with digest-pinned `BIZBOARD_API_IMAGE`.

## Remaining shared resources

- Docker engine / disk on this machine
- `bizboard_pip_cache` (pip downloads only)
- Image tags `bizboard-api:latest` and `bizboard-web` (code, not tenant data)
- Read-only `nginx/default.conf` bind
- Container stdout logs (`docker compose logs`); there is no log volume
