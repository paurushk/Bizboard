#!/bin/sh
# M1-033: entrypoint for the docker-compose `test` profile. This service
# overrides the image's default entrypoint (to `pip install
# requirements-dev.txt` before running pytest) — the original override ran
# that install and the whole test command as root, since it bypassed
# docker-entrypoint.sh's privilege drop entirely. This mirrors the same
# chown-then-drop pattern for the pip-cache volume and the `app` user, so
# nothing in the test container ever executes as root.
set -e
if [ -n "$PIP_CACHE_DIR" ]; then
  mkdir -p "$PIP_CACHE_DIR"
fi
if [ "$(id -u)" = "0" ]; then
  if [ -n "$PIP_CACHE_DIR" ]; then
    chown -R app:app "$PIP_CACHE_DIR"
  fi
  export HOME=/home/app
  exec setpriv --reuid=app --regid=app --clear-groups \
    sh -c 'pip install --user --quiet -c constraints.txt -r requirements-dev.txt && exec "$@"' -- "$@"
fi
pip install --user --quiet -c constraints.txt -r requirements-dev.txt
exec "$@"
