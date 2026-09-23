"""Backward-compatible shim.

India GST math lives in ``core.services.tax_engine.india``. Sales and purchase
document totals go through ``get_tax_engine(company).compute_document_totals``.
These names stay importable here for the remaining helpers (rounding, state
codes, RCM, previews) and for existing tests.
"""

from core.services.tax_engine.india import (
    DISCOUNT_AFTER_TAX,
    DISCOUNT_BEFORE_TAX,
    IN_STATE_NAME_TO_CODE,
    RUPEE,
    TWO_PLACES,
    VALID_GST_STATE_CODES,
    _FROZEN_STATUS,
    _RATEABLE_DOCS,
    _apply_line_tax,
    _document_tax_date,
    _tax_totals_snapshot,
    apply_effective_gst_rate,
    apply_inclusive_prices_to_items,
    apply_rcm_memo_after_tax,
    build_totals_preview,
    compute_document_totals,
    extract_exclusive_from_inclusive_line,
    extract_state_code,
    fold_tds_from_rate,
    is_intra_state,
    place_of_supply_known,
    q2,
    recompute_totals_for_stamped_gstin,
)
from core.services.tax_engine.registry import get_tax_engine

__all__ = [
    "DISCOUNT_AFTER_TAX",
    "DISCOUNT_BEFORE_TAX",
    "IN_STATE_NAME_TO_CODE",
    "RUPEE",
    "TWO_PLACES",
    "VALID_GST_STATE_CODES",
    "_FROZEN_STATUS",
    "_RATEABLE_DOCS",
    "_apply_line_tax",
    "_document_tax_date",
    "_tax_totals_snapshot",
    "apply_effective_gst_rate",
    "apply_inclusive_prices_to_items",
    "apply_rcm_memo_after_tax",
    "build_totals_preview",
    "compute_document_totals",
    "extract_exclusive_from_inclusive_line",
    "extract_state_code",
    "fold_tds_from_rate",
    "get_tax_engine",
    "is_intra_state",
    "place_of_supply_known",
    "q2",
    "recompute_totals_for_stamped_gstin",
]
