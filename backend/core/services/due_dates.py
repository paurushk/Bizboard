"""One rule for when a bill falls due.

The invoice's own due date wins; otherwise bill date plus payment terms. Ageing, the
collections list and the Money hub all read it from here so they cannot disagree.
"""

from __future__ import annotations

from datetime import date, timedelta


def effective_due_date(invoice) -> date | None:
    due = getattr(invoice, "due_date", None)
    if due:
        return due
    bill_date = getattr(invoice, "invoice_date", None)
    if bill_date is None:
        return None
    return bill_date + timedelta(days=int(getattr(invoice, "payment_terms_days", 0) or 0))
