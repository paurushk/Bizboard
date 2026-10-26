#!/bin/sh
# Ensure the media volume is writable by the non-root app user.
# Named Docker volumes are often created as root:root, which blocks FileAsset uploads.
set -e
mkdir -p /app/media
# Django admin's own CSS/JS live in STATIC_ROOT (/app/staticfiles) — gunicorn
# doesn't serve static files, so nginx serves this volume directly (see
# nginx/default.conf's /static/ location). collectstatic is idempotent and
# cheap; running it on every container start (not just `migrate`) means a
# static-asset change never needs a manual step to take effect.
python manage.py collectstatic --noinput
# Prometheus multiprocess files (core/ops_metrics.py). Start empty, so a previous run's processes are
# not summed into this one, and writable by the app user: gunicorn workers run as `app` below, and a
# root-owned directory made every metric write fail and /api/v1/metrics/ answer 500 (WP-6 game day).
if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then
  mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
  rm -f "$PROMETHEUS_MULTIPROC_DIR"/*.db
fi
if [ "$(id -u)" = "0" ]; then
  chown -R app:app /app/media /app/staticfiles
  if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then chown -R app:app "$PROMETHEUS_MULTIPROC_DIR"; fi
  # setpriv drops uid/gid but keeps HOME=/root; gunicorn 26 creates its control socket under
  # $HOME/.gunicorn and logs "Permission denied: /root/.gunicorn" every start without this.
  export HOME=/home/app
  exec setpriv --reuid=app --regid=app --clear-groups -- "$@"
fi
exec "$@"
