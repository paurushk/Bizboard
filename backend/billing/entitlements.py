"""Plan-module keys that stay off for freeze / paid-beta until a new freeze.

FREEZE_SCOPE.md Table B: Tally sync, manufacturing, payroll, and CRM are not
supported. POS is in freeze scope (A23). Seeded SaaS plans must not grant
Table B modules — a paid Starter/Pro checkout must not turn those surfaces on.

GSTR-1 / GSTR-3B worksheets (``ENABLE_GSTR``) are granted on every seeded paid
plan, as on the trial (founder decision D-16, 2026-10-25), so upgrading never
takes them away. They are worksheets for the CA, not GSTN filing;
``ENABLE_GSTN_JSON`` stays ungranted.
"""

from __future__ import annotations

FREEZE_DARK_PLAN_MODULES: tuple[str, ...] = (
    "ENABLE_MANUFACTURING",
    "ENABLE_PAYROLL",
    "ENABLE_CRM",
    "ENABLE_TALLY",
)


def freeze_safe_modules(*, pos: bool) -> dict[str, bool]:
    modules = {key: False for key in FREEZE_DARK_PLAN_MODULES}
    modules["ENABLE_GSTR"] = True
    modules["ENABLE_POS"] = bool(pos)
    return modules
