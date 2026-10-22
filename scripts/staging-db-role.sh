#!/usr/bin/env bash
# STG-17: create/refresh the non-superuser app role used by the STAGING api/worker/beat.
# Thin wrapper: the logic lives in scripts/db-app-role.sh + scripts/sql/app_role.sql (SR0-06),
# shared with production. Run it after every `migrate` and every restore.
#
# Usage: scripts/staging-db-role.sh        (needs the staging `db` service running)
set -euo pipefail
cd "$(dirname "$0")/.."
exec scripts/db-app-role.sh .env.staging docker-compose.yml docker-compose.staging.yml
