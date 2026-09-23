"""Country-neutral tax engine surface (COMP-009).

No GST vocabulary here. India is the only pack shipped.
"""

from __future__ import annotations

from typing import Protocol


class TaxEngine(Protocol):
    def round_amount(self, value): ...

    def apply_effective_rate(self, document, item, *, tax_enabled: bool = True): ...

    def is_intra_jurisdiction(self, company_state: str, party_state: str, **kwargs) -> bool: ...

    def compute_document_totals(self, document, items, **kwargs): ...
