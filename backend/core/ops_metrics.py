"""Process-local + infra gauges for GET /metrics (O-Gate 1), plus multiprocess mode (WP-D2).

Without ``PROMETHEUS_MULTIPROC_DIR`` (dev, tests): HTTP counters are per-process, a
scrape reaches ONE gunicorn worker, and the latency histogram carries a ``pid`` label
(aggregate with ``sum without (pid) (...)``).

With ``PROMETHEUS_MULTIPROC_DIR`` set (staging, production): every counter and
histogram is also recorded through ``prometheus_client`` in multiprocess mode, and
``/metrics`` renders the sum across all worker processes of the container. Each Celery
worker container serves its own task metrics on ``WORKER_METRICS_PORT``
(``config/celery.py``); the collector scrapes the api and every worker. The directory
must be emptied before the server starts (the Compose command) and dead
gunicorn workers are marked in ``child_exit`` (``config/gunicorn.conf.py``).

Queue / health / DLQ / books-check gauges are read at scrape time from Redis/DB with
the same ~15s cache as HealthView. Never put a company id in a label.
"""

from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_REQUEST_COUNT = 0
_HTTP_5XX = 0
_DURATION_MS_SUM = 0
_DURATION_COUNT = 0
_CELERY_FAILURES = 0
# Upper bounds (ms) of the request-latency histogram. The perf SLOs (500 ms dashboard,
# 800 ms Complete, 2 s list) and the 8 s gate each sit on or between bucket edges.
LATENCY_BUCKETS_MS = (50, 100, 250, 500, 800, 1000, 2000, 5000, 8000, 30000)
_BUCKET_COUNTS = [0] * (len(LATENCY_BUCKETS_MS) + 1)  # last slot = +Inf

# Every Celery queue a worker must consume (config/celery.py routes). Depth is read per queue.
CELERY_QUEUES = ("celery", "high_priority", "media_heavy", "reports", "agents", "agents_interactive")


def multiprocess_enabled() -> bool:
    return bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR"))


_MP: dict | None = None


def _mp() -> dict | None:
    """The prometheus_client metric objects, created once per process (multiprocess mode only)."""
    global _MP
    if _MP is not None or not multiprocess_enabled():
        return _MP
    try:
        from prometheus_client import Counter, Histogram
    except ImportError:  # pragma: no cover - requirements.txt pins it
        return None
    _MP = {
        "requests": Counter("bizboard_http_requests", "HTTP requests handled.", ["status_class"]),
        "http_5xx": Counter("bizboard_http_5xx", "HTTP responses with status >= 500."),
        "latency": Histogram(
            "bizboard_http_latency_ms",
            "Request latency in milliseconds.",
            buckets=[*LATENCY_BUCKETS_MS, float("inf")],
        ),
        "events": Counter("bizboard_business_events", "Business events (receipts created, voided...).", ["event"]),
        "celery_failures": Counter("bizboard_celery_task_failure", "Celery task failures."),
        "celery_duration": Histogram(
            "bizboard_celery_task_duration_seconds",
            "Celery task run time in seconds.",
            ["task", "status"],
            buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 300, 900, float("inf")),
        ),
    }
    return _MP


def bump_request_count() -> None:
    global _REQUEST_COUNT
    with _lock:
        _REQUEST_COUNT += 1
    # The multiprocess request counter is bumped in record_http_result, which knows the status.


def get_request_count() -> int:
    return _REQUEST_COUNT


def record_http_result(*, status: int, duration_ms: int) -> None:
    global _HTTP_5XX, _DURATION_MS_SUM, _DURATION_COUNT
    d = max(0, int(duration_ms))
    slot = next((i for i, le in enumerate(LATENCY_BUCKETS_MS) if d <= le), len(LATENCY_BUCKETS_MS))
    with _lock:
        _DURATION_MS_SUM += d
        _DURATION_COUNT += 1
        _BUCKET_COUNTS[slot] += 1
        if int(status) >= 500:
            _HTTP_5XX += 1
    mp = _mp()
    if mp is not None:
        try:
            mp["requests"].labels(status_class=f"{int(status) // 100}xx").inc()
            mp["latency"].observe(d)
            if int(status) >= 500:
                mp["http_5xx"].inc()
        except Exception:  # noqa: BLE001 - metrics must never break a request
            pass


_EVENTS: dict[str, int] = {}


def bump_event(name: str) -> None:
    """Count a business event (this process), e.g. ``money_in_receipt_voided``. Never raises."""
    key = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(name))[:64] or "unknown"
    with _lock:
        _EVENTS[key] = _EVENTS.get(key, 0) + 1
    mp = _mp()
    if mp is not None:
        try:
            mp["events"].labels(event=key).inc()
        except Exception:  # noqa: BLE001
            pass


def get_event_counts() -> dict[str, int]:
    with _lock:
        return dict(_EVENTS)


def bump_celery_failure() -> None:
    global _CELERY_FAILURES
    with _lock:
        _CELERY_FAILURES += 1
    mp = _mp()
    if mp is not None:
        try:
            mp["celery_failures"].inc()
        except Exception:  # noqa: BLE001
            pass


def get_celery_failure_count() -> int:
    return _CELERY_FAILURES


def observe_celery_task(*, task: str, status: str, duration_ms: int | None) -> None:
    """Record one finished Celery task (worker side). Never raises."""
    mp = _mp()
    if mp is None or duration_ms is None:
        return
    try:
        mp["celery_duration"].labels(task=str(task)[:120], status=str(status)).observe(max(0, duration_ms) / 1000)
    except Exception:  # noqa: BLE001
        pass


