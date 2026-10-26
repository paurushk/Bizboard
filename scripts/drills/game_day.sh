#!/usr/bin/env bash
# WP-6 (BB-099/149/051/093): technical game day on LOCAL staging.
#
# Each case breaks one thing, measures how long until the alert path notices, restores it, and
# measures recovery. Results are appended as a markdown table to the output file.
#
#   scripts/drills/game_day.sh --out docs/ops/DRILLS/<date>_LOCAL_GAME_DAY.md [--case db] [--dry-run]
#
# Alert paths on local staging (no Prometheus there; with docker-compose.monitoring.yml the
# worker/beat Prometheus rules can be checked as well, see docs/ops/DRILLS/README.md):
#   - GlitchTip uptime monitors, every 60 s: "Bizboard app" (/api/v1/health/) and "Saving and
#     loading data" (/api/v1/health/?ready=1: database, Redis, broker, beat heartbeat). A monitor
#     going down sends the tracker's down alert (email + ntfy, D-02).
#   - GlitchTip issues: a new error sends the "new error" alert.
#   - Bizboard's own ops pages (core.services.telegram.send_ops_alert): ntfy + Telegram.
#
# REAL ALERTS: every case except --dry-run sends real email / phone pushes to the on-call
# recipients. --dry-run prints the steps and changes nothing.
set -euo pipefail
cd "$(dirname "$0")/../.."

ENV_FILE=".env.staging"
COMPOSE="-f docker-compose.yml -f docker-compose.staging.yml -f docker-compose.glitchtip.yml"
OUT=""; ONLY="all"; DRY=0; PROM=0
BASE="http://127.0.0.1:${APP_PORT:-8081}"
DETECT_TIMEOUT=420   # monitors poll every 60 s; allow several intervals
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift ;;
    --case) ONLY="$2"; shift ;;
    --env-file) ENV_FILE="$2"; shift ;;
    --compose) COMPOSE="$2"; shift ;;
    --dry-run) DRY=1 ;;
    --prometheus) PROM=1 ;;  # docker-compose.monitoring.yml is running: also wait for the Prometheus alert
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
[[ -n "$OUT" ]] || { echo "--out is required" >&2; exit 2; }
DC="docker compose --env-file $ENV_FILE $COMPOSE"
mkdir -p "$(dirname "$OUT")"

say() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
ready() { curl -s -o /dev/null -w '%{http_code}' "$BASE/api/v1/health/?ready=1" || echo 000; }
pyshell() { $DC exec -T api python manage.py shell -c "$1" 2>/dev/null | grep -v -e '^Sentry' -e '^Waiting' -e 'Ctrl-C' -e 'objects imported' | tail -n 1; }

# "up" / "down" / "?" for a GlitchTip monitor, read with the app's read-only tracker token.
monitor() {
  pyshell "
from core.error_tracker import _get
try:
    m = {x['name']: x for x in _get('monitors/').json()}['$1']
    print('up' if m.get('isUp') else 'down')
except Exception:
    print('?')
"
}

wait_for() {  # wait_for <description> <command that prints a value> <wanted value> -> seconds or "timeout"
  local start=$SECONDS got
  while (( SECONDS - start < DETECT_TIMEOUT )); do
    got="$(eval "$2" || true)"
    [[ "$got" == "$3" ]] && { echo $((SECONDS - start)); return 0; }
    sleep 10
  done
  echo "timeout"
}

READY_MON="Saving and loading data"

# "firing" when Prometheus reports the named alert firing (needs --prometheus and the overlay).
prom_alert() {
  docker compose --env-file "$ENV_FILE" $COMPOSE -f docker-compose.monitoring.yml exec -T prometheus     wget -qO- localhost:9090/api/v1/alerts 2>/dev/null   | python -c "import json,sys; d=json.load(sys.stdin); print('firing' if any(a['labels'].get('alertname')=='$1' and a['state']=='firing' for a in d['data']['alerts']) else 'no')" 2>/dev/null || echo no
}
row() { printf '| %s | %s | %s | %s | %s | %s |\n' "$1" "$2" "$3" "$4" "$5" "$6" >> "$OUT"; }
if [[ ! -s "$OUT" ]]; then
  {
    echo "| Case | Injected | Alert path | Detected after | Recovered after | Notes |"
    echo "|---|---|---|---|---|---|"
  } >> "$OUT"
