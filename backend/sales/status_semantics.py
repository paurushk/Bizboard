"""Canonical predicates over SalesInvoice.status (CF-001, TESTING_STRATEGY.md
§8 weak assumption #12; CROSS_FLOW_IMPACT_MAP.md §1).

G-17 through G-20 all had the same root cause: independent readers each
wrote their own `status__in=(COMPLETED, RETURNED)` or `status=COMPLETED`
filter and drifted from each other, because nothing forced them to agree.
This module doesn't invent new semantics — it names the two status-sets
already correctly in use across the codebase today, so future readers call
one tested predicate instead of restating the set:

- ``is_open_receivable`` — may still carry a nonzero AR balance (outstanding
  / aging / statements / payment-health / dunning / credit-risk). A RETURNED
  invoice can still owe money: the auto credit-note from a full return
  doesn't always net exactly to zero (e.g. a post-return debit note).
- ``is_operational_sale`` — counts as a real, standing sale for analytics/
  attribution (best-seller, trending, margin, concentration). Deliberately
  excludes RETURNED — a fully-reversed sale is treated as never having
  happened.

There is no third "is_dunning_eligible" predicate: dunning eligibility is
``is_open_receivable`` plus a due-date rule, not a distinct status set.
"""

from __future__ import annotations

from .models import SalesInvoice

Status = SalesInvoice.Status

OPEN_RECEIVABLE_STATUSES = (Status.COMPLETED, Status.RETURNED)
OPERATIONAL_SALE_STATUSES = (Status.COMPLETED,)

# Back-compat alias — ledgers/services.py originated this name; keep it
# importable from here too so callers can migrate one at a time.
OPEN_SALES_STATUSES = OPEN_RECEIVABLE_STATUSES


def is_open_receivable(status: str) -> bool:
    return status in OPEN_RECEIVABLE_STATUSES


def is_operational_sale(status: str) -> bool:
    return status in OPERATIONAL_SALE_STATUSES
