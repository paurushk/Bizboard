#!/usr/bin/env bash
# Run docker compose against the DEV or STAGING overlay.
# Usage: scripts/compose-env.sh dev|staging <compose args...>
#   scripts/compose-env.sh staging --profile migrate run --rm migrate
#   scripts/compose-env.sh staging up -d
set -euo pipefail
cd "$(dirname "$0")/.."
env="${1:?usage: compose-env.sh dev|staging <compose args>}"
shift
case "$env" in
  dev)
    if [[ -f .env.dev ]]; then
      env_file=.env.dev
    else
      env_file=.env
    fi
    exec docker compose --env-file "$env_file" -f docker-compose.yml -f docker-compose.dev.yml "$@"
    ;;
  staging)
    if [[ ! -f .env.staging ]]; then
      echo "Missing .env.staging — copy .env.staging.example first." >&2
      exit 1
    fi
    exec docker compose --env-file .env.staging -f docker-compose.yml -f docker-compose.staging.yml "$@"
    ;;
  *)
    echo "usage: compose-env.sh dev|staging <compose args>" >&2
    exit 1
    ;;
esac
