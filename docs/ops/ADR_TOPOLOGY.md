# Topology ADR (2.2)

**Status:** Draft — Human picks the host.  
**Context:** `docker-compose.yml` + `docker-compose.prod.yml` (digest images, one-shot migrate profile, ClamAV, loopback HTTP behind a TLS edge).

## Decision required

| Option | When | Residual |
|---|---|---|
| A — Compose on a single VM | Fastest pilot | Single-AZ; Human accepts R002/R006 |
| B — Managed Postgres + Redis + VM for api/worker/web | Prefer for paid beta | App still one AZ unless Human funds HA |
| C — Full k8s | Out of freeze | Do not start in an LLM session |

**Default recommendation for freeze:** B. PgBouncer is built as an opt-in overlay (`docker-compose.pgbouncer.yml`, session mode, `CONN_MAX_AGE=0` enforced at boot); start without it and enable it only when connections become the limit (`docs/ops/POSTGRES.md`, WP-5 2026-10-25). Do not enable prod RLS.

## Already decided in code

- Postgres-only when `DJANGO_ENV` is production/staging (`ADR-A03`).
- Images by digest in prod overlay (`BIZBOARD_API_IMAGE`).
- Nginx/Caddy/cloud LB terminates TLS; Django speaks HTTP internally.