fi

run_case() { [[ "$ONLY" == "all" || "$ONLY" == "$1" ]]; }

case_stop_service() {  # case_stop_service <case> <service> <note>
  local name=$1 svc=$2 note=$3
  say "$name: stop $svc"
  if (( DRY )); then echo "  would: $DC stop $svc; wait for '$READY_MON' down; $DC start $svc; wait for up"; return; fi
  [[ "$(ready)" == 200 ]] || { row "$name" "-" "-" "-" "-" "skipped: not healthy before the case"; return; }
  $DC stop "$svc" >/dev/null 2>&1
  local first; first="$(wait_for "ready 503" ready 503)"
  local det; det="$(wait_for "monitor down" "monitor '$READY_MON'" down)"
  $DC start "$svc" >/dev/null 2>&1
  local rec; rec="$(wait_for "ready 200" ready 200)"
  local mon_up; mon_up="$(wait_for "monitor up" "monitor '$READY_MON'" up)"
  row "$name" "stop \`$svc\`" "uptime monitor \"$READY_MON\" -> down alert" \
      "probe 503 after ${first}s; monitor down after ${det}s" "probe 200 after ${rec}s; monitor up after ${mon_up}s" "$note"
}

case_heartbeat() {  # case_heartbeat <case> <service> <note> [prometheus alert]
  local name=$1 svc=$2 note=$3 rule=${4:-}
  say "$name: stop $svc and back-date the beat heartbeat by 700 s (the probe allows 600 s)"
  if (( DRY )); then echo "  would: $DC stop $svc; back-date heartbeat; wait for monitor down; start; wait for up"; return; fi
  [[ "$(ready)" == 200 ]] || { row "$name" "-" "-" "-" "-" "skipped: not healthy before the case"; return; }
  $DC stop "$svc" >/dev/null 2>&1
  pyshell "import time; from django.core.cache import cache; from core.tasks import BEAT_HEARTBEAT_KEY; cache.set(BEAT_HEARTBEAT_KEY, time.time() - 700, timeout=900); print('ok')" >/dev/null
  local first; first="$(wait_for "ready 503" ready 503)"
  local det; det="$(wait_for "monitor down" "monitor '$READY_MON'" down)"
  local prom="not checked (no --prometheus)"
  if (( PROM )) && [[ -n "$rule" ]]; then
    local old=$DETECT_TIMEOUT; DETECT_TIMEOUT=1080  # rules use for: 5m / 10m, scrape 30 s
    prom="$rule firing after $(wait_for "prometheus" "prom_alert $rule" firing)s"
    DETECT_TIMEOUT=$old
  fi
  $DC start "$svc" >/dev/null 2>&1
  local rec; rec="$(wait_for "ready 200" ready 200)"
  local mon_up; mon_up="$(wait_for "monitor up" "monitor '$READY_MON'" up)"
  note="$note; Prometheus: $prom"
  row "$name" "stop \`$svc\` + heartbeat 700 s old" "uptime monitor \"$READY_MON\" (beat heartbeat) -> down alert" \
      "probe 503 after ${first}s; monitor down after ${det}s" "probe 200 after ${rec}s; monitor up after ${mon_up}s" "$note"
}

case_error() {
  say "error: send a uniquely marked error event (a repeat of an old message would join the old issue and not alert)"
  if (( DRY )); then echo "  would: capture 'GAME DAY drill <marker>' in the api, then wait for that issue in the tracker"; return; fi
  local marker="gameday$(date +%s)"
  pyshell "import sentry_sdk; sentry_sdk.capture_message('GAME DAY drill $marker (test, no action needed)', level='error'); sentry_sdk.flush(timeout=5); print('sent')" >/dev/null
  local det; det="$(wait_for "issue" "pyshell \"from core.error_tracker import fetch_issues; r = fetch_issues('$marker', 5); print('new' if r.issues else 'none')\"" new)"
  row "error" "unique error event (\`$marker\`)" "GlitchTip new issue -> new-error alert" "issue listed after ${det}s" "resolve the issue in the tracker" "a repeated message joins its old issue and does not alert again"
}

