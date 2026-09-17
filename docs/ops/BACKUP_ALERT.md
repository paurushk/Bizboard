# Backup-fail alert (7.6)

If the daily dump job exits non-zero, page on-call (`docs/ops/ALERTS.md`). Encrypt at rest on the off-host bucket (KMS — Human).

Minimum:

- Cron/host job: `docker compose --profile backup run --rm backup`
- Copy `./backups/bizboard-*.sql.gz` off-host
- Alert if no new object in 26h
- Monthly `scripts/restore_drill.sh` dated in `GO_NO_GO.md`

The volume `postgres_data` is not a backup.
