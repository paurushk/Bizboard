"""Every test under tests/regression/ gets the ``regression`` marker for free."""

from __future__ import annotations


def pytest_collection_modifyitems(config, items):
    import pathlib

    here = pathlib.Path(__file__).parent
    for item in items:
        try:
            in_regression = here in pathlib.Path(str(item.fspath)).parents
        except Exception:
            in_regression = False
        if in_regression:
            item.add_marker("regression")
