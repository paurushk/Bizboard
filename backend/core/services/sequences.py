"""Per-company sequence for documents that are not GST series."""

from __future__ import annotations

from django.db import IntegrityError, transaction

from core.exceptions import BusinessRuleError
from core.models import SequenceCounter


def next_number(company, scope: str, *, prefix: str) -> str:
    """Row-locked counter. Retries the first-insert race on the unique constraint."""
    for _ in range(3):
        try:
            with transaction.atomic():
                counter, _ = SequenceCounter.objects.select_for_update().get_or_create(
                    company=company, scope=scope, defaults={"last_value": 0}
                )
                counter.last_value += 1
                counter.save(update_fields=["last_value", "updated_at"])
                return f"{prefix}-{counter.last_value:06d}"
        except IntegrityError:
            continue
    raise BusinessRuleError("Could not allocate a number, try again.")