def queue_depths() -> dict[str, int]:
    """Broker depth per Celery queue (Redis LLEN). All zero when eager; empty when Redis is unreachable."""
    from django.conf import settings

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return {q: 0 for q in CELERY_QUEUES}
    url = getattr(settings, "CELERY_BROKER_URL", None) or getattr(settings, "REDIS_URL", None)
    if not url:
        return {}
    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        return {q: int(client.llen(q) or 0) for q in CELERY_QUEUES}
    except Exception:  # noqa: BLE001
        return {}


def books_check_failures() -> int:
    """Companies whose latest nightly books check FAILED or hit an ERROR (cached 60 s)."""
    from django.core.cache import cache

    key = "bizboard:metrics_books_failures"
    try:
        cached = cache.get(key)
    except Exception:  # noqa: BLE001
        cached = None
    if cached is not None:
        return int(cached)
    try:
        from core.sweep import failing_company_count

        value = failing_company_count()
    except Exception:  # noqa: BLE001
        return 0
    try:
        cache.set(key, value, 60)
    except Exception:  # noqa: BLE001
        pass
    return value


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


_GAUGE_HELP = (
    ("pdf_queue_depth", "Broker queue depth for the default Celery queue."),
    ("dead_letter_events", "Pending billing DeadLetterEvent rows."),
    ("circuit_open", "1 if any money-path circuit breaker is open."),
    ("health_db", "1 if the database connection probe succeeded."),
    ("health_redis", "1 if the cache/Redis probe succeeded."),
    ("health_celery", "1 if Celery workers responded to inspect.ping (or eager)."),
    ("health_beat", "1 if the celery-beat heartbeat is fresh."),
)


def clock_skew_seconds() -> float:
    """WP-CP1: |app clock - database clock| in seconds. CERT-In needs logs with synced time (NTP on
    every host); a drift means incident timelines across logs can't be trusted. -1 if unknown."""
    import datetime as _dt

    try:
        from django.db import connection

        if connection.vendor != "postgresql":
            return 0.0
        with connection.cursor() as cur:
            before = _dt.datetime.now(_dt.timezone.utc)
            cur.execute("SELECT now()")
            db_now = cur.fetchone()[0]
            after = _dt.datetime.now(_dt.timezone.utc)
        mid = before + (after - before) / 2
        return round(abs((mid - db_now).total_seconds()), 3)
    except Exception:  # noqa: BLE001
        return -1.0


def _scrape_time_lines(gauges: dict) -> list[str]:
    """Gauges read at scrape time: the same value whichever worker answers."""
    lines: list[str] = []
    for name, help_text in _GAUGE_HELP:
        lines += [f"# HELP bizboard_{name} {help_text}", f"# TYPE bizboard_{name} gauge", f"bizboard_{name} {gauges[name]}"]
    lines += [
        "# HELP bizboard_celery_queue_depth Broker depth per Celery queue.",
        "# TYPE bizboard_celery_queue_depth gauge",
        *[f'bizboard_celery_queue_depth{{queue="{q}"}} {n}' for q, n in sorted(queue_depths().items())],
        "# HELP bizboard_books_check_failures Companies whose latest nightly books check failed or crashed.",
        "# TYPE bizboard_books_check_failures gauge",
        f"bizboard_books_check_failures {books_check_failures()}",
        "# HELP bizboard_clock_skew_seconds Absolute difference between app and database clocks.",
        "# TYPE bizboard_clock_skew_seconds gauge",
        f"bizboard_clock_skew_seconds {clock_skew_seconds()}",
    ]
    return lines


def _histogram_lines() -> list[str]:
    pid = os.getpid()
    with _lock:
        counts = list(_BUCKET_COUNTS)
        total = _DURATION_COUNT
        dsum = _DURATION_MS_SUM
    lines = [
        "# HELP bizboard_http_latency_ms Request latency histogram in milliseconds (this process).",
        "# TYPE bizboard_http_latency_ms histogram",
    ]
    running = 0
    for le, c in zip(LATENCY_BUCKETS_MS, counts):
        running += c
        lines.append(f'bizboard_http_latency_ms_bucket{{le="{le}",pid="{pid}"}} {running}')
    lines.append(f'bizboard_http_latency_ms_bucket{{le="+Inf",pid="{pid}"}} {total}')
    lines.append(f'bizboard_http_latency_ms_sum{{pid="{pid}"}} {dsum}')
    lines.append(f'bizboard_http_latency_ms_count{{pid="{pid}"}} {total}')
    return lines


def render_multiprocess() -> str:
    """Counters and histograms summed across every worker process, plus the scrape-time gauges."""
    from prometheus_client import CollectorRegistry, generate_latest, multiprocess

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    body = generate_latest(registry).decode("utf-8")
    return body + "\n".join(_scrape_time_lines(_gauge_snapshot())) + "\n"


def render_prometheus() -> str:
    if multiprocess_enabled() and _mp() is not None:
        return render_multiprocess()
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
        *_scrape_time_lines(gauges),
        "# HELP bizboard_business_events_total Business events counted by this process (receipts created, voided...).",
        "# TYPE bizboard_business_events_total counter",
        *[
            f'bizboard_business_events_total{{event="{name}"}} {count}'
            for name, count in sorted(get_event_counts().items())
        ],
        *_histogram_lines(),
        "",
    ]
    return "\n".join(lines)
