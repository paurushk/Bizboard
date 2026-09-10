"""Shared helpers for persona journeys."""

from __future__ import annotations

import pytest


def _status(client, method, url, **kw):
    return getattr(client, method.lower())(url, **kw).status_code


@pytest.fixture
def boundary():
    """assert_allowed / assert_denied for capability-boundary checks."""

    class _B:
        @staticmethod
        def allowed(client, method, url, **kw):
            s = _status(client, method, url, **kw)
            assert s < 400 or s in (409, 422), f"{method} {url} expected allowed, got {s}"
            return s

        @staticmethod
        def denied(client, method, url, **kw):
            s = _status(client, method, url, **kw)
            assert s in (401, 403, 404), f"{method} {url} expected denied (401/403/404), got {s}"
            return s

    return _B()
