#!/usr/bin/env bash
# WP-1: signed-in ZAP API scan of LOCAL staging, in batches by API area.
#
# Each batch signs in through the normal login form (zap/zap_login.py, a test login without
# two-step). The access cookie lasts JWT_ACCESS_MINUTES (15 by default): for the run, set
# JWT_ACCESS_MINUTES=180 in the LOCAL .env.staging and restart api, or the later requests of a
# batch go out signed out. Each batch's active scan is capped at BATCH_MINUTES (ZAP's scanner.*
# options); a watchdog stops the container if a batch overruns that by 10 minutes. One thread and
# 150 ms between requests keep it under nginx's per-IP limit (api_general 30 r/s): above it nginx
# answers 503, which ZAP reports as server errors and which fools its SQL-injection heuristic.
# The scan writes data (ZAP sends payloads to POST/PUT/PATCH): take a pg_dump first and restore it
# afterwards. DELETEs and destructive / external-call endpoints are never sent (zap/filter_openapi.py).
#
#   SCAN_EMAIL=... SCAN_PASSWORD=... scripts/security/run_local_api_scan.sh <out-dir> [first-batch]
#
# Needs: DJANGO_ALLOWED_HOSTS in .env.staging to include host.docker.internal for the run.
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT="${1:?usage: run_local_api_scan.sh <out-dir> [first-batch]}"
FIRST="${2:-1}"
mkdir -p "$OUT"
IMAGE="${ZAP_IMAGE:-ghcr.io/zaproxy/zaproxy:stable}"
BATCH_MINUTES="${BATCH_MINUTES:-20}"
BATCHES=(
  "sales"
  "purchases|suppliers"
  "inventory|products|masters|customers"
  "accounting|ledgers|banking|money"
  "reports|dashboard|search|insights|audit|audit-timeline|care-kpis|statutory-events"
  "company|feature-flags|whats-new|announcements|help-feedback|help-health|invariants|files"
  "crm|complaints|contracts|insurance|workshop|projects|jobwork|quality|plan|manufacturing|payroll|support|imports"
)
i=0
for areas in "${BATCHES[@]}"; do
  i=$((i + 1))
  (( i < FIRST )) && continue
  python scripts/security/zap/filter_openapi.py "$OUT/spec-$i.json" --only "$areas"
  ZAP_OPTS="$(python scripts/security/zap/zap_login.py)"
  echo "batch $i ($areas): scanning, up to $BATCH_MINUTES min"
  name="bb-zap-batch-$i"
  docker rm -f "$name" >/dev/null 2>&1 || true
  ( sleep $(( (BATCH_MINUTES + 10) * 60 )); docker stop "$name" >/dev/null 2>&1 ) &
  watchdog=$!
  MSYS_NO_PATHCONV=1 docker run --rm --name "$name" -v "$OUT:/zap/wrk:rw" "$IMAGE" zap-api-scan.py \
    -t "/zap/wrk/spec-$i.json" -f openapi -J "api-$i.json" -r "api-$i.html" -I \
    -z "$ZAP_OPTS -config scanner.maxScanDurationInMins=$BATCH_MINUTES -config scanner.maxRuleDurationInMins=3 -config scanner.threadPerHost=1 -config scanner.delayInMs=150" \
    | grep -E "FAIL-NEW|WARN-NEW|^FAIL|^WARN" || true
  kill "$watchdog" 2>/dev/null || true
  sleep 8  # login throttle
done
echo "done: $OUT/api-*.json"
