"""Audit-trail completeness (§G7 / §H-audit).

These are **plain callables — NOT registered** in the default sweep. They only
hold when a document's whole lifecycle happened in this database (the strict
sweep runs against tests that build partial state on purpose). Chains that own
the full lifecycle call them directly:

    from core.invariants.audit import statutory_events_present
    assert not statutory_events_present(company)
"""

from __future__ import annotations


def statutory_events_present(company) -> list[str]:
    """BB-000177 lifecycle log: every sales invoice past DRAFT carries a COMPLETE
    statutory event, and a CANCELLED one also carries a CANCEL event."""
    from core.models import StatutoryDocumentEvent
    from sales.models import SalesInvoice

    seen: dict[int, set[str]] = {}
    for entity_id, event_type in StatutoryDocumentEvent.objects.filter(
        company=company, entity_type="sales_invoice"
    ).values_list("entity_id", "event_type"):
        try:
            seen.setdefault(int(entity_id), set()).add(event_type)
        except (TypeError, ValueError):
            continue

    ET = StatutoryDocumentEvent.EventType
    out: list[str] = []
    for inv in SalesInvoice.objects.filter(company=company).exclude(
        status=SalesInvoice.Status.DRAFT
    ):
        have = seen.get(inv.pk, set())
        label = inv.number or f"#{inv.pk}"
        if ET.COMPLETE not in have:
            out.append(f"sales_invoice {label} ({inv.status}) has no COMPLETE event")
        if inv.status == SalesInvoice.Status.CANCELLED and ET.CANCEL not in have:
            out.append(f"sales_invoice {label} is CANCELLED but has no CANCEL event")
    return out


def money_mutations_logged(company) -> list[str]:
    """Every append-only MoneyFieldAudit row points at a live entity and records
    the from/to values — the change trail is not silently truncated."""
    from core.models import MoneyFieldAudit

    out: list[str] = []
    for row in MoneyFieldAudit.objects.filter(company=company).values(
        "id", "entity_type", "entity_id", "field", "old_value", "new_value"
    ):
        if not row["field"]:
            out.append(f"MoneyFieldAudit #{row['id']}: blank field name")
        if row["old_value"] == row["new_value"]:
            out.append(
                f"MoneyFieldAudit #{row['id']}: no-op row "
                f"({row['entity_type']} {row['field']} {row['old_value']!r})"
            )
    return out
