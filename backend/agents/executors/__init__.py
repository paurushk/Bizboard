"""Shared executor helpers. Executors call EXISTING domain services; they never write models directly.

An executor is ``fn(proposal, ctx) -> dict`` returning ``result_ref``. It must:
* re-validate against live data and raise ``StaleProposal`` if the world changed;
* stamp document dates with ``ctx.today`` (execution time), never from the payload;
* pass ``ctx.external_ref`` to the domain service so the same revision cannot create two documents.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core.exceptions import BusinessRuleError

from .. import error_codes as E


class StaleProposal(BusinessRuleError):
    status_code = 409

    def __init__(self, detail="The data changed since this draft was prepared. Prepare it again."):
        super().__init__(detail=detail, code=E.AGT_E_STALE)


@dataclass
class ExecContext:
    company: object
    company_user: object
    today: date
    external_ref: str


def external_ref(proposal) -> str:
    return f"{proposal.idempotency_key}:r{proposal.revision}"
