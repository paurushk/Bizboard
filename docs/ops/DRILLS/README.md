# Drills (WP-6)

Each technical game day writes one file here, `<date>_<where>_GAME_DAY.md`, from
`scripts/drills/game_day.sh`. Tabletop sessions use the run pack in
`docs/ops/TABLETOP_EXERCISES.md` and add their record to `docs/ops/DR_CADENCE.md`.

## Running the game day

```bash
# local staging, everything (real alerts go to the on-call email and phone)
docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml \
  -f docker-compose.monitoring.yml up -d prometheus alertmanager
scripts/drills/game_day.sh --out docs/ops/DRILLS/$(date +%F)_LOCAL_GAME_DAY.md --prometheus
# one case, or a dry run
scripts/drills/game_day.sh --out /tmp/x.md --case db --dry-run
```

| Case | Breaks | Alert path checked |
|---|---|---|
| db | stops Postgres | uptime monitor "Saving and loading data" (`?ready=1`) |
| redis | stops Redis | same monitor (cache, broker, heartbeat) |
| beat | stops beat; heartbeat back-dated past the 600 s allowance | same monitor; with `--prometheus` also `BizBoardBeatSilent` |
| worker | stops the worker (it runs the heartbeat task) | same monitor; with `--prometheus` also `BizBoardWorkerDown` |
| error | `manage.py sentry_test_event` | GlitchTip issue and its new-error alert |
| backup | a 27-hour-old dump | `check_backup_age.sh` exits 1; `send_ops_alert` pages |
| rollback | `docker-compose.rollback.yml` on locally tagged images | app healthy on the "previous" image, then rolled forward |

On a host, run it the same way in a quiet hour after telling the on-call person. Prometheus there
should be the managed service or the same overlay. The failover half of DR (BB-099) is
`docs/ops/DB_FAILOVER.md` on hosted Postgres.
