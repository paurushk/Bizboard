#!/bin/sh
# Ensure the media volume is writable by the non-root app user.
# Named Docker volumes are often created as root:root, which blocks FileAsset uploads.
set -e
mkdir -p /app/media
if [ "$(id -u)" = "0" ]; then
  chown -R app:app /app/media
  exec setpriv --reuid=app --regid=app --clear-groups -- "$@"
fi
exec "$@"
