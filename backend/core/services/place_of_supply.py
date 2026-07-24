"""Shared helpers for document complete / place-of-supply guards."""

from core.exceptions import BusinessRuleError
from core.services.billing import is_intra_state, place_of_supply_known


def assert_place_of_supply_for_gst(*, company, party_state: str, party_gstin: str = "", tax_enabled: bool):
    """Block GST Complete when place of supply cannot be determined."""
    if not tax_enabled:
        return
    if not company.is_gst_registered:
        return
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
