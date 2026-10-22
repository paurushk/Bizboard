"""WP-GR1a: staff turn a rollout flag on or off for one company, with a reason, on the record.

Used for Tally import (Q9, 2026-10-22: import stays behind ``ENABLE_TALLY``, which is off in the
frozen profile and for trials; staff grant it to each named pilot). Only keys in
``ROLLOUT_GRANTABLE_KEYS`` can be granted — for those the company's value is applied last
(``build_feature_flags``), so a grant works even on a trial whose plan holds the flag off. Dark
modules (``DARK_MODULE_KEYS``) can't be lifted this way. Every change writes an audit row naming
the staff member, the reason and the support ticket. Flags are rebuilt on each request, so the
change applies on the company's next request.
"""

from __future__ import annotations

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService


def grantable_keys() -> list[str]:
    from core.services.feature_flags import DARK_MODULE_KEYS, ROLLOUT_GRANTABLE_KEYS

    return sorted(set(ROLLOUT_GRANTABLE_KEYS) - set(DARK_MODULE_KEYS))


def set_flag(company, *, key: str, on: bool, staff_user, reason: str, ticket: str = ""):
    if not getattr(staff_user, "is_superuser", False):
        raise BusinessRuleError("Only a superuser can grant rollout flags.")
    if key not in grantable_keys():
        raise BusinessRuleError(f"{key} can't be granted per company.")
    if len((reason or "").strip()) < 5:
        raise BusinessRuleError("Say why (at least a few words).")
    flags = dict(company.feature_flags or {})
    before = flags.get(key)
    if on:
        flags[key] = True
    else:
        flags.pop(key, None)
    company.feature_flags = flags
    company.save(update_fields=["feature_flags", "updated_at"])
    AuditService.log(
        company=company, user=staff_user, action="rollout_flag.granted" if on else "rollout_flag.revoked",
        entity_type="Company", entity_id=company.pk,
        description=f"{key} {'on' if on else 'off'}: {reason.strip()}",
        metadata={"key": key, "before": before, "ticket": ticket, "reason": reason.strip()[:500]},
    )
    return company

