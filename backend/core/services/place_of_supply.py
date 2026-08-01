"""Shared helpers for document complete / place-of-supply guards."""

from core.exceptions import BusinessRuleError
from core.services.billing import is_intra_state, place_of_supply_known


def assert_place_of_supply_for_gst(*, company, party_state: str, party_gstin: str = "", tax_enabled: bool):
    """Block GST Complete when place of supply cannot be determined."""
    if not tax_enabled:
        return
    # BUG-206: this used to also return early whenever the company itself
    # wasn't GST-registered — but an unregistered/composition company can
    # still issue a tax_enabled invoice type (TAX/RETAIL) that computes real
    # CGST/SGST/IGST, so gating on tax_enabled alone (not is_gst_registered)
    # is what actually matches whether tax is about to be computed.
    if place_of_supply_known(party_state=party_state, party_gstin=party_gstin):
        return
    if getattr(company, "assume_local_state_for_blank_party", False):
        return
    raise BusinessRuleError(
        "Customer/supplier state or GSTIN is required for GST invoices. "
        "Add place of supply, or enable 'Assume local state for blank party' in GST settings."
    )


def party_intra_state(company, party_state: str, party_gstin: str = "") -> bool:
    return is_intra_state(
        company.state,
        party_state,
        company_gstin=company.gstin or "",
        party_gstin=party_gstin or "",
    )
