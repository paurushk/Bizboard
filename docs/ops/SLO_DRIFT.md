# SLO drift review (C.2)

Monthly (Human meeting). Compare `docs/ops/SLO.md` draft numbers to:

- External `/health/` uptime
- PDF 409 duration (worker logs)
- Webhook 2xx ratio
- Backup job success

If error budget is >50% burned in 7 days: freeze feature work; incident. Do not raise the SLO to hide a burn.
