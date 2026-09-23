"""Resolve the tax pack for a company. India is the only pack."""

from __future__ import annotations

from .base import TaxEngine
from .india import IndiaTaxEngine


def get_tax_engine(company) -> TaxEngine:
    del company  # one pack until a second country is a separate ticket
    return IndiaTaxEngine()
