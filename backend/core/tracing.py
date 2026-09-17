"""Lightweight request spans for money-path operations.

Sentry sampling remains the production tracer when SENTRY_DSN is set. This
module always records a structured log line so tests and local ops can assert
a Complete / webhook span existed, without requiring OpenTelemetry.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger("bizboard.trace")

_current_spans: ContextVar[list] = ContextVar("bizboard_trace_spans", default=None)


def captured_spans() -> list[dict]:
    return list(_current_spans.get() or [])


def clear_spans() -> None:
    _current_spans.set([])


@contextmanager
def trace_span(name: str, **attrs):
    started = time.perf_counter()
    try:
        from core.observability import current_request_id

        rid = current_request_id()
        if rid and "request_id" not in attrs:
            attrs = {**attrs, "request_id": rid}
    except Exception:  # noqa: BLE001
        pass
    record = {"name": name, "attrs": dict(attrs), "duration_ms": None, "error": None}
    try:
        yield record
    except Exception as exc:
        record["error"] = type(exc).__name__
        raise
    finally:
        record["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
        bucket = _current_spans.get()
        if bucket is None:
            bucket = []
            _current_spans.set(bucket)
        bucket.append(record)
        logger.info(
            "span %s duration_ms=%s",
            name,
            record["duration_ms"],
            extra={"span": name, "duration_ms": record["duration_ms"], **attrs},
        )
