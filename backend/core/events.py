"""
In-process domain event bus (MVP).

Document services emit events inside the completing DB transaction;
handlers (audit, PDF queueing, notifications) react synchronously.
A message broker can replace this later without touching emitters.
"""

import logging
from collections import defaultdict
from typing import Callable

_subscribers: dict[str, list[Callable]] = defaultdict(list)
logger = logging.getLogger(__name__)


def subscribe(event_name: str):
    def decorator(fn: Callable):
        _subscribers[event_name].append(fn)
        return fn

    return decorator


def emit(event_name: str, **payload):
    """Run handlers but never abort the emitter's transaction (P0)."""
    for handler in list(_subscribers.get(event_name) or ()):
        try:
            handler(**payload)
        except Exception:
            logger.exception(
                "Domain event handler failed event=%s handler=%s",
                event_name,
                getattr(handler, "__name__", handler),
            )
