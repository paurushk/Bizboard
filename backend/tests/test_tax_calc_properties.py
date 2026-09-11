"""Property-based tests for the core rounding/GST-split logic (E4.3 follow-up).

test_tax_calc.py exercises specific, hand-picked cases through the full
invoice flow (DB-backed). These test the pure calculation primitives
directly — core/services/billing.py's q2() and _apply_line_tax() never touch
the DB — against randomly generated inputs, so hypothesis can search for a
rounding/split edge case an example-based test wouldn't think to write.

Tolerance note: BILL-01's own comment in _apply_line_tax documents that
splitting tax into two independently-rounded halves (q2(tax/2) each for
CGST/SGST) can land the pair up to one paisa over the exact
taxable*rate/100 — the same one-paisa tolerance core/invariants/gst.py's
cgst_equals_sgst/igst_xor_intrastate checks already accept at the
document-totals level. Reused here, not invented fresh.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from hypothesis import given
from hypothesis import strategies as st

from core.services.billing import _apply_line_tax, q2
from core.validators import ALLOWED_GST_RATES

_CENT = Decimal("0.01")

taxable_amounts = st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("1000000"), places=2
)
gst_rates = st.sampled_from([Decimal(r) for r in ALLOWED_GST_RATES])
booleans = st.booleans()


@given(value=st.decimals(min_value=Decimal("-1000000"), max_value=Decimal("1000000"), places=4))
def test_q2_always_quantizes_to_two_places(value):
    result = q2(value)
    assert result.as_tuple().exponent == -2


@given(value=st.decimals(min_value=Decimal("-1000000"), max_value=Decimal("1000000"), places=2))
def test_q2_is_idempotent(value):
    assert q2(q2(value)) == q2(value)


def _tax_line(taxable, rate, *, tax_enabled, intra_state):
    item = SimpleNamespace()
    _apply_line_tax(item, taxable, rate, tax_enabled=tax_enabled, intra_state=intra_state)
    return item


@given(taxable=taxable_amounts, rate=gst_rates)
def test_intra_state_taxed_line_always_has_cgst_equal_sgst(taxable, rate):
    item = _tax_line(taxable, rate, tax_enabled=True, intra_state=True)
    assert item.cgst == item.sgst
    assert item.igst == Decimal("0.00")


@given(taxable=taxable_amounts, rate=gst_rates)
def test_inter_state_taxed_line_never_carries_cgst_or_sgst(taxable, rate):
    item = _tax_line(taxable, rate, tax_enabled=True, intra_state=False)
    assert item.cgst == Decimal("0.00")
    assert item.sgst == Decimal("0.00")
    # A sub-half-paisa raw tax (e.g. taxable=0.01, rate=0.25%) legitimately
    # rounds down to 0.00 — only assert strictly positive once the raw tax
    # clears the rounding threshold.
    if taxable * rate / Decimal("100") >= Decimal("0.005"):
        assert item.igst > Decimal("0.00")
    else:
        assert item.igst >= Decimal("0.00")


@given(taxable=taxable_amounts, rate=gst_rates, intra_state=booleans)
def test_tax_disabled_line_is_always_zero_tax(taxable, rate, intra_state):
    item = _tax_line(taxable, rate, tax_enabled=False, intra_state=intra_state)
    assert item.cgst == Decimal("0.00")
    assert item.sgst == Decimal("0.00")
    assert item.igst == Decimal("0.00")


@given(taxable=taxable_amounts, rate=gst_rates)
def test_intra_state_total_tax_matches_taxable_times_rate_within_a_paisa(taxable, rate):
    item = _tax_line(taxable, rate, tax_enabled=True, intra_state=True)
    expected = taxable * rate / Decimal("100")
    actual_total = item.cgst + item.sgst
    assert abs(actual_total - expected) <= _CENT


@given(taxable=taxable_amounts, rate=gst_rates)
def test_inter_state_igst_matches_taxable_times_rate_exactly_after_rounding(taxable, rate):
    item = _tax_line(taxable, rate, tax_enabled=True, intra_state=False)
    assert item.igst == q2(taxable * rate / Decimal("100"))


@given(taxable=taxable_amounts, rate=gst_rates, intra_state=booleans)
def test_line_total_equals_taxable_plus_tax(taxable, rate, intra_state):
    item = _tax_line(taxable, rate, tax_enabled=True, intra_state=intra_state)
    assert item.line_total == q2(taxable + item.cgst + item.sgst + item.igst)
