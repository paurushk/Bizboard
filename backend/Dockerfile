# R5-010/M1-030: pin the Debian release (bookworm) AND the digest for
# reproducible base images — Dependabot's docker ecosystem (.github/dependabot.yml)
# is configured to bump this digest as python:3.12-slim-bookworm moves.
FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

# BB-000521: uploaded media (PDF/images) are stored as-is — no antivirus/clamav scan
# in this image. For production, run a separate AV pipeline or optional clamav profile.

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/app/.local/bin:${PATH}"

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY requirements.txt constraints.txt ./
# BB-000345: install with constraints for reproducible images.
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt

COPY . .
RUN mkdir -p /app/media \
    && sed -i 's/\r$//' /app/docker-entrypoint.sh /app/docker-entrypoint-test.sh \
    && chmod +x /app/docker-entrypoint.sh /app/docker-entrypoint-test.sh \
    && chown -R app:app /app

# Start as root so the entrypoint can chown the mounted media volume; the
# entrypoint immediately drops to the unprivileged `app` user via setpriv
# before exec-ing this CMD (R5-007 — gunicorn never runs as root).
USER root

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# R5-008: worker count / timeout are env-tunable per instance.
# --timeout default 120 matches nginx proxy_read_timeout and the web import
# client (IMPORT_TIMEOUT_MS); gunicorn's implicit 30s default kills ordinary
# catalog commits before those layers apply.
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-2} --timeout ${GUNICORN_TIMEOUT:-120}"]
