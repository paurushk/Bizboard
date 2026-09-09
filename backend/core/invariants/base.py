"""Invariant registry (Phase 2 — Freeze Gate crown jewels).

An *invariant* is a business rule that must hold for a company at rest — after
any completed operation. Each is a function ``check(company) -> list[str]``:
an empty list means it holds; each string is one human-readable violation.

Register with ``@invariant("<domain>.<name>", consequence="one sentence")`` and
run them all with ``assert_all_invariants(company)``.

Design notes:
- Checks are **read-only**. They must never write, and should avoid heavy
  queries that would dominate a test's runtime — aggregate, don't loop rows
  where a DB aggregate will do.
- A check that cannot run for a company (feature off, no data) returns ``[]``.
- Grouping by ``<domain>`` lets callers scope: ``assert_all_invariants(c,
  only={"gl", "inventory"})`` or ``skip={"gst"}``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

CheckFn = Callable[[object], list[str]]

_REGISTRY: dict[str, tuple[CheckFn, str]] = {}


class InvariantViolation(AssertionError):
    """Raised by assert_all_invariants when one or more invariants fail."""

    def __init__(self, company, failures: dict[str, list[str]]):
        self.company = company
        self.failures = failures
        company_label = getattr(company, "name", None) or getattr(company, "pk", "?")
        lines = [f"Invariant violations for company {company_label!r}:"]
        for name, msgs in failures.items():
            lines.append(f"  [{name}]")
            for m in msgs:
                lines.append(f"    - {m}")
        super().__init__("\n".join(lines))


def invariant(name: str, *, consequence: str) -> Callable[[CheckFn], CheckFn]:
    """Register ``fn`` as the invariant ``name`` (e.g. ``"gl.trial_balance_zero"``)."""

    def deco(fn: CheckFn) -> CheckFn:
        if name in _REGISTRY:
            raise RuntimeError(f"invariant {name!r} already registered")
        _REGISTRY[name] = (fn, consequence)
        fn._invariant_name = name  # type: ignore[attr-defined]
        fn._invariant_consequence = consequence  # type: ignore[attr-defined]
        return fn

    return deco


def _domain(name: str) -> str:
    return name.split(".", 1)[0]


def registered() -> dict[str, str]:
    """{invariant name: consequence} — for docs / the CI listing."""
    return {name: cons for name, (_fn, cons) in sorted(_REGISTRY.items())}


def run_invariants(
    company,
    *,
    only: Iterable[str] | None = None,
    skip: Iterable[str] | None = None,
) -> dict[str, list[str]]:
    """Run matching invariants; return {name: violations} for those that failed."""
    only_set = set(only) if only is not None else None
    skip_set = set(skip) if skip is not None else set()
    failures: dict[str, list[str]] = {}
    for name, (fn, _cons) in _REGISTRY.items():
        dom = _domain(name)
        if only_set is not None and dom not in only_set and name not in only_set:
            continue
        if dom in skip_set or name in skip_set:
            continue
        try:
            violations = fn(company) or []
        except Exception as exc:  # a broken check must not masquerade as "clean"
            violations = [f"invariant check raised {type(exc).__name__}: {exc}"]
        if violations:
            failures[name] = list(violations)
    return failures


def assert_all_invariants(
    company,
    *,
    only: Iterable[str] | None = None,
    skip: Iterable[str] | None = None,
) -> None:
    """Raise :class:`InvariantViolation` if any matching invariant fails."""
    failures = run_invariants(company, only=only, skip=skip)
    if failures:
        raise InvariantViolation(company, failures)
