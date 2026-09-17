"""V3 / G-mutation — assertions that kill likely survivors on money/tax/stock.

mutmut itself stays Linux-only (`scripts/mutation_audit.sh`). These tests are
the triage: they pin behaviour the audit targets (`core.services.billing`,
`place_of_supply`, `tds_worksheets.parse_month_period`, `opening_is_voided`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from core.exceptions import BusinessRuleError, exception_error_code
from core.help_codes import HelpCode
from core.services.billing import extract_state_code, is_intra_state, place_of_supply_known
from core.services.place_of_supply import (
    assert_place_of_supply_for_gst,
    is_deemed_export_supply,
    is_export_or_sez_supply,
    resolve_place_of_supply_code,
)
from inventory.services import InventoryService
from reporting.tds_worksheets import parse_month_period

KA_GSTIN = "29AAAAA0000A1ZY"
MH_GSTIN = "27AAAAA0000A1ZY"


def test_extract_state_code_rejects_non_gstin_15_char_and_blank():
    assert extract_state_code(None) is None
    assert extract_state_code("") is None
    assert extract_state_code("   ") is None
    # BILL-08: 15 chars starting with digits is not enough without GSTIN shape.
    assert extract_state_code("111111111111111") is None
    assert extract_state_code("29notagstinXXXX") is None
    assert extract_state_code("00") is None
    assert extract_state_code("29") == "29"
    assert extract_state_code(KA_GSTIN) == "29"
    assert extract_state_code("Karnataka") == "29"
    assert extract_state_code("karnataka") == "29"


def test_is_intra_state_blank_party_is_not_silent_intra():
    assert is_intra_state("Karnataka", "Karnataka") is True
    assert is_intra_state("Karnataka", "Maharashtra") is False
    assert is_intra_state("Karnataka", "") is False
    assert is_intra_state("", "Karnataka") is False
    assert is_intra_state("Karnataka", "Maharashtra", company_gstin=KA_GSTIN, party_gstin=MH_GSTIN) is False
    assert is_intra_state("Karnataka", "Karnataka", company_gstin=KA_GSTIN, party_gstin=KA_GSTIN) is True


def test_place_of_supply_known_requires_mappable_code():
    assert place_of_supply_known(party_state="Narnia") is False
    assert place_of_supply_known(party_state="Karnataka") is True
    assert place_of_supply_known(party_gstin=KA_GSTIN) is True


def test_dexp_is_domestic_pos_not_96():
    assert is_export_or_sez_supply("DEXP") is False
    assert is_deemed_export_supply("DEXP") is True
    assert is_deemed_export_supply("EXPWP") is False
    assert resolve_place_of_supply_code(supply_type="DEXP", party_gstin=KA_GSTIN) == "29"
    assert resolve_place_of_supply_code(supply_type="EXPWP") == "96"


def test_assert_place_of_supply_skips_when_tax_disabled():
    company = SimpleNamespace(assume_local_state_for_blank_party=False)
    assert_place_of_supply_for_gst(
        company=company, party_state="", party_gstin="", tax_enabled=False
    )


def test_assert_place_of_supply_blocks_unresolved_gst():
    company = SimpleNamespace(assume_local_state_for_blank_party=False)
    with pytest.raises(BusinessRuleError) as exc:
        assert_place_of_supply_for_gst(
            company=company, party_state="", party_gstin="", tax_enabled=True
        )
    assert exception_error_code(exc.value) == HelpCode.PLACE_OF_SUPPLY_UNRESOLVED


def test_parse_month_period_january_and_december_inclusive():
    assert parse_month_period("2026-01") == (date(2026, 1, 1), date(2026, 1, 31))
    assert parse_month_period("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))
    assert parse_month_period("2024-02") == (date(2024, 2, 1), date(2024, 2, 29))
    with pytest.raises(ValueError):
        parse_month_period("2026-13")
    with pytest.raises(ValueError):
        parse_month_period("2026-00")


def test_opening_is_voided_early_returns_without_db():
    assert InventoryService.opening_is_voided(SimpleNamespace(reference_type="import_voided", reference_id="1")) is True
    assert InventoryService.opening_is_voided(SimpleNamespace(reference_type="sale", reference_id="9")) is False
    assert InventoryService.opening_is_voided(SimpleNamespace(reference_type="import", reference_id="")) is False
    assert InventoryService.opening_is_voided(SimpleNamespace(reference_type="import", reference_id=None)) is False
