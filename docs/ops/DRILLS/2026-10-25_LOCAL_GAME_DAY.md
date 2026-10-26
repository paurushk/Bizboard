| Case | Injected | Alert path | Detected after | Recovered after | Notes |
|---|---|---|---|---|---|
| redis | stop `redis` | uptime monitor "Saving and loading data" -> down alert | probe 503 after 34s; monitor down after 47s | probe 200 after 16s; monitor up after 51s | Redis down (cache, broker, heartbeat) |
| beat | stop `beat` + heartbeat 700 s old | uptime monitor "Saving and loading data" (beat heartbeat) -> down alert | probe 503 after 12s; monitor down after 43s | probe 200 after 90s; monitor up after 38s | real detection: up to 600 s + one monitor interval without the back-date; Prometheus: BizBoardBeatSilent firing after 623s |
| worker | stop `worker` + heartbeat 700 s old | uptime monitor "Saving and loading data" (beat heartbeat) -> down alert | probe 503 after 0s; monitor down after 27s | probe 200 after 54s; monitor up after 24s | the worker runs the heartbeat task, so a dead worker shows the same way; Prometheus: BizBoardWorkerDown firing after 319s |
| backup | newest dump 27 h old | check_backup_age.sh exit 1 -> ops alert (ntfy/Telegram) | check exit 1 (want 1); send_ops_alert -> TelegramSendResult(mode='sent', raw=None) | - | ops alert relay token: configured |
| rollback | `docker-compose.rollback.yml` with previous-image tags, `--no-build` | probe 200 on the old image | rolled back in 142s (api ran bizboard-api:drill-prev) | rolled forward in 133s | same image tagged as previous: proves the mechanism, not a real version change |
| db | stop `db` | uptime monitor "Saving and loading data" -> down alert | probe 503 after 55s; monitor down after 20s | probe 200 after 2s; monitor up after 47s | Postgres down |
| error | unique error event (`gameday1792943263`) | GlitchTip new issue -> new-error alert | issue listed after 20s | resolve the issue in the tracker | a repeated message joins its old issue and does not alert again |

## 2026-10-25 local game day: what it found

Run on local staging with `scripts/drills/game_day.sh --prometheus` (Prometheus and Alertmanager
from `docker-compose.monitoring.yml`). Real alerts went to the on-call email and ntfy topic (D-02),
with the founder's approval. The `db` and `error` rows are from the re-run after the fixes below.

| # | Found | Fixed |
|---|---|---|
| 1 | **`/api/v1/metrics/` answered 500 for good.** gunicorn workers run as `app`, but the Prometheus multiprocess directory was root-owned. The first metric write failed after one counter had registered, and every later call failed with DuplicateTimeseries. Prometheus could not read the API at all; on a host the API-side alert rules would never have fired | `backend/docker-entrypoint.sh` creates and empties the directory and hands it to `app`; `core/ops_metrics._mp()` unregisters a half-built set and turns metrics off for that process instead of failing every call (`test_an_unwritable_metrics_dir_turns_metrics_off_without_poisoning_the_process`). After the fix both scrape targets are `up` |
| 2 | **With Postgres down, the health probe answered 500, not 503.** The RLS middleware bound the tenant (a database call) before the probe could answer. The uptime monitor still saw "down", but the probe should answer for itself | `/api/v1/health/` is exempt from the RLS middleware; it reads no tenant table (`test_health_probe_answers_even_when_binding_rls_would_fail`). Re-run: 503 while down, 200 two seconds after Postgres was back |
| 3 | The drill's error case counted issues capped at 100, and a repeated test message joins its old issue, which does **not** send a new-error alert | The drill now sends a uniquely marked error and finds that issue (20 s) |
| 4 | Ops alert relay token (`OPS_ALERT_TOKEN`) was empty on local staging, so cron's backup-age page and Alertmanager could not reach `/api/v1/ops/alert/` | Set locally for the drill. **On the host it must be set** (preflight lists it as MANUAL; `HOSTED_STAGING.md` §2) |
| 5 | A dead worker or scheduler is seen through the heartbeat, which allows 600 s, plus one monitor interval. Prometheus pages a dead worker in about 5 minutes and a silent scheduler in about 10 | No change: use the Prometheus rules on the host (managed service or this overlay) for the faster worker page |

Not covered here: database failover (needs hosted Postgres, `DB_FAILOVER.md`), and the tabletop
(founder, `TABLETOP_EXERCISES.md` run pack).
