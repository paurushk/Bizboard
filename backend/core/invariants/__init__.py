"""Freeze Gate crown-jewel invariants (Phase 2).

    from core.invariants import assert_all_invariants
    assert_all_invariants(company)                       # everything
    assert_all_invariants(company, only={"gl"})          # one domain
    assert_all_invariants(company, skip={"gst"})         # all but one

Importing this package registers every check. New domains: add a module here and
import it below.
"""

from __future__ import annotations

from . import (  # noqa: F401 — import = register
    gl,
    gst,
    inventory,
    money,
    numbering,
    reports,
    tenancy,
)
from .base import (
    InvariantViolation,
    assert_all_invariants,
    registered,
    run_invariants,
)

__all__ = [
    "assert_all_invariants",
    "run_invariants",
    "registered",
    "InvariantViolation",
]
