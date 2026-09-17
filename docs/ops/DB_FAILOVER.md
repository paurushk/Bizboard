# DB reconnect / failover (7.4)

Django already sets `CONN_HEALTH_CHECKS=True` on Postgres and `CONN_MAX_AGE=600`. A failed connection is discarded before the next request.

On managed PG failover:

1. DNS/IP of `DATABASE_URL` must follow the new primary (vendor behaviour).
2. Bounce `api` `worker` `beat` if they hold dead sockets longer than health checks.
3. With PgBouncer transaction pooling, set `CONN_MAX_AGE=0` first (`docs/ops/POSTGRES.md`).
4. Measure RTO; Human signs G7/G13. Do not invent a second AZ in compose.
