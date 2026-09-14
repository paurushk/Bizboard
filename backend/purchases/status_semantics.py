"""Canonical predicates over PurchaseInvoice.status (Phase 7.1 / CF-001 twin).

Mirrors ``sales.status_semantics`` so AP readers cannot each invent
``status__in=(COMPLETED, RETURNED)`` and drift (G-18 class).

- ``is_open_payable`` — may still carry a nonzero AP balance (outstanding /
  aging / dunning / GST inward). A RETURNED purchase can still owe the
  supplier after a residual debit note.
- ``is_operational_purchase`` — counts as a standing purchase for analytics.
  Deliberately excludes RETURNED.
"""

from __future__ import annotations

from .models import PurchaseInvoice

Status = PurchaseInvoice.Status

OPEN_PAYABLE_STATUSES = (Status.COMPLETED, Status.RETURNED)
OPERATIONAL_PURCHASE_STATUSES = (Status.COMPLETED,)


def is_open_payable(status: str) -> bool:
    return status in OPEN_PAYABLE_STATUSES


def is_operational_purchase(status: str) -> bool:
    return status in OPERATIONAL_PURCHASE_STATUSES
