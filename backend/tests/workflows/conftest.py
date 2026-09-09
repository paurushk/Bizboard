"""Shared helpers for workflow-contract tests.

Every test here carries the ``workflow`` marker and asserts full-chain
consistency explicitly (not via the env-gated teardown sweep).
"""

from __future__ import annotations

import pathlib

import pytest

from core.invariants import assert_all_invariants


def pytest_collection_modifyitems(config, items):
    here = pathlib.Path(__file__).parent
    for item in items:
        try:
            if here in pathlib.Path(str(item.fspath)).parents:
                item.add_marker("workflow")
        except Exception:
            pass


@pytest.fixture
def assert_consistent():
    """Call ``assert_consistent(company)`` at the end of a chain."""

    def _check(company, **kw):
        assert_all_invariants(company, **kw)

    return _check
