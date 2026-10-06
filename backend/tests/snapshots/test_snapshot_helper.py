"""The snapshot helper itself: it must hide DB decimal-scale differences and nothing else."""

from __future__ import annotations

from decimal import Decimal

from tests.snapshots.conftest import _canon_decimals, _dump


def test_trailing_fractional_zeros_do_not_matter():
    assert _dump({"a": "354.00"}) == _dump({"a": "354"}) == _dump({"a": "354.0"})
    assert _dump({"a": "-708.00"}) == _dump({"a": "-708"})


def test_a_real_fraction_is_kept():
    assert _canon_decimals("100.50") == "100.5"
    assert _canon_decimals("0.05") == "0.05"
    assert _dump({"a": "100.50"}) != _dump({"a": "100.05"})


def test_different_amounts_still_differ():
    assert _dump({"a": "354.00"}) != _dump({"a": "355.00"})
    assert _dump({"a": "1242.00"}) != _dump({"a": "1242.01"})


def test_zero_forms_collapse_to_zero():
    assert _canon_decimals("0.00") == "0"
    assert _canon_decimals("-0.00") == "-0" or _canon_decimals("-0.00") == "0"


def test_only_strings_with_a_decimal_point_are_touched():
    payload = {"id": "0001", "gstin": "29ABCDE1234F1Z5", "date": "2026-10-01", "n": 5, "ok": True, "x": None}
    assert _canon_decimals(payload) == payload


def test_decimals_and_dates_in_the_payload_are_stringified_then_canonicalised():
    assert _dump({"v": Decimal("12.50")}) == _dump({"v": "12.5"})


def test_nested_structures_are_canonicalised_everywhere():
    a = {"rows": [{"amt": "1.00"}, {"amt": "2.50"}], "tot": {"debit": "3.50"}}
    b = {"rows": [{"amt": "1"}, {"amt": "2.5"}], "tot": {"debit": "3.5"}}
    assert _dump(a) == _dump(b)
