"""FG-2c — place-of-supply → intra/inter-state is a pure function of
(seller state, party state, supply type). Table-driven, no DB.

Covers the state-pair x supply-type grid plus the export/SEZ override and the
blank-party 'assume local' behaviour. Rate resolution (HSN/SAC x effective date)
is a separate fixture set — see tests/gst/fixtures/.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.services.place_of_supply import (
    is_export_or_sez_supply,
    party_intra_state,
    resolve_place_of_supply_code,
)

KA = "Karnataka"       # state code 29
MH = "Maharashtra"     # state code 27
KA_GSTIN = "29AAAAA0000A1ZY"
MH_GSTIN = "27AAAAA0000A1ZY"


def _company(state=KA, gstin=KA_GSTIN, assume_local=False):
    return SimpleNamespace(
        state=state, gstin=gstin, assume_local_state_for_blank_party=assume_local
    )


# (seller_state, seller_gstin, party_state, party_gstin, supply_type, expect_intra)
_MATRIX = [
    ("same state, both registered",      KA, KA_GSTIN, KA, KA_GSTIN, "", True),
    ("different state, both registered",  KA, KA_GSTIN, MH, MH_GSTIN, "", False),
    ("same state, party unregistered",    KA, KA_GSTIN, KA, "",       "", True),
    ("different state, party unregistered", KA, KA_GSTIN, MH, "",     "", False),
    ("export with parties in same state", KA, KA_GSTIN, KA, KA_GSTIN, "EXPWP", False),
    ("export without payment",            KA, KA_GSTIN, MH, "",       "EXPWOP", False),
    ("SEZ with payment, same state",      KA, KA_GSTIN, KA, KA_GSTIN, "SEZWP", False),
    ("deemed export is domestic (intra)", KA, KA_GSTIN, KA, KA_GSTIN, "DEXP", True),
]


@pytest.mark.parametrize(
    "label,seller_state,seller_gstin,party_state,party_gstin,supply_type,expect_intra",
    _MATRIX,
    ids=[row[0] for row in _MATRIX],
)
def test_intra_state_matrix(
    label, seller_state, seller_gstin, party_state, party_gstin, supply_type, expect_intra
):
    company = _company(state=seller_state, gstin=seller_gstin)
    got = party_intra_state(
        company,
        party_state,
        party_gstin,
        seller_state=seller_state,
        seller_gstin=seller_gstin,
        supply_type=supply_type,
    )
    assert got is expect_intra, f"{label}: expected intra={expect_intra}, got {got}"


def test_export_and_sez_are_always_inter_state():
    for st in ("EXPWP", "EXPWOP", "SEZWP", "SEZWOP"):
        assert is_export_or_sez_supply(st) is True
        assert resolve_place_of_supply_code(supply_type=st) == "96"
    assert is_export_or_sez_supply("DEXP") is False


def test_blank_party_without_assume_local_is_unresolved():
    company = _company(assume_local=False)
    assert resolve_place_of_supply_code(party_state="", party_gstin="", company=company) is None


def test_blank_party_with_assume_local_falls_back_to_seller_state():
    company = _company(state=KA, gstin=KA_GSTIN, assume_local=True)
    code = resolve_place_of_supply_code(
        party_state="", party_gstin="", company=company, seller_gstin=KA_GSTIN
    )
    assert code == "29"
    assert party_intra_state(company, "", "", seller_state=KA, seller_gstin=KA_GSTIN) is True
