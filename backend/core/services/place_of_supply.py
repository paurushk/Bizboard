"""Shared helpers for document complete / place-of-supply guards."""

from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode
from core.services.billing import extract_state_code, is_intra_state, place_of_supply_known

# POS-01: DEXP (deemed export) is a *domestic* supply — the recipient is in
# India (EOU / Advance-Authorisation holder), so its place of supply is the
# recipient's actual state (GSTR-1 table 6C), never the export code "96". Only
# real exports / SEZ supplies get POS 96 and skip the party-state requirement.
EXPORT_SEZ_SUPPLY_TYPES = frozenset({"SEZWP", "SEZWOP", "EXPWP", "EXPWOP"})
DEEMED_EXPORT_SUPPLY_TYPES = frozenset({"DEXP"})
EXPORT_POS_CODE = "96"


def is_export_or_sez_supply(supply_type: str | None) -> bool:
    """Real export / SEZ supply → POS 96, no party state needed. Excludes DEXP."""
    return (supply_type or "").strip().upper() in EXPORT_SEZ_SUPPLY_TYPES


def is_deemed_export_supply(supply_type: str | None) -> bool:
    return (supply_type or "").strip().upper() in DEEMED_EXPORT_SUPPLY_TYPES


def resolve_place_of_supply_code(
    *,
    party_state="",
    party_gstin="",
    supply_type="",
    company=None,
    seller_gstin="",
    seller_state="",
) -> str | None:
    if is_export_or_sez_supply(supply_type):
        return EXPORT_POS_CODE
    code = party_state_code(party_state, party_gstin)
    if code:
        return code
    if company is not None and getattr(company, "assume_local_state_for_blank_party", False):
        return (
            extract_state_code(seller_gstin)
            or extract_state_code(seller_state)
            or extract_state_code(getattr(company, "gstin", None) or "")
            or extract_state_code(getattr(company, "state", None) or "")
        )
    return None


def assert_place_of_supply_for_gst(
    *,
    company,
    party_state: str,
    party_gstin: str = "",
    tax_enabled: bool,
    supply_type: str = "",
):
    """Block GST Complete when place of supply cannot be determined."""
    if not tax_enabled:
        return
    # Export / SEZ: POS is fixed as 96 — no party state required.
    if is_export_or_sez_supply(supply_type):
        return
    # BUG-206: this used to also return early whenever the company itself
    # wasn't GST-registered — but an unregistered/composition company can
    # still issue a tax_enabled invoice type (TAX/RETAIL) that computes real
    # CGST/SGST/IGST, so gating on tax_enabled alone (not is_gst_registered)
    # is what actually matches whether tax is about to be computed.
    # BB-000063: place_of_supply_known uses GSTIN digits + state-name→code map.
    if place_of_supply_known(party_state=party_state, party_gstin=party_gstin):
        return
    if not (party_state or "").strip() and getattr(company, "assume_local_state_for_blank_party", False):
        return
    raise BusinessRuleError(
        "Customer/supplier state or GSTIN is required for GST invoices. "
        "Add place of supply, or enable 'Assume local state for blank party' in GST settings.",
        code=HelpCode.PLACE_OF_SUPPLY_UNRESOLVED,
    )


def party_intra_state(
    company,
    party_state: str,
    party_gstin: str = "",
    *,
    seller_state: str = "",
    seller_gstin: str = "",
) -> bool:
    """Intra/inter via normalized state codes (BB-000063), not raw free-text alone.

    Unresolvable free-text (or truly blank) is treated as blank for assume_local.
    """
    if not place_of_supply_known(party_state=party_state, party_gstin=party_gstin):
        return bool(getattr(company, "assume_local_state_for_blank_party", False))
    return is_intra_state(
        seller_state or company.state or "",
        party_state,
        company_gstin=seller_gstin or company.gstin or "",
        party_gstin=party_gstin or "",
    )


def party_state_code(party_state: str = "", party_gstin: str = "") -> str | None:
    """Canonical POS code: GSTIN digits 0–1 first, else mapped state name."""
    return extract_state_code(party_gstin) or extract_state_code(party_state)
