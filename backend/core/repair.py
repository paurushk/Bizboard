"""WP-F7 / DIM6-12: every data repair leaves a trail and proves the books afterwards.

A repair command that changed a company's data calls ``record_repair`` once for that company:

- one ``AuditEvent`` (``action="REPAIR"``, ``description`` = the command name, ``metadata`` =
  what it did), written under that company's RLS scope;
- the full books check (``run_invariants``) for that company, printed, so a repair that made
  things worse is visible immediately instead of at the next nightly sweep.

Dry runs never call it. See docs/ops/LEDGER_REPAIR_RUNBOOK.md for which command fixes what.
"""

from __future__ import annotations


def record_repair(*, command: str, company, summary: dict, stdout=None, user=None) -> dict[str, list[str]]:
    from core.invariants import run_invariants
    from core.rls import rls_bypass
    from core.services.audit import AuditService

    AuditService.log(
        action="REPAIR",
        company=company,
        user=user,
        entity_type="Company",
        entity_id=company.pk,
        description=command,
        metadata={k: (str(v) if not isinstance(v, (int, float, str, bool, type(None))) else v) for k, v in summary.items()},
    )
    with rls_bypass():
        failures = run_invariants(company)
    if stdout is not None:
        if failures:
            stdout.write(f"  books check after {command} for company {company.pk}: FAILED {sorted(failures)}")
        else:
            stdout.write(f"  books check after {command} for company {company.pk}: clean")
    return failures
