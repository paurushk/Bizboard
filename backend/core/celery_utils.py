"""Dispatch Celery tasks without letting a down broker block the HTTP request."""

import logging

logger = logging.getLogger(__name__)


def safe_delay(task, *args, **kwargs):
    """Call ``task.delay``, swallowing dispatch failure.

    A down or unreachable broker must not fail the caller — the business
    transaction that triggered this dispatch has already committed. The work
    (for example rendering a PDF) can be retried from its own endpoint.
    """
    try:
        task.delay(*args, **kwargs)
    except Exception:
        logger.exception("Failed to enqueue task %s", getattr(task, "name", task))
