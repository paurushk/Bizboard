# Security group / edge templates (2.4)

Apply on the host. `scripts/edge_tls_smoke.sh` proves HTTPS+HSTS **after** Human terminates TLS.

## Ingress

| Port | Source | Dest | Why |
|---|---|---|---|
| 443/tcp | 0.0.0.0/0 | TLS terminator | User + webhooks |
| 80/tcp | 0.0.0.0/0 | Terminator only (redirect) | Optional |
| 22/tcp | operator IPs | VM | SSH; never 0.0.0.0/0 if avoidable |

## Must not be public

| Port | Bind |
|---|---|
| 5432 Postgres | private subnet / SG from api+worker only |
| 6379 Redis | same |
| 6432 PgBouncer if used | same |
| 8000 Django | loopback or docker network (`APP_BIND=127.0.0.1`) |
| 5555 Flower / admin extras | off |

Compose already binds nginx to `127.0.0.1:80` by default. Set `APP_BIND=0.0.0.0` only when a real TLS edge is in front.
