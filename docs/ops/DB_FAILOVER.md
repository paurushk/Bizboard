# DB reconnect / failover (7.4)

Django already sets `CONN_HEALTH_CHECKS=True` on Postgres and `CONN_MAX_AGE=600`. A failed connection is discarded before the next request.

On managed PG failover:

1. DNS/IP of `DATABASE_URL` must follow the new primary (vendor behaviour).
2. Bounce `api` `worker` `beat` if they hold dead sockets longer than health checks.
3. Behind PgBouncer (session pooling, see `docs/ops/POSTGRES.md`), keep `CONN_MAX_AGE=0`.
4. Measure RTO; Human signs G7/G13. Do not invent a second AZ in compose.
