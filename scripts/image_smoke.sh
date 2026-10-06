#!/bin/sh
# PRE-2 / F-PORT-01: smoke the BUILT API image, not the venv CI tests on.
#
#   scripts/image_smoke.sh <api-image> <database-url> [expected-python-minor]
#
# e.g. scripts/image_smoke.sh bizboard-api:ci postgresql://u:p@127.0.0.1:5432/smoke 3.13
#
# Proves, inside the image that would ship:
#   1. the interpreter is the one CI tests (when expected-python-minor is given)
#   2. `manage.py check --deploy` passes with production-style settings
#   3. there is no model/migration drift (`makemigrations --check`)
#   4. every migration applies to an empty Postgres
#   5. gunicorn boots and /api/v1/health/ answers 200
# SMOKE_REDIS_URL defaults to redis://127.0.0.1:6379/0 (production settings require a REDIS_URL;
# CI provides a redis service, `check`/`migrate` do not actually connect to it).
# SMOKE_DOCKER_ARGS lets a caller add flags (e.g. --network, --add-host on Docker Desktop).
set -eu

IMAGE="${1:?usage: image_smoke.sh <api-image> <database-url> [python-minor]}"
DBURL="${2:?database url required}"
EXPECT_PY="${3:-}"
NAME="bb-image-smoke-$$"
HOST_ARGS="${SMOKE_DOCKER_ARGS:---network host}"
PORT="${SMOKE_PORT:-18000}"
HEALTH_RETRIES="${SMOKE_HEALTH_RETRIES:-30}"
HEALTH_SLEEP="${SMOKE_HEALTH_SLEEP:-2}"

# Production-style settings with throwaway secrets (nothing here is a real credential).
ENVS="-e DJANGO_ENV=production -e DJANGO_DEBUG=0
 -e DJANGO_SECRET_KEY=smoke-only-$(date +%s)-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
 -e DJANGO_ALLOWED_HOSTS=smoke.example.test,localhost,127.0.0.1
 -e CORS_ALLOWED_ORIGINS=https://smoke.example.test
 -e CSRF_TRUSTED_ORIGINS=https://smoke.example.test
 -e OTP_PEPPER=smoke-only-pepper-bbbbbbbbbbbbbbbbbbbbbbbbbbbb
 -e USE_TLS=1 -e DATABASE_URL=${DBURL}
 -e REDIS_URL=${SMOKE_REDIS_URL:-redis://127.0.0.1:6379/0}
 -e EMAIL_HOST=smtp.smoke.example.test -e DEFAULT_FROM_EMAIL=noreply@smoke.example.test
 -e GSP_FERNET_KEY=MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

# shellcheck disable=SC2086
run() { docker run --rm $HOST_ARGS $ENVS "$IMAGE" "$@"; }

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== 1. interpreter"
# The entrypoint runs collectstatic first and prints to stdout; take the last line only.
PYV="$(run python -c 'import sys; print("%d.%d" % sys.version_info[:2])' | tail -n 1)"
echo "image python: ${PYV}"
if [ -n "$EXPECT_PY" ] && [ "$PYV" != "$EXPECT_PY" ]; then
    echo "FAIL: image runs Python ${PYV} but CI tests ${EXPECT_PY}" >&2
    exit 1
fi

echo "== 2. check --deploy"
run python manage.py check --deploy --fail-level ERROR

echo "== 3. migration drift"
run python manage.py makemigrations --check --dry-run

echo "== 4. migrate on an empty database"
run python manage.py migrate --noinput

echo "== 5. gunicorn boot + health"
# shellcheck disable=SC2086
docker run -d --name "$NAME" $HOST_ARGS $ENVS -e GUNICORN_WORKERS=1 \
    -e "GUNICORN_CMD_ARGS=--bind 0.0.0.0:${PORT}" "$IMAGE" \
    sh -c "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 1 --timeout 60" >/dev/null
i=0
until [ "$(docker exec "$NAME" python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:${PORT}/api/v1/health/',timeout=3).status)" 2>/dev/null || true)" = "200" ]; do
    i=$((i + 1))
    if [ "$i" -gt "$HEALTH_RETRIES" ]; then
        echo "FAIL: /api/v1/health/ did not return 200 after ${HEALTH_RETRIES} tries" >&2
        docker logs "$NAME" 2>&1 | tail -30 >&2
        exit 1
    fi
    sleep "$HEALTH_SLEEP"
done
echo "health 200"
echo "IMAGE SMOKE OK (python ${PYV})"
