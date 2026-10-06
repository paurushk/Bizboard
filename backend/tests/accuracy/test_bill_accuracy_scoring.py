"""QOS-0015 — the accuracy scorer itself, without an LLM or a corpus.

The benchmark lane (test_llm_bill_extraction_accuracy.py) skips until real bills exist,
which left its scoring logic unexercised. These cases run in the default suite and
pin how fields are matched, so a wrong scorer cannot quietly move the accuracy floor.
"""

from __future__ import annotations

from tests.accuracy.test_llm_bill_extraction_accuracy import (
    ACCURACY_FLOOR,
    _field_match,
    _score_case,
)

EXPECTED = {
    "supplier_name": "VTC Tradewings Pvt Ltd",
    "supplier_gstin": "09AAPCS3897R1ZX",
    "bill_number": "VTAGR-26-1038635",
    "bill_date": "2026-06-11",
    "lines": [
        {"name": "Olay NA IGF 40gm", "quantity": "3", "unit_price": "140.50", "gst_rate": "18"},
        {"name": "Dettol 100ml", "quantity": "10", "unit_price": "55", "gst_rate": "18"},
    ],
}


def _perfect() -> dict:
    return {**EXPECTED, "lines": [dict(line) for line in EXPECTED["lines"]]}


def test_perfect_extraction_scores_every_field():
    matched, scored = _score_case(EXPECTED, _perfect())
    assert (matched, scored) == (12, 12)  # 4 header fields + 2 lines x 4 fields


def test_amounts_match_across_formatting_but_not_across_values():
    assert _field_match("1,250.00", "1250")
    assert _field_match("140.50", 140.5)
    assert not _field_match("140.50", "140.60")


def test_text_match_ignores_case_and_padding():
    assert _field_match("VTC Tradewings Pvt Ltd", "  vtc tradewings pvt ltd ")
    assert not _field_match("VTC Tradewings Pvt Ltd", "VTC Trade")


def test_a_field_missing_from_the_case_is_not_scored():
    matched, scored = _score_case({"bill_number": "B-1"}, {"bill_number": "B-1", "bill_date": "2026-01-01"})
    assert (matched, scored) == (1, 1)


def test_wrong_header_field_lowers_the_score():
    actual = _perfect()
    actual["supplier_gstin"] = "09AAPCS3897R1ZZ"
    matched, scored = _score_case(EXPECTED, actual)
    assert (matched, scored) == (11, 12)


def test_lines_pair_by_best_match_regardless_of_order():
    actual = _perfect()
    actual["lines"].reverse()
    assert _score_case(EXPECTED, actual) == (12, 12)


def test_a_missed_line_counts_against_the_score_without_crashing():
    actual = _perfect()
    actual["lines"] = actual["lines"][:1]
    matched, scored = _score_case(EXPECTED, actual)
    assert scored == 12
    assert matched == 8


def test_an_actual_line_is_consumed_once():
    expected = {"lines": [{"name": "Soap", "quantity": "1"}, {"name": "Soap", "quantity": "1"}]}
    actual = {"lines": [{"name": "Soap", "quantity": "1"}]}
    assert _score_case(expected, actual) == (2, 4)


def test_an_empty_extraction_scores_zero_and_fails_the_floor():
    matched, scored = _score_case(EXPECTED, {})
    assert matched == 0 and scored == 12
    assert (matched / scored) < ACCURACY_FLOOR
