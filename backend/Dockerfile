FROM python:3.12-slim

# BB-000521: uploaded media (PDF/images) are stored as-is — no antivirus/clamav scan
# in this image. For production, run a separate AV pipeline or optional clamav profile.

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY requirements.txt constraints.txt ./
# BB-000345: install with constraints for reproducible images.
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt

COPY . .
RUN mkdir -p /app/media \
    && sed -i 's/\r$//' /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R app:app /app

# Start as root so the entrypoint can chown the mounted media volume, then drop to app.
USER root

EXPOSE 8000

# BB-000358: liveness only (no topology leak). Compose uses ?ready=1 separately.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/')"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# --timeout 120 matches nginx proxy_read_timeout and the web import client
# (IMPORT_TIMEOUT_MS). Gunicorn's implicit 30s default kills ordinary catalog
# commits before those layers apply. Batching in ImportService.commit is the
# real scalability fix; this flag is the stopgap so small-to-medium files
# are not 502'd.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
