"""Plan-module keys that stay off for freeze / paid-beta until a new freeze.

FREEZE_SCOPE.md Table B: GSTR screens, Tally sync, manufacturing, payroll, and
CRM are not supported. POS is in freeze scope (A23). Seeded SaaS plans must
not grant Table B modules — a paid Starter/Pro checkout must not turn those
surfaces on.
"""

from __future__ import annotations

FREEZE_DARK_PLAN_MODULES: tuple[str, ...] = (
    "ENABLE_GSTR",
    "ENABLE_MANUFACTURING",
    "ENABLE_PAYROLL",
    "ENABLE_CRM",
    "ENABLE_TALLY",
)


def freeze_safe_modules(*, pos: bool) -> dict[str, bool]:
    modules = {key: False for key in FREEZE_DARK_PLAN_MODULES}
    modules["ENABLE_POS"] = bool(pos)
    return modules
