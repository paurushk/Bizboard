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
if [ "$(id -u)" = "0" ]; then
  chown -R app:app /app/media /app/staticfiles
  exec setpriv --reuid=app --regid=app --clear-groups -- "$@"
fi
exec "$@"
