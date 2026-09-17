"""Process-local + infra gauges for GET /metrics (O-Gate 1).

HTTP counters are per-process (gunicorn workers scrape independently).
Queue / health / DLQ gauges are read from Redis/DB with the same ~15s cache
as HealthView.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_REQUEST_COUNT = 0
_HTTP_5XX = 0
_DURATION_MS_SUM = 0
_DURATION_COUNT = 0
_CELERY_FAILURES = 0


def bump_request_count() -> None:
    global _REQUEST_COUNT
    with _lock:
        _REQUEST_COUNT += 1


def get_request_count() -> int:
    return _REQUEST_COUNT


def record_http_result(*, status: int, duration_ms: int) -> None:
    global _HTTP_5XX, _DURATION_MS_SUM, _DURATION_COUNT
    with _lock:
        _DURATION_MS_SUM += max(0, int(duration_ms))
        _DURATION_COUNT += 1
        if int(status) >= 500:
            _HTTP_5XX += 1


def bump_celery_failure() -> None:
    global _CELERY_FAILURES
    with _lock:
        _CELERY_FAILURES += 1


def get_celery_failure_count() -> int:
    return _CELERY_FAILURES


def _gauge_snapshot() -> dict:
    from core.views import probe_infra

    celery_ok, depth, _workers_ok, beat_ok = probe_infra(use_cache=True)
    db_ok = 0
    cache_ok = 0
    try:
        from django.db import connection

        connection.ensure_connection()
        db_ok = 1
    except Exception:  # noqa: BLE001
        db_ok = 0
    try:
        from django.core.cache import cache

        cache.set("bizboard:metrics_probe", "1", 5)
        cache_ok = 1 if cache.get("bizboard:metrics_probe") == "1" else 0
    except Exception:  # noqa: BLE001
        cache_ok = 0

    dlq = 0
    try:
        from billing.models import DeadLetterEvent

        dlq = DeadLetterEvent.objects.filter(status=DeadLetterEvent.Status.PENDING).count()
    except Exception:  # noqa: BLE001
        dlq = 0

    circuit_open = 0
    try:
        from core.circuit_breaker import any_open

        circuit_open = 1 if any_open() else 0
    except Exception:  # noqa: BLE001
        circuit_open = 0

    return {
        "pdf_queue_depth": 0 if depth is None else int(depth),
        "health_db": db_ok,
        "health_redis": cache_ok,
        "health_celery": 1 if celery_ok else 0,
        "health_beat": 1 if beat_ok else 0,
        "dead_letter_events": int(dlq),
        "circuit_open": circuit_open,
    }


def render_prometheus() -> str:
    gauges = _gauge_snapshot()
    lines = [
        "# HELP bizboard_http_requests_total Total HTTP requests handled by this process.",
        "# TYPE bizboard_http_requests_total counter",
        f"bizboard_http_requests_total {get_request_count()}",
        "# HELP bizboard_http_5xx_total HTTP responses with status >= 500 (this process).",
        "# TYPE bizboard_http_5xx_total counter",
        f"bizboard_http_5xx_total {_HTTP_5XX}",
        "# HELP bizboard_http_request_duration_ms_sum Sum of HTTP request duration in milliseconds (this process).",
        "# TYPE bizboard_http_request_duration_ms_sum counter",
        f"bizboard_http_request_duration_ms_sum {_DURATION_MS_SUM}",
        "# HELP bizboard_http_request_duration_ms_count Count of HTTP requests timed (this process).",
        "# TYPE bizboard_http_request_duration_ms_count counter",
        f"bizboard_http_request_duration_ms_count {_DURATION_COUNT}",
        "# HELP bizboard_celery_task_failure_total Celery task failures seen by this process.",
        "# TYPE bizboard_celery_task_failure_total counter",
        f"bizboard_celery_task_failure_total {get_celery_failure_count()}",
        "# HELP bizboard_pdf_queue_depth Broker queue depth for the default Celery queue.",
        "# TYPE bizboard_pdf_queue_depth gauge",
        f"bizboard_pdf_queue_depth {gauges['pdf_queue_depth']}",
        "# HELP bizboard_dead_letter_events Pending billing DeadLetterEvent rows.",
        "# TYPE bizboard_dead_letter_events gauge",
        f"bizboard_dead_letter_events {gauges['dead_letter_events']}",
        "# HELP bizboard_circuit_open 1 if any money-path circuit breaker is open.",
        "# TYPE bizboard_circuit_open gauge",
        f"bizboard_circuit_open {gauges['circuit_open']}",
        "# HELP bizboard_health_db 1 if the database connection probe succeeded.",
        "# TYPE bizboard_health_db gauge",
        f"bizboard_health_db {gauges['health_db']}",
        "# HELP bizboard_health_redis 1 if the cache/Redis probe succeeded.",
        "# TYPE bizboard_health_redis gauge",
        f"bizboard_health_redis {gauges['health_redis']}",
        "# HELP bizboard_health_celery 1 if Celery workers responded to inspect.ping (or eager).",
        "# TYPE bizboard_health_celery gauge",
        f"bizboard_health_celery {gauges['health_celery']}",
        "# HELP bizboard_health_beat 1 if the celery-beat heartbeat is fresh.",
        "# TYPE bizboard_health_beat gauge",
        f"bizboard_health_beat {gauges['health_beat']}",
        "",
    ]
    return "\n".join(lines)