case_backup() {
  say "backup: a 27-hour-old dump must fail the backup-age check and page"
  if (( DRY )); then echo "  would: run scripts/check_backup_age.sh on a 27 h old dump, then send_ops_alert"; return; fi
  local tmp; tmp="$(mktemp -d)"
  : > "$tmp/bizboard-drill.age"
  touch -d "27 hours ago" "$tmp/bizboard-drill.age" 2>/dev/null || touch -t "$(date -d '27 hours ago' +%Y%m%d%H%M 2>/dev/null || date +%Y%m%d%H%M)" "$tmp/bizboard-drill.age"
  local code=0; BACKUP_DIR="$tmp" sh scripts/check_backup_age.sh >/dev/null 2>&1 || code=$?
  local sent; sent="$(pyshell "from core.services.telegram import send_ops_alert; print(send_ops_alert('GAME DAY drill: backup older than 26 h (test, no action needed)'))")"
  rm -rf "$tmp"
  local token; token="$(sed -n 's/^OPS_ALERT_TOKEN=//p' "$ENV_FILE" | tail -n 1 | tr -d '\r')"
  local relay="not configured (OPS_ALERT_TOKEN empty: cron's POST to /api/v1/ops/alert/ would get 401)"
  [[ -n "$token" ]] && relay="configured"
  row "backup" "newest dump 27 h old" "check_backup_age.sh exit 1 -> ops alert (ntfy/Telegram)" \
      "check exit ${code} (want 1); send_ops_alert -> ${sent:-?}" "-" "ops alert relay token: ${relay}"
}

case_rollback() {
  say "rollback: run the rollback overlay on locally tagged images, then roll forward"
  if (( DRY )); then echo "  would: tag bizboard-api/web as :drill-prev; up -d --no-build with docker-compose.rollback.yml; roll forward"; return; fi
  local api_img web_img
  api_img="$($DC images -q api | head -n 1)"; web_img="$($DC images -q web | head -n 1)"
  docker tag "$api_img" bizboard-api:drill-prev; docker tag "$web_img" bizboard-web:drill-prev
  local start=$SECONDS
  BIZBOARD_API_PREVIOUS_IMAGE=bizboard-api:drill-prev BIZBOARD_WEB_PREVIOUS_IMAGE=bizboard-web:drill-prev \
    docker compose --env-file "$ENV_FILE" $COMPOSE -f docker-compose.rollback.yml up -d --no-build --no-deps api worker beat web >/dev/null 2>&1
  local back; back="$(wait_for "ready 200" ready 200)"
  local running; running="$(docker inspect --format '{{.Config.Image}}' "$($DC ps -q api)")"
  $DC up -d --no-deps api worker beat web >/dev/null 2>&1
  local fwd; fwd="$(wait_for "ready 200" ready 200)"
  docker rmi bizboard-api:drill-prev bizboard-web:drill-prev >/dev/null 2>&1 || true
  row "rollback" "\`docker-compose.rollback.yml\` with previous-image tags, \`--no-build\`" "probe 200 on the old image" \
      "rolled back in ${back}s (api ran ${running})" "rolled forward in ${fwd}s" "same image tagged as previous: proves the mechanism, not a real version change"
}

run_case db && case_stop_service db db "Postgres down"
run_case redis && case_stop_service redis redis "Redis down (cache, broker, heartbeat)"
run_case beat && case_heartbeat beat beat "real detection: up to 600 s + one monitor interval without the back-date" BizBoardBeatSilent
run_case worker && case_heartbeat worker worker "the worker runs the heartbeat task, so a dead worker shows the same way" BizBoardWorkerDown
run_case error && case_error
run_case backup && case_backup
run_case rollback && case_rollback
say "done: $OUT"
