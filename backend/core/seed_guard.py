"""Process-local switch for the staging load fixture.

``seed_load_tenant`` turns this on so Complete does not enqueue PDFs, GSP
calls, or notification tasks. It is a ContextVar, not a setting, so a test
or a management command can enable it without mutating global Django state
for the rest of the process.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager

_active: contextvars.ContextVar[bool] = contextvars.ContextVar("bizboard_seed_load", default=False)


def seed_load_active() -> bool:
    return bool(_active.get())


@contextmanager
def seed_load_scope():
    token = _active.set(True)
    try:
        yield
    finally:
        _active.reset(token)
